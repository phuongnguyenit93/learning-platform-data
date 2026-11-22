# AuthenticationException và AccessDeniedException trong Spring Security

> Phạm vi: Spring Security cho ứng dụng Servlet (Spring MVC), minh họa bằng Spring Boot 3.x / Spring Security 6.x và Java 17+. Đây là hai nhóm ngoại lệ bảo mật có ý nghĩa khác nhau: **xác thực danh tính** (authentication) và **kiểm tra quyền truy cập** (authorization).

## 1. Phân biệt hai câu hỏi bảo mật

Khi xử lý một yêu cầu, hệ thống thường cần trả lời lần lượt:

1. **Bạn là ai?** — Xác thực thông tin đăng nhập, token, phiên làm việc… để tạo đối tượng `Authentication` hợp lệ.
2. **Bạn được phép làm gì?** — Đối chiếu `Authentication`, `GrantedAuthority` và chính sách truy cập của tài nguyên hoặc phương thức.

`AuthenticationException` biểu thị trục trặc ở quá trình hoặc trạng thái **xác thực**. `AccessDeniedException` biểu thị **truy cập bị từ chối**, thường vì không đủ quyền; một số cơ chế khác như CSRF cũng dùng nhánh ngoại lệ này. Vì vậy, không thể chỉ nhìn tên ngoại lệ rồi khẳng định mã HTTP chắc chắn là 401 hay 403.

| Tiêu chí | `AuthenticationException` | `AccessDeniedException` |
| --- | --- | --- |
| Ý nghĩa chính | Không thể xác thực, hoặc bằng chứng xác thực không hợp lệ/không đủ | Chính sách bảo mật không cho phép yêu cầu |
| Lớp Java | `org.springframework.security.core.AuthenticationException` | `org.springframework.security.access.AccessDeniedException` |
| Kiểu lớp | Lớp trừu tượng kế thừa `RuntimeException` | Lớp cụ thể kế thừa `RuntimeException` |
| Ví dụ | Mật khẩu sai, token không hợp lệ, tài khoản bị khóa, thiếu thông tin xác thực cần thiết | Thiếu `ROLE_ADMIN`, không đạt điều kiện `@PreAuthorize`, CSRF token không hợp lệ |
| Xử lý ở servlet web | Có thể chuyển tới `AuthenticationEntryPoint` hoặc failure handler của cơ chế đăng nhập | `AccessDeniedHandler` nếu người dùng đã xác thực đủ mức; có thể chuyển sang `AuthenticationEntryPoint` nếu chưa xác thực đầy đủ |
| HTTP thường gặp | 401 đối với API dùng Basic/Bearer; form login có thể chuyển hướng | 403 khi đã xác thực nhưng không được phép |
| Hướng xử lý phía client | Cung cấp/sửa thông tin đăng nhập, đăng nhập lại hoặc lấy token hợp lệ | Kiểm tra quyền/scope hoặc điều kiện chính sách; không mặc nhiên thử lại cùng credential |

**Ví dụ trực quan:** Gọi `GET /admin`. Chưa gửi credential: hệ thống thường yêu cầu xác thực (401 với HTTP Basic). Đăng nhập thành công bằng tài khoản chỉ có `ROLE_USER`: hệ thống từ chối quyền (403). Đăng nhập bằng tài khoản có `ROLE_ADMIN`: yêu cầu được cho qua (200 nếu endpoint xử lý thành công).

## 2. AuthenticationException: lỗi liên quan đến xác thực

`AuthenticationException` là lớp cha trừu tượng cho các ngoại lệ khi đối tượng `Authentication` hoặc quá trình kiểm chứng không hợp lệ. Chúng thường xuất hiện từ `AuthenticationManager`, `AuthenticationProvider` hay các bộ lọc xác thực (Basic, form login, Bearer token…). Một vài ngoại lệ tiêu biểu:

| Ngoại lệ | Trường hợp điển hình |
| --- | --- |
| `BadCredentialsException` | Sai tên đăng nhập/mật khẩu hoặc bằng chứng xác thực không được chấp nhận |
| `UsernameNotFoundException` | Không tìm thấy người dùng khi tải thông tin tài khoản; có cấu hình cố ý che nguyên nhân thành lỗi credentials |
| `DisabledException`, `LockedException` | Tài khoản bị vô hiệu hóa hoặc bị khóa |
| `CredentialsExpiredException`, `AccountExpiredException` | Thông tin xác thực hoặc tài khoản hết hạn |
| `AuthenticationCredentialsNotFoundException` | Một thao tác cần đối tượng xác thực nhưng ngữ cảnh chưa có |
| `InsufficientAuthenticationException` | Mức xác thực hiện có chưa đủ để truy cập tài nguyên |
| `AuthenticationServiceException` | Sự cố của dịch vụ xác thực, khác với trường hợp người dùng đơn thuần nhập sai |

Không nên tự khởi tạo `new AuthenticationException(...)` vì lớp này là `abstract`. Khi viết `AuthenticationProvider` tùy chỉnh, sử dụng kiểu con phù hợp, ví dụ `BadCredentialsException` cho credential không được chấp nhận. Không trả thông tin quá chi tiết như “tài khoản tồn tại nhưng sai mật khẩu” trong thông báo gửi client vì có thể làm lộ thông tin người dùng.

`AuthenticationException` không đồng nghĩa với “người dùng chưa đăng nhập”: người dùng có thể đã gửi token nhưng token hết hạn, sai chữ ký, bị thu hồi hoặc chưa thỏa điều kiện xác thực; cách phản hồi phụ thuộc cơ chế đang sử dụng.

## 3. AccessDeniedException: truy cập không được phép

`AccessDeniedException` thường xuất hiện khi cơ chế authorization đánh giá yêu cầu và kết luận không đủ quyền. Với cách cấu hình phổ biến `authorizeHttpRequests`, `AuthorizationFilter` áp dụng các quy tắc `AuthorizationManager`; method security như `@PreAuthorize` cũng có thể từ chối trước khi phương thức được chạy.

Ví dụ:

- Quy tắc `.requestMatchers("/admin").hasRole("ADMIN")` yêu cầu quyền `ROLE_ADMIN`. `hasRole("ADMIN")` tự thêm tiền tố `ROLE_` theo quy ước mặc định; `hasAuthority("ROLE_ADMIN")` kiểm tra tên quyền chính xác.
- Người dùng có `ROLE_USER` đã được xác thực nhưng không có `ROLE_ADMIN` sẽ bị từ chối.
- Trong các phiên bản Spring Security 6.3+, `AuthorizationDeniedException` là một kiểu con của `AccessDeniedException`; ngoại lệ này có thể mang theo `AuthorizationResult`.
- `CsrfException` và các kiểu con như `MissingCsrfTokenException`, `InvalidCsrfTokenException` cũng thuộc nhánh `AccessDeniedException`. Đây là lỗi bảo vệ yêu cầu, không nhất thiết phản ánh thiếu role. `CsrfFilter` có thể tự gọi `AccessDeniedHandler`.

**Điểm dễ nhầm:** Một `AccessDeniedException` không chứng minh người gọi đã đăng nhập. Khi đối tượng hiện tại là anonymous, hoặc mức remember-me chưa đủ, Spring Security có thể quyết định **bắt đầu xác thực** thay vì trả ngay 403.

## 4. ExceptionTranslationFilter chuyển ngoại lệ thành hành vi HTTP như thế nào?

Trong một `SecurityFilterChain` của ứng dụng Servlet, `ExceptionTranslationFilter` làm cầu nối từ ngoại lệ bảo mật sang phản hồi web. Bản thân nó **không thực thi chính sách cấp quyền**; việc đó thuộc các thành phần như `AuthorizationFilter`, method security hoặc bộ lọc chuyên trách.

Luồng đơn giản hóa:

```text
Request
  -> SecurityFilterChain
      -> Authentication filters (Basic/Form/Bearer...)
      -> ExceptionTranslationFilter
          -> downstream filters / AuthorizationFilter / controller
              -> AuthenticationException
                   -> AuthenticationEntryPoint: yêu cầu xác thực
              -> AccessDeniedException
                   -> anonymous / remember-me chưa đủ?
                        -> AuthenticationEntryPoint
                   -> đã xác thực đủ mức?
                        -> AccessDeniedHandler: từ chối truy cập
              -> không có lỗi bảo mật
                   -> tiếp tục xử lý bình thường
```

Ba thành phần cần phân biệt:

- **`AuthenticationEntryPoint`**: bắt đầu một cơ chế xác thực. Ví dụ `BasicAuthenticationEntryPoint` phát 401 và header `WWW-Authenticate: Basic ...`; `LoginUrlAuthenticationEntryPoint` có thể chuyển hướng tới trang đăng nhập; Bearer token dùng entry point phù hợp chuẩn Bearer.
- **`AccessDeniedHandler`**: tạo phản hồi khi yêu cầu đã qua xác thực nhưng bị chặn; cách xử lý cơ bản thường là 403, hoặc chuyển đến trang access denied đã cấu hình.
- **`AuthenticationFailureHandler`**: xử lý thất bại của một luồng đăng nhập cụ thể, đặc biệt ở form login. Không phải mọi `AuthenticationException` đều đi qua `ExceptionTranslationFilter`: bộ lọc xác thực đứng trước nó có thể tự bắt lỗi và gọi failure handler/entry point.

Vì thế, công thức “`AuthenticationException` luôn là 401; `AccessDeniedException` luôn là 403” **không đúng**. Kết quả phụ thuộc trạng thái xác thực, loại yêu cầu, vị trí phát sinh lỗi trong chuỗi filter và handler đã cấu hình.

### 401, 403 và redirect: đọc đúng ý nghĩa

| Tình huống | Kết quả thường gặp |
| --- | --- |
| Gọi API HTTP Basic không có credential, trong khi endpoint yêu cầu đăng nhập | `401 Unauthorized`; kèm header thách thức `WWW-Authenticate` |
| Gửi sai mật khẩu qua HTTP Basic | `401 Unauthorized` do bộ lọc Basic xử lý thất bại |
| Đã xác thực nhưng thiếu quyền vào `/admin` | `403 Forbidden` |
| Anonymous gặp quy tắc yêu cầu `ROLE_ADMIN` | Thường bắt đầu xác thực, ví dụ 401 với HTTP Basic, không nhất thiết 403 |
| Form login thất bại | Chuyển hướng về trang đăng nhập kèm dấu hiệu lỗi hoặc phản hồi theo failure handler |
| Bearer token hết hạn/không hợp lệ | Thường 401 với Bearer challenge |
| Bearer token hợp lệ nhưng thiếu scope | Thường 403; có thể có thông tin `insufficient_scope` theo chuẩn Bearer |
| Yêu cầu POST bị chặn vì CSRF token sai/thiếu | Thường 403; có thể do `CsrfFilter` gọi handler trực tiếp |

HTTP 401 thường cần header `WWW-Authenticate` phù hợp lược đồ xác thực. Nếu tùy biến body JSON, đừng vô tình làm mất header hoặc hành vi cần thiết cho HTTP Basic/Bearer. Với form login dùng cookie/session, hành vi chuyển hướng là bình thường.

## 5. Ví dụ chạy được: hai tài khoản, một endpoint bảo vệ theo role

Ví dụ dưới đây là **một file Java hoàn chỉnh** cho dự án Spring Boot 3.x đã có `spring-boot-starter-web` và `spring-boot-starter-security`, dùng Java 17+. Lưu tại `src/main/java/demo/DemoApplication.java`.

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}

@Configuration
class SecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/public").permitAll()
                        .requestMatchers("/admin").hasRole("ADMIN")
                        .anyRequest().authenticated())
                .httpBasic(Customizer.withDefaults())
                .build();
    }

    @Bean
    UserDetailsService userDetailsService() {
        return new InMemoryUserDetailsManager(
                User.withUsername("member")
                        .password("{noop}demo")
                        .roles("USER")
                        .build(),
                User.withUsername("admin")
                        .password("{noop}demo")
                        .roles("ADMIN")
                        .build()
        );
    }
}

@RestController
class DemoController {
    @GetMapping("/public")
    String open() {
        return "public";
    }

    @GetMapping("/profile")
    String profile() {
        return "profile";
    }

    @GetMapping("/admin")
    String admin() {
        return "admin";
    }
}
```

Giải thích:

1. `/public` mở cho mọi người; `/profile` chỉ cần đã xác thực; `/admin` yêu cầu `ROLE_ADMIN`.
2. Spring Security tạo các authority `ROLE_USER` và `ROLE_ADMIN` tương ứng với `.roles("USER")` và `.roles("ADMIN")`.
3. `httpBasic` bật luồng xác thực dựa trên header `Authorization: Basic ...`.
4. `InMemoryUserDetailsManager` và tiền tố `{noop}` chỉ phục vụ minh họa; **không dùng mật khẩu rõ hoặc tài khoản hard-code trong production**. Trong thực tế sử dụng kho người dùng phù hợp và `PasswordEncoder` an toàn như BCrypt.

Chạy ứng dụng bằng tác vụ Boot của dự án, ví dụ:

```bash
./gradlew bootRun
```

Sau khi ứng dụng khởi động tại `http://localhost:8080`, kiểm chứng:

```bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/profile
curl -i -u member:wrong http://localhost:8080/profile
curl -i -u member:demo http://localhost:8080/profile
curl -i -u member:demo http://localhost:8080/admin
curl -i -u admin:demo http://localhost:8080/admin
```

| Lệnh | HTTP kỳ vọng | Nội dung khi thành công | Giải thích |
| --- | --- | --- | --- |
| `GET /public` (anonymous) | 200 | `public` | `permitAll` |
| `GET /profile` (anonymous) | 401 | — | Cần xác thực |
| `GET /profile` (sai password) | 401 | — | Xác thực thất bại |
| `GET /profile` (member:demo) | 200 | `profile` | Đã xác thực |
| `GET /admin` (member:demo) | 403 | — | Có danh tính nhưng thiếu `ROLE_ADMIN` |
| `GET /admin` (admin:demo) | 200 | `admin` | Đúng quyền |

Các mã ở bảng là kết quả kỳ vọng của cấu hình minh họa, không phải mã cố định của từng lớp ngoại lệ. Header và body thực tế có thể khác theo cấu hình hoặc phiên bản. Lệnh `curl -i` cho phép xem cả status và header; nên quan sát `WWW-Authenticate` ở phản hồi 401.

## 6. Tùy biến phản hồi lỗi cho REST API

Với REST API, thường cần body JSON nhất quán: `401` để client biết phải xác thực, `403` để client biết đã bị từ chối quyền. Cấu hình dưới đây là **đoạn thay thế phương thức `securityFilterChain`** trong `SecurityConfig` ở ví dụ trước; bổ sung import `AuthenticationEntryPoint` và `AccessDeniedHandler` từ `org.springframework.security.web` / `org.springframework.security.web.access`. Đây là đoạn cấu hình đặt trong lớp, **không phải chương trình Java độc lập**.

```java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
    AuthenticationEntryPoint unauthorized = (request, response, cause) -> {
        response.setStatus(401);
        response.setContentType("application/json;charset=UTF-8");
        response.setHeader("WWW-Authenticate", "Basic realm=\"demo\"");
        response.getWriter().write("{\"error\":\"unauthorized\"}");
    };

    AccessDeniedHandler forbidden = (request, response, cause) -> {
        response.setStatus(403);
        response.setContentType("application/json;charset=UTF-8");
        response.getWriter().write("{\"error\":\"forbidden\"}");
    };

    return http
            .authorizeHttpRequests(auth -> auth
                    .requestMatchers("/public").permitAll()
                    .requestMatchers("/admin").hasRole("ADMIN")
                    .anyRequest().authenticated())
            .httpBasic(basic -> basic.authenticationEntryPoint(unauthorized))
            .exceptionHandling(ex -> ex
                    .authenticationEntryPoint(unauthorized)
                    .accessDeniedHandler(forbidden))
            .build();
}
```

Các import cần thêm:

```java
import org.springframework.security.web.AuthenticationEntryPoint;
import org.springframework.security.web.access.AccessDeniedHandler;
```

- Cấu hình `exceptionHandling` xử lý các ngoại lệ đến đường `ExceptionTranslationFilter`. Cấu hình `httpBasic` riêng giúp lỗi mật khẩu sai do `BasicAuthenticationFilter` cũng trả body 401 mong muốn.
- `WWW-Authenticate: Basic realm="demo"` được giữ trong đáp ứng 401 để client nhận đúng challenge HTTP Basic. Nếu chuyển sang Bearer/JWT, phải sử dụng entry point/denied handler chuyên dụng cho Bearer và giữ chuẩn header liên quan; không tái dùng header Basic.
- Không phản hồi chi tiết nhạy cảm của `cause.getMessage()` ra client. Ghi log phía máy chủ có kiểm soát, phân biệt lỗi credential, lỗi cấu hình và lỗi authorization bằng thông tin phục vụ điều tra.
- Ví dụ dùng GET nên không cần tắt CSRF. **Đừng thêm `csrf.disable()` như cách “sửa nhanh” khi gặp 403**: trước hết xác định ứng dụng là API stateless thật sự hay có cookie/session và hiểu mô hình đe dọa CSRF.

## 7. Chẩn đoán lỗi theo thứ tự thực tế

1. **Xem status, redirect và header**: `401` có `WWW-Authenticate`? `302` có đưa tới login? `403` xuất hiện ở request nào? Không đoán loại ngoại lệ từ status một cách máy móc.
2. **Kiểm tra cơ chế xác thực**: client có gửi Authorization header/cookie/token đúng không; credential còn hiệu lực không; `AuthenticationProvider` có phù hợp kiểu token không?
3. **Kiểm tra danh tính và authority**: inspect thông tin `Authentication` trong môi trường debug an toàn; `hasRole("ADMIN")` cần `ROLE_ADMIN` chứ không chỉ `ADMIN`.
4. **Xem điểm áp dụng chính sách**: URL matcher và thứ tự các `requestMatchers`, `@PreAuthorize`, custom `AuthorizationManager`, method security. Một endpoint có thể vượt qua HTTP authorization nhưng vẫn bị chặn ở phương thức.
5. **Kiểm tra các nhánh chặn khác**: CSRF token trên POST/PUT/DELETE, CORS/preflight, nhiều `SecurityFilterChain` có `securityMatcher` khác nhau; đừng quy mọi 403 cho thiếu role.
6. **Xem bộ xử lý lỗi thực sự**: `AuthenticationEntryPoint`, `AuthenticationFailureHandler`, `AccessDeniedHandler`; filter nào phát hiện lỗi và có nằm phía sau `ExceptionTranslationFilter` hay không.
7. **Xác nhận bằng kiểm thử đối lập**: anonymous, sai credential, user đúng nhưng thiếu quyền, user đủ quyền; riêng endpoint thay đổi trạng thái cần kiểm thử CSRF theo thiết kế.

Lưu ý khi debug: `AnonymousAuthenticationToken` có thể là một `Authentication` hiện diện trong `SecurityContext`. Vì vậy chỉ kiểm tra `getAuthentication() != null` hoặc `isAuthenticated()` theo cách thô có thể dẫn tới kết luận sai về việc user đã đăng nhập; Spring Security sử dụng `AuthenticationTrustResolver` để phân biệt anonymous, remember-me và mức xác thực thích hợp.

## 8. Sai lầm phổ biến và cách sửa

- **Đồng nhất lỗi với status**: `AuthenticationException` không phải luôn 401 (form login có thể redirect); `AccessDeniedException` không phải luôn 403 (anonymous có thể bị yêu cầu đăng nhập). Hãy xem cơ chế xác thực và handler.
- **Đổi mọi 403 thành 401**: điều này che mất lỗi thiếu quyền thật sự. Đã xác thực nhưng thiếu scope/role thì 403 thường là tín hiệu phù hợp.
- **Dùng `@ControllerAdvice` làm nơi duy nhất bắt lỗi bảo mật**: nhiều lỗi bị chặn ngay trong filter chain, trước khi request vào Spring MVC; `@ExceptionHandler` trong controller không thay thế cấu hình security handler.
- **Ném `AccessDeniedException` để biểu diễn mọi lỗi nghiệp vụ**: một lỗi kiểm tra dữ liệu thông thường nên dùng loại lỗi domain/API tương ứng. Chỉ dùng ngoại lệ bảo mật khi chính sách bảo mật từ chối thao tác.
- **Dùng `new BadCredentialsException` để báo thiếu quyền**: sai tầng trách nhiệm. Kiểm tra role/permission nên nằm ở authorization và có thể phát sinh `AccessDeniedException`.
- **Tiết lộ nguyên nhân nhạy cảm**: không phản hồi tên tài khoản tồn tại, giá trị token, stack trace hoặc trạng thái khóa quá chi tiết cho client.
- **Tắt CSRF để “hết 403” mà chưa hiểu ngữ cảnh**: có thể làm yếu bảo vệ ứng dụng dùng cookie/session.

## 9. Bài tập tự kiểm tra

1. User chưa đăng nhập vào `/admin` với HTTP Basic: dự đoán status và vai trò của `AuthenticationEntryPoint`.
2. User đã đăng nhập, có `ROLE_USER` nhưng thiếu `ROLE_ADMIN`: xác định nhánh `AccessDeniedHandler` và giải thích vì sao không nên trả 401.
3. User đủ role nhưng gửi POST thiếu CSRF token trong ứng dụng có bật CSRF: vì sao vẫn có thể bị 403?
4. Form login sai mật khẩu trả redirect thay vì 401: bộ phận nào của luồng đăng nhập có thể quyết định hành vi này?
5. Ứng dụng có custom JSON cho `exceptionHandling` nhưng HTTP Basic sai mật khẩu vẫn có body khác: cần kiểm tra thêm cấu hình nào?

**Gợi ý đối chiếu:** (1) thường 401 và entry point mời xác thực; (2) 403 vì đã xác thực nhưng thiếu quyền; (3) bị chặn bởi cơ chế chống CSRF; (4) failure handler của form login; (5) entry point/failure handling tại `httpBasic`.

## Tài liệu chính thức

- [Spring Security — Servlet Architecture và ExceptionTranslationFilter](https://docs.spring.io/spring-security/reference/servlet/architecture.html)
- [Spring Security — ExceptionTranslationFilter API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/access/ExceptionTranslationFilter.html)
- [Spring Security — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html)
- [Spring Security — CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)
- [Spring Security — In-Memory Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/in-memory.html)