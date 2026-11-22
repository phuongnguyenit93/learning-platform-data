# Authorization Code, Access Token, Refresh Token và ID Token

Trong OAuth 2.0 và OpenID Connect (OIDC), bốn giá trị **Authorization Code**, **Access Token**, **Refresh Token** và **ID Token** có nhiệm vụ khác nhau. Hiểu đúng ranh giới giữa chúng là nền tảng để thiết kế, cấu hình, bảo mật, kiểm thử và vận hành **OAuth 2.0/OpenID Connect Authorization Server bằng Spring Security và Spring Authorization Server trong ứng dụng Spring Boot**.

## 1. Bối cảnh: ai phát hành, ai sử dụng?

Một hệ thống điển hình có các thành phần:

- **Resource Owner / End User:** người dùng sở hữu dữ liệu và thực hiện đăng nhập, đồng ý cấp quyền khi cần.
- **Client:** ứng dụng muốn truy cập API thay mặt người dùng; có thể là ứng dụng web có backend, SPA, ứng dụng di động hoặc ứng dụng máy chủ.
- **Authorization Server (AS):** xác thực người dùng, xử lý yêu cầu ủy quyền, phát hành và quản lý các mã/token. Đây là vai trò mà Spring Authorization Server đảm nhiệm.
- **Resource Server (RS):** API bảo vệ tài nguyên; xác minh Access Token và thực thi chính sách truy cập. Spring Security Resource Server thường đảm nhiệm vai trò này.

**OAuth 2.0** giải quyết việc *ủy quyền truy cập tài nguyên*. **OIDC**, xây dựng trên OAuth 2.0, bổ sung cơ chế *xác thực danh tính* và phát hành ID Token. Vì vậy, việc một ứng dụng nhận được Access Token không tự động có nghĩa là ứng dụng đã thực hiện đầy đủ quy trình đăng nhập OIDC.

| Giá trị | Dùng để làm gì? | Bên sử dụng chính | Đặc tính tiêu biểu |
| --- | --- | --- | --- |
| **Authorization Code** | Đại diện tạm thời cho kết quả của bước ủy quyền để đổi lấy token | Client gửi đến AS | Ngắn hạn, chỉ dùng một lần, gắn với một giao dịch ủy quyền |
| **Access Token** | Cho phép gọi tài nguyên/API trong phạm vi được cấp | Client gửi đến RS | Có thời hạn; có thể là JWT hoặc chuỗi opaque |
| **Refresh Token** | Xin Access Token mới mà không cần lặp lại tương tác đăng nhập/ủy quyền | Client gửi đến AS | Thường sống lâu hơn Access Token; phải bảo vệ nghiêm ngặt |
| **ID Token** | Chuyển thông tin xác thực người dùng từ AS đến OIDC Client | OIDC Client kiểm tra và sử dụng | Thường là JWT có chữ ký, chứa các claim chuẩn như `iss`, `sub`, `aud` |

Không nên suy ra chức năng từ việc các giá trị trông giống nhau: **JWT là một định dạng token, không phải một loại quyền**. Access Token có thể là JWT, ID Token thường là JWT, còn Authorization Code và Refresh Token thường là những chuỗi mà chỉ AS hiểu.

## 2. Chúng xuất hiện ở đâu trong Authorization Code Flow?

Ví dụ: một ứng dụng web dùng OIDC để đăng nhập rồi gọi API `/api/orders` với quyền `orders.read`.

```mermaid
sequenceDiagram
    autonumber
    actor U as Người dùng
    participant B as Trình duyệt
    participant C as Client (backend/BFF)
    participant AS as Authorization Server
    participant RS as Resource Server (API)
    U->>B: Chọn Đăng nhập
    B->>C: Yêu cầu trang cần đăng nhập
    C-->>B: Chuyển đến /oauth2/authorize
    B->>AS: response_type=code, state, PKCE, scope=openid ...
    AS->>U: Xác thực và xin đồng ý (nếu cần)
    AS-->>B: 302 redirect_uri?code=...&state=...
    B->>C: Gửi Authorization Code về callback
    C->>C: Kiểm tra state, lấy code_verifier đã lưu
    C->>AS: POST /oauth2/token: code + code_verifier + xác thực client
    AS-->>C: Access Token; ID Token (OIDC); Refresh Token (nếu cấp)
    C->>C: Kiểm tra ID Token và tạo phiên ứng dụng
    C->>RS: Authorization: Bearer <access_token>
    RS->>RS: Kiểm tra token và quyền orders.read
    RS-->>C: Dữ liệu đơn hàng
    C-->>B: Trang hoặc kết quả cho người dùng
```

Những điểm cần nhận ra:

1. **Authorization Code đi qua trình duyệt** ở bước chuyển hướng, nhưng **Access Token không cần xuất hiện trong URL chuyển hướng** của Authorization Code Flow.
2. Client đổi code tại **Token Endpoint**; chính ở bước này mới nhận các token.
3. **ID Token chỉ xuất hiện khi thực hiện OIDC** (ví dụ có scope `openid`, OIDC được bật và yêu cầu hợp lệ). **Refresh Token phụ thuộc grant type và chính sách cấp token**, không được bảo đảm có trong mọi phản hồi.
4. Sau khi Access Token hết hạn, client có thể dùng Refresh Token tại Token Endpoint nếu đã được cấp và còn hợp lệ.

## 3. Authorization Code: vé một lần để đổi token

### 3.1. Tạo yêu cầu ủy quyền

Với Spring Authorization Server, Authorization Endpoint mặc định là `/oauth2/authorize`. Ví dụ minh họa (các giá trị trong dấu `<...>` là placeholder):

```http
GET /oauth2/authorize?response_type=code
    &client_id=web-client
    &redirect_uri=https%3A%2F%2Fclient.example.com%2Fcallback
    &scope=openid%20profile%20orders.read
    &state=<random-state>
    &code_challenge=<base64url-sha256-verifier>
    &code_challenge_method=S256
    &nonce=<random-nonce>
Host: auth.example.com
```

| Tham số | Vai trò |
| --- | --- |
| `response_type=code` | Yêu cầu Authorization Code Flow |
| `client_id` | Xác định client đã đăng ký với AS |
| `redirect_uri` | Nơi AS trả trình duyệt về; phải phù hợp URI đã đăng ký |
| `scope` | Những quyền/phạm vi client yêu cầu; `openid` đánh dấu yêu cầu OIDC |
| `state` | Giá trị ngẫu nhiên do client tạo, dùng liên kết response với phiên yêu cầu và chống CSRF |
| `code_challenge` và `code_challenge_method=S256` | Bằng chứng PKCE dẫn xuất từ bí mật `code_verifier` mà client đang giữ |
| `nonce` | Giá trị liên kết yêu cầu xác thực OIDC với ID Token nhận được để chống phát lại |

Sau khi xử lý xác thực/ủy quyền, AS chuyển hướng:

```http
HTTP/1.1 302 Found
Location: https://client.example.com/callback?code=<authorization-code>&state=<same-state>
```

Client phải kiểm tra `state` trước khi dùng `code`. Nếu người dùng từ chối cấp quyền hoặc xảy ra lỗi, AS có thể trả `error` tại redirect URI thay vì trả `code`.

### 3.2. Đổi code lấy token

Backend của **confidential client** (client có thể giữ bí mật) thường xác thực bằng `client_secret_basic`. Ví dụ rút gọn:

```http
POST /oauth2/token HTTP/1.1
Host: auth.example.com
Authorization: Basic <base64(client_id:client_secret)>
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code&
code=<authorization-code>&
redirect_uri=https%3A%2F%2Fclient.example.com%2Fcallback&
code_verifier=<original-random-verifier>
```

AS kiểm tra code còn hiệu lực, chưa được dùng, thuộc đúng client và phù hợp redirect URI; nếu có PKCE thì phải kiểm tra `code_verifier` tương ứng với challenge trước đó. **Public client** (như SPA/native app) không có `client_secret` đáng tin cậy: thường gửi `client_id`, dùng PKCE và không giả vờ bảo vệ secret trong mã frontend.

Một phản hồi minh họa:

```json
{
  "access_token": "<access-token>",
  "token_type": "Bearer",
  "expires_in": 600,
  "scope": "openid profile orders.read",
  "refresh_token": "<refresh-token-if-issued>",
  "id_token": "<id-token-if-oidc>"
}
```

Các trường `refresh_token` và `id_token` trong ví dụ chỉ xuất hiện khi điều kiện phát hành tương ứng được đáp ứng. Giá trị `expires_in` là số giây hiệu lực của Access Token. Đây là phản hồi minh họa, không phải token có thể sử dụng.

### 3.3. Vì sao cần PKCE dù đã có code?

Nếu một Authorization Code bị lộ qua callback, lịch sử trình duyệt hoặc cơ chế chuyển hướng không an toàn, kẻ tấn công có thể thử đổi code tại Token Endpoint. PKCE ràng buộc code với bên nắm `code_verifier`:

```text
code_verifier  = chuỗi ngẫu nhiên có entropy cao, client giữ kín
code_challenge = BASE64URL(SHA256(ASCII(code_verifier)))
code_challenge_method = S256
```

Client gửi **challenge** trước; khi đổi code mới gửi **verifier**. AS so khớp chúng. Không đặt `code_verifier` vào URL ủy quyền, không tái sử dụng cùng verifier cho mọi giao dịch. Nên dùng PKCE (`S256`) cho cả public client và confidential client.

Ba cơ chế bảo vệ những mối đe dọa khác nhau: `state` liên kết callback với yêu cầu do client khởi tạo, **PKCE** ràng buộc việc đổi code với client giữ verifier, còn `nonce` liên kết **ID Token** với yêu cầu OIDC. Chúng không thay thế cho nhau.

## 4. Access Token: bằng chứng quyền truy cập API

Access Token được client trình cho Resource Server, thông thường qua HTTP header:

```http
GET /api/orders HTTP/1.1
Host: api.example.com
Authorization: Bearer <access-token>
```

Resource Server quyết định có chấp nhận yêu cầu hay không dựa trên token và chính sách của API. Một Access Token hợp lệ về mặt chữ ký **chưa đủ** nếu đã hết hạn, không thuộc issuer được tin cậy, không dành cho API đó, hoặc thiếu scope cần thiết.

### 4.1. JWT hay opaque token?

| Kiểu Access Token | Cách Resource Server kiểm tra | Đặc điểm vận hành |
| --- | --- | --- |
| **JWT có chữ ký** | Kiểm tra chữ ký bằng khóa công khai/JWKS, issuer, thời hạn, audience nếu được áp dụng, cùng quyền liên quan | Kiểm tra cục bộ nhanh; token tự chứa thường không bị thu hồi tức thì chỉ bằng việc xóa bản ghi phía AS |
| **Opaque token** | Gọi Token Introspection Endpoint trên AS (hoặc cơ chế tra cứu hợp lệ khác) | Trạng thái hiệu lực có thể được kiểm tra tập trung; phụ thuộc kết nối đến AS và chính sách cache |

Đừng giải mã JWT rồi tin ngay payload: nội dung JWT thông thường chỉ được mã hóa Base64URL để vận chuyển, **không được giữ bí mật**, và các claim chỉ đáng tin sau khi kiểm tra chữ ký cùng các điều kiện cần thiết.

Với JWT Access Token, các claim thường gặp gồm `iss` (issuer), `sub` (subject), `exp` (hết hạn), `iat` (thời điểm phát hành), `aud` (audience, nếu được cấp), `scope` hoặc `scp`. Không phải mọi JWT Access Token đều có cùng bộ claim; điều này phụ thuộc profile và cấu hình của AS. API phải kiểm tra audience phù hợp **nếu hệ thống sử dụng audience để ràng buộc token với API**; không được mặc nhiên coi mọi token từ cùng issuer đều được gọi mọi API.

### 4.2. Scope không đồng nghĩa với vai trò hay danh tính

Ví dụ `orders.read` biểu diễn quyền đọc đơn hàng mà token được cấp. Trong Spring Security Resource Server, các scope được chuyển thành authority dạng `SCOPE_orders.read` trong cấu hình JWT phổ biến. API có thể dùng:

```java
http.authorizeHttpRequests(authorize -> authorize
        .requestMatchers("/api/orders/**").hasAuthority("SCOPE_orders.read")
        .anyRequest().authenticated())
    .oauth2ResourceServer(oauth2 -> oauth2.jwt(Customizer.withDefaults()));
```

Đoạn trên là **một phần cấu hình `SecurityFilterChain`**, không phải một ứng dụng chạy độc lập. Ngoài scope, API thường còn phải kiểm tra quyền sở hữu tài nguyên hoặc chính sách nghiệp vụ, chẳng hạn người dùng A không được đọc đơn hàng riêng của người dùng B chỉ vì cả hai có `orders.read`.

## 5. Refresh Token: lấy token mới mà không đăng nhập lại

Access Token nên có thời hạn tương đối ngắn để giảm tác động nếu bị lộ. Khi Access Token hết hạn, client có thể gửi Refresh Token đã nhận về **Authorization Server**, không gửi Refresh Token cho API:

```http
POST /oauth2/token HTTP/1.1
Host: auth.example.com
Authorization: Basic <base64(client_id:client_secret)>
Content-Type: application/x-www-form-urlencoded

grant_type=refresh_token&
refresh_token=<refresh-token>
```

AS kiểm tra Refresh Token, client và quyền được cấp rồi trả Access Token mới; tùy cấu hình có thể trả **Refresh Token mới**. Yêu cầu refresh không đồng nghĩa với việc được tự ý tăng scope. Nếu người dùng đã thu hồi quyền, phiên đã bị vô hiệu, hoặc Refresh Token hết hạn/bị thu hồi, AS có thể trả lỗi như `invalid_grant` và client phải yêu cầu ủy quyền lại.

### 5.1. Refresh Token rotation và bảo vệ lưu trữ

**Rotation** nghĩa là mỗi lần refresh thành công, AS phát hành Refresh Token mới và làm token cũ không còn dùng được. Điều này giúp giảm khả năng sử dụng lại token đã bị đánh cắp; để phát hiện phát lại và thu hồi cả chuỗi token một cách hiệu quả, hệ thống cần có chính sách quản lý token family/reuse detection tương ứng. Đừng mặc định bật rotation đã tự tạo đầy đủ cơ chế phát hiện xâm nhập.

- Với backend/BFF, nên lưu Refresh Token ở phía server, hạn chế quyền đọc và mã hóa dữ liệu lưu trữ phù hợp.
- Với ứng dụng native, dùng vùng lưu trữ an toàn của hệ điều hành; dùng system browser và PKCE cho luồng đăng nhập.
- Với ứng dụng thuần trình duyệt, coi token là dữ liệu nhạy cảm trước XSS; ưu tiên kiến trúc BFF/session phía server khi phù hợp. Tránh lưu Refresh Token lâu dài trong `localStorage`.
- Không ghi Access Token, Refresh Token, code hoặc client secret vào log, URL, hệ thống analytics hay thông báo lỗi.
- Việc thu hồi token tự chứa dạng JWT thường cần thêm thiết kế (TTL ngắn, denylist hoặc kiểm tra trạng thái); **revoke Refresh Token không mặc nhiên làm mọi JWT Access Token đã cấp mất hiệu lực ngay**.

Refresh Token không phải bằng chứng để API cho phép truy cập và cũng không phải ID Token. Client có thể không được cấp Refresh Token tùy loại client, grant, consent và chính sách của Authorization Server.

## 6. ID Token: kết quả xác thực trong OpenID Connect

Khi client yêu cầu và hoàn tất đăng nhập **OIDC** (chẳng hạn scope chứa `openid`), AS phát hành **ID Token** cho OIDC Client. ID Token là JWT chứa các claim cho phép client xác minh **ai đã được xác thực, bởi issuer nào, dành cho client nào và trong thời hạn nào**.

Payload ví dụ (đã lược bỏ header/chữ ký):

```json
{
  "iss": "https://auth.example.com",
  "sub": "user-123",
  "aud": "web-client",
  "iat": 1893455700,
  "exp": 1893456000,
  "nonce": "nonce-in-original-request",
  "auth_time": 1893455500
}
```

| Claim | Ý nghĩa và cách sử dụng |
| --- | --- |
| `iss` | Định danh issuer; client phải so với issuer tin cậy đã cấu hình |
| `sub` | Định danh người dùng tại issuer; nên kết hợp `iss` + `sub` làm khóa danh tính ổn định |
| `aud` | Client ID của bên nhận (có thể là danh sách); phải chứa client ID hiện tại |
| `exp`, `iat` | Thời gian hết hạn và phát hành; phải kiểm tra các ràng buộc thời gian theo chính sách |
| `nonce` | Nếu yêu cầu đã gửi nonce, client phải so sánh với giá trị lưu cho giao dịch đó |
| `auth_time` | Thời điểm xác thực, xuất hiện khi được yêu cầu/áp dụng; hữu ích với chính sách yêu cầu đăng nhập gần đây |
| `azp` | Authorized party trong trường hợp OIDC cần thể hiện bên được ủy quyền; phải kiểm tra theo quy tắc OIDC khi có |

Client cần **xác minh chữ ký**, thuật toán hợp lệ, `iss`, `aud`, `exp`, nonce nếu đã yêu cầu và các điều kiện OIDC liên quan. Khóa công khai có thể lấy qua JWKS được quảng bá trong discovery metadata. Đừng lấy dữ liệu người dùng từ một ID Token chưa được kiểm tra rồi tạo phiên đăng nhập.

**ID Token không dùng làm Bearer Token để gọi API**. `aud` của ID Token nhằm vào *OIDC Client*, còn Resource Server cần Access Token được phát hành cho quyền truy cập tài nguyên. API không nên chấp nhận ID Token chỉ vì chữ ký cũng do cùng Authorization Server ký.

Một ID Token có thể không chứa email, tên hay mọi thuộc tính hồ sơ người dùng. Các scope như `profile`, `email` và OIDC UserInfo Endpoint giúp quy định cách yêu cầu thông tin bổ sung; thuộc tính thực nhận phụ thuộc consent, claim mapping và cấu hình AS. `sub` ổn định trong phạm vi issuer là điểm tựa tốt hơn email vốn có thể thay đổi.

## 7. Liên hệ với Spring Authorization Server và Spring Security

### 7.1. Các endpoint liên quan

Khi dùng Spring Authorization Server với cấu hình endpoint mặc định:

| Endpoint | Công việc |
| --- | --- |
| `/oauth2/authorize` | Nhận yêu cầu ủy quyền, tạo Authorization Code |
| `/oauth2/token` | Đổi code lấy token, refresh token |
| `/oauth2/jwks` | Công bố khóa công khai để bên nhận xác minh JWT khi có cấu hình JWK |
| `/oauth2/introspect` | Kiểm tra trạng thái token theo OAuth 2.0 Token Introspection |
| `/oauth2/revoke` | Nhận yêu cầu thu hồi token theo OAuth 2.0 Token Revocation |
| `/.well-known/openid-configuration` | Metadata discovery OIDC khi đã bật OIDC |
| `/userinfo` | OIDC UserInfo Endpoint khi đã bật OIDC |

Đây là đường dẫn mặc định; có thể tùy chỉnh với `AuthorizationServerSettings`. OIDC không tự được bật chỉ vì có OAuth 2.0: cần bật cấu hình OIDC và đăng ký scope thích hợp.

### 7.2. Ví dụ đăng ký client và chính sách token

Đoạn cấu hình minh họa dưới đây dùng các kiểu của Spring Authorization Server; các import và cấu hình hạ tầng đã lược bỏ:

```java
@Bean
RegisteredClientRepository registeredClientRepository(
        PasswordEncoder passwordEncoder,
        @Value("${security.demo.client-secret}") String clientSecret) {

    RegisteredClient client = RegisteredClient.withId(UUID.randomUUID().toString())
            .clientId("web-client")
            .clientSecret(passwordEncoder.encode(clientSecret))
            .clientAuthenticationMethod(ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
            .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
            .authorizationGrantType(AuthorizationGrantType.REFRESH_TOKEN)
            .redirectUri("https://client.example.com/callback")
            .scope(OidcScopes.OPENID)
            .scope(OidcScopes.PROFILE)
            .scope("orders.read")
            .clientSettings(ClientSettings.builder()
                    .requireProofKey(true)
                    .requireAuthorizationConsent(true)
                    .build())
            .tokenSettings(TokenSettings.builder()
                    .accessTokenTimeToLive(Duration.ofMinutes(10))
                    .refreshTokenTimeToLive(Duration.ofDays(7))
                    .reuseRefreshTokens(false)
                    .build())
            .build();

    return new InMemoryRegisteredClientRepository(client);
}
```

Cấu hình trên có các tác dụng trực tiếp:

- **`AUTHORIZATION_CODE`** cho phép luồng đổi code lấy token, **`REFRESH_TOKEN`** cho phép dùng grant refresh khi token được cấp.
- **`requireProofKey(true)`** yêu cầu PKCE; **`requireAuthorizationConsent(true)`** yêu cầu màn hình đồng ý theo cấu hình.
- **`accessTokenTimeToLive`** và **`refreshTokenTimeToLive`** đặt thời hạn; **`reuseRefreshTokens(false)`** yêu cầu cấp Refresh Token mới khi refresh, thay vì tái sử dụng token cũ.
- `client_secret_basic` chỉ phù hợp với confidential client giữ secret ở backend. Một SPA không được nhúng bí mật này vào JavaScript phân phối cho người dùng.

`InMemoryRegisteredClientRepository` và client secret lấy từ cấu hình là ví dụ học tập. Khi vận hành thực tế, dùng kho client/authorization/consent bền vững, lưu secret an toàn, và quản lý signing key có kiểm soát. Có thể cấu hình issuer rõ ràng để token, discovery và Resource Server nhất quán:

```java
@Bean
AuthorizationServerSettings authorizationServerSettings() {
    return AuthorizationServerSettings.builder()
            .issuer("https://auth.example.com")
            .build();
}
```

Để bật OIDC với cấu hình `OAuth2AuthorizationServerConfigurer` tương ứng phiên bản đang dùng:

```java
authorizationServerConfigurer.oidc(Customizer.withDefaults());
```

Đây là lời gọi được ghép vào `SecurityFilterChain` của Authorization Server, **không phải cấu hình đầy đủ**. Phát hành ID Token ký số còn đòi hỏi cấu hình JWK/khóa ký phù hợp.

### 7.3. Phía Resource Server xác minh Access Token

Với JWT và issuer discovery, ứng dụng API Spring Boot có thể cấu hình:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://auth.example.com
```

Spring Security sẽ dùng metadata/khóa thích hợp để xác minh JWT theo cấu hình Resource Server. Vẫn phải cấu hình **authorization rules** và audience validation khi kiến trúc yêu cầu ràng buộc token với API cụ thể. Nếu dùng opaque token, Resource Server cần cấu hình introspection thay vì `jwt`.

## 8. Ba tình huống dễ nhầm lẫn

### Tình huống A: Client có ID Token, API trả 401

Ứng dụng dùng ID Token gọi `GET /api/orders`. API từ chối là đúng: nó cần **Access Token** phù hợp. Cách sửa là gửi Access Token trong `Authorization: Bearer ...`, đồng thời kiểm tra issuer, audience, hạn sử dụng và quyền đọc đơn hàng.

### Tình huống B: Token Endpoint trả `invalid_grant`

Code có thể đã được đổi, hết hạn, không khớp client/redirect URI, hoặc PKCE verifier sai. Với refresh flow, Refresh Token có thể hết hạn, bị thu hồi hoặc đã bị thay thế sau rotation. Kiểm tra log có chọn lọc qua correlation ID và thông tin lỗi an toàn; **không log nguyên giá trị code/token/verifier**.

### Tình huống C: Client nhận Access Token nhưng không có ID Token hoặc Refresh Token

Kiểm tra `scope=openid`, OIDC đã được bật, client/grant type đã đăng ký và phản hồi có thuộc một luồng OIDC hợp lệ hay không. Refresh Token cần grant type và chính sách cấp token tương ứng. Có Access Token thôi không thể kết luận AS đã thực hiện OIDC hoặc đã hứa cấp Refresh Token.

## 9. Checklist thiết kế, kiểm thử và vận hành

1. **Đăng ký client:** chỉ cho phép redirect URI cần thiết, đúng client authentication method và grant type; phân biệt public/confidential client.
2. **Bảo vệ flow:** dùng Authorization Code + PKCE `S256`, `state` ngẫu nhiên cho mỗi giao dịch, và `nonce` khi yêu cầu OIDC; kiểm tra chúng tại thời điểm xử lý phản hồi.
3. **Phát hành:** đặt thời hạn Access Token ngắn hợp lý, cấu hình Refresh Token theo rủi ro của client, quy tắc cấp scope và chính sách ký khóa.
4. **Xác minh:** OIDC Client kiểm tra ID Token; Resource Server kiểm tra Access Token, quyền truy cập và quyền trên từng tài nguyên; không hoán đổi hai token.
5. **Kiểm thử âm tính:** thử code hết hạn/dùng lại, verifier sai, `state` sai, issuer/audience sai, token hết hạn, scope không đủ, Refresh Token bị thu hồi và token cũ sau rotation.
6. **Vận hành:** bảo vệ secret/khóa ký/token, theo dõi lỗi OAuth an toàn, thiết lập rotation khóa ký và JWKS, xác định chính sách thu hồi cho JWT/opaque token, kiểm soát đồng hồ hệ thống.

**Ghi nhớ:** Authorization Code là *vé đổi token một lần*; Access Token là *quyền gọi API*; Refresh Token là *quyền xin Access Token mới*; ID Token là *bằng chứng xác thực cho OIDC Client*. Khi đặt từng giá trị đúng vào bước và bên nhận của nó, việc thiết kế hệ thống Spring Security OAuth2/OIDC trở nên rõ ràng và dễ kiểm thử hơn.

## Tài liệu chuẩn để tra cứu

- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749)
- [RFC 6750 — Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 7636 — Proof Key for Code Exchange (PKCE)](https://www.rfc-editor.org/rfc/rfc7636)
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414)
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html)
- [Spring Authorization Server — Reference](https://docs.spring.io/spring-authorization-server/reference/)
