# Network Proxy Fundamentals

Proxy là thành phần trung gian nhận lưu lượng từ một phía và chuyển tiếp đến phía còn lại. Trong hệ thống mạng và ứng dụng web, proxy có thể giúp kiểm soát truy cập, định tuyến, cân bằng tải, mã hóa hoặc tối ưu cách truyền dữ liệu. Để thiết kế và vận hành đúng, người học cần hiểu vị trí của proxy trong luồng kết nối và thông tin nào được giữ lại khi một request đi qua nhiều hop.

Module này bắt đầu với vai trò của proxy, sau đó phân biệt **forward proxy** và **reverse proxy**, cùng cách hoạt động ở **L4 (TCP)** và **L7 (HTTP)**. Bạn sẽ tìm hiểu định tuyến và header chuyển tiếp, cân bằng tải và health checks, TLS và kiểm soát truy cập, rồi đến caching, buffering, timeouts và retries. Phần cuối tập trung vào logs và các chỉ số giúp xác định lỗi xuất phát từ client, proxy hay backend.

Lộ trình dành cho lập trình viên backend, kỹ sư mạng, DevOps và người học về hạ tầng. Sau khi hoàn thành, bạn có thể phác họa kiến trúc proxy phù hợp với nhu cầu, giải thích các quyết định định tuyến và bảo vệ kết nối, đồng thời chẩn đoán những sự cố proxy phổ biến trước khi đi sâu vào các công cụ như NGINX hoặc HAProxy.