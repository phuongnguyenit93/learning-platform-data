# Từ cấu hình nối chuỗi cũ sang Lambda DSL trong Spring Security Servlet

## 1. Bối cảnh nâng cấp: mục tiêu là giữ nguyên chính sách bảo mật

Một dự án Spring MVC có thể từng cấu hình Spring Security theo cách **nối chuỗi (chained DSL)**:

~~~java
// Mã kiểu CŨ, dùng để đọc/so sánh, không biên dịch trong Spring Security 6.
http
    .authorizeRequests()
        .antMatchers("/public/**").permitAll()
        .antMatchers("/admin/**").hasRole("ADMIN")
        .anyRequest().authenticated()
        .and()
    .formLogin()
        .and()
    .httpBasic();
~~~

Kiểu này gọi các configurer trả về một đối tượng trung gian, rồi dùng `.and()` để quay lại cấu hình cha `HttpSecurity`. Khi cấu hình lớn, người đọc khó biết phương thức đang áp dụng cho configurer nào; cú pháp được đánh giá và hỗ trợ khác nhau giữa các dòng Spring Security.

Trong **Lambda DSL**, từng configurer nhận một hàm lambda rõ phạm vi:

~~~java
// Kiểu MỚI, dành cho Spring Security 6 / Servlet.
http
    .authorizeHttpRequests(auth -> auth
        .requestMatchers("/public/**").permitAll()
        .requestMatchers("/admin/**").hasRole("ADMIN")
        .anyRequest().authenticated())
    .formLogin(Customizer.withDefaults())
    .httpBasic(Customizer.withDefaults());

return http.build();
~~~

Trong file Java cần import `org.springframework.security.config.Customizer`. Những đoạn đầu bài là mảnh cấu hình bên trong phương thức nhận `HttpSecurity`, không phải class có thể chạy độc lập; ví dụ hoàn chỉnh và project Maven nằm ở mục 9.

**Điều quan trọng nhất:** nâng cấp DSL phải **giữ hoặc chủ động thay đổi có kiểm chứng** các bất biến bảo mật: endpoint nào public, ai được gọi method nào, CSRF có hiệu lực với POST hay không, entry point khi chưa login, các filter/cookie/session/headers, và cách kiểm quyền trên dữ liệu. Không coi việc “code biên dịch lại được” là bằng chứng không có authentication/authorization regression.

Bài thuộc chủ đề **Nâng cấp** của Spring Security Servlet, tập trung vào chuyển từ chain/ `.and()` sang lambda, cùng những API liên quan đã thay đổi. Ví dụ thực hành dùng **Java 17, Spring Boot 3.3.5 và Spring Security 6**, trong đó phiên bản chỉ để minh họa một baseline cụ thể, **không** khẳng định đây là bản mới nhất hoặc còn được hỗ trợ tại thời điểm phát hành. Khi áp dụng vào sản phẩm, hãy kiểm release notes, migration guide và version support của chính dòng đang sử dụng.

## 2. Từ WebSecurityConfigurerAdapter đến bean SecurityFilterChain

Trong code đời cũ, có thể gặp:

~~~java
// MÃ LỊCH SỬ — Spring Security 5.x, KHÔNG dùng được nguyên trạng với 6.x.
@EnableWebSecurity
public class LegacySecurityConfig extends WebSecurityConfigurerAdapter {

    @Override
    protected void configure(HttpSecurity http) throws Exception {
        http
            .authorizeRequests()
                .antMatchers("/public/**").permitAll()
                .antMatchers("/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated()
                .and()
            .httpBasic();
    }
}
~~~

`WebSecurityConfigurerAdapter` được đánh dấu deprecated trong Spring Security 5.7 và bị loại bỏ trong Spring Security 6. `antMatchers()` và kiểu cấu hình `authorizeRequests()` là những dấu hiệu cần kiểm khi nâng lên API mới. Lambda DSL không chỉ thay `.and()`: ứng dụng cũng nên chuyển về **bean-based configuration**.

Phiên bản Spring Security 6 tương ứng:

~~~java
@Configuration
@EnableWebSecurity
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/**").permitAll()
                .requestMatchers("/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated());

        http.httpBasic(Customizer.withDefaults());

        return http.build();
    }
}
~~~

Imports của mảnh mã này: `org.springframework.context.annotation.Bean`, `org.springframework.context.annotation.Configuration`, `org.springframework.security.config.annotation.web.configuration.EnableWebSecurity`, `org.springframework.security.config.annotation.web.builders.HttpSecurity`, `org.springframework.security.config.Customizer`, `org.springframework.security.web.SecurityFilterChain`. Nếu đã dùng Spring Boot auto-configuration, `@EnableWebSecurity` thường không bắt buộc, nhưng có thể khai báo khi cần tường minh.

**Các điểm cần hiểu:**

1. `SecurityFilterChain` là **bean** định nghĩa filter chain cho request được matcher chọn; `HttpSecurity.build()` tạo chain.
2. Không còn override `configure(HttpSecurity)` từ adapter đã bị loại bỏ.
3. Với `authorizeHttpRequests`, Spring Security sử dụng kiến trúc **AuthorizationManager/AuthorizationFilter**; đây không chỉ là tên mới của `authorizeRequests`. Vì thế nên kiểm cả đặc điểm dispatcher type, matcher và thứ tự quyết định.
4. `httpBasic(Customizer.withDefaults())` bật cấu hình mặc định cho HTTP Basic rõ ràng mà không cần gọi kiểu `.httpBasic().and()`.
5. `@Bean` cho phép quản lý nhiều chain có `@Order`, cấu hình các component và test từng route có chủ đích.

**Không nên** vừa kế thừa adapter cũ vừa khai báo `SecurityFilterChain` mới trong cùng một lớp rồi mong Spring tự hòa giải. Khi migration, loại bỏ đường cấu hình cũ và bảo đảm ứng dụng chỉ có các chain có chủ đích.

## 3. Lambda DSL thay đổi điều gì về cách viết?

Một lambda thường có dạng:

~~~java
http.formLogin(form -> form
        .loginPage("/login")
        .defaultSuccessUrl("/home", true)
        .permitAll());
~~~

Ở đây biến `form` là `FormLoginConfigurer`. Các lệnh trong lambda chỉ cấu hình **form login**. Khi lambda đóng, ta quay lại `HttpSecurity` mà **không cần** `.and()`.

So sánh:

| Nhu cầu | Kiểu chained cũ | Lambda DSL hiện đại |
| --- | --- | --- |
| Cho phép public URL | `authorizeRequests().antMatchers(...).permitAll()` | `authorizeHttpRequests(auth -> auth.requestMatchers(...).permitAll())` |
| HTTP Basic mặc định | `httpBasic()` rồi `.and()` nếu cần | `httpBasic(Customizer.withDefaults())` |
| Form Login | `formLogin().loginPage("/login").and()` | `formLogin(form -> form.loginPage("/login"))` |
| CSRF | `csrf().disable()` trong một số code cũ | `csrf(csrf -> csrf.disable())` nếu **có cơ sở bảo mật** |
| Logout | `logout().logoutUrl("/logout").and()` | `logout(logout -> logout.logoutUrl("/logout"))` |
| Session | `sessionManagement().sessionCreationPolicy(...).and()` | `sessionManagement(session -> session.sessionCreationPolicy(...))` |
| Security headers | `headers().frameOptions().sameOrigin().and()` | `headers(h -> h.frameOptions(f -> f.sameOrigin()))` |
| Resource Server JWT | `oauth2ResourceServer().jwt().and()` | `oauth2ResourceServer(oauth -> oauth.jwt(Customizer.withDefaults()))` |

**Không copy `csrf(csrf -> csrf.disable())` như mặc định.** Nó chỉ là cú pháp tương ứng cho một quyết định cấu hình đã được phân tích. Ở ứng dụng có cookie/session và unsafe methods từ browser, bỏ CSRF toàn cục có thể tạo lỗ hổng. Mẫu chính ở mục 9 **giữ CSRF bật**.

`Customizer.withDefaults()` thể hiện: “áp dụng cấu hình mặc định của configurer này mà không tùy chỉnh thêm”, tương đương lambda rỗng về ý nghĩa DSL:

~~~java
http.httpBasic(Customizer.withDefaults());
http.httpBasic(basic -> {});
~~~

Chỉ cần chọn một cách, không gọi cả hai lặp lại trong cùng cấu hình. Lambda rỗng có thể ngắn, nhưng `Customizer.withDefaults()` thường diễn đạt chủ ý tốt hơn.

### 3.1. Có phải thay mọi method call bằng lambda không?

Không. Một số method trên `HttpSecurity` và object khác vẫn sử dụng setter/builder thông thường. Điều cần chuyển là các **configurer DSL dạng no-arg trả configurer + `.and()`**, nhất là các API deprecated/removed, để tránh lẫn phạm vi. Ví dụ:

~~~java
http
    .authorizeHttpRequests(auth -> auth
        .anyRequest().authenticated())
    .httpBasic(Customizer.withDefaults())
    .build();
~~~

Dòng cuối vẫn là `.build()` trên `HttpSecurity`, không phải lỗi. `hasRole(...)` và `permitAll()` vẫn là lời gọi theo chuỗi bên trong lambda, vì chúng định nghĩa rule trên registry.

### 3.2. Vì sao khai báo thứ tự vẫn quan trọng?

Lambda không tự sửa logic **first matching rule wins**. Ví dụ nguy hiểm:

~~~java
http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/api/**").authenticated()
        .requestMatchers("/api/admin/**").hasRole("ADMIN")
        .anyRequest().denyAll());
~~~

Nếu `/api/admin/**` đã khớp rule rộng `/api/**` đứng trước, yêu cầu admin phía sau không còn hiệu lực như mong đợi. Quy tắc đúng là **matcher cụ thể trước matcher rộng**, và test role âm tính:

~~~java
http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/api/admin/**").hasRole("ADMIN")
        .requestMatchers("/api/**").authenticated()
        .anyRequest().denyAll());
~~~

Tương tự, `hasRole("ADMIN")` so khớp `ROLE_ADMIN` theo prefix mặc định, trong khi `hasAuthority("ADMIN")` so khớp đúng chuỗi `ADMIN`. Migration không được làm đổi convention authority một cách vô tình.

## 4. Bản đồ migration chi tiết: URL matcher và API phân quyền

Các API sau thường xuất hiện trong dự án cũ:

~~~java
// Mã lịch sử, không compile với Spring Security 6.
http.authorizeRequests()
    .antMatchers("/api/public/**").permitAll()
    .mvcMatchers("/reports/**").hasRole("ANALYST")
    .antMatchers(HttpMethod.POST, "/orders/**").hasRole("EDITOR")
    .anyRequest().authenticated();
~~~

Trong cấu hình mới, có thể khai báo:

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/public/**").permitAll()
    .requestMatchers("/reports/**").hasRole("ANALYST")
    .requestMatchers(HttpMethod.POST, "/orders/**").hasRole("EDITOR")
    .anyRequest().authenticated());
~~~

`HttpMethod` import từ `org.springframework.http.HttpMethod`. Mảnh mới dùng `requestMatchers`; không mặc định mọi loại matcher **trước và sau** có semantic tương đương tuyệt đối.

**Những thay đổi cần kiểm:**

- `antMatchers` lịch sử và `mvcMatchers` lịch sử không còn là phương thức registry thông dụng trong Spring Security 6; `requestMatchers` là API thống nhất, chọn request matcher phù hợp theo context/các overload.
- Khi Spring MVC hiện diện, lựa chọn matcher có thể dựa trên `HandlerMappingIntrospector` và servlet path; cần **kiểm thực tế** cách decode/normalize URL, trailing slash, encoded slash, matrix variables hoặc servlet path riêng.
- `requestMatchers(HttpMethod.POST, "/orders/**")` chỉ xét POST; GET/DELETE cùng đường có thể cần rule độc lập.
- `requestMatchers("/reports/**")` không có method hạn chế thì áp dụng cho những HTTP methods khớp path, không chỉ GET.
- `anyRequest().authenticated()` và `anyRequest().denyAll()` mang ý nghĩa khác nhau. Khi migration, nên phân loại endpoint và **quyết định có chủ đích** có cần chuyển sang default deny hay giữ behavior cũ.
- Những regex/request matcher custom trước đây cần test riêng, không tự thay bằng `/**` vì dễ mở rộng phạm vi.
- Với `@PreAuthorize`, nếu vẫn dùng `@EnableGlobalMethodSecurity(prePostEnabled=true)` trong code cũ, cần xem migration sang `@EnableMethodSecurity`; URL DSL **không** tự bật method security.

### 4.1. securityMatcher và requestMatchers không thay thế cho nhau

Đây là hai phạm vi:

~~~java
// Chọn NHỮNG request mà toàn bộ filter chain xử lý:
http.securityMatcher("/api/**");

// Phân quyền CHO request nằm trong chain đã chọn:
http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/api/admin/**").hasRole("ADMIN")
        .anyRequest().authenticated());
~~~

`securityMatcher("/api/**")` không tự cấp quyền; nó quyết định **chain có được chọn hay không**. Nếu không chain nào match `/reports/**`, request đó có thể **không được bảo vệ bởi Spring Security**, bất kể một chain khác có `anyRequest().denyAll()` bên trong nó. Mỗi chain chỉ có quyền quyết định đối với request mà nó xử lý.

Ví dụ với nhiều chain:

~~~java
@Bean
@Order(1)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    return http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                    .requestMatchers("/api/admin/**")
                        .hasRole("ADMIN")
                    .anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults())
            .build();
}

@Bean
@Order(2)
SecurityFilterChain fallbackChain(HttpSecurity http) throws Exception {
    return http
            .authorizeHttpRequests(auth -> auth
                    .requestMatchers("/public/**").permitAll()
                    .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults())
            .build();
}
~~~

Đây là **mảnh cấu hình cho application đã có bean dependencies/imports tương ứng**, không phải file độc lập. `@Order` import từ `org.springframework.core.annotation.Order`. Fallback chain không có `securityMatcher` nên có thể xử lý phần còn lại; cần đánh giá public assets, login callbacks và error paths thực tế. Nếu form login với default login URL nằm ngoài `/api/**`, phải kiểm lại chain nào xử lý nó.

Với nhiều servlet, có thể cần `MvcRequestMatcher.Builder` hoặc `PathPatternRequestMatcher` phù hợp với dòng framework, chỉ rõ servlet path. Tránh bê nguyên cấu hình matcher từ ứng dụng khác khi context path hoặc reverse proxy rewrite không giống nhau.

## 5. Chuyển các cấu hình phổ biến mà vẫn giữ chính sách

### 5.1. Form login và trang đăng nhập riêng

Kiểu cũ:

~~~java
// Lịch sử — chained
http.formLogin()
        .loginPage("/login")
        .defaultSuccessUrl("/dashboard", true)
        .permitAll()
        .and();
~~~

Kiểu mới:

~~~java
http.formLogin(form -> form
        .loginPage("/login")
        .defaultSuccessUrl("/dashboard", true)
        .permitAll());
~~~

**Cần có controller/view thực sự cho GET `/login`** nếu chọn trang login riêng. `.permitAll()` ở form login configurer điều chỉnh quyền truy cập các URL liên quan đến login; không bảo đảm file CSS, JS và error view đã được phép. Nếu muốn dùng trang login mặc định do Spring Security cung cấp, có thể dùng `formLogin(Customizer.withDefaults())`.

Thay đổi loginPage, success URL hoặc saved request behavior là **thay đổi UX/security flow**, không nên lẫn vào thao tác chuyển syntax. Với session cookie, giữ kiểm CSRF cho login POST và test session fixation protection, logout, remember-me nếu dùng.

### 5.2. HTTP Basic

~~~java
http.httpBasic(Customizer.withDefaults());
~~~

HTTP Basic gửi `Authorization: Basic ...` cho mỗi request, nên phải chạy qua HTTPS. Khi yêu cầu chưa authenticated, entry point thường trả 401 và header `WWW-Authenticate`; form login thường trả redirect 302. Không coi sự thay đổi status 302 thành 401 là bug hoặc thành công một cách tự động — cần kiểm entry point dựa trên client/contract.

Một ứng dụng có cả `formLogin` và `httpBasic` có thể lựa chọn entry point tùy request, Accept header và chain. Viết test đúng browser/API client thay vì chỉ kiểm một `curl -i`.

### 5.3. CSRF: tránh chuyển `disable` máy móc

Cú pháp legacy:

~~~java
// Lịch sử, thể hiện một policy cần đánh giá lại.
http.csrf().disable();
~~~

Cú pháp lambda tương ứng:

~~~java
// Chỉ minh họa CÚ PHÁP, không khuyến nghị bật cho mọi dự án.
http.csrf(csrf -> csrf.disable());
~~~

**Không lấy đoạn này làm cấu hình mặc định.** Spring Security Servlet thường bật CSRF; đối với các request được browser gửi tự động với cookie/session, cần chống CSRF ở unsafe methods. Khi nâng cấp, đặt câu hỏi: app xác thực bằng cookie, Basic, bearer token, hay hỗn hợp? Browser có tự gắn credential không? Endpoint nào có side effect? Có cross-origin requests không?

Để giữ bảo vệ theo mặc định:

~~~java
http.csrf(Customizer.withDefaults());
~~~

Hoặc không gọi `csrf(...)` nếu cấu hình mặc định phù hợp.

Khi một webhook được xác minh bằng chữ ký riêng và không dùng browser/session, có thể cân nhắc ngoại lệ hẹp:

~~~java
http.csrf(csrf -> csrf
        .ignoringRequestMatchers("/webhooks/verified/**"));
~~~

Đây là **mảnh cấu hình**: phần `/webhooks/verified/**` phải có authentication/signature verification và replay protection thích hợp. Chỉ bỏ CSRF không biến webhook thành an toàn. Đặc biệt, **`permitAll()` không tắt CSRF**: POST tới một URL public vẫn có thể bị CsrfFilter từ chối nếu thiếu token.

### 5.4. CORS

~~~java
http.cors(Customizer.withDefaults());
~~~

Cú pháp bật tích hợp CORS không thay chính sách origin. Ứng dụng cần cung cấp cấu hình CORS phù hợp (chẳng hạn `CorsConfigurationSource` hoặc MVC CORS integration được chọn), chỉ cho phép những origin/method/header cần dùng. Không kết hợp wildcard origin với credential support; preflight OPTIONS thường không mang session cookie nên CORS cần chạy đúng trước authentication.

Một preflight hợp lệ không đồng nghĩa actual request được phép: request thực vẫn cần xác thực, phân quyền và CSRF nếu threat model yêu cầu.

### 5.5. Logout

~~~java
http.logout(logout -> logout
        .logoutUrl("/logout")
        .logoutSuccessUrl("/logged-out")
        .invalidateHttpSession(true));
~~~

Trong ứng dụng có CSRF bật, Spring Security thường yêu cầu **POST /logout** cho logout an toàn. Không thay thành GET logout chỉ để thuận tiện tạo hyperlink nếu điều đó khiến site khác có thể ép người dùng logout. Đảm bảo `/logged-out` tồn tại và được phép truy cập nếu muốn mọi người xem được sau logout.

Khi có remember-me, refresh token hoặc session store phân tán, logout không tự thu hồi mọi access token/session ở hệ thống khác; cần chính sách riêng.

### 5.6. Session management

~~~java
http.sessionManagement(session -> session
        .sessionCreationPolicy(SessionCreationPolicy.IF_REQUIRED));
~~~

Import `org.springframework.security.config.http.SessionCreationPolicy`. Với API thuần bearer token có thể dùng:

~~~java
http.sessionManagement(session -> session
        .sessionCreationPolicy(SessionCreationPolicy.STATELESS));
~~~

**`STATELESS` không có nghĩa mọi request tự được bảo vệ bằng JWT và không tự tắt CSRF.** Bạn còn phải cấu hình cách xác thực token, bảo đảm credential không được browser tự gửi trong mô hình đang dùng và kiểm session usage của các component khác. Không chuyển toàn bộ ứng dụng dùng formLogin/OIDC sang STATELESS chỉ vì đang migration DSL; việc đó có thể làm mất session/state phục vụ login.

### 5.7. Security headers

~~~java
http.headers(headers -> headers
        .contentSecurityPolicy(csp -> csp
                .policyDirectives(
                        "default-src 'self'; object-src 'none'; " +
                        "base-uri 'self'")));
~~~

`Content-Security-Policy` là chính sách cần điều chỉnh theo nguồn script/style/frame thật của ứng dụng; ví dụ trên minh họa syntax và một baseline hạn chế. Đừng thêm `unsafe-inline`/`*` máy móc chỉ để sửa giao diện bị chặn. Với HTML server-rendered có thể cần nonce, hash hoặc report-only rollout.

Spring Security có default security headers, nhưng **không tự phát CSP theo nhu cầu của từng ứng dụng**. HSTS thường phụ thuộc request HTTPS; test trên HTTP MockMvc không đủ để kết luận browser nhận HSTS ở ingress. Cấu hình security headers không thay thế TLS và không cho phép chứa token trong log.

Nếu dự án cũ dùng:

~~~java
// Mảnh mã chained cũ:
http.headers()
        .frameOptions().sameOrigin()
        .and();
~~~

Lambda tương ứng có thể là:

~~~java
http.headers(headers -> headers
        .frameOptions(frame -> frame.sameOrigin()));
~~~

Chỉ nới `frame-options` khi ứng dụng có nhu cầu nhúng hợp lệ và threat model đã xem xét; default DENY có thể phù hợp hơn. Nếu dùng H2 Console trong dev, không mang cấu hình frame/CSRF rộng từ profile dev sang production.

### 5.8. Exception handling và 401/403

~~~java
http.exceptionHandling(errors -> errors
        .authenticationEntryPoint(
                new HttpStatusEntryPoint(HttpStatus.UNAUTHORIZED)));
~~~

Imports cho mảnh: `org.springframework.security.web.authentication.HttpStatusEntryPoint` và `org.springframework.http.HttpStatus`. Đây là lựa chọn cho API muốn trả 401 thay redirect; không bắt buộc khi đã dùng HTTP Basic phù hợp. Với ứng dụng cả browser và API, tùy biến entry point theo RequestMatcher có thể cần thiết hơn cấu hình toàn cục.

**401** thường dành cho request chưa được xác thực; **403** cho authenticated user thiếu quyền, hoặc request bị CSRF từ chối. Test POST bị 403 mà thiếu CSRF token **không chứng minh** role enforcement chính xác.

### 5.9. OAuth2 Login và OIDC

Khi dự án có OAuth2 Client, cấu hình từng nhánh user service bên trong lambda:

~~~java
// Mảnh cấu hình, cần oauth2-client dependency và các bean tương ứng.
http.oauth2Login(oauth2 -> oauth2
        .userInfoEndpoint(userInfo -> userInfo
                .userService(customOAuth2UserService)
                .oidcUserService(customOidcUserService)));
~~~

`userService` dùng cho OAuth2 login không OIDC; `oidcUserService` cho OpenID Connect. Không chỉ thay `.and()` mà bỏ nhầm OIDC-specific configurer. Trong regression cần kiểm authorization code callback, state, nonce khi áp dụng, ID token validation, issuer, redirect URI, session và mapping local identity/roles.

### 5.10. OAuth2 Resource Server / JWT

~~~java
// Mảnh cấu hình, không nằm trong Maven demo mục 9.
http.oauth2ResourceServer(oauth2 -> oauth2
        .jwt(Customizer.withDefaults()));
~~~

Cấu hình này chỉ có ý nghĩa khi app có dependency `spring-boot-starter-oauth2-resource-server` và JWT decoder/issuer/JWK settings phù hợp. Nó không phát JWT và không tự chỉ định audience; cần policy về issuer, audience, expiry, thuật toán, role/scopes, error handling. Đừng nhầm `oauth2Login` cho browser với `oauth2ResourceServer` cho bearer API.

### 5.11. API chỉ cho phép HTTPS

Với môi trường phù hợp, có thể diễn đạt chính sách yêu cầu secure channel qua Lambda DSL; nhưng HTTPS ở ingress, proxy forwarded headers và runtime awareness phải được cấu hình đồng bộ. Nếu app chạy HTTP nội bộ sau trusted TLS terminator, một chính sách “redirect HTTP → HTTPS” sai có thể gây vòng lặp. Kiểm scheme thực tế mà Spring nhìn thấy, trust proxy và secure cookies bằng integration test qua ingress.

## 6. Những thay đổi không thuần cú pháp khi nâng cấp Spring Security

Nhiều nhóm gặp lỗi vì nghĩ rằng tất cả sự khác biệt đều do thay đổi chữ `.and()` thành `->`. Thực tế cần phân biệt **DSL style migration** và **framework semantic migration**.

| Vùng | Điều có thể thay đổi | Cách kiểm |
| --- | --- | --- |
| Adapter → SecurityFilterChain bean | Bean ordering, chain selection, default chain từ Spring Boot | Đếm chain, kiểm `securityMatcher`/`@Order`, test từng route |
| `authorizeRequests` → `authorizeHttpRequests` | AuthorizationManager/AuthorizationFilter, dispatch/invocation behavior | Role matrix + FORWARD/ERROR dispatch tests |
| `antMatchers`/`mvcMatchers` → `requestMatchers` | Path matching theo MVC/servlet, URL encoding, method | Negative tests path, query, servlet context |
| `hasRole`/authority mapping | Prefix và hierarchy; không tự kế thừa role | Test `ROLE_USER` vs `ROLE_ADMIN` |
| CSRF config | Matcher và token handling, đặc biệt SPA/session | POST/PUT/DELETE có/không/sai CSRF |
| Form login/OIDC | Entry point, redirect, session, state/callback | Login success/fail, cookie, redirect, logout |
| Headers | CSP, HSTS, frame options và giá trị mặc định theo phiên bản | Kiểm HTTP headers qua HTTPS/browser |
| Custom DSL | API `apply`/`with`, bean lifecycle | Kiểm filter order, test effect trước/sau |
| Multiple chains | Fallback chain, chain không match request | Test route ngoài /api, static, error, actuator |
| Method security | `@EnableMethodSecurity`, proxy/SpEL differences | Gọi Spring-managed service và HTTP |

Các ví dụ về API cũ là **mã lịch sử để nhận diện/đối chiếu**; không biên dịch trực tiếp bằng Boot 3.x. Với project thật, hãy tra migration guide đúng phiên bản nguồn/đích (ví dụ 5.x → 6.x hay 6.x → 7.x) và test theo policy của hệ thống.

### 6.1. FORWARD, ERROR và ASYNC dispatcher

Trong Servlet, một request có thể được dispatch qua `REQUEST`, `FORWARD`, `ERROR` hoặc `ASYNC`. Khi thay chiến lược authorization, hãy kiểm `spring.security.filter.dispatcher-types`, filter registration và các rule dành cho internal forward/error views. Đừng cho `dispatcherTypeMatchers(FORWARD).permitAll()` đại trà nếu có endpoint xử lý dữ liệu nhạy cảm được gọi bằng forward.

Một cách tiếp cận an toàn là bảo vệ URL nguồn và đích, có method/service-level authorization cho dữ liệu nhạy cảm. Với test, `MockMvc.forwardedUrl(...)` không tự chứng minh container đã thực hiện forward thật và filter có chạy lại; cần integration test khi điều đó là yêu cầu bảo mật.

### 6.2. Static resource và bỏ qua filter

`web.ignoring().requestMatchers("/assets/**")` có thể khiến static requests không qua các security filters/headers. Trong nhiều ứng dụng, nên dùng:

~~~java
http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/assets/**", "/login").permitAll()
        .anyRequest().authenticated());
~~~

**Chỉ** tài nguyên công khai mới nên permit. Không lưu file upload riêng trong `classpath:/static/` rồi bảo vệ controller `/files/**`; file có thể còn được tải từ static URL khác. Route download riêng cần owner/tenant ACL ở service, không chỉ role URL.

### 6.3. Method security không thay bằng URL DSL

Khi có `@PreAuthorize`, migration từ `@EnableGlobalMethodSecurity(prePostEnabled=true)` sang `@EnableMethodSecurity` có thể phù hợp với Spring Security 6. Đừng loại bỏ method security chỉ vì URL rules đã được chuyển sang lambda.

Ví dụ mảnh:

~~~java
@Service
class DocumentService {

    @PreAuthorize("hasRole('READER') and " +
                  "@documentAccess.canRead(authentication, #p0)")
    Document read(String documentId) {
        // Lấy đúng document ID, kiểm ownership trong service.
        return repository.getRequired(documentId);
    }
}
~~~

Đây là **mảnh minh họa chưa tự biên dịch**: `Document`, `repository`, `documentAccess` là domain dependencies của ứng dụng. `#p0` tham chiếu tham số method đầu tiên; cần có bean `documentAccess` và `@EnableMethodSecurity`. Method-level checks chỉ chạy khi lời gọi đi qua Spring security proxy; self-invocation có thể bỏ qua proxy.

## 7. Quy trình refactor từng bước, không mở rộng quyền ngoài ý muốn

Dùng một **phương pháp có kiểm chứng** thay vì chuyển toàn bộ file bằng search/replace:

1. **Chụp baseline policy**: liệt kê `SecurityFilterChain` cũ, URL/method, matcher order, role, public assets, login/logout, CSRF, CORS, session, headers và custom filters.
2. **Lập ma trận kỳ vọng**: anonymous/USER/ADMIN/tenant khác, GET/POST/PUT/DELETE, CSRF hợp lệ/thiếu/sai, 401/302/403 và business state.
3. **Nâng đúng runtime/toolchain**: Java 17+ nếu chuyển sang Spring Boot 3 / Spring Framework 6; cập nhật BOM tương thích thay vì nâng từng Spring Security module tùy tiện.
4. **Chuyển cấu trúc**: `WebSecurityConfigurerAdapter` → `SecurityFilterChain @Bean`; giữ request scope, filter chain order và authentication providers.
5. **Chuyển từng configurer**: `authorizeRequests` → `authorizeHttpRequests`, `antMatchers`/ `mvcMatchers` → `requestMatchers` phù hợp; `formLogin`/`httpBasic`/`logout`/`csrf`/headers/CORS sang lambda.
6. **Xóa `.and()` theo ngữ nghĩa**: không xóa thô tất cả chuỗi `.and()` rồi đoán code compile; đối chiếu từng scope configurer trước/sau.
7. **Rà soát khác biệt hành vi**: matcher resolution, dispatcher, default-deny, login entry point và CSRF token, đặc biệt khi thay `authorizeRequests` bằng `authorizeHttpRequests`.
8. **Chạy security regression**: MockMvc cho URL và method role matrix; integration cho login/OIDC/LDAP, TLS/ingress, forwarded/ERROR dispatch và cookie/session.
9. **Kiểm hiệu lực runtime**: đúng profile/env vars, không có default/generated user ngoài ý muốn, không có chain bỏ sót, Actuator/debug không public.
10. **Phát hành có rollback**: ghi commit/dependency tree, artifact digest và security test report; kiểm canary/staging trước production, so 401/403/CSRF rejections sau deploy.

Một migration thành công có thể cố ý **siết** một route từng bị public nhầm. Khi đó phải cập nhật test và changelog theo quyết định được duyệt, không “giữ nguyên behavior” của một lỗ hổng cũ. Ngược lại, nếu một rule cũ kiểm owner/tenant mà bản mới chỉ kiểm role, đó là regression bảo mật dù mọi request hợp lệ trước đây vẫn trả 200.

### 7.1. Những câu grep tìm cấu hình cũ

Trong terminal có Git và shell phù hợp:

~~~bash
# Tìm các dấu hiệu legacy, đọc thủ công từng kết quả.
git grep -n -E 'WebSecurityConfigurerAdapter|authorizeRequests|antMatchers|mvcMatchers'
git grep -n -E 'csrf\(\)|formLogin\(\)|httpBasic\(\)|sessionManagement\(\)'
git grep -n 'web.ignoring'
git grep -n 'EnableGlobalMethodSecurity'
~~~

Một số biểu thức như `csrf()` cũng có thể xuất hiện trong **test helper**, không phải production config; không mass-replace thiếu phân biệt. `git grep` chỉ tìm source đã theo dõi, không bao gồm cấu hình từ secret manager/Helm hay thư viện thứ ba; kiểm runtime config riêng.

### 7.2. Mẫu mapping trước và sau cho cùng một yêu cầu

Yêu cầu: public GET `/public/status`, USER được GET `/api/me`, ADMIN được GET `/admin/audit`, các route khác bị chặn.

Legacy illustration:

~~~java
// MÃ CŨ, syntax chỉ áp dụng dòng Spring Security hỗ trợ API cũ.
http.authorizeRequests()
        .antMatchers(HttpMethod.GET, "/public/status").permitAll()
        .antMatchers(HttpMethod.GET, "/api/me").hasRole("USER")
        .antMatchers(HttpMethod.GET, "/admin/audit").hasRole("ADMIN")
        .anyRequest().denyAll()
        .and()
        .httpBasic();
~~~

Modern:

~~~java
http.authorizeHttpRequests(auth -> auth
        .requestMatchers(HttpMethod.GET, "/public/status").permitAll()
        .requestMatchers(HttpMethod.GET, "/api/me").hasRole("USER")
        .requestMatchers(HttpMethod.GET, "/admin/audit").hasRole("ADMIN")
        .anyRequest().denyAll());

http.httpBasic(Customizer.withDefaults());
return http.build();
~~~

Chuyển code **không** tự quyết định `/api/me` nên là `hasRole("USER")` hay `authenticated()`: đó là yêu cầu nghiệp vụ, phải giữ policy đã thỏa thuận. Nếu bản cũ cho ADMIN đọc `/api/me` thông qua role hierarchy, bản mới phải test/khai báo hierarchy hoặc `hasAnyRole` tương đương.

## 8. Mục tiêu demo: kiểm cú pháp mới và bất biến bảo mật

Để luyện tập, ta tạo một ứng dụng độc lập dùng HTTP Basic và một số endpoint:

| Method/URL | Anonymous | READER | ADMIN | Ghi chú |
| --- | ---: | ---: | ---: | --- |
| GET `/public/ping` | 200 | 200 | 200 | Công khai rõ ràng |
| GET `/api/me` | 401 | 200 | 200 | Yêu cầu authenticated |
| POST `/api/notes` (CSRF hợp lệ) | 401 | 201 | 403 | Chỉ READER; ADMIN không tự có READER |
| GET `/admin/audit` | 401 | 403 | 200 | Chỉ ADMIN |
| GET `/unexpected` | 401 | 403 | 403 | Default deny (sau auth, nếu auth) |

Ứng dụng dùng người dùng thử `reader` và `admin`, password demo ở dạng `{noop}` **chỉ phục vụ bài học**. Đây là fixture để kiểm behavior bằng HTTP Basic, tuyệt đối không đưa cấu hình mật khẩu này vào production. Không nên copy các endpoint giả lập thành API nghiệp vụ có dữ liệu nhạy cảm mà thiếu ownership/tenant checks.

**Về CSRF:** trong tests kiểm authorization của POST, ta sẽ cấp token hợp lệ để 403 (ADMIN) chỉ xuất phát từ role. Có thêm tests POST thiếu/sai CSRF trả 403 cho user hợp role. Với browser session cần CSRF thật; ở mẫu này bật mặc định để minh họa một migration an toàn.

## 9. Project Java 17 + Spring Boot 3.3.5 hoàn chỉnh

### 9.1. Cấu trúc thư mục

~~~text
lambda-dsl-migration-demo/
  pom.xml
  src/main/java/example/lambdadsl/LambdaDslApplication.java
  src/test/java/example/lambdadsl/LambdaDslSecurityTests.java
~~~

Chỉ cần Maven và JDK 17+ cùng kết nối Maven repository hợp lệ để resolve dependency. **Bản Boot 3.3.5 là baseline minh họa**, không phải gợi ý để một hệ thống mới trong tương lai chọn phiên bản chưa được xác minh security support.

### 9.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>lambda-dsl-migration-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
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
~~~

Dependency cho OAuth2 Login/OIDC, JWT Resource Server và Actuator **không có trong POM demo**; các snippet đó ở mục 5 chỉ để biết cách migration, không thể dùng ngay trong project này nếu không thêm dependency/configuration đúng.

### 9.3. SecurityFilterChain và các controller

**src/main/java/example/lambdadsl/LambdaDslApplication.java**:

~~~java
package example.lambdadsl;

import java.util.Map;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class LambdaDslApplication {

    public static void main(String[] args) {
        SpringApplication.run(LambdaDslApplication.class, args);
    }

    @Bean
    UserDetailsService users() {
        // HỌC TẬP: {noop} cho phép mật khẩu demo không hash.
        // Production cần PasswordEncoder và nguồn user đáng tin.
        return new InMemoryUserDetailsManager(
                User.withUsername("reader")
                    .password("{noop}demo-pass")
                    .roles("READER")
                    .build(),
                User.withUsername("admin")
                    .password("{noop}demo-pass")
                    .roles("ADMIN")
                    .build());
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(
                    HttpMethod.GET, "/public/ping").permitAll()
                .requestMatchers(
                    HttpMethod.GET, "/api/me").authenticated()
                .requestMatchers(
                    HttpMethod.POST, "/api/notes").hasRole("READER")
                .requestMatchers(
                    HttpMethod.GET, "/admin/audit").hasRole("ADMIN")
                .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults())
            // Ghi tường minh để nhấn mạnh không tắt CSRF.
            .csrf(Customizer.withDefaults())
            .headers(headers -> headers
                .contentSecurityPolicy(csp -> csp
                    .policyDirectives(
                        "default-src 'self'; " +
                        "object-src 'none'; base-uri 'self'")))
            .build();
    }

    @RestController
    static class DemoController {

        @GetMapping("/public/ping")
        Map<String, String> ping() {
            return Map.of("status", "ok");
        }

        @GetMapping("/api/me")
        Map<String, String> me(Authentication authentication) {
            return Map.of("name", authentication.getName());
        }

        @PostMapping("/api/notes")
        ResponseEntity<Map<String, String>> createNote() {
            return ResponseEntity.status(HttpStatus.CREATED)
                    .body(Map.of("id", "note-1"));
        }

        @GetMapping("/admin/audit")
        Map<String, String> audit() {
            return Map.of("result", "restricted");
        }
    }
}
~~~

Đây là một **file Java hoàn chỉnh** cùng POM ở trên; `@SpringBootApplication` giúp Spring Boot scan nested controller. Tất cả lời gọi cấu hình Security đều dùng **Lambda DSL hoặc `Customizer.withDefaults()`**, không còn `WebSecurityConfigurerAdapter`, `authorizeRequests`, `antMatchers` hay `.and()`.

**Chính sách dự kiến:**

- `GET /public/ping`: không cần authentication; `permitAll` nhưng Security filter chain vẫn chạy.
- `GET /api/me`: bất kỳ người dùng hợp lệ nào cũng xem được tên của **chính mình**; Basic provider của demo kiểm password khi request mang credentials.
- `POST /api/notes`: chỉ `ROLE_READER`, phải có CSRF hợp lệ để vượt `CsrfFilter`.
- `GET /admin/audit`: chỉ `ROLE_ADMIN`.
- Route khác: `denyAll`, không mặc định public.
- `Content-Security-Policy` được thêm minh họa syntax headers; nếu ứng dụng thật render HTML/SPA phải kiểm scripts/styles/assets, rollout report-only/nonce khi cần.
- `{noop}` và các `Map` trả JSON là fixture. Endpoint POST không ghi database; bản thật cần validation, object-level ACL, idempotency và bảo vệ dữ liệu.

### 9.4. Chạy ứng dụng và request mẫu

Tại thư mục dự án:

~~~bash
mvn -B -ntp clean verify
mvn spring-boot:run
~~~

Một terminal khác:

~~~bash
# Public GET: 200.
curl -i http://localhost:8080/public/ping

# Chưa xác thực: 401 theo HTTP Basic.
curl -i http://localhost:8080/api/me

# Credentials hợp lệ: 200 + {"name":"reader"}.
curl -i -u reader:demo-pass http://localhost:8080/api/me

# Reader truy cập admin: 403.
curl -i -u reader:demo-pass http://localhost:8080/admin/audit

# Admin được truy cập: 200.
curl -i -u admin:demo-pass http://localhost:8080/admin/audit

# POST thiếu CSRF: thường 403 trước khi kiểm role.
curl -i -u reader:demo-pass -X POST \
    http://localhost:8080/api/notes
~~~

Vì đây là demo với CSRF bật và không có endpoint cấp CSRF token cho curl, **không dùng lệnh POST trên để kết luận `ROLE_READER` có/không có quyền**. Để xác minh POST role với CSRF hợp lệ, dùng `MockMvc.with(csrf())` trong mục 10. Nếu app thực có browser/session, có thể test GET trang/form lấy CSRF token và POST với cùng cookie session.

**HTTP Basic trên HTTP** chỉ để chạy cục bộ. Production phải dùng HTTPS. Mật khẩu demo không được sử dụng cho tài khoản thật hoặc môi trường có dữ liệu nhạy cảm.

## 10. Hồi quy bằng JUnit 5 và MockMvc

Khi chuyển DSL, bộ test nên kiểm:

1. Public endpoint vẫn public đúng method.
2. Anonymous vẫn bị chặn ở endpoint protected.
3. User hợp lệ vượt authentication với credential **thật sự qua HTTP Basic** (khác mock user).
4. Reader không thể truy cập admin.
5. Admin không tự có role READER.
6. POST có role + CSRF hợp lệ được cho phép.
7. POST thiếu/sai CSRF bị từ chối.
8. Route/method không được khai báo bị default-deny.
9. Security header đã cấu hình vẫn xuất hiện.

**src/test/java/example/lambdadsl/LambdaDslSecurityTests.java**:

~~~java
package example.lambdadsl;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class LambdaDslSecurityTests {

    @Autowired
    MockMvc mvc;

    @Test
    void publicPingDoesNotRequireLogin() throws Exception {
        mvc.perform(get("/public/ping"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("ok"));
    }

    @Test
    void anonymousUserCannotReadProfile() throws Exception {
        mvc.perform(get("/api/me"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void basicCredentialsAreValidated() throws Exception {
        mvc.perform(get("/api/me")
                    .with(httpBasic("reader", "demo-pass")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.name").value("reader"));

        mvc.perform(get("/api/me")
                    .with(httpBasic("reader", "wrong")))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void readerCannotReadAdminAudit() throws Exception {
        mvc.perform(get("/admin/audit")
                    .with(httpBasic("reader", "demo-pass")))
                .andExpect(status().isForbidden());
    }

    @Test
    void adminCanReadAudit() throws Exception {
        mvc.perform(get("/admin/audit")
                    .with(httpBasic("admin", "demo-pass")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.result").value("restricted"));
    }

    @Test
    void readerCanCreateWithCsrf() throws Exception {
        mvc.perform(post("/api/notes")
                    .with(httpBasic("reader", "demo-pass"))
                    .with(csrf()))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.id").value("note-1"));
    }

    @Test
    void adminHasNoImplicitReaderRole() throws Exception {
        mvc.perform(post("/api/notes")
                    .with(httpBasic("admin", "demo-pass"))
                    .with(csrf()))
                .andExpect(status().isForbidden());
    }

    @Test
    void missingCsrfIsRejected() throws Exception {
        mvc.perform(post("/api/notes")
                    .with(httpBasic("reader", "demo-pass")))
                .andExpect(status().isForbidden());
    }

    @Test
    void invalidCsrfIsRejected() throws Exception {
        mvc.perform(post("/api/notes")
                    .with(httpBasic("reader", "demo-pass"))
                    .with(csrf().useInvalidToken()))
                .andExpect(status().isForbidden());
    }

    @Test
    void unlistedRouteIsDeniedAfterLogin() throws Exception {
        mvc.perform(get("/unexpected")
                    .with(httpBasic("reader", "demo-pass")))
                .andExpect(status().isForbidden());
    }

    @Test
    void headersArePreservedAfterMigration() throws Exception {
        mvc.perform(get("/public/ping"))
                .andExpect(status().isOk())
                .andExpect(header().string(
                    "X-Content-Type-Options", "nosniff"))
                .andExpect(header().string(
                    "Content-Security-Policy",
                    "default-src 'self'; object-src 'none'; " +
                            "base-uri 'self'"));
    }
}
~~~

Chạy:

~~~bash
mvn -B -ntp clean verify
~~~

**Kỳ vọng:** các tests chạy qua Spring Security filter chain của ứng dụng; chúng kiểm status/body/header đã định nghĩa. Đây là **mã mẫu được rà soát**, không phải báo cáo rằng build đã thật sự chạy thành công trong một môi trường có Maven. Cần chạy lệnh ở máy/CI của người học để biết kết quả thực.

**Tại sao không chỉ dùng `@WithMockUser`?** Với `httpBasic(...)`, ta gửi header thực qua filter/provider, kiểm cả trường hợp password đúng/sai. `@WithMockUser` và `with(user(...))` tạo identity giả lập để test **authorization** nhưng không xác minh password. Kết hợp hai loại tests theo mục tiêu, tránh test “đăng nhập thành công” bằng mock principal rồi tuyên bố provider đã đúng.

**Tại sao cần CSRF token trong test quyền POST?** Nếu không `with(csrf())`, ngay cả một user có quyền có thể nhận 403 từ CsrfFilter trước khi đến rule `hasRole`. Test `adminHasNoImplicitReaderRole` cố ý cấp CSRF hợp lệ để 403 thực sự đến từ thiếu role READER.

## 11. Ma trận test migration ở quy mô thực

Ngoài project tối giản, một ứng dụng sản xuất nên có ma trận:

| Loại đường dẫn | Người gọi | Bối cảnh | Kỳ vọng |
| --- | --- | --- | --- |
| Public CSS/JS/login | Anonymous | GET | Được phép, không lộ dữ liệu riêng |
| Protected API | Anonymous | GET | 401 hoặc redirect theo entry point |
| Protected API | Authenticated đúng role | GET | 200 và đúng object/tenant |
| Protected API | Authenticated sai role | GET | 403 hoặc 404 theo chính sách |
| Admin endpoint | Role thấp | GET | Không truy cập |
| File download | Cùng role khác owner | GET/HEAD/Range | Không tải dữ liệu |
| Mutation endpoint | Role đúng | POST/PUT/PATCH/DELETE + CSRF hợp lệ | Thực hiện đúng một tác động |
| Mutation endpoint | Role đúng | Thiếu/sai CSRF (khi áp dụng) | Từ chối |
| OAuth2 callback | Browser session flow | State/redirect/nonce | Thành công/thất bại đúng giao thức |
| Resource server | Bearer JWT sai signature/issuer/audience | GET/POST | 401/403 đúng contract |
| Forward/internal view | Request trực tiếp/forward | FORWARD dispatcher | Đúng quyền tại nguồn và đích |
| CORS preflight | OPTIONS không credentials | Origin/method/header allowlist | Preflight hợp lệ, actual request vẫn phải auth |
| Error/actuator | Anonymous | ERROR/GET | Không lộ stack trace, secrets, mappings |
| Không match chain | Bất kỳ | URL mới/servlet path | Có fallback bảo vệ, không bypass |

Không nhất thiết phải kiểm mọi tổ hợp vô nghĩa. Nhưng với **mỗi security rule có rủi ro riêng**, cần ít nhất một happy path và một hoặc nhiều denial path. Khi nâng framework, các case **âm tính** thường bắt lỗi privilege escalation tốt hơn chỉ so 200.

### 11.1. Method-level authorization và ownership

Với endpoint `GET /api/documents/{id}`, rule `authenticated()` hoặc `hasRole("READER")` chỉ nói ai được gọi chức năng. Người dùng Alice vẫn không được đọc tài liệu của Bob nếu không có ACL/ownership phù hợp. Test cross-tenant và same-role wrong-owner nên có trong regression trước/sau.

### 11.2. HEAD, OPTIONS, CORS và HTTP method

Một `@GetMapping` của MVC có thể hỗ trợ HEAD, trong khi `requestMatchers(HttpMethod.GET,...)` của Spring Security là rule cho GET. Nếu hệ thống hỗ trợ HEAD, cần mô tả quyền/kiểm thử riêng. OPTIONS được dùng cho CORS preflight; phải kiểm cách chain và CORS xử lý, không `permitAll(OPTIONS, "/**")` rồi tin CORS đã được cấu hình.

### 11.3. Runtime config khác source

Spring Boot có thể nhận cấu hình từ YAML, environment, JVM flags, Config Server, Kubernetes/Helm hoặc secret manager. Khi migration, nguồn cấu hình khác có thể ghi đè port/profile, enabled endpoints, cookie, issuer URI hoặc debug settings. So sánh **effective runtime policy** có redaction, không chỉ `application.yml`.

### 11.4. Các yêu cầu phi chức năng

SecurityFilterChain dùng RequestMatcher/AuthorizationManager có thể tác động hiệu năng; đo latency theo route quan trọng, số lần gọi custom policy hoặc DB lookup, session creation và error rate. Thay đổi matcher rộng/sai có thể tạo 401/403 hàng loạt sau deploy; monitor canary bằng request method, path, status và error category nhưng không log raw credentials/JWT/cookies.

## 12. Các lỗi migration điển hình và cách xử lý

| Lỗi | Biểu hiện | Nguyên nhân hoặc cách sửa |
| --- | --- | --- |
| `WebSecurityConfigurerAdapter` không tồn tại | Compile error khi nâng lên Security 6 | Chuyển sang bean `SecurityFilterChain` |
| `antMatchers()` không tồn tại | IDE/compiler không nhận phương thức | Dùng `requestMatchers` đúng loại và version |
| `authorizeRequests()`/ `.and()` bị deprecated hoặc không còn dùng được ở dòng đích | Warning/compile error | Chuyển `authorizeHttpRequests(auth -> ...)` và lambda configurers |
| `httpBasic()` no-arg deprecated | Compiler warning khi dùng bản mới | `httpBasic(Customizer.withDefaults())` |
| Xóa `.and()` bằng regex rồi code lỗi | Configurer scope và chain bị sai | Refactor theo từng block, không mass replace |
| Matcher rộng đặt trước admin | User thường truy cập admin | Đặt rule cụ thể trước, test role âm tính |
| Dùng `securityMatcher` như rule permit/deny | Chain không match request ngoài phạm vi | Phân biệt chain selection và URL authorization |
| Quên fallback chain | Một URL không được Security xử lý | Có chain catch-all bảo vệ và test route mới |
| `ROLE_ADMIN` không vào `hasRole("USER")` | 403 bất ngờ | Không có role inheritance mặc định; kiểm authority/role hierarchy |
| POST 403 sau khi nâng | Test không có CSRF hoặc role thiếu | Thêm CSRF hợp lệ khi test role, test thiếu CSRF riêng |
| Đưa `csrf.disable()` vào mọi chain | POST từ browser có thể bị CSRF | Chỉ vô hiệu hóa theo threat model và phạm vi hẹp |
| Form login redirect khác HTTP Basic | Anonymous 302 thay 401 | Kiểm authentication entry point, Accept/header/chain |
| Login page vòng redirect | `/login` chưa public hoặc thiếu controller | Form login allowlist + view mapping đúng |
| Static CSS bị chặn | Login page mất giao diện | Permit public assets cụ thể, không bỏ security toàn phần |
| `@PreAuthorize` không có tác dụng | Gọi sai bean hoặc chưa enable method security | `@EnableMethodSecurity`, dùng Spring proxy và negative tests |
| Forwarded view 403 hoặc bị public | Dispatcher rule sai hoặc thiếu target ACL | Kiểm FORWARD registration/authorization, service-level policy |
| CORS preflight bị 401 | OPTIONS không có credential | Tích hợp CORS phù hợp trước auth; actual request vẫn bị kiểm |
| OAuth2/OIDC callback lỗi | Session/state/redirect URI/issuer thay đổi | Integration test login flow, không chỉ test mock principal |
| CSP chặn JS hợp lệ | Header syntax không khớp resource thực | CSP rollout theo report-only/nonce/asset audit |
| Health/actuator vô tình public | Rule `permitAll("/**")` hoặc management chain sai | Explicit allowlist + network/access tests |
| Test xanh nhưng runtime vẫn sai | Test mock không chạy auth provider hoặc proxy thực | End-to-end tests và kiểm effective configuration |

**Hướng debug theo thứ tự:** xác định request đang vào **chain nào**, match **URL/method nào**, authentication entry point nào, có bị CSRF trước authorization không, có gặp `@PreAuthorize`/object ACL không, rồi mới xem MVC handler/status. Không sửa lỗi 403 bằng cách tăng `permitAll` diện rộng.

## 13. Chẩn đoán một tình huống nâng cấp cụ thể

**Triệu chứng:** Sau khi chuyển code sang lambda, `POST /api/orders` luôn bị 403.

**Bước 1 — Kiểm CSRF:** Nếu ứng dụng dùng Spring Security Servlet với CSRF bật, một POST không có token có thể bị chặn dù user đã authenticated. Dùng MockMvc:

~~~java
mvc.perform(post("/api/orders")
        .with(user("member").roles("MEMBER"))
        .with(csrf()))
    .andExpect(status().isCreated());
~~~

Đây là **mảnh test minh họa**; endpoint `/api/orders` phải được khai báo và phép tạo đơn trả 201 trong ứng dụng thực. Nó **không** thuộc project demo ở mục 9, nơi POST endpoint là `/api/notes`.

**Bước 2 — Kiểm method matcher:** Nếu config hiện tại chỉ cho `HttpMethod.GET` ở `/api/orders/**`, POST sẽ rơi vào deny rule. Phải có rule POST được phê duyệt:

~~~java
http.authorizeHttpRequests(auth -> auth
        .requestMatchers(HttpMethod.POST, "/api/orders")
            .hasRole("MEMBER")
        .anyRequest().denyAll());
~~~

**Bước 3 — Kiểm roles:** `hasRole("MEMBER")` đòi `ROLE_MEMBER`, không phải literal `MEMBER`; nếu quyền từ JWT/OIDC là `SCOPE_order.write`, cần mapping được thiết kế/kiểm chứng, không tự cho scope thành admin.

**Bước 4 — Kiểm chain selection:** Nếu `securityMatcher("/web/**")` không khớp `/api/orders`, toàn bộ rule có thể nằm trong chain **không bao giờ được chọn** cho API. Cần một API chain hoặc fallback phù hợp.

**Bước 5 — Kiểm service/CSRF/application:** `@PreAuthorize`, `AccessDeniedHandler`, validation/ownership và method-level checks có thể từ chối sau URL authorization. Ghi log ở mức an toàn, không in token/password và không kết luận từ status một mình.

Sau khi sửa, test lại **member được POST khi có CSRF**, **admin sai role bị từ chối khi có CSRF**, **member thiếu CSRF bị từ chối**, **anonymous với CSRF bị từ chối**, và cùng URL nhưng GET/DELETE theo chính sách. Đó là ma trận giúp ngăn việc “sửa một lỗi 403” bằng cách mở rộng quyền.

## 14. Khi nào Lambda DSL bắt buộc? Chuẩn bị nâng cấp qua nhiều dòng phiên bản

Spring Security 5.7 đã khuyến khích component-based configuration thay cho `WebSecurityConfigurerAdapter`; Spring Security 6 loại bỏ adapter và các matcher cũ. Chained DSL dần được deprecate trong Spring Security 6.x để hướng đến Lambda DSL, đặc biệt khi đi lên các dòng mới hơn.

**Không nhầm “có thể biên dịch” với “API sẽ được duy trì mãi”.** Khi build hiện tại chỉ cảnh báo deprecated, migration sang lambda là cơ hội giảm technical debt trước bản nâng cấp lớn. Khi chuyển phiên bản đích, phải xem **migration guide của đúng release** để biết API nào đã bị removed và hành vi nào đổi.

Các chuẩn bị cần thiết:

- Bỏ `WebSecurityConfigurerAdapter` và các method của adapter trong code đã chuyển lên Spring Security 6.
- Không còn dùng `.antMatchers(...)` trong rules mới; chuyển sang `requestMatchers` với semantics được test.
- Cấu hình chính bằng `SecurityFilterChain` beans, `authorizeHttpRequests` và lambda configurers/`Customizer.withDefaults()`.
- Kiểm `@EnableMethodSecurity`, entry points, CSRF, dispatcher types và nhiều chains.
- Nếu có custom DSL sử dụng `http.apply(...)`, kiểm hướng dẫn migration của framework đích về `http.with(configurer, customizer)` và constructor/bean lifecycle. Không copy API này vào bản framework quá cũ mà chưa xác minh nó được hỗ trợ.
- Không pin Spring Security một phiên bản mới ngẫu nhiên trong khi Spring Boot BOM quản lý các module khác: nâng có kiểm compatibility.

Về custom DSL, một ví dụ **hình thức** trên những dòng hỗ trợ `with`:

~~~java
// Chỉ dùng khi custom configurer và Spring Security version
// đích hỗ trợ API tương ứng.
http.with(customConfigurer, configurer ->
        configurer.setSomeOption(true));
~~~

Đoạn này chỉ minh họa migration concept, **không phải mã biên dịch độc lập**: `customConfigurer` và `setSomeOption` do ứng dụng tùy biến cung cấp. Với một dự án không có custom DSL, không cần thêm `with`; `authorizeHttpRequests`, `httpBasic`, `csrf`... là đủ.

## 15. Bài tập tự kiểm tra

**1.** Vì sao `authorizeRequests().antMatchers(...).and()` không thể chỉ xóa `.and()` rồi dùng với Spring Security 6?  
Vì API configurer/matcher và cơ chế cấu hình đã thay đổi; phải dùng `authorizeHttpRequests`/`requestMatchers` và lambda phù hợp, rồi kiểm semantics.

**2.** `Customizer.withDefaults()` có nghĩa là vô hiệu hóa security control?  
Không. Nó chọn cấu hình mặc định của configurer (ví dụ HTTP Basic), không phải `disable()`.

**3.** `http.securityMatcher("/api/**")` có tương đương `auth.requestMatchers("/api/**").authenticated()` không?  
Không. Một cái chọn phạm vi **filter chain**, một cái quyết định **authorization trong chain**.

**4.** Khi `anyRequest().denyAll()` nằm trong một chain chỉ match `/api/**`, route `/admin` chắc chắn bị từ chối chưa?  
Chưa. Cần có chain khác/fallback xử lý `/admin`; nếu không match chain nào, Spring Security không bảo vệ route đó.

**5.** Vì sao `@WithMockUser` test xanh không đủ chứng minh HTTP Basic password validation đúng?  
Vì annotation tạo authentication mock, không gọi provider xác minh password thật.

**6.** Khi migration, admin nhận 403 ở URL yêu cầu `ROLE_USER`. Có phải bug?  
Không mặc định. `ROLE_ADMIN` không tự có `ROLE_USER` nếu không định nghĩa role hierarchy hoặc cấp cả hai.

**7.** POST của reader trả 403 nhưng request thiếu CSRF. Có thể kết luận reader sai role không?  
Không. Cấp token CSRF hợp lệ để test role; test thiếu CSRF riêng.

**8.** `/public/ping` được `permitAll()` nhưng Spring Security vẫn thêm security headers?  
Thông thường có, vì `permitAll` vẫn để request đi qua filter chain. Bỏ qua filter qua `web.ignoring` khác về bảo vệ.

**9.** Với formLogin, người chưa xác thực có thể nhận 302 thay vì 401 không?  
Có. Tùy authentication entry point và client; không copy expectation của HTTP Basic sang browser flow.

**10.** Vì sao phải kiểm `FORWARD`/ `ERROR` khi nâng sang `authorizeHttpRequests`?  
Vì dispatch behavior/filter registration và đường đích nội bộ có thể ảnh hưởng authorization; cần bảo vệ dữ liệu bằng nhiều lớp và integration tests thích hợp.

**11.** Một số module Spring Security được override cao hơn BOM để vá CVE. Test nào cần chạy?  
Dependency resolution/compatibility, authentication/authorization, session, CSRF, headers, login/OIDC/JWT, integration tests tương ứng và SCA theo bản vá được vendor xác nhận.

**12.** Dùng `httpBasic(Customizer.withDefaults())` có tự khiến cả ứng dụng stateless và CSRF không cần thiết không?  
Không. Cần đánh giá session creation, browser credential behavior và threat model riêng; có Basic không đồng nghĩa bỏ CSRF.

## 16. Checklist trước khi merge thay đổi Lambda DSL

### Kiểm code

- [ ] Đã loại bỏ `WebSecurityConfigurerAdapter`/legacy overrides khi nâng lên dòng không hỗ trợ.
- [ ] `SecurityFilterChain` beans có matcher, order và fallback đầy đủ.
- [ ] `authorizeHttpRequests` dùng `requestMatchers` phù hợp với method/path/servlet.
- [ ] `hasRole`/`hasAuthority`, rule order và default deny được đối chiếu với baseline.
- [ ] Các configurer formLogin/httpBasic/CSRF/CORS/logout/session/headers/OAuth được chuyển từng phần sang lambda.
- [ ] Không đưa `csrf.disable()`, `permitAll("/**")`, `web.ignoring("/**")` hoặc `{noop}` từ demo vào production.
- [ ] `@EnableMethodSecurity` và kiểm owner/tenant vẫn hoạt động khi gọi service bean.
- [ ] Custom filters/AuthenticationProviders/ExceptionHandlers có thứ tự và phạm vi như thiết kế.

### Kiểm hành vi

- [ ] Unit/MockMvc role matrix: public, anonymous, role thấp, admin, sai quyền.
- [ ] Unsafe methods: CSRF hợp lệ/thiếu/sai trong các flow cần bảo vệ.
- [ ] Credential tests: Basic/form login/OIDC/JWT có failure path, không chỉ mock principal.
- [ ] Session/redirect/logout/cookies: kết quả đúng sau migration.
- [ ] Static resources, error/forward, Actuator/internal URLs không lộ.
- [ ] CORS preflight + actual request, security headers, HTTPS/proxy behavior được kiểm khi ứng dụng dùng.
- [ ] Object/tenant ACL không mất khi đổi URL config; test quyền trên dữ liệu cụ thể.
- [ ] Regression tests có cả **negative cases**, không chỉ 200 OK.
- [ ] Dependency BOM/Java version tương thích, không còn deprecated API cần loại bỏ ở phiên bản đích.

### Kiểm phát hành

- [ ] Chạy `mvn -B -ntp clean verify` và kiểm số lượng test thật sự chạy.
- [ ] Review diff bảo mật theo từng rule; không chấp nhận thay đổi quyền ngoài ý định.
- [ ] Kiểm cấu hình hiệu lực ở staging/production profile, secrets và trusted proxy.
- [ ] Lưu artifact digest, release notes và test report; có canary/rollback plan.
- [ ] Theo dõi 401/403/CSRF rejection, login error rate và session issues sau deploy.

**Kết luận:** Chuyển từ chained configuration sang Lambda DSL không phải thao tác “thay cú pháp cho hết warning”. Với Spring Security Servlet, bạn cần hiểu **bean SecurityFilterChain**, phạm vi lambda configurers, **requestMatchers so với securityMatcher**, các thay đổi từ `authorizeRequests` sang `authorizeHttpRequests`, và dùng **kiểm thử hồi quy bảo mật** để bảo đảm ứng dụng vẫn chỉ cho đúng danh tính gọi đúng endpoint/HTTP method với điều kiện CSRF và quyền dữ liệu phù hợp.
