# @ExceptionHandler, @ControllerAdvice và @RestControllerAdvice trong Spring Boot

> **Phạm vi:** Spring Boot **3.5.x**, Spring Framework **6.2.x**, Java **17+**, ứng dụng HTTP **Spring MVC (Servlet)**. Chủ đề là cách bắt và chuyển ngoại lệ thành HTTP response có kiểm soát: xử lý ngay trong controller với `@ExceptionHandler`, xử lý dùng chung bằng `@ControllerAdvice` / `@RestControllerAdvice`, thứ tự ưu tiên, lỗi framework, RFC 9457 `ProblemDetail`, kiểm thử và các bẫy thường gặp. Phần cuối đối chiếu WebFlux. Ví dụ hoàn chỉnh dùng Maven và Spring Boot **3.5.0**; thay version khi triển khai thực tế.

## 1. Vì sao cần một chiến lược xử lý lỗi HTTP?

Controller có thể gặp nhiều lỗi:

- Người dùng yêu cầu sách không tồn tại → **404 Not Found**.
- ID sai hoặc request body không hợp lệ → **400 Bad Request**.
- HTTP method không được hỗ trợ → thường **405 Method Not Allowed**.
- `Content-Type` hoặc `Accept` không phù hợp → có thể **415** hoặc **406**.
- Xung đột trạng thái nghiệp vụ → có thể **409 Conflict**.
- Lỗi hạ tầng không mong đợi → **500 Internal Server Error**, không lộ thông tin nội bộ.

Không nên viết `try/catch` lớn trong từng endpoint chỉ để ghép một chuỗi JSON lỗi. Thay vào đó, có thể cho service ném exception có ý nghĩa, dùng các exception handler để biến exception thành HTTP status, headers và body **nhất quán**.

Mô hình điển hình:

~~~text
HTTP request
     |
     v
Servlet filter chain (có thể gồm Spring Security)
     |
     v
DispatcherServlet
     |
     +-- HandlerMapping -> Controller -> Service
     |                           |
     |                           +-- trả kết quả thành công
     |                           |
     |                           +-- ném exception
     |
     +-- HandlerExceptionResolver chain
              |
              +-- @ExceptionHandler cục bộ?
              +-- @ExceptionHandler trong @ControllerAdvice?
              +-- @ResponseStatus / ResponseStatusException?
              +-- default resolver của Spring MVC?
              |
              v
        HTTP status + headers + error body/view
~~~

Sơ đồ mang tính khái quát: `@ExceptionHandler` được tìm qua `ExceptionHandlerExceptionResolver`; các resolver có thứ tự và điều kiện riêng. Nếu không xử lý được, lỗi có thể đi đến cơ chế error dispatch của Servlet container và Spring Boot `/error`.

Điểm quan trọng: **ngoại lệ là sự kiện trong Java; HTTP status là hợp đồng với client**. Spring không luôn biết mọi custom exception tương ứng mã HTTP nào. Ứng dụng cần ánh xạ có chủ đích, đồng thời không vô tình đổi lỗi lập trình thành response 200.

## 2. Ba annotation khác nhau như thế nào?

| Thành phần | Đặt ở đâu? | Phạm vi | Dùng cho |
|---|---|---|---|
| `@ExceptionHandler` | Trên một method trong `@Controller` hoặc advice | Xử lý các exception type phù hợp | Tạo HTTP response/view khi exception xuất hiện |
| `@ControllerAdvice` | Trên class Spring bean | Dùng chung nhiều controller, có thể giới hạn phạm vi | `@ExceptionHandler`, `@InitBinder`, `@ModelAttribute` |
| `@RestControllerAdvice` | Trên class Spring bean | Giống `@ControllerAdvice`, với response-body semantics | Global JSON/REST exception handling |

**`@RestControllerAdvice` = `@ControllerAdvice` + `@ResponseBody`** theo cơ chế meta-annotation. Nó không làm `@ExceptionHandler` trở nên ưu tiên hơn `@ControllerAdvice`; khác biệt chính là cách mặc định chuyển giá trị trả về thành HTTP response body thay vì để Spring MVC xử lý như một view.

Ví dụ so sánh nhanh:

~~~java
// Fragment trong một REST controller:
@ExceptionHandler(BookNotFoundException.class)
public ResponseEntity<String> notFound(
        BookNotFoundException exception) {
    return ResponseEntity.status(404).body("Book not found");
}
~~~

Đặt trong controller, handler trên chỉ phục vụ controller đó (và kế thừa class liên quan). Đặt trong một advice, handler có thể phục vụ nhiều controller.

### 2.1. @ExceptionHandler xác định exception như thế nào?

Spring có thể suy ra loại exception từ tham số method:

~~~java
@ExceptionHandler(BookNotFoundException.class)
public ResponseEntity<String> handle(
        BookNotFoundException exception) {
    return ResponseEntity.status(404).body("Not found");
}
~~~

Có thể khai báo một hoặc nhiều exception classes trong annotation, nhưng để rõ ràng nên dùng **một handler cho một loại lỗi nghiệp vụ chính**, nhất là khi lỗi có HTTP status khác nhau.

Các tham số hợp lệ của handler MVC gồm exception tương ứng, `HttpServletRequest`, `HttpServletResponse`, `WebRequest`, `Locale` và một số MVC types khác. Những tham số có thể dùng thực tế tùy cơ chế dispatch. Return type thường là `ResponseEntity<?>`, `ProblemDetail`, một DTO lỗi, `ModelAndView` hoặc tên view có chủ đích.

**Không viết một `@ExceptionHandler(Exception.class)` rồi luôn trả 400:** nhiều lỗi hệ thống nghiêm trọng cần trả 500 và log để vận hành.

### 2.2. @ControllerAdvice áp dụng vào controller nào?

Mặc định advice có thể áp dụng rộng trên các controller trong Spring context. Nếu cần giới hạn, các selector có thể bao gồm:

~~~java
@RestControllerAdvice(
    basePackageClasses = BookController.class
)
class BookAreaAdvice {
    // Handler cho những controller phù hợp selector.
}
~~~

Đây chỉ là **fragment minh họa**, không đặt cạnh `ApiExceptionAdvice` của project mẫu nếu hai advice cùng đăng ký handler cho một exception mà không có chiến lược rõ ràng. `basePackageClasses` mạnh hơn tên package viết bằng String về khả năng refactor; ngoài ra có `basePackages`, `annotations` và `assignableTypes`.

Selector giúp tổ chức nhiều nhóm API nhưng không phải cơ chế bảo mật hoặc isolate hoàn toàn mọi exception. Khi thêm advice mới phải kiểm tra phạm vi thực tế và thứ tự.

### 2.3. @RestControllerAdvice không tự nhận mọi lỗi toàn hệ thống

Annotation này không đồng nghĩa “bắt mọi exception ở mọi nơi”. Exception từ Servlet `Filter` trước khi vào `DispatcherServlet`, một scheduled task hoặc code async chạy sau khi response đã commit có thể cần cơ chế khác. Spring Security có `AuthenticationEntryPoint` và `AccessDeniedHandler` để tạo response 401/403 phù hợp. MVC advice thường phục vụ exception đi qua hệ thống exception handling của MVC.

## 3. Thứ tự ưu tiên: local trước global

Khi một controller có handler riêng cho exception, handler **cục bộ** được xem xét trước global `@ControllerAdvice`. Điều này hữu ích nếu một API có quy tắc lỗi riêng, còn những lỗi phổ biến đi qua advice.

Ví dụ cùng một exception type:

~~~java
@RestController
class ExampleController {

    @GetMapping("/example")
    public String example() {
        throw new IllegalArgumentException("Invalid input");
    }

    @ExceptionHandler(IllegalArgumentException.class)
    public ResponseEntity<String> local(
            IllegalArgumentException ex) {
        return ResponseEntity.badRequest()
                .body("Handled by this controller");
    }
}
~~~

Nếu đồng thời có global advice xử lý `IllegalArgumentException`, handler trong `ExampleController` thường được ưu tiên cho exception do chính controller đó ném.

**Đừng đặt local handler rộng quá mức.** Ví dụ `@ExceptionHandler(Exception.class)` trong controller có thể bắt cả những lỗi mà global advice lẽ ra xử lý tốt hơn.

### 3.1. Nhiều advice: @Order và Ordered

Các advice được sắp xếp theo quy tắc `Ordered` / `@Order`. Thông thường **giá trị nhỏ hơn có độ ưu tiên cao hơn**, ví dụ:

~~~java
@RestControllerAdvice
@Order(0)
class PrimaryAdvice {
    // Các handler quan trọng, cụ thể.
}
~~~

~~~java
@RestControllerAdvice
@Order(100)
class FallbackAdvice {
    // Các handler dự phòng.
}
~~~

Đây là **hai class fragment** để minh họa thứ tự, không nằm trong project runnable. Các bean advice còn có caveat về `Ordered`, `PriorityOrdered`, bean scope và các selector khác nhau. `@Order` không nên được dùng để che giấu việc nhiều advice cạnh tranh cùng exception; nếu có thể hãy phân tách rõ phạm vi hoặc loại exception.

**Nuance về exception cause:** Trong *cùng một advice*, handler khớp exception gốc (root) nhìn chung được ưu tiên so với handler khớp exception nguyên nhân (cause). Nhưng giữa **hai advice có priority khác nhau**, một handler chỉ khớp cause trong advice ưu tiên cao có thể được chọn **trước** handler khớp root trong advice ưu tiên thấp. Vì vậy, khai báo primary root mappings trong advice được ưu tiên phù hợp và viết tests cho wrapper exceptions.

### 3.2. Đừng đăng ký handler mơ hồ

Hai method handler cùng phù hợp với cùng exception trong **một advice/controller** có thể gây ambiguity khi Spring xây dựng exception resolver mapping.

Ví dụ **không nên**:

~~~java
// Trong cùng class, hai handler đều nhắm tới cùng lỗi:
@ExceptionHandler(IllegalArgumentException.class)
public String a(IllegalArgumentException ex) { return "a"; }

@ExceptionHandler(IllegalArgumentException.class)
public String b(IllegalArgumentException ex) { return "b"; }
~~~

Đây là đoạn minh họa lỗi, không đặt vào project chạy. Chọn một handler rõ ràng, hoặc dùng exception subclasses có mục đích riêng.

## 4. Spring MVC dùng HandlerExceptionResolver như thế nào?

Các thành phần phổ biến:

| Resolver | Trách nhiệm |
|---|---|
| `ExceptionHandlerExceptionResolver` | Tìm và gọi method `@ExceptionHandler` local/advice |
| `ResponseStatusExceptionResolver` | Xử lý `@ResponseStatus`, `ResponseStatusException` và mapping liên quan |
| `DefaultHandlerExceptionResolver` | Xử lý nhiều exception chuẩn của Spring MVC thành HTTP status phù hợp |
| `SimpleMappingExceptionResolver` | Dùng exception-to-view mapping trong ứng dụng MVC render HTML, khi cấu hình |

Những thành phần này thuộc chuỗi `HandlerExceptionResolver` của `DispatcherServlet`. Một resolver có thể xử lý và tạo response; nếu không xử lý được, resolver khác được xét tùy cấu hình.

Spring Boot còn có cơ chế error MVC như `BasicErrorController`, `ErrorAttributes` và error page. Đó **không phải** là một `@RestControllerAdvice` tự động với cùng phạm vi. Kết quả có thể phụ thuộc `Accept`, cấu hình error handling và việc exception được xử lý ở bước nào.

### 4.1. @ResponseStatus và ResponseStatusException

Ngoài advice, có thể khai báo:

~~~java
@ResponseStatus(HttpStatus.NOT_FOUND)
public class ProductNotFoundException extends RuntimeException {
}
~~~

Đoạn class trên là **fragment minh họa** cần imports; nó không nằm trong project mẫu. Annotation liên kết exception với một HTTP status thông dụng.

Trong handler:

~~~java
throw new ResponseStatusException(
        HttpStatus.NOT_FOUND, "Resource not found");
~~~

`ResponseStatusException` phù hợp cho một lỗi đơn giản tại một điểm. Với nhiều API cần error contract nhất quán, logging, i18n và validation fields, advice dùng chung thường dễ kiểm soát hơn.

Một `@ExceptionHandler` phù hợp có thể xử lý exception trước resolver chỉ chuyên đọc `@ResponseStatus`. Do đó, khi trộn `@ResponseStatus` trên exception và global advice, phải kiểm tra response cuối cùng thay vì giả định hai cấu hình độc lập.

## 5. Dùng RFC 9457 ProblemDetail cho REST API

Spring Framework 6.2 hỗ trợ `org.springframework.http.ProblemDetail` theo **RFC 9457** (Problem Details for HTTP APIs). Một response lỗi phổ biến:

~~~http
HTTP/1.1 404 Not Found
Content-Type: application/problem+json
~~~

Body minh họa:

~~~json
{
  "type": "about:blank",
  "title": "Book not found",
  "status": 404,
  "detail": "No book with id 7",
  "instance": "/api/books/7"
}
~~~

Các trường chính:

- `type`: định danh loại vấn đề; `about:blank` là giá trị mặc định khi không có URI loại lỗi riêng.
- `title`: tên lỗi ngắn, ổn định.
- `status`: mã HTTP được khai trong problem detail; phải nhất quán với actual HTTP status.
- `detail`: lời giải thích an toàn dành cho client, không phải raw stack trace.
- `instance`: URI tham chiếu request/lỗi cụ thể; Framework có thể tự bổ sung path nếu chưa đặt.

`ProblemDetail.forStatusAndDetail(HttpStatus.NOT_FOUND, "No book with id 7")` tạo object lỗi, sau đó có thể `setTitle`, `setType`, `setInstance` hoặc `setProperty`. `ResponseEntity<ProblemDetail>` cho phép đặt status và headers tường minh.

Ví dụ:

~~~java
ProblemDetail body = ProblemDetail.forStatusAndDetail(
        HttpStatus.NOT_FOUND, "Book is missing");

body.setTitle("Book not found");
body.setProperty("errorCode", "BOOK_NOT_FOUND");

return ResponseEntity.status(HttpStatus.NOT_FOUND).body(body);
~~~

Đây là **method body fragment**, không phải Java file độc lập. Với Jackson converter trong MVC, những thuộc tính tùy chỉnh từ `ProblemDetail#setProperty` có thể xuất hiện như các trường JSON top-level; không tự đặt `errorCode` làm lý do phân quyền.

**Không đưa `exception.getMessage()` vào public detail một cách máy móc.** Message từ SQL, filesystem, secret-bearing dependency hoặc framework có thể lộ dữ liệu nội bộ. Hãy tạo client-safe message có chủ đích và log nguyên nhân nội bộ trên server với correlation ID.

### 5.1. Khi nào dùng DTO lỗi riêng?

Nếu contract API đã có DTO lỗi ổn định, ví dụ `ApiError(code, message, traceId)`, bạn có thể trả `ResponseEntity<ApiError>`. Không bắt buộc mọi ứng dụng dùng `ProblemDetail`. Nhưng nếu chọn RFC 9457, nên nhất quán status, media type và cấu trúc cho các endpoint.

Tránh một API trả HTML error page, endpoint khác trả JSON tùy biến, endpoint thứ ba trả empty body mà không có lý do. Client cần biết rõ khi nào parse `application/problem+json`, còn backend cần tránh lộ stack trace.

## 6. ResponseEntityExceptionHandler giúp xử lý lỗi framework

Spring MVC có nhiều exception do framework tự ném, không xuất phát từ business service:

| Exception | Tình huống thường gặp | HTTP status thông dụng |
|---|---|---|
| `MethodArgumentNotValidException` | `@Valid @RequestBody` không hợp lệ | 400 |
| `HandlerMethodValidationException` | Method parameter validation của controller | Thường 400 cho input; output validation có thể 500 |
| `HttpMessageNotReadableException` | JSON body hỏng hoặc không parse được | 400 |
| `MissingServletRequestParameterException` | Thiếu tham số bắt buộc | 400 |
| `MethodArgumentTypeMismatchException` | Path/query value không đổi được sang type | 400 |
| `HttpRequestMethodNotSupportedException` | HTTP method không hỗ trợ | 405 |
| `HttpMediaTypeNotSupportedException` | `Content-Type` không phù hợp | 415 |
| `HttpMediaTypeNotAcceptableException` | Không thể đáp ứng `Accept` | 406 |
| `NoResourceFoundException` | Static resource không tìm thấy trong mapping | 404 |
| `NoHandlerFoundException` | Không có handler phù hợp trong cấu hình phát sinh exception | 404 |
| `MaxUploadSizeExceededException` | Multipart upload quá hạn mức | Thường 413 khi được ánh xạ thích hợp |

Không nên tự viết `@ExceptionHandler` riêng cho **tất cả** framework exceptions nếu `ResponseEntityExceptionHandler` đã có cơ chế xử lý. Có thể kế thừa class này trong `@ControllerAdvice` / `@RestControllerAdvice` và override đúng điểm cần tùy chỉnh.

Lưu ý: `ResponseEntityExceptionHandler` đã có method `@ExceptionHandler` xử lý nhiều exception chuẩn, rồi phân nhánh đến những phương thức protected như `handleMethodArgumentNotValid` hoặc `handleHttpMessageNotReadable`. Nếu subclass khai báo một **method @ExceptionHandler khác cho cùng một framework exception**, có thể tạo ambiguous exception mapping. Thường **override phương thức protected** thay vì khai báo handler cạnh tranh.

Ví dụ chữ ký đúng của Spring Framework 6.2:

~~~java
@Override
protected ResponseEntity<Object> handleMethodArgumentNotValid(
        MethodArgumentNotValidException ex,
        HttpHeaders headers,
        HttpStatusCode status,
        WebRequest request) {

    ProblemDetail body = ProblemDetail.forStatus(status);
    body.setTitle("Validation failed");
    return handleExceptionInternal(
            ex, body, headers, status, request);
}
~~~

Đây là **method fragment** bên trong class extends `ResponseEntityExceptionHandler`, không phải file độc lập; imports nằm trong project đầy đủ bên dưới. Không cần gắn `@ExceptionHandler(MethodArgumentNotValidException.class)` thêm vào method override.

## 7. Project Spring Boot hoàn chỉnh: local handler, global advice và Bean Validation

Chúng ta tạo **một REST app** có các hành vi xác định:

| Request | Mục đích | Kết quả dự kiến |
|---|---|---|
| `GET /api/books/42` | Sách tồn tại | 200 + BookView JSON |
| `GET /api/books/7` | Không tồn tại | 404 + ProblemDetail từ global advice |
| `GET /api/books/0` | ID không hợp lệ | 400 + ProblemDetail từ **local @ExceptionHandler** |
| `POST /api/books` với title hợp lệ | Tạo sách mô phỏng | 201 + BookView JSON |
| `POST /api/books` với title rỗng | `@NotBlank` fail | 400 + ProblemDetail với `invalidFields` |
| `POST /api/books` với JSON sai | Parsing fail | 400 qua framework exception handling |

Ví dụ không có database; id `42` được coi là có sẵn để kết quả có thể dự đoán. Phần tạo mới chỉ trả DTO, không thực sự persist.

### 7.1. Cấu trúc thư mục

~~~text
spring-mvc-exceptions/
  pom.xml
  src/main/resources/application.properties
  src/main/java/com/example/errors/
    ErrorHandlingApplication.java
    BookNotFoundException.java
    BookController.java
    ApiExceptionAdvice.java
  src/test/java/com/example/errors/
    BookErrorHandlingTest.java
~~~

### 7.2. pom.xml — cần starter-validation

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>spring-mvc-exceptions</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-validation</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`spring-boot-starter-validation` được thêm riêng để `@Valid` kết hợp `@NotBlank` chạy như dự kiến. Với các Boot starter hiện đại, **không mặc định** starter Web đã mang Bean Validation provider.

`src/main/resources/application.properties`:

~~~properties
server.port=8080

# Không tự để lộ exception message/stack trace trong Boot error body:
server.error.include-message=never
server.error.include-stacktrace=never
~~~

Các property thuộc **Boot error handling fallback**; chúng không thay nội dung mà bạn tự tạo trong `@ExceptionHandler`. Nếu handler tự copy stack trace vào ProblemDetail, những property này không thể bảo vệ.

### 7.3. Application entry point

`src/main/java/com/example/errors/ErrorHandlingApplication.java`:

~~~java
package com.example.errors;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ErrorHandlingApplication {

    public static void main(String[] args) {
        SpringApplication.run(ErrorHandlingApplication.class, args);
    }
}
~~~

### 7.4. Custom exception nghiệp vụ

`src/main/java/com/example/errors/BookNotFoundException.java`:

~~~java
package com.example.errors;

public class BookNotFoundException extends RuntimeException {

    private final long bookId;

    public BookNotFoundException(long bookId) {
        super("Book does not exist: " + bookId);
        this.bookId = bookId;
    }

    public long getBookId() {
        return bookId;
    }
}
~~~

Việc ném `BookNotFoundException` tự nó chưa bắt Spring trả 404. Trạng thái 404 của demo đến từ **global @ExceptionHandler** ở mục 7.6. Message trong exception có thể dùng để log nội bộ; public response sẽ xây dựng detail riêng theo hợp đồng API.

### 7.5. Controller có local @ExceptionHandler

`src/main/java/com/example/errors/BookController.java`:

~~~java
package com.example.errors;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;

import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/books")
public class BookController {

    @GetMapping("/{id}")
    public BookView find(@PathVariable long id) {
        if (id <= 0) {
            throw new IllegalArgumentException(
                    "Book id must be positive");
        }

        if (id != 42) {
            throw new BookNotFoundException(id);
        }

        return new BookView(42, "Spring MVC");
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public BookView create(
            @Valid @RequestBody CreateBookRequest request) {
        return new BookView(100, request.title());
    }

    // Local handler: áp dụng cho BookController.
    @ExceptionHandler(IllegalArgumentException.class)
    public ResponseEntity<ProblemDetail> invalidId(
            IllegalArgumentException ex) {

        ProblemDetail body = ProblemDetail.forStatusAndDetail(
                HttpStatus.BAD_REQUEST,
                "Book id must be a positive integer");
        body.setTitle("Invalid book id");

        return ResponseEntity.badRequest().body(body);
    }

    public record BookView(long id, String title) {
    }

    public record CreateBookRequest(
            @NotBlank String title) {
    }
}
~~~

Điểm cần hiểu:

- `GET /api/books/42` trả JSON của `BookView`.
- `GET /api/books/7` ném `BookNotFoundException`; không có local handler cho loại này, nên global advice xử lý.
- `GET /api/books/0` ném `IllegalArgumentException`; method `invalidId` trong chính controller xử lý thành HTTP 400.
- `POST /api/books` dùng `@Valid` + `@NotBlank`; một title `""` hoặc chỉ chứa khoảng trắng làm validation fail.
- `@ResponseStatus(HttpStatus.CREATED)` gắn lên method thành công, không phải lên exception handler.
- Java 17 record là DTO; Jackson converter của Spring Boot đọc/ghi JSON.
- Project dùng một bộ mã cố định để dễ kiểm thử, không đưa DB lỗi thật vào bài.

### 7.6. Global @RestControllerAdvice kế thừa ResponseEntityExceptionHandler

`src/main/java/com/example/errors/ApiExceptionAdvice.java`:

~~~java
package com.example.errors;

import java.util.List;

import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.context.request.WebRequest;
import org.springframework.web.servlet.mvc.method.annotation.ResponseEntityExceptionHandler;

@RestControllerAdvice
@Order(Ordered.HIGHEST_PRECEDENCE)
public class ApiExceptionAdvice
        extends ResponseEntityExceptionHandler {

    @ExceptionHandler(BookNotFoundException.class)
    public ResponseEntity<ProblemDetail> bookNotFound(
            BookNotFoundException ex) {

        ProblemDetail body = ProblemDetail.forStatusAndDetail(
                HttpStatus.NOT_FOUND,
                "No book with id " + ex.getBookId());
        body.setTitle("Book not found");
        body.setProperty("errorCode", "BOOK_NOT_FOUND");

        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .body(body);
    }

    @Override
    protected ResponseEntity<Object> handleMethodArgumentNotValid(
            MethodArgumentNotValidException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        List<String> fields = ex.getBindingResult()
                .getFieldErrors()
                .stream()
                .map(error -> error.getField())
                .distinct()
                .sorted()
                .toList();

        ProblemDetail body = ProblemDetail.forStatusAndDetail(
                HttpStatus.BAD_REQUEST,
                "Request body failed Bean Validation");
        body.setTitle("Validation failed");
        body.setProperty("invalidFields", fields);

        return handleExceptionInternal(
                ex, body, headers, status, request);
    }
}
~~~

**Vì sao class này hoạt động:**

1. `@RestControllerAdvice` tạo advice bean trên package được component-scan.
2. `@ExceptionHandler(BookNotFoundException.class)` chuyển lỗi nghiệp vụ thành HTTP 404 với `ProblemDetail`.
3. `ResponseEntityExceptionHandler` được Spring Framework dùng để xử lý nhiều lỗi MVC như invalid request body, unsupported method và malformed JSON.
4. `handleMethodArgumentNotValid` override đúng hook cho `@Valid @RequestBody` thất bại, thêm field `invalidFields` vào ProblemDetail.
5. Không gắn `@ExceptionHandler(MethodArgumentNotValidException.class)` vào override để tránh mapping trùng với exception handling method kế thừa từ base class.
6. `@Order(Ordered.HIGHEST_PRECEDENCE)` thể hiện ý định ưu tiên advice này nếu còn các global advice khác; **local handler của BookController vẫn được ưu tiên** trong MVC exception resolution.
7. `handleExceptionInternal` giữ các headers và HTTP status mà framework đã xác định, phù hợp hơn tự dựng response thô cho mọi lỗi.
8. `invalidFields` chỉ chứa tên trường, không đưa nguyên giá trị người dùng gửi hoặc object validation nội bộ vào public detail.

Không nên thêm một generic `@ExceptionHandler(Exception.class)` vào class này chỉ để “đảm bảo mọi lỗi đều thành JSON 400”. Nếu cần 500 fallback, phải log lỗi nội bộ, trả nội dung an toàn và bảo đảm không ảnh hưởng đến xử lý của Spring Security/filter layer.

## 8. Chạy ứng dụng và quan sát HTTP response

Từ thư mục chứa `pom.xml`:

~~~bash
mvn spring-boot:run
~~~

Hoặc đóng gói:

~~~bash
mvn clean package
java -jar target/spring-mvc-exceptions-1.0.0.jar
~~~

Ví dụ bên dưới giả định ứng dụng chạy tại `http://localhost:8080`.

### 8.1. GET thành công

~~~bash
curl -i http://localhost:8080/api/books/42
~~~

HTTP status `200` và JSON body:

~~~json
{"id":42,"title":"Spring MVC"}
~~~

### 8.2. Lỗi nghiệp vụ: global advice trả 404

~~~bash
curl -i http://localhost:8080/api/books/7
~~~

HTTP status `404` và body có các trường:

~~~json
{
  "type": "about:blank",
  "title": "Book not found",
  "status": 404,
  "detail": "No book with id 7",
  "instance": "/api/books/7",
  "errorCode": "BOOK_NOT_FOUND"
}
~~~

Spring Framework có thể bổ sung `instance` bằng request path. Thứ tự key, spacing và một số headers do converter quyết định; đây là **JSON cấu trúc mong đợi**, không phải cam kết bytes response nguyên văn.

### 8.3. Lỗi dữ liệu: local @ExceptionHandler trả 400

~~~bash
curl -i http://localhost:8080/api/books/0
~~~

Body có `title="Invalid book id"`, `detail="Book id must be a positive integer"` và `status=400`. Đây là local handler của controller, không phải global `BookNotFoundException` handler.

### 8.4. POST hợp lệ

~~~bash
curl -i -X POST http://localhost:8080/api/books \
  -H "Content-Type: application/json" \
  -d '{"title":"Exception Handling"}'
~~~

Trả HTTP `201 Created` và:

~~~json
{"id":100,"title":"Exception Handling"}
~~~

### 8.5. POST không hợp lệ

~~~bash
curl -i -X POST http://localhost:8080/api/books \
  -H "Content-Type: application/json" \
  -d '{"title":""}'
~~~

Trả HTTP `400 Bad Request`. Body ProblemDetail chứa:

~~~json
{
  "type": "about:blank",
  "title": "Validation failed",
  "status": 400,
  "detail": "Request body failed Bean Validation",
  "invalidFields": ["title"]
}
~~~

Framework có thể bổ sung `instance`; ví dụ trên tập trung vào các trường do ứng dụng kiểm soát.

### 8.6. JSON hỏng

~~~bash
curl -i -X POST http://localhost:8080/api/books \
  -H "Content-Type: application/json" \
  -d '{"title":'
~~~

JSON không parse được nên Spring MVC tạo `HttpMessageNotReadableException`. `ResponseEntityExceptionHandler` đã hỗ trợ lỗi framework này; request trả HTTP **400**. Không kỳ vọng body giống hệt custom validation error vì đây là **lỗi parse**, không phải `@NotBlank`.

**Lưu ý shell:** các ví dụ `curl` nhiều dòng dùng cú pháp Bash. Trong PowerShell có thể dùng `curl.exe` và quoting phù hợp hoặc tách thành một dòng. Không nhất thiết nhìn thấy cùng status/body khi dự án bổ sung Spring Security, filter, custom content negotiation hoặc proxy.

## 9. Kiểm thử tự động: xác minh local, global và framework exception

Tạo `src/test/java/com/example/errors/BookErrorHandlingTest.java`:

~~~java
package com.example.errors;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class BookErrorHandlingTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void existingBookReturns200() throws Exception {
        mvc.perform(get("/api/books/42"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value(42))
            .andExpect(jsonPath("$.title").value("Spring MVC"));
    }

    @Test
    void localExceptionHandlerReturns400() throws Exception {
        mvc.perform(get("/api/books/0"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.title")
                    .value("Invalid book id"))
            .andExpect(jsonPath("$.status").value(400))
            .andExpect(jsonPath("$.detail")
                    .value("Book id must be a positive integer"));
    }

    @Test
    void globalAdviceReturns404() throws Exception {
        mvc.perform(get("/api/books/7"))
            .andExpect(status().isNotFound())
            .andExpect(content().contentTypeCompatibleWith(
                    MediaType.APPLICATION_PROBLEM_JSON))
            .andExpect(jsonPath("$.title")
                    .value("Book not found"))
            .andExpect(jsonPath("$.errorCode")
                    .value("BOOK_NOT_FOUND"))
            .andExpect(jsonPath("$.status").value(404));
    }

    @Test
    void beanValidationReturns400AndInvalidFields()
            throws Exception {
        mvc.perform(post("/api/books")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"title\":\"\"}"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.title")
                    .value("Validation failed"))
            .andExpect(jsonPath("$.invalidFields[0]")
                    .value("title"));
    }

    @Test
    void validPostReturns201() throws Exception {
        mvc.perform(post("/api/books")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"title\":\"New book\"}"))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.id").value(100))
            .andExpect(jsonPath("$.title").value("New book"));
    }

    @Test
    void malformedJsonIsRejectedAs400() throws Exception {
        mvc.perform(post("/api/books")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"title\":"))
            .andExpect(status().isBadRequest());
    }
}
~~~

Chạy:

~~~bash
mvn test
~~~

Bộ test kiểm chứng:

- Bình thường MVC trả đúng HTTP 200 và DTO.
- Local handler trong controller trả 400 và có title/detail như thiết kế.
- Global advice bắt exception nghiệp vụ 404 và trả `application/problem+json`.
- `@Valid`/`@NotBlank` ném exception framework, được advice override thành body có `invalidFields`.
- Parse JSON lỗi được framework xử lý thành 400.
- Request thành công khác vẫn trả 201, không bị global handler làm ảnh hưởng.

**Giới hạn:** `MockMvc` kiểm thử MVC dispatch trong Spring context nhưng không mở HTTP socket thật. Nếu cần xác minh Servlet container, reverse proxy, filter chain hạ tầng, forwarded headers hoặc error dispatch thật, dùng `@SpringBootTest(webEnvironment = RANDOM_PORT)` và HTTP client để kiểm thử thêm.

## 10. Xử lý lỗi trong @ControllerAdvice và @RestControllerAdvice

### 10.1. Khi ứng dụng render HTML view

Một ứng dụng MVC có template Thymeleaf có thể dùng `@ControllerAdvice` để trả view name:

~~~java
@ControllerAdvice
public class HtmlErrorAdvice {

    @ExceptionHandler(ProductNotFoundException.class)
    public String showNotFound(
            ProductNotFoundException ex,
            Model model) {

        model.addAttribute("message", "Product not found");
        return "errors/not-found";
    }
}
~~~

Đây là **fragment độc lập về ý tưởng**, chưa có `ProductNotFoundException`/template/imports và không nằm trong app REST ở mục 7. Nếu ứng dụng có template `errors/not-found.html` thì return String có thể được coi là tên view. Cùng method nếu đặt trong `@RestControllerAdvice` thường sẽ được hiểu là response body string, không phải view.

### 10.2. Khi API cần JSON

Với REST API, cách dễ hiểu hơn là:

~~~java
@RestControllerAdvice
public class JsonErrorAdvice {

    @ExceptionHandler(ProductNotFoundException.class)
    public ResponseEntity<ProblemDetail> notFound(
            ProductNotFoundException ex) {

        ProblemDetail body = ProblemDetail.forStatus(
                HttpStatus.NOT_FOUND);
        body.setTitle("Product not found");

        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .body(body);
    }
}
~~~

Đây là **fragment minh họa**; không tạo class này trong project `com.example.errors` ở mục 7 vì sẽ cần thêm exception type và có thể làm trùng error strategy.

`@ControllerAdvice` cũng có thể trả JSON nếu handler được gắn `@ResponseBody` hoặc trả `ResponseEntity`. `@RestControllerAdvice` đơn giản hóa semantics cho đa số REST error handlers, chứ không có khả năng xử lý exception “mạnh hơn”.

## 11. Quy tắc mapping lỗi HTTP hợp lý

Trước khi chọn HTTP status, xác định **bản chất lỗi**:

| Tình huống | Lựa chọn thường dùng | Ghi chú |
|---|---|---|
| Client gửi JSON body không đọc được | 400 | Không lộ parser stacktrace |
| Thiếu trường bắt buộc, Bean Validation fail | 400 | Có thể trả tên trường an toàn |
| Resource không tồn tại | 404 | Có thể tránh leak thông tin tồn tại resource nếu cần security |
| Resource có xung đột state/version | 409 | Tùy contract nghiệp vụ |
| Không được xác thực | 401 | Dùng auth entry point khi thuộc Spring Security |
| Đã xác thực nhưng không đủ quyền | 403 | Đừng lấy role từ header tự khai |
| Request vượt size limit | 413 | Tùy container/proxy và exception mapping |
| HTTP method không được hỗ trợ | 405 | Giữ header `Allow` nếu framework tạo |
| Request Content-Type sai | 415 | Giữ semantics content negotiation |
| Response không đáp ứng Accept | 406 | Không trả JSON vô điều kiện nếu client không chấp nhận |
| Lỗi lập trình hoặc dependency bên trong | 500 | Log nội bộ, trả thông điệp chung |

**Không bắt toàn bộ lỗi và trả 200 với `{"success":false}`**: điều đó phá HTTP semantics, monitoring, retry behavior và cache policies. Cũng không trả 404 cho mọi lỗi backend: hệ thống vận hành cần phân biệt resource missing với database outage.

### 11.1. Giữ lại HTTP headers có ý nghĩa

Các framework exceptions có thể mang headers cần giữ, ví dụ `Allow` cho 405 hoặc thông tin media type. Khi override `ResponseEntityExceptionHandler`, dùng `headers` do Spring cung cấp và `handleExceptionInternal` để tránh vô tình bỏ các headers đó.

Với rate limiting có thể cần `Retry-After` cho một số response. Với authentication, `WWW-Authenticate` cần đi đúng cơ chế security. Việc trả “JSON đẹp” không phải lý do để xóa những header chuẩn này.

## 12. Validation exceptions không chỉ có một loại

### 12.1. @Valid @RequestBody

Trong ứng dụng Spring MVC với Bean Validation provider, `@Valid @RequestBody` thường gây `MethodArgumentNotValidException` khi dữ liệu body bind được nhưng constraint fail. Ví dụ `title=""` vi phạm `@NotBlank`.

### 12.2. Method parameter validation

Nếu controller có constraint trực tiếp trên method parameters, Spring Framework 6.1+ có cơ chế method validation với `HandlerMethodValidationException`. Không nên mặc định mọi `@NotBlank`/`@Min` đều xuất hiện dưới `MethodArgumentNotValidException`.

### 12.3. JSON parse khác validation

Body `{"title":` không phải lỗi `@NotBlank`; parser không tạo được DTO nên có thể ném `HttpMessageNotReadableException`, trước bước Bean Validation.

Nếu bạn cần error contract chung, hãy viết test cho **từng lớp**: parse lỗi, convert kiểu lỗi, validation field lỗi, method validation lỗi và business validation lỗi. Giữ detail không lộ giá trị nhạy cảm.

## 13. Những lỗi thường gặp khi viết @ExceptionHandler

| Hiện tượng | Nguyên nhân thường gặp | Cách khắc phục |
|---|---|---|
| Custom exception trả 500 thay vì 404 | Chưa có handler hoặc `@ResponseStatus` phù hợp | Thêm `@ExceptionHandler`/`ResponseStatusException` đúng phạm vi |
| Handler global không chạy | Advice ngoài component scan hoặc selector không match | Kiểm tra package, bean và `@RestControllerAdvice` |
| Local handler chạy thay global | Local có ưu tiên trong MVC | Chỉ giữ local cho lỗi đặc thù; test đúng ý định |
| App startup lỗi ambiguous exception mapping | Hai handler cùng bắt một exception trong một class | Gộp hoặc làm rõ mapping |
| Lỗi 400 thành 500 | Handler tự ném exception hoặc mapping sai | Kiểm tra stack server, viết test cho error handler |
| @Valid không chạy | Thiếu provider/dependency hoặc annotation không áp dụng đúng | Dùng starter validation, kiểm tra argument |
| JSON malformed không vào handler validation | Đây là lỗi parse, không phải Bean Validation | Dùng `ResponseEntityExceptionHandler`/hook phù hợp |
| `@ControllerAdvice` trả text view thay vì JSON | Method trả String và không có response-body semantics | Dùng `@RestControllerAdvice`, `@ResponseBody` hoặc `ResponseEntity` |
| HTTP body trả nội dung nhạy cảm | Copy raw exception message/stacktrace | Client-safe detail, log nội bộ |
| Security 401/403 không vào MVC advice | Spring Security xử lý ở filter layer | Cấu hình `AuthenticationEntryPoint`, `AccessDeniedHandler` |
| Lỗi filter trước servlet không vào advice | Chưa đến `DispatcherServlet` | Xử lý tại filter/security/container phù hợp |
| @ExceptionHandler không sửa được lỗi sau response commit | Status/headers đã gửi | Thiết kế async/streaming error path và observability |
| Response 405 mất Allow header | Tự dựng ResponseEntity bỏ qua headers framework | Dùng `handleExceptionInternal` hoặc giữ headers |
| Hai advice ưu tiên lạ | `@Order`, `Ordered`, selector, cause matching | Test thứ tự và phân rõ ownership |
| API có cả HTML và JSON error | Content negotiation/fallback khác nhau | Thiết kế và test theo `Accept` |

### 13.1. Catch-all exception handler không phải phương án mặc định

Một global handler `@ExceptionHandler(Exception.class)` có thể hữu ích cho fallback 500, nhưng rất dễ che khuất lỗi đã có handler chuyên biệt. Nếu có dùng, bảo đảm:

1. Chỉ trả **500** cho lỗi chưa phân loại, không biến mọi exception thành 400.
2. Log server-side ở mức thích hợp, có correlation ID, không log secrets.
3. Không gửi raw exception messages/SQL/query params nhạy cảm.
4. Không phá cơ chế 401/403/405/415, kể cả headers liên quan.
5. Test cả lỗi nội bộ, lỗi client và hành vi Security.

Không phải mọi lỗi phát sinh từ background thread đều đi qua MVC exception resolver; cần handling ở chính executor/message listener đó.

### 13.2. Tránh gọi trực tiếp exception handler trong service

Service nên biểu đạt lỗi nghiệp vụ bằng exception hoặc một kiểu result, không import/controller-invoke `ApiExceptionAdvice` để tạo HTTP response. Điều đó làm business layer phụ thuộc Spring Web và khó tái sử dụng.

Sơ đồ trách nhiệm khuyến nghị:

~~~text
Controller / Router
       |
       v
Application / Domain Service
       |
       +-- ném lỗi nghiệp vụ rõ nghĩa
       |
       v
MVC exception resolution
       |
       v
ApiExceptionAdvice -> HTTP response
~~~

### 13.3. Tránh swallow và trả null

~~~java
// Anti-pattern:
try {
    service.execute();
} catch (Exception ex) {
    return null;
}
~~~

Đoạn này là **fragment** có `service` giả định. Trả `null` có thể khiến client nhận response sai, không có error body/status, và vận hành không còn biết lỗi. Nếu handler không thể giải quyết, cho exception được xử lý bởi tầng phù hợp, hoặc trả error response đã xác định contract.

## 14. Xử lý ngoại lệ với WebFlux và router chức năng

Spring WebFlux dùng `DispatcherHandler`, không phải Servlet `DispatcherServlet`. Dù `@ExceptionHandler` / `@RestControllerAdvice` cũng hỗ trợ cho **annotated controllers WebFlux**, base class, async return types và exception pipeline thuộc **reactive stack**.

| Spring MVC | Spring WebFlux |
|---|---|
| `DispatcherServlet` | `DispatcherHandler` |
| `org.springframework.web.servlet.mvc.method.annotation.ResponseEntityExceptionHandler` | `org.springframework.web.reactive.result.method.annotation.ResponseEntityExceptionHandler` |
| `HttpServletRequest` / `HttpServletResponse` | `ServerWebExchange` |
| `HandlerExceptionResolver` | Reactive exception handling/`WebExceptionHandler` |
| WebMvc.fn handler | WebFlux.fn handler trả `Mono<ServerResponse>` |

Với **WebFlux.fn functional routes**, exceptions có thể được xử lý bằng `RouterFunction` filter, error handlers tại reactive infrastructure hoặc `ErrorWebExceptionHandler` của Boot. Không giả định một `@RestControllerAdvice` viết cho annotated controllers luôn bao phủ mọi lỗi từ functional handlers hay `WebFilter`.

**Không copy nguyên chữ ký override** `handleMethodArgumentNotValid(MethodArgumentNotValidException, HttpHeaders, HttpStatusCode, WebRequest)` từ MVC sang WebFlux: `WebRequest` và các hook base class differ theo stack/version. Đọc Javadoc reactive `ResponseEntityExceptionHandler` của phiên bản dùng trước khi override.

Một controller WebFlux có thể trả `Mono<T>`; nếu bên trong Publisher xảy ra lỗi, reactive error handling cần quản lý cả việc response có thể đã commit. `Mono.onErrorResume` có thể được dùng ở mức pipeline để xử lý lỗi **có chủ đích**, nhưng không nên biến mọi lỗi thành successful 200 response.

## 15. Logging, correlation ID và quốc tế hóa lỗi

### 15.1. Public detail và internal diagnostics

Hai đối tượng phục vụ mục tiêu khác nhau:

- **Client error body:** HTTP status, public error code, detail an toàn, optional trace ID.
- **Server diagnostics:** exception chain, stacktrace, request timing, principal đã xác thực, correlation ID, service dependency và nơi phát sinh.

Không để stacktrace, database credentials, absolute filesystem path, SQL query có secrets hoặc JWT token vào `ProblemDetail.detail`.

### 15.2. Correlation ID không phải authorization

Có thể gắn một request/trace ID được tạo hoặc xác nhận phù hợp vào `ProblemDetail#setProperty("traceId", ...)`. Nhưng nếu ID đến từ `X-Request-Id` client tự khai, nó **không được dùng để cấp quyền** và phải kiểm tra format/length; audit chống giả mạo nên có ID riêng do server sinh.

### 15.3. i18n với MessageSource

Spring Framework hỗ trợ message codes cho một số `ErrorResponse` và `ProblemDetail` thông qua `MessageSource`. Với các lỗi thường gặp, có thể dùng message bundles theo `Locale` để cung cấp title/detail phù hợp ngôn ngữ.

Dù dùng i18n, vẫn giữ **machine-readable errorCode** hoặc `type URI` ổn định; client không nên parse tiếng Anh/tiếng Việt từ detail để quyết định workflow nghiệp vụ.

### 15.4. Type URI là hợp đồng API

Trong `ProblemDetail`, `type` có thể là URI của tài liệu giải thích loại lỗi, ví dụ một trang documentation ổn định của API. Đừng đặt những URI không tồn tại hoặc không thuộc quyền quản lý của tổ chức rồi bắt client phụ thuộc vào đó. Nếu chưa có error type registry, `about:blank` + mã riêng được tài liệu hóa có thể đủ cho lab.

## 16. Checklist kiểm thử trước triển khai

- [ ] Custom exception có HTTP status đúng (400/404/409...), không bị mặc định trả 500 ngoài dự kiến.
- [ ] Local `@ExceptionHandler` chỉ xử lý những lỗi thực sự đặc thù của controller đó.
- [ ] Global `@RestControllerAdvice` được scan và không có duplicate/ambiguous mappings.
- [ ] `@Order` và root/cause matching giữa các advice được test nếu có nhiều advice.
- [ ] Project có `spring-boot-starter-validation` nếu dùng Bean Validation.
- [ ] Lỗi parse JSON, type mismatch, field validation và method validation được kiểm thử riêng.
- [ ] `ResponseEntityExceptionHandler` được override đúng API/phiên bản, không khai báo handler trùng.
- [ ] HTTP status, `Content-Type`, `Allow`, `Retry-After` hoặc `WWW-Authenticate` đúng khi áp dụng.
- [ ] `ProblemDetail` thống nhất, không gửi stacktrace/secrets/private data.
- [ ] Security 401/403 được xử lý đúng ở filter/security boundary.
- [ ] Lỗi filter/async/streaming khi response đã commit được thiết kế riêng.
- [ ] Error contract được kiểm thử cả với `Accept: application/json`, `application/problem+json` và lỗi không có handler.
- [ ] Có test cho trạng thái thành công để bảo đảm advice không làm hỏng response bình thường.
- [ ] Có HTTP integration test trên container thực khi production có proxy/filter đặc thù.
- [ ] Logging và monitoring có correlation ID phục vụ chẩn đoán nhưng không làm lộ dữ liệu nhạy cảm.

## Tài liệu tham khảo chính thức

- [Spring Framework 6.2 — @ExceptionHandler](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-exceptionhandler.html): mapping exception, handler arguments, result types và cause matching.
- [Spring Framework 6.2 — Controller Advice](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-advice.html): scope, @RestControllerAdvice, local trước global.
- [Spring Framework 6.2 — Error Responses](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-ann-rest-exceptions.html): RFC 9457 ProblemDetail, ErrorResponse, ResponseEntityExceptionHandler.
- [Spring Framework 6.2 — ResponseEntityExceptionHandler Javadoc](https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/web/servlet/mvc/method/annotation/ResponseEntityExceptionHandler.html): các phương thức protected có thể override.
- [Spring Framework 6.2 — Controller Advice Javadoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/web/bind/annotation/ControllerAdvice.html): ordering, cause và selectors.
- [Spring Framework 6.2 — WebFlux Error Responses](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/ann-rest-exceptions.html): cơ chế tương đương cho reactive stack.
- [Spring Boot 3.5 — Servlet Web Applications](https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html): Spring MVC và Boot error handling.
- [Spring Boot 3.5 — Spring Boot Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/): `server.error.*` và các tùy chọn liên quan.

**Kết luận:** `@ExceptionHandler` trả lời “ngoại lệ này được biến thành response thế nào”; `@ControllerAdvice` chia sẻ cách xử lý giữa các MVC controllers; `@RestControllerAdvice` đặt mặc định response-body semantics thuận tiện cho REST. Với Spring MVC hiện đại, kết hợp handler cục bộ cho nhu cầu đặc thù, global advice cho lỗi nghiệp vụ và `ResponseEntityExceptionHandler` cho lỗi framework sẽ giúp API có status, ProblemDetail và tests rõ ràng, đồng thời không làm rò rỉ chi tiết nội bộ.
