# Spring Data Couchbase

Spring Data Couchbase giúp ứng dụng Java và Spring Boot truy cập Couchbase, một cơ sở dữ liệu document hỗ trợ thao tác key-value theo ID và truy vấn SQL++. Thay vì tự ánh xạ JSON hay xử lý mọi lệnh từ SDK, bạn có thể sử dụng entity mapping, `CouchbaseTemplate`, repository và các API reactive. Module này dành cho người đã nắm Java, Spring Boot và những khái niệm dữ liệu cơ bản.

Lộ trình đi từ cấu trúc document, bucket/scope/collection và cách kết nối, đến ánh xạ entity cùng thao tác CRUD. Sau đó bạn học cách khai báo repository, viết truy vấn có chỉ mục phù hợp, quản lý TTL và lựa chọn giữa truy cập đồng bộ với reactive. Phần cuối tập trung vào kiểm soát cập nhật đồng thời bằng CAS, lựa chọn độ bền ghi và điều kiện để áp dụng giao dịch.

Kết thúc module, bạn có thể xây dựng tầng truy cập Couchbase cho một ứng dụng Spring, giải thích khi nào nên đọc theo ID hay truy vấn SQL++, sử dụng API tương ứng và kiểm thử các tình huống document không tồn tại, hết hạn hoặc bị cập nhật đồng thời.