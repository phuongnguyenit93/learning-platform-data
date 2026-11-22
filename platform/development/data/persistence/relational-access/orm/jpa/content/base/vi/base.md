# Data Persistence Relational Access ORM JPA

JPA (Jakarta Persistence) là chuẩn của Java cho ánh xạ đối tượng với dữ liệu quan hệ. Thông qua `EntityManager` và persistence context, bạn có thể quản lý vòng đời Entity, truy vấn và đồng bộ thay đổi xuống cơ sở dữ liệu mà không buộc mã nghiệp vụ gắn với một persistence provider cụ thể.

Module phù hợp với người đã nắm Java hướng đối tượng, SQL cơ bản và khóa ngoại trong CSDL quan hệ. Nội dung đi từ khái niệm JPA và cấu hình ban đầu, ánh xạ Entity, quan hệ giữa các bảng đến quản lý trạng thái, JPQL/Criteria, giao dịch, khóa và chiến lược nạp dữ liệu.

Lộ trình gồm tám mốc ngắn và kết thúc bằng thực hành CRUD có quan hệ Entity. Sau khi học, bạn nên giải thích được SQL do JPA tạo ra, kiểm tra hành vi lưu/truy vấn/rollback và nhận diện những truy vấn gây dư thừa như N+1.