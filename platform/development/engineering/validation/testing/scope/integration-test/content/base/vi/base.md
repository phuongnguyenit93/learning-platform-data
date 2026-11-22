# Validation Testing Scope – Integration Test

Integration Test (kiểm thử tích hợp) đánh giá cách nhiều thành phần của hệ thống phối hợp để tạo ra hành vi đúng, chẳng hạn API gọi service, service lưu dữ liệu, hoặc ứng dụng trao đổi với hệ thống bên ngoài. Phạm vi này bổ sung cho Unit Test bằng việc kiểm tra tương tác thật giữa các lớp, module và tài nguyên, đồng thời có thể hẹp hơn một kịch bản End-to-End toàn hệ thống.

Module hướng dẫn cách chọn ranh giới tích hợp, thiết kế kịch bản và chuẩn bị môi trường, dữ liệu test có thể tái lập. Từ đó người học thực hành xác minh tương tác database, API, service, messaging và dịch vụ ngoài; kiểm tra các tình huống transaction, lỗi và trạng thái dữ liệu; cuối cùng xây dựng bộ test ổn định để chạy trên CI.

Nội dung dành cho developer, QA và tester đã biết viết test case cơ bản. Sau khi học, bạn có thể lựa chọn giữa phụ thuộc thực và test double theo mục tiêu, phát hiện lỗi tại điểm nối giữa các thành phần, tổ chức dọn dẹp dữ liệu và phân tích lỗi integration test trong môi trường tự động.