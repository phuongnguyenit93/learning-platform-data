# Spring Data Commons

Spring Data Commons cung cấp các abstraction dùng chung cho hệ sinh thái Spring Data, như repository, truy vấn theo tên phương thức, phân trang, sắp xếp, projection và auditing. Đây là nền tảng giúp các ứng dụng Spring tổ chức truy cập dữ liệu nhất quán giữa nhiều công nghệ lưu trữ; để thực thi truy vấn trên cơ sở dữ liệu thực tế, ứng dụng vẫn cần module tương ứng như Spring Data JPA hoặc MongoDB.

Module phù hợp với người đã biết Java, Spring Boot và khái niệm entity cùng repository. Lộ trình đi từ những interface nền tảng và CRUD đến derived query methods, Pageable/Sort, projection, Query by Example, thông tin auditing và cách mở rộng repository bằng custom fragment. Các khả năng cụ thể có thể khác nhau giữa từng data store nên mỗi ví dụ cần được đối chiếu với module sử dụng.

Sau khi hoàn thành, bạn có thể chọn đúng abstraction cho yêu cầu đọc–ghi, định nghĩa repository có kiểu dữ liệu rõ ràng và viết kiểm thử cho phân trang, truy vấn, projection, auditing và phương thức tùy biến trên một data store cụ thể.