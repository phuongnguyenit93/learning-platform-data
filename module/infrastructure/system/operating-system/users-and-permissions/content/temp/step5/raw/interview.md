Bạn phân biệt user account, group và process identity trong cơ chế kiểm soát truy cập của hệ điều hành như thế nào?
UID và GID trên Linux đại diện cho điều gì, và kernel sử dụng chúng khi kiểm tra quyền truy cập ra sao?
Bạn giải thích vai trò của các trường trong /etc/passwd và vì sao mật khẩu không nên được lưu trực tiếp trong tệp này như thế nào?
Bạn mô tả cách /etc/shadow bảo vệ thông tin xác thực và những quyền truy cập nào cần áp dụng cho tệp này như thế nào?
Bạn phân biệt primary group và supplementary groups của một tài khoản Linux trong quá trình truy cập tài nguyên như thế nào?
Bạn giải thích NSS giúp Linux tra cứu người dùng và nhóm từ local files, LDAP hoặc nguồn danh tính khác như thế nào?
Bạn mô tả vai trò của PAM trong xác thực và quản lý phiên đăng nhập trên Linux như thế nào?
Bạn tạo, sửa, khóa và xóa tài khoản Linux bằng useradd, usermod, passwd và userdel theo quy trình nào?
Bạn lựa chọn UID và GID cho tài khoản người dùng, tài khoản hệ thống và service account dựa trên nguyên tắc nào?
Bạn xử lý rủi ro khi tái sử dụng UID của một tài khoản đã xóa nhưng các tệp cũ vẫn còn trên hệ thống như thế nào?
Bạn phân biệt tài khoản người dùng tương tác với service account không cần shell đăng nhập như thế nào?
Bạn kiểm tra nhóm hiệu lực của một phiên đăng nhập và giải thích vì sao thay đổi group membership có thể chưa có hiệu lực ngay như thế nào?
Bạn xác định cách khóa đăng nhập mà vẫn giữ lại quyền sở hữu tệp của một tài khoản cần ngừng hoạt động như thế nào?
Bạn giải thích sự khác nhau giữa quyền owner, group và others trong mô hình permission POSIX như thế nào?
Bạn diễn giải quyền đọc, ghi và thực thi đối với tệp thông thường và thư mục Linux khác nhau ra sao?
Bạn chuyển đổi giữa symbolic mode và octal mode khi dùng chmod để cấp quyền cho tệp như thế nào?
Bạn phân tích cách quyền execute trên từng thư mục cha ảnh hưởng đến khả năng truy cập một đường dẫn đầy đủ như thế nào?
Bạn giải thích umask tác động đến quyền mặc định của tệp và thư mục mới được tạo như thế nào?
Bạn phân biệt tác động của umask với default ACL khi tạo tệp trong một thư mục đã có ACL kế thừa như thế nào?
Bạn sử dụng setgid trên thư mục để các tệp và thư mục con kế thừa group phù hợp trong môi trường cộng tác như thế nào?
Bạn giải thích sticky bit hạn chế việc xóa hoặc đổi tên tệp trong thư mục dùng chung như /tmp như thế nào?
Bạn đánh giá rủi ro bảo mật của setuid và setgid executable, đồng thời xác định cách kiểm tra các tệp có bit đặc biệt ra sao?
Bạn phân biệt Linux capabilities với quyền root toàn phần và lựa chọn capability tối thiểu cho một dịch vụ như thế nào?
Bạn đọc output của ls -l để nhận diện owner, group, permission bits và các ký hiệu ACL mở rộng như thế nào?
Bạn sử dụng getfacl và setfacl để cấp quyền riêng cho một user hoặc group mà không thay đổi quyền POSIX cơ bản ra sao?
Bạn phân biệt access ACL với default ACL trên thư mục và giải thích cách quyền được kế thừa cho đối tượng mới như thế nào?
Bạn giải thích ACL mask giới hạn quyền hiệu lực của named user và group entry như thế nào?
Bạn phân tích vì sao chmod có thể làm thay đổi ACL mask và khiến quyền hiệu lực khác với giá trị hiển thị ban đầu như thế nào?
Bạn thiết kế ACL cho thư mục dự án để nhiều nhóm có quyền khác nhau mà vẫn duy trì quyền tối thiểu ra sao?
Bạn kiểm tra quyền thực tế của một user khi POSIX mode bits và extended ACL cùng tồn tại bằng những lệnh nào?
Bạn phân biệt sudo với su về danh tính thực thi, cách xác thực và khả năng kiểm toán như thế nào?
Bạn chỉnh sửa sudoers bằng visudo và tổ chức tệp include để giảm nguy cơ lỗi cú pháp làm mất quyền quản trị ra sao?
Bạn thiết kế sudoers rule chỉ cho phép một nhóm chạy một số lệnh cụ thể với tham số giới hạn như thế nào?
Bạn đánh giá rủi ro khi cấp quyền sudo ALL hoặc cho phép chạy shell, editor và lệnh có thể thực thi chương trình con như thế nào?
Bạn kiểm soát biến môi trường, PATH và quyền ghi vào executable khi cấu hình sudo để tránh privilege escalation ra sao?
Bạn sử dụng sudo logging và audit trail để xác định ai đã chạy lệnh quản trị, trên máy nào và vào thời điểm nào như thế nào?
Bạn phân biệt real UID, effective UID, saved UID và filesystem UID trong quá trình một process Linux truy cập tài nguyên như thế nào?
Bạn giải thích kernel kiểm tra quyền tại thời điểm mở tệp và vì sao một file descriptor đang mở có thể tiếp tục sử dụng sau khi permission thay đổi như thế nào?
Bạn xác định sự khác nhau giữa quyền xóa tệp và quyền ghi lên chính tệp khi thao tác xóa hoặc đổi tên trong thư mục Linux như thế nào?
Bạn đánh giá ảnh hưởng của mount options nosuid, noexec và nodev đến quyền và hành vi truy cập trên filesystem như thế nào?
Bạn phân biệt quyền của symbolic link với quyền của đối tượng đích khi chẩn đoán lỗi truy cập trên Linux như thế nào?
Bạn điều tra lỗi Permission denied bằng cách kiểm tra từng thư mục cha, owner, group, mode bits và ACL theo trình tự nào?
Bạn sử dụng namei -l, stat, id và getfacl để xác định thành phần đường dẫn đang chặn quyền truy cập như thế nào?
Bạn phân biệt lỗi DAC do POSIX permission với quyết định từ SELinux hoặc AppArmor khi mode bits có vẻ cho phép truy cập như thế nào?
Bạn dùng auditd hoặc audit rules để tìm tiến trình và thao tác dẫn tới sự kiện bị từ chối truy cập trên Linux như thế nào?
Bạn cấu hình systemd service với User, Group và SupplementaryGroups để giới hạn danh tính tiến trình như thế nào?
Bạn lựa chọn systemd sandboxing options và Linux capabilities để giảm quyền của dịch vụ mà vẫn cho phép nó hoạt động như thế nào?
Bạn xử lý tình huống service chạy dưới tài khoản riêng không thể đọc secret hoặc ghi log dù người quản trị truy cập được như thế nào?
Bạn giải thích vì sao process trong container chạy với UID 0 chưa chắc có quyền root trên host khi user namespace được bật như thế nào?
Bạn cấu hình USER trong Docker image và quyền sở hữu volume để ứng dụng chạy non-root mà vẫn đọc ghi đúng dữ liệu như thế nào?
Bạn phân tích lỗi permission denied khi container mount thư mục từ host có UID/GID không khớp và đề xuất cách xử lý ra sao?
Bạn sử dụng runAsUser, runAsGroup, fsGroup và securityContext trong Kubernetes để cấp quyền tối thiểu cho workload như thế nào?
Bạn phân biệt tác động của fsGroup, volume ownership và CSI driver đến quyền truy cập persistent volume trong Kubernetes như thế nào?
Bạn kiểm tra tương tác giữa container user, read-only root filesystem, Linux capabilities và SELinux khi pod không truy cập được tệp như thế nào?
Bạn phân biệt tên tài khoản Windows với Security Identifier (SID) và giải thích vì sao SID mới là định danh bảo mật được dùng trong access check như thế nào?
Bạn so sánh local account, domain account và managed service account trong môi trường Windows như thế nào?
Bạn giải thích Windows access token chứa user SID, group SID và privilege, và được tạo hoặc cập nhật trong quá trình đăng nhập ra sao?
Bạn phân biệt quyền được gán trong access token với quyền được cấp bởi ACL trên một đối tượng Windows như thế nào?
Bạn mô tả User Account Control và split token của tài khoản administrator ảnh hưởng đến việc chạy ứng dụng elevated như thế nào?
Bạn phân biệt DACL và SACL trong NTFS security descriptor theo mục đích cấp quyền và kiểm toán truy cập như thế nào?
Bạn giải thích ACE allow và deny được đánh giá theo thứ tự trong DACL, bao gồm ảnh hưởng của explicit và inherited ACE như thế nào?
Bạn phân biệt quyền kế thừa từ thư mục cha với quyền được đặt trực tiếp trên tệp NTFS như thế nào?
Bạn kiểm soát việc bật, tắt hoặc bảo vệ inheritance khi một thư mục con cần chính sách truy cập riêng như thế nào?
Bạn xác định effective permissions của một user Windows khi người đó thuộc nhiều group có các ACE khác nhau như thế nào?
Bạn phân biệt quyền chia sẻ SMB với quyền NTFS và xác định quyền truy cập cuối cùng khi truy cập tệp qua mạng như thế nào?
Bạn sử dụng icacls để xem, cấp, thu hồi và kế thừa quyền NTFS trong một thư mục như thế nào?
Bạn phân biệt owner của đối tượng NTFS với quyền đọc, ghi hoặc thay đổi ACL mà user đang có như thế nào?
Bạn cấu hình SACL và audit policy để ghi nhận truy cập thành công hoặc thất bại đối với tệp nhạy cảm như thế nào?
Bạn phân biệt Windows privileges như SeServiceLogonRight với quyền truy cập tệp được cấp qua NTFS ACL như thế nào?
Bạn lựa chọn service account, virtual account hoặc gMSA cho Windows service dựa trên yêu cầu danh tính và quản lý credential như thế nào?
Bạn xác định quyền Log on as a service và quyền truy cập file, registry hoặc network resource cần thiết cho một Windows service như thế nào?
Bạn điều tra lỗi Access is denied trên Windows bằng Security tab, Effective Access, icacls và access token như thế nào?
Bạn xác định vì sao user có quyền đọc tệp nhưng không thể truy cập qua SMB bằng cách kiểm tra share permission, NTFS ACL và danh tính phiên mạng như thế nào?
Bạn phân biệt integrity level với quyền DACL khi một tiến trình Windows bị ngăn ghi vào tài nguyên như thế nào?
Bạn sử dụng Event Viewer và Security audit events để xác định tài khoản, đối tượng và loại truy cập bị từ chối như thế nào?
Bạn so sánh cơ chế UID/GID và POSIX ACL của Linux với SID, access token và NTFS ACL của Windows như thế nào?
Bạn thiết kế quy trình cấp quyền tối thiểu cho một dịch vụ chạy trên cả Linux và Windows mà vẫn giữ hành vi nhất quán như thế nào?
Bạn đánh giá rủi ro khi cấp quyền rộng cho thư mục dùng chung, thư mục triển khai hoặc thư mục chứa secret trong môi trường nhiều người vận hành như thế nào?
Bạn tự động hóa việc cấp quyền theo nhóm và phát hiện permission drift bằng policy hoặc configuration management như thế nào?
Bạn tổ chức rà soát định kỳ user, group, sudoers, NTFS ACL và service account để thu hồi quyền không còn cần thiết ra sao?
Bạn thiết kế kiểm toán quyền truy cập để xác định ai đã cấp, thay đổi hoặc sử dụng quyền đặc biệt và lưu bằng chứng ở đâu như thế nào?
Bạn xây dựng kịch bản kiểm thử cho permission denied trên tệp, thư mục, process, service và container để phân biệt lỗi cấu hình với lỗi ứng dụng như thế nào?
Bạn xử lý sự cố một ứng dụng chỉ lỗi permission trong production dù chạy bình thường ở môi trường phát triển bằng cách đối chiếu danh tính, group, ACL, mount và security policy như thế nào?
