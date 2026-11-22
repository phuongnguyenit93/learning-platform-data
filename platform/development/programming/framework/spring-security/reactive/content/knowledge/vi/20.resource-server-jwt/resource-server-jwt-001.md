# Cơ chế Bearer token và luồng xác thực JWT trong WebFlux

## 1. Bài toán: API Reactive nhận Bearer token như thế nào?

Một ứng dụng Spring WebFlux cung cấp API `GET /api/catalog` và `POST /api/orders`. Client đã đăng nhập với một Authorization Server và sở hữu **access token** được cấp cho API này. Client gửi:

~~~http
GET /api/catalog HTTP/1.1
Host: api.example.test
Authorization: Bearer <access-token>
Accept: application/json
~~~

Spring Security Reactive cần giải quyết **hai câu hỏi độc lập**:

1. **Authentication:** Bearer token có tồn tại, hợp lệ, chưa hết hạn, đúng issuer, chữ ký và audience không? Nếu đáp ứng, ai hoặc client nào đang được nhận diện?
2. **Authorization:** Authentication đó có quyền cụ thể như `SCOPE_catalog.read` hoặc `SCOPE_orders.write` để thực hiện request không?

Nếu token thiếu/sai, thường trả **401 Unauthorized** cùng `WWW-Authenticate: Bearer`. Nếu token hợp lệ nhưng thiếu quyền, thường trả **403 Forbidden**. Các lỗi về payload/đơn hàng/tồn kho xảy ra sau security checks là lỗi nghiệp vụ riêng.

Trong Spring Security Reactive, framework cung cấp một dây chuyền để:
- Trích Bearer credential từ HTTP request.
- Đưa token đến một `ReactiveAuthenticationManager`.
- Giải mã và **xác minh** JWT bằng `ReactiveJwtDecoder`.
- Chuyển JWT đã xác minh thành `JwtAuthenticationToken`.
- Cung cấp authentication trong reactive security context.
- Thực thi quy tắc `authorizeExchange` hoặc method/object authorization trước khi cho controller xử lý.

**Điểm quan trọng:** Resource Server chỉ **xác minh access token**, không phải nơi cấp token. JWT là **một định dạng token có chữ ký**, không phải mật khẩu được mã hóa hay bằng chứng token luôn an toàn trong mọi hoàn cảnh.

### Bạn sẽ học

- Hiểu Bearer Authentication theo RFC 6750, ý nghĩa của Bearer và replay risk.
- Nêu tên các class Reactive chính xác: `ServerBearerTokenAuthenticationConverter`, `JwtReactiveAuthenticationManager`, `ReactiveJwtDecoder`, `JwtAuthenticationToken`.
- Phân tích JWT header/payload/signature, issuer/audience/expiry/not-before/scopes.
- Cấu hình Spring Boot 3.5 + Spring Security WebFlux với `issuer-uri`, `jwk-set-uri`, `audiences` và một security chain default-deny.
- Hiểu 401/403, challenge header, CSRF và stateless API trade-offs.
- Viết Java 17+ ứng dụng WebFlux, test chuỗi HTTP Bearer thật với decoder mock, test authorization riêng bằng `mockJwt()`.
- Nhận biết test nào **không** chứng minh chữ ký/issuer/audience thật và cần IdP/JWKS integration test nào.
- Debug các lỗi token, key rotation, CORS, logging, multi-tenant, clock skew.

Bài thuộc nhóm **Resource Server JWT** của module Spring Security - reactive. Các hostname/token trong ví dụ là dữ liệu mô phỏng, không phải credential hay endpoint triển khai sẵn.

## 2. Bearer token là gì?

“Bearer” có nghĩa **ai đang giữ token hợp lệ có thể trình token đó để truy cập tài nguyên**, trong giới hạn quyền và thời hạn token. Resource server thường không yêu cầu một chữ ký riêng của người trình token ở mỗi request như một proof-of-possession scheme.

Chuẩn phổ biến:

~~~http
Authorization: Bearer eyJhbGciOiJSUzI1NiIs...
~~~

Theo RFC 6750:
- `Authorization` là HTTP request header tiêu chuẩn.
- `Bearer` là authentication scheme.
- Phần sau là chuỗi access token nhận từ authorization server.
- Resource server xác minh token và áp dụng authorization policy.

### 2.1. Hậu quả của cơ chế Bearer

Nếu attacker có được một Bearer access token còn hợp lệ, attacker có thể **replay** token để gọi API trong phạm vi được cấp, trừ khi hệ thống có kiểm soát bổ sung như token binding, proof-of-possession (DPoP/mTLS), thu hồi token hoặc chính sách endpoint.

Vì vậy:
- Bắt buộc TLS/HTTPS ở môi trường thật.
- Không gửi token trong URL query: URL có thể rơi vào logs, browser history, referrer, analytics, reverse proxy.
- Không log `Authorization`, raw JWT hay refresh token.
- Không trả token vào error response, exception text hoặc telemetry.
- Dùng access token sống ngắn; xét refresh-token rotation/revocation ở Authorization Server.
- Xem xét DPoP/mTLS-bound tokens khi threat model yêu cầu chống replay mạnh hơn.

**JWT signature chỉ bảo đảm tính toàn vẹn/xác thực nguồn phát theo khóa và trust policy, không làm token tự chống được việc bị đánh cắp.**

### 2.2. Bearer không nhất thiết là JWT

Có hai kiểu thường gặp:

| Access token | Đặc điểm | Resource server làm gì? |
| --- | --- | --- |
| JWT đã ký | Header/payload/JOSE signature, claims như iss/aud/exp/scope | Xác minh chữ ký, khóa, thuật toán, claims; thường không cần gọi IdP mỗi request |
| Opaque token | Chuỗi không thể giải mã hữu ích theo định dạng JWT tại API | Sử dụng token introspection hoặc một cơ chế đáng tin khác |

Spring Security hỗ trợ cả `oauth2ResourceServer(...jwt(...))` và `oauth2ResourceServer(...opaqueToken(...))`, nhưng bài này chỉ tập trung **Bearer JWT**.

Không chọn JWT mode rồi parse một opaque token tùy ý. Ngược lại, không ép JWT phải introspect mỗi request nếu kiến trúc đang dùng offline signature validation mà không có yêu cầu như vậy.

## 3. OAuth2 client, Authorization Server và Resource Server

Một kiến trúc điển hình:

~~~text
[Browser/Mobile/Service Client]
             |
             | Authorization Code + PKCE, Client Credentials,
             | hoặc grant phù hợp tùy client
             v
[Authorization Server / Identity Provider]
             |
             | Cấp access token cho audience/resource cụ thể
             v
[Client giữ access token một cách an toàn]
             |
             | HTTPS
             | Authorization: Bearer <access-token>
             v
[Spring WebFlux OAuth2 Resource Server]
             |
             | Decode + verify JWT, kiểm scopes/roles/ownership
             v
[Controller -> Service -> Data]
~~~

Vai trò:
- **Authorization Server:** xác thực client/user theo flow và phát access token.
- **Resource Server:** tin một hoặc vài issuer cụ thể, xác minh token do issuer phát, rồi bảo vệ API.
- **OAuth2 Client:** ứng dụng thực hiện flow ủy quyền để lấy access token.
- **Resource Owner:** chủ thể sở hữu hoặc có quyền cấp ủy quyền tài nguyên theo mô hình OAuth.

Một ứng dụng có thể đồng thời là OAuth2 Client và Resource Server, nhưng phải cấu hình rõ từng security chain/route. Chỉ thêm resource-server starter **không tạo endpoint phát JWT** hoặc đăng nhập OAuth2 Login.

### 3.1. Access token khác ID token

Trong OIDC Login:
- **ID token** có audience là OIDC client; được client dùng để xác nhận authentication result của end-user.
- **Access token** dành cho resource server/API; nó có scopes/permissions, audience/resource và thời hạn phù hợp.

Đừng dùng `OidcUser.getIdToken().getTokenValue()` làm Bearer token tới business API. Một JWT có issuer/signature đúng nhưng `aud` là web-client vẫn có thể **không phải token dành cho API**.

### 3.2. Refresh token không gửi tới Resource Server

Refresh token dùng với Authorization Server/token endpoint theo chính sách grant; nó không phải credential để gọi `/api/catalog`. Resource Server không tự phát refresh token chỉ vì access token hết hạn.

## 4. Luồng xác thực Bearer JWT bên trong WebFlux

Đây là pipeline khái niệm phù hợp với Spring Security Reactive 6.x:

~~~text
HTTP request
  Authorization: Bearer <jwt>
          |
          v
SecurityWebFilterChain / WebFilter
          |
          v
AuthenticationWebFilter dành cho Resource Server
          |
          v
ServerBearerTokenAuthenticationConverter
          |
          | Không có Bearer token?
          |   -> Mono.empty() (không có authentication attempt từ token)
          |
          | Có token/chuỗi sai cấu trúc?
          |   -> ứng viên BearerTokenAuthenticationToken
          |      hoặc lỗi trích xuất tùy tình huống
          v
ReactiveAuthenticationManager
  (thường JwtReactiveAuthenticationManager)
          |
          v
ReactiveJwtDecoder
  (thường NimbusReactiveJwtDecoder qua Boot/JWKS)
          |
          +-- Ký số/issuer/audience/time không hợp lệ
          |         -> Authentication failure -> thường 401
          |
          +-- JWT hợp lệ
                    |
                    v
JWT -> GrantedAuthority mapping
  scope/scp -> SCOPE_catalog.read, ...
                    |
                    v
JwtAuthenticationToken
  principal = Jwt
  authentication.name thường từ sub
                    |
                    v
Reactive SecurityContext / Reactor Context
                    |
                    v
AuthorizationWebFilter + authorizeExchange
                    |
          +---------+--------------+
          |                        |
     Thiếu authority          Có quyền route
          |                        |
          v                        v
         403                 DispatcherHandler
                                Controller
                                Service + object policy
~~~

**Đây là mô hình học tập, không phải trace một thứ tự tuyệt đối của mọi WebFilter.** Request có thể bị CORS, CSRF, matcher, gateway hoặc một security chain khác xử lý trước. Với anonymous request đến protected route, authorization thường kích hoạt Bearer authentication entry point -> 401.

### 4.1. ServerBearerTokenAuthenticationConverter

Package Reactive:

~~~java
org.springframework.security.oauth2.server.resource.web.server.authentication
    .ServerBearerTokenAuthenticationConverter
~~~

Nó triển khai `ServerAuthenticationConverter` và đọc Bearer token từ `ServerWebExchange`, mặc định ở `Authorization` header.

- Không có Bearer phù hợp: converter có thể trả `Mono.empty()`, đồng nghĩa không có authentication attempt dựa vào token.
- Có Bearer hợp lệ về cú pháp: tạo `BearerTokenAuthenticationToken` chứa chuỗi token **chưa được xác minh**.
- Header malformed/nhiều token/định dạng sai: có thể phát lỗi OAuth Bearer; status chính xác phụ thuộc loại lỗi.

**Không nhầm converter với JWT decoder.** Converter không nên phân tích JWT claims, quyết định quyền hay tin vào token value.

### 4.2. JwtReactiveAuthenticationManager

`JwtReactiveAuthenticationManager` triển khai `ReactiveAuthenticationManager`. Nó nhận Authentication mang Bearer token, nhờ `ReactiveJwtDecoder` xác minh JWT và biến kết quả thành Authentication đã được xác thực.

- Decode/validation thất bại: phát lỗi authentication, không tự tạo principal.
- Decode hợp lệ: chạy JWT-to-Authentication converter.
- Không cần controller tự gọi `decode` trong mọi request; Security Resource Server đã điều phối.

### 4.3. ReactiveJwtDecoder

Interface:

~~~java
org.springframework.security.oauth2.jwt.ReactiveJwtDecoder
~~~

Hợp đồng khái niệm:

~~~java
// Chữ ký minh họa, không phải file Java độc lập.
Mono<Jwt> decode(String token);
~~~

Nhiệm vụ **không chỉ Base64URL decode** mà còn kiểm chữ ký bằng khóa tin cậy, kiểm claims theo validators và phát lỗi nếu JWT không đạt policy. Implementation thông thường là `NimbusReactiveJwtDecoder`.

### 4.4. JwtAuthenticationToken

Một request JWT hợp lệ thường có:
- `Authentication` loại `JwtAuthenticationToken`.
- `Authentication.getPrincipal()` là `Jwt`.
- `Authentication.getName()` mặc định thường từ `sub`.
- `Authentication.getAuthorities()` được mapping từ `scope`/`scp` hoặc converter tùy biến.

Tại controller:

~~~java
@GetMapping("/api/whoami")
public Mono<Map<String, Object>> whoAmI(
        @AuthenticationPrincipal Jwt jwt) {
    return Mono.just(Map.of("subject", jwt.getSubject()));
}
~~~

Đây là snippet controller; nếu route không yêu cầu auth hoặc `sub` vắng thì cần hợp đồng phù hợp. **Không serialize toàn bộ Jwt hoặc raw token value** ra client để “debug”.

### 4.5. SecurityContext trong Reactor không phải ThreadLocal Servlet

Spring Security Reactive truyền authentication xuống pipeline qua **Reactor Context** và các WebFilter tương ứng. Không dùng `SecurityContextHolder.getContext()` với giả định một ThreadLocal luôn theo request khi chạy trên event loop; nếu cần, dùng `ReactiveSecurityContextHolder.getContext()` hoặc argument injection.

Không dùng `block()` hay `subscribe()` thủ công trong filter/controller để lấy Authentication, vì có thể chặn event loop hoặc cắt đứt subscription context.

## 5. JWT có ba phần nhưng không phải dữ liệu được mã hóa

Một JWT ký bằng JWS thường có dạng:

~~~text
BASE64URL(header).BASE64URL(payload).BASE64URL(signature)
~~~

Ví dụ header minh họa:

~~~json
{
  "alg": "RS256",
  "kid": "signing-key-2026-11",
  "typ": "at+jwt"
}
~~~

Payload minh họa:

~~~json
{
  "iss": "https://idp.example.test/realms/demo",
  "sub": "user-42",
  "aud": ["catalog-api"],
  "scope": "catalog.read orders.write",
  "iat": 1790000000,
  "nbf": 1790000000,
  "exp": 1790003600,
  "jti": "opaque-token-id"
}
~~~

Đây chỉ là **JSON minh họa**, không phải signed JWT có thể sử dụng. Header `typ=at+jwt` là ví dụ cho JWT access token profile; không phải provider nào cũng sử dụng cùng giá trị, và những quy tắc kiểm token type phụ thuộc hợp đồng token của issuer/resource server.

### 5.1. Header, claims và signature

- **Header:** thuật toán ký `alg`, mã định danh khóa `kid`, đôi khi loại token `typ`.
- **Payload:** claims; `iss`, `sub`, `aud`, `exp`, `nbf`, `iat`, `scope/scp` có semantics riêng.
- **Signature:** bảo vệ tính toàn vẹn và chứng minh token do bên giữ signing key hợp lệ phát theo trust policy.

Base64URL chỉ là **encoding**. Ai giữ JWT thường có thể decode header/payload; không đưa password, access secret hay dữ liệu quá nhạy cảm vào claims chỉ vì JWT có chữ ký. Khi cần bảo mật nội dung claim có thể cần token opaque, dữ liệu tối thiểu hoặc JWE theo thiết kế; chữ ký JWS không tự làm payload kín.

### 5.2. Không tin claims trước khi verify

Đừng làm:

~~~java
// SAI: parsing payload rồi tin "role" trước khi verify chữ ký.
String role = parseBase64Payload(untrustedJwt).get("role");
if ("ADMIN".equals(role)) {
    grantAdminAccess();
}
~~~

Đây là pseudocode minh họa lỗi. Attacker có thể sửa payload nếu server không xác minh chữ ký. Nếu multi-tenant cần đọc `iss` chưa được tin cậy để chọn decoder, chỉ dùng nó để **tra cứu allowlist cố định** rồi xác minh token đầy đủ bằng decoder tương ứng, không chấp nhận issuer/JWKS URL tự do từ token.

## 6. Những claims cần kiểm tra

| Claim | Ý nghĩa | Lưu ý bảo mật |
| --- | --- | --- |
| `iss` | Issuer/authorization server | Chỉ tin issuer đã cấu hình |
| `sub` | Subject, thường user/client ID | Không tự xem là email/role/tenant |
| `aud` | Audience/resource token dành đến | **Phải gồm API của bạn** theo hợp đồng |
| `exp` | Hết hạn | Không nhận JWT hết hạn, chỉ cho clock skew giới hạn |
| `nbf` | Not before | Không nhận token trước thời điểm có hiệu lực |
| `iat` | Issued at | Dùng theo policy thời gian/token age khi thích hợp |
| `jti` | Token identifier | Có thể hỗ trợ revoke/replay detection nếu có state |
| `scope` | Các scopes dạng chuỗi | Thường map thành `SCOPE_...` |
| `scp` | Danh sách scopes ở một số provider | Spring có hỗ trợ mapping dạng phù hợp |
| `client_id` / `azp` | Client/authorized party theo profile | Không đồng nghĩa quyền trên dữ liệu |
| `tenant` / `org` | Claim riêng của nhà cung cấp | Cần validation cùng issuer/audience/ownership |
| `typ` (header) | Token type hint/profile | Đánh giá nếu provider dùng access-token profile |

### 6.1. iss: trust boundary

Một API chỉ nên chấp nhận token do issuer được phép phát. Nếu API có nhiều tenants/providers, mỗi issuer phải có policy xác thực/khóa/audience rõ ràng. Không nhận `iss` bất kỳ rồi tự động tải `.well-known` từ URL do attacker chọn; đó là rủi ro SSRF/issuer confusion.

### 6.2. aud: dễ bị bỏ sót

ID token của web client có thể có `aud=web-ui`, còn access token dành cho API có `aud=catalog-api`. **Chữ ký và issuer đúng chưa đủ**; `aud` cũng cần phù hợp với resource server.

Trong Spring Boot 3.5, có thể cấu hình:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          audiences:
            - catalog-api
~~~

Kết hợp với issuer/JWKS config, Boot áp audience validation cho token. Nếu access token không chứa audience theo hợp đồng, không được tùy tiện tắt validation chỉ để request 200; làm việc với authorization server để cấp token dành cho đúng resource.

### 6.3. exp, nbf và clock skew

Spring Security dùng JWT timestamp validators, có một lượng clock skew mặc định trong cấu hình tiêu chuẩn để chấp nhận chênh lệch đồng hồ nhỏ. Không tăng clock skew lên hàng giờ để “sửa expired token”: như vậy kéo dài cửa sổ mà token đáng lẽ bị từ chối.

Đảm bảo NTP/time synchronization ở máy chủ; kiểm tra token đã hết hạn, nbf trong tương lai, issuer, timezone và thời điểm phát hành. Token chưa hết hạn nhưng bị revoke vẫn có thể được JWT validator chấp nhận nếu hệ thống **chỉ kiểm offline chữ ký/claims** mà không có cơ chế thu hồi bổ sung.

### 6.4. sub không tự là quyền

`sub` có thể là user ID hoặc machine client ID. `sub=user-42` không có nghĩa user này sở hữu mọi record. Controller/service vẫn phải kiểm tra ownership/tenant và permissions cho tài nguyên cụ thể. Không dùng email/name được token khai báo làm khóa định danh chính nếu provider không bảo đảm quy tắc ổn định.

## 7. Chữ ký JWT, JWKS, thuật toán và key rotation

Authorization Server ký JWT bằng private key phù hợp. Resource Server thường tải public keys qua **JWK Set URI**, dùng `kid`/algorithm được cho phép để chọn key và kiểm JWS signature.

~~~text
Authorization Server
    private signing key
       |
       v
Signed JWT (alg, kid, claims, signature)
       |
       v
Spring Resource Server
    trusted JWK Set URI
       |
       +--> public keys / permitted JWS algorithms
       +--> kiểm signature
       +--> issuer/audience/timestamps validators
       v
Authenticated Jwt
~~~

### 7.1. jwk-set-uri và issuer-uri

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.test/realms/demo
          jwk-set-uri: https://idp.example.test/realms/demo/protocol/openid-connect/certs
          audiences:
            - catalog-api
~~~

Đây là **cấu hình demo với endpoint không tồn tại**. Khi dùng thật, issuer/JWKS phải đến từ Authorization Server tin cậy. Cung cấp cả `issuer-uri` và `jwk-set-uri` giúp ứng dụng biết JWKS trực tiếp mà vẫn có thông tin issuer để validate; không cần phụ thuộc discovery để biết endpoint JWKS tại startup.

Nếu chỉ có `issuer-uri`, Spring Security có thể khám phá metadata/JWKS khi cần; với nhánh Spring Security 6.5 hiện đại, quá trình này có thể được trì hoãn đến request Bearer đầu tiên. Không suy đoán rằng app boot luôn gọi IdP ngay lập tức.

### 7.2. Algorithm allowlist và alg=none

Theo Spring Security 6.5 Reference, `NimbusReactiveJwtDecoder` mặc định chỉ trust/verify `RS256` trong trường hợp tiêu chuẩn, và có thể cấu hình các trusted algorithms khác theo yêu cầu provider. Không tự chấp nhận `alg=none` và không cho untrusted JWT header quyết định key/algorithm một cách tự do.

Một cấu hình nếu provider thật dùng RS512:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.test/realms/demo
          jwk-set-uri: https://idp.example.test/realms/demo/jwks
          audiences:
            - catalog-api
          jws-algorithms:
            - RS512
~~~

Chỉ đổi algorithm khi đã xác minh provider ký như vậy. Nếu provider đang dùng RS256, cấu hình ép RS512 sẽ làm token bị từ chối; đó là hành vi đúng.

### 7.3. Key rotation

Khi Authorization Server đổi signing key:
- JWKS có thể công bố đồng thời key cũ và key mới trong giai đoạn chuyển tiếp.
- JWT header `kid` giúp decoder chọn đúng public key.
- Resource Server có thể cache JWKS và cập nhật theo cơ chế thư viện.
- Token ký với key cũ có thể cần tiếp tục được xác minh cho đến khi hết hạn theo policy.
- Nếu JWKS thiếu key mới, token hợp lệ theo IdP có thể tạm thời bị từ chối.

Không copy/paste public key vào code rồi quên key rotation nếu hạ tầng dùng JWKS. Không vô hiệu signature validation để “bỏ qua” một lỗi JWKS: kiểm tra cache, key id, trusted endpoint, TLS và clock.

### 7.4. JWKS không đáng tin từ token input

JWT header có thể chứa `jku` hoặc `x5u` trong một số profile. Không cho phép token tự quyết định URL tải public key từ host bất kỳ. Khóa và issuer phải được ràng buộc vào trusted configuration/allowlist. Đây là điểm thường bị bỏ qua ở custom decoder.

## 8. SCOPE_* authority được tạo thế nào?

Spring Security Resource Server thường chuyển scope từ claim `scope` (chuỗi phân tách bởi space) hoặc `scp` thành GrantedAuthority có tiền tố `SCOPE_`.

Ví dụ token hợp lệ:

~~~json
{
  "sub": "reader-42",
  "aud": ["catalog-api"],
  "scope": "catalog.read orders.write"
}
~~~

Authorities có thể là:

~~~text
SCOPE_catalog.read
SCOPE_orders.write
~~~

Security rules:

~~~java
.authorizeExchange(ex -> ex
        .pathMatchers(HttpMethod.GET, "/api/catalog")
            .hasAuthority("SCOPE_catalog.read")
        .pathMatchers(HttpMethod.POST, "/api/orders")
            .hasAuthority("SCOPE_orders.write")
        .anyExchange().denyAll())
~~~

**Lưu ý:**
- `hasAuthority("SCOPE_catalog.read")` kiểm đúng chuỗi.
- `hasRole("ADMIN")` thông thường kiểm `ROLE_ADMIN`, **không đồng nghĩa** `SCOPE_admin`.
- Token có scope đúng không tự chứng minh quyền sở hữu object; cần domain access check.
- Nếu provider lưu scopes trong claim khác, cần custom JWT authorities converter có chủ đích.

### 8.1. Custom authorities converter trong Reactive

Spring Security 6.5 cung cấp `ReactiveJwtAuthenticationConverter` và `ReactiveJwtAuthenticationConverterAdapter`. Với `JwtAuthenticationConverter` dạng đồng bộ:

~~~java
// Snippet cấu hình; import đầy đủ ở project tương ứng.
JwtGrantedAuthoritiesConverter scopes = new JwtGrantedAuthoritiesConverter();
scopes.setAuthoritiesClaimName("permissions");
scopes.setAuthorityPrefix("PERM_");

JwtAuthenticationConverter converter = new JwtAuthenticationConverter();
converter.setJwtGrantedAuthoritiesConverter(scopes);

var reactiveConverter =
        new ReactiveJwtAuthenticationConverterAdapter(converter);

http.oauth2ResourceServer(oauth2 -> oauth2
        .jwt(jwt -> jwt.jwtAuthenticationConverter(reactiveConverter)));
~~~

Chỉ dùng khi provider thực sự cấp claim `permissions` với format đã biết và claim đó được **signed/verified**. Không lấy JSON request body, cookie user-controlled hay untrusted header để cấp GrantedAuthority.

### 8.2. Không cho issuer tự cấp quyền nội bộ không kiểm soát

Ngay cả token hợp lệ có `scope=orders.write` vẫn cần kiểm:
- Audience token đúng API.
- User/client có quyền trên tenant/tài nguyên cụ thể.
- Client loại machine-to-machine có được thao tác này không.
- Chính sách least privilege và revocation/entitlement tại tổ chức.

Không tự map mọi scope thành `ROLE_ADMIN`. Role/tenant mapping phải được review như một chính sách bảo mật của hệ thống.

## 9. Authentication vs Authorization: 401 và 403

| Tình huống | Lớp lỗi | HTTP thường gặp | Cách xử lý |
| --- | --- | --- | --- |
| GET protected không có Bearer | Chưa authentication | **401** | Cung cấp access token |
| Bearer sai chữ ký | Authentication thất bại | **401** | Lấy token hợp lệ, không disable verify |
| Bearer hết hạn | Authentication thất bại | **401** | Refresh/re-authorize ở OAuth client |
| Bearer issuer hoặc audience sai | Authentication thất bại | **401** | Sửa issuer/resource target, không bỏ validation |
| Header Bearer malformed hoặc nhiều credential | Syntax/protocol | **400 hoặc 401**, tùy lỗi handler | Sửa cách gửi header, kiểm RFC 6750 |
| JWT hợp lệ nhưng không có `catalog.read` | Authorization | **403** | Cấp scope/permission theo chính sách |
| JWT hợp lệ, scope đủ, nhưng object thuộc tenant khác | Domain authorization | **403** hoặc 404 có chủ đích | Bảo vệ object-level access |
| JWT hợp lệ, quyền đủ, payload order sai | Request/business | **400/409/422** tùy contract | Sửa request hoặc xử lý conflict |
| JWKS/IdP unreachable khi cần lấy key | Dependency/security infrastructure | Có thể là auth failure/5xx tùy giai đoạn | Kiểm tra network/cache, không hạ xác minh |

### 9.1. WWW-Authenticate: Bearer

Một response thiếu credentials theo RFC 6750 thường có:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
~~~

Một token invalid có thể dẫn đến:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
~~~

Một user đã xác thực nhưng thiếu scope có thể nhận:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope"
~~~

Đây là **các ví dụ giao thức**; header thực có thể chứa thêm realm, error_description hoặc thay đổi theo Spring Security config. Đừng test exact string không cần thiết hoặc tự làm mất `WWW-Authenticate` khi viết custom error handler.

### 9.2. Vì sao @RestControllerAdvice không bắt hết 401?

Bởi Resource Server WebFilter có thể từ chối request **trước DispatcherHandler/controller**. `@RestControllerAdvice` chủ yếu xử lý exception phát sinh trong handler/controller path, không phải entry point/failure handler của security filters.

Nếu cần body JSON cho lỗi JWT:
- Cấu hình `ServerAuthenticationEntryPoint`/failure handler/`ServerAccessDeniedHandler` phù hợp ở security layer.
- Giữ HTTP 401/403 và Bearer challenge.
- Không để response body tiết lộ token raw, signing key hoặc stack trace.
- Test cả thiếu token, invalid token, expired token và insufficient scope.

## 10. JWT Resource Server “stateless” có nghĩa gì?

Một API chỉ dùng Bearer token do client **chủ động** đưa vào `Authorization` thường không cần login session phía server. Mỗi request:
1. Client gửi token.
2. Resource Server xác minh token.
3. Tạo authentication trong request/reactive context.
4. Controller/service xử lý.
5. Request kết thúc, không cần lưu authentication vào WebSession.

Có thể cấu hình:

~~~java
.securityContextRepository(
        NoOpServerSecurityContextRepository.getInstance())
~~~

Nó nói Spring Security không lưu `SecurityContext` qua session trong chain đó. **Không** có nghĩa toàn bộ WebFlux không thể có WebSession nếu controller/filter khác gọi `getSession()`, và cũng không tự có nghĩa token không bị replay.

### 10.1. Khi nào tắt CSRF trong Bearer-only API?

Với một API thực sự chỉ nhận Bearer token đặt thủ công trong Authorization header, browser không tự động gửi loại credential này như cookie session/form login, nên rủi ro CSRF truyền thống có thể thấp hơn. Khi threat model xác nhận **không dùng ambient credentials**, nhiều Bearer-only API cấu hình:

~~~java
.csrf(ServerHttpSecurity.CsrfSpec::disable)
~~~

Điều này **không phải lời khuyên tắt CSRF mặc định cho mọi WebFlux app**. Nếu cùng app dùng cookie login, HTTP Basic được browser nhớ, OAuth2 Login session hoặc endpoint dựa trên ambient credentials, phải đánh giá CSRF riêng và có thể dùng **nhiều SecurityWebFilterChain** với matcher đúng route.

Trong demo bên dưới, chúng ta tắt CSRF vì **chỉ mô phỏng Bearer-only API**, không có form login/cookie authentication. Nếu thêm browser session authentication trong cùng chain, phải xem lại quyết định.

### 10.2. CORS không thay CSRF và không cấp quyền

Một frontend `http://localhost:5173` gọi API `http://localhost:8080` với Authorization header có thể cần CORS preflight. CORS chỉ điều khiển việc browser được phép giao tiếp cross-origin; nó không validate JWT hoặc cấp scope.

Đừng `permitAll OPTIONS/**` rồi nghĩ đã cấu hình CORS đầy đủ. Hãy dùng WebFlux CORS config/filter đúng, xem preflight được xử lý trước authentication, và test actual requests. Ngược lại, tắt CORS không chặn được `curl` hoặc một non-browser client.

## 11. Dự án runnable: Java 17 + Spring Boot WebFlux Resource Server JWT

Project minh họa:
- `GET /public/ping`: public.
- `GET /api/catalog`: cần `SCOPE_catalog.read`.
- `POST /api/orders`: cần `SCOPE_orders.write`.
- `GET /api/whoami`: authenticated JWT, trả **safe metadata** (không có raw token).
- `anyExchange().denyAll()`: deny mặc định.
- JWT issuer/JWKS/audience policy được cấu hình tường minh.
- Test HTTP Bearer thông qua **mock ReactiveJwtDecoder**, nghĩa là nó tập trung vào filter/authz flow và không cần IdP mạng.
- Test authorization riêng qua `mockJwt()`, được dùng khi không cần test JWT decoder.

Dùng **Java 17, Spring Boot 3.5.7, Spring Security Reactive 6.5.x** với Gradle. Version cụ thể là cấu hình tham chiếu cho bài học; production cần bản vá và release được tổ chức hỗ trợ. Địa chỉ IdP mẫu là **placeholder documentation**, không thể xác minh token thật cho đến khi thay bằng trusted issuer/JWKS hoạt động.

### 11.1. Cấu trúc

~~~text
reactive-jwt-resource-server/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/demo/
    │   │   ├── DemoApplication.java
    │   │   ├── SecurityConfig.java
    │   │   └── ApiController.java
    │   └── resources/
    │       └── application.yml
    └── test/java/demo/
        ├── BearerJwtWebFluxTest.java
        └── JwtAuthorizationMockTest.java
~~~

### 11.2. settings.gradle

~~~groovy
rootProject.name = 'reactive-jwt-resource-server'
~~~

### 11.3. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.7'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

`spring-boot-starter-oauth2-resource-server` kéo vào hỗ trợ Resource Server và JOSE/JWT theo dependency management. **Không cần** `spring-boot-starter-oauth2-client` cho một API chỉ nhận JWT từ client; OAuth2 Client starter dùng khi ứng dụng tự thực hiện flow ủy quyền/call downstream với authorized clients.

### 11.4. application.yml

`src/main/resources/application.yml`:

~~~yaml
spring:
  application:
    name: reactive-jwt-resource-server
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.test/realms/demo
          jwk-set-uri: https://idp.example.test/realms/demo/jwks
          audiences:
            - catalog-api
~~~

Điều này mô tả:
- `issuer-uri`: issuer mà decoder phải chấp nhận.
- `jwk-set-uri`: điểm lấy public signing keys; đặt tường minh để không cần metadata discovery.
- `audiences`: JWT access token phải có `aud` phù hợp `catalog-api`.

**Không có IdP ở hostname ví dụ.** App có thể khởi động cho local/mock tests, nhưng nhận JWT thật cần kết nối đến issuer/JWKS hợp lệ. Không “tạo nhanh” token `alg=none` rồi cho API nhận để tránh cấu hình IdP.

### 11.5. DemoApplication.java

`src/main/java/demo/DemoApplication.java`:

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

### 11.6. SecurityConfig.java

`src/main/java/demo/SecurityConfig.java`:

~~~java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.context.NoOpServerSecurityContextRepository;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    SecurityWebFilterChain securityFilterChain(ServerHttpSecurity http) {
        return http
                .securityContextRepository(
                        NoOpServerSecurityContextRepository.getInstance())
                // CHỈ demo Bearer-only: không dùng cookie/form/Basic login.
                .csrf(ServerHttpSecurity.CsrfSpec::disable)
                .httpBasic(ServerHttpSecurity.HttpBasicSpec::disable)
                .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
                .authorizeExchange(ex -> ex
                        .pathMatchers(HttpMethod.GET, "/public/ping")
                                .permitAll()
                        .pathMatchers(HttpMethod.GET, "/api/catalog")
                                .hasAuthority("SCOPE_catalog.read")
                        .pathMatchers(HttpMethod.POST, "/api/orders")
                                .hasAuthority("SCOPE_orders.write")
                        .pathMatchers(HttpMethod.GET, "/api/whoami")
                                .authenticated()
                        .anyExchange().denyAll())
                .oauth2ResourceServer(resourceServer -> resourceServer
                        .jwt(Customizer.withDefaults()))
                .build();
    }
}
~~~

**Phân tích:**
1. Không dùng session authentication: `NoOpServerSecurityContextRepository`.
2. CSRF được tắt **chỉ do điều kiện mô phỏng Bearer-only**; không áp dụng máy móc cho cookie/browser apps.
3. Tắt Basic/form login để phản hồi authentication là Bearer, không bị HTML redirect hoặc Basic challenge.
4. `/api/catalog` và `/api/orders` kiểm tra authorities được map từ scopes.
5. `/api/whoami` chỉ cần JWT đã xác minh, không dùng scope cụ thể.
6. `denyAll()` cho các request chưa khai báo, kể cả methods khác.
7. `oauth2ResourceServer(...jwt(...))` kích hoạt Reactive JWT decoder đã được Boot tạo theo `application.yml`.
8. Không khai báo custom decoder không cần thiết, tránh vô tình làm mất Boot issuer/audience validators.
9. Chưa có object-level authorization trong demo, nên production phải bổ sung tenant/ownership policy tại service.

### 11.7. ApiController.java

`src/main/java/demo/ApiController.java`:

~~~java
package demo;

import java.util.List;
import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class ApiController {

    public record CreateOrderRequest(String sku, int quantity) {
    }

    public record OrderReceipt(String status, String sku, int quantity) {
    }

    @GetMapping(path = "/public/ping",
            produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> ping() {
        return Mono.just("pong");
    }

    @GetMapping(path = "/api/catalog",
            produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<List<String>> catalog() {
        return Mono.just(List.of("BOOK", "PEN", "NOTE"));
    }

    @GetMapping("/api/whoami")
    public Mono<Map<String, Object>> whoAmI(
            @AuthenticationPrincipal Jwt jwt) {
        return Mono.just(Map.of(
                "subject", jwt.getSubject(),
                "audience", jwt.getAudience()));
    }

    @PostMapping(path = "/api/orders",
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    @ResponseStatus(HttpStatus.CREATED)
    public Mono<OrderReceipt> createOrder(
            @RequestBody Mono<CreateOrderRequest> request) {
        return request.map(value -> {
            if (value.quantity() < 1 || value.sku() == null
                    || value.sku().isBlank()) {
                throw new IllegalArgumentException(
                        "sku and quantity must be valid");
            }
            return new OrderReceipt(
                    "ACCEPTED", value.sku(), value.quantity());
        });
    }
}
~~~

Trong ứng dụng thật nên dùng `@Validated`/exception mapping có 4xx riêng cho request invalid; ở demo các test chỉ gửi payload hợp lệ. `IllegalArgumentException` không tự mặc định cho 400 ở mọi WebFlux handler, nên **không** dùng nó như minh chứng cho error contract production.

`OrderReceipt` chỉ là kết quả minh họa, **không lưu database** hoặc tạo giao dịch thật. HTTP 201 thể hiện ý định của API demo; khi triển khai nghiệp vụ thật, cần transaction, idempotency key, authorization theo object và kiểm tra stock/tenant.

`whoAmI` cố ý không trả `jwt.getTokenValue()`, `Authorization` header hoặc toàn bộ claims. Thậm chí subject/audience là metadata cần được bảo vệ theo policy; endpoint này đã yêu cầu authenticated.

## 12. Kiểm thử HTTP Bearer thật với decoder mock

Có hai kiểu test dễ bị nhầm:
1. **Gửi một HTTP header `Authorization: Bearer ...`** vào Spring Security WebFilter và mock `ReactiveJwtDecoder` để kiểm tra converter, AuthenticationWebFilter, manager, authorities và authorization.
2. Dùng `mockJwt()` để inject authentication trực tiếp, không đi qua JWT decoding. Phù hợp unit/integration tests về authorization/controller.

Phần này dùng cách **(1)**. Nó thật sự gửi Bearer header qua WebTestClient, nhưng **decoder đã bị mock**, nên **không** chứng minh signature/issuer/audience/exp validation.

### 12.1. BearerJwtWebFluxTest.java

`src/test/java/demo/BearerJwtWebFluxTest.java`:

~~~java
package demo;

import java.time.Instant;
import java.util.List;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.http.MediaType;
import org.springframework.security.oauth2.jwt.BadJwtException;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.core.publisher.Mono;

import static org.mockito.Mockito.when;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
class BearerJwtWebFluxTest {

    @Autowired
    ApplicationContext context;

    // Spring Framework 6.2+; thay decoder thật bằng mock cho test.
    @MockitoBean
    ReactiveJwtDecoder jwtDecoder;

    private WebTestClient client;

    @BeforeEach
    void setup() {
        client = WebTestClient.bindToApplicationContext(context)
                .apply(springSecurity())
                .configureClient()
                .build();

        when(jwtDecoder.decode("reader-token"))
                .thenReturn(Mono.just(jwt(
                        "reader-token", "reader-42", "catalog.read")));
        when(jwtDecoder.decode("writer-token"))
                .thenReturn(Mono.just(jwt(
                        "writer-token", "writer-99",
                        "catalog.read orders.write")));
        when(jwtDecoder.decode("bad-token"))
                .thenReturn(Mono.error(
                        new BadJwtException("invalid JWT for test")));
    }

    private Jwt jwt(String value, String subject, String scopes) {
        Instant now = Instant.now();

        return Jwt.withTokenValue(value)
                .header("alg", "RS256")
                .claim("iss", "https://idp.example.test/realms/demo")
                .claim("sub", subject)
                .claim("aud", List.of("catalog-api"))
                .claim("scope", scopes)
                .issuedAt(now.minusSeconds(30))
                .expiresAt(now.plusSeconds(600))
                .build();
    }

    @Test
    void publicRouteNeedsNoBearer() {
        client.get().uri("/public/ping")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("pong");
    }

    @Test
    void missingBearerIs401WithChallenge() {
        client.get().uri("/api/catalog")
                .exchange()
                .expectStatus().isUnauthorized()
                .expectHeader()
                .valueMatches("WWW-Authenticate", "Bearer.*");
    }

    @Test
    void malformedOrInvalidJwtIs401() {
        client.get().uri("/api/catalog")
                .headers(h -> h.setBearerAuth("bad-token"))
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void validReaderScopeCanReadCatalog() {
        client.get().uri("/api/catalog")
                .headers(h -> h.setBearerAuth("reader-token"))
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$[0]").isEqualTo("BOOK");
    }

    @Test
    void authenticatedReaderWithoutWriteScopeGets403() {
        client.post().uri("/api/orders")
                .headers(h -> h.setBearerAuth("reader-token"))
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(new ApiController.CreateOrderRequest(
                        "BOOK", 1))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void writerWithWriteScopeCanCreate() {
        client.post().uri("/api/orders")
                .headers(h -> h.setBearerAuth("writer-token"))
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(new ApiController.CreateOrderRequest(
                        "BOOK", 2))
                .exchange()
                .expectStatus().isCreated()
                .expectBody()
                .jsonPath("$.status").isEqualTo("ACCEPTED")
                .jsonPath("$.sku").isEqualTo("BOOK")
                .jsonPath("$.quantity").isEqualTo(2);
    }

    @Test
    void validJwtShowsSafePrincipalDetails() {
        client.get().uri("/api/whoami")
                .headers(h -> h.setBearerAuth("reader-token"))
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.subject").isEqualTo("reader-42")
                .jsonPath("$.audience[0]").isEqualTo("catalog-api")
                .jsonPath("$.tokenValue").doesNotExist();
    }

    @Test
    void writerCannotUseUnlistedRoute() {
        client.get().uri("/api/unlisted")
                .headers(h -> h.setBearerAuth("writer-token"))
                .exchange()
                .expectStatus().isForbidden();
    }
}
~~~

### 12.2. Tại sao test này là integration của filter nhưng không phải validation chữ ký?

- WebTestClient tạo real HTTP request trong mock WebFlux application context.
- `ServerBearerTokenAuthenticationConverter` thấy header Bearer.
- `JwtReactiveAuthenticationManager` sử dụng bean `ReactiveJwtDecoder`.
- `@MockitoBean` làm decoder trả một `Jwt` đã dựng sẵn, **không kiểm chữ ký**.
- JwtAuthenticationConverter mapping `scope` thành `SCOPE_...`.
- AuthorizationWebFilter quyết định 200/201/401/403 theo rule.
- Controller chỉ chạy nếu đi qua security phù hợp.

**Rất quan trọng:** JWT giả `reader-token` không phải token thật, không có ba phần JWS. Nó “hoạt động” trong test vì decoder là mock. Đưa chuỗi này vào app chạy với NimbusReactiveJwtDecoder thật sẽ bị từ chối 401.

### 12.3. Vai trò của @MockitoBean

`@MockitoBean` thuộc Spring Framework Test 6.2+, available trong Spring Boot 3.5.x. Nó thay/đăng ký mock cho decoder trong test ApplicationContext; việc này khác với cấu hình production. Không lưu mock decoder trong `src/main` hoặc một bean hoạt động ở production profile, vì như vậy có thể cho phép token giả qua hệ thống.

Trong một số project cũ, bạn có thể thấy `@MockBean` của Spring Boot, nhưng ở các phiên bản mới có API `@MockitoBean`. Theo bài này, dùng dependency Spring Boot 3.5.7/Spring Framework 6.2 tương thích.

### 12.4. Chạy tests

Tại thư mục dự án:

~~~bash
gradle test
~~~

Nếu có Wrapper: `./gradlew test` hoặc `gradlew.bat test`. Dự kiến **8 tests** trong class này kiểm tra flow tương ứng; đó là kỳ vọng từ code, **không phải báo cáo Gradle đã chạy**.

Nếu test HTTP 401 thất bại, kiểm tra security chain đang áp dụng, decoder mock có nhận đúng token string, Bearer header có bị proxy/other filters thay đổi không, và `springSecurity()` đã được gắn đúng vào WebTestClient.

## 13. Kiểm thử authorization riêng bằng mockJwt()

Khi chỉ muốn test controller/access policy, Spring Security Test cung cấp `SecurityMockServerConfigurers.mockJwt()`. Nó tạo authentication mô phỏng, **không gọi `ReactiveJwtDecoder` và không xác minh signature/issuer/audience**.

### 13.1. JwtAuthorizationMockTest.java

`src/test/java/demo/JwtAuthorizationMockTest.java`:

~~~java
package demo;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockJwt;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
class JwtAuthorizationMockTest {

    @Autowired
    ApplicationContext context;

    private WebTestClient client;

    @BeforeEach
    void setup() {
        client = WebTestClient.bindToApplicationContext(context)
                .apply(springSecurity())
                .configureClient()
                .build();
    }

    @Test
    void scopeCanBeSuppliedViaMockJwt() {
        client.mutateWith(mockJwt()
                    .jwt(jwt -> jwt
                            .claim("sub", "mock-user")
                            .claim("scope", "catalog.read")))
                .get().uri("/api/catalog")
                .exchange()
                .expectStatus().isOk();
    }

    @Test
    void missingScopeIsForbiddenEvenWhenJwtIsMocked() {
        client.mutateWith(mockJwt()
                    .jwt(jwt -> jwt
                            .claim("sub", "mock-user")
                            .claim("scope", "profile")))
                .get().uri("/api/catalog")
                .exchange()
                .expectStatus().isForbidden();
    }
}
~~~

Ở đây `mockJwt()` bypass token parsing/validation và cung cấp principal cho authorization layer. Đây là **2 tests** bổ sung, không cần IdP thật. Nếu test dùng custom authorities converter, có thể chỉ định `.authorities(...)` tường minh hoặc dùng converter tương ứng để không nhầm “scope trong claim” và “GrantedAuthority đang có”.

### 13.2. Hai loại test giải quyết hai câu hỏi khác nhau

| Kiểu test | Gửi Authorization header qua filter? | Decode thật? | Kiểm chứng |
| --- | --- | --- | --- |
| `mockJwt()` | Không cần | Không | Route/permission/controller khi đã authenticated |
| HTTP Bearer + mocked ReactiveJwtDecoder | **Có** | Không | Token extraction, error path, JWT-to-authorities, authorization |
| HTTP Bearer + Nimbus decoder + signed fixture/JWKS test server | **Có** | **Có** | Signature, algorithm, issuer, audience, timestamps và integration |
| Browser/IdP staging | Tùy client | **Có** | Complete deployment, key rotation, discovery, gateway, TLS, token lifecycle |

Vì vậy, **không có** một test `mockJwt()` nào chứng minh token `alg=none` sẽ bị production từ chối. Để kiểm chứng điều đó phải test decoder/JWS validation thật với negative fixtures.

## 14. Kiểm thử JWT validation thật: test plan với JWKS và RSA

Trong môi trường test/staging, nên có một Authorization Server/JWKS test fixture hoặc một embedded test HTTP server để phục vụ JWKS public keys. Test một JWT được **ký hợp lệ** rồi những bản sai như sau:

| Ca | Setup | Kết quả mong đợi |
| --- | --- | --- |
| Happy path | Signature valid, expected issuer/audience, exp/nbf hợp lệ | Authentication thành công |
| Sai signature | Token ký bởi private key không khớp trusted JWKS | 401 |
| Unknown kid | Header kid không có trong JWKS tin cậy | 401 |
| Unsupported alg | Header alg không nằm trong allowlist | 401 |
| alg=none | JWT không có chữ ký theo profile không được cho phép | 401 |
| Issuer sai | JWT hợp lệ về signature nhưng `iss` không phải trusted issuer | 401 |
| Audience sai | `aud` không chứa catalog-api | 401 |
| Token hết hạn | exp nhỏ hơn thời điểm hiện tại ngoài clock skew | 401 |
| nbf ở tương lai | Token chưa bắt đầu có hiệu lực | 401 |
| Missing scope | JWT hợp lệ, không có catalog.read | 403 trên /api/catalog |
| Correct scope, wrong tenant | Có scope nhưng không sở hữu tenant/object | 403 hoặc 404 có chủ đích |
| Key rotation | JWKS có key mới và decoder refresh theo policy | Token hợp lệ được chấp nhận |
| JWKS unavailable | Có key cache hoặc không có; kết quả tùy cấu hình | Không bypass chữ ký để làm 200 |

**Không tạo những negative fixtures bằng cách thay payload rồi mock decoder trả chính payload đó**, vì hành vi ấy bỏ qua signature validation. Mỗi test phải dùng đúng tầng muốn chứng minh.

### 14.1. Một khi token đã bị revoke thì sao?

JWT validation offline không mặc nhiên biết access token vừa bị revoke tại IdP. Một token còn `exp` hợp lệ và chữ ký đúng có thể được nhận cho đến khi hết hạn nếu không có cơ chế bổ sung.

Các lựa chọn phụ thuộc hệ thống:
- Access token TTL ngắn.
- Introspection thay vì JWT offline cho một số API/flow.
- Revocation store/deny-list theo `jti` cho tình huống đặc thù.
- Key rotation khẩn cấp, hiểu tác động đến mọi token cùng key.
- DPoP/mTLS-bound access tokens.
- Gateway policy/continuous access evaluation khi nền tảng hỗ trợ.

Không tuyên bố “JWT luôn stateless nên có logout/revoke tức thì” — đó là quyết định thiết kế chứ không phải bảo đảm của token format.

## 15. Lệnh curl: phân biệt local demo và IdP thật

Khởi động app:

~~~bash
gradle bootRun
~~~

Public endpoint:

~~~bash
curl -i http://localhost:8080/public/ping
~~~

Kỳ vọng `200 OK`, body `pong`.

Protected endpoint không token:

~~~bash
curl -i http://localhost:8080/api/catalog
~~~

Kỳ vọng **401 Unauthorized** và `WWW-Authenticate: Bearer` vì chưa authentication.

Token sai định dạng/signature:

~~~bash
curl -i http://localhost:8080/api/catalog \
  -H 'Authorization: Bearer not-a-real-jwt'
~~~

Kỳ vọng **401 Unauthorized**, vì Nimbus Reactive JWT decoder thực không thể xác minh một chuỗi giả.

**Không thể** dùng `reader-token` / `writer-token` từ unit tests với app chạy thật. Các chuỗi này chỉ được test mock `ReactiveJwtDecoder` chấp nhận. Nếu bạn cần thử happy path bằng curl, hãy dùng **một access token thực sự được Authorization Server tin cậy cấp cho catalog-api**, qua TLS trong môi trường phù hợp:

~~~bash
# Không commit token; lấy nó qua flow của môi trường thử nghiệm.
curl -i https://your-api.example.test/api/catalog \
  -H "Authorization: Bearer <valid-access-token-for-catalog-api>"
~~~

Đây là lệnh mẫu: chuỗi trong dấu ngoặc nhọn cần thay bằng access token thật; không phải credential có sẵn. Tránh gõ token production trong terminal chia sẻ hoặc lưu history/log. Có thể dùng biến môi trường tạm thời với chính sách secret handling phù hợp.

Với JWT hợp lệ có `catalog.read`: kỳ vọng 200 và danh sách catalog. Với JWT hợp lệ có `orders.write` và JSON body hợp lệ:

~~~bash
curl -i -X POST https://your-api.example.test/api/orders \
  -H "Authorization: Bearer <valid-access-token-for-catalog-api>" \
  -H 'Content-Type: application/json' \
  --data '{"sku":"BOOK","quantity":2}'
~~~

Kỳ vọng **201 Created** trong demo, nếu token thật có scope cần thiết. Nếu không đủ scope, 403. Nếu đặt sai issuer/audience hoặc hết hạn, 401.

## 16. Multi-tenant, nhiều issuers và token confusion

Một API có thể phục vụ nhiều tenants hoặc nhiều Authorization Servers. Rủi ro thường gặp là tin `iss`/`aud`/tenant claims quá rộng.

### 16.1. Không xây decoder từ issuer do client tự gửi

Pseudocode sai:

~~~java
// SAI, không phải production implementation:
String issuer = unverifiedJwtPayload.get("iss");
ReactiveJwtDecoder decoder =
        ReactiveJwtDecoders.fromIssuerLocation(issuer);
return decoder.decode(token);
~~~

Nếu issuer do attacker tự chọn, server có thể gọi URL độc hại (SSRF), tải khóa của attacker hoặc nhầm trust boundary. Thay bằng issuer allowlist đã cấu hình:

~~~text
trusted issuer A -> verifier/key set A -> tenant policy A
trusted issuer B -> verifier/key set B -> tenant policy B
unrecognized issuer -> reject
~~~

Spring Security có `JwtIssuerReactiveAuthenticationManagerResolver` cho multi-tenant trusted issuer resolution. Nó là một công cụ kiến trúc, không miễn kiểm tra trusted-issuer allowlist/audience/resource ownership.

### 16.2. Một token có scope không tự có quyền mọi tenant

Ngay cả với `SCOPE_orders.write`, API phải giới hạn user/client được viết orders trong tenant nào. Ràng buộc tenant với principal và entity ID ở service, không chỉ với URL param do client chọn.

Không phân quyền chỉ bằng claim `tenant_id` nếu nó không được issuer tin cậy cấp theo hợp đồng và kiểm chứng; thậm chí claim hợp lệ vẫn phải so với resource tenant/entitlements hiện tại.

### 16.3. Different token profiles

Một issuer có thể cấp:
- ID tokens cho frontend.
- Access tokens JWT cho API.
- Opaque tokens cho introspection clients.
- Tokens cho nhiều audiences và scopes.

Đừng chấp nhận token sai profile chỉ vì nó cùng issuer/signature. Khi Authorization Server hỗ trợ JWT Access Token Profile RFC 9068, xem thêm token type/header và các claims theo profile. Bảo vệ chống token substitution và cross-resource token confusion.

## 17. Bearer token propagation qua WebClient: khi nào cần?

Resource Server A có thể cần gọi API B. Tùy hợp đồng, có thể:
- Forward token của caller **nếu** token cũng được cấp cho API B và policy cho phép.
- Thực hiện token exchange để lấy token có audience API B.
- Dùng client credentials riêng của backend nếu là service-level action.
- Không chuyển token user khi downstream không cần nó.

Spring Security Reactive có `ServerBearerExchangeFilterFunction`:

~~~java
// Snippet @Bean, cần WebClient và Spring Security imports.
@Bean
WebClient downstreamWebClient() {
    return WebClient.builder()
            .filter(new ServerBearerExchangeFilterFunction())
            .build();
}
~~~

Filter này có thể trích Bearer token từ current Authentication và đưa vào Authorization header của outbound request. **Không** tự động refresh token hết hạn như OAuth2 Client authorized-client manager.

**Bảo mật:** không gắn filter này vào WebClient dùng để truy cập mọi URL do user nhập; nếu không, token có thể bị chuyển tới host attacker. Phải giới hạn trusted downstream hosts, audience/resource binding, retry và logging. Nếu B yêu cầu audience riêng, chuyển nguyên token A có thể bị 401 — đó là dấu hiệu token được thiết kế cho API khác, không nên tắt audience validation.

### 17.1. API Gateway và header preservation

Nếu chạy sau gateway:
- HTTPS từ client tới edge và các hop nội bộ theo policy.
- Header Authorization không bị gateway strip/thay nhầm.
- Gateway xác thực riêng không tự thay API authorization.
- Nếu gateway chuyển trusted identity header, cần mTLS/proxy trust/strip untrusted incoming headers; không dùng X-User-ID client-supplied thay Bearer validation một cách vô điều kiện.
- Không log Authorization header ở access logs, WAF, CDN hay distributed tracing.

## 18. Các lỗi phổ biến và cách sửa

| Anti-pattern | Hậu quả | Hướng xử lý |
| --- | --- | --- |
| JWT có ba phần nên tự tin là hợp lệ | Header/payload có thể bị làm giả | Dùng ReactiveJwtDecoder/JWS verification |
| Chỉ verify signature, bỏ issuer/audience | Nhận token của client/resource khác | Issuer + audience + exp/nbf validators |
| Chấp nhận `alg=none` | Bypass signing | Algorithm allowlist và JOSE decoder an toàn |
| Tải JWKS từ `jku` tùy ý | SSRF/attacker-controlled keys | Trusted JWK Set URI/issuer allowlist |
| Gửi ID token làm Bearer API | Sai audience, token substitution | Dùng access token dành cho API |
| Dùng refresh token gọi API | Lộ credential sai mục đích | Refresh ở Authorization Server |
| Mặc định mọi scope đều là ROLE_ADMIN | Leo thang đặc quyền | Mapping quyền từ nguồn tin cậy |
| Bỏ object/tenant authorization | User đọc object người khác | Ownership/ABAC/RBAC ở service |
| Bật `setDefaultOAuth2AuthorizedClient` hay propagation tới mọi URL | Leak token outbound | Scope WebClient theo trusted hosts |
| Tắt CSRF toàn app vì có Bearer | Browser cookie flow có nguy cơ CSRF | Threat model từng chain |
| Nghĩ disable CSRF cũng tắt CORS | Hai cơ chế độc lập | CORS trước authentication, CSRF theo client |
| Tự gọi `block()` trong WebFlux | Chặn event loop | Mono/map/flatMap |
| Dùng Servlet `BearerTokenAuthenticationFilter` | Sai stack | Reactive AuthenticationWebFilter |
| Đọc `SecurityContextHolder` ThreadLocal như Servlet | Authentication không ổn định qua reactive hops | Reactor Context / ReactiveSecurityContextHolder |
| Nhầm `JwtAuthenticationToken` với `OidcUser` | Sai principal type | Tách Resource Server và OAuth2 Login |
| Test bằng `mockJwt` rồi kết luận signature validation PASS | Mock bypass decoder | Test JWKS/real JWT separately |
| Lấy `reader-token` từ test gửi lên production | Token không ký, 401 | Dùng token thật trong môi trường kiểm soát |
| Vô hiệu verify để “fix 401” | Authentication bypass | Sửa issuer/JWKS/alg/aud |
| Coi mọi 403 là token sai | Có thể là thiếu scope/CSRF/tenant | Kiểm tra tầng phát lỗi |
| Log token để debug | Rò credentials | Redact Authorization và raw JWT |
| Tin JWT revoke tức thời | Token offline có thể còn hợp lệ đến exp | TTL ngắn/revoke strategy |

## 19. Debug theo từng bước

### Request GET protected trả 401

1. Header có thật là `Authorization: Bearer <token>` không?
2. Gateway/proxy có strip header?
3. Token có phải access token, không phải ID token?
4. Chuỗi có đúng cấu trúc JWS và signature?
5. Issuer `iss` có khớp configured issuer?
6. Audience `aud` có chứa resource ID phù hợp?
7. `exp`/`nbf` và clock skew?
8. Algorithm có được decoder cho phép?
9. `kid` có trong trusted JWKS? Key rotation và cache có cập nhật?
10. TLS/JWKS endpoint có truy cập được không?
11. Error nào được trả trong `WWW-Authenticate` (không log token)?
12. Request có vào security chain đúng không?

**Không tắt audience hoặc signature validation để chữa 401.** Nếu token có audience khác, xin lại token được cấp cho resource server đúng.

### GET được 200, POST bị 403

1. JWT hợp lệ nhưng có scope `catalog.read` mà thiếu `orders.write`?
2. API có rule method-specific cho POST chưa?
3. Object/tenant-level checks có từ chối?
4. Nếu ứng dụng pha cookie login, CSRF filter có chặn POST không?
5. CORS preflight của browser có cho phép Authorization và Content-Type?
6. Có nhiều security chains với matcher hoặc thứ tự khác nhau?
7. Request đã vượt qua converter/decoder nhưng bị AuthorizationWebFilter chặn chưa?
8. Có custom authority converter mapping claim sai prefix?

### JWT từ issuer A được, issuer B không được

- Hệ thống có cho phép nhiều issuer thật không?
- Issuer B có trust/key set riêng?
- Audience của B đúng API?
- Có một issuer allowlist cho multi-tenant?
- Key rotation/truststore/clock?
- Không tự chấp nhận issuer từ request.

### Test mock PASS, production 401

- Mock JWT có thể bỏ chữ ký/issuer/audience/expiry.
- Cấu hình production chỉ chấp nhận signing algorithms theo policy.
- Real token có `aud`/scope khác mock.
- JWKS và IdP endpoint không có trong local tests.
- Resource Server đang nhận ID token thay access token.

Đây là lý do cần **ít nhất hai tầng test**: authorization mocks và JWT validation integration.

## 20. Security checklist trước production

### HTTP và token handling

- [ ] HTTPS/TLS cho client-to-API và trusted internal hops.
- [ ] Authorization: Bearer header là kênh mặc định; không đưa token vào query string.
- [ ] No secrets/token values trong logs, error bodies hoặc telemetry.
- [ ] JWT không chứa dữ liệu nhạy cảm không cần thiết vì payload thường đọc được.
- [ ] Short-lived access tokens và chính sách revoke/refresh phù hợp.
- [ ] Không trả Jwt object/raw token trong DTO.

### JWT validation

- [ ] Chỉ trusted issuers và trusted JWKS endpoints.
- [ ] Signature verified bằng khóa/algorithms đã phê duyệt.
- [ ] aud khớp resource server; không nhận ID token của web client.
- [ ] exp/nbf/iat, clock skew được đánh giá.
- [ ] Header alg/kid/typ profile được xử lý an toàn.
- [ ] Key rotation, JWKS caching và outage behavior được test.
- [ ] Không tự chấp nhận jku/x5u bên ngoài allowlist.
- [ ] Opaque access token không bị đưa qua JWT decoder.

### Authorization

- [ ] Scopes/authorities mapping đúng `SCOPE_` hoặc claim converter đã review.
- [ ] `hasAuthority` và `hasRole` không bị trộn.
- [ ] HTTP method/route matcher default-deny.
- [ ] Object ownership và tenant boundary được enforce.
- [ ] Token của machine clients không tự có user privileges.
- [ ] Multi-issuer resolution chỉ cho trusted issuers.

### Reactive, browser và operations

- [ ] Spring Security Reactive classes đúng: `ServerHttpSecurity` / `SecurityWebFilterChain`.
- [ ] Không block/subscribe thủ công trong authentication chain.
- [ ] SecurityContext repository/stateless policy đã được chọn rõ.
- [ ] CSRF không tắt nếu có browser ambient credentials.
- [ ] CORS preflight hoạt động khi SPA cần Authorization header.
- [ ] Entry point 401 và access-denied 403 giữ Bearer semantics.
- [ ] WebClient không truyền token tới host không tin cậy.
- [ ] Monitoring có request ID, route, auth result, không có raw tokens.

### Tests

- [ ] Missing token -> 401 + Bearer challenge.
- [ ] Invalid token -> 401.
- [ ] Valid token + correct scope -> 200/201.
- [ ] Valid token + insufficient scope -> 403.
- [ ] Jwt principal safe DTO không lộ token.
- [ ] Different issuer/audience/key/expiry negatives qua real decoder.
- [ ] Key rotation JWKS fixture.
- [ ] Ownership/tenant authorization negatives.
- [ ] Mock tests không được coi là signature-validation tests.
- [ ] Gateway/header forwarding, TLS, CORS/CSRF, session behavior trên staging.

## 21. Câu hỏi tự kiểm tra

**1. Bearer token có nghĩa gì?**

> Ai giữ credential hợp lệ có thể trình nó để gọi API trong phạm vi quyền/thời hạn; nếu bị đánh cắp có thể bị replay.

**2. Converter Bearer có phải JWT decoder không?**

> Không. ServerBearerTokenAuthenticationConverter trích chuỗi Bearer từ request; ReactiveJwtDecoder xác minh JWS và claims.

**3. Spring Security Reactive dùng authentication manager nào cho JWT?**

> Thường JwtReactiveAuthenticationManager, implement ReactiveAuthenticationManager.

**4. Controller nhận principal nào sau JWT Resource Server?**

> Thường Jwt trong JwtAuthenticationToken, không phải OidcUser của OAuth2 Login.

**5. Chữ ký đúng có đủ để API chấp nhận JWT không?**

> Không. Cần issuer, audience, exp/nbf, algorithm và policy phù hợp.

**6. Vì sao `scope=catalog.read` thành `SCOPE_catalog.read`?**

> Spring Security default JWT authorities converter thêm tiền tố SCOPE_.

**7. Missing token và insufficient scope khác HTTP thế nào?**

> Thường 401 cho thiếu/invalid credentials, 403 cho authenticated user thiếu permission.

**8. ID token có dùng làm Authorization: Bearer tới orders-api được không?**

> Không. ID token dành cho OIDC client; API nhận access token dành cho resource của mình.

**9. `NoOpServerSecurityContextRepository` có làm API không thể dùng authentication không?**

> Không. Authentication vẫn được tạo trên mỗi request; nó không được lưu thành server session security context.

**10. Khi nào tắt CSRF hợp lý?**

> Khi API thật sự chỉ dùng Bearer token được client tự gửi và không có browser ambient credentials; cần threat model rõ.

**11. `mockJwt()` có test được signature verification không?**

> Không. Nó bypass decoder, chỉ test security decisions sau khi authentication được giả lập.

**12. Audience sai nên sửa thế nào?**

> Xin access token cho resource đúng và cấu hình audience đúng, không bỏ validation.

**13. JWT hết hạn có tự làm refresh token hết hạn không?**

> Không. Token lifetimes và refresh policy có lifecycle riêng.

**14. Nếu JWKS key rotate, phải làm gì?**

> Đảm bảo trusted JWKS cập nhật/decoder refresh key và test giai đoạn chuyển tiếp, không disable verify.

**15. JWT bị revoke tại IdP có chắc Resource Server offline biết ngay không?**

> Không. Cần policy TTL, revocation/introspection/deny-list hoặc cơ chế bổ sung.

## 22. Tổng kết

Cơ chế Bearer JWT trong Spring Security WebFlux là một pipeline **Reactive**:

~~~text
Authorization: Bearer <JWT>
       -> ServerBearerTokenAuthenticationConverter
       -> JwtReactiveAuthenticationManager
       -> ReactiveJwtDecoder (signature + issuer/audience/time validation)
       -> JwtAuthenticationToken (principal=Jwt, authorities=SCOPE_...)
       -> Reactor SecurityContext
       -> authorizeExchange / method and object authorization
       -> Controller / Service
~~~

Giữ đúng ba ranh giới:
1. **Bearer token là credential có thể replay**, nên phải có TLS, bảo vệ token, không log và giới hạn thời hạn.
2. **JWT authentication không phải chỉ decode payload**: bắt buộc xác minh chữ ký, issuer, audience, thời gian và token profile theo trust policy.
3. **Authentication không tự là authorization**: scopes, roles, tenant và object ownership phải được kiểm soát riêng.

Dùng `spring-boot-starter-oauth2-resource-server`, `ServerHttpSecurity.oauth2ResourceServer(...jwt(...))` và `issuer-uri/jwk-set-uri/audiences` để bảo vệ API. Test JWT authorization bằng mock là hữu ích nhưng phải bổ sung real JWT/JWKS validation tests trước production.

### Tài liệu tham khảo chính thức

- Spring Security 6.5 — OAuth 2.0 Resource Server JWT (Reactive): https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/resource-server/jwt.html
- Spring Security 6.5 — Reactive Bearer Tokens: https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/resource-server/bearer-tokens.html
- Spring Security 6.5 — Testing Reactive OAuth2/JWT: https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/oauth2.html
- Spring Boot 3.5 — Spring Security Resource Server properties: https://docs.spring.io/spring-boot/3.5/reference/web/spring-security.html
- Spring Security 6.5 Javadoc — JwtReactiveAuthenticationManager: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/server/resource/authentication/JwtReactiveAuthenticationManager.html
- Spring Security 6.5 Javadoc — ServerBearerTokenAuthenticationConverter: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/server/resource/web/server/authentication/ServerBearerTokenAuthenticationConverter.html
- Spring Security 6.5 Javadoc — ReactiveJwtDecoder: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/jwt/ReactiveJwtDecoder.html
- Spring Security — Reactive multi-tenancy: https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/resource-server/multitenancy.html
- RFC 6750 — OAuth 2.0 Bearer Token Usage: https://www.rfc-editor.org/rfc/rfc6750
- RFC 7519 — JSON Web Token (JWT): https://www.rfc-editor.org/rfc/rfc7519
- RFC 7517 — JSON Web Key (JWK): https://www.rfc-editor.org/rfc/rfc7517
- RFC 8725 — JWT Best Current Practices: https://www.rfc-editor.org/rfc/rfc8725
- RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens: https://www.rfc-editor.org/rfc/rfc9068
- RFC 9700 — OAuth 2.0 Security Best Current Practice: https://www.rfc-editor.org/rfc/rfc9700