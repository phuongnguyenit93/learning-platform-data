# Thiết kế phản hồi lỗi JSON nhất quán và mã tương quan

**Module:** Spring Security – reactive (Spring WebFlux)  
**Phần:** Phản hồi lỗi  
**Mục tiêu:** Thiết kế một hợp đồng lỗi JSON chung cho `401`/`403` từ Spring Security và `400`/`404`/`500` từ WebFlux; gắn **correlation ID riêng cho từng HTTP request**; bảo toàn HTTP headers quan trọng; không để rò rỉ mật khẩu, stack trace hoặc dữ liệu nhạy cảm; kiểm thử hành vi bằng Java 17+, Spring Boot, `curl` và `WebTestClient`.

Trong API có xác thực, cùng một thao tác có thể thất bại ở nhiều tầng. Request không có credential bị chặn bởi Spring Security **trước controller**; người đã đăng nhập nhưng thiếu role thường nhận `403`; tham số sai, không tìm thấy resource hoặc lỗi nội bộ lại có thể xuất phát từ WebFlux/handler. Nếu mỗi tầng trả một dạng khác nhau — lúc HTML, lúc chuỗi trống, lúc JSON chứa message nội bộ — client khó xử lý ổn định và nhóm vận hành khó đối chiếu request lỗi với log.

Thiết kế phù hợp giải quyết **hai vấn đề độc lập nhưng phối hợp**:

1. **Hợp đồng lỗi JSON nhất quán:** mỗi phản hồi lỗi có HTTP status phù hợp, body cấu trúc ổn định, error code dành cho máy, thông điệp công khai an toàn, path của request, và tùy chọn timestamp.
2. **Mã tương quan (correlation ID):** một identifier do server quản lý cho từng request, xuất hiện ở header và body JSON, đồng thời được ghi vào log/trace metadata. Khi client báo `correlationId=...`, người vận hành tìm được request đó mà không cần biết password/token của user.

**Điểm mấu chốt:** Correlation ID **không phải authentication token**, không cấp quyền, không chứng minh danh tính; còn status `401` và `403` **không thể dùng thay thế lẫn nhau** chỉ để JSON trông giống nhau.

## 1. Hợp đồng dữ liệu: nhất quán nhưng vẫn đúng HTTP

Nên dùng dạng Problem Details của **RFC 9457** với media type `application/problem+json`. Năm trường tiêu chuẩn là `type`, `title`, `status`, `detail` và `instance`; ứng dụng có thể bổ sung extension fields như `code`, `correlationId`, `timestamp`.

Ví dụ một người đã đăng nhập nhưng không có quyền xem admin:

```http
HTTP/1.1 403 Forbidden
Content-Type: application/problem+json
Cache-Control: no-store
X-Correlation-Id: 8d9cc0a5-4e2f-49ba-9b01-4e120a13516a

{
  "type": "about:blank",
  "title": "Forbidden",
  "status": 403,
  "detail": "You do not have permission to access this resource.",
  "instance": "/api/admin",
  "code": "ACCESS_DENIED",
  "correlationId": "8d9cc0a5-4e2f-49ba-9b01-4e120a13516a",
  "timestamp": "2026-11-07T06:00:00Z"
}
```

Đây là **mẫu giao thức minh họa**: ID/timestamp khác nhau ở mỗi lần chạy. Trường `status` trong JSON phải phản ánh mã HTTP thực. `type="about:blank"` chấp nhận khi không định nghĩa một URI tài liệu lỗi riêng; khi dùng loại riêng, ví dụ `https://api.example.test/problems/access-denied`, cần quản lý tài liệu và version tương ứng. `instance` có thể là đường dẫn của request, không nên chứa raw query token.

**Nguyên tắc đặt trường:**

| Trường | Dành cho | Điều cần tránh |
| --- | --- | --- |
| `type` | Loại vấn đề theo RFC 9457 | Thay đổi URI/type tùy text exception |
| `title` | Tiêu đề ổn định, ngắn, theo status | Đổ nguyên stack trace vào title |
| `status` | HTTP status trong body để client/observability đọc | Để body ghi 200 trong HTTP 500 |
| `detail` | Mô tả an toàn cho client, có thể dịch theo ngôn ngữ | Password, SQL, tên class nội bộ, path trên server |
| `instance` | URI reference của request, thường chỉ path | Full URL có token trong query hoặc dữ liệu nhạy cảm |
| `code` | Mã nghiệp vụ/ứng dụng ổn định, ví dụ `AUTHENTICATION_REQUIRED` | Dùng câu tiếng Anh có thể thay đổi làm code |
| `correlationId` | Đối chiếu lỗi với request/log | Dùng làm credential hoặc id định danh người dùng |
| `timestamp` | Thời điểm tạo error response, ISO-8601 UTC | Tưởng timestamp là bằng chứng thứ tự tuyệt đối trong hệ phân tán |

Không phải mọi lỗi đều cần `detail` riêng. Với `401`/`403`, dùng thông điệp đủ chung để không tiết lộ liệu username có tồn tại, tên role bí mật, hoặc resource của người khác có thực hay không.

### 1.1. Status khác nhau có ý nghĩa khác nhau

| HTTP status | Trường hợp | `code` đề xuất | Lưu ý |
| --- | --- | --- | --- |
| `400 Bad Request` | Tham số cú pháp/giá trị sai | `INVALID_REQUEST` | Không trả toàn bộ input nhạy cảm |
| `401 Unauthorized` | Thiếu/không hợp lệ authentication | `AUTHENTICATION_REQUIRED` | Với HTTP Basic phải giữ `WWW-Authenticate` challenge |
| `403 Forbidden` | Đã xác thực nhưng không được phép | `ACCESS_DENIED` | Không tự cấp role/đổi policy chỉ để test pass |
| `404 Not Found` | Route/tài nguyên không tồn tại hoặc chủ động che giấu resource theo policy | `NOT_FOUND` | Không lộ dữ liệu của người khác trong detail |
| `405 Method Not Allowed` | URL có nhưng HTTP method không được hỗ trợ | `METHOD_NOT_ALLOWED` | Giữ header `Allow` nếu framework cung cấp |
| `409 Conflict` | Xung đột trạng thái/version | `CONFLICT` | Giúp client quyết định retry có điều kiện |
| `422 Unprocessable Content` | Nội dung hợp cú pháp nhưng không thỏa domain rule khi ứng dụng chọn status này | `VALIDATION_FAILED` | Cần policy nhất quán với 400 |
| `429 Too Many Requests` | Rate limit | `RATE_LIMITED` | Có thể cần `Retry-After`/RateLimit headers |
| `500 Internal Server Error` | Lỗi không mong đợi phía server | `INTERNAL_ERROR` | Trả thông điệp chung, log riêng nguyên nhân an toàn |
| `503 Service Unavailable` | Phụ thuộc quan trọng không hoạt động / bảo trì | `SERVICE_UNAVAILABLE` | `Retry-After` nếu có ý nghĩa |

**Không ép mọi lỗi thành HTTP 200 + JSON `{"status": 401}`.** Proxy, browser, client SDK và monitoring đọc HTTP status thực. Cũng không nên biến mọi lỗi thành 500; lỗi sai request, thiếu quyền, resource không tồn tại có semantics khác nhau.

## 2. Hai đường lỗi khác nhau trong Spring WebFlux

Một API có thể nhận lỗi ở **tầng bảo mật** hoặc ở **tầng ứng dụng**:

```text
HTTP request
      |
      v
CorrelationWebFilter (gắn ID và response header ngay đầu request)
      |
      v
Spring Security WebFilters
      |
      +-- thiếu/sai credential
      |      -> ServerAuthenticationEntryPoint
      |         HTTP 401 + WWW-Authenticate + JSON
      |
      +-- đã authenticated, thiếu role
      |      -> ServerAccessDeniedHandler
      |         HTTP 403 + JSON
      |
      +-- pass security
             |
             v
         Spring WebFlux Handler/Controller
             |
             +-- input sai, resource missing
             |      -> ResponseStatusException / WebFlux error handling
             |         HTTP 400/404 + JSON
             |
             +-- unexpected exception
             |      -> ErrorWebExceptionHandler
             |         HTTP 500 + JSON, no stack trace
             |
             +-- success
                    HTTP 200 + X-Correlation-Id
```

### 2.1. Vì sao `@RestControllerAdvice` một mình chưa đủ?

`@ExceptionHandler`/`@RestControllerAdvice` hữu ích cho lỗi xảy ra **trong xử lý controller** (validation/domain exceptions). Nhưng nhiều lỗi `401/403` phát sinh từ `AuthenticationWebFilter` hoặc `ExceptionTranslationWebFilter` **trước khi controller chạy**, nên một `@RestControllerAdvice` thông thường không đảm bảo bắt được chúng.

Với WebFlux/Spring Security hãy cấu hình:

- `ServerAuthenticationEntryPoint` cho lỗi **cần xác thực** — bao gồm request không có credential, và entry point của cơ chế Basic khi credential không hợp lệ.
- `ServerAccessDeniedHandler` cho trường hợp **đã xác thực nhưng bị từ chối quyền**.
- `ErrorWebExceptionHandler` hoặc cơ chế Problem Details/`ErrorAttributes` của Spring Boot để chuẩn hóa lỗi **WebFlux ngoài Security**, gồm mapping không có route hoặc exception không được controller xử lý.
- Một **writer chung** cho content type/body/headers để mọi đường sinh cùng contract; không tự copy JSON string theo từng filter.

Cần test toàn bộ đường **HTTP thật**, không chỉ unit test controller; cấu hình một nhánh nhưng bỏ nhánh còn lại có thể khiến 401 đôi lúc JSON, đôi lúc trống/HTML.

### 2.2. HTTP Basic có hai nguồn 401

Với HTTP Basic, `httpBasic(...)` tự tạo authentication filter và có xử lý **authentication failure** khi password sai. Để nhất quán, cấu hình cùng một `ServerAuthenticationEntryPoint` ở cả:

1. `exceptionHandling(ex -> ex.authenticationEntryPoint(...))`: trường hợp request đi tới endpoint cần login mà chưa có authentication hợp lệ.
2. `httpBasic(basic -> basic.authenticationEntryPoint(...))`: trường hợp converter/manager Basic nhận credential nhưng authentication **thất bại**.

API `ServerHttpSecurity.HttpBasicSpec.authenticationEntryPoint` hỗ trợ cấu hình thứ hai. Nếu chỉ cài entry point cho `exceptionHandling`, một số lỗi password sai có thể đi theo failure handler của Basic và trả định dạng khác. Đây là điểm rất dễ bỏ sót.

Đối với HTTP Basic **phải giữ** header `WWW-Authenticate: Basic realm="..."` ở status 401. JSON là **body bổ sung**, không được làm mất yêu cầu challenge của giao thức. Với bearer token/OAuth2 Resource Server, challenge thường dùng `WWW-Authenticate: Bearer ...` theo RFC 6750; không copy nguyên header Basic sang Bearer.

### 2.3. Vì sao phản hồi lỗi nên có Cache-Control?

Phản hồi `401/403` có thể chứa đường resource hoặc metadata. Thiết lập `Cache-Control: no-store` theo policy giúp tránh lưu phản hồi lỗi nhạy cảm ở cache trung gian hoặc browser; tuy nhiên phải kiểm thêm cache của proxy/CDN và không dùng nó thay cho kiểm soát quyền. Khi xử lý `429`/`503`, có thể cung cấp `Retry-After` với semantics thực, không gắn một thời gian tùy ý.

## 3. Mã tương quan: yêu cầu, hợp đồng và vòng đời

**Correlation ID** thường là chuỗi không mang bí mật (ví dụ UUID v4) để nối toàn bộ log và response **của một HTTP request**. Với một request vào API:

- Server tạo hoặc xác thực/chấp nhận ID **theo chính sách trust boundary**.
- Gắn ID vào `ServerWebExchange.getAttributes()` để các WebFilter/handler cùng request đọc dễ dàng.
- Có thể đưa vào Reactor `Context` để các operator/WebClient downstream truy cập khi subscribe.
- Trả cho client qua header `X-Correlation-Id` và field `correlationId` của JSON lỗi; response thành công có thể chỉ cần header.
- Ghi cùng ID ở access log/structured log, bên cạnh status, route template hoặc operation name đã được khử nhạy cảm.
- Nếu gọi downstream service, cân nhắc truyền ID bằng header nội bộ theo hợp đồng, hoặc tận dụng trace context của hệ quan sát.

### 3.1. Không tin mù quáng `X-Correlation-Id` từ Internet

Một client có thể gửi:

```http
X-Correlation-Id: alice-admin-superuser
```

Đây **không** là bằng chứng người đó là Alice hoặc admin. Nếu server phản chiếu nguyên giá trị vào log/header, kẻ tấn công có thể tạo ID quá dài, trùng ID người khác, chứa ký tự điều khiển hoặc gây log injection (HTTP library thường chặn CRLF nhưng không nên chỉ dựa vào điều đó). Chính sách demo **luôn phát UUID mới tại server** và bỏ qua giá trị client gửi.

Trong hệ thống có API Gateway/tracing được tin cậy, có thể **chấp nhận incoming correlation ID** nếu gateway đã xác thực/giới hạn độ dài, định dạng, character set, uniqueness policy và stripping header không tin cậy. Tách rõ `requestId` của hop hiện tại, `correlationId` của luồng nghiệp vụ và `traceId` của distributed tracing.

### 3.2. Phân biệt correlation ID, trace ID, span ID và principal

| Mã | Mục đích | Nên lấy từ đâu? | Không nên dùng làm |
| --- | --- | --- | --- |
| `correlationId` | Liên hệ request/luồng với lỗi/incident | Server/gateway tin cậy, chính sách định dạng rõ | Authentication hay authorization token |
| `traceId` | Nối nhiều span qua các dịch vụ | OpenTelemetry/W3C Trace Context instrumentation | Thông tin nhạy cảm hoặc chứng cứ user |
| `spanId` | Định danh một đoạn công việc trong trace | Tracing SDK/instrumentation | Trường ổn định qua nhiều request |
| `userId` / `sub` | Chủ thể đã xác thực | Spring Security `Authentication`/token đã xác minh | Thay correlation ID cho client hỗ trợ |
| `sessionId` | Cookie/server session | Session infrastructure | Giá trị public trong error JSON/log |
| `access token` / `password` | Credential | Nguồn xác thực được bảo vệ | Nội dung log, response detail hoặc correlation ID |

**W3C `traceparent` không giống `X-Correlation-Id`.** Nếu tổ chức đã có Micrometer Tracing/OpenTelemetry, có thể đưa `traceId` vào log và error response theo policy, thay vì phát minh một hệ thống thứ hai. Không viết đè trace context được instrumentation quản lý; xác nhận `traceparent` từ client theo trust policy.

### 3.3. Reactor Context khác ThreadLocal MDC

WebFlux có thể xử lý nhiều request xen kẽ trên cùng event-loop thread; `ThreadLocal`/MDC tự quản lý không bảo đảm mỗi callback luôn mang đúng ID. Nếu cần log từ operator async, dùng Reactor Context/Micrometer Context Propagation với integration chính thức, hoặc truyền ID dưới dạng biến local/parameter rõ ràng. Không làm:

```java
static String currentCorrelationId; // SAI: dùng chung mọi request
```

Cũng không chỉ gọi `MDC.put("cid", id)` lúc request vào rồi hi vọng mọi `flatMap`/`publishOn` sẽ chạy đúng thread. Nếu dùng context propagation, phải có accessor/cleanup và test nhiều request đồng thời. Demo bên dưới log trực tiếp biến ID được capture, không phụ thuộc MDC.

## 4. Kiến trúc đề xuất của ứng dụng mẫu

Ta sẽ viết một project Spring Boot WebFlux có:

- `CorrelationWebFilter`: tạo UUID mỗi request, lưu attribute + Reactor Context, gắn header cho cả response thành công/lỗi, log status cùng ID.
- `ApiProblem`: Java record chứa 5 trường chuẩn RFC 9457 và các extension `code`, `correlationId`, `timestamp`.
- `ApiProblemWriter`: **một chỗ duy nhất** serialize JSON với Jackson, đặt HTTP status, content type, no-store và header thích hợp.
- `SecurityConfig`: dùng entry point cho **cả** `httpBasic` và `exceptionHandling`, plus access-denied handler.
- `ApiErrorWebExceptionHandler`: bắt lỗi chưa xử lý từ WebFlux với `@Order(-2)`, mã hóa `400/404/500` bằng contract chung. Trường hợp response đã committed thì không cố ghi JSON lần hai.
- `ApiController`: vài endpoints để sinh đủ tình huống.
- `ApiErrorTests`: `WebTestClient` qua server thật, assert **HTTP status + media type + header + JSON fields + không lộ lỗi nội bộ + ID tách biệt mỗi request**.

### Ma trận endpoint demo

| Endpoint | Authentication | Behavior |
| --- | --- | --- |
| `GET /public/ping` | Public | `200 pong` + `X-Correlation-Id` |
| `GET /api/me` | Bắt buộc | `200 hello:alice` nếu Alice đúng password |
| `GET /api/admin` | `ROLE_ADMIN` | Alice đúng password vẫn `403` |
| `GET /api/parse?n=-1` | Bắt buộc | Ném `ResponseStatusException(BAD_REQUEST)`, thành `400` JSON |
| `GET /api/fail` | Bắt buộc | Lỗi chủ động mô phỏng, thành `500` JSON an toàn |
| `GET /api/not-here` | Bắt buộc | Không có mapping, thành `404` JSON nếu đã authenticated |
| `GET /api/me` không Basic/sai Basic | Bị từ chối | `401` JSON + Basic challenge |

Tài khoản chỉ dùng cho **localhost**: `alice / alice123` (role USER) và `admin / admin123` (role ADMIN). Password được hash bằng `PasswordEncoder`, không lưu `{noop}`.

## 5. Ứng dụng Spring Boot WebFlux Java 17+ hoàn chỉnh

Dùng **JDK 17+**, Maven và **Spring Boot 3.5.7** làm mốc ví dụ; khi triển khai production phải chọn phiên bản được hỗ trợ và bản vá theo chính sách bảo mật. Không thêm Spring MVC starter vào project WebFlux.

### 5.1. Cấu trúc

```text
reactive-json-errors/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/errors/
    │   │   ├── ErrorApiApplication.java
    │   │   ├── CorrelationWebFilter.java
    │   │   ├── ApiProblem.java
    │   │   ├── ApiProblemWriter.java
    │   │   ├── SecurityConfig.java
    │   │   ├── ApiController.java
    │   │   └── ApiErrorWebExceptionHandler.java
    │   └── resources/application.properties
    └── test/java/demo/errors/
        └── ApiErrorTests.java
```

`pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>reactive-json-errors</artifactId>
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
            <artifactId>spring-boot-starter-security</artifactId>
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

Spring Boot WebFlux starter cung cấp Jackson cùng JSON integration dùng trong ví dụ. Với Java 17, `record` được hỗ trợ trực tiếp. Trong một dependency graph thật cần kiểm tra Jackson/Boot BOM để không có phiên bản tự override gây xung đột.

`src/main/resources/application.properties`:

```properties
spring.application.name=reactive-json-errors
server.port=8080
```

### 5.2. Application class

`src/main/java/demo/errors/ErrorApiApplication.java`:

```java
package demo.errors;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ErrorApiApplication {
    public static void main(String[] args) {
        SpringApplication.run(ErrorApiApplication.class, args);
    }
}
```

### 5.3. CorrelationWebFilter: phát ID cho từng request

`src/main/java/demo/errors/CorrelationWebFilter.java`:

```java
package demo.errors;

import java.util.UUID;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;

import reactor.core.publisher.Mono;

@Component
@Order(Ordered.HIGHEST_PRECEDENCE)
public class CorrelationWebFilter implements WebFilter {
    static final String ATTRIBUTE_KEY = "demo.correlationId";
    static final String CONTEXT_KEY = "demo.correlationId";
    static final String HEADER = "X-Correlation-Id";

    private static final Logger log =
        LoggerFactory.getLogger(CorrelationWebFilter.class);

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange, WebFilterChain chain) {

        // Demo chỉ tin ID do server tạo; không sao chép header từ client.
        String id = UUID.randomUUID().toString();
        exchange.getAttributes().put(ATTRIBUTE_KEY, id);
        exchange.getResponse().getHeaders().set(HEADER, id);

        return chain.filter(exchange)
            .contextWrite(context -> context.put(CONTEXT_KEY, id))
            .doFinally(signal -> log.info(
                "request-finished status={} correlationId={}",
                exchange.getResponse().getStatusCode(), id));
    }

    static String id(ServerWebExchange exchange) {
        return exchange.getAttributeOrDefault(
            ATTRIBUTE_KEY, "unavailable");
    }
}
```

**Quan sát:**

- `@Order(Ordered.HIGHEST_PRECEDENCE)` đưa filter vào rất sớm trong pipeline WebFlux, trước việc kiểm tra Basic/authorization thông thường, nên cả 401/403 có ID. Nếu có gateway/filter khác ở ngoài ứng dụng, chúng có vòng đời và thứ tự riêng; không hứa mọi lỗi xảy ra trước khi WebFlux handler bắt đầu đều có cùng ID.
- `exchange.getAttributes()` thuộc **request cụ thể**, không phải mutable field singleton. `contextWrite` giúp operator Reactor downstream đọc ID khi subscription có Context; request A và B không dùng chung ID.
- Logger ghi status và correlation ID, **không** ghi password, header `Authorization`, raw query, body hoặc `SecurityContext`. Dữ liệu log đầy đủ của observability stack cần policy riêng.
- `doFinally` chạy khi pipeline kết thúc, bao gồm complete/error/cancel; status code có thể null nếu response chưa được chốt khi lỗi xảy ra rất sớm. Đây là log kỹ thuật, không phải success log tuyệt đối.
- Giá trị `unavailable` là fallback phòng vệ trong code demo khi một handler chạy ngoài luồng filter. `ApiProblemWriter` phía dưới vẫn tạo UUID mới nếu thiếu ID để response không bị thiếu correlation.

### 5.4. ApiProblem: schema JSON ổn định

`src/main/java/demo/errors/ApiProblem.java`:

```java
package demo.errors;

public record ApiProblem(
    String type,
    String title,
    int status,
    String detail,
    String instance,
    String code,
    String correlationId,
    String timestamp
) {}
```

Record chỉ là mô hình dữ liệu, không chứa secret hay `Throwable`. Jackson serialize các field theo accessor của record; không cần tự nối chuỗi `"{" + ... + "}"` gây lỗi escaping hoặc JSON injection. Vì field tên đồng nhất, client có thể parse theo `code` và hiển thị `detail`.

### 5.5. ApiProblemWriter: một nơi chuẩn hóa status, header và JSON

`src/main/java/demo/errors/ApiProblemWriter.java`:

```java
package demo.errors;

import java.time.Instant;
import java.util.UUID;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@Component
public class ApiProblemWriter {
    private final ObjectMapper mapper;

    public ApiProblemWriter(ObjectMapper mapper) {
        this.mapper = mapper;
    }

    public Mono<Void> write(
            ServerWebExchange exchange,
            HttpStatusCode status,
            String code,
            String publicDetail,
            boolean basicChallenge) {

        var response = exchange.getResponse();
        if (response.isCommitted()) {
            return Mono.error(new IllegalStateException(
                "Cannot render an error after response commit"));
        }

        String id = exchange.getAttribute(
            CorrelationWebFilter.ATTRIBUTE_KEY);
        if (id == null) {
            id = UUID.randomUUID().toString();
            exchange.getAttributes().put(
                CorrelationWebFilter.ATTRIBUTE_KEY, id);
        }

        HttpStatus knownStatus = HttpStatus.resolve(status.value());
        String title = knownStatus == null
            ? "HTTP Error" : knownStatus.getReasonPhrase();

        ApiProblem body = new ApiProblem(
            "about:blank",
            title,
            status.value(),
            publicDetail,
            exchange.getRequest().getPath()
                .pathWithinApplication().value(),
            code,
            id,
            Instant.now().toString()
        );

        byte[] json;
        try {
            json = mapper.writeValueAsBytes(body);
        } catch (JsonProcessingException ex) {
            return Mono.error(ex);
        }

        response.setStatusCode(status);
        response.getHeaders().setContentType(
            MediaType.APPLICATION_PROBLEM_JSON);
        response.getHeaders().setCacheControl(
            CacheControl.noStore());
        response.getHeaders().set(
            CorrelationWebFilter.HEADER, id);

        if (basicChallenge) {
            response.getHeaders().set(
                HttpHeaders.WWW_AUTHENTICATE,
                "Basic realm=\"demo\"");
        }

        return response.writeWith(Mono.just(
            response.bufferFactory().wrap(json)));
    }
}
```

**Vì sao writer không nhận Throwable làm JSON?** Chỉ các thông điệp **đã kiểm soát** được đưa ra công khai. Nếu truyền `Throwable.getMessage()` lên client, lỗi SQL/JDBC, địa chỉ máy chủ, username hoặc logic nội bộ có thể bị lộ. `ApiProblemWriter` chỉ nhận `code` và `publicDetail` được chọn theo policy. Trong server log, có thể ghi exception stack ở nơi phù hợp và hạn chế truy cập; không gửi nó ra mạng.

**Lưu ý kỹ thuật:** Code đặt `response.isCommitted()` guard trước khi viết. Khi HTTP body đã bắt đầu phát, bạn **không thể đổi status 200 sang 500 và ghi JSON hoàn chỉnh**; phải xử lý error trong stream hoặc kết thúc kết nối theo ngữ nghĩa transport. Các endpoint `Flux` dài/streaming cần thiết kế riêng, ví dụ SSE error events với contract khác; đừng cố ghi thêm một Problem JSON ở cuối stream đã commit.

### 5.6. SecurityConfig: cả authentication entry point và access-denied

`src/main/java/demo/errors/SecurityConfig.java`:

```java
package demo.errors;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.ServerAuthenticationEntryPoint;
import org.springframework.security.web.server.authorization.ServerAccessDeniedHandler;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("alice123"))
            .roles("USER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("admin123"))
            .roles("ADMIN")
            .build();

        return new MapReactiveUserDetailsService(alice, admin);
    }

    @Bean
    SecurityWebFilterChain security(
            ServerHttpSecurity http, ApiProblemWriter writer) {

        ServerAuthenticationEntryPoint entryPoint =
            (exchange, exception) ->
                writer.write(
                    exchange,
                    HttpStatus.UNAUTHORIZED,
                    "AUTHENTICATION_REQUIRED",
                    "Authentication is required.",
                    true
                );

        ServerAccessDeniedHandler denied =
            (exchange, exception) ->
                writer.write(
                    exchange,
                    HttpStatus.FORBIDDEN,
                    "ACCESS_DENIED",
                    "You do not have permission to access this resource.",
                    false
                );

        return http
            .authorizeExchange(ex -> ex
                .pathMatchers(HttpMethod.GET, "/public/ping")
                    .permitAll()
                .pathMatchers(HttpMethod.GET, "/api/admin")
                    .hasRole("ADMIN")
                .pathMatchers(HttpMethod.GET, "/api/**")
                    .authenticated()
                .anyExchange().denyAll()
            )
            .exceptionHandling(ex -> ex
                .authenticationEntryPoint(entryPoint)
                .accessDeniedHandler(denied))
            .httpBasic(basic ->
                basic.authenticationEntryPoint(entryPoint))
            .formLogin(form -> form.disable())
            .build();
    }
}
```

**Bốn quyết định cần giữ:**

1. `httpBasic(...authenticationEntryPoint(entryPoint))` xử lý cả authentication failure do mật khẩu sai (filter Basic), còn `exceptionHandling(...authenticationEntryPoint(entryPoint))` xử lý request không có authentication phù hợp đến resource protected. Cùng writer → cùng schema.
2. `ServerAccessDeniedHandler` được dùng cho user có Authentication hợp lệ nhưng thiếu `ROLE_ADMIN`; khác `401` cả body code và status.
3. `hasRole("ADMIN")` tương ứng authority `ROLE_ADMIN` từ `User.roles("ADMIN")`; role được lấy từ nguồn tin cậy, không từ header `X-Role`.
4. `anyExchange().denyAll()` tránh mở route không khai báo. Đối với `/api/not-here`, khi đã authenticated thì matcher `GET /api/**` cho phép request đi tới WebFlux để thấy 404. Khi anonymous, security thường chặn 401 trước routing.

Ví dụ giữ CSRF mặc định cho các method thay đổi trạng thái; toàn bộ endpoint thử nghiệm chỉ là GET. Khi thêm POST/PUT/DELETE dùng cookie/session, cần cấu hình và test CSRF thích hợp, không disable CSRF như biện pháp “sửa” 403.

### 5.7. ApiController: tạo success và ba loại lỗi ứng dụng

`src/main/java/demo/errors/ApiController.java`:

```java
package demo.errors;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import reactor.core.publisher.Mono;

@RestController
public class ApiController {

    @GetMapping(value = "/public/ping",
                produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> ping() {
        return Mono.just("pong");
    }

    @GetMapping(value = "/api/me",
                produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> me() {
        return ReactiveSecurityContextHolder.getContext()
            .map(context -> context.getAuthentication().getName())
            .map(name -> "hello:" + name);
    }

    @GetMapping(value = "/api/admin",
                produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> admin() {
        return Mono.just("admin-ok");
    }

    @GetMapping(value = "/api/parse",
                produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> parse(@RequestParam("n") int number) {
        if (number < 0) {
            return Mono.error(new ResponseStatusException(
                HttpStatus.BAD_REQUEST,
                "Internal validation detail not for client"));
        }
        return Mono.just("n=" + number);
    }

    @GetMapping(value = "/api/fail",
                produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> fail() {
        return Mono.error(new IllegalStateException(
            "simulated-internal-secret-must-not-leak"));
    }
}
```

`/api/fail` là lỗi mô phỏng chủ đích để **đảm bảo response không rò rỉ message exception**. Không ném lỗi với credential thật; string trên chỉ là sentinel trong test. Trong sản phẩm thật, lỗi không mong muốn cần logging có redaction/observability, không nên bắt rồi in nguyên ra client.

`ResponseStatusException` là lựa chọn phù hợp cho lỗi với HTTP status rõ; khi exception có `reason` chứa thông tin nội bộ, writer vẫn gửi detail chung. Với ứng dụng lớn, thay vì tạo `ResponseStatusException` ở mọi service, có thể dùng domain exceptions/`@RestControllerAdvice` và ánh xạ code ổn định.

### 5.8. ApiErrorWebExceptionHandler: chuẩn hóa 400, 404 và 500

`src/main/java/demo/errors/ApiErrorWebExceptionHandler.java`:

```java
package demo.errors;

import org.springframework.boot.web.reactive.error.ErrorWebExceptionHandler;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpStatus;
import org.springframework.http.HttpStatusCode;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@Component
@Order(-2)
public class ApiErrorWebExceptionHandler
        implements ErrorWebExceptionHandler {

    private final ApiProblemWriter writer;

    public ApiErrorWebExceptionHandler(ApiProblemWriter writer) {
        this.writer = writer;
    }

    @Override
    public Mono<Void> handle(
            ServerWebExchange exchange, Throwable error) {

        if (exchange.getResponse().isCommitted()) {
            return Mono.error(error);
        }

        HttpStatusCode status =
            error instanceof ResponseStatusException ex
                ? ex.getStatusCode()
                : HttpStatus.INTERNAL_SERVER_ERROR;

        // Giữ HTTP headers có ý nghĩa mà framework đính kèm
        // (ví dụ Allow ở 405), rồi writer đặt Content-Type.
        if (error instanceof ResponseStatusException ex) {
            exchange.getResponse().getHeaders()
                .putAll(ex.getHeaders());
        }

        String code;
        String safeDetail;
        switch (status.value()) {
            case 400 -> {
                code = "INVALID_REQUEST";
                safeDetail = "The request is invalid.";
            }
            case 404 -> {
                code = "NOT_FOUND";
                safeDetail = "The requested resource was not found.";
            }
            case 405 -> {
                code = "METHOD_NOT_ALLOWED";
                safeDetail = "This HTTP method is not supported.";
            }
            case 409 -> {
                code = "CONFLICT";
                safeDetail = "The request conflicts with current state.";
            }
            case 429 -> {
                code = "RATE_LIMITED";
                safeDetail = "Too many requests.";
            }
            case 503 -> {
                code = "SERVICE_UNAVAILABLE";
                safeDetail = "The service is temporarily unavailable.";
            }
            default -> {
                if (status.is4xxClientError()) {
                    code = "REQUEST_REJECTED";
                    safeDetail = "The request cannot be completed.";
                } else {
                    code = "INTERNAL_ERROR";
                    safeDetail = "An unexpected error occurred.";
                    status = HttpStatus.INTERNAL_SERVER_ERROR;
                }
            }
        }

        return writer.write(
            exchange, status, code, safeDetail, false);
    }
}
```

`ErrorWebExceptionHandler` là extension của WebFlux exception handling. `@Order(-2)` để handler custom được chọn trước default handler do Spring Boot cung cấp; khi đã có bean custom, Boot có thể không tạo default error handler tùy auto-configuration. Đây là cách can thiệp **thấp tầng**; phải giữ hành vi đúng với các exception/status hiện có và test kỹ khi nâng framework.

**Tại sao bảo toàn headers?** `ResponseStatusException.getHeaders()` có thể mang `Allow` cho 405 hoặc header hữu ích khác; writer chung chỉ thay content type/cache/correlation. Với một API lớn, cần ánh xạ thêm `ErrorResponseException`/validation exception và exception headers theo phiên bản, hỗ trợ structured validation details có redaction, CORS headers, 422/429 theo policy.

**Vì sao không thử ghi 500 sau khi response đã commit?** WebFlux có thể bắt đầu stream SSE/Flux và phát 200 trước khi lỗi xảy ra. Khi đó không thể gửi HTTP 500 + body Problem JSON mới trên cùng response. Handler trả lỗi cho tầng ngoài thay vì tạo một JSON bị nối hỏng; thiết kế streaming errors riêng.

## 6. Chạy ứng dụng và quan sát bằng curl

Từ thư mục project:

```bash
java -version
mvn -version
mvn spring-boot:run
```

Khi Netty chạy ở 8080, mở terminal thứ hai. `curl -i` hiển thị status/header/body:

```bash
curl -i http://localhost:8080/public/ping
curl -i http://localhost:8080/api/me
curl -i --user alice:alice123 http://localhost:8080/api/me
curl -i --user alice:wrong http://localhost:8080/api/me
curl -i --user alice:alice123 http://localhost:8080/api/admin
curl -i --user admin:admin123 http://localhost:8080/api/admin
curl -i --user alice:alice123 'http://localhost:8080/api/parse?n=-1'
curl -i --user alice:alice123 http://localhost:8080/api/not-here
curl -i --user alice:alice123 http://localhost:8080/api/fail
```

| Request | Dự kiến | Điều cần đối chiếu |
| --- | --- | --- |
| `/public/ping` public | 200, `pong` | Có `X-Correlation-Id` dù không có error body |
| `/api/me` anonymous | 401 | `WWW-Authenticate: Basic ...`, JSON code `AUTHENTICATION_REQUIRED` |
| `/api/me` Alice đúng | 200, `hello:alice` | Header ID là UUID do server phát |
| `/api/me` Alice sai | 401 | Cùng schema/headers như anonymous; không lộ user/password |
| `/api/admin` Alice | 403 | JSON code `ACCESS_DENIED`, không có Basic challenge bắt buộc |
| `/api/admin` admin | 200, `admin-ok` | Role được tải từ user store |
| `/api/parse?n=-1` | 400 | JSON code `INVALID_REQUEST`, không lộ reason nội bộ |
| `/api/not-here` sau authentication | 404 | JSON code `NOT_FOUND`, path không có query secret |
| `/api/fail` | 500 | JSON code `INTERNAL_ERROR`, không lộ `simulated-internal-secret-must-not-leak` |

Với các lỗi trên, content type là `application/problem+json`, status JSON bằng HTTP status, header `X-Correlation-Id` bằng field `correlationId`. Timestamp và UUID thay đổi giữa các request, vì vậy **không so với giá trị cố định** trong test.

Dùng PowerShell cũ có thể cần `curl.exe` thay cho alias `curl`. Chỉ dùng password demo qua localhost; Basic gửi credential dạng Base64, cần **HTTPS** ở môi trường thật. Không đặt password hoặc Bearer token thật vào shell history.

### 6.1. Kiểm chứng server không tin mã tương quan do client khai

```bash
curl -i --user alice:alice123 \
  -H 'X-Correlation-Id: attacker-picked-id' \
  http://localhost:8080/api/me
```

Header response phải là một UUID do server phát, **khác** `attacker-picked-id`. Điều đó giúp tránh phản chiếu các chuỗi tùy ý từ Internet vào log hoặc lỗi. Nếu tổ chức muốn giữ correlation từ gateway đáng tin, hãy thực hiện validation/trust boundary ở ingress và kiểm thử riêng.

### 6.2. HTTP/JSON không nên bị “đồng nhất hóa” sai

- Với HTTP Basic 401, **`WWW-Authenticate` là thành phần giao thức**, không thể bỏ chỉ vì body đã đẹp.
- Với HTTP 403, client đã đăng nhập nhưng thiếu role; không nên gửi credential challenge như thể password sai.
- Với 404 sau authentication, request có thể đi tới mapping không có route; nếu an ninh chặn sớm theo default deny, bạn có thể thấy 401/403 thay cho 404. Thiết kế matcher có chủ đích.
- Với 500, thông điệp công khai luôn chung và phải ghi log nguyên nhân ở phía server với quyền truy cập phù hợp.
- Với validation lỗi, có thể bổ sung list `violations` chỉ chứa field name và message an toàn, không echo raw password/token.

## 7. Kiểm thử WebTestClient tự động

Để kiểm tra đúng **các filter HTTP** thay vì chỉ gọi trực tiếp controller, dùng `@SpringBootTest(webEnvironment = RANDOM_PORT)`. `WebTestClient` gửi request tới server thật, không mock Authentication bằng test-only header.

Bộ kiểm thử kiểm tra cả các trường quan trọng của JSON, không chỉ status. `ObjectMapper` dùng để parse JSON; không assert toàn bộ string vì thứ tự field, timestamp và UUID không phải constant.

`src/test/java/demo/errors/ApiErrorTests.java`:

```java
package demo.errors;

import java.util.UUID;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.EntityExchangeResult;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class ApiErrorTests {

    @Autowired
    WebTestClient client;

    @Autowired
    ObjectMapper mapper;

    private JsonNode assertProblem(
            EntityExchangeResult<byte[]> result,
            int status, String code) throws Exception {

        assertEquals(status, result.getStatus().value());
        assertEquals(MediaType.APPLICATION_PROBLEM_JSON,
            result.getResponseHeaders().getContentType());

        String id = result.getResponseHeaders()
            .getFirst(CorrelationWebFilter.HEADER);
        assertNotNull(id, "Missing X-Correlation-Id header");
        assertEquals(UUID.fromString(id).toString(), id);

        String cacheControl = result.getResponseHeaders()
            .getFirst(HttpHeaders.CACHE_CONTROL);
        assertNotNull(cacheControl);
        assertTrue(cacheControl.contains("no-store"));

        JsonNode json = mapper.readTree(result.getResponseBody());
        assertEquals("about:blank", json.path("type").asText());
        assertEquals(status, json.path("status").asInt());
        assertEquals(code, json.path("code").asText());
        assertEquals(id, json.path("correlationId").asText());
        assertFalse(json.path("title").asText().isBlank());
        assertFalse(json.path("detail").asText().isBlank());
        assertFalse(json.path("timestamp").asText().isBlank());
        return json;
    }

    @Test
    void anonymousRequestGets401JsonAndBasicChallenge() throws Exception {
        var result = client.get().uri("/api/me")
            .exchange()
            .expectStatus().isUnauthorized()
            .expectBody().returnResult();

        JsonNode json =
            assertProblem(result, 401, "AUTHENTICATION_REQUIRED");
        assertEquals("/api/me", json.path("instance").asText());
        String challenge = result.getResponseHeaders()
            .getFirst(HttpHeaders.WWW_AUTHENTICATE);
        assertNotNull(challenge);
        assertTrue(challenge.startsWith("Basic "));
    }

    @Test
    void wrongPasswordHasSameSafe401Contract() throws Exception {
        var result = client.get().uri("/api/me")
            .headers(h -> h.setBasicAuth("alice", "incorrect"))
            .exchange()
            .expectStatus().isUnauthorized()
            .expectBody().returnResult();

        JsonNode json =
            assertProblem(result, 401, "AUTHENTICATION_REQUIRED");
        assertTrue(json.toString().contains("AUTHENTICATION_REQUIRED"));
        assertFalse(json.toString().contains("incorrect"));
        assertNotNull(result.getResponseHeaders()
            .getFirst(HttpHeaders.WWW_AUTHENTICATE));
    }

    @Test
    void authenticatedReaderGets403Problem() throws Exception {
        var result = client.get().uri("/api/admin")
            .headers(h -> h.setBasicAuth("alice", "alice123"))
            .exchange()
            .expectStatus().isForbidden()
            .expectBody().returnResult();

        JsonNode json = assertProblem(result, 403, "ACCESS_DENIED");
        assertEquals("/api/admin", json.path("instance").asText());
    }

    @Test
    void invalidInputGets400Problem() throws Exception {
        var result = client.get().uri("/api/parse?n=-1")
            .headers(h -> h.setBasicAuth("alice", "alice123"))
            .exchange()
            .expectStatus().isBadRequest()
            .expectBody().returnResult();

        JsonNode json = assertProblem(result, 400, "INVALID_REQUEST");
        assertEquals("/api/parse", json.path("instance").asText());
        assertFalse(json.toString().contains(
            "Internal validation detail not for client"));
    }

    @Test
    void nonexistentApiPathGets404Problem() throws Exception {
        var result = client.get().uri("/api/not-here")
            .headers(h -> h.setBasicAuth("alice", "alice123"))
            .exchange()
            .expectStatus().isNotFound()
            .expectBody().returnResult();

        JsonNode json = assertProblem(result, 404, "NOT_FOUND");
        assertEquals("/api/not-here", json.path("instance").asText());
    }

    @Test
    void unexpectedErrorIs500WithoutInternalException() throws Exception {
        var result = client.get().uri("/api/fail")
            .headers(h -> h.setBasicAuth("alice", "alice123"))
            .exchange()
            .expectStatus().is5xxServerError()
            .expectBody().returnResult();

        JsonNode json = assertProblem(result, 500, "INTERNAL_ERROR");
        assertFalse(json.toString().contains(
            "simulated-internal-secret-must-not-leak"));
        assertFalse(json.toString().contains("IllegalStateException"));
    }

    @Test
    void successfulRequestAlsoHasCorrelationHeader() {
        client.get().uri("/api/me")
            .headers(h -> h.setBasicAuth("alice", "alice123"))
            .exchange()
            .expectStatus().isOk()
            .expectHeader().exists(CorrelationWebFilter.HEADER)
            .expectBody(String.class).isEqualTo("hello:alice");
    }

    @Test
    void clientSuppliedCorrelationIdIsNotTrusted() {
        var result = client.get().uri("/api/me")
            .headers(h -> h.setBasicAuth("alice", "alice123"))
            .header(CorrelationWebFilter.HEADER, "attacker-picked-id")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("hello:alice")
            .returnResult();

        String returned = result.getResponseHeaders()
            .getFirst(CorrelationWebFilter.HEADER);
        assertNotNull(returned);
        assertEquals(UUID.fromString(returned).toString(), returned);
        assertNotEquals("attacker-picked-id", returned);
    }

    @Test
    void separateRequestsReceiveDifferentIds() {
        var first = client.get().uri("/public/ping")
            .exchange().expectStatus().isOk()
            .expectBody().returnResult();
        var second = client.get().uri("/public/ping")
            .exchange().expectStatus().isOk()
            .expectBody().returnResult();

        String a = first.getResponseHeaders()
            .getFirst(CorrelationWebFilter.HEADER);
        String b = second.getResponseHeaders()
            .getFirst(CorrelationWebFilter.HEADER);
        assertNotNull(a);
        assertNotNull(b);
        assertNotEquals(a, b);
    }

    @Test
    void adminCanUseAdminEndpoint() {
        client.get().uri("/api/admin")
            .headers(h -> h.setBasicAuth("admin", "admin123"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("admin-ok");
    }
}
```

Chạy:

```bash
mvn test
```

Nếu chỉ có test class trên, **mục tiêu là 10 test pass** khi dependency, môi trường, cấu hình chính xác. Đây là mã giáo trình để tự chạy; **không tuyên bố test đã được thực thi trên máy của người đọc**. Khi gặp lỗi, xem status/header/JSON path nào không khớp và ngoại lệ phía server; không sửa test thành chỉ assert 200/401 mà bỏ hợp đồng.

### 7.1. Vì sao các test này có giá trị hơn việc kiểm HTTP status?

- Anonymous 401 **và** password sai 401: xác nhận hai nguồn authentication error đi qua cùng schema và vẫn có Basic challenge.
- Alice gọi admin: Authentication hợp lệ, nhưng `403` từ access denied, không trả 401 như lỗi password.
- Input sai/route không tồn tại/unexpected error: kiểm tra writer chung có được gọi từ tầng WebFlux, không chỉ Spring Security.
- Error 500 không có message và tên class nội bộ: xác nhận policy **không lộ chi tiết server**.
- Header `X-Correlation-Id` và JSON `correlationId` bằng nhau; chuỗi parse được thành UUID chuẩn.
- Hai request có hai ID khác nhau; client gửi ID tùy ý không làm thay đổi ID server phát.
- Test success 200 cũng có ID — giúp điều tra các request không lỗi nhưng gây hành vi chậm/sai dữ liệu.

**Giới hạn:** Test môi trường local không chứng minh API gateway/nginx/service mesh cũng giữ header hoặc redaction đúng. Khi deploy, cần kiểm thử end-to-end từ ingress công khai tới backend và distributed tracing.

## 8. Khi nào nên dùng ProblemDetail có sẵn thay vì writer thủ công?

Spring Framework có `org.springframework.http.ProblemDetail` và hỗ trợ RFC 9457. Spring Boot WebFlux có thể bật:

```properties
spring.webflux.problemdetails.enabled=true
```

Đây là một **lựa chọn thay thế** cho phần handling lỗi ứng dụng; nó không tự bảo đảm Spring Security entry point, HTTP Basic failure handler và mọi error mapping đều thêm extension `code`/`correlationId` theo schema tổ chức. Nếu dùng `ProblemDetail`/`ErrorResponse`, nên chuẩn hóa qua `@ControllerAdvice`, `ErrorAttributes` hoặc các hook tương ứng, kết hợp Security handlers dùng cùng schema.

Project ví dụ ở trên dùng writer tùy biến nhất quán cho cả security và general errors để minh họa trách nhiệm từng tầng. **Không bật chồng hai pipeline lỗi độc lập** mà không biết thứ tự: có thể tạo response không nhất quán, hai writer cùng ghi body hoặc thay đổi Content-Type. Trong ứng dụng production, chọn **một convention rõ ràng**, test đủ các đường và ưu tiên cơ chế framework khi đáp ứng được yêu cầu.

### 8.1. @RestControllerAdvice vẫn hữu ích cho domain exceptions

Ví dụ nếu domain có `ResourceAlreadyExistsException`, controller advice có thể chuyển thành `409 Conflict` với mã `CONFLICT`. Nhưng lỗi bảo mật trước controller vẫn phải đi qua `ServerAuthenticationEntryPoint` và `ServerAccessDeniedHandler`. Với custom `@RestControllerAdvice`, có thể tạo một `ApiProblem` qua factory chung và trả `ResponseEntity<ApiProblem>`; khi đó vẫn phải đồng bộ `Content-Type`, `X-Correlation-Id` và logging policy.

Đừng thiết kế `@ExceptionHandler(Exception.class)` ở mọi controller rồi giấu mọi lỗi thành 200 rỗng, vì sẽ mất status chính xác và làm client không thể phân biệt retry/permission/input.

## 9. Propagation ID qua WebClient và hệ thống phân tán

`ServerWebExchange.getAttributes()` là nơi thuận tiện **trong request hiện tại**. Khi WebFlux code gọi service khác qua `WebClient`, không nên cố đọc exchange attribute ở bean singleton không có request. Vì `CorrelationWebFilter` đã đặt ID trong Reactor Context, một `ExchangeFilterFunction` có thể truy cập Context ở subscription để gắn header outbound có kiểm soát.

**Fragment mô tả**, cần import `WebClient`, `ClientRequest`, `ExchangeFilterFunction`, `Mono` và bean cấu hình tương ứng:

```java
@Bean
WebClient internalWebClient(WebClient.Builder builder) {
    ExchangeFilterFunction propagate = (request, next) ->
        Mono.deferContextual(context -> {
            String id = context.getOrDefault(
                CorrelationWebFilter.CONTEXT_KEY, "");
            ClientRequest.Builder outbound =
                ClientRequest.from(request);
            if (!id.isBlank()) {
                outbound.headers(headers ->
                    headers.set(CorrelationWebFilter.HEADER, id));
            }
            return next.exchange(outbound.build());
        });

    return builder
        .filter(propagate)
        .build();
}
```

Đây **không phải file cần thêm vào project runnable**: hệ thống demo không có downstream. Khi sử dụng thật, chỉ propagation tới service được tin cậy và phù hợp policy; nếu có OpenTelemetry, ưu tiên instrumentation chính thức để chuyển `traceparent`/baggage. Correlation ID chỉ hỗ trợ liên hệ, không cấp quyền cho outbound call.

Trường hợp lời gọi ra Kafka/queue/background task, không dựa vào Reactor Context của request đã kết thúc. Truyền correlation ID dưới dạng metadata/message header được validate, giữ đủ TTL và không nhét access token/PII vào đó. Hệ thống nhận tạo span/request ID riêng nếu cần, và nối đến trace/correlation gốc theo hợp đồng. Một người dùng bấm nhiều thao tác có thể sinh nhiều request ID; đừng dùng một ID cố định cho toàn bộ user session.

### 9.1. Logging JSON/structured logs

Log tối thiểu cho một error nên liên hệ được `correlationId`, timestamp, service name, operation/route, status, error code và trace/span IDs nếu có. Ví dụ mẫu:

```json
{
  "event": "api_request_failed",
  "service": "report-api",
  "status": 403,
  "code": "ACCESS_DENIED",
  "correlationId": "8d9cc0a5-4e2f-49ba-9b01-4e120a13516a",
  "route": "/api/admin"
}
```

Không log `Authorization`, cookies, Basic credentials, refresh token, full request body, database connection string, raw stack trace vào logging public. Server-side stack trace nếu cần phải nằm trong log bảo vệ quyền truy cập/retention, không phải error response. Nên log **route template** (ví dụ `/reports/{id}`) thay vì full path nếu path chứa PII; không nên đưa email/SSN vào `correlationId`.

### 9.2. Những ngoại lệ của quy tắc một request một ID

- Một request có nhiều retry nội bộ: có thể giữ correlation ID đầu vào và tạo span riêng cho mỗi lần gọi downstream.
- Một batch request gồm nhiều item: một request ID cho HTTP request, item IDs riêng cho từng lỗi nghiệp vụ nếu cần.
- Một asynchronous job kéo dài sau response: giữ correlation/causation ID của job theo metadata bền vững, tạo request/job event ID mới khi xử lý.
- Một CDN trả 4xx/5xx **trước khi request tới ứng dụng**: filter WebFlux không chạy; CDN/gateway phải có error contract và ID riêng hoặc phối hợp.

## 10. Bảo mật của phản hồi lỗi

### 10.1. Không tiết lộ thông tin xác thực

Với 401, tránh response phân biệt `"unknown user"` và `"wrong password"` nếu có nguy cơ liệt kê username. Dùng `AUTHENTICATION_REQUIRED` và detail chung, log nội bộ loại lỗi theo mức bảo mật phù hợp. Mật khẩu không bao giờ được phản chiếu trong error JSON.

### 10.2. Không tiết lộ permission nội bộ qua 403

User thường chỉ cần biết `ACCESS_DENIED`. Tránh gửi toàn bộ authorities, role nội bộ, policy evaluation trace, tên bảng database hoặc resource của user khác. Một số API có thể trả 404 để che việc resource tồn tại, nhưng đó là **quyết định domain/security policy** riêng; không đổi 403 thành 404 tùy tiện để “khớp JSON”.

### 10.3. Không leak exception ở 500

`IllegalStateException: databasePassword=...`, stack trace, SQL, host nội bộ hoặc Java package names không được gửi ra ngoài. Response `INTERNAL_ERROR` vẫn kèm correlationId để team điều tra trong log quyền hạn phù hợp. Dùng hệ thống exception capture/tracing bảo vệ dữ liệu, không dựa vào client gửi nguyên stack.

### 10.4. Giữ status và headers giao thức

Tổng quát hóa lỗi JSON không có nghĩa bỏ `WWW-Authenticate`, `Allow`, `Retry-After`, `Vary`, CORS, `Content-Language` hoặc cache directives khi chúng có ý nghĩa. Bộ handler mẫu giữ `ResponseStatusException.getHeaders()` và writer chuẩn hóa content type; hệ thống thật còn cần kiểm thử middleware/proxy, đặc biệt khi response preflight CORS hoặc rate limiting được tạo ở filter bên ngoài.

### 10.5. Kiểm soát input và output

Client có thể đưa Unicode/control chars hoặc chuỗi dài vào query/path. Không embed raw input vào JSON bằng string concatenation: serializer Jackson xử lý escaping, còn validation/length limit phải theo domain. Không phản chiếu trực tiếp `X-Correlation-Id` từ client. Với `instance`, dùng path không kèm query; nếu path chứa giá trị bí mật hoặc ID nhạy cảm, dùng route template thay thế.

### 10.6. Không tạo response mới sau commit

Stream đã phát HTTP 200 và một phần dữ liệu sẽ không thể chuyển thành `500 application/problem+json` theo cách truyền thống. Với SSE/NDJSON/WebSocket, cần contract error/event riêng và close/retry semantics rõ. Không cố gọi `response.writeWith` lần hai sau commit.

## 11. Phân biệt cách xử lý các lỗi nghiệp vụ

**Validation:** Với JSON request có fields sai, có thể thêm extension `violations` như `[{"field":"amount","code":"MUST_BE_POSITIVE"}]` sau khi lọc thông tin nhạy cảm. Không echo password hoặc raw payload. Chọn 400 vs 422 có quy tắc.

**Resource ownership:** Khi user A yêu cầu tài nguyên của B, `@PreAuthorize` hoặc service/repository có thể trả 403/404 theo chính sách. Không cung cấp chi tiết có thể giúp suy luận có tài nguyên người khác.

**Concurrency:** Một optimistic locking conflict thường là 409 với code `CONFLICT`, chứ không phải 500. Trả một mã ổn định để client quyết định tải lại/đề nghị user giải quyết.

**Rate limiting:** Khi vượt hạn mức, API có thể trả 429 với `Retry-After` theo policy; không ghi một số giây đoán mò. Correlation ID hữu ích để điều tra request bị giới hạn.

**Timeout/dependency failure:** Một downstream 503/504 cần phân biệt retry được hay không; không coi mọi network error đều là lỗi người dùng. Không để body lộ hostname/URL chứa secret.

**Cancelled request:** Khi client hủy kết nối trước response, server không chắc gửi được JSON problem. Log `cancel` cùng correlationId nếu observability cần, nhưng không tuyên bố mọi lỗi đều có body trên wire.

## 12. Bảng kiểm thử nghiệm thu

| Scenario | Status | JSON code | Header cần kiểm | Test bảo mật |
| --- | --- | --- | --- | --- |
| GET public | 200 | Không bắt buộc error JSON | `X-Correlation-Id` | Không lộ thông tin auth |
| GET protected anonymous | 401 | `AUTHENTICATION_REQUIRED` | `WWW-Authenticate` + correlation ID | Không rò thông tin user |
| Basic sai password | 401 | `AUTHENTICATION_REQUIRED` | `WWW-Authenticate` | Không echo raw password |
| User đã login thiếu role | 403 | `ACCESS_DENIED` | Correlation ID | Không tiết lộ policy internals |
| Invalid parameter | 400 | `INVALID_REQUEST` | Correlation ID | Không echo raw input secret |
| Không có route, đã login | 404 | `NOT_FOUND` | Correlation ID | Không tiết lộ filesystem |
| Unexpected exception | 500 | `INTERNAL_ERROR` | Correlation ID | Không stack trace/message nội bộ |
| Request giả header correlation | Theo nghiệp vụ | Theo nghiệp vụ | Server-issued ID | ID client không được tin |
| Hai request liên tiếp | Theo nghiệp vụ | Theo nghiệp vụ | **Hai ID khác nhau** | Không dùng biến static |
| Streaming response đã commit rồi lỗi | Tùy transport | Contract streaming riêng | ID/log | Không cố ghi JSON sau commit |

### 12.1. Trình tự điều tra khi JSON không đồng nhất

1. Xem đúng **HTTP status và Content-Type** của response sai khác; có phải một filter tạo response trước controller không?
2. Kiểm tra request thiếu Basic, sai Basic, thiếu role hay được phép vào controller; xác định nguồn 401/403 trước.
3. Xem `ServerHttpSecurity.httpBasic.authenticationEntryPoint` và `exceptionHandling.authenticationEntryPoint` có dùng **cùng** handler không.
4. Xem `ServerAccessDeniedHandler` có dùng chung writer không, và có giữ status 403 không.
5. Xem `ErrorWebExceptionHandler` có được Spring Boot chọn trước default handler hay không; nếu lỗi 404 vẫn HTML, kiểm tra route error handler/Accept header.
6. Kiểm tra `CorrelationWebFilter` được áp dụng trước security, ID không bị proxy loại bỏ hoặc sinh lại ngoài ý muốn.
7. Kiểm tra body không được ghi sau response commit; với SSE/streaming dùng chiến lược khác.
8. Chạy test đủ 401/403/400/404/500, test header và JSON fields, không chỉ snapshot body.
9. Ở môi trường deploy, kiểm tra gateway/CDN/ingress có tạo lỗi của riêng chúng và chính sách header propagation ra sao.
10. Đối chiếu log bằng ID, kiểm tra redaction, sampling và retention. Nếu log không có ID, trước hết xác định hop nào đã tạo response.

## 13. Những câu hỏi thường nhầm

**“Chỉ cần @RestControllerAdvice là 401, 403 cũng JSON.”** Không đảm bảo. Spring Security thường từ chối ở WebFilter trước controller; cần reactive entry point/denied handler.

**“401 và 403 đều là permission denied nên dùng chung status.”** Không. `401` cho tình huống cần xác thực/challenge, còn `403` là thiếu quyền theo policy. HTTP semantics phải được giữ.

**“Đã trả JSON 401 nên bỏ WWW-Authenticate được.”** Không với HTTP Basic chuẩn. Header challenge là phần quan trọng của giao thức.

**“Correlation ID chỉ xuất hiện trên error.”** Không nên nếu mục tiêu là truy vết end-to-end: response thành công cũng nên có ID.

**“Lấy email hoặc username làm correlation ID cho tiện.”** Không. Đó là PII/identity, có nguy cơ lộ và không phân biệt nhiều request của cùng user.

**“Dùng UUID thì có quyền truy cập API.”** Không. UUID ở đây là nhãn quan sát, không có vai trò authentication hoặc authorization.

**“Dùng MDC.put rồi WebFlux tự đảm bảo đúng ID xuyên thread.”** Không. Cần Reactor Context/Micrometer Context Propagation hoặc truyền dữ liệu phù hợp.

**“Muốn nhất quán thì lỗi nào cũng trả 500.”** Không. Body thống nhất nhưng status vẫn phải phản ánh input, quyền, resource hoặc hạ tầng.

**“ApiProblemWriter có thể luôn viết body lỗi ngay khi nhận Throwable.”** Không khi response đã commit hoặc lỗi ở tầng ngoài WebFlux. Xử lý theo lifecycle/transport.

**“Thêm một header correlation do client gửi vào log thì vô hại.”** Không chắc. Nó có thể bị dùng để tạo log injection, kích thước cực lớn hoặc giả mạo ID. Xác định trust boundary và validation.

## 14. Checklist áp dụng vào sản phẩm

1. Chốt contract `application/problem+json`, field chuẩn RFC 9457, extension `code`/`correlationId` và bộ mã lỗi có version.
2. Phân biệt 400/401/403/404/409/429/500/503 đúng HTTP, và giữ các headers bắt buộc như `WWW-Authenticate`.
3. Dùng một service/writer duy nhất sinh JSON, không nối JSON bằng chuỗi thủ công.
4. Wiring cả HTTP Basic failure và missing-authentication entry point, cộng access denied handler.
5. Chuẩn hóa lỗi WebFlux/validation/domain, tránh conflict giữa `@RestControllerAdvice`, Boot default error handling và custom `ErrorWebExceptionHandler`.
6. Phát correlation ID đủ sớm, trong scope request, không tin giá trị client chưa kiểm chứng; trả header cho cả success/error.
7. Nếu có tracing, đồng bộ correlation ID với trace/span infrastructure thay vì ghi đè `traceparent`.
8. Không ghi credential, session cookie, token, SQL hoặc stack trace vào response/public logs.
9. Kiểm tra streaming/cancel/error sau commit và định nghĩa contract riêng nếu dùng SSE/WebSocket.
10. Test tự động 401/403/400/404/500, challenge, content type, status-vs-body, ID header/body, ID khác nhau giữa requests và message redaction.
11. Test end-to-end qua gateway/CDN, forwarded headers, CORS, rate limit và reverse proxy; không coi test localhost là đủ cho toàn hệ thống.
12. Khi thay Spring Security/Boot version, chạy lại integration tests vì thứ tự filter/error handling và default headers có thể thay đổi.

## 15. Câu hỏi tự đánh giá

**Câu 1.** User không gửi Basic credential vào `/api/me`. Tầng nào thường tạo 401?  
`ServerAuthenticationEntryPoint` của Spring Security khi authorization yêu cầu authentication, không nhất thiết có controller method được gọi.

**Câu 2.** User nhập sai password và cũng nhận 401. Cấu hình ở đâu để JSON giống trường hợp thiếu credential?  
Cấu hình cùng entry point ở `httpBasic(...authenticationEntryPoint(...))` **và** `exceptionHandling(...authenticationEntryPoint(...))`.

**Câu 3.** Alice đã đăng nhập nhưng không có ADMIN gọi `/api/admin`. Tại sao 403 chứ không phải 401?  
Authentication đúng, authorization thiếu quyền; `ServerAccessDeniedHandler` xử lý, không thách thức Basic như khi thiếu credential.

**Câu 4.** Vì sao một `@RestControllerAdvice` không bảo đảm bắt hết lỗi Security?  
Vì Security WebFilters xử lý ở lớp trước controller; nhiều lỗi 401/403 không được ném từ handler method.

**Câu 5.** `correlationId` có được phép chứa Bearer token hoặc session ID không?  
**Không.** Đó là metadata truy vết, không phải kho lưu credential hoặc thông tin nhạy cảm.

**Câu 6.** Response HTTP 500 có nên trả `SQLException.getMessage()` cho client không?  
**Không.** Trả `INTERNAL_ERROR`/detail an toàn và log nguyên nhân ở nơi hạn chế quyền, liên hệ qua correlation ID.

**Câu 7.** Một WebFlux thread phục vụ nhiều request. Có nên dùng biến static để lưu correlation ID hiện tại không?  
**Không.** Dùng exchange attributes/Reactor Context hoặc tracing integration theo request/subscriber.

**Câu 8.** API đã gửi nửa Flux body với HTTP 200, sau đó xảy ra exception. Có thể đổi thành 500 Problem JSON không?  
**Không** nếu response đã committed. Cần streaming-specific error strategy/close semantics.

**Câu 9.** Nếu client gửi `X-Correlation-Id: attacker-picked-id`, demo sẽ trả gì?  
Một UUID mới do server phát, không tin chuỗi của client.

**Câu 10.** Đã dùng `application/problem+json` có thể bỏ HTTP status chuẩn không?  
**Không.** Body hỗ trợ chẩn đoán, nhưng HTTP status và headers giao thức vẫn là hợp đồng mạng.

### Tài liệu chính thức

- RFC 9457, *Problem Details for HTTP APIs*: https://www.rfc-editor.org/rfc/rfc9457
- Spring Boot, *Reactive Web Applications — Error Handling*: https://docs.spring.io/spring-boot/reference/web/reactive.html
- Spring Framework, *Error Responses / ProblemDetail*: https://docs.spring.io/spring-framework/reference/web/webflux/ann-rest-exceptions.html
- Spring Security, *WebFlux Security*: https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html
- Spring Security API, `ServerHttpSecurity.HttpBasicSpec`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.HttpBasicSpec.html
- Spring Security API, `ServerHttpSecurity.ExceptionHandlingSpec`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.ExceptionHandlingSpec.html
- Spring Security API, `ServerAuthenticationEntryPoint`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/ServerAuthenticationEntryPoint.html
- Spring Security API, `ServerAccessDeniedHandler`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/authorization/ServerAccessDeniedHandler.html
- Spring Boot API, `ErrorWebExceptionHandler`: https://docs.spring.io/spring-boot/api/java/org/springframework/boot/web/reactive/error/ErrorWebExceptionHandler.html
- W3C, *Trace Context*: https://www.w3.org/TR/trace-context/
- Spring Framework, *WebTestClient*: https://docs.spring.io/spring-framework/reference/testing/webtestclient.html

**Ghi nhớ:** JSON lỗi nhất quán không chỉ là một record. Cần cùng schema/writer cho **Spring Security 401/403 và WebFlux 4xx/5xx**, giữ HTTP status/headers đúng, phát **correlation ID theo request**, không tin ID từ client chưa kiểm chứng, không tiết lộ credential/stack trace và có integration tests xuyên các tầng. Nhờ đó client nhận lỗi đoán được, còn vận hành tìm đúng request từ log mà không làm yếu bảo mật.