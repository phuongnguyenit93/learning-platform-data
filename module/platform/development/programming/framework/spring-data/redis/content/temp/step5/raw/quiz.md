Câu 1. Trong Spring Boot, starter nào phù hợp để dùng `RedisTemplate` với Redis?
A. Thêm `spring-boot-starter-data-mongodb` để tạo Redis client.
B. Thêm `spring-boot-starter-data-redis` vào ứng dụng.
C. Thêm `spring-boot-starter-data-jpa` cùng Redis URL.
D. Thêm `spring-boot-starter-cache` thay cho Redis driver.
Đáp án đúng: B

Câu 2. Với Spring Boot 3.x, property nào cấu hình hostname Redis standalone?
A. Dùng `spring.redis.sentinel.master` làm hostname server.
B. Dùng `spring.data.redis.cluster.nodes` với tên host đơn.
C. Dùng `spring.data.redis.host` trong application config.
D. Dùng `spring.cache.redis.host` cho kết nối dữ liệu.
Đáp án đúng: C

Câu 3. Khi chọn driver Lettuce, bean nào quản lý kết nối Redis cho `RedisTemplate`?
A. Sử dụng `RedisStandaloneConfiguration` làm bean connection.
B. Sử dụng `LettuceConnectionFactory` phù hợp cấu hình.
C. Sử dụng `RedisMessageListenerContainer` làm data connection.
D. Sử dụng `RedisCacheManager` thay cho connection factory.
Đáp án đúng: B

Câu 4. Vì sao `StringRedisTemplate` phù hợp khi đọc ghi khóa và giá trị dạng chuỗi?
A. Nó mặc định ghi value thành JSON có type metadata.
B. Nó mặc định biến value thành Redis Hash nhiều field.
C. Nó mặc định dùng JDK serialization cho cả key và value.
D. Nó mặc định dùng string serializer cho key và value.
Đáp án đúng: D

Câu 5. Ứng dụng lưu `Order` bằng RedisTemplate và nhiều service cần đọc; cách serialize nào phù hợp?
A. Dùng JDK serialization mặc định cho client khác ngôn ngữ.
B. Dùng key serializer để chuyển value thành Redis Stream.
C. Dùng string serializer trực tiếp cho Java object `Order`.
D. Cấu hình JSON serializer có schema tương thích rõ ràng.
Đáp án đúng: D

Câu 6. Thiết kế Redis key cho giỏ hàng nhiều tenant cần tránh va chạm; mẫu nào phù hợp?
A. Dùng namespace có tenant và ID, ví dụ `cart:t1:u42`.
B. Dùng cùng key user ID tại các tenant và chọn database 0.
C. Dùng key theo timestamp hiện tại nhưng bỏ user ID.
D. Dùng key `cart` và đặt tenant ID ở Redis value.
Đáp án đúng: A

Câu 7. Muốn ghi và đọc một chuỗi đơn giản qua `RedisTemplate`, API nào phù hợp?
A. Gọi `opsForHash().put()` và `opsForHash().get()`.
B. Gọi `opsForZSet().add()` và `opsForZSet().score()`.
C. Gọi `opsForStream().add()` và `opsForStream().read()`.
D. Gọi `opsForValue().set()` và `opsForValue().get()`.
Đáp án đúng: D

Câu 8. Cần cập nhật một field của Redis Hash mà không ghi lại toàn object; API nào phù hợp?
A. Dùng `opsForValue().set(key, field, value)`.
B. Dùng `opsForSet().add(key, field, value)`.
C. Dùng `opsForHash().put(key, field, value)`.
D. Dùng `opsForList().rightPush(key, field)`.
Đáp án đúng: C

Câu 9. Cần lưu tập ID người theo dõi không trùng nhau; cấu trúc nào phù hợp?
A. Dùng Redis Set thông qua `opsForSet().add()`.
B. Dùng Redis Stream thông qua `opsForStream().add()`.
C. Dùng Redis Sorted Set với score ngẫu nhiên cho mỗi ID.
D. Dùng Redis List thông qua `opsForList().rightPush()`.
Đáp án đúng: A

Câu 10. Bảng xếp hạng điểm cần truy xuất top người chơi; cấu trúc nào hợp lý?
A. Dùng Redis Sorted Set với score làm điểm xếp hạng.
B. Dùng Redis Stream và coi stream ID là điểm xếp hạng.
C. Dùng Redis Set không có score rồi đọc theo thứ tự ghi.
D. Dùng Redis Hash với field name làm thứ tự xếp hạng.
Đáp án đúng: A

Câu 11. Muốn xử lý hàng đợi FIFO đơn giản bằng Redis List, cặp thao tác nào phù hợp?
A. `rightPush` để enqueue, `rightPop` để dequeue.
B. `set` để enqueue, `get` để dequeue rồi xóa key.
C. `leftPush` để enqueue, `leftPop` để dequeue.
D. `rightPush` để enqueue, `leftPop` để dequeue.
Đáp án đúng: D

Câu 12. Trên Redis có hàng triệu key, cần quét key theo namespace; cách nào an toàn hơn?
A. Dùng `KEYS pattern` trong request online có latency thấp.
B. Dùng `FLUSHDB` rồi đọc key còn lại theo từng đợt.
C. Dùng `SCAN` với cursor và pattern, xử lý theo từng đợt.
D. Dùng `GET pattern` để server liệt kê key có tiền tố.
Đáp án đúng: C

Câu 13. Khi dùng Spring Data Redis repository, annotation nào khai báo entity dạng hash?
A. Dùng `@Document("customers")` để tạo Redis Hash repository.
B. Dùng `@Entity("customers")` để ánh xạ Redis key-value.
C. Dùng `@RedisHash("customers")` cùng identifier của entity.
D. Dùng `@Table("customers")` để tạo Redis Hash repository.
Đáp án đúng: C

Câu 14. Cache hit giảm và Redis latency tăng, nhóm tín hiệu nào nên kiểm tra?
A. Quan sát JVM classloader, tốc độ compile và file JAR.
B. Quan sát số SQL join, JDBC index scan và DB migrations.
C. Quan sát số queue Kafka, consumer lag và producer batch.
D. Quan sát hit/miss, eviction, memory và độ trễ lệnh Redis.
Đáp án đúng: D

Câu 15. Với Spring Data Redis repository, field `@TimeToLive` kiểu số thường điều khiển gì?
A. Thời gian sống của key Redis gắn với entity, mặc định giây.
B. Thời gian Redis giữ kết nối TCP trong connection pool.
C. Thời gian chờ khóa WATCH trước khi gọi lệnh MULTI.
D. Thời gian chờ socket khi repository kết nối Redis server.
Đáp án đúng: A

Câu 16. Muốn đặt TTL 5 phút cho một key bằng RedisTemplate, thao tác nào phù hợp?
A. Gọi `getExpire(key)` để kích hoạt thời gian sống.
B. Gọi `persist(key)` để đặt thời điểm hết hạn.
C. Gọi `expire(key, Duration.ofMinutes(5))` trên template.
D. Gọi `rename(key, "ttl:300")` để server tự áp thời gian.
Đáp án đúng: C

Câu 17. Với Spring Cache có `@EnableCaching`, `@Cacheable` hoạt động thế nào khi có cache hit?
A. Xóa entry trước khi gọi method và không lưu kết quả.
B. Trả kết quả trong cache và bỏ qua thực thi method mục tiêu.
C. Cache exception từ method để bỏ qua lần gọi sau.
D. Gọi method rồi cập nhật cache mỗi lần, kể cả khi có hit.
Đáp án đúng: B

Câu 18. Khi cập nhật sản phẩm trong DB, annotation nào giúp xóa cache entry tương ứng?
A. Dùng `@CacheEvict` với cache name và key phù hợp.
B. Dùng `@Cacheable` để ép entry hiện tại bị xóa.
C. Dùng `@RedisHash` để xóa toàn bộ cache của ứng dụng.
D. Dùng `@CachePut` để xóa entry mà không thực thi method.
Đáp án đúng: A

Câu 19. Muốn cấu hình TTL 10 phút riêng cho cache Redis, API nào phù hợp?
A. Dùng `RedisTemplate.getExpire(key)` cho toàn bộ cache.
B. Dùng `RedisCacheConfiguration.entryTtl(Duration.ofMinutes(10))`.
C. Dùng `LettuceConnectionFactory.setTimeout(Duration...)`.
D. Dùng `RedisMessageListenerContainer.setRecoveryInterval(...)`.
Đáp án đúng: B

Câu 20. Vì sao `@Cacheable` có thể không chạy khi một method cùng bean tự gọi method khác có annotation?
A. Redis Cache Manager giới hạn một method cache trên mỗi bean.
B. Spring Cache tắt serialization khi method gọi từ cùng class.
C. RedisTemplate xóa entry trước khi method nội bộ chạy.
D. Lời gọi nội bộ bỏ qua Spring proxy thực hiện cache advice.
Đáp án đúng: D

Câu 21. Một subscriber Redis Pub/Sub tạm offline, điều nào cần lưu ý?
A. Redis Pub/Sub lưu pending message để subscriber nhận khi online.
B. Message đã publish lúc subscriber offline không được replay.
C. Subscriber nhận lại message nhờ consumer group offset mặc định.
D. Pub/Sub chuyển message chưa ACK sang Redis Stream bền vững.
Đáp án đúng: B

Câu 22. Muốn lưu event có thể đọc lại sau khi consumer offline, tính năng Redis nào phù hợp?
A. Dùng Redis Streams với record ID và consumer group thích hợp.
B. Dùng Redis Keyspace Notification thay stream lưu trữ sự kiện.
C. Dùng Redis String SET với một key chung ghi đè message.
D. Dùng Redis Pub/Sub với subscriber mới để tải lại lịch sử.
Đáp án đúng: A

Câu 23. Sau khi consumer group xử lý một Stream record thành công, `XACK` có tác dụng gì?
A. Xóa consumer group và đặt lại ID đọc từ đầu Stream.
B. Phát record cho Pub/Sub subscriber ở kênh khác.
C. Xóa record khỏi Stream khiến các group khác mất dữ liệu.
D. Gỡ record khỏi pending entries list của consumer group.
Đáp án đúng: D

Câu 24. Consumer Streams chết trước khi ACK; cách phục hồi message pending nào phù hợp?
A. Dùng `XGROUP DESTROY` để ACK các record chưa hoàn tất.
B. Dùng `PUBLISH` lại payload cho consumer group pending.
C. Dùng `XADD` với ID mới để Redis tự xóa pending cũ.
D. Dùng `XAUTOCLAIM` nhận lại entry idle trong pending list.
Đáp án đúng: D

Câu 25. Với Redis `MULTI` và `EXEC`, cách hiểu transaction nào đúng?
A. Thực thi các lệnh đã queue liên tiếp, không có rollback SQL.
B. Đảm bảo transaction còn hiệu lực sau failover sang replica.
C. Gộp các lệnh thành transaction ACID với rollback khi lệnh lỗi.
D. Chạy từng lệnh ngay lúc MULTI được gọi mà không queue.
Đáp án đúng: A

Câu 26. Để cập nhật giá trị khi dữ liệu chưa bị client khác sửa, Redis hỗ trợ gì?
A. Dùng `SCAN` trước `MULTI/EXEC` để chặn writer cạnh tranh.
B. Dùng `WATCH` trước `MULTI/EXEC` để phát hiện key đổi.
C. Dùng `PERSIST` trước `MULTI/EXEC` để khóa key.
D. Dùng `EVAL` trước `MULTI/EXEC` để bỏ kiểm tra phiên bản.
Đáp án đúng: B

Câu 27. Trong Spring Data Redis, muốn các thao tác `MULTI/EXEC` trên cùng connection, nên dùng gì?
A. Dùng hai `RedisTemplate` tách biệt để mỗi lệnh có kết nối.
B. Dùng `SessionCallback` với `RedisTemplate.execute()`.
C. Dùng `@Cacheable` để giữ Redis connection trong transaction.
D. Dùng `StreamMessageListenerContainer` để quản lý MULTI.
Đáp án đúng: B

Câu 28. Pipelining các lệnh Redis có lợi ích và giới hạn nào?
A. Thay đổi key serializer thành binary để giảm kích thước mạng.
B. Biến lệnh thành transaction có rollback ở mức command.
C. Giảm số lượt round trip mạng nhưng không tự tạo transaction.
D. Buộc Redis xử lý song song lệnh trên nhiều thread của shard.
Đáp án đúng: C

Câu 29. Muốn tăng counter và đặt TTL khi counter mới được tạo mà không có race giữa hai lệnh, dùng gì?
A. Dùng pipelining `INCR`/`EXPIRE` để tự đảm bảo atomicity.
B. Gọi `INCR` rồi `EXPIRE` tách rời và giả định cùng transaction.
C. Thực thi Lua script qua `RedisScript` để cập nhật nguyên tử.
D. Gọi `GET` rồi `SET` hai lần để giữ counter cùng TTL.
Đáp án đúng: C

Câu 30. Trong Redis replication bất đồng bộ, khi primary lỗi và failover có rủi ro nào?
A. Write vừa ACK có thể mất nếu chưa được replica nhận.
B. Client phải xóa toàn bộ key trước khi nối tới primary mới.
C. Replica không thể được thăng primary khi node cũ mất.
D. Write đã ACK đồng nghĩa replica nhận đủ quorum mặc định.
Đáp án đúng: A

Câu 31. Redis Cluster yêu cầu hai key cùng hash slot để multi-key operation hoạt động; cách thiết kế nào phù hợp?
A. Dùng cùng RedisSerializer cho hai key để slot tự khớp.
B. Dùng hash tag chung như `cart:{u42}:a` và `cart:{u42}:b`.
C. Dùng cùng TTL cho hai key để cluster đặt chúng một slot.
D. Dùng tiền tố chung như `cart:u42:a` và `cart:u42:b` là đủ.
Đáp án đúng: B

Câu 32. Muốn kiểm chứng serialization, TTL và Stream consumer với Redis thật trong CI, cách nào phù hợp?
A. Dùng H2 in-memory để kiểm tra Redis transaction và Stream.
B. Kiểm tra annotation `@RedisHash` thay cho Redis runtime.
C. Dùng Redis Testcontainers rồi assert các thao tác trong test.
D. Mock `RedisTemplate` rồi coi kết quả TTL tương đương Redis.
Đáp án đúng: C
