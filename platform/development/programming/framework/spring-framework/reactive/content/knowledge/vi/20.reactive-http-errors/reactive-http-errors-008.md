# Che thông tin nhạy cảm và giữ mã tương quan trong lỗi HTTP với Spring WebFlux

**Module:** Spring Framework - reactive. **Nhóm:** Lỗi HTTP.

Khi một API lỗi, phía gọi cần một phản hồi **ổn định, dễ xử lý và đủ thông tin để yêu cầu hỗ trợ**; phía vận hành cần dấu vết có thể lần theo qua log, trace và các service. Hai mục tiêu này không đồng nghĩa với việc gửi stack trace, tên máy, SQL, token, request body hay exception message nội bộ cho client.

Bài học này trình bày ranh giới giữa thông tin **công khai** và **nội bộ**, cách tạo và truyền correlation ID trong WebFlux, cách xử lý các thời điểm response khác nhau, và kiểm thử tính an toàn của hợp đồng lỗi. Các ví dụ nhỏ ở phần 1–9 minh họa từng nguyên tắc; từ phần 10 trở đi là cách chọn error boundary, dự án mẫu, kiểm thử và quy trình vận hành.

## 1. Mục tiêu và mô hình đe dọa

Đầu ra mong đợi: chọn đúng HTTP status/error code, xây body lỗi công khai an toàn, gắn một correlation ID có thể tra cứu ở response và log, giữ ngữ cảnh sau các phép chuyển scheduler, kiểm chứng không lộ bí mật và xử lý được trường hợp response đã bắt đầu gửi.

Xem các nguồn dữ liệu sau là **không đáng tin và có thể nhạy cảm**: path/query, cookie, `Authorization`, API key, username, email, payload JSON, validation rejected value, exception message, SQL, JDBC/R2DBC diagnostics, stack trace, raw response body từ upstream và inbound correlation header do client gửi. Lỗi do thư viện ném ra có thể chứa dữ liệu này ngay cả khi controller không cố ý log.

**Quy tắc bất biến:** không đưa thông tin nội bộ ra HTTP chỉ vì nó tiện cho debug. Logging cũng cần chính sách bảo vệ; log không phải nơi mặc định an toàn để sao chép toàn bộ request.

## 2. Hợp đồng lỗi bên ngoài: status, code, detail, correlation ID

Một lỗi REST nên có ít nhất: (1) HTTP status đúng hợp đồng; (2) error `code` ổn định để máy xử lý; (3) `title`/`detail` đã kiểm duyệt, có thể bản địa hóa; (4) `correlationId` không tiết lộ thông tin người dùng; (5) media type nhất quán, ví dụ `application/problem+json` cho RFC 9457 Problem Details.

Ví dụ phản hồi công khai (giá trị ID minh họa):

~~~http
HTTP/1.1 500 Internal Server Error
Content-Type: application/problem+json
X-Correlation-ID: 5eafc70a-84e9-46d8-bcc0-034aa5f1f2c4

{"type":"https://api.example.test/problems/internal-error","title":"Internal server error","status":500,"detail":"An unexpected error occurred. Provide the correlation ID to support.","code":"INTERNAL_ERROR","correlationId":"5eafc70a-84e9-46d8-bcc0-034aa5f1f2c4"}
~~~

Ví dụ này **không** chứa tên class exception, hostname, SQL, đường dẫn file, session token, thông tin khách hàng hay raw input. Người dùng đưa correlation ID cho support; support dùng quyền truy cập log/trace được kiểm soát để tra cứu nguyên nhân. Không coi ID là mật khẩu, bằng chứng định danh hay cơ chế phân quyền.

Với 400/422, chỉ cho biết field và quy tắc đã công khai; không echo nguyên giá trị bị từ chối nếu có thể chứa secret. Với 401/403, không tiết lộ người dùng/tài nguyên nội bộ có tồn tại hay không nếu chính sách chống enumeration yêu cầu điều đó. Với 429/503, có thể dùng `Retry-After` theo contract; không biến chi tiết hạ tầng thành thông báo cho client.

## 3. Phân loại dữ liệu được phép xuất hiện

| Thành phần | Có thể trả client | Chỉ giữ nội bộ có kiểm soát |
| --- | --- | --- |
| Mã HTTP, mã lỗi nghiệp vụ, thông điệp an toàn | Có | Có |
| Correlation ID sinh từ hệ thống, không gắn PII | Có | Có |
| Stack trace, package/class Java, topology, hostname | Không | Chỉ lưu nếu cần và được phân quyền |
| SQL, connection URL, token, cookie, API key | Không | Mặc định phải che; không log secret |
| Validation field đã allowlist | Có điều kiện | Có |
| Rejected value, request body, downstream error body | Không mặc định | Cần chính sách riêng, lọc dữ liệu, retention |

**Allowlist tốt hơn denylist:** xây `ProblemDetail` từ một tập trường đã duyệt thay vì lấy exception rồi cố tìm chuỗi mật khẩu để thay thế. Regex che dữ liệu chỉ là lớp phòng vệ bổ sung; không thể phát hiện mọi dạng secret.

## 4. Vòng đời của correlation ID và vùng tin cậy

Có thể sử dụng `X-Correlation-ID` dạng UUID độc lập với `traceId`/`spanId` do hệ thống tracing tạo. Hai loại ID có thể cùng tồn tại: correlation ID để người dùng/support đối chiếu request, trace ID để khám phá quan hệ giữa các span. Không dùng user ID, email hay nội dung secret làm correlation ID.

Luồng hợp lý:

~~~text
HTTP request -> gateway (trusted boundary)
             -> WebFilter chọn/tạo ID
             -> exchange attribute + Reactor Context
             -> handler/service/WebClient
             -> log/trace có ID
             -> response header + error body an toàn
~~~

Nếu nhận header từ bên ngoài, phải quyết định rõ chính sách: gateway đáng tin có thể xác minh format/chiều dài rồi truyền tiếp; trường hợp không có gateway, cách an toàn nhất là **sinh UUID mới ở ứng dụng**. Không đưa header tùy ý của client nguyên văn vào log; kẻ tấn công có thể chèn ký tự xuống dòng, tạo ID dài hoặc giả mạo dấu vết.

Khi propagate qua nhiều service, cấu hình thống nhất việc gửi ID và chính sách đổi ID ở trust boundary. Trong hệ thống có OpenTelemetry/W3C Trace Context, để tracing instrumentation quản lý `traceparent`; custom correlation ID không thay thế protocol tracing.

## 5. Đưa ID vào WebFlux không phụ thuộc một thread

`ServerWebExchange` chứa request/response của một HTTP exchange và có `attributes` phù hợp cho middleware trao đổi dữ liệu; Reactor `Context` chứa metadata theo **subscription**, không phải global variable. Có thể đặt cùng một ID vào cả hai nơi để các tầng phù hợp truy xuất.

Ví dụ minh họa một `WebFilter` sinh ID mới ở đầu request (đoạn độc lập, **không** thêm đồng thời với `CorrelationIdFilter` trong dự án hoàn chỉnh ở phần 11):

~~~java
import java.util.UUID;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;
import reactor.core.publisher.Mono;

@Component
public class ExampleCorrelationFilter implements WebFilter {
    @Override
    public Mono<Void> filter(ServerWebExchange exchange, WebFilterChain chain) {
        String id = UUID.randomUUID().toString();
        exchange.getAttributes().put("correlationId", id);
        exchange.getResponse().getHeaders().set("X-Correlation-ID", id);
        return chain.filter(exchange)
            .contextWrite(ctx -> ctx.put("correlationId", id));
    }
}
~~~

`Mono<Void>` được **trả lại** cho WebFlux, không gọi `subscribe()` thủ công. Việc đặt response header ở đây diễn ra trước khi chain được thực thi/commit. Bất kỳ bộ lọc nào cần thay đổi response sau này phải kiểm `isCommitted()` hoặc dùng callback trước commit; đừng cố ghi header sau khi bytes đã được gửi.

Tại service, có thể đọc `Mono.deferContextual(ctx -> Mono.just(ctx.getOrDefault("correlationId", "unavailable")))` trong cùng reactive chain. `Context` không tự động được truyền sang một luồng xử lý tách rời do tự gọi `subscribe()` hoặc qua mọi thư viện; kiểm tra đúng chỗ tạo subscription và tích hợp propagator khi cần.

## 6. Logging và redaction trong môi trường reactive

Log có cấu trúc nên có `event`, `correlationId`, `errorCode`, `status`, `exceptionType` (nếu chính sách cho phép), `service`, `durationMs` và `traceId` khi có tracing. Không đặt raw body, token, cookie, JDBC URL hay exception message chưa duyệt làm field mặc định. Các câu như `log.error("request {}", request)` có thể vô tình tuần tự hóa dữ liệu riêng tư.

Ví dụ thông điệp log được thiết kế an toàn:

~~~text
event=http_request_failed correlationId=5eafc70a-84e9-46d8-bcc0-034aa5f1f2c4 errorCode=INTERNAL_ERROR status=500 exceptionType=IllegalStateException
~~~

Ở tầng trung tâm thu log, thực thi truy cập theo vai trò, retention có hạn, kiểm soát export và rà soát detection đối với secret/PII. Không dùng ID tương quan để vượt quyền xem log. Nếu cần thêm stack trace nội bộ, lưu ở sink có mức bảo vệ phù hợp và đánh giá nội dung trước khi ghi.

**Lưu ý MDC:** MDC phổ biến dựa trên `ThreadLocal`; Reactor có thể chuyển scheduler hoặc event loop giữa các tín hiệu. Không set MDC một lần rồi giả định nó luôn đúng; dùng Reactor Context và cơ chế context propagation/observability đã cấu hình, hoặc log `correlationId` tường minh tại điểm có dữ liệu. Không dùng `ThreadLocal` làm nguồn duy nhất của ID.

## 7. Qua WebClient, gateway và các dịch vụ phụ thuộc

Mỗi request outbound cần tách rõ request ID/correlation ID với dữ liệu xác thực. Khi dùng Spring Boot `WebClient.Builder` được quản lý cùng Micrometer Observation, tracing propagation có thể được cấu hình; không giả định `WebClient.create()` tự mang mọi trace header của ứng dụng.

Khi propagate custom ID, chỉ gửi header đến **đích tin cậy được allowlist** và giữ đúng ID của request đang xử lý. Không gửi token hoặc user metadata cùng ID để tiện debug. Khi upstream trả 500 kèm body chi tiết, ánh xạ về `DEPENDENCY_UNAVAILABLE` hoặc `INTERNAL_ERROR` và log mã/status có kiểm soát, **không proxy nguyên error body** cho client.

Nếu downstream dùng retry, giữ một correlation ID cho yêu cầu logic và sử dụng span/attempt index riêng để phân biệt từng lần thử; xác minh idempotency trước khi retry request có side effect. ID giúp truy vết, không bảo đảm exactly-once.

## 8. Phân biệt lỗi trước và sau khi response commit

**Trước commit:** framework còn có thể chọn status, headers và response body. `@ExceptionHandler`, `@RestControllerAdvice`, `WebExceptionHandler` hoặc error handler phù hợp sẽ tạo `ProblemDetail` công khai và log một lần. Lựa chọn tầng bắt lỗi phụ thuộc lỗi phát sinh ở controller, functional handler hay WebFilter.

**Sau commit:** status/header có thể đã gửi đến client, đặc biệt với SSE, NDJSON, chunked response hoặc download. Không thể thay response đang truyền thành JSON lỗi mới hoặc đổi mã 200 thành 500 một cách đáng tin. Chỉ có thể kết thúc stream, gửi frame lỗi *in-band* nếu giao thức và trạng thái cho phép, ghi log/metric với correlation ID, hoặc để client reconnect theo hợp đồng.

Không xử lý `onErrorResume` bằng cách trả một response thứ hai sau khi output đã được commit; điều đó có thể tạo protocol corruption hoặc làm mất ngữ cảnh lỗi. Xem chi tiết tình huống trong phần 15.

## 9. QA contract lỗi và runbook

Kiểm thử ít nhất các đường đi: lỗi validation 400/422; unauthorized/forbidden 401/403; lỗi nghiệp vụ 404/409; exception không phân loại được 500; lỗi WebFilter trước handler; upstream 5xx; client hủy stream; lỗi khi response đã commit.

Với từng trường hợp, assert `HTTP status`, `Content-Type`, allowlisted `code`, `detail`, `X-Correlation-ID`, sự tương ứng giữa header và body, đồng thời phủ định các dấu vết như password giả, tên DB, stack trace, `Authorization` và raw exception message. Dùng `WebTestClient` để kiểm tra HTTP contract; kiểm tra log/trace qua appender hoặc instrumentation test với log capture đã kiểm soát.

Checklist vận hành: có dashboard tỉ lệ lỗi/latency, alert theo nhóm status và upstream, đường tra cứu correlation ID, chính sách redaction log, quyền truy cập support, tài liệu cho khách hàng về cách báo mã lỗi mà không gửi secret, và replayable test với marker giả để phát hiện rò rỉ.

**Ví dụ xử lý sự cố:** client báo 500 và correlation ID → support tra log theo ID → xác định exception type, service/trace span và thời điểm → điều tra trong hệ thống nội bộ → phản hồi khách hàng bằng thông điệp an toàn. Không yêu cầu khách hàng gửi token, full cookie hoặc database credentials.

---
## 10. Chọn đúng exception boundary trong Spring WebFlux

Spring WebFlux có nhiều tầng xử lý lỗi. Dùng đúng tầng giúp response được làm sạch dù lỗi xảy ra trong controller, filter hay phần xử lý HTTP bên ngoài.

| Cơ chế | Phạm vi | Dùng khi |
| --- | --- | --- |
| `@ExceptionHandler` | Exception gắn với controller/handler method | Lỗi nghiệp vụ cụ thể, mapping sang status/error code |
| `@RestControllerAdvice` | Nhiều annotated controller | Error contract chung cho REST API |
| `ResponseEntityExceptionHandler` | Built-in exception của Spring WebFlux và `ErrorResponseException` | Chuẩn hóa lỗi binding, method, media type và các lỗi framework |
| `WebExceptionHandler` | WebFilter chain và target WebHandler | Lỗi phát sinh ngoài annotated controller, ví dụ lỗi trong filter |
| `WebFilter` | Bao quanh request/response chain | Gắn correlation ID, timing và request context |
| `WebClient` filter / `onStatus` | HTTP client outbound | Chuẩn hóa lỗi từ service phụ thuộc, không chuyển raw downstream body |

`@RestControllerAdvice` không thay thế `WebExceptionHandler` cho lỗi xảy ra trước hoặc ngoài controller invocation. Ví dụ một `WebFilter` ném exception có thể không đi qua controller advice.

### 10.1. Dùng ResponseEntityExceptionHandler để làm sạch lỗi framework

Spring WebFlux cung cấp `ResponseEntityExceptionHandler` làm base class cho `@ControllerAdvice`. Có thể override `handleExceptionInternal` để thay body mặc định bằng ProblemDetail an toàn. Điều này đặc biệt hữu ích vì built-in exception có thể mang detail kỹ thuật hoặc input không nên echo nguyên văn.

~~~java
@RestControllerAdvice
public class ApiExceptionHandler extends ResponseEntityExceptionHandler {

    @ExceptionHandler(OrderNotFoundException.class)
    public Mono<ResponseEntity<Object>> handleNotFound(
            OrderNotFoundException exception,
            ServerWebExchange exchange) {

        String id = CorrelationIdFilter.from(exchange);
        ProblemDetail problem = ApiProblems.create(
            HttpStatus.NOT_FOUND,
            "ORDER_NOT_FOUND",
            "Order not found",
            "The requested order was not found.",
            id
        );

        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.APPLICATION_PROBLEM_JSON);

        return super.handleExceptionInternal(
            exception, problem, headers, HttpStatus.NOT_FOUND, exchange);
    }

    @Override
    protected Mono<ResponseEntity<Object>> handleExceptionInternal(
            Exception exception,
            Object body,
            HttpHeaders headers,
            HttpStatusCode status,
            ServerWebExchange exchange) {

        String id = CorrelationIdFilter.from(exchange);
        ProblemDetail safeBody = ApiProblems.forStatus(status, id);

        HttpHeaders safeHeaders = headers == null
            ? new HttpHeaders()
            : new HttpHeaders(headers);

        safeHeaders.setContentType(MediaType.APPLICATION_PROBLEM_JSON);

        return super.handleExceptionInternal(
            exception, safeBody, safeHeaders, status, exchange);
    }
}
~~~

Ở đây:
- `OrderNotFoundException` có error code nghiệp vụ rõ và detail an toàn.
- Built-in WebFlux exceptions đi qua `handleExceptionInternal`; body gốc được thay bằng ProblemDetail tạo từ status.
- `correlationId` được lấy từ exchange attribute, cùng giá trị mà filter đã ghi vào response header.
- `instance` dùng URN opaque để không echo raw path.
- Nếu response đã commit, Spring không thể ghi đè response; cần log lỗi với correlation ID và xử lý theo giao thức streaming nếu có.

Không đưa `exception.getMessage()` vào `ApiProblems`. Khi cần thêm thông tin cho client, map exception sang error code và câu chữ đã được duyệt.

### 10.2. WebExceptionHandler cho lỗi ngoài controller

Dùng `WebExceptionHandler` như fallback cho lỗi từ WebFilter chain hoặc target WebHandler. Ví dụ dưới đây giữ `ResponseStatusException` status, còn lỗi không phân loại được trả 500. Nó luôn tạo public detail an toàn.

~~~java
@Component
@Order(-2)
public class SanitizingWebExceptionHandler implements WebExceptionHandler {

    private static final Logger log =
        LoggerFactory.getLogger(SanitizingWebExceptionHandler.class);

    private static final HandlerStrategies STRATEGIES =
        HandlerStrategies.withDefaults();

    private static final ServerResponse.Context RESPONSE_CONTEXT =
        new ServerResponse.Context() {
            @Override
            public List<HttpMessageWriter<?>> messageWriters() {
                return STRATEGIES.messageWriters();
            }

            @Override
            public List<ViewResolver> viewResolvers() {
                return STRATEGIES.viewResolvers();
            }
        };

    @Override
    public Mono<Void> handle(
            ServerWebExchange exchange, Throwable exception) {

        if (exchange.getResponse().isCommitted()) {
            return Mono.error(exception);
        }

        String id = CorrelationIdFilter.from(exchange);

        HttpStatusCode status =
            exception instanceof ResponseStatusException responseStatus
                ? responseStatus.getStatusCode()
                : HttpStatus.INTERNAL_SERVER_ERROR;

        log.error(
            "web_pipeline_failed correlationId={} exceptionType={}",
            id,
            exception.getClass().getName()
        );

        ProblemDetail problem = ApiProblems.forStatus(status, id);

        return ServerResponse.status(status)
            .contentType(MediaType.APPLICATION_PROBLEM_JSON)
            .bodyValue(problem)
            .flatMap(response ->
                response.writeTo(exchange, RESPONSE_CONTEXT));
    }
}
~~~

`ServerResponse.writeTo` cần `ServerResponse.Context` để lấy message writers và view resolvers. Ví dụ dùng default `HandlerStrategies`; nếu ứng dụng tùy biến codec, hãy dùng cùng writer configuration của server để error body có serialization nhất quán.

`@Order(-2)` đặt handler này trước status handler mặc định có order thấp ưu tiên hơn. Kiểm tra order của toàn bộ `WebExceptionHandler` trong ứng dụng, nhất là khi Spring Security hoặc custom error handler cũng tham gia. Không đăng ký nhiều catch-all handler mà không có thứ tự rõ ràng.

### 10.3. Mapping status thành public detail

Một factory tập trung giúp tất cả boundary trả cùng schema:

~~~java
final class ApiProblems {

    private ApiProblems() {}

    static ProblemDetail create(
            HttpStatusCode status,
            String code,
            String title,
            String detail,
            String correlationId) {

        ProblemDetail problem =
            ProblemDetail.forStatusAndDetail(status, detail);

        String slug = code.toLowerCase(Locale.ROOT)
            .replace('_', '-');

        problem.setType(URI.create(
            "https://api.example.test/problems/" + slug));
        problem.setTitle(title);

        // Opaque instance: không echo path/query có thể chứa PII.
        problem.setInstance(URI.create("urn:uuid:" + correlationId));

        problem.setProperty("code", code);
        problem.setProperty("correlationId", correlationId);

        return problem;
    }

    static ProblemDetail forStatus(
            HttpStatusCode status, String correlationId) {

        int value = status.value();

        String code = switch (value) {
            case 400 -> "INVALID_REQUEST";
            case 401 -> "UNAUTHENTICATED";
            case 403 -> "FORBIDDEN";
            case 404 -> "NOT_FOUND";
            case 405 -> "METHOD_NOT_ALLOWED";
            case 406 -> "NOT_ACCEPTABLE";
            case 409 -> "CONFLICT";
            case 413 -> "PAYLOAD_TOO_LARGE";
            case 415 -> "UNSUPPORTED_MEDIA_TYPE";
            case 429 -> "RATE_LIMITED";
            default -> status.is5xxServerError()
                ? "INTERNAL_ERROR"
                : "HTTP_ERROR";
        };

        String title = status.is5xxServerError()
            ? "Internal server error"
            : "Request failed";

        String detail = status.is5xxServerError()
            ? "An unexpected error occurred. Provide the correlation ID to support."
            : "The request could not be processed. Check the request and try again.";

        return create(status, code, title, detail, correlationId);
    }
}
~~~

Trong production, có thể thay `type` URI và câu chữ bằng tài liệu API của tổ chức. Không đưa hostname, stack trace hoặc exception message vào URI. Giữ `code` ổn định để client có thể xử lý mà không phụ thuộc câu chữ đã dịch.

## 11. Ví dụ hoàn chỉnh: Spring Boot 4.1.2 và Java 17+

Project minh họa:
- Tạo correlation ID cho mỗi request.
- Đặt cùng ID ở `X-Correlation-ID` và Reactor Context.
- Trả `ORDER_NOT_FOUND` an toàn cho lỗi nghiệp vụ.
- Trả `INTERNAL_ERROR` chung cho exception không dự kiến.
- Dùng `ResponseEntityExceptionHandler` để sanitize built-in WebFlux errors.
- Dùng `WebExceptionHandler` làm fallback cho lỗi ngoài controller.
- Cấu hình `WebClient` filter để truyền ID sang service nội bộ.
- Kiểm thử qua HTTP server thật bằng JDK `HttpClient`.

### 11.1. Cấu trúc thư mục

~~~text
webflux-error-correlation/
├── pom.xml
├── src/main/java/com/example/errors/
│   ├── ErrorCorrelationApplication.java
│   ├── CorrelationIdFilter.java
│   ├── ApiProblems.java
│   ├── ApiExceptionHandler.java
│   ├── SanitizingWebExceptionHandler.java
│   ├── DownstreamWebClientConfiguration.java
│   ├── Order.java
│   ├── OrderNotFoundException.java
│   └── OrderController.java
└── src/test/java/com/example/errors/
    └── ErrorCorrelationIntegrationTest.java
~~~

### 11.2. pom.xml

Spring Boot 4.1.2 là bản stable trong ví dụ; yêu cầu Java 17+ và Maven 3.6.3+.

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>webflux-error-correlation</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
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

### 11.3. ErrorCorrelationApplication.java

~~~java
package com.example.errors;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ErrorCorrelationApplication {

    public static void main(String[] args) {
        SpringApplication.run(ErrorCorrelationApplication.class, args);
    }
}
~~~

### 11.4. CorrelationIdFilter.java

~~~java
package com.example.errors;

import java.util.UUID;

import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;

import reactor.core.publisher.Mono;

@Component
@Order(Ordered.HIGHEST_PRECEDENCE)
public class CorrelationIdFilter implements WebFilter {

    public static final String HEADER = "X-Correlation-ID";
    public static final String ATTRIBUTE =
        CorrelationIdFilter.class.getName() + ".id";
    public static final String CONTEXT_KEY = "app.correlationId";

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange, WebFilterChain chain) {

        String id = UUID.randomUUID().toString();

        exchange.getAttributes().put(ATTRIBUTE, id);
        exchange.getResponse().getHeaders().set(HEADER, id);

        return chain.filter(exchange)
            .contextWrite(context -> context.put(CONTEXT_KEY, id));
    }

    public static String from(ServerWebExchange exchange) {
        String id = exchange.getAttribute(ATTRIBUTE);
        return id != null ? id : "unavailable";
    }
}
~~~

Ví dụ luôn tạo ID mới ở service boundary. Nếu có gateway tin cậy cấp ID, hãy thay chính sách này bằng logic chỉ nhận giá trị đã được gateway xác thực và validate theo allowlist; không đọc rồi echo nguyên văn header từ Internet.

### 11.5. Order.java và OrderNotFoundException.java

~~~java
package com.example.errors;

public record Order(String id, String description) {}
~~~

~~~java
package com.example.errors;

public class OrderNotFoundException extends RuntimeException {
}
~~~

Exception nghiệp vụ không cần chứa PII, token hoặc thông tin database. Public message được tạo ở exception handler, không lấy từ constructor message.

### 11.6. OrderController.java

~~~java
package com.example.errors;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/orders")
public class OrderController {

    @GetMapping("/{id}")
    public Mono<Order> get(@PathVariable String id) {

        if ("missing".equals(id)) {
            return Mono.error(new OrderNotFoundException());
        }

        if ("boom".equals(id)) {
            // Chỉ để chứng minh exception message không bị trả ra HTTP.
            return Mono.error(new IllegalStateException(
                "dbHost=orders-db.internal password=do-not-return"));
        }

        return Mono.just(new Order(id, "Sample order"));
    }
}
~~~

`/api/orders/boom` mô phỏng exception kỹ thuật có chuỗi nhạy cảm. Test sẽ xác nhận response không chứa `orders-db.internal` hoặc `do-not-return`.

### 11.7. ApiExceptionHandler.java

~~~java
package com.example.errors;

import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.MediaType;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;

@RestControllerAdvice
public class ApiExceptionHandler
        extends ResponseEntityExceptionHandler {

    @ExceptionHandler(OrderNotFoundException.class)
    public Mono<ResponseEntity<Object>> handleOrderNotFound(
            OrderNotFoundException exception,
            ServerWebExchange exchange) {

        String id = CorrelationIdFilter.from(exchange);

        ProblemDetail problem = ApiProblems.create(
            HttpStatus.NOT_FOUND,
            "ORDER_NOT_FOUND",
            "Order not found",
            "The requested order was not found.",
            id
        );

        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.APPLICATION_PROBLEM_JSON);

        return super.handleExceptionInternal(
            exception, problem, headers, HttpStatus.NOT_FOUND, exchange);
    }

    @Override
    protected Mono<ResponseEntity<Object>> handleExceptionInternal(
            Exception exception,
            Object body,
            HttpHeaders headers,
            HttpStatusCode status,
            ServerWebExchange exchange) {

        String id = CorrelationIdFilter.from(exchange);
        ProblemDetail safeBody = ApiProblems.forStatus(status, id);

        HttpHeaders safeHeaders = headers == null
            ? new HttpHeaders()
            : new HttpHeaders(headers);

        safeHeaders.setContentType(MediaType.APPLICATION_PROBLEM_JSON);

        return super.handleExceptionInternal(
            exception, safeBody, safeHeaders, status, exchange);
    }
}
~~~

Override này thay body mặc định của các built-in WebFlux exceptions bằng thông điệp an toàn dựa trên status. Handler nghiệp vụ gọi `super.handleExceptionInternal` với body riêng để giữ `ORDER_NOT_FOUND`. Không có chỗ nào echo `exception.getMessage()`.

### 11.8. SanitizingWebExceptionHandler.java

~~~java
package com.example.errors;

import java.util.List;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMessageWriter;
import org.springframework.http.HttpStatus;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.server.HandlerStrategies;
import org.springframework.web.reactive.function.server.ServerResponse;
import org.springframework.web.reactive.result.view.ViewResolver;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebExceptionHandler;

import reactor.core.publisher.Mono;

@Component
@Order(-2)
public class SanitizingWebExceptionHandler
        implements WebExceptionHandler {

    private static final Logger log =
        LoggerFactory.getLogger(SanitizingWebExceptionHandler.class);

    private static final HandlerStrategies STRATEGIES =
        HandlerStrategies.withDefaults();

    private static final ServerResponse.Context RESPONSE_CONTEXT =
        new ServerResponse.Context() {
            @Override
            public List<HttpMessageWriter<?>> messageWriters() {
                return STRATEGIES.messageWriters();
            }

            @Override
            public List<ViewResolver> viewResolvers() {
                return STRATEGIES.viewResolvers();
            }
        };

    @Override
    public Mono<Void> handle(
            ServerWebExchange exchange, Throwable exception) {

        if (exchange.getResponse().isCommitted()) {
            return Mono.error(exception);
        }

        String id = CorrelationIdFilter.from(exchange);

        HttpStatusCode status =
            exception instanceof ResponseStatusException responseStatus
                ? responseStatus.getStatusCode()
                : HttpStatus.INTERNAL_SERVER_ERROR;

        log.error(
            "web_pipeline_failed correlationId={} exceptionType={}",
            id,
            exception.getClass().getName()
        );

        return ServerResponse.status(status)
            .contentType(MediaType.APPLICATION_PROBLEM_JSON)
            .bodyValue(ApiProblems.forStatus(status, id))
            .flatMap(response ->
                response.writeTo(exchange, RESPONSE_CONTEXT));
    }
}
~~~

Handler này là fallback cho lỗi không được controller advice xử lý, chẳng hạn lỗi từ WebFilter hoặc target WebHandler. Nếu response đã commit, nó phát lại error signal vì không thể thay status/body đã gửi. Log chỉ ghi correlation ID và exception type, không ghi raw message.

### 11.9. DownstreamWebClientConfiguration.java

~~~java
package com.example.errors;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.ClientRequest;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.publisher.Mono;

@Configuration
public class DownstreamWebClientConfiguration {

    @Bean
    WebClient internalWebClient(WebClient.Builder builder) {
        return builder
            .filter((request, next) ->
                Mono.deferContextual(context -> {
                    if (!context.hasKey(
                            CorrelationIdFilter.CONTEXT_KEY)) {
                        return next.exchange(request);
                    }

                    String id = context.get(
                        CorrelationIdFilter.CONTEXT_KEY);

                    ClientRequest forwarded = ClientRequest.from(request)
                        .headers(headers -> headers.set(
                            CorrelationIdFilter.HEADER, id))
                        .build();

                    return next.exchange(forwarded);
                }))
            .build();
    }
}
~~~

Dùng bean này cho destination nội bộ đã được allowlist. Boot cung cấp `WebClient.Builder`; giữ builder auto-configured để không làm mất cấu hình observability/tracing. Không dùng filter này cho mọi third-party host nếu không có chính sách truyền correlation header tới bên ngoài.


## 12. Kiểm thử error contract và việc không rò rỉ secret

Test phải xác nhận những gì client nhìn thấy qua HTTP, không chỉ gọi trực tiếp method controller. Dùng `RANDOM_PORT` để đi qua WebFlux server, filter, dispatch, exception mapping và response writer.

### 12.1. ErrorCorrelationIntegrationTest.java

~~~java
package com.example.errors;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class ErrorCorrelationIntegrationTest {

    private static final HttpClient CLIENT = HttpClient.newHttpClient();

    @Value("${local.server.port}")
    int port;

    private HttpResponse<String> get(String path) throws Exception {
        HttpRequest request = HttpRequest.newBuilder(
                URI.create("http://localhost:" + port + path))
            .GET()
            .build();

        return CLIENT.send(
            request, HttpResponse.BodyHandlers.ofString());
    }

    @Test
    void unexpectedErrorIsSanitizedAndCorrelated() throws Exception {
        HttpResponse<String> response = get("/api/orders/boom");

        assertEquals(500, response.statusCode());

        String correlationId = response.headers()
            .firstValue("X-Correlation-ID")
            .orElseThrow();

        assertTrue(response.headers()
            .firstValue("Content-Type")
            .orElse("")
            .startsWith("application/problem+json"));

        assertTrue(response.body().contains(
            "\"correlationId\":\"" + correlationId + "\""));
        assertTrue(response.body().contains("\"code\":\"INTERNAL_ERROR\""));

        assertFalse(response.body().contains("orders-db.internal"));
        assertFalse(response.body().contains("do-not-return"));
        assertFalse(response.body().contains("IllegalStateException"));
        assertFalse(response.body().contains("password"));
    }

    @Test
    void knownDomainErrorHasSafeStableCode() throws Exception {
        HttpResponse<String> response = get("/api/orders/missing");

        assertEquals(404, response.statusCode());

        String correlationId = response.headers()
            .firstValue("X-Correlation-ID")
            .orElseThrow();

        assertTrue(response.body().contains("\"code\":\"ORDER_NOT_FOUND\""));
        assertTrue(response.body().contains(
            "\"correlationId\":\"" + correlationId + "\""));
        assertFalse(response.body().contains("OrderNotFoundException"));
    }

    @Test
    void everyRequestGetsItsOwnCorrelationId() throws Exception {
        HttpResponse<String> first = get("/api/orders/42");
        HttpResponse<String> second = get("/api/orders/43");

        String firstId = first.headers()
            .firstValue("X-Correlation-ID").orElseThrow();
        String secondId = second.headers()
            .firstValue("X-Correlation-ID").orElseThrow();

        assertNotEquals(firstId, secondId);
    }

    @Test
    void untrustedIncomingCorrelationHeaderIsNotReflected()
            throws Exception {

        HttpRequest request = HttpRequest.newBuilder(
                URI.create("http://localhost:" + port + "/api/orders/42"))
            .header("X-Correlation-ID", "attacker-chosen-id")
            .GET()
            .build();

        HttpResponse<String> response = CLIENT.send(
            request, HttpResponse.BodyHandlers.ofString());

        assertEquals(200, response.statusCode());

        String returnedId = response.headers()
            .firstValue("X-Correlation-ID")
            .orElseThrow();

        assertNotEquals("attacker-chosen-id", returnedId);
    }
}
~~~

Test xác nhận:
- 500 trả `application/problem+json`.
- Correlation ID ở header khớp với property trong ProblemDetail.
- Exception message có database hostname/password không xuất hiện trong public body.
- Lỗi nghiệp vụ 404 có code ổn định.
- Request mới có ID riêng.
- Header client tự gửi không được phản chiếu nguyên văn.

### 12.2. Chạy ứng dụng và test

Yêu cầu JDK 17+ và Maven 3.6.3+:

~~~bash
java -version
mvn -version
mvn test
mvn spring-boot:run
~~~

Thử endpoint thành công:

~~~bash
curl -i http://localhost:8080/api/orders/42
~~~

Thử lỗi nghiệp vụ:

~~~bash
curl -i http://localhost:8080/api/orders/missing
~~~

Thử exception kỹ thuật:

~~~bash
curl -i http://localhost:8080/api/orders/boom
~~~

Response minh họa cho `/api/orders/boom`:

~~~http
HTTP/1.1 500 Internal Server Error
Content-Type: application/problem+json
X-Correlation-ID: 3f6c4b77-8e6d-4f24-8d9c-1a3b2c4d5e6f
~~~

~~~json
{
  "type": "https://api.example.test/problems/internal-error",
  "title": "Internal server error",
  "status": 500,
  "detail": "An unexpected error occurred. Provide the correlation ID to support.",
  "instance": "urn:uuid:3f6c4b77-8e6d-4f24-8d9c-1a3b2c4d5e6f",
  "code": "INTERNAL_ERROR",
  "correlationId": "3f6c4b77-8e6d-4f24-8d9c-1a3b2c4d5e6f"
}
~~~

UUID ở trên chỉ là ví dụ. Giá trị thực được tạo mới cho mỗi request. Database host/password từ exception message không xuất hiện trong body.

## 13. Micrometer Tracing: khi cần nối nhiều service

Custom correlation ID hữu ích cho một request hoặc workflow, nhưng nếu cần quan sát distributed call graph, dùng tracing thay vì tự tạo một hệ thống trace bằng header tùy ý.

Spring Boot hỗ trợ Micrometer Tracing với các tracer như OpenTelemetry hoặc Brave. Khi tracing hoạt động:
- Trace ID nối các span trong cùng distributed trace.
- Span ID nhận diện từng operation/span.
- Correlation ID trong log mặc định được tạo từ trace ID và span ID.
- Các client builder được auto-configure có thể tự propagate trace context.
- Context propagation giúp trace/span liên kết đúng qua reactive execution.

Một log pattern tùy chỉnh có thể là:

~~~properties
logging.pattern.correlation=[${spring.application.name:},%X{traceId:-},%X{spanId:-}]
logging.include-application-name=false
~~~

Boot dùng dấu cách cuối pattern để tách correlation prefix khỏi tên logger trong output. Nếu thay format, kiểm tra key MDC mà tracer đang dùng.

**Phân biệt hai ID:**
- `X-Correlation-ID` trong ví dụ là ID do application tạo và trả cho client.
- `traceId` là ID của distributed trace do tracing system quản lý.
- `spanId` thay đổi theo operation/span.
- Không ghi đè `traceparent` bằng custom correlation ID.
- Không bắt client gửi trace ID tùy ý rồi tin nó là trace hợp lệ; tracing library phải parse/validate theo W3C Trace Context.

Khi dùng `WebClient`, ưu tiên builder do Spring Boot cung cấp để trace propagation được kích hoạt. Nếu tạo client bằng builder độc lập hoặc `WebClient.create()` không qua auto-configuration, trace propagation có thể không hoạt động như mong muốn.

### 13.1. Reactor Context và MDC

Reactor Context là nơi phù hợp cho custom request metadata trong pipeline reactive. MDC dựa trên ThreadLocal nên cần context propagation integration nếu muốn log pattern đọc giá trị từ MDC qua thread switch.

Không:
- Set MDC ở đầu request rồi giả định callback luôn chạy trên cùng thread.
- Clear MDC ở một `doFinally` bất kỳ mà không hiểu scope của thread.
- Dùng `ThreadLocal` để thay Reactor Context.
- Gắn raw user object, request body hoặc credential vào Reactor Context.

Có thể dùng Micrometer Context Propagation hoặc cơ chế tích hợp được hỗ trợ bởi Spring Boot/Reactor để bridge context khi thật sự cần MDC. Với custom ID, log field tường minh từ `deferContextual` thường dễ kiểm soát hơn.

## 14. WebClient error handling: không chuyển tiếp lỗi thô từ service khác

Một downstream service có thể trả body chứa hostname, stack trace, SQL, token hoặc thông tin nội bộ. Đừng trả nguyên `WebClientResponseException.getResponseBodyAsString()` cho client hiện tại.

~~~java
WebClient client = internalWebClient;

Mono<Inventory> inventory =
    client.get()
        .uri("/api/inventory/{id}", itemId)
        .retrieve()
        .onStatus(
            status -> status.isError(),
            response -> response.releaseBody()
                .thenReturn(new InventoryUnavailableException())
        )
        .bodyToMono(Inventory.class);
~~~

Đây là fragment minh họa. `InventoryUnavailableException` là exception nghiệp vụ/kỹ thuật nội bộ do ứng dụng định nghĩa; error mapper của API hiện tại sẽ biến nó thành `DEPENDENCY_UNAVAILABLE` hoặc `INTERNAL_ERROR` với detail an toàn. Nếu cần ghi downstream status, chỉ ghi status và destination service đã allowlist; không log raw body hoặc toàn bộ headers.

Đối với retry:
- Chỉ retry lỗi transient và operation idempotent hoặc có idempotency key.
- Giữ correlation ID xuyên các lần retry của cùng request.
- Ghi retry count dưới dạng field riêng, không tạo ID mới mỗi lần.
- Có timeout và giới hạn retry; không biến một lỗi downstream thành vòng retry vô hạn.

## 15. Response đã commit: không thể thay bằng ProblemDetail mới

Khi response chưa commit, exception handler có thể chọn status và ghi ProblemDetail. Khi header/body đã được gửi, server không thể quay lại thay 200 thành 500 hoặc ghi một JSON lỗi mới từ đầu.

Điều này thường gặp với:
- `Flux<T>` streaming.
- Server-Sent Events.
- NDJSON.
- File download.
- Response body ghi trực tiếp qua `ServerHttpResponse`.

Khi lỗi xuất hiện sau commit:
1. Giữ correlation ID trong log/event nội bộ.
2. Ghi nhận stream kết thúc bất thường và exception category.
3. Kết thúc connection/Publisher theo contract.
4. Nếu protocol hỗ trợ error event, phát một event an toàn theo schema riêng.
5. Không cố ghi thêm một ProblemDetail JSON vào giữa NDJSON/SSE stream.

Với SSE, có thể định nghĩa event `error` có `code` và `correlationId` nếu client contract cho phép. Không gửi exception message hoặc stack trace trong event.

## 16. Bảo mật và vận hành trong production

### 16.1. Kiểm soát correlation ID đầu vào

Nếu một gateway tin cậy cấp ID:
- Xác thực gateway bằng network boundary, mTLS hoặc cơ chế service identity.
- Chỉ nhận header từ gateway đã xác thực.
- Validate charset/length, ví dụ `[A-Za-z0-9._-]{1,64}`.
- Loại CR/LF, control characters và giá trị quá dài.
- Không sử dụng ID như authorization token.
- Không đưa raw ID vào SQL hoặc câu log không được escape.

Nếu không có trust boundary rõ ràng, tạo ID mới ở service. Có thể lưu inbound ID đã kiểm tra ở field riêng nếu cần audit, nhưng không cho phép nó ghi đè ID nội bộ.

### 16.2. Giới hạn nơi xuất hiện ID

Correlation ID không phải bí mật xác thực, nhưng vẫn có thể liên kết hoạt động của một người dùng. Chỉ đưa nó tới:
- Response header và error body của request đó.
- Log/trace backend nội bộ.
- Service nội bộ được phép nhận metadata tương quan.
- Support tooling có authorization.

Không đưa ID vào URL, query string, analytics công khai hoặc log của bên thứ ba không liên quan. Không dùng correlation ID làm metric tag vì mỗi request có thể tạo một giá trị mới, khiến cardinality tăng rất lớn.

### 16.3. Quyền truy cập và retention của log

- Giới hạn ai có thể xem stack trace và diagnostic payload.
- Tách log vận hành khỏi audit log nếu retention/access policy khác nhau.
- Mã hóa log khi truyền và khi lưu theo chính sách tổ chức.
- Có retention và disposal rõ ràng.
- Theo dõi ai truy cập hoặc export log chứa dữ liệu nhạy cảm.
- Kiểm tra cả log app, proxy, gateway, APM, tracing backend và crash report.
- Định kỳ quét log test/staging để phát hiện secret bị ghi nhầm.

### 16.4. Error code và status phải ổn định

Không dùng câu chữ `detail` làm contract máy đọc. Dùng mã như:
- `ORDER_NOT_FOUND`
- `INVALID_REQUEST`
- `UNAUTHENTICATED`
- `FORBIDDEN`
- `DEPENDENCY_UNAVAILABLE`
- `INTERNAL_ERROR`

Client có thể dịch message hoặc hiển thị UX theo error code. Khi câu chữ thay đổi hoặc được quốc tế hóa, logic client vẫn giữ nguyên.

## 17. Lỗi thường gặp và cách sửa

| Sai lầm | Hậu quả | Cách làm đúng |
| --- | --- | --- |
| Trả `exception.getMessage()` | Lộ SQL, hostname, token hoặc input | Map exception sang ProblemDetail an toàn |
| Serialize toàn bộ `Throwable` | Lộ stack trace/cause/class nội bộ | Chỉ trả status, stable code, safe detail và ID |
| Log toàn bộ request/response | Credential, cookie và PII đi vào log | Allowlist field, không log body/header toàn bộ |
| Chỉ mask token bằng `****` trong response | Một phần secret vẫn có thể nhạy cảm | Loại bỏ hoàn toàn khỏi public error |
| Tạo correlation ID trong từng service method | ID không khớp giữa các lớp | Tạo ở request boundary, truyền qua context |
| Tạo ID mới khi retry | Không nối được một request qua các lần thử | Giữ ID cũ, thêm retry count |
| Tin `X-Correlation-ID` bất kỳ từ client | Log forging, ID spoofing và header injection | Sinh mới hoặc chỉ tin gateway xác thực + validate |
| Dùng correlation ID làm trace ID | Sai semantics, làm hỏng trace propagation | Tách app correlation ID với W3C trace/span |
| Dùng ThreadLocal/MDC trực tiếp trong reactive | Mất context khi thread switch hoặc rò sang request khác | Reactor Context và Micrometer Context Propagation |
| `@ControllerAdvice` được kỳ vọng bắt mọi filter error | Lỗi ngoài controller không có error contract thống nhất | Thêm WebExceptionHandler cho WebHandler chain |
| WebExceptionHandler ghi body sau commit | Response hỏng hoặc ghi lỗi lần hai | Kiểm tra `isCommitted()` và kết thúc stream an toàn |
| Forward raw downstream error body | Lộ topology và thông tin service phụ thuộc | Map sang error code của API hiện tại |
| Đưa correlation ID vào metric label | Cardinality cao, tăng chi phí metric | Để ID trong log/trace; metric dùng low-cardinality tags |
| Log raw URL path/query | Có thể chứa email, token, account ID | Log route template và trường allowlist |
| Bật stacktrace công khai khi debug | Rò rỉ implementation và secret | Dùng diagnostic log nội bộ được bảo vệ |

## 18. Quy trình debug khi client báo lỗi

1. Lấy `X-Correlation-ID` từ response header hoặc `correlationId` trong ProblemDetail.
2. Tìm log theo ID ở service nhận request.
3. Xác định route template, method, status, error code và thời điểm.
4. Tìm trace ID/span ID liên quan nếu Micrometer Tracing được bật.
5. Theo trace qua các service và xác định span đầu tiên thất bại.
6. Kiểm tra exception type và diagnostic record nội bộ đã được làm sạch.
7. Nếu lỗi từ downstream, kiểm tra status/duration/retry count của service đó.
8. Xác nhận response đã commit hay chưa để hiểu vì sao error body có thể không thay đổi.
9. Sau khi xử lý, kiểm tra client nhận đúng status/error code và correlation ID vẫn khớp.

Không yêu cầu người dùng gửi password, cookie, Authorization header hoặc raw request body qua ticket support. Correlation ID đủ để tìm request trong hệ thống có kiểm soát.

## 19. Checklist production

- [ ] Error response dùng RFC 9457 `ProblemDetail` hoặc contract lỗi tương đương.
- [ ] Mỗi loại lỗi có status và stable error code.
- [ ] `detail` được tạo từ message đã duyệt, không lấy trực tiếp `Throwable.getMessage()`.
- [ ] Không có stack trace, SQL, connection string, hostname hoặc secret trong response.
- [ ] `instance` không echo path/query có thể chứa PII hoặc token.
- [ ] Correlation ID được tạo ở boundary và giữ nguyên qua response header/body/log.
- [ ] Correlation ID không được dùng làm credential hoặc metric label.
- [ ] Header client gửi chỉ được tin qua gateway đã xác thực và sau validation.
- [ ] Reactor Context được dùng cho custom metadata trong reactive pipeline.
- [ ] MDC/ThreadLocal chỉ dùng khi context propagation được cấu hình đúng.
- [ ] WebClient truyền trace context bằng builder auto-configured và custom ID chỉ tới service nội bộ cần thiết.
- [ ] `@RestControllerAdvice` xử lý lỗi controller; `WebExceptionHandler` xử lý lỗi WebHandler chain.
- [ ] WebExceptionHandler kiểm tra response committed trước khi ghi.
- [ ] Log có allowlist; không log raw credentials, cookies, bodies hoặc exception messages chưa được làm sạch.
- [ ] Test chứng minh secret không xuất hiện trong response/log.
- [ ] Test xác nhận correlation ID trong header khớp với body và log.
- [ ] CORS expose correlation header nếu browser client cần đọc.
- [ ] Error từ downstream được map về contract của service hiện tại.
- [ ] Có quy trình support tra cứu theo correlation ID và quyền truy cập log phù hợp.

## 20. Bài tập thực hành

**Bài 1 – Sanitized 500.** Tạo controller phát `IllegalStateException` với message chứa database host và password giả. Trả 500 ProblemDetail; viết test khẳng định body không chứa các chuỗi đó.

**Bài 2 – Domain error.** Tạo `OrderNotFoundException`, map thành 404 và `ORDER_NOT_FOUND`. Xác nhận message không phụ thuộc exception constructor.

**Bài 3 – Correlation filter.** Gắn UUID vào exchange attribute, response header và Reactor Context. Viết test xác nhận ID ở header và body giống nhau.

**Bài 4 – Header spoofing.** Gửi request với `X-Correlation-ID` tự chọn. Xác nhận service tạo ID mới; sau đó thiết kế trust boundary nếu gateway cần truyền ID.

**Bài 5 – Reactor Context.** Dùng `Mono.deferContextual` đọc ID trong service sau `contextWrite`. Thêm `publishOn` và xác nhận context vẫn theo subscription.

**Bài 6 – WebClient propagation.** Dùng mock `ExchangeFunction` để kiểm tra filter thêm `X-Correlation-ID` từ Reactor Context vào request outbound.

**Bài 7 – Built-in exception.** Gửi Content-Type không hỗ trợ hoặc JSON malformed. Override `handleExceptionInternal`; kiểm tra response không echo parser message hoặc rejected body.

**Bài 8 – Filter-level exception.** Tạo một WebFilter phát error trước controller. Xác nhận `WebExceptionHandler` trả ProblemDetail và giữ cùng correlation ID.

**Bài 9 – Response đã commit.** Tạo `Flux` phát vài phần tử rồi error. Kiểm tra response không bị ghi thêm JSON ProblemDetail giữa stream; ghi lỗi nội bộ với correlation ID.

**Bài 10 – Log redaction.** Tạo test capture log và gửi Authorization/cookie/password giả. Xác nhận output chỉ có allowlisted fields và correlation ID.

## 21. Tài liệu tham khảo chính thức

1. Spring Framework – Error Responses và ProblemDetail trong WebFlux: https://docs.spring.io/spring-framework/reference/web/webflux/ann-rest-exceptions.html
2. Spring Framework – Reactive Core, WebFilter và WebExceptionHandler: https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html
3. Spring Framework Javadoc – `ResponseEntityExceptionHandler`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/result/method/annotation/ResponseEntityExceptionHandler.html
4. Spring Framework Javadoc – `WebFilter`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/server/WebFilter.html
5. Spring Framework Javadoc – `WebExceptionHandler`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/server/WebExceptionHandler.html
6. Spring Framework – WebClient filters: https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-filter.html
7. Spring Framework – WebClient Context: https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-context.html
8. Reactor Core – Adding a Context to a Reactive Sequence: https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html
9. Spring Boot 4.1 – Tracing và Logging Correlation IDs: https://docs.spring.io/spring-boot/4.1/reference/actuator/tracing.html
10. Spring Boot – System Requirements: https://docs.spring.io/spring-boot/system-requirements.html
11. OWASP – Logging Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html

**Tự đánh giá cuối:** Nếu database exception chứa password, client nên nhận gì? Correlation ID phải xuất hiện ở những nơi nào để support tra được request? Vì sao `@RestControllerAdvice` không thay thế `WebExceptionHandler` cho lỗi filter? Vì sao Reactor Context an toàn hơn ThreadLocal trong pipeline reactive? Khi test được cả response body, header, log và downstream propagation, bạn đã có một error contract vừa an toàn vừa có thể vận hành.
