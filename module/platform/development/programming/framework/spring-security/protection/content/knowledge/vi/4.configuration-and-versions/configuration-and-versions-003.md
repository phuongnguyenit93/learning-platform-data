# Cấu hình theo bean thay cho các ví dụ kế thừa cấu hình cũ

> **Chương:** Cấu hình và phiên bản  
> **Module:** `SPRING_SECURITY_HTTP_PROTECTION`  
> **Phạm vi:** Cấu hình phòng vệ HTTP và trình duyệt trong Spring Security bằng các bean tường minh cho **Servlet / Spring MVC** và **Reactive / WebFlux**: CSRF, CORS, security headers, CSP, HSTS, HTTP firewall, session, xác thực và phân quyền.  
> **Bối cảnh phiên bản:** `WebSecurityConfigurerAdapter` bị deprecate từ Spring Security **5.7** và bị loại bỏ ở **6.0**. Spring Security **7.x** yêu cầu sử dụng Lambda DSL trong cấu hình Java. Các ví dụ mới trong bài sử dụng phong cách cấu hình được tài liệu Spring Security hiện đại khuyến nghị.

## 1. Vì sao phải thay lối kế thừa bằng cấu hình theo bean?

Nhiều bài hướng dẫn Spring Security cũ bắt đầu bằng:

```java
@Configuration
@EnableWebSecurity
public class SecurityConfig extends WebSecurityConfigurerAdapter {

    @Override
    protected void configure(HttpSecurity http) throws Exception {
        // Chính sách bảo vệ URL, xác thực, CSRF, headers...
    }

    @Override
    protected void configure(AuthenticationManagerBuilder auth)
            throws Exception {
        // Nguồn user và phương thức xác thực...
    }
}
```

Đây là **minh họa mã lịch sử**: `WebSecurityConfigurerAdapter` không còn tồn tại trong các dòng Spring Security 6/7. Cố sao chép ví dụ trên vào dự án Spring Boot 3/4 thường làm ứng dụng không biên dịch được, hoặc khiến người học tìm cách thêm một phiên bản Security cũ vào classpath. Điều này gây rủi ro tương thích và duy trì bảo mật.

Phong cách hiện đại tổ chức cấu hình thành **các bean có trách nhiệm rõ ràng**:

```text
ApplicationContext
    |
    +-- SecurityFilterChain bean             (Servlet)
    |      |
    |      +-- HttpSecurity / Lambda DSL
    |      +-- URL authorization, CSRF, CORS
    |      +-- headers, CSP, HSTS, session, login
    |
    +-- UserDetailsService bean              (Servlet, nếu dùng username/password)
    +-- PasswordEncoder bean                 (nếu cần mã hóa/kiểm tra mật khẩu)
    +-- AuthenticationProvider/Manager bean  (khi cần tùy chỉnh xác thực)
    +-- CorsConfigurationSource bean         (nguồn chính sách CORS)
    +-- WebSecurityCustomizer bean           (tùy chỉnh WebSecurity khi thật cần)

Ứng dụng WebFlux tương ứng
    |
    +-- SecurityWebFilterChain bean          (Reactive)
    |      +-- ServerHttpSecurity / Lambda DSL
    +-- ReactiveUserDetailsService bean      (nếu dùng username/password)
    +-- PasswordEncoder bean
    +-- ReactiveAuthenticationManager bean   (nếu cần)
    +-- Reactive CorsConfigurationSource bean
```

Các bean này do Spring quản lý thông qua dependency injection, nên có thể cấu hình, thay thế, kiểm thử và kết hợp chúng theo từng nhu cầu cụ thể. **Cấu hình theo bean không tự động làm chính sách an toàn hơn**: bạn vẫn phải xác định request nào được bảo vệ, ai được truy cập, cách giữ phiên và CSRF/CORS/headers có được áp dụng đúng hay không.

### Mục tiêu sau bài học

- Phân biệt các điểm mở rộng cũ với bean tương ứng, tránh sử dụng API đã bị loại bỏ.
- Viết cấu hình Servlet có `SecurityFilterChain`, nguồn xác thực và policy CORS rõ ràng.
- Viết cấu hình Reactive có `SecurityWebFilterChain` và `ReactiveUserDetailsService`.
- Hiểu khi nào cần `AuthenticationManager`, `AuthenticationProvider`, `WebSecurityCustomizer` và khi nào nên để framework cấu hình mặc định.
- Giữ được bảo vệ CSRF, CORS, CSP/HSTS, HTTP firewall và session khi chuyển cấu hình.
- Phát hiện lỗi do Spring Boot auto-configuration, nhiều filter chain, thứ tự matcher hoặc bean cấu hình trùng lặp.

## 2. Ma trận chuyển đổi từ API cũ sang bean hiện đại

| Cách cũ | Cách mới | Lưu ý về bảo mật |
| --- | --- | --- |
| `extends WebSecurityConfigurerAdapter` | Lớp `@Configuration` thông thường, khai báo các `@Bean` | Không còn base class để override |
| `configure(HttpSecurity http)` | `@Bean SecurityFilterChain filterChain(HttpSecurity http)` + `http.build()` | Đảm bảo toàn bộ URL cần bảo vệ có chain phù hợp |
| `configure(WebSecurity web)` | `@Bean WebSecurityCustomizer` nếu thực sự cần | `web.ignoring()` bỏ qua **toàn bộ** Spring Security filter chain |
| `configure(AuthenticationManagerBuilder auth)` với in-memory user | `@Bean UserDetailsService` / `InMemoryUserDetailsManager` | Không dùng password dạng plain text trong production |
| `auth.jdbcAuthentication()` | `@Bean JdbcUserDetailsManager` hoặc repository/provider tùy chỉnh | Kiểm soát schema, password hashing, vòng đời tài khoản |
| `auth.ldapAuthentication()` | Factory/provider/manager LDAP riêng | Không copy cấu hình LDAP cũ khi chưa kiểm tra API tương thích |
| `authenticationManagerBean()` từ adapter | `@Bean AuthenticationManager` khi cần expose/tùy chỉnh | Không tạo nhiều authentication manager không rõ phạm vi |
| `http.authorizeRequests().antMatchers(...)` | `http.authorizeHttpRequests(a -> a.requestMatchers(...))` | Cần rà soát matcher khi nâng phiên bản |
| `http.formLogin().and().csrf()` | `http.formLogin(Customizer.withDefaults()).csrf(Customizer.withDefaults())` | Lambda DSL cần cho Spring Security 7 |
| Cấu hình Reactive có `ServerHttpSecurity` | `@Bean SecurityWebFilterChain` | Dùng WebFlux API, không dùng `HttpSecurity` Servlet |

**Quan trọng:** một số bài viết cũ giới thiệu `WebSecurityCustomizer` với `antMatchers`; đó là cú pháp lịch sử. Khi dùng Spring Security 6/7, ưu tiên sử dụng `requestMatchers` trong cấu hình phân quyền và **`permitAll()` cho tài nguyên công khai**. Không giữ lại một cách máy móc mã `web.ignoring()` của tài liệu cũ.

## 3. Các mốc phiên bản cần nhớ

| Mốc Spring Security | Hệ quả đối với cấu hình |
| --- | --- |
| **5.4** | Bắt đầu hỗ trợ xây dựng filter chain thông qua `@Bean SecurityFilterChain` |
| **5.7** | `WebSecurityConfigurerAdapter` được đánh dấu deprecated, khuyến nghị chuyển sang cấu hình theo thành phần |
| **6.0** | Adapter bị loại bỏ; cần bean thay thế và xử lý các thay đổi Java/Jakarta khi chuyển lên Spring Boot 3 |
| **6.5** | Dòng chuẩn bị chuyển lên 7, nên xử lý các API deprecated và migration warnings |
| **7.x** | Lambda DSL bắt buộc cho các API cấu hình Java; phải thay các chuỗi `.and()` và method cấu hình không tham số kiểu cũ |

Nếu đang nâng dự án Spring Boot 2.7 → 3.x → 4.x, **chọn dòng Boot trước** và dùng các phiên bản Framework/Security do Boot quản lý. Không chữa lỗi thiếu `WebSecurityConfigurerAdapter` bằng cách thêm bản `spring-security-config` cũ trong ứng dụng đang dùng Boot/Framework mới. Nếu cần tính năng bảo vệ HTTP mới, hãy nâng tổ hợp Boot/Framework/Security có tương thích đã công bố.

## 4. Lối cũ: nhận diện các trách nhiệm trộn trong một adapter

Đoạn ví dụ sau thuộc phong cách **Spring Security 5.x cũ**, chỉ để đọc/di chuyển, **không dùng làm mẫu chạy với 6/7**:

```java
// LEGACY ONLY: không biên dịch với Spring Security 6/7.
@Configuration
@EnableWebSecurity
class OldSecurityConfig extends WebSecurityConfigurerAdapter {

    @Override
    protected void configure(HttpSecurity http) throws Exception {
        http
            .authorizeRequests()
                .antMatchers("/public/**").permitAll()
                .antMatchers("/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated()
                .and()
            .formLogin()
                .and()
            .csrf();
    }

    @Override
    protected void configure(AuthenticationManagerBuilder auth)
            throws Exception {
        auth.inMemoryAuthentication()
            .withUser("demo")
            .password("{noop}demo")
            .roles("USER");
    }
}
```

Từ ví dụ này, tách hai trách nhiệm:

1. **Chính sách request:** phạm vi URL, quy tắc truy cập, login/logout, CSRF/CORS/headers, session → bean `SecurityFilterChain`.
2. **Nguồn danh tính:** dữ liệu người dùng, cách mã hóa mật khẩu và xác thực → bean `UserDetailsService` / `PasswordEncoder` hoặc `AuthenticationProvider` / `AuthenticationManager` phù hợp.

`{noop}` trong ví dụ cũ là chỉ báo mật khẩu không được hash, **không an toàn cho production**. Khi di chuyển, nâng phương thức lưu mật khẩu theo chính sách hiện tại, chẳng hạn `DelegatingPasswordEncoder` sử dụng thuật toán thích hợp. Di chuyển API là cơ hội kiểm tra lại các giả định về HTTP, chứ không chỉ thay tên class.

## 5. Ví dụ Servlet hoàn chỉnh bằng bean

Giả sử ứng dụng Spring MVC có các yêu cầu:

- `GET /public/**` truy cập không đăng nhập.
- `/admin/**` chỉ cho vai trò ADMIN.
- Mọi endpoint còn lại yêu cầu người dùng đã xác thực.
- Frontend ở `https://app.example.com` gọi backend bằng cookie/session; cần CORS allowlist và CSRF cho thao tác thay đổi trạng thái.
- HTML sử dụng CSP giới hạn nguồn tài nguyên, và hệ thống chạy qua HTTPS.

Ví dụ dưới đây minh họa đủ các bean cơ bản. **Nguồn user in-memory và mật khẩu trong mã chỉ dùng cho lab**, cần thay bằng store được quản lý và secret riêng trong môi trường thực.

### 5.1. Bean `SecurityFilterChain` và policy HTTP

```java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableWebSecurity
public class ServletSecurityConfig {

    @Bean
    SecurityFilterChain webSecurity(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/public/**", "/error").permitAll()
                .requestMatchers("/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated()
            )
            .cors(Customizer.withDefaults())
            .csrf(Customizer.withDefaults())
            .headers(headers -> headers
                .contentSecurityPolicy(csp -> csp
                    .policyDirectives(
                        "default-src 'self'; object-src 'none'; frame-ancestors 'none'"
                    )
                )
            )
            .formLogin(Customizer.withDefaults())
            .logout(Customizer.withDefaults());

        return http.build();
    }
}
```

Đây là một **lớp cấu hình** chứ không kế thừa adapter. Spring inject `HttpSecurity` vào phương thức `@Bean`, còn phương thức trả về `SecurityFilterChain`. Các lambda gói từng nhóm chính sách; không dùng `.and()`.

Điều cần kiểm tra sau khi chuyển:

- `permitAll()` chỉ miễn **quy tắc authorization**; tài nguyên công khai vẫn đi qua security filters để nhận header, xử lý CSRF (nếu áp dụng) và các lớp bảo vệ khác.
- `formLogin(Customizer.withDefaults())` bổ sung luồng xác thực biểu mẫu. Request đăng nhập POST yêu cầu CSRF token theo chính sách mặc định.
- `cors(Customizer.withDefaults())` cần một nguồn CORS hợp lệ hoặc cấu hình tích hợp Spring MVC; nó không tự tạo allowlist.
- CSP trong ví dụ chỉ phù hợp một ứng dụng có tài nguyên cùng origin; frontend có script/CDN/nonce phải thiết kế lại policy theo thực tế.
- Spring Security mặc định quản lý một số header, trong đó có HSTS trên kết nối HTTPS; **CSP không được tự tạo mặc định**.

### 5.2. Bean `CorsConfigurationSource` cho Servlet

```java
import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Configuration
class ServletCorsConfig {

    @Bean
    UrlBasedCorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration config = new CorsConfiguration();
        config.setAllowedOrigins(List.of("https://app.example.com"));
        config.setAllowedMethods(List.of("GET", "POST", "PUT", "DELETE"));
        config.setAllowedHeaders(
            List.of("Content-Type", "X-CSRF-TOKEN")
        );
        config.setAllowCredentials(true);

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/**", config);
        return source;
    }
}
```

Khi sử dụng cookie qua origin khác nhau, frontend cũng phải gửi credentials đúng cách và cookie phải đáp ứng HTTPS/SameSite. Không cấu hình wildcard `*` cho `Access-Control-Allow-Origin` đồng thời bật `allowCredentials(true)`.

Với Spring MVC, nếu **không khai báo nguồn CORS**, `http.cors(Customizer.withDefaults())` có thể dùng cấu hình CORS của MVC. Nếu có **nhiều** `CorsConfigurationSource`, Spring Security không thể luôn tự chọn nguồn; hãy cấu hình per-chain `cors(cors -> cors.configurationSource(source))` khi cần.

### 5.3. Bean `UserDetailsService` và `PasswordEncoder`

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;

@Configuration
class ServletIdentityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder passwordEncoder) {
        // CHỈ DÀNH CHO LAB: không hard-code credential trong production.
        UserDetails user = User.withUsername("demo")
            .password(passwordEncoder.encode("change-me-in-lab"))
            .roles("USER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(passwordEncoder.encode("change-admin-in-lab"))
            .roles("ADMIN")
            .build();

        return new InMemoryUserDetailsManager(user, admin);
    }
}
```

`InMemoryUserDetailsManager` là một triển khai `UserDetailsService`, cung cấp người dùng cho authentication provider được Spring Security thiết lập khi phù hợp. `DelegatingPasswordEncoder` quản lý việc đối chiếu mật khẩu theo mã định danh thuật toán, ví dụ `{bcrypt}...`. Ở môi trường thật, user store thường là database, LDAP, identity provider hoặc một nguồn chuyên dụng. Mật khẩu băm nên được quản lý bền vững, không tạo lại ngẫu nhiên theo mỗi lần khởi động nếu ứng dụng cần đăng nhập ổn định.

**Tách bean nguồn user không buộc phải tự tạo `AuthenticationManager`.** Với use case username/password cơ bản, Spring Security có thể tạo các thành phần xác thực cần thiết từ `UserDetailsService` và `PasswordEncoder`. Chỉ xuất bản manager/provider riêng khi có nhu cầu điều khiển cụ thể.

## 6. Khi nào cần bean `AuthenticationManager` hoặc `AuthenticationProvider`?

### 6.1. Phân biệt trách nhiệm

| Thành phần | Làm gì? | Câu hỏi cần trả lời |
| --- | --- | --- |
| `UserDetailsService` | Tra cứu username, password hash, authorities | Người dùng là ai và có quyền gì? |
| `PasswordEncoder` | Hash và kiểm tra mật khẩu | Mật khẩu nhập vào có khớp hash? |
| `AuthenticationProvider` | Thực hiện một cơ chế xác thực | Cơ chế này có thể xác thực token này không? |
| `AuthenticationManager` | Điều phối xác thực, thường qua nhiều provider | Kết quả xác thực cuối cùng là gì? |
| `SecurityFilterChain` | Xử lý HTTP theo chain, gọi cơ chế xác thực và authorization thích hợp | Request được xử lý theo chính sách nào? |

Nếu có API đăng nhập riêng cần gọi `AuthenticationManager.authenticate(...)` hoặc cần tùy biến provider, có thể khai báo bean rõ ràng:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.password.PasswordEncoder;

@Configuration
class ExplicitAuthenticationConfig {

    @Bean
    AuthenticationManager authenticationManager(
            UserDetailsService users,
            PasswordEncoder encoder) {

        DaoAuthenticationProvider provider =
            new DaoAuthenticationProvider(users);
        provider.setPasswordEncoder(encoder);

        return new ProviderManager(provider);
    }
}
```

**Chỉ thêm đoạn này khi đã có nhu cầu dùng manager riêng và đã xác minh cơ chế nào đang sử dụng nó.** ProviderManager trên chỉ biết provider username/password; nếu ứng dụng cần OAuth2, SAML, MFA hoặc nhiều provider, phải thiết kế đúng thứ tự/hệ thống manager. Một bean manager tường minh cũng có thể làm auto-configuration username/password của Spring Boot thay đổi, vì vậy hãy quan sát dependency và flow xác thực thực tế.

Khi cần manager **riêng cho một chain**, Servlet API hỗ trợ thiết lập manager cục bộ:

```java
// Trong @Bean SecurityFilterChain, với một AuthenticationManager phù hợp:
http
    .authenticationManager(apiAuthenticationManager)
    .authorizeHttpRequests(authorize -> authorize
        .anyRequest().authenticated()
    )
    .httpBasic(Customizer.withDefaults());
```

`apiAuthenticationManager` ở ví dụ là đối tượng đã được cấp/chọn rõ ràng. Không tự suy ra rằng mọi chain sẽ dùng cùng manager chỉ vì chúng nằm trong một lớp `@Configuration`.

### 6.2. Tránh tạo vòng phụ thuộc

Một lỗi migration thường gặp là khai báo bean `AuthenticationManager` rồi lại inject nó theo chu trình trong các bean cấu hình provider hoặc filter chain. Để tránh:

1. Xác định ai **tạo** provider/manager và ai chỉ **sử dụng** nó.
2. Sắp xếp dependency một chiều: `UserDetailsService` + `PasswordEncoder` → provider → manager → chain/filter/client.
3. Không kết hợp tùy tiện nhiều cách lấy manager toàn cục và cục bộ.
4. Với authentication thực tế qua OAuth2 Resource Server hoặc OAuth2 Login, ưu tiên cơ chế chuyên dụng của Spring Security; không ép mọi trường hợp vào `DaoAuthenticationProvider`.

## 7. Vì sao `WebSecurityCustomizer` không tương đương `permitAll()`?

Đây là điểm dễ mất các lớp **HTTP protection** khi chuyển từ `configure(WebSecurity web)`.

**Cấu hình cũ:**

```java
// LEGACY ONLY: WebSecurityConfigurerAdapter và antMatchers đã lỗi thời.
@Override
public void configure(WebSecurity web) {
    web.ignoring().antMatchers("/assets/**");
}
```

**Đề xuất mới cho tài nguyên tĩnh công khai:**

```java
@Bean
SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
    http.authorizeHttpRequests(authorize -> authorize
        .requestMatchers("/assets/**", "/public/**").permitAll()
        .anyRequest().authenticated()
    );
    return http.build();
}
```

| `permitAll()` | `web.ignoring()` |
| --- | --- |
| Request vẫn qua Spring Security filter chain | Request tương ứng **bỏ qua** Spring Security filter chain |
| Có thể nhận security headers, CORS và các xử lý áp dụng trong chain | Không được Spring Security ghi headers hay áp chính sách trong chain |
| Thường là lựa chọn phù hợp cho public/static URL | Chỉ cân nhắc cho trường hợp thật sự cần loại trừ hoàn toàn |
| Authorization cho phép truy cập | Spring Security không tham gia xử lý request bị ignore |

Nếu có use case thật sự cần tùy chỉnh `WebSecurity` (ví dụ cấu hình Servlet HTTP firewall), ta vẫn có thể đăng ký `WebSecurityCustomizer`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.annotation.web.configuration.WebSecurityCustomizer;
import org.springframework.security.web.firewall.StrictHttpFirewall;

@Bean
StrictHttpFirewall strictHttpFirewall() {
    return new StrictHttpFirewall();
}

@Bean
WebSecurityCustomizer webSecurityCustomizer(
        StrictHttpFirewall firewall) {
    return web -> web.httpFirewall(firewall);
}
```

Hai method `@Bean` trên phải nằm trong lớp `@Configuration` của Servlet. **Ví dụ chỉ minh họa điểm mở rộng**: Spring Security đã cung cấp firewall mặc định; không cần tạo lại nếu không có yêu cầu riêng. Nếu cần nới một quy tắc URL nghiêm ngặt, hãy đánh giá nguy cơ bypass request matcher trước khi chỉnh `StrictHttpFirewall`.

### Đừng dùng `web.ignoring()` để “sửa” lỗi 401/403

Request bị từ chối có thể do xác thực, phân quyền, CSRF, CORS hoặc security matcher. Đưa `/api/**` vào `web.ignoring()` sẽ khiến toàn bộ nhóm API không được Spring Security bảo vệ. Thay vào đó, tìm nguyên nhân và chỉnh từng chính sách cụ thể, đồng thời kiểm thử trường hợp truy cập trái phép.

## 8. Nhiều bean `SecurityFilterChain` và thứ tự kiểm tra

Một ứng dụng có thể có hai cơ chế HTTP, chẳng hạn API dùng HTTP Basic và website dùng form login. Phong cách bean cho phép thể hiện rõ từng chain:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class MultipleChains {

    @Bean
    @Order(1)
    SecurityFilterChain api(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/api/public/**").permitAll()
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults());
        return http.build();
    }

    @Bean
    SecurityFilterChain fallback(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/public/**").permitAll()
                .anyRequest().authenticated()
            )
            .formLogin(Customizer.withDefaults());
        return http.build();
    }
}
```

**Bài học chính về matcher:**

- `securityMatcher("/api/**")` quyết định **chain API có xử lý request hay không**.
- `requestMatchers("/api/public/**")` quyết định quyền **bên trong chain API**.
- `anyRequest()` chỉ bao phủ các request đã match chain hiện tại.
- `@Order(1)` khiến chain API được xét trước; fallback không có `securityMatcher` nên bao phủ các request còn lại.
- Nếu **không có chain nào match**, Spring Security không bảo vệ request đó. Đây có thể là lỗ hổng lớn khi chuyển từ adapter một chain sang nhiều bean.

Một request chỉ đi qua **chain đầu tiên phù hợp**, không được tự động xử lý liên tiếp bởi mọi bean `SecurityFilterChain`. Những chính sách cần chung, như CSP/CORS, phải bảo đảm có mặt trong các chain tương ứng. Ví dụ phía trên tập trung vào phân luồng, chưa khai báo CORS/CSP riêng cho từng chain; production cần bổ sung theo mô hình client.

**Lưu ý về login/logout endpoint:** nếu một chain chỉ match `/api/**` mà lại cấu hình `formLogin` mặc định ở chain đó, endpoint `/login` có thể không thuộc phạm vi chain. Hãy thiết kế login URL phù hợp hoặc đặt form login ở fallback chain.

## 9. Reactive: `SecurityWebFilterChain` là bean tương ứng

WebFlux từ đầu dùng phong cách cấu hình `ServerHttpSecurity` và `SecurityWebFilterChain`; nó **không có** `WebSecurityConfigurerAdapter` của Servlet để kế thừa. Tuy nhiên, người học rất dễ sao chép ví dụ Servlet rồi cố ép sang Reactive.

Tạo ứng dụng WebFlux **độc lập** với ứng dụng MVC ở mục 5:

```java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class ReactiveSecurityConfig {

    @Bean
    SecurityWebFilterChain webFluxSecurity(ServerHttpSecurity http) {
        http
            .authorizeExchange(exchange -> exchange
                .pathMatchers("/public/**", "/error").permitAll()
                .pathMatchers("/admin/**").hasRole("ADMIN")
                .anyExchange().authenticated()
            )
            .cors(Customizer.withDefaults())
            .csrf(Customizer.withDefaults())
            .headers(headers -> headers
                .contentSecurityPolicy(csp -> csp
                    .policyDirectives(
                        "default-src 'self'; object-src 'none'; frame-ancestors 'none'"
                    )
                )
            )
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }
}
```

Khi cấu hình user/password trong Reactive, dùng `ReactiveUserDetailsService` thay cho `UserDetailsService` Servlet:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;

@Configuration
class ReactiveIdentityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService reactiveUsers(
            PasswordEncoder encoder) {
        // CHỈ DÀNH CHO LAB: thay store và credential trong production.
        UserDetails user = User.withUsername("reactive-user")
            .password(encoder.encode("change-me-in-lab"))
            .roles("USER")
            .build();
        return new MapReactiveUserDetailsService(user);
    }
}
```

Các lớp `ServletSecurityConfig`/`ServletIdentityConfig` và `ReactiveSecurityConfig`/`ReactiveIdentityConfig` là **hai ứng dụng ví dụ riêng biệt**. Không đăng ký tất cả trong cùng một Spring Boot context rồi kỳ vọng mọi request sẽ qua hai security stacks.

### 9.1. Reactive CORS cần dùng đúng package

```java
import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource;

@Configuration
class ReactiveCorsConfig {
    @Bean
    UrlBasedCorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration config = new CorsConfiguration();
        config.setAllowedOrigins(List.of("https://app.example.com"));
        config.setAllowedMethods(List.of("GET", "POST", "PUT", "DELETE"));
        config.setAllowedHeaders(List.of("Content-Type", "X-CSRF-TOKEN"));
        config.setAllowCredentials(true);

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/**", config);
        return source;
    }
}
```

Cùng tên `UrlBasedCorsConfigurationSource` có hai package:

- Servlet: `org.springframework.web.cors.UrlBasedCorsConfigurationSource`.
- Reactive: `org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource`.

Chúng không thay thế được cho nhau. Preflight CORS `OPTIONS` thường không có cookie nên phải được xử lý trước khi kiểm tra xác thực. Ngoài việc có bean, cần kiểm tra origin, method, header và credentials với request thật.

### 9.2. Bean xác thực Reactive là thành phần riêng

Trong WebFlux, hệ thống có `ReactiveAuthenticationManager`, `ReactiveUserDetailsService`, `ServerSecurityContextRepository` và `WebSession`. Không đưa `AuthenticationManager` hoặc `HttpSession` của Servlet vào chain Reactive. Có thể cấu hình riêng một `ReactiveAuthenticationManager` cho API tùy chỉnh nếu cần, nhưng mẫu username/password cơ bản thường chỉ cần `ReactiveUserDetailsService` và `PasswordEncoder`.

Nếu ứng dụng dùng OAuth2 Resource Server hoặc Client, bean do Spring Boot tự tạo có thể thay đổi khi thêm các starter này. Đừng dựa vào giả định “Boot luôn sinh user mặc định” trong một ứng dụng đã cấu hình security theo bean.

## 10. Spring Boot tự cấu hình những gì khi có bean tùy chỉnh?

Spring Boot tự cấu hình security khi starter Security nằm trên classpath, nhưng **các bean do lập trình viên khai báo làm thay đổi quy tắc tự cấu hình**.

### Với Spring MVC / Servlet

- Nếu không có cấu hình tùy chỉnh, Boot cung cấp bảo vệ mặc định cho các URL và tài khoản phát triển sinh sẵn (phụ thuộc điều kiện auto-configuration).
- Khi thêm bean `SecurityFilterChain`, Boot **lùi khỏi cấu hình web security mặc định**; từ đó phạm vi matcher, authentication entry point và quyền truy cập là trách nhiệm của cấu hình tự viết.
- Việc thêm `SecurityFilterChain` **không tự động loại bỏ** cấu hình `UserDetailsService` mặc định.
- Khi thêm bean `UserDetailsService`, `AuthenticationProvider` hoặc `AuthenticationManager`, auto-configuration nguồn user mặc định thường lùi lại; các module OAuth2/SAML2 cũng có thể khiến cấu hình user mặc định không được tạo.
- Spring Boot Actuator có thể bị ảnh hưởng khi thay cấu hình mặc định. Đừng vô tình để endpoint vận hành nhạy cảm ở trạng thái `permitAll`.

### Với Spring WebFlux / Reactive

- Boot có `ReactiveWebSecurityAutoConfiguration` và `ReactiveUserDetailsServiceAutoConfiguration`.
- Có thể tùy chỉnh luật truy cập bằng bean `SecurityWebFilterChain`; logic back-off của các auto-configuration Reactive có khác biệt so với Servlet.
- Nếu có bean `ReactiveUserDetailsService` hoặc `ReactiveAuthenticationManager`, nguồn user Reactive mặc định lùi theo điều kiện của Boot.
- Không suy diễn rằng chỉ cần khai báo một `SecurityWebFilterChain` là mọi bean Reactive Security mặc định đều bị vô hiệu. Hãy đọc **condition evaluation report** và kiểm tra chain đang chạy.

**Sai lầm thường gặp:** sau khi thêm một `SecurityFilterChain` chỉ có `.securityMatcher("/api/**")`, các URL ngoài `/api/**` không còn được fallback chain bảo vệ. Cần khai báo một fallback chain hợp lý, thay vì tin rằng Boot sẽ tự sinh chain mặc định để lấp khoảng trống.

## 11. Đưa các lớp phòng vệ HTTP vào cấu hình theo bean

Việc bỏ adapter không có nghĩa bỏ các tính năng bảo vệ. Về nguyên tắc, các policy phải được bảo toàn trên **mọi chain có liên quan**.

### 11.1. CSRF: đừng bỏ qua khi chuyển sang bean

CSRF giúp ngăn website độc hại khiến trình duyệt gửi yêu cầu thay đổi trạng thái bằng cookie/credential được trình duyệt tự gửi. Với session/form login, Spring Security thường **bật CSRF theo mặc định**.

**Servlet:** 

```java
http.csrf(Customizer.withDefaults());

// Chỉ là một ngoại lệ có cơ sở: webhook dùng chữ ký độc lập,
// không dựa vào cookie/session từ trình duyệt.
http.csrf(csrf -> csrf.ignoringRequestMatchers("/webhook/signed"));
```

Đoạn thứ hai minh họa **một lựa chọn cấu hình thay thế** cho dòng thứ nhất; không cần đặt cả hai lời gọi liên tiếp trong cùng cấu hình. Ngoại lệ webhook cần xác minh chữ ký, timestamp và chống replay; CSRF exclusion không phải authentication.

**Reactive:** `ServerHttpSecurity.csrf(Customizer.withDefaults())` có ý nghĩa tương ứng nhưng dùng CSRF repository và WebSession của Reactive. Cơ chế token cho SPA cần được thiết kế theo WebFlux, không bê nguyên `HttpSessionCsrfTokenRepository` của Servlet sang.

**Chỉ cân nhắc tắt CSRF toàn chain** khi kiến trúc xác thực và threat model cho thấy không có credential dễ bị browser tự gửi. Ví dụ, một Bearer API thuần mà client tự gắn `Authorization` header có thể không cần CSRF; một REST API dùng cookie vẫn có nguy cơ.

### 11.2. CORS: cấu hình nguồn chính sách riêng với filter chain

Bean `CorsConfigurationSource` là một ví dụ rõ về lợi ích của cấu hình theo thành phần:

- Bean nguồn CORS chứa origin/method/header/credentials được phép.
- `SecurityFilterChain` hoặc `SecurityWebFilterChain` tích hợp xử lý CORS vào đường đi request.
- Test HTTP kiểm chứng preflight hợp lệ có header đúng và origin lạ không được cho phép.

**CORS không thay thế CSRF hoặc authorization**. Trình duyệt có thể gửi một số request cross-origin dù không được phép đọc response; vì vậy server vẫn phải kiểm tra user, quyền và CSRF ở nơi cần.

### 11.3. Security headers, CSP, HSTS và reverse proxy

Bean filter chain có thể cấu hình CSP riêng:

```java
http.headers(headers -> headers
    .contentSecurityPolicy(csp -> csp
        .policyDirectives(
            "default-src 'self'; object-src 'none'; frame-ancestors 'none'"
        )
    )
);
```

Header `Content-Security-Policy` **không có mặc định chung** được Spring Security áp sẵn. Các header mặc định khác có thể được Spring Security thêm, nhưng bạn vẫn phải kiểm tra request đi qua **đúng chain**. Một tài nguyên bị `web.ignoring()` sẽ không được chain Spring Security ghi thêm header.

HSTS (`Strict-Transport-Security`) được sử dụng trên **HTTPS**; khi TLS được kết thúc ở reverse proxy, cần xác định cách Spring nhận forwarded scheme và quan sát response từ phía client public. Việc đặt `includeSubDomains` hoặc `preload` có ảnh hưởng rộng; chỉ chọn khi toàn bộ tên miền liên quan đáp ứng HTTPS.

### 11.4. HTTP firewall khác với bean phân quyền

Ở Servlet, `StrictHttpFirewall` kiểm tra request có path/encoding bất thường trước khi các matcher phân quyền xử lý. `WebSecurityCustomizer` có thể tùy chỉnh WebSecurity/HTTP firewall, nhưng không phải nơi viết rule cấp quyền cho `/admin/**`. Đừng nới firewall chỉ để request có dấu phân cách lạ hoặc URL mã hóa bất thường “chạy được”.

Reactive dùng hạ tầng xử lý `ServerWebExchange` khác Servlet. Một bean `StrictHttpFirewall` Servlet không bảo vệ WebFlux. Kiểm thử payload URL bất thường phải sử dụng đúng stack và đúng đường đi proxy/container thực tế.

### 11.5. Session và logout cần chính sách riêng

Với Servlet, ứng dụng có thể cấu hình:

```java
import org.springframework.security.config.http.SessionCreationPolicy;

// Ví dụ cho một chain API thực sự không dùng session/cookie để xác thực:
http.sessionManagement(session -> session
    .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
);
```

`STATELESS` liên quan cách Spring Security sử dụng `HttpSession` để lưu/đọc ngữ cảnh bảo mật; nó không biến toàn bộ ứng dụng thành stateless nếu code khác vẫn tạo session. Nếu dùng form login/cookie, đặt `STATELESS` vô điều kiện có thể khiến đăng nhập không được giữ hoặc logout hành xử khác kỳ vọng.

Trong WebFlux, làm việc với `WebSession` và `ServerSecurityContextRepository` thay vì API Servlet. Sau khi chuyển sang bean-based config, kiểm tra session fixation, cookie flags (`Secure`, `HttpOnly`, `SameSite`), timeout, logout và xóa context theo đúng flow ứng dụng.

## 12. Kiểm thử sau migration: giữ hành vi, không chỉ giữ cú pháp

Tối thiểu hãy chứng minh các đường đi sau:

| Kịch bản | Servlet/WebFlux mong đợi | Trục trặc gợi ý |
| --- | --- | --- |
| GET `/public/info` không đăng nhập | Endpoint công khai xử lý bình thường | URL bị chặn bởi chain hoặc rule |
| GET `/account` không đăng nhập | 401 hoặc redirect login | 200 có dữ liệu → có thể lọt chain |
| GET `/admin/report` dưới vai trò USER | 403 | 200 → sai rule/chain/role prefix |
| POST có cookie/session nhưng thiếu CSRF token | 403 sau khi đã xác thực | 200 → xem lại CSRF và matcher |
| POST với CSRF token hợp lệ | Qua kiểm tra CSRF, phụ thuộc authorization | Vẫn 403 → kiểm tra session/token/role |
| Preflight từ origin được phép | Trả CORS headers phù hợp | 401/403 do CORS xử lý sau auth hoặc sai bean |
| Preflight từ origin lạ | Không cấp quyền origin đó | Cấu hình allowlist quá rộng |
| GET HTML qua HTTPS | Có CSP/HSTS theo chính sách | Chain khác, headers tắt, proxy scheme sai |
| URL chứa ký tự bất thường | Không vượt qua firewall/authorization | Matcher bị bypass hoặc firewall tùy chỉnh sai |
| Đăng nhập → logout → request tiếp | Session/context bị vô hiệu hợp lý | Session repository/manager thay đổi sau migration |

### 12.1. Servlet: kiểm thử bean `SecurityFilterChain` bằng `MockMvc`

Ví dụ giả sử `MockMvc` đã được tích hợp Spring Security và ứng dụng có endpoint `POST /orders` trả 200 cho user phù hợp:

```java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@Test
void servletPostRequiresCsrf() throws Exception {
    mvc.perform(post("/orders").with(user("alice")))
       .andExpect(status().isForbidden());

    mvc.perform(post("/orders").with(user("alice")).with(csrf()))
       .andExpect(status().isOk());
}
```

Trong đoạn này, `mvc` là đối tượng `MockMvc` được inject/configure bởi test framework, controller `/orders` phải có sẵn. Dùng `with(csrf().useInvalidToken())` để xác nhận token sai vẫn bị chặn. Nếu endpoint trả 201/204, chỉnh expectation tương ứng.

**Đảm bảo test có filter chain thật**: cấu hình `@AutoConfigureMockMvc` hoặc `springSecurity()` khi tạo `MockMvc` thủ công; test chỉ gọi controller mà không chạy security filters sẽ cho kết quả giả.

### 12.2. Reactive: kiểm thử bằng `WebTestClient`

Với `WebTestClient` bind vào `ApplicationContext` và đã áp dụng `springSecurity()`:

```java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;

@Test
void reactivePostRequiresCsrf() {
    client.mutateWith(mockUser("alice"))
        .post().uri("/orders")
        .exchange()
        .expectStatus().isForbidden();

    client.mutateWith(mockUser("alice"))
        .mutateWith(csrf())
        .post().uri("/orders")
        .exchange()
        .expectStatus().isOk();
}
```

Đoạn test giả định `client` đã được tạo đúng kiểu WebFlux và có endpoint hợp lệ. `mockUser()` chỉ mô phỏng user trong test bind-to-context; test gọi server từ xa phải có flow xác thực thực sự.

### 12.3. Kiểm tra CORS và headers ngoài framework test

```bash
curl -i -X OPTIONS "https://api.example.com/orders" \
  -H "Origin: https://app.example.com" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: content-type,x-csrf-token"

curl -i "https://app.example.com/" 
```

Ở response đầu tiên kiểm tra `Access-Control-Allow-Origin`, allowed methods/headers và `Access-Control-Allow-Credentials` nếu thực sự dùng cookie cross-origin. Gửi lại preflight từ origin không được cho phép và chắc chắn không nhận quyền CORS. Ở response HTTPS thứ hai, kiểm tra CSP và HSTS **trên đường đi public qua proxy**.

## 13. Những lỗi dễ gặp khi chuyển từ adapter sang bean

### Lỗi A — Không tìm thấy `WebSecurityConfigurerAdapter`

**Biểu hiện:** IDE báo cannot resolve symbol hoặc build lỗi sau nâng lên Spring Security 6/7.

**Nguyên nhân:** vẫn kế thừa API đã bị xóa.

**Cách sửa:** bỏ `extends WebSecurityConfigurerAdapter`, chuyển `configure(HttpSecurity)` thành bean `SecurityFilterChain`, tách cấu hình user/manager sang các bean tương ứng. Không hạ riêng một module Security xuống 5.x trong dự án dùng Framework 6/7.

### Lỗi B — Có `SecurityFilterChain` mới nhưng trang quản trị không được bảo vệ

**Biểu hiện:** `/admin/**` trả dữ liệu mà không cần quyền.

**Nguyên nhân:** `securityMatcher` quá hẹp, sai thứ tự `@Order`, một chain trước đó có `permitAll` rộng, hoặc không có fallback chain.

**Cách sửa:** kiểm tra chain được chọn và matcher bên trong, xây integration tests cho các URL nhạy cảm, thêm fallback phù hợp.

### Lỗi C — Thêm bean `AuthenticationManager` làm đăng nhập OAuth2/SAML2 ngừng chạy

**Biểu hiện:** flow xác thực cũ ngừng hoạt động sau khi thêm cấu hình username/password.

**Nguyên nhân:** manager tự khai báo chỉ chứa `DaoAuthenticationProvider` hoặc làm thay đổi điều kiện auto-configuration.

**Cách sửa:** phân biệt cơ chế xác thực theo từng chain; dùng cấu hình OAuth2/SAML2 chuyên dụng; chỉ tự tạo manager khi có yêu cầu cụ thể và kiểm thử từng flow.

### Lỗi D — Public resource mất CSP/HSTS sau migration

**Biểu hiện:** `/assets/**` không còn security headers.

**Nguyên nhân:** chuyển public URL từ `permitAll()` thành `web.ignoring()`, hoặc route rơi ngoài mọi chain.

**Cách sửa:** dùng `permitAll()` khi muốn cho phép tải tài nguyên nhưng vẫn áp dụng filters/headers; đảm bảo chain bao phủ request.

### Lỗi E — POST trả 403 dù người dùng đã đăng nhập

**Biểu hiện:** GET hoạt động; POST bị từ chối.

**Nguyên nhân có thể:** CSRF token thiếu/sai, session/cookie mất do proxy, hoặc user thiếu quyền.

**Cách sửa:** kiểm tra exception CSRF, test có token hợp lệ, rà soát cookie và policy phân quyền. Không tắt CSRF toàn cục chỉ để request trả 200.

### Lỗi F — CORS preflight trả 401

**Biểu hiện:** browser dừng trước khi gửi POST thật.

**Nguyên nhân:** source CORS không tồn tại, dùng nhầm package Servlet/Reactive, nhiều source mà chain không chọn đúng, proxy chặn OPTIONS.

**Cách sửa:** kiểm tra bean CORS và preflight ở đường đi thực tế; đối chiếu allowlist origin/method/header và thứ tự CORS so với authentication.

### Lỗi G — Có hai bean auth giống nhau hoặc vòng phụ thuộc

**Biểu hiện:** container không khởi động, lỗi ambiguous bean, circular dependency hoặc bean definition conflict.

**Nguyên nhân:** copy cấu hình cũ sang nhiều `@Configuration`, tự tạo nhiều `AuthenticationManager`, `PasswordEncoder` hoặc `CorsConfigurationSource` không có qualifier.

**Cách sửa:** xác định từng bean thuộc stack, policy và chain nào; đưa logic chung vào một nơi, dùng qualifier/per-chain config khi cần, không khai báo hai cấu hình Servlet/Reactive trong cùng ứng dụng trừ khi có thiết kế thật rõ.

## 14. Lộ trình chuyển đổi một ứng dụng có cấu hình kế thừa cũ

1. **Chốt phiên bản mục tiêu:** kiểm tra dòng Spring Boot, Spring Framework, Spring Security và Java thực tế được resolve. Cập nhật build tool/plugin tương thích.
2. **Đọc toàn bộ adapter cũ:** liệt kê những gì có trong `configure(HttpSecurity)`, `configure(WebSecurity)`, `configure(AuthenticationManagerBuilder)`, bean liên quan, custom filters và security exceptions.
3. **Tách cấu hình authentication:** tạo `UserDetailsService`/`PasswordEncoder` hoặc provider/manager phù hợp. Kiểm tra migration của OAuth2/LDAP/SAML/JDBC nếu có.
4. **Tạo bean filter chain:** di chuyển URL authorization, login/logout, CSRF, CORS, headers, session và custom filter sang Lambda DSL. Giữ nguyên thứ tự matcher đã được kiểm tra.
5. **Xử lý `web.ignoring()`:** chuyển các public resources về `permitAll()` khi có thể; chỉ giữ ignore với lý do bảo mật và vận hành rõ ràng.
6. **Thêm fallback chain nếu có nhiều chain:** kiểm tra `@Order` và phạm vi `securityMatcher`, không để route ngoài bảo vệ.
7. **Kiểm tra tác động Spring Boot:** xem các bean auto-configured bị thay, user mặc định có còn tồn tại không, Actuator và endpoints nhạy cảm đang được bảo vệ thế nào.
8. **Chạy kiểm thử HTTP thực tế:** anonymous/authorized, CSRF token thiếu/đúng, CORS origin đúng/sai, CSP/HSTS, firewall, session/logout và reverse proxy.
9. **Dọn mã obsolete:** xóa adapter và cấu hình cũ sau khi đã xác nhận thay thế tương đương; không giữ song song những cơ chế gây xung đột.

## 15. Bài tập thực hành

### Bài tập 1 — Chuyển cấu hình user cũ

Cho một adapter Spring Security 5.x khai báo `inMemoryAuthentication()` với user `demo` và dùng `.authorizeRequests().antMatchers("/public/**").permitAll()`. Hãy viết hai bean `SecurityFilterChain` và `UserDetailsService` (cùng `PasswordEncoder`), bảo toàn quyền truy cập và giữ CSRF mặc định.

**Tiêu chí:** không có `WebSecurityConfigurerAdapter`; user/password phải được quản lý qua encoder; GET public được phép, POST có session thiếu CSRF token bị từ chối.

### Bài tập 2 — Phát hiện route lọt chain

Hệ thống có một bean:

```java
@Bean
SecurityFilterChain apiOnly(HttpSecurity http) throws Exception {
    http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(a -> a.anyRequest().authenticated())
        .httpBasic(Customizer.withDefaults());
    return http.build();
}
```

Hãy chỉ ra vì sao `GET /admin/report` có thể không được Spring Security bảo vệ. Viết thêm bean fallback với rule `/admin/**` yêu cầu ADMIN và các route khác cần xác thực. Thêm test xác nhận user không có quyền nhận 403.

### Bài tập 3 — So sánh Servlet và Reactive

Tạo hai ứng dụng độc lập dùng `/public/**` công khai và `/admin/**` yêu cầu ADMIN. Ứng dụng thứ nhất dùng `SecurityFilterChain`/`UserDetailsService`; ứng dụng thứ hai dùng `SecurityWebFilterChain`/`MapReactiveUserDetailsService`. Cấu hình CSP và CORS allowlist cho cùng một origin; kiểm thử bằng `MockMvc` và `WebTestClient`.

### Bài tập 4 — Điều tra regression bảo mật

Sau khi bỏ adapter cũ, một nhóm chuyển `/assets/**` sang `web.ignoring()`. Người kiểm thử phát hiện response asset không có các security headers do Spring Security ghi. Hãy giải thích nguyên nhân, chọn sửa `permitAll()` hoặc ngoại lệ có kiểm soát, và bổ sung test response headers.

## 16. Checklist trước khi hoàn thành migration

- [ ] Không còn `WebSecurityConfigurerAdapter` hoặc các cú pháp cũ `antMatchers`/`.and()` trong cấu hình chạy với Security 6/7.
- [ ] Mỗi stack dùng đúng kiểu bean: Servlet `SecurityFilterChain`, Reactive `SecurityWebFilterChain`.
- [ ] Nguồn danh tính, encoder, provider/manager được khai báo có mục đích và không xung đột với Spring Boot.
- [ ] Phạm vi `securityMatcher`, rule authorization và `@Order` có test; URL không thuộc chain đã được xét.
- [ ] Static/public URL được cho phép theo chính sách mà vẫn giữ security headers cần thiết.
- [ ] CSRF vẫn áp dụng cho browser có credential tự động; mọi ngoại lệ đều có lý do cụ thể.
- [ ] CORS source đúng package và preflight hợp lệ/bất hợp lệ được kiểm tra.
- [ ] CSP/HSTS/security headers được xác nhận trên response HTTPS qua proxy.
- [ ] Không nới HTTP firewall để bỏ qua lỗi mà chưa đánh giá request encoding/matcher.
- [ ] Login/logout, session/cookie, timeout và Actuator endpoints có regression tests.
- [ ] Dependency graph được kiểm tra; không ghép module Spring Security cũ vào thế hệ mới.

## Nguồn tham khảo chính thức

1. [Spring Security without the WebSecurityConfigurerAdapter](https://spring.io/blog/2022/02/21/spring-security-without-the-websecurityconfigureradapter) — bài viết chính thức giới thiệu các bean thay cho adapter, `WebSecurityCustomizer`, `UserDetailsService` và `AuthenticationManager`.
2. [Spring Security Servlet Java Configuration](https://docs.spring.io/spring-security/reference/servlet/configuration/java.html) — `SecurityFilterChain`, nhiều chain, matcher và login/logout endpoints.
3. [Spring Security Servlet Username/Password Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/index.html) — `UserDetailsService`, `PasswordEncoder`, `DaoAuthenticationProvider` và `ProviderManager`.
4. [Spring Security WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html) — `ServerHttpSecurity`, `SecurityWebFilterChain` và Reactive security configuration.
5. [Spring Boot Security Reference](https://docs.spring.io/spring-boot/reference/web/spring-security.html) và [Spring Boot Security How-to](https://docs.spring.io/spring-boot/how-to/security.html) — hành vi mặc định, điều kiện back-off và tùy chỉnh các bean security.
6. [Spring Security Servlet CORS](https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html) và [Reactive CORS](https://docs.spring.io/spring-security/reference/reactive/integrations/cors.html) — nguồn CORS và xử lý preflight.
7. [Spring Security Servlet CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html), [Reactive CSRF](https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html) và [Servlet Security Headers](https://docs.spring.io/spring-security/reference/servlet/exploits/headers.html) — tác động thực tế của các lớp phòng vệ.
8. [Spring Security 7 Migration Guide](https://docs.spring.io/spring-security/reference/migration/) — rà soát thay đổi API, Lambda DSL và yêu cầu tương thích.

**Câu hỏi tự đánh giá:** Vì sao thay `configure(WebSecurity)` bằng `web.ignoring()` có thể khiến public endpoints mất CSP/HSTS? Khi nào khai báo `AuthenticationManager` là cần thiết? Tại sao chỉ có một bean `SecurityFilterChain` match `/api/**` chưa đủ bảo vệ cả ứng dụng? Trong WebFlux, bean nào đảm nhiệm vai trò tương đương `SecurityFilterChain` của Servlet?
