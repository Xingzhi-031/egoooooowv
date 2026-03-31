import os
import numpy as np
import matplotlib.pyplot as plt

bin_path = r"C:\ti\mmwave_studio_02_01_01_00\mmWaveStudio\PostProc\ods_dca_clean_Raw_0.bin"
raw = np.fromfile(bin_path, dtype=np.int16)

print("Original int16 count:", raw.size)

# ===== 参数 =====
num_adc_samples = 256
num_rx = 4
num_tx = 3
num_loops = 32
chirps_per_frame = num_tx * num_loops   # 96

# ===== 先裁掉尾巴，让它能按 chirp 对齐 =====
trim_real = raw.size % (num_adc_samples * num_rx)   # % 1024
raw_trim = raw[:raw.size - trim_real]

print("Tail removed:", trim_real)
print("Trimmed int16 count:", raw_trim.size)

# =========================================================
# A. REAL-ONLY 假设
# =========================================================
print("\n===== REAL-ONLY TEST =====")
int16_per_chirp_real = num_adc_samples * num_rx      # 1024
usable_real = (raw_trim.size // int16_per_chirp_real) * int16_per_chirp_real
real_data = raw_trim[:usable_real].reshape(-1, num_adc_samples, num_rx)

print("Real-only shape:", real_data.shape)  # [chirps, samples, rx]

sig_real = real_data[0, :, 0].astype(np.float32)

window = np.hanning(num_adc_samples)
fft_real = np.fft.fft(sig_real * window)
fft_real_mag = np.abs(fft_real[:num_adc_samples // 2])

plt.figure(figsize=(8,4))
plt.plot(sig_real)
plt.title("Real-only assumption: chirp0, RX0 waveform")
plt.xlabel("Sample index")
plt.ylabel("Amplitude")
plt.tight_layout()

plt.figure(figsize=(8,4))
plt.plot(fft_real_mag)
plt.title("Real-only assumption: Range FFT (chirp0, RX0)")
plt.xlabel("Range bin")
plt.ylabel("Magnitude")
plt.tight_layout()

# =========================================================
# B. COMPLEX-IQ 假设
# =========================================================
print("\n===== COMPLEX-IQ TEST =====")
if raw_trim.size % 2 != 0:
    print("Trimmed int16 count is odd, cannot form IQ pairs.")
else:
    iq = raw_trim[0::2].astype(np.float32) + 1j * raw_trim[1::2].astype(np.float32)

    complex_per_chirp = num_adc_samples * num_rx   # 1024 complex
    usable_cplx = (iq.size // complex_per_chirp) * complex_per_chirp
    iq_data = iq[:usable_cplx].reshape(-1, num_adc_samples, num_rx)

    print("Complex-IQ shape:", iq_data.shape)  # [chirps, samples, rx]

    sig_cplx = iq_data[0, :, 0]

    fft_cplx = np.fft.fft(sig_cplx * window)
    fft_cplx_mag = np.abs(fft_cplx[:num_adc_samples // 2])

    plt.figure(figsize=(8,4))
    plt.plot(np.real(sig_cplx), label="I")
    plt.plot(np.imag(sig_cplx), label="Q")
    plt.title("Complex-IQ assumption: chirp0, RX0 waveform")
    plt.xlabel("Sample index")
    plt.ylabel("Amplitude")
    plt.legend()
    plt.tight_layout()

    plt.figure(figsize=(8,4))
    plt.plot(fft_cplx_mag)
    plt.title("Complex-IQ assumption: Range FFT (chirp0, RX0)")
    plt.xlabel("Range bin")
    plt.ylabel("Magnitude")
    plt.tight_layout()

plt.show()