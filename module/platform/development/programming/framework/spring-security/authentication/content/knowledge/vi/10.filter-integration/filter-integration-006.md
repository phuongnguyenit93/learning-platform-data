# requiresAuthenticationRequestMatcher chọn đúng yêu cầu cần xác thực

## Mục tiêu và câu trả lời cốt lõi

Trong Spring Security Servlet, một authentication filter không nên thử đăng nhập ở mọi request. Ví dụ, form login chỉ cần nhận **HTTP POST đến endpoint xử lý đăng nhập**, không phải mọi GET trang login, request tải CSS, gọi API hay request logout. `AbstractAuthenticationProcessingFilter` giải quyết việc này bằng một `RequestMatcher` được cấu hình qua phương thức **`setRequiresAuthenticationRequestMatcher(...)`**.

Khi một request đi qua filter:

- Nếu `requestMatcher.matches(request) == false`, filter **không gọi `attemptAuthentication(...)`** và chuyển tiếp request đến phần còn lại của filter chain.
- Nếu trả `true`, filter bắt đầu luồng authentication: gọi `attemptAuthentication(...)` để tạo/kiểm chứng một `Authentication`; sau đó xử lý thành công, thất bại hoặc một bước xác thực chưa hoàn tất.
- Matcher **không kiểm tra password**, **không phân quyền truy cập**, **không tự chọn SecurityFilterChain** và **không thay CSRF protection**.
- Chọn đúng matcher nghĩa là giới hạn filter vào **đúng HTTP method, URL và điều kiện kỹ thuật** mà cơ chế xác thực đó chủ động hỗ trợ; không được biến logic “có đường dẫn giống login” thành “được tin cậy”.

Bài thuộc nhóm **Tích hợp bộ lọc** của module *Spring Security - authentication*, tập trung vào Servlet `AbstractAuthenticationProcessingFilter` và `UsernamePasswordAuthenticationFilter` ở Spring Security 6.x. Ví dụ dùng **Java 17+, Spring Boot 3.x** và `PathPatternRequestMatcher` (có trong nhánh Spring Security 6.5). Phần WebFlux dùng API `ServerWebExchangeMatcher` khác, không áp dụng nguyên đoạn Servlet.

Sau bài, bạn cần làm được:

1. Phân biệt filter **được gọi** với filter **quyết định có thử xác thực**.
2. Chỉ rõ `requiresAuthentication(...)` và `requiresAuthenticationRequestMatcher` nằm ở đâu trong `AbstractAuthenticationProcessingFilter`.
3. Khớp chính xác `POST /auth/login` nhưng loại `GET /auth/login`, `POST /auth/login/extra` và đường dẫn API khác.
4. Phân biệt matcher xử lý authentication với `http.securityMatcher(...)` và `authorizeHttpRequests(...requestMatchers(...))`.
5. Cấu hình form login chuẩn bằng `loginProcessingUrl(...)`, và biết khi nào mới cần trực tiếp gọi setter trên custom filter.
6. Kiểm thử cả **request khớp** lẫn **request không khớp**, kể cả context path.
7. Nhận diện sai lầm về method, CSRF, nhiều filter chains, servlet path và filter đăng ký hai lần.

## 1. Các tầng lọc: ba quyết định khác nhau

Một HTTP request đến Spring Security thường đi qua nhiều lớp lựa chọn:

~~~text
HTTP request
    |
    v
DelegatingFilterProxy -> FilterChainProxy
    |
    +-- (A) SecurityFilterChain nào khớp?
    |       http.securityMatcher(...)
    |
    v
Các filter trong chain được chọn
    |
    +-- (B) Authentication filter này có cần xử lý?
    |       requiresAuthenticationRequestMatcher.matches(request)
    |            false -> chain.doFilter(...)
    |            true  -> attemptAuthentication(...)
    |
    v
Authentication/Authorization của request
    |
    +-- (C) Request được phép truy cập tài nguyên không?
            authorizeHttpRequests(...requestMatchers(...))
~~~

Ba tầng tuy có thể cùng dùng `RequestMatcher` nhưng mục đích khác nhau:

| Tầng | Cấu hình/API | Trả lời câu hỏi | Khi không khớp |
| --- | --- | --- | --- |
| Chọn **SecurityFilterChain** | `http.securityMatcher(...)` | Chain này có áp dụng cho request không? | `FilterChainProxy` xét chain kế tiếp |
| Chọn **authentication attempt** trong một filter | `setRequiresAuthenticationRequestMatcher(RequestMatcher)` | Filter này có thử xác thực request không? | Filter bỏ qua attempt và chuyển tiếp |
| Chọn **authorization rule** | `authorizeHttpRequests(a -> a.requestMatchers(...))` | Khi xử lý tài nguyên, rule nào cấp/từ chối quyền? | Xét rule tiếp theo trong chain đã chọn |

Ví dụ: `POST /auth/login` có thể được nhận bởi form-login filter, nhưng `GET /auth/login` đi qua filter ấy mà **không kích hoạt đăng nhập**. Sau đó GET vẫn có thể bị `AuthorizationFilter` yêu cầu authenticated, redirect trang login, trả 404 hoặc được controller xử lý, tùy các rules và endpoint thực tế. **Không khớp authentication matcher không đồng nghĩa request tự được phép truy cập.**

### 1.1. Filter được gọi khác filter thử xác thực

`AbstractAuthenticationProcessingFilter#doFilter(...)` chạy khi request đã vào filter chain và filter instance này nằm trong chain. Bên trong nó gọi `requiresAuthentication(request,response)`. Phương thức này sử dụng `RequestMatcher` được cài bởi `setRequiresAuthenticationRequestMatcher(...)`.

Lược đồ trách nhiệm:

~~~text
AbstractAuthenticationProcessingFilter.doFilter(...)
    |
    +-- requiresAuthentication(request, response)?
    |        |
    |        +-- false -> filterChain.doFilter(request,response)
    |        |
    |        +-- true  -> attemptAuthentication(request,response)
    |                     |
    |                     +-- Authentication result (thành công)
    |                     |      -> session strategy + success flow
    |                     |
    |                     +-- AuthenticationException
    |                     |      -> failure flow
    |                     |
    |                     +-- null (cơ chế còn tiếp tục)
    |                            -> return, chờ bước tiếp theo
~~~

Đây là **sơ đồ logic**, không phải source code copy nguyên từ Spring Security. Một số filter có cơ chế conversion/continuation riêng, nhưng hợp đồng của `AbstractAuthenticationProcessingFilter` nêu rõ filter chỉ bắt đầu authentication khi matcher khớp. Phần xử lý thành công/thất bại phải dựa vào `AuthenticationManager`, `SecurityContextRepository`, handlers và session strategy đã cấu hình.

### 1.2. Tại sao phải khớp đúng request?

Matcher quá **rộng** có thể gây:

- Filter cố đọc username/password từ endpoint không phải login.
- Một `GET /login` (để hiển thị form) bị xử lý nhầm là nỗ lực đăng nhập.
- `POST /api/orders` hay `POST /logout` bị filter chiếm mất request.
- Dữ liệu request được parse và log không đúng ngữ cảnh, tăng bề mặt tấn công và lỗi nghiệp vụ.
- Hai authentication filters cạnh tranh xử lý một URL; filter chạy trước có thể “nuốt” request.

Matcher quá **hẹp** có thể gây:

- Form submit đúng nhưng filter không bao giờ gọi `attemptAuthentication`.
- Client nhận `404`, `405`, redirect hoặc `403` từ một tầng khác mà dev hiểu nhầm là sai password.
- Context path hoặc servlet path khiến đường dẫn thực tế không khớp.
- HTTP method bị giới hạn sai (đăng ký form POST nhưng matcher chỉ nhận GET).

Chọn đúng matcher vừa giúp **tách trách nhiệm** vừa giúp behavior dễ kiểm thử, nhưng phải kết hợp với authentication policy thật.

## 2. API của AbstractAuthenticationProcessingFilter

`org.springframework.security.web.authentication.AbstractAuthenticationProcessingFilter` là lớp cơ sở cho nhiều filter xử lý yêu cầu đăng nhập qua HTTP, tiêu biểu là `UsernamePasswordAuthenticationFilter`.

Những method đáng chú ý:

~~~java
// Chữ ký minh họa, rút gọn theo Spring Security 6.x.
// Đây không phải class cần tự tạo.

public final void setRequiresAuthenticationRequestMatcher(
    RequestMatcher requestMatcher
);

protected boolean requiresAuthentication(
    HttpServletRequest request,
    HttpServletResponse response
);

public abstract Authentication attemptAuthentication(
    HttpServletRequest request,
    HttpServletResponse response
) throws AuthenticationException, IOException, ServletException;

public void setFilterProcessesUrl(String filterProcessesUrl);
~~~

`RequestMatcher` là interface có method `boolean matches(HttpServletRequest request)`. Nó xác định **có cần thử xác thực ở request hiện tại hay không**, không có nhiệm vụ tạo token hoặc xác minh bí mật.

### 2.1. Setter tác động đến điều gì?

Khi bạn gọi:

~~~java
filter.setRequiresAuthenticationRequestMatcher(loginMatcher);
~~~

filter sẽ dùng `loginMatcher` cho quyết định `requiresAuthentication` ở các request đến **filter instance đó**. Nó **không** tự đăng ký filter vào `SecurityFilterChain`, không ảnh hưởng filter instance khác và không đồng bộ với authorization rules nếu bạn chưa cấu hình chúng.

Nếu custom filter kế thừa `AbstractAuthenticationProcessingFilter`, bạn có thể truyền matcher ngay trong constructor:

~~~java
public CustomLoginFilter(
    RequestMatcher loginMatcher,
    AuthenticationManager manager
) {
    super(loginMatcher, manager);
}
~~~

Đây là **fragment constructor** của lớp tùy chỉnh; custom filter còn phải implement `attemptAuthentication(...)` và wiring chính xác. Truyền matcher lúc khởi tạo giúp tránh quên setter. Một số phiên bản/implementation có constructor overload khác; kiểm tra Javadoc đúng phiên bản.

### 2.2. setFilterProcessesUrl so với setRequiresAuthenticationRequestMatcher

`setFilterProcessesUrl("/auth/login")` là cấu hình convenience cho URL xử lý của lớp filter. `setRequiresAuthenticationRequestMatcher(...)` cho phép dùng một `RequestMatcher` tùy biến, gồm HTTP method, pattern và các điều kiện kết hợp.

**Không gọi cả hai setter rồi giả định điều kiện được “AND”**: các setter có thể thay đổi matcher hiện tại, nên cấu hình cuối cùng có thể ghi đè điều kiện bạn đặt trước. Chọn một nguồn cấu hình rõ ràng, test đúng filter instance và URL/method thực tế.

### 2.3. UsernamePasswordAuthenticationFilter mặc định

`UsernamePasswordAuthenticationFilter` xử lý form login với parameters `username` và `password`. Khi cấu hình form login chuẩn, endpoint xử lý mặc định là **`POST /login`**; `GET /login` thường dùng để hiển thị trang đăng nhập.

Khi form login dùng `http.formLogin(...)`, nên thay đổi URL xử lý qua DSL:

~~~java
http.formLogin(form -> form
    .loginProcessingUrl("/auth/login")
    .permitAll()
);
~~~

Đây là **fragment bên trong cấu hình `HttpSecurity`**, không phải file Java độc lập. Để login thực sự hoạt động, client phải gửi form đúng **HTTP method**, **URL**, **param names** và **CSRF token** khi CSRF đang bật. Đừng tự tạo thêm một `UsernamePasswordAuthenticationFilter` nếu DSL đã tạo filter tương ứng.

## 3. Chọn đường dẫn và HTTP method cùng lúc

Một yêu cầu đăng nhập kiểu form có thể được nhận diện bằng:

~~~text
method = POST
path   = /auth/login
~~~

Chỉ khớp path mà **không kiểm tra method** sẽ khiến GET, PUT hoặc DELETE ở cùng URL có thể kích hoạt authentication attempt. Chỉ kiểm tra method mà không kiểm tra path còn nguy hiểm hơn: mọi POST của ứng dụng có thể bị chọn.

Từ Spring Security 6.5, có thể dùng `PathPatternRequestMatcher`:

~~~java
import org.springframework.http.HttpMethod;
import org.springframework.security.web.servlet.util.matcher
    .PathPatternRequestMatcher;
import org.springframework.security.web.util.matcher.RequestMatcher;

RequestMatcher loginMatcher =
    PathPatternRequestMatcher.withDefaults()
        .matcher(HttpMethod.POST, "/auth/login");
~~~

**Chú ý imports:** Đoạn trên tách tên package trên hai dòng để dễ đọc, nhưng **Java không cho phép xuống dòng sau tên package khi import class chưa đầy đủ**. Trong file runnable, viết đúng import trên một dòng:

~~~java
import org.springframework.security.web.servlet.util.matcher.PathPatternRequestMatcher;
~~~

`PathPatternRequestMatcher.Builder.matcher(HttpMethod, String)` kiểm tra cả phương thức và đường dẫn. Path được viết **relative to context path**. Với app chạy ở root, `/auth/login` là path tương ứng; nếu deploy dưới `/shop`, URL client là `/shop/auth/login` nhưng matcher vẫn thường viết `/auth/login`. Với servlet có prefix không phải default, cần cân nhắc `basePath(...)` theo mapping.

Để giảm nhầm lẫn, file Java trong ví dụ runnable bên dưới đặt import trên một dòng chuẩn. Dấu slash cuối hoặc match pattern có thể ảnh hưởng kết quả; dùng **exact path**, tránh `/**` cho login trừ khi có yêu cầu thực sự.

### 3.1. Bảng yêu cầu được chọn và bị bỏ qua

Với matcher `POST /auth/login`:

| Request | Matches? | Vì sao |
| --- | --- | --- |
| `POST /auth/login` | `true` | Đúng method và exact path |
| `GET /auth/login` | `false` | Sai method |
| `PUT /auth/login` | `false` | Sai method |
| `OPTIONS /auth/login` | `false` | CORS preflight không phải đăng nhập |
| `POST /auth/login/extra` | `false` | Thừa path segment |
| `POST /auth/login2` | `false` | Khác exact path |
| `POST /api/orders` | `false` | Request nghiệp vụ khác |
| `POST /auth/login?next=/me` | `true` | Query string không đổi path được match |
| App có context path `/shop`, client gửi `POST /shop/auth/login` | `true` khi matcher relative to context path được cấu hình đúng | `/shop` là context path, không phải login path |

Các giá trị giả định theo default path parser và servlet mapping tương thích; nếu ứng dụng có reverse proxy rewrite, nhiều servlet hoặc path parser tùy chỉnh, hãy test bằng môi trường triển khai thực.

### 3.2. Không coi header là bằng chứng đăng nhập

Một số authentication filters chỉ xử lý request có header riêng, chẳng hạn `X-Requested-With` hoặc `Content-Type: application/json`. Header có thể hữu ích để **chọn parser**, nhưng **không chứng minh** client đáng tin. Attacker có thể đặt nhiều header theo ý muốn.

Nếu filter dùng JSON credentials, matcher nên giới hạn **method và URL**, còn parser phải kiểm tra content type, kích thước body và format hợp lệ; authentication provider mới xác minh credentials. Không dùng `X-Internal: true` hoặc một header tự khai báo như quyền bypass password.

### 3.3. Path, context path và servlet path

Giả sử deployment:

~~~text
https://example.com/shop/api/auth/login
                     ^^^^^
                     context path = /shop
                           ^^^^
                           servlet/base path = /api
                                ^^^^^^^^^^^
                                endpoint under servlet = /auth/login
~~~

Khi dùng `PathPatternRequestMatcher.withDefaults()`, pattern relative to **context path**, và nếu muốn tạo các paths chung cho servlet prefix, builder có `basePath("/api")`. Trong ví dụ có DispatcherServlet map dưới `/api/*`:

~~~java
RequestMatcher loginMatcher =
    PathPatternRequestMatcher.withDefaults()
        .basePath("/api")
        .matcher(HttpMethod.POST, "/auth/login");
~~~

Fragment này chọn đường dẫn tương ứng `/api/auth/login` trong ứng dụng, sau khi bỏ context path. Nếu custom servlet mapping, forwarded headers hoặc proxy rewrite khác, phải kiểm tra request path mà Spring Security thực sự thấy. **Không** lấy chuỗi external URL trong browser rồi nối nguyên vào matcher nếu phần context path bị lặp.

### 3.4. Matcher và query parameters

Đường dẫn `/auth/login?continue=/home` vẫn có path `/auth/login`. Matcher theo path/method không tự kiểm soát tham số `continue`. Nếu login success handler dùng parameter redirect, phải validate redirect destinations để tránh open redirect. Không đưa username/password vào query string; chúng có thể xuất hiện trong browser history, logs hoặc referrer.

## 4. Chỉ matcher đúng không đủ để login

Một authentication filter còn cần:

1. Được đặt **đúng trong SecurityFilterChain**, không đăng ký sai thứ tự.
2. Có `AuthenticationManager` thực hiện xác minh.
3. Có cách parse credentials đúng với content type của request.
4. Có success/failure handlers và chính sách SecurityContext phù hợp.
5. Có session strategy nếu dùng session-based login.
6. Có bảo vệ CSRF, TLS, rate limiting và audit theo mô hình đe dọa.

Ví dụ: matcher chấp nhận `POST /auth/login`, nhưng client gửi body JSON trong khi `UsernamePasswordAuthenticationFilter` chuẩn đọc **form parameters** `username` và `password`. Không thể mong JSON tự được parse. Muốn JSON login, cần converter/filter được thiết kế rõ ràng; đừng sửa matcher rồi cho rằng đã giải quyết định dạng body.

### 4.1. Matcher không thay PasswordEncoder

Request khớp chỉ nói “đây là một yêu cầu login candidate”. Provider vẫn phải làm:

~~~text
username/password từ filter
        |
        v
UsernamePasswordAuthenticationToken chưa xác thực
        |
        v
AuthenticationManager -> DaoAuthenticationProvider
        |
        +--> UserDetailsService đọc stored hash/status
        +--> PasswordEncoder.matches(rawPassword, storedHash)
        +--> kiểm tra account flags và chính sách
        |
        v
Authentication thành công hoặc AuthenticationException
~~~

Dù matcher đúng, user vẫn có thể nhận authentication failure vì password sai, account disabled, locked, expired hoặc provider không hỗ trợ token. Matcher **không tự đặt `Authentication.isAuthenticated()==true`**.

### 4.2. Matcher không thay authorization

Một endpoint có rule:

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/public").permitAll()
    .requestMatchers("/admin").hasRole("ADMIN")
    .anyRequest().authenticated()
)
~~~

Rule này quyết định **quyền vào tài nguyên**. Nó không thay đổi lúc nào `UsernamePasswordAuthenticationFilter` gọi `attemptAuthentication`. Ngược lại, setter của authentication filter không làm `/admin` thành public.

## 5. Ba matcher thường bị nhầm trong HttpSecurity

### 5.1. http.securityMatcher — chọn SecurityFilterChain

~~~java
@Bean
@Order(1)
SecurityFilterChain api(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(auth ->
            auth.anyRequest().authenticated()
        )
        .httpBasic(Customizer.withDefaults())
        .build();
}
~~~

Đây là **fragment** của một class cấu hình; import `@Bean`, `@Order`, `HttpSecurity`, `SecurityFilterChain` và `Customizer`. `FilterChainProxy` chỉ đưa request khớp `/api/**` vào chain này; request khác được xét chain tiếp theo. Nếu **không có chain nào khớp**, request có thể **không được Spring Security bảo vệ**. Vì vậy nên có catch-all security chain với rule bảo vệ mặc định phù hợp.

### 5.2. authorizeHttpRequests.requestMatchers — chọn rule quyền

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/public").permitAll()
    .requestMatchers("/admin/**").hasRole("ADMIN")
    .anyRequest().authenticated()
);
~~~

Các matcher này áp dụng **bên trong chain đã chọn**, không quyết định có gọi filter xử lý form login hay không. `permitAll()` không có nghĩa “bypass toàn bộ filter”: authentication filter vẫn có thể xử lý request khớp endpoint trong chain ấy.

### 5.3. requiresAuthenticationRequestMatcher — chọn attempt trong filter

~~~java
UsernamePasswordAuthenticationFilter loginFilter =
    new UsernamePasswordAuthenticationFilter();

loginFilter.setRequiresAuthenticationRequestMatcher(
    PathPatternRequestMatcher.withDefaults()
        .matcher(HttpMethod.POST, "/auth/login")
);
~~~

Đây là **fragment cho custom wiring**, không phải cấu hình hoàn chỉnh. Phải đặt authentication manager, session strategy, context repository/handlers phù hợp rồi đăng ký filter đúng một lần trong security chain. Với **form login chuẩn**, đơn giản hơn là `formLogin(f -> f.loginProcessingUrl("/auth/login"))`.

### 5.4. Ví dụ lỗi do hai chain không giao nhau

Một cấu hình chỉ có:

~~~java
http
    .securityMatcher("/api/**")
    .formLogin(form ->
        form.loginProcessingUrl("/auth/login")
    );
~~~

Chain trên **không được chọn** cho `POST /auth/login`, nên login filter **không có cơ hội** xử lý request ấy. Lỗi có thể xuất hiện dưới dạng 404/redirect/fallback chain behavior. Không sửa bằng cách thay PasswordEncoder vì credentials thậm chí chưa vào provider.

Có hai cách sửa tùy thiết kế:

- Chuyển endpoint login vào prefix của chain, ví dụ `/api/auth/login`, rồi đảm bảo form/action và matcher thống nhất.
- Hoặc để chain chứa login filter cũng khớp `/auth/login` qua `securityMatcher(RequestMatcher)` tổng hợp, và có catch-all chain bảo vệ phần còn lại.

Nếu có nhiều chains, ghi rõ `@Order`. Chain ưu tiên cao hơn được chọn trước; một request **không chạy tuần tự qua tất cả các SecurityFilterChain**. Điều đó khác với việc một composite `OrRequestMatcher` kiểm tra nhiều điều kiện bên trong cùng filter.

## 6. Ví dụ Spring Boot 3.x / Java 17+ chạy được

Ví dụ này sử dụng **form login có sẵn** và cấu hình URL xử lý là `/auth/login`. Mục đích chứng minh cách chọn yêu cầu đăng nhập đúng method/path, tránh tự cài đặt authentication filter từ đầu khi không cần.

### 6.1. Tạo project

Tạo project với Spring Initializr:

- Java 17 hoặc 21, Spring Boot **3.x**, Maven.
- Group `com.example`, artifact `login-request-matcher`.
- Package `com.example.demo`.
- Dependencies: **Spring Web** và **Spring Security**.

Dự án cần `spring-boot-starter-web` và `spring-boot-starter-security` do Initializr tạo. Không cần database: dùng user test trong bộ nhớ. Cây file chính:

~~~text
src/main/java/com/example/demo/LoginMatcherApplication.java
src/test/java/com/example/demo/LoginMatcherGateTest.java
pom.xml
~~~

### 6.2. Source Spring Boot đầy đủ

Tạo **`src/main/java/com/example/demo/LoginMatcherApplication.java`**:

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class LoginMatcherApplication {

    public static void main(String[] args) {
        SpringApplication.run(LoginMatcherApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("demo-pass"))
            .roles("USER")
            .build();
        return new InMemoryUserDetailsManager(alice);
    }

    @Bean
    SecurityFilterChain security(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .requestMatchers("/admin").hasRole("ADMIN")
                .anyRequest().authenticated()
            )
            .formLogin(form -> form
                .loginProcessingUrl("/auth/login")
                .permitAll()
            )
            .build();
    }

    @RestController
    static class DemoController {
        @GetMapping("/public")
        String open() {
            return "public";
        }

        @GetMapping("/me")
        String me(Authentication auth) {
            return "Hello " + auth.getName();
        }

        @GetMapping("/admin")
        String admin() {
            return "admin";
        }
    }
}
~~~

Giải thích:

- `formLogin(...loginProcessingUrl("/auth/login"))` cấu hình endpoint **xử lý form credentials**. Nó khác **trang hiển thị form**, mặc định thường là `GET /login` được Spring Security sinh khi không khai báo custom `loginPage`.
- Filter xử lý login chuẩn chỉ nên thử authentication trên form POST đến processing URL đã cấu hình, không coi mọi request là login.
- `PasswordEncoder` băm mật khẩu demo; provider kiểm tra mật khẩu thật.
- `/public` có thể được gọi anonymous; `/me` cần authenticated; `/admin` cần `ROLE_ADMIN`, nhưng Alice chỉ có `ROLE_USER`.
- Không cần định nghĩa `@PostMapping("/auth/login")` trong MVC controller: endpoint xử lý login được **filter** cung cấp khi chain khớp. Viết một controller trùng endpoint thường gây hiểu nhầm việc ai thực sự nhận request.
- Ví dụ giữ CSRF mặc định; không tắt CSRF chỉ để thử POST login bằng curl.

**Không dùng mật khẩu demo hardcode, HTTP không TLS hoặc in-memory user trong production.** Mục đích là minh họa filter routing.

### 6.3. Chạy và thử bằng browser

Trong thư mục project:

~~~bash
./mvnw spring-boot:run
~~~

Windows PowerShell:

~~~powershell
.\mvnw.cmd spring-boot:run
~~~

Cách thử:

1. Mở `http://localhost:8080/public` → body `public`.
2. Mở `http://localhost:8080/me` khi chưa login → thường redirect đến `/login`.
3. Trang login mặc định tạo HTML form có action tương thích `/auth/login`; đăng nhập **alice / demo-pass**.
4. Truy cập lại `/me` → body **`Hello alice`**.
5. Truy cập `/admin` khi đã là Alice → **HTTP 403**, vì thiếu `ROLE_ADMIN`.
6. Logout qua cơ chế có sẵn rồi vào `/me` → cần login lại.

Nếu bạn cấu hình trang login tùy chỉnh, form phải submit **POST `/auth/login`**, dùng đúng tham số `username`/`password`, có CSRF token hợp lệ và browser/session cookie. Nếu form POST nhầm `/login` sau khi đã đổi processing URL, login filter không nhận yêu cầu đó.

### 6.4. Không được suy response status từ matcher một cách máy móc

| Request | Login filter attempt? | Response còn phụ thuộc |
| --- | --- | --- |
| `GET /login` | Không | Generated login page hoặc custom page |
| `POST /auth/login`, valid CSRF/credentials | Có | Success handler thường redirect |
| `POST /auth/login`, sai password, valid CSRF | Có | Failure handler thường redirect `/login?error` |
| `POST /auth/login`, thiếu CSRF | Có thể bị chặn **trước khi đến filter** | `CsrfFilter` có thể trả 403 |
| `GET /auth/login` | Không | Authorization, redirect hoặc 404; không phải chắc chắn 405 |
| `POST /api/orders` | Không | Controller và các filter/rules khác |
| `OPTIONS /auth/login` | Không phải POST login | CORS/preflight rules |

Vì CSRF filter thường chạy trước authentication filter, `POST /auth/login` thiếu CSRF có thể bị từ chối mà không có lần gọi `attemptAuthentication` nào. **Matcher có thể khớp về mặt path/method nhưng không đồng nghĩa request sẽ tới được bước attempt**. Muốn test đúng filter, dùng test đơn vị bên dưới; muốn test HTTP end-to-end, cung cấp CSRF token/cookie hợp lệ.

## 7. Unit test trực tiếp điều kiện chọn request

App chạy được qua browser, nhưng để **kiểm chứng chính xác matcher và filter gate**, dùng `AbstractAuthenticationProcessingFilter` tối giản trong JUnit. Filter trong test đếm số lần gọi `attemptAuthentication` rồi trả `null`, nhằm tránh đăng nhập giả hoặc thử kiểm chứng password. Theo contract của filter, kết quả `null` biểu thị quá trình authentication chưa hoàn tất nên filter return, không tiếp tục chain ở lần thử đó.

### 7.1. Dependency test

Thêm `spring-boot-starter-test` vào `pom.xml` nếu project chưa có:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Spring Test cung cấp `MockHttpServletRequest`/`MockHttpServletResponse`. Không cần thêm `spring-security-test` cho unit test dưới đây vì nó không dùng các helper của MockMvc security integration.

### 7.2. File JUnit 5 hoàn chỉnh

Tạo **`src/test/java/com/example/demo/LoginMatcherGateTest.java`**:

~~~java
package com.example.demo;

import java.util.concurrent.atomic.AtomicBoolean;

import jakarta.servlet.FilterChain;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.junit.jupiter.api.Test;
import org.springframework.http.HttpMethod;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.security.core.Authentication;
import org.springframework.security.web.authentication.AbstractAuthenticationProcessingFilter;
import org.springframework.security.web.servlet.util.matcher.PathPatternRequestMatcher;
import org.springframework.security.web.util.matcher.RequestMatcher;

import static org.junit.jupiter.api.Assertions.assertEquals;

class LoginMatcherGateTest {

    static final class CountingLoginFilter
            extends AbstractAuthenticationProcessingFilter {

        int attempts = 0;

        CountingLoginFilter(RequestMatcher matcher) {
            super(matcher, authentication -> authentication);
        }

        @Override
        public Authentication attemptAuthentication(
            HttpServletRequest request,
            HttpServletResponse response
        ) {
            attempts++;
            // Null: trong fixture này chỉ đo có được gọi hay không.
            // Không thể dùng cách trả null này để login thực tế.
            return null;
        }
    }

    private void assertSelection(
        String method,
        String uri,
        String contextPath,
        String servletPath,
        boolean expectedAttempt
    ) throws Exception {

        RequestMatcher matcher =
            PathPatternRequestMatcher.withDefaults()
                .matcher(HttpMethod.POST, "/auth/login");

        CountingLoginFilter filter = new CountingLoginFilter(matcher);

        MockHttpServletRequest request =
            new MockHttpServletRequest(method, uri);
        request.setContextPath(contextPath);
        request.setServletPath(servletPath);

        MockHttpServletResponse response =
            new MockHttpServletResponse();
        AtomicBoolean continued = new AtomicBoolean(false);

        FilterChain chain = (req, res) -> continued.set(true);
        filter.doFilter(request, response, chain);

        assertEquals(
            expectedAttempt ? 1 : 0,
            filter.attempts
        );
        assertEquals(
            !expectedAttempt,
            continued.get()
        );
    }

    @Test
    void postExactPathAttemptsAuthentication() throws Exception {
        assertSelection(
            "POST", "/auth/login", "", "/auth/login", true
        );
    }

    @Test
    void wrongMethodsAndPathsDoNotAttempt() throws Exception {
        assertSelection(
            "GET", "/auth/login", "", "/auth/login", false
        );
        assertSelection(
            "PUT", "/auth/login", "", "/auth/login", false
        );
        assertSelection(
            "OPTIONS", "/auth/login", "", "/auth/login", false
        );
        assertSelection(
            "POST", "/auth/login/extra",
            "", "/auth/login/extra", false
        );
        assertSelection(
            "POST", "/auth/login2", "", "/auth/login2", false
        );
        assertSelection(
            "POST", "/api/orders", "", "/api/orders", false
        );
    }

    @Test
    void contextPathIsNotPartOfMatcherPattern() throws Exception {
        assertSelection(
            "POST", "/shop/auth/login",
            "/shop", "/auth/login", true
        );
    }
}
~~~

**Kiểm thử những gì?**

- Request khớp method/path → `attemptAuthentication` được gọi đúng **một lần**, filter không gọi `chain.doFilter` vì fixture cố tình trả `null`.
- Request không khớp → `attemptAuthentication` **không chạy**, và filter chuyển tiếp qua `chain.doFilter`.
- Với context path `/shop`, request URI có prefix `/shop` nhưng pattern vẫn relative to context path `/auth/login`.

Đoạn `authentication -> authentication` trong constructor là **authentication manager giả**, chỉ để có một object manager hợp lệ cho fixture. Nó **không** xác thực người dùng. Không sao chép `CountingLoginFilter` hoặc manager giả này vào production; trong ứng dụng thật phải dùng provider xác thực credentials thực sự.

### 7.3. Chạy test và output kỳ vọng

~~~bash
./mvnw test
~~~

Windows: `.\mvnw.cmd test`. Khi sử dụng JUnit 5/Surefire phù hợp, ba test sẽ pass; một dòng tóm tắt thường có dạng:

~~~text
Tests run: 3, Failures: 0, Errors: 0, Skipped: 0
~~~

Đầu ra có thể khác theo Maven Surefire version, nhưng điều kiện kiểm chứng quan trọng là **3 test methods pass**. Test này không chạy HTTP login thực tế, không kiểm tra CSRF, SecurityFilterChain selection hoặc password provider. Đó là kiểm thử riêng cho **gating logic**. Test tích hợp vẫn cần để xác nhận filter được đăng ký và form action trỏ đúng endpoint.

## 8. Khi cần một matcher phức hợp

`RequestMatcher` có thể kết hợp nhiều tiêu chí bằng các implementation như `AndRequestMatcher`, `OrRequestMatcher`, `NegatedRequestMatcher`. Nhưng phức tạp hơn không đồng nghĩa an toàn hơn.

### 8.1. Giới hạn method và path

`PathPatternRequestMatcher.withDefaults().matcher(HttpMethod.POST,"/auth/login")` đã kết hợp method + path, nên không cần tự viết:

~~~java
RequestMatcher wrong = request ->
    request.getRequestURI().contains("/login");
~~~

**Sai:** kiểm tra `contains` có thể chọn `/admin/login-history`, `/evil/login123` hoặc đường dẫn không mong đợi; ngoài ra dùng `requestURI` trực tiếp dễ nhầm context path, URI encoding và servlet mapping.

### 8.2. Nhiều endpoint đăng nhập thật sự cần cùng filter

Nếu **cùng một cơ chế auth** xử lý hai URL khác nhau, có thể dùng:

~~~java
RequestMatcher loginEndpoints = new OrRequestMatcher(
    PathPatternRequestMatcher.withDefaults()
        .matcher(HttpMethod.POST, "/auth/login"),
    PathPatternRequestMatcher.withDefaults()
        .matcher(HttpMethod.POST, "/auth/login/legacy")
);

customFilter.setRequiresAuthenticationRequestMatcher(
    loginEndpoints
);
~~~

Đây là **fragment**, cần imports `OrRequestMatcher`, `PathPatternRequestMatcher`, `HttpMethod` và `RequestMatcher` cùng custom filter có parser rõ. Trước khi cho hai endpoints nhận password, xác định chúng có cùng protection, rate limit, response contract và kế hoạch loại bỏ endpoint legacy hay không.

**Không mở rộng matcher đến `/**`** chỉ vì một URL login cũ vẫn còn; điều đó dễ làm filter bắt nhầm request nghiệp vụ.

### 8.3. Chỉ REQUEST dispatch nếu flow yêu cầu

Một custom filter dùng stateful login đôi khi chỉ muốn nhận initial `DispatcherType.REQUEST`, không xử lý `ERROR`/`FORWARD`. Có thể cân nhắc matcher bổ sung dispatcher type và test nó:

~~~java
RequestMatcher loginOnlyOnRequest = new AndRequestMatcher(
    PathPatternRequestMatcher.withDefaults()
        .matcher(HttpMethod.POST, "/auth/login"),
    new DispatcherTypeRequestMatcher(DispatcherType.REQUEST)
);
~~~

Đây là fragment cần imports `jakarta.servlet.DispatcherType`, `AndRequestMatcher`, `DispatcherTypeRequestMatcher` và path matcher. Đừng vô tình loại `ASYNC`/`ERROR` nếu cơ chế của bạn cần xử lý chúng; mặt khác, đừng để một filter login đọc lại credentials vào error dispatch nếu không chủ đích.

## 9. Những lỗi về thứ tự filter và đăng ký

### 9.1. Tự đăng ký filter hai lần

Một custom class vừa được khai báo `@Component` (Spring Boot có thể auto-register thành Servlet filter), vừa thêm qua `http.addFilterBefore(...)`/`addFilterAt(...)` có thể chạy **hai lần** hoặc không chạy dưới security context mong muốn. Với custom auth filter, nên kiểm soát việc tạo instance, vị trí trong `SecurityFilterChain` và tránh đăng ký servlet container ngoài ý muốn.

Nếu sử dụng `FilterRegistrationBean` để vô hiệu đăng ký trực tiếp trong container cho filter được thêm vào Spring Security chain, phải cấu hình đúng instance. Không copy một ví dụ trộn `@Component`/`addFilterBefore` mà không kiểm tra kết quả.

### 9.2. Đặt filter sai vị trí

Authentication filter cần chạy khi `SecurityContextHolder` đã được chuẩn bị và trước authorization đánh giá request. Nếu đặt sau `AuthorizationFilter`, request chưa authenticated có thể bị từ chối trước khi login filter xử lý. Nếu đặt không đúng thứ tự so với `CsrfFilter`, session context filters hay exception translation, có thể bỏ qua bảo vệ cần thiết.

Đặt vị trí bằng các API `addFilterBefore`, `addFilterAfter` hoặc `addFilterAt` một cách **có chủ đích**. `addFilterAt` không nhất thiết “thay thế” instance cũ tại cùng vị trí nếu cả hai cùng được đăng ký; đừng gắn filter thủ công song song với `formLogin` rồi cho rằng chỉ còn một filter.

### 9.3. Một endpoint có hai filters đều match

Nếu custom JSON login filter và form login filter cùng nhận `POST /login`, tùy thứ tự, filter trước có thể parse body, trả lỗi, redirect hoặc return trước khi filter còn lại chạy. Nên tách endpoints rõ ràng (ví dụ `POST /api/auth/login` cho JSON, `POST /login` cho form), hoặc thiết kế converter/handler duy nhất hỗ trợ cả hai format theo contract được kiểm thử.

## 10. CSRF, CORS và HTTP semantics

### 10.1. CSRF không được “tắt” bởi matcher

Một POST form login có thể cần CSRF token ngay cả khi path/method đúng. Spring Security `CsrfFilter` có thể chạy **trước** form login filter. Khi token thiếu/sai, HTTP có thể trả **403** mà `attemptAuthentication` chưa từng chạy.

Vì vậy test matcher “true” và một request HTTP “403” **không mâu thuẫn**. Bài test từng lớp:

1. Matcher: method và path có khớp?
2. Filter chain: request có đi vào đúng chain?
3. CSRF: token có hợp lệ?
4. Authentication: manager/provider có xác thực không?
5. Success handler/session: response, cookie và context có được lưu đúng không?

Nếu sử dụng stateless API không dựa cookie, quyết định CSRF cần theo threat model, không tắt toàn bộ chỉ vì tiện test curl. Browser tự gửi credentials hoặc cookie vẫn có thể cần CSRF protection.

### 10.2. CORS preflight không phải login attempt

CORS preflight thường là `OPTIONS` request gửi trước một số cross-origin requests. Matcher `POST /auth/login` không kích hoạt login ở OPTIONS; CORS phải được cấu hình riêng. Nếu server yêu cầu authenticated cho mọi OPTIONS trước khi CORS xử lý, frontend có thể thấy lỗi preflight. Không sửa bằng cách cho OPTIONS đi vào password authentication filter.

### 10.3. Dùng POST cho credential submission

Không xử lý password bằng GET vì query string có thể bị lưu trong URL logs/history/proxy. Sử dụng HTTPS, form POST body và CSRF token khi cần. Một client cố tình gửi POST đúng path mà thiếu username/password vẫn là request **được matcher chọn**, nhưng provider nên từ chối qua failure flow, không bao giờ cho authenticated chỉ vì URL đúng.

## 11. Test matrix trong dự án thật

Khi tạo/customize authentication filter, lập bảng tối thiểu:

| Ca | Cần gọi attemptAuthentication? | Ghi chú |
| --- | --- | --- |
| POST đúng login path | Có nếu request tới filter sau các lớp trước | Kiểm thử matcher và CSRF riêng |
| GET login page | Không | Trình bày form, không đăng nhập |
| GET login processing path | Không | Có thể redirect/404 bởi tầng khác |
| OPTIONS login path | Không | CORS preflight |
| POST login path có query | Có | Query không phải một phần path |
| POST login path có segment thừa | Không nếu exact matcher | Tránh matcher `/**` ngoài ý muốn |
| POST endpoint API khác | Không | Để controller/filters khác xử lý |
| POST login trong context path | Có nếu builder được cấu hình tương thích | Test context/servlet mapping |
| POST login dưới chain không chứa filter | Không thể gọi | Sửa `securityMatcher`/chain order |
| POST login thiếu CSRF token | Có thể bị từ chối trước filter | Không diễn giải là password sai |
| POST login sai password | Có attempt, authentication failure | Provider xử lý |
| POST login account disabled | Có attempt, status failure | Không thay thế account-status checks |
| POST login đúng password | Có attempt, success flow | Session/context/redirect hợp lệ |
| Request ERROR dispatch cùng URL | Theo dispatcher policy | Không trigger login ngoài ý muốn |
| Hai filters cùng match | Có thể một hoặc hai tùy flow | Tách URL hoặc định nghĩa ưu tiên |

### 11.1. Tách unit test và integration test

**Unit test matcher/filter gate** kiểm tra `attemptAuthentication` được gọi chính xác khi cần. Nó không cần password thật và không cần HTTP server.

**Integration test filter chain** kiểm tra `FilterChainProxy` chọn đúng chain, URL login nằm trong chain, CSRF rules, session authentication strategy và success/failure handlers. Có thể dùng Spring Security MockMvc test support để gửi form login với CSRF token hợp lệ. Không dùng test “đã vào controller” làm bằng chứng login filter đúng: filter có thể xử lý request **trước controller**.

**End-to-end test** dùng browser/session cookie với form login và kiểm tra GET `/me` sau login, logout, CSRF, endpoint không match, đường dẫn có context path thực tế và reverse proxy nếu sản phẩm có dùng.

## 12. Troubleshooting

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| POST login trả 404 | Login URL không thuộc chain; filter chưa đăng ký; URL sai | Kiểm tra `securityMatcher`, `loginProcessingUrl`, thứ tự chains |
| Login page hiển thị nhưng submit không xác thực | Form action gửi sai URL/method, filter không match | So form action với matcher và test method/path |
| POST login trả 403 dù matcher đúng | CSRF invalid/missing hoặc authorization policy | Kiểm tra `CsrfFilter` và token trước khi debug password |
| GET login URL bị xử lý như đăng nhập | Matcher chỉ xét path, không method | Match `HttpMethod.POST` |
| Filter chạy trên mọi POST | Matcher quá rộng, chỉ kiểm tra method | Match exact path + method |
| `/auth/login/extra` cũng kích hoạt login | Dùng `/**` hoặc regex quá thoáng | Dùng exact pattern và negative tests |
| GET /auth/login redirect /login | Filter bỏ qua attempt, authorization yêu cầu login | Bình thường tùy config, không hẳn là lỗi matcher |
| POST /auth/login sai password nhưng không có failure handler | Filter custom thiếu manager/handler/session policy | Dùng form login chuẩn hoặc cấu hình đầy đủ |
| POST login JSON bị coi như không có credentials | `UsernamePasswordAuthenticationFilter` chuẩn đọc form params | Dùng authentication converter/filter JSON đúng thiết kế |
| Endpoint login trong `/auth/**` nhưng chỉ có `securityMatcher("/api/**")` | Chain không chứa login URL | Đổi URL hoặc mở rộng chain matcher có kiểm soát |
| Matcher test pass nhưng production không gọi filter | Filter không nằm trong chain, sai thứ tự, bị chain khác chọn | Xác minh `FilterChainProxy` và registrations |
| Filter chạy hai lần | Cùng instance được auto-register và add vào chain | Chỉ đăng ký đúng một nơi |
| Context path /shop khiến matcher fail | Nhầm URI ngoài với path relative context | Dùng PathPattern matcher/basePath và test |
| OPTIONS bị 401/403 trước request thật | CORS/preflight config không phù hợp | CORS xử lý trước auth; không coi OPTIONS là login |
| User login đúng nhưng /me vẫn anonymous | Chưa save SecurityContext/session policy sai | Kiểm tra success handler, repository, session/cookie |
| Hai login filters tranh cùng URL | Matcher overlap, order không rõ | Tách processing URLs hoặc hợp nhất auth flow |

### 12.1. Debug theo thứ tự để không sửa sai lớp

1. Lấy **HTTP method**, path, context path và servlet mapping mà server thực sự thấy; không log password.
2. Kiểm tra `FilterChainProxy` chọn chain nào.
3. Kiểm tra filter instance đó đã được đăng ký đúng chưa và không bị đăng ký hai lần.
4. Kiểm tra `RequestMatcher.matches(request)` trên request thật hoặc test mock tương ứng.
5. Xem CSRF/CORS có chặn request trước filter hay không.
6. Nếu `attemptAuthentication` chạy, kiểm tra body parser, `AuthenticationManager` và providers.
7. Nếu thành công mà request sau anonymous, chuyển sang debug SecurityContext/session persistence; không sửa matcher trước.
8. Nếu request đã authenticated nhưng `403`, kiểm tra authorization và authorities.
9. Giữ logs an toàn: không in credentials, session ID nguyên vẹn, access/refresh tokens hoặc full authentication object.

## 13. Tình huống và đáp án

**Câu 1.** Filter được thêm vào chain, nhưng `GET /login` không gọi `attemptAuthentication`. Đây có phải lỗi?

**Đáp án:** không. Với form login chuẩn, GET thường hiển thị trang; POST mới xử lý credentials. Filter có thể được gọi nhưng matcher trả false.

**Câu 2.** Client gửi `POST /auth/login` và matcher trả true. Có được phép kết luận user đã đăng nhập?

**Đáp án:** không. Matcher chỉ chọn authentication attempt. Manager/provider còn phải xác minh credentials và các điều kiện account; CSRF có thể chặn request trước filter.

**Câu 3.** Ứng dụng dùng `http.securityMatcher("/api/**")` và form login processing URL `/auth/login`. Tại sao filter không chạy?

**Đáp án:** vì request `/auth/login` không đi vào chain chỉ match `/api/**`. Cần đồng bộ chain matcher và endpoint login; không thay bằng rule `permitAll()` đơn thuần.

**Câu 4.** `authorizeHttpRequests().requestMatchers("/auth/login").permitAll()` có đảm bảo `UsernamePasswordAuthenticationFilter` xử lý login không?

**Đáp án:** không. Nó chỉ đặt authorization rule, không bảo đảm filter được đăng ký, matcher đúng URL/method hay chain chứa endpoint.

**Câu 5.** Có nên set `requiresAuthenticationRequestMatcher` thành `/**` để tránh bỏ sót request?

**Đáp án:** không. Authentication filter có thể chiếm cả requests nghiệp vụ. Chọn method/path chính xác và thêm negative tests.

**Câu 6.** URL client là `/shop/auth/login` khi app deploy với context path `/shop`. Matcher nên khai báo path nào?

**Đáp án:** với PathPattern matcher relative to context path, thường là `/auth/login`. Nếu servlet có mapping prefix khác thì dùng `basePath`/test phù hợp.

**Câu 7.** `POST /auth/login` thiếu CSRF bị 403, trong unit test matcher lại true. Hai kết quả có mâu thuẫn?

**Đáp án:** không. Unit test chỉ đo matcher; `CsrfFilter` có thể từ chối trước khi login filter được gọi.

**Câu 8.** Form gửi body JSON vào `UsernamePasswordAuthenticationFilter` chuẩn mà không có form params. Matcher đúng có đủ không?

**Đáp án:** không. Cần parsing/`AuthenticationConverter` hoặc filter phù hợp JSON; matcher chỉ chọn request.

**Câu 9.** Trong unit test, `attemptAuthentication` trả null. Có nghĩa request login thành công?

**Đáp án:** không. Đây là fixture minh họa flow chưa hoàn tất. Production phải trả authentication đã được manager xác minh hoặc ném exception/tiếp tục đúng contract.

**Câu 10.** Một filter custom đã được khai báo `@Component` và thêm qua `addFilterBefore`. Có thể xảy ra điều gì?

**Đáp án:** filter có thể bị đăng ký hai lần (container và Spring Security chain). Cần kiểm soát đăng ký đúng một nơi.

**Câu 11.** Tại sao `GET /auth/login` không match không nhất thiết trả HTTP 405?

**Đáp án:** filter chỉ chuyển tiếp request; sau đó authorization/entry point, controller mappings hoặc fallback chain có thể redirect/404/405 theo cấu hình. Matcher không quyết định response status khi bỏ qua request.

**Câu 12.** Nếu muốn hai URL login khác nhau nhưng cùng provider, nên làm gì?

**Đáp án:** cân nhắc `OrRequestMatcher` của hai **POST exact paths**, đồng thời chuẩn hóa parser, policies, CSRF, rate limit, success/failure handlers và tránh matcher overlap với filter khác.

## 14. Checklist tích hợp

- [ ] Xác định đúng `SecurityFilterChain` chứa authentication filter cho endpoint login.
- [ ] Phân biệt rõ `securityMatcher`, `authorizeHttpRequests.requestMatchers` và `requiresAuthenticationRequestMatcher`.
- [ ] Với form login chuẩn, ưu tiên `formLogin(...loginProcessingUrl(...))` thay vì tạo filter thủ công.
- [ ] Nếu custom filter, cấu hình `RequestMatcher` qua constructor hoặc `setRequiresAuthenticationRequestMatcher` đúng instance, không ghi đè ngoài ý muốn bằng `setFilterProcessesUrl`.
- [ ] Matcher giới hạn đúng **HTTP method** và **exact path**, không dùng `contains("/login")` hoặc wildcard quá rộng.
- [ ] Đã thử GET/POST/PUT/OPTIONS, path sai, slash/segment thừa, query string, context path và servlet mapping.
- [ ] Không nhầm matcher true với authentication success, authorization permit hoặc CSRF valid.
- [ ] Form/JSON parser dùng đúng content type, username/password parameter names và body size limits.
- [ ] Login POST trong browser có CSRF token phù hợp và chạy qua HTTPS.
- [ ] Custom filter có manager/provider, handlers, context repository, session strategy, rate limit, audit và filter order đúng.
- [ ] Không tạo authenticated token từ dữ liệu client mà không kiểm chứng.
- [ ] Không đăng ký cùng filter hai lần; biết rõ filters nào chạy trong chain đã chọn.
- [ ] Với multi-chain, endpoint login không nằm ngoài `securityMatcher`; có catch-all chain bảo vệ toàn ứng dụng.
- [ ] Đã phân biệt lỗi 404/405/403/401/302 do những tầng khác nhau, không “sửa” bằng cách mở rộng matcher bừa bãi.
- [ ] Unit test filter gate và integration test chain + CSRF + login success/failure đều chạy với dependency thực tế.

**Kết luận:** `requiresAuthenticationRequestMatcher` là **cổng quyết định một authentication filter có thử xác thực ở request hiện tại hay không**. Cấu hình điển hình cho form login là **`POST` đến một processing URL xác định**. Matcher chỉ giới hạn nhiệm vụ của filter: nó không chọn security chain, không cấp quyền, không kiểm tra mật khẩu và không thay CSRF. Muốn tích hợp an toàn, hãy đồng bộ URL/method giữa client và filter, đặt filter đúng chain, và kiểm thử cả request cần xử lý lẫn request phải đi tiếp.

## Tài liệu tham khảo chính thức

- [Spring Security 6.5 — AbstractAuthenticationProcessingFilter API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/AbstractAuthenticationProcessingFilter.html)
- [Spring Security 6.5 — UsernamePasswordAuthenticationFilter API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/UsernamePasswordAuthenticationFilter.html)
- [Spring Security 6.5 — Form Login](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/form.html)
- [Spring Security 6.5 — Java Configuration: SecurityFilterChain Endpoints](https://docs.spring.io/spring-security/reference/6.5/servlet/configuration/java.html)
- [Spring Security 6.5 — PathPatternRequestMatcher.Builder API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/servlet/util/matcher/PathPatternRequestMatcher.Builder.html)
- [Spring Security 6.5 — RequestMatcher API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/util/matcher/RequestMatcher.html)
- [Spring Security 6.5 — Servlet Security Filters](https://docs.spring.io/spring-security/reference/6.5/servlet/architecture.html)
- [Spring Security 6.5 — CSRF](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html)
