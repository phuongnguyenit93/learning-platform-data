# Tách đăng nhập quản trị, người dùng và tài khoản dịch vụ

> Phạm vi: **Spring Security - authentication → Nhiều cơ chế** trên **Spring Boot 3.5 / Spring Security 6.5 Servlet / Java 17+**. Bài giải thích cách phân tách đăng nhập tương tác của quản trị viên, người dùng cuối và xác thực không tương tác của tài khoản dịch vụ, từ cơ chế nhận credential, nguồn danh tính, quyền, session tới kiểm thử. Ví dụ Java dùng ba `SecurityFilterChain` và một chain dự phòng.

## 1. Ba loại danh tính không có cùng hợp đồng đăng nhập

| Nhóm | Chủ thể | Luồng xác thực | URL | Quyền | Trạng thái |
| --- | --- | --- | --- | --- | --- |
| Quản trị viên | Nhân sự vận hành | Form login, mật khẩu băm; production cần MFA/step-up | `/admin/login`, `/admin/**` | `REALM_ADMIN` **và** `ROLE_ADMIN` | Session; context của admin |
| Người dùng | Người dùng cuối | Form login | `/user/login`, `/user/**` | `REALM_USER` **và** `ROLE_USER` | Session; context của user |
| Tài khoản dịch vụ | Worker, job, ứng dụng khác | OAuth2 `client_credentials` lấy access token; API xác minh Bearer JWT | `/svc/**` | `SCOPE_reports.read` | Stateless, không có form/cookie login |

Việc tách này có ít nhất bốn phần: (1) cơ chế authentication, (2) nguồn dữ liệu hoặc issuer quyết định danh tính, (3) policy authorization, (4) lưu hoặc không lưu `SecurityContext`. Tách riêng URL login nhưng vẫn dùng cùng tài khoản, cùng token và cùng session repository chưa bảo đảm cô lập.

Những yêu cầu cần chứng minh bằng kiểm thử:

1. Người dùng `alice` đăng nhập thành công ở `/user/login` **không thể** đi tới `/admin/home` chỉ nhờ cookie.
2. Quản trị viên `operator` đăng nhập ở `/admin/login` **không tự có** context user.
3. Credential của `operator` gửi sang `/user/login` và credential của `alice` gửi sang `/admin/login` đều phải thất bại.
4. Một `HttpSession` của trình duyệt không thay thế `Authorization: Bearer` ở `/svc/reports`.
5. Token service có scope `reports.read` chỉ được vào endpoint dịch vụ đúng policy; bearer token không phải session đăng nhập admin.
6. Request không nằm trong bất kỳ nhóm URL đã công bố vẫn phải chịu chain dự phòng, không lặng lẽ đi qua Spring Security.

**Xác thực** trả lời “chủ thể là ai và bằng chứng đáng tin tới đâu”; **phân quyền** trả lời “chủ thể được làm gì trong phạm vi nào”. Tài khoản admin cũng không mặc định có quyền cho mọi ứng dụng hoặc mọi tenant. Tài khoản dịch vụ là một **machine identity**, không phải account của nhân viên được gắn thêm `ROLE_SERVICE`.

## 2. Cách FilterChainProxy chọn SecurityFilterChain

Trên Servlet stack, Spring Security dùng `FilterChainProxy` so khớp các `SecurityFilterChain` theo thứ tự ưu tiên. **Chỉ chain khớp đầu tiên được chạy**.

```text
HTTP request
     |
     v
FilterChainProxy
     |
     +-- /admin/** -> Admin chain @Order(1)
     |                 form login; admin AuthenticationManager
     |                 CSRF ON; SECCTX_ADMIN; ROLE_ADMIN + REALM_ADMIN
     |
     +-- /user/**  -> User chain @Order(2)
     |                 form login; user AuthenticationManager
     |                 CSRF ON; SECCTX_USER; ROLE_USER + REALM_USER
     |
     +-- /svc/**   -> Service chain @Order(3)
     |                 Bearer JWT / JwtDecoder
     |                 STATELESS; SCOPE_reports.read
     |
     '-- còn lại  -> Fallback @Order(4), denyAll()
```

- `http.securityMatcher("/admin/**")` xác định request **nào vào chain**. `authorizeHttpRequests(...requestMatchers(...))` chỉ xác định policy **bên trong** chain đã chọn. Không thay thế hai loại matcher cho nhau.
- URL do filter tạo (chẳng hạn `POST /login`) phải thuộc phạm vi chain. Khi dùng `/admin/**`, cần đặt `loginProcessingUrl("/admin/login")` thay vì giữ `/login` mặc định.
- Khi đặt `loginPage("/admin/login")`, Spring Security **không tự phát sinh HTML trang GET**. Phải tạo controller/template riêng cho `GET /admin/login`. Tương tự cho user login.
- Một chain không có `securityMatcher` được dùng làm fallback để mọi request còn lại vẫn đi qua Spring Security.
- Service chain không bật `formLogin` và không nhận browser session làm bằng chứng xác thực.

### Vì sao tách chain chưa đồng nghĩa tách session?

Khi hai browser chain cùng chạy trên một host, chúng có thể sử dụng **chung cookie `JSESSIONID`** và chung `HttpSession`. Nếu cả hai dùng khóa mặc định `SPRING_SECURITY_CONTEXT`, chúng có thể đọc cùng một `Authentication` bất kể URL login nào đã tạo ra.

Ví dụ này dùng hai `HttpSessionSecurityContextRepository` với khóa khác nhau:

```text
HttpSession (demo dùng cùng JSESSIONID)
  |
  +-- SECCTX_ADMIN -> Authentication operator, REALM_ADMIN, ROLE_ADMIN
  |
  '-- SECCTX_USER  -> Authentication alice, REALM_USER, ROLE_USER
```

Đây là cách tách **SecurityContext về mặt logic**, không phải hai session vật lý. Một cookie bị chiếm đoạt có thể làm lộ cả hai context; logout mặc định của một chain thường vô hiệu hóa toàn bộ `HttpSession`. Muốn ranh giới quản trị mạnh, nên tách ứng dụng/origin như `admin.example.com` và `app.example.com`, dùng cookie host-only, session store và timeout riêng, áp dụng MFA/step-up cho admin. Không nên coi việc đổi tên session attribute là biện pháp cô lập tuyệt đối.

## 3. Ví dụ chạy trên Spring Boot 3.5 / Spring Security 6.5

Ví dụ minh họa hai kho user in-memory độc lập, mỗi nơi chỉ có một danh tính. Với service, ứng dụng đóng vai trò **OAuth2 Resource Server** và kiểm tra JWT từ issuer tin cậy. Test ở phần 5 dùng JwtDecoder giả riêng trong test để kiểm tra luồng; không dùng decoder đó trong production.

### 3.1. Dependencies và application.yml

Trong project Spring Boot 3.5 đã cấu hình Gradle/Java 17, khai báo:

```groovy
// build.gradle - phần dependencies
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

**`src/main/resources/application.yml`**

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          # Điền issuer thật có metadata/JWK hợp lệ khi chạy với IdP.
          issuer-uri: https://idp.example.test/realms/learning
          audiences: https://api.example.test
server:
  servlet:
    session:
      cookie:
        http-only: true
        same-site: lax
```

`idp.example.test` là hostname mẫu, **không phải server thật**. `bootRun` cần một IdP được cấu hình đúng để xác thực Bearer JWT thực tế; bộ test bên dưới dùng `@TestConfiguration JwtDecoder` và chạy không phụ thuộc IdP. Trong production dùng HTTPS và bật cookie `Secure` cùng HSTS theo chính sách triển khai.

**`src/main/java/example/realms/RealmApplication.java`**

```java
package example.realms;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RealmApplication {
    public static void main(String[] args) {
        SpringApplication.run(RealmApplication.class, args);
    }
}
```

### 3.2. SecurityConfig: kho identity, manager và context tách riêng

**`src/main/java/example/realms/SecurityConfig.java`**

```java
package example.realms;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.authorization.AuthorizationManagers;
import org.springframework.security.authorization.AuthorityAuthorizationManager;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.intercept.RequestAuthorizationContext;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.security.web.context.NullSecurityContextRepository;
import org.springframework.security.web.context.SecurityContextRepository;

@Configuration
@EnableWebSecurity
public class SecurityConfig {
    public static final String ADMIN_CONTEXT = "SECCTX_ADMIN";
    public static final String USER_CONTEXT = "SECCTX_USER";

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    // Chỉ danh tính quản trị, không dùng chung với appUsers.
    @Bean("adminUsers")
    UserDetailsService adminUsers(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("operator")
                .password(encoder.encode("operator-pass"))
                .authorities("REALM_ADMIN", "ROLE_ADMIN")
                .build()
        );
    }

    // Chỉ danh tính người dùng cuối.
    @Bean("appUsers")
    UserDetailsService appUsers(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoder.encode("alice-pass"))
                .authorities("REALM_USER", "ROLE_USER")
                .build()
        );
    }

    private static AuthenticationManager manager(
            UserDetailsService users, PasswordEncoder encoder) {
        DaoAuthenticationProvider provider = new DaoAuthenticationProvider(users);
        provider.setPasswordEncoder(encoder);
        return new ProviderManager(provider);
    }

    @Bean("adminManager")
    AuthenticationManager adminManager(
            @Qualifier("adminUsers") UserDetailsService users,
            PasswordEncoder encoder) {
        return manager(users, encoder);
    }

    @Bean("appManager")
    AuthenticationManager appManager(
            @Qualifier("appUsers") UserDetailsService users,
            PasswordEncoder encoder) {
        return manager(users, encoder);
    }

    private static SecurityContextRepository sessionContext(String key) {
        HttpSessionSecurityContextRepository repository =
            new HttpSessionSecurityContextRepository();
        repository.setSpringSecurityContextKey(key);
        return repository;
    }

    @Bean("adminRepo")
    SecurityContextRepository adminRepo() {
        return sessionContext(ADMIN_CONTEXT);
    }

    @Bean("appRepo")
    SecurityContextRepository appRepo() {
        return sessionContext(USER_CONTEXT);
    }

    // Truy cập cần cả realm chính xác và vai trò đã được xác minh.
    private static AuthorizationManager<RequestAuthorizationContext>
            realmAndRole(String realm, String role) {
        return AuthorizationManagers.allOf(
            AuthorityAuthorizationManager
                .<RequestAuthorizationContext>hasAuthority(realm),
            AuthorityAuthorizationManager
                .<RequestAuthorizationContext>hasRole(role)
        );
    }

    @Bean
    @Order(1)
    SecurityFilterChain adminChain(
            HttpSecurity http,
            @Qualifier("adminManager") AuthenticationManager manager,
            @Qualifier("adminRepo") SecurityContextRepository repository)
            throws Exception {
        http
            .securityMatcher("/admin/**")
            .authenticationManager(manager)
            .securityContext(sc -> sc.securityContextRepository(repository))
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.IF_REQUIRED))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/admin/login").permitAll()
                .anyRequest().access(realmAndRole("REALM_ADMIN", "ADMIN")))
            .formLogin(form -> form
                .loginPage("/admin/login")
                .loginProcessingUrl("/admin/login")
                .defaultSuccessUrl("/admin/home", true)
                .failureUrl("/admin/login?error")
                .permitAll())
            .logout(logout -> logout
                .logoutUrl("/admin/logout")
                .logoutSuccessUrl("/admin/login?logout"));
        // CSRF mặc định vẫn bảo vệ form POST.
        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain userChain(
            HttpSecurity http,
            @Qualifier("appManager") AuthenticationManager manager,
            @Qualifier("appRepo") SecurityContextRepository repository)
            throws Exception {
        http
            .securityMatcher("/user/**")
            .authenticationManager(manager)
            .securityContext(sc -> sc.securityContextRepository(repository))
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.IF_REQUIRED))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/user/login").permitAll()
                .anyRequest().access(realmAndRole("REALM_USER", "USER")))
            .formLogin(form -> form
                .loginPage("/user/login")
                .loginProcessingUrl("/user/login")
                .defaultSuccessUrl("/user/home", true)
                .failureUrl("/user/login?error")
                .permitAll())
            .logout(logout -> logout
                .logoutUrl("/user/logout")
                .logoutSuccessUrl("/user/login?logout"));
        return http.build();
    }

    @Bean
    @Order(3)
    SecurityFilterChain serviceChain(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/svc/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/svc/reports")
                    .hasAuthority("SCOPE_reports.read")
                .anyRequest().denyAll())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .securityContext(sc -> sc.securityContextRepository(
                new NullSecurityContextRepository()))
            .requestCache(AbstractHttpConfigurer::disable)
            .csrf(AbstractHttpConfigurer::disable)
            .formLogin(AbstractHttpConfigurer::disable)
            .httpBasic(AbstractHttpConfigurer::disable)
            .oauth2ResourceServer(oauth -> oauth
                .jwt(Customizer.withDefaults()));
        return http.build();
    }

    @Bean
    @Order(4)
    SecurityFilterChain fallback(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth.anyRequest().denyAll());
        return http.build();
    }
}
```

Các điểm cần đọc kỹ:

1. `adminManager` và `appManager` có `DaoAuthenticationProvider` với `UserDetailsService` khác nhau. Không có account `operator` trong `appUsers` hoặc `alice` trong `adminUsers`. `ProviderManager` không tự dùng chung kho credential chỉ vì các chain cùng ứng dụng.
2. Authorities `REALM_ADMIN`/`REALM_USER` đánh dấu loại danh tính; `ROLE_ADMIN`/`ROLE_USER` thể hiện role. `realmAndRole(...)` yêu cầu **cả hai**. Các authority này được cấp từ dữ liệu server, không đọc từ form/header do client gửi.
3. `HttpSessionSecurityContextRepository.setSpringSecurityContextKey(...)` quyết định khóa lưu context; `securityContextRepository(...)` gắn kho tương ứng cho filter đọc và các filter authentication tham gia lưu. Hai chain có thể chia sẻ một `HttpSession` nhưng không đọc `Authentication` của nhau.
4. Form login dùng URL xử lý đăng nhập nằm trong matcher; GET login tự triển khai ở phần sau. `defaultSuccessUrl(...,true)` khiến kết quả redirect ổn định cho bài kiểm thử.
5. Service sử dụng `oauth2ResourceServer(...jwt(...))`; Bearer authentication tạo `JwtAuthenticationToken` chỉ sau khi JwtDecoder xác minh token. `SCOPE_reports.read` đến từ claim scope đã được xác minh, khác `ROLE_ADMIN` của browser.
6. `SessionCreationPolicy.STATELESS` và `NullSecurityContextRepository` làm rõ service không dùng session. CSRF chỉ tắt trong chain này vì bearer header được client đưa vào có chủ đích; không tắt CSRF ở hai form chain.
7. Fallback `denyAll()` được đặt cuối để route mới không mở tự do. Endpoint ngoài ba namespace chưa được cấp quyền sẽ bị từ chối.

### 3.3. Trang login GET cho hai realm

Khi dùng `.loginPage("/admin/login")`, Spring Security không tự sinh HTML của custom page. Ví dụ có một controller tạo form bằng HTML tối giản và token CSRF lấy từ request.

**`src/main/java/example/realms/LoginPageController.java`**

```java
package example.realms;

import jakarta.servlet.http.HttpServletRequest;
import org.springframework.http.MediaType;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.util.HtmlUtils;

@RestController
public class LoginPageController {

    @GetMapping(value = {"/admin/login", "/user/login"},
                produces = MediaType.TEXT_HTML_VALUE)
    public String loginPage(HttpServletRequest request) {
        CsrfToken csrf =
            (CsrfToken) request.getAttribute(CsrfToken.class.getName());
        if (csrf == null) {
            throw new IllegalStateException("CSRF token unavailable");
        }

        String action = request.getRequestURI()
            .substring(request.getContextPath().length());

        return """
            <!doctype html>
            <html lang="vi">
            <head><meta charset="UTF-8"><title>Đăng nhập</title></head>
            <body>
              <h1>Đăng nhập</h1>
              <form method="post" action="%s">
                <input type="hidden" name="%s" value="%s">
                <label>Tên đăng nhập
                  <input name="username" autocomplete="username">
                </label>
                <label>Mật khẩu
                  <input name="password" type="password"
                         autocomplete="current-password">
                </label>
                <button type="submit">Đăng nhập</button>
              </form>
            </body>
            </html>
            """.formatted(
                HtmlUtils.htmlEscape(action),
                HtmlUtils.htmlEscape(csrf.getParameterName()),
                HtmlUtils.htmlEscape(csrf.getToken()));
    }
}
```

Form GET `/admin/login` gửi `POST /admin/login`, form GET `/user/login` gửi `POST /user/login`. Cả hai có trường CSRF, username, password. Spring Security xử lý POST và xác thực qua manager riêng; GET controller chỉ tạo giao diện, không quyết định tài khoản hợp lệ. Trong ứng dụng thực tế, dùng template engine và làm giao diện riêng (đặc biệt admin MFA), không đặt mật khẩu trong URL hay JavaScript log.

### 3.4. Tài nguyên minh họa

**`src/main/java/example/realms/RealmController.java`**

```java
package example.realms;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class RealmController {

    @GetMapping("/admin/home")
    public String admin(Authentication authentication) {
        return "admin:" + authentication.getName();
    }

    @GetMapping("/user/home")
    public String user(Authentication authentication) {
        return "user:" + authentication.getName();
    }

    @GetMapping("/svc/reports")
    public String reports(Authentication authentication) {
        return "service:" + authentication.getName();
    }
}
```

Sau admin login, `GET /admin/home` trả nội dung `admin:operator`. Sau user login, `GET /user/home` trả `user:alice`. Với token service có `sub=report-worker` và scope phù hợp, `GET /svc/reports` trả `service:report-worker`. Đây là các body minh họa; trong ứng dụng thật, controller nên thực hiện quyền nghiệp vụ trên từng tài nguyên/tenant.

## 4. Vì sao service account nên dùng client credentials?

`client_credentials` là flow OAuth 2.0 cấp access token **cho chính client/workload** sau khi authorization server xác minh nó. Không cần browser, form login, `JSESSIONID`, CSRF token của người dùng hoặc vai trò mặc định `ROLE_USER`/`ROLE_ADMIN`.

```text
report-worker
     |
     | client assertion / mTLS / client secret qua HTTPS
     v
Authorization Server
     | xác minh machine identity, policy và scope
     '-- ký access token ngắn hạn
              |
              v
report-worker gửi:
Authorization: Bearer <access-token>
              |
              v
Resource Server: /svc/reports
     | JwtDecoder xác minh chữ ký, iss, aud, exp, nbf...
     | scope="reports.read" -> authority SCOPE_reports.read
     '-- GET được phép nếu đúng scope
```

Với JWT, Spring Security ánh xạ claim `scope` hoặc `scp` được xác minh thành authorities với tiền tố `SCOPE_`. Vì vậy `hasAuthority("SCOPE_reports.read")` có ý nghĩa khác `hasRole("ADMIN")`. Token có scope nhưng sai `iss`, sai `aud`, hết hạn hoặc chữ ký không hợp lệ **phải bị từ chối**, không được chỉ parse JSON rồi tin claim.

Trong production, ưu tiên client authentication mạnh như private-key JWT, mTLS hoặc workload identity phù hợp hệ thống; cấp scope tối thiểu, token sống ngắn, khóa/secret được rotate, có khả năng thu hồi và audit theo client ID. Một service token dùng ở resource server A không tự nhiên hợp lệ ở server B vì cần audience đúng.

**Không dùng một “admin service user” đăng nhập bằng form** để automation chạy nền. Làm vậy trộn quyền nhân sự với workload, khó revoke/rotate độc lập và có thể bỏ qua MFA hoặc các kiểm soát phiên của quản trị viên.

## 5. Kiểm thử tích hợp với MockMvc

Ví dụ test kiểm tra cả phân luồng chain, kho danh tính tách biệt và ranh giới stateful/stateless. Để test offline, lớp `@TestConfiguration` cung cấp một `JwtDecoder` chỉ trả dữ liệu JWT cho **hai token giả đã định sẵn**. Decoder này không xác minh mật mã, chỉ dùng để kiểm tra Resource Server filter và quyền sau khi decoder đã trả `Jwt`.

**`src/test/java/example/realms/RealmIsolationTest.java`**

```java
package example.realms;

import java.util.List;

import jakarta.servlet.http.HttpSession;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.security.oauth2.jwt.BadJwtException;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.hamcrest.Matchers.containsString;
import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class RealmIsolationTest {
    @Autowired
    MockMvc mvc;

    @TestConfiguration
    static class FakeDecoderConfig {
        @Bean
        JwtDecoder jwtDecoder() {
            return raw -> {
                if (!raw.equals("test-service-token")
                        && !raw.equals("test-no-scope-token")) {
                    throw new BadJwtException("Unknown test token");
                }

                Jwt.Builder jwt = Jwt.withTokenValue(raw)
                    .header("alg", "RS256")
                    .claim("sub", "report-worker")
                    .claim("iss", "https://idp.example.test/realms/learning")
                    .claim("aud", List.of("https://api.example.test"));

                if (raw.equals("test-service-token")) {
                    jwt.claim("scope", "reports.read");
                }
                return jwt.build();
            };
        }
    }

    private MockHttpSession loginAdmin() throws Exception {
        MvcResult result = mvc.perform(post("/admin/login")
                .with(csrf())
                .param("username", "operator")
                .param("password", "operator-pass"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/admin/home"))
            .andReturn();

        HttpSession session = result.getRequest().getSession(false);
        assertNotNull(session);
        return (MockHttpSession) session;
    }

    @Test
    void loginPagesContainCsrfFields() throws Exception {
        mvc.perform(get("/admin/login"))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(MediaType.TEXT_HTML))
            .andExpect(content().string(containsString("name=\"_csrf\"")));

        mvc.perform(get("/user/login"))
            .andExpect(status().isOk())
            .andExpect(content().string(
                containsString("action=\"/user/login\"")));
    }

    @Test
    void adminSessionCannotActAsUserSession() throws Exception {
        MockHttpSession session = loginAdmin();
        assertNotNull(session.getAttribute(SecurityConfig.ADMIN_CONTEXT));
        assertNull(session.getAttribute(SecurityConfig.USER_CONTEXT));

        mvc.perform(get("/admin/home").session(session))
            .andExpect(status().isOk())
            .andExpect(content().string("admin:operator"));

        mvc.perform(get("/user/home").session(session))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/user/login"));
    }

    @Test
    void userSessionCannotActAsAdminSession() throws Exception {
        MvcResult result = mvc.perform(post("/user/login")
                .with(csrf())
                .param("username", "alice")
                .param("password", "alice-pass"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/user/home"))
            .andReturn();

        MockHttpSession session =
            (MockHttpSession) result.getRequest().getSession(false);
        assertNotNull(session);
        assertNotNull(session.getAttribute(SecurityConfig.USER_CONTEXT));
        assertNull(session.getAttribute(SecurityConfig.ADMIN_CONTEXT));

        mvc.perform(get("/user/home").session(session))
            .andExpect(status().isOk())
            .andExpect(content().string("user:alice"));

        mvc.perform(get("/admin/home").session(session))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/admin/login"));
    }

    @Test
    void adminCredentialIsRejectedByUserLogin() throws Exception {
        mvc.perform(post("/user/login")
                .with(csrf())
                .param("username", "operator")
                .param("password", "operator-pass"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/user/login?error"));
    }

    @Test
    void userCredentialIsRejectedByAdminLogin() throws Exception {
        mvc.perform(post("/admin/login")
                .with(csrf())
                .param("username", "alice")
                .param("password", "alice-pass"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/admin/login?error"));
    }

    @Test
    void twoContextKeysCanExistInSamePhysicalSession() throws Exception {
        MockHttpSession shared = loginAdmin();

        mvc.perform(post("/user/login")
                .session(shared)
                .with(csrf())
                .param("username", "alice")
                .param("password", "alice-pass"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/user/home"));

        assertNotNull(shared.getAttribute(SecurityConfig.ADMIN_CONTEXT));
        assertNotNull(shared.getAttribute(SecurityConfig.USER_CONTEXT));

        mvc.perform(get("/admin/home").session(shared))
            .andExpect(status().isOk())
            .andExpect(content().string("admin:operator"));

        mvc.perform(get("/user/home").session(shared))
            .andExpect(status().isOk())
            .andExpect(content().string("user:alice"));
    }

    @Test
    void browserCookieCannotAuthenticateServiceApi() throws Exception {
        MockHttpSession adminSession = loginAdmin();

        mvc.perform(get("/svc/reports").session(adminSession))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void serviceTokenWithScopeCanReadReport() throws Exception {
        mvc.perform(get("/svc/reports")
                .header("Authorization", "Bearer test-service-token"))
            .andExpect(status().isOk())
            .andExpect(content().string("service:report-worker"));
    }

    @Test
    void serviceTokenWithoutScopeGets403() throws Exception {
        mvc.perform(get("/svc/reports")
                .header("Authorization", "Bearer test-no-scope-token"))
            .andExpect(status().isForbidden());
    }

    @Test
    void invalidServiceTokenGets401() throws Exception {
        mvc.perform(get("/svc/reports")
                .header("Authorization", "Bearer invalid"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void serviceBearerHeaderCannotAuthenticateAdminChain()
            throws Exception {
        mvc.perform(get("/admin/home")
                .header("Authorization", "Bearer test-service-token"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/admin/login"));
    }

    @Test
    void formLoginsRequireCsrf() throws Exception {
        mvc.perform(post("/admin/login")
                .param("username", "operator")
                .param("password", "operator-pass"))
            .andExpect(status().isForbidden());

        mvc.perform(post("/user/login")
                .param("username", "alice")
                .param("password", "alice-pass"))
            .andExpect(status().isForbidden());
    }
}
```

Chạy trong ứng dụng có Gradle wrapper:

```bash
./gradlew test --tests example.realms.RealmIsolationTest
./gradlew bootRun
```

Trên Windows dùng `gradlew.bat`. Suite chứa **12 phương thức `@Test`**. Khi chạy `bootRun` với Bearer JWT thật, cần sửa issuer/audience ví dụ thành nhà phát hành token đang hoạt động. Test sử dụng decoder giả trong `src/test` nên không phụ thuộc IdP để thực hiện các kiểm tra routing và scope.

### Đọc kết quả đúng cách

- **Browser realm:** login thật qua `POST` với CSRF; admin session có `SECCTX_ADMIN` nhưng chưa có `SECCTX_USER`, và ngược lại. Truy cập realm chưa đăng nhập chuyển tới trang login **của chính realm đó**.
- **Không trộn credential:** mật khẩu admin được gửi đến user login vẫn bị từ chối vì `appManager` không có `operator`. Hai manager tách biệt quan trọng hơn việc đặt tên URL khác nhau.
- **Cùng session vẫn hai context:** khi admin rồi user login trong cùng `MockHttpSession`, hai khóa cùng tồn tại, còn từng chain vẫn chỉ nạp khóa của mình. Điều này chứng minh tách **logical context**, không chứng minh cookie vật lý độc lập.
- **Service stateless:** cùng cookie browser không thể thỏa `/svc/reports` vì cần Bearer JWT. Không có token trả `401`.
- **Authorization của service:** JWT test có scope đúng trả `200`; thiếu scope trả `403`; decoder từ chối token trả `401`. `401` nghĩa là chưa có credential được chấp nhận; `403` nghĩa là đã xác thực nhưng không đủ quyền.
- **Không mượn Bearer để vào admin:** admin chain chỉ có form authentication, không có bearer filter. Header `Authorization: Bearer` trong request admin không làm nó trở thành admin login.
- **CSRF theo chain:** tắt CSRF trong service chain không thay đổi yêu cầu CSRF cho form login của admin/user.
- **Giới hạn bảo đảm:** decoder test không kiểm tra signature, issuer, audience, expiration, key rotation. Phải có bài tích hợp thực với IdP và token ký hợp lệ, sai chữ ký, sai issuer/audience, hết hạn và chưa có hiệu lực.

## 6. Chính sách bổ sung để thật sự tách rủi ro

### Quản trị viên

Form login admin dùng password trong ví dụ vì đơn giản để học. Trong production, cần MFA hoặc phishing-resistant authentication, step-up cho thao tác quyền cao, session idle/absolute timeout ngắn, quản lý concurrent sessions, chính sách reset/recovery riêng, audit thao tác đặc quyền. Không nên chia sẻ cookie, session store hoặc origin với portal người dùng khi yêu cầu cô lập mạnh. Mọi admin POST dùng cookie phải được CSRF bảo vệ. Hạn chế quyền theo hành động, không dùng `ROLE_ADMIN` làm quyền vạn năng.

### Người dùng cuối

User login có chính sách riêng cho rate limiting, credential stuffing, account recovery, email/phone verification khi phù hợp và bảo mật cookie. Sau khi xác thực, authorization tài nguyên còn cần kiểm tra tenant, resource ownership và quyền nghiệp vụ. Không cho phép tự nâng `REALM_USER` thành `REALM_ADMIN` bằng header hay claim do client kiểm soát.

### Tài khoản dịch vụ

Workload cần client ID/identity riêng, token scope tối thiểu, issuer/audience đúng, exp/nbf và key rotation. Không dùng email/password của nhân viên cho cron job; không ghi access token trong log; tránh token rất dài hạn; kiểm soát secret qua secret manager hoặc workload identity. Khi một service có thể gọi nhiều API, cấp token đúng audience cho từng API, thay vì sử dụng một token toàn năng. Nếu dùng mTLS, quản lý certificate lifecycle và xác nhận định danh ở tầng chấp nhận kết nối.

### Đăng xuất và thu hồi quyền

Trong demo, hai repo có khóa context riêng nhưng dùng chung HttpSession. Logout mặc định của admin hoặc user có thể invalidate cả session; nếu muốn logout riêng hoàn toàn, nên chọn session/origin riêng hoặc xây logout handler kiểm tra và xóa đúng context với semantics rõ ràng. Việc xóa authority/role trong database **không nhất thiết** làm session đang dùng cập nhật ngay: phải định nghĩa refresh, reauthentication hoặc thu hồi session. Tương tự, JWT service còn hạn có thể tiếp tục được chấp nhận theo chính sách dù quyền ở phía IdP vừa thay đổi; cân nhắc token sống ngắn hoặc introspection/revocation phù hợp.

## 7. Lỗi thường gặp

| Sai lầm | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Chỉ tách `/admin/login`, `/user/login` | Có thể vẫn chung user store, manager, context | Tách nguồn danh tính, manager, repo và authorization |
| Thêm nhiều chain nhưng không kiểm tra thứ tự | Chain rộng bắt request trước chain cụ thể | `@Order` rõ ràng, test URL và fallback |
| `securityMatcher("/admin/**")` + xử lý form ở `/login` | POST không đi vào admin chain | URL xử lý đăng nhập phải nằm trong chain |
| Mong Spring Security tự sinh trang sau `loginPage(custom)` | GET login 404 | Cung cấp GET HTML form và CSRF token |
| Chỉ dùng `anyRequest().authenticated()` cho admin | Danh tính hợp lệ ở realm khác có thể bị chấp nhận nếu context chung | Kiểm tra cả realm và role với repo đúng |
| Dùng chung `SPRING_SECURITY_CONTEXT` cho hai realm | Có thể vô tình tái dùng Authentication | Repo với khóa riêng hoặc tách session vật lý |
| Nghĩ hai khóa context có nghĩa hai cookie | Mất một cookie vẫn ảnh hưởng cả hai | Tách origin/cookie/store để cô lập thực sự |
| Bật form/httpBasic trong service API | Workload có thể dùng account con người hoặc được browser gửi cookie | JWT bearer/mTLS stateless với scope |
| Parse JWT không xác minh chữ ký | Client có thể tự gắn scope/admin claim | JwtDecoder xác minh cryptographic signature, iss/aud/time |
| Dùng `hasRole("ADMIN")` cho service | Trộn namespace quyền người và máy | Dùng `SCOPE_*` cho service; role riêng |
| Chỉ test bằng decoder giả rồi kết luận JWT production an toàn | Chưa test issuer/audience/signature | E2E/integration với IdP thật và token lỗi |
| Không có fallback chain | URL mới có thể bỏ qua Spring Security | Catch-all denyAll |
| Để secret, cookie, token trong logs | Rò rỉ quyền truy cập | Redaction, audit metadata và secret rotation |
| Xóa role ở DB nhưng không nghĩ tới session/JWT đang sống | Quyền cũ có thể tiếp tục đến khi hết hạn | Định nghĩa refresh/revoke/step-up policy |
| Cho rằng login admin đủ bảo vệ thao tác cực nhạy | Credential bị lộ vẫn đủ quyền thay đổi hệ thống | MFA, step-up, kiểm soát hành động và audit |

## 8. Checklist hoàn thành

- [ ] Request tới `/admin/**`, `/user/**`, `/svc/**` chọn đúng chain theo thứ tự.
- [ ] Hai form login có GET page, POST processing URL và CSRF token nằm trong matcher.
- [ ] Admin và user dùng authentication manager, nguồn danh tính riêng; không dùng credential chéo.
- [ ] Admin endpoint yêu cầu `REALM_ADMIN` + `ROLE_ADMIN`; user endpoint yêu cầu `REALM_USER` + `ROLE_USER`.
- [ ] Context admin/user lưu dưới khóa riêng; test cả truy cập lẫn trường hợp cùng HttpSession.
- [ ] Xác định giới hạn cô lập của việc dùng chung cookie/session; có chính sách logout, timeout, session fixation và physical isolation phù hợp.
- [ ] Service API xác thực Bearer JWT, không dùng browser cookie hoặc form login.
- [ ] JWT được kiểm tra signature, issuer, audience, expiry và scope từ nguồn tin cậy; test integration thật ngoài các test giả lập.
- [ ] Scope `reports.read` được ánh xạ `SCOPE_reports.read`, không nhầm với role của con người.
- [ ] Thiếu token trả `401`, token hợp lệ thiếu scope trả `403`, form chưa login redirect tới login tương ứng.
- [ ] Chain mặc định từ chối endpoint không được khai báo.
- [ ] Admin production yêu cầu MFA/step-up, monitoring và audit; service token có rotation/revocation và quyền tối thiểu.

### Tài liệu chính thức

- [Spring Security 6.5 — Multiple HttpSecurity, securityMatcher và login endpoints](https://docs.spring.io/spring-security/reference/6.5/servlet/configuration/java.html)
- [Spring Security — FilterChainProxy và nhiều SecurityFilterChain](https://docs.spring.io/spring-security/reference/6.5/servlet/architecture.html)
- [Spring Security — Authentication Architecture / ProviderManager](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html)
- [Spring Security — Persisting Authentication](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/persistence.html)
- [HttpSessionSecurityContextRepository — setSpringSecurityContextKey](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/context/HttpSessionSecurityContextRepository.html)
- [Spring Security — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/jwt.html)
- [Spring Security — OAuth2 Client Credentials](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/index.html)
- [Spring Security — Servlet CSRF](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html)
