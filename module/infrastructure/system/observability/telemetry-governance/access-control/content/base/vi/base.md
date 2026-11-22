# Observability Telemetry Governance Access Control

Access Control trong quản trị telemetry xác định **ai được thu thập, gửi, xem, truy vấn hoặc thay đổi** dữ liệu quan sát và cấu hình liên quan. Metrics, logs và traces có thể tiết lộ thông tin về hệ thống, người dùng và luồng xử lý, vì vậy quyền truy cập cần được áp dụng xuyên suốt từ ứng dụng, Collector, kho lưu trữ đến dashboard và API.

Lộ trình dành cho lập trình viên, kỹ sư nền tảng, SRE và người quản trị hệ thống observability. Bạn sẽ nhận diện tài nguyên và danh tính, chọn cách xác thực, thiết kế phân quyền tối thiểu, bảo vệ đầu vào telemetry, kiểm soát truy vấn, tách biệt môi trường và tenant, rồi quản lý vòng đời credentials.

Sau khi học, bạn có thể xây dựng ma trận quyền phù hợp cho hệ thống quan sát, kiểm thử các trường hợp truy cập bị từ chối và thiết lập kiểm toán để phát hiện, điều chỉnh những quyền cấp quá rộng. Các kỹ thuật cụ thể cần được đối chiếu với khả năng và phiên bản của nền tảng đang sử dụng.