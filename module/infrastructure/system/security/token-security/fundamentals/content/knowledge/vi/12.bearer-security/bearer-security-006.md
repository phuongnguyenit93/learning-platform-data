# Redact token trong exception và trace

Một Resource Server dùng OAuth 2.0 nhận request với header `Authorization: Bearer <access-token>`. Khi token hết hạn, lập trình viên muốn chẩn đoán lỗi `401` nên thêm:

~~~java
log.error("Auth failed: {}", request.getHeader("Authorization"), exception);
~~~

Dòng này có thể chép **toàn bộ bearer token** vào log. Nếu exception được tự động ghi vào distributed trace, error reporting hoặc APM, cùng một giá trị còn có thể xuất hiện trong span events, stack trace, dashboard, kho lưu trữ và bản export. Người có quyền xem những dữ liệu đó có thể **phát lại token** trong thời gian nó còn hợp lệ, dù token là JWT được ký hay opaque token ngẫu nhiên.

**Redaction** là việc loại bỏ hoặc thay giá trị nhạy cảm trước khi dữ liệu đi vào log, exception response, span, event hoặc telemetry. Đối với token bảo mật, lựa chọn ưu tiên là **không thu thập từ đầu**. Khi cần chẩn đoán, chỉ ghi thông tin được kiểm soát như mã lỗi, HTTP status, route template, service, trace ID và thời gian xử lý.

Bài thuộc chương **Bearer security** của module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**. Trọng tâm là cách tránh lộ access token, refresh token, ID token và bí mật liên quan trong ứng dụng Java/Spring, OAuth 2.0/OIDC, API gateway và hệ thống distributed tracing, đồng thời giữ nguyên việc kiểm claims, scope, audience, thời hạn, quyền và cơ chế thu hồi.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vì sao **bearer token trong log/trace là credential exposure**, không chỉ là lỗi định dạng thông báo.
2. Xác định nơi token rò gián tiếp: HTTP headers, body, URL, exception message/cause, stack trace, APM, OpenTelemetry, baggage và DTO serialization.
3. Phân biệt **không ghi dữ liệu**, **redact**, **mask một phần**, **HMAC fingerprint** và **ẩn trên dashboard**.
4. Xây dựng logging theo **allowlist trường an toàn** thay vì chỉ dựa vào regex tìm JWT.
5. Xử lý lỗi Spring Security/MVC không trả hoặc ghi bearer token.
6. Thiết kế span attributes/events/status an toàn, cấu hình agent/collector theo nguyên tắc tối thiểu.
7. Kiểm thử bằng canary credential và xử lý sự cố khi token đã nằm trong telemetry.

## 2. Tại sao log bearer token lại nguy hiểm?

Bearer token cho phép bên đang giữ token trình nó tại Resource Server. Server kiểm chữ ký hoặc introspection, issuer, audience, scope, thời gian và policy, nhưng **bearer token không tự chứng minh người gửi request hiện tại chính là người đã đăng nhập**.

Ví dụ:

~~~text
08:00  Người dùng đăng nhập qua MFA và nhận access token của orders-api.
08:01  API ghi Authorization header vào log vì lỗi validation.
08:02  Người có quyền đọc log sao chép token chưa hết hạn.
08:03  Người đó trình token tại orders-api.
08:03  API có thể chấp nhận nếu token còn hiệu lực và đủ quyền.
~~~

MFA đã tăng bảo đảm cho sự kiện đăng nhập nhưng không khiến bản sao bearer token vô hiệu. Chữ ký JWT ngăn sửa payload mà **không ngăn sao chép**. Opaque token ngẫu nhiên khó đoán nhưng khi bị lộ cũng có thể bị tái sử dụng.

**Sender-constrained access token** (ví dụ DPoP hoặc mTLS) làm giảm khả năng dùng lại token bị sao chép bằng cách yêu cầu bằng chứng sở hữu khóa/chứng chỉ. Tuy vậy, **không được log token**: khóa/proof có thể bị lộ cùng môi trường, dữ liệu có thể chứa thông tin nhạy cảm và telemetry không phải nơi giữ credentials.

### 2.1. Phân loại những dữ liệu cần giữ kín

| Dữ liệu | Nguy cơ | Chính sách |
|---|---|---|
| **Access token JWT** | Bearer credential; payload JWS có thể lộ `sub`, `aud`, `scope`, tenant/role. | Không ghi token nguyên vẹn hoặc một phần tùy tiện. |
| **Access token opaque** | Bí mật dùng để tra trạng thái hoặc truy cập API. | Không ghi dù chuỗi trông vô nghĩa. |
| **Refresh token** | Có thể xin access token mới; thường sống lâu hơn access token. | Không ghi request/response token endpoint. |
| **OIDC ID token** | Chứa bằng chứng xác thực và có thể có dữ liệu danh tính. | Không ghi; không dùng thay access token của API. |
| **Authorization code** | Có thể bị lạm dụng trong thời gian ngắn nếu điều kiện bảo vệ bị phá. | Không ghi callback query hoặc response `Location`. |
| **Session cookie / API key** | Có thể chiếm phiên hoặc xác thực ứng dụng. | Không ghi `Cookie`, `Set-Cookie` hay API key. |
| **Client secret / private key / PKCE verifier** | Bí mật xác thực hoặc ràng buộc luồng. | Không ghi vào logs, traces, test output. |
| **DPoP proof và recovery code** | Dữ liệu xác thực/proof có thể bị lạm dụng. | Không ghi giá trị thô. |

Tình trạng “token đã hết hạn” không đủ để kết luận nó an toàn cho log: token vẫn có thể tiết lộ thông tin nội bộ/người dùng, tồn tại trong backup lâu dài hoặc bị nhầm trong một validator lỗi.

## 3. Mô hình nơi token bị sao chép

~~~mermaid
flowchart LR
    C[Client có Bearer token] --> G[API Gateway]
    G --> API[Resource Server]
    API --> AUTH[Token Validation]
    AUTH -->|Exception chứa request| LOG[Application Logger]
    AUTH -->|Auto recordException| SPAN[OpenTelemetry / APM]
    G -. Header hoặc URL capture .-> COL[Telemetry Collector]
    LOG --> COL
    SPAN --> COL
    COL --> STORE[(Log / Trace Storage)]
    STORE --> VIEW[Dashboard / Export / Alert]
    VIEW -. Lộ token .-> A[Người có token]
    A --> API
~~~

Một token có thể bị ghi trước khi ứng dụng xử lý request, chẳng hạn tại reverse proxy hoặc gateway; hoặc sau khi app trả lỗi, chẳng hạn tại HTTP client, agent, collector hay error reporting SaaS.

**Ba lớp phòng vệ:**

1. **Tại nguồn**: không đưa credential vào log statements, exception, span attributes, body/URL capture và baggage.
2. **Trong pipeline**: agent/collector lọc hoặc loại trường nhạy cảm trước export, bảo vệ đường truyền telemetry.
3. **Tại kho lưu**: RBAC, retention, mã hóa, audit, kiểm soát export và ứng cứu.

Redaction chỉ trên **dashboard** là không đủ, vì storage, backup hoặc API export vẫn có thể chứa giá trị gốc.

## 4. Các đường rò phổ biến cần kiểm kê

| Nguồn | Ví dụ không an toàn | Cách phòng |
|---|---|---|
| **Request logging** | `headers=... Authorization: Bearer ...` | Không capture header bí mật; dùng allowlist. |
| **Response logging** | JSON của `/token` có `access_token`/`refresh_token` | Không capture body của endpoint token/auth. |
| **OAuth redirect logging** | `Location: /callback?code=...` | Không ghi Location/query nhạy cảm. |
| **Exception message** | `"Invalid token " + token` | Error code cố định, không nhúng token. |
| **Stack trace/cause** | HTTP client exception ghi URL có query/headers | Kiểm nguồn exception, không tự log throwable chưa scrub. |
| **Wire/debug logging** | Reactor Netty, Feign, OkHttp hoặc Apache HttpClient ghi request | Không bật capture thô cho credentials. |
| **Gateway access log** | Log raw request URI có `?access_token=...` | Bỏ query, dùng route/template đã chuẩn hóa. |
| **APM/tracing** | `url.full`, `exception.message`, `http.request.header.authorization` | Cấm attributes/events nhạy cảm và kiểm exporter. |
| **MDC/log context** | `MDC.put("token", rawToken)` | Chỉ dùng trace/request ID và error code an toàn. |
| **W3C Baggage** | Truyền `access_token` giữa microservices | Không mang bí mật qua baggage. |
| **DTO `toString()`** | Log nguyên token response/principal | Không serialize security DTO vào log. |
| **HTTP error body** | Trả `ex.getMessage()` | Trả thông báo cố định và correlation ID. |
| **Crash/heap dump** | Dump chứa token trong bộ nhớ | Hạn chế tạo, truyền, lưu, quyền xem và retention. |
| **CI và báo cáo lỗi** | In biến môi trường/token test hoặc ticket | Dùng canary giả, không gửi secret thật. |

**Bẫy thường gặp:** app đã redact header `Authorization` nhưng gateway vẫn ghi toàn bộ query; app không log JWT nhưng thư viện HTTP tự đính kèm request snapshot vào exception; console đã sạch nhưng APM ghi `exception.stacktrace` có token.

## 5. Chọn không thu thập, redact hay fingerprint

| Biện pháp | Hành vi | Mức phù hợp |
|---|---|---|
| **Không thu thập** | Không đưa token/header/body vào object log/span. | **Ưu tiên cao nhất.** |
| **Redact tại nguồn** | Trường nhạy cảm được bỏ hoặc thay `[REDACTED]` trước khi xuất. | Hữu ích nếu bắt buộc giữ cấu trúc sự kiện. |
| **Mask một phần** | Giữ vài ký tự đầu/cuối token. | Thường **không nên** với bearer token. |
| **Hash không khóa** | Ghi digest để liên kết token. | Có rủi ro nếu token entropy thấp và có thể bị liên kết. |
| **HMAC fingerprint** | HMAC với khóa audit độc lập, lưu mã rút gọn. | Chỉ khi cần correlation/security analytics và có kiểm soát. |
| **Scrub ở collector** | Loại credential trước khi export backend. | Phòng vệ bổ sung, không thay kiểm ở nguồn. |
| **Che ở dashboard** | Người xem UI không thấy token nhưng storage vẫn có. | **Không đủ** để ngăn rò. |

**Regex tìm JWT ba phần không đủ**: opaque token có thể không có dấu chấm; token có thể URL-encoded, JSON-escaped, trong cookie, payload nested, exception hoặc chuỗi riêng của provider.

Ưu tiên **lọc theo nguồn và tên trường**, xác định allowlist metadata, sau đó mới dùng pattern detection như lưới phòng vệ cuối.

### 5.1. Không log substring token

Một vài ký tự của token có thể làm tăng khả năng liên kết người dùng/phiên hoặc lộ metadata; dùng substring còn khuyến khích code phụ thuộc raw token. Khi cần xác định một token cho mục đích điều tra, hãy cân nhắc fingerprint được bảo vệ thay vì `token.substring(...)`.

### 5.2. HMAC fingerprint dùng khi thật cần

Ví dụ mô hình:

~~~text
auditFingerprint = first128bits(
    HMAC_SHA256(dedicatedAuditKey, rawAccessToken)
)
~~~

Các điều kiện:

- Khóa HMAC **riêng cho audit**, không dùng JWT signing key, client secret hoặc khóa mã hóa khác.
- Quản lý khóa qua secret manager; có rotation và giới hạn truy cập.
- Chỉ xuất vào **security audit stream** phù hợp, không vào mọi log/span.
- Xét nhu cầu retention và khả năng liên kết cross-service/cross-environment.
- Không ghi đồng thời fingerprint và raw token; khi không cần fingerprint thì bỏ.

HMAC fingerprint **không thay** việc bảo vệ token và không phải claim JWT/chuẩn OAuth bắt buộc.

## 6. Logging theo allowlist thay vì log raw request

Một bản ghi lỗi xác thực có thể như sau:

~~~json
{
  "timestamp": "2026-11-23T02:00:00Z",
  "service": "orders-api",
  "event": "authentication_denied",
  "http_method": "GET",
  "http_route": "/orders/{orderId}",
  "http_status": 401,
  "auth_error_code": "invalid_token",
  "trace_id": "b7d9f1225a6e4c7ab30d2189444b5f60"
}
~~~

Không có access token, header, query string, JWT claims hoặc exception message. Chỉ lưu trace ID với định dạng hợp lệ và provenance đáng tin; không dùng token làm correlation ID.

| Trường nên cân nhắc ghi | Ràng buộc |
|---|---|
| `service`, `environment` | Giá trị cấu hình cố định, không chứa secret. |
| `http.method` | Method HTTP, không gồm body. |
| `http.route` | **Route template** như `/orders/{id}`, không raw path/query. |
| `http.status_code` | Mã kết quả, không phải response body. |
| `auth.result` | Enum `success`, `denied`, `error`. |
| `auth.error_code` | Mã lỗi chuẩn hóa, không là `exception.getMessage()`. |
| `trace_id`, `span_id` | ID trace hợp lệ; không chứa secret hoặc dữ liệu nhận dạng. |
| `duration_ms` | Độ trễ; không tiết lộ credential. |

Một số metadata như `sub`, tenant, role, scope có thể là thông tin cá nhân/nội bộ. Chỉ lưu khi **có mục đích audit rõ** và quyền truy cập, retention thích hợp. Không log toàn bộ claims dù JWT đã được xác minh.

## 7. Trường HTTP phải ngăn thu thập

### 7.1. Headers nhạy cảm

Danh sách tối thiểu, so khớp tên header **không phân biệt hoa/thường**:

~~~text
Authorization
Proxy-Authorization
Cookie
Set-Cookie
X-API-Key
X-Auth-Token
X-Access-Token
X-Refresh-Token
DPoP
Custom credential headers according to application contracts
~~~

Không serialize nguyên header map rồi hi vọng regex lọc hết. Header có thể có nhiều giá trị hoặc được proxy gộp.

### 7.2. Request/response fields nhạy cảm

~~~text
access_token
refresh_token
id_token
code
code_verifier
client_secret
client_assertion
password
api_key
token
session
assertion
recovery_code
signed URL parameters
~~~

Danh sách cần mở rộng theo sản phẩm. Những trường này có thể nằm ở query, form body, JSON nested, token endpoint response hoặc redirect `Location`.

**OAuth authorization code trong callback URL** cũng cần bảo vệ, dù chưa phải access token. `Location`, `Set-Cookie` và body của token endpoint là những đường rò quan trọng phía response.

### 7.3. Trường tracing đáng chú ý

~~~text
http.request.header.authorization
http.response.header.set_cookie
url.full
url.query
http.request.body
http.response.body
exception.message
exception.stacktrace
error.message
messaging.message.payload
rpc.request.metadata
baggage values
~~~

Tên thuộc tính cụ thể có thể khác theo phiên bản OpenTelemetry và SDK/agent. **Phải kiểm dữ liệu thực sự được export**, không dựa vào giả định cấu hình mặc định an toàn.

## 8. Exception thường làm lộ token như thế nào?

Một exception có thể chứa raw token hoặc URL trong `message`, `cause`, request snapshot hoặc stack trace.

Ví dụ xấu:

~~~java
String bearer = request.getHeader("Authorization");
throw new IllegalArgumentException("Invalid credential " + bearer);
~~~

Sau đó:

~~~java
log.error("Authentication failed", exception);
span.recordException(exception);
problem.setDetail(exception.getMessage());
~~~

Ba đường đều có thể đưa token tới các nơi khác nhau: log, trace và HTTP response. Một số agent tự record exception **ngay cả khi ứng dụng không gọi `span.recordException` trực tiếp**.

**Quy tắc an toàn:**

1. Exception bảo mật mang **mã lỗi cố định** như `INVALID_ACCESS_TOKEN`, không chứa raw credential.
2. Không ghép request headers, raw URL có query, request/response body hoặc access token vào exception constructor.
3. Không log `ex.getMessage()`, `ex.toString()` hoặc raw throwable chưa đánh giá nguồn.
4. Không trả exception message trực tiếp cho client.
5. Khi cần stack trace, dùng **kênh debug riêng có sanitizer và giới hạn quyền**, không tự động đẩy tất cả throwable vào mọi sink.
6. Thông báo lỗi từ thư viện hoặc upstream là **dữ liệu chưa đáng tin để ghi**; có thể chứa request snapshot.

### 8.1. Mã lỗi có ích hơn token trong log

Ví dụ bảng phân loại:

| Mã | Điều kiện | HTTP thường dùng | Metadata chẩn đoán |
|---|---|---|---|
| `AUTH_TOKEN_MISSING` | Không có bearer token bắt buộc | 401 | Route/status/trace ID |
| `AUTH_TOKEN_INVALID` | Token lỗi chữ ký, issuer, audience, format, hết hạn | 401 | Error code chung |
| `AUTH_SCOPE_INSUFFICIENT` | Token hợp lệ nhưng thiếu scope | 403 | Error code, route |
| `AUTH_RESOURCE_DENIED` | Không có quyền trên resource hoặc tenant | 403 hoặc 404 | Policy decision code |
| `AUTH_BACKEND_UNAVAILABLE` | Introspection/policy dependency lỗi | Theo fail-closed policy | Dependency name đã biết, duration |
| `INTERNAL_ERROR` | Lỗi ngoài dự đoán | 500 | Exception class, trace ID; không raw message |

Đừng đưa thông tin token bị từ chối vào `error_description` của `WWW-Authenticate`. Nếu cần giải thích cho client, dùng câu ngắn **cố định**.

## 9. Spring Boot: trả response lỗi an toàn

Ví dụ Spring MVC dùng `ProblemDetail`. Đây là đoạn code minh họa, cần tích hợp phù hợp phiên bản framework:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class SafeErrorHandler {
    private static final Logger LOG =
        LoggerFactory.getLogger(SafeErrorHandler.class);

    @ExceptionHandler(Exception.class)
    public ResponseEntity<ProblemDetail> handleUnexpected(Exception ex) {
        String traceId = MDC.get("traceId");

        // Không ghi ex.getMessage(), ex.toString(), hay raw throwable.
        LOG.error(
            "request_failed category=internal_error type={} trace_id={}",
            ex.getClass().getSimpleName(),
            traceId
        );

        ProblemDetail result =
            ProblemDetail.forStatus(HttpStatus.INTERNAL_SERVER_ERROR);
        result.setTitle("Internal server error");
        result.setDetail("Request could not be completed");
        if (traceId != null) {
            result.setProperty("traceId", traceId);
        }
        return ResponseEntity
            .status(HttpStatus.INTERNAL_SERVER_ERROR)
            .body(result);
    }
}
~~~

Điểm quan trọng:

- Response chỉ chứa thông báo chung/trace ID, không phản ánh bearer token.
- Logger chỉ ghi exception **class**, không ghi message/stack có thể chứa URL/header/token.
- `MDC.get("traceId")` chỉ hoạt động khi tracing/MDC được cấu hình; kiểm provenance/format trước khi công bố ra ngoài.
- Đây không phải exception handler đầy đủ cho production; cần các case lỗi ứng dụng, HTTP status và mã nội bộ riêng.
- **`@RestControllerAdvice` không thay thế `AuthenticationEntryPoint` hoặc `AccessDeniedHandler` của Spring Security filter chain**, nơi nhiều lỗi access token phát sinh trước controller.

Ví dụ HTTP challenge cho **token không hợp lệ**:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api", error="invalid_token"
Cache-Control: no-store
Content-Type: application/problem+json

{
  "type": "about:blank",
  "title": "Unauthorized",
  "status": 401,
  "detail": "Access token is invalid or expired."
}
~~~

Theo RFC 6750, challenge khi **thiếu token** không nhất thiết có `error="invalid_token"`; khi token hợp lệ nhưng thiếu scope, có thể dùng `403` với `insufficient_scope`. Tùy tình huống, vẫn phải tuân thủ quy tắc OAuth Bearer. **Không echo token hoặc raw exception vào challenge/body**.
## 10. Spring: audit HTTP request mà không đọc bearer token

Thay vì bật log mọi HTTP header/body, có thể ghi một sự kiện **tối thiểu**. Ví dụ `OncePerRequestFilter`:

~~~java
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.web.filter.OncePerRequestFilter;
import org.springframework.web.servlet.HandlerMapping;

public final class SafeHttpAuditFilter extends OncePerRequestFilter {
    private static final Logger LOG =
        LoggerFactory.getLogger(SafeHttpAuditFilter.class);

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {
        try {
            chain.doFilter(request, response);
        } finally {
            Object mapping = request.getAttribute(
                HandlerMapping.BEST_MATCHING_PATTERN_ATTRIBUTE
            );
            String route = mapping instanceof String
                ? (String) mapping : "unmatched";

            LOG.info(
                "http_request method={} route={} status={}",
                request.getMethod(),
                route,
                response.getStatus()
            );
        }
    }
}
~~~

Mẫu này **không truy cập** `Authorization`, cookies, raw query string hoặc request body. Với request bị từ chối trước controller, route mapping có thể không tồn tại; dùng `unmatched` cố định thay vì raw path. Khi triển khai thật phải xử lý order của filter, async/error dispatch, correlation IDs và status cuối cùng theo framework.

**Các lệnh nên tránh:**

~~~java
LOG.info("headers={}", allRequestHeaders);
LOG.info("authorization={}", request.getHeader("Authorization"));
LOG.info("url={}", request.getRequestURL());
LOG.info("query={}", request.getQueryString());
LOG.info("body={}", rawRequestBody);
LOG.info("authentication={}", securityContext.getAuthentication());
~~~

`Authentication.toString()`, request/response DTO và các lớp tạo tự động `toString()` có thể chứa credentials hoặc dữ liệu nhạy cảm tùy cách viết và thư viện. Không tự giả định các phương thức đó an toàn.

### 10.1. Gateway và HTTP client phải có cùng chính sách

Trong một hệ thống có nginx/reverse proxy, API gateway, Spring WebClient, RestClient, Feign, OkHttp hoặc Apache HttpClient, cần kiểm cả:

- Access logs tại gateway có ghi raw URI/query hay headers không?
- Wire/debug logging của HTTP client có ghi request/response body không?
- Token endpoint trả JSON access/refresh token có bị client logging capture không?
- Redirect `Location` có chứa authorization code hoặc sensitive query không?
- Exception của HTTP client có bao gồm URL, headers, response body hoặc request snapshot không?
- Có auto-generated report gửi lên APM/SaaS lỗi mà chưa scrub không?

Không thể coi việc ứng dụng có `SafeHttpAuditFilter` là đủ nếu **gateway đã ghi Authorization trước đó**. Việc bật DEBUG tạm thời trong production cũng cần trải qua chính sách bảo mật và kế hoạch tắt/kiểm tra dữ liệu.

## 11. OpenTelemetry: span attributes và events

Distributed tracing nối các request qua nhiều service bằng trace context. Một span có thể chứa attributes, events, status description và dữ liệu exception tự động được instrumentation ghi. Nếu các trường đó chứa bearer token, token bị nhân bản sang tracing backend.

Ví dụ **không an toàn**:

~~~java
Span span = Span.current();
span.setAttribute(
    "http.request.header.authorization",
    request.getHeader("Authorization")
);
span.setAttribute("user.access_token", accessToken);
span.recordException(exception);
span.setStatus(StatusCode.ERROR, exception.getMessage());
~~~

Ví dụ **an toàn hơn**:

~~~java
import io.opentelemetry.api.trace.Span;
import io.opentelemetry.api.trace.StatusCode;

public final class SafeSecurityTrace {
    private SafeSecurityTrace() {}

    public static void recordInvalidToken() {
        Span span = Span.current();
        span.setAttribute("auth.validation.result", "invalid");
        span.setAttribute("auth.error.code", "invalid_token");
        span.addEvent("authentication_denied");
        span.setStatus(StatusCode.ERROR, "AUTHENTICATION_DENIED");
    }
}
~~~

Các custom attributes `auth.validation.result` và `auth.error.code` trong ví dụ là **tên minh họa do hệ thống tự chọn**, không phải trường bắt buộc của OpenTelemetry Semantic Conventions.

### 11.1. Vì sao `recordException(ex)` cần kiểm soát?

Tùy SDK/config, `recordException` có thể tạo event với `exception.type`, `exception.message` và `exception.stacktrace`. Nếu thông báo hoặc cause của exception chứa URL với `code`, bearer token hoặc response body của token endpoint, dữ liệu đó có thể được xuất. Một agent có thể tự capture exception mà code ứng dụng không gọi hàm này.

Với lỗi xác thực đã dự kiến, mã lỗi cố định và trạng thái thường đủ để vận hành. Khi cần stack trace, phải chọn cơ chế debug an toàn, sanitize theo nguồn, giới hạn quyền xem và tránh tự động đẩy throwable chưa kiểm vào span.

### 11.2. `url.full` so với `http.route`

`url.full` và raw path có thể chứa query hoặc token trong route. Ví dụ:

~~~text
GET /oauth/callback?code=CANARY_AUTH_CODE
GET /download?access_token=CANARY_ACCESS
GET /reset/CANARY_RESET_TOKEN
~~~

Trong telemetry, nên dùng `http.route` dạng template như `/oauth/callback` hoặc `/reset/{token}` thay vì raw URL. Đồng thời cần **sửa API không chở bearer token trong URL** khi có thể. Chỉ dùng sampling thấp không giải quyết được vấn đề: một trace có token vẫn có thể được export.

### 11.3. W3C Trace Context và Baggage

| Cơ chế | Mục đích | Không được làm |
|---|---|---|
| `traceparent` | Truyền trace ID/span relationship. | Dùng token làm trace ID hoặc user credential. |
| `tracestate` | Truyền trace vendor context theo chuẩn. | Giấu access token/client secret vào giá trị. |
| `baggage` | Truyền metadata dạng key–value giữa dịch vụ. | Đưa token, cookie, email, thông tin nhạy cảm. |

Baggage có thể theo request đến nhiều service và bị instrumentation ghi nhận ở nơi không dự kiến. Để gọi service khác thay mặt người dùng, cần access token **đúng audience** hoặc cơ chế delegated authorization/token exchange, không chuyển credential trong baggage.

### 11.4. Cẩn trọng với cấu hình capture headers

Một số Java agent và HTTP instrumentation cho phép liệt kê headers được ghi vào span. Danh sách cần được kiểm soát chặt và **không chứa** `Authorization`, `Cookie`, `Set-Cookie`, `Proxy-Authorization`, `DPoP` hoặc custom token headers.

Không giả định cấu hình mặc định của agent hiện nay mãi an toàn ở mọi phiên bản. Hãy kiểm **payload span sau exporter/collector**, bao gồm attributes, events và status descriptions.

## 12. Chính sách telemetry thống nhất

Một policy **mang tính mô tả** có thể như sau; nó **không phải cú pháp nạp trực tiếp** của Spring hay OpenTelemetry Collector:

~~~yaml
observabilitySecurityPolicy:
  default: deny_sensitive_data

  applicationLogs:
    allowFields:
      - timestamp
      - service
      - environment
      - event
      - http.method
      - http.route
      - http.status_code
      - auth.error_code
      - trace_id
      - duration_ms
    forbiddenSources:
      - raw_request_headers
      - raw_response_headers
      - raw_request_body
      - raw_response_body
      - raw_query_string
      - throwable_message
      - throwable_stacktrace

  traces:
    allowedCustomAttributes:
      - auth.validation.result
      - auth.error.code
    forbiddenAttributes:
      - http.request.header.authorization
      - http.response.header.set_cookie
      - url.query
      - token
      - exception.message
      - exception.stacktrace
    captureRawBodies: false
    captureCredentials: false

  pipeline:
    scrubBeforeExport: true
    restrictReaders: true
    retention: minimum_required
    alertOnCanaryCredentials: true
~~~

**Lớp kiểm soát cần đồng thời tồn tại:**

1. Application không tạo log/span chứa token.
2. Agent/instrumentation không thu thập header, body, exception nhạy cảm.
3. Collector scrub/drop trường nhạy cảm trước export, bổ sung secret detection.
4. Telemetry backend có RBAC, retention, encryption và audit truy cập/export.
5. Regression tests khẳng định **không còn token ở từng sink**.

Collector scrub chỉ là **defense in depth**, vì token có thể đã nằm trong application log file, agent buffer, local crash dump hoặc hệ thống bên thứ ba khác trước khi collector xử lý.

### 12.1. Cách xử lý dữ liệu thô khi không thể tránh

Nếu một component được giao cấu trúc header/JSON để audit, không serialize toàn bộ rồi dùng regex mơ hồ. Áp chính sách **theo key và allowlist**:

~~~text
for each field in structuredInput:
    normalizedName = lowerCase(field.name)
    if normalizedName in sensitiveNames:
        omit or replace with "[REDACTED]"
    else if normalizedName in approvedAllowlist:
        emit validatedNonSecret(field.value)
    else:
        omit
~~~

Header names HTTP không phân biệt hoa/thường. Chú ý giá trị lặp, JSON nested, query URL-encoded, signed URL và tên secret riêng của hệ thống. `Authorization` thường nên **bỏ hẳn khỏi telemetry**, thay vì thêm placeholder.

Regex nhận dạng JWT có thể hỗ trợ kiểm tra cuối pipeline nhưng không phát hiện đáng tin tất cả opaque, refresh token, custom credentials hoặc chuỗi được encode.

## 13. Kiểm thử bảo mật bằng canary token

Sử dụng **giá trị giả có thể tìm kiếm**, không dùng token thật. Tiêm nó qua các đường có thể rò, sau đó kiểm logs, trace exporter, gateway, collector và APM.

Ví dụ Spring Boot Test (cần điều chỉnh URL/bean và bảo mật của dự án):

~~~java
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.system.CapturedOutput;
import org.springframework.boot.test.system.OutputCaptureExtension;
import org.springframework.test.web.servlet.MockMvc;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@ExtendWith(OutputCaptureExtension.class)
class TokenRedactionTest {
    private static final String CANARY =
        "CANARY_BEARER_NEVER_LOG_6D2E3A";

    @Autowired
    MockMvc mvc;

    @Test
    void invalidBearerIsNotPrinted(CapturedOutput output) throws Exception {
        mvc.perform(get("/orders")
                .header("Authorization", "Bearer " + CANARY))
            .andExpect(status().isUnauthorized());

        assertThat(output.getAll()).doesNotContain(CANARY);
    }
}
~~~

Test trên chỉ kiểm **output được Spring Boot OutputCaptureExtension bắt được**, không tự bao phủ file logs, gateway, trace exporter hay SaaS APM. Không được kết luận toàn hệ thống an toàn chỉ từ test này.

### 13.1. Ma trận test canary

| Đường đưa canary | Đích quan sát cần kiểm | Kỳ vọng |
|---|---|---|
| `Authorization: Bearer CANARY_ACCESS` | App/gateway logs, spans, alerts | Không chứa canary |
| Header viết kiểu `aUtHoRiZaTiOn` | Header scrubber | Không chứa canary |
| `Cookie: session=CANARY_COOKIE` | Request logs và capture | Không chứa canary |
| Response `Set-Cookie` chứa canary | Response tracing/logging | Không chứa canary |
| `?access_token=CANARY_QUERY` | Access log, `url.full` và APM | Không chứa canary |
| OAuth callback `?code=CANARY_CODE` | Redirect/callback logs | Không chứa canary |
| JSON `refresh_token=CANARY_REFRESH` | Token endpoint body capture | Không chứa canary |
| Exception message chứa canary | App log, trace exception event, error SaaS | Không chứa canary |
| HTTP client exception có URL/header canary | Outbound logs và traces | Không chứa canary |
| Baggage chứa canary | Downstream spans/telemetry | Không chứa canary |
| JWT giả có `sub`/email nhạy cảm | Log claims và trace | Không in raw JWT/claim nhạy cảm |
| Secret được URL-encode/JSON-escape | Collector và parser | Không chứa secret sau xử lý |

**Kiểm thử dương tính:** sau khi bảo vệ credential, logs vẫn có mã lỗi, HTTP status, service, route template và trace ID để điều tra. Đừng xóa sạch mọi dấu vết chẩn đoán.

### 13.2. Kiểm trace thực tế

Có thể dùng in-memory span exporter trong test hoặc backend observability dành riêng cho staging, rồi duyệt:

- Span attributes.
- Span events và `exception.message`/`exception.stacktrace`.
- Status description và resource attributes.
- Kênh truyền Baggage qua service.
- Dữ liệu sau export/collector, không chỉ object `Span` trước export.

Nếu hệ thống dùng third-party APM, cần xác minh SDK/agent đang bật chế độ nào và các bản sao/export thực tế có còn canary không.

## 14. Bảo vệ telemetry qua nhiều service

Chuỗi ứng dụng điển hình:

~~~mermaid
sequenceDiagram
    autonumber
    participant C as Browser / Client
    participant G as API Gateway
    participant O as Orders API
    participant P as Payments Client/API
    participant T as Telemetry Backend
    C->>G: Bearer access token
    G->>G: Kiểm/log metadata; không log token
    G->>O: Forward request theo trust policy
    O->>O: Xác minh token, scope, audience, tenant
    O->>P: Gọi service bằng token đúng audience
    P-->>O: Kết quả hoặc lỗi đã phân loại
    O-->>G: Response an toàn
    G-->>C: Response
    G-->>T: Metadata log không credential
    O-->>T: Span/event mã lỗi và route template
    P-->>T: Telemetry không raw secret
~~~

Các trách nhiệm:

- Gateway **không ghi** bearer header/query, và không tin `X-User-Id` do client ngoài tự gửi.
- Orders API xác minh token, không log JWT payload/raw claims.
- HTTP client không ghi outbound Authorization, request/response body hoặc URL query.
- Payments API không nhận token dành riêng cho Orders API chỉ vì chúng cùng issuer; mỗi RS kiểm audience.
- Collector và backend quan sát xử lý dữ liệu tối thiểu, có RBAC và retention.

**Sampling không phải redaction.** Một trace được lấy mẫu vẫn có thể chứa token; ngay cả ở sampling 1%, nếu token bị ghi thì đó vẫn là lỗ hổng.

## 15. Xử lý sự cố token đã bị lộ trong log hoặc trace

Nếu phát hiện bearer token thật trong telemetry, xem đó là **credential exposure**.

### 15.1. Thứ tự xử lý

1. **Ngăn ghi tiếp:** tắt header/body capture nguy hiểm, sửa exception logging/tracing và chặn export nhạy cảm.
2. **Khoanh vùng:** token loại nào, phát hành khi nào, còn hiệu lực không, những sink nào đã nhận (gateway, app logs, collector, APM, dashboard, alert, export, backup).
3. **Giới hạn lạm dụng:** revoke token/phiên/grant khi hỗ trợ; thu hồi refresh token; rotate API key/client secret khi bị lộ; yêu cầu đăng nhập lại nếu cần.
4. **Điều tra:** sử dụng metadata, audit access và dấu hiệu token reuse bất thường; không sao chép raw token sang ticket hay log khác.
5. **Hạn chế dữ liệu tồn dư:** khóa truy cập không cần thiết, xử lý xóa/redact các bản sao và retention theo chính sách vận hành/pháp lý.
6. **Ngăn tái diễn:** thêm canary tests, kiểm tất cả agent và thay đổi quy trình review code.

### 15.2. Các giới hạn phải nắm

- Một access JWT còn hạn có thể vẫn được RS xác minh cục bộ chấp nhận đến `exp` nếu không có denylist/state check; revoke refresh token **không tự thu hồi** access JWT cũ.
- Opaque token có thể bị đánh dấu inactive sớm, nhưng cache introspection tại RS/gateway có thể trì hoãn hiệu lực.
- Log đã lưu trong backup hoặc exported SaaS không nhất thiết xóa ngay được; phải đánh giá đường dữ liệu cụ thể.
- Token bị lộ **không đồng nghĩa signing key đã lộ**. Không tự động rotate khóa ký JWT khi chỉ lộ một bearer access token; rotation khóa cần căn cứ và chính sách riêng.
- Xóa token khỏi log không chứng minh token chưa từng bị lạm dụng trước đó.

## 16. Lỗi triển khai thường gặp

| Sai lầm | Hậu quả | Cách phòng |
|---|---|---|
| `log.error("...", ex)` với exception có token | Stack/message chứa secret | Không log raw throwable chưa kiểm; mã lỗi cố định, debug có sanitizer |
| Log raw Authorization để so token | Credential lưu dài hạn | Không ghi; HMAC fingerprint có kiểm soát khi cần |
| Regex chỉ tìm JWT ba phần | Không bắt opaque/custom/encoded tokens | Field/path allowlist và ngăn ở nguồn |
| Mask token trên dashboard | Storage vẫn có token thật | Scrub trước xuất và bỏ capture ở app/agent |
| Đưa bearer vào MDC | Secret tự lan sang nhiều dòng log | MDC chỉ chứa correlation metadata |
| Dùng `span.recordException` tùy tiện | Exception event chứa message/stack | Chọn event/status mã lỗi, kiểm agent |
| Dùng `url.full` và raw path | OAuth code/token/signed URL trong trace | Route template, bỏ query và raw secret path |
| Truyền token bằng baggage | Bí mật lan qua nhiều service | Auth header đúng mục đích hoặc token exchange |
| Bật body capture tại `/token` | Lộ access/refresh token | Tắt body capture, kiểm response |
| Log nguyên `Authentication`/DTO | Có thể in credentials và PII | Structured log trường an toàn |
| Dùng sampling thay redaction | Trace được chọn vẫn có secret | Redact ngay cả sampling 100% |
| Chỉ app có redaction, gateway không | Header/query bị ghi trước app | Kiểm từng hop/collector/sink |
| Trả `ex.getMessage()` trong `401` | Lộ token cho caller | Error/challenge tĩnh theo OAuth |
| Không xử lý các bản copy | Token còn trong alert, export và backup | Inventory/retention/incident response |

## 17. Bài tập thực hành

### Bài 1 — Sửa đoạn code dễ rò token

~~~java
try {
    tokenValidator.validate(bearer);
} catch (Exception ex) {
    log.warn("Bad JWT: " + bearer, ex);
    span.recordException(ex);
    return ResponseEntity
        .status(401)
        .body(Map.of("error", ex.getMessage()));
}
~~~

Hãy tìm các lỗi:

1. `bearer` được ghi trực tiếp.
2. `ex` có thể mang request/token trong stack hoặc message.
3. `span.recordException(ex)` có thể đưa secret vào trace.
4. `ex.getMessage()` có thể bị trả cho client.
5. APM tự capture exception có thể tạo bản sao ngoài logger.

**Cách sửa:** xác minh token theo profile, trả `invalid_token` và thông báo chung, log mã lỗi và trace ID, không ghi token hoặc raw throwable; kiểm cả Spring Security entry point và tracing agent.

### Bài 2 — Thiết kế test ma trận

Giả sử hệ thống dùng Spring Boot, OTel Java Agent, gateway và third-party APM. Hãy tạo canary khác nhau cho:

- JWT và opaque access tokens.
- Refresh token, ID token, session cookie.
- OAuth callback với `code` trong query.
- Upstream exception chứa header và request body.
- Span event/`exception.message`/status description.
- W3C Baggage, HTTP client wire logs.
- Error response, gateway access log, alert notification.
- Trường mixed-case và URL-encoded.

Kiểm ở **từng sink cuối cùng**, không chỉ console. Đồng thời giữ được trace ID, error code, HTTP status và route template.

### Bài 3 — Thiết kế response cho sai audience

Orders API nhận token hợp lệ về chữ ký nhưng `aud=payments-api`. Viết:

1. `401` với Bearer challenge phù hợp, không echo token.
2. Body lỗi cố định.
3. Log `auth.error_code=invalid_token`, `http.route=/orders/{id}` và trace ID.
4. Trace event `authentication_denied`, không có JWT payload.
5. Test canary chứng minh token không xuất hiện trong HTTP response, logs, spans, APM.

### Bài 4 — Incident response

Một APM đã ghi refresh token thật trong exception message suốt nhiều giờ. Hãy viết playbook: ngăn capture, xác định bản sao, thu hồi token/phiên, tìm reuse, hạn chế truy cập APM, xử lý retention/backup, và thêm regression tests. Không gửi raw refresh token vào ticket xử lý sự cố.

## 18. Checklist triển khai

- [ ] Phân loại access/refresh/ID token, authorization code, session cookie, client secret, DPoP proof và PKCE verifier là dữ liệu nhạy cảm.
- [ ] App không log raw Authorization, Cookie, Set-Cookie, token body hoặc query chứa bí mật.
- [ ] Exception auth dùng error code cố định; không đưa raw request/header/body vào message/cause.
- [ ] Spring Security entry point và Spring MVC exception handler không trả nguyên exception/token.
- [ ] Gateway, reverse proxy, HTTP clients và debug logging không capture headers/body nhạy cảm.
- [ ] OpenTelemetry spans/events/status không chứa token, raw URL/query, exception message/stack chưa kiểm hoặc baggage nhạy cảm.
- [ ] Logging schema dùng allowlist metadata gồm service, route template, HTTP status, error code và trace ID.
- [ ] Nếu cần fingerprint, dùng HMAC/audit key riêng, quyền truy cập và retention rõ ràng.
- [ ] Collector scrub/drop như defense in depth; storage có RBAC, encryption, retention và audit.
- [ ] Canary tests chạy qua app logs, gateway, exporter, APM và alert sink.
- [ ] JWT/opaque vẫn được RS kiểm issuer, audience, expiry, scope, trạng thái và permission độc lập với telemetry.
- [ ] Có quy trình revoke/rotate credential và xử lý bản sao khi phát hiện leak.
- [ ] Sampling và dashboard masking không được coi là redaction đầy đủ.
- [ ] Khi dependency lỗi, hệ thống fail closed về bảo mật nhưng vẫn cung cấp mã lỗi/trace ID để điều tra.

**Ghi nhớ:** bearer token là **bí mật có thể bị sử dụng lại**, không phải dữ liệu debug. Cách phòng tốt nhất là **không thu thập token ngay từ nguồn**. Nếu cần log/trace, hãy dùng **mã lỗi, route template, HTTP status và trace ID**, không dùng bearer header, raw URL/body, exception message hoặc stack trace chưa kiểm. Redaction chỉ thành công khi token không lọt vào **ứng dụng, gateway, span, collector, APM và bản export**.

### Tài liệu chuẩn để tra cứu

- **RFC 6750 — OAuth 2.0 Bearer Token Usage:** đặc tính bearer và Bearer challenge (`invalid_token`, `insufficient_scope`).
- **RFC 9700 — Best Current Practice for OAuth 2.0 Security:** bảo vệ token và giảm lạm dụng.
- **RFC 7519 — JSON Web Token (JWT):** claims và khả năng lộ dữ liệu.
- **RFC 7662 — OAuth 2.0 Token Introspection:** trạng thái access token opaque.
- **RFC 7009 — OAuth 2.0 Token Revocation:** thu hồi token.
- **RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP):** sender-constrained tokens.
- **OpenID Connect Core 1.0:** ID token, authorization code và xác thực.
- **OWASP Logging Cheat Sheet:** dữ liệu không nên ghi, sanitization và bảo vệ log.
- **OWASP Secrets Management Cheat Sheet:** quản lý và bảo vệ bí mật.
- **OpenTelemetry Documentation / Semantic Conventions:** HTTP attributes, span events, exception telemetry và instrumentation.
- **W3C Trace Context và W3C Baggage:** truyền ngữ cảnh giữa dịch vụ.
- **Spring Security OAuth2 Resource Server / Spring Boot Actuator:** bearer authentication, Micrometer observation và telemetry.

