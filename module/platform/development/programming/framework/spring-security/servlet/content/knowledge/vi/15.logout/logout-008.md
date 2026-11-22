# Phân biệt đăng xuất cục bộ, đăng xuất tại nhà cung cấp danh tính và thu hồi token

> **Phạm vi:** Spring Security 6 trên **Servlet stack**, Spring Boot 3.x, Java 17+. Ba hoạt động thường cùng được gọi là “logout” nhưng có ý nghĩa khác nhau: **local logout** hủy phiên xác thực tại ứng dụng; **IdP logout** nhắm đến phiên Single Sign-On (SSO) tại nhà cung cấp danh tính/OpenID Provider; **token revocation** làm credential OAuth2 bị thu hồi theo chính sách Authorization Server (AS). Bài này phân biệt rõ phạm vi, cơ chế, API, tác động lên phiên/cookie/token, ví dụ Java chạy được và kiểm thử.

## 1. Ba phạm vi logout: vì sao chỉ bấm một nút chưa đủ?

Một người dùng có thể đồng thời có những trạng thái sau:

- `HttpSession` tại **ứng dụng A** lưu `SecurityContext` / `Authentication`. Trình duyệt mang cookie phiên như `JSESSIONID`.
- Cookie **SSO của IdP/OpenID Provider** tại một origin riêng; khi ứng dụng A hoặc B chuyển đến trang đăng nhập IdP, cookie đó có thể giúp SSO mà không yêu cầu nhập lại mật khẩu.
- **OAuth2 access token** để gọi API/resource server; **refresh token** để xin access token mới; **ID token** để RP hiểu sự kiện xác thực OIDC.
- **Remember-me cookie** ở ứng dụng A, có thể khôi phục authentication sau khi session thông thường hết hiệu lực.
- Một `HttpSession` **khác tại ứng dụng B** cũng sử dụng IdP đó nhưng lưu phiên local riêng.

Xóa session ở A **không tự xóa** cookie SSO ở IdP, không tự hủy session B, và không làm một access token JWT đã phát hành mất chữ ký hay hết hạn.

```text
Browser / Client
    |
    +--> App A: JSESSIONID -> HttpSession -> SecurityContext
    |        |
    |        +-- Local logout: invalidate session, clear context
    |
    +--> IdP: SSO cookie -> phiên đăng nhập tại OP
    |        |
    |        +-- IdP logout: kết thúc SSO theo giao thức/hỗ trợ OP
    |
    +--> API: Authorization: Bearer <access-token>
             |
             +-- Token revocation: AS thay đổi trạng thái token/grant
                 (hiệu quả ở RS phụ thuộc loại token/cách validate)
```

**Quy tắc:** định nghĩa chính xác mục tiêu trước khi code. “Đăng xuất ứng dụng này”, “đăng xuất tài khoản SSO”, “đăng xuất mọi thiết bị”, “thu hồi refresh token” là những yêu cầu nghiệp vụ khác nhau.

| Cơ chế | State chính bị thay đổi | Ai xử lý? | Không tự bảo đảm |
| --- | --- | --- | --- |
| **Local logout** | `SecurityContext`, `HttpSession`, app cookie và local logout handlers | Spring Security tại ứng dụng | Không tự chấm dứt IdP SSO hoặc revoke OAuth2 token |
| **IdP/OP logout** | SSO session ở nhà cung cấp danh tính | IdP/OpenID Provider, có thể do RP khởi xướng | Không bảo đảm mọi RP đã hủy phiên local; không bảo đảm JWT đã phát hành mất hiệu lực ngay |
| **Token revocation** | Trạng thái token/grant tại Authorization Server | AS, theo request của client được quyền | Không tự xóa JSESSIONID, SSO cookie, hoặc local session các RP |

## 2. Local logout: Spring Security làm gì với phiên ứng dụng?

Trong ứng dụng Servlet dùng form login, Spring Security cung cấp `LogoutFilter` và các `LogoutHandler`. Khi nhận logout request phù hợp, có thể:

1. Dọn `Authentication`/`SecurityContext` hiện tại;
2. Invalidate `HttpSession` theo chính sách;
3. Xử lý remember-me cookie và persistent remember-me tokens khi đã cấu hình;
4. Yêu cầu xóa cookie ứng dụng và chạy thêm handlers được đăng ký;
5. Trả redirect hoặc response bằng `LogoutSuccessHandler`.

```text
POST /logout + session cookie + CSRF hợp lệ
    |
    v
LogoutFilter
    |
    +--> SecurityContextLogoutHandler
    |       clearAuthentication / clear SecurityContext
    |       invalidate HttpSession nếu bật
    |
    +--> RememberMeServices logout (nếu đã tích hợp)
    +--> Cookie clearing / custom LogoutHandler (nếu có)
    |
    v
LogoutSuccessHandler -> 302 /logged-out hoặc response phù hợp
```

### 2.1. Không chỉ clear SecurityContextHolder

`SecurityContextHolder` nắm context của request/thread hiện tại. Một controller tự gọi:

```java
SecurityContextHolder.clearContext();
```

**không tự đảm bảo session đã được invalidate**. Nếu context vẫn được lưu trong `HttpSessionSecurityContextRepository`, request sau có thể nạp lại authentication. Vì vậy nên dùng `http.logout(...)` và handlers chuẩn.

Đoạn minh họa khi cần triển khai handler riêng:

```java
SecurityContextLogoutHandler handler = new SecurityContextLogoutHandler();
handler.setInvalidateHttpSession(true);
handler.setClearAuthentication(true);
handler.logout(request, response, authentication);
```

Đây là fragment nằm trong code đã có `request`/`response`/`authentication`, không phải class độc lập. Không gọi lặp lại handler nếu `LogoutFilter` của Spring Security đã làm nhiệm vụ đó.

### 2.2. Xóa cookie và invalidation server-side khác nhau

Xóa `JSESSIONID` trong browser chỉ xóa bản sao **session identifier** ở client; nếu session cũ vẫn còn tồn tại server-side, ai đã lấy được ID cũ có thể vẫn dùng được. Local logout phải làm **session ID cũ không còn mang quyền truy cập**.

Ngược lại, invalidating session server-side mới là cơ chế chặn ID cũ, kể cả browser vẫn gửi ID đó thêm một lần. `deleteCookies("JSESSIONID")` hỗ trợ phía browser, nhưng cookie path/domain và container có thể ảnh hưởng việc xóa đúng cookie.

### 2.3. CSRF với logout

Khi CSRF protection đang bật, form-based logout thông thường là **`POST /logout` có CSRF token**. `GET /logout` có thể hiển thị trang xác nhận do Spring Security sinh ra nhưng không nên gây side effect logout tự động. Nếu cho logout qua GET không có bảo vệ, website khác có thể ép browser người dùng logout (*logout CSRF*).

Không tắt CSRF chỉ để dùng `curl -X POST /logout` không kèm token. Thay vào đó, cung cấp token hợp lệ và kiểm thử đúng hành vi.

### 2.4. Remember-me: lý do logout xong lại tự đăng nhập

Nếu ứng dụng có remember-me cookie dài hạn, hủy riêng `HttpSession` có thể vẫn để cookie remember-me còn giá trị. Ở request mới không có context, `RememberMeAuthenticationFilter` có thể khôi phục danh tính và user lại thấy mình đang đăng nhập.

Khi dùng `http.rememberMe(...)`, tích hợp logout handlers liên quan để xóa cookie/thu hồi persistent token theo policy. Với `PersistentTokenRepository.removeUserTokens(username)`, việc xóa mặc định theo username có thể ảnh hưởng **nhiều thiết bị**, khác ý nghĩa “logout riêng thiết bị này”. Đừng suy luận phạm vi nếu chưa kiểm tra repository/handler thực tế.

## 3. Khi đăng nhập OIDC: hai session độc lập

Ứng dụng dùng `oauth2Login()` có thể đăng nhập qua một OpenID Provider (OP). Luồng authorization code diễn ra ở IdP, rồi ứng dụng tạo **local authentication/session**. Đồng thời OP giữ **SSO session** của browser.

```text
Browser                App A (Relying Party)          Identity Provider
   |                           |                           |
   | GET /private              |                           |
   |-------------------------->|                           |
   |<---- redirect tới IdP ----|                           |
   |---------------------- trang/login SSO ---------------->|
   |<----- authorization code / redirect -------------------|
   |------ callback ---------->|                           |
   |                           |-- exchange code/token ---->|
   |                           |<----- ID/access tokens ----|
   |<----- JSESSIONID ---------|                           |
   |                           |                     SSO cookie có thể còn
```

Khi app A chỉ invalidate `JSESSIONID`, nó **không thể trực tiếp xóa cookie thuộc domain IdP**. User quay lại login của A có thể được IdP xác thực ngay dựa trên SSO session còn hiệu lực. Điều này không nhất thiết là lỗi local logout.

**Ba loại dữ liệu cần phân biệt:**

- **ID token:** OIDC cung cấp thông tin authentication cho RP; không phải access token để gọi API.
- **Access token:** dùng ở resource server với scope/audience được cấp.
- **Refresh token:** client dùng ở AS để xin access token mới; không phải HTTP session cookie.

Xóa local app session cũng không tự xóa những token này nếu chúng còn trong client-side hay server-side storage.

## 4. Đăng xuất IdP/OpenID Provider: RP-Initiated Logout

OIDC hỗ trợ mô hình **RP-Initiated Logout** khi provider triển khai endpoint liên quan. RP yêu cầu OP chấm dứt phiên SSO, thường bằng browser redirect tới `end_session_endpoint` từ metadata.

```text
User chọn "Đăng xuất khỏi SSO"
    |
    v
POST /logout tại RP (CSRF hợp lệ)
    |
    +--> LogoutFilter/LogoutHandlers dọn local session
    |
    v
OidcClientInitiatedLogoutSuccessHandler
    |
    +--> tìm đúng OIDC ClientRegistration / metadata
    +--> xây redirect tới OP end_session_endpoint
    |
    v
Browser -> OP xử lý logout SSO
    |
    +--> OP có thể yêu cầu xác nhận / id_token_hint
    |
    v
OP -> post_logout_redirect_uri đã cho phép
```

Các tham số OIDC thường gặp:

- `id_token_hint`: ID token được RP cung cấp để gợi ý user/phiên/client cho OP.
- `post_logout_redirect_uri`: nơi OP có thể đưa user quay về; thường phải đăng ký/allowlist.
- `state`: giá trị tương quan giữa request và redirect, khi flow/provider sử dụng.

**Không tự đoán** endpoint logout bằng cách nối chuỗi `issuer + "/logout"`: IdP khác nhau có endpoint/metadata/requirements khác nhau. Cũng không nhận redirect URI tùy tiện từ query string nếu có thể gây **open redirect**.

### 4.1. RP-initiated logout có phải global logout?

Không. Có ít nhất ba cơ chế liên quan:

| Cơ chế | Luồng | Mục đích |
| --- | --- | --- |
| **RP-Initiated Logout** | RP yêu cầu OP logout | Kết thúc SSO session tại OP theo khả năng của OP |
| **Front-Channel Logout** | OP điều phối thông báo qua browser đến RPs | RPs tham gia có thể dọn local sessions theo giao thức |
| **Back-Channel Logout** | OP gửi logout notification server-to-server cho RP | RP xác thực thông báo và thu hồi sessions tương ứng |

Không có quy tắc rằng tất cả ứng dụng dùng chung IdP đều tự nhận được thông báo logout. Nếu ứng dụng B còn `HttpSession` mà không hỗ trợ front/back-channel logout, B có thể tiếp tục cho phép request dù OP SSO đã kết thúc.

**“Đăng xuất mọi ứng dụng” là một yêu cầu tích hợp SLO end-to-end**, không phải hành vi mặc định của một lời gọi `http.logout()`.

## 5. Spring Security cấu hình OIDC logout ra sao?

Trong project Spring Boot Servlet có các dependencies:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
}
```

Đây là đoạn trong `build.gradle`; cần có plugin/repositories của project. Ví dụ cấu hình Java:

```java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.client.oidc.web.logout.OidcClientInitiatedLogoutSuccessHandler;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class OidcLogoutConfig {

    @Bean
    OidcClientInitiatedLogoutSuccessHandler oidcLogoutSuccessHandler(
            ClientRegistrationRepository registrations) {

        OidcClientInitiatedLogoutSuccessHandler handler =
                new OidcClientInitiatedLogoutSuccessHandler(registrations);
        handler.setPostLogoutRedirectUri("{baseUrl}/");
        return handler;
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            OidcClientInitiatedLogoutSuccessHandler oidcLogout)
            throws Exception {

        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/").permitAll()
                .anyRequest().authenticated());

        http.oauth2Login(Customizer.withDefaults());

        http.logout(logout -> logout
                .logoutSuccessHandler(oidcLogout));

        return http.build();
    }
}
```

`OidcClientInitiatedLogoutSuccessHandler` tìm metadata của provider qua `ClientRegistrationRepository` và xây redirect khi OP hỗ trợ. `{baseUrl}` là placeholder do Spring xử lý để xây post-logout URI của ứng dụng, không phải URL có thể tự do lấy từ user.

Ví dụ `application.yml` **chỉ có giá trị minh họa**, không phải IdP chạy thực tế:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corp:
            client-id: replace-with-client-id
            client-secret: from-secure-secret-manager
            scope: openid, profile
        provider:
          corp:
            issuer-uri: https://idp.example.com/realms/example
```

Để chạy E2E cần đăng ký client thật, redirect URI cho login, post-logout redirect URI tại IdP, client authentication phù hợp và provider có `end_session_endpoint`. Không thể coi fragment này là **dự án độc lập chạy được mà không cần IdP**.

### Cần kiểm thử gì?

1. `POST /logout` hợp lệ làm local session không còn authentication.
2. Handler đưa browser tới **đúng OP** của user đã login.
3. `post_logout_redirect_uri` được allowlist và không nhận open redirect.
4. OP kết thúc SSO theo chính sách thực, hoặc UI trình bày rõ nếu OP không hỗ trợ.
5. RP khác có nhận/triển khai logout notification không nếu sản phẩm hứa hẹn SLO.
6. Multi-tenant/multiple registration không redirect nhầm IdP.
7. Trường hợp IdP unreachable, RP vẫn dọn local session và không nói “global logout thành công” khi chưa chứng minh.
8. Không làm lộ ID token/token hint trong application logs hoặc hệ thống analytics.

## 6. Token revocation theo OAuth2 RFC 7009

**Thu hồi token** nghĩa là yêu cầu **Authorization Server** không còn cho phép token được sử dụng theo chính sách của AS. RFC 7009 định nghĩa token revocation endpoint; khả năng revoke access và refresh token phụ thuộc AS/provider.

### 6.1. Xóa token ở client KHÁC revoke ở AS

- **Remove local token:** ứng dụng xóa access/refresh token khỏi local cache hoặc repository. AS chưa chắc biết.
- **Revoke tại AS:** client được phép gửi HTTP request tới revocation endpoint của AS; AS cập nhật trạng thái token/grant theo hợp đồng.
- **RS từ chối token:** phụ thuộc resource server có kiểm tra trạng thái revocation (opaque introspection/denylist/validation online), hay chỉ kiểm chữ ký JWT offline.

```text
Client storage: access_token T, refresh_token R
    |
    +--> xóa bản lưu T/R: chỉ tác động client storage
    |
    +--> RFC7009 revoke(R) tại AS:
    |       R không thể xin token mới theo policy
    |       T đã phát hành có thể chưa hết hạn
    |
    +--> revoke(T) tại AS:
            hiệu lực khi RS kiểm tra hoặc có dữ liệu revoke phù hợp
```

### 6.2. Request thu hồi token

Ví dụ HTTP, **endpoint chỉ minh họa**:

```http
POST /oauth2/revoke HTTP/1.1
Host: idp.example.com
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <base64(client-id:client-secret)>

token=<refresh-token>&token_type_hint=refresh_token
```

`token` chứa token cần thu hồi; `token_type_hint` (nếu hỗ trợ) có thể là `refresh_token` hoặc `access_token`. Cơ chế client authentication tùy AS, ví dụ `client_secret_basic` hoặc một phương thức khác. Không mọi public client đều có client secret.

Lệnh shell **chỉ là mẫu, không chạy nguyên placeholder**:

```bash
curl --request POST \
  'https://idp.example.com/oauth2/revoke' \
  --user "$CLIENT_ID:$CLIENT_SECRET" \
  --data-urlencode "token=$REFRESH_TOKEN" \
  --data-urlencode 'token_type_hint=refresh_token'
```

Đừng chép secret thật vào tài liệu hoặc shell history; sử dụng cơ chế secret management phù hợp, kết nối HTTPS và log redaction.

### 6.3. HTTP 200 của revoke nói gì?

Theo mục tiêu tránh dò xem token có tồn tại không, revocation endpoint có thể trả success ngay cả khi token đã không hợp lệ hoặc không được tìm thấy. Vì vậy **HTTP 200 không chứng minh token trước đó tồn tại** và không chứng minh mọi resource server đã từ chối access token liên quan.

Kiểm thử phải gồm bước **thử refresh lại** và bước **gọi API bằng access token cũ** trong đúng architecture, không chỉ assert status của request revoke.

### 6.4. Vì sao access JWT cũ có thể vẫn chạy?

JWT self-contained có chữ ký và `exp`. Resource server có thể chỉ verify chữ ký, `iss`, `aud`, `exp` và authorities **offline** mà không hỏi AS mỗi request. Một request RFC7009 không tự thay bytes/chữ ký của access JWT đã phát hành.

Các phương án để hạn chế hiệu lực sau logout:

- Access token **TTL ngắn**, refresh token được bảo vệ, rotate và revoke.
- Reference/opaque token với **introspection** nếu RS cần biết trạng thái active hiện tại; quản lý cache.
- Denylist theo `jti` hoặc token ID được đồng bộ đến resource servers; có TTL đến khi JWT hết hạn.
- Tùy AS, revoke grants/sessions liên quan hoặc xử lý back-channel logout.
- Rotation signing key chỉ cho tình huống khẩn cấp/có kiểm soát, có ảnh hưởng diện rộng, không phải giải pháp logout từng user.

**Không khẳng định** revoke refresh token làm mọi access token bị từ chối lập tức. Hành vi phụ thuộc AS, token type và cơ chế RS validation.

### 6.5. ID token không phải access token

Trong OIDC, **ID token** cung cấp thông tin authentication cho RP và có thể được dùng làm `id_token_hint` khi RP-initiated logout. Nó **không** phải access token để gọi API và không tự động là đối tượng của mọi token revocation endpoint. Không thay chuỗi access token bằng ID token trong HTTP Authorization header.

## 7. OAuth2AuthorizedClientService chỉ quản lý bản lưu local

Trong Spring Security OAuth2 Client, `OAuth2AuthorizedClient` có thể giữ access và refresh token gắn với `ClientRegistration` và principal. Cách xóa bản lưu local có thể là:

```java
// Fragment bên trong một service có biến và dependency tương ứng.
authorizedClientService.removeAuthorizedClient(
        clientRegistrationId, principalName);
```

`OAuth2AuthorizedClientService.removeAuthorizedClient(...)` **không mặc định** gọi RFC 7009 revocation endpoint. `OAuth2AuthorizedClientRepository.removeAuthorizedClient(...)` cũng thuộc cơ chế local storage theo request/principal; không tự chứng minh AS đã thu hồi token.

Một flow cần local logout **và** revoke remote phải chủ động:

1. Xác định authorized client thực sự thuộc principal hiện tại, không tin token/registration tùy ý từ query string.
2. Lấy refresh token từ **storage server-side** trước khi xóa, không gửi giá trị ra frontend.
3. Gọi revocation endpoint đúng AS với client authentication/timeout/error handling phù hợp.
4. Xóa local authorized client và invalidate session/cookie theo chính sách.
5. Nếu có OIDC SSO logout, thực hiện browser redirect tới OP theo hợp đồng riêng.
6. Ghi nhận partial success/timeout và thiết kế retry/incident process khi cần.

Đây là **quy trình kiến trúc**, không phải một phương thức duy nhất của `http.logout()`. Nếu remote revocation lỗi, vẫn phải đảm bảo user không tiếp tục có local authentication có quyền chỉ vì network lỗi; nhưng UI không được tuyên bố “đã revoke mọi token” khi chưa thực hiện được.

### Resource Server có tự revoke JWT không?

Ứng dụng chỉ cấu hình `http.oauth2ResourceServer(oauth2 -> oauth2.jwt(...))` là **resource server**. Nó không tự trở thành Authorization Server và không có khả năng làm một access JWT ngoại phát mất chữ ký hoặc hết hạn. Cần phối hợp AS hoặc áp dụng denylist/introspection theo security architecture.

`SecurityContextHolder.clearContext()` của một request stateless không cấm client gửi lại JWT hợp lệ ở request kế tiếp.

## 8. Dự án Spring Boot chạy được: kiểm chứng local logout

Ví dụ Java 17 / Spring Boot **3.3.5** / Spring Security 6 / Gradle 8.5 minh họa **đúng một phạm vi**: form login/session ở ứng dụng và local logout. Không có external IdP hoặc OAuth2 Authorization Server, nên bài kiểm thử sẽ **không** giả nhận đã chứng minh SSO logout hay token revocation.

### 8.1. Tổ chức project

```text
local-logout-demo/
  settings.gradle
  build.gradle
  src/main/java/demo/
    DemoApplication.java
    SecurityConfig.java
    DemoController.java
  src/test/java/demo/
    LocalLogoutTest.java
```

Tệp `settings.gradle`:

```groovy
rootProject.name = 'local-logout-demo'
```

Tệp `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
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
```

### 8.2. Main application

`src/main/java/demo/DemoApplication.java`:

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

### 8.3. SecurityConfig

`src/main/java/demo/SecurityConfig.java`:

```java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails learner = User.withUsername("learner")
                .password(encoder.encode("study123"))
                .roles("USER")
                .build();
        return new InMemoryUserDetailsManager(learner);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/logged-out").permitAll()
                .anyRequest().authenticated());

        http.formLogin(form -> form
                .defaultSuccessUrl("/me", true)
                .permitAll());

        http.logout(logout -> logout
                .logoutUrl("/logout")
                .logoutSuccessUrl("/logged-out")
                .invalidateHttpSession(true)
                .clearAuthentication(true)
                .deleteCookies("JSESSIONID"));

        // CSRF được giữ bật. Logout và login bằng POST cần CSRF token.
        return http.build();
    }
}
```

Cấu hình không dùng `csrf.disable()`, không tự viết endpoint logout. `LogoutFilter` của Spring Security được nối vào filter chain; sau logout, session đã invalidate và local Authentication bị dọn.

`deleteCookies("JSESSIONID")` giúp browser bỏ cookie, nhưng an toàn vẫn cần session ID cũ không còn được server chấp nhận. Với cookie name/path/domain tùy biến, điều chỉnh cookie clearing policy đúng môi trường. Mật khẩu demo được hash BCrypt; không hard-code tài khoản production.

### 8.4. DemoController

`src/main/java/demo/DemoController.java`:

```java
package demo;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/")
    public String home() {
        return "public";
    }

    @GetMapping("/me")
    public String me(Authentication authentication) {
        return authentication.getName();
    }

    @GetMapping("/logged-out")
    public String loggedOut() {
        return "logged-out";
    }
}
```

### 8.5. MockMvc: session trước/sau logout

`src/test/java/demo/LocalLogoutTest.java`:

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class LocalLogoutTest {

    @Autowired
    MockMvc mvc;

    private MockHttpSession login() throws Exception {
        MockHttpSession session = new MockHttpSession();

        mvc.perform(post("/login")
                        .session(session)
                        .with(csrf())
                        .param("username", "learner")
                        .param("password", "study123"))
                .andExpect(status().is3xxRedirection());

        return session;
    }

    @Test
    void publicEndpointIsAvailable() throws Exception {
        mvc.perform(get("/"))
                .andExpect(status().isOk())
                .andExpect(content().string("public"));
    }

    @Test
    void anonymousRequestRequiresLogin() throws Exception {
        mvc.perform(get("/me"))
                .andExpect(status().is3xxRedirection());
    }

    @Test
    void loggedInSessionAccessesProtectedEndpoint() throws Exception {
        MockHttpSession session = login();
        mvc.perform(get("/me").session(session))
                .andExpect(status().isOk())
                .andExpect(content().string("learner"));
    }

    @Test
    void logoutRequiresCsrfAndInvalidatesSession() throws Exception {
        MockHttpSession session = login();

        mvc.perform(post("/logout").session(session))
                .andExpect(status().isForbidden());

        // Thiếu CSRF: logout chưa xảy ra.
        mvc.perform(get("/me").session(session))
                .andExpect(status().isOk())
                .andExpect(content().string("learner"));

        mvc.perform(post("/logout")
                        .session(session)
                        .with(csrf()))
                .andExpect(status().is3xxRedirection())
                .andExpect(redirectedUrl("/logged-out"));

        assertTrue(session.isInvalid());

        // Request mới không mang session hợp lệ.
        mvc.perform(get("/me"))
                .andExpect(status().is3xxRedirection());

        mvc.perform(get("/logged-out"))
                .andExpect(status().isOk())
                .andExpect(content().string("logged-out"));
    }
}
```

**Kết quả kỳ vọng:** 4 test PASS theo dependencies/cấu hình demo. Test dùng form login thật qua MockMvc, không dùng `@WithMockUser` vì annotation có thể tạo sẵn Authentication và làm mất ý nghĩa kiểm thử session lifecycle. `MockHttpSession.isInvalid()` xác minh session đã được invalidate; sau đó test request mới không tái dùng session object đã invalid.

### 8.6. Chạy và quan sát

Với JDK 17+ và Gradle tương thích:

```bash
gradle test
gradle bootRun
```

Nếu có Gradle Wrapper: dùng `./gradlew test`/`./gradlew bootRun` (macOS/Linux), `.\gradlew.bat test`/`.\gradlew.bat bootRun` (Windows).

Trong browser tại `http://localhost:8080`:

1. `GET /me` khi chưa login → redirect đến trang login.
2. Login `learner` / `study123` → `GET /me` trả `learner`.
3. Đi tới `/logout` và gửi POST qua form xác nhận có CSRF token, không dùng GET logout tùy tiện.
4. Sau logout `/logged-out` trả `logged-out`, request `/me` mới lại cần authentication.
5. Không công khai session cookie thực trong screenshot/log.

HTTP localhost chỉ dành cho thực hành. Production cần HTTPS, cookie `Secure`, `HttpOnly`, `SameSite` phù hợp, session timeout/revocation và chính sách CSRF.

**Giới hạn:** chương trình này không gọi OP `end_session_endpoint` và không gọi OAuth2 revocation endpoint. Muốn test SSO/token revocation phải tích hợp IdP/AS/RS thực hoặc test doubles có hợp đồng rõ ràng.

## 9. Kết hợp local logout, OP logout và token revocation trong một sản phẩm

Nếu ứng dụng vừa có local session, OIDC login và refresh token trong server-side `OAuth2AuthorizedClientService`, một flow “logout đầy đủ” có thể cần orchestration:

```text
POST /logout + CSRF
    |
    +--> nhận dạng user/client/authorized-client từ trusted server state
    |
    +--> lưu dữ liệu cần thiết để gọi revocation/OP logout an toàn
    |
    +--> invalidating local session + clear Authentication/remember-me
    |
    +--> gọi RFC7009 revoke refresh token (nếu policy cần và AS hỗ trợ)
    |        |
    |        +--> theo dõi success/error/timeout, không lộ secret
    |
    +--> redirect browser tới OP end_session_endpoint nếu hỗ trợ
    |
    +--> post-logout redirect về ứng dụng
    |
    +--> UI trình bày chính xác phạm vi đã hoàn thành
```

Thứ tự chính xác phụ thuộc framework hooks và threat model. Đặc biệt nếu cần `OidcUser` hay `id_token_hint`, phải lấy thông tin đáng tin từ authentication **trước khi nó bị dọn** hoặc dựa vào parameter authentication được handler chuẩn cung cấp. Không lấy token hint từ input client không đáng tin.

Nếu remote revoke hoặc OP logout lỗi, **không giữ local session có quyền** chỉ vì network hỏng. Đồng thời không ghi rằng “đã đăng xuất trên mọi thiết bị” nếu chỉ chắc chắn local session đã bị hủy; ghi nhận partial failure và xử lý theo policy.

### 9.1. “Đăng xuất thiết bị này”

Thường cần hủy session hiện tại, xóa remember-me credential của thiết bị (nếu kiến trúc hỗ trợ phạm vi riêng), xóa token cache local và có thể revoke refresh token thuộc thiết bị. Không nhất thiết hủy SSO ở IdP hoặc session của các thiết bị khác.

### 9.2. “Đăng xuất khỏi SSO”

Cần OP logout nếu hỗ trợ, đồng thời hủy local session của RP hiện tại. Các RP khác chỉ bị ảnh hưởng khi có front/back-channel logout hoặc cơ chế tập trung tương đương. Access JWT có thể vẫn còn hiệu lực nếu không có RS revoke check.

### 9.3. “Đăng xuất mọi thiết bị”

Cần nhận diện toàn bộ sessions, remember-me series, OAuth2 grants/tokens của user, quản lý revocation đồng bộ trên nhiều hệ thống, và khả năng IdP terminate sessions theo provider policy. Một request `POST /logout` mặc định tại ứng dụng A **không thể** tự invalidate `HttpSession` của app B.

## 10. Troubleshooting: logout xong nhưng vẫn dùng được hệ thống

| Hiện tượng | Giải thích có thể | Điều cần kiểm tra |
| --- | --- | --- |
| `GET /me` redirect `/login` sau logout | Local logout đã hủy authentication phiên | Session ID cũ không còn quyền; CSRF/handler đúng |
| Login lại qua OIDC mà không cần password | IdP SSO session còn | Có triển khai RP-Initiated Logout không? OP có hỗ trợ? |
| App B vẫn authenticated | App B giữ local session | Có front/back-channel logout, session mapping và test không? |
| API vẫn nhận Bearer JWT cũ | JWT được verify offline, chưa expire | TTL, denylist, introspection, AS policy |
| Refresh token vẫn xin token mới được | Chưa revoke grant/token đúng AS | Request RFC7009, client authentication, refresh test |
| Browser tự nhớ login lại | Remember-me cookie/token còn | LogoutHandler/repository cleanup |
| `POST /logout` trả 403 | Thiếu CSRF token | Giữ CSRF, gửi token đúng |
| GET logout không đổi trạng thái | CSRF đang bảo vệ logout bằng POST | Dùng form POST hoặc API có CSRF thích hợp |
| `removeAuthorizedClient` rồi JWT vẫn chạy | Chỉ xóa local storage | Revoke/RS validation là cơ chế khác |
| Revocation HTTP 200 nhưng RS vẫn nhận token | HTTP 200 không chứng minh RS biết revoke | Thử token cũ với API thật, kiểm tra loại token |
| IdP logout URL sai/không redirect về | Endpoint/URI chưa allowlist | Đọc metadata, client registration, provider support |
| Local logout thành công nhưng backend remote timeout | Partial failure | Local fail closed, telemetry/retry và UI trung thực |

Đừng bật logging chứa `Authorization`, cookie, session ID, refresh token hoặc ID token để tìm lỗi; đó là những credentials có thể bị sử dụng lại. Quan sát qua event IDs/metrics/correlation IDs không chứa secret.

## 11. Checklist bảo mật và test E2E

- **Scope:** product label giải thích rõ local/IdP/token/global logout.
- **Local session:** `HttpSession` invalidated, `SecurityContext` không được nạp lại từ cookie cũ.
- **Cookie:** clearing đúng path/domain và flags; server-side invalidation là căn cứ chính.
- **CSRF:** request POST logout thiếu token bị chặn, có token hoạt động.
- **Remember-me:** không tự auto-login trái policy từ cookie còn lại.
- **OIDC:** OP `end_session_endpoint` được hỗ trợ, post-logout redirect allowlisted, đúng client/issuer.
- **SLO:** nếu cam kết global SSO, RP khác nhận/xác minh front/back-channel logout notifications.
- **OAuth2 client local cache:** loại bỏ authorized-client record theo policy, không nhầm nó với remote revoke.
- **Refresh token:** gửi revocation request được xác thực tại AS khi cần; kiểm thử refresh thất bại.
- **Access token:** kiểm tra RS có xử lý revocation hay JWT có TTL ngắn phù hợp.
- **ID token:** không đem dùng gọi API hoặc mặc định revoke như access token.
- **Logout-all:** session registry, remembered devices và grants có cơ chế thu hồi thực sự.
- **Remote errors:** timeout/retry/partial success được quan sát, local session luôn được xử lý an toàn.
- **Security:** TLS, CSRF, cookie security, secret storage, tránh open redirect và token trong logs.
- **Đa SecurityFilterChain:** xác nhận endpoint logout thuộc đúng chain/registration.
- **Kết quả:** không chỉ assert status 302; kiểm tra mỗi state ở hệ thống chịu trách nhiệm.

## 12. Câu hỏi tự kiểm tra

1. **Local logout có xóa cookie của IdP không?** Không. RP không tự xóa cookie thuộc origin của OP.
2. **Tại sao logout rồi login OIDC vẫn không cần password?** Có thể local session đã mất nhưng SSO session của OP vẫn hợp lệ.
3. **RP-Initiated Logout có tự logout các RPs khác không?** Không bảo đảm; cần OP và các RP hỗ trợ cơ chế liên quan.
4. **`removeAuthorizedClient` có gọi RFC7009 không?** Không mặc định; nó xóa authorized-client record ở phía ứng dụng.
5. **Revoke refresh token có làm JWT access token đã cấp lập tức bị từ chối không?** Không được giả định.
6. **ID token là gì?** Token OIDC cho RP hiểu thông tin authentication, không phải bearer access token dùng trực tiếp gọi API.
7. **Vì sao revocation endpoint có thể trả 200 với token không tồn tại?** Để tránh tiết lộ token tồn tại; status không đủ chứng minh RS đã đồng bộ.
8. **Xóa JSESSIONID trong frontend đủ logout chưa?** Chưa; phải invalidating session/authentication server-side.
9. **Remember-me có làm user tự login trở lại không?** Có thể nếu chỉ xóa session và để remember-me cookie/token hợp lệ.
10. **POST logout cần CSRF vì sao?** Browser tự đính kèm cookie, nên request bị kích hoạt từ origin khác có thể gây side effect.
11. **OAuth2 Resource Server có tự revoke JWT của IdP không?** Không; cần AS/RS policy riêng.
12. **Logout tất cả thiết bị cần gì?** Thu hồi mọi sessions/tokens/grants phù hợp, không chỉ một local `HttpSession`.

**Ghi nhớ:** **Local logout** kết thúc phiên và `SecurityContext` của ứng dụng; **IdP logout** nhắm tới SSO session tại OpenID Provider theo giao thức được hỗ trợ; **OAuth2 token revocation** thay đổi khả năng sử dụng token tại AS, nhưng không mặc nhiên vô hiệu hóa mọi access JWT đang tồn tại. Đây là **ba hợp đồng riêng**, cần triển khai, quan sát và kiểm thử độc lập. Khi kết hợp, hãy bảo đảm local session fail closed, không lộ credentials, và mô tả kết quả đúng phạm vi.
