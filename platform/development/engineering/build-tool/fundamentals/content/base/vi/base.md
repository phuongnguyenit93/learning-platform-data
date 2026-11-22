# Build Tool Fundamentals

Build Tool là công cụ tự động hóa quá trình biến mã nguồn thành sản phẩm phần mềm có thể kiểm thử, đóng gói và phân phối. Thay vì thực hiện thủ công nhiều lệnh rời rạc, nhóm phát triển mô tả các bước build và mối quan hệ giữa chúng để có thể chạy nhất quán trên máy cá nhân cũng như trong môi trường tích hợp liên tục (CI).

Module này giới thiệu nền tảng chung của hệ thống build: quy trình compile–test–package, cấu trúc và cấu hình dự án, task và vòng đời build, quản lý dependency, plugin, tối ưu tốc độ và khả năng tái lập kết quả. Các khái niệm được trình bày độc lập với cú pháp của một công cụ cụ thể; Ant, Maven và Gradle có thể được tìm hiểu sâu hơn ở các module riêng.

Người học nên có kiến thức cơ bản về mã nguồn, thư viện và dòng lệnh. Sau khi hoàn thành lộ trình, bạn có thể đọc cấu hình build ở mức khái quát, giải thích các bước thực thi, xác định nguyên nhân thường gặp khi build lỗi và hiểu cách một dự án sử dụng build trong CI.