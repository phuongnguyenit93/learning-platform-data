# Đọc cấu hình cũ dùng WebSecurityConfigurerAdapter hoặc API đã lỗi thời trong Spring Security

## 1. Vì sao đọc được cấu hình cũ là kỹ năng cần thiết?

Nhiều dự án Java vẫn có các class như `SecurityConfig extends WebSecurityConfigurerAdapter`, gọi `configure(HttpSecurity)`, `configure(WebSecurity)` và `configure(AuthenticationManagerBuilder)`. Người mới thấy các đoạn:

```java
http.authorizeRequests()
    .antMatchers("/admin/**").hasRole("ADMIN")
    .anyRequest().authenticated()
    .and()
    .formLogin();
```

Trong Spring Security 6.x, một số class/phương thức này đã bị loại bỏ hoặc deprecated. Sao chép y nguyên vào Spring Boot 3.x có thể không compile. Nguy hiểm hơn, thay thế bằng API mới mà không hiểu **quy tắc gốc** có thể vô tình mở public endpoint, tắt CSRF, mất login, sai session hoặc làm mất method authorization.

Mục tiêu bài học là **đọc, diễn giải, kiểm kê và chuyển đổi cấu hình**, không chỉ học thuộc cú pháp mới. Bạn cần trả lời:

1. Cấu hình cũ **bảo vệ request nào**, và request nào bị bỏ qua hoàn toàn?
2. User được xác thực qua **provider nào**: form login, HTTP Basic, JDBC, LDAP, OAuth2, custom filter hay bearer JWT?
3. Quy tắc `role`, `authority`, method security và thứ tự matchers có ý nghĩa gì?
4. Spring Security đã tạo những endpoint nào như `POST /login`, `POST /logout`?
5. Khi chuyển sang `SecurityFilterChain`, **hành vi** có giữ nguyên không, đặc biệt là những chỗ vốn không an toàn?
6. Đang nâng từ Spring Security 5.6, 5.8, 6.5 hay 7.0? API hợp lệ còn phụ thuộc **version và Servlet/WebFlux**.

Phần mã đích tập trung **Spring Boot 3.x + Spring Security 6.5 + Java 17+ + Servlet/MVC**. Phần cuối giải thích điều cần biết khi lên Spring Security 7.x/Boot 4.x. Mã cũ minh họa một cấu hình để đọc, **không khuyến khích triển khai mới**.

## 2. Lập bản đồ phiên bản trước khi sửa code

| Phiên bản/nhánh | Điểm nhận dạng | Hướng đọc và chuyển đổi |
| --- | --- | --- |
| Spring Security 5.6 trở về trước | `WebSecurityConfigurerAdapter` được dùng rộng rãi; `authorizeRequests`, `antMatchers`, `.and()` phổ biến | Hiểu ba override và thứ tự rule trước khi thay API |
| Spring Security 5.7 | `WebSecurityConfigurerAdapter` bị **deprecated**; khuyến nghị `SecurityFilterChain` và `WebSecurityCustomizer` beans | Có thể di trú từng class mà chưa đổi Java/Jakarta |
| Spring Security 5.8 | Phiên bản đệm chuẩn bị cho 6.0; nhiều API hiện đại đã có | Dọn deprecated APIs, matchers, method security và session assumptions |
| Spring Security 6.0+ | `WebSecurityConfigurerAdapter` và `antMatchers`/`mvcMatchers` DSL cũ **không còn**; Servlet types chuyển sang `jakarta.*` | Dùng `SecurityFilterChain`, `authorizeHttpRequests`, `requestMatchers`, `@EnableMethodSecurity` |
| Spring Security 6.5 | Chuẩn bị migration sang 7.x; một số matcher và DSL cũ deprecated for removal | Dùng Lambda DSL, xem `PathPatternRequestMatcher`, audit matchers và filter-chain boundaries |
| Spring Security 7.x | Lambda DSL là bắt buộc; `AntPathRequestMatcher`/`MvcRequestMatcher` bị loại khỏi đường cấu hình hiện đại | Chuẩn bị pattern semantics mới và kiểm thử đầy đủ trên Boot/Jakarta versions tương thích |

**Hai mốc không được nhầm:** `WebSecurityConfigurerAdapter` bị **deprecated ở 5.7**, nhưng bị **loại bỏ ở 6.0**. Trong 5.7/5.8, code cũ còn có thể biên dịch với cảnh báo; sang 6.0 thì cần thay. Không kết luận “chỉ cần bump version là Spring tự migrate class”.

**Spring Boot 2.7 → Boot 3.0** còn là nâng cấp hệ sinh thái: Boot 3 dùng Java 17+, Spring Framework 6 và Jakarta EE packages (ví dụ `jakarta.servlet` thay `javax.servlet`). Đây **không chỉ** là một lần đổi DSL bảo mật.

Một hướng nâng cấp có kiểm soát thường là: Boot 2.7 + Security 5.8 để chuẩn bị → Boot 3.x + Security 6.x → dọn các cảnh báo 6.5 chuẩn bị cho Boot 4/Security 7. Đối chiếu đúng BOM/dependency alignment thay vì ép một Spring Security major bất kỳ vào Boot major không tương thích.

## 3. Ba phương thức configure cũ: mỗi cái có trách nhiệm riêng

`WebSecurityConfigurerAdapter` là base class kiểu kế thừa để cấu hình nhiều khía cạnh của Spring Security:

| Cũ | Trách nhiệm | Thay bằng gì |
| --- | --- | --- |
| `configure(HttpSecurity http)` | Xác định chuỗi filter, request authorization, login, logout, CSRF, session, exception handling | Một hoặc nhiều `@Bean SecurityFilterChain` |
| `configure(WebSecurity web)` | Tùy biến cấp `WebSecurity`, nhất là `web.ignoring()` bỏ qua security filters | `@Bean WebSecurityCustomizer` **nếu thật cần bỏ qua**, hoặc ưu tiên `permitAll` ở filter chain |
| `configure(AuthenticationManagerBuilder auth)` | Đăng ký users, provider, JDBC/LDAP, password encoder, manager building | `UserDetailsService`, `PasswordEncoder`, `AuthenticationProvider`, `AuthenticationManager` beans tùy trường hợp |

Cách đọc một class cũ:

```text
@Configuration / @EnableWebSecurity
      |
      v
extends WebSecurityConfigurerAdapter
      |
      +-- configure(WebSecurity)
      |     -> REQUEST NÀO KHÔNG VÀO Spring Security?
      |
      +-- configure(HttpSecurity)
      |     -> REQUEST NÀO VÀO FILTER CHAIN?
      |     -> rule nào cho phép / từ chối?
      |     -> provider/login/logout/session/CSRF nào được bật?
      |
      +-- configure(AuthenticationManagerBuilder)
            -> credential được so thế nào?
            -> UserDetailsService nào, encoder nào?
            -> có custom providers hay LDAP/JDBC không?
```

**Đừng chỉ đọc `configure(HttpSecurity)`.** Một endpoint có vẻ yêu cầu xác thực trong `authorizeRequests` vẫn có thể không chạy các security filters nếu `configure(WebSecurity).ignoring()` đã bỏ qua nó từ trước.

### Những nơi khác cũng định nghĩa quyền

- `@EnableGlobalMethodSecurity` + `@PreAuthorize`/`@Secured`: quyền ở method/service.
- `@Order` hoặc nhiều WebSecurityConfigurerAdapter: thứ tự security chains.
- `@Bean` đặc biệt như custom filters, `AuthenticationProvider`, `AuthenticationEntryPoint`.
- Spring Boot properties về session, cookie, reverse proxy và OAuth2 client/provider.
- Controller routes, servlet path, reverse proxy path rewrite ảnh hưởng request matchers.

Một bản migration chỉ sửa một class nhưng bỏ qua method security, resources hoặc provider custom thường chưa đủ.

## 4. Ví dụ legacy Spring Security 5.x: đọc từng rule

Đây là một **mẫu mã legacy** thuộc cách viết Spring Security 5.x. **Không biên dịch nó bằng Security 6.5** vì class và DSL đã được loại bỏ.

```java
// Ví dụ để ĐỌC trong dự án legacy Security 5.x.
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.authentication.builders
        .AuthenticationManagerBuilder;
import org.springframework.security.config.annotation.method.configuration
        .EnableGlobalMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.builders.WebSecurity;
import org.springframework.security.config.annotation.web.configuration
        .EnableWebSecurity;
import org.springframework.security.config.annotation.web.configuration
        .WebSecurityConfigurerAdapter;

@Configuration
@EnableWebSecurity
@EnableGlobalMethodSecurity(prePostEnabled = true)
class LegacySecurityConfig extends WebSecurityConfigurerAdapter {

    @Override
    protected void configure(HttpSecurity http) throws Exception {
        http
            .authorizeRequests()
                .antMatchers("/assets/**").permitAll()
                .antMatchers("/login").permitAll()
                .antMatchers("/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated()
                .and()
            .formLogin()
                .permitAll()
                .and()
            .httpBasic();
    }

    @Override
    public void configure(WebSecurity web) throws Exception {
        web.ignoring().antMatchers("/assets/**");
    }

    @Override
    protected void configure(AuthenticationManagerBuilder auth)
            throws Exception {
        // Password {noop} CHỈ để minh họa môi trường test.
        auth.inMemoryAuthentication()
            .withUser("alice")
            .password("{noop}test-only-password")
            .roles("USER")
            .and()
            .withUser("root")
            .password("{noop}test-only-admin")
            .roles("ADMIN");
    }
}
```

Diễn giải:

1. `/assets/**` **bị ignored ở WebSecurity**, nên request này **bỏ qua FilterChainProxy**; rule `antMatchers("/assets/**").permitAll()` trong HttpSecurity trở thành dư thừa cho những request đã bị ignore.
2. `/login` được permit và `formLogin()` cung cấp authentication flow phù hợp. Với form login mặc định, Spring Security xử lý `POST /login`, trang login mặc định hoặc trang được custom cấu hình.
3. `/admin/**` yêu cầu user có authority `ROLE_ADMIN`. `hasRole("ADMIN")` tự thêm prefix `ROLE_`, không cần viết `hasRole("ROLE_ADMIN")`.
4. Các đường còn lại `anyRequest().authenticated()`: chỉ cần đã authenticated, chưa chắc cần một role đặc biệt.
5. `.and()` thoát configurer con trở về `HttpSecurity` theo DSL cũ.
6. `httpBasic()` bật cơ chế HTTP Basic bên cạnh form login, có thể khiến entry point/response 401 vs login redirect khác nhau theo loại request.
7. `@EnableGlobalMethodSecurity(prePostEnabled=true)` kích hoạt `@PreAuthorize`/`@PostAuthorize` ở method.
8. `{noop}` lưu password thô chỉ để demo. **Không dùng trên production**; phải dùng adaptive one-way hash/PasswordEncoder đúng policy.

**Chưa phải ứng dụng production:** còn cần HTTPS, session/cookie, CSRF, password hashing, error handling, account source, logout, kiểm thử security matchers. Mã ví dụ được chọn để hiểu rule chứ không đề nghị chạy bản cũ.

## 5. Viết lại theo Spring Security 6.5 với bean SecurityFilterChain

Thay vì subclass `WebSecurityConfigurerAdapter`, ứng dụng hiện đại xuất các beans cấu hình. Ví dụ class **trong Spring Boot 3.x/Java 17+**, dùng Spring Security 6.5 Servlet:

```java
package demo.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration
        .EnableMethodSecurity;
import org.springframework.security.config.annotation.web.configuration
        .EnableWebSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableWebSecurity
@EnableMethodSecurity
public class ModernSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/assets/**", "/login").permitAll()
                        .requestMatchers("/admin/**").hasRole("ADMIN")
                        .anyRequest().authenticated())
                .formLogin(Customizer.withDefaults())
                .httpBasic(Customizer.withDefaults())
                .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
                User.withUsername("alice")
                    .password(encoder.encode("demo-only-password"))
                    .roles("USER")
                    .build(),
                User.withUsername("root")
                    .password(encoder.encode("demo-only-admin"))
                    .roles("ADMIN")
                    .build());
    }
}
```

Khi dán vào project Spring Boot 3.x đã có `spring-boot-starter-web` và `spring-boot-starter-security`, class trên tạo security chain và nguồn user test. Các username/password trong ví dụ là **fixtures**, không phải credential production. Password encoder thật tạo hash bcrypt có salt; mỗi lần start có thể sinh string khác nhau. Production nên lưu hash trong DB/IdP và quản lý credential secrets đúng.

### Bảng đổi ý nghĩa, không chỉ đổi cú pháp

| Cấu hình cũ | Cấu hình mới | Giữ được gì? |
| --- | --- | --- |
| `extends WebSecurityConfigurerAdapter` | `@Bean SecurityFilterChain` | Thay inheritance bằng composition |
| `configure(HttpSecurity)` | Method bean nhận `HttpSecurity` và gọi `http.build()` | Security filters cho request tương ứng |
| `authorizeRequests()` | `authorizeHttpRequests(auth -> ...)` | Policy request, nhưng authorization implementation có thể khác |
| `antMatchers("/admin/**")` | `requestMatchers("/admin/**")` | Mục đích match URL; **phải test ngữ nghĩa matcher thực tế** |
| `.anyRequest().authenticated()` | `.anyRequest().authenticated()` trong lambda | Rule fallback ở **chain được chọn** |
| `.formLogin().and()` | `.formLogin(Customizer.withDefaults())` | Bật form login defaults |
| `.httpBasic()` | `.httpBasic(Customizer.withDefaults())` | Bật HTTP Basic defaults |
| `web.ignoring().antMatchers(...)` | Ưu tiên `requestMatchers(...).permitAll()` hoặc `WebSecurityCustomizer` | **Không hoàn toàn tương đương** nếu chuyển ignoring → permitAll |
| `configure(AuthenticationManagerBuilder)` | `UserDetailsService`/`PasswordEncoder`/provider beans | Cấu hình xác thực tường minh |
| `@EnableGlobalMethodSecurity(prePostEnabled=true)` | `@EnableMethodSecurity` | Kích hoạt pre/post method checks mặc định |

**Đổi sang `permitAll` đối với static assets là một thay đổi có chủ đích tốt hơn, không phải semantics 100% giống ignoring.** Nó giữ request bên trong security chain để Spring Security vẫn có thể áp dụng headers và nhiều lớp bảo vệ khác, trong khi authorization cho tài nguyên ấy là public.

### Đừng tắt CSRF chỉ để code mới “dễ chạy”

Ví dụ hiện đại **không** gọi `http.csrf(csrf -> csrf.disable())`. Với form login/browsers có cookie session, CSRF protection nên giữ và dùng token cho các request thay đổi trạng thái. Nếu ứng dụng thuần Bearer token stateless, cân nhắc riêng sau khi phân tích chính xác credential transport; không suy luận API JSON là không có CSRF.

## 6. Vì sao SecurityFilterChain bean là kiến trúc mới?

`SecurityFilterChain` là danh sách security filters và một `RequestMatcher` cho phạm vi request mà chain áp dụng. `FilterChainProxy` chọn **chuỗi đầu tiên khớp** để xử lý request.

```text
HttpServletRequest
      |
      v
DelegatingFilterProxy
      |
      v
FilterChainProxy
      |
      +-- SecurityFilterChain @Order(1): /api/**
      |           | match -> chạy các filters của API chain
      |
      +-- SecurityFilterChain @Order(2): /admin/**
      |           | match -> chạy các filters của admin chain
      |
      +-- SecurityFilterChain fallback: /** (mọi request còn lại)
                  | match -> chạy filters fallback
```

Mỗi request chỉ dùng **chain đầu tiên match**, không tự đi tiếp sang chain sau vì bị deny. Bởi vậy một chain `@Order(1)` có policy quá rộng có thể **che hoàn toàn** chain quản trị ở dưới.

### securityMatcher khác requestMatchers

- `http.securityMatcher("/api/**")`: quyết định **toàn bộ SecurityFilterChain này có áp dụng** cho request không.
- `authorizeHttpRequests(auth -> auth.requestMatchers("/api/admin/**")...)`: khi request **đã nằm trong chain**, chọn rule authorization nào trong chain ấy.
- `anyRequest()` chỉ xét **mọi request được chọn vào chain**, không có nghĩa bảo vệ những URL đã không match bất kỳ chain nào.

Không có fallback chain cho `/portal/**` mà các chains khác chỉ match `/api/**` có thể để request `/portal/**` **không được Spring Security bảo vệ** (những bảo vệ khác ở proxy/container không tự tương đương).

### Ví dụ nhiều SecurityFilterChain

```java
@Configuration
@EnableWebSecurity
class MultipleChainsSecurity {

    @Bean
    @Order(1)
    SecurityFilterChain api(HttpSecurity http) throws Exception {
        return http
                .securityMatcher("/api/**")
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/api/public/**").permitAll()
                        .requestMatchers("/api/admin/**").hasRole("ADMIN")
                        .anyRequest().authenticated())
                .httpBasic(Customizer.withDefaults())
                .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain browser(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/login", "/assets/**").permitAll()
                        .anyRequest().authenticated())
                .formLogin(Customizer.withDefaults())
                .build();
    }
}
```

Các imports là cùng nhóm Spring Security ở trên cộng `org.springframework.core.annotation.Order`. Đây là **một cấu hình thay thế** cho `ModernSecurityConfig`, không bật cả hai ví dụ cùng lúc khi chưa kiểm soát thứ tự. Cần nguồn `UserDetailsService`/`AuthenticationProvider` và test thực tế; class không tự chạy bằng `javac`.

Lưu ý trong chain API ở trên vẫn giữ CSRF defaults. Với browser tự gắn HTTP Basic credentials, CSRF vẫn có thể liên quan; không disable chỉ vì route bắt đầu bằng `/api`.

**Một bẫy phổ biến:** nếu `securityMatcher("/secured/**")` mà dùng form login mặc định `POST /login`, endpoint đó có thể **không thuộc chain**; việc filter login không được chạy gây 404 hoặc flow sai. Hãy đặt `loginProcessingUrl`/`loginPage` trong phạm vi đúng, hoặc dùng fallback chain hợp lệ. Tài liệu Spring Security cảnh báo rõ về endpoint do security filters cung cấp.

## 7. URL matching khác nhau giữa các major versions

Một cuộc chuyển đổi ngây thơ:

```text
Legacy:
  .antMatchers("/admin/**").hasRole("ADMIN")

New:
  .requestMatchers("/admin/**").hasRole("ADMIN")
```

có vẻ tương đương nhưng **không được phép mặc định rằng implementation matchers và path normalization giống hệt**.

### Ant, MVC và PathPattern

- `AntPathRequestMatcher` trong các version cũ làm việc theo quy tắc Ant-style trên request path, có chi tiết về servletPath/pathInfo.
- `MvcRequestMatcher` xét ngữ nghĩa Spring MVC và có thể cần `HandlerMappingIntrospector`, servletPath phù hợp.
- `PathPatternRequestMatcher` dùng `PathPattern`, trong Spring Security 7 là phương hướng mặc định; path được viết theo URL **tuyệt đối trong ứng dụng, bỏ context root**, và có quy tắc servlet basePath.
- Trong Spring Security 6.5, `AntPathRequestMatcher`/`MvcRequestMatcher` đã deprecated for removal, khuyến nghị chuẩn bị `PathPatternRequestMatcher`.

Điều cần test không chỉ `/admin` mà còn:

| Đường yêu cầu | Nguy cơ |
| --- | --- |
| `/admin/report` | Đường bình thường |
| `/admin` | Pattern `/admin/**` có match gốc hay không? Kiểm tra theo matcher/version |
| `/adminx` | Không được vô tình match prefix `/admin` |
| `/ADMIN/report` | Case sensitivity và normalization |
| `/api;param=1/admin` | Semicolon/path parameters/firewall |
| `/api//admin` | Double-slash handling/firewall |
| `/app/admin/report` | `/app` là context path, không nhất thiết nằm trong matcher pattern |
| `/servlet/admin/report` | Non-default servletPath cần builder/basePath |
| Encoded slash, dot segments | URL decoding/path traversal và `StrictHttpFirewall` |
| `/admin/report?x=1` | Query string không phải path, không nên điều khiển matcher quyền |

Khi chuyển sang Security 7, đọc hướng dẫn `6.5/migration-7/web.html` về `PathPatternRequestMatcher`, và kiểm thử những pattern có Ant-only syntax hoặc servlet mapping đặc biệt. Không tự tắt `StrictHttpFirewall` để “làm matcher cũ hoạt động”.

### Một cách chủ động chuẩn bị cho 7.x

Spring Security 6.5 cung cấp `PathPatternRequestMatcher` và cơ chế cấu hình để DSL dùng PathPattern matchers trước khi bump major:

```java
// Bean chuẩn bị migration trên Security 6.5, theo tài liệu chính thức:
@Bean
PathPatternRequestMatcherBuilderFactoryBean requestMatcherBuilder() {
    return new PathPatternRequestMatcherBuilderFactoryBean();
}
```

Class `PathPatternRequestMatcherBuilderFactoryBean` thuộc `org.springframework.security.config.web`. Đây là **mảnh config**: cần import, Spring context và kiểm thử mapping MVC đúng. Nếu dự án đang dùng nhiều servlets hoặc non-default servlet base paths, đừng bật tùy tiện trước khi đánh giá matchers.

**Không hard-code `/app` vào mọi matcher** chỉ vì ứng dụng có `server.servlet.context-path=/app`: PathPattern matcher thường đánh giá path **loại trừ context path**, nhưng các servlet paths khác có quy tắc riêng.

## 8. WebSecurityCustomizer và permitAll: giống quyền truy cập, khác bảo vệ

Đoạn legacy:

```java
@Override
public void configure(WebSecurity web) {
    web.ignoring().antMatchers("/css/**", "/js/**");
}
```

Một chuyển đổi có thể giữ semantics ignoring bằng bean:

```java
@Bean
WebSecurityCustomizer webSecurityCustomizer() {
    return web -> web.ignoring()
            .requestMatchers("/css/**", "/js/**");
}
```

Nhưng đây **không phải khuyến nghị mặc định**. `web.ignoring()` loại những request ấy khỏi Spring Security `FilterChainProxy`. Điều đó cũng khiến chúng không được áp dụng các security filters liên quan, trong đó có response headers của Spring Security và các cơ chế khác mà ứng dụng trông đợi.

Cách thường được khuyến nghị hơn:

```java
http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/css/**", "/js/**").permitAll()
        .anyRequest().authenticated());
```

Khác biệt quan trọng:

| Khía cạnh | `web.ignoring()` | `permitAll()` |
| --- | --- | --- |
| Authorization đọc static resource | Cho phép vì bỏ security chain | Cho phép bởi authorization manager |
| Chạy Spring Security filters | **Không** | **Có**, trong chain được chọn |
| Security response headers do Spring Security | Không được áp dụng từ chain | Có thể được áp dụng |
| CSRF/other filters trên endpoint public | Bị bỏ qua ở Spring Security | Vẫn đi qua filters, trừ khi filter riêng exclude |
| Visibility/metrics/filter behavior | Thay đổi vì bypass | Dễ thống nhất với app |
| Thích hợp mặc định cho dynamic endpoints | Không | Có thể, tùy quyền thực tế |

**`permitAll()` chỉ bỏ yêu cầu authorization; nó không tắt CSRF, không miễn mọi authentication filter và không biến POST sai CSRF thành hợp lệ.** Ví dụ `POST /signup` đã permitAll vẫn có thể cần CSRF token trong ứng dụng cookie-based.

Đặc biệt không chuyển `web.ignoring().antMatchers("/api/**")` thành `permitAll` mà không hiểu: một cách là bỏ hết Spring Security, cách kia cho public access; cả hai đều có thể nguy hiểm nếu `/api/**` chứa dữ liệu riêng.

## 9. Chuyển AuthenticationManagerBuilder và cách đăng ký provider

Một class cũ thường có:

```java
@Override
protected void configure(AuthenticationManagerBuilder auth)
        throws Exception {
    auth.userDetailsService(myUserDetailsService)
        .passwordEncoder(myPasswordEncoder);
}
```

Ở cấu hình bean-based, có những lựa chọn tùy use case:

1. **Form login username/password thông thường:** công bố `UserDetailsService` và `PasswordEncoder` beans; kiểm tra Spring Boot/Spring Security có thực sự chọn đúng provider/manager.
2. **Custom AuthenticationProvider:** đăng ký provider cho đúng `HttpSecurity` hoặc `AuthenticationManager`.
3. **Custom login controller/service cần gọi manager:** cung cấp/inject `AuthenticationManager` có wiring rõ ràng, không lấy đại một object chưa được kết nối với filter login.
4. **Multi-chain:** một chain có thể có authentication manager riêng; không giả định tất cả dùng chung manager toàn cục.

Ví dụ explicit provider/manager cho Spring Security 6.5:

```java
@Bean
AuthenticationManager explicitPasswordManager(
        UserDetailsService users, PasswordEncoder encoder) {

    DaoAuthenticationProvider dao = new DaoAuthenticationProvider(users);
    dao.setPasswordEncoder(encoder);
    return new ProviderManager(dao);
}
```

Imports: `org.springframework.security.authentication.AuthenticationManager`, `org.springframework.security.authentication.ProviderManager`, `org.springframework.security.authentication.dao.DaoAuthenticationProvider`.

Khi cần chain dùng đúng manager này:

```java
@Bean
SecurityFilterChain customLoginChain(
        HttpSecurity http,
        AuthenticationManager explicitPasswordManager) throws Exception {

    return http
            .authenticationManager(explicitPasswordManager)
            .authorizeHttpRequests(auth -> auth
                    .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .build();
}
```

Hai snippet là một **cấu hình thay thế**, không bật song song với class đầy đủ ở mục 5 mà không quản lý các beans cùng loại và chain order. Kiểm tra user service, password encoder, success/failure handling và context persistence bằng integration test. Nếu tạo `ProviderManager` thủ công, các authentication events/publisher, erase-credentials, parent providers và các cấu hình tùy biến có thể không tự được sao chép từ manager mặc định.

**Không tự viết password check bằng `raw.equals(storedHash)`**, hoặc chuyển hash từ BCrypt sang `{noop}` để “sửa lỗi Login 401”. Di trú encoder/hashes là một kế hoạch riêng, có kiểm thử hash legacy và auto rehash khi đã xác minh.

### Có cần AuthenticationManager bean cho mọi ứng dụng?

**Không.** Một ứng dụng chỉ cần form login tiêu chuẩn có thể hoạt động với `UserDetailsService`/`PasswordEncoder` và security chain mà không công bố global `AuthenticationManager` bean riêng. Hãy tạo explicit manager khi kiến trúc yêu cầu, rồi kiểm thử tránh circular dependency và duplicate provider wiring.

## 10. @EnableGlobalMethodSecurity → @EnableMethodSecurity

Method authorization không chỉ nằm trong HTTP rules. Ví dụ legacy:

```java
@EnableGlobalMethodSecurity(prePostEnabled = true)
class LegacyMethodSecurity {}
```

Chuyển sang Spring Security 6.x:

```java
@Configuration
@EnableMethodSecurity
class MethodSecurityConfiguration {}
```

`@EnableMethodSecurity` bật `@PreAuthorize`/`@PostAuthorize`/`@PreFilter`/`@PostFilter` **theo mặc định**, trong khi `@Secured` và JSR-250 có cờ riêng.

### Bẫy thay đổi default khi migrate

Nếu cấu hình cũ chỉ bật `securedEnabled=true` mà **không** bật pre/post annotations:

```java
@EnableGlobalMethodSecurity(securedEnabled = true)
```

chuyển trực tiếp thành:

```java
@EnableMethodSecurity(securedEnabled = true)
```

có thể vô tình **bật thêm** `@PreAuthorize`/`@PostAuthorize` vì `prePostEnabled=true` là mặc định mới. Để giữ gần sát trạng thái cũ:

```java
@EnableMethodSecurity(
        securedEnabled = true,
        prePostEnabled = false)
```

Tương tự `jsr250Enabled=true` khi dùng `@RolesAllowed`/`@PermitAll` cần kiểm chứng đúng javax/jakarta annotation imports và behavior. Spring Security method security dựa Spring AOP, nên **self-invocation** (method trong cùng object gọi nhau trực tiếp) có thể bỏ qua proxy, không được mặc định coi test annotation là đã bảo vệ mọi đường gọi.

### Không dùng HTTP authorization làm thay thế quyền domain

`.requestMatchers("/admin/**").hasRole("ADMIN")` bảo vệ URL, nhưng một service `approveOrder(id)` có thể được gọi từ scheduled job, message listener hoặc API khác. Nếu cần bảo vệ nghiệp vụ, dùng method/service authorization đúng và kiểm tra resource ownership/tenant. Việc migrate sang `@EnableMethodSecurity` không tự tạo quyền domain chưa được thiết kế.

## 11. @EnableWebSecurity, request matchers và Spring Boot auto-configuration

Trong Spring Boot, khi ứng dụng cung cấp `SecurityFilterChain` bean, Boot thường rút lại security chain mặc định do auto-configuration tạo. Điều đó có nghĩa:

- Bạn **phải** có rule fallback phù hợp (ví dụ `anyRequest().authenticated()`/`denyAll()` tùy policy).
- Đừng tưởng vì đã thêm một chain `/api/**` thì Boot tự bảo vệ các URL còn lại.
- Đừng tạo một `@Bean WebSecurityCustomizer` mà bỏ qua quá rộng rồi nghĩ fallback chain bảo vệ được.
- Kiểm tra các filter/beans từ starter OAuth2 resource server, OAuth2 client, management/Actuator và service-specific security.
- Nếu dùng multiple chains, định nghĩa rõ `@Order` và matcher của từng chain.

### Security filter-provided endpoints

Một số endpoint được cung cấp bởi chính filter chain: form login process, logout, OAuth2 authorization redirect/callback. Nếu `securityMatcher` loại các đường này ra, chúng có thể biến mất dù bạn vẫn gọi `formLogin`/`oauth2Login` trong chain.

Ví dụ (minh họa sai phạm vi):

```java
http.securityMatcher("/secure/**")
    .formLogin(Customizer.withDefaults());
```

`POST /login` mặc định **không thuộc** `/secure/**`. Muốn nó do chain này phục vụ, cần thiết kế `loginProcessingUrl`/`loginPage` nằm trong scope, hoặc một fallback chain có setup hợp lệ. Nếu đặt custom login page, ứng dụng phải cung cấp GET route/template tương ứng; Spring không tự generate giao diện tùy chỉnh.

### DispatcherType và ERROR/FORWARD

Spring Security 6 có thay đổi về dispatch types được authorize. Một `ERROR` dispatch đến `/error` có thể bị rule authenticated chặn, làm người phát triển thấy 401/403 thay cho lỗi gốc. Khi phù hợp, cấu hình:

```java
http.authorizeHttpRequests(auth -> auth
        .dispatcherTypeMatchers(DispatcherType.ERROR).permitAll()
        .requestMatchers("/admin/**").hasRole("ADMIN")
        .anyRequest().authenticated());
```

Import `jakarta.servlet.DispatcherType`. Đây là ví dụ cần áp dụng theo **error-page security policy thực tế**, không phải lời khuyên permit mọi dispatcher type một cách vô điều kiện. `permitAll` không tắt các filters còn lại; bảo vệ error response khỏi lộ exception, stack trace, secrets.

## 12. Các API lỗi thời khác đáng nhận diện khi đọc code cũ

| Dấu hiệu trong source | Trạng thái/hướng hiện đại | Điều cần kiểm thử |
| --- | --- | --- |
| `WebSecurityConfigurerAdapter` | Removed 6.x → bean `SecurityFilterChain` | Bean/chain thực sự được đăng ký |
| `authorizeRequests()` | Ưu tiên `authorizeHttpRequests(...)` | Authorization decisions khác nhau không? |
| `antMatchers(...)`/`mvcMatchers(...)` trong DSL | Removed 6.0 → `requestMatchers(...)` | URL matching, servletPath, encoded paths |
| `antMatcher(...)` chọn chain | `securityMatcher(...)` | Chỉ chain nào match, fallback còn không |
| `httpBasic().and()` | `httpBasic(Customizer.withDefaults())` | Entry point 401, WWW-Authenticate |
| `formLogin().and()` | `formLogin(Customizer.withDefaults())` | Login endpoints, CSRF, session |
| `csrf().disable()` | Nếu có lý do thật: `csrf(csrf -> csrf.disable())` | **Không** biến “dịch cú pháp” thành tắt CSRF bừa bãi |
| `authorizeRequests().anyRequest()` | `authorizeHttpRequests(auth -> auth.anyRequest()...)` | Quyền fallback |
| `@EnableGlobalMethodSecurity` | `@EnableMethodSecurity` | prePost/secured/jsr250 flags |
| `javax.servlet.Filter` | `jakarta.servlet.Filter` ở Boot 3/Security 6 | Third-party dependencies, Filter registration |
| `AntPathRequestMatcher` custom | Chuẩn bị `PathPatternRequestMatcher` cho 7 | Path semantics và servlet mappings |
| `.apply(new CustomDsl())` | `.with(customDsl, customizer)` trong 6.2+/7 | Filter order và customization |
| `shouldFilterAllDispatcherTypes(false)` | `dispatcherTypeMatchers(...)` | ERROR/FORWARD dispatch đúng policy |
| `web.ignoring().antMatchers(...)` | `WebSecurityCustomizer` hoặc khuyến nghị `permitAll` | Static headers, filters bypass |
| `AuthenticationManagerBuilder` trong adapter | User/service/provider/manager beans | Provider wiring, password hash, events |
| `SecurityContextPersistenceFilter` assumptions | Xem `SecurityContextHolderFilter`/explicit save ở 6 | Custom login persist SecurityContext |
| `authorizeHttpRequests().and()` | Lambda DSL bắt buộc ở 7 | Không còn chaining không-lambda |

### "Deprecated" khác "removed"

- **Deprecated:** code có thể vẫn compile ở version hiện tại, nhưng compiler cảnh báo và framework đề nghị chuyển.
- **Deprecated for removal:** khả năng bị xóa ở major tiếp theo cao; càng cần test trước khi nâng.
- **Removed:** compile error vì symbol đã không còn, phải dùng API thay thế có semantic tương ứng.

Không sửa tất cả deprecations bằng search-and-replace mù. Thứ tự filter, security matcher và authentication method có thể thay đổi behavior.

## 13. Spring Security 7.x: còn điều gì cần chuẩn bị?

Tài liệu migration từ 6.5 sang 7.x nêu rõ:

- **Lambda DSL bắt buộc:** các cách chain `http.authorizeHttpRequests().anyRequest()...and()`/`http.httpBasic()` không còn là hướng hợp lệ; dùng `authorizeHttpRequests(auth -> ...)`, `httpBasic(Customizer.withDefaults())`, `csrf(csrf -> ...)`.
- `AntPathRequestMatcher` và `MvcRequestMatcher` không còn được hỗ trợ như các implementations legacy cho DSL; `PathPatternRequestMatcher` là lựa chọn mặc định.
- Pattern đường dẫn phải tuân thủ quy tắc PathPattern, URL **tuyệt đối nhưng không gồm context root**; đặc biệt kiểm tra non-default servlet paths.
- Các API custom DSL `apply()` cần chuyển sang `with()`.
- Cấu hình cũ về session, headers, dispatch types hoặc authorization manager có thể có behavior mới; đọc guide theo **version cụ thể đang deploy**.
- Boot 4/Security 7 còn có các thay đổi ngoài bảo mật (ví dụ Jackson alignment) nên phải test toàn ứng dụng, không chỉ SecurityConfig.

**Không gọi `PathPatternRequestMatcher` là tên khác của `AntPathRequestMatcher`.** Đây là hai cách định nghĩa semantics đường dẫn. Test URL oddities và gateway rewrite trước khi nâng cấp production.

## 14. Servlet vs WebFlux: hai DSL không thay thế lẫn nhau

Code legacy WebFlux có thể dùng `@EnableWebFluxSecurity` và `ServerHttpSecurity`, không phải `WebSecurityConfigurerAdapter` của Servlet.

| Servlet MVC | Reactive WebFlux |
| --- | --- |
| `HttpSecurity` | `ServerHttpSecurity` |
| `SecurityFilterChain` | `SecurityWebFilterChain` |
| `authorizeHttpRequests(...)` | `authorizeExchange(...)` |
| `requestMatchers(...)` | `pathMatchers(...)` |
| `UsernamePasswordAuthenticationFilter` | Authentication WebFilters |
| `HttpSession`/`SecurityContextHolder` | `WebSession`/`ReactiveSecurityContextHolder` |
| `OncePerRequestFilter` | `WebFilter` |
| Servlet `jakarta.servlet.*` | Reactive APIs |

Ví dụ cấu hình WebFlux (snippet, không phải full project):

```java
@Bean
SecurityWebFilterChain reactiveSecurity(ServerHttpSecurity http) {
    return http
            .authorizeExchange(auth -> auth
                    .pathMatchers("/public/**").permitAll()
                    .anyExchange().authenticated())
            .httpBasic(Customizer.withDefaults())
            .build();
}
```

Không cố gọi `HttpSecurity` của MVC trong WebFlux hoặc chuyển `ServerHttpSecurity` sang `HttpSecurity` chỉ vì cả hai cùng có chữ “security”.

## 15. Java 17 chạy độc lập: phân biệt public, ignored và filter-chain selection

Ví dụ này không import Spring để có thể **biên dịch bằng Java SE 17** và cho output deterministic. Nó mô phỏng một số khái niệm:

- Cấu hình cũ dùng `web.ignoring("/assets/**")` cho public assets → allowed nhưng **không chạy Spring Security filters**.
- Cấu hình mới dùng `requestMatchers("/assets/**").permitAll()` → allowed nhưng **vẫn chạy filters**.
- `hasRole("ADMIN")` kiểm tra authority `ROLE_ADMIN`.
- `securityMatcher("/api/**")` chọn API chain, không thay các authorization rules bên trong.
- Nếu không có fallback chain, request khác có thể **không được bảo vệ bởi Spring Security**.

Tạo file **`LegacySecurityPolicyDemo.java`**:

```java
import java.util.*;

public class LegacySecurityPolicyDemo {
    record Request(
            String path, boolean authenticated, Set<String> authorities) {}

    record Decision(
            boolean allowed, boolean securityFiltersApplied,
            String matchedRule) {}

    // Mô phỏng prefix pattern đơn giản, KHÔNG phải Ant/Mvc/PathPattern engine.
    static boolean matches(String pattern, String path) {
        if (pattern.equals("/**")) return path.startsWith("/");
        if (pattern.endsWith("/**")) {
            String prefix = pattern.substring(0, pattern.length() - 3);
            return path.equals(prefix) || path.startsWith(prefix + "/");
        }
        return pattern.equals(path);
    }

    static boolean role(Request request, String role) {
        return request.authenticated()
                && request.authorities().contains("ROLE_" + role);
    }

    static Decision evaluate(Request r, boolean modern) {
        if (matches("/assets/**", r.path())) {
            return modern
                    ? new Decision(true, true, "assets_permitAll")
                    : new Decision(true, false, "assets_ignored");
        }

        if (matches("/login", r.path())) {
            return new Decision(true, true, "login_permitAll");
        }

        if (matches("/admin/**", r.path())) {
            return new Decision(
                    role(r, "ADMIN"), true, "admin_hasRole");
        }

        return new Decision(
                r.authenticated(), true, "fallback_authenticated");
    }

    static String apiChainSelection(String path, boolean hasFallback) {
        if (matches("/api/**", path)) return "API_CHAIN";
        return hasFallback ? "DEFAULT_CHAIN" : "NO_SECURITY_CHAIN";
    }

    public static void main(String[] args) {
        Request assets = new Request("/assets/app.css", false, Set.of());
        Decision oldAssets = evaluate(assets, false);
        Decision newAssets = evaluate(assets, true);

        System.out.println("oldAssetsAllowed=" + oldAssets.allowed());
        System.out.println("oldAssetsFiltered="
                + oldAssets.securityFiltersApplied());
        System.out.println("newAssetsAllowed=" + newAssets.allowed());
        System.out.println("newAssetsFiltered="
                + newAssets.securityFiltersApplied());

        Request guestAdmin =
                new Request("/admin/report", false, Set.of());
        Request userAdmin = new Request(
                "/admin/report", true, Set.of("ROLE_USER"));
        Request actualAdmin = new Request(
                "/admin/report", true, Set.of("ROLE_ADMIN"));

        System.out.println("guestAdminAllowed="
                + evaluate(guestAdmin, true).allowed());
        System.out.println("userAdminAllowed="
                + evaluate(userAdmin, true).allowed());
        System.out.println("adminAllowed="
                + evaluate(actualAdmin, true).allowed());

        System.out.println("anonymousLoginAllowed="
                + evaluate(new Request("/login", false, Set.of()), true)
                        .allowed());
        System.out.println("anonymousPrivateAllowed="
                + evaluate(new Request("/private", false, Set.of()), true)
                        .allowed());

        System.out.println("apiRequestChain="
                + apiChainSelection("/api/orders", true));
        System.out.println("uiRequestChain="
                + apiChainSelection("/ui/home", true));
        System.out.println("missingFallback="
                + apiChainSelection("/ui/home", false));
    }
}
```

Chạy:

```bash
javac LegacySecurityPolicyDemo.java
java LegacySecurityPolicyDemo
```

**Stdout đã kiểm tra:**

```text
oldAssetsAllowed=true
oldAssetsFiltered=false
newAssetsAllowed=true
newAssetsFiltered=true
guestAdminAllowed=false
userAdminAllowed=false
adminAllowed=true
anonymousLoginAllowed=true
anonymousPrivateAllowed=false
apiRequestChain=API_CHAIN
uiRequestChain=DEFAULT_CHAIN
missingFallback=NO_SECURITY_CHAIN
```

### Đọc kết quả đúng

- Cả old và new assets đều “allowed”, nhưng `oldAssetsFiltered=false` và `newAssetsFiltered=true` chứng minh lý do **ignoring không tương đương permitAll**.
- Guest và user `ROLE_USER` không được phép vào admin route; chỉ user authenticated có `ROLE_ADMIN` được cho qua rule.
- `anonymousLoginAllowed=true` cho thấy login page phải được truy cập trước khi authenticated.
- `anonymousPrivateAllowed=false` minh họa fallback yêu cầu đăng nhập.
- `apiRequestChain=API_CHAIN` và `uiRequestChain=DEFAULT_CHAIN` minh họa first-match chain selection.
- `missingFallback=NO_SECURITY_CHAIN` minh họa nguy cơ khi định nghĩa API-only chain mà bỏ protection cho phần còn lại.

**Giới hạn:** `matches(...)` chỉ hỗ trợ exact path và hậu tố `/**` rất đơn giản. Nó không mô phỏng `AntPathRequestMatcher`, `MvcRequestMatcher`, `PathPatternRequestMatcher`, URL decoding, servletPath, contextPath, firewall, HTTP methods, CSRF, sessions hay JWT. Cần integration tests với Spring Security thật trước khi coi một policy tương đương.

## 16. Kiểm thử quy tắc sau migration với Spring Security Test

Một cấu hình mới **compile** chưa đủ. Phải kiểm tra request/response với `spring-security-test` + Spring MVC `MockMvc`, dùng application beans và security chain thật.

Dependencies trong project Spring Boot 3.x có test setup:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Mẫu test fragment (cần các controllers `/private`, `/admin/report`, static asset routes phù hợp trong test app):

```java
@SpringBootTest
@AutoConfigureMockMvc
class MigrationSecurityTest {

    @Autowired MockMvc mvc;

    @Test
    void anonymousCannotReadPrivatePage() throws Exception {
        mvc.perform(get("/private"))
                .andExpect(status().is3xxRedirection());
    }

    @Test
    void loggedInUserWithoutAdminRoleIsForbidden() throws Exception {
        mvc.perform(get("/admin/report")
                .with(user("alice").roles("USER")))
                .andExpect(status().isForbidden());
    }

    @Test
    void adminHasAccessToAdminRoute() throws Exception {
        mvc.perform(get("/admin/report")
                .with(user("root").roles("ADMIN")))
                .andExpect(status().isOk());
    }

    @Test
    void realPasswordLoginStillWorks() throws Exception {
        mvc.perform(formLogin()
                .user("alice")
                .password("demo-only-password"))
                .andExpect(authenticated());
    }
}
```

Imports: `org.springframework.boot.test.context.SpringBootTest`, `org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc`, `org.springframework.beans.factory.annotation.Autowired`, `org.springframework.test.web.servlet.MockMvc`, `org.junit.jupiter.api.Test`, static `org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get`, `org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user`, `org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestBuilders.formLogin`, `org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers.authenticated` và `org.springframework.test.web.servlet.result.MockMvcResultMatchers.status`.

**Chú ý:** `with(user(...))` mô phỏng authenticated principal để test authorization, **không xác minh password** qua `DaoAuthenticationProvider`. Muốn kiểm thử form-login credential flow, dùng `formLogin()` với user source/encoder thật trong test configuration. Trong nhiều dự án, request unauthorized không trả redirect mà trả 401 JSON (HTTP Basic/Bearer); điều chỉnh assertions theo contract **đã thống nhất**, không hard-code mọi app phải là 302.

Khi test các routes không có controller handler trong fixture, có thể nhận `404` sau khi được authorization cho phép; cần cung cấp endpoint hoặc xác minh filter/authorization outcome có chủ đích, không gán `200` cho route không tồn tại.

### Test các trường hợp dễ gây bypass

| Test | Kỳ vọng |
| --- | --- |
| Anonymous `GET /login` | Cho phép; login page hoạt động |
| Anonymous `GET /private` | Redirect login hoặc 401 theo cơ chế |
| Anonymous `GET /admin/report` | Không được truy cập |
| User ROLE_USER vào `/admin/report` | 403 |
| User ROLE_ADMIN vào `/admin/report` | Cho phép khi resource tồn tại |
| `GET /assets/app.css` | Public nhưng security headers còn khi dùng permitAll |
| `POST /login` password sai | Failure handler, không tạo authenticated session |
| `POST /transfer` thiếu CSRF trên cookie-based browser | Bị từ chối theo CSRF policy |
| `POST /logout` với CSRF hợp lệ | Vô hiệu session theo policy |
| `GET /adminx` | Không bị nhầm `/admin/**` |
| `GET /ADMIN/report` | Case handling theo matcher policy |
| Servlet context path khác `/` | Rules match path đúng |
| Encoded slash/semicolon/traversal | Firewall/matcher xử lý an toàn |
| API chain `/api/**` và browser chain `/**` | Chọn đúng chain đầu tiên |
| `GET /error` / ERROR dispatch | Error handling không bị double failure |
| Session cookie sau login | Tạo/rotate ID và persist context |
| Method `@PreAuthorize` được gọi | Không có quyền thì bị từ chối |
| WebSecurity ignoring static | Biết rõ không được Spring Security áp headers |
| Boot version bump | Dependencies resolve, không còn javax servlet/API removed |
| HTTP Basic vs form login | Entry point, request matchers, 401/403/302 đúng |
| OAuth2 resource server/custom filters | Matcher và provider thật, không chỉ bean tồn tại |
| Zero matching chains | Không có unprotected route ngoài chủ đích |

## 17. Checklist điều tra compile error khi nâng cấp

### "Cannot resolve symbol WebSecurityConfigurerAdapter"

- Xác định đang sử dụng Spring Security 6.x/7.x.
- Bỏ inheritance và chuyển logic `configure(HttpSecurity)` sang bean `SecurityFilterChain`.
- Tách `configure(WebSecurity)` thành quyết định giữa `permitAll` và `WebSecurityCustomizer`.
- Tách `configure(AuthenticationManagerBuilder)` thành nguồn user/provider/manager beans.
- Đừng thêm dependency Security 5.x vào Boot 3 chỉ để class cũ xuất hiện: dễ tạo xung đột Spring Framework/Jakarta.

### "Cannot resolve method antMatchers" hoặc "mvcMatchers"

- Thay bằng `requestMatchers(...)` phù hợp DSL.
- Kiểm tra import, Spring MVC presence, servlet path và matcher behavior.
- Với 6.5 chuẩn bị 7, đánh giá `PathPatternRequestMatcher`.
- Chạy URL security tests; đừng chỉ để compiler sửa cú pháp.

### "package javax.servlet does not exist"

- Boot 3/Spring Framework 6 chuyển sang Jakarta packages: `jakarta.servlet.*`.
- Kiểm tra các custom Filter, HttpServletRequest/Response, interceptors và thư viện bên thứ ba.
- Không trộn `javax.servlet.Filter` với `jakarta.servlet.Filter` rồi cast/bridge.
- Kiểm tra servlet container version và plugin/dependency BOM.

### "No qualifying bean of type AuthenticationManager"

- Không còn cách `authenticationManagerBean()` từ adapter.
- Nếu cần manager cho custom flow, khai báo/nhận manager thông qua config tường minh hoặc `AuthenticationConfiguration.getAuthenticationManager()` ở context phù hợp.
- Xác minh provider, encoder, UserDetailsService được wiring đúng.
- Tránh vòng phụ thuộc: manager bean inject chính nó hoặc một filter bean lại inject security config chưa sẵn sàng.

### "POST /login returns 404"

- SecurityFilterChain có `securityMatcher` loại `/login` ra không?
- `formLogin()`/`loginProcessingUrl()` có được bật tại chain đúng không?
- Custom login page GET route có tồn tại không?
- Reverse proxy/path rewrite/contextPath có thay đổi request thực tế không?

### "Every POST now returns 403"

- Kiểm tra CSRF token và mechanism, chứ không tắt CSRF vội.
- Nếu client chuyển sang Bearer stateless, phân tích riêng transport credential và SecurityFilterChain.
- Kiểm tra filter order/CSRF matcher và error dispatch, cùng với request mapping.

### "Static assets no longer have security headers"

- Có `web.ignoring()` không? Nếu có, filters không chạy.
- Chuyển sang `permitAll` cho assets phù hợp, giữ header writer.
- Kiểm tra cache headers/CSP ở edge và app, tránh gây double headers mâu thuẫn.

## 18. Sai lầm migration thường gặp

**Sai lầm 1 — Chỉ đổi tên class.** `WebSecurityConfigurerAdapter` không thể thay đơn thuần bằng `SecurityFilterChain` mà giữ ba override; phải chia đúng các trách nhiệm.

**Sai lầm 2 — Lấy `antMatchers` thành `requestMatchers` mà không test path.** Security 6/7 thay matcher semantics; URL edge cases có thể đổi.

**Sai lầm 3 — Chuyển `web.ignoring` sang `permitAll` nhưng tuyên bố không đổi behavior.** Mức access tương tự cho static nhưng filters/headers khác.

**Sai lầm 4 — Dùng `web.ignoring("/api/**")` vì muốn API public.** Bỏ tất cả security filters có thể vô tình xóa CSRF/headers/observability; audit scope và dùng authorization policy có kiểm soát.

**Sai lầm 5 — Quên `anyRequest` hoặc fallback chain.** Một URL không match chain nào có thể nằm ngoài sự bảo vệ của Spring Security.

**Sai lầm 6 — Đặt `@Order` sai.** Chain `/**` đứng trước làm chain `/api/**` không được chọn.

**Sai lầm 7 — Nghĩ `securityMatcher` và `requestMatchers` tương đương.** Một cái chọn chain, một cái chọn policy trong chain.

**Sai lầm 8 — Tắt CSRF để “fix all 403”.** Nếu browser dùng session cookie/form login, nguy cơ CSRF còn nguyên.

**Sai lầm 9 — Bỏ password encoder hoặc dùng `{noop}`.** Không làm yếu password storage để sửa compile/login error; migration credential là việc riêng.

**Sai lầm 10 — Thấy `@Bean AuthenticationManager` là tưởng web filter tự dùng.** Phải kiểm tra actual manager và filter chain wiring.

**Sai lầm 11 — Bỏ qua `@EnableGlobalMethodSecurity` khi loại adapter.** Method-level authorization có thể ngừng hoặc thay default.

**Sai lầm 12 — Chuyển securedEnabled sang `@EnableMethodSecurity` nhưng bật thêm prePost ngoài ý định.** Audit annotation flags.

**Sai lầm 13 — Trộn `javax.servlet` và `jakarta.servlet`.** Có thể compile errors hoặc third-party filter không được đăng ký đúng.

**Sai lầm 14 — Đổi multi-chain thành một chain quá rộng.** OAuth/Basic/form errors, session policy và endpoint matchers không còn như cũ.

**Sai lầm 15 — Nhầm 401/403/302.** HTTP Basic/Bearer/chưa đăng nhập có entry point khác form login; status mới không nhất thiết nghĩa role mất.

**Sai lầm 16 — Tin test `@WithMockUser` là test login.** Annotation bypass credential verification, cần test formLogin và provider thật.

**Sai lầm 17 — Bảo vệ chỉ URL, bỏ service.** Một service có thể gọi qua nhiều entry points; giữ method/domain authorization.

**Sai lầm 18 — Chọn PathPattern mà không test reverse proxy servletPath.** Context root, path prefix, encoded path có thể tạo bypass/mismatch.

**Sai lầm 19 — Tắt StrictHttpFirewall khi matcher cũ không nhận path.** Có thể mở path traversal/malformed URL; sửa matcher/routing đúng.

**Sai lầm 20 — Không kiểm tra endpoint do security filters tạo.** Form login/logout/OAuth callback có thể nằm ngoài `securityMatcher` và biến mất.

**Sai lầm 21 — Thêm nhiều `SecurityFilterChain` không có thứ tự.** Kết quả không còn giống legacy adapter với order cũ.

**Sai lầm 22 — Coi dẹp deprecation là đã xong nâng cấp Boot.** Java 17, Jakarta, Spring Framework 6, dependencies và serializer phải tương thích.

**Sai lầm 23 — Chỉ thử GET.** POST/CSRF, login/logout, OAuth callback và ERROR dispatch thường lộ lỗi khi migration.

**Sai lầm 24 — Sao chép cấu hình từ blog khác version.** DSL import/type khác nhau; luôn tra reference theo major/minor đang chạy.

**Sai lầm 25 — Chỉ test trong MockMvc không có security filters.** Nếu `@AutoConfigureMockMvc(addFilters=false)` hoặc stand-alone setup không áp filter chain, test authorization có thể xanh giả.

## 19. Kế hoạch migration an toàn theo từng giai đoạn

1. **Inventory:** chốt Java, Boot/Security versions, liệt kê legacy adapters, method-security annotations, providers, servlet filters và proxy routes.
2. **Snapshot hành vi:** lập ma trận URL/method/role, status, CSRF, login/logout, cookies/session, provider responses và headers.
3. **Chuẩn bị phiên bản 5.8 nếu nâng từ 5.x:** dọn deprecated API khi có thể, bật test coverage trước khi nâng major.
4. **Đổi entrypoints cấu hình:** tách adapter thành `SecurityFilterChain`, xác định `WebSecurityCustomizer` thực sự cần, xuất `UserDetailsService`/`PasswordEncoder`/manager đúng.
5. **Bảo toàn authorization:** giữ thứ tự matchers, role/authority, security matcher scope, fallback chain và method security flags.
6. **Đổi Servlet/Jakarta:** chuyển imports, dependency coordinates, custom filters, third-party integrations.
7. **Đảm bảo authentication:** kiểm tra form/Basic/OIDC/JWT, CSRF, session rotation, context persistence, authentication manager/provider wiring.
8. **Test hành vi end-to-end:** chạy HTTP positive + negative matrix với Spring Security test/MockMvc và browser/proxy khi phù hợp.
9. **Chuẩn bị 7.x:** chuyển hoàn toàn sang Lambda DSL, thử `PathPatternRequestMatcher` trong 6.5 và sửa custom DSL `apply` → `with`.
10. **Triển khai có kiểm soát:** canary rollout, quan sát login 401/403/302, auth failures, CSRF, request chain metrics, rollback khi có policy regressions.

### Một số điểm cần chủ động so sánh giữa trước và sau

| Hành vi | Trước migration | Sau migration phải xác nhận |
| --- | --- | --- |
| Anonymous vào `/login` | Allowed | Allowed |
| Anonymous vào private API | Denied/redirect | Denied/redirect tương ứng |
| USER vào ADMIN | 403 | 403 |
| ADMIN vào ADMIN | Allowed | Allowed |
| Static assets | Ignored hoặc permitAll | Xác định rõ muốn giữ ignoring hay nâng lên permitAll |
| Form login | POST/login path, remember-me, session | Cùng đường hoặc chuyển có chủ đích |
| Logout/CSRF | Method + token policy | Không yếu đi |
| OAuth redirect callbacks | Đúng endpoints/state | Không bị chặn bởi securityMatcher |
| AuthenticationProvider | JDBC/LDAP/custom flow | Đúng provider + encoder, không double register |
| Method @PreAuthorize/@Secured | On/off theo config | Giữ đúng flags và ownership |
| Multiple chains | Theo thứ tự cũ | Không có fallback gap |
| Exception handling | 401/403/redirect handler | Không đổi semantics bất ngờ |
| Response headers | Được/không được áp dụng | Không mất HSTS/CSP security headers |
| Error dispatch | `/error` và FORWARD | Không bị secondary unauthorized error |
| Proxy/servlet path | URL public vs internal | Request matcher vẫn bảo vệ đúng |

## 20. Checklist cuối khi đọc bất kỳ bài hướng dẫn Spring Security cũ

- [ ] Đã đọc đúng **version** tài liệu? Biết 5.7 deprecated, 6.0 removed, 6.5 preparing 7?
- [ ] Biết class `WebSecurityConfigurerAdapter` có những `configure` overrides nào?
- [ ] Đã tách danh sách `web.ignoring` khỏi `permitAll`?
- [ ] Đã chụp thứ tự rule `antMatchers/mvcMatchers/anyRequest` và quyền tương ứng?
- [ ] Khi dùng `SecurityFilterChain` đã kiểm tra `http.build()` và bean thực được Boot chọn?
- [ ] Biết `securityMatcher` chọn chain, `requestMatchers` chọn rule bên trong?
- [ ] Có fallback chain cho đường không match chain chuyên biệt?
- [ ] Chưa làm mất login/logout/OAuth2 callback nằm ngoài chain scope?
- [ ] Đã map `AuthenticationManagerBuilder` sang UserDetailsService/PasswordEncoder/provider đúng?
- [ ] Không dùng `{noop}` và không tự bỏ CSRF vì lỗi migration?
- [ ] Đã chuyển `@EnableGlobalMethodSecurity` sang `@EnableMethodSecurity` và kiểm tra defaults?
- [ ] Đã đổi `javax.servlet` sang `jakarta.servlet` theo Boot 3/Framework 6?
- [ ] Đã chuẩn bị Lambda DSL và PathPattern rules cho Security 7?
- [ ] Đã test route with context path, servlet path, odd encodings, role, CSRF và ERROR dispatch?
- [ ] Đã test login thật qua filter/provider, không chỉ `@WithMockUser`?
- [ ] Đã kiểm tra static security headers, session cookies, CSRF và active filter chain bằng integration tests?
- [ ] Không có endpoint mới public do bỏ fallback hay matchers quá rộng?
- [ ] Các deprecations/custom filters không còn làm thay đổi behavior khi nâng major?

### Tài liệu tham khảo chính thức

- Spring Security 5.7 API — `WebSecurityConfigurerAdapter` deprecated: https://docs.spring.io/spring-security/site/docs/5.7.0/api/org/springframework/security/config/annotation/web/configuration/WebSecurityConfigurerAdapter.html
- Spring Security 6.5 — Java Configuration, multiple `SecurityFilterChain`: https://docs.spring.io/spring-security/reference/6.5/servlet/configuration/java.html
- Spring Security 6.5 — Authorization for Servlet HTTP Requests: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html
- Spring Security 6.5 — Method Security / migration flags: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html
- Spring Security 6.5 — DaoAuthenticationProvider: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html
- Spring Security 6.5 — Preparation for 7, Configuration Migrations/Lambda DSL: https://docs.spring.io/spring-security/reference/6.5/migration-7/configuration.html
- Spring Security 6.5 — Preparation for 7, Web Migrations/PathPattern: https://docs.spring.io/spring-security/reference/6.5/migration-7/web.html
- Spring Security 6.5 API — `PathPatternRequestMatcher`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/servlet/util/matcher/PathPatternRequestMatcher.html
- Spring Boot 3 Migration Guide (maintained by spring-projects): https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.0-Migration-Guide
- Spring Security 6.5 — Spring Security Test, MockMvc: https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/index.html

**Kết luận:** đọc cấu hình cũ không chỉ là nhận diện class đã bị deprecated. Phải dựng lại **các chuỗi filter, phạm vi matchers, nguồn xác thực, method authorization, endpoint do filter sinh và các default security controls**. Khi chuyển sang `SecurityFilterChain`/Lambda DSL, hãy chứng minh bằng test rằng các quyền và đường xử lý quan trọng không yếu đi, đồng thời chủ động xử lý khác biệt về PathPattern, Jakarta và phiên bản Spring Security 7.
