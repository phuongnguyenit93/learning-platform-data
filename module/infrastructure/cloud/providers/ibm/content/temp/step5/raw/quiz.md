Câu 1: Một tài khoản IBM Cloud có hai môi trường dev và prod; nhóm muốn gom tài nguyên để cấp quyền IAM và xem mức sử dụng theo môi trường. Nên làm gì?
A. Tạo hai IAM access group cho người dùng.
B. Tạo hai resource group cho dev và prod.
C. Tạo hai security group trong mạng VPC.
D. Tạo hai service ID cho từng môi trường.
Đáp án đúng: B

Câu 2: Hai mươi kỹ sư cần cùng quyền đọc dịch vụ IBM Cloud; quản trị viên muốn chỉnh chính sách một lần khi người mới gia nhập. Nên sử dụng gì?
A. Gán policy riêng cho từng tài khoản người dùng.
B. Dùng chung API key của một service ID duy nhất.
C. Đưa các kỹ sư vào cùng một resource group.
D. Gán chính sách IAM cho một access group chung.
Đáp án đúng: D

Câu 3: Pipeline CI cần gọi API IBM Cloud bằng danh tính riêng với quyền IAM tối thiểu, tách khỏi tài khoản nhân viên. Nên tạo gì?
A. Tạo IAM service ID riêng cho pipeline CI.
B. IAM access group thay cho danh tính.
C. Resource group làm danh tính tác vụ.
D. API key của chủ sở hữu tài khoản.
Đáp án đúng: A

Câu 4: Nhóm muốn lọc kết nối tại giao diện mạng của VSI bằng luật có trạng thái, tự cho phép gói phản hồi khi kết nối đã được chấp nhận. Nên dùng gì?
A. Security group gắn trên NIC của VSI.
B. Network ACL áp dụng tại cấp subnet.
C. Route table quy định đường đi của gói.
D. Public gateway nối subnet ra Internet.
Đáp án đúng: A

Câu 5: Các VSI trong subnet cần chủ động tải bản vá từ Internet nhưng không muốn gán IP công khai cho từng máy. Thành phần IBM Cloud VPC nào phù hợp?
A. Floating IP gắn trực tiếp cho từng VSI.
B. VPN gateway kết nối về mạng văn phòng.
C. Gắn public gateway cho subnet chứa VSI.
D. Load balancer công khai trước các VSI.
Đáp án đúng: C

Câu 6: Một VSI cần được truy cập trực tiếp từ Internet qua IP công khai ổn định; luật security group đã cho phép kết nối. Cần cấu hình gì?
A. Public gateway kết nối với subnet.
B. Floating IP dành riêng cho giao diện VSI.
C. Route table thêm tuyến nội bộ VPC.
D. Endpoint gateway dành cho dịch vụ.
Đáp án đúng: B

Câu 7: Dịch vụ HTTPS có nhiều VSI backend và cần phân phối yêu cầu mới, tự bỏ qua backend lỗi qua health check. Thành phần nào thích hợp?
A. VPN for VPC thiết lập kết nối site-to-site.
B. Transit Gateway liên kết nhiều mạng VPC.
C. Public gateway cho phép kết nối Internet.
D. Application Load Balancer có health check.
Đáp án đúng: D

Câu 8: Ứng dụng IBM Cloud Kubernetes Service phải tiếp tục chạy khi một zone lỗi mà vẫn ở cùng region. Phương án phân bố worker và ứng dụng nào phù hợp?
A. Tăng số pod nhưng chỉ dùng một worker node.
B. Đặt nhiều worker trong duy nhất một zone.
C. Trải worker và pod replicas qua nhiều zone.
D. Tăng số namespace trong cùng một cluster.
Đáp án đúng: C

Câu 9: API container có lưu lượng biến động; nhóm cần tự mở rộng theo request đến mức không còn instance lúc rảnh và không quản trị cluster. Nên dùng gì?
A. Kubernetes Service với worker node luôn bật.
B. VSI tự chạy container trên máy cố định.
C. Code Engine job chạy một lượt rồi kết thúc.
D. Code Engine application co giãn về zero.
Đáp án đúng: D

Câu 10: Tác vụ xử lý dữ liệu chạy theo yêu cầu, có thể thực thi nhiều bản song song và thoát khi xong. Nên chọn loại workload Code Engine nào?
A. Code Engine job xử lý rồi kết thúc.
B. Code Engine app phục vụ HTTP liên tục.
C. Code Engine project giữ cấu hình chung.
D. Code Engine revision nhận request mới.
Đáp án đúng: A

Câu 11: Dữ liệu phải nằm trong một khu vực đô thị nhưng bucket IBM Cloud Object Storage cần chịu lỗi một zone. Cấu hình khả năng phục hồi nào phù hợp?
A. Single Site bucket trong một data center.
B. Regional bucket đa zone trong cùng metro.
C. Cross Region bucket trải nhiều vùng địa lý.
D. Archive class chỉ tối ưu chi phí lưu trữ.
Đáp án đúng: B

Câu 12: IBM Cloud Object Storage đã mã hóa dữ liệu, nhưng tổ chức cần quản lý root key dùng để bảo vệ khóa mã hóa của bucket. Nên tích hợp dịch vụ nào?
A. Secrets Manager lưu bí mật cho ứng dụng.
B. Activity Tracker chuyển sự kiện kiểm toán.
C. IBM Key Protect quản lý root key bucket.
D. Cloud Monitoring cảnh báo hiệu năng.
Đáp án đúng: C

Câu 13: Nhóm cần PostgreSQL do IBM vận hành, có sao lưu tự động và không muốn tự vá máy chủ cơ sở dữ liệu. Nên chọn dịch vụ nào?
A. IBM Cloud Databases for PostgreSQL.
B. VSI tự triển khai PostgreSQL và backup.
C. Cloud Object Storage giữ tệp SQL.
D. Block Storage for VPC gắn vào VSI.
Đáp án đúng: A

Câu 14: Đội hạ tầng có mẫu Terraform cho VPC và VSI, cần chạy apply lặp lại và quản lý state mà không dựng máy thực thi riêng. Dịch vụ nào đáp ứng?
A. IBM Code Engine chạy container theo sự kiện.
B. IBM Cloud Monitoring theo dõi metric hạ tầng.
C. IBM IAM access group cấp quyền cho nhóm.
D. IBM Cloud Schematics hỗ trợ chạy Terraform.
Đáp án đúng: D

Câu 15: Bộ phận an ninh cần định tuyến sự kiện thay đổi IAM trên IBM Cloud đến đích lưu log phục vụ kiểm toán. Cơ chế nào nên cấu hình?
A. Cloud Monitoring theo dõi CPU và RAM.
B. VPC Flow Logs ghi lưu lượng mạng nội bộ.
C. Activity Tracker Event Routing gửi audit.
D. Cloud Schematics theo dõi Terraform apply.
Đáp án đúng: C

Câu 16: Tài khoản IBM Cloud Pay-As-You-Go muốn nhận email khi chi tiêu tháng đạt ngưỡng tiền đã đặt. Nên bật tính năng nào?
A. Cloud Monitoring cảnh báo độ trễ API.
B. Tính năng Spending notifications.
C. IAM access group phân quyền thanh toán.
D. Resource groups nhóm tài nguyên dịch vụ.
Đáp án đúng: B
