# wifi_server.py
# 사용법:
# 1) 기존 UI 파일(wifi.html)을 이 스크립트와 같은 폴더에 둡니다.
# 2) 관리자 권한으로 PowerShell / CMD 실행 (netsh 권한 필요)
# 3) python wifi_server.py
# 4) 브라우저에서 http://127.0.0.1:5000 접속 → "다시 스캔" 클릭

from flask import Flask, jsonify, send_from_directory, render_template_string
from collections import Counter
import subprocess
import os
import re

app = Flask(__name__, static_folder='.', static_url_path='')

# 기본값: 사용자가 원래 코드에서 쓰던 인터페이스 이름 ("Wi-Fi" 등)
# 보통 Windows 한글 환경: "Wi-Fi" 또는 "무선 LAN" 또는 "무선 네트워크 연결"
PREFERRED_INTERFACE = "Wi-Fi"

# ---------------------
# 유틸: netsh 명령 실행 (raw 출력 반환)
# ---------------------
def run_netsh(cmd_args):
    """
    cmd_args: 리스트 또는 문자열 (shell=True로 실행)
    반환: decoded text (cp949 우선, 실패시 utf-8)
    """
    try:
        # 윈도우에서는 subprocess.check_output에 shell=True로 편리하게 호출
        if isinstance(cmd_args, list):
            cmd = cmd_args
            result = subprocess.check_output(cmd, shell=False, stderr=subprocess.DEVNULL)
        else:
            cmd = cmd_args
            result = subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL)
        try:
            return result.decode("cp949", errors="ignore")
        except:
            return result.decode("utf-8", errors="ignore")
    except subprocess.CalledProcessError as e:
        # 호출 실패하면 빈 문자열 반환
        return ""

# ---------------------
# 자동 인터페이스 검색
# ---------------------
def detect_interface_name():
    """
    netsh wlan show interfaces 실행해 Name / 이름 항목을 파싱해서 인터페이스 이름 반환
    우선 PREFERRED_INTERFACE가 실제로 동작하는지 확인하고, 아니면 출력에서 추출함.
    """
    # 먼저 시도: PREFERRED_INTERFACE 로 실행해보기
    test_cmd = f'netsh wlan show networks interface="{PREFERRED_INTERFACE}" mode=bssid'
    out = run_netsh(test_cmd)
    if out and "SSID" in out:
        return PREFERRED_INTERFACE

    # 그렇지 않다면 interfaces 출력에서 이름 찾아보기
    raw = run_netsh("netsh wlan show interfaces")
    if not raw:
        return PREFERRED_INTERFACE  # 못찾으면 기본값 반환

    # 인터페이스 이름 파싱 (영문 "Name" 또는 한글 "이름")
    # 예시 줄: "    Name                   : Wi-Fi"
    for line in raw.splitlines():
        line = line.strip()
        # 여러 로케일 처리: "Name" 또는 "이름"
        if line.lower().startswith("name") or line.startswith("이름"):
            parts = line.split(":", 1)
            if len(parts) > 1:
                candidate = parts[1].strip()
                if candidate:
                    # 테스트로 candidate로 스캔 가능한지 시도
                    test2 = run_netsh(f'netsh wlan show networks interface="{candidate}" mode=bssid')
                    if test2 and "SSID" in test2:
                        return candidate
                    else:
                        # 그래도 반환은 후보로 해둠
                        return candidate
    return PREFERRED_INTERFACE

# ---------------------
# 실제 스캔 파싱 함수
# ---------------------
def parse_netsh_networks(interface_name):
    """
    netsh wlan show networks interface="<interface_name>" mode=bssid
    파싱하여 [(ssid, channel, signal), ...] 반환
    """
    cmd = f'netsh wlan show networks interface="{interface_name}" mode=bssid'
    raw = run_netsh(cmd)
    if not raw:
        return [], raw

    networks = []
    ssid = None
    chan = None
    signal = None

    # 여러 포맷을 견디게 라인 단위 파싱
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue

        # SSID 관련: "SSID 1 : MyAP" 또는 "SSID : MyAP"
        # 단, 'BSSID' 포함 라인은 SSID가 아님
        if re.match(r'^(SSID)\s*\d*\s*:', line, flags=re.IGNORECASE) and 'BSSID' not in line:
            parts = line.split(":", 1)
            if len(parts) > 1:
                ssid = parts[1].strip()
                # reset chan/signal to ensure next entries belong to this SSID
                chan = None
                signal = None
            continue

        # Channel 또는 채널
        if re.search(r'\bchannel\b', line, flags=re.IGNORECASE) or "채널" in line:
            parts = line.split(":", 1)
            if len(parts) > 1:
                try:
                    chan = int(re.sub(r'[^0-9]', '', parts[1]))
                except:
                    chan = None
            continue

        # Signal 또는 신호
        if re.search(r'\bsignal\b', line, flags=re.IGNORECASE) or "신호" in line:
            parts = line.split(":", 1)
            if len(parts) > 1:
                sig_text = parts[1].strip()
                sig_num = re.sub(r'[^0-9]', '', sig_text)
                try:
                    signal = int(sig_num) if sig_num else 0
                except:
                    signal = 0

            # SSID와 chan이 확보되어 있으면 리스트에 추가
            if ssid is not None and chan is not None:
                networks.append((ssid, chan, signal if signal is not None else 0))
                # 초기화 (netsh 출력에서 다음 AP가 바로 올 수 있음)
                ssid = None
                chan = None
                signal = None
            continue

    return networks, raw

# ---------------------
# 추천 채널 계산
# ---------------------
def recommend_channel(networks):
    """
    networks: list of (ssid, channel, signal)
    반환: best_channel (int or None), channel_counter (dict)
    """
    if not networks:
        return None, {}

    channels = [n[1] for n in networks if isinstance(n[1], int)]
    counter = Counter(channels)

    # 후보 채널
    candidate_channels_24ghz = [1,6,11]
    candidate_channels_5ghz = [36,40,44,48,149,153,157,161]
    candidates = candidate_channels_24ghz + candidate_channels_5ghz

    best = min(candidates, key=lambda c: counter.get(c, 0))
    return int(최고), dict(counter)

# ---------------------
# Flask 라우트: UI 서빙 (원본 wifi.html 사용)
# ---------------------
@app.route("/")
def index():
    # 같은 폴더에 wifi.html 파일이 있어야 함 (원본 디자인 그대로)
    html_path = os.path.join(os.getcwd(), "wifi.html")
    if os.path.exists(html_path):
        return send_from_directory(os.getcwd(), "wifi.html")
    # 파일이 없으면 간단 안내(개발중)
    return render_template_string("<h3>wifi.html 파일을 동일 폴더에 두고 실행하세요.</h3>")

# 스캔 API
@app.route("/scan")
def api_scan():
    # 자동으로 인터페이스 이름 감지 시도
    iface = detect_interface_name()
    networks, raw = parse_netsh_networks(iface)

    if not networks:
        # 빈 결과일 때 디버깅 정보를 함께 반환 (로컬 개발용)
        return jsonify({
            "error": "주변 Wi-Fi를 찾지 못했습니다.",
            "detail": {
                "used_interface": iface,
                "raw_netsh_output_present": bool(raw),
                "raw_sample": raw[:2000]  # 너무 길면 일부만 반환
            },
            "networks": [],
            "channel_usage": {},
            "recommended": None
        }), 200

    best, counter = recommend_channel(networks)

    return jsonify({
        "networks": [{"ssid": s, "channel": c, "signal": sig} for (s,c,sig) in networks],
        "channel_usage": {str(k): v for k,v in counter.items()},
        "recommended": best,
        "predicted": f"{int((counter.get(best,0) / (max(counter.values()) if counter else 1))*100)}%"
    }), 200

# 디버그용: raw netsh interfaces / networks 출력 확인
@app.route("/debug_netsh")
def debug_netsh():
    iface_info = run_netsh("netsh wlan show interfaces")
    networks_info = run_netsh(f'netsh wlan show networks interface="{PREFERRED_INTERFACE}" mode=bssid')
    return jsonify({
        "preferred_interface": PREFERRED_INTERFACE,
        "interfaces_raw": iface_info[:4000],
        "networks_raw_sample": networks_info[:4000],
    })

if __name__ == "__main__":
    print(">>> Starting Wi-Fi Scanner (Flask).")
    print("Make sure you run this in an ADMIN CMD/PowerShell for netsh to work correctly.")
    print(f"Preferred interface (config): {PREFERRED_INTERFACE}")
    app.run(host="127.0.0.1", port=5000, debug=True)
