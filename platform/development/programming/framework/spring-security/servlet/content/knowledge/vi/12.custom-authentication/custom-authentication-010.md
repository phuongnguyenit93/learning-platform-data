# Phân biệt API key, opaque token và JWT trước khi chọn cách tích hợp

Khi xây dựng một API với **Spring Security Servlet**, ba lựa chọn dễ bị đặt cạnh nhau là **API key, opaque token và JWT**. Nhưng đây không phải ba “thuật toán đăng nhập” có cùng bản chất. API key chủ yếu nói về **credential được cấp cho client/integration**; opaque token nói về **cách tài nguyên phải kiểm tra giá trị token**; JWT nói về **định dạng dữ liệu token và các claim**. Một OAuth2 access token có thể ở dạng opaque hoặc JWT, và một API key thường cũng là một chuỗi bí mật không có cấu trúc. Vì vậy cần quyết định về **chủ thể, nguồn tin cậy, vòng đời cấp phát, kiểm chứng và thu hồi** trước khi chọn thư viện tích hợp.

Bài học thuộc phần **Xác thực tùy chỉnh**, trong module **Spring Security – servlet**. Các ví dụ sử dụng Spring Security 6.x, Java 17 và Spring Boot 3.3.5; phân biệt rõ **ví dụ chạy được** (API key với MockMvc) và **mẫu tích hợp phụ thuộc authorization server** (OAuth2 opaque/JWT).

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích API key, opaque token và signed JWT mà không nhầm **định dạng** với **mục đích cấp token**.
2. Phân biệt `authentication`, `authorization`, `scope`, `principal`, `issuer` và `audience`.
3. Chọn giữa kiểm tra **key store**, **introspection** và **JWT signature/claim validation** cho từng trường hợp.
4. Đánh giá latency, cache, revocation, quyền động, rủi ro replay, key rotation và dữ liệu có thể bị lộ.
5. Dùng Spring Security Servlet đúng vai trò: custom API-key filter/provider hoặc OAuth2 Resource Server có sẵn.
6. Viết test cho credential thiếu/sai, scope thiếu, token sai mục tiêu, token bị thu hồi và ranh giới tenant.
7. Biết khi nào **không nên tự viết JWT parser, bearer-token filter hoặc giao thức OAuth2**.

## 2. Ba trục khái niệm phải tách riêng

### 2.1. Credential dùng để làm gì?

Credential là bằng chứng phía gọi đưa cho API. Nó có thể đại diện một user, service account, integration, dự án, thiết bị hoặc một lần ủy quyền từ user cho client.

**API key** thường do chủ API cấp cho một integration/service. Một key có thể gắn quyền truy cập cố định, hạn dùng, quota và tenant. API key không tự nói rằng nó đại diện một người dùng đã đăng nhập bằng trình duyệt.

**Access token** thường được phát hành theo một giao thức/chính sách xác thực và ủy quyền, ví dụ OAuth2. Nó có thể đại diện cho client qua client credentials flow hoặc cho truy cập được user ủy quyền qua authorization code flow. Opaque và JWT chỉ là hai cách thể hiện/kiểm tra token.

**ID token** của OpenID Connect thường là JWT nhưng dùng để chuyển thông tin authentication cho client. API **không được dùng ID token như access token** chỉ vì cùng issuer hoặc chữ ký hợp lệ.

### 2.2. Token có hình dạng gì?

~~~text
X-API-Key: random-secret-issued-to-service-42
Authorization: Bearer opaque-random-access-token
Authorization: Bearer eyJ...encoded-header.eyJ...encoded-payload.signature
~~~

Cả ba giá trị đều chỉ minh họa. Header `Authorization: Bearer` **không chứng minh** token là JWT; OAuth2 resource server có thể nhận opaque token hoặc signed JWT trong cùng header tùy cấu hình. API key cũng có thể đặt trong Authorization header theo giao thức do hệ thống quy định.

JWT dạng JWS compact thường có ba phần `header.payload.signature`, trong đó header/payload được base64url encode. **Base64url không phải mã hóa bảo mật**: payload JWS thường có thể được đọc bởi ai đang giữ token. JWE có hỗ trợ mã hóa nhưng là một cơ chế khác.

### 2.3. Ai có quyền quyết định credential hợp lệ?

- **API key**: key store/verifier do hệ thống API tin cậy, có thể tra key id và so hash.
- **Opaque token**: authorization server/introspection endpoint hoặc token store đáng tin cung cấp trạng thái và quyền.
- **JWT**: resource server dùng khóa đáng tin để verify chữ ký rồi kiểm tra `iss`, `aud`, thời hạn, token type, scopes và các claim/ràng buộc liên quan.

**Chỉ trích xuất được một chuỗi tên/role từ request không đồng nghĩa đã xác thực thành công.** Authentication đáng tin phải xuất hiện *sau* bước verification, không phải ngay khi parse header hay decode JSON.

## 3. Bảng so sánh tổng thể

| Tiêu chí | API key | Opaque access token | JWT access token dạng JWS |
| --- | --- | --- | --- |
| Khái niệm | Credential thường cấp cho client/integration | Access token cần tra cứu/introspection để xác định nội dung tin cậy | Định dạng token mang claim, thường có chữ ký |
| Hình dạng | Thường chuỗi ngẫu nhiên, không chuẩn chung | Giá trị opaque, không tự giải nghĩa ở resource server | JWS: header.payload.signature |
| Chủ thể phổ biến | Client, service, integration | User hoặc client tùy OAuth2 grant | User hoặc client tùy OAuth2 grant |
| Kiểm chứng | Key store, hash, trạng thái, scopes | Token store hoặc introspection | Signature và claim validators |
| Có cần gọi issuer mỗi request? | Tùy key-store/cache | Thường có khi introspection online; có thể cache | Thường không, sau khi cache trusted JWKS |
| Thu hồi | Dễ nếu tra trạng thái key thật | Dễ hơn khi introspect trạng thái hiện tại | Khó khi hoàn toàn offline; cần TTL/denylist/state |
| Quyền có thể lỗi thời? | Có nếu cache key metadata | Có nếu cache introspection | Có cho đến hết hạn hoặc có kiểm tra thêm |
| Nội dung lộ qua token | Thường không có claim, nhưng key là bí mật | Không tự lộ claim, nhưng bearer token là bí mật | JWS payload đọc được, không đặt secret/PII không cần thiết |
| Tích hợp Spring Security | Custom filter/provider thường gặp | `oauth2ResourceServer().opaqueToken(...)` | `oauth2ResourceServer().jwt(...)` |
| Ví dụ use case | Đối tác backend đồng bộ dữ liệu | OAuth2 cần quyền/thu hồi tập trung | Nhiều microservices cần local signature verification |
| Rủi ro khi bị đánh cắp | Có thể bị dùng lại | Có thể bị dùng lại | Có thể bị dùng lại |

**Lưu ý:** các hàng là thiết kế điển hình, không phải hợp đồng áp dụng cho mọi nhà cung cấp. API key cũng có thể ngắn hạn; JWT cũng có thể bị introspect; opaque token cũng có thể dùng local token database. **Bearer token** là credential dùng được bởi người sở hữu giá trị, trừ khi hệ thống bổ sung cơ chế sender-constrained như mTLS-bound token hoặc DPoP.

## 4. API key: đơn giản ở client, nhưng vòng đời phải nghiêm túc

API key có thể phù hợp khi bạn sở hữu API và một số client backend cần tự động gọi API **không thay mặt user cụ thể**. Client được cấp một secret, gửi trong header đã thống nhất và API xác minh key trước khi truy cập tài nguyên.

### 4.1. Thiết kế key đúng

Một hệ thống đáng tin thường phải:

- Sinh key bằng **CSPRNG** với entropy cao; đừng dùng email, username, timestamp hoặc dữ liệu dễ đoán làm secret.
- Có **key id/prefix không bí mật** để truy vấn nhanh, nhưng vẫn yêu cầu secret hợp lệ.
- Chỉ hiển thị raw key **một lần** khi tạo; lưu hash/digest phù hợp thay vì giá trị có thể tái sử dụng.
- Gắn key với `clientId`, owner, tenant, scopes, trạng thái, ngày cấp/hết hạn và quota.
- Cho phép rotate key với khoảng chuyển tiếp được phê duyệt, sau đó thu hồi key cũ.
- Áp dụng HTTPS, rate limiting, audit, secret scanning và không log raw key.
- Tách key production, staging và development; không chia sẻ một key cho mọi integration.

Dạng dữ liệu minh họa:

~~~text
key_id:        integration_102
key_hash:      SHA256(secret entropy cao)  [chỉ mô tả]
client_id:     invoice-sync
tenant_id:     tenant-a
scopes:        [invoice.read]
status:        active
expires_at:    2027-06-01T00:00:00Z
last_used_at:  metadata không nhạy cảm
~~~

Vì API key cần có entropy đủ cao, lưu một **SHA-256 digest** có thể là giải pháp hợp lý cho key dài ngẫu nhiên; điều này **khác hoàn toàn việc băm mật khẩu người dùng**. Password do user chọn có entropy thường thấp, cần bcrypt/Argon2id/PBKDF2/SCrypt với work factor thích hợp. Với key entropy thấp, digest nhanh vẫn dễ bị brute force.

### 4.2. Nơi lưu key ở client

- Server-to-server backend có thể giữ key trong secret manager hoặc environment được bảo vệ.
- Không hardcode **secret API key** trong JavaScript chạy trên browser hoặc ứng dụng mobile public, vì người dùng có thể trích xuất.
- Không gửi key qua query parameter URL: token dễ lọt vào logs, history, monitoring hoặc referer.
- Tránh key được dùng bởi hàng nghìn người dùng frontend thay cho user authentication; một key bị lộ có thể khiến mọi người dùng bị ảnh hưởng.

### 4.3. Quyền của API key

Key hợp lệ không có nghĩa được gọi mọi endpoint. Một key chỉ có `invoice.read` không nên POST sửa hóa đơn, không được truy cập tenant khác hoặc gọi endpoint admin. Scopes/authorities phải đến từ **bản ghi key trên server đã được kiểm chứng**, không từ header do client tự gửi như `X-Role: ADMIN`.

### 4.4. Hạn chế của API key

Nếu bạn cần user consent, delegated authorization cho ứng dụng bên thứ ba, token theo phiên người dùng, chuẩn scopes/refresh/PKCE hoặc một authorization server đã có, API key tự chế có thể trở thành giao thức OAuth2 không chuẩn. Hãy cân nhắc OAuth2/OIDC phù hợp, mTLS/workload identity hoặc các cơ chế chuẩn khác trước khi đầu tư tự phát triển.

## 5. Opaque token: tin vào issuer/token store qua introspection

Opaque token là token mà bên sử dụng **không nên tự giải mã nội dung để cấp quyền**. Đối với OAuth2, một authorization server phát access token và resource server hỏi **introspection endpoint** để nhận thông tin như token active, subject, client id, scopes và metadata, theo khả năng của issuer.

~~~text
Client -> GET /api/invoices
          Authorization: Bearer opaque-access-token
        |
        v
Resource server / BearerTokenAuthenticationFilter
        |
        v
OpaqueTokenIntrospector
        |
        +-- HTTPS -> Authorization server introspection endpoint
        |            resource server xác thực bằng credential riêng
        |
        +-- response active, scopes, claims, metadata
        |
        v
Authentication đáng tin + GrantedAuthority
        |
        v
Authorization -> controller (200) hoặc từ chối (401/403)
~~~

Nếu introspection báo inactive, token phải bị từ chối. Nếu endpoint timeout hoặc không thể xác nhận token, **không mặc định cho qua**. Cần có error handling rõ ràng, monitoring/timeout/circuit breaker phù hợp với chính sách không fail-open.

### 5.1. Ưu điểm

- Có điểm quyết định trạng thái token tập trung: issuer có thể thu hồi hoặc phản ánh thay đổi policy.
- Resource server không phải verify JWS/JWKS nếu chỉ nhận opaque token qua introspection.
- Token string không nhất thiết chứa claims đọc được; có lợi về data minimization, nhưng bản thân bearer token vẫn là secret.
- Hữu ích khi authorization server đã cung cấp token introspection đáng tin và nhu cầu kiểm soát quyền động cao.

### 5.2. Đánh đổi

- Gọi mạng tới introspection tạo latency, throughput cost và phụ thuộc khả dụng của AS.
- Introspection client id/secret phải được lưu an toàn, khác với access token của user.
- Cache introspection giảm tải nhưng làm chậm thu hồi. Nếu TTL cache 5 phút, token đã bị thu hồi có thể được resource server chấp nhận trong cửa sổ cache theo policy.
- Phải kiểm tra audience, resource, issuer/tenant/client binding nếu hệ thống cần; phản hồi `active=true` **không có nghĩa mọi API đều được cấp quyền**.
- Cần xử lý token malformed, timeout, HTTP error, scope mapping và không log token nguyên văn.

**Không khẳng định “opaque luôn thu hồi ngay” nếu ứng dụng cache kết quả introspection lâu.** Mức thu hồi thực tế là quyết định vận hành, không chỉ tên định dạng.

## 6. JWT: tự chứa claim và kiểm tra chữ ký/điều kiện

JWT dạng JWS thường có chữ ký và claim JSON:

~~~text
base64url(header).base64url(payload).base64url(signature)
~~~

Payload minh họa (không có chữ ký nên **không phải token hợp lệ**):

~~~json
{
  "iss": "https://issuer.example",
  "sub": "user-123",
  "aud": ["invoice-api"],
  "exp": 1893456000,
  "iat": 1893452400,
  "scope": "invoice.read"
}
~~~

Các claim phổ biến:

| Claim | Vai trò | Cần chú ý |
| --- | --- | --- |
| `iss` | Issuer phát token | Chỉ tin issuer được cấu hình/ủy quyền |
| `sub` | Chủ thể được biểu diễn | Không tự suy luận đầy đủ quyền |
| `aud` | Đối tượng nhận token | Token dành cho API khác phải bị từ chối |
| `exp` | Hết hạn | Cần kiểm tra chính xác, có clock skew hợp lý |
| `nbf` | Chưa được dùng trước thời điểm | Phải kiểm tra nếu có |
| `iat` | Thời điểm phát hành | Hữu ích cho policy tuổi token/diagnostics |
| `scope` / `scp` | Scopes theo convention issuer | Map chính xác sang authorities |
| `jti` | Id token khi issuer cấp | Có thể dùng cho denylist/audit nếu cần |

JWT không phải lúc nào cũng là OAuth2 access token: **ID token** và các JWT thuộc mục đích khác phải được phân biệt. Resource server không được chấp nhận token cho client login như access token chỉ vì chữ ký hợp lệ.

### 6.1. Checklist validate JWT

1. Verify JWS signature bằng key đáng tin được issuer công bố/được cấu hình.
2. Chỉ cho phép JWS algorithms theo policy; không tin chuỗi `alg` do token tự khai như quyền điều khiển crypto.
3. Xác minh `iss`, `aud`, `exp`, `nbf` và giới hạn tuổi token nếu cần.
4. Kiểm tra loại/mục đích token để chống **token confusion**.
5. Ánh xạ scopes/roles theo issuer đã kiểm chứng, không đọc trước verify để cấp quyền.
6. Kiểm tra tenant/resource ownership và các quyền động cần thiết ở authorization.
7. Quản lý JWKS/key id `kid`, cache và rotation từ trust anchor đã cấu hình; không tự theo URI do token chưa được xác minh gợi ý.
8. Dùng TLS, logging redaction và không đưa secret/PII không cần thiết vào JWT payload.

**Giải mã payload bằng base64url chỉ cho bạn biết token khai gì; không bảo đảm điều đó đúng.** Trong Spring Security nên dùng `JwtDecoder`/OAuth2 Resource Server thay vì tự viết code parse chữ ký.

### 6.2. Ưu điểm

- Resource server có thể verify token cục bộ, giảm gọi issuer trên mỗi request.
- Nhiều microservices có thể chia sẻ trust issuer và JWKS, áp dụng audience/scope riêng.
- Chữ ký bất đối xứng giúp resource server chỉ cần public keys để kiểm tra, không cần private signing key.
- Claims đã xác minh có thể giúp dựng Authentication mà không phải lookup thông tin cơ bản cho mỗi request.

### 6.3. Nhược điểm và nghĩa vụ vận hành

- **Revocation** khó hơn nếu resource server hoàn toàn offline và token chưa hết hạn; phải cân nhắc TTL ngắn, denylist, policy check động hoặc introspection khi cần.
- Roles/scopes đã nhúng có thể lỗi thời khi user bị khóa hoặc quyền thay đổi.
- JWS payload **đọc được**; không cho passwords, secrets hoặc thông tin cá nhân không cần thiết vào token.
- Token có thể quá lớn; Authorization header gặp giới hạn kích thước ở proxy/gateway.
- JWKS cache, key rotation, network outage, thuật toán và issuer metadata cần được quản lý rõ.
- Dùng HMAC shared secret cho nhiều resource servers có thể mở rộng phạm vi lộ bí mật; asymmetric signing thường tách quyền phát/kiểm tra dễ hơn.

**JWT không đồng nghĩa hoàn toàn stateless.** Authentication có thể verify offline, nhưng authorization động vẫn cần policy/database/cache; token có thể vẫn phải kiểm tra denylist hoặc account trạng thái hiện tại.

## 7. Quy trình chọn giải pháp theo nhu cầu

| Nhu cầu thực tế | Hướng đánh giá đầu tiên | Điều kiện cần xác minh |
| --- | --- | --- |
| Backend đối tác gọi vài API, không có user delegation | API key per-integration | Key entropy, scopes, expiry, rotate, quota, tenant |
| OAuth2 cần revoke nhanh, quyền thường xuyên thay đổi | Opaque introspection | Latency, AS availability, cache TTL, fail-closed |
| Nhiều resource servers, thông lượng cao, cần local validation | Signed JWT access token | Audience, issuer/JWKS, TTL, revocation/claim staleness |
| Cần user consent/third-party login | OAuth2/OIDC chuẩn | Access token/ID token khác nhau, grant và client type |
| Browser public frontend không thể bảo vệ client secret | Authorization Code + PKCE hay BFF theo thiết kế | Token storage, session, XSS/CSRF, refresh handling |
| Client credentials service-to-service | OAuth2 client credentials hoặc workload identity | Client identity, scopes, key rotation |
| Cần quyền theo tenant với thay đổi tức thời | Có thể dùng token nào cũng được nhưng thêm state checks | Không tin tenant header do client tự gửi |
| Hạ tầng chưa có AS và cần tích hợp nhỏ có kiểm soát | API key đơn giản | Tránh biến key thành quyền vô hạn/không thu hồi |

### Cây quyết định

~~~text
Có user delegation, consent hoặc issuer OAuth2 chuẩn?
    |
    +-- CÓ --> Dùng OAuth2 access token
    |          |
    |          +-- Cần cập nhật revoked/permissions gần thời gian thực?
    |          |       +-- Xem opaque introspection hoặc JWT + state checks
    |          |
    |          +-- Cần local verification ở rất nhiều resource servers?
    |                  +-- Xem signed JWT + audience/issuer/scope validators
    |
    +-- KHÔNG --> Integration backend có ít client?
                 |
                 +-- Có --> API key per-client có hạn dùng, scopes và rotation
                 |
                 +-- Không --> Đánh giá OAuth2 client credentials / mTLS
                                hoặc workload identity đáng tin

Bất kể nhánh nào: xác minh danh tính + quyền + ranh giới tenant + thu hồi.
~~~

Không có yêu cầu phải chọn đúng **một kiểu cho toàn bộ công ty**. Có thể dùng API key cho integration, OAuth2 token cho user APIs và workload identity cho nội bộ. Tuy nhiên phải tách policy của các nhóm endpoint để một credential không trở thành **đường tắt vượt quyền**.

## 8. Spring Security Servlet: nơi nào xử lý token/key?

Trong Servlet stack, `FilterChainProxy` chọn `SecurityFilterChain` theo request matcher. Các filter xử lý authentication trước khi controller được gọi. Dữ liệu từ credential phải được kiểm chứng, rồi mới đưa một `Authentication` đáng tin vào `SecurityContext` để authorization đánh giá.

~~~text
HTTP request
    |
    v
FilterChainProxy chọn SecurityFilterChain
    |
    +--- API key: custom verifier/filter/provider
    |           -> key store/status/scopes
    |           -> trusted Authentication
    |
    +--- Bearer opaque: BearerTokenAuthenticationFilter
    |                 -> OpaqueTokenIntrospector
    |                 -> trusted Authentication
    |
    +--- Bearer JWT: BearerTokenAuthenticationFilter
    |              -> JwtDecoder/validators
    |              -> trusted Authentication
    |
    v
Authorization: scope/role/tenant/resource ownership
    |
    +-- đủ quyền -> DispatcherServlet/controller
    +-- thiếu/sai -> 401 hoặc 403 theo policy/entry point
~~~

Cần phân biệt:

- **Authentication**: “credential có hợp lệ và đại diện cho ai?”
- **Authorization**: “người gọi đã xác thực có quyền gọi đúng resource/action này không?”
- **Chọn chain**: `securityMatcher(...)` giới hạn URL/method được đưa vào một chain.
- **Chọn rule**: `requestMatchers(...)` trong `authorizeHttpRequests` chọn yêu cầu quyền trong chain đó.

Một token hợp lệ nhưng scope không đủ thường gây 403; không có/sai token trên API Bearer thường gây 401. Trong các ứng dụng khác, entry point và CSRF có thể ảnh hưởng status; đừng suy từ một code status mà bỏ qua filter order.

### 8.1. API key thường cần custom integration

Spring Security không có một chuẩn API-key chung cho mọi sản phẩm tương đương với OAuth2 Resource Server. Lựa chọn hợp lý:

- `OncePerRequestFilter` cho một integration rất đơn giản, verifier rõ ràng, kiểm soát khi nào filter chạy.
- `AuthenticationFilter + AuthenticationConverter + AuthenticationManager/Provider` để tách parsing, verification, principal mapping và failure handling; hữu ích cho nhiều key types/tenant.
- Gateway/workload identity nếu trust boundary được xác minh chặt và không tin bừa header do client gửi.

Custom filter chỉ nên cấp `Authentication` **sau khi** key đã được server kiểm chứng; không đưa `X-Role` hoặc `X-Tenant` tự khai thành authorities. Đặt filter vào đúng security chain, không đăng ký trùng như servlet filter độc lập.

### 8.2. OAuth2 opaque token: tích hợp có sẵn

Mẫu cấu hình **độc lập** (không ghép trực tiếp vào class demo API key phía dưới):

~~~java
@Bean
SecurityFilterChain opaqueSecurity(HttpSecurity http) throws Exception {
    return http
        .sessionManagement(s -> s
            .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/public/ping").permitAll()
            .requestMatchers("/api/**").hasAuthority("SCOPE_invoice.read")
            .anyRequest().denyAll())
        .oauth2ResourceServer(oauth -> oauth
            .opaqueToken(Customizer.withDefaults()))
        .build();
}
~~~

Đoạn này cần đặt trong `@Configuration` với các import cần thiết, dependency `spring-boot-starter-oauth2-resource-server`, authorization server hỗ trợ introspection và credentials của resource server. Ví dụ cấu hình property:

~~~properties
spring.security.oauth2.resourceserver.opaquetoken.introspection-uri=https://issuer.example/oauth2/introspect
spring.security.oauth2.resourceserver.opaquetoken.client-id=api-resource-server
spring.security.oauth2.resourceserver.opaquetoken.client-secret=REPLACE_WITH_SECURE_SECRET_SOURCE
~~~

Các giá trị trên là **ký hiệu**, không phải server/credential hoạt động. Không commit client secret thật. Introspection trả metadata và scopes; Spring Security có convention ánh xạ scopes thành `SCOPE_...`, nhưng cần kiểm tra mappings, issuer/tenant/resource binding. `active=true` không đủ để cho phép mọi API.

### 8.3. JWT access token: Resource Server và validators

Mẫu cấu hình **biến thể độc lập**:

~~~java
@Bean
SecurityFilterChain jwtSecurity(HttpSecurity http) throws Exception {
    return http
        .sessionManagement(s -> s
            .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/public/ping").permitAll()
            .requestMatchers("/api/**").hasAuthority("SCOPE_invoice.read")
            .anyRequest().denyAll())
        .oauth2ResourceServer(oauth -> oauth
            .jwt(Customizer.withDefaults()))
        .build();
}
~~~

Đặt trong class cấu hình Spring với import `HttpSecurity`, `SecurityFilterChain`, `SessionCreationPolicy`, `Customizer` và `@Bean`; cần starter OAuth2 Resource Server và issuer/trusted keys thật.

Ví dụ property:

~~~properties
spring.security.oauth2.resourceserver.jwt.issuer-uri=https://issuer.example/realms/demo
~~~

**Không xem issuer-uri là đủ để tự động áp audience nghiệp vụ đúng trong mọi phiên bản.** Phải cấu hình kiểm tra `aud` cho API và token purpose/type theo policy. Ví dụ một bean `JwtDecoder` tạo validators cho issuer và audience (chỉ là mảnh code minh họa):

~~~java
@Bean
JwtDecoder jwtDecoder() {
    String issuer = "https://issuer.example/realms/demo";
    String jwks = "https://issuer.example/realms/demo/jwks";

    NimbusJwtDecoder decoder =
        NimbusJwtDecoder.withJwkSetUri(jwks).build();

    OAuth2TokenValidator<Jwt> base =
        JwtValidators.createDefaultWithIssuer(issuer);

    OAuth2TokenValidator<Jwt> audience = token ->
        token.getAudience().contains("invoice-api")
            ? OAuth2TokenValidatorResult.success()
            : OAuth2TokenValidatorResult.failure(
                new OAuth2Error("invalid_token",
                    "Wrong audience", null));

    decoder.setJwtValidator(
        new DelegatingOAuth2TokenValidator<>(base, audience));

    return decoder;
}
~~~

Đoạn này cần các import `Jwt`/`JwtDecoder`/`NimbusJwtDecoder`/`JwtValidators`, `OAuth2TokenValidator`, `OAuth2TokenValidatorResult`, `DelegatingOAuth2TokenValidator` và `OAuth2Error`. Chỉ dùng JWKS URL đã được xác định từ issuer tin cậy, validate JWS algorithm, access token purpose và tenant theo yêu cầu. **Không dùng URI ví dụ cho hệ thống thật.**

### 8.4. Nhiều SecurityFilterChain

Khi một ứng dụng dùng API key cho `/integrations/**` và OAuth2 cho `/user/**`, có thể dùng các bean chain có `@Order` và `securityMatcher` tương ứng. Phải có fallback policy cho các URL ngoài matcher. **Chain đầu tiên khớp request được chọn**; `anyRequest()` bên trong chain chỉ bao phủ request đã vào chain đó. Không dựa vào một token hợp lệ ở endpoint A để tự cho phép endpoint B.

## 9. Ví dụ chạy được Java 17: API key custom filter

Để người học thấy rõ việc **trước verify chỉ có secret tự khai, sau verify mới được gắn authority**, phần này xây dựng một Spring Boot MVC application nhỏ:

- `GET /public/ping`: public, trả 200.
- `GET /api/data`: thiếu hoặc sai API key trả 401; key hợp lệ trả 200.
- Scope `SCOPE_data.read` được **server tạo sau khi** so digest của API key.
- Demo stateless theo request, không phát session login hoặc access token.
- Key có trong property chỉ để chạy local, **không phải cách lưu API key production**.

Đối với opaque/JWT, mã mục 8 cần authorization server hoặc signing keys và các test bổ sung; không giả vờ rằng chỉ thay HTTP header là đã có token thật.

### 9.1. Cấu trúc thư mục

~~~text
api-key-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/example/apikey/
    │   │   ├── ApiKeyDemoApplication.java
    │   │   ├── ApiKeySecurityConfiguration.java
    │   │   ├── ApiKeyFilter.java
    │   │   └── ApiController.java
    │   └── resources/application.properties
    └── test/java/example/apikey/
        └── ApiKeyIntegrationTests.java
~~~

Tệp `settings.gradle`:

~~~groovy
rootProject.name = 'api-key-demo'
~~~

Tệp `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Tệp `src/main/resources/application.properties`:

~~~properties
# Chỉ cho lab local; không dùng ở production.
demo.api-key=local-demo-only-secret-not-for-real-use
~~~

Key minh họa không đại diện cho secret ngẫu nhiên cấp trong production. Hệ thống thật cần CSPRNG, key id và hash key lưu trong DB/key store, source secret từ secret manager và rotation.

### 9.2. Class khởi động

Tệp `src/main/java/example/apikey/ApiKeyDemoApplication.java`:

~~~java
package example.apikey;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ApiKeyDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ApiKeyDemoApplication.class, args);
    }
}
~~~

### 9.3. ApiKeyFilter

Tệp `src/main/java/example/apikey/ApiKeyFilter.java`:

~~~java
package example.apikey;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.List;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.filter.OncePerRequestFilter;

public class ApiKeyFilter extends OncePerRequestFilter {

    private static final String HEADER = "X-API-Key";
    private final byte[] expectedDigest;

    public ApiKeyFilter(String configuredKey) {
        this.expectedDigest = digest(configuredKey);
    }

    @Override
    protected boolean shouldNotFilter(HttpServletRequest request) {
        String path = request.getRequestURI()
            .substring(request.getContextPath().length());
        return !"/api/data".equals(path);
    }

    @Override
    protected void doFilterInternal(HttpServletRequest request,
                                    HttpServletResponse response,
                                    FilterChain chain)
            throws ServletException, IOException {

        String candidate = request.getHeader(HEADER);
        if (candidate == null || candidate.isBlank()) {
            // Không có key: rule authorization sẽ từ chối.
            chain.doFilter(request, response);
            return;
        }

        if (candidate.length() > 256
                || !MessageDigest.isEqual(
                    digest(candidate), expectedDigest)) {
            response.sendError(HttpServletResponse.SC_UNAUTHORIZED);
            return;
        }

        // Đã so khớp server-side: lúc này mới cấp identity và scope.
        var verified = new UsernamePasswordAuthenticationToken(
            "demo-client",
            null,
            List.of(new SimpleGrantedAuthority("SCOPE_data.read")));

        SecurityContext context =
            SecurityContextHolder.createEmptyContext();
        context.setAuthentication(verified);
        SecurityContextHolder.setContext(context);

        try {
            chain.doFilter(request, response);
        } finally {
            SecurityContextHolder.clearContext();
        }
    }

    private static byte[] digest(String value) {
        try {
            MessageDigest sha256 =
                MessageDigest.getInstance("SHA-256");
            return sha256.digest(
                value.getBytes(StandardCharsets.UTF_8));
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException("SHA-256 unavailable", e);
        }
    }
}
~~~

Trong ví dụ, `MessageDigest.isEqual` dùng để so digest; production cần xử lý duplicate headers, kiểm tra trạng thái/expiry/scope của key và logging redaction. Việc bảo vệ password người dùng **không** dùng công thức SHA-256 đơn thuần này.

`UsernamePasswordAuthenticationToken` ba tham số là authenticated token; vì thế chỉ được tạo **sau khi** verify key. Đừng dùng ba tham số trong converter nhận thẳng dữ liệu client để tự cấp role. `SecurityContextHolder` phải được clear theo request; ở đây filter dùng `finally`, đồng thời framework cũng quản lý lifecycle trong filter chain.

### 9.4. Cấu hình security filter chain

Tệp `src/main/java/example/apikey/ApiKeySecurityConfiguration.java`:

~~~java
package example.apikey;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;

@Configuration
public class ApiKeySecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http, Environment environment)
            throws Exception {

        ApiKeyFilter keyFilter = new ApiKeyFilter(
            environment.getRequiredProperty("demo.api-key"));

        return http
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/public/ping")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/api/data")
                    .hasAuthority("SCOPE_data.read")
                .anyRequest().denyAll())
            .exceptionHandling(ex -> ex
                .authenticationEntryPoint((request, response, error) ->
                    response.sendError(401)))
            .addFilterBefore(
                keyFilter, UsernamePasswordAuthenticationFilter.class)
            .build();
    }
}
~~~

Chỉ dùng GET endpoints nên demo **không cần tắt CSRF**. Khi thêm POST, phải đánh giá cách client gửi credential và liệu cookie/session tự gắn có tạo CSRF risk hay không. Không tắt CSRF mặc định cho toàn hệ thống dựa vào tên “API”.

Filter được tạo **bên trong phương thức build chain**, không khai báo `@Component` hay `@Bean` độc lập: điều này tránh Spring Boot tự đăng ký thêm một Servlet Filter ngoài Spring Security chain gây double execution. Nếu cần inject filter bean trong dự án lớn, kiểm soát auto-registration.

### 9.5. Controller

Tệp `src/main/java/example/apikey/ApiController.java`:

~~~java
package example.apikey;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ApiController {

    @GetMapping("/public/ping")
    public String ping() {
        return "pong";
    }

    @GetMapping("/api/data")
    public String data() {
        return "secured-data";
    }
}
~~~

Controller không tự kiểm tra `X-API-Key`; việc xác minh và phân quyền phải xảy ra ở security chain.

### 9.6. MockMvc integration tests

Tệp `src/test/java/example/apikey/ApiKeyIntegrationTests.java`:

~~~java
package example.apikey;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ApiKeyIntegrationTests {

    @Autowired
    MockMvc mockMvc;

    @Test
    void publicEndpointIsAvailable() throws Exception {
        mockMvc.perform(get("/public/ping"))
            .andExpect(status().isOk())
            .andExpect(content().string("pong"));
    }

    @Test
    void missingKeyIsDenied() throws Exception {
        mockMvc.perform(get("/api/data"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void wrongKeyIsDenied() throws Exception {
        mockMvc.perform(get("/api/data")
                .header("X-API-Key", "wrong"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void matchingKeyCanAccessData() throws Exception {
        mockMvc.perform(get("/api/data")
                .header("X-API-Key",
                    "local-demo-only-secret-not-for-real-use"))
            .andExpect(status().isOk())
            .andExpect(content().string("secured-data"));
    }
}
~~~

Các tests kiểm tra public/missing/invalid/valid API key qua Spring Security filters. Không diễn giải chúng như bằng chứng JWT signature validation hoặc opaque introspection hoạt động. Với OAuth2 variants cần test riêng decoder/introspector thật hoặc mocked có kiểm soát, issuer/audience/scope và service failure.

### 9.7. Lệnh chạy và HTTP mẫu

Với Gradle và Java 17:

~~~bash
gradle test
gradle bootRun
~~~

Nếu có wrapper, dùng `./gradlew test` và `./gradlew bootRun` (Windows: `gradlew.bat`). Các class phụ thuộc Spring libraries nên `javac/java` trần không đủ nếu thiếu classpath.

Thử ở localhost khi server chạy cổng mặc định:

~~~bash
curl -i http://localhost:8080/public/ping
curl -i http://localhost:8080/api/data
curl -i -H 'X-API-Key: wrong' http://localhost:8080/api/data
curl -i -H 'X-API-Key: local-demo-only-secret-not-for-real-use' \
  http://localhost:8080/api/data
~~~

Bảng kết quả theo cấu hình demo:

| Request | Status | Body nếu thành công |
| --- | --- | --- |
| GET public không key | 200 | `pong` |
| GET private không key | 401 | Không cố định body lỗi |
| GET private sai key | 401 | Không cố định body lỗi |
| GET private đúng key | 200 | `secured-data` |

Không dùng key mẫu này cho môi trường thật, không chia sẻ key thật qua shell history/logs. Chỉ dùng HTTP không TLS cho demo localhost.

## 10. Cách kiểm thử OAuth2 opaque/JWT ngoài ví dụ API key

### 10.1. JWT authorization test và decoder test là hai mức khác nhau

Spring Security Test có `jwt()` request post-processor để gắn JwtAuthenticationToken giả trong MockMvc, hữu ích kiểm tra route/scope policy. Ví dụ **mảnh code** (không phải class test hoàn chỉnh):

~~~java
mockMvc.perform(get("/api/invoices")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_invoice.read"))))
    .andExpect(status().isOk());

mockMvc.perform(get("/api/invoices")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_unrelated"))))
    .andExpect(status().isForbidden());
~~~

Cần endpoint/chain tương ứng và imports của Spring Security Test/JUnit. **Hai test này không xác minh chữ ký thật**: `jwt()` mock helper đã cung cấp Authentication cho test. Muốn kiểm thử security end-to-end, phải có tests với JwtDecoder, key/certificate fixtures và các token sai signature, hết hạn, sai issuer, sai audience, sai token purpose.

### 10.2. Opaque introspection tests

Kiểm thử quan trọng gồm:

- Token không tồn tại hoặc inactive → request không được chấp nhận.
- Introspection active nhưng scope không đủ → 403.
- Introspection active và scope đúng → controller chạy.
- Introspection endpoint timeout hoặc lỗi HTTP → **không fail-open**.
- Introspection trả tenant/client/subject không phù hợp → authorization từ chối.
- Cache introspection TTL và revocation window phù hợp policy.

Có thể mock `OpaqueTokenIntrospector` cho unit/integration tests kiểm tra mapping, nhưng cũng cần contract/integration testing với authorization server thực hoặc test double tuân thủ chuẩn.

### 10.3. 401 khác 403

| Trường hợp | Status thường gặp | Ý nghĩa |
| --- | --- | --- |
| Không có bearer access token | 401 | Chưa có credential cho endpoint protected |
| JWT sai chữ ký, expired hoặc audience sai | 401 | Authentication bị từ chối |
| Opaque token inactive | 401 | Token không hợp lệ |
| API key sai | 401 (theo demo) | Xác minh key thất bại |
| Credential hợp lệ nhưng scope thiếu | 403 | Authorization không đủ |
| Introspection endpoint lỗi mạng | Theo handling, không được cho qua | Có thể là lỗi hạ tầng, không giống invalid token |
| POST bị CSRF từ chối | 403 có thể xảy ra | Không nhất thiết là thiếu scope |

Entry point, bearer challenge và filter chain config có thể thay đổi chi tiết response. Phải test cả authentication lẫn authorization, không chỉ một status.

## 11. Thu hồi, caching, key rotation và quyền động

### 11.1. Câu hỏi về thời điểm thu hồi

Giả sử admin khóa client lúc **14:00**. Bạn muốn resource server từ chối request tiếp theo ngay lập tức hay chấp nhận một cửa sổ tối đa vài phút?

- API key có state trong DB có thể bị vô hiệu khi verifier đọc trạng thái mới. Nếu cache key, cần invalidation hoặc TTL rõ ràng.
- Opaque introspection không cache có thể cập nhật trạng thái theo issuer ngay request sau, nhưng phụ thuộc availability/latency.
- Signed JWT verify offline có thể còn hợp lệ đến `exp`. Nếu cần phản ánh revoke nhanh, bổ sung denylist, introspection, short TTL hoặc policy state checks.

**Revocation là đặc tính của cơ chế kiểm chứng và cache**, không phải phép màu đến từ tên “opaque” hoặc “JWT”.

### 11.2. Rotation

- API key: cấp key mới, cho phép cùng lúc key mới/cũ trong một cửa sổ ngắn nếu có lý do, báo client đổi và vô hiệu key cũ.
- Opaque token: token issuer quản lý signing/opaque token store và rotation/expiry riêng; resource server cần cập nhật introspection credentials khi rotate.
- JWT: issuer rotate signing key; resource servers cập nhật JWKS cache theo chính sách, vẫn nhận token còn hiệu lực được ký bằng key cũ trong thời gian chuyển tiếp hợp lệ.

Đừng deploy rotation xóa tất cả verifier/keys cũ trước khi xem xét token còn sống hoặc đường rollback.

### 11.3. Claims và scope bị lỗi thời

Một user bị bỏ quyền admin sau khi JWT được phát. Nếu resource server chỉ đọc authority từ signed token, quyền có thể còn tồn tại tới lúc token hết hạn. Nếu business không chấp nhận, phải xác minh quyền động hoặc rút ngắn thời hạn token. Cách tương tự áp dụng cho API key metadata và opaque introspection **nếu có cache**.

## 12. Multi-tenant, browser và môi trường vận hành

### 12.1. Tenant boundary

Một API key có `tenant_id=A`, JWT chứa claim `tenant=A` hoặc introspection trả tenant A không được dùng cho request `/tenants/B/orders`. Token có thể hợp lệ nhưng **resource ownership/tenant authorization** phải từ chối. Đừng tin header `X-Tenant: B` như bằng chứng quyền truy cập B.

### 12.2. Token trong cookie và CSRF

CSRF liên quan **ambient credentials** browser tự gửi, điển hình session cookie. Nếu JWT nằm trong cookie tự gửi, việc “JWT là stateless” **không** tự xóa rủi ro CSRF. Ngược lại, bearer token chỉ gửi qua Authorization header do client chủ động đính kèm có threat model khác. Cần đánh giá cả CSRF, SameSite, CORS, XSS và token storage theo client thực tế.

### 12.3. Log, monitoring và sự cố

Không log raw API key, Authorization header, token nguyên vẹn, introspection client secret, signing private keys hoặc JWT claims nhạy cảm. Có thể dùng key id, client id đã xác minh, request correlation id, auth mechanism, error category, route và status với privacy policy phù hợp. Cần kế hoạch incident response: xác định credential bị lộ, khóa key/token, rotate signing keys khi cần và đo blast radius.

### 12.4. Rate limiting

Một API key dài hạn bị đánh cắp có thể được dùng với tốc độ rất lớn. JWT/opaque bearer token bị lộ cũng vậy. Rate limiting nên xét client id, tenant, scope, IP và đường đi; không dùng quota thay thế việc kiểm chứng credential. Với introspection, giám sát request volume và timeouts để tránh gây quá tải authorization server.

## 13. Sai lầm cần tránh

| Sai lầm | Vì sao sai | Hướng đúng |
| --- | --- | --- |
| API key luôn “kém bảo mật” hơn JWT | Bảo mật phụ thuộc lifecycle/entropy/scopes/verification | So threat model và quản trị credential |
| JWT decode được nên tin được | Payload chưa verify có thể bị giả | Verify chữ ký/claims trước khi tạo Authentication |
| JWT ký hợp lệ có thể dùng cho mọi API | `aud`/purpose có thể khác | Kiểm tra audience, type và issuer |
| Dùng ID token gọi resource API | Token confusion | Dùng access token dành đúng API |
| Opaque `active=true` tức là full access | Authorization vẫn cần scope/resource/tenant | Kiểm tra đủ quyền sau introspection |
| Introspection timeout thì cho qua | Fail-open | Từ chối và xử lý lỗi hạ tầng |
| Cache token state vô thời hạn | Revocation không phản ánh | TTL/invalidation được phê duyệt |
| Key lưu plaintext | DB leak có thể dùng key | Hash key entropy cao, key id/rotation |
| Client gửi `X-Role: ADMIN` để cấp quyền | Authority không đáng tin | Scope từ server/issuer đã kiểm chứng |
| Nhúng API key vào frontend bundle | Người dùng có thể lấy secret | OAuth2 public client flow/BFF phù hợp |
| Cho JWT payload chứa password/PII | JWS thường đọc được | Claim tối thiểu, mã hóa khi cần |
| Dùng một HMAC secret cho mọi resource server | Shared signing secret tăng blast radius | Đánh giá asymmetric key/JWKS |
| Tự code JWT parser/crypto | Dễ sai algorithms/validators | Spring Resource Server + JwtDecoder |
| Quên fallback chain | Request không khớp có thể thiếu security | Test matchers/chain coverage |
| Tắt CSRF chỉ vì tên “API/JWT” | Browser vẫn có thể gửi cookie tự động | Đánh giá ambient credentials |
| Chỉ test `jwt()` mocked | Chưa chứng minh verify signature | Test decoder/introspection thật |

## 14. Bài tập tự kiểm tra

1. API key có thể là opaque string không? Vì sao API key và opaque token không phải hai “định dạng loại trừ nhau”?
2. OAuth2 bearer token trong Authorization header có chắc là JWT không?
3. Resource server chỉ decode JWT và thấy `ROLE_ADMIN`, chưa verify chữ ký. Vì sao không thể cho request đi qua?
4. JWT đúng chữ ký và chưa hết hạn nhưng `aud` dành cho resource khác. Hệ thống phải làm gì?
5. Một dịch vụ cần revoke access gần thời gian thực nhưng đang dùng offline JWT 30 phút. Nêu các trade-off và giải pháp.
6. Opaque token introspection có cache 10 phút. Khi revoke token, cửa sổ cache ảnh hưởng thế nào?
7. Thiết kế API key cho 10 đối tác: key id, secret, scopes, tenant, rotate, quota, audit và monitoring.
8. Vì sao hash API key entropy cao có thể dùng SHA-256 nhưng password người dùng không nên dùng SHA-256 đơn thuần?
9. Trong ví dụ, vì sao `UsernamePasswordAuthenticationToken` authenticated chỉ được tạo sau khi verify key?
10. Nếu client gửi API key hợp lệ nhưng `X-Tenant: B` trong khi key chỉ thuộc tenant A, authorization phải làm gì?
11. `jwt()` MockMvc post-processor chứng minh được điều gì và không chứng minh được điều gì?
12. Giải thích sự khác nhau giữa `securityMatcher` và `authorizeHttpRequests.requestMatchers`.
13. Nếu một JWT nằm trong cookie, có thể tắt CSRF chỉ vì “JWT stateless” không?
14. Resource server chọn đúng issuer nhưng quên audience validator có nguy cơ gì?
15. Khi JWT signing key rotate, cần xử lý token đang sống và JWKS cache thế nào?
16. Nếu opaque introspection endpoint bị downtime, có được “tạm cho token cũ qua” không? Chính sách nào cần thiết?
17. Một user bị khóa nhưng role trong JWT chưa hết hạn; cách nào giúp quyền động được áp dụng?
18. Chọn API key, opaque OAuth2 token, signed JWT cho ba hệ thống: ERP integration, nhiều microservices, ứng dụng ủy quyền truy cập dữ liệu user. Đưa ra tiêu chí chứ không chỉ nêu tên.

## 15. Checklist trước khi triển khai production

- [ ] Định nghĩa chủ thể thật (user, client, service, integration) và ai có quyền phát credential.
- [ ] HTTPS bắt buộc; không gửi secret qua URL/query hoặc log.
- [ ] API key entropy cao, key id, hash store, scopes, expiry, rotate và thu hồi.
- [ ] Không nhúng secret API key vào browser/mobile public.
- [ ] Opaque token có introspection/token store, timeout và fail-closed, cache TTL phù hợp revoke.
- [ ] JWT được verify signature + thuật toán + issuer + audience + lifetime + token purpose.
- [ ] Chỉ tin scopes/roles/tenant từ token/key đã xác minh và áp dụng authorization theo resource.
- [ ] Có chiến lược cập nhật quyền động và revoked token, maximum staleness đã định.
- [ ] JWKS/signing key rotation hoặc introspection secret rotation được thử nghiệm.
- [ ] Không dùng ID token như access token; không tự viết crypto.
- [ ] Có rate limiting, monitoring, audit và incident response.
- [ ] Không log token/header Authorization/secret nguyên văn.
- [ ] Ranh giới nhiều SecurityFilterChain không tạo đường bypass.
- [ ] Cookie/CSRF/CORS/XSS được đánh giá theo cách client thật gửi credential.
- [ ] Có tests 401/403, missing/invalid key, wrong audience, expired/revoked token, cross-tenant.
- [ ] Có kế hoạch migration/rollback nếu đổi từ API key sang OAuth2 hoặc đổi token format.

## 16. Kết luận

**API key** nói chủ yếu về credential được cấp cho integration và vòng đời riêng của nó. **Opaque token** nói về quyền kiểm chứng dựa trên nguồn trạng thái/introspection thay vì tự đọc token. **JWT** nói về định dạng có claims, thường được ký để resource server xác minh cục bộ; nó không tự giải quyết revocation, quyền động hay token-purpose validation.

Hãy chọn mô hình dựa trên **ai là principal, ai là issuer, nguồn nào xác minh credential, yêu cầu thu hồi nhanh đến đâu, có bao nhiêu resource servers, scopes và tenant được kiểm soát thế nào**. Khi đã rõ các câu hỏi đó, Spring Security Servlet có hướng tích hợp tự nhiên: custom API-key filter/provider cho key tự quản lý, `opaqueToken` introspection cho opaque OAuth2 access token, hoặc `jwt` resource server cùng JwtDecoder/claim validators cho signed JWT access token.
