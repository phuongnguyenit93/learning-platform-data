# Observability Telemetry Governance Sanitization Redaction

Redaction trong telemetry là việc loại bỏ dữ liệu nhạy cảm khỏi thông tin quan sát hệ thống trước khi thông tin đó được lưu trữ, chia sẻ hoặc chuyển sang dịch vụ bên ngoài. Dữ liệu cần kiểm soát có thể xuất hiện trong log message, span attributes, metric attributes, URL hoặc các trường ngữ cảnh. Mục tiêu là ngăn lộ thông tin cá nhân, token và bí mật hệ thống mà vẫn giữ những tín hiệu cần thiết để chẩn đoán sự cố.

Module dành cho lập trình viên, kỹ sư vận hành và người thiết kế pipeline observability đã có kiến thức cơ bản về logs, metrics và traces. Người học tập trung nhận diện trường nhạy cảm, xây dựng chính sách xóa theo trường hoặc theo mẫu, đồng thời hiểu giới hạn của các quy tắc so khớp. Redaction cần được áp dụng sớm và kiểm chứng trên dữ liệu thực tế đã được thay bằng dữ liệu thử nghiệm an toàn.

Lộ trình bắt đầu từ rủi ro rò rỉ và phân loại dữ liệu, sau đó đi qua chính sách, redaction theo trường, redaction theo mẫu và cách triển khai trong OpenTelemetry Collector. Cuối cùng, người học kiểm thử đầu ra và duy trì quy tắc khi cấu trúc telemetry thay đổi, để vừa bảo vệ dữ liệu vừa giữ giá trị quan sát hệ thống.