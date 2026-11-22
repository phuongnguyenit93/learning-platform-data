# Token introspection và ranh giới tin cậy với Authorization Server

## 1. Bài học giải quyết vấn đề gì?

Trong một ứng dụng Spring WebFlux đóng vai trò **OAuth 2.0 Resource Server**, client gửi access token để gọi API:

```http
GET /api/reports HTTP/1.1
Host: reports.example.invalid
Authorization: Bearer <opaque-access-token>
```

Khi token là **opaque**, Resource Server (RS) không thể tự đọc chuỗi token và xác nhận tình trạng của nó. RS thường phải gửi token tới **Introspection Endpoint** của **Authorization Server (AS)** đáng tin cậy theo RFC 7662. AS trả thông tin token đang active hay không, những scopes đã được cấp, chủ thể, client, audience và các metadata khác mà AS cho phép RS xem.

**Bài học:** Token introspection và ranh giới tin cậy với Authorization Server.  
**Chương cha:** Resource Server Opaque.  
**Module:** Spring Security - reactive.

Hai câu hỏi cần tách biệt:

1. **Authentication/token validity:** token có active, chưa hết hạn/thu hồi và thực sự do AS tin cậy xác minh hay không?
2. **Authorization/resource suitability:** dù token đang active, nó có được cấp cho **reports-api**, đúng issuer/client/tenant và có đủ quyền để truy cập endpoint cụ thể hay không?

Nguy hiểm nhất là suy luận **“AS trả active=true nên request có quyền làm bất cứ điều gì”**. Authorization Server cung cấp dữ liệu token đã xác minh, nhưng Resource Server vẫn chịu trách nhiệm đặt ranh giới sử dụng token cho **chính tài nguyên của mình**.

### Mục tiêu học tập

Sau bài, bạn có thể:

1. Mô tả token introspection theo RFC 7662 bằng HTTPS POST, body form, credential của RS và JSON response.
2. Phân biệt opaque token với JWT và biết JWT vẫn có thể được introspect khi cần kiểm tra revocation.
3. Phân biệt HTTP 200/`active:false` từ AS với HTTP 401/403/5xx của **introspection endpoint**, và với HTTP 401/403 mà **Resource Server API** trả về client.
4. Giải thích các roles của `ReactiveOpaqueTokenIntrospector`, `SpringReactiveOpaqueTokenIntrospector`, `OpaqueTokenReactiveAuthenticationManager`, `BearerTokenAuthentication` và `OAuth2AuthenticatedPrincipal`.
5. Cấu hình Spring Security 6.5 WebFlux bằng `ServerHttpSecurity.oauth2ResourceServer(...).opaqueToken(...)` và Spring Boot 3.x.
6. Thêm local validation `iss`, `aud`, `client_id` khi các claims đó thuộc hợp đồng dữ liệu với AS.
7. Hiểu scope mapping thành `SCOPE_*`, sự khác nhau giữa 401 thiếu/không hợp lệ token và 403 đã authenticated nhưng thiếu quyền.
8. Thiết kế AS/RS trust boundary với TLS, credential management, audience restriction, claim minimization, network egress policy, no-open-redirect và chống SSRF.
9. Xử lý AS unavailable, timeout, concurrency, revocation/caching trade-off theo hướng **fail closed**.
10. Viết ứng dụng Java 17+ Spring Boot WebFlux có introspector wrapper, REST endpoints bảo vệ và 17 trường hợp kiểm thử mẫu; biết vì sao test fake không thay được HTTP introspection integration test thật.
11. Chẩn đoán multi-issuer/tenant confusion, token substitution, stale introspection response và lộ token qua logs.

**Phiên bản minh họa:** Java 17+, Spring Boot 3.5.x, Spring Security 6.5.x, Reactor/WebFlux. Tên miền `example.invalid` và token/credentials ví dụ là giả. Các ví dụ chạy được khi có Gradle wrapper từ Initializr; gọi AS thật đòi thông tin endpoint và credential hợp lệ, không có trong bài.

## 2. Opaque access token khác JWT ra sao?

### 2.1. Opaque token

Opaque access token có thể chỉ là một chuỗi ngẫu nhiên:

```text
tok_9b02_opaque_value_for_illustration
```

Resource Server không nên suy luận người dùng, scope hoặc audience từ hình dạng của chuỗi. Nó có thể là một handle đến dữ liệu lưu trong AS hoặc định dạng riêng mà RS không biết. **Không** tự Base64 decode token rồi tin metadata do chính client có thể kiểm soát.

RS nhận request Bearer rồi hỏi AS: token này có được AS biết đến, còn active và có thể dùng ở tài nguyên được hỏi không?

### 2.2. JWT không đồng nghĩa “không introspect”

JWT thường mang các claims và chữ ký; RS có thể kiểm tra JWT cục bộ bằng JWKS, issuer, audience, thời hạn và các validator phù hợp. Tuy nhiên token có định dạng JWT vẫn có thể đưa vào một **opaque-token introspection flow** khi hệ thống đòi hỏi trạng thái revocation trực tuyến. Spring Security `opaqueToken` không buộc chuỗi token phải không thể parse được: nó mô tả **chiến lược xác minh bằng introspection**.

| Khía cạnh | JWT validation tại RS | Opaque token introspection |
|---|---|---|
| Xác minh chính | Signed claims/JWKS và validators | Phản hồi từ AS qua endpoint tin cậy |
| Revocation gần thời gian thực | Cần giải pháp bổ sung | AS có thể trả inactive sau revoke |
| Phụ thuộc mạng mỗi request | Thường không, ngoài key refresh | Có thể cần AS cho mỗi request |
| Claims/roles | Từ JWT đã verify | Từ introspection response đã xác minh |
| Nguy cơ chính | Sai key/alg/iss/aud/expiry handling | AS outage, latency, lộ token tại network/logs, stale cache |
| Endpoint authorization | Vẫn thuộc RS | Vẫn thuộc RS |

**Token introspection** không phải `/userinfo` của OIDC, không phải token exchange và không tự revoke token:
- Introspection: xác minh trạng thái và metadata token.
- UserInfo: claims người dùng theo OIDC; không thay resource-server token validation.
- Token exchange: nhận một token khác dành cho downstream resource/delegation.
- Revocation: yêu cầu AS thu hồi token.
- Resource Server: cuối cùng quyết định một subject có được đọc một bản ghi hay không.

## 3. RFC 7662: request, response và ngữ nghĩa

### 3.1. Toàn bộ luồng

```text
[OAuth2 Client]
      |
      | GET /api/reports
      | Authorization: Bearer T
      v
[Resource Server: Spring WebFlux]
      |
      | 1. Nhận và trích xuất Bearer token T
      | 2. HTTPS POST /oauth2/introspect
      |    Authorization: Basic <credentials của RS>
      |    Content-Type: application/x-www-form-urlencoded
      |    token=T
      v
[Authorization Server đã được tin cậy]
      |
      | 3. Xác thực RS introspection client
      | 4. Kiểm tra token và những metadata RS được phép xem
      | 5. Trả JSON active true/false, scope, iss, aud, sub...
      v
[Resource Server]
      |
      | 6. active=true? issuer/audience/client_id đúng?
      | 7. Map scope -> authorities SCOPE_*
      | 8. Route/tenant/resource authorization
      v
[Controller/Service nếu tất cả điều kiện pass]
```

AS và RS có hai loại identity khác nhau:
- **Client dùng Bearer token gọi API** có OAuth2 access token T.
- **RS dùng client credential gọi introspection** được AS cấp quyền hỏi trạng thái token.

Credential introspection **không phải** access token T, và có thể khác client secret dùng khi OAuth2 Client xin token tại token endpoint.

### 3.2. HTTP POST form theo RFC 7662

```http
POST /oauth2/introspect HTTP/1.1
Host: auth.example.invalid
Authorization: Basic <base64-of-introspection-client-id-and-secret>
Content-Type: application/x-www-form-urlencoded
Accept: application/json

token=<opaque-token>&token_type_hint=access_token
```

- `token` là tham số body bắt buộc.
- `token_type_hint` chỉ là **gợi ý tùy chọn** để AS xử lý, không thay xác minh token.
- `application/x-www-form-urlencoded` là content type request chuẩn.
- Introspection request cần **TLS** và RS authentication theo AS contract.
- Ví dụ Basic auth chỉ hợp lệ khi AS hỗ trợ; có thể dùng mTLS/client assertion hoặc phương thức khác theo chính sách.
- **Không đặt token trong URL query** vì proxy logs, history, traces và referrer có thể lưu URL.
- Base64 trong Basic không phải encryption: toàn bộ kết nối phải được bảo vệ bằng TLS, certificate và hostname validation.

### 3.3. Kết quả active=true

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "active": true,
  "scope": "report.read report.export",
  "client_id": "reports-frontend",
  "token_type": "Bearer",
  "sub": "user-42",
  "aud": ["reports-api"],
  "iss": "https://issuer.example.invalid/",
  "iat": 1767996400,
  "exp": 1768000000
}
```

Các giá trị `iat`/`exp` là ví dụ định dạng Unix timestamp; **không có nghĩa token còn hạn hôm nay**. AS phải tính active theo trạng thái hiện tại thay vì dùng response tĩnh.

| Claim | Ý nghĩa | Điểm cần nhớ |
|---|---|---|
| `active` | Boolean RS có thể tin token active hay không | Bắt buộc theo RFC 7662 |
| `scope` | Các capabilities, thường chuỗi space-separated | Spring map thành `SCOPE_*`, không thay audience |
| `client_id` | OAuth client được cấp token | Khác introspection client credential của RS |
| `sub` | Subject của token | Không nhất thiết là email, không duy nhất trên nhiều issuers |
| `aud` | Resource Server audience mà token hướng đến | Phải match policy của API khi được yêu cầu |
| `iss` | AS issuer identifier | Đối chiếu issuer trusted theo agreed contract |
| `exp` | Thời điểm token hết hạn | AS thường dùng để tính active; RS có thể thêm kiểm tra riêng |
| `iat` | Thời điểm phát hành | Không tự cấp quyền |
| `token_type` | Loại token, ví dụ Bearer | Không đồng nghĩa được phép mọi endpoint |

**RFC 7662 chỉ bắt buộc trường `active`**, các trường còn lại phụ thuộc AS. Nếu sản phẩm cần `iss`, `aud` và `client_id` làm policy, hãy yêu cầu AS cung cấp đúng **claims schema**, hoặc xây binding tin cậy tương đương. Không âm thầm cho phép token thiếu audience.

### 3.4. Kết quả active=false

```http
HTTP/1.1 200 OK
Content-Type: application/json

{"active":false}
```

Đây là introspection HTTP **thành công về giao thức**, nhưng token **không được phép dùng**. Một số lý do có thể là expired, revoked, không tồn tại, hoặc RS này không được AS cho phép xem trạng thái token. Để giảm tiết lộ thông tin, RFC khuyến nghị không kèm lý do/claims khác cho inactive token.

**HTTP 200 không tương đương token active.** Spring Security phải từ chối token khi `active:false`; API thường trả 401 cho caller.

### 3.5. AS 401/403/429/5xx khác API 401/403

| Tình huống | Bên trả | Ý nghĩa |
|---|---|---|
| HTTP 200 + active=false | AS | Query introspection hợp lệ, token không active |
| HTTP 200 + active=true | AS | Token có thể tiếp tục bị RS kiểm tra claims và permissions |
| HTTP 401 | AS | Credential RS dùng introspection sai/hết hạn hoặc AS không chấp nhận auth |
| HTTP 403 | AS, tùy provider | RS introspection client thiếu quyền hỏi |
| HTTP 429/5xx/timeout | AS/network | Chưa xác minh được token vì lỗi phụ thuộc |
| HTTP 401 | RS API | Caller thiếu hoặc có Bearer token không được chấp nhận |
| HTTP 403 | RS API | Caller authenticated nhưng không có quyền cho endpoint |

Một lỗi operational **AS 401** không tự biến thành “user nhập sai password”; phải kiểm tra secret/client authentication giữa RS và AS. Với AS outage, **không** trả 2xx hoặc thực hiện protected side effect. Có thể trả lỗi generic 5xx/503 theo chính sách hoặc security exception handling, nhưng không fail-open.

## 4. Ranh giới tin cậy giữa AS và RS

### 4.1. Ai quyết định điều gì?

**AS có thẩm quyền về:**
- Token do AS có phát hành không?
- Token còn trong time window và chưa revoked không?
- Token active cho RS đã xác thực đang hỏi?
- Token được gắn với subject, OAuth client, scopes, audience nào?
- RS này có quyền gọi introspection hay không?

**RS có trách nhiệm về:**
- Introspection response thật sự đến từ AS được cấu hình đáng tin?
- TLS/credentials/authentication của AS có đúng?
- Issuer và audience có đúng API hiện tại không?
- OAuth client hoặc tenant có nằm trong allowlist theo business không?
- Principal có authority cần cho route không?
- Subject có được xem bản ghi/tenant cụ thể không?

Một `active:true` ở AS không tự thay các kiểm tra cuối cùng. Đặc biệt với AS phục vụ nhiều APIs, token được cấp cho `payments-api` không nên tự được chấp nhận bởi `reports-api` chỉ vì token đang tồn tại và có scope giống tên.

### 4.2. Token substitution và confused deputy

Ví dụ:
- Token A: `active=true`, `scope=report.read`, `aud=payments-api`.
- Token B: `active=true`, `scope=report.read`, `aud=reports-api`.

RS reports-api phải **từ chối token A** dù scope cùng tên, nếu không token cấp cho hệ thống khác có thể bị sử dụng tại reports. Đây là một dạng token substitution/resource confusion.

Ràng buộc khuyến nghị:

```text
Verified by AS:
  active == true

Enforced by RS:
  iss == expectedTrustedIssuer
  aud contains "reports-api"
  client_id belongs to allowedOAuthClients (nếu business yêu cầu)
  authorities contains SCOPE_report.read
  subject/tenant/resource ACL grants this operation
```

Nếu AS trả thiếu các claim cần thiết, hãy **fail closed** và sửa hợp đồng AS–RS. Chỉ dùng dữ liệu có xuất xứ đáng tin; không lấy role/issuer từ `X-User` hay query params do caller tự gửi.

### 4.3. Không gửi token đến AS do user chỉ định

Thiết kế nguy hiểm:

```text
GET /api/resource?introspection_url=https://attacker.example.invalid/check
Authorization: Bearer T
```

Nếu RS chọn introspection endpoint từ input caller, nó có thể gửi **toàn bộ access token T** và credential RS cho attacker. Đây là exfiltration và có thể là SSRF.

Chỉ chọn AS từ trusted configuration/tenant routing đã xác minh. Với multi-issuer, **opaque token không có issuer tự chứng minh**, nên không thể đọc một prefix/header không tin cậy rồi coi đó là sự thật. Cũng không nên gửi thử cùng token tới **mọi AS** để dò xem AS nào trả active.

### 4.4. TLS và chính sách network

- Introspection URI bắt buộc HTTPS theo trust policy.
- Kiểm tra certificate chain và hostname. Không dùng `trustAll` hoặc tắt SSL verification.
- Credential của RS lưu trong secret manager/env và rotate; không commit.
- AS xác thực RS, phân quyền introspection client theo principle of least privilege.
- Tránh redirect tự động từ AS introspection endpoint tới host khác, đặc biệt khi token/Basic header có thể bị chuyển tiếp.
- Egress allowlist hostname/IP/service identities của AS; DNS rebinding/SSRF và proxy routing cần được đánh giá.
- Không mở token endpoint/AS introspection credentials để mọi ứng dụng nội bộ tùy ý dùng.
- Đặt timeouts, connection pool, concurrency limit và quota tại đường RS→AS.
- Với mTLS, client certificate riêng và identity binding đúng AS contract.
- Bảo vệ access token trong request body, không log raw request/response chứa claims.

### 4.5. Client ID trong response không phải client ID của RS introspection

Trong response `client_id=reports-frontend` là OAuth client được **AS cấp access token**. Credential RS gọi AS để **introspect** có thể là `reports-resource-server`. Hai thứ là hai OAuth identities khác nhau:

```text
OAuth client (reports-frontend)
  -> nhận token từ AS
  -> gọi reports-api với Bearer token

Resource server (reports-api)
  -> dùng introspection-client credential riêng
  -> gọi AS hỏi token active hay không
```

Không nhầm claim client_id với credential RS đang sử dụng và không tự cấp permission bằng cách kiểm tra credential RS thay cho subject/tenant.

## 5. Tích hợp Spring Security WebFlux 6.5

### 5.1. Các class chính

| Class/Interface | Vai trò |
|---|---|
| `ServerHttpSecurity` | DSL reactive inbound HTTP security |
| `SecurityWebFilterChain` | Chuỗi WebFilters thực thi authentication/authorization |
| `ReactiveOpaqueTokenIntrospector` | `Mono<OAuth2AuthenticatedPrincipal> introspect(String token)` |
| `SpringReactiveOpaqueTokenIntrospector` | HTTP client chuẩn gọi token introspection endpoint |
| `OpaqueTokenReactiveAuthenticationManager` | Xác thực opaque bearer token và tạo Authentication |
| `BearerTokenAuthentication` | Authentication sau introspection thành công |
| `OAuth2AuthenticatedPrincipal` | Attributes và authorities do introspector đã xác minh trả |
| `DefaultOAuth2AuthenticatedPrincipal` | Principal thông dụng, tiện cho tests |
| `BadOpaqueTokenException` | Lỗi token không hợp lệ |
| `ReactiveSecurityContextHolder` | Reactor Context mang SecurityContext trong WebFlux |
| `@AuthenticationPrincipal` | Đưa principal đã xác thực vào controller |
| `WebTestClient` | Kiểm thử request/response qua WebFlux |

**Không nhầm Servlet classes:**
- WebFlux: `ReactiveOpaqueTokenIntrospector`, `SpringReactiveOpaqueTokenIntrospector`, `ServerHttpSecurity`.
- Servlet: `OpaqueTokenIntrospector`, `SpringOpaqueTokenIntrospector`, `HttpSecurity`.

WebFlux controller không nên `.block()` để gọi introspection trên event loop. Spring Security reactive filter composition đã đảm nhiệm publisher lifecycle.

### 5.2. Minimal Spring Boot configuration

Từ Spring Boot 3.x, properties:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://auth.example.invalid/oauth2/introspect
          client-id: resource-server-client
          client-secret: secret-from-secret-manager
```

Đây là mẫu shape cấu hình **không có credentials thật**. Trong sản phẩm, inject environment/secret manager; không commit `client-secret` vào Git. Boot tạo `ReactiveOpaqueTokenIntrospector` khi có property và bean cần thiết; `SpringReactiveOpaqueTokenIntrospector` là implementation Spring Security 6.5 mặc định.

Ví dụ cấu hình Java snippet:

```java
@Bean
SecurityWebFilterChain chain(ServerHttpSecurity http) {
    return http
        .authorizeExchange(exchanges -> exchanges
            .pathMatchers("/api/reports/**")
                .hasAuthority("SCOPE_report.read")
            .anyExchange().authenticated())
        .oauth2ResourceServer(oauth2 -> oauth2
            .opaqueToken(Customizer.withDefaults()))
        .build();
}
```

Đây là **snippet**, cần imports/bean context và properties. Chọn `opaqueToken` tức xác thực qua introspection endpoint, không tự xác minh JWT bằng JWK. Nếu API cần local claim policy, hãy cung cấp wrapper `ReactiveOpaqueTokenIntrospector` thay vì tự sửa client parsing code.

### 5.3. Builder SpringReactiveOpaqueTokenIntrospector

Spring Security 6.5 có builder:

```java
ReactiveOpaqueTokenIntrospector delegate =
    SpringReactiveOpaqueTokenIntrospector
        .withIntrospectionUri(introspectionUri)
        .clientId(introspectionClientId)
        .clientSecret(introspectionClientSecret)
        .build();
```

**Lưu ý version:** Constructor nhận ba String đã deprecated trong 6.5; ưu tiên builder. Class reactive nằm trong `org.springframework.security.oauth2.server.resource.introspection`.

Có thể cung cấp bean custom hoặc `.opaqueToken(opaque -> opaque.introspector(myIntrospector))` để override config mặc định. Nếu nhiều candidate cùng type, cần chọn bean rõ; tránh vừa dùng properties auto-config, vừa tạo custom bean không biết cái nào đang thực thi.

### 5.4. Mapping scope sang authorities

Nếu AS trả:

```json
{"active":true,"scope":"report.read report.export"}
```

Spring Security thường map thành:

```text
SCOPE_report.read
SCOPE_report.export
```

DSL:

```java
.pathMatchers("/api/reports/**")
    .hasAuthority("SCOPE_report.read")
```

Đây là snippet của authorization rules. `SCOPE_*` chứng minh loại quyền có trong token đã introspect, **không** tự khẳng định issuer/audience/client ID/tenant đúng. Các rule quyền theo bản ghi vẫn phải được business service kiểm tra.

### 5.5. Principal và Reactor Context

Sau authentication, controller có thể nhận:

```java
@GetMapping("/api/whoami")
Mono<String> whoami(
        @AuthenticationPrincipal OAuth2AuthenticatedPrincipal principal) {
    return Mono.just(principal.getName());
}
```

Đây là snippet; method cần nằm trong `@RestController` và imports. Đối với reactive code khác, dùng `ReactiveSecurityContextHolder.getContext()` thay cho giả định ThreadLocal theo thread. Đừng trả token raw hoặc toàn bộ claims nhạy cảm vào JSON.

## 6. Thời gian, revocation, caching và availability

### 6.1. Introspection là dependency trong critical path

Một WebFlux Resource Server có thể phải introspect từng Bearer request, tức thêm network RTT và tải cho AS. Khi AS chậm hoặc outage:
- Latency API tăng.
- Connection pool có thể bão hòa.
- Timeout/concurrency/circuit breaker cần có deadline rõ.
- Token không được xác minh, **không** cho business handler chạy.
- Monitoring cần phân biệt AS 401 credential failure, active=false, 429/5xx và timeout.

Dùng `WebClient` nonblocking, connection/response timeout; không gọi blocking HTTP client trên event loop. Retry giới hạn với backoff/jitter cho lỗi tạm thời nếu policy cho phép, không retry vô hạn trên inactive/token invalid/AS credential 401.

### 6.2. Fail-closed, không “tạm cho qua”

Sai:

```java
// Ví dụ ANTI-PATTERN, không triển khai:
return delegate.introspect(token)
    .onErrorResume(error ->
        Mono.just(previouslyAuthenticatedPrincipal));
```

Khi AS bị lỗi, việc lấy một principal cũ hoặc gán anonymous thành authenticated có thể bypass revocation, audience và tenant isolation. Đúng hơn là propagate error, khiến protected request **không** được xử lý; nếu muốn một HTTP response generic 503 cho AS unavailable, xử lý ở error mapping và observability mà không gán Authentication thành công.

### 6.3. Cache introspection có đánh đổi

RFC 7662 cho phép cache kết quả để giảm tải, **đổi lại tính mới của trạng thái**. Nếu AS revoke một token vào 10:00 nhưng RS cache active=true tới 10:15, token vẫn có thể được chấp nhận trong cửa sổ đó.

Thiết kế cache cần:
- TTL ngắn, không vượt token expiry và chính sách revocation.
- Namespace theo trusted issuer, audience, tenant và chính sách nếu kết quả phụ thuộc context.
- Cache key an toàn không lộ raw token trong logs/traces; hash/HMAC có thiết kế phù hợp.
- Kiểm soát negative caching active=false và không leak token existence.
- Không cache AS 401/5xx/timeout như “permanently invalid token” hoặc success.
- Có invalidation/push nếu yêu cầu revoke gần thời gian thực.
- Không dùng global `Mono.cache()` sai cách khiến principal user A được dùng cho B.
- Luồng kiểm thử expired/revoked và multi-node cache consistency.

**Introspection trực tuyến** có thể giúp revocation nhanh hơn, nhưng nếu bạn cache vô thời hạn thì ưu điểm đó mất. Chọn TTL theo business risk, không theo một con số cố định không có căn cứ.

### 6.4. Các đường rò rỉ riêng tư

Introspection request mang **raw token** tới AS. Không log:
- `Authorization: Bearer ...` incoming.
- Basic credential của RS→AS.
- Form body `token=...`.
- Access/refresh tokens và client secrets.
- Toàn bộ introspection JSON có PII.
- Raw query params và exception message kèm token.

AS nên chỉ trả những claims RS cần để cấp quyền; inactive response thường chỉ có `active:false`. Metrics dùng status/error category, normalized AS host, latency, correlation ID không chứa secrets. Cần rate-limit token guessing/abuse và cấp cho introspection client quyền truy vấn vừa đủ.

### 6.5. Multi-tenant/multi-AS

Nếu RS phục vụ nhiều tenants với AS khác nhau, không được:
- Chọn introspection URL từ query/`Host` tùy ý.
- Gửi cùng token thử tuần tự tới tất cả AS.
- Tin một `iss` do client tự gửi trước introspection.
- Dùng một global cache token-to-principal không tách issuer/tenant.
- Tự gộp subjects từ hai issuers chỉ bằng `sub` hoặc email.

Cần trusted tenant resolution, endpoint AS cố định theo tenant, credential riêng, expected audience/issuer riêng, network egress policy, scoped cache và audit. `iss+sub` thường là key ổn định hơn `sub` đơn lẻ khi identity đến từ nhiều issuers.

## 7. Demo Spring Boot 3.5 WebFlux: introspection và local trust policy

App có:
- `GET /health` public.
- `GET /api/reports` cần `SCOPE_report.read`, active token với `iss`, `aud` và `client_id` đúng.
- `GET /api/admin` cần `SCOPE_report.admin`.
- `BoundaryIntrospector` gọi delegate đã introspect rồi check expected claims.
- `@Profile("test")` trong JUnit thay network AS bằng fake delegate, nhưng vẫn chạy WebFlux security filter.

**Giới hạn cố ý:** demo hostname `auth.example.invalid` không có AS thật, nên protected calls trong runtime thông thường không thành công. `/health` chạy offline. Tests chỉ cần fake fixture và không gửi token ra mạng.

### 7.1. Khởi tạo project

Tạo Gradle Groovy project từ [Spring Initializr](https://start.spring.io/) với Java 17+, Spring Boot 3.5.x:
- Spring Reactive Web.
- Spring Security.
- OAuth2 Resource Server.
- Spring Boot Starter Test, Spring Security Test, Reactor Test.

Phần `dependencies` của `build.gradle`:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}
```

Đây **chỉ là dependencies block**, không phải build.gradle đầy đủ. Giữ plugins, repositories, Java toolchain và Gradle wrapper từ Initializr. Tránh thêm `spring-boot-starter-web` nếu inbound cần WebFlux, vì Boot 3.x ưu tiên MVC khi cả hai starter cùng có.

Bố cục:

```text
src/main/java/demo/opaque/
  OpaqueBoundaryApplication.java
  BoundaryIntrospector.java
  IntrospectionConfig.java
  SecurityConfig.java
  ReportsController.java
src/test/java/demo/opaque/
  OpaqueBoundaryWebTests.java
  BoundaryIntrospectorTests.java
```

### 7.2. OpaqueBoundaryApplication.java

```java
package demo.opaque;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OpaqueBoundaryApplication {
    public static void main(String[] args) {
        SpringApplication.run(OpaqueBoundaryApplication.class, args);
    }
}
```

### 7.3. BoundaryIntrospector.java: kiểm tra iss/aud/client

```java
package demo.opaque;

import java.time.Duration;
import java.util.Collection;
import java.util.Objects;

import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector;
import reactor.core.publisher.Mono;

public final class BoundaryIntrospector
        implements ReactiveOpaqueTokenIntrospector {

    public static final String EXPECTED_ISSUER =
        "https://issuer.example.invalid/";
    public static final String EXPECTED_AUDIENCE =
        "reports-api";
    public static final String EXPECTED_CLIENT =
        "reports-frontend";

    private final ReactiveOpaqueTokenIntrospector delegate;
    private final Duration timeout;

    public BoundaryIntrospector(
            ReactiveOpaqueTokenIntrospector delegate,
            Duration timeout) {
        this.delegate = Objects.requireNonNull(delegate);
        this.timeout = Objects.requireNonNull(timeout);
        if (timeout.isNegative() || timeout.isZero()) {
            throw new IllegalArgumentException(
                "Introspection timeout must be positive");
        }
    }

    @Override
    public Mono<OAuth2AuthenticatedPrincipal> introspect(
            String token) {
        return delegate.introspect(token)
            .timeout(timeout)
            .switchIfEmpty(Mono.error(
                new BadOpaqueTokenException(
                    "No valid introspection result")))
            .flatMap(principal -> {
                if (!EXPECTED_ISSUER.equals(
                        principal.getAttribute("iss"))
                        || !EXPECTED_CLIENT.equals(
                            principal.getAttribute("client_id"))
                        || !audienceAllowed(
                            principal.getAttribute("aud"))) {
                    return Mono.error(
                        new BadOpaqueTokenException(
                            "Token is not intended for this API"));
                }
                return Mono.just(principal);
            });
    }

    private boolean audienceAllowed(Object raw) {
        if (raw instanceof String single) {
            return EXPECTED_AUDIENCE.equals(single);
        }
        if (raw instanceof Collection<?> multiple) {
            return multiple.stream()
                .anyMatch(EXPECTED_AUDIENCE::equals);
        }
        return false;
    }
}
```

Giải thích:

1. `delegate` phải chịu trách nhiệm xác minh `active` với AS. Wrapper **không** tự đánh dấu token active.
2. `timeout` đặt deadline cho Mono; khi deadline vượt, không có principal trả thành công. Production còn cần connect/response timeout, bulkhead và circuit-breaker tại network layer.
3. `iss` và `client_id` so chính xác với contract; `client_id` ở đây là OAuth client nhận token, **không phải** credential introspection của RS.
4. `aud` chấp nhận một chuỗi audience hoặc danh sách theo provider schema; nếu thiếu/khác kiểu, mặc định từ chối.
5. Lỗi policy dùng `BadOpaqueTokenException` để security infrastructure không tạo Authentication thành công.
6. Không tự bổ sung authorities; scope mapping do trusted delegate tạo.
7. Những `EXPECTED_*` values được hardcode cho demo. Production dùng trusted config/allowlist và nhiều clients nếu business yêu cầu.
8. Với AS không trả aud/iss do claims là optional, **demo sẽ từ chối tất cả token**. Cần AS–RS thống nhất schema hoặc một binding đáng tin tương đương, không bỏ kiểm tra trong lúc debug.

### 7.4. IntrospectionConfig.java: delegate HTTP tới AS

```java
package demo.opaque;

import java.net.URI;
import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector;
import org.springframework.security.oauth2.server.resource.introspection.SpringReactiveOpaqueTokenIntrospector;

@Configuration
public class IntrospectionConfig {

    @Bean
    @Profile("!test")
    ReactiveOpaqueTokenIntrospector introspector() {

        String uri = System.getenv().getOrDefault(
            "INTROSPECTION_URI",
            "https://auth.example.invalid/oauth2/introspect");
        String clientId = System.getenv().getOrDefault(
            "INTROSPECTION_CLIENT_ID",
            "demo-resource-server");
        String secret = System.getenv().getOrDefault(
            "INTROSPECTION_CLIENT_SECRET",
            "non-production-placeholder");

        URI endpoint = URI.create(uri);
        if (!"https".equalsIgnoreCase(endpoint.getScheme())
                || !"auth.example.invalid".equalsIgnoreCase(
                    endpoint.getHost())
                || endpoint.getRawUserInfo() != null
                || endpoint.getRawFragment() != null) {
            throw new IllegalArgumentException(
                "Untrusted introspection endpoint");
        }

        ReactiveOpaqueTokenIntrospector delegate =
            SpringReactiveOpaqueTokenIntrospector
                .withIntrospectionUri(uri)
                .clientId(clientId)
                .clientSecret(secret)
                .build();

        return new BoundaryIntrospector(
            delegate, Duration.ofSeconds(3));
    }
}
```

Code thực hành dùng environment variables nhưng có **demo defaults không có hiệu lực**. Khi triển khai thực, phải:
- Bắt buộc khai báo credentials thật từ secret manager, không giữ default secret.
- Thay hostname pin `auth.example.invalid` bằng allowlist AS đã được review.
- Cấu hình TLS certificate/hostname verification, egress ACL, redirect handling và connect/response timeout.
- Cấp credential riêng cho RS và rotate phù hợp.
- Đồng bộ expected issuer/aud/client trong `BoundaryIntrospector` với AS thực.

`@Profile("!test")` loại bean remote khi test chạy profile `test`; fixture test sẽ cung cấp một introspector fake đã được wrapper. Đừng dùng profile test ở production.

Spring Security 6.5 builder được dùng thay constructor 3 String đã deprecated. Không có `.block()` hoặc lời gọi HTTP thủ công trong controller; delegate xử lý reactive HTTP.

### 7.5. SecurityConfig.java: WebFlux Bearer auth và route scopes

```java
package demo.opaque;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    SecurityWebFilterChain chain(
            ServerHttpSecurity http,
            ReactiveOpaqueTokenIntrospector introspector) {

        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/health")
                    .permitAll()
                .pathMatchers(HttpMethod.GET, "/api/reports")
                    .hasAuthority("SCOPE_report.read")
                .pathMatchers(HttpMethod.GET, "/api/admin")
                    .hasAuthority("SCOPE_report.admin")
                .anyExchange().denyAll()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .opaqueToken(opaque ->
                    opaque.introspector(introspector)))
            .httpBasic(basic -> basic.disable())
            .formLogin(form -> form.disable())
            .build();
    }
}
```

Đây là inbound Resource Server, không phải OAuth2 Client làm browser login. `httpBasic` và `formLogin` bị tắt để bảo vệ API bằng Bearer. Demo chỉ dùng GET protected endpoints; nếu thêm POST/PUT/PATCH/DELETE và browser credential tự gửi, đánh giá CSRF theo threat model, **không** tắt CSRF bừa bãi.

`SCOPE_report.read`/`SCOPE_report.admin` là authorities; các bản ghi có tenant/ACL thực vẫn cần policy phía service/database. Không cho user chọn role qua request header hoặc query.

### 7.6. ReportsController.java

```java
package demo.opaque;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class ReportsController {

    public record ReportView(
            String subject, String resource, String summary) {
    }

    @GetMapping("/health")
    public Mono<String> health() {
        return Mono.just("ok");
    }

    @GetMapping("/api/reports")
    public Mono<ReportView> reports(
            @AuthenticationPrincipal
            OAuth2AuthenticatedPrincipal principal) {
        return Mono.just(new ReportView(
            principal.getName(),
            "reports-api",
            "Report data is protected"));
    }

    @GetMapping("/api/admin")
    public Mono<String> admin(
            @AuthenticationPrincipal
            OAuth2AuthenticatedPrincipal principal) {
        return Mono.just("admin access for " + principal.getName());
    }
}
```

Không đưa raw Bearer token, Basic credential, toàn bộ introspection claims hoặc PII không cần thiết ra response. `principal.getName()` phụ thuộc trusted principal trả về; không coi nó luôn là email.

### 7.7. Chạy demo

Từ root Gradle:

```bash
./gradlew bootRun
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Test health:

```bash
curl -i http://localhost:8080/health
```

Dự kiến HTTP 200, body `ok` (các headers/charset theo framework version). Request protected thiếu token:

```bash
curl -i http://localhost:8080/api/reports
```

Dự kiến HTTP 401. Với placeholder `auth.example.invalid`, **không có token thật** nào vượt introspection; đó là hành vi đúng, không phải bug của Spring. Muốn chạy thật cần AS và token đúng `active`, `iss`, `aud`, `client_id`, scope như contract.

## 8. WebTestClient integration tests dùng fake introspector offline

Các tests dưới đây **không tạo một AS giả qua HTTP**. Thay vào đó, `@ActiveProfiles("test")` bỏ bean remote và `@TestConfiguration` đăng ký một fake delegate với outcomes xác định, bọc bởi `BoundaryIntrospector` thật. Mục tiêu: test WebFlux security chain, local issuer/audience/client policy và endpoint scope decisions.

File `src/test/java/demo/opaque/OpaqueBoundaryWebTests.java`:

```java
package demo.opaque;

import java.time.Duration;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.core.publisher.Mono;

@SpringBootTest(webEnvironment =
    SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
@ActiveProfiles("test")
@Import(OpaqueBoundaryWebTests.FakeConfig.class)
class OpaqueBoundaryWebTests {

    @Autowired
    WebTestClient client;

    @TestConfiguration
    static class FakeConfig {

        @Bean
        ReactiveOpaqueTokenIntrospector introspector() {
            ReactiveOpaqueTokenIntrospector fake = token ->
                switch (token) {
                    case "valid-read" -> Mono.just(
                        principal(
                            BoundaryIntrospector.EXPECTED_ISSUER,
                            List.of("reports-api"),
                            BoundaryIntrospector.EXPECTED_CLIENT,
                            "report.read"));
                    case "valid-admin" -> Mono.just(
                        principal(
                            BoundaryIntrospector.EXPECTED_ISSUER,
                            List.of("reports-api"),
                            BoundaryIntrospector.EXPECTED_CLIENT,
                            "report.admin"));
                    case "no-scope" -> Mono.just(
                        principal(
                            BoundaryIntrospector.EXPECTED_ISSUER,
                            List.of("reports-api"),
                            BoundaryIntrospector.EXPECTED_CLIENT,
                            ""));
                    case "wrong-audience" -> Mono.just(
                        principal(
                            BoundaryIntrospector.EXPECTED_ISSUER,
                            List.of("payments-api"),
                            BoundaryIntrospector.EXPECTED_CLIENT,
                            "report.read"));
                    case "wrong-issuer" -> Mono.just(
                        principal(
                            "https://untrusted.example.invalid/",
                            List.of("reports-api"),
                            BoundaryIntrospector.EXPECTED_CLIENT,
                            "report.read"));
                    case "wrong-client" -> Mono.just(
                        principal(
                            BoundaryIntrospector.EXPECTED_ISSUER,
                            List.of("reports-api"),
                            "untrusted-client",
                            "report.read"));
                    case "no-audience" -> Mono.just(
                        principal(
                            BoundaryIntrospector.EXPECTED_ISSUER,
                            null,
                            BoundaryIntrospector.EXPECTED_CLIENT,
                            "report.read"));
                    default -> Mono.error(
                        new BadOpaqueTokenException(
                            "Inactive or unknown test token"));
                };

            return new BoundaryIntrospector(
                fake, Duration.ofSeconds(2));
        }

        private static OAuth2AuthenticatedPrincipal principal(
                String issuer, Object audience,
                String clientId, String scope) {
            var attrs = new java.util.HashMap<String, Object>();
            attrs.put("sub", "user-42");
            attrs.put("iss", issuer);
            if (audience != null) {
                attrs.put("aud", audience);
            }
            attrs.put("client_id", clientId);
            attrs.put("scope", scope);

            List<GrantedAuthority> authorities = scope.isBlank()
                ? List.of()
                : List.of(new SimpleGrantedAuthority(
                    "SCOPE_" + scope));

            return new DefaultOAuth2AuthenticatedPrincipal(
                "user-42", attrs, authorities);
        }
    }

    @Test
    void healthDoesNotRequireToken() {
        client.get().uri("/health")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("ok");
    }

    @Test
    void missingBearerIsUnauthorized() {
        client.get().uri("/api/reports")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void inactiveTokenIsUnauthorized() {
        client.get().uri("/api/reports")
            .headers(h -> h.setBearerAuth("inactive"))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void validReadTokenWorks() {
        client.get().uri("/api/reports")
            .headers(h -> h.setBearerAuth("valid-read"))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.subject").isEqualTo("user-42")
            .jsonPath("$.resource").isEqualTo("reports-api");
    }

    @Test
    void readTokenCannotUseAdminEndpoint() {
        client.get().uri("/api/admin")
            .headers(h -> h.setBearerAuth("valid-read"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void adminScopeCanUseAdminEndpoint() {
        client.get().uri("/api/admin")
            .headers(h -> h.setBearerAuth("valid-admin"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class)
            .isEqualTo("admin access for user-42");
    }

    @Test
    void wrongAudienceIsUnauthorizedEvenIfActive() {
        client.get().uri("/api/reports")
            .headers(h -> h.setBearerAuth("wrong-audience"))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void wrongIssuerIsUnauthorizedEvenIfActive() {
        client.get().uri("/api/reports")
            .headers(h -> h.setBearerAuth("wrong-issuer"))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void wrongClientIsUnauthorizedEvenIfActive() {
        client.get().uri("/api/reports")
            .headers(h -> h.setBearerAuth("wrong-client"))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void missingAudienceFailsClosed() {
        client.get().uri("/api/reports")
            .headers(h -> h.setBearerAuth("no-audience"))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void missingScopeYieldsForbidden() {
        client.get().uri("/api/reports")
            .headers(h -> h.setBearerAuth("no-scope"))
            .exchange()
            .expectStatus().isForbidden();
    }
}
```

**11 integration test methods**. Điểm học tập:
- Missing/inactive token: API 401.
- Token với issuer/audience/client đúng và scope thích hợp: 200.
- Token active nhưng sai issuer/aud/client hoặc thiếu aud: local wrapper từ chối trước business.
- Token đã authenticated nhưng thiếu `SCOPE_report.read`: 403.
- Không bắt fake token liên hệ AS thật; `@Profile("!test")` loại remote bean khỏi test.

**Quan trọng:** Fake introspector tự tạo `DefaultOAuth2AuthenticatedPrincipal` và authorities để mô phỏng result đã verified. Nó **không** chứng minh HTTP `active:false` đã được AS parser xử lý, không chứng minh Basic credentials/TLS và không phải một IdP hợp lệ. Không copy fake bean vào runtime production.

## 9. Unit tests kiểm tra BoundaryIntrospector fail-closed

File `src/test/java/demo/opaque/BoundaryIntrospectorTests.java`:

```java
package demo.opaque;

import java.time.Duration;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection.OAuth2IntrospectionException;
import org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertSame;

class BoundaryIntrospectorTests {

    private OAuth2AuthenticatedPrincipal principal(
            String issuer, Object audience, String client) {
        var attrs = new java.util.HashMap<String, Object>();
        attrs.put("sub", "subject-7");
        attrs.put("iss", issuer);
        if (audience != null) {
            attrs.put("aud", audience);
        }
        attrs.put("client_id", client);

        List<GrantedAuthority> authorities = List.of(
            new SimpleGrantedAuthority("SCOPE_report.read"));
        return new DefaultOAuth2AuthenticatedPrincipal(
            "subject-7", attrs, authorities);
    }

    private BoundaryIntrospector guard(
            ReactiveOpaqueTokenIntrospector delegate) {
        return new BoundaryIntrospector(
            delegate, Duration.ofSeconds(2));
    }

    @Test
    void acceptsTrustedPrincipalWithoutPrivilegeChanges() {
        var p = principal(
            BoundaryIntrospector.EXPECTED_ISSUER,
            List.of("reports-api"),
            BoundaryIntrospector.EXPECTED_CLIENT);

        StepVerifier.create(guard(token -> Mono.just(p))
                .introspect("fake-token"))
            .assertNext(actual -> assertSame(p, actual))
            .verifyComplete();
    }

    @Test
    void rejectsWrongAudience() {
        var p = principal(
            BoundaryIntrospector.EXPECTED_ISSUER,
            List.of("payments-api"),
            BoundaryIntrospector.EXPECTED_CLIENT);

        StepVerifier.create(guard(token -> Mono.just(p))
                .introspect("fake-token"))
            .expectError(BadOpaqueTokenException.class)
            .verify();
    }

    @Test
    void rejectsWrongIssuer() {
        var p = principal(
            "https://other.example.invalid/",
            List.of("reports-api"),
            BoundaryIntrospector.EXPECTED_CLIENT);

        StepVerifier.create(guard(token -> Mono.just(p))
                .introspect("fake-token"))
            .expectError(BadOpaqueTokenException.class)
            .verify();
    }

    @Test
    void rejectsMissingAudience() {
        var p = principal(
            BoundaryIntrospector.EXPECTED_ISSUER,
            null,
            BoundaryIntrospector.EXPECTED_CLIENT);

        StepVerifier.create(guard(token -> Mono.just(p))
                .introspect("fake-token"))
            .expectError(BadOpaqueTokenException.class)
            .verify();
    }

    @Test
    void inactiveDelegateErrorIsNotConvertedToSuccess() {
        ReactiveOpaqueTokenIntrospector delegate = token ->
            Mono.error(new BadOpaqueTokenException("inactive"));

        StepVerifier.create(guard(delegate)
                .introspect("fake-token"))
            .expectError(BadOpaqueTokenException.class)
            .verify();
    }

    @Test
    void unavailableAsErrorIsNotConvertedToSuccess() {
        ReactiveOpaqueTokenIntrospector delegate = token ->
            Mono.error(new OAuth2IntrospectionException(
                "AS unavailable"));

        StepVerifier.create(guard(delegate)
                .introspect("fake-token"))
            .expectError(OAuth2IntrospectionException.class)
            .verify();
    }
}
```

**6 StepVerifier tests**. Chúng kiểm tra principal trusted không bị tự nâng quyền, sai/missing audience/issuer bị từ chối và lỗi delegate không được biến thành authenticated success.

Có thể bổ sung unit test `Mono.empty()` để xác nhận `switchIfEmpty` từ chối kết quả thiếu principal, và một virtual-time test cho deadline. Không dùng clock thực trong test timeout ngắn nếu CI tải cao gây flaky.

### 9.1. Chạy test

```bash
./gradlew test
```

Windows PowerShell:

```powershell
.\gradlew.bat test
```

Tổng **17 test methods** được định nghĩa (11 WebTestClient + 6 unit). **Đây là kiểm tra tĩnh về nội dung mã**, chưa có xác nhận Gradle đã chạy. Với version khác, cần kiểm tra API, status/exception thực tế; không “sửa lỗi” bằng bỏ audience check hoặc cho phép `active:false`.

## 10. HTTP integration tests cần bổ sung với AS giả

Fake principal test ở trên kiểm tra local policy, **chưa xác minh RFC 7662 qua HTTP**. Trong staging/CI, dùng mock HTTP AS đáng tin (WireMock hoặc MockWebServer) và cấu hình một introspector test instance trỏ đến địa chỉ test có kiểm soát. Không dùng token/secret production.

Những trường hợp quan trọng:

1. AS nhận **HTTP POST**, không GET.
2. Form body chứa đúng `token` (và `token_type_hint` nếu client gửi), không đưa token vào URL.
3. RS dùng đúng client authentication theo AS contract, ví dụ Basic/mTLS.
4. AS trả `200 {"active":false}` → RS không xác thực.
5. AS trả `200 {"active":true,...}` với expected issuer/aud/client/scopes → RS có thể đi tiếp.
6. AS trả active=true nhưng sai audience → wrapper từ chối.
7. AS 401 do introspection client credential lỗi → không cho phép, metric operational category khác inactive token.
8. AS 429, 500, timeout, malformed JSON, missing active → không cấp authenticated principal.
9. AS redirect sang host khác → không được rò Bearer token/Basic credential qua redirect.
10. Token vừa revoke sau khi request trước đã pass → kiểm tra cache TTL/invalidation.
11. TLS certificate/hostname validation và trusted DNS/network egress policy.
12. Kiểm tra AS không trả thông tin user/token vượt quyền RS introspection client.

Một request `curl` để hiểu protocol (chỉ dùng **test credentials** và môi trường bảo vệ secret):

```bash
curl --request POST \
  --url "https://auth.example.invalid/oauth2/introspect" \
  --user "$INTROSPECTION_CLIENT_ID:$INTROSPECTION_CLIENT_SECRET" \
  --data-urlencode "token=$TEST_ACCESS_TOKEN" \
  --data-urlencode "token_type_hint=access_token"
```

Đây là **minh họa**: domain `example.invalid` sẽ không hoạt động. Với token/credentials thật, tránh paste trong terminal history, ticket, CI log hoặc truyền vào URL. Có thể thực hiện HTTP tests qua mock server không có Internet và không cần AS thật.

## 11. Troubleshooting: trạng thái AS, RS và security chain

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| AS 200 nhưng API 401 | AS trả active=false hoặc local claims fail | Kiểm tra active và issuer/aud/client policy, không log raw token |
| AS trả 401, nhiều API cùng fail | Credential **RS→AS** sai/hết hạn | Kiểm tra introspection client auth/secret rotation |
| API 403 dù token active | Thiếu `SCOPE_*`/tenant ACL | Xem scope mapping và authorization rules |
| AS outage khiến API 5xx | Phụ thuộc network introspection | Timeout/bulkhead/monitoring, fail closed |
| API vẫn 200 khi AS outage | Cache quá cũ hoặc fallback allow | Gỡ fail-open, rà TTL/circuit breaker behavior |
| Missing audience nhưng token active | AS không trả optional aud claim | Thỏa thuận claims schema hoặc binding khác, không auto-allow |
| Token JWT được introspect thành công | OpaqueToken mode là chiến lược validation | Có thể đúng nếu cần revocation |
| Host AS đúng nhưng TLS bị disable | Trust config không an toàn | Bật hostname/certificate verification |
| RS gửi token đến AS do user chọn | SSRF/token exfiltration | Trusted endpoint allowlist, không arbitrary URL |
| Multi-tenant nhận token của tenant khác | Routing/cache/issuer/audience sai | Trusted tenant resolution và namespace policy |
| `.block()` trong ReactiveOpaqueTokenIntrospector | Blocking event loop | Dùng Reactor/WebClient nonblocking |
| API /health 200 nhưng /api/reports fail | Health public, AS chưa hoạt động | Separate readiness/AS metrics |
| Scope được tự map thành role ADMIN | Custom converter tin arbitrary claim | Chỉ map trusted claims được validate |
| Secret trong application.yml commit Git | Credentials lộ | Secret manager/env và rotation |
| Test fake pass nhưng AS trả JSON sai | Chưa test HTTP protocol/delegate | Mock AS HTTP tests và contract checks |
| Caching khiến revoke không hiệu lực ngay | TTL quá dài | Rút TTL/invalidation và test |
| AS Basic credential trong logs | Logger/interceptor ghi headers | Redaction ở app, proxy, APM |
| RS bị quá tải khi AS chậm | Không có deadline/concurrency limit | Timeouts, bulkhead, quotas, backpressure |
| Token active nhưng client_id sai | Token cấp cho app khác | Ràng buộc client allowlist theo contract |
| Subject từ nhiều issuers bị nhầm | Chỉ dùng `sub` hoặc email | Ràng buộc issuer + subject và tenant |

### 11.1. Quy trình điều tra

1. Xác nhận Spring **WebFlux inbound**, đúng class `ReactiveOpaqueTokenIntrospector`, không dùng Servlet counterpart.
2. Kiểm tra missing/malformed Bearer header trước, không log token.
3. Kiểm tra trusted introspection endpoint, TLS, credential và AS entitlement cho RS.
4. Quan sát AS HTTP status khác `active` nội dung; tránh tự log toàn bộ JSON.
5. Kiểm tra missing/invalid iss, aud, client_id theo hợp đồng dữ liệu.
6. Kiểm tra scope-to-authority và endpoint policy; phân biệt API 401 vs 403.
7. AS unavailable phải không tạo principal thành công hoặc chạy business side effect.
8. Nếu cache, kiểm tra TTL, issuer namespace, token revocation và invalidation.
9. Kiểm tra multi-node, proxy, egress DNS/IP, rate limiting và concurrency.
10. Đối chiếu HTTP integration test, không chỉ fake-principal tests.

## 12. Bài tập có đáp án

### Bài 1 — HTTP 200 có nghĩa token active?

AS trả HTTP 200 với `{"active":false}`. Cho user truy cập không?

**Đáp án:** Không. HTTP status thành công cho introspection request, nhưng body khẳng định token inactive. RS từ chối authentication; API thường 401.

### Bài 2 — AS trả 401 thì lỗi của ai?

AS introspection endpoint từ chối Basic credentials.

**Đáp án:** Đó là credential RS dùng để hỏi AS, không tự đồng nghĩa end user nhập sai password. Sửa introspection client permissions/secret/mTLS thay vì cho token qua.

### Bài 3 — active=true nhưng audience payments-api

RS reports-api nhận token active có `aud=payments-api` và scope `report.read`.

**Đáp án:** Từ chối vì audience không hướng tới reports-api. Scope không thay ràng buộc tài nguyên; tránh token substitution.

### Bài 4 — JWT có phải luôn dùng local decoder?

**Đáp án:** Không. Token JWT có thể introspect nếu cần trạng thái revocation trực tuyến hoặc AS contract yêu cầu. “Opaque” trong DSL nói về phương pháp introspection, không ép token không có định dạng JWT.

### Bài 5 — Phân biệt RS credential và OAuth client_id

**Đáp án:** Credential RS→AS cấp quyền hỏi introspection; claim `client_id` trong token metadata xác định OAuth client được cấp access token. Hai identities khác nhau, có quyền và rotation khác.

### Bài 6 — Nếu AS outage có nên tạm tin token đã từng pass?

**Đáp án:** Không theo chính sách fail-closed của demo. Cached active state có revocation window; khi không có kết quả hợp lệ và chưa có cache policy được chấp thuận, không cấp quyền mới.

### Bài 7 — Vì sao POST body thay GET query?

**Đáp án:** POST form là protocol RFC 7662, tránh đặt token trong URL có thể rò qua logs/history. Vẫn phải dùng TLS và bảo vệ body/Authorization trong logging.

### Bài 8 — Vì sao không tự map email thành admin?

**Đáp án:** Email/username/role chưa được xác minh theo policy không thể tự tạo quyền. Chỉ map trusted claims, issuer/tenant đúng và xét business authorization.

### Bài 9 — Cache active quá lâu sẽ ra sao?

**Đáp án:** Token bị revoke có thể vẫn được chấp nhận đến TTL hết, làm chậm hiệu lực revoke. TTL phải phù hợp expiry/rủi ro; có thể cần invalidation.

### Bài 10 — Missing issuer/audience thì làm gì?

**Đáp án:** Nếu hợp đồng RS yêu cầu các claims, fail closed và sửa schema hoặc cách xác minh. Không tự cho phép “audience bất kỳ” chỉ vì AS trả active=true.

### Bài 11 — Multi-AS có nên thử token ở cả hai endpoints?

**Đáp án:** Không mặc định. Opaque token là secret, gửi tới AS không tin cậy có thể lộ. Route dựa trên trusted tenant context và định nghĩa AS riêng.

### Bài 12 — Test @TestConfiguration có chứng minh Basic/TLS không?

**Đáp án:** Không. Fake introspector trả principal trực tiếp, chỉ test WebFlux và local claims policy. Cần HTTP mock AS/real provider tests cho POST, TLS, credentials và active JSON parsing.

### Bài 13 — 401 và 403 khác thế nào?

**Đáp án:** API 401 khi chưa hoặc không được xác thực; 403 khi đã có principal nhưng không được phép endpoint. AS 401 lại có thể là introspection client credential của RS bị lỗi.

### Bài 14 — Health 200 nhưng API fail?

**Đáp án:** Public health chỉ chứng minh process/route hoạt động. Protected API còn phụ thuộc AS, token, audiences, scopes và policy; thiết kế readiness/AS monitoring riêng.

### Bài 15 — Token xuất hiện trong AS logs?

**Đáp án:** Dừng logging raw token, redact logs/traces, thu hồi/rotate khi cần, đánh giá tác động và giới hạn quyền/TTL. Không paste token vào ticket hoặc chat.

### Bài 16 — Có nên dùng cùng một introspection client secret cho mọi RS?

**Đáp án:** Không nên nếu AS hỗ trợ tách credential. Cấp quyền riêng cho từng RS, dễ least privilege, rotate/revoke và audit. Không để một credential rò ảnh hưởng mọi service.

## 13. Checklist triển khai production

- [ ] Định nghĩa trusted AS introspection URI và tenant routing từ server config.
- [ ] HTTPS/TLS certificate + hostname verification luôn bật.
- [ ] RS introspection credential riêng, lưu secret manager, có rotation.
- [ ] RFC 7662 POST form với token trong body, không trong URL query.
- [ ] AS authenticates RS và chỉ trả claims cần thiết; inactive không leak lý do.
- [ ] `ReactiveOpaqueTokenIntrospector` xác minh active, không tự lấy claims từ caller.
- [ ] Check `iss`/`aud`/`client_id` nếu thuộc contract, missing claims fail closed.
- [ ] Scope-to-authority mapping chính xác và route/tenant/row ACL vẫn hoạt động.
- [ ] Không nhầm HTTP status AS 401 với API 401, hoặc active:true với grant quyền.
- [ ] Client không dùng email/username chưa verify để cấp admin.
- [ ] Timeouts và concurrency limits rõ; không block Reactor event loop.
- [ ] AS outage/429/5xx/timeout không tạo authenticated principal.
- [ ] Caching có TTL/invalidation/issuer namespace theo revocation policy.
- [ ] Multi-AS không dò token ở endpoints tùy ý.
- [ ] Egress allowlist, DNS/IP restrictions và chống SSRF/redirect.
- [ ] Logs/APM/traces/correlation không lộ token, Basic credential và PII.
- [ ] API có rate limit, abuse detection, HTTPS và generic error handling.
- [ ] WebTestClient tests bao gồm inactive, wrong issuer/audience/client, missing scopes.
- [ ] HTTP integration tests xác minh AS POST, active true/false, 401/5xx và TLS.
- [ ] Có runbook xử lý lộ token/client secret và AS outage.

## 14. Tóm tắt cuối

```text
Client -> Authorization: Bearer T -> Resource Server WebFlux
   |
   v
ReactiveOpaqueTokenIntrospector
   |
   +-- HTTPS POST T tới trusted AS
   |   xác thực bằng RS introspection client credential
   |
   +-- AS trả active true/false + claims
   |
   +-- active=false -> deny
   +-- timeout/AS error -> fail closed
   +-- active=true ->
          check trusted issuer
          check audience reports-api
          check allowed client_id
          map scope -> SCOPE_*
          route + resource/tenant authorization
                   |
                   +-- pass -> business handler
                   +-- fail authn -> 401
                   +-- thiếu quyền -> 403

TRUST BOUNDARY:
  AS là nguồn metadata/token state có thẩm quyền
  RS kiểm soát policy cho chính resource
  TLS + credentials + claim checks + authorization
  caching/timeout/network logs không được mở quyền
```

**Thông điệp quan trọng:** Introspection cho biết token có được Authorization Server tin cậy công nhận là **active** hay không, nhưng Resource Server mới quyết định token ấy có **được dùng tại tài nguyên và thao tác cụ thể** hay không. Thiết kế tốt kiểm tra audience/issuer/client và scope, bảo vệ RS→AS bằng TLS/credential, và khi không xác minh được token thì không cấp quyền.

## 15. Nguồn tham khảo

- [Spring Security 6.5 — Reactive OAuth2 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/resource-server/opaque-token.html)
- [Spring Security — Reactive Bearer Tokens](https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/resource-server/bearer-tokens.html)
- [Spring Security — ReactiveOpaqueTokenIntrospector API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/server/resource/introspection/ReactiveOpaqueTokenIntrospector.html)
- [Spring Security — SpringReactiveOpaqueTokenIntrospector API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/server/resource/introspection/SpringReactiveOpaqueTokenIntrospector.html)
- [Spring Security — OpaqueTokenReactiveAuthenticationManager API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/server/resource/authentication/OpaqueTokenReactiveAuthenticationManager.html)
- [Spring Security — BadOpaqueTokenException API](https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/oauth2/server/resource/introspection/BadOpaqueTokenException.html)
- [RFC 7662 — OAuth2 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [RFC 6750 — OAuth2 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 8707 — OAuth2 Resource Indicators](https://www.rfc-editor.org/rfc/rfc8707)
- [RFC 9700 — OAuth2 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700)
- [OWASP — OAuth2 Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/OAuth2_Cheat_Sheet.html)
- [OWASP — REST Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html)
