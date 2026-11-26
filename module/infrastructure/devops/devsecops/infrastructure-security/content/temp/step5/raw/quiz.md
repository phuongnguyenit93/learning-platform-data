Câu 1: Runner CI cần đọc artifact cloud trong 15 phút. Cách cấp quyền nào hạn chế hậu quả lộ credential?
A. Trao quyền qua OIDC để nhận credential ngắn hạn.
B. Ghi access key cố định vào biến môi trường của job.
C. Dùng khóa quản trị chia sẻ giữa các repository.
D. Lưu mật khẩu người dùng vào file trên runner.
Đáp án đúng: A

Câu 2: Quản trị viên cloud có quyền sửa IAM và firewall. Cách nào giảm rủi ro chiếm quyền tài khoản?
A. Chỉ giới hạn thời gian đăng nhập trên console cloud.
B. Áp MFA và tài khoản riêng có quyền tối thiểu.
C. Dùng chung tài khoản admin có mật khẩu đổi định kỳ.
D. Chỉ chặn truy cập console ngoài giờ làm việc.
Đáp án đúng: B

Câu 3: VPC có subnet web và DB riêng, chỉ web cần PostgreSQL. Rule nào hạn chế dịch chuyển ngang tốt nhất?
A. Cho cả VPC vào DB trên tất cả cổng ứng dụng.
B. Chỉ cho nhóm web vào DB qua TCP 5432.
C. Mở TCP 5432 từ Internet để web truy cập.
D. Cho mọi subnet vào DB nhưng chặn lưu lượng ICMP.
Đáp án đúng: B

Câu 4: Block storage cloud chứa dữ liệu nhạy cảm. Cấu hình nào bảo vệ dữ liệu lưu trữ và quyền giải mã?
A. Dùng TLS ở load balancer nhưng không mã hóa đĩa.
B. Giữ snapshot trong subnet riêng mà không mã hóa.
C. Bật mã hóa đĩa và giới hạn quyền sử dụng khóa KMS.
D. Giới hạn cổng SSH rồi giữ khóa ở cloud-init user data.
Đáp án đúng: C

Câu 5: Máy bastion chỉ cần SSH bằng public key. Cấu hình nào giảm rủi ro đăng nhập đặc quyền?
A. Chỉ đổi cổng SSH và giữ mật khẩu cho tài khoản root.
B. Bật SSH password cho root nhưng giới hạn dải IP.
C. Đặt mật khẩu root vào vault rồi vẫn cho đăng nhập root.
D. Tắt xác thực SSH bằng mật khẩu và root login trực tiếp.
Đáp án đúng: D

Câu 6: Terraform plan cho thấy security group mở SSH 22 từ `0.0.0.0/0`. Cách xử lý nào đúng trước apply?
A. Thu hẹp dải IP được phép rồi quét lại bản plan.
B. Đổi port SSH trong image ứng dụng đã deploy trên cloud.
C. Tắt rule scanner vì dải IP đã được khai báo.
D. Apply trước để xem có ai thực sự kết nối được.
Đáp án đúng: A

Câu 7: Đội muốn chặn Terraform tạo bucket public bằng policy as code. Bước nào phù hợp?
A. Đánh dấu ticket review sau khi Terraform đã apply.
B. Chỉ quét access log sau khi bucket được tạo.
C. Đánh giá plan theo policy và chặn CI khi vi phạm.
D. Đặt nhãn `private` cho bucket rồi bỏ kiểm tra policy.
Đáp án đúng: C

Câu 8: Security group production bị sửa trực tiếp trên console, lệch IaC. Trước khi đồng bộ nên làm gì?
A. Sửa state thủ công để loại chênh lệch trên dashboard.
B. Bỏ qua vì thay đổi có thể do administrator hợp lệ.
C. Xóa toàn bộ stack rồi áp lại từ nhánh release.
D. Xem drift qua plan, xác minh rồi đồng bộ theo IaC.
Đáp án đúng: D

Câu 9: Pod giám sát tại namespace `metrics` chỉ cần get/list Pod ở đó. Cấp RBAC nào vừa đủ?
A. Gán cluster-admin cho ServiceAccount bằng ClusterRoleBinding.
B. Dùng ClusterRoleBinding gán quyền edit trên toàn cluster.
C. Tạo Role đọc pods và RoleBinding trong namespace metrics.
D. Dùng ServiceAccount mặc định ở namespace kube-system.
Đáp án đúng: C

Câu 10: Cluster phải từ chối Pod vi phạm mức Restricted thay vì chỉ cảnh báo. Nhãn namespace nào đúng?
A. `pod-security.kubernetes.io/audit: restricted`.
B. `pod-security.kubernetes.io/warn: restricted`.
C. `pod-security.kubernetes.io/enforce: restricted`.
D. `pod-security.kubernetes.io/enforce: privileged`.
Đáp án đúng: C

Câu 11: Terraform đánh dấu biến mật khẩu DB là `sensitive`, nhưng state vẫn chứa giá trị. Bảo vệ state thế nào?
A. Mã hóa backend và giới hạn IAM đọc state.
B. Chỉ dùng `sensitive=true` để loại mật khẩu khỏi state.
C. Đẩy state vào Git private và duyệt bằng pull request.
D. Chỉ ẩn output CI rồi lưu state trên runner.
Đáp án đúng: A

Câu 12: Hai dịch vụ nội bộ cần xác thực danh tính cả hai đầu trong kết nối. Cơ chế nào đáp ứng?
A. Chỉ dùng TLS để xác thực chứng chỉ phía server.
B. Dùng firewall giới hạn dải IP của các subnet.
C. Mã hóa payload với base64 trước khi gửi request.
D. Dùng mTLS và kiểm tra chứng chỉ của cả hai phía.
Đáp án đúng: D

Câu 13: Sau khi VM bị xóa, đội bảo mật vẫn cần biết ai sửa IAM policy cloud. Thiết kế log nào phù hợp?
A. Chỉ ghi log hệ điều hành trên ổ đĩa VM rồi xóa cùng VM.
B. Bật audit control plane và lưu log tập trung chống sửa.
C. Chỉ lưu access log của dịch vụ load balancer.
D. Đọc log build của runner khi xảy ra sự cố.
Đáp án đúng: B

Câu 14: Bastion có CVE nghiêm trọng trong OpenSSH và lộ SSH ra Internet. Ưu tiên xử lý nào hợp lý?
A. Chỉ đổi cổng SSH rồi trì hoãn cập nhật bản vá đến kỳ sau.
B. Tăng tài nguyên bastion để giảm tải khi bị scan.
C. Thêm tag hardened vào image nhưng giữ bản CVE.
D. Giới hạn nguồn truy cập, vá và kiểm chứng phiên bản.
Đáp án đúng: D

Câu 15: Một access key cloud bị in vào log CI công khai. Hành động ứng phó ban đầu nào đúng?
A. Thu hồi key, kiểm audit và cấp lại qua cơ chế an toàn.
B. Chỉ xóa dòng log và giữ nguyên access key đang dùng.
C. Chuyển job sang runner khác để ẩn khóa cũ.
D. Đổi tên biến secret trong CI mà không thu hồi key.
Đáp án đúng: A

Câu 16: Một resource vi phạm policy IaC nhưng cần ngoại lệ tạm để migration. Hồ sơ nào thích hợp?
A. Tắt rule policy toàn dự án đến khi migration hoàn tất.
B. Ghi lý do rủi ro, owner, biện pháp bù và hạn hết.
C. Thay tên resource để scanner bỏ qua rule hiện có.
D. Chuyển lỗi sang cảnh báo mà không ghi người duyệt.
Đáp án đúng: B
