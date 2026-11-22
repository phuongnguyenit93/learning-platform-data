# Kiểm tra 401, 403, challenge và phản hồi lỗi API

## 1. Phân biệt authentication và authorization

Một Spring Security WebFlux Resource Server phải trả lời hai câu hỏi độc lập:

1. Caller đã được xác thực bằng credential hợp lệ chưa?
2. Principal đã xác thực có quyền thực hiện hành động này không?
**401 Unauthorized**: request chưa có authentication hợp lệ. Có thể thiếu Bearer token, token sai chữ ký, hết hạn, sai issuer/audience hoặc introspection xác nhận inactive.

**403 Forbidden**: principal đã xác thực nhưng không được phép thực hiện hành động. Ví dụ thiếu scope, không thuộc tenant hoặc không sở hữu resource.

Ví dụ:

~~~text
GET /api/orders
No Authorization header
  -> Không có authentication
  -> 401 + WWW-Authenticate: Bearer

GET /api/orders
Authorization: Bearer <expired-token>
  -> Credential không hợp lệ
  -> 401 + Bearer error="invalid_token"

POST /api/orders
Authorization: Bearer <valid-token-with-orders.read>
  -> Authentication thành công, thiếu orders.write
  -> 403 + Bearer error="insufficient_scope" khi phù hợp

POST /api/orders
Authorization: Bearer <valid-token-with-orders.write>
  -> Authentication và authorization đạt
  -> API tiếp tục xử lý nghiệp vụ
~~~

**401 là lỗi authentication; 403 là lỗi authorization.** Không trả 403 cho token hết hạn và không yêu cầu client đăng nhập lại chỉ vì principal hợp lệ thiếu quyền.

Một số 403 có thể đến từ CSRF, CORS, gateway hoặc network policy. Phải xác định đúng thành phần đã từ chối request.

## 2. Luồng WebFlux Resource Server

~~~mermaid
sequenceDiagram
    participant C as Client
    participant W as WebFlux Security Filters
    participant B as Bearer Converter
    participant M as ReactiveAuthenticationManager
    participant D as JWT Decoder / Opaque Introspector
    participant A as Authorization
    participant H as Handler

    C->>W: Request + Authorization Bearer
    W->>B: Extract credential
    B-->>W: Bearer authentication request
    W->>M: authenticate
    M->>D: verify JWT or introspect opaque token
    alt Authentication fails
      D-->>M: Authentication exception
      M-->>W: Failure
      W-->>C: AuthenticationEntryPoint -> 401
    else Authentication succeeds
      D-->>M: Valid principal
      M-->>W: Authentication
      W->>A: Check authority and access rules
      alt Authorization denied
        A-->>W: AccessDeniedException
        W-->>C: AccessDeniedHandler -> 403
      else Authorization granted
        A->>H: Invoke handler
        H-->>C: API response
      end
    end
~~~

Các thành phần:

| Thành phần | Vai trò |
|---|---|
| **ServerBearerTokenAuthenticationConverter** | Trích Bearer token từ ServerWebExchange |
| **AuthenticationWebFilter** | Thực hiện reactive authentication |
| **ReactiveAuthenticationManager** | Xác thực credential theo strategy đã cấu hình |
| **ReactiveJwtDecoder** | Verify và validate JWT |
| **ReactiveOpaqueTokenIntrospector** | Xác minh opaque token qua introspection |
| **ExceptionTranslationWebFilter** | Chuyển authentication/authorization exceptions thành HTTP response |
| **ServerAuthenticationEntryPoint** | Bắt đầu authentication challenge, thường là 401 |
| **ServerAccessDeniedHandler** | Xử lý authorization denial, thường là 403 |
| **SecurityWebFilterChain** | Chuỗi WebFilters bảo vệ request |
| **ServerHttpSecurity** | DSL cấu hình WebFlux Security |

Servlet stack có các API khác tên: AuthenticationEntryPoint, AccessDeniedHandler, HttpSecurity và SecurityFilterChain. Bài này tập trung vào **WebFlux reactive APIs**.

### Authentication failure xảy ra trước controller

JWT sai chữ ký thường bị từ chối trong AuthenticationWebFilter/Resource Server flow trước khi controller chạy. Vì thế **@RestControllerAdvice** không phải nơi chính để xử lý Bearer challenge.

Authorization có thể thất bại ở authorizeExchange trong filter chain hoặc ở reactive method security như @PreAuthorize.

## 3. 401: thiếu hoặc không có authentication hợp lệ

| Tình huống | Nguyên nhân | Kết quả thường gặp |
|---|---|---|
| Không gửi Authorization trên protected route | Thiếu credential | 401 challenge |
| Bearer header không có token | Request malformed | 400 invalid_request hoặc lỗi parser tương ứng |
| Token malformed | Không parse được credential | 401 invalid_token |
| JWT signature sai | Không xác minh được nguồn ký | 401 invalid_token |
| JWT issuer sai | Không thuộc trust domain | 401 invalid_token |
| JWT audience sai | Token không dành cho API này | 401 invalid_token |
| JWT hết hạn | exp đã qua theo time policy | 401 invalid_token |
| JWT chưa tới nbf | Token chưa có hiệu lực | 401 invalid_token |
| Opaque token active=false | AS không xác nhận token active | 401 invalid_token |
| Token type/profile sai | Không đúng access-token contract | 401 invalid_token |

Với protected resource, request không có authentication hợp lệ thường nhận:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
~~~

Khi caller đã gửi Bearer token nhưng token invalid:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
~~~

### Không có token khác với token invalid

Khi caller không gửi authentication information, server thường gửi challenge mà không cần error code. Khi caller đã trình bày token nhưng token không hợp lệ, challenge có thể chứa error="invalid_token".

Khác biệt này giúp client hiểu:
- Không có token: cần lấy credential.
- Token invalid/expired: có thể cần xin token mới.
- Thiếu scope: cần quyền phù hợp hoặc grant khác.

Không đưa raw JWT, key ID, JWKS URL nội bộ, stack trace hoặc toàn bộ claims vào error response.

## 4. 403: principal đã xác thực nhưng không được phép

Giả sử JWT đã được xác minh:

~~~json
{
  "iss": "https://auth.example.com/realms/shop",
  "sub": "user-42",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "exp": 1794731400
}
~~~

GET có thể được phép, nhưng POST cần orders.write sẽ bị từ chối:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope"
~~~

Khi phù hợp, challenge có thể nêu scope cần thiết:

~~~http
WWW-Authenticate: Bearer error="insufficient_scope", scope="orders.write"
~~~

**403 không có nghĩa token sai.** Nó có thể có nghĩa token hợp lệ nhưng thiếu quyền.

### 403 không phải lúc nào cũng là insufficient_scope

Một request có thể bị từ chối vì:
- User không thuộc tenant sở hữu resource.
- User không phải owner của order.
- Order đã ở trạng thái không cho phép chỉnh sửa.
- Domain policy cấm hành động.
- CSRF token thiếu hoặc sai.
- Gateway/IP/network policy từ chối.
- Một role nội bộ khác đang được yêu cầu.

Không gắn insufficient_scope cho mọi AccessDeniedException. Nếu token đã có scope yêu cầu nhưng tenant mismatch, error code insufficient_scope có thể làm client hiểu sai.

## 5. Ba Bearer error codes theo RFC 6750

| Error | HTTP status điển hình | Ý nghĩa |
|---|---:|---|
| **invalid_request** | 400 | Request truyền Bearer credential sai, thiếu field hoặc có nhiều phương thức truyền token mâu thuẫn |
| **invalid_token** | 401 | Token expired, revoked, malformed hoặc không hợp lệ |
| **insufficient_scope** | 403 | Token thiếu scope cần cho resource |

Ví dụ:

~~~http
HTTP/1.1 400 Bad Request
WWW-Authenticate: Bearer error="invalid_request"
~~~

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
~~~

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope", scope="orders.write"
~~~

Các parameters như realm, error_description và error_uri là tùy chọn theo contract. Không phải mọi response đều cần có tất cả.

### Không lộ thông tin trong error_description

Không gửi:
- Raw access token.
- Chữ ký, private key hoặc shared secret.
- Stack trace.
- Full JWT claims/PII.
- JWKS host hoặc topology nội bộ.
- Chi tiết account bị khóa nếu điều đó tiết lộ dữ liệu nhạy cảm.

Thông điệp an toàn có thể là **The access token is invalid** hoặc **The request is not permitted**. Ghi chi tiết kỹ thuật trong logs có kiểm soát và gắn correlation ID.

## 6. WWW-Authenticate là một phần của HTTP response

Với HTTP 401, server phải gửi ít nhất một WWW-Authenticate challenge theo HTTP semantics. Với OAuth Bearer, authentication scheme là Bearer.

Challenge đơn giản:

~~~http
WWW-Authenticate: Bearer
~~~

Có realm:

~~~http
WWW-Authenticate: Bearer realm="orders-api"
~~~

Token invalid:

~~~http
WWW-Authenticate: Bearer realm="orders-api", error="invalid_token"
~~~

Thiếu scope:

~~~http
WWW-Authenticate: Bearer realm="orders-api", error="insufficient_scope", scope="orders.write"
~~~

Client dùng challenge để biết scheme, trạng thái credential, scope cần thiết và hành vi lấy token mới. JSON body không thay thế header challenge.

Không ghép raw exception message hoặc caller input vào challenge header. Dùng Spring Security Bearer handlers để giữ grammar và semantics.

## 7. Reactive handlers có sẵn trong Spring Security

| Class | Package | Trách nhiệm |
|---|---|---|
| **BearerTokenServerAuthenticationEntryPoint** | org.springframework.security.oauth2.server.resource.web.server | Tạo Bearer challenge khi authentication thất bại |
| **BearerTokenServerAccessDeniedHandler** | org.springframework.security.oauth2.server.resource.web.server | Xử lý access denied và Bearer challenge khi phù hợp |

Các interface:

| Interface | Package | Method |
|---|---|---|
| **ServerAuthenticationEntryPoint** | org.springframework.security.web.server | commence(ServerWebExchange, AuthenticationException) |
| **ServerAccessDeniedHandler** | org.springframework.security.web.server.authorization | handle(ServerWebExchange, AccessDeniedException) |

Signature reactive:

~~~java
Mono<Void> commence(
        ServerWebExchange exchange,
        AuthenticationException exception);

Mono<Void> handle(
        ServerWebExchange exchange,
        AccessDeniedException exception);
~~~

Handlers trả **Mono<Void>**. Không dùng HttpServletResponse.sendError() hoặc Servlet AuthenticationEntryPoint trong WebFlux.

Khi cấu hình:

~~~java
.oauth2ResourceServer(oauth2 ->
        oauth2.jwt(Customizer.withDefaults()))
~~~

Spring Security thiết lập Bearer authentication behavior và handlers phù hợp. Không cần tự viết entry point chỉ để có 401/403 chuẩn.

Nếu muốn JSON error body riêng, có thể decorate handlers có sẵn để giữ status/challenge rồi thêm body.

## 8. Cấu hình ServerHttpSecurity cho 401 và 403

Ví dụ WebFlux JWT Resource Server:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.oauth2.server.resource.web.server.BearerTokenServerAccessDeniedHandler;
import org.springframework.security.oauth2.server.resource.web.server.BearerTokenServerAuthenticationEntryPoint;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class ApiSecurityConfiguration {

    @Bean
    SecurityWebFilterChain api(ServerHttpSecurity http) {
        BearerTokenServerAuthenticationEntryPoint entryPoint =
                new BearerTokenServerAuthenticationEntryPoint();
        entryPoint.setRealmName("orders-api");

        BearerTokenServerAccessDeniedHandler deniedHandler =
                new BearerTokenServerAccessDeniedHandler();

        return http
                .authorizeExchange(auth -> auth
                        .pathMatchers("/api/public/**").permitAll()
                        .pathMatchers(HttpMethod.GET, "/api/orders/**")
                            .hasAuthority("SCOPE_orders.read")
                        .pathMatchers(HttpMethod.POST, "/api/orders/**")
                            .hasAuthority("SCOPE_orders.write")
                        .anyExchange().authenticated())
                .exceptionHandling(ex -> ex
                        .authenticationEntryPoint(entryPoint)
                        .accessDeniedHandler(deniedHandler))
                .oauth2ResourceServer(oauth2 -> oauth2
                        .authenticationEntryPoint(entryPoint)
                        .accessDeniedHandler(deniedHandler)
                        .jwt(Customizer.withDefaults()))
                .build();
    }
}
~~~

Ý nghĩa:
- ServerHttpSecurity là DSL WebFlux.
- BearerTokenServerAuthenticationEntryPoint tạo 401 challenge.
- setRealmName đặt realm.
- BearerTokenServerAccessDeniedHandler xử lý 403.
- exceptionHandling đặt handlers cho exception translation.
- oauth2ResourceServer đặt handlers cho Bearer authentication path.
- Authorization rule phân biệt read và write scopes.

Các DSL methods có thể thay đổi giữa các Spring Security versions. Kiểm tra dependency thực tế nếu một method không có. Không thay reactive handlers bằng Servlet handlers.

Opaque token cũng có cùng error boundary:

~~~java
.oauth2ResourceServer(oauth2 -> oauth2
        .authenticationEntryPoint(entryPoint)
        .accessDeniedHandler(deniedHandler)
        .opaqueToken(Customizer.withDefaults()))
~~~

Opaque token active=false thường dẫn tới authentication failure/401. Token active nhưng thiếu scope dẫn tới authorization denial/403.

## 9. Missing token, malformed Bearer và invalid token

Không có token:

~~~http
GET /api/orders HTTP/1.1
Host: api.example.com
~~~

Protected route thường trả:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api"
~~~

Bearer header malformed:

~~~http
GET /api/orders HTTP/1.1
Host: api.example.com
Authorization: Bearer
~~~

Có thể trả 400 invalid_request tùy parser và version. Hãy kiểm thử với Spring Security version thực tế thay vì giả định mọi malformed header có cùng mapping.

Token được gửi nhưng invalid:

~~~http
GET /api/orders HTTP/1.1
Host: api.example.com
Authorization: Bearer expired-or-invalid-token
~~~

Response điển hình:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api", error="invalid_token"
~~~

Không dùng query parameter access_token làm đường dự phòng khi header Bearer invalid. RFC 6750 khuyến nghị client chỉ dùng một phương thức truyền Bearer token trong request.

## 10. Thiếu scope khác với domain permission

Một token chỉ có orders.read:

~~~json
{
  "scope": "orders.read"
}
~~~

Khi POST yêu cầu orders.write, authorization manager từ chối. Đây là trường hợp phù hợp với insufficient_scope.

Nhưng một token có orders.write vẫn có thể không được sửa order thuộc tenant khác:

~~~text
Authentication:
  SCOPE_orders.write

Domain:
  order 42 belongs to tenant-blue
  caller belongs to tenant-red
~~~

Đây là domain authorization failure. API có thể trả 403 generic:

~~~http
HTTP/1.1 403 Forbidden
Content-Type: application/problem+json
~~~

Không nhất thiết thêm Bearer insufficient_scope vì token đã có scope. Client cần biết hành động bị cấm theo resource policy.

Một số API trả 404 thay vì 403 để không tiết lộ resource có tồn tại hay không cho caller không có quyền. Đây là lựa chọn security/domain contract, không phải quy tắc bắt buộc.
## 11. Custom JSON error body nhưng giữ Bearer challenge

Nhiều API muốn trả Problem Details hoặc JSON thống nhất. Có thể delegate cho Bearer handler trước để giữ status và challenge, sau đó ghi body.

Ví dụ authentication entry point:

~~~java
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.http.CacheControl;
import org.springframework.http.MediaType;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.oauth2.server.resource.web.server.BearerTokenServerAuthenticationEntryPoint;
import org.springframework.security.web.server.ServerAuthenticationEntryPoint;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

import java.util.Map;

public final class JsonBearerAuthenticationEntryPoint
        implements ServerAuthenticationEntryPoint {

    private final BearerTokenServerAuthenticationEntryPoint delegate;
    private final ObjectMapper objectMapper;

    public JsonBearerAuthenticationEntryPoint(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
        this.delegate = new BearerTokenServerAuthenticationEntryPoint();
        this.delegate.setRealmName("orders-api");
    }

    @Override
    public Mono<Void> commence(
            ServerWebExchange exchange,
            AuthenticationException exception) {

        return delegate.commence(exchange, exception)
                .then(Mono.defer(() -> writeBody(exchange)));
    }

    private Mono<Void> writeBody(ServerWebExchange exchange) {
        var response = exchange.getResponse();
        int status = response.getStatusCode() != null
                ? response.getStatusCode().value()
                : 401;

        Map<String, Object> body = Map.of(
                "type", "about:blank",
                "title", status == 400
                        ? "Invalid authentication request"
                        : "Unauthorized",
                "status", status,
                "code", "authentication_failed",
                "detail", "A valid Bearer credential is required");

        byte[] bytes;
        try {
            bytes = objectMapper.writeValueAsBytes(body);
        }
        catch (JsonProcessingException ex) {
            return Mono.error(ex);
        }

        response.getHeaders().setContentType(MediaType.APPLICATION_PROBLEM_JSON);
        response.getHeaders().setCacheControl(CacheControl.noStore());

        return response.writeWith(
                Mono.just(response.bufferFactory().wrap(bytes)));
    }
}
~~~

Điểm quan trọng:
- Delegate thiết lập status và WWW-Authenticate theo Bearer semantics.
- JSON body chỉ bổ sung representation cho API.
- Body không chứa raw exception message hoặc raw token.
- Cache-Control no-store tránh cache response lỗi chứa metadata không cần thiết.
- Không ghi đè WWW-Authenticate bằng header generic sau khi delegate đã tạo challenge.

### Custom access denied JSON body

~~~java
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.http.CacheControl;
import org.springframework.http.MediaType;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.oauth2.server.resource.web.server.BearerTokenServerAccessDeniedHandler;
import org.springframework.security.web.server.authorization.ServerAccessDeniedHandler;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

import java.util.Map;

public final class JsonBearerAccessDeniedHandler
        implements ServerAccessDeniedHandler {

    private final ServerAccessDeniedHandler delegate =
            new BearerTokenServerAccessDeniedHandler();

    private final ObjectMapper objectMapper;

    public JsonBearerAccessDeniedHandler(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    @Override
    public Mono<Void> handle(
            ServerWebExchange exchange,
            AccessDeniedException exception) {

        return delegate.handle(exchange, exception)
                .then(Mono.defer(() -> writeBody(exchange)));
    }

    private Mono<Void> writeBody(ServerWebExchange exchange) {
        var response = exchange.getResponse();

        Map<String, Object> body = Map.of(
                "type", "about:blank",
                "title", "Forbidden",
                "status", 403,
                "code", "access_denied",
                "detail", "The authenticated principal cannot access this resource");

        byte[] bytes;
        try {
            bytes = objectMapper.writeValueAsBytes(body);
        }
        catch (JsonProcessingException ex) {
            return Mono.error(ex);
        }

        response.getHeaders().setContentType(MediaType.APPLICATION_PROBLEM_JSON);
        response.getHeaders().setCacheControl(CacheControl.noStore());

        return response.writeWith(
                Mono.just(response.bufferFactory().wrap(bytes)));
    }
}
~~~

Đây là cách decorate handler, không tự tạo lại toàn bộ Bearer protocol. Phải kiểm thử handler với version Spring Security thực tế để chắc chắn delegate chưa commit response trước khi body được ghi.

Gắn custom handlers:

~~~java
@Bean
SecurityWebFilterChain api(
        ServerHttpSecurity http,
        ObjectMapper objectMapper) {

    ServerAuthenticationEntryPoint entryPoint =
            new JsonBearerAuthenticationEntryPoint(objectMapper);

    ServerAccessDeniedHandler deniedHandler =
            new JsonBearerAccessDeniedHandler(objectMapper);

    return http
            .authorizeExchange(auth ->
                    auth.anyExchange().authenticated())
            .exceptionHandling(ex -> ex
                    .authenticationEntryPoint(entryPoint)
                    .accessDeniedHandler(deniedHandler))
            .oauth2ResourceServer(oauth2 -> oauth2
                    .authenticationEntryPoint(entryPoint)
                    .accessDeniedHandler(deniedHandler)
                    .jwt(Customizer.withDefaults()))
            .build();
}
~~~

Đảm bảo imports là reactive interfaces. Không dùng Servlet AuthenticationEntryPoint/AccessDeniedHandler trong WebFlux.

## 12. Vì sao @RestControllerAdvice không thay Security handlers?

Một @RestControllerAdvice có thể xử lý lỗi từ controller/application handler:

~~~java
@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(OrderNotFoundException.class)
    public ResponseEntity<?> handleNotFound(OrderNotFoundException ex) {
        // Trả domain error phù hợp.
        return ResponseEntity.notFound().build();
    }
}
~~~

Nhưng authentication có thể thất bại **trước khi controller được gọi** trong AuthenticationWebFilter. Authorization có thể được xử lý trong ExceptionTranslationWebFilter hoặc method security.

Vì vậy:
- Dùng **ServerAuthenticationEntryPoint** cho authentication challenges.
- Dùng **ServerAccessDeniedHandler** cho access denied.
- Dùng **@RestControllerAdvice** cho application/domain exceptions phù hợp.
- Không bắt mọi Throwable rồi trả HTTP 200.
- Không nuốt AuthenticationException/AccessDeniedException để request tiếp tục.

Nếu custom WebExceptionHandler có order cao, bảo đảm nó không ghi response trước security handlers hoặc làm mất challenge semantics.

## 13. Phân biệt authentication, authorization và dependency failure

| Nguồn lỗi | Ví dụ | HTTP mapping có thể dùng |
|---|---|---|
| Bearer parser | Header malformed | 400 |
| Authentication | Token missing/invalid/expired | 401 |
| Authorization | Thiếu scope/quyền | 403 |
| Domain policy | Không được sửa order | 403 hoặc 404 theo contract |
| CSRF | POST cookie session thiếu CSRF token | 403 |
| CORS | Origin/method/header không được phép | CORS behavior theo browser/server |
| Rate limit | Quá nhiều request | 429 |
| Dependency | JWKS/introspection timeout | Có thể 503 theo error mapping |
| Server bug | Unexpected exception | 500 |

### JWKS/introspection outage không tự chứng minh token invalid

Nếu Resource Server không liên hệ được JWKS endpoint, nó thiếu dữ kiện để verify token bằng key mới. Nếu introspection timeout, RS không biết token active hay không.

Hai trường hợp phải **fail closed**, nhưng logs/metrics nên phân loại dependency error. Không giả vờ AS đã xác nhận token inactive.

Không khẳng định mọi Spring Security version tự trả 503 cho mọi lỗi mạng. Status phụ thuộc exception mapping và application error contract. Điều bắt buộc là không tạo authenticated principal khi không xác minh được credential.

### Không dùng 403 insufficient_scope để che lỗi hạ tầng

AS outage không có nghĩa principal đã xác thực nhưng thiếu quyền. Nếu trả 403, client có thể xin thêm scope trong khi vấn đề thật là RS không thể kiểm tra token.

## 14. CSRF và CORS cũng có thể gây 403

Một request POST có session cookie nhưng không có CSRF token có thể bị chặn:

~~~http
POST /api/orders HTTP/1.1
Cookie: SESSION=...
Content-Type: application/json
~~~

Response có thể là 403 dù user có scope orders.write. Đây không phải bằng chứng thiếu scope.

Browser preflight:

~~~http
OPTIONS /api/orders HTTP/1.1
Origin: https://shop.example.com
Access-Control-Request-Method: POST
Access-Control-Request-Headers: authorization,content-type
~~~

Nếu CORS policy từ chối origin/method/header, browser có thể báo CORS error và JavaScript không đọc được response. Đừng chẩn đoán đó là Bearer authentication error khi preflight chưa qua.

### CORS configuration

Spring WebFlux có CORS integration với ServerHttpSecurity và reactive CORS configuration phù hợp version. Cần allow origin/method/header có chủ đích, đặc biệt Authorization header.

Không mở wildcard origins cùng credentials nếu policy không cho phép. Không cho OPTIONS bypass vô hạn; hãy định nghĩa preflight behavior rõ.

### CSRF với stateless Bearer API

API chỉ dùng Authorization Bearer header do client chủ động gửi có threat model khác browser session cookie. Nếu ứng dụng cũng chấp nhận cookie, không tắt CSRF chỉ vì có Resource Server. Xác định credential precedence và ambient browser credentials.

## 15. BearerTokenServerAccessDeniedHandler và insufficient_scope

Handler chuyên cho Resource Server là **BearerTokenServerAccessDeniedHandler**. Khi principal là OAuth2 token authentication và authorization từ chối, handler có thể thêm challenge insufficient_scope theo semantics Bearer.

Không phải mọi AccessDeniedException đều là scope failure:

- **hasAuthority("SCOPE_orders.write")** với Bearer token thiếu scope: có thể là insufficient_scope.
- Domain service từ chối tenant ownership: generic access denied có thể phù hợp.
- CSRF filter từ chối: không phải Bearer insufficient_scope.

Khi custom handler, giữ thông tin cần thiết cho client nhưng không tiết lộ resource hoặc quyền của actor khác.

### Scope parameter

Challenge có thể nêu scope cần:

~~~http
WWW-Authenticate: Bearer error="insufficient_scope", scope="orders.write"
~~~

Không tiết lộ internal permission taxonomy hoặc danh sách scopes nhạy cảm cho caller không được phép biết.

## 16. Chuẩn hóa JSON error response

API có thể dùng Problem Details hoặc schema riêng:

~~~json
{
  "type": "about:blank",
  "title": "Forbidden",
  "status": 403,
  "code": "access_denied",
  "detail": "The authenticated principal cannot access this resource",
  "requestId": "req-123"
}
~~~

Field nên có:
- **type/title/status**: mô tả HTTP error.
- **code**: mã ổn định cho client.
- **detail**: thông điệp an toàn.
- **requestId**: correlation ID không nhạy cảm.

Không:
- Đưa exception message nguyên văn ra ngoài.
- Đưa token hoặc full claims vào body.
- Trả stack trace.
- Tiết lộ JWKS/introspection URL nội bộ.
- Ghi body status 401 trong response HTTP 403.
- Xóa WWW-Authenticate khi thêm JSON.
- Dùng HTTP 200 với success=false để che auth error.

JSON body và Bearer challenge cùng tồn tại:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
Content-Type: application/problem+json
Cache-Control: no-store
~~~

Body phục vụ API contract; header giữ OAuth/Bearer semantics.
## 17. WebTestClient: test 401 khi thiếu token

WebFlux test nên đi qua SecurityWebFilterChain thật khi mục tiêu là HTTP security behavior.

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class BearerHttpStatusTests {

    @Autowired
    WebTestClient client;

    @Test
    void missingBearerTokenReturns401Challenge() {
        client.get()
                .uri("/api/orders")
                .exchange()
                .expectStatus().isUnauthorized()
                .expectHeader()
                    .valueMatches("WWW-Authenticate", "Bearer.*");
    }
}
~~~

Giả định:
- /api/orders là protected route.
- Ứng dụng bật Bearer Resource Server.
- Không có test authentication tự động cấp quyền.
- Request không mang session cookie hoặc credential khác có thể thay thế Bearer.

Kỳ vọng:
- HTTP 401.
- WWW-Authenticate bắt đầu bằng Bearer.
- Controller/business handler không được gọi.
- Không có token/exception internals trong body.

Nếu bind WebTestClient trực tiếp tới controller mà không gắn security filters, test không chứng minh filter chain.

## 18. WebTestClient: test 403 với principal đã authenticated

Spring Security Test có **mockJwt()** cho WebFlux. Dùng nó để kiểm tra authorization:

~~~java
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.mockJwt;

import org.springframework.security.core.authority.SimpleGrantedAuthority;

@Test
void validAuthenticationWithoutWriteScopeReturns403() {
    client.mutateWith(mockJwt().authorities(
                    new SimpleGrantedAuthority("SCOPE_orders.read")))
            .post()
            .uri("/api/orders")
            .exchange()
            .expectStatus().isForbidden();
}
~~~

Test này xác minh principal đã được giả lập chỉ có read scope, nên không được POST. Nó **không chứng minh** JWT signature, issuer, audience hoặc JWKS đã được kiểm tra.

Test có write scope:

~~~java
@Test
void writeScopeCanCreateOrder() {
    client.mutateWith(mockJwt().authorities(
                    new SimpleGrantedAuthority("SCOPE_orders.write")))
            .post()
            .uri("/api/orders")
            .exchange()
            .expectStatus().is2xxSuccessful();
}
~~~

Ví dụ cần endpoint và request data phù hợp trong ứng dụng thực tế.

## 19. Test invalid token qua decoder thật

Để kiểm tra authentication failure, gửi compact JWS thực qua Authorization header:

~~~java
@Test
void invalidSignatureReturns401() {
    String token = signedWithUntrustedTestKey();

    client.get()
            .uri("/api/orders")
            .headers(headers -> headers.setBearerAuth(token))
            .exchange()
            .expectStatus().isUnauthorized()
            .expectHeader()
                .valueMatches("WWW-Authenticate", ".*invalid_token.*");
}
~~~

Test cần:
- Bearer Resource Server filter chain thật.
- ReactiveJwtDecoder thật, không mock.
- Test JWKS chỉ công bố trusted public key.
- Token ký bằng key không được trust.
- Issuer/audience/timestamp validators theo contract.

**mockJwt()** bỏ qua decoder; không dùng nó để kiểm tra chữ ký.

### Opaque token inactive

Với opaque Resource Server, dùng mock HTTP introspection endpoint và gửi Bearer opaque token. Khi AS trả active=false, request bị từ chối, thường 401 invalid_token. Đây là test khác mockOpaqueToken(), vì post-processor có thể dựng Authentication giả và bỏ qua HTTP introspection.

## 20. Ma trận test status và challenge

| Case | Status | WWW-Authenticate |
|---|---:|---|
| Không token | 401 | Bearer, có thể kèm realm |
| Token expired | 401 | Bearer error="invalid_token" |
| Signature sai | 401 | Bearer error="invalid_token" |
| Issuer/audience sai | 401 | Bearer error="invalid_token" |
| Malformed Bearer request | Thường 400 | Bearer error="invalid_request" theo parser |
| Token hợp lệ thiếu scope | 403 | Bearer error="insufficient_scope" khi phù hợp |
| Domain permission denial | 403 | Có thể không cần insufficient_scope |
| CSRF denial | 403 | Không phải Bearer scope challenge |
| Dependency outage | Fail closed | Status theo error contract |

Header có thể chứa realm và parameters theo thứ tự khác nhau. Nên kiểm tra semantics bằng regex/parser thay vì so sánh chuỗi cứng nếu framework có thể thêm parameters.

Không chỉ assert status. Cần kiểm tra:
- Challenge đúng scheme/error.
- JSON content type và schema.
- Controller không được gọi khi authentication thất bại.
- Side effects không xảy ra khi authorization bị từ chối.
- Raw token không xuất hiện trong body/log.
- Dependency error được phân loại đúng.

## 21. Test JSON handlers

Với custom entry point:

~~~java
client.get()
        .uri("/api/orders")
        .exchange()
        .expectStatus().isUnauthorized()
        .expectHeader()
            .contentTypeCompatibleWith(
                    MediaType.APPLICATION_PROBLEM_JSON)
        .expectHeader()
            .valueMatches("WWW-Authenticate", "Bearer.*")
        .expectBody()
            .jsonPath("$.status").isEqualTo(401)
            .jsonPath("$.code").isEqualTo("authentication_failed");
~~~

Với access denied:

~~~java
client.mutateWith(mockJwt().authorities(
                new SimpleGrantedAuthority("SCOPE_orders.read")))
        .post()
        .uri("/api/orders")
        .exchange()
        .expectStatus().isForbidden()
        .expectBody()
            .jsonPath("$.status").isEqualTo(403)
            .jsonPath("$.code").isEqualTo("access_denied");
~~~

Test phải chạy security config có custom handlers. Nếu delegate đã commit response trước khi body được ghi, integration test sẽ phát hiện lỗi response committed/double write. Vì vậy custom handler cần được kiểm tra qua WebTestClient, không chỉ unit test class.

## 22. Test phân biệt CSRF, CORS và insufficient_scope

### CSRF

Nếu app dùng session cookie, POST không có CSRF token có thể trả 403 trước method authorization. Test phải xác định đây là CSRF denial, không mong Bearer insufficient_scope.

### CORS

Gửi OPTIONS preflight với Origin, Access-Control-Request-Method và Access-Control-Request-Headers. Kiểm tra:
- Origin được phép mới có Access-Control-Allow-Origin.
- Method và Authorization header được cho phép theo policy.
- Preflight được xử lý trước khi yêu cầu Bearer authentication nếu cấu hình CORS cho phép.
- Origin không được phép bị từ chối đúng contract.

Browser enforce CORS; Java HTTP clients thường không enforce như browser. Cần browser/e2e test nếu muốn chứng minh behavior phía trình duyệt.

### Domain denial

Tạo principal có SCOPE_orders.write nhưng tenant mismatch. Kỳ vọng 403 domain policy. Không gắn insufficient_scope khi token có scope yêu cầu.

## 23. Observability an toàn

Có thể ghi:

~~~text
requestId
routeId
authenticationOutcome = missing / invalid / success
authenticationFailureCategory = invalid_token / invalid_request / dependency
authorizationOutcome = granted / denied
authorizationCategory = insufficient_scope / tenant / ownership / csrf
httpStatus
securityHandler = bearer_entry_point / access_denied_handler
latency
~~~

Không ghi:
- Authorization header.
- Raw access/refresh token.
- Password, client secret, API key.
- Full JWT payload có PII.
- Stack trace hoặc key management details vào response.
- Unverified issuer/subject như trusted identity.

Metrics nên dùng route ID, configured issuer ID, strategy ID và error category có cardinality giới hạn; không dùng raw sub/token/error message làm labels.

Phân biệt invalid_token với dependency failure rất quan trọng. JWKS/introspection outage nghĩa là RS không thể xác minh, không phải AS đã xác nhận token inactive.

## 24. Anti-pattern thường gặp

| Sai lầm | Vấn đề | Cách đúng |
|---|---|---|
| Token hết hạn trả 403 | Nhầm authentication và authorization | 401 invalid_token |
| Thiếu scope trả 401 | Bắt user đăng nhập lại không cần thiết | 403 insufficient_scope |
| 401 không có WWW-Authenticate | Thiếu Bearer challenge | Bearer entry point |
| Mọi 403 đều insufficient_scope | Sai với CSRF/domain/CORS | Phân loại denial |
| Chỉ có JSON body, bỏ challenge | Mất HTTP auth semantics | Giữ WWW-Authenticate |
| Custom entry point trả 200 | Che authentication failure | Status đúng |
| Trả exception message nguyên văn | Lộ internals/secrets | Generic detail, correlation ID |
| @RestControllerAdvice xử lý mọi security error | Filter-chain errors không đi qua controller | Reactive security handlers |
| Dùng Servlet AuthenticationEntryPoint trong WebFlux | Sai API stack | ServerAuthenticationEntryPoint |
| block() trong response handler | Chặn reactive pipeline | Mono<Void> composition |
| Ghi body sau khi response đã committed | Double write/response error | Delegate lifecycle + integration test |
| CORS preflight bị coi là invalid token | Sai policy | Cấu hình CORS đúng |
| CSRF 403 bị báo thiếu scope | Sai nguyên nhân | Phân loại CSRF riêng |
| mockJwt() để test signature | Bỏ qua decoder | Signed Bearer token + real decoder |
| Chỉ assert status | Không kiểm tra challenge/body | Assert headers, body, side effects |
| Log raw JWT | Lộ credential | Sanitized telemetry |

## 25. Ma trận quyết định response

| Authentication | Authorization | Response thường dùng |
|---|---|---|
| Không có credential | Chưa chạy | 401 + Bearer challenge |
| Credential malformed | Không xác thực | 400 invalid_request khi phù hợp |
| Credential invalid/expired/revoked | Thất bại | 401 invalid_token |
| Dependency không thể xác minh | Chưa authenticated | Fail closed; status theo error contract, có thể 503 |
| Authentication thành công, thiếu scope | Từ chối | 403 insufficient_scope |
| Authentication thành công, sai tenant/owner | Từ chối | 403 hoặc 404 theo policy |
| Authentication thành công, được phép | Cho qua | 2xx hoặc status nghiệp vụ |
| CSRF/CORS/gateway denial | Có thể chưa tới authorization | Status theo filter/policy |

Không phải mọi request bị từ chối đều là OAuth error. Reverse proxy, CORS, CSRF, authentication, authorization, domain và rate limiting là các lớp riêng. Response nên phản ánh đúng lớp từ chối theo API contract.

## 26. Tổng kết

~~~text
HTTP Request
    |
    v
Bearer credential parsing
    |
    v
Authentication
  +-- missing/invalid -> ServerAuthenticationEntryPoint
  |                       -> 401 + WWW-Authenticate
  |
  +-- valid
         |
         v
Authorization
  +-- insufficient permission -> ServerAccessDeniedHandler
  |                               -> 403
  |
  +-- permitted
         |
         v
      Controller / domain
         |
         v
      API response
~~~

Những nguyên tắc cần nhớ:

1. **401** khi caller chưa có authentication hợp lệ, ví dụ thiếu hoặc invalid Bearer token.
2. **403** khi principal đã xác thực nhưng không được phép thực hiện action.
3. **WWW-Authenticate: Bearer** là challenge quan trọng cho 401; JSON body không thay header.
4. RFC 6750 phân biệt **invalid_request**, **invalid_token** và **insufficient_scope**.
5. **BearerTokenServerAuthenticationEntryPoint** và **BearerTokenServerAccessDeniedHandler** là reactive handlers phù hợp.
6. Dùng **ServerAuthenticationEntryPoint** và **ServerAccessDeniedHandler**, không dùng Servlet handlers trong WebFlux.
7. JSON body có thể bổ sung nhưng phải giữ status và challenge semantics.
8. **@RestControllerAdvice** không thay security filter-chain handlers.
9. CSRF/CORS/domain denial không tự là thiếu OAuth scope.
10. Dependency failure phải fail closed, nhưng không giả vờ AS đã xác nhận token inactive.
11. Test bằng **WebTestClient** cần kiểm tra status, WWW-Authenticate, body và side effects.
12. **mockJwt()** hữu ích cho authorization tests nhưng không chứng minh signature/JWKS đã được kiểm tra.

**Kết luận:** WebFlux Resource Server cần trả đúng HTTP semantics cho từng lớp bảo mật. 401 phản ánh authentication challenge, 403 phản ánh authorization denial, Bearer error code phải đúng nguyên nhân và JSON body phải an toàn. Spring Security cung cấp reactive entry point/denied handler để giữ protocol behavior; WebTestClient giúp kiểm chứng response contract của API.

## 27. Tài liệu tham khảo

- **Spring Security Reference — Reactive OAuth 2.0 Resource Server:** Bearer authentication, error handling, JWT và opaque flows. https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/index.html
- **Spring Security Reference — Reactive JWT Resource Server:** JWT authentication và validation. https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html
- **Spring Security Reference — Reactive Opaque Token Resource Server:** introspection và inactive token handling. https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/opaque-token.html
- **Spring Security API — ServerAuthenticationEntryPoint:** reactive authentication challenge. https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/ServerAuthenticationEntryPoint.html
- **Spring Security API — ServerAccessDeniedHandler:** reactive authorization denial. https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/authorization/ServerAccessDeniedHandler.html
- **Spring Security API — BearerTokenServerAuthenticationEntryPoint:** Bearer challenge implementation. https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/web/server/BearerTokenServerAuthenticationEntryPoint.html
- **Spring Security API — BearerTokenServerAccessDeniedHandler:** Bearer access-denied implementation. https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/web/server/BearerTokenServerAccessDeniedHandler.html
- **Spring Security Reference — WebFlux Security:** SecurityWebFilterChain and exception handling. https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html
- **Spring Security Reference — Reactive Testing:** WebTestClient and mock JWT. https://docs.spring.io/spring-security/reference/reactive/test/web/index.html
- **Spring Security Reference — Testing OAuth 2.0:** mock JWT and Resource Server test concepts. https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/oauth2.html
- **RFC 6750 — OAuth 2.0 Bearer Token Usage:** invalid_request, invalid_token, insufficient_scope và WWW-Authenticate. https://www.rfc-editor.org/rfc/rfc6750
- **RFC 9110 — HTTP Semantics:** 401 challenge, 403 forbidden và WWW-Authenticate. https://www.rfc-editor.org/rfc/rfc9110
- **RFC 7807 — Problem Details for HTTP APIs:** error representation. https://www.rfc-editor.org/rfc/rfc7807
- **RFC 9457 — Problem Details for HTTP APIs:** bản cập nhật Problem Details. https://www.rfc-editor.org/rfc/rfc9457


