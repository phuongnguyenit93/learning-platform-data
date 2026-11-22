# Chọn mô hình xác thực theo loại client và yêu cầu của sản phẩm

> **Phạm vi:** Thiết kế cơ chế xác thực trong ứng dụng Spring Security dùng Java 17+ và Spring Boot 3.x. Quyết định cần dựa trên loại client, nơi có thể giữ bí mật, trải nghiệm sản phẩm, khả năng cấp/thu hồi quyền và nhu cầu vận hành. Những phương án session, OIDC, BFF, Resource Server và machine-to-machine dưới đây là **các mô hình để lựa chọn**, không phải các cấu hình phải bật cùng lúc.

## 1. Bài toán: nhiều client, nhiều ranh giới tin cậy

Một hệ thống có portal nhân viên, SPA khách hàng, ứng dụng iOS/Android và job chạy lúc nửa đêm. Nếu bắt tất cả dùng cùng một JWT dài hạn hoặc một tài khoản/password chung, hệ thống sẽ gặp các vấn đề khác nhau: browser có nguy cơ lộ token khi XSS; mobile không thể giữ client secret dùng chung; job không có danh tính người dùng cuối; logout và thu hồi quyền trở nên khó dự đoán.

Trước khi chọn công nghệ, phải trả lời:

1. **Ai gửi request?** Người dùng tương tác, ứng dụng/đối tác hay tác vụ tự động?
2. **Client chạy ở đâu?** Server-rendered web, SPA trong browser, native mobile, desktop, CLI, thiết bị thiếu bàn phím, server hoặc webhook?
3. **Ai giữ được bí mật?** Chỉ backend được team kiểm soát mới có thể bảo vệ client secret/private key. JavaScript trong browser và binary mobile phân phối cho người dùng đều là môi trường **public client**.
4. **Ai quản lý danh tính?** Account local hay IdP có OIDC, SSO, MFA, passkeys, account recovery và deprovisioning?
5. **API được gọi từ đâu?** Cùng origin/browser cookie, browser gọi API trực tiếp, mobile Bearer token hay server-to-server?
6. **Dữ liệu có nhạy cảm không?** Có role, owner/tenant, audit, thao tác tiền bạc, yêu cầu kiểm MFA mới, hoặc thời gian thu hồi quyền rất ngắn?
7. **Vận hành cần gì?** Session store, SSO logout, revocation, rotation, token introspection, IdP outage, scale và latency?

**Quyết định có cơ sở:** “Portal nội bộ chạy web cùng origin, cần SSO/MFA, chọn OIDC Login + server-side session, cookie an toàn, CSRF và kiểm quyền dữ liệu.” **Quyết định thiếu cơ sở:** “API REST nên nhất định phải JWT.”

## 2. Thuật ngữ bắt buộc phân biệt

| Khái niệm | Công dụng | Không được nhầm |
| --- | --- | --- |
| Authentication | Xác minh chủ thể là ai. | Được xem mọi tài nguyên. |
| Authorization | Quyết định hành động/tài nguyên nào được phép. | Chỉ kiểm `authenticated()`. |
| HTTP session | Trạng thái đăng nhập phía server; browser thường gửi session ID trong cookie. | JWT tự chứa claims. |
| Cookie | Dữ liệu trình duyệt tự gửi theo domain/site/path policy. | Quyền truy cập được xác minh. |
| OAuth 2.0 | Khung **ủy quyền** để client nhận access token gọi protected resource. | Chuẩn login danh tính người dùng đầy đủ. |
| OpenID Connect (OIDC) | Lớp danh tính/login trên OAuth2 với ID token và identity claims. | Access token gọi API. |
| Access token | Credential gọi Resource Server cho đúng audience/scope. | ID token cấp cho OAuth client. |
| ID token | Bằng chứng OIDC xác thực danh tính để client xử lý đăng nhập. | Credential thay access token gửi tới mọi API. |
| Refresh token | Credential đổi lấy access token mới theo chính sách grant. | Dữ liệu được phép lưu tùy tiện trong JavaScript/localStorage. |
| JWT | Định dạng token có claims, thường ký số để resource server kiểm. | Bản thân một mô hình login hoặc giải pháp revocation. |
| Opaque token | Token không cần được API hiểu trực tiếp, thường dùng introspection. | Mặc định kém an toàn hơn JWT. |
| Role / authority / scope | Cách biểu diễn quyền chức năng. | Quyền sở hữu bản ghi/thuộc tổ chức. |

Ví dụ: user đã xác thực, có `SCOPE_orders.read`, nhưng order ID 42 thuộc tenant khác. Scope đó **không tự** chứng minh user được xem order 42. Backend phải kiểm membership/owner, dùng query có `owner_user_id` hoặc `authorized_org_id`.

Một ứng dụng đóng vai **OAuth2 Client** khi đưa user đến IdP hoặc xin token; nó đóng vai **Resource Server** khi nhận và xác minh Bearer token cho API. Spring Security Resource Server không tự tạo màn hình login, và chỉ thêm OAuth2 Client cũng không khiến backend tự phát hành token.

## 3. Ma trận lựa chọn nhanh

| Loại client | Mô hình nên cân nhắc đầu tiên | Credential client giữ | Điều kiện an toàn |
| --- | --- | --- | --- |
| Web server-rendered cùng origin | Session cookie + form login hoặc OIDC Login. | Session ID trong cookie. | HttpOnly, Secure, SameSite, CSRF, session timeout, logout, chống session fixation. |
| SPA có backend riêng do team kiểm soát | **Backend for Frontend (BFF)** + OIDC. | Browser chỉ có session cookie; BFF giữ token phía server. | CSRF, XSS, server-side token storage, proxy có quyền và session lifecycle. |
| SPA thuần browser gọi API trực tiếp | OAuth/OIDC **Authorization Code + PKCE**. | Bearer access token theo chính sách lưu trữ ngắn hạn. | Public client, PKCE S256, state/nonce, redirect URI, XSS, CORS. |
| Native iOS/Android | Authorization Code + PKCE qua **system browser**. | Access/refresh token trong OS secure storage. | Không nhúng client secret, token rotation/revocation, bảo vệ redirect. |
| Desktop/CLI có browser | Authorization Code + PKCE qua browser/loopback. | Token cache bảo vệ theo nền tảng. | Redirect, PKCE, local storage và logout. |
| TV/thiết bị khó nhập mật khẩu | Device Authorization Grant nếu IdP hỗ trợ. | Device code tạm, token sau xác nhận. | Mã hết hạn, polling/rate limit, chống phishing. |
| Job/service không có user cuối | Client Credentials hoặc workload identity. | Secret/private key/mTLS chỉ trên server. | Least privilege, scope, audience, rotation, audit. |
| Partner/mobile API nhận Bearer token | OAuth2 Resource Server với JWT hoặc opaque token. | `Authorization: Bearer` qua HTTPS. | Issuer/audience/expiry/signature hoặc introspection, permissions, tenant. |
| Webhook inbound | HMAC/public-key signature/mTLS theo contract. | Signature request, không phải browser session. | Timestamp/nonce, replay defense, idempotency. |

Đây là **điểm khởi đầu**, không phải luật tuyệt đối. Một sản phẩm hoàn toàn có thể dùng session cho portal, OIDC + PKCE cho mobile, Bearer token cho API và Client Credentials cho backend job. Mỗi đường phải có chính sách `SecurityFilterChain`, dữ liệu và test riêng.

## 4. Bước một: xác định actor và public/confidential client

**Người dùng cuối** cần một quá trình login (local, SSO hoặc OIDC), thời gian phiên, policy MFA/recovery và quyền theo từng tài nguyên. **Máy** cần workload identity riêng; không được mượn password của tài khoản nhân viên rồi gọi job là “user”.

**Public client** (SPA/native app) không thể bảo vệ shared client secret. Việc biên dịch APK hay minify JS không biến mã đó thành nơi giữ secret tin cậy. **Confidential client** là server team quản lý, có thể dùng secret manager, private key, mTLS và client authentication đáng tin cậy.

Với OAuth2 Authorization Code Grant, public client dùng **PKCE S256**. Không dùng Implicit Grant hoặc Resource Owner Password Credentials Grant cho thiết kế mới: OAuth2 Security Best Current Practice RFC 9700 nêu rõ nguy cơ token/credential leakage và yêu cầu bảo vệ authorization code. Với OIDC, cần xử lý `state`, `nonce`, issuer, audience và redirect URI theo provider/library.

## 5. Bước hai: chọn nơi giữ trạng thái đăng nhập và access token

### 5.1. Session + cookie cho web cùng origin

Luồng cơ bản:

```text
Browser                    Spring Boot server
  | GET /me                       |
  |------------------------------>|
  |<---------- 302 /login --------|
  | POST /login + CSRF token      |
  |------------------------------>|
  |   xác minh username/password  |
  |<---- Set-Cookie: JSESSIONID --|
  | GET /me + session cookie      |
  |------------------------------>|
  |<------------- 200 ------------|
```

Session ID **chỉ tham chiếu** trạng thái server-side, không chứa password. Ưu điểm là đơn giản cho sản phẩm một backend, logout và invalidation dễ mô hình hóa; không cần cho browser JS giữ Bearer token. Đánh đổi là phải quản lý session store, idle timeout, clustering, cookie policy và CSRF.

**Cookie production:** `HttpOnly` giúp JS không đọc trực tiếp cookie, nhưng XSS vẫn có thể gọi API bằng session; `Secure` yêu cầu TLS; `SameSite` điều chỉnh browser cross-site behavior và phải phù hợp với OIDC redirect. `SameSite` **không thay toàn bộ** CSRF protection. Với cookie-authenticated POST/PUT/PATCH/DELETE, phải có CSRF token/cơ chế phòng CSRF phù hợp.

**Khi chọn:** web server-rendered, portal cùng origin hoặc ứng dụng có backend tin cậy và không cần browser nhận access token. Nếu cần SSO, backend có thể dùng OIDC Login mà vẫn quản lý session browser.

### 5.2. SPA + BFF giữ token server-side

Một BFF là server phục vụ SPA, thực hiện OAuth/OIDC login rồi giữ access/refresh tokens **ngoài browser JavaScript**. Browser gửi session cookie tới BFF; BFF gọi downstream API bằng access token đúng audience.

```text
Browser SPA             BFF backend              OIDC IdP       Downstream API
  | start login              |                        |              |
  |------------------------->|--- Authorization Code ->|              |
  |                          |<---- callback code -----|              |
  |                          |---- token request ----->|              |
  |                          |<---- access token ------|              |
  |<--- session cookie ------|                        |              |
  | GET /bff/orders + cookie |                        |              |
  |------------------------->|------ Bearer token ------------------->|
  |                          |<------- JSON -------------------------|
  |<---------- JSON ---------|                        |              |
```

Ưu điểm: token không phải được lưu trong `localStorage` hoặc JS memory; tập trung xử lý refresh, session và nhiều APIs. Đánh đổi: BFF là thành phần vận hành quan trọng, phải có CSRF/XSS hardening, session store, token storage, least-privilege proxy, kiểm origin và audit.

**Cảnh báo:** `oauth2Login()` giúp login bằng OIDC nhưng chưa tự tạo một BFF hoàn thiện. BFF thật còn cần API proxy layer, OAuth2 authorized client/token lifecycle, session-to-user mapping, logout, CSRF và xử lý lỗi downstream. Không trả access token trong JSON “để frontend tiện dùng” nếu mục tiêu là giữ token ở server.

### 5.3. SPA thuần browser phải gọi API trực tiếp

Khi không có BFF khả thi, SPA là OAuth2 public client, thường dùng Authorization Code + PKCE:

```text
SPA            Authorization Server             Resource API
 | code_challenge S256 + state |                      |
 |---------------------------->|                      |
 | user login tại IdP          |                      |
 |<-------- code --------------|                      |
 | code_verifier tới token     |                      |
 |---------------------------->|                      |
 |<-------- access token ------|                      |
 | Authorization: Bearer <access_token>               |
 |--------------------------------------------------->|
 |<------------------- response ----------------------|
```

PKCE bảo vệ code khỏi bị sử dụng nếu chỉ có authorization code. Không đưa client secret vào JS, không dùng implicit flow và không lấy password người dùng trực tiếp để gọi password grant. Đăng ký redirect URI chính xác; triển khai `state` và OIDC `nonce` theo SDK.

**Token trong browser:** XSS có thể lấy token từ `localStorage` hoặc thực thi thao tác bằng phiên hiện tại; lưu trong memory giảm một số kiểu lưu tồn lâu nhưng **không loại bỏ XSS**. Chỉ nhận refresh token khi IdP cho phép loại client đó, với rotation/TTL/reuse detection. Dùng CSP, chống injection, kiểm dependencies, không đưa token vào URL, log hoặc query param.

**CORS không phải phân quyền.** CORS chỉ giới hạn browser đọc response cross-origin; backend vẫn phải xác minh token và phân quyền mọi request. Nếu API còn chấp nhận cookie tự gửi, chính sách CSRF vẫn cần được đánh giá độc lập.

## 6. Bước ba: mobile, desktop và thiết bị hạn chế

Ứng dụng iOS/Android, desktop và CLI phân phối tới máy người dùng không thể giữ một shared client secret lâu dài. Luồng login người dùng thường là Authorization Code + PKCE qua **system browser** (external user-agent), không phải embedded webview yêu cầu nhập mật khẩu ngay trong app.

Yêu cầu thực tế gồm:

- PKCE `S256`, redirect URI chính xác, `state`/`nonce` phù hợp; bảo vệ code interception.
- OAuth client đăng ký đúng kiểu public client, không gắn secret giống confidential web server.
- Access/refresh token lưu qua OS secure storage (Keychain/Keystore hoặc tương đương), không trong logs hoặc cấu hình plaintext.
- Access token ngắn hạn, refresh token rotation/revocation theo nhà cung cấp, kế hoạch đăng xuất hoặc mất thiết bị.
- Offline mode phải có giới hạn dữ liệu, mã hóa cache và thời điểm kiểm quyền lại; offline không đồng nghĩa token vĩnh viễn.
- API luôn kiểm Bearer token và owner/tenant, không tin role do mobile tự gửi.

Với CLI có browser, có thể dùng loopback redirect với PKCE. TV/thiết bị thiếu browser có thể dùng **Device Authorization Grant (RFC 8628)** nếu provider hỗ trợ: người dùng xác nhận trên thiết bị khác, device code ngắn hạn, polling có giới hạn và chống phishing.

## 7. Bước bốn: machine-to-machine không có user cuối

Job chạy theo lịch, microservice hoặc integration server có thể dùng **OAuth2 Client Credentials** hoặc workload identity. Grant này đại diện **client/service**, không phải một nhân viên được giả lập.

```text
Scheduled job           Authorization Server          Resource API
     | authenticate client + scope |                       |
     |----------------------------->|                       |
     |<----- access token ----------|                       |
     | Authorization: Bearer token                          |
     |----------------------------------------------------->|
     |<---------------- response ---------------------------|
```

Chỉ dùng client secret/private key ở server có secret manager và rotation; cân nhắc mTLS hoặc `private_key_jwt` khi IdP hỗ trợ. Token audience và scope phải dành đúng API, ví dụ `reports.export` thay vì `admin:*`. Audit workload identity riêng.

**Không** dùng Client Credentials cho SPA/mobile để tránh màn hình đăng nhập: chúng không bảo vệ được client secret và grant này không xác thực người dùng cuối. Nếu job làm việc **thay mặt một user**, cần delegation/token exchange phù hợp, không gán tùy tiện role của user cho service account.

## 8. Bước năm: JWT, opaque token, revocation và phân quyền dữ liệu

| Yếu tố | JWT access token | Opaque access token |
| --- | --- | --- |
| Kiểm tra | Resource Server thường xác minh chữ ký và claims cục bộ bằng keys đáng tin. | API gọi introspection endpoint hoặc dùng kết quả cache có TTL. |
| Hiệu năng | Có thể giảm round-trip introspection, cần key fetching/rotation. | Phụ thuộc network/IdP, cache cần kiểm rủi ro stale. |
| Thu hồi | Token chưa hết hạn vẫn hợp lệ nếu API chỉ kiểm chữ ký/`exp`; cần chiến lược bổ sung nếu phải revoke ngay. | Introspection có thể phản ánh token inactive nhưng cache làm trễ hiệu lực. |
| Dữ liệu | JWT payload thường đọc được bởi bên giữ token dù signature hợp lệ. | Client thường không đọc trực tiếp metadata từ opaque string. |
| Phù hợp | Hệ phân tán chấp nhận TTL/rotation và xác minh tại API. | Cần kiểm quyền/token state tập trung hoặc không muốn public token claims. |

Cả JWT và opaque đều cần issuer/audience/scope/expiry đúng, HTTPS và authorization. **Không chọn JWT chỉ vì “stateless”.** Nếu sản phẩm yêu cầu khóa admin có hiệu lực trong 1 phút, access token sống 1 giờ chỉ kiểm chữ ký sẽ không đáp ứng SLA nếu không có cơ chế revocation/kiểm quyền online.

**Owner/tenant:** Role `ROLE_USER` và scope `SCOPE_orders.read` thường mới là quyền hành động. Với bản ghi riêng phải kiểm `owner_user_id`; với tổ chức phải kiểm membership và giới hạn query theo `authorized_organization_id`. Không tin `userId`/`organizationId` từ body hay header tự đặt như một quyền đã cấp.

## 9. Ánh xạ sang Spring Security

| Chức năng | Thành phần Spring Security |
| --- | --- |
| Local username/password | `UserDetailsService`, `PasswordEncoder`, `formLogin`, session management. |
| Web OIDC/SSO hoặc BFF | `spring-boot-starter-oauth2-client`, `oauth2Login` và `oauth2Client`. |
| API nhận JWT | `spring-boot-starter-oauth2-resource-server`, `oauth2ResourceServer(...jwt...)`, `JwtDecoder`. |
| API nhận opaque token | `oauth2ResourceServer(...opaqueToken...)`, `OpaqueTokenIntrospector`. |
| Service OAuth2 client | Client registration cho `client_credentials` và authorized client manager. |
| Quyền HTTP/method | `authorizeHttpRequests`, `hasRole`, `hasAuthority`, `@EnableMethodSecurity`, `@PreAuthorize`. |
| Bảo vệ dữ liệu | Repository query theo owner/tenant, membership/ACL do server xác minh. |

**Lưu ý phiên bản:** Ví dụ chạy được bên dưới ghim Spring Boot **3.5.16** cho Java 17/Spring Security 6.x. Đây là bản cuối của nhánh 3.5.x có hỗ trợ OSS; với production mới ở năm 2026 cần dùng nhánh còn được nhận bản vá và lên kế hoạch nâng cấp. Snippets cho OIDC và Resource Server là **những phương án khác**, không ghép ngẫu nhiên với project demo đang dùng form login.

## 10. Ví dụ Java 17+ chạy được: ứng dụng web chọn session

Giả sử sản phẩm là portal cùng origin, chưa cần SSO hoặc third-party API. Chọn form login, session cookie và CSRF. Ví dụ dưới đây có Gradle, Java application, test và kết quả HTTP dự kiến.

### 10.1. Cấu hình Gradle

`settings.gradle`:

```groovy
rootProject.name = 'auth-choice-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
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
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`src/main/resources/application.properties`:

```properties
spring.application.name=auth-choice-demo
server.servlet.session.timeout=20m
server.servlet.session.cookie.http-only=true
```

Với production qua HTTPS, cần cấu hình cookie `Secure`, `SameSite`, reverse proxy headers và session store cho nhiều instance. Không dùng tài khoản mẫu trong sản phẩm thật.

### 10.2. Ứng dụng Spring Boot

Tạo `src/main/java/demo/authchoice/SessionAuthApplication.java`:

```java
package demo.authchoice;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class SessionAuthApplication {
    public static void main(String[] args) {
        SpringApplication.run(SessionAuthApplication.class, args);
    }
}

@RestController
class BrowserApi {
    @GetMapping("/public")
    String publicEndpoint() {
        return "public";
    }

    @GetMapping("/me")
    String me(Authentication authentication) {
        return authentication.getName();
    }

    @PostMapping("/actions")
    String saveAction(Authentication authentication) {
        return "saved-for-" + authentication.getName();
    }
}

@Configuration
class BrowserSecurity {
    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoder.encode("alice123"))
                .roles("USER")
                .build()
        );
    }

    @Bean
    SecurityFilterChain webChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public", "/error").permitAll()
                .anyRequest().authenticated()
            )
            .formLogin(form -> form.permitAll())
            .logout(Customizer.withDefaults());

        // CSRF mặc định vẫn bật. Không đổi sang STATELESS.
        return http.build();
    }
}
```

**Cách hiểu:** Spring Security thực hiện login, lưu trạng thái đăng nhập qua session; browser giữ session ID trong cookie. GET `/me` yêu cầu login; POST `/actions` yêu cầu đăng nhập **và** CSRF token hợp lệ. Demo có một user `alice` với hash BCrypt. `authenticated()` không tự bảo vệ owner/tenant cho API dữ liệu riêng.

### 10.3. Test Spring Security và session thật với MockMvc

Tạo `src/test/java/demo/authchoice/SessionAuthTest.java`:

```java
package demo.authchoice;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.redirectedUrlPattern;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SessionAuthTest {
    @Autowired MockMvc mvc;

    private MockHttpSession signedIn() throws Exception {
        var result = mvc.perform(post("/login")
                .param("username", "alice")
                .param("password", "alice123")
                .with(csrf()))
            .andExpect(status().is3xxRedirection())
            .andReturn();

        var session =
            (MockHttpSession) result.getRequest().getSession(false);
        assertThat(session).isNotNull();
        return session;
    }

    @Test
    void publicPageIsAccessible() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));
    }

    @Test
    void anonymousIsRedirectedToLogin() throws Exception {
        mvc.perform(get("/me"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrlPattern("**/login"));
    }

    @Test
    void wrongPasswordIsRejected() throws Exception {
        mvc.perform(post("/login")
                .param("username", "alice")
                .param("password", "wrong")
                .with(csrf()))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/login?error"));
    }

    @Test
    void signedInSessionWorks() throws Exception {
        mvc.perform(get("/me").session(signedIn()))
            .andExpect(status().isOk())
            .andExpect(content().string("alice"));
    }

    @Test
    void postWithoutCsrfIsForbidden() throws Exception {
        mvc.perform(post("/actions").session(signedIn()))
            .andExpect(status().isForbidden());
    }

    @Test
    void postWithCsrfWorks() throws Exception {
        mvc.perform(post("/actions")
                .session(signedIn())
                .with(csrf()))
            .andExpect(status().isOk())
            .andExpect(content().string("saved-for-alice"));
    }
}
```

`@SpringBootTest` nạp cấu hình ứng dụng và `@AutoConfigureMockMvc` giữ các security filters. Test login bằng request `POST /login` với CSRF và credentials thật, sau đó **dùng lại session** cho các request tiếp theo. Không dùng `@WithMockUser` để giả quá trình login.

Kết quả mong đợi:

| Request | Kết quả |
| --- | --- |
| Anonymous GET `/public` | 200, body `public`. |
| Anonymous GET `/me` | 302 redirect tới `/login`. |
| Password sai tại POST `/login` có CSRF | 302 redirect tới `/login?error`. |
| Login đúng và GET `/me` cùng session | 200, body `alice`. |
| Login đúng, POST `/actions` thiếu CSRF | 403. |
| Login đúng, POST `/actions` có CSRF | 200, body `saved-for-alice`. |

Chạy trong thư mục dự án nếu đã có Gradle Wrapper:

```bash
./gradlew test
./gradlew bootRun
```

Windows: `gradlew.bat test` và `gradlew.bat bootRun`. Nếu không có wrapper, dùng `gradle test` / `gradle bootRun` với Gradle 8.x tương thích. Mở `http://localhost:8080/me` trên trình duyệt, login `alice / alice123` trong môi trường học tập. Cần nhớ đây là demo localhost, **không phải cấu hình TLS/cookie/secrets production**.

## 11. Phương án OIDC Login/BFF khi cần SSO

Nếu sản phẩm có doanh nghiệp dùng SSO/MFA hoặc SPA cần gọi downstream API, có thể thay local form login bằng OIDC. **Đây là blueprint cấu hình**, không chạy độc lập nếu chưa có IdP thật, client registration, secret manager, BFF proxy và CSRF integration.

Dependency:

```groovy
implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
```

Ví dụ `application.yml`:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company
            client-id: your-client-id-from-secret-store
            client-secret: your-secret-from-secret-store
            authorization-grant-type: authorization_code
            scope: openid,profile,email
        provider:
          company:
            issuer-uri: https://identity.example.com/issuer
```

Chọn thông tin client/issuer thực theo IdP; **không commit secrets** trong YAML source. Bean cấu hình minh họa:

```java
@Bean
SecurityFilterChain bffChain(HttpSecurity http) throws Exception {
    http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/", "/assets/**", "/error").permitAll()
            .anyRequest().authenticated()
        )
        .oauth2Login(Customizer.withDefaults())
        .oauth2Client(Customizer.withDefaults());

    // Browser session vẫn cần CSRF.
    return http.build();
}
```

Các snippet trên cần imports `@Bean`, `HttpSecurity`, `SecurityFilterChain`, `Customizer`, và một ứng dụng BFF thật. BFF còn phải quản lý `OAuth2AuthorizedClient` và token storage phía server, gọi downstream API với access token đúng audience, refresh/revoke, xây frontend CSRF flow, logout và xử lý đa instance.

**Quy tắc:** Redirect URI phải trùng cấu hình IdP; `state`/OIDC `nonce`, PKCE và issuer binding phải được client library xác thực đúng. Không gửi ID token làm access token API, không trả access/refresh token cho browser khi mục tiêu BFF là che token.

## 12. Phương án OAuth2 Resource Server cho API Bearer token

API nhận Bearer token từ mobile, SPA direct hoặc đối tác cần xác minh token ở **Resource Server**. Đây là **đoạn tích hợp riêng**, không chạy độc lập thiếu trusted issuer/route và access token thật.

Dependency:

```groovy
implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
```

`application.yml`:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.com/issuer
          audiences: https://api.example.com
```

Ví dụ chain chỉ dành cho API nhận **Bearer header**, không dùng browser cookie tự gửi:

```java
@Bean
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/health").permitAll()
            .requestMatchers(HttpMethod.GET, "/api/reports/**")
                .hasAuthority("SCOPE_reports.read")
            .anyRequest().authenticated()
        )
        .sessionManagement(s -> s
            .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
        )
        .csrf(AbstractHttpConfigurer::disable)
        .oauth2ResourceServer(o -> o.jwt(Customizer.withDefaults()));

    return http.build();
}
```

Cần imports `@Bean`, `HttpSecurity`, `HttpMethod`, `SecurityFilterChain`, `SessionCreationPolicy`, `AbstractHttpConfigurer`, `Customizer`. **Tắt CSRF chỉ có điều kiện** khi toàn bộ chain này thực sự chỉ chấp nhận Authorization Bearer header, không chấp nhận session cookie. Nếu có cookie-authenticated endpoints, không copy cấu hình này vào web/BFF mà không phân chia chain.

Resource Server kiểm chữ ký/khóa, issuer, audience, expiry, thời điểm hiệu lực và scopes. Claim scope thường thành authority `SCOPE_reports.read`. Token không hợp lệ thường 401; token hợp lệ nhưng thiếu scope thường 403. Dù đủ scope vẫn cần kiểm ownership/tenant ở dữ liệu.

Nếu dùng opaque token, chọn `opaqueToken` thay `jwt` cùng introspection endpoint/credentials của IdP, cân nhắc độ trễ và hiệu lực revoke. JWT chỉ kiểm cục bộ có trade-off revocation; opaque cache introspection cũng có nguy cơ stale.

## 13. Phương án Client Credentials cho service-to-service

Đây là cấu hình định hướng cho job, **không phải cách login của mobile/browser**. Cần `spring-boot-starter-oauth2-client`, OAuth2 client manager thích hợp và IdP thực:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          report-job:
            provider: company
            client-id: workload-client-id
            client-secret: secret-from-manager
            authorization-grant-type: client_credentials
            scope: reports.export
        provider:
          company:
            token-uri: https://identity.example.com/oauth2/token
```

Dùng workload identity/secret manager, scope hẹp, token ngắn hạn, key rotation, audit theo service. Nếu công việc thực hiện thay một user cụ thể, cần delegation model khác, không tùy tiện cho service scope toàn cục.

## 14. Yêu cầu sản phẩm làm thay đổi quyết định

### 14.1. Enterprise SSO và MFA

Portal B2B cần SSO, MFA, passkeys hoặc chính sách deprovisioning thường hướng tới IdP chuyên dụng. Web/BFF dùng OIDC Login và session; mobile dùng Authorization Code + PKCE; service dùng client authentication riêng. Một số doanh nghiệp cần SAML2 federation, khi đó có thể tích hợp SAML service provider thay vì giả định mọi IdP dùng OIDC.

### 14.2. Thu hồi ngay và logout

- Session server-side có thể invalidate, nhưng cần đồng bộ nhiều node/device và cache.
- JWT chưa hết hạn có thể tiếp tục được chấp nhận nếu resource server chỉ kiểm signature/expiry.
- Opaque token introspection có thể phản ánh revoke sớm hơn, nhưng cache làm trễ.
- Refresh token rotation/revocation bảo vệ việc gia hạn, không tự vô hiệu hóa mọi access token chưa hết hạn.
- Logout ở app không đồng nghĩa đã logout toàn bộ session IdP và sản phẩm khác.

Sản phẩm cần định nghĩa SLA, ví dụ “khóa account có hiệu lực tối đa sau N phút” rồi mới chọn TTL, introspection, token revocation và session policy.

### 14.3. Multi-tenant, owner và quyền dữ liệu

Chỉ có `ROLE_USER` hoặc `SCOPE_reports.read` không chứng minh user được đọc mọi báo cáo. Cần xác minh membership/owner và đặt predicate `organization_id = :authorizedOrgId` hoặc `owner_user_id = :currentUserId` ngay trong truy vấn. Test người A và người B cùng role với tài nguyên riêng, cả API list/detail/count/export/write.

### 14.4. Vận hành và độ phức tạp

Session cần store/replication, timeout; BFF cần proxy/token store, scale và CSRF; JWT cần JWK rotation, clock skew và revoke plan; opaque introspection cần latency/availability SLO; Client Credentials cần key/secret rotation và service account governance. Chọn mô hình team có năng lực bảo trì, không chỉ dựa vào số request mỗi giây.

## 15. Ba tình huống thiết kế mẫu

**Portal nội bộ:** browser, backend cùng origin, doanh nghiệp yêu cầu SSO/MFA và audit → OIDC Login ở server, session cookie HttpOnly/Secure/SameSite, CSRF; backend kiểm role/owner và quyền tổ chức. Không bắt browser cầm JWT nếu mọi API qua backend/BFF.

**Mobile thương mại:** iOS/Android, login user, API trực tiếp, có mất thiết bị/offline → Authorization Code + PKCE qua system browser; token trong OS secure storage; API Resource Server kiểm audience/scope và owner; refresh rotation và revoke policy.

**Job xuất báo cáo:** chạy tự động không có user, quyền đọc/export dataset → workload identity/Client Credentials, secret/private key bảo vệ server-side, access token ngắn hạn và scope hẹp; API audit theo workload. Không lưu mật khẩu nhân viên trong cron.

## 16. Những lỗi thiết kế phổ biến

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Mọi client phải dùng JWT. | Trộn login/user/machine, khó revoke. | Chọn theo actor và trust boundary. |
| Dùng ID token gọi Resource Server. | Sai audience/token semantics. | Access token riêng cho API. |
| SPA/mobile nhúng client secret. | Secret không bí mật. | Public client + PKCE hoặc BFF. |
| Dùng Implicit hoặc Password Grant mới. | Tăng rủi ro lộ code/token/password. | Authorization Code + PKCE. |
| BFF trả token về JS. | Mất lợi thế token storage server-side. | Browser chỉ nhận session cookie. |
| Cookie session nhưng tắt CSRF. | Cross-site request có thể dùng cookie tự gửi. | CSRF phù hợp và SameSite/Origin policy. |
| Tin CORS thay token validation. | API vẫn có thể bị gọi bởi non-browser client. | Backend kiểm authentication/authorization. |
| Decode JWT mà không verify. | Claims có thể bị giả mạo. | Validate signature, issuer, audience, expiry. |
| JWT dài hạn không revoke. | Quyền bị thu hồi có thể vẫn còn hiệu lực. | TTL/revoke/introspection theo SLA. |
| Job dùng password user. | Sai audit, scope quá rộng, khó rotation. | Workload identity/Client Credentials. |
| Chỉ kiểm scope, bỏ owner/tenant. | BOLA/IDOR và rò rỉ dữ liệu. | Scoped DB queries và membership. |
| Trộn cookie và bearer trên một chain tùy tiện. | CSRF/authorization không nhất quán. | `securityMatcher`, `@Order` và tests theo client. |

## 17. Kiểm thử kiến trúc và checklist

| Loại test | Những ca tối thiểu |
| --- | --- |
| Session web | Anonymous redirect; login đúng/sai; session reuse; logout; POST có/không CSRF. |
| OIDC/BFF | Redirect URI, state/nonce/PKCE, token không lộ trong browser, session/CSRF, IdP logout policy. |
| SPA/mobile | PKCE, token expiry/refresh, redirect validation, CORS không thay quyền, OS storage. |
| Resource Server | Thiếu token, sai signature/issuer/audience/expiry, thiếu scope 403, đủ scope 200. |
| M2M | Client auth fail, thiếu scope, sai audience, rotation và workload audit. |
| Data authorization | Owner sai/tenant sai bị chặn; list/count/export và update không vượt scope. |
| Vận hành | IdP down, session store down, logout/revoke SLA, logging redaction và alert. |

Checklist trước khi phát hành:

- [ ] Đã liệt kê từng client, user vs machine identity.
- [ ] Đã phân biệt public và confidential clients, không lộ client secret.
- [ ] Đã chọn session, BFF, direct OAuth hoặc Client Credentials theo yêu cầu.
- [ ] Public OAuth clients dùng Authorization Code + PKCE, redirect chính xác.
- [ ] SSO/MFA/passkey/step-up phù hợp yêu cầu sản phẩm.
- [ ] API dùng access token đúng audience, không dùng ID token.
- [ ] Cookie HttpOnly/Secure/SameSite và CSRF được thiết kế cho browser flow.
- [ ] Bearer token được verify và role/scope/owner được kiểm server-side.
- [ ] Có TTL, logout/revocation, key rotation và incident plan theo SLA.
- [ ] SecurityFilterChain/matcher và method security nhất quán.
- [ ] Có cả allow/deny tests, cross-user và cross-tenant tests.
- [ ] Secret, token, password và session ID không bị ghi vào logs.
- [ ] Có ADR ghi lựa chọn, trade-offs và phương án loại trừ.

## 18. Tự kiểm tra

**Q1.** Web Spring MVC cùng origin có nhất thiết dùng JWT không?  
**A1.** Không. Session cookie + CSRF có thể đơn giản và phù hợp; dùng OIDC Login nếu cần SSO.

**Q2.** SPA có backend của mình, không muốn token trong JS thì nên xem xét gì?  
**A2.** BFF + OIDC; BFF giữ downstream tokens phía server, browser giữ session cookie, vẫn cần CSRF/XSS protections.

**Q3.** Mobile nhúng client secret trong APK có trở thành confidential client không?  
**A3.** Không. Binary có thể bị trích xuất; nên dùng Authorization Code + PKCE bằng system browser.

**Q4.** `oauth2ResourceServer().jwt()` có tự cung cấp trang login không?  
**A4.** Không. Nó chỉ xác minh Bearer token cho API; login thuộc OAuth/OIDC Client và IdP.

**Q5.** API có thể dùng ID token có chữ ký đúng như access token không?  
**A5.** Không nên. API cần access token đúng audience và quyền; signature đúng chưa đủ.

**Q6.** Job chạy đêm không có user nên dùng grant gì?  
**A6.** Workload identity/Client Credentials với scope hẹp và server-side secret/key.

**Q7.** User có scope đọc đơn hàng nhưng đơn thuộc tenant khác có xem được không?  
**A7.** Không nếu policy yêu cầu tenant isolation; vẫn cần kiểm owner/membership.

**Q8.** CORS được bật đúng origin thì API có thể bỏ token validation?  
**A8.** Không. CORS là cơ chế browser, không phải authorization.

**Q9.** JWT sống một giờ nhưng yêu cầu revoke admin trong một phút. Thiết kế thiếu gì?  
**A9.** Token/permission revocation strategy và TTL không đáp ứng SLA; cần kiểm online, revoke hoặc rút ngắn hiệu lực.

**Q10.** POST dùng cookie session nhận 403, có nên tắt CSRF?  
**A10.** Không chỉ vì status 403. Kiểm token CSRF, cookie và flow chính xác; giữ bảo vệ phù hợp mô hình credentials.

## 19. Ghi nhớ và tài liệu chính thức

**Công thức chọn:** loại client và trust boundary → con người hay workload → login/IdP → session hoặc Bearer token → quyền API và dữ liệu → logout/revocation/test. Với web cùng origin có thể dùng session; SPA có backend đánh giá BFF; SPA direct/mobile dùng Authorization Code + PKCE; API nhận token dùng Resource Server; backend-to-backend dùng Client Credentials. Không có một cơ chế tốt nhất cho mọi loại client.

- [Spring Security — Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html)
- [Spring Security — Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html)
- [Spring Security — CSRF](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html)
- [Spring Security — OAuth2 Login](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/login/index.html)
- [Spring Security — OAuth2 Client](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/client/index.html)
- [Spring Security — JWT Resource Server](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/jwt.html)
- [Spring Security — Opaque Token Resource Server](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/opaque-token.html)
- [RFC 9700 — OAuth2 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700)
- [RFC 7636 — PKCE](https://www.rfc-editor.org/rfc/rfc7636)
- [RFC 8252 — OAuth2 for Native Apps](https://www.rfc-editor.org/rfc/rfc8252)
- [RFC 8628 — Device Authorization](https://www.rfc-editor.org/rfc/rfc8628)
- [OWASP — Session Management](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)
- [OWASP — CSRF Prevention](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html)
