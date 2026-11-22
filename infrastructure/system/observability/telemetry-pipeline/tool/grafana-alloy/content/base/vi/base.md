# Observability Telemetry Pipeline Tool Grafana Alloy

Grafana Alloy là công cụ thu thập và chuyển tiếp dữ liệu quan sát, được xây dựng trên nền OpenTelemetry Collector và tích hợp các pipeline Prometheus, Loki cùng những thành phần liên quan. Công cụ cho phép tạo luồng thu thập, xử lý và xuất metrics, logs, traces hoặc profiles đến backend phù hợp thông qua các components được nối với nhau trong cấu hình.

Lộ trình dành cho lập trình viên, kỹ sư vận hành, SRE và người xây dựng nền tảng observability đã biết các tín hiệu telemetry cơ bản. Bạn sẽ tìm hiểu vai trò của Alloy, cách cài đặt và cấu hình, xây dựng pipeline metrics, logs, traces/OTLP, sau đó áp dụng xử lý và định tuyến dữ liệu.

Khi hoàn thành, bạn có thể tự xây dựng pipeline Alloy ở mức cơ bản, xác minh dữ liệu đến được đích nhận, quan sát tình trạng components và xử lý các lỗi thường gặp. Cấu hình receiver, processor và exporter cần được chọn theo loại dữ liệu và hệ thống backend thực tế.