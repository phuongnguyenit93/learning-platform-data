# @ExceptionHandler, @ControllerAdvice và ResponseEntityExceptionHandler trong Spring MVC

## 1. Vì sao cần một chiến lược phản hồi lỗi nhất quán?

Khi Spring MVC nhận request, lỗi có thể đến từ nhiều tầng:

- **HTTP/argument resolution:** thiếu query parameter, HTTP method không hỗ trợ, không đọc được JSON, chuyển kiểu thất bại.
- **Validation:** object được `@Valid` đánh dấu không hợp lệ hoặc direct constraint trên tham số controller bị vi phạm.
- **Nghiệp vụ:** không tìm thấy đơn đặt hàng, trạng thái không cho phép thay đổi, tài nguyên bị xung đột.
- **Hệ thống:** database lỗi, timeout, bug của code, kết quả controller không thỏa hậu điều kiện.

Nếu mỗi controller tự `try/catch` rồi trả chuỗi bất kỳ, API dễ gặp các lỗi: HTTP 200 dù thao tác thất bại, cấu trúc JSON khác nhau giữa endpoints, lộ stack trace hoặc dữ liệu nhạy cảm và thiếu cơ chế dịch thông điệp.

Spring MVC cung cấp ba công cụ chính:

1. **`@ExceptionHandler`**: khai báo phương thức xử lý một hoặc nhiều loại exception.
2. **`@ControllerAdvice`** (hoặc `@RestControllerAdvice`): đưa exception handlers ra phạm vi nhiều controller, có thể lọc theo package, annotation hoặc kiểu.
3. **`ResponseEntityExceptionHandler`**: lớp cơ sở dành cho global advice, xử lý nhiều lỗi do Spring MVC sinh ra, mặc định dùng cấu trúc **RFC 9457 Problem Details** và có các phương thức `protected` để tùy biến.

**Quy tắc quan trọng:** Nếu kế thừa `ResponseEntityExceptionHandler`, hãy **override đúng method `protected handle...`** cho những exception Spring đã đăng ký trong lớp cơ sở; không thêm một `@ExceptionHandler` thứ hai xử lý cùng exception trong cùng advice rồi gây mapping mơ hồ.

Phạm vi bài là **Spring Framework 6.2 + Spring MVC Servlet stack**, với ví dụ Spring Boot 3.5.6 và Java 17. WebFlux có lớp cùng tên `ResponseEntityExceptionHandler` nhưng thuộc **package khác** và dùng cơ chế reactive; đừng copy nhầm import.

## 2. Tổng quan luồng xử lý exception

Một request qua MVC thường đi theo chuỗi sau:

```text
HTTP request
    |
    v
DispatcherServlet
    |
    +--> argument resolution / body conversion / binding / validation
    |        |
    |        +--> lỗi có thể được ném trước khi vào controller
    |
    v
@Controller / @RestController method
    |
    +--> có thể ném exception nghiệp vụ
    |
    v
HandlerExceptionResolver chain
    |
    +--> ExceptionHandlerExceptionResolver
    |       |-- @ExceptionHandler cục bộ trong controller
    |       |-- @ExceptionHandler từ @ControllerAdvice phù hợp
    |
    +--> ResponseStatusExceptionResolver
    |       |-- @ResponseStatus / ResponseStatusException
    |
    +--> DefaultHandlerExceptionResolver
            |-- ánh xạ một số lỗi Spring MVC về status
    |
    v
HTTP response (status, headers, body)
```

Sơ đồ diễn tả các resolver tiêu biểu và không thay thế việc kiểm tra ordering khi ứng dụng tự thêm `HandlerExceptionResolver`. MVC tự cấu hình một chuỗi resolver; khi một resolver xử lý được exception, các bước sau thường không cần tiếp tục.

Với REST API, xử lý ngoại lệ cần quyết định **cả ba phần**: HTTP status, response headers và response body. Chỉ trả một câu báo lỗi mà giữ status 200 là không đúng hợp đồng.

### 2.1. Exception có thể xảy ra trước handler body

Ví dụ:

```java
@PostMapping("/bookings")
public String create(@Valid @RequestBody BookingRequest request) {
    // ...
    return "CREATED";
}
```

Đây là **đoạn minh họa**, cần DTO `BookingRequest` và các imports. JSON không đọc được có thể tạo `HttpMessageNotReadableException` **trước khi** thân `create` chạy. DTO đọc được nhưng vi phạm constraint thường tạo `MethodArgumentNotValidException` nếu không có `BindingResult` liền kề và không có yếu tố kích hoạt whole-method validation.

Vì vậy, `try/catch` nằm **bên trong thân controller** không xử lý được mọi lỗi đầu vào. Exception handler ở hạ tầng MVC mới bao quát được các lỗi phù hợp.

## 3. @ExceptionHandler: xử lý một exception cụ thể

`@ExceptionHandler` có thể đặt ngay trong controller:

```java
@RestController
public class BookController {

    @GetMapping("/books/{id}")
    public String get(@PathVariable long id) {
        if (id != 7) {
            throw new BookNotFoundException(id);
        }
        return "Book 7";
    }

    @ExceptionHandler(BookNotFoundException.class)
    public ResponseEntity<String> missing(BookNotFoundException ex) {
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .body("Book not found");
    }
}
```

Đây là **đoạn minh họa tích hợp**, chưa có class `BookNotFoundException` và imports. Exception handler cục bộ trên chỉ áp dụng cho controller đó (bao gồm kế thừa class nếu phù hợp). Nó không phải xử lý toàn hệ thống.

### 3.1. Cách chỉ định loại exception

Có hai cách phổ biến:

```java
@ExceptionHandler(BookNotFoundException.class)
ResponseEntity<String> handle(BookNotFoundException ex) {
    // ...
    return ResponseEntity.notFound().build();
}
```

Hoặc để Spring suy ra loại từ argument:

```java
@ExceptionHandler
ResponseEntity<String> handle(BookNotFoundException ex) {
    // ...
    return ResponseEntity.status(404).body("Not found");
}
```

Cả hai là **fragment**, không khai báo cùng lúc để xử lý một loại exception trong cùng controller/advice. Nên khai báo cụ thể và rõ ràng; tránh nhiều handler có mapping chồng chéo khó dự đoán.

Một `@ExceptionHandler` có thể dùng các argument phù hợp với hạ tầng MVC như exception, `WebRequest`, `HttpServletRequest`, `Locale`, và return `ResponseEntity<?>`, `ProblemDetail`, `ModelAndView` hoặc các kiểu return được MVC hỗ trợ. Tuy nhiên không phải mọi argument của một `@RequestMapping` đều dùng y hệt trong exception handler.

### 3.2. Local có ưu tiên hơn global

Khi cùng một exception có thể được xử lý bởi handler trong controller và bởi advice toàn cục, Spring MVC **kiểm tra @ExceptionHandler cục bộ trước** các handlers từ `@ControllerAdvice`.

Điều này hữu ích khi một controller cần thông điệp hoặc chiến lược phục hồi riêng. Nhưng nếu ứng dụng muốn JSON error thống nhất ở mọi endpoint, hãy giữ xử lý có hệ thống trong global advice và chỉ override local khi thật sự có lý do.

## 4. @ControllerAdvice và @RestControllerAdvice: chia sẻ và giới hạn phạm vi

Thay vì sao chép nhiều phương thức vào từng controller:

```java
@RestControllerAdvice
public class ApiErrorAdvice {

    @ExceptionHandler(BookNotFoundException.class)
    ResponseEntity<String> notFound(BookNotFoundException ex) {
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .body("Book not found");
    }
}
```

Đây là đoạn tích hợp minh họa. `@RestControllerAdvice` là tổ hợp tiện lợi của `@ControllerAdvice` và `@ResponseBody`; kết quả từ các exception handlers được ghi vào response body theo cơ chế HTTP message converters. `@ControllerAdvice` thông thường cũng có thể trả `ResponseEntity`, nhưng không mặc định biến một chuỗi return thành response body nếu thiếu xử lý `@ResponseBody` tương ứng.

**Không nhầm `@ControllerAdvice` với filter hoặc servlet interceptor.** Advice tham gia cơ chế xử lý của Spring MVC, không mặc định bắt mọi exception phát sinh trong security filter chain, trước `DispatcherServlet`, hoặc những tác vụ chạy ngoài HTTP request.

### 4.1. Giới hạn phạm vi advice

Có thể dùng selectors:

```java
@RestControllerAdvice(basePackages = "demo.api")
class ApiOnlyAdvice {}

@RestControllerAdvice(
    assignableTypes = {BookingController.class}
)
class BookingOnlyAdvice {}

@RestControllerAdvice(annotations = RestController.class)
class RestControllerOnlyAdvice {}
```

Các class trên là **ví dụ selector tách biệt**, không cần đưa tất cả vào một ứng dụng mẫu. Nếu không có selector, advice có phạm vi áp dụng rộng hơn. Selector có thể giới hạn theo package, class hoặc annotation; nếu dùng nhiều selector khác nhau, hãy kiểm tra quy tắc kết hợp của Spring và tránh giả định chúng luôn là phép giao.

### 4.2. Thứ tự của nhiều global advice

Với các advice cùng khớp, sử dụng `@Order` hoặc `Ordered` để nêu ưu tiên:

```java
@RestControllerAdvice
@Order(10)
class BusinessAdvice {}

@RestControllerAdvice
@Order(20)
class FallbackAdvice {}
```

Giá trị `@Order` thấp hơn có ưu tiên cao hơn trong trường hợp advice beans thông thường. Trong **cùng một advice**, root exception match thường được ưu tiên hơn cause match; nhưng **giữa các advice**, một cause match ở advice có ưu tiên cao hơn có thể được chọn trước root match ở advice ít ưu tiên hơn.

Vì vậy đặt một `@ExceptionHandler(Exception.class)` quá rộng ở advice có ưu tiên cao nhất có thể che các handlers cụ thể ở advice khác. Nên thiết kế các nhóm exception theo phạm vi và order rõ ràng.

### 4.3. Root exception và nested cause

Spring MVC có thể tìm exception handler dựa trên exception được ném trực tiếp hoặc nguyên nhân lồng sâu trong chain. Ví dụ `IllegalStateException` bao `IOException` có thể khớp handler của `IOException` ở một advice thích hợp.

Để tránh ambiguity, dùng signature cụ thể. Khi handler nhận một exception đã match qua nguyên nhân sâu, cần hiểu object được cung cấp có thể không giống root exception ban đầu; không viết logic giả định mọi lần gọi luôn nhận cùng tầng wrapper.

Spring còn cho phép handler **rethrow chính exception ban đầu** để trả quyền xử lý cho các resolver/handlers tiếp theo khi một điều kiện động không phù hợp. Chỉ dùng chiến lược đó khi hiểu rõ thứ tự resolver và có test.

## 5. ResponseEntityExceptionHandler: điểm mở rộng có sẵn cho MVC

`org.springframework.web.servlet.mvc.method.annotation.ResponseEntityExceptionHandler` là lớp cơ sở để xử lý các exception liên quan Spring MVC, như lỗi body, binding, validation, HTTP method/media type và các loại `ErrorResponseException`.

Khi dùng:

```java
@RestControllerAdvice
public class GlobalApiExceptionHandler
        extends ResponseEntityExceptionHandler {
    // Override những protected methods cần tùy biến.
}
```

Lớp cơ sở đã có một phương thức `@ExceptionHandler` xử lý các lỗi MVC mà nó hỗ trợ. Theo Spring 6.2, phương thức `handleException(Exception, WebRequest)` là **final**. Vì vậy:

- **Không override `handleException(...)`.**
- **Không thêm `@ExceptionHandler(MethodArgumentNotValidException.class)` trong subclass để giành xử lý cùng exception**; hãy override `handleMethodArgumentNotValid(...)`.
- Có thể thêm `@ExceptionHandler(MyBusinessException.class)` cho **exception nghiệp vụ riêng** mà base không xử lý.
- Có thể override `handleExceptionInternal(...)` cho hành vi chung, hoặc `createResponseEntity(...)` khi cần can thiệp bước tạo response cuối cùng.

### 5.1. Một số protected hooks Spring 6.2

| Method có thể override | Tình huống |
| --- | --- |
| `handleMethodArgumentNotValid(...)` | DTO/form object không hợp lệ khi argument-level validation |
| `handleHandlerMethodValidationException(...)` | Method validation trên controller parameters/return value, Spring MVC 6.1+ |
| `handleHttpMessageNotReadable(...)` | JSON/body không đọc được, giá trị không deserialize được |
| `handleTypeMismatch(...)` | Lỗi type conversion ở hạ tầng argument binding |
| `handleMissingServletRequestParameter(...)` | Thiếu required query/form parameter |
| `handleHttpRequestMethodNotSupported(...)` | HTTP method không hỗ trợ |
| `handleHttpMediaTypeNotSupported(...)` | Unsupported Content-Type |
| `handleHttpMediaTypeNotAcceptable(...)` | Không thương lượng được response media type |
| `handleErrorResponseException(...)` | `ErrorResponseException` |
| `handleExceptionInternal(...)` | Điểm xử lý chung sau khi đã xác định status/body |
| `createResponseEntity(...)` | Can thiệp cuối trước khi trả `ResponseEntity` |

**Đừng copy override signatures của Spring 5.x vào 6.2.** Spring 6 sử dụng `HttpStatusCode` trong nhiều callback, không phải mọi nơi đều dùng `HttpStatus`. IDE hoặc Javadoc đúng version là nguồn để xác nhận method và thứ tự tham số.

Chữ ký chính xác của hai hook validation trong Spring 6.2:

```java
@Override
protected ResponseEntity<Object> handleMethodArgumentNotValid(
        MethodArgumentNotValidException ex,
        HttpHeaders headers,
        HttpStatusCode status,
        WebRequest request) {
    // ...
}

@Override
protected ResponseEntity<Object> handleHandlerMethodValidationException(
        HandlerMethodValidationException ex,
        HttpHeaders headers,
        HttpStatusCode status,
        WebRequest request) {
    // ...
}
```

Đây là **fragment chỉ thể hiện chữ ký**; cần thân return phù hợp và các imports. Chương trình đầy đủ có ở mục 8.

### 5.2. Giữ status và headers do framework xác định

Trong override, các tham số `status` và `headers` không phải đồ trang trí. Ví dụ lỗi method không hỗ trợ có thể mang header `Allow`; các exception khác có thể có thông tin phù hợp với HTTP contract.

Với validation trên request, status thông thường là 400. Nhưng validation **return value** trên controller có thể mang status 500. Đừng viết một helper ép mọi `HandlerMethodValidationException` thành 400.

Khi gọi `handleExceptionInternal(ex, body, headers, status, request)`, bạn có thể giữ cách xử lý chung của base. Chỉ đổi status/headers có lý do rõ ràng và test.

## 6. ProblemDetail và RFC 9457

Spring Framework 6+ hỗ trợ `org.springframework.http.ProblemDetail`, dựa trên RFC 9457 *Problem Details for HTTP APIs*. Các trường chính:

| Thuộc tính | Ý nghĩa |
| --- | --- |
| `type` | URI nhận dạng loại vấn đề; mặc định thường là `about:blank` |
| `title` | Tên ngắn của lỗi, thích hợp cho người đọc |
| `status` | HTTP status của vấn đề |
| `detail` | Diễn giải cho request cụ thể |
| `instance` | URI định danh lần xảy ra vấn đề, thường là request path |
| Extension properties | Trường riêng của ứng dụng, ví dụ `fields`, `code`, `traceId` |

Ví dụ JSON minh họa:

```json
{
  "type": "about:blank",
  "title": "Invalid request",
  "status": 400,
  "detail": "Request body validation failed",
  "instance": "/bookings",
  "fields": ["customer", "seats"]
}
```

Khi dùng `ProblemDetail` làm body, Spring MVC có thể dùng media type **`application/problem+json`** và tự điền `instance` từ request path nếu bạn chưa đặt. Không giả định thứ tự key JSON luôn giống nhau hoặc response luôn có đủ tất cả optional fields trong mọi cấu hình.

### 6.1. Tạo ProblemDetail

```java
ProblemDetail p = ProblemDetail.forStatus(HttpStatus.BAD_REQUEST);
p.setTitle("Invalid request");
p.setDetail("Please correct your input");
p.setProperty("code", "INVALID_INPUT");
```

Đây là **fragment** trong Java. `setProperty(...)` thêm extension property, và Spring/Jackson có hỗ trợ đưa các property mở rộng này vào JSON response.

### 6.2. ErrorResponse và ErrorResponseException

`ErrorResponse` là abstraction của Spring biểu diễn error status, headers và `ProblemDetail`. Nhiều exception do Spring MVC tạo ra tuân theo contract đó. `ErrorResponseException` là một triển khai có thể dùng khi ứng dụng cần ném một HTTP error với body đã cấu hình.

Ngoài ra có `ResponseStatusException` để báo status/reason trực tiếp trong code. Nhưng để bảo đảm một format lỗi thống nhất và không phụ thuộc text của exception, nên dùng `@ControllerAdvice` / `ResponseEntityExceptionHandler` hoặc error response abstraction có chủ đích.

### 6.3. Các nguyên tắc bảo mật trong body

- Không trả exception class name, stack trace, SQL query, repository path, token hoặc mật khẩu.
- Không tự động serialize nguyên `BindingResult` hoặc `FieldError#getRejectedValue()`.
- Với HTTP 500, dùng câu generic; ghi log chi tiết ở server cùng correlation ID nếu có.
- Đừng tự đưa mọi incoming header hoặc request body vào `ProblemDetail`.
- Nếu đưa danh sách field lỗi, xem xét allowlist field names public để không lộ cấu trúc domain nhạy cảm.

## 7. Chọn đúng exception cho binding và validation

Một controller có thể gặp các exception sau:

| Trường hợp | Exception điển hình trong Spring MVC 6.1+ | Trạng thái thường gặp |
| --- | --- | --- |
| `@Valid @RequestBody DTO` có constraint sai, không có `BindingResult` liền kề và không kích hoạt whole-method validation | `MethodArgumentNotValidException` | 400 |
| Constraint trực tiếp `@Min(1)` trên `@RequestParam` | `HandlerMethodValidationException` | 400 nếu input sai |
| Constraint trên return value của controller | `HandlerMethodValidationException` | 500 |
| JSON sai cú pháp hoặc không thể đọc | `HttpMessageNotReadableException` | 400 |
| Required query parameter bị thiếu | `MissingServletRequestParameterException` | 400 |
| Không convert được `page=abc` sang `int` | `MethodArgumentTypeMismatchException` | 400 |
| HTTP method không hỗ trợ | `HttpRequestMethodNotSupportedException` | 405 |
| Media type của request không được hỗ trợ | `HttpMediaTypeNotSupportedException` | 415 |
| Không tìm thấy tài nguyên của ứng dụng | Custom exception như `BookingNotFoundException` | Phụ thuộc handler, thường 404 |
| Bug hoặc lỗi hạ tầng chưa nhận diện | Exception bất kỳ | 500, không nên xuất chi tiết nội bộ |

Các dòng là **tình huống thông thường**, không có nghĩa mọi signature hoặc toàn bộ cấu hình đều đi đúng một exception duy nhất. Converter, `@ControllerAdvice`, AOP method validation và custom argument resolvers có thể thay đổi đường xử lý.

### 7.1. BindingResult có làm exception biến mất không?

Một handler như:

```java
@PostMapping("/forms")
public String save(
        @Valid @ModelAttribute("form") SignupForm form,
        BindingResult result) {

    if (result.hasErrors()) {
        return "formView";
    }
    return "successView";
}
```

có `BindingResult` **đứng ngay sau** form nên handler có thể xử lý lỗi binding/validation tại chỗ. Trường hợp ấy không nhất thiết ném `MethodArgumentNotValidException`. Vì vậy, đừng kỳ vọng global exception advice nhận tất cả validation errors nếu controller tự giữ `BindingResult` rồi trả view/status.

### 7.2. Direct method constraints từ Spring MVC 6.1

`@Valid` trên object là cascade marker. Khi thêm `@Min`, `@NotBlank` hay constraint trực tiếp trên method parameter/return type, Spring MVC có thể dùng **built-in method validation** cho toàn handler.

Với `@Validated` cấp class của controller, có thể chuyển sang method validation qua Spring AOP. Tài liệu Spring MVC 6.1+ khuyến nghị bỏ class-level `@Validated` nếu mục tiêu là dùng built-in MVC method validation; nếu không, exception có thể khác (chẳng hạn `ConstraintViolationException`).

### 7.3. Exception từ filter hoặc security chain

`@ControllerAdvice` không phải cơ chế duy nhất để chuẩn hóa lỗi của hệ thống. Authentication/authorization failures phát sinh tại Spring Security filter chain thường do `AuthenticationEntryPoint` hoặc `AccessDeniedHandler` chịu trách nhiệm. Cần xây dựng contract lỗi nhất quán ở boundary tương ứng, không cố catch mọi security exception trong controller advice.

## 8. Ứng dụng hoàn chỉnh: Java 17 + Spring Boot 3.5.6

Ví dụ chứng minh cả ba công cụ:

1. Controller ném một **exception nghiệp vụ riêng**.
2. Spring MVC tự ném các exception về **validation/binding**.
3. Global `@RestControllerAdvice extends ResponseEntityExceptionHandler` override các hook chuẩn và thêm một `@ExceptionHandler` chỉ cho exception nghiệp vụ.

Chương trình chạy với Java 17+, Maven 3.x và không cần database hay template engine.

### 8.1. Cấu trúc file

```text
mvc-error-response-demo/
├── pom.xml
└── src/main/java/demo/errors/
    ├── ErrorDemoApplication.java
    ├── BookingController.java
    ├── BookingNotFoundException.java
    └── GlobalApiExceptionHandler.java
```

### 8.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>

  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.6</version>
    <relativePath/>
  </parent>

  <groupId>demo</groupId>
  <artifactId>mvc-error-response-demo</artifactId>
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
```

`spring-boot-starter-web` cấu hình Spring MVC/embedded Tomcat, còn `spring-boot-starter-validation` cung cấp Jakarta Validation provider.

### 8.3. ErrorDemoApplication.java

```java
package demo.errors;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ErrorDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ErrorDemoApplication.class, args);
    }
}
```

### 8.4. BookingNotFoundException.java

```java
package demo.errors;

public class BookingNotFoundException extends RuntimeException {

    public BookingNotFoundException(long id) {
        super("Booking " + id + " not found");
    }
}
```

Thông điệp của exception chỉ phục vụ chẩn đoán. Global handler **không** đưa nguyên `ex.getMessage()` vào public response để tránh lộ dữ liệu nếu exception chứa chi tiết nội bộ.

### 8.5. BookingController.java

```java
package demo.errors;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/bookings")
public class BookingController {

    public record BookingRequest(
        @NotBlank String customer,
        @NotNull @Min(1) Integer seats
    ) {}

    @PostMapping
    public ResponseEntity<String> create(
            @Valid @RequestBody BookingRequest request) {

        return ResponseEntity.status(HttpStatus.CREATED).body(
            "BOOKED:" + request.customer() + ":" + request.seats());
    }

    @GetMapping
    public String list(@RequestParam("page") @Min(1) int page) {
        return "PAGE:" + page;
    }

    @GetMapping("/{id}")
    public String find(@PathVariable("id") long id) {
        if (id != 7L) {
            throw new BookingNotFoundException(id);
        }
        return "BOOKING:7";
    }

    @GetMapping("/bad-return")
    @NotBlank
    public String badReturn() {
        // Chủ ý vi phạm hậu điều kiện để kiểm thử HTTP 500.
        return "";
    }
}
```

Giải thích đường lỗi:

- `POST /bookings` với body JSON hợp lệ tạo booking và trả 201.
- DTO `BookingRequest` có field constraints; `@Valid` khiến MVC kiểm tra sau khi deserialize. Khi input sai, handler body không được gọi.
- `GET /bookings?page=0` vi phạm **direct method constraint `@Min(1)`**. Với Spring MVC 6.1+, đó là đường `HandlerMethodValidationException`.
- `GET /bookings/99` ném exception riêng `BookingNotFoundException`.
- `GET /bookings/bad-return` cố ý trả chuỗi rỗng trong khi method có `@NotBlank` trên return value, dẫn đến validation phía server và HTTP 500.

Không đặt `@Validated` ở cấp class trên controller để sử dụng built-in method validation. Đường `/bad-return` cụ thể hơn path-variable mapping `/{id}`; Spring MVC chọn mapping cụ thể.

### 8.6. GlobalApiExceptionHandler.java

```java
package demo.errors;

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
public class GlobalApiExceptionHandler
        extends ResponseEntityExceptionHandler {

    // Lỗi DTO validation: override hook của base class.
    @Override
    protected ResponseEntity<Object> handleMethodArgumentNotValid(
            MethodArgumentNotValidException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        List<String> fields = ex.getBindingResult().getFieldErrors()
            .stream()
            .map(FieldError::getField)
            .distinct()
            .sorted()
            .toList();

        ProblemDetail detail = ProblemDetail.forStatus(status);
        detail.setTitle("Invalid request");
        detail.setDetail("Request body validation failed");
        detail.setProperty("fields", fields);

        return handleExceptionInternal(
            ex, detail, headers, status, request);
    }

    // Spring MVC 6.1+ method validation: input 400, return value 500.
    @Override
    protected ResponseEntity<Object> handleHandlerMethodValidationException(
            HandlerMethodValidationException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        ProblemDetail detail = ProblemDetail.forStatus(status);
        detail.setTitle(ex.isForReturnValue()
            ? "Invalid server response"
            : "Invalid request parameters");
        detail.setDetail(ex.isForReturnValue()
            ? "Controller returned invalid data"
            : "Controller parameters failed validation");

        return handleExceptionInternal(
            ex, detail, headers, status, request);
    }

    // Body không đọc được: lỗi decoder/converter khác với constraint.
    @Override
    protected ResponseEntity<Object> handleHttpMessageNotReadable(
            HttpMessageNotReadableException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        ProblemDetail detail = ProblemDetail.forStatus(status);
        detail.setTitle("Unreadable request body");
        detail.setDetail("Malformed JSON or incompatible value");

        return handleExceptionInternal(
            ex, detail, headers, status, request);
    }

    // Exception nghiệp vụ riêng, không nằm trong mapping của base class.
    @ExceptionHandler(BookingNotFoundException.class)
    public ResponseEntity<ProblemDetail> handleNotFound(
            BookingNotFoundException ex) {

        ProblemDetail detail = ProblemDetail.forStatusAndDetail(
            HttpStatus.NOT_FOUND, "Booking was not found");
        detail.setTitle("Booking not found");

        return ResponseEntity.status(HttpStatus.NOT_FOUND).body(detail);
    }
}
```

Đây là source hoàn chỉnh cho global advice của ứng dụng demo. Các chú ý quan trọng:

1. **Ba lỗi framework được xử lý bằng `@Override protected handle...`**. Chúng không có annotation `@ExceptionHandler` mới, tránh mapping trùng với base class.
2. Exception nghiệp vụ `BookingNotFoundException` có `@ExceptionHandler` riêng vì nó không phải một built-in error type mà base đã đăng ký.
3. `HttpStatusCode status` được giữ nguyên khi gọi `handleExceptionInternal(...)`. Điều này bảo toàn status 400/500 theo loại lỗi.
4. `FieldError#getField()` được dùng để tạo danh sách field names đã sắp xếp, **không** trả rejected values.
5. Không trả `ex.getMessage()` trực tiếp cho client.
6. `ProblemDetail` được serializer của Spring xử lý như RFC 9457 error body; `instance` có thể được tự điền theo request path.
7. Nếu muốn thêm mã lỗi public, có thể gọi `detail.setProperty("code","INVALID_BOOKING")` và test contract ổn định.

### 8.7. Chạy ứng dụng

Tại thư mục có `pom.xml`:

```bash
mvn -q spring-boot:run
```

Mặc định server lắng nghe `http://localhost:8080` nếu cổng chưa được sử dụng. Trong terminal bash/zsh/WSL khác, kiểm tra qua HTTP.

**Case A — booking hợp lệ:**

```bash
curl -i -X POST 'http://localhost:8080/bookings' \
  -H 'Content-Type: application/json' \
  -d '{"customer":"Alice","seats":2}'
```

HTTP **201 Created**, body:

```text
BOOKED:Alice:2
```

**Case B — DTO có hai field không hợp lệ:**

```bash
curl -i -X POST 'http://localhost:8080/bookings' \
  -H 'Content-Type: application/json' \
  -d '{"customer":"","seats":0}'
```

HTTP **400 Bad Request**. Response body kiểu `ProblemDetail` có các nội dung quan trọng:

```json
{
  "title": "Invalid request",
  "status": 400,
  "detail": "Request body validation failed",
  "fields": ["customer", "seats"]
}
```

JSON trên là **trích các field cần kiểm tra**, không phải toàn bộ literal byte-for-byte: Spring có thể thêm `type`, `instance` và media type `application/problem+json`; thứ tự key phụ thuộc serializer. `fields` được sắp xếp để ổn định.

**Case C — direct constraint trên query parameter:**

```bash
curl -i 'http://localhost:8080/bookings?page=0'
```

HTTP **400 Bad Request**, `title` là:

```text
Invalid request parameters
```

Đường lỗi này được xử lý trong override `handleHandlerMethodValidationException`, không phải `handleMethodArgumentNotValid`.

**Case D — exception nghiệp vụ không tìm thấy:**

```bash
curl -i 'http://localhost:8080/bookings/99'
```

HTTP **404 Not Found**, `title` và `detail`:

```text
title: Booking not found
detail: Booking was not found
```

Đường xử lý là phương thức `@ExceptionHandler(BookingNotFoundException.class)` được thêm vào subclass.

**Case E — body JSON lỗi cú pháp:**

```bash
curl -i -X POST 'http://localhost:8080/bookings' \
  -H 'Content-Type: application/json' \
  -d '{"customer":'
```

HTTP **400 Bad Request**, `title` và `detail`:

```text
title: Unreadable request body
detail: Malformed JSON or incompatible value
```

Lỗi này xảy ra **trước Bean Validation**; vì vậy không kỳ vọng `fields` là danh sách field sai constraint.

**Case F — return-value validation thất bại:**

```bash
curl -i 'http://localhost:8080/bookings/bad-return'
```

HTTP **500 Internal Server Error**, `title` là:

```text
Invalid server response
```

Đây là vi phạm hậu điều kiện của controller; không được gộp vào HTTP 400 chỉ vì cùng dùng một class `HandlerMethodValidationException`.

**Case G — type conversion error:**

```bash
curl -i 'http://localhost:8080/bookings?page=abc'
```

Ở đây `String "abc"` không thể chuyển thành `int`. MVC thường phát `MethodArgumentTypeMismatchException` và base class xử lý như lỗi 400. **Không** kỳ vọng body từ override `handleHandlerMethodValidationException`, vì `@Min(1)` chưa có giá trị số hợp lệ để đánh giá.

**Case H — thiếu query parameter:**

```bash
curl -i 'http://localhost:8080/bookings'
```

Vì `@RequestParam("page")` mặc định `required=true`, việc thiếu `page` thường phát `MissingServletRequestParameterException`; base handler xử lý với HTTP 400 theo RFC 9457. Đây là nhánh khác với case `page=0`.

Mọi case `curl -i` in cả headers lẫn body. Các đoạn output trên là **những giá trị cần kiểm chứng**, không cố khẳng định từng header hoặc thứ tự tất cả JSON properties giống nhau giữa môi trường.

## 9. Không trùng @ExceptionHandler trong subclass

Một lỗi thường gặp:

```java
@RestControllerAdvice
public class WrongAdvice extends ResponseEntityExceptionHandler {

    // KHÔNG KHUYẾN NGHỊ: mapping lỗi đã có trong base class.
    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<String> anotherHandler(
            MethodArgumentNotValidException ex) {
        return ResponseEntity.badRequest().body("Invalid");
    }
}
```

Đây là **mã cố tình sai để minh họa**, không thêm vào project ở mục 8. Base class đã khai báo một phương thức `@ExceptionHandler` bao gồm `MethodArgumentNotValidException`. Thêm một handler tương đương có thể khiến Spring MVC báo **ambiguous @ExceptionHandler method mapped**, làm ứng dụng lỗi cấu hình thay vì xử lý request.

Cách đúng:

```java
@Override
protected ResponseEntity<Object> handleMethodArgumentNotValid(
        MethodArgumentNotValidException ex,
        HttpHeaders headers,
        HttpStatusCode status,
        WebRequest request) {

    ProblemDetail detail = ProblemDetail.forStatus(status);
    detail.setTitle("Invalid request");
    return handleExceptionInternal(
        ex, detail, headers, status, request);
}
```

Đây là fragment hợp lệ khi nằm trong subclass và có imports phù hợp.

### 9.1. Khi nào dùng @ExceptionHandler riêng?

Dùng cho những exception **không được base class xử lý** hoặc khi không kế thừa base class:

- `EntityNotFoundException`/exception nghiệp vụ riêng.
- `OptimisticLockingFailureException` nếu bạn muốn ánh xạ conflict HTTP 409 theo domain contract.
- Một exception do tầng ứng dụng định nghĩa để biểu diễn “không được phép chuyển trạng thái”.

Không mặc định bắt mọi `RuntimeException` và trả 400; điều đó che bug phía server và gây sai HTTP semantics. Nếu cần catch-all cho 500, trả thông điệp an toàn, log server-side và cân nhắc để hạ tầng error mặc định xử lý những lỗi không dự kiến.

## 10. Phản hồi lỗi validation: body và mã ổn định

Thay vì trả nguyên `FieldError`, hãy định nghĩa contract có cấu trúc:

```json
{
  "type": "https://api.example.test/problems/validation",
  "title": "Validation failed",
  "status": 400,
  "detail": "One or more fields are invalid",
  "code": "INVALID_INPUT",
  "violations": [
    {"field": "customer", "code": "NotBlank"},
    {"field": "seats", "code": "Min"}
  ]
}
```

Ví dụ này chỉ để giải thích thiết kế, **không phải body byte-for-byte của source demo**. Bạn có thể dùng `ProblemDetail#setType(URI)` và `setProperty("violations", ...)` để gắn các chi tiết mở rộng.

Lưu ý rằng `FieldError#getCode()` thường là mã tổng quát như `NotBlank`, trong khi `getCodes()` là mảng mã ưu tiên theo object/field. Client không nên parse câu `getDefaultMessage()` để tìm logic. Nếu error code là public API, hãy định nghĩa mapping ổn định do ứng dụng sở hữu.

### 10.1. Phân biệt FieldError và ObjectError

`BindingResult#getFieldErrors()` chỉ chứa lỗi field. Các custom validators có thể tạo **global errors** bằng `errors.reject(...)`; chúng xuất hiện qua `getGlobalErrors()` hoặc `getAllErrors()`.

Ví dụ demo chỉ xuất tên field; production nên quyết định cách biểu diễn global errors sao cho không làm mất thông tin liên quan nhiều thuộc tính. Nếu response chỉ duyệt field errors, phải xác nhận business validator không có object-level rules cần công bố.

### 10.2. MessageSource và đa ngôn ngữ

Spring `MessageSource` có thể phân giải `ObjectError`/`FieldError` (chúng là `MessageSourceResolvable`) theo `Locale`:

```java
String displayMessage = messageSource.getMessage(error, locale);
```

Đây là fragment dùng `messageSource`, `error` và `locale` đã có. Với `ResponseEntityExceptionHandler`, Spring hỗ trợ lookup và cấu hình messages cho `ProblemDetail`. Hãy thống nhất chiến lược i18n và tránh hardcode tiếng Anh trong advice nếu ứng dụng cần nhiều ngôn ngữ.

**Không nhầm** resource bundle `ValidationMessages.properties` của Jakarta Bean Validation với `messages.properties` của Spring `MessageSource` nếu chưa cấu hình chúng dùng chung.

## 11. Local handler, global advice và base handler: chọn cách nào?

| Nhu cầu | Lựa chọn thường phù hợp | Vì sao |
| --- | --- | --- |
| Một controller cần quy tắc recovery riêng | `@ExceptionHandler` ngay trong controller | Scope cục bộ rõ ràng |
| Nhiều REST controllers dùng error contract thống nhất | `@RestControllerAdvice` | Dùng lại và quản lý tập trung |
| Cần định dạng tất cả lỗi framework MVC chuẩn | `ResponseEntityExceptionHandler` làm base | Có hook chuyên dụng, status/headers chuẩn |
| Chỉ vài exception nghiệp vụ riêng | `@ExceptionHandler` trong advice | Mapping cụ thể, không phải override base |
| Đổi cấu trúc cuối cùng của mọi response từ base | `createResponseEntity(...)` | Can thiệp tập trung trước khi gửi |
| Bổ sung logic chung của các exception framework | `handleExceptionInternal(...)` | Bước xử lý chung |
| Lỗi xác thực ở Security filter chain | `AuthenticationEntryPoint` / `AccessDeniedHandler` | Không thuộc mọi đường @ControllerAdvice |
| Exception không phát sinh trong MVC request | Xử lý ở boundary tương ứng | Controller advice không bao trùm scheduler/kafka/background task |

Một hệ thống có thể kết hợp các mức, nhưng nên hạn chế duplicate mappings và thứ tự advice ngầm định.

## 12. @Order, exception specificity và nguy cơ handler quá rộng

Giả sử có hai advice:

```java
@RestControllerAdvice
@Order(10)
class GenericAdvice {

    @ExceptionHandler(Exception.class)
    ResponseEntity<String> all(Exception ex) {
        return ResponseEntity.internalServerError()
                .body("Unexpected error");
    }
}

@RestControllerAdvice
@Order(20)
class BusinessAdvice {

    @ExceptionHandler(BookingNotFoundException.class)
    ResponseEntity<String> missing(BookingNotFoundException ex) {
        return ResponseEntity.status(404).body("Not found");
    }
}
```

Đây là **cấu hình minh họa**, không thêm vào project chính. Với `@Order(10)` được ưu tiên hơn `@Order(20)`, handler tổng quát của GenericAdvice có thể xử lý mất những lỗi business mà bạn định cho BusinessAdvice, tạo HTTP 500 thay vì 404.

Nên đặt handlers cụ thể ở tầng ưu tiên phù hợp, hoặc không đăng ký catch-all rộng ngoài nhu cầu. Trong một advice, Spring so độ sâu exception class và ưu tiên match cụ thể; nhưng quy tắc giữa các advice phải xét `@Order`, không chỉ độ đặc thù của exception.

Nếu advice có selector package/type, một handler chỉ có hiệu lực khi controller thực tế thuộc phạm vi selector. Lỗi nằm ngoài phạm vi có thể được base/default resolver xử lý.

## 13. Dùng ResponseEntityExceptionHandler để thêm metadata an toàn

Một hướng mở rộng phổ biến là thêm mã lỗi thống nhất. Nếu mọi `ProblemDetail` từ base phải có `code`, có thể override `createResponseEntity(...)`, nhưng phải giữ chính xác status, headers và tránh làm thay đổi response ngoài ý muốn.

Fragment minh họa:

```java
@Override
protected ResponseEntity<Object> createResponseEntity(
        Object body,
        HttpHeaders headers,
        HttpStatusCode statusCode,
        WebRequest request) {

    if (body instanceof ProblemDetail detail) {
        detail.setProperty("code", "HTTP_ERROR");
    }

    return super.createResponseEntity(
        body, headers, statusCode, request);
}
```

Đây là **fragment cho subclass**, không cần có trong source chính. Nếu dùng `code="HTTP_ERROR"` cho mọi status, bạn mất sự phân loại nguyên nhân. Trong ứng dụng thật, nên ánh xạ code cụ thể theo exception type, status và domain semantics.

### Trace/correlation ID

Nếu hạ tầng có tracing, bạn có thể thêm correlation ID đã được sanitize vào extension property. Không trả stack trace hoặc request headers chứa token; không tiết lộ thông tin từ MDC hay tracing mà API không định công khai.

### Các response đã được commit

Khi HTTP response đã bắt đầu gửi body/headers, một exception handler có thể không còn khả năng thay đổi status. Spring's internal handler có thể trả `null` khi response đã committed. Vì vậy exception advice không thay thế transactional design, streaming error handling hoặc client retry strategy.

## 14. Kiểm thử thực tế

Unit test gọi trực tiếp method controller **không** thực hiện toàn bộ argument resolution/validation và không kích hoạt `HandlerExceptionResolver`. Với lỗi MVC, nên dùng `MockMvc` hoặc HTTP integration tests.

Bộ kiểm thử tối thiểu:

| Test | Kỳ vọng |
| --- | --- |
| JSON hợp lệ, `customer=Alice,seats=2` | 201, `BOOKED:Alice:2` |
| `customer=""`, `seats=0` | 400, title `Invalid request`, danh sách field chuẩn |
| `GET /bookings?page=0` | 400, title `Invalid request parameters` |
| `GET /bookings?page=1` | 200, body `PAGE:1` |
| `GET /bookings/99` | 404, title `Booking not found` |
| `GET /bookings/7` | 200, body `BOOKING:7` |
| JSON sai cú pháp | 400, title `Unreadable request body` |
| `GET /bookings/bad-return` | 500, title `Invalid server response` |
| `GET /bookings?page=abc` | 400 từ type mismatch, không vào direct Min handler |
| Thiếu `page` | 400 từ missing request parameter |
| POST với content type không hỗ trợ | 415, header/body phù hợp |
| HTTP method không hỗ trợ | 405, header `Allow` nếu applicable |

Để test mapping không mơ hồ, ứng dụng phải khởi động Spring context thành công. Một subclass base có hai handlers trùng `MethodArgumentNotValidException` sẽ có nguy cơ lỗi ngay khi lập exception resolver; kiểm thử endpoint hợp lệ cũng giúp phát hiện.

### 14.1. Ví dụ kiểm thử với MockMvc

Nếu bổ sung `spring-boot-starter-test` với test scope vào `pom.xml`, bạn có thể viết:

```java
@SpringBootTest
@AutoConfigureMockMvc
class ErrorApiTest {

    @Autowired
    MockMvc mvc;

    @Test
    void invalidQueryGetsProblemDetail() throws Exception {
        mvc.perform(get("/bookings").param("page", "0"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.title")
                .value("Invalid request parameters"));
    }
}
```

Đây là **fragment kiểm thử**, chưa có imports, test dependency và source file nên không thuộc ứng dụng chạy tối thiểu. `MockMvc` chạy chuỗi Spring MVC resolver và exception advice; gọi `new BookingController().list(0)` không có đủ cơ chế để kiểm chứng.

## 15. Những lỗi thường gặp và cách sửa

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| Spring báo ambiguous exception handler mapping | Subclass base có `@ExceptionHandler` trùng built-in exception | Override `handleMethodArgumentNotValid` hoặc hook tương ứng |
| DTO sai nhưng advice không chạy | Controller có `BindingResult` liền kề và xử lý tại chỗ | Quyết định rõ local versus central validation handling |
| Direct `@Min` tạo exception khác dự tính | Spring MVC 6.1+ dùng whole-method validation | Hỗ trợ `HandlerMethodValidationException` |
| JSON lỗi vẫn trả format mặc định | Chỉ override lỗi validation, không override lỗi decoder | Tùy biến `handleHttpMessageNotReadable` |
| Controller-local handler không được dùng | Lỗi xảy ra trước khi chọn controller hoặc scope không khớp | Kiểm tra handler selection và advice/global fallback |
| Error status 500 bị chuyển nhầm sang 400 | Xử lý tất cả validation exceptions cùng một status | Giữ `status` và `isForReturnValue()` |
| Headers cần thiết bị mất | Tự tạo response mới và bỏ qua `headers` | Giữ headers do base đưa vào |
| Lỗi nghiệp vụ 404 bị generic 500 handler bắt | `@Order` hoặc catch-all quá rộng | Ưu tiên handler cụ thể, tránh generic advice che khuất |
| API lộ stack trace hoặc dữ liệu đầu vào | Serialize exception/BindingResult trực tiếp | Dùng `ProblemDetail` với field/code/message an toàn |
| Exception security không vào advice | Phát sinh trong Security filter chain | Cấu hình entry point/access denied handler |
| Swagger/client kỳ vọng application/json nhưng nhận problem+json | RFC 9457 media type khác | Document content negotiation và schema |
| Test gọi controller trực tiếp không thấy lỗi | Bỏ qua Spring MVC runtime | Dùng MockMvc/HTTP integration |
| Tham số override không compile | Sao chép chữ ký Spring 5.x hoặc thiếu `HttpStatusCode` | Dùng Javadoc đúng Spring version |
| Exception đã được xử lý mà response vẫn không đổi | Response headers/body đã committed | Kiểm tra streaming/async semantics |

## 16. Quy tắc triển khai an toàn

1. **Phân loại error theo nguồn:** validation input 400; not found 404; conflict 409; unsupported method 405; unexpected server errors 500.
2. **Giữ contract ổn định:** codes dành cho client không phụ thuộc câu tiếng Anh/Việt, tên exception class hoặc stack trace.
3. **Dùng ProblemDetail/RFC 9457 có chủ đích:** standard fields cho HTTP semantics, extension properties cho dữ liệu public.
4. **Giữ status và headers từ framework:** đặc biệt khi override các protected hooks của base.
5. **Không dùng catch-all che exceptions quan trọng:** xem lại `@Order` và scopes.
6. **Không bỏ qua lỗi bị giữ trong BindingResult:** global advice không tự biết controller đã nuốt lỗi và trả success.
7. **Tránh lỗi lộ thông tin:** không serialize raw arguments, rejected values, SQL query hoặc environment paths.
8. **Kiểm thử request thật:** HTTP content type, validation, conversion, binding và method return-value validation.
9. **Phân biệt MVC với WebFlux:** package của `ResponseEntityExceptionHandler` khác; imports và reactive error semantics khác.
10. **Không dùng exception handler thay thế authorization hay transaction:** kiểm tra quyền và kiểm soát side effects ở tầng thích hợp.

## 17. Tóm tắt

**`@ExceptionHandler`** xử lý exception theo loại trong một controller hoặc advice. **`@ControllerAdvice` / `@RestControllerAdvice`** đưa handlers đến nhiều controller theo selectors và ordering. **`ResponseEntityExceptionHandler`** là lớp cơ sở sẵn có để chuẩn hóa các lỗi framework MVC, với các hook như `handleMethodArgumentNotValid`, `handleHandlerMethodValidationException`, `handleHttpMessageNotReadable` và `handleExceptionInternal`.

Khi dùng Spring MVC 6.2, hãy ưu tiên **override protected hook cho built-in exception** và chỉ thêm `@ExceptionHandler` cho lỗi nghiệp vụ riêng. Dùng `ProblemDetail` để truyền HTTP status/title/detail và các extension properties an toàn, bảo toàn status/headers do framework xác định, và test cả trường hợp lỗi xảy ra trước controller, trong controller, lẫn sau khi controller tạo return value.

## Tài liệu tham khảo

- Spring Framework 6.2 — Exception handlers: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-exceptionhandler.html
- Spring Framework 6.2 — Controller advice, scope và precedence: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-advice.html
- Spring Framework 6.2 — Error Responses, ProblemDetail và RFC 9457: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-ann-rest-exceptions.html
- Spring Framework 6.2 — HandlerExceptionResolver chain: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-servlet/exceptionhandlers.html
- Spring Framework 6.2 Javadoc — ResponseEntityExceptionHandler: https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/web/servlet/mvc/method/annotation/ResponseEntityExceptionHandler.html
- Spring Framework 6.2 Javadoc — HandlerMethodValidationException: https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/web/method/annotation/HandlerMethodValidationException.html
- Spring Framework 6.2 Javadoc — ProblemDetail: https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/http/ProblemDetail.html
- Spring Framework 6.2 — Validation in annotated controllers: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html
- RFC 9457 — Problem Details for HTTP APIs: https://www.rfc-editor.org/rfc/rfc9457