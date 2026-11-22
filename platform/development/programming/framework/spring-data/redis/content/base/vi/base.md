# Spring Data Redis

Spring Data Redis cung cấp các API giúp ứng dụng Java và Spring Boot làm việc với Redis — một kho dữ liệu hỗ trợ nhiều cấu trúc như String, Hash, List, Set và Sorted Set. Thay vì tự quản lý từng lệnh và kết nối, người học có thể sử dụng `RedisTemplate`, `RedisRepository` và các tích hợp sẵn của Spring. Module này dành cho người đã biết Java, Spring Boot và khái niệm lưu trữ dữ liệu cơ bản.

Lộ trình đi từ mô hình dữ liệu Redis và cấu hình driver, sang thao tác với `RedisTemplate`, lựa chọn serializer và ánh xạ đối tượng. Sau đó bạn học cách dùng repository, TTL, `RedisCacheManager`, Pub/Sub và Redis Streams cho những nhu cầu khác nhau. Phần cuối giới thiệu transaction, pipelining và các giới hạn khi vận hành, bao gồm khác biệt giữa repository với transaction support và sự đánh đổi khi sử dụng Redis Cluster.

Sau khi học, bạn có thể kết nối một ứng dụng Spring với Redis, triển khai các thao tác đọc/ghi và cache có thời hạn, chọn cách truyền thông điệp phù hợp, đồng thời kiểm thử kết quả sau lỗi hoặc hết hạn. Bạn cũng biết vì sao cần chủ động cấu hình serialization và không mặc định xem Redis là nơi lưu trữ thay thế cho mọi mô hình dữ liệu quan hệ.