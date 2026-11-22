# Database Schema Migration Fundamentals

Database schema migration là quy trình quản lý có phiên bản các thay đổi cấu trúc và dữ liệu của cơ sở dữ liệu khi ứng dụng phát triển. Thay vì sửa bảng thủ công ở mỗi môi trường, nhóm phát triển lưu các migration cùng mã nguồn, thực thi theo thứ tự và theo dõi lịch sử để giữ schema nhất quán giữa development, testing và production.

Module này phù hợp với người đã biết SQL, bảng, khóa và giao dịch cơ bản. Bạn sẽ học cách phân biệt DDL với data migration, đặt tên và quản lý changelog, làm quen Flyway và Liquibase, xác định phụ thuộc giữa các thay đổi, hiểu ảnh hưởng của lock/transaction, rồi áp dụng expand–contract để triển khai tương thích với nhiều phiên bản ứng dụng.

Kết thúc lộ trình, bạn có thể chuẩn bị một chuỗi migration nhỏ, kiểm tra kết quả trên database thử nghiệm, tích hợp bước migration vào CI/CD và lập phương án rollback, roll-forward hoặc khôi phục khi có sự cố. Trọng tâm là an toàn dữ liệu và khả năng tái lập; hành vi DDL và giao dịch thực tế cần được xác minh với từng hệ quản trị cơ sở dữ liệu.