# HandlerExceptionResolver và ResponseEntityExceptionHandler trong Spring MVC

## 1. Hai thành phần giải quyết vấn đề gì?

Trong Spring MVC, một request có thể thất bại **trước khi controller được gọi**, **trong lúc xử lý controller**, hoặc **khi ghi phản hồi**. Ví dụ: JSON sai cú pháp, query parameter không chuyển được sang số, vi phạm Bean Validation, resource không tồn tại hoặc exception từ service.

Spring MVC cung cấp hai tầng liên quan nhưng có vai trò khác nhau:

- **`HandlerExceptionResolver`** là **contract hạ tầng** do `DispatcherServlet` sử dụng để nhờ các resolver xử lý exception. Có thể có nhiều implementation và một chuỗi được gọi theo thứ tự.
- **`ResponseEntityExceptionHandler`** là **base class cho `@ControllerAdvice`** để trả về `ResponseEntity` với phản hồi lỗi chuẩn cho nhiều exception quen thuộc của Spring MVC. Bản thân class này **không phải implementation của `HandlerExceptionResolver`**: Spring gọi các method `@ExceptionHandler` của nó thông qua `ExceptionHandlerExceptionResolver`.

Đây là phân biệt quan trọng nhất của bài. Thông thường, ứng dụng REST cần tùy chỉnh lỗi bằng **`@RestControllerAdvice` + kế thừa `ResponseEntityExceptionHandler`** hoặc các method `@ExceptionHandler` riêng. Chỉ viết `HandlerExceptionResolver` tùy biến nếu thật sự cần kiểm soát ở mức chuỗi resolver.

Ví dụ lỗi khác nhau cần phản hồi thích hợp:

| Lỗi | Exception tiêu biểu | HTTP status thông dụng |
| --- | --- | --- |
| JSON body không đọc được | `HttpMessageNotReadableException` | 400 Bad Request |
| `@Valid @RequestBody` không hợp lệ | `MethodArgumentNotValidException` | 400 Bad Request |
| Constraint trực tiếp trên tham số controller, Spring 6.1+ | `HandlerMethodValidationException` | 400 cho lỗi input; có thể 500 cho lỗi return value |
| Thiếu query parameter bắt buộc | `MissingServletRequestParameterException` | 400 Bad Request |
| Request sử dụng HTTP method không được phép | `HttpRequestMethodNotSupportedException` | 405 Method Not Allowed |
| Không có biểu diễn chấp nhận được theo `Accept` | `HttpMediaTypeNotAcceptableException` | 406 Not Acceptable |
| Request body có media type không hỗ trợ | `HttpMediaTypeNotSupportedException` | 415 Unsupported Media Type |
| Nghiệp vụ không tìm thấy entity | Exception domain do ứng dụng định nghĩa | Thường 404 Not Found |
| Bug không được xử lý trong ứng dụng | `NullPointerException` hoặc tương tự | 500 Internal Server Error |

Trạng thái cuối phụ thuộc cấu hình resolver, `@ControllerAdvice`, filter, Spring Security, Servlet container và ứng dụng. Không nên xem bảng này là cam kết tự động cho mọi exception.

## 2. Vòng đời lỗi bên trong `DispatcherServlet`

Luồng rút gọn:

```text
HTTP request
      |
Servlet Filter chain (Security, logging, ...)
      |
DispatcherServlet
      |
HandlerMapping -> HandlerAdapter -> Controller
      |                                |
      |                           exception được ném
      +------------------------------->|
      |
      v
HandlerExceptionResolver chain
      |
      +-- ExceptionHandlerExceptionResolver
      |     @ExceptionHandler local / @ControllerAdvice
      |     ResponseEntityExceptionHandler (qua advice)
      |
      +-- ResponseStatusExceptionResolver
      |     @ResponseStatus / ResponseStatusException
      |
      +-- DefaultHandlerExceptionResolver
      |     lỗi chuẩn của Spring MVC -> HTTP status
      |
      +-- resolver khác nếu ứng dụng đăng ký
      |
      v
HTTP error response / ModelAndView
      |
      +-- không ai xử lý? Có thể chuyển về Servlet container,
          error dispatch, Spring Boot /error (tùy trường hợp)
```

**Thứ tự trên là cấu hình MVC mặc định điển hình**, không phải thứ tự bất biến khi ứng dụng thêm resolver và `Ordered`. Một resolver xử lý thành công sẽ dừng chuỗi tại đó; những resolver sau thường không được gọi.

`HandlerExceptionResolver` có method:

```java
ModelAndView resolveException(
        HttpServletRequest request,
        HttpServletResponse response,
        Object handler,
        Exception ex);
```

Đây là chữ ký API minh họa, **không phải một method độc lập để chạy bằng `javac`**. Trong các phiên bản Spring hiện đại, tham số `handler` có thể `null` khi chưa chọn được handler. Contract có ba trường hợp:

- Trả **`ModelAndView` không rỗng**: exception đã xử lý, Spring có thể render view được chỉ định.
- Trả **`new ModelAndView()` rỗng**: exception đã xử lý và response đã được chuẩn bị; không cần render view.
- Trả **`null`**: resolver **không xử lý** exception; `DispatcherServlet` thử resolver tiếp theo.

**Không trả `null` sau khi tự ghi response**, nếu mục đích của bạn là kết thúc xử lý. Làm thế có thể khiến resolver khác tiếp tục ghi response, gây double-write hoặc sai status.

Exception ném từ Servlet Filter **trước khi vào `DispatcherServlet`** không mặc nhiên đi qua chuỗi resolver MVC. Tương tự, lỗi xảy ra sau khi response đã committed không thể tùy ý đổi thành body lỗi JSON mới.

## 3. Các `HandlerExceptionResolver` quan trọng

### 3.1. `ExceptionHandlerExceptionResolver`

Thực thi các method được gắn `@ExceptionHandler` trong controller và các bean `@ControllerAdvice`/`@RestControllerAdvice`.

Ví dụ khai báo cục bộ:

```java
@RestController
class ProfileController {

    @GetMapping("/profiles/{id}")
    String profile(@PathVariable long id) {
        if (id <= 0) {
            throw new IllegalArgumentException("invalid id");
        }
        return "profile-" + id;
    }

    @ExceptionHandler(IllegalArgumentException.class)
    ResponseEntity<String> badId(IllegalArgumentException ex) {
        return ResponseEntity.badRequest().body("Invalid profile id");
    }
}
```

Đây là class minh họa trong Spring MVC, cần các imports Spring. Handler này **chỉ áp dụng cho controller tương ứng**; khi muốn tái sử dụng toàn ứng dụng, chuyển sang global advice.

Các method `@ExceptionHandler` cục bộ được xét trước global advice. Trong nhiều advice, Spring sử dụng `@Order`/`Ordered` để quyết định mức ưu tiên; **root exception match** thường được ưu tiên trước cause match trong **cùng advice**, nhưng cause match trong advice ưu tiên cao hơn có thể thắng root match ở advice thấp hơn. Vì vậy, tránh các handler quá rộng như `@ExceptionHandler(Exception.class)` có độ ưu tiên cao nếu không có chiến lược rõ.

### 3.2. `ResponseStatusExceptionResolver`

Đọc `@ResponseStatus` trên exception hoặc `ResponseStatusException` và chuyển thành trạng thái HTTP phù hợp.

```java
@ResponseStatus(HttpStatus.NOT_FOUND)
class BookNotFoundException extends RuntimeException {
    BookNotFoundException(long id) {
        super("Book " + id + " not found");
    }
}
```

Khi exception này được ném, `ResponseStatusExceptionResolver` có thể map thành HTTP 404 **nếu resolver trước chưa xử lý nó**. `@ResponseStatus` không tự cung cấp schema JSON lỗi ổn định, trường `code` tùy biến hay bộ field errors.

Spring 6+ hỗ trợ `ProblemDetail` và `ErrorResponse`; trong ứng dụng muốn output lỗi thống nhất, một `@RestControllerAdvice` trả `ProblemDetail`/`ResponseEntity` thường thuận tiện hơn.

### 3.3. `DefaultHandlerExceptionResolver`

Xử lý nhiều lỗi chuẩn do Spring MVC sinh ra (ví dụ method không được hỗ trợ, thiếu request parameter, media type không phù hợp) và chuyển sang HTTP status tương ứng. Nó **không tự hiểu mọi exception nghiệp vụ** như `CustomerNotFoundException` hay `InventoryConflictException`.

Với API JSON, base class `ResponseEntityExceptionHandler` có thể bắt nhiều lỗi MVC và tạo lỗi dạng `ProblemDetail` trước khi đến default resolver. Nếu không có advice phù hợp, response thực tế có thể do default resolver và lớp xử lý lỗi của Servlet container/Spring Boot hoàn thiện.

### 3.4. `SimpleMappingExceptionResolver`

Resolver ánh xạ tên loại exception sang **view name**. Thường hữu ích với ứng dụng MVC render JSP/Thymeleaf và các trang HTML lỗi truyền thống.

Đối với API REST trả JSON, `@RestControllerAdvice` hoặc `ResponseEntityExceptionHandler` thường phù hợp hơn. Đừng đặt một HTML error view resolver bắt mọi lỗi cho endpoint JSON rồi để client nhận HTML không mong đợi.

## 4. `ResponseEntityExceptionHandler` giải quyết phần nào?

Class `org.springframework.web.servlet.mvc.method.annotation.ResponseEntityExceptionHandler` cung cấp một `@ExceptionHandler` xử lý nhiều exception chuẩn của Spring MVC, dựng `ResponseEntity<Object>` theo status, headers, body. Spring Framework 6+ dùng hỗ trợ `ProblemDetail`; trong Framework 6.2, định dạng lỗi được mô tả theo **RFC 9457**.

Cách dùng chuẩn:

```java
@RestControllerAdvice
public class ApiErrorAdvice extends ResponseEntityExceptionHandler {
    // Override protected handleXxx(...) khi cần tùy chỉnh
    // hoặc khai báo @ExceptionHandler cho lỗi domain riêng.
}
```

Đây là fragment cần imports; `ResponseEntityExceptionHandler` xử lý tập exception Spring MVC đã biết, còn những exception riêng do ứng dụng định nghĩa **cần thêm `@ExceptionHandler` phù hợp**.

Những hook điển hình có thể override trong **Spring Framework 6.1/6.2**:

| Protected method | Khi nào nên dùng |
| --- | --- |
| `handleMethodArgumentNotValid` | Điều chỉnh lỗi Bean Validation trên DTO |
| `handleHandlerMethodValidationException` | Điều chỉnh lỗi native method validation (Spring 6.1+) |
| `handleHttpMessageNotReadable` | Chuẩn hóa JSON malformed hoặc không deserialize được |
| `handleHttpRequestMethodNotSupported` | 405 và metadata về HTTP methods được phép |
| `handleHttpMediaTypeNotSupported` | 415 Unsupported Media Type |
| `handleHttpMediaTypeNotAcceptable` | 406 Not Acceptable |
| `handleMissingServletRequestParameter` | Query parameter bắt buộc bị thiếu |
| `handleTypeMismatch` | Đầu vào không thể chuyển sang kiểu mong đợi |
| `handleNoResourceFoundException` | Không tìm thấy static resource, Spring 6.1+ |
| `handleExceptionInternal` | Điểm xử lý chung cho một số exception |
| `createResponseEntity` | Điểm cuối để tạo `ResponseEntity` từ body/status/headers |

**Không viết thêm `@ExceptionHandler(MethodArgumentNotValidException.class)` bên trong subclass này** khi base class đã đăng ký exception đó qua `handleException`. Hai handler trùng có thể gây **ambiguous exception handler mapping** lúc khởi tạo.

Thay vào đó, override **protected `handleMethodArgumentNotValid(...)`**. Với lỗi nghiệp vụ mới (chưa nằm trong tập exception base class xử lý), hãy khai báo `@ExceptionHandler(MyDomainException.class)`.

### Chữ ký của override và khác biệt phiên bản

Trong Framework 6.x, hook dùng `HttpStatusCode`:

```java
@Override
protected ResponseEntity<Object> handleMethodArgumentNotValid(
        MethodArgumentNotValidException ex,
        HttpHeaders headers,
        HttpStatusCode status,
        WebRequest request) {
    // custom xử lý
}
```

Các tên type ở đây thuộc Spring MVC, cần imports phù hợp. Đừng sao chép override từ Spring Framework 5.x có tham số `HttpStatus` rồi mong nó override thành công trong 6.x. Framework 7 có thêm tiến hóa API, nên khi nâng version hãy xem Javadoc tương ứng thay vì tự sửa signature theo suy đoán.

## 5. `ProblemDetail`: chuẩn hóa body lỗi

RFC 9457 định nghĩa cấu trúc **Problem Details for HTTP APIs**. Spring Framework 6+ có `org.springframework.http.ProblemDetail` với những trường chuẩn:

| JSON field | Ý nghĩa |
| --- | --- |
| `type` | URI xác định loại vấn đề; mặc định thường là `about:blank` |
| `title` | Mô tả ngắn, dùng như nhãn loại lỗi |
| `status` | Mã HTTP tương ứng |
| `detail` | Diễn giải cụ thể cho instance lỗi |
| `instance` | URI chỉ instance xảy ra vấn đề |
| Extension fields | Thông tin tùy biến như `code`, `fields`, `traceId` |

Ví dụ response API có schema rõ:

```http
HTTP/1.1 404 Not Found
Content-Type: application/problem+json

{
  "type": "about:blank",
  "title": "Book not found",
  "status": 404,
  "detail": "Book was not found",
  "code": "BOOK_NOT_FOUND"
}
```

Đây là **response minh họa**, không khẳng định mọi cấu hình sẽ phát chính xác các headers/field như vậy. Jackson hỗ trợ serialize `ProblemDetail`, và Spring có cơ chế đưa các extension properties từ map thành các JSON fields.

Tạo thủ công:

```java
ProblemDetail problem = ProblemDetail.forStatusAndDetail(
        HttpStatus.NOT_FOUND, "Book was not found");
problem.setTitle("Book not found");
problem.setProperty("code", "BOOK_NOT_FOUND");
return ResponseEntity.status(HttpStatus.NOT_FOUND).body(problem);
```

Đây là fragment trong handler có imports `ProblemDetail`, `HttpStatus` và `ResponseEntity`. Khi body là `ProblemDetail`, Spring MVC ưu tiên media type `application/problem+json` khi có converter phù hợp; vẫn phải kiểm tra negotiated response trong ứng dụng thật.

### Phân biệt `status`, `detail` và exception message

Không trả trực tiếp `ex.getMessage()` cho mọi lỗi:

- Exception message có thể chứa SQL, path, implementation details, user input, token hoặc stack trace.
- `title` và `code` nên ổn định để client xử lý; `detail` nên hữu ích nhưng an toàn.
- Stack trace và thông tin nội bộ đưa vào **structured logs/tracing**, không phơi ra client.
- Field validation errors nên trả **tên field public** và mã lỗi được chọn, tránh trả lại password/rejectedValue nhạy cảm.
- `ProblemDetail` không có nghĩa tự động bảo đảm localization hay security; ứng dụng cần `MessageSource` và chính sách dữ liệu phù hợp.

## 6. Ví dụ Spring Boot 3.2+ / Spring Framework 6.1+ chạy được

Bài này dùng **Java 17+, Spring Boot 3.2+ với Spring MVC 6.1+**, để có cả hai loại lỗi validation. Ví dụ sử dụng in-memory map, không cần database. Spring Boot 3.x dùng `jakarta.validation.*`.

### 6.1. Dependencies

Trong dự án Spring Boot Gradle đã cấu hình plugin Boot, repositories và Java toolchain, cần:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Đây chỉ là **mảnh `build.gradle`**; khi dùng Maven thêm các starter tương ứng. `starter-validation` đảm bảo có provider Jakarta Bean Validation; chỉ có annotation API trong classpath thì chưa chứng minh validation hoạt động.

### 6.2. Application và controller

Tạo **`src/main/java/demo/errorhandling/ErrorHandlingApplication.java`**:

```java
package demo.errorhandling;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import java.net.URI;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicLong;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class ErrorHandlingApplication {

    public static void main(String[] args) {
        SpringApplication.run(ErrorHandlingApplication.class, args);
    }
}

record CreateBookRequest(@NotBlank String title) {}

record BookResponse(long id, String title) {}

class BookMissingException extends RuntimeException {
    BookMissingException(long id) {
        super("Book id " + id + " does not exist");
    }
}

@RestController
@RequestMapping("/api/books")
class BookController {

    private final AtomicLong nextId = new AtomicLong(1000);
    private final ConcurrentMap<Long, BookResponse> books =
            new ConcurrentHashMap<>();

    @PostMapping(
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    ResponseEntity<BookResponse> create(
            @Valid @RequestBody CreateBookRequest request) {

        long id = nextId.incrementAndGet();
        BookResponse saved = new BookResponse(id, request.title());
        books.put(id, saved);

        return ResponseEntity
                .created(URI.create("/api/books/" + id))
                .body(saved);
    }

    @GetMapping(path = "/{id}", produces = MediaType.APPLICATION_JSON_VALUE)
    BookResponse get(@PathVariable long id) {
        BookResponse book = books.get(id);
        if (book == null) {
            throw new BookMissingException(id);
        }
        return book;
    }

    @GetMapping(path = "/page", produces = MediaType.APPLICATION_JSON_VALUE)
    java.util.Map<String, Integer> page(@RequestParam @Min(1) int number) {
        return java.util.Map.of("number", number);
    }
}
```

Đây là **một file Java hợp lệ khi dùng classpath Boot 3**, do chỉ `ErrorHandlingApplication` là public; các kiểu còn lại package-private. Spring Boot component scan từ package `demo.errorhandling` sẽ nhận controller và advice ở phần tiếp theo.

- POST hợp lệ sẽ lưu sách, trả `201 Created` cùng `Location: /api/books/{id}`.
- POST `{"title":""}` bị `@NotBlank` từ chối, thường là `MethodArgumentNotValidException`.
- POST JSON sai cú pháp bị converter từ chối, thường là `HttpMessageNotReadableException`; validation chưa bắt đầu nếu JSON chưa chuyển được thành object.
- GET sách không tồn tại ném exception nghiệp vụ `BookMissingException`.
- GET `/api/books/page?number=0` vi phạm `@Min(1)` trực tiếp trên tham số method. Từ Framework 6.1+, đây là trường hợp native method validation (`HandlerMethodValidationException`) khi controller không đặt `@Validated` ở cấp class.

Ứng dụng dùng map trong bộ nhớ nên mất dữ liệu khi restart, không chia sẻ state giữa nhiều node và không có transaction DB. Trong production, exception nghiệp vụ nên phát sinh từ service/domain sau khi xét repository, authentication và quyền truy cập.

### 6.3. Global advice kế thừa `ResponseEntityExceptionHandler`

Tạo **`src/main/java/demo/errorhandling/ApiErrorAdvice.java`**:

```java
package demo.errorhandling;

import java.util.List;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.validation.FieldError;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.context.request.WebRequest;
import org.springframework.web.method.annotation.HandlerMethodValidationException;
import org.springframework.web.servlet.mvc.method.annotation.ResponseEntityExceptionHandler;

@RestControllerAdvice
class ApiErrorAdvice extends ResponseEntityExceptionHandler {

    // Exception nghiệp vụ riêng: base class không tự biết điều này.
    @ExceptionHandler(BookMissingException.class)
    ResponseEntity<ProblemDetail> bookMissing(BookMissingException ex) {
        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                HttpStatus.NOT_FOUND, "Book was not found");
        problem.setTitle("Book not found");
        problem.setProperty("code", "BOOK_NOT_FOUND");

        return ResponseEntity.status(HttpStatus.NOT_FOUND).body(problem);
    }

    // Lỗi trên DTO @Valid @RequestBody: override protected hook.
    @Override
    protected ResponseEntity<Object> handleMethodArgumentNotValid(
            MethodArgumentNotValidException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        ProblemDetail problem = ex.getBody();
        problem.setTitle("Invalid request");
        problem.setProperty("code", "INVALID_FIELDS");

        List<String> fields = ex.getBindingResult().getFieldErrors()
                .stream()
                .map(FieldError::getField)
                .distinct()
                .sorted()
                .toList();

        problem.setProperty("fields", fields);
        return handleExceptionInternal(
                ex, problem, headers, status, request);
    }

    // Lỗi cú pháp hoặc kiểu JSON trước khi DTO được bind thành công.
    @Override
    protected ResponseEntity<Object> handleHttpMessageNotReadable(
            HttpMessageNotReadableException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                status, "Request JSON cannot be read");
        problem.setTitle("Malformed request");
        problem.setProperty("code", "INVALID_JSON");

        return handleExceptionInternal(
                ex, problem, headers, status, request);
    }

    // Native method validation từ Spring MVC 6.1+.
    @Override
    protected ResponseEntity<Object> handleHandlerMethodValidationException(
            HandlerMethodValidationException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        ProblemDetail problem = ex.getBody();
        problem.setProperty("code", "METHOD_VALIDATION_FAILED");

        return handleExceptionInternal(
                ex, problem, headers, status, request);
    }
}
```

Các điểm kỹ thuật:

1. `@RestControllerAdvice` là global advice để trả body trực tiếp. `ResponseEntityExceptionHandler` đã có phương thức handler chung cho lỗi MVC được biết đến.
2. `bookMissing(...)` dùng `@ExceptionHandler` **chỉ cho exception domain riêng**. Handler này trả 404 và code ổn định.
3. `handleMethodArgumentNotValid(...)` **override** đúng hook thay vì đăng ký lại cùng exception qua `@ExceptionHandler`; trả danh sách **tên field** đã lỗi, không gửi lại rejected values.
4. `handleHttpMessageNotReadable(...)` trả detail cố định an toàn; **không truyền `ex.getMostSpecificCause().getMessage()` cho client** vì có thể lộ dữ liệu không nên công khai.
5. `handleHandlerMethodValidationException(...)` **giữ nguyên `status` do Spring quyết định**. Điều này quan trọng: lỗi input thường là 400, nhưng vi phạm return value có thể là 500; ép 400 cho cả hai sẽ che giấu bug.
6. Mọi protected override truyền tiếp qua `handleExceptionInternal(...)` để giữ quy trình chung của base class.
7. `ProblemDetail` do `ex.getBody()` cung cấp có status/detail từ exception. Việc chỉnh title/extension là có chủ đích; không tự đặt status mới không khớp với HTTP response.

**Không khai báo** `@Validated` ở cấp class `BookController` trong ví dụ này. Với Spring MVC 6.1+, nếu đặt ở cấp class, method validation có thể được thực hiện qua AOP proxy với đường exception khác native MVC. `@Validated` vẫn có vai trò hợp lệ trong service layer và trên tham số DTO để chọn nhóm.

### 6.4. Chạy thử với curl

Chạy:

```bash
./gradlew bootRun
```

Ở terminal Bash khác:

```bash
curl -i -X POST 'http://localhost:8080/api/books' \
  -H 'Content-Type: application/json' \
  -d '{"title":"Spring MVC"}'

curl -i -X POST 'http://localhost:8080/api/books' \
  -H 'Content-Type: application/json' \
  -d '{"title":""}'

curl -i -X POST 'http://localhost:8080/api/books' \
  -H 'Content-Type: application/json' \
  -d '{"title":'

curl -i 'http://localhost:8080/api/books/999999'
curl -i 'http://localhost:8080/api/books/page?number=0'
```

Kỳ vọng status trong ứng dụng mẫu, không có filter/security thay đổi hành vi:

| Request | Status | Extension `code` trong body nếu có |
| --- | --- | --- |
| POST JSON hợp lệ | 201 Created | Không phải body ProblemDetail; body là `BookResponse` |
| POST `title=""` | 400 Bad Request | `INVALID_FIELDS`; `fields` chứa `title` |
| POST JSON lỗi cú pháp | 400 Bad Request | `INVALID_JSON` |
| GET ID không tồn tại | 404 Not Found | `BOOK_NOT_FOUND` |
| GET `number=0` | 400 Bad Request | `METHOD_VALIDATION_FAILED` |
| GET `number=2` | 200 OK | JSON `{"number":2}` |

**Không dựa vào thứ tự field JSON hay thứ tự constraint violations**. Nếu bật Spring Security, client có thể nhận 401/403 trước khi vào MVC. Nếu custom filter thay đổi body/status, cần điều chỉnh kiểm thử theo hệ thống thật.

## 7. Kiểm thử tích hợp với `MockMvc`

Trong dự án ví dụ, tạo **`src/test/java/demo/errorhandling/ErrorHandlingApplicationTests.java`**:

```java
package demo.errorhandling;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ErrorHandlingApplicationTests {

    @Autowired
    MockMvc mvc;

    @Test
    void successfulCreationReturns201() throws Exception {
        mvc.perform(post("/api/books")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"title":"Spring MVC"}
                    """))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.title").value("Spring MVC"));
    }

    @Test
    void invalidDtoUsesOverriddenHook() throws Exception {
        mvc.perform(post("/api/books")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"title":""}
                    """))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("INVALID_FIELDS"))
            .andExpect(jsonPath("$.fields[0]").value("title"));
    }

    @Test
    void malformedJsonGetsSafeProblemDetail() throws Exception {
        mvc.perform(post("/api/books")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"title\":"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("INVALID_JSON"));
    }

    @Test
    void domainExceptionGets404() throws Exception {
        mvc.perform(get("/api/books/999999"))
            .andExpect(status().isNotFound())
            .andExpect(jsonPath("$.code").value("BOOK_NOT_FOUND"))
            .andExpect(jsonPath("$.title").value("Book not found"));
    }

    @Test
    void methodValidationUsesSeparateHook() throws Exception {
        mvc.perform(get("/api/books/page").param("number", "0"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("METHOD_VALIDATION_FAILED"));

        mvc.perform(get("/api/books/page").param("number", "2"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.number").value(2));
    }
}
```

Chạy:

```bash
./gradlew test
```

Với Spring Framework 6.1+/Boot 3.2+ tương thích, `spring-boot-starter-validation` và các class như trên, **năm test được thiết kế để pass**. Đây là kỳ vọng phân tích từ mã mẫu; bài không tuyên bố đã thực thi Gradle.

Bộ test chứng minh **đường error handling end-to-end bên trong MVC**. Để khẳng định body luôn là `application/problem+json`, thêm assertion `contentTypeCompatibleWith(MediaType.APPLICATION_PROBLEM_JSON)` nếu đó là hợp đồng API được công bố và Spring phiên bản đó hỗ trợ media type. Không yêu cầu mọi API lỗi phải dùng JSON khi client chỉ chấp nhận HTML.

Những kiểm thử khác nên có: thiếu query parameter, JSON sai kiểu, 405/406/415, method validation return value và tương tác với Spring Security. Đặc biệt cần kiểm tra có rule global advice nào khác vô tình “cướp” lỗi cùng loại không.

## 8. Chọn lớp nào cho từng loại tùy chỉnh?

| Nhu cầu | Công cụ phù hợp | Lý do |
| --- | --- | --- |
| Một controller cần cách xử lý lỗi cục bộ | `@ExceptionHandler` trong controller | Đơn giản, scope hẹp |
| Toàn REST API dùng schema lỗi chung | `@RestControllerAdvice` | Xử lý tập trung |
| Muốn custom lỗi chuẩn MVC (JSON malformed, validation, unsupported method...) | Kế thừa `ResponseEntityExceptionHandler` | Có hooks và status/headers mặc định |
| Cần ánh xạ exception nghiệp vụ sang HTTP | `@ExceptionHandler(DomainException.class)` trong advice | Rõ status và body |
| REST API cần chuẩn hóa lỗi RFC 9457 | `ProblemDetail`/`ErrorResponse` | JSON schema chuẩn |
| MVC render trang HTML lỗi | `SimpleMappingExceptionResolver` hoặc `@ControllerAdvice` trả view | Gắn với view resolution |
| Thay đổi cơ chế resolve ở hạ tầng MVC | `HandlerExceptionResolver` tùy biến | Kiểm soát sâu thứ tự/giải quyết lỗi |
| Exception ném trước `DispatcherServlet` từ filter | Cơ chế error handling ở filter/container/security phù hợp | Không mặc nhiên thuộc chuỗi MVC resolver |

**Quy tắc thực hành:** nếu bạn có thể giải quyết bằng `@ExceptionHandler` hoặc override của `ResponseEntityExceptionHandler`, không cần tự viết custom `HandlerExceptionResolver`. Việc tự viết resolver đòi hỏi xử lý response output, thứ tự, null/empty result và trường hợp response đã committed.

## 9. Khi nào tự implement `HandlerExceptionResolver`?

Trong các hệ thống phải can thiệp sâu (ví dụ MVC hỗn hợp HTML/REST, quản lý exception tại tầng framework riêng hoặc tích hợp legacy resolver), có thể tự tạo một resolver. Mẫu sau **chỉ xử lý một exception cụ thể** và trả `null` cho mọi exception khác:

```java
package demo.errorhandling;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.core.Ordered;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.HandlerExceptionResolver;
import org.springframework.web.servlet.ModelAndView;

@Component
class LegacyQuotaResolver
        implements HandlerExceptionResolver, Ordered {

    @Override
    public int getOrder() {
        return Ordered.HIGHEST_PRECEDENCE;
    }

    @Override
    public ModelAndView resolveException(
            HttpServletRequest request,
            HttpServletResponse response,
            Object handler,
            Exception ex) {

        if (!(ex instanceof LegacyQuotaExceededException)) {
            return null; // Resolver khác có thể tiếp tục xử lý.
        }

        response.setStatus(HttpServletResponse.SC_TOO_MANY_REQUESTS);
        return new ModelAndView(); // Đánh dấu đã xử lý; body rỗng.
    }
}

class LegacyQuotaExceededException extends RuntimeException {}
```

Đây là **ví dụ resolver độc lập về cấu trúc** nhưng phải tích hợp cẩn thận với cách Spring MVC xây resolver chain. Chỉ đặt `@Component` không phải bảo đảm thứ tự/đăng ký mong muốn trong mọi cấu hình Boot hay custom MVC; hãy kiểm tra danh sách resolver thực tế. Mẫu trả body rỗng cho `429 Too Many Requests`, chưa có thông tin `Retry-After` hoặc `ProblemDetail`, nên **không xem là endpoint production hoàn chỉnh**.

Nhiều trường hợp tốt hơn viết:

```java
@ExceptionHandler(LegacyQuotaExceededException.class)
ResponseEntity<ProblemDetail> quotaExceeded(
        LegacyQuotaExceededException ex) {

    ProblemDetail p = ProblemDetail.forStatus(
            HttpStatus.TOO_MANY_REQUESTS);
    p.setTitle("Too many requests");
    p.setProperty("code", "QUOTA_EXCEEDED");
    return ResponseEntity.status(HttpStatus.TOO_MANY_REQUESTS).body(p);
}
```

Đây là fragment `@RestControllerAdvice`, chưa đặt header `Retry-After` vì cần chính sách quota thực tế. Khi lỗi này thuộc MVC/controller, cách viết advice giúp nhất quán với các exception handler khác và tránh phải trực tiếp ghi Servlet response.

**Nếu cần điều chỉnh resolver chain**, Spring MVC có các hook `WebMvcConfigurer#configureHandlerExceptionResolvers(...)` và `extendHandlerExceptionResolvers(...)`. Trong Spring 6.x, method `configureHandlerExceptionResolvers` với list đã được thêm custom resolver có thể khiến Spring bỏ đăng ký chuỗi default thông thường; còn `extendHandlerExceptionResolvers` phù hợp khi chỉ cần sửa/bổ sung list sẵn có. Trước khi thay thứ tự, đọc đúng Javadoc bản Spring đang chạy và đảm bảo `ExceptionHandlerExceptionResolver` cùng các default resolvers vẫn hiện diện.

## 10. Thứ tự `@ControllerAdvice` và trường hợp “handler không chạy”

Một ứng dụng có thể có nhiều advice:

```java
@RestControllerAdvice
@Order(Ordered.HIGHEST_PRECEDENCE)
class DomainAdvice {
    @ExceptionHandler(DomainException.class)
    ResponseEntity<ProblemDetail> handle(DomainException ex) {
        // ...
    }
}
```

Đây là fragment minh họa, cần import `@Order` và `Ordered`, định nghĩa `DomainException`; **không phải class runnable khi dấu `...` còn trong thân method**.

Các nguyên tắc:

- `@ExceptionHandler` trong controller được xét trước global advice.
- Giữa các global advice, `@Order`, `Ordered` hoặc `@Priority` ảnh hưởng độ ưu tiên. Trong một advice, Spring chọn mapping exception phù hợp nhất với root/cause.
- Một advice ưu tiên cao bắt cause có thể thắng một advice thấp bắt root. Không dựa vào giả định “root luôn thắng bất kể order”.
- Một handler bắt `Exception.class` quá rộng có thể nuốt `ResponseStatusException`, 405/415, lỗi framework hoặc logic riêng và làm mất HTTP status đúng.
- Class kế thừa `ResponseEntityExceptionHandler` vốn đã có handler cho rất nhiều loại exception MVC. Tránh tạo advice thứ hai có catch-all ưu tiên cao mà không đánh giá xung đột.
- Nếu annotation selector như `basePackages`/`assignableTypes` hạn chế advice, controller nằm ngoài vùng đó không được áp dụng advice.
- Với exception được wrap, Spring có thể xét cause chain; kiểm tra root/cause và thứ tự advice trong test thay vì chỉ dựa vào tên exception.
- Nếu handler rethrow exception nguyên bản, việc xử lý có thể tiếp tục qua chuỗi resolution; không nên rethrow hoặc return null tùy tiện khi response đã bị ghi.

Một global advice kế thừa `ResponseEntityExceptionHandler` ở vị trí hợp lý cùng handler domain cụ thể thường dễ bảo trì hơn nhiều advice có `@Order` chồng chéo.

## 11. Lỗi validation: vì sao đôi khi khác exception?

Hai API nhìn tương tự nhưng đường xử lý khác:

```java
// Validate DTO bằng @Valid trên argument:
@PostMapping("/users")
void create(@Valid @RequestBody UserDto body) {}

// Constraint trực tiếp trên method parameter, Spring MVC 6.1+:
@GetMapping("/users/page")
void page(@RequestParam @Min(1) int number) {}
```

Các đoạn trên là fragment trong controller, `UserDto` cần định nghĩa.

- Trường hợp thứ nhất thường gây **`MethodArgumentNotValidException`** khi object DTO không hợp lệ và không có `BindingResult` theo ngay sau tham số.
- Trường hợp thứ hai kích hoạt **native method validation** và có thể gây **`HandlerMethodValidationException`**.
- Khi có constraint trực tiếp trên tham số phương thức (ví dụ `@NotNull` ở method parameter), Spring MVC 6.1+ có thể áp dụng method validation bao trùm cả constraints lồng nhau; lỗi DTO lúc đó có thể đi qua method validation.
- Nếu đặt `@Validated` ở **class level** của controller, method validation có thể do Spring AOP proxy thực hiện, với exception/đường gọi khác. Để tận dụng native method validation, Spring khuyến nghị bỏ class-level `@Validated` khỏi controller trong trường hợp thích hợp.
- Với Spring Framework 6.0 trở xuống, native method validation của MVC từ 6.1 **chưa tồn tại**; cần cấu hình/hành vi AOP tương ứng nếu muốn validate trực tiếp method parameters.
- `BindingResult` phải theo ngay sau argument được validate. Với method validation, controller chỉ có thể chạy nếu mọi lỗi liên quan được xử lý ở các tham số có `Errors`/`BindingResult` thích hợp; vi phạm ở tham số khác vẫn có thể ném exception.

**Không hardcode “mọi exception validation đều là 400”**. Ví dụ vi phạm return value constraint là dấu hiệu server code trả về sai contract và có thể được Spring 6.1+ xử lý là 500. Sử dụng status có sẵn từ `HandlerMethodValidationException` và log tình huống 5xx.

## 12. `ResponseStatusException` và `ErrorResponseException`

Khi muốn controller/service báo lỗi HTTP có chủ đích mà không tạo exception domain riêng, Spring cung cấp `ResponseStatusException`:

```java
throw new ResponseStatusException(
        HttpStatus.NOT_FOUND, "Book was not found");
```

Spring 6+ tích hợp nhiều exception dạng `ErrorResponse`, có thể cung cấp `ProblemDetail` và status. Ví dụ `ResponseStatusException` thường được xử lý bởi resolver phù hợp; khi có `ResponseEntityExceptionHandler` trong advice, tập exception nền tảng của nó có thể nhận trước.

Ưu điểm: dễ dùng cho lỗi đơn giản. Đánh đổi: service/domain có thể bị phụ thuộc vào ngữ nghĩa HTTP nếu ném từ sâu bên trong business layer. Với nghiệp vụ lớn, thường tốt hơn định nghĩa `BookMissingException` độc lập rồi map ở web layer bằng `@ExceptionHandler`.

`ErrorResponseException` trong Spring 6+ cung cấp cơ chế biểu diễn exception cùng `ErrorResponse`/`ProblemDetail`. Không nên xem nó là base class buộc phải kế thừa cho mọi exception nghiệp vụ; hãy chọn theo kiến trúc và hợp đồng lỗi đã thiết kế.

## 13. Header HTTP phải được bảo toàn khi tùy chỉnh lỗi

Một số exception không chỉ có status. Ví dụ:

- **405 Method Not Allowed**: header **`Allow`** có thể liệt kê các HTTP methods được phép.
- **415 Unsupported Media Type**: response có thể mang thông tin media type hỗ trợ theo logic MVC.
- **429 Too Many Requests**: nếu áp dụng rate limiting, `Retry-After` có ích theo policy thực tế.
- **401 Unauthorized**: các challenge **`WWW-Authenticate`** phải được giữ khi giao thức xác thực yêu cầu.
- **413 Content Too Large** hoặc các lỗi container/network: có thể xảy ra trước controller, cần xem layer thực sự sinh response.

Khi override `handleHttpRequestMethodNotSupported`, `handleHttpMediaTypeNotSupported` hoặc những hook tương tự, Spring truyền vào `HttpHeaders headers` cùng `status` đã chọn. **Đừng vô tình đánh rơi header chuẩn** bằng cách dựng response mới bỏ qua `headers`. Sử dụng `handleExceptionInternal(ex, body, headers, status, request)` hoặc xây `ResponseEntity` có headers thích hợp.

Nếu response đã committed (đã flush hoặc truyền một phần body), Spring không thể biến nó một cách đáng tin cậy thành ProblemDetail mới. Các exception khi stream/file download, SSE hoặc async response cần chiến lược riêng.

## 14. Spring Boot `/error` và các resolver MVC là hai tầng khác nhau

Spring Boot Servlet app thường có endpoint lỗi fallback `/error` cùng `BasicErrorController`/`ErrorAttributes` tùy auto-configuration. Nó phục vụ xử lý lỗi qua **Servlet container error dispatch** và những trường hợp không được giải quyết bằng response của MVC resolver/advice.

Đường đi ví dụ:

```text
Controller throws exception
   |
DispatcherServlet HandlerExceptionResolvers
   |
   +-- Advice xây ResponseEntity<ProblemDetail> thành công
   |      -> trả JSON trực tiếp, không cần BasicErrorController
   |
   +-- Exception chưa xử lý hoặc sendError / container error dispatch
          -> có thể vào Spring Boot /error
          -> BasicErrorController / ErrorAttributes / custom error page
```

Do đó cấu hình `server.error.*` trong Spring Boot có thể ảnh hưởng fallback `/error`, nhưng **không nên giả định nó biến đổi body do custom `@ExceptionHandler` đã trả**. Tương tự, việc cấu hình `spring.mvc.problemdetails.enabled` ở một số dòng Boot 3 có thể bật cơ chế lỗi ProblemDetail tích hợp, còn một advice tự trả `ProblemDetail` vẫn có hợp đồng riêng. Xác nhận property và default theo đúng version Boot.

Nếu ứng dụng có hai cách xử lý lỗi, cần test để bảo đảm **schema nhất quán** ở các đường controller, missing handler/static resource, filter/security và container errors. Tuy nhiên, không cố ép mọi lỗi container hoặc stream failure thành một JSON body khi response đã bắt đầu gửi.

## 15. Kết hợp với Spring Security và filter chain

`HandlerExceptionResolver` MVC **không phải cơ chế thay thế hoàn chỉnh cho Spring Security**.

- Spring Security filter xử lý nhiều lỗi authentication/authorization trước khi request đến `DispatcherServlet`; `AuthenticationEntryPoint` và `AccessDeniedHandler` có trách nhiệm tạo 401/403 tương ứng.
- Nếu exception được ném từ một custom Servlet filter trước MVC, global `@RestControllerAdvice` **không tự bắt được**.
- Có thể chủ động tích hợp filter với một bean `HandlerExceptionResolver` được inject để delegate exception, nhưng cần cẩn thận request/response lifecycle, thứ tự, double-write và security semantics. Đây là quyết định hạ tầng có chủ đích, không phải behavior mặc định.
- Chỉ nên đưa public error code và correlation ID an toàn ra response; chi tiết về token, quyền, SQL hoặc stack trace thuộc log nội bộ.
- Nếu reverse proxy/gateway cũng biến đổi status/body, hãy kiểm thử end-to-end để phát hiện lỗi do layer bên ngoài trả.

Ví dụ một client không có quyền GET resource có thể nhận 403 ngay từ Security, dù controller nếu được gọi sẽ ném `BookMissingException` 404. Để xác định trách nhiệm, kiểm tra HTTP status, filter chain và logs với correlation ID.

## 16. Version compatibility và migration

| Spring Framework / Boot thường gặp | Cách xử lý cần chú ý |
| --- | --- |
| Framework 5.x / Boot 2.x | Có `HandlerExceptionResolver` và `ResponseEntityExceptionHandler`; custom signature thường dùng `HttpStatus` thay vì `HttpStatusCode`; Jakarta namespace trong nhiều API còn là `javax.*`; chưa có `ProblemDetail` built-in như Spring 6. |
| Framework 6.0 / Boot 3.0–3.1 | Java 17+, Jakarta namespace, `ProblemDetail` và `ErrorResponse` được bổ sung; `ResponseEntityExceptionHandler` xử lý lỗi theo cơ chế mới. |
| Framework 6.1+ / Boot 3.2+ | Native MVC method validation và `HandlerMethodValidationException`; thêm các tình huống như `NoResourceFoundException` cho static resources. |
| Framework 6.2 / Boot 3.4–3.5 | Đường `ResponseEntityExceptionHandler` hỗ trợ định dạng lỗi RFC 9457 và các protected hooks cần thiết cho ví dụ. |
| Framework 7.x / Boot 4.x | Hạ tầng `HandlerExceptionResolver` và base advice tiếp tục tồn tại; cần kiểm tra lại signatures, error formatting, Jackson 3/Boot module changes khi chuyển code hiện hữu. |

Bản chạy ví dụ nên dùng **Boot 3.4 hoặc 3.5** để có Spring Framework 6.2 tương thích với các protected overrides đã nêu, Java 17+. Nếu ứng dụng override BOM, version thực tế của `spring-webmvc` mới quyết định API cần dùng.

Không tự suy luận rằng copy một advice từ Boot 2 lên Boot 3 sẽ biên dịch: `javax.servlet` đã đổi sang `jakarta.servlet`, tham số `HttpStatus` trong nhiều hooks được thay bằng `HttpStatusCode`, và tập exception framework hỗ trợ đã phát triển.

## 17. Chẩn đoán khi API lỗi không đúng định dạng

### Trường hợp 1: controller ném exception nhưng advice không chạy

Kiểm tra:

1. Exception có thực sự ném **trong `DispatcherServlet`**? Nếu xảy ra ở security/filter hoặc servlet khác, MVC advice không mặc nhiên tham gia.
2. `@RestControllerAdvice` có được component scan? Package của advice có nằm dưới root `@SpringBootApplication` hoặc đã được import?
3. Có `@ExceptionHandler` cục bộ hoặc global advice khác bắt lỗi trước không?
4. Có tự đăng ký `HandlerExceptionResolver` ưu tiên cao và trả non-null quá sớm?
5. Response đã committed hoặc xử lý async/stream khác thường chưa?

### Trường hợp 2: có 400 nhưng body lại là JSON `/error` hoặc HTML

Kiểm tra whether exception đã được resolver xử lý trực tiếp, error dispatch đến container, và content negotiation theo `Accept`. Quan sát header `Content-Type`, `ProblemDetail` content và logs. Trong Boot, cấu hình mặc định `/error` có thể tạo JSON structure khác advice. Đừng chỉ dựa vào status code.

### Trường hợp 3: thêm handler validation bị lỗi ambiguous mapping

Nếu đang `extends ResponseEntityExceptionHandler` mà tự khai báo `@ExceptionHandler(MethodArgumentNotValidException.class)` hoặc `@ExceptionHandler(HttpMessageNotReadableException.class)` trên cùng advice, có thể trùng handler của base class. Hãy **override đúng protected hook**, gỡ handler trùng và viết integration test context starts.

### Trường hợp 4: mọi lỗi thành 500

Rà soát một catch-all handler `@ExceptionHandler(Exception.class)` hoặc custom resolver ép status 500 và đánh rơi thông tin `ErrorResponse`. Bảo toàn `HttpStatusCode` từ các framework exceptions đã biết, và để lỗi nghiệp vụ map theo loại cụ thể. Chỉ dùng 500 cho lỗi phía server thật sự.

### Trường hợp 5: lỗi xảy ra nhưng client nhận 200

Một resolver có thể đã ghi body mà quên set status; một `@ExceptionHandler` trả object bình thường mà không dùng `@ResponseStatus`/`ResponseEntity.status(...)` sẽ không tự chuyển sang mã lỗi mong muốn. Kiểm tra status được set ở layer xử lý exception.

### Trường hợp 6: content negotiation hỏng khi trả ProblemDetail

Nếu client gửi `Accept` chỉ cho một media type không hỗ trợ, Spring có thể không serialize được body ProblemDetail theo ý định. Kiểm tra converters thực tế (Jackson 2 ở Boot 3, Jackson 3 ở Boot 4), `Accept` và những endpoint hỗn hợp HTML/JSON. Không cố ghi JSON vào response đã committed.

## 18. Checklist triển khai production

- [ ] Có bảng ánh xạ rõ **domain errors → HTTP status → public error code**, không leak technical exception names.
- [ ] Có một đường xử lý tập trung cho lỗi Spring MVC thông dụng bằng `ResponseEntityExceptionHandler` hoặc cơ chế tương đương.
- [ ] Các override giữ `status`, `headers`, content negotiation và hành vi 5xx thích hợp.
- [ ] Có `@ExceptionHandler` cụ thể cho lỗi domain; tránh catch-all nuốt lỗi framework.
- [ ] `ProblemDetail`/schema JSON có title, detail, code, traceId ở mức an toàn và có versioning khi contract đổi.
- [ ] Error body không chứa token, password, SQL, path nội bộ hay stack trace.
- [ ] Handler validation đúng theo Framework version, phân biệt `MethodArgumentNotValidException` và `HandlerMethodValidationException`.
- [ ] Filter/Security/container error paths được đánh giá riêng; các lỗi 401/403 không bị MVC advice vô tình thay thế.
- [ ] Có integration tests cho 400, 404, 405, 415, 500 và content negotiation thực tế.
- [ ] Có correlation ID và structured logging riêng cho vận hành; lỗi dự kiến 4xx không bị log full stack trace ồ ạt.
- [ ] Các lỗi chưa xử lý vẫn được log và giám sát; không che tất cả thành `200 OK`.
- [ ] Sau nâng cấp Spring/Boot, rà soát protected override signatures và resolver ordering.

## 19. Bài tập tự kiểm tra

1. Trình bày khác biệt giữa `HandlerExceptionResolver` và `ResponseEntityExceptionHandler`. Class nào được `DispatcherServlet` gọi trực tiếp, và class nào được `ExceptionHandlerExceptionResolver` gọi gián tiếp?
2. Một custom resolver gặp exception không biết thì nên trả `null` hay `new ModelAndView()`? Hãy giải thích tác động tới resolver tiếp theo.
3. Khi `@Valid @RequestBody` thất bại và bạn kế thừa `ResponseEntityExceptionHandler`, vì sao cần override `handleMethodArgumentNotValid` thay vì thêm `@ExceptionHandler(MethodArgumentNotValidException.class)`?
4. Spring Framework 6.1+, vì sao `@RequestParam @Min(1) int page` có thể đi qua `HandlerMethodValidationException`, trong khi `@Valid @RequestBody UserDto` thường đi qua `MethodArgumentNotValidException`?
5. Xây dựng một `@RestControllerAdvice` map `OrderMissingException` sang 404 và `OrderConflictException` sang 409 bằng `ProblemDetail` với `code` ổn định.
6. Nếu một exception handler 405 làm mất header `Allow`, điều gì có thể bị ảnh hưởng? Hãy giữ `headers` do Spring chuyển vào protected hook.
7. Một custom filter ném lỗi trước `DispatcherServlet`, còn global `@RestControllerAdvice` không chạy. Đâu là layer phù hợp để xử lý và vì sao?
8. Ứng dụng có hai advice: advice ưu tiên cao bắt cause `IOException`, advice thấp bắt root `IllegalStateException`. Advice nào có thể thắng? Giải thích theo thứ tự và matching.
9. Hãy viết test chứng minh `ProblemDetail` validation không chứa rejected password nhưng có public error code và field name.
10. Nâng Boot 2 lên Boot 3: những imports/chữ ký nào phải đổi khi override `handleMethodArgumentNotValid`, và tại sao không thể bê nguyên cơ chế cũ?

## 20. Tài liệu chính thức

- [Spring Framework — Servlet MVC Exception Resolvers](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/exceptionhandlers.html): `HandlerExceptionResolver`, chuỗi resolver và semantics của `ModelAndView`.
- [Spring Framework — `@ExceptionHandler`](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-exceptionhandler.html): mapping ngoại lệ, root/cause và return values.
- [Spring Framework — `@ControllerAdvice`](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-advice.html): global scope và độ ưu tiên.
- [Spring Framework — REST Exceptions and Error Responses](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html): `ProblemDetail`/`ErrorResponse` và `ResponseEntityExceptionHandler`.
- [Spring Framework 6.2 — ResponseEntityExceptionHandler Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/servlet/mvc/method/annotation/ResponseEntityExceptionHandler.html): các protected override và signatures.
- [Spring Framework 6.2 — HandlerExceptionResolver Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/servlet/HandlerExceptionResolver.html): contract resolver.
- [Spring Framework — MVC Validation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html): phân biệt `MethodArgumentNotValidException` và `HandlerMethodValidationException`.
- [RFC 9457 — Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457.html): semantics và các members chuẩn của problem response.
- [Spring Boot — Error Handling](https://docs.spring.io/spring-boot/reference/web/servlet.html): `/error`, `BasicErrorController` và error fallback.
