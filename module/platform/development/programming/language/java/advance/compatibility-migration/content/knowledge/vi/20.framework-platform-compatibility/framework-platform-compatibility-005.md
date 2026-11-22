# Nâng cấp Spring Security và kiểm thử lại hợp đồng bảo mật

Nâng cấp Spring Security không chỉ là thay một dependency hoặc đổi API cấu hình. Spring Security quyết định request nào được xác thực, ai được phép gọi endpoint nào, khi nào cần CSRF token, cách bảo vệ session, cách kiểm tra JWT và nơi các bộ lọc được thực thi. Nếu thay đổi những quy tắc này ngoài ý muốn, ứng dụng có thể biên dịch và khởi động bình thường nhưng **vô tình mở endpoint nhạy cảm**, từ chối người dùng hợp lệ hoặc không kiểm tra đúng quyền truy cập dữ liệu.

Trong **Java Advance Compatibility Migration**, nâng Spring Security thường đi cùng nâng JDK, Spring Framework, Spring Boot, Servlet/Jakarta stack, OAuth2/JWT libraries và các Spring Security filters tự viết. Bài học này giới thiệu cách chuyển đổi cấu hình qua những dòng phiên bản lớn, xác định **hợp đồng bảo mật** trước và sau migration, xây dựng negative tests và triển khai có phương án rollback.

## 1. Hợp đồng bảo mật là gì?

**Hợp đồng bảo mật** (*security contract*) là tập các quy tắc có thể kiểm chứng mà ứng dụng cam kết:

- Endpoint hoặc hành động nào được truy cập ẩn danh?
- Người dùng không đăng nhập được chuyển tới login hay nhận HTTP 401?
- Người dùng đã đăng nhập nhưng không đủ quyền bị chặn bằng HTTP 403 hay phản hồi khác theo API?
- Role, authority, scope và JWT claim nào cho phép hành động?
- Những thao tác nào phải có CSRF token?
- API dùng bearer token hoàn toàn stateless hay dựa vào cookie/session?
- CORS cho phép origin, method, header và credential nào?
- Session được tạo, hết hạn, vô hiệu hóa và bảo vệ ra sao?
- User có quyền xem *đúng tài nguyên của mình* hay chỉ cần có role tổng quát?

Ví dụ một contract minh họa:

| Hành động | Ẩn danh | User đã đăng nhập | Admin | Điều kiện khác |
|---|---|---|---|---|
| GET /public/info | Cho phép | Cho phép | Cho phép | Không lộ dữ liệu nhạy cảm. |
| GET /api/orders/me | 401 | Cho phép nếu có scope đọc | Tùy chính sách | Chỉ xem dữ liệu của chính mình. |
| POST /api/orders | 401 | Cần scope ghi | Tùy chính sách | Token hợp lệ, kiểm tra input. |
| GET /admin/reports | 401 hoặc redirect | 403 | Cho phép | Chỉ cho role/authority thích hợp. |
| POST /web/account/email | Chưa login bị chặn | Cần CSRF token | Cần CSRF token | Web sử dụng cookie session. |

Các status và endpoint trong bảng chỉ để minh họa. **Dự án thật cần chốt chính sách** vì web form login có thể trả redirect 302 còn bearer API thường trả 401.

## 2. Vì sao compile thành công chưa đủ?

Đổi một cấu hình cũ:

```java
http.authorizeRequests()
    .antMatchers("/admin/**").hasRole("ADMIN")
    .anyRequest().authenticated();
```

thành:

```java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/admin/**").permitAll()
    .anyRequest().authenticated());
```

có thể giúp code dùng được API mới, nhưng lại mở quyền cho mọi request tới admin. Trường hợp này cực kỳ nghiêm trọng và hoàn toàn không được phát hiện bằng Java compiler.

Những thay đổi tinh vi hơn gồm:

- Pattern matcher mới có ngữ nghĩa khác với matcher cũ.
- Chuyển từ một chain sang nhiều chains và quên một catch-all chain.
- Lỗi ánh xạ role `ROLE_ADMIN` thành authority `ADMIN`.
- Custom authentication filter không lưu `SecurityContext` như trước.
- JWT từ một issuer sai được chấp nhận vì test chỉ mock token.
- CSRF bị vô hiệu hóa trên cả web session chỉ vì một API cần stateless.
- Method security bị bỏ qua vì test gọi đối tượng tạo bằng `new`.

Vì vậy, test migration phải trả lời không chỉ “ai **được** truy cập?” mà còn “ai **không được** truy cập?”.

## 3. Các cột mốc nâng cấp

| Nguồn/đích | Trọng tâm thay đổi | Hành động chuẩn bị |
|---|---|---|
| Spring Security 5.x đời cũ | `WebSecurityConfigurerAdapter`, `authorizeRequests`, `antMatchers` có thể còn hiện diện. | Đọc migration guide và lập baseline rule. |
| 5.8 → 6.x | Bean-based configuration, request matcher APIs, các thay đổi tương thích Spring Framework 6 / Boot 3 / Jakarta, Java 17 baseline. | Thực hiện các bước chuẩn bị của 5.8 rồi nâng sang 6. |
| 6.x → 7.x | Các DSL/matcher cũ bị loại bỏ; Lambda DSL và `PathPatternRequestMatcher` đóng vai trò trung tâm. | Dùng hướng dẫn 6.5 chuẩn bị cho 7, đối chiếu Boot 4/Framework 7. |
| Bất kỳ lần nâng nào | Security fixes, thay đổi mặc định, dependency và runtime. | Đọc release notes đúng bản patch, chạy lại security contract tests. |

Không suy ra target JDK hoặc cấu hình hợp lệ chỉ từ version major. Spring Boot thường quản lý các module Spring Security qua BOM; phải kiểm tra version thực tế đã resolve và compatibility matrix của đúng tổ hợp Boot, Framework, Security, Servlet container và JDK.

### 3.1. Kiểm kê phiên bản thực tế

Maven:

```bash
mvn -version
mvn dependency:tree
```

Gradle:

```bash
./gradlew --version
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight \
  --dependency spring-security \
  --configuration runtimeClasspath
```

Kiểm tra `spring-security-core`, `spring-security-web`, `spring-security-config`, `spring-security-test`, OAuth2/JWT modules, Spring Boot/Framework, application server và thư viện bên thứ ba có tham gia authentication/filter chain. Nếu chỉ nâng một Security JAR nhưng phần còn lại chưa tương thích, runtime có thể xảy ra linkage error.

## 4. Inventory cấu hình trước khi sửa

Tìm toàn bộ:
- `WebSecurityConfigurerAdapter`, `SecurityFilterChain`, `HttpSecurity`, `WebSecurityCustomizer`.
- `antMatchers`, `mvcMatchers`, `requestMatchers`, `securityMatcher`, `@Order`.
- `AuthenticationManager`, `AuthenticationProvider`, `UserDetailsService`, `PasswordEncoder`.
- `@PreAuthorize`, `@PostAuthorize`, `@Secured`, `@EnableMethodSecurity`.
- CSRF, CORS, logout, headers, remember-me, sessions.
- OAuth2 client, resource server, JWT decoder, SAML2 nếu có.
- Custom `Filter`, `OncePerRequestFilter`, `SecurityContextRepository`, entry point và denied handler.
- Các route ở MVC, WebFlux, actuator, WebSocket, static files và error page.
- Tham số runtime, reverse proxy, IdP và session store.

Đừng bỏ sót các policy được cấu hình qua YAML/properties, annotations và framework auto-configuration. Một số bộ lọc được đăng ký trong servlet container chứ không xuất hiện trong Spring Security chain.

## 5. Chuyển từ WebSecurityConfigurerAdapter

Một cấu hình legacy thường thấy:

```java
@Configuration
@EnableWebSecurity
public class LegacySecurityConfig
        extends WebSecurityConfigurerAdapter {
    @Override
    protected void configure(HttpSecurity http) throws Exception {
        http.authorizeRequests()
            .antMatchers("/public/**").permitAll()
            .antMatchers("/admin/**").hasRole("ADMIN")
            .anyRequest().authenticated()
            .and()
            .formLogin();
    }
}
```

Đây là **mã minh họa cho dòng cũ**, không dùng trực tiếp trong Spring Security 6/7. Thay vào đó, định nghĩa bean `SecurityFilterChain`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class WebSecurityConfig {
    @Bean
    SecurityFilterChain filterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/public/**").permitAll()
                .requestMatchers("/login", "/assets/**").permitAll()
                .requestMatchers("/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults());
        return http.build();
    }
}
```

Ở đây:
- `SecurityFilterChain` mô tả filters và rules cho request khớp chain.
- `authorizeHttpRequests` dùng authorization model mới.
- Lambda DSL tránh cách gọi `.and()` lồng nhau; ở Spring Security 7 cần dùng cấu hình DSL mới theo migration guide.
- `anyRequest().authenticated()` làm rule bao phủ những request còn lại trong chain.
- Không tắt CSRF cho web cookie session mà không có lý do.

Cấu hình chỉ có ý nghĩa khi các request path trong ứng dụng và rules đã được xác nhận bằng test.

## 6. Phân biệt securityMatcher và requestMatchers

`http.securityMatcher(...)` chọn **request nào được đưa qua cả SecurityFilterChain**. Còn `requestMatchers(...)` bên trong `authorizeHttpRequests` chọn **authorization rule** cho request đã vào chain.

Ví dụ:

```java
@Bean
@Order(1)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/public/**").permitAll()
            .anyRequest().authenticated())
        .httpBasic(Customizer.withDefaults());
    return http.build();
}
```

Nếu chỉ có chain này, `/admin/reports` không khớp `/api/**` và có thể **không được Spring Security bảo vệ**. Giải pháp là có chain bổ sung phù hợp:

```java
@Bean
@Order(2)
SecurityFilterChain fallbackChain(HttpSecurity http)
        throws Exception {
    http.authorizeHttpRequests(auth -> auth
        .anyRequest().denyAll());
    return http.build();
}
```

Các snippet giả định cùng file cấu hình và imports phù hợp. Trong ứng dụng thực tế, fallback có thể là policy form login/web, nhưng không nên để unmatched requests đi qua không được bảo vệ.

### 6.1. Filter chain order

`FilterChainProxy` chọn chain đầu tiên phù hợp với request theo thứ tự được cấu hình.

```text
Request
  |
  +--> Chain 1 matches /api/**? ---- yes --> bearer/API rules
  |
  +--> Chain 2 matches /admin/**? -- yes --> admin rules
  |
  +--> Catch-all --------------------------> web/deny rules
```

Kiểm thử cả trường hợp:
- Match chain hẹp.
- Match nhiều chain, ưu tiên chain nào.
- Không match chain nào trước catch-all.
- Login/logout, static resource và `/error`.
- Các dispatcher types, path encoding và trailing slash.
- Endpoint management/actuator có context riêng.

Không dùng `anyRequest().permitAll()` như fallback để “chữa” lỗi deployment.

## 7. Request matchers khi nâng Spring Security 7

Dòng Spring Security 6 đã đưa nhiều người dùng từ `antMatchers`/`mvcMatchers` sang `requestMatchers`. Spring Security 7 tiếp tục thay đổi:
- `AntPathRequestMatcher` và `MvcRequestMatcher` không còn được hỗ trợ theo migration guide.
- `PathPatternRequestMatcher` được dùng theo mặc định.
- URI trong Java DSL dùng absolute path **không tính context root**.
- Những matcher tự tạo ngoài DSL cần được xem xét riêng.

Ví dụ với servlet path, phải kiểm tra route thực tế:

```text
Application context path: /shop
Servlet mapping: /api/*
Request URL: /shop/api/orders/42
Security rule: /api/orders/**
```

Không bao gồm context root `/shop` vào matcher khi contract yêu cầu path tương đối với ứng dụng; nhưng phải đọc đúng cách path được phân tích bởi runtime và matcher version. Với nhiều servlet, JSP, legacy encoded URLs và custom matchers, cần integration test trên servlet container thực.

Các đường dẫn nên test: `/admin`, `/admin/`, `/admin/users`, URL có path variables, encoded characters và HTTP methods khác nhau. Việc matcher không còn khớp có thể dẫn đến 404/403 sai hoặc nguy hiểm hơn là một route không còn được bảo vệ.

## 8. Role và authority không hoàn toàn giống nhau

Theo quy ước mặc định:

```java
.hasRole("ADMIN")
```

thường kiểm tra authority `ROLE_ADMIN`. Nhưng:

```java
.hasAuthority("ADMIN")
```

kiểm tra đúng chuỗi `ADMIN`.

Với JWT resource server, scope thường trở thành authority có prefix `SCOPE_`:

```text
JWT scope: orders.read orders.write

Spring authorities:
SCOPE_orders.read
SCOPE_orders.write
```

Policy:

```java
.requestMatchers(HttpMethod.GET, "/api/orders/**")
    .hasAuthority("SCOPE_orders.read")
```

Trong migration, hãy test JWT claims và cách `JwtAuthenticationConverter` ánh xạ chúng. Nếu IdP chuyển từ `scope` sang một claim custom hoặc đổi tên authority, controller vẫn khởi động nhưng người dùng có thể bị cấp thiếu hoặc cấp thừa quyền.

## 9. Phân biệt 401, 403 và redirect

**Authentication** trả lời danh tính là ai. **Authorization** trả lời danh tính đó có quyền làm gì.

Đối với bearer API:
- Thiếu hoặc không hợp lệ token: thường HTTP 401.
- Token hợp lệ nhưng thiếu quyền: thường HTTP 403.
- Có quyền: request được chuyển tới nghiệp vụ, nhưng có thể tiếp tục bị chặn vì ownership/tenant policy.

Đối với web form login:
- Chưa login: thường redirect 302 tới trang login.
- Login nhưng thiếu role: thường 403.
- Session hết hạn: quay lại luồng login theo configuration.

Không áp đặt một status duy nhất cho mọi cơ chế. Cần chốt cả `AuthenticationEntryPoint`, `AccessDeniedHandler`, response body, `WWW-Authenticate` và redirect URL theo chính sách của API.

## 10. CSRF và giới hạn của lời khuyên “stateless”

CSRF đặc biệt liên quan tới những request mà browser tự gửi cookie/session credential. Một POST có authentication hợp lệ vẫn có thể cần CSRF token.

Ví dụ với web session:

```text
POST /web/account/email
Cookie: JSESSIONID=...
X-CSRF-TOKEN: ...
```

Nếu thiếu CSRF token khi policy yêu cầu, HTTP 403 thường là **kết quả đúng**.

Với API sử dụng bearer token trong `Authorization` header, không dựa vào cookie hoặc các credential tự động từ browser, có thể cân nhắc tắt CSRF cho **chain API riêng**:

```java
http
    .securityMatcher("/api/**")
    .csrf(csrf -> csrf.disable())
    .sessionManagement(session -> session
        .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
    .oauth2ResourceServer(oauth2 -> oauth2
        .jwt(Customizer.withDefaults()));
```

Nhưng “REST” không tự chứng minh an toàn khi tắt CSRF. Nếu dùng cookie authentication, HTTP Basic của browser hoặc mixed credentials, phải đánh giá CSRF riêng. Không tắt CSRF toàn ứng dụng chỉ để một unit test xanh.

## 11. CORS là browser policy, không thay authentication

Preflight `OPTIONS` từ browser thường không chứa bearer token hay session cookie như actual request. Nếu CORS xử lý sau authentication mà không được cấu hình đúng, browser client có thể bị chặn.

Ví dụ một nguồn hợp lệ:

```java
@Bean
UrlBasedCorsConfigurationSource corsConfigurationSource() {
    CorsConfiguration config = new CorsConfiguration();
    config.setAllowedOrigins(
        java.util.List.of("https://app.example.test"));
    config.setAllowedMethods(
        java.util.List.of("GET", "POST", "PUT"));
    config.setAllowedHeaders(
        java.util.List.of("Authorization", "Content-Type"));
    config.setAllowCredentials(false);

    UrlBasedCorsConfigurationSource source =
        new UrlBasedCorsConfigurationSource();
    source.registerCorsConfiguration("/api/**", config);
    return source;
}
```

Ở chain liên quan:

```java
http.cors(Customizer.withDefaults());
```

Các class cần import từ Spring Web CORS API. Đây là domain ví dụ, không phải domain production. CORS không cho phép bỏ authentication/authorization trên actual request. Kiểm thử preflight origin hợp lệ, origin bị chặn và request POST thực có token hợp lệ.

## 12. Sessions và SecurityContext persistence

Sự thay đổi về cách đọc/ghi `SecurityContext` trong các dòng Spring Security mới có thể ảnh hưởng custom login:
- User authenticate thành công ở request đầu.
- Code custom đặt Authentication vào `SecurityContextHolder`.
- Request thứ hai không nhận lại session đã đăng nhập.

Một nguyên nhân là custom flow không lưu SecurityContext qua `SecurityContextRepository` như yêu cầu trong configuration mới.

Nếu cần session persistence:
1. Xác định `SecurityContextRepository` đang được dùng.
2. Xác định filter nào tạo, đọc và lưu context.
3. Kiểm tra thời điểm lưu context sau custom authentication.
4. Test **hai request liên tiếp**, không chỉ kết quả tại request login.
5. Kiểm tra session fixation, logout và session invalidation.

Với bearer API thực sự stateless, mỗi request nên chứng minh token hợp lệ mà không dựa vào session được tạo tình cờ.

## 13. Resource Server JWT: kiểm thử decoder thật

Một cấu hình resource server:

```java
@Bean
SecurityFilterChain apiSecurity(HttpSecurity http)
        throws Exception {
    http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/api/catalog/**")
                .permitAll()
            .requestMatchers(HttpMethod.GET, "/api/orders/**")
                .hasAuthority("SCOPE_orders.read")
            .requestMatchers(HttpMethod.POST, "/api/orders/**")
                .hasAuthority("SCOPE_orders.write")
            .anyRequest().denyAll())
        .sessionManagement(session -> session
            .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
        .csrf(csrf -> csrf.disable())
        .oauth2ResourceServer(oauth2 -> oauth2
            .jwt(Customizer.withDefaults()));
    return http.build();
}
```

Ví dụ dùng `HttpMethod`, `SessionCreationPolicy` và các bean imports phù hợp. Để chạy được, ứng dụng còn phải cấu hình `JwtDecoder`, `issuer-uri`, `jwk-set-uri` hoặc provider tương đương theo yêu cầu.

Một bộ test đầy đủ gồm:
- Token thiếu, rỗng, sai cấu trúc.
- Token sai signature/algorithm hoặc key không đáng tin.
- Token hết hạn hoặc chưa có hiệu lực.
- Token sai issuer/audience.
- Key rotation/JWKS retrieval errors.
- Token hợp lệ nhưng thiếu scope.
- Token hợp lệ có scope cần thiết.
- Token thuộc tenant/issuer khác.
- Authentication principal mapping và authorities đúng như hợp đồng.

Không coi `jwt()` trong `spring-security-test` là bài test cryptographic signature: nó tạo authentication giả lập để test authorization. Cần integration tests thực sự đưa signed JWT qua decoder.

## 14. OAuth2 login, OIDC và SAML

Nếu ứng dụng dùng `oauth2Login()` hoặc SAML2, cần kiểm tra:
- Client registration, redirect URI, grant type, PKCE.
- OAuth state, OIDC nonce, code exchange và token validation.
- UserInfo, authorities/claims mapping và liên kết local account.
- Session sau login, logout local và upstream IdP nếu cần.
- Cookie settings, proxy headers và HTTPS redirect.
- Hành vi khi IdP timeout, JWKS key rotation hoặc malformed response.

Không dùng production client secret hoặc access token thật trong test/log. Nên có test IdP mô phỏng hoặc staging IdP được quản lý, đồng thời test rằng request không xác thực không có quyền truy cập resource nhạy cảm.

## 15. Method Security và proxy behavior

Ở dòng cũ có thể dùng:

```java
@EnableGlobalMethodSecurity(prePostEnabled = true)
```

Cấu hình hiện đại:

```java
@Configuration
@EnableMethodSecurity
class MethodSecurityConfiguration {
}
```

Ví dụ:

```java
@Service
public class ReportService {
    @PreAuthorize("hasAuthority('reports.export')")
    public byte[] export(String reportId) {
        return ("report:" + reportId)
            .getBytes(java.nio.charset.StandardCharsets.UTF_8);
    }
}
```

Kiểm thử:
- Caller có quyền `reports.export` được chạy.
- Caller chỉ có `reports.read` bị chặn.
- Method được gọi qua Spring bean/proxy; lời gọi nội bộ qua `this` có thể bypass advice.
- Expression dùng tên tham số có thể cần compilation `-parameters`.
- PermissionEvaluator, role hierarchy và post-authorization còn hoạt động.
- Scheduled jobs/listeners truy cập service theo authorization policy phù hợp.

Không tạo bean bằng `new ReportService()` trong test để xác minh annotation, vì Spring AOP/method security có thể không tham gia.

## 16. PasswordEncoder và dữ liệu mật khẩu cũ

Trong migration cần kiểm tra:
- Password encoder được đăng ký thực tế.
- Cấu trúc password hash hiện có và prefix thuật toán.
- Những tài khoản dùng legacy hash.
- Chính sách nâng hash sau khi login.
- Reset-password token, lockout policy và rate limits.

Ví dụ dùng delegating encoder:

```java
@Bean
PasswordEncoder passwordEncoder() {
    return PasswordEncoderFactories
        .createDelegatingPasswordEncoder();
}
```

Kiểu `DelegatingPasswordEncoder` thường dùng prefix như `{bcrypt}`. Không đặt `NoOpPasswordEncoder` hoặc bỏ kiểm tra mật khẩu để khôi phục login trong production. Nếu hash cũ cần migration, thiết kế lộ trình rõ và kiểm thử cả tài khoản cũ lẫn tài khoản mới.

## 17. Custom filters và thứ tự thực thi

Các filter tự viết có thể xử lý token, API key, tenant, audit, request signature, correlation ID hoặc authentication.

Sau nâng cấp cần xác định:
- Class `Filter` dùng `jakarta.servlet.*` hay `javax.servlet.*` đúng runtime.
- Filter là bean được Servlet container tự đăng ký hay được đưa vào `SecurityFilterChain`.
- Có bị đăng ký **hai lần** không.
- Vị trí filter so với authentication, SecurityContext và authorization filters.
- Filter có leak credentials trong logs hoặc dùng thread-local không được cleanup không.

Ví dụ minh họa API:

```java
http.addFilterBefore(
    customAuthenticationFilter,
    UsernamePasswordAuthenticationFilter.class);
```

Vị trí này không phải khuyến nghị cho tất cả custom filters. Audit filter có thể cần chạy sau authentication; một custom token filter phải được thiết kế đúng với SecurityContext lifecycle. Test bằng runtime chain thực thay vì chỉ xem cấu hình source.

## 18. HTTP security headers, HTTPS và reverse proxy

Một thay đổi framework/container có thể ảnh hưởng:
- HSTS.
- Content-Security-Policy, X-Frame-Options, X-Content-Type-Options.
- Cache-control cho nội dung nhạy cảm.
- Cookie Secure/HttpOnly/SameSite.
- Trusted forwarded headers, cách nhận diện HTTP/HTTPS và HTTPS redirect.
- Login redirect trong môi trường ingress/reverse proxy.

Không chỉ test MockMvc khi production chạy qua API gateway hoặc reverse proxy. Nên có contract test thực tế ở ingress để kiểm tra header cuối cùng và không có redirect loop HTTP↔HTTPS.

## 19. Method-level vs resource ownership

Một policy như:

```java
.hasAuthority("SCOPE_orders.read")
```

chỉ xác nhận một quyền tổng quát. Nó **không** cho biết user A có được phép xem order của user B không. Nếu service trả order theo ID mà không kiểm tra owner/tenant, endpoint có thể bị lỗ hổng IDOR dù đã có Spring Security.

Contract phải bao gồm:
1. User A xem order A: cho phép.
2. User A xem order B: từ chối (403 hoặc 404 theo hợp đồng).
3. User không đăng nhập: không thấy dữ liệu.
4. Admin hoặc operator: được truy cập rộng hơn chỉ khi policy có định nghĩa.
5. Token đổi tenant claim: không được vượt boundary dữ liệu.

Các case này cần được giữ khi migration, kể cả khi HTTP route và annotation bảo mật giữ nguyên.

## 20. Bài kiểm thử MockMvc cho web security

Với Spring Boot 3-era test stack, có thể chạy integration test MVC filter chain:

```java
@SpringBootTest
@AutoConfigureMockMvc
class WebSecurityContractTest {
    @Autowired
    MockMvc mvc;

    @Test
    void publicEndpointIsAccessible() throws Exception {
        mvc.perform(get("/public/info"))
            .andExpect(status().isOk());
    }

    @Test
    void normalUserCannotAccessAdmin() throws Exception {
        mvc.perform(get("/admin/reports")
                .with(user("reader").roles("USER")))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminCanAccessAdmin() throws Exception {
        mvc.perform(get("/admin/reports")
                .with(user("root").roles("ADMIN")))
            .andExpect(status().isOk());
    }

    @Test
    void postWithoutCsrfIsRejected() throws Exception {
        mvc.perform(post("/web/account/email")
                .with(user("reader").roles("USER")))
            .andExpect(status().isForbidden());
    }

    @Test
    void postWithCsrfCanProceed() throws Exception {
        mvc.perform(post("/web/account/email")
                .with(user("reader").roles("USER"))
                .with(csrf()))
            .andExpect(status().is2xxSuccessful());
    }
}
```

Các static imports cần thiết (phụ thuộc phiên bản tương ứng):
- `MockMvcRequestBuilders.get` và `post`.
- `MockMvcResultMatchers.status`.
- `SecurityMockMvcRequestPostProcessors.user` và `csrf`.

Các endpoint/status là giả định và phải tồn tại trong ứng dụng thật. Nếu controller thành công trả 302/204/201, phải kiểm tra status theo contract của nó. **Spring Boot 4 có tổ chức module/test packages khác Boot 3 ở một số thành phần**, vì vậy cần đối chiếu các test annotations/imports theo hướng dẫn phiên bản đang dùng; không copy nguyên code Boot 3 mà không điều chỉnh.

## 21. Test JWT authorization với mock principal

Với `spring-security-test`:

```java
@Test
void orderReadAllowedWithScope() throws Exception {
    mvc.perform(get("/api/orders/42")
            .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_orders.read"))))
        .andExpect(status().isOk());
}

@Test
void orderReadDeniedWithOnlyWriteScope() throws Exception {
    mvc.perform(get("/api/orders/42")
            .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_orders.write"))))
        .andExpect(status().isForbidden());
}
```

Cần import `SecurityMockMvcRequestPostProcessors.jwt`, `SimpleGrantedAuthority` và các MockMvc static imports. Test chỉ xác minh authorization với principal đã dựng sẵn, không kiểm chứng signature, issuer, audience, token expiry hay JWKS. Những yếu tố đó phải được test ở tầng JWT decoder/integration.

Ngoài positive path, hãy test authority casing, scope prefix, token thuộc tenant khác, user thiếu permission và response không lộ dữ liệu.

## 22. Test Method Security

```java
@SpringBootTest
class ReportMethodSecurityTest {
    @Autowired
    ReportService reportService;

    @Test
    @WithMockUser(authorities = "reports.read")
    void readerCannotExport() {
        assertThrows(AccessDeniedException.class,
            () -> reportService.export("R-42"));
    }

    @Test
    @WithMockUser(authorities = "reports.export")
    void exporterCanExport() {
        reportService.export("R-42");
    }
}
```

Đoạn code rút gọn cần imports JUnit/Spring và bean `ReportService` đã khai báo ở trên. Nó chỉ có ý nghĩa nếu `@EnableMethodSecurity` đã được bật và test lấy bean qua proxy từ Spring context. Bổ sung tests cho self-invocation, internal service calls và expression parameter names nếu ứng dụng dùng chúng.

## 23. Test session, CSRF và CORS theo chuỗi request

Một request đơn lẻ chưa đủ xác nhận session policy. Nên thử:
1. POST login hợp lệ.
2. Lấy cookie/session từ response.
3. Request kế tiếp dùng session và truy cập tài nguyên được bảo vệ.
4. Logout và thử lại request với session cũ.
5. Session hết hạn hoặc vô hiệu hóa phải bị từ chối.
6. Đổi privilege/session fixation phải tạo kết quả đúng contract.

Với CSRF:
- POST thiếu token bị chặn khi policy yêu cầu.
- POST có token hợp lệ được đi vào nghiệp vụ.
- Token sai hoặc của session khác bị từ chối.
- Những API bearer token stateless được kiểm thử riêng, không vô tình mở web.

Với CORS:
- OPTIONS preflight từ origin hợp lệ được phản hồi đúng.
- Origin không hợp lệ không được chấp nhận.
- Actual request vẫn bị xác thực và phân quyền bình thường.
- Không gộp CORS allowlist với authorization rules.

## 24. Reactive WebFlux có stack khác Servlet

Nếu ứng dụng là WebFlux, không dùng cấu hình Servlet nguyên trạng:

| Spring MVC / Servlet | Spring WebFlux |
|---|---|
| `HttpSecurity` | `ServerHttpSecurity` |
| `SecurityFilterChain` | `SecurityWebFilterChain` |
| `HttpServletRequest` | `ServerWebExchange` |
| `MockMvc` | `WebTestClient` |
| Servlet Filter | WebFilter |

Ví dụ:

```java
@Bean
SecurityWebFilterChain reactiveChain(ServerHttpSecurity http) {
    return http
        .authorizeExchange(exchange -> exchange
            .pathMatchers("/public/**").permitAll()
            .pathMatchers("/admin/**").hasRole("ADMIN")
            .anyExchange().authenticated())
        .httpBasic(Customizer.withDefaults())
        .build();
}
```

Migration cần đọc đúng hướng dẫn Servlet hay Reactive. Phương thức lấy SecurityContext, WebFlux filter order, session và test infrastructure có các cơ chế khác.

## 25. Chẩn đoán lỗi phổ biến

| Triệu chứng | Nguyên nhân có thể | Cách điều tra |
|---|---|---|
| Không tìm thấy `WebSecurityConfigurerAdapter` | API cấu hình cũ đã bị loại. | Chuyển sang bean `SecurityFilterChain`. |
| Không tìm thấy `antMatchers` | Chặng API/matcher mới. | Dùng matcher được support, kiểm tra ngữ nghĩa path. |
| `NoClassDefFoundError: javax/servlet/...` | Trộn Servlet namespace cũ với Jakarta runtime. | Xem dependency graph/framework/container. |
| Admin endpoint không bị chặn | Không khớp chain hoặc fallback quá rộng. | Rà `securityMatcher`, `@Order` và negative tests. |
| User hợp lệ nhận 403 | Role/authority mapping sai hoặc thiếu permission. | Kiểm tra quyền và matcher. |
| API bearer trả 302 login | Request rơi vào form-login chain. | Tách chain/entry point. |
| POST web bị 403 | CSRF thiếu hoặc sai. | Kiểm tra token flow trước khi đổi policy. |
| Preflight OPTIONS bị 401 | CORS bị chặn bởi authentication. | Kiểm tra cấu hình CORS trong chain. |
| Sau login request tiếp lại 401 | SecurityContext chưa được lưu đúng. | Xem custom auth flow/repository/session. |
| JWT test mock xanh, production 401 | JwtDecoder/JWKS/issuer không được kiểm thử. | Integration tests với token đã ký. |
| `@PreAuthorize` không chạy | Method security chưa bật hoặc proxy bị bypass. | Test qua Spring bean thật. |
| Custom filter chạy hai lần | Đăng ký cả container lẫn Security chain. | Xem filter registrations và order. |
| 401/403 bất thường ở /error | ERROR/FORWARD dispatch bị match khác. | Test error flow và dispatcher types. |

Đừng sửa lỗi bằng cách chuyển rule sang `permitAll` mà chưa hiểu nguyên nhân.

## 26. Kế hoạch migration theo wave

### Wave 0 — Baseline

Xác định JDK, Spring Boot/Framework/Security, dependency versions, chain config, endpoint inventory. Lưu security contract tests và auth failure metrics trước khi nâng.

### Wave 1 — Bản cầu nối

Nếu đi từ 5.x lên 6, đọc hướng dẫn chuẩn bị từ 5.8; nếu từ 6.x lên 7, đọc hướng dẫn chuẩn bị từ 6.5. Chuyển deprecated APIs, cấu hình lambda, bean SecurityFilterChain và các cách đặt matchers được khuyến nghị.

### Wave 2 — Authorization and matching

Xác định toàn bộ URL/method rules, `securityMatcher`, `@Order`, catch-all, role prefix và mapping scope. Chạy positive/negative tests và kiểm tra encoded paths.

### Wave 3 — Authentication integrations

Kiểm tra password encoders, custom providers, OAuth2/OIDC, JWT signature/issuer/audience/JWKS, SAML nếu có. Test session context persistence và logout.

### Wave 4 — Browser, method, data security

Test CSRF, CORS, headers, cookies, method security, ownership/tenant and IDOR. Chạy tests với servlet container/gateway/IdP đại diện, không chỉ mock.

### Wave 5 — Triển khai có kiểm soát

Canary hoặc blue-green rollout. Theo dõi login failures, 401/403/302, CSRF rejection, CORS preflight, JWT validation error và access denied. Sẵn sàng rollback cả application config và session/data impact.

## 27. Ma trận security contract test cần lưu

| Case | Credential | Quyền | Kỳ vọng |
|---|---|---|---|
| Public GET | Không | — | Cho phép. |
| Restricted GET | Không | — | 401 hoặc redirect đúng contract. |
| Admin GET | User thường | ROLE_USER | 403. |
| Admin GET | Admin | ROLE_ADMIN | Cho phép. |
| User A đọc tài nguyên B | Token A | Có quyền đọc chung | Từ chối theo ownership policy. |
| POST web không CSRF | Cookie session | User hợp lệ | Từ chối. |
| POST web có CSRF | Cookie + token | User hợp lệ | Đi vào nghiệp vụ. |
| GET API không JWT | Không | — | 401. |
| GET API JWT sai issuer | JWT không tin cậy | — | 401. |
| GET API JWT đúng, thiếu scope | JWT hợp lệ | Thiếu read | 403. |
| GET API JWT đúng, đủ scope | JWT hợp lệ | Có read | Cho phép nếu resource hợp lệ. |
| OPTIONS origin hợp lệ | Preflight | — | CORS headers chính xác. |
| OPTIONS origin lạ | Preflight | — | Không được origin access. |
| Logout sau session login | Cookie cũ | — | Không giữ authentication. |

Lưu các expected results theo version contract. Nếu yêu cầu sản phẩm chủ động đổi từ redirect 302 sang JSON 401 cho API, phải có quyết định và review; không âm thầm cập nhật snapshot test để hợp thức hóa regression.

## 28. Bảo mật sau migration: negative tests trước positive comfort

Các câu hỏi cần kiểm chứng:
- Có URI nào thoát mọi SecurityFilterChain?
- Có HTTP method PATCH/DELETE/OPTIONS không được xét policy?
- Có bypass bằng URL encoding, trailing slash, servlet mapping hoặc proxy prefix?
- Có custom filter nào bypass authorization?
- Có role/scope nào tăng quyền ngoài ý định?
- Có token sai issuer/audience/expiry được chấp nhận?
- Có cách truy cập dữ liệu của người khác trong cùng tenant hoặc giữa tenants?
- Logout có vô hiệu hóa session thực sự?
- Error handler có lộ nội dung nhạy cảm?
- Audit có ghi đủ access-denied events mà không rò token?

Những negative cases nên được tự động hóa và chạy cả sau khi nâng Security 7/matcher semantics. Một test “admin thành công” không thay thế test “user thường bị từ chối”.

## 29. Rollout, rollback và quan sát production

Khi chạy hai phiên bản song song:
- Cookie name/path/domain/SameSite và security key có tương thích?
- Session store có deserialize được state từ cả hai version?
- OAuth callback/redirect URI có đúng gateway/canary route?
- JWT authorities mapping có giống nhau?
- Proxy có giữ `X-Forwarded-Proto`/forwarded headers đúng?
- Hành động logout một version có hiệu lực với version kia?
- Nếu rollback code, session hoặc token được tạo mới có còn hợp lệ?

Theo dõi các metric tách theo endpoint/category:
- Login success/fail, MFA challenge nếu có.
- HTTP 401/403/302, bất thường theo user class mà không log PII.
- JWT validation/expired/issuer failures.
- CSRF/CORS failures.
- Latency tăng do authentication/authorization/IdP.
- Audit coverage, access-denied events.

Không giảm quyền truy cập toàn bộ để giảm 403 khi chưa xác minh request nào đáng được cho phép.

## 30. Các nhầm lẫn cần tránh

**Build xanh nghĩa là migration xong.** Chưa biết có endpoint bị mở quyền.

**Chỉ đổi tên API matcher.** Có thể còn khác biệt path semantics, order và servlet context.

**Bỏ CSRF cho mọi REST API.** REST có thể dùng cookie/session, vẫn cần phân tích CSRF.

**`hasRole("ADMIN")` và `hasAuthority("ADMIN")` là một.** Prefix `ROLE_` mặc định có thể khiến khác nhau.

**Mock JWT đủ kiểm tra chữ ký.** `jwt()` helper không thay thế JWT decoder integration.

**Không cần catch-all nếu đã có /api matcher.** Requests không khớp chain có thể không được bảo vệ.

**Có authenticated() là có ownership.** Authorization theo ID/tenant còn là hợp đồng riêng.

**Chỉ bảo vệ Controller.** Service layer có thể được gọi từ job/listener hoặc code khác.

**Method security annotation tự hoạt động với đối tượng tạo bằng new.** Proxy/AOP có thể không tham gia.

**403 luôn là lỗi.** CSRF hoặc thiếu quyền có thể được từ chối đúng.

## 31. Checklist trước khi phê duyệt Spring Security mới

- [ ] Đã ghi Spring Security, Spring Boot, Spring Framework, Servlet/Jakarta và JDK versions.
- [ ] Đã đọc đúng migration guide và release notes cho từng chặng.
- [ ] Đã inventory tất cả chains, matchers, filter order và custom auth flows.
- [ ] Đã có endpoint × principal × credential × expected result matrix.
- [ ] Đã test mọi URI bảo vệ thực sự khớp ít nhất một security chain.
- [ ] Đã xử lý path matcher, context path, multi-servlet và encoded path.
- [ ] Role, authority, scope, claim mapping đã có positive/negative tests.
- [ ] JWT decoder thật đã test signature, issuer, audience, expiry và key rotation.
- [ ] CSRF vẫn được yêu cầu cho các luồng cookie/session cần bảo vệ.
- [ ] CORS preflight và actual request được test riêng.
- [ ] Session login/logout/expiry và persistence qua nhiều requests được test.
- [ ] OAuth2/OIDC/SAML flows được test nếu có.
- [ ] Method Security chạy qua Spring proxy và có negative tests.
- [ ] Custom filters không bị đăng ký hai lần hoặc sai order.
- [ ] Ownership/tenant/IDOR tests không bị mất.
- [ ] Security headers/cookies/HTTPS redirect được test sau proxy.
- [ ] Có kế hoạch canary, audit/metrics và rollback khi session state thay đổi.
- [ ] Không nới quyền để làm tests xanh mà thiếu security review.

## Tài liệu tham khảo

- [Spring Security Reference](https://docs.spring.io/spring-security/reference/): tài liệu chính thức về HTTP security, authentication và authorization.
- [Spring Security 6 Migration Guide](https://docs.spring.io/spring-security/reference/6.5/migration/index.html): chuẩn bị từ 5.8 và di chuyển sang 6.
- [Spring Security 7 Migration Guide](https://docs.spring.io/spring-security/reference/7.0/migration/index.html): các bước nâng lên 7.
- [Spring Security 7 Web Migration Preparation](https://docs.spring.io/spring-security/reference/6.5/migration-7/web.html): PathPattern và các thay đổi matcher.
- [Spring Security Configuration Migration to 7](https://docs.spring.io/spring-security/reference/6.5/migration-7/configuration.html): Lambda DSL và các thay đổi cấu hình.
- [Spring Security 6.5 Java Configuration](https://docs.spring.io/spring-security/reference/6.5/servlet/configuration/java.html): sự khác nhau giữa securityMatcher và requestMatchers.
- [Spring Security 7 Authorization](https://docs.spring.io/spring-security/reference/7.0/servlet/authorization/authorize-http-requests.html): AuthorizationManager và authorizeHttpRequests.
- [Spring Security Testing OAuth 2.0](https://docs.spring.io/spring-security/reference/7.0/servlet/test/mockmvc/oauth2.html): jwt mock và MockMvc tests.
- [Spring Security CSRF](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html): nguyên tắc chống CSRF.
- [Spring Boot Reference](https://docs.spring.io/spring-boot/reference/): compatibility, auto-configuration và testing theo Boot release.
- [OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html): deny-by-default, least privilege và IDOR prevention.
- [OWASP ASVS](https://owasp.org/www-project-application-security-verification-standard/): gợi ý xây security verification requirements.

## Kết luận

Nâng Spring Security phải được thực hiện như **một lần chuyển đổi hợp đồng bảo mật**. Các thay đổi API trong Spring Security 6/7, nhất là bean `SecurityFilterChain`, Lambda DSL, request matchers và module Jakarta, chỉ là phần biểu hiện ở source code. Điều quan trọng là xác nhận mọi endpoint và mọi hành động vẫn áp dụng đúng authentication, authorization, CSRF, CORS, session và JWT policies. Hãy lập baseline, kiểm thử cả người được phép và người phải bị từ chối, xác nhận JWT thật và các proxy/container integrations, rồi triển khai canary với khả năng rollback. Một migration tốt không chỉ tránh lỗi khởi động mà còn tránh việc hệ thống cấp thêm quyền truy cập ngoài ý định.

