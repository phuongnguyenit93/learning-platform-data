# Data Persistence Non Relational Access

Dữ liệu phi quan hệ không chỉ có một kiểu lưu trữ. Tùy bài toán, ứng dụng Java có thể truy cập cơ sở dữ liệu document, key-value, wide-column hoặc graph. Module này giới thiệu cách lựa chọn mô hình, thiết kế dữ liệu và thực hiện các thao tác đọc/ghi với API hoặc driver phù hợp. MongoDB, Redis, Apache Cassandra và Neo4j là những hệ đại diện để thực hành, không phải một bộ API thống nhất.

Bạn nên biết Java cơ bản, thao tác dữ liệu và khái niệm database. Lộ trình bắt đầu từ các mô hình NoSQL, cách tổ chức khóa và dữ liệu, rồi thiết lập Java client hoặc Spring Data. Tiếp đó, bạn thực hành truy cập document/key-value, dữ liệu theo partition và graph, tối ưu truy vấn với index, và kiểm tra đặc tính nhất quán cũng như transaction theo từng hệ quản trị.

Khi hoàn thành, bạn có thể chọn cách truy cập NoSQL dựa trên nhu cầu ứng dụng, viết các thao tác CRUD/truy vấn có kiểm soát và nhận biết những vấn đề thường gặp về index, phân trang, hiệu năng, bảo mật kết nối và tính nhất quán.