import tkinter as tk
from tkinter import ttk, messagebox
import serial
import serial.tools.list_ports
import threading
import queue
import time

POLL_INTERVAL = 200   # ms
CMD_DELAY = 0.2       # s

# ---- Device communication helpers ----
def open_device(port, baud=19200):
    try:
        return serial.Serial(port, baudrate=baud, timeout=1)
    except Exception as e:
        messagebox.showerror("Error", f"Could not open {port}: {e}")
        return None

def close_device(dev):
    try:
        if dev and dev.is_open:
            dev.close()
    except:
        pass

def set_temp(dev, value):
    dev.reset_input_buffer()
    cmd = f"SVS,{value:.2f}\r\n"
    dev.write(cmd.encode())
    time.sleep(0.1)
    dev.readline()  # ignore reply

def query_set_temp(dev):
    dev.reset_input_buffer()
    dev.write(b"SVR\r\n")
    time.sleep(0.1)
    reply = dev.readline().decode(errors="ignore").strip()
    return reply

def query_curr_temp(dev):
    dev.reset_input_buffer()
    dev.write(b"TMR\r\n")
    time.sleep(0.1)
    reply = dev.readline().decode(errors="ignore").strip()
    if not reply:
        return None
    first_value = reply.split(",")[0].strip()
    try:
        return float(first_value)
    except ValueError:
        return None

def set_drive(dev, on=True):
    dev.reset_input_buffer()
    cmd = b"TCC,1\r\n" if on else b"TCC,0\r\n"
    dev.write(cmd)
    time.sleep(0.1)
    dev.readline()  # ignore reply

# ---- LED widget ----
class LedIndicator(tk.Canvas):
    def __init__(self, master, size=20):
        super().__init__(master, width=size, height=size, highlightthickness=0, bg=master["bg"])
        self.size = size
        self.circle = self.create_oval(2, 2, size-2, size-2, fill="grey", outline="black")

    def set_state(self, on):
        color = "green2" if on else "grey"
        self.itemconfig(self.circle, fill=color)

# ---- Controller Frame ----
class ControllerFrame(tk.LabelFrame):
    def __init__(self, master, title):
        super().__init__(master, text=title, padx=5, pady=5)
        self.dev = None
        self.com_var = tk.StringVar()
        self.set_var = tk.StringVar(value="--")
        self.curr_var = tk.StringVar(value="--")
        self.queue = queue.Queue()
        self.drive_state = False
        self.busy = False

        # COM selection
        ports = [p.device for p in serial.tools.list_ports.comports()]
        self.combo = ttk.Combobox(self, values=ports, textvariable=self.com_var, state="readonly", width=8)
        self.combo.grid(row=0, column=0, pady=2)
        self.connect_btn = tk.Button(self, text="Connect", command=self.connect, width=8)
        self.connect_btn.grid(row=0, column=1, padx=5)
        self.connect_led = LedIndicator(self, size=15)
        self.connect_led.grid(row=0, column=2, padx=5)

        # Big numbers
        tk.Label(self, text="Set Temp:", font=("Arial", 12)).grid(row=1, column=0, sticky="e")
        self.set_label = tk.Label(self, textvariable=self.set_var, font=("Arial", 16, "bold"))
        self.set_label.grid(row=1, column=1, sticky="w")

        tk.Label(self, text="Curr Temp:", font=("Arial", 12)).grid(row=2, column=0, sticky="e")
        self.curr_label = tk.Label(self, textvariable=self.curr_var, font=("Arial", 16, "bold"))
        self.curr_label.grid(row=2, column=1, sticky="w")

        # Entry + Set button
        self.new_temp = tk.Entry(self, width=6, font=("Arial", 12))
        self.new_temp.grid(row=1, column=2, padx=5)
        self.set_btn = tk.Button(self, text="Set Temp", command=self.update_temp, width=10)
        self.set_btn.grid(row=1, column=3)

        # Start/Stop
        self.start_btn = tk.Button(
            self,
            text="Start",
            command=lambda: self.toggle_drive(True),
            width=8,
            bg="SpringGreen4",
            fg="white"
        )
        self.start_btn.grid(row=3, column=0, pady=5)

        self.stop_btn = tk.Button(
            self,
            text="Stop",
            command=lambda: self.toggle_drive(False),
            width=8,
            bg="firebrick4",
            fg="white"
        )
        self.stop_btn.grid(row=3, column=1, pady=5)

        # Drive indicator
        tk.Label(self, text="DRV:", font=("Arial", 12)).grid(row=3, column=2, sticky="e")
        self.led = LedIndicator(self, size=20)
        self.led.grid(row=3, column=3)

    def connect(self):
        port = self.com_var.get()
        if not port:
            messagebox.showwarning("Warning", "Select a COM port")
            return
        self.dev = open_device(port)
        if self.dev:
            self.connect_led.set_state(True)
            threading.Thread(target=self.query_setpoint_once, daemon=True).start()

    def query_setpoint_once(self):
        try:
            reply = query_set_temp(self.dev)
            if reply:
                self.queue.put(("setpoint", reply))
        except:
            pass

    def update_temp(self):
        if not self.dev or self.busy:
            return
        try:
            value = float(self.new_temp.get())
        except ValueError:
            messagebox.showwarning("Invalid", "Enter a valid number")
            return
        def worker():
            self.busy = True
            set_temp(self.dev, value)
            self.queue.put(("setpoint", f"{value:.2f}"))
            time.sleep(CMD_DELAY)
            self.busy = False
        threading.Thread(target=worker, daemon=True).start()

    def toggle_drive(self, on):
        if not self.dev or self.busy:
            return
        def worker():
            self.busy = True
            set_drive(self.dev, on)
            self.drive_state = on
            self.queue.put(("drive", on))
            time.sleep(CMD_DELAY)
            self.busy = False
        threading.Thread(target=worker, daemon=True).start()

    def poll_thread(self):
        if self.dev and not self.busy:
            def worker():
                curr = query_curr_temp(self.dev)
                if curr is not None:
                    self.queue.put(("curr", curr))
            threading.Thread(target=worker, daemon=True).start()
        self.after(POLL_INTERVAL, self.poll_thread)

    def process_queue(self):
        try:
            while True:
                msg, data = self.queue.get_nowait()
                if msg == "setpoint":
                    self.set_var.set(data)
                elif msg == "curr":
                    self.curr_var.set(f"{data:.2f}")
                elif msg == "drive":
                    self.led.set_state(data)
        except queue.Empty:
            pass
        self.after(50, self.process_queue)

# ---- Power Supply / DC Charge Frame ----
class PowerSupplyFrame(tk.LabelFrame):
    def __init__(self, master, controller1, controller2, title="Power Supply"):
        super().__init__(master, text=title, padx=5, pady=5)
        self.dev = None
        self.controller1 = controller1
        self.controller2 = controller2
        self.busy = False

        # Arduino COM selection
        self.com_var = tk.StringVar()
        ports = [p.device for p in serial.tools.list_ports.comports()]
        self.combo = ttk.Combobox(self, values=ports, textvariable=self.com_var, state="readonly", width=8)
        self.combo.grid(row=0, column=0, padx=5)
        self.connect_btn = tk.Button(self, text="Connect", command=self.connect, width=8)
        self.connect_btn.grid(row=0, column=1, padx=5)
        self.connect_led = LedIndicator(self, size=15)
        self.connect_led.grid(row=0, column=2, padx=5)

        self.dc_btn = tk.Button(
            self,
            text="DC Charge",
            width=12,
            bg="dodgerblue4",
            fg="white",
            disabledforeground="white",
            command=self.send_dc_charge,
            state="disabled"
        )
        self.dc_btn.grid(row=1, column=0, pady=5)

        # LED indicator for charge
        self.led = LedIndicator(self, size=20)
        self.led.grid(row=1, column=1, padx=5)

        self.poll_button_state()

    def connect(self):
        port = self.com_var.get()
        if not port:
            messagebox.showwarning("Warning", "Select a COM port for Arduino")
            return
        try:
            self.dev = serial.Serial(port, baudrate=9600, timeout=1)
            time.sleep(2)  # Arduino reset
            self.connect_led.set_state(True)  # indicate connected
        except Exception as e:
            messagebox.showerror("Error", f"Could not open {port}: {e}")
            self.dev = None
            self.connect_led.set_state(False)

    def send_dc_charge(self):
        if not self.dev or self.busy:
            return

        def worker():
            self.busy = True
            self.dc_btn.config(state="disabled")
            self.led.set_state(True)
            self.dev.write(b'1')  # turn on
            for i in range(6, 0, -1):
                self.dc_btn.config(text=f"Charging {i}s")
                time.sleep(1)
            self.dev.write(b'0')  # turn off
            self.dc_btn.config(text="DC Charge", state="normal")
            self.led.set_state(False)
            self.busy = False

        threading.Thread(target=worker, daemon=True).start()

    def poll_button_state(self):
        """Enable button if both controllers' curr temp > set temp - 0.5 and Arduino connected"""
        try:
            c1_curr = self.controller1.curr_var.get()
            c1_set = self.controller1.set_var.get()
            c2_curr = self.controller2.curr_var.get()
            c2_set = self.controller2.set_var.get()

            if c1_curr != "--" and c1_set != "--" and c2_curr != "--" and c2_set != "--":
                c1_curr = float(c1_curr)
                c1_set = float(c1_set)
                c2_curr = float(c2_curr)
                c2_set = float(c2_set)
                if c1_curr > c1_set - 0.5 and c2_curr > c2_set - 0.5 and not self.busy and self.dev:
                    self.dc_btn.config(state="normal")
                else:
                    self.dc_btn.config(state="disabled")
            else:
                self.dc_btn.config(state="disabled")
        except ValueError:
            self.dc_btn.config(state="disabled")

        self.after(200, self.poll_button_state)

# ---- DDS Lock Frame ----
class DDSLockFrame(tk.LabelFrame):
    def __init__(self, master, controller1, controller2, title="DDS Lock", port="COM12", baud=115200):
        super().__init__(master, text=title, padx=5, pady=5)
        self.controller1 = controller1
        self.controller2 = controller2
        self.port = port
        self.baud = baud
        self.ser = None
        self.lock_active = True  # True = DDS outputs disabled

        tk.Label(self, text="DDS Status:", font=("Arial", 12)).grid(row=0, column=0, sticky="e")
        self.status_var = tk.StringVar(value="Disabled")
        self.status_label = tk.Label(self, textvariable=self.status_var, font=("Arial", 12, "bold"),
                                     bg="lightgrey", width=12, relief="sunken")
        self.status_label.grid(row=0, column=1, padx=5, pady=5)

        self.start_watchdog()
        self.poll_status()

    def start_watchdog(self):
        try:
            self.ser = serial.Serial(self.port, self.baud, timeout=0.5)
            time.sleep(0.1)
        except Exception as e:
            messagebox.showerror("DDS Error", f"Cannot open {self.port}: {e}")
            self.ser = None
            return

        def watchdog():
            while self.ser and self.ser.is_open:
                if self.lock_active:
                    self._send(":w25=0000.")
                    self._send(":w26=0000.")
                    self._send(":w20=0,0.")
                time.sleep(0.001)

        threading.Thread(target=watchdog, daemon=True).start()

    def _send(self, cmd):
        if not cmd.endswith("\n"):
            cmd += "\n"
        if self.ser and self.ser.is_open:
            self.ser.write(cmd.encode("ascii"))
            time.sleep(0.001)
            self.ser.read_until(b"\n")  # ignore reply

    def poll_status(self):
        try:
            c1_curr = self.controller1.curr_var.get()
            c1_set = self.controller1.set_var.get()
            c2_curr = self.controller2.curr_var.get()
            c2_set = self.controller2.set_var.get()

            if c1_curr != "--" and c1_set != "--" and c2_curr != "--" and c2_set != "--":
                c1_curr = float(c1_curr)
                c1_set = float(c1_set)
                c2_curr = float(c2_curr)
                c2_set = float(c2_set)
                if c1_curr > c1_set - 0.5 and c2_curr > c2_set - 0.5:
                    self.lock_active = False
                    self.status_var.set("Enabled")
                    self.status_label.config(bg="green2")
                else:
                    self.lock_active = True
                    self.status_var.set("Disabled")
                    self.status_label.config(bg="lightgrey")
            else:
                self.lock_active = True
                self.status_var.set("Disabled")
                self.status_label.config(bg="lightgrey")
        except ValueError:
            self.lock_active = True
            self.status_var.set("Disabled")
            self.status_label.config(bg="lightgrey")

        self.after(500, self.poll_status)

    def unlock_dds(self):
        if self.ser and self.ser.is_open:
            self.ser.close()
            self.ser = None

# ---- Main App ----
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("EOD Temp Moniter/Interlock")
        self.resizable(False, False)

        # Controllers
        self.ctrl1 = ControllerFrame(self, "Controller 1")
        self.ctrl1.pack(fill="x", pady=5, padx=10)
        self.ctrl2 = ControllerFrame(self, "Controller 2")
        self.ctrl2.pack(fill="x", pady=5, padx=10)

        # Power supply / DC charge
        self.ps_frame = PowerSupplyFrame(self, self.ctrl1, self.ctrl2)
        self.ps_frame.pack(fill="x", pady=5, padx=10)

        # DDS Lock panel
        self.dds_frame = DDSLockFrame(self, self.ctrl1, self.ctrl2)
        self.dds_frame.pack(fill="x", pady=5, padx=10)

        # Start polling
        self.ctrl1.poll_thread()
        self.ctrl2.poll_thread()
        self.ctrl1.process_queue()
        self.ctrl2.process_queue()

        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def on_close(self):
        close_device(self.ctrl1.dev)
        close_device(self.ctrl2.dev)
        if self.ps_frame.dev:
            close_device(self.ps_frame.dev)
        if self.dds_frame.ser:
            self.dds_frame.unlock_dds()
        self.destroy()

if __name__ == "__main__":
    app = App()
    app.mainloop()
