# Nhận diện javax.servlet, jakarta.servlet và các ví dụ thuộc thế hệ cũ

## 1. Đọc Spring Security theo phiên bản, không chỉ theo tên API

Một lỗi phổ biến khi học Spring Security là tìm một bài viết trên Internet, copy lớp cấu hình và gặp ngay `cannot find symbol`, `package javax.servlet does not exist` hoặc `WebSecurityConfigurerAdapter cannot be resolved`. Đôi khi code biên dịch được nhưng route lại mở rộng hơn dự định. Nguyên nhân có thể không nằm ở Java syntax, mà ở **thế hệ của Spring Boot, Spring Framework, Spring Security, Servlet API và thư viện phụ thuộc**.

Bài này thuộc phần **Phiên bản và học tiếp** của *Spring Security - fundamentals*. Nó giúp phân biệt:

- Mẫu **Spring Boot 2.x / Spring Framework 5.x / Spring Security 5.x**, thường còn `javax.servlet`, `WebSecurityConfigurerAdapter`, `authorizeRequests` và `antMatchers`.
- Mẫu **Spring Boot 3.x / Spring Framework 6.x / Spring Security 6.x**, dùng `jakarta.servlet`, bean `SecurityFilterChain` và `authorizeHttpRequests`.
- Mẫu **Spring Boot 4.x / Spring Framework 7.x / Spring Security 7.x**, vẫn thuộc namespace Jakarta nhưng có thêm thay đổi API và yêu cầu Lambda DSL.
- Trường hợp **WebFlux**: dùng `SecurityWebFilterChain`, `ServerHttpSecurity` và reactive `WebFilter`, không phải Servlet filter dù vẫn đang ở Boot 3 hay Boot 4.

Mục tiêu cuối cùng không chỉ làm ứng dụng “hết báo lỗi” mà là **giữ nguyên hoặc cải thiện chính sách bảo mật**, kiểm chứng các đường public/protected, role, password, CSRF, session, filter matching và quyền đối tượng sau khi chuyển phiên bản.

## 2. Bản đồ nhận diện nhanh các thế hệ

| Tín hiệu | Thế hệ cũ hay gặp | Thế hệ Boot 3 / Security 6 | Thế hệ Boot 4 / Security 7 |
| --- | --- | --- | --- |
| Spring Boot | 2.7.x hoặc cũ hơn | 3.0–3.5.x | 4.0/4.1+ |
| Spring Framework | 5.3.x | 6.x | 7.x |
| Spring Security | 5.x (5.7/5.8 là giai đoạn chuyển tiếp) | 6.x | 7.x |
| Môi trường Servlet | Java EE/Jakarta EE 8, package `javax.servlet` | Jakarta EE namespace `jakarta.servlet` | Vẫn là `jakarta.servlet`, nền Servlet mới hơn |
| Validation | `javax.validation` | `jakarta.validation` | `jakarta.validation` |
| JPA | `javax.persistence` | `jakarta.persistence` | `jakarta.persistence` |
| Java | Nhiều app chạy JDK 8/11 tùy bản 2.x | Tối thiểu **Java 17** | Tối thiểu **Java 17** theo Boot 4 hiện hành |
| Security config | `WebSecurityConfigurerAdapter` hoặc bean chain | `@Bean SecurityFilterChain` | Bean chain, Lambda DSL bắt buộc ở Security 7 |
| Cách xác thực thông tin | Đọc build và tài liệu được pin 5.x | Đọc build và tài liệu được pin 6.x | Đọc migration guide 7.x/Boot 4 |

Đây là **bản đồ suy luận, không phải quy tắc một-một**. Bean `SecurityFilterChain` xuất hiện từ Spring Security 5.4, trước thế hệ 6. `WebSecurityConfigurerAdapter` bị deprecated từ 5.7 và bị loại bỏ trong 6.0. Vì vậy một tutorial có `SecurityFilterChain` không tự chứng minh nó viết cho Security 6; phải nhìn phiên bản thật trong `pom.xml` hoặc `build.gradle`.

**Bản chạy cụ thể của bài:** ví dụ thực hành chọn **Spring Boot 3.5.16, Java 17+ và Security 6.x do BOM quản lý**. Bản Boot 3.5.16 đã được phát hành; đây là mốc minh họa ổn định về API, **không phải khuyến nghị chọn nhánh lâu dài cho production năm 2026**. Nhóm dự án đang dùng Boot 4/Security 7 phải tra migration docs của nhánh đó; không tự hạ dependency chỉ để khớp ví dụ.

## 3. `javax.servlet` và `jakarta.servlet` là hai kiểu nhị phân khác nhau

Trước Jakarta EE 9, các Servlet API thông dụng dùng `javax.servlet`:

```java
// Imports của hệ Servlet đời cũ
import javax.servlet.Filter;
import javax.servlet.FilterChain;
import javax.servlet.ServletException;
import javax.servlet.http.HttpServletRequest;
import javax.servlet.http.HttpServletResponse;
```

Từ Jakarta EE 9, namespace API chuyển sang `jakarta`, vì vậy dự án Spring Boot 3.x dùng:

```java
// Imports của hệ Jakarta Servlet
import jakarta.servlet.Filter;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
```

Hai class có cùng tên ngắn như `Filter` nhưng **khác fully-qualified class name**; chúng không tự chuyển đổi cho nhau. Một jar được compile cho `javax.servlet.Filter` có thể không link với filter chain dùng `jakarta.servlet.Filter`. Không sửa bằng cách thêm cả hai Servlet API jars để “IDE tìm được class”; việc này dễ che mâu thuẫn binary/runtime thay vì giải quyết nó.

### Bảng chuyển namespace thường gặp

| API cũ | API Jakarta mới | Chức năng |
| --- | --- | --- |
| `javax.servlet.Filter` | `jakarta.servlet.Filter` | Servlet filter |
| `javax.servlet.http.HttpServletRequest` | `jakarta.servlet.http.HttpServletRequest` | HTTP request |
| `javax.servlet.http.HttpServletResponse` | `jakarta.servlet.http.HttpServletResponse` | HTTP response |
| `javax.servlet.ServletException` | `jakarta.servlet.ServletException` | Servlet exception |
| `javax.persistence.Entity` | `jakarta.persistence.Entity` | JPA entity |
| `javax.persistence.Id` | `jakarta.persistence.Id` | JPA primary key |
| `javax.validation.Valid` | `jakarta.validation.Valid` | Validation |
| `javax.validation.constraints.NotBlank` | `jakarta.validation.constraints.NotBlank` | Bean Validation constraint |
| `javax.annotation.PostConstruct` | `jakarta.annotation.PostConstruct` | Lifecycle callback |
| `javax.transaction.Transactional` | `jakarta.transaction.Transactional` | Jakarta Transactions API |

**Cực kỳ quan trọng:** không phải mọi `javax.*` chuyển sang `jakarta.*`. Nhiều package thuộc **Java SE** vẫn giữ tên `javax`: `javax.crypto.Cipher`, `javax.net.ssl.SSLContext`, `javax.sql.DataSource`, `javax.xml.parsers.DocumentBuilder`, `javax.annotation.processing.Processor`. Không tồn tại phép đổi chung `javax.crypto` → `jakarta.crypto` cho JDK.

Cũng không đổi `org.springframework.transaction.annotation.Transactional`; đó là annotation của Spring, không phải Jakarta Transactions. Với nhiều API bên thứ ba, chỉ đổi import không đủ vì **artifact/version** cũng phải tương thích.

## 4. Chỉ nhìn import là chưa đủ: kiểm build và container

Spring Boot 2.x thường dùng Servlet container như Tomcat 9 (namespace `javax`). Spring Boot 3.5 dùng Tomcat 10.1/Servlet 6.0 mặc định và các thư viện Jakarta phù hợp qua dependency management. Spring Boot 4 có yêu cầu container mới hơn; phải xem trang **System Requirements** của đúng nhánh. Một WAR được compile cho Boot 3.x không thể kỳ vọng chạy an toàn trên Tomcat 9 chỉ vì các method vẫn tên `doFilter`.

Trong Maven, dấu hiệu đời cũ có thể là dependency trực tiếp `javax.servlet:javax.servlet-api`. Với Boot 3, Servlet API coordinate thuộc `jakarta.servlet:jakarta.servlet-api`, nhưng nếu dùng `spring-boot-starter-web` và embedded container thì **thường không cần khai báo riêng API dependency**. Hãy để Spring Boot BOM chọn version tương thích; không pin Servlet API tùy ý.

Dùng các lệnh sau tại thư mục chứa `pom.xml`:

```bash
java -version
mvn -version
mvn dependency:tree
mvn help:effective-pom
```

Cần kiểm:

- Spring Boot parent/BOM version, có bị override ở module con không.
- `spring-security-web`, `spring-security-config` và Spring Framework cùng thế hệ.
- `javax.servlet-api`/`jakarta.servlet-api` hoặc web container transitive gây xung đột.
- Hibernate/JPA/Validation libraries tương thích Jakarta.
- Third-party starters, custom filters, servlet listeners, test dependencies và WAR target container.

Với Gradle có thể dùng:

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-security-web --configuration runtimeClasspath
```

Trên Windows PowerShell/CMD, dùng `gradlew.bat` nếu wrapper project cung cấp. Dependency tree là **bằng chứng phiên bản runtime**, không chỉ là suy đoán từ một file import.

## 5. Nhận diện ngay một ví dụ `WebSecurityConfigurerAdapter` cũ

Ví dụ sau mang phong cách Spring Security 5:

```java
// ĐOẠN LỊCH SỬ — không thể copy nguyên vào Security 6/7
@Configuration
@EnableWebSecurity
public class LegacySecurity extends WebSecurityConfigurerAdapter {

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
```

Đây là **fragment lịch sử**, không phải file trong dự án chạy được ở mục 8. Các dấu hiệu:

1. `extends WebSecurityConfigurerAdapter`: dùng kế thừa một adapter framework, bị deprecated từ 5.7 và bị xóa trong 6.0.
2. `configure(HttpSecurity)` với `@Override`: thay vì bean `SecurityFilterChain`.
3. `authorizeRequests()`: DSL authorization cũ; mẫu hiện đại dùng `authorizeHttpRequests(...)`.
4. `antMatchers(...)`: matcher DSL cũ; Security 6 dùng `requestMatchers(...)` hoặc `RequestMatcher` cụ thể.
5. `.and().httpBasic()`: fluent/nested DSL đời trước; Security 7 yêu cầu Lambda DSL.
6. Dự án thường còn `javax.servlet.*` khi có custom filters và servlet hooks.

Một blog có các dấu hiệu này **không nhất thiết sai trong ngữ cảnh năm nó được viết**. Nhưng nếu mục tiêu là Boot 3/Security 6, không thêm lại adapter bằng dependency cũ chỉ để copy bài học. Hãy chuyển cấu trúc và **kiểm semantics** của policy.

### Mẫu cấu hình hiện đại tương ứng

```java
// FRAGMENT TRONG @Bean SecurityFilterChain CỦA SECURITY 6
http
    .authorizeHttpRequests(auth -> auth
        .requestMatchers("/public/**").permitAll()
        .requestMatchers("/admin/**").hasRole("ADMIN")
        .anyRequest().authenticated())
    .httpBasic(Customizer.withDefaults());

return http.build();
```

Mẫu này dùng `AuthorizationManager`-based authorization và Lambda DSL. Trong dự án thật, cần cấu hình khác như password encoder/provider, session, CSRF, OAuth2 hay exception handling tùy yêu cầu; một đoạn chuyển đổi hai dòng **chưa chứng minh** ứng dụng đã migrate đầy đủ.

## 6. Bảng chuyển API đời cũ sang Spring Security 6

| Code thế hệ cũ | Mẫu hiện đại | Cần kiểm thêm |
| --- | --- | --- |
| `extends WebSecurityConfigurerAdapter` | `@Bean SecurityFilterChain(HttpSecurity)` | Có bao nhiêu chain, matcher và fallback? |
| Override `configure(HttpSecurity)` | Cấu hình bean rồi `return http.build()` | Authentication/filter order giữ đúng? |
| `authorizeRequests()` | `authorizeHttpRequests(auth -> ...)` | Request authorization/dispatch semantics |
| `antMatchers(path)` | `requestMatchers(path)` | MVC/Ant matching semantics và thứ tự |
| `mvcMatchers(path)` | `requestMatchers(path)` hoặc matcher tường minh | Servlet path và MVC infrastructure |
| `http.antMatcher(path)` | `http.securityMatcher(path)` | Chọn phạm vi **cả chain** |
| `http.csrf().disable()` | `http.csrf(csrf -> csrf.disable())` *nếu thật cần* | Không làm giảm CSRF protection ngoài ý muốn |
| `.and().formLogin()` | `.formLogin(Customizer.withDefaults())` | Login page, session, success handler |
| `.and().httpBasic()` | `.httpBasic(Customizer.withDefaults())` | Client/entry point, HTTPS |
| `@EnableGlobalMethodSecurity(prePostEnabled=true)` | `@EnableMethodSecurity` | Method proxy, SpEL, parameter names |
| `configure(AuthenticationManagerBuilder)` | Bean `UserDetailsService` / `PasswordEncoder` / providers | Hash, account status, lookup |
| `web.ignoring().antMatchers(...)` | `WebSecurityCustomizer` hoặc cân nhắc `permitAll()` | Ignoring bỏ filter chain, không giống permitAll |

Đừng chỉ tìm/replace token. Những phép đổi đúng cú pháp có thể **khác bảo mật**:

- `web.ignoring()` thường bỏ các Spring Security filters và security headers; `permitAll()` vẫn xử lý request qua chain.
- `securityMatcher()` chọn chain; `requestMatchers()` bên trong `authorizeHttpRequests()` chọn authorization rule. Nếu không có chain nào match, Spring Security có thể **không bảo vệ request đó**.
- `hasRole("ADMIN")` thông thường kiểm authority `ROLE_ADMIN`, khác với `hasAuthority("ADMIN")` và `hasAuthority("SCOPE_admin")`.
- Cấu hình `anyRequest().permitAll()` có thể mở toàn bộ route mới; ưu tiên deny-by-default hoặc rule tổng thể theo yêu cầu.
- Khi migrate `authorizeRequests` sang `authorizeHttpRequests`, cần test HTTP method, path, servlet path, dispatcher types, role và error handling.

## 7. `securityMatcher` và `requestMatchers` — sai một chữ, lệch cả chain

Ví dụ minh họa cho nhiều chain:

```java
// FRAGMENT — các method phải đặt trong configuration class.
@Bean
@Order(1)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(a -> a
            .requestMatchers("/api/admin/**").hasRole("ADMIN")
            .anyRequest().authenticated())
        .httpBasic(Customizer.withDefaults())
        .build();
}

@Bean
SecurityFilterChain fallback(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(a -> a
            .anyRequest().denyAll())
        .build();
}
```

**Ý nghĩa:**

- `securityMatcher("/api/**")` nói chain đầu chỉ **áp dụng** cho URL `/api/**`.
- `requestMatchers("/api/admin/**")` tạo rule **bên trong chain đã được chọn**.
- `@Order(1)` ưu tiên chain đầu; fallback chain từ chối những gì chưa khớp.
- Nếu bỏ fallback chain, request ngoài `/api/**` có thể không đi qua Spring Security dù bạn viết `anyRequest().authenticated()` trong API chain.

Đây không phải cấu hình đầy đủ production: một số ứng dụng có CSRF, OAuth2/JWT, login, headers và filter custom phải đặt trong chain đúng. Tài liệu cũ dùng `antMatcher` trên `HttpSecurity` thường có ý nghĩa **giới hạn cả chain**, không được chuyển nhầm thành rule `requestMatchers` bên trong một chain global.

## 8. Ví dụ runnable Java 17+: Boot 3, `jakarta.servlet` và bean chain

Ví dụ hoàn chỉnh dưới đây chạy với **Java 17+, Maven, Spring Boot 3.5.16, Spring MVC và Spring Security 6.x**. Nó chứng minh custom Servlet filter hiện đại có chữ ký `jakarta.servlet` và policy HTTP có hành vi dự kiến.

Mục tiêu:

- `GET /api/public` cho anonymous, trả JSON.
- `GET /api/me` cần authenticated, trả username.
- `GET /api/admin` yêu cầu role ADMIN.
- Custom filter gắn header `X-Servlet-Namespace: jakarta` để chứng minh nó đã chạy.
- Account demo `alice/alice-pass` có role USER, `admin/admin-pass` có role ADMIN; password được mã hóa với `PasswordEncoder`.
- Test anonymous, password sai, role sai và admin đúng qua filter chain.

### 8.1. Cấu trúc project

```text
security-jakarta-demo/
├── pom.xml
└── src/
    ├── main/java/demo/
    │   ├── SecurityJakartaApplication.java
    │   ├── SecurityConfiguration.java
    │   ├── ServletMarkerFilter.java
    │   └── ApiController.java
    └── test/java/demo/
        └── SecurityJakartaTests.java
```

### 8.2. Maven `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>security-jakarta-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
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
```

Đây là **Maven POM hoàn chỉnh**, có thẻ `<plugin>` lồng đúng trong `<plugins>`. Không thêm `javax.servlet-api`; starter web chọn Jakarta Servlet container. Boot parent quản lý version của các Spring dependencies.

### 8.3. `src/main/java/demo/SecurityJakartaApplication.java`

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SecurityJakartaApplication {
    public static void main(String[] args) {
        SpringApplication.run(SecurityJakartaApplication.class, args);
    }
}
```

### 8.4. `src/main/java/demo/ServletMarkerFilter.java`

```java
package demo;

import java.io.IOException;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.web.filter.OncePerRequestFilter;

public final class ServletMarkerFilter extends OncePerRequestFilter {

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws ServletException, IOException {
        response.setHeader("X-Servlet-Namespace", "jakarta");
        chain.doFilter(request, response);
    }
}
```

`jakarta.servlet.FilterChain`, `ServletException`, `HttpServletRequest` và `HttpServletResponse` phải được dùng **đồng nhất**. Nếu thay một trong số này bằng bản `javax`, chữ ký `@Override` có thể không khớp, hoặc jar bị lỗi ở runtime.

**Tránh double registration:** filter được tạo bằng `new ServletMarkerFilter()` trong Spring Security chain, không đánh dấu `@Component` và không khai báo bean Servlet Filter riêng. Spring Boot có thể tự đăng ký Servlet `Filter` bean với container; nếu cũng thêm bean ấy vào security chain, filter có thể chạy hai lần hoặc sai thứ tự. Ví dụ này tránh tình huống đó.

Header `X-Servlet-Namespace` **chỉ là dấu hiệu demo**, không phải security header cần thêm vào production. Không bao giờ đưa token/session/password vào custom header để debug.

### 8.5. `src/main/java/demo/SecurityConfiguration.java`

```java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;

import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;

@Configuration
public class SecurityConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
                User.withUsername("alice")
                        .password(encoder.encode("alice-pass"))
                        .roles("USER").build(),
                User.withUsername("admin")
                        .password(encoder.encode("admin-pass"))
                        .roles("ADMIN").build());
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(HttpMethod.GET, "/api/public")
                            .permitAll()
                        .requestMatchers(HttpMethod.GET, "/api/me")
                            .authenticated()
                        .requestMatchers(HttpMethod.GET, "/api/admin")
                            .hasRole("ADMIN")
                        .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .formLogin(form -> form.disable())
                .addFilterBefore(
                        new ServletMarkerFilter(),
                        UsernamePasswordAuthenticationFilter.class)
                .build();
    }
}
```

**Giải thích khác với tutorial cũ:**

- Không còn `extends WebSecurityConfigurerAdapter`; chỉ có bean `SecurityFilterChain`.
- Không gọi `authorizeRequests` hay `antMatchers`; dùng `authorizeHttpRequests`/`requestMatchers` theo method/path.
- Lambda DSL không cần `.and()`.
- `hasRole("ADMIN")` yêu cầu authority `ROLE_ADMIN` từ `.roles("ADMIN")`.
- Password được hash bằng delegating encoder, không dùng `{noop}` cho production.
- `httpBasic` xử lý `Authorization: Basic ...`; khi chạy ngoài localhost cần HTTPS.
- `formLogin` chỉ được tắt cho demo API GET; CSRF vẫn giữ mặc định. Không coi HTTP Basic tự động stateless hoặc miễn nhiễm CSRF.
- `addFilterBefore` thêm filter theo vị trí chuẩn được Spring Security biết; không cần lớp adapter cũ.

### 8.6. `src/main/java/demo/ApiController.java`

```java
package demo;

import java.util.Map;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ApiController {

    @GetMapping("/api/public")
    public Map<String, String> publicEndpoint() {
        return Map.of("access", "public");
    }

    @GetMapping("/api/me")
    public Map<String, String> me(Authentication auth) {
        return Map.of("username", auth.getName());
    }

    @GetMapping("/api/admin")
    public Map<String, String> admin() {
        return Map.of("access", "admin");
    }
}
```

Controller dùng `Authentication` do Spring Security cấp, không tin giá trị `isAdmin` hoặc `role` từ JSON/body. Nó không cần dùng Servlet API trực tiếp; điều này bình thường: **không có lý do thêm import Jakarta vào controller chỉ để chứng minh “code mới”**.

### 8.7. `src/test/java/demo/SecurityJakartaTests.java`

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc(addFilters = true)
class SecurityJakartaTests {

    @Autowired
    MockMvc mvc;

    @Test
    void publicApiAndJakartaFilterWork() throws Exception {
        mvc.perform(get("/api/public"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.access").value("public"))
                .andExpect(header().string(
                        "X-Servlet-Namespace", "jakarta"));
    }

    @Test
    void anonymousCannotReadMe() throws Exception {
        mvc.perform(get("/api/me"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void wrongPasswordIsRejected() throws Exception {
        mvc.perform(get("/api/me")
                        .with(httpBasic("alice", "wrong")))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void realAlicePasswordWorks() throws Exception {
        mvc.perform(get("/api/me")
                        .with(httpBasic("alice", "alice-pass")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.username").value("alice"));
    }

    @Test
    void userIsForbiddenOnAdmin() throws Exception {
        mvc.perform(get("/api/admin")
                        .with(httpBasic("alice", "alice-pass")))
                .andExpect(status().isForbidden());
    }

    @Test
    void adminIsAllowed() throws Exception {
        mvc.perform(get("/api/admin")
                        .with(httpBasic("admin", "admin-pass")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.access").value("admin"));
    }
}
```

Với `@SpringBootTest` và `@AutoConfigureMockMvc(addFilters = true)`, test đi qua security filters của application context. `httpBasic(...)` đặt header credential để provider thật của demo xác thực. **`@WithMockUser` hoặc `with(user(...))`** phù hợp để kiểm authorization với principal giả, nhưng **không** kiểm mật khẩu. Không thay các test wrong/correct password bằng mock principal rồi kết luận authentication thành công.

`MockMvc` không mở HTTP socket; nếu cần kiểm server/TLS/Servlet container thực, chạy jar và thêm integration test với `RANDOM_PORT` hoặc HTTP client. Header demo cho thấy custom filter trong chain đã được gọi, không chứng minh mọi servlet filter của môi trường production đúng.

### 8.8. Build và thử bằng curl

Cần JDK 17+, Maven 3.6.3+ và dependencies được tải. Tại thư mục có `pom.xml`:

```bash
java -version
mvn -version
mvn -q test
mvn -q -DskipTests package
java -jar target/security-jakarta-demo-0.0.1-SNAPSHOT.jar
```

Terminal thứ hai:

```bash
curl -i http://localhost:8080/api/public
curl -i http://localhost:8080/api/me
curl -i -u alice:wrong http://localhost:8080/api/me
curl -i -u alice:alice-pass http://localhost:8080/api/me
curl -i -u alice:alice-pass http://localhost:8080/api/admin
curl -i -u admin:admin-pass http://localhost:8080/api/admin
```

Các HTTP status **kỳ vọng** theo thứ tự: **200, 401, 401, 200, 403, 200**. JSON khi gọi public:

```json
{
  "access": "public"
}
```

Khi Alice đọc `/api/me`:

```json
{
  "username": "alice"
}
```

Khi admin đọc `/api/admin`:

```json
{
  "access": "admin"
}
```

Response public có header `X-Servlet-Namespace: jakarta`; mã test kiểm chính xác tên/giá trị header này. Thứ tự JSON/headers/body lỗi có thể thay đổi tùy Spring/Jackson. **Đây là output dự kiến, không phải log thực thi Maven được ghi lại.** Không dùng tài khoản/mật khẩu demo cho production hay Basic credentials trên đường truyền HTTP công khai.

## 9. Những mảnh code legacy có thể đọc nhưng không dán vào dự án mới

Một custom filter đời cũ có thể viết:

```java
// FRAGMENT CŨ
import javax.servlet.FilterChain;
import javax.servlet.ServletException;
import javax.servlet.http.HttpServletRequest;
import javax.servlet.http.HttpServletResponse;
```

Chữ ký mới cần nhất quán `jakarta.servlet.*` như ví dụ `ServletMarkerFilter`. Nếu trộn `javax.servlet.FilterChain` với `jakarta.servlet.http.HttpServletRequest`, `@Override` có thể không còn match method của base class. Lỗi “method does not override or implement a method from a supertype” là một tín hiệu để so chữ ký full package.

Cấu hình cũ:

```java
@EnableGlobalMethodSecurity(prePostEnabled = true)
public class OldMethodConfig {}

// Trong adapter/config cũ:
http.authorizeRequests().antMatchers("/admin/**").hasRole("ADMIN");
```

Chuyển sang `@EnableMethodSecurity` và `@PreAuthorize` trên Spring bean được quản lý; request authorization mới dùng `authorizeHttpRequests`. Nhưng **migrating method security không tự làm an toàn dữ liệu theo owner/tenant**. `hasRole("ADMIN")` chỉ là coarse permission, service vẫn phải kiểm tài nguyên.

Mẫu cũ `web.ignoring().antMatchers("/css/**")` cũng cần review: ignoring bỏ filter chain, còn `permitAll()` cho phép request đi qua chain và vẫn nhận các bảo vệ khác. Không mặc định coi hai hành vi tương đương.

## 10. JPA, Bean Validation và Jakarta không chỉ là chuyện Security

Trong dự án Boot 3+, các imports thường thay cùng nhau:

```java
// BẢN CŨ
import javax.persistence.Entity;
import javax.persistence.Id;
import javax.validation.Valid;
import javax.validation.constraints.NotBlank;
```

```java
// BẢN MỚI
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
```

Những fragments này chỉ minh họa namespace, không có entity/controller hoàn chỉnh. Khi nâng:

- Dùng JPA/Hibernate provider tương thích Jakarta thay vì giữ một phiên bản ORM cũ.
- Khi cần Bean Validation trong Spring MVC, khai báo `spring-boot-starter-validation` phù hợp; đừng giả định starter web tự mang mọi validator.
- Không đổi `javax.sql.DataSource` của JDBC; đó là Java SE.
- Không đổi `org.springframework.transaction.annotation.Transactional`; chỉ Jakarta Transactions API có namespace mới.
- Kiểm cả thư viện bên thứ ba: một framework security filter compile bằng `javax` có thể làm app không start dù source của bạn đã đổi toàn bộ imports.
- Nếu dùng annotation processing, generated code/JPA metamodel cũ cũng có thể đưa `javax` vào build output; clean/rebuild sau khi sửa.

Tách migration thành hai câu hỏi: **mã nguồn đã đổi namespace đúng chưa?** và **runtime dependencies đã cùng thế hệ Jakarta chưa?** Cả hai cần được xác nhận.

## 11. Đừng nhầm Servlet MVC với WebFlux

Spring MVC chạy trên Servlet container và dùng `HttpSecurity`, `SecurityFilterChain`, `jakarta.servlet.Filter` khi cần Servlet Filter. Spring WebFlux có thể dùng Reactor Netty và dùng `ServerHttpSecurity`, `SecurityWebFilterChain`, reactive `WebFilter`, không dùng Servlet Filter trong luồng reactive thông thường.

Ví dụ reactive (fragment, không phải chương trình độc lập):

```java
@Bean
SecurityWebFilterChain reactiveSecurity(ServerHttpSecurity http) {
    return http
            .authorizeExchange(ex -> ex
                    .pathMatchers("/public").permitAll()
                    .anyExchange().authenticated())
            .httpBasic(Customizer.withDefaults())
            .build();
}
```

Nếu gặp tutorial WebFlux không có `javax.servlet` hoặc `jakarta.servlet`, đó **không** nhất thiết là tutorial cũ. Đó có thể là stack khác. Hãy kiểm `spring-boot-starter-webflux`, application type và web server thực; nếu project có cả web và webflux starters, không đoán stack chỉ từ một import.

## 12. Các thay đổi bảo mật không được bỏ qua khi nâng version

### HTTP matchers và fallback

Sự khác nhau giữa `antMatchers`, `mvcMatchers` và `requestMatchers` có thể ảnh hưởng xử lý path pattern, servlet path và HTTP method. Test cả URL được phép và URL tương tự phải bị chặn. Với nhiều security chains, kiểm `securityMatcher` và chain order để không có request rơi ngoài tất cả chain.

### CSRF và authentication model

Nhiều ví dụ cũ viết `http.csrf().disable()` để gọi API bằng Postman. Trong Lambda DSL, có thể biểu diễn tương đương cú pháp bằng `http.csrf(csrf -> csrf.disable())` — nhưng **không nên làm thế mặc định**. Các ứng dụng cookie/session và browser credential models có rủi ro CSRF; chỉ miễn trừ khi có lý do kiến trúc và test rõ. `with(csrf())` trong Spring Security Test kiểm request có CSRF token, không kiểm UI đã render token.

### Method security

`@EnableGlobalMethodSecurity(prePostEnabled=true)` thuộc mẫu cũ; dùng `@EnableMethodSecurity` khi nâng và test `@PreAuthorize`/`@PostAuthorize`. Nếu SpEL tham chiếu tên tham số, migration guide khuyên kiểm compile flag `-parameters`. Spring AOP proxy có thể không intercept self-invocation, nên không dựa duy nhất vào annotation trên method gọi nội bộ cùng bean.

### SecurityContext và dispatch

Migrations Security 6 có thay đổi liên quan servlet dispatch types và security context persistence. Một request `ERROR`/`FORWARD` hoặc async có thể bị chặn nếu rule chưa tính tới. Không mở `permitAll("/**")` để chữa 403; hãy kiểm dispatcher types, exception handling, session persistence và các rule theo release.

### Role/scope và các thay đổi không do namespace

`hasRole("ADMIN")` mặc định kiểm `ROLE_ADMIN`; `hasAuthority("SCOPE_reports.read")` yêu cầu một authority có tên chính xác. Khi đổi JWT converter hoặc OAuth2 integration, không tự gán scope thành role nếu policy chưa định nghĩa điều đó. Đổi `javax` thành `jakarta` không giải quyết lỗi mapping authority.

### Browser/UI/static resources

`web.ignoring()` có thể làm static files bỏ qua security filters/headers; `permitAll()` trong authorization rules không làm như vậy. Test UI login/logout, session cookies, redirects và các tài nguyên CSS/JS khi migrate để tránh lỗi khó phát hiện bằng unit test.

## 13. Các thông báo lỗi và cách khắc phục có hệ thống

| Lỗi/triệu chứng | Khả năng cần kiểm | Hướng giải quyết |
| --- | --- | --- |
| `package javax.servlet does not exist` | Code `javax` trên Boot 3/Jakarta classpath | Chuyển imports và thư viện cùng thế hệ |
| `package jakarta.servlet does not exist` | Boot 2/Servlet API cũ hoặc thiếu dependency | Kiểm Boot version/starter/runtime |
| `NoClassDefFoundError: javax/servlet/Filter` | Jar cũ yêu cầu `javax` trên runtime Jakarta | Nâng/thay library, xem dependency tree |
| `NoClassDefFoundError: jakarta/servlet/Filter` | Servlet API/container quá cũ | Dùng container Jakarta phù hợp |
| `method does not override...` | Chữ ký mix `javax` và `jakarta` hoặc API khác | Đối chiếu full class names của tham số |
| `cannot find symbol: WebSecurityConfigurerAdapter` | Code Security 5 trên Security 6/7 | Bean `SecurityFilterChain` |
| `cannot find symbol: antMatchers` | DSL cũ đã bị bỏ | `requestMatchers` + test semantics |
| 401 sau migrate | Authentication/session/entry point thay đổi | Test credentials và context |
| 403 sau migrate | Role, CSRF, dispatch, matcher hoặc method security | Xác định filter/rule từ chối |
| 200 cho route đáng ra protected | Chain không match hoặc fallback quá rộng | Kiểm `securityMatcher` và deny-by-default |
| Boot 3 WAR không chạy Tomcat 9 | WAR Jakarta trên Servlet container `javax` | Nâng container cho Jakarta |
| `@Valid` không hoạt động | Thiếu Jakarta validation provider/starter | Kiểm starter và constraints |

**Cách debug:** trước hết xác định runtime version và dependency tree; sau đó đọc lỗi compile/class loading; cuối cùng test từng nhóm hành vi. Thêm tùy tiện jar `javax.servlet-api` vào project Boot 3 để biến lỗi compile thành runtime conflict không phải giải pháp.

Nếu có `rg` (ripgrep), tìm dấu vết code cũ:

```bash
rg -n 'javax\.servlet|javax\.persistence|javax\.validation|WebSecurityConfigurerAdapter|authorizeRequests\(|antMatchers\(|mvcMatchers\(|EnableGlobalMethodSecurity' src
```

Lệnh này **chỉ liệt kê vị trí cần kiểm**, không tự sửa. Khi search source tree lớn, xác định test fixtures/migration code lịch sử trước khi xóa; không mọi lần xuất hiện `javax` đều cần thay, nhất là ở module không thuộc Jakarta.

## 14. Quy trình nâng cấp có kiểm thử và khả năng rollback

1. **Chốt nguồn và đích:** Boot 2.7/Security 5 → Boot 3.x/Security 6; hay Boot 3.5/Security 6 → Boot 4/Security 7. Hai bài toán có migration guide khác nhau.
2. **Nâng đến bản bảo trì và đọc deprecations:** Security 5.8 là bước chuẩn bị chính thức cho Security 6. Không override dependency tùy ý chỉ để ép API mới.
3. **Kiểm Java/toolchain:** Boot 3 yêu cầu Java 17+, Maven/Gradle tương thích; kiểm cả CI và runtime container.
4. **Nâng Jakarta ecosystem:** Servlet container, JPA provider, Validation, javax-based libraries, WAR packaging.
5. **Chuyển Security config:** bean chain, Lambda DSL, request matchers, method security, authentication providers/encoders.
6. **Lập bảng chính sách trước–sau:** public/protected paths, methods, roles/scopes, owner/tenant checks, login/logout, CSRF, session, static resources.
7. **Chạy unit + MockMvc + HTTP integration:** credential sai/đúng, 401/403, missing CSRF, path không match, multiple chains, dispatch types nếu dùng.
8. **Kiểm môi trường triển khai:** embedded jar hoặc WAR, reverse proxy, TLS, ingress, CORS, session store, IdP/OAuth2/JWT issuer nếu có.
9. **Không sửa test bằng cách nới quyền:** tránh `anyRequest().permitAll()` chỉ vì gặp 403.
10. **Giữ dependency lock và rollback plan:** ghi lại BOM version, plugin/container versions, kết quả regression tests và những thay đổi security có chủ đích.

Thực hành tốt: chia migration thành một loạt commit nhỏ có thể review, không đồng thời thay namespace, rewrite authorization và đổi kiến trúc authentication mà không có tests đối chiếu.

## 15. Học tiếp với Spring Security 7 và Spring Boot 4

Thế hệ Security 7 đã thay đổi thêm API và yêu cầu Lambda DSL, trong khi Spring Boot 4 dựa trên Spring Framework 7 và Servlet/container mới hơn. **Namespace `jakarta.servlet` vẫn còn**, nhưng chỉ đổi imports không đủ để nâng 6 → 7.

Khi học hoặc migrate tiếp:

- Luôn tra docs **được pin theo phiên bản** như `/6.5/` khi dự án dùng Security 6.5. Trang `/reference/` không pin có thể hiển thị version mới nhất và API không có trong project.
- Với Boot 2.7, xem **Boot 3.0 Migration Guide** và **Security 5.8 → 6.0** trước.
- Với Boot 3.x, xem **Security 6.5 → 7.0** và **Boot 3.5 → 4.0**; cân nhắc third-party starters, Jackson, testing và JVM/container requirements.
- Học sâu `Authentication`, `SecurityContext`, `AuthorizationManager`, `SecurityFilterChain`, Servlet vs reactive — đây là các khái niệm bền hơn tên method DSL.
- Nếu tutorial dùng `.and()`, `WebSecurityConfigurerAdapter` hoặc `javax.servlet`, đánh dấu rõ **mục tiêu cũ** trước khi quyết định rewrite.

Không hạ dependency Security hoặc Java runtime của dự án production chỉ để chạy một blog từ năm 2021. Hãy giữ stack đã được tổ chức chấp thuận và dịch ý nghĩa của tutorial sang API tương thích.

## 16. Những nhầm lẫn cần tránh

1. “Mọi `javax.*` đều phải chuyển `jakarta.*`” — sai vì nhiều package thuộc Java SE.
2. “Thêm cả hai Servlet API jars là tương thích” — sai; các kiểu nhị phân khác nhau.
3. “`SecurityFilterChain` chỉ tồn tại trong Security 6” — sai, có từ Security 5.4.
4. “`WebSecurityConfigurerAdapter` deprecated vẫn tồn tại trong Security 6” — sai, đã bị xóa.
5. “`antMatchers` và `requestMatchers` có thể đổi tên mà không kiểm HTTP behavior” — nguy hiểm.
6. “`securityMatcher` và `requestMatchers` là giống nhau” — một cái chọn chain, một cái chọn rule.
7. “Dùng `.and()` trên Security 7 như tutorial cũ” — không còn là DSL được hỗ trợ như trước.
8. “Bỏ `@EnableMethodSecurity` vì annotation `@PreAuthorize` tự chạy” — phải bật đúng và gọi qua Spring proxy.
9. “Tắt CSRF toàn bộ để test POST pass” — có thể tạo lỗ hổng cho browser clients.
10. “`web.ignoring` và `permitAll` giống nhau” — khác ở việc request có đi qua filters không.
11. “Tomcat 9 chạy WAR Boot 3 bình thường” — namespace/container không tương thích.
12. “Code compile nghĩa là policy không đổi” — tests còn phải kiểm 401/403, roles, matcher, session.
13. “`javax.crypto` phải đổi thành `jakarta.crypto`” — không phải Jakarta EE API.
14. “JPA/Validation không liên quan nâng Boot vì bài chỉ về Security” — Boot 3 nâng Jakarta ở cả ecosystem.
15. “WebFlux lỗi Servlet filter thì cứ thêm `jakarta.servlet-api`” — reactive stack dùng WebFilters.
16. “`@WithMockUser` chứng minh mật khẩu đúng” — mock principal bypass credential validation.
17. “Admin role đủ để đọc mọi tenant/object” — phải kiểm object-level authorization.
18. “Mọi `<dependency>` hoặc parent POM tự có version tương thích” — transitive/overrides có thể phá BOM.
19. “Chỉ ẩn endpoint khỏi menu là bảo vệ URL” — server vẫn cần authorization.
20. “Docs mới nhất luôn khớp version dự án” — phải pin version docs và so API.

## 17. Checklist khi đọc một ví dụ trên Internet

- [ ] Xác định Boot/Framework/Security/JDK versions thực bằng build và dependency tree.
- [ ] Xác định MVC Servlet hay WebFlux, embedded jar hay WAR external container.
- [ ] Xem imports `javax.servlet`/`jakarta.servlet`; không thay bừa package Java SE.
- [ ] Xác nhận JPA/Validation/thư viện bên thứ ba tương thích Jakarta.
- [ ] Gặp `WebSecurityConfigurerAdapter`, `authorizeRequests`, `antMatchers` hay `.and()` thì kiểm version tutorial.
- [ ] Chuyển sang bean `SecurityFilterChain` và Lambda DSL khi phù hợp.
- [ ] Phân biệt `securityMatcher` chọn chain với `requestMatchers` chọn rule.
- [ ] Kiểm thứ tự path/method rules, fallback và nhiều filter chains.
- [ ] Giữ behavior authentication, role prefix, CSRF, session, login/logout và method security.
- [ ] Không dùng `web.ignoring` cho protected endpoints; đánh giá static resource policy.
- [ ] Viết test 200/401/403, anonymous, credentials sai và route không mong muốn.
- [ ] Thử object ID/tenant khác, đừng chỉ kiểm user đã đăng nhập.
- [ ] Kiểm Servlet container version trước khi deploy WAR.
- [ ] Không hard-code password hoặc để `permitAll("/**")` ở production chỉ vì tutorial demo.
- [ ] Chọn tài liệu chính thức của đúng release khi có khác biệt API.

## 18. Bài tập tự luyện

1. Một đoạn code chứa `javax.servlet.Filter`, `antMatchers` và `WebSecurityConfigurerAdapter`. Đặt giả thuyết về generation và nêu cách xác minh.
2. Vì sao `javax.crypto.Cipher` không cần đổi thành `jakarta.crypto.Cipher`?
3. Giải thích khác biệt ở runtime giữa `javax.servlet.http.HttpServletRequest` và `jakarta.servlet.http.HttpServletRequest`.
4. Cấu hình Security 5 dùng `configure(HttpSecurity)`; cần tạo những bean nào cho Security 6?
5. Phân biệt `securityMatcher("/api/**")` và `requestMatchers("/api/admin/**")` với một request `/health`.
6. Nếu có API chain nhưng không fallback, request ngoài chain được bảo vệ chắc chắn không? Vì sao?
7. Vì sao thêm `javax.servlet-api` vào Boot 3 chưa chắc sửa `NoClassDefFoundError`?
8. Khi chuyển `web.ignoring` sang `permitAll`, security headers có thể khác thế nào?
9. Vì sao `@WithMockUser` được 200 không chứng minh username/password provider hoạt động?
10. Một WAR Boot 3 không chạy trên Tomcat 9: nên kiểm điều gì?
11. Thế nào là một test phát hiện lỗi `antMatchers` → `requestMatchers` thay đổi semantics?
12. Khi chuyển từ Security 6 sang 7, vì sao Lambda DSL và migration docs quan trọng?
13. Nêu ba lỗi có thể được thấy ngay lúc compile và ba lỗi chỉ xuất hiện khi runtime/security tests.
14. Vì sao một ứng dụng WebFlux không cần import `jakarta.servlet.Filter`?
15. Hãy viết kế hoạch migration 2.7 → 3.5 gồm version, Jakarta, filter chain, passwords và regression tests.

## 19. Tài liệu chính thức theo version

- [Spring Boot 3.0 Migration Guide — Jakarta EE và Java 17](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.0-Migration-Guide)
- [Spring Boot 3.5 System Requirements](https://docs.spring.io/spring-boot/3.5/system-requirements.html)
- [Spring Security 6.5 — Migrating to 6.0](https://docs.spring.io/spring-security/reference/6.5/migration/index.html)
- [Spring Security 6.5 — Servlet Migration](https://docs.spring.io/spring-security/reference/6.5/migration/servlet/index.html)
- [Spring Security 6.5 — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html)
- [Spring Security 6.5 — Java Configuration and Matchers](https://docs.spring.io/spring-security/reference/6.5/servlet/configuration/java.html)
- [Spring Security 6.5 — Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html)
- [Spring Security 6.5 — MockMvc Testing](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/index.html)
- [Spring Security 6.5 — Lambda DSL Migration to 7](https://docs.spring.io/spring-security/reference/6.5/migration-7/configuration.html)
- [Spring Security 7 — Migrating to 7.0](https://docs.spring.io/spring-security/reference/migration/)
- [Spring Security without WebSecurityConfigurerAdapter — Spring team](https://spring.io/blog/2022/02/21/spring-security-without-the-websecurityconfigureradapter)
- [Spring Boot 4 System Requirements](https://docs.spring.io/spring-boot/system-requirements.html)

**Điểm ghi nhớ:** `javax.servlet` → `jakarta.servlet` là **ranh giới API và binary compatibility**, còn `WebSecurityConfigurerAdapter` → `SecurityFilterChain` là **thay đổi cấu hình Spring Security**. Chỉ hoàn thành migration khi **dependencies, imports, filter chains và test bảo mật** đều phù hợp với phiên bản dự án, không phải khi IDE hết gạch đỏ.
