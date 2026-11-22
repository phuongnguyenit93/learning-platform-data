# Luồng Authorization Code, địa chỉ chuyển hướng và callback trong Spring Security WebFlux

## Mục tiêu

Bài thuộc nhóm **Đăng nhập OAuth2/OIDC** của module **Spring Security - reactive**. Khi user chọn “Đăng nhập bằng một nhà cung cấp danh tính”, ứng dụng WebFlux không nên tự thu mật khẩu của nhà cung cấp đó. Thay vào đó, trình duyệt được redirect tới Authorization Server/OpenID Provider, user đăng nhập tại đó, rồi provider **chuyển trình duyệt trở lại callback của client** kèm một authorization code. Spring Security trao đổi code qua kết nối server-to-server, xác minh kết quả và thiết lập phiên đăng nhập cho ứng dụng.

Sau bài học, bạn có thể:

1. Phân biệt OAuth 2.0 Authorization Code Grant với OpenID Connect (OIDC) Login.
2. Nắm đúng **client initiation URL** `/oauth2/authorization/{registrationId}`, **IdP Authorization Endpoint** và **client callback** `/login/oauth2/code/{registrationId}`.
3. Giải thích vai trò của `redirect_uri`, `client_id`, `scope`, `state`, `nonce` và PKCE `code_verifier`/`code_challenge`.
4. Chỉ ra bước nào chạy trong browser và bước nào chạy **giữa hai server**.
5. Phân biệt authorization code, access token, ID token, refresh token, client secret và WebSession cookie.
6. Hiểu cách Spring Security WebFlux dùng `ReactiveClientRegistrationRepository`, `OAuth2AuthorizationRequestRedirectWebFilter`, `OAuth2LoginAuthenticationWebFilter`, `WebSessionOAuth2ServerAuthorizationRequestRepository`, `ServerSecurityContextRepository` và `ReactiveSecurityContextHolder`.
7. Chạy ví dụ **Java 17+, Spring Boot 3.3.13, Gradle, WebFlux** với Keycloak OIDC chạy local.
8. Tùy biến callback đúng cách bằng `authenticationMatcher(...)` **và** `redirect-uri`, đồng thời đăng ký URI chính xác tại provider.
9. Xử lý reverse proxy/HTTPS, multi-instance và lỗi mất session/state khi callback quay lại.
10. Kiểm thử các trường hợp thành công, thiếu state, sai redirect URI, code expired/replayed và lỗi token/issuer.
11. Phân biệt test `mockOidcLogin()` ở tầng HTTP với E2E test code exchange thật.
12. Áp dụng những yêu cầu bảo mật tối thiểu: HTTPS, session cookie, secret management, PKCE, token validation, CSRF và không ghi token/code vào log.

**Thông điệp chính:** Callback OAuth2 Login **không phải một controller GET bạn cần tự viết để nhận code**. Với Spring Security reactive, callback được xử lý trong security WebFilter chain, dùng dữ liệu yêu cầu đang chờ ở session để kiểm tra `state` và thực hiện token exchange.

## 1. OAuth 2.0 và OIDC: giống nhau ở luồng, khác mục đích

**OAuth 2.0** là framework ủy quyền cho client truy cập protected resources trong phạm vi được cho phép. **OpenID Connect 1.0** xây dựng trên OAuth2 để xác thực danh tính end user theo một giao thức có ID Token.

| Thành phần | OAuth2 Authorization Code | OIDC Authorization Code |
| --- | --- | --- |
| Mục đích | Cấp quyền truy cập tài nguyên | Cấp quyền và xác thực người dùng |
| Authorization request | `response_type=code` | `response_type=code` + scope `openid` |
| Authorization response | Code + state | Code + state |
| Token endpoint | Access token, đôi khi refresh token | Access token + **ID Token** (theo OIDC), có thể refresh token |
| User identity | Không chuẩn hóa bằng ID Token | Xác minh `id_token` với `iss`/`aud`/signature/time/`nonce` khi được sử dụng |
| Principal trong Spring Security | Có thể `OAuth2User` | Thường `OidcUser` |
| API access | Access token gửi tới resource server hợp lệ | **Vẫn** dùng access token, không lấy ID token làm API bearer token |

Scope `openid` là dấu hiệu quan trọng cho biết client đang yêu cầu OIDC. Scope `profile` hoặc `email` không có nghĩa mọi claim đều được nhà cung cấp bảo đảm có hoặc đã xác minh; cần đọc profile/claims thực và policy của IdP.

### Các vai trò trong ví dụ

| Vai trò | Ví dụ | Nhiệm vụ |
| --- | --- | --- |
| Resource Owner / End User | User `alice` | Đăng nhập tại IdP |
| User Agent | Chrome/Firefox | Thực hiện redirect; giữ cookie |
| OAuth2 Client / OIDC Relying Party | Spring Boot WebFlux `localhost:8080` | Bắt đầu login, nhận callback, đổi code lấy token, tạo SecurityContext |
| Authorization Server / OpenID Provider | Keycloak `localhost:9090` | Xác thực, phát code/token, cung cấp issuer/JWK |
| Resource Server | Một API dùng Bearer token (không bắt buộc trong lab) | Xác minh access token để cho gọi API |
| Spring Security reactive | `SecurityWebFilterChain` | Bảo vệ HTTP routes, xử lý start/callback, lưu/nạp phiên |

Đừng nhầm `spring-boot-starter-oauth2-client` với `spring-boot-starter-oauth2-resource-server`. Bài này dùng **OAuth2 Client** để login. Bản thân WebFlux app không tự phát access token hoặc ID token.

## 2. Sơ đồ Authorization Code Flow

```text
Browser                   WebFlux Client                  Keycloak OP
                         localhost:8080                  localhost:9090
   |                          |                                |
1. | GET /oauth2/authorization/keycloak                        |
   |------------------------->|                                |
   |                          | Tạo state, pending request       |
   |                          | lưu vào WebSession              |
2. |<-------- 302 Location: http://localhost:9090/.../auth?... |
   |                          |                                |
3. | GET authorize?response_type=code&state=S... -------------->|
   |                          |                                |
4. |<---------- Form login/consent tại Keycloak ----------------|
5. |------------- user login tại Keycloak --------------------->|
   |                          |                                |
6. |<------------ 302 Location: http://localhost:8080/.../code |
   |                               /keycloak?code=C&state=S     |
7. | GET /login/oauth2/code/keycloak?code=C&state=S             |
   |------------------------->|                                |
   |                          | Khôi phục pending request       |
   |                          | Đối chiếu state/session         |
8. |                          | POST /protocol/.../token ------>|
   |                          | code, redirect_uri, client auth |
   |                          | (+ code_verifier nếu PKCE)      |
9. |                          |<--- access_token, id_token ----|
   |                          | Validate ID Token + OidcUser    |
   |                          | Lưu SecurityContext/session    |
10.|<-------------------- 302 về saved request / trang chính --|
11.| GET /me + cookie phiên ----------------------------------->|
12.|<--------------------- 200 principal đã xác thực -----------|
```

Các bước 1, 3, 5, 7, 11 là **browser navigation/request**. Bước 8 là **back-channel HTTP request từ Spring Client sang token endpoint**, không phải `fetch` JavaScript mang client secret. Redirect callback chứa code và state, **không** chứa raw ID token/access token trong query của Authorization Code Flow chuẩn.

### 2.1. Bắt đầu login: URL của client

Spring Security WebFlux mặc định nhận:

```text
GET /oauth2/authorization/{registrationId}
```

Ví dụ `GET http://localhost:8080/oauth2/authorization/keycloak`. `registrationId` là ID của ClientRegistration do bạn đặt trong cấu hình Spring, **không nhất thiết bằng `client_id` đã cấp ở Keycloak**. Request này được `OAuth2AuthorizationRequestRedirectWebFilter` xử lý; nó gọi `DefaultServerOAuth2AuthorizationRequestResolver` để tạo authorization request và redirect browser tới IdP.

Không nhầm đây là token endpoint hay callback. Một link HTML như sau là đủ để bắt đầu:

```html
<a href="/oauth2/authorization/keycloak">
  Đăng nhập bằng Keycloak
</a>
```

Không tự ghép URL chứa `state` tĩnh hoặc client secret trong frontend.

### 2.2. Authorization endpoint: URL của IdP

Trong ví dụ Keycloak realm `learning`:

```text
http://localhost:9090/realms/learning/protocol/openid-connect/auth
```

Browser được redirect đến đó kèm:

```http
GET /realms/learning/protocol/openid-connect/auth?
  response_type=code
  &client_id=webflux-login
  &redirect_uri=http%3A%2F%2Flocalhost%3A8080%2Flogin%2Foauth2%2Fcode%2Fkeycloak
  &scope=openid%20profile%20email
  &state=<ngẫu-nhiên>
  [&nonce=<nonce-nếu-có>]
  [&code_challenge=<pkce>&code_challenge_method=S256]
```

Đây là **biểu diễn khái niệm xuống dòng**, không phải URL được copy nguyên vào browser. Các tham số thực tế còn tùy client/provider/version và cấu hình PKCE. Browser thấy `client_id`/`state`/`redirect_uri` là bình thường. **Không được** có `client_secret` trong URL authorize.

### 2.3. Callback: URL của Spring Client

Mặc định:

```text
{baseUrl}/login/oauth2/code/{registrationId}
```

Với demo:

```text
http://localhost:8080/login/oauth2/code/keycloak
```

Sau khi user đăng nhập, Keycloak trả:

```http
HTTP/1.1 302 Found
Location: http://localhost:8080/login/oauth2/code/keycloak?code=C&state=S
```

Spring Security `OAuth2LoginAuthenticationWebFilter` nhận callback, tải request đã lưu trong WebSession và so `state`. Bạn không cần đặt `@GetMapping("/login/oauth2/code/keycloak")`, và **không nên** tự đổi code lấy token trong controller nghiệp vụ. Làm thủ công dễ bỏ state, PKCE, nonce, ID Token verification và error handling.

### 2.4. Token endpoint: kết nối phía server

Keycloak token endpoint:

```text
POST http://localhost:9090/realms/learning/protocol/openid-connect/token
```

Payload chính:

```http
grant_type=authorization_code
&code=C
&redirect_uri=http%3A%2F%2Flocalhost%3A8080%2Flogin%2Foauth2%2Fcode%2Fkeycloak
[&code_verifier=<nếu PKCE được bật>]
```

Với **confidential client**, token endpoint còn yêu cầu client authentication như `client_secret_basic`. Spring Security OAuth2 client gửi request từ backend, nhận response và xử lý ID Token, không để user agent giữ client secret. Authorization code phải **short-lived và single-use**; replay code sẽ bị token endpoint từ chối.

## 3. Những URI rất dễ nhầm

| Đường dẫn | Thuộc bên nào? | Mục đích |
| --- | --- | --- |
| `/login` | Spring Client | Trang login mặc định/chọn IdP khi framework tạo |
| `/oauth2/authorization/keycloak` | Spring Client | Start authorization flow |
| `/realms/learning/protocol/openid-connect/auth` | Keycloak | Authorization endpoint, login/consent |
| `/login/oauth2/code/keycloak` | Spring Client | Callback nhận code/state |
| `/realms/learning/protocol/openid-connect/token` | Keycloak | Back-channel code exchange |
| `/me` | Controller Spring Client | Xem principal sau khi login |
| `/logout` | Spring Client | Local logout theo cấu hình (khác OIDC OP logout) |

**Authorization endpoint != callback URL.** **Callback URL != login page.** **Token endpoint != endpoint browser cần gọi trực tiếp**. Tên path chứa `login` không biến callback thành form-login POST.

## 4. Các tham số bảo mật quan trọng

### 4.1. client_id khác registrationId

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          keycloak:                    # registrationId
            client-id: webflux-login   # client_id của IdP
```

Link bắt đầu dùng `keycloak`, trong khi IdP nhận `client_id=webflux-login`. Khi debug 404 registration, cần xem đúng key Spring thay vì đổi Client ID trên Keycloak một cách tùy tiện.

### 4.2. redirect_uri: ba nơi phải nhất quán

Một redirect URI hợp lệ phải khớp **đồng thời**:

1. `spring.security.oauth2.client.registration.keycloak.redirect-uri` trên Client.
2. `authenticationMatcher` của WebFlux OAuth2 Login filter xử lý callback.
3. **Valid Redirect URIs** trong cấu hình client ở Keycloak.

Với mặc định cả ba dùng:

```text
http://localhost:8080/login/oauth2/code/keycloak
```

Mỗi chi tiết có ý nghĩa: `http` khác `https`; `localhost` khác `127.0.0.1`; cổng 8080 khác 8443; `/login/oauth2/code` khác `/login/oauth2/callback`. Không đặt wildcard redirect rộng kiểu `https://*.example.com/*` để né `invalid_redirect_uri`.

**Không biến tham số `returnTo`/`next` chưa kiểm chứng thành redirect_uri hoặc success URL**: đó có thể là open redirect làm code/token rò rỉ hoặc chuyển người dùng đến trang giả mạo.

### 4.3. state: liên kết response với yêu cầu đã bắt đầu

`state` là chuỗi khó đoán do Client tạo trong authorization request. Khi callback quay lại, Spring Security tìm pending `OAuth2AuthorizationRequest` đã lưu và đối chiếu `state`.

```text
GET /oauth2/authorization/keycloak
   -> tạo state S1
   -> lưu pending request S1 trong WebSession
   -> redirect IdP với state S1

GET /login/oauth2/code/keycloak?code=C1&state=S1
   -> lấy pending request từ cùng WebSession
   -> so state
   -> hợp lệ mới đổi code C1

Nếu state khác / không có pending request -> DENY login.
```

`state` giúp chống **login CSRF** và callback injection. Đừng thay state bằng một chuỗi hằng, đừng tắt validation khi gặp lỗi session. Một callback có authorization code “có vẻ hợp lệ” nhưng **không liên kết yêu cầu của browser này** không được coi là một phiên login an toàn.

### 4.4. WebSession lưu pending authorization request

Trong reactive stack, `ServerAuthorizationRequestRepository` mặc định là `WebSessionOAuth2ServerAuthorizationRequestRepository`. Browser thường nhận cookie session của Spring Client khi bắt đầu OAuth login; khi IdP redirect quay về, browser cần gửi lại cookie để Client tìm request `state` đã lưu.

**Nếu cookie mất**, có thể thấy `authorization_request_not_found` dù IdP đã xác thực user thành công. Các nguyên nhân gồm:

- Thay `localhost` thành `127.0.0.1` hoặc đổi hostname/scheme giữa đầu và cuối.
- Cookie `SameSite=Strict` chặn một số navigation cross-site về Client.
- Session hết hạn, logout hoặc bị xóa trong lúc đang ở IdP.
- Pod callback không có shared WebSession của pod đã tạo pending request.
- Redis/Session store outage, serializer/namespace không tương thích.
- Multiple concurrent login flows hoặc tab khác ghi đè/đổi pending request theo hành vi repository/phiên bản.

**Không dùng CORS wildcard để chữa lỗi cookie/session**. OAuth callback là top-level navigation; CORS không quyết định việc trình duyệt được redirect về callback hay không.

### 4.5. PKCE không phải state

PKCE dùng một `code_verifier` bí mật phía client và `code_challenge` đã biến đổi:

```text
code_verifier (chuỗi ngẫu nhiên)
      |
      +-- SHA-256 + base64url --> code_challenge
      |                           gửi lúc authorization request
      |
      +-------------------------> code_verifier
                                  gửi khi token exchange
```

Authorization Server kiểm tra verifier tương ứng challenge trước khi đổi code lấy token. Nhờ đó code bị chặn giữa đường sẽ khó bị kẻ khác sử dụng nếu không có verifier.

**Spring Security 6.x** hỗ trợ PKCE cho public client. PKCE được tự dùng khi ClientRegistration có `client-authentication-method=none`, không có client secret, hoặc `ClientRegistration.clientSettings.requireProofKey=true`. Với confidential client dùng secret như demo, **đừng mặc định tuyên bố PKCE luôn bật**: kiểm tra authorization request thật và cấu hình provider/client nếu yêu cầu PKCE.

PKCE bổ sung bảo vệ code; nó **không** thay state correlation, client authentication phù hợp, redirect URI validation hoặc OIDC ID Token verification.

### 4.6. nonce và OIDC ID Token

OIDC `nonce` (khi được gửi) giúp gắn ID Token với authentication request và hạn chế replay. ID Token cần kiểm tra chữ ký thông qua JWK/algorithms được phép, `iss`, `aud`, `exp`/thời gian, `nonce` tương ứng khi áp dụng, và những điều kiện tiêu chuẩn khác.

Không dùng code kiểu “`Base64.decode(jwt.payload)` rồi tin trường role” làm authentication. Spring Security OIDC login có các thành phần xác minh token; đừng tắt signature/issuer validation để vượt qua lỗi cấu hình Keycloak.

### 4.7. Code, tokens và session khác nhau

| Loại | Mục đích | Nơi nên được dùng |
| --- | --- | --- |
| Authorization code | Một lần đổi lấy token | Callback → back-channel token request |
| Access token | Truy cập protected resource đúng audience/scope | HTTP Authorization Bearer tới Resource Server |
| ID Token | Chứng minh OIDC authentication với Client | Client xác minh identity, không dùng thay access token |
| Refresh token | Xin access token mới khi được cấp | Server/token store an toàn, theo chính sách refresh |
| Client secret | Chứng thực confidential OAuth Client | Server/secret manager, không đưa vào browser |
| `SESSION` cookie | Định danh WebSession của Spring Client | Browser giữ để nạp pending request/context |
| Spring `SecurityContext` | Authentication của user tại Client | WebSession + Reactor Context |

Browser callback có thể hiển thị code trong URL tạm thời; **không log/raw trace callback query**, không gửi nó sang analytics hoặc link bên thứ ba. Không coi code như password dùng nhiều lần.

## 5. Spring Security WebFlux triển khai flow ra sao?

Các thành phần chính:

| Class/interface | Vai trò |
| --- | --- |
| `ReactiveClientRegistrationRepository` | Boot tạo registration từ `spring.security.oauth2.client.*` |
| `ClientRegistration` | Metadata client: client ID/secret, grant, redirect, scopes, provider endpoints |
| `DefaultServerOAuth2AuthorizationRequestResolver` | Xây authorization request theo URL start và registration ID |
| `OAuth2AuthorizationRequestRedirectWebFilter` | Redirect browser tới Authorization Endpoint |
| `WebSessionOAuth2ServerAuthorizationRequestRepository` | Lưu pending request/state trong WebSession |
| `OAuth2LoginAuthenticationWebFilter` | Xử lý callback code/state; xác thực OAuth2/OIDC |
| `OidcReactiveOAuth2UserService` | Xử lý OIDC user identity/UserInfo theo cấu hình |
| `ReactiveOAuth2AccessTokenResponseClient` | Back-channel token exchange cho OAuth2 code grant |
| `ServerSecurityContextRepository` | Lưu/nạp SecurityContext giữa các request |
| `ReactiveSecurityContextHolder` | Lấy Authentication trong Reactor Context |
| `OAuth2AuthenticationToken`/`OidcUser` | Authentication/principal sau callback thành công |
| `ServerOAuth2AuthorizedClientRepository` | Quản lý authorized client và token khi cần gọi API |

Sơ đồ hai giai đoạn lưu trữ:

```text
Trước callback:
  /oauth2/authorization/keycloak
       -> WebSession lưu OAuth2AuthorizationRequest + state

Sau callback thành công:
  /login/oauth2/code/keycloak
       -> Authentication/OidcUser
       -> ServerSecurityContextRepository lưu context
       -> browser tiếp tục dùng session cookie cho /me
```

Trong WebFlux, authentication của request nằm trong **Reactor Context**, không phải Servlet `ThreadLocal`. Nếu cần đọc principal trong reactive service, dùng `ReactiveSecurityContextHolder.getContext()` hoặc argument resolver phù hợp, tránh `block()`.

## 6. Ví dụ đầy đủ Java 17+, Spring Boot 3.3.13 và Keycloak

Dự án chạy Spring Client tại `http://localhost:8080`, Keycloak tại `http://localhost:9090`. Ví dụ này là lab local, **không** dành để triển khai công khai với HTTP hoặc mật khẩu mẫu.

### 6.1. Cấu trúc thư mục

```text
webflux-oidc-code-flow/
  settings.gradle
  build.gradle
  src/
    main/
      java/example/OidcCodeFlowApplication.java
      resources/application.yml
    test/
      java/example/OidcCodeFlowApplicationTests.java
```

### 6.2. settings.gradle

```groovy
rootProject.name = 'webflux-oidc-code-flow'
```

### 6.3. build.gradle

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'example'
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
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Dùng Spring Boot BOM để quản lý Spring Security, WebFlux, OIDC và Reactor. **Không thêm `spring-boot-starter-web`** khi mục tiêu là WebFlux. Không copy cấu hình `HttpSecurity`/Servlet `OAuth2LoginAuthenticationFilter` sang reactive `ServerHttpSecurity`.

### 6.4. application.yml

Tạo `src/main/resources/application.yml`:

```yaml
server:
  port: 8080

spring:
  security:
    oauth2:
      client:
        registration:
          keycloak:
            provider: keycloak
            client-id: webflux-login
            client-secret: ${OIDC_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
        provider:
          keycloak:
            issuer-uri: http://localhost:9090/realms/learning
```

Chi tiết:

- `registration.keycloak` ⇒ `registrationId=keycloak`, không phải client ID.
- `client-id=webflux-login` phải đúng Keycloak client.
- `client-secret` lấy từ **biến môi trường `OIDC_CLIENT_SECRET`**, không commit Git, không nhúng vào JavaScript.
- `client_secret_basic` chứng thực Client tại **token endpoint**, không liên quan mật khẩu user.
- `authorization_code` yêu cầu cấp authorization code.
- `openid` khiến Spring Security dùng xử lý OIDC Login thay vì chỉ OAuth2 generic user.
- `redirect-uri` có template mặc định; `{baseUrl}` dựa vào URL mà server nhìn thấy sau forwarded-header handling.
- `issuer-uri` cho Boot/Spring Security thực hiện OIDC discovery để nhận authorization/token/JWK endpoints và issuer. IdP phải sẵn sàng lúc Spring xây registration; nên chạy Keycloak trước.

### 6.5. Khởi chạy Keycloak local

Yêu cầu Docker đã cài. Trên Linux/macOS:

```bash
docker run --rm --name keycloak-oidc-lab \
  -p 127.0.0.1:9090:8080 \
  -e KC_BOOTSTRAP_ADMIN_USERNAME=admin \
  -e KC_BOOTSTRAP_ADMIN_PASSWORD=admin \
  quay.io/keycloak/keycloak:26.8.2 \
  start-dev --hostname=http://localhost:9090
```

Port host 9090 khác Spring Boot 8080; port bên trong container vẫn 8080. Với Windows PowerShell, nhập lệnh Docker **trên một dòng** nếu không dùng cú pháp xuống dòng của PowerShell.

**Chỉ lab:** `start-dev`, admin/admin và HTTP không phù hợp production. Chỉ bind Redis/Keycloak/etc. vào localhost trong lab; khi triển khai thật, bắt buộc HTTPS, credentials mạnh, Keycloak production mode, database/HA và backup.

Mở Admin Console:

```text
http://localhost:9090/admin/
```

Đăng nhập bằng admin demo. Container `--rm` bị xóa sau khi dừng; dữ liệu Keycloak dev có thể mất. Với môi trường học kéo dài, cấu hình volume/DB test riêng và chính sách reset phù hợp.

### 6.6. Tạo realm, client, user

Trong Keycloak Admin Console:

1. Tạo realm tên **`learning`**.
2. Chuyển đến realm `learning`, mở **Clients → Create client**.
3. Chọn **OpenID Connect**, Client ID **`webflux-login`**.
4. Bật **Client authentication** (confidential client).
5. Bật **Standard flow** để hỗ trợ Authorization Code Grant. Không cần bật Direct Access Grants/password grant.
6. Đặt **Valid Redirect URIs** chính xác:

```text
http://localhost:8080/login/oauth2/code/keycloak
```

7. Có thể đặt Home URL `http://localhost:8080/`. **Không cần `Web origins: *`** để OP redirect browser: callback là navigation, không phải JavaScript CORS fetch.
8. Lấy Client secret ở tab **Credentials** theo quyền được giao, đưa vào `OIDC_CLIENT_SECRET` cho backend.
9. Mở **Users**, tạo user `alice` và đặt mật khẩu **`learn`** trong lab. Chọn non-temporary nếu muốn không bị buộc đổi mật khẩu ở lần đầu.
10. Kiểm tra realm trong URL là `learning`, không nhầm admin realm `master`.

Mở OIDC discovery:

```text
http://localhost:9090/realms/learning/.well-known/openid-configuration
```

Hoặc:

```bash
curl -fsS http://localhost:9090/realms/learning/.well-known/openid-configuration
```

Trường `issuer` phải là `http://localhost:9090/realms/learning`. Nếu là host/port khác, sửa Keycloak hostname/network trước; **không tắt issuer validation**.

### 6.7. Spring Boot Java application

Tạo `src/main/java/example/OidcCodeFlowApplication.java`:

```java
package example;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.MediaType;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

import static org.springframework.security.config.Customizer.withDefaults;

@SpringBootApplication
@EnableWebFluxSecurity
@RestController
public class OidcCodeFlowApplication {

    public static void main(String[] args) {
        SpringApplication.run(OidcCodeFlowApplication.class, args);
    }

    @GetMapping(value = "/", produces = MediaType.TEXT_HTML_VALUE)
    public String home() {
        return """
            <!doctype html>
            <html lang="vi">
            <head><meta charset="utf-8"><title>OIDC Code Flow</title></head>
            <body>
              <h1>Spring Security WebFlux OAuth2/OIDC Login</h1>
              <p><a href="/oauth2/authorization/keycloak">
                Dang nhap bang Keycloak
              </a></p>
              <p><a href="/me">Xem danh tinh da dang nhap</a></p>
            </body>
            </html>
            """;
    }

    @GetMapping("/public/ping")
    public Map<String, String> ping() {
        return Map.of("message", "PONG");
    }

    @GetMapping("/me")
    public Mono<Map<String, String>> me() {
        return ReactiveSecurityContextHolder.getContext()
                .map(SecurityContext::getAuthentication)
                .map(this::safeProfile);
    }

    private Map<String, String> safeProfile(Authentication auth) {
        String type = auth.getPrincipal() instanceof OidcUser
                ? "oidc" : "other";

        // Không xuất ID Token, access token hay session ID.
        return Map.of(
                "name", auth.getName(),
                "principalType", type);
    }

    @Bean
    SecurityWebFilterChain security(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/", "/public/**").permitAll()
                        .anyExchange().authenticated())
                .oauth2Login(withDefaults())
                .build();
    }
}
```

**Vì sao code đủ cho Authorization Code/OIDC Login?**

- `ServerHttpSecurity.oauth2Login(withDefaults())` gắn các filter OAuth2 login vào `SecurityWebFilterChain` reactive.
- `ReactiveClientRegistrationRepository` do Spring Boot tạo dựa trên `application.yml`.
- Link ở trang chính gọi URL start mặc định; framework tạo `state` và lưu pending authorization request.
- Không cần controller callback; Spring Security filter nhận `/login/oauth2/code/keycloak` và thực hiện token exchange.
- Khi OIDC login thành công, principal là `OidcUser`; `/me` đọc Authentication từ `ReactiveSecurityContextHolder` (Reactor Context), không dùng Servlet ThreadLocal.
- `auth.getName()` thường là subject/claim được cấu hình, **không mặc định bằng username hiển thị "alice"**.
- Demo chỉ trả hai field an toàn. Không trả access token, ID token, client secret, raw profile claims hay WebSession ID.
- `/me` yêu cầu authenticated; request chưa login thường redirect đến login page/entry point do Spring Security cấu hình.
- CSRF vẫn bật theo mặc định. Đừng thêm `csrf.disable()` chỉ để OAuth2 login hoạt động; logout/thay đổi trạng thái vẫn phải đánh giá CSRF.
- Ứng dụng không định nghĩa UserDetailsService/mật khẩu; **Keycloak** xác thực user.

### 6.8. Chạy Spring Boot

Sau khi Keycloak đã tạo realm/client/user, đặt secret.

Linux/macOS:

```bash
export OIDC_CLIENT_SECRET='your-real-keycloak-client-secret'
gradle bootRun
```

Windows PowerShell:

```powershell
$env:OIDC_CLIENT_SECRET = "your-real-keycloak-client-secret"
gradle bootRun
```

Thay chuỗi mẫu bằng secret thật của client trong lab; không commit secret hoặc dán vào ticket/chat. Nếu có Gradle Wrapper, dùng `./gradlew bootRun` / `gradlew.bat bootRun`. Với Spring Boot chạy trong container riêng, `localhost` bên trong container có ý nghĩa khác host; cần dùng DNS/network nhất quán với issuer và public redirect URL, không copy config local một cách mù quáng.

### 6.9. Chạy flow end-to-end bằng browser

1. Mở `http://localhost:8080/`.
2. Mở DevTools → Network, bật Preserve log.
3. Nhấn **Đăng nhập bằng Keycloak**; xem GET `/oauth2/authorization/keycloak`.
4. Request start trả 302 đến `http://localhost:9090/realms/learning/protocol/openid-connect/auth` với `response_type=code`, `client_id=webflux-login`, `redirect_uri`, `state` và scope chứa `openid`.
5. Đăng nhập Keycloak realm learning với `alice` / `learn`.
6. Keycloak chuyển browser về `/login/oauth2/code/keycloak?code=...&state=...` trên `localhost:8080`.
7. Spring Client đổi code lấy token trong back-channel. Browser có thể không hiển thị token endpoint POST trong Network tab vì lệnh gọi diễn ra **từ backend**.
8. Sau callback, Spring Security redirect theo saved request/success handler.
9. Mở `http://localhost:8080/me` trong cùng browser profile. Response JSON dự kiến:

```json
{
  "name": "<subject-from-IdP>",
  "principalType": "oidc"
}
```

Giá trị `name` là ID của principal theo Keycloak/Spring Security, thường không phải literal username `alice`. Đây là kết quả **dự kiến**, không phải log chạy sẵn trên máy người học.

10. Mở Incognito mới vào `/me`: chưa có cookie session của Client sẽ đi lại login flow.
11. Xóa cookie client rồi truy cập `/me`: có thể tự login lại rất nhanh nếu Keycloak còn SSO cookie; **SSO session khác local client session**.
12. Nếu callback lỗi, đừng copy query chứa code/state ra log chia sẻ. Dùng diagnostics đã redact và các bước mục 11.

## 7. Kiểm thử bằng WebTestClient

Có **hai mức**:

- **Spring test mức filter/handler:** kiểm public route, 302 start authorization, principal đã authenticated bằng mock.
- **E2E browser + IdP:** kiểm sự kiện user nhập password tại Keycloak, callback code/state thật, token exchange/JWK/ID Token validation và session persistence.

`mockOidcLogin()` giúp tập trung test authorization/controller mà **không chứng minh** IdP có phát token hợp lệ. Đừng trộn hai loại kết quả.

### 7.1. Tạo test class

Tạo `src/test/java/example/OidcCodeFlowApplicationTests.java`:

```java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.mockOidcLogin;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureWebTestClient
class OidcCodeFlowApplicationTests {

    @Autowired
    WebTestClient client;

    @Test
    void publicPingIsAvailableWithoutLogin() {
        client.get().uri("/public/ping")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.message").isEqualTo("PONG");
    }

    @Test
    void anonymousProtectedEndpointRedirectsToLogin() {
        client.get().uri("/me")
                .exchange()
                .expectStatus().is3xxRedirection()
                .expectHeader().exists(HttpHeaders.LOCATION);
    }

    @Test
    void authorizationStartRedirectsWithStateAndCodeFlow() {
        var result = client.get()
                .uri("/oauth2/authorization/keycloak")
                .exchange()
                .expectStatus().is3xxRedirection()
                .returnResult(Void.class);

        String location = result.getResponseHeaders()
                .getFirst(HttpHeaders.LOCATION);

        assertNotNull(location);
        assertTrue(location.contains(
                "/realms/learning/protocol/openid-connect/auth"));
        assertTrue(location.contains("response_type=code"));
        assertTrue(location.contains("client_id=webflux-login"));
        assertTrue(location.contains("state="));
        assertTrue(location.contains("redirect_uri="));
    }

    @Test
    void mockOidcPrincipalCanReadMe() {
        client.mutateWith(mockOidcLogin())
                .get().uri("/me")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.principalType").isEqualTo("oidc");
    }
}
```

Chạy khi Keycloak đã có realm/client và discovery endpoint hoạt động, vì `issuer-uri` được Spring Boot dùng trong quá trình dựng registration:

```bash
gradle test
```

**Kiểm chứng đúng phạm vi:**

- `@SpringBootTest(webEnvironment=MOCK)` + `@AutoConfigureWebTestClient` cho phép test WebFlux security chain trong application context mà không cần live HTTP port.
- `mockOidcLogin()` cung cấp một mocked OIDC Authentication cho `/me`; nó **không gọi Keycloak**, không kiểm code, token exchange hay JWT signature.
- Test authorization initiation kiểm redirect tới Keycloak, `state`, `response_type=code` và tham số `redirect_uri` tồn tại. Vì test dùng mock server context, `baseUrl` trong URL redirect có thể không phải chính xác port 8080; dùng browser thật để xác nhận public redirect URI.
- Không tự kiểm thử callback với `code=fake` rồi kỳ vọng luôn một status cố định; failure handler có thể redirect sang `/login?error` hoặc response khác tùy config/version. **Tiêu chí bảo mật** là không có SecurityContext authenticated khi state/code không hợp lệ.

### 7.2. Test E2E có IdP thật

| Test | Hành động | Kết quả an toàn |
| --- | --- | --- |
| Flow thành công | Browser login Keycloak và quay lại client | `/me` 200, principal đúng |
| Callback không state | Gọi callback không có pending request/state | Không authenticated |
| State không khớp | Callback khác state đã lưu | Từ chối |
| Code replay | Dùng code đã đổi token trước đó | Từ chối (single-use) |
| Code expired | Đợi hết hạn theo IdP | Không tạo login |
| Client secret sai | Token endpoint nhận auth sai | `invalid_client`, không lộ secret |
| Redirect mismatch | Cấu hình port/path sai tại IdP | IdP từ chối URI |
| ID token issuer/signature sai | IdP test stub hoặc trust config lỗi | Token validation fail-closed |
| User từ chối consent | OP trả `error=access_denied` | Login thất bại, không phát context |
| Session hết hạn | Mất pending request trước callback | Không authenticated |
| Callback tới pod B | Start ở A, callback ở B | Chỉ thành công khi pending WebSession chia sẻ |
| Reverse proxy HTTPS | Public app URL HTTPS, upstream HTTP | Callback đúng scheme/host công khai |

Các test với token/code sai nên chạy trong môi trường test với dữ liệu giả; không log raw credential hay token. Nếu dùng IdP test container, cần provision realm/client/test user trước khi Spring context khởi tạo.

## 8. Tùy biến callback path trong WebFlux

Mặc định:

```text
/login/oauth2/code/{registrationId}
```

Giả sử muốn:

```text
/login/oauth2/callback/{registrationId}
```

**Cần đổi cả ba thành phần:**

### 8.1. Matcher trong reactive security chain

Thay `.oauth2Login(withDefaults())` bằng:

```java
.oauth2Login(oauth2 -> oauth2
    .authenticationMatcher(
        new PathPatternParserServerWebExchangeMatcher(
            "/login/oauth2/callback/{registrationId}")))
```

Import:

```java
import org.springframework.security.web.server.util.matcher.PathPatternParserServerWebExchangeMatcher;
```

Đoạn này là **fragment thay vào class ở mục 6**, không phải class runnable độc lập. API ở đây là **`ServerHttpSecurity.oauth2Login(...).authenticationMatcher(...)` của WebFlux**. Đừng copy API Servlet `HttpSecurity.oauth2Login().redirectionEndpoint().baseUri(...)` sang reactive.

### 8.2. Client registration redirect URI

Đổi property đang có thành:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          keycloak:
            redirect-uri: "{baseUrl}/login/oauth2/callback/{registrationId}"
```

Đây là mảnh YAML mô tả một property. **Sửa/gộp** vào `application.yml` hiện có, không dán cả block tạo duplicate keys.

### 8.3. Valid Redirect URIs của Keycloak

Với lab, đăng ký:

```text
http://localhost:8080/login/oauth2/callback/keycloak
```

Không giữ URL `/login/oauth2/code/keycloak` rồi đòi OP gửi callback tới path mới. Khi deploy public HTTPS, đăng ký URI public tương ứng.

### 8.4. Tùy biến authorization initiation URL là việc khác

Đổi start URL `/oauth2/authorization/keycloak` thành `/login/oauth2/authorization/keycloak` cần custom `ServerOAuth2AuthorizationRequestResolver`/`ServerWebExchangeMatcher`, rồi sửa link login. Nó **không tự đổi callback**. Tách hai việc để không tạo 404/redirect loop.

## 9. Reverse proxy, HTTPS và baseUrl

Mô hình production thường:

```text
Browser: https://app.example.test
       |
       v
Ingress / TLS termination
       |
       v
WebFlux upstream: http://app:8080
```

Với template `{baseUrl}`, nếu app không được cung cấp đúng host/scheme public, nó có thể sinh sai:

```text
http://app:8080/login/oauth2/code/keycloak
```

trong khi Keycloak chỉ cho:

```text
https://app.example.test/login/oauth2/code/keycloak
```

Đây là lỗi cấu hình proxy/base URL, **không phải** lỗi role hay CORS.

### 9.1. Forwarded headers trong Spring Boot

Boot WebFlux có thể dùng:

```yaml
server:
  forward-headers-strategy: framework
```

Spring Framework xử lý các `Forwarded`/`X-Forwarded-*` headers qua `ForwardedHeaderTransformer` trong reactive stack. **Chỉ bật với reverse proxy đáng tin**: ingress phải loại bỏ/ghi đè forwarded headers do client ngoài Internet tự tạo; application upstream phải được cô lập để không nhận traffic giả mạo headers trực tiếp.

Một số hệ thống muốn dùng `server.forward-headers-strategy=native` khi web server hỗ trợ đúng; cần đọc tài liệu Boot và kiểm thử thực tế. Không đặt một setting rồi tin redirect_uri đã đúng mà không xem URL trong browser Network.

### 9.2. Redirect URI cố định

Nếu public origin chỉ có một, có thể dùng:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          keycloak:
            redirect-uri: "https://app.example.test/login/oauth2/code/keycloak"
```

Nó tránh sai base URL nhưng cần config riêng cho staging/dev, không hardcode production URL vào mọi môi trường. Giữ exact allowlist ở IdP và không mở wildcard rộng.

### 9.3. Những chỗ cần khớp

- Public scheme HTTPS/HTTP.
- Public hostname; `localhost` khác `127.0.0.1`.
- Public port; 443 mặc định khác 8443.
- Context path/reverse proxy prefix.
- Callback path và registration ID.
- IdP issuer hostname/port; `iss` trong ID Token phải khớp issuer đã đăng ký.
- Cookie domain/path/SameSite/Secure khi browser quay từ IdP về.

**Khi IdP công bố issuer nội bộ khác public** (ví dụ ID Token `iss=http://keycloak:8080/realms/...` trong khi client cấu hình public HTTPS URL), phải sửa Keycloak canonical hostname/network; **không bỏ issuer validation**.

## 10. Session, nhiều nút, SameSite và login state

Spring Security lưu pending authorization request trong WebSession. Khi browser quay về callback, **cookie phiên của client** phải nhận diện đúng session.

```text
Node A: GET /oauth2/authorization/keycloak
  -> pending request có state S trong WebSession I
  -> browser nhận Cookie SESSION=I

IdP redirect callback
  -> GET /login/oauth2/code/keycloak?code=C&state=S
  -> browser gửi Cookie SESSION=I

Node A/B:
  -> load WebSession I
  -> tìm pending request state S
  -> so khớp rồi xử lý C
```

### 10.1. Nếu callback vào node khác

Nếu WebSession nằm riêng trong RAM từng process:

```text
Start ở node A -> session pending chỉ ở A
Callback về node B -> B không thấy state -> login fail
```

**Spring Session Redis reactive** có thể cung cấp `ReactiveSessionRepository` chia sẻ WebSession giữa các nút, bao gồm pending authorization request và security context. Tất cả các node cần cùng Redis, namespace, serializer, secret/config, session TTL và cookie policy. Sticky sessions giảm chuyển nút nhưng không bảo đảm sống qua node failure.

**Không thay giải pháp bằng việc tắt `state` hoặc lưu code trong query tùy ý**.

### 10.2. SameSite cookie

OAuth redirect là top-level navigation; cookie `SameSite=Lax` trong các điều kiện thường có thể được gửi khi browser quay về client bằng GET. `SameSite=Strict` có thể làm cookie không gửi trong cross-site navigation; `SameSite=None; Secure` cần HTTPS và có rủi ro CSRF khác cần xem xét. Browser privacy settings cũng có thể tác động.

Đừng xem `Access-Control-Allow-Origin` là công tắc cho phép cookie callback: **CORS không kiểm soát top-level OAuth navigation**. Đừng bật CORS wildcard tại token endpoint để browser gửi client secret; confidential client nên đổi code phía backend.

### 10.3. Session fixation và local logout

Sau đăng nhập, session ID có thể thay đổi theo cơ chế chống session fixation; khi test hãy giữ **cookie mới nhất**. Không dựa vào ID session cũ trước login.

Local logout của ứng dụng không nhất thiết xóa Keycloak SSO session. User quay lại IdP có thể được đăng nhập tự động. **OIDC RP-Initiated Logout** là một flow khác, đòi cấu hình riêng ở RP/OP. Thu hồi access/refresh token cũng khác với xóa WebSession.

Với Spring Security cookie-backed browser login, POST logout có thể yêu cầu CSRF token. Không tắt CSRF chỉ vì đã dùng OIDC.

## 11. Chẩn đoán lỗi Authorization Code và callback

### 11.1. `invalid_redirect_uri` / `redirect_uri_mismatch`

IdP không chấp nhận callback client gửi trong authorization request. So:

- Request `redirect_uri` ở browser Network (giải mã URL).
- `registration.keycloak.redirect-uri` trong Spring.
- Reactive callback matcher mặc định hoặc custom.
- **Valid Redirect URIs** của đúng realm/client trên IdP.
- Scheme, hostname, port, prefix/trailing slash và proxy headers.

**Sửa chính xác URI**, không mở wildcard hoặc vô hiệu redirect check.

### 11.2. `authorization_request_not_found`

Spring Security không tìm thấy pending authorization request:

- Cookie `SESSION` không gửi về callback;
- Session hết hạn/khởi tạo mới;
- Callback vào node không chia sẻ session;
- Đồng thời nhiều login flows làm mất pending state;
- Origin/host khác giữa start và callback;
- Session store Redis bị lỗi;
- Request đã được consume hoặc callback replay.

Sửa session/cookie/Redis/host, **không tắt state validation**.

### 11.3. `invalid_grant`

Token endpoint từ chối code vì hết hạn, đã dùng, sai client/redirect_uri, PKCE verifier không hợp lệ hoặc lỗi theo policy IdP. Không thử lặp lại cùng code bằng curl để “khắc phục”; code là single-use. Hãy bắt đầu một flow login mới.

### 11.4. `invalid_client`

Sai Client ID/secret, auth method mismatch, nhầm realm, secret bị rotate mà backend chưa cập nhật, hoặc confidential/public mode không khớp. Không tắt client authentication của confidential client để né lỗi; đồng bộ Client Registration và credentials.

### 11.5. State mismatch

Khi browser trả `state` khác yêu cầu đã lưu, Spring phải từ chối. Không biến lỗi thành một login mới mặc định user “đã xác thực ở Keycloak”. Cần kiểm tra cookie, nhiều tab, session store, callback reuse và security chain.

### 11.6. Callback 404

Có thể `redirect-uri` đã đổi nhưng `authenticationMatcher` vẫn mặc định, hoặc request đi vào security chain khác. Cần đảm bảo `/oauth2/authorization/{registrationId}` và `/login/oauth2/code/{registrationId}` đều được xử lý bởi chain có OAuth2 login.

### 11.7. Redirect loop

Khi session không lưu Authentication hoặc callback thất bại, `/me` có thể redirect login mãi. Kiểm tra:
- Có thực sự nhận code/state hợp lệ?
- Token endpoint thành công?
- ID Token verification đúng?
- SecurityContext được lưu vào session?
- Browser có gửi cookie trên request sau login?
- User đã login nhưng authorization policy chặn `/me`?

### 11.8. Issuer mismatch hoặc JWT signature invalid

Cấu hình `issuer-uri` sai host/port/realm, Keycloak trả issuer khác canonical URL, hoặc JWK key đã rotate/config lỗi. Kiểm discovery document và ID Token metadata trong log **đã redact**, không vô hiệu chữ ký/issuer validation.

### 11.9. Provider trả `error=access_denied`

User từ chối consent, chính sách IdP từ chối hoặc quá trình auth lỗi. OP có thể redirect callback với `error=access_denied&state=...`; Spring xử lý authentication failure. Không coi đó là một code hợp lệ và không đưa error_description thô vào error page.

### 11.10. CORS error ở token endpoint

Nếu frontend JavaScript tự gọi token endpoint với client secret, đó **không phải** confidential server-side OAuth2 Login của bài. Client secret không được đặt trong browser. Với SPA public client, dùng Authorization Code + PKCE và thiết kế token/CORS/storage riêng theo chuẩn; không chép backend secret vào JS để tránh CORS.

### 11.11. Nhiều SecurityWebFilterChain

`WebFilterChainProxy` chỉ chọn chain đầu tiên khớp request. Nếu authorization start thuộc chain A, callback thuộc chain B không bật OAuth2 login, flow hỏng. Kiểm `@Order`/`securityMatcher`/`authorizeExchange` và gateway rewrite cho cả start, callback và business routes.

### 11.12. HTTP status không phải toàn bộ sự thật

Lỗi OAuth thường là **302 redirect tới trang login error** chứ không nhất thiết 400/401/403. Khi kiểm thử, ưu tiên xem:

- Có `Authentication` sau flow hay không?
- Có SecurityContext được nạp khi GET `/me`?
- Có token exchange/ID token validation thật?
- Có session cookie đúng và state correlation?
- Có dấu hiệu rò rỉ code/token trong URL/log?

## 12. Phân quyền sau OIDC login

Login OIDC xác minh danh tính; nó **không tự động cấp ROLE_ADMIN** hoặc quyền đọc tài liệu của người khác.

Một `OidcUser` có thể chứa `sub`, `preferred_username`, `email` và những claims khác tùy provider. `email` có thể thiếu hoặc chưa verified; `preferred_username` có thể thay đổi. Với nghiệp vụ quan trọng, khóa user thường nên gắn **issuer + subject** hoặc ánh xạ sang immutable internal user ID.

Spring Security OAuth2 login có thể mang các authorities như `OIDC_USER` và `SCOPE_*` theo provider/mapping. Đừng coi mọi OIDC subject là `ROLE_USER`/`ROLE_ADMIN` nếu chưa cấu hình rõ.

Nếu app cần:

- User được xem đơn hàng của mình;
- Admin tenant A không được truy cập tenant B;
- Service chỉ cho người có scope/role phù hợp;

thì sau login, phải dùng `ReactiveAuthorizationManager` và reactive method/service authorization đọc quyền/ownership từ nguồn đáng tin. Đừng lấy role từ query/header hay một field client tự sửa.

**ID Token dành cho RP**, không phải access token của mọi API; để gọi Resource Server, dùng access token có đúng audience/scope và cơ chế `OAuth2AuthorizedClient`/WebClient phù hợp.

## 13. Logging, cookies và bảo mật production

### 13.1. Không log secrets

Không đưa những thứ sau vào app logs, reverse-proxy access logs, analytics hoặc distributed traces công khai:

- `code=...`, `code_verifier`;
- `client_secret`;
- raw access/ID/refresh token;
- session cookie ID;
- raw `state`/`nonce`;
- complete callback query string;
- credentials hoặc toàn bộ SecurityContext.

Có thể ghi registrationId, issuer không nhạy cảm, event stage, error code, HTTP status, latency và correlation ID đã được xử lý/redact.

### 13.2. Yêu cầu cơ bản

1. **HTTPS** cho public Client/IdP và token endpoint; không dùng HTTP ngoài localhost lab.
2. **Exact redirect URI allowlist**, không wildcard rộng/open redirect.
3. **State correlation** fail-closed, không bỏ qua callback thiếu pending request.
4. **PKCE** cho public clients; xem yêu cầu thêm cho confidential client theo IdP/chuẩn hiện hành.
5. **Client secret** chỉ ở backend/secret store, rotate có kiểm soát.
6. **ID Token validation**: signature, issuer, audience, expiry, nonce theo OIDC.
7. **Cookie** Secure/HttpOnly/SameSite/Path/Domain phù hợp flow; timeout hợp lý.
8. **Session shared storage** nếu scale đa nút; pending request và authenticated context phải được duy trì.
9. **Proxy trust**: forwarded headers do ingress kiểm soát; không tin header do Internet client tự gửi.
10. **Role mapping** từ nguồn tin cậy và kiểm quyền ở service.
11. **CSRF** cho các browser request thay đổi trạng thái dựa vào cookie; OIDC không thay thế CSRF.
12. **Logout**: phân biệt local logout, OP SSO logout và token revocation.
13. **Multi-environment**: dev/staging/prod dùng issuer, redirect URI và secrets riêng.
14. **Regression tests**: start URL, callback, state, PKCE, cookie, ID token, HTTPS/public URL.
15. **Metrics**: provider latency, token exchange errors, callback failure, session lost state, user login failures.
16. **Không dùng secret mẫu** `admin/admin`, `alice/learn` của lab trong production.

## 14. Thực hành QA theo từng tầng

| Tầng | Công cụ | Kiểm chứng |
| --- | --- | --- |
| Client registration | Spring configuration + discovery URL | client ID, issuer, endpoints, redirect-uri |
| Authorization redirect | Browser Network / HTTP 302 | response_type=code, client_id, state, redirect_uri |
| IdP | Keycloak Admin + test user | realm/client/standard flow/valid redirects |
| Callback | Browser Network | code/state tới đúng Spring path, không bị 404 |
| Token exchange | Backend metrics/logs đã redact | exchange thành công, không expose secret |
| OIDC verification | Integration test + IdP | ID token issuer/audience/signature/nonce đúng |
| WebSession | Browser cookies/redis metrics | pending state và SecurityContext sống qua redirect |
| Controller | GET /me | principalType oidc, không lộ token |
| Security negative | State fake/code replay/issuer fake | không authenticated |
| Reverse proxy | Staging HTTPS | public redirect-uri đúng; cookie đúng |
| Scale multi-node | Start node A → callback node B | shared state hợp lệ hoặc lỗi fail-closed |

**`curl` chỉ quan sát redirect headers**, không tự thực hiện toàn bộ IdP login có cookie, CSRF, consent và callback. Browser hoặc test framework điều khiển user-agent thường phù hợp hơn cho E2E.

## 15. Câu hỏi tự kiểm tra

**1. URL nào của Spring WebFlux bắt đầu đăng nhập OAuth2?**  
`/oauth2/authorization/{registrationId}`, ví dụ `/oauth2/authorization/keycloak`.

**2. Callback mặc định trong Spring Security reactive ở đâu?**  
`/login/oauth2/code/{registrationId}`, ví dụ `/login/oauth2/code/keycloak`.

**3. URL /oauth2/authorization/keycloak có phải URL của Keycloak không?**  
Không. Nó là endpoint của **Client** dùng để tạo và redirect authorization request tới OP.

**4. IdP redirect callback kèm code và state; client có nên xử lý code bằng controller tự viết không?**  
Không cần. `OAuth2LoginAuthenticationWebFilter` xử lý callback; tự viết dễ bỏ các kiểm tra bảo mật.

**5. `client_id` có luôn bằng `registrationId`?**  
Không. Bài dùng client_id `webflux-login`, registrationId `keycloak`.

**6. Vì sao state quan trọng?**  
Nó ràng buộc callback với authorization request đã bắt đầu từ cùng session, giúp chống login CSRF/callback injection.

**7. PKCE khác state thế nào?**  
PKCE ràng buộc code exchange với code_verifier; state ràng buộc authorization response với request.

**8. Với confidential client, Spring Security lúc nào cũng tự bật PKCE không?**  
Không nên giả định. Auto-PKCE rõ cho public client phù hợp hoặc khi requireProofKey được bật; kiểm provider/request khi yêu cầu PKCE.

**9. `openid` scope có tác dụng gì?**  
Yêu cầu OIDC authentication và ID Token, cho phép Spring Security xử lý OIDC-specific login.

**10. Authorization code có thể gọi API lâu dài như access token không?**  
Không. Code ngắn hạn, dùng một lần để đổi token; access token dùng cho Resource Server đúng audience/scope.

**11. Browser có thấy token endpoint POST không?**  
Trong server-side confidential client, POST token là request từ backend, không phải browser JavaScript fetch.

**12. Vì sao callback báo authorization_request_not_found dù IdP login thành công?**  
Thường vì pending request/state trong WebSession không còn hoặc cookie/session không được tải đúng.

**13. Đổi callback path cần sửa đâu?**  
Reactive `oauth2Login().authenticationMatcher(...)`, `ClientRegistration.redirectUri` và Valid Redirect URIs của IdP.

**14. Tại sao CORS wildcard không sửa được OAuth callback?**  
Callback là browser top-level redirect; CORS kiểm soát JavaScript đọc cross-origin response, không thay callback/session.

**15. Reverse proxy HTTPS gây redirect_uri sai cần xử lý thế nào?**  
Sửa forwarded headers/trust boundary hoặc dùng redirect-uri public cố định theo environment; không mở wildcard.

**16. Hai pod cùng ứng dụng, callback từ A chuyển sang B mà state biến mất?**  
Pending authorization request ở session node A; cần Spring Session Redis reactive/shared state hoặc kiến trúc HA tương đương.

**17. `mockOidcLogin()` có chứng minh Keycloak đã phát ID Token hợp lệ không?**  
Không. Nó giả lập OIDC Authentication; cần test E2E/browser+OP để kiểm exchange và validation.

**18. Đăng nhập OIDC thành công có nghĩa user có ROLE_ADMIN không?**  
Không. Authorization/role/tenant ownership phải được ánh xạ và kiểm tra riêng.

**19. Local logout có luôn logout phiên SSO ở Keycloak không?**  
Không. OIDC provider logout và token revocation cần cơ chế riêng.

**20. Có thể dán client secret hoặc authorization code vào issue khi debug không?**  
Không. Chỉ dùng logs/traces đã redact, quyền truy cập hạn chế và dữ liệu giả nếu cần tái hiện.

**Ghi nhớ:** Authorization Code Flow trong WebFlux gồm **start URL → IdP authorize/login → callback code+state → back-channel token exchange → OIDC principal + session**. Địa chỉ callback phải khớp Client Registration, WebFlux authentication matcher và allowlist IdP. Bảo mật luồng phụ thuộc vào **state, PKCE đúng cách, issuer/ID Token validation, HTTPS, client secret server-side, cookie/WebSession ổn định** — không chỉ vào việc nhận được HTTP 302.

## Tài liệu chính thức

- [Spring Security — Reactive OAuth2 Login Core](https://docs.spring.io/spring-security/reference/reactive/oauth2/login/core.html): `ClientRegistration`, `oauth2Login` và default redirect URI.
- [Spring Security — Reactive OAuth2 Login Advanced](https://docs.spring.io/spring-security/reference/reactive/oauth2/login/advanced.html): custom `authenticationMatcher` callback, OAuth2 Login Page, OIDC user service.
- [Spring Security — Reactive OAuth2 Authorization Code](https://docs.spring.io/spring-security/reference/reactive/oauth2/client/authorization-grants.html): authorization initiation, state repository và PKCE.
- [Spring Security — OAuth2 WebFlux](https://docs.spring.io/spring-security/reference/reactive/oauth2/): OAuth2 Client vs Resource Server, OIDC endpoints và token types.
- [Spring Security — Testing Reactive OAuth2/OIDC](https://docs.spring.io/spring-security/reference/reactive/test/web/oauth2.html): `mockOidcLogin()` và mô hình test.
- [Spring Boot 3.3 — OAuth2 Clients](https://docs.spring.io/spring-boot/3.3/reference/web/spring-security.html): client/provider properties, reactive registration.
- [Spring Boot 3.3 — Behind a Proxy](https://docs.spring.io/spring-boot/3.3/how-to/webserver.html): `server.forward-headers-strategy`.
- [Keycloak — Docker Getting Started](https://www.keycloak.org/getting-started/getting-started-docker): start-dev/realm/client/user.
- [Keycloak — Server Administration](https://www.keycloak.org/docs/latest/server_admin/): OIDC clients và valid redirect URIs.
- [OAuth 2.0 Authorization Framework — RFC 6749](https://www.rfc-editor.org/rfc/rfc6749): authorization code, redirect URI, token exchange.
- [PKCE — RFC 7636](https://www.rfc-editor.org/rfc/rfc7636): code_challenge và code_verifier.
- [OAuth 2.0 Security Best Current Practice — RFC 9700](https://www.rfc-editor.org/rfc/rfc9700): bảo mật OAuth2.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): ID Token, nonce, issuer, audience và code flow.
