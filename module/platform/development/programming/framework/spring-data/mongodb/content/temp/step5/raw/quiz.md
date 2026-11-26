Câu 01. Muốn ánh xạ entity `Order` tới MongoDB collection `orders`, annotation nào phù hợp?
A. `@Indexed(name = "orders")` chọn collection của entity
B. `@Document(collection = "orders")` đặt collection MongoDB
C. `@Field(name = "orders")` chọn collection của entity
D. `@TypeAlias("orders")` chọn collection của entity
Đáp án đúng: B

Câu 02. Với entity `Product`, `@Id` trên trường `id` gắn với field MongoDB nào?
A. Trường định danh `id` được ánh xạ vào `createdAt`
B. Trường định danh `id` được ánh xạ vào `_class`
C. Trường định danh `id` được ánh xạ vào `version`
D. Java property `id` được ánh xạ vào MongoDB `_id`
Đáp án đúng: D

Câu 03. Muốn Java property `displayName` được lưu bằng key `display_name`, nên dùng gì?
A. `@Field("display_name")` trên property cần đổi tên
B. `@Indexed("display_name")` trên property cần đổi tên
C. `@TypeAlias("display_name")` trên property cần đổi tên
D. `@Document("display_name")` trên property cần đổi tên
Đáp án đúng: A

Câu 04. Muốn một property không được lưu vào document MongoDB, annotation nào phù hợp?
A. `@PersistenceCreator` loại property khỏi mapping persistence
B. `@Transient` loại property khỏi mapping persistence
C. `@Version` loại property khỏi mapping persistence
D. `@Indexed` loại property khỏi mapping persistence
Đáp án đúng: B

Câu 05. Nếu `Order.customer` dùng `@DBRef`, document cha thường lưu dữ liệu nào?
A. Object khách hàng được nhúng đầy đủ vào document Order
B. Snapshot toàn bộ collection Customer tại lúc tạo Order
C. DBRef trỏ đến customer trong collection tương ứng
D. Pipeline `$lookup` được lưu trực tiếp trong document Order
Đáp án đúng: C

Câu 06. `@DocumentReference` khác `@DBRef` ở điểm nào khi lưu mặc định?
A. Giữ ID đơn giản, thay vì cấu trúc BSON DBRef
B. Tham chiếu được chuyển thành join table trong MongoDB
C. Tham chiếu được gắn vào field `_class` thay vì field riêng
D. Tham chiếu nhúng nguyên document của entity vào parent
Đáp án đúng: A

Câu 07. Khi truy vấn cần nhiều điều kiện do người dùng chọn lúc chạy, công cụ nào tiện dùng?
A. `MongoMappingContext` thay thế `Query` ở mỗi request
B. `MongoRepository` chỉ gọi `saveAll` cho các điều kiện động
C. `MongoTransactionManager` kết hợp `Query` và `Criteria`
D. `MongoTemplate` tạo `Query` và `Criteria` động cho nhiều tiêu chí
Đáp án đúng: D

Câu 08. Đối với CRUD theo entity và ID bằng repository, interface nào đặc trưng cho MongoDB?
A. `MongoRepository<Product, String>` cho CRUD document
B. `JpaRepository<Product, String>` cho CRUD document
C. `ReactiveCrudRepository<Product, String>` cho JPA SQL
D. `MongoTransactionManager<Product>` cho CRUD document
Đáp án đúng: A

Câu 09. Method repository `findByStatusAndAmountGreaterThan(s, n)` lọc document thế nào?
A. Status khác s và amount lớn hơn n theo derived query
B. Status bằng s và amount nhỏ hơn n theo derived query
C. Status bằng s và amount lớn hơn n theo derived query
D. Status bằng s hoặc amount lớn hơn n theo derived query
Đáp án đúng: C

Câu 10. Trong `@Query` của MongoDB repository, cú pháp nào tham chiếu tham số đầu tiên?
A. Dùng `?0` trong JSON query để bind tham số thứ nhất
B. Đặt `%0` trong JSON query để bind tham số đầu tiên
C. Đặt `:0` trong JSON query để bind tham số đầu tiên
D. Đặt `$0` trong JSON query để bind tham số đầu tiên
Đáp án đúng: A

Câu 11. Khi dùng `MongoTemplate`, cách biểu diễn điều kiện `status == "PAID"` nào đúng?
A. `Criteria.where("status").is("PAID")` so sánh bằng trên status
B. `Criteria.where("status").gt("PAID")` cho điều kiện bằng
C. `Criteria.where("status").exists(false)` cho điều kiện bằng
D. `Criteria.where("status").ne("PAID")` cho điều kiện bằng
Đáp án đúng: A

Câu 12. Muốn lấy document thỏa ít nhất một trong hai tiêu chí, chọn tổ hợp nào?
A. `new Criteria().norOperator(c1, c2)` nối điều kiện OR
B. `Criteria.where("tag").in("c1", "c2")` lọc trên một field
C. `new Criteria().orOperator(c1, c2)` nối OR giữa hai điều kiện
D. `new Criteria().andOperator(c1, c2)` nối điều kiện OR
Đáp án đúng: C

Câu 13. Muốn lọc theo field lồng `address.city` trong một document, biểu thức nào hợp lệ?
A. `Criteria.where("address->city").is("Hue")` dùng dot path
B. `Criteria.where("address_city").is("Hue")` dùng dot path
C. `Criteria.where("address/city").is("Hue")` dùng dot path
D. `Criteria.where("address.city").is("Hue")` dùng dot path
Đáp án đúng: D

Câu 14. Muốn sửa field `status` ở document khớp đầu tiên, API `MongoTemplate` nào phù hợp?
A. `updateMulti(query, update, Order.class)` sửa một bản ghi
B. `updateFirst(query, update, Order.class)` sửa một document
C. `upsert(query, update, Order.class)` sửa một bản ghi
D. `findAllAndRemove(query, Order.class)` sửa một bản ghi
Đáp án đúng: B

Câu 15. Muốn sửa tất cả document khớp một `Query`, method nào trong `MongoTemplate` phù hợp?
A. `findAndModify(query, update, Order.class)` sửa nhiều bản ghi
B. `findOne(query, Order.class)` sửa nhiều bản ghi
C. `updateFirst(query, update, Order.class)` sửa nhiều bản ghi
D. `updateMulti(query, update, Order.class)` sửa nhiều document
Đáp án đúng: D

Câu 16. Khi cần cập nhật document nếu có, hoặc thêm mới khi không có document khớp, dùng gì?
A. `upsert(query, update, Order.class)` để update hoặc insert
B. `findOne(query, Order.class)` xử lý update hoặc insert
C. `updateFirst(query, update, Order.class)` xử lý update hoặc insert
D. `findAndRemove(query, Order.class)` xử lý update hoặc insert
Đáp án đúng: A

Câu 17. `findAndModify` trả document phiên bản trước update theo mặc định; muốn lấy bản sau update cần gì?
A. `FindAndModifyOptions.options().upsert(false)` để nhận bản sau sửa
B. `FindAndModifyOptions.options().returnNew(true)` để nhận bản sau sửa
C. `FindAndModifyOptions.options().upsert(true)` để nhận bản sau sửa
D. `FindAndModifyOptions.options().returnNew(false)` để nhận bản sau sửa
Đáp án đúng: B

Câu 18. Khi cần thực thi nhiều thao tác ghi có tính chất bulk, API nào của Spring Data MongoDB hỗ trợ?
A. `MongoTemplate.findAndModify(...)` cập nhật rồi trả kết quả
B. `MongoTemplate.bulkOps(...)` gom các thao tác ghi
C. `MongoTemplate.updateFirst(...)` cập nhật một document khớp
D. `MongoTemplate.indexOps(...)` quản lý index cho collection
Đáp án đúng: B

Câu 19. Trên MongoDB document có `@Version`, cập nhật entity đã cũ thường dẫn đến điều gì?
A. Optimistic locking tự merge field của hai bản cạnh tranh
B. MongoDB tăng TTL của entity đang có version cũ
C. MongoDB thay đổi ID document khi version không khớp
D. Optimistic locking phát hiện version mismatch khi lưu
Đáp án đúng: D

Câu 20. Muốn xóa và lấy lại document đầu tiên khớp `Query`, API nào phù hợp?
A. `findAndRemove(query, Order.class)` xóa và trả document
B. `MongoTemplate.findOne(query, Order.class)` xóa và trả
C. `MongoTemplate.findAndModify(query, update)` xóa và trả
D. `MongoTemplate.findAll(query, Order.class)` xóa và trả
Đáp án đúng: A

Câu 21. Để khai báo aggregation pipeline trực tiếp trên repository method, annotation nào phù hợp?
A. `@Indexed` mô tả các stage xử lý của pipeline
B. `@Document` mô tả các stage xử lý của pipeline
C. `@Query` mô tả các stage xử lý của pipeline
D. `@Aggregation` định nghĩa các stage của pipeline
Đáp án đúng: D

Câu 22. Trong aggregation pipeline, stage `$match` được dùng chủ yếu để làm gì?
A. Kết hợp collection khác thông qua khóa tham chiếu
B. Gom các document theo khóa để tính toán tổng hợp
C. `$match` lọc document theo điều kiện trước `$group`
D. Trải phần tử mảng thành từng document đầu ra
Đáp án đúng: C

Câu 23. Khi cần tính tổng `amount` theo `region` trong aggregation, stage nào phù hợp?
A. `$match` gom theo region và cộng amount qua `$sum`
B. `$unwind` gom theo region và cộng amount qua `$sum`
C. `$group` gom theo region và cộng amount qua `$sum`
D. `$sort` gom theo region và cộng amount qua `$sum`
Đáp án đúng: C

Câu 24. Một document có mảng `items` và cần một output cho mỗi phần tử, stage nào phù hợp?
A. Stage `$unwind` tạo document cho mỗi phần tử mảng
B. `$limit` tách từng phần tử mảng thành một document
C. `$count` tách từng phần tử mảng thành một document
D. `$group` tách từng phần tử mảng thành một document
Đáp án đúng: A

Câu 25. Muốn ghép dữ liệu từ collection `customers` khi tổng hợp `orders`, stage nào hỗ trợ?
A. `$unwind` ghép thêm document từ collection khác
B. `$lookup` ghép thêm document từ collection khác
C. `$project` ghép thêm document từ collection khác
D. `$skip` ghép thêm document từ collection khác
Đáp án đúng: B

Câu 26. Để tính tổng doanh số từ các order `PAID` theo `region`, trình tự aggregation nào đúng?
A. Dùng `$group` theo region rồi `$match` status PAID
B. Dùng `$limit` rồi `$group` mà bỏ điều kiện status
C. Áp `$match` PAID trước `$group` theo region để tính tổng
D. Dùng `$sort` rồi `$count` thay phép cộng amount
Đáp án đúng: C

Câu 27. Muốn database từ chối hai document có cùng email khi index đã được tạo, dùng gì?
A. `@Field(targetType = STRING)` trên property email
B. `@Indexed(unique = true)` áp dụng cho email
C. `@Version` trên property email của entity
D. `@Indexed(sparse = true)` trên property email của entity
Đáp án đúng: B

Câu 28. Một truy vấn lọc theo tenant và sort `createdAt` giảm dần; index kép nào phù hợp?
A. Compound index `{ region: -1, currency: 1 }`
B. Index `{ tenantId: 1, createdAt: -1 }` cho query theo tenant
C. Compound index `{ createdAt: 1, tenantId: -1 }`
D. Compound index `{ total: 1, status: -1 }`
Đáp án đúng: B

Câu 29. TTL index áp dụng lên trường thời gian có bảo đảm xóa document chính xác tại lúc hết hạn không?
A. Không; TTL monitor xóa bất đồng bộ sau khi hết hạn theo chu kỳ
B. Có; thao tác update đồng bộ xóa document đúng millisecond
C. Có; collection scan xóa record ngay trước khi mỗi query chạy
D. Không; TTL chỉ đổi trạng thái field mà giữ record nguyên
Đáp án đúng: A

Câu 30. Với index `{tenantId: 1, createdAt: -1}`, truy vấn nào tận dụng tốt phần đầu index?
A. Lọc status và sắp xếp currency tăng theo thời gian
B. Lọc amount và sắp xếp tenantId giảm trong collection
C. Lọc createdAt nhưng bỏ tenantId và sắp xếp theo amount
D. Lọc tenantId bằng giá trị và sắp xếp createdAt giảm
Đáp án đúng: D

Câu 31. Khi chẩn đoán MongoDB query đang scan nhiều document, thông tin nào hữu ích?
A. Spring Data mapping context trả về SQL execution plan
B. Query profiler chỉ cho biết số Java beans của repository
C. Query explain cho biết COLLSCAN/IXSCAN và số tài liệu xét
D. Aggregation result cho biết mức heap JVM trước khi query
Đáp án đúng: C

Câu 32. Muốn dùng MongoDB multi-document transaction trên production, cấu hình triển khai nào phù hợp?
A. Standalone mongod không bật replica set và chỉ dùng journal
B. MongoDB file-based test store không có replica set
C. Replica set hoặc sharded cluster hỗ trợ transaction
D. Collection capped không khai báo replica set trong môi trường
Đáp án đúng: C

Câu 33. Trong Spring Data MongoDB imperative, thành phần nào phối hợp transaction với Spring?
A. `MongoConverter` liên kết transaction và Mongo session
B. `MongoRepositoryFactory` liên kết transaction và Mongo session
C. `MongoMappingContext` liên kết transaction và Mongo session
D. `MongoTransactionManager` quản lý Mongo session theo transaction
Đáp án đúng: D

Câu 34. Một service cần ghi hai collection MongoDB cùng commit/rollback; điều kiện nào phù hợp?
A. Chạy trong Mongo transaction với session và manager đúng
B. Thêm index unique ở cả hai collection để thay transaction
C. Chạy hai lệnh save độc lập không có transaction chung
D. Chỉ dùng `ordered=true` trong BulkOperations cho cả hai
Đáp án đúng: A

Câu 35. Vì sao không thể dựa vào Mongo transaction để rollback HTTP request đã gửi ra ngoài?
A. Mongo transaction sao lưu HTTP request để tự hủy ở backend
B. HTTP side effect không thuộc transaction của MongoDB
C. Mongo transaction giữ kết nối HTTP đến khi commit hoàn tất
D. Mongo transaction dùng broker để phối hợp rollback HTTP
Đáp án đúng: B

Câu 36. `ReactiveMongoTemplate.find(query, Order.class)` thường trả kiểu dữ liệu nào?
A. `List<Order>` được trả ngay khi chưa subscribe
B. `Page<Order>` được tự tạo từ MongoDB reactive driver
C. `Flux<Order>` biểu diễn nhiều document bất đồng bộ
D. `Mono<List<Order>>` là kết quả trực tiếp từ reactive find
Đáp án đúng: C

Câu 37. Muốn định nghĩa CRUD repository reactive cho entity `Order`, interface nào phù hợp?
A. `PagingAndSortingRepository<Order, String>` cho reactive CRUD
B. `MongoRepository<Order, String>` cho reactive CRUD
C. `JpaRepository<Order, String>` cho reactive CRUD
D. `ReactiveMongoRepository<Order, String>` hỗ trợ reactive CRUD
Đáp án đúng: D

Câu 38. Trong pipeline WebFlux sử dụng reactive MongoDB, gọi `.block()` trên event loop có rủi ro gì?
A. Phân phối truy vấn sang boundedElastic dù không cấu hình
B. Tăng MongoDB transaction isolation lên SERIALIZABLE
C. Tự thêm index phục vụ truy vấn trước khi phát response
D. Giữ event-loop thread và gây nghẽn xử lý request khác
Đáp án đúng: D

Câu 39. Với Spring Boot, `@DataMongoTest` thường tập trung kiểm thử nhóm thành phần nào?
A. JPA EntityManager, SQL migration và JDBC transactions
B. Test slice cho Mongo mapping, repository và template
C. Spring Cloud Gateway filters và remote discovery client
D. HTTP controllers, WebSocket handlers và security filter
Đáp án đúng: B

Câu 40. Vì sao dùng Testcontainers MongoDB để kiểm tra truy vấn thay vì chỉ mock repository?
A. Tạo schema SQL tương ứng từ document mapping trong test
B. Điều chỉnh index cho production ngay từ lúc build
C. Chạy query/index trên MongoDB thực trong bài kiểm thử
D. Cải thiện query khi deploy nhờ bỏ qua kiểm tra index
Đáp án đúng: C
