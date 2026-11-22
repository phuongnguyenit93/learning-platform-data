# Kiểm tra nguồn cấp, đối tượng sử dụng, thời hạn và chữ ký token

> **Module:** Spring Security – fundamentals → **Token và giao thức**. Bài học tập trung vào việc một **OAuth 2.0 Resource Server** nhận access token dạng **JWT** phải xác minh đồng thời: **nguồn cấp (`iss`)**, **đối tượng sử dụng (`aud`)**, **thời hạn hiệu lực (`exp` và `nbf`)**, và **chữ ký/JWS + khóa tin cậy**. Ví dụ sử dụng **Spring Boot 3.x, Spring Security 6.x, Java 17+**, phân biệt cấu hình production qua `issuer-uri`/JWKS với bài test ký RSA thực tế tại máy local.

## 1. Bối cảnh: “token giải mã được” chưa có nghĩa token hợp lệ

Một HTTP API nhận:

```http
GET /api/whoami HTTP/1.1
Host: orders.example.internal
Authorization: Bearer eyJhbGciOiJSUzI1NiIs...
```

JWT thường là một chuỗi **JWS compact serialization** gồm ba phần Base64URL:

```text
BASE64URL(header).BASE64URL(payload).BASE64URL(signature)
```

Ví dụ cấu trúc minh họa (không phải token có chữ ký hợp lệ):

```json
{
  "header": {
    "alg": "RS256",
    "kid": "key-2026-11",
    "typ": "JWT"
  },
  "payload": {
    "iss": "https://identity.example.org",
    "sub": "user-42",
    "aud": ["orders-api"],
    "iat": 1793779200,
    "nbf": 1793779200,
    "exp": 1793782800,
    "scope": "orders.read"
  },
  "signature": "Base64URL-signature-here"
}
```

Chỉ cần Base64URL decode `header` và `payload` là có thể **đọc** các claim. Đó không phải là xác thực! Một attacker có thể tự soạn JSON có `"sub":"admin"` và `"scope":"orders.write"`. Nếu API dùng dữ liệu đó trước khi xác minh chữ ký và các điều kiện khác, API có thể tin nhầm danh tính/quyền do attacker tự khai.

**Nguyên tắc:** Không sử dụng claim để đưa ra quyết định bảo mật cho đến khi bộ giải mã JWT và các validator đã xác minh token theo **cấu hình tin cậy phía server**. JWT có chữ ký **không mặc định được mã hóa**; nội dung payload có thể được đọc bởi bất cứ ai giữ token, nên không đưa password, secret hoặc thông tin nhạy cảm không cần thiết vào JWT.

## 2. Bốn kiểm tra không thể thay thế nhau

| Kiểm tra | Trường / thành phần | Câu hỏi | Nếu bỏ qua |
|---|---|---|---|
| **Nguồn cấp** | Claim `iss` | Token do **authorization server/issuer được API chấp nhận** cấp ra? | Token từ môi trường hoặc nhà phát hành khác có thể được dùng nhầm |
| **Đối tượng sử dụng** | Claim `aud` | Token này **dành cho resource server này**? | Token cấp cho service A bị mang sang service B (token substitution) |
| **Thời hạn** | `exp`, `nbf` và khi cần `iat` | Token đang ở trong cửa sổ hiệu lực được policy cho phép? | Token hết hạn/chưa có hiệu lực vẫn được chấp nhận |
| **Chữ ký và khóa** | JWS `alg`, `kid`, `signature`, JWKS/public key | Nội dung token còn nguyên vẹn và được ký bằng **khóa đã tin cậy** theo thuật toán cho phép? | Token bị sửa hoặc ký bằng khóa lạ vẫn được coi là xác thực |

**Điều kiện cần đồng thời:** Có chữ ký hợp lệ nhưng issuer sai → **reject**; issuer đúng nhưng audience sai → **reject**; cả hai đúng nhưng hết hạn → **reject**; claim đúng nhưng chữ ký sai → **reject**.

Ngoài bốn điều kiện cốt lõi, hệ thống thực tế còn có thể phải kiểm tra `typ` (access token profile), `azp`/`client_id`, scopes/authorities, tenant, `jti`/revocation, token binding, DPoP, IP/device/risk policy hoặc mục đích của token. Không biến “4 điều kiện đúng” thành tuyên bố “được làm bất cứ hành động gì”: **authentication** khác **authorization**.

### 2.1. Luồng xác thực chuẩn cho Bearer JWT

```text
Client gửi Authorization: Bearer <JWT>
      |
      v
BearerTokenAuthenticationFilter
      |
      v
JwtAuthenticationProvider → JwtDecoder
      |
      +-- Parse JWS, kiểm tra định dạng/thuật toán cho phép
      |
      +-- Chọn public key từ trust anchor/JWKS và xác minh chữ ký
      |
      +-- Jwt validators
      |     ├─ iss == issuer tin cậy?
      |     ├─ aud chứa audience của API?
      |     ├─ exp/nbf hợp lệ với đồng hồ và clock skew?
      |     └─ Các ràng buộc claim/business khác?
      |
      +-- Bất kỳ kiểm tra nào fail → authentication thất bại (thường 401)
      |
      +-- Tất cả pass → tạo JwtAuthenticationToken
                         |
                         v
              Chuyển scope → authorities
                         |
                         v
              HTTP/method/object authorization
                         |
                         +-- Thiếu quyền → thường 403
                         |
                         +-- Đủ quyền → controller/service
```

Đây là mô hình xử lý logic. Thứ tự internal parse/signature/claims có thể khác giữa library versions, nhưng **không được trao danh tính đáng tin cho ứng dụng khi validation chưa thành công**.

## 3. Xác minh issuer (`iss`): ai được quyền cấp token cho API này?

### 3.1. `iss` có nghĩa gì?

Issuer là định danh của bên phát hành token, thường là URI ổn định do hệ thống danh tính quản lý:

```json
{
  "iss": "https://identity.example.org/realms/shop",
  "sub": "alice"
}
```

Ở resource server dành cho issuer đó, giá trị `iss` phải được so với **giá trị issuer được cấu hình từ nguồn tin cậy**, không phải lấy issuer trên token rồi mặc nhiên coi đó là đúng.

Ví dụ **Spring Boot config**:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.org/realms/shop
```

Khi dùng cấu hình tự động phù hợp, Spring Security có thể tìm metadata của issuer, xác định JWKS để kiểm tra chữ ký, rồi xác minh `iss` cùng các thời gian `exp`, `nbf`. URI ví dụ không phải endpoint có thật của người học; thay bằng URI do nhà cung cấp identity cấp và xác minh.

**So sánh chính xác:** `https://id.example/realm` và `https://id.example/realm/` có thể là hai chuỗi khác nhau theo validator. Không “sửa” issuer bằng cách tùy tiện bỏ slash hoặc chuyển sang `contains`. Hãy dùng issuer identifier chính thức và test cả môi trường prod/staging.

### 3.2. Issuer khác host của API

`iss` là issuer của token, không phải domain nhận request. API `orders.example.org` hoàn toàn có thể chấp nhận token do `identity.example.org` phát hành. Không bắt buộc `iss` bằng hostname của service.

Một ứng dụng có thể có nhiều issuer (multi-tenant, nhiều identity provider). Nhưng khi đó phải có **chính sách explicit** để chọn trust configuration cho từng issuer, ví dụ quản trị danh sách issuer được phép và dùng resolver thích hợp, không tải keys từ bất kỳ URL `iss` attacker đưa vào. Đặc biệt tránh SSRF hoặc tự động tin JWKS được chỉ định bởi token.

### 3.3. Chỉ kiểm tra `iss` thôi vẫn không đủ

Attacker có thể tự tạo payload `"iss":"https://identity.example.org"`. Nếu không kiểm tra chữ ký với **key được tin cậy có liên hệ với issuer**, claim này chỉ là chuỗi do attacker nhập. Các claim xác thực và khóa phải cùng nằm trong một thiết lập trust nhất quán: issuer chính thức ↔ metadata/JWKS chính thức ↔ thuật toán cho phép.

## 4. Xác minh audience (`aud`): token này dành cho ai?

### 4.1. Audience là resource/recipient, không phải user

`aud` trả lời “token này được định dùng ở **đâu hoặc bởi dịch vụ nào**?”. Nó không phải tên người dùng; trường `sub` thường xác định subject.

Ví dụ một issuer chung phát hành token cho hai API:

```json
{
  "iss": "https://identity.example.org",
  "sub": "alice",
  "aud": ["catalog-api"],
  "scope": "catalog.read"
}
```

Token trên có thể hợp lệ tại `catalog-api`, nhưng **orders-api phải từ chối**, dù chữ ký và issuer đều đúng. Nếu cả hai service cùng tin một issuer mà bỏ qua `aud`, token cho service A có thể bị “chuyền tay” sang service B.

Một JWT `aud` có thể là một chuỗi hoặc một mảng chuỗi theo chuẩn; trong Spring Security JWT claim thường được chuyển thành `List<String>` để kiểm tra:

```json
{
  "aud": ["orders-api", "billing-api"]
}
```

Một resource server mong đợi `orders-api` sẽ kiểm tra **danh sách audience có chứa phần tử chính xác `orders-api`** (trong khi vẫn áp dụng các policy khác), chứ không dùng substring `"orders"`. Nếu sản phẩm yêu cầu audience chỉ chứa một giá trị, đó là policy **chặt hơn** cần thiết kế và kiểm thử riêng.

### 4.2. Boot cấu hình audience trực tiếp

Với các bản Spring Boot 3.x hỗ trợ property này:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.org/realms/shop
          audiences:
            - orders-api
```

Spring Boot tích hợp audience validation vào resource server khi config phù hợp. Nếu chỉ khai báo `issuer-uri` mà không khai báo audience, **đừng mặc định `aud` đã được kiểm tra theo tên API**. Cần đối chiếu chính xác phiên bản Boot và mọi `JwtDecoder` bean tùy biến (custom bean có thể ghi đè auto configuration).

### 4.3. Khi nào cần validator riêng?

Đối với issuer thay đổi, policy multi-audience, luật bắt buộc có claim, hoặc môi trường cần báo lỗi rõ ràng, có thể dùng `OAuth2TokenValidator<Jwt>` riêng:

```java
OAuth2TokenValidator<Jwt> audienceValidator =
    new JwtClaimValidator<List<String>>(
        JwtClaimNames.AUD,
        audiences -> audiences != null
            && audiences.contains("orders-api"));
```

Đây là **đoạn trong cấu hình**, imports và class đầy đủ xuất hiện trong ví dụ ở mục 8. Lưu ý không thay tất cả validator mặc định bằng **chỉ** một audience validator: điều đó có thể làm mất kiểm tra issuer/thời hạn. Hãy **kết hợp** các validator.

## 5. Thời hạn (`exp`, `nbf`, `iat`) và clock skew

### 5.1. Ý nghĩa của các claim thời gian

- `exp` (*expiration time*): token không còn hợp lệ tại hoặc sau mốc hết hạn. Đây là ranh giới tối đa thời gian sử dụng.
- `nbf` (*not before*): token không nên được chấp nhận **trước** mốc này.
- `iat` (*issued at*): thời điểm tạo token. Nó hữu ích để audit và một số policy về “token age”, nhưng **không thay `exp`/`nbf`**.

Các giá trị thời gian trong JWT thường là **NumericDate**, tức số giây tính từ Unix epoch UTC (có thể là số thập phân theo chuẩn), không phải mili-giây JavaScript. Không nhầm `1793782800` giây với `1793782800000` mili-giây.

### 5.2. Timeline minh họa

```text
UTC time:
    nbf                    now                    exp
     |----------------------|----------------------|
   chưa có hiệu lực      token dùng được       hết hạn
```

Một token `nbf` ở tương lai một giờ không nên được chấp nhận lúc này. Token `exp` cách đây một giờ phải bị từ chối. Có thể có sai lệch đồng hồ vài giây giữa Authorization Server và API; Spring Security cung cấp `JwtTimestampValidator` để xét `exp/nbf` với **clock skew** phù hợp.

**Clock skew không phải gia hạn token tùy tiện.** Nếu một API cho phép vài chục giây dung sai, một token hết hạn cách đây rất ít giây có thể vẫn được chấp nhận theo policy. Đừng thử nghiệm token hết hạn 1–2 giây rồi tuyên bố validation hỏng; dùng test tách xa ranh giới hoặc cấu hình skew tường minh.

### 5.3. Validator thời gian mặc định và policy bổ sung

`JwtValidators.createDefaultWithIssuer(issuer)` kết hợp các điều kiện mặc định (bao gồm thời hạn và issuer theo API Spring Security). Tuy nhiên, ứng dụng phải kiểm tra hợp đồng riêng:

- Một số validator chỉ kiểm tra `exp`/`nbf` **khi claim tồn tại**; nếu yêu cầu token **bắt buộc có `exp`**, thêm required-claim policy tường minh.
- `iat` không mặc nhiên chứng minh token được cấp bởi một bên đáng tin. Chỉ tin nó sau signature validation, và thêm “maximum token age” nếu threat model yêu cầu.
- JWT không có revocation built-in. Token chưa hết hạn có thể đã bị thu hồi. Cần short TTL, introspection, revocation store, key rollover hoặc cơ chế khác tùy nhu cầu.
- Không dùng cách “cộng 1 ngày vào `exp` khi server đọc token” để chữa lỗi đồng hồ; sửa NTP/time sync và skew đã thỏa thuận.

Ví dụ đặt tolerance (đoạn minh họa):

```java
JwtTimestampValidator timestamp =
    new JwtTimestampValidator(Duration.ofSeconds(30));
```

Nếu xây validator tùy biến có timestamp, cần **giữ lại** issuer/audience và các policy khác qua `DelegatingOAuth2TokenValidator`. Không gọi `setJwtValidator(timestamp)` rồi làm mất kiểm tra issuer.

### 5.4. Khi nào cần kiểm soát `iat` và TTL?

Giả sử hệ thống chỉ chấp nhận access token sống tối đa 10 phút. Dù `exp` trong tương lai, một token tự khai `exp = now + 10 years` vẫn không phù hợp policy. Vì token phải được ký hợp lệ trước, đây là lỗi do issuer hoặc cấu hình phát hành, nhưng resource server có thể áp đặt phòng vệ thêm: kiểm tra `exp - iat <= 10 minutes`, giới hạn clock skew và yêu cầu `iat` hợp lệ.

**Không nên cho phép caller tự nhập `iat`/`exp`** và ký token bằng khóa của API; issuer phải quản lý điều này. Nếu tự viết TTL validator, test claim thiếu/null, token tạo trong tương lai, âm/dài bất thường và phép trừ Duration có thể tràn hoặc sai units.

## 6. Chữ ký: khóa tin cậy, `alg`, `kid` và JWKS

### 6.1. Chữ ký chứng minh điều gì?

Với JWS `RS256`, Authorization Server ký phần `Base64URL(header) + "." + Base64URL(payload)` bằng **RSA private key**. Resource Server dùng **public key đáng tin cậy** để kiểm tra chữ ký. Nếu attacker sửa `sub`, `aud` hay `exp` mà không thể tạo chữ ký tương ứng bằng private key được tin cậy, token phải bị từ chối.

```text
Authorization Server                        Resource Server
  RSA private key (bí mật)                    RSA public key (tin cậy)
           |                                         ^
           v                                         |
     JWS signature --- JWT qua HTTPS ------------> verify
                                                      |
                        ┌─────────────────────────────┤
                        |                             |
                        v                             v
                    signature OK                 signature FAIL
                        |                             |
                        v                             v
                 Validate claims                  Reject token
```

**Quan trọng:** Valid signature chỉ khẳng định token được ký bằng private key tương ứng một public key mà verifier đã tin; nó **không** tự chứng minh issuer/audience/timestamp đúng. Một khóa công khai đọc được từ một URL bất kỳ **không đủ** để biến token thành đáng tin: URL đó phải nằm trong trust configuration do server kiểm soát.

### 6.2. Header `alg` không được tự quyết định mọi thứ

JWT header có thể mang:

```json
{
  "alg": "RS256",
  "kid": "prod-2026-rotate-a",
  "typ": "at+jwt"
}
```

- `alg` nói token đang yêu cầu thuật toán nào, nhưng API phải có **allowlist thuật toán** được chọn bởi ứng dụng/issuer configuration.
- `kid` chỉ là **gợi ý chọn khóa** trong tập khóa đã tin. `kid` không phải bằng chứng quyền sở hữu khóa và không phải URL đáng tải. Không cho token tự chọn đường dẫn file, SQL query hay host JWKS dựa trên `kid` tùy ý.
- `typ` cho biết loại JWT; nhiều hệ thống access token dùng `at+jwt` theo RFC 9068, còn ID token có hợp đồng khác. Nếu hệ thống dựa vào token profile, cần validator tương thích và kiểm thử.

**Các lỗi cần tránh:** chấp nhận `alg=none`, đổi nhầm giữa asymmetric RS256 và symmetric HS256, tin mọi thuật toán do token yêu cầu, tìm public key ở URL lấy từ token chưa tin, tự triển khai chữ ký bằng string concat/compare thường, hoặc dùng “decode JSON thành công” để cấp quyền.

### 6.3. JWKS là gì?

**JSON Web Key Set (JWKS)** là tập hợp public key mà issuer công bố để resource server kiểm tra JWT. Ví dụ hình dạng rút gọn:

```json
{
  "keys": [
    {
      "kty": "RSA",
      "kid": "prod-key-1",
      "use": "sig",
      "alg": "RS256",
      "n": "BASE64URL_RSA_MODULUS",
      "e": "AQAB"
    }
  ]
}
```

Đoạn trên chỉ mô tả cấu trúc, không phải JWK sử dụng được: RSA modulus thực phải là giá trị hợp lệ. **Public key** có thể được công bố; **private key không được xuất hiện trong JWKS**. Dùng TLS để lấy metadata/JWKS, giới hạn outbound network và tin JWKS theo issuer/URL đã cấu hình, không theo dữ liệu từ token.

Khi issuer đổi khóa:

1. Issuer có thể công bố khóa mới trước khi bắt đầu ký token bằng khóa đó.
2. Token mới có `kid` phù hợp.
3. Resource server làm mới JWKS cache và kiểm tra token mới bằng public key tương ứng.
4. Khóa cũ có thể còn được công bố trong thời gian token đã ký cũ chưa hết hạn, tùy quy trình rotation.
5. Sau thời gian phù hợp, loại bỏ khóa cũ khỏi trust set.

Không tự tắt signature verification để tránh lỗi `kid not found`. Điều tra JWKS cache, proxy, metadata, key rotation schedule, algorithm mismatch và timeout. Khi bị compromise private key, cần cơ chế khẩn cấp khác với rollover bình thường.

### 6.4. Phân biệt JWS và JWE

JWT có thể được **ký** (JWS) hoặc **mã hóa** (JWE), hoặc được lồng nhau tùy thiết kế. Resource Server JWT theo cấu hình ví dụ học tập này kiểm tra **JWS có chữ ký**, không mặc định giải mã JWE. Payload của JWS có thể đọc được mà không cần khóa. Nếu sản phẩm cần bảo mật nội dung token trước bên giữ token, cân nhắc thiết kế hạn chế claim hoặc tiêu chuẩn encryption đúng nhu cầu, không tự gọi JWS là “JWT được mã hóa”.

## 7. Cấu hình production ngắn gọn với Spring Boot

### 7.1. Dependencies

Tạo ứng dụng Spring Boot 3.x / Java 17+ từ Spring Initializr, chọn **Spring Web** và **OAuth2 Resource Server**. Trong `build.gradle` của project đã có Boot plugin/BOM, cấu hình cơ bản:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Starter Resource Server kéo theo phần Spring Security cần cho bearer JWT, bao gồm thư viện JOSE phù hợp trong dependency graph. Không ghi đè riêng version các thư viện security khi chưa kiểm tra tính tương thích với Boot BOM.

### 7.2. Chỉ cấu hình issuer và audience

Trong `src/main/resources/application.yml`:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.org/realms/shop
          audiences:
            - orders-api
```

Trong setup này, nguồn keys sẽ được discovery theo metadata issuer (đòi hỏi provider đáp ứng endpoint discovery thích hợp), và các policy cơ bản đã được Resource Server tích hợp. Với phiên bản Boot cho phép property `audiences`, token có issuer khác, không dành cho `orders-api`, đã hết hạn/chưa có hiệu lực hoặc chữ ký sai phải bị từ chối.

Nếu issuer hỗ trợ JWKS nhưng không muốn khám phá metadata lúc khởi động hoặc muốn cấu hình chính xác URI, có thể chỉ rõ **cả issuer và JWKS**:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.org/realms/shop
          jwk-set-uri: https://identity.example.org/realms/shop/protocol/openid-connect/certs
          audiences:
            - orders-api
```

**Không được suy ra JWKS URL trên là URL của mọi nhà cung cấp**; nó chỉ là ví dụ hình dạng. Lấy giá trị chính xác từ tài liệu/metadata đã xác minh của issuer. **Dùng `jwk-set-uri` mà quên `issuer-uri` có thể không tự bật issuer validation**, nên giữ cả hai khi cần quản lý trust issuer rõ ràng.

### 7.3. Cấu hình HTTP security và scope

Đoạn Java riêng cho `SecurityFilterChain` (chỉ method trong cấu hình, **chưa phải class độc lập**):

```java
@Bean
SecurityFilterChain api(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/public/ping").permitAll()
            .requestMatchers(HttpMethod.GET, "/api/orders/**")
                .hasAuthority("SCOPE_orders.read")
            .anyRequest().denyAll())
        .sessionManagement(session -> session
            .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
        .oauth2ResourceServer(oauth -> oauth.jwt(
            Customizer.withDefaults()))
        .build();
}
```

Imports thuộc Spring Security: `HttpSecurity`, `SecurityFilterChain`, `Customizer`, `SessionCreationPolicy`, `HttpMethod`. Với cấu hình mặc định, scope `orders.read` thường được chuyển thành authority `SCOPE_orders.read`. Đây là **authorization**, bổ sung vào bốn kiểm tra token; không dùng role/scope thay issuer/signature.

Để tạo API stateless hoàn toàn, cần xem CSRF/browser-cookie threat model, session policy, error handlers và client architecture. Không mặc định “Bearer token” đồng nghĩa mọi browser flow miễn CSRF; hãy xét credential có tự được browser đính kèm không. Endpoint GET an toàn trong ví dụ có thể giữ cấu hình CSRF mặc định mà không phát sinh vấn đề.

### 7.4. Phân biệt auto config với custom `JwtDecoder`

Khi Spring Boot thấy một bean `JwtDecoder` do lập trình viên tự tạo, auto configuration của decoder có thể được thay thế. Điều này đồng nghĩa các property/validator mà bạn **tưởng** Boot tự áp dụng có thể không còn hiệu lực. Với custom decoder, hãy tự thiết lập đầy đủ issuer, audience, timestamp và signature trust/algorithm.

Đừng làm:

```java
// Chỉ minh họa sai lầm: custom decoder này KHÔNG tự
// chứng minh issuer và audience phù hợp chính sách.
@Bean
JwtDecoder decoderOnlyKey() {
    return NimbusJwtDecoder.withPublicKey(publicKey).build();
}
```

Giá trị `publicKey` ở đây không khai báo, code không phải class runnable. Kiểm tra public key đơn lẻ có thể giúp xác minh signature, nhưng để phù hợp policy của API, **vẫn phải cấu hình claim validators**.

## 8. Ví dụ runnable: xác minh chữ ký RSA và bốn claim trong local

Ví dụ này dùng **một RSA key pair sinh tạm mỗi lần khởi động**, chỉ nhằm kiểm thử nhanh **ở môi trường cục bộ**. Resource Server nhận public key; test có private key để ký token thử nghiệm. **Không triển khai mô hình “service tự tạo key pair mới mỗi lần khởi động” trong production**, vì không có issuer độc lập, JWKS rotation/discovery, quản lý khóa hoặc liên tục xác thực sau restart.

Trong project Spring Boot 3.x / Java 17+ với dependencies mục 7.1, tạo hai tệp.

### 8.1. Ứng dụng Spring Security

Đặt `src/main/java/example/jwtcheck/JwtValidationDemoApplication.java`:

```java
package example.jwtcheck;

import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.interfaces.RSAPublicKey;
import java.util.List;
import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtClaimNames;
import org.springframework.security.oauth2.jwt.JwtClaimValidator;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class JwtValidationDemoApplication {

    static final String ISSUER = "https://issuer.example.test";
    static final String AUDIENCE = "orders-api";

    public static void main(String[] args) {
        SpringApplication.run(JwtValidationDemoApplication.class, args);
    }

    @Bean
    KeyPair demoKeyPair() throws Exception {
        // Chỉ tạo khóa tạm để local test; production lấy JWKS
        // từ issuer đã được cấu hình và bảo vệ.
        KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);
        return generator.generateKeyPair();
    }

    @Bean
    JwtDecoder jwtDecoder(KeyPair demoKeyPair) {
        NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withPublicKey((RSAPublicKey) demoKeyPair.getPublic())
            .signatureAlgorithm(
                org.springframework.security.oauth2.jose.jws.SignatureAlgorithm.RS256)
            .build();

        // Mặc định có issuer + timestamp validation.
        OAuth2TokenValidator<Jwt> issuerAndTimes =
            JwtValidators.createDefaultWithIssuer(ISSUER);

        // Audience phải chứa chính xác "orders-api".
        OAuth2TokenValidator<Jwt> audience =
            new JwtClaimValidator<List<String>>(
                JwtClaimNames.AUD,
                values -> values != null && values.contains(AUDIENCE));

        // Policy thêm: yêu cầu luôn có exp.
        OAuth2TokenValidator<Jwt> requireExpiry =
            new JwtClaimValidator<java.time.Instant>(
                JwtClaimNames.EXP,
                value -> value != null);

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                issuerAndTimes, audience, requireExpiry));

        return decoder;
    }

    @Bean
    SecurityFilterChain security(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/ping").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/whoami")
                    .authenticated()
                .requestMatchers(HttpMethod.GET, "/api/orders")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().denyAll())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .oauth2ResourceServer(oauth -> oauth
                .jwt(Customizer.withDefaults()))
            .build();
    }
}

@RestController
class DemoController {

    @GetMapping("/public/ping")
    String ping() {
        return "ok";
    }

    @GetMapping("/api/whoami")
    Map<String, String> whoami(@AuthenticationPrincipal Jwt jwt) {
        return Map.of(
            "subject", jwt.getSubject(),
            "issuer", jwt.getIssuer().toString());
    }

    @GetMapping("/api/orders")
    String orders() {
        return "orders:allowed";
    }
}
```

**Giải thích từng thành phần:**

1. `demoKeyPair()` sinh cặp RSA 2048 bit **chỉ dùng trong local demo**. Public key dùng cho decoder, private key chỉ được test truy xuất để tạo token. Không có endpoint phát token.
2. `NimbusJwtDecoder.withPublicKey(...)` kiểm tra chữ ký token bằng public key đã tin. Builder giới hạn thuật toán vào `RS256`.
3. `JwtValidators.createDefaultWithIssuer(ISSUER)` giữ issuer và default time validators.
4. `JwtClaimValidator` audience buộc `aud` chứa chính xác `orders-api`.
5. `requireExpiry` là quy tắc thêm để `exp` bắt buộc tồn tại, thay vì chỉ dựa vào việc validator xử lý claim khi có mặt.
6. `DelegatingOAuth2TokenValidator` tổng hợp điều kiện; **tất cả** phải đạt.
7. HTTP bearer JWT được Spring Security kiểm tra trước khi controller nhận `@AuthenticationPrincipal Jwt`.
8. `/api/whoami` chỉ yêu cầu token hợp lệ; `/api/orders` còn yêu cầu scope `orders.read`, được map thành `SCOPE_orders.read`.

**Vì sao không dùng `@WithMockUser` hoặc `jwt()` để kiểm tra signature?** Chúng có ích cho test authorization, nhưng thường **đưa Authentication trực tiếp vào security context**, không làm decoder thật kiểm tra JWS/claim validators. Muốn chứng minh bốn kiểm tra hoạt động, phải gửi **Bearer token compact được ký thật** vào filter chain.

### 8.2. Integration test phát JWT thật bằng private key

Đặt `src/test/java/example/jwtcheck/JwtValidationDemoTest.java`:

```java
package example.jwtcheck;

import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.interfaces.RSAPrivateKey;
import java.security.interfaces.RSAPublicKey;
import java.time.Instant;
import java.util.List;

import com.nimbusds.jose.jwk.JWKSet;
import com.nimbusds.jose.jwk.RSAKey;
import com.nimbusds.jose.jwk.source.ImmutableJWKSet;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.JwtClaimsSet;
import org.springframework.security.oauth2.jwt.JwtEncoderParameters;
import org.springframework.security.oauth2.jwt.JwsHeader;
import org.springframework.security.oauth2.jwt.NimbusJwtEncoder;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class JwtValidationDemoTest {

    @Autowired MockMvc mvc;
    @Autowired KeyPair trustedKey;

    private String sign(KeyPair key, String issuer,
                        List<String> audiences,
                        Instant notBefore, Instant expiresAt,
                        String scope) {
        RSAKey jwk = new RSAKey.Builder(
                (RSAPublicKey) key.getPublic())
            .privateKey((RSAPrivateKey) key.getPrivate())
            .keyID("test-key")
            .build();

        NimbusJwtEncoder encoder = new NimbusJwtEncoder(
            new ImmutableJWKSet<>(new JWKSet(jwk)));

        JwtClaimsSet claims = JwtClaimsSet.builder()
            .issuer(issuer)
            .subject("alice")
            .audience(audiences)
            .issuedAt(Instant.now().minusSeconds(7200))
            .notBefore(notBefore)
            .expiresAt(expiresAt)
            .claim("scope", scope)
            .build();

        JwsHeader header = JwsHeader.with(SignatureAlgorithm.RS256)
            .keyId("test-key")
            .build();

        return encoder.encode(
            JwtEncoderParameters.from(header, claims))
            .getTokenValue();
    }

    private String validToken() {
        Instant now = Instant.now();
        return sign(
            trustedKey,
            JwtValidationDemoApplication.ISSUER,
            List.of(JwtValidationDemoApplication.AUDIENCE),
            now.minusSeconds(30),
            now.plusSeconds(600),
            "orders.read");
    }

    @Test
    void validTokenPassesAllChecks() throws Exception {
        mvc.perform(get("/api/whoami")
                .header(HttpHeaders.AUTHORIZATION, "Bearer " + validToken()))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.subject").value("alice"));
    }

    @Test
    void missingBearerIsRejected() throws Exception {
        mvc.perform(get("/api/whoami"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void wrongIssuerIsRejected() throws Exception {
        Instant now = Instant.now();
        String token = sign(trustedKey,
            "https://another-issuer.example.test",
            List.of("orders-api"),
            now.minusSeconds(30), now.plusSeconds(600),
            "orders.read");

        mvc.perform(get("/api/whoami")
                .header(HttpHeaders.AUTHORIZATION, "Bearer " + token))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void wrongAudienceIsRejected() throws Exception {
        Instant now = Instant.now();
        String token = sign(trustedKey,
            JwtValidationDemoApplication.ISSUER,
            List.of("catalog-api"),
            now.minusSeconds(30), now.plusSeconds(600),
            "orders.read");

        mvc.perform(get("/api/whoami")
                .header(HttpHeaders.AUTHORIZATION, "Bearer " + token))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void expiredTokenIsRejected() throws Exception {
        Instant now = Instant.now();
        String token = sign(trustedKey,
            JwtValidationDemoApplication.ISSUER,
            List.of("orders-api"),
            now.minusSeconds(7200), now.minusSeconds(3600),
            "orders.read");

        mvc.perform(get("/api/whoami")
                .header(HttpHeaders.AUTHORIZATION, "Bearer " + token))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void notYetValidTokenIsRejected() throws Exception {
        Instant now = Instant.now();
        String token = sign(trustedKey,
            JwtValidationDemoApplication.ISSUER,
            List.of("orders-api"),
            now.plusSeconds(3600), now.plusSeconds(7200),
            "orders.read");

        mvc.perform(get("/api/whoami")
                .header(HttpHeaders.AUTHORIZATION, "Bearer " + token))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void signatureFromUntrustedKeyIsRejected() throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);
        KeyPair attackerKey = generator.generateKeyPair();

        Instant now = Instant.now();
        // Claims đầy đủ và ĐÚNG, chỉ signature không tin cậy.
        String token = sign(attackerKey,
            JwtValidationDemoApplication.ISSUER,
            List.of("orders-api"),
            now.minusSeconds(30), now.plusSeconds(600),
            "orders.read");

        mvc.perform(get("/api/whoami")
                .header(HttpHeaders.AUTHORIZATION, "Bearer " + token))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void scopeStillControlsAuthorizationAfterValidJwt() throws Exception {
        Instant now = Instant.now();
        String noOrderScope = sign(trustedKey,
            JwtValidationDemoApplication.ISSUER,
            List.of("orders-api"),
            now.minusSeconds(30), now.plusSeconds(600),
            "profile.read");

        mvc.perform(get("/api/orders")
                .header(HttpHeaders.AUTHORIZATION, "Bearer " + noOrderScope))
            .andExpect(status().isForbidden());

        mvc.perform(get("/api/orders")
                .header(HttpHeaders.AUTHORIZATION, "Bearer " + validToken()))
            .andExpect(status().isOk())
            .andExpect(content().string("orders:allowed"));
    }
}
```

**Kết quả dự kiến khi chạy `./gradlew test`:**

| Test | Expect | Chứng minh |
|---|---:|---|
| Valid issuer/audience/time/signature | 200 | Bốn điều kiện cùng đúng |
| Không có Bearer | 401 | Không có authentication hợp lệ |
| Issuer khác | 401 | Kiểm tra `iss` |
| Audience khác | 401 | Kiểm tra `aud` |
| Token hết hạn từ lâu | 401 | Kiểm tra `exp` vượt clock skew |
| `nbf` ở tương lai | 401 | Kiểm tra `nbf` vượt clock skew |
| Chữ ký bởi private key khác | 401 | Kiểm tra JWS và trust key |
| JWT hợp lệ nhưng scope sai | 403 | Phân biệt xác thực token và phân quyền |

**Bất biến kiểm thử:** Mỗi negative case **chỉ thay một điều kiện chính** so với valid token (trừ các yếu tố thời gian cần tương quan hợp lý), vì vậy có thể định vị lỗi policy. Test thực hiện HTTP request qua security filter chain, không mock decoder. Tài liệu Java không bảo đảm mọi minor version/patch đều giống nhau; dùng Spring Initializr với Boot 3.x phù hợp và test trong project thật. Nếu package/API có thay đổi theo version, cập nhật theo BOM/official docs; không bỏ validator để làm test xanh.

Trong demo, `issuer.example.test` chỉ là chuỗi claim đã ký, **không có kết nối tới external issuer**. Đây là local test của decoder dùng RSA public key tĩnh, không kiểm tra JWKS rotation/discovery. Các cơ chế đó cần integration test riêng ở môi trường staging.

### 8.3. Chạy ứng dụng

Trong project đã có Gradle Wrapper:

```bash
./gradlew test
./gradlew bootRun
```

Windows PowerShell:

```powershell
.\gradlew.bat test
.\gradlew.bat bootRun
```

Nếu gọi:

```bash
curl -i http://localhost:8080/public/ping
curl -i http://localhost:8080/api/whoami
```

Kỳ vọng đường public trả 200 với `ok`, còn đường riêng thiếu bearer trả 401. Để có token ký đúng cho ứng dụng demo vừa khởi động, phải ký bằng **private key tương ứng với bean `demoKeyPair` của đúng process**; mỗi lần restart key thay đổi. Trong cấu trúc học tập này, test tự tạo token từ bean của test context. Không thể dùng token do test context ký để gọi một instance chạy tách riêng nếu key pair khác.

**Không đưa private key demo, access token thật hoặc Bearer header vào source control, log, ảnh chụp màn hình hay public issue.**

## 9. Bộ kiểm tra nên chạy theo chính sách nào?

Một checklist kiểm tra token điển hình:

```text
[ ] Bearer token đúng cấu trúc/hợp đồng HTTP
[ ] Chỉ chấp nhận JWS algorithms đã allowlist
[ ] Lựa chọn key trong JWKS/trust anchor do server cấu hình
[ ] Signature được xác minh bằng khóa tương ứng
[ ] iss khớp issuer được API chấp thuận
[ ] aud có ít nhất một audience hợp lệ của API
[ ] exp có và chưa quá hạn (theo clock skew cho phép)
[ ] nbf nếu có không ở tương lai vượt tolerance
[ ] iat/maximum age nếu policy cần
[ ] typ/token profile đúng loại access token
[ ] Token không bị revoke/compromise theo chính sách
[ ] scope/roles/permissions đủ cho endpoint
[ ] tenant/owner/ACL được kiểm tra trên tài nguyên cụ thể
```

Không dùng `aud` để thay `scope`: audience trả lời **API nào là recipient**, scope trả lời **khả năng nào đã được ủy quyền**, còn owner/tenant trả lời **bản ghi nào được thao tác**.

### 9.1. Ví dụ ba token cùng issuer

| Token | Issuer | Audience | Scope | API orders nhận? |
|---|---|---|---|---|
| A | Issuer hợp lệ | `orders-api` | `orders.read` | Nếu chữ ký/thời hạn hợp lệ: qua token validation và có quyền đọc |
| B | Issuer hợp lệ | `catalog-api` | `orders.read` | **Không**: audience sai |
| C | Issuer hợp lệ | `orders-api` | `profile.read` | Token validation có thể qua; endpoint yêu cầu `orders.read` trả **403** |

### 9.2. Issuer/tenant đa môi trường

Một issuer staging có thể ký bằng khóa riêng và dùng cùng format token như production. Prod API không nên tin issuer staging chỉ vì payload có `role=admin`. Khi nhiều issuer cùng được phép, quản lý mapping issuer → JWKS/trust config và audience theo môi trường; test tokens chéo giữa tenants/environments.

### 9.3. Subject và authorized party

Claim `sub` nhận dạng chủ thể nhưng không tự nói “đây là người dùng nào trong database này” khi có nhiều issuer. Một khóa danh tính bền vững có thể cần cặp `(iss, sub)`, không chỉ `sub`, để tránh hai issuer khác nhau cùng phát `sub=42` bị đồng nhất. Tùy profile, `azp` hoặc `client_id` có thể xác định ứng dụng gọi; khi có nhiều audience hoặc delegation, cần xét authorized party theo giao thức/IdP cụ thể.

### 9.4. Access token khác ID token

**OIDC ID token** được thiết kế để chứng minh kết quả đăng nhập cho **OAuth/OIDC client**, thường có `aud` là **client ID**. Resource Server API phải nhận **access token dành cho API**, không chấp nhận ID token chỉ vì nó là JWT ký đúng và do cùng issuer cấp. Nếu bên cấp phát token hỗ trợ `typ=at+jwt`/RFC 9068, cân nhắc validator theo access token profile và thiết kế rõ audience, client_id, scope.

**Quan trọng:** Chữ ký của ID token có thể hợp lệ, `iss` cũng hợp lệ, thời gian cũng hợp lệ; **audience/token type** vẫn khiến ID token không phù hợp với API. Đây là một lý do then chốt không bỏ qua `aud`.

## 10. 401 và 403: token không hợp lệ khác thiếu quyền

| Trường hợp | Thường trả | Nguyên nhân |
|---|---:|---|
| Không gửi `Authorization: Bearer ...` tới private API | 401 | Chưa xác thực |
| JWT sai chữ ký | 401 | Không xác thực được token |
| JWT issuer sai | 401 | Sai trust issuer |
| JWT audience sai | 401 | Không dành cho API này |
| JWT hết hạn / `nbf` chưa tới | 401 | Không thuộc cửa sổ hiệu lực |
| JWT hợp lệ nhưng thiếu authority trên endpoint | 403 | Đã xác thực nhưng không được phép |
| JWT hợp lệ, scope phù hợp nhưng object thuộc user khác | 403 hoặc 404 tùy policy | Authorization trên đối tượng |
| Lỗi ứng dụng/DB không liên quan JWT | 5xx/4xx theo loại lỗi | Không đánh đồng với authentication |

Trong OAuth2 Bearer response, có thể có header `WWW-Authenticate` theo RFC 6750, ví dụ `error="invalid_token"` với token bị từ chối. **Đừng lộ chi tiết nội bộ** như private key, nguyên token, tên file keystore hoặc stack trace qua response/log. Phân biệt 401/403 bằng test với exact authentication configuration (form login có thể redirect thay vì 401).

JWT là bearer credential: chỉ cần nắm token còn hợp lệ là có thể dùng nếu không có binding/mitigation bổ sung. Luôn sử dụng HTTPS, giới hạn lưu trữ token và không gửi token qua query string.

## 11. Đừng chỉ kiểm tra đúng bốn claim rồi bỏ qua revocation và rotation

### 11.1. Expiration không thu hồi token trước hạn

Token có `exp` còn 30 phút không tự bị vô hiệu ngay khi user logout, đổi password, bị khóa hoặc rút quyền. Nếu yêu cầu “revoke lập tức”, cân nhắc introspection, denylist theo `jti`, key rotation khẩn cấp, short token lifetime, session coordination và policy thích hợp. Cân bằng mức độ realtime, tính sẵn sàng, chi phí và bảo mật.

### 11.2. Key rotation và JWKS cache

Một token `kid=new-key` không được API công nhận nếu JWKS cache chưa có public key mới. Không nên chấp nhận token không xác minh chỉ để tránh 401; giải quyết bằng kế hoạch công bố khóa trước, chuyển khóa ký, thời gian sống token cũ và cache refresh. Key rollover bình thường khác với compromise private key cần thu hồi ngay.

### 11.3. Xử lý IdP/JWKS tạm không khả dụng

Nếu API chỉ có issuer-uri và cần discovery/JWKS fetch, thời điểm khởi tạo kết nối phụ thuộc phiên bản Spring Security, cấu hình và cache. Không tuyên bố mọi version luôn ping issuer lúc startup hoặc luôn chờ request đầu tiên. Với `issuer-uri + jwk-set-uri`, có thể tách một số bước discovery nhưng vẫn cần key fetching/refresh sau đó. Chuẩn bị timeout, retry policy có giới hạn, monitor lỗi và fallback **fail closed**: không mở signature validation hoặc tin key lạ.

### 11.4. JWT validator không thay kiểm soát business logic

Ví dụ buyer có `SCOPE_orders.read` và audience `orders-api`, nhưng cố gọi `GET /api/orders/999` là đơn của tenant khác. Token hợp lệ vẫn chưa cho phép đọc đơn 999. Service/repository cần kiểm tra tenant, owner, ACL và field-level authorization với dữ liệu tin cậy, không chỉ nhìn role claim.

## 12. Các hiểu nhầm và lỗi triển khai phổ biến

| Sai lầm | Hậu quả | Cách sửa |
|---|---|---|
| “Decode Base64URL là validate JWT.” | Tin claim attacker tự sửa | Dùng `JwtDecoder` với chữ ký + validators |
| “Chữ ký đúng nghĩa là hợp lệ với mọi API.” | Token substitution giữa services | Kiểm tra `aud` của API hiện tại |
| “`iss` có mặt là đúng nguồn cấp.” | Token của issuer lạ được dùng | So exact với allowlist issuer tin cậy |
| “Có `issuer-uri` là audience tự đúng.” | Một token cùng issuer cho API khác có thể lọt | Cấu hình `audiences` hoặc validator riêng |
| “Key nào trong `kid` cũng được.” | Tin nhầm key attacker lựa chọn | Chỉ chọn keys từ JWKS/trust anchor đã cấu hình |
| “`alg` token ghi gì thì verify như thế.” | Algorithm confusion/none attack | Giới hạn algorithms do server phê duyệt |
| “JWT không thể bị đọc vì có signature.” | Lộ dữ liệu trong payload | Không đưa secrets vào JWT; JWS không phải JWE |
| “`exp` 1 giây trước mà vẫn qua tức lỗi.” | Bỏ qua clock skew | Hiểu tolerance, test quá xa ranh giới |
| “Token có `iat` nên không cần `exp`.” | Không có giới hạn lifetime | Yêu cầu `exp`, kiểm tra thời hạn |
| “Custom decoder vẫn tự dùng mọi property Boot.” | Mất kiểm tra issuer/audience | Đăng ký validator đầy đủ trên bean |
| “`jwt()` MockMvc chứng minh signature.” | Test bypass decoder thật | Gửi token ký thật qua Bearer header |
| “401 cho mọi thiếu quyền là đúng.” | Không phân biệt authentication/authorization | Dùng 401 invalid, 403 insufficient scope |
| “ID token ký đúng dùng gọi API được.” | Nhầm OIDC client token với access token | Kiểm tra audience/token type/profile |
| “Cứ log JWT để debug.” | Rò bearer credential | Redact header/token, log trace ID |
| “JWT hợp lệ nên có thể đọc mọi bản ghi.” | IDOR/BOLA, vượt tenant | Kiểm tra quyền resource-level |

## 13. Ma trận test có giá trị cao trong CI

Ngoài test ở mục 8, nên bổ sung các tình huống theo production policy:

1. **Positive:** issuer, audience, signature, thời gian và scope đều đúng; API trả kết quả hợp lệ.
2. **Signature mismatch:** cùng claims, ký bằng private key không được issuer chấp nhận → 401.
3. **Modified payload:** sửa một ký tự thuộc payload sau ký, chữ ký không còn tương ứng → 401.
4. **`alg=none` và algorithm lạ:** phải bị từ chối khi API chỉ tin RS256.
5. **Unknown `kid`:** chỉ tin key trong JWKS cấu hình, không tải key từ nơi attacker yêu cầu.
6. **Wrong issuer:** issuer staging/token của IdP khác → 401.
7. **Wrong audience:** token cho API khác → 401 dù các claim còn lại đúng.
8. **Missing audience:** nếu hợp đồng yêu cầu `aud`, phải từ chối.
9. **Expiration:** hết hạn từ lâu → 401; thời điểm sát biên phải test theo clock skew chính sách.
10. **Not before:** token chỉ có hiệu lực sau một giờ → 401.
11. **Missing expiration:** nếu hợp đồng bắt buộc `exp`, custom policy phải chặn.
12. **Issued-at:** tùy threat model, test `iat` ở tương lai hoặc token sống quá lâu.
13. **Valid JWT missing scope:** 403 tại endpoint có `hasAuthority`.
14. **Valid scope but wrong object:** 403/404 ở service/repository.
15. **Multi-issuer:** key/issuer/audience phải khớp trust configuration tương ứng, không lẫn stage/prod.
16. **JWKS rotation:** token ký với old/new keys được chấp nhận hoặc từ chối đúng giai đoạn chuyển đổi.
17. **Auth provider outage:** request không thể xác thực fail closed và trả lỗi an toàn; không bỏ qua validation.
18. **Unauthorized logs:** không chứa raw Bearer token, JWT signature hoặc secret; metrics có tín hiệu phù hợp.
19. **ID token as access token:** token OIDC sai audience/type bị từ chối.
20. **Timeout/retry/clock drift:** cấu hình có giới hạn; không mở rộng thời hạn vô hạn để bù lỗi hạ tầng.

Tách **unit test** cho policy (audience, claim shape, TTL), **integration test** đi qua `BearerTokenAuthenticationFilter` với token ký thật, và **staging test** sử dụng issuer/JWKS/token rotation thực tế. Chỉ một lớp test không chứng minh cả hệ thống.

## 14. Checklist code review

- [ ] Xác định API này chấp nhận access token của issuer nào, audience nào, thuật toán nào.
- [ ] Issuer URI lấy từ nguồn đáng tin và so khớp chính xác; không dùng claim `iss` để tự tin mọi host.
- [ ] JWKS URL/public key được quản trị tin cậy; chỉ chấp nhận `kid` và `alg` trong giới hạn cho phép.
- [ ] JWT signature được xác minh; không tự decode rồi dùng claims.
- [ ] `aud` được kiểm tra rõ ràng, không nhầm audience với scope hoặc subject.
- [ ] `exp`/`nbf` được validate cùng clock skew phù hợp; `exp` bắt buộc nếu policy yêu cầu.
- [ ] Nếu có `iat`/TTL/`typ`/`azp` policy, validator đã được thực thi và test.
- [ ] Custom `JwtDecoder` không làm mất các validator khi ghi đè auto config.
- [ ] Scope được map chính xác thành authorities, ví dụ `SCOPE_orders.read`.
- [ ] Endpoint vẫn kiểm tra quyền theo HTTP/method/object/tenant; JWT hợp lệ không tự cho phép mọi thao tác.
- [ ] Login/ID token và access token không bị dùng lẫn, đặc biệt trong cùng issuer.
- [ ] Không tin forwarded Host/issuer/JWKS URLs do client tự chỉ định.
- [ ] Auth fail closed; không tắt signature/issuer validation để “sửa lỗi 401”.
- [ ] Rotation, revocation, cache, retry, timeout, NTP và key compromise có quy trình vận hành.
- [ ] Test negative với token **ký thật**, không chỉ mock Authentication.
- [ ] Không log token, private keys hoặc claims nhạy cảm; giao tiếp qua HTTPS.

## 15. Bài tập tự kiểm tra

**Câu 1.** Token ký RSA hợp lệ, có `iss=https://identity.example.org`, `exp` tương lai, nhưng `aud=["catalog-api"]`. `orders-api` có nên nhận không?

**Đáp án:** Không. Token không dành cho orders-api; signature/issuer/expiry đúng không thay thế audience validation.

**Câu 2.** Bạn Base64URL decode JWT và thấy `"role":"ADMIN"`. Có thể tin chưa?

**Đáp án:** Chưa. Payload đọc được mà không cần secret, ai cũng có thể tự tạo. Cần xác minh chữ ký với key tin cậy, issuer/audience/time và mapping role/authority.

**Câu 3.** Token có `iss` đúng, `aud` đúng, nhưng được ký bằng private key do attacker sinh. Kết quả?

**Đáp án:** Từ chối vì signature không xác minh bằng public key mà resource server tin. `kid` hay `iss` tự khai không làm key lạ trở thành hợp lệ.

**Câu 4.** JWT có `exp` vừa trôi qua 5 giây mà API vẫn nhận. Có chắc validator tắt không?

**Đáp án:** Không chắc. `JwtTimestampValidator` có thể cho phép một khoảng clock skew. Kiểm tra policy và test token hết hạn từ lâu để phân biệt.

**Câu 5.** Vì sao `issuer-uri` đơn lẻ có thể không đủ để bảo vệ hai API cùng issuer?

**Đáp án:** Nó xác định nguồn cấp và giúp thiết lập signature/time validation, nhưng API A và B cần audience riêng. Nếu bỏ `aud`, token của API A có thể bị dùng ở API B.

**Câu 6.** Một token hợp lệ có `scope=orders.read`, dùng đọc đơn hàng của Bob. Chắc chắn được phép?

**Đáp án:** Không. `scope` cho biết khả năng chung; API còn phải kiểm tra owner, tenant, membership/ACL của đơn cụ thể.

**Câu 7.** Trong MockMvc, test dùng `jwt()` và kỳ vọng 200. Điều đó có chứng minh signature RSA hợp lệ?

**Đáp án:** Không. `jwt()` chủ yếu tạo Authentication cho phép test authorization; không bắt buộc chạy decoder ký/xác thực thật. Dùng compact JWT được ký và đưa qua `Authorization: Bearer ...` để test crypto/validators.

**Câu 8.** Có nên thêm `jwtDecoder.setJwtValidator(audienceValidator)` để bật audience nếu trước đó decoder đã kiểm tra issuer/timestamp?

**Đáp án:** Không nên thay thế đơn lẻ. `setJwtValidator` gán validator mới; cần dùng `DelegatingOAuth2TokenValidator` kết hợp issuer/timestamp với audience và các ràng buộc khác.

## 16. Nguồn tham khảo chính thức

- [Spring Security 6.5 — OAuth 2.0 Resource Server JWT (Servlet)](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/jwt.html): issuer-uri, JWKS, trusted algorithms, audience, `exp/nbf`, custom JWT validator và scope mapping.
- [Spring Security — OAuth2 Resource Server JWT (current reference)](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): tài liệu API và behavior theo phiên bản hiện tại.
- [Spring Security — Testing OAuth 2.0 with MockMvc](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/oauth2.html): test `jwt()`, mock Authentication và phân biệt với gửi Bearer token thật.
- [Spring Security — Reactive OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html): đối chiếu khi sử dụng WebFlux/`ReactiveJwtDecoder`.
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): định nghĩa các registered claims `iss`, `aud`, `exp`, `nbf` và `iat`.
- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515): chữ ký JWS, protected header và compact serialization.
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517): biểu diễn khóa công khai, `kid` và JWK Set.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): các ràng buộc khi sử dụng JWT làm OAuth access token.
- [RFC 6750 — Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): `Authorization: Bearer` và authentication error semantics.

**Kết luận:** Một JWT được resource server chấp nhận khi nó **được ký bởi key đáng tin theo thuật toán cho phép**, **đến từ issuer đã được phê duyệt**, **nhắm tới audience của API**, và **đang trong thời gian hiệu lực**. Sau đó vẫn phải kiểm tra scope, quyền nghiệp vụ và quyền dữ liệu. Với Spring Security, ưu tiên Resource Server + `issuer-uri` + `audiences`; nếu custom `JwtDecoder`, chủ động giữ đầy đủ validators và test bằng JWT được ký thật, bao gồm các trường hợp âm tính.
