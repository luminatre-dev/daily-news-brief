import anthropic
import json
import os
import xml.etree.ElementTree as ET
import requests
from datetime import datetime
import pytz

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

sgt = pytz.timezone('Asia/Singapore')
today = datetime.now(sgt).strftime('%Y년 %m월 %d일')

# FT RSS 피드에서 뉴스 가져오기
def fetch_ft_news(max_items=3):
    ft_feeds = [
        ("https://www.ft.com/rss/home", "FT"),
        ("https://www.ft.com/markets?format=rss", "FT Markets"),
    ]
    items = []
    for url, source in ft_feeds:
        try:
            res = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
            root = ET.fromstring(res.content)
            for item in root.findall(".//item")[:max_items]:
                title = item.findtext("title", "").strip()
                link = item.findtext("link", "").strip()
                desc = item.findtext("description", "").strip()
                if title and link:
                    items.append({
                        "title": title,
                        "summary": desc[:100] + "..." if len(desc) > 100 else desc,
                        "source": source,
                        "url": link,
                        "category": "global",
                        "categoryLabel": "글로벌",
                        "time": "FT"
                    })
            if items:
                break
        except Exception as e:
            print(f"FT RSS 오류: {e}")
    return items[:max_items]

# Claude로 뉴스 수집
response = client.messages.create(
    model="claude-sonnet-4-20250514",
    max_tokens=1500,
    tools=[{"type": "web_search_20250305", "name": "web_search"}],
    system="""You are a news aggregator. Return ONLY a JSON array with exactly 7 news items.
Each item: { title, summary (1 sentence in Korean, max 30 words), source, url, category (sg|global|alt), categoryLabel (싱가포르|글로벌|대체투자), time }
Find:
- 2 Singapore local news
- 2 Global news
- 3 Korean alternative investment & PE/VC related news covering: 대체투자, 사모펀드(PEF), 바이아웃, 스타트업 투자, VC 딜, PE 딜, M&A, 인수합병, 업계동향, 정부/금융당국 정책, 펀드 결성, LP/GP 동향 etc. Search broadly across dealsite.co.kr, etnews.com, investchosun.com, hankyung.com, mk.co.kr, sedaily.com, bloter.net, thevc.kr, platum.kr, venturesquare.net or any other relevant Korean news sites
Return ONLY valid JSON array. No markdown, no explanation.""",
    messages=[{"role": "user", "content": f"{today} 최신 뉴스 7개를 JSON 배열로 반환해주세요."}]
)

text = next((b.text for b in response.content if b.type == "text"), "[]")
text = text.strip().replace("```json", "").replace("```", "").strip()
start, end = text.find('['), text.rfind(']')
news_list = json.loads(text[start:end+1]) if start != -1 else []

# FT 뉴스 추가
ft_news = fetch_ft_news(max_items=3)
news_list = news_list + ft_news

output = {
    "updated_at": datetime.now(sgt).isoformat(),
    "updated_at_display": datetime.now(sgt).strftime('%Y-%m-%d %H:%M SGT'),
    "news": news_list
}

with open("news_data.json", "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

print(f"✅ 총 {len(news_list)}개 뉴스 저장 완료 (Claude {len(news_list)-len(ft_news)}개 + FT {len(ft_news)}개)")
