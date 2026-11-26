Câu 1. Trong Spring Framework, vai trò chính của `DataSource` đối với JDBC là gì?
A. Tạo `RowMapper` cho từng kiểu kết quả từ tên class domain.
B. Chuyển câu SQL thành JPQL rồi tạo EntityManager tương ứng.
C. Định nghĩa quy tắc rollback cho từng method repository.
D. Cung cấp `Connection` để ứng dụng thao tác cơ sở dữ liệu.
Đáp án đúng: D

Câu 2. Dùng connection pool cho nhiều request truy cập SQL mang lại lợi ích nào?
A. Thay transaction của database bằng cơ chế đồng bộ trong JVM.
B. Cache kết quả SQL ngay trong pool để giảm số lần chạy query.
C. Giữ một connection chung cho các thread để tránh tranh chấp.
D. Tái sử dụng kết nối vật lý và giới hạn lượng connection mở.
Đáp án đúng: D

Câu 3. `JdbcTemplate` quản lý tài nguyên JDBC thế nào khi chạy trong Spring transaction?
A. Commit riêng từng statement kể cả khi transaction đang active.
B. Giữ một Connection duy nhất mở xuyên suốt vòng đời của bean.
C. Quản lý lấy/trả tài nguyên JDBC theo transaction hiện hành.
D. Tạo DataSource mới mỗi lần gọi `query()` hoặc `update()`.
Đáp án đúng: C

Câu 4. Trong đoạn JDBC viết thủ công có Spring-managed transaction, nên lấy Connection ra sao?
A. Dùng `DataSourceUtils.getConnection(dataSource)` của Spring.
B. Tự commit mọi query trên `dataSource.getConnection()`.
C. Dùng `TransactionSynchronizationManager` thay cho JDBC Connection.
D. Dùng `DriverManager.getConnection()` theo JDBC URL của DataSource.
Đáp án đúng: A

Câu 5. Cần lấy danh sách `Customer` từ SELECT nhiều row bằng `JdbcTemplate`; dùng gì?
A. Gọi `queryForObject(sql, mapper)` để nhận danh sách nhiều row.
B. Gọi `query(sql, rowMapper)` và nhận danh sách đối tượng.
C. Gọi `update(sql)` rồi chuyển số row thành danh sách đối tượng.
D. Gọi `execute(sql)` và coi return value là `List<Customer>`.
Đáp án đúng: B

Câu 6. Giá trị kiểu `int` do `JdbcTemplate.update(...)` trả về thường biểu thị gì?
A. Số hàng bị tác động bởi câu lệnh ghi SQL vừa thực thi.
B. Số lần tự động retry sau khi một query bị deadlock.
C. Số bản ghi được JDBC driver đưa vào một ResultSet.
D. Số connection còn rảnh trong pool của DataSource.
Đáp án đúng: A

Câu 7. Để nhận dữ liệu nhập từ client trong SQL WHERE mà tránh injection, cách nào phù hợp?
A. Nối trực tiếp input vào SQL sau khi trim khoảng trắng.
B. Encode input thành Base64 trước khi ghép vào SQL.
C. Thêm dấu nháy quanh input rồi ghép vào chuỗi SQL.
D. Bind input bằng placeholder `?` của PreparedStatement.
Đáp án đúng: D

Câu 8. Tên cột `ORDER BY` được chọn từ request; cách xử lý nào an toàn hơn?
A. Escape dấu nháy đơn rồi coi tên cột là một SQL parameter.
B. Bind tên cột qua placeholder `?` như giá trị của WHERE.
C. Cho client gửi biểu thức ORDER BY rồi thêm LIMIT.
D. Chọn identifier từ allowlist để tạo `ORDER BY` hợp lệ.
Đáp án đúng: D

Câu 9. Trong `JdbcTemplate.query`, `RowMapper<T>` thường được gọi theo cách nào?
A. Điều khiển commit của transaction khi hết ResultSet.
B. Ánh xạ một hàng của ResultSet thành một đối tượng T.
C. Ánh xạ toàn bộ ResultSet một lượt thành danh sách T.
D. Tạo PreparedStatement và quyết định tham số bind SQL.
Đáp án đúng: B

Câu 10. Khi cần gom nhiều hàng SQL thành một object cha có danh sách con, API nào phù hợp?
A. Dùng `RowMapper` để tạo object cha riêng cho mỗi row.
B. Dùng `PreparedStatementSetter` để gộp hàng sau query.
C. Dùng `ResultSetExtractor` để xử lý toàn bộ ResultSet.
D. Dùng `KeyHolder` để hợp nhất các row theo primary key.
Đáp án đúng: C

Câu 11. `BeanPropertyRowMapper` thường ánh xạ cột `first_name` sang property nào?
A. Property Java `name` vì mapper tự loại bỏ tiền tố.
B. Property Java `first_name` bất kể convention của bean.
C. Property Java `id` nếu cột nằm trong câu SELECT đầu.
D. Ánh xạ `first_name` vào property `firstName` của bean.
Đáp án đúng: D

Câu 12. `queryForObject(sql, rowMapper)` nhận 0 hàng khi chờ đúng một hàng; điều gì xảy ra?
A. Trả về collection rỗng như `query()` với RowMapper.
B. Ném `EmptyResultDataAccessException` khi không có hàng.
C. Phát sinh `DuplicateKeyException` do query thiếu kết quả.
D. Trả về object mới với các property mang giá trị null.
Đáp án đúng: B

Câu 13. SQL có `WHERE id=:id` và muốn bind parameter theo tên; API nào phù hợp?
A. Dùng `NamedParameterJdbcTemplate` với tham số `id`.
B. Dùng `SimpleJdbcCall` để thực thi câu SELECT tên `id`.
C. Dùng `RowMapper` để đặt giá trị `:id` sau khi query chạy.
D. Dùng `JdbcTemplate` với `?` và coi tên `id` là placeholder.
Đáp án đúng: A

Câu 14. Với `NamedParameterJdbcTemplate`, thành phần nào giúp bind các giá trị SQL có tên?
A. Dùng `MapSqlParameterSource.addValue("id", value)`.
B. Dùng `KeyHolder` với `registerOutParameter("id")`.
C. Dùng `ResultSetExtractor` với `setValues("id", value)`.
D. Dùng `DataSourceUtils` với `addParameter("id", value)`.
Đáp án đúng: A

Câu 15. Trong Spring Framework 6.1+, cách dùng `JdbcClient` để SELECT một giá trị là gì?
A. Dùng `.query(...).setParameter(...).getSingleResult()`.
B. Dùng `.sql(...).param(...).query(String.class).single()`.
C. Dùng `.sql(...).executeQuery().fetchOne(String.class)`.
D. Dùng `.select(...).bind(...).queryForObject(String.class)`.
Đáp án đúng: B

Câu 16. Với SQL UPDATE có tham số, thao tác fluent nào của `JdbcClient` phù hợp?
A. Gọi `.sql(updateSql).param(...).update()` để thực thi.
B. Gọi `.sql(updateSql).query(String.class).list()` để ghi.
C. Gọi `.sql(updateSql).fetch().stream()` để sửa dữ liệu.
D. Gọi `.sql(updateSql).param(...).single()` để cập nhật.
Đáp án đúng: A

Câu 17. Muốn lấy ID database tự sinh sau INSERT bằng `JdbcTemplate`, nên dùng thành phần nào?
A. Gọi `batchUpdate` và coi mỗi phần tử là generated key.
B. Gọi `update(sql)` và dùng affected-row count làm generated ID.
C. Dùng `GeneratedKeyHolder` cùng overload `JdbcTemplate.update`.
D. Gọi `DataSourceUtils.getConnection()` để đọc ID từ pool.
Đáp án đúng: C

Câu 18. Khi dùng `JdbcTemplate.queryForStream`, cần lưu ý điều gì về tài nguyên?
A. Đóng DataSource trước khi duyệt Stream để giữ cursor.
B. Đợi GC đóng Stream vì JDBC resource do pool thu hồi ngay.
C. Đóng Stream sau khi đọc để giải phóng resource JDBC.
D. Commit transaction trước khi đọc Stream để tránh lock.
Đáp án đúng: C

Câu 19. Spring JDBC dịch lỗi vendor SQL sang hệ ngoại lệ nào?
A. Các runtime exception chuyên dùng của `EntityManager`.
B. Các subclass unchecked của `DataAccessException`.
C. Các subclass của `ServletException` tùy HTTP request.
D. Các checked exception kế thừa `SQLException` như cũ.
Đáp án đúng: B

Câu 20. Unique constraint bị vi phạm và được translator nhận diện; exception nào thường phù hợp?
A. `EmptyResultDataAccessException` vì SELECT không có hàng.
B. `CannotGetJdbcConnectionException` vì pool hết connection.
C. `DuplicateKeyException` trong nhóm lỗi toàn vẹn dữ liệu.
D. `BadSqlGrammarException` vì cú pháp INSERT không hợp lệ.
Đáp án đúng: C

Câu 21. Một câu SQL dùng tên cột không tồn tại và driver báo lỗi cú pháp; Spring JDBC thường dịch thành gì?
A. `EmptyResultDataAccessException` khi database không có row.
B. `DuplicateKeyException` khi INSERT xảy ra xung đột key.
C. `BadSqlGrammarException` khi SQL không được chấp nhận.
D. `DeadlockLoserDataAccessException` khi transaction bị khóa.
Đáp án đúng: C

Câu 22. Lợi ích chính của `JdbcTemplate.batchUpdate` khi ghi nhiều row cùng dạng là gì?
A. Tự rollback mỗi row bị lỗi mà giữ commit các row còn lại.
B. Tự biến mọi batch thành distributed transaction giữa DB.
C. Thay SQL INSERT bằng một câu truy vấn SELECT tối ưu.
D. Gom các lệnh ghi vào JDBC batch để giảm round trip.
Đáp án đúng: D

Câu 23. Khi dùng `BatchPreparedStatementSetter`, hai method quan trọng là gì?
A. Dùng `mapRow(rs, index)` và `getResultSetSize()`.
B. Dùng `setValues(ps, index)` và `getBatchSize()`.
C. Dùng `beforeCommit()` và `afterCompletion()`.
D. Dùng `extractData(rs)` và `getGeneratedKeys()`.
Đáp án đúng: B

Câu 24. Để gọi stored procedure có tên trong Spring JDBC, thành phần nào thuận tiện?
A. Dùng `RowMapper` rồi truyền tên thủ tục như column SQL.
B. Dùng `SimpleJdbcCall` cấu hình tên thủ tục và tham số.
C. Dùng `BeanPropertyRowMapper` thay cho JDBC callable statement.
D. Dùng `KeyHolder` để định nghĩa tham số IN và OUT của thủ tục.
Đáp án đúng: B

Câu 25. Khi driver không cung cấp metadata stored procedure đáng tin cậy, cách nào phù hợp?
A. Đổi stored procedure thành truy vấn `SELECT *` không tham số.
B. Tăng fetch size để driver tự khám phá đúng tên tham số.
C. Tắt đọc metadata và khai báo thủ công tham số procedure.
D. Đổi mọi tham số OUT thành IN để bỏ nhu cầu đọc metadata.
Đáp án đúng: C

Câu 26. Để cả cập nhật order và order_item trong cùng JDBC transaction, đặt boundary ở đâu?
A. Đặt `@Transactional` trên service method điều phối hai cập nhật.
B. Đặt một `@Transactional` riêng trên mỗi `RowMapper` được gọi.
C. Đặt `@Transactional` ở DataSource URL để driver tự áp dụng.
D. Đặt transaction ở controller sau khi response đã được gửi.
Đáp án đúng: A

Câu 27. Với một DataSource JDBC và giao dịch cục bộ, transaction manager nào phù hợp?
A. Dùng `JdbcTransactionManager` với DataSource của ứng dụng.
B. Dùng `JmsTransactionManager` để điều phối SQL Connection.
C. Dùng `WebSphereUowTransactionManager` cho mọi JDBC local tx.
D. Dùng `JpaTransactionManager` mà không cần EntityManagerFactory.
Đáp án đúng: A

Câu 28. Theo rollback rule mặc định thông thường, `@Transactional` rollback khi method ném gì?
A. Checked exception bất kỳ dù chưa cấu hình `rollbackFor`.
B. Rollback nếu `RuntimeException` hoặc `Error` thoát method.
C. Log ở mức ERROR dù method trả kết quả thành công.
D. Giá trị return null khi method update không tìm thấy row.
Đáp án đúng: B

Câu 29. Khi dùng propagation `REQUIRES_NEW`, hệ quả nào đáng chú ý?
A. Thực thi ngoài transaction mà không giữ connection DB.
B. Giữ nguyên transaction cũ và chỉ đánh dấu read-only mới.
C. Tạo savepoint bên trong transaction cũ thay vì tách transaction.
D. Transaction mới độc lập, tạm suspend transaction hiện tại.
Đáp án đúng: D

Câu 30. Vì sao `this.saveOrder()` tự gọi method cùng bean có `@Transactional` có thể không mở transaction?
A. Transaction manager chỉ hỗ trợ method khai báo ở controller.
B. DataSource bỏ transaction khi hai method cùng thread.
C. Annotation chỉ hoạt động khi method có kiểu trả về boolean.
D. Self-invocation không đi qua proxy giao dịch của Spring.
Đáp án đúng: D

Câu 31. Muốn kiểm soát giao dịch cục bộ bằng code thay vì annotation, API nào phù hợp?
A. Dùng `KeyHolder` để tự quản lý rollback giữa các statement.
B. Dùng `RowCallbackHandler` để đánh dấu transaction commit.
C. Dùng `TransactionTemplate.execute(...)` với manager thích hợp.
D. Dùng `BeanPropertyRowMapper` để bao các lời gọi update.
Đáp án đúng: C

Câu 32. Để kiểm chứng `JdbcTemplate` mapping, SQL constraint và rollback trong integration test, nên làm gì?
A. Kiểm thử mapping và rollback trên DB thật với Testcontainers.
B. Chỉ mock `JdbcTemplate` rồi coi SQL constraint đã đúng.
C. Chỉ unit test DTO mà không thực thi SQL trên DB.
D. Dùng H2 giả lập và kết luận hành vi vendor DB giống nhau.
Đáp án đúng: A
