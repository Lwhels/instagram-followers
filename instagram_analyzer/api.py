"""FastAPI backend server for Instagram Follower Analyzer with multi-tenancy and async file upload framework."""

import asyncio
import os
import shutil
import tempfile
import uuid
from typing import List, Optional
from fastapi import (
    BackgroundTasks,
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles

from instagram_analyzer.auth import (
    TokenResponse,
    UserProfile,
    create_access_token,
    decode_access_token,
    hash_password,
    security_bearer,
    verify_password,
)
from instagram_analyzer.database import Database
from instagram_analyzer.engine import FollowerEngine
from instagram_analyzer.models import (
    AuditMetrics,
    BatchDecisionRequest,
    DecisionType,
    DiffResult,
    InstagramAccount,
    RelationshipType,
    SnapshotMeta,
    SwipeAction,
    UploadJobResponse,
    UserLoginRequest,
    UserRegisterRequest,
)
from instagram_analyzer.upload_framework import (
    UploadSecurityError,
    UploadStorage,
    process_upload_task,
)


def create_app(db_path: Optional[str] = None, upload_dir: Optional[str] = None) -> FastAPI:
    app = FastAPI(
        title="Instagram Follower Analyzer & Vault",
        description="Multi-tenant follower relationship auditor with interactive swipe triage, authentication, and async upload pipeline",
        version="2.1.0",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    resolved_db_path = db_path or os.getenv("DATABASE_PATH", os.getenv("DATABASE_URL", "follower_vault.db"))
    resolved_upload_dir = upload_dir or os.getenv("UPLOAD_DIR", "uploads_staging")

    engine = FollowerEngine(db_path=resolved_db_path)
    storage = UploadStorage(base_dir=resolved_upload_dir)

    # Auth Dependency
    def get_current_user(credentials=Depends(security_bearer)) -> dict:
        """Extract user from Bearer JWT; default to demo user (id=1) if unauthenticated."""
        if not credentials:
            # Fallback to demo user
            demo_user = engine.db.get_user_by_id(1)
            if demo_user:
                return demo_user
            return {"id": 1, "email": "demo@followervault.local", "display_name": "Demo User"}

        payload = decode_access_token(credentials.credentials)
        user_id = int(payload.get("sub", 1))
        user = engine.db.get_user_by_id(user_id)
        if not user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
        return user

    # -------------------------------------------------------------
    # Authentication Routes
    # -------------------------------------------------------------
    @app.post("/api/auth/register", response_model=TokenResponse)
    def register_user(req: UserRegisterRequest):
        existing = engine.db.get_user_by_email(req.email)
        if existing:
            raise HTTPException(status_code=400, detail="Email is already registered")

        if len(req.password) < 6:
            raise HTTPException(status_code=400, detail="Password must be at least 6 characters")

        pw_hash = hash_password(req.password)
        user_id = engine.db.create_user(
            email=req.email,
            password_hash=pw_hash,
            display_name=req.display_name,
        )
        token = create_access_token(user_id=user_id, email=req.email)
        user = engine.db.get_user_by_id(user_id)

        return TokenResponse(
            access_token=token,
            user=UserProfile(
                id=user["id"],
                email=user["email"],
                display_name=user["display_name"],
                created_at=user["created_at"],
            ),
        )

    @app.post("/api/auth/login", response_model=TokenResponse)
    def login_user(req: UserLoginRequest):
        user = engine.db.get_user_by_email(req.email)
        if not user or not verify_password(req.password, user["password_hash"]):
            raise HTTPException(status_code=401, detail="Invalid email or password")

        token = create_access_token(user_id=user["id"], email=user["email"])
        return TokenResponse(
            access_token=token,
            user=UserProfile(
                id=user["id"],
                email=user["email"],
                display_name=user["display_name"],
                created_at=user["created_at"],
            ),
        )

    @app.post("/api/auth/demo", response_model=TokenResponse)
    def login_demo_user():
        """Instant one-click demo login, seeds demo dataset if empty."""
        user = engine.db.get_user_by_id(1)
        if not user:
            user_id = engine.db.create_user("demo@followervault.local", hash_password("demo123"), "Demo User")
            user = engine.db.get_user_by_id(user_id)

        # Seed sample data if user has no snapshots
        if not engine.db.get_latest_snapshot_id(user_id=user["id"]):
            engine.load_sample_demo(snapshot_name="Interactive Demo Snapshot", user_id=user["id"])

        token = create_access_token(user_id=user["id"], email=user["email"])
        return TokenResponse(
            access_token=token,
            user=UserProfile(
                id=user["id"],
                email=user["email"],
                display_name=user["display_name"],
                created_at=user["created_at"],
            ),
        )

    @app.get("/api/auth/me", response_model=UserProfile)
    def get_me(user: dict = Depends(get_current_user)):
        return UserProfile(
            id=user["id"],
            email=user["email"],
            display_name=user["display_name"],
            created_at=user["created_at"],
        )

    # -------------------------------------------------------------
    # Async File Upload Framework Routes
    # -------------------------------------------------------------
    @app.post("/api/uploads/start", response_model=UploadJobResponse, status_code=status.HTTP_202_ACCEPTED)
    async def start_async_upload(
        background_tasks: BackgroundTasks,
        file: UploadFile = File(...),
        snapshot_name: str = Form("Imported Export"),
        user: dict = Depends(get_current_user),
    ):
        """Asynchronous upload intake: validates, stages file, and queues background processing."""
        user_id = user["id"]
        original_filename = file.filename or "export.zip"
        ext = os.path.splitext(original_filename)[1].lower()

        try:
            file_id, staged_path = storage.save_upload_stream(file.file, original_filename)
        except UploadSecurityError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Upload saving failed: {str(e)}")

        job_id = str(uuid.uuid4())
        engine.db.create_upload_job(
            job_id=job_id,
            user_id=user_id,
            filename=original_filename,
            file_type=ext.lstrip("."),
        )

        # Dispatch background parsing worker
        background_tasks.add_task(
            process_upload_task,
            job_id=job_id,
            user_id=user_id,
            file_path=staged_path,
            snapshot_name=snapshot_name,
            db=engine.db,
            storage=storage,
        )

        job = engine.db.get_upload_job(job_id, user_id=user_id)
        return job

    @app.get("/api/uploads/{job_id}", response_model=UploadJobResponse)
    def poll_upload_job(job_id: str, user: dict = Depends(get_current_user)):
        job = engine.db.get_upload_job(job_id, user_id=user["id"])
        if not job:
            raise HTTPException(status_code=404, detail="Upload job not found")
        return job

    # -------------------------------------------------------------
    # Scoped Follower & Swipe Analysis Routes
    # -------------------------------------------------------------
    @app.get("/api/status")
    def get_status(user: dict = Depends(get_current_user)):
        user_id = user["id"]
        latest_id = engine.db.get_latest_snapshot_id(user_id=user_id)
        snapshots = engine.db.list_snapshots(user_id=user_id)
        return {
            "status": "healthy",
            "user_id": user_id,
            "has_data": latest_id is not None,
            "latest_snapshot_id": latest_id,
            "total_snapshots": len(snapshots),
        }

    @app.get("/api/snapshots", response_model=List[SnapshotMeta])
    def get_snapshots(user: dict = Depends(get_current_user)):
        return engine.db.list_snapshots(user_id=user["id"])

    @app.get("/api/metrics", response_model=AuditMetrics)
    def get_metrics(snapshot_id: Optional[int] = Query(None), user: dict = Depends(get_current_user)):
        return engine.recompute(snapshot_id=snapshot_id, user_id=user["id"])

    @app.get("/api/accounts", response_model=List[InstagramAccount])
    def get_accounts(
        snapshot_id: Optional[int] = Query(None),
        relationship: Optional[RelationshipType] = Query(None),
        decision: Optional[DecisionType] = Query(None),
        search: Optional[str] = Query(None),
        limit: int = Query(500, ge=1, le=5000),
        offset: int = Query(0, ge=0),
        user: dict = Depends(get_current_user),
    ):
        return engine.db.get_accounts(
            snapshot_id=snapshot_id,
            user_id=user["id"],
            relationship=relationship,
            decision=decision,
            search=search,
            limit=limit,
            offset=offset,
        )

    @app.get("/api/swipe/deck", response_model=List[InstagramAccount])
    def get_swipe_deck(
        snapshot_id: Optional[int] = Query(None),
        limit: int = Query(50, ge=1, le=200),
        user: dict = Depends(get_current_user),
    ):
        return engine.db.get_swipe_deck(snapshot_id=snapshot_id, user_id=user["id"], limit=limit)

    @app.post("/api/swipe/decision")
    def post_swipe_decision(action: SwipeAction, user: dict = Depends(get_current_user)):
        metrics = engine.swipe(
            username=action.username,
            decision=action.decision,
            user_id=user["id"],
            tags=action.tags,
            notes=action.notes,
        )
        return {
            "success": True,
            "username": action.username,
            "decision": action.decision,
            "metrics": metrics,
        }

    @app.post("/api/swipe/undo")
    def post_swipe_undo(user: dict = Depends(get_current_user)):
        restored, metrics = engine.undo(user_id=user["id"])
        if not restored:
            raise HTTPException(status_code=400, detail="No action to undo")
        return {
            "success": True,
            "restored": restored,
            "metrics": metrics,
        }

    @app.post("/api/batch/decision")
    def post_batch_decision(req: BatchDecisionRequest, user: dict = Depends(get_current_user)):
        metrics = engine.batch_decide(
            usernames=req.usernames,
            decision=req.decision,
            user_id=user["id"],
            tags=req.tags,
        )
        return {
            "success": True,
            "updated_count": len(req.usernames),
            "metrics": metrics,
        }

    @app.post("/api/recompute", response_model=AuditMetrics)
    def post_recompute(snapshot_id: Optional[int] = Query(None), user: dict = Depends(get_current_user)):
        return engine.recompute(snapshot_id=snapshot_id, user_id=user["id"])

    @app.post("/api/demo/load")
    def post_load_demo(snapshot_name: str = Query("Interactive Demo Snapshot"), user: dict = Depends(get_current_user)):
        snap_id = engine.load_sample_demo(snapshot_name=snapshot_name, user_id=user["id"])
        metrics = engine.recompute(snapshot_id=snap_id, user_id=user["id"])
        return {
            "success": True,
            "snapshot_id": snap_id,
            "metrics": metrics,
        }

    @app.post("/api/upload")
    async def post_upload(
        snapshot_name: str = Form("Imported Snapshot"),
        followers_file: Optional[UploadFile] = File(None),
        following_file: Optional[UploadFile] = File(None),
        zip_file: Optional[UploadFile] = File(None),
        user: dict = Depends(get_current_user),
    ):
        """Synchronous upload fallback for simple direct imports."""
        user_id = user["id"]
        with tempfile.TemporaryDirectory() as tmpdir:
            zip_path = None
            f_path = None
            fg_path = None

            if zip_file and zip_file.filename:
                zip_path = os.path.join(tmpdir, zip_file.filename)
                with open(zip_path, "wb") as f:
                    shutil.copyfileobj(zip_file.file, f)
            else:
                if followers_file and followers_file.filename:
                    f_path = os.path.join(tmpdir, followers_file.filename)
                    with open(f_path, "wb") as f:
                        shutil.copyfileobj(followers_file.file, f)

                if following_file and following_file.filename:
                    fg_path = os.path.join(tmpdir, following_file.filename)
                    with open(fg_path, "wb") as f:
                        shutil.copyfileobj(following_file.file, f)

            try:
                snap_id = engine.ingest_files(
                    snapshot_name=snapshot_name,
                    followers_file=f_path,
                    following_file=fg_path,
                    zip_file=zip_path,
                    user_id=user_id,
                )
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"Failed to parse files: {str(e)}")

            metrics = engine.recompute(snapshot_id=snap_id, user_id=user_id)
            return {
                "success": True,
                "snapshot_id": snap_id,
                "metrics": metrics,
            }

    @app.get("/api/export")
    def get_export(
        format: str = Query("csv", pattern="^(csv|json|markdown)$"),
        snapshot_id: Optional[int] = Query(None),
        relationship: Optional[RelationshipType] = Query(None),
        decision: Optional[DecisionType] = Query(None),
        user: dict = Depends(get_current_user),
    ):
        content = engine.export_data(
            format_type=format,
            snapshot_id=snapshot_id,
            user_id=user["id"],
            relationship=relationship,
            decision=decision,
        )
        media_types = {
            "csv": "text/csv",
            "json": "application/json",
            "markdown": "text/markdown",
        }
        filename = f"instagram_audit_{format}.{('md' if format == 'markdown' else format)}"
        return Response(
            content=content,
            media_type=media_types[format],
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @app.post("/api/snapshots/diff", response_model=DiffResult)
    def post_snapshots_diff(
        snapshot_a_id: int = Query(...),
        snapshot_b_id: int = Query(...),
        user: dict = Depends(get_current_user),
    ):
        try:
            return engine.db.diff_snapshots(
                snapshot_a_id=snapshot_a_id,
                snapshot_b_id=snapshot_b_id,
                user_id=user["id"],
            )
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

    # Static UI files
    static_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")
    if os.path.exists(static_dir):
        app.mount("/static", StaticFiles(directory=static_dir), name="static")

        @app.get("/", response_class=HTMLResponse)
        def serve_index():
            index_path = os.path.join(static_dir, "index.html")
            if os.path.exists(index_path):
                with open(index_path, "r", encoding="utf-8") as f:
                    return f.read()
            return "<h1>Instagram Follower Analyzer</h1>"

    return app


app = create_app()
