# Kiểm soát lỗi trả về, header bảo mật và thông tin triển khai bị lộ

## 1. Mục tiêu: một cổng vào an toàn không tiết lộ cấu trúc bên trong

Trong module **SPRING_CLOUD_GATEWAY**, Gateway chọn route bằng predicate, chạy filter chain, sửa đường dẫn/header, tìm microservice qua discovery/load balancing và thực thi những chính sách như xác thực, rate limiting, circuit breaker, retry, TLS và observability. Khi vận hành, các chức năng đó có thể tạo ra nhiều kiểu HTTP response: một số từ Gateway, một số từ Spring Security, số khác đến từ backend. Không phải mọi response đều đã được bảo vệ theo cùng một cách.

Ví dụ một client gọi:

~~~http
GET /api/orders/42 HTTP/1.1
Host: api.example.test
Authorization: Bearer test-token
~~~

Khi service không sẵn sàng, một response **không nên** tiết lộ:

~~~http
HTTP/1.1 500 Internal Server Error
Server: ReactorNetty/1.x
X-Upstream-Host: orders-7f68d9cc58-4xg2b.internal:8081
Content-Type: text/plain

java.net.ConnectException: Connection refused:
connect to orders-7f68d9cc58-4xg2b.internal/10.42.5.31:8081
at reactor.netty.http.client.HttpClientConnect...
~~~

Đây là **phản ví dụ**: tên Pod, IP nội bộ, implementation class, phiên bản server và stack trace không phải thông tin cần đưa tới người dùng. Nếu Gateway chuyển nguyên error body của backend, thông điệp SQL, hostname, exception hoặc token cũng có thể bị lộ tương tự.

Mục tiêu tốt hơn là:

~~~http
HTTP/1.1 503 Service Unavailable
Content-Type: application/problem+json
Cache-Control: no-store
X-Content-Type-Options: nosniff

{
  "type": "https://api.example.test/problems/upstream-unavailable",
  "title": "Service temporarily unavailable",
  "status": 503,
  "detail": "Please try again later.",
  "code": "UPSTREAM_UNAVAILABLE"
}
~~~

Response trên chỉ là **contract minh họa**. Spring Cloud Gateway không tự động biến mọi connection error thành chính xác body/status trên. Để có contract này cần xử lý exception, error serialization hoặc response policy có chủ đích; status phải đúng với fault thật và không được sửa bừa.

Bài **“Kiểm soát lỗi trả về, header bảo mật và thông tin triển khai bị lộ”**, thuộc chương **Gia cố bảo mật**, tập trung vào ba đầu việc:

1. **Kiểm soát lỗi**: phân biệt lỗi routing, security, upstream HTTP response, timeout và application exception; trả status/body phù hợp, không lộ stack trace.
2. **Gia cố response headers**: HSTS, CSP, X-Content-Type-Options, clickjacking, Referrer-Policy, caching, CORS, cookies; tránh header thiếu hoặc chồng lặp.
3. **Chặn rò rỉ triển khai**: server fingerprints, internal hostname/port/IP, debug headers, absolute redirects, Actuator, logs/traces và dữ liệu cá nhân.

Sau bài học, bạn có thể thiết kế hợp đồng lỗi, cấu hình các filter/hệ thống security ở đúng tầng, kiểm tra response từ Gateway và backend bằng HTTP integration tests, và lập checklist triển khai an toàn.

> **Phạm vi:** ví dụ chính cho **Spring Cloud Gateway Server WebFlux** dùng Spring Security reactive, Reactor Netty và Spring Boot hiện đại. Gateway Server Web MVC và Proxy Exchange MVC chạy stack khác; khái niệm an toàn vẫn áp dụng nhưng không dùng nguyên `GlobalFilter`/`WebFilter`/`SecurityWebFilterChain` trong ứng dụng Servlet.

## 2. Threat model: client biết được gì qua HTTP response?

Những loại thông tin có thể vô tình bị tiết lộ:

| Nhóm | Ví dụ | Hậu quả tiềm năng |
| --- | --- | --- |
| Framework/server | `Server: nginx/1.xx`, `X-Powered-By`, framework/version banners | Giúp fingerprint hệ thống, lựa chọn exploit phù hợp |
| Hạ tầng nội bộ | `orders.default.svc.cluster.local`, private IP, container/pod ID, upstream port | Lộ topology, tên services và địa chỉ quản trị |
| Runtime exception | Java class name, stack trace, file/classpath, Netty SSL error | Lộ implementation và trạng thái hạ tầng |
| Database | SQL statement, table names, JDBC URL, migration errors | Lộ schema/chi tiết dữ liệu |
| Xác thực | JWT/session tokens, cookie, signing metadata, OAuth code, login exception | Credential leak và account enumeration |
| Ủy quyền | Phân biệt 403/404 theo object không được phép | Dò sự tồn tại của tài nguyên |
| Service discovery | Route IDs, service registry instance IDs, environment tags | Lộ nội bộ microservices |
| Debug/metrics | Actuator env, configprops, heapdump, gateway routes, health details | Truy cập secrets/cấu hình và thay đổi routes nếu quyền quá rộng |
| Headers từ backend | `X-Backend-Server`, `X-Trace-Debug`, `Via`, internal `Location` | Lộ route/path và backend identity |
| Headers do client tự đưa | `Forwarded`, `X-Forwarded-Host`, `X-Debug` | Host poisoning hoặc spoofing nếu xử lý sai |
| Error body từ backend | Validation raw DTO, PII, payload echo | Tiết lộ dữ liệu nhạy cảm ngoài contract |

**Không phải mọi giá trị `Server` hay route ID đều là lỗ hổng nghiêm trọng**, và xóa một banner không thể vá một CVE. Nhưng trong chiến lược defense-in-depth, client chỉ nên nhận **dữ liệu thuộc public API contract**.

### 2.1. Ba miền tin cậy

~~~mermaid
flowchart LR
    C["Public client<br/>không tin cậy"] --> I["CDN/Ingress<br/>edge policy"]
    I --> G["Spring Cloud Gateway<br/>routing + security"]
    G --> O["Backend services<br/>upstream HTTP"]
    G --> M["Management plane<br/>private access"]
~~~

- Client có thể tự đặt Host, Origin, Forwarded, query, body và nhiều request headers.
- Edge proxy phải sanitize forwarded headers và không để client bypass đường trusted.
- Gateway phải enforce authentication/authorization, route allowlist, error/header policy.
- Backend không được mặc định tin mọi caller và cũng phải ẩn lỗi nghiệp vụ/secret.
- Management plane nên tách network/access control khỏi public data plane.

## 3. Một status code có nhiều nguồn phát sinh

HTTP 404/500/503 mà client thấy không nói rõ **ai** đã tạo nó.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant S as Spring Security
    participant G as Gateway filters/router
    participant U as Backend
    C->>S: GET /api/orders/42
    alt Không đủ quyền
        S-->>C: 401 hoặc 403
    else Không match route
        S->>G: request đã qua security
        G-->>C: 404 hoặc custom no-route response
    else Có route
        S->>G: authorized request
        G->>U: forwarded HTTP request
        alt Backend trả HTTP 422/503
            U-->>G: status + body + headers
            G-->>C: HTTP response được proxy/biến đổi theo policy
        else Connect/TLS/timeout trước khi nhận response
            G-->>C: Gateway/framework error handler
        end
    end
~~~

### 3.1. Bảng phân loại theo nguồn

| Tình huống | Nơi quyết định | Không nên làm |
| --- | --- | --- |
| 401 thiếu token | Spring Security entry point | Đổi thành 200 + HTML login trên API thuần JWT không có contract |
| 403 thiếu scope/quyền | Authorization layer | Trả chi tiết nội bộ về policy/role map |
| 404 không khớp route | Gateway/WebFlux handler mapping | Kết luận ngay là backend không có resource |
| 404 backend resource không tồn tại | Backend | Thay bừa thành 500 |
| 400/422 body sai schema | Backend hoặc request validation | Dump raw body, class/SQL error |
| 429 quota hết | RequestRateLimiter/edge | Retry tự động rồi tạo tải lớn hơn |
| 502/503/504 network/resilience | Gateway, ingress, load balancer, custom error handling | Khẳng định mọi `ConnectException` có một status mặc định cho mọi release |
| 503 backend trả | Backend HTTP response | Gọi là lỗi kết nối nếu upstream thực sự trả HTTP |
| 500 exception của Gateway filter | Reactive error chain | Lộ stack trace trong body |
| 200 từ circuit breaker fallback | Fallback policy | Để client tưởng thao tác ghi đã hoàn tất khi chưa có chứng cứ |

**Phân biệt status từ Gateway và status từ upstream** bằng recorded upstream request, route ID, trace/log metadata đã redact và error category; không suy đoán chỉ từ status.

### 3.2. 404 không khớp route khác 404 upstream

~~~text
GET /unknown
  -> không match route -> Gateway/WebFlux 404
  -> upstream requests = 0

GET /api/orders/999
  -> match orders-api, gọi /orders/999
  -> upstream trả 404
  -> upstream requests = 1
~~~

Hai response có thể có cùng status, nhưng logging, problem code và alerting nên phân biệt. Một biến thể công khai có thể cố ý thống nhất body để không tiết lộ tồn tại resource; hệ thống quan sát nội bộ vẫn phải nhận diện được nguồn.

### 3.3. Retry, circuit breaker và lỗi đứt kết nối

Nếu route có `Retry` và backend trả `503` ở lần đầu, client có thể chỉ thấy status cuối `200` sau retry. Nếu CircuitBreaker trả fallback, client có thể thấy `200` dù **backend chưa được gọi**. Vì thế không dùng mỗi HTTP 200 để xác nhận business side effect; riêng POST/payment cần idempotency, hậu kiểm và mã trạng thái phản ánh kết quả thực tế.

Với timeout/connection reset, response có thể đã gửi một phần. Khi response đã commit, Gateway **không thể đáng tin cậy thay toàn bộ body bằng Problem Details**; cần xử lý streaming/cancellation/transport error riêng.

## 4. Định nghĩa hợp đồng lỗi public tối thiểu

Một API contract tốt thường gồm:

- **HTTP status đúng** ngữ nghĩa.
- Một mã lỗi ổn định do hệ thống định nghĩa.
- Thông điệp an toàn, đủ để client biết cách xử lý, không nêu hostname, stack trace hoặc cấu hình.
- `Content-Type` phù hợp, có thể dùng RFC 9457 `application/problem+json`.
- Correlation/tracing ID tùy chính sách, không chứa PII và không dùng làm quyền.
- `Cache-Control: no-store` khi response nhạy cảm hoặc liên quan xác thực.
- `Retry-After` khi 429/503 cần và có chính sách rõ; không phát giá trị vô căn cứ.

### 4.1. Ví dụ RFC 9457 Problem Details

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/problem+json
Cache-Control: no-store

{
  "type": "https://api.example.test/problems/invalid-request",
  "title": "Invalid request",
  "status": 400,
  "detail": "One or more fields are invalid.",
  "code": "INVALID_REQUEST"
}
~~~

RFC 9457 chuẩn hóa những trường như `type`, `title`, `status`, `detail`, `instance`. `code` là **extension field do ứng dụng định nghĩa**, không phải trường bắt buộc của RFC. Không truyền raw validation object có password/token hoặc thông báo SQL thành `detail`.

### 4.2. Mã lỗi có thể khác status

| HTTP status | `code` gợi ý | Detail an toàn |
| --- | --- | --- |
| 400 | `INVALID_REQUEST` | Request format is invalid |
| 401 | `AUTHENTICATION_REQUIRED` | Authentication is required |
| 403 | `ACCESS_DENIED` | Access is denied |
| 404 | `RESOURCE_NOT_FOUND` | Resource not found |
| 405 | `METHOD_NOT_ALLOWED` | HTTP method not supported |
| 413 | `PAYLOAD_TOO_LARGE` | Request body exceeds allowed size |
| 429 | `RATE_LIMITED` | Too many requests |
| 502 | `BAD_GATEWAY` | Upstream response unavailable |
| 503 | `SERVICE_UNAVAILABLE` | Service temporarily unavailable |
| 504 | `GATEWAY_TIMEOUT` | Upstream request timed out |
| 500 | `INTERNAL_ERROR` | Unexpected server error |

Đây là **gợi ý thiết kế**, không phải bảng tự động của Spring Cloud Gateway. Status phải được ánh xạ dựa trên **exception và upstream semantics thật**, không gom mọi exception thành `503`.

### 4.3. Khi nào cần che cả 403/404?

Một số API không muốn client chưa đủ quyền biết đối tượng có tồn tại. Khi đó chính sách **404 thay cho 403** có thể phù hợp ở tầng authorization nghiệp vụ, nhưng:

- Phải áp dụng nhất quán, tránh enumeration qua sự khác biệt latency/body/headers.
- Không làm logs nội bộ mất nguyên nhân thực (403 vs 404).
- Không dùng mọi 404 để ngụy trang lỗi 500.
- Kiểm contract public với nhóm bảo mật và product.
- Cần rate limiting và ngăn brute-force kể cả khi body được làm giống nhau.

## 5. Spring Boot WebFlux error handling và các tùy chọn ẩn lỗi

Spring Boot có error handler cho WebFlux. Trên các release Boot 3.5, thuộc tính `server.error.*` có thể kiểm soát mức chi tiết đưa ra response; những default quan trọng là **không bao gồm message/stack trace**.

### 5.1. Một baseline production cho Spring Boot 3.5

~~~yaml
server:
  error:
    include-message: never
    include-stacktrace: never
    include-exception: false
    include-binding-errors: never
    include-path: never
~~~

**Giải thích:**

- `include-message: never` tránh trả thông báo exception thô.
- `include-stacktrace: never` tránh lộ stack trace.
- `include-exception: false` tránh đưa tên class exception vào response.
- `include-binding-errors: never` tránh trả binding errors chi tiết có thể chứa dữ liệu nhạy cảm.
- `include-path: never` giảm rò rỉ raw request path trong error document, nhất là đường dẫn chứa ID/token.
- Các property này **không bắt upstream 500 response phải đi qua error handler của Boot**. Một backend tự trả JSON chứa stack trace vẫn có thể được Gateway proxy nguyên body.
- `never`/`false` không có nghĩa mọi custom `@ExceptionHandler`, Gateway response filter, ingress error page đều tự trở nên an toàn.

Spring Boot 3.5 property docs xác nhận các default: `include-message=never`, `include-stacktrace=never`, `include-exception=false`, `include-binding-errors=never`; `include-path` mặc định có thể là `always`, nên môi trường muốn ẩn path có thể đặt `never` rõ ràng.

### 5.2. Hạn chế các lựa chọn `always` và `on-param`

Một số cấu hình dev sử dụng:

~~~yaml
# PHẢN VÍ DỤ: không triển khai production.
server:
  error:
    include-stacktrace: always
    include-message: always
~~~

Hoặc `on-param` cho phép query parameter của request ảnh hưởng mức chi tiết lỗi, làm lộ dữ liệu cho client không tin cậy nếu không có lớp kiểm soát khác. Chỉ sử dụng thông tin debug ở môi trường phát triển cô lập, không dựa vào một URL query để bật raw exception ở API public.

### 5.3. Spring Boot 4.x và property migration

Boot 4.x có thay đổi cấu trúc auto-configuration và một số property namespaces; xác nhận bằng **versioned common application properties** của release đang chạy. Ví dụ trong bài dùng Boot 3.5 để phân tích cụ thể và không khẳng định mọi tên/behavior sẽ nguyên vẹn ở Boot 4.x.

## 6. RFC 9457 và phạm vi hỗ trợ trong WebFlux

Spring WebFlux có `ProblemDetail` và hỗ trợ `application/problem+json`. Spring Boot cung cấp property `spring.webflux.problemdetails.enabled` để bật khả năng hỗ trợ được tài liệu mô tả trong những release tương ứng.

~~~yaml
spring:
  webflux:
    problemdetails:
      enabled: true
~~~

**Những điều quan trọng:**

1. Bật property **không đảm bảo mọi 4xx/5xx từ upstream được convert thành Problem Details**.
2. `ProblemDetail` áp dụng tốt cho lỗi do **application WebFlux/controller** xử lý.
3. Lỗi ở Netty routing, load balancing, Gateway filter hoặc Spring Security entry point có thể đi qua **những pipeline khác**.
4. Muốn chuẩn hóa mọi response status/body, cần xác định **nguồn lỗi** và cách can thiệp cụ thể ở mỗi tầng.
5. `instance` thường có thể là path request; nếu path chứa dữ liệu nhạy cảm, cần sanitize hoặc bỏ field theo contract.
6. Nếu upstream đã trả `application/problem+json` hợp lệ, không nhất thiết rewrite lại toàn bộ body: tránh mất semantics và overhead.

### 6.1. Handler lỗi cho một controller nội bộ

Ví dụ một controller địa phương thuộc **ứng dụng Gateway WebFlux** muốn trả lỗi 400 mà không lộ exception message:

~~~java
package example.gateway.security;

public class InvalidOrderInputException extends RuntimeException {
    public InvalidOrderInputException(String internalDetail) {
        super(internalDetail);
    }
}
~~~

~~~java
package example.gateway.security;

import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class LocalControllerProblemAdvice {

    @ExceptionHandler(InvalidOrderInputException.class)
    public ProblemDetail invalidOrderInput(InvalidOrderInputException ex) {
        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                HttpStatus.BAD_REQUEST,
                "The supplied order input is invalid.");

        problem.setTitle("Invalid request");
        problem.setType(java.net.URI.create(
                "https://api.example.test/problems/invalid-request"));
        problem.setProperty("code", "INVALID_ORDER_INPUT");
        return problem;
    }
}
~~~

Ở đây, nội dung `internalDetail` được giữ để phân loại/log có redaction phù hợp ở server, **không được copy sang client**. `@RestControllerAdvice` chỉ giải quyết những exception thuộc phạm vi annotated controllers; **không tự bắt mọi HTTP 503 từ backend hoặc mọi lỗi trong Gateway routing filter**.

### 6.2. ErrorWebExceptionHandler cho lỗi ngoài controller

Với WebFlux, có các điểm mở rộng như:

- `ErrorAttributes` để kiểm soát dữ liệu error.
- `ErrorWebExceptionHandler` / `AbstractErrorWebExceptionHandler` để thay đổi cách serialization và status.
- `WebExceptionHandler` cho exception handling theo order/contract.
- Spring Security `ServerAuthenticationEntryPoint` và `ServerAccessDeniedHandler` cho các response 401/403.

Khi triển khai custom handler phải đặc biệt chú ý:

- Order so với Boot default handler và Spring Security filters.
- Response đã commit hay chưa.
- Content negotiation (JSON/HTML).
- `Mono<Void>` và blocking IO trong reactive handler.
- Bảo toàn status 400/404/429 vs 500.
- Không ghi đè nội dung upstream đã trả thành công hoặc body đã streaming.
- Không log JWT/cookie/SQL query dù error handler nhận được exception gốc.

**Không gắn một exception class name vào response chỉ để thuận tiện debugging**. Sử dụng một mã lỗi chuẩn hóa và trace/correlation ID có policy; details kỹ thuật ở hệ thống logging nội bộ.

## 7. Gateway route filters có phạm vi khác WebFilter và Spring Security

### 7.1. Ba loại hook

| Hook | Hoạt động ở đâu? | Điều cần chú ý |
| --- | --- | --- |
| `GatewayFilter` / `GlobalFilter` | Gateway filter chain **khi đã match route** | Không tự chạy cho no-route 404 hoặc auth bị chặn trước route |
| `WebFilter` | WebFlux HTTP request processing | Có thể bảo vệ routes không thuộc Gateway, tùy ordering và chain |
| Spring Security `SecurityWebFilterChain` | AuthN/AuthZ, CSRF và HTTP headers | Response 401/403 có thể được tạo trước Gateway route |

Do đó cấu hình chỉ ở `default-filters` của Gateway **không bảo đảm** headers có trong những response do Spring Security hay WebFlux tạo trước route match.

Ví dụ:

~~~text
GET /api/orders/42 + token hợp lệ
  -> route match -> SecureHeaders / RemoveResponseHeader có thể chạy

GET /api/orders/42 + token không hợp lệ
  -> Security trả 401 trước route -> Gateway route filters có thể không chạy

GET /no-such-route
  -> WebFlux 404 -> không có Gateway route filters
~~~

Nếu cần HSTS/X-Content-Type-Options và caching policy cho **tất cả public responses**, đặt chúng ở **edge proxy hoặc Spring Security/WebFilter** phù hợp rồi test đầy đủ, thay vì cho rằng một route filter bao phủ mọi trường hợp.

### 7.2. Spring Security headers không thay policy upstream

Spring Security có các header writers bảo vệ response do Gateway tạo hoặc đi qua chain, nhưng không tự xóa raw error body do upstream trả. Nó cũng không thay backend authorization hoặc việc xử lý redirect Location nội bộ.

## 8. Security headers: mỗi header có mục đích riêng

| Header | Mục đích | Ghi chú triển khai |
| --- | --- | --- |
| `Strict-Transport-Security` | Browser ưu tiên HTTPS cho origin | Chỉ có ý nghĩa trên HTTPS công khai; cẩn thận includeSubDomains/preload |
| `X-Content-Type-Options: nosniff` | Hạn chế MIME sniffing | Luôn trả Content-Type đúng |
| `Content-Security-Policy` | Giới hạn nguồn script/style/frame và các tính năng liên quan | Phụ thuộc loại HTML/UI; không có CSP tốt cho mọi app |
| `X-Frame-Options: DENY` | Chống frame/clickjacking cho UA hỗ trợ | `frame-ancestors` trong CSP linh hoạt hơn |
| `Referrer-Policy` | Kiểm dữ liệu URL đi trong Referer | `no-referrer` nghiêm ngặt, `strict-origin-when-cross-origin` là lựa chọn khác |
| `Cache-Control: no-store` | Ngăn lưu response nhạy cảm ở caches | Không áp đặt cho assets public có caching contract |
| `Pragma`, `Expires` | Tương thích với caching clients cũ | Không thay `Cache-Control` chính |
| `Permissions-Policy` | Hạn chế browser features (camera, location…) | Browser support/directives thay đổi |
| `Cross-Origin-Opener-Policy` | Cô lập browsing context khi cần | Có thể phá OAuth popups/flows nếu đặt bừa |
| `Cross-Origin-Resource-Policy` | Kiểm cross-origin embedding của resources | Dễ ảnh hưởng asset delivery |
| `X-Download-Options` | Cơ chế legacy ở một số browsers | Không thay MIME/content disposition |
| `X-Permitted-Cross-Domain-Policies` | Legacy Adobe cross-domain policy | Chỉ có tác dụng với client liên quan |
| `X-XSS-Protection` | Browser XSS auditor legacy | Không thay CSP; giá trị `1; mode=block` không còn khuyến nghị phổ quát |
| `Access-Control-Allow-Origin` | Browser CORS | **Không là authentication**, không dùng wildcard với credentials |

### 8.1. HSTS phải được quyết định ở HTTPS edge

~~~http
Strict-Transport-Security: max-age=31536000
~~~

HSTS chỉ được browser tiếp nhận từ **HTTPS đáng tin cậy**. Nếu TLS terminate ở CDN/ingress nhưng Gateway chỉ thấy HTTP nội bộ, Spring Security có thể không tự thêm HSTS theo request scheme; hãy kiểm nơi TLS public kết thúc và trusted forwarded handling.

**Đừng bật ngay**:

~~~http
Strict-Transport-Security: max-age=31536000; includeSubDomains; preload
~~~

trên một domain chưa bảo đảm mọi subdomain đều hỗ trợ HTTPS lâu dài. `includeSubDomains` và `preload` có tác động rộng và khó hoàn tác; cần domain-owner approval, kế hoạch rollout và các điều kiện của preload list.

### 8.2. CSP phải phù hợp frontend

Một API chỉ trả JSON có thể dùng CSP hạn chế nếu nó đồng thời phục vụ tài liệu/HTML, nhưng **CSP chủ yếu được browser thực thi khi tài liệu được tải**, không phải một tường lửa cho toàn JSON API.

Ví dụ policy chặt cho trang nội bộ không cần script từ ngoài:

~~~http
Content-Security-Policy: default-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'
~~~

Với SPA/CDN, policy phải cho phép đúng script hashes/nonces/hosts cần thiết. Không chỉ copy một CSP mặc định cho route dùng Swagger UI hoặc OAuth callback rồi xem đã hardening: trang có thể hỏng chức năng.

Chạy `Content-Security-Policy-Report-Only` trong giai đoạn đánh giá nếu cần, sau đó chuyển sang enforcement khi đã giải quyết violations. CSP báo cáo cũng có thể chứa URL nhạy cảm, cần lọc dữ liệu và rate limiting reporting endpoint.

### 8.3. X-XSS-Protection không phải lớp bảo vệ hiện đại

Một số bản `SecureHeaders` của Gateway còn có default legacy:

~~~http
X-XSS-Protection: 1; mode=block
~~~

Nhiều trình duyệt hiện đại đã bỏ XSS auditor, và Spring Security hiện đại có thể dùng `X-XSS-Protection: 0`. Đừng để hai hệ thống cùng đặt hai giá trị mâu thuẫn. Ưu tiên escape output, validation, CSP phù hợp và bảo vệ dữ liệu thay vì trông cậy vào header legacy này.

### 8.4. Không để response nhạy cảm bị cache

Một API trả thông tin tài khoản hoặc lỗi đăng nhập nên cân nhắc:

~~~http
Cache-Control: no-store
Pragma: no-cache
~~~

Nhưng route phục vụ public assets có thể cần caching tích cực. Chính sách cache nên tách theo route/resource type, authentication và dữ liệu. `no-cache` có nghĩa là cần revalidation, **không đồng nghĩa `no-store`**. Với `Vary: Authorization/Cookie` và shared caches, cần hiểu chuẩn HTTP cache, không lấy một response policy chung để giấu lỗi bảo mật.

## 9. Gateway SecureHeaders filter và giới hạn của nó

Spring Cloud Gateway Server WebFlux có `SecureHeaders` GatewayFilter factory. Nó tạo một nhóm security response headers và cho phép tùy chỉnh/bỏ một số header theo release.

### 9.1. Ví dụ trên route WebFlux 5.x

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: orders-api
              uri: http://localhost:8081
              predicates:
                - Path=/api/orders/**
              filters:
                - StripPrefix=1
                - SecureHeaders
~~~

Đây là **route-specific filter**. Với Gateway 4.x namespace cũ, routes thường đặt ở `spring.cloud.gateway.routes`. Tên `SecureHeaders` có ở cả các dòng tài liệu tương ứng, nhưng default headers/custom properties phải kiểm version.

### 9.2. Những default không nhất thiết phù hợp mọi môi trường

Theo tài liệu Gateway 5.x, những headers thuộc bộ mặc định có thể gồm:

- `X-XSS-Protection`.
- `Strict-Transport-Security`.
- `X-Frame-Options`.
- `X-Content-Type-Options`.
- `Referrer-Policy`.
- `Content-Security-Policy`.
- `X-Download-Options`.
- `X-Permitted-Cross-Domain-Policies`.

**Không xem việc liệt kê là khuyến nghị bật nguyên tất cả giá trị mặc định ở production.** Ví dụ một CSP có `script-src https:` có thể quá rộng cho một SPA cần CSP nghiêm ngặt; `X-XSS-Protection` có thể xung đột với security header writer khác. Gateway 5.x cũng có support `Permissions-Policy` theo tùy chọn.

### 9.3. Tùy chỉnh theo route và property namespace

Ví dụ một route cố ý không dùng `X-XSS-Protection` legacy:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: json-api
              uri: http://localhost:8081
              predicates:
                - Path=/api/json/**
              filters:
                - name: SecureHeaders
                  args:
                    disable: x-xss-protection
~~~

Tên cấu hình `disable` và giá trị lowercase header phải xác nhận theo API của phiên bản Gateway đang chạy; một số release có `enabled-headers`/`disabled-headers` và `default-headers` theo `configprops`. **Không dựa vào một file YAML để kết luận mọi header đã biến mất**, phải kiểm thực tế qua HTTP response.

### 9.4. Vì sao chỉ dùng SecureHeaders chưa đủ?

Nó hoạt động như **GatewayFilter trên route được chọn**, không nhất thiết có tác dụng trên response 401 do Security trả trước route, hoặc error 404 không match route. Nó không tự ẩn stack trace trong error body upstream. Nó cũng không thay security policy của ingress/CDN nơi có thể thêm cùng header một lần nữa.

**Giải pháp:** chọn owner cho mỗi security header (edge, Spring Security hoặc Gateway filter), tránh chồng chéo và test cả success lẫn error/no-route/auth-denied.

## 10. Spring Security WebFlux và response headers cho nhiều loại lỗi

Spring Security WebFlux có các HTTP response header writers mặc định, được tùy chỉnh qua `SecurityWebFilterChain`. Theo tài liệu Spring Security hiện đại, nhóm mặc định gồm caching headers, `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY` và `X-XSS-Protection: 0`; HSTS được thêm trong ngữ cảnh HTTPS thích hợp. **CSP không được tự động áp một chính sách duy nhất** vì từng ứng dụng có nhu cầu HTML/script khác nhau.

~~~http
Cache-Control: no-cache, no-store, max-age=0, must-revalidate
Pragma: no-cache
Expires: 0
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
X-XSS-Protection: 0
~~~

Bộ headers thực tế còn phụ thuộc phiên bản Spring Security, response headers do ứng dụng đặt trước đó, filter order và TLS termination. Không khẳng định danh sách trên luôn hiện đầy đủ cho mọi 401/403 khi một custom filter/ingress đã override chúng.

### 10.1. SecurityWebFilterChain ví dụ cho Gateway JWT Resource Server

Ví dụ sau giả định dự án đã có Spring Security OAuth2 Resource Server dependency và issuer/JWK configuration hợp lệ:

~~~java
package example.gateway.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
public class GatewaySecurityConfiguration {

    @Bean
    SecurityWebFilterChain apiSecurity(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/actuator/health").permitAll()
                        .anyExchange().authenticated())
                .oauth2ResourceServer(oauth -> oauth
                        .jwt(Customizer.withDefaults()))
                .headers(headers -> headers
                        .contentSecurityPolicy(policy -> policy
                                .policyDirectives(
                                    "default-src 'none'; " +
                                    "frame-ancestors 'none'")))
                .build();
    }
}
~~~

Giải thích:

1. `permitAll` đối với health không có nghĩa nên expose các Actuator endpoints khác; quản trị cần network/access policy riêng.
2. `oauth2ResourceServer(jwt)` xác thực bearer JWT, nhưng authorization theo scope/resource ownership phải được khai báo bổ sung đúng nghiệp vụ.
3. Ví dụ CSP `default-src 'none'` có thể hợp với một API chỉ trả JSON, **không hợp** với Gateway đồng thời phục vụ Swagger UI/SPA cần scripts/styles. Đánh giá CSP theo public UI contract.
4. Không dùng `headers.disable()` để chữa “trùng headers” một cách mù quáng: nó loại cả các bảo vệ mặc định có ích.
5. Với browser session/cookie, CSRF protection vẫn là một quyết định cần threat model. Không tắt CSRF cho mọi project chỉ vì Gateway có JWT support.
6. Test headers trên **401/403, no-route 404, upstream 503 và successful 200**, vì chúng có thể đi qua các pipeline khác nhau.

### 10.2. Đặt một owner cho mỗi header

~~~http
Strict-Transport-Security: max-age=31536000
Strict-Transport-Security: max-age=631138519
~~~

Khi CDN, ingress, Security và Gateway `SecureHeaders` cùng đặt HSTS/CSP/CORS, client có thể thấy nhiều giá trị không nhất quán. Với CSP, nhiều policies có thể đồng thời hạn chế resource loading khiến frontend ngừng hoạt động. Với HSTS, một chính sách rộng `includeSubDomains`/`preload` có hậu quả cho cả tổ chức.

| Header | Owner thích hợp theo topology | Lý do |
| --- | --- | --- |
| HSTS | Public TLS edge hoặc app hiểu HTTPS trusted | Chỉ có ý nghĩa ở HTTPS public origin |
| CSP cho HTML | Application/UI owner, qua security review | Cần biết scripts/assets/frame behavior |
| X-Content-Type-Options | Spring Security hoặc edge đã thống nhất | Chính sách chung |
| Frame protection | UI owner hoặc Spring Security | Phụ thuộc embedding |
| Cache-Control cho private API | Backend hoặc Gateway theo route | Phụ thuộc dữ liệu |
| CORS | Một owner chính, backend chỉ theo hợp đồng | Tránh ACAO chồng chéo |
| Server/version banners | Ingress/CDN và server-level config | Có thể sinh sau Gateway filter |
| Debug headers từ backend | Backend + Gateway route/default filters | Không để lọt qua public boundary |

**Public response cuối** qua CDN/ingress mới là kết quả khách hàng nhìn thấy; chỉ test response của Gateway pod bên trong cluster chưa đủ.

## 11. RemoveResponseHeader, SetResponseHeader và WebFilter

Gateway Server WebFlux hỗ trợ:

- `RemoveResponseHeader`: xóa response header theo tên.
- `SetResponseHeader`: ghi đè các giá trị của header cùng tên.
- `AddResponseHeader`: thêm header, có thể tăng số giá trị nếu đã tồn tại.
- `DedupeResponseHeader`: xử lý trùng values theo chiến lược.
- `RewriteLocationResponseHeader`: sửa một số URL trong `Location`, nhưng không tự giải quyết mọi public scheme/prefix.

### 11.1. Gateway Server WebFlux 5.x: default-filters chỉ trên matched routes

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          default-filters:
            - RemoveResponseHeader=X-Powered-By
            - RemoveResponseHeader=X-Backend-Host
            - RemoveResponseHeader=X-Internal-Error
          routes:
            - id: private-orders-api
              uri: http://localhost:8081
              predicates:
                - Path=/api/orders/**
              filters:
                - StripPrefix=1
                - SetResponseHeader=Cache-Control, no-store
~~~

Điểm cần nắm:

1. Gateway 5.x dùng `spring.cloud.gateway.server.webflux.default-filters`, trong khi các nhánh Gateway 4.x namespace cũ thường dùng `spring.cloud.gateway.default-filters`.
2. `default-filters` áp dụng vào **route được match**, không tự chạy trên no-route 404 hoặc 401 bị Spring Security chặn trước routing.
3. `RemoveResponseHeader=X-Powered-By` không kiểm tra nội dung JSON/HTML trả từ backend.
4. `SetResponseHeader=Cache-Control, no-store` phù hợp route private; với assets public cần cache policy khác.
5. Header `Server` có thể được sinh bởi Netty, Nginx hoặc CDN **sau** khi GatewayFilter đã thực hiện; không thể cam kết xóa nó bằng một route filter.
6. Đừng xóa `WWW-Authenticate` của 401 hay `Retry-After` của 429/503 nếu chúng thuộc API contract.
7. Không xóa `Set-Cookie` bừa bãi: một số flows cần session, OAuth state hoặc refresh token cookies, phải đặt attributes chính xác.

### 11.2. Trường hợp cần loại response headers rộng hơn route scope

Ví dụ một `WebFilter` đăng ký callback trước commit:

~~~java
package example.gateway.security;

import org.springframework.core.annotation.Order;
import org.springframework.http.HttpHeaders;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;
import reactor.core.publisher.Mono;

@Component
@Order(-200)
public class ResponseMetadataBoundaryFilter implements WebFilter {

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange, WebFilterChain chain) {

        exchange.getResponse().beforeCommit(() -> {
            HttpHeaders headers = exchange.getResponse().getHeaders();
            headers.remove("X-Powered-By");
            headers.remove("X-Backend-Host");
            headers.remove("X-Internal-Error");
            return Mono.empty();
        });

        return chain.filter(exchange);
    }
}
~~~

Đây là ví dụ **WebFilter**, không phải Gateway `GlobalFilter`. `beforeCommit` giúp loại headers khi response còn sửa được; nó không sửa được response đã commit hoặc header do một proxy bên ngoài thêm về sau.

Một `WebFilter` có thể tham gia những requests không match Gateway route, nhưng vẫn cần integration tests cho error handler và security filter order. `@Order(-200)` chỉ là thứ tự minh họa, không phải thứ tự bắt buộc trong mọi ứng dụng. **Nếu Spring Security và public edge đã có chính sách đầy đủ, ưu tiên cấu hình sẵn có thay vì viết thêm filter trùng nhiệm vụ.**

### 11.3. Xóa header không phải xóa dữ liệu trong body

~~~http
HTTP/1.1 500 Internal Server Error
Content-Type: application/json
X-Backend-Host: orders.svc.cluster.local

{
  "message": "jdbc:postgresql://db-internal:5432/orders",
  "exception": "org.postgresql.util.PSQLException"
}
~~~

Xóa `X-Backend-Host` không thay đổi JSON trong body. Nếu response từ backend có SQL/JDBC URL, server path hoặc stack trace, cần sửa error serialization ở backend hoặc một response rewrite **theo schema có kiểm soát**, không dùng global Regex tự xóa vài từ. Khi rewrite, phải xử lý JSON/HTML/gzip, Content-Length, streaming, HEAD/204/304 và giới hạn bộ nhớ.

## 12. Lỗi HTTP từ upstream cần chính sách riêng

### 12.1. Upstream 500 là một HTTP response, không mặc nhiên là Gateway exception

Backend có thể trả:

~~~json
{
  "exception": "org.postgresql.util.PSQLException",
  "message": "Authentication failed for database admin",
  "node": "orders-7cd9.internal"
}
~~~

Gateway đã nhận được một HTTP response hợp lệ, chỉ là status 500. **`server.error.include-stacktrace=never` đặt trên Gateway không tự khiến body này an toàn**, vì Boot error handler của Gateway có thể không được gọi.

Ba lựa chọn:

| Phương án | Ưu điểm | Cần kiểm |
| --- | --- | --- |
| Backend chuẩn hóa lỗi | Gần domain/exception, giữ status hợp lý | Mọi service thực thi error contract |
| Gateway rewrite body có chọn lọc | Bảo vệ API legacy chưa sửa được | Memory, encoding, retries, 204/HEAD, performance |
| Ingress/service mesh generic error | Chặn một số infrastructure errors | Không hiểu mọi lỗi nghiệp vụ/JSON |

**Ưu tiên để backend trả public error contract an toàn**, còn Gateway làm guardrail cho legacy/boundary.

### 12.2. Không chuyển mọi exception thành 503

~~~text
Upstream 400/422:
  Validation error status phải được giữ theo contract
  Không trả raw DTO chứa password/secret

Upstream 401/403:
  Không lộ nội bộ role/scope mapping
  Vẫn giữ auth semantics

Upstream 500/503:
  Generalize detail, nhưng giữ failure status phù hợp

Gateway DNS/connect/timeout:
  Dùng configured 502/503/504 mapping theo nguồn lỗi
  Không tự khẳng định mọi exception có status mặc định cố định
~~~

Nếu response đã commit một phần, việc biến response thành Problem Details có thể không còn khả thi; network disconnect/streaming error cần cách xử lý riêng.

## 13. CORS, caching và headers thuộc giao thức

### 13.1. DedupeResponseHeader không thay CORS policy

Ví dụ hai tầng cùng ghi:

~~~http
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Allow-Origin: *
Access-Control-Allow-Credentials: true
~~~

Gateway cung cấp `DedupeResponseHeader`:

~~~yaml
filters:
  - DedupeResponseHeader=Access-Control-Allow-Credentials Access-Control-Allow-Origin
~~~

Các strategy có thể là `RETAIN_FIRST`, `RETAIN_LAST` và `RETAIN_UNIQUE`. **Loại trùng không chứng minh giá trị được giữ là an toàn**: khi Gateway giữ `*` với credentials, browser có thể từ chối, và policy có thể mở rộng ngoài ý muốn.

Quy trình:

1. Chọn owner CORS chính.
2. Allowlist origins và methods/headers thật cần.
3. Không dùng `Access-Control-Allow-Origin: *` trên credentialed requests.
4. Xét `Vary: Origin` nếu shared cache có thể lưu response khác nhau theo Origin.
5. Test preflight `OPTIONS` và success/error response.
6. Không dùng CORS làm authentication; curl và non-browser clients vẫn gọi API.

### 13.2. Cache-Control cho tài nguyên nhạy cảm

Một response người dùng đăng nhập:

~~~http
Cache-Control: private, no-store
Vary: Authorization
~~~

khác public static asset:

~~~http
Cache-Control: public, max-age=300
~~~

Không trả `Cache-Control: public` cho user-specific payload hoặc auth failures nếu chưa có cache key/auth partitioning được thiết kế an toàn. `no-cache` chỉ yêu cầu revalidation; **`no-store`** là chỉ dẫn không lưu. Với CDNs, phải kiểm config cache thực tế thay vì chỉ nhìn header trên Gateway.

### 13.3. Những header không được loại bỏ tùy tiện

- `WWW-Authenticate`: thông tin challenge của 401, có thể cần cho OAuth2/Bearer clients.
- `Authorization`: request header, thuộc token relay/service authentication policy; tuyệt đối không phản chiếu vào response/log.
- `Set-Cookie`: session/cookie credentials, cần `Secure`, `HttpOnly`, `SameSite`, `Path`, `Domain`.
- `Retry-After`: dùng cho 429/503 khi có chính sách backoff.
- `Location`: HTTP redirects; cần public hostname/prefix an toàn.
- `Vary` và `ETag`: thuộc caching/content negotiation contract.
- `traceparent`: request trace propagation, không phải credential hoặc rate-limit key.

## 14. Response URL là một nguồn rò rỉ khác body và headers debug

### 14.1. Internal Location

Backend trả:

~~~http
HTTP/1.1 302 Found
Location: http://orders.internal:8081/orders/42
~~~

Client đáng lẽ chỉ thấy:

~~~http
Location: https://api.example.test/platform/api/orders/42
~~~

Một route đã xóa `X-Powered-By` nhưng vẫn trả absolute `Location` tới `orders.internal` **chưa được harden đầy đủ**.

`RewriteLocationResponseHeader` có thể giúp sửa một số thành phần URL, nhưng không mặc nhiên phục hồi đúng toàn bộ `https`, host, port, public path prefix trên mọi topology.

### 14.2. Ba đường dẫn phải có contract riêng

~~~text
Client:     /platform/api/orders/42
Ingress:    /api/orders/42       (strip /platform)
Gateway:    /orders/42           (StripPrefix=1)
Client redirect Location:
            https://api.example.test/platform/api/orders/42
~~~

Nếu Gateway hoặc ingress thêm prefix hai lần, người dùng có thể nhận `/platform/platform/api/...`. Nếu backend tạo relative Location `/orders/42`, browser không tự cộng `/platform/api`.

### 14.3. Untrusted forwarded headers có thể gây host poisoning

~~~http
Forwarded: for=10.0.0.1;proto=http;host=evil.example
X-Forwarded-Host: evil.example
X-Forwarded-Prefix: /admin
~~~

Client có thể tự gửi các headers đó. Chỉ tin metadata từ proxy đã được xác thực và sanitize ở ingress trusted boundary; chặn direct Gateway bypass bằng network ACL. Không dùng `X-Forwarded-Host` từ client làm public base URL OAuth2/reset-password.

### 14.4. Các nguồn URL lộ thông tin khác

- `Link`, `Content-Location`, `Refresh`.
- OAuth2/OIDC `redirect_uri` và logout callback.
- OpenAPI/Swagger `servers`.
- Email reset-password hoặc invitation links.
- JSON `downloadUrl`, pagination URLs.
- Cookie `Domain`, `Path`.
- CORS `Access-Control-Allow-Origin` nếu phản chiếu Origin không kiểm soát.

Kiểm cả **headers lẫn body** trên public entrypoint, không chỉ status.

## 15. Quản trị Actuator ngoài public data plane

### 15.1. Những endpoint cần kiểm soát

Spring Boot Actuator có thể bộc lộ:

| Endpoint | Rủi ro nếu public không kiểm soát |
| --- | --- |
| `health`, `info` | Metadata/service status, discovery details |
| `metrics`, `prometheus` | Traffic, routes, runtime cardinalities |
| `env`, `configprops` | Cấu hình runtime và có thể chứa dữ liệu nhạy cảm |
| `beans`, `conditions`, `mappings` | Nội bộ app structure |
| `loggers` | Thay log level/đọc behavior runtime tùy quyền |
| `heapdump`, `threaddump` | Có thể chứa token, strings, topology/stack data |
| `gateway` | Đọc routes, refresh, tạo/xóa routes tùy access level |
| `logfile` | Access logs có thể chứa PII hoặc secrets |

### 15.2. Baseline management exposure cho Boot 3.5

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info
  endpoint:
    health:
      show-details: never
    gateway:
      access: none
~~~

Ví dụ chỉ mở `health,info` trên HTTP management endpoints. **Nó không tự hạn chế network port, không tự cấu hình SecurityFilterChain, và không thay firewall.**

Nếu cần quan sát Gateway route trên **private management network**:

~~~yaml
management:
  endpoint:
    gateway:
      access: read-only
  endpoints:
    web:
      exposure:
        include: health,info,gateway
~~~

Tài liệu Gateway 5.x khuyến nghị `management.endpoint.gateway.access=read-only` nếu bật actuator gateway endpoint. Quyền `unrestricted` có thể cho phép refresh/create/delete routes, rất nhạy cảm và phải có network+auth controls nghiêm ngặt. Ở một số release `management.endpoint.gateway.enabled=true` cũng có thể ảnh hưởng quyền ghi theo version; kiểm exact behavior và không copy config vô điều kiện.

### 15.3. Health không cần lộ hạ tầng

`show-details: never` hạn chế detail trên health endpoint public. Readiness/liveness cho orchestration có thể dùng internal endpoint riêng; không công bố JDBC/Redis/Eureka hostnames hay raw exceptions cho Internet.

### 15.4. Security testing của Actuator

Kiểm các paths tiêu biểu:

~~~text
/actuator
/actuator/env
/actuator/configprops
/actuator/gateway
/actuator/heapdump
/actuator/loggers
/swagger-ui
/v3/api-docs
/error
~~~

Các path trên là **danh sách cần thử theo deployment**, không khẳng định chúng đều tồn tại. Một 404 public có thể do ingress trả trong khi direct management port vẫn mở; kiểm riêng network bypass.

## 16. Server fingerprints, TLS errors và scope thực sự của HTTP filters

~~~text
Backend -> Gateway/Reactor Netty -> Nginx/Ingress -> CDN -> Browser
~~~

`Server`, `Via`, `X-Powered-By`, `X-Envoy-Upstream-Service-Time` hoặc vendor headers có thể được sinh ở từng hop. Xóa `Server` bằng Gateway route filter không chứng minh CDN/Nginx không thêm lại giá trị. Phải kiểm public responses từ nhiều **nguồn**:

- 200/3xx từ backend.
- 404/5xx do Gateway tạo.
- 401/403 do Spring Security.
- 413/502/503/504 do ingress/CDN.
- Lỗi ở tầng TLS/HTTP2 trước khi request tới Gateway.

Nếu TLS handshake fail trước HTTP thì **không có HTTP response** để WebFilter trả Problem Details, và mọi header cài tại Gateway đều không có cơ hội chạy. Cần TLS/certificate tests riêng.

Ẩn banner giúp giảm fingerprint, **không thay việc vá CVE, cập nhật Spring/Netty và hạn chế public exposure**. Nếu muốn rewrite JSON error body cần xử lý gzip, Content-Length, 204/HEAD/304, streaming, response đã commit và backpressure; không dùng một regex thay chuỗi trên raw bytes.

## 17. Logging, tracing và error diagnostics không được tạo rò rỉ mới

### 17.1. Client response và internal diagnostics cần khác nhau

| Thông tin | Có nên trả client? | Có thể ghi nội bộ? |
| --- | --- | --- |
| HTTP status, public error code | Có | Có |
| Detail an toàn | Có | Có |
| Correlation ID đã validate | Có thể | Có |
| Route ID, retry count, upstream failure category | Thường không | Có, khi cần |
| Internal hostname/IP/Pod ID | Không | Có giới hạn |
| Java exception class/stack trace | Không | Chỉ trong logs an toàn |
| SQL statement/JDBC URL | Không | Hạn chế, không có credentials |
| JWT, refresh token, cookies | Không | **Không log raw**, kể cả DEBUG |
| User payload chứa PII | Không echo | Không dump raw |
| `traceparent`, baggage | Không coi là credential | Theo trust/privacy policy |

Một trace ID giúp đối chiếu requests qua Gateway và services, nhưng **không chứng minh người gọi đã xác thực**. Nếu client tự gửi `traceparent`/`X-Request-Id`, hãy kiểm format/size và có trust boundary, không lấy arbitrary strings gắn vào logs/response header.

### 17.2. Phản ví dụ logging rất nguy hiểm

~~~java
// PHẢN VÍ DỤ: có thể ghi Authorization, cookie và body chứa PII.
log.error("Gateway failed, headers={}, body={}",
        request.getHeaders(), rawRequestBody, exception);
~~~

Một log thiết kế tốt hơn:

~~~text
timestamp=2026-11-24T05:00:00Z
service=edge-gateway
routeId=orders-api
httpMethod=POST
outcome=ERROR
status=503
errorCategory=UPSTREAM_CONNECT
durationMs=155
correlationId=req-demo-42
~~~

Đây là **schema minh họa**, không phải Gateway tự tạo. Khi cần stack trace để điều tra, ghi trong hệ thống operator logs có phân quyền, redact token/PII và retention giới hạn. Không đưa trực tiếp exception message vào public `detail`.

### 17.3. Wiretap và distributed tracing

Bật Reactor Netty wiretap có thể ghi HTTP headers/body tùy log level/format, gây rò rỉ secret. Chỉ bật ở sandbox/traffic synthetic, trong thời hạn ngắn, theo quy trình xử lý dữ liệu.

Micrometer Tracing/OpenTelemetry cho phép tìm hop/latency lỗi, nhưng không tự ẩn `Server`, chuẩn hóa `Location` hay xóa error body. Traces còn có thể chứa raw URL/query, hostname và baggage; áp dụng schema/redaction và giới hạn span attributes.

### 17.4. Metrics không nên có labels từ input tùy ý

Không đưa raw `traceId`, JWT subject, email, request body hoặc `/api/orders/{actual-id}` vào metric labels. Chọn route ID cố định, status/outcome/error category đã giới hạn cardinality để không làm nổ số time series.

## 18. Kiểm thử HTTP qua hai ranh giới: client và mock upstream

### 18.1. Sơ đồ test tích hợp

~~~mermaid
flowchart LR
    T["WebTestClient/curl"] --> G["Gateway WebFlux<br/>RANDOM_PORT"]
    G --> U["MockWebServer/WireMock"]
    U --> R["RecordedRequest: method/path/headers"]
    G --> C["Public response: status/headers/body"]
~~~

Không chỉ test một `GlobalFilter` bằng mock `ServerWebExchange` rồi kết luận public Gateway đã an toàn. Cần test **HTTP outbound thật** tới mock backend, và test **response client thực nhận**.

### 18.2. Ví dụ test status + header + body

Giả sử test đã dựng Gateway với route `/api/orders/**`, mock backend trả `503` với body Problem Details **đã an toàn**, và filter loại `X-Powered-By`/`X-Backend-Host`:

~~~java
// Đoạn assertion minh họa, không phải test class độc lập.
client.get()
        .uri("/api/orders/42")
        .header("Authorization", "Bearer demo-test-token")
        .exchange()
        .expectStatus().isEqualTo(503)
        .expectHeader().doesNotExist("X-Powered-By")
        .expectHeader().doesNotExist("X-Backend-Host")
        .expectHeader().valueEquals(
                "X-Content-Type-Options", "nosniff")
        .expectBody()
        .jsonPath("$.code").isEqualTo("UPSTREAM_UNAVAILABLE")
        .jsonPath("$.trace").doesNotExist()
        .jsonPath("$.exception").doesNotExist();
~~~

Điều kiện cần:

- `client` là `WebTestClient` đã bind tới HTTP server Gateway, không phải bindToController.
- Token test phải được tạo từ test identity provider/JWT fixture phù hợp. Chuỗi `demo-test-token` **không tự là JWT hợp lệ**.
- Mock upstream phải trả JSON `code=UPSTREAM_UNAVAILABLE` hoặc Gateway phải có response rewrite có chủ đích. `RemoveResponseHeader` chỉ xóa headers, không tạo body.
- Test này kiểm hai JSON paths vắng mặt nhưng **chưa đủ** để phát hiện string SQL/internal hostname lẩn trong `detail`.
- Nếu Spring Security tạo 401 **trước khi route match**, `Gateway default-filters` có thể không chạy; đừng dùng test 503 sau auth thành công để kết luận headers 401 cũng đúng.

### 18.3. Mock upstream cố tình tạo các response khác nhau

Một mock upstream nên có khả năng trả:

~~~text
1) HTTP 200 JSON hợp lệ
2) HTTP 404 safe business error
3) HTTP 422 validation error
4) HTTP 503 problem+json an toàn
5) HTTP 500 body legacy chứa stack trace, internal hostname
6) HTTP 302 Location=http://orders.internal:8081/...
7) HTTP 204 No Content
8) HTTP 200 với X-Backend-Host, X-Powered-By, Set-Cookie
9) Slow response, connection reset, truncated body
~~~

Với response (5), test **phải fail** nếu chỉ có `RemoveResponseHeader` mà không có cơ chế bảo vệ body. Đó là một kiểm thử hữu ích, không phải lỗi test fixture.

### 18.4. So sánh upstream request count để xác định nguồn status

~~~text
No JWT:
  -> Security trả 401
  -> upstream request count tăng 0

Insufficient scope:
  -> Security trả 403
  -> upstream request count tăng 0

No matching Gateway route:
  -> WebFlux/Gateway trả 404
  -> upstream request count tăng 0

Route matched, upstream returns HTTP 404:
  -> upstream request count tăng 1
  -> client thấy 404 theo contract

Rate limiter denies:
  -> Gateway trả 429
  -> upstream request count tăng 0

Backend HTTP 503:
  -> upstream request count tăng 1
  -> client thấy 503 nếu Retry/fallback không đổi

Circuit breaker short-circuit:
  -> upstream request count có thể tăng 0
  -> client status/body do fallback policy
~~~

Một test chỉ assert status 404/503 không chỉ ra route có chạy. Recorded requests và trace/route metadata đã redact giúp phân loại nguồn.

## 19. Ma trận test bảo mật response

| ID | Kịch bản | Assertion |
| --- | --- | --- |
| E01 | Không khớp route | Status no-route; không gọi backend; không lộ route table |
| E02 | Backend trả 404 | Đã gọi upstream; status/body hợp đồng |
| E03 | Thiếu token | 401, không gọi backend, `WWW-Authenticate` đúng policy |
| E04 | Token không đủ scope | 403, không lộ principal/role map |
| E05 | JSON sai | 400/422, không echo payload/validation secret |
| E06 | Backend 500 raw stack trace | Client không lộ thông tin đó |
| E07 | Gateway connection refused | Không lộ internal IP/hostname/class name |
| E08 | Backend timeout | Status theo policy, không giả success |
| E09 | Backend 503 + Retry | Attempt count đúng, final status an toàn |
| E10 | CircuitBreaker fallback | Không giả giao dịch ghi hoàn thành |
| E11 | Rate limiter 429 | Không có upstream call, Retry-After nếu contract yêu cầu |
| H01 | Upstream `X-Powered-By` | Public response không có header |
| H02 | Upstream `X-Backend-Host` | Public response không có header |
| H03 | Security trả 401/403 | Có security headers thuộc owner áp dụng |
| H04 | No-route 404 | Có headers do Security/edge/WebFilter bảo vệ |
| H05 | CDN tự trả 502/504 | Không lộ banner/version/internal upstream |
| H06 | CSP/HSTS ở nhiều tầng | Không có giá trị mâu thuẫn |
| H07 | CORS trusted origin | ACAO/credentials/`Vary` đúng |
| H08 | CORS untrusted origin | Không mở quyền ngoài allowlist |
| H09 | Cookie session | Secure/HttpOnly/SameSite/Domain/Path hợp lệ |
| H10 | Redirect Location | Public HTTPS origin, đúng prefix |
| H11 | Client giả Forwarded Host | Không tạo Location tới evil host |
| H12 | Response 204/HEAD | Không có body JSON bị thêm ngoài protocol |
| M01 | Public `/actuator/env` | Không truy cập được |
| M02 | Public `/actuator/gateway` | Không cho đọc/ghi routes trái policy |
| M03 | Public `/actuator/heapdump` | Không truy cập được |
| M04 | `/actuator/health` | Không lộ internal dependency details |
| M05 | OpenAPI docs public | Không chứa internal service hostnames |
| P01 | Gzip/streamed errors | Không corrupt body/compression |
| P02 | Multi-replica | Headers/error schema đồng nhất |
| P03 | Nâng Boot/Cloud/Security | Regression tests còn đúng contract |

**Không gán một mã lỗi cố định cho mọi exception nếu chưa có error-mapping policy của ứng dụng.** Khi error xảy ra ngoài HTTP (TLS handshake), không mong JSON body của Gateway.

## 20. Dùng curl để kiểm public boundary

### 20.1. Kiểm một endpoint hợp lệ

~~~bash
curl -isS 'https://api.example.test/api/orders/42'
~~~

Kiểm `X-Content-Type-Options`, HSTS trên public HTTPS nếu được bật, caching policy, CORS/Content-Type, không có backend debug banners. Nếu endpoint cần JWT và không gửi token, nó có thể trả 401; **không suy thành lỗi route**.

### 20.2. Kiểm response 3xx đầu tiên

~~~bash
curl -isS 'https://api.example.test/api/orders/42/redirect'
~~~

Không thêm `-L` nếu mục tiêu là xem status và `Location` trước khi follow. Một redirect sang `http://orders.internal` vẫn là lỗi dù browser cuối cùng không truy cập được domain nội bộ.

### 20.3. Kiểm thiếu token, token sai và no-route

~~~bash
curl -isS 'https://api.example.test/api/orders/42'

curl -isS \
  -H 'Authorization: Bearer demo-invalid-token' \
  'https://api.example.test/api/orders/42'

curl -isS 'https://api.example.test/no-such-path'
~~~

Kiểm response body/headers không chứa exception, secrets hay implementation details; status cụ thể phụ thuộc security/route policy. Không lưu **token thật** trong shell history.

### 20.4. Kiểm spoofing ở môi trường được phép

~~~bash
curl -isS \
  -H 'Forwarded: proto=http;host=evil.example' \
  -H 'X-Forwarded-Host: evil.example' \
  -H 'X-Forwarded-Prefix: /internal' \
  'https://api.example.test/api/orders/42'
~~~

Kỳ vọng không có `Location` hoặc cookies dùng attacker host/prefix. Edge proxy phải sanitize headers và Gateway không được public bypass entrypoint.

### 20.5. Kiểm management exposure

~~~bash
curl -isS 'https://api.example.test/actuator/env'

curl -isS 'https://api.example.test/actuator/gateway'
~~~

Các endpoints không có mục đích public phải bị chặn. Một 404 từ CDN không chứng minh direct management port đã được firewall; test network riêng.

### 20.6. Kiểm HTTP headers thực sự qua CDN

Security scanner chỉ thấy public response; hãy so:

~~~text
Backend -> Gateway -> Ingress -> CDN -> Client
~~~

- Response thành công qua tất cả hops.
- Security/no-route errors.
- Proxy-generated timeout/413/502/504 ở ingress/CDN.
- HSTS/Server/CSP/CORS duplicates.
- Location, Set-Cookie và cache behavior.

Không coi Gateway pod response là bằng chứng đủ nếu CDN có thể thêm hoặc sửa headers về sau.

## 21. Chẩn đoán một số sai sót thường gặp

| Triệu chứng | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| Client thấy `java.net.ConnectException` | Error handler expose message/stacktrace | `server.error.*` và safe error serialization |
| Client thấy JDBC URL trong 500 | Upstream JSON proxy nguyên body | Backend fix hoặc Gateway rewrite theo schema |
| X-Powered-By vẫn xuất hiện | Do ingress/CDN hoặc route filter không chạy | Kiểm public edge và no-route/401 |
| 401 không có `SecureHeaders` | Security chặn trước route | Spring Security/edge header owner |
| Browser không tải được Swagger | CSP `default-src 'none'` quá nghiêm cho UI | CSP theo resources thực |
| HSTS không xuất hiện | TLS terminate trước Gateway, request nội bộ HTTP | Đặt ở public TLS owner |
| HSTS làm hỏng subdomains | Bật includeSubDomains/preload quá sớm | Rollout/review phạm vi |
| CORS lỗi do nhiều ACAO values | Gateway và backend cùng ghi | Chọn owner; dedupe sau khi validate |
| Browser nhận cookie nhưng không gửi lại | Secure/Domain/Path/SameSite sai | Test browser-facing URL/cookie contract |
| Response 302 trỏ host nội bộ | Backend tạo internal Location | Canonical base URL/rewrite |
| 429 thiếu Retry-After | Filter chưa đặt contract hoặc bị xóa | Bổ sung nếu API cần |
| 401 thiếu WWW-Authenticate | Global header removal sai | Giữ auth protocol |
| 503 bị convert thành 200 | Fallback/SetStatus quá rộng | Sửa error mapping/contract |
| /actuator/gateway public | Endpoint được expose + auth thiếu | Private management/read-only |
| Prometheus metrics có nhiều series | Gắn raw path/traceId vào labels | Low-cardinality tags |
| Dò raw stack trace qua query | Debug `include-stacktrace: on-param` | Dùng `never` production |
| Lỗi chỉ trên một pod | Config drift/version mismatch | Canary rollout, config diff |
| TLS error không có JSON body | Thất bại trước HTTP | Test certificate/protocol layer riêng |

## 22. Quy trình thay đổi chính sách an toàn

1. **Khảo sát:** xác định các route public/private, auth modes, backend error schemas, proxy hops và Actuator exposure.
2. **Phân loại:** thống kê no-route, security, upstream 4xx/5xx, connect/timeout, fallback.
3. **Thiết kế contract:** status, public code, detail, safe headers, cache/CORS/cookies, Location.
4. **Chỉ định owner:** CDN/ingress, Spring Security, Gateway route filters, backend.
5. **Cấu hình:** ẩn message/stack trace, loại debug headers, áp CSP/HSTS phù hợp, chặn quản trị.
6. **Kiểm thử:** mock upstream và client assertions cho cả success/error; spoof Host/Forwarded; test 401/no-route.
7. **Đánh giá hiệu năng:** body rewrite error không làm bùng bộ nhớ; không bật full body logging.
8. **Canary:** rollout một replica/path, kiểm status 401/403/404/429/5xx, frontend/SSO/cookie flows.
9. **Giám sát:** metrics lỗi theo route và nguồn; log/trace IDs đã redact.
10. **Rollback:** quay lại config đã kiểm chứng an toàn, không tắt toàn bộ Spring Security headers hoặc expose Actuator để chữa nhanh.

Một thay đổi có thể giảm rò rỉ nhưng phá OAuth callback hoặc CORS, vì vậy phải test behavior người dùng, không chỉ một checklist scanner.

## 23. Bài thực hành tổng hợp

**Bối cảnh:** Gateway WebFlux tại `https://api.example.test`; route `/api/orders/**` tới order-service; JWT auth, ingress terminate TLS, management Actuator private. Một backend legacy đôi khi trả 500 chứa internal hostname.

Yêu cầu thực hiện:

1. Chọn Boot/Gateway/Security phiên bản được hỗ trợ và ghi rõ dependencies.
2. Cấu hình route `Path=/api/orders/**`, `StripPrefix=1`.
3. Tạo mock backend trả 200, 404, 422, 503 và một 500 chứa thông tin nhạy cảm.
4. Xác minh no-route 404 khác backend 404 bằng mock request count.
5. Đặt `server.error.include-stacktrace/message/exception/binding-errors` an toàn trên Boot 3.5.
6. Thiết kế JSON error theo Problem Details hoặc API code contract.
7. Dùng `RemoveResponseHeader` loại `X-Backend-Host`/`X-Powered-By` trên matched routes.
8. Thêm Spring Security headers phù hợp và test 401/403 trước route match.
9. Chọn owner cho HSTS, CSP, cache, CORS, frame/Referrer policy.
10. Chuẩn hóa lỗi 500 từ backend ở chính backend hoặc response rewrite theo schema, không lọc chuỗi thô.
11. Đảm bảo 422 vẫn là 422, không bị thay thành 200/503.
12. Test Gateway connect refused/timeout không tiết lộ DNS/IP/stack trace.
13. Test 302 Location không trỏ internal hostname và giữ HTTPS/prefix.
14. Test session cookies, OAuth redirect URI và CORS browser flow.
15. Tách management endpoint ra private network; hạn chế `gateway` actuator endpoint.
16. Test client tự gửi Host/Forwarded/X-Forwarded-Host giả không ảnh hưởng public URL.
17. Kiểm response do ingress/CDN tự sinh, gồm 413/502/504.
18. Chạy regression tests trên mọi Gateway replicas.
19. Kiểm logs/traces/CI reports không chứa token/cookie/PII.
20. Viết runbook deploy và rollback an toàn.

### Tiêu chí hoàn thành

~~~text
[PASS] Status/error code phản ánh đúng nguồn và kết quả nghiệp vụ
[PASS] Response không lộ stacktrace/class/SQL/internal host/IP
[PASS] Gateway route error headers đã được lọc theo policy
[PASS] Security/no-route responses vẫn có header protection từ đúng owner
[PASS] HSTS/CSP/CORS/cache policies nhất quán trên public origin
[PASS] Cookie/Location/OAuth không lộ host/path nội bộ
[PASS] Actuator/env/configprops/gateway management không public
[PASS] Client giả Forwarded/Host không điều khiển redirects
[PASS] WWW-Authenticate/Retry-After được giữ theo contract
[PASS] Logs/traces/test fixtures không đưa secrets/PII ra ngoài
[PASS] Kết quả được xác minh qua full HTTP chain, không chỉ một unit test
~~~

Đây là **tiêu chí dự kiến**, không phải kết quả đã chạy trong workspace.

## 24. Checklist trước production

- [ ] Có phân loại nguồn lỗi: Spring Security, no-route, upstream HTTP, network/timeout, fallback.
- [ ] Response errors có status, stable code và detail an toàn; không giấu failure bằng 200.
- [ ] Boot `server.error.*` ở mode không hiển thị message/exception/stacktrace trên public API.
- [ ] Không bật stacktrace `always`/`on-param` trong production.
- [ ] Backend chuẩn hóa lỗi và không trả raw SQL/JDBC/hostname/class/PII.
- [ ] Gateway body rewrite nếu có đã test gzip, streaming, length, HEAD/204/304, memory limits.
- [ ] HSTS thuộc public HTTPS owner, không áp preload/includeSubDomains vô điều kiện.
- [ ] CSP theo HTML/frontend requirements; Report-Only rollout khi cần.
- [ ] Spring Security headers không bị tắt chung chỉ vì trùng với SecureHeaders.
- [ ] Gateway `SecureHeaders` không được coi là bảo vệ mọi 401/no-route errors.
- [ ] X-Content-Type-Options, frame, Referrer-Policy và caching đã test.
- [ ] CORS có owner, không credentialed wildcard, `Vary` đúng khi cần.
- [ ] `WWW-Authenticate`, `Retry-After`, `Vary`, `Set-Cookie` không bị xóa bừa.
- [ ] Headers debug/upstream node/version được loại ở đúng hop; public edge được test.
- [ ] Response `Location`/`Link`/OpenAPI không tiết lộ internal hosts/ports.
- [ ] Cookie Secure/HttpOnly/SameSite/Domain/Path phù hợp public URL.
- [ ] Ingress sanitize untrusted Forwarded/Host, Gateway không bị public bypass.
- [ ] Actuator/gateway management read-only tối thiểu trên private plane hoặc không expose.
- [ ] Không dump raw headers/body/token/cookie/PII vào logs/traces/CI.
- [ ] Trace IDs và metric labels được validate/giới hạn cardinality.
- [ ] Test matrix 200/201/204/3xx/400/401/403/404/413/429/500/503/504 đầy đủ.
- [ ] Test mock upstream ghi lại request thật; client test kiểm response cuối.
- [ ] Test cả errors do CDN/ingress tạo trước khi Gateway nhận request.
- [ ] Release train Spring Boot/Spring Cloud Gateway/Security được vá và hỗ trợ.
- [ ] Canary, multi-replica config drift, rollback và observability có kế hoạch rõ.

## 25. Tổng kết và tài liệu tham khảo

**Gia cố bảo mật response của Spring Cloud Gateway không thể hoàn tất chỉ bằng một filter**. Một API an toàn cần kiểm soát:

1. **Error responses:** giữ HTTP status chính xác, ổn định public error code, không tiết lộ Java stack trace/SQL/hostname/PII, kể cả lỗi từ backend.
2. **Security headers:** áp dụng từ đúng owner — public TLS edge, Spring Security, WebFilter hoặc Gateway route filter — để tránh duplicate/missing headers ở 401, 404 và 5xx.
3. **Deployment details:** không lộ Server banners, debug headers, internal `Location`, cookie attributes sai, Actuator endpoints hoặc secret từ logs/traces.

Hãy test từ **public client** và **mock upstream** trong cùng một luồng HTTP. Chỉ nhìn status 200 hoặc một scanner báo đủ headers chưa chứng minh routing, authorization và lỗi trả về đều an toàn. Duy trì error contract, security patch, network isolation và khả năng quan sát nội bộ đã redact để vừa bảo vệ người dùng vừa điều tra sự cố hiệu quả.

### Tài liệu tham khảo chính thức

- [Spring Boot — Reactive Web Applications: Error Handling và Problem Details](https://docs.spring.io/spring-boot/reference/web/reactive.html).
- [Spring Boot 3.5 — Common Application Properties, server.error.*](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/).
- [Spring Security — Reactive HTTP Response Headers](https://docs.spring.io/spring-security/reference/reactive/exploits/headers.html).
- [Spring Cloud Gateway Server WebFlux — SecureHeaders GatewayFilter](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/gatewayfilter-factories/secureheaders-factory.html).
- [Spring Cloud Gateway Server WebFlux — RemoveResponseHeader](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/gatewayfilter-factories/removeresponseheader-factory.html).
- [Spring Cloud Gateway Server WebFlux — SetResponseHeader](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/gatewayfilter-factories/setresponseheader-factory.html).
- [Spring Cloud Gateway Server WebFlux — DedupeResponseHeader](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/gatewayfilter-factories/deduperesponseheader-factory.html).
- [Spring Cloud Gateway Server WebFlux — RewriteLocationResponseHeader](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/gatewayfilter-factories/rewritelocationresponseheader-factory.html).
- [Spring Cloud Gateway — Configuration Properties 5.x](https://docs.spring.io/spring-cloud-gateway/reference/5.0/configprops.html).
- [Spring Cloud Gateway Server WebFlux — Actuator API](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/actuator-api.html).
- [Spring Boot — Actuator Endpoints and Access Control](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html).
- [Spring Framework WebFlux — Error Responses / RFC 9457](https://docs.spring.io/spring-framework/reference/web/webflux/ann-rest-exceptions.html).
- [IETF RFC 9457 — Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457.html).
