# 20.2. Luồng OAuth2 và OIDC Login trong WebFlux

## 1. Vì sao đăng nhập OAuth2/OIDC trong WebFlux cần được hiểu riêng?

Spring Security hỗ trợ OAuth 2.0 Login và OpenID Connect (OIDC) Login trên cả **Servlet** lẫn **Reactive WebFlux**. Hai mô hình cùng tuân theo giao thức OAuth 2.0/OIDC, nhưng khác nhau ở cách Spring xử lý HTTP request, bảo mật phiên, thực thi bất đồng bộ và tích hợp HTTP client.

Trong ứng dụng Servlet, người học thường gặp <code>HttpSecurity</code>, <code>SecurityFilterChain</code>, <code>HttpSession</code> và <code>RestClient</code>. Với **WebFlux**, các thành phần tương ứng thường là:

- <code>ServerHttpSecurity</code> và <code>SecurityWebFilterChain</code>.
- <code>ServerWebExchange</code> và <code>WebSession</code>.
- <code>ReactiveSecurityContextHolder</code>, Reactor <code>Context</code>, <code>Mono</code>/<code>Flux</code>.
- <code>ReactiveClientRegistrationRepository</code> và reactive authorized-client components.
- <code>WebClient</code> cùng <code>ServerOAuth2AuthorizedClientExchangeFilterFunction</code>.

Sự khác biệt này quan trọng khi:

1. Người dùng được chuyển tới OpenID Provider (OP) để đăng nhập.
2. OP trả authorization code qua callback của ứng dụng.
3. Spring Security kiểm tra <code>state</code>, đổi code lấy token và xác minh ID Token.
4. Kết quả xác thực được đặt vào reactive security context.
5. Ứng dụng cần tiếp tục gọi REST API bằng access token trong môi trường không được chặn event-loop.

> **Nguyên tắc của bài:** OAuth2/OIDC giao thức không thay đổi chỉ vì ứng dụng dùng WebFlux. Điểm thay đổi là cách Spring Security triển khai flow qua **WebFilter, WebSession và Reactor Context**, cũng như cách ứng dụng sử dụng token bất đồng bộ.

## 2. Trường hợp sử dụng xuyên suốt

Giả sử xây một ứng dụng quản lý báo cáo:

- Frontend sử dụng trình duyệt truy cập ứng dụng WebFlux tại <code>https://portal.example.org</code>.
- Spring Boot ứng dụng đóng vai **OAuth2/OIDC Client** có registration ID là <code>company</code>.
- OpenID Provider có issuer <code>https://idp.example.org/realms/company</code>.
- Người dùng đăng nhập bằng **Authorization Code Flow**.
- Sau đăng nhập, WebFlux có thể hiển thị thông tin <code>OidcUser</code> và gọi Reports API bằng access token đã được cấp.

Các tên miền, Client ID, đường dẫn và người dùng trong bài là **ví dụ giả lập**, không phải cấu hình của một hệ thống thật.

Một authorization request khái niệm:

~~~http
GET /authorize?response_type=code&client_id=portal-web&scope=openid%20profile&redirect_uri=https%3A%2F%2Fportal.example.org%2Flogin%2Foauth2%2Fcode%2Fcompany&state=RANDOM_STATE&nonce=RANDOM_NONCE HTTP/1.1
Host: idp.example.org
~~~

Trong request thật, Spring Security xây các tham số từ <code>ClientRegistration</code> và authorization request resolver, đồng thời thực hiện encoding đúng. Không tự lắp URL bằng nối chuỗi trong code production.

## 3. Phân biệt OAuth 2.0 Login và OpenID Connect Login

OAuth 2.0 và OIDC có quan hệ chặt chẽ nhưng không đồng nghĩa.

| Thuộc tính | OAuth 2.0 Login | OIDC Login |
|---|---|---|
| Nền tảng | OAuth 2.0 Authorization Code Flow | OAuth 2.0 Authorization Code Flow mở rộng bằng OIDC |
| Mục tiêu chính | Cho phép Client ủy quyền và, trong Spring Security OAuth2 Login, dùng thông tin user từ provider | Xác thực End-User và truyền danh tính theo chuẩn OIDC |
| Scope đặc trưng | Provider-specific như <code>read:user</code> | Phải yêu cầu <code>openid</code> để là OIDC authentication request |
| Token response | Access token, đôi khi refresh token | Access token, **ID Token**, có thể refresh token |
| Định danh chuẩn | Tùy API/provider | Cặp <code>(iss, sub)</code> trong ID Token |
| Dữ liệu user | UserInfo API/provider-specific | OIDC claims; UserInfo Endpoint nếu được sử dụng |
| Spring Security principal thường gặp | <code>OAuth2User</code> | <code>OidcUser</code> |

**Đối với Spring Security:** cùng một cấu hình <code>oauth2Login()</code> có thể phục vụ cả OAuth 2.0 Login và OIDC Login. Khi ClientRegistration sử dụng scope <code>openid</code> và provider hỗ trợ OIDC, Spring Security xử lý token response/ID Token theo OIDC.

Không coi access token là bằng chứng danh tính tương đương ID Token. Access token nhằm truy cập Resource Server và có audience, scope, thời hạn riêng; ID Token chứng minh End-User authentication cho Client theo OIDC.

### 3.1. Vai trò của các bên

| Bên | Vai trò |
|---|---|
| **Browser/User Agent** | Theo redirect tới OP và quay về callback |
| **WebFlux application** | OAuth2/OIDC Relying Party / Client; giữ session và token phù hợp |
| **OpenID Provider/Authorization Server** | Xác thực người dùng, trả authorization code và token |
| **Resource Server** | API bảo vệ bằng access token; kiểm tra issuer, audience, scope và policy |

Một ứng dụng có thể đồng thời đóng vai OIDC Client và Resource Server, nhưng các luồng đó phải được cấu hình tách bạch theo endpoint.

## 4. Luồng tổng thể: từ URL đăng nhập đến principal OIDC

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Người dùng
    participant B as Browser
    participant W as Spring Security WebFlux Client
    participant OP as OpenID Provider
    participant API as Downstream Resource Server
    U->>B: Mở trang yêu cầu đăng nhập
    B->>W: GET /reports
    W-->>B: 302 tới trang login hoặc authorization initiation
    B->>W: GET /oauth2/authorization/company
    W->>W: Tạo OAuth2AuthorizationRequest, state, nonce, PKCE khi áp dụng
    W->>W: Lưu authorization request trong WebSession/repository
    W-->>B: 302 tới Authorization Endpoint OP
    B->>OP: Authorization request
    OP->>U: Login, MFA, consent theo policy
    OP-->>B: 302 callback kèm code và state
    B->>W: GET /login/oauth2/code/company?code=...&state=...
    W->>W: Load request gốc và kiểm tra state
    W->>OP: POST Token Endpoint, đổi code lấy token
    OP-->>W: Access Token + ID Token (+ Refresh Token nếu có)
    W->>W: Xác minh ID Token, nạp OidcUser/UserInfo khi phù hợp
    W->>W: Lưu authorized client và SecurityContext
    W-->>B: Redirect tới trang sau đăng nhập
    B->>W: GET /reports
    W->>API: WebClient + Bearer access token phù hợp
    API-->>W: Kết quả được phép
    W-->>B: Trang/bản dữ liệu
~~~

Từng pha có một mục đích riêng:

1. **Khởi tạo authorization request:** xác định provider/Client, scope, redirect URI và tạo correlation data.
2. **Xác thực tại OP:** người dùng cung cấp credential với OP; ứng dụng Client không trực tiếp xử lý mật khẩu của OP.
3. **Callback:** đối chiếu authorization response với yêu cầu đã phát đi.
4. **Token exchange:** gửi code và client authentication/PKCE verifier phù hợp tới Token Endpoint.
5. **OIDC validation:** xác minh ID Token, nonce/issuer/audience và những ràng buộc liên quan.
6. **Lưu trạng thái:** giữ Authentication ở WebFlux security context/session và authorized client trong repository/service.
7. **Dùng token cho downstream API:** chỉ với Resource Server đúng audience/scope/quyền.

## 5. Cấu hình một WebFlux OIDC Client tối thiểu

### 5.1. Dependencies

Ví dụ Spring Boot 3, Spring Security 6, Java 17:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
}
~~~

Nếu dự án chỉ muốn chạy **Reactive WebFlux**, không thêm <code>spring-boot-starter-web</code> vào cùng ví dụ một cách vô ý. Khi cả Spring MVC và WebFlux cùng có mặt, Spring Boot thông thường ưu tiên ứng dụng Servlet/MVC, khiến việc mong đợi <code>SecurityWebFilterChain</code> hoạt động như cấu hình web chính trở nên sai.

Nếu hệ thống bắt buộc có cả hai stack, phải quyết định rõ application type và thiết kế bảo mật tương ứng; không sử dụng cấu hình Servlet rồi cho rằng nó tự chuyển thành reactive.

### 5.2. application.yml cho OIDC discovery

~~~yaml
server:
  port: 8080

spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company
            client-id: portal-web
            client-secret: ${COMPANY_OIDC_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
        provider:
          company:
            issuer-uri: https://idp.example.org/realms/company
~~~

Giải thích:

| Thuộc tính | Ý nghĩa |
|---|---|
| <code>registration.company</code> | Registration ID nội bộ, được dùng trong URL khởi tạo login |
| <code>provider: company</code> | Liên kết registration với metadata provider |
| <code>client-id</code> | Client ID đã đăng ký tại OP |
| <code>client-secret</code> | Secret dành cho confidential Client; không commit secret thật |
| <code>authorization-grant-type</code> | <code>authorization_code</code> cho browser login |
| <code>redirect-uri</code> | Callback mà OP được phép redirect về; phải đăng ký chính xác |
| <code>scope: openid</code> | Chuyển request thành OIDC authentication request |
| <code>issuer-uri</code> | Issuer tin cậy, dùng khám phá metadata OP và validation |

Với issuer hợp lệ có OIDC Discovery metadata, Spring Security/Boot có thể suy ra authorization endpoint, token endpoint, JWK Set URI và UserInfo endpoint (nếu được công bố). Với provider không hỗ trợ discovery, cần cấu hình các endpoint và user-info settings tường minh.

Trong production:

- Chỉ cấu hình issuer/endpoint OP từ nguồn tin cậy.
- Lưu secret ở secret manager/biến môi trường.
- Dùng HTTPS cho callback production và đăng ký redirect URI chính xác.
- Kiểm tra issuer, endpoint, Client ID, scope, authentication method phù hợp với chính sách OP.
- Không dùng cùng secret giữa các môi trường chỉ vì mục đích demo.

### 5.3. SecurityWebFilterChain

~~~java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class ReactiveSecurityConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/", "/error", "/assets/**").permitAll()
                .anyExchange().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .oauth2Client(Customizer.withDefaults())
            .build();
    }
}
~~~

**Điểm khác với Servlet:**

~~~text
Servlet:
    HttpSecurity
    SecurityFilterChain
    authorizeHttpRequests(...)

Reactive WebFlux:
    ServerHttpSecurity
    SecurityWebFilterChain
    authorizeExchange(...)
~~~

<code>oauth2Login()</code> kích hoạt luồng login. <code>oauth2Client()</code> cung cấp thêm cơ chế OAuth2 Client cho việc sử dụng authorized client khi gọi API; với ứng dụng chỉ cần login, phần thứ hai có thể không cần thiết tùy use case.

Hãy bảo đảm ứng dụng có các bean reactive registration/repository thích hợp. Khi Spring Boot auto-configuration được kích hoạt đúng bởi starter và properties, phần lớn bean liên quan có thể được tạo tự động.

## 6. Pha 1 — Khởi tạo authorization request

Khi user bấm liên kết:

~~~text
GET /oauth2/authorization/company
~~~

WebFlux OAuth2 Login nhận biết <code>company</code> là registration ID, truy xuất <code>ClientRegistration</code> rồi tạo <code>OAuth2AuthorizationRequest</code>.

Request chứa các thông tin thường gặp:

~~~text
response_type = code
client_id     = portal-web
redirect_uri  = https://portal.example.org/login/oauth2/code/company
scope         = openid profile email
state         = giá trị ngẫu nhiên dùng correlate callback
nonce         = giá trị liên kết ID Token với authorization request nếu gửi
code_challenge / code_challenge_method = PKCE khi áp dụng
~~~

<code>state</code>, <code>nonce</code> và PKCE có mục đích **khác nhau**:

| Trường | Vai trò |
|---|---|
| <code>state</code> | Liên kết callback với authorization request ban đầu, chống CSRF/login injection trong OAuth2 flow |
| <code>nonce</code> | Liên kết ID Token với OIDC authentication request, giảm rủi ro replay/token substitution |
| <code>code_verifier</code> | Bí mật tạm thời của Client để chứng minh khi đổi authorization code bằng PKCE |
| <code>code_challenge</code> | Dẫn xuất từ verifier, được đưa lên Authorization Endpoint |
| <code>redirect_uri</code> | Địa chỉ callback đã được đăng ký mà OP chuyển code về |

Không đưa <code>code_verifier</code> vào authorization URL front channel; phần front channel mang <code>code_challenge</code>, còn verifier được dùng tại Token Endpoint.

### 6.1. state được lưu ở đâu trong WebFlux?

Spring Security Reactive sử dụng abstraction <code>ServerAuthorizationRequestRepository&lt;OAuth2AuthorizationRequest&gt;</code> để giữ authorization request chờ callback. Một implementation thông dụng là <code>WebSessionOAuth2ServerAuthorizationRequestRepository</code>, lưu dữ liệu trong **WebSession**.

~~~text
Browser request /oauth2/authorization/company
  → Tạo state ngẫu nhiên
  → Lưu OAuth2AuthorizationRequest trong WebSession
  → Redirect browser sang OP

Browser trở về callback:
  → Tìm WebSession tương ứng
  → Đọc request trước đó
  → Kiểm tra state nhận được
~~~

Nếu browser mất session cookie hoặc nhiều node không chia sẻ session theo cấu hình, callback có thể thất bại vì không tìm thấy authorization request hoặc state không khớp.

Không trộn <code>WebSessionOAuth2ServerAuthorizationRequestRepository</code> với <code>HttpSessionOAuth2AuthorizationRequestRepository</code> của Servlet; chúng thuộc hai stack khác nhau.

### 6.2. URL redirect tới Authorization Endpoint

Spring Security trả HTTP 302 để browser tới OP. OP là nơi người dùng nhập mật khẩu hoặc thực hiện MFA theo chính sách. WebFlux Client **không tự gửi thông tin đăng nhập của người dùng** tới OP bằng một server-to-server request.

Với ứng dụng chạy qua reverse proxy, redirect URI phải được tính đúng scheme/host/port đã công bố. Nếu backend thấy <code>http://localhost:8080</code> nhưng public endpoint là HTTPS, cấu hình proxy và forwarded headers sai có thể tạo redirect URI mismatch.

Chỉ tin các forwarded headers từ **proxy được kiểm soát**. Không chấp nhận tùy tiện <code>X-Forwarded-Host</code> do Client bên ngoài tự gửi để xây URL redirect tin cậy.

## 7. Pha 2 — Browser đăng nhập ở OpenID Provider

Trong giai đoạn này, OP có thể:

1. Hiển thị trang đăng nhập.
2. Sử dụng SSO session đã có.
3. Yêu cầu MFA/step-up.
4. Hiển thị màn hình consent nếu cần.
5. Áp dụng chính sách tenant và ClientRegistration.

Sau khi hoàn tất, OP redirect browser trở lại Client:

~~~http
HTTP/1.1 302 Found
Location: https://portal.example.org/login/oauth2/code/company?code=AUTH_CODE_PLACEHOLDER&state=STATE_PLACEHOLDER
~~~

Đây là callback kiểu **authorization code**, chưa phải token response. Authorization code thường ngắn hạn, một lần dùng, và phải được trao đổi qua Token Endpoint.

Nếu user từ chối consent, OP có thể redirect về callback với tham số <code>error</code> và <code>state</code>, ví dụ <code>access_denied</code>. Client cần xử lý lỗi theo flow, không cố đổi token khi không có code.

### 7.1. State không phải access token

<code>state</code> là giá trị correlate request và response. Nó không xác thực danh tính End-User và không thay thế kiểm tra ID Token. Nếu callback có state không khớp, Spring Security phải từ chối xử lý như một authorization response hợp lệ.

### 7.2. Login từ nhiều tab

Hai tab cùng khởi tạo login có thể tạo hai authorization request khác nhau. Tùy repository và cách dùng WebSession, request thứ hai có thể thay thế request trước hoặc tạo tình huống callback state không còn khớp.

Nếu sản phẩm cần hỗ trợ nhiều flow đăng nhập song song, phải thiết kế repository/correlation phù hợp; không “chữa” lỗi bằng cách bỏ state validation.

## 8. Pha 3 — WebFlux xử lý callback và token exchange

Callback mặc định thường là:

~~~text
GET /login/oauth2/code/{registrationId}
~~~

Ví dụ:

~~~text
GET /login/oauth2/code/company?code=...&state=...
~~~

Spring Security Reactive có các web filters chuyên trách trong OAuth2 Login flow. Tên thường gặp trong API là <code>OAuth2AuthorizationRequestRedirectWebFilter</code> cho authorization initiation và <code>OAuth2LoginAuthenticationWebFilter</code> cho callback/authentication.

Khái niệm xử lý:

~~~mermaid
flowchart TD
    A["Callback: code + state"] --> B["Tìm authorization request gốc"]
    B --> C{"state và registration hợp lệ?"}
    C -->|Không| X["Authentication failure / không cấp phiên"]
    C -->|Có| D["Token Endpoint: code exchange + client authentication/PKCE"]
    D --> E{"Token response hợp lệ?"}
    E -->|Không| X
    E -->|Có, OIDC| F["Xác minh ID Token, nonce/issuer/audience/expiry"]
    E -->|Có, OAuth2 Login không OIDC| G["Lấy OAuth2User theo cấu hình provider"]
    F --> H["OidcUser / Authentication"]
    G --> H
    H --> I["Lưu OAuth2AuthorizedClient và SecurityContext"]
    I --> J["Chuyển tới trang sau đăng nhập"]
~~~

Token exchange được thực hiện **back channel** từ Client tới OP Token Endpoint:

~~~http
POST /oauth2/token HTTP/1.1
Host: idp.example.org
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <CLIENT_AUTH_PLACEHOLDER>

grant_type=authorization_code&code=AUTH_CODE_PLACEHOLDER&redirect_uri=https%3A%2F%2Fportal.example.org%2Flogin%2Foauth2%2Fcode%2Fcompany&code_verifier=PKCE_VERIFIER_PLACEHOLDER
~~~

Đây là ví dụ mô tả cấu trúc. Thực tế Client Authentication có thể là <code>client_secret_basic</code>, <code>client_secret_post</code>, private key JWT hoặc phương thức khác theo registration; PKCE verifier chỉ có nếu flow đã sử dụng PKCE.

Không ghi authorization code, code verifier, client secret hay raw token response vào log.

## 9. Pha 4 — ID Token và OIDC validation

Với scope <code>openid</code>, token response OIDC Authorization Code Flow phải chứa ID Token theo giao thức:

~~~json
{
  "access_token": "ACCESS_TOKEN_PLACEHOLDER",
  "token_type": "Bearer",
  "expires_in": 3600,
  "id_token": "HEADER.PAYLOAD.SIGNATURE",
  "refresh_token": "REFRESH_TOKEN_PLACEHOLDER"
}
~~~

Refresh token trong JSON trên là **tùy chọn**, không phải provider nào cũng trả. Payload ID Token được ký ví dụ:

~~~json
{
  "iss": "https://idp.example.org/realms/company",
  "sub": "user-2482",
  "aud": "portal-web",
  "iat": 1794810000,
  "exp": 1794813600,
  "nonce": "NONCE_PLACEHOLDER",
  "name": "Alex Example",
  "email": "alex@example.org"
}
~~~

Các thời điểm, dữ liệu danh tính, token và tên miền đều minh họa. Chỉ có thể tin những claim này **sau khi đã xác minh ID Token bằng cấu hình OP tin cậy**.

### 9.1. Những kiểm tra quan trọng

Spring Security OIDC Client thực hiện validation theo cấu hình, bao gồm các điều kiện liên quan:

| Điều kiện | Vì sao cần? |
|---|---|
| Chữ ký/thuật toán/khóa tin cậy | Không tin token bị giả mạo/sửa payload |
| <code>iss</code> | Token phải đến từ issuer đã cấu hình |
| <code>aud</code> | Token phải được phát hành cho Client phù hợp |
| <code>azp</code> khi áp dụng | Phân biệt authorized party theo điều kiện OIDC |
| <code>exp</code> / thời gian | Không dùng ID Token đã hết hạn |
| <code>nonce</code> khi request có gửi | Gắn ID Token với authorization request hiện tại |
| Các ràng buộc OIDC khác | Bảo đảm token response và authentication flow hợp lệ |

Ứng dụng không nên lấy phần giữa của JWT, Base64URL decode rồi coi claims là đã xác minh. Đọc <code>OidcUser</code> mà Spring Security tạo sau authentication mới là đường đi phù hợp.

### 9.2. UserInfo có bắt buộc không?

Không. OIDC Client có thể dùng ID Token để xác nhận danh tính, và **UserInfo Endpoint** được gọi khi provider, scopes và cấu hình cho phép/cần thiết. UserInfo thường cung cấp những claim hồ sơ như tên, email, ảnh hoặc locale.

Điều quan trọng là claim <code>sub</code> trong UserInfo response phải **khớp** subject của ID Token theo OIDC. Không ghép hồ sơ UserInfo thuộc một subject khác vào principal hiện tại.

### 9.3. OIDC identity khác quyền truy cập API

<code>sub</code>, <code>iss</code>, <code>email</code> xác định danh tính/hồ sơ; chúng **không tự cấp role quản trị**. Quyền tại Resource Server còn phụ thuộc scope/entitlement, ownership, tenant và chính sách nghiệp vụ.

Một ID Token hợp lệ không khiến access token tự có audience cho mọi API.

## 10. Pha 5 — Reactive Authentication và SecurityContext

Sau login thành công, Spring Security tạo một <code>Authentication</code> đại diện cho người dùng. Với OAuth2/OIDC Login, kiểu thường gặp là <code>OAuth2AuthenticationToken</code>; principal thường là:

- <code>OAuth2User</code> nếu là OAuth2 Login không OIDC.
- <code>OidcUser</code> nếu là OIDC Login.

### 10.1. Security context trong Reactor Context

Trong Servlet, lập trình viên quen với <code>SecurityContextHolder</code> dựa trên thread-local. Trong reactive pipeline, xử lý có thể chuyển thread; do đó Spring Security sử dụng <code>ReactiveSecurityContextHolder</code> và **Reactor Context** để lan truyền security context.

~~~text
Servlet:
    thread → SecurityContextHolder

Reactive:
    Mono/Flux subscription → Reactor Context → SecurityContext
~~~

Ví dụ service lấy tên principal:

~~~java
package example.security;

import reactor.core.publisher.Mono;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.stereotype.Service;

@Service
public class CurrentUserService {

    public Mono<String> currentPrincipalName() {
        return ReactiveSecurityContextHolder.getContext()
            .map(context -> context.getAuthentication())
            .filter(authentication ->
                authentication != null && authentication.isAuthenticated())
            .map(Authentication::getName)
            .switchIfEmpty(
                Mono.error(new IllegalStateException(
                    "No authenticated principal")));
    }
}
~~~

Không gọi <code>.block()</code> để lấy kết quả đồng bộ trong WebFlux request handler. Việc block event-loop có thể làm giảm throughput hoặc dẫn tới deadlock/bottleneck.

### 10.2. WebSession và lưu security context

Với browser login thông thường, security context cần tồn tại qua nhiều HTTP requests. Trong WebFlux, cơ chế session là <code>WebSession</code> với abstraction <code>ServerSecurityContextRepository</code> (thường gặp <code>WebSessionServerSecurityContextRepository</code>).

~~~text
Request A: callback OIDC thành công
    → Authentication được lưu
    → Browser nhận/giữ session cookie

Request B: GET /me
    → WebSession được tìm lại
    → SecurityContext/Authentication được phục hồi
~~~

**Authentication/SecurityContext khác OAuth2AuthorizedClient storage:**

- SecurityContext giữ người dùng đã được xác thực và authorities của họ.
- Authorized client giữ access/refresh token gắn với registration/principal.
- Authorization request repository giữ <code>state</code>/PKCE trong giai đoạn **chưa callback**.

Ba loại dữ liệu có vòng đời khác nhau. Không coi session cookie là access token; không đưa access/refresh token vào cookie tùy biến.

### 10.3. Một cấu hình stateless có thể làm login lỗi

Nếu cấu hình <code>NoOpServerSecurityContextRepository</code> hoặc xóa WebSession một cách không phù hợp, OAuth2 Login có thể không giữ được phiên đăng nhập sau callback.

API Bearer stateless và browser OIDC Login có yêu cầu khác nhau. Khi ứng dụng chứa cả hai, nên thiết kế security chain theo route và bảo đảm login/callback thuộc chain hỗ trợ WebSession đúng cách.

## 11. Truy cập OidcUser trong WebFlux Controller

Sau OIDC Login, controller có thể nhận principal:

~~~java
package example.web;

import java.util.Map;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class MeController {

    @GetMapping("/me")
    public Mono<Map<String, Object>> me(
            @AuthenticationPrincipal OidcUser user) {

        return Mono.just(Map.of(
            "subject", user.getSubject(),
            "issuer", user.getIdToken().getIssuer().toString(),
            "hasUserInfo", user.getUserInfo() != null
        ));
    }
}
~~~

Trong ứng dụng thật, chỉ trả những thông tin hồ sơ mà frontend có quyền xem. Không trả nguyên ID Token, access token, refresh token hoặc toàn bộ claims nếu không có nhu cầu.

Ví dụ trên giả định endpoint chỉ dành cho OIDC Login. Nếu hệ thống có cả OAuth2 Login không OIDC, <code>@AuthenticationPrincipal OidcUser</code> có thể không phù hợp cho mọi principal; cần phân biệt kiểu authentication hoặc tách route.

### 11.1. Đọc ID Token và UserInfo đúng nguồn

~~~java
OidcIdToken idToken = user.getIdToken();
OidcUserInfo userInfo = user.getUserInfo(); // có thể null

String subject = user.getSubject();
String issuer = idToken.getIssuer().toString();
~~~

Các import:

~~~java
import org.springframework.security.oauth2.core.oidc.OidcIdToken;
import org.springframework.security.oauth2.core.oidc.OidcUserInfo;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
~~~

Nếu UserInfo không được gọi hoặc không có, <code>userInfo</code> có thể null. Không bắt buộc có email, full name hay avatar. <code>(iss, sub)</code> mới là định danh OIDC quan trọng, trong khi email có thể thay đổi.

### 11.2. Không suy diễn quyền từ tên hoặc email

Ví dụ nguy hiểm:

~~~text
if user.getEmail().endsWith("@company.example"):
    grant ADMIN
~~~

Địa chỉ email không phải một hệ thống cấp quyền nghiệp vụ. Ngay cả khi OP cung cấp email_verified, cũng cần quy tắc role/permission riêng từ nguồn được ủy quyền và áp dụng ở backend.

## 12. Reactive ClientRegistration và authorized client

Trong WebFlux, Spring Security sử dụng các abstraction reactive:

| Mục đích | Reactive component |
|---|---|
| Tra cứu registration | <code>ReactiveClientRegistrationRepository</code> |
| Lưu authorized client theo principal | <code>ReactiveOAuth2AuthorizedClientService</code> |
| Lưu authorized client theo web exchange | <code>ServerOAuth2AuthorizedClientRepository</code> |
| Điều phối authorization/refresh | <code>ReactiveOAuth2AuthorizedClientManager</code> |
| Gắn access token vào WebClient | <code>ServerOAuth2AuthorizedClientExchangeFilterFunction</code> |

<code>OAuth2AuthorizedClient</code> vẫn là mô hình liên kết ClientRegistration + principal + access token + refresh token tùy chọn. Sự khác biệt là cách **tra cứu, lưu và xử lý asynchronous flows**.

Ví dụ mô hình:

~~~text
ClientRegistration(company)
    └── principalName = user-2482
        ├── accessToken = token dùng Reports API khi đúng audience/scope
        └── refreshToken = tùy chọn
~~~

Không trộn <code>OAuth2AuthorizedClientService</code> của Servlet/service-style đồng bộ với <code>ReactiveOAuth2AuthorizedClientService</code> mà không có thiết kế chủ động. Đừng gọi JDBC blocking ngay trên event-loop chỉ để lấy token.

### 12.1. Token và login session có thể hết hạn khác nhau

Một người dùng có thể vẫn đang đăng nhập ở WebSession nhưng access token đã hết hạn. Khi gọi API, Client có thể cần refresh token hoặc authorization flow mới tùy provider/policy. Ngược lại, một access token còn hạn không chứng minh browser session hiện tại vẫn tồn tại.

Refresh token không bắt buộc có trong mọi OIDC token response; không coi việc không có refresh token là lỗi mặc định.

### 12.2. Client credentials khác OIDC Login

Nếu một WebFlux application có background worker gọi API bằng quyền service, có thể dùng <code>client_credentials</code> registration và reactive manager phù hợp. Token đó **không** đại diện cho End-User và không tạo <code>OidcUser</code>.

Với một ứng dụng vừa có browser login vừa có service jobs, nên tách registration, scope, audience và principal management cho hai use case để không nhầm token user và token service.

## 13. WebClient dùng authorized client sau OIDC Login

<code>WebClient</code> là HTTP client reactive của Spring. Với WebFlux, đây thường là lựa chọn tự nhiên để gọi API mà không block event-loop.

### 13.1. Tạo WebClient với OAuth2 Client filter

~~~java
package example.web;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.registration.ReactiveClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction;
import org.springframework.security.oauth2.client.web.server.ServerOAuth2AuthorizedClientRepository;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
public class DownstreamWebClientConfig {

    @Bean("oauth2WebClient")
    WebClient oauth2WebClient(
        ReactiveClientRegistrationRepository registrations,
        ServerOAuth2AuthorizedClientRepository authorizedClients) {

        var oauth2 = new ServerOAuth2AuthorizedClientExchangeFilterFunction(
            registrations, authorizedClients);

        return WebClient.builder()
            .filter(oauth2)
            .build();
    }
}
~~~

Đây là WebClient được gắn filter OAuth2, không có nghĩa **mọi request WebClient tự mang token**. Ở ví dụ tiếp theo, request chọn authorized client tường minh để tránh gửi token nhầm sang endpoint ngoài dự kiến.

### 13.2. Dùng @RegisteredOAuth2AuthorizedClient trong Controller

~~~java
package example.web;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.annotation.RegisteredOAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

@RestController
public class ReportsController {

    private final WebClient webClient;

    public ReportsController(
            @Qualifier("oauth2WebClient") WebClient webClient) {
        this.webClient = webClient;
    }

    @GetMapping("/reports/remote")
    public Mono<String> reports(
            @RegisteredOAuth2AuthorizedClient("company")
            OAuth2AuthorizedClient authorizedClient) {

        return webClient.get()
            .uri("https://api.example.org/v1/reports")
            .attributes(
                ServerOAuth2AuthorizedClientExchangeFilterFunction
                    .oauth2AuthorizedClient(authorizedClient))
            .retrieve()
            .bodyToMono(String.class);
    }
}
~~~

Điểm cần lưu ý:

1. Annotation resolve authorized client theo registration ID và principal/request hiện tại.
2. <code>oauth2AuthorizedClient(authorizedClient)</code> gắn **đúng authorized client** vào request WebClient.
3. Filter có thể gắn Bearer access token cho HTTP call theo cấu hình.
4. <code>bodyToMono(String.class)</code> trả một publisher; WebFlux quản lý subscription khi tạo HTTP response.
5. Không gọi <code>.block()</code>, <code>.subscribe()</code> thủ công trong controller để lấy kết quả.

Mẫu chỉ hợp lệ khi Reports API thực sự chấp nhận token do registration <code>company</code> cấp. Nếu access token chỉ dành cho UserInfo hoặc một Resource Server khác, Reports API phải từ chối vì audience/scope không phù hợp.

Ví dụ trả raw String để tập trung vào flow. Ở production cần DTO và xử lý timeout, response size, lỗi HTTP, telemetry, authorization nghiệp vụ, và không log dữ liệu nhạy cảm.

### 13.3. Vì sao không bật defaultOAuth2AuthorizedClient bừa bãi?

Một số cấu hình exchange filter cho phép chọn authorized client từ authentication hiện tại hoặc đặt registration mặc định. Dùng default token cho **mọi request** tới mọi host có thể vô tình gửi credential tới URL không tin cậy nếu WebClient được dùng lại không kiểm soát.

An toàn hơn:

- Chỉ tạo WebClient dành riêng cho downstream service tin cậy.
- Chọn <code>authorizedClient</code> hoặc registration một cách tường minh tại nơi gọi.
- Không cho browser truyền URL đích hoặc registration ID tùy ý để backend gắn token rồi gọi.
- Nếu có nhiều issuer/audience, tách WebClient/registration theo resource policy.

### 13.4. Những HTTP lỗi thường gặp

| Response từ Resource Server | Ý nghĩa điển hình | Hướng xử lý |
|---|---|---|
| 200 | Request thành công | Xử lý dữ liệu trả về theo schema |
| 401 <code>invalid_token</code> | Token không được chấp nhận | Kiểm tra expiry, issuer, audience, khả năng refresh |
| 403 <code>insufficient_scope</code> | Token thiếu scope | Kiểm tra quyền cấp, consent và policy; không refresh mù |
| 403 khác | Role/tenant/object authorization hoặc gateway | Xác định nguồn phản hồi |
| 429 | Rate limit | Backoff có giới hạn |
| 5xx | Lỗi downstream/gateway | Retry nếu request an toàn, circuit breaker |

Không tự động retry những POST/PUT có side effect khi không có cơ chế idempotency. Nếu dùng failure handler của OAuth2 WebClient filter, kiểm tra behavior theo đúng Spring Security version đang chạy; đừng xóa authorized client do mọi response 403.

## 14. Reactive code không có nghĩa mọi thư viện đều non-blocking

Một lỗi phổ biến là dùng WebFlux controller nhưng gọi một SDK/JDBC client blocking ngay trong <code>map</code> hoặc <code>flatMap</code>:

~~~java
// Không nên chặn event-loop:
return Mono.just(userId)
    .map(id -> blockingJdbcRepository.findById(id));
~~~

Nếu thư viện blocking, nó có thể chiếm event-loop thread, làm giảm khả năng xử lý các request khác. Ưu tiên:

- Reactive database driver/repository như R2DBC khi phù hợp.
- WebClient cho HTTP I/O reactive.
- Reactive session/token store hoặc adapter có thread isolation.
- Với thư viện blocking bắt buộc, cô lập trên scheduler phù hợp và đo tải.

Ví dụ bridge với thư viện blocking (chỉ khi không thể thay thế):

~~~java
return Mono.fromCallable(() -> blockingService.loadProfile(userId))
    .subscribeOn(reactor.core.scheduler.Schedulers.boundedElastic());
~~~

Đây là **giải pháp cô lập blocking work**, không biến thư viện đó thành non-blocking và không thay thế việc giới hạn connection/thread pool. Một profile lookup chậm trong callback OIDC cũng có thể gây login timeout; cần đặt timeout và chính sách lỗi.

### 14.1. Không lấy SecurityContext bằng thread-local tùy tiện

Trong reactive code:

~~~java
ReactiveSecurityContextHolder.getContext()
~~~

phù hợp hơn việc giả định <code>SecurityContextHolder.getContext()</code> trên event-loop thread chứa user tương ứng. Reactor Context gắn với reactive subscription, không phải một global thread-local cho mọi request.

### 14.2. Không gọi subscribe() thủ công trong handler

Sai về mặt kiểm soát luồng:

~~~java
webClient.get()
    .uri("https://api.example.org/data")
    .retrieve()
    .bodyToMono(String.class)
    .subscribe(value -> System.out.println(value));

return Mono.just("done");
~~~

Handler có thể trả response trước khi HTTP call hoàn tất, tách mất error propagation, transaction/cancellation và security context. Thay vào đó, **trả về publisher** hoặc compose bằng <code>flatMap</code>:

~~~java
return webClient.get()
    .uri("https://api.example.org/data")
    .retrieve()
    .bodyToMono(String.class)
    .map(value -> "Received " + value.length() + " characters");
~~~

Không log nội dung data nếu có PII. Ví dụ chỉ trả số ký tự minh họa composition.

## 15. SecurityWebFilterChain: thứ tự và callback

Một ứng dụng WebFlux có thể có nhiều <code>SecurityWebFilterChain</code>, ví dụ:

- Chain API phục vụ Bearer JWT.
- Chain web phục vụ browser OIDC Login.

Trong reactive stack, Spring Security chọn **chain phù hợp đầu tiên** theo thứ tự; các exchange matchers quyết định route thuộc chain nào.

Nếu chain API được đặt quá rộng và match luôn:

~~~text
/oauth2/authorization/company
/login/oauth2/code/company
~~~

thì các filter của <code>oauth2Login()</code> có thể không nhận được authorization initiation/callback, dẫn tới 401/404/login loop.

### 15.1. Ví dụ phân tách API và web

~~~java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.util.matcher.PathPatternParserServerWebExchangeMatcher;

@Configuration
@EnableWebFluxSecurity
public class MultipleReactiveChainsConfig {

    @Bean
    @Order(1)
    SecurityWebFilterChain apiChain(ServerHttpSecurity http) {
        return http
            .securityMatcher(
                new PathPatternParserServerWebExchangeMatcher("/api/**"))
            .authorizeExchange(exchanges -> exchanges
                .anyExchange().authenticated())
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .csrf(ServerHttpSecurity.CsrfSpec::disable)
            .build();
    }

    @Bean
    @Order(2)
    SecurityWebFilterChain webChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/", "/error").permitAll()
                .anyExchange().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .oauth2Client(Customizer.withDefaults())
            .build();
    }
}
~~~

**Đây là cấu hình thay thế mục 5.3**, không khai báo cả hai class trong cùng project rồi tạo ba chain chồng chéo mà không thiết kế thứ tự.

API chain có Resource Server JWT cần dependency và issuer/audience validation đúng:

~~~groovy
implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
~~~

Ví dụ chỉ tắt CSRF cho **API chain stateless dùng Bearer token**. Không tắt CSRF toàn bộ web chain chỉ vì API không cần session; browser session-based routes vẫn có rủi ro CSRF.

### 15.2. Matcher chọn chain khác rule phân quyền

<code>securityMatcher(...)</code> quyết định **chain nào xử lý** request.

<code>authorizeExchange(...).pathMatchers(...)</code> quyết định **quyền truy cập** trong chain đã chọn.

Một rule <code>permitAll()</code> không khiến callback được xử lý bằng login filter nếu request đã rơi vào chain khác không cấu hình <code>oauth2Login()</code>.

## 16. CSRF, session cookie và bảo mật callback

OAuth2 Login có state/correlation; browser session còn cần các bảo vệ web thông thường.

### 16.1. state và CSRF có liên quan nhưng không thay thế nhau

- <code>state</code> trong OAuth2 Authorization Code Flow giúp chống CSRF/login injection ở **authorization callback**.
- CSRF token của Spring Security bảo vệ những **request thay đổi trạng thái** do browser gửi bằng cookie/session authentication.

Không được suy ra “đã có state nên có thể tắt CSRF cho toàn bộ ứng dụng”.

### 16.2. Cookie và SameSite

Callback thường là top-level navigation từ OP về Client. Nếu cookie/session bị chặn do Domain, Path, SameSite, Secure flag hoặc chính sách trình duyệt, Spring Security không tìm được authorization request ban đầu.

Biểu hiện:

~~~text
Authorization request tạo thành công → redirect OP
OP callback về đúng URL → state not found / mismatch
~~~

Kiểm tra cấu hình session cookie, HTTPS, reverse proxy, nhiều tab và session store. Không giải quyết bằng cách tắt state validation.

### 16.3. HTTPS và redirect URI

Sử dụng HTTPS trong production và đăng ký redirect URI chính xác trên OP. Không cho request tùy ý quyết định redirect URI hoặc host callback bằng header chưa tin cậy; đó có thể dẫn đến open redirect, authorization code leakage và login flow bị chiếm.

### 16.4. Session fixation và logout

Sau login, security context/session cần được quản lý theo các biện pháp session security thích hợp. Logout khỏi WebFlux application, logout tại OP, xóa authorized client và revoke refresh token là các hành động **khác nhau**.

Không giả định <code>logout()</code> mặc định luôn thu hồi access/refresh token ở Authorization Server. Với OIDC RP-Initiated Logout, cần cấu hình và kiểm tra endpoint provider tương ứng nếu có nhu cầu SSO logout.

## 17. WebFlux nhiều instance: session và authorized client storage

Khi triển khai nhiều replica:

~~~text
Browser
  └── Load Balancer
       ├── Instance A: Spring WebFlux
       └── Instance B: Spring WebFlux
~~~

Có hai vấn đề độc lập:

1. **Login callback correlation:** Request khởi tạo login ở A, callback quay về B. Nếu WebSession chưa chia sẻ và không có session affinity, B có thể không tìm được authorization request chứa state.
2. **Authorized client token storage:** User sau login gọi API ở B, nhưng token chỉ lưu in-memory tại A, dẫn đến lookup thất bại hoặc không có trạng thái refresh hiện hành.

Spring Session với Redis hoặc một session store chia sẻ có thể giúp quản lý WebSession qua nhiều node theo cấu hình. Tuy nhiên, **chia sẻ WebSession không mặc nhiên đồng nghĩa mọi ReactiveOAuth2AuthorizedClientService cũng dùng cùng store**, và dùng shared authorized-client service không tự giải quyết state/callback session.

### 17.1. Những điều cần thống nhất

| Vấn đề | Cần xem |
|---|---|
| Cookie/session | Cấu hình cookie, session ID, shared session store hoặc affinity |
| State/correlation | Authorization request repository dùng đúng WebSession |
| Principal identity | Principal name không va chạm giữa tenant/issuer |
| Authorized client | Storage phù hợp nhu cầu chia sẻ và refresh |
| Refresh token rotation | Tránh hai instance đồng thời dùng cùng refresh token |
| Logout/revocation | Chính sách thu hồi phiên/token trên mọi node |
| Định tuyến | Proxy forwarding, HTTPS, redirect URI nhất quán |

### 17.2. Refresh race trong nhiều instance

Nếu A và B cùng đọc một refresh token cũ <code>R0</code>:

~~~text
A: refresh R0 → nhận A1/R1
B: refresh R0 → invalid_grant / reuse detection
~~~

Với OP bật refresh token rotation, request trùng có thể khiến refresh token mới bị ảnh hưởng. Shared storage không tự ngăn race.

Ứng dụng có thể cần **single-flight refresh theo (registrationId, principal)**, đọc lại trạng thái sau lock, cập nhật access/refresh token atomic và xử lý conditional delete/versioning để không xóa token mới do node khác vừa lưu.

Đây là bài toán concurrency của OAuth2 token lifecycle, không phải vấn đề chỉ riêng Servlet hay Reactive.

## 18. Tùy biến OIDC UserService trong reactive flow

Không phải ứng dụng nào cũng chỉ cần claim từ ID Token/UserInfo. Nhiều hệ thống cần ánh xạ người dùng vào hồ sơ nội bộ hoặc xác định role từ một service khác.

Trên WebFlux, hãy dùng **reactive user service** thay vì gọi blocking REST/JDBC trực tiếp trong authentication pipeline.

### 18.1. Kiến trúc bổ sung profile

~~~text
OIDC ID Token đã xác minh
    ↓
Lấy (issuer, subject)
    ↓
Reactive profile lookup (WebClient/R2DBC)
    ↓
Kiểm tra account active, tenant, role
    ↓
Tạo principal/authorities theo policy
    ↓
Authentication thành công hoặc từ chối
~~~

Không dùng email làm khóa liên kết user nội bộ chỉ vì nó dễ đọc. Với OIDC, cặp <code>(iss, sub)</code> là cơ sở định danh theo issuer.

### 18.2. Reactive user service khác Servlet user service

Trong Servlet, người học thường gặp <code>OidcUserService</code>. Trong reactive stack, có các loại reactive service, ví dụ <code>OidcReactiveOAuth2UserService</code> và interface <code>ReactiveOAuth2UserService&lt;OidcUserRequest, OidcUser&gt;</code> theo API/version Spring Security.

Ý tưởng tùy biến an toàn:

1. Delegate cho OIDC user service mặc định để giữ việc xử lý claims/UserInfo phù hợp.
2. Lấy subject/issuer từ principal đã xác minh.
3. Sử dụng WebClient/reactive repository để tải profile.
4. Ánh xạ role theo **allowlist** và policy ứng dụng.
5. Kết hợp bằng <code>Mono.flatMap</code> thay vì <code>block()</code>.
6. Nếu user bị khóa hoặc profile service không khả dụng, xử lý theo policy fail-closed hoặc chế độ hạn chế đã thiết kế; không tự cấp role mặc định đặc quyền.

Điểm tích hợp cụ thể và method name của custom DSL cần theo version Spring Security đã chọn. Không nên bê nguyên class <code>OAuth2UserService</code> đồng bộ từ Servlet sang WebFlux rồi dùng blocking call trong event-loop.

### 18.3. Role không phải OIDC authentication

OIDC chứng minh user đã được OP xác thực, còn role nội bộ cho phép dùng các chức năng nghiệp vụ. Một user có ID Token hợp lệ vẫn có thể không được phép truy cập dữ liệu, hoặc internal account đã bị khóa.

Với quyền nhạy cảm, không tin role snapshot trong session vô thời hạn; cần chính sách cập nhật/thu hồi quyền phù hợp.

## 19. Testing: mô phỏng principal và kiểm tra flow

Spring Security Test cho WebFlux tích hợp với <code>WebTestClient</code>. Có thể kiểm tra security rule/controller bằng cách mô phỏng OIDC authentication mà không chạy toàn bộ flow qua OP thật.

### 19.1. Dependency test

~~~groovy
testImplementation 'org.springframework.boot:spring-boot-starter-test'
testImplementation 'org.springframework.security:spring-security-test'
~~~

### 19.2. Kiểm tra endpoint yêu cầu đăng nhập

Một test minh họa:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockOidcLogin;

@SpringBootTest
@AutoConfigureWebTestClient
class MeControllerSecurityTest {

    @Autowired
    WebTestClient webTestClient;

    @Test
    void authenticatedOidcUserCanReadMe() {
        webTestClient
            .mutateWith(mockOidcLogin())
            .get()
            .uri("/me")
            .exchange()
            .expectStatus().isOk();
    }
}
~~~

Đây là **test của behavior sau authentication**, không phải test end-to-end thực hiện redirect browser, token exchange, chữ ký ID Token hay UserInfo thật. Mock authentication không thể thay thế việc xác minh cấu hình OP trong integration test.

### 19.3. Kiểm tra các trường hợp quan trọng

| Trường hợp | Kỳ vọng |
|---|---|
| Browser chưa login gọi route được bảo vệ | Có phản hồi yêu cầu authentication/redirect theo configuration |
| OIDC principal hợp lệ gọi <code>/me</code> | 2xx |
| Authorized client không có scope gọi Reports API | API từ chối 403 theo policy |
| Callback state sai | Không cấp Authentication/session |
| Token Endpoint từ chối code | Login thất bại; không lưu authorized client thành công |
| ID Token sai issuer/audience/expiry | OIDC validation từ chối |
| Session cookie bị mất trước callback | Lỗi correlation; không tắt kiểm tra state |
| API stateless route có Bearer token sai | 401 theo Resource Server configuration |
| WebSession trên hai replica | Callback vẫn tìm được request nếu session store/affinity hoạt động đúng |

Không cần tự dựng một Authorization Server giả trong mỗi unit test; các integration tests có thể dùng OP test hoặc stub endpoint được kiểm soát khi cần kiểm tra token exchange.

## 20. Những lỗi thường gặp khi đưa OAuth2 Login sang WebFlux

| Triệu chứng | Nguyên nhân có thể | Cách điều tra |
|---|---|---|
| <code>SecurityWebFilterChain</code> không có tác dụng | Dự án chạy MVC/Servlet do starter web có mặt | Xác định application type, dependencies, security stack |
| <code>/oauth2/authorization/company</code> trả 404 | Registration thiếu, filter/chain không match | Kiểm tra reactive ClientRegistrationRepository và chain |
| Redirect URI sai host/scheme | Proxy/forwarded headers cấu hình sai | Kiểm tra public URL, HTTPS và trusted proxy |
| OP báo <code>redirect_uri_mismatch</code> | Callback chưa đăng ký chính xác | Đối chiếu redirect URI giữa Client và OP |
| Callback <code>invalid_state</code> | Mất WebSession, cookie, login nhiều tab hoặc repository sai | Kiểm tra state repository/session |
| Callback liên tục quay lại login | SecurityContext không lưu, cookie bị chặn, chain sai | Kiểm tra WebSession, ServerSecurityContextRepository |
| ID Token bị từ chối | Sai issuer/audience/nonce, key hoặc clock | Kiểm tra OP metadata và cấu hình OIDC |
| <code>OidcUser</code> null/sai kiểu | Registration không có scope openid hoặc đang dùng OAuth2 Login thường | Phân biệt OAuth2User và OidcUser |
| UserInfo không có email | Provider không công bố claim/scope hoặc chưa gọi UserInfo | Không coi email là khóa bắt buộc |
| <code>ReactiveSecurityContextHolder</code> rỗng | Pipeline được tạo/subscribed ngoài request context hoặc context bị mất | Kiểm tra Reactor Context propagation |
| WebFlux request bị chậm/hung | Gọi <code>block()</code> hoặc thư viện blocking trong event-loop | Dùng WebClient/reactive store hoặc isolate blocking |
| Downstream API trả 401 | Access token sai audience/issuer, expired hoặc không có Bearer | Kiểm tra authorized client và Resource Server |
| Downstream API trả 403 | Thiếu scope/role/tenant/ownership | Không refresh mù; kiểm tra authorization |
| Callback rơi vào API chain | <code>securityMatcher</code> quá rộng hoặc @Order sai | Giới hạn API matcher, giữ callback trong web chain |
| Login hoạt động ở node A, lỗi ở node B | WebSession hoặc token storage không được chia sẻ | Đánh giá session store, routing, authorized client service |
| Spring Security báo bean ambiguity | Có nhiều reactive manager/repository cùng kiểu | Đặt tên/qualifier và chọn đúng bean |

### 20.1. Trình tự chẩn đoán có hệ thống

~~~text
Ứng dụng đang chạy Reactive WebFlux thật?
    |
    v
Reactive ClientRegistration "company" có tồn tại?
    |
    v
GET /oauth2/authorization/company có qua login WebFilter?
    |
    v
Authorization request/state được lưu vào WebSession?
    |
    v
OP có nhận redirect URI, client ID, scopes đúng?
    |
    v
Callback có quay về đúng chain và có session cookie?
    |
    v
state khớp và token exchange thành công?
    |
    v
ID Token issuer/audience/signature/expiry/nonce hợp lệ?
    |
    v
OidcUser/Authentication có được lưu và đọc lại?
    |
    v
Authorized client có access token đúng audience/scope?
    |
    v
WebClient có truyền token tới API được phép?
~~~

Khi debug, chỉ ghi metadata an toàn như registration ID, loại lỗi, route template, correlation ID, trạng thái session và HTTP status. **Không log authorization code, state/nonce thật, PKCE verifier, client secret, access token, refresh token hoặc raw ID Token.**

## 21. Các bài tập thực hành

### Bài 1 — Chọn đúng security stack

Một dự án thêm <code>spring-boot-starter-webflux</code> nhưng vẫn giữ <code>spring-boot-starter-web</code> và cấu hình <code>SecurityWebFilterChain</code>. Ứng dụng thực tế khởi động theo MVC.

**Câu hỏi:** Vì sao cấu hình reactive có thể không tác dụng như mong đợi?

**Đáp án:** Khi cả MVC và WebFlux cùng có mặt, Boot thường chọn Servlet/MVC mặc định. Cần xác định web application type và dùng đúng <code>HttpSecurity</code>/<code>SecurityFilterChain</code> cho Servlet hoặc thiết kế reactive thực sự với <code>ServerHttpSecurity</code>/<code>SecurityWebFilterChain</code>.

### Bài 2 — Authorization Code Flow

Điền các bước vào đúng thứ tự:

~~~text
Tạo authorization request + state
→ Browser redirect tới OP
→ OP xác thực và trả code/state
→ Client kiểm tra state
→ Client đổi code lấy token
→ Xác minh ID Token
→ Tạo OidcUser/Authentication
→ Lưu SecurityContext/authorized client
~~~

**Câu hỏi:** Browser có trực tiếp nhận refresh token từ Token Endpoint không?

**Đáp án:** Trong mô hình confidential server-side OIDC Client của bài, token exchange diễn ra giữa backend và OP; browser chỉ nhận redirect/cookie, không cần nhận raw refresh token.

### Bài 3 — state, nonce và PKCE

**Câu hỏi:** Có thể thay cả <code>state</code>, <code>nonce</code> và PKCE bằng một biến <code>requestId</code> tùy ý không?

**Đáp án:** Không. Mỗi cơ chế có vai trò riêng: state correlate callback, nonce liên kết ID Token với OIDC request, PKCE ràng buộc authorization code với Client đã khởi tạo request. Cần dùng đúng giao thức và framework behavior.

### Bài 4 — SecurityContext trong WebFlux

Một service reactive dùng <code>SecurityContextHolder.getContext()</code> rồi cho rằng nó luôn có người dùng hiện tại.

**Câu hỏi:** Cách đọc phù hợp hơn?

**Đáp án:** Sử dụng <code>ReactiveSecurityContextHolder.getContext()</code> trong pipeline, hoặc injection authentication/principal theo cơ chế WebFlux. Tránh phụ thuộc ThreadLocal trong reactive execution.

### Bài 5 — WebClient và audience

OIDC login thành công, authorized client có access token dùng UserInfo API. Backend gửi token đó sang Billing API và nhận 401.

**Câu hỏi:** ID Token hợp lệ có chứng minh Billing API phải chấp nhận access token không?

**Đáp án:** Không. ID Token có audience Client; access token có audience/scope riêng. Cần cấp token đúng cho Billing API và để Resource Server validate.

### Bài 6 — Event-loop blocking

Một user service sau callback gọi JDBC blocking trực tiếp bên trong <code>map(...)</code>.

**Câu hỏi:** Rủi ro và cách khắc phục?

**Đáp án:** Blocking I/O làm kẹt reactive event-loop, tăng latency và giảm throughput. Nên dùng reactive database/client hoặc cô lập blocking call trên scheduler được giới hạn/đo đạc. Không gọi <code>block()</code> trong authentication pipeline.

### Bài 7 — Missing state trong cluster

Authorization request được tạo ở instance A; callback từ OP được load balancer chuyển đến instance B và nhận lỗi state không tìm thấy.

**Câu hỏi:** Có nên bỏ state validation?

**Đáp án:** Không. Cần cấu hình WebSession chia sẻ hoặc routing/session affinity thích hợp, kiểm tra cookie/Session repository và proxy. Bỏ state validation làm suy yếu OAuth2 flow.

### Bài 8 — Nhiều SecurityWebFilterChain

Một API chain với matcher <code>/**</code> được đặt <code>@Order(1)</code>, web OIDC Login chain đặt <code>@Order(2)</code>. Callback không chạy.

**Câu hỏi:** Vì sao?

**Đáp án:** Chain đầu match mọi request và được chọn trước, khiến callback không tới chain có OAuth2 Login WebFilter. Chỉ match API path cụ thể ở chain thứ nhất và giữ đường dẫn login/callback trong web chain.

### Bài 9 — Phân biệt OAuth2User và OidcUser

Provider A không dùng scope <code>openid</code>, provider B dùng <code>openid profile</code>.

**Câu hỏi:** Có thể ép mọi principal về <code>OidcUser</code> không?

**Đáp án:** Không. Spring Security OAuth2 Login thường tạo <code>OAuth2User</code> cho provider không OIDC; OIDC Login có <code>OidcUser</code>. Controller/authorization logic phải xét kiểu principal và cấu hình provider.

### Bài 10 — Thực hành WebFlux Login

1. Tạo Spring Boot WebFlux app, không trộn web MVC starter ngoài chủ đích.
2. Cấu hình OIDC ClientRegistration với issuer, Client ID/secret, scope <code>openid</code> và callback đã đăng ký.
3. Tạo <code>SecurityWebFilterChain</code> có <code>oauth2Login()</code>.
4. Thử mở <code>/oauth2/authorization/company</code>, quan sát redirect tới OP.
5. Sau login, dùng <code>/me</code> để xem subject/issuer và sự có mặt của UserInfo, **không hiển thị token**.
6. Dùng <code>WebClient</code> với authorized client để gọi một API thử nghiệm **có audience/scope phù hợp**.
7. Thử lỗi state mismatch, redirect URI sai, token bị từ chối và scope thiếu.
8. Thử song song nhiều browser sessions và mô tả nơi WebSession/authorized client được lưu.
9. Dùng <code>WebTestClient</code> với mock OIDC login cho controller security tests, phân biệt với integration test token exchange thật.
10. Ghi nhận kết quả bằng HTTP status, registration ID, mã lỗi và correlation ID an toàn.

## 22. Tổng kết

- WebFlux triển khai OAuth2/OIDC Login bằng **<code>SecurityWebFilterChain</code>, <code>ServerHttpSecurity</code>, WebFilters, WebSession và Reactor Context**, thay cho các abstraction Servlet quen thuộc.
- URL khởi tạo login thường là <code>/oauth2/authorization/{registrationId}</code>; callback authorization code thường là <code>/login/oauth2/code/{registrationId}</code>.
- Authorization request cần <code>state</code> để đối chiếu callback; với OIDC có thể có <code>nonce</code> để liên kết ID Token, và PKCE bảo vệ authorization code khi áp dụng.
- OP xác thực người dùng, trả authorization code; backend đổi code tại Token Endpoint rồi xác minh ID Token. **Không tin claim từ JWT chưa xác minh.**
- OIDC Login tạo principal <code>OidcUser</code>; OAuth2 Login thông thường có thể dùng <code>OAuth2User</code>. ID Token và UserInfo khác với access token dùng cho downstream API.
- Reactive security context lan truyền qua **<code>ReactiveSecurityContextHolder</code> và Reactor Context**; tránh phụ thuộc ThreadLocal hoặc gọi <code>block()</code>/<code>subscribe()</code> tùy tiện.
- <code>WebClient</code> và <code>ServerOAuth2AuthorizedClientExchangeFilterFunction</code> giúp dùng authorized client; chỉ gửi access token tới API **đúng audience/scope**.
- Browser WebSession, authorization request repository và authorized client storage là **ba trạng thái khác nhau**. Trong multi-instance cần thiết kế session/token sharing và refresh concurrency phù hợp.
- Khi có nhiều chain, <code>securityMatcher</code> và <code>@Order</code> phải bảo đảm authorization initiation/callback thuộc chain cấu hình OAuth2 Login.
- Duy trì HTTPS, session cookie an toàn, CSRF protection cho browser routes, state/nonce validation, kiểm soát role/tenant và tránh log token/credential.

### Tài liệu tham khảo

- **Spring Security Reference — Reactive OAuth2 Login:** cấu hình <code>oauth2Login()</code>, authorization flow, ClientRegistration và OIDC Login trong WebFlux.
- **Spring Security Reference — Reactive OAuth2 Client:** <code>ReactiveOAuth2AuthorizedClientManager</code>, <code>ServerOAuth2AuthorizedClientRepository</code> và <code>WebClient</code>.
- **Spring Security Reference — Reactive SecurityContext:** <code>ReactiveSecurityContextHolder</code> và Reactor Context.
- **Spring Security Reference — WebFlux Security:** <code>SecurityWebFilterChain</code>, <code>ServerHttpSecurity</code>, multiple chains và CSRF.
- **Spring Security Java API:** <code>OAuth2AuthorizationRequestRedirectWebFilter</code>, <code>OAuth2LoginAuthenticationWebFilter</code>, <code>WebSessionOAuth2ServerAuthorizationRequestRepository</code>, <code>ServerOAuth2AuthorizedClientExchangeFilterFunction</code>.
- **Spring Framework Reference — WebFlux / WebClient:** reactive execution, WebClient filters và HTTP response handling.
- **Spring Security Test — WebTestClient:** <code>SecurityMockServerConfigurers.mockOidcLogin()</code> để mô phỏng authentication trong reactive tests.
- **RFC 6749 — The OAuth 2.0 Authorization Framework:** Authorization Code Flow, token exchange và access/refresh token.
- **RFC 7636 — Proof Key for Code Exchange (PKCE):** <code>code_challenge</code> và <code>code_verifier</code>.
- **OpenID Connect Core 1.0:** OIDC Authorization Code Flow, ID Token, nonce và UserInfo.
- **OpenID Connect Discovery 1.0:** issuer và metadata dùng cấu hình OpenID Provider.
