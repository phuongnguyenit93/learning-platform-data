# Observability Telemetry Pipeline Tool Logstash

Logstash là công cụ xử lý sự kiện trong hệ thống observability. Nó thu nhận dữ liệu từ các nguồn như file log hoặc Beats, giải mã và biến đổi event, sau đó chuyển tiếp tới hệ thống lưu trữ và phân tích. Module này giúp bạn hiểu và xây dựng pipeline Logstash theo mô hình input → filter → output, từ cấu hình cơ bản đến xử lý log có cấu trúc.

Lộ trình bắt đầu bằng vai trò Logstash và cách chạy một pipeline mẫu. Bạn sẽ lần lượt kết nối nguồn log, chọn codec, tách trường bằng Grok hoặc Dissect, chuẩn hóa thời gian, lọc/làm giàu sự kiện và cấu hình đầu ra an toàn. Các mốc cuối giới thiệu persistent queue, dead letter queue, điều chỉnh hiệu năng, monitoring API và kiểm thử để vận hành pipeline đáng tin cậy.

Module dành cho lập trình viên và kỹ sư vận hành đã biết khái niệm log và observability cơ bản. Sau khi học, bạn có thể triển khai pipeline phù hợp với nguồn dữ liệu, xác minh chất lượng bản ghi, chẩn đoán các lỗi xử lý và theo dõi tình trạng pipeline trong quá trình vận hành.