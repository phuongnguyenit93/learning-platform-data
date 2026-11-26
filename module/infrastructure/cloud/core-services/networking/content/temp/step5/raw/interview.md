Khi thiết kế mạng cho ứng dụng ba tầng trên đám mây, bạn sẽ tổ chức VPC/VNet, các môi trường triển khai và các vùng sẵn sàng như thế nào để cô lập sự cố và dễ mở rộng?
Bạn lập kế hoạch CIDR cho nhiều VPC/VNet và mạng tại trung tâm dữ liệu ra sao để tránh chồng lấn dải IP, dành không gian tăng trưởng và hỗ trợ kết nối hybrid về sau?
Một ứng dụng cần phục vụ người dùng Internet nhưng cơ sở dữ liệu phải nằm trong mạng riêng; bạn sẽ bố trí public subnet, private subnet và bảng định tuyến cho từng tầng như thế nào?
Khi một máy ảo trong private subnet không thể truy cập dịch vụ Internet cần thiết, bạn sẽ lần theo đường đi và đường về của gói tin qua route table, NAT và các lớp kiểm soát lưu lượng ra sao?
Bạn sẽ chọn NAT gateway, proxy truy cập ra ngoài hay private endpoint cho các dịch vụ trong private subnet dựa trên những đánh đổi nào về bảo mật, độ sẵn sàng và chi phí?
Trong hệ thống hybrid cần phân giải tên miền nội bộ từ cả mạng doanh nghiệp và đám mây, bạn sẽ thiết kế private DNS zone, DNS forwarding và quyền truy cập DNS như thế nào?
Bạn sẽ phối hợp security group/NSG, network ACL và firewall để kiểm soát chính xác các luồng truy cập giữa tầng web, tầng ứng dụng và tầng dữ liệu theo nguyên tắc quyền tối thiểu ra sao?
Với một dịch vụ có cả HTTP API và kết nối TCP kéo dài, bạn sẽ xác định nhu cầu cân bằng tải tầng 4 hay tầng 7 và thiết kế health check, xử lý TLS, phân phối đa vùng như thế nào?
Khi cần kết nối mạng doanh nghiệp với VPC/VNet, bạn sẽ so sánh Site-to-Site VPN với đường truyền riêng và thiết kế định tuyến, dự phòng, xử lý xung đột CIDR ra sao?
Lưu lượng giữa hai subnet bị từ chối dù đã cho phép ingress tại đích; bạn sẽ sử dụng flow logs, kiểm tra trạng thái kết nối và các cấu hình mạng để khoanh vùng nguyên nhân như thế nào?
Nếu một vùng sẵn sàng gặp sự cố khiến nhiều yêu cầu tới ứng dụng bị timeout, bạn sẽ thiết kế và kiểm thử khả năng chuyển tiếp lưu lượng của load balancer, subnet, NAT và tuyến mạng như thế nào?
Khi chi phí mạng tăng mạnh sau khi mở rộng ứng dụng, bạn sẽ phân tích lưu lượng egress, phí xử lý NAT và truyền dữ liệu liên vùng rồi ưu tiên những thay đổi nào để giảm chi phí mà vẫn bảo đảm an toàn?
