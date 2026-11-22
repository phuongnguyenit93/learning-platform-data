# Error Prone — Phân tích tĩnh trong Java Compiler

Error Prone là công cụ phân tích tĩnh cho Java, tích hợp vào trình biên dịch `javac` để tìm các mẫu lỗi (*bug patterns*) ngay khi mã nguồn được biên dịch. Công cụ mở rộng kiểm tra thông thường của trình biên dịch bằng các quy tắc phát hiện lỗi logic, cách dùng API dễ nhầm và những vấn đề có thể gây lỗi trong thực tế. Kết quả được đưa ra dưới dạng chẩn đoán có tên check, vị trí mã và mức nghiêm trọng.

Module này dành cho người đã biết lập trình Java, hiểu quy trình biên dịch và muốn ngăn lỗi trước khi mã được tích hợp. Bạn sẽ học cách kích hoạt Error Prone trong Gradle hoặc Maven, đọc chẩn đoán, nhận diện các bug pattern quan trọng và tùy chỉnh checks. Mỗi cảnh báo cần được xem xét dựa trên hành vi thực tế của đoạn mã; suppression chỉ phù hợp khi có lý do rõ ràng.

Phần thực hành tập trung vào sửa lỗi, kiểm tra gợi ý tự động và duy trì Error Prone trong CI. Sau module, bạn có thể giải thích các phát hiện phổ biến, xử lý lỗi có cơ sở và đưa phân tích tĩnh vào bước biên dịch của dự án Java.