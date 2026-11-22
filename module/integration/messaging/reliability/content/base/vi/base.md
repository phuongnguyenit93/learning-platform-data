# Integration Messaging Reliability

**Messaging Reliability** là khả năng hệ thống gửi, lưu trữ và xử lý thông điệp đúng kỳ vọng ngay cả khi mạng, broker, producer hoặc consumer gặp sự cố. Độ tin cậy không chỉ phụ thuộc vào message broker: ứng dụng còn phải hiểu bảo đảm phân phối, xác nhận xử lý, phát lại, dữ liệu bền vững và cách tránh thực thi nghiệp vụ nhiều lần.

Lộ trình gồm **8 mốc**: delivery semantics; độ bền khi publish; ACK và offset; retry với backoff; dead-letter queue và replay; idempotency và chống trùng; ordering cùng transactional outbox; cuối cùng là giám sát và thử nghiệm phục hồi. Mỗi mốc kết hợp khái niệm với tình huống kiểm chứng như mất kết nối, consumer crash hoặc nhận lại message, qua đó đánh giá rủi ro mất, trùng và xử lý sai thứ tự.

Học phần dành cho người đã biết producer, consumer, queue/topic và kiến thức cơ bản về hệ thống phân tán. Sau khi học, bạn có thể lựa chọn bảo đảm phân phối phù hợp, đặt điểm ACK/commit đúng, thiết kế retry và DLQ có giới hạn, xử lý idempotent, giám sát consumer lag và xác minh luồng sự kiện chịu lỗi bằng các bài thử thực tế.