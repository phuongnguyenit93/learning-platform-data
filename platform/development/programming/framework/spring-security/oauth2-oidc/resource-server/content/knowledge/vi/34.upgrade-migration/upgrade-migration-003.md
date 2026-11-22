# Lambda DSL, phương thức bị thay thế và thay đổi theo dòng phiên bản

## 1. Vì sao Spring Security thay đổi DSL cấu hình?

Spring Security đã chuyển dần từ cách cấu hình theo chuỗi gọi phương thức sang **Lambda DSL**. Thay đổi này làm cấu hình dễ đọc hơn, thể hiện rõ ranh giới của từng configurer và chuẩn bị API cho các phiên bản mới.

Cấu hình cũ thường dùng chuỗi `.and()`:

~~~java
http
    .authorizeRequests()
        .antMatchers("/api/public/**").permitAll()
        .anyRequest().authenticated()
    .and()
    .oauth2ResourceServer()
        .jwt();
~~~

Cấu hình hiện đại truyền lambda vào từng configurer:

~~~java
http
    .authorizeHttpRequests(authorize -> authorize
        .requestMatchers("/api/public/**").permitAll()
        .anyRequest().authenticated()
    )
    .oauth2ResourceServer(oauth2 -> oauth2
        .jwt(Customizer.withDefaults())
    );
~~~

Lambda DSL không chỉ là thay đổi cú pháp. Nó đi cùng với các thay đổi về cách khai báo security configuration bằng bean, cách chọn `SecurityFilterChain`, authorization API, request matchers, JWT/opaque token Resource Server, method security và Java/Jakarta baseline.

Khi migration, cần xác định chính xác phiên bản Spring Security và Spring Boot đang dùng. Một ví dụ hợp lệ ở Spring Security 5.x có thể đã deprecated hoặc bị xóa ở 6.x/7.x.

## 2. Dòng thời gian các thay đổi chính

Bảng dưới đây tóm tắt các mốc quan trọng khi chuyển từ cấu hình cũ sang cấu hình hiện đại. Hãy đối chiếu với release notes và API reference đúng minor version của dự án trước khi thay đổi.

| Dòng phiên bản | Thay đổi đáng chú ý | Hướng migration |
|---|---|---|
| Spring Security 5.2 | Lambda DSL được giới thiệu | Có thể bắt đầu dùng lambda cho các configurer |
| Spring Security 5.5+ | `authorizeHttpRequests` và AuthorizationManager trở thành hướng cấu hình mới | Chuyển dần từ `authorizeRequests` |
| Spring Security 5.7 | `WebSecurityConfigurerAdapter` bị deprecated | Khai báo `SecurityFilterChain` bean |
| Spring Security 5.8 | Có API chuyển tiếp để chuẩn bị cho 6.x, gồm `requestMatchers`/`securityMatcher` | Dùng API mới trước khi nâng major |
| Spring Security 6.0 | `WebSecurityConfigurerAdapter` và matcher cũ như `antMatchers`, `mvcMatchers`, `regexMatchers` bị loại bỏ; namespace Jakarta được sử dụng | Chuyển sang bean configuration và matcher mới |
| Spring Security 6.1 | Các phương thức configurer không truyền lambda bị deprecated để chuẩn bị cho 7.0 | Dùng lambda hoặc `Customizer.withDefaults()` |
| Spring Security 7.x | Lambda DSL là cách cấu hình bắt buộc; API cũ đã deprecated và được lên kế hoạch loại bỏ không còn dùng được | Loại bỏ no-arg configurer calls và legacy DSL |

Một số thay đổi được đưa vào ở minor release rồi mới bị loại bỏ ở major release tiếp theo. Vì vậy, không nên suy ra rằng mọi API cũ bị xóa ngay ở 6.0 hoặc mọi ứng dụng 6.x đều có cùng cảnh báo.

### 2.1. Spring Security 5.2: Lambda DSL

Lambda DSL xuất hiện từ Spring Security 5.2. Trong các bản 5.x, code cũ vẫn có thể hoạt động, nhưng lambda giúp cấu hình thể hiện rõ phạm vi của từng nhóm thiết lập.

~~~java
http
    .authorizeRequests(authorize -> authorize
        .antMatchers("/health").permitAll()
        .anyRequest().authenticated()
    )
    .httpBasic(Customizer.withDefaults());
~~~

Ở giai đoạn này, tên authorization DSL và matcher vẫn có thể là API cũ. Điểm mới là cách truyền lambda. Khi chuẩn bị migration xa hơn, nên chuyển cả DSL/matcher sang API hiện đại nếu version hiện tại hỗ trợ.

### 2.2. Spring Security 5.7: thay WebSecurityConfigurerAdapter

`WebSecurityConfigurerAdapter` được deprecated trong Spring Security 5.7. Ứng dụng có thể tiếp tục chạy trong giai đoạn chuyển tiếp, nhưng nên chuyển sang các bean tường minh trước khi lên 6.x.

### 2.3. Spring Security 5.8: bản chuyển tiếp hữu ích

Spring Security 5.8 cung cấp các API mới để giảm số thay đổi cần thực hiện cùng lúc khi nâng lên 6.0. Đây là một điểm dừng migration hữu ích:

- Chuyển từ `antMatchers`/`mvcMatchers`/`regexMatchers` sang `requestMatchers`.
- Chuyển matcher chọn filter chain sang `securityMatcher`.
- Chuyển khỏi `WebSecurityConfigurerAdapter`.
- Cập nhật cấu hình theo Lambda DSL.

Nếu ứng dụng có thể nâng lên bản 5.8 tương thích trước, hãy giải quyết warning và test trên đó trước khi thay đổi Spring Boot/Spring Security major version.

### 2.4. Spring Security 6.x và 7.x

Spring Security 6 yêu cầu nền tảng Java/Jakarta mới hơn, đồng thời loại bỏ một số API đã deprecated từ 5.x. Spring Security 6.1 tiếp tục đánh dấu các no-arg configurer methods để loại bỏ trong 7.0.

Với Spring Security 7, hãy viết cấu hình bằng Lambda DSL ngay từ đầu. Tránh gọi các phương thức kiểu `http.csrf()`, `http.oauth2ResourceServer()` hoặc `http.authorizeHttpRequests()` không truyền lambda nếu API version đã loại bỏ các overload đó.

## 3. Hiểu cấu trúc Lambda DSL

### 3.1. Mỗi lambda cấu hình một configurer

~~~java
http
    .csrf(csrf -> csrf.disable())
    .cors(cors -> cors.configurationSource(corsConfigurationSource))
    .sessionManagement(session -> session
        .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
    )
    .authorizeHttpRequests(authorize -> authorize
        .requestMatchers("/api/public/**").permitAll()
        .anyRequest().authenticated()
    )
    .oauth2ResourceServer(oauth2 -> oauth2
        .jwt(Customizer.withDefaults())
    );
~~~

Các lambda có ý nghĩa riêng:

- `csrf` cấu hình CSRF protection.
- `cors` cấu hình CORS.
- `session` cấu hình session policy.
- `authorize` cấu hình authorization rules.
- `oauth2` cấu hình OAuth 2.0 Resource Server.
- `jwt` cấu hình JWT decoder/converter trong Resource Server.

Đọc code theo từng lambda giúp thấy rõ configurer nào đang được thay đổi.

### 3.2. Không cần .and() để quay lại HttpSecurity

Với DSL cũ, `.and()` thường được dùng để thoát khỏi configurer hiện tại và quay lại `HttpSecurity`:

~~~java
http
    .authorizeRequests()
        .anyRequest().authenticated()
    .and()
    .httpBasic();
~~~

Với Lambda DSL, configurer được đóng khi lambda kết thúc:

~~~java
http
    .authorizeHttpRequests(authorize -> authorize
        .anyRequest().authenticated()
    )
    .httpBasic(Customizer.withDefaults());
~~~

Không thêm `.and()` vào cuối lambda. Cũng không cần gọi `and()` để chuyển từ cấu hình authorization sang Resource Server.

### 3.3. Customizer.withDefaults() và lambda rỗng

Khi chỉ muốn bật configurer với defaults:

~~~java
.oauth2ResourceServer(oauth2 -> oauth2
    .jwt(Customizer.withDefaults())
)
~~~

Có thể dùng import:

~~~java
import org.springframework.security.config.Customizer;
~~~

Một số API cho phép lambda rỗng tương đương:

~~~java
.httpBasic(Customizer.withDefaults())
~~~

Không phải mọi configurer đều có cùng overload hoặc cùng default behavior. Dùng API reference của version đang chạy thay vì suy luận từ một configurer khác.

### 3.4. Tách cấu hình thành method khi lambda quá dài

Lambda DSL không yêu cầu nhồi toàn bộ cấu hình vào một method. Có thể tách logic theo chức năng:

~~~java
@Bean
SecurityFilterChain apiSecurity(
        HttpSecurity http,
        JwtDecoder jwtDecoder) throws Exception {

    configureApiAuthorization(http);
    configureResourceServer(http, jwtDecoder);

    return http.build();
}

private void configureApiAuthorization(HttpSecurity http)
        throws Exception {

    http.authorizeHttpRequests(authorize -> authorize
        .requestMatchers("/api/public/**").permitAll()
        .requestMatchers("/api/orders/**")
            .hasAuthority("SCOPE_orders.read")
        .anyRequest().authenticated()
    );
}

private void configureResourceServer(
        HttpSecurity http,
        JwtDecoder jwtDecoder) throws Exception {

    http.oauth2ResourceServer(oauth2 -> oauth2
        .jwt(jwt -> jwt.decoder(jwtDecoder))
    );
}
~~~

Ví dụ chỉ minh họa cách phân tách; trong dự án, cân nhắc cấu trúc để không gọi cấu hình trùng lặp hoặc làm mất thứ tự matcher.

## 4. Thay WebSecurityConfigurerAdapter bằng SecurityFilterChain

### 4.1. Cấu hình cũ

Một cấu hình Servlet Resource Server có thể từng được viết:

~~~java
@Configuration
@EnableWebSecurity
public class SecurityConfig extends WebSecurityConfigurerAdapter {

    @Override
    protected void configure(HttpSecurity http) throws Exception {
        http
            .authorizeRequests()
                .antMatchers("/actuator/health").permitAll()
                .anyRequest().authenticated()
            .and()
            .oauth2ResourceServer()
                .jwt();
    }
}
~~~

Vấn đề khi nâng phiên bản:

- `WebSecurityConfigurerAdapter` bị deprecated rồi bị loại bỏ.
- `authorizeRequests`/`antMatchers` thuộc DSL cũ.
- No-arg configurer methods không còn là hướng được khuyến nghị.
- Cấu hình phụ thuộc inheritance và override method, khó thấy rõ bean nào đang sở hữu chain.

### 4.2. Cấu hình mới bằng bean

Chuyển sang `SecurityFilterChain`:

~~~java
@Configuration
@EnableWebSecurity
public class SecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(
            HttpSecurity http) throws Exception {

        return http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/actuator/health").permitAll()
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults())
            )
            .build();
    }
}
~~~

`HttpSecurity` được Spring cung cấp để tạo chain. Phương thức `build()` trả về `SecurityFilterChain` mà Spring Security đăng ký trong application context.

Không cần kế thừa adapter. Các dependency như `JwtDecoder`, converter, authentication provider hoặc CORS configuration có thể được inject trực tiếp vào bean method.

### 4.3. Cấu hình JWT decoder tường minh

Nếu cần validator riêng:

~~~java
@Bean
SecurityFilterChain apiSecurity(
        HttpSecurity http,
        JwtDecoder jwtDecoder,
        JwtAuthenticationConverter jwtAuthenticationConverter)
        throws Exception {

    return http
        .authorizeHttpRequests(authorize -> authorize
            .requestMatchers("/api/public/**").permitAll()
            .requestMatchers("/api/orders/**")
                .hasAuthority("SCOPE_orders.read")
            .anyRequest().authenticated()
        )
        .oauth2ResourceServer(oauth2 -> oauth2
            .jwt(jwt -> jwt
                .decoder(jwtDecoder)
                .jwtAuthenticationConverter(jwtAuthenticationConverter)
            )
        )
        .build();
}
~~~

Cấu hình này giữ JWT decoder và converter thành dependency riêng, dễ kiểm thử và tái sử dụng. Nếu dùng opaque token, DSL sẽ chuyển sang `opaqueToken(...)` với `OpaqueTokenIntrospector` phù hợp.

### 4.4. Nhiều SecurityFilterChain

Với nhiều loại endpoint, có thể khai báo nhiều chain:

~~~java
@Bean
@Order(1)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(authorize -> authorize
            .anyRequest().authenticated()
        )
        .oauth2ResourceServer(oauth2 -> oauth2
            .jwt(Customizer.withDefaults())
        )
        .build();
}

@Bean
@Order(2)
SecurityFilterChain webChain(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(authorize -> authorize
            .requestMatchers("/assets/**").permitAll()
            .anyRequest().authenticated()
        )
        .formLogin(Customizer.withDefaults())
        .build();
}
~~~

Spring Security chọn chain phù hợp theo thứ tự và matcher. Chain API chỉ áp dụng cho `/api/**`; chain web xử lý phần còn lại.

**`securityMatcher` và `requestMatchers` có vai trò khác nhau:**

- `securityMatcher(...)` chọn toàn bộ `SecurityFilterChain` cho request.
- `requestMatchers(...)` chọn authorization rule bên trong chain đã được chọn.

Dùng nhầm hai API có thể khiến endpoint rơi vào chain không có Resource Server, hoặc khiến rule được viết nhưng không bao giờ được áp dụng.

## 5. Thay các authorization DSL và request matchers cũ

### 5.1. authorizeRequests chuyển sang authorizeHttpRequests

~~~java
http.authorizeRequests()
    .antMatchers("/api/public/**").permitAll()
    .antMatchers(HttpMethod.GET, "/api/orders/**")
        .hasAuthority("SCOPE_orders.read")
    .anyRequest().authenticated();
~~~

Chuyển sang:

~~~java
http.authorizeHttpRequests(authorize -> authorize
    .requestMatchers("/api/public/**").permitAll()
    .requestMatchers(HttpMethod.GET, "/api/orders/**")
        .hasAuthority("SCOPE_orders.read")
    .anyRequest().authenticated()
);
~~~

`authorizeHttpRequests` dùng AuthorizationManager và `AuthorizationFilter`. Đây là authorization model mới, có cách xử lý Authentication khác với legacy `FilterSecurityInterceptor`/`AccessDecisionManager`. Không chỉ đổi tên method rồi giả định custom voter hoặc metadata source cũ tự hoạt động như trước.

### 5.2. antMatchers, mvcMatchers và regexMatchers chuyển sang requestMatchers

~~~java
http.authorizeHttpRequests(authorize -> authorize
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .requestMatchers(HttpMethod.GET, "/api/orders/**")
        .hasAuthority("SCOPE_orders.read")
    .requestMatchers("/legacy/[0-9]+").permitAll()
);
~~~

Overload chuỗi của `requestMatchers` chọn matcher theo môi trường Spring MVC/Spring Security và version; không nên giả định semantics luôn giống hệt `antMatchers`, `mvcMatchers` hoặc regex matcher cũ. Nếu rule phụ thuộc servlet path, path pattern, HTTP method, context path hoặc matcher tùy biến, hãy cấu hình RequestMatcher tường minh và kiểm tra bằng request tests.

### 5.3. securityMatcher và requestMatchers

| API | Tác dụng |
|---|---|
| `http.securityMatcher("/api/**")` | Chọn toàn bộ SecurityFilterChain cho request |
| `authorize.requestMatchers("/api/admin/**")` | Chọn authorization rule bên trong chain |
| `WebSecurityCustomizer.ignoring()` | Bỏ qua Spring Security filter chain |
| `permitAll()` | Vẫn đi qua security chain nhưng không yêu cầu authentication |

Một lỗi migration phổ biến là chuyển `http.antMatcher("/api/**")` thành authorization `requestMatchers("/api/**")`. Hai chỗ này không tương đương. Nếu mục tiêu là chọn filter chain, hãy dùng `securityMatcher`.

### 5.4. Kiểm tra thứ tự matcher

Authorization rules được đánh giá theo thứ tự khai báo. Rule tổng quát đặt trước có thể che rule cụ thể:

~~~java
http.authorizeHttpRequests(authorize -> authorize
    .requestMatchers("/api/**").authenticated()
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .anyRequest().denyAll()
);
~~~

Trong ví dụ trên, request tới `/api/admin/**` đã khớp rule `/api/**` trước khi đến rule ADMIN. Hãy đặt rule cụ thể trước:

~~~java
http.authorizeHttpRequests(authorize -> authorize
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .requestMatchers("/api/**").authenticated()
    .anyRequest().denyAll()
);
~~~

Sau migration, test cả các path chồng lấn, method khác nhau, trailing slash, encoded path và context path theo contract API.

### 5.5. Static resources: ignoring hay permitAll?

Cấu hình cũ thường bỏ qua static assets bằng:

~~~java
web.ignoring().antMatchers("/css/**", "/js/**");
~~~

Cấu hình mới có thể dùng:

~~~java
@Bean
WebSecurityCustomizer webSecurityCustomizer() {
    return web -> web.ignoring()
        .requestMatchers("/static/**");
}
~~~

Tuy nhiên, `ignoring` bỏ request khỏi security filter chain. Nếu không có lý do cần bypass, thường nên dùng `permitAll` để request vẫn nhận security headers và các filter behavior cần thiết:

~~~java
http.authorizeHttpRequests(authorize -> authorize
    .requestMatchers("/css/**", "/js/**", "/images/**").permitAll()
    .anyRequest().authenticated()
);
~~~

Chọn theo mục tiêu ứng dụng, không chuyển máy móc mọi lời gọi `web.ignoring()` mà không xác định lý do bypass.

## 6. Các no-arg configurer methods bị deprecated

Từ Spring Security 6.1, nhiều phương thức gọi configurer không truyền lambda bị deprecated để chuẩn bị cho 7.0. Hãy chuyển sang overload nhận lambda hoặc `Customizer.withDefaults()`.

| Cách gọi cũ | Lambda DSL |
|---|---|
| `http.csrf().disable()` | `http.csrf(csrf -> csrf.disable())` |
| `http.cors()` | `http.cors(Customizer.withDefaults())` |
| `http.httpBasic()` | `http.httpBasic(Customizer.withDefaults())` |
| `http.formLogin()` | `http.formLogin(Customizer.withDefaults())` |
| `http.logout()` | `http.logout(Customizer.withDefaults())` |
| `http.sessionManagement().sessionCreationPolicy(...)` | `http.sessionManagement(session -> session.sessionCreationPolicy(...))` |
| `http.exceptionHandling().authenticationEntryPoint(...)` | `http.exceptionHandling(errors -> errors.authenticationEntryPoint(...))` |
| `http.oauth2ResourceServer().jwt()` | `http.oauth2ResourceServer(oauth2 -> oauth2.jwt(Customizer.withDefaults()))` |
| `http.headers().frameOptions().sameOrigin()` | `http.headers(headers -> headers.frameOptions(frame -> frame.sameOrigin()))` |

Ví dụ cấu hình tổng hợp:

~~~java
@Bean
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    return http
        .csrf(csrf -> csrf.disable())
        .cors(Customizer.withDefaults())
        .sessionManagement(session -> session
            .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
        )
        .exceptionHandling(errors -> errors
            .authenticationEntryPoint(new BearerTokenAuthenticationEntryPoint())
            .accessDeniedHandler(new BearerTokenAccessDeniedHandler())
        )
        .authorizeHttpRequests(authorize -> authorize
            .requestMatchers("/actuator/health").permitAll()
            .anyRequest().authenticated()
        )
        .oauth2ResourceServer(oauth2 -> oauth2
            .jwt(Customizer.withDefaults())
        )
        .build();
}
~~~

Ví dụ này dành cho API stateless dùng Bearer token. Chỉ disable CSRF nếu threat model và credential transport cho phép. Nếu ứng dụng còn dùng browser session/cookie authentication, không được tắt CSRF chỉ vì một phần endpoint dùng JWT.

Một số method cụ thể có thể khác theo minor version hoặc configurer. Khi compiler báo deprecated-for-removal, chuyển sang lambda overload được API version hiện tại cung cấp.

## 7. Thay đổi cấu hình Authentication khi bỏ adapter

### 7.1. Cấu hình cũ trong configure(AuthenticationManagerBuilder)

Ứng dụng trước đây thường override:

~~~java
@Override
protected void configure(AuthenticationManagerBuilder auth)
        throws Exception {
    auth
        .userDetailsService(userDetailsService)
        .passwordEncoder(passwordEncoder);
}
~~~

Khi bỏ `WebSecurityConfigurerAdapter`, không còn override method này. Hãy khai báo các dependency authentication thành bean tường minh.

### 7.2. Khai báo UserDetailsService và PasswordEncoder

~~~java
@Bean
UserDetailsService userDetailsService(UserRepository users) {
    return username -> users.findByUsername(username)
        .orElseThrow(() ->
            new UsernameNotFoundException("User not found")
        );
}

@Bean
PasswordEncoder passwordEncoder() {
    return new BCryptPasswordEncoder();
}
~~~

Ví dụ chỉ ra cách tách user lookup và password hashing. Chọn encoder theo chính sách ứng dụng và cấu hình migration/upgrade password phù hợp. Không lưu password thô hoặc dùng encoder yếu để làm test đơn giản.

### 7.3. Khai báo AuthenticationProvider

Nếu cần cấu hình DAO authentication tường minh:

~~~java
@Bean
AuthenticationProvider authenticationProvider(
        UserDetailsService userDetailsService,
        PasswordEncoder passwordEncoder) {

    DaoAuthenticationProvider provider =
        new DaoAuthenticationProvider();

    provider.setUserDetailsService(userDetailsService);
    provider.setPasswordEncoder(passwordEncoder);
    return provider;
}
~~~

Sau đó có thể đăng ký provider trong chain:

~~~java
@Bean
SecurityFilterChain webSecurity(
        HttpSecurity http,
        AuthenticationProvider authenticationProvider)
        throws Exception {

    return http
        .authenticationProvider(authenticationProvider)
        .authorizeHttpRequests(authorize -> authorize
            .anyRequest().authenticated()
        )
        .formLogin(Customizer.withDefaults())
        .build();
}
~~~

Không cần tự tạo một `AuthenticationManagerBuilder` chỉ để thay thế override cũ. Dùng provider bean hoặc cơ chế AuthenticationManager phù hợp với authentication flow thực tế.

### 7.4. Expose AuthenticationManager khi ứng dụng thực sự cần

Nếu controller/service hoặc integration cần inject `AuthenticationManager`, có thể expose từ `AuthenticationConfiguration`:

~~~java
@Bean
AuthenticationManager authenticationManager(
        AuthenticationConfiguration configuration)
        throws Exception {
    return configuration.getAuthenticationManager();
}
~~~

Chỉ expose khi có caller cần. Với Resource Server JWT, Spring Security thường tự cấu hình authentication manager từ `JwtDecoder` và converter; không tạo một `AuthenticationManager` thủ công nếu không có yêu cầu cụ thể.

## 8. Thay đổi trong Method Security

### 8.1. EnableGlobalMethodSecurity chuyển sang EnableMethodSecurity

Cấu hình cũ:

~~~java
@Configuration
@EnableGlobalMethodSecurity(prePostEnabled = true)
public class MethodSecurityConfig {
}
~~~

Cấu hình mới:

~~~java
@Configuration
@EnableMethodSecurity
public class MethodSecurityConfig {
}
~~~

`@EnableMethodSecurity` là annotation hiện đại để bật method authorization. Cần chú ý khác biệt default: `prePostEnabled` của `@EnableMethodSecurity` mặc định là true, trong khi cấu hình cũ thường cần bật `prePostEnabled = true` rõ ràng. Khi migration, khai báo các tùy chọn tường minh để giữ nguyên policy.

Nếu ứng dụng dùng `@Secured` hoặc JSR-250 annotations, bật tương ứng:

~~~java
@EnableMethodSecurity(
    prePostEnabled = true,
    securedEnabled = true,
    jsr250Enabled = true
)
~~~

Không bật thêm annotation mechanism chỉ vì thấy ví dụ trên mạng. Chỉ giữ các cơ chế mà ứng dụng thực sự sử dụng.

### 8.2. Giữ nguyên semantics của PreAuthorize/PostAuthorize

~~~java
@PreAuthorize("hasAuthority('SCOPE_orders.read')")
public OrderDto getOrder(UUID id) {
    return service.load(id);
}
~~~

Migration annotation không tự sửa expression. Kiểm tra method proxy có được tạo và method có được gọi qua Spring bean proxy không; self-invocation có bypass proxy không; parameter names có được giữ để expression dùng `#tenantId` không; expression có đọc đúng principal type sau Resource Server authentication không; và các method overload có policy khác nhau không.

Method security là lớp authorization bổ sung; không bỏ URL authorization hoặc tenant/resource checks chỉ vì đã có annotation.

### 8.3. Kiểm tra thứ tự và tương tác authorization

Nếu cả request-level và method-level authorization cùng tồn tại, một request có thể bị từ chối ở filter chain trước khi method được gọi. Test nên xác định rõ layer nào đang kiểm tra điều kiện nào.

Không viết test chỉ assert 403 rồi kết luận method expression hoạt động. Có thể filter chain đã từ chối trước đó. Với method-security tests, gọi method qua Spring-managed bean và cấu hình Authentication context phù hợp.

## 9. Cập nhật cấu hình OAuth 2.0 Resource Server

### 9.1. JWT Resource Server

Cách gọi cũ:

~~~java
http
    .oauth2ResourceServer()
        .jwt();
~~~

Lambda DSL:

~~~java
http.oauth2ResourceServer(oauth2 -> oauth2
    .jwt(Customizer.withDefaults())
);
~~~

Khi cần decoder và converter riêng:

~~~java
http.oauth2ResourceServer(oauth2 -> oauth2
    .jwt(jwt -> jwt
        .decoder(jwtDecoder)
        .jwtAuthenticationConverter(jwtAuthenticationConverter)
    )
);
~~~

Đổi DSL không làm thay đổi trust policy một cách an toàn tự động. Hãy giữ và kiểm tra issuer validator, audience validator, timestamp validator và clock skew, algorithm/key trust, claim-to-authority converter, custom principal mapping và error handling cho invalid token.

Không xóa validator để giải quyết compile error trong lúc migration.

### 9.2. Opaque token Resource Server

Cách gọi cũ:

~~~java
http
    .oauth2ResourceServer()
        .opaqueToken();
~~~

Lambda DSL:

~~~java
http.oauth2ResourceServer(oauth2 -> oauth2
    .opaqueToken(opaque -> opaque
        .introspector(opaqueTokenIntrospector)
    )
);
~~~

Nếu chỉ dùng auto-configuration mặc định:

~~~java
http.oauth2ResourceServer(oauth2 -> oauth2
    .opaqueToken(Customizer.withDefaults())
);
~~~

Kiểm tra lại introspection URI, client authentication, timeout, error mapping, authorities và principal attributes. Đừng vô tình chuyển từ opaque token sang JWT hoặc ngược lại chỉ để phù hợp với một ví dụ cấu hình.

### 9.3. Bearer token resolver và custom converter

Nếu ứng dụng tùy biến cách đọc token:

~~~java
http.oauth2ResourceServer(oauth2 -> oauth2
    .bearerTokenResolver(bearerTokenResolver)
    .jwt(jwt -> jwt
        .jwtAuthenticationConverter(jwtAuthenticationConverter)
    )
);
~~~

Giữ nguyên policy về vị trí token được phép xuất hiện. Theo chuẩn, access token thường được gửi trong Authorization header. Nếu ứng dụng cho phép query parameter hoặc form parameter, đánh giá rủi ro lộ token qua URL, history, referrer và access logs.

### 9.4. Legacy Spring Security OAuth project

Cần phân biệt Spring Security OAuth Resource Server hiện đại với project legacy `spring-security-oauth`. Các class như `@EnableResourceServer`, `ResourceServerConfigurerAdapter`, `ResourceServerTokenServices` hoặc `JwtAccessTokenConverter` thuộc mô hình legacy.

Migration thường chuyển sang Resource Server support tích hợp trong Spring Security:

- Dùng `SecurityFilterChain` thay cho `ResourceServerConfigurerAdapter`.
- Dùng `oauth2ResourceServer(oauth2 -> oauth2.jwt(...))` cho JWT.
- Dùng `oauth2ResourceServer(oauth2 -> oauth2.opaqueToken(...))` cho opaque token.
- Dùng `JwtDecoder`/`JwtAuthenticationConverter` hoặc `OpaqueTokenIntrospector` theo token format.
- Chuyển custom token services/claims mapping thành decoder, validator, converter hoặc introspector phù hợp.

Đây là migration kiến trúc, không phải chỉ đổi tên package. Hãy lập inventory cho custom grant, token enhancer, claims, authentication details, exception mapping và downstream principal contract trước khi bỏ dependency legacy.

## 10. Servlet và WebFlux có DSL riêng

Không áp dụng ví dụ Servlet cho reactive stack chỉ bằng cách đổi kiểu client.

| Thành phần | Servlet | WebFlux |
|---|---|---|
| HTTP security builder | `HttpSecurity` | `ServerHttpSecurity` |
| Chain type | `SecurityFilterChain` | `SecurityWebFilterChain` |
| Enable annotation | `@EnableWebSecurity` | `@EnableWebFluxSecurity` |
| Authorization DSL | `authorizeHttpRequests` | `authorizeExchange` |
| Request type | `HttpServletRequest` | `ServerWebExchange` |
| JWT decoder | `JwtDecoder` | `ReactiveJwtDecoder` |
| Opaque introspector | `OpaqueTokenIntrospector` | `ReactiveOpaqueTokenIntrospector` |

WebFlux example:

~~~java
@Bean
SecurityWebFilterChain apiSecurity(
        ServerHttpSecurity http,
        ReactiveJwtDecoder jwtDecoder) {

    return http
        .authorizeExchange(exchange -> exchange
            .pathMatchers("/api/public/**").permitAll()
            .pathMatchers("/api/orders/**")
                .hasAuthority("SCOPE_orders.read")
            .anyExchange().authenticated()
        )
        .oauth2ResourceServer(oauth2 -> oauth2
            .jwt(jwt -> jwt.jwtDecoder(jwtDecoder))
        )
        .build();
}
~~~

Trong WebFlux, authorization DSL thường là `authorizeExchange` và matcher dùng `pathMatchers` hoặc `matchers` theo API version. Không copy `authorizeHttpRequests` của Servlet vào `ServerHttpSecurity`.

Nếu ứng dụng có cả MVC và WebFlux dependencies, xác định application thực sự chạy stack nào và test đúng chain. Không chỉ nhìn dependency có mặt trong classpath.

## 11. Các thay đổi nền tảng khi nâng lên Spring Security 6

### 11.1. Java và Jakarta namespace

Spring Security 6 dựa trên Spring Framework 6 và Jakarta EE APIs. Ứng dụng nâng từ Spring Boot 2/Spring Security 5 lên Boot 3/Security 6 cần xử lý các package Jakarta liên quan.

Ví dụ Servlet:

~~~java
// Trước
import javax.servlet.Filter;
import javax.servlet.http.HttpServletRequest;

// Sau
import jakarta.servlet.Filter;
import jakarta.servlet.http.HttpServletRequest;
~~~

Tương tự, rà soát các API Jakarta khác mà ứng dụng sử dụng như validation, persistence và annotation. Không thay toàn bộ chuỗi `javax.` bằng `jakarta.` một cách mù quáng; một số package Java SE vẫn thuộc namespace `javax`.

### 11.2. Đồng bộ Spring Boot và Spring Security versions

Spring Boot quản lý các phiên bản Spring Framework, Spring Security và dependency liên quan thông qua dependency management/BOM. Thông thường nên dùng phiên bản do Spring Boot BOM quản lý thay vì tự pin từng artifact Spring Security.

Ví dụ Gradle:

~~~groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-security")
    implementation("org.springframework.boot:spring-boot-starter-oauth2-resource-server")
    testImplementation("org.springframework.security:spring-security-test")
}
~~~

Nếu dự án dùng Spring Boot plugin/BOM, tránh ghi version riêng cho từng `spring-security-*` artifact trừ khi có lý do tương thích được xác minh.

Nếu override version không đồng bộ, có thể gặp linkage errors, `NoSuchMethodError`, `ClassNotFoundException` hoặc behavior khác nhau giữa compile/runtime.

### 11.3. Kiểm tra dependency tree

Gradle:

~~~bash
./gradlew dependencyInsight --dependency spring-security-config --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-security-oauth2-resource-server --configuration runtimeClasspath
./gradlew dependencies --configuration testRuntimeClasspath
~~~

Maven:

~~~bash
mvn dependency:tree -Dincludes=org.springframework.security
~~~

Xác nhận các module Spring Security cùng một release train tương thích, starter và test dependency không kéo version xung đột, và không còn module legacy ngoài ý muốn.

## 12. Quy trình migration theo từng bước

Không nên đổi đồng thời Java, Spring Boot, Spring Security, Jakarta, matcher và authorization policy trong một commit lớn nếu có thể tách giai đoạn.

### Bước 1 — Chụp lại baseline

Ghi nhận Java version, Spring Boot version, Spring Security module versions, Servlet hay WebFlux, số lượng SecurityFilterChain, Resource Server dùng JWT hay opaque token, custom decoder/converter/introspector/resolver/validators, method security annotations và tests hiện có.

Lưu dependency tree và kết quả test trước migration để có baseline so sánh.

### Bước 2 — Nâng lên bản chuyển tiếp tương thích nếu cần

Nếu đang ở Spring Security 5.x cũ, cân nhắc nâng lên 5.8 trước khi chuyển major. Dùng API chuyển tiếp để loại matcher cũ và adapter, sau đó chạy tests.

Không ép một dự án đã không còn hỗ trợ lên một bản trung gian không tương thích với Java/Boot hiện tại. Chọn đường nâng cấp được Spring Boot release train hỗ trợ.

### Bước 3 — Thay WebSecurityConfigurerAdapter

Tạo bean `SecurityFilterChain` cho từng chain. Di chuyển URL rules, Resource Server config, CORS, CSRF, session, exception handling và custom providers vào bean.

Nếu có nhiều adapter trước đây, xác định chúng đã tạo bao nhiêu chain và thứ tự nào. Đừng gộp nhiều chain thành một nếu mỗi chain có matcher, authentication mechanism hoặc stateless/session policy khác nhau.

### Bước 4 — Chuyển authorization DSL và matchers

Thay `authorizeRequests` bằng `authorizeHttpRequests`. Thay matcher cũ bằng `requestMatchers` hoặc RequestMatcher phù hợp. Chuyển matcher chọn chain sang `securityMatcher`.

Kiểm tra semantics path, HTTP method, context path, servlet path và thứ tự rule.

### Bước 5 — Chuyển no-arg configurer calls

Dùng lambda cho CSRF, CORS, headers, session management, exception handling, OAuth2 Resource Server, form login và HTTP Basic. Xóa các warning deprecated-for-removal.

### Bước 6 — Chuyển authentication và method security

Thay cấu hình AuthenticationManagerBuilder/adapter overrides bằng UserDetailsService, PasswordEncoder, AuthenticationProvider hoặc AuthenticationManager bean. Chuyển method security sang `@EnableMethodSecurity` và giữ nguyên enabled flags.

### Bước 7 — Nâng nền tảng Java/Jakarta và dependency

Đảm bảo Java version, Spring Boot, Spring Framework và Spring Security tương thích. Cập nhật import Jakarta ở các API liên quan. Kiểm tra không có module Security bị pin lệch.

### Bước 8 — Chạy integration tests với token thật

Dùng signed JWT test key qua filter chain hoặc introspection stub phù hợp. Kiểm tra issuer, audience, signature, expiry, scope mapping, principal type, 401/403 và multiple filter chains.

### Bước 9 — Deploy canary và quan sát

Theo dõi authentication success/failure, 401/403, decoder/JWKS errors, introspection latency, session behavior và endpoint matcher. So sánh node mới/cũ trước khi hoàn tất rollout.

## 13. Kiểm thử hồi quy sau migration

### 13.1. Test URL authorization

Với từng chain, kiểm tra:

- Public endpoint vẫn public.
- Endpoint protected vẫn yêu cầu authentication.
- Scope/role mapping giữ nguyên.
- Matcher cụ thể không bị rule tổng quát che.
- Method khác nhau có rule đúng.
- Endpoint không khớp chain API không vô tình được mở.
- CSRF/CORS/session behavior vẫn đúng với loại client.

### 13.2. Test JWT Resource Server

Gửi compact JWT được ký bằng test key qua Authorization header và xác nhận:

- Decoder đang được cấu hình thực sự được gọi.
- Issuer, audience, signature và timestamp validation vẫn chạy.
- Custom JwtAuthenticationConverter tạo authorities như trước.
- Controller nhận đúng principal/claims.
- Token invalid trả 401; token hợp lệ nhưng thiếu quyền trả 403.
- Key rotation/JWKS refresh behavior không bị thay đổi ngoài dự kiến.

MockMvc `jwt()` hoặc WebFlux `mockJwt()` hữu ích cho principal/authorization tests, nhưng chúng tạo Authentication giả lập và bỏ qua decoder. Không dùng chúng làm bằng chứng cho signature validation.

### 13.3. Test opaque token

Nếu ứng dụng dùng opaque token:

- Introspection endpoint và client authentication còn đúng.
- Active principal có attributes/authorities đúng.
- Inactive token trả authentication failure.
- Lỗi network/timeout được phân biệt với token inactive.
- Principal type và application mapping không thay đổi.
- Request vẫn dùng đúng Bearer token extraction path.

### 13.4. Test method security

Gọi method qua Spring-managed bean. Kiểm tra cả allow và deny, parameter expression, tenant ownership và self-invocation cases nếu code có internal method calls.

Nếu trước đây dùng `@EnableGlobalMethodSecurity`, test riêng `@PreAuthorize`, `@PostAuthorize`, `@Secured` và JSR-250 theo đúng flags đã migrate.

### 13.5. Test nhiều SecurityFilterChain

Với mỗi chain, tạo request khớp và không khớp matcher. Xác nhận chain đúng xử lý request, authentication mechanism không bị trộn và thứ tự `@Order` không làm route rơi vào catch-all ngoài ý muốn.

## 14. Lỗi migration thường gặp

### Lỗi 1 — Chỉ thay tên method mà giữ nguyên DSL cũ

Đổi `authorizeRequests` thành `authorizeHttpRequests` nhưng vẫn gọi no-arg configurer hoặc matcher đã bị xóa. Hãy chuyển cả authorization DSL, matcher và configurer calls.

### Lỗi 2 — Vẫn kế thừa WebSecurityConfigurerAdapter

Adapter đã bị loại khỏi Spring Security 6. Chuyển cấu hình sang bean `SecurityFilterChain` và các bean authentication cần thiết.

### Lỗi 3 — Dùng requestMatchers để chọn chain

`requestMatchers` là authorization rule trong chain. Dùng `securityMatcher` để xác định request thuộc chain nào.

### Lỗi 4 — Matcher mới không có semantics giống matcher cũ

Overload string có thể chọn matcher theo classpath/version. Test context path, servlet path, MVC matching và HTTP method. Dùng RequestMatcher rõ ràng khi cần semantics cụ thể.

### Lỗi 5 — Thay ignoring thành permitAll mà không đánh giá filter behavior

`permitAll` vẫn chạy security filters; `ignoring` bỏ qua chain. Chọn theo yêu cầu security headers, CORS, logging và các filter khác.

### Lỗi 6 — Disable CSRF cho toàn bộ ứng dụng

API stateless dùng Bearer header có thể có policy CSRF khác browser session/cookie. Đừng tắt CSRF cho cả ứng dụng chỉ vì có Resource Server.

### Lỗi 7 — Quên default mới của EnableMethodSecurity

`@EnableMethodSecurity` mặc định bật pre/post annotations. Khai báo flags tường minh để giữ behavior mong muốn và test từng annotation mechanism.

### Lỗi 8 — Pin Spring Security modules lệch version

Dùng Spring Boot BOM hoặc dependency management tương thích. Kiểm tra runtime dependency tree, không chỉ compile classpath.

### Lỗi 9 — Bỏ validator khi chuyển Resource Server DSL

Giữ issuer, audience, timestamp và custom validators. Compile thành công không có nghĩa trust policy còn nguyên.

### Lỗi 10 — Chỉ chạy unit tests

Unit tests không chứng minh filter chain, decoder, request matcher và method security được nối đúng. Cần integration tests qua HTTP stack thật của ứng dụng.

## 15. Bảng đối chiếu API cũ và mới

| API/cách cấu hình cũ | API/cách cấu hình mới | Lưu ý migration |
|---|---|---|
| `WebSecurityConfigurerAdapter` | Bean `SecurityFilterChain` | Giữ riêng từng chain và thứ tự |
| `configure(HttpSecurity)` | `@Bean SecurityFilterChain` | Trả về kết quả `http.build()` |
| `configure(WebSecurity)` | `WebSecurityCustomizer` | Chỉ ignore khi thật sự cần bypass |
| `authorizeRequests` | `authorizeHttpRequests` | AuthorizationManager model |
| `antMatchers` / `mvcMatchers` / `regexMatchers` | `requestMatchers` | Xác nhận semantics matcher |
| `http.antMatcher` / `mvcMatcher` | `securityMatcher` | Chọn chain, không phải rule |
| No-arg configurer methods | Lambda / `Customizer.withDefaults()` | Tránh deprecated-for-removal |
| `configure(AuthenticationManagerBuilder)` | `AuthenticationProvider` / `AuthenticationManager` beans | Chuyển user lookup và password encoder |
| `@EnableGlobalMethodSecurity` | `@EnableMethodSecurity` | Giữ flags và kiểm tra default |
| `oauth2ResourceServer().jwt()` | `oauth2ResourceServer(o -> o.jwt(...))` | Giữ decoder, validators và converter |
| `oauth2ResourceServer().opaqueToken()` | `oauth2ResourceServer(o -> o.opaqueToken(...))` | Giữ introspector và principal mapping |
| Legacy `@EnableResourceServer` | Built-in Resource Server support | Đây là migration kiến trúc |
| `javax.servlet.*` | `jakarta.servlet.*` | Áp dụng khi nâng lên nền Jakarta |

Bảng là bản đồ định hướng, không phải script thay thế tự động. Một số overload có thể khác giữa các minor release; compiler và API reference của version mục tiêu là nguồn xác nhận cuối cùng.

## 16. Ví dụ migration hoàn chỉnh cho Servlet Resource Server

Một cấu hình JWT API hiện đại có thể trông như sau:

~~~java
@Configuration
@EnableWebSecurity
@EnableMethodSecurity
public class ApiSecurityConfiguration {

    @Bean
    SecurityFilterChain apiSecurity(
            HttpSecurity http,
            JwtDecoder jwtDecoder,
            JwtAuthenticationConverter jwtAuthenticationConverter)
            throws Exception {

        return http
            .securityMatcher("/api/**")
            .csrf(csrf -> csrf.disable())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            )
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers(HttpMethod.GET, "/api/public/**")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(jwt -> jwt
                    .decoder(jwtDecoder)
                    .jwtAuthenticationConverter(jwtAuthenticationConverter)
                )
            )
            .build();
    }
}
~~~

Đây là ví dụ cho một API stateless chỉ nhận Bearer token trong header. Nếu ứng dụng dùng cookie/session, đánh giá CSRF trước khi disable. Nếu có browser routes, đặt chúng trong chain riêng với session/login policy phù hợp.

Các bean decoder/converter phải giữ validators và claim mapping của hệ thống. Không coi việc chuyển code sang lambda là hoàn thành migration nếu audience validator hoặc custom authority mapping đã bị bỏ.

## 17. Kiểm tra thay đổi theo version trong build và IDE

Khi nâng phiên bản, hãy đọc compiler warnings thay vì chỉ tìm và thay chuỗi API. Một số phương thức tồn tại ở bản hiện tại nhưng đã deprecated-for-removal; một số khác đã bị xóa hoàn toàn.

Quy trình hữu ích:

1. Kiểm tra Spring Boot plugin/BOM và Java toolchain.
2. Chạy compile để nhận diện API đã bị xóa.
3. Bật hoặc xem deprecation warnings cho Spring Security.
4. Tìm các class adapter, matcher và configurer cũ.
5. Kiểm tra dependency tree của runtime và test.
6. Chạy test security chain sau từng nhóm thay đổi.

Các tìm kiếm trong repository có thể gồm:

~~~bash
rg -n "WebSecurityConfigurerAdapter|authorizeRequests|antMatchers|mvcMatchers|regexMatchers" src
rg -n "EnableGlobalMethodSecurity|oauth2ResourceServer\\(\\)|csrf\\(\\)|headers\\(\\)" src
rg -n "EnableResourceServer|ResourceServerConfigurerAdapter|JwtAccessTokenConverter" .
~~~

Điều chỉnh path theo layout dự án. Các lệnh chỉ tìm vị trí có khả năng cần migration; không thay thế việc đọc ngữ cảnh của từng kết quả.

## 18. Checklist hoàn tất migration

- [ ] Đã chốt Spring Boot, Spring Framework, Spring Security và Java versions tương thích.
- [ ] Các module Spring Security được quản lý cùng release train.
- [ ] Không còn kế thừa `WebSecurityConfigurerAdapter`.
- [ ] Mỗi `SecurityFilterChain` có matcher và `@Order` đúng.
- [ ] Đã phân biệt `securityMatcher` với `requestMatchers`.
- [ ] Đã thay legacy authorization DSL và matcher đã bị loại bỏ.
- [ ] Không còn no-arg configurer methods deprecated-for-removal.
- [ ] Đã rà soát `WebSecurityCustomizer` và lý do dùng `ignoring`.
- [ ] CSRF/CORS/session behavior phù hợp từng loại client.
- [ ] AuthenticationProvider/AuthenticationManager được đăng ký đúng.
- [ ] Method security dùng annotation mới và giữ đúng flags.
- [ ] JWT decoder vẫn kiểm tra issuer, audience, signature và timestamps.
- [ ] Authority converter và principal claims giữ đúng contract.
- [ ] Opaque introspection vẫn dùng đúng endpoint, client authentication và mapping.
- [ ] Legacy Spring Security OAuth components đã được inventory và migrate có chủ đích.
- [ ] Import Jakarta đã được cập nhật ở API liên quan.
- [ ] Unit, MockMvc/WebTestClient và signed-token integration tests đều chạy.
- [ ] Các test 401/403, matcher order và multiple chains đã được xác nhận.
- [ ] Canary/production rollout có metrics để phát hiện authentication regression.

## 19. Kết luận

Migration Lambda DSL cần được thực hiện cùng với việc chuyển các API cấu hình đã deprecated hoặc bị loại bỏ theo từng dòng Spring Security.

Các bước quan trọng nhất là thay adapter bằng bean `SecurityFilterChain`, chuyển authorization sang `authorizeHttpRequests` và `requestMatchers`, dùng `securityMatcher` để chọn chain, thay no-arg configurer calls bằng lambda, cập nhật method security và giữ nguyên decoder/validator/converter của Resource Server.

Hãy dùng version matrix, compiler warnings, dependency tree và integration tests để xác nhận migration. Một cấu hình mới chỉ hoàn tất khi request vẫn đi qua đúng filter chain, token vẫn được xác minh theo trust policy cũ và authorization behavior không thay đổi ngoài chủ đích.

### Tài liệu tham khảo

- [Spring Security Reference — Lambda DSL](https://docs.spring.io/spring-security/reference/servlet/configuration/java.html)
- [Spring Security Reference — Java Configuration](https://docs.spring.io/spring-security/reference/servlet/configuration/java.html)
- [Spring Security Reference — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security Reference — Multiple HttpSecurity Instances](https://docs.spring.io/spring-security/reference/servlet/configuration/java.html#_multiple_httpsecurity_instances)
- [Spring Security Reference — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security Reference — OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html)
- [Spring Security Reference — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Security Reference — Migration Guides](https://docs.spring.io/spring-security/reference/migration/index.html)
- [Spring Boot Reference — Dependency Versions](https://docs.spring.io/spring-boot/reference/using/build-systems.html)








