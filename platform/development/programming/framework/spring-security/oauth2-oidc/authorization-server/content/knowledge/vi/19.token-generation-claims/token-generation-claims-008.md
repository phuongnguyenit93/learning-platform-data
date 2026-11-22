# Áp dụng profile JWT access token phù hợp với Resource Server

## 1. Bối cảnh: JWT hợp lệ về chữ ký vẫn có thể sai mục đích

Trong hệ thống OAuth 2.0/OpenID Connect (OIDC) sử dụng **Spring Security**, **Spring Authorization Server** và Spring Boot, Authorization Server (AS) phát hành access token để client gọi Resource Server (RS). Nhiều hệ thống chọn JWT vì RS có thể xác minh chữ ký và claims tại chỗ mà không phải gọi AS cho từng request.

Tuy nhiên, **không phải JWT nào cũng là access token**. Một ID token OIDC, JWT client assertion, JWT dùng cho Token Exchange hoặc JWT nội bộ đều có thể được ký hợp lệ nhưng mang mục đích và audience khác nhau. Nếu RS chỉ kiểm tra chữ ký mà không kiểm tra đúng profile, issuer, audience, loại token và claims bắt buộc, API có thể chấp nhận một credential không dành cho nó.

Ví dụ, hệ thống đặt phòng có `booking-bff`, `booking-api` và `inventory-api`. Một token được phát hành cho Booking API không nên được Inventory API chấp nhận chỉ vì cả hai API cùng tin một khóa ký. Hai API cần hợp đồng token rõ ràng, đặc biệt là **audience**.

**JWT Access Token Profile** được chuẩn hóa trong **RFC 9068 — JSON Web Token (JWT) Profile for OAuth 2.0 Access Tokens**. Profile này xác định cách biểu diễn access token bằng JWT, gồm JOSE header và các claims cần thiết để Resource Server diễn giải nhất quán.

Sau bài học, bạn có thể:

1. Phân biệt JWT access token theo RFC 9068 với JWT nói chung và OIDC ID token.
2. Nhận biết JOSE header `typ=at+jwt` và ý nghĩa của nó.
3. Xác định các claims bắt buộc như `iss`, `sub`, `aud`, `exp`, `iat`, `jti` và `client_id`.
4. Thiết kế semantics của subject, audience và scope theo loại grant.
5. Cấu hình Spring Authorization Server phát JWT access token theo profile.
6. Cấu hình Spring Security Resource Server kiểm tra issuer, audience, algorithm, token type và claims.
7. Ánh xạ scope thành authorities và áp dụng authorization tại API.
8. Quản lý JWKS/key rotation, TTL, revocation và custom claims.
9. Xây dựng ma trận kiểm thử positive/negative cho token profile.

## 2. JWT access token profile là gì?

JWT là định dạng biểu diễn claims. Nó có thể được ký (JWS) hoặc mã hóa (JWE), nhưng **định dạng JWT tự nó không nói token được dùng làm gì**. Profile JWT access token bổ sung một hợp đồng cho JWT được dùng như OAuth 2.0 access token.

RFC 9068 chuẩn hóa hợp đồng này để Resource Server nhận biết token là JWT access token thay vì một JWT loại khác; các claim nền tảng có tên và ý nghĩa thống nhất; issuer và audience được xác minh theo đúng ngữ cảnh; client ID, subject, thời điểm phát hành và định danh token được diễn giải nhất quán.

| Khái niệm | Trả lời câu hỏi | Ví dụ |
|---|---|---|
| JWT | Credential có cấu trúc JSON Web Token? | Header.payload.signature |
| OAuth access token | Credential cấp quyền truy cập Resource Server? | Bearer token gọi API |
| RFC 9068 JWT access token | Access token JWT tuân theo header/claims profile? | JWS có `typ=at+jwt` và claims theo profile |

Một JWT có chữ ký RS256 **chưa chắc** là RFC 9068 access token. Một OAuth access token cũng có thể là opaque token, không phải JWT.

### 2.1. Vì sao chỉ kiểm tra chữ ký là chưa đủ?

Giả sử API chỉ đọc JWT, xác minh chữ ký bằng public key của AS và kiểm tra `exp` chưa hết hạn. Cách này vẫn thiếu các câu hỏi:

- Token có được phát bởi đúng issuer không?
- Token có được dành cho API hiện tại không?
- JWT này là access token hay ID token?
- Client nào đã yêu cầu token?
- Subject của token là người dùng hay workload?
- Scope có đủ cho endpoint không?
- Token có dùng thuật toán hoặc khóa ngoài allowlist không?

**Profile định nghĩa contract; Resource Server phải chủ động xác minh contract đó.** Chỉ bật JWT decoder không tự chứng minh mọi yêu cầu RFC 9068 đã được thực thi.

## 3. Phân biệt access token với OIDC ID token

OIDC sử dụng OAuth 2.0 nhưng ID token và access token có mục đích khác nhau.

| Thuộc tính | JWT access token | OIDC ID token |
|---|---|---|
| Đối tượng nhận chính | Resource Server | OIDC Client / Relying Party |
| Mục đích | Cấp quyền truy cập API | Cung cấp thông tin xác thực người dùng cho RP |
| Audience | Resource/API dự kiến nhận token | Client ID của RP |
| Header type theo profile | `at+jwt` theo RFC 9068 | Thường là `JWT` theo OIDC |
| Claims quan trọng | `iss`, `sub`, `aud`, `exp`, `iat`, `jti`, `client_id` | `iss`, `sub`, `aud`, `exp`, `iat`, `nonce` khi được yêu cầu |
| Gửi tới API bằng Bearer | Khi token được cấp cho API và policy cho phép | **Không** |

Một ID token được ký hợp lệ cho `booking-bff` không có nghĩa `inventory-api` được phép nhận nó. Audience của ID token là client; API cần access token được cấp cho audience phù hợp.

### 3.1. Header `typ`

RFC 9068 yêu cầu JWT access token có JOSE header parameter:

```json
{
  "alg": "RS256",
  "typ": "at+jwt",
  "kid": "as-signing-key-2026-01"
}
```

- `alg`: thuật toán ký được AS sử dụng.
- `typ`: xác định loại JWT là access token theo profile.
- `kid`: định danh khóa ký trong JWK Set nếu AS sử dụng key ID.

`typ=at+jwt` không thay thế xác minh chữ ký, issuer, audience, expiry hay scope. Nó là điều kiện nhận dạng bổ sung. **Không chấp nhận token chỉ vì header tự khai là `at+jwt`**; kẻ tấn công có thể tạo header đó trên JWT giả.

## 4. Các claims bắt buộc theo RFC 9068

| Claim | Bắt buộc | Ý nghĩa |
|---|---|---|
| `iss` | Có | Issuer đã phát hành token |
| `exp` | Có | Thời điểm token hết hạn |
| `aud` | Có | Resource Server hoặc audience được token dành cho |
| `sub` | Có | Chủ thể mà token đại diện |
| `client_id` | Có | OAuth client đã yêu cầu token |
| `iat` | Có | Thời điểm token được phát hành |
| `jti` | Có | Định danh duy nhất của JWT |
| `scope` | Tùy chọn | Danh sách scope dạng chuỗi phân tách bằng dấu cách |
| `nbf` | Tùy chọn | Thời điểm token bắt đầu có hiệu lực |
| `cnf` | Tùy chọn | Thông tin ràng buộc token với khóa/chứng chỉ |
| `auth_time`, `acr`, `amr` | Theo use case | Ngữ cảnh xác thực người dùng khi có ý nghĩa |

Claims bổ sung cần có semantics rõ ràng. Không tự thêm tên claim dễ xung đột với chuẩn hoặc sử dụng claim của ID token mà không xác định ý nghĩa cho access token.

### 4.1. `iss` — issuer

`iss` là định danh Authorization Server phát hành token. RS phải so sánh với issuer được cấu hình tin cậy, thường là URI ổn định:

```text
iss = https://auth.example.com
```

Không suy ra issuer từ header `Host` của request tới API hoặc từ claim do caller tự gửi. Nếu hệ thống có nhiều issuer, cần cấu hình trust mapping rõ ràng và tránh chấp nhận issuer tùy ý.

Issuer URL phải nhất quán với metadata/JWKS mà RS sử dụng. Sai khác scheme, host hoặc path có thể khiến token bị từ chối; không nới validator thành kiểm tra chuỗi chứa tên miền.

### 4.2. `sub` — subject

`sub` xác định chủ thể mà token đại diện. Ý nghĩa phụ thuộc grant:

- Với Authorization Code đại diện người dùng, `sub` thường là định danh user ổn định do AS quản lý.
- Với Client Credentials, token đại diện workload/client; subject phải phản ánh client identity thích hợp theo profile.
- Với Token Exchange/delegation, `sub` có thể là người dùng được đại diện, còn actor được biểu diễn riêng theo policy.

Không dùng email hoặc username có thể đổi làm subject nếu một mã định danh ổn định, ít tiết lộ hơn có thể đáp ứng yêu cầu. Subject không phải quyền truy cập; API vẫn cần kiểm tra scope và authorization nghiệp vụ.

### 4.3. `aud` — audience

`aud` chỉ ra token được dành cho bên nhận nào:

```json
{
  "aud": [
    "https://booking-api.example.com"
  ]
}
```

RS của Booking API phải xác minh audience của chính nó có trong `aud`. Token dành cho Inventory API phải bị Booking API từ chối, ngay cả khi issuer và chữ ký đều đúng.

Một hệ thống có thể dùng một chuỗi hoặc mảng audience. Cần thống nhất identifier chính xác giữa AS và RS. Không dùng `client_id` làm audience chỉ vì đó là ID của client; client yêu cầu token và Resource Server nhận token là hai vai trò khác nhau.

### 4.4. `exp`, `iat` và `nbf` — vòng đời

- `iat` là thời điểm token được phát hành.
- `exp` là thời điểm token hết hạn.
- `nbf` (nếu có) là thời điểm trước đó token chưa được sử dụng.

RS cần xác minh token chưa hết hạn, chưa nằm ngoài thời gian hiệu lực và xử lý clock skew theo giới hạn nhỏ có chủ đích. Không đặt clock skew quá lớn chỉ để chữa lỗi đồng hồ hạ tầng.

AS nên phát token có TTL phù hợp với rủi ro, còn RS cần đồng bộ thời gian bằng NTP/clock service đáng tin. `iat` trong tương lai quá xa có thể là tín hiệu token bất thường.

### 4.5. `jti` — định danh token

`jti` là định danh của JWT. Nó hữu ích cho audit, correlation, denylist/revocation bổ sung và điều tra sự cố mà không cần ghi raw token.

`jti` phải có tính duy nhất trong phạm vi issuer phù hợp. Không dùng cùng một `jti` cho nhiều token phát hành độc lập. `jti` không phải bí mật hoặc bearer credential.

### 4.6. `client_id` — client đã yêu cầu token

`client_id` xác định OAuth client yêu cầu token. Claim này khác `sub`:

- Trong user authorization, `sub` có thể là user, còn `client_id` là BFF/client.
- Trong Client Credentials, `sub` có thể đại diện workload, và `client_id` vẫn xác định client request.
- Trong delegated flow, `client_id` giúp truy vết client thực hiện yêu cầu trong khi `sub` có thể là user.

RS có thể dùng claim này cho policy theo client, audit hoặc quota, nhưng **không chỉ dựa vào `client_id` để cấp quyền nghiệp vụ**. Cần kiểm tra audience, scope và subject/context.

## 5. Claim `scope` và ánh xạ quyền

RFC 9068 biểu diễn scope bằng claim `scope` dạng **chuỗi chứa các scope phân tách bằng dấu cách**:

```json
{
  "scope": "bookings.read bookings.cancel"
}
```

Không nhầm chuỗi này với JSON array tự định nghĩa, claim `roles`, quyền sở hữu tài nguyên hoặc vai trò quản trị nội bộ.

Spring Security thường ánh xạ scope thành authority có prefix `SCOPE_`:

```text
bookings.read   -> SCOPE_bookings.read
bookings.cancel -> SCOPE_bookings.cancel
```

### 5.1. Cấu hình ánh xạ scope

```java
@Bean
JwtAuthenticationConverter jwtAuthenticationConverter() {
    JwtGrantedAuthoritiesConverter authoritiesConverter =
        new JwtGrantedAuthoritiesConverter();

    authoritiesConverter.setAuthoritiesClaimName("scope");
    authoritiesConverter.setAuthorityPrefix("SCOPE_");

    JwtAuthenticationConverter converter =
        new JwtAuthenticationConverter();

    converter.setJwtGrantedAuthoritiesConverter(authoritiesConverter);
    return converter;
}
```

Đoạn code dành cho **Resource Server**. Nếu claim `scope` được phát theo đúng profile, converter có thể đọc chuỗi scope phân tách bằng dấu cách. Nếu hệ thống dùng `roles` hoặc `permissions` riêng, cần converter riêng với semantics được định nghĩa rõ.

### 5.2. Scope không thay thế authorization nghiệp vụ

Token có `bookings.read` không nhất thiết được đọc mọi booking. API còn phải xác minh user có sở hữu booking đó không, booking thuộc tenant nào và trạng thái nghiệp vụ có cho phép hành động không.

```java
http.authorizeHttpRequests(authorize -> authorize
    .requestMatchers(HttpMethod.GET, "/bookings/**")
        .hasAuthority("SCOPE_bookings.read")
    .requestMatchers(HttpMethod.POST, "/bookings/*/cancel")
        .hasAuthority("SCOPE_bookings.cancel")
    .anyRequest().denyAll());
```

Đây là authorization ở mức HTTP route. Service/domain vẫn phải kiểm tra quyền trên đúng đối tượng dữ liệu, đặc biệt trong hệ thống multi-tenant.

## 6. Chọn profile phù hợp với Resource Server

Một Authorization Server có thể phục vụ nhiều Resource Server, mỗi API có identifier và scope riêng:

| Resource Server | Audience ví dụ | Scope ví dụ |
|---|---|---|
| Booking API | `https://booking-api.example.com` | `bookings.read`, `bookings.cancel` |
| Inventory API | `https://inventory-api.example.com` | `inventory.read` |
| Payment API | `https://payment-api.example.com` | `payments.status.read` |

### 6.1. Một token cho nhiều API có phải luôn tốt?

Không. Nếu token có nhiều audience, mọi API được liệt kê có thể trở thành đích chấp nhận token theo policy. Điều này làm tăng phạm vi ảnh hưởng khi token bị lộ và tạo rủi ro token substitution.

Ưu tiên token **audience hẹp**, chỉ dành cho API cần dùng. Nếu nghiệp vụ cần gọi nhiều API, có thể xin token riêng theo từng Resource Server hoặc dùng Token Exchange để đổi token sang audience đích theo policy.

### 6.2. Audience phải được quyết định phía server

Không lấy `aud` trực tiếp từ tham số request tùy ý rồi ghi vào JWT. AS cần mapping đáng tin giữa client registration, grant, resource được phép và audience. Nếu AS hỗ trợ tham số `resource` hoặc `audience`, phải kiểm tra client được phép xin token cho resource đó và scope tương ứng. Tham số caller gửi là **yêu cầu**, không phải quyền.

## 7. Cấu hình RegisteredClient để phát JWT access token

Trong Spring Authorization Server, `RegisteredClient` xác định grant, client authentication, scope và token settings. Để dùng JWT access token, cấu hình định dạng `SELF_CONTAINED`:

```java
RegisteredClient bookingBff = RegisteredClient
    .withId("booking-bff-internal-id")
    .clientId("booking-bff")
    .clientSecret(passwordEncoder.encode(secretFromSecureStore))
    .clientAuthenticationMethod(
        ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
    .authorizationGrantType(
        AuthorizationGrantType.AUTHORIZATION_CODE)
    .redirectUri("https://app.example.com/login/oauth2/code/booking-bff")
    .scope(OidcScopes.OPENID)
    .scope("bookings.read")
    .scope("bookings.cancel")
    .tokenSettings(TokenSettings.builder()
        .accessTokenFormat(OAuth2TokenFormat.SELF_CONTAINED)
        .accessTokenTimeToLive(Duration.ofMinutes(5))
        .build())
    .build();
```

Đây là ví dụ cấu hình mô hình client, chưa phải toàn bộ Authorization Server. Ứng dụng còn cần `RegisteredClientRepository`, `OAuth2AuthorizationService`, issuer, JWK source/khóa ký và `SecurityFilterChain` tương thích.

- `SELF_CONTAINED` chọn token tự chứa; cấu hình JWT signer/JWK phải có.
- TTL 5 phút chỉ là giá trị minh họa.
- Scope ở registration chỉ là các quyền client được phép yêu cầu, không đồng nghĩa mọi token đều nhận tất cả scope.
- `clientSecret` phải lấy từ secret manager và được bảo vệ phù hợp.
- Client authentication và user authentication là hai hoạt động khác nhau.

### 7.1. SELF_CONTAINED không tự bật RFC 9068

`OAuth2TokenFormat.SELF_CONTAINED` chọn dạng token tự chứa. Nó **không tự bảo đảm** token đáp ứng toàn bộ RFC 9068.

Cần xác minh hoặc tùy biến:

- Header `typ=at+jwt`.
- Các claims bắt buộc.
- Semantics của `sub`, `aud`, `client_id`.
- `scope` dạng chuỗi phân tách bằng dấu cách khi profile yêu cầu.
- Thuật toán ký bất đối xứng và quản lý khóa.
- RS kiểm tra đúng issuer, audience, token type và claims.

Đừng ghi “đã hỗ trợ RFC 9068” chỉ vì access token đang là JWT.

## 8. Tùy biến JWT bằng OAuth2TokenCustomizer

Spring Authorization Server cung cấp `OAuth2TokenCustomizer<JwtEncodingContext>` để bổ sung claims/header khi generator tạo JWT. Ví dụ sau minh họa profile cho access token của Booking API:

```java
@Bean
OAuth2TokenCustomizer<JwtEncodingContext> accessTokenProfileCustomizer() {
    return context -> {
        if (!OAuth2TokenType.ACCESS_TOKEN.equals(context.getTokenType())) {
            return;
        }

        context.getJwsHeader().type("at+jwt");

        context.getClaims().claim(
            "client_id",
            context.getRegisteredClient().getClientId());

        context.getClaims().audience(
            List.of("https://booking-api.example.com"));

        context.getClaims().claim(
            "scope",
            String.join(" ", context.getAuthorizedScopes()));

        if (AuthorizationGrantType.CLIENT_CREDENTIALS.equals(
                context.getAuthorizationGrantType())) {
            context.getClaims().subject(
                context.getRegisteredClient().getClientId());
        }
    };
}
```

Các import được lược bớt. Đây là **mẫu tùy biến profile**, cần đối chiếu API của phiên bản Spring Authorization Server trong dự án và kết hợp cấu hình JWK/issuer thực tế.

### 8.1. Chỉ tùy biến access token

`OAuth2TokenCustomizer` có thể được gọi cho nhiều loại token. Điều kiện `OAuth2TokenType.ACCESS_TOKEN` tránh vô tình thêm `typ=at+jwt` hoặc claim access token vào ID token.

Không sửa header ID token thành `at+jwt`. ID token phải tuân theo OIDC, có audience và semantics khác.

### 8.2. Claims generator có thể đã cung cấp

Spring Authorization Server có thể tạo claims tiêu chuẩn như issuer, subject, audience, thời gian phát hành, hết hạn, token ID và scope theo context. **Chi tiết mặc định phụ thuộc phiên bản và cấu hình.**

Vì vậy, customizer nên đặt rõ claim profile cần có mà implementation chưa tạo đúng; không tạo `jti` mới làm thay đổi giá trị framework quản lý nếu không cần; không ghi đè `iss`, `iat` hoặc `exp` tùy tiện; và kiểm tra payload token đã ký trong integration test.

Trong ví dụ, `client_id` được đặt rõ, audience lấy từ mapping server-side và scope được serialize thành chuỗi. Với hệ thống nhiều API, không hard-code một audience cho mọi client/grant; hãy dùng policy resolver phía server.

### 8.3. Semantics của `sub` theo grant

Ví dụ chỉ thay `sub` cho Client Credentials:

```java
if (AuthorizationGrantType.CLIENT_CREDENTIALS.equals(
        context.getAuthorizationGrantType())) {
    context.getClaims().subject(
        context.getRegisteredClient().getClientId());
}
```

Với Authorization Code đại diện người dùng, giữ subject đã xác thực theo nguồn identity tin cậy. Với Token Exchange, giữ subject/actor theo policy delegation. Không áp dụng phép gán `sub=client_id` cho mọi grant vì có thể làm mất danh tính người dùng.

### 8.4. Không copy toàn bộ claims từ ID token

Access token có thể cần một số thông tin identity để RS thực hiện authorization, nhưng không nên sao chép tất cả claims từ ID token. Giảm PII; tránh phát lộ email, phone, địa chỉ hoặc profile không cần thiết; tránh token quá lớn; dùng UserInfo hoặc API chuyên dụng khi client cần dữ liệu profile.

## 9. Định nghĩa contract claims cho từng API

Một contract mẫu cho Booking API:

```json
{
  "iss": "https://auth.example.com",
  "sub": "user-42",
  "aud": [
    "https://booking-api.example.com"
  ],
  "exp": 1794825600,
  "iat": 1794825300,
  "jti": "a-unique-token-id",
  "client_id": "booking-bff",
  "scope": "bookings.read bookings.cancel"
}
```

Đây là **payload minh họa**, không phải token đã ký.

| Claim | JSON type | Quy tắc của API |
|---|---|---|
| `iss` | string | Khớp issuer đã cấu hình |
| `sub` | string | Subject ổn định; không dùng làm quyền tự động |
| `aud` | string hoặc array string | Phải chứa audience của API |
| `exp` | number | NumericDate và còn hiệu lực |
| `iat` | number | NumericDate; không ở tương lai bất hợp lý |
| `jti` | string | Bắt buộc, định danh token |
| `client_id` | string | Bắt buộc, client đã yêu cầu token |
| `scope` | string | Space-delimited; chỉ scope API hiểu |

Không chỉ kiểm tra claim tồn tại; cần kiểm tra kiểu dữ liệu và giới hạn độ dài/phạm vi phù hợp. Nếu `aud` là mảng, API phải kiểm tra membership chính xác, không so sánh chuỗi JSON đã serialize.

### 9.1. Custom claims và namespace

Nếu cần thêm tenant, organization, entitlement hoặc actor context, xác định nguồn dữ liệu đáng tin, ai được phép nhận claim, Resource Server nào được phép diễn giải, schema/version, cách thay đổi claim và liệu có chứa PII hay không.

Ví dụ namespace:

```json
{
  "https://claims.example.com/tenant_id": "tenant-a",
  "https://claims.example.com/policy_version": "2026-11"
}
```

Tên trên chỉ là ví dụ. Tránh claim chung chung như `role` hoặc `permissions` nếu không có schema chung và ownership rõ.

## 10. Cấu hình Resource Server xác minh issuer, audience và type

Resource Server phải kiểm tra chữ ký bằng public key từ nguồn tin cậy, issuer, thời gian, audience và profile. Ví dụ dùng `NimbusJwtDecoder` với JWK Set URI:

```java
@Bean
JwtDecoder jwtDecoder() {
    String issuer = "https://auth.example.com";
    String jwkSetUri = "https://auth.example.com/oauth2/jwks";
    String expectedAudience = "https://booking-api.example.com";

    NimbusJwtDecoder decoder = NimbusJwtDecoder
        .withJwkSetUri(jwkSetUri)
        .jwsAlgorithm(SignatureAlgorithm.RS256)
        .build();

    OAuth2TokenValidator<Jwt> issuerAndTime =
        JwtValidators.createDefaultWithIssuer(issuer);

    OAuth2TokenValidator<Jwt> audience =
        jwt -> jwt.getAudience().contains(expectedAudience)
            ? OAuth2TokenValidatorResult.success()
            : OAuth2TokenValidatorResult.failure(
                new OAuth2Error(
                    "invalid_token",
                    "Required audience is missing",
                    null));

    OAuth2TokenValidator<Jwt> accessTokenType =
        jwt -> "at+jwt".equalsIgnoreCase(
                String.valueOf(jwt.getHeaders().get("typ")))
            ? OAuth2TokenValidatorResult.success()
            : OAuth2TokenValidatorResult.failure(
                new OAuth2Error(
                    "invalid_token",
                    "JWT is not an access token profile",
                    null));

    decoder.setJwtValidator(
        new DelegatingOAuth2TokenValidator<>(
            issuerAndTime,
            audience,
            accessTokenType,
            requiredProfileClaims()));

    return decoder;
}
```

Đoạn code là **mẫu Resource Server**; import và cấu hình `SecurityFilterChain` được lược bớt. JWK Set URI phải thuộc Authorization Server được tin cậy. Ví dụ chỉ cho phép RS256; nếu AS dùng ES256, cần cấu hình allowlist tương ứng và kiểm thử.

### 10.1. Validator cho claims bắt buộc

```java
private OAuth2TokenValidator<Jwt> requiredProfileClaims() {
    return jwt -> {
        boolean valid =
            jwt.getIssuer() != null
            && jwt.getSubject() != null
            && !jwt.getSubject().isBlank()
            && jwt.getAudience() != null
            && !jwt.getAudience().isEmpty()
            && jwt.getExpiresAt() != null
            && jwt.getIssuedAt() != null
            && jwt.getId() != null
            && !jwt.getId().isBlank()
            && jwt.getClaimAsString("client_id") != null
            && !jwt.getClaimAsString("client_id").isBlank();

        return valid
            ? OAuth2TokenValidatorResult.success()
            : OAuth2TokenValidatorResult.failure(
                new OAuth2Error(
                    "invalid_token",
                    "Required JWT access token claim is missing",
                    null));
    };
}
```

Validator bổ sung kiểm tra sự hiện diện claims theo contract. `JwtValidators.createDefaultWithIssuer` xử lý validation mặc định gồm issuer và timestamp; vẫn cần test trên phiên bản thực tế.

Nếu profile token không có `scope`, endpoint cần scope phải từ chối ở authorization layer. Không nhất thiết bắt mọi token của hệ thống phải có scope nếu có use case hợp lệ không phát scope.

### 10.2. Pin thuật toán

Không để token header tự quyết định mọi thuật toán được chấp nhận. RS phải có allowlist phù hợp key material và policy, đồng thời từ chối:

- `alg=none`.
- Thuật toán không được tổ chức cho phép.
- Key type/algorithm mismatch.
- Thuật toán yếu hoặc legacy đã bị loại bỏ.

RFC 9068 yêu cầu chữ ký bất đối xứng cho JWT access token profile. Không thay bằng HMAC shared secret nếu mục tiêu là profile RFC 9068.

### 10.3. Không lấy JWK Set URI từ token

RS chỉ lấy public keys từ URI cấu hình tin cậy hoặc metadata issuer đã xác minh. Không đọc `jku` hoặc `x5u` do token gửi rồi tự tải khóa từ URL đó; hành vi này có thể dẫn đến SSRF và cho attacker kiểm soát nguồn khóa.

## 11. Scope và endpoint authorization trong Spring Security

Một cấu hình Resource Server có thể gắn decoder và converter:

```java
@Bean
SecurityFilterChain apiSecurity(
        HttpSecurity http,
        JwtDecoder jwtDecoder,
        JwtAuthenticationConverter jwtAuthenticationConverter)
        throws Exception {

    http
        .authorizeHttpRequests(authorize -> authorize
            .requestMatchers(HttpMethod.GET, "/bookings/**")
                .hasAuthority("SCOPE_bookings.read")
            .requestMatchers(HttpMethod.POST, "/bookings/*/cancel")
                .hasAuthority("SCOPE_bookings.cancel")
            .anyRequest().denyAll())
        .oauth2ResourceServer(resourceServer ->
            resourceServer.jwt(jwt -> jwt
                .decoder(jwtDecoder)
                .jwtAuthenticationConverter(jwtAuthenticationConverter)));

    return http.build();
}
```

Đây là chain của **Booking Resource Server**, không phải Authorization Server. Nếu cùng một ứng dụng vừa chạy AS vừa cung cấp API, cần tách `SecurityFilterChain` và thứ tự matcher đúng cho hai vai trò.

### 11.1. Đừng ánh xạ mọi claim thành quyền

Không tự động biến `tenant_id` thành `ROLE_ADMIN` hoặc biến `groups` thành authority mà không có mapping rõ. Claim là dữ liệu do issuer ký, nhưng semantics vẫn do hợp đồng ứng dụng định nghĩa.

Giữ ranh giới giữa authentication, coarse-grained authorization theo scope và fine-grained authorization theo đúng record/tenant.

## 12. `cnf` và sender-constrained access token

JWT Bearer access token thông thường có thể bị bất kỳ ai sở hữu token sử dụng trước khi hết hạn. Nếu threat model yêu cầu giảm rủi ro token bị đánh cắp, có thể xem xét mTLS certificate-bound access token theo RFC 8705 hoặc DPoP theo RFC 9449.

Ví dụ cấu trúc claim:

```json
{
  "cnf": {
    "x5t#S256": "BASE64URL_CERTIFICATE_THUMBPRINT"
  }
}
```

Đây chỉ là ví dụ dạng claim, không phải cấu hình mTLS hoàn chỉnh. Resource Server phải xác minh request thực sự được ràng buộc với chứng chỉ/khóa tương ứng. **Chỉ kiểm tra `cnf` mà không xác minh proof/certificate không tạo ra sender constraint.**

Không phát claim `cnf` dựa trên header do caller gửi. Claim phải đến từ kết quả xác thực ràng buộc đáng tin tại AS.

## 13. JWT TTL, revocation và thay đổi quyền

JWT tự chứa giúp RS xác minh cục bộ, nhưng token đã phát hành có thể còn hợp lệ tới `exp` nếu RS không kiểm tra trạng thái thu hồi.

| Sự kiện | Tác động thường gặp |
|---|---|
| Giảm `accessTokenTimeToLive` | Token mới ngắn hơn; token cũ không tự đổi `exp` |
| Thu hồi refresh token | Ngăn refresh đó cấp token mới; access token đang sống cần policy riêng |
| Disable client | Có thể chặn issuance mới; JWT cũ không tự biến mất |
| Gỡ scope khỏi client | Token cũ vẫn có thể chứa scope đã phát hành |
| Xoay khóa ký AS | RS cần nhận key mới và vẫn xác minh token còn sống được ký bằng key cũ trong overlap |
| Revoke JWT theo `jti` | Chỉ có hiệu lực ngay nếu RS kiểm tra denylist/introspection hoặc cơ chế tương ứng |

Các lựa chọn gồm TTL ngắn, opaque/reference token với introspection, denylist theo `jti`, token version hoặc sender-constrained token. Mỗi phương án có chi phí latency/state/availability riêng.

**JWT signature validation đơn thuần không cung cấp revocation tức thời.**

## 14. JWKS và signing key rotation

AS ký JWT bằng private key; RS xác minh bằng public key được công bố qua JWKS. Header `kid` giúp RS chọn đúng key.

Quy trình xoay khóa an toàn:

1. Tạo signing key mới trong KMS/HSM hoặc key store được bảo vệ.
2. Công bố public key mới trong JWKS cùng key cũ.
3. Chờ các RS/cache có cơ hội tải key mới.
4. Chuyển AS sang ký token mới bằng key mới.
5. Theo dõi lỗi signature verification và cache miss.
6. Giữ public key cũ đủ lâu để xác minh token cũ còn hạn và theo cache/rollout policy.
7. Chỉ loại key cũ khi không còn token hợp lệ cần xác minh hoặc có kế hoạch thu hồi rõ.

Không xóa public key cũ ngay khi bắt đầu ký bằng key mới; token cũ có thể bị từ chối trước `exp`.

### 14.1. `kid` không phải bằng chứng tin cậy

`kid` chỉ là selector. RS vẫn phải lấy khóa từ JWK Set tin cậy, kiểm tra key type, algorithm và chữ ký. Không dùng `kid` như URL hoặc cho phép nó điều khiển đường dẫn đọc file.

### 14.2. JWKS cache và sự cố key lookup

Khi RS gặp `kid` chưa có trong cache, thư viện có thể tải JWKS mới. Cần giới hạn timeout/retry và kiểm soát tải để tránh một token giả có `kid` ngẫu nhiên kích hoạt quá nhiều request tới AS.

Dùng JWK source framework quản lý, kiểm tra cache behavior và theo dõi lỗi key retrieval. Không tự tải JWKS cho mỗi API request.

## 15. Claims nhạy cảm, privacy và token size

JWT thường được ký nhưng **không được mã hóa** trong profile JWS thông dụng. Người sở hữu token có thể decode payload. Vì vậy, không đưa password, client secret, API key, private key, dữ liệu thanh toán hoặc PII không cần thiết vào claims.

Nên ưu tiên subject identifier ổn định nhưng ít tiết lộ, scope tối thiểu, audience hẹp và custom claims thực sự cần cho authorization. Nếu API cần dữ liệu biến động, truy vấn nguồn dữ liệu đáng tin thay vì nhúng mọi thứ vào token.

### 15.1. Không dùng JWT làm database snapshot

Ví dụ user bị xóa khỏi tenant nhưng JWT có `tenant_role=admin` còn sống thêm 30 phút. Nếu RS chỉ tin claim cũ, quyền có thể tồn tại sau khi nghiệp vụ đã thay đổi.

Với dữ liệu thay đổi nhanh hoặc cần thu hồi ngay, cần kiểm tra trạng thái tại service/authorization store hoặc giảm TTL phù hợp.

## 16. Tách access token profile khỏi token response

Token Endpoint trả một response OAuth như:

```http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "access_token": "SIGNED_JWT_VALUE",
  "token_type": "Bearer",
  "expires_in": 300,
  "scope": "bookings.read"
}
```

Hai loại `typ` dễ bị nhầm:

- JOSE header trong JWT: `typ=at+jwt` — loại JWT theo RFC 9068.
- Token response: `token_type=Bearer` — cách client dùng token trong HTTP Authorization header.

**`token_type` không thay thế JOSE `typ`.** Response nói `Bearer` không chứng minh token là RFC 9068 JWT access token. Token response cần cache directive phù hợp, thường `Cache-Control: no-store` và `Pragma: no-cache`.

## 17. Những lỗi triển khai thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Chỉ xác minh chữ ký | Nhận token sai issuer/audience/mục đích | Validate profile đầy đủ |
| Chấp nhận mọi JWT do cùng AS ký | ID token/assertion có thể bị dùng nhầm | Kiểm tra `typ=at+jwt` và audience |
| Bỏ qua `aud` | Token API A có thể dùng tại API B | Audience validator riêng từng RS |
| Dùng `client_id` làm audience | Nhầm requesting client với resource | Dùng resource identifier |
| Thiếu `client_id` hoặc `jti` | Không đạt claim contract profile | Đảm bảo claim bắt buộc và test |
| `scope` dạng array khi profile yêu cầu string | Interoperability không nhất quán | Serialize space-delimited string |
| Gán `sub` bằng email | Đổi email có thể đổi identity; lộ PII | Subject ổn định, ít tiết lộ |
| Gán `sub=client_id` cho mọi grant | Mất subject user trong user flow | Chọn semantics theo grant |
| Customizer access token làm thay đổi ID token | OIDC RP có thể lỗi | Chỉ customizer khi token type là ACCESS_TOKEN |
| Chọn `SELF_CONTAINED` rồi tuyên bố RFC 9068 | JWT format không đồng nghĩa profile | Kiểm tra header và required claims |
| Dùng HMAC shared secret nhưng tuyên bố RFC 9068 | Sai yêu cầu chữ ký bất đối xứng | Dùng asymmetric signing |
| RS tự tải `jku` từ token | SSRF/trust arbitrary key | Chỉ dùng JWKS URI tin cậy |
| Xóa key cũ ngay sau rotation | Token cũ không xác minh được | Overlap key theo TTL/cache |
| Tin `cnf` mà không xác minh proof | Sender constraint giả | Xác minh certificate/DPoP proof |
| Nhúng PII và quyền quá rộng | Token lộ gây tác động lớn | Data minimization, audience/scope hẹp |
| Chỉ test token thành công | Không phát hiện token substitution | Test ID token, issuer/audience/type sai |

## 18. Kiểm thử profile tại Authorization Server

Cần kiểm tra token **sau khi generator tạo và ký**, không chỉ test customizer bean.

### 18.1. Kiểm tra header và claims

| Thành phần | Kết quả cần có |
|---|---|
| JOSE `typ` | `at+jwt` |
| JOSE `alg` | Thuật toán asymmetric trong allowlist |
| JOSE `kid` | Khớp một key trong JWKS tin cậy |
| `iss` | Issuer đã cấu hình |
| `sub` | Subject phù hợp grant |
| `aud` | Resource Server đích |
| `exp` | Thời điểm hết hạn hợp lệ |
| `iat` | Thời điểm phát hành |
| `jti` | Định danh không rỗng và duy nhất |
| `client_id` | Client đã yêu cầu token |
| `scope` | Chuỗi space-delimited nếu được phát hành |

Nếu framework đã tạo claim, test vẫn phải xác minh nó đúng; không cần tùy biến lại chỉ để test pass.

### 18.2. Test theo từng grant

- Authorization Code: `sub` là user đã xác thực, `client_id` là client request, `aud` là API dự kiến.
- Client Credentials: `sub` phản ánh workload/client theo profile, `client_id` xác định client.
- Token Exchange: `sub` và actor context theo chính sách delegation, audience mới được kiểm tra chặt.
- Refresh Token: access token mới giữ đúng semantics subject/client và áp dụng scope/TTL hiện hành.

Không giả định một bộ claim giống hệt nhau cho mọi grant. Contract cốt lõi cần nhất quán nhưng giá trị subject và quyền phải phù hợp ngữ cảnh.

## 19. Kiểm thử Resource Server với Spring Security

### 19.1. Ma trận positive/negative

| Trường hợp | Token | Kết quả mong đợi |
|---|---|---|
| Token profile hợp lệ | Đúng issuer, key, `typ`, audience, expiry, claims | Được xác thực; authorization theo scope |
| Sai issuer | `iss` từ nguồn không tin | 401 |
| Sai audience | `aud` không chứa API hiện tại | 401 |
| ID token | `typ` không phải `at+jwt` hoặc audience là client | 401 |
| JWT assertion | JWT ký đúng nhưng sai mục đích/audience/type | 401 |
| Sai chữ ký | Token bị sửa payload | 401 |
| `alg=none` | Không có chữ ký tin cậy | 401 |
| Thuật toán ngoài allowlist | Algorithm ngoài policy | 401 |
| Hết hạn | `exp` đã qua | 401 |
| Chưa tới `nbf` | Token chưa có hiệu lực | 401 |
| Thiếu `client_id` | Vi phạm profile contract | 401 |
| Thiếu `jti` | Vi phạm profile contract | 401 |
| Thiếu `sub` | Vi phạm profile contract | 401 |
| Thiếu scope | Token không có quyền endpoint cần | 403 |
| Scope khác | Có `inventory.read` nhưng gọi Booking API | 403 hoặc 401 theo policy/audience |
| Token cũ sau key rotation | `kid` cũ còn trong JWKS overlap | Được xác minh nếu vẫn hợp lệ |
| Token có `cnf` nhưng request thiếu proof | Sender-constrained policy | Bị từ chối |

### 19.2. Test audience validator

Có thể tạo Jwt giả lập để unit test validator trả success/failure. Tuy nhiên, cần integration test với `JwtDecoder` thật để kiểm tra cả chữ ký, header, issuer, audience và timestamp.

Không mock mọi validator rồi kết luận Resource Server đã tuân thủ RFC 9068. Test phải đi qua cấu hình decoder thực tế.

### 19.3. Test scope authorization

Dùng `MockMvc`/HTTP integration test để xác minh:

- Token có `bookings.read` gọi GET thành công.
- Token chỉ có `inventory.read` gọi GET Booking bị từ chối.
- Token có `bookings.read` nhưng không có `bookings.cancel` gọi POST cancel bị từ chối.
- Token hợp lệ nhưng subject không sở hữu record bị từ chối ở domain layer.
- Token đúng scope nhưng sai tenant không thể đọc record tenant khác.

Những test này chứng minh authentication và authorization là hai lớp riêng.

## 20. Vận hành, observability và xử lý sự cố

### 20.1. Metric nên theo dõi

- Tỷ lệ token bị từ chối theo nguyên nhân: signature, issuer, audience, expiry, type, missing claim.
- Tỷ lệ `401` và `403` theo Resource Server/route.
- Tỷ lệ key ID chưa có trong JWKS cache và thời gian tải JWKS.
- Token issuance latency và lỗi signing/KMS.
- Token size distribution và lỗi header quá lớn.
- Thời gian từ khi AS rotate key đến khi RS xác minh được key mới.
- Số token sắp hết hạn/đang dùng theo profile và audience nếu có cơ chế đo phù hợp.

Không đưa raw JWT, subject PII, token ID không giới hạn hoặc toàn bộ audience động vào metric label. Dùng nhóm lỗi, issuer/resource đã chuẩn hóa và correlation ID an toàn.

### 20.2. Audit không được chứa token

Có thể ghi event type `ACCESS_TOKEN_ISSUED`, `JWT_VALIDATION_FAILED`, `SIGNING_KEY_ROTATED`; client ID và issuer theo chính sách; audience, grant type, scope đã chuẩn hóa; `jti` hoặc pseudonym phù hợp nếu cần điều tra; thời điểm, correlation ID, mã lỗi và key ID.

Không ghi raw access token, ID token, refresh token, client secret hoặc private signing key.

### 20.3. Khi RS đột ngột trả 401 hàng loạt

Điều tra theo thứ tự:

1. AS có đổi issuer hoặc cấu hình `iss` không?
2. Token mới có đúng `aud` và `typ` không?
3. RS có tải được JWKS không; `kid` mới đã xuất hiện chưa?
4. Thuật toán ký có còn trong allowlist của RS?
5. Đồng hồ AS/RS có lệch gây token chưa hợp lệ hoặc hết hạn sớm?
6. Customizer có đổi semantics `sub`/`scope` hoặc serialize sai kiểu claim?
7. Có deployment nào vô tình dùng ID token thay access token?
8. Cache/JWKS/decoder có đang giữ cấu hình cũ?

Không chữa 401 bằng cách bỏ audience validation hoặc chấp nhận mọi issuer. Hãy sửa contract/rollout key đúng nguyên nhân.

## 21. Checklist áp dụng RFC 9068

- [ ] AS phát access token dạng JWT khi use case và token format yêu cầu.
- [ ] JOSE header dùng `typ=at+jwt` cho access token profile.
- [ ] JWT được ký bằng thuật toán asymmetric trong allowlist.
- [ ] `iss` là issuer đáng tin và ổn định.
- [ ] `sub` biểu diễn đúng subject theo từng grant.
- [ ] `aud` chỉ rõ Resource Server đích; RS xác minh membership chính xác.
- [ ] `exp` và `iat` hợp lệ; clock skew có giới hạn.
- [ ] `jti` có giá trị duy nhất phù hợp.
- [ ] `client_id` xác định client yêu cầu token.
- [ ] `scope` có semantics và encoding đúng; RS ánh xạ scope thành authority.
- [ ] Không dùng ID token thay access token.
- [ ] Không chấp nhận token chỉ vì chữ ký hợp lệ.
- [ ] Không tải JWK từ URL do token tự khai.
- [ ] Có quy trình JWKS/key rotation với overlap đủ thời gian.
- [ ] Có policy revocation/TTL phù hợp với yêu cầu ngắt quyền.
- [ ] Claims custom tối thiểu, không chứa bí mật/PII không cần thiết.
- [ ] Test token hợp lệ, sai issuer/audience/type/alg/exp và thiếu claims.
- [ ] Test 401/403, scope và ownership/tenant tại API.
- [ ] Metrics/audit không lưu raw JWT hoặc secret.

### Kiến thức cốt lõi

**RFC 9068 định nghĩa profile cho OAuth 2.0 access token được biểu diễn bằng JWT.** Profile này không đồng nghĩa với mọi JWT có chữ ký và không được nhầm với OIDC ID token. Một Resource Server cần xác minh chữ ký bằng khóa tin cậy, thuật toán được cho phép, issuer, audience, thời gian, JOSE `typ=at+jwt` và các claims bắt buộc.

Trong Spring Authorization Server, `SELF_CONTAINED` chọn JWT format; `OAuth2TokenCustomizer<JwtEncodingContext>` giúp hoàn thiện header/claims theo contract. Trong Spring Security Resource Server, `JwtDecoder`, validators và authority converter thực thi kiểm tra. Chỉ khi **AS phát và RS xác minh cùng một profile rõ ràng**, JWT access token mới có thể được dùng an toàn và nhất quán giữa các dịch vụ.

## Tài liệu tham khảo

- [RFC 9068 — JSON Web Token (JWT) Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515)
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517)
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414)
- [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705)
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449)
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700)
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html)
- [Spring Authorization Server — Core Model / Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html)
- [Spring Authorization Server — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html)
- [Spring Security — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
