# Kiểm tra issuer, audience, thời hạn và chữ ký token

## 1. Mục tiêu: không chỉ “giải mã được JWT” mà phải xác thực đúng JWT

Trong kiến trúc microservices, **Spring Cloud Gateway** thường là điểm nhận HTTP request công khai trước khi route đến các backend. Một client gọi:

~~~http
GET /api/orders/42 HTTP/1.1
Host: api.example.test
Authorization: Bearer eyJ...
~~~

Gateway có thể chọn route theo `Path`/`Method`, áp dụng filter chain, biến đổi path/header rồi khám phá instance qua `lb://orders-service`. Nhưng trước khi cho phép truy cập API được bảo vệ, nó phải biết **Bearer token có thực sự hợp lệ và được cấp cho tài nguyên này không**.

Đối với **JWT access token được ký** (JWS), bốn phép kiểm tra cốt lõi của bài thuộc chương **Xác thực và phân quyền** là:

1. **Chữ ký (signature):** token có được ký bằng khóa và thuật toán mà Gateway tin cậy không, payload có bị thay đổi không?
2. **Issuer (`iss`):** token có được phát hành bởi đúng Authorization Server/Identity Provider đã cấu hình không?
3. **Audience (`aud`):** token có được cấp cho API/resource server này không, hay nó dành cho một ứng dụng khác?
4. **Thời hạn (`exp`, `nbf`; hiểu thêm `iat`):** token đã hết hạn, chưa tới thời điểm có hiệu lực hoặc không phù hợp chính sách thời gian không?

**Một JWT được ký hợp lệ chưa chắc là token được phép dùng tại API này.** Chẳng hạn một token được phát hành hợp lệ cho `billing-api` không nên được Gateway chấp nhận để truy cập `orders-api` chỉ vì chữ ký đúng.

Trong module **SPRING_CLOUD_GATEWAY**, việc xác thực này là nền tảng để triển khai API Gateway an toàn cùng route predicate, biến đổi header/path, service discovery, rate limiting, circuit breaker, retry, TLS và quan sát request. Bài tập trung vào **Spring Cloud Gateway Server WebFlux** với **Spring Security Reactive OAuth2 Resource Server**. Gateway Server MVC dùng security stack khác.

> **Giả định:** Đây là luồng xác minh **JWT access token có chữ ký** do một issuer tin cậy cấp. Token opaque cần cơ chế introspection thay vì JWT decoder; JWT mã hóa JWE có cách xử lý khác với JWS. Ví dụ hostname, token và audience đều là dữ liệu minh họa, không phải hệ thống xác thực đang hoạt động.

## 2. Cấu trúc JWT và những gì có thể, không thể tin

Một JWT dạng JWS compact có ba phần phân cách bằng dấu chấm:

~~~text
BASE64URL(header).BASE64URL(payload).BASE64URL(signature)
~~~

Header **minh họa**:

~~~json
{
  "alg": "RS256",
  "typ": "at+jwt",
  "kid": "key-2026-11"
}
~~~

Payload **minh họa**:

~~~json
{
  "iss": "https://id.example.test/realms/platform",
  "sub": "user-123",
  "aud": ["gateway-api", "orders-api"],
  "scope": "orders.read",
  "iat": 1795000000,
  "nbf": 1795000000,
  "exp": 1795003600
}
~~~

| Thành phần | Ý nghĩa | Điều cần kiểm tra |
| --- | --- | --- |
| Header `alg` | Thuật toán chữ ký | Thuật toán nằm trong **allowlist do server cấu hình**, không lấy quyết định tin cậy chỉ từ header |
| Header `kid` | Gợi ý chọn khóa trong JWKS | Khóa phải đến từ **nguồn đã cấu hình tin cậy**; `kid` không phải bằng chứng hợp lệ |
| Header `typ` | Gợi ý loại token | Một số profile access token (ví dụ RFC 9068) cần kiểm tra loại token riêng |
| Claim `iss` | Bên phát hành token | So sánh với issuer dự kiến |
| Claim `aud` | Những bên nhận token hợp lệ | Phải chứa audience mà API này yêu cầu |
| Claim `exp` | Thời điểm hết hạn | Từ chối token đã quá hạn sau khi xét độ lệch đồng hồ cho phép |
| Claim `nbf` | Thời điểm bắt đầu được chấp nhận | Từ chối token chưa có hiệu lực |
| Claim `iat` | Thời điểm phát hành | Hữu ích cho audit và policy riêng; không thay thế `exp` |
| Claim `scope` hoặc `scp` | Quyền được cấp | Là dữ liệu đầu vào cho **authorization**, không chứng minh chữ ký/issuer/audience |

Các mốc thời gian JWT là **NumericDate**: số giây tính từ Unix epoch, **không phải mili giây**. Chẳng hạn Java `Instant.getEpochSecond()` và JavaScript `Date.now() / 1000` cho đơn vị giây; lấy trực tiếp `Date.now()` làm `exp` là sai đơn vị.

**Rất quan trọng:** Header và payload chỉ được **mã hóa Base64URL, không được mã hóa bí mật**. Bất kỳ ai cầm token đều có thể đọc các claim. Không đưa mật khẩu, secret hoặc thông tin không nên lộ vào JWT payload. Việc tách payload và gọi JSON parser **không hề xác minh chữ ký**; không dùng kết quả chưa xác thực để xây `Authentication` hoặc quyết định route/role.

## 3. Xác thực ở đâu trong luồng Gateway WebFlux?

Trong một Gateway WebFlux có Spring Security Reactive:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant S as Spring Security WebFilterChain
    participant J as ReactiveJwtDecoder / JWKS
    participant G as Gateway route + filter chain
    participant B as orders-service

    C->>S: GET /api/orders/42 + Bearer JWT
    S->>J: Giải mã, xác minh chữ ký và claims
    Note over J: Chữ ký, iss, aud, exp, nbf
    alt Token không hợp lệ
        J-->>S: Authentication failure
        S-->>C: 401 Unauthorized
    else Token hợp lệ nhưng thiếu scope
        J-->>S: JWT đã xác minh
        S-->>C: 403 Forbidden
    else Token hợp lệ và đủ quyền
        J-->>S: JWT + authorities
        S->>G: Cho phép request qua security chain
        G->>B: Forward request theo route
        B-->>G: HTTP response
        G-->>C: HTTP response
    end
~~~

Đây là **sơ đồ logic**, không phải mô tả chi tiết thứ tự của mọi WebFilter/GatewayFilter ở mọi phiên bản. Điểm cần nhớ là **Spring Security WebFlux bảo vệ request ở tầng WebFilter**, trước khi một request không hợp lệ được chuyển đến backend. Gateway route predicate **không thay thế** xác thực hay phân quyền.

| Kết quả | Ý nghĩa thường gặp | Backend có nhận request không? |
| --- | --- | --- |
| **401 Unauthorized** | Thiếu token hoặc JWT không xác thực được: chữ ký, issuer, audience, thời hạn sai | Không, nếu Gateway chặn |
| **403 Forbidden** | Token hợp lệ nhưng không đủ quyền/scope; hoặc một security policy khác từ chối | Không, nếu Gateway chặn |
| **404 Not Found** | Không có route/handler phù hợp hoặc backend trả 404 | Phụ thuộc vị trí tạo 404 |
| **503 Service Unavailable** | Ví dụ route `lb://...` khớp nhưng không có instance khả dụng | Thường chưa đến backend |

Mã thực tế có thể khác do exception handler/filter được tùy biến. **Không đưa chi tiết nội bộ về token, khóa hoặc policy vào response lỗi công khai**; chỉ ghi thông tin cần thiết ở logs có bảo vệ.

## 4. Kiểm tra chữ ký: tin khóa và thuật toán nào?

Với token ký bằng **RS256**, Authorization Server giữ **private key** để ký; Gateway lấy **public key** tương ứng để kiểm tra. Thông thường issuer cung cấp bộ khóa công khai qua **JWKS endpoint**.

~~~mermaid
flowchart LR
    A["Authorization Server<br/>giữ private key"] -->|"Ký JWT"| T["JWT: alg + kid + claims + signature"]
    A -->|"Công bố public JWKs"| K["JWKS HTTPS"]
    T --> G["Gateway JWT decoder"]
    K --> G
    G --> V{"Xác minh chữ ký<br/>với khóa được tin?"}
    V -->|"Không"| N["401"]
    V -->|"Có"| C["Kiểm tiếp iss / aud / exp / nbf"]
~~~

### 4.1. JWKS, kid và key rotation

Ví dụ một phần JWKS **minh họa, không phải khóa thật**:

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "use": "sig",
      "kid": "key-2026-11",
      "alg": "RS256",
      "n": "<modulus-public-key>",
      "e": "AQAB"
    }
  ]
}
~~~

Trường `kid` hỗ trợ thư viện chọn khóa phù hợp trong bộ khóa mà **server tin cậy đã cấu hình**. Nó **không cho phép** client tùy ý yêu cầu Gateway tải khóa từ một URL bất kỳ. Những header như `jku`/`x5u` do token cung cấp không được biến thành nguồn khóa tự do, tránh rủi ro **SSRF/đổi nguồn khóa**.

Khi issuer xoay khóa, nó có thể tạm xuất bản **khóa cũ và khóa mới** trong JWKS để các token chưa hết hạn tiếp tục xác thực. Resource Server hỗ trợ cập nhật khóa khi JWKS thay đổi; hành vi refresh/cache chi tiết phụ thuộc thư viện và version. Cần lập kế hoạch cho trường hợp issuer/JWKS endpoint không truy cập được và không xóa khóa cũ trước khi các token cần nó hết hạn.

### 4.2. Không tin thuật toán tự khai trong token

Một cấu hình tốt có **allowlist thuật toán** phù hợp với IdP và loại khóa:

- `RS256`, `RS512`, `ES256` ... chỉ khi issuer thực sự phát hành và Gateway được cấu hình xác minh.
- **Không chấp nhận `alg=none`** cho access token ký.
- Không để attacker chuyển nhầm bất đối xứng `RS256` sang đối xứng `HS256` để gây lỗi *algorithm confusion*.
- Không dùng một key bí mật yếu/được chia sẻ công khai; với JWKS bất đối xứng, Gateway chỉ cần public key.

Theo tài liệu Spring Security Reactive JWT, `NimbusReactiveJwtDecoder` mặc định tin **RS256** trong cấu hình tiêu chuẩn; có thể thay đổi bằng property `jws-algorithms` hoặc builder. Nếu IdP dùng thuật toán khác, cần cấu hình **đúng thuật toán được phép**, không bật mọi thuật toán chỉ để một token vượt qua kiểm tra.

### 4.3. Chữ ký không thay thế claim validation

Token có chữ ký đúng nhưng:

~~~json
{
  "iss": "https://issuer-khac.example.test",
  "aud": "another-api",
  "exp": 1700000000
}
~~~

vẫn phải bị từ chối tại Gateway này nếu issuer, audience hoặc thời điểm không hợp lệ. Đặc biệt, **token ký hợp lệ từ cùng IdP nhưng dành cho ứng dụng khác** là lỗi rất thường gặp khi bỏ qua `aud`.

## 5. Kiểm tra issuer (iss)

`iss` là định danh của bên phát hành token. Ví dụ issuer được Gateway chấp nhận:

~~~text
https://id.example.test/realms/platform
~~~

Spring Security OAuth2 Resource Server có thể dùng property `issuer-uri` để tìm metadata của Authorization Server (OIDC Provider Configuration/OAuth Authorization Server Metadata), lấy URI JWKS và kiểm tra claim `iss`. Giá trị phải khớp **issuer do IdP công bố**, không được suy từ hostname một cách đại khái.

| Giá trị claim `iss` trong JWT | So với issuer cấu hình ở trên |
| --- | --- |
| `https://id.example.test/realms/platform` | Khớp |
| `http://id.example.test/realms/platform` | Sai scheme |
| `https://id.example.test/realms/other` | Sai realm/tenant |
| `https://id.example.test/realms/platform/` | Khác chuỗi do dấu slash cuối |
| `https://evil.example.test/realms/platform` | Sai hostname |

**Không chấp nhận issuer tùy ý dựa trên claim `iss` của token chưa được xác minh** rồi dùng issuer đó để tự tải JWKS. Với hệ thống đa tenant/multi issuer, phải có **allowlist issuer và ràng buộc issuer → JWKS → audience/policy** rõ ràng, tránh token của tenant này được dùng cho tenant khác.

Issuer URI đôi khi có **đường dẫn**, ví dụ `/realms/platform`. URI `jwk-set-uri` không có quy tắc bắt buộc chung; dùng metadata của IdP hoặc tài liệu của nhà cung cấp, không tự đoán `/keys` từ tên realm.

## 6. Kiểm tra audience (aud): token dành cho ai?

Audience cho biết **resource/API nào được phép tiêu thụ token**. `aud` có thể là một chuỗi hoặc danh sách chuỗi trong JWT; Spring Security thường chuẩn hóa thành danh sách khi truy cập `Jwt.getAudience()`.

Ví dụ Gateway yêu cầu:

~~~text
Expected audience: gateway-api
~~~

| Claim `aud` | Hợp lệ với expected `gateway-api`? |
| --- | --- |
| `"gateway-api"` | Có |
| `["gateway-api", "orders-api"]` | Có |
| `"billing-api"` | Không |
| `["orders-api", "billing-api"]` | Không |
| Không có `aud` | Không, nếu policy của Gateway yêu cầu audience |

**`aud` khác `iss` và `client_id`/`azp`.** Issuer nói *ai phát hành*, audience nói *cho ai*, còn client ID/authorized party nói về ứng dụng đã yêu cầu token. Không dùng `sub`, `azp` hoặc `scope` để thay thế kiểm tra audience.

### 6.1. Audience tại Gateway so với backend

Trong hệ thống nhiều service, cần quyết định **API nào là resource server**:

- Nếu Gateway là tài nguyên được bảo vệ, có thể yêu cầu token chứa `gateway-api` trong `aud`.
- Nếu Gateway forward cùng access token cho `orders-service`, backend nên **xác minh token độc lập** và yêu cầu audience mà backend chấp nhận, chẳng hạn `orders-api`, đồng thời kiểm tra quyền đơn hàng.
- Nếu dùng token exchange hoặc token relay theo chính sách, audience của token downstream có thể khác token client gửi vào Gateway.

Một JWT mang `aud=["gateway-api","orders-api"]` chỉ là **ví dụ**; đừng ép mọi token có nhiều audience rộng hơn cần thiết. Cần thiết kế audience phù hợp với IdP, ranh giới tin cậy và nguyên tắc least privilege.

## 7. Thời hạn: exp, nbf, iat và clock skew

Các claim thời gian:

| Claim | Ý nghĩa | Quy tắc |
| --- | --- | --- |
| `exp` | Expiration time | Token không được chấp nhận từ thời điểm hết hạn trở đi, xét độ lệch đồng hồ được cho phép |
| `nbf` | Not before | Không dùng token trước thời điểm có hiệu lực, xét độ lệch đồng hồ |
| `iat` | Issued at | Cho biết thời điểm phát hành; **không tự thay thế kiểm tra hết hạn** |

Ví dụ theo thời gian:

~~~text
nbf = 10:00:00 UTC
iat = 10:00:00 UTC
exp = 10:20:00 UTC

09:59:00 ── chưa có hiệu lực ── 10:00:00 ── hợp lệ ── 10:20:00 ── hết hạn
~~~

Spring Security Reactive Resource Server dùng **`JwtTimestampValidator`** để kiểm tra cửa sổ `exp`/`nbf`; tài liệu nêu mức **clock skew mặc định 60 giây** nhằm dung sai lệch đồng hồ giữa các máy. Với một token vừa hết hạn, kết quả kiểm tra trong khoảng skew có thể khác quy tắc “chặn đúng mili giây”. Đây là lựa chọn kỹ thuật, không nên tăng rộng vô hạn.

### 7.1. Đừng nhầm validation với yêu cầu bắt buộc có exp

Kiểm tra thời hạn của một claim **nếu claim có mặt** không đồng nghĩa mọi cấu hình mặc định đều **bắt buộc token phải chứa `exp`**. Nếu policy bảo mật của bạn yêu cầu mọi access token có thời hạn hữu hạn, hãy **bổ sung validator yêu cầu `exp` hiện diện**, ngoài kiểm tra mốc thời gian. Tương tự, có thể kiểm tra `iat` không nằm quá xa tương lai hoặc giới hạn tuổi thọ `exp - iat` theo chính sách riêng.

Đừng gộp ba quy tắc thành một phép kiểm tra “token age” tự chế rồi bỏ qua `JwtTimestampValidator`. Mỗi claim mang một ý nghĩa; tự viết logic thời gian dễ gây lỗi khi timezone hoặc đơn vị giây/mili giây không thống nhất.

### 7.2. Đồng bộ đồng hồ và vòng đời token

- Đồng bộ NTP giữa IdP, Gateway và microservices.
- Giữ skew nhỏ nhất phù hợp hạ tầng; mặc định 60 giây là điểm tham chiếu, không phải lựa chọn bắt buộc cho mọi hệ thống.
- Dùng access token ngắn hạn, refresh token được bảo vệ ở phía phù hợp.
- JWT đã xác minh chữ ký và chưa hết hạn **không tự bị thu hồi ngay** khi người dùng logout hoặc mất quyền. Nếu cần revoke tức thời, thiết kế session state, token introspection, danh sách thu hồi, token exchange hoặc giảm TTL theo yêu cầu.

## 8. Cấu hình tối thiểu: Spring Boot Resource Server JWT cho Gateway WebFlux

### 8.1. Dependencies Maven

Ví dụ với Spring Cloud Gateway Server WebFlux dòng mới:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-gateway-server-webflux</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
    </dependency>
</dependencies>
~~~

Starter OAuth2 Resource Server cung cấp hỗ trợ Spring Security Resource Server và JWT/Jose cần thiết theo dependency management của Spring Boot. Với một số phiên bản Gateway WebFlux cũ, starter tên `spring-cloud-starter-gateway`. Hãy chọn **Spring Cloud BOM tương thích với Spring Boot**; đừng trộn dependency Servlet MVC (`spring-boot-starter-web`) vào Gateway Server WebFlux nếu không có lý do đặc biệt.

### 8.2. Cấu hình issuer, audience và thuật toán

`src/main/resources/application.yml`:

~~~yaml
server:
  port: 8080

spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://id.example.test/realms/platform
          audiences:
            - gateway-api
          jws-algorithms:
            - RS256

  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: orders-api
              uri: http://localhost:9091
              predicates:
                - Path=/api/orders/**
              filters:
                - StripPrefix=1
~~~

**Ý nghĩa các property bảo mật của Spring Boot:**

- `issuer-uri`: nguồn issuer tin cậy; Resource Server dùng để tìm metadata/JWKS khi cần và xác minh `iss`.
- `audiences`: yêu cầu `aud` chứa ít nhất audience được cấu hình, ở đây `gateway-api` (hỗ trợ trong Spring Boot các dòng hiện hành theo tài liệu).
- `jws-algorithms`: giới hạn thuật toán chữ ký được chấp nhận, ở đây `RS256`.

**Không có một property Gateway routes nào tự thay thế được các phép kiểm tra này.** `Path=/api/orders/**` chỉ là predicate định tuyến; việc xác thực nằm ở **Spring Security WebFlux**.

Với Gateway **Server WebFlux 4.2/4.3**, danh sách route trong ví dụ trên thường dùng namespace `spring.cloud.gateway.routes` thay cho `spring.cloud.gateway.server.webflux.routes`. Các property `spring.security.oauth2.resourceserver.jwt.*` thuộc Spring Boot/Security và **không đổi chỉ vì namespace routes thay đổi**. Chọn đúng version khi triển khai.

### 8.3. Khi cần đặt JWK Set URI trực tiếp

Nếu IdP không cung cấp metadata chuẩn, hoặc muốn biết trước JWKS URL, có thể cấu hình cả hai:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://id.example.test/realms/platform
          jwk-set-uri: https://id.example.test/realms/platform/protocol/openid-connect/certs
          audiences:
            - gateway-api
          jws-algorithms:
            - RS256
~~~

Đường JWKS trên là **ví dụ theo kiểu endpoint của một IdP**, không được suy ra như đường dẫn chuẩn của mọi nhà cung cấp. Khi khai báo cả `issuer-uri` lẫn `jwk-set-uri`, Resource Server có thể tránh bước discovery để biết JWKS URL mà **vẫn kiểm tra `iss`** từ issuer đã cấu hình. Nếu chỉ đặt `jwk-set-uri` và không thiết lập issuer validator, **không được mặc định kết luận `iss` vẫn đang được xác minh**.

JWKS cần được truy xuất qua nguồn HTTPS tin cậy với TLS validation; không nhúng private key của IdP vào Gateway. Một số dòng Spring Security mới dùng cơ chế khởi tạo/lấy metadata **khi có request đầu tiên**; khi tự khai báo decoder bean, hãy kiểm tra vòng đời khởi tạo vì thay auto-config có thể làm hành vi này khác đi.

## 9. Bảo vệ API theo scope sau khi xác thực JWT

JWT hợp lệ về chữ ký và claims chưa có nghĩa người gọi được xem mọi tài nguyên. Ví dụ, một token có `scope: "orders.read"` có thể đọc đơn nhưng không được tạo đơn.

Tạo `SecurityWebFilterChain` trong Gateway WebFlux:

~~~java
package demo.gateway.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class GatewaySecurityConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
                // Chỉ chọn disable CSRF cho API stateless dùng Bearer
                // header, không dùng cookie/session làm auth.
                .csrf(ServerHttpSecurity.CsrfSpec::disable)
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/actuator/health").permitAll()
                        .pathMatchers(HttpMethod.GET, "/api/orders/**")
                            .hasAuthority("SCOPE_orders.read")
                        .pathMatchers(HttpMethod.POST, "/api/orders/**")
                            .hasAuthority("SCOPE_orders.write")
                        .anyExchange().authenticated())
                .oauth2ResourceServer(oauth2 ->
                        oauth2.jwt(Customizer.withDefaults()))
                .build();
    }
}
~~~

Trong cấu hình JWT Resource Server mặc định, Spring Security chuyển các giá trị `scope`/`scp` thành authorities có tiền tố `SCOPE_`. Vì vậy `orders.read` trở thành `SCOPE_orders.read`. Nếu IdP sử dụng định dạng role/claim riêng, phải cấu hình converter tường minh và kiểm thử; không giả định claim `roles` tự được nhận làm authority.

**Chú ý:**

- Tắt CSRF như code mẫu chỉ phù hợp nếu API **thực sự stateless và chỉ xác thực Bearer token trong header**. Nếu browser dùng cookie để xác thực, cần đánh giá CSRF protection riêng.
- Với browser cross-origin, CORS/preflight phải được xử lý đúng thứ tự trước authentication. Không yêu cầu Bearer token cho CORS preflight OPTIONS rồi khiến browser không gửi request thật.
- Backend vẫn phải **phân quyền theo resource**, ví dụ người dùng có quyền đọc *đơn hàng số 42 của chính mình*. Scope không tự kiểm tra sở hữu tài nguyên.
- Việc Gateway xác thực JWT không khiến backend tự động tin mọi header `X-User-Id` từ client. Nếu forward danh tính, cần có cơ chế tin cậy và kiểm soát truy cập trực tiếp vào backend.

## 10. Custom ReactiveJwtDecoder: kiểm tra audience và bắt buộc có exp

Trong một số hệ thống, bạn cần validator riêng, ví dụ:

- Token phải có `exp` hiện diện.
- `aud` phải chứa `gateway-api`.
- `iss`, `exp`, `nbf` vẫn được kiểm tra theo validator tiêu chuẩn.
- Chỉ chấp nhận chữ ký `RS256` từ JWKS do **cấu hình server** quyết định.

Ví dụ dưới đây **thay thế auto-config decoder** bằng một bean tường minh. Dùng nó **như lựa chọn thay thế**, không đồng thời giả định các property `spring.security.oauth2.resourceserver.jwt.*` ở mục 8 sẽ tự áp dụng lên decoder custom.

`application.yml` bổ sung:

~~~yaml
app:
  security:
    jwt:
      issuer: https://id.example.test/realms/platform
      jwk-set-uri: https://id.example.test/realms/platform/protocol/openid-connect/certs
      audience: gateway-api
~~~

`JwtValidationConfig.java`:

~~~java
package demo.gateway.security;

import java.util.List;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtClaimNames;
import org.springframework.security.oauth2.jwt.JwtClaimValidator;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusReactiveJwtDecoder;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;

@Configuration
public class JwtValidationConfig {

    @Bean
    ReactiveJwtDecoder jwtDecoder(
            @Value("${app.security.jwt.issuer}") String issuer,
            @Value("${app.security.jwt.jwk-set-uri}") String jwkSetUri,
            @Value("${app.security.jwt.audience}") String requiredAudience) {

        NimbusReactiveJwtDecoder decoder =
                NimbusReactiveJwtDecoder.withJwkSetUri(jwkSetUri)
                        .jwsAlgorithm(SignatureAlgorithm.RS256)
                        .build();

        // Giữ các phép kiểm tra tiêu chuẩn, bao gồm issuer và exp/nbf.
        OAuth2TokenValidator<Jwt> issuerAndTime =
                JwtValidators.createDefaultWithIssuer(issuer);

        // aud trong đối tượng Jwt thường được chuẩn hóa thành List<String>.
        OAuth2TokenValidator<Jwt> audience =
                new JwtClaimValidator<List<String>>(
                        JwtClaimNames.AUD,
                        audiences -> audiences != null
                                && audiences.contains(requiredAudience));

        // Chính sách bổ sung: JWT nào thiếu exp thì từ chối.
        OAuth2TokenValidator<Jwt> requireExp = jwt -> {
            if (jwt.getExpiresAt() == null) {
                OAuth2Error error = new OAuth2Error(
                        "invalid_token", "Missing exp claim", null);
                return OAuth2TokenValidatorResult.failure(error);
            }
            return OAuth2TokenValidatorResult.success();
        };

        decoder.setJwtValidator(
                new DelegatingOAuth2TokenValidator<>(
                        issuerAndTime, audience, requireExp));
        return decoder;
    }
}
~~~

Trong ví dụ:

1. **Xác minh chữ ký** do `NimbusReactiveJwtDecoder` thực hiện với **JWKS URL và RS256 server cấu hình**.
2. **Issuer và thời hạn** vẫn được `JwtValidators.createDefaultWithIssuer(issuer)` kiểm tra; không thay thế bằng một audience validator tự viết rồi vô tình mất kiểm tra mặc định.
3. **Audience** được validator riêng so khớp với `gateway-api`.
4. **Sự hiện diện của exp** được yêu cầu rõ ràng; chính sách riêng này bổ sung cho phép kiểm tra thời điểm đã hết hạn.

Nếu ứng dụng của bạn dùng dòng Spring Security hoặc Spring Boot với API khác, cần đối chiếu chính xác chữ ký phương thức trong tài liệu version đang sử dụng. Đây là mã minh họa cách **kết hợp validators**, không phải một triển khai được build/test trong bài viết.

### 10.1. Tùy chỉnh clock skew mà không xóa validation khác

Nếu cần lệch đồng hồ khác mặc định, sử dụng `JwtTimestampValidator(Duration)` cùng issuer/audience/requireExp validators trong cùng `DelegatingOAuth2TokenValidator`. Chỉ tăng skew sau khi đã kiểm tra thời gian hệ thống:

~~~java
// Minh họa chính sách thời gian riêng, thay phần validator tiêu chuẩn
// bằng tập validator đầy đủ chứ không chỉ còn timestamp.
OAuth2TokenValidator<Jwt> timestamp =
        new JwtTimestampValidator(java.time.Duration.ofSeconds(30));
OAuth2TokenValidator<Jwt> issuer =
        new JwtIssuerValidator(expectedIssuer);
~~~

Đoạn này cần import `JwtTimestampValidator` và `JwtIssuerValidator`, khai báo biến `expectedIssuer` trong ngữ cảnh Java thích hợp. Phải **kết hợp cả timestamp, issuer, audience và requireExp** khi đưa vào decoder; không chỉ gọi `setJwtValidator(timestamp)` rồi mất kiểm tra issuer.

### 10.2. Cách khác: property audience khi chỉ cần chính sách phổ biến

Nếu Spring Boot version đang dùng đã hỗ trợ `spring.security.oauth2.resourceserver.jwt.audiences`, ví dụ ở mục 8 có thể **đủ** để kiểm tra audience mà không cần tạo bean riêng. Đó thường là cách ít mã và dễ bảo trì hơn. Chỉ custom decoder khi có yêu cầu cụ thể như bắt buộc `exp`, giới hạn tuổi token hoặc multi-issuer policy; khi custom cần sở hữu và kiểm thử toàn bộ chuỗi validators.

## 11. Kịch bản kiểm thử tích hợp

Hãy chuẩn bị một **Identity Provider thử nghiệm do bạn quản lý** có endpoint JWKS hợp lệ và cho phép cấp các token kiểm thử theo từng biến thể. Token ví dụ trong tài liệu không mang chữ ký hợp lệ; **không dùng chúng trực tiếp với Gateway rồi mong status 200**.

Để tránh lẫn lỗi JWT với lỗi backend, tạm dùng một route ổn định như:

~~~yaml
# Đặt bên trong danh sách routes theo đúng namespace Gateway WebFlux
- id: orders-api
  uri: http://localhost:9091
  predicates:
    - Path=/api/orders/**
  filters:
    - StripPrefix=1
~~~

Backend ở `localhost:9091` cần có endpoint GET `/orders/42`; có thể dùng echo service đơn giản. Cần nhớ Security WebFilter chạy trước việc kiểm tra kết quả nghiệp vụ, nên khi JWT không hợp lệ backend **không nên** nhìn thấy request.

### 11.1. Gọi không có token

~~~bash
curl -i "http://localhost:8080/api/orders/42"
~~~

Kỳ vọng **401** với route yêu cầu xác thực; tùy cấu hình có thể xuất hiện `WWW-Authenticate: Bearer`. Trạng thái này khác với 404 của một path không route và khác với 503 của `lb://` không có instance.

### 11.2. Gọi với token hợp lệ do IdP phát hành

Trong terminal, lưu **token kiểm thử** vào biến môi trường bằng cách an toàn của hệ điều hành/CI. Minh họa Bash khi biến đã tồn tại:

~~~bash
curl -i "http://localhost:8080/api/orders/42" \
  -H "Authorization: Bearer $ACCESS_TOKEN"
~~~

Với JWT đúng chữ ký, `iss`, `aud`, `exp/nbf` và có authority `SCOPE_orders.read`, security chain cho request đi vào Gateway. Nếu backend endpoint hoạt động, response có thể trả **200**. Không gán mọi response 200 chỉ cho “JWT hợp lệ”: status cuối còn do route, LoadBalancer và backend quyết định.

### 11.3. Ma trận kiểm thử xác thực và phân quyền

| Ca kiểm thử | Dữ liệu token/điều kiện | Kỳ vọng ở Gateway |
| --- | --- | --- |
| A. Thiếu Bearer token | Không có `Authorization` | **401** |
| B. Token sai cấu trúc | Không phải JWT hợp lệ | **401** |
| C. Sửa payload sau khi ký | Chữ ký không còn khớp | **401** |
| D. Sai thuật toán hoặc `alg=none` | Không thuộc allowlist | **401** |
| E. Chữ ký từ khóa không tin cậy | `kid` không tìm thấy khóa phù hợp, hoặc chữ ký sai | **401** |
| F. Sai issuer | `iss` là realm/tenant khác | **401** |
| G. Sai audience | `aud=["billing-api"]`, cần `gateway-api` | **401** |
| H. Thiếu audience | Không có `aud`, policy yêu cầu | **401** |
| I. Hết hạn | `exp` đã quá hạn vượt clock skew | **401** |
| J. Chưa hiệu lực | `nbf` ở tương lai vượt clock skew | **401** |
| K. Thiếu exp | Token không có `exp`, bật `requireExp` của mục 10 | **401** |
| L. Đúng tất cả claims, thiếu scope | JWT hợp lệ nhưng không có `orders.read` | **403** |
| M. Hợp lệ và đủ scope | Có `orders.read` | Được **forward**, status do backend quyết định |
| N. Đã bị thu hồi phía IdP nhưng chưa hết hạn | JWT offline vẫn có chữ ký hợp lệ | Cần **cơ chế thu hồi riêng**; không mặc định từ chối ngay |

**Khi tạo các ca C–K**, hãy dùng IdP test hoặc công cụ phát token **có quyền kiểm soát khóa thử nghiệm**, không sửa token production hay đưa secret thật vào tài liệu/log. Các tình huống yêu cầu claim `exp` có mặt phải được kiểm thử bằng decoder custom nếu policy đó chưa được cấu hình mặc định.

### 11.4. Kiểm thử issuer và audience không được nhầm với scope

Ví dụ hai JWT có cùng:

~~~json
{
  "iss": "https://id.example.test/realms/platform",
  "scope": "orders.read"
}
~~~

nhưng khác `aud`:

~~~text
Token 1: aud = ["gateway-api"] → có thể được Gateway chấp nhận.
Token 2: aud = ["billing-api"] → bị Gateway từ chối.
~~~

Nếu chỉ kiểm chữ ký và scope, Token 2 có thể bị chấp nhận sai, dẫn tới **token confusion/cross-service token reuse**. Bởi vậy audience validation rất quan trọng khi có nhiều microservice dùng chung IdP/JWKS.

## 12. Phân biệt lỗi 401, 403, 404, 429 và 503

Khi bảo vệ Gateway, status không chỉ đến từ JWT decoder:

| Status | Điểm phát sinh thường gặp | Điều tra |
| --- | --- | --- |
| **401** | OAuth2 Resource Server không tìm thấy hoặc không xác thực được Bearer token | Kiểm `iss/aud/exp/nbf/alg/kid` và JWKS |
| **403** | Token hợp lệ, nhưng authorization policy từ chối | Kiểm scope, role mapping, route permission |
| **404** | Gateway không có route, hoặc backend không có endpoint | Xem route ID và path sau biến đổi |
| **429** | Rate limiter ở Gateway chặn request | Kiểm khóa hạn mức, policy và identity đã được xác minh |
| **503** | LoadBalancer không tìm được instance của `lb://service-id` | Kiểm discovery, registry, supplier và health |
| **5xx khác** | Backend lỗi, timeout hoặc proxy/decoder không kết nối JWKS | Phân biệt lỗi mạng hạ tầng với JWT sai |

**Không nên chuyển tất cả lỗi token thành HTTP 403 để “đơn giản hóa”.** 401 là phản hồi xác thực thất bại, 403 thường thể hiện đã xác thực nhưng không đủ quyền; client và monitoring cần phân biệt.

Đối với CORS preflight, `OPTIONS` có thể không mang Bearer token; nếu Security chặn sớm, frontend báo CORS error thay vì lỗi JWT. Khi ứng dụng có frontend browser, cấu hình CORS reactive trước authentication đúng cách và kiểm tra request thật riêng.

## 13. Những sai lầm bảo mật cần tránh

### 13.1. Chỉ đọc payload bằng Base64URL

Việc `Base64.getUrlDecoder()` đọc được JSON claim hoặc thư viện parse trả ra `sub` **không chứng minh** JWT hợp lệ. Toàn bộ kiểm tra phải đi qua `ReactiveJwtDecoder` có chữ ký và validators; không tự tạo `Authentication` từ payload trước khi verify.

### 13.2. Tin mỗi chữ ký, bỏ issuer/audience

Một issuer có thể phát token cho nhiều app và API. Cùng public key **không có nghĩa mọi token đều dành cho Gateway**. Bắt buộc đối chiếu issuer tin cậy, audience yêu cầu và policy resource phù hợp.

### 13.3. Tự tải JWKS từ jku/iss do client cung cấp

Không suy diễn URL lấy khóa từ header/payload của JWT chưa được xác minh. Chỉ dùng endpoint metadata/JWKS của các issuer nằm trong **allowlist cấu hình do server kiểm soát**; áp dụng HTTPS, timeout/cache thích hợp, tránh SSRF và token/key confusion.

### 13.4. Cho phép thuật toán không phù hợp

Không chấp nhận `alg=none` hoặc tự đổi RS256 → HS256 theo header của client. Cấu hình explicit algorithm allowlist và loại khóa tương ứng với IdP; không dùng “decode without verify” trong security flow.

### 13.5. Bỏ exp hoặc cho skew quá lớn

Token có chữ ký hợp lệ nhưng hết hạn phải bị từ chối. Nếu ứng dụng yêu cầu mọi token có `exp`, thêm validator bắt buộc claim này. Dùng đồng bộ đồng hồ; không mở `clockSkew` hàng giờ để né lỗi NTP.

### 13.6. Gateway xác thực xong, backend tin mù quáng

Một service có thể bị gọi trực tiếp nếu mạng không được khóa. Backend cần bảo vệ API theo ranh giới riêng: xác minh token phù hợp hoặc tin thông tin xác thực do Gateway truyền qua kênh bảo vệ (ví dụ mTLS, network policy và header provenance chặt chẽ). Không tin `X-User-Id` do client tự gửi.

### 13.7. Nhầm access token với ID token

**ID token** trong OpenID Connect chủ yếu dành cho client ứng dụng để biết phiên đăng nhập và danh tính người dùng; nó không mặc nhiên là **access token dành cho API**. Không lấy ID token gửi tới Gateway chỉ vì cả hai đều có dạng JWT và cùng issuer.

### 13.8. Truyền token qua URL, logs hoặc công cụ online

Bearer token là **bí mật theo quyền sở hữu**: ai có token có thể thử sử dụng nó tới khi hết hạn hoặc bị thu hồi. Không gửi qua query string, không đưa vào access log, trace, lỗi exception, Git hay website JWT debugger công khai. Có thể đọc metadata từ token test giả nhưng không upload token người dùng thật vào công cụ không tin cậy.

## 14. Tác động của retry, caching và TLS

**JWT key cache:** Resource Server có thể cache JWKS/public keys để tránh gọi IdP trên mọi request. Cần điều chỉnh TTL/refresh phù hợp và lập kế hoạch rotation; không chấp nhận mọi khóa lạ khi JWKS tạm lỗi. Các phiên bản có xử lý discovery/lazy decoder khác nhau; đo startup và request đầu tiên trong môi trường thật.

**Retry:** Retry ở Gateway hoặc LoadBalancer thường áp dụng request tới backend sau khi xác thực. Không được dùng retry để bỏ qua lỗi token, và phải bảo vệ các POST có tác dụng phụ bằng idempotency. Nếu có thêm service token exchange, phân biệt token client với token backend; không biến issuer/audience kiểm tra ở Gateway thành “tự động được mọi backend tin”.

**Rate limiting:** Khóa hạn mức nên dựa trên danh tính **đã xác minh** (ví dụ principal/sub hoặc client ID đáng tin) thay vì claim được giải mã nhưng chưa xác thực hoặc `X-Forwarded-For` chưa được chuẩn hóa. Một request không token nên có chính sách riêng.

**Circuit breaker:** Khi IdP hoặc JWKS không truy cập được, không được “fail open” bằng cách bỏ chữ ký/claim validator. Thiết kế timeout, cache, readiness và cảnh báo riêng; circuit breaker/fallback không tạo quyền truy cập giả.

**TLS:** client → Gateway, Gateway → IdP/JWKS và Gateway → backend là các chặng khác nhau. Sử dụng HTTPS/mTLS theo yêu cầu từng chặng, xác minh certificate và không tắt hostname verification để làm chạy được demo.

## 15. Checklist trước khi triển khai production

- [ ] Gateway dùng **Spring Security Reactive Resource Server** trên WebFlux với dependency JWT/Jose phù hợp.
- [ ] Chỉ nhận access token qua kênh an toàn, phổ biến là `Authorization: Bearer`; không log token.
- [ ] Issuer URI khớp chính xác với `iss` được IdP công bố, gồm scheme/path/trailing slash khi có.
- [ ] JWKS/metadata lấy từ endpoint của issuer **được cấu hình tin cậy**, qua HTTPS.
- [ ] Thuật toán ký nằm trong allowlist; không chấp nhận `none` hoặc thuật toán do token tự áp đặt.
- [ ] Audience bắt buộc chứa API/resource ID được kỳ vọng; không thay `aud` bằng `scope` hay `client_id`.
- [ ] Kiểm tra `exp`/`nbf` và cân nhắc **bắt buộc hiện diện exp**, policy `iat` và maximum token lifetime khi cần.
- [ ] Đồng hồ hệ thống được đồng bộ; clock skew nhỏ và có chủ đích.
- [ ] Custom decoder luôn **kết hợp** validator tiêu chuẩn với validator riêng, không vô tình bỏ issuer/time validation.
- [ ] Phân quyền theo scopes/roles và **quyền nghiệp vụ** sau authentication.
- [ ] Tách rõ 401, 403 và lỗi định tuyến/LoadBalancer/backend.
- [ ] CORS preflight và Spring Security có thứ tự xử lý đúng với frontend browser.
- [ ] Có kịch bản JWKS unavailable, `kid` mới, key rotation và token bị thu hồi.
- [ ] Backend không thể bị truy cập trái phép bằng đường bypass Gateway.
- [ ] Metrics/trace ghi loại lỗi và route ID an toàn, không chứa raw token hay dữ liệu nhạy cảm.
- [ ] Bộ test có token sai chữ ký, issuer, audience, expired, not-before, thiếu exp và thiếu scope.

## 16. Tài liệu chính thức để đối chiếu phiên bản

1. [Spring Security — Reactive OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html): xác minh chữ ký, `issuer-uri`, `jwk-set-uri`, algorithms, timestamp và audience validator.
2. [Spring Security 6.5 — Reactive JWT Resource Server](https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/resource-server/jwt.html): ví dụ `NimbusReactiveJwtDecoder`, `DelegatingOAuth2TokenValidator` và clock skew.
3. [Spring Boot — OAuth2 Resource Server](https://docs.spring.io/spring-boot/reference/security/oauth2.html): properties `spring.security.oauth2.resourceserver.jwt.issuer-uri`, `jwk-set-uri`, `audiences`.
4. [Spring Security — Reactive Authorization](https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html): `SecurityWebFilterChain`, matching và scope/authorization.
5. [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): các claim `iss`, `sub`, `aud`, `exp`, `nbf` và `iat`.
6. [RFC 8725 — JWT Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): algorithm/key confusion, validation chặt chẽ, chống token substitution.
7. [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): định dạng `at+jwt` và các quy tắc cần thiết khi yêu cầu tuân thủ profile này.

**Ghi nhớ:** Xác minh JWT tại Spring Cloud Gateway cần **đủ bốn lớp**: chữ ký từ **khóa/thuật toán tin cậy**, `iss` đúng issuer, `aud` chứa resource phù hợp, `exp/nbf` còn hiệu lực theo clock skew hợp lý. Sau khi xác thực, **authorization theo scope và tài nguyên vẫn là bước riêng**. Dùng Spring Security Reactive Resource Server và các validators tiêu chuẩn, bổ sung validator có chủ đích, kiểm thử cả token sai và không bao giờ tin payload chỉ vì nó đọc được.
