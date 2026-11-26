Câu 1. Lợi ích cốt lõi của Spring Data R2DBC là gì?
A. Dùng ORM persistence context để cache entity khi truy vấn
B. Truy cập SQL qua pipeline reactive không chặn I/O
C. Chạy từng SELECT trên một luồng JDBC cố định
D. Tự sinh schema DDL cho tất cả repository entity
Đáp án đúng: B

Câu 2. R2DBC khác JDBC rõ nhất ở đặc điểm nào khi truy cập database?
A. Bắt buộc dùng Hibernate EntityManager để truy vấn
B. Luôn phân phối mỗi query cho một thread cố định
C. Chỉ truy cập cơ sở dữ liệu NoSQL qua giao thức HTTP
D. Dùng API bất đồng bộ dựa trên Reactive Streams
Đáp án đúng: D

Câu 3. ConnectionFactory trong R2DBC thường đảm nhiệm vai trò nào?
A. Cấp DataSource JDBC cho mọi thao tác database
B. Duy trì một connection cố định cho mỗi HTTP request
C. Tạo connection theo hợp đồng R2DBC reactive
D. Cấu hình commit transaction cho mọi phương thức repository
Đáp án đúng: C

Câu 4. Khi chọn driver cho Spring Data R2DBC, điều gì phải phù hợp?
A. Driver R2DBC và hệ cơ sở dữ liệu đang kết nối
B. JDBC URL và phiên bản Hibernate trên classpath
C. Tên Java package của entity và schema của cluster
D. Phiên bản WebFlux với số lượng bảng trong database
Đáp án đúng: A

Câu 5. Annotation @Table trên entity R2DBC thường dùng làm gì?
A. Tạo transaction riêng cho mỗi property của lớp
B. Ánh xạ lớp entity đến bảng quan hệ được chọn
C. Chọn database driver cho mọi repository query
D. Bật mapping relationship kiểu JPA lazy loading
Đáp án đúng: B

Câu 6. Muốn property Java dùng tên cột khác trong SQL, nên chọn gì?
A. @Id để đổi alias của mọi cột khi đọc dữ liệu
B. @Version để sửa tên bảng tại runtime
C. @Table để đặt tên riêng cho từng property
D. @Column để khai báo tên cột được ánh xạ
Đáp án đúng: D

Câu 7. Annotation @Id trên entity Spring Data R2DBC biểu diễn gì?
A. Tên index dùng cho mọi query lọc theo trạng thái
B. Số lần transaction sẽ được tự động retry
C. Tên connection pool được dùng khi save entity
D. Thuộc tính định danh của một hàng trong bảng
Đáp án đúng: D

Câu 8. Khi ID do database tạo lúc insert, lưu ý nào chính xác?
A. @Id tự tạo sequence cho mọi driver và mọi schema
B. Repository tự ghi một UUID dù bảng chỉ nhận integer
C. Đảm bảo DB sinh ID và driver trả khóa phù hợp
D. @Version được dùng thay ID khi database sinh khóa
Đáp án đúng: C

Câu 9. Khi entity R2DBC có @Version, cơ chế nào có thể được kích hoạt?
A. Optimistic locking khi cập nhật bản ghi thay đổi
B. Tạo migration SQL cho schema ở mỗi startup
C. Quản lý TTL của mỗi row bằng trường version
D. Phân phối truy vấn SQL qua nhiều replica database
Đáp án đúng: A

Câu 10. Về quan hệ entity, Spring Data R2DBC khác JPA ở điểm nào?
A. Tự nhận mọi @OneToMany và sinh join khi findById
B. Tự cascade mọi bảng theo persistence context
C. Không mặc định cung cấp lazy loading quan hệ như JPA
D. Bắt buộc ánh xạ toàn bộ foreign key thành entity con
Đáp án đúng: C

Câu 11. ReactiveCrudRepository hỗ trợ tác vụ nào thông dụng?
A. Điều phối giao dịch XA cho nhiều database
B. Quản lý JDBC connection bằng ThreadLocal
C. Các thao tác CRUD trả kết quả reactive
D. Dùng Hibernate session để tracking dirty entity
Đáp án đúng: C

Câu 12. Khi findById của reactive repository có thể không có kết quả, kiểu nào hợp lý?
A. Mono phát tối đa một entity rồi kết thúc
B. Flux phát ít nhất hai entity theo cùng một ID
C. Optional lấy kết quả bằng JDBC đồng bộ
D. List chứa mọi row được tải trước khi subscribe
Đáp án đúng: A

Câu 13. Khi một truy vấn repository trả nhiều hàng, kiểu kết quả nào thích hợp?
A. Mono phát nhiều onNext trong cùng một subscription
B. Flux phát nhiều entity qua luồng reactive
C. Optional giữ toàn bộ kết quả của query SQL
D. Stream JDBC đồng bộ chạy trên event-loop thread
Đáp án đúng: B

Câu 14. Với Publisher truy vấn R2DBC dạng cold, sự kiện nào thường khởi chạy công việc?
A. Chỉ cần xây dựng Mono trong phương thức controller
B. Chỉ cần định nghĩa interface repository ở compile time
C. Có subscription tới pipeline truy vấn đã khai báo
D. Chỉ cần gọi map() để tạo thêm một operator
Đáp án đúng: C

Câu 15. Vì sao service reactive không nên gọi subscribe() thủ công rồi trả kết quả rỗng?
A. Làm WebFlux tự chuyển mọi query sang JDBC
B. Buộc repository tạo thêm bảng ở lần subscribe sau
C. Đảm bảo transaction sẽ commit trước khi controller trả
D. Mất liên kết luồng lỗi và vòng đời với caller
Đáp án đúng: D

Câu 16. Khi truy vấn findById không tìm thấy hàng, cách xử lý nào đúng với Mono?
A. Repository tự phát null qua một tín hiệu onNext
B. Mono chuyển thành Flux với một row mặc định
C. Luồng có thể kết thúc rỗng mà không có onNext
D. R2DBC tự ghi lại entity vào bảng rồi trả về
Đáp án đúng: C

Câu 17. Trong Reactor, onErrorResume thường phù hợp để làm gì?
A. Chuyển mọi lỗi SQL thành commit transaction thành công
B. Khôi phục luồng bằng fallback khi gặp lỗi được xử lý
C. Bỏ qua mọi constraint database trước khi retry
D. Tự đóng ApplicationContext khi query phát sinh lỗi
Đáp án đúng: B

Câu 18. onErrorMap trong pipeline R2DBC thường được dùng để làm gì?
A. Tạo result row mới thay cho mọi câu SQL thất bại
B. Tự retry transaction trên cùng connection đã đóng
C. Biến query blocking thành query không chặn I/O
D. Đổi lỗi SQL thành ngoại lệ phù hợp tầng ứng dụng
Đáp án đúng: D

Câu 19. R2dbcEntityTemplate hữu ích nhất trong trường hợp nào?
A. Định tuyến JDBC DataSource qua service registry
B. Tự quản lý schema migration cho mọi collection
C. CRUD và truy vấn linh hoạt với entity mapping
D. Thay thế connection pool bằng một cache toàn JVM
Đáp án đúng: C

Câu 20. Để lọc entity theo một field với R2dbcEntityTemplate, cách nào phù hợp?
A. Dùng Query cùng Criteria theo mapping của entity
B. Dùng @Query từ JPA CriteriaBuilder để lọc entity
C. Chuyển property thành tên bảng trước khi gọi select
D. Dùng ReactiveCrudRepository.save() để đánh dấu predicate
Đáp án đúng: A

Câu 21. DatabaseClient của Spring R2DBC phù hợp khi cần gì?
A. Thực thi SQL qua JDBC EntityManager đồng bộ
B. Bắt buộc ánh xạ mọi result row thành entity @Table
C. Quản lý migration schema qua SessionFactory của Hibernate
D. Chạy SQL tùy chỉnh với bind và ánh xạ kết quả
Đáp án đúng: D

Câu 22. Vì sao SQL với tham số người dùng cần dùng bind marker?
A. Tạo index riêng cho mỗi tham số trước khi SELECT
B. Đảm bảo mỗi lần thực thi có transaction XA mới
C. Bind giá trị để tách input khỏi cú pháp SQL
D. Bỏ qua bước kiểm tra ràng buộc database khi INSERT
Đáp án đúng: C

Câu 23. Khi khai báo SQL riêng cho phương thức repository R2DBC, thường dùng gì?
A. @Query gắn câu SQL cùng tham số phù hợp
B. @Table chứa chuỗi SELECT thay cho tên bảng
C. @Version chỉ định SQL dùng khi đọc entity
D. @Id truyền driver dialect cho từng phương thức
Đáp án đúng: A

Câu 24. Muốn repository dùng một câu UPDATE được khai báo bằng @Query, điều gì đáng chú ý?
A. Chỉ dùng @Column trên method để phát sinh UPDATE
B. Dùng @Modifying và trả số hàng cập nhật phù hợp
C. Dùng @Transactional của JDBC để chuyển SQL thành DML
D. Trả Mono của entity mà không cần ánh xạ result
Đáp án đúng: B

Câu 25. Khi cần đọc dữ liệu từ nhiều bảng quan hệ với R2DBC, hướng nào phù hợp?
A. Dùng @OneToMany để JPA tự lazy load trên R2DBC
B. Dùng SQL JOIN hoặc nhiều query và mapping rõ ràng
C. Nhờ @Id tự resolve mọi foreign key khi findById
D. Nhờ repository tự join tất cả bảng theo tên entity
Đáp án đúng: B

Câu 26. Để tăng hiệu năng query SQL lọc theo customer_id, nên cân nhắc gì?
A. Index phù hợp predicate và thống kê thực thi
B. Tăng số lần subscribe của cùng một Flux query
C. Tăng kích thước connection pool thay cho mọi index
D. Bật @Version để tự tăng tốc điều kiện WHERE
Đáp án đúng: A

Câu 27. Muốn kiểm tra database chọn index hay table scan, công cụ nào phù hợp?
A. EXPLAIN hay execution plan của database cụ thể
B. StepVerifier để xem trực tiếp SQL optimizer plan
C. @Table để in chỉ mục được chọn trong entity
D. ConnectionFactory để đếm số row quét bởi query
Đáp án đúng: A

Câu 28. Khi phân trang query SQL, vì sao ORDER BY ổn định quan trọng?
A. Làm OFFSET tự động nhỏ lại khi dữ liệu tăng
B. ORDER BY ổn định giúp giảm trùng, sót trang
C. Buộc R2DBC giữ một connection suốt đời ứng dụng
D. Khiến database tự chọn index mới ở mỗi trang
Đáp án đúng: B

Câu 29. Khi OFFSET của query phân trang rất lớn, rủi ro hiệu năng nào xuất hiện?
A. R2DBC tự thay đổi kiểu trả về từ Flux thành Mono
B. SQL optimizer mặc định chuyển OFFSET thành keyset
C. Spring Data tự xóa cache của mọi repository
D. Database có thể phải bỏ qua nhiều row trước LIMIT
Đáp án đúng: D

Câu 30. Vì sao cần quan tâm dialect khi viết SQL R2DBC tùy chỉnh?
A. Placeholder, cú pháp và kiểu dữ liệu có thể khác nhau
B. Mọi driver đều hỗ trợ cùng cú pháp phân trang SQL
C. Dialect tự quyết định cách WebFlux gửi HTTP response
D. Chỉ dialect mới tạo được transaction manager reactive
Đáp án đúng: A

Câu 31. R2dbcTransactionManager trong Spring có nhiệm vụ nào?
A. Dùng EntityManager quản lý transaction JPA truyền thống
B. Quản lý transaction qua R2DBC ConnectionFactory
C. Khởi tạo JDBC DataSource thay cho ConnectionFactory
D. Tự bù trừ giao dịch HTTP tới downstream service
Đáp án đúng: B

Câu 32. TransactionalOperator thường hữu ích trong trường hợp nào?
A. Tạo index cho mọi câu query trong repository
B. Áp phạm vi transaction lên reactive Publisher bằng lập trình
C. Chuyển ReactiveTransactionManager thành SessionFactory
D. Thực thi lời gọi SQL ngay khi operator được khai báo
Đáp án đúng: B

Câu 33. Để @Transactional quản lý một nghiệp vụ reactive đúng cách, cách viết nào phù hợp?
A. Gọi subscribe thủ công rồi trả void trước khi SQL hoàn tất
B. Gọi block trong event-loop để giữ transaction hoạt động
C. Tạo new Thread và dùng JDBC transaction ThreadLocal
D. Trả Mono hoặc Flux tạo trong phạm vi reactive transaction
Đáp án đúng: D

Câu 34. Vì sao transaction reactive cần Reactor Context thay vì chỉ ThreadLocal?
A. Mọi câu SQL chạy mãi trên cùng thread của request
B. Context đi theo subscription dù thread thay đổi
C. Context tự được lưu trong khóa chính của database
D. ThreadLocal có thể dùng xuyên mọi reactive operator tùy ý
Đáp án đúng: B

Câu 35. Trong transaction reactive, thời điểm commit thường gắn với điều gì?
A. Phương thức service vừa trả về đối tượng Mono
B. Publisher trong phạm vi transaction hoàn thành thành công
C. Controller vừa tạo đối tượng Flux trước subscription
D. ConnectionFactory vừa mở connection trước khi query
Đáp án đúng: B

Câu 36. Nếu gọi subscribe() riêng bên trong service @Transactional reactive, nguy cơ nào đáng lưu ý?
A. Spring tự nối mọi subscription vào transaction đang mở
B. Các statement ở subscription mới chắc chắn rollback cùng
C. Truy vấn phụ tách khỏi transaction và chuỗi lỗi chính
D. Repository tự chuyển subscription phụ thành một save đồng bộ
Đáp án đúng: C

Câu 37. Vì sao @Transactional R2DBC không tự rollback HTTP side effect?
A. WebClient tự động tham gia cùng local SQL transaction
B. HTTP server gửi compensating request khi SQL rollback
C. Mọi response HTTP đều được ghi vào transaction log DB
D. Giao dịch database không kiểm soát thao tác dịch vụ ngoài
Đáp án đúng: D

Câu 38. Khi dùng R2DBC connection pool, lợi ích chính nào thường được kỳ vọng?
A. Tái sử dụng connection để giảm chi phí tạo mới
B. Biến mọi SQL query thành giao dịch XA phân tán
C. Thay thế constraint khóa ngoại của relational DB
D. Tự nâng số session vô hạn theo số HTTP request
Đáp án đúng: A

Câu 39. Khi pool connection hết slot, ứng dụng nên xử lý hiện tượng nào?
A. Chờ acquire hoặc timeout thay vì tăng tải vô hạn
B. Pool tự mở transaction mới để cấp thêm connection
C. Repository có thể bỏ transaction để dùng slot dự phòng
D. Mọi acquire chờ sẽ tự mở connection bên ngoài pool
Đáp án đúng: A

Câu 40. Khi subscriber hủy truy vấn reactive đang dùng connection, nguyên tắc nào quan trọng?
A. Connection phải giữ tới lúc ứng dụng được restart
B. Mỗi cancel bắt buộc commit toàn bộ SQL chưa chạy
C. Mọi query cần chạy lại trên JDBC thread để cleanup
D. Giải phóng connection khi luồng bị cancel
Đáp án đúng: D

Câu 41. Backpressure trong pipeline R2DBC đem lại điều gì và giới hạn gì?
A. Điều tiết demand nhưng không tự tối ưu SQL
B. Tự tạo index phù hợp cho mọi điều kiện WHERE
C. Bảo đảm mọi database query không dùng thêm RAM
D. Tự phân phối tất cả query qua nhiều DB replica
Đáp án đúng: A

Câu 42. Trong controller WebFlux gọi repository R2DBC, kiểu trả về nào phù hợp?
A. Gọi block và trả dữ liệu đồng bộ từ event-loop
B. Tạo thread chờ JDBC Future của mỗi request
C. Trả Mono/Flux để WebFlux quản lý subscription
D. Gọi subscribe rồi trả response OK không có dữ liệu
Đáp án đúng: C

Câu 43. Vì sao tránh block() trên WebFlux event-loop khi dùng R2DBC?
A. Block tạo thêm transaction khi Mono chưa có subscriber
B. Block tự tạo event-loop riêng cho mỗi SQL request
C. Block buộc connection pool trả tất cả connection
D. Chặn thread xử lý làm suy giảm khả năng phục vụ đồng thời
Đáp án đúng: D

Câu 44. Khi retry một nghiệp vụ INSERT sau lỗi mất kết nối, điều gì cần kiểm soát?
A. Khả năng ghi trùng nếu lần trước đã commit nhưng client chưa biết
B. Retry đảm bảo mọi INSERT chỉ được server ghi một lần
C. Connection pool tự đánh dấu toàn bộ SQL là idempotent
D. ReactiveTransactionManager tự xóa row của lần thử cũ
Đáp án đúng: A

Câu 45. Để kiểm thử luồng Mono trả lỗi hoặc hoàn thành, công cụ nào phù hợp?
A. EXPLAIN kiểm tra tất cả tín hiệu Reactor của service
B. StepVerifier kiểm tra onNext, completion và error
C. ConnectionFactory tự assert nội dung các error signal
D. @Table cho phép đo số subscription trong test
Đáp án đúng: B

Câu 46. Khi muốn kiểm thử SQL và mapping đúng dialect thực tế, cách nào đáng tin cậy?
A. Chỉ mock repository rồi bỏ qua SQL do @Query cung cấp
B. Chỉ chạy unit test trên object Java không có driver
C. Chỉ kiểm tra Spring context đã tạo được repository
D. Testcontainers với database thật và dữ liệu kiểm thử
Đáp án đúng: D

Câu 47. Để quan sát hiệu năng và lỗi R2DBC production, nên theo dõi gì?
A. Lưu toàn bộ mật khẩu SQL vào metric tag theo connection
B. Tăng log level để xuất nguyên mọi bind parameter nhạy cảm
C. Latency SQL, lỗi và tình trạng pool mà không lộ credential
D. Bỏ đo pool vì request reactive không bao giờ chờ connection
Đáp án đúng: C

Câu 48. Khi INSERT vi phạm UNIQUE constraint của database, pipeline reactive thường ra sao?
A. Mono tự trả lại row cũ rồi complete không có lỗi
B. Repository tự đổi khóa chính và thử ghi lại lần nữa
C. Phát lỗi qua onError để ứng dụng xử lý xung đột
D. R2DBC tự xóa constraint rồi commit INSERT mới
Đáp án đúng: C
