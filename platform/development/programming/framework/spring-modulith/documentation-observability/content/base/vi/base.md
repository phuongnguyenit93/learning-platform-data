# Spring Modulith Documentation Observability

Spring Modulith hỗ trợ tạo tài liệu kiến trúc và quan sát hoạt động của các application module trong ứng dụng Spring Boot. Từ cùng một mô hình module, bạn có thể sinh sơ đồ và bản tóm tắt cấu trúc, đồng thời theo dõi những tương tác xảy ra giữa các module khi ứng dụng chạy.

Module này dành cho người đã biết Spring Boot và các khái niệm application module, phụ thuộc giữa module và sự kiện ứng dụng. Lộ trình bắt đầu bằng `ApplicationModules`, tiếp đến là sinh sơ đồ C4/UML, Application Module Canvas và tài liệu Asciidoc qua `Documenter`. Phần vận hành đi vào endpoint Actuator, cấu hình observability, trace các lời gọi liên module và metric về sự kiện.

Sau khi học, bạn có thể tạo bộ tài liệu kiến trúc có thể tái sinh từ mã nguồn, đọc metadata module tại runtime và đối chiếu trace/metric với một luồng xử lý thực tế. Trọng tâm là giúp cấu trúc kiến trúc dễ hiểu, dễ kiểm tra và dễ quan sát khi hệ thống vận hành.