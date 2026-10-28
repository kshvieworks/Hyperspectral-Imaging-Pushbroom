import numpy as np
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation, FFMpegWriter
import glob
import os

# ==========================================
# RAW 설정
# ==========================================
WIDTH = 500
HEIGHT = 500
DTYPE = np.uint16
FILE_DIR = r"C:\Users\2021600\Desktop\20260928\Time Response @ 6V, PWM 20"

# ==========================================
# RAW 파일 불러오기
# ==========================================
file_paths = sorted(glob.glob(os.path.join(FILE_DIR, "*.raw")))

if not file_paths:
    raise ValueError(f"'{FILE_DIR}' 경로에 RAW 파일이 없습니다.")

data_list = []

for path in file_paths:
    img_1d = np.fromfile(path, dtype=DTYPE)

    expected_size = WIDTH * HEIGHT

    if img_1d.size != expected_size:
        print(
            f"Warning: {os.path.basename(path)} "
            f"size={img_1d.size}, expected={expected_size}"
        )
        continue

    img_2d = img_1d.reshape((HEIGHT, WIDTH))
    data_list.append(img_2d)

data = np.array(data_list)

n_frames = data.shape[0]

# ==========================================
# 영상 표시 범위
# ==========================================
vmin = np.percentile(data, 1)
vmax = np.percentile(data, 99)

# ==========================================
# Figure
# ==========================================
fig, ax = plt.subplots(figsize=(6, 6))

im = ax.imshow(
    data[0],
    cmap="gray",
    vmin=vmin,
    vmax=vmax
)

title = ax.set_title(
    f"Frame 0 : {os.path.basename(file_paths[0])}"
)

ax.axis("off")


# ==========================================
# Animation update
# ==========================================
def update(frame):
    im.set_data(data[frame])

    title.set_text(
        f"Frame {frame} : {os.path.basename(file_paths[frame])}"
    )

    return im, title


ani = FuncAnimation(
    fig,
    update,
    frames=n_frames,
    interval=50,   # ms, 100 ms = 10 fps
    blit=True
)

# ==========================================
# MP4 저장
# ==========================================
output_path = os.path.join(FILE_DIR, "RAW_sequence.mp4")

writer = FFMpegWriter(
    fps=40,
    metadata={"artist": "RAW Viewer"},
    bitrate=5000
)

ani.save(output_path, writer=writer)

print(f"Video saved: {output_path}")

plt.show()