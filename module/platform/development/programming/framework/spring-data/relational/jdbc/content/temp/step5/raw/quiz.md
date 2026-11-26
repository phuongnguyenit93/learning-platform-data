Câu 01. Một aggregate root trong Spring Data JDBC được hiểu thế nào theo DDD?
A. Bản sao dữ liệu đọc từ nhiều database khác nhau
B. Entity phụ chỉ lưu khi gọi repository của từng child
C. Đầu mối thay đổi và bảo vệ invariant của aggregate
D. DTO kết quả dùng để tránh tạo bảng cho aggregate
Đáp án đúng: C

Câu 02. Vì sao repository Spring Data JDBC thường đặt ở aggregate root?
A. Sửa aggregate thông qua root để bảo đảm tính nhất quán
B. Mỗi child cần có repository riêng để chia transaction
C. Root được tạo chủ yếu nhằm hỗ trợ lazy loading
D. Các entity dùng chung repository qua tên bảng
Đáp án đúng: A

Câu 03. Điểm khác biệt của Spring Data JDBC so với JPA về context là gì?
A. Dùng EntityManager để đồng bộ managed entity
B. Không có persistence context theo dõi entity
C. Giữ lazy proxy cho collection thuộc aggregate
D. Có first-level cache và dirty checking khi commit
Đáp án đúng: B

Câu 04. Sau khi sửa field của aggregate load từ JDBC repository, việc nào cần làm để lưu DB?
A. Đánh dấu field bằng @Transient trước commit
B. Chờ transaction commit tự detect dirty fields
C. Cần gọi repository.save(root) để ghi thay đổi
D. Chỉ gọi flush trên EntityManager của JDBC module
Đáp án đúng: C

Câu 05. Đối với child thuộc cùng aggregate, Spring Data JDBC thường nạp chúng thế nào?
A. Để lazy proxy gọi SELECT tại lần access đầu
B. Chỉ nhận child dưới dạng ID tới một root khác
C. Chỉ lấy child nếu có JPQL JOIN FETCH trong query
D. Đọc root sẽ nạp cả child thuộc cùng aggregate
Đáp án đúng: D

Câu 06. Mô hình tham chiếu aggregate Customer từ Order nên tránh điều gì?
A. Tránh tách Customer ra repository root riêng
B. Tránh tạo transaction cho thay đổi độc lập
C. Tránh lưu Customer ID trong order schema
D. Không coi Customer là child được root Order sở hữu
Đáp án đúng: D

Câu 07. Loại nào cho phép tham chiếu aggregate khác bằng ID mà không map toàn graph?
A. `AggregateReference<Customer, Long>` lưu tham chiếu ID
B. `JdbcAggregateTemplate` thao tác đọc và lưu aggregate root
C. `CrudRepository<Customer, Long>` cung cấp API tìm root theo ID
D. `RelationalMappingContext` chứa metadata ánh xạ entity
Đáp án đúng: A

Câu 08. Annotation Spring Data Relational nào đặt tên bảng lưu `PurchaseOrder`?
A. `@Column("purchase_order")` ánh xạ tên bảng root
B. `@MappedCollection(idColumn="purchase_order")` đặt tên bảng
C. `@Table("purchase_order")` ánh xạ tên bảng root
D. `@Embedded(prefix="purchase_order")` đặt tên bảng
Đáp án đúng: C

Câu 09. Annotation nào ánh xạ field `displayName` sang cột `display_name`?
A. `@Column("display_name")` đặt tên cột trong SQL
B. `@MappedCollection(idColumn="display_name")` đặt tên cột
C. `@Embedded(prefix="display_name")` đặt tên cột
D. `@Table("display_name")` đặt tên cột trong SQL
Đáp án đúng: A

Câu 10. Trong `@MappedCollection(idColumn="order_id")`, idColumn diễn đạt gì?
A. Cột version để ngăn cập nhật đồng thời từ root
B. Cột khóa ngoại ở bảng child trỏ tới root Order
C. Cột khóa chính trong bảng Order được sinh lúc insert
D. Cột chứa index của List child trong bảng Order
Đáp án đúng: B

Câu 11. `keyColumn` của `@MappedCollection` dùng trong collection nào?
A. Chỉ định tên primary key của root trong schema
B. Lưu chỉ số List hoặc khóa Map ở bảng child
C. Chỉ định tên sequence cấp phát ID của child
D. Đặt tên discriminator của kiểu entity kế thừa
Đáp án đúng: B

Câu 12. Dùng `@Embedded` cho value object Address có tác dụng gì trong JDBC?
A. Lưu thuộc tính Address vào các cột của bảng owner
B. Chuyển Address thành JSON string mặc định ở một cột
C. Tạo một lazy association tới Address aggregate
D. Lưu Address thành một bảng root với ID riêng
Đáp án đúng: A

Câu 13. Spring Data JDBC thường coi ID null của root với ID do DB tạo là gì?
A. Root read-only nên bỏ qua thao tác ghi
B. Root đã tồn tại nên cần UPDATE theo khóa chính
C. Root detached nên cần reattach trước khi save
D. Root mới cần INSERT và nhận ID từ database
Đáp án đúng: D

Câu 14. Khi root hiện có được save kèm child collection, hành vi nào cần chú ý?
A. Các child được dirty checking như managed JPA entity
B. Child chỉ được cập nhật nếu gọi từng child repository
C. Child có thể bị xóa/insert lại khi save aggregate
D. Các child được merge theo từng field đã sửa
Đáp án đúng: C

Câu 15. Vì sao cần tránh đưa nhiều entity độc lập vào cùng một aggregate?
A. Repository cần gọi EntityManager khi aggregate rộng
B. Save aggregate rộng có thể ghi lại các child không đổi
C. NamedParameterJdbcTemplate không đọc bảng lớn
D. Root nhỏ sẽ thiếu proxy lazy cho các thuộc tính
Đáp án đúng: B

Câu 16. Spring Data JDBC hỗ trợ mối quan hệ giữa hai aggregate độc lập ra sao?
A. Sử dụng `mappedBy` trên quan hệ `@ManyToMany`
B. Cascade persist tới các aggregate reference riêng
C. Lưu ID tham chiếu rồi đọc root khác từ repository
D. Tạo lazy proxy được quản lý bởi persistence context
Đáp án đúng: C

Câu 17. Trong `CrudRepository<Order, Long>`, `findById(42L)` khi thiếu dữ liệu trả gì?
A. `null` biểu thị order không được tìm thấy trong bảng
B. `Page.empty()` biểu thị không có order cần tìm
C. `Stream.empty()` biểu thị order không tìm thấy
D. `Optional.empty()` biểu thị không có order cần tìm
Đáp án đúng: D

Câu 18. Nếu muốn chủ động yêu cầu INSERT một aggregate, API nào phù hợp?
A. `CrudRepository.findAll()` kích hoạt insert cho aggregate
B. `JdbcAggregateTemplate.delete(root)` gọi insert
C. `JdbcAggregateTemplate.insert(root)` thực hiện INSERT
D. `JdbcAggregateTemplate.findById(root)` gọi insert
Đáp án đúng: C

Câu 19. Trong annotation `@Query` của Spring Data JDBC, truy vấn được viết theo ngôn ngữ nào?
A. HQL theo class managed bởi persistence context
B. JPQL theo tên entity và collection association
C. SQL dựa trên tên bảng và cột của database quan hệ
D. Mongo JSON query theo field của BSON document
Đáp án đúng: C

Câu 20. SQL `WHERE status = :status` trong `@Query` liên kết argument rõ ràng bằng gì?
A. `@Column("status")` trên tham số repository method
B. `@MappedCollection(idColumn="status")` trên method
C. `@Version` trên tham số repository method
D. `@Param("status")` trên tham số repository method
Đáp án đúng: D

Câu 21. Muốn khai báo `@Query` để thực thi `UPDATE` trong Spring Data JDBC, cần annotation nào?
A. `@MappedCollection` đánh dấu custom SQL có dữ liệu
B. `@Modifying` đánh dấu custom query có ghi dữ liệu
C. `@QueryHints` đánh dấu custom query ghi dữ liệu
D. `@Transactional(readOnly=true)` đánh dấu ghi dữ liệu
Đáp án đúng: B

Câu 22. Tên method derived `findByStatusAndTotalGreaterThan` thường tạo điều kiện nào?
A. Status bằng đối số và total lớn hơn giá trị truyền
B. Status bằng đối số và total nhỏ hơn giá trị truyền
C. Status bằng đối số hoặc total lớn hơn giá trị truyền
D. Status khác đối số và total lớn hơn giá trị truyền
Đáp án đúng: A

Câu 23. Derived query Spring Data JDBC thường phù hợp nhất với thuộc tính nào?
A. Thuộc tính con cần traversal qua nhiều join động
B. Biểu thức JPQL gọi method của entity managed
C. Thuộc tính của root khác đọc bằng lazy proxy
D. Thuộc tính trực tiếp của aggregate root trong bảng gốc
Đáp án đúng: D

Câu 24. Khi cần SQL JOIN phức tạp và mapping kết quả đặc thù, hướng nào hợp lý?
A. Dùng @MappedCollection để khai báo JOIN qua nhiều root
B. Dùng NamedParameterJdbcTemplate và RowMapper chủ động
C. Dùng @Query theo JPQL để join các association
D. Dùng JPA EntityGraph để tự fetch theo JPQL
Đáp án đúng: B

Câu 25. Bảng schema cần thay đổi có kiểm soát qua các bản deploy, nên làm gì?
A. Đổi tên entity Java để JDBC tự xóa và tạo bảng
B. Dựa vào persistence context để tạo bảng khi commit
C. Mỗi lần save aggregate tự nâng version của schema
D. Quản lý migration SQL bằng Flyway hoặc Liquibase
Đáp án đúng: D

Câu 26. Hai repository thao tác trên cùng DB cần chung một unit of work; đặt `@Transactional` ở đâu?
A. Đặt @Transactional trên từng repository method riêng lẻ
B. Đặt @Transactional vào method đọc trước khi ghi dữ liệu
C. Đặt @Transactional tại callback sau save root đầu tiên
D. Service method bao trọn cả hai thao tác nghiệp vụ
Đáp án đúng: D

Câu 27. Thành phần Spring nào điều phối giao dịch JDBC qua DataSource?
A. `JdbcTransactionManager` quản lý transaction JDBC
B. `MongoTransactionManager` quản lý transaction JDBC
C. `ReactiveMongoTransactionManager` quản lý JDBC
D. `JpaTransactionManager` dùng EntityManager cho JDBC
Đáp án đúng: A

Câu 28. Theo mặc định Spring `@Transactional` rollback với loại lỗi nào?
A. Lỗi SQL đã được bắt rồi trả về giá trị bình thường
B. Unchecked exception như RuntimeException khi thoát method
C. Checked exception bất kỳ nếu method có throws
D. Exception được catch và nuốt trong service method
Đáp án đúng: B

Câu 29. Khi ghi hai aggregate root trong một `@Transactional` service, điều gì đúng?
A. Đổi repository khiến mỗi root commit độc lập ngoài TX
B. Hai lần lưu có thể nằm chung một JDBC transaction
C. Cả hai aggregate dùng chung JPA persistence context
D. Root lưu trước sẽ commit trước khi root tiếp theo lưu
Đáp án đúng: B

Câu 30. Khi cần ghi nhiều root để đạt invariant xuyên aggregate, cần cân nhắc điều gì?
A. Bật lazy loading để tránh xung đột giữa nhiều repository
B. Tạo EntityManager cho root vì JDBC hỗ trợ managed entity
C. Xác định transaction boundary và tranh chấp ghi
D. Dùng cascade @OneToMany để nối các root không liên quan
Đáp án đúng: C

Câu 31. Trường `@Version` trên aggregate root giúp kiểm soát gì?
A. Tạo sequence tự tăng cho các child khi insert
B. Bật lazy loading với child collection thuộc aggregate
C. Chặn ghi với version cũ nhờ optimistic locking
D. Chuyển tên bảng sang định dạng theo phiên bản schema
Đáp án đúng: C

Câu 32. Khi hai transaction lưu cùng root với version cũ, lần ghi thứ hai thường gặp gì?
A. `LazyInitializationException` do context đã đóng
B. `NoSuchBeanDefinitionException` do repository sai
C. `DataIntegrityViolationException` do SQL parser
D. `OptimisticLockingFailureException` do lệch version
Đáp án đúng: D

Câu 33. Sau `OptimisticLockingFailureException`, cách retry nghiệp vụ nào phù hợp?
A. Retry trong tx mới, tải root mới và kiểm nghiệp vụ
B. Bỏ @Version rồi dùng lại dữ liệu stale vừa chỉnh
C. Chỉ gọi flush trên EntityManager để nhận version mới
D. Lặp save root stale trong transaction đã rollback
Đáp án đúng: A

Câu 34. Khi muốn lưu CreatedDate/LastModifiedDate trong JDBC entity, cần bật gì?
A. `@EnableJdbcAuditing` cùng auditing annotations
B. `@EnableR2dbcRepositories` cùng auditing annotations
C. `@EnableJpaAuditing` cùng auditing annotations
D. `@EnableMongoAuditing` cùng auditing annotations
Đáp án đúng: A

Câu 35. Annotation nào điền thời điểm tạo lần đầu cho aggregate?
A. `@LastModifiedDate` ánh xạ trường thời gian tạo
B. `@CreatedDate` ánh xạ trường thời gian tạo
C. `@CreatedBy` ánh xạ trường thời gian tạo
D. `@LastModifiedBy` ánh xạ trường thời gian tạo
Đáp án đúng: B

Câu 36. Khi cần gán người đang thao tác vào `@CreatedBy`, Spring Data dùng thành phần nào?
A. `JdbcAggregateTemplate` trả actor từ tên bảng
B. `AuditorAware<T>` trả định danh actor hiện tại
C. `RowMapper<T>` trả actor từ dữ liệu ResultSet
D. `BeforeSaveCallback<T>` trả actor mặc định từ ID
Đáp án đúng: B

Câu 37. Callback nào được dùng để chuẩn bị root trước khi chuyển sang SQL?
A. `AfterDeleteCallback<T>` can thiệp trước convert
B. `AfterSaveCallback<T>` can thiệp trước convert
C. `AfterConvertCallback<T>` chạy trước khi ghi vào DB
D. `BeforeConvertCallback<T>` chạy trước bước convert
Đáp án đúng: D

Câu 38. Với `BeforeConvertCallback`, ví dụ dùng thực tế hợp lý là gì?
A. Lấy JDBC ResultSet trực tiếp trước khi convert entity
B. Khóa row database sau khi save transaction kết thúc
C. Gán UUID cho root mới trước khi JDBC ghi xuống DB
D. Mở Hibernate Session và khởi tạo lazy proxy
Đáp án đúng: C

Câu 39. Trong Spring Boot, `@DataJdbcTest` tập trung khởi tạo môi trường nào?
A. `@DataJdbcTest` nạp JDBC repository trong test slice
B. Reactor WebFlux và server Netty cho HTTP request
C. JPA EntityManager cùng Hibernate persistence context
D. Full HTTP MVC server và toàn bộ background schedules
Đáp án đúng: A

Câu 40. Lý do hữu ích của Testcontainers với đúng hệ RDBMS production khi test JDBC là gì?
A. Kiểm tra dialect/constraint và SQL trên engine thực
B. Bảo đảm transaction tránh deadlock khi chạy thật
C. Bảo đảm query có index tối ưu trên production
D. Bỏ qua migration SQL do container tạo schema đúng
Đáp án đúng: A
