import tkinter as tk
from tkinter import ttk, messagebox
import serial
import serial.tools.list_ports
import threading
import numpy as np
import time

serial_device = None
abort_flag = False
pause_flag = False
pause_event = threading.Event()

def list_serial_ports():
    return [port.device for port in serial.tools.list_ports.comports()]

def make_phase_list(p1, p2, N):
    y_val = np.linspace(-1, 1, N)
    asin_y = np.arcsin(y_val)
    p1_rad = np.deg2rad(p1)
    p2_rad = np.deg2rad(p2)
    phase_list = 10 * (np.round(np.rad2deg(p1_rad + ((asin_y + np.pi / 2) / np.pi) * (p2_rad - p1_rad)))).astype(int)
    return phase_list

def mod_phase(phase_val):
    cmd = f":w31={phase_val}.\n"
    try:
        serial_device.write(cmd.encode())
    except Exception as e:
        print("Error setting phase:", e)

def initialize_dds():
    try:
        cmds = [
            ":w20=0,0.\n",
            ":w22=2.\n",
            ":w29=5000.\n",
            ":w24=10000000,0.\n",
            ":w28=1150.\n",
            ":w26=3000.\n",
        ]
        for cmd in cmds:
            serial_device.write(cmd.encode())
            time.sleep(0.1)
        print("DDS initialized")
    except Exception as e:
        print("Initialization error:", e)

def set_frequency(freq):
    try:
        serial_device.write(f":w23={freq},0.\n".encode())
        time.sleep(0.1)
        serial_device.write(f":w24={freq},0.\n".encode())
        time.sleep(0.1)
    except Exception as e:
        print("Error setting frequency:", e)

def start_phase_oscillation(com_port, baud_rate, phase1_deg, phase2_deg, drive_voltage, num_steps, delay, freq):
    global serial_device, abort_flag, pause_flag, pause_event
    abort_flag = False
    pause_flag = False

    try:
        serial_device = serial.Serial(com_port, baud_rate, timeout=1)
        print(f"Connected to {com_port}")
    except Exception as e:
        messagebox.showerror("Connection Error", str(e))
        return

    initialize_dds()
    set_frequency(freq)

    try:
        serial_device.write(":w25=0000.\n".encode())
        time.sleep(0.1)
        serial_device.write(":w21=0.\n".encode())           # Sine wave
        time.sleep(0.1)
        serial_device.write(":w20=1,1.\n".encode())         # Turn on

        for i in range(drive_voltage + 1):
            while pause_flag:
                pause_event.wait()
            if abort_flag:
                raise InterruptedError("Aborted during voltage ramp")
            value = i * 1000
            serial_device.write(f":w25={value:04d}.\n".encode())
            time.sleep(1)

        phase_values = make_phase_list(phase1_deg, phase2_deg, num_steps)

        while not abort_flag:
            for p in phase_values:
                while pause_flag:
                    pause_event.wait()
                if abort_flag:
                    raise InterruptedError("Aborted during forward sweep")
                mod_phase(p)
                time.sleep(delay)
            for p in reversed(phase_values):
                while pause_flag:
                    pause_event.wait()
                if abort_flag:
                    raise InterruptedError("Aborted during backward sweep")
                mod_phase(p)
                time.sleep(delay)

    except InterruptedError as e:
        print(str(e))
    finally:
        serial_device.close()
        print("Serial closed")

def start_thread():
    try:
        com_port = com_var.get()
        baud_rate = int(baud_var.get())
        phase1 = float(phase1_var.get())
        phase2 = float(phase2_var.get())
        drive_voltage = int(voltage_var.get())
        steps = int(steps_var.get())
        delay = float(delay_var.get())
        freq_kHz = float(freq_var.get())
        freq = int(freq_kHz * 1000)

        t = threading.Thread(target=start_phase_oscillation, args=(
            com_port, baud_rate, phase1, phase2, drive_voltage, steps, delay, freq
        ))
        t.start()
    except ValueError as e:
        messagebox.showerror("Input Error", str(e))

def abort():
    global abort_flag
    abort_flag = True

def pause_resume():
    global pause_flag, pause_event
    pause_flag = not pause_flag
    if not pause_flag:
        pause_event.set()
    else:
        pause_event.clear()
    pause_button.config(text="Resume" if pause_flag else "Pause")

# ----- GUI SETUP -----
root = tk.Tk()
root.title("MP Control")
root.geometry("400x450")

# COM port
tk.Label(root, text="COM Port").pack()
com_var = tk.StringVar()
com_dropdown = ttk.Combobox(root, textvariable=com_var, values=list_serial_ports())
com_dropdown.pack()

# Baud rate
tk.Label(root, text="Baud Rate").pack()
baud_var = tk.StringVar(value="115200")
tk.Entry(root, textvariable=baud_var).pack()

# Phase 1
tk.Label(root, text="Phase 1 (°)").pack()
phase1_var = tk.StringVar(value="58")
tk.Entry(root, textvariable=phase1_var).pack()

# Phase 2
tk.Label(root, text="Phase 2 (°)").pack()
phase2_var = tk.StringVar(value="238")
tk.Entry(root, textvariable=phase2_var).pack()

# Drive Voltage
tk.Label(root, text="Drive Voltage (0–12)").pack()
voltage_var = tk.StringVar(value="12")
tk.Entry(root, textvariable=voltage_var).pack()

# Steps
tk.Label(root, text="Number of Steps").pack()
steps_var = tk.StringVar(value="11")
tk.Entry(root, textvariable=steps_var).pack()

# Delay
tk.Label(root, text="Delay (sec)").pack()
delay_var = tk.StringVar(value="5e-6")
tk.Entry(root, textvariable=delay_var).pack()

# Frequency
tk.Label(root, text="Frequency (kHz)").pack()
freq_var = tk.StringVar(value="10")
tk.Entry(root, textvariable=freq_var).pack()

# Buttons
button_frame = tk.Frame(root)
button_frame.pack(pady=10)
tk.Button(button_frame, text="Start", command=start_thread, bg="green", fg="white").pack(side=tk.LEFT, padx=5)
pause_button = tk.Button(button_frame, text="Pause", command=pause_resume)
pause_button.pack(side=tk.LEFT, padx=5)
tk.Button(button_frame, text="Abort", command=abort, bg="red", fg="white").pack(side=tk.LEFT, padx=5)

root.mainloop()
pause_event.set()  # Initialize the pause event