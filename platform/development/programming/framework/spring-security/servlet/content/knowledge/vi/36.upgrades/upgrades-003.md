# Từ WebSecurityConfigurerAdapter sang các bean cấu hình

**Module:** Spring Security – Servlet  
**Chủ đề cha:** Nâng cấp

## 1. Vì sao phải chuyển đổi?

Trong các dự án Spring Security Servlet đời cũ, cấu hình bảo mật thường được gom trong một class kế thừa `WebSecurityConfigurerAdapter`. Class này override các phương thức `configure(HttpSecurity)`, `configure(WebSecurity)` và `configure(AuthenticationManagerBuilder)`. Cách tiếp cận đó từng phổ biến nhưng khiến nhiều trách nhiệm khác nhau bị gắn vào một lớp có vòng đời và thứ tự cấu hình khó nhìn thấy.

Từ **Spring Security 5.7**, `WebSecurityConfigurerAdapter` được deprecate; trong **Spring Security 6** nó đã bị loại bỏ. Spring Boot 3 dùng Spring Security 6 và hệ sinh thái Jakarta EE, nên một dự án nâng cấp từ Boot 2/Security 5 cần chuyển sang **khai báo bean cấu hình theo thành phần**.

Không chỉ là đổi tên class. Bản nâng cấp phải bảo toàn hành vi thực sự:

- Đường dẫn nào được phép công khai, đường dẫn nào cần authentication và quyền cụ thể?
- API dùng HTTP Basic, Bearer token hay một cơ chế khác? Web browser dùng form login hay OAuth2 Login?
- CSRF vẫn được áp dụng cho request thay đổi trạng thái theo đúng threat model chưa?
- User và password được xác minh từ nguồn nào? `PasswordEncoder` có tương thích hash hiện hữu không?
- `AuthenticationProvider`/ `AuthenticationManager` có custom logic cần chuyển đổi không?
- Cấu hình `web.ignoring()`, URL login/logout, request cache, CORS, headers, session, exception handling có thay đổi ý nghĩa không?
- Method security `@PreAuthorize` còn hoạt động sau khi thay annotation cấu hình không?
- Nếu có nhiều filter chain, `@Order` và `securityMatcher` đã bao phủ tất cả endpoint chưa?

**Mục tiêu bài:** chuyển cấu hình legacy sang bean `SecurityFilterChain`, `UserDetailsService`, `PasswordEncoder`, `AuthenticationProvider`/ `AuthenticationManager` và `WebSecurityCustomizer` khi thật sự cần; hiểu các khác biệt của API; sau đó viết **kiểm thử HTTP và method security** để chứng minh hành vi không bị nới quyền hoặc hỏng đăng nhập.

> Phạm vi: Spring Security **Servlet** với `HttpSecurity` và `SecurityFilterChain`, không phải WebFlux `ServerHttpSecurity` và `SecurityWebFilterChain`.

## 2. Bản đồ chuyển đổi: kiểu kế thừa sang kiểu composition

| Cấu hình cũ | Cấu hình mới | Ý nghĩa |
| --- | --- | --- |
| `extends WebSecurityConfigurerAdapter` | Một hoặc nhiều `@Bean SecurityFilterChain` | Mỗi bean mô tả một security filter chain và policy. |
| Override `configure(HttpSecurity http)` | `SecurityFilterChain filterChain(HttpSecurity http)` + `return http.build()` | Định nghĩa HTTP security bằng composition. |
| `http.authorizeRequests()` | `http.authorizeHttpRequests(auth -> ...)` | DSL authorization dựa trên `AuthorizationManager` hiện đại. |
| `antMatchers(...)`, `mvcMatchers(...)` cũ | `requestMatchers(...)` và matcher thích hợp | Xác định path/method; cần xét MVC/servlet mapping thực tế. |
| `antMatchers(...).hasRole("ADMIN")` | `requestMatchers(...).hasRole("ADMIN")` | Hợp đồng role vẫn cần kiểm tra prefix `ROLE_`. |
| Override `configure(AuthenticationManagerBuilder)` | `UserDetailsService`, `PasswordEncoder`, `AuthenticationProvider` hoặc `AuthenticationManager` bean | Authentication là trách nhiệm riêng, không phải override adapter. |
| Override `configure(WebSecurity web)` | `WebSecurityCustomizer` bean nếu thật sự phải bypass | `web.ignoring()` bỏ qua filter chain; thường ưu tiên `permitAll()`. |
| `@EnableGlobalMethodSecurity(prePostEnabled = true)` | `@EnableMethodSecurity` | Bật `@PreAuthorize`/`@PostAuthorize` theo API mới. |
| `WebSecurityConfigurerAdapter#authenticationManagerBean()` | Chỉ khi cần: `AuthenticationConfiguration#getAuthenticationManager()` hoặc bean manager riêng | Không công bố một global manager chỉ theo thói quen. |
| `javax.servlet.*` ở mã Boot 2 | `jakarta.servlet.*` trong Boot 3 | Chuyển namespace Servlet API; tránh ghép adapter cũ không tương thích. |
| `http.and().formLogin().and()` kiểu chain cũ | Lambda DSL `http.formLogin(Customizer.withDefaults())` | Phân nhóm config rõ ràng, dễ đọc và nâng cấp. |
| `@Order` trên nhiều adapter | `@Order` trên các `SecurityFilterChain` bean | Ưu tiên chain chuyên biệt trước chain tổng quát. |

**Không phải phép thay thế cơ học 1:1.** Cấu hình cũ có thể đã sử dụng hành vi mặc định, filter tùy chỉnh hoặc provider ẩn sau adapter. Cần đọc threat model của ứng dụng, viết bảng endpoint/role/method rồi đối chiếu bằng test sau nâng cấp.

## 3. Ví dụ cấu hình cũ — chỉ để nhận diện, không chạy trên Spring Security 6

Sau đây là phong cách **Spring Security 5 đời cũ**. Không copy đoạn này vào ứng dụng Boot 3; các API như `WebSecurityConfigurerAdapter` và `antMatchers` không còn là cách cấu hình hợp lệ của Spring Security 6.

~~~java
// LEGACY: minh họa cú pháp cũ, KHÔNG thuộc dự án runnable ở dưới.
@Configuration
@EnableWebSecurity
public class LegacySecurityConfig extends WebSecurityConfigurerAdapter {

    @Override
    protected void configure(HttpSecurity http) throws Exception {
        http
            .authorizeRequests()
                .antMatchers("/", "/public").permitAll()
                .antMatchers("/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated()
            .and()
            .formLogin()
            .and()
            .httpBasic();
    }

    @Override
    protected void configure(AuthenticationManagerBuilder auth)
            throws Exception {
        auth.inMemoryAuthentication()
            .withUser("alice")
            .password("{noop}training-only")
            .roles("USER");
    }

    @Override
    public void configure(WebSecurity web) {
        web.ignoring().antMatchers("/assets/**");
    }
}
~~~

Các trách nhiệm đang đan xen: HTTP authorization + authentication source + bypass filter. Bản mới tách chúng thành các bean có thể inject và test riêng.

**Không mang cấu hình password `{noop}` vào production.** Nó là kiểu password encoder không hash để demo lịch sử; hệ thống thật cần hash thích hợp, migration hash cũ có kiểm chứng và quản lý secret. Dùng `PasswordEncoderFactories.createDelegatingPasswordEncoder()` cho ví dụ mới để tránh bỏ qua encoding.

### 3.1. Vì sao adapter bị thay thế?

Bean composition giúp:

- Tạo **nhiều chain có phạm vi rõ ràng**, mỗi chain có `securityMatcher`, `@Order` và policy riêng.
- Tách nguồn user, cơ chế hash, provider và security filter config.
- Đơn giản hóa kiểm thử bằng cách inject `SecurityFilterChain`, `AuthenticationManager`/provider hoặc service, thay vì phụ thuộc inheritance hooks.
- Hỗ trợ thiết kế phù hợp với `authorizeHttpRequests`, method security và lambda DSL.
- Giảm tình trạng cấu hình nằm phân tán giữa override và auto-configuration nhưng hiệu lực khó quan sát.

Tuy nhiên, tạo bean không tự làm ứng dụng an toàn. Nếu bạn quên fallback chain, dùng `permitAll` quá rộng hoặc disabled CSRF theo thói quen, rủi ro vẫn còn.

## 4. SecurityFilterChain bean thay configure(HttpSecurity)

Một ví dụ tối thiểu với **Java 17 / Spring Security 6**:

~~~java
// Trích đoạn trong @Configuration; cần UserDetailsService/provider thích hợp.
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
    http.authorizeHttpRequests(auth -> auth
            .requestMatchers("/", "/health").permitAll()
            .requestMatchers("/admin/**").hasRole("ADMIN")
            .anyRequest().authenticated()
        )
        .formLogin(Customizer.withDefaults());

    return http.build();
}
~~~

Đây là **snippet để giải thích API**, không phải project đầy đủ. `HttpSecurity` được Spring đưa vào phương thức `@Bean`; sau khi cấu hình, gọi `http.build()` để tạo `SecurityFilterChain`. Không khởi tạo `new HttpSecurity(...)` bằng tay.

### 4.1. authorizeHttpRequests và thứ tự rule

Trong một chain, các matcher thường được xét theo **thứ tự đã khai báo**, rule đầu tiên khớp quyết định policy. Nên:

1. Đặt endpoint public cụ thể trước.
2. Đặt path cần role/scope cụ thể tiếp theo.
3. Đặt catch-all `anyRequest().authenticated()` hoặc `anyRequest().denyAll()` ở cuối theo chính sách đã phê duyệt.

Ví dụ:

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/reports").hasAuthority("REPORT_READ")
    .requestMatchers(HttpMethod.POST, "/reports").hasAuthority("REPORT_WRITE")
    .anyRequest().denyAll()
)
~~~

Nếu chỉ cho phép GET mà POST chưa có quy tắc, `denyAll` giúp POST **không tự được cấp quyền**. Đừng chuyển legacy `anyRequest().authenticated()` thành `permitAll()` chỉ để test ít lỗi hơn: đó là thay đổi bảo mật lớn.

### 4.2. securityMatcher và requestMatchers không giống nhau

Với nhiều chain:

~~~java
@Bean
@Order(1)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    http.securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/public").permitAll()
            .anyRequest().authenticated()
        )
        .httpBasic(Customizer.withDefaults());
    return http.build();
}
~~~

- `securityMatcher("/api/**")` quy định **phạm vi chain**.
- `requestMatchers("/api/public")` quy định **rule trong chain đã được chọn**.
- `anyRequest()` cũng chỉ được áp dụng cho request **đã vào chain**.

Nếu không có chain khác, `/web/private` không khớp `/api/**` có thể đi qua ứng dụng **không được Spring Security filters bảo vệ**. Với nhiều chain, đặt chain chuyên biệt trước và có **catch-all chain** cuối.

### 4.3. Không mặc định disable CSRF khi chuyển đổi

Nhiều hướng dẫn cũ viết:

~~~java
// Chỉ là anti-pattern nếu dùng cho form/session mà không đánh giá.
http.csrf(csrf -> csrf.disable());
~~~

Nếu ứng dụng dùng browser + session cookie, CSRF protection là cần thiết cho các request đổi trạng thái. Khi đổi sang bean mới, **giữ nguyên CSRF đã hoạt động hoặc điều chỉnh theo threat model thật**. Một API chỉ nhận bearer token ở Authorization header và không dựa vào browser-auto credentials có thể có đánh giá khác; **HTTP Basic** thậm chí có thể được browser gửi tự động, không nên disable CSRF chỉ vì endpoint có chữ API.

## 5. Authentication: tách UserDetailsService và PasswordEncoder

Trong cấu hình mới, cách dễ hiểu cho ứng dụng có username/password là đăng ký bean:

~~~java
@Bean
PasswordEncoder passwordEncoder() {
    return PasswordEncoderFactories.createDelegatingPasswordEncoder();
}

@Bean
UserDetailsService userDetailsService(PasswordEncoder encoder) {
    return new InMemoryUserDetailsManager(
        User.withUsername("alice")
            .password(encoder.encode("training-only"))
            .authorities("ROLE_USER")
            .build()
    );
}
~~~

Đây là **snippet**, không phải nơi lưu user production. Khi có đúng nguồn `UserDetailsService`/provider thích hợp, Spring Security có thể cấu hình cơ chế authentication từ các bean được đăng ký. Nếu ứng dụng có nhiều provider/custom manager, phải kiểm tra cách `AuthenticationManager` được xây dựng và thứ tự provider, không mặc định một bean `UserDetailsService` sẽ ghi đè logic bảo mật khác.

### 5.1. PasswordEncoder và migration hash

- `PasswordEncoder#encode` tạo representation để lưu.
- `matches(raw, encoded)` dùng khi xác minh password; không tự so sánh raw strings.
- `DelegatingPasswordEncoder` hỗ trợ identifier prefix trong encoded value, ví dụ dạng `{bcrypt}...`.
- Nếu DB cũ lưu hash không có prefix hoặc dùng thuật toán cũ, nâng cấp cần **kế hoạch tương thích/rehash** có kiểm thử, không tự thêm `{noop}` vào mọi password.
- Không log raw password, encoded hash từ người dùng thật hoặc credential trong request.

**Lỗi phổ biến:** sau migration mọi đăng nhập đều 401/redirect về `/login?error` do bean `PasswordEncoder` không khớp định dạng hash cũ. Kiểm tra encoder và dữ liệu đã encode thay vì mở public endpoint.

### 5.2. Authority và role prefix

| Cấu hình | Authority được mong đợi theo convention mặc định |
| --- | --- |
| `hasRole("ADMIN")` | `ROLE_ADMIN` |
| `hasAuthority("ROLE_ADMIN")` | `ROLE_ADMIN` |
| `hasAuthority("REPORT_READ")` | `REPORT_READ` |
| `hasAuthority("SCOPE_orders.read")` | `SCOPE_orders.read` |

Nếu user được tạo bằng `.authorities("ADMIN")`, `hasRole("ADMIN")` có thể trả 403 vì thiếu prefix `ROLE_`. Không đổi rule thành `permitAll`; chuẩn hóa authority mapper hoặc `hasAuthority` cho đúng hợp đồng.

**Lưu ý:** trong `User.UserBuilder`, không dựa vào việc gọi `.roles(...)` sau `.authorities(...)` để tự động cộng dồn cả hai danh sách nếu chưa kiểm tra API. Ví dụ hoàn chỉnh bên dưới khai báo **toàn bộ authorities cần có** bằng một lời gọi `.authorities(...)`.

## 6. Khi nào phải dùng AuthenticationProvider hoặc AuthenticationManager bean?

Không phải dự án nào bỏ `WebSecurityConfigurerAdapter` cũng cần tự tạo `AuthenticationManager`.

### 6.1. Trường hợp UserDetailsService + PasswordEncoder đã đủ

Nếu dùng form login/HTTP Basic với `DaoAuthenticationProvider` do Spring Security cấu hình phù hợp, một `UserDetailsService` và `PasswordEncoder` bean thường là đủ. Các filter nhận `AuthenticationManager` qua hạ tầng Security thay vì controller tự gọi password check.

**Không** viết một REST controller nhận password và tự so sánh nó với chuỗi trong DB chỉ để thay `configure(AuthenticationManagerBuilder)`.

### 6.2. Có custom provider/LDAP/external system

Khi hệ thống có xác thực riêng (ví dụ xác thực với backend tương thích `AuthenticationProvider`), khai báo provider và tích hợp rõ vào Spring Security:

~~~java
// Snippet CHỈ MINH HỌA cho Spring Security 6.x có API tương ứng,
// không thêm vào dự án demo bên dưới.
@Bean
AuthenticationProvider daoAuthenticationProvider(
        UserDetailsService users, PasswordEncoder encoder) {
    DaoAuthenticationProvider provider = new DaoAuthenticationProvider();
    provider.setUserDetailsService(users);
    provider.setPasswordEncoder(encoder);
    return provider;
}
~~~

Các API constructor/setter của `DaoAuthenticationProvider` có thể thay đổi hoặc deprecate theo release mới hơn; kiểm tra JavaDoc của **phiên bản đang triển khai** trước khi copy. Với provider tùy biến khác, phải trả `Authentication` đã xác thực đúng kiểu và authorities đáng tin, ném `AuthenticationException` khi credential sai, không fail open.

Đừng đồng thời đăng ký nhiều provider thừa chỉ để “chắc chắn login được”. Thứ tự/provider selection và `supports` quyết định kết quả; cần test nhánh thành công, thất bại, user disabled/locked, password sai và backend unavailable.

### 6.3. Chỉ expose AuthenticationManager khi cần inject

Nếu một thành phần ứng dụng **thực sự** phải inject global manager, có thể dùng pattern:

~~~java
// Snippet optional: không thêm vào demo bên dưới nếu không cần.
@Bean
AuthenticationManager authenticationManager(
        AuthenticationConfiguration configuration) throws Exception {
    return configuration.getAuthenticationManager();
}
~~~

Cần import `org.springframework.security.config.annotation.authentication.configuration.AuthenticationConfiguration` và `org.springframework.security.authentication.AuthenticationManager`.

**Không dùng pattern này như bảo đảm mọi dự án có manager thích hợp:** phải có provider/config hợp lệ và xem tác động của nhiều chain, custom provider, manager per-chain. Trong đa số ứng dụng form login thông thường, app không cần trực tiếp inject manager vào controller.

### 6.4. Khi nào dùng http.authenticationProvider?

Nếu provider chỉ dành cho một security chain, có thể gắn qua cấu hình `HttpSecurity` phù hợp:

~~~java
// Snippet nằm trong quá trình cấu hình một HttpSecurity.
http.authenticationProvider(customProvider);
~~~

Điều này không tương đương mặc định với việc đưa provider vào một global manager cho mọi chain. Cần xác định provider được dùng ở đâu và kiểm thử từng authentication mechanism.

## 7. WebSecurityCustomizer: đừng nhầm ignoring với permitAll

Cấu hình cũ thường có:

~~~java
@Override
public void configure(WebSecurity web) {
    web.ignoring().antMatchers("/css/**", "/js/**");
}
~~~

Để biểu đạt bypass trong cấu hình dựa trên bean, API tương ứng có dạng:

~~~java
// Snippet minh họa, KHÔNG khuyến nghị bật mặc định.
@Bean
WebSecurityCustomizer webSecurityCustomizer() {
    return web -> web.ignoring().requestMatchers("/legacy-static/**");
}
~~~

Nhưng **`web.ignoring()` khiến request không đi qua Spring Security filter chain**, nên có thể mất security headers, security context handling, audit/security filters và những biện pháp áp dụng ở filter chain.

Với tài nguyên public thuộc ứng dụng, thường nên:

~~~java
// Bên trong authorizeHttpRequests của chain bao phủ path:
.requestMatchers("/css/**", "/js/**", "/images/**").permitAll()
~~~

Khi đó request vẫn đi qua Spring Security filters nhưng không cần authentication theo rule.

**Khác biệt quan trọng:**

| Điều kiện | `permitAll()` | `web.ignoring()` |
| --- | --- | --- |
| Request có đi qua `FilterChainProxy` Spring Security? | Có | Không, đối với matcher bị ignore |
| Authorization yêu cầu login? | Không tại rule permit | Không qua Spring Security |
| Các security headers/filter khác có cơ hội chạy? | Có, tùy chain | Không chạy filter Spring Security cho request ignored |
| Dùng cho endpoint động/nhạy cảm? | Chỉ khi public thật sự | Tránh; có thể tạo bypass nghiêm trọng |
| Thích hợp mặc định cho static assets? | Thường nên chọn | Chỉ cho ngoại lệ được đánh giá |

**Tuyệt đối không dùng** `web.ignoring().requestMatchers("/api/**")` như cách khắc phục 401/403 cho API. Nó có thể làm toàn bộ API bỏ qua Spring Security.

## 8. Nâng cấp method security

Trong code cũ:

~~~java
// Legacy annotation.
@EnableGlobalMethodSecurity(prePostEnabled = true)
~~~

Trong Spring Security 6, thường dùng:

~~~java
// Trên @Configuration hoặc application configuration.
@EnableMethodSecurity
~~~

`@EnableMethodSecurity` bật xử lý các annotation như `@PreAuthorize` và `@PostAuthorize` với cấu hình mặc định phù hợp. Tuy nhiên, **phải gọi method qua Spring-managed bean/proxy**; nếu test dùng `new SomeService()`, `@PreAuthorize` không được Spring intercept. Self-invocation trong cùng bean cũng có thể bypass proxy-based method security.

Ví dụ:

~~~java
@Service
public class AdminReportService {
    @PreAuthorize("hasRole('ADMIN')")
    public String internalReport() {
        return "admin-report";
    }
}
~~~

Đoạn trên là **ví dụ class riêng cần import tương ứng**; dự án hoàn chỉnh ở mục 9 sẽ đưa class này thành file đầy đủ.

**Không được coi URL authorization đủ thay cho method/resource authorization**. Nếu service đọc object theo tenant, cần kiểm tra ownership/tenant tương ứng; `hasRole` chỉ kiểm tra authority, không tự giới hạn bản ghi.

## 9. Dự án chạy được: Spring Boot 3.3.5 + Java 17 + bean-based config

Để có thể so sánh một hệ thống có API và form login, ta triển khai **hai SecurityFilterChain**:

- `@Order(1)` cho `/api/**`: HTTP Basic, API public hoặc cần authority `REPORT_READ`/`REPORT_WRITE`.
- `@Order(2)` cho phần còn lại: form login, user profile, admin page, POST web notes cần `ROLE_USER`, fallback `denyAll`.
- Spring Security **CSRF mặc định vẫn bật** cho POST. Đây là chủ đích để giữ an toàn cho browser/cookie và chứng minh migration không xóa CSRF vì convenience.

User in-memory và các response nhỏ chỉ dành cho demo. Không sử dụng tài khoản/mật khẩu hard-code trong production; dùng repository/IdP và secret management phù hợp.

### 9.1. Cấu trúc

~~~text
bean-security-migration/
├── pom.xml
└── src/
    ├── main/
    │   └── java/demo/
    │       ├── MigrationApplication.java
    │       ├── SecurityConfig.java
    │       ├── MigrationController.java
    │       └── AdminReportService.java
    └── test/
        └── java/demo/
            ├── MigrationHttpSecurityTests.java
            └── MigrationMethodSecurityTests.java
~~~

### 9.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>bean-security-migration</artifactId>
    <version>1.0.0</version>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
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

Dùng `spring-boot-starter-security` cùng BOM của Boot để quản lý phiên bản Spring Security modules. `spring-security-test` cần cho MockMvc `csrf()`, `httpBasic()`, `user()` và `@WithMockUser`.

### 9.3. src/main/java/demo/MigrationApplication.java

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MigrationApplication {
    public static void main(String[] args) {
        SpringApplication.run(MigrationApplication.class, args);
    }
}
~~~

### 9.4. src/main/java/demo/SecurityConfig.java

~~~java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        // DEMO ONLY: không đưa mật khẩu cố định vào production.
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoder.encode("demo-only"))
                .authorities("ROLE_USER", "REPORT_READ")
                .build(),
            User.withUsername("writer")
                .password(encoder.encode("demo-only"))
                .authorities("REPORT_WRITE")
                .build(),
            User.withUsername("admin")
                .password(encoder.encode("demo-only"))
                .authorities(
                    "ROLE_USER", "ROLE_ADMIN", "REPORT_READ")
                .build(),
            User.withUsername("limited")
                .password(encoder.encode("demo-only"))
                .authorities("ROLE_USER")
                .build()
        );
    }

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/public")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/api/reports")
                    .hasAuthority("REPORT_READ")
                .requestMatchers(HttpMethod.POST, "/api/reports")
                    .hasAuthority("REPORT_WRITE")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults());

        // Ví dụ cố tình giữ CSRF cho POST HTTP Basic.
        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain webAndFallback(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/", "/health", "/error")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/web/profile")
                    .authenticated()
                .requestMatchers(HttpMethod.GET, "/web/admin")
                    .hasRole("ADMIN")
                .requestMatchers(HttpMethod.POST, "/web/notes")
                    .hasRole("USER")
                .anyRequest().denyAll()
            )
            .formLogin(form -> form
                .defaultSuccessUrl("/web/profile", true)
                .permitAll()
            )
            .logout(logout -> logout.permitAll());

        // Chain này không có securityMatcher => catch-all.
        return http.build();
    }
}
~~~

**Giải thích migration ở file này:**

- Không còn `extends WebSecurityConfigurerAdapter` và không override `configure`.
- Bảo mật API và web được tạo từ **hai bean `SecurityFilterChain`**, phân biệt bằng `@Order` và `securityMatcher`.
- `apiChain` được xét trước, `/api/reports` không rơi vào web form-login chain. API anonymous dùng **HTTP Basic challenge** thay vì redirect đến `/login`.
- Chain web không giới hạn matcher nên là catch-all cho URL còn lại. `anyRequest().denyAll()` giúp endpoint chưa khai báo không tự public.
- `UserDetailsService` cung cấp bốn user cho demo; `PasswordEncoder` quản lý password hash.
- `@EnableMethodSecurity` thay annotation legacy và cho phép `@PreAuthorize` ở service.
- `hasRole("ADMIN")` cần `ROLE_ADMIN`; user `admin` đã được gán authority đó.
- Đối với form login, `.permitAll()` trong formLogin mở đúng endpoint đăng nhập do framework tạo; không phải mở `anyRequest().permitAll()`.
- Khi CSRF bật, POST `/web/notes` và `/api/reports` cần CSRF token. Trong thực tế policy API có thể khác nếu sử dụng bearer token stateless; đánh giá từng chain.

### 9.5. src/main/java/demo/AdminReportService.java

~~~java
package demo;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class AdminReportService {

    @PreAuthorize("hasRole('ADMIN')")
    public String adminLabel() {
        return "admin-only";
    }
}
~~~

Method security là lớp kiểm soát bổ sung. `@EnableMethodSecurity` làm phương thức này được kiểm tra khi gọi qua Spring-managed bean/proxy.

### 9.6. src/main/java/demo/MigrationController.java

~~~java
package demo;

import java.util.Map;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class MigrationController {

    private final AdminReportService adminService;

    public MigrationController(AdminReportService adminService) {
        this.adminService = adminService;
    }

    @GetMapping("/")
    Map<String, String> home() {
        return Map.of("message", "public-home");
    }

    @GetMapping("/health")
    Map<String, String> health() {
        return Map.of("status", "up");
    }

    @GetMapping("/api/public")
    Map<String, String> publicApi() {
        return Map.of("message", "public-api");
    }

    @GetMapping("/api/reports")
    Map<String, String> reports() {
        return Map.of("report", "read");
    }

    @PostMapping("/api/reports")
    Map<String, String> createReport() {
        return Map.of("report", "created");
    }

    @GetMapping("/web/profile")
    Map<String, String> profile(Authentication authentication) {
        return Map.of("user", authentication.getName());
    }

    @GetMapping("/web/admin")
    Map<String, String> admin() {
        return Map.of("message", adminService.adminLabel());
    }

    @PostMapping("/web/notes")
    Map<String, String> notes() {
        return Map.of("message", "saved");
    }

    // Có controller nhưng không nằm trong allowlist của catch-all.
    @GetMapping("/shadow")
    Map<String, String> shadow() {
        return Map.of("secret", "never-public");
    }
}
~~~

Controller demo không lưu dữ liệu. Trong production, endpoint `POST` phải có DTO/validation, chống mass assignment và kiểm tra quyền theo object/tenant. Cấu hình `@PreAuthorize` ở service `adminLabel()` không thay tất cả kiểm tra ownership nghiệp vụ.

### 9.7. Chạy ứng dụng

Trong thư mục chứa `pom.xml`:

~~~bash
mvn spring-boot:run
~~~

Thử endpoint public:

~~~bash
curl -i http://localhost:8080/api/public
curl -i http://localhost:8080/health
~~~

Kỳ vọng trả HTTP 200 với JSON tương ứng.

Thử API cần authentication:

~~~bash
curl -i http://localhost:8080/api/reports

curl -i -u alice:demo-only \
  http://localhost:8080/api/reports

curl -i -u writer:demo-only \
  http://localhost:8080/api/reports
~~~

Kỳ vọng: **401**, **200**, **403** lần lượt. Basic credential chỉ để thực hành trên localhost; production phải dùng HTTPS và không đưa password thật vào lệnh có thể bị ghi shell history.

Thử form-login web route:

~~~bash
curl -i http://localhost:8080/web/profile
~~~

Kỳ vọng response 302 có `Location` tới `/login`. Đừng dùng `curl -L` khi cần quan sát redirect đầu tiên. Browser có thể vào `http://localhost:8080/login`, dùng user/password demo để xác thực, rồi vào profile.

### 9.8. Vì sao không đưa WebSecurityCustomizer vào file runnable?

Mục tiêu demo là giữ Spring Security filters trên cả public endpoint. Với `permitAll()`, request vẫn đi qua chain. Một `WebSecurityCustomizer` thật sự không cần thiết nên được trình bày như **snippet optional** ở mục 7. Nếu cố thêm để đủ số bean, dễ tạo thói quen ignore quá mức.

Tương tự, không thêm `AuthenticationManager` bean chỉ để “đủ bộ”. Với demo này, `UserDetailsService` và `PasswordEncoder` cùng cơ chế Basic/form login đã đủ để tạo authentication flow phù hợp. Chính sách thay đổi authentication provider phải được kiểm thử riêng.

## 10. Regression tests: chứng minh không thay đổi hành vi khi bỏ adapter

### 10.1. src/test/java/demo/MigrationHttpSecurityTests.java

~~~java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class MigrationHttpSecurityTests {

    @Autowired
    MockMvc mvc;

    @Test
    void publicApiIsAccessibleWithoutLogin() throws Exception {
        mvc.perform(get("/api/public"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.message").value("public-api"));
    }

    @Test
    void apiAnonymousGetsBasic401NotWebRedirect() throws Exception {
        mvc.perform(get("/api/reports"))
            .andExpect(status().isUnauthorized())
            .andExpect(header().string(
                HttpHeaders.WWW_AUTHENTICATE, containsString("Basic")));
    }

    @Test
    void incorrectBasicPasswordIsRejected() throws Exception {
        mvc.perform(get("/api/reports")
                .with(httpBasic("alice", "wrong")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void validBasicUserCanRead() throws Exception {
        mvc.perform(get("/api/reports")
                .with(httpBasic("alice", "demo-only")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.report").value("read"));
    }

    @Test
    void authenticatedWithoutReadAuthorityIsForbidden()
            throws Exception {
        mvc.perform(get("/api/reports")
                .with(user("writer").authorities(
                    new SimpleGrantedAuthority("REPORT_WRITE")
                )))
            .andExpect(status().isForbidden());
    }

    @Test
    void postWithoutCsrfIsForbiddenEvenForWriter()
            throws Exception {
        mvc.perform(post("/api/reports")
                .with(user("writer").authorities(
                    new SimpleGrantedAuthority("REPORT_WRITE")
                )))
            .andExpect(status().isForbidden());
    }

    @Test
    void postWithCsrfButNoWriteAuthorityIsForbidden()
            throws Exception {
        mvc.perform(post("/api/reports")
                .with(user("alice").authorities(
                    new SimpleGrantedAuthority("REPORT_READ")
                ))
                .with(csrf()))
            .andExpect(status().isForbidden());
    }

    @Test
    void postWithCsrfAndWriteAuthoritySucceeds()
            throws Exception {
        mvc.perform(post("/api/reports")
                .with(user("writer").authorities(
                    new SimpleGrantedAuthority("REPORT_WRITE")
                ))
                .with(csrf()))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.report").value("created"));
    }

    @Test
    void webAnonymousGets302LoginRedirect() throws Exception {
        mvc.perform(get("/web/profile"))
            .andExpect(status().isFound())
            .andExpect(header().string(
                HttpHeaders.LOCATION, containsString("/login")));
    }

    @Test
    void webUserCanReadOwnPrincipal() throws Exception {
        mvc.perform(get("/web/profile")
                .with(user("alice").roles("USER")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.user").value("alice"));
    }

    @Test
    void normalUserCannotVisitWebAdmin() throws Exception {
        mvc.perform(get("/web/admin")
                .with(user("alice").roles("USER")))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminRoleAllowsAdminPage() throws Exception {
        mvc.perform(get("/web/admin")
                .with(user("admin").roles("ADMIN")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.message").value("admin-only"));
    }

    @Test
    void webMutationNeedsCsrf() throws Exception {
        mvc.perform(post("/web/notes")
                .with(user("alice").roles("USER")))
            .andExpect(status().isForbidden());
    }

    @Test
    void webMutationWithRoleAndCsrfSucceeds() throws Exception {
        mvc.perform(post("/web/notes")
                .with(user("alice").roles("USER"))
                .with(csrf()))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.message").value("saved"));
    }

    @Test
    void loginWorksWithCsrfAndRedirectsToConfiguredTarget()
            throws Exception {
        mvc.perform(post("/login")
                .with(csrf())
                .param("username", "alice")
                .param("password", "demo-only"))
            .andExpect(status().isFound())
            .andExpect(redirectedUrl("/web/profile"));
    }

    @Test
    void unlistedMappedPathIsBlockedByCatchAll() throws Exception {
        mvc.perform(get("/shadow")
                .with(user("alice").roles("USER")))
            .andExpect(status().isForbidden());
    }

    @Test
    void unknownApiPathIsBlocked() throws Exception {
        mvc.perform(get("/api/new-private-path")
                .with(user("alice").authorities(
                    new SimpleGrantedAuthority("REPORT_READ")
                )))
            .andExpect(status().isForbidden());
    }
}
~~~

**Những điều test này chứng minh:**

- Đã có HTTP filters thật trong MockMvc context; `@SpringBootTest` + `@AutoConfigureMockMvc` kiểm tra chain integration.
- API chưa có authentication trả 401 Basic challenge, không bị web form-login chain chiếm để redirect 302.
- Sai password bị từ chối; đúng password + authority đọc được API.
- `@WithMockUser`/`.with(user())` **không** kiểm tra password provider nên test Basic riêng vẫn cần thiết.
- POST thiếu token trả 403; khi test role, dùng `csrf()` để không tạo 403 “đúng mã nhưng sai nguyên nhân”.
- Web anonymous redirect 302; user thiếu admin bị 403, admin được 200.
- Controller `/shadow` có thật nhưng bị catch-all denyAll chặn; đây là test bảo vệ việc thêm route mới.
- Test form-login xác nhận **đúng redirect URL** chứ không chỉ mã 302.

Tổng cộng file này có **17 test**. Không có assertion nào phụ thuộc vào thứ tự các test, và không ghi state vào database.

### 10.2. src/test/java/demo/MigrationMethodSecurityTests.java

~~~java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@SpringBootTest
class MigrationMethodSecurityTests {

    @Autowired
    AdminReportService adminService;

    @Test
    @WithMockUser(username = "admin", roles = "ADMIN")
    void adminIsAllowedByPreAuthorize() {
        assertThat(adminService.adminLabel())
            .isEqualTo("admin-only");
    }

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void userWithoutAdminAuthorityIsDenied() {
        assertThatThrownBy(adminService::adminLabel)
            .isInstanceOf(AccessDeniedException.class);
    }
}
~~~

**Cần có cả positive và negative test.** Nếu quên `@EnableMethodSecurity`, test positive có thể vẫn trả đúng string, nhưng test negative sẽ phát hiện annotation không được enforce.

**Không tạo `new AdminReportService()` để test `@PreAuthorize`**, vì như vậy bỏ qua Spring-managed proxy. Cũng không mock chính service được bảo vệ và coi kết quả là method security integration test.

### 10.3. Chạy test

~~~bash
mvn test
~~~

Dự kiến chạy **19 test**: 17 HTTP tests + 2 method security tests. Các test nhằm xác minh 0 failures/0 errors với project như đã trình bày. Đây là **kết quả dự kiến**; phần README không tuyên bố đã chạy Maven hay thu được log thực tế ở môi trường hiện tại.

Chạy riêng nhóm HTTP:

~~~bash
mvn -Dtest=MigrationHttpSecurityTests test
~~~

Với security migrations thực tế, nên chạy test trên cả ứng dụng trước và sau khi đổi config để phát hiện sai khác về status, redirect, headers, cookie, role và CSRF. Một response `200` không đủ chứng minh an toàn nếu request đã vô tình bypass chain; luôn có negative cases.

## 11. Các thay đổi Boot 2 → Boot 3 và namespace cần kiểm tra

Việc loại `WebSecurityConfigurerAdapter` thường diễn ra cùng nâng cấp runtime:

### 11.1. Java và Servlet API

- Spring Boot 3 yêu cầu **Java 17 trở lên**.
- Spring Framework 6/Security 6 chạy trên Jakarta EE namespaces, ví dụ `jakarta.servlet.Filter`, `jakarta.servlet.http.HttpServletRequest`.
- Library/filter cũ biên dịch với `javax.servlet.*` có thể không tương thích với Jakarta Servlet; cần chọn adapter version hỗ trợ Boot 3.
- **Đừng** đổi mọi `javax.*` thành `jakarta.*` bằng tìm-thay mù quáng: `javax.crypto`, `javax.net.ssl` và nhiều Java SE packages vẫn thuộc `javax`.

### 11.2. DSL matchers

`antMatchers` được dùng nhiều trong Security 5; bản hiện đại dùng `requestMatchers`. Cách Spring tạo matcher từ String có thể dựa trên MVC/Servlet environment. Với **nhiều DispatcherServlet hoặc servlet path khác nhau**, cần kiểm tra matcher semantics, `HandlerMappingIntrospector`/`MvcRequestMatcher` phù hợp phiên bản và context path thực.

Kiểm thử các đường dẫn nguy hiểm:

- `/api` so với `/api/`.
- `/api/private` so với `/api/private/`.
- Context path `/app` và servlet mapping không mặc định.
- Encoded slash, dot segment, semicolon/matrix variable nếu stack hỗ trợ.
- URL ngoài phạm vi chuyên biệt rơi vào catch-all.
- Method mới GET/POST/PUT/PATCH/DELETE có rule hay không.
- `ERROR`/`FORWARD` dispatcher có bị chặn ngoài ý muốn không.

**Không cố tự normalize path bằng string slicing trước khi ủy quyền**; dùng matcher phù hợp runtime và kiểm thử request thực tế.

### 11.3. Các cấu hình phải migrate riêng, không mất vì thiếu override

Nếu hệ thống cũ có cấu hình đặc thù trong `configure(HttpSecurity)`, cần đối chiếu từng điểm:

| Tính năng | Kiểm tra sau migration |
| --- | --- |
| Form login | Login page, processing URL, failure/success handler, saved request, `permitAll`. |
| Logout | POST/CSRF, invalidation session, clear authentication, success URL. |
| CSRF | Repository, matching paths, token lifecycle; không tắt toàn cục nếu còn cookie session. |
| CORS | Origin/method/header/credentials, preflight OPTIONS, proper `CorsConfigurationSource`. |
| Session | Session creation policy, fixation protection, concurrent sessions, `SecurityContextRepository`. |
| Exception handling | `AuthenticationEntryPoint`, `AccessDeniedHandler`, API 401/403 vs web redirect. |
| Headers | HSTS khi HTTPS, CSP/Frame options/X-Content-Type-Options theo policy. |
| Remember-me | Key/cookie/expiry/password changes, persistent token repository nếu dùng. |
| Filter tùy biến | `addFilterBefore`/`addFilterAfter`, dependencies, location so với authentication/authorization filters. |
| Authentication | Provider order, UserDetailsService, password hash migration, disabled users. |
| OAuth2/OIDC/SAML2 | Redirect URI, callback paths, claims/scopes/role mapping, adapters đúng release. |
| Method security | `@EnableMethodSecurity`, `@PreAuthorize` proxy, permission evaluator. |
| Multi-chain | `@Order`, `securityMatcher`, default/catch-all coverage. |

Định nghĩa `SecurityFilterChain` bean cũng có thể khiến **auto-configured default web security chain của Spring Boot** không còn được sử dụng theo cách mặc định. Vì vậy phải chủ động khai báo policy đủ cho các path cần thiết, không trông chờ rằng starter sẽ tự bổ sung một chain dự phòng.

## 12. Từ chẩn đoán lỗi đến sửa đúng

### 12.1. Sau khi nâng cấp, tất cả endpoint trả 403

Khả năng:

- `authorizeHttpRequests` có `denyAll` bắt quá rộng hoặc quy tắc path được đặt sai thứ tự.
- Đổi `hasRole` và `hasAuthority` gây thiếu prefix.
- Method security `@PreAuthorize` bắt đầu áp dụng và chặn service trước đây không được bảo vệ.
- POST thiếu CSRF do form JS chưa gửi token.
- Request bị một chain chuyên biệt match sớm hơn mong đợi.

**Cách làm:** test GET đủ quyền, GET thiếu quyền, POST có/không CSRF, kiểm tra `Authentication.getAuthorities()` trong môi trường test, so sánh chain đầu tiên match. Không thêm `anyRequest().permitAll()` để “sửa nhanh”.

### 12.2. API trước trả 401, nay trả 302 /login

Thường API đã rơi vào form-login chain hoặc `AuthenticationEntryPoint` khác. Xem `securityMatcher("/api/**")` và `@Order`. Kiểm tra request `/api/v2/...` có khớp path, và URL login có thuộc chain phù hợp không.

**Fix:** phục hồi cấu hình authentication/entry point đúng cho API, thêm regression test cho `WWW-Authenticate` và `Location`.

### 12.3. Form login đúng password nhưng redirect /login?error

Nguyên nhân có thể: UserDetailsService không được dùng, PasswordEncoder mismatch, credential provider sai, user disabled, login processing URL không khớp, cấu hình mới có nhiều `AuthenticationManager`. Phải kiểm tra provider selection và password hash, không tắt encoder hoặc gán `permitAll` tùy tiện.

### 12.4. Controller mới chạy công khai dù không được khai báo

Khả năng: chỉ có chain `/api/**`, không có catch-all; hoặc `web.ignoring()` đang bỏ qua một path quá rộng. Đây là **lỗ hổng**, cần sửa vùng phủ SecurityFilterChain, không chỉ đổi HTTP status.

### 12.5. `@PreAuthorize` không có tác dụng

Kiểm tra:

- Đã dùng `@EnableMethodSecurity` chưa?
- Service là Spring-managed bean và được gọi **qua proxy** chưa?
- Có self-invocation vượt qua proxy không?
- Test có mock bean thay cho service thật không?
- Có cấu hình global method security cũ hoặc adapter conflict không?

Viết test denied cho user không có quyền; chỉ test authorized là không đủ.

### 12.6. Test trả 403 nhưng không đúng nguyên nhân

Đối với POST, `CsrfFilter` có thể trả 403 trước authorization. Nếu muốn test role, gửi token hợp lệ bằng `csrf()` rồi thay đổi authorities. Nếu muốn test CSRF, giữ role hợp lệ và bỏ token.

Đối với GET, nếu unauthenticated, entry point có thể trả **401** (API Basic) hoặc **302** (web form login). Không mặc định mọi anonymous GET đều có cùng mã.

### 12.7. Login hoặc OAuth2 callback bị redirect lặp

Một chain hẹp có thể không match `/login`, `/logout` hoặc `/login/oauth2/code/{registrationId}`. Kiểm tra default page, processing path, callback, session cookie và reverse proxy host/scheme. Khi nâng cấp, phải giữ đúng URL từ cấu hình cũ hoặc cập nhật IdP/redirect registrations có chủ đích.

## 13. Quy trình migration an toàn theo bước

**Bước 1 — Chụp hợp đồng hiện tại bằng test.** Liệt kê public endpoints, protected endpoints, HTTP methods, roles/scopes, authentication entry points, CSRF, login/logout, headers và session. Viết test integration chạy trên phiên bản cũ trước khi đổi config.

**Bước 2 — Nâng runtime/dependency có kiểm soát.** Xác minh Java 17, Boot 3/Security 6, Jakarta Servlet APIs và các custom libraries. Tránh trộn Spring Security 5 và 6 cùng classpath hoặc đưa `javax.servlet` adapter legacy vào runtime Jakarta.

**Bước 3 — Tách configure(HttpSecurity).** Chuyển rule HTTP sang một hoặc nhiều `SecurityFilterChain` bean. Đổi `authorizeRequests`/`antMatchers` theo DSL mới. Thêm `anyRequest` cuối và default chain rõ ràng.

**Bước 4 — Tách authentication beans.** Chuyển UserDetailsService, PasswordEncoder và provider; chỉ thêm AuthenticationManager bean khi một thành phần cần inject. Kiểm tra password hashes, role mapping và cơ chế disabled/locked users.

**Bước 5 — Kiểm tra web ignoring.** Ưu tiên `permitAll()` cho static/public resources. Nếu có ngoại lệ cần `WebSecurityCustomizer`, ghi rõ lý do và test không bỏ qua security cho endpoint động.

**Bước 6 — Chuyển method security.** Dùng `@EnableMethodSecurity`, kiểm thử proxy và negative permissions; kiểm tra các permission evaluator hoặc custom expressions trước đây.

**Bước 7 — Kiểm tra login/CSRF/session.** Form login/logout, session repository, request cache, CSRF field, CORS và exception handling có thể thay đổi hành vi khi chuyển code. Không đồng ý việc “test xanh” chỉ vì bỏ filter.

**Bước 8 — Chạy HTTP integration tests.** Bao phủ anonymous, invalid credential, authorized, forbidden, CSRF missing/valid, 302 redirects, status 401 vs 403, method chưa khai báo, path ngoài allowlist, multiple chain overlap.

**Bước 9 — Chạy test ở môi trường tương ứng production.** Proxy/context path/HTTPS, external IdP, JDBC/LDAP user store và security headers có thể khác local. Không dùng secret thật trong log.

**Bước 10 — Review theo nguyên tắc least privilege.** Với mỗi request/role, chứng minh không nới quyền. Sau cùng mới xóa hẳn class adapter cũ, dependency legacy và các cấu hình trùng lặp. Đừng để cả hai cấu hình tranh quyền trong cùng ApplicationContext.

## 14. Anti-pattern và cách sửa

| Sai lầm | Rủi ro | Cách khắc phục |
| --- | --- | --- |
| Thay `WebSecurityConfigurerAdapter` bằng một chain `permitAll` để build pass. | Toàn ứng dụng có thể mất authorization. | Di chuyển từng rule cũ, test denied cases. |
| Bỏ `http.build()` hoặc return sai bean. | Không tạo được security chain. | `return http.build()` sau lambda DSL. |
| Tạo một chain `/api/**` nhưng không có fallback. | URL ngoài `/api/**` có thể bypass Spring Security filters. | Catch-all chain cuối. |
| Đặt chain `/api/**` trước `/api/admin/**`. | Chain rộng chiếm request chuyên biệt. | `@Order` chain hẹp trước; test path giao nhau. |
| Dùng `web.ignoring()` thay mọi `permitAll()`. | Request mất security headers/filter handling. | Prefer `permitAll()` trong chain. |
| Disable CSRF toàn bộ chỉ vì POST test 403. | CSRF cho browser/session có thể bị mất. | Form/token/repository đúng, hoặc threat model thật cho API stateless. |
| Copy `{noop}` từ demo cũ vào production. | Lưu password không hash. | Dùng encoder mạnh, migration hash an toàn. |
| Dùng `roles("ROLE_ADMIN")` thay vì tên role. | Prefix không khớp, 403 hoặc lỗi build user. | `roles("ADMIN")` hoặc `authorities("ROLE_ADMIN")`. |
| Tạo hai provider giống nhau để "chắc" login. | Thứ tự authentication khó kiểm soát. | Chọn provider có chủ đích, kiểm thử đầy đủ. |
| Quên `@EnableMethodSecurity`. | `@PreAuthorize` không được thực thi. | Bật method security, test negative. |
| Test `new Service()` thay Spring bean. | Bỏ qua method-security proxy. | `@Autowired` Spring-managed service. |
| MockMvc có `addFilters = false`. | Test HTTP security xanh giả. | Bật Spring Security filters trong test. |
| Test POST role mà không gắn `csrf()`. | 403 đúng mã nhưng do thiếu token. | Gắn token hợp lệ khi cô lập authorization. |
| Chuyển `javax.servlet` thành `jakarta.servlet` mà không kiểm tra thư viện. | Classloading/adapter API mismatch. | Cập nhật dependencies và integration tests. |
| Đổi matcher mà không test context/servlet path. | Route bị bypass hoặc chặn sai. | Test trên URL/method thực, chú ý dispatcher và proxy. |
| Cho mọi resource có login quyền admin. | Mất kiểm tra object/tenant. | Kết hợp URL, method và resource authorization. |

## 15. Checklist nghiệm thu cuối cùng

- [ ] Không còn reference/extension từ `WebSecurityConfigurerAdapter` hoặc DSL removed trong code Boot 3/Security 6.
- [ ] Có ít nhất một `SecurityFilterChain` bean và policy rõ cho mọi path quan trọng.
- [ ] Nếu có nhiều chain, `@Order`/ `securityMatcher` rõ ràng và có catch-all.
- [ ] `authorizeHttpRequests` dùng `requestMatchers` đúng semantics và method, `anyRequest` cuối.
- [ ] Public URL có `permitAll` được phê duyệt; không bypass filter với `web.ignoring` tràn lan.
- [ ] Authentication source và PasswordEncoder được đăng ký chính xác; user/password migration có tests.
- [ ] Custom AuthenticationProvider/manager chỉ tồn tại khi cần và có test lỗi xác thực.
- [ ] `@EnableMethodSecurity` thay annotation legacy, các test denied/authorized chạy qua proxy.
- [ ] CSRF cho session/forms còn bảo vệ POST/PUT/PATCH/DELETE theo threat model.
- [ ] Form login, logout, request cache, redirect và entry point API 401 vs web 302 không bị đổi ngoài ý muốn.
- [ ] 403 thiếu role khác 403 thiếu CSRF trong test; có negative cases tương ứng.
- [ ] Endpoint mới ngoài allowlist bị deny, không bị route ngoài chain.
- [ ] Cookies, HTTPS, CORS, headers, forwarded proxies, session và callback URLs được kiểm tra.
- [ ] Jakarta Servlet và third-party adapters tương thích Boot/Security version hiện tại.
- [ ] Không log password/token, không hard-code user production và không dùng `NoOpPasswordEncoder` ở prod.
- [ ] Có so sánh trước/sau trên contract matrix, không chỉ dựa vào dự án khởi động thành công.

## 16. Tự kiểm tra kiến thức

**Câu 1.** Vì sao Spring Security 6 không dùng `extends WebSecurityConfigurerAdapter` nữa?

**Trả lời:** Adapter đã bị loại bỏ; cấu hình mới dùng bean `SecurityFilterChain` và các bean authentication riêng. Tư duy chuyển từ override/inheritance sang composition.

**Câu 2.** Thay `configure(HttpSecurity)` bằng API nào?

**Trả lời:** Một `@Bean SecurityFilterChain` nhận `HttpSecurity`, cấu hình bằng DSL phù hợp, rồi trả `http.build()`.

**Câu 3.** `securityMatcher("/api/**")` có làm `anyRequest().denyAll()` bao phủ `/web/admin` không?

**Trả lời:** Không. `anyRequest` chỉ áp cho request đã match chain. Muốn bảo vệ URL ngoài `/api/**`, phải có chain khác/catch-all.

**Câu 4.** Khi nào nên khai báo `AuthenticationManager` bean?

**Trả lời:** Khi một thành phần cần inject/điều phối manager cụ thể hoặc custom authentication flow. Nhiều ứng dụng chỉ cần `UserDetailsService` + `PasswordEncoder` và provider do Spring cấu hình phù hợp.

**Câu 5.** Vì sao ưu tiên `permitAll` hơn `web.ignoring` cho static resources?

**Trả lời:** `permitAll` không yêu cầu authentication nhưng request vẫn đi qua Spring Security filters; `web.ignoring` bỏ qua các filters này.

**Câu 6.** `@EnableGlobalMethodSecurity(prePostEnabled=true)` thay bằng gì?

**Trả lời:** `@EnableMethodSecurity`, cộng với kiểm thử rằng `@PreAuthorize` thật sự intercept method Spring-managed bean.

**Câu 7.** Tại sao đổi sang bean config xong, API anonymous có thể trả 302 thay vì 401?

**Trả lời:** URL API có thể rơi vào form-login chain/entry point, hoặc chain selection/order không đúng. Cần tách đúng chain và test `Location`/`WWW-Authenticate`.

**Câu 8.** POST thiếu CSRF token trả 403. Có chứng minh role rule đã từ chối không?

**Trả lời:** Không. `CsrfFilter` có thể chặn trước. Để test role, gửi token hợp lệ `csrf()` rồi thay đổi authority.

**Câu 9.** `@WithMockUser` có kiểm thử PasswordEncoder thực không?

**Trả lời:** Không. Nó giả Authentication cho test authorization. Muốn test credential/password, cần test HTTP Basic/formLogin/provider với thông tin test hợp lệ và sai.

**Câu 10.** Vì sao Java 17/Boot 3 cần chú ý Jakarta?

**Trả lời:** Servlet APIs của Jakarta EE dùng `jakarta.servlet`; thư viện còn phụ thuộc `javax.servlet` cũ có thể không tương thích. Không đổi bừa mọi package `javax` vì nhiều Java SE APIs vẫn có tên đó.

---

**Kết luận:** Nâng cấp từ `WebSecurityConfigurerAdapter` sang các bean cấu hình không chỉ là thay cú pháp. Hãy tách **HTTP security** thành `SecurityFilterChain`, tách **xác thực** thành `UserDetailsService`/`PasswordEncoder` và provider cần thiết, chuyển method security sang `@EnableMethodSecurity`, giữ vùng phủ matcher/catch-all, CSRF/session/login và test đủ các nhánh 200/302/401/403. Cấu hình bean mới chỉ đạt yêu cầu khi các **hành vi bảo mật trước và sau nâng cấp** đã được kiểm tra và không có endpoint vô tình được nới quyền.