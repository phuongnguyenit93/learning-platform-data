# Spring MVC — Ẩn thông tin nhạy cảm, gắn mã đối chiếu và tránh trả stack trace cho người dùng

## 1. Mục tiêu

Khi request thất bại, API phải giúp client hiểu **điều gì cần làm tiếp**, còn người vận hành phải tìm được **nguyên nhân kỹ thuật**. Hai đối tượng này cần mức thông tin khác nhau.

Ví dụ phản hồi nguy hiểm:

~~~json
{
  "error": "SQLException: password for jdbc://db.internal:5432/app is secret123",
  "stackTrace": "at com.example.payment.internal.DatabaseAdapter.save(DatabaseAdapter.java:84)",
  "authorization": "Bearer eyJ..."
}
~~~

Phản hồi an toàn hơn:

~~~json
{
  "code": "INTERNAL_ERROR",
  "message": "Không thể xử lý yêu cầu. Vui lòng thử lại sau.",
  "requestId": "6efdbf4c-55a5-4d3c-a04a-4f0f9abce235",
  "violations": []
}
~~~

HTTP status thực vẫn là 500. Mã đối chiếu giúp đội vận hành tìm sự kiện tương ứng trong log/tracing có kiểm soát; client không cần thấy exception class, source path, SQL hoặc stack trace.

Sau bài này, bạn có thể:

- Phân biệt **thông tin công khai trong HTTP response** với **dữ liệu chẩn đoán nội bộ**.
- Liệt kê những nguồn rò rỉ thường gặp: exception message, stack trace, error page, URL/query, validation rejected value, logs, headers, framework defaults và proxy.
- Thiết kế mã lỗi ổn định (`code`) và mã đối chiếu từng request (`requestId` hoặc `traceId`); hiểu hai mã phục vụ hai mục đích khác nhau.
- Tạo request ID do server kiểm soát, trả ở header `X-Request-ID` và error JSON, đưa vào MDC để đối chiếu log; dọn MDC bằng `finally` hoặc `MDC.putCloseable`.
- Dùng `@RestControllerAdvice` và `ResponseEntityExceptionHandler` để trả thông điệp an toàn cho các lỗi đã phân loại, giữ nguyên HTTP status cần thiết.
- Cấu hình Spring Boot tránh xuất stack trace, exception message và binding errors trong đường xử lý lỗi mặc định.
- Kiểm thử rằng response không chứa thông tin giả lập nhạy cảm và request ID trong body khớp header.

**Bối cảnh:** Spring MVC Servlet stack, Java 17+, Spring Boot 3.5.0 / Spring Framework 6.2. Một số ví dụ là mã độc lập trong dự án Maven đầy đủ ở mục 9; các đoạn ngắn khác được đánh dấu "minh họa".

## 2. Điều gì có thể bị lộ khi API trả lỗi?

| Dữ liệu | Rủi ro nếu lộ trong response | Cách xử lý |
| --- | --- | --- |
| Stack trace, source file, line number | Tiết lộ cấu trúc ứng dụng, thư viện, luồng xử lý | Ghi vào kênh chẩn đoán nội bộ phù hợp; không nhúng vào body |
| `exception.getMessage()` | Có thể chứa SQL, host, token, thông tin người dùng hoặc tham số nội bộ | Dùng public message cố định/đã kiểm duyệt |
| SQL và connection string | Lộ schema, host, account, database topology | Không gửi cho client; lọc secret cả ở log |
| Password, API key, bearer token, cookie | Đánh cắp quyền truy cập | Không echo/log raw value; redact hoặc loại bỏ |
| HTTP query/body | Có thể chứa email, mã xác nhận, token, dữ liệu cá nhân | Không log toàn bộ mặc định; whitelist metadata thật sự cần |
| Validation rejected value | Có thể mang PII/secret hoặc payload độc hại, rất dài | Trả tên field và mã lỗi an toàn; không trả giá trị thô |
| Internal exception class/package | Lộ chi tiết triển khai mà client không cần | Dùng `code` ổn định ở cấp API |
| Trace/span metadata nội bộ | Có thể tiết lộ kiến trúc hay định danh nội bộ | Chỉ trả ID đối chiếu đã được đánh giá an toàn |
| Response headers | Version server, thông tin debug hoặc token | Kiểm tra cả headers, không chỉ JSON body |
| HTML error page | Có thể hiển thị stack trace hoặc detail | Cấu hình error handling cho cả browser/HTML route |

**Nguyên tắc:** response là **giao diện công khai**; mọi chuỗi từ exception, request, database và dependency đều phải được coi là không đáng tin trước khi đưa ra ngoài. Một lỗi 4xx cũng có thể rò rỉ thông tin, không riêng 5xx.

## 3. Phân biệt error code, request ID và trace ID

Ba loại định danh thường bị nhầm:

| Tên | Nghĩa | Độ ổn định | Ai sử dụng |
| --- | --- | --- | --- |
| HTTP status | Nhóm/ý nghĩa kết quả HTTP | Theo HTTP semantics | HTTP client, proxy, monitor |
| `code` / error code | Loại lỗi nghiệp vụ/kỹ thuật trong contract, ví dụ `INVALID_INPUT`, `ACCOUNT_CONFLICT` | Ổn định qua nhiều request | Client hiển thị/xử lý lỗi |
| `requestId` / correlation ID | Định danh một lần xử lý request | Khác nhau giữa các request | Support, log search |
| Distributed `traceId` | Định danh trace gồm nhiều span qua các dịch vụ | Chung trong cùng distributed trace | Tracing/observability |

Ví dụ hai request đều có code `INTERNAL_ERROR` nhưng có hai `requestId` khác nhau. Người dùng cung cấp request ID để support tìm đúng lần thất bại; client dùng error code để biết cách xử lý tự động. Không sử dụng exception class làm error code công khai.

Một contract đơn giản:

~~~json
{
  "code": "INVALID_INPUT",
  "message": "Dữ liệu yêu cầu không hợp lệ.",
  "requestId": "9e9912e6-f2c3-44c7-a6e2-118b6fbfcf4c",
  "violations": [
    {"field": "email", "code": "EMAIL_INVALID"}
  ]
}
~~~

Trong ví dụ này, `message` là thông điệp đã chọn cho client; `violations` chỉ cho biết trường và loại lỗi, **không echo địa chỉ email sai**. HTTP status đi trong response HTTP (400), không cần lặp trong body nếu API contract không yêu cầu.

### 3.1. Request ID do ai sinh ra?

Có hai chiến lược phổ biến:

1. **Server-generated:** server tạo UUID ngẫu nhiên và dùng nhất quán trong request. Đơn giản và phù hợp demo.
2. **Trusted gateway-generated:** gateway tạo ID, bảo đảm format/độ dài/nguồn tin cậy, truyền vào backend; backend có thể giữ và đưa vào MDC.

Không lấy tùy ý `X-Request-ID` từ một client không tin cậy rồi đưa thẳng vào log/header. Dữ liệu do client điều khiển có thể quá dài, chứa ký tự điều khiển, newline hoặc gây trùng/spoof ID. Nếu cần nhận ID từ upstream, phải giới hạn nguồn, độ dài, bảng ký tự và chính sách thay thế khi không hợp lệ.

**Request ID khác authorization token.** Nó nên là mã đối chiếu ngẫu nhiên không mang PII, secret, user ID, internal host hoặc thời gian đoán được. Tuy nhiên ID vẫn có thể làm lộ việc hai log cùng một request; quyết định phạm vi hiển thị hợp lý và không cho phép chỉ dựa vào ID để truy cập log của người khác.

### 3.2. Correlation ID xuyên dịch vụ

Nếu A gọi B và B gọi C, có thể truyền context tracing chuẩn W3C như `traceparent` theo hệ thống tracing đang dùng. `traceId` của distributed trace không nhất thiết là UUID hoặc bằng custom `requestId`; đừng khởi tạo hệ ID cạnh tranh nếu hệ thống đã có Micrometer Tracing/OpenTelemetry.

Một mô hình:

~~~text
Browser ── request ──> Gateway ──> Service A ──> Service B
                            │           │              │
                        traceId       traceId        traceId
                        requestId     spanId         spanId
                            │
                public X-Request-ID response
~~~

Một trace có nhiều span; riêng request ID có thể được dùng theo từng request hoặc edge request theo chính sách. Nếu kết nối logs với traces, cấu hình log pattern/structured logging đọc MDC/tracing context ở từng service thay vì giả định tự động lan truyền.

## 4. HTTP lỗi nên tiết lộ thông tin ở mức nào?

| Tình huống | HTTP | Public `code` ví dụ | Public message hợp lý | Không nên trả |
| --- | --- | --- | --- | --- |
| JSON sai cú pháp | 400 | `INVALID_JSON` | Không đọc được dữ liệu JSON | Nội dung parser stacktrace, toàn bộ body |
| DTO sai validation | 400 | `INVALID_INPUT` | Dữ liệu yêu cầu không hợp lệ | Raw rejected password/token |
| Không tìm thấy resource | 404 | `RESOURCE_NOT_FOUND` | Không tìm thấy tài nguyên | DB table/key nội bộ |
| Xung đột trạng thái domain | 409 | `STATE_CONFLICT` | Thao tác không hợp lệ ở trạng thái hiện tại | Tên service/method nội bộ |
| Resource thiếu quyền | 403 hoặc policy-specific 404 | `ACCESS_DENIED` | Không có quyền thực hiện | Thông tin tài khoản/role bí mật |
| Rate limit | 429 | `RATE_LIMITED` | Đã vượt giới hạn, vui lòng thử lại sau | Cấu hình nội bộ không cần công bố |
| DB hoặc dependency tạm hỏng | 503 nếu phù hợp | `SERVICE_UNAVAILABLE` | Dịch vụ tạm thời không khả dụng | DB host, credentials, raw driver error |
| Exception bất ngờ | 500 | `INTERNAL_ERROR` | Đã xảy ra lỗi máy chủ | Stack trace, source path, runtime details |

Lỗi đăng nhập và đăng ký cũng có thể cần **câu trả lời có độ chi tiết giới hạn** để tránh user/account enumeration. Ví dụ yêu cầu khôi phục mật khẩu nên dùng thông điệp chung khi chính sách bảo mật cần che giấu việc email có tồn tại. Cách đó thuộc thiết kế security flow; không thể giải quyết bằng việc ẩn stacktrace.

Đừng bao giờ đổi lỗi hệ thống thành HTTP 200 chỉ để client có một JSON "đẹp":

~~~java
// Phản ví dụ: HTTP status không phản ánh kết quả.
try {
    return service.update();
} catch (Exception ex) {
    return ResponseEntity.ok(Map.of(
            "success", false,
            "error", ex.getMessage()));
}
~~~

Đoạn này chỉ minh họa anti-pattern; vừa sai status, vừa có nguy cơ lộ message. Hãy tách exception semantics và mapping HTTP phù hợp.

## 5. Spring Boot: cấu hình lỗi mặc định an toàn

Với Spring Boot 3.5, trong `src/main/resources/application.properties`:

~~~properties
server.error.include-stacktrace=never
server.error.include-message=never
server.error.include-binding-errors=never
server.error.include-exception=false
server.error.include-path=never
server.error.whitelabel.enabled=false
~~~

Ý nghĩa:

- `include-stacktrace=never`: không cho đường xử lý lỗi mặc định thêm thuộc tính trace vào response, kể cả khi request cố kích hoạt qua query parameter.
- `include-message=never`: không đưa exception message ra body mặc định.
- `include-binding-errors=never`: không thêm binding errors nguyên dạng.
- `include-exception=false`: không thêm exception class name.
- `include-path=never`: không tự thêm request path (có thể có token/PII ở path).
- `whitelabel.enabled=false`: tắt trang lỗi HTML mặc định dạng Whitelabel của Boot; **không có nghĩa sẽ không có bất kỳ HTML error page nào** vì có thể do servlet container/proxy/frontend cung cấp.

Đây là cấu hình **đường lỗi Boot mặc định**, không tự động lọc response bạn tự dựng bằng `@ExceptionHandler` hoặc `ResponseEntity`. Nếu code gọi `ex.getMessage()` đưa vào JSON, các cấu hình trên không cứu được. Cần kiểm tra proxy, framework error handlers, Security filter chain và exception ở tầng response serialization.

**Không dùng** trong production:

~~~properties
# Phản ví dụ: tăng rủi ro lộ thông tin.
server.error.include-stacktrace=always
server.error.include-message=always
server.error.include-binding-errors=always
~~~

Tùy phiên bản, các thuộc tính include dạng `on_param` cho phép client kích hoạt chi tiết qua request parameter. Tránh chọn kiểu này cho môi trường public. Không coi việc tắt `spring.mvc.problemdetails.enabled` là cơ chế bảo mật; ProblemDetail vẫn có thể được tự dựng với detail nguy hiểm.

## 6. Xử lý exception mà không phơi thông tin

Trong Spring MVC:

- `@RestControllerAdvice` gom logic chuyển **exception → HTTP response** cho controllers thuộc scope.
- `@ExceptionHandler` xử lý domain/system exception mà ứng dụng chủ động định nghĩa.
- `ResponseEntityExceptionHandler` cung cấp các handler cho nhiều lỗi Spring MVC có sẵn (body unreadable, validation, 405/415…).
- `ProblemDetail` chuẩn RFC 9457 là một lựa chọn error contract khác; không bắt buộc dùng song song với custom DTO.
- `@ResponseStatus` có thể map exception/status, nhưng nếu cần kiểm soát JSON an toàn, advice thường rõ ràng hơn.

Ví dụ minh họa handler domain:

~~~java
@ExceptionHandler(DuplicateUsernameException.class)
ResponseEntity<SafeError> duplicate(
        DuplicateUsernameException ex,
        HttpServletRequest request) {
    return ResponseEntity.status(HttpStatus.CONFLICT)
            .body(new SafeError(
                    "USERNAME_UNAVAILABLE",
                    "Không thể đăng ký tên người dùng này.",
                    requestId(request),
                    List.of()));
}
~~~

Ở đây **không** nối `ex.getMessage()` vào body. Đoạn code này là method trong advice, chưa là file độc lập; dự án hoàn chỉnh ở mục 9.

### 6.1. Có nên dùng catch-all Exception.class?

Nếu `@ExceptionHandler(Exception.class)` trả 500 cho mọi exception, nó có thể vô tình **che mất HTTP status hợp lệ** của framework (405, 406, 415 hoặc các exception đã là `ErrorResponse`). Nếu dùng `ResponseEntityExceptionHandler`, tránh khai báo exception handler trùng với mapping sẵn có vì có thể gây ambiguous mapping.

Có thể chọn một trong các cách sau:

- Kế thừa `ResponseEntityExceptionHandler` và override các hook chính xác, giữ HTTP status gốc nhưng thay body thành DTO an toàn.
- Định nghĩa handler rõ cho các domain/system exceptions đã xác định; để Boot/framework xử lý lỗi không dự đoán được với cấu hình giấu chi tiết.
- Nếu cần một catch-all public 500 thống nhất, thiết kế fallback không đè lên các exception HTTP có status sẵn có và kiểm thử đủ 400/404/405/406/415/422/500.

**Lưu ý:** exceptions sinh ra trong servlet filters (đặc biệt Spring Security filter chain) hoặc khi response đã commit không nhất thiết đi qua controller advice. Security 401/403 thường do `AuthenticationEntryPoint` và `AccessDeniedHandler` xử lý; cần cùng chính sách ẩn lỗi và correlation ID tại đó.

## 7. Logging: đủ để debug, ít dữ liệu nhất có thể

Log nội bộ có thể ghi thông tin mà client không được thấy, nhưng **log cũng là nơi lưu trữ nhạy cảm**. Cần kiểm soát truy cập, retention, redaction và transmission.

Một mẫu log cấu trúc:

~~~text
level=ERROR event=checkout_failed errorCode=INTERNAL_ERROR
requestId=6efdbf4c-55a5-4d3c-a04a-4f0f9abce235
route=/api/checkouts method=POST status=500
exceptionClass=PaymentAdapterException
~~~

Dữ liệu trong ví dụ là minh họa. Stack trace nội bộ có thể hữu ích nhưng có nguy cơ chứa dữ liệu trong exception messages và stack context. Chỉ log exception đầy đủ ở nơi đã có policy xử lý secret, phân quyền, retention và scrub thích hợp.

**Nên log:**

- Event name, stable error code, HTTP status, route template, method, thời lượng, request ID / trace ID.
- Exception class và stacktrace trong kênh bảo vệ (nếu cần, theo mức log phù hợp).
- Dependency name **đã được whitelist**, timeouts, retry count, outcome.

**Không log mặc định:**

- `Authorization`, `Cookie`, `Set-Cookie`, API key, password, OTP, token; đặc biệt không log toàn bộ HTTP headers.
- Toàn bộ query/body JSON nếu chứa PII hoặc thông tin thanh toán.
- JDBC URL mang password, SQL statements có giá trị nhạy cảm, raw third-party response.
- Định danh người dùng/địa chỉ IP không cần thiết cho case; nếu có nhu cầu pháp lý/vận hành phải tuân theo chính sách bảo vệ dữ liệu.

**Whitelist tốt hơn blacklist:** log các metadata được định nghĩa rõ thay vì ghi mọi trường rồi cố thay tất cả secret bằng dấu sao. Secrets có thể xuất hiện ở key không đoán trước, nested JSON, exception cause, URL và cả file path.

### 7.1. Tránh log injection và cardinality bùng nổ

Khi log dữ liệu không tin cậy (nếu thực sự cần), cấu trúc hóa và sanitize control characters để một giá trị chứa newline không giả tạo thêm log entry. Không lấy raw URL/query làm metric label (các id khác nhau gây high cardinality). Dùng route template như `/api/orders/{id}`.

Nếu có log correlation ID, hãy đặt kích thước tối đa hợp lý; ví dụ này tự sinh UUID nên không phải xử lý chuỗi tùy ý từ client.

## 8. MDC và request-scoped correlation ID

MDC (Mapped Diagnostic Context) của SLF4J lưu các cặp key/value gắn với **thread hiện tại**. Trong Servlet MVC đồng bộ, filter có thể thêm `requestId` để các log statements trong cùng thread đọc được:

~~~java
try (MDC.MDCCloseable ignored =
        MDC.putCloseable("requestId", requestId)) {
    filterChain.doFilter(request, response);
}
~~~

`MDC.putCloseable` tự gỡ entry khi thoát scope, kể cả exception. Nếu dùng `MDC.put(...)`, phải có `finally { MDC.remove("requestId"); }` để không rò context qua thread pool.

Ví dụ log pattern:

~~~properties
logging.pattern.level=%5p [rid:%X{requestId}]
~~~

Đây chỉ minh họa đưa MDC vào console pattern; nếu dùng structured JSON logging, cần cấu hình field tương ứng. Với Spring Boot + Micrometer Tracing, log pattern và MDC có thể đã có traceId/spanId; đừng ghi đè các key tracing đang được framework quản lý.

### 8.1. MDC có giới hạn quan trọng

MDC thường dựa trên ThreadLocal; **không tự lan truyền an toàn qua** `@Async`, `CompletableFuture`, thread pool, scheduled tasks, virtual threads hoặc reactor contexts. Nếu request chuyển thread, cần cơ chế context propagation phù hợp với công nghệ đang dùng (Micrometer Context Propagation, executor task decorator, OpenTelemetry context), rồi dọn context đúng scope.

Một request ID dùng cho cả chuỗi request không có nghĩa là mỗi async task tự thấy MDC đó. Nếu servlet request bước vào ERROR hoặc ASYNC dispatch mới, `OncePerRequestFilter` có cờ `shouldNotFilterErrorDispatch()` / `shouldNotFilterAsyncDispatch()` và dispatcher registration cần được kiểm tra; demo ở mục 9 thiết kế cho synchronous MVC handlers thông thường.

### 8.2. Khi nào trả mã cho client?

- HTTP response header, ví dụ `X-Request-ID: <uuid>`, giúp support kiểm tra bằng DevTools và client logs.
- Error body field `requestId` với **đúng ID trong header**; test tự động phải đối chiếu hai chỗ.
- Thành công cũng có thể trả header để hỗ trợ điều tra mọi lần gọi; đừng bắt client phải tạo lỗi mới lấy được ID.
- Nếu đã dùng W3C Trace Context, cân nhắc publish `traceId` được phép sử dụng, phân biệt với internal span id và policy observability.

Trong browser, nếu cần JavaScript đọc `X-Request-ID` qua CORS, server cần cấu hình `Access-Control-Expose-Headers: X-Request-ID` với origin policy phù hợp. Không mở CORS bừa hoặc dùng `*` với credentials nếu không phù hợp.

## 9. Dự án Spring Boot Java 17 chạy được

Dự án hoàn chỉnh minh họa **server-generated correlation ID**, **safe error response**, **validation và JSON parse errors**, **domain conflict**, lỗi 500 giả lập và test không rò stacktrace.

Cấu trúc:

~~~text
safe-error-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/SafeErrorApplication.java
    │   └── resources/application.properties
    └── test/java/demo/SafeErrorApiTest.java
~~~

### 9.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>safe-error-demo</artifactId>
    <version>1.0.0</version>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
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

### 9.2. application.properties

~~~properties
server.error.include-stacktrace=never
server.error.include-message=never
server.error.include-binding-errors=never
server.error.include-exception=false
server.error.include-path=never
server.error.whitelabel.enabled=false

logging.pattern.level=%5p [rid:%X{requestId}]
~~~

### 9.3. SafeErrorApplication.java

Đặt tất cả code sau trong **một file** `src/main/java/demo/SafeErrorApplication.java`. Chỉ có một top-level `public class`, các thành phần còn lại package-private.

~~~java
package demo;

import java.io.IOException;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.stereotype.Component;
import org.springframework.validation.FieldError;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.context.request.WebRequest;
import org.springframework.web.filter.OncePerRequestFilter;
import org.springframework.web.servlet.mvc.method.annotation.ResponseEntityExceptionHandler;

@SpringBootApplication
public class SafeErrorApplication {
    public static void main(String[] args) {
        SpringApplication.run(SafeErrorApplication.class, args);
    }
}

@Component
class RequestIdFilter extends OncePerRequestFilter {
    static final String ATTRIBUTE = RequestIdFilter.class.getName() + ".requestId";
    static final String HEADER = "X-Request-ID";

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {

        // Không tin cậy X-Request-ID tự gửi từ client.
        String requestId = UUID.randomUUID().toString();
        request.setAttribute(ATTRIBUTE, requestId);
        response.setHeader(HEADER, requestId);

        try (MDC.MDCCloseable ignored =
                     MDC.putCloseable("requestId", requestId)) {
            chain.doFilter(request, response);
        }
    }
}

record RegistrationRequest(
        @NotBlank String username,
        @NotBlank @Email String email) {
}

record FieldIssue(String field, String code) {
}

record SafeError(
        String code,
        String message,
        String requestId,
        List<FieldIssue> violations) {
}

class UsernameUnavailableException extends RuntimeException {
    UsernameUnavailableException() {
        super("Username is unavailable");
    }
}

class InternalDemoException extends RuntimeException {
    InternalDemoException() {
        // Đây chỉ là giá trị giả dùng để kiểm thử chống rò thông tin.
        super("SYNTHETIC_DEMO_SECRET: connection failed at db.internal");
    }
}

@RestController
@RequestMapping("/api/demo")
class RegistrationController {
    // Kho dữ liệu trong RAM, chỉ dành cho demo.
    private final Set<String> usedNames = ConcurrentHashMap.newKeySet();

    RegistrationController() {
        usedNames.add("taken");
    }

    @PostMapping(path = "/register",
                 consumes = MediaType.APPLICATION_JSON_VALUE,
                 produces = MediaType.APPLICATION_JSON_VALUE)
    ResponseEntity<Map<String, String>> register(
            @Valid @RequestBody RegistrationRequest request) {

        String key = request.username().toLowerCase(Locale.ROOT);
        if (!usedNames.add(key)) {
            throw new UsernameUnavailableException();
        }
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(Map.of("status", "created"));
    }

    @GetMapping(path = "/unexpected",
                produces = MediaType.APPLICATION_JSON_VALUE)
    Map<String, String> unexpected() {
        throw new InternalDemoException();
    }

    @GetMapping(path = "/ping",
                produces = MediaType.APPLICATION_JSON_VALUE)
    Map<String, String> ping() {
        return Map.of("status", "ok");
    }
}

@RestControllerAdvice
class SafeErrorAdvice extends ResponseEntityExceptionHandler {
    private static final Logger LOG =
            LoggerFactory.getLogger(SafeErrorAdvice.class);

    private static String requestId(HttpServletRequest request) {
        Object id = request.getAttribute(RequestIdFilter.ATTRIBUTE);
        return id instanceof String s ? s : "unavailable";
    }

    private static String requestId(WebRequest request) {
        Object id = request.getAttribute(
                RequestIdFilter.ATTRIBUTE, WebRequest.SCOPE_REQUEST);
        return id instanceof String s ? s : "unavailable";
    }

    private static SafeError error(
            String code, String message, String id, List<FieldIssue> issues) {
        return new SafeError(code, message, id, issues);
    }

    @ExceptionHandler(UsernameUnavailableException.class)
    ResponseEntity<SafeError> usernameUnavailable(
            UsernameUnavailableException ex, HttpServletRequest request) {
        return ResponseEntity.status(HttpStatus.CONFLICT)
                .body(error(
                        "USERNAME_UNAVAILABLE",
                        "Không thể đăng ký tên người dùng này.",
                        requestId(request), List.of()));
    }

    @ExceptionHandler(InternalDemoException.class)
    ResponseEntity<SafeError> unexpected(
            InternalDemoException ex, HttpServletRequest request) {
        String id = requestId(request);

        // Log nội bộ theo policy, không trả ex.getMessage() cho client.
        LOG.error("Unexpected internal error requestId={}", id, ex);

        return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
                .body(error("INTERNAL_ERROR",
                        "Không thể xử lý yêu cầu. Vui lòng thử lại sau.",
                        id, List.of()));
    }

    @Override
    protected ResponseEntity<Object> handleHttpMessageNotReadable(
            HttpMessageNotReadableException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {
        SafeError body = error(
                "INVALID_JSON",
                "Không đọc được dữ liệu JSON.",
                requestId(request),
                List.of());
        return super.handleExceptionInternal(
                ex, body, headers, status, request);
    }

    @Override
    protected ResponseEntity<Object> handleMethodArgumentNotValid(
            MethodArgumentNotValidException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        List<FieldIssue> issues = ex.getBindingResult()
                .getFieldErrors().stream()
                .map(SafeErrorAdvice::fieldIssue)
                .distinct()
                .toList();

        SafeError body = error(
                "INVALID_INPUT",
                "Dữ liệu yêu cầu không hợp lệ.",
                requestId(request),
                issues);

        return super.handleExceptionInternal(
                ex, body, headers, status, request);
    }

    private static FieldIssue fieldIssue(FieldError error) {
        // Whitelist mã constraint, không trả rejectedValue hay raw message.
        String code = switch (error.getCode() == null
                ? "" : error.getCode()) {
            case "NotBlank" -> "REQUIRED_TEXT";
            case "Email" -> "INVALID_EMAIL";
            default -> "INVALID_VALUE";
        };
        return new FieldIssue(error.getField(), code);
    }

    @Override
    protected ResponseEntity<Object> handleExceptionInternal(
            Exception ex,
            Object body,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        // Với lỗi MVC chưa tùy biến: giữ nguyên HTTP status/headers.
        // Không tái sử dụng body/error detail do exception cung cấp.
        SafeError safe = error(
                status.is5xxServerError()
                        ? "INTERNAL_ERROR" : "REQUEST_ERROR",
                status.is5xxServerError()
                        ? "Không thể xử lý yêu cầu."
                        : "Yêu cầu không được chấp nhận.",
                requestId(request),
                List.of());

        return super.handleExceptionInternal(
                ex, safe, headers, status, request);
    }
}
~~~

**Lưu ý kỹ thuật khi đọc code:**

- `handleMethodArgumentNotValid` và `handleHttpMessageNotReadable` gọi thẳng `super.handleExceptionInternal(...)`, nên giữ body an toàn đã chọn mà không bị `handleExceptionInternal` override chung thay thế.
- Override `handleExceptionInternal` dùng cho các lỗi MVC khác do base class chuyển đến, giữ **status và headers framework** (ví dụ `Allow` của 405), đồng thời thay body bằng thông điệp trung tính. Tùy xử lý content negotiation, một số lỗi như 406 có thể không có response body; status vẫn là điều quan trọng.
- Không khai báo `@ExceptionHandler(Exception.class)` chung khiến status framework bị làm thành 500.
- Ví dụ internal error cố ý có chuỗi `SYNTHETIC_DEMO_SECRET`; chỉ nhằm xác minh chuỗi đó **không xuất hiện ở HTTP response**. Đây không phải một mật khẩu thật.
- Filter sinh UUID mới, không nhận header do client gửi, giảm spoof/log injection; `MDC.putCloseable` dọn context khi kết thúc.
- `Set` trong RAM được thêm atomically cho demo; trong sản phẩm thật dùng persistence uniqueness constraint/transaction và quy tắc bảo mật chống username enumeration.

### 9.4. Chạy và thử bằng curl

Chạy ở thư mục có `pom.xml`:

~~~bash
mvn spring-boot:run
~~~

Thử thành công:

~~~bash
curl -i 'http://localhost:8080/api/demo/ping'
~~~

HTTP 200, body tương đương:

~~~json
{"status":"ok"}
~~~

Ngoài body, header `X-Request-ID` chứa một UUID do server sinh.

Thử JSON body hợp lệ:

~~~bash
curl -i -X POST 'http://localhost:8080/api/demo/register' \
  -H 'Content-Type: application/json' \
  --data '{"username":"lan","email":"lan@example.com"}'
~~~

HTTP 201, body `{"status":"created"}`. Nếu gọi lại cùng username (không phân biệt hoa/thường), HTTP 409, response tương đương:

~~~json
{
  "code":"USERNAME_UNAVAILABLE",
  "message":"Không thể đăng ký tên người dùng này.",
  "requestId":"6efdbf4c-55a5-4d3c-a04a-4f0f9abce235",
  "violations":[]
}
~~~

UUID ở đây chỉ là **ví dụ về định dạng**; runtime sinh UUID mới mỗi request. Request ID trong header và body của **cùng một request** phải khớp chính xác.

Thử lỗi JSON cú pháp:

~~~bash
curl -i -X POST 'http://localhost:8080/api/demo/register' \
  -H 'Content-Type: application/json' \
  --data '{"username":"lan","email":'
~~~

HTTP 400 với `code=INVALID_JSON`, message an toàn và requestId; response không chứa đoạn JSON raw client gửi.

Thử validation với email không hợp lệ:

~~~bash
curl -i -X POST 'http://localhost:8080/api/demo/register' \
  -H 'Content-Type: application/json' \
  --data '{"username":"","email":"not-an-email"}'
~~~

HTTP 400, `code=INVALID_INPUT` và violations tương đương:

~~~json
[
  {"field":"username","code":"REQUIRED_TEXT"},
  {"field":"email","code":"INVALID_EMAIL"}
]
~~~

Thứ tự lỗi không được đảm bảo. Đặc biệt không có `"not-an-email"` trong body, tránh phản chiếu giá trị mà client gửi.

Thử lỗi hệ thống giả lập:

~~~bash
curl -i 'http://localhost:8080/api/demo/unexpected'
~~~

HTTP **500**, public body có `code=INTERNAL_ERROR` và thông điệp trung tính; **không có** chuỗi `SYNTHETIC_DEMO_SECRET`, `db.internal`, class name hoặc Java stacktrace. Console/log được bảo vệ có thể nhận exception stacktrace cùng requestId để chẩn đoán.

Các lệnh trên dùng cú pháp Bash. Trên Windows PowerShell, dùng `curl.exe` và thay dấu nối dòng `\` bằng cú pháp thích hợp hoặc viết cùng một dòng.

### 9.5. Kiểm thử MockMvc: header và body khớp ID, không rò exception

File `src/test/java/demo/SafeErrorApiTest.java`:

~~~java
package demo;

import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SafeErrorApiTest {
    @Autowired MockMvc mvc;
    @Autowired ObjectMapper mapper;

    private JsonNode assertCorrelation(MvcResult result) throws Exception {
        String header = result.getResponse().getHeader("X-Request-ID");
        assertNotNull(header);
        UUID.fromString(header); // Ném lỗi nếu không phải UUID hợp lệ.

        JsonNode body = mapper.readTree(
                result.getResponse().getContentAsString());
        assertEquals(header, body.path("requestId").asText());
        return body;
    }

    @Test
    void malformedJsonReturnsSafe400() throws Exception {
        MvcResult result = mvc.perform(post("/api/demo/register")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"username\":\"lan\",\"email\":"))
            .andExpect(status().isBadRequest())
            .andReturn();

        JsonNode body = assertCorrelation(result);
        assertEquals("INVALID_JSON", body.path("code").asText());
        assertFalse(result.getResponse().getContentAsString()
                .contains("HttpMessageNotReadableException"));
    }

    @Test
    void validationDoesNotEchoRejectedValues() throws Exception {
        MvcResult result = mvc.perform(post("/api/demo/register")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"username":"","email":"private-input@example.invalid!"}
                    """))
            .andExpect(status().isBadRequest())
            .andReturn();

        JsonNode body = assertCorrelation(result);
        assertEquals("INVALID_INPUT", body.path("code").asText());
        assertFalse(result.getResponse().getContentAsString()
                .contains("private-input@example.invalid!"));
    }

    @Test
    void internalErrorHidesStacktraceAndExceptionMessage() throws Exception {
        MvcResult result = mvc.perform(get("/api/demo/unexpected"))
            .andExpect(status().isInternalServerError())
            .andReturn();

        JsonNode body = assertCorrelation(result);
        assertEquals("INTERNAL_ERROR", body.path("code").asText());

        String serialized = result.getResponse().getContentAsString();
        assertFalse(serialized.contains("SYNTHETIC_DEMO_SECRET"));
        assertFalse(serialized.contains("db.internal"));
        assertFalse(serialized.contains("InternalDemoException"));
        assertFalse(serialized.contains("SafeErrorApplication.java"));
        assertFalse(serialized.contains("stackTrace"));
        assertFalse(serialized.contains("\"trace\""));
    }

    @Test
    void clientCannotChooseCorrelationId() throws Exception {
        MvcResult result = mvc.perform(get("/api/demo/unexpected")
                .header("X-Request-ID", "attacker-controlled"))
            .andExpect(status().isInternalServerError())
            .andReturn();

        JsonNode body = assertCorrelation(result);
        assertFalse("attacker-controlled".equals(
                body.path("requestId").asText()));
    }

    @Test
    void successAlsoHasRequestIdHeader() throws Exception {
        MvcResult result = mvc.perform(get("/api/demo/ping"))
            .andExpect(status().isOk())
            .andReturn();
        String header = result.getResponse().getHeader("X-Request-ID");
        assertNotNull(header);
        UUID.fromString(header);
        assertEquals("{\"status\":\"ok\"}",
                result.getResponse().getContentAsString());
    }
}
~~~

Chạy:

~~~bash
mvn test
~~~

Các test xác nhận **hành vi HTTP**, không phụ thuộc UUID cố định. Test JSON so sánh field code và ID; riêng body của endpoint thành công chỉ có một field status nên có thể so sánh trực tiếp. Với API thực tế, nên dùng JSON tree/JSONPath và kiểm tra response headers toàn bộ.

**Giới hạn của bộ kiểm thử:** Demo bao phủ synchronous MVC handlers trong `MockMvc`. Nó chưa chứng minh error dispatch qua container, filter chain có Spring Security, async thread context, gateway reverse proxy, response bị commit một phần, hoặc lỗi từ actuator. Với ứng dụng thật, viết thêm integration tests chạy embedded server + security/proxy, kiểm tra cả JSON, HTML error, headers và logs.

## 10. Điều gì vẫn có thể rò dù đã có @RestControllerAdvice?

### 10.1. Error trước khi vào DispatcherServlet

Authentication failures xảy ra trong Spring Security filters có thể bỏ qua controller advice. Nếu muốn response JSON thống nhất, cấu hình `AuthenticationEntryPoint` cho 401 và `AccessDeniedHandler` cho 403, rồi áp dụng cùng safe error code và request ID. Security layer cần xác định error detail nào có thể công bố; không trả stacktrace hay chi tiết lý do xác thực mật khẩu thất bại.

### 10.2. Error trong serializer sau khi handler trả kết quả

Controller đã trả một object, nhưng Jackson không serialize được vì object graph có vòng hoặc getter ném exception. Nếu output đã ghi/headers đã commit, exception handler không thể bảo đảm thay bằng JSON lỗi 500. Vì vậy phải tránh serialize entity graph không kiểm soát; dùng response DTO, test các loại content. Với streaming response/file download/SSE, mô hình báo lỗi khác với JSON body thông thường.

### 10.3. Proxy, CDN, container error pages

Nginx, API gateway, load balancer hoặc servlet container có thể tự tạo trang lỗi HTTP khi backend chết hoặc timeout. Cấu hình lỗi của Spring Boot **không kiểm soát toàn bộ các tầng này**. Kiểm tra các mã 502/503/504 từ gateway; đảm bảo trang HTML không tiết lộ upstream host, nội dung debug hay exception details.

### 10.4. Error details trong observability và alerting

- APM/tracing có thể tự thu request attributes và exception events; cấu hình tắt/cắt PII, bearer token, password.
- Log aggregation và third-party alerting là các điểm truyền dữ liệu; có quyền truy cập và retention riêng.
- Thông điệp alert nên chứa error code/trace ID và liên kết dashboard, không copy toàn bộ request payload.
- Khi phân tích sự cố, không gửi log chứa dữ liệu thật lên issue công khai; redact trước khi chia sẻ.

### 10.5. Correlation ID và bảo mật

Không bao giờ coi `X-Request-ID` như một "mật khẩu" cho endpoint tra log công khai. Chỉ nhân viên được phân quyền mới được tra log phù hợp; rate limit endpoint hỗ trợ nếu có. Nếu exposure của ID tạo khả năng liệt kê, dùng ID ngẫu nhiên đủ entropy như UUIDv4, không dùng id tăng dần hoặc user id thô.

## 11. Tình huống trước/sau

### Sai: đưa dữ liệu dependency thẳng cho client

~~~java
try {
    database.save(entity);
} catch (Exception ex) {
    return ResponseEntity.status(500).body(Map.of(
            "error", ex.getMessage(),
            "trace", Arrays.toString(ex.getStackTrace())));
}
~~~

Đoạn minh họa có `database`, `entity` chưa định nghĩa; đây là anti-pattern. Nó làm lộ stack trace và exception details.

### Đúng: thông điệp an toàn + mã tra cứu

~~~java
try {
    database.save(entity);
} catch (KnownDatabaseOutage ex) {
    String requestId = currentRequestId();
    safeLogger.error("Database operation unavailable; rid={}",
            requestId, ex);
    throw new DependencyUnavailableException();
}
~~~

Đây là pseudo-code trong service/adapter (các helper và exception minh họa), cho thấy adapter phân loại **lỗi đã xác định** và giữ cause ở kênh nội bộ. Web advice ánh xạ nó thành status thích hợp và safe body; không tự in message dependency ra HTTP. Với lỗi bất ngờ, đừng chuyển bừa tất cả thành `DependencyUnavailableException`; giữ nguyên cause để vận hành thấy bug.

**Cẩn thận:** việc log `ex` có thể bao gồm dữ liệu nhạy cảm trong message hoặc cause. Chỉ log exception đầy đủ nơi đã có chính sách che secret, hạn chế người xem, thời hạn lưu và logging middleware phù hợp. Nếu dependency đưa secret vào exception, điều chỉnh/redact từ adapter thay vì đẩy nguyên văn vào log chung.

## 12. Một checklist cho API production

1. **Error contract:** 4xx/5xx đúng nghĩa, `code` ổn định, `message` an toàn, request/trace ID nhất quán, field errors không echo raw values.
2. **Default error safety:** cấu hình Boot `include-stacktrace/message/binding-errors` về `never` và `include-exception=false`; kiểm tra cả HTML và proxy errors.
3. **Explicit handlers:** không chuyển `ex.getMessage()`, `Throwable.toString()`, `StackTraceElement[]` hoặc raw SQL sang body.
4. **Correlation:** sinh ID đủ ngẫu nhiên hoặc chỉ chấp nhận từ trusted gateway; kiểm tra header/body khớp và log có thể tra cứu.
5. **MDC lifecycle:** dọn MDC ngay khi kết thúc; kiểm tra context propagation khi async/virtual threads/tracing.
6. **Logs:** whitelist metadata; redact secret/PII; bảo vệ quyền truy cập, thời hạn lưu, truyền tải, backup.
7. **Security:** 401/403 filter chain có error response an toàn; không lộ việc account tồn tại khi policy yêu cầu.
8. **Validation:** phân biệt JSON parse và Bean Validation; không trả raw rejectedValue hoặc toàn bộ body.
9. **Integration:** test thành công, 400, 404, 405, 415, 409, 500, errors trước controller, errors trong serialization và gateway; không bỏ qua response headers.
10. **Review:** xem error contract như API công khai, ghi rõ các error codes trong tài liệu và kiểm tra security review trước khi triển khai.

## 13. Bài tập

**Bài 1 — Audit response:** Phát hiện dữ liệu nên ẩn trong:

~~~json
{
  "message": "org.postgresql.util.PSQLException: password authentication failed for service-account",
  "path": "/reset?token=abc123",
  "debug": "at com.acme.account.ResetService.reset(ResetService.java:77)"
}
~~~

Thiết kế một body 500 an toàn có `code` và `requestId`.

**Bài 2 — Correlation:** Một browser gửi hai HTTP requests lỗi 500. Giải thích vì sao chúng nên có hai request IDs khác nhau nhưng có thể cùng error code; viết test khẳng định body requestId = response header.

**Bài 3 — MDC:** Cho một request dùng servlet thread pool. Hệ quả khi quên `MDC.remove("requestId")` trong `finally` là gì? Viết phiên bản dùng `MDC.putCloseable`.

**Bài 4 — Async:** Handler `CompletableFuture.supplyAsync(...)` log không có requestId. Giải thích vì sao ThreadLocal MDC không tự đi qua executor; đề xuất context propagation phù hợp.

**Bài 5 — Validation:** Request có `password` chưa đạt constraint. Đề xuất JSON errors chỉ nêu field `password`, error code phù hợp, không phản chiếu password. Kiểm tra test không chứa rejectedValue.

**Bài 6 — Framework:** So sánh behavior của `@RestControllerAdvice` với lỗi `HttpMessageNotReadableException` và lỗi xác thực phát sinh trong Spring Security filter. Xác định handler chính xác cho mỗi đường.

**Bài 7 — Observability:** Thiết kế log event cho database timeout gồm error code, requestId, route template, status và duration; chỉ ra chỗ không nên ghi SQL arguments hoặc authentication header.

**Bài 8 — Production integration:** Dùng embedded server test GET nonexistent path, sai HTTP method, sai Content-Type và lỗi dependency; xác minh mọi response từ tầng web/proxy không có stack trace và có correlation ID nếu hợp đồng yêu cầu.

## 14. Tóm tắt kiến thức

- Lỗi trả cho client phải **dễ hiểu nhưng tối giản**; thông tin kỹ thuật sâu thuộc kênh quan sát nội bộ được bảo vệ.
- **Error code** cho biết nhóm lỗi; **requestId/traceId** chỉ đúng lần thực hiện để đối chiếu; các mã này không thay thế authentication/authorization.
- `@RestControllerAdvice` và `ResponseEntityExceptionHandler` giúp chuẩn hóa các lỗi MVC, nhưng không tự bao phủ Spring Security filters, proxies, async hoặc response đã commit.
- Spring Boot có cấu hình ngăn mặc định xuất `trace`, exception message và binding details. Custom handlers vẫn phải tự tuân thủ nguyên tắc an toàn.
- Không trả `exception.getMessage()`/stacktrace cho client; ngay cả nội bộ cũng cần chính sách redaction và kiểm soát log.
- Kiểm thử **không rò dữ liệu nhạy cảm** bằng các chuỗi giả, đồng thời so khớp request ID giữa header và body.

## 15. Tài liệu tham khảo

- [Spring Boot 3.5 — Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/): các thuộc tính `server.error.include-*`, `server.error.whitelabel.enabled`.
- [Spring Framework 6.2 — Error Responses](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-ann-rest-exceptions.html): Spring MVC error handling, `ErrorResponse`, `ProblemDetail`.
- [Spring Framework 6.2 — ResponseEntityExceptionHandler API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/servlet/mvc/method/annotation/ResponseEntityExceptionHandler.html): chữ ký override chính xác của các exception hooks.
- [Spring Framework 6.2 — OncePerRequestFilter API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/filter/OncePerRequestFilter.html): request, error, async dispatch.
- [SLF4J — MDC](https://www.slf4j.org/manual.html): mapped diagnostic context, putCloseable và logging.
- [W3C Trace Context](https://www.w3.org/TR/trace-context/): `traceparent` và distributed tracing.
- [RFC 9457 — Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457): định dạng phản hồi lỗi chuẩn.
