"""Mock dataset generator for interactive demos and offline testing."""

from datetime import datetime, timedelta
import random
from typing import List, Tuple
from instagram_analyzer.parser import ParsedEntry


def generate_sample_dataset() -> Tuple[List[ParsedEntry], List[ParsedEntry]]:
    """
    Generate a realistic, diverse dataset of followers and following.
    Includes:
    - Mutuals (friends who follow each other)
    - Celebrities/Brands (you follow them, they don't follow back - swipe right candidates)
    - Inactive / Unreciprocated acquaintances (swipe left candidates)
    - Fans / Secret admirers (follow you, but you don't follow back)
    """
    base_time = datetime(2025, 1, 15, 12, 0, 0)

    # 1. Mutuals (60 accounts)
    mutual_names = [
        "alex_rivers", "sophia_chen", "marcus_vance", "elena_rostova", "liam_odonnell",
        "maya_patel", "noah_kim", "olivia_bennett", "lucas_silva", "chloe_dupont",
        "ethan_wright", "emma_larsson", "aaron_brooks", "mia_tanaka", "sam_mendoza",
        "hannah_schmidt", "julian_cross", "zoe_alvarez", "gabriel_costa", "isabella_rossi",
        "jordan_lee", "ava_martinez", "dylan_taylor", "grace_kelly_dev", "leo_zimmerman",
        "amara_singh", "caleb_turner", "leila_habib", "owen_clark", "ruby_fletcher",
        "nathan_gray", "claire_fontaine", "felix_braun", "stella_novak", "victor_hugo_code",
        "daphne_blake", "jasper_hale", "penelope_park", "tariq_mansoor", "fiona_gallagher",
        "brandon_stark", "camila_cabral", "diego_maradona_fan", "freya_lind", "haruki_murakami_lit",
        "iris_west", "kai_nakamura", "luna_lovegood_ai", "milo_ventimiglia_fan", "nadia_comaneci_gym",
        "oscar_isaac_stan", "priya_deshmukh", "quinn_fabray", "rafael_nadal_club", "sienna_miller_style",
        "tomas_soucek", "uma_thurman_cinema", "valerie_pieris", "winston_bishop", "xander_cage"
    ]

    # 2. Celebrities, Creators & Brands (You follow, they don't follow back - ~35 accounts)
    celeb_brand_names = [
        "natgeo", "nasa", "wired", "openai", "google", "apple", "github", "theverge",
        "mkbhd", "hubermanlab", "lexfridman", "timferriss", "karpathy", "ylecun",
        "paulgraham", "satyanadella", "sundarpichai", "sama", "zuck", "elonmusk",
        "nike", "patagonia", "redbull", "spotify", "netflix", "nytimes", "newyorkermag",
        "archdigest", "kinfolk", "pitchfork", "formula1", "premierleague", "nba",
        "tasty", "bonappetitmag"
    ]

    # 3. Unreciprocated Acquaintances / Inactive accounts (You follow, they don't follow back - ~45 accounts)
    unreciprocated_names = [
        "crypto_trader_99", "ghost_traveler", "random_drop_shipper", "nft_collector_xyz",
        "highschool_mate_2017", "camp_counselor_dan", "ex_colleague_dave", "roommate_sublet_2019",
        "marketing_guru_dan", "growth_hacker_jay", "fitness_promo_bot", "daily_quotes_aesthetic",
        "urban_vibes_blog", "vintage_thrift_resell", "dj_drop_beats", "streetwear_plug_la",
        "crypto_alpha_leaks", "startup_founder_hustle", "nomad_life_bali", "coffee_beans_co",
        "tech_gear_unboxing", "sunset_photography_page", "downtown_barber_co", "artisan_sourdough_sf",
        "sneaker_vault_ny", "cozy_interiors_daily", "minimalist_desk_setups", "synthwave_radio",
        "study_with_me_lofi", "wanderlust_passport", "matcha_club_tokyo", "street_art_berlin",
        "sunset_chaser_sd", "cycling_club_pdx", "climbing_gym_crew", "surf_forecast_norcal",
        "boba_addict_bay", "plant_parent_daily", "ceramic_pottery_studio", "film_camera_club",
        "bookstore_cats", "vinyl_records_collector", "espresso_shots_only", "hiking_trails_tahoe",
        "old_internship_friend"
    ]

    # 4. Fans / Secret Admirers (They follow you, you don't follow them - ~25 accounts)
    fan_names = [
        "fan_of_tech", "silent_lurker_01", "student_coder_mike", "design_enthusiast_amy",
        "open_source_contributor", "dev_rel_scout", "recruiter_sarah_tech", "junior_dev_hopeful",
        "podcast_listener_rob", "conference_attendee_ken", "hackathon_teammate_ali",
        "ai_researcher_junior", "swiftui_learner_dan", "python_novice_ben", "frontend_fanatic",
        "data_science_learner", "product_manager_aspirant", "indie_hacker_fan", "remote_worker_chaz",
        "web3_curious_cat", "algorithms_enthusiast", "react_dev_austin", "docker_fanatic",
        "cloud_engineer_toby", "startup_job_seeker"
    ]

    followers: List[ParsedEntry] = []
    following: List[ParsedEntry] = []

    # Populate mutuals in both
    for i, uname in enumerate(mutual_names):
        ts = (base_time - timedelta(days=i * 5, hours=i)).strftime("%b %d, %Y %I:%M %p")
        followers.append(ParsedEntry(username=uname, timestamp_str=ts))
        following.append(ParsedEntry(username=uname, timestamp_str=ts))

    # Populate celebs & unreciprocated in following only
    for i, uname in enumerate(celeb_brand_names + unreciprocated_names):
        ts = (base_time - timedelta(days=i * 3, hours=i % 12)).strftime("%b %d, %Y %I:%M %p")
        following.append(ParsedEntry(username=uname, timestamp_str=ts))

    # Populate fans in followers only
    for i, uname in enumerate(fan_names):
        ts = (base_time - timedelta(days=i * 4, hours=i % 24)).strftime("%b %d, %Y %I:%M %p")
        followers.append(ParsedEntry(username=uname, timestamp_str=ts))

    # Shuffle for realistic ordering
    rng = random.Random(42)
    rng.shuffle(followers)
    rng.shuffle(following)

    return followers, following
