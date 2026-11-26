Câu 1. Để Spring Boot tích hợp repository Cassandra, dependency nào phù hợp nhất?
A. Thêm `spring-boot-starter-data-cassandra` cho ứng dụng.
B. Thêm `spring-boot-starter-data-mongodb` cho Cassandra cluster.
C. Thêm `spring-boot-starter-data-jpa` rồi dùng CassandraRepository.
D. Thêm `spring-boot-starter-jdbc` rồi dùng CassandraTemplate.
Đáp án đúng: A

Câu 2. Trong Spring Data Cassandra, annotation nào ánh xạ class Java thành bảng?
A. Dùng `@MappedSuperclass` để đăng ký CQL table trực tiếp.
B. Dùng `@Table` trên class domain được lưu bằng Cassandra.
C. Dùng `@Entity` của JPA để quản lý Cassandra partition.
D. Dùng `@Document` trên class domain để tạo bảng CQL.
Đáp án đúng: B

Câu 3. Entity Cassandra có một khóa chính đơn giản `UUID id`; annotation nào phù hợp?
A. Gắn `@Version` để làm `id` thành partition key.
B. Gắn `@PrimaryKey` cho field `id` của entity.
C. Gắn `@IdClass` để định nghĩa partition key Cassandra.
D. Gắn `@GeneratedValue` để Cassandra tự cấp UUID.
Đáp án đúng: B

Câu 4. Entity dùng khóa tổng hợp; cách mapping Spring Data Cassandra nào đúng?
A. Định nghĩa `@IdClass` cùng `@GeneratedValue` cho khóa CQL.
B. Định nghĩa JPA `@EmbeddedId` rồi dùng JPA repository Cassandra.
C. Định nghĩa `@Table` lồng nhau rồi Cassandra tạo composite key.
D. Định nghĩa `@PrimaryKeyClass` rồi gắn `@PrimaryKey` cho field key.
Đáp án đúng: D

Câu 5. Trong `@PrimaryKeyColumn`, thuộc tính nào phân biệt partition với clustering?
A. Chọn `CascadeType.PERSIST` hoặc `MERGE` theo vị trí khóa.
B. Chọn `GenerationType.AUTO` hoặc `IDENTITY` để phân phối khóa.
C. Chọn `PrimaryKeyType.PARTITIONED` hoặc `CLUSTERED` đúng vai trò.
D. Chọn `FetchType.LAZY` hoặc `EAGER` cho từng thành phần khóa.
Đáp án đúng: C

Câu 6. Với khóa `(tenant_id, event_day)` làm partition key và `event_time` là clustering, truy vấn nào thuận lợi?
A. Lọc riêng `event_time` trên toàn bộ tenant để tìm phân vùng.
B. Lọc theo payload không có index rồi quét nhiều partition.
C. Lọc riêng `tenant_id` rồi ORDER BY các cột của nhiều ngày.
D. Lọc đủ `tenant_id`, `event_day` rồi lấy sự kiện theo thời gian.
Đáp án đúng: D

Câu 7. Chọn partition key chỉ từ một giá trị cố định cho dữ liệu ghi lớn gây vấn đề gì?
A. Clustering key bị vô hiệu và mọi record mất thứ tự.
B. Quá nhiều partition nhỏ khiến mỗi query phải fan-out.
C. Các mutation dùng lightweight transaction thay cho regular write.
D. Nhiều ghi dồn vào một partition, dễ tạo hotspot.
Đáp án đúng: D

Câu 8. Cần tra cứu đơn hàng theo `customer_id` nhưng bảng chính partition theo `order_id`; nên làm gì?
A. Tạo bảng truy vấn theo `customer_id` và đồng bộ dữ liệu phù hợp.
B. Đổi `consistency` thành `ALL` để tra phân vùng theo customer.
C. Gắn `ORDER BY customer_id` vào CQL của bảng theo `order_id`.
D. Dùng `ALLOW FILTERING` khi thiếu partition key trong production.
Đáp án đúng: A

Câu 9. Vì sao Cassandra thường thiết kế bảng theo mẫu truy vấn trước khi xây API?
A. Join đa bảng được CQL optimizer dùng để chọn access path.
B. Partition và clustering key chi phối đường đọc hiệu quả.
C. Optimizer tự chọn partition khác nếu truy vấn thiếu khóa.
D. Cassandra tự lập index đa cột cho tất cả trường khi ghi.
Đáp án đúng: B

Câu 10. Clustering column trong Cassandra chủ yếu ảnh hưởng đến điều gì?
A. Cách driver chọn datacenter làm local cho consistency.
B. Số partition được tạo mới sau mỗi lần commit batch.
C. Số lượng bản sao được lưu ở các datacenter của cluster.
D. Thứ tự lưu và khả năng sắp xếp các row trong một partition.
Đáp án đúng: D

Câu 11. Cần danh sách sự kiện gần nhất của một tenant theo ngày; mô hình nào phù hợp?
A. Partition theo giá trị status có ít loại, không theo tenant.
B. Partition theo payload JSON rồi sort bằng ORDER BY ngoài khóa.
C. Partition theo tenant/ngày và clustering theo thời gian.
D. Partition theo timestamp duy nhất rồi lọc tenant khi đọc.
Đáp án đúng: C

Câu 12. Cassandra thường chấp nhận nhân bản một phần dữ liệu qua nhiều bảng vì sao?
A. Đổi consistency level giúp truy vấn join hoạt động nhanh.
B. Mỗi bảng tối ưu đường truy vấn riêng, giảm nhu cầu join.
C. Replication của Cassandra chỉ hoạt động trên dữ liệu trùng.
D. Transaction nhiều bảng bảo đảm bản sao được cập nhật nguyên tử.
Đáp án đúng: B

Câu 13. Repository đơn giản cho entity `Event` có ID kiểu `EventKey` nên khai báo thế nào?
A. Cho interface kế thừa `JpaRepository<Event, UUID>` cho CQL.
B. Cho interface kế thừa `CassandraRepository<Event, EventKey>`.
C. Cho interface kế thừa `CrudRepository<Event, Long>` mặc định.
D. Cho interface kế thừa `MongoRepository<Event, EventKey>`.
Đáp án đúng: B

Câu 14. Muốn khai báo CQL tùy chỉnh trực tiếp trên repository method, nên dùng gì?
A. Dùng `@EntityListeners` để chèn điều kiện vào CQL.
B. Dùng `@NamedEntityGraph` để tạo CQL có điều kiện.
C. Dùng `@Query` với CQL và tham số bind phù hợp.
D. Dùng `@Transactional` thay cho phần WHERE của CQL.
Đáp án đúng: C

Câu 15. Khi muốn thao tác entity linh hoạt ngoài repository method, API nào hữu ích?
A. Dùng `CassandraTemplate` với select hoặc insert phù hợp.
B. Dùng `JdbcTemplate` để gửi CQL lên PostgreSQL driver.
C. Dùng `EntityManager` của JPA để phát câu lệnh CQL.
D. Dùng `MongoTemplate` để thao tác Cassandra keyspace.
Đáp án đúng: A

Câu 16. Với Spring Boot hiện đại, property nào chỉ định keyspace Cassandra mặc định?
A. Đặt `spring.data.mongodb.database` thành keyspace.
B. Đặt `spring.cassandra.keyspace-name` trong cấu hình app.
C. Đặt `spring.jpa.database-platform` thành tên keyspace.
D. Đặt `spring.datasource.schema` thành Cassandra namespace.
Đáp án đúng: B

Câu 17. Khi ứng dụng có client reactive, API repository nào phù hợp hơn?
A. Dùng `ReactiveCassandraRepository` trả publisher reactive.
B. Dùng `CassandraRepository` kết hợp blocking trên event loop.
C. Dùng `JpaRepository` rồi bao phương thức blocking trong Flux.
D. Dùng `CrudRepository` và tự thêm annotation `@Async`.
Đáp án đúng: A

Câu 18. Với replication factor 3 trong một datacenter, `QUORUM` cần bao nhiêu replica đáp ứng?
A. Cần ít nhất 2 replica để đạt quorum trong nhóm 3.
B. Cần đúng 1 replica vì Cassandra vẫn eventual consistent.
C. Cần 2 datacenter thay vì 2 replica trong cùng DC.
D. Cần cả 3 replica dù có consistency thấp hơn ALL.
Đáp án đúng: A

Câu 19. Với multi-datacenter Cassandra, `LOCAL_QUORUM` chủ yếu yêu cầu điều gì?
A. Replica ở datacenter xa hơn phải nhận dữ liệu đầu tiên.
B. Đủ quorum replica trong datacenter local của coordinator.
C. Đủ quorum gộp giữa toàn bộ datacenter của cluster.
D. Toàn bộ replica local và remote đều phải ACK mới thành công.
Đáp án đúng: B

Câu 20. Khi chọn consistency `ONE` cho read sau write gần đây, rủi ro nào cần cân nhắc?
A. CQL tự nâng read level thành SERIAL để đọc mới nhất.
B. Driver chờ quorum replica rồi trả kết quả cho read ONE.
C. Read `ONE` có thể trả bản cũ từ replica chưa cập nhật.
D. Kết quả được trả từ replica leader với thứ tự tuyến tính.
Đáp án đúng: C

Câu 21. CQL `INSERT ... IF NOT EXISTS` dùng cơ chế nào để tránh ghi đè dữ liệu tồn tại?
A. Dùng lightweight transaction với điều kiện có kiểm chứng.
B. Dùng batch logged bao phủ tất cả partition khi ghi row.
C. Dùng `ALLOW FILTERING` để kiểm tra table trước khi insert.
D. Dùng TTL mặc định để khóa record được lưu không trùng.
Đáp án đúng: A

Câu 22. Muốn bản ghi tự hết hạn sau một thời gian, CQL hỗ trợ cú pháp nào?
A. Thiết lập `IF NOT EXISTS` cho các lần SELECT dữ liệu.
B. Thiết lập `ORDER BY` với thời gian hết hạn trên row.
C. Thiết lập `ALLOW FILTERING` và expire theo page size.
D. Thiết lập `USING TTL` với số giây khi ghi dữ liệu.
Đáp án đúng: D

Câu 23. Xóa nhiều hàng hoặc hết hạn TTL dồn dập trong Cassandra gây vấn đề gì?
A. Clustering order bị xóa khỏi schema khi số TTL lớn.
B. Tombstone làm tăng chi phí đọc và tác vụ compaction.
C. Truy vấn chuyển sang consistency SERIAL để quét tombstone.
D. Memtable tự giải phóng ngay khi delete được xác nhận.
Đáp án đúng: B

Câu 24. Cassandra `INSERT` cùng primary key vào bảng thông thường thường có hành vi nào?
A. Tự chọn partition key khác để tránh ghi đè row hiện hữu.
B. Chèn row mới trùng primary key như bảng SQL không ràng buộc.
C. Upsert cập nhật các cột tương ứng của row theo key.
D. Trả lỗi duplicate-key nếu row đang tồn tại ở một replica.
Đáp án đúng: C

Câu 25. Dùng một batch rất lớn trải qua nhiều partition để bulk import Cassandra có rủi ro nào?
A. Batch loại bỏ hoàn toàn network overhead khi ghi phân tán.
B. Batch chuyển các ghi thành transaction ACID toàn cluster.
C. Batch sẽ tự tách song song thành các partition tối ưu.
D. Batch coordinator chịu tải lớn; throughput có thể giảm.
Đáp án đúng: D

Câu 26. Khi quét một kết quả CQL lớn, cơ chế paging nào phù hợp?
A. Tăng `LIMIT` tuyến tính rồi đọc lại toàn bộ trang trước.
B. Dùng `ORDER BY` mà không cần paging state của driver.
C. Dùng `OFFSET` cho mỗi trang như PostgreSQL để bỏ qua row.
D. Fetch theo page size và tiếp tục bằng paging state.
Đáp án đúng: D

Câu 27. Vì sao không nên giả định Cassandra hỗ trợ phân trang `OFFSET` như SQL truyền thống?
A. Dùng paging state thay vì truy cập trực tiếp theo OFFSET.
B. Driver tự dựng row number toàn cluster cho mỗi câu SELECT.
C. Primary key không thể được dùng làm điều kiện phân trang.
D. Clustering column không có ý nghĩa với thứ tự đọc CQL.
Đáp án đúng: A

Câu 28. Trong Cassandra, `ALLOW FILTERING` với truy vấn thiếu partition key thường tiềm ẩn điều gì?
A. Cassandra tự xây secondary index phù hợp rồi retry CQL.
B. Driver tự tạo materialized view tối ưu theo mọi field.
C. Đọc nhiều dữ liệu rồi lọc, tạo latency khó dự đoán.
D. Query được tách thành local-quorum transaction nguyên tử.
Đáp án đúng: C

Câu 29. Với cột collection lớn và tăng không giới hạn, rủi ro vận hành thường gặp nào?
A. Collection giúp giảm tombstone dù các phần tử bị xóa.
B. Collection chia partition theo từng phần tử trong một map.
C. Collection tăng lớn làm đọc/ghi nặng và phình dữ liệu.
D. Cassandra tự chuyển collection thành index có phân trang.
Đáp án đúng: C

Câu 30. Khi ứng dụng bị timeout CQL dù CPU client thấp, tín hiệu nào nên kiểm tra?
A. Đo latency, tombstone, timeout và mức lệch phân vùng.
B. Đo thời gian build JAR thay cho tình trạng node Cassandra.
C. Đo heap client và số connection đang mở trong pool.
D. Đếm truy vấn CQL nhưng bỏ qua latency tail của cluster.
Đáp án đúng: A

Câu 31. Muốn kiểm thử mapping repository và truy vấn CQL đúng hành vi thật, hướng nào phù hợp?
A. Mock CassandraRepository rồi xem như đã xác minh CQL.
B. Dùng H2 in-memory để kiểm tra partition key và TTL.
C. Kiểm tra mapping annotation thay cho thực thi query.
D. Dùng Cassandra Testcontainers và chạy schema CQL cho test.
Đáp án đúng: D

Câu 32. Khi kết nối Cassandra trong môi trường production, biện pháp nào phù hợp?
A. Để kết nối không mã hóa nếu đã cấu hình consistency ALL.
B. Đặt timeout trên driver để thay xác thực và phân quyền.
C. Bật TLS và auth, dùng credential có quyền keyspace tối thiểu.
D. Ghi thông tin mật khẩu trong source và dùng chung mọi cluster.
Đáp án đúng: C
