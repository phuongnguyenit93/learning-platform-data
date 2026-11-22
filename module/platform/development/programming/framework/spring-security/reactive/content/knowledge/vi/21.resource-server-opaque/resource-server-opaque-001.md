# Opaque token và sự khác biệt với JWT tự xác minh trong Spring Security reactive

## 1. Mục tiêu học tập

Một hệ thống API sử dụng OAuth 2.0 thường nhận access token qua HTTP header `Authorization: Bearer <token>`. Cùng là Bearer token, nhưng có hệ thống phát một chuỗi **opaque** mà resource server không thể tự đọc nội dung và phải hỏi Authorization Server; hệ thống khác phát **JWT (JSON Web Token)** có cấu trúc và chữ ký, để resource server kiểm tra cục bộ với public key. Hai lựa chọn này ảnh hưởng mạnh tới cách xác thực request, khả năng thu hồi token, độ trễ, mức độ phụ thuộc IdP và ranh giới tin cậy.

Trong **Spring Security reactive / Spring WebFlux**, chủ đề này tương ứng với hai nhánh cấu hình `ServerHttpSecurity.oauth2ResourceServer(...).opaqueToken(...)` và `.jwt(...)`, không phải `HttpSecurity` của Servlet.

Sau bài học, bạn có thể:

1. Giải thích opaque access token, JWT access token, Bearer token và vì sao **định dạng token** khác với **cách xác minh token**.
2. Mô tả quy trình `ReactiveOpaqueTokenIntrospector` gửi token đến OAuth 2.0 Token Introspection Endpoint theo **RFC 7662**, nhận `active` và các metadata rồi tạo `Authentication`.
3. So sánh với `ReactiveJwtDecoder` kiểm JWT signature, `iss`, `exp`, `nbf` và `aud` bằng JWK/public key mà không nhất thiết gọi IdP trên từng request.
4. Cấu hình Spring Boot 4.1.x + Spring Security WebFlux cho opaque token bằng URI, introspection client ID/secret và `SecurityWebFilterChain`.
5. Xây một demo Java 17+ chạy độc lập ở local với **custom reactive introspector được giới hạn vào profile demo**, quan sát HTTP 200/401/403 và ánh xạ scope thành `SCOPE_*`.
6. Phân tích thời gian đáp ứng, lỗi mạng, caching, revocation, audience, bảo mật token/secret và kiểm thử tính đúng đắn.
7. Quyết định khi nào chọn opaque introspection, JWT tự xác minh hoặc **JWT được introspect** để kiểm tra trạng thái online.

**Thông điệp trung tâm:** “Opaque” không đồng nghĩa “bảo mật hơn JWT” một cách tuyệt đối, “JWT” không đồng nghĩa “đã xác thực chỉ vì có ba đoạn Base64URL”, và **Bearer token nào bị lộ cũng có thể bị sử dụng lại** nếu không có ràng buộc bổ sung.

## 2. Khái niệm: Bearer, opaque, JWT và introspection

### 2.1. Bearer là phương thức trình bày, không phải cấu trúc token

Ví dụ hai request:

~~~http
GET /api/messages HTTP/1.1
Host: api.example.com
Authorization: Bearer 9LzSxY7kExampleRandomString
~~~

~~~http
GET /api/messages HTTP/1.1
Host: api.example.com
Authorization: Bearer eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJ1c2VyIn0.signature
~~~

Cả hai sử dụng **Bearer authentication scheme** theo RFC 6750. Chuỗi thứ hai chỉ mô phỏng ba segment JWT, **không phải JWT được ký hợp lệ**; không được gửi làm access token thật. Resource Server quyết định **cơ chế kiểm tra** theo cấu hình, không nên dựa vào việc đếm dấu chấm của chuỗi để tự tin tưởng nó.

Bearer token là credential **ai sở hữu có thể trình lên** cho resource server, trừ khi hệ thống áp dụng các cơ chế proof-of-possession/token binding phù hợp. Do đó luôn cần TLS/HTTPS, hạn chế log/header/query và kiểm soát cấp phát token.

### 2.2. Opaque access token

Một access token **opaque với resource server** nghĩa là resource server không nên hoặc không thể suy ra các claims/quyền chỉ bằng cách parse token. Thường đó là chuỗi ngẫu nhiên, khó đoán, được Authorization Server cấp và ánh xạ tới state ở server.

Ví dụ minh họa:

~~~text
opaque-token: a8f26e7b9c... (chuỗi ngẫu nhiên được cấp)
~~~

Resource Server gửi token tới **introspection endpoint** có kiểm soát, nhận trạng thái `active` và metadata. Nó không cần biết token lưu state ở database, cache hay cơ chế nào bên trong Authorization Server.

**Điểm quan trọng:** một token được xử lý như opaque có thể **mang định dạng JWT**. Nếu resource server luôn gửi chuỗi đó tới introspection endpoint thay vì tự giải mã/chấp nhận chữ ký, phương pháp xác minh thực tế vẫn là **online introspection**. Ngược lại, chuỗi random có vài dấu chấm không trở thành JWT hợp lệ.

### 2.3. JWT access token

JWT là cấu trúc có ba segment khi dùng **JWS Compact Serialization**:

~~~text
BASE64URL(header).BASE64URL(payload).BASE64URL(signature)
~~~

Payload có thể chứa claims như:

~~~json
{
  "iss": "https://idp.example.com",
  "sub": "user-123",
  "aud": ["api.example.com"],
  "scope": "messages.read reports.read",
  "iat": 1790000000,
  "exp": 1790003600
}
~~~

Đây là dữ liệu **minh họa**, không phải token được ký. JWT được ký dạng JWS thông thường chỉ **mã hóa Base64URL**, không bảo mật nội dung payload; ai có chuỗi đều có thể đọc claims. JWE là dạng **mã hóa**, khác với JWS; không tự giả định một JWT là bí mật vì payload trông khó đọc.

Resource server **không chỉ decode** payload rồi tin claims. Nó cần:

- Verify chữ ký và thuật toán tin cậy, không chấp nhận `alg=none` hoặc algorithm confusion.
- Kiểm issuer `iss` là một issuer được phép.
- Kiểm thời gian `exp` và `nbf`, xử lý clock skew có kiểm soát.
- Kiểm `aud`/resource indicators ứng với chính API, và các ràng buộc tenant/client/scope cần thiết.
- Lấy public key từ **JWK Set** tin cậy; xử lý key rotation mà không chấp nhận key do attacker cung cấp.
- Kiểm authority ở bước authorization, không coi “JWT valid” là “đủ quyền”.

### 2.4. Hai trục khác nhau

| Trục | Các lựa chọn |
| --- | --- |
| **Định dạng/biểu diễn** | Random opaque string, JWT/JWS, định dạng token khác |
| **Chiến lược xác minh** | Local cryptographic validation, OAuth2 token introspection, lookup trong store/validator chuyên biệt |

Đừng đồng nhất “JWT = luôn xác minh offline” và “opaque = luôn gọi mạng”. Tuy nhiên trong Spring Security WebFlux thông dụng, **`jwt()`** đại diện chiến lược self-verify JWT, còn **`opaqueToken()`** mặc định gọi introspection endpoint.

## 3. Luồng xác thực một opaque Bearer token

~~~text
OAuth2 Client                      Resource Server (WebFlux)          Authorization Server
     |                                       |                              |
     | GET /api/messages                     |                              |
     | Authorization: Bearer opaque-123      |                              |
     |-------------------------------------->|                              |
     |                               Bearer authentication filter           |
     |                               ReactiveOpaqueTokenIntrospector        |
     |                                       | POST /introspect             |
     |                                       | token=opaque-123             |
     |                                       | client authentication       |
     |                                       |----------------------------->|
     |                                       |       active + scope + sub   |
     |                                       |<-----------------------------|
     |                               Map OAuth2AuthenticatedPrincipal        |
     |                               + SCOPE_* authorities                  |
     |                               AuthorizationWebFilter                 |
     |                                      / \                              |
     |                                   pass deny                           |
     |                                     |    |                             |
     |<--------------------------- 200 hoặc 403/401                          |
~~~

Spring Security reactive đảm nhận filter/authentication trong WebFlux. Khi có Bearer token, `ReactiveOpaqueTokenIntrospector.introspect(token)` kiểm token và trả `Mono<OAuth2AuthenticatedPrincipal>`. Sau khi thành công, `BearerTokenAuthentication` được đưa vào `SecurityContext` trong Reactor Context; authorization sử dụng principal và authorities để quyết định quyền.

### 3.1. Request introspection theo RFC 7662

Một request introspection điển hình là **POST HTTPS** với form parameter `token` và client authentication do Authorization Server yêu cầu:

~~~http
POST /oauth2/introspect HTTP/1.1
Host: idp.example.com
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <base64-of-introspection-client-credentials>

token=opaque-123&token_type_hint=access_token
~~~

`token_type_hint` là tùy chọn của giao thức, không phải lúc nào introspector mặc định cũng gửi. Dòng Basic chỉ minh họa HTTP authentication; không ghi raw client secret vào tài liệu, log hoặc command history. Authorization Server có thể hỗ trợ phương thức client authentication khác như mTLS hoặc private_key_jwt; cần cấu hình implementation tương ứng, không giả định một client ID/secret dùng được với mọi IdP.

Một response active theo RFC 7662 có thể là:

~~~json
{
  "active": true,
  "client_id": "report-web",
  "scope": "messages.read reports.read",
  "sub": "user-123",
  "token_type": "Bearer",
  "exp": 1790003600,
  "iat": 1790000000,
  "aud": ["api.example.com"],
  "iss": "https://idp.example.com"
}
~~~

Một token **không active** nên trả response tối giản:

~~~json
{
  "active": false
}
~~~

`active=false` có thể do token không tồn tại, hết hạn, bị revoke, không dành cho resource server đang hỏi hoặc chính sách của Authorization Server. Không sử dụng response đó để phân biệt chi tiết “user nào bị revoke” trong HTTP response công khai.

### 3.2. active không thay thế audience/authorization policy

`active=true` nghĩa là Authorization Server xác nhận trạng thái token theo chính sách introspection của nó. Nhưng resource server vẫn phải bảo vệ **đúng API**:

- Kiểm token được **phát cho resource server này**, không lấy token hợp lệ của API A sang API B.
- Kiểm `aud`, resource indicator, `client_id`/issuer/tenant và scopes khi hợp đồng IdP cung cấp.
- Nếu introspection response không chứa thông tin cần thiết để giới hạn audience, yêu cầu IdP cấu hình chính sách introspection theo resource server hoặc bổ sung validation rõ ràng.
- Không cấp `ROLE_ADMIN` chỉ vì introspection trả một thuộc tính tên `role` chưa được kiểm chứng ngữ nghĩa.
- `active=true` không tự cho phép xem tất cả URL. Rule `hasAuthority("SCOPE_messages.read")` vẫn quyết định.

### 3.3. Lỗi từ introspection endpoint

Phải phân biệt:

| Trường hợp | Bản chất | Nguyên tắc |
| --- | --- | --- |
| HTTP 200 `{"active":true,...}` | Token được xác minh | Tiếp tục authorization |
| HTTP 200 `{"active":false}` | Token không hợp lệ theo server | Từ chối authentication |
| HTTP 401 từ introspection endpoint | **Resource server không authenticate được với IdP** (client secret/method sai) | Sự cố cấu hình hoặc credentials, không mặc nhiên lỗi token của user |
| HTTP 429/503/timeout từ introspection | IdP/network quá tải hoặc lỗi | **Fail closed**; không bỏ qua kiểm tra vì IdP đang lỗi |
| Malformed JSON/thiếu `active` | Response không đúng protocol | Không suy token active |
| HTTP 403 ở API sau introspection active | Token có thể hợp lệ nhưng thiếu scope | Authorization denied; không tự đổi thành lỗi token |

Người dùng ngoài chỉ nên nhận lỗi phù hợp HTTP security contract (thường 401 khi token invalid, 403 khi thiếu scope; với outage có thể là 5xx tùy xử lý). Không phơi stack trace, client secret, token, internal endpoint hoặc chi tiết introspection trong response.

## 4. JWT tự xác minh ở Resource Server: luồng đối chiếu

~~~text
Client                   Spring WebFlux Resource Server           Authorization Server
  |                                  |                                  |
  | GET /api/messages                |                                  |
  | Authorization: Bearer JWS        |                                  |
  |--------------------------------->|                                  |
  |                           ReactiveJwtDecoder                       |
  |                           parse header/payload                     |
  |                           find key by kid / trusted JWKS          |
  |                           verify signature + validators           |
  |                                  |                                  |
  |                           key cache miss / rotation? ----------- JWKS|
  |                           (không hỏi introspection mỗi request)    |
  |                           validate iss, exp, nbf, aud              |
  |                           map scopes -> SCOPE_*                    |
  |                           authorization                             |
  |<-------------------------- 200 / 401 / 403                           |
~~~

Với JWT, resource server có thể giữ **public keys** và xác minh token mà không phải gọi IdP ở từng request. Điều này thường giảm latency và giảm phụ thuộc runtime vào introspection endpoint. Nhưng khi khóa rotate, cache JWK hết hạn hoặc issuer thay đổi, resource server vẫn cần chiến lược cập nhật key.

Điểm đổi lại: một JWT được ký hợp lệ **có thể vẫn được chấp nhận cho đến khi hết hạn**, dù user/account/token vừa bị revoke ở phía Authorization Server, trừ khi ứng dụng áp dụng revocation list, introspection, session/token version, thời hạn rất ngắn hoặc một policy check bổ sung.

### 4.1. Tự xác minh không có nghĩa “chỉ kiểm chữ ký”

Một resource server chỉ verify chữ ký mà **không kiểm `aud` hoặc issuer** có thể chấp nhận JWT dành cho dịch vụ khác. JWT **không có cơ chế ngầm** đảm bảo mọi claim đúng cho API; người thiết kế phải xác nhận default validations và bổ sung audience/tenant/permission policy.

Tương tự, một `JwtDecoder` custom thay thế mặc định có thể vô tình bỏ validation `iss`/`aud` nếu cấu hình sai. Để bảo mật, nên dựa trên các validator chuẩn và bổ sung validator rõ, không chỉ decode payload.

### 4.2. Trường hợp JWT cũng dùng introspection

Spring Security Opaque Token support **không phụ thuộc token có mấy segment**. Nếu một JWT được gửi tới introspection endpoint, resource server có thể dùng `opaqueToken()` và để Authorization Server quyết định còn active hay không. Đây là lựa chọn hợp lý khi **revocation nhanh** quan trọng hơn tự xác minh cục bộ. Vì vậy, lựa chọn kỹ thuật nên diễn đạt là:

- **JWT local validation**: kiểm chứng dựa vào chữ ký/public key và claims.
- **Online token introspection**: gọi Authorization Server, áp dụng cho random opaque string **hoặc** JWT.
- **Hybrid**: local JWT validation cộng kiểm trạng thái online theo hành động/độ nhạy; phải thiết kế rõ ràng để không vô tình bypass bước nào.

## 5. Bảng so sánh để ra quyết định

| Tiêu chí | Opaque + introspection | JWT tự xác minh |
| --- | --- | --- |
| Resource server đọc token? | Không cần parse cấu trúc | Phải decode/verify JWS |
| Nguồn quyết định token active | Authorization Server (introspection) | Chữ ký + claims/validators cục bộ |
| Network call khi xác thực | Thường **mỗi request** nếu không cache | Thường không, trừ JWKS discovery/refresh |
| Thu hồi trước khi hết hạn | Có thể thấy gần tức thời khi introspection real time | Không tự thấy nếu token vẫn signature/claim hợp lệ |
| Ảnh hưởng khi IdP tạm lỗi | Cao nếu không có cache | Thường ít hơn khi public key đã cache |
| Độ trễ mỗi request | Thêm mạng và xử lý endpoint | Crypto verify cục bộ, latency thường thấp hơn |
| Khả năng mở rộng | Introspection phải scale theo lưu lượng API hoặc cache | Phân tán dễ hơn, không cần central per-request lookup |
| Token chứa PII | Chuỗi opaque thường không lộ claims cho client | JWS payload đọc được nếu sở hữu token |
| Chi phí lưu state | AS thường cần token state/lookup | Có thể stateless ở AS, nhưng còn rotation/revocation tradeoff |
| Complexity chính | Trust introspection endpoint, HTTP client, credentials, availability | JWKS, crypto, alg, issuer/audience/time validators |
| Scope/role | Từ introspection response | Từ JWT claims đã verify |
| Caching | Giảm tải nhưng làm revocation chậm | Cache JWKS; token validation vẫn phải thực hiện |
| JWT dùng introspection? | **Có thể** | Không áp dụng nếu chỉ chọn local decoder |
| Phù hợp | Quyền có thể thu hồi sớm, IdP tập trung | API nhiều request, nhiều services, latency thấp |
| Failure mode | Timeout/503 introspection → fail closed | Signature/key/claim invalid → fail closed |

**Không có lựa chọn luôn thắng.** Với giao dịch nhạy cảm và yêu cầu thu hồi ngay, introspection có lợi. Với API throughput cao, JWT tự xác minh thường hợp lý nếu access token TTL ngắn và có chính sách thu hồi bổ sung cho hành động rủi ro.

## 6. Các API reactive của Spring Security

| Thành phần | Opaque | JWT |
| --- | --- | --- |
| DSL `ServerHttpSecurity` | `oauth2ResourceServer(o -> o.opaqueToken(...))` | `oauth2ResourceServer(o -> o.jwt(...))` |
| Validator chính | `ReactiveOpaqueTokenIntrospector` | `ReactiveJwtDecoder` |
| Default implementation | `SpringReactiveOpaqueTokenIntrospector` | `NimbusReactiveJwtDecoder` theo config |
| Input | `String token` | `String token` |
| Output | `Mono<OAuth2AuthenticatedPrincipal>` | `Mono<Jwt>` |
| Authentication thường gặp | `BearerTokenAuthentication` | `JwtAuthenticationToken` |
| Principal | `OAuth2AuthenticatedPrincipal` | `Jwt` |
| Authorities mặc định | Scope introspection → `SCOPE_*` | Scope/`scp` JWT → `SCOPE_*` |
| Spring Boot property namespace | `spring.security.oauth2.resourceserver.opaquetoken.*` | `spring.security.oauth2.resourceserver.jwt.*` |
| Cần OAuth2 Client registration? | **Không**, đây là Resource Server | **Không**, đây là Resource Server |

### 6.1. ReactiveOpaqueTokenIntrospector

Chữ ký rút gọn:

~~~java
@FunctionalInterface
public interface ReactiveOpaqueTokenIntrospector {
    Mono<OAuth2AuthenticatedPrincipal> introspect(String token);
}
~~~

Đây là đoạn mô tả contract, **không** phải class cần tự định nghĩa. Import đúng:

~~~java
import org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import reactor.core.publisher.Mono;
~~~

Publisher phải **emit principal đã xác minh** nếu token hợp lệ; token inactive/invalid phải **error**, không tạo principal “anonymous nhưng authenticated” để bypass. Với implementation chuẩn, `SpringReactiveOpaqueTokenIntrospector` thực hiện HTTP introspection và áp response theo RFC 7662.

**Không dùng** `OpaqueTokenIntrospector` hoặc `SpringOpaqueTokenIntrospector` của Servlet/đồng bộ trong WebFlux, trừ khi bạn thật sự chủ động bridge blocking qua scheduler (thường không cần). Tránh `block()` trong `introspect(...)` trên event loop.

### 6.2. Cấu hình WebFlux DSL

Một chain tối thiểu:

~~~java
@Bean
SecurityWebFilterChain filterChain(ServerHttpSecurity http) {
    return http
            .authorizeExchange(exchanges ->
                    exchanges.anyExchange().authenticated())
            .oauth2ResourceServer(oauth2 ->
                    oauth2.opaqueToken(Customizer.withDefaults()))
            .build();
}
~~~

Đây là **method snippet**, cần import `@Bean`, `ServerHttpSecurity`, `SecurityWebFilterChain` và `Customizer`. Khi dùng properties introspection của Spring Boot, các thông tin `introspection-uri`/client ID/secret có thể được Boot auto-configure. Nếu tự định nghĩa `ReactiveOpaqueTokenIntrospector` bean hoặc gọi `.introspector(custom)`, bạn đang **thay thế** default introspection, phải đảm bảo custom code thực sự xác minh token.

### 6.3. Spring Boot properties — opaque resource server

~~~properties
spring.security.oauth2.resourceserver.opaquetoken.introspection-uri=${INTROSPECTION_URI}
spring.security.oauth2.resourceserver.opaquetoken.client-id=${INTROSPECTION_CLIENT_ID}
spring.security.oauth2.resourceserver.opaquetoken.client-secret=${INTROSPECTION_CLIENT_SECRET}
~~~

Khi bài được lưu, ký hiệu `${...}` được đổi thành property placeholder chuẩn dùng dấu dollar. Endpoint phải dùng **HTTPS** và chỉ chấp nhận Authorization Server đã tin cậy. Đây là **introspection client credentials**, không phải client ID/secret của một người dùng đang gọi API; không để trong Git, không in log, quản lý bằng secret manager và rotation.

### 6.4. Tùy chỉnh bằng SpringReactiveOpaqueTokenIntrospector

Trong Spring Security 6.5+/7.x, constructor nhận URI/ID/secret cũ có thể đã deprecated; Javadoc hướng dẫn dùng **builder**:

~~~java
ReactiveOpaqueTokenIntrospector introspector =
        SpringReactiveOpaqueTokenIntrospector
                .withIntrospectionUri(introspectionUri)
                .clientId(introspectionClientId)
                .clientSecret(introspectionClientSecret)
                .build();
~~~

Đây là snippet bên trong configuration class, các biến trên phải được inject từ secret/config được bảo vệ. Khi tự tạo bean:

~~~java
@Bean
ReactiveOpaqueTokenIntrospector customIntrospector(
        @Value("${demo.introspection-uri}") String uri,
        @Value("${demo.introspection-client-id}") String id,
        @Value("${demo.introspection-client-secret}") String secret) {
    return SpringReactiveOpaqueTokenIntrospector.withIntrospectionUri(uri)
            .clientId(id)
            .clientSecret(secret)
            .build();
}
~~~

Đoạn bean này là **tùy chọn** cho ứng dụng có ba property `demo.*`, **không đồng thời dùng** với bean mock introspector của phần demo. Nó minh họa cách xây builder; với cấu hình mặc định đủ tốt, **ưu tiên chỉ cấu hình ba Spring Boot properties** ở phần 6.3.

### 6.5. Tùy chỉnh authorization

Introspection response:

~~~json
{
  "active": true,
  "sub": "reader",
  "scope": "messages.read reports.read"
}
~~~

Spring Security mặc định map scope thành:

~~~text
SCOPE_messages.read
SCOPE_reports.read
~~~

Policy ví dụ:

~~~java
.pathMatchers("/api/messages")
        .hasAuthority("SCOPE_messages.read")
.pathMatchers("/api/admin")
        .hasAuthority("SCOPE_admin")
~~~

`hasAuthority` kiểm chính xác chuỗi. `hasRole("ADMIN")` mặc định tìm `ROLE_ADMIN`, **không tự thấy `SCOPE_admin`**. Nếu IdP có claim role riêng, cần mapper từ nguồn đáng tin theo allowlist và không tự nối `ROLE_` vào mọi string từ client.

## 7. Ví dụ Java 17+ chạy local: Resource Server Opaque

Để **không cần đăng ký một IdP thật** khi học, ta dùng một `ReactiveOpaqueTokenIntrospector` trong profile `demo`. Nó nhận **chính xác hai token minh họa cố định** và từ chối mọi giá trị khác. Điều này giúp nhìn thấy đường đi HTTP/Authentication/Authorization thực tế trong Spring Security WebFlux.

**Cảnh báo bắt buộc:** đây chỉ là **fake introspector để học**, hoàn toàn **không có bảo mật token thật**. Không bật profile `demo` ở production hoặc công khai ra Internet; production phải dùng introspection endpoint thật. Mọi dữ liệu/token thử nghiệm dưới đây không có giá trị bảo mật.

### 7.1. Tạo project

Dùng Maven + Java 17+, group `com.example`, artifact `reactive-opaque-demo`, Spring Boot **4.1.2**, chọn **Spring Reactive Web**, **Spring Security** và **OAuth2 Resource Server**.

Với Spring Boot 4, starter chuẩn mang tên `spring-boot-starter-security-oauth2-resource-server` (starter tên `spring-boot-starter-oauth2-resource-server` cũ được giữ tương thích/deprecated). File `pom.xml` đầy đủ:

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
    <version>4.1.2</version>
    <relativePath/>
  </parent>
  <groupId>com.example</groupId>
  <artifactId>reactive-opaque-demo</artifactId>
  <version>0.0.1-SNAPSHOT</version>
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
      <artifactId>spring-boot-starter-security-oauth2-resource-server</artifactId>
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

Không thêm `spring-boot-starter-webmvc` hoặc `spring-boot-starter-web` để tránh trộn Servlet/MVC với WebFlux. Để Boot BOM quản lý phiên bản các module Spring Security; không chọn các phiên bản riêng mâu thuẫn.

### 7.2. Java source hoàn chỉnh

Tạo file `src/main/java/com/example/opaque/OpaqueVsJwtApplication.java`:

~~~java
package com.example.opaque;

import java.util.List;
import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Profile;
import org.springframework.http.MediaType;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.authentication.BearerTokenAuthentication;
import org.springframework.security.oauth2.server.resource.introspection.BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@SpringBootApplication
@EnableWebFluxSecurity
public class OpaqueVsJwtApplication {

    public static void main(String[] args) {
        SpringApplication.run(OpaqueVsJwtApplication.class, args);
    }

    @Bean
    SecurityWebFilterChain security(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/public").permitAll()
                        .pathMatchers("/api/messages")
                                .hasAuthority("SCOPE_messages.read")
                        .pathMatchers("/api/admin")
                                .hasAuthority("SCOPE_admin")
                        .pathMatchers("/api/me").authenticated()
                        .anyExchange().denyAll())
                .httpBasic(basic -> basic.disable())
                .formLogin(form -> form.disable())
                .oauth2ResourceServer(oauth2 ->
                        oauth2.opaqueToken(Customizer.withDefaults()))
                .build();
    }

    // Chỉ dùng cho local demo. KHÔNG chạy profile demo ở production.
    @Bean
    @Profile("demo")
    ReactiveOpaqueTokenIntrospector demoOpaqueIntrospector() {
        return token -> {
            if ("opaque-reader-demo".equals(token)) {
                return Mono.just(principal(
                        "reader", "messages.read",
                        List.of("SCOPE_messages.read")));
            }
            if ("opaque-admin-demo".equals(token)) {
                return Mono.just(principal(
                        "administrator", "messages.read admin",
                        List.of("SCOPE_messages.read", "SCOPE_admin")));
            }
            // Không trả Mono.empty() hoặc fake anonymous principal.
            // Invalid token phải là authentication failure.
            return Mono.error(new BadOpaqueTokenException(
                    "Inactive or unknown token"));
        };
    }

    private static OAuth2AuthenticatedPrincipal principal(
            String subject, String scopes, List<String> authorities) {

        List<GrantedAuthority> granted = authorities.stream()
                .map(SimpleGrantedAuthority::new)
                .map(authority -> (GrantedAuthority) authority)
                .toList();

        return new DefaultOAuth2AuthenticatedPrincipal(
                subject,
                Map.of("sub", subject, "scope", scopes),
                granted);
    }

    @RestController
    static class Api {

        @GetMapping(value = "/public",
                produces = MediaType.APPLICATION_JSON_VALUE)
        Mono<Map<String, String>> publicEndpoint() {
            return Mono.just(Map.of("message", "PUBLIC_OK"));
        }

        @GetMapping(value = "/api/me",
                produces = MediaType.APPLICATION_JSON_VALUE)
        Mono<Map<String, Object>> me(
                BearerTokenAuthentication authentication) {
            return Mono.just(Map.<String, Object>of(
                    "subject", authentication.getName(),
                    "authorities", authentication.getAuthorities()
                            .stream()
                            .map(GrantedAuthority::getAuthority)
                            .sorted()
                            .toList()));
        }

        @GetMapping(value = "/api/messages",
                produces = MediaType.APPLICATION_JSON_VALUE)
        Mono<Map<String, String>> messages() {
            return Mono.just(Map.of("message", "MESSAGES_OK"));
        }

        @GetMapping(value = "/api/admin",
                produces = MediaType.APPLICATION_JSON_VALUE)
        Mono<Map<String, String>> admin() {
            return Mono.just(Map.of("message", "ADMIN_OK"));
        }
    }
}
~~~

**Phân tích kỹ:**

1. Bean `SecurityWebFilterChain` cấu hình đúng reactive `ServerHttpSecurity`.
2. `oauth2ResourceServer(...opaqueToken(...))` dùng opaque authentication manager; Spring Security tìm bean `ReactiveOpaqueTokenIntrospector` phù hợp.
3. `@Profile("demo")` khiến fake token acceptance chỉ có khi profile `demo` được bật. **Production không được bật profile này**; khi tắt demo cần cấu hình introspection endpoint và credentials như phần 8.
4. Trong fake introspector, `Mono.just(principal(...))` là kết quả token được coi active; `Mono.error(new BadOpaqueTokenException(...))` thể hiện token không active. Không dùng `Mono.empty()` như cách lặng lẽ coi token hợp lệ.
5. `DefaultOAuth2AuthenticatedPrincipal` giữ name, attributes và explicit authorities. Fake implementation tự đặt scopes/authorities; thực tế `SpringReactiveOpaqueTokenIntrospector` mới lấy từ introspection endpoint.
6. `BearerTokenAuthentication` ở controller được Spring Security cung cấp **sau authentication thành công**. Không tự lấy token từ header trong controller rồi parse/authorize.
7. `/api/messages` yêu cầu `SCOPE_messages.read`. `/api/admin` yêu cầu `SCOPE_admin`. Token reader hợp lệ không có admin scope → **403**.
8. `/public` có `permitAll()`, nhưng nếu client **cố ý gửi Bearer token sai** vào public route, authentication filter vẫn có thể từ chối trước controller; thử public **không gửi token**.
9. Các endpoint demo chỉ có GET, chưa cần xử lý CSRF của cookie-authenticated POST. Với API chỉ dùng Bearer token và không có cookie/session credentials browser tự gửi, threat model CSRF khác; không tự tắt CSRF toàn hệ thống khi còn form/session login.
10. Token demo **không có tính bảo mật**, không dùng làm proof về signature, introspection protocol hay revocation thực tế.
11. `Map.of` không cam kết thứ tự key JSON; test nên so các giá trị theo tên field.
12. Vì demo dùng hai literal token, nội dung `Authorization` tuyệt đối không được dùng trong hệ thống được truy cập từ Internet.

### 7.3. Chạy local demo

Trong thư mục chứa `pom.xml`:

~~~bash
./mvnw clean package
SPRING_PROFILES_ACTIVE=demo ./mvnw spring-boot:run
~~~

Trên Windows PowerShell, đặt biến môi trường:

~~~powershell
$env:SPRING_PROFILES_ACTIVE = "demo"
.\mvnw.cmd clean package
.\mvnw.cmd spring-boot:run
~~~

Nếu không có wrapper, dùng `mvn` đã cài. Với source trên, Spring Boot chạy mặc định ở `http://localhost:8080`. **Chỉ mở ở localhost**, dùng dữ liệu giả để học; khi deploy thật bật HTTPS và dùng introspection online.

### 7.4. Gọi API bằng curl

~~~bash
# Endpoint public không cần Authorization.
curl -i http://localhost:8080/public

# Endpoint private thiếu Bearer.
curl -i http://localhost:8080/api/me

# Opaque reader hợp lệ.
curl -i -H 'Authorization: Bearer opaque-reader-demo' \
  http://localhost:8080/api/me

# Reader xem messages.
curl -i -H 'Authorization: Bearer opaque-reader-demo' \
  http://localhost:8080/api/messages

# Reader không có admin authority.
curl -i -H 'Authorization: Bearer opaque-reader-demo' \
  http://localhost:8080/api/admin

# Admin có đủ scope.
curl -i -H 'Authorization: Bearer opaque-admin-demo' \
  http://localhost:8080/api/admin

# Token không được công nhận.
curl -i -H 'Authorization: Bearer unknown-demo-token' \
  http://localhost:8080/api/me
~~~

Bảng expected behavior:

| Request | Status | Nội dung chính |
| --- | --- | --- |
| `GET /public` không header | **200** | `{"message":"PUBLIC_OK"}` |
| `GET /api/me` anonymous | **401** | Bearer challenge; không có principal hợp lệ |
| `GET /api/me` reader | **200** | Subject `reader`, authorities có `SCOPE_messages.read` |
| `GET /api/messages` reader | **200** | `{"message":"MESSAGES_OK"}` |
| `GET /api/admin` reader | **403** | Token valid nhưng không có `SCOPE_admin` |
| `GET /api/admin` admin | **200** | `{"message":"ADMIN_OK"}` |
| `GET /api/me` unknown | **401** | Token fake introspector từ chối |

Status/error body/header chi tiết của 401/403 có thể phụ thuộc Spring Security version và exception handler; đừng assert một chuỗi JSON lỗi mặc định không do controller tạo. Trong WebFlux, principal tồn tại nhờ Reactor Security Context sau filter, không nhờ Servlet `HttpSession`.

### 7.5. Bài thực hành: quan sát không cần token parser

Hãy thử ba thay đổi nhỏ **chỉ ở local**:

1. Đổi `"opaque-reader-demo"` thành một token không được bean công nhận: nhận 401, dù chuỗi có thể trông giống JWT.
2. Gọi `/api/admin` bằng token reader: nhận 403, bởi authentication thành công nhưng authorization thiếu scope.
3. Thêm `SCOPE_admin` vào list authority của reader trong fake introspector: sau restart, `/api/admin` thành công. Điều này chứng minh **quyền đến từ kết quả introspection/mapping đáng tin**, không đơn thuần từ hình thức chuỗi token.

Đây là bài học trách nhiệm của server; đừng bao giờ cho phép client tự gửi authority list và bỏ kiểm tra nguồn.

## 8. Chuyển từ demo sang introspection thật

### 8.1. Tắt profile demo và cấu hình production

Không đặt `SPRING_PROFILES_ACTIVE=demo` ở server thật. Đặt ba Spring Boot properties trong `application.properties`, hoặc biến môi trường/secret manager phù hợp:

~~~properties
spring.security.oauth2.resourceserver.opaquetoken.introspection-uri=${INTROSPECTION_URI}
spring.security.oauth2.resourceserver.opaquetoken.client-id=${INTROSPECTION_CLIENT_ID}
spring.security.oauth2.resourceserver.opaquetoken.client-secret=${INTROSPECTION_CLIENT_SECRET}
~~~

Đặt giá trị thật thông qua secret manager hoặc môi trường được quản lý:

~~~bash
export INTROSPECTION_URI='https://idp.example.com/oauth2/introspect'
export INTROSPECTION_CLIENT_ID='api-resource-server'
export INTROSPECTION_CLIENT_SECRET='secret-issued-by-idp'
./mvnw spring-boot:run
~~~

**Các giá trị ở ví dụ là minh họa**, không có IdP công khai nào được dựng sẵn. Phải thay bằng endpoint introspection thật, client credentials thật và token thật đã được Authorization Server cấp. Spring Boot sẽ cấu hình `SpringReactiveOpaqueTokenIntrospector` khi không có bean mock introspector đang active.

Ở production không để introspection secret trong Git, không log request body/headers chứa bearer/secret, đặt timeout, pool và khả năng giám sát kết nối tới IdP theo topology thực tế.

### 8.2. Kiểm tra token trước khi tích hợp Spring

Nếu bạn có một access token test và một introspection client hợp lệ, một cách thăm dò thủ công **trong môi trường được bảo vệ**:

~~~bash
curl --fail-with-body \
  --user "$INTROSPECTION_CLIENT_ID:$INTROSPECTION_CLIENT_SECRET" \
  --data-urlencode "token=$ACCESS_TOKEN" \
  "$INTROSPECTION_URI"
~~~

Cần bảo đảm endpoint HTTPS tin cậy. **Không bật verbose HTTP logging**, không đưa token vào URL, ticket, screenshot công khai hay shell history. Lệnh có thể làm credential xuất hiện trong process arguments tùy môi trường; với production nên dùng tooling/secret injection được quản trị và kiểm soát log.

Nếu IdP trả `{"active":false}`, **đừng** sửa response hoặc tạo local principal để ép API 200. Hãy kiểm tra token thật được cấp cho resource server nào, có hết hạn/revoke hay sai client authentication/issuer không.

### 8.3. Chính sách tối thiểu cho resource server

Khi introspection có `active=true`, resource server **vẫn phải** yêu cầu authority phù hợp từng route:

~~~java
.authorizeExchange(exchanges -> exchanges
        .pathMatchers("/api/messages")
                .hasAuthority("SCOPE_messages.read")
        .pathMatchers("/api/admin")
                .hasAuthority("SCOPE_admin")
        .anyExchange().authenticated())
~~~

Nếu introspection response sử dụng claim riêng, phải ánh xạ có kiểm soát trước khi autorization quyết định. Đặc biệt kiểm `aud` và resource restriction khi API gồm nhiều dịch vụ. Một token active của client khác hoặc audience khác **không được tự nhiên truy cập API này**.

### 8.4. Mô hình custom delegate để kiểm policy

Nếu cần thêm kiểm issuer/audience từ metadata introspection, có thể bao một introspector chuẩn bằng một wrapper:

~~~java
ReactiveOpaqueTokenIntrospector delegate =
        SpringReactiveOpaqueTokenIntrospector
                .withIntrospectionUri(introspectionUri)
                .clientId(clientId)
                .clientSecret(clientSecret)
                .build();

ReactiveOpaqueTokenIntrospector validating = token ->
        delegate.introspect(token)
                .flatMap(principal -> {
                    Object aud = principal.getAttribute("aud");
                    if (!(aud instanceof java.util.Collection<?> c)
                            || !c.contains("api.example.com")) {
                        return Mono.error(new BadOpaqueTokenException(
                                "Token not intended for this API"));
                    }
                    return Mono.just(principal);
                });
~~~

Đây là **snippet cấu hình tùy chọn**, không phải file chạy độc lập. Nó **giả định IdP contract trả `aud` dưới dạng Collection**; nếu provider trả String hoặc một metadata khác, phải sửa validator theo schema đã thỏa thuận thay vì bỏ qua audience check. Phải dùng introspection client có quyền hỏi về token dành cho API này và bảo vệ response data. Với tính năng mạnh hơn, có thể dùng `ReactiveOpaqueTokenAuthenticationConverter` để tùy chỉnh principal/authorities sau introspection.

### 8.5. Không coi introspection client ID là user client ID

Introspection endpoint có thể yêu cầu **resource server credentials** để hỏi token, khác với client đã xin token cho user. Giá trị `client_id` trong introspection response là thông tin về client gốc mà token được cấp cho; khác với `INTROSPECTION_CLIENT_ID` dùng để resource server authenticate tới IdP. Đừng đối chiếu nhầm hai giá trị nếu hợp đồng không đòi chúng giống nhau.

## 9. So sánh cấu hình JWT tự xác minh

Cũng trên Spring Boot WebFlux, nếu IdP phát JWT access token và API muốn **verify chữ ký cục bộ**, dùng cấu hình JWT thay cho opaque.

### 9.1. application.properties cho JWT

~~~properties
spring.security.oauth2.resourceserver.jwt.issuer-uri=${JWT_ISSUER_URI}
spring.security.oauth2.resourceserver.jwt.audiences=${JWT_EXPECTED_AUDIENCE}
~~~

Ví dụ triển khai thật phải thay issuer/audience bằng thông tin được IdP công bố. `issuer-uri` dùng discovery metadata để tìm JWK Set; `audiences` kiểm token thực sự được cấp cho API này. Ngoài ra có thể cấu hình `jwk-set-uri` khi muốn chỉ rõ endpoint public keys hoặc không để discovery tạo dependency ở startup/first request, nhưng vẫn cần validator `iss`/`aud` thích hợp.

### 9.2. SecurityWebFilterChain JWT

~~~java
@Bean
SecurityWebFilterChain jwtSecurity(ServerHttpSecurity http) {
    return http
            .authorizeExchange(exchanges -> exchanges
                    .pathMatchers("/api/messages")
                            .hasAuthority("SCOPE_messages.read")
                    .anyExchange().authenticated())
            .oauth2ResourceServer(oauth2 ->
                    oauth2.jwt(Customizer.withDefaults()))
            .build();
}
~~~

**Snippet để thay thế** chain opaque trong ứng dụng dùng JWT; không copy thêm một chain match-all thứ hai cùng thứ tự. Với JWT, bean chính là `ReactiveJwtDecoder`, và đối tượng `Authentication` thường là `JwtAuthenticationToken`. Kiểm thuật toán được phép, chữ ký, issuer, expiresAt, notBefore và audience. `JWT_EXPECTED_AUDIENCE` không tự có giá trị mặc định an toàn cho mọi dự án — phải đặt theo resource server.

### 9.3. Vì sao “tôi decode được JWT” không đủ?

Một JWT có payload `{"scope":"admin"}` có thể được **bất kỳ ai tự tạo** nếu server chỉ Base64URL decode mà không verify chữ ký. Không viết code kiểu:

~~~javascript
// ANTI-PATTERN: đọc payload chỉ để hiển thị,
 // KHÔNG ĐƯỢC coi là xác thực token.
const payload = JSON.parse(atob(token.split(".")[1]));
if (payload.scope === "admin") grantAdmin();
~~~

Đoạn này là anti-pattern để nhận diện; Base64URL còn có quy tắc khác Base64 thường. Đặt authorization ở server sau khi token đã được Spring Security verify bằng trusted decoder và validators.

### 9.4. Public key cache và revocation

Resource server JWT có thể cache JWKS và không phải gọi IdP trên từng request. Nó vẫn có thể cần cập nhật public keys khi IdP rotate hoặc `kid` chưa có trong cache. Nếu tài khoản bị khóa hoặc token bị revoke nhưng JWT chưa hết hạn, local verify có thể **tiếp tục chấp nhận token** theo chính sách cho đến hết `exp`; cần cơ chế thu hồi riêng cho yêu cầu chặt chẽ.

Đừng dựa vào việc “xóa public key JWT” để revoke một user token duy nhất: đó có thể làm hỏng **tất cả token** được ký bằng cùng key. Nếu cần thu hồi từng token nhanh, cân nhắc opaque introspection hoặc hybrid/revocation list được thiết kế rõ.

## 10. Khi nào chọn loại nào?

### 10.1. Opaque + introspection thường phù hợp khi

- Hệ thống cần **thu hồi access token gần thời gian thực**.
- Quyền/scopes có thể thay đổi nhanh; cần Authorization Server là nguồn quyết định tập trung.
- Tập services không quá lớn hoặc introspection endpoint có đủ năng lực/HA.
- Muốn hạn chế dữ liệu claims lộ trong token mà client có thể decode.
- Có khả năng vận hành HTTPS introspection với SLA, timeout, observability, secret rotation.

### 10.2. JWT tự xác minh thường phù hợp khi

- Lưu lượng API lớn hoặc nhiều microservices cần latency thấp.
- Dịch vụ cần hoạt động khi IdP ngắn hạn không sẵn sàng, miễn JWK cache còn hợp lệ.
- Access token TTL ngắn và độ trễ revocation chấp nhận được hoặc có revocation check riêng.
- Đội vận hành quản lý được JWKS/algorithm/key rotation/issuer/audience validation.
- Các claims tối thiểu không gây lộ PII không cần thiết cho bearer holder.

### 10.3. Hybrid: JWT + introspection

Nếu IdP phát JWT nhưng yêu cầu **revocation nhanh**, có thể:

1. Dùng `opaqueToken()` để introspect JWT như bất kỳ bearer string nào; **không** vừa local verify vừa introspect trừ khi policy yêu cầu.
2. Dùng `jwt()` local verify ở phần lớn request, nhưng gọi trạng thái online riêng ở route/hành động nhạy cảm.
3. Dùng access token JWT lifetime ngắn và refresh-token revocation ở Authorization Server theo threat model.

Mỗi phương án có tradeoff; nếu muốn hybrid, định nghĩa rõ **khả năng thất bại của từng lớp** và điều kiện fail closed. Tránh “introspection lỗi thì fallback local verify” một cách âm thầm ở tài nguyên yêu cầu revocation tức thời.

## 11. Caching, hiệu năng và tính nhất quán

### 11.1. Request nào cũng introspect có thể tốn kém

Giả sử một request vào API phải gọi HTTPS tới IdP; nếu số request tăng, introspection endpoint và mạng trở thành một dependency trên critical path. Độ trễ của request phụ thuộc:

~~~text
Tổng thời gian ~ network tới resource server
               + network tới introspection
               + xử lý trạng thái token ở IdP
               + authorization/controller work
~~~

Đây là công thức mô hình, không phải dự báo latency cụ thể. Cần đo P50/P95/P99, timeout, circuit breaker và saturation thực tế. Đừng thiết kế server chỉ có một IdP endpoint ở một vùng mạng mà không có phương án HA.

### 11.2. Có nên cache introspection result?

Có thể, nhưng caching làm giảm hiệu lực thu hồi token:

| Chính sách | Lợi ích | Rủi ro |
| --- | --- | --- |
| Không cache kết quả introspection | Mỗi request có trạng thái mới nhất | Tải/latency cao, phụ thuộc IdP |
| Cache positive rất ngắn | Giảm số lần gọi | Revoke có thể chưa có hiệu lực đến hết TTL |
| Cache theo token đến `exp` | Giảm nhiều call | Vô hiệu lợi ích revocation gần real-time |
| Cache negative ngắn có kiểm soát | Giảm bão request token sai | Cần tránh làm lệch hành vi token mới/phân loại outage |
| JWKS cache cho JWT | Giảm call public key | Không đồng nghĩa cache trạng thái từng JWT |

Nếu cache introspection, TTL nên **không vượt quá phần thời gian còn lại của token** và phải nhỏ hơn mức stale-authorization tối đa nghiệp vụ chấp nhận. Với action nhạy cảm, cân nhắc bypass cache hoặc query lại trạng thái. Hãy test revoke token ngay sau cache hit.

**Bảo mật cache key:** tránh lưu raw bearer token trong metric/log/Redis key hiển thị. Dùng HMAC/fingerprint được quản lý key và tránh cache value chứa PII không cần thiết. Invalidate cache khi có revocation event nếu IdP hỗ trợ, nhưng vẫn giữ expiry-bound TTL.

### 11.3. Đừng tưởng Mono.cache() tự tạo cache toàn ứng dụng

~~~java
return delegate.introspect(token).cache();
~~~

Đây là **anti-pattern nếu được viết bên trong method introspect của mỗi request** với mong muốn cache xuyên request. Mỗi invocation có thể tạo một `Mono` mới; `cache()` chỉ memoize publisher instance đó, không tự tạo token cache toàn cục. Muốn cache xuyên requests phải có store/key/TTL/concurrency control thực, và tính tới token revocation.

### 11.4. Khi introspection down

Không làm:

~~~java
return delegate.introspect(token)
        .onErrorResume(error ->
                Mono.just(fakeAuthenticatedPrincipal));
~~~

Đây là **anti-pattern** minh họa, `fakeAuthenticatedPrincipal` chưa định nghĩa và **không phải code biên dịch độc lập**. Nó biến lỗi IdP thành authentication thành công và có thể bypass revocation/authorization. Nếu hệ thống có fail-open vì availability, phải được review đặc biệt, có điều kiện an toàn, không phải default API security.

Với các request nhạy cảm, fail closed: từ chối access và báo lỗi hạ tầng phù hợp, tách metric `invalid_token` khỏi `introspection_unavailable`. Không ẩn 5xx/timeout của IdP thành “sai password” trong dashboard và không retry vô hạn.

## 12. 401, 403, audience và lỗi cấu hình

| Tình huống | HTTP resource server thường thấy | Cần kiểm tra |
| --- | --- | --- |
| Thiếu Authorization ở protected URL | **401** + Bearer challenge | Client có gửi header không |
| Token malformed/unknown/inactive | **401** | Introspection trả active false? Bearer format? |
| Token active nhưng thiếu `SCOPE_messages.read` | **403** | Scope và mapping authority |
| Token active nhưng `aud` sai | **401** nếu được validator xem là invalid | IdP introspection audience contract |
| Token active, scope đúng, handler chạy | **200** | Business rule vẫn phải kiểm |
| IdP introspection 401 | Có thể lỗi hạ tầng (resource server client credentials) | Client ID/secret và auth method |
| Introspection timeout/503 | Lỗi hệ thống; không fail-open | Timeout, retry budget, circuit breaker |
| JWT signature sai | **401** | JWKS, key rotation, alg/issuer |
| JWT `exp` quá hạn | **401** | Exp/nbf/clock skew |
| JWT signed hợp lệ nhưng `aud` khác API | **401** nếu validator aud được bật | Audience configuration |
| Token active nhưng không đúng tenant | Phải bị từ chối theo policy | Issuer/client/tenant mapping |

Một resource server có thể trả 401/403 nhưng response body không do controller quyết định. Hãy kiểm cả `WWW-Authenticate` và thông tin xác thực/authorization, không dựa một string error JSON cố định.

### 12.1. Resource Server khác OAuth2 Client

Các property `spring.security.oauth2.resourceserver.opaquetoken.*` cấu hình **API nhận Bearer token**. Chúng không đăng ký OAuth2 Login `/oauth2/authorization/...`, không tạo `OAuth2AuthorizedClient` để gọi downstream và không phát token. Muốn làm OAuth2 Client, cần dependency/manager/client registration riêng.

### 12.2. Không nên chấp nhận token theo vẻ bề ngoài

Đừng phân loại bằng:

- “Token có ba phần là JWT, không cần introspect”.
- “Token dài 64 ký tự chắc random nên hợp lệ”.
- “ID Token là JWT, dùng làm access token gọi API”.
- “Introspection active true của mọi tenant đủ để cho admin”.
- “JWT decode được Base64URL nghĩa là signature đúng”.

Resource server phải có cấu hình validation theo issuer/audience/resource/authority thực tế.

## 13. Kiểm thử chính xác với WebTestClient và IdP mock

### 13.1. WebTestClient kiểm authorization policy

Spring Security Test reactive cung cấp `mockOpaqueToken()` để tạo một `BearerTokenAuthentication` trong `SecurityContext` khi test:

~~~java
// Snippet trong test class đã có WebTestClient được cấu hình.
webTestClient.mutateWith(mockOpaqueToken()
        .authorities(new SimpleGrantedAuthority(
                "SCOPE_messages.read")))
        .get().uri("/api/messages")
        .exchange()
        .expectStatus().isOk();

webTestClient.mutateWith(mockOpaqueToken()
        .authorities(new SimpleGrantedAuthority(
                "SCOPE_profile")))
        .get().uri("/api/messages")
        .exchange()
        .expectStatus().isForbidden();
~~~

Đây là **test snippet**, cần import `SecurityMockServerConfigurers.mockOpaqueToken`, `SimpleGrantedAuthority`, WebFlux Test/Spring Security Test tương thích; không phải JUnit class đầy đủ.

**Giới hạn quan trọng:** `mockOpaqueToken()` **không gọi introspection endpoint**. Nó gắn Authentication giả vào request để kiểm tra **authorization policy**. Muốn kiểm integration của `SpringReactiveOpaqueTokenIntrospector`, phải có test gọi một mock HTTP introspection endpoint thật theo RFC 7662, rồi assert request/response/timeout/error mapping.

### 13.2. Test matrix nghiệp vụ và giao thức

| Case | Đầu vào | Kết quả mong đợi |
| --- | --- | --- |
| Public anonymous | GET `/public` không header | 200 |
| Protected không token | GET `/api/me` | 401 |
| Opaque token hợp lệ | Introspection `active=true` | Authentication thành công |
| Introspection `active=false` | Random/revoked/expired token | 401, không controller |
| Token active không scope | `scope="profile"`, URL đòi messages.read | 403 |
| Token active đúng scope | `scope="messages.read"` | 200 |
| Audience sai | `aud` không chứa API hiện tại | Phải bị từ chối nếu policy yêu cầu |
| IdP introspection HTTP 401 | Client secret sai | Hạ tầng config error, không bypass |
| IdP timeout hoặc HTTP 503 | Network/IdP outage | Fail closed; giám sát và không retry vô hạn |
| Introspection JSON sai schema | Thiếu `active` hoặc `active` sai type | Không coi token hợp lệ |
| Token là JWT nhưng dùng `opaqueToken()` | Introspection xác minh JWT | Phụ thuộc active result, không local verify |
| JWT signed đúng nhưng `aud` sai | JWT decoder có audience validation | 401 |
| JWT hết `exp` | JWT decoder kiểm thời gian | 401 |
| JWT revoke trước expiry | Chỉ local JWT validation | Có thể vẫn được chấp nhận nếu không có revoke check |
| JWT key rotated | JWKS cache refresh | Chấp nhận key mới theo policy |
| 429 introspection hoặc nhiều request cùng token | Rate/availability policy | Không fail-open, không request storm |
| Token không thuộc issuer được phép | Policy issuer/token metadata | Không cấp quyền |
| JSON business route public nhưng có invalid Bearer | Header invalid được gửi | Có thể bị auth filter từ chối dù permitAll |

### 13.3. Test hiệu năng và thu hồi

Thử theo quy trình:

1. Cấp access token hợp lệ, gọi API 200.
2. Revoke token tại IdP.
3. Gọi lại API ngay: opaque introspection **không cache** nên kỳ vọng 401 khi IdP báo active=false.
4. Bật cache introspection TTL ngắn: kiểm chính xác **khoảng stale window** trước khi API bắt đầu từ chối.
5. Với JWT local-only, revoke ở IdP nhưng giữ JWT chưa hết hạn: ghi nhận policy có thể tiếp tục accept; không diễn giải sai thành lỗi verify signature.
6. Kiểm throughput/P95 và IdP call rate ở peak traffic.
7. Tắt introspection endpoint trong môi trường thử nghiệm: xác minh API **fail closed**, không âm thầm chấp nhận token cũ vô hạn.
8. Kiểm secret rotation của introspection client: không gây outage dài, không rò credentials.

Đây là **kịch bản test**, không phải kết quả đo đã thực hiện.

## 14. Những lỗi phổ biến

### 14.1. Dùng Servlet API trong WebFlux

`OpaqueTokenIntrospector` và `SpringOpaqueTokenIntrospector` (không có Reactive) thuộc cách dùng đồng bộ; WebFlux nên sử dụng `ReactiveOpaqueTokenIntrospector`, `SpringReactiveOpaqueTokenIntrospector` và `ServerHttpSecurity`.

### 14.2. Copy JWT properties sang opaque config

`spring.security.oauth2.resourceserver.jwt.issuer-uri` không tự cấu hình online introspection. Đối với opaque, phải có `opaquetoken.introspection-uri` và introspection client authentication hợp lệ, hoặc một bean `ReactiveOpaqueTokenIntrospector` có contract rõ ràng.

### 14.3. Quên audience/resource restriction

`active=true` của token dành cho API khác không đủ để cho truy cập. Ràng buộc audience/client/issuer/tenant theo hợp đồng Authorization Server và không tin scope của tenant khác.

### 14.4. Gọi introspection endpoint qua HTTP

Bearer token và introspection client secret có thể bị lộ khi không có TLS. Dùng HTTPS và validate certificate chain, không tắt kiểm chứng TLS bằng trust-all.

### 14.5. Phát role admin dựa trên raw claim tự chọn

Một claim `roles=["admin"]` chỉ được map nếu Authorization Server thực sự quản trị claim đó và nó dành cho đúng API/tenant. Không nối `ROLE_` vào mọi string do token/client cung cấp.

### 14.6. Xử lý token không active bằng empty principal

Custom introspector không được trả `Mono.just(new DefaultOAuth2AuthenticatedPrincipal(...))` nếu token chưa được xác minh; không trả `Mono.empty()` để diễn giải “không có lỗi” thay vì invalid. Dùng error theo contract.

### 14.7. Cho rằng JWT được mã hóa

JWT/JWS phổ biến chỉ có chữ ký, payload Base64URL đọc được. Không đưa password/API secret/PII nhạy cảm không cần thiết vào JWT claim.

### 14.8. Chỉ decode JWT, không verify chữ ký và issuer

Một chuỗi JWT tự tạo vẫn có thể decode. Dùng `ReactiveJwtDecoder` và validators, tránh tự parse payload rồi tự cấp authority.

### 14.9. Caching introspection quá lâu

Cache positive bằng TTL đến `exp` có thể che việc revoke/disable account. Quyết định TTL theo SLA của revocation, không chỉ tối ưu throughput.

### 14.10. Mất kết nối IdP thì accept mọi token

Đây là fail-open nguy hiểm. Phải phân biệt token invalid và introspection unavailable, giữ policy fail closed, có incident handling/circuit breaker.

### 14.11. Tưởng OAuth2 Resource Server tự làm OAuth2 Login

Resource Server chỉ xác thực Bearer token tới API; không tự phát token, không redirect user tới IdP và không tự tạo OAuth2AuthorizedClient gọi downstream.

### 14.12. Không kiểm WWW-Authenticate khi 401/403

Có thể 401 do token sai/missing header, 403 do scope thiếu; Bearer challenge cung cấp thông tin giao thức. Không đổi tất cả thành “password sai”.

### 14.13. Chỉ test mockOpaqueToken, không test introspection network

`mockOpaqueToken()` bypass introspector; nó phù hợp policy, không chứng minh client credentials/endpoint/active parsing đang chạy. Phải có integration test với mock IdP.

### 14.14. Phát fake demo introspector lên Internet

Hardcoded token `opaque-admin-demo` sẽ là **lỗ hổng nghiêm trọng** nếu chạy production. Hạn chế profile demo tới máy học và loại bỏ bean fake khỏi artifact sản xuất khi có thể. Không coi `@Profile("demo")` là hàng rào đủ mạnh nếu operator vẫn có thể bật nhầm profile.

### 14.15. Dùng token trong query parameter

Bearer token trong URL dễ lọt vào history, access log, analytics và Referer; dùng `Authorization: Bearer ...` qua HTTPS.

### 14.16. Tắt CSRF theo tên “REST API”

Với API chỉ nhận Bearer header và không dùng credential tự động từ browser, CSRF model khác cookie session. Nhưng nếu ứng dụng còn form login, cookie auth, WebSocket hoặc SPA gửi cookie, phải đánh giá riêng trước khi tắt CSRF. Việc chọn opaque hay JWT **không quyết định CSRF**.

## 15. Checklist triển khai production

1. Xác định đúng **định dạng** token và **chiến lược xác minh**; không mặc định JWT luôn local hay opaque luôn random.
2. Dùng `ReactiveOpaqueTokenIntrospector`/`ServerHttpSecurity` với WebFlux, không copy Servlet API.
3. Spring Boot/Spring Security version tương thích, resource server starter đúng Boot 4.x.
4. Introspection endpoint có HTTPS/TLS được kiểm chứng, client credentials được bảo vệ và rotate.
5. Response introspection có `active=true` và đủ metadata để kiểm đúng resource server.
6. Có rule scope/authority cho từng URL; `active` không tự cấp toàn bộ quyền.
7. Kiểm issuer, audience, client, tenant theo hợp đồng token và resource server.
8. Không fail-open khi IdP outage, timeout hoặc response invalid.
9. Timeout, connection pooling, rate limiting, circuit breaker và observability được thiết kế phù hợp.
10. Nếu cache introspection, TTL tương thích `exp` và yêu cầu thu hồi; test stale window.
11. JWT local validation có trusted algorithms, keys, iss/exp/nbf/aud validators và key rotation.
12. Không log Bearer token, introspection secret hoặc claims nhạy cảm.
13. Không truyền token qua URL/query string.
14. Test 200, 401, 403, active false, wrong audience, expired, revoked, invalid introspection client, 503 và cache.
15. Test resource server sau proxy/TLS termination, giữ Bearer header đúng và không vô tình log ở gateway.
16. Không để profile demo hoặc hardcoded test token được kích hoạt ở production.
17. Với nhiều microservices, đánh giá throughput/availability của introspection so với JWT JWKS cache.
18. Chọn cơ chế revocation riêng nếu JWT local validation không đáp ứng yêu cầu nghiệp vụ.

## 16. Tự kiểm tra

**Câu 1.** Opaque token và Bearer token khác nhau thế nào?

**Đáp án:** Bearer là authentication scheme khi trình token trong HTTP header; opaque nói rằng resource server không tự suy nội dung/quyền từ token và thường cần introspection hoặc token store để xác minh.

**Câu 2.** JWT có phải luôn được Spring Security tự xác minh offline không?

**Đáp án:** Không. JWT có thể được xử lý qua `jwt()` và local signature validation, hoặc được gửi đến introspection endpoint qua `opaqueToken()` nếu cần trạng thái online.

**Câu 3.** Introspection trả `{"active":true}` đã đủ để gọi mọi API chưa?

**Đáp án:** Chưa. Cần kiểm token dành cho đúng resource server/audience và có scope/authority phù hợp endpoint.

**Câu 4.** Vì sao `GET /api/admin` bằng token reader demo nhận 403 mà không phải 401?

**Đáp án:** Token reader được fake introspector công nhận active, nhưng authorities không có `SCOPE_admin`. Authentication thành công, authorization thất bại.

**Câu 5.** Nếu JWT signature hợp lệ nhưng `aud` sai, có nên chấp nhận?

**Đáp án:** Không. Resource server cần audience validation, ngoài signature/issuer/time.

**Câu 6.** Tại sao JWT local validation có thể chấp nhận token vừa bị revoke?

**Đáp án:** Local verifier chỉ biết chữ ký/claims/keys; không tự hỏi Authorization Server về trạng thái thu hồi từng token. Cần online check/revocation mechanism hoặc token TTL ngắn.

**Câu 7.** Vì sao caching introspection làm thay đổi tính năng revocation?

**Đáp án:** Cache active=true có thể còn hiệu lực sau khi IdP đã revoke token, cho đến lúc TTL hết hoặc cache được invalidate.

**Câu 8.** Spring Security WebFlux nhận opaque token bằng interface nào?

**Đáp án:** `ReactiveOpaqueTokenIntrospector`, trả `Mono<OAuth2AuthenticatedPrincipal>`; implementation chuẩn `SpringReactiveOpaqueTokenIntrospector`.

**Câu 9.** `mockOpaqueToken()` kiểm chứng điều gì?

**Đáp án:** Kiểm HTTP authorization với Authentication giả; không gọi introspection endpoint, không xác minh client credentials hoặc token thật.

**Câu 10.** Nếu introspection endpoint timeout, có được tạm coi token active để giữ availability?

**Đáp án:** Không theo default an toàn. Cần fail closed, xử lý lỗi IdP, giám sát và thiết kế HA/caching theo giới hạn rủi ro đã được phê duyệt.

## 17. Tài liệu chính thức

- [Spring Security — Reactive OAuth2 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/opaque-token.html)
- [Spring Security — Reactive OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html)
- [Spring Security — OAuth2 WebFlux overview](https://docs.spring.io/spring-security/reference/reactive/oauth2/)
- [Javadoc — ReactiveOpaqueTokenIntrospector](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/introspection/ReactiveOpaqueTokenIntrospector.html)
- [Javadoc — SpringReactiveOpaqueTokenIntrospector](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/introspection/SpringReactiveOpaqueTokenIntrospector.html)
- [Javadoc — ServerHttpSecurity OAuth2 OpaqueTokenSpec](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.OAuth2ResourceServerSpec.OpaqueTokenSpec.html)
- [Javadoc — BadOpaqueTokenException](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/introspection/BadOpaqueTokenException.html)
- [Javadoc — DefaultOAuth2AuthenticatedPrincipal](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/core/DefaultOAuth2AuthenticatedPrincipal.html)
- [Javadoc — BearerTokenAuthentication](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/BearerTokenAuthentication.html)
- [Spring Security — Testing OAuth2 in Reactive WebTestClient](https://docs.spring.io/spring-security/reference/reactive/test/web/oauth2.html)
- [Spring Boot — OAuth2 Resource Server auto-configuration](https://docs.spring.io/spring-boot/reference/security/oauth2.html)
- [RFC 7662 — OAuth2 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [RFC 6750 — OAuth2 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725)
- [RFC 9068 — JWT Profile for OAuth2 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
