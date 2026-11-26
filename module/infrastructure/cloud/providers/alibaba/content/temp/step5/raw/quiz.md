Câu 1: Dịch vụ trên ECS cần đọc bucket OSS, nhưng không được lưu AccessKey dài hạn trong image. Cách xác thực nào phù hợp?
A. Lưu AccessKey của RAM user trong biến môi trường hệ điều hành ECS.
B. Gắn instance RAM role và lấy thông tin xác thực STS tạm thời.
C. Dùng AccessKey tài khoản chính trong cấu hình khởi động.
D. Mở quyền đọc công khai của bucket để ECS có thể truy cập.
Đáp án đúng: B

Câu 2: Nhân viên hỗ trợ chỉ cần xem trạng thái ECS, không được tạo, dừng hay xóa máy. Nên cấp quyền theo cách nào?
A. Gán quyền quản trị ECS đầy đủ và chỉ theo dõi nhật ký truy cập.
B. Gán quyền quản trị VPC để thao tác lên tài nguyên ECS.
C. Gán quyền tạo và cập nhật ECS, giới hạn bằng tên nhóm.
D. Tạo RAM policy chỉ cho phép những hành động đọc ECS cần thiết.
Đáp án đúng: D

Câu 3: Ứng dụng cần tách frontend và backend thành hai subnet trong cùng mạng riêng Alibaba Cloud. Cách tổ chức nào đúng?
A. Tạo một VPC và hai vSwitch có dải địa chỉ không chồng nhau.
B. Tạo hai Security Group rồi coi mỗi nhóm là một subnet.
C. Tạo hai EIP rồi gắn vào các ECS của hai tầng ứng dụng.
D. Tạo hai route table rồi coi mỗi bảng định tuyến là subnet.
Đáp án đúng: A

Câu 4: ECS nội bộ chỉ được nhận kết nối SSH từ bastion có IP 10.10.2.10. Nên chỉnh gì để giới hạn nguồn truy cập?
A. Thêm rule outbound TCP/22 tới IP bastion cho nhóm ECS.
B. Thêm rule inbound TCP/22 từ 10.10.2.10/32 vào Security Group.
C. Thêm rule inbound TCP/22 từ 0.0.0.0/0 vào Security Group của ECS.
D. Gắn EIP cho ECS rồi giới hạn nguồn bằng tên máy bastion.
Đáp án đúng: B

Câu 5: ECS backend không có EIP cần gọi API ngoài Internet và không muốn nhận kết nối từ Internet vào. Cấu hình nào phù hợp?
A. Tạo DNAT trên Internet NAT Gateway trỏ tới từng ECS backend.
B. Gắn EIP trực tiếp cho toàn bộ ECS và đóng các cổng ứng dụng.
C. Dùng Internet NAT Gateway với SNAT và tuyến mạng phù hợp.
D. Mở toàn bộ inbound trên Security Group để ECS truy cập ra ngoài.
Đáp án đúng: C

Câu 6: Website chạy nhiều ECS sau ALB, lưu lượng biến động mạnh theo giờ. Cách nào tự tăng giảm số máy phục vụ request?
A. Liên kết Auto Scaling group với ALB và đặt policy theo metric.
B. Cấu hình ALB tự tạo ECS mới sau khi số request đạt ngưỡng tải.
C. Thêm Security Group để phân phối request theo mức CPU.
D. Gắn thêm EIP để ECS tự sinh thêm instance khi tải cao.
Đáp án đúng: A

Câu 7: Dịch vụ dùng ECS và ApsaraDB RDS phải tiếp tục hoạt động khi một zone gặp sự cố. Phương án nào phù hợp?
A. Đặt toàn bộ ECS và RDS Basic Edition trong cùng một zone.
B. Rải ECS trên hai zone nhưng giữ RDS Basic Edition một zone.
C. Đặt ECS một zone và RDS High-availability cùng zone đó.
D. Rải ECS qua hai zone, dùng RDS High-availability đa zone.
Đáp án đúng: D

Câu 8: Hợp đồng ở OSS bucket private cần cho khách tải trong 15 phút mà không cấp tài khoản cloud. Cách nào phù hợp?
A. Chuyển bucket sang public-read rồi tự đổi lại sau 15 phút.
B. Gửi AccessKey của RAM user chỉ đọc OSS để khách truy cập.
C. Sinh URL ký cho GET object và đặt thời hạn sử dụng 15 phút.
D. Đặt object ACL thành public-read và chia sẻ đường dẫn cố định.
Đáp án đúng: C

Câu 9: Ảnh trên OSS được truy cập nhiều trong tháng đầu, về sau ít sử dụng nhưng phải giữ hai năm. Nên tối ưu lưu trữ thế nào?
A. Chuyển ảnh sang bộ nhớ cache của ECS trong suốt hai năm.
B. Giữ toàn bộ ảnh trong Standard để tránh mọi phí khôi phục.
C. Chuyển toàn bộ ảnh sang Archive ngay trong ngày đầu tải.
D. Dùng OSS lifecycle chuyển lớp lưu trữ khi nhu cầu đọc giảm.
Đáp án đúng: D

Câu 10: RDS MySQL bị xóa nhầm bản ghi, cần khôi phục dữ liệu trước lúc xóa và kiểm tra trước khi đưa vào production. Cách nào phù hợp?
A. Đọc bản ghi cũ từ read replica, vì bản sao không nhận lệnh xóa.
B. Khôi phục RDS đến thời điểm đã chọn trên instance khác để đối chiếu.
C. Tạo snapshot ngay sau sự cố rồi lấy dữ liệu đã xóa từ snapshot.
D. Khởi động lại RDS để rollback tất cả thao tác SQL đã commit.
Đáp án đúng: B

Câu 11: ACK có Kubernetes Deployment ba replica, cần cập nhật image và có thể hoàn tác nếu lỗi. Cách triển khai nào phù hợp?
A. Đổi image trong Deployment rồi theo dõi rollout và rollback.
B. Xóa toàn bộ Pod đang chạy trước, rồi tạo thủ công từ image mới.
C. Tạo một ECS mới rồi xóa các node hiện có của cluster.
D. SSH vào từng node để sửa trực tiếp container đang chạy.
Đáp án đúng: A

Câu 12: Cần tạo ảnh thu nhỏ sau mỗi lần tải ảnh mới lên OSS, không muốn duy trì server chạy liên tục. Nên dùng cách nào?
A. Dùng ActionTrail thực hiện trực tiếp việc xử lý mỗi object.
B. Dùng CloudMonitor để chạy tác vụ biến đổi dữ liệu ảnh.
C. Dùng ALB gọi batch xử lý ảnh theo lịch định kỳ mỗi giờ.
D. Dùng OSS trigger gọi Function Compute khi có sự kiện tải lên.
Đáp án đúng: D

Câu 13: Nhiều dịch vụ phát sự kiện cần lọc theo loại rồi chuyển tới hàm xử lý, tránh ghép chặt nguồn với đích. Dùng cơ chế nào?
A. Dùng NAT Gateway định tuyến theo loại sự kiện ứng dụng.
B. Dùng CloudMonitor đổi Security Group theo thông báo lỗi.
C. Dùng EventBridge với rule lọc sự kiện và target xử lý.
D. Dùng ECS Auto Scaling nhận sự kiện rồi tăng số máy.
Đáp án đúng: C

Câu 14: Nhóm muốn theo dõi mức CPU ECS và nhận cảnh báo khi vượt ngưỡng. Dịch vụ Alibaba Cloud nào phù hợp nhất?
A. ActionTrail để xem nhật ký thao tác quản trị tài nguyên.
B. OSS Analytics để đọc lưu lượng tải xuống từng object.
C. CloudMonitor để theo dõi metric và cấu hình cảnh báo.
D. RAM policy để ghi nhận hoạt động CPU của instance.
Đáp án đúng: C

Câu 15: Sau khi Security Group bị sửa, đội vận hành cần biết ai thao tác và lúc nào qua API hoặc console. Nên tra cứu ở đâu?
A. CloudMonitor để xem metric CPU và dung lượng RAM của từng ECS.
B. ActionTrail để tra các sự kiện quản trị Security Group.
C. OSS lifecycle để tra lịch sử chuyển lớp lưu trữ object.
D. ALB access log để tra các request HTTP đi qua backend.
Đáp án đúng: B

Câu 16: Các dự án dùng chung tài khoản Alibaba Cloud cần tách chi phí ECS và OSS theo mã dự án trên hóa đơn. Cách nào phù hợp?
A. Gắn resource tag dự án và kích hoạt cost allocation tag đó.
B. Tạo Security Group riêng từng dự án để chia chi phí theo nhóm.
C. Tạo vSwitch cho từng nhóm và phân chia phí theo dải mạng.
D. Chỉ đổi tên ECS theo dự án để hệ thống tự tách hóa đơn.
Đáp án đúng: A
