# Cấu hình SecurityFilterChain thay cho mẫu cấu hình cũ

Spring Security 6 chuyển cách cấu hình web security sang mô hình **khai báo các bean SecurityFilterChain**. Các ứng dụng trước đây thường kế thừa WebSecurityConfigurerAdapter, ghi đè configure(HttpSecurity), configure(WebSecurity) hoặc configure(AuthenticationManagerBuilder). Adapter này đã deprecated từ Spring Security 5.7 và bị loại bỏ ở Spring Security 6.0. Khi nâng cấp, cần chuyển từng trách nhiệm sang bean hoặc DSL tương ứng.

Với Spring Security OAuth 2.0 / OIDC Resource Server, cấu hình mới thường ngắn hơn: tạo một bean SecurityFilterChain, khai báo authorization rules và bật JWT hoặc opaque token support. Tuy nhiên, migration không chỉ là đổi tên class. Cần giữ đúng thứ tự matcher, lựa chọn filter chain, CSRF/CORS/session behavior, error handling và các validator của token.

Bài học thuộc chương **Nâng cấp và di chuyển**. Ví dụ dùng Spring Boot 3 và Spring Security 6 theo lambda DSL.

## 1. Vì sao WebSecurityConfigurerAdapter được thay thế?

Mẫu cấu hình cũ tập trung nhiều trách nhiệm vào một subclass:

```java
@EnableWebSecurity
public class SecurityConfig extends WebSecurityConfigurerAdapter {

    @Override
    protected void configure(HttpSecurity http) throws Exception {
        http
            .authorizeRequests()
                .antMatchers("/public/**").permitAll()
                .anyRequest().authenticated()
            .and()
            .oauth2ResourceServer()
                .jwt();
    }
}
```

Cách này buộc ứng dụng kế thừa một adapter để tùy chỉnh cấu hình. Mô hình mới dùng bean và composition: Spring tìm các bean SecurityFilterChain rồi đăng ký chúng với FilterChainProxy.

Lợi ích chính:

- Cấu hình tách thành các bean độc lập, dễ đọc và dễ test.
- Có thể định nghĩa nhiều filter chains với phạm vi URL khác nhau.
- Không cần subclass adapter để khai báo security policy.
- Dependencies được inject tường minh qua method parameters.
- Lambda DSL giúp cấu hình lồng nhau rõ ràng, giảm phụ thuộc vào chuỗi and().

WebSecurityConfigurerAdapter đã deprecated từ Spring Security 5.7 và bị loại bỏ ở Spring Security 6.0. Khi migrate lên 6.x, class kế thừa adapter phải được chuyển đổi; không thể chỉ giữ nguyên code và đổi dependency.

## 2. Chuyển configure(HttpSecurity) thành bean SecurityFilterChain

Cấu hình mới:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain applicationSecurity(HttpSecurity http)
            throws Exception {

        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/public/**").permitAll()
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults())
            );

        return http.build();
    }
}
```

Spring inject một HttpSecurity builder vào bean method. Ứng dụng cấu hình builder rồi gọi build() để tạo SecurityFilterChain.

Các điểm cần nhớ:

- Bean method phải trả về SecurityFilterChain.
- Gọi http.build() sau khi khai báo toàn bộ cấu hình.
- Không gọi build() nhiều lần trên cùng builder.
- Không tự tạo new HttpSecurity(...); hãy dùng builder do Spring cung cấp.
- Có thể inject JwtDecoder, AuthenticationManager, CorsConfigurationSource hoặc handler qua tham số bean method.

Trong Spring Boot, khi ứng dụng cung cấp SecurityFilterChain bean, cấu hình security mặc định của Boot thường lùi lại theo điều kiện auto-configuration. Vì vậy, bean mới cần mô tả đầy đủ các quy tắc mà ứng dụng muốn giữ.

## 3. Chuyển authorization DSL cũ sang authorizeHttpRequests

Một số API cũ đã bị loại bỏ:

| Cấu hình cũ | Cấu hình mới |
| --- | --- |
| authorizeRequests() | authorizeHttpRequests(...) |
| antMatchers(...) | requestMatchers(...) |
| mvcMatchers(...) | requestMatchers(...) |
| WebSecurityConfigurerAdapter | SecurityFilterChain bean |
| @EnableGlobalMethodSecurity | @EnableMethodSecurity |
| DSL chain and() | Lambda DSL |

Ví dụ cũ:

```java
http.authorizeRequests()
    .antMatchers("/health", "/docs/**").permitAll()
    .antMatchers("/admin/**").hasRole("ADMIN")
    .anyRequest().authenticated();
```

Ví dụ mới:

```java
http.authorizeHttpRequests(authorize -> authorize
    .requestMatchers("/health", "/docs/**").permitAll()
    .requestMatchers("/admin/**").hasRole("ADMIN")
    .anyRequest().authenticated()
);
```

Các rule được xét theo thứ tự khai báo. Rule cụ thể cần đứng trước rule tổng quát. Nếu đặt anyRequest().authenticated() trước /admin/**, rule phía sau không còn cơ hội áp dụng.

## 4. Phân biệt securityMatcher và requestMatchers

Đây là khác biệt quan trọng nhất khi dùng nhiều filter chains:

- securityMatcher(...) quyết định **filter chain nào sẽ xử lý request**.
- requestMatchers(...) bên trong authorizeHttpRequests quyết định **quyền của request sau khi đã chọn chain**.

Ví dụ:

```java
@Bean
@Order(1)
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(authorize -> authorize
            .requestMatchers("/api/public/**").permitAll()
            .anyRequest().authenticated()
        )
        .oauth2ResourceServer(oauth2 -> oauth2.jwt(Customizer.withDefaults()));

    return http.build();
}
```

Chain trên chỉ tham gia xử lý các request khớp /api/**. Bên trong chain, /api/public/** được permitAll và các request API còn lại cần Authentication.

Nếu bỏ securityMatcher, chain mặc định có thể áp dụng cho mọi request. Nếu chain có securityMatcher nhưng không khớp request, FilterChainProxy thử chain tiếp theo theo thứ tự. Nếu không chain nào khớp, request không được xử lý bởi các security filters trong những chain đó.

## 5. Khi nào cần nhiều SecurityFilterChain?

Nhiều chain phù hợp khi ứng dụng có các bề mặt bảo mật khác nhau, ví dụ:

- /api/** là Resource Server dùng Bearer JWT.
- /admin/** là browser application dùng form login.
- /actuator/health được mở theo policy riêng.
- Một endpoint nội bộ yêu cầu mutual TLS hoặc cơ chế xác thực riêng.

Ví dụ API và browser cùng ứng dụng:

```java
@Configuration
public class SecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/api/**")
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            )
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/api/public/**").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().denyAll()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults())
            );

        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain browserChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/login", "/assets/**").permitAll()
                .anyRequest().authenticated()
            )
            .formLogin(Customizer.withDefaults());

        return http.build();
    }
}
```

Chain có order nhỏ hơn được xét trước. API chain chỉ nhận /api/**; các request khác tiếp tục đến browser chain. Browser chain không có securityMatcher, nên đóng vai trò fallback cho những request còn lại.

Đừng tạo nhiều chain chỉ để chia file cấu hình. Mỗi chain làm tăng độ phức tạp về thứ tự, matcher và filter behavior. Chỉ tách khi authentication mechanism hoặc security policy thực sự khác nhau.

## 6. @Order và thứ tự chọn chain

FilterChainProxy chọn chain đầu tiên có matcher khớp request. Nó không kết hợp tất cả các chain khớp cùng một request.

Ví dụ nếu chain đầu tiên có matcher /api/**, request /api/orders được xử lý bởi chain đó; chain thứ hai không tiếp tục bổ sung rule. Vì vậy:

1. Đặt chain có phạm vi hẹp hoặc yêu cầu đặc biệt trước.
2. Đặt chain catch-all/fallback cuối cùng.
3. Không để hai chain cùng khớp một URL nếu không có lý do rõ ràng.
4. Kiểm thử request đại diện cho từng chain.
5. Kiểm tra cả URL không khớp chain nào.

Nếu hai bean không có thứ tự rõ ràng và cùng match, behavior có thể không như mong đợi. Dùng @Order hoặc Ordered để khai báo thứ tự một cách tường minh.

## 7. Không nhầm permitAll với bỏ qua security filters

Trong cấu hình cũ, ứng dụng thường dùng:

```java
@Override
public void configure(WebSecurity web) {
    web.ignoring().antMatchers("/assets/**");
}
```

Tương ứng mới là WebSecurityCustomizer:

```java
@Bean
WebSecurityCustomizer webSecurityCustomizer() {
    return web -> web.ignoring().requestMatchers("/assets/**");
}
```

Tuy nhiên, với phần lớn endpoint public, nên dùng permitAll() trong chain:

```java
http.authorizeHttpRequests(authorize -> authorize
    .requestMatchers("/assets/**", "/health").permitAll()
    .anyRequest().authenticated()
);
```

Khác biệt:

- permitAll() vẫn đi qua security filter chain. Security headers, CORS, security context và các filter khác có thể hoạt động theo cấu hình.
- web.ignoring() bỏ qua Spring Security filter chain cho request khớp matcher.

Chỉ dùng ignoring khi thực sự muốn bỏ toàn bộ security filters, thường dành cho static resources rất đơn giản. Không dùng ignoring cho health endpoint, API public hoặc route cần security headers/CORS nếu không cân nhắc hậu quả.

## 8. Chuyển cấu hình Resource Server JWT

Một Resource Server JWT có thể được cấu hình trực tiếp trong chain:

```java
@Bean
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(authorize -> authorize
            .requestMatchers("/api/orders/**")
                .hasAuthority("SCOPE_orders.read")
            .anyRequest().authenticated()
        )
        .oauth2ResourceServer(oauth2 -> oauth2
            .jwt(Customizer.withDefaults())
        )
        .build();
}
```

Spring Boot có thể cấu hình decoder từ issuer URI:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.com/realms/shop
```

Nếu ứng dụng cần custom JwtDecoder, có thể khai báo bean:

```java
@Bean
JwtDecoder jwtDecoder() {
    return JwtDecoders.fromIssuerLocation(
        "https://identity.example.com/realms/shop");
}
```

Khi tự cấu hình decoder, hãy giữ các validator cần thiết như issuer, timestamp và audience. Việc chuyển sang SecurityFilterChain không tự thêm audience validation nếu trước đó ứng dụng chưa cấu hình.

## 9. Chuyển cấu hình Opaque Token

Với opaque token, cấu hình chain dùng opaqueToken:

```java
@Bean
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(authorize -> authorize
            .requestMatchers("/api/orders/**")
                .hasAuthority("SCOPE_orders.read")
            .anyRequest().authenticated()
        )
        .oauth2ResourceServer(oauth2 -> oauth2
            .opaqueToken(Customizer.withDefaults())
        )
        .build();
}
```

Cấu hình endpoint introspection:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://identity.example.com/oauth2/introspect
          client-id: orders-resource-server
          client-secret: INTROSPECTION_CLIENT_SECRET_FROM_SECRET_MANAGER
```

Khi migrate, giữ nguyên introspection URI, client authentication, custom OpaqueTokenIntrospector và metadata validation. Nếu trước đó có bean introspector riêng, xác nhận chain mới vẫn dùng đúng bean đó.

## 10. Stateless API và session policy

Resource Server API thường dùng Bearer token trong Authorization header và không cần lưu HTTP session:

```java
.sessionManagement(session -> session
    .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
)
```

STATELESS yêu cầu Spring Security không dùng session để lưu SecurityContext cho request tiếp theo. Nó không có nghĩa mọi thứ trong ứng dụng đều không có state; business session, database và cache vẫn có thể tồn tại.

Các lựa chọn chính:

| Policy | Hành vi |
| --- | --- |
| ALWAYS | Luôn tạo session |
| IF_REQUIRED | Tạo session khi cần |
| NEVER | Không tạo session mới, nhưng có thể dùng session sẵn có |
| STATELESS | Không tạo hoặc dùng session để lấy SecurityContext |

Không áp dụng STATELESS cho browser form login nếu ứng dụng cần session để duy trì đăng nhập. Với nhiều chain, hãy đặt session policy riêng cho từng chain.

## 11. CSRF: không tắt chỉ vì ứng dụng có REST API

Spring Security bật CSRF protection mặc định cho các unsafe HTTP methods. Một API dùng Bearer token được gửi tường minh trong Authorization header, không tự động gửi như cookie, có thể không cần CSRF protection trên chain API.

Ví dụ cho API thuần Bearer token:

```java
http
    .securityMatcher("/api/**")
    .csrf(csrf -> csrf.disable())
    .sessionManagement(session -> session
        .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
    )
    .oauth2ResourceServer(oauth2 -> oauth2
        .jwt(Customizer.withDefaults())
    );
```

Chỉ disable CSRF khi chain thực sự không dựa vào credential tự động được browser gửi kèm như session cookie hoặc authentication cookie. Nếu API dùng cookie authentication, browser session hoặc mixed authentication, cần giữ CSRF protection và cấu hình token repository/handler phù hợp.

Không tắt CSRF toàn ứng dụng chỉ vì một phần route là API. Với nhiều chain, có thể giữ CSRF cho browser chain và disable có chủ đích ở stateless bearer API chain.

## 12. CORS trong cấu hình mới

CORS cần được xử lý trước authorization cho preflight requests. Có thể bật CORS và inject CorsConfigurationSource:

```java
@Bean
CorsConfigurationSource corsConfigurationSource() {
    CorsConfiguration configuration = new CorsConfiguration();
    configuration.setAllowedOrigins(List.of("https://app.example.com"));
    configuration.setAllowedMethods(
        List.of("GET", "POST", "PUT", "DELETE", "OPTIONS"));
    configuration.setAllowedHeaders(
        List.of("Authorization", "Content-Type"));
    configuration.setAllowCredentials(false);

    UrlBasedCorsConfigurationSource source =
        new UrlBasedCorsConfigurationSource();
    source.registerCorsConfiguration("/api/**", configuration);
    return source;
}

@Bean
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/**")
        .cors(Customizer.withDefaults())
        .authorizeHttpRequests(authorize -> authorize
            .anyRequest().authenticated())
        .oauth2ResourceServer(oauth2 -> oauth2.jwt(Customizer.withDefaults()))
        .build();
}
```

Không dùng wildcard origin với credentials. Chỉ cho phép origins, methods và headers cần thiết. CORS không phải authorization: nó điều khiển browser cross-origin access, không thay thế token validation hoặc scope checks.

## 13. Chuyển custom authentication entry point và access denied handler

Cấu hình cũ có thể khai báo handler bằng DSL. Cấu hình mới dùng lambda:

```java
http
    .exceptionHandling(exceptions -> exceptions
        .authenticationEntryPoint(customAuthenticationEntryPoint)
        .accessDeniedHandler(customAccessDeniedHandler)
    );
```

Hai handler phục vụ hai tình huống:

- AuthenticationEntryPoint: request chưa được xác thực hoặc Bearer credential không hợp lệ.
- AccessDeniedHandler: caller đã xác thực nhưng không có quyền.

Với Resource Server, Bearer token failure handler còn có thể tạo WWW-Authenticate challenge đúng chuẩn. Nếu thay entry point mặc định, giữ behavior cần thiết cho OAuth Bearer error response và không để lộ chi tiết nội bộ của IdP.

Không dùng cùng một handler để biến mọi lỗi thành 403 hoặc mọi lỗi thành 401. Status và challenge cần phản ánh đúng authentication/authorization semantics của API.

## 14. Chuyển custom filter

Nếu adapter cũ thêm filter:

```java
http.addFilterBefore(
    customFilter,
    UsernamePasswordAuthenticationFilter.class);
```

Cấu hình này vẫn có thể dùng trong bean SecurityFilterChain, nhưng cần xem lại vị trí filter trong chain mới. Với Resource Server, không thêm custom Bearer token parser nếu Spring Security đã xử lý BearerTokenAuthenticationFilter, trừ khi có một yêu cầu protocol cụ thể.

Nếu filter dùng request attributes, MDC hoặc SecurityContext, bảo đảm cleanup trong finally và xử lý async dispatch đúng cách. Đừng đăng ký cùng một filter vừa là servlet container filter vừa được thêm vào Spring Security chain nếu điều đó khiến filter chạy hai lần.

Nếu filter cần chạy trước/sau một security filter cụ thể, dùng addFilterBefore, addFilterAfter hoặc addFilterAt theo contract và test thứ tự thực tế.

## 15. Chuyển configure(WebSecurity) sang WebSecurityCustomizer

Cấu hình cũ:

```java
@Override
public void configure(WebSecurity web) {
    web.ignoring().antMatchers("/assets/**", "/favicon.ico");
}
```

Cấu hình bean:

```java
@Bean
WebSecurityCustomizer webSecurityCustomizer() {
    return web -> web.ignoring()
        .requestMatchers("/assets/**", "/favicon.ico");
}
```

Nhắc lại: ignoring loại request khỏi Spring Security filter chain. Với public API hoặc endpoint cần security headers, dùng permitAll trong chain thường an toàn và nhất quán hơn.

Không chuyển nguyên xi mọi web.ignoring() từ cấu hình cũ mà không kiểm tra lý do ban đầu. Có thể một số route trước kia bị ignore chỉ để tránh lỗi static resource, nhưng hiện nay có thể xử lý bằng permitAll().

## 16. Chuyển configure(AuthenticationManagerBuilder) và AuthenticationManager

Adapter cũ có thể cấu hình user details hoặc authentication provider:

```java
@Override
protected void configure(AuthenticationManagerBuilder auth) throws Exception {
    auth.userDetailsService(userDetailsService)
        .passwordEncoder(passwordEncoder);
}
```

Trong mô hình bean, khai báo các thành phần:

```java
@Bean
PasswordEncoder passwordEncoder() {
    return PasswordEncoderFactories.createDelegatingPasswordEncoder();
}

@Bean
DaoAuthenticationProvider daoAuthenticationProvider(
        UserDetailsService userDetailsService,
        PasswordEncoder passwordEncoder) {

    DaoAuthenticationProvider provider = new DaoAuthenticationProvider();
    provider.setUserDetailsService(userDetailsService);
    provider.setPasswordEncoder(passwordEncoder);
    return provider;
}
```

Sau đó cấu hình provider trong chain browser nếu cần form login:

```java
http.authenticationProvider(daoAuthenticationProvider);
```

Nếu cần expose AuthenticationManager:

```java
@Bean
AuthenticationManager authenticationManager(
        AuthenticationConfiguration configuration) throws Exception {
    return configuration.getAuthenticationManager();
}
```

Đối với OAuth2 Resource Server, thường không cần cấu hình UserDetailsService hoặc password encoder chỉ để xác minh access token. JWT dùng decoder/validators; opaque token dùng introspector. Chỉ giữ DaoAuthenticationProvider nếu ứng dụng còn hỗ trợ login bằng username/password hoặc một authentication flow riêng.

## 17. Chuyển @EnableGlobalMethodSecurity

Nếu cấu hình cũ dùng:

```java
@EnableGlobalMethodSecurity(
    prePostEnabled = true,
    securedEnabled = true
)
```

Spring Security 6 dùng:

```java
@EnableMethodSecurity(
    securedEnabled = true,
    jsr250Enabled = true
)
```

@EnableMethodSecurity bật pre/post annotations theo mặc định. securedEnabled bật @Secured; jsr250Enabled bật JSR-250 annotations như @RolesAllowed.

Method security là lớp độc lập với request authorization trong SecurityFilterChain. Một controller có thể được phép đi qua filter chain nhưng service method vẫn bị @PreAuthorize từ chối. Khi migrate, giữ cả hai lớp policy nếu ứng dụng đang dùng chúng.

## 18. Matcher semantics và path matching sau migration

requestMatchers có thể chọn matcher phù hợp với môi trường MVC và Spring Security. Không giả định mọi path expression có semantics giống hệt AntPathRequestMatcher cũ trong mọi ứng dụng.

Kiểm tra:
- Context path và servlet path.
- Path variable và wildcard patterns.
- Trailing slash behavior.
- HTTP method constraints.
- Dispatcher types và error/forward dispatch.
- Nhiều servlet mappings nếu ứng dụng có chúng.

Ví dụ rule có method:

```java
.authorizeHttpRequests(authorize -> authorize
    .requestMatchers(HttpMethod.GET, "/api/orders/**")
        .hasAuthority("SCOPE_orders.read")
    .requestMatchers(HttpMethod.POST, "/api/orders/**")
        .hasAuthority("SCOPE_orders.write")
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .anyRequest().denyAll()
)
```

Nếu cần semantics matcher chính xác hoặc path handling không phụ thuộc MVC auto-selection, có thể khai báo RequestMatcher tường minh. Quan trọng là test URL thực tế, không chỉ đọc pattern bằng mắt.

## 19. anyRequest() và deny-by-default

Một API nhạy cảm nên kết thúc rule bằng policy rõ ràng:

```java
.authorizeHttpRequests(authorize -> authorize
    .requestMatchers("/api/public/**").permitAll()
    .requestMatchers(HttpMethod.GET, "/api/orders/**")
        .hasAuthority("SCOPE_orders.read")
    .requestMatchers(HttpMethod.POST, "/api/orders/**")
        .hasAuthority("SCOPE_orders.write")
    .anyRequest().denyAll()
)
```

anyRequest().authenticated() chỉ yêu cầu caller đã xác thực, không giới hạn operation theo scope. Nếu endpoint có quyền khác nhau, khai báo scope/role cụ thể trước catch-all.

Khi migrate, đừng vô tình thay một rule cũ denyAll() bằng authenticated() chỉ để tránh lỗi truy cập. Giữ policy least privilege và thêm test cho route không được khai báo.

## 20. Security headers và HTTPS

Nếu cấu hình cũ có custom headers, chuyển sang lambda DSL:

```java
http.headers(headers -> headers
    .frameOptions(frame -> frame.deny())
    .contentTypeOptions(Customizer.withDefaults())
    .httpStrictTransportSecurity(hsts -> hsts
        .includeSubDomains(true)
        .maxAgeInSeconds(31536000)
    )
);
```

Không bật HSTS với includeSubDomains nếu mọi subdomain chưa sẵn sàng HTTPS. Một reverse proxy terminate TLS có thể yêu cầu cấu hình forwarded headers/trusted proxy chính xác để Spring hiểu scheme. Không tin X-Forwarded-Proto từ client tùy ý.

Migration cần giữ các security headers và HTTPS redirect behavior đã được policy phê duyệt. Đừng giả định chúng tự được giữ chỉ vì SecurityFilterChain mới đã build thành công.

## 21. CSRF, CORS và session khi có nhiều chain

Một thiết kế điển hình:

| Chain | Authentication | Session | CSRF | CORS |
| --- | --- | --- | --- | --- |
| /api/** | Bearer JWT/opaque | Stateless | Có thể disable nếu không dùng cookie credential | Theo API origins |
| Browser routes | Form login/session | IF_REQUIRED | Enabled | Theo browser app |
| Internal routes | Workload/mTLS hoặc token riêng | Theo contract | Theo cơ chế credential | Thường giới hạn chặt |

Không dùng một cấu hình global rồi vô tình áp dụng browser session hoặc CSRF policy sai cho API. Với nhiều chain, mỗi chain có matcher và policy riêng; hãy kiểm tra chain nào thực sự xử lý route.

## 22. Thứ tự filter và thứ tự bean là hai thứ khác nhau

@Order trên SecurityFilterChain bean quyết định thứ tự chọn chain. Các lệnh addFilterBefore/addFilterAfter quyết định vị trí custom filter bên trong một chain.

Không nhầm:
- Chain order: API chain được xét trước browser chain.
- Filter order: custom correlation filter đứng trước hoặc sau một security filter cụ thể.
- Authorization rule order: matcher rule cụ thể được xét trước rule catch-all.

Ba tầng thứ tự này độc lập và đều có thể làm thay đổi behavior khi migration.

## 23. Testing SecurityFilterChain với MockMvc

Dùng MockMvc để xác nhận HTTP behavior qua filter chain:

```java
@SpringBootTest
@AutoConfigureMockMvc
class ApiSecurityIntegrationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicEndpointIsAccessibleWithoutToken() throws Exception {
        mvc.perform(get("/api/public/status"))
            .andExpect(status().isOk());
    }

    @Test
    void protectedEndpointRejectsMissingToken() throws Exception {
        mvc.perform(get("/api/orders"))
            .andExpect(status().isUnauthorized());
    }
}
```

Đây là ví dụ khung; cần endpoint thật hoặc controller fixture trong test context. Không tắt filters khi mục tiêu là kiểm tra SecurityFilterChain. Một controller slice có thể cần import security configuration và resource server dependencies tương ứng.

## 24. Test JWT authorities và authorization rules

Spring Security Test cung cấp jwt() request post-processor:

```java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;

@Test
void readerCanReadOrders() throws Exception {
    mvc.perform(get("/api/orders")
            .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_orders.read"))))
        .andExpect(status().isOk());
}

@Test
void readerCannotCreateOrders() throws Exception {
    mvc.perform(post("/api/orders")
            .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_orders.read")))
            .contentType(MediaType.APPLICATION_JSON)
            .content("{\"item\":\"book\"}"))
        .andExpect(status().isForbidden());
}
```

jwt() tạo Authentication giả lập cho test; nó không xác minh chữ ký, issuer, audience hoặc JWK retrieval. Dùng nó để test request authorization và mapping authorities. Thêm integration test riêng với signed JWT hoặc decoder fixture để xác minh token validation thực tế.

## 25. Test Opaque Token chain

Với opaque token, opaqueToken() post-processor có thể tạo authentication giả lập cho request test:

```java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.opaqueToken;

@Test
void opaqueTokenWithReadScopeCanReadOrders() throws Exception {
    mvc.perform(get("/api/orders")
            .with(opaqueToken().authorities(
                new SimpleGrantedAuthority("SCOPE_orders.read"))))
        .andExpect(status().isOk());
}
```

Post-processor này không gọi introspection endpoint. Nếu cần kiểm thử integration của introspection, hãy cấu hình endpoint giả lập và gửi Bearer token thực qua filter chain. Đừng coi test dùng opaqueToken() là bằng chứng client credentials/introspection URI hoạt động.

## 26. Test nhiều chain và matcher precedence

Nếu ứng dụng có API và browser chain, hãy test từng nhóm URL:

| Request | Chain mong đợi | Hành vi |
| --- | --- | --- |
| /api/orders | API chain | Bearer token, scope orders |
| /api/public/status | API chain | Public theo API rule |
| /login | Browser fallback | Login page |
| /admin/users | Browser fallback | Session/role policy |
| /unknown | Fallback hoặc deny | Theo default policy |

Nên có test route không khớp chain đầu nhưng phải khớp fallback chain. Nếu không, một route có thể vô tình không đi qua chain nào.

Trong test, có thể inject bean chain hoặc dùng request behavior để xác nhận chain được chọn. Tránh chỉ assert @Order tồn tại; điều cần chứng minh là request đi qua đúng authentication mechanism và authorization rules.

## 27. Migration custom filter, handler và matcher theo từng bước

Quy trình an toàn:

1. Liệt kê mọi method override trong adapter cũ.
2. Tách authorization rules, session, CSRF, CORS, headers, exception handling và custom filters.
3. Xác định route nào thuộc API, browser hoặc internal chain.
4. Tạo SecurityFilterChain bean đầu tiên giữ behavior hiện tại.
5. Chuyển matcher sang requestMatchers và kiểm tra semantics.
6. Chuyển web.ignoring() sang permitAll() nếu không cần bỏ filter chain.
7. Chuyển AuthenticationProvider/UserDetailsService thành beans nếu còn dùng.
8. Chuyển method security annotation enablement.
9. Thêm test positive và negative cho từng route.
10. So sánh behavior trước/sau trên môi trường test hoặc staging.

Không thực hiện đồng thời nhiều thay đổi policy và framework migration nếu khó xác định nguồn gốc regression.

## 28. Ví dụ migration đầy đủ cho API Resource Server

Cấu hình hoàn chỉnh cho một API thuần JWT Bearer:

```java
@Configuration
@EnableWebSecurity
public class ApiSecurityConfiguration {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/api/**")
            .cors(Customizer.withDefaults())
            .csrf(csrf -> csrf.disable())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            )
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/api/public/**").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().denyAll()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults())
            )
            .build();
    }
}
```

Cấu hình này giả định:
- API dùng Bearer token trong Authorization header.
- Không dùng cookie/session authentication trên /api/**.
- CSRF được disable chỉ cho chain stateless này.
- CORS source đã được khai báo.
- Issuer/JWT decoder được cấu hình ở property hoặc bean khác.
- Mỗi operation có scope riêng.
- Route không được khai báo bị deny.

Nếu các giả định không đúng, cần điều chỉnh policy thay vì sao chép nguyên ví dụ.

## 29. @EnableWebSecurity có bắt buộc không?

Trong ứng dụng Spring Boot, auto-configuration thường tự đăng ký web security khi dependency hiện diện. @EnableWebSecurity có thể được dùng để bật cấu hình web security rõ ràng, nhưng không phải lúc nào cũng cần thêm vào mọi configuration class.

Điều quan trọng là bean SecurityFilterChain được Spring phát hiện và đăng ký. Nếu ứng dụng có nhiều security configuration, tránh thêm annotation hoặc import lặp lại gây khó hiểu. Kiểm tra auto-configuration conditions và context thực tế khi có xung đột bean.

## 30. Các lỗi migration thường gặp

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Giữ WebSecurityConfigurerAdapter trên Spring Security 6 | Không compile | Chuyển sang SecurityFilterChain bean |
| Dùng antMatchers/authorizeRequests | API đã bị loại bỏ | Dùng requestMatchers/authorizeHttpRequests |
| Nhầm securityMatcher với requestMatchers | Chain hoặc rule áp dụng sai phạm vi | Tách chọn chain và authorization |
| Thiếu @Order cho nhiều chain | Request có thể vào chain không mong muốn | Khai báo thứ tự tường minh |
| Không có fallback chain | Một số route không qua security filters | Thêm chain catch-all phù hợp |
| Dùng web.ignoring cho API public | Bỏ qua headers/CORS/security filters | Dùng permitAll nếu vẫn cần chain |
| Disable CSRF toàn ứng dụng | Browser/cookie flow dễ bị CSRF | Chỉ disable trên stateless bearer chain |
| Dùng STATELESS cho form login | Session login không hoạt động như mong muốn | Session policy riêng từng chain |
| Chỉ authenticated cho mọi API | Token có thể thiếu scope nghiệp vụ | Khai báo authority theo method/resource |
| Mất custom JwtDecoder/introspector | Mất issuer/audience/metadata policy | Giữ và test bean validator/delegate |
| Custom filter chạy hai lần | Duplicate work hoặc context leak | Kiểm tra servlet registration và chain registration |
| Test với jwt() rồi kết luận decoder tốt | Bỏ qua chữ ký/JWK validation | Thêm signed-token integration test |

## 31. Checklist trước và sau khi nâng cấp

Trước migration:
- Ghi lại mọi configure(...) override và DSL rule.
- Liệt kê route public, protected, admin và internal.
- Ghi lại authentication mechanisms và custom providers.
- Ghi lại session, CSRF, CORS, headers và custom filters.
- Xác định JWT/opaque token validators và authority converters.
- Ghi lại exception entry point/access denied behavior.

Sau migration:
- Không còn dependency vào WebSecurityConfigurerAdapter.
- Mỗi SecurityFilterChain có matcher và order rõ.
- Các rule dùng authorizeHttpRequests/requestMatchers.
- permitAll và ignoring được chọn có chủ đích.
- CSRF/session policy đúng từng chain.
- Resource Server vẫn kiểm tra issuer, signature, expiry, audience và scope.
- Custom filter/handler được đăng ký đúng một lần.
- Method security được bật nếu ứng dụng dùng annotations.
- MockMvc tests bao phủ success, 401, 403 và route fallback.
- JWT/opaque integration tests vẫn xác minh decoder/introspection thật.
- Quan sát log/metric để phát hiện tỷ lệ 401/403/5xx bất thường sau deploy.

## 32. Tài liệu tham khảo

- [Spring Security 6.5 — Java Configuration](https://docs.spring.io/spring-security/reference/6.5/servlet/configuration/java.html): khai báo SecurityFilterChain và nhiều chain.
- [Spring Security 6.5 — Lambda DSL](https://docs.spring.io/spring-security/reference/6.5/migration-7/configuration.html): lambda DSL và cách cấu hình hiện đại.
- [Spring Security 6.5 — Authorization](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html): authorizeHttpRequests, requestMatchers và authorization rules.
- [Spring Security 6.5 — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/jwt.html): cấu hình JWT Resource Server.
- [Spring Security 6.5 — Opaque Token](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/opaque-token.html): cấu hình opaque token introspection.
- [Spring Security 6.5 — CSRF](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html): CSRF protection và cấu hình.
- [Spring Security 6.5 — CORS](https://docs.spring.io/spring-security/reference/6.5/servlet/integrations/cors.html): tích hợp CORS trong filter chain.
- [Spring Security 5.7 Release Notes](https://spring.io/blog/2022/02/21/spring-security-without-the-websecurityconfigureradapter): lý do và hướng thay thế adapter cũ.

## 33. Kết luận

Migration sang SecurityFilterChain chuyển cấu hình bảo mật từ mô hình kế thừa adapter sang các bean khai báo rõ ràng. Với một chain, tạo bean nhận HttpSecurity, chuyển DSL sang authorizeHttpRequests, bật JWT hoặc opaque token và gọi build(). Với nhiều chain, dùng securityMatcher để chọn phạm vi chain và @Order để kiểm soát chain nào được xét trước; dùng requestMatchers bên trong để quyết định quyền.

Khi nâng cấp, giữ nguyên security behavior có chủ đích: CSRF, CORS, session policy, exception handling, custom filters, token validators và method security. Đừng thay mọi rule thành authenticated, đừng bỏ filter chain cho route public nếu vẫn cần security headers, và đừng disable CSRF cho browser/cookie flows. Kiểm thử bằng MockMvc và token fixtures để xác nhận đúng chain, đúng authority và đúng HTTP response.

**Điểm cốt lõi:** *Một migration hoàn chỉnh không chỉ làm code biên dịch với Spring Security 6; nó phải giữ đúng chain được chọn, credential được xác minh và authorization policy được thực thi cho từng route.*
