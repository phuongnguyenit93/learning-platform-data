# Network API Gateway Kong

Kong Gateway là API gateway đứng trước các dịch vụ, nhận yêu cầu từ client, chọn đường đi đến upstream và áp dụng các chính sách như xác thực hoặc giới hạn lưu lượng. Module này giúp bạn hiểu cách Kong xử lý request và cách sử dụng các đối tượng **Gateway Service**, **Route**, **Consumer**, **Plugin** và **Upstream** để quản lý API tập trung.

Lộ trình bắt đầu từ kiến trúc và thiết lập môi trường Kong, sau đó cấu hình Services và Routes để proxy một API thực tế. Bạn tiếp tục áp dụng xác thực, rate limiting và các plugin phổ biến, tìm hiểu cân bằng tải và xử lý lỗi, rồi quản lý cấu hình bằng **decK**. Cuối cùng, bạn sử dụng logs và metrics để đánh giá hoạt động của gateway và tìm nguyên nhân sự cố.

Nội dung dành cho lập trình viên backend, DevOps và kỹ sư nền tảng đã quen với HTTP/API cơ bản. Sau khi hoàn thành, bạn có thể dựng một gateway mẫu, bảo vệ và điều phối lưu lượng đến dịch vụ, quản lý thay đổi cấu hình có kiểm soát và kiểm tra trạng thái vận hành.