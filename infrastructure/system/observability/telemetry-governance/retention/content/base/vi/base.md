# Observability Telemetry Governance Retention

Telemetry retention là chính sách quyết định dữ liệu observability được giữ trong bao lâu, ở đâu và khi nào phải xóa. Với logs, metrics và traces, thời hạn lưu giữ phù hợp giúp đội kỹ thuật điều tra sự cố và phân tích xu hướng, đồng thời kiểm soát chi phí lưu trữ và giới hạn dữ liệu tồn tại không cần thiết.

Module này dành cho lập trình viên, SRE và kỹ sư vận hành đã quen với các tín hiệu telemetry. Bạn sẽ học cách xác định nhu cầu tra cứu, phân loại dữ liệu, đặt thời hạn lưu giữ theo mục đích và mức độ nhạy cảm, rồi chọn tầng lưu trữ thích hợp. Phần triển khai giới thiệu cơ chế retention tiêu biểu của Prometheus, Loki, Tempo và Elasticsearch.

Lộ trình kết thúc bằng quản lý xóa và ngoại lệ, ước lượng dung lượng, giám sát quá trình dọn dẹp và lưu bằng chứng kiểm toán. Mục tiêu là thiết kế được một chính sách có thể thực thi và kiểm chứng trên cả dữ liệu đang dùng, dữ liệu lưu trữ dài hạn và các bản sao liên quan.