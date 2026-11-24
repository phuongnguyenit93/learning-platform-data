# Spring Security với filter chain, method security và tích hợp danh tính

Spring Security bảo vệ ứng dụng Spring Boot ở nhiều lớp: filter chain kiểm soát HTTP request, method security bảo vệ thao tác nghiệp vụ, còn các cơ chế tích hợp danh tính xác thực người dùng hoặc dịch vụ qua UserDetails, JWT, OAuth 2.0 và OpenID Connect. Khi chuyển ứng dụng sang **GraalVM Native Image**, các thành phần chuẩn của Spring Security đã được tích hợp với Spring AOT, nhưng một số đường truy cập động của ứng dụng vẫn cần reflection hints.

Trong module **`SPRING_BOOT_NATIVE_IMAGE`**, mục tiêu là biên dịch ứng dụng Spring Boot bằng Spring AOT, đánh giá startup và memory, kiểm thử tương thích, đóng gói container và vận hành bản native. Bài học này tập trung vào cách thiết kế SecurityFilterChain, method authorization và identity integration sao cho có thể phân tích AOT; cách bổ sung hints cho custom principal hoặc Authentication được gọi qua SpEL; và cách kiểm chứng các luồng bảo mật trên native executable.

> **Phạm vi:** ví dụ chính dùng Servlet stack (Spring MVC và `SecurityFilterChain`). WebFlux dùng `SecurityWebFilterChain` và reactive security context riêng; không dùng lẫn hai mô hình. Spring Security hỗ trợ Native Image, nhưng vẫn cần kiểm tra những class và member do ứng dụng tự truy cập động.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích vai trò của `FilterChainProxy` và thứ tự các `SecurityFilterChain`.
- Cấu hình request authorization cho API stateless và web login có session.
- Đặt custom filter đúng vị trí trong filter chain.
- Bật method security bằng `@EnableMethodSecurity` và bảo vệ service bằng `@PreAuthorize`/`@PostAuthorize`.
- Tích hợp custom `UserDetails`, `Authentication`, OAuth2 Resource Server và OIDC Login.
- Nhận biết trường hợp SpEL gọi method trên custom principal cần reflection hints.
- Phân biệt hỗ trợ Native Image có sẵn của Spring Security với hints riêng của ứng dụng.
- Kiểm thử authentication, authorization, method security và identity provider trên native executable.

## 2. Kiến trúc bảo mật có ba lớp

Một request đi vào ứng dụng Servlet thường đi qua các lớp sau:

1. **Servlet filter chain:** nhận request từ container và chuyển vào Spring Security.
2. **Security filter chain:** tải SecurityContext, bảo vệ request, xác thực credential và áp dụng request authorization.
3. **Method security:** khi controller/service gọi một Spring bean được bảo vệ, interceptor kiểm tra quyền trước hoặc sau khi thực thi method.

Danh tính có thể đến từ nhiều nguồn: username/password, JWT bearer token, opaque token, OAuth2 Login/OIDC hoặc một hệ thống xác thực riêng. Spring Security chuyển kết quả xác thực thành `Authentication` và đặt trong `SecurityContext` để các lớp authorization sử dụng.

~~~mermaid
flowchart TD
    A["HTTP request"] --> B["Servlet container filters"]
    B --> C["DelegatingFilterProxy"]
    C --> D["FilterChainProxy"]
    D --> E["SecurityFilterChain phù hợp"]
    E --> F["Load SecurityContext"]
    F --> G["Authentication filters"]
    G --> H["Request authorization"]
    H --> I["Controller"]
    I --> J["Spring service proxy"]
    J --> K["Method authorization"]
    K --> L["Business method"]
    M["UserDetails / JWT / OIDC / custom Authentication"] --> G
~~~

Với Native Image, các filter và authorization manager chuẩn đã thuộc Spring Security. Phần cần xem xét thêm thường nằm ở custom filter, custom principal, biểu thức SpEL, serializer hoặc thư viện identity mà ứng dụng tích hợp.

## 3. SecurityFilterChain và thứ tự xử lý request

`SecurityFilterChain` là tập filter áp dụng cho một nhóm request. `FilterChainProxy` xem các chain theo thứ tự và chọn **chain đầu tiên có matcher khớp**. Nếu nhiều chain cùng khớp một URL, chain sau không tiếp tục được áp dụng cho request đó.

Ví dụ API dùng bearer token:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
@EnableWebSecurity
public class ApiSecurityConfiguration {

    @Bean
    SecurityFilterChain apiSecurityFilterChain(HttpSecurity http) throws Exception {
        http
            .csrf(csrf -> csrf.disable())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/actuator/health").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/catalog/**").permitAll()
                .requestMatchers("/api/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults()));

        return http.build();
    }
}
~~~

Trong ví dụ này:

- Health endpoint và catalog GET được công khai.
- `/api/admin/**` yêu cầu authority `ROLE_ADMIN` vì `hasRole("ADMIN")` tự thêm prefix `ROLE_`.
- Các request còn lại cần xác thực.
- API dùng bearer token và không dựa vào cookie/session nên cấu hình stateless.
- CSRF được tắt cho chain này vì credential được gửi qua Authorization header; không sao chép lựa chọn này sang web application dùng cookie/session mà chưa đánh giá CSRF.

### Nhiều filter chain

Ứng dụng có thể tách API và browser login thành các chain riêng:

~~~java
@Configuration(proxyBeanMethods = false)
@EnableWebSecurity
class SecurityConfiguration {

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/api/**")
            .csrf(csrf -> csrf.disable())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/api/public/**").permitAll()
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth2 -> oauth2.jwt(Customizer.withDefaults()));
        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain browserChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/", "/assets/**").permitAll()
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .oauth2Login(Customizer.withDefaults());
        return http.build();
    }
}
~~~

Chain đầu tiên chỉ xét `/api/**`; chain thứ hai xử lý phần còn lại. Nếu tạo nhiều chain, cần kiểm tra:

- `securityMatcher` có bao phủ đúng URL dự kiến không.
- `@Order` có đặt chain đặc thù trước chain tổng quát không.
- Có request nào không khớp bất kỳ chain nào không.
- Các endpoint Actuator có được bảo vệ theo chủ đích không.

Một `SecurityFilterChain` bean tùy chỉnh làm Spring Boot lùi lại cấu hình web security mặc định. Khi đó, ứng dụng chịu trách nhiệm khai báo đầy đủ rules cần thiết. Spring Boot vẫn có thể cấu hình `UserDetailsService` mặc định nếu chưa có bean authentication tương ứng và dependency không làm auto-configuration đó lùi lại.

## 4. Custom filter: chọn đúng vị trí

Custom filter thường được dùng để kiểm tra tenant, correlation identity hoặc một loại credential riêng. Thứ tự filter rất quan trọng vì nó quyết định SecurityContext đã được tải hay authentication đã hoàn tất chưa.

| Loại filter | Vị trí thường phù hợp |
|---|---|
| Custom authentication filter | Sau `LogoutFilter` và trước các bước authorization |
| Filter cần đọc authenticated principal để kiểm tra tenant | Sau `AnonymousAuthenticationFilter` |
| Filter bảo vệ request trước authentication | Sau `SecurityContextHolderFilter`, tùy mục đích |

Ví dụ filter kiểm tra tenant sau khi authentication đã chạy:

~~~java
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

@Component
public class TenantAccessFilter extends OncePerRequestFilter {

    private final TenantAuthorizationService tenantAuthorizationService;

    public TenantAccessFilter(TenantAuthorizationService tenantAuthorizationService) {
        this.tenantAuthorizationService = tenantAuthorizationService;
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain) throws ServletException, IOException {

        Authentication authentication =
                SecurityContextHolder.getContext().getAuthentication();

        if (authentication == null
                || !authentication.isAuthenticated()
                || authentication instanceof AnonymousAuthenticationToken) {
            filterChain.doFilter(request, response);
            return;
        }

        String tenantId = request.getHeader("X-Tenant-Id");
        if (tenantId == null
                || !tenantAuthorizationService.canAccess(authentication, tenantId)) {
            response.sendError(HttpServletResponse.SC_FORBIDDEN);
            return;
        }

        filterChain.doFilter(request, response);
    }
}
~~~

Đăng ký filter trong chain:

~~~java
@Bean
SecurityFilterChain apiSecurityFilterChain(
        HttpSecurity http,
        TenantAccessFilter tenantAccessFilter) throws Exception {

    http
        .authorizeHttpRequests(authorize -> authorize
            .anyRequest().authenticated())
        .oauth2ResourceServer(oauth2 -> oauth2.jwt(Customizer.withDefaults()))
        .addFilterAfter(
            tenantAccessFilter,
            AnonymousAuthenticationFilter.class);

    return http.build();
}
~~~

Nếu filter được khai báo thành Spring bean trong ứng dụng Spring Boot Servlet, Boot cũng có thể đăng ký nó với servlet container. Khi filter chỉ nên chạy bên trong Spring Security chain, hãy tắt đăng ký servlet riêng:

~~~java
@Bean
FilterRegistrationBean<TenantAccessFilter> tenantFilterServletRegistration(
        TenantAccessFilter filter) {
    FilterRegistrationBean<TenantAccessFilter> registration =
            new FilterRegistrationBean<>(filter);
    registration.setEnabled(false);
    return registration;
}
~~~

Điều này tránh filter chạy hai lần trên cùng request. Nếu filter được tạo trực tiếp và chỉ được gắn trong chain, không cần thêm servlet registration.

### Custom filter và Native Image

Việc filter là một class tự viết **không tự động có nghĩa cần reflection hints**. Nếu filter được Spring tạo qua constructor injection và được gắn trực tiếp vào chain, AOT thường có thể xử lý cấu trúc bean thông thường. Hints chỉ cần khi filter hoặc thư viện nó dùng thực hiện truy cập động mà builder không suy ra được, chẳng hạn:

- Gọi method trên principal bằng reflection/SpEL.
- Nạp implementation theo class name lấy từ cấu hình.
- Đọc resource theo tên được tạo động.
- Tạo JDK proxy hoặc dùng JNI theo cách không có metadata.

Hãy kiểm tra lỗi native thực tế và bổ sung hint cho đúng class/member/resource. Không đăng ký reflection rộng cho mọi filter và mọi class Spring Security.

## 5. Method security bảo vệ lớp nghiệp vụ

Request authorization trả lời câu hỏi “request này được vào endpoint nào?”. Method security trả lời câu hỏi “người dùng này có được gọi thao tác nghiệp vụ cụ thể không?”.

Spring Boot Starter Security không tự bật method-level authorization. Cần bật rõ ràng bằng `@EnableMethodSecurity`:

~~~java
@Configuration(proxyBeanMethods = false)
@EnableMethodSecurity
class MethodSecurityConfiguration {
}
~~~

Sau đó có thể dùng `@PreAuthorize`, `@PostAuthorize`, `@PreFilter` và `@PostFilter` trên Spring-managed beans:

~~~java
@Service
public class InvoiceService {

    @PreAuthorize("hasAuthority('invoice:read')")
    public Invoice findById(String invoiceId) {
        return loadInvoice(invoiceId);
    }

    @PreAuthorize(
        "hasAuthority('invoice:read:any') or #ownerId == authentication.name")
    public List<Invoice> findForOwner(String ownerId) {
        return loadInvoices(ownerId);
    }

    @PostAuthorize(
        "returnObject.ownerId == authentication.name or hasAuthority('invoice:read:any')")
    public Invoice read(String invoiceId) {
        return loadInvoice(invoiceId);
    }
}
~~~

Ý nghĩa:

- `hasAuthority` so sánh chính xác authority string.
- `hasRole("ADMIN")` kiểm tra authority `ROLE_ADMIN`.
- `@PreAuthorize` kiểm tra trước khi method chạy.
- `@PostAuthorize` kiểm tra kết quả sau khi method trả về.
- `#ownerId` truy cập tham số method; `returnObject` là giá trị trả về.

Method security dùng Spring AOP proxy. Lời gọi phải đi qua Spring bean proxy thì interceptor mới được áp dụng. Gọi một method được bảo vệ từ method khác trong cùng instance (self-invocation qua `this`) không đi qua proxy và có thể bỏ qua interceptor; hãy tổ chức service hoặc gọi qua bean boundary phù hợp.

### Phân biệt role và authority

| Expression | Quy tắc |
|---|---|
| `hasRole("ADMIN")` | Kiểm tra `ROLE_ADMIN` |
| `hasAuthority("ROLE_ADMIN")` | Kiểm tra đúng chuỗi `ROLE_ADMIN` |
| `hasAuthority("invoice:read")` | Kiểm tra đúng permission `invoice:read` |
| `hasAnyAuthority("invoice:read", "invoice:read:any")` | Cho phép một trong các permission |

Nên thống nhất quy ước authority giữa identity provider, JWT converter, UserDetails và method security.

## 6. Custom UserDetails và principal trong biểu thức SpEL

Một use case đặc biệt quan trọng với Native Image là SpEL gọi method trên custom principal. Ví dụ custom `UserDetails`:

~~~java
import java.util.Collection;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.userdetails.UserDetails;

public class CustomUserDetails implements UserDetails {

    private final String username;
    private final String password;
    private final Collection<? extends GrantedAuthority> authorities;

    public CustomUserDetails(
            String username,
            String password,
            Collection<? extends GrantedAuthority> authorities) {
        this.username = username;
        this.password = password;
        this.authorities = authorities;
    }

    public boolean isAdmin() {
        return this.authorities.contains(
                new SimpleGrantedAuthority("ROLE_ADMIN"));
    }

    @Override
    public Collection<? extends GrantedAuthority> getAuthorities() {
        return authorities;
    }

    @Override
    public String getPassword() {
        return password;
    }

    @Override
    public String getUsername() {
        return username;
    }

    @Override
    public boolean isAccountNonExpired() {
        return true;
    }

    @Override
    public boolean isAccountNonLocked() {
        return true;
    }

    @Override
    public boolean isCredentialsNonExpired() {
        return true;
    }

    @Override
    public boolean isEnabled() {
        return true;
    }
}
~~~

Service dùng method của principal:

~~~java
@Service
public class AdminReportService {

    @PreAuthorize("principal?.isAdmin()")
    public Report generateSensitiveReport() {
        return createReport();
    }
}
~~~

Spring Security đánh giá biểu thức và có thể dùng reflection để gọi `isAdmin()`. Native Image không mặc định cho phép mọi reflective access. Nếu method hoặc class này không được hints bao phủ, ứng dụng có thể chạy tốt trên JVM nhưng lỗi khi gọi method trên native executable.

Spring Security hướng dẫn đăng ký custom `UserDetails` class bằng `@RegisterReflectionForBinding`:

~~~java
import org.springframework.aot.hint.annotation.RegisterReflectionForBinding;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@RegisterReflectionForBinding(CustomUserDetails.class)
class SecurityRuntimeHintsConfiguration {
}
~~~

Nếu biểu thức `@PreAuthorize`/`@PostAuthorize` sử dụng nhiều custom principal hoặc `Authentication` types, hãy đăng ký các kiểu tương ứng và kiểm thử từng biểu thức. Không chỉ đăng ký class principal đầu tiên rồi giả định mọi kiểu dữ liệu trong SpEL đã có metadata.

### Khi SpEL gọi bean authorization riêng

Có thể tách logic quyền phức tạp sang bean:

~~~java
@Component("invoiceAuthz")
public class InvoiceAuthorization {

    public boolean canRead(Authentication authentication, Invoice invoice) {
        return invoice.ownerId().equals(authentication.getName())
                || authentication.getAuthorities().stream()
                    .anyMatch(authority ->
                        authority.getAuthority().equals("invoice:read:any"));
    }
}
~~~

~~~java
@PreAuthorize("@invoiceAuthz.canRead(authentication, #invoice)")
public Invoice read(Invoice invoice) {
    return loadInvoice(invoice.id());
}
~~~

Spring Security AOT có thể quét các Spring beans để tìm method dùng `@PreAuthorize` hoặc `@PostAuthorize`, phân giải bean được tham chiếu trong security expression và đăng ký runtime hints thích hợp cho bean đó. Dù vậy, custom types được gọi động bên trong biểu thức vẫn cần được kiểm tra riêng.

## 7. Tích hợp username/password qua UserDetailsService

Với ứng dụng dùng form login hoặc HTTP Basic, `UserDetailsService` tải thông tin tài khoản và `PasswordEncoder` kiểm tra mật khẩu:

~~~java
@Configuration(proxyBeanMethods = false)
class PasswordAuthenticationConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(
            AccountRepository accounts) {
        return username -> accounts.findByUsername(username)
                .map(account -> new CustomUserDetails(
                        account.username(),
                        account.passwordHash(),
                        account.authorities()))
                .orElseThrow(() ->
                        new UsernameNotFoundException("Account not found"));
    }
}
~~~

Mật khẩu lưu trong database phải là password hash do PasswordEncoder tạo ra; không lưu plain text. Với production, cần cấu hình rate limiting, lockout policy, MFA hoặc cơ chế identity provider phù hợp.

Nếu `CustomUserDetails` chỉ được dùng để cung cấp `getUsername()`/`getAuthorities()` theo các đường truy cập tĩnh, có thể không cần thêm hints riêng. Nếu SpEL hoặc thư viện gọi method/field của nó bằng reflection, dùng binding hints như phần trước và kiểm thử native.

## 8. OAuth2 Resource Server với JWT

Resource Server xác thực bearer token từ client và đưa kết quả vào `Authentication`. Với JWT, Spring Security dùng `JwtDecoder` để xác minh chữ ký, issuer, thời hạn và decode claims.

Dependency Spring Boot:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
</dependency>
~~~

Cấu hình issuer:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.com/issuer
~~~

Spring Boot có thể tự cấu hình Resource Server từ property này. Nếu cần tự kiểm soát chain, dùng:

~~~java
@Bean
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    http
        .authorizeHttpRequests(authorize -> authorize
            .anyRequest().authenticated())
        .oauth2ResourceServer(oauth2 -> oauth2.jwt(Customizer.withDefaults()));
    return http.build();
}
~~~

### Map claim thành authority

Identity provider có thể phát claim `roles` riêng. Dùng `JwtAuthenticationConverter` để chuyển claim thành `GrantedAuthority`:

~~~java
@Bean
JwtAuthenticationConverter jwtAuthenticationConverter() {
    JwtGrantedAuthoritiesConverter scopesConverter =
            new JwtGrantedAuthoritiesConverter();

    JwtAuthenticationConverter converter = new JwtAuthenticationConverter();
    converter.setJwtGrantedAuthoritiesConverter(jwt -> {
        Collection<GrantedAuthority> authorities =
                new ArrayList<>(scopesConverter.convert(jwt));

        List<String> roles = jwt.getClaimAsStringList("roles");
        if (roles != null) {
            roles.stream()
                    .map(role -> new SimpleGrantedAuthority("ROLE_" + role))
                    .forEach(authorities::add);
        }
        return authorities;
    });
    return converter;
}
~~~

Gắn converter vào resource server:

~~~java
.oauth2ResourceServer(oauth2 -> oauth2
    .jwt(jwt -> jwt.jwtAuthenticationConverter(jwtAuthenticationConverter)))
~~~

Sau đó method security có thể dùng `hasRole("ADMIN")` hoặc `hasAuthority("SCOPE_invoice.read")` theo convention đã chọn.

### JWT và Native Image

Các thành phần Resource Server chuẩn của Spring Security được hỗ trợ Native Image. Khi ứng dụng dùng custom converter, custom `Authentication`, hoặc SpEL gọi method trên principal, cần kiểm tra thêm:

- Class custom có được AOT xử lý như Spring bean không.
- Có reflective access nào không được suy ra không.
- Public key, certificate hoặc file cấu hình có phải resource đọc từ classpath không.
- JWK endpoint/issuer có truy cập được trong môi trường runtime native không.

`issuer-uri` thường yêu cầu discovery metadata của identity provider và lấy JWK set khi cần. Điều đó là hoạt động mạng lúc runtime. Nếu muốn cấu hình trực tiếp JWK Set URI, có thể dùng `jwk-set-uri`; nếu vẫn cần kiểm tra issuer, cấu hình issuer tương ứng theo hướng dẫn Spring Security. Không nhầm network discovery với resource classpath hint.

## 9. Opaque token và introspection

Với opaque bearer token, ứng dụng không tự giải mã JWT. Nó gửi token đến authorization server để introspection và nhận thông tin token còn hiệu lực, subject và scope.

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://identity.example.com/oauth2/introspect
          client-id: ${INTROSPECTION_CLIENT_ID}
          client-secret: ${INTROSPECTION_CLIENT_SECRET}
~~~

Spring Security dùng `OpaqueTokenIntrospector` để xác minh token. Credential introspection phải lấy từ secret manager hoặc environment được quản lý an toàn; không commit secret vào repository.

Trong native executable, cần kiểm tra:

- DNS, network, proxy và TLS trust configuration của container.
- Authorization server có reachable từ môi trường deployment không.
- Timeout, retry và failure behavior khi introspection endpoint không sẵn sàng.
- Authorities được ánh xạ đúng vào các endpoint/method.

Đây chủ yếu là kiểm tra tích hợp mạng/runtime; chỉ thêm reflection hints nếu custom introspector thực hiện dynamic access chưa được AOT nhận diện.

## 10. OAuth2 Login và OpenID Connect

OAuth2 Client có thể đăng nhập người dùng qua OAuth 2.0 hoặc OIDC. Với OIDC, scope `openid` khiến Spring Security dùng các thành phần OIDC như `OidcUserService` và xác minh ID token.

Dependency:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-client</artifactId>
</dependency>
~~~

Cấu hình registration:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company-login:
            provider: company-idp
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            scope: openid, profile, email
        provider:
          company-idp:
            issuer-uri: https://identity.example.com
~~~

Bật OAuth2 Login trong chain:

~~~java
http
    .authorizeHttpRequests(authorize -> authorize
        .requestMatchers("/", "/assets/**").permitAll()
        .anyRequest().authenticated())
    .oauth2Login(Customizer.withDefaults());
~~~

Spring Security tạo các endpoint login/redirect theo cấu hình registration. Redirect URI phải khớp với cấu hình của identity provider và URL bên ngoài mà reverse proxy công bố. Trong container, kiểm tra forwarded headers, scheme HTTPS và host để callback URI được tạo đúng.

### Native integration cần kiểm thử luồng đầy đủ

Đừng chỉ kiểm tra trang login trả redirect. Hãy xác minh:

1. Authorization request được tạo với đúng client, scope và redirect URI.
2. Callback nhận authorization code.
3. Token endpoint được gọi và ID token được xác minh.
4. UserInfo endpoint được gọi nếu cấu hình yêu cầu.
5. User được ánh xạ thành principal/authorities mong đợi.
6. Session hoặc authorized client được lưu và dùng ở request tiếp theo.

Nếu dùng custom `OAuth2UserService`/`OidcUserService`, kiểm tra custom principal và các method được SpEL hoặc thư viện gọi qua reflection. Không đưa client secret hoặc token thật vào log/test fixture.

## 11. Ánh xạ danh tính thành principal nghiệp vụ

Trong một hệ thống nhiều tenant, principal có thể chứa user ID, tenant ID và permission đã chuẩn hóa. Có thể dùng custom `UserDetails` cho username/password hoặc custom `OAuth2User`/`OidcUser` cho federated login.

~~~java
public record ApplicationPrincipal(
        String userId,
        String tenantId,
        Set<String> permissions) {

    public boolean canManageTenant() {
        return permissions.contains("tenant:manage");
    }
}
~~~

Khi chuyển identity từ provider bên ngoài, chỉ lấy claim đã được xác minh và map sang model nội bộ. Không tin một header do client tự gửi như `X-User-Id` hoặc `X-Roles` trừ khi nó được đặt bởi một proxy đáng tin cậy với cơ chế xác thực và ranh giới mạng rõ ràng.

Nếu security expression gọi `principal.canManageTenant()`, hãy xác nhận kiểu principal được giữ và method có reflection hint cần thiết. Có thể đăng ký class bằng:

~~~java
@Configuration(proxyBeanMethods = false)
@RegisterReflectionForBinding(ApplicationPrincipal.class)
class PrincipalHintsConfiguration {
}
~~~

Nếu principal được bao bọc trong một custom `Authentication`, đăng ký cả class custom đó khi expression hoặc thư viện truy cập nó bằng reflection. Hints không thay thế việc kiểm tra nguồn gốc claim và quy tắc authorization.

## 12. Spring Security AOT tự xử lý những gì?

Spring Security tích hợp với Spring AOT và Native Image. Nhiều thành phần chuẩn như filter chain, authentication manager, request authorization, JWT Resource Server và method security hoạt động mà không cần người dùng tự đăng ký mọi class của framework.

Đối với method security, Spring Security AOT có thể:

- Quét các Spring beans trong ApplicationContext để tìm method có `@PreAuthorize` hoặc `@PostAuthorize`.
- Phân giải bean name được tham chiếu trong security expression.
- Đăng ký runtime hints phù hợp cho bean được tham chiếu.
- Với các tính năng return-object authorization được hỗ trợ trong phiên bản tương ứng, tiếp tục phân tích kiểu trả về để tìm security annotations liên quan.

Tuy nhiên, ứng dụng vẫn có thể cần hints cho custom `UserDetails`, custom `Authentication` hoặc kiểu mà SpEL gọi method động. Đây là lý do nên phân biệt:

| Thành phần | Hướng xử lý |
|---|---|
| Filter/authorization manager chuẩn | Dùng Spring Security integration; không tự đăng ký reflection hàng loạt |
| `SecurityFilterChain` cấu hình tĩnh | Để Spring AOT xử lý bean/configuration thông thường |
| Custom principal dùng trong SpEL | Đăng ký reflection binding hints khi cần |
| Custom method được gọi bằng reflection | Xác định member và đăng ký hint phù hợp |
| Public key/certificate/schema đọc từ classpath | Kiểm tra resource hints nếu không được framework tự nhận diện |
| Custom OAuth2 service hoặc converter | Kiểm thử native; thêm hints cho dynamic access thực tế |

## 13. Đăng ký Runtime Hints khi cần

Với custom principal thường dùng `@RegisterReflectionForBinding` là lựa chọn đơn giản và đúng với hướng dẫn Spring Security.

Nếu một thư viện custom gọi method cụ thể không thuộc binding, có thể dùng `RuntimeHintsRegistrar` để đăng ký invocation:

~~~java
public class SecurityRuntimeHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(RuntimeHints hints, ClassLoader classLoader) {
        Method method = ReflectionUtils.findMethod(
                ApplicationPrincipal.class, "canManageTenant");
        if (method != null) {
            hints.reflection().registerMethod(method, ExecutableMode.INVOKE);
        }
    }
}
~~~

Đăng ký registrar bằng `@ImportRuntimeHints` trên configuration:

~~~java
@Configuration(proxyBeanMethods = false)
@ImportRuntimeHints(SecurityRuntimeHints.class)
class SecurityHintsConfiguration {
}
~~~

Ví dụ này minh họa cách đăng ký method invocation hẹp. Trong một dự án cụ thể, kiểm tra API Spring Framework version đang dùng và xác định liệu `@RegisterReflectionForBinding` đã bao phủ use case chưa. Không thêm cả hai cơ chế cho cùng một access nếu không có lý do.

## 14. Kiểm thử request authorization và method security

Nên kiểm thử hai lớp authorization độc lập. Một endpoint có thể bị request filter từ chối trước khi method security chạy; ngược lại, request có thể vào controller nhưng service từ chối thao tác.

### Kiểm thử filter chain với MockMvc

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class InvoiceSecurityTests {

    @Autowired
    MockMvc mockMvc;

    @Test
    void unauthenticatedRequestIsRejected() throws Exception {
        mockMvc.perform(get("/api/invoices/42"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void authorizedJwtCanReadInvoice() throws Exception {
        mockMvc.perform(get("/api/invoices/42")
                .with(jwt().authorities(
                        new SimpleGrantedAuthority("invoice:read"))))
                .andExpect(status().isOk());
    }
}
~~~

Post processor `jwt()` từ Spring Security Test tạo Authentication giả lập cho test MVC. Nó kiểm tra request authorization và controller mapping, nhưng không kiểm tra việc decoder xác minh chữ ký JWT thật.

### Kiểm thử method security

~~~java
@SpringBootTest
class InvoiceMethodSecurityTests {

    @Autowired
    InvoiceService invoiceService;

    @Test
    @WithMockUser(authorities = "invoice:read")
    void readerCanLoadInvoice() {
        assertThat(invoiceService.findById("INV-100")).isNotNull();
    }

    @Test
    @WithMockUser(authorities = "invoice:write")
    void writerWithoutReadPermissionIsDenied() {
        assertThatThrownBy(() -> invoiceService.findById("INV-100"))
                .isInstanceOf(AccessDeniedException.class);
    }
}
~~~

Các test này xác minh proxy method security được áp dụng khi gọi qua Spring bean. Với custom principal, cần có test riêng dùng đúng principal type và security expression production.

## 15. Native integration tests cho identity flow

Native test cần xác minh những thứ mock test không thể chứng minh. Với Resource Server JWT, nên có test dùng token thật được ký bởi khóa test và JWK endpoint cục bộ:

- Token thiếu chữ ký hợp lệ bị từ chối.
- Token hết hạn bị từ chối.
- Issuer/audience sai bị từ chối theo policy.
- Token hợp lệ được chuyển thành Authentication.
- Claim roles/scopes được map thành authorities chính xác.
- Request được phép ở filter chain và method security.
- Token hợp lệ nhưng thiếu permission nhận 403 ở đúng lớp.

Với OIDC Login, dùng một identity provider giả lập trong integration test để kiểm tra authorization redirect, callback, token exchange và principal mapping. Không phụ thuộc identity provider công cộng trong test CI nếu có thể tránh.

### Chạy native tests

Nếu build đã cấu hình Native Build Tools và Spring AOT:

~~~bash
# Gradle
./gradlew nativeTest

# Maven profile đã cấu hình nativeTest
./mvnw test -PnativeTest
~~~

Tên profile/task phụ thuộc cấu hình project. Ngoài native test, nên build và chạy application executable cuối cùng trong container để kiểm tra network, TLS, session store, cookie, reverse proxy và environment variables.

### Test custom principal trong native

Nếu method security gọi `principal.isAdmin()`:

1. Chạy test JVM để xác nhận logic expression.
2. Đăng ký `CustomUserDetails` bằng `@RegisterReflectionForBinding`.
3. Build AOT/native.
4. Gọi method được bảo vệ với custom principal trong native executable.
5. Kiểm tra cả trường hợp được phép và bị từ chối.

Không chỉ kiểm tra build thành công. Lỗi SpEL reflection thường chỉ xuất hiện khi method security expression thực sự được đánh giá.

## 16. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Endpoint yêu cầu authentication dù đã permit | Request khớp chain khác hoặc chain order/matcher sai | Kiểm tra `@Order`, `securityMatcher`, matcher đầu tiên khớp |
| Custom filter chạy hai lần | Filter bean vừa được servlet container đăng ký vừa được thêm vào SecurityFilterChain | Tắt servlet registration nếu filter chỉ thuộc security chain |
| Filter không thấy principal | Filter đặt trước authentication filter hoặc request chưa authenticated | Đặt đúng vị trí theo sự kiện cần có |
| `@PreAuthorize` không chạy | Chưa bật `@EnableMethodSecurity`, method không gọi qua Spring proxy hoặc bean không được quản lý | Kiểm tra config, bean boundary và self-invocation |
| SpEL không tìm thấy method trên custom principal trong native | Thiếu reflection hints cho custom `UserDetails`/`Authentication` | Dùng `@RegisterReflectionForBinding` cho custom type |
| Role không khớp | JWT claim mapping và convention `ROLE_`/scope không thống nhất | Kiểm tra converter và dùng `hasRole`/`hasAuthority` đúng nghĩa |
| JWT hợp lệ trên JVM nhưng native không gọi được JWK endpoint | DNS/TLS/network/container configuration | Kiểm tra runtime connectivity, trust store, issuer/JWK URI |
| OIDC callback sai redirect URI | Reverse proxy/forwarded headers hoặc registration URI sai | Đồng bộ external URL và cấu hình forwarded headers |
| Native build pass nhưng custom auth flow lỗi | Test chưa đi qua custom principal, converter hoặc provider | Bổ sung native integration test cho đúng đường code |

## 17. Checklist trước khi phát hành

- [ ] Phân loại ứng dụng là Servlet hay WebFlux; dùng đúng loại security chain.
- [ ] Kiểm tra `SecurityFilterChain` order và matcher cho từng nhóm endpoint.
- [ ] Bật CSRF phù hợp với cách ứng dụng lưu credential (cookie/session hay bearer header).
- [ ] Kiểm tra session policy, CORS, logout và error handling.
- [ ] Đặt custom filter theo đúng vị trí trong authentication/authorization flow.
- [ ] Tránh đăng ký custom filter hai lần trong servlet container và security chain.
- [ ] Bật `@EnableMethodSecurity` nếu dùng method annotations.
- [ ] Kiểm tra method được gọi qua Spring proxy và không bị self-invocation bỏ qua.
- [ ] Chuẩn hóa role/authority giữa UserDetails, JWT claims và SpEL.
- [ ] Đăng ký hints cho custom UserDetails/Authentication được gọi qua SpEL khi cần.
- [ ] Kiểm thử JWT signature, issuer, expiry, audience và authority mapping.
- [ ] Kiểm thử OIDC callback/session nếu dùng OAuth2 Login.
- [ ] Quản lý client secret, signing key và credential bằng secret manager/environment.
- [ ] Chạy JVM tests, AOT/native tests và smoke test trên executable cuối cùng.
- [ ] Kiểm thử trong container với TLS, DNS, proxy, cookie và forwarded headers thực tế.

## 18. Bài tập tự kiểm tra

**Câu 1.** `FilterChainProxy` chọn `SecurityFilterChain` như thế nào khi có nhiều chain?

**Gợi ý:** xét theo thứ tự và chỉ dùng chain đầu tiên có matcher khớp.

**Câu 2.** Vì sao API stateless dùng bearer token có thể tắt CSRF trong ví dụ, còn web login dùng cookie/session thường cần giữ CSRF?

**Gợi ý:** CSRF khai thác credential được trình duyệt tự động gửi như cookie; bearer token do client chủ động đặt trong header có threat model khác. Cần đánh giá đúng cách credential được lưu và gửi.

**Câu 3.** `@EnableMethodSecurity` có tự được bật bởi Spring Boot Starter Security không?

**Gợi ý:** không. Phải bật rõ ràng nếu muốn dùng `@PreAuthorize`/`@PostAuthorize`.

**Câu 4.** Vì sao custom `UserDetails` có thể cần reflection hints trong Native Image?

**Gợi ý:** SpEL có thể dùng reflection để gọi method như `principal.isAdmin()`; class/member cần được đăng ký.

**Câu 5.** `@RegisterReflectionForBinding` có cần áp dụng cho mọi class trong Spring Security không?

**Gợi ý:** không. Spring Security đã hỗ trợ Native Image; chỉ bổ sung hints cho custom types/dynamic access chưa được framework suy ra.

**Câu 6.** Test dùng `jwt()` trong MockMvc có chứng minh JWT decoder xác minh chữ ký thật không?

**Gợi ý:** không. Nó tạo Authentication giả lập; cần integration test với token ký thật và JWK/decoder.

**Câu 7.** Nếu dùng WebFlux, có nên đọc SecurityContext trực tiếp qua `SecurityContextHolder` trong custom reactive filter không?

**Gợi ý:** không nên. Reactive stack lưu security context trong Reactor Context; dùng reactive security APIs phù hợp.

## 19. Tài liệu tham khảo

- [Spring Security — GraalVM Native Image Support](https://docs.spring.io/spring-security/reference/native-image/index.html): tổng quan hỗ trợ Native Image và các trường hợp cần hints bổ sung.
- [Spring Security — Method Security in GraalVM Native Image](https://docs.spring.io/spring-security/reference/native-image/method-security.html): custom `UserDetails`/`Authentication`, SpEL và `@RegisterReflectionForBinding`.
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@EnableMethodSecurity`, `@PreAuthorize`, `@PostAuthorize` và Spring Security AOT.
- [Spring Security — Servlet Architecture](https://docs.spring.io/spring-security/reference/servlet/architecture.html): `FilterChainProxy`, thứ tự filter và cách thêm custom filter.
- [Spring Security — OAuth2](https://docs.spring.io/spring-security/reference/servlet/oauth2/): Resource Server, OAuth2 Client, OAuth2 Login và OIDC.
- [Spring Boot — Spring Security](https://docs.spring.io/spring-boot/reference/web/spring-security.html): auto-configuration, custom `SecurityFilterChain`, MVC và WebFlux security.
- [Spring Framework — Ahead-of-Time Optimizations](https://docs.spring.io/spring-framework/reference/core/aot.html): Runtime Hints, reflection, resources và proxy metadata.

**Ghi nhớ:** Spring Security có hỗ trợ Native Image cho các tính năng chuẩn. Hãy cấu hình filter chain và method authorization bằng các API Spring Security thông thường; tập trung kiểm tra những custom principal, Authentication, expression và filter có truy cập động. Kết hợp JVM security tests với native integration tests cho JWT/OIDC và method authorization để xác nhận cả bean topology, reflection hints lẫn hành vi xác thực/ủy quyền trong executable cuối cùng.
