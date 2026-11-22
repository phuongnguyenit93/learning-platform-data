# Xây dựng phản hồi lỗi API thống nhất cho Spring MVC hoặc WebFlux

## 1. Mục tiêu thực hành và tiêu chí hoàn thành

Một API Spring thường phát sinh lỗi ở nhiều giai đoạn: parse JSON, chuyển đổi kiểu, data binding, Bean Validation, method validation, phân quyền, xử lý nghiệp vụ và truy cập hệ thống phụ thuộc. Nếu mỗi nơi trả một JSON khác nhau, client phải viết nhiều nhánh xử lý khó bảo trì, trong khi thông tin lỗi nội bộ dễ bị tiết lộ.

Mục tiêu là tạo một **error response contract** nhất quán và kiểm thử được, dùng **`ProblemDetail` (RFC 9457)** trên **Spring MVC** hoặc **Spring WebFlux**:

1. Trả đúng **HTTP status**, không biến mọi exception thành 400 hoặc 500.
2. Dùng cùng định dạng cho **validation errors**, JSON không đọc được, lỗi nghiệp vụ, resource không tồn tại và lỗi máy chủ.
3. Có **machine-readable `code`** ổn định; phía client không cần so khớp tiếng Anh/tiếng Việt trong thông điệp.
4. Có **`errorId`** để tra cứu log, không gửi stack trace hoặc rejected values.
5. Có danh sách **`violations`** cho lỗi field/parameter theo hợp đồng public DTO; có thể là mảng rỗng trong lỗi không phải validation.
6. Hỗ trợ **`instance`** là URI đường dẫn request, `type`, `title`, `status`, `detail` theo RFC 9457.
7. Tách lỗi do **client input** (thường 4xx) khỏi **server return value** hoặc internal failure (5xx).
8. Giữ nguyên headers chuẩn như `Allow` ở 405, `Retry-After` ở 429/503 nếu có, thay vì tùy tiện ghi đè.
9. Có **MockMvc tests** cho MVC và **WebTestClient tests** cho WebFlux; không giả định hai stack dùng chung exception classes và handler signatures.
10. Không dùng error body để thay HTTP status, không lộ exception class, database SQL, token, body raw hoặc stack trace.

Ví dụ sẽ xây **một Spring MVC project đầy đủ** rồi minh họa **cách chuyển sang WebFlux** ở một project khác. Hai lựa chọn cùng chia sẻ schema, codes và policy, nhưng **không** chạy cả `spring-boot-starter-web` và `spring-boot-starter-webflux` trong một demo để rồi đoán runtime web stack nào được Spring Boot chọn.

## 2. Chọn RFC 9457 `ProblemDetail` thay vì một JSON tự tạo tùy hứng

Spring Framework 6.x hỗ trợ `ProblemDetail`, `ErrorResponse`, `ErrorResponseException` và `ResponseEntityExceptionHandler` cho cả Servlet MVC lẫn WebFlux. `ProblemDetail` nắm giữ năm trường chuẩn, cộng với custom properties:

| Trường | Bắt buộc theo thiết kế ví dụ? | Ý nghĩa |
| --- | --- | --- |
| `type` | Có | Loại vấn đề, ở ví dụ dùng `about:blank`; nếu xây tài liệu máy đọc được có thể dùng URI loại lỗi ổn định. |
| `title` | Có | Tiêu đề ngắn, không chứa dữ liệu nhạy cảm. |
| `status` | Có | Số HTTP status; **phải trùng status ở response line**. |
| `detail` | Có | Lời giải thích an toàn cho người dùng, có thể i18n. |
| `instance` | Có trong ví dụ | URI của occurrence/request path; tuyệt đối không nhét token/query secrets vào đây. |
| `code` | Custom, có | Mã ổn định để client xử lý. |
| `errorId` | Custom, có | ID của một error occurrence; cần liên kết với hệ thống log/trace thật khi triển khai. |
| `violations` | Custom, có | Danh sách field/parameter và thông điệp đã whitelist; rỗng nếu không phải validation. |

**Ví dụ response** (các UUID là minh họa, không phải output cố định):

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/problem+json

{
  "type": "about:blank",
  "title": "Bad Request",
  "status": 400,
  "detail": "One or more fields are invalid.",
  "instance": "/api/items",
  "code": "VALIDATION_FAILED",
  "errorId": "a41e2813-7a60-41e3-8e0e-d775de7e28e6",
  "violations": [
    {"field": "name", "message": "Must not be blank"},
    {"field": "quantity", "message": "Must be at least the minimum"}
  ]
}
~~~

Đây là **ví dụ hình dạng JSON**; thứ tự keys không quan trọng, giá trị `errorId` thay đổi theo request, và error messages cụ thể phụ thuộc policy. Với Spring/Jackson, custom entries trong `ProblemDetail.properties` được serialize ra **top-level JSON fields**, thay vì một map lồng tên `properties`.

### Không lạm dụng `type`

RFC 9457 `type` dùng để phân loại vấn đề. `about:blank` có nghĩa status/title là phân loại chung. Nếu dùng URI như `https://api.example.com/problems/validation`, hãy dùng một URI được ứng dụng **thực sự quản lý và tài liệu hóa**, không phát minh URI mà không có docs. Ví dụ runnable chọn `about:blank` và mã `code`; một API lớn có thể nâng cấp sang **type URI registry** sau.

### `errorId` khác traceId

Trong demo, `errorId` được sinh bằng `UUID.randomUUID()` và trả cho client. Khi xảy ra exception bất ngờ, handler log cùng ID. Trong hệ thống thực tế, cần tương quan với distributed tracing (`traceId`/`spanId` từ OpenTelemetry hoặc Micrometer), request logging, log retention và access policy. **UUID trong JSON một mình không bảo đảm có thể tra cứu log** nếu không được ghi kèm sự kiện server.

Không đọc thẳng header `X-Request-ID` từ client rồi coi là ID đáng tin; nếu cần tiếp nhận external correlation ID, phải validate format, giới hạn độ dài và gắn với server-generated ID khi thích hợp.

## 3. Phân loại lỗi trước khi viết handler

| Nguyên nhân | Spring MVC thường gặp | Spring WebFlux thường gặp | Status khuyến nghị |
| --- | --- | --- | --- |
| `@Valid @RequestBody` DTO không hợp lệ | `MethodArgumentNotValidException` | `WebExchangeBindException` | 400 |
| Method parameters (ví dụ `@RequestParam @Min(1)`) không hợp lệ | `HandlerMethodValidationException` | `HandlerMethodValidationException` | 400 |
| **Giá trị trả về của controller method vi phạm constraint** | `HandlerMethodValidationException` | `HandlerMethodValidationException` | **500** |
| JSON sai cú pháp/không đọc được | `HttpMessageNotReadableException` | `ServerWebInputException` hoặc codec cause tương ứng | 400 |
| Query/path number không convert được | `TypeMismatchException`, `MethodArgumentTypeMismatchException` | `ServerWebInputException` / type conversion error | 400 |
| Thiếu required query/header/body | `MissingServletRequestParameterException` hoặc subtype khác | `MissingRequestValueException` / `ServerWebInputException` | 400 |
| Request method không hỗ trợ | `HttpRequestMethodNotSupportedException` | `MethodNotAllowedException` | 405 |
| `Content-Type` không hỗ trợ | `HttpMediaTypeNotSupportedException` | `UnsupportedMediaTypeStatusException` | 415 |
| `Accept` không thương lượng được | `HttpMediaTypeNotAcceptableException` | `NotAcceptableStatusException` | 406 |
| Resource domain không tồn tại | Exception nghiệp vụ riêng | Exception nghiệp vụ riêng | 404 |
| Business conflict (duplicate/version mismatch) | Exception nghiệp vụ riêng | Exception nghiệp vụ riêng | 409 |
| Người dùng thiếu authentication | Spring Security entry point | Reactive Security entry point | 401 |
| Authenticated nhưng không được phép | Spring Security access denied handler | Reactive access denied handler | 403 |
| Request quá lớn, rate limit | Multipart/gateway/rate limiter exceptions | Codec/gateway/rate limiter exceptions | 413 / 429 theo chính sách |
| Database/serialization/bug | Unhandled runtime exception | Unhandled reactive signal/exception | 500 |
| Downstream quá tải/chưa sẵn sàng | Service/gateway exception đã phân loại | Reactive downstream exception đã phân loại | 503/504 nếu phù hợp |

**Không gom tất cả vào 400.** Với method validation của controller ở Spring 6.1+, `HandlerMethodValidationException#getStatusCode()` trả **400 cho input violations** và **500 cho return-value violations**. Với Bean Validation ở **service AOP**, `ConstraintViolationException` không tự cho biết HTTP status của một request: đó có thể là input do hệ thống nội bộ tạo hoặc server return value. Cần dịch trạng thái ở boundary theo ngữ cảnh.

**Không gom tất cả thành 500.** Một request `quantity=0` hợp lệ về JSON nhưng sai `@Min(1)` phải nhận 400. Một resource thiếu theo hợp đồng phải là 404, không phải 500.

## 4. Luồng tổng thể và trách nhiệm từng tầng

~~~text
HTTP request
    |
    +-- Servlet MVC stack ------------------------------+
    |    HttpMessageConverter / @ModelAttribute binding
    |    @Valid + method validation
    |    Handler / Controller -> service -> repository
    |    ExceptionHandlerExceptionResolver
    |    @RestControllerAdvice / ResponseEntityExceptionHandler
    |
    +-- Reactive WebFlux stack -------------------------+
         HttpMessageReader / reactive codec
         @Valid + method validation
         Annotated handler -> Mono/Flux service
         @ExceptionHandler / ResponseEntityExceptionHandler
         WebExceptionHandler fallback
    |
    v
Internal exception category + safe error metadata
    |
    v
ProblemDetail (RFC 9457)
    |
    +-- HTTP status, Content-Type, relevant headers
    +-- type/title/status/detail/instance
    +-- code/errorId/violations
    |
    v
API client
~~~

**Quan trọng:** `@RestControllerAdvice` không phải một “bộ lọc bắt mọi thứ”:
- Lỗi từ **Servlet filter chain**, Spring Security authentication/authorization, container hoặc proxy/gateway có thể phát sinh **ngoài MVC controller exception resolver**.
- Với WebFlux, lỗi từ `WebFilter`, handler function routes và trường hợp response đã commit có thể cần `WebExceptionHandler` hoặc `ErrorWebExceptionHandler` riêng.
- Nếu response đã bắt đầu streaming/đã commit, không thể bảo đảm thay bằng một JSON ProblemDetail mới.
- Boot default `/error`, static-resource fallback hoặc error dispatch có thể tạo response theo policy riêng; cần test end-to-end và tích hợp ở đúng tầng.

Để thống nhất thật trong production, phân định **controller advice**, **security handlers**, **fallback error infrastructure**, và **gateway** như các phần riêng có cùng contract.

## 5. Thiết kế mã lỗi ổn định

Ví dụ mã cho client:

| `code` | HTTP | Khi nào client dùng |
| --- | --- | --- |
| `VALIDATION_FAILED` | 400 | Highlight các `violations.field`, sửa form. |
| `MALFORMED_BODY` | 400 | JSON/body không đọc được, sửa payload. |
| `BAD_REQUEST` | 400 | Thiếu hoặc sai tham số/cấu trúc yêu cầu khác. |
| `RESOURCE_NOT_FOUND` | 404 | Resource domain không tồn tại hoặc policy che tồn tại. |
| `METHOD_NOT_ALLOWED` | 405 | Method route sai, client thay HTTP verb. |
| `NOT_ACCEPTABLE` | 406 | Header Accept không hỗ trợ. |
| `UNSUPPORTED_MEDIA_TYPE` | 415 | Gửi đúng Content-Type/format. |
| `CONFLICT` | 409 | Conflict với trạng thái hiện tại, ví dụ duplicate. |
| `INTERNAL_ERROR` | 500 | Hiển thị thông báo chung và báo `errorId`. |
| `SERVICE_UNAVAILABLE` | 503 | Retry theo policy, có thể cần Retry-After. |

Mã `code` **không được thay đổi chỉ vì locale thay đổi**. `detail`, `title` và `violations.message` có thể được localize qua `MessageSource`/resource bundles, nhưng client không so khớp bằng văn bản. Nếu cần versioning, quản lý code registry và deprecation policy; tránh đưa internal exception Java class names vào API error codes.

### `violations` và field paths

Một field entry có cấu trúc:

~~~json
{"field":"name","message":"Must not be blank"}
~~~

Đối với lỗi cấp object hoặc cross-field, có thể dùng một field marker public ổn định như `"_object"`. Không trả `BindingResult#getRejectedValue()`, raw JWT, password, SQL parameter hoặc giá trị PII. Các field names chỉ nên đến từ **request DTO/schema công khai**, không phải nội bộ entity/repository.

Mảng `violations` có thể rỗng với 404, 409, 415 hoặc 500. Giữ trường này luôn xuất hiện giúp client có schema nhất quán. Nếu giới hạn số lượng errors trả về (ví dụ 20) cần document truncation để ngăn payload rất lớn.

## 6. MVC: dự án runnable với Spring Boot 3.5.x và Java 17+

Bản mẫu dùng Spring Boot **3.5.16** và Spring Framework 6.2.x để minh họa API đã xác minh. Phiên bản 3.5.x là nhánh cũ ở thời điểm viết; **ứng dụng production nên dùng bản Boot/Framework còn được hỗ trợ và đã có security patches**, không sao chép số phiên bản demo làm khuyến nghị vận hành. Mã có thể cần điều chỉnh imports/config khi chuyển sang Boot 4.x/Spring 7.x.

Cấu trúc:

~~~text
pom.xml
src/main/java/com/example/problems/
  ProblemApplication.java
  CreateItemRequest.java
  ItemView.java
  ApiViolation.java
  ApiProblemFactory.java
  ItemNotFoundException.java
  DuplicateItemException.java
  ItemController.java
  MvcApiProblemAdvice.java
src/test/java/com/example/problems/
  MvcApiProblemTest.java
~~~

Đây là **project REST MVC độc lập**. Không đưa `spring-boot-starter-webflux` vào pom này.

### 6.1. `pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
           https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>api-problems-mvc</artifactId>
    <version>0.0.1-SNAPSHOT</version>

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

`spring-boot-starter-validation` cung cấp Bean Validation provider; riêng `spring-boot-starter-web` không bảo đảm có provider ở mọi Boot phiên bản/cấu hình. Dự án tự viết `@RestControllerAdvice` nên không phụ thuộc property `spring.mvc.problemdetails.enabled` để bật nó. Nếu đã bật Boot-generated ProblemDetail advice trong ứng dụng khác, phải kiểm soát advice ordering/khả năng trùng handler.

### 6.2. `ProblemApplication.java`

~~~java
package com.example.problems;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ProblemApplication {

    public static void main(String[] args) {
        SpringApplication.run(ProblemApplication.class, args);
    }
}
~~~

### 6.3. Input DTO `CreateItemRequest.java`

~~~java
package com.example.problems;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

public record CreateItemRequest(
        @NotBlank String name,
        @Min(1) int quantity) {
}
~~~

**Tại sao dùng record?** Request schema chỉ có hai client-owned fields, không bind trực tiếp JPA entity. Khi `name=""` hoặc `quantity=0`, Jakarta Bean Validation có thể đưa field errors vào `MethodArgumentNotValidException`. Khi JSON sai cú pháp hoặc `quantity="oops"` không chuyển được, Jackson/`HttpMessageConverter` có thể thất bại **trước Bean Validation**, theo đường `HttpMessageNotReadableException`.

### 6.4. Response DTO `ItemView.java`

~~~java
package com.example.problems;

public record ItemView(
        String id,
        String name,
        int quantity) {
}
~~~

Không trả entity hay internal fields như secret/tenant/role chỉ để hoàn thành response; business data response phải có DTO/hợp đồng riêng.

### 6.5. Field violation `ApiViolation.java`

~~~java
package com.example.problems;

public record ApiViolation(
        String field,
        String message) {
}
~~~

Type này được serialize vào `violations`. Không có trường `rejectedValue` hoặc stack trace. Khi cần mã per-field, có thể mở rộng bằng public `reasonCode` nhưng phải versioning nhất quán.

### 6.6. Factory chung `ApiProblemFactory.java`

~~~java
package com.example.problems;

import org.springframework.http.HttpStatus;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.ProblemDetail;

import java.net.URI;
import java.util.List;
import java.util.UUID;

public final class ApiProblemFactory {

    private ApiProblemFactory() {
    }

    public static ProblemDetail create(
            HttpStatusCode status,
            String code,
            String detail,
            List<ApiViolation> violations,
            String path) {

        ProblemDetail problem = ProblemDetail.forStatus(status);
        problem.setType(URI.create("about:blank"));

        HttpStatus standard = HttpStatus.resolve(status.value());
        problem.setTitle(
                standard == null ? "HTTP Error"
                                 : standard.getReasonPhrase());

        problem.setDetail(detail);

        // Chỉ dùng đường dẫn, không lấy query string có thể chứa token.
        if (path != null && path.startsWith("/")) {
            problem.setInstance(URI.create(path));
        }

        problem.setProperty("code", code);
        problem.setProperty(
                "errorId", UUID.randomUUID().toString());
        problem.setProperty("violations", violations);

        return problem;
    }

    public static String codeFor(HttpStatusCode status) {
        return switch (status.value()) {
            case 400 -> "BAD_REQUEST";
            case 404 -> "RESOURCE_NOT_FOUND";
            case 405 -> "METHOD_NOT_ALLOWED";
            case 406 -> "NOT_ACCEPTABLE";
            case 409 -> "CONFLICT";
            case 415 -> "UNSUPPORTED_MEDIA_TYPE";
            case 429 -> "RATE_LIMITED";
            case 503 -> "SERVICE_UNAVAILABLE";
            default -> status.is5xxServerError()
                    ? "INTERNAL_ERROR" : "HTTP_ERROR";
        };
    }

    public static String detailFor(HttpStatusCode status) {
        if (status.is5xxServerError()) {
            return "An internal error occurred.";
        }

        return switch (status.value()) {
            case 400 -> "The request is invalid.";
            case 404 -> "The requested resource was not found.";
            case 405 -> "This HTTP method is not supported.";
            case 406 -> "No acceptable response representation.";
            case 409 -> "The request conflicts with current state.";
            case 415 -> "Unsupported request media type.";
            case 429 -> "Too many requests.";
            default -> "The request could not be completed.";
        };
    }
}
~~~

**Đây là file dùng chung cho MVC và WebFlux**: chỉ import `spring-web` classes, không import Servlet hoặc Reactor. `ProblemDetail` lưu `code/errorId/violations` trong custom properties, được Spring Jackson module serialize ra các keys ngang hàng với `status`.

`errorId` thay đổi mỗi lần gọi `create`. Đối với exception 500, controller advice sẽ log đúng ID đó. Với lỗi 4xx, không cần log raw request body vì người dùng có thể nhập dữ liệu nhạy cảm.

`URI.create(path)` giả định servlet path đã được container encode hợp lệ; trong ứng dụng cứng hóa chống path bất thường, có thể đặt `instance` bằng route template hoặc URI đã được sanitize. Tránh đưa raw query string, Authorization headers hay request payload vào instance.

### 6.7. Domain exception classes

`ItemNotFoundException.java`:

~~~java
package com.example.problems;

public final class ItemNotFoundException
        extends RuntimeException {
}
~~~

`DuplicateItemException.java`:

~~~java
package com.example.problems;

public final class DuplicateItemException
        extends RuntimeException {
}
~~~

Chúng được dùng **có chủ đích** tại business boundary. Không nên chuyển `IllegalArgumentException` bất kỳ thành 400 hoặc `IllegalStateException` bất kỳ thành 409; những exception chung đó có thể phản ánh bug backend, không phải lỗi client có thể sửa.

### 6.8. Controller `ItemController.java`

~~~java
package com.example.problems;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.List;

@RestController
@RequestMapping("/api/items")
public class ItemController {

    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<ItemView> create(
            @Valid @RequestBody CreateItemRequest request) {

        if ("conflict".equalsIgnoreCase(request.name())) {
            throw new DuplicateItemException();
        }

        ItemView view = new ItemView(
                "item-42", request.name(), request.quantity());

        return ResponseEntity.status(HttpStatus.CREATED)
                .body(view);
    }

    @GetMapping("/{id}")
    public ItemView get(@PathVariable String id) {
        if ("missing".equals(id)) {
            throw new ItemNotFoundException();
        }

        return new ItemView(id, "Sample", 2);
    }

    // Constraint trực tiếp trên controller parameter:
    // Spring MVC 6.1+ dùng built-in method validation.
    @GetMapping("/search")
    public List<ItemView> search(
            @RequestParam("limit") @Min(1) int limit) {
        return List.of(new ItemView("item-1", "Sample", limit));
    }

    // Cố ý vi phạm return-value constraint để test HTTP 500.
    @NotBlank
    @GetMapping(path = "/invalid-output",
            produces = MediaType.TEXT_PLAIN_VALUE)
    public String invalidOutput() {
        return "";
    }

    // Chỉ dùng cho test: exception text không được tiết lộ.
    @GetMapping("/explode")
    public String unexpectedFailure() {
        throw new IllegalStateException(
                "Sensitive database details must not leak");
    }
}
~~~

**Không đặt class-level `@Validated` lên MVC controller** này. Spring Framework 6.1+ có built-in controller method validation; class-level `@Validated` có thể chuyển method validation sang AOP proxy và thay exception pipeline. `@Valid @RequestBody` thường tạo `MethodArgumentNotValidException`, còn `@Min` trên query parameter và `@NotBlank` trên controller return tạo `HandlerMethodValidationException` tương ứng.

Không dùng `/explode` hoặc `/invalid-output` như endpoint thật. Chúng là controlled test fixtures để đo hợp đồng 500.

### 6.9. Advice `MvcApiProblemAdvice.java`

Đây là phần trung tâm: Spring MVC `ResponseEntityExceptionHandler` **ở package Servlet MVC**, cung cấp handler cho framework exceptions. Ta override một số hooks để gắn business codes, rồi giữ một nơi tạo schema:

~~~java
package com.example.problems;

import jakarta.servlet.http.HttpServletRequest;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
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
import org.springframework.web.context.request.ServletWebRequest;
import org.springframework.web.context.request.WebRequest;
import org.springframework.web.method.annotation.HandlerMethodValidationException;
import org.springframework.web.servlet.mvc.method.annotation.ResponseEntityExceptionHandler;

import java.util.List;

@RestControllerAdvice
@Order(Ordered.HIGHEST_PRECEDENCE)
public class MvcApiProblemAdvice
        extends ResponseEntityExceptionHandler {

    private static final Logger LOG =
            LoggerFactory.getLogger(MvcApiProblemAdvice.class);

    private static String path(WebRequest request) {
        if (request instanceof ServletWebRequest servlet) {
            return servlet.getRequest().getRequestURI();
        }
        return null;
    }

    private static String safeMessage(FieldError error) {
        return switch (String.valueOf(error.getCode())) {
            case "NotBlank" -> "Must not be blank";
            case "Min" -> "Must be at least the minimum";
            default -> "Invalid value";
        };
    }

    // Individual @Valid @RequestBody / @ModelAttribute:
    @Override
    protected ResponseEntity<Object> handleMethodArgumentNotValid(
            MethodArgumentNotValidException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        List<ApiViolation> violations =
                ex.getBindingResult().getFieldErrors()
                        .stream()
                        .map(err -> new ApiViolation(
                                err.getField(), safeMessage(err)))
                        .distinct()
                        .toList();

        ProblemDetail problem = ApiProblemFactory.create(
                status,
                "VALIDATION_FAILED",
                "One or more fields are invalid.",
                violations,
                path(request));

        return handleExceptionInternal(
                ex, problem, headers, status, request);
    }

    // Direct parameter constraints and return-value constraints:
    @Override
    protected ResponseEntity<Object>
    handleHandlerMethodValidationException(
            HandlerMethodValidationException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        if (ex.isForReturnValue()) {
            // Không trả details của server-generated output.
            ProblemDetail problem = ApiProblemFactory.create(
                    status,
                    "INTERNAL_ERROR",
                    "An internal error occurred.",
                    List.of(),
                    path(request));

            return handleExceptionInternal(
                    ex, problem, headers, status, request);
        }

        ProblemDetail problem = ApiProblemFactory.create(
                status,
                "VALIDATION_FAILED",
                "One or more parameters are invalid.",
                List.of(new ApiViolation(
                        "parameter", "Invalid value")),
                path(request));

        return handleExceptionInternal(
                ex, problem, headers, status, request);
    }

    // JSON parse/converter errors:
    @Override
    protected ResponseEntity<Object> handleHttpMessageNotReadable(
            HttpMessageNotReadableException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        ProblemDetail problem = ApiProblemFactory.create(
                status,
                "MALFORMED_BODY",
                "Request body is missing or cannot be read.",
                List.of(),
                path(request));

        return handleExceptionInternal(
                ex, problem, headers, status, request);
    }

    // Chạy ở cuối quá trình xử lý các framework exceptions
    // do ResponseEntityExceptionHandler nhận:
    @Override
    protected ResponseEntity<Object> createResponseEntity(
            Object body,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        ProblemDetail problem;

        if (body instanceof ProblemDetail pd
                && pd.getProperties() != null
                && pd.getProperties().containsKey("code")) {
            problem = pd;
        }
        else {
            // Normalise cả framework exceptions chưa override.
            // Không echo body/messsage gốc có thể nhạy cảm.
            problem = ApiProblemFactory.create(
                    status,
                    ApiProblemFactory.codeFor(status),
                    ApiProblemFactory.detailFor(status),
                    List.of(),
                    path(request));
        }

        // Giữ nguyên headers do framework cung cấp (Allow,...).
        return super.createResponseEntity(
                problem, headers, status, request);
    }

    @ExceptionHandler(ItemNotFoundException.class)
    public ResponseEntity<ProblemDetail> notFound(
            ItemNotFoundException ex,
            HttpServletRequest request) {

        ProblemDetail problem = ApiProblemFactory.create(
                HttpStatus.NOT_FOUND,
                "RESOURCE_NOT_FOUND",
                "The requested item was not found.",
                List.of(),
                request.getRequestURI());

        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .body(problem);
    }

    @ExceptionHandler(DuplicateItemException.class)
    public ResponseEntity<ProblemDetail> conflict(
            DuplicateItemException ex,
            HttpServletRequest request) {

        ProblemDetail problem = ApiProblemFactory.create(
                HttpStatus.CONFLICT,
                "CONFLICT",
                "An item with this name already exists.",
                List.of(),
                request.getRequestURI());

        return ResponseEntity.status(HttpStatus.CONFLICT)
                .body(problem);
    }

    @ExceptionHandler(Exception.class)
    public ResponseEntity<ProblemDetail> unexpected(
            Exception ex,
            HttpServletRequest request) {

        ProblemDetail problem = ApiProblemFactory.create(
                HttpStatus.INTERNAL_SERVER_ERROR,
                "INTERNAL_ERROR",
                "An internal error occurred.",
                List.of(),
                request.getRequestURI());

        // ID trả cho client trùng ID ghi ở server log:
        Object errorId = problem.getProperties().get("errorId");
        LOG.error("Unhandled API error, errorId={}", errorId, ex);

        return ResponseEntity
                .status(HttpStatus.INTERNAL_SERVER_ERROR)
                .body(problem);
    }
}
~~~

### 6.10. Tại sao thiết kế này dùng đúng Spring hooks?

- `ResponseEntityExceptionHandler` xử lý **Spring MVC framework exceptions** trong một advice. Không tạo `@ExceptionHandler(MethodArgumentNotValidException.class)` **trùng** với exception handler đã định nghĩa trong base class; hãy override protected `handleMethodArgumentNotValid`.
- `handleHandlerMethodValidationException` giữ **status do Spring truyền vào**, bao gồm **500** cho return-value violation. Không ép status về 400.
- `handleHttpMessageNotReadable` chỉ tạo thông điệp public chung, không expose Jackson parse stack trace hoặc vị trí dữ liệu nhạy cảm.
- `createResponseEntity` là điểm cuối để chuẩn hóa những Spring exceptions chưa override; giữ lại `HttpHeaders`. Dùng cùng factory giúp mọi response có `code`, `errorId` và `violations`.
- `@ExceptionHandler(ItemNotFoundException.class)` và `@ExceptionHandler(DuplicateItemException.class)` là **business mappings riêng**; status từ exception domain không nên suy ra từ class name thông thường.
- `@ExceptionHandler(Exception.class)` là fallback **bên trong MVC exception resolver**, không đảm bảo bao phủ filters, Security, Boot fallback, streaming hoặc gateway.
- `@Order(HIGHEST_PRECEDENCE)` giúp custom advice có thứ tự rõ khi ứng dụng có advice khác; không thay thế rà soát các advice hiện hữu và Spring Boot Problem Details auto-configuration.
- Logging chỉ dùng `errorId` và exception trong server logs. Không trả `ex.getMessage()`, SQL, stack trace hoặc `BindingResult` cho client.
- Validation errors được giới hạn trong public `FieldError#getField()` cùng safe message mapping; không gửi rejected values.
- Mảng `violations` **luôn có mặt**. Với method-level validation, demo dùng generic field `"parameter"` để tránh suy luận sai tên parameter. Bản nâng cao có thể duyệt `ex.getAllValidationResults()`/visitor để trả tên parameter sau khi sanitize.

**Cảnh báo:** `@ExceptionHandler(Exception.class)` không nên dùng để biến lỗi cấu hình, phân quyền hoặc return value thành lỗi 400. Nó chỉ map **unexpected MVC failures -> 500** với nội dung an toàn; security handlers ở tầng filter cần triển khai riêng.

## 7. Kiểm thử MVC bằng MockMvc

Tạo `src/test/java/com/example/problems/MvcApiProblemTest.java`:

~~~java
package com.example.problems;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.not;
import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class MvcApiProblemTest {

    @Autowired
    MockMvc mvc;

    @Test
    void validItemReturns201WithoutProblemBody() throws Exception {
        mvc.perform(post("/api/items")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                            {"name":"Notebook","quantity":2}
                            """))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.name")
                        .value("Notebook"))
                .andExpect(jsonPath("$.quantity").value(2));
    }

    @Test
    void blankNameReturnsUnifiedValidationProblem()
            throws Exception {
        mvc.perform(post("/api/items")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                            {"name":"","quantity":2}
                            """))
                .andExpect(status().isBadRequest())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_PROBLEM_JSON))
                .andExpect(jsonPath("$.status").value(400))
                .andExpect(jsonPath("$.code")
                        .value("VALIDATION_FAILED"))
                .andExpect(jsonPath("$.instance")
                        .value("/api/items"))
                .andExpect(jsonPath("$.errorId").isString())
                .andExpect(jsonPath("$.violations[0].field")
                        .value("name"));
    }

    @Test
    void lowQuantityAlsoUsesValidationCode()
            throws Exception {
        mvc.perform(post("/api/items")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                            {"name":"Notebook","quantity":0}
                            """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("VALIDATION_FAILED"))
                .andExpect(jsonPath("$.violations[0].field")
                        .value("quantity"));
    }

    @Test
    void malformedJsonIsNotBeanValidationError()
            throws Exception {
        mvc.perform(post("/api/items")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"name\":"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.status").value(400))
                .andExpect(jsonPath("$.code")
                        .value("MALFORMED_BODY"))
                .andExpect(jsonPath("$.violations").isArray());
    }

    @Test
    void wrongJsonTypeIsMalformedBody() throws Exception {
        mvc.perform(post("/api/items")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                            {"name":"Notebook","quantity":"oops"}
                            """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("MALFORMED_BODY"));
    }

    @Test
    void directMethodConstraintCreates400()
            throws Exception {
        mvc.perform(get("/api/items/search")
                    .param("limit", "0"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("VALIDATION_FAILED"))
                .andExpect(jsonPath("$.violations").isArray());
    }

    @Test
    void controllerReturnConstraintCreates500()
            throws Exception {
        mvc.perform(get("/api/items/invalid-output"))
                .andExpect(status().isInternalServerError())
                .andExpect(jsonPath("$.status").value(500))
                .andExpect(jsonPath("$.code")
                        .value("INTERNAL_ERROR"))
                .andExpect(jsonPath("$.violations").isArray());
    }

    @Test
    void domainNotFoundHas404Code() throws Exception {
        mvc.perform(get("/api/items/missing"))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.code")
                        .value("RESOURCE_NOT_FOUND"))
                .andExpect(jsonPath("$.instance")
                        .value("/api/items/missing"));
    }

    @Test
    void duplicateItemHas409Code() throws Exception {
        mvc.perform(post("/api/items")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                            {"name":"conflict","quantity":2}
                            """))
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.code").value("CONFLICT"));
    }

    @Test
    void wrongContentTypeReturns415() throws Exception {
        mvc.perform(post("/api/items")
                    .contentType(MediaType.TEXT_PLAIN)
                    .content("not json"))
                .andExpect(status().isUnsupportedMediaType())
                .andExpect(jsonPath("$.code")
                        .value("UNSUPPORTED_MEDIA_TYPE"));
    }

    @Test
    void unsupportedMethodReturns405() throws Exception {
        mvc.perform(put("/api/items/missing"))
                .andExpect(status().isMethodNotAllowed())
                .andExpect(header().exists("Allow"))
                .andExpect(jsonPath("$.code")
                        .value("METHOD_NOT_ALLOWED"));
    }

    @Test
    void unexpectedExceptionHidesInternalMessage()
            throws Exception {
        mvc.perform(get("/api/items/explode"))
                .andExpect(status().isInternalServerError())
                .andExpect(jsonPath("$.code")
                        .value("INTERNAL_ERROR"))
                .andExpect(jsonPath("$.errorId").isString())
                .andExpect(content().string(
                        not(containsString(
                                "Sensitive database details"))));
    }

    @Test
    void missingRequiredQueryParamIs400()
            throws Exception {
        mvc.perform(get("/api/items/search"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("BAD_REQUEST"));
    }
}
~~~

Có **13 MockMvc tests** xác nhận:

- Happy path không bị wrap thành ProblemDetail.
- Validation DTO với 400 và fields; `quantity=0` và `name=""`.
- Malformed JSON và Jackson type mismatch được phân loại khác `@Valid`.
- Controller parameter method validation → 400.
- **Controller return-value validation → 500**, tránh phân loại nhầm là lỗi người dùng.
- Domain not found 404, conflict 409.
- `Content-Type` sai 415, method sai 405 và header `Allow` được giữ.
- Internal exception không tiết lộ message nhạy cảm, có `errorId`.
- Thiếu query parameter được map 400 với generic code.

Lệnh chạy:

~~~bash
mvn test
mvn spring-boot:run
~~~

Hoặc nếu đã tạo Maven wrapper:

~~~bash
./mvnw test
./mvnw spring-boot:run
~~~

**Chú ý:** mã mẫu và assertions được thiết kế cho Spring Boot 3.5.x / Spring Framework 6.2.x; đây **không phải bằng chứng Maven/JUnit đã được thực thi**. Với Boot 4.x/Spring 7.x hoặc custom `@ControllerAdvice`, điều chỉnh APIs/imports/expectations theo phiên bản thật. Nếu Spring Security có mặt, requests trong tests cần auth/CSRF setup phù hợp.

### 7.1. Không assert UUID cố định

`errorId` thay đổi mỗi lần tạo error. Test chỉ yêu cầu tồn tại và có hình dạng string/UUID nếu muốn nghiêm ngặt; không so toàn bộ response JSON nguyên văn với một UUID mẫu. Timestamp cũng nên được test tương tự nếu schema có thêm.

### 7.2. Không assert thứ tự `violations` nếu nhiều fields lỗi

Khi input có nhiều violations, thứ tự field errors có thể khác theo validation provider và thứ tự duyệt. Nếu contract không hứa thứ tự, test **tập field names** hoặc JSONPath predicates, không so list theo thứ tự một cách cứng nhắc.

### 7.3. Test chính xác `instance`

Bản demo lấy `HttpServletRequest#getRequestURI()`, nên `instance` là **request path** không bao gồm query string. Nếu app đặt reverse proxy, context path hoặc path rewriting, hãy document giá trị external/internal URI và dùng trusted forwarded-header policy; không nhận unvalidated Forwarded headers vào error links.

### 7.4. Kiểm chứng bằng curl

Sau khi chạy ứng dụng:

~~~bash
curl -i -X POST http://localhost:8080/api/items \
  -H "Content-Type: application/json" \
  -d '{"name":"Notebook","quantity":2}'

curl -i -X POST http://localhost:8080/api/items \
  -H "Content-Type: application/json" \
  -d '{"name":"","quantity":0}'

curl -i -X POST http://localhost:8080/api/items \
  -H "Content-Type: application/json" \
  -d '{"name":'

curl -i http://localhost:8080/api/items/missing

curl -i "http://localhost:8080/api/items/search?limit=0"

curl -i http://localhost:8080/api/items/invalid-output
~~~

Dự kiến status lần lượt là **201, 400, 400, 404, 400, 500**. Body thành công là ItemView; bodies lỗi dùng `ProblemDetail` có error codes tương ứng. **Không xem bất kỳ body JSON nào dưới đây là stdout của Java**; đây là HTTP responses, và `errorId` không cố định.

## 8. Phiên bản WebFlux: cùng schema, khác class và callback signature

Nếu ứng dụng thực sự dùng **Spring WebFlux**, có hai khác biệt lớn:

1. `ResponseEntityExceptionHandler` nằm ở package **`org.springframework.web.reactive.result.method.annotation`**, không phải MVC Servlet package.
2. Override `handleExceptionInternal` / `createResponseEntity` dùng **`ServerWebExchange`** và trả **`Mono<ResponseEntity<Object>>`**, thay vì `WebRequest`/`ResponseEntity<Object>`.

Ngoài ra:
- Request body đọc qua `HttpMessageReader`/reactive codecs, không phải `HttpMessageConverter` Servlet.
- Invalid DTO thường thành **`WebExchangeBindException`**, không phải `MethodArgumentNotValidException`.
- Other parse/missing/convert errors có thể là `ServerWebInputException`.
- Method-level validation ở Spring WebFlux 6.1+ có thể thành `HandlerMethodValidationException`.
- Fallback handler ngoài annotated controller có thể là `ErrorWebExceptionHandler` / `WebExceptionHandler`.
- `WebTestClient` là test client phù hợp với WebFlux, khác `MockMvc` của MVC.

**Không copy nguyên MVC advice sang WebFlux rồi đổi mỗi import**, vì method signatures và return types khác.

### 8.1. Tạo project WebFlux riêng

Tạo một Maven project độc lập. Trong `pom.xml`, thay:

~~~xml
<artifactId>api-problems-mvc</artifactId>
~~~

thành:

~~~xml
<artifactId>api-problems-webflux</artifactId>
~~~

và thay **chỉ** dependency:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
~~~

bằng:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webflux</artifactId>
</dependency>
~~~

Giữ `spring-boot-starter-validation` và `spring-boot-starter-test`; các dependency/version Java còn lại như project MVC. Không để lại `spring-boot-starter-web` trong WebFlux project để tránh Spring Boot chọn servlet web stack khi cả hai starters cùng hiện diện.

**Tái sử dụng nguyên văn** các class độc lập stack: `CreateItemRequest.java`, `ItemView.java`, `ApiViolation.java`, `ApiProblemFactory.java`, `ItemNotFoundException.java` và `DuplicateItemException.java` trong package `com.example.problems`. Giữ `ProblemApplication.java` làm Spring Boot entrypoint; **không copy** `ItemController.java`/`MvcApiProblemAdvice.java`/`MvcApiProblemTest.java` sang project WebFlux. Thay bằng các classes sau.

### 8.2. `ReactiveItemController.java`

~~~java
package com.example.problems;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/items")
public class ReactiveItemController {

    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
    public Mono<ResponseEntity<ItemView>> create(
            @Valid @RequestBody CreateItemRequest input) {

        if ("conflict".equalsIgnoreCase(input.name())) {
            return Mono.error(new DuplicateItemException());
        }

        ItemView view = new ItemView(
                "item-42", input.name(), input.quantity());

        return Mono.just(ResponseEntity
                .status(HttpStatus.CREATED).body(view));
    }

    @GetMapping("/{id}")
    public Mono<ItemView> get(@PathVariable String id) {
        if ("missing".equals(id)) {
            return Mono.error(new ItemNotFoundException());
        }

        return Mono.just(new ItemView(id, "Sample", 2));
    }

    @GetMapping("/search")
    public Mono<ItemView> search(
            @RequestParam("limit") @Min(1) int limit) {
        return Mono.just(
                new ItemView("item-1", "Sample", limit));
    }

    @GetMapping("/explode")
    public Mono<ItemView> explode() {
        return Mono.error(new IllegalStateException(
                "Sensitive internal failure details"));
    }
}
~~~

`Mono.error(...)` tạo tín hiệu lỗi trong reactive pipeline. `@Valid @RequestBody CreateItemRequest` minh họa annotated controller nhận body DTO. Nếu endpoint nhận `Mono<CreateItemRequest>` thay vì DTO trực tiếp, cần test đúng reactive body validation path và không trộn syntax `Mono<@Valid Dto>` mà không kiểm tra behavior trên Spring version đã chọn.

### 8.3. `ReactiveApiProblemAdvice.java`

Trong WebFlux project, tạo file cùng package nhưng dùng **Reactive `ResponseEntityExceptionHandler`**:

~~~java
package com.example.problems;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.FieldError;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.bind.support.WebExchangeBindException;
import org.springframework.web.method.annotation.HandlerMethodValidationException;
import org.springframework.web.reactive.result.method.annotation.ResponseEntityExceptionHandler;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;

import java.util.List;

@RestControllerAdvice
@Order(Ordered.HIGHEST_PRECEDENCE)
public class ReactiveApiProblemAdvice
        extends ResponseEntityExceptionHandler {

    private static final Logger LOG =
            LoggerFactory.getLogger(ReactiveApiProblemAdvice.class);

    private static String path(ServerWebExchange exchange) {
        return exchange.getRequest()
                .getPath().pathWithinApplication().value();
    }

    // Spring WebFlux's protected handler is REACTIVE:
    @Override
    protected Mono<ResponseEntity<Object>> handleExceptionInternal(
            Exception ex,
            Object body,
            HttpHeaders headers,
            HttpStatusCode status,
            ServerWebExchange exchange) {

        ProblemDetail problem;

        if (ex instanceof WebExchangeBindException bind) {
            List<ApiViolation> violations =
                    bind.getFieldErrors()
                            .stream()
                            .map(FieldError::getField)
                            .distinct()
                            .map(field -> new ApiViolation(
                                    field, "Invalid value"))
                            .toList();

            problem = ApiProblemFactory.create(
                    status, "VALIDATION_FAILED",
                    "One or more fields are invalid.",
                    violations, path(exchange));
        }
        else if (ex instanceof HandlerMethodValidationException method
                && !method.isForReturnValue()) {

            problem = ApiProblemFactory.create(
                    status, "VALIDATION_FAILED",
                    "One or more parameters are invalid.",
                    List.of(new ApiViolation(
                            "parameter", "Invalid value")),
                    path(exchange));
        }
        else {
            // Bao gồm return-value validation (status 500)
            // và mọi framework exception khác.
            problem = ApiProblemFactory.create(
                    status,
                    ApiProblemFactory.codeFor(status),
                    ApiProblemFactory.detailFor(status),
                    List.of(),
                    path(exchange));
        }

        // Giữ status và headers do framework chọn.
        return super.handleExceptionInternal(
                ex, problem, headers, status, exchange);
    }

    @ExceptionHandler(ItemNotFoundException.class)
    public ResponseEntity<ProblemDetail> notFound(
            ItemNotFoundException ex,
            ServerWebExchange exchange) {

        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .body(ApiProblemFactory.create(
                        HttpStatus.NOT_FOUND,
                        "RESOURCE_NOT_FOUND",
                        "The requested item was not found.",
                        List.of(),
                        path(exchange)));
    }

    @ExceptionHandler(DuplicateItemException.class)
    public ResponseEntity<ProblemDetail> conflict(
            DuplicateItemException ex,
            ServerWebExchange exchange) {

        return ResponseEntity.status(HttpStatus.CONFLICT)
                .body(ApiProblemFactory.create(
                        HttpStatus.CONFLICT,
                        "CONFLICT",
                        "An item with this name already exists.",
                        List.of(),
                        path(exchange)));
    }

    @ExceptionHandler(Exception.class)
    public ResponseEntity<ProblemDetail> unexpected(
            Exception ex,
            ServerWebExchange exchange) {

        ProblemDetail problem = ApiProblemFactory.create(
                HttpStatus.INTERNAL_SERVER_ERROR,
                "INTERNAL_ERROR",
                "An internal error occurred.",
                List.of(),
                path(exchange));

        Object errorId = problem.getProperties().get("errorId");
        LOG.error("Unexpected reactive API error, errorId={}",
                errorId, ex);

        return ResponseEntity
                .status(HttpStatus.INTERNAL_SERVER_ERROR)
                .body(problem);
    }
}
~~~

**Điểm đáng chú ý:**

- Phương thức WebFlux `handleExceptionInternal` trả **`Mono<ResponseEntity<Object>>`**. Với MVC, method tương ứng trả `ResponseEntity<Object>` và nhận `WebRequest`.
- `WebExchangeBindException#getFieldErrors()` cung cấp field errors, nhưng ví dụ chỉ trả field name + message an toàn, không trả rejected value.
- `HandlerMethodValidationException` cho input được 400/`VALIDATION_FAILED`; **return-value** rẽ sang status 500/`INTERNAL_ERROR` và không lộ kết quả nội bộ.
- Các framework exceptions khác vẫn đi qua `ResponseEntityExceptionHandler`, status/headers do framework chọn; factory bổ sung contract.
- `@ExceptionHandler` cho domain/fallback returns `ResponseEntity<ProblemDetail>` là được trong annotated WebFlux controllers; không nhất thiết mọi exception handler phải trả Mono khi response sẵn có.
- Dùng cùng `ApiProblemFactory` nhưng **khác pipeline và handler method signatures**.
- Code không chặn Reactor event loop bằng JDBC/HTTP blocking; nếu thêm logging/enrichment trong production, phải tránh các thao tác blocking trong reactive chain.
- Nếu lỗi xảy ra ngoài annotated controller hoặc response đã commit/đang streaming, `@RestControllerAdvice` vẫn không bao phủ mọi tình huống; cần tầng reactive fallback riêng.

### 8.4. Kiểm thử WebFlux bằng `WebTestClient`

Vẫn ở WebFlux project, tạo `src/test/java/com/example/problems/ReactiveApiProblemTest.java`:

~~~java
package com.example.problems;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class ReactiveApiProblemTest {

    @Autowired
    WebTestClient client;

    @Test
    void validReactiveCreateReturns201() {
        client.post()
                .uri("/api/items")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue("""
                        {"name":"Book","quantity":1}
                        """)
                .exchange()
                .expectStatus().isCreated()
                .expectBody()
                .jsonPath("$.name").isEqualTo("Book");
    }

    @Test
    void invalidDtoHasUnifiedValidationCode() {
        client.post()
                .uri("/api/items")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue("""
                        {"name":"","quantity":0}
                        """)
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.code")
                    .isEqualTo("VALIDATION_FAILED")
                .jsonPath("$.status").isEqualTo(400)
                .jsonPath("$.errorId").isNotEmpty()
                .jsonPath("$.violations").isArray();
    }

    @Test
    void missingItemIs404() {
        client.get()
                .uri("/api/items/missing")
                .exchange()
                .expectStatus().isNotFound()
                .expectBody()
                .jsonPath("$.code")
                    .isEqualTo("RESOURCE_NOT_FOUND");
    }

    @Test
    void duplicateItemIs409() {
        client.post()
                .uri("/api/items")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue("""
                        {"name":"conflict","quantity":1}
                        """)
                .exchange()
                .expectStatus().isEqualTo(409)
                .expectBody()
                .jsonPath("$.code").isEqualTo("CONFLICT");
    }

    @Test
    void invalidMethodParameterIs400() {
        client.get()
                .uri("/api/items/search?limit=0")
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.code")
                    .isEqualTo("VALIDATION_FAILED");
    }

    @Test
    void unexpectedFailureIsSanitized500() {
        client.get()
                .uri("/api/items/explode")
                .exchange()
                .expectStatus().is5xxServerError()
                .expectBody()
                .jsonPath("$.code")
                    .isEqualTo("INTERNAL_ERROR")
                .jsonPath("$.errorId").isNotEmpty();
    }
}
~~~

Có **6 WebTestClient tests**. Chạy `mvn test` trong WebFlux project riêng; chúng kiểm tra cùng **contract public**, nhưng không tái sử dụng `MockMvc` hoặc Servlet-only exception classes. Với WebFlux/Boot version khác, kiểm chứng exact handler invocation và problem JSON trên server đang dùng trước khi ứng dụng hóa.

**Lưu ý kỹ thuật:** JSON body khi gọi `bodyValue(String)` với `Content-Type: application/json` thường được gửi dưới dạng chuỗi; trong một số test configurations codec có thể encode chuỗi theo converter khác. Nếu test environment gặp khác biệt, có thể truyền JSON bytes:
 
~~~java
.bodyValue(
        "{\"name\":\"Book\",\"quantity\":1}"
                .getBytes(StandardCharsets.UTF_8))
~~~

Đây là snippet cần import `java.nio.charset.StandardCharsets`, không thay đổi contract API. Phân biệt lỗi do test client chọn encoder với lỗi của Spring controller.

## 9. Không làm mất ý nghĩa của HTTP statuses và headers

### 9.1. Status ở header và JSON phải trùng

Nếu response line là 400 mà JSON `status=500`, client/proxy/metrics mâu thuẫn. Tất cả code mẫu tạo `ProblemDetail.forStatus(status)` và trả `ResponseEntity` với **cùng status**.

Khi dùng `@ResponseStatus`, `ResponseStatusException` hoặc `ErrorResponseException`, chú ý Spring có thể đã chọn status và headers. Nếu viết handler riêng, không ghi đè bằng 500 chung chỉ vì “đang xử lý exception”.

### 9.2. 401 và 403 từ Spring Security

Spring Security thường xử lý tại **filter chain** (Servlet `AuthenticationEntryPoint`/`AccessDeniedHandler`; Reactive `ServerAuthenticationEntryPoint`/`ServerAccessDeniedHandler`), có thể **không** đi qua MVC/WebFlux `@RestControllerAdvice`.

Để đồng nhất 401/403, dùng cùng `ApiProblemFactory` hoặc shared serializer logic tại các security handlers, nhưng:
- 401 nên có `WWW-Authenticate` theo authentication scheme nếu yêu cầu.
- 403 giữ đúng semantics không có quyền.
- Không tiết lộ resource tồn tại hay không nếu policy cần trả 404 để hạn chế enumeration.
- Không làm lộ authentication token, password hoặc security context vào JSON.
- Không xóa `WWW-Authenticate` / `Retry-After` chỉ để ép cùng schema.

Lấy `HttpServletRequest#getRequestURI()` / `ServerWebExchange#getRequest().getURI().getPath()` theo cùng sanitization policy. Không tin unvalidated `Forwarded`/`X-Forwarded-*` headers do client gửi.

### 9.3. 405, 406, 415

Khi request method không cho phép, response 405 cần giữ `Allow` header. Với `Accept` không phù hợp, 406 có thể khó tạo ProblemDetail JSON theo chính header Accept đã không cho JSON; **không cam kết body problem JSON trong mọi content negotiation failure**. Với 415, giữ contract `Content-Type` và hỗ trợ format thực tế. Tests nên assert **status trước**, sau đó body/schema khi framework có thể render.

### 9.4. 429 và 503, Retry-After

Nếu API có rate limiting hoặc circuit breaker:
- 429: `RATE_LIMITED`, có thể kèm `Retry-After`.
- 503: `SERVICE_UNAVAILABLE`, cũng có thể kèm `Retry-After`.
- 504: gateway timeout ở proxy/gateway layer, không nhất thiết vào controller advice.

Không dùng `Retry-After` tùy tiện hoặc hứa retry an toàn cho **non-idempotent** operation. Hãy document retry semantics và idempotency keys cho API cập nhật dữ liệu.

## 10. Tránh rò rỉ dữ liệu và thông tin nội bộ

### Không trả thẳng exception message

Sai:

~~~java
@ExceptionHandler(Exception.class)
ResponseEntity<?> handle(Exception ex) {
    return ResponseEntity.status(500)
            .body(java.util.Map.of(
                    "error", ex.getMessage()));
}
~~~

Đây là snippet **anti-pattern**, không dùng production. Exception message có thể chứa URL nội bộ, stack fragment, SQL, connection string, user email, rejected values, token hoặc tên column/entity.

Đúng: thông điệp 5xx chung:

~~~json
{
  "status": 500,
  "code": "INTERNAL_ERROR",
  "detail": "An internal error occurred.",
  "errorId": "59ce42b5-32c9-471e-9c4e-1f4577c6d458",
  "violations": []
}
~~~

Đây là JSON rút gọn chỉ minh họa custom fields; full `ProblemDetail` còn có `type/title/instance`.

### Không trả rejected values

`FieldError#getRejectedValue()` hoặc `ConstraintViolation#getInvalidValue()` có thể là secrets. Đừng serialize nguyên `BindingResult` hoặc `ConstraintViolationException`. Với `@Email`, không cần lặp email trong error message; client đã biết giá trị mình nhập.

### Mã field phải là public schema

Nếu request DTO có nested paths, ví dụ `address.postalCode`, có thể trả tên field này nếu đã công bố trong API contract. Không trả internal JPA property names hoặc SQL column names. Đối với mass-assignment extra input, cân nhắc mã chung `BAD_REQUEST` thay vì liệt kê toàn bộ server-only field names.

### Lỗi server return-value validation

Nếu controller hoặc service trả output sai constraint, đây **không phải yêu cầu người dùng sửa form**. Đặc biệt Spring MVC `HandlerMethodValidationException#isForReturnValue()` giúp chọn 500. Trả `violations: []` thay vì phản chiếu giá trị trả về sai.

### Logging/trace

- Log đầy đủ exception **chỉ vào server logs** có access controls và retention phù hợp.
- Gắn `errorId`/trace ID vào logs và metrics, nhưng đừng dùng `errorId` để chứa secret hoặc user ID.
- Không log request JSON raw để “debug lỗi 400” mặc định.
- Với validation 400 xuất hiện nhiều, dùng counters/metrics aggregate thay vì stack trace mỗi request để tránh log flood.
- Trước khi log 5xx, cân nhắc redaction cho exception message trong đường telemetry nếu underlying library có thể chứa PII.

## 11. WebFlux và reactive-specific pitfalls

**`@RestControllerAdvice` chỉ dành cho annotated controllers**. Với WebFlux functional endpoints (`RouterFunction`/`HandlerFunction`), không có cùng exception resolver path cho mọi trường hợp. Nếu ứng dụng dùng functional routes nhiều, cân nhắc `WebExceptionHandler`/Boot `ErrorWebExceptionHandler` hoặc filter/operator policy đồng nhất.

**`onErrorResume` ở service không thay global handler hoàn toàn.** Nếu service tự chuyển mọi `Throwable` thành `Mono.empty()`, lỗi có thể biến mất hoặc API trả 200/404 sai ngữ nghĩa. Chỉ recover những exception có nghĩa nghiệp vụ xác định; để các lỗi khác đi tới error layer.

**Không blocking trong reactive advice.** Tránh gọi JDBC blocking, hệ thống log đồng bộ quá nặng hoặc remote HTTP request blocking trên event loop. Trace/error enrichment cần nhanh và nonblocking.

**Response đã commit:** Với SSE/Flux streaming, nếu gửi dữ liệu trước rồi mới xảy ra lỗi, không thể chuyển response đã commit thành `ProblemDetail` mới với status 500. Thiết kế một **in-stream error event contract** hoặc kết thúc stream phù hợp, và kiểm thử streaming behavior riêng.

**Backpressure/payload limits:** Một error body thống nhất không bảo vệ app khỏi request body quá lớn. Đặt codec memory limits, gateway limits, upload limits và collection validation phù hợp.

**Method validation vs argument validation:** Trong WebFlux có `WebExchangeBindException` và `HandlerMethodValidationException`, tùy signature. Class-level `@Validated` trên controller có thể chuyển sang AOP-based validation; Spring 6.1+ docs khuyến cáo gỡ nếu muốn built-in method validation. Không gộp cả hai vào một nhánh 400 một cách mù quáng.

## 12. Lộ trình mở rộng thành error contract production

Một hệ thống sản xuất cần thêm những phần sau bên cạnh ví dụ:

1. **Registry mã lỗi** có namespace/versioning: `VALIDATION_FAILED`, `RESOURCE_NOT_FOUND`, `CONFLICT`,... và tài liệu công khai.
2. **MessageSource/i18n** cho `title`, `detail`, `violations.message`; giữ `code` không đổi qua locale.
3. **Structured logging** tích hợp trace ID, errorId, log sampling và privacy redaction.
4. **Security handlers** cho 401/403 ở Servlet filter chain hoặc reactive filter chain.
5. **Boot fallback** cho errors không đi qua advice (Servlet `/error` / `ErrorAttributes` hoặc reactive `ErrorWebExceptionHandler`), cùng schema nếu có thể.
6. **CORS headers** và client-visible errors: đừng để error handler bỏ các CORS headers cần thiết nếu yêu cầu xuất phát từ browser.
7. **Rate limiting / gateway** error policy đồng nhất 429/503/504 và `Retry-After`.
8. **Contract tests** độc lập framework: assert status, content-type, mã code, errorId, array violations, instance và absence of secrets.
9. **OpenAPI error schemas**: document `application/problem+json` và các status cho từng operation; versioning của code fields.
10. **Observability**: latency, error rates, status distribution, exception category, correlation; alert trên 5xx, không báo động 400 hợp lệ.
11. **Client compatibility**: client xử lý unknown `code` bằng fallback theo HTTP status, không crash khi server thêm extension field.
12. **Authentication/authorization**: không đưa stack/security internals vào ProblemDetail, không che 401/403 thành 500.
13. **Testing các proxy/timeouts**: đảm bảo status và body không bị rewrite ngoài ý muốn.
14. **Data minimization**: response 500 và validation output không lộ secrets/PII, kể cả trong localized messages.
15. **Transactions**: một 500 do return-value violation không tự đảm bảo rollback; test side effects và idempotency.

### Hai cách tổ chức code khi có cả MVC và WebFlux trong các microservice

- **Module contract/framework-neutral**: record `ApiViolation`, `ApiProblemFactory`, error codes và conventions, dùng Spring `ProblemDetail` từ `spring-web` hoặc DTO độc lập nếu cần.
- **MVC adapter**: `ResponseEntityExceptionHandler` Servlet, `WebRequest`, `MockMvc`, security servlet entry points.
- **WebFlux adapter**: `ResponseEntityExceptionHandler` Reactive, `ServerWebExchange`, `Mono<ResponseEntity<?>>`, `WebTestClient`, reactive security entry points.
- **Shared contract tests**: mỗi adapter phải produce cùng JSON shape và code mapping.
- **Không share một exception-handler class** giữa Servlet và Reactive, vì các signatures khác nhau.

## 13. Lỗi thường gặp, triệu chứng và hướng khắc phục

| Anti-pattern | Triệu chứng | Sửa đúng |
| --- | --- | --- |
| Mỗi controller tự return `Map.of("error", ...)` | Body không nhất quán | Dùng `ProblemDetail` và global advice. |
| Catch `Exception.class` trả 400 | Lỗi DB/return value thành lỗi client | Phân loại business/validation riêng, fallback 500. |
| Catch toàn bộ lỗi trả 500 | Input JSON sai trả 500 | Dùng framework exception handler và map 400/415/405,... |
| Dùng `ex.getMessage()` cho public `detail` | Lộ SQL/token/internal URLs | Trả detail an toàn, log exception nội bộ. |
| Trả `FieldError#getRejectedValue()` | Lộ PII/password | Chỉ trả field + public message/code. |
| Mã lỗi dựa vào localized detail | Client hỏng khi dịch ngôn ngữ | `code` ổn định, i18n cho messages. |
| `ProblemDetail.status` khác HTTP response status | Proxy/client không nhất quán | Tạo từ cùng `HttpStatusCode` và test cả hai. |
| Override Spring handler bằng một `@ExceptionHandler` trùng exception | Ambiguous mapping hoặc cấu hình sai | Override protected handler của `ResponseEntityExceptionHandler`. |
| Sửa handler MVC sang WebFlux bằng đổi imports tối thiểu | Lỗi compile/signature, reactive behavior sai | Adapter riêng với `ServerWebExchange` và Mono. |
| Dùng `MockMvc` để test WebFlux controller | Sai web stack | Dùng `WebTestClient`. |
| Cho cả hai starters web và webflux vào demo | Spring Boot có thể chọn MVC stack | Chọn một stack rõ hoặc cấu hình có chủ đích. |
| Thêm `@Validated` trên controller mà không xét method validation | Exception pipeline đổi | Với Spring 6.1+ dùng built-in như dự kiến. |
| Map mọi `ConstraintViolationException` sang 400 | Server return-value error thành 400 | Phân biệt boundary, input/return status. |
| Ghi đè mọi HttpHeaders bằng empty headers | Mất `Allow`, `WWW-Authenticate`, `Retry-After` | Giữ headers gốc và bổ sung có chủ đích. |
| Nhầm 404 domain với 404 static/gateway | Không có schema thống nhất ở mọi đường | Test fallback `/error`/gateway riêng. |
| Nghĩ advice bắt mọi Servlet filter/Security error | 401/403 trả JSON khác | Tích hợp security exception handlers. |
| Error body thay đổi khi response đã commit | Không thể đổi status/body streaming | Thiết kế streaming error protocol. |
| Dùng UUID ngẫu nhiên mà không log | Không truy được sự cố | Log cùng errorId hoặc gắn trace IDs thật. |
| Log toàn bộ request khi lỗi validation | Lộ dữ liệu riêng tư | Redaction, structured events, sampling. |
| Body lỗi quá nhiều violations | Response lớn, DoS/log flood | Giới hạn và document error list length. |
| Không contract-test 406/415/405 | Content negotiation/headers hỏng | Test status/header, body khi có thể serialize. |

## 14. Checklist nghiệm thu

- [ ] API lỗi dùng `ProblemDetail` chuẩn RFC 9457, media type `application/problem+json` khi có thể thương lượng.
- [ ] HTTP status trùng `ProblemDetail.status`.
- [ ] `type/title/status/detail/instance` có nghĩa và không chứa secrets.
- [ ] Extension `code` tồn tại và ổn định, không phụ thuộc locale.
- [ ] Extension `errorId` có giá trị duy nhất/mang tính correlation, log cùng ID với 5xx.
- [ ] `violations` là array, không lộ rejected values; fields chỉ từ public input contract.
- [ ] Individual DTO validation map 400/`VALIDATION_FAILED`.
- [ ] Direct method input validation map 400, return-value violation map 500.
- [ ] Malformed JSON/body map 400 với message an toàn.
- [ ] Type mismatch, missing query/header/body map 400 theo contract.
- [ ] Domain not found 404, conflict 409; không dùng exception chung tùy tiện.
- [ ] Unsupported method 405 và `Allow` header được giữ.
- [ ] Unsupported media type 415; Accept mismatch 406 được test đúng khả năng content negotiation.
- [ ] Unexpected backend exceptions map 500 nhưng không đưa stack/message ra JSON.
- [ ] Chỉ chọn **một** runtime web stack cho từng app: MVC hoặc WebFlux.
- [ ] MVC advice kế thừa Servlet `ResponseEntityExceptionHandler`; WebFlux dùng Reactive class tương ứng.
- [ ] Unit/MockMvc hoặc WebTestClient tests kiểm tra các error branches thực tế.
- [ ] 401/403 từ Spring Security được thiết kế ở đúng filter layer.
- [ ] Fallback `/error`/`ErrorWebExceptionHandler`/gateway có hợp đồng nhất quán theo khả năng.
- [ ] Log và metrics dùng trace/error IDs có privacy controls, không log raw payload.
- [ ] Có i18n plan cho `detail` và messages nếu sản phẩm cần đa ngôn ngữ.
- [ ] Không bảo đảm ProblemDetail cho response đã commit/stream đang gửi.
- [ ] Dependency Spring Boot/Framework được cập nhật theo nhánh còn hỗ trợ và security advisory.
- [ ] API docs/OpenAPI mô tả lỗi, media type, codes, fields và retry behavior.
- [ ] Khi đổi validation annotations hoặc error handler, chạy lại negative contract tests.

**Kết luận:** Một error contract tốt không chỉ là “mọi lỗi có trường `message`”. Hãy dùng **`ProblemDetail` theo RFC 9457**, có **`code`**, **`errorId`** và **`violations`** nhất quán, giữ đúng HTTP status và headers, rồi tách các adapter tương ứng cho **Spring MVC** và **Spring WebFlux**. Unit/HTTP tests phải chứng minh validation input 400, return-value violation 500, domain 404/409, parsing 400, media type 415 và unexpected 500. Với hệ thống thật, tiếp tục tích hợp Spring Security, fallback handler, tracing và gateway để đạt mức “thống nhất” xuyên toàn bộ request lifecycle.

## Tài liệu tham khảo

- Spring Framework 6.2 Reference — **MVC Error Responses, RFC 9457, `ProblemDetail`/`ResponseEntityExceptionHandler`**: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-ann-rest-exceptions.html
- Spring Framework 6.2 Reference — **WebFlux Error Responses**: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/ann-rest-exceptions.html
- Spring Framework 6.2 Reference — **MVC Handler Method Validation**: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html
- Spring Framework 6.2 Reference — **WebFlux Handler Method Validation**: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-validation.html
- Spring Framework 6.2 Javadoc — **MVC ResponseEntityExceptionHandler**: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/servlet/mvc/method/annotation/ResponseEntityExceptionHandler.html
- Spring Framework 6.2 Javadoc — **WebFlux ResponseEntityExceptionHandler**: https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/web/reactive/result/method/annotation/ResponseEntityExceptionHandler.html
- Spring Framework 6.2 Javadoc — **HandlerMethodValidationException**: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/method/annotation/HandlerMethodValidationException.html
- RFC 9457 — **Problem Details for HTTP APIs**: https://www.rfc-editor.org/rfc/rfc9457.html
- Spring Boot Reference — **Error Handling, Problem Details**: https://docs.spring.io/spring-boot/reference/web/servlet.html
