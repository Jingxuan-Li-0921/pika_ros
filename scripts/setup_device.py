#!/usr/bin/env python3

import argparse
import json
import shlex
import subprocess
import re
import os
import cv2
import time
from pathlib import Path

DEVICE_LABELS = {
    "左": ("左", "Left"),
    "右": ("右", "Right"),
    "sensor": ("sensor", "sensor"),
    "gripper": ("gripper", "gripper"),
    "helmet": ("helmet", "helmet"),
}


def print_bilingual(zh, en):
    print(zh)
    print(en)


def input_bilingual(zh, en):
    print_bilingual(zh, en)
    return input()


def device_label(name, lang="zh"):
    zh, en = DEVICE_LABELS[name]
    return zh if lang == "zh" else en


def set_env_var_persistent(key, value, shell_rc="~/.config/pika/device.env"):
    rc_path = Path(shell_rc).expanduser()
    rc_path.parent.mkdir(parents=True, exist_ok=True)
    if not rc_path.exists():
        rc_path.touch()

    lines = rc_path.read_text().splitlines()
    export_line = f'export {key}={shlex.quote(str(value))}'
    updated = False

    for i, line in enumerate(lines):
        if line.startswith(f"export {key}="):
            lines[i] = export_line
            updated = True
            break

    if not updated:
        lines.append(export_line)

    rc_path.write_text("\n".join(lines) + "\n")
    print(f"Updated {rc_path}")


def run_command(command, *, report_error=False):
    """Run a command and return its output."""
    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True)
        if result.returncode != 0 and report_error:
            detail = result.stderr.strip() or f"exit status {result.returncode}"
            print_bilingual(
                f"命令执行失败: {command}\n{detail}",
                f"Command failed: {command}\n{detail}",
            )
        return result.stdout.strip()
    except Exception as e:
        print_bilingual(
            f"执行命令时出错: {str(e)}",
            f"Error running command: {str(e)}",
        )
        return None


def get_device_info(localization_tag=True):
    """Get device information."""
    # 运行 rs-enumerate-devices 命令
    rs_output = run_command("rs-enumerate-devices -s")
    if not rs_output:
        print_bilingual(
            "无法获取到深度摄像头数据",
            "Unable to get depth camera data",
        )
        return None, None, None, None

    # 解析输出获取序列号
    serial_match = re.search(r'Intel RealSense D405\s+(\d+)', rs_output)
    if not serial_match:
        print_bilingual(
            "无法获取到深度摄像头数据",
            "Unable to get depth camera data",
        )
        return None, None, None, None
    serial_number = serial_match.group(1)

    # 运行 udevadm 命令
    serial_devices = sorted(
        path.name
        for path in Path("/dev").glob("ttyUSB*")
        if path.name not in {"ttyUSB50", "ttyUSB51", "ttyUSB60", "ttyUSB61", "ttyUSB70"}
    )
    if len(serial_devices) != 1:
        print_bilingual(
            "请确保工控机只插入一个未绑定的USB串口设备",
            "Please ensure exactly one unbound USB serial device is connected to the industrial PC",
        )
        return None, None, None, None
    ls_output = serial_devices[0]
    udev_output = run_command(
        f"udevadm info --query=path --name=/dev/{shlex.quote(ls_output)}",
        report_error=True,
    )
    if not udev_output:
        print_bilingual(
            "无法获取到串口数据",
            "Unable to get serial port data",
        )
        return None, None, None, None

    # 解析 USB 路径
    usb_interfaces = re.findall(r"/([^/]+:\d+\.\d+)(?:/|$)", udev_output)
    if not usb_interfaces:
        print_bilingual("无法解析串口USB路径", "Unable to parse the serial USB path")
        return None, None, None, None
    usb_path = usb_interfaces[-1]
    # print("寻找鱼眼摄像头，请在出现鱼眼摄像头时按下s，非鱼眼摄像头则按下q(注意在图像窗口按下，不要在终端！！！)")
    # video_path = None
    # cv2.setLogLevel(0)
    # for i in range(50):
    #     cap = cv2.VideoCapture(i)
    #     fourcc = cv2.VideoWriter_fourcc(*'MJPG')
    #     cap.set(cv2.CAP_PROP_FOURCC, fourcc)
    #     cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    #     cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    #     cap.set(cv2.CAP_PROP_FPS, 30)
    #     key = None
    #     if cap.isOpened():
    #         # print("port:", "/dev/video"+str(i))
    #         while True:
    #             ret, frame = cap.read()
    #             cv2.imshow("/dev/video"+str(i), frame)
    #             key = cv2.waitKey(1)
    #             if key & 0xFF == ord('q'):
    #                 break
    #             elif key & 0xFF == ord('s'):
    #                 break
    #     cv2.destroyAllWindows()
    #     if key is not None and key & 0xFF == ord('s'):
    #         video_path = 'video' + str(i)
    #         break
    # cv2.destroyAllWindows()
    # if video_path is None:
    #     print("无法获取到鱼眼摄像头数据")
    #     return None, None

    video_device = None
    for i in range(50):
        video_output1 = run_command(f"cat /sys/class/video4linux/video{i}/device/../idVendor 2>/dev/null")
        video_output2 = run_command(f"cat /sys/class/video4linux/video{i}/device/../idProduct 2>/dev/null")
        if video_output1 == "1bcf" and video_output2 == "2cd1":
            video_device = 'video' + str(i)
            break

    if video_device is None:
        print_bilingual("无法获取到鱼眼摄像头数据", "Unable to get fisheye camera data")
        return None, None, None, None
    udev_output = run_command(
        f"udevadm info --query=path --name=/dev/{shlex.quote(video_device)}",
        report_error=True,
    )
    video_interfaces = re.findall(r"/([^/]+:\d+\.\d+)(?:/|$)", udev_output)
    if not video_interfaces:
        print_bilingual("无法解析鱼眼USB路径", "Unable to parse the fisheye USB path")
        return None, None, None, None
    video_path = video_interfaces[-1]

    localization_tag_serial = None
    if localization_tag:
        # Find LHR device serial (28de:2300)
        localization_tag_list = run_command("lsusb -d 28de:2300")
        if localization_tag_list:
            localization_tag_count = len([line for line in localization_tag_list.splitlines() if "28de:2300" in line])
            if localization_tag_count > 1:
                print_bilingual(
                    "请确保工控机只插入一个定位标签设备",
                    "Please ensure only one localization tag device is connected to the industrial PC",
                )
                return None, None, None, None

        localization_tag_output = run_command("lsusb -v -d 28de:2300 2>/dev/null")
        if not localization_tag_output:
            localization_tag_output = run_command("lsusb -v | grep 28de:2300 -A 20")
        localization_tag_serial_match = re.search(r'iSerial\s+\d+\s+([^\s]+)', localization_tag_output or "")
        if not localization_tag_serial_match:
            print_bilingual(
                "无法获取到设备定位标签序列号",
                "Unable to get localization tag serial number",
            )
            return None, None, None, None
        localization_tag_serial = localization_tag_serial_match.group(1)

    return serial_number, usb_path, video_path, localization_tag_serial


def binding_entries(left_info, right_info, select, helmet_info=None):
    """Return (kind, device_info, stable_number) entries for host udev."""
    if select == "1":
        return [("sensor", left_info, 50), ("sensor", right_info, 51)]
    if select == "2":
        return [("gripper", left_info, 60), ("gripper", right_info, 61)]
    if select == "3":
        return [("sensor", left_info, 50), ("gripper", right_info, 60)]
    if select == "4":
        return [("helmet", left_info, 70)]
    if select == "5":
        return [
            ("sensor", left_info, 50),
            ("sensor", right_info, 51),
            ("helmet", helmet_info, 70),
        ]
    raise ValueError(f"unsupported binding selection: {select}")


def generate_host_bundle(left_info, right_info, select, output_dir, helmet_info=None):
    """Generate data files for host-side udev installation without running sudo."""
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    grouped_rules = {}
    expected_devices = []

    for kind, info, stable_number in binding_entries(left_info, right_info, select, helmet_info):
        if not info:
            raise ValueError(f"missing device information for {kind}")
        serial_rule = (
            f'ACTION=="add", KERNEL=="ttyUSB*", KERNELS=="{info[1]}", '
            f'SUBSYSTEMS=="usb", MODE:="0777", SYMLINK+="ttyUSB{stable_number}"'
        )
        video_rule = (
            f'ACTION=="add", KERNEL=="video[0-9]*", KERNELS=="{info[2]}", '
            f'SUBSYSTEMS=="usb", ENV{{ID_V4L_CAPABILITIES}}=="*:capture:*", '
            f'MODE:="0777", SYMLINK+="video{stable_number}"'
        )
        grouped_rules.setdefault(f"99-pika-{kind}-serial.rules", []).append(serial_rule)
        grouped_rules.setdefault(f"99-pika-{kind}-fisheye.rules", []).append(video_rule)
        expected_devices.extend([f"/dev/ttyUSB{stable_number}", f"/dev/video{stable_number}"])

    environment = {}
    if select in {"1", "5"}:
        environment.update(pika_L_code=left_info[3], pika_R_code=right_info[3])
    elif select == "3":
        environment["pika_code"] = left_info[3]
    if select == "4" and left_info[3]:
        environment["pika_H_code"] = left_info[3]
    if select == "5":
        environment["pika_H_code"] = helmet_info[3]
    for key, value in environment.items():
        set_env_var_persistent(key, value)

    rule_files = []
    for filename, lines in sorted(grouped_rules.items()):
        rule_path = output_dir / filename
        rule_path.write_text("\n".join(lines) + "\n")
        rule_files.append(filename)

    manifest = {
        "version": 1,
        "selection": select,
        "rules": rule_files,
        "expected_devices": expected_devices,
        "environment": environment,
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    return manifest_path


def generate_setup_bash(left_info, right_info, select, helmet_with_tracker=False, helmet_info=None):
    if select == "1":
        path = "setup_multi_sensor.bash"
        usb_num1 = 50
        usb_num2 = 51
        name1 = "sensor_"
        name2 = "sensor_"
        to1 = ">"
        to2 = ">>"
        set_env_var_persistent("pika_L_code", left_info[3])
        set_env_var_persistent("pika_R_code", right_info[3])

    if select == "2":
        path = "setup_multi_gripper.bash"
        usb_num1 = 60
        usb_num2 = 61
        name1 = "gripper_"
        name2 = "gripper_"
        to1 = ">"
        to2 = ">>"
    if select == "3":
        path = "setup_sensor_gripper.bash"
        usb_num1 = 50
        usb_num2 = 60
        name1 = "sensor_"
        name2 = "gripper_"
        to1 = ">"
        to2 = ">"
        set_env_var_persistent("pika_code", left_info[3])
    if select == "4":
        path = "setup_helmet.bash"
        usb_num1 = 70
        usb_num2 = None
        name1 = "helmet_"
        name2 = None
        to1 = ">"
        to2 = None
        if helmet_with_tracker:
            set_env_var_persistent("pika_H_code", left_info[3])
    if select == "5":
        path = "setup_multi_sensor_helmet_whit_tracker.bash"
        set_env_var_persistent("pika_L_code", left_info[3])
        set_env_var_persistent("pika_R_code", right_info[3])
        set_env_var_persistent("pika_H_code", helmet_info[3])
        content = f"""
#/bin/bash

sudo sh -c 'echo "ACTION==\\\"add\\\", KERNELS==\\\"{left_info[1]}\\\", SUBSYSTEMS==\\\"usb\\\", MODE:=\\\"0777\\\", SYMLINK+=\\\"ttyUSB50\\\"" > /etc/udev/rules.d/sensor_serial.rules'
sudo sh -c 'echo "ACTION==\\\"add\\\", KERNELS==\\\"{right_info[1]}\\\", SUBSYSTEMS==\\\"usb\\\", MODE:=\\\"0777\\\", SYMLINK+=\\\"ttyUSB51\\\"" >> /etc/udev/rules.d/sensor_serial.rules'
sudo sh -c 'echo "ACTION==\\\"add\\\", KERNELS==\\\"{helmet_info[1]}\\\", SUBSYSTEMS==\\\"usb\\\", MODE:=\\\"0777\\\", SYMLINK+=\\\"ttyUSB70\\\"" > /etc/udev/rules.d/helmet_serial.rules'

sudo sh -c 'echo "ACTION==\\\"add\\\", KERNEL==\\\"video[0,2,4,6,8,10,12,14,16,18,20,22,24,26,28,30,32,34,36,38,40,42,44,46,48]*\\\", KERNELS==\\\"{left_info[2]}\\\", SUBSYSTEMS==\\\"usb\\\", MODE:=\\\"0777\\\", SYMLINK+=\\\"video50\\\"" > /etc/udev/rules.d/sensor_fisheye.rules'
sudo sh -c 'echo "ACTION==\\\"add\\\", KERNEL==\\\"video[0,2,4,6,8,10,12,14,16,18,20,22,24,26,28,30,32,34,36,38,40,42,44,46,48]*\\\", KERNELS==\\\"{right_info[2]}\\\", SUBSYSTEMS==\\\"usb\\\", MODE:=\\\"0777\\\", SYMLINK+=\\\"video51\\\"" >> /etc/udev/rules.d/sensor_fisheye.rules'
sudo sh -c 'echo "ACTION==\\\"add\\\", KERNEL==\\\"video[0,2,4,6,8,10,12,14,16,18,20,22,24,26,28,30,32,34,36,38,40,42,44,46,48]*\\\", KERNELS==\\\"{helmet_info[2]}\\\", SUBSYSTEMS==\\\"usb\\\", MODE:=\\\"0777\\\", SYMLINK+=\\\"video70\\\"" > /etc/udev/rules.d/helmet_fisheye.rules'

sudo udevadm control --reload-rules && sudo service udev restart && sudo udevadm trigger
            """
    """Generate setup.bash file."""
    if select == "5":
        pass
    elif usb_num2 is not None:
        content = f"""
#/bin/bash

sudo sh -c 'echo "ACTION==\\"add\\", KERNELS==\\"{left_info[1]}\\", SUBSYSTEMS==\\"usb\\", MODE:=\\"0777\\", SYMLINK+=\\"ttyUSB{usb_num1}\\"" {to1} /etc/udev/rules.d/{name1}serial.rules'
sudo sh -c 'echo "ACTION==\\"add\\", KERNELS==\\"{right_info[1]}\\", SUBSYSTEMS==\\"usb\\", MODE:=\\"0777\\", SYMLINK+=\\"ttyUSB{usb_num2}\\"" {to2} /etc/udev/rules.d/{name2}serial.rules'

sudo sh -c 'echo "ACTION==\\"add\\", KERNEL==\\"video[0,2,4,6,8,10,12,14,16,18,20,22,24,26,28,30,32,34,36,38,40,42,44,46,48]*\\", KERNELS==\\"{left_info[2]}\\", SUBSYSTEMS==\\"usb\\", MODE:=\\"0777\\", SYMLINK+=\\"video{usb_num1}\\"" {to1} /etc/udev/rules.d/{name1}fisheye.rules'
sudo sh -c 'echo "ACTION==\\"add\\", KERNEL==\\"video[0,2,4,6,8,10,12,14,16,18,20,22,24,26,28,30,32,34,36,38,40,42,44,46,48]*\\", KERNELS==\\"{right_info[2]}\\", SUBSYSTEMS==\\"usb\\", MODE:=\\"0777\\", SYMLINK+=\\"video{usb_num2}\\"" {to2} /etc/udev/rules.d/{name2}fisheye.rules'

sudo udevadm control --reload-rules && sudo service udev restart && sudo udevadm trigger
            """
    else:
        content = f"""
#/bin/bash

sudo sh -c 'echo "ACTION==\\"add\\", KERNELS==\\"{left_info[1]}\\", SUBSYSTEMS==\\"usb\\", MODE:=\\"0777\\", SYMLINK+=\\"ttyUSB{usb_num1}\\"" {to1} /etc/udev/rules.d/{name1}serial.rules'

sudo sh -c 'echo "ACTION==\\"add\\", KERNEL==\\"video[0,2,4,6,8,10,12,14,16,18,20,22,24,26,28,30,32,34,36,38,40,42,44,46,48]*\\", KERNELS==\\"{left_info[2]}\\", SUBSYSTEMS==\\"usb\\", MODE:=\\"0777\\", SYMLINK+=\\"video{usb_num1}\\"" {to1} /etc/udev/rules.d/{name1}fisheye.rules'

sudo udevadm control --reload-rules && sudo service udev restart && sudo udevadm trigger
            """

    with open(path, "w") as f:
        f.write(content)
    os.chmod(path, 0o755)


def generate_start_bash(
    left_info,
    right_info,
    select,
    helmet_with_tracker=False,
    helmet_info=None,
    output_dir=".",
):
    if select == "1":
        path = "start_multi_sensor.bash"
        usb_num1 = 50
        usb_num2 = 51
        content = f"""
SCRIPT_DIR=$(dirname "$(readlink -f "$0")")
camera_fps=30
camera_width=640
camera_height=480
l_depth_camera_no={left_info[0]}
r_depth_camera_no={right_info[0]}

l_serial_port=/dev/ttyUSB{usb_num1}
r_serial_port=/dev/ttyUSB{usb_num2}
sudo chmod a+rw /dev/ttyUSB*
l_fisheye_port={usb_num1}
r_fisheye_port={usb_num2}
sudo chmod a+rw /dev/video*

source /opt/ros/humble/setup.bash && cd $SCRIPT_DIR/../install/sensor_tools/share/sensor_tools/scripts/ && chmod 777 usb_camera.py
if [ -n "$1" ]; then
    source $SCRIPT_DIR/../install/setup.bash && ros2 launch sensor_tools open_multi_sensor.launch.py l_depth_camera_no:=_$l_depth_camera_no r_depth_camera_no:=_$r_depth_camera_no l_serial_port:=$l_serial_port r_serial_port:=$r_serial_port l_fisheye_port:=$l_fisheye_port r_fisheye_port:=$r_fisheye_port camera_fps:=$camera_fps camera_width:=$camera_width camera_height:=$camera_height camera_profile:=$camera_width,$camera_height,$camera_fps name:=$1 name_index:=$1_
else
    source $SCRIPT_DIR/../install/setup.bash && ros2 launch sensor_tools open_multi_sensor.launch.py l_depth_camera_no:=_$l_depth_camera_no r_depth_camera_no:=_$r_depth_camera_no l_serial_port:=$l_serial_port r_serial_port:=$r_serial_port l_fisheye_port:=$l_fisheye_port r_fisheye_port:=$r_fisheye_port camera_fps:=$camera_fps camera_width:=$camera_width camera_height:=$camera_height camera_profile:=$camera_width,$camera_height,$camera_fps
fi
                """
    if select == "2":
        path = "start_multi_gripper.bash"
        usb_num1 = 60
        usb_num2 = 61
        content = f"""
SCRIPT_DIR=$(dirname "$(readlink -f "$0")")
camera_fps=30
camera_width=640
camera_height=480
l_depth_camera_no={left_info[0]}
r_depth_camera_no={right_info[0]}

l_serial_port=/dev/ttyUSB{usb_num1}
r_serial_port=/dev/ttyUSB{usb_num2}
sudo chmod a+rw /dev/ttyUSB*
l_fisheye_port={usb_num1}
r_fisheye_port={usb_num2}
sudo chmod a+rw /dev/video*

source /opt/ros/humble/setup.bash && cd $SCRIPT_DIR/../install/sensor_tools/share/sensor_tools/scripts/ && chmod 777 usb_camera.py
if [ -n "$1" ]; then
    source $SCRIPT_DIR/../install/setup.bash && ros2 launch sensor_tools open_multi_gripper.launch.py l_depth_camera_no:=_$l_depth_camera_no r_depth_camera_no:=_$r_depth_camera_no l_serial_port:=$l_serial_port r_serial_port:=$r_serial_port l_fisheye_port:=$l_fisheye_port r_fisheye_port:=$r_fisheye_port camera_fps:=$camera_fps camera_width:=$camera_width camera_height:=$camera_height camera_profile:=$camera_width,$camera_height,$camera_fps name:=$1 name_index:=$1_
else
    source $SCRIPT_DIR/../install/setup.bash && ros2 launch sensor_tools open_multi_gripper.launch.py l_depth_camera_no:=_$l_depth_camera_no r_depth_camera_no:=_$r_depth_camera_no l_serial_port:=$l_serial_port r_serial_port:=$r_serial_port l_fisheye_port:=$l_fisheye_port r_fisheye_port:=$r_fisheye_port camera_fps:=$camera_fps camera_width:=$camera_width camera_height:=$camera_height camera_profile:=$camera_width,$camera_height,$camera_fps
fi
                """
    if select == "3":
        path = "start_sensor_gripper.bash"
        usb_num1 = 50
        usb_num2 = 60
        content = f"""
SCRIPT_DIR=$(dirname "$(readlink -f "$0")")
camera_fps=30
camera_width=640
camera_height=480
gripper_depth_camera_no={right_info[0]}

sensor_serial_port=/dev/ttyUSB{usb_num1}
gripper_serial_port=/dev/ttyUSB{usb_num2}
sudo chmod a+rw /dev/ttyUSB*
gripper_fisheye_port={usb_num2}
sudo chmod a+rw /dev/video*

source /opt/ros/humble/setup.bash && cd $SCRIPT_DIR/../install/sensor_tools/share/sensor_tools/scripts/ && chmod 777 usb_camera.py
source $SCRIPT_DIR/../install/setup.bash && ros2 launch sensor_tools open_sensor_gripper.launch.py gripper_depth_camera_no:=_$gripper_depth_camera_no sensor_serial_port:=$sensor_serial_port gripper_serial_port:=$gripper_serial_port  gripper_fisheye_port:=$gripper_fisheye_port camera_fps:=$camera_fps camera_width:=$camera_width camera_height:=$camera_height camera_profile:=$camera_width,$camera_height,$camera_fps
                """
    if select == "4":
        path = "start_helmet.bash"
        usb_num1 = 70
        helmet_launch = "open_helmet_whit_tracker.launch.py" if helmet_with_tracker else "open_helmet.launch.py"
        content = f"""
SCRIPT_DIR=$(dirname "$(readlink -f "$0")")
camera_fps=30
camera_width=640
camera_height=480
helmet_depth_camera_no={left_info[0]}
helmet_serial_port=/dev/ttyUSB{usb_num1}
sudo chmod a+rw /dev/ttyUSB*
helmet_fisheye_port={usb_num1}
sudo chmod a+rw /dev/video*

source /opt/ros/humble/setup.bash && cd $SCRIPT_DIR/../install/sensor_tools/share/sensor_tools/scripts/ && chmod 777 usb_camera.py
source $SCRIPT_DIR/../install/setup.bash && ros2 launch sensor_tools {helmet_launch} depth_camera_no:=_$helmet_depth_camera_no serial_port:=$helmet_serial_port fisheye_port:=$helmet_fisheye_port camera_fps:=$camera_fps camera_width:=$camera_width camera_height:=$camera_height camera_profile:=$camera_width,$camera_height,$camera_fps
                """
    if select == "5":
        path = "start_multi_sensor_helmet_whit_tracker.bash"
        content = f"""
SCRIPT_DIR=$(dirname "$(readlink -f "$0")")
camera_fps=30
camera_width=640
camera_height=480
l_depth_camera_no={left_info[0]}
r_depth_camera_no={right_info[0]}
h_depth_camera_no={helmet_info[0]}

l_serial_port=/dev/ttyUSB50
r_serial_port=/dev/ttyUSB51
h_serial_port=/dev/ttyUSB70
sudo chmod a+rw /dev/ttyUSB*
l_fisheye_port=50
r_fisheye_port=51
h_fisheye_port=70
sudo chmod a+rw /dev/video*

source /opt/ros/humble/setup.bash && cd $SCRIPT_DIR/../install/sensor_tools/share/sensor_tools/scripts/ && chmod 777 usb_camera.py
if [ -n "$1" ]; then
    source $SCRIPT_DIR/../install/setup.bash && ros2 launch sensor_tools open_multi_sensor_helmet_whit_tracker.launch.py l_depth_camera_no:=_$l_depth_camera_no r_depth_camera_no:=_$r_depth_camera_no h_depth_camera_no:=_$h_depth_camera_no l_serial_port:=$l_serial_port r_serial_port:=$r_serial_port h_serial_port:=$h_serial_port l_fisheye_port:=$l_fisheye_port r_fisheye_port:=$r_fisheye_port h_fisheye_port:=$h_fisheye_port camera_fps:=$camera_fps camera_width:=$camera_width camera_height:=$camera_height camera_profile:=$camera_width,$camera_height,$camera_fps name:=$1 name_index:=$1_
else
    source $SCRIPT_DIR/../install/setup.bash && ros2 launch sensor_tools open_multi_sensor_helmet_whit_tracker.launch.py l_depth_camera_no:=_$l_depth_camera_no r_depth_camera_no:=_$r_depth_camera_no h_depth_camera_no:=_$h_depth_camera_no l_serial_port:=$l_serial_port r_serial_port:=$r_serial_port h_serial_port:=$h_serial_port l_fisheye_port:=$l_fisheye_port r_fisheye_port:=$r_fisheye_port h_fisheye_port:=$h_fisheye_port camera_fps:=$camera_fps camera_width:=$camera_width camera_height:=$camera_height camera_profile:=$camera_width,$camera_height,$camera_fps
fi
                """
    # Generated launchers may live outside the ROS workspace. Resolve the
    # install prefix through the environment set by the container entrypoint.
    content = content.replace(
        "$SCRIPT_DIR/../install", "${PIKA_WS:-/workspace/Pika_data/pika_ros}/install"
    )
    content = content.replace("sudo chmod a+rw", "chmod a+rw")
    output_path = Path(output_dir) / path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        f.write(content)
    os.chmod(output_path, 0o755)
    return output_path


def parse_arguments():
    parser = argparse.ArgumentParser(description="Bind Pika devices to stable host device names.")
    parser.add_argument(
        "--host-managed",
        action="store_true",
        help="generate host udev rule files without trying to install them in the container",
    )
    parser.add_argument(
        "--output-dir",
        default=".",
        help="directory for generated rules, manifest, and launcher",
    )
    return parser.parse_args()


def main():
    args = parse_arguments()
    print_bilingual("=== pika配置工具 ===", "=== Pika Setup Tool ===")
    helmet_with_tracker = False
    select = None
    while True:
        select = input_bilingual(
            "请选择绑定\n"
            "1.两个pika sensor(手持夹爪)\n"
            "2.两个pika gripper(安装于机械臂上的夹爪)\n"
            "3.一个pika sensor 一个pika gripper\n"
            "4.一个pika helmet\n"
            "5.两个pika sensor和一个带定位器的helmet\n"
            "请输入：",
            "Please select binding\n"
            "1. Two pika sensors (handheld grippers)\n"
            "2. Two pika grippers (mounted on robot arm)\n"
            "3. One pika sensor and one pika gripper\n"
            "4. One pika helmet\n"
            "5. Two pika sensors and one helmet with tracker\n"
            "Enter:",
        )
        if select == "1":
            device1 = "左"
            device2 = "右"
            break
        if select == "2":
            device1 = "左"
            device2 = "右"
            break
        if select == "3":
            device1 = "sensor"
            device2 = "gripper"
            break
        if select == "4":
            device1 = "helmet"
            device2 = None
            tracker_select = input_bilingual(
                "helmet是否带定位器(Tracker)？\n1.带定位器\n2.不带定位器\n请输入：",
                "Does the helmet include a tracker?\n"
                "1. With tracker\n"
                "2. Without tracker\n"
                "Enter:",
            ).strip()
            helmet_with_tracker = tracker_select == "1"
            break
        if select == "5":
            device1 = "左"
            device2 = "右"
            device3 = "helmet"
            helmet_with_tracker = True
            break
        else:
            print_bilingual("请输入1、2、3、4或5", "Please enter 1, 2, 3, 4, or 5")
            continue

    print_bilingual(
        f"请插入{device_label(device1)}设备，然后按回车键继续...",
        f"Please plug in the {device_label(device1, 'en')} device, then press Enter to continue...",
    )
    input()
    print_bilingual(
        f"正在获取{device_label(device1)}设备信息...",
        f"Getting {device_label(device1, 'en')} device information...",
    )
    while True:
        left_info = get_device_info(True if select == "1" or select == "3" or select == "5" or (select == "4" and helmet_with_tracker) else False)
        if not left_info[0]:
            print_bilingual(
                f"无法获取{device_label(device1)}设备信息，请检查设备连接，然后按回车键继续...",
                f"Unable to get {device_label(device1, 'en')} device information. "
                "Please check the device connection, then press Enter to continue...",
            )
            input()
        else:
            break
    print_bilingual(
        f"{device_label(device1)}设备信息: {left_info[0]} {left_info[1]} {left_info[2]} {left_info[3]}",
        f"{device_label(device1, 'en')} device info: {left_info[0]} {left_info[1]} {left_info[2]} {left_info[3]}",
    )

    right_info = None
    if device2 is not None:
        print_bilingual(
            f"请拔出{device_label(device1)}设备，插入{device_label(device2)}设备"
            "（注意不要插在同一个USB口，配置完成后USB口不能改变），然后按回车键继续...",
            f"Please unplug the {device_label(device1, 'en')} device and plug in the {device_label(device2, 'en')} device "
            "(do not use the same USB port; the USB port must not change after setup), then press Enter to continue...",
        )
        input()
        print_bilingual(
            f"正在获取{device_label(device2)}设备信息...",
            f"Getting {device_label(device2, 'en')} device information...",
        )
        while True:
            right_info = get_device_info(True if select == "1" or select == "5" else False)
            if not right_info[0]:
                print_bilingual(
                    f"无法获取{device_label(device2)}设备信息，请检查设备连接，然后按回车键继续...",
                    f"Unable to get {device_label(device2, 'en')} device information. "
                    "Please check the device connection, then press Enter to continue...",
                )
                input()
            else:
                break
        print_bilingual(
            f"{device_label(device2)}设备信息: {right_info[0]} {right_info[1]} {right_info[2]} {right_info[3]}",
            f"{device_label(device2, 'en')} device info: {right_info[0]} {right_info[1]} {right_info[2]} {right_info[3]}",
        )

    helmet_info = None
    if select == "5":
        print_bilingual(
            f"请拔出{device_label(device2)}设备，插入{device_label(device3)}设备（注意不要插在同一个USB口，配置完成后USB口不能改变），然后按回车键继续...",
            f"Please unplug the {device_label(device2, 'en')} device and plug in the {device_label(device3, 'en')} device "
            "(do not use the same USB port; the USB port must not change after setup), then press Enter to continue...",
        )
        input()
        print_bilingual(
            f"正在获取{device_label(device3)}设备信息...",
            f"Getting {device_label(device3, 'en')} device information...",
        )
        while True:
            helmet_info = get_device_info(True)
            if not helmet_info[0]:
                print_bilingual(
                    f"无法获取{device_label(device3)}设备信息，请检查设备连接，然后按回车键继续...",
                    f"Unable to get {device_label(device3, 'en')} device information. "
                    "Please check the device connection, then press Enter to continue...",
                )
                input()
            else:
                break
        print_bilingual(
            f"{device_label(device3)}设备信息: {helmet_info[0]} {helmet_info[1]} {helmet_info[2]} {helmet_info[3]}",
            f"{device_label(device3, 'en')} device info: {helmet_info[0]} {helmet_info[1]} {helmet_info[2]} {helmet_info[3]}",
        )

    # 生成配置文件
    print_bilingual("正在生成配置文件...", "Generating configuration files...")
    if args.host_managed:
        manifest_path = generate_host_bundle(
            left_info, right_info, select, args.output_dir, helmet_info
        )
        start_path = generate_start_bash(
            left_info,
            right_info,
            select,
            helmet_with_tracker,
            helmet_info,
            args.output_dir,
        )
        print_bilingual(
            "容器内设备识别完成；等待 run.py 在宿主机安装 udev 规则。",
            "Device discovery is complete; run.py will install the udev rules on the host.",
        )
        print(f"PIKA_SETUP_MANIFEST={manifest_path}")
        print(f"PIKA_START_SCRIPT={start_path}")
        return

    generate_setup_bash(left_info, right_info, select, helmet_with_tracker, helmet_info)
    generate_start_bash(left_info, right_info, select, helmet_with_tracker, helmet_info)
    setup_path = "setup_multi_sensor.bash" if select=="1" else ("setup_multi_gripper.bash" if select=="2" else ("setup_sensor_gripper.bash" if select == "3" else ("setup_helmet.bash" if select == "4" else "setup_multi_sensor_helmet_whit_tracker.bash")))
    start_path = "start_multi_sensor.bash" if select=="1" else ("start_multi_gripper.bash" if select=="2" else ("start_sensor_gripper.bash" if select == "3" else ("start_helmet.bash" if select == "4" else "start_multi_sensor_helmet_whit_tracker.bash")))
    print_bilingual("配置完成！已生成以下文件：", "Setup complete! The following files were generated:")
    print(f"1. {setup_path}")
    print(f"2. {start_path}")
    print_bilingual(f"执行{setup_path}", f"Running {setup_path}")
    run_command(f"bash {setup_path}")
    print_bilingual("执行完成。", "Done.")
    while True:
        print_bilingual(
            "请拔插设备，注意插入先前绑定的同一个USB口。然后按回车键检查是否绑定成功...",
            "Please unplug and replug the device into the same USB port used during binding. "
            "Then press Enter to verify the binding...",
        )
        input()
        print_bilingual("请等待...", "Please wait...")
        time.sleep(5)
        video_list = run_command("ls /dev | grep video")
        usb_list = run_command("ls /dev | grep ttyUSB")
        if (select == "1" or select == "3" or select == "5") and video_list.find("50") < 0:
            print_bilingual(
                "找不到sensor（左）鱼眼",
                "Cannot find sensor (left) fisheye camera",
            )
            continue
        if (select == "1" or select == "5") and video_list.find("51") < 0:
            print_bilingual(
                "找不到sensor（右）鱼眼",
                "Cannot find sensor (right) fisheye camera",
            )
            continue
        if (select == "2" or select == "3") and video_list.find("60") < 0:
            print_bilingual(
                "找不到gripper（左）鱼眼",
                "Cannot find gripper (left) fisheye camera",
            )
            continue
        if (select == "2") and video_list.find("61") < 0:
            print_bilingual(
                "找不到gripper（右）鱼眼",
                "Cannot find gripper (right) fisheye camera",
            )
            continue
        if (select == "1" or select == "3" or select == "5") and usb_list.find("50") < 0:
            print_bilingual(
                "找不到sensor（左）串口",
                "Cannot find sensor (left) serial port",
            )
            continue
        if (select == "1" or select == "5") and usb_list.find("51") < 0:
            print_bilingual(
                "找不到sensor（右）串口",
                "Cannot find sensor (right) serial port",
            )
            continue
        if (select == "2" or select == "3") and usb_list.find("60") < 0:
            print_bilingual(
                "找不到gripper（左）串口",
                "Cannot find gripper (left) serial port",
            )
            continue
        if (select == "2") and usb_list.find("61") < 0:
            print_bilingual(
                "找不到gripper（右）串口",
                "Cannot find gripper (right) serial port",
            )
            continue
        if (select == "4" or select == "5") and usb_list.find("70") < 0:
            print_bilingual(
                "找不到helmet串口",
                "Cannot find helmet serial port",
            )
            continue
        break
    print_bilingual("绑定成功，启动设备方法：", "Binding successful. To start the device:")
    print_bilingual(f"2. 然后运行: bash {start_path}", f"2. Then run: bash {start_path}")


if __name__ == "__main__":
    main()
