# Chuẩn hóa phản hồi 401, 403 và lỗi xác thực trong Spring Cloud Gateway

Một **API Gateway** thường đứng trước nhiều microservice, xử lý route predicate, filter chain, biến đổi path/header và kiểm soát việc client được phép gọi những API nào. Khi một request bị từ chối, phản hồi không chỉ cần đúng mã HTTP: nó còn phải **nhất quán về cấu trúc**, **đúng giao thức xác thực**, **không tiết lộ dữ liệu nhạy cảm** và **giúp client biết nên làm gì tiếp theo**.

Ví dụ, ứng dụng di động gọi `GET /api/orders/42` có thể gặp ba tình huống:

- Không có access token: client cần đăng nhập hoặc lấy token phù hợp.
- Token hợp lệ nhưng không có quyền đọc đơn hàng: client không được phép tiếp tục với danh tính hiện tại.
- Token bị giả mạo hoặc hết hạn: client phải xử lý token không hợp lệ, không chỉ hiển thị thông báo “Server error”.

Ba trường hợp có thể nhìn giống nhau trong giao diện, nhưng **không nên trả cùng status hoặc cùng hướng xử lý**.

Bài thuộc chương **Xác thực và phân quyền** của module `SPRING_CLOUD_GATEWAY`. Trọng tâm là **Spring Cloud Gateway Server WebFlux**, **Spring Security Reactive OAuth2 Resource Server**, thông báo lỗi HTTP và hợp đồng API dùng chung. Những chính sách khác như rate limiting, retry, circuit breaker, TLS và tracing được đề cập ở điểm giao nhau với lỗi bảo mật.

> **Phạm vi phiên bản:** Ví dụ chính theo **Spring Cloud Gateway Server WebFlux 5.0.x**, Spring Cloud 2025.1.x, Spring Boot 4.x và Spring Security 7.x. Route YAML dùng `spring.cloud.gateway.server.webflux.routes`. Đừng chép cấu hình của các nhánh Gateway cũ (dùng `spring.cloud.gateway.routes`) hoặc Server Web MVC sang WebFlux mà không đối chiếu tài liệu/API.

## 1. Kết quả học tập

Sau bài này, bạn có thể:

1. Phân biệt **authentication failure** và **authorization denial**, ánh xạ đúng `401`, `403` cùng các tình huống ngoại lệ.
2. Giải thích vai trò của `WWW-Authenticate`, `invalid_token`, `invalid_request` và `insufficient_scope` theo OAuth 2.0 Bearer Token (RFC 6750).
3. Đề xuất JSON error contract dựa trên **Problem Details** (RFC 9457) có `status`, `code` và `requestId`.
4. Tạo `ServerAuthenticationEntryPoint` và `ServerAccessDeniedHandler` trong Spring Security WebFlux, không nhầm với `@ControllerAdvice` hay `GlobalFilter`.
5. Cấu hình Spring Security Reactive Resource Server xác minh JWT và kiểm soát scope trên route được Gateway proxy.
6. Kiểm thử thiếu token, token sai/hết hạn, token đủ/thiếu scope, CORS preflight, backend 401/403 và lỗi kết nối.
7. Tránh tiết lộ nguyên nhân xác thực chi tiết hoặc làm mất header chuẩn khi xử lý lỗi.

## 2. Phân biệt `401 Unauthorized` và `403 Forbidden`

Tên chuẩn HTTP `401 Unauthorized` dễ gây hiểu sai: trong thực tế nó thường biểu thị **chưa có xác thực hợp lệ**, không phải “đã đăng nhập nhưng thiếu quyền”.

| Tình huống | Có thông tin xác thực hợp lệ? | Mã thường dùng | Hướng xử lý client |
|---|---|---|---|
| Không gửi `Authorization` tới API yêu cầu Bearer | Không | `401` | Nhận token rồi thử lại nếu phù hợp |
| Access token hết hạn/không hợp lệ | Không | `401` | Thay token bằng token hợp lệ; không retry vô hạn |
| JWT sai chữ ký, sai issuer hoặc không được chấp nhận | Không | `401` | Đăng nhập lại/kiểm tra token hợp lệ |
| Bearer request sai cú pháp, token gửi lặp theo nhiều cách | Không thể xử lý đúng | Thường `400` theo RFC 6750 `invalid_request` | Sửa request |
| Token đã xác thực, thiếu scope bắt buộc | Có | `403` | Yêu cầu quyền/scope phù hợp; không refresh vô hạn |
| User đã xác thực nhưng không có quyền trên đơn hàng của user khác | Có | Thường `403`; đôi khi `404` để tránh lộ tài nguyên | Không được phép xem/sửa tài nguyên |
| Route/path không tồn tại | Không phải lỗi auth tự thân | `404` nếu policy/handler cho phép | Kiểm tra endpoint |
| Gateway rate limiter từ chối request | Không phải lỗi auth tự thân | `429` | Tôn trọng `Retry-After` nếu có |
| Upstream không sẵn sàng/timeout | Không phải lỗi auth tự thân | `5xx` phù hợp | Retry có giới hạn theo tính idempotent |

Quy tắc nhớ nhanh:

```text
401: "Tôi chưa thể xác thực bạn."
403: "Tôi đã xác thực, nhưng bạn không được phép làm việc này."
```

Không phải mọi hệ thống đều sử dụng JWT: session, mTLS/X.509 hoặc API key có cơ chế xác thực riêng. **Ý nghĩa 401/403 vẫn giữ**, nhưng scheme và header challenge cần theo cơ chế đang dùng, không gán `Bearer` cho một hệ thống không sử dụng Bearer token.

### 2.1. Sơ đồ ra quyết định

```mermaid
flowchart TD
    A["Request tới API cần bảo vệ"] --> B{"Credentials đúng cú pháp?"}
    B -- "Không" --> C["400 invalid_request<br/>nếu đúng loại lỗi OAuth Bearer"]
    B -- "Có / không gửi" --> D{"Xác thực thành công?"}
    D -- "Không" --> E["401 + WWW-Authenticate"]
    D -- "Có" --> F{"Có quyền theo route/tài nguyên?"}
    F -- "Không" --> G["403 hoặc 404 theo policy chống lộ tài nguyên"]
    F -- "Có" --> H["Chuyển tới Gateway route/backend"]
```

Sơ đồ mô tả **quy tắc thiết kế**, không phải thứ tự gọi callback chính xác trong mọi request: một request thiếu token có thể bị từ chối bởi Spring Security trước khi route predicate của Gateway được xét. Nếu một endpoint không tồn tại nhưng security policy yêu cầu xác thực trên mọi path, client chưa xác thực vẫn có thể nhận `401` thay vì `404`.

### 2.2. `401` và `403` không thay thế được nhau

Nếu client gửi JWT hợp lệ, đủ điều kiện xác minh nhưng thiếu scope `orders:write`, việc trả `401` khiến client nghĩ token đã hết hạn và có thể thử làm mới nhiều lần. Trả `403` cho phép client hiển thị “Bạn không có quyền” hoặc hướng dẫn xin quyền.

Ngược lại, trả `403` cho token hết hạn có thể khiến ứng dụng không kích hoạt luồng lấy token hợp lệ. Vì vậy một API nhất quán phải phân biệt **token invalid** với **permission denied**.

## 3. Chuẩn HTTP Bearer: `WWW-Authenticate`

Theo **RFC 6750**, resource server bảo vệ bằng Bearer token phải trả `WWW-Authenticate` khi request không có credentials hoặc không có token cho phép truy cập. Header challenge giúp client hiểu **scheme** và, khi phù hợp, **lý do OAuth**.

### 3.1. Thiếu token

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api"
Cache-Control: no-store
Content-Type: application/problem+json
```

**Quan trọng:** Khi client không gửi thông tin xác thực, RFC 6750 khuyến nghị **không thêm `error`** vào challenge. Nói cách khác, `WWW-Authenticate: Bearer realm="orders-api"` là đủ; không bắt buộc gắn `error="invalid_token"` cho request hoàn toàn thiếu token.

### 3.2. Token hết hạn hoặc sai

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api", error="invalid_token"
Cache-Control: no-store
Content-Type: application/problem+json
```

Mã `invalid_token` bao phủ token hết hạn, bị thu hồi, sai chữ ký, sai issuer và nhiều lỗi token khác. **Không cần tiết lộ** token sai vì lý do cụ thể nào trong phản hồi công khai. Việc trả `error_description` quá chi tiết có thể làm lộ cấu trúc hệ thống xác thực; ưu tiên thông điệp an toàn và ghi chi tiết tại log nội bộ.

### 3.3. Token hợp lệ nhưng thiếu scope

```http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer realm="orders-api", error="insufficient_scope", scope="orders:write"
Cache-Control: no-store
Content-Type: application/problem+json
```

`insufficient_scope` áp dụng **khi biết rõ rằng thiếu scope**, không phải cho mọi trường hợp từ chối 403. Chẳng hạn một user đã có scope đọc đơn hàng nhưng truy cập đơn hàng của user khác có thể bị từ chối vì **quyền sở hữu tài nguyên**. Đó không nhất thiết là lỗi thiếu scope, và không nên công bố scope sai hoặc thông tin tài nguyên của user khác.

### 3.4. Bearer request sai cú pháp

RFC 6750 có `invalid_request`, chẳng hạn token được gửi nhiều cách không hợp lệ hoặc tham số xác thực sai cú pháp. Trong trường hợp đó, `400 Bad Request` là mã được khuyến nghị theo chuẩn; không ép mọi lỗi liên quan Authorization thành `401`.

| Mã OAuth trong `WWW-Authenticate` | Thường đi với HTTP | Nghĩa |
|---|---|---|
| Không có `error` | `401` | Chưa gửi credentials |
| `invalid_request` | `400` | Request xác thực sai cấu trúc |
| `invalid_token` | `401` | Token không thể được chấp nhận |
| `insufficient_scope` | `403` | Token hợp lệ nhưng thiếu scope |

Đối với API không dùng OAuth Bearer, `WWW-Authenticate` phải dùng authentication scheme tương ứng. Không trả challenge giả hoặc giữ nguyên challenge do backend khác không thuộc cùng security domain cung cấp mà chưa kiểm tra.

## 4. Hợp đồng JSON: RFC 9457 Problem Details

Chỉ trả:

```json
{"message":"Unauthorized"}
```

là quá mơ hồ nếu nhiều ứng dụng cần phân biệt token sai, thiếu scope hay lỗi nghiệp vụ. Một giải pháp là dùng **Problem Details for HTTP APIs**, được chuẩn hóa tại **RFC 9457** (thay thế RFC 7807).

Ví dụ `401`:

```http
HTTP/1.1 401 Unauthorized
Content-Type: application/problem+json
WWW-Authenticate: Bearer realm="orders-api"
Cache-Control: no-store
X-Request-Id: 9e84c68e-3b32-44aa-a0dd-439d4c4c3a8e

{
  "type": "about:blank",
  "title": "Unauthorized",
  "status": 401,
  "code": "AUTHENTICATION_REQUIRED",
  "requestId": "9e84c68e-3b32-44aa-a0dd-439d4c4c3a8e"
}
```

Trong đó:

| Trường | Mục đích | Chú ý |
|---|---|---|
| `type` | Định danh loại vấn đề | `about:blank` là giá trị hợp lệ; API có thể dùng URI tài liệu nếu có |
| `title` | Tên tổng quát, ổn định | Không nhét chi tiết exception vào đây |
| `status` | Mã HTTP trong body | **Phải khớp** với mã response thật |
| `detail` | Mô tả ngắn hướng người dùng | Có thể bỏ để tránh tiết lộ thông tin |
| `instance` | Xác định lần xuất hiện cụ thể | Nếu dùng URI, tránh gắn query/token nhạy cảm |
| `code` | **Extension field** của API cho máy đọc | Ổn định theo hợp đồng riêng, không phải field bắt buộc RFC |
| `requestId` | **Extension field** hỗ trợ tra cứu log | Không chứa token, email hoặc IP người dùng |

`type: about:blank` không làm `code` trở thành mã lỗi HTTP chuẩn. **Các code `AUTHENTICATION_REQUIRED`, `TOKEN_INVALID`, `ACCESS_DENIED` dưới đây là quy ước của ứng dụng**, do team công bố và duy trì ổn định.

### 4.1. Bảng mã lỗi đề xuất

| HTTP | `code` ứng dụng | Khi nào dùng |
|---|---|---|
| `401` | `AUTHENTICATION_REQUIRED` | Request thiếu credentials |
| `401` | `TOKEN_INVALID` | JWT/token đã được gửi nhưng không hợp lệ |
| `403` | `ACCESS_DENIED` | Danh tính hợp lệ bị từ chối vì policy hoặc ownership |
| `403` | `INSUFFICIENT_SCOPE` | Đã xác minh thiếu scope cụ thể |
| `400` | `AUTH_REQUEST_INVALID` | Cấu trúc Bearer authentication request không hợp lệ |

Một hợp đồng error ổn định cần có **đường dẫn tài liệu**, danh sách mã và hướng xử lý client. HTTP status vẫn là tín hiệu chính; frontend không nên chỉ dựa vào chuỗi `title` vì title có thể dịch sang ngôn ngữ khác.

### 4.2. Không trả exception chi tiết ra client

Tránh phản hồi như:

```json
{
  "status": 401,
  "detail": "SignatureVerificationException at com.example.jwt.AuthFilter:172"
}
```

hoặc nhúng nguyên JWT, public key ID, issuer nội bộ, danh sách role, user ID, stacktrace. Client chỉ cần tín hiệu đủ để chọn hành vi. Log nội bộ có thể lưu **loại lỗi đã chuẩn hóa**, route ID, request ID và thời gian; không log access token/cookie/raw Authorization.

## 5. Ranh giới xử lý lỗi: Spring Security hay GatewayFilter?

Trong **Gateway Server WebFlux**, **Spring Security `WebFilter`** thường xử lý xác thực/ủy quyền **trước** khi request tới phần chọn route và chuỗi `GlobalFilter + GatewayFilter` của Gateway.

```mermaid
sequenceDiagram
    participant C as Client
    participant S as Spring Security WebFilter
    participant G as Gateway route + filter chain
    participant B as Backend
    C->>S: GET /api/orders/42
    alt Token thiếu hoặc không hợp lệ
      S-->>C: 401 + Bearer challenge
    else Token hợp lệ nhưng thiếu quyền
      S-->>C: 403
    else Authentication + authorization hợp lệ
      S->>G: Chuyển tiếp HTTP request
      G->>B: Proxy đến service đã match
      B-->>G: HTTP response
      G-->>C: HTTP response
    end
```

Do đó, **đặt `onErrorResume` trong một `GlobalFilter` không bảo đảm bắt được các lỗi xác thực xảy ra ở Spring Security WebFilter**. Cũng không nên trông chờ một `@RestControllerAdvice` sẽ xử lý mọi lỗi bị security từ chối trước controller.

| Vị trí | Công cụ phù hợp | Những việc nó không tự làm |
|---|---|---|
| **Spring Security**: chưa xác thực | `ServerAuthenticationEntryPoint` | Không xử lý mọi lỗi do backend trả |
| **Spring Security**: từ chối quyền | `ServerAccessDeniedHandler` | Không tự phân tích mọi 403 upstream |
| **WebFlux controller** | `@ExceptionHandler`, `@RestControllerAdvice` / `ProblemDetail` | Không tự thay entry point của security filter |
| **Gateway route filter** | `GatewayFilter`, `GlobalFilter` | Không mặc định chạy trước Spring Security |
| **Backend service** | Backend security/exception handling | Gateway không tự biến 401/403 backend thành contract chung |
| **Ingress/WAF** | Chính sách proxy/ingress | Không phải response do Gateway code sinh |

Một kiến trúc nhất quán nên **quy định hợp đồng lỗi ở cấp toàn hệ thống**, nhưng triển khai tại **mỗi lớp phát sinh lỗi**. Không nên viết một filter cố gắng “biến tất cả 4xx thành 401” vì nó có thể làm mất `404`, `429`, `WWW-Authenticate` và thông tin quan trọng khác.

## 6. Cấu hình Resource Server JWT trên Gateway WebFlux

### 6.1. Dependency và issuer

Với Spring Boot 4, starter được khuyến nghị cho OAuth 2.0 Resource Server là:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-security-oauth2-resource-server</artifactId>
</dependency>
```

Ngoài ra cần starter **Spring Cloud Gateway Server WebFlux**, Spring Cloud BOM tương thích với Boot 4 và ứng dụng Spring Boot. Dependency này không tự tạo Authorization Server.

Ví dụ cấu hình:

```yaml
server:
  port: 8080

spring:
  application:
    name: secure-gateway
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.test/issuer

  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: orders-route
              uri: http://localhost:9001
              predicates:
                - Path=/api/orders/**
              filters:
                - StripPrefix=1
```

`identity.example.test` là **địa chỉ minh họa**, không có IdP thật nên ví dụ chưa thể xác minh token. Trong lab phải thay bằng issuer thuộc hệ thống test đã cấu hình OIDC/OAuth2 Resource Server. Gateway xác thực chữ ký, `iss`, `exp` và `nbf` theo cấu hình/decoder; nếu API yêu cầu **audience** cụ thể, phải thêm validator `aud` phù hợp. Đừng chỉ decode phần payload JWT rồi dùng `sub`/`scope` như dữ liệu đáng tin.

**Lưu ý:** Trên Spring Security, scope OAuth2 thường được ánh xạ thành authority có tiền tố `SCOPE_`. Ví dụ scope `orders:read` có authority `SCOPE_orders:read`. Nếu IdP phát claim đặc thù như `roles`/`permissions`, bạn phải có converter và policy được kiểm chứng; không tự gán `ROLE_ADMIN` từ request header.

### 6.2. Bước đầu: giữ handler Bearer chuẩn của Spring Security

Trước khi viết format JSON tùy biến, nên chạy một ứng dụng dùng **handler Bearer có sẵn**. Các lớp reactive:

- `BearerTokenServerAuthenticationEntryPoint`: chuẩn hóa challenge và status khi authentication thất bại.
- `BearerTokenServerAccessDeniedHandler`: chuẩn hóa truy cập bị từ chối. Handler mặc định có thể phát `insufficient_scope` khi nhận diện OAuth2 Authentication hợp lệ; nếu ứng dụng còn kiểm tra **ownership/tenant** ngoài scope, cần cân nhắc custom handler để không diễn giải mọi từ chối quyền là thiếu scope.

Ví dụ `GatewaySecurityConfiguration.java`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.oauth2.server.resource.web.server.BearerTokenServerAuthenticationEntryPoint;
import org.springframework.security.oauth2.server.resource.web.access.server.BearerTokenServerAccessDeniedHandler;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
public class GatewaySecurityConfiguration {
    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        var authEntryPoint = new BearerTokenServerAuthenticationEntryPoint();
        authEntryPoint.setRealmName("orders-api");

        var deniedHandler = new BearerTokenServerAccessDeniedHandler();
        deniedHandler.setRealmName("orders-api");

        return http
            // Chỉ phù hợp demo API Bearer token KHÔNG dùng browser session.
            .csrf(ServerHttpSecurity.CsrfSpec::disable)
            .httpBasic(ServerHttpSecurity.HttpBasicSpec::disable)
            .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
            .authorizeExchange(ex -> ex
                .pathMatchers("/actuator/health").permitAll()
                .pathMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders:read")
                .pathMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders:write")
                .anyExchange().authenticated())
            .exceptionHandling(errors -> errors
                .authenticationEntryPoint(authEntryPoint)
                .accessDeniedHandler(deniedHandler))
            .oauth2ResourceServer(oauth -> {
                oauth.authenticationEntryPoint(authEntryPoint);
                oauth.accessDeniedHandler(deniedHandler);
                oauth.jwt(Customizer.withDefaults());
            })
            .build();
    }
}
```

**Đây là cấu hình dành cho một API Bearer-only stateless.** Nếu Gateway còn dùng cookie/session hoặc browser login, không tắt CSRF/`formLogin` một cách máy móc; cần thiết kế security chain theo từng loại endpoint và mô hình credentials.

Hướng xử lý khi gọi `GET /api/orders/42`:

- Không Bearer token → thường `401` và challenge `Bearer realm="orders-api"`.
- JWT không hợp lệ → thường `401` và `invalid_token`.
- JWT hợp lệ nhưng thiếu `orders:read` → `403`; built-in denial handler xử lý Bearer challenge theo ngữ cảnh authentication.
- JWT có `orders:read` → tiếp tục vào Gateway route, sau đó HTTP status phụ thuộc backend.

Các default Bearer handlers **không tự thêm JSON Problem Details giống hợp đồng ở mục 4**; ưu điểm của chúng là đã hiểu ngữ nghĩa RFC 6750. Nếu muốn thêm body JSON, phải làm cẩn thận để không làm hỏng challenge/status.

### 6.3. Vì sao cần cấu hình cả hai điểm cắm?

`exceptionHandling(...)` của `ServerHttpSecurity` xác định entry point và access-denied handler cho lỗi do framework authorization xử lý. `oauth2ResourceServer(...)` cũng cho phép đặt các handler cho lỗi trực tiếp từ Bearer token authentication.

Khi chuẩn hóa lỗi, hãy bảo đảm **cả nhánh authorization và nhánh Bearer token** đều sử dụng chính sách đồng nhất, vì token sai và thiếu token có thể đi qua vị trí xử lý khác nhau. Spring Security có default riêng, nhưng mặc định không bảo đảm đúng JSON contract do team tự thiết kế.

## 7. Tùy biến `401` và `403` thành Problem Details JSON

Mẫu sau tạo body `application/problem+json` với các giá trị **hằng/UUID do server tạo**, tránh nhúng raw exception message. Nó là **một phương án thay thế** cho built-in handlers của mục 6.2 — chọn một phương án, không đăng ký hai chính sách khác nhau trong cùng security chain.

### 7.1. Viết response bằng WebFlux `ServerHttpResponse`

Tạo `SecurityProblemHandlers.java`:

```java
import java.nio.charset.StandardCharsets;
import java.util.UUID;

import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.server.reactive.ServerHttpResponse;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.web.server.ServerAuthenticationEntryPoint;
import org.springframework.security.web.server.authorization.ServerAccessDeniedHandler;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

public final class SecurityProblemHandlers {
    private static final MediaType PROBLEM_JSON =
            MediaType.parseMediaType("application/problem+json");

    private SecurityProblemHandlers() { }

    public static ServerAuthenticationEntryPoint entryPoint() {
        return (exchange, error) -> {
            HttpStatus status = HttpStatus.UNAUTHORIZED;
            String code = "AUTHENTICATION_REQUIRED";
            String challenge = "Bearer realm=\"orders-api\"";

            if (error instanceof OAuth2AuthenticationException oauth) {
                String oauthCode = oauth.getError().getErrorCode();

                if ("invalid_token".equals(oauthCode)) {
                    code = "TOKEN_INVALID";
                    challenge += ", error=\"invalid_token\"";
                } else if ("invalid_request".equals(oauthCode)) {
                    status = HttpStatus.BAD_REQUEST;
                    code = "AUTH_REQUEST_INVALID";
                    challenge += ", error=\"invalid_request\"";
                }
            }

            return write(exchange, status, code, challenge);
        };
    }

    public static ServerAccessDeniedHandler deniedHandler() {
        return (exchange, denied) ->
            // Không mặc định gán insufficient_scope cho MỌI 403:
            // nó còn có thể là thiếu quyền trên một tài nguyên cụ thể.
            write(exchange, HttpStatus.FORBIDDEN, "ACCESS_DENIED", null);
    }

    private static Mono<Void> write(
            ServerWebExchange exchange,
            HttpStatus status,
            String code,
            String wwwAuthenticate) {

        ServerHttpResponse response = exchange.getResponse();

        if (response.isCommitted()) {
            // Không cố sửa status/header/body khi HTTP response đã commit.
            return Mono.error(new IllegalStateException(
                    "Security response was already committed"));
        }

        String id = UUID.randomUUID().toString();
        String title = status == HttpStatus.UNAUTHORIZED
                ? "Unauthorized"
                : status == HttpStatus.FORBIDDEN
                    ? "Forbidden"
                    : "Bad Request";

        response.setStatusCode(status);
        response.getHeaders().setContentType(PROBLEM_JSON);
        response.getHeaders().set(HttpHeaders.CACHE_CONTROL, "no-store");
        response.getHeaders().set("X-Request-Id", id);

        if (wwwAuthenticate != null) {
            response.getHeaders().set(
                    HttpHeaders.WWW_AUTHENTICATE, wwwAuthenticate);
        }

        // Mọi trường chèn vào JSON đều do server kiểm soát:
        // status/title/code hằng và UUID mới. Không chèn raw error text.
        String json = """
            {"type":"about:blank",
             "title":"%s",
             "status":%d,
             "code":"%s",
             "requestId":"%s"}
            """.formatted(title, status.value(), code, id);

        byte[] bytes = json.getBytes(StandardCharsets.UTF_8);
        return response.writeWith(Mono.just(
                response.bufferFactory().wrap(bytes)));
    }
}
```

**Giải thích:**

- `ServerAuthenticationEntryPoint` nhận `AuthenticationException` trước khi trả phản hồi xác thực không thành công.
- Nếu exception là `OAuth2AuthenticationException` và có mã `invalid_token`, đặt status `401`, code `TOKEN_INVALID` và challenge đúng loại.
- Nếu đúng `invalid_request`, ví dụ ánh xạ thành `400` theo RFC 6750. Không phải mọi lỗi `400` của ứng dụng đều là `invalid_request`.
- `ServerAccessDeniedHandler` trả `403` và `ACCESS_DENIED`. Nó **không tự phỏng đoán** thiếu scope cho mọi denial.
- `Cache-Control: no-store` giảm nguy cơ cache phản hồi có liên quan tới auth.
- `requestId` được tạo bằng UUID mới trong handler. Đây là **demo độc lập**: nếu hệ thống đã có correlation ID tin cậy, hãy thống nhất nguồn tạo ID ở ingress/`WebFilter` sớm để response thành công/thất bại đều dùng một ID; đừng tạo ID thứ hai tùy ý trong production.
- `Content-Type: application/problem+json` mô tả format RFC 9457; `code` và `requestId` là extension fields.
- JSON được format thủ công **chỉ vì đầu vào toàn hằng/UUID an toàn**. Nếu bổ sung detail, URI hoặc dữ liệu động, dùng serializer JSON và escaping đúng chuẩn; đừng nối input tùy ý.

### 7.2. Gắn handler mới vào `SecurityWebFilterChain`

Giữ nguyên cấu hình issuer và route ở mục 6.1. Tạo **một** security chain; đoạn sau **thay thế** phần tạo handler của mục 6.2:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
public class GatewayProblemSecurityConfiguration {
    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        var entry = SecurityProblemHandlers.entryPoint();
        var denied = SecurityProblemHandlers.deniedHandler();

        return http
            .csrf(ServerHttpSecurity.CsrfSpec::disable)
            .httpBasic(ServerHttpSecurity.HttpBasicSpec::disable)
            .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
            .authorizeExchange(ex -> ex
                .pathMatchers("/actuator/health").permitAll()
                .pathMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders:read")
                .pathMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders:write")
                .anyExchange().authenticated())
            .exceptionHandling(errors -> errors
                .authenticationEntryPoint(entry)
                .accessDeniedHandler(denied))
            .oauth2ResourceServer(oauth -> {
                oauth.authenticationEntryPoint(entry);
                oauth.accessDeniedHandler(denied);
                oauth.jwt(Customizer.withDefaults());
            })
            .build();
    }
}
```

**Đừng đăng ký cả `GatewaySecurityConfiguration` và `GatewayProblemSecurityConfiguration` đồng thời**, vì chúng tạo các `SecurityWebFilterChain` cùng điều kiện. Chỉ giữ một class cấu hình.

### 7.3. Giới hạn quan trọng của mẫu JSON đơn giản

Trong ví dụ, handler `403` dùng code chung `ACCESS_DENIED` và **không thêm `WWW-Authenticate`** vì nó không biết denial có thực sự do thiếu scope hay không. Đối với API thuần OAuth2 cần challenge `insufficient_scope` chính xác, có hai lựa chọn:

1. **Ưu tiên built-in `BearerTokenServerAccessDeniedHandler`** của Spring Security, vốn biết xử lý RFC 6750 theo loại OAuth2 authentication; chấp nhận body mặc định và chuẩn hóa ở client nếu không bắt buộc Problem Details.
2. Khi bắt buộc trả Problem Details, mở rộng handler bằng **kết quả authorization đáng tin** để phân biệt lỗi thiếu scope với policy/ownership; chỉ khi thực sự thiếu scope mới đặt `WWW-Authenticate: Bearer realm="orders-api", error="insufficient_scope"` và, nếu phù hợp, thêm `scope="orders:write"`. Không suy luận scope thiếu chỉ từ exception text.

Bài demo cũng chủ động **không** chèn `error_description`; khi dùng native Bearer handler, các thông số challenge khác như `error_uri` có thể được nó xử lý theo RFC 6750. Khi custom, cần kiểm thử đầy đủ `invalid_request`, `invalid_token` và yêu cầu thiếu quyền; **không được coi ví dụ là sự thay thế đầy đủ cho mọi tính năng mặc định của framework**.

### 7.4. Mã lỗi nhất quán phải đi cùng mã HTTP đúng

Ví dụ JSON khi access token hợp lệ nhưng thiếu quyền:

```http
HTTP/1.1 403 Forbidden
Content-Type: application/problem+json
Cache-Control: no-store
X-Request-Id: 90f9fe22-44f4-49bb-9cae-1824f821d591

{
  "type": "about:blank",
  "title": "Forbidden",
  "status": 403,
  "code": "ACCESS_DENIED",
  "requestId": "90f9fe22-44f4-49bb-9cae-1824f821d591"
}
```

Một lỗi 401 không được ghi `status: 403` trong body chỉ vì dùng chung template. Client có thể kiểm tra cả HTTP status và application `code`. Ưu tiên HTTP status thực; khi hai giá trị không khớp, đó là lỗi triển khai API.

## 8. `401/403` tại Gateway và tại backend là hai nguồn khác nhau

### 8.1. Gateway tự từ chối

Nếu Spring Security từ chối **trước Gateway routing**, backend **không được gọi**. Đây là vị trí thích hợp để response thống nhất theo `ServerAuthenticationEntryPoint`/`ServerAccessDeniedHandler`.

### 8.2. Backend trả 401 hoặc 403

Nếu Gateway đã xác thực client thành công và proxy đến order-service nhưng order-service trả `403` (chẳng hạn user không sở hữu đơn hàng), thì đó là **HTTP response từ backend**. Không tự hiểu rằng Security WebFilter của Gateway sẽ bắt và định dạng lại response đó.

Những hệ quả thiết kế:

- Backend nên dùng **cùng error contract** nếu toàn hệ thống cần nhất quán.
- Nếu bắt buộc chuẩn hóa ở Gateway, phải dùng một response filter phù hợp, xử lý content-type/body/streaming/response commit và **bảo toàn header `WWW-Authenticate`** khi hợp lệ.
- Không đổi `403` backend thành `401` vô điều kiện. Việc này phá semantics và có thể gây lặp refresh token ở client.
- Nếu backend trả 401 do **service-to-service token** mà Gateway dùng để gọi backend, đây có thể là lỗi cấu hình/credential nội bộ, **không được quy trách nhiệm trực tiếp cho end user**. Cần xác định nguồn gây lỗi trước khi chọn phản hồi công khai.

### 8.3. Xác thực tại Gateway chưa đủ để bảo vệ mọi tài nguyên

Một route có `hasAuthority("SCOPE_orders:read")` kiểm tra scope trước khi chuyển tới backend. Nhưng backend vẫn cần kiểm tra user có quyền với **đơn hàng 42 cụ thể** không. Token có scope đọc đơn hàng không đồng nghĩa được đọc mọi đơn hàng.

Với nguy cơ lộ sự tồn tại của tài nguyên nhạy cảm, backend có thể lựa chọn `404` thay vì `403` theo policy sản phẩm. Quy tắc này phải được thống nhất và kiểm thử, không áp dụng ngẫu nhiên giữa các service.

## 9. Thực hành: kiểm thử `401`, `403` bằng `curl`

Giả sử ứng dụng Gateway đã có cấu hình:

- Route `/api/orders/**` tới backend `http://localhost:9001`, filter `StripPrefix=1`.
- Spring Security Resource Server JWT có issuer **test thật**, không phải `identity.example.test` giả.
- `GET /api/orders/**` yêu cầu `SCOPE_orders:read`.
- `POST /api/orders/**` yêu cầu `SCOPE_orders:write`.
- Một trong hai kiểu handler ở mục 6 hoặc mục 7.

### 9.1. Backend echo chỉ để kiểm tra route

Nếu chưa có order-service, tạo `OrderBackend.java` trong một thư mục lab:

```java
import com.sun.net.httpserver.HttpServer;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;

public class OrderBackend {
    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 9001), 0);

        server.createContext("/", exchange -> {
            String payload = "method=" + exchange.getRequestMethod()
                    + "\npath=" + exchange.getRequestURI().getRawPath()
                    + "\n";

            byte[] bytes = payload.getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().set(
                    "Content-Type", "text/plain; charset=utf-8");
            exchange.sendResponseHeaders(200, bytes.length);
            try (var out = exchange.getResponseBody()) {
                out.write(bytes);
            }
        });

        server.start();
        System.out.println("Order backend listening on :9001");
    }
}
```

Chạy bằng JDK 17+:

```bash
java --add-modules jdk.httpserver OrderBackend.java
```

Mở terminal khác ở dự án Gateway:

```bash
# Linux/macOS
./mvnw spring-boot:run

# Windows PowerShell
.\mvnw.cmd spring-boot:run
```

Backend echo **không có xác thực**, chỉ để quan sát xem Gateway có proxy request hay không. Production phải khóa đường truy cập trực tiếp backend qua network policy/mTLS hoặc xác thực service-to-service; không dựa hoàn toàn vào gateway.

### 9.2. Test A — thiếu Bearer token

```bash
curl -i http://localhost:8080/api/orders/42
```

Với cấu hình Problem Details tùy biến của mục 7, bạn sẽ thấy kết quả tương tự:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api"
Content-Type: application/problem+json
Cache-Control: no-store

{"type":"about:blank","title":"Unauthorized","status":401,
 "code":"AUTHENTICATION_REQUIRED","requestId":"<UUID do Gateway tạo>"}
```

Đây là **phản hồi minh họa**: giá trị UUID, thứ tự header và encoding có thể khác. Điều quan trọng là HTTP `401`, challenge `Bearer` và application code nhất quán. Order backend **không nên nhận được** request này.

Với **built-in handlers mục 6.2**, status/challenge tương tự nhưng **có thể không có body JSON**.

### 9.3. Test B — access token không hợp lệ

```bash
curl -i http://localhost:8080/api/orders/42 \
  -H "Authorization: Bearer this-is-not-a-valid-jwt"
```

Token giả này không thể vượt bước xác thực JWT. Trong trường hợp Spring Security phân loại thành `invalid_token`, kết quả mong đợi:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api", error="invalid_token"
Content-Type: application/problem+json

{"type":"about:blank","title":"Unauthorized","status":401,
 "code":"TOKEN_INVALID","requestId":"<UUID do Gateway tạo>"}
```

Trong code demo, nếu framework trả về loại `AuthenticationException` khác, ứng dụng có thể sử dụng mã chung `AUTHENTICATION_REQUIRED`. Khi contract yêu cầu phân loại chi tiết hơn, cần làm rõ **loại exception thực tế** và kiểm tra trong test tự động, không so sánh chuỗi exception message.

### 9.4. Test C — token hợp lệ nhưng thiếu quyền

Chuẩn bị một **JWT hợp lệ do IdP test cấp** có scope `profile:read` nhưng **không có** `orders:read`. Không tự sửa payload của token rồi coi chữ ký còn hợp lệ.

Trên Bash:

```bash
# Lấy token từ IdP test, không nhập token thật vào tài liệu/code.
export TOKEN_PROFILE='<valid-test-access-token>'

curl -i http://localhost:8080/api/orders/42 \
  -H "Authorization: Bearer $TOKEN_PROFILE"
```

Kết quả với Problem Details tùy biến ở mục 7:

```http
HTTP/1.1 403 Forbidden
Content-Type: application/problem+json
Cache-Control: no-store

{"type":"about:blank","title":"Forbidden","status":403,
 "code":"ACCESS_DENIED","requestId":"<UUID do Gateway tạo>"}
```

Nếu dùng **BearerTokenServerAccessDeniedHandler** của mục 6.2, thông tin challenge khi thiếu scope sẽ được Spring Security xử lý theo quy tắc OAuth2; đừng so sánh body JSON của hai phương án như thể chúng giống hệt nhau.

### 9.5. Test D — token hợp lệ có scope phù hợp

Chuẩn bị token test chứa scope `orders:read` và audience/issuer được Gateway chấp nhận:

```bash
export TOKEN_READ='<valid-test-access-token-with-orders-read>'

curl -i http://localhost:8080/api/orders/42 \
  -H "Authorization: Bearer $TOKEN_READ"
```

Nếu backend chạy khỏe và route đúng, phản hồi mẫu:

```http
HTTP/1.1 200 OK
Content-Type: text/plain; charset=utf-8

method=GET
path=/orders/42
```

Điều này chứng minh request đã vượt qua security policy, Gateway chọn route và `StripPrefix=1` hoạt động. **Nó không chứng minh backend production sẽ cho user đọc đơn hàng 42**, vì authorization theo tài nguyên chưa được mô phỏng trong echo backend.

### 9.6. Test E — khác biệt giữa `GET` và `POST`

Với cùng token chỉ có `orders:read`:

```bash
curl -i -X POST http://localhost:8080/api/orders \
  -H "Authorization: Bearer $TOKEN_READ"
```

Nếu policy `POST` đòi `SCOPE_orders:write`, kết quả là `403` **trước khi proxy**. Không nên cấp quyền write chỉ vì JWT có read. Hãy thử lại với token riêng có `orders:write` từ IdP test để xác nhận Gateway cho phép POST.

> Trên PowerShell 5.1, `curl` có thể là alias của `Invoke-WebRequest`. Khi muốn cú pháp curl chuẩn, dùng `curl.exe` và viết các lệnh có dấu `\` nối dòng thành một dòng. Không đưa access token thật vào lịch sử lệnh, log CI hoặc báo cáo lỗi; dùng secret của môi trường test và thu hồi khi xong.

### 9.7. Bảng kiểm thử tối thiểu

| Ca thử | HTTP kỳ vọng | `WWW-Authenticate` | Backend có được gọi? |
|---|---:|---|---|
| Không Bearer token | `401` | `Bearer`, thường không `error` | Không |
| JWT sai chữ ký/hết hạn | `401` | `Bearer` với `invalid_token` khi xác định được | Không |
| Bearer request sai cấu trúc | Thường `400` | `invalid_request` theo RFC | Không |
| JWT hợp lệ, thiếu `orders:read` | `403` | Với native handler có thể chỉ ra `insufficient_scope` | Không |
| JWT hợp lệ có `orders:read`, GET, backend khỏe | `200` từ backend | Không bắt buộc | Có |
| JWT hợp lệ chỉ có read, gọi POST cần write | `403` | Tùy handler/policy scope | Không |
| JWT hợp lệ, backend trả 404 | `404` từ backend | Không phải auth challenge | Có |
| JWT hợp lệ, backend hỏng | `5xx` hoặc fallback theo cấu hình | Không tự thay bằng `401` | Có nỗ lực proxy |

Chạy test với cả hai kiểu handler và ghi nhận sự khác biệt giữa **HTTP semantics** và **JSON contract**.

## 10. CORS: trình duyệt có thể bị chặn trước khi thấy 401/403

Với SPA chạy trên `https://app.example.test` gọi Gateway ở một origin khác, browser có thể gửi `OPTIONS` **preflight** trước request có header `Authorization`. Preflight thường không mang Bearer token; nếu Security từ chối ngay bằng `401`, JavaScript có thể chỉ nhìn thấy lỗi CORS thay vì body JSON thực sự.

**CORS phải được xử lý trước các bước security phụ thuộc vào credentials của request thực**. Với Gateway Server WebFlux, có thể cấu hình CORS ở Gateway, hoặc dùng `CorsWebFilter`/Spring Security reactive integration. Không chỉ thêm `OPTIONS` vào route `Method` rồi coi là đã xử lý CORS.

### 10.1. Ví dụ CORS cho WebFlux Security

Một cách rõ ràng là cung cấp `UrlBasedCorsConfigurationSource` trong ứng dụng:

```java
import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource;

@Configuration
public class ApiCorsConfiguration {
    @Bean
    UrlBasedCorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration config = new CorsConfiguration();
        config.setAllowedOrigins(List.of("https://app.example.test"));
        config.setAllowedMethods(List.of("GET", "POST", "OPTIONS"));
        config.setAllowedHeaders(
                List.of("Authorization", "Content-Type", "X-Request-Id"));
        config.setExposedHeaders(
                List.of("WWW-Authenticate", "X-Request-Id"));
        config.setAllowCredentials(false);

        UrlBasedCorsConfigurationSource source =
                new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/**", config);
        return source;
    }
}
```

Trong `SecurityWebFilterChain`, thêm:

```java
.cors(Customizer.withDefaults())
```

ở vị trí thích hợp trong fluent DSL trước `.build()`. Không tạo nhiều cấu hình CORS mâu thuẫn giữa Security, Gateway và ingress.

- `allowedOrigins` nên là danh sách origin đã được tin, không dùng wildcard tùy ý khi cho phép credentials.
- `allowedHeaders` phải cho phép request header cần thiết, ví dụ `Authorization`.
- `exposedHeaders` giúp JavaScript có thể đọc `WWW-Authenticate` và `X-Request-Id` khi CORS policy cho phép.
- `allowCredentials(false)` phù hợp ví dụ API Bearer-only; nếu dùng cookies/session, phải thiết kế riêng `allowCredentials`, CSRF, SameSite và origin allowlist.

### 10.2. Kiểm thử preflight

```bash
curl -i -X OPTIONS http://localhost:8080/api/orders/42 \
  -H "Origin: https://app.example.test" \
  -H "Access-Control-Request-Method: GET" \
  -H "Access-Control-Request-Headers: Authorization"
```

Hãy kiểm tra status, `Access-Control-Allow-Origin`, allowed methods/headers và xem request **GET thực** có thể tới Gateway hay không. Nếu không có các header cho origin hợp lệ, browser sẽ chặn việc đọc response, dù API có thể đã trả body Problem Details trên mạng.

Với Gateway 5.0, cấu hình thay thế ở tầng Gateway có property `spring.cloud.gateway.server.webflux.globalcors.cors-configurations`. Nếu route có `Method=GET` khiến `OPTIONS` không match, hãy xem thêm `globalcors.add-to-simple-url-handler-mapping`. Chọn một phương án CORS có chủ đích và kiểm thử cả path **có** lẫn **không** khớp Gateway route.

## 11. Chuẩn hóa lỗi bảo mật không làm lẫn các loại lỗi khác

Gateway còn có rate limiter, circuit breaker, retry, TLS và cơ chế proxy. Chúng tạo những kết quả HTTP **khác** auth/authorization:

| Tình huống | Lớp phát sinh | Mã thường thấy | Cách xử lý |
|---|---|---|---|
| Không có access token | Spring Security | `401` | Challenge Bearer hợp lệ |
| Có token nhưng thiếu quyền | Spring Security/backend | `403` | Không tự làm mới token liên tục |
| Tài nguyên không tồn tại | Backend/router | `404` | Kiểm tra nghiệp vụ/path |
| Body/request không hợp lệ | Gateway/backend | `400`/`413` | Sửa payload hoặc giảm kích thước |
| RequestRateLimiter từ chối | Gateway filter | `429` | Tôn trọng giới hạn và `Retry-After` nếu có |
| Backend lỗi kết nối | Gateway HTTP client | `502`/`503`/`504` tùy trường hợp | Theo dõi upstream, timeout và fallback |
| Circuit breaker mở | Gateway filter | `5xx` hoặc response fallback theo cấu hình | Theo dõi trạng thái circuit, không giả thành 401 |
| TLS handshake client → Gateway thất bại | TLS terminator | Thường **không có HTTP status** | Kiểm tra cert/CA/SAN/protocol |
| mTLS Gateway → backend thất bại | Gateway HTTP client/TLS | Lỗi proxy `5xx` | Kiểm tra certificate/trust outbound |

**Không viết một error filter thay mọi `4xx`/`5xx` thành `200` kèm JSON `{"success":false}`.** Cách đó khiến client, load balancer, metrics và retry policy hiểu sai kết quả; đồng thời phá semantics của `WWW-Authenticate` và `Retry-After`.

### 11.1. Hạn chế retry với lỗi xác thực

- `401` vì token hết hạn: client có thể xin token hợp lệ **một lần theo chính sách** rồi thử lại; không đặt một vòng retry vô hạn trên cùng token.
- `403` vì thiếu quyền: refresh cùng credential thường không tạo quyền mới. Tránh retry vô ích.
- `429`: tôn trọng policy rate limiting/backoff.
- `5xx`/timeout: retry phải xét idempotency, số lần thử, timeout tổng và circuit breaker; với `POST /payments` có nguy cơ gây giao dịch trùng.

### 11.2. Chặn giả mạo header định danh nội bộ

Header `X-Internal-User-Id` do client gửi **không** là bằng chứng danh tính. Khi Gateway xác thực JWT và muốn cung cấp user ID cho backend, cần loại bỏ header nội bộ đầu vào rồi tạo lại từ principal đã kiểm chứng, đồng thời khóa truy cập trực tiếp backend.

Nếu hệ thống dùng correlation ID, hãy tạo hoặc xác nhận request ID từ ingress/`WebFilter` tin cậy **trước bước xác thực** để cả lỗi `401`/`403` và request thành công đều được liên kết. Một `GlobalFilter` của Gateway có thể không chạy cho request bị Security từ chối trước route; do đó không nên coi nó là nơi bao phủ mọi lỗi xác thực.

## 12. Logging, tracing và observability cho 401/403

Mục tiêu quan sát không chỉ là đếm bao nhiêu response `401`, `403` mà còn giúp phân biệt **token thiếu**, **token không hợp lệ**, **authorization policy từ chối** và **backend trả lỗi**.

Một sự kiện log an toàn có thể chứa:

```json
{
  "event": "gateway.security.denied",
  "requestId": "8fa0c97f-a5c2-4bca-9f93-b26ab23563f3",
  "routePattern": "/api/orders/**",
  "method": "GET",
  "status": 403,
  "code": "ACCESS_DENIED",
  "authMethod": "bearer",
  "source": "gateway-security",
  "durationMs": 7
}
```

Đây là dữ liệu minh họa. Đặc biệt, `routePattern` nên là mẫu route (không chứa số đơn hàng thật) khi cần hạn chế cardinality trong metrics. Trước route matching, bạn có thể **chưa có route ID**, vì vậy log auth rejection không nên giả rằng trường này luôn có.

### 12.1. Những gì nên ghi và không nên ghi

| Nên ghi | Không nên ghi trong log thường |
|---|---|
| `requestId`, `traceId` đã chuẩn hóa | Raw Bearer token hoặc refresh token |
| HTTP status và error code ổn định | Toàn bộ `Authorization`, `Cookie`, `Set-Cookie` |
| Phân loại lỗi `missing`/`invalid`/`denied` ở mức an toàn | Raw JWT claim chứa dữ liệu cá nhân |
| Tên policy/route pattern đã được phê duyệt | Nội dung response/debug stacktrace trả cho client |
| Thời gian xử lý, tỷ lệ lỗi theo nhóm | Password, private key, session ID |
| Nguồn kết quả: gateway security hay backend | Header nội bộ do client tự gửi mà chưa kiểm chứng |

Với `401` liên tục tăng, hãy xác định có phải ứng dụng hết hạn token hàng loạt, IdP đổi key/issuer, đồng hồ hệ thống lệch hoặc ứng dụng đang gửi credentials sai. Với `403` tăng, kiểm tra quyền/role/scope, rollout policy và phân quyền theo tài nguyên.

### 12.2. Alert và phân tích nguồn phát sinh

Các nhóm chỉ số hữu ích:

- `http.server.requests` hoặc metric tương đương, phân loại theo status code, route pattern và nguồn khi có.
- Tỷ lệ `401`/`403` theo client application/tenant **đã xác thực**, tránh gắn user ID/cardinality cao trực tiếp vào metric label.
- Lỗi token validation do không truy cập JWKS/IdP so với token sai thực sự.
- Số `403` sau khi thay đổi chính sách role/scope.
- Số `429` từ rate limiter và `5xx` từ backend, không cộng tất cả vào một nhóm “authentication failures”.
- Tỷ lệ CORS preflight thất bại cho các frontend origin được phép.

Không mặc định rằng mọi lỗi không kết nối được JWKS đều do **token không hợp lệ**; đôi khi đó là **hạ tầng xác minh không sẵn sàng**. Quy tắc xử lý phải fail closed cho truy cập bảo vệ, nhưng cảnh báo và nguyên nhân nội bộ cần phản ánh sự khác nhau để đội vận hành sửa đúng.

## 13. Những lỗi cấu hình thường gặp

| Hiện tượng | Nguyên nhân cần kiểm tra | Cách khắc phục |
|---|---|---|
| Không có token nhưng phản hồi `403` | Một handler/CSRF policy xử lý trước auth hoặc cấu hình exception handling sai | Kiểm tra `SecurityWebFilterChain` và loại API có session/CSRF hay không |
| Token hết hạn nhưng client chỉ thấy `403` | Lỗi xác thực bị ánh xạ thành access denied | Dùng entry point cho `AuthenticationException`; kiểm tra JWT validation |
| 403 bị đổi thành 401 sau khi qua Gateway | Error rewrite filter ghi đè status hoặc xử lý chung mọi security error | Phân loại lỗi đúng lớp; không thay status tùy tiện |
| Thiếu `WWW-Authenticate` trên 401 Bearer | Custom JSON handler quên challenge | Dùng built-in Bearer entry point hoặc tự tạo challenge theo RFC 6750 |
| Mọi 403 có `insufficient_scope` | Handler giả định mọi denial là thiếu scope | Chỉ dùng khi policy xác nhận thiếu scope; dùng `ACCESS_DENIED` cho denial chung |
| Client refresh token vô hạn | Frontend coi mọi 403 là token hết hạn hoặc retry mọi 401 | Retry có giới hạn, phân biệt 401/403 và OAuth code |
| SPA báo CORS error thay vì 401 JSON | Preflight bị chặn, response không có CORS headers | Cấu hình CORS trước Security, test `OPTIONS` và expose headers |
| JWT hợp lệ vẫn nhận 401 | Issuer/audience/clock/key/algorithm chưa khớp hoặc token dành cho API khác | Kiểm tra validation, JWKS và môi trường IdP |
| JWT có `scope=orders:read` nhưng vẫn 403 | Authority mapping không đúng `SCOPE_orders:read` hoặc converter tùy biến | Kiểm tra authorities đã được xác minh, không dựa vào token chưa xác thực |
| `@RestControllerAdvice` không bắt 401 | Lỗi phát sinh ở Spring Security WebFilter trước controller | Đặt `ServerAuthenticationEntryPoint` và `ServerAccessDeniedHandler` |
| `GlobalFilter` không ghi log cho 401 | Request bị từ chối trước Gateway route/filter | Đưa correlation/observability đến ingress hoặc WebFilter sớm |
| JWT có read scope nhưng truy cập đơn hàng người khác được | Chỉ kiểm tra scope tại Gateway, backend thiếu ownership check | Áp dụng authorization theo tài nguyên ở backend |
| Client gửi `X-Internal-Role: admin` và được quyền | Gateway/backend tin header nội bộ từ Internet | Xóa/sanitize, chỉ tạo từ principal đã xác thực; khóa backend |
| Request qua route trả 401 dù Gateway đã xác thực | Backend tự xác thực token riêng, token Gateway→backend không hợp lệ | Phân biệt nguồn 401 và trust/service-to-service credential |
| Token sai nhưng HTTP trả `200` + error JSON | Handler chuẩn hóa phá HTTP semantics | Trả đúng `401`/`403`, phù hợp RFC và hợp đồng API |
| `401` bị cache và phục vụ nhầm | Cache configuration không phù hợp | Đặt `Cache-Control: no-store` cho error response nhạy cảm |
| Các service trả body khác nhau | Chưa thống nhất error contract | Công bố schema/version, áp dụng ở Gateway **và** backend |

**Không nên “sửa” 401/403 bằng cách thêm `permitAll()` rộng để hệ thống chạy qua test.** Với Gateway công khai, policy phải là **default deny hoặc explicit allow** theo thiết kế; việc mở quyền để che lỗi cấu hình có thể tạo lỗ hổng.

## 14. Một checklist triển khai cho team API Gateway

- [ ] Có hợp đồng rõ ràng về `401` (chưa xác thực), `403` (đã xác thực nhưng bị từ chối), `400` (Bearer request sai cấu trúc) và `404` theo resource policy.
- [ ] Dùng Spring Security WebFlux Reactive Resource Server, không lấy JWT claim từ request body/header mà chưa xác minh.
- [ ] Validate chữ ký, issuer, thời hạn, audience và policy scope/authority theo hợp đồng API.
- [ ] `WWW-Authenticate` đúng scheme; không ghi `invalid_token` cho mọi request thiếu token.
- [ ] `insufficient_scope` chỉ sử dụng cho thiếu scope thực sự; không tiết lộ role/tenant nhạy cảm.
- [ ] Status HTTP và `status` trong Problem Details JSON luôn khớp nhau.
- [ ] Mã ứng dụng như `AUTHENTICATION_REQUIRED` và `ACCESS_DENIED` được định nghĩa và versioning rõ ràng.
- [ ] Không trả stacktrace, token, key, password, thông tin chữ ký, user ID hoặc chính sách nội bộ trong `detail`.
- [ ] Xử lý `Cache-Control` cho phản hồi auth nhạy cảm; cân nhắc rate limiting đối với login/token endpoint.
- [ ] Đã cấu hình CORS preflight cho frontend origin hợp lệ, không bỏ qua CSRF khi có cookie/session authentication.
- [ ] Đã phân biệt lỗi từ Gateway Security, ingress, Backend Security và lỗi proxy/timeout.
- [ ] Không cho client tự gắn header `X-Internal-User-Id`/`X-Internal-Role` được backend tin ngay.
- [ ] Backend kiểm tra ownership/tenant/resource, không chỉ tin vào scope chung của Gateway.
- [ ] Có request/trace ID chuẩn hóa trước security cho cả response thành công và từ chối.
- [ ] Có test 401/403 thiếu token, token hết hạn, token sai issuer, token thiếu scope, token đủ scope, CORS và backend 401/403.
- [ ] Có dashboard/alert theo nhóm lỗi, không log raw `Authorization`/`Cookie`.
- [ ] Retry/fallback không đổi lỗi xác thực thành mã thành công hoặc lặp request vô hạn.

## 15. Tình huống thiết kế: ba backend có cùng error contract

Giả sử Gateway có ba nhóm API:

| API | Policy tại Gateway | Policy còn cần ở backend |
|---|---|---|
| `GET /api/catalog/**` | Có thể public hoặc cần `SCOPE_catalog:read` | Chặn dữ liệu không công khai theo sản phẩm/tenant |
| `GET /api/orders/**` | Bắt buộc token có `SCOPE_orders:read` | Kiểm tra user có sở hữu đơn hàng |
| `POST /api/payments/**` | Token có `SCOPE_payments:write` | Giới hạn quyền thanh toán, chống replay/idempotency |

Team thống nhất JSON Problem Details `status`, `code` và `requestId`. Nhưng cách áp dụng phải theo từng **nguồn lỗi**:

- **Gateway** sinh 401 khi token thiếu/hết hạn và 403 khi policy trước routing từ chối.
- **Order-service** sinh 403 hoặc 404 theo chính sách ownership, dù token hợp lệ tại Gateway.
- **Payment-service** có thể sinh 409 khi yêu cầu trùng idempotency key hoặc 422 vì nghiệp vụ; đừng chuẩn hóa thành 401 chỉ vì payment liên quan “ủy quyền”.
- **Rate limiter** sinh 429, **circuit breaker** có thể sinh fallback/5xx; chúng dùng cùng định dạng lỗi nếu mong muốn nhưng **khác HTTP status và `code`**.
- **TLS/mTLS** sai certificate có thể thất bại trước khi hình thành HTTP response; JSON Problem Details không giải quyết lỗi handshake ở TLS terminator.

## 16. Câu hỏi tự kiểm tra

**Câu 1.** Client gọi API cần JWT mà không gửi `Authorization`. Nên trả `401` hay `403`?

**Đáp án:** `401`, kèm `WWW-Authenticate: Bearer ...` nếu đây là Bearer-protected resource.

**Câu 2.** JWT đã xác minh nhưng chỉ có `orders:read`, client gọi `POST /api/orders` yêu cầu `orders:write`. Trả gì?

**Đáp án:** `403 Forbidden`. Nếu đã xác nhận thiếu scope, có thể dùng Bearer `insufficient_scope` và scope cần thiết theo RFC 6750.

**Câu 3.** Request hoàn toàn thiếu token có cần `error="invalid_token"` trong `WWW-Authenticate` không?

**Đáp án:** Không. RFC 6750 khuyến nghị không nêu error code khi request thiếu authentication information.

**Câu 4.** Vì sao `@RestControllerAdvice` không luôn bắt 401 do Resource Server?

**Đáp án:** Lỗi có thể phát sinh trong Spring Security WebFilter trước controller. Phải cấu hình `ServerAuthenticationEntryPoint` / `ServerAccessDeniedHandler`.

**Câu 5.** `code: ACCESS_DENIED` trong Problem Details có phải một field tiêu chuẩn bắt buộc của RFC 9457 không?

**Đáp án:** Không. Nó là extension field do ứng dụng quy định. Các field `type`, `title`, `status`, `detail`, `instance` có semantics theo RFC; không phải tất cả đều bắt buộc xuất hiện.

**Câu 6.** Backend trả HTTP 403 sau khi Gateway đã proxy thành công. Entry point `401` của Gateway có tự sửa body đó không?

**Đáp án:** Không. Đó là response từ backend; muốn schema chung cần backend tuân theo hợp đồng hoặc một response transformation được thiết kế riêng.

**Câu 7.** Vì sao browser có thể báo CORS error dù `curl` thấy JSON 401?

**Đáp án:** Browser yêu cầu preflight và CORS response headers phù hợp. Nếu Security từ chối `OPTIONS` hoặc response thiếu `Access-Control-Allow-Origin`, JavaScript không đọc được body như khi dùng curl.

**Câu 8.** Một `GlobalFilter` viết log ID không thấy request bị từ chối 401. Vì sao?

**Đáp án:** Request có thể bị Spring Security xử lý trước Gateway route/filter chain. Để bao phủ mọi request, tạo correlation ID sớm ở ingress hoặc WebFilter thích hợp.

**Câu 9.** Có nên trả raw exception `JWT signature mismatch at key-2026-prod` trong `detail`?

**Đáp án:** Không. Client không cần biết implementation/key metadata; dùng code công khai và log nội bộ an toàn.

**Câu 10.** Client thấy 403 do không sở hữu đơn hàng 42 nhưng token có `orders:read`. Có nên tự động refresh token?

**Đáp án:** Không. Đây là từ chối quyền trên tài nguyên, token refresh thường không thay đổi ownership.

**Bài tập mở rộng:** Từ cấu hình Security ở mục 6, tạo bảng test có ít nhất 8 trường hợp: thiếu token, token sai chữ ký, sai issuer, hết hạn, thiếu scope, đủ scope, browser preflight, backend trả 403. Với mỗi trường hợp ghi rõ **lớp phát sinh**, **HTTP status**, **`WWW-Authenticate`**, **`code`**, **backend có được gọi không** và **hành vi frontend**. Sau đó chọn một trong hai phương án handler ở mục 6/7 và viết automated integration tests tương ứng trước khi đưa vào production.

## 17. Tài liệu tham khảo

- [RFC 9110 — HTTP Semantics, 401 và 403](https://www.rfc-editor.org/rfc/rfc9110).
- [RFC 6750 — OAuth 2.0 Bearer Token Usage, `WWW-Authenticate` và error codes](https://www.rfc-editor.org/rfc/rfc6750).
- [RFC 9457 — Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457).
- [Spring Security 7.0 — Reactive OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/7.0/reactive/oauth2/resource-server/jwt.html).
- [Spring Security 7.0 — Reactive Bearer Tokens](https://docs.spring.io/spring-security/reference/7.0/reactive/oauth2/resource-server/bearer-tokens.html).
- [Spring Security — `ServerHttpSecurity.ExceptionHandlingSpec` Javadoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.ExceptionHandlingSpec.html).
- [Spring Security — `BearerTokenServerAuthenticationEntryPoint` Javadoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/web/server/BearerTokenServerAuthenticationEntryPoint.html).
- [Spring Security — `BearerTokenServerAccessDeniedHandler` Javadoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/web/access/server/BearerTokenServerAccessDeniedHandler.html).
- [Spring Security — Reactive CORS](https://docs.spring.io/spring-security/reference/7.0/reactive/integrations/cors.html).
- [Spring Framework 7.0 — WebFlux Error Responses / ProblemDetail](https://docs.spring.io/spring-framework/reference/web/webflux/ann-rest-exceptions.html).
- [Spring Cloud Gateway 5.0 — CORS Configuration](https://docs.spring.io/spring-cloud-gateway/reference/5.0/spring-cloud-gateway-server-webflux/cors-configuration.html).
- [Spring Cloud Gateway 5.0 — How It Works](https://docs.spring.io/spring-cloud-gateway/reference/5.0/spring-cloud-gateway-server-webflux/how-it-works.html).
- [Spring Boot 4.0 — Starter dependencies](https://docs.spring.io/spring-boot/4.0/reference/using/build-systems.html).

**Ghi nhớ:** `401` cho biết client chưa chứng thực hợp lệ, `403` cho biết request đã được xác thực nhưng bị từ chối; `WWW-Authenticate` phải tuân theo giao thức Bearer khi dùng OAuth2. **Problem Details chuẩn hóa JSON, không thay thế HTTP semantics**. Trong Gateway WebFlux, hãy đặt logic tại đúng lớp Spring Security, bảo vệ response khỏi lộ thông tin nhạy cảm, phân biệt lỗi backend và kiểm thử đầy đủ các nhánh trước khi vận hành cổng vào microservices.
