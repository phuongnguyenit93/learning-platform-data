1. Sau khi thêm user Linux vào group `deploy`, service đang chạy vẫn bị từ chối truy cập. Cách xử lý phù hợp là gì?
A. Chạy chmod để process đang chạy tự nạp lại group membership mới.
B. Đổi umask của unit để kernel cập nhật group credentials đang dùng.
C. Dùng setfacl vì ACL có thể thay group credentials của process cũ.
D. Restart service để process mới nhận supplementary group vừa thêm.
Đáp án đúng: D

2. Trong quyền POSIX, bit nào trên thư mục cho phép process traverse thư mục khi phân giải đường dẫn?
A. Quyền read (`r`) cho phép traverse dù thư mục không có execute.
B. Quyền write (`w`) cho phép traverse nếu process sở hữu thư mục.
C. Quyền execute (`x`) cho phép traverse thư mục trong path lookup.
D. Sticky bit cấp quyền traverse cho mọi thành viên của group thư mục.
Đáp án đúng: C

3. File được tạo bằng mode 0666 nhưng kết quả là 0640. Cơ chế nào giải thích việc loại bỏ các bit quyền?
A. Setgid trên thư mục cha tự đặt mode file thành 0640 khi tạo.
B. Umask xóa các bit khỏi mode mà ứng dụng yêu cầu khi tạo file.
C. ACL mask luôn thay umask và đặt quyền đọc ghi cho group owner.
D. Sticky bit loại bỏ quyền của others trên mọi file mới được tạo.
Đáp án đúng: B

4. Thư mục dự án cần cấp quyền mặc định cho group support trên file tạo mới. Nên cấu hình gì?
A. Đặt default ACL trên thư mục dự án để file mới kế thừa quyền.
B. Đặt access ACL trên thư mục để file mới tự nhận cùng ACL.
C. Đặt sticky bit để file mới được sở hữu bởi group support.
D. Đặt umask của root để thay đổi quyền tạo file của mọi user.
Đáp án đúng: A

5. `getfacl` cho thấy named group có `rwx`, nhưng quyền hiệu lực chỉ là `r-x`. Thành phần nào cần kiểm tra?
A. Default ACL ghi đè quyền truy cập hiện tại của mọi file con.
B. Sticky bit loại bỏ quyền ghi của named group trên file hiện tại.
C. Owner UID thay đổi quyền hiệu lực của tất cả group ACL entries.
D. ACL mask giới hạn quyền hiệu lực của named user và group entries.
Đáp án đúng: D

6. Nhiều user tạo file trong thư mục chia sẻ và cần file mới thuộc group dự án. Cấu hình nào phù hợp?
A. Đặt setuid bit trên thư mục để owner của thư mục được kế thừa.
B. Đặt sticky bit để file mới luôn thuộc group của người tạo file.
C. Đặt setgid bit trên thư mục chia sẻ để file mới kế thừa group.
D. Đặt noexec trên mount để file mới nhận group của thư mục cha.
Đáp án đúng: C

7. Trong thư mục có sticky bit, user A không thể xóa file do user B tạo dù có quyền ghi thư mục. Vì sao?
A. Sticky bit chỉ cho phép owner thư mục đọc file do thành viên tạo.
B. Sticky bit giới hạn xóa entry cho owner file, owner thư mục hoặc root.
C. Sticky bit loại bỏ quyền write của group sau khi file được tạo.
D. Sticky bit yêu cầu mọi file con phải có cùng UID với thư mục.
Đáp án đúng: B

8. Quản trị viên cần sửa `/etc/sudoers` và kiểm tra cú pháp trước khi lưu. Công cụ nào phù hợp?
A. Dùng chmod 777 rồi sửa bằng editor thường và kiểm tra sau khi lưu.
B. Dùng `visudo` để sửa sudoers và kiểm tra cú pháp trước khi lưu.
C. Dùng shell redirect để sudo tự khôi phục nếu cú pháp không hợp lệ.
D. Đổi owner sang user thường để editor tự kiểm tra quyền sudoers.
Đáp án đúng: B

9. Sudoers cho phép chạy script root để restart service. Điều kiện nào giúp tránh biến script thành đường nâng quyền?
A. Script và thư mục cha do root sở hữu, user thường không thể sửa.
B. Đặt script trong thư mục user ghi được để cập nhật nhanh sau deploy.
C. Cho script nhận tham số shell tùy ý rồi chuyển nguyên vẹn cho root.
D. Cho phép chạy shell tương tác để script tự chọn lệnh cần thiết.
Đáp án đúng: A

10. Daemon Linux chỉ cần bind cổng TCP 443. Cách cấp quyền nào hẹp hơn chạy toàn bộ daemon bằng root?
A. Cấp toàn bộ Linux capabilities và giữ UID root trong suốt vòng đời.
B. Bật setuid root cho mọi binary mà daemon có thể gọi tới.
C. Thêm service account vào group root để cho phép bind cổng thấp.
D. Cấp capability `CAP_NET_BIND_SERVICE` cho executable hoặc service.
Đáp án đúng: D

11. Binary setuid chạy trên filesystem mount với tùy chọn `nosuid`. Hành vi nào được mong đợi?
A. Kernel bỏ qua quyền execute nhưng vẫn đổi effective UID khi chạy.
B. Kernel bỏ qua setuid và setgid của file trên mount đó.
C. Kernel tự cấp capability đầy đủ cho binary để thay thế setuid.
D. Kernel chuyển file sang filesystem khác trước khi thực thi binary.
Đáp án đúng: B

12. POSIX mode bits cho phép đọc file nhưng SELinux vẫn ghi AVC denial. Hướng điều tra nào phù hợp?
A. Kiểm tra SELinux context và policy của process cùng file đích.
B. Chỉ tăng mode file lên 0777 để bỏ qua policy SELinux hiện tại.
C. Tắt auditd vì AVC denial thường do audit daemon chặn truy cập.
D. Đổi UID service thành root vì SELinux chỉ áp dụng cho user thường.
Đáp án đúng: A

13. Service Linux bị AppArmor chặn đọc thư mục mới dù POSIX permissions đã cho phép. Cần cập nhật gì?
A. ACL mask cần thêm execute cho mọi user trên filesystem đang dùng.
B. Cập nhật profile AppArmor cho đường dẫn mới.
C. Sudoers cần cấp quyền đọc thư mục cho process đang chạy service.
D. Umask cần đổi vì AppArmor kiểm tra mode khi file được tạo mới.
Đáp án đúng: B

14. Tài khoản Windows đổi display name nhưng vẫn là cùng security principal. Định danh nào giữ nguyên?
A. Tên đăng nhập mới thay SID trong mọi access token đang tồn tại.
B. Tên thư mục profile được dùng làm định danh trong DACL của file.
C. Password hash trở thành định danh duy nhất cho principal Windows.
D. SID giữ định danh principal dù display name đổi.
Đáp án đúng: D

15. Trong security descriptor của file NTFS, DACL và SACL có vai trò nào?
A. DACL kiểm soát truy cập; SACL chọn sự kiện trên object cần audit.
B. DACL lưu sự kiện audit; SACL quyết định quyền đọc và ghi file.
C. DACL xác định owner; SACL lưu SID của các group đăng nhập.
D. DACL cấp quyền share SMB; SACL đồng bộ quyền với Linux ACL.
Đáp án đúng: A

16. DACL theo thứ tự canonical có explicit Deny Write đứng trước ACE Allow áp dụng. Kết quả access check là gì?
A. Yêu cầu ghi được phép vì Allow từ group luôn được ưu tiên hơn.
B. Yêu cầu ghi được phép nếu user là owner của file NTFS đó.
C. Yêu cầu ghi bị từ chối vì explicit Deny ACE áp dụng trước Allow.
D. Windows bỏ qua Deny ACE khi user thuộc nhiều group khác nhau.
Đáp án đúng: C

17. File con NTFS không nhận quyền mới từ thư mục cha dù group đã được thêm vào ACL cha. Điều gì có thể giải thích?
A. SID thư mục cha tự động ghi đè mọi ACE được đặt trên file con.
B. File con đã tắt inheritance nên không nhận ACE mới từ thư mục cha.
C. UAC ngăn quyền kế thừa từ thư mục xuống file trong user profile.
D. Share permission thay thế inheritance NTFS trên cùng một volume.
Đáp án đúng: B

18. User truy cập file qua SMB. Share permission cho phép Read nhưng NTFS ACL cho phép Modify. Quyền hiệu lực qua share là gì?
A. Modify, vì NTFS ACL luôn ghi đè share permission khi truy cập mạng.
B. Full Control, vì quyền share và NTFS được cộng lại với nhau.
C. Access Denied, vì share và NTFS ACL phải giống hệt nhau.
D. Read có hiệu lực vì SMB áp dụng mức hạn chế hơn giữa hai lớp quyền.
Đáp án đúng: D

19. Administrator đăng nhập Windows nhưng ứng dụng vẫn bị từ chối ghi thư mục hệ thống. Cơ chế nào cần kiểm tra?
A. UAC có thể giữ process bằng filtered token nếu chưa được elevate.
B. SID administrator bị thay đổi mỗi lần mở một ứng dụng Windows.
C. SACL tự động chặn thao tác ghi của mọi process chưa audit.
D. NTFS bỏ qua DACL khi user thuộc nhóm Administrators cục bộ.
Đáp án đúng: A

20. Windows Service không khởi động dưới tài khoản domain dù tài khoản đọc được file cấu hình. Quyền nào có thể còn thiếu?
A. Log on as a service, một user right riêng cho service logon.
B. Modify trên thư mục Windows để Service Control Manager tạo process.
C. Owner trên registry hive vì mọi service cần sở hữu registry key.
D. Interactive logon để service có thể tạo desktop session riêng.
Đáp án đúng: A

21. Windows service cần truy cập tài nguyên domain và tránh quản lý mật khẩu thủ công. Danh tính nào phù hợp?
A. LocalSystem vì tài khoản này luôn có quyền của mọi domain user.
B. Guest account vì SMB tự cấp quyền theo tên máy chạy service.
C. gMSA để domain tự quản lý mật khẩu service account.
D. Local Administrator dùng chung để không phải gia hạn credential.
Đáp án đúng: C

22. SACL đã cấu hình audit thao tác xóa file nhưng Security log không có sự kiện mong muốn. Cần kiểm tra gì?
A. Kiểm tra audit policy File System trong Object Access đã bật chưa.
B. DACL có cấp quyền Delete cho user thực hiện thao tác hay chưa.
C. Owner của file có trùng tài khoản đang đăng nhập Windows không.
D. Share permission có cho phép truy cập file từ mạng hay chưa.
Đáp án đúng: A

23. User vừa được thêm vào group AD có quyền truy cập share nhưng phiên Windows hiện tại vẫn Access Denied. Cách xử lý nào thường cần thiết?
A. Refresh Explorer để token Windows cập nhật theo mỗi lần mở folder.
B. Xóa SMB credential cache để group SID được thêm vào token cũ.
C. Đổi tên user để Windows tạo lại membership của các group.
D. Đăng nhập lại để token nhận group SID mới từ Active Directory.
Đáp án đúng: D

24. Windows service chạy dưới LocalSystem cần truy cập share trong domain trên máy domain-joined. Danh tính mạng nào thường được dùng?
A. SID của Interactive User đang mở cửa sổ Services trên máy đó.
B. Guest account cục bộ được Windows bật cho mọi SMB share mặc định.
C. LocalSystem dùng computer account của máy khi truy cập mạng domain.
D. SID ngẫu nhiên do Service Control Manager tạo cho mỗi kết nối.
Đáp án đúng: C

25. Process Linux biết PID process khác nhưng `kill()` trả EPERM. Điều kiện nào có thể giải thích?
A. Kernel kiểm tra UID phù hợp hoặc `CAP_KILL` trước khi gửi signal.
B. Process đích không có execute trên thư mục chứa binary đang chạy.
C. Process gửi thiếu read trên `/proc` nên kernel cấm mọi signal.
D. Process đích đang sleeping nên không thể nhận signal từ kernel.
Đáp án đúng: A

26. Service báo Permission denied khi mở `/srv/app/config.yml`. Lệnh nào xác định thư mục cha nào chặn traverse?
A. Dùng `df -h` để xác định owner của từng thư mục cha trên disk.
B. Dùng `ps aux` để in ACL của file và mọi thư mục cha.
C. Dùng `netstat` để kiểm tra quyền truy cập trên filesystem path.
D. Dùng `namei -l` để xem quyền trên từng thành phần đường dẫn.
Đáp án đúng: D

27. `strace` cho thấy `openat()` trả `EACCES` khi ứng dụng mở file. Điều này chứng minh điều gì?
A. File chắc chắn không tồn tại và kernel đã trả về sai loại lỗi.
B. Kernel trả EACCES do kiểm tra quyền thất bại.
C. Filesystem đã hết dung lượng nên kernel từ chối mở file đó.
D. Process không có socket mạng để truy cập đường dẫn file cục bộ.
Đáp án đúng: B

28. Muốn ghi nhận process nào truy cập file nhạy cảm trên Linux, công cụ nào phù hợp?
A. Cron chạy `ls -l` định kỳ để suy ra process đã đọc file.
B. Sudoers ghi mọi lần user mở file mà không cần audit rule.
C. Dùng auditd rule để ghi nhận truy cập vào file hoặc syscall liên quan.
D. Umask lưu lịch sử process tạo hoặc đọc file nhạy cảm.
Đáp án đúng: C

29. Systemd service cần chạy bằng user `app`, group `logs` và thêm group `metrics`. Cấu hình nào phù hợp?
A. Đặt `User`, `Group` và `SupplementaryGroups` trong unit.
B. Dùng `User=root`, `Group=app` và `UMask=metrics` trong unit.
C. Dùng `DynamicUser=yes` cùng `PrivateUsers=logs` để thêm group.
D. Dùng `CapabilityBoundingSet=app logs metrics` để gán identity.
Đáp án đúng: A

30. Service có quyền POSIX ghi `/var/lib/app` nhưng bị chặn sau khi bật `ProtectSystem=strict`. Cấu hình nào phù hợp?
A. Tăng mode bits thư mục lên 0777 để vượt sandbox systemd.
B. Bỏ `User=` để service chạy root và tự ghi mọi đường dẫn.
C. Thêm thư mục vào `SupplementaryGroups=` để bỏ giới hạn mount.
D. Khai báo đường dẫn cần ghi trong `ReadWritePaths=` của unit.
Đáp án đúng: D

31. Container chạy UID 10001 nhưng bind mount trên host thuộc root:root mode 0750. Vì sao ứng dụng có thể không ghi được?
A. Quyền ghi trong image luôn ghi đè owner và mode của bind mount.
B. Container runtime tự chuyển UID 10001 thành root khi ghi volume.
C. Dockerfile `WORKDIR` tự cấp quyền ghi cho mọi bind mount.
D. Quyền host path được kiểm tra theo UID/GID của process.
Đáp án đúng: D

32. Container rootless bật user namespace. UID 0 bên trong container thường được ánh xạ thế nào?
A. Luôn tương ứng UID 0 trên host vì root trong container là root thật.
B. Ánh xạ tới UID người dùng mở terminal bất kể cấu hình namespace.
C. Ánh xạ tới UID không đặc quyền trên host theo user namespace map.
D. Không có UID trên host vì user namespace chỉ ánh xạ group ID.
Đáp án đúng: C

33. Pod Kubernetes đặt `runAsUser` nhưng process vẫn không ghi được volume cần group access. Thuộc tính nào có thể bổ sung group cho volume?
A. `runAsNonRoot` tự đổi owner volume thành UID của process đang chạy.
B. `fsGroup` cấp group access cho volume nếu driver hỗ trợ.
C. `readOnlyRootFilesystem` cấp quyền ghi cho persistent volume đã mount.
D. `allowPrivilegeEscalation` thêm group ID vào access token của process.
Đáp án đúng: B

34. Ứng dụng chạy non-root trong Docker image cần ghi vào thư mục dữ liệu. Cặp cấu hình nào cần phối hợp?
A. Đặt `USER root` rồi đổi permission sau khi container khởi động xong.
B. Đặt `WORKDIR` vào volume vì Docker tự cấp quyền ghi cho thư mục.
C. Đặt `USER` và quyền owner/group phù hợp trên volume.
D. Đặt `EXPOSE` cho cổng ứng dụng để runtime cấp quyền ghi file.
Đáp án đúng: C

35. User Windows không truy cập được file dù thuộc nhiều group. Công cụ nào đánh giá quyền thực tế trên đối tượng?
A. Task Manager để xem SID và ACE đã áp dụng cho file đó.
B. Disk Management để so sánh quyền NTFS giữa các volume.
C. Effective Access để xem quyền tổng hợp từ token và ACL.
D. Services console để xem quyền hiệu lực của user trong domain.
Đáp án đúng: C

36. Tài khoản triển khai chỉ cần restart một service và đọc log. Cách cấp quyền nào phù hợp nhất?
A. Cấp sudo ALL hoặc local Administrators để tránh lỗi triển khai.
B. Chỉ cấp quyền cần cho service control và log path.
C. Dùng tài khoản quản trị chung cho pipeline và mọi kỹ sư.
D. Cấp Full Control trên toàn bộ thư mục hệ thống cho nhóm deploy.
Đáp án đúng: B
