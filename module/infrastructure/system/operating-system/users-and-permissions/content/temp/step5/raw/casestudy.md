Một ứng dụng Linux chạy dưới tài khoản service riêng nhưng file cấu hình do root tạo với mode 0600; service không đọc được file và trả lỗi Permission denied dù thư mục chứa file có quyền đọc cho mọi người.
Quản trị viên thêm tài khoản kỹ thuật vào group deploy nhưng tiến trình đang chạy chưa nhận supplementary group mới; lệnh id trong shell mới cho thấy quyền đã cập nhật còn service cũ vẫn bị từ chối truy cập.
Một user có UID 1001 trên máy chủ mới nhưng thư mục dữ liệu được khôi phục từ máy cũ với owner UID 1002; tên tài khoản hiển thị gần giống nhau nhưng kernel kiểm tra UID số và chặn ghi file.
Hai tài khoản Linux có cùng tên ở hai máy nhưng UID/GID khác nhau trên NFS; file tạo từ máy này hiện owner là một user khác ở máy kia và quyền truy cập không nhất quán.
Ứng dụng cần đọc file qua nhiều thư mục cha; file có mode 0644 nhưng một thư mục cha thiếu quyền execute cho service account nên open() vẫn trả Permission denied.
Một thư mục cho phép group đọc nhưng không có quyền execute; thành viên group nhìn thấy tên file bằng một số công cụ nhưng không thể traverse hoặc mở file bên trong.
Quản trị viên cấp chmod 777 để xử lý lỗi ghi log; dịch vụ hoạt động trở lại nhưng mọi user cục bộ đều có thể sửa hoặc thay thế log, tạo rủi ro giả mạo dữ liệu kiểm toán.
Ứng dụng tạo file bí mật với mode 0666; umask của systemd service không được đặt nên file có quyền đọc rộng hơn dự kiến dù shell tương tác tạo file an toàn.
Nhóm vận hành thay umask trong profile người dùng nhưng service khởi chạy bằng systemd không đọc profile đó; file mới vẫn được tạo với quyền cũ.
Một thư mục chia sẻ có setgid bit nhưng nhóm tạo file qua ứng dụng không nhận group kế thừa như kỳ vọng do thư mục được mount với hành vi hoặc quyền khác trên filesystem.
Thư mục upload có sticky bit nhưng đội phát triển tưởng mọi thành viên group đều có thể xóa file của nhau; thao tác xóa thất bại vì chỉ owner file, owner thư mục hoặc root được phép.
Một binary cần quyền setuid để thực hiện thao tác đặc quyền nhưng file nằm trên filesystem mount với tùy chọn nosuid; chương trình chạy dưới UID thường và không có quyền cần thiết.
Ứng dụng gọi script có setuid bit trên Linux nhưng kernel bỏ qua setuid cho script thông thường; nhóm nhầm rằng quyền owner của script sẽ tự nâng đặc quyền cho interpreter.
Quản trị viên cấp sudo ALL cho tài khoản hỗ trợ để họ restart một service; tài khoản có thể chạy shell root và đọc mọi file thay vì chỉ được phép thao tác dịch vụ cần thiết.
File sudoers được chỉnh sửa sai cú pháp; sudo từ chối nạp cấu hình và đội vận hành có nguy cơ mất đường truy cập quản trị qua tài khoản được ủy quyền.
Nhóm cấu hình sudo command allowlist cho phép chạy một script root; script nhận tham số tùy ý và có thể ghi file ngoài thư mục dự kiến, làm quyền giới hạn trở thành đường nâng đặc quyền.
Một tài khoản có quyền sudo chạy lệnh qua shell script có biến môi trường do người dùng kiểm soát; môi trường không được làm sạch khiến lệnh đặc quyền nạp binary hoặc cấu hình ngoài ý muốn.
Quản trị viên thêm user vào group wheel nhưng PAM hoặc sudoers trên máy đó chỉ cho phép group sudo; user đăng nhập được nhưng không thể thực hiện lệnh quản trị.
Ứng dụng cần bind cổng thấp nhưng nhóm chạy toàn bộ process bằng root; Linux capability CAP_NET_BIND_SERVICE có thể giới hạn đặc quyền cần cấp mà không cần UID 0.
Một service chạy root chỉ để đọc một thiết bị; sau khi chuyển sang user riêng, thiết bị vẫn thuộc group khác và service bị Permission denied vì thiếu quyền thiết bị hoặc capability phù hợp.
File được cấp quyền ACL cho nhóm support nhưng ACL mask chỉ cho phép đọc; lệnh getfacl hiển thị rwx ở entry nhóm khiến người vận hành tưởng quyền ghi đã có hiệu lực.
Quản trị viên thêm named user ACL cho một thư mục nhưng quên default ACL; file mới do ứng dụng tạo không kế thừa quyền dự kiến và nhóm hỗ trợ không đọc được.
Mode bits của file thay đổi sau khi setfacl; người vận hành không nhận ra group mode hiển thị thực tế phản ánh ACL mask và kết luận sai về quyền của group owner.
Một ACL entry cho phép user đọc file nhưng một ACL entry khác bị mask loại bỏ quyền; getfacl có chú thích effective khác với quyền mà nhóm tưởng đã cấp.
Ứng dụng chạy trong container với UID 10001 nhưng bind mount trên host thuộc root:root mode 0750; process trong container không thể ghi dữ liệu dù bên trong image thư mục có quyền ghi.
Container rootless dùng user namespace mapping UID; file tạo trong container có owner UID đã ánh xạ khác trên host và thao tác backup/restore bằng user host gặp Permission denied.
Pod Kubernetes đặt runAsUser và runAsGroup nhưng volume được mount với group ownership khác; container process không ghi được dữ liệu dù securityContext đã cấu hình UID.
Nhóm bật fsGroup cho pod để cấp quyền volume nhưng storage driver không áp dụng ownership change như mong đợi; ứng dụng vẫn bị từ chối ghi khi mount persistent volume.
Một container chạy privileged để khắc phục lỗi đọc thiết bị; thay đổi này cấp quyền rộng trên host và vượt quá nhu cầu truy cập một device cụ thể.
Service systemd chạy với User=app nhưng thư mục StateDirectory hoặc RuntimeDirectory có owner không khớp; service khởi động được rồi thất bại khi tạo socket hoặc file trạng thái.
Một systemd unit dùng ProtectSystem=strict và ReadWritePaths chưa khai báo thư mục upload; ứng dụng có quyền POSIX ghi trên host nhưng sandbox của systemd vẫn chặn thao tác.
Service bị lỗi khi đọc secret sau khi bật DynamicUser; UID được cấp động và file secret có ownership tĩnh nên không tương thích với danh tính runtime.
Quản trị viên đổi owner thư mục bằng chown nhưng service vẫn không ghi được vì ACL, SELinux policy hoặc mount option bổ sung đang giới hạn truy cập.
Trên Linux, ls -l cho thấy quyền file hợp lệ nhưng SELinux audit log ghi AVC denial; đội trực chỉ chạy chmod mà không xem security context và policy.
Ứng dụng bị AppArmor chặn đọc đường dẫn mới sau khi chuyển thư mục dữ liệu; Unix mode bits vẫn cho phép nhưng profile confinement từ chối truy cập.
Một NFS export bật root_squash; process root trên client tạo file nhưng server ánh xạ root thành anonymous UID, khiến owner và quyền sau đó khác kỳ vọng.
Ứng dụng truy cập CIFS/SMB share từ Linux với UID/GID mapping không nhất quán; quyền hiển thị cục bộ khác ACL trên Windows server và thao tác ghi bị từ chối.
Windows service chạy dưới LocalSystem nhưng cần truy cập file share trên máy khác; danh tính LocalSystem không có credential mạng phù hợp và SMB trả Access Denied.
Một Windows service chạy dưới tài khoản domain đã bị đổi mật khẩu; service vẫn dùng credential cũ và không khởi động được sau lần restart kế tiếp.
Nhóm tạo Windows service bằng tài khoản người dùng thường nhưng không cấp Log on as a service; Service Control Manager từ chối khởi động dù tài khoản có quyền đọc file cấu hình.
Windows UAC khiến tiến trình chạy trong phiên đăng nhập của administrator nhưng token chỉ có quyền lọc; thao tác ghi vào thư mục hệ thống bị từ chối cho tới khi chạy với elevation phù hợp.
Ứng dụng Windows được khởi chạy bằng Run as administrator nhưng vẫn không truy cập được file share; elevated token cục bộ không tự cấp quyền trên tài nguyên mạng.
Danh sách DACL của file NTFS cho phép nhóm Developers Modify nhưng một explicit Deny trên user cụ thể được ưu tiên; người dùng thuộc cả hai nhóm vẫn không thể sửa file.
Folder NTFS có quyền kế thừa nhưng file con tắt inheritance và giữ ACL cũ; người dùng mới được thêm vào group cha không truy cập được file con.
Quản trị viên cấp quyền trên share SMB nhưng NTFS ACL ở thư mục đích chỉ Read; quyền hiệu lực là phần hạn chế hơn giữa share permission và NTFS permission.
Người dùng có quyền NTFS Modify nhưng share permission chỉ Read; truy cập qua mạng không thể ghi dù truy cập trực tiếp trên máy chủ có thể sửa file.
Một Windows folder được cấp quyền cho nhóm qua nested Active Directory group; token đăng nhập chưa được làm mới nên người dùng cần logoff/logon để nhận membership mới.
Quản trị viên xóa user khỏi nhóm AD nhưng access token của phiên đăng nhập hiện tại vẫn chứa SID nhóm; quyền cũ còn hiệu lực cho tới khi token hoặc phiên được làm mới.
Một ứng dụng Windows chạy impersonation theo người dùng cuối; khi thread quên revert impersonation, các thao tác tiếp theo dùng sai security context và truy cập tài nguyên bị từ chối.
Service account được cấp quyền NTFS qua SID cũ sau khi domain account bị tạo lại; tài khoản mới có tên giống nhưng SID khác nên ACL không còn áp dụng.
Windows ACL cho phép đọc file nhưng không cấp quyền traverse trên một thư mục cha; người dùng nhận Access Denied dù quyền file đích nhìn có vẻ đầy đủ.
Nhóm dùng icacls để thay ACL thư mục đệ quy nhưng tùy chọn inheritance và propagation flags không như dự kiến; một số file con giữ quyền cũ hoặc nhận quyền quá rộng.
Đội bật auditing SACL cho thao tác xóa file nhưng không cấu hình audit policy phù hợp; Security log không có sự kiện mong muốn dù ACL SACL đã được thêm.
Windows Security log ghi nhiều sự kiện truy cập thất bại nhưng không có Object Access auditing; nhóm không thể xác định tài khoản nào đã thử đọc file nhạy cảm.
Trên Linux, auditd không theo dõi đường dẫn chứa file cấu hình quan trọng; khi file bị đọc bởi tài khoản lạ, đội an ninh không có bằng chứng trong audit log.
Một service bị Permission denied khi mở file nhưng nhóm chỉ xem log ứng dụng; strace cho thấy syscall openat trả EACCES và đường dẫn thực tế khác với cấu hình mà nhóm kiểm tra.
Windows service trả Access Denied khi mở registry key; nhóm kiểm tra NTFS ACL của thư mục cài đặt mà không xem quyền trên registry object.
Ứng dụng không thể tạo named pipe trên Windows vì ACL của pipe chỉ cho phép SYSTEM; service client chạy bằng domain service account và không có quyền kết nối.
Tiến trình Linux không thể gửi signal tới process khác dù biết PID; UID của tiến trình gửi không khớp owner và không có capability phù hợp để vượt kiểm tra quyền.
Một ứng dụng Java chạy với user riêng cần đọc log do sidecar tạo; file log có group đúng nhưng mode không cho group read và thư mục cha không cho traverse.
Đội vận hành sửa permission trên thư mục hiện tại nhưng file mới tiếp tục sai quyền do default ACL, umask hoặc ứng dụng tạo file với mode riêng; lỗi tái diễn sau mỗi lần deploy.
Nhóm áp dụng least privilege cho tài khoản triển khai nhưng pipeline cần restart service và đọc log; quyền được chia nhỏ không đầy đủ khiến deploy thất bại, trong khi cấp sudo toàn quyền lại quá rộng.
Một tài khoản quản trị dùng chung cho nhiều kỹ sư; audit log chỉ ghi cùng một UID/SID nên không thể quy trách nhiệm cá nhân khi có thay đổi quyền hoặc truy cập dữ liệu.
Quyền đọc một thư mục production được cấp tạm cho nhân viên xử lý sự cố nhưng không có ngày hết hạn; nhiều tháng sau tài khoản vẫn truy cập dữ liệu ngoài phạm vi công việc.
Đội bảo mật rà soát thành viên group nhưng không kiểm tra nested groups, ACL và sudoers; tài khoản tưởng không có quyền vẫn truy cập được tài nguyên thông qua đường cấp quyền gián tiếp.
