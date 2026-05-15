import streamlit as st
import pandas as pd
import folium
from folium import Popup
from streamlit_folium import st_folium
import requests
import urllib3
import io  # 📌 엑셀 다운로드를 위해 추가된 라이브러리

# 🛡️ 보안 설정
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 🔑 카카오 API 설정 (본인 키를 꼭 넣어주세요!)
KAKAO_API_KEY = "14298707d84729013520ca6d9c214656"
CLEAN_KEY = KAKAO_API_KEY.encode('ascii', 'ignore').decode('ascii').strip()

def get_lat_lng(address):
    url_addr = "https://dapi.kakao.com/v2/local/search/address.json"
    url_keyword = "https://dapi.kakao.com/v2/local/search/keyword.json"
    headers = {"Authorization": f"KakaoAK {CLEAN_KEY}"}
    params = {"query": address}
    try:
        response = requests.get(url_addr, headers=headers, params=params, verify=False)
        result = response.json()
        if result.get('documents'):
            return float(result['documents'][0]['y']), float(result['documents'][0]['x'])
        response_kw = requests.get(url_keyword, headers=headers, params=params, verify=False)
        result_kw = response_kw.json()
        if result_kw.get('documents'):
            return float(result_kw['documents'][0]['y']), float(result_kw['documents'][0]['x'])
        return None, None
    except: return None, None

st.set_page_config(page_title="울산 중구의회 민원 관리 대시보드", layout="wide")

# 1. 데이터 불러오기
try:
    data = pd.read_excel("민원데이터.xlsx")
    if '접수일자' in data.columns:
        data['접수일자_분석용'] = pd.to_datetime(data['접수일자'], errors='coerce')
        data['년월'] = data['접수일자_분석용'].dt.strftime('%Y-%m')
        data['접수일자'] = data['접수일자_분석용'].dt.strftime('%Y-%m-%d')
except:
    st.error("데이터 파일을 확인해주세요.")
    st.stop()

# 2. 좌표 자동 저장
new_coords = False
for i, row in data.iterrows():
    if pd.isna(row.get('위도')) or pd.isna(row.get('경도')):
        lat, lng = get_lat_lng(str(row['민원지 주소']))
        if lat and lng:
            data.at[i, '위도'], data.at[i, '경도'] = lat, lng
            new_coords = True
if new_coords:
    try: data.drop(columns=['접수일자_분석용', '년월'], errors='ignore').to_excel("민원데이터.xlsx", index=False)
    except: pass

# =====================================================================
# 🔗 접속 모드 분기 (관리자 모드 vs 의원 전용 모드)
# =====================================================================
query_params = st.query_params
target_name = query_params.get("id")

if target_name:
    # 🔒 특정 의원 모드 (읽기 전용, 본인 데이터만 표시하되 월/상태 필터 제공)
    st.title(f"🏛️ {target_name} 의원님 민원 현황")
    st.info(f"본 화면은 {target_name} 의원님 접수 민원 조회 페이지입니다.")
    
    # 1차 필터링: 해당 의원의 데이터만 가져오기
    base_data = data[data['접수자'] == target_name].copy()
    
    # 의원 전용 사이드바 필터 추가
    st.sidebar.header(f"🔍 {target_name} 의원님 전용 검색")
    
    month_list = sorted(base_data['년월'].dropna().unique().tolist())
    selected_months = st.sidebar.multiselect("📅 월별 선택", month_list, default=month_list)
    
    status_list = sorted(base_data['처리상태'].dropna().astype(str).unique().tolist())
    selected_status = st.sidebar.multiselect("📌 처리상태 선택", status_list, default=status_list)
    
    # 2차 필터링: 사용자가 선택한 월/상태 적용
    filtered_data = base_data.copy()
    if selected_months: 
        filtered_data = filtered_data[filtered_data['년월'].isin(selected_months)]
    if selected_status: 
        filtered_data = filtered_data[filtered_data['처리상태'].astype(str).isin(selected_status)]

else:
    # 🔓 관리자 모드 (전체 필터 제공)
    st.title("🗺️ 울산 중구의회 민원 관리 대시보드(관리자)")
    st.sidebar.header("🔍 전체 민원 검색 필터")

    month_list = sorted(data['년월'].dropna().unique().tolist())
    selected_months = st.sidebar.multiselect("📅 월별 선택", month_list, default=month_list)

    member_list = sorted(data['접수자'].dropna().unique().tolist())
    selected_members = st.sidebar.multiselect("👤 접수자 선택", member_list, default=member_list)

    status_list = sorted(data['처리상태'].dropna().astype(str).unique().tolist())
    selected_status = st.sidebar.multiselect("📌 처리상태 선택", status_list, default=status_list)

    filtered_data = data.copy()
    if selected_months: filtered_data = filtered_data[filtered_data['년월'].isin(selected_months)]
    if selected_members: filtered_data = filtered_data[filtered_data['접수자'].isin(selected_members)]
    if selected_status: filtered_data = filtered_data[filtered_data['처리상태'].astype(str).isin(selected_status)]

# 지도에 표시할 데이터 (위경도 있는 것만)
valid_data = filtered_data.dropna(subset=['위도', '경도'])

# =====================================================================
# 🖥️ 메인 화면
# =====================================================================
col1, col2 = st.columns([2, 1])

with col1:
    st.subheader(f"📍 민원 발생 지도 (조회: {len(valid_data)}건)")
    m = folium.Map(location=[35.5696, 129.3327], zoom_start=14)
    
    # 지도 범례
    legend_html = '''
<div style="position: fixed; bottom: 50px; left: 50px; width: 140px; height: 140px; 
        border:2px solid grey; z-index:9999; font-size:14px; background-color: rgba(255, 255, 255, 0.8); 
        padding: 10px; border-radius: 5px; box-shadow: 3px 3px 5px rgba(0,0,0,0.2);">
        <b>📍민원 처리 상태</b><br>
        <span style="color:blue;">●</span> 완료<br>
        <span style="color:purple;">●</span> 장기과제<br>
        <span style="color:red;">●</span> 조치불가<br>
        <span style="color:orange;">●</span> 진행/검토<br>
        <span style="color:black;">●</span> 보류
    </div>
    '''
    m.get_root().html.add_child(folium.Element(legend_html))
    
    for idx, row in valid_data.iterrows():
        s = str(row['처리상태']).strip()
        
        # 색상 조건
        if '완료' in s: p_color = 'blue'
        elif '장기' in s: p_color = 'purple'
        elif '불가' in s: p_color = 'red'
        elif '진행' in s or '검토' in s: p_color = 'orange'
        elif '보류' in s: p_color = 'black'
        else: p_color = 'gray'
        
        tooltip_text = f"[{row['접수일자']}] {row['접수자']} - {row['처리상태']}"
        popup_content = Popup(str(row['민원내용']), max_width=400)
        
        folium.Marker(
            location=[row['위도'], row['경도']],
            popup=popup_content,
            tooltip=tooltip_text,
            icon=folium.Icon(color=p_color)
        ).add_to(m)
    
    st_folium(m, width=800, height=600)

with col2:
    st.subheader("📊 민원 내역")
    ordered_cols = ['민원번호', '접수일자', '민원지 주소', '민원내용', '접수자', '처리상태']
    
    # 📥 엑셀 다운로드 버튼 (메모리에 엑셀 파일 생성)
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
        # 화면에 필터링된 현재 상태의 데이터만 엑셀로 변환
        filtered_data[ordered_cols].to_excel(writer, index=False, sheet_name='필터링_데이터')
    
    st.download_button(
        label="📥 조회된 데이터 엑셀 다운로드",
        data=buffer.getvalue(),
        file_name="울산중구의회_민원데이터_추출.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True
    )
    
    st.dataframe(filtered_data[ordered_cols], height=600)
