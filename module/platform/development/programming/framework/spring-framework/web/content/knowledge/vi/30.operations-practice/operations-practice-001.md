# Thiết kế lớp HTTP mỏng, ranh giới dịch vụ và hợp đồng dữ liệu rõ ràng

## 1. Vì sao thiết kế ranh giới HTTP là một vấn đề vận hành?

Trong ứng dụng Spring Framework, `@RestController` là nơi HTTP request đi vào hệ thống. Viết mọi logic ngay tại controller ban đầu có thể nhanh, nhưng lâu dài dễ gây các vấn đề: endpoint chứa SQL hoặc JPA repository calls, xử lý transaction lẫn với JSON mapping, ngoại lệ nghiệp vụ bị trả thành HTTP 500, thay tên cột database làm thay đổi response JSON, và test nghiệp vụ buộc phải khởi động web server.

Thiết kế **lớp HTTP mỏng** có nghĩa controller chỉ làm những việc thuộc giao thức HTTP:

1. Nhận và diễn giải input từ path, query, headers hoặc JSON body.
2. Thực hiện kiểm tra hình dạng dữ liệu tại ranh giới (ví dụ Bean Validation).
3. Chuyển request DTO thành input của một ca sử dụng/service.
4. Gọi service và chuyển kết quả thành response DTO.
5. Chọn HTTP status, response headers và hợp đồng lỗi ổn định.

**Service boundary** giữ hành vi nghiệp vụ độc lập với HTTP: kiểm tra bất biến nghiệp vụ, điều phối repository/domain, phân định transaction, phát sự kiện theo thiết kế. **Data contract** là sự thỏa thuận rõ ràng về request, response, kiểu dữ liệu, optional fields, quy tắc lỗi, versioning, status codes và ngữ nghĩa; contract có thể tồn tại lâu hơn một bảng database hay một class domain.

Đây không phải lời kêu gọi tạo thật nhiều lớp. Với endpoint rất đơn giản, service có thể nhỏ. Mục tiêu là trách nhiệm có chỗ đứng rõ ràng, các thay đổi có phạm vi ảnh hưởng dự đoán được, và test đúng lớp.

Phạm vi: HTTP APIs trong **Spring MVC**, Java 17+ / Spring Boot 3.3.x / Spring Framework 6.1.x, kèm phân biệt khi dùng WebFlux. Bài tập runnable minh họa API đăng ký và tra cứu sách, với in-memory repository để tập trung vào kiến trúc mà không cần database.

## 2. Tách transport, application, domain và persistence

Một luồng HTTP điển hình:

```text
HTTP client
    │ POST /api/books + JSON
    ▼
[HTTP adapter / @RestController]
  - parse/validate request DTO
  - map DTO → command
  - call application service
  - map result → response DTO + HTTP 201
    │
    ▼
[Application service / use case]
  - áp dụng quy tắc nghiệp vụ
  - chọn transaction boundary nếu cần
  - gọi repository port
    │
    ▼
[Repository abstraction] ← port (hợp đồng truy cập dữ liệu)
    │
    ▼
[Persistence adapter]
  - JPA/JDBC/Mongo/in-memory
    │
    ▼
Database hoặc storage
```

| Lớp/trách nhiệm | Biết điều gì? | Tránh điều gì? |
| --- | --- | --- |
| **Controller / HTTP adapter** | URL, HTTP verb, status, headers, JSON DTO, `@Valid` | SQL, entity manager, chính sách giao dịch, thuật toán nghiệp vụ dài |
| **Application service** | Ca sử dụng, input command, quyền nghiệp vụ, transaction và orchestration | `ResponseEntity`, `HttpServletRequest`, `@RequestBody`, status 404/409 |
| **Domain** | Entity/value object, bất biến, quy tắc nghiệp vụ | Jackson annotations, HTTP query param, tên cột database |
| **Repository port** | Những thao tác storage mà use case cần | Thông tin transport HTTP |
| **Repository adapter** | JDBC/JPA/SQL/index/cache/storage cụ thể | HTTP serialization, response status |
| **Exception translation / advice** | Đổi exception thành response lỗi công khai | Che giấu bug thành 200, tiết lộ stack trace |

Chiều phụ thuộc hợp lý là: controller phụ thuộc service; service phụ thuộc domain và repository interface; implementation storage thực thi interface đó. Có thể dùng dependency injection của Spring bằng constructor. Không cần triển khai Clean Architecture đầy đủ với hàng chục module Java cho mỗi CRUD; tách ít nhất ranh giới HTTP và nghiệp vụ là bước có giá trị lớn.

### Ví dụ dấu hiệu controller đang quá dày

```java
// Ví dụ PHẢN MẪU, không có các class đi kèm để chạy độc lập.
@PostMapping("/orders")
public ResponseEntity<?> place(@RequestBody OrderEntity order) {
    order.setStatus("NEW");
    repository.save(order);
    paymentClient.charge(order.getAmount());
    emailSender.send(order.getCustomerEmail());
    return ResponseEntity.ok(order);
}
```

Đoạn này vừa nhận persistence entity qua HTTP, vừa điều phối thanh toán/email, vừa ghi dữ liệu và chọn response. Các lỗi có thể tạo trạng thái nửa thành công: ghi order trước rồi charge thất bại; retry POST có thể nhân đôi thanh toán. Khó đảm bảo transaction và idempotency.

Thiết kế lại: HTTP adapter nhận `PlaceOrderRequest` (contract), gọi `OrderApplicationService.place(command)`, service đặt quy tắc/transaction/outbox và trả một kết quả `PlacedOrder`; controller ánh xạ thành `201 Created` và DTO. Với thanh toán bên ngoài, giao dịch database không thể rollback được HTTP charge đã thành công: cần idempotency key, saga/compensation hoặc event-driven workflow thích hợp.

## 3. Định nghĩa HTTP contract trước khi viết controller

Bắt đầu từ hợp đồng API ở góc nhìn consumer. Ví dụ “tạo sách” và “xem một sách”:

| Operation | Request | Thành công | Lỗi điển hình |
| --- | --- | --- | --- |
| Tạo sách | `POST /api/books`, JSON `{"title":"Spring","isbn":"9780000000001"}` | `201 Created`, `Location: /api/books/1`, response JSON có id/title/isbn | `400` nếu JSON/field không hợp lệ; `409` nếu ISBN đã tồn tại |
| Tra cứu | `GET /api/books/{id}` | `200 OK`, response JSON | `400` nếu id không hợp lệ; `404` nếu không tìm thấy |

Một request DTO khác response DTO:

```java
// Java 17+ records, fragment; file runnable đầy đủ ở mục 8.
public record CreateBookRequest(
        @NotBlank String title,
        @NotBlank String isbn) {}

public record BookResponse(
        long id,
        String title,
        String isbn) {}
```

Dấu `@NotBlank` thuộc Bean Validation (import `jakarta.validation.constraints.NotBlank`). Nó kiểm tra đầu vào tại HTTP boundary; service vẫn nên bảo vệ các quy tắc cốt lõi vì use case có thể được gọi từ scheduler, message listener, batch job hoặc test mà không đi qua controller.

### Contract không phải database schema

Giả sử persistence entity có thêm `costPrice`, `supplierId`, `internalNotes`, `rowVersion`. API public không nên tự trả tất cả fields đó chỉ vì entity có getter. Việc serialize trực tiếp `@Entity` có thể làm rò dữ liệu, gây vòng tham chiếu JSON ở quan hệ JPA và khiến lazy-loading chạy khi viết response. DTO là một **phép chiếu có chủ ý**.

Đặt tên JSON, kiểu và semantics ổn định. `id` là định danh tài nguyên, `title` là tên sách, `isbn` là định danh sách được dùng để kiểm tra trùng theo chính sách demo. Nếu ISBN bắt buộc có định dạng chuẩn trong production, thêm validation nghiệp vụ tương ứng thay vì dựa duy nhất vào `@NotBlank`.

### Những quyết định contract cần viết rõ

- Field nào bắt buộc và field nào optional? Phân biệt field **thiếu**, giá trị `null`, chuỗi trống và giá trị mặc định.
- POST trả `201 Created` hay `202 Accepted`? Nếu tạo đồng bộ thì 201; nếu chỉ nhận việc vào queue để xử lý sau, 202 có thể đúng hơn.
- Sau POST, `Location` trỏ tới resource nào? Đường dẫn công khai cần nhất quán với GET.
- Trường thời gian dùng ISO 8601/UTC hay có timezone nào? Số tiền dùng kiểu biểu diễn gì (tránh `double` tùy tiện)?
- Pagination/filter/sort dùng query params nào? Có giới hạn số kết quả, chiều dài chuỗi, size payload không?
- Hợp đồng lỗi gồm `status`, `detail`, `type` và correlation ID thế nào? Có tiết lộ dữ liệu nội bộ không?
- Có cần idempotency key cho POST chịu retry, ETag/`If-Match` cho update đồng thời và versioning khi đổi contract không?

Đặt các quyết định trên trong API docs/OpenAPI + contract tests. Không trộn sự phụ thuộc vào property naming ngẫu nhiên của Jackson với quyết định nghiệp vụ.

## 4. Controller mỏng: một HTTP operation được viết ra sao?

Một controller đúng nhiệm vụ có thể chỉ có vài dòng:

```java
@RestController
@RequestMapping(path = "/api/books", produces = MediaType.APPLICATION_JSON_VALUE)
class BookController {
    private final BookService service;

    BookController(BookService service) {
        this.service = service;
    }

    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
    ResponseEntity<BookResponse> create(
            @Valid @RequestBody CreateBookRequest request) {
        Book created = service.create(request.title(), request.isbn());
        BookResponse response = toResponse(created);
        return ResponseEntity
                .created(URI.create("/api/books/" + created.id()))
                .body(response);
    }

    @GetMapping("/{id}")
    BookResponse get(@PathVariable long id) {
        return toResponse(service.find(id));
    }

    private static BookResponse toResponse(Book book) {
        return new BookResponse(book.id(), book.title(), book.isbn());
    }
}
```

Đây là **fragment**; Java imports và các class đi kèm có ở mục 8. Điểm cần quan sát:

- `@RestController` tương đương controller có body serialization, sử dụng Spring MVC `HttpMessageConverter` để đọc/ghi JSON.
- `@RequestMapping` định nghĩa path và `produces`; `@PostMapping(consumes=...)` định nghĩa content type request phù hợp. Spring có thể trả `415` khi Content-Type không được hỗ trợ và `406` khi response không thỏa Accept header.
- `@Valid @RequestBody` kiểm tra DTO nếu dự án có Jakarta Bean Validation provider. JSON lỗi, type mismatch và Bean Validation có thể tạo các exception khác nhau.
- Controller xây dựng `Location` và `201 Created` vì đây là quyết định **HTTP**, không phải domain rule.
- `toResponse` đưa domain object sang DTO có kiểm soát; có thể chuyển mapper sang class riêng khi phức tạp hoặc tái sử dụng.
- Service chỉ biết hai giá trị nghiệp vụ và trả `Book`, **không nhận `HttpServletRequest` và không trả `ResponseEntity`**.

Với response kiểu `BookResponse`, Spring mặc định trả 200 khi thành công. Nếu cần kiểm soát header hoặc status, trả `ResponseEntity<BookResponse>`. Đừng bắt mọi handler luôn trả `ResponseEntity<?>` nếu kiểu trả về cố định đã diễn đạt contract tốt.

### Quy tắc thực dụng để đánh giá “mỏng”

Một controller method thường dễ đọc như một pipeline: `bind → validate → map → call → map → respond`. Nó không có một vòng lặp xử lý business dài, không trực tiếp gọi repository/persistence API và không quyết định business transaction. Số dòng không phải metric duy nhất: controller 40 dòng toàn ánh xạ DTO vẫn có thể hợp lý, còn controller 5 dòng chứa một lệnh SQL hoặc business operation không idempotent vẫn sai chỗ.

## 5. Service boundary: nghiệp vụ, transaction và orchestration

Dịch vụ ứng dụng là nơi diễn tả **ca sử dụng**. Với ví dụ sách, quy tắc quan trọng là:

- Tiêu đề và ISBN sau chuẩn hóa cơ bản không được để trống, ngay cả khi gọi service không qua HTTP.
- Không đăng ký hai sách có cùng ISBN theo tiêu chí của ví dụ.
- ID được cấp ở storage boundary, và tra cứu ID không hợp lệ phải thất bại có chủ đích.
- Repository là dependency thông qua interface, nên service được unit test mà không cần web server hoặc database.

```java
@Service
class BookService {
    private final BookRepository repository;

    BookService(BookRepository repository) {
        this.repository = repository;
    }

    Book create(String title, String isbn) {
        String normalizedTitle = normalize(title, "title");
        String normalizedIsbn = normalize(isbn, "isbn");
        return repository.saveUnique(normalizedTitle, normalizedIsbn);
    }

    Book find(long id) {
        if (id <= 0) {
            throw new InvalidBookInputException("id must be positive");
        }
        return repository.find(id)
                .orElseThrow(() -> new BookNotFoundException(id));
    }

    private static String normalize(String value, String field) {
        if (value == null || value.isBlank()) {
            throw new InvalidBookInputException(field + " must not be blank");
        }
        return value.strip();
    }
}
```

Đây là fragment trích từ ví dụ hoàn chỉnh, dùng `@Service`, interface `BookRepository` và domain record `Book`. Service không import `org.springframework.http.*`, không định nghĩa HTTP 404/409; nó ném ngoại lệ nghiệp vụ (ví dụ `BookNotFoundException`), tầng HTTP advice sẽ dịch lỗi.

### Vì sao service phải kiểm tra bất biến dù DTO đã có @NotBlank?

Bean Validation tại controller xử lý tính hợp lệ của **incoming HTTP body**, giúp trả 400 sớm. Nhưng service có thể bị gọi từ scheduled task hoặc consumer khác. Để bất biến quan trọng không bị vượt qua, đặt chúng ở service/domain và/hoặc constraint database.

Tính duy nhất của ISBN là quy tắc có cạnh tranh đồng thời. Mẫu code `if (!exists) save()` ở hai thread có race condition: cả hai đều thấy chưa tồn tại. Trong production, **unique index/constraint ở database** mới là một lớp bảo vệ quan trọng; service/adapter phải map duplicate-key violation sang lỗi nghiệp vụ. Ví dụ in-memory ở mục 8 dùng `synchronized` để minh họa thao tác atomic trong một JVM, **không phải** giải pháp lock phân tán nhiều node.

### Transaction boundary nằm đâu?

Thường đặt `@Transactional` vào service method thực hiện một ca sử dụng thay đổi dữ liệu:

```java
@Service
class OrderService {
    @Transactional
    public OrderResult place(PlaceOrderCommand command) {
        // Load aggregate, kiểm tra rule, thay đổi nhiều bảng,
        // ghi outbox event trong cùng transaction nếu cần.
        return ...; // fragment ý tưởng, không compile độc lập
    }
}
```

Dòng `return ...;` là ký hiệu mô tả, **không phải Java runnable**. Với database JPA/JDBC, cần transaction manager phù hợp. Trong Spring proxy mode, `@Transactional` thường được áp dụng khi gọi qua Spring proxy; tự gọi `this.otherTransactionalMethod()` trong cùng object không tạo proxy interception. Transaction chỉ bao phủ resource đã tham gia vào transaction; không biến HTTP gọi payment service thành hoạt động có thể rollback tự động.

Đừng đặt `@Transactional` vào mọi controller để “đảm bảo an toàn”. Điều đó trộn persistence policy vào transport và có thể giữ transaction mở trong lúc serialize response hoặc gọi mạng chậm. Dành transaction cho ranh giới nghiệp vụ cần nhất quán.

## 6. Repository port và persistence adapter

Một repository interface mô tả **những thao tác mà service cần**, thay vì phơi bày toàn bộ mọi query/trình quản lý dữ liệu:

```java
interface BookRepository {
    Book saveUnique(String title, String isbn);
    Optional<Book> find(long id);
}
```

Trong ví dụ runnable, một adapter in-memory thực hiện interface này. Nếu đổi sang JPA, bạn có thể có Spring Data repository cho `BookEntity`, còn adapter `JpaBookRepositoryAdapter` chuyển entity ↔ domain `Book` và thực hiện `BookRepository`.

Sơ đồ phụ thuộc:

```text
BookController ──► BookService ──► BookRepository (interface)
                                          ▲
                                          │ implements
                                  JpaBookRepositoryAdapter
                                          │
                                          ▼
                                Spring Data/JPA/Database
```

Lợi ích là service dễ unit test bằng in-memory/fake implementation và không bị chi phối bởi JPA lazy proxies. **Không nhất thiết phải tạo repository port riêng trong mọi ứng dụng nhỏ**; nếu việc dùng trực tiếp `JpaRepository` trong service đã ổn định, có thể chấp nhận. Khi cần tách persistence model, testing độc lập hoặc nhiều data sources, port/adapter tạo ranh giới hữu ích.

### Những quy tắc không nên đánh đổi

- Không trả JPA `Page<Entity>` trực tiếp chỉ vì tiện: cần quyết định DTO fields, pagination metadata và contract public.
- Đừng để controller cài điều kiện business bằng các chuỗi `if` rải rác; tập trung vào service/domain.
- Không dùng lazy-loading bên ngoài transaction một cách tình cờ khi Jackson serialize entity.
- Khi API nhận các ID liên quan tài nguyên của user khác, service/security phải enforce authorization theo resource, tránh insecure direct object reference (IDOR).
- Kiểu lỗi storage cụ thể như `DataIntegrityViolationException` nên được dịch ở boundary phù hợp thành domain conflict khi đã hiểu nguyên nhân, không tùy tiện chuyển mọi lỗi database thành 409.

## 7. Validation, error contract và HTTP status phải nhất quán

### 7.1 Phân biệt validation shape và business validation

| Loại vấn đề | Nơi phát hiện lý tưởng | HTTP mapping gợi ý |
| --- | --- | --- |
| JSON bị sai syntax hoặc type | Spring `HttpMessageConverter` | `400 Bad Request` |
| Bắt buộc field title/isbn | `@Valid` / Bean Validation | `400 Bad Request` |
| ID path không chuyển được sang `long` | Spring MVC argument binding | `400 Bad Request` |
| ID đã parse nhưng không hợp lệ (<=0) | Service/domain | `400 Bad Request` |
| Không có resource tương ứng | Service/domain | `404 Not Found` |
| ISBN đã tồn tại | Service/repository uniqueness | `409 Conflict` |
| User chưa đăng nhập / không được phép | Security layer | `401 Unauthorized` / `403 Forbidden` |
| Request quá lớn / quá tải | Web/server/gateway policy | `413` hoặc `429` khi phù hợp |
| Lỗi chương trình/hạ tầng không lường trước | Exception monitoring | `500` hoặc `503` theo tình huống; không lộ stack trace |

Những status trên là **mapping policy**, không phải annotation tự suy luận toàn bộ. Spring MVC có hành vi mặc định cho nhiều lỗi binding/validation, nhưng ứng dụng cần định nghĩa payload lỗi thống nhất.

### 7.2 Dùng ProblemDetail để báo lỗi công khai

Spring Framework 6 hỗ trợ `ProblemDetail` theo chuẩn problem details; trong Spring 6.1 tài liệu liên quan RFC 7807, các bản cập nhật tham chiếu RFC 9457. Ví dụ:

```java
@RestControllerAdvice
class ApiErrorHandler {

    @ExceptionHandler(BookNotFoundException.class)
    ProblemDetail notFound(BookNotFoundException ex) {
        return ProblemDetail.forStatusAndDetail(
                HttpStatus.NOT_FOUND, ex.getMessage());
    }

    @ExceptionHandler(DuplicateIsbnException.class)
    ProblemDetail duplicate(DuplicateIsbnException ex) {
        return ProblemDetail.forStatusAndDetail(
                HttpStatus.CONFLICT, ex.getMessage());
    }

    @ExceptionHandler(InvalidBookInputException.class)
    ProblemDetail invalid(InvalidBookInputException ex) {
        return ProblemDetail.forStatusAndDetail(
                HttpStatus.BAD_REQUEST, ex.getMessage());
    }
}
```

Ví dụ hoàn chỉnh còn xử lý `MethodArgumentNotValidException` cho `@Valid`. Spring hỗ trợ content type `application/problem+json` khi serialize ProblemDetail. Các trường thường thấy gồm `type`, `title`, `status`, `detail`, `instance`; bạn có thể thêm extension properties đã kiểm soát như `errorCode`, `traceId` và danh sách `violations`.

**Không phản ánh trực tiếp exception message nội bộ ra công khai**: SQL table names, stack traces, bearer token, raw user input nhạy cảm, internal hostnames hoặc vendor errors có thể gây rò thông tin. Ví dụ hiển thị `BookNotFoundException` chứa ID đơn giản không nhạy cảm; production nên dùng error codes và messages đã được chuẩn hóa.

### 7.3 Lỗi nghiệp vụ khác lỗi lập trình

Một `BookNotFoundException` dự kiến khi GET ID không có dữ liệu là business outcome, phù hợp 404. `NullPointerException` trong service không được “cứu” bằng `@ExceptionHandler(Exception.class)` rồi trả 200 hoặc 400. Ghi log correlation ID, trả response 500 an toàn và sửa bug. Nếu external dependency không sẵn sàng, có thể trả 503 theo hợp đồng, nhưng thiết kế retry/backoff và circuit breaker độc lập.

Đối với update, kết hợp `ETag` và `If-Match` hoặc version field giúp phát hiện lost update (thường trả 412 Precondition Failed theo HTTP semantics khi precondition không đạt). Không mặc định mọi `PUT` sẽ idempotent nếu business logic ghi thêm bản ghi phụ hoặc phát event không kiểm soát.

## 8. Ví dụ hoàn chỉnh: API Spring Boot Java 17+

Ví dụ API sách dưới đây chạy **không cần database**: lưu trong một in-memory repository, dùng Spring MVC và Jakarta Validation. Nó minh họa HTTP adapter, service boundary, repository port, DTOs, duplicate detection và error contract. Cơ chế in-memory không lưu dữ liệu sau restart và không dùng cho multi-instance.

### 8.1 Cấu trúc và dependencies

```text
thin-http-demo/
├── build.gradle
└── src/
    ├── main/java/demo/ThinHttpApp.java
    └── test/java/demo/BookServiceTest.java
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '1.0.0'

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}

springBoot {
    mainClass = 'demo.ThinHttpApp'
}
```

Cần Gradle phù hợp phiên bản plugin cùng JDK 17+. Nếu dự án đã có Gradle Wrapper, sử dụng wrapper; ví dụ này không giả định wrapper tự có trong thư mục mới tạo. Spring Boot starter web đem theo Spring MVC + Jackson; starter validation đem theo Hibernate Validator/Jakarta Bean Validation implementation.

### 8.2 Source đầy đủ: ThinHttpApp.java

```java
package demo;

import java.net.URI;
import java.util.HashMap;
import java.util.Map;
import java.util.Optional;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Repository;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@SpringBootApplication
public class ThinHttpApp {
    public static void main(String[] args) {
        SpringApplication.run(ThinHttpApp.class, args);
    }
}

// ----- Public API contracts -----

record CreateBookRequest(
        @NotBlank String title,
        @NotBlank String isbn) {}

record BookResponse(
        long id,
        String title,
        String isbn) {}

// ----- Domain model và application exceptions -----

record Book(long id, String title, String isbn) {}

class BookNotFoundException extends RuntimeException {
    BookNotFoundException(long id) {
        super("Book " + id + " not found");
    }
}

class DuplicateIsbnException extends RuntimeException {
    DuplicateIsbnException(String isbn) {
        super("ISBN already exists: " + isbn);
    }
}

class InvalidBookInputException extends RuntimeException {
    InvalidBookInputException(String detail) {
        super(detail);
    }
}

// ----- Port của storage -----

interface BookRepository {
    Book saveUnique(String title, String isbn);
    Optional<Book> find(long id);
}

// ----- Persistence adapter (chỉ dành cho demo) -----

@Repository
class InMemoryBookRepository implements BookRepository {
    private final Map<Long, Book> byId = new HashMap<>();
    private final Map<String, Long> idByIsbn = new HashMap<>();
    private long nextId = 1;

    @Override
    public synchronized Book saveUnique(String title, String isbn) {
        if (idByIsbn.containsKey(isbn)) {
            throw new DuplicateIsbnException(isbn);
        }

        Book book = new Book(nextId++, title, isbn);
        byId.put(book.id(), book);
        idByIsbn.put(isbn, book.id());
        return book;
    }

    @Override
    public synchronized Optional<Book> find(long id) {
        return Optional.ofNullable(byId.get(id));
    }
}

// ----- Application service: hoàn toàn độc lập với HTTP -----

@Service
class BookService {
    private final BookRepository repository;

    BookService(BookRepository repository) {
        this.repository = repository;
    }

    Book create(String title, String isbn) {
        String normalizedTitle = normalize(title, "title");
        String normalizedIsbn = normalize(isbn, "isbn");
        return repository.saveUnique(normalizedTitle, normalizedIsbn);
    }

    Book find(long id) {
        if (id <= 0) {
            throw new InvalidBookInputException("id must be positive");
        }
        return repository.find(id)
                .orElseThrow(() -> new BookNotFoundException(id));
    }

    private static String normalize(String value, String field) {
        if (value == null || value.isBlank()) {
            throw new InvalidBookInputException(field + " must not be blank");
        }
        return value.strip();
    }
}

// ----- HTTP adapter: bind, validate, map, respond -----

@RestController
@RequestMapping(
        path = "/api/books",
        produces = MediaType.APPLICATION_JSON_VALUE)
class BookController {
    private final BookService service;

    BookController(BookService service) {
        this.service = service;
    }

    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
    ResponseEntity<BookResponse> create(
            @Valid @RequestBody CreateBookRequest request) {
        Book result = service.create(request.title(), request.isbn());
        BookResponse body = toResponse(result);
        URI location = URI.create("/api/books/" + result.id());
        return ResponseEntity.created(location).body(body);
    }

    @GetMapping("/{id}")
    BookResponse get(@PathVariable long id) {
        return toResponse(service.find(id));
    }

    private static BookResponse toResponse(Book book) {
        return new BookResponse(book.id(), book.title(), book.isbn());
    }
}

// ----- HTTP exception mapping -----

@RestControllerAdvice
class ApiErrorHandler {
    @ExceptionHandler(BookNotFoundException.class)
    ProblemDetail notFound(BookNotFoundException ex) {
        return ProblemDetail.forStatusAndDetail(
                HttpStatus.NOT_FOUND, ex.getMessage());
    }

    @ExceptionHandler(DuplicateIsbnException.class)
    ProblemDetail duplicate(DuplicateIsbnException ex) {
        return ProblemDetail.forStatusAndDetail(
                HttpStatus.CONFLICT, ex.getMessage());
    }

    @ExceptionHandler(InvalidBookInputException.class)
    ProblemDetail badInput(InvalidBookInputException ex) {
        return ProblemDetail.forStatusAndDetail(
                HttpStatus.BAD_REQUEST, ex.getMessage());
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    ProblemDetail invalidBody(MethodArgumentNotValidException ex) {
        return ProblemDetail.forStatusAndDetail(
                HttpStatus.BAD_REQUEST,
                "Request body validation failed");
    }
}
```

**Tại sao chỉ một Java file mà vẫn thể hiện ranh giới?** Java cho phép chỉ một class public (`ThinHttpApp`), còn các top-level classes/records package-private cùng file. Đây là cách rút ngắn phần setup ví dụ. Trong codebase thật nên tách chúng theo trách nhiệm, ví dụ `api/`, `application/`, `domain/` và `persistence/`, để ownership và visibility rõ hơn. `InMemoryBookRepository` có `synchronized` trên cả ghi và đọc để giữ hai maps nhất quán trong một process; thay bằng storage phù hợp khi triển khai thật.

Controller không biết hai maps đang tồn tại. Service không biết `ResponseEntity` hay `ProblemDetail`. Đổi từ in-memory sang JPA adapter chỉ ảnh hưởng implementation repository và wiring nếu interface giữ nguyên.

### 8.3 Unit test service không cần Spring context

`src/test/java/demo/BookServiceTest.java`:

```java
package demo;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class BookServiceTest {

    @Test
    void createsAndFindsBook() {
        BookService service =
                new BookService(new InMemoryBookRepository());

        Book book = service.create("  Spring HTTP  ", "  123  ");

        assertEquals(1L, book.id());
        assertEquals("Spring HTTP", book.title());
        assertEquals("123", book.isbn());
        assertEquals(book, service.find(1L));
    }

    @Test
    void rejectsDuplicateAndMissingBook() {
        BookService service =
                new BookService(new InMemoryBookRepository());

        service.create("First", "ISBN-1");

        assertThrows(DuplicateIsbnException.class,
                () -> service.create("Other", "ISBN-1"));
        assertThrows(BookNotFoundException.class,
                () -> service.find(42L));
        assertThrows(InvalidBookInputException.class,
                () -> service.find(0L));
    }
}
```

Test gọi service như Java object bình thường. Không có Tomcat, HTTP, Spring `ApplicationContext`, Jackson hay database. Đây là một dấu hiệu tốt: **business logic có ranh giới riêng** và có thể xác minh độc lập.

Chạy:

```bash
gradle test
gradle bootRun
```

Trong thực tế, `gradle test` là lệnh hoàn tất rồi `gradle bootRun` chạy server; khi dùng hai terminal riêng, có thể chạy các lệnh tách biệt. Nếu có wrapper: `./gradlew test` / `./gradlew bootRun`, trên PowerShell `.\gradlew.bat test` / `.\gradlew.bat bootRun`.

Kết quả test được kỳ vọng: **2 tests pass**. Đây là kỳ vọng logic dựa trên mã đã trình bày, không phải báo cáo một lần chạy thực tế trong môi trường này. Không có stdout cố định từ `System.out.println`; Gradle sẽ ghi log riêng.

### 8.4 Dùng curl kiểm tra public contract

Khi Boot server đang ở port 8080, tạo sách:

```bash
curl -i -X POST http://localhost:8080/api/books \
  -H "Content-Type: application/json" \
  -d '{"title":"Spring HTTP","isbn":"9780000000001"}'
```

**Ví dụ response thành công** (chỉ hiển thị status/header/body liên quan, server có thể thêm headers và thay đổi thứ tự):

```http
HTTP/1.1 201 Created
Location: /api/books/1
Content-Type: application/json

{"id":1,"title":"Spring HTTP","isbn":"9780000000001"}
```

GET tiếp:

```bash
curl -i http://localhost:8080/api/books/1
```

**Ví dụ response:**

```http
HTTP/1.1 200 OK
Content-Type: application/json

{"id":1,"title":"Spring HTTP","isbn":"9780000000001"}
```

POST lần hai với cùng ISBN (service đã strip whitespace) trả **409 Conflict** và `ProblemDetail` có `status:409` cùng thông điệp duplicate. Gọi `GET /api/books/999` trả **404 Not Found**; gọi `GET /api/books/0` trả **400 Bad Request**. POST body `{"title":"","isbn":"x"}` sẽ bị Bean Validation chặn và trả 400 trước khi service tạo sách. Body JSON sai cú pháp cũng thường nhận HTTP 400 từ Spring MVC, dù không đi qua handler cho `MethodArgumentNotValidException`.

**Không khẳng định chính xác toàn bộ JSON lỗi** từ ví dụ nếu có auto-configuration hay extension khác. Chỉ coi các status và những trường contract được định nghĩa là kỳ vọng; để ổn định tuyệt đối, hãy thêm HTTP integration test kiểm tra response JSON keys, content type và status.

Thử POST hợp lệ khi server vừa restart: in-memory repository reset nên ID bắt đầu lại ở 1. Đó là behavior của demo, không phải requirement cho ứng dụng production.

### 8.5 Vì sao cần thêm HTTP contract test?

Unit test `BookService` không thể phát hiện lỗi `@PostMapping` sai route, Jackson không deserialize được record, thiếu `@Valid`, sai `Location` hoặc status 200 thay vì 201. Vì vậy cần một lớp web test dùng `MockMvc` hoặc chạy server trên random port; với Spring Boot có thể dùng `@WebMvcTest(BookController.class)` + mock service, hoặc `@SpringBootTest` + `@AutoConfigureMockMvc` để kiểm tra wiring. Các test nên assert contract thật, ví dụ:

- `POST /api/books` với JSON hợp lệ trả `201`, header `Location` đúng và JSON có ba field dự kiến.
- POST thiếu title trả `400`, service **không được gọi**.
- Duplicate ISBN trả `409` và error contract `application/problem+json`.
- GET ID không tồn tại trả `404`; GET ID tồn tại trả `200`.
- JSON không hợp lệ trả `400`; request Content-Type sai có thể trả `415`.

Với security được bật, test còn phải xác minh 401/403 đúng và bảo đảm user không truy cập tài nguyên của người khác. Kết hợp unit tests cho luật nghiệp vụ, web tests cho mapping, persistence integration tests cho uniqueness/transactions và end-to-end tests cho các hợp đồng quan trọng.

## 9. Thiết kế request/response mapping không tạo coupling ngầm

### 9.1 DTO mapping nên rõ ràng

Trong demo, mapper là một private method:

```java
private static BookResponse toResponse(Book book) {
    return new BookResponse(
            book.id(), book.title(), book.isbn());
}
```

Nếu có nhiều endpoint, mapping phức tạp hoặc cần reuse, có thể tách `BookDtoMapper`. Một mapper nên biểu diễn chuyển đổi dữ liệu có chủ đích, không chứa transaction, repository lookup hay network calls. MapStruct có thể hữu ích cho nhiều fields nhưng không tự giải quyết design contract; bạn vẫn phải chọn field nào công khai.

### 9.2 Những thay đổi hợp đồng dễ làm client hỏng

| Thay đổi | Tác động | Cách làm an toàn hơn |
| --- | --- | --- |
| Đổi tên JSON `isbn` thành `bookNumber` | Client cũ đọc field sai | Giữ alias tương thích hoặc version API |
| Đổi `id` từ số sang UUID string | Client parsing/storage thay đổi | Thiết kế migration và version |
| Biến optional field thành required | Request cũ trả 400 | Có giai đoạn chuyển tiếp, default hoặc endpoint version |
| Trả thêm field optional mới | Thường backward compatible với client tolerant | Đừng giả định mọi client đều bỏ qua unknown fields |
| Đổi 404 thành 200 + `null` | Consumer error branch sai | Giữ semantics ổn định, thông báo contract change |
| Dùng persistence entity mới làm response | Có nguy cơ lộ internal fields | Map explicit response DTO |
| Đổi thứ tự JSON properties | Thường không quan trọng về ngữ nghĩa JSON | Consumer không nên so sánh raw JSON string |

OpenAPI giúp khám phá hợp đồng nhưng file schema tự sinh không thay thế review về semantics. Một API có OpenAPI hợp lệ vẫn có thể có tên trường khó hiểu hoặc lỗi domain được trả sai status.

### 9.3 Versioning, pagination và idempotency

Versioning có thể nằm trong URL (`/api/v1/books`), header hoặc media type. Quan trọng hơn vị trí là **chính sách tương thích**: thay đổi nào breaking, hỗ trợ phiên bản cũ bao lâu, deprecation và migration diễn ra thế nào.

Endpoint danh sách nên quy định pagination và sort thay vì trả toàn bộ dataset theo kích thước tùy ý. Trả response DTO với `items`, `nextCursor` hoặc `page`/`size` theo yêu cầu, không lộ trực tiếp cấu trúc `Page<Entity>` bên trong. Limit max page size ở HTTP boundary; service phải xác thực query scope và bảo vệ query cost.

Với POST có side effects hoặc thanh toán, cân nhắc `Idempotency-Key` được client gửi qua header. Service/storage cần lưu trạng thái key theo user/operation cùng request fingerprint, xử lý cạnh tranh và TTL; chỉ đọc header trong controller mà không có cơ chế lưu/dedup thì **chưa** đạt idempotency.

## 10. Bảo mật, quan sát và vận hành tại ranh giới

### 10.1 AuthN/AuthZ không phải chuyện controller tự đọc JWT

Authentication xác định danh tính và thường do Spring Security filter chain xử lý. Controller có thể nhận principal hoặc security context cần thiết, sau đó application layer xác minh **quyền trên tài nguyên và use case**. Không tin bất kỳ `userId`/`tenantId` nào do client tự gửi là bằng chứng sở hữu.

Ví dụ `GET /api/books/42` trong demo là public, chưa có auth. Production cần quyết định ai được đọc/tạo/sửa, bảo vệ IDOR và multi-tenancy. Ràng buộc tài nguyên nên được enforce trong service/repository query dựa trên authenticated identity, không chỉ ẩn nút trên frontend.

### 10.2 Logging và tracing theo đúng lớp

- Ở HTTP layer: log HTTP method, route template, status, latency, correlation ID/trace ID; tránh log full Authorization headers, cookies và body nhạy cảm.
- Ở service: log sự kiện nghiệp vụ có ý nghĩa (book registered, order placed), outcome, identifier không nhạy cảm, không lặp dữ liệu request.
- Ở persistence: metric query latency, slow query và constraint violations; không log raw database credentials.
- Ở exception mapping: phân biệt expected client/business errors với unexpected 5xx. Không ghi stack trace 404 dự kiến như lỗi nghiêm trọng.
- Dùng Micrometer/Observation/trace propagation của Spring Boot khi phù hợp, để request ID nối qua HTTP client, service và storage.

Observability không nên làm service biết `HttpServletRequest`; truyền explicit business context/correlation khi thực sự cần, hoặc dựa tracing context được quản lý đúng.

### 10.3 Timeout, tài nguyên và tránh blocking không phù hợp

Với MVC/Servlet, thread request có thể bị giữ trong lúc đồng bộ gọi database/remote API; phải có connection pool, timeout và giới hạn đồng thời. Với WebFlux, controller nên trả reactive pipeline và tránh `block()` trên event-loop. Ranh giới service vẫn phải rõ dù method signature có thể là `Mono<Result>` hoặc `Flux<Result>`.

Khi service gọi API bên ngoài, định nghĩa connect/response timeout, retry có điều kiện, circuit breaker và backpressure phù hợp. Không để controller chứa `Thread.sleep`, infinite retry hay đồng bộ hóa trên một lock toàn cục để chữa nghẽn tải. Khi công việc rất dài, có thể trả `202 Accepted` với operation ID và tách xử lý background/job theo design thay vì giữ một HTTP request mở quá lâu.

## 11. Chọn package structure và cách refactor controller đang phình to

Một cấu trúc đơn giản theo feature thường dễ theo dõi hơn một thư mục chứa hàng trăm controllers/services chung:

```text
com.example.books/
├── api/
│   ├── BookController.java
│   ├── CreateBookRequest.java
│   ├── BookResponse.java
│   └── BookApiErrorHandler.java
├── application/
│   ├── BookService.java
│   └── BookRepository.java
├── domain/
│   ├── Book.java
│   └── DuplicateIsbnException.java
└── persistence/
    ├── JpaBookRepositoryAdapter.java
    └── BookEntity.java
```

Đây là mô hình tổ chức, không bắt buộc project nhỏ phải có đúng bốn package. Với nhiều bounded contexts, mỗi feature có thể quản lý domain và adapter của riêng nó. Đặt service name theo **ca sử dụng** (`RegisterBookService`, `PlaceOrderService`) nếu class quá lớn; không để một `CommonService` phụ trách mọi thứ.

### Các bước refactor an toàn

1. **Chụp public contract hiện tại:** routes, methods, body JSON, status, headers, error cases. Tạo HTTP tests cho behavior mà client đang dùng.
2. **Xác định luật nghiệp vụ** nằm trong controller: kiểm tra trạng thái, quyền resource, uniqueness, transaction, orchestration.
3. **Tách request/response DTO khỏi persistence entity**, đưa mapping vào adapter; tránh đổi JSON contract ngoài ý muốn.
4. **Đưa use case vào service** với input/output không phụ thuộc HTTP. Gắn transaction boundary vào service khi cần.
5. **Đưa storage vào repository/adapter**, dùng database constraints bảo vệ dữ liệu cạnh tranh.
6. **Chuẩn hóa exception translation** bằng `@RestControllerAdvice`/`ProblemDetail`, giữ status codes công khai nếu đã là hợp đồng ổn định.
7. **Chạy unit + HTTP contract + persistence integration tests** và kiểm tra logs/metrics trước khi rollout.

Đừng viết lại tất cả endpoints cùng lúc chỉ để “đẹp kiến trúc”. Với hệ thống legacy, chọn một vertical slice, giữ behavior và refactor dần. Nếu đang tồn tại contract sai nhưng client vẫn dựa vào nó, sửa cần kế hoạch tương thích/versioning thay vì âm thầm đổi 200 sang 404 trên production.

## 12. Những phản mẫu dễ gặp

1. **Controller gọi thẳng repository và chứa mọi rule:** business logic khó reuse/test, transaction boundary phân tán.
2. **Service trả `ResponseEntity` hoặc nhận `HttpServletRequest`:** transport coupling tràn vào application core.
3. **Trả JPA entity trực tiếp:** khó khóa chặt JSON schema, có nguy cơ lazy loading và lộ internal fields.
4. **Tin rằng `@Valid` đã bảo vệ mọi rule:** nó không thay thế business invariants, concurrency constraints hoặc authorization.
5. **Check duplicate bằng exists + save không atomic:** chạy song song sẽ tạo trùng; dùng database unique constraint và map lỗi hợp lý.
6. **Bắt tất cả exceptions rồi trả 200 với `success:false`:** vi phạm HTTP semantics, phá monitoring/retry/caching và hợp đồng client.
7. **Dùng mọi lỗi business là 500:** xóa nhòa expected outcomes và làm hệ thống báo động giả.
8. **Dùng `Map<String,Object>` cho mọi DTO:** dễ typo/thiếu compile-time safety, contract không rõ và thiếu validation.
9. **Biến service thành “God object” với hàng chục dependencies:** mỗi ca sử dụng nên có scope rõ; tách orchestration/aggregate theo domain boundaries.
10. **Dùng DTO class làm domain entity:** cùng một object có cả `@Entity`, `@JsonProperty`, `@RequestBody` và business lifecycle, khiến mọi tầng đổi theo nhau.
11. **Phụ thuộc message wording thay vì error code:** client parse `detail` string để ra quyết định, dẫn tới breaking khi dịch ngôn ngữ.
12. **Không phân biệt create đồng bộ và xử lý async:** trả 201 ngay khi job chưa tạo resource; cân nhắc 202 + operation status endpoint.
13. **Log request/response bodies mặc định:** có thể rò token, dữ liệu cá nhân và tăng log volume.
14. **Phỏng đoán performance từ số lớp:** chi phí network/DB/serialization thường vượt một lời gọi service; benchmark có chứng cứ rồi mới tối ưu.

## 13. Bài tập tự kiểm tra

**Câu 1.** Controller có method gọi JPA repository, chuyển tiền và gửi email trước khi trả response. Vì sao nên tách service?

**Trả lời:** HTTP adapter đang sở hữu cả business orchestration, transaction và integration failure handling. Service cần đặt ranh giới ca sử dụng; các side effects ngoài database có chính sách idempotency/outbox/saga phù hợp.

**Câu 2.** Có `@NotBlank` trên `CreateBookRequest.title`; có cần check null/blank trong service nữa không?

**Trả lời:** Với invariant quan trọng, có. Service có thể được gọi từ job/message listener không qua `@Valid`. Tránh duplicate validation quá phức tạp nhưng đừng đặt domain safety phụ thuộc HTTP.

**Câu 3.** Client gửi POST ISBN đã tồn tại; có nên trả 500?

**Trả lời:** Không, nếu duplicate là business conflict dự kiến, 409 là lựa chọn hợp lý. Mapping phải xuất phát từ rule thực, không biến mọi database exception thành 409.

**Câu 4.** Chỉ có unit test BookService thì đủ chứng minh endpoint POST trả 201 và Location đúng chưa?

**Trả lời:** Chưa. Cần HTTP contract test cho annotation routes, JSON binding, validation, status, headers, errors, security và serialization.

**Câu 5.** Có nên trả `BookEntity` trực tiếp làm JSON vì entity có sẵn getters?

**Trả lời:** Không nên. Public DTO kiểm soát fields và versioning; entity thường chứa nội bộ, relationships hoặc persistence-specific metadata.

**Câu 6.** Tạo thêm ba Spring instances có giúp unique ISBN an toàn nếu mỗi instance tự lock bằng `synchronized` không?

**Trả lời:** Không. Lock chỉ nằm trong JVM. Production cần unique index/constraint ở storage dùng chung và cơ chế xử lý tranh chấp.

**Câu 7.** REST controller trả 202 thay 201 trong trường hợp nào?

**Trả lời:** Khi request chỉ được **chấp nhận để xử lý sau**, chưa hoàn tất việc tạo resource. Contract nên có operation ID/status URL để client kiểm tra trạng thái.

**Câu 8.** Khi service đã tách khỏi HTTP, WebFlux có thể tái sử dụng service đồng bộ cũ trên event-loop một cách tự nhiên không?

**Trả lời:** Không tự động. Blocking I/O phải tránh trên event-loop; có thể cần reactive persistence/client, hoặc chuyển blocking tác vụ sang scheduler thích hợp có kiểm soát. Ý tưởng ranh giới vẫn đúng, nhưng execution model ảnh hưởng signatures và thread usage.

## Tài liệu tham khảo chính thức

- [Spring Framework — Annotated Controllers (Spring MVC)](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller.html)
- [Spring Framework — RequestBody and Validation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html)
- [Spring Framework — Controller Advice](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-advice.html)
- [Spring Framework — Error Responses / Problem Details](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html)
- [Spring Framework — Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html)
- [Spring Framework — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html)
- [Spring Boot — Validation](https://docs.spring.io/spring-boot/reference/io/validation.html)
- [Spring Boot — Testing](https://docs.spring.io/spring-boot/reference/testing/index.html)
