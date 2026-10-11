"""FastAPI backend server for Instagram Follower Analyzer."""

import os
import shutil
import tempfile
from typing import List, Optional
from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles

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
)

# App factory
def create_app(db_path: str = "follower_vault.db") -> FastAPI:
    app = FastAPI(
        title="Instagram Follower Analyzer & Swipe Deck",
        description="Production-grade local-first follower relationship auditor with interactive swipe deck and recomputation",
        version="2.0.0",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    engine = FollowerEngine(db_path=db_path)

    # API Routes
    @app.get("/api/status")
    def get_status():
        latest_id = engine.db.get_latest_snapshot_id()
        snapshots = engine.db.list_snapshots()
        return {
            "status": "healthy",
            "has_data": latest_id is not None,
            "latest_snapshot_id": latest_id,
            "total_snapshots": len(snapshots),
        }

    @app.get("/api/snapshots", response_model=List[SnapshotMeta])
    def get_snapshots():
        return engine.db.list_snapshots()

    @app.get("/api/metrics", response_model=AuditMetrics)
    def get_metrics(snapshot_id: Optional[int] = Query(None)):
        return engine.recompute(snapshot_id=snapshot_id)

    @app.get("/api/accounts", response_model=List[InstagramAccount])
    def get_accounts(
        snapshot_id: Optional[int] = Query(None),
        relationship: Optional[RelationshipType] = Query(None),
        decision: Optional[DecisionType] = Query(None),
        search: Optional[str] = Query(None),
        limit: int = Query(500, ge=1, le=5000),
        offset: int = Query(0, ge=0),
    ):
        return engine.db.get_accounts(
            snapshot_id=snapshot_id,
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
    ):
        return engine.db.get_swipe_deck(snapshot_id=snapshot_id, limit=limit)

    @app.post("/api/swipe/decision")
    def post_swipe_decision(action: SwipeAction):
        metrics = engine.swipe(
            username=action.username,
            decision=action.decision,
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
    def post_swipe_undo():
        restored, metrics = engine.undo()
        if not restored:
            raise HTTPException(status_code=400, detail="No action to undo")
        return {
            "success": True,
            "restored": restored,
            "metrics": metrics,
        }

    @app.post("/api/batch/decision")
    def post_batch_decision(req: BatchDecisionRequest):
        metrics = engine.batch_decide(
            usernames=req.usernames,
            decision=req.decision,
            tags=req.tags,
        )
        return {
            "success": True,
            "updated_count": len(req.usernames),
            "metrics": metrics,
        }

    @app.post("/api/recompute", response_model=AuditMetrics)
    def post_recompute(snapshot_id: Optional[int] = Query(None)):
        return engine.recompute(snapshot_id=snapshot_id)

    @app.post("/api/demo/load")
    def post_load_demo(snapshot_name: str = Query("Interactive Demo Snapshot")):
        snap_id = engine.load_sample_demo(snapshot_name=snapshot_name)
        metrics = engine.recompute(snapshot_id=snap_id)
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
    ):
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
                )
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"Failed to parse files: {str(e)}")

            metrics = engine.recompute(snapshot_id=snap_id)
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
    ):
        content = engine.export_data(
            format_type=format,
            snapshot_id=snapshot_id,
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
    def post_snapshots_diff(snapshot_a_id: int = Query(...), snapshot_b_id: int = Query(...)):
        try:
            return engine.db.diff_snapshots(snapshot_a_id=snapshot_a_id, snapshot_b_id=snapshot_b_id)
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


# Default app instance
app = create_app()
