Câu 01. `Repository<T, ID>` trong Spring Data Commons chủ yếu cung cấp điều gì?
A. Cung cấp hàm lấy Page và Sort cho query repository
B. Đánh dấu repository theo domain và ID của entity
C. Cung cấp API tìm entity bằng ExampleMatcher và probe
D. Cung cấp `save` và `deleteById` cho entity
Đáp án đúng: B

Câu 02. Interface nào khai báo các thao tác CRUD cơ bản như `save`, `findById` và `deleteById`?
A. `Repository<T, ID>` khai báo các thao tác CRUD chuẩn
B. `PagingAndSortingRepository<T, ID>` khai báo CRUD chuẩn
C. `CrudRepository<T, ID>` khai báo thao tác CRUD chuẩn
D. `QueryByExampleExecutor<T>` khai báo thao tác CRUD chuẩn
Đáp án đúng: C

Câu 03. Khi `CrudRepository.findById(id)` không tìm thấy entity, giá trị trả về là gì?
A. `Stream.empty()` biểu thị không có entity cho ID
B. `null` biểu thị không có entity cho ID được yêu cầu
C. `Page.empty()` biểu thị không có entity cho ID được hỏi
D. `Optional.empty()` biểu thị không có entity cho ID
Đáp án đúng: D

Câu 04. So với `CrudRepository`, `ListCrudRepository` thay đổi kiểu trả về của `findAll()` thành gì?
A. `Slice<T>` thay vì `Iterable<T>` với truy vấn nhiều entity
B. `List<T>` thay vì `Iterable<T>` với truy vấn nhiều entity
C. `Stream<T>` thay vì `Iterable<T>` với truy vấn nhiều entity
D. `Page<T>` thay vì `Iterable<T>` với truy vấn nhiều entity
Đáp án đúng: B

Câu 05. Trong Spring Data 3+, muốn cùng một repository có CRUD và các API phân trang/sắp xếp, nên làm gì?
A. Chỉ kế thừa `PagingAndSortingRepository` để có cả CRUD
B. Kế thừa cả `CrudRepository` và `PagingAndSortingRepository`
C. Chỉ kế thừa `ListCrudRepository` để có API `findAll(Pageable)`
D. Chỉ kế thừa `Repository` để có đủ paging và sorting
Đáp án đúng: B

Câu 06. Một interface generic làm base cho nhiều repository con nên dùng annotation nào để tránh tạo bean riêng?
A. `@Transactional` trên interface repository cơ sở
B. `@RepositoryDefinition` trên interface repository cơ sở
C. `@EnableJpaRepositories` trên interface repository cơ sở
D. `@NoRepositoryBean` trên interface repository cơ sở
Đáp án đúng: D

Câu 07. Muốn bổ sung logic truy vấn tùy chỉnh theo mô hình repository fragment, hướng nào phù hợp?
A. Kế thừa fragment interface và cung cấp implementation tương ứng
B. Cho repository kế thừa `ExampleMatcher` để cài đặt một fragment
C. Khai báo `Pageable` làm interface base cho custom implementation
D. Chỉ thêm default method vào `Repository` rồi ghi native query trong annotation
Đáp án đúng: A

Câu 08. Muốn khai báo repository bằng interface không `extends Repository`, annotation nào chỉ ra domain và ID type?
A. `@NoRepositoryBean` chỉ rõ domainClass và idClass
B. `@PersistenceCreator` chỉ rõ domainClass và idClass
C. `@RepositoryDefinition` chỉ rõ domainClass và idClass
D. `@EnableJpaAuditing` chỉ rõ domainClass và idClass
Đáp án đúng: C

Câu 09. Trong mapping metadata dùng chung của Spring Data, annotation `@Id` có ý nghĩa gì?
A. Đánh dấu thuộc tính làm định danh của aggregate/entity
B. Đánh dấu thuộc tính không được lưu vào datastore
C. Đánh dấu thuộc tính giữ phiên bản để khóa lạc quan
D. Đánh dấu thuộc tính ghi thời điểm cập nhật cuối cùng
Đáp án đúng: A

Câu 10. Trong datastore hỗ trợ optimistic locking, `@Version` thường được dùng để làm gì?
A. Gắn tên collection/table lưu entity vào metadata
B. Ghi ngày giờ entity được tạo lần đầu theo auditing
C. Đánh dấu trường ID dùng cho truy vấn theo khóa chính
D. Phát hiện ghi đè đồng thời qua phiên bản entity
Đáp án đúng: D

Câu 11. Derived query `findByEmailAndActiveTrue(String email)` thường diễn đạt điều kiện gì?
A. Email trùng đối số hoặc `active` bằng true
B. Email trùng đối số và `active` bằng false
C. Email trùng đối số và thuộc tính `active` có giá trị true
D. Email chứa đối số bất kỳ và bỏ qua thuộc tính `active`
Đáp án đúng: C

Câu 12. Derived query `findByAgeGreaterThan(int age)` thường so khớp entity như thế nào?
A. Trường age bằng giá trị được truyền vào của phương thức
B. Trường age lớn hơn giá trị truyền vào của phương thức
C. Trường age lớn hơn hoặc bằng giá trị được truyền
D. Trường age nhỏ hơn giá trị truyền vào của phương thức
Đáp án đúng: B

Câu 13. Derived query `findByNameContaining(String term)` nhắm tới kiểu điều kiện gì?
A. Thuộc tính name chứa chuỗi term như một phần nội dung
B. Thuộc tính name kết thúc bằng đúng chuỗi term truyền vào
C. Thuộc tính name so khớp toàn bộ chuỗi term truyền vào
D. Thuộc tính name bắt đầu bằng đúng chuỗi term truyền vào
Đáp án đúng: A

Câu 14. Với datastore hỗ trợ, hậu tố `IgnoreCase` trong `findByEmailIgnoreCase` yêu cầu gì?
A. So khớp email có phân biệt chữ hoa/thường
B. Bỏ điều kiện email để chỉ dựa vào các field còn lại
C. Bỏ qua entity có field email thuộc kiểu dữ liệu null
D. So khớp email không phân biệt chữ hoa/thường
Đáp án đúng: D

Câu 15. Derived query `findByCreatedAtBetween(start, end)` diễn đạt gì về thời điểm tạo?
A. Lọc entity theo thứ tự createdAt thay vì theo khoảng
B. Lọc entity chỉ có createdAt lớn hơn mốc end đã truyền
C. Lọc entity có createdAt nằm trong khoảng được truyền
D. Lọc entity chỉ có createdAt nhỏ hơn mốc start đã truyền
Đáp án đúng: C

Câu 16. Method `findByStatusOrderByCreatedAtDesc(status)` yêu cầu thứ tự nào?
A. Lọc theo status; xếp createdAt giảm dần
B. Sắp xếp status giảm dần rồi bỏ điều kiện lọc
C. Lọc theo createdAt rồi sắp xếp status giảm dần
D. Lọc status; xếp createdAt tăng dần
Đáp án đúng: A

Câu 17. Trong tên derived query `findByAddress_City`, ký tự `_` được dùng nhằm mục đích gì?
A. Đổi tên field thành `address_city` trong datastore
B. Chỉ định phân trang theo trường `address.city`
C. Bật phép so khớp không phân biệt hoa thường
D. Chỉ rõ đường đi thuộc tính lồng `address.city`
Đáp án đúng: D

Câu 18. Method `findTop3ByOrderByScoreDesc()` thường được diễn giải như thế nào?
A. Lấy tối đa ba page, mỗi page chứa các score giảm dần
B. Lấy ba entity có score thấp nhất theo thứ tự tăng
C. Lấy toàn bộ entity rồi nhóm theo ba giá trị score
D. Lấy ba entity score cao nhất theo thứ tự giảm
Đáp án đúng: D

Câu 19. Derived query `existsByEmail(String email)` trả về ý nghĩa nào?
A. Giá trị Optional cho entity đầu tiên khớp email
B. Giá trị boolean cho biết có entity khớp email hay không
C. Giá trị List chứa các entity có email tương ứng
D. Giá trị long cho biết số entity khớp email trong datastore
Đáp án đúng: B

Câu 20. Derived query `countByStatus(Status status)` chủ yếu trả về thông tin gì?
A. Số trang cần đọc khi sắp xếp entity theo status
B. Số entity khớp với trạng thái status đã cho
C. Số lần phương thức save được gọi với status
D. Số field có tên status trong entity metadata
Đáp án đúng: B

Câu 21. `PageRequest.of(0, 20)` biểu diễn yêu cầu đọc trang như thế nào?
A. Trang có chỉ số 0 với page size là 20
B. Trang cuối theo chỉ số 0, kích thước tối đa 20
C. Trang thứ hai có page size bằng 20
D. Trang đầu tiên theo chỉ số 1, kích thước tối đa 0
Đáp án đúng: A

Câu 22. So với `Slice<T>`, kết quả `Page<T>` có thêm nhóm thông tin nào?
A. Thông tin tổng số phần tử/trang phù hợp truy vấn
B. Thông tin serializer và bộ chuyển đổi mapping type
C. Thông tin phiên bản entity khi lưu trên mỗi partition
D. Danh sách các headers của request HTTP hiện tại
Đáp án đúng: A

Câu 23. Vì sao chọn `Slice<T>` khi client chỉ cần tải tiếp các trang kế tiếp?
A. Có thể nhận tổng số trang chính xác với ít truy vấn hơn
B. Xem `hasNext` mà không cần biết tổng bản ghi
C. Có thể lấy toàn bộ entity của tập kết quả trong memory
D. Có thể đồng bộ offset commit giữa các consumer group
Đáp án đúng: B

Câu 24. Muốn sort kết quả theo `createdAt` giảm dần với Spring Data Commons, cách nào hợp lệ?
A. `Sort.by("createdAt").ascending()`
B. `Sort.by("createdAt").descending()`
C. `Sort.by(Sort.Direction.ASC, "createdAt")`
D. `Sort.unsorted().and(Sort.by("createdAt"))`
Đáp án đúng: B

Câu 25. Giá trị `Pageable.unpaged()` mang ý nghĩa gì đối với truy vấn repository?
A. Yêu cầu chia kết quả theo page size mặc định là 20
B. Yêu cầu dùng page cuối cùng theo tổng số entity
C. Đọc kết quả mà không áp dụng phân trang
D. Yêu cầu trả page đầu tiên với kích thước là một
Đáp án đúng: C

Câu 26. Trong repository hỗ trợ paging, chữ ký nào cho phép truyền điều kiện status và phân trang động?
A. `Page<User> findByStatus(String status, Sort sort)`
B. `List<User> findByStatus(String status, ExampleMatcher m)`
C. `Page<User> findByStatus(String s, Pageable p)`
D. `User findByStatus(String status, ScrollPosition p)`
Đáp án đúng: C

Câu 27. Muốn lấy tổng số entity thuộc cả tập kết quả từ một `Page<User> page`, gọi API nào?
A. `page.getNumber()` cho tổng phần tử của toàn bộ truy vấn
B. `page.getTotalElements()` cho tổng phần tử của truy vấn
C. `page.getNumberOfElements()` cho tổng phần tử truy vấn
D. `page.getSize()` cho tổng phần tử của toàn bộ truy vấn
Đáp án đúng: B

Câu 28. Muốn vừa phân trang vừa sắp xếp theo giá giảm dần, cách tạo Pageable nào phù hợp?
A. `PageRequest.of(0,20,Sort.by("price").descending())`
B. `PageRequest.of(20, 0, Sort.by("price").descending())`
C. `PageRequest.of(0, 20, Sort.unsorted())`
D. `PageRequest.of(0, 20, Sort.by("price").ascending())`
Đáp án đúng: A

Câu 29. Closed interface-based projection thường định nghĩa dữ liệu cần đọc theo cách nào?
A. DTO class dùng constructor tùy ý không gắn property domain
B. Interface chỉ khai báo getters tương ứng thuộc tính domain
C. Interface dùng SpEL `@Value` để tính field từ toàn entity
D. Entity tự thiết lập toàn bộ association khi fetch projection
Đáp án đúng: B

Câu 30. Khi dùng class-based DTO projection, Spring Data thường cần yếu tố nào để tạo đối tượng?
A. Annotation `@Version` để biết tên constructor DTO
B. Interface getter với Spring proxy thay cho DTO constructor
C. Constructor có tham số phù hợp dữ liệu projection cần map
D. Bean `ExampleMatcher` để khởi tạo các trường DTO
Đáp án đúng: C

Câu 31. Chữ ký nào mô tả cơ chế dynamic projection của Spring Data?
A. `Page<User> findByLastname(String name, Sort sort)`
B. `Optional<User> findByLastname(String name)`
C. `List<User> findByLastname(String name, Pageable pageable)`
D. `<T> List<T> findByLastname(String name, Class<T> type)`
Đáp án đúng: D

Câu 32. Open projection dùng `@Value` với SpEL khác closed projection chủ yếu ở điểm nào?
A. Getter có thể tính giá trị bằng SpEL trên target
B. Getter chỉ map trực tiếp từ property cùng tên
C. Giá trị getter được bind từ tham số `Pageable` của request
D. Giá trị getter chỉ đọc annotation `@Id` từ entity gốc
Đáp án đúng: A

Câu 33. Khi tạo `Example.of(probe)` mặc định, thuộc tính nào của probe thường được xét khớp?
A. Các property có giá trị khác null trong probe được đưa vào
B. Các property không phải chuỗi bị đưa ra khỏi truy vấn
C. Các property null trong probe được chuyển thành điều kiện null
D. Các property được đánh dấu `@Id` bị thay bằng count query
Đáp án đúng: A

Câu 34. `ExampleMatcher.matchingAny()` thay đổi cách kết hợp nhiều điều kiện từ probe như thế nào?
A. Sắp xếp các điều kiện probe theo tên thuộc tính tăng dần
B. Bỏ các thuộc tính chuỗi khi dữ liệu probe có nhiều field
C. Khớp một trong các tiêu chí đã được đưa vào Example
D. Yêu cầu thỏa đồng thời các tiêu chí được đưa vào Example
Đáp án đúng: C

Câu 35. Với chuỗi trong Query by Example, `ExampleMatcher.withIgnoreCase()` dùng để làm gì?
A. Chuyển điều kiện chuỗi sang tìm kiếm phân biệt hoa/thường
B. Bỏ toàn bộ trường chuỗi khỏi Example hiện tại
C. Sắp xếp kết quả theo giá trị chuỗi không dấu
D. Cho phép so khớp chuỗi không phân biệt chữ hoa/thường
Đáp án đúng: D

Câu 36. Interface nào bổ sung API tìm kiếm theo `Example<S>` cho repository hỗ trợ QBE?
A. `Repository<T, ID>` hỗ trợ query theo Example
B. `PagingAndSortingRepository<T, ID>` hỗ trợ Example
C. `ListCrudRepository<T, ID>` hỗ trợ query theo Example
D. `QueryByExampleExecutor<T>` cho phép tìm qua Example
Đáp án đúng: D

Câu 37. Trong auditing, annotation nào ghi dấu thời điểm entity được tạo?
A. `@CreatedBy` dùng cho thời điểm entity được tạo
B. `@LastModifiedBy` dùng cho thời điểm entity được tạo
C. `@CreatedDate` dùng cho thời điểm entity được tạo
D. `@LastModifiedDate` dùng cho thời điểm entity được tạo
Đáp án đúng: C

Câu 38. Annotation auditing nào đánh dấu thời điểm entity được cập nhật?
A. `@LastModifiedDate` ghi thời điểm cập nhật
B. `@CreatedDate` ghi lúc update entity
C. `@LastModifiedBy` ghi thời điểm thay đổi gần nhất
D. `@CreatedBy` ghi thời điểm thay đổi gần nhất
Đáp án đúng: A

Câu 39. Trong Spring Data auditing, `AuditorAware<T>` cung cấp thông tin gì?
A. Tên repository hiện tại để tạo phân trang mặc định
B. Thời gian UTC hiện tại cho CreatedDate/LastModifiedDate
C. Phiên bản entity hiện tại cho trường được gắn `@Version`
D. Cung cấp actor hiện tại cho CreatedBy/LastModifiedBy
Đáp án đúng: D

Câu 40. Khi chuyển repository từ JPA sang MongoDB, giới hạn nào cần lưu ý ở Spring Data Commons?
A. Cấu trúc derived query được thực thi bởi một SQL engine chung
B. Các annotation mapping sẽ tương ứng cùng mô hình tài liệu
C. Kiểm lại khả năng hỗ trợ query/transaction theo từng store
D. Các phép join và transaction sẽ có cùng hành vi ở hai store
Đáp án đúng: C
