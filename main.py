import tkinter as tk
from tkinter import messagebox
import win32gui
import win32process
import win32api
import win32con
import psutil
import os
import subprocess
import shutil
import winreg
import ctypes
import time


class UninstallToolApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Windows Visual Uninstaller (WinXKill)")
        self.root.geometry("450x220")
        self.root.resizable(False, False)

        # Center the window on the screen
        self.center_window(450, 220)

        # Core state data
        self.software_info = self.get_empty_info()

        # Security Protection: Critical system processes or paths that are restricted
        self.protected_processes = ['explorer.exe', 'svchost.exe', 'cmd.exe', 'powershell.exe', 'taskmgr.exe']
        self.protected_paths = ['c:\\windows', 'c:\\windows\\system32', 'c:\\windows\\syswow64']

        self.setup_ui()

    def get_empty_info(self):
        return {
            "name": "",           # Software name
            "exe_path": "",       # Executable path
            "install_path": "",    # Installation directory
            "uninstall_cmd": "",   # Official uninstall command
        }

    def center_window(self, width, height):
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        x = (screen_width / 2) - (width / 2)
        y = (screen_height / 2) - (height / 2)
        self.root.geometry('%dx%d+%d+%d' % (width, height, x, y))

    def setup_ui(self):
        title_label = tk.Label(self.root, text="🎯 WinXKill", font=("Segoe UI", 16, "bold"))
        title_label.pack(pady=15)

        desc_label = tk.Label(self.root, text="Click the button, then click on the target window to uninstall it.", font=("Segoe UI", 10))
        desc_label.pack(pady=5)

        self.select_btn = tk.Button(self.root, text="Pick Target Window", font=("Segoe UI", 12),
                                    command=self.start_capture, width=25, height=2, bg="#f0f0f0")
        self.select_btn.pack(pady=10)

    def is_system_protected(self, exe_path, process_name):
        """Security check to prevent deleting system files."""
        if process_name.lower() in self.protected_processes:
            return True
        exe_dir = os.path.dirname(exe_path).lower()
        for protected_path in self.protected_paths:
            if exe_dir.startswith(protected_path):
                return True
        return False

    def start_capture(self):
        """Prepares to capture the window clicked by the mouse."""
        self.root.iconify()  # Minimize the current window
        time.sleep(0.5)      # Wait for the minimize animation

        # Check mouse state without blocking the main thread
        self.check_mouse_click()

    def check_mouse_click(self):
        """Detect mouse left button click."""
        # VK_LBUTTON = 0x01
        state = win32api.GetAsyncKeyState(win32con.VK_LBUTTON)
        if state < 0:  # Key is pressed
            self.process_click()
        else:
            # Check again after 50ms
            self.root.after(50, self.check_mouse_click)

    def process_click(self):
        """Process click event and get window info."""
        try:
            x, y = win32gui.GetCursorPos()
            hwnd = win32gui.WindowFromPoint((x, y))

            # Reshow the main window
            self.root.deiconify()

            # Get Process ID
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            if pid <= 0:
                raise Exception("Failed to get valid PID.")

            process = psutil.Process(pid)
            exe_path = process.exe()
            process_name = process.name()

            if self.is_system_protected(exe_path, process_name):
                messagebox.showerror("Security Warning", f"Target ({process_name}) is a system process and cannot be modified!")
                return

            self.software_info["exe_path"] = exe_path
            self.software_info["name"] = process_name.replace(".exe", "")
            self.software_info["install_path"] = os.path.dirname(exe_path)

            # Search registry for uninstall info
            self.find_software_registry_info()
            self.show_software_info()

        except psutil.AccessDenied:
            messagebox.showerror("Permission Denied", "Cannot access process info. Please run this tool as Administrator.")
            self.root.deiconify()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to parse window: {str(e)}")
            self.root.deiconify()

    def find_software_registry_info(self):
        """Uses winreg to find uninstall info from the registry."""
        reg_paths = [
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
            (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall")
        ]

        target_dir = os.path.normpath(self.software_info["install_path"]).lower()

        for root_key, reg_path in reg_paths:
            try:
                with winreg.OpenKey(root_key, reg_path) as hkey:
                    num_subkeys = winreg.QueryInfoKey(hkey)[0]
                    for i in range(num_subkeys):
                        subkey_name = winreg.EnumKey(hkey, i)
                        try:
                            with winreg.OpenKey(hkey, subkey_name) as subkey:
                                display_name = ""
                                install_loc = ""
                                uninstall_cmd = ""

                                try:
                                    display_name = winreg.QueryValueEx(subkey, "DisplayName")[0]
                                except FileNotFoundError:
                                    pass

                                try:
                                    install_loc = winreg.QueryValueEx(subkey, "InstallLocation")[0]
                                except FileNotFoundError:
                                    pass

                                try:
                                    uninstall_cmd = winreg.QueryValueEx(subkey, "UninstallString")[0]
                                except FileNotFoundError:
                                    pass

                                # Matching logic: if install location or uninstall command contains the target path
                                match_found = False
                                if install_loc and os.path.normpath(install_loc).lower() in target_dir:
                                    match_found = True
                                elif uninstall_cmd and target_dir in uninstall_cmd.lower():
                                    match_found = True

                                if match_found:
                                    self.software_info["name"] = display_name if display_name else self.software_info["name"]
                                    if install_loc and os.path.exists(install_loc):
                                        self.software_info["install_path"] = install_loc
                                    self.software_info["uninstall_cmd"] = uninstall_cmd
                                    return 
                        except EnvironmentError:
                            continue
            except EnvironmentError:
                continue

    def show_software_info(self):
        """Display recognition results and confirm."""
        info_text = f"""🔍 Recognition Result:

App Name: {self.software_info['name']}
Executable: {self.software_info['exe_path']}
Install Dir: {self.software_info['install_path']}

Do you want to confirm the uninstallation of this software?"""

        confirm = messagebox.askyesno("Confirm Uninstall", info_text)
        if confirm:
            self.execute_uninstall()

    def execute_uninstall(self):
        """Execute the uninstallation."""
        try:
            cmd = self.software_info["uninstall_cmd"]

            if cmd:
                messagebox.showinfo("Tip", "Official uninstaller found, starting...\nPlease follow the wizard to complete.")
                subprocess.Popen(cmd, shell=True)
            else:
                # Force delete confirmation
                msg = "⚠️ No official uninstaller found.\nDo you want to FORCE terminate the process and PERMANENTLY delete its folder?\nThis action is irreversible!"
                if messagebox.askyesno("Force Delete", msg, icon='warning'):
                    self.terminate_process()
                    time.sleep(1)  # Wait for file unlock
                    if os.path.exists(self.software_info["install_path"]):
                        shutil.rmtree(self.software_info["install_path"], ignore_errors=True)
                    messagebox.showinfo("Success", "Files deleted successfully!")

            self.software_info = self.get_empty_info()  # Reset
        except Exception as e:
            messagebox.showerror("Uninstall Error", f"Operation failed: {str(e)}")

    def terminate_process(self):
        """Kill-related processes."""
        target_exe = self.software_info["exe_path"]
        killed = 0
        for proc in psutil.process_iter(['pid', 'exe']):
            try:
                if proc.info['exe'] == target_exe:
                    proc.kill()
                    killed += 1
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        return killed


def is_admin():
    """Check for Administrator privileges."""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False


if __name__ == "__main__":
    # Force Administrator requirement
    if not is_admin():
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        messagebox.showwarning("Admin Required", "Please run this program as Administrator!\nOtherwise, it may fail to read the registry or terminate processes.")
        root.destroy()
        # You could also use the following to auto-elevate:
        # ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, __file__, None, 1)

    # Start the application
    root = tk.Tk()
    app = UninstallToolApp(root)
    root.mainloop()