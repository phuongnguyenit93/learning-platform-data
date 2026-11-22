# 33.3. Chuyển cấu hình adapter cũ sang SecurityFilterChain

## 1. Bài toán nâng cấp

Một ứng dụng **Employee Portal** được viết bằng Spring Boot 2 và Spring Security 5, cho nhân viên đăng nhập OpenID Connect (OIDC), gọi Orders API bằng access token và phân quyền các trang quản trị. Cấu hình cũ dựa trên `WebSecurityConfigurerAdapter`:

~~~java
// LEGACY ONLY — không biên dịch trên Spring Security 6.
@Configuration
@EnableWebSecurity
public class LegacySecurityConfig extends WebSecurityConfigurerAdapter {

    @Override
    protected void configure(HttpSecurity http) throws Exception {
        http
            .authorizeRequests()
                .antMatchers("/", "/login", "/assets/**").permitAll()
                .antMatchers("/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated()
                .and()
            .oauth2Login()
                .loginPage("/login")
                .and()
            .oauth2Client();
    }
}
~~~

Khi nâng cấp **Spring Boot 3 / Spring Security 6**, class adapter đã bị loại bỏ; các DSL cũ như `antMatchers()` và `.and()` cũng cần thay. Cấu hình mới được khai báo qua **`@Bean SecurityFilterChain`**:

~~~java
@Configuration
@EnableWebSecurity
public class SecurityConfig {

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/login", "/assets/**")
                    .permitAll()
                .requestMatchers("/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated()
            )
            .oauth2Login(oauth -> oauth
                .loginPage("/login")
            )
            .oauth2Client(Customizer.withDefaults());

        return http.build();
    }
}
~~~

Đây là **component-based configuration**: thay việc kế thừa class adapter bằng việc cung cấp beans cho Spring Security.

**Điểm quan trọng:** ứng dụng compile/start được không có nghĩa đã migrate đúng. Browser login, redirect/callback URI, state/nonce/PKCE, session/CSRF, OIDC claims/authorities, authorized-client tokens, logout và API permissions đều cần được giữ đúng.

> Phạm vi: Java 17+, Spring MVC/Servlet, Spring Boot 3, Spring Security 6, OAuth2 Login và OIDC Client. Bài cũng nêu cách xử lý vendor adapter đời cũ và phân biệt với WebFlux/Resource Server. Code mang tính minh họa, không sử dụng secrets hoặc token production.

## 2. Mục tiêu học tập

Sau bài này, người học cần:

1. Hiểu vì sao `WebSecurityConfigurerAdapter` được thay bằng beans.
2. Chuyển `configure(HttpSecurity)` thành `SecurityFilterChain`.
3. Thay `authorizeRequests()/antMatchers()` bằng `authorizeHttpRequests()/requestMatchers()`.
4. Phân biệt `securityMatcher` với `requestMatchers`.
5. Duy trì OAuth2 Login, OIDC callback và authorized-client management.
6. Chuyển custom login page, user service, success/failure handlers, logout.
7. Chuyển `configure(WebSecurity)` và authentication components đúng cách.
8. Tách browser OIDC session chain khỏi Bearer Resource Server API chain nếu cần.
9. Hiểu tác động của Jakarta Servlet, Spring Boot 3, CSRF, proxy và sessions.
10. Kiểm thử hồi quy hành vi bảo mật, chuẩn bị rollout/rollback.

## 3. Bảng đối chiếu API cũ và mới

| Spring Security cũ | Spring Security 6 / cấu hình mới | Ý nghĩa |
|---|---|---|
| `extends WebSecurityConfigurerAdapter` | `@Bean SecurityFilterChain` | Không kế thừa adapter |
| `configure(HttpSecurity)` | Bean method nhận `HttpSecurity`, gọi `http.build()` | HTTP security |
| `authorizeRequests()` | `authorizeHttpRequests(auth -> ...)` | AuthorizationManager-style |
| `antMatchers(...)` | `requestMatchers(...)` | URL matching rules |
| `mvcMatchers(...)` | `requestMatchers(...)` hoặc RequestMatcher cụ thể | Xem servlet/path semantics |
| `http.antMatcher(...)` | `http.securityMatcher(...)` | Giới hạn phạm vi cả filter chain |
| Chain DSL `.and()` | Lambda DSL | Cấu hình rõ từng configurer |
| `configure(WebSecurity)` | `WebSecurityCustomizer` nếu cần | Cẩn thận bypass filters |
| `configure(AuthenticationManagerBuilder)` | UserDetailsService, providers, AuthenticationManager beans | Phân tách authentication |
| `@EnableGlobalMethodSecurity` | `@EnableMethodSecurity` | Method security |
| `javax.servlet.*` | `jakarta.servlet.*` | Spring Boot 3/Jakarta |

Spring Security đã hỗ trợ cách khai báo `SecurityFilterChain` từ trước 6.x, rồi deprecate WebSecurityConfigurerAdapter trong nhánh 5.7. Lambda DSL là cách nên dùng khi viết cấu hình mới.

## 4. Vì sao component-based configuration tốt hơn?

~~~mermaid
flowchart TD
    A["Legacy WebSecurityConfigurerAdapter"] --> B["configure(HttpSecurity)"]
    A --> C["configure(WebSecurity)"]
    A --> D["configure(AuthenticationManagerBuilder)"]
    B --> E["New @Bean SecurityFilterChain"]
    C --> F["New WebSecurityCustomizer only if needed"]
    D --> G["New AuthenticationManager / authentication beans"]
    E --> H["FilterChainProxy"]
    I["OAuth2 Client beans"] --> H
~~~

Ưu điểm:

- Không bị khóa vào một class base phải override.
- Có thể có **nhiều SecurityFilterChain** với phạm vi và thứ tự rõ.
- Authentication providers, OIDC user mapping, authorized-client managers và HTTP security được cấu hình độc lập.
- Dễ thay thế từng thành phần cho integration tests.

Nhưng nhiều beans cũng làm phát sinh rủi ro **bean trùng**, **filter chain order sai** hoặc **một path nằm ngoài mọi chain**. Vì vậy migration cần test.

## 5. Bước chuẩn bị: ghi lại security contract cũ

Đừng sửa code ngay trước khi liệt kê hành vi hiện tại:

| Hành vi | Thông tin cần lấy từ adapter cũ |
|---|---|
| Public URLs | `/`, `/login`, assets, health |
| Protected URLs | Browser pages, admin pages, JSON APIs |
| Authorities | ROLE_ADMIN, scopes, tenant permissions |
| OAuth2 registration IDs | `company`, `partner`, ... |
| Login page | Tự dựng hay generated page |
| Authorization request | Default URI hay custom resolver |
| Redirect callback | Base URI, redirect_uri |
| User mapping | OidcUserService, OAuth2UserService, groups/claims |
| Success/failure | Redirect, audit, provisioning |
| Authorized clients | Session, JDBC, Redis hoặc service |
| HTTP client | WebClient, RestClient, RestTemplate |
| Session/CSRF | SessionCreationPolicy, CSRF exemptions |
| Logout | Local logout, OP logout, token revocation |
| Filter order | Custom filters và adapter order |

Khi thay cấu hình, mục tiêu là bảo toàn các thuộc tính này hoặc thay đổi có chủ đích.

## 6. Cấu hình adapter cũ có nhiều responsibilities

Ví dụ lịch sử đầy đủ:

~~~java
// Chỉ dùng để đọc và đối chiếu dự án Spring Security 5.
@Configuration
@EnableWebSecurity
@EnableGlobalMethodSecurity(prePostEnabled = true)
public class LegacyPortalSecurity
        extends WebSecurityConfigurerAdapter {

    @Override
    protected void configure(HttpSecurity http) throws Exception {
        http
            .authorizeRequests()
                .antMatchers(
                    "/", "/login", "/assets/**", "/error"
                ).permitAll()
                .antMatchers("/admin/**").hasRole("ADMIN")
                .antMatchers("/api/**").authenticated()
                .anyRequest().authenticated()
                .and()
            .oauth2Login()
                .loginPage("/login")
                .defaultSuccessUrl("/home", false)
                .and()
            .oauth2Client()
                .and()
            .logout()
                .logoutSuccessUrl("/");
    }

    @Override
    public void configure(WebSecurity web) {
        web.ignoring().antMatchers("/favicon.ico");
    }
}
~~~

Cần giữ:

~~~text
/                     public
/login                public
/assets/**            public
/error                public
/admin/**             ROLE_ADMIN
/api/**               authenticated
everything else       authenticated
OIDC login            active
OAuth2 client         active
custom login page     /login
post-login landing    /home unless saved request wins
logout success        /
~~~

Cũng cần xem lại `web.ignoring()`: nó bỏ qua filter chain hoàn toàn, khác với `permitAll()`.

## 7. Cấu hình mới tương đương với SecurityFilterChain

~~~java
package com.example.portal.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration
    .EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration
    .EnableWebSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableWebSecurity
@EnableMethodSecurity
public class PortalSecurityConfiguration {

    @Bean
    SecurityFilterChain portalFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(
                    "/", "/login", "/assets/**",
                    "/favicon.ico", "/error"
                ).permitAll()
                .requestMatchers("/admin/**").hasRole("ADMIN")
                .requestMatchers("/api/**").authenticated()
                .anyRequest().authenticated()
            )
            .oauth2Login(oauth -> oauth
                .loginPage("/login")
                .defaultSuccessUrl("/home", false)
            )
            .oauth2Client(Customizer.withDefaults())
            .logout(logout -> logout
                .logoutSuccessUrl("/")
            );

        return http.build();
    }
}
~~~

Các điểm mới:

1. Không còn class extends adapter.
2. `@Bean SecurityFilterChain` nhận `HttpSecurity` do Spring inject.
3. `authorizeHttpRequests` và `requestMatchers` thay DSL cũ.
4. `oauth2Login` giữ browser OAuth/OIDC login.
5. `oauth2Client` giữ các OAuth2 Client features cần cho authorized clients.
6. `http.build()` tạo chain.

### 7.1. Không nhất thiết khai báo mọi bean bằng tay

Spring Boot có thể tạo `ClientRegistrationRepository` và authorized-client components từ properties. Nếu không cần custom manager/repository, đừng tự tạo một bản sao khiến auto-configuration bị thay.

### 7.2. @EnableWebSecurity có bắt buộc không?

Spring Boot thường hỗ trợ auto-configuration cho Security, nhưng khai báo `@EnableWebSecurity` giúp cấu hình Java tự thể hiện ý định. Quan trọng là tránh hai filter chains không mong muốn do import nhiều cấu hình.

### 7.3. Không dành cho WebFlux

Nếu ứng dụng thực sự dùng WebFlux Reactive, tương ứng là `SecurityWebFilterChain(ServerHttpSecurity)`, không phải `SecurityFilterChain(HttpSecurity)`.

## 8. Lambda DSL và Customizer.withDefaults()

Trước:

~~~java
http
    .authorizeRequests().anyRequest().authenticated()
    .and()
    .oauth2Login()
    .and()
    .oauth2Client();
~~~

Sau:

~~~java
http
    .authorizeHttpRequests(auth -> auth
        .anyRequest().authenticated()
    )
    .oauth2Login(Customizer.withDefaults())
    .oauth2Client(Customizer.withDefaults());
~~~

Lambda DSL không cần `.and()__ vì sau mỗi lambda, cấu hình trở lại `HttpSecurity`.

`Customizer.withDefaults()` nghĩa là bật module bằng cấu hình mặc định, không đồng nghĩa mọi chính sách security/business đều đã phù hợp.

### 8.1. Custom DSL riêng

Nếu adapter cũ dùng custom `AbstractHttpConfigurer`, ở các bản Spring Security 6.2+ nên xem khả năng `http.with(customDsl, customizer)` thay cho `http.apply(customDsl)` vốn bị deprecated trong hướng tới Spring Security 7. Điều chỉnh theo version thực tế.

### 8.2. Tránh gọi build() hai lần

`HttpSecurity` là builder của một SecurityFilterChain. Đừng tái sử dụng builder đã build cho chain khác.

## 9. requestMatchers() không giống securityMatcher()

`requestMatchers()` trong `authorizeHttpRequests` là **authorization policy bên trong một chain**:

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/admin/**").hasRole("ADMIN")
    .anyRequest().authenticated());
~~~

`securityMatcher()` là **điều kiện chọn cả chain**:

~~~java
http.securityMatcher("/api/**");
~~~

### 9.1. Lỗi rất thường gặp: OIDC callback ngoài chain

~~~java
@Bean
SecurityFilterChain apiOnly(HttpSecurity http) throws Exception {
    http.securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated())
        .oauth2Login(Customizer.withDefaults());
    return http.build();
}
~~~

Nhưng OAuth2 Login mặc định sử dụng:

~~~text
/oauth2/authorization/{registrationId}
/login/oauth2/code/{registrationId}
~~~

Hai đường dẫn này không thuộc `/api/**`. Nếu không có chain khác chứa login filters, login initiation/callback không hoạt động.

### 9.2. Một chain fallback bảo vệ mọi request

Với browser app, nên có chain không đặt `securityMatcher` để làm fallback, hoặc bảo đảm tất cả endpoints cần thiết đã được match bằng một tập chain có chủ đích.

### 9.3. Không có chain match thì sao?

Request không match chain nào có thể **không đi qua Spring Security filters**. `anyRequest().authenticated()` trong chain `/api/**` không bảo vệ `/admin/**`.

## 10. Chuyển antMatchers/mvcMatchers có lưu ý về path

Cũ:

~~~java
.antMatchers(HttpMethod.GET, "/catalog/**").permitAll()
.antMatchers("/admin/**").hasRole("ADMIN")
~~~

Mới:

~~~java
.requestMatchers(HttpMethod.GET, "/catalog/**").permitAll()
.requestMatchers("/admin/**").hasRole("ADMIN")
~~~

Spring Security 6 hỗ trợ `requestMatchers(...)` theo path/method, nhưng ứng dụng có **nhiều Servlets**, custom servlet path hoặc URL parsing đặc biệt nên chọn một `RequestMatcher` cụ thể và viết tests để xác nhận semantics.

### 10.1. Đừng vô tình permit POST

~~~java
.requestMatchers(HttpMethod.GET, "/catalog/**").permitAll()
.requestMatchers(HttpMethod.POST, "/catalog/**")
    .hasRole("EDITOR")
~~~

Không thay bằng `.requestMatchers("/catalog/**").permitAll()` vì có thể mở quyền ghi dữ liệu.

### 10.2. Context path khác servlet path

Nếu ứng dụng deploy với `server.servlet.context-path` hoặc custom `spring.mvc.servlet.path`, cần kiểm tra matcher thực tế; đừng tự chắp context prefix vào rule mà không hiểu matcher API.

### 10.3. Thứ tự rules

Rule rộng đặt trước có thể che rules hẹp. Sắp xếp public endpoints có kiểm soát, rules đặc thù rồi tới `anyRequest()`.

## 11. Spring Boot 3, Java 17 và Jakarta Servlet

Nâng Spring Boot 2 lên 3 đồng thời chuyển nền tảng:

~~~text
Java 17+
Spring Framework 6
Spring Security 6
Jakarta EE namespace
~~~

Ví dụ custom filter:

~~~java
// Cũ:
import javax.servlet.FilterChain;
import javax.servlet.http.HttpServletRequest;

// Mới:
import jakarta.servlet.FilterChain;
import jakarta.servlet.http.HttpServletRequest;
~~~

Đừng thay toàn bộ namespace `javax` trong Java SE; ví dụ `javax.net.ssl` không biến thành `jakarta.net.ssl`.

### 11.1. Không trộn jars Spring Security 5 và 6

Nếu thiếu `WebSecurityConfigurerAdapter`, giải pháp không phải thêm spring-security-config 5.x vào Boot 3. Hãy migrate code và dùng dependency management/BOM tương thích.

### 11.2. JPA, Validation và các APIs khác

Những phần Jakarta Persistence/Validation cũng có thể phải cập nhật imports. Chúng nằm ngoài cấu hình OIDC nhưng có thể chặn ứng dụng boot/test khi migration.

## 12. ClientRegistration vẫn là phần cốt lõi

`SecurityFilterChain` không tự chứa client ID, secret hay issuer. Spring Boot có thể đọc:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company-oidc
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
              - orders.read
        provider:
          company-oidc:
            issuer-uri: https://login.company.example/realms/employees
~~~

`company` là **registration ID**; `company-oidc` là **provider alias**.

### 12.1. Scope openid

Khi requested scopes có `openid`, Spring Security thực hiện OIDC login với ID Token/OidcUser behavior thích hợp. Không coi access token là ID Token.

### 12.2. Secrets

Đưa client secret vào secret manager hoặc runtime environment, không commit vào source. Khi đổi app/version, xác nhận cùng client registration ở OP và secret version đúng.

### 12.3. Issuer discovery

`issuer-uri` có thể khiến app thực hiện OIDC discovery để xây provider metadata. Integration tests nên dùng fake metadata/ClientRegistration để không gọi IdP production.

### 12.4. Registration ID có thể là storage key

Đổi registration ID có thể ảnh hưởng:

~~~text
/oauth2/authorization/{registrationId}
/login/oauth2/code/{registrationId}
authorized client lookup by registrationId
~~~

Vì vậy không đổi ID chỉ để “đẹp tên” mà bỏ qua redirects và token store.

## 13. oauth2Login() và oauth2Client() khác nhiệm vụ

~~~java
http
    .oauth2Login(Customizer.withDefaults())
    .oauth2Client(Customizer.withDefaults());
~~~

`oauth2Login()` xử lý **browser login** và tạo authenticated principal/session.

`oauth2Client()` hỗ trợ **OAuth2 Client authorization/authorized clients** phục vụ gọi downstream API với access token.

Một Browser OIDC login thành công không chứng minh:

- Orders API sẽ chấp nhận access token.
- Access token chưa hết hạn.
- Authorized-client repository/service đang lưu token ở đúng nơi.
- ClientRegistration khác đã được user cấp consent.

### 13.1. Resource Server là một vai trò riêng

`oauth2ResourceServer(server -> server.jwt(...))` dùng cho API **nhận Bearer access token**, không thay thế Authorization Code browser login.

## 14. Custom login page sau migration

Khi khai báo:

~~~java
.oauth2Login(oauth -> oauth.loginPage("/login"))
~~~

ứng dụng cần có trang/route `/login` và permit anonymous:

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/login", "/assets/**").permitAll()
    .anyRequest().authenticated())
~~~

Controller:

~~~java
@Controller
class LoginPageController {
    @GetMapping("/login")
    String login() {
        return "login";
    }
}
~~~

HTML:

~~~html
<a href="/oauth2/authorization/company">
  Đăng nhập bằng Company SSO
</a>
~~~

### 14.1. Đừng nhầm trang login với OAuth authorization endpoint

`/login` là UI của Portal. `/oauth2/authorization/company` là endpoint Spring Security bắt đầu redirect sang OP.

### 14.2. Login redirect loop

Nếu `/login` cũng đòi authenticated, anonymous browser có thể bị redirect về chính login page vô hạn. Test truy cập `/login` không có session.

### 14.3. Custom login page không tự có view

Khi set `loginPage("/login")`, Spring không mặc định tạo template thay bạn. Cần actual controller/view hoặc endpoint phù hợp.

## 15. Authorization request và callback URI

Các URI mặc định:

~~~text
Start:    /oauth2/authorization/{registrationId}
Callback: /login/oauth2/code/{registrationId}
~~~

Khi cần custom:

~~~java
http.oauth2Login(oauth -> oauth
    .authorizationEndpoint(auth -> auth
        .baseUri("/sso/authorize"))
    .redirectionEndpoint(redirection -> redirection
        .baseUri("/sso/callback/*")));
~~~

thì cấu hình registration:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            redirect-uri: "{baseUrl}/sso/callback/{registrationId}"
~~~

Link bắt đầu login:

~~~text
/sso/authorize/company
~~~

### 15.1. Ba điểm phải khớp

1. URL authorization initiation.
2. Callback matcher của Spring Security.
3. Redirect URI tại OAuth2 ClientRegistration và đã đăng ký ở OP.

Nếu chỉ sửa một, có thể gặp `invalid_redirect_uri`, callback 404 hoặc `authorization_request_not_found`.

### 15.2. State, nonce, PKCE

Không bỏ `state`, `nonce` hoặc PKCE code verifier khi migrate custom authorization request resolver/repository. Chúng gắn browser callback với original authorization request.

## 16. Custom AuthorizationRequestRepository

Adapter cũ:

~~~java
http.oauth2Login()
    .authorizationEndpoint()
    .authorizationRequestRepository(customRepository);
~~~

Lambda DSL:

~~~java
http.oauth2Login(oauth -> oauth
    .authorizationEndpoint(auth -> auth
        .authorizationRequestRepository(customRepository)));
~~~

`customRepository` là implementation của:

~~~java
AuthorizationRequestRepository<OAuth2AuthorizationRequest>
~~~

Default Servlet login thường lưu original authorization request vào HttpSession. Nếu dùng cookie repository custom, phải có integrity/TTL/SameSite/Secure/HttpOnly và replay protection phù hợp.

### 16.1. Không dùng ThreadLocal thay session

OIDC authorization có browser redirect; callback đến request khác, thậm chí node khác. ThreadLocal không thể lưu original state cho flow này.

### 16.2. Multi-node session store

Ứng dụng nhiều pods có thể dùng Spring Session Redis/JDBC hoặc giải pháp session continuity khác. Migration SecurityFilterChain không tự tạo shared session.

## 17. OIDC user mapping và authorities

Legacy app có thể dùng custom `OidcUserService` hoặc vendor role mapper. DSL mới:

~~~java
http.oauth2Login(oauth -> oauth
    .userInfoEndpoint(userInfo -> userInfo
        .oidcUserService(appOidcUserService)));
~~~

Một bean service minh họa:

~~~java
@Bean
OAuth2UserService<OidcUserRequest, OidcUser>
appOidcUserService() {
    OidcUserService delegate = new OidcUserService();

    return request -> {
        OidcUser user = delegate.loadUser(request);
        Set<GrantedAuthority> authorities =
            new HashSet<>(user.getAuthorities());

        Object groups = user.getClaims().get("groups");
        if (groups instanceof Collection<?> values
                && values.contains("portal-admins")) {
            authorities.add(
                new SimpleGrantedAuthority("ROLE_ADMIN"));
        }

        if (user.getUserInfo() == null) {
            return new DefaultOidcUser(
                authorities, user.getIdToken(), "sub");
        }
        return new DefaultOidcUser(
            authorities,
            user.getIdToken(),
            user.getUserInfo(),
            "sub"
        );
    };
}
~~~

Đây là **mẫu mapping**, không phải policy đúng cho mọi IdP. Cần xác minh provider claims contract, issuer, tenant membership và nguồn cấp roles.

### 17.1. OAuth2UserService vs OidcUserService

Trong `userInfoEndpoint`, `userService(...)` phục vụ OAuth2 UserInfo chung; `oidcUserService(...)` phục vụ OIDC login. Dùng đúng hook tùy login type.

### 17.2. Role mapping không tự diễn ra

`hasRole("ADMIN")` thường kiểm tra `ROLE_ADMIN`. Một claim JSON `{"roles":["admin"]}` không tự thành GrantedAuthority nếu chưa mapping.

### 17.3. Identity mapping

User identity nên dựa trên trusted `(issuer, subject)` và tenant mapping khi có nhiều tổ chức, không tự gộp user chỉ bởi email.

## 18. Success/failure handlers

Trước:

~~~java
.oauth2Login()
    .successHandler(loginSuccessHandler)
    .failureHandler(loginFailureHandler)
~~~

Sau:

~~~java
http.oauth2Login(oauth -> oauth
    .successHandler(loginSuccessHandler)
    .failureHandler(loginFailureHandler));
~~~

Các handlers có thể thực hiện:

- Provisioning/link internal user.
- Kiểm tra tenant membership.
- Audit login success/failure.
- Redirect đến saved request hoặc default page.
- Hiển thị lỗi hợp lý khi OP từ chối.

### 18.1. SavedRequest

`defaultSuccessUrl("/home", false)` thường tôn trọng request ban đầu đã lưu. Nếu thay bằng custom handler luôn redirect `/home`, user có thể mất vị trí đang truy cập trước login.

### 18.2. Không biến handler thành bypass

Success handler không được chấp nhận ID Token sai signature/issuer/audience; nó chạy sau authentication success. Failure handler cũng không được tự tạo authenticated principal khi callback thất bại.

### 18.3. Sanitized errors

Không đưa raw provider error description, authorization code, access token, client secret hoặc ID Token vào log/browser.

## 19. Authorized-client persistence nằm ngoài HTTP rules

`OAuth2AuthorizedClient` bao gồm:

~~~text
ClientRegistration
principalName
OAuth2AccessToken
OAuth2RefreshToken (nếu có)
~~~

Các types:

~~~java
OAuth2AuthorizedClientRepository
OAuth2AuthorizedClientService
OAuth2AuthorizedClientManager
~~~

Repository thường quản lý authorized clients giữa Servlet requests (có thể dựa trên HttpSession). Service quản lý ở application level (in-memory/JDBC/custom).

### 19.1. Migration không đồng nghĩa xóa token store

Nếu hệ cũ lưu refresh tokens ở JDBC/Redis, chuyển vô tình sang InMemory store có thể làm tokens mất khi restart và gây reauthorization/token endpoint overload.

### 19.2. Registration/principal chính xác

Không cache token chỉ theo email hoặc username. Authorized client phải gắn đúng registration và trusted principal; multi-tenant cần partition tương ứng.

## 20. OAuth2AuthorizedClientManager cho Servlet request

Khi cần manager custom:

~~~java
@Bean
OAuth2AuthorizedClientManager authorizedClientManager(
    ClientRegistrationRepository registrations,
    OAuth2AuthorizedClientRepository repository
) {
    OAuth2AuthorizedClientProvider provider =
        OAuth2AuthorizedClientProviderBuilder.builder()
            .authorizationCode()
            .refreshToken()
            .clientCredentials()
            .build();

    DefaultOAuth2AuthorizedClientManager manager =
        new DefaultOAuth2AuthorizedClientManager(
            registrations, repository);
    manager.setAuthorizedClientProvider(provider);
    return manager;
}
~~~

`DefaultOAuth2AuthorizedClientManager` dành cho `HttpServletRequest` context, có thể load/save authorized clients và refresh theo provider chain.

### 20.1. Không tạo manager thừa

Một số phiên bản Spring Security có thể cung cấp default manager bean; chỉ customize nếu cần grant/provider/error handler/persistence đặc thù.

### 20.2. Custom success/failure handlers

Nếu thay các handlers mà không persist token mới, token endpoint có thể bị gọi mỗi request. Nếu failure handler xóa token quá rộng, có thể làm mất authorized clients của user/tenant khác.

### 20.3. Không tự tăng scopes bằng refresh

Refresh token không tự cấp thêm quyền mới. API trả 403 insufficient_scope cần kiểm tra consent/RBAC/authorization contract, không refresh vô hạn.

## 21. Background jobs dùng service-based manager

Một scheduled task `client_credentials` không có browser HttpServletRequest. Dùng:

~~~java
@Bean
AuthorizedClientServiceOAuth2AuthorizedClientManager
serviceAuthorizedClientManager(
    ClientRegistrationRepository registrations,
    OAuth2AuthorizedClientService service
) {
    OAuth2AuthorizedClientProvider provider =
        OAuth2AuthorizedClientProviderBuilder.builder()
            .clientCredentials()
            .build();

    var manager =
        new AuthorizedClientServiceOAuth2AuthorizedClientManager(
            registrations, service);
    manager.setAuthorizedClientProvider(provider);
    return manager;
}
~~~

Request:

~~~java
OAuth2AuthorizeRequest request = OAuth2AuthorizeRequest
    .withClientRegistrationId("reports-service")
    .principal("reports-job")
    .build();

OAuth2AuthorizedClient authorized =
    manager.authorize(request);
~~~

`reports-job` là service storage principal, không phải nhân viên đăng nhập OIDC. Trong production, registration và service identity phải xuất phát từ trusted job configuration.

## 22. WebClient hoặc RestClient sau khi bỏ adapter

Với Servlet:

~~~java
ServletOAuth2AuthorizedClientExchangeFilterFunction
~~~

cho phép tích hợp OAuth2 Client với WebClient. Spring Security 6.4+ cũng có:

~~~java
OAuth2ClientHttpRequestInterceptor
~~~

cho RestClient.

### 22.1. WebClient ví dụ

~~~java
@Bean
WebClient ordersWebClient(OAuth2AuthorizedClientManager manager) {
    var oauth =
        new ServletOAuth2AuthorizedClientExchangeFilterFunction(manager);

    return WebClient.builder()
        .baseUrl("https://orders.example.test")
        .apply(oauth.oauth2Configuration())
        .build();
}
~~~

Request tường minh:

~~~java
import static org.springframework.security.oauth2.client.web
    .reactive.function.client
    .ServletOAuth2AuthorizedClientExchangeFilterFunction
    .clientRegistrationId;

Mono<String> orders = ordersWebClient.get()
    .uri("/api/orders")
    .attributes(clientRegistrationId("company"))
    .retrieve()
    .bodyToMono(String.class);
~~~

### 22.2. Không tự forward Bearer token sang URL bất kỳ

Nếu request parameter quyết định host:

~~~text
?target=https://untrusted.example
~~~

và WebClient gắn token vào Authorization header, có thể làm lộ access token. Bind registration và destination bằng trusted allowlist.

### 22.3. Downstream errors khác login errors

Orders API `401 Bearer invalid_token` khác Portal browser chưa authenticated; `403 insufficient_scope` khác expired session. Không logout user trên mọi HTTP 401 hoặc xóa authorized client trên 429/5xx.

## 23. Session là cơ chế quan trọng của browser login

OIDC authorization code login Servlet thường cần lưu:

~~~text
OAuth2AuthorizationRequest
state
nonce
PKCE code_verifier theo flow
SecurityContext
SavedRequest
~~~

Do đó:

~~~java
.sessionManagement(session -> session
    .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
~~~

**không phù hợp một cách mặc định** với browser OIDC login dựa trên HttpSession.

### 23.1. API bearer-only có thể stateless

Tách API Resource Server chain nếu muốn stateless JWT; giữ browser login chain có session policy phù hợp.

### 23.2. Session fixation

Spring Security có session fixation protection như thay session ID sau authentication. Test cần bảo đảm callback được correlated trước login và session mới vẫn mang authenticated state.

### 23.3. Multi-node

Nhiều pods cần shared session storage/routing strategy; chỉ đổi adapter không sửa session continuity.

## 24. CSRF: không vô tình disable cho browser

Một migration sai thường làm:

~~~java
.csrf(csrf -> csrf.disable())
~~~

trên toàn app chỉ vì POST test nhận 403. Với browser session/cookie authentication, CSRF protection thường vẫn cần.

### 24.1. Chỉ miễn trừ khi có lý do

~~~java
.csrf(csrf -> csrf
    .ignoringRequestMatchers("/webhooks/provider"))
~~~

Webhook phải được xác thực theo cơ chế riêng (HMAC/mTLS hoặc provider verification), không được chỉ “permit” vì là webhook.

### 24.2. Với Bearer-only stateless APIs

API chỉ nhận Authorization Bearer header, không dựa vào auto-sent browser cookies, có thể dùng policy khác. Cân nhắc tách SecurityFilterChain.

### 24.3. MockMvc

~~~java
mockMvc.perform(post("/api/settings")
        .with(oidcLogin())
        .with(csrf()))
    .andExpect(status().isOk());
~~~

`csrf()` đến từ `SecurityMockMvcRequestPostProcessors`. Nếu test bị 403 khi POST, kiểm tra CSRF và roles, không chỉ OAuth token.

## 25. Hai SecurityFilterChains: browser OIDC và external Bearer API

~~~java
@Configuration
@EnableWebSecurity
public class MultiChainSecurity {

    @Bean
    @Order(1)
    SecurityFilterChain externalApi(HttpSecurity http)
            throws Exception {
        http
            .securityMatcher("/api/external/**")
            .authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated())
            .sessionManagement(session -> session
                .sessionCreationPolicy(
                    SessionCreationPolicy.STATELESS))
            .csrf(csrf -> csrf.disable())
            .oauth2ResourceServer(server -> server
                .jwt(Customizer.withDefaults()));
        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain browser(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(
                    "/", "/login", "/assets/**", "/error"
                ).permitAll()
                .requestMatchers("/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .oauth2Client(Customizer.withDefaults());
        return http.build();
    }
}
~~~

### 25.1. Chain order

FilterChainProxy chọn chain đầu tiên match request. API chain ở `@Order(1)` bắt `/api/external/**` trước; browser fallback chain ở `@Order(2)` bắt những routes khác.

### 25.2. Callback vẫn được bảo vệ

Browser chain không có `securityMatcher` nên còn match:

~~~text
/oauth2/authorization/company
/login/oauth2/code/company
~~~

### 25.3. Khi nào API disable CSRF trong ví dụ hợp lý?

Chỉ khi API chain này **Bearer-only**, stateless, không dùng browser cookie auth. Nếu API còn nhận session cookie thì không tự disable CSRF.

## 26. configure(AuthenticationManagerBuilder) sau migration

Adapter cũ:

~~~java
@Override
protected void configure(AuthenticationManagerBuilder auth)
        throws Exception {
    auth.userDetailsService(users)
        .passwordEncoder(passwordEncoder);
}
~~~

Trong component-based model, tùy nhu cầu, ứng dụng có thể khai báo:

~~~java
@Bean
UserDetailsService users(PasswordEncoder encoder) {
    UserDetails localAdmin = User.withUsername("local-admin")
        .password(encoder.encode("test-only-password"))
        .roles("ADMIN")
        .build();
    return new InMemoryUserDetailsManager(localAdmin);
}

@Bean
PasswordEncoder passwordEncoder() {
    return new BCryptPasswordEncoder();
}
~~~

Đây là ví dụ **local test/demo account**; production không lưu mật khẩu trong source, kể cả khi được hash. Dùng credential store và provisioning policy phù hợp.

Nếu thực sự cần global manager:

~~~java
@Bean
AuthenticationManager authenticationManager(
    AuthenticationConfiguration configuration
) throws Exception {
    return configuration.getAuthenticationManager();
}
~~~

### 26.1. OIDC-only app thường không cần local password login

Nếu tất cả users đăng nhập qua OIDC, đừng thêm UserDetailsService/password authentication chỉ để thay một override cũ không còn chức năng.

### 26.2. Custom AuthenticationProvider

Nếu có provider custom, đưa thành bean/configuration theo phạm vi chain phù hợp. Không để API Bearer flow vô tình dùng provider của browser login.

## 27. WebSecurityCustomizer: chỉ khi cần bypass filters

Cũ:

~~~java
@Override
public void configure(WebSecurity web) {
    web.ignoring().antMatchers("/assets/**");
}
~~~

Khuyến nghị trong nhiều trường hợp là:

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/assets/**").permitAll()
    .anyRequest().authenticated())
~~~

`permitAll` giữ request đi qua Spring Security filter chain, khác với `web.ignoring` bỏ qua toàn bộ filters, headers và security infrastructure.

### 27.1. Nếu thực sự cần customizer

~~~java
@Bean
WebSecurityCustomizer webSecurityCustomizer() {
    return web -> web.ignoring()
        .requestMatchers("/very-special-unfiltered-path");
}
~~~

Phải đánh giá thật kỹ. Không ignore endpoints authentication, OIDC callback hay data nhạy cảm.

### 27.2. Health endpoints

Health liveness/readiness nên có policy network/access riêng; không disable security toàn app chỉ vì probe bị 401.

## 28. Method security: @EnableMethodSecurity

Cũ:

~~~java
@EnableGlobalMethodSecurity(prePostEnabled = true)
~~~

Mới:

~~~java
@EnableMethodSecurity
~~~

Ví dụ:

~~~java
@Service
public class ReportsService {
    @PreAuthorize("hasRole('ADMIN')")
    public Report readSensitiveReport() {
        return /* ... */;
    }
}
~~~

### 28.1. Roles mapping

`hasRole("ADMIN")` thường mong GrantedAuthority `ROLE_ADMIN`. Nếu legacy IdP adapter từng map vendor groups, cần port logic đó sang OidcUserService/GrantedAuthoritiesMapper/JWT converter tương ứng.

### 28.2. Self-invocation

Proxy-based method security có thể không intercept `this.securedMethod()` khi gọi nội bộ cùng bean; không coi migration annotation là cách tự khắc phục vấn đề này.

### 28.3. URL rule và service rule bổ trợ nhau

HTTP controllers có thể gọi cùng service từ nhiều endpoints, scheduled jobs hoặc nội bộ; method security là một lớp authorization bổ sung, không thay thế tenant/resource ownership validation.

## 29. Vendor-specific adapters cũ (ví dụ Keycloak)

Một dự án có thể extends adapter thuộc SDK IdP, không chỉ `WebSecurityConfigurerAdapter`. Những vendor adapters đời cũ có thể thực hiện:

- Browser OAuth2/OIDC login.
- Bearer token authentication.
- Mapping vendor-specific roles.
- Session registration và SSO logout.
- Token propagation/refresh.
- Client secret/provider configuration.

**Không có phép đổi class một-một** để giữ tất cả chức năng.

| Vai trò của app | Spring Security native replacement |
|---|---|
| Browser redirects/SSO | `oauth2Login()` với OIDC |
| Downstream tokens | `oauth2Client()` và manager |
| JWT Bearer API | `oauth2ResourceServer().jwt()` |
| Opaque token API | `oauth2ResourceServer().opaqueToken()` |
| UserInfo/OIDC role mapping | OidcUserService/GrantedAuthoritiesMapper |
| JWT resource roles | JwtAuthenticationConverter |
| RP-initiated logout | OIDC logout handler |
| Provider back-channel logout | Dedicated integration theo provider/version |

### 29.1. Vendor role claims

Ví dụ một số IdPs có cấu trúc:

~~~json
{
  "realm_access": {"roles": ["auditor"]},
  "resource_access": {
    "portal": {"roles": ["admin"]}
  }
}
~~~

Đây không phải claim schema OAuth/OIDC chuẩn mà Spring tự hiểu. Phải mapping theo verified token/claims và business policy.

### 29.2. Đừng dùng service token để vượt 403

Nếu user đã login nhưng không có quyền, không tự gọi API bằng client_credentials token đặc quyền chỉ để request thành công. Permission boundary vẫn phải được enforce.

### 29.3. Client và Resource Server khác nhau

Một app nhận mobile API bearer token thường cần Resource Server, không nhất thiết browser OAuth2 Login. Phân loại role trước khi migrate adapter.

## 30. Logout không tự tương đương giữa các adapters

Local logout:

~~~java
.logout(logout -> logout
    .logoutSuccessUrl("/"))
~~~

không tự logout toàn bộ SSO session ở OP hoặc revoke mọi access/refresh token.

Khi OP hỗ trợ RP-initiated OIDC logout, Spring Security có:

~~~java
OidcClientInitiatedLogoutSuccessHandler
~~~

Ví dụ:

~~~java
@Bean
LogoutSuccessHandler oidcLogout(
    ClientRegistrationRepository registrations
) {
    var handler =
        new OidcClientInitiatedLogoutSuccessHandler(registrations);
    handler.setPostLogoutRedirectUri("{baseUrl}/");
    return handler;
}
~~~

Gắn vào chain:

~~~java
http.logout(logout -> logout
    .logoutSuccessHandler(oidcLogoutHandler));
~~~

`oidcLogoutHandler` trong ví dụ là bean injection. Cần OP metadata/support và post-logout URI allowlist phù hợp.

### 30.1. Ba vòng đời khác nhau

~~~text
Local HttpSession
OAuth2AuthorizedClient access/refresh tokens
OpenID Provider SSO session
~~~

Không giả định xóa một thứ sẽ làm hai thứ còn lại tự kết thúc.

## 31. Custom filters trong SecurityFilterChain

Adapter cũ:

~~~java
http.addFilterBefore(
    customFilter, UsernamePasswordAuthenticationFilter.class);
~~~

Bean chain mới vẫn có:

~~~java
http.addFilterBefore(
    customFilter, UsernamePasswordAuthenticationFilter.class);
~~~

Nhưng cần xác định filter nên chạy trước/sau:

~~~text
OAuth2 authorization request filter
OAuth2 login authentication filter
SecurityContext filters
AuthorizationFilter
~~~

### 31.1. Tránh đăng ký filter hai lần

Nếu `customFilter` là `@Component Filter`, Spring Boot có thể tự đăng ký nó với Servlet container; `http.addFilterBefore` lại đăng ký trong Spring Security chain. Cần điều chỉnh `FilterRegistrationBean` hoặc bean setup để tránh double execution.

### 31.2. Không chặn callback bằng custom Bearer filter

Một custom filter bắt mọi request thiếu Authorization Bearer sẽ làm hỏng browser callback khi chạy trước OAuth2Login. Dùng RequestMatcher và kiểm thử endpoints cụ thể.

### 31.3. Đừng tự tạo Authentication từ unsigned JWT

Claims lấy từ unverified JWT header/payload là untrusted. Phải có signature/issuer/audience checks trước khi cấp authorities.

## 32. Exception handling: API JSON khác browser login

Với browser login, anonymous request có thể redirect đến trang đăng nhập. JSON API đôi khi cần `401` thay vì 302/HTML:

~~~java
http.exceptionHandling(errors -> errors
    .defaultAuthenticationEntryPointFor(
        new HttpStatusEntryPoint(HttpStatus.UNAUTHORIZED),
        new AntPathRequestMatcher("/api/**")
    ));
~~~

`AntPathRequestMatcher` là API có mặt trong nhiều bản Spring Security 6 nhưng có thể bị deprecated ở các bản mới; nếu đã chuyển sang matcher hiện đại hơn, thay bằng `RequestMatcher` cùng semantics.

### 32.1. 401 khác 403

- **401**: caller chưa authenticated hoặc session không hợp lệ.
- **403**: caller authenticated nhưng không đủ quyền, hoặc CSRF bị từ chối.

Không trả 401 cho mọi thiếu ROLE_ADMIN để frontend cứ redirect login mãi.

### 32.2. Downstream 401 không tự logout browser

Orders API trả `401 Bearer invalid_token` có thể cần reauthorization của authorized client, không nhất thiết làm user Portal chưa authenticated.

## 33. Trusted proxy, baseUrl và redirect URI

Trong production:

~~~text
Browser HTTPS portal.company.example
  -> Reverse proxy
      -> Spring Boot HTTP 8080
~~~

OIDC callback public:

~~~text
https://portal.company.example/login/oauth2/code/company
~~~

`{baseUrl}` cần được Spring tính đúng public scheme/host.

Một cấu hình có thể dùng:

~~~yaml
server:
  forward-headers-strategy: framework
~~~

Nhưng ingress phải **strip/overwrite Forwarded/X-Forwarded-* headers do client tự gửi**. Không lấy `X-Forwarded-Host` untrusted làm redirect URI, tenant ID hoặc issuer selector.

### 33.1. Redirect mismatch

IdP có thể từ chối redirect URI không khớp registration. Khi đổi domain/path/proxy, cập nhật URI phía OP và Spring.

### 33.2. SameSite

Browser cross-site OIDC callbacks phụ thuộc session cookie. GET callback với Lax thường phù hợp nhiều browser flows, nhưng `response_mode=form_post` có yêu cầu cookie cross-site khác. Không vô hiệu hóa state/CSRF để xử lý sai cookie policy.

## 34. SecurityContext persistence trong 6.x

Nếu custom adapter trước đây tự tạo Authentication:

~~~java
SecurityContextHolder.getContext().setAuthentication(authentication);
~~~

thì sau migration không nên tự tin Authentication đã được lưu cho request tiếp theo. Với custom authentication flows, cần dùng `SecurityContextRepository` hoặc đúng Spring Security authentication infrastructure.

### 34.1. Login OAuth2 mặc định

OAuth2 Login filter có lifecycle lưu authenticated session theo cơ chế đã cấu hình; không tự set principal trước khi state/nonce/ID Token được xác minh.

### 34.2. Test request thứ hai

Sau login callback, gửi request khác bằng cookie/session vừa được cấp để kiểm tra `SecurityContext` được persist, không chỉ assert callback redirect.

### 34.3. Không bỏ qua session fixation

Session ID có thể được rotate sau login. Đây là behavior security mong muốn; test phải phù hợp original authorization request/session correlation.

## 35. ERROR/FORWARD dispatcher và authorization

Sau migration, một số ứng dụng thấy error page thành 403 vì authorization rules áp vào error/forward dispatch. Khi policy cho phép:

~~~java
.authorizeHttpRequests(auth -> auth
    .dispatcherTypeMatchers(
        DispatcherType.ERROR,
        DispatcherType.FORWARD
    ).permitAll()
    .requestMatchers("/error").permitAll()
    .anyRequest().authenticated())
~~~

Đây là ví dụ có chủ đích; cần xem security requirements của error views. Không permit toàn bộ sensitive forwards một cách mù quáng.

### 35.1. Phân biệt request chính và error dispatch

Một request thất bại 500 rồi bị deny ở error dispatch có thể hiển thị 403, khiến điều tra nhầm nguyên nhân. Ghi log/tracing theo dispatch type và kiểm tra cả HTTP filter rules.

## 36. Test plan cho việc nâng cấp

| Test case | Kỳ vọng |
|---|---|
| Anonymous GET `/` | Public |
| Anonymous GET `/assets/app.css` | Public, không bypass không chủ đích |
| Anonymous GET `/login` | Không redirect loop |
| Anonymous GET `/admin/report` | Login entry point hoặc API 401 theo policy |
| OIDC user thường GET `/admin/report` | 403 |
| OIDC user ROLE_ADMIN GET `/admin/report` | 200 |
| OIDC user GET `/api/me` | 200 |
| POST `/api/settings` thiếu CSRF | 403 nếu session CSRF được bật |
| POST có CSRF và authentication | Thành công |
| GET `/oauth2/authorization/company` | Redirect đến trusted authorization endpoint |
| Callback sai state | Từ chối |
| Callback ID Token sai issuer/audience/signature | Từ chối |
| Callback đúng với cùng session | Authenticated |
| Token store load đúng registration/principal | Có |
| API outbound Bearer | Token đúng registration |
| Local logout | Invalidate session |
| OIDC OP logout | Theo cấu hình riêng |
| Bearer-only external API không token | 401, không HTML login |
| Bearer-only external API valid JWT | Policy đúng issuer/audience/scopes |
| User từ tenant khác | Không dùng chéo token/data |

### 36.1. Không chỉ test happy path

Một test `oidcLogin()` trả 200 ở controller chỉ chứng minh mocked Authentication đi qua authorization rule; nó không chứng minh Authorization Code callback hoặc ID Token signature validation.

## 37. MockMvc kiểm thử SecurityFilterChain

Dependencies:

~~~kotlin
dependencies {
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.security:spring-security-test")
}
~~~

Test fragment:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class PortalSecurityMigrationIT {

    @Autowired
    MockMvc mvc;

    @Test
    void anonymousCannotAccessAdminPage() throws Exception {
        mvc.perform(get("/admin/report"))
            .andExpect(status().is3xxRedirection());
    }

    @Test
    void normalOidcUserCannotAccessAdminPage() throws Exception {
        mvc.perform(get("/admin/report")
                .with(oidcLogin()))
            .andExpect(status().isForbidden());
    }

    @Test
    void oidcAdminCanAccessAdminPage() throws Exception {
        mvc.perform(get("/admin/report")
                .with(oidcLogin()
                    .authorities(
                        new SimpleGrantedAuthority("ROLE_ADMIN"))))
            .andExpect(status().isOk());
    }
}
~~~

`/admin/report` cần controller thực tế trả 200 khi được phép. Assertion anonymous redirect đúng với browser chain có login entry point; nếu app cấu hình HTTP 401 API entry point, điều chỉnh test theo contract.

### 37.1. CSRF test

~~~java
mvc.perform(post("/api/settings")
        .with(oidcLogin()))
    .andExpect(status().isForbidden());

mvc.perform(post("/api/settings")
        .with(oidcLogin())
        .with(csrf()))
    .andExpect(status().isOk());
~~~

Các tests cần route/controller tồn tại và không vấp business validation khác; ví dụ nhằm minh họa CSRF policy.

### 37.2. API test phải dùng đúng Authentication type

Nếu API Resource Server dùng JWT Bearer, `jwt()` postprocessor phù hợp cho authorization tests; không dùng `oidcLogin()` để tuyên bố JWT resource validation đã chạy.

## 38. OAuth2 authorization request/callback integration tests

MockMvc:

~~~java
@Test
void startsOauthLogin() throws Exception {
    mvc.perform(get("/oauth2/authorization/company"))
        .andExpect(status().is3xxRedirection())
        .andExpect(header().exists("Location"));
}
~~~

Nên parse Location và assert:

~~~text
authorization endpoint matches trusted OP
client_id matches ClientRegistration
redirect_uri matches public callback
scope includes openid
state is nonempty
nonce is present for OIDC as required
PKCE code_challenge when configured
~~~

### 38.1. Callback test với fake OP

Fake token/JWKS endpoints cho phép test:

- Browser authorization request/state/session.
- Token endpoint response parsing.
- ID Token signature, issuer, audience, expiration.
- OIDC nonce validation.
- Authentication success/failure handlers.
- Session persistence.

Không dùng `oidcLogin()` để thay thế cryptographic tests.

### 38.2. Có nhiều registrations

Kiểm tra `/oauth2/authorization/company` không tự dùng callback/token của `partner`, nhất là khi cả hai dùng chung issuer.

## 39. Authorized client và downstream test

MockMvc test có thể seed authorized client:

~~~java
mvc.perform(get("/api/orders")
        .with(oidcLogin())
        .with(oauth2Client("company")))
    .andExpect(status().isOk());
~~~

Nếu controller cần:

~~~java
@RegisteredOAuth2AuthorizedClient("company")
OAuth2AuthorizedClient client
~~~

test phải assert đúng registration/principal/access token context; không chỉ 200.

### 39.1. Repository custom

`oauth2Client()` test postprocessor có thể seed HttpSession repository; nếu production dùng custom JDBC/Redis service, cần setup đúng store để test không cho false confidence.

### 39.2. Outbound Bearer

Sử dụng fake Orders API server/ExchangeFunction để assert:

~~~http
Authorization: Bearer <test-token-for-company>
~~~

Không expose real tokens trong logs hoặc HTTP response của Portal.

## 40. Lộ trình migrate ít rủi ro

### Bước 1 — Chụp security contract

Liệt kê public/protected URLs, roles, clients, session/CSRF, redirect URIs, logout và custom filters. Viết regression tests trước.

### Bước 2 — Chuẩn bị dependencies

Nâng Java, Spring Boot/Security, Jakarta; tránh mix major versions.

### Bước 3 — Tách beans

Tạo reusable OAuth2UserService/OidcUserService, authorized-client repository/manager và AuthenticationProviders khi cần.

### Bước 4 — Thay adapter

Tạo SecurityFilterChain, port authorization rules sang Lambda DSL và matchers mới.

### Bước 5 — Chốt chain order

Đảm bảo OAuth login initiation/callback luôn match chain cần thiết; APIs stateless tách rõ nếu có.

### Bước 6 — Đồng bộ external IdP

Client IDs, secrets, issuer, authorization/token endpoints, redirect URI, role mapping, logout.

### Bước 7 — Chạy regression tests

Happy-path và negative auth/authorization/CSRF/token/session/tenant/callback tests.

### Bước 8 — Quan sát rollout

Theo dõi login failures, callback state mismatches, token refresh errors, 401/403/429/5xx, session/cookie incidents.

### Bước 9 — Chuẩn bị rollback

Giữ release/tag cũ và kế hoạch tương thích token/session/database schema nếu có migration storage.

### Bước 10 — Loại bỏ adapter còn sót

Không giữ đồng thời legacy configuration và chain mới gây security rules trùng hoặc bypass khó giải thích.

## 41. Observability sau migration

Metrics/logs nên phân biệt:

~~~text
oauth.login.start
oauth.login.success
oauth.login.failure
oauth.callback.state_mismatch
oauth.token.refresh.failure
authorization.denied
csrf.denied
session.invalidated
downstream.invalid_token
~~~

Các tên trên là application-defined examples, không phải bảo đảm Spring Security phát tất cả mặc định.

**Không log**:

~~~text
access_token
refresh_token
id_token
client_secret
authorization_code
Authorization Bearer header
JSESSIONID/SESSION cookie
private key
~~~

### 41.1. Trace theo dependency và registration

Nếu chỉ company registration login lỗi, kiểm tra đúng issuer, secret, redirect URI và callback matcher. Nếu tất cả ADMIN requests bị 403, kiểm tra authority mapping/method security/CSRF.

### 41.2. Không bật wire logs quá rộng

HTTP debug logs có thể in token endpoint request/response; bật trong thời gian có kiểm soát, redact và đặt retention phù hợp.

## 42. Troubleshooting nhanh

| Triệu chứng | Nguyên nhân có thể | Xử lý |
|---|---|---|
| Không tìm thấy WebSecurityConfigurerAdapter | Spring Security 6 đã bỏ adapter | Dùng @Bean SecurityFilterChain |
| `antMatchers()` không tồn tại | DSL cũ | Dùng requestMatchers |
| `.and()` deprecated/không phù hợp | DSL cũ | Lambda DSL |
| `javax.servlet.*` compile error | Jakarta namespace | `jakarta.servlet.*` |
| Login page redirect loop | /login không permitAll | Fix authorization |
| OAuth start 404 | Chain không match login entry | Fallback chain, registration |
| Callback 404 | redirect matcher không khớp | Đồng bộ redirect URI |
| `invalid_redirect_uri` | Provider registration sai | Fix public host/redirect |
| `authorization_request_not_found` | State/session mất | Cookie/SameSite/shared session |
| ID Token invalid issuer | Issuer config/trust mismatch | Correct ClientRegistration |
| User admin nhưng 403 | Role mapping mất | OIDC authorities mapper |
| POST 403 | CSRF hoặc role | Đúng token/permissions |
| API gửi HTML login page | Wrong chain/entry point | JSON 401 policy |
| Token refresh liên tục | Persistence/manager issue | Kiểm tra store/success handler |
| Logout không thoát IdP | Local logout only | RP-initiated logout integration |
| Filter chạy hai lần | Container + chain registration | FilterRegistrationBean |
| Error page thành 403 | Dispatcher rule | ERROR/FORWARD policy |
| Multiple chains bypass URL | securityMatcher/order sai | Test chain coverage |
| Test gọi production IdP | issuer discovery | Fake provider/test profile |

## 43. Anti-pattern cần tránh

**1.** Chỉ thay class adapter, không kiểm tra login/callback/authorization semantics.

**2.** Đặt `securityMatcher("/api/**")` cho chain duy nhất có OAuth2 login.

**3.** Để chain rộng `@Order(1)` bắt requests trước chain cụ thể.

**4.** Dùng `web.ignoring("/**")` để chữa 401.

**5.** Disable CSRF toàn browser session app.

**6.** Bật `STATELESS` cho OIDC login dựa vào HttpSession.

**7.** Thay OAuth2 Client và Resource Server bằng cùng một chức năng.

**8.** Bỏ custom OIDC role mapper của vendor adapter.

**9.** Không xác minh issuer/audience/signature của ID Token.

**10.** Dùng email làm stable identity key mọi providers.

**11.** Đổi redirect URI mà không cập nhật OP.

**12.** Tin X-Forwarded-Host không qua trusted proxy.

**13.** Cho rằng local logout đồng nghĩa OP logout/token revocation.

**14.** Mất authorized-client persistence làm token endpoint storm.

**15.** Chỉ test 200, không test anonymous/403/CSRF/callback/tenant.

## 44. Bài tập thực hành

### Bài 1 — Chuyển URL rules

Legacy:

~~~java
http.authorizeRequests()
    .antMatchers("/public/**").permitAll()
    .anyRequest().authenticated();
~~~

**Đáp án:**

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/public/**").permitAll()
    .anyRequest().authenticated());
~~~

### Bài 2 — Callback OIDC bị 404

Chain duy nhất có `.securityMatcher("/api/**")`, callback là `/login/oauth2/code/company`.

**Giải:** Callback nằm ngoài chain; thêm fallback chain bao phủ OAuth2 endpoints hoặc cấu hình matching có chủ đích.

### Bài 3 — ROLE_ADMIN không có

ID Token có `groups=["admins"]`, nhưng GrantedAuthorities chỉ chứa `OIDC_USER`.

**Giải:** Chuyển verified claim/tenant role mapping sang OidcUserService/GrantedAuthoritiesMapper, không nghĩ Spring tự cấp ROLE_ADMIN.

### Bài 4 — Redirect host sai

OP đăng ký HTTPS public URI nhưng app gửi HTTP localhost callback.

**Giải:** Kiểm tra proxy forwarded headers, public base URL, redirect-uri và OP client registration.

### Bài 5 — POST 403

User đã OIDC login nhưng request POST bị từ chối.

**Giải:** Kiểm tra CSRF và RBAC; không tắt CSRF theo phản xạ.

### Bài 6 — Manager không tìm thấy token

Browser authenticated nhưng WebClient gọi Orders API thiếu token.

**Giải:** Kiểm tra ClientRegistration, principal, authorized-client repository/service và manager.

### Bài 7 — Scheduled job

Job client_credentials dùng request-scoped DefaultOAuth2AuthorizedClientManager.

**Giải:** Dùng AuthorizedClientServiceOAuth2AuthorizedClientManager với service store.

### Bài 8 — Static assets

Legacy dùng web.ignoring cho `/assets/**`.

**Giải:** Cân nhắc `requestMatchers("/assets/**").permitAll()` để giữ security filters.

### Bài 9 — Vendor adapter

Adapter cũ tự map provider realm roles.

**Giải:** Xác định browser OIDC hay Resource Server, mapping vào OidcUserService/GrantedAuthoritiesMapper hoặc JWT converter phù hợp.

### Bài 10 — Logout

Logout local vẫn giữ session OP.

**Giải:** Nếu yêu cầu kết thúc OP SSO, cấu hình OIDC RP-initiated logout theo provider contract và test riêng.

### Bài 11 — State mismatch

MockMvc `oidcLogin()` pass nhưng callback thật báo invalid state.

**Giải:** Mock Authentication bypass callback. Cần fake OP integration test với cùng browser session/state.

### Bài 12 — Hai filter chains

External JWT API cần stateless, browser cần OIDC session.

**Giải:** Tách chains bằng `@Order`, `securityMatcher`, fallback browser chain; không disable CSRF trong browser chain.

## 45. Checklist trước khi triển khai

| Câu hỏi | Điều cần đảm bảo |
|---|---|
| Không còn extends WebSecurityConfigurerAdapter? | Có |
| Có @Bean SecurityFilterChain? | Có |
| Dùng Lambda DSL? | Có |
| antMatchers/mvcMatchers đã chuyển? | Có |
| securityMatcher đúng phạm vi? | Có |
| Fallback chain bảo vệ paths còn lại? | Có |
| Multiple chain order được test? | Có |
| Login page anonymous được truy cập? | Có |
| OAuth2 authorization endpoint hoạt động? | Có |
| OIDC callback matcher/redirect URI khớp? | Có |
| State/nonce/PKCE vẫn được kiểm tra? | Có |
| ClientRegistration issuer/clientId đúng? | Có |
| Secrets không hard-code? | Có |
| OIDC authorities mapping còn đúng? | Có |
| Method security được bật nếu cần? | Có |
| Session/CSRF phù hợp browser login? | Có |
| OAuth2AuthorizedClient store tương thích? | Có |
| Manager đúng web vs job context? | Có |
| Bearer API chain tách khi cần? | Có |
| API không trả nhầm browser login HTML? | Có |
| Static assets không bypass filters vô lý? | Có |
| Custom filters không double registered? | Có |
| Local logout/OP logout rõ ràng? | Có |
| Trusted proxy/public base URL đúng? | Có |
| Jakarta imports đã chuyển? | Có |
| MockMvc tests cho 401/403/CSRF? | Có |
| Fake OP tests cho OIDC callback? | Có |
| Test token/registration/tenant isolation? | Có |
| Logs không lộ credentials? | Có |
| Có rollback plan? | Có |

## 46. Tài liệu tham khảo chính thức

- Spring Security Blog — **Spring Security without the WebSecurityConfigurerAdapter**: https://spring.io/blog/2022/02/21/spring-security-without-the-websecurityconfigureradapter
- Spring Security 6.5 — **Java Configuration**: https://docs.spring.io/spring-security/reference/6.5/servlet/configuration/java.html
- Spring Security 6.5 — **Authorize HttpServletRequests**: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html
- Spring Security 6.5 — **Advanced OAuth2 Login Configuration**: https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/login/advanced.html
- Spring Security 6.5 — **Core OAuth2 Client Interfaces and Classes**: https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/client/core.html
- Spring Security 6.5 — **Configuration Migrations / Lambda DSL**: https://docs.spring.io/spring-security/reference/6.5/migration-7/configuration.html

Đối chiếu snippets với **đúng major/minor version** của dự án; một số matchers/configuration APIs có thể thay đổi hoặc bị deprecated ở các phiên bản mới hơn.

## 47. Tổng kết

Chuyển từ `WebSecurityConfigurerAdapter` sang `SecurityFilterChain` là chuyển từ cấu hình dựa trên kế thừa sang **beans độc lập**. Mẫu mới cốt lõi:

~~~java
@Bean
SecurityFilterChain filterChain(HttpSecurity http)
        throws Exception {
    http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/public/**").permitAll()
            .anyRequest().authenticated())
        .oauth2Login(Customizer.withDefaults())
        .oauth2Client(Customizer.withDefaults());
    return http.build();
}
~~~

Tuy nhiên một OAuth2/OIDC Client thực tế còn có **ClientRegistration, issuer/client ID, redirect URI, authorization state/nonce/PKCE, authenticated session, CSRF, user/authority mapping, authorized-client storage, token refresh, downstream HTTP integration và logout semantics**. Với vendor-specific adapters, có thể phải tách riêng browser login, Resource Server Bearer validation và provider-specific claims/roles.

Những rủi ro lớn nhất khi migration thường nằm ở **securityMatcher quá hẹp làm callback nằm ngoài chain**, rules permitAll quá rộng, bật stateless sai context, quên CSRF/mapping roles, mất token persistence hoặc bỏ qua proxy redirects. Hãy dùng tests cho **valid login, anonymous denial, ADMIN permission, callback state/ID Token verification, session, token registration và tenant isolation**.

**Nguyên tắc quan trọng:** migration hoàn tất khi **hành vi bảo mật được bảo toàn hoặc cải thiện**, không chỉ khi code biên dịch và endpoint trả HTTP 200.
