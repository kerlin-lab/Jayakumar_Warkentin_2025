import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import serial
import serial.tools.list_ports
import ctypes
from tisgrabber.samples import tisgrabber as tis
import numpy as np
import os
import time
import sys
import traceback
from threading import Thread, Event

# Global variables
ic = None
hGrabber = 0
serial_device = None
frequency = None

def setup_camera_device(hGrabber):
    if ic.IC_IsDevValid(hGrabber):
        ic.IC_StartLive(hGrabber, 1)
        time.sleep(0.5)
        ic.IC_StopLive(hGrabber)
    else:
        print("No device opened")

def grab_frames_from_camera(hGrabber, phase_name, save_folder, num_images):
    if ic.IC_IsDevValid(hGrabber):
        ic.IC_StartLive(hGrabber, 0)
        
        for i in range(num_images):
            if ic.IC_SnapImage(hGrabber, 2000) == tis.IC_SUCCESS:
                filename = os.path.join(save_folder, f"image_{phase_name}_frame_{i+1}.bmp")
                ic.IC_SaveImage(hGrabber, tis.T(filename), tis.ImageFileTypes['BMP'], 90)
                time.sleep(0.1)
            else:
                print(f"No frame received in 2 seconds for phase {phase_name}, frame {i+1}.")
        
        ic.IC_StopLive(hGrabber)
    else:
        print("Invalid device handle.")

def initialize_DDS(serial_device, frequency):
    turn_off=":w20=0,0.\n"
    set_pulse_2_cmd = ":w22=2.\n"
    set_frequency_2_cmd= f":w24={frequency},0.\n"
    set_duty_cmd = ":w29=5000.\n"
    set_offset_cmd= ":w28=1150.\n"
    set_voltage_2_cmd= ":w26=3000.\n"
    try:
        serial_device.write(turn_off.encode())
        time.sleep(0.1)
        serial_device.write(set_pulse_2_cmd.encode())
        time.sleep(0.1)
        serial_device.write(set_duty_cmd.encode())
        time.sleep(0.1)
        serial_device.write(set_frequency_2_cmd.encode())
        time.sleep(0.1)
        serial_device.write(set_offset_cmd.encode())
        time.sleep(0.1)
        serial_device.write(set_voltage_2_cmd.encode())
        print("DDS initialized")

        serial_device.write(":w25=0000.\n".encode())
        time.sleep(0.1)
    
        serial_device.write(f":w23={frequency},0.\n".encode())
        time.sleep(0.1)
    
        serial_device.write(":w21=0.\n".encode())
        time.sleep(0.1)
    
        serial_device.write(":w20=1,1.\n".encode())
        time.sleep(0.1)
    except Exception as e:
        print(e)
        return

def make_phase_list(p1, p2, N):
    y_val = np.linspace(-1, 1, N)
    asin_y = np.arcsin(y_val)

    p1_rad = np.deg2rad(p1)
    p2_rad = np.deg2rad(p2)

    delta_rad = (p2_rad - p1_rad) % (2 * np.pi)

    phase_list_rad = p1_rad + ((asin_y + np.pi/2) / np.pi) * delta_rad
    phase_degs = np.rad2deg(phase_list_rad) % 360

    phase_list = np.round(phase_degs, 1)

    return phase_list

def modify_phase(curr_phase):
    global serial_device
    set_phase=":w31=" + str(curr_phase) + ".\n"
    try:
        serial_device.write(set_phase.encode())
    except Exception as e:
        print(e)
        return

def perform_phase_shift_image_acquisition(DDS_COM, baud_rate, phase1, phase2, steps, drive_voltage, num_frames, save_folder, progress_bar, abort_event, pause_event, delay, frequency):
    global ic
    global hGrabber
    global serial_device

    if ic is None:
        ic = ctypes.cdll.LoadLibrary("C:/Users/EOD/auto_zstack/reqs/tisgrabber/samples/tisgrabber_x64.dll")
        tis.declareFunctions(ic)
        ic.IC_InitLibrary(0)

    camera_name = b"DMK 72BUC02"

    if hGrabber == 0:
        hGrabber = ic.IC_CreateGrabber()
        success = ic.IC_OpenVideoCaptureDevice(hGrabber, camera_name)
        if not success:
            print(f"Failed to open camera device {camera_name.decode()}")
            return

        setup_camera_device(hGrabber)

    phase_list = make_phase_list(phase1, phase2, steps)

    try:
        serial_device = serial.Serial(DDS_COM, baud_rate)
        if serial_device.is_open:
            print(f"Serial port {DDS_COM} is already open.")
    except serial.SerialException as e:
        print(f"Failed to open {DDS_COM} on first attempt: {e}")
        traceback.print_exc()
        try:
            serial_device = serial.Serial(DDS_COM, baud_rate)
            print("Second attempt succeeded.")
        except serial.SerialException as e2:
            print(f"Second attempt to open {DDS_COM} also failed: {e2}")
            traceback.print_exc()
            print("Exiting function early due to serial failure.")
            return

    initialize_DDS(serial_device, frequency)

    try:
        for i in range(drive_voltage + 1):
            if abort_event.is_set():
                return
            if pause_event.is_set():
                while pause_event.is_set():
                    time.sleep(0.1)
            value = i * 1000
            cmd = f":w25={value:04d}.\n"
            serial_device.write(cmd.encode())
            time.sleep(1)
    except Exception as e:
        print(f"Error ramping voltage: {e}")
        traceback.print_exc()
        try:
            if serial_device and serial_device.is_open:
                serial_device.close()
        except Exception as e:
            print(f"Error closing serial device: {e}")
            traceback.print_exc()
        return

    try:
        for i, phase in enumerate(phase_list):
            if abort_event.is_set():
                return
            if pause_event.is_set():
                while pause_event.is_set():
                    time.sleep(0.1)
            multphase = phase * 10
            modify_phase(multphase)
            grab_frames_from_camera(hGrabber, str(phase), save_folder, num_frames)
            time.sleep(delay)
            progress_bar['value'] = (i + 1) / len(phase_list) * 100
    except Exception as e:
        print(f"Error during acquisition loop: {e}")
        traceback.print_exc()
    finally:
        try:
            if serial_device and serial_device.is_open:
                abort_DDS()
                serial_device.close()
                serial_device = None
        except Exception as e:
            print(f"Error closing serial device: {e}")
            traceback.print_exc()

class TS_Ranger:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("TS Ranger")
        self.root.config(bg="#eeeeee")

        default_font = ("Microsoft Tai Le", 12)
        self.root.option_add("*Font", default_font)

        self.root.iconbitmap(r"C:\Users\EOD\TS_Ranger_icon.ico")

        self.phase1_label = tk.Label(self.root, text="Phase 1 (°):", bg="#eeeeee")
        self.phase1_label.grid(row=0, column=0, padx=5, pady=5)
        self.phase1_entry = tk.Entry(self.root)
        self.phase1_entry.insert(0, "58")
        self.phase1_entry.grid(row=0, column=1, padx=5, pady=5)

        self.phase2_label = tk.Label(self.root, text="Phase 2 (°):", bg="#eeeeee")
        self.phase2_label.grid(row=1, column=0, padx=5, pady=5)
        self.phase2_entry = tk.Entry(self.root)
        self.phase2_entry.insert(0, "238")
        self.phase2_entry.grid(row=1, column=1, padx=5, pady=5)

        self.steps_label = tk.Label(self.root, text="Steps:", bg="#eeeeee")
        self.steps_label.grid(row=2, column=0, padx=5, pady=5)
        self.steps_entry = tk.Entry(self.root)
        self.steps_entry.insert(0, "45")
        self.steps_entry.grid(row=2, column=1, padx=5, pady=5)

        self.drive_voltage_label = tk.Label(self.root, text="Drive Voltage (V):", bg="#eeeeee")
        self.drive_voltage_label.grid(row=3, column=0, padx=5, pady=5)
        self.drive_voltage_entry = tk.Entry(self.root)
        self.drive_voltage_entry.insert(0, "12")
        self.drive_voltage_entry.grid(row=3, column=1, padx=5, pady=5)

        self.num_frames_label = tk.Label(self.root, text="Frames:", bg="#eeeeee")
        self.num_frames_label.grid(row=4, column=0, padx=5, pady=5)
        self.num_frames_entry = tk.Entry(self.root)
        self.num_frames_entry.insert(0, "1")
        self.num_frames_entry.grid(row=4, column=1, padx=5, pady=5)

        self.delay_label = tk.Label(self.root, text="Step Delay (s):", bg="#eeeeee")
        self.delay_label.grid(row=5, column=0, padx=5, pady=5)
        self.delay_entry = tk.Entry(self.root)
        self.delay_entry.insert(0, "5e-3")
        self.delay_entry.grid(row=5, column=1, padx=5, pady=5)

        self.frequency_label = tk.Label(self.root, text="Frequency (kHz):", bg="#eeeeee")
        self.frequency_label.grid(row=6, column=0, padx=5, pady=5)
        self.frequency_entry = tk.Entry(self.root)
        self.frequency_entry.insert(0, "100")
        self.frequency_entry.grid(row=6, column=1, padx=5, pady=5)

        self.DDS_COM_label = tk.Label(self.root, text="DDS COM:", bg="#eeeeee")
        self.DDS_COM_label.grid(row=7, column=0, padx=5, pady=5)
        self.DDS_COM_var = tk.StringVar()
        self.DDS_COM = ttk.Combobox(self.root, textvariable=self.DDS_COM_var)
        self.DDS_COM['values'] = [comport.device for comport in serial.tools.list_ports.comports()]
        self.DDS_COM.current(3)
        self.DDS_COM.grid(row=7, column=1, padx=5, pady=5)

        self.baud_rate_label = tk.Label(self.root, text="Baud Rate (bits/s):", bg="#eeeeee")
        self.baud_rate_label.grid(row=8, column=0, padx=5, pady=5)
        self.baud_rate_entry = tk.Entry(self.root)
        self.baud_rate_entry.insert(0, "115200")
        self.baud_rate_entry.grid(row=8, column=1, padx=5, pady=5)

        self.save_folder_label = tk.Label(self.root, text="Save Folder:", bg="#eeeeee")
        self.save_folder_label.grid(row=9, column=0, padx=5, pady=5)
        self.save_folder_button = tk.Button(self.root, text="Browse", command=self.browse_save_folder)
        self.save_folder_button.grid(row=9, column=1, padx=5, pady=5)
        self.save_folder_path = tk.StringVar()
        self.save_folder_path_label = tk.Label(self.root, textvariable=self.save_folder_path, bg="#eeeeee")
        self.save_folder_path_label.grid(row=10, column=0, columnspan=2, padx=5, pady=5)

        self.scan_status_label = tk.Label(self.root, text="", fg="red", bg="#eeeeee")
        self.scan_status_label.grid(row=11, column=0, columnspan=2, padx=5, pady=5)

        button_frame = tk.Frame(self.root, bg="#eeeeee")
        button_frame.grid(row=12, column=0, columnspan=2)

        self.start_button = tk.Button(button_frame, text="Start", command=self.start_acquisition, bg="#216D4A", fg="#ffffff")
        self.start_button.pack(side=tk.LEFT, padx=5, pady=5)

        self.pause_resume_button = tk.Button(button_frame, text="Pause", command=self.pause_resume_ramp, bg="#eeeeee", fg="#000000", state=tk.DISABLED)
        self.pause_resume_button.pack(side=tk.LEFT, padx=5, pady=5)

        self.abort_button = tk.Button(button_frame, text="Abort", command=self.abort_acquisition, bg="#E64141", fg="#ffffff", state=tk.DISABLED)
        self.abort_button.pack(side=tk.LEFT, padx=5, pady=5)
        
        self.progress_bar = ttk.Progressbar(self.root, length=200, mode="determinate")
        self.progress_bar.grid(row=14, column=0, columnspan=2, padx=5, pady=10)

        self.abort_event = Event()
        self.pause_event = Event()

    def start_acquisition(self):
        self.scan_status_label['text'] = "Scan Running"
        self.abort_event.clear()
        self.pause_event.clear()
        phase1 = float(self.phase1_entry.get())
        phase2 = float(self.phase2_entry.get())
        steps = int(self.steps_entry.get())
        drive_voltage = int(self.drive_voltage_entry.get())
        num_frames = int(self.num_frames_entry.get())
        delay = float(self.delay_entry.get())
        DDS_COM = self.DDS_COM_var.get()
        baud_rate = int(self.baud_rate_entry.get())
        save_folder = self.save_folder_path.get()
        frequency = int(self.frequency_entry.get())*100000

        if not save_folder:
            messagebox.showerror("Error", "Please select a save folder")
            self.scan_status_label['text'] = ""
            return

        self.start_button.config(state=tk.DISABLED)
        self.pause_resume_button.config(state=tk.NORMAL, text="Pause")
        self.abort_button.config(state=tk.NORMAL)

        thread = Thread(target=perform_phase_shift_image_acquisition, args=(DDS_COM, baud_rate, phase1, phase2, steps, drive_voltage, num_frames, save_folder, self.progress_bar, self.abort_event, self.pause_event, delay, frequency))
        thread.daemon = True
        thread.start()

        def check_thread():
            if thread.is_alive():
                self.root.after(100, check_thread)
            else:
                self.start_button.config(state=tk.NORMAL)
                self.pause_resume_button.config(state=tk.DISABLED, text="Pause")
                self.abort_button.config(state=tk.DISABLED)
                self.scan_status_label['text'] = "Scan Complete"
                self.root.after(2000, lambda: self.scan_status_label.config(text=""))
        check_thread()

    def pause_resume_ramp(self):
        if self.pause_resume_button['text'] == "Pause":
            self.scan_status_label['text'] = "Scan Paused"
            self.pause_event.set()
            self.pause_resume_button.config(text="Resume")
        else:
            self.scan_status_label['text'] = "Scan Running"
            self.pause_event.clear()
            self.pause_resume_button.config(text="Pause")

    def abort_acquisition(self):
        global serial_device

        #ch 1 voltage to 0
        serial_device.write(":w25=0000.\n".encode())
        #ch 2 voltage to 0
        serial_device.write(":w26=0000.\n".encode())
        #turn off ch1/2
        serial_device.write(":w20=0,0.\n".encode())

        try:
            if serial_device and serial_device.is_open:
                abort_DDS()
                serial_device.close()
                serial_device = None
        except Exception as e:
            print(f"Error closing serial device: {e}")
            traceback.print_exc()

        self.scan_status_label['text'] = "Scan Aborted"
        self.abort_event.set()
        
        self.start_button.config(state=tk.NORMAL)
        self.pause_resume_button.config(state=tk.DISABLED, text="Pause")
        self.abort_button.config(state=tk.DISABLED)

    def browse_save_folder(self):
        save_folder = filedialog.askdirectory(title="Select Save Folder")
        self.save_folder_path.set(save_folder)

    def run(self):
        self.root.mainloop()

if __name__ == "__main__":
    app = TS_Ranger()
    app.run()