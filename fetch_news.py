import anthropic
import json
import os
from datetime import datetime
import pytz

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

sgt = pytz.timezone('Asia/Singapore')
today = datetime.now(sgt).strftime('%Y년 %m월 %d일')

response = client.messages.create(
    model="claude-sonnet-4-20250514",
    max_tokens=1500,
    tools=[{"type": "web_search_20250305", "name": "web_search"}],
    system="""You are a news aggregator. Return ONLY a JSON array with exactly 5 news items.
Each item: { title, summary (1 sentence in Korean, max 30 words), source, url, category (sg|global|alt), categoryLabel (싱가포르|글로벌|대체투자), time }
Find:
- 2 Singapore local news
- 2 Global news
- 4 Korean alternative investment & PE/VC related news
- 3 Korean alternative investment & PE/VC related news covering any of the following topics: 대체투자, 사모펀드(PEF), 바이아웃, 스타트업 투자, VC 딜, PE 딜, M&A, 인수합병, 업계동향, 정부/금융당국 정책 (FSC, FSS, KVCA 등), 펀드 결성, LP/GP 동향, 블라인드펀드, 세컨더리, 크레딧펀드 등. Search broadly across any Korean financial/business news sources including dealsite.co.kr, etnews.com, investchosun.com, hankyung.com, mk.co.kr, sedaily.com, bloter.net, thevc.kr, platum.kr, venturesquare.net or any other relevant Korean news sites
Return ONLY valid JSON array. No markdown, no explanation.""",
    messages=[{"role": "user", "content": f"{today} news_data.json 파일에 8개를 JSON 배열로 반환해주세요."}]
)

text = next((b.text for b in response.content if b.type == "text"), "[]")
text = text.strip().replace("```json", "").replace("```", "").strip()
start, end = text.find('['), text.rfind(']')
news_list = json.loads(text[start:end+1]) if start != -1 else []

output = {
    "updated_at": datetime.now(sgt).isoformat(),
    "updated_at_display": datetime.now(sgt).strftime('%Y-%m-%d %H:%M SGT'),
    "news": news_list
}

with open("news_data.json", "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

print(f"✅ {len(news_list)}개 뉴스 저장 완료")
