Câu 1. Trong Spring Boot, starter nào phù hợp để công bố repository qua Spring Data REST?
A. Thêm `spring-boot-starter-actuator` để export repository.
B. Thêm `spring-boot-starter-hateoas` thay cho Data REST.
C. Thêm `spring-boot-starter-data-rest` cho ứng dụng.
D. Thêm `spring-boot-starter-web` và bật `@EnableJpaRepositories`.
Đáp án đúng: C

Câu 2. Khi đặt `@RepositoryRestResource(path="books", collectionResourceRel="library")`, cấu hình có tác dụng gì?
A. `books` là path collection; `library` là HAL collection rel.
B. `library` là path item; `books` là JSON content type.
C. `library` là path collection; `books` là HAL collection rel.
D. `books` là path finder; `library` là projection name.
Đáp án đúng: A

Câu 3. Cần đặt các endpoint Spring Data REST dưới `/api`; property nào phù hợp?
A. Dùng `management.endpoints.web.base-path=/api` cho repository.
B. Dùng `spring.data.jpa.repositories.path=/api` cho các endpoint.
C. Dùng `spring.mvc.servlet.path=/api` để đổi riêng Data REST.
D. Dùng `spring.data.rest.base-path=/api` trong cấu hình.
Đáp án đúng: D

Câu 4. Một repository được Spring Data REST cho phép export thì tài nguyên HTTP sinh từ đâu?
A. Từ repository interface và metadata entity tương ứng.
B. Từ schema SQL rồi sinh controller từ tên cột database.
C. Từ `@EntityGraph` rồi xuất endpoint theo fetch plan.
D. Từ `@RestController` khai báo cho từng CRUD method.
Đáp án đúng: A

Câu 5. Response HAL của Spring Data REST thường có Content-Type nào?
A. Media type `application/json-patch+json` cho response GET.
B. Media type `application/hal+json` cho biểu diễn HAL.
C. Media type `application/problem+json` cho collection bình thường.
D. Media type `application/x-www-form-urlencoded` cho các HAL link.
Đáp án đúng: B

Câu 6. Trong HAL representation, trường `_links` dùng để biểu diễn gì?
A. Chứa các field không được phép cập nhật bằng PATCH.
B. Chứa link có rel để client điều hướng các resource.
C. Chứa page number, size và totalElements của collection.
D. Chứa các entity con được nhúng vào collection response.
Đáp án đúng: B

Câu 7. Trong HAL collection response, `_embedded` thường chứa gì?
A. Những quy tắc xác thực người dùng trước khi truy cập.
B. Những URI mẫu của toàn bộ query method có thể gọi.
C. Những resource được nhúng trong tập kết quả trả về.
D. Những header HTTP ETag được gửi kèm representation.
Đáp án đúng: C

Câu 8. Link `self` trong HAL của một item giúp client làm gì?
A. Xác định URI xóa toàn bộ collection chứa resource.
B. Xác định phương thức HTTP dùng để cập nhật mọi field.
C. Xác định URI chuẩn liên kết tới resource hiện tại.
D. Xác định ID của repository method đã xử lý request.
Đáp án đúng: C

Câu 9. Ưu điểm HATEOAS khi client làm việc với repository API là gì?
A. Cho phép bỏ kiểm thử các link không còn khả dụng.
B. Khám phá quan hệ qua link thay vì tự ghép URL.
C. Giữ cố định cấu trúc JSON dù API được đổi version.
D. Loại bỏ bước kiểm tra quyền cho link được cung cấp.
Đáp án đúng: B

Câu 10. Với repository `Book` được expose ở `/books`, HTTP request nào lấy collection?
A. Gửi `GET /books` để đọc tập tài nguyên của repository.
B. Gửi `PATCH /books` để liệt kê item theo trường đã sửa.
C. Gửi `DELETE /books` để lấy danh sách item đã bị xóa.
D. Gửi `POST /books` để nhận collection mà không tạo item.
Đáp án đúng: A

Câu 11. Khi có resource `Book` id `42`, URI thông thường nào lấy riêng item?
A. Gửi `GET /books/42/search` để truy xuất item bằng finder.
B. Gửi `GET /books?id=42` để dùng id endpoint chuẩn HAL.
C. Gửi `GET /books/search/42` như endpoint item mặc định.
D. Gửi `GET /books/42` đến endpoint item đã được export.
Đáp án đúng: D

Câu 12. Muốn tạo item mới qua collection repository REST có quyền ghi, thao tác nào thường phù hợp?
A. Gửi `POST /books/42` để tạo item mới trong collection.
B. Gửi `PATCH /books` để sinh một Book chưa có id.
C. Gửi `PUT /books` để thay toàn bộ collection bằng Book mới.
D. Gửi `POST /books` với body hợp lệ để tạo Book.
Đáp án đúng: D

Câu 13. Khi chỉ muốn thay đổi `title` của một Book hiện có, HTTP method nào biểu đạt partial update?
A. Dùng `PATCH /books/{id}` với field title cần cập nhật.
B. Dùng `HEAD /books/{id}` để thay thuộc tính của item.
C. Dùng `GET /books/{id}` với body JSON chứa title mới.
D. Dùng `POST /books/{id}` để thay một field của item.
Đáp án đúng: A

Câu 14. Khi repository cho phép xóa, request nào thường xóa Book id 42?
A. Gửi `DELETE /books` mà không chọn id của item.
B. Gửi `DELETE /books/42` tới item resource tương ứng.
C. Gửi `POST /books/search/deleteById` như endpoint CRUD mặc định.
D. Gửi `PATCH /books` với query parameter `delete=true`.
Đáp án đúng: B

Câu 15. Một Book liên kết Author, Spring Data REST thường biểu diễn association thế nào?
A. Dùng tên cột khóa ngoại làm đường dẫn root API khác.
B. Dùng HTTP header Location để đưa toàn bộ quan hệ vào body.
C. Dùng link `self` của Book thay thế liên kết đến Author.
D. Dùng link quan hệ, ví dụ `books/42/author`, để khám phá.
Đáp án đúng: D

Câu 16. Cần gán Author hiện có cho quan hệ một-một của Book qua API sinh sẵn; cách nào phù hợp?
A. Gửi `PUT` tới collection `/authors` với query id của Book.
B. Gửi `PATCH` tới resource Author để gán Book làm chủ sở hữu.
C. Gửi `POST` tới association với body `application/hal+json`.
D. Gửi `PUT` tới association với body `text/uri-list` của Author.
Đáp án đúng: D

Câu 17. Muốn ẩn một repository query method khỏi HTTP API được export, dùng gì?
A. Gắn `@Transactional(readOnly=true)` để khóa HTTP finder.
B. Gắn `@RestResource(exported=false)` trên finder cần ẩn.
C. Gắn `@JsonIgnore` trên repository interface để ẩn route.
D. Gắn `@Column(updatable=false)` vào field finder truy cập.
Đáp án đúng: B

Câu 18. Muốn đổi đường dẫn và rel của một finder trên repository, annotation nào phù hợp?
A. Gắn `@RequestMapping("by-title")` trên field của Book entity.
B. Gắn `@RepositoryRestResource(path="by-title")` lên method finder.
C. Gắn `@JsonProperty("by-title")` vào method parameter.
D. Gắn `@RestResource(path="by-title", rel="by-title")` cho finder.
Đáp án đúng: D

Câu 19. Repository có finder `findByTitle(@Param("title") String title)`; URI nào thường truy cập finder?
A. Gọi `/books?findByTitle=Spring` như property filter mặc định.
B. Gọi `/books/42/search?title=Spring` như finder ở item resource.
C. Gọi `/books/findByTitle/Spring` như đường dẫn collection chuẩn.
D. Gọi `/books/search/findByTitle?title=Spring` nếu đã export.
Đáp án đúng: D

Câu 20. Trong finder được xuất bản qua REST, `@Param("title")` có vai trò gì?
A. Khai báo relation HAL mới cho collection trong response.
B. Khai báo projection để endpoint trả ít field hơn.
C. Liên kết tên query parameter với tham số của finder.
D. Khai báo tên database index mà repository phải sử dụng.
Đáp án đúng: C

Câu 21. Khi collection hỗ trợ `Pageable`, `?page=1&size=20` thường yêu cầu gì?
A. Trang đầu tiên bắt đầu ở offset 1 với tối đa 20 item.
B. Trang thứ hai với tối đa 20 item khi page bắt đầu từ 0.
C. 20 trang đầu tiên, mỗi trang có tối đa một item duy nhất.
D. Trang đầu tiên với đúng 20 item bỏ qua tổng số document.
Đáp án đúng: B

Câu 22. Muốn lấy Book theo title tăng dần qua collection endpoint, tham số nào phù hợp?
A. Dùng `order=title&direction=up` trong URI resource item.
B. Dùng `sort=title,asc` trong query string collection.
C. Dùng `sortBy=title:ascending` như cú pháp của HAL pager.
D. Dùng `orderBy=title;ascending` như chuẩn của Spring Data REST.
Đáp án đúng: B

Câu 23. Trong HAL response của collection có phân trang, trường `page.totalElements` cho biết gì?
A. Tổng số phần tử của tập kết quả trước khi chia trang.
B. Số phần tử thực tế có trong trang HTTP response hiện tại.
C. Chỉ số page bắt đầu từ 0 của trang đang được yêu cầu.
D. Số item có quan hệ link `self` đã được client truy cập.
Đáp án đúng: A

Câu 24. Cần một cách biểu diễn Book ngắn hơn khi đọc mà không sửa entity; dùng gì?
A. Tạo `@Projection` tên `summary`, chọn qua `?projection=summary`.
B. Đặt `@JsonView` trên repository, dùng `?projection=summary`.
C. Đặt `@RepositoryRestResource` trên DTO để tự tạo projection.
D. Đặt `@RestResource` vào field rồi chọn `?view=summary`.
Đáp án đúng: A

Câu 25. Nếu projection chỉ hiện tên và giá, có thể coi nó là cơ chế bảo mật dữ liệu nhạy cảm không?
A. Projection ngăn truy cập field qua các endpoint association.
B. Projection kiểm soát quyền repository method theo role.
C. Projection chặn endpoint item detail khi response rút gọn.
D. Projection ngắn không ngăn lộ field qua các representation khác.
Đáp án đúng: D

Câu 26. Muốn chạy logic ứng dụng ngay trước khi tạo entity qua repository REST, dùng hook nào?
A. Dùng `@ControllerAdvice` cùng `@ExceptionHandler` cho 201.
B. Dùng `@RestController` cùng `@GetMapping` trước create.
C. Dùng `@RepositoryEventHandler` và `@HandleBeforeCreate`.
D. Dùng `@Projection` để thực thi getter khi entity được tạo.
Đáp án đúng: C

Câu 27. Để chạy xử lý nghiệp vụ ngay trước khi lưu thay đổi entity, event handler nào phù hợp?
A. Dùng `@HandleAfterDelete` để kiểm tra trước thao tác save.
B. Dùng `@HandleAfterCreate` để thực thi trước khi update.
C. Dùng `@HandleBeforeSave` trong repository event handler.
D. Dùng `@HandleBeforeLinkDelete` cho cập nhật scalar field.
Đáp án đúng: C

Câu 28. Muốn dùng Spring Validator với lifecycle `beforeCreate` của Data REST, cách nào phù hợp?
A. Đăng ký `Validator` cho `beforeCreate` qua event listener.
B. Thay validation bằng `spring.data.rest.default-page-size`.
C. Đặt Validator trong `RepositoryRestResource` trên entity.
D. Đặt `@Param` trên method repository để kiểm tra input.
Đáp án đúng: A

Câu 29. Muốn chỉ nhân viên được sửa Book qua HTTP API repository, nên áp dụng gì?
A. Cấu hình Spring Security authorization theo route hoặc method.
B. Ẩn link `self` trong HAL response để cấm request ghi.
C. Đổi collection rel thành tên khó đoán trong `@RepositoryRestResource`.
D. Giảm `page-size` để client không thấy endpoint sửa dữ liệu.
Đáp án đúng: A

Câu 30. Vì sao `@RestResource(exported=false)` không thay thế kiểm soát truy cập dữ liệu?
A. Cờ export làm mất quyền đọc/ghi entity tại DB layer.
B. Cờ export ẩn route; kiểm soát quyền vẫn cần ở nơi khác.
C. Cờ export chuyển mọi repository method thành chỉ đọc.
D. Cờ export chỉ ẩn JSON nhưng không ảnh hưởng HTTP route.
Đáp án đúng: B

Câu 31. Khi Spring Data REST sinh API từ entity persistence, rủi ro thiết kế hợp đồng nào cần cân nhắc?
A. Repository API không phụ thuộc mapping entity persistence.
B. HAL link giữ nguyên mọi trường JSON khi entity schema đổi.
C. Đổi entity/repository có thể làm thay đổi API công khai.
D. Projection tự tạo phiên bản endpoint khi schema đổi.
Đáp án đúng: C

Câu 32. Muốn kiểm thử endpoint repository xuất HAL có phân trang và kiểm soát quyền, cách nào phù hợp?
A. Kiểm tra DTO getter rồi kết luận pageable query param đã đúng.
B. Mock repository rồi suy ra HAL response và HTTP status đều đúng.
C. Dùng MockMvc integration test để kiểm tra HAL, page và quyền.
D. Dùng reflection kiểm tra annotation và bỏ HTTP level test.
Đáp án đúng: C
