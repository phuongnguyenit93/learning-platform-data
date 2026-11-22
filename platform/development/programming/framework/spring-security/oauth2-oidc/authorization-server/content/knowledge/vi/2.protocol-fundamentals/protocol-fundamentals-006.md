# Redirect URI, Issuer Identifier và Discovery Document

> **Phạm vi:** Giao thức và thuật ngữ — học cách thiết kế, cấu hình, bảo mật, kiểm thử và vận hành OAuth 2.0/OpenID Connect Authorization Server bằng Spring Security và Spring Authorization Server trong Spring Boot. Bài này tập trung vào ba khái niệm dễ bị nhầm lẫn: nơi trình duyệt quay về sau khi cấp quyền, danh tính của máy chủ cấp quyền và tài liệu mô tả các endpoint của máy chủ đó.

## 1. Ba khái niệm, ba câu hỏi khác nhau

Trong một hệ thống có ứng dụng web (`OAuth Client`), máy chủ xác thực/cấp quyền (`Authorization Server` hoặc `OpenID Provider`) và API (`Resource Server`), ba giá trị sau đảm nhiệm ba vai trò riêng:

| Khái niệm | Trả lời câu hỏi | Ví dụ | Bên cấu hình/sử dụng |
|---|---|---|---|
| **Redirect URI** | Sau khi người dùng hoàn thành bước cấp quyền, Authorization Server gửi trình duyệt về **đâu**? | `https://app.example.vn/login/oauth2/code/portal` | Client khai báo callback; Authorization Server lưu danh sách URI đã đăng ký và kiểm tra yêu cầu |
| **Issuer Identifier** (`issuer`) | Token và bộ metadata này do **Authorization Server nào** phát hành? | `https://login.example.vn` | Authorization Server công bố; Client/Resource Server kiểm tra |
| **Discovery Document** | Muốn tích hợp với issuer này thì **gọi endpoint nào, hỗ trợ tính năng gì và lấy khóa công khai ở đâu**? | `https://login.example.vn/.well-known/openid-configuration` | Authorization Server xuất bản tài liệu JSON; Client/Resource Server đọc |

**Ghi nhớ:** Redirect URI thuộc phía **Client**; issuer định danh phía **Authorization Server**; discovery document mô tả cách làm việc với **issuer**. Discovery URL được xây dựng từ issuer theo quy tắc chuẩn, còn redirect URI được đăng ký riêng cho từng client.

Ví dụ xuyên suốt:

- Authorization Server: `https://login.example.vn`.
- Ứng dụng Spring Boot đóng vai trò OAuth2/OIDC Client: `https://app.example.vn`, `client_id=web-client`, `registrationId=portal`.
- Redirect URI: `https://app.example.vn/login/oauth2/code/portal`.
- API kiểm tra JWT: `https://api.example.vn`.

## 2. Chúng phối hợp như thế nào?

~~~mermaid
sequenceDiagram
    autonumber
    participant Client as OAuth2/OIDC Client
    participant Browser as Trình duyệt
    participant AS as Authorization Server
    participant API as Resource Server

    Client->>AS: GET /.well-known/openid-configuration
    AS-->>Client: JSON: issuer, endpoints, jwks_uri
    Browser->>Client: Yêu cầu đăng nhập
    Client-->>Browser: Chuyển đến authorization_endpoint (state, PKCE, redirect_uri)
    Browser->>AS: GET /oauth2/authorize?...
    AS->>Browser: Xác thực người dùng và lấy consent khi cần
    AS-->>Browser: 302 Location: redirect_uri?code=...&state=...
    Browser->>Client: GET /login/oauth2/code/portal?code=...&state=...
    Client->>Client: Đối chiếu state và phiên giao dịch
    Client->>AS: POST /oauth2/token (code, redirect_uri, code_verifier, xác thực client nếu có)
    AS-->>Client: Token response (OIDC có thể chứa id_token)
    Client->>Client: Kiểm tra ID Token: chữ ký, iss, aud, exp, nonce khi áp dụng
    Client->>API: Gọi API với access token
    API->>AS: Tải metadata/JWKS khi cần
    API->>API: Kiểm tra chữ ký, issuer, thời hạn, audience/scope theo chính sách
    API-->>Client: Tài nguyên được phép
~~~

Sơ đồ minh họa một luồng **Authorization Code + PKCE**. Việc tải metadata/JWKS có thể diễn ra lúc khởi tạo, lần dùng đầu tiên hoặc khi làm mới khóa, tùy thư viện. Discovery không bắt buộc cho mọi tích hợp OAuth 2.0: hệ thống vẫn có thể cấu hình các endpoint tĩnh nếu giao thức/thư viện cho phép.

## 3. Redirect URI: đường quay về của authorization response

### 3.1. Redirect URI là gì?

Trong Authorization Code Flow, client đưa tham số `redirect_uri` vào yêu cầu cấp quyền. Sau khi xác thực và xử lý quyết định cấp quyền, Authorization Server đưa **authorization code** cùng `state` (nếu đã gửi) về callback thông qua trình duyệt. Client sau đó dùng authorization code để gọi `token_endpoint` qua kênh sau (back-channel).

~~~http
GET /oauth2/authorize?response_type=code
    &client_id=web-client
    &redirect_uri=https%3A%2F%2Fapp.example.vn%2Flogin%2Foauth2%2Fcode%2Fportal
    &scope=openid%20profile
    &state=RANDOM_CSRF_VALUE
    &nonce=RANDOM_OIDC_VALUE
    &code_challenge=BASE64URL_SHA256_OF_VERIFIER
    &code_challenge_method=S256
Host: login.example.vn
~~~

Các dòng trên được tách để dễ đọc; yêu cầu HTTP thực tế phải đặt toàn bộ query trên một dòng và mã hóa URL đúng quy tắc. `state`, `nonce`, `code_verifier` và `code_challenge` phải được tạo theo từng giao dịch, có độ ngẫu nhiên phù hợp; các giá trị chữ hoa là placeholder.

Sau khi xử lý thành công, Authorization Server trả về dạng:

~~~http
HTTP/1.1 302 Found
Location: https://app.example.vn/login/oauth2/code/portal?code=AUTH_CODE&state=RANDOM_CSRF_VALUE
~~~

**Callback không phải token endpoint.** URL `/login/oauth2/code/portal` là endpoint của **ứng dụng client**, do cơ chế OAuth2 Login của Spring Security xử lý theo cấu hình. Nó nhận `code` để client đổi token; nó không phải `/oauth2/token` của Authorization Server. Token không nên nằm trong URL callback ở Authorization Code Flow.

### 3.2. Đăng ký và kiểm tra chính xác

Authorization Server phải lưu các Redirect URI hợp lệ theo từng `client_id`. Với ứng dụng web, URI nên là HTTPS đầy đủ, chỉ rõ host và đường dẫn callback. Theo OAuth 2.0 Security Best Current Practice (RFC 9700), đối chiếu URI cần dùng **so sánh chuỗi chính xác**; ngoại lệ được chuẩn quy định liên quan đến số cổng biến đổi của redirect URI loopback `localhost` cho native app. Không dựa vào tiền tố, wildcard hoặc so khớp gần đúng.

| URI đã đăng ký | URI xuất hiện trong yêu cầu | Kết quả mong đợi |
|---|---|---|
| `https://app.example.vn/callback` | `https://app.example.vn/callback` | Trùng |
| `https://app.example.vn/callback` | `https://app.example.vn/callback/` | Không trùng: thêm dấu `/` |
| `https://app.example.vn/callback` | `http://app.example.vn/callback` | Không trùng: khác scheme |
| `https://app.example.vn/callback` | `https://app.example.vn.evil.test/callback` | Không trùng: khác host |
| `https://app.example.vn/callback` | `https://app.example.vn/callback?next=https://evil.test` | Không trùng nếu query này chưa được đăng ký chính xác |

Một Redirect URI hợp lệ có thể có query đã đăng ký, nhưng không được mở ra cơ chế chuyển tiếp tùy ý như `?next=<URL do người dùng cung cấp>`. Authorization Server cần **từ chối yêu cầu có redirect URI không hợp lệ** và tránh đưa mã lỗi hoặc authorization code đến URI không được tin cậy. Client phải phòng chống open redirect tại callback.

Ngoài kiểm tra tại authorization endpoint, khi đổi authorization code lấy token, `redirect_uri` (nếu được dùng trong yêu cầu cấp quyền) phải khớp với giá trị gắn với authorization code; Authorization Server cũng ràng buộc code với đúng client. PKCE bổ sung `code_verifier` để chống sử dụng mã bị đánh cắp, nhưng không thay thế việc kiểm tra redirect URI và `state`.

### 3.3. Phân biệt với các URI khác

- `redirect_uri` dùng cho authorization response; mỗi RegisteredClient có thể đăng ký nhiều giá trị, nhưng yêu cầu sử dụng giá trị nào thì phải kiểm tra đúng giá trị đó.
- `post_logout_redirect_uri` trong OIDC RP-Initiated Logout là đích quay về sau khi đăng xuất, có cơ chế đăng ký/kiểm tra riêng; đừng dùng nó thay authorization callback.
- `authorization_endpoint` là điểm bắt đầu yêu cầu cấp quyền trên Authorization Server; `token_endpoint` nhận yêu cầu đổi code lấy token; cả hai **không** phải redirect URI của client.
- `state` giúp client liên kết authorization response với yêu cầu ban đầu và chống CSRF; `nonce` giúp ràng buộc ID Token với phiên xác thực OIDC tương ứng khi áp dụng.

## 4. Issuer Identifier: danh tính ổn định của Authorization Server

Issuer là URL xác định **chủ thể phát hành**. Ví dụ:

~~~text
https://login.example.vn
~~~

Trong OIDC, cùng một định danh phải xuất hiện nhất quán tại:

1. Giá trị `issuer` trong OpenID Provider Configuration (discovery document).
2. Claim `iss` của **ID Token** do issuer đó phát hành.
3. Giá trị issuer mà ứng dụng client tin cậy và dùng để xác thực token.

Với **JWT access token** có claim `iss`, Resource Server cũng cần kiểm tra `iss` bằng giá trị issuer đã tin cậy, bên cạnh chữ ký, hạn dùng và các điều kiện liên quan như audience. Không suy luận rằng mọi access token đều là JWT: access token dạng opaque không có JSON claims để resource server tự đọc.

Ví dụ phần payload minh họa của một ID Token:

~~~json
{
  "iss": "https://login.example.vn",
  "sub": "user-123",
  "aud": "web-client",
  "exp": 1890000000,
  "iat": 1889996400,
  "nonce": "RANDOM_OIDC_VALUE"
}
~~~

Đây chỉ là **payload ví dụ**, không phải JWT đã ký hợp lệ. `iss` nói ai phát hành; `aud` nói token hướng đến đối tượng nào; `sub` định danh chủ thể người dùng trong ngữ cảnh issuer. Client phải kiểm tra chữ ký ID Token với khóa phù hợp, `iss`, `aud`, thời gian hiệu lực và các điều kiện OIDC liên quan. Chỉ kiểm tra chữ ký mà bỏ qua issuer/audience là thiếu an toàn.

**Ràng buộc của issuer:**

- Trong triển khai production, issuer dùng `https://`, không chứa query hoặc fragment, là URL công khai và ổn định để các thành phần khác truy cập. Local demo có thể dùng HTTP loopback theo môi trường thử nghiệm; đó không phải mẫu triển khai production.
- Đối chiếu theo **giá trị chính xác** được cấu hình và công bố. `https://login.example.vn`, `https://login.example.vn/` và `https://login.example.vn/auth` là ba chuỗi khác nhau; không tự loại dấu `/`, viết lại host hoặc đổi path khi kiểm tra `iss`.
- Issuer không phải domain callback của client. Thay đổi issuer có thể làm hỏng discovery, kiểm tra JWT hoặc các cấu hình tin cậy ở client/resource server; cần kế hoạch chuyển đổi rõ ràng.
- Một hostname có thể phục vụ nhiều issuer theo đường dẫn, nhưng phải tuân thủ quy tắc discovery tương ứng và xác minh kỹ hỗ trợ thực tế của sản phẩm/thư viện.

### 4.1. Vì sao proxy/load balancer thường gây lỗi issuer?

Authorization Server có thể chạy ở `http://localhost:9000` trong container nhưng được công bố qua gateway `https://login.example.vn`. Nếu suy issuer từ URL request nội bộ hoặc từ forwarded headers không được xử lý đúng, metadata và `iss` có thể vô tình mang `http://...`, hostname nội bộ hoặc sai path. Resource Server cấu hình issuer công khai sẽ từ chối token.

Với Spring Authorization Server, cần ưu tiên cấu hình issuer công khai một cách **tường minh** qua `AuthorizationServerSettings`. Nếu giao thức yêu cầu URL được dựng dựa trên proxy, cấu hình forwarded headers theo hạ tầng đã tin cậy và kiểm tra cả host, scheme, port, context path thực tế. Không tin vô điều kiện các `X-Forwarded-*` header đến trực tiếp từ internet.

## 5. Discovery Document: bản mô tả có thể đọc bằng máy

Discovery document là JSON công bố metadata về Authorization Server/OpenID Provider để client, SDK và Resource Server tìm endpoint và khả năng hỗ trợ mà không phải hard-code từng URL.

### 5.1. Hai chuẩn discovery thường gặp

| Chuẩn | Metadata URL khi issuer là `https://login.example.vn` | Mục đích |
|---|---|---|
| **OpenID Connect Discovery 1.0** | `https://login.example.vn/.well-known/openid-configuration` | Metadata của OpenID Provider; phục vụ đăng nhập OIDC, thông tin `issuer`, endpoint, khóa và năng lực OIDC |
| **OAuth 2.0 Authorization Server Metadata — RFC 8414** | `https://login.example.vn/.well-known/oauth-authorization-server` | Metadata của Authorization Server theo OAuth 2.0, kể cả khi không bật OIDC |

Hai tài liệu có nhiều trường trùng nhau nhưng **không đồng nhất về toàn bộ yêu cầu và ngữ nghĩa**. Spring Authorization Server có OAuth Authorization Server Metadata endpoint trong cấu hình giao thức mặc định; OIDC Provider Configuration endpoint chỉ xuất hiện khi **bật OIDC**. Endpoint JWK Set cần một `JWKSource<SecurityContext>` được cấu hình. Không suy đoán URL JWK hoặc mặc định OIDC đã bật chỉ từ việc `/oauth2/authorize` trả lời.

**Trường hợp issuer có path:** Các phép ghép well-known không hoàn toàn giống nhau giữa hai đặc tả. Với issuer `https://login.example.vn/tenant-a`:

- OIDC Discovery 1.0 ghép ở cuối issuer: `https://login.example.vn/tenant-a/.well-known/openid-configuration`.
- RFC 8414 chèn đoạn well-known trước path của issuer: `https://login.example.vn/.well-known/oauth-authorization-server/tenant-a`.

Một số thư viện thử thêm vị trí metadata tương thích. Khi triển khai issuer theo path/tenant, phải xác nhận URL được Authorization Server **thực sự xuất bản** và cách thư viện client tra cứu; không mặc định mọi biến thể đều được hỗ trợ.

### 5.2. Ví dụ tài liệu `.well-known/openid-configuration`

~~~json
{
  "issuer": "https://login.example.vn",
  "authorization_endpoint": "https://login.example.vn/oauth2/authorize",
  "token_endpoint": "https://login.example.vn/oauth2/token",
  "jwks_uri": "https://login.example.vn/oauth2/jwks",
  "userinfo_endpoint": "https://login.example.vn/userinfo",
  "response_types_supported": ["code"],
  "subject_types_supported": ["public"],
  "id_token_signing_alg_values_supported": ["RS256"],
  "scopes_supported": ["openid", "profile"],
  "token_endpoint_auth_methods_supported": ["client_secret_basic"]
}
~~~

Các URL và danh sách khả năng ở trên là **dữ liệu minh họa**, không cam kết đó là toàn bộ metadata hoặc thuật toán/capabilities Spring Authorization Server trả về trong mọi cấu hình. Luôn đọc kết quả thật từ server.

Các trường cần hiểu:

| Trường | Cách dùng đúng |
|---|---|
| `issuer` | Kiểm tra trùng issuer đã tin cậy; phải nhất quán với `iss` trong ID Token |
| `authorization_endpoint` | Điều hướng trình duyệt đến đây để mở đầu Authorization Code Flow |
| `token_endpoint` | Client gọi qua back-channel để đổi code, dùng PKCE/client authentication theo đăng ký |
| `jwks_uri` | Tải **public keys** để kiểm tra chữ ký JWT; đây là URL lấy khóa, không phải issuer hoặc discovery URL |
| `userinfo_endpoint` | Nếu được cung cấp, client có thể lấy claims của người dùng bằng access token OIDC thích hợp |
| `response_types_supported`, `grant_types_supported` | Các loại response/grant mà server tuyên bố hỗ trợ |
| `scopes_supported`, `token_endpoint_auth_methods_supported` | Các scope và phương pháp xác thực client mà server công bố |

Metadata có thể được tải công khai qua HTTP GET, không cần đăng nhập; đó là **cấu hình công khai**. Nó không chứa client secret hoặc private signing key. Đặc biệt, JWKS thường công bố public key và `kid` để chọn khóa xác minh. Không nhầm `jwks_uri` với API trả về private key; private key phải được bảo vệ trên server.

### 5.3. Discovery không thay thế việc xác thực

Lấy được một JSON có `issuer` và `jwks_uri` không tự động biến server thành đáng tin cậy. Ứng dụng phải bắt đầu từ issuer được cấu hình/cho phép, truy cập metadata qua kết nối an toàn, so khớp trường `issuer`, rồi xác minh token theo giao thức. Không nhận một issuer URL bất kỳ từ người dùng để tự động fetch metadata nếu chưa giới hạn và kiểm soát, vì có rủi ro SSRF hoặc tin nhầm nguồn cấp token.

Đối với Resource Server, discovery giúp tự tìm JWKS nhưng **chưa đủ** để quyết định token có quyền gọi một API cụ thể: còn phải kiểm tra audience, scopes/authorities và quy tắc truy cập của API.

## 6. Cấu hình với Spring Authorization Server

Các ví dụ dưới đây minh họa các thành phần liên quan trong Spring Boot sử dụng API Java của Spring Authorization Server 1.5.x. Chúng là **đoạn cấu hình trọng tâm**, cần được đặt trong lớp `@Configuration` cùng các bean hạ tầng khác như `JWKSource`, cơ chế đăng nhập người dùng và lưu trữ authorization phù hợp. Tùy phiên bản Spring Security/Spring Authorization Server, tên API tích hợp có thể khác.

### 6.1. Cố định issuer công khai

~~~java
@Bean
AuthorizationServerSettings authorizationServerSettings() {
    return AuthorizationServerSettings.builder()
        .issuer("https://login.example.vn")
        // Giữ mặc định: /oauth2/authorize, /oauth2/token, /oauth2/jwks, ...
        .build();
}
~~~

Nếu bỏ `.issuer(...)`, Spring Authorization Server có thể suy issuer từ request đang xử lý. Cấu hình tường minh phù hợp hơn khi chạy sau reverse proxy, nhiều pod hoặc nhiều tên miền.

### 6.2. Đăng ký redirect URI cho một client

~~~java
@Bean
RegisteredClientRepository registeredClientRepository() {
    RegisteredClient portal = RegisteredClient.withId(UUID.randomUUID().toString())
        .clientId("web-client")
        // Chỉ là thông tin minh họa để đọc luồng, KHÔNG dùng secret {noop} trong production.
        .clientSecret("{noop}demo-secret")
        .clientAuthenticationMethod(ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
        .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
        .authorizationGrantType(AuthorizationGrantType.REFRESH_TOKEN)
        .redirectUri("https://app.example.vn/login/oauth2/code/portal")
        .scope(OidcScopes.OPENID)
        .scope(OidcScopes.PROFILE)
        .clientSettings(ClientSettings.builder()
            .requireProofKey(true)
            .requireAuthorizationConsent(true)
            .build())
        .build();

    return new InMemoryRegisteredClientRepository(portal);
}
~~~

Ở đây `.redirectUri(...)` là **URI được phép** cho `web-client`; nó không tự tạo endpoint callback trên Authorization Server. Spring Security phía ứng dụng client phải thật sự xử lý đường dẫn `/login/oauth2/code/portal`. Trong production, dùng secret được mã hóa, quản lý bí mật và kho lưu RegisteredClient bền vững; không tạo ID ngẫu nhiên mới cho client đã đăng ký ở mỗi lần chạy server nếu cần giữ định danh/lưu trữ ổn định.

Với public client (ví dụ SPA hoặc native app), không thể tin cậy client secret: dùng loại xác thực `ClientAuthenticationMethod.NONE`, Authorization Code + PKCE, callback đúng loại ứng dụng và các cơ chế bảo vệ theo nền tảng. `requireProofKey(true)` buộc client gửi PKCE, tránh downgrade xuống luồng không có PKCE.

### 6.3. Bật OpenID Connect Provider Configuration

~~~java
@Bean
@Order(1)
SecurityFilterChain authorizationServerSecurityFilterChain(HttpSecurity http)
        throws Exception {
    OAuth2AuthorizationServerConfigurer authorizationServer =
        OAuth2AuthorizationServerConfigurer.authorizationServer();

    http.securityMatcher(authorizationServer.getEndpointsMatcher())
        .with(authorizationServer, server ->
            server.oidc(Customizer.withDefaults()))
        .authorizeHttpRequests(authorize ->
            authorize.anyRequest().authenticated())
        .exceptionHandling(exceptions -> exceptions
            .defaultAuthenticationEntryPointFor(
                new LoginUrlAuthenticationEntryPoint("/login"),
                new MediaTypeRequestMatcher(MediaType.TEXT_HTML)));

    return http.build();
}
~~~

Các import tương ứng có thể lấy từ gói Spring Security và Spring Authorization Server (ví dụ `org.springframework.security.oauth2.server.authorization.config.annotation.web.configurers.OAuth2AuthorizationServerConfigurer`). Ứng dụng cần thêm filter chain xử lý đăng nhập người dùng, `JWKSource<SecurityContext>` để ký/công bố public keys và `JwtDecoder` khi dùng các endpoint OIDC yêu cầu. Ví dụ bean decoder:

~~~java
@Bean
JwtDecoder jwtDecoder(JWKSource<SecurityContext> jwkSource) {
    return OAuth2AuthorizationServerConfiguration.jwtDecoder(jwkSource);
}
~~~

`.oidc(Customizer.withDefaults())` bật các endpoint OIDC, bao gồm Provider Configuration và UserInfo; **OIDC Dynamic Client Registration** không tự bật theo mặc định. Chỉ dùng OAuth 2.0 mà không bật OIDC thì không nên trông chờ `/.well-known/openid-configuration` khả dụng.

### 6.4. Client Spring Security dùng issuer để discovery

Cấu hình sau thuộc **ứng dụng client** `https://app.example.vn`, không phải Authorization Server:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          portal:
            provider: company-idp
            client-id: web-client
            client-secret: ${PORTAL_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
        provider:
          company-idp:
            issuer-uri: https://login.example.vn
~~~

Spring Security thay `{baseUrl}` và `{registrationId}` bằng URL công khai của client và `portal`, thu được `https://app.example.vn/login/oauth2/code/portal`. Giá trị này phải **trùng chính xác** URI đã đăng ký trên Authorization Server. Thiết lập `issuer-uri` cho phép client lấy metadata thay vì tự nhập `authorization-uri`, `token-uri` và `jwk-set-uri` cho từng endpoint.

Nếu ứng dụng client chạy sau gateway, hãy cấu hình cách xác định public base URL/forwarded headers một cách nhất quán để không tự tạo `http://localhost:8080/login/oauth2/code/portal` trái với giá trị đã đăng ký.

### 6.5. Resource Server xác nhận issuer của JWT

Ví dụ cấu hình **ứng dụng API**:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.vn
~~~

Khi đã bổ sung starter/dependencies Resource Server và JOSE cần thiết, Spring Security dùng issuer để tìm metadata/JWKS và kiểm tra claim `iss` của JWT. Tùy cấu hình, có thể chỉ định `jwk-set-uri` trực tiếp để giảm phụ thuộc vào việc tải discovery lúc khởi tạo; khi đó vẫn nên giữ `issuer-uri` để kiểm tra `iss`. Việc kiểm tra `aud` và authorization theo API cần cấu hình/đánh giá riêng.

## 7. Kiểm tra và xử lý sự cố

### 7.1. Kiểm tra discovery và JWKS bằng lệnh HTTP

Sau khi khởi chạy hệ thống trên domain đúng (hoặc đổi host thành địa chỉ môi trường test), thực hiện:

~~~bash
curl -fsS https://login.example.vn/.well-known/openid-configuration \
  | jq '{issuer, authorization_endpoint, token_endpoint, jwks_uri}'

curl -fsS https://login.example.vn/.well-known/oauth-authorization-server \
  | jq '{issuer, authorization_endpoint, token_endpoint}'

curl -fsS https://login.example.vn/oauth2/jwks \
  | jq '{key_count: (.keys | length)}'
~~~

Kỳ vọng: endpoint OIDC trả JSON nếu đã bật OIDC; cả hai metadata có `issuer` **đúng bằng** `https://login.example.vn`; endpoint public JWKS trả danh sách key khi có JWKSource. Trường `jwks_uri` trong metadata mới là nguồn sự thật của URL JWKS: nếu đã tùy biến, lấy URL từ JSON trước khi kiểm tra.

Lưu ý: muốn kiểm tra đầy đủ thì cần đăng ký client và thực thi luồng Authorization Code + PKCE thực sự. Các lệnh GET ở trên chỉ xác minh khả năng khám phá metadata, không chứng minh một token hay callback đã an toàn.

### 7.2. Bộ kiểm thử tối thiểu có giá trị

1. **Đúng redirect URI:** gửi authorization request có callback được đăng ký, đăng nhập và lấy consent (nếu cần); xác nhận `Location` chỉ tới callback đó, có `code` và `state` phù hợp. Kiểm tra client chỉ nhận response khớp `state` đã phát.
2. **Sai redirect URI:** thay `https` thành `http`, thêm `/` hoặc đổi domain. Xác nhận Authorization Server từ chối và **không điều hướng** đến đích chưa đăng ký.
3. **Ràng buộc mã cấp quyền:** cố đổi authorization code với `redirect_uri` hoặc `code_verifier` sai; yêu cầu đổi token phải thất bại. Authorization code không được tái sử dụng sau khi đã đổi thành công.
4. **Issuer/metadata nhất quán:** kiểm tra `issuer` trong metadata, `iss` của ID Token, `issuer-uri` ở client và resource server bằng nhau; token có `iss` giả phải bị từ chối dù chữ ký có vẻ hợp lệ trong môi trường thử nghiệm.
5. **Khóa và xác thực token:** kiểm tra `jwks_uri` truy cập được, JWT ký bằng key tương ứng được xác thực, token hết hạn hoặc sai `aud` bị từ chối theo chính sách.
6. **Reverse proxy:** chạy kiểm thử qua HTTPS public hostname thật, không chỉ gọi `localhost`; xác nhận issuer, endpoint URL và client redirect URI không lộ host/scheme nội bộ.

### 7.3. Triệu chứng thường gặp

| Hiện tượng | Nguyên nhân cần kiểm tra | Hướng xử lý |
|---|---|---|
| `redirect_uri` không hợp lệ | Khác scheme, port, host, dấu `/`, `registrationId` hoặc callback chưa đăng ký | So sánh nguyên văn URI ở authorization request, `RegisteredClient` và client `redirect-uri` |
| Client quay về callback nhưng đăng nhập lỗi | `state`/session mất, callback không được filter xử lý, code hết hạn, PKCE hoặc token exchange sai | Giữ cookie/session phù hợp, rà soát OAuth2 Login callback và kiểm tra code/token flow |
| `/.well-known/openid-configuration` trả 404 | OIDC chưa bật, proxy/path route sai hoặc cấu hình giao thức chưa đầy đủ | Bật OIDC configurer; kiểm tra đường public thực tế và security filter chain |
| Metadata hiển thị `http://localhost:9000` | Issuer được suy từ request nội bộ hoặc proxy cấu hình sai | Đặt `AuthorizationServerSettings.issuer(...)` bằng URL HTTPS công khai; kiểm tra proxy |
| Resource Server báo `Invalid issuer` | Claim `iss` khác `issuer-uri`, bao gồm dấu `/` cuối/path | So sánh chuỗi issuer từ token, metadata và cấu hình |
| JWT không xác minh được chữ ký | `jwks_uri` sai, JWKSource chưa có, key/`kid` không khớp hoặc xoay khóa thiếu đồng bộ | Kiểm tra public JWKS, key rotation và metadata đúng issuer |
| Discovery hoạt động nhưng không login OIDC được | Client chưa được đăng ký, thiếu scope `openid`, redirect URI/PKCE không hợp lệ hoặc thiếu user authentication | Kiểm tra toàn bộ RegisteredClient, OIDC bật và chuỗi Authorization Code Flow |

## 8. Quy tắc vận hành cần giữ nhất quán

- Dùng một **issuer public HTTPS ổn định** theo môi trường, công bố cùng giá trị trong metadata và token; chỉ thay đổi khi có kế hoạch migration.
- Đăng ký **redirect URI cụ thể, chính xác** theo client và môi trường; không dùng wildcard hoặc callback mở; bật PKCE cho Authorization Code Flow.
- Công bố metadata chuẩn để các bên tích hợp khám phá endpoint; bảo vệ private signing keys, vẫn cho phép đọc metadata/JWKS public theo thiết kế.
- Theo dõi health/khả dụng của discovery, token endpoint và JWKS; đảm bảo key rotation không làm client đang sử dụng token hợp lệ mất khả năng xác minh.
- Test qua gateway/proxy và hostname thật, gồm cả ca từ chối redirect sai và từ chối JWT sai issuer/audience.
- Trong giám sát/log, nên ghi client ID, mã lỗi và endpoint; tránh ghi authorization code, client secret, access token, refresh token, ID Token hoặc `code_verifier` nguyên văn.

**Câu hỏi tự kiểm tra:**

1. Vì sao `https://app.example.vn/callback/` không được thay thế tùy ý cho `https://app.example.vn/callback` đã đăng ký?
2. Nếu JWT có chữ ký hợp lệ nhưng `iss` khác issuer Resource Server tin cậy, API phải làm gì?
3. Discovery document và JWKS khác nhau ở điểm nào?
4. Vì sao cấu hình issuer tường minh quan trọng khi Authorization Server nằm sau reverse proxy?
5. Trong một client Spring Security, URI tạo bởi `{baseUrl}/login/oauth2/code/{registrationId}` phải tương ứng với cấu hình nào trên Authorization Server?

## Tài liệu tham khảo

- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749), đặc biệt các mục về redirection endpoint và authorization code.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700), đặc biệt yêu cầu so khớp redirect URI chính xác, PKCE và ngăn open redirect.
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414).
- [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html) và [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html).
- [Spring Authorization Server — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html) và [Core Model/Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html).
- [Spring Security — OAuth 2.0 Client Configuration](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html) và [OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html).
