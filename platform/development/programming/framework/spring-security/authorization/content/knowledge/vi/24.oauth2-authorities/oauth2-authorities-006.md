# Audience, issuer và tiền điều kiện trước khi dùng claim cấp quyền

> **Chủ đề:** Spring Security – authorization → **Quyền từ OAuth2**. Bài học làm rõ cách một OAuth2 Resource Server quyết định JWT access token **đáng tin để đọc quyền hay chưa**: kiểm chữ ký và thuật toán, issuer (`iss`), audience (`aud`), thời gian (`exp`/`nbf`), **loại token** (`typ`), client và các claim bắt buộc trước khi ánh xạ `scope`/`scp`/`roles` thành Spring Security authorities. Có mô hình đe dọa, cách cấu hình Spring Security 6.x/Boot 3.x, demo Java 17+ với RSA ký JWT thật trong môi trường test, kiểm thử 401/403, lưu ý multi-tenant, opaque token, troubleshooting và bài tập.

## 1. Nguyên tắc: claim chỉ có ý nghĩa sau khi token được chấp nhận cho đúng API

Một JWT nhìn giống:

~~~text
header.payload.signature
~~~

Chỉ vì có thể Base64URL-decode `payload` và thấy:

~~~json
{
  "iss": "https://login.example.invalid/realms/demo",
  "aud": ["urn:ledger-api"],
  "sub": "alice",
  "scope": "ledger.read ledger.write",
  "exp": 1924992000
}
~~~

**không có nghĩa** user đã có quyền đọc/sửa sổ cái. Payload JWT ở bước decode là dữ liệu **do người gửi cung cấp**; trước khi xác minh chữ ký và các ràng buộc sử dụng token, mọi `scope`/`roles`/`tenant` chỉ là lời tự khai.

Một quyết định đúng gồm **hai cổng**, theo thứ tự:

~~~text
Authorization: Bearer <token>
               |
               v
GATE A: TOKEN VALIDATION / AUTHENTICATION
 - đúng định dạng và token type?
 - chữ ký hợp lệ với public key từ issuer tin cậy?
 - thuật toán thuộc allowlist?
 - issuer chính xác?
 - audience chứa resource API hiện tại?
 - exp, nbf, iat, các claim bắt buộc hợp lệ?
 - client/grant/tenant theo profile nếu có?
               |
       FAIL --> 401 invalid_token
               |
              PASS
               v
GATE B: AUTHORIZATION
 - claim scope/roles đã được ánh xạ đúng chưa?
 - operation cần authority nào?
 - subject có quyền với đúng tenant/object không?
 - membership/entitlement hiện hành có cho phép không?
               |
       FAIL --> 403 insufficient_scope/forbidden
               |
              PASS
               v
          BUSINESS OPERATION
~~~

**Không bao giờ thực hiện Gate B bằng cách tự parse claim từ token chưa qua Gate A.** Một access token có scope rất mạnh nhưng được cấp cho *API khác* vẫn phải bị từ chối tại audience validation trước khi phân quyền.

## 2. Phân biệt OAuth2 access token, ID token và JWT

| Thuật ngữ | Dùng để làm gì? | Người nhận dự kiến |
| --- | --- | --- |
| **OAuth2 access token** | Chứng từ ủy quyền truy cập resource | Resource Server/API (`aud` hướng tới API) |
| **OIDC ID token** | Khẳng định authentication event và user identity cho client | Relying party/OIDC client (`aud` thường là client ID) |
| **Refresh token** | Dùng với Authorization Server để lấy access token mới | Authorization Server, không đưa trực tiếp vào API |
| **JWT** | Một định dạng token (JWS/JWE), có thể dùng cho nhiều mục đích | Không xác định mục đích chỉ bằng việc nhìn ba đoạn |
| **Opaque access token** | Chuỗi tham chiếu không tự có claim đọc được | Resource Server thường introspect qua nơi tin cậy |

**JWT không đồng nghĩa OAuth2 access token.** Một token có chữ ký hợp lệ vẫn có thể là **ID token**, logout token hoặc token dành cho dịch vụ khác. Việc tái sử dụng nhầm loại token gọi là **token substitution / token confusion**.

Với profile JWT access token của **RFC 9068**, `typ` trong JOSE header phải là `at+jwt` hoặc `application/at+jwt` khi resource server xác minh token theo profile này. Không chỉ dựa vào việc token có trường `scope` hoặc `sub`.

### 2.1. Một token giả định đúng mục tiêu

~~~json
{
  "header": {
    "alg": "RS256",
    "typ": "at+jwt",
    "kid": "training-key-1"
  },
  "claims": {
    "iss": "https://issuer.example.invalid/tenant-a",
    "sub": "user-17",
    "aud": ["urn:ledger-api"],
    "client_id": "console-client",
    "scope": "ledger.read",
    "iat": 1910000000,
    "nbf": 1910000000,
    "exp": 1910000300,
    "jti": "token-001"
  }
}
~~~

Đây là **cấu trúc minh họa**, không phải JWT compact thật và không có chữ ký thật. Các mốc thời gian chỉ để minh họa quan hệ `iat/nbf/exp`; không dùng token mẫu trong request production. Trong test chạy được ở phần sau, `iat` và `exp` được tính động quanh thời điểm hiện tại.

### 2.2. Claims không thay thế kiểm tra nghiệp vụ

Ngay cả sau khi JWT hợp lệ:

~~~text
Token: sub=alice, aud=ledger-api, scope=ledger.read
Request: GET /api/tenants/beta/ledger/202
Membership DB: alice thuộc tenant acme
Resource DB: ledger#202 thuộc beta
=> DENY
~~~

`scope=ledger.read` chứng minh token được cấp loại quyền này **trong miền ý nghĩa mà Authorization Server và API thống nhất**; nó không tự cho quyền trên mọi bản ghi hoặc mọi tenant.

## 3. Kiểm tra `iss`: ai đã phát token?

`iss` (issuer) là định danh của thực thể phát JWT. Trong OAuth2, Resource Server phải có **tập issuer được tin cậy** từ cấu hình/quản trị, không tạo lòng tin theo URL do JWT tự khai.

Ví dụ cấu hình API kỳ vọng:

~~~text
TRUSTED_ISSUER=https://issuer.example.invalid/tenant-a
~~~

| `iss` trong JWT | Kết quả |
| --- | --- |
| `https://issuer.example.invalid/tenant-a` | Khớp điều kiện issuer |
| `https://issuer.example.invalid/tenant-b` | DENY: issuer tenant khác |
| `https://issuer.example.invalid/tenant-a/` | Không khớp nếu issuer chuẩn không có dấu slash cuối |
| `http://issuer.example.invalid/tenant-a` | Không khớp protocol |
| `https://issuer.example.invalid/tenant-A` | Không khớp chữ hoa/thường |
| Không có `iss` | DENY với profile yêu cầu issuer |

Issuer identifier cần so sánh theo định danh được cấu hình, **không** chỉ dùng `contains("example.invalid")`, `startsWith(...)` hoặc so domain sau khi tự bỏ segment. Với một API tin nhiều issuer, cách chọn decoder/public keys phải lấy từ **allowlist issuer**.

### 3.1. Issuer và discovery/JWKS

Authorization Server thường công bố OAuth2 Authorization Server Metadata hoặc OpenID Connect Discovery:

~~~text
Known issuer
    |
    v
Trusted metadata endpoint
    |
    v
JWK Set URI do metadata đáng tin công bố
    |
    v
Verifier lấy public keys + algorithm được hỗ trợ
    |
    v
Token signature + iss validation
~~~

Resource Server cần tin **cặp** issuer và key set, không chỉ nhận token có một địa chỉ issuer nhìn hợp lệ. `iss` nằm trong JWT **chưa verify** không thể tự định nghĩa nơi API sẽ tải key về.

**Rủi ro nghiêm trọng:** code đọc `iss` từ token rồi gọi `JwtDecoders.fromIssuerLocation(iss)` cho mọi issuer do client gửi có thể biến một issuer của kẻ tấn công thành nơi cấp token được chấp nhận. Mô hình multi-issuer phải xác minh issuer trong danh sách trusted trước khi khởi tạo decoder cho issuer đó. Điều này cũng hạn chế SSRF qua URL/metadata chưa được phép.

### 3.2. Khi chuyển môi trường

`dev`, `staging` và `production` thường dùng issuer khác nhau. Không tạo một validator “nếu issuer chứa company domain thì được” để token dev hoạt động trên production. Mỗi môi trường có cấu hình issuer, audience, algorithms và trust material riêng; dùng tests để ngăn token của môi trường khác bị nhận nhầm.

### 3.3. Tenant ID không đồng nghĩa issuer

Một tổ chức có thể có:
- Một issuer phục vụ nhiều tenants; tenant nằm trong membership/token claim riêng.
- Một issuer riêng cho từng tenant.
- Một API tin một tập issuer.

Dù mô hình nào, `iss` đúng chỉ chứng minh nguồn cấp token, **không tự chứng minh** caller thuộc tenant trong URL. Tenant claim/membership và resource ownership vẫn cần chốt riêng.

## 4. Kiểm tra `aud`: token này dành cho resource server nào?

`aud` (audience) nhận diện các bên dùng token. Với JWT access token, Resource Server phải xác minh audience chứa **định danh API hiện tại**.

Ví dụ:

~~~text
Ledger API expects: urn:ledger-api
Reports API expects: urn:reports-api
Portal client ID:    console-client
~~~

Alice có thể có một token:

~~~json
{
  "iss": "https://issuer.example.invalid/tenant-a",
  "aud": ["urn:reports-api"],
  "scope": "ledger.read reports.read"
}
~~~

Dù chứa chuỗi `ledger.read`, Ledger API phải **từ chối** vì token hướng tới Reports API, không hướng tới Ledger API.

### 4.1. Audience không phải client ID

| Claim | Câu hỏi |
| --- | --- |
| `aud` | Resource Server/API nào được phép nhận token? |
| `client_id` | OAuth2 client nào nhận/được cấp access token? |
| `azp` | Authorized party theo ngữ nghĩa token/profile tương ứng |
| `sub` | Chủ thể của token theo grant/profile |
| `scope`/`scp` | Quyền được ủy quyền theo API/AS contract |

Một OIDC ID token có `aud=console-client` và có thể chứa `roles` cho giao diện. Ledger API không nên chấp nhận nó như access token chỉ vì cả ID token lẫn access token được ký bởi cùng một identity provider.

### 4.2. `aud` dạng chuỗi hoặc mảng

JWT cho phép audience có thể được biểu diễn dưới dạng JSON string hoặc array; API Spring Security thường cung cấp qua `Jwt.getAudience()` dạng danh sách.

~~~json
{"aud":"urn:ledger-api"}
~~~

Hoặc:

~~~json
{"aud":["urn:reports-api","urn:ledger-api"]}
~~~

Với rule `aud contains urn:ledger-api`, hai dạng trên có thể hợp lệ theo contract. **Đừng** viết `jwt.getClaimAsString("aud").equals(...)` rồi giả định mọi issuer luôn gửi string; cũng đừng match substring như `aud.toString().contains("ledger")`.

Chính sách stricter (chỉ cho một audience duy nhất) có thể là yêu cầu bổ sung, nhưng cần được thỏa thuận với issuer/client và kiểm thử rõ. RFC 9068 yêu cầu audience chứa giá trị resource indicator của resource server nhận token.

### 4.3. Vì sao nhiều audience cần lưu ý?

Một token có audiences rộng hơn làm tăng phạm vi dùng lại token nếu nhiều APIs diễn giải scope giống nhau. Nên cân nhắc:
- Phát access token có audience hẹp tương ứng resource.
- Dùng resource indicator theo RFC 8707 khi Authorization Server hỗ trợ.
- Thiết kế scope gắn namespace rõ (`ledger.read`, `reports.read`).
- Không dùng token của API A để gọi API B chỉ bằng cách forward header.
- Dùng token exchange/on-behalf-of đúng protocol khi call downstream cần audience khác.

**Kết luận:** kiểm issuer mà thiếu audience vẫn có thể chấp nhận một token thật nhưng dành cho **dịch vụ khác**.

## 5. Trước khi tin claim, phải xác minh chữ ký, thuật toán và nguồn key

JWT JWS gồm:

~~~text
base64url(header) . base64url(payload) . base64url(signature)
~~~

Với `RS256`, chữ ký được tạo bằng RSA + SHA-256, resource server xác minh bằng **public key tin cậy** của issuer. Việc decode Base64URL, parse JSON, hoặc gọi `Jwt.getClaim(...)` trên object tự tạo **không xác minh** chữ ký.

### 5.1. Kiểm tra tối thiểu

1. JWT có định dạng hợp lệ, kích thước/header/JSON được giới hạn.
2. `alg` phải thuộc allowlist issuer/API đã tin; **từ chối `none`** và thuật toán không được hỗ trợ.
3. `kid` chỉ là **gợi ý chọn key** trong trusted JWK Set; không phải chứng cứ key đó đáng tin.
4. Public key được lấy từ issuer metadata/JWKS đáng tin hoặc key pin cấu hình.
5. Verify chữ ký theo thuật toán/key type phù hợp.
6. Chỉ sau đó đánh giá `iss`, `aud`, `exp`, `nbf`, `typ` và các claims khác.
7. Chỉ khi validate thành công mới ánh xạ authorities và kiểm permissions.

Không nạp arbitrary `jku`, `x5u` hoặc key URL từ token header do client gửi. Không “tự học” public key của token chưa xác minh. Một `kid` không được tìm thấy trong trusted JWK Set phải gây lỗi xác minh hoặc quy trình refresh key có kiểm soát, **không** tự dùng key từ Internet.

### 5.2. Key rotation

Khi Authorization Server quay vòng khóa, JWKS có thể công bố key mới và giữ key cũ trong khoảng chuyển tiếp. Resource Server cần cơ chế JWKS refresh/cache/timeout đáng tin, nhưng fail closed nếu không thể xác minh chữ ký. Không tắt signature validation vì downtime của identity provider.

### 5.3. Symmetric vs asymmetric

Với `HS256`, Resource Server cần giữ shared secret để verify. Với `RS256`/`ES256`, Resource Server chỉ cần public key, giảm nhu cầu phân phối private signing material. Theo RFC 9068, dùng asymmetric signature được khuyến nghị cho access token. Ví dụ runnable bên dưới chọn **RSA keypair thử nghiệm** và chỉ chia sẻ public key với decoder.

## 6. Thời gian, loại token và các claim bắt buộc

| Trường | Ý nghĩa | Kiểm tra |
| --- | --- | --- |
| `exp` | Thời điểm token hết hạn | Bây giờ phải trước exp (có clock-skew nhỏ có kiểm soát) |
| `nbf` | Not-before | Không chấp nhận quá sớm |
| `iat` | Issued-at | Hợp lệ theo profile, tránh iat vô lý, dùng trong telemetry |
| `jti` | JWT ID | Có thể dùng chống replay/thu hồi theo policy |
| `typ` (JOSE header) | Loại token | RFC 9068 đòi at+jwt hoặc application/at+jwt |
| `iss` | Issuer | Khớp exact trusted issuer |
| `aud` | Audience | Bao gồm API này |
| `client_id` | OAuth2 client ID | Kiểm nếu policy/resource profile yêu cầu |
| `sub` | Subject | Có mặt và được diễn giải đúng |
| `scope` | Delegated scopes | Chỉ dùng sau validation và theo API policy |

RFC 9068 xác định một profile với các claims bắt buộc như `iss`, `exp`, `aud`, `sub`, `client_id`, `iat`, `jti`; `nbf` có thể xuất hiện. Các issuer không theo profile có thể có cấu trúc khác, do đó **chọn contract rõ**. Không gắn validator RFC 9068 lên một issuer cung cấp token format khác rồi tự bỏ các rule khi test đỏ.

### 6.1. Clock skew không phải “gia hạn vô hạn”

Spring Security có `JwtTimestampValidator` với clock skew nhất định để chịu sai số thời gian giữa hệ thống. Giới hạn vài chục giây/phút có thể hợp lý tùy hạ tầng; không tự đặt skew hàng giờ để làm token hết hạn vẫn được chấp nhận.

Test nên dùng token đã hết hạn **rõ ràng vượt clock skew**, không kiểm sát ngưỡng gây flaky vì hệ thống chạy chậm vài giây.

### 6.2. `typ` để tránh token confusion

Một ID token OIDC thường có `typ=JWT` hoặc không có typ bắt buộc theo cùng cách access-token profile. Một Resource Server tuân thủ RFC 9068 phải kiểm `at+jwt`; chỉ nhìn `roles` trong ID token rồi chấp nhận như access token là sai. Trong Spring Security **6.5**, cách cấu hình minh bạch được tài liệu chính thức khuyến nghị:

~~~java
NimbusJwtDecoder decoder = NimbusJwtDecoder
        .withIssuerLocation(issuerUri)
        .validateType(false)
        .build();

decoder.setJwtValidator(
        JwtValidators.createAtJwtValidator()
                .issuer(issuerUri)
                .audience("urn:ledger-api")
                .clientId("console-client")
                .build());
~~~

Đây là **đoạn tích hợp**, `issuerUri` cần đến từ cấu hình tin cậy. `validateType(false)` tắt việc Nimbus áp dụng type validation mặc định và **chuyển trách nhiệm kiểm type sang validator** `createAtJwtValidator()`; không phải là “tắt bảo vệ type hoàn toàn”. API này có trong Spring Security 6.5; khi nâng lên 7.x, kiểm lại cách mặc định xử lý typ/validator.

## 7. Gate A vs Gate B: quyết định 401 hay 403

Sau khi token được xác thực, Spring Resource Server ánh xạ claim `scope`/`scp` thành authorities như `SCOPE_ledger.read` theo quy ước mặc định.

| Trường hợp | Authentication/validation | Authorization | HTTP thường gặp |
| --- | --- | --- | --- |
| Token vắng mặt | Chưa xác thực | Chưa xét | 401 |
| Chữ ký sai | FAIL | Không xét scope | 401 |
| `iss` sai | FAIL | Không xét scope | 401 |
| `aud` không chứa API | FAIL | Không xét scope | 401 |
| `typ` không phải access token profile đã yêu cầu | FAIL | Không xét scope | 401 |
| `exp` quá khứ | FAIL | Không xét scope | 401 |
| Token hợp lệ, không có `ledger.read` | PASS | DENY | 403 |
| Token hợp lệ, có `ledger.read` | PASS | ALLOW với endpoint đọc | 200 nếu business success |
| Token hợp lệ, có scope nhưng object thuộc tenant khác | PASS | DENY object scope | 403/404 theo API policy |

Hệ thống có thể custom error response, nhưng phân biệt logic giữa **invalid token** và **valid token nhưng thiếu quyền** phải rõ. Không trả nội dung dữ liệu hoặc raw claims nhạy cảm trong lỗi 401/403.

## 8. Cấu hình Spring Boot Resource Server cho production

Bài dùng **Servlet Spring MVC** để viết integration tests thật với `MockMvc`. Nếu ứng dụng sử dụng WebFlux, đổi sang `ServerHttpSecurity` và `ReactiveJwtDecoder` tương ứng; không trộn hai stack.

### 8.1. Dependencies

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Spring Boot starter resource server cung cấp phần phụ thuộc cần thiết để verify JWT/JWS. Với non-Boot ứng dụng, cần đúng modules `spring-security-oauth2-resource-server` và `spring-security-oauth2-jose`.

### 8.2. Cấu hình issuer và audience, không tùy tiện bỏ một trong hai

Ví dụ production với issuer được vận hành thật:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.com/realms/prod
          audiences:
            - urn:ledger-api
~~~

Trong Spring Boot 3.x phù hợp, `spring.security.oauth2.resourceserver.jwt.audiences` chỉ rõ audience API kỳ vọng. `issuer-uri` kích hoạt xác minh issuer và khám phá metadata/JWKS tương ứng (tùy cách cấu hình).

**Lưu ý:** đường `https://idp.example.com/realms/prod` chỉ là ví dụ địa chỉ; phải thay bằng issuer thật và xác nhận chính xác định danh issuer từ tài liệu IdP. Không cấu hình IdP chưa có metadata trong môi trường chạy.

### 8.3. Khi dùng explicit decoder

~~~java
@Bean
JwtDecoder jwtDecoder() {
    NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withIssuerLocation(issuerUri)
            .build();
    decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                    JwtValidators.createDefaultWithIssuer(issuerUri),
                    new JwtAudienceValidator("urn:ledger-api")));
    return decoder;
}
~~~

Imports:

~~~java
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.JwtAudienceValidator;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
~~~

**Đây là đoạn tích hợp, không tự chạy:** `issuerUri` phải được cung cấp từ nguồn cấu hình tin cậy. Khi tự khai `JwtDecoder` bean, cần tự chịu trách nhiệm kết hợp đủ issuer/audience/time/type validators; không mặc định mọi property auto-config từ Boot còn tự thêm vào custom decoder. Đừng gọi `setJwtValidator(customAudienceOnly)` làm mất các timestamp/issuer validators.

**Quan trọng:** decoder trên dùng default JWT type contract. Nếu issuer phát **RFC 9068 at+jwt** thì dùng `validateType(false)` + `JwtValidators.createAtJwtValidator()` như mục 6.2/demo bên dưới, **không** chỉ copy một đoạn cấu hình dành cho JWT type khác.

### 8.4. JWT được xác thực rồi mới check scope

~~~java
@Bean
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    return http
            .authorizeHttpRequests(auth -> auth
                    .requestMatchers("/public/ping").permitAll()
                    .requestMatchers(
                            HttpMethod.GET, "/api/ledger/**")
                    .hasAuthority("SCOPE_ledger.read")
                    .requestMatchers(
                            HttpMethod.POST, "/api/ledger/**")
                    .hasAuthority("SCOPE_ledger.write")
                    .anyRequest().denyAll())
            .oauth2ResourceServer(oauth2 ->
                    oauth2.jwt(Customizer.withDefaults()))
            .sessionManagement(session -> session
                    .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .csrf(csrf -> csrf.disable())
            .build();
}
~~~

Imports chính:

~~~java
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;
~~~

`csrf.disable()` ở đây **chỉ** minh họa một API stateless **chỉ dùng Bearer token trong Authorization header**, không dùng browser-auto cookies/Basic auth. Nếu một chain còn dùng cookie/session credentials, đánh giá lại CSRF thay vì tắt vô điều kiện.

## 9. Demo tự chứa: Spring Boot 3.5.x, JWT ký RSA thật trong test

Bài tập chính không liên hệ IdP ngoài Internet: app tạo **RSA keypair tạm trong memory khi khởi động test**, decoder có public key và kiểm đầy đủ `iss`, `aud`, `typ`, `client_id`, timestamp/required claims theo RFC 9068. Test dùng private key tương ứng để ký JWT thật, rồi gửi qua `Authorization: Bearer` tới `MockMvc`.

**Mục đích:** tránh hạn chế của `spring-security-test mockJwt()`. `mockJwt()` rất tốt để test rules `hasAuthority`, nhưng nó **không chứng minh** chữ ký, issuer, audience hay decoder đang validate đúng vì mô phỏng Authentication và bỏ qua quá trình decode token thật.

### 9.1. `settings.gradle`

~~~groovy
rootProject.name = 'oauth2-jwt-trust-lab'
~~~

### 9.2. `build.gradle`

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.6'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo.jwttrust'
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
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

### 9.3. `src/main/java/demo/jwttrust/JwtTrustApplication.java`

~~~java
package demo.jwttrust;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class JwtTrustApplication {
    public static void main(String[] args) {
        SpringApplication.run(JwtTrustApplication.class, args);
    }
}
~~~

### 9.4. `src/main/java/demo/jwttrust/ResourceServerSecurity.java`

~~~java
package demo.jwttrust;

import java.security.GeneralSecurityException;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.interfaces.RSAPublicKey;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableWebSecurity
public class ResourceServerSecurity {

    public static final String ISSUER =
            "https://issuer.example.invalid/tenant-a";
    public static final String AUDIENCE = "urn:ledger-api";
    public static final String CLIENT_ID = "console-client";

    @Bean
    KeyPair demoSigningKeyPair() throws GeneralSecurityException {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);
        return generator.generateKeyPair();
    }

    @Bean
    JwtDecoder jwtDecoder(KeyPair demoSigningKeyPair) {
        NimbusJwtDecoder decoder = NimbusJwtDecoder
                .withPublicKey(
                        (RSAPublicKey) demoSigningKeyPair.getPublic())
                .validateType(false)
                .build();

        decoder.setJwtValidator(
                JwtValidators.createAtJwtValidator()
                        .issuer(ISSUER)
                        .audience(AUDIENCE)
                        .clientId(CLIENT_ID)
                        .build());
        return decoder;
    }

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/public/ping").permitAll()
                        .requestMatchers(
                                HttpMethod.GET, "/api/ledger/entries")
                        .hasAuthority("SCOPE_ledger.read")
                        .requestMatchers(
                                HttpMethod.POST, "/api/ledger/entries")
                        .hasAuthority("SCOPE_ledger.write")
                        .anyRequest().denyAll())
                .oauth2ResourceServer(oauth2 -> oauth2
                        .jwt(Customizer.withDefaults()))
                .sessionManagement(session -> session
                        .sessionCreationPolicy(
                                SessionCreationPolicy.STATELESS))
                // Chỉ vì demo là stateless Bearer header API.
                .csrf(csrf -> csrf.disable())
                .build();
    }
}
~~~

**Đọc cấu hình:**

1. `demoSigningKeyPair` chỉ dành cho môi trường học/test. **Không tạo private signing key bên trong resource server production.** Trong hệ thống thật, Authorization Server giữ private key, Resource Server chỉ lấy public JWKs qua issuer đáng tin.
2. `withPublicKey` chỉ tin RSA public key đã được inject từ Bean; không tải key từ URL mà JWT tự khai.
3. `validateType(false)` giao trách nhiệm `typ` cho `createAtJwtValidator()` để chấp nhận đúng JWT access token RFC 9068 thay vì default JWT type.
4. Validator yêu cầu issuer, audience, client ID và các điều kiện RFC 9068; test sẽ cố ý gửi token đúng chữ ký nhưng sai `iss`/`aud`/`typ`.
5. Authorization URL `GET` đòi `SCOPE_ledger.read`; `POST` đòi `SCOPE_ledger.write`, không đánh đồng hai hành động.
6. Method `jwtDecoder` được Spring Resource Server dùng để xác thực bearer token **trước** khi ánh xạ scope thành authority.
7. Không tạo `JwtAuthenticationConverter` riêng vì default mapping từ `scope` phù hợp bài này.
8. `anyRequest().denyAll()` hạn chế các route chưa định nghĩa.
9. `example.invalid` là miền dành cho tài liệu; app không gọi metadata endpoint vì dùng public key trực tiếp. Không copy issuer này vào production.

### 9.5. `src/main/java/demo/jwttrust/LedgerController.java`

~~~java
package demo.jwttrust;

import java.security.Principal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class LedgerController {

    @GetMapping("/public/ping")
    public String ping() {
        return "pong";
    }

    @GetMapping("/api/ledger/entries")
    public String read(Principal principal) {
        return "read:" + principal.getName();
    }

    @PostMapping("/api/ledger/entries")
    public String write(Principal principal) {
        return "write:" + principal.getName();
    }
}
~~~

Controller cố ý không đụng tới raw JWT hay tự parse scope. Spring Security xác thực và tạo `Authentication`; các rules được thực thi **trước khi controller nhận request**. Controller chỉ trả một chuỗi demo. Trong production, service vẫn cần kiểm quyền theo owner/tenant/resource và authorization cho side effects.

## 10. Integration tests: JWT ký thật, không dùng mockJwt để bỏ qua Gate A

Test thực hiện:
- Tạo claims của JWT access token với `iss`/`sub`/`aud`/`client_id`/`iat`/`jti`/`exp`/`scope`.
- JSON-serialize header/payload và Base64URL encode.
- Dùng private RSA key của **test fixture** để ký bằng `SHA256withRSA` (JWT `RS256`).
- Gửi compact JWT thật vào `Authorization: Bearer`.
- MockMvc chạy Spring Security filter chain, `NimbusJwtDecoder` kiểm chữ ký và các validators.
- Kiểm tra riêng 401 invalid token với 403 valid token nhưng thiếu authority.

### 10.1. `src/test/java/demo/jwttrust/TokenTrustIntegrationTest.java`

~~~java
package demo.jwttrust;

import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.PrivateKey;
import java.security.Signature;
import java.time.Instant;
import java.util.Base64;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.ResultActions;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(classes = JwtTrustApplication.class)
@AutoConfigureMockMvc
class TokenTrustIntegrationTest {

    @Autowired MockMvc mvc;
    @Autowired KeyPair demoSigningKeyPair;
    @Autowired ObjectMapper mapper;

    private static String b64(byte[] bytes) {
        return Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(bytes);
    }

    private Map<String, Object> standardClaims() {
        long now = Instant.now().getEpochSecond();
        Map<String, Object> claims = new LinkedHashMap<>();
        claims.put("iss", ResourceServerSecurity.ISSUER);
        claims.put("sub", "alice");
        claims.put("aud", List.of(ResourceServerSecurity.AUDIENCE));
        claims.put("client_id", ResourceServerSecurity.CLIENT_ID);
        claims.put("scope", "ledger.read");
        claims.put("iat", now - 10);
        claims.put("nbf", now - 10);
        claims.put("exp", now + 300);
        claims.put("jti", UUID.randomUUID().toString());
        return claims;
    }

    private String sign(
            Map<String, Object> claims,
            PrivateKey privateKey,
            String tokenType) throws Exception {

        Map<String, Object> header = Map.of(
                "alg", "RS256",
                "typ", tokenType);

        String signingInput =
                b64(mapper.writeValueAsBytes(header)) + "."
                + b64(mapper.writeValueAsBytes(claims));

        Signature signature = Signature.getInstance("SHA256withRSA");
        signature.initSign(privateKey);
        signature.update(
                signingInput.getBytes(StandardCharsets.US_ASCII));

        return signingInput + "." + b64(signature.sign());
    }

    private String token(Map<String, Object> claims)
            throws Exception {
        return sign(
                claims,
                demoSigningKeyPair.getPrivate(),
                "at+jwt");
    }

    private ResultActions readWith(String compactJwt)
            throws Exception {
        return mvc.perform(get("/api/ledger/entries")
                .header(HttpHeaders.AUTHORIZATION,
                        "Bearer " + compactJwt));
    }

    @Test
    void publicEndpointWorksWithoutToken() throws Exception {
        mvc.perform(get("/public/ping"))
                .andExpect(status().isOk())
                .andExpect(content().string("pong"));
    }

    @Test
    void missingBearerTokenIs401() throws Exception {
        mvc.perform(get("/api/ledger/entries"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void correctIssuerAudienceSignatureTypeAndScopeAreAccepted()
            throws Exception {

        readWith(token(standardClaims()))
                .andExpect(status().isOk())
                .andExpect(content().string("read:alice"));
    }

    @Test
    void issuerFromAnotherTenantRejectedDespiteValidSignature()
            throws Exception {

        Map<String, Object> claims = standardClaims();
        claims.put("iss",
                "https://issuer.example.invalid/tenant-b");

        readWith(token(claims))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void wrongAudienceRejectedDespiteValidReadScope()
            throws Exception {

        Map<String, Object> claims = standardClaims();
        claims.put("aud", List.of("urn:reports-api"));

        readWith(token(claims))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void missingAudienceIsInvalid()
            throws Exception {

        Map<String, Object> claims = standardClaims();
        claims.remove("aud");

        readWith(token(claims))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void multipleAudiencesIncludingThisApiAreAccepted()
            throws Exception {

        Map<String, Object> claims = standardClaims();
        claims.put("aud",
                List.of("urn:reports-api",
                        ResourceServerSecurity.AUDIENCE));

        readWith(token(claims))
                .andExpect(status().isOk());
    }

    @Test
    void tokenWithOrdinaryJwtTypeIsNotAtJwt()
            throws Exception {

        String ordinaryJwt = sign(
                standardClaims(),
                demoSigningKeyPair.getPrivate(),
                "JWT");

        readWith(ordinaryJwt)
                .andExpect(status().isUnauthorized());
    }

    @Test
    void wrongClientIdIsDeniedByThisApiPolicy()
            throws Exception {

        Map<String, Object> claims = standardClaims();
        claims.put("client_id", "different-client");

        readWith(token(claims))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void expiredTokenIsRejected()
            throws Exception {

        Map<String, Object> claims = standardClaims();
        long now = Instant.now().getEpochSecond();
        claims.put("exp", now - 3600);

        readWith(token(claims))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void futureNotBeforeIsRejected()
            throws Exception {

        Map<String, Object> claims = standardClaims();
        long now = Instant.now().getEpochSecond();
        claims.put("nbf", now + 3600);

        readWith(token(claims))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void untrustedSignatureIsRejected()
            throws Exception {

        KeyPairGenerator generator =
                KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);
        KeyPair untrustedKey = generator.generateKeyPair();

        String forged = sign(
                standardClaims(),
                untrustedKey.getPrivate(),
                "at+jwt");

        readWith(forged)
                .andExpect(status().isUnauthorized());
    }

    @Test
    void validTokenWithoutRequiredReadScopeIs403()
            throws Exception {

        Map<String, Object> claims = standardClaims();
        claims.put("scope", "ledger.write");

        readWith(token(claims))
                .andExpect(status().isForbidden());
    }

    @Test
    void validReadTokenDoesNotGrantWrite()
            throws Exception {

        mvc.perform(post("/api/ledger/entries")
                .header(HttpHeaders.AUTHORIZATION,
                        "Bearer " + token(standardClaims())))
                .andExpect(status().isForbidden());
    }

    @Test
    void validWriteTokenIsAcceptedForWrite()
            throws Exception {

        Map<String, Object> claims = standardClaims();
        claims.put("scope", "ledger.write");

        mvc.perform(post("/api/ledger/entries")
                .header(HttpHeaders.AUTHORIZATION,
                        "Bearer " + token(claims)))
                .andExpect(status().isOk())
                .andExpect(content().string("write:alice"));
    }
}
~~~

**Lưu ý kiểm thử:** Java `Signature` với `SHA256withRSA` là phép ký tương ứng JWS `RS256`. Vì test dùng private key **tạm**, mọi chữ ký hợp lệ trong test đều thuộc keypair được bean cung cấp; code **không** minh họa việc lấy private key từ production IdP. Test có một key không được tin để chứng minh decoder thực sự xác minh signature.

### 10.2. Ma trận kết quả

| Case | Chữ ký | `iss` | `aud` | `typ` | Scope | HTTP |
| --- | --- | --- | --- | --- | --- | --- |
| Không token | — | — | — | — | — | 401 |
| Token đúng | OK | Đúng | Chứa API | at+jwt | ledger.read | 200 |
| Issuer tenant khác | OK | Sai | Đúng | at+jwt | ledger.read | 401 |
| Audience reports-api | OK | Đúng | Sai | at+jwt | ledger.read | 401 |
| Thiếu audience | OK | Đúng | Thiếu | at+jwt | ledger.read | 401 |
| Audience gồm reports-api + ledger-api | OK | Đúng | Chứa API | at+jwt | ledger.read | 200 |
| Ordinary typ JWT | OK | Đúng | Đúng | JWT | ledger.read | 401 |
| Client ID không được phép | OK | Đúng | Đúng | at+jwt | ledger.read | 401 |
| Token hết hạn | OK | Đúng | Đúng | at+jwt | ledger.read | 401 |
| Token chưa đến nbf | OK | Đúng | Đúng | at+jwt | ledger.read | 401 |
| Ký bằng RSA key khác | SAI | Đúng | Đúng | at+jwt | ledger.read | 401 |
| Valid token thiếu read scope | OK | Đúng | Đúng | at+jwt | ledger.write | 403 |
| Valid read token gọi POST | OK | Đúng | Đúng | at+jwt | ledger.read | 403 |
| Valid write token gọi POST | OK | Đúng | Đúng | at+jwt | ledger.write | 200 |

**Hai bài học quan trọng:** (1) Scope mạnh không cứu được token có issuer/audience/signature sai. (2) Token đã được xác thực hợp lệ không có nghĩa mọi operation đều được phép.

### 10.3. Lệnh chạy

~~~bash
./gradlew test --tests demo.jwttrust.TokenTrustIntegrationTest
./gradlew bootRun
~~~

Windows:

~~~text
gradlew.bat test --tests demo.jwttrust.TokenTrustIntegrationTest
gradlew.bat bootRun
~~~

Test không cần kết nối tới `issuer.example.invalid` vì decoder pin public key từ bean và validate issuer string tại chỗ. Các test tạo token ký bằng RSA trong memory; không có stdout nghiệp vụ cố định. **Kết quả mong đợi** là các assertions thành công và Gradle hoàn thành task `test`; mã ví dụ được kiểm tra tĩnh, cần chạy thật trong môi trường Gradle/JDK phù hợp trước khi dùng làm cơ sở production.

## 11. Giới hạn của demo và cách triển khai thật

### 11.1. Không tạo signing key trong Resource Server production

Ứng dụng demo có:

~~~java
@Bean
KeyPair demoSigningKeyPair() {
    // Generate key pair for local test ...
}
~~~

Đây chỉ là test fixture. Trong production, **private key thuộc Authorization Server**; Resource Server lấy public keys từ issuer metadata/JWKS đáng tin hoặc được pin qua configuration. Nếu API tự giữ private signing key như Authorization Server mà không có lý do quản trị riêng, ranh giới trust bị mở rộng không cần thiết.

### 11.2. Client ID policy cần phù hợp thực tế

`createAtJwtValidator().clientId("console-client")` trong demo chủ ý chỉ chấp nhận token cấp cho **một client**. Nhiều API production hợp lệ phục vụ **nhiều OAuth clients**. Khi đó cần thiết kế allowlist client IDs, phân loại clients hoặc validator tùy profile; không ép một client cố định nếu business contract không yêu cầu.

Nhưng tuyệt đối không bỏ `aud` hoặc `iss` chỉ để chấp nhận token từ nhiều clients. **Audience là đối tượng resource**, không phải OAuth client đang gọi.

### 11.3. Demo chưa giải quyết mọi business conditions

Ngay cả access token hợp lệ còn phải xét:
- Resource ownership, tenant membership, account status, policy của hành động.
- Thu hồi role/entitlement hoặc token trước khi token hết hạn.
- Giới hạn đối tượng theo scopes và permission catalog.
- Delegation/on-behalf-of: ai là user, ai là service client.
- Rate limiting, DPoP/mTLS proof-of-possession nếu hệ thống yêu cầu.
- Log và audit không ghi token thô, private key hoặc dữ liệu cá nhân quá mức.

## 12. Đọc scope và roles sau khi Gate A pass

Mặc định Spring Security Resource Server thường ánh xạ `scope` hoặc `scp` thành authorities tiền tố `SCOPE_`:

~~~text
JWT claim: "scope": "ledger.read ledger.write"
Authorities:
  SCOPE_ledger.read
  SCOPE_ledger.write
~~~

Rule:

~~~java
.requestMatchers(HttpMethod.GET, "/api/ledger/**")
    .hasAuthority("SCOPE_ledger.read")
.requestMatchers(HttpMethod.POST, "/api/ledger/**")
    .hasAuthority("SCOPE_ledger.write")
~~~

**Không nhầm:**
- `scope=ledger.read` không tự chuyển thành `ROLE_ADMIN`.
- Claim `roles` custom không tự động được ánh xạ giống `scope` nếu không có converter cấu hình.
- `hasRole("ADMIN")` thường kiểm `ROLE_ADMIN`; `hasAuthority("SCOPE_ledger.read")` kiểm chuỗi đúng.
- Một issuer có thể dùng `scp` dạng array, một issuer khác dùng `scope` string; luôn kiểm claim contract thực tế.
- Scope được cấp tại Authorization Server không thay cho permission đối với resource/tenant.

### 12.1. Converter không được cấp quyền trước validation

Nếu IdP có custom claim `roles`:

~~~json
{
  "roles": ["TENANT_ADMIN"]
}
~~~

Bạn có thể tạo `JwtAuthenticationConverter` và `Converter<Jwt, Collection<GrantedAuthority>>` để thêm authority theo allowlist. Nhưng converter phải chạy trên `Jwt` đã được `JwtDecoder` xác minh; không dùng Jackson parse JWT thô rồi tự thêm authorities vào SecurityContext.

Ngoài ra cần ràng buộc role vào tenant. `TENANT_ADMIN` trong tenant A không phải admin toàn nền tảng; kiểm membership/domain policy phía server.

### 12.2. Authorization riêng cho service-to-service

Trong client credentials grant, `sub` có thể không đại diện end user theo cùng ngữ nghĩa với authorization code grant. API phải biết dùng `client_id`/subject/service identity như thế nào, không mặc định mọi token đều là token của người dùng tương tác.

Hãy định nghĩa permissions cho service accounts riêng, tránh role `SYSTEM_ADMIN` cho tất cả jobs; audit phải phân biệt initiating user và service client khi có delegation.

## 13. Multi-tenant và multi-issuer: tránh chọn validator bằng issuer chưa tin

Ví dụ một API phục vụ hai trusted issuers:

~~~text
ALLOWED_ISSUERS:
  https://idp.example.invalid/tenant-a
  https://idp.example.invalid/tenant-b
~~~

Spring Security Servlet hỗ trợ một mẫu:

~~~java
// ĐOẠN TÍCH HỢP (cần import và config HttpSecurity tương ứng)
JwtIssuerAuthenticationManagerResolver resolver =
        JwtIssuerAuthenticationManagerResolver.fromTrustedIssuers(
                "https://idp.example.invalid/tenant-a",
                "https://idp.example.invalid/tenant-b");

http.oauth2ResourceServer(oauth2 ->
        oauth2.authenticationManagerResolver(resolver));
~~~

**Chỉ để minh họa trust policy, không phải app độc lập**: hai issuer mẫu không có metadata thật. Resolver lấy issuer trong claim để chọn strategy, nhưng **chỉ chấp nhận issuer trong allowlist**; strategy tương ứng vẫn phải verify signature và các JWT validators.

Với multi-tenant production:
1. Cho phép issuer từ trust repository do admin cấu hình, không từ request body.
2. Bảo đảm key selection và expected issuer đi với nhau; không cho token issuer A verify bằng key B ngoài policy.
3. Với mỗi API, kiểm `aud` tương ứng; không “tin issuer” rồi bỏ audience.
4. Khi principal thuộc nhiều tenant, kiểm membership active ở tenant đích.
5. Resource `tenantId` lấy từ database, không tin path/header để cấp quyền.
6. Nếu issuer list thay đổi động, có workflow approve/revoke, cache invalidation, audit và monitoring.
7. Không tự tải metadata từ URL chưa trust để tránh SSRF và trust-on-first-use sai.

## 14. Opaque tokens: khi không có JWT claim để parse

Một OAuth2 resource server có thể nhận opaque access token. Lúc này không nên cố split token thành ba phần rồi tự parse JWT. Dùng introspection endpoint thuộc Authorization Server đáng tin, xác minh response `active=true` và các thuộc tính audience/issuer/scope theo hợp đồng AS/API.

~~~text
Opaque bearer token
     |
     v
Trusted introspection endpoint
     |
     v
active? issuer? audience? scope? expiration?
     |
     v
Map authorities + domain authorization
~~~

Opaque introspection có thể giúp token revocation nhanh hơn khi mỗi request tra trạng thái hiện hành, nhưng có chi phí network/cache và giới hạn theo AS. Không tự suy ra “active=true ⇒ API này được quyền đọc hết”; audience/resource permissions vẫn phải đúng policy.

## 15. Bảng lỗi thường gặp

| Triệu chứng | Nguyên nhân | Hướng sửa |
| --- | --- | --- |
| API tin token vừa decode thấy scope | Parse JWT mà không verify | Dùng JwtDecoder/Resource Server filter |
| Chấp nhận JWT ký bởi issuer lạ | Đọc issuer từ claim rồi tự tin nó | Trusted issuers allowlist |
| Token API B gọi được API A | Thiếu aud validation | Cấu hình expected audience của API A |
| Issuer staging token dùng được ở production | Dùng startsWith/domain substring | Exact issuer và môi trường tách biệt |
| ID token được dùng làm access token | Không check typ/audience/token profile | RFC 9068 at+jwt type validator |
| `alg=none` được chấp nhận | Custom verifier sai | Algorithm allowlist, reject unsigned |
| Header `jku` điều khiển key tải về | Dùng untrusted key URL | Chỉ trusted JWKS |
| Token expired vẫn dùng được lâu | Clock skew quá rộng | Giảm skew, test exp cũ rõ |
| `nbf` tương lai mà token được dùng | Thiếu timestamp validation | Dùng standard validators |
| Scope hợp lệ nhưng trả 403 | Sai mapping `SCOPE_`, typo authority | Kiểm `JwtGrantedAuthoritiesConverter` và HTTP rules |
| Scope mạnh dù aud sai vẫn được 200 | Authorization trước JWT validation | Chặn bằng resource server decoder trước claims |
| Custom decoder mất kiểm exp/iss | Thay default validators bằng một validator đơn | Kết hợp đủ validators |
| Token do client tự tạo được chấp nhận | Không verify signature bằng trusted key | RSA/JWKS verifier, test forged key |
| `mockJwt()` tests xanh nhưng token sai issuer vẫn được | Mock bypass decoder | Thêm tests ký token thật qua HTTP |
| Same role ở tenant A cấp quyền tenant B | Chỉ tin roles claim | Membership + tenant resource predicate |
| `client_id` bị nhầm là audience | Lẫn OAuth client và Resource Server | Xác định aud theo API resource indicator |
| JWT có kid lạ | Verifier tự fetch key không trust | Chọn key trong configured JWKS, fail closed |
| Resource server giữ signing private key | Trộn trách nhiệm AS/RS | AS giữ private, RS chỉ public |
| API bị lỗi khi IdP/JWKS down | Key discovery/cache không được thiết kế | Timeout/retry/cache có kiểm soát, không skip verification |
| Lộ raw JWT trong log | Debug Authorization header | Redact token/claims nhạy cảm, log reason codes |

## 16. Checklist trước khi production

1. API chỉ chấp nhận **access token** theo profile đã thỏa thuận?
2. JWT đã được verify cryptographic signature bằng trusted key/algorithm chưa?
3. `alg=none`/algorithm không có allowlist có bị từ chối không?
4. `kid`/`jku` không tự xác lập nơi lấy key chưa được trust?
5. `iss` exact và thuộc allowed issuers/environment chưa?
6. `aud` chứa đúng định danh API, không bị thay bằng client ID?
7. `exp`/`nbf` và skew được kiểm và có negative tests chưa?
8. Nếu theo RFC 9068, `typ=at+jwt`/`application/at+jwt` được xác minh?
9. Required claims `sub`/`client_id`/`iat`/`jti` theo profile đã kiểm đủ?
10. Custom JwtDecoder có giữ validators issuer/time/type/audience cần thiết?
11. Spring `scope/scp` mapping sang `SCOPE_` có đúng contract IdP?
12. Roles custom chỉ được map **sau** token validation?
13. HTTP rules kiểm đúng GET vs POST, không cho scope READ thay WRITE?
14. Sau scope, nghiệp vụ vẫn kiểm tenant/owner/resource/entitlement?
15. Multi-issuer trust list không do client tự mở rộng?
16. Có test signed valid token và invalid signature/iss/aud/typ/exp/scope thật?
17. Dùng `mockJwt()` chỉ cho test authorization rules, không nhầm với signature tests?
18. Không đưa private signing key vào resource server production?
19. JWKS rotation/cache/issuer outage có hành vi fail-closed rõ?
20. Có theo dõi invalid_token/insufficient_scope không log token nguyên văn?
21. Nếu API có cookie/browser credentials, đã đánh giá CSRF thay vì tắt vì “JWT”?
22. Có regression tests khi cập nhật Spring Boot/Security/OAuth2 provider?

## 17. Bài tập thực hành

**Bài 1 – Cross-API token.** Phát token có `scope=ledger.read` nhưng `aud=["urn:reports-api"]`. Test Ledger API trả 401. Giải thích vì sao scope hợp lệ không được xét.

**Bài 2 – Issuer chính xác.** Thay `iss` từ `tenant-a` sang `tenant-b`, giữ nguyên chữ ký RSA test. Test 401; không “sửa” bằng cách dùng `startsWith`.

**Bài 3 – ID token confusion.** Đổi header `typ` từ `at+jwt` thành `JWT` trong token được ký đúng. Test bị từ chối theo RFC 9068 validator. Thảo luận khác biệt ID token và access token.

**Bài 4 – Signature forgery.** Dùng keypair khác ký cùng claims, kiểm 401. Tại sao payload và scopes nhìn hợp lệ vẫn vô nghĩa?

**Bài 5 – Scope mapping.** Phát token `scope=ledger.read` rồi gọi POST; test 403. Thay bằng `ledger.write`, test 200. Giải thích `SCOPE_` prefix.

**Bài 6 – Audience nhiều giá trị.** Cho `aud` gồm reports-api và ledger-api; kiểm policy “contains expected audience”. Nếu muốn only-single-audience, thiết kế validator bổ sung và test.

**Bài 7 – Thời gian.** Tạo token hết hạn nhiều phút, token `nbf` ở tương lai và token thiếu `exp`. Đảm bảo validators phù hợp từ chối.

**Bài 8 – Custom roles.** Cho IdP claim `roles=["TENANT_EDITOR"]`. Tạo converter có allowlist role; test roles không được map từ JWT chưa verify và không cho tenant A sửa tài nguyên B.

**Bài 9 – Trusted multi-issuer.** Thiết lập hai issuer trong allowlist, không accept issuer thứ ba. Đảm bảo mỗi issuer dùng đúng keys và policy audience riêng.

**Bài 10 – JWT vs opaque.** So sánh local JWT validation với opaque introspection trong trường hợp role bị revoke. Mô tả cache/latency/consistency contract và cách fail closed.

**Bài 11 – Security test quality.** Viết riêng hai lớp: một lớp dùng `mockJwt()` để test quyền endpoint, một lớp dùng JWT ký thật để test signature/issuer/audience/type/timestamp; giải thích mỗi lớp chứng minh gì.

**Tiêu chí hoàn thành:** giải thích issuer/audience đúng ý nghĩa; chặn token cross-API hoặc issuer lạ dù có scopes; xác minh chữ ký/key/algorithm/type/time trước khi dùng claims; cấu hình Spring Resource Server và validators chính xác; phân biệt 401/403; test signed tokens thật và thêm object-level authorization khi cần.

## 18. Tài liệu tham khảo chính thức

- RFC 9068 – **JSON Web Token (JWT) Profile for OAuth 2.0 Access Tokens**, yêu cầu issuer/audience/type/signature/time: https://www.rfc-editor.org/rfc/rfc9068.html
- RFC 7519 – **JSON Web Token (JWT)**, `iss`, `aud`, `exp`, `nbf`, `iat`: https://www.rfc-editor.org/rfc/rfc7519.html
- RFC 8725 – **JSON Web Token Best Current Practices**, algorithm/token substitution: https://www.rfc-editor.org/rfc/rfc8725.html
- RFC 8707 – **Resource Indicators for OAuth 2.0**: https://www.rfc-editor.org/rfc/rfc8707.html
- Spring Security 6.5 – **OAuth2 Resource Server JWT**, RFC 9068 validation, JwtDecoder và custom audiences: https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/jwt.html
- Spring Security 6.5 – **JwtValidators.AtJwtBuilder API**: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/jwt/JwtValidators.AtJwtBuilder.html
- Spring Security – **Resource Server Multi-tenancy** và trusted issuer resolver: https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/multitenancy.html
- Spring Boot – **OAuth2 Resource Server Configuration**, `audiences` property: https://docs.spring.io/spring-boot/reference/security/oauth2.html
- Spring Security – **Opaque Token Resource Server**: https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html
- Spring Security – **Testing OAuth2 Resource Server**, `mockJwt`: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/oauth2.html
