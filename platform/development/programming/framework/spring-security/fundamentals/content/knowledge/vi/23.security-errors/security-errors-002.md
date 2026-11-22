# 401 Unauthorized, 403 Forbidden và chuyển hướng tới trang đăng nhập

## 1. Nhận diện đúng ba kết quả

Khi truy cập một tài nguyên được bảo vệ, cần phân biệt **xác thực (authentication)**, tức xác định người gửi yêu cầu là ai, với **phân quyền (authorization)**, tức xác định người đã biết danh tính có được thực hiện hành động hay không. Trong ứng dụng Spring Security dùng Servlet, ba kết quả dưới đây thường xuất hiện:

| Kết quả HTTP | Ý nghĩa đối với yêu cầu | Tình huống điển hình |
| --- | --- | --- |
| **401 Unauthorized** | Yêu cầu cần thông tin xác thực hợp lệ hoặc thông tin đã gửi không được chấp nhận. Tên chuẩn có chữ “Unauthorized”, nhưng vấn đề chủ yếu ở **authentication**. | Gọi REST API không gửi thông tin xác thực hoặc gửi Basic/Bearer token không hợp lệ. |
| **403 Forbidden** | Máy chủ hiểu yêu cầu nhưng từ chối thực hiện; rất thường gặp khi danh tính đã xác thực không có quyền phù hợp. | Người dùng có `ROLE_USER` gọi endpoint đòi `ROLE_ADMIN`; yêu cầu POST thiếu CSRF token hợp lệ cũng có thể trả 403. |
| **302 Found** kèm `Location: /login` | Máy chủ yêu cầu trình duyệt đi đến trang đăng nhập. Đây là **chuyển hướng HTTP**, không phải mã 401/403. | Người chưa đăng nhập mở trang web được bảo vệ khi ứng dụng dùng form login. |

**Không có quy tắc “chưa đăng nhập luôn trả 401, đã đăng nhập luôn trả 403”.** Cách bắt đầu xác thực phụ thuộc vào `AuthenticationEntryPoint` được cấu hình cho yêu cầu. Cùng một yêu cầu không có phiên đăng nhập có thể được chuyển hướng đến trang login ở phần giao diện web, nhưng nhận 401 ở REST API. Ngược lại, một số kiểm tra như CSRF có thể trả 403 dù sự cố không bắt nguồn từ thiếu vai trò.

Ví dụ cùng tài nguyên `/admin`:

- Trên **website dùng form login**: chưa đăng nhập → `302 Location: /login`; đã đăng nhập bằng tài khoản không có vai trò quản trị → thường là `403`; có vai trò quản trị → xử lý thành công.
- Trên **API dùng HTTP Basic**: chưa gửi credentials → `401` với header `WWW-Authenticate`; đã xác thực nhưng thiếu vai trò → `403`; có quyền → xử lý thành công.

## 2. Ai quyết định trả 401, 403 hay chuyển hướng?

Trong Spring Security Servlet, yêu cầu đi qua `FilterChainProxy` và một `SecurityFilterChain` phù hợp. Bộ lọc phân quyền, ví dụ `AuthorizationFilter`, có thể từ chối truy cập; `ExceptionTranslationFilter` chuyển các ngoại lệ bảo mật từ phía sau nó thành hành vi HTTP phù hợp.

Dòng xử lý khái quát:

1. **Yêu cầu đến** → chuỗi bộ lọc phù hợp được lựa chọn.
2. **Xác thực**: cơ chế như form login, HTTP Basic hoặc Bearer token nhận diện người dùng và thiết lập thông tin bảo mật khi hợp lệ.
3. **Phân quyền**: quy tắc `permitAll()`, `authenticated()`, `hasRole(...)`, `hasAuthority(...)`... quyết định truy cập có được phép.
4. Nếu xảy ra `AuthenticationException`, hoặc `AccessDeniedException` cần khởi động xác thực cho người chưa đăng nhập, `ExceptionTranslationFilter` gọi **`AuthenticationEntryPoint`**. Entry point có thể trả 401/challenge hoặc chuyển hướng đến trang login.
5. Nếu đã được nhận diện phù hợp nhưng thiếu quyền và xảy ra `AccessDeniedException`, bộ lọc gọi **`AccessDeniedHandler`**, mặc định thường trả 403.

`ExceptionTranslationFilter` **không tự xác thực hoặc cấp quyền**; nó nối ngoại lệ bảo mật với phản hồi HTTP. Các lỗi phát sinh trực tiếp trong bộ lọc đăng nhập hoặc bộ lọc CSRF có thể được xử lý bởi cơ chế riêng của bộ lọc đó, nên đừng giả định mọi lỗi đều đi qua đúng một đường ném ngoại lệ.

`AuthenticationEntryPoint` và `AccessDeniedHandler` làm hai việc khác nhau:

| Thành phần | Trả lời câu hỏi | Ví dụ hành vi |
| --- | --- | --- |
| `AuthenticationEntryPoint` | “Phải bắt đầu/tiếp tục xác thực thế nào?” | `LoginUrlAuthenticationEntryPoint` trả 302 đến `/login`; `BasicAuthenticationEntryPoint` trả 401 và HTTP Basic challenge. |
| `AccessDeniedHandler` | “Từ chối truy cập hiện tại thế nào?” | `AccessDeniedHandlerImpl` gửi 403; có thể cấu hình trang thông báo hoặc JSON tùy ứng dụng. |

Trạng thái `anonymous` trong Spring Security là một cơ chế đại diện người chưa đăng nhập; nó **không có nghĩa** người dùng đã được xác thực chỉ vì đối tượng `Authentication` có thể tồn tại trong `SecurityContext`. Khi `AccessDeniedException` xuất hiện với người dùng anonymous, luồng thường khởi động xác thực trước, không mặc định kết luận thiếu role và trả 403.

## 3. Vì sao website chuyển tới trang đăng nhập?

Với `formLogin(Customizer.withDefaults())`, Spring Security cung cấp trang login mặc định ở `GET /login` và xử lý thông tin đăng nhập tại `POST /login`. Khi người chưa đăng nhập yêu cầu một đường dẫn cần xác thực:

1. Trình duyệt gọi `GET /profile`.
2. Quy tắc `authenticated()` không thỏa; `LoginUrlAuthenticationEntryPoint` gửi phản hồi `302` có `Location` trỏ tới `/login`.
3. Trình duyệt tự theo chuyển hướng, gọi `GET /login` rồi nhận HTML trang đăng nhập (thường `200 OK`).
4. Người dùng gửi biểu mẫu `POST /login` với `username`, `password` và CSRF token hợp lệ.
5. Nếu đăng nhập thành công, Spring Security thường chuyển hướng về yêu cầu đã lưu trong `RequestCache`, hoặc URL mặc định nếu không có yêu cầu được lưu. Nếu đăng nhập sai, cấu hình mặc định chuyển hướng tới `/login?error`.

Vì thế, **trang login hiển thị 200 không có nghĩa yêu cầu `/profile` ban đầu đã thành công**. Mở tab Network của DevTools và xem cả chuỗi `302 → /login → 200`. Công cụ HTTP thường cho phép chọn có tự theo redirect hay không; `curl -i` mặc định hiển thị phản hồi 302 đầu tiên, còn `curl -L` sẽ theo redirect.

Khi đặt `formLogin(form -> form.loginPage("/sign-in"))`, chính ứng dụng phải cung cấp trang `GET /sign-in` và bảo đảm URL đăng nhập/asset được phép truy cập. Nếu quên `permitAll()` cho trang login tùy chỉnh, yêu cầu login có thể bị chuyển hướng lặp. Với form HTML có session/cookie, cần giữ CSRF protection và gửi CSRF token hợp lệ.

## 4. Thực hành: một ứng dụng phân biệt web và API

Ví dụ này dùng **Java 17+, Spring Boot 3.x, Spring Security 6.x (Servlet)**. Tạo dự án Gradle bằng Spring Initializr với hai dependency `Spring Web` và `Spring Security`, rồi đặt tệp `src/main/java/demo/SecurityStatusDemoApplication.java` như sau. Hai `SecurityFilterChain` được tách rõ để `/api/**` dùng HTTP Basic, còn trang web dùng form login. Mã là chương trình Spring Boot đầy đủ trong dự án có các dependency vừa nêu; không thể biên dịch chỉ bằng `javac` thuần khi thiếu thư viện Spring.

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpStatus;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.savedrequest.NullRequestCache;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@EnableWebSecurity
public class SecurityStatusDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(SecurityStatusDemoApplication.class, args);
    }

    @Bean
    @Order(1)
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public").permitAll()
                .requestMatchers("/api/admin").hasRole("ADMIN")
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults())
            .sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            )
            .requestCache(cache ->
                cache.requestCache(new NullRequestCache())
            );

        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain webSecurity(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .requestMatchers("/admin").hasRole("ADMIN")
                .anyRequest().authenticated()
            )
            .formLogin(Customizer.withDefaults());

        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoder.encode("demo-pass"))
                .roles("USER")
                .build(),
            User.withUsername("admin")
                .password(encoder.encode("admin-pass"))
                .roles("ADMIN")
                .build()
        );
    }

    @RestController
    public static class Endpoints {
        @GetMapping("/public")
        public String publicWeb() {
            return "public-web";
        }

        @GetMapping("/profile")
        public String profile() {
            return "profile";
        }

        @GetMapping("/admin")
        public String adminWeb() {
            return "admin-web";
        }

        @GetMapping("/api/public")
        public String publicApi() {
            return "public-api";
        }

        @GetMapping("/api/admin")
        public String adminApi() {
            return "admin-api";
        }
    }
}
```

**Giải thích các điểm quan trọng:**

- `@Order(1)` giúp chuỗi API được xét trước. `securityMatcher("/api/**")` xác định **phạm vi áp dụng của cả chuỗi**; `requestMatchers(...)` bên trong chỉ xác định **quyền truy cập** sau khi chuỗi đã được chọn. Chuỗi web sau đó xử lý các URL còn lại.
- `httpBasic(...)` sử dụng thử thách HTTP Basic để yêu cầu credentials; trong ví dụ, API không kích hoạt form login. `SessionCreationPolicy.STATELESS` và `NullRequestCache` tránh lưu phiên/yêu cầu trước đó cho luồng API của ví dụ.
- `formLogin(...)` bật trang đăng nhập mặc định cho luồng web. Chương trình **không** tắt CSRF toàn cục.
- `hasRole("ADMIN")` đòi authority `ROLE_ADMIN`; `roles("ADMIN")` tạo đúng authority đó. Dùng `hasAuthority("ADMIN")` sẽ là phép kiểm tra khác và không tự thêm tiền tố `ROLE_`.
- Tài khoản in-memory `alice/demo-pass` và `admin/admin-pass` chỉ dành cho thử nghiệm cục bộ. Mật khẩu được mã hóa khi khởi động nhờ `DelegatingPasswordEncoder`; ứng dụng thực tế phải quản lý tài khoản và bí mật an toàn, chỉ truyền HTTP Basic qua HTTPS.

Chạy dự án đã có Gradle Wrapper:

```bash
./gradlew bootRun
# Windows PowerShell: .\gradlew.bat bootRun
```

Kiểm tra API bằng terminal khác; các kết quả bên phải là **mã HTTP và phần body/header liên quan**, không phải toàn bộ output của `curl`:

```bash
curl -i http://localhost:8080/api/public
# 200 OK; body: public-api

curl -i http://localhost:8080/api/admin
# 401 Unauthorized; WWW-Authenticate: Basic ...

curl -i -u alice:demo-pass http://localhost:8080/api/admin
# 403 Forbidden

curl -i -u admin:admin-pass http://localhost:8080/api/admin
# 200 OK; body: admin-api

curl -i http://localhost:8080/profile
# 302 Found; Location trỏ tới /login
```

Không giả định toàn bộ header, ngày tháng, cookie hay nội dung trang lỗi luôn giống nhau giữa các phiên bản và môi trường; điều cần kiểm chứng là **status**, `Location`/`WWW-Authenticate` khi tương ứng và body của endpoint khi truy cập thành công.

Sau đó mở trình duyệt mới hoặc cửa sổ riêng tư:

1. Truy cập `http://localhost:8080/profile` khi chưa đăng nhập → được chuyển sang trang login.
2. Đăng nhập `alice / demo-pass` → được đưa tới trang cần truy cập (thường `/profile`), thấy `profile`.
3. Mở `/admin` trong cùng phiên → `403` vì `alice` chỉ có `ROLE_USER`.
4. Đăng xuất hoặc dùng phiên trình duyệt mới, đăng nhập `admin / admin-pass` → `/admin` trả nội dung `admin-web`.

Bảng kết quả mong đợi:

| Yêu cầu | Ngữ cảnh | Kết quả chính |
| --- | --- | --- |
| `GET /api/public` | Không gửi credentials | 200 |
| `GET /api/admin` | Không gửi credentials | 401 + Basic challenge |
| `GET /api/admin` | `alice` hợp lệ, thiếu quyền | 403 |
| `GET /api/admin` | `admin` hợp lệ, đủ quyền | 200 |
| `GET /profile` | Chưa có phiên web | 302 tới `/login` |
| `GET /admin` | Phiên web của `alice` | 403 |
| `GET /admin` | Phiên web của `admin` | 200 |

## 5. REST API, Bearer token và hành vi của frontend

REST API thường muốn trả **trạng thái có thể xử lý bằng mã** thay vì redirect HTML. Với OAuth2 Resource Server/Bearer token, cách diễn giải điển hình là:

- Token thiếu, hết hạn, sai chữ ký hoặc không dùng được → **401**, thường có `WWW-Authenticate: Bearer`; phản hồi có thể chứa thông tin lỗi như `invalid_token` theo cấu hình và chuẩn áp dụng.
- Token hợp lệ nhưng thiếu scope/quyền yêu cầu → **403**, có thể kèm Bearer challenge mang `insufficient_scope`.
- Token hợp lệ, có đủ quyền → tiếp tục đến controller.

Ở client, nên xử lý phân biệt: **401** → yêu cầu xác thực lại/làm mới token theo cơ chế được thiết kế; **403** → hiển thị thông báo thiếu quyền và không tự động đăng nhập lại vô hạn; **302** → xem nó có chủ đích trong luồng web hay là dấu hiệu API bị cấu hình sai entry point. Với `fetch`/XHR, một redirect HTML có thể dẫn đến việc client nhận trang login thay vì JSON mong đợi. Đừng suy luận rằng mọi 403 có thể sửa bằng refresh token.

Nếu cả UI và API chạy trong một ứng dụng, cấu hình entry point theo **chuỗi, matcher và phương thức xác thực**. Không dùng một quy tắc “mọi yêu cầu chưa xác thực → /login” cho API JSON nếu client đòi 401. Khi tự viết entry point trả 401 cho Basic/Bearer, phải cân nhắc challenge `WWW-Authenticate` tương ứng; chỉ gửi mã 401 trống có thể không đáp ứng mong đợi của giao thức/client.

## 6. Phân biệt lỗi phân quyền với CSRF và đăng nhập thất bại

**403 không nhất thiết là thiếu vai trò.** Trong ứng dụng Servlet sử dụng session/cookie, Spring Security bật bảo vệ CSRF mặc định cho các phương thức thay đổi trạng thái (như POST/PUT/DELETE, tùy cấu hình). Thiếu hoặc sai CSRF token có thể bị `CsrfFilter` từ chối **403** trước khi controller được gọi, kể cả khi tài khoản có đủ role. Trang login mặc định xử lý token giúp bạn; khi tự tạo HTML form, cần cung cấp token theo cơ chế Spring Security.

Một số tình huống dễ nhầm:

| Hiện tượng | Nguyên nhân cần kiểm tra |
| --- | --- |
| Gọi `POST /submit` bị 403, nhưng `GET` cùng tài nguyên hoạt động | Thiếu/sai CSRF token; đừng vô hiệu hóa CSRF trên toàn ứng dụng chỉ để “sửa 403”. |
| Đăng nhập form sai, bị quay về `/login?error` | `AuthenticationFailureHandler` xử lý đăng nhập thất bại; đây không đồng nghĩa controller đã trả 401. |
| Gọi `/admin` khi đã đăng nhập vẫn bị 403 | Authority thực tế có `ROLE_ADMIN` chưa? `hasRole`/`hasAuthority` có đang dùng đúng tiền tố? |
| API trả HTML trang login hoặc 302 thay vì 401 JSON/challenge | Kiểm tra `SecurityFilterChain` nào bắt URL và entry point được cấu hình. |
| Trình duyệt nhận 200 sau khi “đi tới trang bị bảo vệ” | Xem chuỗi redirect trong Network; 200 có thể là trang `/login`, không phải trang ban đầu. |
| Redirect nhiều lần giữa các URL login | Kiểm tra URL login tùy chỉnh đã mở truy cập, có tồn tại controller/view và các matcher không chặn chính nó. |
| Sau đăng nhập vẫn không quay về URL ban đầu | Kiểm tra `RequestCache`, session, success handler, `defaultSuccessUrl(..., true)` hoặc cấu hình stateless. |

Lỗi do bảo vệ CSRF cần sửa bằng cách gửi token đúng và xác định mô hình xác thực phù hợp. Chỉ cân nhắc loại trừ CSRF cho endpoint thực sự không phụ thuộc credential tự động của trình duyệt (ví dụ bearer API stateless được thiết kế đúng), sau khi đánh giá rủi ro; **HTTP Basic trong trình duyệt vẫn có nguy cơ CSRF vì trình duyệt có thể tự gửi credentials**.

## 7. Cách chẩn đoán theo thứ tự

1. **Ghi nhận yêu cầu thực tế**: method, URL, header `Accept`, `Authorization`, cookie/session, HTTP status, `Location` và `WWW-Authenticate`. Với redirect, kiểm tra phản hồi đầu tiên trước khi client tự theo liên kết.
2. **Xác định chuỗi bảo mật đang xử lý**: so sánh `securityMatcher`, `@Order` và phạm vi `requestMatchers`. Một URL đi nhầm chuỗi có thể nhận cơ chế login khác mong đợi.
3. **Xác định danh tính**: anonymous, Basic username, Bearer principal hay phiên form login? Dữ liệu xác thực có hợp lệ và còn hiệu lực không?
4. **Xác định quyền**: endpoint cần `authenticated()`, role, authority, scope hay kiểm tra method-level (`@PreAuthorize`)? Kiểm tra giá trị authority thực tế, không chỉ tên role trên giao diện.
5. **Xác định bộ lọc từ chối**: thiếu quyền, CSRF, đăng nhập thất bại hay xử lý tùy chỉnh? Với POST/PUT/DELETE, kiểm tra CSRF token trước khi kết luận là lỗi role.
6. **Xác nhận phản hồi phù hợp hợp đồng client**: browser có thể dùng 302 tới form login; API nên dùng 401/challenge khi chưa xác thực và 403 khi thiếu quyền, theo cơ chế đã thiết kế.

Có thể bật log chẩn đoán bảo mật ở mức phù hợp trong môi trường phát triển để hiểu matcher và quyết định phân quyền, nhưng tránh ghi credentials, Bearer token hoặc cookie nhạy cảm vào log; tắt log chi tiết ở production sau khi xử lý.

### Quy tắc ghi nhớ

- **Authentication**: “Bạn là ai?” → chưa/không xác thực được thì yêu cầu xác thực, thường **401** cho API hoặc **302 tới login** cho web dùng form.
- **Authorization**: “Bạn có quyền làm việc này không?” → đã xác thực nhưng thiếu quyền thì thường **403**.
- **Redirect**: **302 + Location** là cách trình duyệt được dẫn tới bước đăng nhập; sau redirect có thể nhận 200 ở trang login.
- **Spring Security quyết định bằng cấu hình filter chain, entry point, access-denied handler và các bộ lọc liên quan**; status HTTP là kết quả của luồng đó, không phải chỉ của một dòng `hasRole(...)`.

### Tài liệu chính thức

- [Spring Security — Security Filters và ExceptionTranslationFilter](https://docs.spring.io/spring-security/reference/servlet/architecture.html)
- [Spring Security — Multiple SecurityFilterChain và securityMatcher](https://docs.spring.io/spring-security/reference/servlet/configuration/java.html)
- [Spring Security — Form Login](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/form.html)
- [Spring Security — CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)
