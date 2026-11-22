# HandlerMethodValidationException trong controller Spring WebFlux

## 1. Tình huống: HTTP 400 có thể đến từ hai cơ chế validation khác nhau

Trong controller **Spring WebFlux**, một request có thể được kiểm tra ở **mức đối số riêng lẻ** hoặc **mức toàn bộ phương thức**. Từ Spring Framework **6.1**, WebFlux hỗ trợ method validation tích hợp cho những controller được khai báo bằng `@RequestMapping`, không bắt buộc dựa vào proxy AOP.

Hai exception quan trọng cần phân biệt:

- **`WebExchangeBindException`**: thường xuất hiện khi Spring đọc/bind **một command object** dùng `@Valid` hoặc `@Validated`, ví dụ `@Valid @RequestBody CreateBookingRequest request`, và object đó vi phạm constraint.
- **`HandlerMethodValidationException`**: xuất hiện khi validation áp dụng **ở cấp phương thức**, ví dụ có constraint `@Min(1)`, `@NotBlank`, `@Pattern` hoặc `@NotNull` **trực tiếp trên tham số controller**, hoặc constraint trên giá trị trả về.

Dù cả hai có thể dẫn đến **400 Bad Request**, chúng mang kết quả lỗi khác nhau. `WebExchangeBindException` gắn với `BindingResult` của **một object**; `HandlerMethodValidationException` gắn với danh sách `ParameterValidationResult` cho **các tham số của method** và hỗ trợ xem lỗi theo loại tham số qua `visitResults(...)`.

Ví dụ hai chữ ký sau:

```java
// Individual argument validation:
@PostMapping("/bookings")
Mono<String> create(@Valid @RequestBody CreateBookingRequest request) {
    return Mono.just("ok");
}

// Built-in method validation:
@GetMapping("/bookings")
Mono<String> list(@RequestParam @Min(1) int page) {
    return Mono.just("page=" + page);
}
```

Đây là hai **fragment controller** để minh họa cơ chế, không phải project độc lập. Với method `create`, `@Valid` kích hoạt constraint của DTO. Với `list`, `@Min` đặt trực tiếp trên method parameter kích hoạt method validation. `@Valid` **không phải một constraint** của chính tham số; nó chủ yếu yêu cầu cascade vào object để xem các constraint bên trong.

**Phạm vi:** bài này dùng Spring WebFlux 6.1–6.2, Java 17+, Jakarta Validation (package `jakarta.validation.*`), và Spring Boot 3.x. Đừng lẫn `WebExchangeBindException` của **WebFlux** với `MethodArgumentNotValidException` thường gặp trong **Spring MVC**. Hai stack cùng có khái niệm `HandlerMethodValidationException` nhưng có pipeline xử lý request khác nhau.

## 2. Method validation thực sự diễn ra ở đâu?

Trong WebFlux annotated controller, luồng xử lý có thể mô tả như sau:

```text
HTTP request
     |
     v
DispatcherHandler -> HandlerMapping -> RequestMappingHandlerAdapter
     |
     v
Resolve controller method arguments
     |                           |
     |                           +--> @RequestParam / @RequestHeader:
     |                           |       đọc và convert giá trị đơn
     |                           |
     |                           +--> @RequestBody:
     |                                   HttpMessageReader, JSON decoder
     |
     +--> Không đọc/convert được? -> lỗi đọc hoặc binding
     |
     v
Nếu chỉ @Valid / @Validated trên command object
     |
     +--> individual object validation
     |           |
     |           +--> WebExchangeBindException nếu có lỗi
     |
     v
Nếu có direct constraint trên method parameter / return value
     |
     +--> built-in method validation
                 |
                 +--> HandlerMethodValidationException nếu có lỗi
     |
     v
Controller method / reactive response handling
```

Sơ đồ này là **mô hình khái niệm**; thứ tự nội bộ còn tùy loại đối số, giá trị reactive, data binding và việc lỗi phát sinh trước hay sau khi publisher được subscribe. Đặc biệt, WebFlux có thể giải quyết `Mono<T>`/`Flux<T>` bất đồng bộ và phát lỗi trong reactive pipeline, nên không mặc định mọi exception đều được ném ngay khi Java gọi method.

### Khi nào lỗi method thắng lỗi object?

Theo cơ chế built-in của Spring WebFlux, **method validation bao phủ cả** constraint trực tiếp trên tham số **và** constraint lồng bên trong object được đánh dấu `@Valid`. Vì vậy, nếu controller có direct constraint trên một tham số, nó có thể **thay thế nhánh individual validation** và báo `HandlerMethodValidationException` ngay cả khi DTO `@Valid` khác cũng không hợp lệ.

Ví dụ:

```java
@PostMapping("/bookings")
Mono<Void> create(
        @RequestParam @Min(1) int location,
        @Valid @RequestBody CreateBookingRequest body) {
    return Mono.empty();
}
```

Đoạn trên chỉ minh họa. Với `location=0`, method validation liên quan đến direct `@Min`. Nếu đồng thời DTO có field sai, Spring có thể gom lỗi theo nhiều tham số dưới `HandlerMethodValidationException`. Tuy nhiên, nếu body không thể deserialize thành DTO, lỗi đọc body xảy ra sớm hơn; không có object hợp lệ để kiểm tra như trong nhánh Bean Validation.

## 3. Bảng phân biệt WebFlux validation và các lỗi đầu vào khác

| Tình huống | Cơ chế | Exception tiêu biểu | Status thường gặp |
| --- | --- | --- | --- |
| `@Valid @RequestBody Dto`, object đọc được nhưng field sai | Individual Bean Validation | `WebExchangeBindException` | 400 |
| `@Valid @ModelAttribute Form`, field sai | Individual object validation | `WebExchangeBindException` | 400 |
| `@Valid @RequestPart Dto`, object part sai | Individual object validation | `WebExchangeBindException` | 400 |
| `@RequestParam @Min(1) int page` với `page=0` | Built-in method validation | `HandlerMethodValidationException` | 400 |
| `@RequestHeader @Pattern(...) String region` sai mẫu | Built-in method validation | `HandlerMethodValidationException` | 400 |
| Method trả giá trị vi phạm return constraint | Built-in return-value validation | `HandlerMethodValidationException` | **500** |
| `page=abc` với `int page` | Conversion trước method validation | Thường là `ServerWebInputException` hoặc lỗi input liên quan | 400 |
| Thiếu tham số bắt buộc do `@RequestParam(required=true)` | Argument resolution | Thường là `ServerWebInputException`/lỗi missing value | 400 |
| JSON sai cú pháp hoặc không deserializable | Reactive codec / message reader | Thường được chuyển thành `ServerWebInputException`, cause như `DecodingException` | 400 |
| `Content-Type` không được hỗ trợ | Media type negotiation | `UnsupportedMediaTypeStatusException` | 415 |
| Constraint trên service bean sử dụng AOP proxy | Service method validation | Có thể là `ConstraintViolationException` hoặc `MethodValidationException` | Tùy ứng dụng |

**Không dùng một `@ExceptionHandler(HandlerMethodValidationException.class)` để xử lý tất cả lỗi HTTP 400.** Handler này chỉ nhận những lỗi do built-in controller method validation. Những lỗi khác cần cơ chế xử lý phù hợp.

### Vì sao return-value violation trả 500?

Constraint của tham số thường biểu thị **request client không đạt điều kiện** → 400. Constraint của giá trị trả về biểu thị **server trả một kết quả trái với hợp đồng đã khai báo** → 500. `HandlerMethodValidationException#getStatusCode()` phân biệt hai tình huống; `isForReturnValue()` cho biết lỗi thuộc return value hay không.

Không ánh xạ mọi `HandlerMethodValidationException` sang 400 một cách cứng nhắc. Khi tự viết handler, **giữ `ex.getStatusCode()`**; nếu là lỗi return value, tránh tiết lộ các giá trị nội bộ trong response.

## 4. Metadata lỗi trong HandlerMethodValidationException

`org.springframework.web.method.annotation.HandlerMethodValidationException` triển khai hợp đồng `org.springframework.validation.method.MethodValidationResult` và là một `ResponseStatusException`. Những API nên biết:

| API | Ý nghĩa |
| --- | --- |
| `getStatusCode()` | HTTP status tương ứng: thường 400 cho input, 500 cho return constraint |
| `isForReturnValue()` | Phân biệt validation of return value với validation of arguments |
| `getMethod()` | Phương thức Java đang được validate |
| `getParameterValidationResults()` | Danh sách kết quả nhóm theo tham số |
| `getCrossParameterValidationResults()` | Các lỗi cross-parameter (nếu có) |
| `visitResults(Visitor visitor)` | Duyệt kết quả qua callback theo annotation loại đối số như `@RequestParam`, `@RequestHeader`, `@ModelAttribute` |
| `getBody()` | `ProblemDetail` được cung cấp theo hợp đồng Spring `ErrorResponse` |

### 4.1. ParameterValidationResult

Mỗi `ParameterValidationResult` biểu diễn các vi phạm gắn với một method parameter. Đáng chú ý:

- `getMethodParameter()`: trả metadata `MethodParameter`; có thể lấy vị trí bằng `getParameterIndex()`.
- `getResolvableErrors()`: danh sách `MessageSourceResolvable` mô tả các lỗi; có thể dùng `MessageSource` để nội suy theo locale.
- `getArgument()`: giá trị đã được validate. **Không tự xuất nó ra HTTP response** vì có thể chứa dữ liệu nhạy cảm.
- Với tham số kiểu container, Spring có thể tạo kết quả riêng theo phần tử, và metadata index/key giúp xác định vị trí bên trong container.
- `ParameterErrors` là subclass dành cho object có lỗi property lồng nhau; nó implement `Errors` để có thể đọc field/global errors theo cách tương tự object validation.

Sơ đồ:

```text
HandlerMethodValidationException
  |
  +-- getParameterValidationResults(): List<ParameterValidationResult>
          |
          +-- parameter 0: @RequestParam page
          |       +-- getResolvableErrors(): @Min(1)
          |
          +-- parameter 1: @RequestHeader X-Region
          |       +-- getResolvableErrors(): @Pattern(...)
          |
          +-- parameter 2: @Valid @RequestBody BookingRequest
                  +-- ParameterErrors (nếu có lỗi nested)
                          +-- FieldError("guest")
                          +-- FieldError("nights")
```

Các nhánh trên mang tính minh họa. Kết quả thực tế phụ thuộc chữ ký controller, constraint bị vi phạm, kiểu request argument và cấu hình validation. **Không giả định luôn có đúng một kết quả cho mỗi tham số** vì các container có thể tạo nhiều kết quả cho các phần tử.

### 4.2. Lấy danh sách vị trí tham số và số lỗi

Một đoạn mã độc lập về mặt API, dùng **bên trong handler** đã có biến `ex`:

```java
List<Integer> positions = ex.getParameterValidationResults().stream()
        .map(r -> r.getMethodParameter().getParameterIndex())
        .distinct()
        .sorted()
        .toList();

int errorCount = ex.getParameterValidationResults().stream()
        .mapToInt(r -> r.getResolvableErrors().size())
        .sum();
```

Đây là fragment, cần imports `java.util.List` và biến `HandlerMethodValidationException ex`. Cách đếm này tính **direct/nested resolvable errors được nhóm theo tham số**, không tự tính `getCrossParameterValidationResults()`; nếu có custom cross-parameter constraints, phải bổ sung nhóm lỗi đó khi tổng hợp.

### 4.3. Lựa chọn duyệt bằng Visitor

Nếu muốn định dạng lỗi theo vị trí nguồn đầu vào, Spring hỗ trợ visitor:

```java
ex.visitResults(new HandlerMethodValidationException.Visitor() {
    @Override
    public void requestParam(
            RequestParam annotation,
            ParameterValidationResult result) {
        // Ví dụ: gắn source="query".
    }

    @Override
    public void requestHeader(
            RequestHeader annotation,
            ParameterValidationResult result) {
        // Ví dụ: gắn source="header".
    }

    @Override
    public void other(ParameterValidationResult result) {
        // Fallback cho kết quả không thuộc callback được override.
    }
});
```

Đây là fragment, không phải class Java hoàn chỉnh. Các kiểu import tương ứng là `org.springframework.web.bind.annotation.RequestParam`, `RequestHeader`, `org.springframework.validation.method.ParameterValidationResult` và `HandlerMethodValidationException`. Các annotation callback có thể là `null` ở một số trường hợp theo API, do đó code xử lý thực tế phải có nhánh dự phòng và không giả định `annotation.name()` luôn dùng được.

Visitor còn có callback cho `@PathVariable`, `@ModelAttribute`, `@RequestBody` và các loại khác tùy phiên bản. Với object có lỗi nested, callback có thể nhận `ParameterErrors`. Cách duyệt trực tiếp `getParameterValidationResults()` thường đủ cho API error schema đơn giản; visitor hữu ích khi cần thông tin rõ ràng về nguồn input.

## 5. Ví dụ Java 17 chạy được: Spring Boot 3 + WebFlux

Ta tạo ứng dụng WebFlux tối giản với:

- `GET /bookings?page=...` và header `X-Region`: hai direct constraints trên controller method để kích hoạt `HandlerMethodValidationException`.
- `POST /bookings` nhận một DTO `@Valid @RequestBody`: riêng constraint DTO bị lỗi thì kích hoạt `WebExchangeBindException`.
- `@RestControllerAdvice` có hai handler, trả **hai error codes khác nhau**.
- `WebTestClient` kiểm tra cả nhánh thành công, query/header constraints, DTO constraints và JSON sai cú pháp.

### 5.1. Cấu trúc dự án

```text
webflux-method-validation/
├── pom.xml
└── src/
    ├── main/java/demo/
    │   ├── WebFluxValidationApplication.java
    │   ├── BookingRequest.java
    │   ├── BookingController.java
    │   └── ValidationAdvice.java
    └── test/java/demo/
        └── BookingControllerTest.java
```

### 5.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.4.5</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>webflux-method-validation</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
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
```

**Quan trọng:** chỉ dùng `spring-boot-starter-webflux` trong project này, không thêm `spring-boot-starter-web` một cách vô tình. Nếu cả hai starter có mặt, Spring Boot thường chọn Spring MVC cho ứng dụng web theo mặc định; khi đó bạn đang kiểm tra một pipeline khác. `spring-boot-starter-validation` cung cấp Jakarta Validation provider cần thiết để constraints được thực thi.

### 5.3. WebFluxValidationApplication.java

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebFluxValidationApplication {
    public static void main(String[] args) {
        SpringApplication.run(WebFluxValidationApplication.class, args);
    }
}
```

### 5.4. BookingRequest.java

```java
package demo;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public record BookingRequest(
        @NotBlank String guest,
        @NotNull @Min(1) Integer nights
) {}
```

`@NotBlank` từ chối guest `null`, `""` hoặc chỉ khoảng trắng. `@NotNull` từ chối `nights=null`; `@Min(1)` từ chối các số nhỏ hơn 1. Nếu JSON chứa `"nights":"abc"`, codec có thể thất bại **trước khi Jakarta Validation kiểm tra**.

### 5.5. BookingController.java

```java
package demo;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.Pattern;

import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class BookingController {

    // Có direct constraints trên method parameters.
    // Không đặt @Validated ở class level để dùng built-in validation.
    @GetMapping("/bookings")
    public Mono<Map<String, Object>> list(
            @RequestParam @Min(1) int page,
            @RequestHeader("X-Region")
            @Pattern(regexp = "EU|APAC") String region) {

        return Mono.just(Map.of(
                "page", page,
                "region", region
        ));
    }

    // Chỉ @Valid trên DTO; không có direct parameter constraint.
    @PostMapping("/bookings")
    public Mono<ResponseEntity<Map<String, Object>>> create(
            @Valid @RequestBody BookingRequest request) {

        return Mono.just(ResponseEntity.status(HttpStatus.CREATED)
                .body(Map.of(
                        "guest", request.guest(),
                        "nights", request.nights()
                )));
    }
}
```

Giải thích:

- `@Min(1)` và `@Pattern(...)` gắn **trực tiếp lên method parameters** của `list(...)`, nên WebFlux chọn method validation khi tham số đã được giải quyết.
- Khi `page=0` hoặc `X-Region=OTHER`, constraint thất bại, `HandlerMethodValidationException` được đưa đến exception handling.
- `create(...)` chỉ có `@Valid` trên command object, nên riêng lỗi `guest`/`nights` dẫn đến `WebExchangeBindException`.
- Cả hai method trả `Mono`, thể hiện response reactive. Demo dùng `Mono.just(...)` vì không có I/O; đây không phải ví dụ cho tính mở rộng của database reactive.
- Không gắn Spring `@Validated` ở class level. Nếu thêm nó, Spring có thể áp dụng method validation qua **AOP proxy** thay vì WebFlux built-in, khiến type exception và behavior khác ví dụ.

### 5.6. ValidationAdvice.java

```java
package demo;

import java.util.List;
import java.util.Map;

import org.springframework.http.ResponseEntity;
import org.springframework.validation.FieldError;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.bind.support.WebExchangeBindException;
import org.springframework.web.method.annotation.HandlerMethodValidationException;

@RestControllerAdvice
public class ValidationAdvice {

    @ExceptionHandler(HandlerMethodValidationException.class)
    public ResponseEntity<Map<String, Object>> handleMethod(
            HandlerMethodValidationException ex) {

        List<Integer> positions = ex.getParameterValidationResults()
                .stream()
                .map(result ->
                        result.getMethodParameter().getParameterIndex())
                .distinct()
                .sorted()
                .toList();

        int count = ex.getParameterValidationResults()
                .stream()
                .mapToInt(result -> result.getResolvableErrors().size())
                .sum();

        String code = ex.isForReturnValue()
                ? "RETURN_CONSTRAINT"
                : "METHOD_CONSTRAINT";

        // Giữ status gốc: input=400, return value=500.
        return ResponseEntity.status(ex.getStatusCode())
                .body(Map.of(
                        "code", code,
                        "parameters", positions,
                        "count", count
                ));
    }

    @ExceptionHandler(WebExchangeBindException.class)
    public ResponseEntity<Map<String, Object>> handleBody(
            WebExchangeBindException ex) {

        List<String> fields = ex.getFieldErrors().stream()
                .map(FieldError::getField)
                .distinct()
                .sorted()
                .toList();

        return ResponseEntity.status(ex.getStatusCode())
                .body(Map.of(
                        "code", "BODY_CONSTRAINT",
                        "fields", fields
                ));
    }
}
```

**Điểm thực hành:**

- Handler trả `ResponseEntity` đồng bộ nhưng **được WebFlux hỗ trợ**, vì nó tạo body nhỏ ngay trong bộ xử lý exception. Không có truy cập I/O blocking. Nếu handler cần thực hiện I/O bất đồng bộ, có thể dùng `Mono<ResponseEntity<?>>`.
- `getParameterValidationResults()` nhóm lỗi theo tham số; `getResolvableErrors()` là danh sách lỗi có thể nội suy thông điệp.
- Ví dụ trả **index của tham số** thay vì lấy raw user input hoặc annotation message. Vì vậy response ổn định theo method signature và không lộ giá trị nhạy cảm.
- `isForReturnValue()` giúp giữ mã lỗi riêng của server. Đừng ép mọi lỗi thành 400.
- `getFieldErrors()` của `WebExchangeBindException` cho field names từ một DTO. Ví dụ chỉ trả `fields`, không đưa rejected values ra client.
- Đây là **hai handler khác nhau**; không gộp bằng cách ép `WebExchangeBindException` thành `HandlerMethodValidationException` hoặc ngược lại.

Trong ứng dụng dùng `ResponseEntityExceptionHandler`/Problem Details đã được cấu hình, có thể cần sắp xếp `@ControllerAdvice` bằng `@Order` để handler tùy chỉnh có ưu tiên theo API contract. Tránh định nghĩa hai handler cạnh tranh cho cùng exception ở cùng precedence.

### 5.7. BookingControllerTest.java

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
@AutoConfigureWebTestClient
class BookingControllerTest {

    @Autowired
    WebTestClient client;

    @Test
    void validQueryAndHeader() {
        client.get()
                .uri("/bookings?page=2")
                .header("X-Region", "EU")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.page").isEqualTo(2)
                .jsonPath("$.region").isEqualTo("EU");
    }

    @Test
    void invalidPageUsesHandlerMethodValidationException() {
        client.get()
                .uri("/bookings?page=0")
                .header("X-Region", "EU")
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.code").isEqualTo("METHOD_CONSTRAINT")
                .jsonPath("$.parameters[0]").isEqualTo(0)
                .jsonPath("$.count").isEqualTo(1);
    }

    @Test
    void twoMethodArgumentsCanHaveValidationErrors() {
        client.get()
                .uri("/bookings?page=0")
                .header("X-Region", "OTHER")
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.code").isEqualTo("METHOD_CONSTRAINT")
                .jsonPath("$.parameters[0]").isEqualTo(0)
                .jsonPath("$.parameters[1]").isEqualTo(1)
                .jsonPath("$.count").isEqualTo(2);
    }

    @Test
    void invalidDtoUsesWebExchangeBindException() {
        client.post()
                .uri("/bookings")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue("{\"guest\":\"\",\"nights\":0}")
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.code").isEqualTo("BODY_CONSTRAINT")
                .jsonPath("$.fields[0]").isEqualTo("guest")
                .jsonPath("$.fields[1]").isEqualTo("nights");
    }

    @Test
    void validDtoIsCreated() {
        client.post()
                .uri("/bookings")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue("{\"guest\":\"Lan\",\"nights\":3}")
                .exchange()
                .expectStatus().isCreated()
                .expectBody()
                .jsonPath("$.guest").isEqualTo("Lan")
                .jsonPath("$.nights").isEqualTo(3);
    }

    @Test
    void malformedJsonIsNotAConstraintViolation() {
        client.post()
                .uri("/bookings")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue("{\"guest\":,}")
                .exchange()
                .expectStatus().isBadRequest();
        // Không assert BODY_CONSTRAINT / METHOD_CONSTRAINT:
        // đây là lỗi JSON decoding, không phải Bean Validation.
    }
}
```

Chạy test từ thư mục project bằng JDK 17+ và Maven:

```bash
mvn -q test
```

**Kỳ vọng:** sáu test ở trên đều pass và Maven trả exit code 0 với cấu hình đã nêu. Không cố định stdout của Maven/JUnit vì tùy bản Surefire, logging và môi trường. Các assertion kiểm tra HTTP status và **error schema do chính `ValidationAdvice` tạo ra**, nên không phụ thuộc wording mặc định của Hibernate Validator, nội suy locale hay thứ tự lỗi không được sắp xếp.

Khi chạy server:

```bash
mvn spring-boot:run
```

Gửi các request minh họa (shell POSIX):

```bash
curl -i 'http://localhost:8080/bookings?page=0' \
  -H 'X-Region: EU'

curl -i 'http://localhost:8080/bookings?page=2' \
  -H 'X-Region: OTHER'

curl -i -X POST 'http://localhost:8080/bookings' \
  -H 'Content-Type: application/json' \
  --data '{"guest":"","nights":0}'
```

**Ví dụ body JSON dự kiến** khi `page=0`, header hợp lệ:

```json
{
  "code": "METHOD_CONSTRAINT",
  "parameters": [0],
  "count": 1
}
```

Khi DTO lỗi ở hai field:

```json
{
  "code": "BODY_CONSTRAINT",
  "fields": ["guest", "nights"]
}
```

Thứ tự các **key** trong JSON object không được API bảo đảm; ví dụ chỉ dựa vào nội dung từng field và thứ tự list đã được sắp xếp. Nếu class hoặc method khác cũng áp dụng AOP validation, Global ControllerAdvice hoặc custom codec, kết quả có thể khác và cần kiểm thử cấu hình thực tế.

## 6. Reactive arguments: @RequestBody DTO khác @RequestBody Mono<DTO>

WebFlux cho phép đối số kiểu reactive publisher, điều mà Spring MVC không dùng với cùng semantics request decoding.

### 6.1. Đối số DTO thường

```java
@PostMapping("/sync-body")
public Mono<String> create(
        @Valid @RequestBody BookingRequest body) {
    return Mono.just(body.guest());
}
```

Ở đây WebFlux cần hoàn tất việc đọc JSON thành DTO trước khi cung cấp đối số Java `BookingRequest` cho controller. Nếu DTO không hợp lệ và không có method validation bao phủ, lỗi có thể được biểu diễn bằng `WebExchangeBindException`.

### 6.2. Đối số Mono<DTO>

```java
@PostMapping("/reactive-body")
public Mono<String> createReactive(
        @Valid @RequestBody Mono<BookingRequest> body) {

    return body.map(BookingRequest::guest);
}
```

Đây là fragment để chèn **vào controller có sẵn** (không phải endpoint trong demo runnable), cần import `@Valid`, `@RequestBody`, `@PostMapping`, `Mono`.

Trong trường hợp này, object được giải mã và validate **khi publisher được xử lý**. Lỗi validation có thể đến dưới dạng tín hiệu `onError` trong reactive stream, thường là `WebExchangeBindException` cho lỗi DTO. Vì lý do đó:

- Không cố khai báo `Errors`/`BindingResult` ngay sau một đối số `Mono<BookingRequest>` như thể object đã được resolve đồng bộ.
- Đối với Mono input, dùng các toán tử Reactor như `onErrorResume(...)` để chuyển lỗi thành kết quả phù hợp nếu đó là một phần thiết kế endpoint.
- Nếu không xử lý trong pipeline, cho phép cơ chế exception handling của WebFlux xử lý phù hợp.
- Không dùng `block()` để lấy DTO trong controller reactive; việc blocking trên event-loop là sai hướng thiết kế và có thể gây vấn đề hiệu năng hoặc exception.

Ví dụ **fragment** chỉ bắt validation error trong publisher:

```java
return body
        .map(dto -> "accepted:" + dto.guest())
        .onErrorResume(
                WebExchangeBindException.class,
                ex -> Mono.just("invalid-body")
        );
```

Đoạn trên là ví dụ xử lý tín hiệu lỗi, **không phải hợp đồng HTTP nên dùng nguyên xi**: trả `Mono<String>` có thể tạo 200 OK nếu không set status. Trong REST API thực tế, phải đưa về 400/ProblemDetail/ResponseEntity thích hợp; cũng cần tránh bắt mọi lỗi không liên quan thành 200.

### 6.3. Lỗi khi đọc body vẫn khác validation

JSON sai cú pháp, sai content type hoặc body quá lớn có thể gây lỗi từ reactive message reader **trước khi có DTO**. Không tự biến mọi `ServerWebInputException` thành `HandlerMethodValidationException`. Nếu cần phân loại:

1. Kiểm tra media type.
2. Kiểm tra có deserialize được DTO không.
3. Nếu có, xem object validation hay method validation có áp dụng.
4. Nếu xuất hiện exception, đọc class và cause thực tế trước khi định nghĩa error code.

## 7. @Valid chỉ yêu cầu cascade, không tự kích hoạt method validation

So sánh:

```java
// @Valid đơn thuần: validate các constraint bên trong DTO.
public Mono<Void> register(
        @Valid @RequestBody BookingRequest request) {
    return Mono.empty();
}

// @NotNull là direct constraint, có thể kích hoạt method validation
// cho phương thức controller cùng với @Valid cascade.
public Mono<Void> registerWithDirectConstraint(
        @NotNull @Valid @RequestBody BookingRequest request) {
    return Mono.empty();
}
```

Đây là **hai method signature minh họa**, cần mapping riêng trong ứng dụng thực tế; không chép cả hai trùng URL khi tích hợp.

**Điểm khác biệt:** `@NotNull` là Jakarta `@Constraint` thực sự trên tham số. Vì vậy, method validation có thể được kích hoạt, dẫn đến `HandlerMethodValidationException` khi bị vi phạm. `@Valid` không phải constraint và tự nó thường chỉ yêu cầu kiểm tra bên trong object.

Cần nhớ rằng `@RequestBody` có thuộc tính `required` mặc định true. Với body thực sự vắng mặt, WebFlux có thể từ chối trong giai đoạn argument resolution **trước khi @NotNull chạy**. Khi muốn dữ liệu tùy chọn, phải thiết kế `required=false`, nullability và validation theo contract, không trông chờ một annotation thay thế tất cả.

## 8. Errors và BindingResult khi có method validation

Trong Spring WebFlux, một controller có thể khai báo `Errors` hoặc `BindingResult` **ngay sau** một command object được bind/validate, ví dụ:

```java
@PostMapping("/forms")
public Mono<String> submit(
        @Valid @ModelAttribute("form") BookingForm form,
        BindingResult result) {

    if (result.hasErrors()) {
        return Mono.just("invalid");
    }
    return Mono.just("accepted");
}
```

Đây là fragment, `BookingForm` cần định nghĩa riêng. Quy tắc quan trọng:

- `BindingResult` phải ngay sau tham số mà nó liên kết.
- Controller có thể được gọi để tự xử lý validation errors của object thay vì Spring ném exception mặc định, nếu điều kiện phương thức cho phép.
- Khi built-in method validation áp dụng, controller chỉ được gọi nếu **tất cả lỗi** thuộc các tham số có `Errors`/`BindingResult` ngay sau.
- Nếu có **bất kỳ lỗi nào** trên một tham số **không có Errors liền kề** (ví dụ `@Min(1) @RequestParam int page`), WebFlux ném `HandlerMethodValidationException`.
- Với `Mono<BookingForm>`, không giả định `BindingResult` liền kề hoạt động như command object đồng bộ.

Ví dụ có nhiều nguồn lỗi:

```java
@GetMapping("/search")
public Mono<String> search(
        @RequestParam @Min(1) int page,
        @Valid @ModelAttribute("filters") FilterForm filters,
        BindingResult filterErrors) {

    if (filterErrors.hasErrors()) {
        return Mono.just("invalid filters");
    }
    return Mono.just("ok");
}
```

Đây là fragment. Nếu `page=0`, `filterErrors` không đại diện cho lỗi của tham số `page` nên controller có thể không được gọi, bất kể có BindingResult cho `filters`. Thiết kế một error schema cho **toàn phương thức** cần xử lý `HandlerMethodValidationException` ngoài những lỗi object riêng.

## 9. Return-value validation: lỗi phía server

Giả sử method trả về chuỗi có ràng buộc `@NotBlank`:

```java
@GetMapping("/generated-code")
@NotBlank
public String generateCode() {
    return "";
}
```

Đây là fragment của WebFlux controller, cố ý trả chuỗi vi phạm constraint để minh họa. Khi built-in method validation đánh giá kết quả trả về đồng bộ và thấy `@NotBlank` thất bại, exception có thể là `HandlerMethodValidationException` với `isForReturnValue() == true`, status mặc định **500 Internal Server Error**.

Không suy rộng rằng mọi `Mono<T>` hay `Flux<T>` tự động có từng item được kiểm tra như một `String` return value thông thường. Reactive wrapper, container-element constraints và việc validate từng tín hiệu phát ra cần được thiết kế/kiểm thử riêng theo loại dữ liệu và hỗ trợ của phiên bản framework.

**Vận hành:** một 500 do return-value validation thường biểu thị lỗi của service/server, không phải lỗi input của client. Trong response công khai, đưa thông báo tổng quát; ghi thông tin chi tiết ở server log với correlation ID nhưng không dump dữ liệu nội bộ.

## 10. @Validated ở class level và sự khác nhau giữa built-in/AOP

Spring cung cấp nhiều đường method validation:

1. **Built-in WebFlux controller method validation** (Spring Framework 6.1+): xử lý trong pipeline controller, có thể tạo `HandlerMethodValidationException`.
2. **AOP method validation** qua `MethodValidationPostProcessor`, thường áp dụng cho service bean có Spring `@Validated` ở class level: advice chạy ở ranh giới lời gọi qua proxy. Exception thường là `ConstraintViolationException` hoặc `MethodValidationException` tùy cấu hình.
3. **Jakarta Validation API trực tiếp**: code gọi `Validator`/`ExecutableValidator` và tự xử lý các `ConstraintViolation`.

Nếu muốn tận dụng **built-in controller method validation**, tài liệu Spring khuyến nghị **không đặt `@Validated` class-level trên controller**. Điều đó tránh áp dụng thêm cơ chế AOP proxy ở cấp controller và giúp exception surface thống nhất với WebFlux.

Tại service, `@Validated` và AOP có thể vẫn cần thiết. Nhưng không dùng exception từ AOP service làm bằng chứng rằng `HandlerMethodValidationException` chắc chắn được ném từ controller; chúng đến từ những cơ chế khác nhau.

**Lưu ý self-invocation:** proxy AOP có giới hạn khi method trong cùng service gọi `this.otherMethod()`; built-in WebFlux controller method validation được kích hoạt trong quá trình WebFlux gọi handler method, không đồng nghĩa mọi lời gọi Java nội bộ tới controller method cũng sẽ được validate.

## 11. Phân loại exception và thiết kế API error response

Một error response ổn định nên có tối thiểu:

- `code`: mã cho client, ví dụ `METHOD_CONSTRAINT`, `BODY_CONSTRAINT`, `INVALID_REQUEST_BODY`.
- `status`: HTTP status đúng nguồn, đặc biệt giữ 500 cho lỗi return value.
- `errors` hoặc `parameters`: thông tin đủ giúp client sửa đúng tham số nhưng không lộ giá trị nhạy cảm.
- `traceId`/request id nếu ứng dụng có tracing; không tự tạo bằng cách sao chép raw input.

Ví dụ cho lỗi ở query parameter:

```json
{
  "code": "METHOD_CONSTRAINT",
  "parameters": [0],
  "count": 1
}
```

Đây là schema của ví dụ runnable ở mục 5. Trong production, có thể trả một object chi tiết hơn:

```json
{
  "type": "https://example.org/problems/invalid-parameter",
  "title": "Request validation failed",
  "status": 400,
  "detail": "One or more request parameters are invalid",
  "invalidParams": [
    {"source": "query", "name": "page", "code": "Min"}
  ]
}
```

Mẫu thứ hai là **gợi ý contract**, không phải output của `ValidationAdvice` trong demo. Khi dùng Spring `ProblemDetail` theo **RFC 9457**, giữ các field chuẩn `type/title/status/detail/instance` và thêm extension properties có kiểm soát. Các key `invalidParams`/`source` chỉ là quy ước ứng dụng, không phải thuộc tính bắt buộc của RFC.

### Đừng trả trực tiếp getArgument()

`ParameterValidationResult#getArgument()` có thể chứa chuỗi mật khẩu, token, số giấy tờ, hồ sơ người dùng hoặc object lớn. Tương tự, `FieldError#getRejectedValue()` của `WebExchangeBindException` có thể tiết lộ thông tin nhạy cảm. Nên lấy **parameter index, tên field, error code đã chuẩn hóa** và nội suy message đã kiểm soát thay vì serializing exception.

### Localized validation messages

Các lỗi từ `getResolvableErrors()` implement `MessageSourceResolvable`. Spring có thể dùng `MessageSource` và locale của request để nội suy thông điệp. Không test logic bằng cách so sánh nguyên văn message tiếng Anh nếu ứng dụng hỗ trợ nhiều locale; test error code, parameter index hoặc constraint code ổn định hơn.

## 12. Troubleshooting: vì sao không thấy HandlerMethodValidationException?

### 12.1. Chỉ có @Valid trên DTO

Nếu không có direct `@Constraint` trên method parameter hay return value, WebFlux thường dùng **individual validation**, báo `WebExchangeBindException`. Đó là hành vi bình thường, không phải lỗi cấu hình.

### 12.2. Không có Bean Validation provider

Chỉ thêm Jakarta annotation vào project nhưng không cài Hibernate Validator/provider có thể khiến constraint không được thực thi theo kỳ vọng. Với Spring Boot WebFlux, thêm `spring-boot-starter-validation` và kiểm tra dependency tree.

### 12.3. Dùng class-level @Validated

Annotation Spring `@Validated` trên controller có thể chuyển method validation qua AOP, dẫn đến exception khác built-in. Bỏ class-level `@Validated` trên controller để thử lại theo hướng built-in Spring 6.1+.

### 12.4. Viết @Min trên String không chuyển được

Nếu `@RequestParam int page` nhận `page=abc`, giai đoạn type conversion không tạo được int. Lỗi chuyển đổi có thể được Spring biểu diễn bằng `ServerWebInputException` chứ không phải `HandlerMethodValidationException`. Hãy test `page=0` để thấy đúng validation của `@Min(1)`.

### 12.5. @RequestBody Mono<Dto> và Errors

Với publisher, DTO chưa được giải mã tại thời điểm controller nhận `Mono<Dto>`. Không đặt `Errors` ngay sau `Mono<Dto>` rồi mong hoạt động như object đồng bộ. Sử dụng Reactor operators hoặc WebFlux exception handling phù hợp.

### 12.6. Có @Valid nhưng quên @NotNull

`@Valid` không tự coi `null` là lỗi. Nếu muốn bắt buộc DTO có mặt, xem `@RequestBody(required=true)`, khả năng null và `@NotNull` thích hợp. Nếu chỉ cần validate các field bên trong, `@Valid` là đủ trong nhiều trường hợp.

### 12.7. Lỗi service AOP bị nhầm là lỗi controller

Service Bean Validation thông qua proxy AOP có thể ném `ConstraintViolationException`. Một handler chỉ bắt `HandlerMethodValidationException` sẽ không tự xử lý exception khác. Cần phân biệt source và giữ status phù hợp.

### 12.8. Dùng Spring MVC thay vì WebFlux mà không nhận ra

Nếu project có `spring-boot-starter-web` cùng `spring-boot-starter-webflux`, Boot mặc định có thể chọn Servlet/MVC. Kiểm tra stack thực sự (DispatcherServlet vs DispatcherHandler) và dependencies trước khi kết luận “WebFlux không ném exception như tài liệu”.

### 12.9. Validation group không khớp

Một constraint chỉ thuộc group tùy chỉnh có thể không chạy trong Default group. Nếu dùng `@Validated(Group.class)`, cần kiểm tra group/hints đang được active và định nghĩa constraint; không mặc định mọi annotation đều thuộc mọi group.

### 12.10. Lỗi nằm ở return value, không phải request

Nếu `isForReturnValue() == true`, status phù hợp thường là 500. Đừng biến lỗi server thành “sai request” chỉ để giữ mọi error response ở 400.

### 12.11. Lỗi container element hoặc nested bean

Một tham số kiểu List/Map có thể tạo nhiều `ParameterValidationResult` theo vị trí phần tử. Khi mapping ra API, nên lấy container index/key và field path nếu cần; không chỉ đoán “một tham số = một lỗi”.

### 12.12. Đặt handler không đúng stack hoặc bị handler khác ưu tiên

WebFlux sử dụng package `org.springframework.web.reactive.*` cho nhiều API reactive; Spring MVC sử dụng `org.springframework.web.servlet.*`. Không kế thừa MVC `ResponseEntityExceptionHandler` trong một advice WebFlux rồi dùng chữ ký `WebRequest`/Servlet request. Nếu áp dụng handler global đã có sẵn của Spring Boot, hãy kiểm tra thứ tự `@ControllerAdvice` và format Problem Details.

## 13. Chiến lược kiểm thử và giám sát

Một bộ test WebFlux nên có các trường hợp:

| Trường hợp | Dữ liệu | Kỳ vọng |
| --- | --- | --- |
| Query hợp lệ | `page=2` | HTTP 200, controller chạy |
| Query vi phạm direct constraint | `page=0` | `HandlerMethodValidationException` → 400 |
| Header vi phạm direct constraint | `X-Region: OTHER` | `HandlerMethodValidationException` → 400 |
| Nhiều tham số cùng lỗi | `page=0` và `X-Region: OTHER` | Kết quả chứa hai nhóm parameter errors |
| DTO @Valid sai | `guest=""` và `nights=0` | `WebExchangeBindException` → 400 |
| DTO @Valid hợp lệ | `guest="Lan"`, `nights=3` | HTTP 201 |
| JSON sai cú pháp | `{"guest":,}` | Lỗi decoding 400, không phải method constraint |
| Query sai kiểu | `page=abc` | Lỗi conversion 400, không phải `@Min` |
| Return value sai constraint | Return value không đáp ứng `@NotBlank` | Built-in method return validation → 500 (với kiểu trả về được hỗ trợ) |
| Body kiểu reactive | `@Valid @RequestBody Mono<Dto>` | Validation error thường phát trong reactive stream |
| Controller có @Validated class-level | Proxy AOP có thể can thiệp | Test exception type thực tế, không áp dụng mặc định của built-in |
| Thiếu validation provider | Không có runtime engine | Phải phát hiện tại build/startup/test, không coi constraints là tự hoạt động |

**Bài test tốt không chỉ assert 400.** Cần kiểm tra đúng **error code** và lớp lỗi được handler map, để biết sự cố ở JSON codec, individual DTO validation, direct method constraints hay nghiệp vụ.

Với service reactive thật, test cả request/response và **tránh blocking I/O trong controller hoặc exception handler**. Quan sát số lượng lỗi validation theo endpoint, client version và mã lỗi (không log raw payload nhạy cảm). Nếu một bản client mới làm `METHOD_CONSTRAINT` tăng đột biến, đó có thể là sự không đồng bộ về contract của query/header, không phải sự cố database.

## 14. Checklist triển khai

- [ ] Ứng dụng dùng **Spring WebFlux** thật sự, không bị chọn MVC do dependencies.
- [ ] Spring Framework phiên bản có built-in controller method validation (6.1+).
- [ ] Có Jakarta Validation provider, ví dụ qua `spring-boot-starter-validation`.
- [ ] Phân biệt `@Valid`/`@Validated` trên command object với direct `@Min`/`@Pattern` trên method parameter.
- [ ] Không dùng class-level Spring `@Validated` trên controller nếu muốn đường built-in.
- [ ] Bắt cả `HandlerMethodValidationException` và `WebExchangeBindException` nếu error contract cần nhất quán.
- [ ] Với method validation, dùng `getParameterValidationResults()` hoặc `visitResults(...)`, không ép thành BindingResult của một DTO.
- [ ] Duy trì status từ `ex.getStatusCode()`, đặc biệt **400 input / 500 return**.
- [ ] Nếu dùng `@RequestBody Mono<Dto>`, hiểu validation error nằm trong reactive stream và dùng Reactor operators phù hợp.
- [ ] Phân biệt lỗi parsing/conversion với constraint errors.
- [ ] Với `Errors`/`BindingResult` trong controller, đặt ngay sau argument tương ứng và xem có lỗi trên argument khác không.
- [ ] Chỉ xuất lỗi có ích, không log/serialize raw rejected values hoặc stack trace cho client.
- [ ] Dùng `WebTestClient` test status + JSON response cho mỗi nhánh, không phụ thuộc message theo locale.

## 15. Kết luận

**`HandlerMethodValidationException` trong WebFlux** là tín hiệu Spring đã thực hiện **method-level validation** trên controller handler, thường do có constraint như `@Min`/`@NotBlank`/`@Pattern` trực tiếp trên parameter hoặc return value. Nó mang lỗi theo **danh sách method parameters**, hỗ trợ `visitResults(...)` và phân biệt input/return constraint để dùng status thích hợp.

**`WebExchangeBindException`** là lỗi thường gặp khi **một command object riêng lẻ** của `@Valid @RequestBody`/`@ModelAttribute`/`@RequestPart` không hợp lệ. Cả hai cần được xử lý nếu ứng dụng muốn API error response nhất quán; không gộp chúng với JSON decoding error, service AOP validation hay exception Spring MVC.

Mấu chốt để debug: **xác định vị trí constraint trên chữ ký controller và lúc validation diễn ra**, rồi xem đúng exception type. Khi đã rõ boundary, việc trả response chuẩn, nội suy lỗi theo locale và kiểm thử bằng WebTestClient sẽ nhất quán hơn.

## Tài liệu tham khảo

- [Spring Framework 6.2 — WebFlux Controller Validation](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-validation.html)
- [Spring Framework 6.2 — WebFlux @RequestBody](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/requestbody.html)
- [Spring Framework 6.2 — WebFlux Error Responses / RFC 9457](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/ann-rest-exceptions.html)
- [Spring Framework 6.2 — HandlerMethodValidationException API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/web/method/annotation/HandlerMethodValidationException.html)
- [Spring Framework 6.2 — ParameterValidationResult API](https://docs.spring.io/spring-framework/docs/6.2.1/javadoc-api/org/springframework/validation/method/ParameterValidationResult.html)
- [Spring Framework 6.2 — WebFlux Config and Validator integration](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/config.html)
- [Spring Framework 6.2 — Bean Validation and AOP-based Method Validation](https://docs.spring.io/spring-framework/reference/6.2/core/validation/beanvalidation.html)
