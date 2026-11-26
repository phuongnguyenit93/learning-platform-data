Câu 01. Annotation JPA nào đánh dấu một lớp là entity được quản lý bởi persistence context?
A. `@Entity` đánh dấu class là entity do JPA quản lý
B. `@Table` biến class thành entity do JPA quản lý
C. `@Embeddable` khai báo class là entity do JPA quản lý
D. `@MappedSuperclass` đánh dấu class là entity được lưu
Đáp án đúng: A

Câu 02. Trong một JPA entity, vai trò của annotation `@Id` là gì?
A. Chỉ định thuộc tính nhận ID từ DB lúc insert
B. Chỉ định thuộc tính phải có unique constraint
C. Chỉ định thuộc tính định danh của entity
D. Chỉ định thuộc tính phiên bản để khóa lạc quan
Đáp án đúng: C

Câu 03. Khi dùng `@GeneratedValue(strategy = GenerationType.IDENTITY)`, ID thường được tạo ở đâu?
A. Database sinh ID qua identity column lúc insert
B. Provider lấy ID từ sequence trước khi gọi insert
C. Ứng dụng sinh UUID trước khi gửi entity xuống database
D. Provider dùng bộ đếm trong memory khi entity được persist
Đáp án đúng: A

Câu 04. Để ánh xạ entity `Invoice` tới bảng `invoices`, annotation nào phù hợp?
A. `@Table(name = "invoices")` chỉ định tên bảng lưu entity
B. `@SecondaryTable(name = "invoices")` đổi bảng chính của entity
C. `@Column(name = "invoices")` chỉ định tên bảng lưu entity
D. `@JoinTable(name = "invoices")` chỉ định tên bảng entity
Đáp án đúng: A

Câu 05. Muốn field `customerName` dùng cột `customer_name`, cấu hình nào phù hợp?
A. `@JoinColumn(name = "customer_name")` trên basic field
B. `@AttributeOverride(name = "customer_name")` trên basic field
C. `@Table(name = "customer_name")` trên field tương ứng
D. `@Column(name = "customer_name")` trên field tương ứng
Đáp án đúng: D

Câu 06. Trong JPA, annotation nào loại một field khỏi mapping persistence?
A. `@Basic(fetch = FetchType.LAZY)` không lưu field xuống DB
B. `@Column(insertable = false)` bỏ field khỏi các câu SELECT
C. `@Version` đánh dấu field không cần lưu xuống database
D. `@Transient` đánh dấu field không được JPA lưu thành cột
Đáp án đúng: D

Câu 07. Theo mặc định JPA, `@ManyToOne` có `FetchType` nào nếu không khai báo?
A. `FetchType.NONE` là mặc định đối với ManyToOne
B. `FetchType.EAGER` là mặc định đối với ManyToOne
C. `FetchType.LAZY` là mặc định đối với ManyToOne
D. `FetchType.DEFAULT` là mặc định đối với ManyToOne
Đáp án đúng: B

Câu 08. Trên `Customer.orders`, `@OneToMany(mappedBy = "customer")` mang ý nghĩa gì?
A. Quan hệ tạo join table do `mappedBy` được cấu hình
B. Field `customer` trong Order là phía sở hữu quan hệ
C. Order là entity độc lập nên không cần mapping liên kết
D. Customer là owning side và giữ foreign key của Order
Đáp án đúng: B

Câu 09. Trong quan hệ `@ManyToOne` từ Order sang Customer, `@JoinColumn(name = "customer_id")` xác định gì?
A. Cột khóa chính `customer_id` nằm ở bảng Customer
B. Cột version `customer_id` nằm ở bảng Order
C. Cột discriminator `customer_id` nằm ở bảng Customer
D. Cột khóa ngoại `customer_id` nằm ở bảng Order
Đáp án đúng: D

Câu 10. Khi `cascade = CascadeType.PERSIST` được đặt trên quan hệ Parent→Child, thao tác nào lan truyền?
A. Refresh parent kéo theo refresh child đang liên kết
B. Remove parent kéo theo delete child đang liên kết
C. Persist parent kéo theo persist child đang liên kết
D. Merge parent kéo theo merge child đang liên kết
Đáp án đúng: C

Câu 11. `orphanRemoval = true` trên `@OneToMany` phù hợp với trường hợp nào?
A. Gỡ child khỏi collection vẫn giữ nguyên record trong DB
B. Gỡ child khỏi collection khiến child mồ côi bị xóa
C. Xóa parent khi child bị loại khỏi association
D. Ngắt association rồi chuyển child về detached state
Đáp án đúng: B

Câu 12. Khi cập nhật field của managed entity trong transaction, JPA thường ghi thay đổi bằng cơ chế nào?
A. Dirty checking phát hiện và đồng bộ thay đổi lúc flush
B. Repository save được gọi cuối mỗi setter của entity
C. Entity listener sinh INSERT riêng cho các field vừa đổi
D. Lazy loading tự phát UPDATE mỗi khi getter được gọi
Đáp án đúng: A

Câu 13. Khác biệt quan trọng giữa `EntityManager.flush()` và transaction commit là gì?
A. Flush xóa managed entity khỏi persistence context khi gọi
B. Flush đóng transaction hiện tại và release connection ngay
C. Flush làm entity chuyển sang detached và tắt dirty checking
D. Flush gửi thay đổi xuống DB nhưng chưa commit giao dịch
Đáp án đúng: D

Câu 14. Khi gọi `EntityManager.clear()`, các entity đang managed sẽ thế nào?
A. Entity được flush rồi xóa khỏi các bảng tương ứng
B. Entity chuyển thành transient và xóa trường định danh
C. Các entity đang managed chuyển sang detached sau clear
D. Entity được refresh từ database nhưng vẫn giữ managed state
Đáp án đúng: C

Câu 15. Repository có method `findByStatusAndTotalGreaterThan(s, n)`; điều kiện nào được áp dụng?
A. Status bằng s đồng thời total lớn hơn n
B. Status bằng s hoặc total lớn hơn n
C. Status khác s đồng thời total lớn hơn n
D. Status bằng s đồng thời total nhỏ hơn n
Đáp án đúng: A

Câu 16. Trong `@Query` dùng JPQL, tên trong `FROM PurchaseOrder o` tham chiếu tới gì?
A. JPQL dùng tên entity và property Java, không phải bảng DB
B. JPQL dùng tên datasource đã khai báo tại JDBC URL
C. JPQL dùng tên bảng/cột SQL, không dựa metadata entity
D. JPQL dùng tên bean repository trong ApplicationContext
Đáp án đúng: A

Câu 17. Muốn viết SQL sử dụng tên bảng/cột thực tế trong `@Query`, cấu hình nào phù hợp?
A. Đặt `countQuery = true` để dùng bảng và cột SQL thuần
B. Đặt `readOnly = true` để query đọc theo tên cột DB
C. Đặt `clearAutomatically = true` để đổi JPQL thành SQL
D. Đặt `nativeQuery = true` để dùng SQL theo bảng/cột DB
Đáp án đúng: D

Câu 18. Với JPQL `where o.status = :status`, cách liên kết tham số method nào rõ ràng?
A. Thêm `@Column("status")` cho tham số status của method
B. Thêm `@Param("status")` cho tham số status của method
C. Thêm `@Lock("status")` cho tham số status của method
D. Thêm `@EntityGraph("status")` cho tham số status method
Đáp án đúng: B

Câu 19. Spring Data JPA dùng annotation nào cùng `@Query` cho JPQL bulk UPDATE hoặc DELETE?
A. `@Modifying` đánh dấu truy vấn làm thay đổi dữ liệu
B. `@QueryHints` đánh dấu truy vấn làm thay đổi dữ liệu
C. `@EntityGraph` đánh dấu truy vấn làm thay đổi dữ liệu
D. `@Lock` đánh dấu truy vấn làm thay đổi dữ liệu
Đáp án đúng: A

Câu 20. Sau bulk UPDATE, managed entity có thể giữ dữ liệu cũ; tùy chọn nào làm sạch context sau query?
A. Dùng `@Transactional(readOnly = true)` để clear context
B. Dùng `@Query(nativeQuery = true)` để clear context
C. Dùng `@Modifying(flushAutomatically = true)` để clear context
D. Dùng `@Modifying(clearAutomatically = true)` để clear context
Đáp án đúng: D

Câu 21. `JpaRepository.saveAndFlush(entity)` khác `save(entity)` chủ yếu ở điểm nào?
A. Gọi save rồi commit transaction độc lập ngay lập tức
B. Gọi flush sau save, vẫn chưa tự commit giao dịch
C. Gọi flush nhưng bỏ qua entity được truyền vào method
D. Ghi batch SQL trực tiếp, bỏ qua persistence context
Đáp án đúng: B

Câu 22. Trong repository query, `@EntityGraph(attributePaths = "items")` thường được dùng để làm gì?
A. Tạo SQL index cho foreign key của association `items`
B. Đặt lock mode lên `items` khi transaction ghi dữ liệu
C. Đổi fetch plan để tải `items` cùng kết quả query
D. Thêm predicate lọc theo ID của association `items`
Đáp án đúng: C

Câu 23. Khi lấy 100 Order rồi đọc `order.getItems()` tạo thêm nhiều SELECT, đây là biểu hiện gì?
A. Dirty read: truy vấn dữ liệu chưa được commit
B. N+1 query: thêm SELECT collection theo từng Order
C. Deadlock: các transaction đợi khóa của nhau
D. Lost update: bản ghi bị transaction khác ghi đè
Đáp án đúng: B

Câu 24. Trong JPQL, `JOIN FETCH o.customer` thường khác `JOIN o.customer` ở điểm nào?
A. Fetch join chỉ chọn ID customer thay vì entity association
B. Fetch join đặt pessimistic lock lên row customer
C. Fetch join buộc repository chạy count query cho Page
D. Fetch join tải customer trong cùng JPQL query
Đáp án đúng: D

Câu 25. Tình huống nào thường gây `LazyInitializationException` với Hibernate?
A. Gọi flush trên entity managed trong một transaction
B. Đọc ID của entity managed trong transaction còn mở
C. Chạm quan hệ lazy chưa tải sau khi đóng context
D. Đọc trường basic đã load trong persistence context
Đáp án đúng: C

Câu 26. Vì sao phân trang trực tiếp query `JOIN FETCH` một collection to-many cần thận trọng?
A. Join chỉ tải các root entity có đúng một child liên kết
B. Join to-many nhân dòng, dễ phải phân trang trong memory
C. Join yêu cầu khóa pessimistic trước khi query phân trang
D. Join mặc định chuyển câu SELECT thành native SQL
Đáp án đúng: B

Câu 27. Với truy vấn phân trang khi chỉ cần nút 'Trang tiếp', loại trả về nào có thể tránh count tổng?
A. `Page<T>` có total pages dù không chạy count query
B. `List<T>` cung cấp metadata hasNext tương tự Slice
C. `Slice<T>` cho biết hasNext mà không cần count toàn bộ
D. `Optional<T>` trả metadata số lượng page đã đọc
Đáp án đúng: C

Câu 28. Muốn lấy trang đầu, 20 record, sort `createdAt` giảm dần, Pageable nào đúng?
A. `PageRequest.of(0, 20, Sort.unsorted())`
B. `PageRequest.of(1, 20, Sort.by("createdAt").descending())`
C. `PageRequest.of(0, 20, Sort.by("createdAt").ascending())`
D. `PageRequest.of(0, 20, Sort.by("createdAt").descending())`
Đáp án đúng: D

Câu 29. Interface projection `OrderSummaryView` chỉ khai báo `getId()` và `getStatus()` nhằm mục đích gì?
A. Gắn khóa lạc quan cho getStatus khi query được gọi
B. Chỉ expose các property cần dùng qua interface getter
C. Khởi tạo đầy đủ các quan hệ lazy khi tạo projection
D. Tạo transaction riêng mỗi khi getter của interface chạy
Đáp án đúng: B

Câu 30. Trong JPQL, class-based DTO projection thường dùng dạng nào?
A. `select dto pkg.OrderSummary(o.id, o.total) from PurchaseOrder o`
B. `select new pkg.OrderSummary(o.id, o.total) from PurchaseOrder o`
C. `select map pkg.OrderSummary(o.id, o.total) from PurchaseOrder o`
D. `select entity pkg.OrderSummary(o.id, o.total) from PurchaseOrder o`
Đáp án đúng: B

Câu 31. Khi nghiệp vụ cập nhật Order và ghi Payment trong cùng transaction, đặt `@Transactional` ở đâu hợp lý?
A. Đặt trên DTO projection trước khi trả response tới client
B. Chỉ đặt trên findById của từng repository riêng biệt
C. Đặt `@Transactional` ở service bao các repository call liên quan
D. Chỉ đặt trên getter entity chạy cuối chuỗi nghiệp vụ
Đáp án đúng: C

Câu 32. Vì sao lời gọi nội bộ `this.update()` có `@Transactional` có thể không mở transaction mới?
A. Lời gọi nội bộ không đi qua Spring transaction proxy
B. Method của service chuyển thành repository transaction
C. Spring commit transaction trước khi gọi method nội bộ
D. EntityManager tạo transaction riêng cho mỗi private method
Đáp án đúng: A

Câu 33. `@Transactional(readOnly = true)` nên được hiểu thế nào trong Spring Data JPA?
A. DB từ chối UPDATE nhờ flag Spring readOnly trên method
B. SELECT lấy pessimistic write lock theo mặc định
C. Là gợi ý tối ưu đọc, không thay thế quyền ghi DB
D. Entity chuyển sang detached sau mỗi query trong scope
Đáp án đúng: C

Câu 34. `@Version` trong entity dùng cho optimistic locking phát hiện trường hợp nào?
A. Tải lazy collection sau khi persistence context đóng
B. Đọc dữ liệu chưa commit khi đang là READ_COMMITTED
C. Chờ row lock được giữ bởi transaction khác quá lâu
D. Ghi bản ghi theo version cũ sau khi transaction khác sửa
Đáp án đúng: D

Câu 35. Trên repository method, `@Lock(PESSIMISTIC_WRITE)` chủ yếu yêu cầu gì?
A. Đưa entity vào cache read-only cho đến khi restart
B. Chạy JPQL update hàng loạt bỏ qua persistence context
C. Đổi version field thành UUID không cần UPDATE SQL
D. Yêu cầu DB khóa row ở chế độ pessimistic write
Đáp án đúng: D

Câu 36. Khi xử lý optimistic lock conflict, cách retry nào giảm nguy cơ ghi đè dữ liệu mới?
A. Giữ entity stale rồi save lại trong tx đã thất bại
B. Mở tx mới, đọc lại entity và kiểm điều kiện nghiệp vụ
C. Gỡ `@Version` để lần sau bỏ kiểm tra row version
D. Merge entity cũ nhưng loại version field khi gửi
Đáp án đúng: B

Câu 37. Muốn tự động ghi ngày tạo/cập nhật entity bằng Spring Data JPA auditing, cần kết hợp gì?
A. Đặt `@Query` trên save để tự ghi created timestamp
B. Chỉ enable repository scanning, bỏ entity listener
C. Bật JPA auditing, entity listener và auditing annotations
D. Gắn `@Table` và `@Version` để nhận created timestamp
Đáp án đúng: C

Câu 38. Khi sử dụng `@CreatedBy` và `@LastModifiedBy`, thành phần nào cung cấp actor?
A. `AuditorAware` trả định danh actor hiện tại cho auditing
B. `JpaRepository` lấy actor từ entity ID với findById
C. `EntityGraph` đọc actor qua association được fetch
D. `JpaSpecificationExecutor` trả actor qua query metadata
Đáp án đúng: A

Câu 39. `@DataJpaTest` trong Spring Boot thường cung cấp phạm vi kiểm thử nào?
A. Test slice JPA repository, mặc định rollback transaction
B. Full end-to-end test qua HTTP controller và security filter
C. Test WebFlux handler bằng Reactor Netty cùng codec
D. Test service discovery với các remote broker đang chạy
Đáp án đúng: A

Câu 40. Vì sao kiểm thử truy vấn JPA bằng Testcontainers với cùng hệ RDBMS production hữu ích?
A. Chuyển JPQL thành native SQL để không cần đổi query
B. Xác nhận các query đã có index tối ưu khi startup
C. Bắt khác biệt SQL dialect/constraint giữa DB thật và H2
D. Loại bỏ nhu cầu test transaction rollback và lock
Đáp án đúng: C
