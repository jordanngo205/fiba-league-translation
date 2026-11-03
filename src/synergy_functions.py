"""
Synergy Sports API functions for scraping basketball stats.
Requires authentication with Synergy credentials.
"""

import requests
from urllib.parse import unquote
import json
from datetime import datetime, timezone
import os
import platform
import re


class CONSTANTS:
    REPORT_TYPES = {
        "Player Offensive": 0,
        "Player Defensive": 1,
        "Team Offensive": 2,
        "Team Defensive": 3,
    }

    LEAGUE_IDS = {
        "College Men": "54457dce300969b132fcfb37",
        "College Women": "54457dce300969b132fcfb38",
    }

    SEASON_IDS = {
        "2024-2025": "66c6293fac528f0cafb5ea58",
        "2025-2026": "68a4bd7588184c4b74497a91",
    }

    SEASON_IDS_BY_LEAGUE = {
        "College Men": {
            "2024-2025": "66c6293fac528f0cafb5ea58",
            "2025-2026": "68a4bd7588184c4b74497a91",
        },
        "College Women": {
            "2025-2026": "68a4bdab3c211b288250118f",
        },
    }

    PLAY_TYPES = {
        "Isolation": 10,
        "P&R Ball Handler": 11,
        "Post-Up": 15,
        "P&R Roll Man": 31,
        "Spot Up": 50,
        "Off Screen": 67,
        "Hand Off": 78,
        "Cut": 81,
        "Offensive Rebounds": 89,
        "Transition": 92,
        "Miscellaneous": 124,
    }

    CONFERENCE_ID = {
        "U SPORTS": "54457dcf300969b132fcfb65",
        "U SPORTS Men": "54457dcf300969b132fcfb65",
        # Women conferenceId verified from TeamSite URL:
        # https://apps.synergysports.com/basketball/players?...&conferenceIds=54457dcf300969b132fcfb7d
        "U SPORTS Women": "54457dcf300969b132fcfb7d",
    }


def make_windows_safe_(name):
    return re.sub(r'[<>:"/\\|?*]', "_", name)


def write_data(name, data):
    try:
        if platform.system() == "Windows":
            name = make_windows_safe_(name)
        with open(name, "w") as file:
            json.dump(data, file, indent=4)
            print(f"JSON saved to {name}")
    except Exception as e:
        print("Error saving JSON to file:", e)


def _extract_csrf_token(html: str) -> str | None:
    match = re.search(r'<input[^>]+name="__RequestVerificationToken"[^>]+value="([^"]+)"', html)
    if match:
        return match.group(1)
    match = re.search(r'<input[^>]+value="([^"]+)"[^>]+name="__RequestVerificationToken"', html)
    return match.group(1) if match else None


def get_access_token(session, code_verifier, code_challenge, username, password):
    base_url = "https://auth.synergysportstech.com"
    return_url = (
        f"/connect/authorize/callback?client_id=client.basketball.teamsite"
        f"&redirect_uri=https%3A%2F%2Fapps.synergysports.com%2Fbasketball%2Flogin"
        f"&response_type=code&scope=openid%20offline_access%20api.config%20api.security"
        f"%20api.basketball%20api.sport%20api.editor&state=a39224c46b7a4ad7b9b754db6c6b0ffd"
        f"&code_challenge={code_challenge}&code_challenge_method=S256"
    )

    nav_headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:133.0) Gecko/20100101 Firefox/133.0",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-CA,en-US;q=0.7,en;q=0.3",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }

    # Fetch login page to get a fresh CSRF token and session cookie
    login_page = session.get(
        f"{base_url}/Account/Login",
        params={"ReturnUrl": return_url},
        headers=nav_headers,
    )
    csrf_token = _extract_csrf_token(login_page.text)
    if not csrf_token:
        print("Failed to extract CSRF token from login page.")
        return None, None, None

    login_response = session.post(
        f"{base_url}/Account/Login",
        headers={**nav_headers, "Content-Type": "application/x-www-form-urlencoded", "Origin": base_url},
        data={
            "ReturnUrl": return_url,
            "Username": username,
            "Password": password,
            "button": "login",
            "__RequestVerificationToken": csrf_token,
            "RememberLogin": "false",
        },
    )

    if login_response.status_code not in (200, 302) or "Invalid" in login_response.text:
        # Synergy returns the same "Invalid username or password" text whether the
        # password is actually wrong or the account is temporarily locked after too
        # many login attempts. Surface whatever the page says so the two are not
        # confused again -- a lockout is fixed by waiting, a bad password is not.
        body = login_response.text
        if any(w in body.lower() for w in ("locked", "too many", "try again later")):
            print("Login blocked: the account appears temporarily locked after too "
                  "many login attempts. Wait it out -- do not retry.")
        else:
            print("Login failed: the server rejected the credentials. This is either "
                  "a wrong/changed password or a silent lockout; it does not say "
                  "which. Do not retry in a loop.")
        import re as _re
        for _m in _re.findall(r'validation-summary-errors.*?</div>', body, _re.S)[:1]:
            _txt = " ".join(_re.sub(r"<[^>]+>", " ", _m).split())
            if _txt:
                print(f"  server said: {_txt[:200]}")
        return None, None, None

    final_url = login_response.url

    # Handle email-based 2FA challenge
    if "/Account/VerifyCode" in final_url:
        verify_csrf = _extract_csrf_token(login_response.text)
        if not verify_csrf:
            # GET the page fresh to extract the CSRF token
            verify_page = session.get(final_url, headers=nav_headers)
            verify_csrf = _extract_csrf_token(verify_page.text)

        print("Synergy requires email verification. Check your inbox for the code.")
        from paths import TWOFA_FILE
        _code_file = str(TWOFA_FILE)
        try:
            code = input("Enter 2FA code: ").strip()
        except EOFError:
            import time as _time
            print(f"Waiting for 2FA code in {_code_file} ...")
            while not os.path.exists(_code_file):
                _time.sleep(1)
            with open(_code_file) as _f:
                code = _f.read().strip()
            os.remove(_code_file)

        verify_response = session.post(
            final_url,
            headers={**nav_headers, "Content-Type": "application/x-www-form-urlencoded", "Origin": base_url},
            data={
                "Code": code,
                "__RequestVerificationToken": verify_csrf or "",
                "button": "login",
            },
        )

        if verify_response.status_code not in (200, 302) or "Invalid" in verify_response.text:
            print("2FA verification failed.")
            return None, None, None

        final_url = verify_response.url

    if "code=" not in final_url:
        print(f"Unexpected redirect after login: {final_url}")
        return None, None, None

    authorization_code = final_url.split("code=")[-1].split("&")[0]
    token_response = session.post(
        f"{base_url}/connect/token",
        headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
        data={
            "grant_type": "authorization_code",
            "code": authorization_code,
            "redirect_uri": "https://apps.synergysports.com/basketball/login",
            "client_id": "client.basketball.teamsite",
            "code_verifier": code_verifier,
        },
    )
    data = token_response.json()
    if "access_token" not in data:
        print(f"Token exchange failed: {data}")
        return None, None, None
    return data["token_type"], data["refresh_token"], data["access_token"]


def get_player_offensive_play_types(
    access_token,
    session,
    leagueId,
    seasonId,
    playType,
    reportType,
    conferenceId,
    competitionType,
    rankingType,
    perGame,
    minPossessions,
    minPossessionsPerGame,
    competitionDefinitionKey=None,
):
    url = "https://basketball.synergysportstech.com/api/leaderboards/recordswithsparseranks"
    if competitionDefinitionKey:
        competition_key = str(competitionDefinitionKey)
    else:
        competition_key = f"{leagueId}:CEE"
    params = {
        "leagueId": leagueId,
        "seasonId": seasonId,
        "playType": f"{playType}",
        "reportType": f"{reportType}",
        "competitionDefinitionKey": competition_key,
        "conferenceId": f"{conferenceId}",
        "competitionType": f"{competitionType}",
        "rankingType": f"{rankingType}",
        "perGame": "true" if perGame else "false",
        "minPossessions": f"{minPossessions}",
        "minPossessionsPerGame": "true" if minPossessionsPerGame else "false",
        "ascending": "false",
        "skip": "0",
        "take": "4096",
        "quickSearchPhrase": "",
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:133.0) Gecko/20100101 Firefox/133.0",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-CA,en-US;q=0.7,en;q=0.3",
        "Accept-Encoding": "gzip",
        "Authorization": f"Bearer {access_token}",
    }
    response = session.get(url, headers=headers, params=params)
    return response.json()


def get_possession_reports(
    access_token,
    session,
    expressions,
    includePartiallyLoggedGames=False,
    includePlayByPlayStats=False,
    timeout=120,
):
    """Query Synergy possession reports API with one or more expressions."""
    url = "https://basketball.synergysportstech.com/api/possessionreports"
    payload = {
        "expressions": expressions,
        "includePartiallyLoggedGames": bool(includePartiallyLoggedGames),
        "includePlayByPlayStats": bool(includePlayByPlayStats),
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:133.0) Gecko/20100101 Firefox/133.0",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-CA,en-US;q=0.7,en;q=0.3",
        "Accept-Encoding": "gzip, deflate",
        "Content-Type": "application/json; charset=utf-8",
        "Authorization": f"Bearer {access_token}",
        "X-SYNERGY-CLIENT": "ProductVersion=2024.12.12.4562; ProductName=Basketball.TeamSite",
        "Origin": "https://apps.synergysports.com",
        "Connection": "keep-alive",
        "Referer": "https://apps.synergysports.com/",
    }
    response = session.post(url, headers=headers, json=payload, timeout=timeout)
    return response.json()


def get_upcoming_games(session, token_type, access_token, conferenceIds):
    url = "https://basketball.synergysportstech.com/api/games"
    payload = {
        "excludeGamesWithoutCompetition": True,
        "seasonIds": ["68a4bd7588184c4b74497a91"],  # 2025-26 season
        "conferenceIds": conferenceIds,
        "competitionIds": [
            "560100ac8dc7a24394b95621",
            "560100ac8dc7a24394b955f1",
            "56d8941d50238a164760b2f1",
            "560100ac8dc7a24394b95682",
            "560100ac8dc7a24394b955f0",
            "56d4d42050238a16475ffe82",
            "560100ac8dc7a24394b95683",
            "623b3e428863b92839774245",
            "642711fc24658713c84e22d0",
            "560100ac8dc7a24394b95638",
            "560100ac8dc7a24394b95663",
            "56d8976550238a164760b31b",
            "56d8976550238a164760b31c",
            "560100ac8dc7a24394b95622",
            "560100ac8dc7a24394b95651",
            "560100ac8dc7a24394b95654",
            "560100ac8dc7a24394b9567b",
            "56e1d38050238a1647626d26",
            "560100ac8dc7a24394b9565d",
            "560100ac8dc7a24394b9566d",
            "560100ac8dc7a24394b9567c",
            "623b3e656b7ff0a2745e33bd",
            "560100ac8dc7a24394b955fa",
            "560100ac8dc7a24394b9562a",
            "560100ac8dc7a24394b955f9",
            "65f8ef06b87385578a256650",
        ],
        "skip": 0,
        "take": 100,
        "endDate": f"{datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')}",
        "statuses": [4, 1, 2, 3, 5],
        "sort": "utc:desc",
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:133.0) Gecko/20100101 Firefox/133.0",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-CA,en-US;q=0.7,en;q=0.3",
        "Accept-Encoding": "gzip, deflate, br, zstd",
        "Content-Type": "application/json; charset=utf-8",
        "Authorization": f"{token_type} {access_token}",
        "X-SYNERGY-CLIENT": "ProductVersion=2024.12.12.4562; ProductName=Basketball.TeamSite",
        "Origin": "https://apps.synergysports.com",
        "Connection": "keep-alive",
        "Referer": "https://apps.synergysports.com/",
    }
    response = session.post(url, headers=headers, json=payload)
    return response.json()


def get_game_data(session, token_type, access_token, game_id):
    url = f"https://basketball.synergysportstech.com/api/games/{game_id}"
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:133.0) Gecko/20100101 Firefox/133.0",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-CA,en-US;q=0.7,en;q=0.3",
        "Accept-Encoding": "gzip, deflate",
        "Authorization": f"{token_type} {access_token}",
        "X-SYNERGY-CLIENT": "ProductVersion=2024.12.12.4562; ProductName=Basketball.TeamSite",
        "Origin": "https://apps.synergysports.com",
        "Connection": "keep-alive",
        "Referer": "https://apps.synergysports.com/",
    }
    response = session.get(url, headers=headers)
    return response.json()


def get_play_by_plays(session, token_type, access_token, game_id):
    url = f"https://basketball.synergysportstech.com/api/games/{game_id}/playbyplays"
    print(url)
    params = {"skip": 0, "take": 1000}
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:133.0) Gecko/20100101 Firefox/133.0",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-CA,en-US;q=0.7,en;q=0.3",
        "Accept-Encoding": "gzip, deflate",
        "Authorization": f"{token_type} {access_token}",
        "X-SYNERGY-CLIENT": "ProductVersion=2024.12.12.4562; ProductName=Basketball.TeamSite",
        "Origin": "https://apps.synergysports.com",
        "Connection": "keep-alive",
        "Referer": "https://apps.synergysports.com/",
    }
    response = session.get(url, headers=headers, params=params)
    return response.json()


def get_line_ups(session, token_type, access_token, game_id, team_one, team_two):
    url = f"https://basketball.synergysportstech.com/api/possessionreports"
    payload = {
        "expressions": [
            f"game eq oid({game_id}) and offensiveteam eq oid({team_one}) and play eq 1 group offensiveteam, offensivelineup",
            f"game eq oid({game_id}) and offensiveteam eq oid({team_two}) and play eq 1 group offensiveteam, offensivelineup",
        ],
        "includePartiallyLoggedGames": False,
        "includePlayByPlayStats": False,
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:133.0) Gecko/20100101 Firefox/133.0",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-CA,en-US;q=0.7,en;q=0.3",
        "Accept-Encoding": "gzip, deflate",
        "Authorization": f"{token_type} {access_token}",
        "X-SYNERGY-CLIENT": "ProductVersion=2024.12.12.4562; ProductName=Basketball.TeamSite",
        "Origin": "https://apps.synergysports.com",
        "Connection": "keep-alive",
        "Referer": "https://apps.synergysports.com/",
    }
    response = session.post(url, headers=headers, json=payload)
    return response.json()


def get_all_shots(
    session,
    token_type,
    access_token,
    season_id,
    competition_id,
    team_id,
    defense=False,
    zone_names=None,
    zones_breakdown=1
):
    """
    Fetch all shots with x/y coordinates from Synergy's multi-game shot chart API.
    
    Args:
        session: requests Session
        token_type: Bearer token type
        access_token: OAuth access token
        season_id: Synergy season ID (e.g., "66c6293fac528f0cafb5ea58" for 2024-25)
        competition_id: Competition definition key (e.g., "54457dce300969b132fcfb37:CEE")
        team_id: Synergy team ID
        defense: If True, get defensive shots (what opponents shot against team)
        zone_names: List of zone names to filter (None = all zones)
        zones_breakdown: Zone breakdown type (integer enum, 1=Standard)
    
    Returns:
        List of shot data batches, each containing 'result' array with shots
    """
    url = "https://basketball.synergysportstech.com/api/court/8/shots"
    
    skip = 0
    take = 1000
    all_records = []
    
    # Default zone names (13-zone breakdown)
    if zone_names is None:
        zone_names = [
            "Rim", "Paint (Non-RA)", "Left Mid-Range",
            "Center Mid-Range", "Right Mid-Range",
            "Left Corner 3", "Right Corner 3",
            "Left Wing 3", "Right Wing 3", "Center 3"
        ]
    
    while True:
        payload = {
            "competitionDefinitionKey": competition_id,
            "defense": defense,
            "seasonId": season_id,
            "skip": skip,
            "take": take,
            "teamId": team_id,
            "zoneNames": zone_names,
            "zonesBreakdown": zones_breakdown,
        }
        
        headers = {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:133.0) Gecko/20100101 Firefox/133.0",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-CA,en-US;q=0.7,en;q=0.3",
            "Accept-Encoding": "gzip, deflate",
            "Content-Type": "application/json; charset=utf-8",
            "Authorization": f"{token_type} {access_token}",
            "X-SYNERGY-CLIENT": "ProductVersion=2026.02.25.10717; ProductName=Basketball.TeamSite",
            "Origin": "https://apps.synergysports.com",
            "Connection": "keep-alive",
            "Referer": "https://apps.synergysports.com/",
        }
        
        response = session.post(url, headers=headers, json=payload, timeout=60)
        
        if response.status_code != 200:
            print(f"Error fetching shots: {response.status_code}")
            print(f"Response: {response.text[:500] if response.text else 'empty'}")
            break
            
        batch = response.json()
        all_records.append(batch)
        
        # Check if we got less than requested (end of data)
        if 'result' not in batch or len(batch.get('result', [])) < take:
            break
        
        skip += take
    
    return all_records
