# Vòng lặp chuyển hướng do endpoint đăng nhập, trang lỗi hoặc matcher

> **Chuyên đề:** Chẩn đoán vòng lặp HTTP 3xx trong Spring Security Servlet — đặc biệt khi **GET trang đăng nhập**, **trang lỗi /error**, **dispatcher ERROR/FORWARD**, **request matcher** hoặc **SecurityFilterChain** được cấu hình sai. Bài dùng Java 17+, Spring Boot 3.x và Spring Security 6.x; phân biệt ví dụ độc lập với các mảnh cấu hình cần đặt trong dự án. Mục tiêu không phải loại bỏ redirect bằng cách mở toàn bộ ứng dụng, mà là xác định **request đầu tiên sai kỳ vọng** và sửa đúng biên authorization.

## 1. Hiện tượng và mục tiêu chẩn đoán

Một vòng lặp chuyển hướng xảy ra khi browser nhận response 301/302/303/307/308 rồi tiếp tục request theo header `Location`, nhưng chuỗi không đến được trang cuối ổn định.

~~~text
GET /private        -> 302 Location: /login
GET /login          -> 302 Location: /login
GET /login          -> 302 Location: /login
Browser             -> Too many redirects
~~~

Ở đây, `GET /private` yêu cầu đăng nhập là bình thường; **`GET /login` của người chưa đăng nhập lại bị chuyển về chính nó** là điểm sai. Một chuỗi phức tạp hơn:

~~~text
GET /private        -> 302 Location: /login
GET /login          -> 500: template/view render lỗi
ERROR dispatch      -> /error
/error              -> 302 Location: /login
GET /login          -> lại 500, lại ERROR /error...
~~~

Và một tình huống có vẻ giống nhưng khác về bản chất:

~~~text
POST /login         -> 302 Location: /dashboard
GET /dashboard      -> 302 Location: /login
GET /login          -> 200, browser hiện form
Người dùng submit lại -> cùng chu kỳ
~~~

Tình huống cuối thường gọi là **login bounce**, có thể do mất `SecurityContext`/session/cookie hoặc chưa hoàn thành MFA, không nhất thiết là loop 302 vô hạn trong một chuỗi GET.

**Sau bài học**, bạn cần phân biệt: login page bị bảo vệ, login processing URL không do form filter nhận, lỗi view dẫn tới error handler bị khóa, chain matcher sai, cookie/session không tồn tại và redirect sai ở proxy/SSO. Bạn sẽ biết thu thập trace, sửa cấu hình, và viết test xác nhận không tạo lỗ hổng mới.

## 2. Cơ chế Spring Security tạo redirect đến login

~~~text
Browser anonymous GET /private
       |
       v
FilterChainProxy chọn SecurityFilterChain
       |
AuthorizationFilter yêu cầu authenticated
       |
AccessDeniedException
       |
ExceptionTranslationFilter
       |
AuthenticationEntryPoint (thường LoginUrlAuthenticationEntryPoint)
       |
HTTP 302 Location: /login
       |
Browser GET /login
       |
       +-- permit /login -> MVC render login -> 200
       |
       +-- /login cũng yêu cầu authenticated
                  |
            AuthenticationEntryPoint
                  |
              302 /login -> LOOP
~~~

Các thành phần và trách nhiệm:

| Thành phần | Vai trò | Gây vòng khi nào? |
| --- | --- | --- |
| `FilterChainProxy` | Chọn filter chain từ danh sách theo thứ tự | Login request vào chain khác dự kiến |
| `http.securityMatcher(...)` | Chọn phạm vi **cả chain** | Filter form login không nhận path /login |
| `authorizeHttpRequests().requestMatchers(...)` | Quy định quyền **trong chain được chọn** | Anonymous không được vào login/error |
| `AuthorizationFilter` | Áp dụng quyền trên request và dispatch | FORWARD/ERROR bị từ chối |
| `ExceptionTranslationFilter` | Khi anonymous bị denied, kích hoạt entry point | Redirect ngay cả lúc request là /login |
| `LoginUrlAuthenticationEntryPoint` | Dẫn browser tới login page | Đích lại bị chặn hoặc controller tự redirect |
| `UsernamePasswordAuthenticationFilter` | Xử lý POST đúng `loginProcessingUrl` | Form POST sang route không khớp filter |
| `AuthenticationFailureHandler` | Quyết định response cho credential invalid | Failure URL không thể hiển thị |
| `AuthenticationSuccessHandler` | Chọn landing URL/saved request | Success target không có quyền/context |
| `SecurityContextRepository` | Persist authenticated context | Request sau login bị xem là anonymous |
| `RequestCache` | Lưu request cần trở lại sau login | Saved request sai hoặc custom handler không an toàn |

**Đừng kết luận thấy 302 là đăng nhập thành công.** 302 có thể đến từ entry point, success handler, failure handler, MVC controller, view resolver, proxy hoặc IdP. Lệnh chẩn đoán đầu tiên là xem `Location` và request method.

## 3. Nguyên nhân phổ biến nhất: custom login page bị bảo vệ

### Cấu hình đáng nghi

~~~java
@Bean
SecurityFilterChain broken(HttpSecurity http) throws Exception {
    return http
            .authorizeHttpRequests(auth ->
                    auth.anyRequest().authenticated())
            .formLogin(form -> form.loginPage("/login"))
            .build();
}
~~~

Trong một dự án có custom `GET /login`, nếu rule hoặc chain thực tế không cho anonymous xem URL này, entry point đưa user tới `/login` rồi lại gặp điều kiện phải đăng nhập. Một số cấu hình `formLogin` có thể tự permit các URL liên quan khi gọi `.permitAll()`, nhưng **không nên giả định mọi chain/controller đều được phép**. Luôn test GET page thực tế.

### Cách sửa đúng phạm vi

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class WebSecurityConfig {

    @Bean
    SecurityFilterChain web(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/login", "/error",
                                "/css/**", "/js/**", "/images/**")
                        .permitAll()
                        .anyRequest().authenticated())
                .formLogin(form -> form
                        .loginPage("/login")
                        .loginProcessingUrl("/login")
                        .failureUrl("/login?error")
                        .defaultSuccessUrl("/dashboard", true)
                        .permitAll())
                .build();
    }
}
~~~

Đây là **mảnh cấu hình cho project Spring**, không phải Java độc lập chạy `javac`. Phải có `GET /login` do ứng dụng render, endpoint `/dashboard`, user store/password provider và giao diện POST đúng CSRF. Quy tắc public chỉ giới hạn vào login, error và tài nguyên tĩnh; mọi route còn lại vẫn yêu cầu authentication.

**Lưu ý:**

- `formLogin().loginPage("/login")` dùng **trang custom**. Spring Security không còn tự sinh HTML login page mặc định theo cách thông thường; ứng dụng phải triển khai GET tương ứng.
- `POST /login` thường do `UsernamePasswordAuthenticationFilter` xử lý nếu đúng `loginProcessingUrl`; không cần một MVC controller POST khác.
- `requestMatchers("/login?error")` **không phải** cách đáng tin để cho phép failure page; query string không phải path. Match path `/login` rồi đọc query `error` trong UI.
- `.defaultSuccessUrl("/dashboard", true)` chọn đích thành công cố định cho demo. Nó không chữa việc mất session; chỉ giúp test đường happy-path dễ đối chiếu.
- Không sử dụng `.anyRequest().permitAll()` hoặc `web.ignoring("/**")` để xóa loop vì chúng làm suy yếu hệ thống.

## 4. GET /login và POST /login: hai quyền sở hữu khác nhau

| Request | Ai thường xử lý? | Điều cần kiểm tra |
| --- | --- | --- |
| Anonymous `GET /login` | MVC controller/template do ứng dụng cung cấp nếu custom loginPage | Có thật controller/view? Có public? |
| `POST /login` | `UsernamePasswordAuthenticationFilter` theo `loginProcessingUrl` | Path, method, CSRF, username/password fields |
| `GET /login?error` | Cũng là GET path /login, thêm query | Trang lỗi công khai có render được không? |
| `GET /dashboard` | MVC protected route | Có Authentication/session sau login không? |
| `GET /error` hoặc ERROR dispatch | Spring Boot error controller/custom error renderer | Có bị security entry point chuyển ngược về login không? |

Khi khai báo custom `loginPage("/signin")` nhưng form trong HTML POST tới `/login` trong khi `loginProcessingUrl("/authenticate")`, filter có thể không bắt POST. Ứng dụng có thể trả 404/405, bị authorize như một request bình thường hoặc dispatch sang /error, khiến browser tưởng password luôn sai.

~~~java
.formLogin(form -> form
        .loginPage("/signin")
        .loginProcessingUrl("/authenticate")
        .failureUrl("/signin?error")
        .permitAll())
~~~

Với snippet trên, ứng dụng phải cung cấp **GET /signin** và form gửi **POST /authenticate**. Mặc định các tên input thường là `username` và `password` trừ khi bạn cấu hình tham số khác. Khi dùng cookie-based form, POST cần CSRF token hợp lệ.

**Nếu GET /login = 404:** kiểm tra controller và template; đừng sửa `PasswordEncoder`.  
**Nếu POST /login = 403:** kiểm tra CSRF hoặc access rule, không lập tức kết luận sai mật khẩu.  
**Nếu POST /login = 302 /login?error:** mới xem lỗi xác thực và handler (vẫn không chắc provider đã thật sự chạy nếu có handler tùy biến).

## 5. /error và ERROR/FORWARD dispatch: lỗi gốc bị che bởi redirect

Trong Spring Boot, khi controller/template ném lỗi, container có thể dispatch tới `/error` theo `DispatcherType.ERROR`. Spring Security `AuthorizationFilter` có thể áp dụng cho nhiều dispatcher types, không chỉ `REQUEST`.

~~~text
GET /login
   -> ViewResolver gặp template không tồn tại
   -> exception
   -> servlet ERROR dispatch /error
   -> AuthorizationFilter: anonymous không được xem /error
   -> LoginUrlAuthenticationEntryPoint: 302 /login
   -> GET /login lại gặp view error
   -> LOOP
~~~

Phải sửa **hai lớp**: cấu hình cho error page/dispatch được xử lý đúng, và **nguyên nhân gốc** như thiếu template, lỗi controller hay đường view sai.

### Cấu hình ERROR/FORWARD có chủ đích

~~~java
import jakarta.servlet.DispatcherType;

@Bean
SecurityFilterChain web(HttpSecurity http) throws Exception {
    return http
            .authorizeHttpRequests(auth -> auth
                    .dispatcherTypeMatchers(
                            DispatcherType.ERROR,
                            DispatcherType.FORWARD).permitAll()
                    .requestMatchers("/login", "/error",
                            "/css/**", "/js/**").permitAll()
                    .anyRequest().authenticated())
            .formLogin(form -> form
                    .loginPage("/login")
                    .permitAll())
            .build();
}
~~~

Đây là **phương án thay cho cấu hình bean web tương ứng**, không gắn cùng lúc hai bean `web(...)` có luật chồng nhau. Spring Boot 3 dùng `jakarta.servlet.DispatcherType`; không copy `javax.servlet.DispatcherType` từ Boot 2.

Giải thích:

- `dispatcherTypeMatchers(ERROR, FORWARD).permitAll()` xử lý authorize cho một số internal dispatch cần render error/view theo thiết kế.
- `requestMatchers("/error").permitAll()` có thể cho phép GET tới trang xử lý lỗi theo path.
- `GET /admin` với dispatcher `REQUEST` **vẫn yêu cầu authentication** theo `anyRequest().authenticated()`.
- Không phải mọi ứng dụng đều muốn cho tất cả FORWARD được phép; cân nhắc giới hạn theo endpoint/error renderer nếu có threat model đặc biệt.
- Nếu error handler của bạn tự `redirect:/login` cho mọi lỗi, vẫn có thể tạo loop dù quyền `/error` đã được sửa. Kiểm tra MVC handler và proxy, không chỉ AuthorizationFilter.

Đôi khi response ban đầu là 500 nhưng browser thấy 302 cuối cùng. Hãy đọc log exception, request ID, `DispatcherType.ERROR` và `Location` tại từng bước để không nhầm là lỗi credential.

## 6. securityMatcher và requestMatchers KHÔNG có cùng ý nghĩa

**`securityMatcher`** chọn liệu một `SecurityFilterChain` có chạy cho request không. **`requestMatchers`** trong `authorizeHttpRequests` chỉ chọn rule authorization **sau khi chain ấy đã được chọn**.

~~~java
@Bean
SecurityFilterChain scoped(HttpSecurity http) throws Exception {
    return http
            .securityMatcher("/secured/**")
            .authorizeHttpRequests(auth -> auth
                    .requestMatchers("/login").permitAll()
                    .anyRequest().authenticated())
            .formLogin(form -> form
                    .loginPage("/login")
                    .loginProcessingUrl("/login"))
            .build();
}
~~~

Ở ví dụ này `/login` **nằm ngoài `/secured/**`** nên toàn chain không chạy cho GET/POST `/login`. Thêm rule permitAll **trong chain ấy** không làm /login tự đi vào chain. Endpoint `POST /login` do filter form login của chain này cũng không được cung cấp cho request ngoài `securityMatcher`. Tùy chain khác/controller, kết quả có thể là 404, 403 hoặc một chuỗi redirect — **không nhất thiết 302 loop**.

### Bảng phân biệt

| Cấu hình | Phạm vi | Kiểm thử cần làm |
| --- | --- | --- |
| `http.securityMatcher("/api/**")` | Chain áp dụng cho /api/** | Request API có vào đúng chain không |
| `authorize.requestMatchers("/api/public").permitAll()` | Rule trong chain đang chọn | Có bị một chain trước chặn không |
| `anyRequest().authenticated()` | Catch-all trong **chain đang chọn** | Không tự bao phủ URL ngoài chain |
| `@Order(1)` | Chain được thử trước chain khác | Chain quá rộng có nuốt /login không |
| Chain không có `securityMatcher` | Thường là fallback cho các request còn lại | Có bao phủ URL không chain trước nhận không |

Nếu **không chain nào match**, một URL có thể nằm ngoài bảo vệ của Spring Security. Đây là vấn đề security quan trọng hơn cả redirect loop; không chữa bằng cách xóa hết matcher mà chưa xác định coverage.

### Cấu hình hai chain có fallback hợp lý

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ChainConfig {

    @Bean
    @Order(1)
    SecurityFilterChain api(HttpSecurity http) throws Exception {
        return http
                .securityMatcher("/api/**")
                .authorizeHttpRequests(auth ->
                        auth.anyRequest().authenticated())
                .httpBasic(Customizer.withDefaults())
                .sessionManagement(session -> session
                        .sessionCreationPolicy(
                                SessionCreationPolicy.STATELESS))
                .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain web(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/login", "/error",
                                "/css/**", "/js/**").permitAll()
                        .anyRequest().authenticated())
                .formLogin(form -> form
                        .loginPage("/login")
                        .loginProcessingUrl("/login")
                        .permitAll())
                .build();
    }
}
~~~

`/api/**` vào chain 1 có HTTP Basic; `/login` vào chain 2 có form login. Web chain không giới hạn `securityMatcher` nên xử lý các request chưa được chain 1 nhận. Các snippet cấu hình trong các mục khác là **phương án thay thế**, không sao chép tất cả `@Configuration` vào cùng một project để tạo các bean đè nhau.

Với API bearer JWT, thay HTTP Basic bằng OAuth2 Resource Server theo contract; ở đây Basic chỉ minh họa **API không redirect HTML login**. Kiểm tra `GET /api/private` anonymous nên nhận 401 theo loại API, không vòng về `/login`.

## 7. Thứ tự rule, HTTP method và query string

Các rule authorization thường được xét theo thứ tự. Luật tổng quát nên đặt **cuối**:

~~~java
// Cách cấu hình rõ ràng:
.authorizeHttpRequests(auth -> auth
        .requestMatchers("/login", "/error").permitAll()
        .requestMatchers("/admin/**").hasRole("ADMIN")
        .anyRequest().authenticated())
~~~

Không thêm `requestMatchers("/login").permitAll()` sau `anyRequest()` rồi mong nó ghi đè rule trước; DSL có thể không chấp nhận cấu hình đó hoặc rule cụ thể sẽ không hoạt động theo giả định.

**Query parameter khác path:** `/login?error` là GET với path `/login`, query `error`. Nhiều matchers phổ biến dựa vào path mà không dùng query. Không viết `requestMatchers("/login?error")` để chữa lỗi. Nếu muốn xử lý query, hãy làm ở controller/template, không mở một đường dẫn bảo mật mới chỉ vì URL có dấu hỏi.

**GET khác POST:** Quy tắc permit cho `HttpMethod.GET` không tự bao gồm POST. `formLogin().permitAll()` có chức năng cho phép các endpoint login liên quan theo framework, nhưng phải kiểm tra chain nhận được POST và CSRF token hợp lệ. Cấu hình `loginProcessingUrl` phải khớp chính xác action của form theo URL mapping.

**Servlet path/context path:** Khi ứng dụng ở `/app` hoặc DispatcherServlet được map tại `/web/*`, phải phân biệt URL bên ngoài browser, context path, servlet path và đường mà matcher thật xét. Đừng tự cộng `/app` vào mọi matcher nếu framework đã loại context path; hãy xem request thực tế và API matcher đúng phiên bản Spring.

**Matcher implementation:** Spring Security có thay đổi API/matcher theo phiên bản; khi ứng dụng dùng MVC và `PathPattern`, test path, wildcard, servlet mapping thay vì đoán từ chuỗi `/**`. Kiểm thử cả trailing slash, URL encoding và case sensitivity nếu hệ thống có quy tắc riêng.

## 8. Success/failure URL và RequestCache tạo vòng khác

### Failure URL

~~~text
POST /login (password sai)
     -> 302 /login?error
GET /login?error
     -> 302 /login
GET /login
     -> 302 /login?error
     -> ...
~~~

Vòng này có thể do custom MVC controller đang tự redirect khi thấy/không thấy `error`, reverse proxy rewrite URL hoặc matcher bảo vệ route. Xác minh `GET /login` trực tiếp có trả 200 không, và nếu có query `error` thì UI chỉ **render** thông báo chung thay vì tiếp tục redirect vô hạn.

### Success URL

~~~text
POST /login (đúng password)
     -> 302 /dashboard
GET /dashboard
     -> 302 /login
GET /login
     -> 200
~~~

Trong ví dụ, password có thể đã đúng nhưng authenticated context không persist hoặc browser không gửi cookie. Nếu user đã authenticated nhưng thiếu role/MFA, kết quả thông thường có thể là 403; chỉ khi hệ thống còn coi user anonymous hoặc handler tùy chỉnh redirect thì thường quay lại login. Phải xem `SecurityContext` ở request sau.

### RequestCache

Spring có thể lưu request ban đầu `/dashboard` trước khi đưa anonymous tới login, rồi success handler chuyển về request đó. Nếu saved request là route sai/không có quyền hoặc một custom handler ghi request không đúng, flow có thể bounce.

- Xem saved request/redirect target trong log an toàn hoặc test.
- Nếu dùng `defaultSuccessUrl("/dashboard", true)`, flag `true` chọn đích mặc định thay vì saved request; hữu ích cho test deterministic.
- Đừng chuyển mọi user tới `/admin` nếu đa số chỉ có `ROLE_USER`.
- Không cho client tự đặt success URL tùy ý dẫn đến open redirect; giới hạn host/path an toàn.
- Không đưa access token, recovery code hay OIDC authorization code vào query redirect.

Một vòng lặp xảy ra ngay cả khi `/login` public có thể bắt đầu từ **một landing URL không phù hợp**; không chữa bằng cách permitAll cho landing URL cần bảo vệ.

## 9. Mất session hoặc SecurityContext sau login

Nếu login POST success nhưng request kế tiếp lại anonymous, xem các nguyên nhân sau:

| Lớp | Lỗi điển hình | Bằng chứng |
| --- | --- | --- |
| Browser cookie | Không gửi lại cookie, sai `Path`/`Domain`/`Secure`/`SameSite` | Browser Network, Set-Cookie/Cookie (không chia sẻ raw secret) |
| Context persistence | Custom auth chỉ set `SecurityContextHolder` mà không `saveContext` | Request sau anonymous, session không có context |
| Session fixation | Login đổi session ID nhưng proxy/browser giữ cookie cũ | So khớp session reference an toàn trước/sau |
| Stateless policy | Browser chain dùng `SessionCreationPolicy.STATELESS` | Không tạo session như mong đợi |
| Multi-node | Pod A lưu local session, pod B không thấy | Lặp chỉ khi load balancer đổi pod |
| Remember-me/OIDC | Cookie hoặc auth request repository mất sau callback | OIDC tự khởi động login lại |
| MFA partial auth | Password đúng nhưng vẫn thiếu yếu tố thứ hai | Chuyển đúng `/mfa/challenge`, không phải private target |
| Auth exception | Session store hay persistence commit lỗi sau provider success | Audit ghi provider success nhưng login chưa hoàn tất |

Với custom authentication trên Spring Security 6, việc set `SecurityContextHolder` có thể chỉ sống trong một request. Nếu ứng dụng tự xử lý login, phải dùng `SecurityContextRepository` phù hợp để lưu context:

~~~java
// Mảnh trong custom login handler, sau verify hoàn chỉnh:
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(verifiedAuthentication);
SecurityContextHolder.setContext(context);
securityContextRepository.saveContext(context, request, response);
~~~

Các biến đã được tạo từ flow thực tế; không copy đoạn này vào mọi Spring form-login handler mặc định. `verifiedAuthentication` phải là chứng cứ đã được provider xác thực, không tự dựng từ `?authenticated=true` do client gửi. Session fixation protection, CSRF, MFA, timeout và authorization vẫn cần thiết kế đúng.

**Không log raw `JSESSIONID` để theo dõi.** Nếu cần correlation, dùng surrogate ID hoặc HMAC tham chiếu trong audit store có phân quyền. Một ứng dụng vẫn có thể có anonymous session dùng cho CSRF/request cache; **có session** không đồng nghĩa **đăng nhập thành công**.

## 10. Reverse proxy và HTTPS redirect có thể lặp trước Spring

~~~text
Browser truy cập HTTPS /login
   -> Proxy terminates TLS, chuyển HTTP tới backend
   -> Backend tưởng đang HTTP, trả 302 HTTPS /login
   -> Browser lại HTTPS, proxy lại chuyển HTTP
   -> Loop
~~~

Hoặc proxy rewrite `/app/login -> /login` nhưng ứng dụng redirect `/login -> /app/login`. Đây có thể là vòng giữa **hai lớp hạ tầng**, không liên quan tới `requestMatchers`.

Khi trace, ghi:

- Scheme `http`/`https` trong `Location` và request.
- Host, port, dấu slash cuối, path prefix, context path.
- Thay đổi từ 301/308 cached redirect so với 302/303 tạm.
- `Forwarded`, `X-Forwarded-Proto`, `X-Forwarded-Host`, `X-Forwarded-Prefix` do proxy **đáng tin** phát ra.
- `server.forward-headers-strategy` và cấu hình ingress/proxy thực tế, không chọn tùy tiện khi chưa có trust model.
- Cookie `Secure`, `SameSite`, `Domain`, `Path` qua TLS termination.
- Sự khác biệt giữa localhost và production HTTPS.

**Không tin header Forwarded do client internet tự cung cấp.** Cho phép attacker điều khiển host/scheme có thể tạo redirect sai hoặc host-header poisoning; backend chỉ tin proxy được quản trị và đã chuẩn hóa headers.

Nếu browser giữ cache 301/308 từ cấu hình cũ, kiểm thử bằng profile sạch/ẩn danh và client HTTP không dùng cache trước khi sửa source code.

## 11. OIDC/OAuth2 login loop cần chẩn đoán bằng state và callback

Một vòng với OAuth2 Login thường trông như:

~~~text
GET /private
 -> /oauth2/authorization/provider
 -> IdP authorization endpoint
 -> /login/oauth2/code/provider?code=...&state=...
 -> local session/state không tìm thấy
 -> /oauth2/authorization/provider
 -> IdP lại chuyển callback
 -> ...
~~~

Các nguyên nhân thường khác form-login:

1. `redirect_uri` tại IdP không khớp scheme/host/path của ứng dụng sau proxy.
2. Callback không lọt vào chain có `oauth2Login(...)` filter do `securityMatcher`/`@Order`.
3. `OAuth2AuthorizationRequestRepository`/session đã lưu state nhưng cookie mất giữa cross-site redirect.
4. `SameSite`, `Secure`, domain/path, load balancer hoặc Spring Session đa pod sai.
5. Có lỗi khi đổi authorization code hoặc verify ID token, nhưng custom failure handler lại bắt đầu login tự động không giới hạn.
6. IdP SSO đã có session nhưng ứng dụng local không persist authenticated context, gây reauthorize lặp.
7. Callback có trailing slash/prefix/method không đúng endpoint filter đã đăng ký.

**Không bỏ kiểm tra `state`, nonce, PKCE hay JWT signature để chữa redirect loop.** Authorization code và token là credential nhạy cảm; không dán nguyên callback URL hoặc HAR chứa code/state vào ticket. Trace cần redaction và giữ phân quyền.

OIDC custom login page còn cần các `/oauth2/authorization/{registrationId}` URL được xử lý bởi đúng chain. Nếu link login IdP được render đúng nhưng chính endpoint OAuth2 authorization bị guard hoặc không được filter nhận, flow có thể quay về trang login.

## 12. Chẩn đoán HTTP từ browser và curl

Trong Developer Tools của browser:

1. Mở Network, bật **Preserve log**.
2. Tải `/private` khi chưa login hoặc reproduce flow trên tài khoản test.
3. Xem từng request theo thứ tự: Method, URL/path, Status, Location, initiator, redirect chain và cookie được gửi/nhận (chỉ xem tại máy kiểm thử).
4. Xác định **bước đầu tiên sai kỳ vọng**; ví dụ `GET /login` trả 302 thay vì 200.
5. Nhìn nếu có request `/error`, scheme thay đổi, callback IdP, 403 CSRF, 404 missing route hoặc 500 view error.
6. Correlate với server request ID và chain match log; không chia sẻ raw Cookie/Authorization/OTP/token.

Bảng trace minh họa:

| Bước | Method/URL | Status | Location | Hướng điều tra |
| --- | --- | --- | --- | --- |
| 1 | GET `/private` | 302 | `/login` | Entry point hợp lệ |
| 2 | GET `/login` | 302 | `/login` | Login page bị guard/controller redirect |
| 1a | GET `/login` | 500 | ERROR `/error` | Lỗi MVC/view |
| 2a | ERROR `/error` | 302 | `/login` | Trang lỗi/dispatch bị guard |
| 1b | POST `/login` | 302 | `/dashboard` | Có thể password đã đúng |
| 2b | GET `/dashboard` | 302 | `/login` | Session/role/MFA/context |
| 1c | POST `/login` | 403 | — | CSRF/method/authorization |
| 1d | GET `/api/private` | 302 | `/login` | Có thể API dùng nhầm web chain |

### Lệnh curl

~~~bash
curl --silent --show-error --dump-header - \
  --output /dev/null https://portal.example.test/private

curl --silent --show-error --dump-header - \
  --output /dev/null https://portal.example.test/login
~~~

Mặc định hai lệnh trên **không theo redirect** nên thấy trực tiếp status và `Location`. Nếu cần xem toàn chuỗi, giới hạn số hops:

~~~bash
curl -v -L --max-redirs 8 \
  --output /dev/null https://portal.example.test/private
~~~

Chạy trên host và environment được phép kiểm thử. Không dán mật khẩu vào command line, không dùng tài khoản production hay gửi raw cookie/token trong output. Dùng GET thay vì `curl -I` mặc định HEAD khi mục tiêu là GET page; security matcher có thể phân biệt method.

### Phân biệt mã HTTP

| HTTP status | Không nên suy luận |
| --- | --- |
| 301/308 | Có thể bị browser/proxy cache; không luôn là redirect Spring |
| 302/303 | Không tự chứng minh login thành công |
| 307/308 | Có semantics preserve method, có thể đưa POST sang path khác |
| 401 | API thiếu/chưa có credential, thường Basic/Bearer |
| 403 | CSRF hoặc thiếu quyền, không đơn thuần là password sai |
| 404/405 | Endpoint/method không được xử lý, có thể do login processing chain sai |
| 500 | Controller/template/auth service lỗi; error dispatch có thể bị guard |
| 502/503/504 | Proxy/upstream/server timeout; không tự mở quyền |

## 13. DEBUG logs và FilterChainProxy

Ở môi trường test/staging, có thể dùng logging cấu hình như sau:

~~~yaml
logging:
  level:
    org.springframework.security: DEBUG
    org.springframework.security.web.FilterChainProxy: DEBUG
    org.springframework.security.web.access: DEBUG
~~~

Cần tìm:

- `FilterChainProxy` chọn chain nào cho `/login`, `/error`, `/dashboard`?
- `AuthorizationFilter` dùng matcher/rule nào để deny GET login hoặc ERROR dispatch?
- `ExceptionTranslationFilter` gọi AuthenticationEntryPoint nào?
- POST login có vào `UsernamePasswordAuthenticationFilter` hay không?
- Failure handler hay success handler tạo `Location` nào?
- `RequestCache` có giữ URL không phù hợp hoặc target khác quyền?
- Request sau login có Authentication/context thực sự không?
- ERROR dispatch được map qua filter chain nào?
- Proxy có trả redirect trước cả khi request tới Spring không?

Nếu cần TRACE, chỉ bật rất ngắn trong môi trường kiểm soát vì log có thể chứa metadata nhạy cảm. **Không** log raw request body/password, JWT, `Authorization`, Cookie, session IDs, CSRF token, OAuth2 code, OIDC state/nonce hoặc `Authentication.toString()`. Log nên có request ID và category thay vì bí mật.

Một test sai phổ biến là thêm `@WithMockUser` vào `GET /login` rồi thấy nó trả 200; điều đó **không chứng minh anonymous user truy cập được**. Luôn kiểm thử login page khi chưa xác thực.

## 14. Java 17 độc lập: mô phỏng đồ thị redirect và vòng lặp

Đoạn này dùng **JDK 17 thuần**, không phụ thuộc Spring, không gửi HTTP request và không xử lý credential. Nó minh họa logic phát hiện một URL xuất hiện lại trong chuỗi `Location`.

Tệp `RedirectLoopDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

public final class RedirectLoopDemo {

    static String walk(Map<String, String> redirectRules, String start) {
        Set<String> seen = new HashSet<>();
        List<String> path = new ArrayList<>();
        String current = start;

        for (int hop = 0; hop < 10; hop++) {
            if (!seen.add(current)) {
                path.add(current);
                return String.join(" -> ", path) + " [LOOP]";
            }
            path.add(current);
            String next = redirectRules.get(current);
            if (next == null) {
                return String.join(" -> ", path) + " [END]";
            }
            current = next;
        }
        return String.join(" -> ", path) + " [LIMIT]";
    }

    public static void main(String[] args) {
        Map<String, String> loginGuarded = Map.of(
                "/private", "/login",
                "/login", "/login");

        Map<String, String> loginPublic = Map.of(
                "/private", "/login");

        Map<String, String> errorGuarded = Map.of(
                "/broken", "/error",
                "/error", "/login",
                "/login", "/error");

        System.out.println("login guarded: "
                + walk(loginGuarded, "/private"));
        System.out.println("login public: "
                + walk(loginPublic, "/private"));
        System.out.println("error guarded: "
                + walk(errorGuarded, "/broken"));
    }
}
~~~

Chạy bằng JDK 17+:

~~~bash
javac RedirectLoopDemo.java
java RedirectLoopDemo
~~~

Stdout chính xác:

~~~text
login guarded: /private -> /login -> /login [LOOP]
login public: /private -> /login [END]
error guarded: /broken -> /error -> /login -> /error [LOOP]
~~~

**Giới hạn:** Hàm `walk` xử lý đồ thị giả lập, không xét HTTP method, scheme, host, query, cookies, authentication state hoặc status code. Với OIDC, mỗi callback có thể mang query `state` mới nên URL toàn phần không giống nhau dù flow cứ quay lại; điều tra thực tế phải **phân nhóm theo route và bước giao thức**. Không dùng hàm giả lập này làm reverse proxy hoặc bộ quyết định authorization.

## 15. Spring Boot 3 / Spring Security 6: fixture kiểm thử thật

Một dự án Maven Boot đã có parent/BOM Java 17 cần các dependency chính: `spring-boot-starter-web`, `spring-boot-starter-security`, `spring-boot-starter-test` và `spring-security-test` trong scope test. Phần này là **nhiều file trong cùng package**; không phải một file độc lập.

### Tệp RedirectTestingApplication.java

~~~java
package example.redirect;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RedirectTestingApplication {
    public static void main(String[] args) {
        SpringApplication.run(RedirectTestingApplication.class, args);
    }
}
~~~

### Tệp RedirectSecurityConfig.java

~~~java
package example.redirect;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class RedirectSecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder passwordEncoder) {
        return new InMemoryUserDetailsManager(
                User.withUsername("learner")
                        .password(passwordEncoder.encode("local-test-pass"))
                        .roles("USER")
                        .build());
    }

    @Bean
    SecurityFilterChain web(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/login", "/error").permitAll()
                        .anyRequest().authenticated())
                .formLogin(form -> form
                        .loginPage("/login")
                        .loginProcessingUrl("/login")
                        .failureUrl("/login?error")
                        .defaultSuccessUrl("/dashboard", true)
                        .permitAll())
                .build();
    }
}
~~~

`local-test-pass` là password **cho fixture học tập**, đã được BCrypt encode trước khi lưu `UserDetails`; không dùng trong tài khoản thật. Login page và dashboard là hai endpoint đã được chọn rõ để test redirect. CSRF vẫn giữ mặc định.

### Tệp RedirectDemoController.java

~~~java
package example.redirect;

import java.security.Principal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class RedirectDemoController {

    @GetMapping("/login")
    public String login() {
        return "login page";
    }

    @GetMapping("/dashboard")
    public String dashboard(Principal principal) {
        return "dashboard:" + principal.getName();
    }
}
~~~

Controller này trả **plain text** để đơn giản hóa test route, **không phải HTML form production**. Với giao diện thật, `GET /login` cần render template có form POST đúng action và CSRF. Form login filter của Spring xử lý POST `/login`, còn controller test chỉ xử lý GET.

## 16. MockMvc: kiểm tra đúng chuỗi redirect và session continuity

Tệp `RedirectFlowTest.java`:

~~~java
package example.redirect;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestBuilders.formLogin;
import static org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers.authenticated;
import static org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers.unauthenticated;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrlPattern;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class RedirectFlowTest {

    @Autowired
    MockMvc mvc;

    @Test
    void privateRouteRedirectsButPublicLoginRenders() throws Exception {
        mvc.perform(get("/dashboard"))
                .andExpect(status().is3xxRedirection())
                .andExpect(redirectedUrlPattern("**/login"));

        mvc.perform(get("/login"))
                .andExpect(status().isOk())
                .andExpect(content().string("login page"));

        mvc.perform(get("/login").param("error", ""))
                .andExpect(status().isOk());
    }

    @Test
    void validLoginSurvivesNextRequest() throws Exception {
        MvcResult result = mvc.perform(formLogin()
                        .user("learner").password("local-test-pass"))
                .andExpect(status().is3xxRedirection())
                .andExpect(redirectedUrl("/dashboard"))
                .andExpect(authenticated().withUsername("learner"))
                .andReturn();

        MockHttpSession session =
                (MockHttpSession) result.getRequest().getSession(false);
        assertThat(session).isNotNull();

        mvc.perform(get("/dashboard").session(session))
                .andExpect(status().isOk())
                .andExpect(content().string("dashboard:learner"));
    }

    @Test
    void wrongPasswordFailsButFailurePageIsReachable()
            throws Exception {
        mvc.perform(formLogin()
                        .user("learner").password("wrong"))
                .andExpect(status().is3xxRedirection())
                .andExpect(redirectedUrl("/login?error"))
                .andExpect(unauthenticated());

        mvc.perform(get("/login").param("error", ""))
                .andExpect(status().isOk());
    }
}
~~~

**Vì sao ba test này có giá trị:**

- `GET /dashboard` anonymous chuyển về login, còn `GET /login` anonymous trả 200; đó là điều kiện chặn self-redirect phổ biến.
- `/login?error` vẫn tải được, nên failure handler không đưa browser vào route bị khóa.
- `formLogin()` gửi POST theo contract của Spring Security test và có CSRF; nó đi qua filter/provider thật thay vì bypass bằng `@WithMockUser`.
- Login hợp lệ kiểm tra **cùng session cho request sau**; nếu GET dashboard lại bị redirect login, test phát hiện vấn đề persistence.
- Wrong password không tạo Authentication ở flow test; response failure rõ ràng, không có infinite redirect.
- Nếu project thay form action/processing URL, test phải điều chỉnh theo endpoint thực; không bê fixture này vào OAuth2/JWT rồi đòi cùng 302.

**Không chỉ test status 302:** cả login success, login failure và unauthenticated entry point đều có thể 302. Luôn assert `Location`, status của GET tiếp theo và principal.

## 17. Những test riêng cần thêm

| Tình huống | Test hợp lệ |
| --- | --- |
| Trang login custom chưa triển khai GET | GET /login returns 404, không giả là auth failure |
| POST tới sai loginProcessingUrl | Không tạo Authentication; kiểm tra filter path/method |
| POST thiếu CSRF | 403 theo CSRF policy, không đếm sai password |
| Trang login render view bị lỗi | ERROR dispatch hiển thị lỗi, không lặp /error -> /login |
| Một custom `@Order(1)` chain quá rộng | /login và /api vào chain nào? |
| API anonymous | 401 Basic/Bearer, không HTML login redirect ngoài hợp đồng |
| Error dispatch được permit | Request `DispatcherType.ERROR` không tự yêu cầu lại login |
| Forward tới template | View được render hoặc lỗi đúng, không bị guard vòng |
| Session rotation | Cookie mới dùng ở GET protected; cookie cũ không tự được tin |
| Login đúng nhưng thiếu role | Theo chính sách trả 403 hoặc authorized landing phù hợp |
| Partial authentication / MFA | Không truy cập protected resource trước factor 2; challenge không tự loop |
| OIDC callback khác context path | Callback filter thực sự nhận request; state và nonce được verify |
| Proxy HTTPS | Không lặp `https -> http -> https`; forwarded headers chỉ từ proxy tin |
| Browser có cached 301/308 | Kiểm tra profile mới, URL thực tế và redirect host |
| Session store đa pod | GET sau login trên pod khác vẫn có authenticated context |
| Static resources của login | CSS/JS cần thiết không bị redirect về login |
| Browser gửi lại saved request | Redirect đích đúng quyền, không open redirect |

**MockMvc có giới hạn với servlet ERROR dispatch.** Một số vòng liên quan `/error` chỉ xuất hiện khi embedded Tomcat/Jetty thực hiện error dispatch thật, nên cần thêm `@SpringBootTest(webEnvironment=RANDOM_PORT)`/browser test với container và proxy staging nếu vấn đề nằm ở dispatch/proxy. Không coi một MockMvc GET /error đơn lẻ là đủ chứng minh hệ thống không có vòng lỗi.

Với ứng dụng có nhiều chain, có thể thêm integration test so sánh `/login`, `/api/private`, `/error` và các callbacks dưới đúng `@Order`, thay vì chỉ kiểm bean tồn tại. Kiểm tra fallthrough để URL không bị bỏ hoàn toàn khỏi Spring Security.

## 18. Bảng chẩn đoán nhanh theo triệu chứng

| Triệu chứng | Kiểm tra ưu tiên | Không nên làm |
| --- | --- | --- |
| `/private -> /login -> /login` | GET /login authorization, loginPage permitAll, MVC login | Mở `anyRequest` |
| `/private -> /login -> /error -> /login` | View/controller exception + ERROR dispatcher | Chỉ sửa password |
| GET /login = 404 | Custom controller/template chưa có hoặc URL ngoài chain | Khẳng định sai credential |
| POST /login = 404/405 | Form action/loginProcessingUrl không khớp, chain không nhận | Tạo POST controller đè filter bừa |
| POST /login = 403 | CSRF token, method/authorization | Disable CSRF toàn app |
| POST /login = 302 /login?error | Failure handler, provider/auth error | Cho rằng đã login thành công |
| POST /login = 302 /dashboard; GET dashboard = 302 login | Cookie/session/context, MFA, multi-node | Cho phép dashboard anonymous |
| GET /error = 302 /login | Error route/dispatch bị guard | Bỏ mọi authorization |
| API GET trả 302 HTML login | Chain order và authentication entry point | Dùng form login cho mọi API |
| HTTPS ở proxy lặp | Scheme/host/prefix/forwarded headers | Tin X-Forwarded-* từ Internet |
| OAuth2 reauthorize liên tục | Callback chain/state/cookie/redirect_uri/SSO | Bỏ nonce/state validation |
| Một chain match mọi path đầu tiên | `@Order`/`securityMatcher` | Đoán rằng chain sau sẽ xử lý |
| Cùng URL có lúc được lúc không | Session multi-node, cache, proxy rewrite | Reset mọi user sessions |
| /login?error và /login lặp qua nhau | Controller redirect theo query | Tạo matcher chứa ?error |
| 500 trở thành 302 login | /error dispatch bị guard | Che exception log gốc |

## 19. Quy trình sửa lỗi với thay đổi tối thiểu

1. Reproduce trên tài khoản test và thu chuỗi tối thiểu 2–4 request, gồm method/status/Location.
2. Chỉ ra **request đầu tiên không đúng kỳ vọng**: GET login 302 thay vì 200, POST login 404, ERROR /error bị redirect, hay sau login authenticated session biến mất.
3. Đối chiếu đường dẫn client với backend request path, servlet mapping, context path và reverse proxy.
4. Dò filter chain selection theo `securityMatcher` và thứ tự `@Order`, sau đó xem `requestMatchers` trong chain được chọn.
5. Nếu login page bị guard, permit **chính xác /login và các endpoint login cần thiết**, không đụng các route private.
6. Nếu /error bị guard, cho phép error renderer và dispatcher đúng policy, đồng thời **sửa lỗi controller/view gốc**.
7. Nếu POST không được filter bắt, sửa `loginProcessingUrl` hoặc form action/method; giữ CSRF.
8. Nếu success rồi bounce, kiểm tra cookie/SecurityContext/session store, saved request và MFA state.
9. Nếu proxy đổi scheme/host/path, sửa forwarded header trust/config và cookie, không bỏ TLS validation.
10. Với SSO, xác minh redirect_uri/callback/state/session trước khi cho flow tự khởi động lại.
11. Bổ sung regression tests cho anonymous login GET, failure URL, valid POST, next-request session, error dispatch và multi-chain.
12. Deploy theo canary và quan sát tỷ lệ redirect repeated, 403 CSRF, login 404, error dispatcher failures và session misses.

**Không dùng** `.anyRequest().permitAll()`, `csrf.disable()`, trust-all forwarded headers hoặc bỏ session fixation protection như cách chữa lỗi tiện tay. Một endpoint không redirect nữa chưa chắc là hệ thống đã bảo mật đúng.

## 20. Checklist trước production

**Đường đăng nhập**

- [ ] Anonymous GET /login hoặc custom loginPage tải thật, không redirect chính nó.
- [ ] /login?error hiển thị thông báo chung, không tự chuyển qua lại.
- [ ] POST login khớp filter/CSRF và chỉ cấp session khi credential hợp lệ.
- [ ] Success URL/saved request phù hợp role và MFA state; không chuyển user vào route không có quyền.
- [ ] GET protected sau login dùng session/context được lưu chính xác.
- [ ] Không có route login processing nằm ngoài `securityMatcher` của chain chứa form filter.

**Trang lỗi, matcher, proxy**

- [ ] ERROR/FORWARD dispatch có chính sách rõ, /error không biến lỗi 500 thành redirect loop.
- [ ] Thứ tự rule cụ thể trước catch-all, thứ tự chain được kiểm thử.
- [ ] API Basic/Bearer trả mã auth theo API contract, không vòng HTML login.
- [ ] Static assets public cần thiết, không cấp thêm quyền cho private resources.
- [ ] Scheme/host/port/context path qua reverse proxy đúng, chỉ tin forwarded headers hợp lệ.
- [ ] OIDC authorization endpoint và callback nằm trong đúng chain, state/nonce/PKCE bảo vệ.

**QA và quan sát**

- [ ] MockMvc test cả 302 entry point, GET login 200, failure URL 200, success và next-request 200.
- [ ] Test CSRF 403 riêng, không coi là password failure.
- [ ] Embedded server/browser tests cho ERROR dispatch, cookies/proxy, multi-chain và OIDC nếu dùng.
- [ ] Request/trace IDs, debug matcher logs có thể xem mà không lộ credentials/session IDs.
- [ ] Sau sửa không để /admin/private/API vô tình thành public.
- [ ] Cảnh báo/giám sát redirect cycles, login failures, 404 processing URL và context persistence.

**Kết luận:** Một vòng redirect cần được giải bằng **chuỗi HTTP cụ thể**, không bằng cảm tính. Spring Security redirect anonymous là bình thường, nhưng redirect **chính trang login**, **error dispatcher** hoặc **login-processing route** về login là dấu hiệu cần đọc matcher và chain. Nếu chỉ sau login mới quay về form, điều tra SecurityContext/cookie/session, success URL, MFA và proxy. Sửa đúng nguyên nhân, giữ authorization chặt và kiểm chứng bằng request nối tiếp để tránh biến một lỗi trải nghiệm thành lỗ hổng truy cập.

## Tài liệu tham khảo

- [Spring Security — Form Login](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/form.html)
- [Spring Security — Java Configuration, multiple HttpSecurity và filter chain endpoints](https://docs.spring.io/spring-security/reference/servlet/configuration/java.html)
- [Spring Security — Authorize HttpServletRequests, ERROR/FORWARD dispatch](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security — Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html)
- [Spring Security — Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html)
- [Spring Security — MockMvc Form Login](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/form-login.html)
- [Spring Security — OAuth2 Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html)
- [Spring Security — FormLoginConfigurer API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/annotation/web/configurers/FormLoginConfigurer.html)
- [Spring Boot — Spring MVC and error handling](https://docs.spring.io/spring-boot/reference/web/servlet.html)
- [OWASP — Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)
- [OWASP — Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)
