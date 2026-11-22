# Biểu diễn không tìm thấy dữ liệu và xung đột cập nhật

Trong ứng dụng Spring WebFlux dùng Spring Data R2DBC, một request đọc hoặc ghi dữ liệu có thể kết thúc theo nhiều cách: tìm thấy bản ghi, không có bản ghi phù hợp, dữ liệu không hợp lệ, vi phạm quy tắc nghiệp vụ hoặc cập nhật thất bại vì một request khác đã thay đổi dữ liệu trước đó.

Các trường hợp này cần được biểu diễn rõ trong reactive pipeline và chuyển thành HTTP status phù hợp. Mono.empty() thường biểu thị không có kết quả; nó không phải lỗi. Một xung đột cập nhật là một lỗi nghiệp vụ/kỹ thuật có ý nghĩa khác, thường được trả bằng HTTP 409 Conflict hoặc 412 Precondition Failed nếu request dùng điều kiện phiên bản như If-Match.

Với Spring Data R2DBC, optimistic locking bằng @Version giúp phát hiện một entity đã bị thay đổi kể từ lúc được đọc. Với câu SQL update trực tiếp, ứng dụng cần đưa version vào điều kiện WHERE, tăng version trong cùng câu lệnh và kiểm tra số hàng bị tác động. WebFlux sau đó chuyển các kết quả này thành response rõ ràng mà không gọi block() hoặc tự tạo subscription.

## 1. Phân biệt không tìm thấy dữ liệu, dữ liệu null và lỗi

Một API cần phân biệt ít nhất ba tình huống:

1. **Không có hàng phù hợp:** query không trả hàng nào. Repository thường biểu diễn trường hợp này bằng Mono.empty().
2. **Có hàng nhưng một cột là SQL NULL:** repository vẫn trả entity/DTO; property tương ứng có thể mang giá trị Java null nếu kiểu đích cho phép.
3. **Truy vấn thất bại:** publisher phát error, ví dụ lỗi kết nối, lỗi SQL, lỗi chuyển đổi hoặc lỗi constraint.

Ví dụ:

~~~java
Mono<Customer> findById(Long id);
~~~

- Nếu có customer, Mono phát một Customer rồi hoàn tất.
- Nếu không có customer, Mono hoàn tất rỗng.
- Nếu database gặp lỗi, Mono phát error.

Không nên chuyển mọi trường hợp thành null. Trong reactive API, Mono không phát một giá trị Java null. Mono.empty() là một tín hiệu hoàn tất không có phần tử; SQL NULL là dữ liệu của một hàng đã tồn tại.

### 1.1. Mono.empty() không phải exception

Một repository method trả Mono<Customer> không tìm thấy ID thường không phát exception. Vì vậy, đoạn code sau không xử lý trường hợp không có dữ liệu:

~~~java
return customerRepository.findById(id)
        .onErrorResume(error -> Mono.just(fallbackCustomer));
~~~

onErrorResume chỉ xử lý error signal. Nếu publisher hoàn tất rỗng, fallback không chạy.

Để xử lý absence, dùng switchIfEmpty:

~~~java
return customerRepository.findById(id)
        .switchIfEmpty(Mono.error(new CustomerNotFoundException(id)));
~~~

Hoặc biểu diễn absence trực tiếp ở tầng HTTP bằng defaultIfEmpty/switchIfEmpty, tùy hợp đồng của service.

### 1.2. Collection rỗng thường là kết quả thành công

Với Flux<Customer>, không có hàng phù hợp thường có nghĩa Flux hoàn tất mà không phát phần tử:

~~~java
Flux<Customer> customers = customerRepository.findAllByStatus("ARCHIVED");
~~~

Một API danh sách thường nên trả HTTP 200 OK với mảng rỗng [], vì truy vấn danh sách đã thành công nhưng không có phần tử. Không nên tự động trả 404 Not Found chỉ vì một Flux không phát phần tử.

Ngược lại, một endpoint đọc một resource cụ thể như GET /customers/{id} thường trả 404 nếu ID không tồn tại hoặc không thuộc phạm vi truy cập của caller.

## 2. Chuyển Mono.empty() thành HTTP 404 trong WebFlux

Với annotated controller, một cách rõ ràng là trả Mono<ResponseEntity<T>>. Khi repository có kết quả, trả 200 OK; khi publisher rỗng, trả 404 Not Found.

~~~java
@RestController
@RequestMapping("/customers")
public class CustomerController {

    private final CustomerRepository repository;

    public CustomerController(CustomerRepository repository) {
        this.repository = repository;
    }

    @GetMapping("/{id}")
    public Mono<ResponseEntity<CustomerResponse>> findById(
            @PathVariable Long id) {

        return repository.findById(id)
                .map(CustomerResponse::from)
                .map(ResponseEntity::ok)
                .defaultIfEmpty(ResponseEntity.notFound().build());
    }
}
~~~

defaultIfEmpty được thực thi khi publisher hoàn tất rỗng. Nếu repository phát error, error vẫn được chuyển tới error handling của WebFlux.

### 2.1. Dùng switchIfEmpty để phát một response khác

Có thể viết tương đương:

~~~java
@GetMapping("/{id}")
public Mono<ResponseEntity<CustomerResponse>> findById(
        @PathVariable Long id) {

    return customerService.findById(id)
            .map(CustomerResponse::from)
            .map(ResponseEntity::ok)
            .switchIfEmpty(Mono.just(ResponseEntity.notFound().build()));
}
~~~

defaultIfEmpty phù hợp khi giá trị fallback có sẵn. switchIfEmpty phù hợp khi cần chuyển sang một publisher khác, ví dụ ghi metric, gọi service fallback hoặc tạo response bất đồng bộ.

### 2.2. Để service phát Mono.empty() hay chuyển thành exception?

Cả hai cách đều có thể đúng, tùy ranh giới trách nhiệm:

- Nếu absence là kết quả bình thường của use case, service có thể giữ Mono.empty() và controller quyết định HTTP status.
- Nếu use case yêu cầu resource phải tồn tại, service có thể chuyển absence thành CustomerNotFoundException.

Ví dụ service giữ semantics absence:

~~~java
public Mono<Customer> findById(Long id) {
    return customerRepository.findById(id);
}
~~~

Controller ánh xạ sang 404:

~~~java
return customerService.findById(id)
        .map(ResponseEntity::ok)
        .defaultIfEmpty(ResponseEntity.notFound().build());
~~~

Ví dụ service coi thiếu resource là lỗi nghiệp vụ:

~~~java
public Mono<Customer> requireById(Long id) {
    return customerRepository.findById(id)
            .switchIfEmpty(Mono.error(new CustomerNotFoundException(id)));
}
~~~

Controller có thể trả Mono<CustomerResponse> và để @RestControllerAdvice ánh xạ exception thành 404.

Điều quan trọng là không để cùng một use case lúc trả empty, lúc ném exception tùy đường code mà không có hợp đồng rõ ràng.

## 3. Trả 404 bằng exception và @RestControllerAdvice

Nếu muốn tập trung việc ánh xạ lỗi, định nghĩa exception domain:

~~~java
public class CustomerNotFoundException extends RuntimeException {

    public CustomerNotFoundException(Long id) {
        super("Customer " + id + " was not found");
    }
}
~~~

Service:

~~~java
public Mono<Customer> requireById(Long id) {
    return customerRepository.findById(id)
            .switchIfEmpty(Mono.error(new CustomerNotFoundException(id)));
}
~~~

Controller:

~~~java
@GetMapping("/{id}")
public Mono<CustomerResponse> findById(@PathVariable Long id) {
    return customerService.requireById(id)
            .map(CustomerResponse::from);
}
~~~

Global exception handler:

~~~java
public record ApiError(String code, String message) {
}

@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(CustomerNotFoundException.class)
    public ResponseEntity<ApiError> handleNotFound(
            CustomerNotFoundException exception) {

        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .body(new ApiError("CUSTOMER_NOT_FOUND", exception.getMessage()));
    }
}
~~~

Cách này giúp nhiều controller dùng cùng một quy tắc. Không nên đưa stack trace, SQL, connection URL hoặc chi tiết nội bộ database vào response cho client.

### 3.1. Dùng ResponseStatusException khi phù hợp

Với một endpoint nhỏ, có thể dùng ResponseStatusException:

~~~java
return customerRepository.findById(id)
        .switchIfEmpty(Mono.error(
                new ResponseStatusException(
                        HttpStatus.NOT_FOUND,
                        "Customer not found")));
~~~

Với ứng dụng có nhiều use case, domain exception riêng thường dễ kiểm soát hơn vì domain không phải phụ thuộc trực tiếp vào HTTP. Controller advice chịu trách nhiệm chuyển domain/application error thành status.

### 3.2. Không làm rò sự tồn tại của dữ liệu tenant khác

Trong ứng dụng multi-tenant hoặc có dữ liệu nhạy cảm, khi ID không tồn tại trong tenant hiện tại, response thường nên là 404. Không nên trả thông tin rằng bản ghi có tồn tại nhưng thuộc tenant khác nếu điều đó làm lộ dữ liệu.

Repository query nên giới hạn ngay từ đầu:

~~~java
Mono<Customer> findByIdAndTenantId(Long id, Long tenantId);
~~~

Không tải bản ghi toàn cục rồi mới kiểm tra tenant ở controller.

## 4. Functional endpoints cũng cần biểu diễn absence rõ ràng

Với WebFlux functional routing, handler có thể chuyển Mono.empty() thành ServerResponse.notFound():

~~~java
public Mono<ServerResponse> getCustomer(ServerRequest request) {
    Long id = Long.valueOf(request.pathVariable("id"));

    return customerRepository.findById(id)
            .flatMap(customer -> ServerResponse.ok()
                    .contentType(MediaType.APPLICATION_JSON)
                    .bodyValue(CustomerResponse.from(customer)))
            .switchIfEmpty(ServerResponse.notFound().build());
}
~~~

Ở đây:

- Có customer: tạo response 200 OK với body.
- Không có customer: tạo response 404 Not Found.
- Repository error: error signal đi tới WebExceptionHandler hoặc cơ chế xử lý lỗi đã cấu hình.

Với endpoint danh sách:

~~~java
public Mono<ServerResponse> listCustomers(ServerRequest request) {
    return ServerResponse.ok()
            .contentType(MediaType.APPLICATION_JSON)
            .body(customerRepository.findAll(), Customer.class);
}
~~~

Nếu không có customer, body là một collection rỗng theo serialization của response; endpoint vẫn có thể trả 200.

## 5. HTTP status cho xung đột cập nhật

Không phải mọi lỗi ghi dữ liệu đều nên trả cùng một status. Một số status thường dùng:

| HTTP status | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| 400 Bad Request | Request sai định dạng hoặc validation không hợp lệ | Thiếu field bắt buộc, version không đúng kiểu |
| 404 Not Found | Resource không tồn tại trong phạm vi caller | ID không có trong tenant hiện tại |
| 409 Conflict | Request hợp lệ nhưng xung đột với trạng thái hiện tại | Optimistic locking thất bại, unique business constraint |
| 412 Precondition Failed | Điều kiện HTTP mà client gửi không còn đúng | If-Match chứa ETag cũ |
| 422 Unprocessable Content | Có thể dùng cho dữ liệu hợp lệ về cú pháp nhưng vi phạm quy tắc domain | Chuyển trạng thái không được phép, theo API convention |
| 500 Internal Server Error | Lỗi không dự kiến ở server | Bug hoặc lỗi không được phân loại |
| 503 Service Unavailable | Dịch vụ tạm thời không thể xử lý | Database/service phụ thuộc không khả dụng, theo chính sách vận hành |

Chọn status nhất quán trong toàn API. Đặc biệt, phân biệt conflict do trạng thái domain với precondition HTTP do client gửi.

### 5.1. 409 Conflict

409 Conflict phù hợp khi thao tác không thể hoàn thành vì trạng thái hiện tại của resource xung đột với yêu cầu. Ví dụ hai người cùng sửa một customer và một người đã lưu trước.

Response có thể chứa mã lỗi ổn định:

~~~json
{
  "code": "CUSTOMER_VERSION_CONFLICT",
  "message": "Customer was modified by another request",
  "resourceId": 42
}
~~~

Không nên trả toàn bộ entity hiện tại nếu caller không có quyền đọc các field đó. Có thể cung cấp version hiện tại hoặc yêu cầu client tải lại resource qua endpoint được bảo vệ.

### 5.2. 412 Precondition Failed

Nếu API dùng HTTP conditional request như If-Match, client yêu cầu server chỉ cập nhật khi resource vẫn có ETag mà client đã đọc. Nếu điều kiện không còn đúng, 412 Precondition Failed thể hiện precondition thất bại.

Ví dụ:

~~~http
PUT /customers/42
If-Match: "7"
Content-Type: application/json
~~~

Nếu version hiện tại đã là 8, server không thực hiện update với version 7 và trả 412. Optimistic locking ở database vẫn cần thiết để xử lý race xảy ra sau khi server kiểm tra header.

## 6. Phát hiện xung đột bằng @Version

Spring Data Relational hỗ trợ optimistic locking bằng @Version. Entity chứa một property version; khi entity được lưu, version được dùng để xác định phiên bản mà ứng dụng đã đọc.

Entity:

~~~java
@Table("customers")
public class Customer {

    @Id
    private Long id;

    @Version
    private Long version;

    private String name;
    private String status;

    // Constructor, getter và setter được lược bớt.
}
~~~

Schema:

~~~sql
CREATE TABLE customers (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    version BIGINT NOT NULL,
    name VARCHAR(160) NOT NULL,
    status VARCHAR(30) NOT NULL
);
~~~

Khi lưu entity mới, Spring Data khởi tạo version theo quy tắc của kiểu version. Khi update, framework dùng version hiện tại trong điều kiện ghi và tăng version khi thành công.

### 6.1. Kịch bản hai request cùng sửa một entity

Giả sử customer có version 4:

| Thứ tự | Request A | Request B |
| ---: | --- | --- |
| 1 | Đọc customer, version 4 | |
| 2 | | Đọc customer, version 4 |
| 3 | Sửa tên và save với version 4 | |
| 4 | Database cập nhật thành công, version thành 5 | |
| 5 | | Sửa status và save với version 4 |
| 6 | | Không có hàng khớp version 4; optimistic locking thất bại |

Request B không âm thầm ghi đè thay đổi của A. Spring Data phát sinh lỗi optimistic locking, thường thuộc OptimisticLockingFailureException.

### 6.2. Service cập nhật entity

~~~java
public Mono<Customer> rename(Long id, String newName) {
    return customerRepository.findById(id)
            .switchIfEmpty(Mono.error(new CustomerNotFoundException(id)))
            .flatMap(customer -> {
                customer.setName(newName);
                return customerRepository.save(customer);
            });
}
~~~

Nếu hai request cùng tải version cũ, chỉ một lần save có thể thành công. Lần còn lại phát lỗi optimistic locking. Cần để lỗi truyền xuống tầng xử lý HTTP hoặc chuyển thành exception nghiệp vụ phù hợp.

### 6.3. Không tự retry entity cũ

Khi optimistic locking thất bại, entity trong memory đã cũ. Gọi save() lại chính object đó với version cũ thường tiếp tục thất bại.

Muốn retry, phải:

1. Tải entity mới.
2. Kiểm tra lại điều kiện nghiệp vụ.
3. Áp dụng lại command nếu còn hợp lệ.
4. Lưu phiên bản mới.

Không phải mọi command đều có thể áp dụng lại tự động. Nếu user sửa cùng một field với một người khác, ứng dụng có thể cần trả conflict để người dùng xem và quyết định hợp nhất.

## 7. Chuyển optimistic locking failure thành HTTP 409

Có thể tập trung xử lý trong @RestControllerAdvice:

~~~java
@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(OptimisticLockingFailureException.class)
    public ResponseEntity<ApiError> handleOptimisticLocking(
            OptimisticLockingFailureException exception) {

        return ResponseEntity.status(HttpStatus.CONFLICT)
                .body(new ApiError(
                        "UPDATE_CONFLICT",
                        "The resource was modified by another request"));
    }
}
~~~

Thông báo trả về nên giải thích rằng client cần tải lại dữ liệu hoặc xử lý conflict. Không đưa SQL, tên bảng, version nội bộ hoặc stack trace vào response.

### 7.1. Phân biệt conflict với resource không tồn tại

Một update bằng @Version có thể thất bại vì entity đã bị thay đổi hoặc không còn tồn tại. Tùy đường thực thi và trạng thái dữ liệu, optimistic locking exception có thể đại diện cho nhiều nguyên nhân cạnh tranh.

Nếu API cần phân biệt chính xác 404 và 409, hãy xác định hợp đồng và cách truy vấn lại trong phạm vi tenant:

- Resource không tồn tại trong tenant hiện tại: 404.
- Resource vẫn tồn tại nhưng version đã thay đổi: 409.

Việc đọc lại sau khi update thất bại chỉ dùng để phân loại response; nó không làm cho update trước đó thành công. Cần tránh tiết lộ sự tồn tại của resource ở tenant khác.

### 7.2. Không bắt mọi lỗi thành 409

Chỉ map lỗi optimistic locking hoặc lỗi conflict đã xác định thành 409. Lỗi connection, timeout, SQL syntax hoặc database unavailable không phải optimistic conflict và cần được xử lý theo nhóm lỗi riêng.

## 8. Direct SQL cần kiểm tra version tường minh

Các câu lệnh @Modifying @Query, DatabaseClient hoặc R2dbcEntityTemplate.update(Query, Update) không tự áp dụng optimistic locking của entity như repository save. Nếu dùng direct update, hãy thêm version vào predicate và tăng version trong cùng statement.

~~~java
@Modifying
@Query("""
       UPDATE customers
       SET name = :name,
           version = version + 1,
           last_modified_at = :modifiedAt
       WHERE id = :id
         AND tenant_id = :tenantId
         AND version = :expectedVersion
       """)
Mono<Integer> updateIfVersionMatches(
        @Param("id") Long id,
        @Param("tenantId") Long tenantId,
        @Param("name") String name,
        @Param("expectedVersion") Long expectedVersion,
        @Param("modifiedAt") Instant modifiedAt);
~~~

Nếu câu lệnh cập nhật đúng một resource có khóa duy nhất:

- rowsUpdated == 1: cập nhật thành công.
- rowsUpdated == 0: không có hàng thỏa cả ID, tenant và version; có thể là resource không tồn tại hoặc version đã cũ.

Việc tăng version trong câu lệnh bảo đảm một update thành công làm phiên bản thay đổi, kể cả khi giá trị nghiệp vụ mới trùng với giá trị cũ.

### 8.1. Phân loại 404 và 409 sau conditional update

Service có thể đọc lại resource theo tenant khi update trả 0:

~~~java
public Mono<Customer> updateName(
        Long tenantId,
        Long id,
        Long expectedVersion,
        String newName) {

    return repository.updateIfVersionMatches(
                    id, tenantId, newName, expectedVersion, clock.instant())
            .flatMap(rows -> {
                if (rows == 1) {
                    return repository.findByIdAndTenantId(id, tenantId)
                            .switchIfEmpty(Mono.error(
                                    new CustomerNotFoundException(id)));
                }

                return repository.findByIdAndTenantId(id, tenantId)
                        .flatMap(current -> Mono.<Customer>error(
                                new CustomerConflictException(id)))
                        .switchIfEmpty(Mono.error(
                                new CustomerNotFoundException(id)));
            });
}
~~~

Đây là một cách phân loại ở mức ứng dụng. Trạng thái có thể thay đổi tiếp giữa câu update và lần đọc phân loại; response mô tả trạng thái quan sát được ở lần đọc sau. Nếu API không cần phân biệt, có thể trả một conflict chung hoặc một kết quả không tiết lộ resource.

### 8.2. Conditional update với R2dbcEntityTemplate

Có thể thêm version vào predicate và tăng version bằng SQL/template phù hợp:

~~~java
Query condition = query(
        where("id").is(id)
                .and("tenantId").is(tenantId)
                .and("version").is(expectedVersion));

Update update = Update.update("name", newName)
        .set("version", expectedVersion + 1)
        .set("lastModifiedAt", clock.instant());

return template.update(Customer.class)
        .matching(condition)
        .apply(update);
~~~

Ví dụ dùng giá trị version dự kiến đã được đọc từ request. Nếu cần tăng version dựa trên giá trị hiện tại một cách nguyên tử, native SQL version = version + 1 thường thể hiện trực tiếp hơn. Không được bỏ predicate version khi dùng template update rồi giả định @Version tự được áp dụng.

## 9. Dùng ETag và If-Match cho cập nhật có điều kiện

HTTP cung cấp conditional request để client tránh ghi đè dữ liệu đã thay đổi kể từ lần đọc.

### 9.1. Trả ETag khi đọc resource

Nếu version là số nguyên, có thể biểu diễn nó thành ETag:

~~~java
@GetMapping("/{id}")
public Mono<ResponseEntity<CustomerResponse>> getCustomer(
        @PathVariable Long id) {

    return customerService.requireById(id)
            .map(customer -> ResponseEntity.ok()
                    .eTag("\"" + customer.getVersion() + "\"")
                    .body(CustomerResponse.from(customer)));
}
~~~

Client nhận header:

~~~http
ETag: "4"
~~~

ETag phải phản ánh một phiên bản đại diện cho nội dung resource. Nếu response có các field phụ thuộc dữ liệu khác ngoài entity version, cần bảo đảm version được tăng khi những dữ liệu đó thay đổi hoặc tạo ETag tổng hợp phù hợp.

### 9.2. Nhận If-Match khi update

~~~java
@PutMapping("/{id}")
public Mono<ResponseEntity<CustomerResponse>> updateCustomer(
        @PathVariable Long id,
        @RequestHeader(HttpHeaders.IF_MATCH) String ifMatch,
        @RequestBody UpdateCustomerRequest request) {

    Long expectedVersion = etagParser.parseVersion(ifMatch);

    return customerService.updateIfVersionMatches(
                    id, expectedVersion, request)
            .map(updated -> ResponseEntity.ok()
                    .eTag("\"" + updated.getVersion() + "\"")
                    .body(CustomerResponse.from(updated)));
}
~~~

Nếu If-Match không khớp version hiện tại, service có thể ném PreconditionFailedException; exception handler chuyển thành 412.

### 9.3. Vì sao vẫn cần optimistic locking ở database?

Giả sử server đọc version 4 và so sánh với If-Match: "4". Ngay sau bước so sánh, một request khác cập nhật entity lên version 5. Nếu server sau đó update không có predicate version, nó vẫn có thể ghi đè dữ liệu mới.

Do đó, kiểm tra header chỉ là điều kiện HTTP ở tầng ứng dụng. Câu update cuối cùng vẫn cần WHERE version = :expectedVersion hoặc entity @Version để phát hiện race tại database.

### 9.4. Phân biệt 409 và 412

- Dùng 409 khi xung đột phát sinh từ trạng thái nghiệp vụ hoặc optimistic locking mà API không biểu diễn bằng HTTP precondition.
- Dùng 412 khi request có If-Match/precondition và điều kiện đó không còn đúng.
- Có thể yêu cầu client luôn gửi If-Match; nếu thiếu header, API có thể trả 428 Precondition Required theo hợp đồng.

## 10. Xử lý lỗi reactive bằng toán tử phù hợp

Các toán tử Reactor có vai trò khác nhau:

| Toán tử | Xử lý |
| --- | --- |
| switchIfEmpty | Chạy publisher thay thế khi nguồn hoàn tất rỗng |
| defaultIfEmpty | Phát giá trị mặc định khi nguồn hoàn tất rỗng |
| onErrorMap | Chuyển một exception thành exception khác |
| onErrorResume | Chuyển lỗi thành publisher thay thế |
| doOnError | Quan sát/log lỗi, không biến lỗi thành thành công |
| retryWhen | Subscribe lại publisher khi lỗi thỏa điều kiện retry |

### 10.1. Map exception ở service boundary

~~~java
public Mono<Customer> updateName(Long id, String name) {
    return customerRepository.findById(id)
            .switchIfEmpty(Mono.error(new CustomerNotFoundException(id)))
            .flatMap(customer -> {
                customer.setName(name);
                return customerRepository.save(customer);
            })
            .onErrorMap(
                    OptimisticLockingFailureException.class,
                    error -> new CustomerConflictException(id, error));
}
~~~

Sau khi chuyển exception kỹ thuật thành exception application/domain, @RestControllerAdvice có thể map CustomerConflictException thành 409.

### 10.2. Không dùng onErrorResume để biến mọi lỗi thành empty

Tránh:

~~~java
return customerRepository.findById(id)
        .onErrorResume(error -> Mono.empty());
~~~

Code này biến lỗi database thành kết quả “không tìm thấy”. Caller không thể phân biệt resource vắng mặt với database unavailable, SQL lỗi hoặc connection reset.

Hãy chỉ xử lý exception cụ thể:

~~~java
return customerRepository.findById(id)
        .onErrorMap(
                DataAccessResourceFailureException.class,
                error -> new CustomerStoreUnavailableException(error));
~~~

Không cần chuyển mọi exception nếu global handler đã có quy tắc phù hợp. Mục tiêu là giữ nguyên ý nghĩa của lỗi.

### 10.3. doOnError không xử lý lỗi

~~~java
return customerRepository.save(customer)
        .doOnError(error -> log.error("Customer update failed", error));
~~~

doOnError chỉ quan sát lỗi; error vẫn tiếp tục tới downstream. Nếu muốn chuyển thành conflict, dùng onErrorMap hoặc để exception handler xử lý.

### 10.4. Không tự subscribe trong controller/service

Tránh:

~~~java
customerRepository.save(customer).subscribe();
return Mono.just(ResponseEntity.ok().build());
~~~

Response có thể được gửi trước khi database hoàn tất. Caller không nhận được lỗi ghi và không thể biết update có thành công hay không.

Hãy trả publisher cho WebFlux:

~~~java
return customerRepository.save(customer)
        .map(ResponseEntity::ok);
~~~

WebFlux quản lý subscription và ghi response theo kết quả reactive.

## 11. Chuẩn hóa response lỗi

Một API có thể dùng cấu trúc lỗi thống nhất:

~~~java
public record ApiError(
        String code,
        String message,
        String resourceId
) {
}
~~~

Advice:

~~~java
@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(CustomerNotFoundException.class)
    public ResponseEntity<ApiError> notFound(
            CustomerNotFoundException exception) {
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .body(new ApiError(
                        "CUSTOMER_NOT_FOUND",
                        "Customer was not found",
                        exception.getResourceId()));
    }

    @ExceptionHandler(CustomerConflictException.class)
    public ResponseEntity<ApiError> conflict(
            CustomerConflictException exception) {
        return ResponseEntity.status(HttpStatus.CONFLICT)
                .body(new ApiError(
                        "CUSTOMER_UPDATE_CONFLICT",
                        "Customer changed before this update could be applied",
                        exception.getResourceId()));
    }

    @ExceptionHandler(PreconditionFailedException.class)
    public ResponseEntity<ApiError> preconditionFailed(
            PreconditionFailedException exception) {
        return ResponseEntity.status(HttpStatus.PRECONDITION_FAILED)
                .body(new ApiError(
                        "ETAG_MISMATCH",
                        "Reload the resource before updating it",
                        exception.getResourceId()));
    }
}
~~~

Các exception class và getter ở ví dụ cần được định nghĩa theo cấu trúc dự án. Có thể dùng ProblemDetail trong Spring Framework 6+ nếu ứng dụng chuẩn hóa response theo Problem Details.

### 11.1. Map lỗi duplicate key

Nếu unique constraint bị vi phạm, Spring có thể chuyển lỗi driver thành DuplicateKeyException. Đây có thể là conflict nghiệp vụ, ví dụ email đã được dùng.

~~~java
@ExceptionHandler(DuplicateKeyException.class)
public ResponseEntity<ApiError> duplicateKey(DuplicateKeyException exception) {
    return ResponseEntity.status(HttpStatus.CONFLICT)
            .body(new ApiError(
                    "DUPLICATE_RESOURCE",
                    "A resource with the same unique value already exists",
                    null));
}
~~~

Không nên map mọi DataIntegrityViolationException thành 409 mà không phân loại. Vi phạm foreign key, not-null, check constraint và lỗi dữ liệu khác có thể cần response khác tùy API contract. Không đưa thông tin constraint nội bộ hoặc giá trị nhạy cảm vào body.

## 12. Transaction và xung đột cập nhật

Một thao tác cập nhật có thể gồm đọc entity, kiểm tra quy tắc, ghi entity và ghi audit. Nếu các thao tác cần nguyên tử, đặt chúng trong reactive transaction:

~~~java
@Transactional
public Mono<Customer> changeStatus(Long id, String newStatus) {
    return customerRepository.findById(id)
            .switchIfEmpty(Mono.error(new CustomerNotFoundException(id)))
            .flatMap(customer -> {
                customer.changeStatus(newStatus);
                return customerRepository.save(customer);
            });
}
~~~

@Transactional bảo đảm các thao tác database tham gia cùng transaction khi chúng dùng đúng R2DBC transaction manager và ConnectionFactory. Nó không tự ngăn lost update nếu không có @Version, conditional update hoặc locking phù hợp.

### 12.1. Không retry mù sau conflict

Optimistic locking failure có nghĩa dữ liệu đã thay đổi so với phiên bản mà request đang dùng. Retry cùng entity cũ không giải quyết được xung đột.

Một API thường nên trả 409/412 để client:

1. Tải resource mới.
2. Hiển thị thay đổi hiện tại nếu cần.
3. Hợp nhất dữ liệu hoặc yêu cầu người dùng xác nhận.
4. Gửi update mới với version mới.

Chỉ tự động retry nếu command có thể được áp dụng lại một cách an toàn sau khi đọc phiên bản mới và quy tắc nghiệp vụ vẫn đúng.

### 12.2. Phân biệt lỗi conflict với lỗi không xác định sau commit

Optimistic locking failure là một conflict có thể nhận diện. Timeout hoặc connection reset trong lúc commit có thể có kết quả không xác định. Không map tất cả thành 409.

Với thao tác ghi có side effect, hãy dùng idempotency key để caller có thể gửi lại cùng ý định mà không tạo dữ liệu trùng. Nếu trạng thái commit không xác định, response có thể là lỗi tạm thời theo API contract; lần retry phải dùng cùng idempotency key.

## 13. Ví dụ end-to-end: GET và PUT với version

Response DTO:

~~~java
public record CustomerResponse(
        Long id,
        String name,
        String status,
        Long version
) {
    static CustomerResponse from(Customer customer) {
        return new CustomerResponse(
                customer.getId(),
                customer.getName(),
                customer.getStatus(),
                customer.getVersion());
    }
}
~~~

Controller:

~~~java
@RestController
@RequestMapping("/customers")
public class CustomerController {

    private final CustomerService service;

    public CustomerController(CustomerService service) {
        this.service = service;
    }

    @GetMapping("/{id}")
    public Mono<ResponseEntity<CustomerResponse>> get(@PathVariable Long id) {
        return service.findById(id)
                .map(customer -> ResponseEntity.ok()
                        .eTag("\"" + customer.getVersion() + "\"")
                        .body(CustomerResponse.from(customer)))
                .defaultIfEmpty(ResponseEntity.notFound().build());
    }

    @PutMapping("/{id}")
    public Mono<ResponseEntity<CustomerResponse>> update(
            @PathVariable Long id,
            @RequestBody UpdateCustomerRequest request) {

        return service.update(id, request)
                .map(customer -> ResponseEntity.ok()
                        .eTag("\"" + customer.getVersion() + "\"")
                        .body(CustomerResponse.from(customer)));
    }
}
~~~

Service:

~~~java
@Service
public class CustomerService {

    private final CustomerRepository repository;

    public CustomerService(CustomerRepository repository) {
        this.repository = repository;
    }

    public Mono<Customer> findById(Long id) {
        return repository.findById(id);
    }

    @Transactional
    public Mono<Customer> update(Long id, UpdateCustomerRequest request) {
        return repository.findById(id)
                .switchIfEmpty(Mono.error(new CustomerNotFoundException(id)))
                .flatMap(customer -> {
                    customer.setName(request.name());
                    customer.setStatus(request.status());
                    return repository.save(customer);
                })
                .onErrorMap(
                        OptimisticLockingFailureException.class,
                        error -> new CustomerConflictException(id, error));
    }
}
~~~

Ví dụ trên minh họa optimistic locking qua @Version. Nếu endpoint yêu cầu If-Match, hãy parse ETag và so sánh/đưa expected version vào thao tác update; chỉ trả ETag ở GET mà không kiểm tra ở PUT thì chưa tạo conditional update.

## 14. Kiểm thử absence và conflict

Nên kết hợp unit test cho service với integration test dùng database R2DBC thật hoặc Testcontainers. Unit test xác nhận logic chuyển publisher; integration test xác nhận mapping, optimistic locking và exception thực tế từ database.

### 14.1. Service trả empty khi không tìm thấy

~~~java
StepVerifier.create(customerService.findById(999L))
        .verifyComplete();
~~~

Test này xác nhận service giữ semantics empty. Nếu service dùng requireById, hãy xác nhận exception:

~~~java
StepVerifier.create(customerService.requireById(999L))
        .expectError(CustomerNotFoundException.class)
        .verify();
~~~

### 14.2. Controller trả 404

Với WebTestClient:

~~~java
webTestClient.get()
        .uri("/customers/999")
        .exchange()
        .expectStatus().isNotFound();
~~~

Kiểm tra thêm body lỗi nếu API dùng @RestControllerAdvice.

### 14.3. Danh sách rỗng trả 200

~~~java
webTestClient.get()
        .uri("/customers?status=UNKNOWN")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .json("[]");
~~~

Điều này phân biệt một collection không có phần tử với một resource cụ thể không tồn tại.

### 14.4. Optimistic locking với hai entity cùng version

Test integration:

1. Tạo một customer.
2. Đọc entity hai lần để có hai object cùng version.
3. Thay đổi và save object thứ nhất; xác nhận thành công.
4. Thay đổi và save object thứ hai; xác nhận optimistic locking failure.
5. Đọc lại database và xác nhận chỉ thay đổi của lần save đầu được lưu.

~~~java
Mono<Void> testConflict(Long id) {
    return customerRepository.findById(id)
            .zipWith(customerRepository.findById(id))
            .flatMap(tuple -> {
                Customer first = tuple.getT1();
                Customer stale = tuple.getT2();

                first.setName("First update");
                stale.setName("Stale update");

                return customerRepository.save(first)
                        .then(customerRepository.save(stale))
                        .then();
            });
}
~~~

Test thực tế cần assert rằng publisher kết thúc bằng optimistic locking exception. Ví dụ trên cho thấy cách tạo hai snapshot entity; không gọi hai save() song song nếu mục tiêu là kiểm soát rõ thứ tự thắng/thua.

### 14.5. Test conditional SQL update

Chuẩn bị version 3:

- Update với expectedVersion 3 phải tác động một hàng và version thành 4.
- Update tiếp với expectedVersion 3 phải tác động 0 hàng.
- Update với ID thuộc tenant khác không được thay đổi hàng.
- Kiểm tra status và audit columns sau mỗi lần thử.

### 14.6. Test HTTP conflict

Dùng hai request đọc cùng ETag, sau đó gửi hai PUT:

1. Cả hai đọc version 4.
2. Request A cập nhật với version 4 và thành công, trả ETag version 5.
3. Request B gửi version 4 và nhận 409 hoặc 412 theo hợp đồng API.
4. Database vẫn giữ thay đổi của A.

## 15. Những lỗi thường gặp khi biểu diễn absence và conflict

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| GET không có dữ liệu nhưng trả 200 body rỗng | Controller không chuyển Mono.empty() thành 404 | Dùng Mono<ResponseEntity<T>> và defaultIfEmpty |
| Database lỗi nhưng API trả 404 | Dùng onErrorResume(error -> Mono.empty()) | Chỉ map lỗi cụ thể; giữ nguyên lỗi hạ tầng |
| Danh sách rỗng trả 404 | Nhầm empty Flux với resource đơn không tồn tại | Trả 200 với collection rỗng |
| Update bị ghi đè âm thầm | Entity không có @Version hoặc SQL thiếu version predicate | Optimistic locking hoặc conditional update |
| Conflict bị trả thành 500 | Chưa map optimistic locking exception | Dùng @RestControllerAdvice trả 409/412 |
| Mọi lỗi database đều thành 409 | Exception handler quá rộng | Chỉ map lỗi conflict đã xác định |
| Retry save liên tục vẫn thất bại | Retry cùng entity/version cũ | Tải entity mới và đánh giá lại command |
| Direct SQL bỏ qua version | Nghĩ @Version áp dụng cho mọi câu DML | Thêm expected version vào WHERE và tăng version |
| 404 làm lộ dữ liệu tenant khác | Query toàn cục rồi kiểm tra tenant sau | Query theo ID và tenant ngay từ repository |
| If-Match được kiểm tra nhưng vẫn mất update | Chỉ so sánh header trước khi ghi, không có predicate version ở DB | Dùng @Version hoặc conditional SQL |
| Timeout bị xem là conflict | Nhầm ambiguous commit với optimistic locking | Phân loại lỗi; dùng idempotency cho write có kết quả không xác định |
| Controller trả response trước khi ghi xong | Gọi subscribe() độc lập | Trả publisher để WebFlux quản lý subscription |

## 16. Quy trình thiết kế API đọc và cập nhật an toàn

1. Xác định endpoint trả một resource hay một collection.
2. Với resource đơn, quyết định absence là empty result hay domain exception.
3. Ánh xạ absence thành HTTP 404; collection rỗng thường là 200 với danh sách rỗng.
4. Phân biệt SQL NULL trong một hàng với Mono.empty().
5. Chọn cơ chế phát hiện concurrent update: @Version, conditional SQL hoặc lock phù hợp.
6. Quy định xung đột là 409 hay 412 nếu dùng HTTP precondition.
7. Với direct DML, thêm tenant predicate và version predicate vào câu lệnh.
8. Map exception cụ thể qua @RestControllerAdvice.
9. Không nuốt lỗi database hoặc retry mù entity cũ.
10. Kiểm thử bằng WebTestClient, StepVerifier và hai snapshot/transaction độc lập.

## 17. Sơ đồ luồng xử lý

~~~mermaid
flowchart TD
    A[HTTP request] --> B[Reactive service / repository]
    B --> C{Publisher kết thúc thế nào?}
    C -->|Có entity| D[Trả resource]
    C -->|Mono.empty| E[404 cho resource đơn]
    C -->|Collection rỗng| F[200 với []]
    C -->|Validation/domain error| G[Map status theo lỗi]
    C -->|Optimistic locking failure| H[409 Conflict]
    C -->|If-Match không còn đúng| I[412 Precondition Failed]
    C -->|Lỗi hạ tầng| J[500/503 theo chính sách]
    D --> K[WebFlux ghi response]
    E --> K
    F --> K
    G --> K
    H --> K
    I --> K
    J --> K
~~~

## 18. Kết luận

Trong Spring Data R2DBC và WebFlux, Mono.empty() là kết quả không có phần tử, không phải lỗi database. Với endpoint resource đơn, hãy chuyển empty thành 404; với endpoint collection, danh sách rỗng thường vẫn là 200. SQL NULL là một giá trị của hàng đã tồn tại và cần được xử lý riêng.

Đối với cập nhật đồng thời, dùng @Version để Spring Data phát hiện entity đã cũ, hoặc đưa expected version vào predicate của câu SQL trực tiếp và tăng version trong cùng statement. Map optimistic locking conflict thành 409; nếu request dùng If-Match và ETag không còn đúng, 412 thường thể hiện rõ hơn. Kiểm tra header ở tầng HTTP không thay thế version predicate tại database vì race vẫn có thể xảy ra giữa kiểm tra và ghi.

Cuối cùng, giữ nguyên error signal có ý nghĩa, dùng switchIfEmpty cho absence, @RestControllerAdvice cho ánh xạ lỗi tập trung và để WebFlux quản lý subscription. Kiểm thử cả response HTTP lẫn hành vi concurrency ở database để bảo đảm một request không âm thầm ghi đè thay đổi của request khác.
