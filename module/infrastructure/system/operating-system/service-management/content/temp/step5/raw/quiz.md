Câu 01. systemd quản lý dịch vụ nền trên Linux thông qua khái niệm nào?
A. Process group mô tả mọi tiến trình cùng người dùng.
B. Package manifest mô tả tệp cài đặt của ứng dụng.
C. Kernel module mô tả driver được nạp khi khởi động.
D. Unit mô tả dịch vụ hoặc tài nguyên cần quản lý.
Đáp án đúng: D

Câu 02. File unit service của systemd thường được chia thành những section chính nào?
A. [Unit], [Service] và [Install].
B. [Unit], [Runtime] và [Security].
C. [Service], [Process] và [Startup].
D. [System], [Daemon] và [Target].
Đáp án đúng: A

Câu 03. Trong unit file, `After=` chủ yếu xác định điều gì?
A. Thứ tự khởi động tương đối giữa các unit.
B. Điều kiện bắt buộc để unit phụ thuộc phải thành công.
C. Chính sách tự khởi động lại khi process thoát.
D. Việc kéo unit được nêu vào transaction hiện tại.
Đáp án đúng: A

Câu 04. Khác biệt quan trọng giữa `Wants=` và `Requires=` là gì?
A. Wants luôn dừng unit chính nếu dependency thất bại.
B. Requires chỉ sắp thứ tự, không kéo dependency vào.
C. Requires tạo quan hệ phụ thuộc mạnh hơn Wants.
D. Hai directive có cùng hành vi trong mọi trường hợp.
Đáp án đúng: C

Câu 05. Trong systemd, `systemctl enable app.service` thường làm gì?
A. Thiết lập liên kết để unit được kéo vào lúc boot.
B. Bật chế độ tự restart khi process trả mã lỗi.
C. Khởi động service ngay trong phiên hiện tại.
D. Nạp lại nội dung unit file vào systemd manager.
Đáp án đúng: A

Câu 06. Muốn enable và start service trong cùng thao tác, dùng lệnh nào?
A. systemctl reload --enable app.service.
B. systemctl enable --now app.service.
C. systemctl start --preset app.service.
D. systemctl daemon-reload app.service.
Đáp án đúng: B

Câu 07. Sau khi chỉnh sửa unit file trên đĩa, bước nào cập nhật cấu hình manager?
A. Chạy systemctl reload app.service.
B. Chạy systemctl daemon-reload.
C. Chạy systemctl restart systemd-journald.
D. Chạy systemctl enable app.service.
Đáp án đúng: B

Câu 08. `systemctl reload app.service` khác `restart` ở điểm nào?
A. Reload yêu cầu ứng dụng nạp lại cấu hình khi hỗ trợ.
B. Hai lệnh luôn tương đương với mọi service.
C. Reload luôn kết thúc process rồi tạo process mới.
D. Restart chỉ gửi tín hiệu nạp lại cấu hình cho process.
Đáp án đúng: A

Câu 09. Trong unit service, `Type=oneshot` thường dùng cho trường hợp nào?
A. Ứng dụng báo sẵn sàng bằng giao thức notify.
B. Chạy một lệnh tác vụ rồi kết thúc.
C. Service tạo nhiều child process và dùng PID file.
D. Daemon chạy liên tục ở nền và giữ process chính.
Đáp án đúng: B

Câu 10. `RemainAfterExit=yes` có tác dụng nào với oneshot service?
A. Tự chạy lại lệnh sau mỗi lần lệnh kết thúc.
B. Giữ unit ở trạng thái active sau khi lệnh kết thúc.
C. Giữ process sống dù chương trình đã gọi exit.
D. Ngăn systemd gửi tín hiệu dừng tới process.
Đáp án đúng: B

Câu 11. `ExecStart=` trong systemd unit được thực thi như thế nào?
A. Chạy trong shell đăng nhập của User= được chỉ định.
B. Luôn chạy qua /bin/bash và mở rộng shell variables.
C. Chạy executable trực tiếp, không tự mở shell.
D. Được phân tích như một câu lệnh PowerShell.
Đáp án đúng: C

Câu 12. Muốn service chạy bằng tài khoản chuyên biệt, cấu hình nào phù hợp?
A. Đặt UID= và GID= trong section [Unit].
B. Đặt Account= và Password= trong section [Service].
C. Đặt Owner= và Mode= trong section [Install].
D. Đặt User= và Group= trong section [Service].
Đáp án đúng: D

Câu 13. `Restart=on-failure` thường yêu cầu systemd làm gì?
A. Khởi động lại sau mọi lần stop có chủ đích.
B. Chỉ restart khi máy chủ khởi động lại.
C. Khởi động lại sau exit lỗi hoặc kết thúc bất thường.
D. Không restart nếu process thoát với mã khác không.
Đáp án đúng: C

Câu 14. Vai trò của `RestartSec=` trong unit file là gì?
A. Đặt timeout để systemd chờ lệnh reload hoàn tất.
B. Giới hạn tổng số lần service được restart.
C. Đặt thời gian tối đa service được phép khởi động.
D. Đặt khoảng chờ trước lần restart tiếp theo.
Đáp án đúng: D

Câu 15. Nếu service liên tục crash và chạm giới hạn khởi động, nên kiểm tra gì?
A. WantedBy và DefaultDependencies.
B. TimeoutStopSec và KillMode của unit service.
C. RestartSec cùng WatchdogSec trong unit.
D. StartLimitIntervalSec và StartLimitBurst.
Đáp án đúng: D

Câu 16. systemd target thường được dùng để làm gì?
A. Nhóm các unit thành một trạng thái vận hành.
B. Lưu trạng thái process và mã thoát cuối cùng.
C. Định nghĩa lệnh thực thi cho một service daemon.
D. Đặt tài khoản và quyền truy cập cho service.
Đáp án đúng: A

Câu 17. `WantedBy=multi-user.target` trong [Install] thường có ý nghĩa nào?
A. Enable tạo liên kết để target kéo service vào boot.
B. Target sẽ tự reload service mỗi khi cấu hình đổi.
C. Service luôn khởi động trước khi target được active.
D. Service trở thành dependency bắt buộc của mọi target.
Đáp án đúng: A

Câu 18. systemd timer unit thường được ghép với unit loại nào?
A. Mount unit lưu kết quả của tác vụ định kỳ.
B. Socket unit giữ kết nối cho đến giờ chạy.
C. Service unit được kích hoạt theo lịch timer.
D. Target unit chứa danh sách lịch cron.
Đáp án đúng: C

Câu 19. `Persistent=true` trong timer với `OnCalendar=` hỗ trợ điều gì?
A. Giữ process của service chạy liên tục giữa hai lần lịch.
B. Chạy service nhiều lần để bù mọi lịch bị trễ.
C. Lưu stdout của tác vụ vào journal lâu dài.
D. Bù lần chạy đã lỡ khi timer không hoạt động.
Đáp án đúng: D

Câu 20. Lệnh nào lọc journal theo một service systemd cụ thể?
A. journalctl -u app.service.
B. dmesg --unit app.service.
C. journalctl --pid=systemd app.service.
D. systemctl logs app.service.
Đáp án đúng: A

Câu 21. Khi `systemctl status` báo service failed, bước chẩn đoán hữu ích nào tiếp theo?
A. Xóa unit file rồi cài lại systemd manager.
B. Đọc journal của unit và kiểm tra exit status.
C. Tăng RestartSec trước khi kiểm tra log.
D. Enable lại service để ghi đè nguyên nhân lỗi.
Đáp án đúng: B

Câu 22. `EnvironmentFile=` trong unit service thường dùng để làm gì?
A. Chạy lệnh shell để tạo biến mới mỗi giây.
B. Đặt biến môi trường cho toàn bộ systemd manager.
C. Lưu secret đã mã hóa trong journal của service.
D. Nạp biến môi trường từ file cho process service.
Đáp án đúng: D

Câu 23. Directive `NoNewPrivileges=yes` nhằm mục tiêu nào?
A. Ngăn process có thêm privilege qua exec.
B. Tự cấp capability cần thiết khi service khởi động.
C. Chạy service với quyền root dù User đã đặt.
D. Cho phép service bỏ qua file permission của Linux.
Đáp án đúng: A

Câu 24. `ProtectSystem=strict` thường ảnh hưởng tới filesystem như thế nào?
A. Ẩn mọi mount point khỏi process service.
B. Làm phần lớn filesystem chỉ đọc với service.
C. Chỉ cho phép service đọc thư mục /tmp.
D. Cho service quyền ghi toàn bộ filesystem host.
Đáp án đúng: B

Câu 25. `RuntimeDirectory=` trong service unit giúp systemd làm gì?
A. Tạo thư mục dữ liệu bền vững dưới /var/lib.
B. Tạo thư mục runtime dưới /run và quản lý vòng đời.
C. Chuyển working directory sang thư mục chứa executable.
D. Tạo thư mục log riêng trong journal namespace.
Đáp án đúng: B

Câu 26. Windows Service Control Manager (SCM) chịu trách nhiệm chính nào?
A. Lưu event log của mọi ứng dụng desktop.
B. Lập lịch mọi thread của ứng dụng lên CPU.
C. Quản lý package update và driver kernel.
D. Cài đặt, cấu hình và điều khiển Windows services.
Đáp án đúng: D

Câu 27. Trên Windows, service start type Automatic có ý nghĩa nào?
A. Service chỉ chạy khi được gọi qua named pipe.
B. Service bị vô hiệu hóa cho đến khi admin enable.
C. SCM khởi động service trong quá trình boot.
D. Service chỉ chạy khi người dùng đăng nhập.
Đáp án đúng: C

Câu 28. Windows service đặt kiểu Disabled sẽ có hành vi nào?
A. Tự khởi động chậm sau các Automatic services.
B. Chỉ được khởi động bởi tài khoản LocalSystem.
C. Chạy một lần rồi tự chuyển sang Manual.
D. Không khởi động được cho tới khi được enable.
Đáp án đúng: D

Câu 29. Delayed Automatic Start trên Windows được dùng để làm gì?
A. Tự trì hoãn mọi lần restart sau crash.
B. Chờ người dùng đăng nhập rồi mới chạy service.
C. Khởi động sau nhóm Automatic thông thường.
D. Chỉ khởi động sau khi một service phụ thuộc dừng.
Đáp án đúng: C

Câu 30. Windows service dependency thường ảnh hưởng điều gì?
A. Dependency chỉ xác định thứ tự dừng, không ảnh hưởng start.
B. SCM khởi động dependency trước service phụ thuộc.
C. Dependency buộc hai service chạy trong cùng process.
D. SCM bỏ qua dependency nếu service chạy dưới LocalSystem.
Đáp án đúng: B

Câu 31. Tài khoản LocalSystem phù hợp khi nào?
A. Service chỉ cần đọc một thư mục dữ liệu riêng.
B. Service cần truy cập mạng bằng danh tính người dùng.
C. Dành cho service cần quyền hệ thống rất cao.
D. Service cần hiển thị cửa sổ trong phiên desktop.
Đáp án đúng: C

Câu 32. NetworkService thường có đặc điểm nào?
A. Không thể truy cập tài nguyên mạng dưới bất kỳ hình thức nào.
B. Quyền cục bộ ngang LocalSystem và không có danh tính mạng.
C. Quyền cục bộ hạn chế, dùng danh tính máy trên mạng.
D. Chỉ được chạy service trong phiên desktop người dùng.
Đáp án đúng: C

Câu 33. PowerShell cmdlet nào thường dùng để xem Windows services?
A. Get-Service liệt kê services.
B. Get-WinEvent -Service.
C. Get-ScheduledTask -Service.
D. Get-Process -Service.
Đáp án đúng: A

Câu 34. Muốn xem log System liên quan đến service trên Windows, công cụ nào phù hợp?
A. Dùng Get-Service với tham số -LogPath.
B. Dùng Get-WinEvent hoặc Event Viewer.
C. sc.exe queryex với tham số -EventLog.
D. Get-Process và lọc theo tên service.
Đáp án đúng: B

Câu 35. Lệnh `sc.exe query` chủ yếu dùng để làm gì?
A. Thay đổi tài khoản đăng nhập của service.
B. Xem trạng thái hiện tại của service.
C. Sửa file cấu hình service rồi tự restart.
D. Đọc event log của Service Control Manager.
Đáp án đúng: B

Câu 36. Windows service recovery actions có thể cấu hình để làm gì?
A. Tăng quyền tài khoản sau mỗi lần crash.
B. Xóa event log cũ khi service khởi động lại.
C. Tự sửa mọi lỗi ứng dụng trước khi restart.
D. Chọn hành động sau lần service thất bại.
Đáp án đúng: D

Câu 37. Trong macOS, launchd quản lý loại thành phần nào?
A. Chỉ kernel extensions được nạp khi boot.
B. Chỉ ứng dụng GUI đang hiển thị trên Dock.
C. Chỉ scheduled tasks chạy bên trong Terminal.
D. Quản lý daemon hệ thống và agent người dùng.
Đáp án đúng: D

Câu 38. LaunchDaemon khác LaunchAgent chủ yếu ở phạm vi chạy nào?
A. Agent quản lý kernel task; daemon quản lý app menu.
B. Daemon chỉ chạy sau login; agent chạy trước boot.
C. Daemon chạy ở cấp hệ thống; agent gắn với phiên người dùng.
D. Cả hai đều chỉ chạy trong phiên GUI của root.
Đáp án đúng: C

Câu 39. Trong launchd property list, `ProgramArguments` thường mô tả gì?
A. Executable cùng danh sách đối số khi launch.
B. Tên tài khoản, nhóm và quyền filesystem của process.
C. Đường dẫn log mà launchd phải rotate hàng ngày.
D. Điều kiện KeepAlive và lịch khởi động định kỳ.
Đáp án đúng: A

Câu 40. Lệnh `launchctl bootstrap` thường dùng để làm gì?
A. Buộc dừng job và xóa file plist khỏi đĩa.
B. Hiển thị log của mọi process thuộc một user.
C. Nạp job vào launchd domain được chỉ định.
D. Sửa nhãn Label và tự tạo executable cho job.
Đáp án đúng: C
