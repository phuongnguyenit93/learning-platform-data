# Spring Data Relational R2DBC

Spring Data R2DBC cung cấp mô hình truy cập cơ sở dữ liệu quan hệ theo hướng reactive, giúp ứng dụng xử lý các thao tác SQL qua các chuỗi dữ liệu bất đồng bộ. Module này làm rõ vai trò của đặc tả R2DBC, cách Spring Data ánh xạ entity và cách sử dụng repository, template hay SQL trực tiếp mà vẫn giữ luồng xử lý non-blocking.

Lộ trình gồm tám mốc: nền tảng Reactive SQL, cấu hình kết nối, entity mapping, reactive repository, query và template, kết hợp pipeline, giao dịch reactive, cuối cùng là kiểm thử và vận hành. Người học sẽ đi từ một truy vấn đơn giản đến các thao tác dữ liệu có xử lý lỗi và transaction, đồng thời nhận diện những khác biệt thiết kế so với JDBC hoặc JPA.

Module phù hợp với lập trình viên Java đã biết Spring, SQL và các khái niệm Mono/Flux cơ bản. Sau khi hoàn thành, bạn có thể xây dựng tầng truy cập dữ liệu bằng Spring Data R2DBC, kiểm thử thao tác bất đồng bộ và phân tích các vấn đề liên quan đến kết nối, mapping, transaction và hiệu năng.