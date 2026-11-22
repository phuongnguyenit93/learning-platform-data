# HTTP `409 Conflict` trong Spring Data REST: xung đột ràng buộc dữ liệu và khóa lạc quan

## Mục tiêu

HTTP `409 Conflict` báo rằng yêu cầu không thể áp dụng vì trạng thái hiện tại của tài nguyên hoặc dữ liệu đã có xung đột. Trong Spring Data REST, hai nhóm lỗi thường được ánh xạ thành `409` là:

- Vi phạm ràng buộc toàn vẹn do tầng lưu trữ báo về, thường được bọc trong `DataIntegrityViolationException`.
- Xung đột khóa lạc quan, được biểu diễn bởi `OptimisticLockingFailureException`.

Cần phân biệt hai nhóm này với lỗi kiểm tra dữ liệu đầu vào và với điều kiện HTTP `If-Match`. Chúng có thể tạo ra các status khác nhau dù đều liên quan đến dữ liệu không còn phù hợp.

## 1. Phân biệt status code

| Tình huống | Dấu hiệu chính | Status thường dùng |
| --- | --- | --- |
| Dữ liệu vi phạm constraint của database, ví dụ trùng khóa duy nhất hoặc xóa bản ghi đang được tham chiếu | `DataIntegrityViolationException` hoặc `DuplicateKeyException` | `409 Conflict` |
| Bản ghi bị cập nhật/xóa bởi một giao dịch khác sau khi request đã đọc phiên bản cũ | `OptimisticLockingFailureException` | `409 Conflict` |
| Validator của Spring Data REST từ chối entity trước khi lưu | `RepositoryConstraintViolationException` | `400 Bad Request` |
| Bean Validation hoặc body JSON không hợp lệ | `ConstraintViolationException`, `HttpMessageNotReadableException` | `400 Bad Request` |
| Client gửi `If-Match` với ETag đã cũ | ETag hiện tại không khớp header điều kiện | `412 Precondition Failed` |
| Client gửi `If-None-Match` trùng ETag hiện tại khi GET | Tài nguyên chưa thay đổi | `304 Not Modified` |

Spring Data REST cung cấp `RepositoryRestExceptionHandler` để xử lý lỗi từ các controller được framework tạo ra. Với cấu hình mặc định, lỗi constraint ở tầng lưu trữ và lỗi optimistic locking được trả về như xung đột `409`. Nếu ứng dụng có `@ControllerAdvice` riêng, hãy kiểm tra thứ tự và phạm vi xử lý vì advice tùy chỉnh có thể thay đổi kết quả.

Một điểm dễ nhầm: `RepositoryConstraintViolationException` **kế thừa** `DataIntegrityViolationException`, nhưng nó được ném ra khi Spring `Validator` báo lỗi. Đây là lỗi validation và cần giữ ở `400`, không nên để handler tổng quát cho `DataIntegrityViolationException` vô tình đổi nó thành `409`.

## 2. Xung đột ràng buộc dữ liệu ở database

`DataIntegrityViolationException` là exception của Spring DAO cho trường hợp câu lệnh SQL bị từ chối vì dữ liệu vi phạm một quy tắc toàn vẹn. Ví dụ thường gặp:

- Giá trị trùng primary key hoặc unique constraint.
- Giá trị `NULL` được ghi vào cột bắt buộc.
- Xóa một bản ghi cha đang được bản ghi khác tham chiếu bằng foreign key.
- Giá trị không thỏa một check constraint.

`DuplicateKeyException` là lớp con cụ thể hơn, nhưng nên xử lý ở mức `DataIntegrityViolationException` khi muốn hỗ trợ nhiều loại database và nhiều kiểu constraint.

Ví dụ entity JPA có mã sản phẩm duy nhất:

~~~java
@Entity
class Product {

    @Id
    @GeneratedValue
    private Long id;

    @Column(nullable = false, unique = true)
    private String sku;

    @Version
    private Long version;
}
~~~

Khi schema thật sự có unique constraint trên `sku`, request tạo một sản phẩm đã tồn tại sẽ bị database từ chối. Spring dịch lỗi persistence thành `DataIntegrityViolationException`; Spring Data REST có thể trả:

~~~http
HTTP/1.1 409 Conflict
~~~

Ví dụ request:

~~~bash
curl -i -X POST http://localhost:8080/products \
  -H 'Content-Type: application/json' \
  -d '{"sku":"BOOK-001"}'
~~~

Gửi lại cùng mã `BOOK-001` khi constraint đã được tạo sẽ tạo xung đột. Client nên chọn mã khác hoặc hiển thị lý do nghiệp vụ phù hợp.

**Lưu ý về schema:** `@Column(unique = true)` mô tả mapping JPA và có thể tạo constraint khi ứng dụng tự sinh schema. Với môi trường thật, hãy xác nhận migration đã tạo unique index/constraint tương ứng. Kiểm tra `existsBySku(...)` trước khi insert không thay thế được constraint của database vì hai request đồng thời vẫn có thể cùng vượt qua bước kiểm tra.

## 3. Khóa lạc quan và `@Version`

Khóa lạc quan phát hiện hai thao tác cùng sửa một phiên bản dữ liệu. Nó không giữ khóa database trong suốt thời gian người dùng đọc và chỉnh sửa.

Với entity có trường version:

~~~java
@Entity
class Product {

    @Id
    @GeneratedValue
    private Long id;

    private String name;

    @Version
    private Long version;
}
~~~

Nếu dùng Spring Data JPA, dùng annotation `jakarta.persistence.Version`. Với các module Spring Data khác, dùng `org.springframework.data.annotation.Version` theo hướng dẫn của module đó.

Khi lưu một entity có version, Spring Data kiểm tra version trong persistence store. Một cập nhật thường có dạng khái niệm:

~~~sql
UPDATE product
SET name = ?, version = 8
WHERE id = ? AND version = 7
~~~

Nếu một giao dịch khác đã chuyển version từ `7` sang `8`, câu lệnh của client đang giữ version `7` không còn cập nhật được hàng nào. Spring Data ném `OptimisticLockingFailureException`. Tài liệu `CrudRepository.save()` cũng nêu rõ exception này được ném khi version của entity khác version đang lưu; các thao tác xóa entity có version cũng có thể gặp lỗi tương tự.

Ví dụ luồng hai client:

1. Client A và B cùng đọc sản phẩm ở version `7`.
2. A lưu trước; dữ liệu được cập nhật và version tăng lên `8`.
3. B gửi bản entity cũ với version `7`.
4. Persistence layer phát hiện version không khớp và ném `OptimisticLockingFailureException`.
5. Khi exception đi qua handler mặc định của Spring Data REST, client B nhận `409 Conflict`.

Client không nên gửi lại nguyên payload cũ theo vòng lặp vô hạn. Hãy đọc lại tài nguyên, so sánh thay đổi của người dùng với dữ liệu mới nhất, hợp nhất nếu hợp lệ rồi mới gửi lại.

## 4. ETag và `If-Match`: trường hợp trả về 412

Spring Data REST dùng trường `@Version` để tạo header `ETag` cho tài nguyên. Client có thể dùng ETag này làm điều kiện khi `PUT`, `PATCH` hoặc `DELETE`.

Đọc tài nguyên:

~~~http
GET /products/42

HTTP/1.1 200 OK
ETag: "7"
~~~

Client gửi thay đổi kèm ETag đã đọc:

~~~bash
curl -i -X PATCH http://localhost:8080/products/42 \
  -H 'If-Match: "7"' \
  -H 'Content-Type: application/json' \
  -d '{"name":"Tên mới"}'
~~~

Nếu client khác đã cập nhật tài nguyên và ETag hiện tại không còn là `"7"`, Spring Data REST từ chối thao tác với `412 Precondition Failed`. Đây là kết quả của điều kiện HTTP `If-Match`, khác với exception optimistic locking được ném ra từ repository.

Vì vậy, khi debug một request cập nhật đồng thời:

- `409`: tầng lưu trữ/repository báo xung đột, chẳng hạn `OptimisticLockingFailureException`.
- `412`: header `If-Match` mà client gửi không khớp ETag hiện tại.

Với GET, `If-None-Match` có tác dụng khác: nếu ETag khớp, Spring Data REST trả `304 Not Modified` và không gửi lại representation. Chỉ dùng ETag với đúng URI và tham số truy vấn đã tạo ra ETag đó.

## 5. Giữ lỗi validation ở 400

Spring Data REST cho phép đăng ký `Validator` bằng tên bean gắn với event. Ví dụ bean có tên `beforeCreateProductValidator` được gọi trước khi tạo `Product`; `beforeSaveProductValidator` được gọi trước khi lưu entity hiện có. Có thể đăng ký thủ công qua `RepositoryRestConfigurer.configureValidatingRepositoryEventListener(...)` và `ValidatingRepositoryEventListener.addValidator(...)`.

Khi validator từ chối entity, Spring Data REST ném `RepositoryConstraintViolationException`. Exception này có phương thức `getErrors()` để lấy lỗi validation và có quan hệ kế thừa từ `DataIntegrityViolationException`. Handler mặc định phân biệt nó với lỗi constraint database và trả `400 Bad Request`.

Nếu ứng dụng tự viết `@RestControllerAdvice`, khai báo handler cụ thể cho `RepositoryConstraintViolationException` trước khi xử lý `DataIntegrityViolationException` tổng quát:

~~~java
@RestControllerAdvice
class ApiExceptionHandler {

    @ExceptionHandler(RepositoryConstraintViolationException.class)
    ResponseEntity<ApiError> validation(
            RepositoryConstraintViolationException ex) {
        return ResponseEntity.badRequest()
                .body(new ApiError("VALIDATION_FAILED",
                        "Dữ liệu gửi lên không hợp lệ"));
    }

    @ExceptionHandler(DataIntegrityViolationException.class)
    ResponseEntity<ApiError> integrity(
            DataIntegrityViolationException ex) {
        return ResponseEntity.status(HttpStatus.CONFLICT)
                .body(new ApiError("DATA_CONFLICT",
                        "Dữ liệu xung đột với trạng thái hiện tại"));
    }

    @ExceptionHandler(OptimisticLockingFailureException.class)
    ResponseEntity<ApiError> optimisticLock(
            OptimisticLockingFailureException ex) {
        return ResponseEntity.status(HttpStatus.CONFLICT)
                .body(new ApiError("STALE_VERSION",
                        "Tài nguyên đã được cập nhật; hãy tải lại trước khi thử lại"));
    }
}
~~~

`ApiError` ở ví dụ là DTO response do ứng dụng định nghĩa. Chỉ thêm handler tùy chỉnh khi cần định dạng response ổn định hoặc thông điệp nghiệp vụ riêng; nếu dùng, kiểm tra advice có thực sự được áp dụng cho endpoint Spring Data REST. Không trả nguyên SQL, tên bảng, constraint nội bộ hoặc stack trace cho client.

## 6. Kiểm thử hành vi

Nên kiểm thử cả exception ở repository và status code ở HTTP boundary. Dùng database test có constraint thật; với lỗi constraint, `saveAndFlush()` giúp ép SQL chạy ngay để test quan sát được lỗi.

### 6.1. Trùng unique key trả 409

Với `ProductRepository` và unique constraint trên `sku`, lưu trước một sản phẩm rồi POST cùng SKU qua endpoint được Spring Data REST export:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class ProductRestConflictTests {

    @Autowired
    MockMvc mvc;

    @Autowired
    ProductRepository repository;

    @Test
    void duplicateSkuReturns409() throws Exception {
        Product existing = new Product();
        existing.setSku("SKU-001");
        repository.saveAndFlush(existing);

        mvc.perform(post("/products")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"sku\":\"SKU-001\"}"))
            .andExpect(status().isConflict());
    }
}
~~~

Test này xác nhận đường đi từ database constraint qua exception translation đến HTTP response. Dữ liệu chuẩn bị cần được commit/flush trước request; tránh để test transaction che khuất thời điểm constraint được kiểm tra.

### 6.2. Entity có version từ chối bản sao cũ

Trong test persistence, đọc entity thành bản cũ, cập nhật và flush một bản mới, sau đó thử lưu bản cũ:

~~~java
Product stale = repository.findById(id).orElseThrow();
entityManager.detach(stale);

Product current = repository.findById(id).orElseThrow();
current.setName("Bản mới");
repository.saveAndFlush(current);

stale.setName("Bản cũ");
assertThatThrownBy(() -> repository.saveAndFlush(stale))
        .isInstanceOf(OptimisticLockingFailureException.class);
~~~

Test này xác nhận optimistic locking tại repository. Bổ sung một integration test qua endpoint Spring Data REST để xác nhận exception được ánh xạ thành `409` trong cấu hình ứng dụng thực tế.

### 6.3. ETag cũ trả 412

1. Gọi GET tài nguyên và lưu giá trị header `ETag`.
2. Cập nhật entity qua repository để tăng version.
3. Gọi `PATCH` cùng URI với `If-Match` chứa ETag cũ.
4. Assert `status().isPreconditionFailed()`.

Test này kiểm tra đường điều kiện HTTP, không thay thế test repository ở mục 6.2.

### 6.4. Validator và GET có điều kiện

- Gửi entity vi phạm `beforeCreateProductValidator` và assert `400 Bad Request`.
- Gửi GET với `If-None-Match` bằng ETag hiện tại và assert `304 Not Modified`.
- Với race test, dùng hai transaction/persistence context độc lập và đồng bộ thời điểm đọc bằng `CountDownLatch` hoặc `CyclicBarrier`. Không dựa vào timing ngẫu nhiên; xác nhận một thao tác thắng và thao tác còn lại nhận đúng conflict/precondition status theo đường xử lý.

Chạy test theo build của dự án, ví dụ `./mvnw test` hoặc `mvn test`.

## 7. Troubleshooting

**Nhận 400 trong khi mong đợi 409**

- Kiểm tra exception thực tế. Nếu là `RepositoryConstraintViolationException`, đây là lỗi từ Spring `Validator` và 400 là phù hợp.
- Nếu dùng advice riêng, kiểm tra handler cho lớp con có bị handler `DataIntegrityViolationException` hoặc catch-all xử lý trước hay không.
- Phân biệt lỗi Bean Validation/JSON binding với constraint do database thực thi.

**Nhận 412 thay vì 409**

- Kiểm tra request có gửi `If-Match` không.
- Đọc lại tài nguyên và lấy ETag mới; không tái sử dụng ETag của URI khác hoặc của lần đọc cũ.
- Nếu nghiệp vụ cần phát hiện xung đột ở repository, kiểm tra version field và đường lưu thực tế; đừng đổi 412 thành 409 chỉ để làm status giống nhau.

**Nhận 500 khi ghi dữ liệu trùng hoặc stale version**

- Xem class exception và cause chain trong log; dùng `getMostSpecificCause()` để tìm lỗi persistence gốc.
- Xác nhận database schema có constraint thật và Spring Data/JPA đang dịch exception như mong đợi.
- Kiểm tra exception có bị bọc trong exception tùy chỉnh hoặc bị catch rồi ném lại thành lỗi tổng quát hay không.
- Với `@Version`, xác nhận đúng annotation cho module, trường version được map và các thao tác đi qua repository có hỗ trợ optimistic locking. Một số bulk update/query có thể bỏ qua cơ chế version.

**Database không báo lỗi khi tạo dữ liệu trùng**

- Kiểm tra unique constraint/index trên database đang chạy, không chỉ annotation trong entity.
- Không dựa vào bước `existsBy...` làm cơ chế chống trùng duy nhất; database constraint mới xử lý được hai insert đồng thời.

**Thông điệp lỗi làm lộ chi tiết database**

- Ghi log đầy đủ exception ở server với correlation/request ID.
- Trả DTO lỗi ổn định như `DATA_CONFLICT` hoặc `STALE_VERSION`; không trả SQL, constraint name nhạy cảm hay stack trace.
- Chỉ ánh xạ sang `409` khi biết đây là xung đột có thể giải quyết ở phía client. Lỗi mapping/schema hoặc lỗi vận hành cần được phân loại riêng, không gom mọi `DataAccessException` thành conflict.

## 8. Tài liệu chính thức

- [Spring Data REST — Conditional Operations with Headers](https://docs.spring.io/spring-data/rest/reference/etags-and-other-conditionals.html): `@Version`, `ETag`, `If-Match`, `If-None-Match`, ví dụ curl và hành vi 412/304. Tài liệu cũng ghi rõ ví dụ POJO ETag được lấy từ unit test.
- [Spring Data REST — Validation](https://docs.spring.io/spring-data/rest/reference/validation.html): đăng ký validator theo tên bean hoặc qua `RepositoryRestConfigurer`.
- [Spring Data REST API — RepositoryConstraintViolationException](https://docs.spring.io/spring-data/rest/docs/current/api/org/springframework/data/rest/core/RepositoryConstraintViolationException.html): exception do Spring `Validator` ném ra và quan hệ kế thừa từ `DataIntegrityViolationException`.
- [Spring Data REST API — RepositoryRestExceptionHandler](https://docs.spring.io/spring-data/rest/docs/current/api/org/springframework/data/rest/webmvc/RepositoryRestExceptionHandler.html): handler mặc định cho controller Spring Data REST.
- [Spring Data Commons API — CrudRepository](https://docs.spring.io/spring-data/commons/reference/api/java/org/springframework/data/repository/CrudRepository.html): hợp đồng của `save()`/`delete()` và `OptimisticLockingFailureException` khi version không khớp.
- [Spring Framework API — DataIntegrityViolationException](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/dao/DataIntegrityViolationException.html): ý nghĩa exception vi phạm integrity constraint.
- [Spring Framework API — OptimisticLockingFailureException](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/dao/OptimisticLockingFailureException.html): exception khi optimistic locking thất bại.

Khi áp dụng vào dự án, đối chiếu tài liệu với phiên bản Spring Data REST/Spring Data đang khai báo trong build và các `@ControllerAdvice` hiện có, vì chúng quyết định handler nào thực sự xử lý request.
