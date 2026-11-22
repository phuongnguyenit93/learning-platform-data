# Network Proxy Haproxy

HAProxy là phần mềm reverse proxy và load balancer giúp tiếp nhận kết nối từ client, chuyển lưu lượng đến các dịch vụ phía sau và cải thiện tính sẵn sàng của hệ thống. HAProxy hoạt động với lưu lượng TCP và HTTP, thường được đặt trước nhiều server ứng dụng để phân phối tải, kiểm tra tình trạng hoạt động và thực hiện các quy tắc điều hướng.

Module dành cho developer, DevOps và người vận hành hệ thống cần hiểu cách triển khai HAProxy ở mức nền tảng. Lộ trình bắt đầu từ vai trò của proxy, cấu trúc cấu hình frontend/backend và chế độ TCP/HTTP; sau đó đi vào định tuyến, thuật toán cân bằng tải, health checks và TLS. Các phần cuối giới thiệu logging, thống kê và những thao tác cần kiểm tra khi thay đổi cấu hình.

Kết thúc module, bạn có thể giải thích luồng client → HAProxy → backend, đọc và viết cấu hình proxy đơn giản, lựa chọn cách phân phối tải, phát hiện server không khỏe và mô tả vị trí xử lý TLS. Bạn cũng có thể kiểm tra cú pháp, quan sát log/thống kê và thực hành tình huống một backend ngừng phản hồi để hiểu cách duy trì dịch vụ.