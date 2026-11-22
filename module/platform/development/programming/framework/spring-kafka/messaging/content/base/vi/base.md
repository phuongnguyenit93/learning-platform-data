# Spring Kafka Messaging

Spring Kafka Messaging giúp ứng dụng Java giao tiếp bất đồng bộ qua Apache Kafka bằng các abstraction quen thuộc của Spring. Thay vì quản lý trực tiếp toàn bộ producer và consumer API, bạn dùng `KafkaTemplate`, `@KafkaListener` và cấu hình Spring để truyền các record có key, payload, header và topic rõ ràng.

Module phù hợp với người đã biết Java, Spring Boot và nguyên lý xử lý sự kiện cơ bản. Lộ trình bắt đầu từ luồng bản tin, topic, partition và offset; tiếp theo là thiết lập Spring Kafka, xuất bản message, serialization/JSON, nhận message bằng listener, phân phối qua consumer group và lựa chọn listener theo record hoặc batch.

Kết thúc module, bạn có thể xây dựng một luồng gửi–nhận dữ liệu trên Kafka và kiểm thử tích hợp với broker thử nghiệm. Trọng tâm là hiểu đúng hợp đồng dữ liệu, đường đi của bản tin và cách Spring Kafka kết nối producer với consumer; các chủ đề về retry, xử lý lỗi nâng cao và vận hành tin cậy được học riêng.