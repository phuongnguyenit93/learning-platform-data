# Code Quality Continuous Inspection SonarQube

SonarQube là công cụ phân tích mã tĩnh giúp nhóm phát triển theo dõi chất lượng và bảo mật mã nguồn qua nhiều lần build. Trong *continuous inspection*, kết quả phân tích được đưa vào quy trình phát triển thường xuyên để phát hiện vấn đề mới, đánh giá thay đổi và tránh tích lũy các lỗi khó bảo trì. Module phù hợp với người học Java đã biết cách build, kiểm thử và sử dụng Git ở mức cơ bản.

Bạn sẽ bắt đầu bằng việc thiết lập dự án trên SonarQube Server, kết nối SonarScanner với Gradle hoặc Maven và đọc kết quả phân tích Java. Tiếp đó là cách hoạt động của rules, Quality Profiles, issues và các chỉ số như duplication, coverage. Trọng tâm cuối cùng là New Code, Quality Gate và cách tích hợp phân tích vào CI/CD để kiểm tra chất lượng mỗi lần mã thay đổi.

Sau module, bạn có thể chạy một lượt phân tích có thể kiểm chứng, giải thích vì sao một issue được phát hiện, đánh giá kết quả theo Quality Gate và đề xuất cách sửa, đo lại sau thay đổi. Với phân tích nhánh hoặc pull request, cần xét tính năng được hỗ trợ bởi phiên bản SonarQube đang sử dụng.