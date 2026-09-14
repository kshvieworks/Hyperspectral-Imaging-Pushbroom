import numpy as np
import matplotlib.pyplot as plt
from matplotlib.widgets import Slider

data = np.load("test_cube.npy")
n_frames = data.shape[0]
vmin = np.percentile(data, 1)
vmax = np.percentile(data, 99)

fig, ax = plt.subplots()
plt.subplots_adjust(bottom=0.2)

im = ax.imshow(data[0], cmap='gray', vmin=vmin, vmax=vmax)
ax.set_title("Frame 0")

slider_ax = plt.axes([0.2, 0.05, 0.6, 0.03])

slider = Slider(slider_ax, "Frame", 0, n_frames -1, valinit=0, valstep=1)

def update(value):
    index = int(slider.val)
    im.set_data(data[index])

    ax.set_title(f"Frame {index}")

    fig.canvas.draw_idle()
slider.on_changed(update)
plt.show()
