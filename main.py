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
        self.root.title("Windows 可视化卸载工具 (类xkill)")
        self.root.geometry("450x220")
        self.root.resizable(False, False)

        # 居中显示窗口
        self.center_window(450, 220)

        # 核心状态数据
        self.software_info = self.get_empty_info()

        # 安全防护：禁止操作的系统关键进程或目录关键字
        self.protected_processes = ['explorer.exe', 'svchost.exe', 'cmd.exe', 'powershell.exe', 'taskmgr.exe']
        self.protected_paths = ['c:\\windows', 'c:\\windows\\system32', 'c:\\windows\\syswow64']

        self.setup_ui()

    def get_empty_info(self):
        return {
            "name": "",  # 软件名称
            "exe_path": "",  # 可执行文件路径
            "install_path": "",  # 安装目录
            "uninstall_cmd": "",  # 官方卸载命令
        }

    def center_window(self, width, height):
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        x = (screen_width / 2) - (width / 2)
        y = (screen_height / 2) - (height / 2)
        self.root.geometry('%dx%d+%d+%d' % (width, height, x, y))

    def setup_ui(self):
        title_label = tk.Label(self.root, text="🎯 准星卸载工具", font=("微软雅黑", 16, "bold"))
        title_label.pack(pady=15)

        desc_label = tk.Label(self.root, text="点击下方按钮后，使用鼠标左键点击要卸载的软件窗口", font=("微软雅黑", 10))
        desc_label.pack(pady=5)

        self.select_btn = tk.Button(self.root, text="点击抓取目标窗口", font=("微软雅黑", 12),
                                    command=self.start_capture, width=25, height=2, bg="#f0f0f0")
        self.select_btn.pack(pady=10)

    def is_system_protected(self, exe_path, process_name):
        """安全检查，防止误删系统文件"""
        if process_name.lower() in self.protected_processes:
            return True
        exe_dir = os.path.dirname(exe_path).lower()
        for protected_path in self.protected_paths:
            if exe_dir.startswith(protected_path):
                return True
        return False

    def start_capture(self):
        """准备捕获鼠标点击的窗口"""
        self.root.iconify()  # 最小化当前窗口
        time.sleep(0.5)  # 等待窗口最小化动画完成

        # 使用原生API非阻塞轮询鼠标左键状态
        self.check_mouse_click()

    def check_mouse_click(self):
        """检测鼠标左键点击"""
        # VK_LBUTTON = 0x01
        state = win32api.GetAsyncKeyState(win32con.VK_LBUTTON)
        if state < 0:  # 小于0表示按键被按下
            self.process_click()
        else:
            # 每 50 毫秒检查一次，不阻塞主线程
            self.root.after(50, self.check_mouse_click)

    def process_click(self):
        """处理点击事件，获取窗口信息"""
        try:
            x, y = win32gui.GetCursorPos()
            hwnd = win32gui.WindowFromPoint((x, y))

            # 恢复主窗口
            self.root.deiconify()

            # 获取进程ID
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            if pid <= 0:
                raise Exception("无法获取有效的进程ID")

            process = psutil.Process(pid)
            exe_path = process.exe()
            process_name = process.name()

            if self.is_system_protected(exe_path, process_name):
                messagebox.showerror("安全警告", f"目标 ({process_name}) 属于系统保护进程，禁止操作！")
                return

            self.software_info["exe_path"] = exe_path
            self.software_info["name"] = process_name.replace(".exe", "")
            self.software_info["install_path"] = os.path.dirname(exe_path)

            # 在注册表中查找完整的卸载信息
            self.find_software_registry_info()
            self.show_software_info()

        except psutil.AccessDenied:
            messagebox.showerror("权限不足", "无法访问该进程信息，请确保本工具已使用管理员权限运行。")
            self.root.deiconify()
        except Exception as e:
            messagebox.showerror("错误", f"解析窗口失败：{str(e)}")
            self.root.deiconify()

    def find_software_registry_info(self):
        """使用内置 winreg 模块从注册表查找卸载信息"""
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

                                # 匹配逻辑：如果注册表中的安装路径或者卸载命令路径 包含 我们抓取到的进程路径
                                match_found = False
                                if install_loc and os.path.normpath(install_loc).lower() in target_dir:
                                    match_found = True
                                elif uninstall_cmd and target_dir in uninstall_cmd.lower():
                                    match_found = True

                                if match_found:
                                    self.software_info["name"] = display_name if display_name else self.software_info[
                                        "name"]
                                    if install_loc and os.path.exists(install_loc):
                                        self.software_info["install_path"] = install_loc
                                    self.software_info["uninstall_cmd"] = uninstall_cmd
                                    return  # 找到即刻返回
                        except EnvironmentError:
                            continue
            except EnvironmentError:
                continue

    def show_software_info(self):
        """展示识别结果并确认"""
        info_text = f"""🔍 识别结果：

软件名称：{self.software_info['name']}
可执行文件：{self.software_info['exe_path']}
安装目录：{self.software_info['install_path']}

是否确认卸载该软件？"""

        confirm = messagebox.askyesno("确认卸载", info_text)
        if confirm:
            self.execute_uninstall()

    def execute_uninstall(self):
        """执行卸载"""
        try:
            cmd = self.software_info["uninstall_cmd"]

            if cmd:
                messagebox.showinfo("提示", "已找到官方卸载程序，即将启动...\n请根据弹出的卸载向导完成操作。")
                # 很多卸载命令带有参数(如 /S, /I)，使用 subprocess.Popen 直接执行
                subprocess.Popen(cmd, shell=True)
            else:
                # 暴力删除前二次确认
                msg = "⚠️ 未找到该软件的官方卸载程序。\n是否要强行终止该进程并永久删除其所在的文件夹？\n此操作不可恢复！"
                if messagebox.askyesno("暴力强制删除", msg, icon='warning'):
                    self.terminate_process()
                    time.sleep(1)  # 等待文件解除占用
                    if os.path.exists(self.software_info["install_path"]):
                        shutil.rmtree(self.software_info["install_path"], ignore_errors=True)
                    messagebox.showinfo("成功", "已强行删除文件目录！")

            self.software_info = self.get_empty_info()  # 重置
        except Exception as e:
            messagebox.showerror("卸载错误", f"操作失败：{str(e)}")

    def terminate_process(self):
        """结束相关进程"""
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
    """检查是否拥有管理员权限"""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False


if __name__ == "__main__":
    # 强制管理员权限提示
    if not is_admin():
        # 如果需要自动提权，可以取消下面代码的注释
        # ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, __file__, None, 1)
        # sys.exit()

        import tkinter as tk

        root = tk.Tk()
        root.withdraw()
        messagebox.showwarning("权限警告", "请右键选择【以管理员身份运行】本程序！\n否则可能无法读取注册表或结束进程。")
        root.destroy()

    # 启动主程序
    root = tk.Tk()
    app = UninstallToolApp(root)
    root.mainloop()