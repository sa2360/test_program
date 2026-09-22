# A 同学 Day08 交接快照

来源：根目录 `ESP32 Project(1).rar` 和 `A交接说明.md`，于 2026-09-17 检查。

这里只解压了 6 个需要对照的文件：相机 main.cpp、camera_pins.h、platformio.ini，原图片服务器 app.py、requirements.txt，以及 Day08 实测 JPEG。

这些文件保持归档原样，作为 A 已完成工作的依据。没有解压个人 Wi-Fi 密码、虚拟环境或编译缓存。实际联合服务位于 `cloud/app/image_server.py`，B 固件位于 `device/esp32_board_test`。

A 自己的相机工程仍由 A 维护；把后续变更连同版本、引脚、协议差异和测试结果一起交接。原 app.py 仅供参考，不要与联合图片服务同时占用 8000 端口。
