Nguyên tắc defense in depth được áp dụng hiệu quả nhất theo cách nào?
A. Tập trung toàn bộ bảo vệ vào một firewall biên mạnh.
B. Chỉ dựa vào phần mềm antivirus trên máy người dùng.
C. Ẩn sơ đồ hạ tầng để người ngoài khó dò tìm.
D. Kết hợp kiểm soát độc lập ở nhiều tầng hệ thống.
Đáp án đúng: D

Khi harden một máy chủ mới, bước nào tạo baseline bảo mật phù hợp?
A. Tắt dịch vụ không cần thiết và áp dụng cấu hình đã phê duyệt.
B. Cài mọi tiện ích quản trị để đội vận hành linh hoạt hơn.
C. Giữ cấu hình mặc định để tránh ảnh hưởng tương thích ứng dụng.
D. Chỉ đổi mật khẩu tài khoản quản trị trước khi đưa vào mạng.
Đáp án đúng: A

Đội vận hành cần ưu tiên bản vá cho một lỗ hổng; tiêu chí nào phù hợp nhất?
A. Cài bản vá theo thứ tự ngày phát hành của nhà cung cấp.
B. Chỉ ưu tiên lỗi có điểm CVSS cao nhất trong mọi trường hợp.
C. Xét khả năng khai thác, mức phơi nhiễm và tác động.
D. Chờ đến đợt bảo trì định kỳ tiếp theo cho tất cả máy chủ.
Đáp án đúng: C

Một tiến trình chỉ cần đọc một thư mục dữ liệu; quyền nào nên được cấp?
A. Cấp quyền quản trị cục bộ để tránh lỗi truy cập sau này.
B. Cấp quyền ghi toàn bộ ổ đĩa để tiến trình tự chọn đường dẫn.
C. Dùng chung tài khoản root với các tiến trình nền khác.
D. Chỉ cấp quyền đọc trên đúng thư mục cần cho tác vụ.
Đáp án đúng: D

Vì sao dịch vụ nên chạy bằng service account riêng?
A. Giới hạn ảnh hưởng và truy vết hoạt động theo dịch vụ.
B. Cho phép nhiều dịch vụ dùng chung một mật khẩu dễ quản lý.
C. Tránh phải rà soát quyền sau khi cập nhật phần mềm.
D. Bảo đảm tiến trình luôn có quyền cao hơn người dùng thường.
Đáp án đúng: A

SELinux hoặc AppArmor hỗ trợ bảo vệ nền tảng bằng cơ chế nào?
A. Mã hóa mọi file trên máy bằng một khóa dùng chung.
B. Áp dụng chính sách kiểm soát truy cập bắt buộc.
C. Thay thế xác thực người dùng khi đăng nhập hệ điều hành.
D. Tự động vá mọi lỗ hổng trong kernel và ứng dụng.
Đáp án đúng: B

Secure Boot giúp bảo vệ giai đoạn khởi động bằng cách nào?
A. Xác minh chữ ký các thành phần khởi động.
B. Chặn mọi tiến trình chưa được cấp quyền root sau đăng nhập.
C. Mã hóa dữ liệu người dùng trước khi hệ điều hành tải lên.
D. Thay thế cập nhật firmware bằng kiểm tra cấu hình mạng.
Đáp án đúng: A

Tổ chức muốn giảm nguy cơ nạp kernel module độc hại; kiểm soát nào phù hợp?
A. Cho mọi quản trị viên nạp module tùy ý khi cần xử lý lỗi.
B. Chỉ nạp module có chữ ký từ nguồn tin cậy.
C. Tắt audit kernel để giảm lượng log khi khởi động.
D. Lưu module trong thư mục tạm để dễ thay thế khi cập nhật.
Đáp án đúng: B

Một file chứa credential được tạo trên máy chủ; cách đặt quyền nào phù hợp?
A. Cho mọi người dùng đọc để ứng dụng không gặp lỗi quyền.
B. Đặt quyền ghi cho tất cả để hỗ trợ cập nhật tự động.
C. Chỉ owner và nhóm dịch vụ được duyệt mới có quyền.
D. Chuyển file vào thư mục public nhưng đổi tên khó đoán.
Đáp án đúng: C

Khi lưu dữ liệu nhạy cảm trên volume dùng chung, kiểm soát nào bổ sung cho mã hóa at-rest?
A. Dùng cùng khóa giải mã cho mọi workload trong môi trường.
B. Tách khóa, giới hạn quyền giải mã theo workload.
C. Lưu khóa giải mã cạnh dữ liệu để thuận tiện phục hồi.
D. Cho mọi tiến trình cùng host đọc volume sau khi mount.
Đáp án đúng: B

Một laptop bị thất lạc khi đang tắt máy và bật full-disk encryption; lợi ích chính là gì?
A. Ngăn malware đọc file khi người dùng đăng nhập trở lại.
B. Bảo vệ dữ liệu khỏi mọi tài khoản quản trị hợp lệ.
C. Giảm khả năng đọc dữ liệu khi không có khóa mở ổ đĩa.
D. Thay thế việc khóa màn hình và xác thực lúc đăng nhập.
Đáp án đúng: C

Chiến lược backup nào tăng khả năng phục hồi trước ransomware?
A. Chỉ đồng bộ liên tục vào thư mục mạng đang được ghi.
B. Cho máy chủ production quyền xóa mọi bản backup.
C. Lưu bản sao duy nhất trên cùng ổ đĩa dữ liệu chính.
D. Giữ bản sao tách biệt, bất biến và thử khôi phục.
Đáp án đúng: D

Phân đoạn mạng giữa vùng người dùng và vùng máy chủ giúp đạt mục tiêu nào?
A. Tăng băng thông giữa mọi subnet mà không cần định tuyến.
B. Hạn chế di chuyển ngang khi một endpoint bị xâm nhập.
C. Cho phép mọi máy trong nội bộ tin cậy lẫn nhau.
D. Loại bỏ nhu cầu xác thực khi truy cập dịch vụ nội bộ.
Đáp án đúng: B

Chính sách firewall cho máy chủ thường nên bắt đầu từ nguyên tắc nào?
A. Cho phép toàn bộ outbound để tránh gián đoạn dịch vụ.
B. Mở mọi port nội bộ vì lưu lượng không đi qua Internet.
C. Chỉ lọc theo địa chỉ nguồn mà không xét cổng đích.
D. Chặn mặc định, chỉ mở luồng đã phê duyệt.
Đáp án đúng: D

Vì sao giao diện quản trị hạ tầng nên nằm trong management network riêng?
A. Cô lập mặt phẳng quản trị khỏi người dùng và workload.
B. Tăng khả năng public hóa giao diện quản trị để dễ hỗ trợ.
C. Cho phép dùng cùng credential quản trị trên mọi subnet.
D. Tránh cần ghi log các thao tác trên thiết bị mạng.
Đáp án đúng: A

Một kỹ sư cần quyền admin production trong thời gian ngắn; cơ chế nào phù hợp?
A. Thêm kỹ sư vào nhóm domain admin vô thời hạn.
B. Cấp quyền JIT kèm MFA, thời hạn và audit.
C. Dùng chung tài khoản root của nhóm vận hành.
D. Lưu mật khẩu admin trong wiki nội bộ để truy cập nhanh.
Đáp án đúng: B

Tài khoản break-glass nên được quản lý theo cách nào?
A. Giới hạn người dùng và rà soát sau mỗi lần dùng.
B. Dùng hằng ngày để tránh quên quy trình đăng nhập khẩn cấp.
C. Chia sẻ mật khẩu trong nhóm chat để luôn có người truy cập.
D. Loại bỏ MFA và audit để giảm thời gian xử lý sự cố.
Đáp án đúng: A

Trước khi triển khai container image vào production, nên xác minh điều gì?
A. Tên tag có chữ latest để luôn nhận bản mới nhất.
B. Xác minh nguồn build, chữ ký và digest được duyệt.
C. Image chạy được trên máy cá nhân của người phát triển.
D. Kích thước image nhỏ hơn mọi image đang chạy.
Đáp án đúng: B

Biện pháp nào giảm tác động khi container bị khai thác?
A. Chạy privileged để container tự quản lý namespace.
B. Mount toàn bộ filesystem host để hỗ trợ chẩn đoán.
C. Chạy non-root và bỏ capability không cần thiết.
D. Dùng chung user ID 0 cho mọi container trong cluster.
Đáp án đúng: C

Linux namespace và cgroup phục vụ hai mục tiêu khác nhau nào?
A. Namespace cô lập góc nhìn; cgroup giới hạn mức dùng.
B. Namespace mã hóa file; cgroup xác minh chữ ký container image.
C. Namespace quản lý bản vá; cgroup phân quyền người dùng hệ điều hành.
D. Namespace giám sát mạng; cgroup cấp danh tính cho workload.
Đáp án đúng: A

Vì sao nên dùng read-only root filesystem cho container khi khả thi?
A. Bảo đảm container không thể gửi lưu lượng mạng ra ngoài.
B. Tự động mã hóa volume ghi dữ liệu của ứng dụng.
C. Giảm khả năng ghi file và duy trì persistence.
D. Thay thế kiểm soát quyền và cập nhật image định kỳ.
Đáp án đúng: C

Seccomp profile giúp giảm bề mặt tấn công container bằng cách nào?
A. Giới hạn số lượng pod có thể chạy trong một namespace.
B. Mã hóa traffic giữa container và Kubernetes API server.
C. Giới hạn system call tiến trình được phép gọi.
D. Quản lý danh tính người dùng đăng nhập vào registry.
Đáp án đúng: C

Cách nào phù hợp để cung cấp secret cho workload container?
A. Đóng gói secret dài hạn trực tiếp trong image container.
B. Commit file secret vào repository private cùng mã nguồn.
C. Đặt một credential chung trong manifest cho mọi namespace.
D. Lấy secret từ manager với quyền hẹp, có rotation.
Đáp án đúng: D

Trong Kubernetes, RBAC nên được cấu hình theo nguyên tắc nào?
A. Dùng cluster-admin cho mọi service account để đơn giản hóa.
B. Cho phép mọi pod đọc mọi Secret trong toàn cluster.
C. Cấp quyền tối thiểu theo namespace và tác vụ.
D. Dùng tài khoản cá nhân của quản trị viên cho workload.
Đáp án đúng: C

Admission policy giúp bảo vệ cluster trước cấu hình workload rủi ro ra sao?
A. Tự động cấp quyền cluster-admin cho pod có nhãn hợp lệ.
B. Từ chối manifest dùng privileged hoặc host namespace.
C. Thay thế việc quét image và quản lý lỗ hổng.
D. Chỉ ghi log manifest sau khi workload đã chạy.
Đáp án đúng: B

Workload trên cloud cần truy cập object storage; lựa chọn nào an toàn hơn?
A. Nhúng access key dài hạn vào source code của ứng dụng.
B. Dùng chung access key quản trị cho mọi môi trường.
C. Lưu secret trong image để mọi replica đọc cùng lúc.
D. Dùng workload identity và role tạm thời, quyền hẹp.
Đáp án đúng: D

Bảo vệ cloud instance metadata service giúp giảm nguy cơ nào?
A. Ngăn người dùng cuối truy cập website qua DNS công cộng.
B. Ngăn cloud provider thay đổi firmware của máy chủ vật lý.
C. Ngăn SSRF lấy credential từ metadata endpoint.
D. Ngăn mọi lưu lượng east-west giữa các subnet.
Đáp án đúng: C

Cloud security group thường được dùng để kiểm soát điều gì?
A. Quyền đọc và ghi file bên trong hệ điều hành khách.
B. Chữ ký số của container image trong registry.
C. Lọc luồng mạng vào và ra của workload.
D. Quyền phê duyệt thay đổi cấu hình tài khoản cloud.
Đáp án đúng: C

Configuration drift xảy ra khi nào?
A. Cấu hình thực tế lệch baseline đã phê duyệt.
B. Một máy chủ được khởi động lại theo lịch bảo trì.
C. Một gói phần mềm được cập nhật đúng phiên bản mục tiêu.
D. Một hệ thống tạo thêm bản sao lưu theo retention policy.
Đáp án đúng: A

Cách nào giúp phát hiện và xử lý configuration drift bền vững?
A. So sánh cấu hình thực tế với baseline và khắc phục.
B. Chỉ dựa vào trí nhớ của quản trị viên vận hành hệ thống.
C. Cho phép chỉnh tay mọi máy chủ mà không ghi nhận thay đổi.
D. Tắt công cụ quản lý cấu hình sau khi triển khai ban đầu.
Đáp án đúng: A

Vì sao asset inventory là nền tảng của vulnerability management?
A. Tự động chứng minh mọi tài sản đã được vá đầy đủ.
B. Thay thế kiểm thử xâm nhập và rà soát cấu hình.
C. Ngăn thiết bị mới kết nối vào mạng doanh nghiệp.
D. Cho biết tài sản, owner và phần mềm liên quan.
Đáp án đúng: D

Log bảo mật của máy chủ quan trọng nên được quản lý thế nào?
A. Chỉ lưu cục bộ để người dùng máy chủ tự xem khi cần.
B. Cho ứng dụng production quyền xóa log sau mỗi lần chạy.
C. Ghi plaintext secret để điều tra đầy đủ mọi sự kiện.
D. Tập trung log, hạn chế sửa/xóa và đồng bộ giờ.
Đáp án đúng: D

Endpoint detection and response hỗ trợ phát hiện điều gì?
A. Chỉ các gói tin bị firewall từ chối ở ranh giới mạng.
B. Phát hiện hành vi tiến trình bất thường trên endpoint.
C. Chỉ lỗi cấu hình trong manifest Kubernetes trước triển khai.
D. Chỉ chứng thư TLS sắp hết hạn của dịch vụ công khai.
Đáp án đúng: B

Kiểm soát nào giúp xác minh phần mềm triển khai không bị thay thế trên đường phát hành?
A. Chỉ đổi tên file artifact sau mỗi lần build.
B. Chỉ tải artifact từ thư mục chia sẻ nội bộ.
C. Dùng tag mutable để cập nhật nội dung mà không cần build lại.
D. Ký artifact và xác minh chữ ký trước khi triển khai.
Đáp án đúng: D

Sau khi áp dụng hardening baseline, cách nào xác minh hiệu quả?
A. Chỉ hỏi quản trị viên xem hệ thống có vẻ an toàn không.
B. Quét cấu hình và kiểm thử theo tiêu chí đã định.
C. Chỉ kiểm tra máy chủ có khởi động thành công hay không.
D. Dừng giám sát vì baseline đã được áp dụng một lần.
Đáp án đúng: B

Khi phát hiện máy chủ bị xâm nhập, hành động nào nên được ưu tiên?
A. Cô lập máy, giữ bằng chứng và điều tra phạm vi.
B. Xóa ngay ổ đĩa để loại bỏ malware trước khi điều tra.
C. Khởi động lại nhiều lần để tiến trình độc hại tự biến mất.
D. Tắt toàn bộ logging để tránh ghi thêm dữ liệu nhạy cảm.
Đáp án đúng: A

Trước khi thanh lý thiết bị từng lưu dữ liệu nhạy cảm, tổ chức nên làm gì?
A. Xóa an toàn hoặc hủy khóa theo chính sách.
B. Xóa shortcut trên desktop và gỡ tài khoản người dùng.
C. Format nhanh phân vùng rồi chuyển thiết bị cho đơn vị khác.
D. Xóa tên thiết bị khỏi inventory mà không xử lý ổ lưu trữ.
Đáp án đúng: A
