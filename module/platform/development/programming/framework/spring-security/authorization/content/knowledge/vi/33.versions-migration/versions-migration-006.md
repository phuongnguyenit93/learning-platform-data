# Chuyển `WebSecurityConfigurerAdapter` sang cấu hình bean trong Spring Security

`WebSecurityConfigurerAdapter` từng là cách quen thuộc để cấu hình `HttpSecurity`, `AuthenticationManagerBuilder` và `WebSecurity` bằng cách kế thừa class và ghi đè `configure(...)`. Spring Security **5.7** đánh dấu adapter là deprecated; **Spring Security 6.0** đã loại bỏ nó. Cách thay thế là **bean-based configuration**: khai báo `SecurityFilterChain`, `UserDetailsService`/`AuthenticationProvider`, `PasswordEncoder` và các bean phụ trợ cần thiết. Các phiên bản mới hướng tới **lambda DSL**; Spring Security 7 đã loại các API cấu hình `.and()` và `authorizeRequests` cũ.

Bài này dành cho **Servlet/Spring MVC**, Spring Security 6.x, Java 17+, với ví dụ Spring Boot 3.5.7 và 12 kiểm thử HTTP bằng MockMvc. Với WebFlux, các loại đúng là `SecurityWebFilterChain` và `ServerHttpSecurity`; không áp dụng nguyên cấu hình servlet cho reactive stack.

## 1. Bản đồ chuyển đổi: mỗi phần của adapter trở thành bean nào?

| Trước đây | Trách nhiệm | Sau chuyển đổi |
| --- | --- | --- |
| `extends WebSecurityConfigurerAdapter` | Gom toàn bộ cấu hình security | Class `@Configuration` thông thường với các `@Bean` rõ nhiệm vụ |
| `configure(HttpSecurity http)` | Authorization URL, HTTP Basic/form login, CSRF, CORS, session, headers | `@Bean SecurityFilterChain securityFilterChain(HttpSecurity http)` |
| `configure(AuthenticationManagerBuilder auth)` | Nguồn user, provider, cơ chế xác thực | `UserDetailsService`, `AuthenticationProvider`, `PasswordEncoder` hoặc manager thích hợp |
| `configure(WebSecurity web)` | Loại URL khỏi Spring Security filters | `WebSecurityCustomizer` khi thật sự cần, thường ưu tiên `permitAll` |
| `authenticationManagerBean()` | Expose manager cho code khác inject | `AuthenticationManager` bean tùy chọn |
| Nhiều adapter dùng `@Order` | Các vùng URL có filter policy riêng | Nhiều `SecurityFilterChain` bean với `@Order` và `securityMatcher` |
| `@EnableGlobalMethodSecurity` | Bảo vệ method bằng annotation | `@EnableMethodSecurity` |

**Không nhất thiết tạo tất cả bean trong bảng.** Nếu ứng dụng là OAuth2 Resource Server nhận JWT, có thể dùng `SecurityFilterChain` + JWT decoder/converter thay vì user/password store. Nếu một ứng dụng web cần đăng nhập qua database, bean `UserDetailsService` và `PasswordEncoder` thường cần thiết, nhưng không đồng nghĩa phải xuất thêm một global `AuthenticationManager`.

Cần giữ **hành vi bảo mật trước và sau**: endpoint nào public, endpoint nào cần role/scope, URL nào bị chặn, phương thức HTTP nào được phép, session/CSRF/CORS/login/logout hoạt động ra sao. Chỉ hết lỗi biên dịch chưa chứng minh migration thành công.

## 2. Trước và sau với một `HttpSecurity` đơn giản

### Cấu hình cũ (chỉ áp dụng ở Spring Security 5.x)

~~~java
// Fragment lịch sử: không biên dịch được trên Spring Security 6+.
@Configuration
@EnableWebSecurity
public class LegacySecurityConfig extends WebSecurityConfigurerAdapter {
    @Override
    protected void configure(HttpSecurity http) throws Exception {
        http.authorizeRequests()
            .antMatchers(HttpMethod.GET, "/public/ping").permitAll()
            .antMatchers("/admin/**").hasRole("ADMIN")
            .anyRequest().authenticated()
            .and()
            .httpBasic();
    }
}
~~~

Lưu ý đoạn trên chỉ biểu diễn chính sách HTTP, chưa chứa nguồn tài khoản hay imports đầy đủ. Nếu di chuyển code cũ nguyên vẹn sang Spring Security 6, lỗi đầu tiên là không còn class adapter, và các lệnh `antMatchers`/`authorizeRequests` không còn tương thích.

### Cấu hình bean (Spring Security 6.x)

~~~java
// Fragment cần đặt trong class @Configuration.
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
    http.authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/public/ping").permitAll()
            .requestMatchers("/admin/**").hasRole("ADMIN")
            .anyRequest().authenticated()
        )
        .httpBasic(Customizer.withDefaults());
    return http.build();
}
~~~

Các import chính:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
~~~

Giải thích các bước:

1. Bỏ `extends WebSecurityConfigurerAdapter`; class cấu hình thường chỉ dùng `@Configuration`.
2. Đổi `protected void configure(HttpSecurity)` thành phương thức `@Bean` **trả về** `SecurityFilterChain`.
3. Đổi `authorizeRequests().antMatchers(...)` thành `authorizeHttpRequests(auth -> auth.requestMatchers(...))`.
4. Đổi cú pháp nối `.and().httpBasic()` thành `.httpBasic(Customizer.withDefaults())`.
5. Kết thúc bằng `return http.build();`. Nếu không có filter chain như mong muốn, request có thể được xử lý bởi default chain khác hoặc một khoảng trống cấu hình.
6. Giữ nguyên thứ tự và mức bảo vệ của matcher; áp dụng first-match rule trong `authorizeHttpRequests`.

Spring Boot có thể tự tạo default web security khi chưa có `SecurityFilterChain` tùy chỉnh. Khi đăng ký chain của ứng dụng, **đừng mặc định** cấu hình mặc định trước đó vẫn tồn tại. Viết rõ luật `anyRequest()` và kiểm thử các URL không có trong inventory.

## 3. Chuyển authentication khỏi `AuthenticationManagerBuilder`

### 3.1. User trong bộ nhớ

Lối cũ:

~~~java
// CŨ — fragment trong configure(AuthenticationManagerBuilder auth).
auth.inMemoryAuthentication()
    .withUser("reader")
    .password("{noop}read123")
    .roles("USER");
~~~

Lối mới cho demo/test:

~~~java
// Fragment trong @Configuration, có dependencies và imports tương ứng.
@Bean
PasswordEncoder passwordEncoder() {
    return new BCryptPasswordEncoder();
}

@Bean
UserDetailsService userDetailsService(PasswordEncoder encoder) {
    UserDetails reader = User.withUsername("reader")
            .password(encoder.encode("read123"))
            .roles("USER")
            .build();
    return new InMemoryUserDetailsManager(reader);
}
~~~

Các loại cần import:

~~~java
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
~~~

Ở ứng dụng production, không hardcode mật khẩu trong source hoặc lưu chuỗi `{noop}...`; dùng kho người dùng và password hash được bảo vệ. `User.withDefaultPasswordEncoder()` có trong một số ví dụ migration cũ nhằm rút ngắn minh họa nhưng không nên dùng để triển khai thực tế.

Nếu code cũ dùng `auth.jdbcAuthentication()`, hãy xét `JdbcUserDetailsManager` cùng `DataSource` và schema phù hợp; nếu dùng LDAP, hãy dùng các LDAP authentication factory/provider. Nếu dùng OAuth2/OIDC/JWT hoặc custom authentication, giữ đúng cơ chế xác thực, không thay bằng user in-memory chỉ để code build.

### 3.2. Có cần bean `AuthenticationManager`?

**Không phải mọi ứng dụng đều cần.** Spring Security có thể thiết lập manager cho filter chain khi `UserDetailsService`/provider được cấu hình đúng. Nếu một service hoặc custom controller cần inject `AuthenticationManager` trực tiếp, có thể chọn:

~~~java
// Fragment tùy chọn; chỉ thêm khi thực sự cần global manager.
@Bean
AuthenticationManager authenticationManager(
        AuthenticationConfiguration configuration) throws Exception {
    return configuration.getAuthenticationManager();
}
~~~

Imports:

~~~java
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.config.annotation.authentication.configuration.AuthenticationConfiguration;
~~~

Nếu nhiều provider cùng hiện diện, hoặc dùng custom manager cho một chain, hãy kiểm tra provider order, bean wiring và cơ chế xác thực cụ thể. `http.authenticationManager(customManager)` có thể cấu hình manager riêng cho chain; không tự thêm bean global và chain-local manager cùng lúc nếu không hiểu luồng xác thực.

**Role khác authority:** `User.roles("ADMIN")` tạo `ROLE_ADMIN`, và `hasRole("ADMIN")` kiểm tra `ROLE_ADMIN`. `hasAuthority("ADMIN")` kiểm tra đúng `ADMIN`, không tự thêm prefix. Khi migrate từ JWT hoặc database, đừng đổi `hasRole`/`hasAuthority` nếu không có test xác thực cách claim/role được map.

## 4. Chuyển `configure(WebSecurity)`: `ignoring` hay `permitAll`?

Mã adapter cũ:

~~~java
// CŨ: fragment trong configure(WebSecurity web).
web.ignoring().antMatchers("/assets/**");
~~~

Bean mới có thể là:

~~~java
// Fragment @Bean trong @Configuration.
@Bean
WebSecurityCustomizer webSecurityCustomizer() {
    return web -> web.ignoring().requestMatchers("/assets/**");
}
~~~

Nhưng đây **không luôn là lựa chọn tốt nhất**. `WebSecurityCustomizer` có `ignoring` làm request **bỏ qua hoàn toàn Spring Security filter chain**. Điều đó cũng bỏ qua security headers và các filter khác do Spring Security quản lý. Với tài nguyên công khai, tài liệu Spring Security khuyến nghị cân nhắc **`permitAll`**:

~~~java
// Fragment trong SecurityFilterChain bean.
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/assets/**", "/favicon.ico").permitAll()
    .anyRequest().authenticated()
);
~~~

`permitAll` cho phép public request **qua authorization** trong khi các filter khác vẫn được xử lý. Nếu URL `/assets/**` chứa endpoint nhạy cảm, đó vẫn là lỗi thiết kế; không mở `/**` chỉ để “cho static chạy”. Với tài nguyên Spring Boot chuẩn, có thể dùng `PathRequest.toStaticResources().atCommonLocations()` khi phù hợp, nhưng phải xác nhận những location mà ứng dụng thực phục vụ.

## 5. Chuyển nhiều adapter thành nhiều `SecurityFilterChain`

Khi có các khu vực API và web cần chính sách khác nhau, đăng ký nhiều bean với thứ tự rõ ràng. Đây là **fragment độc lập**, không ghép cùng cấu hình ví dụ chạy ở mục 6:

~~~java
// Fragment thuộc class @Configuration; import @Order.
@Bean
@Order(1)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    http.securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/admin/**").hasRole("ADMIN")
            .anyRequest().authenticated()
        )
        .httpBasic(Customizer.withDefaults());
    return http.build();
}

@Bean
SecurityFilterChain fallbackChain(HttpSecurity http) throws Exception {
    http.authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/public/ping").permitAll()
            .anyRequest().denyAll()
        )
        .httpBasic(Customizer.withDefaults());
    return http.build();
}
~~~

`@Order` có import `org.springframework.core.annotation.Order`. Một request được `FilterChainProxy` đưa qua **chain khớp đầu tiên**; các chain còn lại không áp dụng. Trong mỗi chain, `authorizeHttpRequests` lại chọn **rule khớp đầu tiên**. Vì vậy có hai tầng thứ tự:

- `http.securityMatcher("/api/**")` là phạm vi **của cả chain**.
- `auth.requestMatchers("/api/admin/**")` áp dụng **bên trong chain** đã được chọn.
- `anyRequest()` là fallback **trong chain đang áp dụng**, không có nghĩa bảo vệ mọi URL nếu chain đã có `securityMatcher` giới hạn.

Nếu không có fallback chain và request nằm ngoài mọi `securityMatcher`, Spring Security sẽ không bảo vệ request đó. Nếu chain chỉ có `securityMatcher("/api/**")`, endpoint login mặc định `/login` có thể không thuộc chain và không được cung cấp như bạn kỳ vọng; test URL login/logout nếu ứng dụng dùng form login.

Một lỗi nghiêm trọng:

~~~java
// SAI: chain ưu tiên 1 bao phủ cả /api/admin/**.
@Bean
@Order(1)
SecurityFilterChain openEverything(HttpSecurity http) throws Exception {
    http.securityMatcher("/**")
        .authorizeHttpRequests(auth -> auth.anyRequest().permitAll());
    return http.build();
}
~~~

Nếu còn một chain admin `@Order(2)`, nó không được chọn với URL admin vì chain thứ nhất đã khớp. Tương tự, trong một chain:

~~~java
// SAI: rule rộng đứng trước che rule admin.
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/**").permitAll()
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .anyRequest().denyAll()
);
~~~

Hãy đặt matcher nhạy cảm trước matcher rộng hơn, và xác nhận cả anonymous lẫn user thiếu quyền đều bị chặn.

## 6. Ví dụ chạy được: Spring Boot 3.5.7 + Java 17 + MockMvc

Demo gồm **một** `SecurityFilterChain`, ba tài khoản in-memory đã mã hóa BCrypt, GET public, GET chỉ cho user đã đăng nhập, GET chỉ cho admin, và POST yêu cầu authority + CSRF. Nó minh họa các bean thay adapter và test bảo mật thực tế, không phụ thuộc database.

### 6.1. Cấu trúc

~~~text
bean-security-demo/
├── pom.xml
└── src/
    ├── main/java/com/example/migration/
    │   ├── DemoApplication.java
    │   ├── SecurityConfig.java
    │   └── DemoController.java
    └── test/java/com/example/migration/
        └── SecurityMigrationTest.java
~~~

### 6.2. `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>bean-security-demo</artifactId>
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

### 6.3. `DemoApplication.java`

~~~java
package com.example.migration;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

### 6.4. `SecurityConfig.java`

~~~java
package com.example.migration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
public class SecurityConfig {
    @Bean
    public SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/public/ping").permitAll()
                .requestMatchers("/admin/**").hasRole("ADMIN")
                .requestMatchers(HttpMethod.GET, "/api/me").authenticated()
                .requestMatchers(HttpMethod.POST, "/api/notes")
                    .hasAuthority("NOTE_WRITE")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(AbstractHttpConfigurer::disable);

        // CSRF mặc định còn bật: POST cần token.
        return http.build();
    }

    @Bean
    public PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    public UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails reader = User.withUsername("reader")
                .password(encoder.encode("read123"))
                .roles("USER")
                .build();

        UserDetails editor = User.withUsername("editor")
                .password(encoder.encode("edit123"))
                .authorities("ROLE_USER", "NOTE_WRITE")
                .build();

        UserDetails admin = User.withUsername("admin")
                .password(encoder.encode("admin123"))
                .roles("ADMIN")
                .build();

        return new InMemoryUserDetailsManager(reader, editor, admin);
    }
}
~~~

`SecurityConfig` tự cung cấp ba bean phụ trách những phần trước đây adapter xử lý. `@SpringBootApplication` quét package `com.example.migration`, nên không cần tự đăng ký `springSecurityFilterChain` như cấu hình Servlet thuần.

### 6.5. `DemoController.java`

~~~java
package com.example.migration;

import java.security.Principal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {
    @GetMapping("/public/ping")
    public String ping() {
        return "pong";
    }

    @GetMapping("/api/me")
    public String me(Principal principal) {
        return principal.getName();
    }

    @GetMapping("/admin/report")
    public String report() {
        return "admin-report";
    }

    @PostMapping("/api/notes")
    public String createNote() {
        return "created";
    }

    @GetMapping("/ops/hidden")
    public String hidden() {
        // Có handler thật, chỉ rule denyAll ngăn truy cập.
        return "should-not-be-seen";
    }
}
~~~

### 6.6. `SecurityMigrationTest.java`

~~~java
package com.example.migration;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SecurityMigrationTest {
    @Autowired MockMvc mvc;

    @Test
    void anonymousCanReadPublicPing() throws Exception {
        mvc.perform(get("/public/ping"))
           .andExpect(status().isOk())
           .andExpect(content().string("pong"));
    }

    @Test
    void anonymousCannotReadMe() throws Exception {
        mvc.perform(get("/api/me"))
           .andExpect(status().isUnauthorized());
    }

    @Test
    void correctCredentialsCanReadMe() throws Exception {
        mvc.perform(get("/api/me").with(httpBasic("reader", "read123")))
           .andExpect(status().isOk())
           .andExpect(content().string("reader"));
    }

    @Test
    void invalidPasswordIsRejected() throws Exception {
        mvc.perform(get("/api/me").with(httpBasic("reader", "wrong")))
           .andExpect(status().isUnauthorized());
    }

    @Test
    void anonymousCannotReadAdmin() throws Exception {
        mvc.perform(get("/admin/report"))
           .andExpect(status().isUnauthorized());
    }

    @Test
    void readerCannotReadAdmin() throws Exception {
        mvc.perform(get("/admin/report")
                .with(httpBasic("reader", "read123")))
           .andExpect(status().isForbidden());
    }

    @Test
    void adminCanReadAdminReport() throws Exception {
        mvc.perform(get("/admin/report")
                .with(httpBasic("admin", "admin123")))
           .andExpect(status().isOk())
           .andExpect(content().string("admin-report"));
    }

    @Test
    void editorCannotPostWithoutCsrfToken() throws Exception {
        mvc.perform(post("/api/notes")
                .with(httpBasic("editor", "edit123")))
           .andExpect(status().isForbidden());
    }

    @Test
    void anonymousWithCsrfStillNeedsAuthentication() throws Exception {
        mvc.perform(post("/api/notes").with(csrf()))
           .andExpect(status().isUnauthorized());
    }

    @Test
    void readerWithCsrfStillLacksAuthority() throws Exception {
        mvc.perform(post("/api/notes")
                .with(httpBasic("reader", "read123"))
                .with(csrf()))
           .andExpect(status().isForbidden());
    }

    @Test
    void editorWithCsrfAndAuthorityCanPost() throws Exception {
        mvc.perform(post("/api/notes")
                .with(httpBasic("editor", "edit123"))
                .with(csrf()))
           .andExpect(status().isOk())
           .andExpect(content().string("created"));
    }

    @Test
    void unlistedEndpointIsDeniedEvenForAdmin() throws Exception {
        mvc.perform(get("/ops/hidden")
                .with(httpBasic("admin", "admin123")))
           .andExpect(status().isForbidden());
    }
}
~~~

Các test gọi HTTP Basic với credential của user store demo, nhờ `SecurityMockMvcRequestPostProcessors.httpBasic`; đây là bài test đi qua filters và xác thực thật của mẫu (khác với `@WithMockUser` chỉ giả lập danh tính). `csrf()` của Spring Security Test tạo CSRF token hợp lệ cho POST trong bối cảnh kiểm thử.

Chạy từ root dự án bằng JDK 17+ và Maven:

~~~bash
mvn test
~~~

**Kết quả kỳ vọng:** 12 phương thức JUnit `@Test` thành công, không có assertion failures. Maven log phụ thuộc môi trường, nên không cố định một chuỗi stdout. Sau khi test thành công có thể chạy:

~~~bash
mvn spring-boot:run
~~~

Trong terminal khác, kiểm tra các endpoint GET của ứng dụng demo:

~~~bash
curl -i http://localhost:8080/public/ping
curl -i -u reader:read123 http://localhost:8080/api/me
curl -i -u reader:read123 http://localhost:8080/admin/report
curl -i -u admin:admin123 http://localhost:8080/admin/report
~~~

Với cấu hình này, HTTP status mong đợi lần lượt là **200, 200, 403, 200**, nội dung của hai request đầu là `pong` và `reader`. Dữ liệu tài khoản chỉ để chạy local; không triển khai nguyên mẫu có credential cố định trên môi trường public.

**Ranh giới mẫu:** Chưa có database, JWT, OAuth2 login, logout theo session, CORS đặc biệt hay nhiều chain chạy cùng lúc. Những biến thể này phải migrate riêng và test tương ứng, không suy ra từ việc 12 test demo đã pass.

## 7. Những cấu hình khác cần chuyển theo lambda DSL

Trong một ứng dụng thật, việc bỏ adapter có thể bỏ sót nhiều phần bảo mật nếu chỉ copy `authorizeHttpRequests`. Ví dụ fragment cấu hình theo lambda:

~~~java
http
    .csrf(csrf -> csrf.ignoringRequestMatchers("/webhooks/signed/**"))
    .sessionManagement(session -> session
        .sessionCreationPolicy(SessionCreationPolicy.IF_REQUIRED))
    .headers(headers -> headers
        .frameOptions(frame -> frame.sameOrigin()));
~~~

Import `org.springframework.security.config.http.SessionCreationPolicy`. Đây **không phải mẫu mặc định bắt buộc**. Chỉ bỏ qua CSRF cho webhook khi xác thực webhook thực sự dùng chữ ký/secret và không phụ thuộc cookie đăng nhập. Chỉ dùng `frameOptions.sameOrigin()` nếu có yêu cầu cho nội dung được nhúng trong frame cùng nguồn. Với API thuần Bearer token không dựa trên cookie, chính sách CSRF có thể khác; cần kiểm tra mô hình client/threat trước khi quyết định.

Các thay đổi thường đi kèm nâng lên Spring Boot 3/Spring Security 6:

- Spring Framework 6/Boot 3 yêu cầu **Java 17+**.
- Servlet API và các loại liên quan dùng namespace `jakarta.*`, chẳng hạn `jakarta.servlet.Filter` thay `javax.servlet.Filter`.
- `@EnableGlobalMethodSecurity(prePostEnabled = true)` được thay thế theo hướng `@EnableMethodSecurity`. Nếu dùng `@PreAuthorize`, vẫn phải bật/kiểm method security và gọi Spring-managed bean qua proxy.
- `antMatchers`/`mvcMatchers` cần chuyển sang `requestMatchers` phù hợp. Không tự giả định sự khác nhau giữa Ant matcher, MVC matcher, servlet path và context path sẽ không ảnh hưởng URL thực tế.
- Với Spring Security 7, sử dụng lambda DSL và `authorizeHttpRequests`; không giữ `authorizeRequests` và xâu chuỗi `.and()`.
- `hasRole("ADMIN")` không đồng nghĩa `hasAuthority("ADMIN")`; mapping role/authority có thể đổi khi thay provider hoặc JWT converter.

**Lưu ý với `@PreAuthorize`:** migration HTTP chain không tự bảo đảm method-level authorization chạy. Các method cần quyền phải được gọi qua Spring proxy (self-invocation trong cùng bean có thể bypass advice) và phải có kiểm thử gọi bean thực.

## 8. Kiểm chứng đúng hành vi sau migration

Trước khi sửa cấu hình, lập một ma trận hành vi. Trong ví dụ chạy được ở mục 6:

| Request | Anonymous | Reader | Editor | Admin |
| --- | --- | --- | --- | --- |
| `GET /public/ping` | 200 | 200 | 200 | 200 |
| `GET /api/me` | 401 | 200 | 200 | 200 |
| `GET /admin/report` | 401 | 403 | 403 | 200 |
| `POST /api/notes` với CSRF token hợp lệ | 401 | 403 | 200 | 403 |
| `POST /api/notes` không có CSRF token | 403 | 403 | 403 | 403 |
| `GET /ops/hidden` | 401 hoặc bị từ chối theo entry point | 403 | 403 | 403 |

Bảng gắn với **HTTP Basic + CSRF mặc định** trong sample. Với ứng dụng form login, anonymous có thể nhận **302 redirect**; JWT resource server thường dùng response/headers khác; không ép tất cả hệ thống về một bộ status khi migration. Điều phải giữ là quy tắc *ai được truy cập gì* và hợp đồng HTTP của từng loại client.

Đặc biệt phân biệt hai nguyên nhân:

- `POST` bị **403 do CSRF** khi không có token.
- `POST` có CSRF hợp lệ nhưng thiếu `NOTE_WRITE` bị **403 do authorization**.

Chỉ test một `403` khi POST không gửi token có thể tạo **cảm giác an toàn giả** vì authorization rule sai vẫn không bị phát hiện. Tương tự, request tới URL không tồn tại trả 404 không chứng minh đường dẫn đó đã được bảo vệ; sample có handler thật `/ops/hidden` để kiểm `denyAll`.

Đối với một ứng dụng có nhiều filter chains, ma trận phải thêm cột “chain nào được chọn”: URL thuộc `/api/**`, URL sát ranh giới prefix, URL `/login`/`/logout`, URL không thuộc chain nào. Kiểm thử cả GET/POST và các đường dẫn gần giống như `/adminish` để tránh matcher sai.

## 9. Quy trình thực hiện trong codebase

1. **Xác định baseline:** lập danh sách endpoints, HTTP methods, role/authority, login/logout, session, CSRF, CORS, custom filters, 401/403/302, security headers. Chạy test hiện tại nếu còn build được.
2. **Tách từng override:** `configure(HttpSecurity)` thành `SecurityFilterChain`; `configure(AuthenticationManagerBuilder)` thành user/provider/password beans; `configure(WebSecurity)` thành `WebSecurityCustomizer` hoặc `permitAll` được đánh giá rõ ràng.
3. **Đổi DSL:** `authorizeRequests`/`antMatchers`/`.and()` thành `authorizeHttpRequests`/`requestMatchers`/lambda; rà soát matcher cụ thể/rộng và HTTP method.
4. **Bảo toàn auth flow:** giữ đúng PasswordEncoder, datasource/LDAP/JWT, custom authentication provider, exception handlers và remember-me nếu có. Không tạo manager thừa hoặc vô tình kích hoạt authentication mặc định khác.
5. **Xử lý multi-chain:** đặt `@Order`, `securityMatcher` và fallback. Mỗi request cần đi vào chain theo thiết kế; không đặt `/**` public làm chain ưu tiên cao nhất.
6. **Kiểm web và method security:** kiểm CSRF, session, CORS, headers, login/logout URLs, `@EnableMethodSecurity` và các lời gọi qua proxy.
7. **Chạy regression test:** user thật/credential sai, anonymous, role thiếu/đủ, URL bị deny, POST có/không có CSRF, URL mới, đường dẫn đã đổi; nếu dùng JWT, test cả claims mapping và expiration.
8. **Thử trên staging:** xác nhận HTTP status, redirect, headers và filter-chain selection trong môi trường gần thực; kiểm quan sát 401/403 trước khi đưa lên production.

Không ghép cùng lúc hai bean `SecurityFilterChain` cùng bảo vệ `/**` với chính sách chồng lấn mà không xác định thứ tự. Nếu biến thể mới làm “lọt” URL admin, coi đó là lỗi migration dù ứng dụng hoạt động được.

## 10. Lỗi phổ biến và cách chẩn đoán

**(a) Chỉ tạo `SecurityFilterChain` nhưng quên `return http.build()`.** Phương thức cấu hình bean không tạo ra chain như dự kiến; cần build thành công và kiểm Spring context thấy đúng bean.

**(b) Xóa adapter làm mất user store.** `configure(AuthenticationManagerBuilder)` không còn, nhưng chưa có `UserDetailsService`/provider mới. Các endpoint đều 401, hoặc startup sử dụng authentication mặc định ngoài dự tính. Kiểm tra login bằng credentials đúng và sai, tránh chỉ kiểm `@WithMockUser`.

**(c) Có `SecurityFilterChain` nhưng URL nhạy cảm không khớp chain nào.** `securityMatcher("/api/**")` không bao phủ `/admin/**`. Dùng fallback phù hợp; nhớ `anyRequest` chỉ áp dụng trong chain đang chọn.

**(d) `permitAll` quá rộng hoặc matcher bị che.** `/api/**` đứng trước `/api/admin/**` cho public cả admin. Kiểm tra từ trên xuống; matcher đầu khớp là quyết định.

**(e) Chuyển static sang `WebSecurityCustomizer.ignoring` không suy xét.** Ignored requests bỏ toàn bộ security filter chain, gồm cả security headers. Ưu tiên `permitAll` khi muốn tài nguyên public nhưng giữ các filter bảo vệ.

**(f) Phân biệt `hasRole` và `hasAuthority` sai.** `ROLE_ADMIN` khác `ADMIN`. Khi đổi user/provider/JWT converter, role prefix có thể thay đổi; test positive và negative cho cả hai.

**(g) POST nhận 403 dù user đủ quyền.** Có thể CSRF token thiếu. Trong test authorization, dùng `csrf()` hợp lệ rồi xác nhận quyền; đừng vội tắt CSRF toàn app.

**(h) Login path không còn được chain cung cấp.** Nếu `securityMatcher` chỉ bao phủ `/api/**`, `/login` có thể ngoài phạm vi. Với form login hãy cấu hình login page/processing URL trong phạm vi được bảo vệ và test redirect/POST chính xác.

**(i) Method security dừng hoạt động.** `@EnableMethodSecurity` chưa bật, method được gọi qua `new` hoặc self-invocation nên interceptor không chạy. Test direct Spring bean và ca bị từ chối; không suy từ HTTP matcher rằng method-level policy đang chạy.

**(j) Servlet/Reactive hoặc Jakarta bị trộn.** `HttpSecurity` khác `ServerHttpSecurity`. Spring Boot 3 chuyển phần lớn Servlet API sang `jakarta.*`; sửa dependency/import đúng thay vì thêm Spring Security 5 cũ vào project mới.

**(k) Thấy bean `AuthenticationManager` thì nghĩ mọi chain dùng cùng provider.** Chain có thể đặt manager riêng hoặc JWT decoder khác; test từng phương thức auth và đường chọn chain.

**(l) Dựa vào mặc định sai.** Custom `SecurityFilterChain` có thể làm Spring Boot không còn áp dụng default web-security chain. Hãy định nghĩa chính sách URL tường minh, kiểm các URL chưa nêu và kiểm HEAD/OPTIONS nếu ứng dụng cần.

## 11. Checklist nghiệm thu

- [ ] Phiên bản Spring Boot, Spring Framework và Spring Security tương thích, Java 17+, không trộn javax/jakarta sai.
- [ ] Không còn kế thừa `WebSecurityConfigurerAdapter` trong cấu hình mới.
- [ ] Có `@Bean SecurityFilterChain` cùng `return http.build()` và lambda DSL.
- [ ] Matcher cụ thể đứng trước matcher rộng; không lộ `/admin/**` hay API nhạy cảm.
- [ ] Các API public, authenticated, role/authority và fallback có kết quả đúng như baseline.
- [ ] Với nhiều chains, `@Order`, `securityMatcher` và fallback bao phủ mọi URL dự định.
- [ ] `UserDetailsService`/provider và `PasswordEncoder` đúng với dữ liệu tài khoản thực; không dùng password plaintext production.
- [ ] Không expose `AuthenticationManager` không cần thiết; nếu có, biết provider nào được chọn.
- [ ] Phân biệt `WebSecurityCustomizer.ignoring` với `permitAll`, xác minh security headers.
- [ ] CSRF/CORS/session/form login/logout/custom filter/error handling được chuyển và test.
- [ ] Nếu dùng `@PreAuthorize`, có `@EnableMethodSecurity` và test gọi Spring bean qua proxy.
- [ ] Test có cả credential đúng/sai và authority đủ/thiếu; kiểm POST với CSRF hợp lệ.
- [ ] URL không đăng ký có hành vi deny theo chính sách; tránh coi 404 là pass authorization.
- [ ] Build/tests chạy trước khi phát hành; đã xem lại 401/403/302 và filter chain trên staging.

## 12. Tài liệu chính thức

- Spring Team — *Spring Security without the WebSecurityConfigurerAdapter*: https://spring.io/blog/2022/02/21/spring-security-without-the-websecurityconfigureradapter
- Spring Security 5.8 & 6.0 release, adapter removal: https://spring.io/blog/2022/11/21/spring-security-5-8-and-6-0-are-now-ga/
- Spring Security — Java Configuration/Multiple SecurityFilterChains: https://docs.spring.io/spring-security/reference/servlet/configuration/java.html
- Spring Security — Authorize HttpServletRequests: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security — Authentication architecture: https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html
- Spring Security — MockMvc Integration: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/
- Spring Security 7 — What's New: https://docs.spring.io/spring-security/reference/7.0/whats-new.html

**Đạt yêu cầu khi:** Cấu hình mới dùng bean `SecurityFilterChain` và các bean authentication phù hợp, tất cả kiểm thử URL/role/CSRF của ứng dụng vẫn thể hiện đúng chính sách. Quá trình chuyển đổi phải bảo toàn quyền truy cập thực tế, kể cả ở những URL ít được gọi hoặc không được liệt kê.
