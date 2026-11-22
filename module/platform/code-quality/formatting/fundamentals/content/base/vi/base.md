# Code Quality Formatting Fundamentals

Code formatting là việc trình bày mã nguồn theo những quy tắc nhất quán về khoảng trắng, căn lề, ngắt dòng, dấu ngoặc và bố cục tệp. Khi các thành viên dùng cùng quy tắc, mã dễ đọc hơn, phần thay đổi trong bản review rõ ràng hơn và những khác biệt do trình soạn thảo được hạn chế. Formatting chủ yếu tác động đến cách mã được hiển thị; việc cải thiện thuật toán hoặc sửa lỗi cần được xem xét riêng.

Module này dành cho người đã biết viết và đọc mã nguồn cơ bản, đặc biệt trong môi trường phát triển nhóm. Nội dung đi từ mục đích và ranh giới của formatting đến quy ước khoảng trắng, dòng, khối lệnh, import và chú thích, sau đó là style guide, cấu hình dự án và sử dụng formatter tự động. Những tài liệu như EditorConfig và Google Java Style Guide được dùng để minh họa cách biến quy ước thành quy tắc có thể áp dụng nhất quán.

Qua bảy mốc học, bạn sẽ biết nhận diện khác biệt định dạng, thiết lập quy ước chung, chạy formatter ở chế độ kiểm tra hoặc sửa, đánh giá các thay đổi trong diff và đưa bước kiểm tra định dạng vào quy trình review/CI. Mục tiêu là xây dựng nền tảng trước khi tìm hiểu sâu một công cụ cụ thể như Spotless.