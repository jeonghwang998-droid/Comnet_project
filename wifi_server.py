# wifi_server.py
import subprocess
from collections import Counter
from flask import Flask, jsonify, render_template_string
import json
import os

# --- 설정 ---
INTERFACE_NAME = "Wi-Fi"   # 시스템의 무선 인터페이스 이름을 정확히 넣으세요 (netsh wlan show interfaces 로 확인)
HOST = "127.0.0.1"
PORT = 5000

# --- HTML (프론트엔드) ---
HTML = """<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>Wi-Fi Optimizer — Prototype</title>
  <style>
    /* (여기에 기존 CSS 전체를 그대로 붙여넣었습니다. 생략하지 않고 실제로 사용할 때는 본문 그대로 사용하세요.) */
    *{box-sizing:border-box;margin:0;padding:0}
    :root{--bg:#f5f7fb;--card:#ffffff;--muted:#6b7280;--accent:#2563eb;--good:#10b981;--warn:#f59e0b;--bad:#ef4444;font-family:Inter, system-ui, -apple-system,"Segoe UI",Roboto,"Noto Sans KR","Apple SD Gothic Neo",sans-serif}
    body{background:var(--bg);color:#111;line-height:1.3;padding:28px}
    .container{max-width:1100px;margin:0 auto;display:grid;grid-template-columns:1fr 380px;gap:24px}
    header{grid-column:1/-1;display:flex;align-items:center;justify-content:space-between;margin-bottom:12px}
    .brand{display:flex;gap:12px;align-items:center}
    .logo{width:44px;height:44px;border-radius:8px;background:linear-gradient(135deg,var(--accent),#7c3aed);display:flex;align-items:center;justify-content:center;color:white;font-weight:700}
    h1{font-size:18px}
    .top-actions{display:flex;gap:10px;align-items:center}
    button.icon{background:transparent;border:0;padding:8px;border-radius:8px;cursor:pointer}
    .card{background:var(--card);border-radius:12px;padding:18px;box-shadow:0 6px 18px rgba(15,23,42,0.06)}
    .main-card{display:flex;flex-direction:column;gap:14px}
    .ssid-row{display:flex;align-items:center;justify-content:space-between}
    .ssid{font-weight:600}
    .meta{color:var(--muted);font-size:13px}
    .channel-row{display:flex;align-items:center;gap:16px}
    .channel-big{font-size:40px;font-weight:700}
    .signal{display:flex;flex-direction:column;gap:6px}
    .progress-wrap{width:240px}
    .progress{height:14px;background:#eee;border-radius:8px;overflow:hidden}
    .progress > i{display:block;height:100%;background:linear-gradient(90deg,var(--good),var(--warn));width:40%}
    .status-tag{display:inline-block;padding:6px 10px;border-radius:999px;font-weight:600}
    .recommend{display:flex;align-items:center;justify-content:space-between;margin-top:6px}
    .rec-box{display:flex;gap:12px;align-items:center}
    .rec-channel{background:linear-gradient(90deg,#fff,rgba(0,0,0,0.02));padding:8px 12px;border-radius:10px;font-weight:700}
    .apply-btn{background:var(--accent);color:white;border:0;padding:10px 14px;border-radius:10px;cursor:pointer}
    .summary{display:flex;flex-direction:column;gap:12px}
    .mini{display:flex;flex-direction:column;gap:8px}
    .mini .row{display:flex;justify-content:space-between;color:var(--muted)}
    .wide{grid-column:1/ -1}
    .chart{display:flex;flex-direction:column;gap:10px;padding:12px}
    .bars{display:flex;gap:8px;align-items:end;height:180px;padding:8px}
    .bar{flex:1;border-radius:6px;padding:6px 4px;display:flex;align-items:flex-end;justify-content:center;position:relative}
    .bar > span{position:absolute;top:-22px;font-size:12px;color:var(--muted)}
    .bar .fill{width:100%;border-radius:6px 6px 0 0;background:linear-gradient(180deg,var(--accent),#60a5fa);display:block}
    .controls{display:flex;gap:8px;align-items:center;margin-top:8px}
    select,input[type=radio]{padding:8px;border-radius:8px;border:1px solid #e6e9ef}
    footer{grid-column:1/-1;margin-top:12px;color:var(--muted);font-size:13px}
    @media (max-width:980px){.container{grid-template-columns:1fr}.wide{grid-column:1}.container {padding:0 12px}}
  </style>
</head>
<body>
  <header>
    <div class="brand">
      <div class="logo">WF</div>
      <div>
        <h1>Wi-Fi Optimizer</h1>
        <div class="meta">채널 혼잡도 분석 및 최적 채널 추천</div>
      </div>
    </div>
    <div class="top-actions">
      <button class="icon" title="설정">⚙️</button>
      <button class="icon" title="도움말">❓</button>
    </div>
  </header>

  <main class="container">
    <section class="card main-card">
      <div class="ssid-row">
        <div>
          <div class="ssid" id="ssid">SSID: -</div>
          <div class="meta" id="bssid">연결 중: -</div>
        </div>
        <div class="meta">스캔 간격: <span id="scan-interval">수동</span></div>
      </div>

      <div class="channel-row">
        <div>
          <div class="channel-big" id="current-channel">-</div>
          <div class="meta">현재 채널</div>
        </div>

        <div class="signal">
          <div class="progress-wrap">
            <div class="progress" aria-hidden="true"><i id="congestion-fill" style="width:0%"></i></div>
            <div class="meta" style="margin-top:6px">혼잡도: <strong id="congestion-percent">-</strong></div>
          </div>
          <div id="status-tag" class="status-tag" style="background:var(--good);color:white">-</div>
        </div>

        <div style="margin-left:auto;text-align:right">
          <div class="meta">추천 채널</div>
          <div class="rec-channel" id="recommended">-</div>
        </div>
      </div>

      <div class="recommend">
        <div class="rec-box">
          <div class="meta">이 채널로 변경하면 예상 혼잡도: <strong id="predicted">-</strong></div>
        </div>
        <div>
          <button class="apply-btn" id="apply-btn">채널 적용 (시뮬레이션)</button>
        </div>
      </div>

      <div style="display:flex;gap:12px;margin-top:6px;align-items:center">
        <button id="rescan" class="apply-btn" style="background:#111;color:#fff;padding:8px 12px">다시 스캔</button>
        <div class="meta">스캔 시간: <span id="last-scan">-</span></div>
      </div>
    </section>

    <aside class="summary">
      <div class="card mini">
        <div class="row"><div>주파수</div><div id="band">-</div></div>
        <div class="row"><div>연결 기기 수(예시)</div><div id="clients">-</div></div>
        <div class="row"><div>업로드/다운로드 속도(예시)</div><div id="speed">-</div></div>
      </div>

      <div class="card mini">
        <div class="meta">알림</div>
        <div>혼잡도 > 70% 일 때 푸시 알림</div>
      </div>
    </aside>

    <section class="card wide">
      <div class="chart">
        <div style="display:flex;justify-content:space-between;align-items:center">
          <div style="font-weight:700">채널 분석</div>
          <div class="controls">
            <label class="meta">대역</label>
            <select id="band-select">
              <option>2.4 GHz</option>
              <option>5 GHz</option>
            </select>
            <label class="meta">보기</label>
            <select id="view-select">
              <option>혼잡도(%)</option>
              <option>기기 수</option>
            </select>
          </div>
        </div>

        <div class="bars" id="bars"></div>

        <div style="display:flex;justify-content:space-between;align-items:center;margin-top:6px">
          <div class="meta">가장 낮은 혼잡도 채널이 추천됩니다</div>
          <div><small class="meta">참고: 실제 라우터 변경은 관리자 페이지에서 진행하세요.</small></div>
        </div>
      </div>
    </section>

    <footer>프로토타입 — HTML/CSS/JS + 실제 스캔 연동</footer>
  </main>

  <script>
    const barsEl = document.getElementById('bars');
    const recommendedEl = document.getElementById('recommended');
    const predictedEl = document.getElementById('predicted');
    const congestionFill = document.getElementById('congestion-fill');
    const congestionPercent = document.getElementById('congestion-percent');
    const statusTag = document.getElementById('status-tag');
    const currentChannelEl = document.getElementById('current-channel');
    const lastScanEl = document.getElementById('last-scan');
    const ssidEl = document.getElementById('ssid');
    const bssidEl = document.getElementById('bssid');

    function renderBars(data){
      barsEl.innerHTML = '';
      if(!data || data.length===0){
        barsEl.innerHTML = '<div class="meta">스캔 결과가 없습니다.</div>';
        recommendedEl.textContent = '-';
        predictedEl.textContent = '-';
        congestionPercent.textContent = '-';
        congestionFill.style.width = '0%';
        currentChannelEl.textContent = '-';
        statusTag.textContent = '-';
        return;
      }

      // data: { channel_usage: { "1": val, ... }, recommended: int, networks: [...] }
      const usage = data.channel_usage || {};
      const channels = Object.keys(usage).map(k=>parseInt(k)).sort((a,b)=>a-b);
      const items = channels.map(ch => ({ channel: ch, value: usage[ch] }));

      // Render bars
      items.forEach(d=>{
        const bar = document.createElement('div');
        bar.className = 'bar';
        const label = document.createElement('span'); label.textContent = d.channel;
        const fill = document.createElement('div'); fill.className = 'fill';
        // normalize height for visibility (if values can be low/high)
        const maxVal = Math.max(...items.map(x=>x.value), 1);
        const pct = Math.round((d.value / maxVal) * 100);
        fill.style.height = pct + '%';
        bar.appendChild(label);
        bar.appendChild(fill);
        if(d.channel === data.recommended) {
          fill.style.background = 'linear-gradient(180deg,var(--good),#6ee7b7)';
          bar.style.boxShadow = '0 6px 14px rgba(16,185,129,0.12)';
        }
        barsEl.appendChild(bar);
      });

      // Update summary
      recommendedEl.textContent = data.recommended ?? '-';
      predictedEl.textContent = data.predicted ?? '-';
      const current = data.networks && data.networks.length ? data.networks[0] : null;
      if(current){
        ssidEl.textContent = 'SSID: ' + current.ssid;
        currentChannelEl.textContent = current.channel;
        bssidEl.textContent = '연결 중 (예시)'; // 실제 BSSID 추출 로직 필요시 서버에서 제공
      }
      // congestion percent: simple average of usage normalized
      const total = Object.values(usage).reduce((a,b)=>a+b,0);
      const avg = total ? Math.round( (Object.values(usage).reduce((s,v)=>s+v,0) / (Object.keys(usage).length || 1)) ) : 0;
      congestionPercent.textContent = avg + '%';
      congestionFill.style.width = Math.min(100, avg) + '%';
      if(avg < 40){ statusTag.textContent='양호'; statusTag.style.background='var(--good)'; }
      else if(avg < 70){ statusTag.textContent='보통'; statusTag.style.background='var(--warn)'; }
      else { statusTag.textContent='혼잡'; statusTag.style.background='var(--bad)'; }
      lastScanEl.textContent = new Date().toLocaleTimeString();
    }

    async function fetchScan(){
      try{
        const res = await fetch('/scan');
        if(!res.ok){
          const txt = await res.text();
          console.error('scan error', res.status, txt);
          renderBars(null);
          return;
        }
        const data = await res.json();
        renderBars(data);
      }catch(e){
        console.error(e);
        renderBars(null);
      }
    }

    document.getElementById('rescan').addEventListener('click', fetchScan);

    // 초기 로드
    fetchScan();
  </script>
</body>
</html>
"""

# ------------------ Wi-Fi 스캔 로직 ------------------
def scan_wifi_windows():
    """
    Windows에서 netsh 명령어로 주변 Wi-Fi 스캔.
    결과로 (ssid, channel, signal) 튜플 리스트 반환.
    """
    # netsh 명령: mode=bssid 로 AP별 정보 포함
    cmd = f'netsh wlan show networks interface="{INTERFACE_NAME}" mode=bssid'
    try:
        # shell=True 사용 (윈도우에서 편리). 보안에 주의하세요.
        result = subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL)
        # 한글 윈도우에서 cp949로 디코딩
        text = result.decode("cp949", errors="ignore")
    except subprocess.CalledProcessError as e:
        # 명령 실패 시 빈 리스트 반환
        return []

    networks = []
    ssid = None
    chan = None
    for line in text.splitlines():
        line = line.strip()
        # SSID: <이름>
        if line.lower().startswith("ssid"):
            # 'SSID 1 : name' 혹은 'SSID : name' 등 다양한 포맷이 있음
            parts = line.split(":", 1)
            if len(parts) > 1:
                ssid = parts[1].strip()
        # 채널: Channel: <num> 또는 '채널 : <num>'
        elif line.lower().startswith("channel") or "채널" in line:
            parts = line.split(":", 1)
            if len(parts) > 1:
                try:
                    chan = int(parts[1].strip())
                except:
                    chan = None
        # 신호: Signal : 76% 또는 '신호 : 76%'
        elif line.lower().startswith("signal") or "신호" in line:
            parts = line.split(":", 1)
            if len(parts) > 1:
                try:
                    sig = int(parts[1].replace("%","").strip())
                except:
                    sig = 0
                # 유의: netsh 출력 구조에 따라 SSID/Channel/Signal이 한 덩어리로 나오지 않을 수 있음.
                if ssid is not None and chan is not None:
                    networks.append((ssid, chan, sig))
                    ssid, chan = None, None

    return networks

def recommend_channel(networks):
    """
    networks: [(ssid, channel, signal), ...]
    반환: (best_channel, counter_dict)
    """
    if not networks:
        return None, {}

    # 채널별 AP 수 집계
    channels = [n[1] for n in networks if isinstance(n[1], int)]
    counter = Counter(channels)

    # 후보 채널(간섭 적은 채널 위주)
    candidate_channels_24ghz = [1, 6, 11]
    candidate_channels_5ghz = [36, 40, 44, 48, 149, 153, 157, 161]
    candidates = candidate_channels_24ghz + candidate_channels_5ghz

    # 후보 중 카운트가 가장 적은 채널을 추천
    best = min(candidates, key=lambda c: counter.get(c, 0))

    return best, dict(counter)

# ------------------ Flask 서버 ------------------
app = Flask(__name__)

@app.route("/")
def index():
    return render_template_string(HTML)

@app.route("/scan")
def api_scan():
    nets = scan_wifi_windows()
    if not nets:
        return jsonify({"error": "주변 Wi-Fi를 찾지 못했습니다.", "networks": [], "channel_usage": {}, "recommended": None}), 200

    best, counter = recommend_channel(nets)
    # predicted: 간단 예측값(추천 채널의 예상 혼잡도) — (채널 AP수 / maxAP) * 100 으로 정규화
    max_count = max(counter.values()) if counter else 1
    predicted_pct = None
    if best is not None:
        predicted_pct = f"{int((counter.get(best,0) / max_count)*100)}%"

    # JSON 반환
    return jsonify({
        "networks": [{"ssid": s, "channel": c, "signal": sig} for (s,c,sig) in nets],
        "channel_usage": {str(k): v for k, v in counter.items()},
        "recommended": int(best) if best is not None else None,
        "predicted": predicted_pct
    })

if __name__ == "__main__":
    print("Starting Wi-Fi Scanner server...")
    print(f"Interface name: {INTERFACE_NAME}")
    app.run(host=HOST, port=PORT, debug=True)
