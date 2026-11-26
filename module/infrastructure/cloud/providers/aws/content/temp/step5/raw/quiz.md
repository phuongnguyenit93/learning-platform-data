Câu 1: Ứng dụng web trên AWS phải tiếp tục nhận yêu cầu khi một Availability Zone trong Region gặp lỗi. Kiến trúc nào phù hợp nhất?
A. Đặt hai EC2 trong một AZ nhưng ở hai subnet.
B. Đặt một EC2 và tạo snapshot EBS định kỳ.
C. Đặt EC2 ở nhiều AZ phía sau một ALB.
D. Đặt hai EC2 chung AZ và tăng kích thước máy.
Đáp án đúng: C

Câu 2: Ứng dụng trên EC2 cần gọi API S3 mà không lưu access key dài hạn trên máy. Cách cấp quyền nên dùng?
A. Gắn IAM role qua instance profile cho EC2.
B. Tạo IAM user rồi lưu access key trong máy.
C. Mở quyền đọc bucket công khai cho Internet.
D. Sao chép access key của root vào máy ảo.
Đáp án đúng: A

Câu 3: Máy EC2 không có public IP trong private subnet cần cập nhật gói qua Internet bằng IPv4. Cấu hình egress nào phù hợp?
A. Định tuyến mặc định tới Internet Gateway trực tiếp.
B. Dùng S3 Gateway Endpoint làm cổng ra Internet.
C. Đặt public IP trên route table của private subnet.
D. Định tuyến qua NAT Gateway ở public subnet có IGW.
Đáp án đúng: D

Câu 4: Tệp báo cáo S3 bị ghi đè; cần đọc lại bản trước đó mà không phục hồi backup. Cơ chế nào cần bật trước khi ghi đè?
A. S3 Replication sao chép đối tượng liên vùng.
B. S3 Lifecycle chuyển đối tượng sang lưu trữ lạnh.
C. S3 Transfer Acceleration tăng tốc tải tệp.
D. S3 Versioning lưu các phiên bản của đối tượng.
Đáp án đúng: D

Câu 5: CSDL OLTP chạy trên EC2 cần ổ block có IOPS tùy chỉnh và tồn tại sau khi dừng/khởi động lại máy. Loại lưu trữ nào phù hợp?
A. Instance Store gắn với máy chủ chạy EC2.
B. Amazon EBS gp3 volume gắn vào EC2 cùng AZ.
C. Amazon S3 Standard truy cập bằng API HTTP.
D. Amazon EFS cung cấp thư mục dùng chung NFS.
Đáp án đúng: B

Câu 6: Nhiều EC2 Linux ở các AZ cần truy cập đồng thời cùng thư mục qua NFS. Dịch vụ nào đáp ứng trực tiếp?
A. Amazon EBS tạo block volume cho một EC2.
B. Amazon S3 truy cập đối tượng qua HTTP.
C. Amazon EFS cung cấp file system qua NFS.
D. EC2 Instance Store tạo đĩa cục bộ tạm.
Đáp án đúng: C

Câu 7: Một tên miền HTTPS cần định tuyến /api/* và /images/* đến hai target group theo đường dẫn. Nên chọn dịch vụ nào?
A. Network Load Balancer phân tuyến bằng IP và port.
B. Application Load Balancer đặt rule theo đường dẫn.
C. Gateway Load Balancer chuyển lưu lượng tới appliance.
D. Classic Load Balancer phân phối theo một listener.
Đáp án đúng: B

Câu 8: Dịch vụ web trên EC2 cần tự tăng số lượng instance khi CPU cao và trải ra nhiều AZ. Cấu hình nào phù hợp nhất?
A. EC2 Auto Scaling Group theo CPU trên nhiều AZ.
B. EC2 Placement Group gom instance trên cùng phần cứng.
C. AWS Lambda tăng bộ nhớ hàm theo lượng yêu cầu.
D. Amazon CloudFront giữ bản sao nội dung tại edge.
Đáp án đúng: A

Câu 9: RDS PostgreSQL cần tự động chuyển sang máy dự phòng khi AZ chính gặp lỗi; mục tiêu chính là HA thay vì mở rộng đọc. Nên bật gì?
A. Read Replica cùng Region để nhận thêm truy vấn đọc.
B. RDS Multi-AZ deployment với standby đồng bộ.
C. Snapshot hàng giờ lưu trong cùng một Region.
D. Storage Auto Scaling tăng dung lượng khi gần đầy.
Đáp án đúng: B

Câu 10: RDS MySQL đủ khả năng ghi nhưng truy vấn SELECT từ hệ thống báo cáo quá nhiều; chấp nhận độ trễ sao chép nhỏ. Cách giảm tải đọc?
A. Tăng backup retention trên DB instance chính.
B. Bật Multi-AZ standby chỉ dành cho failover.
C. Bật Performance Insights để theo dõi câu SQL.
D. Tạo RDS Read Replica cho truy vấn chỉ đọc.
Đáp án đúng: D

Câu 11: Ứng dụng đưa tác vụ vào Amazon SQS; muốn Lambda xử lý message theo lô mà không tự viết vòng lặp polling. Cần cấu hình gì?
A. Lambda event source mapping tới SQS.
B. S3 Event Notification gửi sự kiện từ bucket.
C. API Gateway tạo REST endpoint gọi trực tiếp.
D. CloudFront Function chạy mỗi lần có request.
Đáp án đúng: A

Câu 12: Đội bảo mật cần xác định danh tính nào đã gọi API thay đổi IAM policy trong tài khoản AWS. Nguồn sự kiện nào phù hợp?
A. Amazon CloudWatch Metrics ghi mức sử dụng CPU.
B. AWS Config ghi trạng thái cấu hình resource.
C. AWS CloudTrail ghi lịch sử lời gọi AWS API.
D. VPC Flow Logs ghi luồng IP trong subnet.
Đáp án đúng: C

Câu 13: Ứng dụng di động cần tải một ảnh lên đúng khóa đối tượng S3 trong 5 phút mà không có access key IAM dài hạn. Giải pháp nào?
A. Mở quyền PutObject công khai cho bucket.
B. Đưa access key IAM user vào ứng dụng.
C. Cho phép mọi principal ghi vào prefix ảnh.
D. Tạo S3 presigned PUT URL hết hạn 5 phút.
Đáp án đúng: D

Câu 14: Dữ liệu trên S3 cần mã hóa lưu trữ và quản trị quyền sử dụng khóa cùng nhật ký khóa qua AWS KMS. Chọn cơ chế nào?
A. SSE-S3 với khóa do S3 quản lý mặc định.
B. SSE-KMS với customer managed KMS key.
C. SSE-C với khóa gửi trong mỗi yêu cầu.
D. TLS cho kết nối tải dữ liệu qua HTTPS.
Đáp án đúng: B

Câu 15: Doanh nghiệp muốn nhận email khi chi phí AWS ước tính trong tháng vượt ngưỡng đã đặt. Công cụ nào thích hợp?
A. AWS Budgets tạo ngưỡng chi phí và cảnh báo.
B. AWS Cost Explorer xem biểu đồ chi tiêu.
C. AWS Pricing Calculator ước tính trước khi dùng.
D. Cost allocation tags phân loại khoản chi.
Đáp án đúng: A

Câu 16: EC2 trong private subnet phải đọc object S3 cùng Region và giảm phí truyền qua NAT Gateway. Cấu hình mạng nào phù hợp?
A. Định tuyến S3 qua Internet Gateway mặc định.
B. Định tuyến S3 qua NAT Gateway trong subnet.
C. Tạo Gateway VPC Endpoint cho S3 và route table.
D. Tạo VPC Peering từ VPC đến dịch vụ S3.
Đáp án đúng: C
