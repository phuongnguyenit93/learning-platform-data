# ExceptionTranslationFilter và chuyển lỗi bảo mật thành phản hồi HTTP

Trong Spring Security dành cho **Servlet**, `ExceptionTranslationFilter` là cầu nối giữa ngoại lệ bảo mật Java và cách ứng dụng trả lời HTTP. Nó giúp hệ thống phân biệt tình huống **cần yêu cầu người dùng xác thực** với tình huống **người dùng đã xác thực nhưng không đủ quyền**. Bài học thuộc nhóm *Xử lý từ chối* của module *Spring Security - authorization*.

## 1. Vị trí và trách nhiệm

Khi request đi qua `FilterChainProxy`, các bộ lọc xác thực xây dựng `Authentication` trong `SecurityContext`; `AnonymousAuthenticationFilter` có thể đặt một danh tính anonymous nếu chưa có xác thực. Ở đoạn sau của chuỗi, `ExceptionTranslationFilter` bao quanh lời gọi `FilterChain.doFilter(...)` để bắt các ngoại lệ bảo mật phát sinh ở phần xử lý phía sau, điển hình là `AuthorizationFilter`.

Luồng rút gọn (không liệt kê mọi filter):

~~~text
HTTP request
  -> bộ lọc xác thực (ví dụ BasicAuthenticationFilter)
  -> AnonymousAuthenticationFilter
  -> ExceptionTranslationFilter
       -> AuthorizationFilter / ứng dụng / method security
       <- có thể ném AuthenticationException hoặc AccessDeniedException
       -> AuthenticationEntryPoint hoặc AccessDeniedHandler
  -> HTTP response
~~~

`AuthorizationFilter` mới là thành phần kiểm tra quy tắc `authorizeHttpRequests` và từ chối truy cập khi không đủ quyền. `ExceptionTranslationFilter` **không tự kiểm tra role, không xác thực mật khẩu, không tạo token**; nó chọn cách xử lý sau khi ngoại lệ bảo mật được ném. Request hợp lệ và không có ngoại lệ sẽ tiếp tục bình thường.

**Giới hạn bắt lỗi:** filter chỉ bắt các ngoại lệ đi ngược qua lời gọi `doFilter` mà nó đang bao quanh. Lỗi đã được một filter đứng **trước** nó xử lý, ngoại lệ nghiệp vụ thông thường hoặc ngoại lệ đã bị nơi khác bắt sẽ không tự động được nó chuyển thành 401/403. Nếu response đã được commit, việc thay mã trạng thái có thể thất bại.

## 2. Hai loại ngoại lệ và hai điểm xử lý

- `AuthenticationException`: lỗi hoặc yêu cầu liên quan đến xác thực. Khi ngoại lệ này đi tới `ExceptionTranslationFilter`, filter khởi động quy trình yêu cầu xác thực qua `AuthenticationEntryPoint`.
- `AccessDeniedException`: truy cập bị từ chối bởi kiểm tra quyền. Filter xem trạng thái xác thực để chọn tiếp: tài khoản anonymous hoặc remember-me có thể cần xác thực đầy đủ qua `AuthenticationEntryPoint`; tài khoản đã xác thực đầy đủ nhưng thiếu quyền sẽ được giao cho `AccessDeniedHandler`.
- `AuthenticationEntryPoint.commence(request, response, exception)`: yêu cầu client xác thực, chẳng hạn trả 401 với `WWW-Authenticate`, hoặc chuyển hướng đến trang login.
- `AccessDeniedHandler.handle(request, response, exception)`: giải quyết yêu cầu đã bị từ chối, thường trả HTTP 403. `AccessDeniedHandlerImpl` là một triển khai thường dùng; có thể trả 403 trực tiếp hoặc forward đến trang lỗi được cấu hình.

Mã giả dưới đây chỉ mô tả **quyết định**, không phải mã Java độc lập:

~~~text
try:
    xử lý phần còn lại của chuỗi filter
catch AuthenticationException:
    bắt đầu xác thực bằng AuthenticationEntryPoint
catch AccessDeniedException:
    if anonymous hoặc remember-me:
        bắt đầu xác thực bằng AuthenticationEntryPoint
    else:
        giao cho AccessDeniedHandler
~~~

Không nên kiểm tra đơn giản `SecurityContextHolder.getContext().getAuthentication() != null` để kết luận đã đăng nhập: một request anonymous thường **vẫn có** đối tượng `AnonymousAuthenticationToken`. Spring Security dùng `AuthenticationTrustResolver` để phân biệt anonymous, remember-me và các trạng thái khác.

Khi bắt đầu xác thực từ `ExceptionTranslationFilter`, Spring Security làm sạch `SecurityContext`, gọi `RequestCache.saveRequest(...)` theo chiến lược đã chọn, rồi mới gọi `AuthenticationEntryPoint`. Request cache hữu ích cho giao diện đăng nhập vì có thể quay lại URL ban đầu; API do client chủ động gọi lại thường dùng `NullRequestCache`.

## 3. 401, 403 và 302 có ý nghĩa gì?

| Hoàn cảnh | Cách xử lý điển hình | HTTP thường thấy |
| --- | --- | --- |
| Client chưa đăng nhập, truy cập tài nguyên cần xác thực | `AccessDeniedException` -> entry point | 401 với HTTP Basic/Bearer; 302 khi dùng form login |
| Đã xác thực nhưng thiếu `ROLE_ADMIN` | `AccessDeniedException` -> access-denied handler | 403 |
| Ngoại lệ `AuthenticationException` đi tới filter | Entry point | Thường là 401 hoặc chuyển hướng |
| Session chỉ có remember-me, tài nguyên cần xác thực đầy đủ | Có thể bắt đầu xác thực lại | Phụ thuộc entry point |
| Request được cấp quyền | Tiếp tục controller | Do ứng dụng quyết định, ví dụ 200 |

**401 Unauthorized** trong ngữ nghĩa HTTP thường thể hiện cần cung cấp thông tin xác thực hợp lệ. Với HTTP Basic, phản hồi 401 nên kèm thử thách `WWW-Authenticate: Basic ...` để client biết cách xác thực. **403 Forbidden** thường thể hiện server đã hiểu request nhưng không cho phép thực hiện dù danh tính đã được xác lập. **302 Found** là kết quả chuyển hướng điển hình của entry point dùng form login; vì vậy không phải mọi lỗi bảo mật đều trả JSON hay luôn trả 401/403.

Phân biệt **loại ngoại lệ**, **điểm xử lý** và **HTTP status**. Không có ánh xạ bất biến “`AuthenticationException` = 401; `AccessDeniedException` = 403”: một `AccessDeniedException` của anonymous thường đi tới entry point, và status thực tế phụ thuộc entry point/handler được cấu hình.

## 4. Ví dụ chạy được với Spring Boot 3.x, Spring Security 6.x và Java 17+

Tạo ứng dụng Spring Boot Servlet có dependencies `spring-boot-starter-web` và `spring-boot-starter-security`. Trong `build.gradle` của dự án Spring Boot đã cấu hình plugin, cần ít nhất:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
}
~~~

Lưu mã sau tại `src/main/java/com/example/securitydemo/SecurityDemoApplication.java`:

~~~java
package com.example.securitydemo;

import jakarta.servlet.http.HttpServletResponse;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.AuthenticationEntryPoint;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.AccessDeniedHandler;
import org.springframework.security.web.savedrequest.NullRequestCache;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class SecurityDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(SecurityDemoApplication.class, args);
    }

    @GetMapping("/api/public")
    public String publicApi() {
        return "public";
    }

    @GetMapping("/api/admin")
    public String adminApi() {
        return "admin";
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        AuthenticationEntryPoint unauthorized = (request, response, error) -> {
            response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
            response.setHeader(HttpHeaders.WWW_AUTHENTICATE,
                    "Basic realm=\"demo\"");
            response.setContentType(MediaType.APPLICATION_JSON_VALUE);
            response.getWriter().write("{\"error\":\"unauthorized\"}");
        };

        AccessDeniedHandler forbidden = (request, response, error) -> {
            response.setStatus(HttpServletResponse.SC_FORBIDDEN);
            response.setContentType(MediaType.APPLICATION_JSON_VALUE);
            response.getWriter().write("{\"error\":\"forbidden\"}");
        };

        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/api/public").permitAll()
                        .requestMatchers("/api/admin").hasRole("ADMIN")
                        .anyRequest().authenticated())
                .httpBasic(basic -> basic.authenticationEntryPoint(unauthorized))
                .exceptionHandling(ex -> ex
                        .authenticationEntryPoint(unauthorized)
                        .accessDeniedHandler(forbidden))
                .requestCache(cache -> cache.requestCache(new NullRequestCache()))
                .build();
    }

    @Bean
    UserDetailsService users() {
        UserDetails normal = User.withUsername("user")
                .password("{noop}pw")
                .roles("USER")
                .build();
        UserDetails admin = User.withUsername("admin")
                .password("{noop}pw")
                .roles("ADMIN")
                .build();
        return new InMemoryUserDetailsManager(normal, admin);
    }
}
~~~

Ở đây `hasRole("ADMIN")` kiểm tra authority `ROLE_ADMIN`. Người dùng `user` chỉ có `ROLE_USER`; `admin` có `ROLE_ADMIN`. Hai handler cố tình trả JSON đơn giản để quan sát rõ nhánh xử lý. `{noop}` chỉ để minh họa với tài khoản trong bộ nhớ; ứng dụng thật cần `PasswordEncoder` và mật khẩu được băm an toàn. Basic Auth phải chạy qua **HTTPS** khi vận hành thực tế.

Cấu hình entry point được áp dụng ở **cả** `exceptionHandling` và `httpBasic`: request chưa xác thực bị `AuthorizationFilter` từ chối có thể đi qua `ExceptionTranslationFilter`; còn mật khẩu Basic sai thường được `BasicAuthenticationFilter` bắt và gọi entry point của chính nó trước khi tới filter dịch ngoại lệ. Thiếu cấu hình ở `httpBasic` có thể khiến hai nhánh trả nội dung khác nhau. `NullRequestCache` tránh lưu request ban đầu vào session trong ví dụ API này.

Không vô hiệu hóa CSRF trong ví dụ: các endpoint chỉ là GET. Khi bổ sung thao tác thay đổi trạng thái, cần đánh giá CSRF theo cách client xác thực, đặc biệt nếu trình duyệt tự gửi cookie hoặc Basic credentials.

### Chạy và kiểm chứng

Tại thư mục dự án Spring Boot chứa Gradle wrapper, chạy `./gradlew bootRun` (Windows: `gradlew.bat bootRun`), rồi gọi các lệnh sau:

~~~bash
curl -i http://localhost:8080/api/public
curl -i http://localhost:8080/api/admin
curl -i -u user:pw http://localhost:8080/api/admin
curl -i -u admin:pw http://localhost:8080/api/admin
curl -i -u admin:wrong http://localhost:8080/api/admin
~~~

Kết quả cần quan sát (chỉ trích các dòng liên quan, header khác có thể thay đổi):

| Lệnh theo thứ tự | Mã HTTP | Body dự kiến | Vì sao |
| --- | --- | --- | --- |
| Public, không credentials | 200 | `public` | `permitAll()` |
| Admin, không credentials | 401 | `{"error":"unauthorized"}` | Anonymous bị từ chối -> entry point |
| Admin, `user:pw` | 403 | `{"error":"forbidden"}` | Xác thực thành công, thiếu `ROLE_ADMIN` |
| Admin, `admin:pw` | 200 | `admin` | Đủ quyền |
| Admin, `admin:wrong` | 401 | `{"error":"unauthorized"}` | Basic authentication thất bại |

Đối với dòng 401, handler minh họa còn gửi header:

~~~http
WWW-Authenticate: Basic realm="demo"
~~~

Ví dụ có hai tình huống 401 **khác đường đi**: thiếu credentials bị xử lý qua `AuthorizationFilter -> ExceptionTranslationFilter -> AuthenticationEntryPoint`; sai mật khẩu bị xử lý ngay trong `BasicAuthenticationFilter -> AuthenticationEntryPoint`. Kết quả HTTP giống nhau không chứng minh cùng một filter đã bắt lỗi.

## 5. Áp dụng trong dự án thật

**Trả lỗi thống nhất cho REST API:** cấu hình `exceptionHandling(ex -> ex.authenticationEntryPoint(...).accessDeniedHandler(...))` trong `SecurityFilterChain` tương ứng. Viết response có mã HTTP đúng, `Content-Type` phù hợp và JSON theo hợp đồng API (ví dụ mã lỗi, thông điệp an toàn, correlation id). Không tiết lộ mật khẩu, nội dung token, stack trace hoặc chi tiết về quyền nội bộ. Đối với HTTP Basic, OAuth2 Resource Server hoặc cơ chế khác, phải giữ các header challenge/định dạng lỗi do giao thức yêu cầu.

**Nhiều SecurityFilterChain:** mỗi chain có `securityMatcher` và cấu hình exception handling riêng; request khớp chain nào sẽ dùng cấu hình chain đó. Nếu trang web dùng `formLogin` còn `/api/**` dùng API authentication, hãy thiết kế entry point theo phạm vi, tránh API trả 302 đến trang HTML login khi client đang chờ JSON.

**OAuth2 Bearer token:** trường hợp thiếu token hoặc không đủ scope có thể dẫn đến challenge `WWW-Authenticate: Bearer` và thông tin lỗi phù hợp. Token lỗi định dạng, hết hạn hoặc không hợp lệ thường được authentication filter tương ứng xử lý trước khi `ExceptionTranslationFilter` nhìn thấy. Không tự áp đặt JSON Basic từ ví dụ cho Resource Server.

**Method security:** một `@PreAuthorize` có thể ném `AccessDeniedException` trong lúc request vẫn đang đi qua đoạn filter được bao quanh; khi ngoại lệ được truyền ra ngoài, `ExceptionTranslationFilter` có thể xử lý nó. Nếu code MVC tự xử lý/đổi ngoại lệ trước khi nó thoát ra, kết quả phụ thuộc code đó. Đây không phải bộ xử lý ngoại lệ chung cho mọi tầng ứng dụng.

**Trang lỗi và forward:** `AccessDeniedHandlerImpl` có thể forward tới trang 403 đã cấu hình. Trang đích phải được cho phép truy cập đúng cách; với `AuthorizationFilter`, các lần dispatch như `FORWARD`/`ERROR` cũng có thể chịu kiểm tra quyền. Nếu quên cấu hình, dễ phát sinh vòng lỗi hoặc nhận 403 thứ cấp.

## 6. Chẩn đoán các lỗi phổ biến

1. **“Chưa đăng nhập mà thấy 403, không phải 401.”** Kiểm tra entry point có phải loại trả 403 (chẳng hạn một cấu hình pre-auth/custom) và xem request khớp `SecurityFilterChain` nào. Không suy từ status rằng Spring Security chọn sai nhánh.
2. **“Đã đăng nhập nhưng cứ bị 401.”** Kiểm tra authentication có thật sự hợp lệ ở request này không, context có được nạp không, cookie/token có đến server không, và remember-me có bị yêu cầu nâng cấp lên xác thực đầy đủ không.
3. **“Tôi cấu hình AccessDeniedHandler nhưng login sai không qua handler đó.”** Sai credentials là lỗi xác thực, thường do authentication filter xử lý và gọi entry point; `AccessDeniedHandler` dành cho từ chối quyền truy cập.
4. **“Ngoại lệ trong custom filter không được dịch.”** Kiểm tra vị trí filter: nếu chạy trước `ExceptionTranslationFilter`, ngoại lệ không nằm trong vùng `doFilter` mà filter này bắt. Đừng tùy tiện đổi thứ tự filter; chọn đúng cơ chế xử lý lỗi ở nơi phát sinh.
5. **“ControllerAdvice không bắt được lỗi security.”** Phần lớn request authorization xảy ra trong servlet security filter chain trước controller. Xử lý ở `SecurityFilterChain` trước, rồi mới xét những ngoại lệ thực sự thuộc MVC.
6. **“API nhận HTML/302 thay vì JSON/401.”** Có thể entry point hiện tại là form login hoặc chain của trang web. Đối chiếu `securityMatcher`, `exceptionHandling` và loại authentication.
7. **“Có quyền mà vẫn 403.”** Kiểm tra `ROLE_` prefix khi dùng `hasRole`, `GrantedAuthority` thực tế, thứ tự `requestMatchers`, method security và CSRF nếu request dùng POST/PUT/DELETE.

Để theo dõi chuỗi filter trong môi trường phát triển, có thể bật `logging.level.org.springframework.security=DEBUG` và kiểm tra log `DefaultSecurityFilterChain` khi khởi động. Dùng `TRACE` có chọn lọc, tránh đưa thông tin request nhạy cảm vào log vận hành.

## 7. Checklist nắm vững

- Chỉ ra **nơi từ chối quyền** (`AuthorizationFilter`/method security) và **nơi chuyển ngoại lệ thành phản hồi** (`ExceptionTranslationFilter`).
- Giải thích được vì sao `AccessDeniedException` của anonymous khác với `AccessDeniedException` của người dùng đã xác thực.
- Biết `AuthenticationEntryPoint` thường phục vụ yêu cầu xác thực còn `AccessDeniedHandler` xử lý thiếu quyền, nhưng HTTP status phụ thuộc implementation.
- Phân biệt 401 do thiếu credentials ở nhánh exception translation với 401 do authentication filter bắt lỗi ngay.
- Tự tái hiện 200/401/403, kiểm tra `WWW-Authenticate` và tránh cấu hình handler phá hợp đồng Basic/Bearer.

### Tham khảo chính thức

- Spring Security — Servlet Architecture / Handling Security Exceptions: https://docs.spring.io/spring-security/reference/servlet/architecture.html
- Spring Security — Authorize HttpServletRequests: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security — HTTP Basic: https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/basic.html
