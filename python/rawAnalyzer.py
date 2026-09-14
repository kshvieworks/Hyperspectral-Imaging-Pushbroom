import numpy as np
import matplotlib.pyplot as plt
from matplotlib.widgets import Slider
import glob
import os

# ==========================================
# [설정 필요] RAW 파일의 속성을 지정해주세요
# ==========================================
WIDTH = 256  # 이미지 가로 픽셀 수 (수정 필요)
HEIGHT = 256  # 이미지 세로 픽셀 수 (수정 필요)
DTYPE = np.uint16  # 데이터 타입 (예: np.uint8, np.uint16, np.float32 등)
FILE_DIR = "C:\\Users\\2021600\\Desktop\\새 폴더 (9)\\손"  # RAW 파일들이 저장된 폴더 경로
# ==========================================

# 1. 폴더 내의 .raw 파일 목록을 불러오고 이름순으로 정렬합니다. (최대 100개)
file_paths = sorted(glob.glob(os.path.join(FILE_DIR, "*.raw")))[:100]

if not file_paths:
    raise ValueError(f"'{FILE_DIR}' 경로에 RAW 파일이 없습니다. 경로를 확인해주세요.")

# 2. RAW 파일들을 읽어서 리스트에 담은 뒤 3D numpy array로 변환합니다.
data_list = []
for path in file_paths:
    # 파일에서 1차원 배열 형태로 데이터를 읽어옴
    img_1d = np.fromfile(path, dtype=DTYPE)

    # 1차원 배열을 2차원 이미지(HEIGHT x WIDTH)로 변환
    # (주의: 파일 크기와 HEIGHT * WIDTH * 데이터바이트 수가 일치해야 합니다)
    img_2d = img_1d.reshape((HEIGHT, WIDTH))
    data_list.append(img_2d)

# (100, HEIGHT, WIDTH) 형태의 3D 배열 생성
data = np.array(data_list)

# 3. 시각화 및 슬라이더 설정 (기존 로직과 동일)
n_frames = data.shape[0]
vmin = np.percentile(data, 1)
vmax = np.percentile(data, 99)

fig, ax = plt.subplots()
plt.subplots_adjust(bottom=0.2)

# 첫 번째 프레임 출력
im = ax.imshow(data[0], cmap='gray', vmin=vmin, vmax=vmax)
ax.set_title(f"Frame 0 : {os.path.basename(file_paths[0])}")

slider_ax = plt.axes([0.2, 0.05, 0.6, 0.03])
slider = Slider(slider_ax, "Frame", 0, n_frames - 1, valinit=0, valstep=1)


def update(value):
    index = int(slider.val)
    im.set_data(data[index])
    # 현재 보여지는 파일 이름을 타이틀에 함께 출력하여 확인하기 쉽게 합니다.
    filename = os.path.basename(file_paths[index])
    ax.set_title(f"Frame {index} : {filename}")
    fig.canvas.draw_idle()


slider.on_changed(update)
plt.show()