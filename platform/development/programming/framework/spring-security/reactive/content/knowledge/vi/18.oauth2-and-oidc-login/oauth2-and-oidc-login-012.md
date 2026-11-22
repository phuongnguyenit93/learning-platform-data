# Đăng xuất OIDC do ứng dụng khởi tạo và giới hạn đăng xuất liên kết

## 1. Bối cảnh và kết quả học tập

Bài học thuộc phần **Đăng nhập OAuth2/OIDC** của **Spring Security - reactive / WebFlux**. Với ứng dụng đăng nhập bằng OpenID Connect (OIDC), nút **Đăng xuất** có thể mang nhiều ý nghĩa: hủy phiên của ứng dụng hiện tại, yêu cầu nhà cung cấp danh tính kết thúc phiên SSO, hoặc yêu cầu các ứng dụng liên kết khác cũng hủy phiên. Ba kết quả này **không tự động đồng nghĩa với nhau**.

**RP-Initiated Logout** (client-initiated logout, “đăng xuất do ứng dụng khởi tạo”) là luồng chuẩn trong **OpenID Connect RP-Initiated Logout 1.0**. Ứng dụng của bạn (Relying Party — **RP**) xử lý logout local, sau đó điều hướng trình duyệt của người dùng tới **Logout Endpoint** tại nhà cung cấp OIDC (OpenID Provider — **OP**). Spring Security WebFlux hỗ trợ bước này bằng `OidcClientInitiatedServerLogoutSuccessHandler`.

Mục tiêu:

1. Phân biệt **local logout**, **RP-initiated logout**, **OP-initiated front-channel**, **OP-initiated back-channel** và “logout mọi thiết bị”.
2. Hiểu sự khác nhau giữa **WebSession tại RP**, **OP session**, **session của RP khác**, access token và refresh token.
3. Đọc được `end_session_endpoint` trong discovery metadata, hiểu `id_token_hint`, `post_logout_redirect_uri`, `state` và quy tắc URI đăng ký.
4. Cấu hình đúng `ReactiveClientRegistrationRepository`, `ServerHttpSecurity.oauth2Login(...)`, `logout(...)` và reactive logout success handler.
5. Giữ **POST /logout được bảo vệ bởi CSRF**, đồng thời dọn local `SecurityContext` và `WebSession` trước khi chuyển browser sang OP.
6. Xây ví dụ Java 17+, Spring Boot 3.3.5/WebFlux có form logout và phần cấu hình OP thực.
7. Tạo **unit tests không cần OP thật** cho cách handler dựng redirect URI; phân biệt với các bài kiểm thử E2E cần OP.
8. Trình bày chính xác giới hạn: redirect đến OP **chưa chứng minh OP đã logout**, và OP logout **không bảo đảm mọi RP đã logout hoặc token bị thu hồi**.

Bài này tập trung vào **OIDC Login và RP-Initiated Logout ở phía client reactive**. Nó không tự triển khai OP, không nhầm Spring Security Servlet `OidcClientInitiatedLogoutSuccessHandler` với lớp reactive `OidcClientInitiatedServerLogoutSuccessHandler`.

## 2. Ba nơi giữ phiên và hệ quả bảo mật

Giả sử trình duyệt đã đăng nhập ứng dụng A và B thông qua một OP:

```text
Trình duyệt
  |
  +-- Cookie session của RP A ----> App A / WebSession A
  |
  +-- Cookie session của RP B ----> App B / Session B
  |
  +-- Cookie của OP -------------> Identity Provider / OP session
                                      |
                                      +-- Issuer của ID Token
                                      +-- Có thể đã cấp Access Token
                                      +-- Có thể đã cấp Refresh Token
```

Đây là ba vùng trạng thái độc lập:
- **RP A** quản lý security context, session ID, cookies và business state thuộc A.
- **OP** quản lý phiên SSO của chính OP, có thể có remember-me hoặc phiên với upstream Identity Provider.
- **RP B** quản lý WebSession riêng; nó không tự nhận một sự kiện logout của A nếu không có cơ chế truyền thông báo phù hợp.

RP A không thể trực tiếp xóa cookie của OP hoặc RP B vì cookie scopes/domain khác nhau. Nếu OP dùng nhiều thiết bị, logout một phiên browser cũng không nhất thiết hủy phiên trên điện thoại.

### Phân loại logout

| Kiểu | Ai khởi tạo? | Tác động trực tiếp | Không tự bảo đảm |
| --- | --- | --- | --- |
| **Local logout** | User tại RP A | Xóa authentication/session A | OP hoặc RP B đã logout |
| **RP-initiated logout** | RP A → trình duyệt → OP | Yêu cầu OP kết thúc phiên SSO | OP đã chấp thuận, RP B đã nhận notification |
| **Front-channel logout** | OP thông qua browser | OP gọi/nhúng endpoint logout của RP(s) | Browser luôn gửi cookie cần thiết |
| **Back-channel logout** | OP → server RP | RP nhận Logout Token và invalidate đúng session | RP được cấu hình hoặc có đủ session mapping |
| **Global logout / sign out everywhere** | Chính sách sản phẩm/OP | Thu hồi các phiên/credentials trong phạm vi thiết kế | Có sẵn mặc định chỉ nhờ một HTTP redirect |

**Quan sát quan trọng:** Nếu bạn local logout A rồi truy cập lại A và được đăng nhập ngay mà không cần nhập mật khẩu, local logout chưa chắc hỏng. Có thể OP vẫn còn **SSO session** và lập tức xác thực lại user. Muốn tránh trạng thái này, A có thể khởi tạo RP-Initiated Logout, nhưng OP phải thực sự hỗ trợ và xử lý yêu cầu đó.

## 3. Luồng RP-Initiated Logout trong Spring Security reactive

```text
Browser đang đăng nhập ở RP A
        |
        | POST /logout + cookie phiên + CSRF token
        v
Spring Security LogoutWebFilter tại RP A
        |
        +--> ServerLogoutHandler:
        |      xóa SecurityContext
        |      xóa CSRF token
        |      invalidate WebSession
        |
        v
OidcClientInitiatedServerLogoutSuccessHandler
        |
        +--> Nhận Authentication trước logout
        +--> Nhận diện OIDC principal / registrationId
        +--> ReactiveClientRegistrationRepository
        +--> Đọc metadata end_session_endpoint
        +--> Dựng OP redirect URL, gồm id_token_hint,
        |    post_logout_redirect_uri khi có cấu hình
        |
        v
HTTP redirect đến OP Logout Endpoint
        |
        v
Browser điều hướng sang OP (thường bằng GET)
        |
        +--> OP xử lý logout hoặc hiển thị xác nhận
        +--> OP có thể phát notification cho RP khác
        |
        v
OP có thể redirect về URI /signed-out đã đăng ký ở RP A
```

**Hai thao tác không được nhầm:**
1. **POST /logout** vào **RP** là state-changing request từ browser tới Spring Security. Khi ứng dụng dùng session/cookie và CSRF enabled, POST phải kèm CSRF token hợp lệ. GET /logout không nên trực tiếp làm logout.
2. HTTP redirect (thường GET) từ browser sang **OP end_session_endpoint** xảy ra **sau** logout local. OP quyết định thực thi request và trả kết quả theo hỗ trợ giao thức của nó.

`OidcClientInitiatedServerLogoutSuccessHandler` chỉ là **ServerLogoutSuccessHandler**: nó quyết định redirect sau khi logout cục bộ. Nó **không phải** handler đi tìm và xóa mọi RP session; trách nhiệm local cleanup thuộc `ServerLogoutHandler`.

Một status 302 của RP chứng minh **đã xây và phát lệnh điều hướng**, không chứng minh browser đã đến OP, OP đã xóa session, RP B đã logout hoặc access token đã bị revoke.

## 4. Những tham số OIDC phải hiểu

### 4.1. `end_session_endpoint` từ OP discovery

OIDC Provider có thể công bố metadata, ví dụ:

```json
{
  "issuer": "https://idp.example.test",
  "authorization_endpoint": "https://idp.example.test/authorize",
  "token_endpoint": "https://idp.example.test/token",
  "jwks_uri": "https://idp.example.test/jwks",
  "end_session_endpoint": "https://idp.example.test/connect/endsession"
}
```

Các URL trên là domain **minh họa**, không có một OP thật nào được giả định. Trong một OP hỗ trợ RP-Initiated Logout và Discovery, `end_session_endpoint` cho RP biết địa chỉ để yêu cầu OP logout. Spring Security có thể nhận metadata qua `issuer-uri` khi tạo `ClientRegistration` bằng discovery.

**Không đoán rằng OP nào cũng có `/logout`**; một số OP không công bố end-session endpoint, hoặc dùng cơ chế/vendor URL riêng. Khi đó phải kiểm tra tài liệu và khả năng hỗ trợ của OP.

So sánh:
- `authorization_endpoint`: bắt đầu login/authorization.
- `token_endpoint`: trao đổi authorization code lấy tokens.
- `end_session_endpoint`: yêu cầu OP kết thúc phiên.
- `revocation_endpoint` (nếu OP hỗ trợ): cơ chế **thu hồi token**, không đồng nghĩa với kết thúc OP session.

### 4.2. `id_token_hint`

`id_token_hint` (RECOMMENDED trong RP-Initiated Logout) là **ID Token** trước đó được OP cấp cho RP, nhằm gợi ý phiên/user/client mà OP cần logout.

Ví dụ URL sau khi đã URL-encode:

```http
GET /connect/endsession?id_token_hint=ID_TOKEN_TEST
    &post_logout_redirect_uri=https%3A%2F%2Fapp.example.test%2Fsigned-out
HTTP/1.1
Host: idp.example.test
```

HTTP request thực có URI trên **một dòng**; ví dụ được xuống dòng để dễ học. `ID_TOKEN_TEST` là một chuỗi giả dùng giải thích cú pháp.

ID Token:
- Mang thông tin xác thực/claims được phát cho RP.
- **Không phải** Access Token dùng gọi resource server.
- **Không phải** Refresh Token dùng xin access token mới.
- Khi gửi làm hint cho OP, **không tự thu hồi** access/refresh tokens còn hiệu lực.

ID Token có thể chứa thông tin người dùng, và trong một số OP log logout URL có thể ghi query string. Vì vậy **không ghi raw `Location` có `id_token_hint`, token, cookies hoặc token-bearing URLs vào logs/APM/analytics/support ticket**. Dùng HTTPS và cấu hình proxy/query redaction phù hợp.

### 4.3. `post_logout_redirect_uri`

Đây là nơi OP **có thể** điều hướng browser về sau khi hoàn thành logout:

```text
https://app.example.test/signed-out
```

OP yêu cầu URI này **khớp chính xác URI đăng ký** cho RP theo đặc tả. Nó **khác** login callback:

| URI | Công dụng |
| --- | --- |
| `https://app.example.test/login/oauth2/code/training` | OIDC authorization-code callback sau login |
| `https://app.example.test/signed-out` | Callback hiển thị trạng thái sau logout |
| `https://idp.example.test/connect/endsession` | OP Logout Endpoint |

Sai lầm thường gặp là đã đăng ký login callback nhưng **chưa** đăng ký post-logout URI; OP có thể từ chối redirect về dù yêu cầu logout hợp lệ.

Spring Security hỗ trợ template `{baseUrl}`:

```java
handler.setPostLogoutRedirectUri("{baseUrl}/signed-out");
```

Ứng dụng sau reverse proxy phải tính đúng **scheme/host/port công khai**, chẳng hạn `https://app.example.test` chứ không phải `http://localhost:8080`. Chỉ tin `Forwarded`/`X-Forwarded-*` từ proxy được kiểm soát; đừng dùng user-controlled URL để mở redirect.

### 4.4. `state`, `logout_hint` và `client_id`

Theo RP-Initiated Logout 1.0:
- `state`: optional, opaque value để RP liên kết logout request và callback; nếu RP dùng, phải xác minh response state đúng phiên và chống replay.
- `logout_hint`: optional, OP-specific hint về user/session, có thể chứa email/username nên cần cân nhắc privacy.
- `client_id`: optional trong các trường hợp OP cần nhận diện client, nhưng không mặc nhiên thay `id_token_hint` hay quy tắc URI đăng ký.

**Không giả định handler reactive ở Spring Security 6.3 tự sinh và xác minh `state` theo mọi workflow**; nếu ứng dụng tự triển khai logout return correlation thì phải thiết kế/test riêng.

### 4.5. Redirect GET và Form POST tại OP

`OidcClientInitiatedServerLogoutSuccessHandler` truyền thống dùng HTTP redirect để browser gửi GET tới OP. Một số OP/phiên bản framework có thể hỗ trợ logout bằng Form POST và redirect strategy tùy biến. **Đừng dùng API mới hơn một cách máy móc trên Spring Security 6.3**; kiểm tra version chính xác trước khi thêm option. Bài demo dùng redirect mặc định phù hợp nguồn tài liệu.

## 5. API reactive cần dùng

### `ReactiveClientRegistrationRepository`

Spring Boot có thể tự tạo repository từ `spring.security.oauth2.client.registration.*` và `spring.security.oauth2.client.provider.*`:

- `registrationId`: tên client nội bộ, ví dụ `training`.
- `client-id`, `client-secret` và cách xác thực client.
- `authorization-grant-type: authorization_code`.
- `scope: openid,profile` để dùng OIDC principal/ID Token.
- `redirect-uri` cho login callback.
- `issuer-uri` cho provider discovery, từ đó có thể lấy `end_session_endpoint`.

Repository **reactive** khác `ClientRegistrationRepository` của Servlet. Nếu bạn import nhầm loại Servlet, constructor của handler reactive không khớp.

### `OidcClientInitiatedServerLogoutSuccessHandler`

Class:

```java
import org.springframework.security.oauth2.client.oidc.web.server.logout.OidcClientInitiatedServerLogoutSuccessHandler;
```

Fragment cấu hình:

```java
OidcClientInitiatedServerLogoutSuccessHandler oidcLogout =
        new OidcClientInitiatedServerLogoutSuccessHandler(
                clientRegistrationRepository);
oidcLogout.setPostLogoutRedirectUri("{baseUrl}/signed-out");
```

Trong đó `clientRegistrationRepository` là biến kiểu `ReactiveClientRegistrationRepository`, được Spring inject. Handler dùng authentication trước logout để xây redirect URI cho OIDC user.

Nếu user login bằng form/Basic hoặc thông tin OIDC không đủ, handler có thể dùng **local fallback success URL**, thay vì gửi một OP logout request không có context. Việc fallback phải được kiểm thử khi ứng dụng cho phép nhiều login methods.

### `ServerLogoutHandler` và cleanup

Trong WebFlux:
- `SecurityContextServerLogoutHandler`: xóa security context lưu tại RP.
- `WebSessionServerLogoutHandler`: invalidate WebSession hiện tại.
- `CsrfServerLogoutHandler`: xóa CSRF token trong repository tương ứng.
- `DelegatingServerLogoutHandler`: phối hợp các handlers.

Tạo custom `logoutHandler(...)` là một quyết định về **cleanup**, không phải hành động đơn giản gắn thêm một redirect. Cần bảo đảm không bỏ quên hủy WebSession, đặc biệt nếu security context/session repositories đã được tùy chỉnh.

### WebFlux khác Servlet

| WebFlux reactive | Servlet |
| --- | --- |
| `ServerHttpSecurity` | `HttpSecurity` |
| `SecurityWebFilterChain` | `SecurityFilterChain` |
| `ReactiveClientRegistrationRepository` | `ClientRegistrationRepository` |
| `OidcClientInitiatedServerLogoutSuccessHandler` | `OidcClientInitiatedLogoutSuccessHandler` |
| `WebSession` | `HttpSession` |
| `ServerLogoutHandler` | `LogoutHandler` |

**Không copy imports từ ví dụ Servlet** rồi mong chúng hoạt động trong một app WebFlux.

## 6. Dự án Java 17 + Spring Boot 3.3.5 WebFlux

Demo sau chạy như một **OIDC Relying Party** khi bạn đã có một provider test hỗ trợ discovery/end-session và client registration. Phần **unit tests ở mục 9 không cần OP mạng**, nhưng **đăng nhập và logout thật** đòi hỏi OP/IdP. Đây là điều kiện giao thức, không phải một service giả có thể tự khởi tạo bằng mã Java.

Cấu trúc:

```text
reactive-oidc-logout/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/dev/example/oidclogout/
    │   │   ├── OidcLogoutApplication.java
    │   │   ├── SecurityConfig.java
    │   │   └── DemoController.java
    │   └── resources/application.yml
    └── test/java/dev/example/oidclogout/
        └── OidcLogoutHandlerTests.java
```

### 6.1. Gradle

`settings.gradle`:

```groovy
rootProject.name = 'reactive-oidc-logout'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'dev.example'
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
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Chỉ dùng WebFlux starter để ứng dụng chọn reactive stack. Nếu thêm `spring-boot-starter-web`, Spring Boot thường ưu tiên Servlet/MVC, không còn khớp ví dụ này.

### 6.2. Main class

`src/main/java/dev/example/oidclogout/OidcLogoutApplication.java`:

```java
package dev.example.oidclogout;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OidcLogoutApplication {
    public static void main(String[] args) {
        SpringApplication.run(OidcLogoutApplication.class, args);
    }
}
```

### 6.3. Cấu hình provider trong `application.yml`

`src/main/resources/application.yml`:

```yaml
server:
  port: 8080

spring:
  security:
    oauth2:
      client:
        registration:
          training:
            provider: training
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            scope: openid,profile
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
        provider:
          training:
            issuer-uri: ${OIDC_ISSUER_URI}
```

Bạn phải cung cấp 3 biến môi trường `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET`, `OIDC_ISSUER_URI` từ **OIDC provider thực/test**. Không lưu client secret thật trong Git, screenshots hoặc command-line history. Đây là runtime configuration bắt buộc để liên hệ OP, không phải giá trị cần suy đoán.

Ở OP, đăng ký **hai URI riêng**:
- Login callback: `http://localhost:8080/login/oauth2/code/training` (khi OP cho phép local HTTP) hoặc HTTPS public URI.
- Post-logout return: `http://localhost:8080/signed-out` (khi OP cho phép local HTTP) hoặc `https://app.example.test/signed-out`.

Không mặc định OP chấp nhận HTTP localhost; nhiều OP chỉ cho HTTPS, hoặc có giới hạn chi tiết với callback. Tài liệu OP là nguồn quyết định.

**Khởi động có thể cần discovery qua mạng** từ `issuer-uri`. Nếu OP không thể kết nối/DNS/TLS lỗi, ứng dụng có thể không khởi động hoặc không đăng nhập. Unit tests ở mục 9 dùng client registration giả nên chạy mà không cần các biến môi trường.

### 6.4. Spring Security reactive và logout handlers

`src/main/java/dev/example/oidclogout/SecurityConfig.java`:

```java
package dev.example.oidclogout;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.oauth2.client.registration.ReactiveClientRegistrationRepository;
import org.springframework.security.oauth2.client.oidc.web.server.logout.OidcClientInitiatedServerLogoutSuccessHandler;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.authentication.logout.DelegatingServerLogoutHandler;
import org.springframework.security.web.server.authentication.logout.SecurityContextServerLogoutHandler;
import org.springframework.security.web.server.authentication.logout.ServerLogoutHandler;
import org.springframework.security.web.server.authentication.logout.WebSessionServerLogoutHandler;
import org.springframework.security.web.server.csrf.CsrfServerLogoutHandler;
import org.springframework.security.web.server.csrf.ServerCsrfTokenRepository;
import org.springframework.security.web.server.csrf.WebSessionServerCsrfTokenRepository;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http,
            ReactiveClientRegistrationRepository registrations) {

        ServerCsrfTokenRepository csrfRepository =
                new WebSessionServerCsrfTokenRepository();

        ServerLogoutHandler cleanup = new DelegatingServerLogoutHandler(
                new SecurityContextServerLogoutHandler(),
                new CsrfServerLogoutHandler(csrfRepository),
                new WebSessionServerLogoutHandler());

        OidcClientInitiatedServerLogoutSuccessHandler oidcLogout =
                new OidcClientInitiatedServerLogoutSuccessHandler(
                        registrations);
        oidcLogout.setPostLogoutRedirectUri("{baseUrl}/signed-out");

        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/", "/signed-out", "/login")
                            .permitAll()
                        .anyExchange().authenticated())
                .oauth2Login(Customizer.withDefaults())
                .csrf(csrf -> csrf.csrfTokenRepository(csrfRepository))
                .logout(logout -> logout
                        .logoutUrl("/logout")
                        .logoutHandler(cleanup)
                        .logoutSuccessHandler(oidcLogout))
                .build();
    }
}
```

**Giải thích:**

1. `@EnableWebFluxSecurity` và `ServerHttpSecurity` cấu hình ứng dụng reactive.
2. `oauth2Login(...)` cho phép OIDC login khi ClientRegistration có scope `openid` và OP đáp ứng yêu cầu.
3. `ReactiveClientRegistrationRepository` được Boot tạo từ `application.yml`; handler dùng repository đúng OP.
4. `csrfRepository` dùng chung cho CSRF filter và `CsrfServerLogoutHandler`; tránh một nơi verify token A nhưng nơi khác xóa token B.
5. `SecurityContextServerLogoutHandler` xóa context; `WebSessionServerLogoutHandler` invalidate local session; `CsrfServerLogoutHandler` xóa token cũ.
6. `DelegatingServerLogoutHandler` giữ các bước local cleanup tường minh khi tự thay logout handler.
7. `OidcClientInitiatedServerLogoutSuccessHandler` là **success handler**, tạo response chuyển browser tới OP sau cleanup, không tự hủy mọi phiên liên kết.
8. `{baseUrl}/signed-out` phải được đăng ký **chính xác** với OP. Không chấp nhận post-logout URI tùy ý từ request query.
9. `/signed-out` là public, vì browser quay về từ OP khi WebSession cục bộ đã bị hủy.
10. Không disable CSRF và không chuyển logout thành GET để tránh lỗi 403.
11. Nếu production dùng Spring Session Redis hoặc custom session resolver, kiểm tra invalidation thực ở session store và cookie name/Path/Domain.

Spring Security WebFlux có thể hỗ trợ local logout mặc định với `/logout`; code này cố ý chỉ rõ cleanup handler để người học nhận biết bước nào thực hiện. Đừng diễn giải một redirect success handler thành “toàn bộ session ở mọi nơi đã bị thu hồi”.

### 6.5. Controller với form logout POST có CSRF

`src/main/java/dev/example/oidclogout/DemoController.java`:

```java
package dev.example.oidclogout;

import java.util.Map;

import org.springframework.http.MediaType;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.security.web.server.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.util.HtmlUtils;

import reactor.core.publisher.Mono;

@RestController
public class DemoController {

    @GetMapping("/")
    public Mono<String> home() {
        return Mono.just(
                "OIDC WebFlux demo: /oauth2/authorization/training "
              + "-> /profile -> /logout-form");
    }

    @GetMapping("/profile")
    public Mono<Map<String, String>> profile(
            @AuthenticationPrincipal OidcUser user) {
        return Mono.just(Map.of("subject", user.getSubject()));
    }

    @GetMapping(value = "/logout-form",
            produces = MediaType.TEXT_HTML_VALUE)
    public Mono<String> logoutForm(ServerWebExchange exchange) {
        Mono<CsrfToken> tokenPublisher =
                exchange.getAttribute(CsrfToken.class.getName());

        if (tokenPublisher == null) {
            return Mono.error(new IllegalStateException(
                    "CSRF token unavailable"));
        }

        return tokenPublisher.map(token -> """
                <!doctype html>
                <html lang="vi">
                <head><meta charset="UTF-8"><title>Đăng xuất</title></head>
                <body>
                  <h1>Đăng xuất ứng dụng và yêu cầu logout tại OP</h1>
                  <form action="/logout" method="post">
                    <input type="hidden" name="%s" value="%s">
                    <button type="submit">Đăng xuất</button>
                  </form>
                </body>
                </html>
                """.formatted(
                    HtmlUtils.htmlEscape(token.getParameterName()),
                    HtmlUtils.htmlEscape(token.getToken())));
    }

    @GetMapping("/signed-out")
    public Mono<String> signedOut() {
        return Mono.just(
                "Phiên ứng dụng cục bộ đã kết thúc. "
              + "Đăng xuất OP và các ứng dụng liên kết "
              + "phụ thuộc kết quả giao thức và cấu hình.");
    }
}
```

- `/profile` cần OIDC session và chỉ hiển thị `subject`, **không trả raw ID Token/access token/refresh token**.
- `/logout-form` yêu cầu authentication do `anyExchange().authenticated()`, lấy `Mono<CsrfToken>` từ exchange attribute và render hidden field.
- Browser thực hiện **form POST /logout** (full-page navigation), dễ phù hợp redirect tới domain OP hơn `fetch("/logout")` vốn chỉ theo redirects bên trong fetch.
- `/signed-out` public; khi quay về từ OP không còn session cũ, nếu bắt auth sẽ tạo vòng login.
- HTML escaping cho hidden input có ích khi render attribute; với ứng dụng thật, ưu tiên template engine có escaping an toàn và security headers phù hợp.

## 7. Chạy với OP thực và đọc kết quả đúng

### Chuẩn bị OP

1. Tạo OIDC client trong một OP thử nghiệm thực sự hỗ trợ **RP-Initiated Logout 1.0**.
2. Đăng ký login callback và post-logout redirect URI.
3. Cung cấp `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET`, `OIDC_ISSUER_URI` an toàn.
4. Kiểm tra metadata có `end_session_endpoint` và TLS/certificate được xác thực.
5. Trong production, dùng HTTPS; không đưa client secret hoặc `id_token_hint` vào URL/log có thể bị chia sẻ.

Chạy:

```bash
gradle bootRun
```

Nếu có Gradle Wrapper, dùng `./gradlew bootRun` hoặc `gradlew.bat bootRun`. Khi chưa có OP thật, **unit test phần 9 vẫn chạy độc lập**, nhưng OIDC login end-to-end không thể được xác nhận.

### Thực hiện

1. Mở `http://localhost:8080/oauth2/authorization/training` hoặc URL HTTPS tương ứng. Browser chuyển tới OP đăng nhập.
2. Khi OP xác thực và trả authorization code, Spring Security hoàn tất OIDC login tại `/login/oauth2/code/training`.
3. Mở `/profile`, nhận `subject` của user đã đăng nhập.
4. Mở `/logout-form`. Browser tải CSRF token của session đang hoạt động.
5. Bấm **Đăng xuất**. Browser gửi `POST /logout` và cookie WebSession + token.
6. Kiểm tra Network: RP trả response redirect có `Location` trỏ tới `end_session_endpoint` ở OP. **Không sao chép URL thực vì chứa `id_token_hint`**.
7. Browser đến OP. OP có thể hiển thị xác nhận hoặc xử lý logout và redirect về `/signed-out` đã đăng ký.
8. Sau khi logout, truy cập lại `/profile`; local RP session cũ không còn được công nhận.
9. Quan sát OP có còn single sign-on ngay không; nếu có, kiểm tra OP session/logout behavior, không mặc định kết luận RP local logout thất bại.
10. Nếu có RP B trong bài lab, kiểm tra session B thực tế còn hay mất, không suy từ status redirect của RP A.

### POST thiếu CSRF

Nếu gửi POST/logout không có token trong ứng dụng dùng browser session và CSRF enabled, kết quả thường **403 Forbidden**, logout không được thực hiện thành công. Không “sửa” bằng cách tắt CSRF hoặc đổi sang GET logout.

### Nếu OP không hỗ trợ end-session

Nếu metadata không có `end_session_endpoint`, ứng dụng không thể giả định RP-Initiated Logout có thể hoạt động. Handler có thể dùng fallback local; sản phẩm phải giải thích rõ “phiên ứng dụng đã kết thúc” nhưng SSO tại OP có thể còn. Đọc provider docs nếu cần endpoint riêng và không tự ghép một vendor logout URL từ input không đáng tin.

## 8. Thiết kế kiểm thử cho các phạm vi độc lập

| Tình huống | Kỳ vọng | Chứng minh được |
| --- | --- | --- |
| User chưa OIDC login vào `/profile` | Yêu cầu login | HTTP security |
| Login OIDC thành công | Profile có subject | OIDC login tại RP |
| POST/logout thiếu CSRF | 403 | CSRF guard RP |
| POST/logout hợp lệ | Redirect đến OP end-session | RP đã **yêu cầu** OP logout |
| Redirect có `id_token_hint` | Có ID Token hint phù hợp | Redirect được xây từ OIDC authentication |
| URI trả về đã đăng ký | OP có thể trả browser về `/signed-out` | Post-logout navigation |
| Sử dụng lại RP session ID cũ | Không thể truy cập profile như user cũ | Local session invalidation |
| Login lại sau OP logout | Phụ thuộc OP auth policy | OP session thực sự còn hay không |
| RP B không hỗ trợ notification | Session B có thể vẫn còn | Giới hạn logout liên kết |
| RP B có back-channel | RP B validate Logout Token và hủy session | Federated session propagation |
| Access token cũ còn hiệu lực | Tùy expiration/revocation/introspection | Token lifecycle **riêng** |
| Multi-device session | Tùy OP và policy global logout | Không mặc định logout mọi thiết bị |

**Nguyên tắc QA:** Unit tests của handler có thể kiểm tra **Location URL**, nhưng không xác minh OP thực sự đã logout. E2E tests cần một OP test, browser thật hoặc HTTP client phù hợp với OIDC flow và session store.

Khi kiểm tra local session invalidation:
- Login với tài khoản test và lưu ID phiên RP trong môi trường an toàn.
- POST/logout đúng CSRF token.
- Gửi thử request bảo vệ với **session ID cũ** từ client độc lập.
- Xác nhận server **không nhận identity cũ**, kể cả nếu browser vẫn giữ cookie.
- Với session phân tán, test qua nhiều instances.

Không thử bằng session ID/token thật từ production hoặc công khai Network trace chứa secret.

## 9. Unit tests của reactive logout handler, không cần OP mạng

Các tests này dùng một `ClientRegistration` **giả** với OP metadata chứa `end_session_endpoint` test, xây `OidcUser`/`OidcIdToken` giả, gọi thẳng `OidcClientInitiatedServerLogoutSuccessHandler`. Do đó **không phụ thuộc issuer-uri, OP test server, browser hoặc application.yml**.

Tệp `src/test/java/dev/example/oidclogout/OidcLogoutHandlerTests.java`:

```java
package dev.example.oidclogout;

import java.net.URI;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.mock.web.server.MockServerWebExchange;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.client.authentication.OAuth2AuthenticationToken;
import org.springframework.security.oauth2.client.oidc.web.server.logout.OidcClientInitiatedServerLogoutSuccessHandler;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.client.registration.InMemoryReactiveClientRegistrationRepository;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;
import org.springframework.security.oauth2.core.oidc.OidcIdToken;
import org.springframework.security.oauth2.core.oidc.user.DefaultOidcUser;
import org.springframework.security.oauth2.core.oidc.user.OidcUserAuthority;
import org.springframework.security.web.server.WebFilterExchange;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class OidcLogoutHandlerTests {

    private ClientRegistration testRegistration() {
        return ClientRegistration.withRegistrationId("training")
                .clientId("test-client-only")
                .clientSecret("test-secret-only")
                .clientAuthenticationMethod(
                        ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
                .authorizationGrantType(
                        AuthorizationGrantType.AUTHORIZATION_CODE)
                .redirectUri(
                        "{baseUrl}/login/oauth2/code/{registrationId}")
                .scope("openid", "profile")
                .authorizationUri("https://idp.example.test/authorize")
                .tokenUri("https://idp.example.test/token")
                .jwkSetUri("https://idp.example.test/jwks")
                .issuerUri("https://idp.example.test")
                .providerConfigurationMetadata(Map.of(
                        "end_session_endpoint",
                        "https://idp.example.test/connect/endsession"))
                .build();
    }

    private OidcClientInitiatedServerLogoutSuccessHandler handler() {
        var repo = new InMemoryReactiveClientRegistrationRepository(
                testRegistration());
        var handler =
                new OidcClientInitiatedServerLogoutSuccessHandler(repo);
        handler.setPostLogoutRedirectUri("{baseUrl}/signed-out");
        handler.setLogoutSuccessUrl(URI.create("/signed-out"));
        return handler;
    }

    private Authentication oidcAuth(String tokenValue) {
        OidcIdToken token = OidcIdToken.withTokenValue(tokenValue)
                .subject("test-user")
                .claim("iss", "https://idp.example.test")
                .build();

        var principal = new DefaultOidcUser(
                List.of(new OidcUserAuthority(token)), token);

        return new OAuth2AuthenticationToken(
                principal, principal.getAuthorities(), "training");
    }

    private URI redirect(
            OidcClientInitiatedServerLogoutSuccessHandler handler,
            Authentication authentication) {

        MockServerWebExchange exchange = MockServerWebExchange.from(
                MockServerHttpRequest
                        .post("https://app.example.test/logout").build());

        WebFilterExchange webFilterExchange =
                new WebFilterExchange(exchange, e -> Mono.empty());

        StepVerifier.create(
                handler.onLogoutSuccess(webFilterExchange, authentication))
                .verifyComplete();

        URI location = exchange.getResponse()
                .getHeaders().getLocation();
        assertNotNull(location);
        return location;
    }

    private String decodedQuery(URI redirect) {
        assertNotNull(redirect.getRawQuery());
        return URLDecoder.decode(
                redirect.getRawQuery(), StandardCharsets.UTF_8);
    }

    @Test
    void redirectsToTheConfiguredProviderEndSessionEndpoint() {
        URI location = redirect(handler(), oidcAuth("id-token-one"));

        assertEquals("https", location.getScheme());
        assertEquals("idp.example.test", location.getHost());
        assertEquals("/connect/endsession", location.getPath());
    }

    @Test
    void sendsCurrentIdTokenAsHint() {
        URI location = redirect(handler(), oidcAuth("id-token-two"));
        assertTrue(decodedQuery(location)
                .contains("id_token_hint=id-token-two"));
    }

    @Test
    void includesRegisteredPostLogoutReturnUri() {
        URI location = redirect(handler(), oidcAuth("id-token-three"));
        assertTrue(decodedQuery(location).contains(
                "post_logout_redirect_uri=https://app.example.test/signed-out"));
    }

    @Test
    void differentUsersTokensYieldDifferentRedirects() {
        URI first = redirect(handler(), oidcAuth("test-token-A"));
        URI second = redirect(handler(), oidcAuth("test-token-B"));

        assertNotEquals(first, second);
        assertTrue(decodedQuery(first).contains(
                "id_token_hint=test-token-A"));
        assertTrue(decodedQuery(second).contains(
                "id_token_hint=test-token-B"));
    }

    @Test
    void nonOidcAuthenticationUsesLocalFallback() {
        Authentication local =
                UsernamePasswordAuthenticationToken.authenticated(
                        "local-user", "not-real-password", List.of());

        URI location = redirect(handler(), local);
        assertEquals("/signed-out", location.toString());
    }
}
```

Chạy:

```bash
gradle test --tests dev.example.oidclogout.OidcLogoutHandlerTests
```

**Dự kiến:** 5 tests thành công với dependencies ở mục 6, **không gọi OP**. Đây là kỳ vọng dựa trên API/cấu trúc ví dụ, **không phải khẳng định đã chạy Gradle trong máy của bạn**.

Các tests kiểm tra:
- OP logout host/path/schema đúng từ metadata.
- `id_token_hint` lấy từ OIDC principal thay vì ID token hardcoded.
- `post_logout_redirect_uri` được xây từ base URL đúng.
- ID Token khác nhau tạo hint khác nhau.
- User không phải OIDC có fallback nội bộ.

**Giới hạn của suite:** Nó không chạy Spring Boot security chain thật, không test POST CSRF, WebSession invalidation, cookie, OP response, RP B notification, token revocation hoặc logout đa thiết bị. Khi đưa production phải bổ sung WebTestClient integration với `mockOidcLogin()` hoặc browser/OP E2E tùy phạm vi, và kiểm tra session invalidation bằng ID cũ.

## 10. Đăng xuất liên kết có những giới hạn gì?

### 10.1. RP A logout không có quyền hủy RP B

Ngay cả khi OP logout thành công, RP B có thể còn session cũ. Chỉ khi OP và B cùng hỗ trợ **front-channel/back-channel notifications** hoặc một cơ chế session registry khác thì B mới biết cần invalidate session.

**Front-channel logout:** thông báo đi qua browser. Nó có thể thất bại khi browser chặn third-party cookies, iframe, network hoặc frame restrictions. Vì vậy không dùng kết quả redirect của A làm bằng chứng B đã logout.

**Back-channel logout:** OP gửi **Logout Token** server-to-server đến RP; RP cần verify signature, issuer/audience, logout event, `sid`/`sub` và replay controls. Nó yêu cầu endpoint/registry và liên hệ phiên OP-RP. Không phải “tự có” chỉ vì cấu hình RP-initiated logout.

**Phiên bản framework:** Tài liệu Spring Security hiện đại có hỗ trợ back-channel reactive, nhưng các DSL/requirements có thể được bổ sung sau Spring Security 6.3. Bài này dùng Boot 3.3.5/ Security 6.3.x cho RP-initiated; khi triển khai back-channel hãy chọn version thực sự hỗ trợ và kiểm tra API đúng version, cookie name và session registry.

### 10.2. OP logout không nhất thiết revoke bearer tokens

OIDC end-session thường nói về **SSO session**. Các OAuth2 access tokens đã phát có thể vẫn hợp lệ tại resource server tới expiry hoặc khi được introspect/revoked tùy OP. Refresh token cũng cần lifecycle/revocation policy riêng. Nếu sản phẩm cần logout lập tức vô hiệu API credentials, phải thiết kế/token revocation hoặc token introspection/denylist tương ứng.

`id_token_hint` **không** là access/refresh token revocation request. Đừng ghi trong tài liệu “logout OP đồng nghĩa revoke mọi JWT”.

### 10.3. Không tự logout mọi thiết bị

Session trên browser A khác mobile device B. RP-initiated logout không mặc nhiên yêu cầu OP hủy toàn bộ phiên của user trên mọi thiết bị. Cần policy global sign-out, session index, token revocation và notification tới đúng RP(s).

### 10.4. OP có thể không chuyển về RP

Theo chuẩn, OP có thể cần xác nhận user; nếu `post_logout_redirect_uri` không khớp đăng ký, OP **không được** redirect đến URI đó. Vì vậy:
- RP redirect 302 chưa xác nhận logout tại OP.
- Browser không về `/signed-out` không tự có nghĩa local logout thất bại.
- Nếu OP outage, UX nên nói “Đã kết thúc phiên ứng dụng; chưa xác nhận logout ở nhà cung cấp danh tính”.
- Không trông chờ OP luôn quay về RP để dọn những state lẽ ra RP phải dọn **trước** redirect.

### 10.5. Logout xong lại được đăng nhập không cần nhập mật khẩu

Nguồn SSO có thể là OP session, upstream SAML/IdP session, remember-me, browser credential manager hoặc session thiết bị khác. Phân tích:
1. Đã thực hiện local `WebSession.invalidate()`?
2. Browser thực sự chuyển tới OP `end_session_endpoint`?
3. OP xử lý/logout hay chỉ hiển thị trang?
4. OP có upstream authentication session vẫn hoạt động?
5. User nhập lại app nhưng được tự cấp phiên mới do OP auth policy?

Kết quả “được login lại ngay” **không đủ** để định lỗi nằm tại RP hay OP.

## 11. Vấn đề bảo mật khi cấu hình thật

### CSRF

Giữ POST/logout với CSRF token cho app browser dùng WebSession/cookie. Không tạo endpoint GET/logout state-changing. Nếu token hết hạn do session timeout, thiết kế UX phù hợp thay vì tắt CSRF.

### Redirect và open redirect

`post_logout_redirect_uri` phải được OP đăng ký và RP kiểm soát. Không chuyển tiếp raw `returnTo` hoặc callback từ query do user gửi. Nếu dùng `{baseUrl}` sau reverse proxy, chỉ trust forwarded headers của proxy được quản lý, cố định public host và scheme HTTPS.

### Token và log

ID Token có thể xuất hiện trong OP redirect URI qua `id_token_hint`; đừng log raw `Location`, full URLs hoặc request headers có token. Đồng thời scrub `Authorization`, cookies, client secrets và refresh tokens trong gateway, APM và support artifacts. Dùng HTTPS, hạn chế referrer leakage và third-party assets trên trang chuyển tiếp.

### Local session invalidate

Xóa cookie browser chưa chứng minh session server đã hết hiệu lực. Test một phiên cũ bằng HTTP client độc lập; với Spring Session backend phân tán, kiểm tra trên nhiều nodes. `WebSessionServerLogoutHandler` xử lý session hiện tại, không hủy session khác khi chưa thiết kế global logout.

### SSO UX

Không tuyên bố “Đã đăng xuất mọi ứng dụng” nếu chỉ có RP-initiated redirect. Thông điệp chính xác có thể là “Bạn đã đăng xuất khỏi ứng dụng này; trạng thái đăng xuất tại nhà cung cấp và ứng dụng liên kết phụ thuộc vào cấu hình hệ thống.”

## 12. Bảng lỗi thường gặp

| Lỗi/hiện tượng | Nguyên nhân | Hướng kiểm tra |
| --- | --- | --- |
| POST/logout → 403 | Thiếu/sai CSRF token | Lấy token từ WebSession hiện tại; không disable |
| Logout chỉ redirect local | Không phải OIDC principal hoặc OP không có end-session | Kiểm tra scope `openid` và metadata |
| OP từ chối post-logout URI | Callback không được đăng ký/không exact match | Đăng ký chính xác scheme/host/port/path |
| `{baseUrl}` thành HTTP/localhost | Reverse proxy forwarded headers sai | Cấu hình trusted proxy, public URL HTTPS |
| OP báo ID token invalid | Hint sai client/issuer/đã hết ngữ cảnh | Dùng ID Token của login OIDC hiện tại |
| Redirect chứa token trong log | Access logging ghi query/Location | Redact token-bearing URLs |
| RP A logout, RP B vẫn hoạt động | Không có OP notification hoặc B không hỗ trợ | Thiết kế front/back-channel riêng |
| JWT vẫn dùng được | Logout không revoke access token | Token lifecycle/revocation |
| Browser cookie còn nhưng session đã logout | Cookie client cleanup khác server invalidation | Thử reuse server session ID cũ |
| Tên cookie là `SESSION` chứ không `JSESSIONID` | WebFlux/Spring Session khác Servlet | Xem `WebSessionIdResolver`/cookie config |
| `/signed-out` redirect lại login | Callback bị bảo vệ bởi authenticated rule | Cho phép public callback |
| Logout dùng fetch không đổi trang | Fetch redirect không phải top-level navigation | Dùng HTML form POST/full-page navigation |
| OP thiếu `end_session_endpoint` | Không hỗ trợ chuẩn hoặc metadata thiếu | Không đoán URL, dùng provider docs |
| OP không trả về RP | OP cần xác nhận, URI sai hoặc network | Local logout vẫn có thể thành công |
| Global logout không hoạt động | Chưa có session registry/notification/token revoke | Thiết kế phạm vi riêng |
| Unit test Location xanh nhưng OP session còn | Chỉ test redirect builder | Test OP/browser E2E |

## 13. Checklist triển khai

1. Đã đăng ký OIDC client với OP đúng issuer, scope `openid` và redirect URIs.
2. OP công bố `end_session_endpoint` hoặc có cơ chế logout được tài liệu xác nhận.
3. Client credentials được quản lý bằng secret manager, không hardcode.
4. Login callback và post-logout redirect URI được đăng ký **riêng**, exact match.
5. Security stack đúng **WebFlux**: `ServerHttpSecurity` + `SecurityWebFilterChain`.
6. Handler dùng `ReactiveClientRegistrationRepository` và `OidcClientInitiatedServerLogoutSuccessHandler`.
7. POST/logout có CSRF token, không có GET state-changing.
8. Local `SecurityContext` bị xóa và `WebSession` invalidate thực sự.
9. Callback public, không tạo vòng login.
10. URL công khai là HTTPS/host đáng tin khi sau reverse proxy.
11. Raw ID Token, client secret, cookies, token-bearing Location không bị log.
12. Không dùng redirect URL do client tự điều khiển.
13. Có test fallback khi user không phải OIDC.
14. Có test status/Location của RP handler **và** E2E OP behavior.
15. Có test reuse session ID cũ sau logout.
16. Nếu cần RP B logout, cơ chế notification được hỗ trợ, đăng ký và verify.
17. Nếu cần global signout, session registry/multiple devices/token revocation được thiết kế.
18. UI phản ánh **phạm vi logout đã được chứng minh**, không nói quá khả năng.
19. Kiểm tra failure cases: OP downtime, session timeout, callback URI mismatch, reverse proxy redirect, browser cookies blocked.
20. Phiên bản Spring Security dùng cho RP-initiated/back-channel được xác nhận, không copy API từ tài liệu version khác.

## 14. Câu hỏi tự kiểm tra

**1. RP-Initiated Logout là gì?**  
RP yêu cầu OP logout user thông qua browser, thường sau khi đã dọn local session.

**2. Class WebFlux hỗ trợ luồng này?**  
`OidcClientInitiatedServerLogoutSuccessHandler`.

**3. Nó dùng repository nào?**  
`ReactiveClientRegistrationRepository`, không phải Servlet repository.

**4. `end_session_endpoint` lấy ở đâu?**  
Từ OIDC Provider discovery metadata nếu OP hỗ trợ.

**5. `id_token_hint` là access token không?**  
Không, đó là ID Token đã cấp, dùng làm hint cho OP.

**6. `post_logout_redirect_uri` có phải login callback không?**  
Không. Nó là URI browser về sau OP logout, được đăng ký riêng.

**7. RP-initiated logout có cần POST không?**  
Ứng dụng RP thường dùng POST/logout có CSRF; OP endpoint thường được gọi qua redirect GET, là bước khác.

**8. Tại sao callback /signed-out nên public?**  
Local session đã bị hủy trước khi OP redirect về.

**9. RP A logout có làm RP B tự logout không?**  
Không đảm bảo; cần OP notifications và RP B hỗ trợ.

**10. OP session đã kết thúc có tự làm access token vô hiệu không?**  
Không mặc định. Token revocation/expiry/introspection thuộc cơ chế khác.

**11. Redirect 302 tới OP chứng minh điều gì?**  
RP đã yêu cầu browser đi tới OP, chưa chứng minh OP đã thực hiện logout.

**12. User login lại ngay có chắc lỗi local logout không?**  
Không. Có thể SSO session ở OP/upstream còn hoạt động.

**13. Tại sao không log Location của OIDC logout?**  
Nó có thể chứa `id_token_hint` và thông tin nhạy cảm.

**14. Back-channel logout khác gì?**  
OP gửi Logout Token server-to-server tới RP; cần endpoint, validation và session mapping riêng.

**15. Nếu OP không có end-session endpoint?**  
Làm local logout trung thực, dùng provider docs nếu có vendor-specific logout; không đoán URL.

**16. Unit test không OP thật xác minh được gì?**  
Cấu trúc redirect URI, ID Token hint, callback và fallback; không chứng minh OP logout hoặc federated propagation.

### Bài tập thực hành

1. Đăng ký một OIDC test client với login callback và post-logout URI riêng, giải thích vì sao không được dùng nhầm.
2. Chạy app qua OP thử nghiệm, dùng form POST/logout và kiểm tra redirect metadata **mà không chia sẻ token thật**.
3. Thử POST/logout thiếu CSRF và giải thích lỗi 403.
4. Thử sai post-logout URI và quan sát OP từ chối redirect, sau đó sửa URI exact match.
5. Thử reverse proxy có public HTTPS host và kiểm tra `{baseUrl}` được tính đúng.
6. Lưu một session ID giả trong bài lab, logout và thử reuse từ client khác, xác nhận RP server từ chối.
7. Chạy RP A và RP B cùng OP, logout A; quan sát B và xác định thiếu front/back-channel ở bước nào.
8. Thay principal bằng non-OIDC trong unit tests để quan sát fallback.
9. Thiết kế token revocation policy cho resource server dùng bearer token.
10. Viết checklist log redaction cho `id_token_hint`, `Authorization`, `Cookie`, `Location`.
11. Đề xuất UX khi OP không phản hồi; tách local logout đã thành công khỏi OP logout chưa xác nhận.
12. Mô tả “sign out everywhere” cần thêm session registry và thiết bị khác như thế nào.

## 15. Tài liệu tham khảo

- [Spring Security — Reactive OIDC Logout](https://docs.spring.io/spring-security/reference/reactive/oauth2/login/logout.html): local/RP-initiated/logout liên kết, class handler reactive, giới hạn back-channel.
- [Spring Security — Reactive OAuth2 Login](https://docs.spring.io/spring-security/reference/reactive/oauth2/login/core.html): client registration, OIDC scope, issuer-uri và callback.
- [Spring Security — Testing Reactive OAuth2/OIDC](https://docs.spring.io/spring-security/reference/reactive/test/web/oauth2.html): `mockOidcLogin()` trong `WebTestClient`.
- [Spring Security API 6.2 — OidcClientInitiatedServerLogoutSuccessHandler](https://docs.spring.io/spring-security/site/docs/6.2.8/api/org/springframework/security/oauth2/client/oidc/web/server/logout/OidcClientInitiatedServerLogoutSuccessHandler.html): repository reactive, redirect URI template, fallback.
- [OpenID Connect RP-Initiated Logout 1.0 Final](https://openid.net/specs/openid-connect-rpinitiated-1_0.html): `end_session_endpoint`, `id_token_hint`, `post_logout_redirect_uri`, `state` và URI matching.
- [OpenID Connect Front-Channel Logout](https://openid.net/specs/openid-connect-frontchannel-1_0.html): OP thông báo qua browser.
- [OpenID Connect Back-Channel Logout](https://openid.net/specs/openid-connect-backchannel-1_0.html): Logout Token gửi server-to-server.
- [OpenID Connect Discovery](https://openid.net/specs/openid-connect-discovery-1_0.html): OP discovery metadata.
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): thu hồi token khác với OIDC end-session.
- [Spring Security — Reactive CSRF](https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html): CSRF cho POST logout.

**Ghi nhớ:** **RP-Initiated Logout = local logout ở ứng dụng → redirect browser tới OP `end_session_endpoint` với `id_token_hint` và callback đã đăng ký**. Không được suy diễn **“đã redirect” = “OP đã logout” = “mọi RP đã logout” = “mọi token bị thu hồi”**. Kiểm thử từng ranh giới và diễn đạt đúng phạm vi.