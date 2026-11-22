# Phân biệt OAuth2 Client, Resource Server và Authorization Server

> **Chủ đề:** Spring Security – reactive  
> **Nhóm kiến thức:** Đăng nhập OAuth2/OIDC  
> **Trọng tâm:** Nhận diện đúng **OAuth2 Client**, **OAuth2 Resource Server** và **OAuth2 Authorization Server** trong một hệ thống WebFlux; phân biệt đăng nhập OIDC với xác thực Bearer access token, hiểu các endpoints, cấu hình Spring Security và biết kiểm thử từng vai trò mà không trộn lẫn trách nhiệm bảo mật.

## 1. Một hệ thống, ba vai trò hoàn toàn khác nhau

Trong OAuth 2.0, từ “OAuth” không tự chỉ một sản phẩm đăng nhập. Nó mô tả cách một **client** xin quyền truy cập vào một **resource server** dưới sự điều phối của một **authorization server**. Nếu cần xác minh danh tính người dùng để tạo phiên đăng nhập, **OpenID Connect (OIDC)** bổ sung một lớp identity phía trên OAuth2. Một ứng dụng có thể đảm nhiệm một vai trò, nhiều vai trò, hoặc chỉ tương tác với các hệ thống đảm nhiệm những vai trò đó.

Hãy xét ví dụ một website bán hàng:

- **Website/BFF ở `https://shop.example.test`**: người dùng truy cập, bấm “Đăng nhập”; ứng dụng này là **OAuth2 Client**. Sau đăng nhập OIDC, website quản lý phiên của chính nó và có thể dùng access token để gọi API.
- **API đơn hàng ở `https://orders.example.test`**: nhận `Authorization: Bearer ...` và kiểm tra token/permissions trước khi trả đơn hàng; đây là **Resource Server**.
- **Hệ thống định danh ở `https://id.example.test`**: xác thực người dùng, hiển thị consent khi cần, cấp authorization code, access token, ID token và công bố metadata/JWKS; đây là **Authorization Server**, đồng thời đóng vai trò **OpenID Provider** nếu triển khai OIDC.

```text
                           +------------------------+
                           | Browser / End User     |
                           +-----------+------------+
                                       |
                              mở website / login
                                       |
                                       v
                       +---------------+----------------+
                       | OAuth2 Client (WebFlux/BFF)     |
                       | shop.example.test               |
                       | oauth2Login / oauth2Client      |
                       +-------+------------------+------+
                               |                  |
              redirect (authorization code)       | API call:
                               |                  | Authorization: Bearer ACCESS_TOKEN
                               v                  v
                    +----------+--------+    +----+--------------------+
                    | Authorization      |    | Resource Server        |
                    | Server / OIDC OP   |    | orders.example.test    |
                    | id.example.test    |    | oauth2ResourceServer   |
                    | /authorize,/token  |    | JWT/opaque validation  |
                    +----------+--------+    +----+--------------------+
                               |                  |
                               +-- issuer/JWKS -->+
                               (metadata, key validation;
                                opaque token may use introspection)
```

Đừng suy rằng ba vai trò nhất thiết là **ba process hoặc ba máy vật lý**: đó là **vai trò trong giao thức**. Một BFF vừa là Client của API A vừa là Resource Server cho API B; một API cũng có thể dùng client credentials để gọi API khác. Nhưng mỗi request cần biết **vai trò và loại token tương ứng** để tránh dùng sai cấu hình.

### Kết quả học tập

Sau bài này bạn có thể:

1. Nhận diện từng vai trò và đặt đúng tên trong sơ đồ hệ thống.
2. Mô tả luồng Authorization Code + PKCE, request token, gọi API, làm mới token và phiên browser.
3. Phân biệt access token, ID token, refresh token, authorization code và session cookie.
4. Biết khi nào dùng `.oauth2Login()`, `.oauth2Client()`, `.oauth2ResourceServer().jwt()` hoặc opaque token.
5. Hiểu vì sao WebFlux reactive client/resource server và Spring Authorization Server là những cấu hình **khác stack/chức năng**.
6. Viết ví dụ Spring Boot Java 17+ cho **client WebFlux** và **API resource server**, kèm test có/không token, scope đúng/sai và redirect login.
7. Biết các lỗi bảo mật thường gặp: dùng ID token gọi API, không kiểm tra audience, nhầm scope với role, tin JWT chỉ vì decode được, nhúng client secret vào SPA.

## 2. Bảng so sánh nhanh: ai làm gì?

| Tiêu chí | OAuth2 Client | Resource Server | Authorization Server |
| --- | --- | --- | --- |
| Mục đích | **Xin và sử dụng** quyền truy cập | **Bảo vệ** tài nguyên/API | **Cấp, quản lý** quyền truy cập/token |
| Ví dụ | WebFlux website, BFF, backend gọi API | REST API orders/reports | IdP/Authorization Service |
| Request đi vào | Browser login/callback hoặc request nghiệp vụ | HTTP Bearer token gọi API | Authorization request, token request, introspection |
| Token được xử lý | Nhận/lưu access/refresh/ID token (tùy flow) | Kiểm tra **access token** | Phát hành access/refresh token; OIDC có ID token |
| Thành phần Spring | `spring-boot-starter-oauth2-client` | `spring-boot-starter-oauth2-resource-server` | Spring Authorization Server hoặc IdP bên ngoài |
| DSL WebFlux | `oauth2Login`, `oauth2Client` | `oauth2ResourceServer` | **Không phải** chỉ bật một DSL WebFlux tương tự |
| Request xác thực | Redirect người dùng tới IdP, code/token exchange; hoặc client credentials | Đọc bearer, verify JWT hoặc introspect opaque | Xác thực client, người dùng/consent và chính sách phát hành |
| Kiểm tra | `state`, PKCE, OIDC nonce/ID token, issuer/provider | `iss`, `exp`, signature, audience, scope, tenant | Client registration, redirect URIs, grant policy, signing keys, token TTL |
| Lỗi hay gặp | `invalid_client`, `invalid_grant`, callback mismatch | HTTP 401 invalid token, 403 insufficient scope | `invalid_client`, `invalid_scope`, `unauthorized_client` |

**Đặc biệt:** `oauth2Login` **không tạo một Authorization Server**. Nó cấu hình **OAuth2 Client** nhận callback đăng nhập. Tương tự `oauth2ResourceServer().jwt()` **không có nghĩa ứng dụng phát hành JWT**; nó chủ yếu giúp API **xác minh JWT**.

## 3. Bốn thực thể trong RFC: đừng bỏ quên Resource Owner

OAuth 2.0 mô tả bốn vai trò kinh điển:

1. **Resource Owner:** chủ sở hữu/quyết định quyền truy cập, thường là end user.
2. **Client:** phần mềm muốn truy cập resource thay mặt resource owner hoặc thay mặt chính client.
3. **Authorization Server:** hệ thống cấp quyền, xác thực và phát hành token.
4. **Resource Server:** hệ thống giữ tài nguyên và xác minh access token.

Resource Owner **không đồng nghĩa** Authorization Server: người dùng là chủ dữ liệu; Authorization Server là hệ thống xử lý đăng nhập/consent/cấp token. Khi `client_credentials` dùng cho machine-to-machine, không cần người dùng tham gia ở từng request; client tự đại diện mình.

### 3.1. “Ứng dụng Spring Boot” không định nghĩa vai trò

Tên repo, port, domain, hay việc sử dụng WebFlux không quyết định ứng dụng là Client/Resource Server/Authorization Server. Hãy hỏi:

- App này **redirect tới /authorize và trao đổi code**? → Phía OAuth2 Client.
- App này **nhận Bearer rồi validate token để trả JSON**? → Phía Resource Server.
- App này **vận hành /authorize, /token, metadata/JWKS, quản lý client/consent**? → Phía Authorization Server.
- App vừa nhận Bearer ở inbound vừa lấy token cho outbound? → Đồng thời **Resource Server + Client**, và nên tách security paths, token audiences rõ ràng.

Một máy chủ có thể đóng nhiều vai trò, nhưng các policy/tập endpoint phải có boundary rõ ràng. Không tự coi bearer token gọi vào API là bằng chứng user đã hoàn thành OIDC login ở một app BFF khác.

## 4. OAuth2 và OpenID Connect khác nhau thế nào?

**OAuth2 chủ yếu là ủy quyền truy cập tài nguyên (authorization)**: client xin một access token để gọi resource server. OAuth2 **không tự chuẩn hóa toàn bộ cách chứng minh end-user đã đăng nhập** cho một ứng dụng.

**OpenID Connect 1.0** là lớp identity trên OAuth2, bổ sung **ID token**, authentication request, provider metadata, nonce, userinfo và các quy tắc xác minh danh tính end-user. Với OIDC, client có thể dùng **ID token đã kiểm tra đúng** để xác định user và thiết lập session đăng nhập cho website.

| Câu hỏi | OAuth2 | OIDC |
| --- | --- | --- |
| Chính | Client được truy cập tài nguyên gì? | Người dùng vừa đăng nhập là ai, thuộc issuer nào? |
| Token điển hình | Access token, refresh token tùy grant | Access token **và ID token**, refresh token tùy cấp |
| Scope | `orders.read`, `profile.read`… | Có `openid`, thường kèm `profile`, `email` |
| Thành phần nhận | Resource Server nhận access token | OIDC Client xác minh ID token |
| Kết quả | Quyền truy cập API | Authentication result của user cho client |

Một số nhà cung cấp social-login hỗ trợ OAuth2 profile retrieval mà không hỗ trợ OIDC đầy đủ; Spring Security có thể làm OAuth2 Login dựa trên user info tương ứng. Tuy nhiên **không nên tự sáng tạo login protocol bằng cách đọc access token như ID token**.

### 4.1. Đừng dùng ID token để gọi API

- **Authorization code:** mã ngắn hạn, thường dùng một lần, đưa về callback client rồi được đổi lấy token. Nó **không phải** access token.
- **Access token:** bằng chứng được cấp cho client truy cập resource server; cần đúng audience/scope/quy tắc của API.
- **ID token:** token **dành cho OIDC Client**, chứa identity claims về authentication của end-user; `aud` thường là `client_id`. **Không** coi ID token là access token để cấp quyền API.
- **Refresh token:** credential để client xin access token mới, không gửi nó vào `Authorization: Bearer` của API.
- **Session cookie:** browser dùng để duy trì phiên tại website/BFF; không phải access token OAuth2 cấp cho resource server (dù đôi khi hệ thống chuyển tiếp session tới backend theo kiến trúc riêng).

```text
Authorization code  -> gửi về OAuth2 Client callback
ID token            -> OIDC Client kiểm tra danh tính user
Access token        -> Resource Server kiểm tra và chấp nhận khi phù hợp
Refresh token       -> OAuth2 Client lưu an toàn, dùng ở Token Endpoint
Session cookie      -> Browser <-> website/BFF (ứng dụng tự quản lý session)
```

Một token JWT có ba segment phân cách bằng dấu chấm **không tự nói nó là ID token hay access token**. Phải dựa vào mục đích sử dụng, issuer, audience và claims/protocol. Access token cũng có thể là **opaque string**, không nhất thiết là JWT.

## 5. Luồng Authorization Code + PKCE: ai nhận request nào?

Đây là luồng thường dùng cho người dùng đăng nhập OIDC qua browser. Các bước được diễn giải cho WebFlux OAuth2 Client:

```text
Browser                    OAuth2 Client             Authorization Server        Resource API
   |                            |                             |                        |
   | GET /private               |                             |                        |
   |--------------------------->|                             |                        |
   |                            | 302 tới /authorize          |                        |
   |<---------------------------|                             |                        |
   | GET /authorize?client_id=&response_type=code             |                        |
   |--------------------------------------------------------->|                        |
   |                            |                             | login/consent          |
   |                            |                             | tạo code ngắn hạn      |
   | 302 redirect_uri?code=...&state=...                       |                        |
   |<---------------------------------------------------------|                        |
   | GET /login/oauth2/code/demo?code=...&state=...            |                        |
   |--------------------------->|                             |                        |
   |                            | POST /token + code, verifier |                        |
   |                            |---------------------------->|                        |
   |                            | access_token (+ id_token)    |                        |
   |                            |<----------------------------|                        |
   |                            | validate token/claims       |                        |
   | session cookie / redirect  |                             |                        |
   |<---------------------------|                             |                        |
   | GET /orders                |                             |                        |
   |--------------------------->|                             |                        |
   |                            | GET /api/orders              |                        |
   |                            | Authorization: Bearer ACCESS_TOKEN                      |
   |                            |------------------------------------------------------->|
   |                            |                                  validate token        |
   |                            | 200 order JSON                                       |
   |                            |<-------------------------------------------------------|
   | 200 HTML/JSON              |                             |                        |
   |<---------------------------|                             |                        |
```

Đây là sơ đồ khái niệm. Các bước token exchange, `state`, PKCE, nonce, OIDC validation, lưu authorized client và tạo session có thể khác theo framework/IdP, nhưng **không thay đổi trách nhiệm cơ bản**.

### 5.1. Authorization Request là request của Client tới AS

Client đưa browser tới Authorization Endpoint của AS, với những tham số thường gặp:

```http
GET /oauth2/authorize?response_type=code&client_id=shop-web&redirect_uri=https%3A%2F%2Fshop.example.test%2Flogin%2Foauth2%2Fcode%2Fdemo&scope=openid%20profile%20orders.read&state=RANDOM_STATE&code_challenge=HASHED_VERIFIER&code_challenge_method=S256 HTTP/1.1
Host: id.example.test
```

Đây là **request minh họa**, không phải URL token/callback dùng lại được; `state` và code verifier/challenge thực phải đủ ngẫu nhiên, được sinh và kiểm tra bởi thư viện bảo mật.

- `client_id` nhận diện client registration tại Authorization Server.
- `redirect_uri` phải trùng chính sách registration; AS không được redirect code đến URI attacker.
- `scope` mô tả quyền mà client yêu cầu; `openid` kích hoạt OIDC.
- `state` gắn callback với authorization request đang chờ, chống CSRF/callback injection.
- `code_challenge`/`code_challenge_method=S256` liên quan PKCE, làm code bị đánh cắp khó đổi lấy token nếu không biết `code_verifier`.
- `nonce` dùng trong OIDC để ràng buộc ID token với authentication request khi áp dụng.

### 5.2. Callback đến Client, không đến API

AS thường redirect browser về:

```text
https://shop.example.test/login/oauth2/code/demo?code=...&state=...
```

Đây là **callback của Client**, không phải endpoint của Resource Server. Spring Security WebFlux `oauth2Login` xử lý callback mặc định theo `/login/oauth2/code/{registrationId}`. Client phải so `state`, sử dụng authorization code đúng một lần, đổi token qua Token Endpoint, xử lý OIDC ID token và hoàn tất authentication. Không tự ghi một controller để “chỉ decode code bằng Base64” — authorization code là opaque credential, phải đổi với AS.

### 5.3. Token Endpoint là endpoint của AS

Client gọi:

```http
POST /oauth2/token HTTP/1.1
Host: id.example.test
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code&code=...&redirect_uri=...&code_verifier=...
```

Đây là mẫu rút gọn; confidential clients còn có **client authentication** theo phương thức đã đăng ký (ví dụ Basic, private-key JWT, mTLS), các trường thực tế do Spring Security/provider xử lý. Token response thường là JSON có `access_token`, `token_type`, `expires_in`, có thể `refresh_token` và `id_token` khi OIDC. Không log nguyên payload này.

### 5.4. Resource Server không tham gia chuyển hướng login

Sau khi có access token, Client gọi API:

```http
GET /api/orders HTTP/1.1
Host: orders.example.test
Authorization: Bearer ACCESS_TOKEN
```

Resource Server thường **không redirect browser tới login page** trong Bearer API; khi thiếu hoặc token invalid, trả **401** với `WWW-Authenticate: Bearer` phù hợp. Khi token hợp lệ nhưng thiếu scope, trả **403** (có thể kèm thông tin `insufficient_scope` theo RFC/policy). OAuth2 Resource Server là phía **bảo vệ tài nguyên**, không “làm login” chỉ vì request có Authorization header.

## 6. OAuth2 Client: không chỉ là nút Đăng nhập

Spring Security reactive OAuth2 Client bao gồm hai use case:

1. **Đăng nhập bằng OAuth2/OIDC**: `ServerHttpSecurity.oauth2Login(...)`, redirect đến AS, callback, OIDC authentication, lập session web.
2. **Lấy và sử dụng access token để gọi API**: `ServerHttpSecurity.oauth2Client(...)`, `ReactiveOAuth2AuthorizedClientManager`, `OAuth2AuthorizedClient` và `WebClient`.

**OAuth2 Client không đồng nghĩa OAuth2 Login.** Một background service dùng `client_credentials` để gọi API là OAuth2 Client nhưng **không có người dùng đăng nhập**. Một website có thể kết hợp cả hai khi vừa login user vừa gọi API thay mặt user.

### 6.1. Các thành phần chính ở WebFlux

| Thành phần | Vai trò |
| --- | --- |
| `ClientRegistration` | Metadata đăng ký client: client ID, secret/method, redirect URI, scopes, provider endpoints |
| `ReactiveClientRegistrationRepository` | Kho ClientRegistration, thường được Boot tạo từ `application.yml` |
| `OAuth2AuthorizedClient` | Sự liên kết giữa client registration, principal và token đã được cấp |
| `ServerOAuth2AuthorizedClientRepository` | Lưu/đọc authorized client trong bối cảnh web request |
| `ReactiveOAuth2AuthorizedClientManager` | Quản lý authorize, re-authorize, refresh theo provider/grant |
| `ServerOAuth2AuthorizedClientExchangeFilterFunction` | Gắn Bearer token của authorized client lên request outbound `WebClient` |
| `oauth2Login` | Xử lý browser redirect/callback login |
| `oauth2Client` | Hỗ trợ client authorization/token management, không tự tạo login UX |

Hai thao tác sau **không tương đương**:

```java
// OAuth2/OIDC browser login:
http.oauth2Login(Customizer.withDefaults());

// Hỗ trợ OAuth2 Client lấy/gửi token tới downstream API:
http.oauth2Client(Customizer.withDefaults());
```

Đây là snippets của DSL trong method cấu hình `ServerHttpSecurity`, không phải file Java độc lập. Khi muốn cả login lẫn gọi downstream API, có thể bật **cả hai** và cấu hình `WebClient` được ủy quyền.

### 6.2. WebClient tự gắn token đúng cách

Ví dụ bean WebFlux:

```java
@Bean
WebClient downstreamClient(
        ReactiveOAuth2AuthorizedClientManager authorizedClientManager) {
    ServerOAuth2AuthorizedClientExchangeFilterFunction oauth2 =
        new ServerOAuth2AuthorizedClientExchangeFilterFunction(
            authorizedClientManager);
    return WebClient.builder().filter(oauth2).build();
}
```

Import các class từ `org.springframework.security.oauth2.client`, `org.springframework.security.oauth2.client.web.reactive.function.client` và `org.springframework.web.reactive.function.client`. Trong request outbound, cần chọn rõ `clientRegistrationId` hoặc authorized client phù hợp, ví dụ:

```java
// Snippet trong service đã inject downstreamClient.
return downstreamClient.get()
    .uri("https://orders.example.test/api/orders")
    .attributes(
        ServerOAuth2AuthorizedClientExchangeFilterFunction
            .clientRegistrationId("demo"))
    .retrieve()
    .bodyToMono(String.class);
```

**Cảnh báo:** `clientRegistrationId("demo")` chỉ chọn registration; token thực phải được cấp thành công theo authorization grant và principal phù hợp. Với `authorization_code`, flow có thể cần một user đã đăng nhập/ủy quyền; với `client_credentials`, token đại diện client chứ không phải user. Không dùng `setDefaultOAuth2AuthorizedClient(true)` một cách tùy tiện cho mọi HTTP call vì có thể vô tình phát access token tới endpoint không đáng tin.

### 6.3. Client credentials có gì khác Authorization Code?

| Thuộc tính | Authorization Code (+ PKCE) | Client Credentials |
| --- | --- | --- |
| Có user login/consent trong flow? | Thường có | Không |
| Access token đại diện cho | Quyền client được cấp theo user và policy | Quyền của chính client/service |
| Request chính | Redirect browser, callback, token exchange | Backend gọi token endpoint trực tiếp |
| Phù hợp | Website/BFF, browser-based login/OIDC | Machine-to-machine, service jobs |
| ID token OIDC? | Có thể khi scope `openid` | Thông thường không có end-user ID token |
| Secret/public client | Tùy loại client và registration; PKCE quan trọng | Confidential client auth cần bảo mật |

**Không** đưa client secret vào source JavaScript/browser SPA: public client không thể giữ bí mật như backend. Với SPA, authorization code + PKCE và kiến trúc BFF/tokens/cookies cần thiết kế theo threat model và chính sách của IdP.

## 7. Resource Server: xác minh access token, không cấp token

Một API Spring WebFlux có thể là Resource Server khi nó nhận:

```http
Authorization: Bearer ACCESS_TOKEN
```

Nhiệm vụ của API là:

1. Trích xuất bearer token đúng chuẩn từ request.
2. **Xác minh** token theo loại và cơ chế được cấu hình.
3. Tạo `Authentication`/authorities từ dữ liệu đã xác minh.
4. Áp dụng URL/method/object authorization.
5. Trả tài nguyên chỉ nếu authentication và permission đều hợp lệ.

Spring Security reactive hỗ trợ hai hướng chính.

### 7.1. JWT access token

JWT là token có thể được resource server xác minh chữ ký bằng public key/JWKS do issuer đáng tin công bố, **không cần AS tham gia trong mọi request** nếu key/metadata đã có/cache. Cấu hình thường dùng:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://id.example.test
```

Spring Security dùng `ReactiveJwtDecoder` để decode và **validate** token, không chỉ parse Base64. Khi dùng issuer discovery, sự phụ thuộc metadata lúc khởi tạo/nhận request tùy cấu hình, cache và phiên bản. Có thể khai báo thêm `jwk-set-uri` tường minh để decoder biết điểm lấy key, tránh phụ thuộc discovery lúc khởi tạo:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://id.example.test
          jwk-set-uri: https://id.example.test/oauth2/jwks
```

Vẫn cần bảo đảm **đúng issuer**, signature algorithm được phép, `exp`/`nbf`, `aud` của API, tenant, scope và key rotation. **Không suy đoán tất cả audience validation đã được framework bật theo đúng nghiệp vụ**: ứng dụng thường phải cấu hình `OAuth2TokenValidator<Jwt>` hoặc issuer/audience policy riêng để chắc chắn chỉ nhận access token được phát hành cho đúng API.

### 7.2. Opaque access token

Opaque token là chuỗi không có cấu trúc JWT có thể giải mã công khai; API có thể dùng **token introspection endpoint** tại AS:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://id.example.test/oauth2/introspect
          client-id: orders-api
          client-secret: SERVER_SIDE_SECRET
```

Client ID/secret ở đây là **credentials của Resource Server để gọi introspection** theo quy định của AS, **không phải** secret của website OAuth2 Client. Dữ liệu thực phải đặt trong secrets manager/environment, không commit lên repo. Bản thân opaque token không phải JWT; không thử `Base64.decode` để tự xác thực.

Introspection tăng phụ thuộc mạng/latency tới AS hoặc cache có kiểm soát, nhưng có thể phản ánh trạng thái active/revocation nhanh hơn so với JWT đã ký có hạn sử dụng còn hiệu lực. Việc chọn JWT hay opaque phụ thuộc threat model, vận hành, revocation, latency và policy.

### 7.3. HTTP 401 khác HTTP 403

| Tình huống API Bearer | HTTP thường gặp | Ý nghĩa |
| --- | --- | --- |
| Không có access token cho endpoint bảo vệ | **401** | Chưa xác thực |
| Bearer token sai, hết hạn, issuer/signature không hợp lệ | **401** | Authentication thất bại |
| Access token hợp lệ nhưng thiếu `orders.read` | **403** | Authentication có, authorization thiếu |
| Access token hợp lệ và đủ scope nhưng không sở hữu đơn hàng | **403** hoặc policy phù hợp | Object-level/tenant authorization |
| Authorization Code hoặc ID token được gửi thay access token | Không được chấp nhận | Sai loại credential cho Resource Server |

Response có thể có `WWW-Authenticate: Bearer`. Không dùng body của lỗi để lộ token, private keys, claims nhạy cảm, hay chính sách phân quyền nội bộ. CORS và CSRF là hai lớp khác, không thay thế quyết định OAuth2 token validity.

## 8. Authorization Server: ai quản lý /authorize và /token?

Authorization Server là nơi **cấp** OAuth2 token và quản lý vòng đời ủy quyền. Nó có thể là dịch vụ identity của tổ chức, sản phẩm IdP bên thứ ba hoặc ứng dụng tự xây với Spring Authorization Server. Nó thường bao gồm:

- **Client registration:** client ID, secret/public client, redirect URI allowlist, grant types, scopes, client authentication methods.
- **User authentication** và consent (khi có người dùng), xác định những quyền nào được cấp.
- **Authorization Endpoint:** nhận `response_type=code` và trả code qua redirect.
- **Token Endpoint:** đổi code/refresh/client credentials lấy token sau khi kiểm tra grant và client.
- **JWK Set/metadata:** công bố keys/issuer/các endpoints giúp client và resource servers thiết lập trust.
- **Introspection/Revocation:** khi bật theo nhu cầu; không mặc định mọi AS đều có mọi endpoint ở cùng path.
- **OIDC endpoints và ID token:** chỉ khi AS đồng thời là OpenID Provider, có OIDC issuer/userinfo/discovery theo cấu hình.

### 8.1. Phân biệt các endpoints

| Đường dẫn minh họa ở AS | Thường do ai gọi | Dùng làm gì |
| --- | --- | --- |
| `/oauth2/authorize` | Browser qua redirect do Client khởi tạo | Authentication/consent và cấp authorization code |
| `/oauth2/token` | Client backend hoặc public client phù hợp | Đổi grant lấy access/refresh/ID token |
| `/oauth2/jwks` | Resource Server, Client/OIDC verifier | Lấy public keys/JWK Set |
| `/oauth2/introspect` | Resource Server được phép | Xác minh opaque token active/scopes |
| `/oauth2/revoke` | Client được phép | Thu hồi token theo policy |
| `/.well-known/openid-configuration` | OIDC Client/Resource Server | OIDC provider metadata |
| `/userinfo` | OIDC Client, sau khi có access token phù hợp | Claims về end-user |

**Đường dẫn là ví dụ của một họ cấu hình**, không phải yêu cầu cố định của mọi AS/IdP. Provider bên ngoài có thể dùng URL khác. Dùng metadata/discovery đáng tin cậy hoặc tài liệu IdP thay vì hardcode các path đoán.

### 8.2. Spring Security reactive không tự cung cấp toàn bộ Authorization Server

Tài liệu Spring Security WebFlux mô tả hai nhóm chính **OAuth2 Client** và **OAuth2 Resource Server**. Vai trò **Authorization Server** được mô tả qua Spring Authorization Server (dự án riêng trong hệ sinh thái Spring Security); tài liệu Authorization Server sử dụng cấu hình **Servlet `HttpSecurity`/`SecurityFilterChain`**. Không lấy ví dụ đó rồi thay tên class thành `ServerHttpSecurity` và tin rằng một Authorization Server reactive đã có đầy đủ endpoints.

Dependency thường dùng khi bạn thật sự **xây Authorization Server riêng**:

```xml
<!-- Dependency thuộc một ứng dụng Authorization Server riêng. -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-authorization-server</artifactId>
</dependency>
```

Để chạy Authorization Server production còn phải thiết kế registered clients, user authentication, key management/JWK, issuer, authorization storage, consent, token generator/TTL, revocation, rotation, audit và HA. **Chỉ thêm dependency không phải hoàn tất một IdP.** Bài này cố ý **không giả làm một Authorization Server runnable bằng vài dòng WebFlux**, vì đó là một ứng dụng và security architecture riêng.

### 8.3. Spring Authorization Server và Spring Security version mới

Trong các nhánh Spring Security gần đây, tính năng Authorization Server có các gói/tài liệu tích hợp sâu hơn vào hệ sinh thái Spring Security. Khi tra cứu version hiện tại, hãy dùng tài liệu đúng version của **Spring Boot/Spring Security** đang vận hành; đừng tự giả định một snippet `HttpSecurity` ở nhánh 7.x tương thích nguyên vẹn với Spring Authorization Server 1.5.x hoặc `ServerHttpSecurity` WebFlux. **Điều không đổi** là vai trò “phát hành token” khác với “client đăng nhập” và “API xác minh token”.

## 9. Ví dụ đọc log: đoán vai trò từ giao dịch, không từ tên service

| Log/request | Vai trò phía xử lý | Diễn giải |
| --- | --- | --- |
| `GET /oauth2/authorization/demo` ở website | OAuth2 Client | Khởi tạo authorization request/redirect |
| Browser được redirect tới IdP `/oauth2/authorize` | Authorization Server | Xác thực/consent, cấp code |
| `GET /login/oauth2/code/demo?code=...` ở website | OAuth2 Client | Callback nhận code/state |
| `POST /oauth2/token` ở IdP | Authorization Server | Kiểm tra grant, cấp tokens |
| `POST /oauth2/token` do worker backend gọi | Client gọi AS | Có thể là client_credentials/refresh grant |
| `GET /api/orders` + `Authorization: Bearer` | Resource Server | Xác minh access token/authorization |
| `GET /.well-known/openid-configuration` ở IdP | Authorization Server/OpenID Provider | Công bố metadata |
| `GET /oauth2/jwks` ở IdP | AS công bố public keys | Resource server/client thường tiêu thụ |
| `POST /oauth2/introspect` ở IdP | Authorization Server | Xác định opaque token active |
| `GET /api/userinfo` ở IdP | OIDC UserInfo protected resource | Thành phần của OIDC provider |

Có thể cùng một sản phẩm IdP vừa là AS vừa có các **resource endpoints** như UserInfo. Một phần mềm không bị giới hạn một vai trò duy nhất.

## 10. Java 17 thuần: ghi nhớ vai trò với kết quả chính xác

Ví dụ này **không cấp/phân tích token**; nó chỉ là một chương trình Java thuần để kiểm tra bạn có phân biệt trách nhiệm đúng hay không. Nó không cần Spring Boot, Maven hoặc internet.

File `OAuthRolesDemo.java`:

```java
public final class OAuthRolesDemo {

    enum Role { CLIENT, RESOURCE_SERVER, AUTHORIZATION_SERVER }

    static String duty(Role role) {
        return switch (role) {
            case CLIENT -> "request and use access tokens";
            case RESOURCE_SERVER -> "validate access tokens and protect APIs";
            case AUTHORIZATION_SERVER -> "issue and manage access tokens";
        };
    }

    public static void main(String[] args) {
        System.out.println("CLIENT: " + duty(Role.CLIENT));
        System.out.println("RESOURCE_SERVER: " + duty(Role.RESOURCE_SERVER));
        System.out.println("AUTHORIZATION_SERVER: "
            + duty(Role.AUTHORIZATION_SERVER));
    }
}
```

Chạy với Java 17+:

```bash
javac OAuthRolesDemo.java
java OAuthRolesDemo
```

**Stdout chính xác**:

```text
CLIENT: request and use access tokens
RESOURCE_SERVER: validate access tokens and protect APIs
AUTHORIZATION_SERVER: issue and manage access tokens
```

Trong hệ thống thật, OAuth2 Client đôi khi chỉ dùng ID token cho OIDC Login mà chưa cần gọi API; chương trình trên mô tả **trách nhiệm điển hình**, không phải toàn bộ khả năng của từng vai trò.

## 11. Project A: OAuth2/OIDC Client WebFlux Java 17+

Project A là **website Client**. Nó **không** cấp JWT và **không** bảo vệ một API Bearer riêng. Vì chưa có IdP thật, project đi đến bước browser **redirect** sang Authorization Server demo; muốn login end-to-end phải cấu hình một IdP thực tương ứng. Mã và test bên dưới **không gọi mạng IdP** khi kiểm tra public endpoints/khởi tạo redirect.

### 11.1. Cấu trúc project

```text
oidc-client-webflux/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/client/
    │   │   ├── Application.java
    │   │   ├── ClientSecurityConfiguration.java
    │   │   └── PageController.java
    │   └── resources/
    │       └── application.yml
    └── test/
        └── java/demo/client/OidcClientTests.java
```

### 11.2. pom.xml (ứng dụng OAuth2 Client)

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>oidc-client-webflux</artifactId>
    <version>1.0.0</version>
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
            <artifactId>spring-boot-starter-oauth2-client</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
            <scope>test</scope>
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
```

Mục tiêu là **Client/OIDC Login**, nên dùng `spring-boot-starter-oauth2-client`. Không cần thêm `spring-boot-starter-oauth2-resource-server` nếu website chỉ login và làm outbound calls, không cung cấp API yêu cầu Bearer. Nếu cần cả hai vai trò, phải cấu hình thêm resource server path/filter riêng.

### 11.3. src/main/resources/application.yml

```yaml
server:
  port: 8082

spring:
  security:
    oauth2:
      client:
        registration:
          demo:
            provider: demo-provider
            client-id: local-learning-web
            client-secret: local-learning-secret
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
        provider:
          demo-provider:
            authorization-uri: https://idp.example.test/oauth2/authorize
            token-uri: https://idp.example.test/oauth2/token
            jwk-set-uri: https://idp.example.test/oauth2/jwks
            user-info-uri: https://idp.example.test/userinfo
            user-name-attribute: sub
```

**Cảnh báo config demo:** `idp.example.test` và client credentials ở đây là **giá trị giả công khai**. Chúng giúp project khởi động và thử redirect mà không cần metadata discovery. Để login đầy đủ, thay chúng bằng provider endpoints, client_id, secret/PKCE policy và redirect URI **đã đăng ký thật tại IdP**. Giữ client secret thật trong environment/secret manager, không commit vào YAML hay frontend JS.

- `registration.demo` tạo một `ClientRegistration` có registration ID **demo**.
- `provider.demo-provider` lưu endpoints của Authorization Server/OIDC Provider; **không** làm client trở thành AS.
- `scope: openid` có ý nghĩa login **OIDC**, kéo theo yêu cầu ID token hợp lệ.
- `redirect-uri` là callback tại **Client** `/login/oauth2/code/demo`; AS phải chấp thuận URI đó.
- Với IdP có issuer metadata, trong production có thể dùng `provider.*.issuer-uri` thay vì tự khai endpoints khi được hỗ trợ; phải bảo đảm URL issuer đúng, không tin discovery của một URL người dùng tự gửi.

### 11.4. src/main/java/demo/client/Application.java

```java
package demo.client;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class Application {
    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
```

### 11.5. src/main/java/demo/client/ClientSecurityConfiguration.java

```java
package demo.client;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
@EnableWebFluxSecurity
public class ClientSecurityConfiguration {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/public").permitAll()
                .anyExchange().authenticated()
            )
            .oauth2Login(withDefaults())
            .oauth2Client(withDefaults())
            .build();
    }
}
```

`oauth2Login` chịu trách nhiệm browser login và callback; `oauth2Client` cung cấp thành phần OAuth2 Client khi client cần lấy/gắn access token outbound. Khi chỉ cần login, phần `oauth2Client` bổ sung có thể không cần cho flow đơn giản; giữ cả hai ở demo để nhấn mạnh **hai tính năng đều thuộc vai trò Client**, không phải AS/RS.

Mẫu này sử dụng default login page và callback do Spring Security cung cấp; `GET /login` và `GET /oauth2/authorization/demo` được xử lý bởi security filters, không phải controller ở dưới. **Không** tạo `@GetMapping("/login/oauth2/code/demo")` tùy tiện nếu chưa hiểu callback filter.

### 11.6. src/main/java/demo/client/PageController.java

```java
package demo.client;

import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class PageController {

    @GetMapping("/public")
    public Mono<String> publicInfo() {
        return Mono.just("client public OK");
    }

    @GetMapping("/private")
    public Mono<String> privateInfo() {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(auth -> "signed-in:" + auth.getName());
    }
}
```

`/private` chỉ trả tên principal đã đăng nhập qua reactive security context, không cần một access token do client tự phát hành. Trong sản phẩm thật, đừng trả raw ID token/access token ra browser chỉ để chứng minh login; browser thường dùng session cookie của BFF, còn BFF giữ authorized client/token phù hợp.

### 11.7. src/test/java/demo/client/OidcClientTests.java

```java
package demo.client;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockOidcLogin;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
class OidcClientTests {

    @Autowired
    ApplicationContext applicationContext;

    private WebTestClient client;

    @BeforeEach
    void setup() {
        client = WebTestClient
            .bindToApplicationContext(applicationContext)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    @Test
    void publicEndpointIsAvailableWithoutLogin() {
        client.get().uri("/public")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("client public OK");
    }

    @Test
    void browserNavigationToPrivatePageStartsLogin() {
        client.get().uri("/private")
            .accept(MediaType.TEXT_HTML)
            .exchange()
            .expectStatus().is3xxRedirection();
    }

    @Test
    void loginInitiationRedirectsToAuthorizationServer() {
        client.get().uri("/oauth2/authorization/demo")
            .exchange()
            .expectStatus().is3xxRedirection()
            .expectHeader().value(HttpHeaders.LOCATION, location -> {
                assertTrue(location.startsWith(
                    "https://idp.example.test/oauth2/authorize?"));
                assertTrue(location.contains("response_type=code"));
                assertTrue(location.contains("client_id=local-learning-web"));
                assertTrue(location.contains("state="));
            });
    }

    @Test
    void mockedOidcLoginCanAccessProtectedPage() {
        client.mutateWith(mockOidcLogin())
            .get().uri("/private")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class)
            .value(value -> assertTrue(value.startsWith("signed-in:")));
    }
}
```

Có **4 bài test** tập trung phân biệt Client:

- Chưa đăng nhập vẫn xem public endpoint.
- Browser điều hướng đến private page được hướng về login.
- `/oauth2/authorization/demo` tạo redirect **tới Authorization Server** với response_type=code, client_id và state — không cấp token cục bộ.
- `mockOidcLogin()` xác minh authorization sau khi có một Authentication OIDC giả.

**Cực kỳ quan trọng:** `mockOidcLogin()` **bỏ qua** live IdP, signature, ID token validation, state/nonce exchange và callback thực. Test này **không chứng minh SSO end-to-end**. Muốn chứng minh thực tế, dùng IdP test với redirect/callback/cookie thật, đăng ký client và kiểm tra token flow được vận hành đúng.

### 11.8. Chạy Project A

```bash
java -version
mvn -version
mvn clean test
mvn spring-boot:run
```

Dự kiến tests cho phép bạn quan sát **4 tests** của `OidcClientTests`. Đây là **kỳ vọng từ mã**, chưa có tuyên bố test đã được chạy trong môi trường này.

Mở:

```text
http://localhost:8082/public
http://localhost:8082/private
http://localhost:8082/oauth2/authorization/demo
```

`/private` dẫn tới login; `/oauth2/authorization/demo` sẽ redirect tới hostname giả nên **không thể hoàn tất đăng nhập** cho đến khi thay bằng IdP thật. Lỗi host không tồn tại ở đây **không chứng minh cấu hình OAuth2 Client logic sai**; đó là ranh giới giữa demo redirect và môi trường SSO thực.

## 12. Project B: OAuth2 Resource Server WebFlux Java 17+

Project B là **API nhận Bearer access token**. Nó không có trang OAuth2 login và không quản lý authorization code/callback. Spring Security **xác minh JWT qua `ReactiveJwtDecoder`** theo issuer/JWKS khi chạy với token thật; tests ở đây dùng `mockJwt()` để kiểm tra scope và HTTP authorization mà **không phụ thuộc IdP**.

### 12.1. Cấu trúc project

```text
oauth2-resource-api/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/resource/
    │   │   ├── Application.java
    │   │   ├── ResourceSecurityConfiguration.java
    │   │   └── ApiController.java
    │   └── resources/
    │       └── application.yml
    └── test/
        └── java/demo/resource/ResourceServerTests.java
```

### 12.2. pom.xml (ứng dụng Resource Server)

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>oauth2-resource-api</artifactId>
    <version>1.0.0</version>
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
            <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
            <scope>test</scope>
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
```

Dự án chỉ có resource-server starter; không cần client starter để **nhận** Bearer JWT. Nếu API đồng thời cần gọi downstream service với client credentials, khi đó mới bổ sung OAuth2 Client riêng và quản lý token outbound có kiểm soát.

### 12.3. src/main/resources/application.yml

```yaml
server:
  port: 8083

spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.test
          jwk-set-uri: https://idp.example.test/oauth2/jwks
```

Hai URL **là issuer/JWK giả cho demo không có IdP**. Khai báo cả `issuer-uri` và `jwk-set-uri` giúp resource server biết vị trí keys mà không cần issuer discovery ngay lúc khởi tạo; **JWT thật không xác minh được** cho đến khi cấu hình IdP thực cấp JWT có issuer/signature tương ứng. Tests dùng `mockJwt` không gọi JWKS network và **không kiểm tra chữ ký**; bài cũng chỉ công bố như vậy.

Trong production nên dùng trust policy thật: `iss` được kỳ vọng, key rotation, thuật toán ký, `exp`/`nbf`, audience phù hợp, token type, tenant/scope; nếu AS dùng opaque token thì cấu hình `opaqueToken`/introspection thay vì `jwt`. Đừng cấu hình `jwk-set-uri` trỏ tới server do client request tự chọn (SSRF/trust bypass).

### 12.4. src/main/java/demo/resource/Application.java

```java
package demo.resource;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class Application {
    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
```

### 12.5. src/main/java/demo/resource/ResourceSecurityConfiguration.java

```java
package demo.resource;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
@EnableWebFluxSecurity
public class ResourceSecurityConfiguration {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/public").permitAll()
                .pathMatchers("/api/read")
                    .hasAuthority("SCOPE_orders.read")
                .pathMatchers("/api/admin")
                    .hasAuthority("SCOPE_admin")
                .pathMatchers("/api/me").authenticated()
                .anyExchange().denyAll()
            )
            // Chỉ API Bearer trong demo, không dùng browser session/login.
            .oauth2ResourceServer(oauth2 -> oauth2.jwt(withDefaults()))
            .httpBasic(basic -> basic.disable())
            .formLogin(form -> form.disable())
            .csrf(csrf -> csrf.disable())
            .build();
    }
}
```

**Tại sao tắt CSRF ở Project B?** Demo này giả định **API chỉ nhận Authorization: Bearer access token do client chủ động gắn**, không dùng cookies/browser authentication tự động và không có endpoint thay đổi trạng thái được gọi bằng session. Đánh giá này **không đúng cho mọi resource server**: nếu cùng app còn hỗ trợ cookie session, Basic được browser tự gửi hoặc form login, phải thiết kế CSRF theo từng security chain/request matcher; không copy `.csrf(...disable())` vô điều kiện vào production.

`hasAuthority("SCOPE_orders.read")` dựa trên mapping mặc định scope claim trong JWT tới Spring authority tên `SCOPE_...`. Nếu issuer dùng claims `roles`/custom scopes hoặc converter tùy chỉnh, phải xác nhận authority mapping. **`SCOPE_orders.read` không tự động tương đương `ROLE_ADMIN`.**

### 12.6. src/main/java/demo/resource/ApiController.java

```java
package demo.resource;

import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class ApiController {

    @GetMapping("/public")
    public Mono<String> publicInfo() {
        return Mono.just("resource public OK");
    }

    @GetMapping("/api/read")
    public Mono<String> read() {
        return Mono.just("orders read OK");
    }

    @GetMapping("/api/admin")
    public Mono<String> admin() {
        return Mono.just("admin OK");
    }

    @GetMapping("/api/me")
    public Mono<String> me() {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(auth -> "subject=" + auth.getName());
    }
}
```

`/api/me` đọc `Authentication` từ **Reactor Context**, không lấy username từ query/header do client đặt. Với JWT mặc định, authentication name thường là `sub`; nếu converter đổi principal claim thì có thể khác. Sử dụng subject ID đáng tin và tenant scope khi kiểm tra resource ownership, không chỉ tin tên trả về.

### 12.7. src/test/java/demo/resource/ResourceServerTests.java

```java
package demo.resource;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.http.HttpHeaders;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockJwt;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
class ResourceServerTests {

    @Autowired
    ApplicationContext applicationContext;

    private WebTestClient client;

    @BeforeEach
    void setup() {
        client = WebTestClient
            .bindToApplicationContext(applicationContext)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    private WebTestClient.ResponseSpec withScope(
            String uri, String authority) {
        return client.mutateWith(
                mockJwt().authorities(
                    new SimpleGrantedAuthority(authority)))
            .get().uri(uri)
            .exchange();
    }

    @Test
    void publicEndpointDoesNotRequireBearerToken() {
        client.get().uri("/public")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("resource public OK");
    }

    @Test
    void protectedEndpointWithoutBearerIs401() {
        client.get().uri("/api/read")
            .exchange()
            .expectStatus().isUnauthorized()
            .expectHeader().exists(HttpHeaders.WWW_AUTHENTICATE);
    }

    @Test
    void readEndpointWithCorrectScopeIs200() {
        withScope("/api/read", "SCOPE_orders.read")
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("orders read OK");
    }

    @Test
    void readEndpointWithWrongScopeIs403() {
        withScope("/api/read", "SCOPE_orders.write")
            .expectStatus().isForbidden();
    }

    @Test
    void readEndpointWithUnprefixedAuthorityIs403() {
        withScope("/api/read", "orders.read")
            .expectStatus().isForbidden();
    }

    @Test
    void adminEndpointWithAdminScopeIs200() {
        withScope("/api/admin", "SCOPE_admin")
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("admin OK");
    }

    @Test
    void adminEndpointWithOnlyReadScopeIs403() {
        withScope("/api/admin", "SCOPE_orders.read")
            .expectStatus().isForbidden();
    }

    @Test
    void getMeUsesAuthenticatedJwtSubject() {
        client.mutateWith(mockJwt().jwt(jwt -> jwt.subject("alice")))
            .get().uri("/api/me")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("subject=alice");
    }

    @Test
    void getMeWithoutTokenIs401() {
        client.get().uri("/api/me")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void defaultDenyProtectsUnknownPath() {
        withScope("/api/not-configured", "SCOPE_admin")
            .expectStatus().isForbidden();
    }

    @Test
    void bothScopeAuthoritiesCanAccessBothEndpoints() {
        var both = mockJwt().authorities(
            new SimpleGrantedAuthority("SCOPE_orders.read"),
            new SimpleGrantedAuthority("SCOPE_admin"));

        client.mutateWith(both)
            .get().uri("/api/read")
            .exchange()
            .expectStatus().isOk();

        client.mutateWith(mockJwt().authorities(
                new SimpleGrantedAuthority("SCOPE_orders.read"),
                new SimpleGrantedAuthority("SCOPE_admin")))
            .get().uri("/api/admin")
            .exchange()
            .expectStatus().isOk();
    }

    @Test
    void validMockJwtDoesNotImplyEveryAuthority() {
        withScope("/api/admin", "SCOPE_profile")
            .expectStatus().isForbidden();
    }
}
```

Bộ test có **12 phương thức `@Test`**, cho thấy API Resource Server:

- Thiếu Bearer -> **401** (chưa xác thực).
- Đủ authority `SCOPE_orders.read` -> **200** tại `/api/read`.
- Sai/thiếu scope -> **403** dù principal giả đã được xác thực.
- Dùng authority `orders.read` thay vì `SCOPE_orders.read` -> **403** trong cấu hình demo.
- Subject JWT xuất hiện qua `Authentication.getName()` trong Reactor Context.

**Phạm vi kiểm thử:** `mockJwt()` tạo Authentication giả hợp lệ cho **authorization tests**, và cố tình **không kiểm tra chữ ký, issuer, audience, expiration, actual Bearer decoder hoặc remote JWKS**. Để kiểm tra JWT security end-to-end, cần thêm tests có JWT được ký thật từ test AS/JWKS (và JWT sai signature/aud/iss/exp), ngoài các tests trên.

### 12.8. Chạy Project B

```bash
java -version
mvn -version
mvn clean test
mvn spring-boot:run
```

Dự kiến test suite của Resource Server có **12 tests**. Không tuyên bố chúng đã được chạy thực tế: đây là kết quả học tập dự kiến từ source.

Gọi endpoint public:

```bash
curl -i http://localhost:8083/public
```

Gọi protected endpoint không có Bearer:

```bash
curl -i http://localhost:8083/api/read
```

Dự kiến **401** với Bearer challenge. Để gọi API protected thành công ở runtime, bạn cần **access token JWT thật được issuer cấu hình phát hành cho API**, với audience/scope đúng. Vì project dùng IdP giả nên:

```text
GET /api/read không có token -> 401
GET /api/read với một JWT tùy ý tự ghép Base64 -> không được chấp nhận
GET /api/read với access token hợp lệ của IdP thật -> có thể 200 nếu scope đúng
```

**Không** dùng một ID token OIDC của browser để thế vào request Bearer cho Resource Server. Đừng coi `mockJwt()` trong test là công cụ phát token ngoài production.

## 13. Nếu một WebFlux application đóng cả Client lẫn Resource Server?

Kiến trúc BFF + API đôi khi dùng **một process Spring**: người dùng đăng nhập bằng OIDC session ở đường `/ui/**`, đồng thời máy chủ nhận Bearer JWT từ một service khác ở `/api/**`. Đây là **hai authentication mechanisms** có boundary riêng.

Hướng thiết kế là có nhiều `SecurityWebFilterChain` **với `securityMatcher` và `@Order` cụ thể**, ví dụ về ý tưởng:

```java
// Snippet minh họa, không phải ứng dụng đầy đủ.
@Bean
@Order(1)
SecurityWebFilterChain apiChain(ServerHttpSecurity http) {
    return http
        .securityMatcher(
            new PathPatternParserServerWebExchangeMatcher("/api/**"))
        .authorizeExchange(ex -> ex.anyExchange().authenticated())
        .oauth2ResourceServer(o -> o.jwt(Customizer.withDefaults()))
        .build();
}

@Bean
@Order(2)
SecurityWebFilterChain uiChain(ServerHttpSecurity http) {
    return http
        .authorizeExchange(ex -> ex.anyExchange().authenticated())
        .oauth2Login(Customizer.withDefaults())
        .oauth2Client(Customizer.withDefaults())
        .build();
}
```

Nhớ import `@Order`, `PathPatternParserServerWebExchangeMatcher`, `Customizer`, `SecurityWebFilterChain`. **Đây chỉ là kiến trúc minh họa**: code production còn cần cấu hình CSRF/cookies, public login/callback paths, unauthenticated entry point, CORS, JWT decoder, registration repository, session repository và security matcher đúng thứ tự. **Không copy nguyên để khai mở API nhạy cảm**.

Các vấn đề dễ sai:

- Cho API Bearer dùng login redirect HTML thay vì 401.
- Cho browser session cookie vô tình authenticate API vốn yêu cầu service-to-service Bearer.
- Dùng token `aud=web-client` để truy cập API `aud=orders-api`.
- Mở `/api/**` rộng vì muốn `/ui/**` public.
- Tắt CSRF cho cả website có session chỉ vì API Bearer không cần cookie.
- `@Order` sai khiến chain web áp vào API hoặc ngược lại.
- Dùng access token của user A khi outbound WebClient xử lý request của user B.

Nguyên tắc: **đúng vai trò cho đúng request/route**, đối chiếu principal/authorities và thử negative cases.

## 14. Authentication, authorization và scope/role

OAuth2 Access Token thường có **scope** được cấp. Với JWT Resource Server của Spring Security, scope từ `scope` hoặc `scp` theo converter mặc định thường được chuyển sang authority `SCOPE_...`. Ví dụ claim `scope="orders.read orders.write"` thành:

```text
SCOPE_orders.read
SCOPE_orders.write
```

Khi đó:

```java
.pathMatchers("/api/orders").hasAuthority("SCOPE_orders.read")
```

không giống `hasRole("ADMIN")`, vốn theo convention mặc định đòi `ROLE_ADMIN`. **Role và scope không phải hai dạng token khác nhau**; chúng là claims/quy ước authorization được mapper chuyển thành authorities. User có `ROLE_ADMIN` không tự có scope `orders.read` nếu không có policy mapping.

### 14.1. JWT claim không tự trở thành authority

Một JWT payload minh họa:

```json
{
  "iss": "https://id.example.test",
  "sub": "user-123",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "exp": 1893456000
}
```

Payload hiển thị **không có nghĩa token hợp lệ**. Phải xác minh chữ ký, issuer, audience, thời gian và các chính sách liên quan. Không dùng đoạn JSON này để tạo token bằng cách tự ghép Base64 và tin tưởng. Nếu AS gửi `roles`, `groups` hoặc quyền dưới claim custom, resource server cần converter rõ ràng; Spring Security không tự suy mọi claim trở thành `ROLE_...`.

### 14.2. Thẩm quyền người dùng và client cần được giới hạn

Trong grant `authorization_code`, access token thường phản ánh ủy quyền có liên quan người dùng và client; vẫn cần xác minh tài nguyên được truy cập thuộc user/tenant nào. Trong `client_credentials`, token thường đại diện cho **client application**, không phải end-user. Không lấy `sub` của service token rồi coi đó là chủ một đơn hàng của khách.

Có thể cần các khái niệm `azp`, `client_id`, `aud`, `iss`, tenant ID, resource ID. Chính sách chính xác phụ thuộc IdP và profile token; không ép một claim vendor-specific thành quy tắc OAuth2 phổ quát.

## 15. Vì sao chỉ decode JWT là sai nghiêm trọng?

JWT có các phần encode bằng Base64URL; người bất kỳ có token đều có thể decode header/payload. **Decode không phải verify.**

Ví dụ bạn thấy:

```json
{"sub":"admin","scope":"orders.read"}
```

Không có nghĩa người gọi thật sự được cấp quyền. Một client độc hại có thể tự chế payload như vậy. Resource Server phải xác minh:

1. **Signature** có hợp lệ theo trusted JWKS/key không?
2. Header `alg` có nằm trong các thuật toán được cho phép không? Không chấp nhận `none` tùy tiện.
3. `iss` có đúng trusted Authorization Server không?
4. `aud` có dành cho chính API/resource server này không?
5. `exp`/`nbf` và clock skew có hợp lệ không?
6. `scope`/permissions có đủ cho endpoint và resource object/tenant không?
7. Token type/format có phù hợp access token profile không?
8. Có yêu cầu revocation/session constraints hay extra claim validation không?

**ID token** có thể có `aud=client-id`; nếu API không kiểm tra audience, sẽ có nguy cơ chấp nhận token dùng cho Client vào sai mục đích. Đây là một vấn đề **token substitution**. Resource Server không chấp nhận JWT chỉ vì được ký bởi IdP tin cậy; còn phải xét **token được cấp cho ai và dùng để làm gì**.

### 15.1. JWT vs opaque và khả năng thu hồi

JWT ký và có hạn sử dụng tự mang thông tin; có thể verify cục bộ, nhanh và ít phụ thuộc AS ở mỗi request, nhưng việc revoke tức thời khó hơn nếu chưa có thêm denylist/backchannel hoặc hạn sử dụng ngắn. Opaque token có thể introspect để biết active trạng thái theo AS; đổi lại có thêm network/caching/failure-mode. Không có lựa chọn nào tự động “an toàn hơn” trong mọi môi trường.

Khi AS xoay khóa, JWKS cache cần được refresh phù hợp; khi AS outage, token validation phải tuân fail policy rõ ràng. Không tự tắt signature check trong Resource Server để giữ availability.

## 16. 401/403 và lỗi OAuth2 từng vai trò

| Nơi xảy ra | Lỗi | Nguyên nhân thường gặp | Hướng kiểm tra |
| --- | --- | --- | --- |
| OAuth2 Client khi redirect | `redirect_uri_mismatch` | Callback URI không được AS đăng ký | Exact scheme/host/port/path, proxy headers |
| OAuth2 Client khi callback | `invalid_state` hoặc login failure | Session/correlation state mất/không khớp | Cookies, WebSession, SameSite, reverse proxy |
| OAuth2 Client khi token exchange | `invalid_grant` | Code hết hạn/dùng lại, code_verifier sai, redirect URI mismatch | Authorization code/PKCE/token endpoint logs đã redact |
| OAuth2 Client khi token exchange | `invalid_client` | Client authentication sai | Client ID, secret/mTLS/JWT assertion/registration |
| OAuth2 Client khi ID token validate | Invalid issuer/audience/nonce | OIDC security checks không hợp lệ | Discovery, client_id, issuer, nonce, clock |
| Resource Server inbound | **401** | Thiếu/invalid/expired Bearer token | `WWW-Authenticate: Bearer`, issuer/JWKS/clock |
| Resource Server inbound | **403** | Valid token nhưng scope/permission/tenant thiếu | Authentication authorities, policy |
| Authorization Server | `invalid_scope` | Client xin scope không được phép | RegisteredClient, consent policy |
| Authorization Server | `unauthorized_client` | Grant type hoặc flow không cho client này | Registration/grant configuration |
| Authorization Server | Invalid redirect URI | AS không cho redirect code | Client redirect URI allowlist |
| BFF browser UX | Redirect loop login | Session/cookie/callback path sai | Cookie SameSite/Secure, base URL, proxy |
| WebFlux API CORS | Browser báo CORS dù HTTP 401/403 | Error response/preflight thiếu CORS headers | Network tab, CORS trước security |

**Lỗi OAuth2 protocol** như `invalid_grant` có thể xuất hiện trong response từ Token Endpoint, không nhất thiết trở thành HTTP 401/403 của API business. Khi API `/orders` trả 403, đừng tự kết luận đã có `invalid_grant`: nó có thể chỉ là thiếu authority.

### 16.1. Khi đăng nhập OIDC bị lỗi

Thứ tự debug:

1. Kiểm tra `ClientRegistration` và provider metadata (authorization/token/JWKS/userinfo).
2. Xác nhận browser được redirect từ **Client** tới **AS** với `client_id`, `scope`, `redirect_uri`, `state` đúng.
3. Xác nhận callback quay về đúng `/login/oauth2/code/{registrationId}`, không bị proxy rewrite.
4. Kiểm tra state/session vẫn còn, cookie được browser gửi trở lại (SameSite/Secure).
5. Kiểm tra code mới, chưa dùng; PKCE verifier và token exchange thành công.
6. Kiểm tra OIDC ID token validation, issuer, audience, nonce, clock, key rotation.
7. Kiểm tra Spring Security session đã được lưu nếu app cần logged-in navigation.
8. Không log code, access token, refresh token, ID token hoặc client secret.

### 16.2. Khi gọi Resource Server bị 401/403

Thứ tự debug:

1. Xác nhận Client thực sự gửi **`Authorization: Bearer` access token**, không phải ID token.
2. Nếu **401**: token được gửi chưa, `exp`/signature/issuer/audience đã được verify chưa, endpoint JWKS/introspection hoạt động không?
3. Nếu **403**: kiểm tra authorities Spring tạo ra từ token (`SCOPE_...`/roles) và rule `hasAuthority`/method security, tenant/resource ownership.
4. Nếu browser lỗi CORS trước khi thấy 401/403: debug CORS/preflight/error response **riêng**, không chữa bằng cách tắt Bearer validation.
5. Nếu mới migrate phiên bản: xem resource-server starter/Jose và reactive JWT converter setup.
6. Không coi `mockJwt()` test success là bằng chứng token thật có signature/audience hợp lệ.

## 17. Checklist security cho từng vai trò

### OAuth2 Client / OIDC Login

- [ ] Dùng Authorization Code + PKCE khi phù hợp; kiểm tra state, OIDC nonce và các checks do provider/framework hỗ trợ.
- [ ] Redirect URI được đăng ký chính xác, dùng HTTPS ở môi trường thực.
- [ ] Không đưa confidential client secret lên frontend/public bundle.
- [ ] Lưu access/refresh tokens an toàn, không log và không gắn mặc định cho mọi WebClient request.
- [ ] Validate ID token đúng issuer/audience/signature/time và purpose; không dùng ID token thay access token.
- [ ] Browser session cookies có HttpOnly/Secure/SameSite phù hợp; bảo vệ CSRF ở endpoints cookie-based.
- [ ] Tránh open redirect và callback injection; kiểm tra các đường logout/session rotation.
- [ ] Test login/callback với IdP thật hoặc IdP sandbox, không chỉ mockOidcLogin.

### Resource Server

- [ ] Chỉ chấp nhận access token đúng loại/audience/issuer của API.
- [ ] Validate chữ ký, thuật toán, thời gian, keys/JWKS hoặc introspection active status.
- [ ] Map scopes/roles/claims sang authorities nhất quán, không tin claims tùy ý từ client.
- [ ] Áp HTTP + method/object/tenant authorization, không chỉ `authenticated()`.
- [ ] Trả 401 cho token chưa hợp lệ và 403 cho valid principal thiếu quyền theo policy.
- [ ] Đặt CSRF policy đúng kiểu credential; đừng tắt nếu endpoint dùng browser cookies.
- [ ] Có test token hợp lệ/sai signature/issuer/audience/expired ngoài các test mockJwt authorization.
- [ ] Không log raw Bearer header, token hay JWKS private key.

### Authorization Server

- [ ] RegisteredClient, redirect URIs, client auth và grant types có policy chặt.
- [ ] Authorization code ngắn hạn, một lần, PKCE, chống CSRF/callback injection và consent đúng.
- [ ] Token claims/issuer/audience/TTL phù hợp resource servers và client registrations.
- [ ] Private signing keys lưu an toàn, rotation/JWKS và recovery có runbook.
- [ ] Introspection/revocation khi cần, session/logout/end-user auth được giám sát.
- [ ] Metadata, trusted issuer, scopes và OIDC provider behavior được kiểm thử.
- [ ] Multi-instance HA/DB storage, audit, monitoring, incident response rõ ràng.
- [ ] Chọn đúng sản phẩm/stack Authorization Server thay vì nhầm bật `oauth2Login` thành token issuer.

## 18. Bài tập phân loại vai trò và đáp án

**Câu 1.** Ứng dụng WebFlux hiển thị nút “Login with OIDC”, redirect user tới IdP rồi nhận code. Nó là gì?  
**Đáp án:** **OAuth2 Client** sử dụng chức năng OIDC/OAuth2 Login. Đó không phải Authorization Server.

**Câu 2.** API chỉ có `.oauth2ResourceServer(o -> o.jwt(...))`. Nó có tự cấp JWT hoặc đăng nhập người dùng qua trình duyệt không?  
**Đáp án:** Không. Nó **xác minh access token** cho API; token issuer và interactive login thuộc các vai trò khác.

**Câu 3.** Ai kiểm tra `grant_type=authorization_code` và cấp access token sau khi nhận code?  
**Đáp án:** **Authorization Server** tại Token Endpoint.

**Câu 4.** Ai gọi `GET /api/orders` với `Authorization: Bearer`?  
**Đáp án:** **OAuth2 Client** (hoặc một service acting as Client) gửi request; **Resource Server** nhận và validate token.

**Câu 5.** Browser nhận ID token khi OIDC login. ID token có dùng trực tiếp để gọi mọi API không?  
**Đáp án:** Không. ID token dành cho **OIDC Client**; API cần **access token** có issuer/audience/scope tương ứng.

**Câu 6.** Background job dùng client credentials mà không có user login. Job có phải OAuth2 Client không?  
**Đáp án:** Có. Client OAuth2 không nhất thiết có user/browser.

**Câu 7.** Vì sao resource server cần kiểm tra `aud` ngoài signature/issuer?  
**Đáp án:** Một token do cùng IdP ký vẫn có thể dành cho **Client hoặc API khác**. Kiểm tra audience giúp ngăn token substitution/cross-service token replay.

**Câu 8.** Tại sao `mockJwt()` pass test không chứng minh AS/JWKS thật đã cấu hình đúng?  
**Đáp án:** Mock bypass việc decode/verify JWT thật; nó chỉ kiểm tra Spring authorization rules với authentication đã được cung cấp.

**Câu 9.** User đăng nhập thành công tại Client nhưng gọi API nhận 403. Lỗi nằm đâu?  
**Đáp án:** Có thể access token hợp lệ nhưng thiếu scope/permission/tenant hoặc Resource Server policy không cho. OIDC login thành công **không hứa** mọi API đều được 200.

**Câu 10.** Nếu Server phát hành token tự ký thì hệ thống đó chắc là OAuth2 Authorization Server đạt chuẩn không?  
**Đáp án:** Không. Việc “tự tạo JWT” chỉ là token generation; một AS thực cần registration, grant, consent, client authentication, token lifecycle, metadata/JWKS và protocol security.

**Câu 11.** `scope=openid` có ý nghĩa gì?  
**Đáp án:** Kích hoạt yêu cầu **OpenID Connect**, client có thể nhận/validate ID token để xác minh danh tính end-user.

**Câu 12.** Resource Server dùng opaque tokens xử lý ra sao?  
**Đáp án:** Thường gọi **introspection** tới AS qua `ReactiveOpaqueTokenIntrospector` thay vì tự giải mã JWT.

**Câu 13.** Có thể một Spring WebFlux app vừa Client vừa Resource Server không?  
**Đáp án:** Có; nhưng cần **tách matcher/security chain/credentials và token audience**, không cho web session login lấn sang API Bearer vô ý.

**Câu 14.** Vì sao browser `POST /login/oauth2/code/demo` tự viết không đúng flow mặc định?  
**Đáp án:** Callback mặc định thường là browser redirect GET có code/state đến client endpoint; Spring Security xử lý và trao đổi code với AS. Không tạo callback xử lý tự phát mà bỏ validation.

**Câu 15.** Nếu thiếu client secret trong Project A thì project có thể test redirect không?  
**Đáp án:** Với client confidential trong demo đã có secret giả; redirect initiation là bước trước token exchange. Login end-to-end cần client authentication/registration thật, không thể chỉ dùng secret giả.

**Câu 16.** Resource Server có cần truy cập Authorization Server cho từng JWT không?  
**Đáp án:** Không nhất thiết. JWT ký có thể verify cục bộ với keys/JWKS đã tin cậy và cache. Opaque token introspection thường phụ thuộc AS/cache theo thiết kế.

## 19. Tổng kết và tài liệu chính thức

**Quy tắc nhớ cuối cùng:**

```text
OAuth2 Client
    -> ĐI XIN token / dùng token / có thể login user bằng OIDC.

OAuth2 Resource Server
    -> NHẬN Bearer access token / validate / xét scope & quyền API.

OAuth2 Authorization Server
    -> CẤP authorization code, access token, refresh token (và ID token nếu OIDC).

OAuth2 Login
    -> MỘT TÍNH NĂNG của OAuth2 Client, không phải vai trò thứ tư.

ID Token
    -> OIDC Client xác minh danh tính; không tự dùng làm API access token.

Access Token
    -> Resource Server xác minh, dùng đúng audience/scope.

Spring Security WebFlux
    -> oauth2Login + oauth2Client + oauth2ResourceServer.
       Authorization Server là sản phẩm/cấu hình riêng, không do
       hai DSL kia tự phát hành.
```

Bài học đã phân biệt **roles, protocol messages, tokens, endpoints, Spring dependencies, DSL, test strategy và security boundaries**. Khi debug, câu hỏi đầu tiên không phải “OAuth có bật chưa?” mà là: *request này đi vào vai trò nào, token nào được dùng và thành phần nào có trách nhiệm xác minh/cấp phép?*

**Nguồn chính thức và tiêu chuẩn tham khảo:**

- Spring Security 6.5 – OAuth2 WebFlux overview: https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/index.html
- Spring Security – Reactive OAuth2 Login: https://docs.spring.io/spring-security/reference/reactive/oauth2/login/index.html
- Spring Security – Reactive OAuth2 Client: https://docs.spring.io/spring-security/reference/reactive/oauth2/client/index.html
- Spring Security – Reactive Authorized Client/WebClient: https://docs.spring.io/spring-security/reference/reactive/oauth2/client/authorized-clients.html
- Spring Security – Reactive Resource Server JWT: https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html
- Spring Security – Reactive Resource Server opaque tokens: https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/opaque-token.html
- Spring Security – Reactive OAuth2 WebTestClient testing (mockJwt, mockOidcLogin): https://docs.spring.io/spring-security/reference/reactive/test/web/oauth2.html
- Spring Authorization Server – Getting Started: https://docs.spring.io/spring-authorization-server/reference/getting-started.html
- IETF RFC 6749 – OAuth 2.0 Authorization Framework: https://www.rfc-editor.org/rfc/rfc6749
- IETF RFC 6750 – OAuth 2.0 Bearer Token Usage: https://www.rfc-editor.org/rfc/rfc6750
- IETF RFC 7636 – Proof Key for Code Exchange (PKCE): https://www.rfc-editor.org/rfc/rfc7636
- IETF RFC 8414 – OAuth2 Authorization Server Metadata: https://www.rfc-editor.org/rfc/rfc8414
- OpenID Connect Core 1.0 – Identity layer and ID token: https://openid.net/specs/openid-connect-core-1_0.html
- OWASP OAuth 2.0 Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/OAuth2_Cheat_Sheet.html
