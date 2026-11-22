# Network Service Discovery

Network Service Discovery là cơ chế giúp một ứng dụng tìm đúng địa chỉ và cổng của dịch vụ cần gọi mà không phải phụ thuộc vào địa chỉ được cấu hình cố định. Khi các instance được khởi tạo, thay thế hoặc di chuyển, hệ thống discovery cần cập nhật thông tin để client vẫn kết nối được đến endpoint phù hợp.

Lộ trình dành cho lập trình viên, kỹ sư hạ tầng, người vận hành hệ thống phân tán và người đã có kiến thức mạng căn bản. Bạn sẽ học nguyên lý service discovery, cách dùng DNS và bản ghi SRV, mDNS/DNS-SD cho mạng cục bộ, service registry tập trung, cơ chế đăng ký và health check, rồi cách Kubernetes cung cấp địa chỉ dịch vụ trong cluster.

Sau khi học, bạn có thể giải thích luồng đăng ký và truy vấn dịch vụ, phân tích ảnh hưởng của cache, TTL hoặc instance mất kết nối, và kiểm tra sự cố bằng các công cụ phân giải DNS cùng trạng thái registry. Bảo mật quyền truy cập và giám sát khả năng tìm kiếm dịch vụ là một phần của vận hành ổn định.