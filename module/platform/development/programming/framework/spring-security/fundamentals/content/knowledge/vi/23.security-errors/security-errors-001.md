# Phân biệt chưa xác thực, xác thực sai và không đủ quyền trong Spring Security

> **Phạm vi:** Spring Security trên ứng dụng HTTP, với ví dụ Java 17+, Spring Boot 3.x và Spring Security 6.x (Servlet stack). Mã trạng thái cụ thể tùy cơ chế HTTP Basic, form login, Bearer token và cấu hình ứng dụng.

## 1. Phân biệt ba tình huống

**Authentication (xác thực)** trả lời “Người gửi request là ai và bằng chứng danh tính có hợp lệ không?”. **Authorization (phân quyền)** trả lời “Danh tính đó có được thực hiện thao tác này trên tài nguyên này không?”.

| Tình huống | Thực chất | Ví dụ | Phản hồi thường gặp với API HTTP Basic/Bearer |
| --- | --- | --- | --- |
| **Chưa xác thực** (*unauthenticated*) | Chưa có danh tính đã được xác thực hợp lệ cho request hiện tại. Client có thể chưa cung cấp credentials hoặc session đăng nhập đã hết hạn. | Gọi `GET /api/account` không có `Authorization` hoặc session. | **401 Unauthorized**, khởi động việc xác thực. |
| **Xác thực sai/thất bại** (*authentication failed*) | Đã thử xác thực nhưng thông tin không được chấp nhận; chưa tạo được danh tính đáng tin cậy. | Sai mật khẩu, Bearer token hết hạn/chữ ký không hợp lệ, tài khoản bị khóa. | Thường **401 Unauthorized**; form login có thể chuyển hướng về trang đăng nhập báo lỗi. |
| **Không đủ quyền** (*authenticated but forbidden*) | Đã xác thực thành công nhưng quyền/role/scope hoặc chính sách truy cập không cho phép thao tác. | Người dùng có `ROLE_USER` truy cập endpoint yêu cầu `ROLE_ADMIN`. | Thường **403 Forbidden**. |

**Lưu ý trọng tâm:** “Chưa xác thực” và “xác thực thất bại” có thể cùng nhận **401**, nhưng khác nhau ở chỗ client **chưa gửi bằng chứng** hay **đã gửi bằng chứng không hợp lệ**. “Không đủ quyền” là chuyện của bước **authorization**, thường xảy ra sau khi authentication đã thành công. **Không thể suy ra nguyên nhân chính xác chỉ từ mã HTTP**.

### 1.1. Hiểu đúng 401, 403 và chuyển hướng đăng nhập

- **401 Unauthorized**: tên HTTP truyền thống có chữ “Unauthorized”, nhưng ý nghĩa thực tế là **thiếu thông tin xác thực hợp lệ** cho tài nguyên yêu cầu xác thực. HTTP Basic/Bearer thường trả thêm `WWW-Authenticate` để cho client biết cơ chế xác thực cần dùng.
- **403 Forbidden**: server từ chối thực hiện request. Trường hợp phổ biến là user đã đăng nhập nhưng thiếu role/scope. Tuy nhiên **403 không tự động chứng minh thiếu role**: bảo vệ CSRF, `denyAll()` hoặc chính sách khác cũng có thể tạo 403.
- **302 Found** hoặc một redirect tương đương: với website dùng form login, người chưa đăng nhập thường được chuyển tới `/login`, còn đăng nhập sai thường được chuyển tới `/login?error`. Sau khi browser theo redirect, trang cuối có thể trả 200 nên phải xem từng request trong Network tab.
- **200 OK**: endpoint được phép và xử lý thành công; endpoint công khai có thể trả 200 ngay cả khi chưa đăng nhập.

Ví dụ `GET /admin` không có credentials và `GET /admin` với token sai đều có thể là 401 ở API. `GET /admin` bằng tài khoản hợp lệ chỉ có role USER thường là 403. Không nên đồng nhất “đăng nhập sai” với “không đủ quyền”.

## 2. Các thành phần Spring Security tham gia xử lý

Trong **Servlet SecurityFilterChain**, luồng điển hình gồm:

1. **Authentication filter** như `BasicAuthenticationFilter`, `UsernamePasswordAuthenticationFilter` hoặc `BearerTokenAuthenticationFilter` lấy credentials từ request, gọi `AuthenticationManager`/`AuthenticationProvider` để xác thực.
2. Khi xác thực thành công, đối tượng `Authentication` chứa principal và authorities được đưa vào `SecurityContext`.
3. Nếu chưa đăng nhập, `AnonymousAuthenticationFilter` có thể thêm một **`AnonymousAuthenticationToken`** đại diện cho khách. Vì vậy **`Authentication != null` không đồng nghĩa người dùng đã xác thực thực sự**.
4. **`AuthorizationFilter`** áp dụng các rule như `authenticated()`, `hasRole(...)`, `hasAuthority(...)`; khi truy cập bị từ chối, thường phát sinh `AccessDeniedException`.
5. **`ExceptionTranslationFilter`** xử lý `AuthenticationException` và `AccessDeniedException` phát sinh ở phần filter chain phía sau nó:
   - Chưa xác thực/anonymous hoặc gặp `AuthenticationException`: gọi **`AuthenticationEntryPoint`** để khởi động xác thực, thường là 401 hoặc redirect login.
   - Đã xác thực nhưng gặp `AccessDeniedException`: gọi **`AccessDeniedHandler`**, thường trả 403.

Sơ đồ khái niệm:

```text
HTTP request
  |
  v
Authentication filter (khi có credentials)
  |-- thông tin sai --> authentication failure handler / entry point
  |                     (Basic/Bearer thường 401; form thường redirect)
  v
SecurityContext (đã xác thực hoặc anonymous)
  |
  v
AuthorizationFilter kiểm tra rule
  |-- cho phép ----------------------> Endpoint
  |
  +-- từ chối --> ExceptionTranslationFilter
                    |-- anonymous/chưa xác thực --> AuthenticationEntryPoint
                    |                               (thường 401 hoặc redirect)
                    +-- đã xác thực -------------> AccessDeniedHandler
                                                    (thường 403)
```

**Nuance quan trọng:** Authentication filter thường tự xử lý lỗi xác thực ngay tại filter. Chẳng hạn `UsernamePasswordAuthenticationFilter` sử dụng `AuthenticationFailureHandler`, còn HTTP Basic có thể trực tiếp gọi `AuthenticationEntryPoint`. Vì vậy nói “mọi lỗi mật khẩu đều được `ExceptionTranslationFilter` bắt” là không chính xác. Filter này chủ yếu chuyển các ngoại lệ bảo mật được truyền tới nó từ bước xử lý phía sau thành phản hồi thích hợp.

### 2.1. Ngoại lệ và dấu hiệu chẩn đoán

| Exception hoặc cơ chế | Ý nghĩa thường gặp | Nhánh cần xem |
| --- | --- | --- |
| `BadCredentialsException` | Credentials không được chấp nhận. | Authentication thất bại; thường 401 trên API. |
| `UsernameNotFoundException`, `LockedException`, `DisabledException`, `CredentialsExpiredException` | Các tình trạng có thể làm xác thực thất bại; một số provider cố tình che lý do cụ thể. | Authentication; không tiết lộ chi tiết account cho client. |
| `InvalidBearerTokenException` | Token không hợp lệ/không còn được chấp nhận. | Authentication bằng Bearer; thường 401. |
| `AccessDeniedException` | Quy tắc bảo vệ tài nguyên không cho phép truy cập. | Kiểm tra anonymous hay đã xác thực, rồi xem rule/policy. |
| Lỗi CSRF token | Request thay đổi trạng thái không có CSRF token hợp lệ. | Có thể trả 403 dù không thiếu role. |

**Không đặt một handler chung luôn trả 403 cho mọi `AuthenticationException` và `AccessDeniedException`**: điều đó khiến client không phân biệt khi nào cần xác thực và khi nào cần quyền truy cập.

## 3. Ví dụ Java 17+ quan sát trực tiếp 401 và 403

Dùng một ứng dụng Spring Boot 3.x có plugin Java/Boot tương thích. Dependency Gradle cần có (thêm vào khối `dependencies` của dự án):

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Tạo tệp `src/main/java/demo/security/SecurityStatusDemoApplication.java`:

```java
package demo.security;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
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
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class SecurityStatusDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(SecurityStatusDemoApplication.class, args);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public").permitAll()
                .requestMatchers("/api/admin").hasRole("ADMIN")
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(AbstractHttpConfigurer::disable);

        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails reader = User.withUsername("reader")
            .password(encoder.encode("reader123"))
            .roles("USER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("admin123"))
            .roles("ADMIN")
            .build();

        return new InMemoryUserDetailsManager(reader, admin);
    }
}

@RestController
class DemoController {
    @GetMapping("/api/public")
    String publicEndpoint() {
        return "public";
    }

    @GetMapping("/api/account")
    String accountEndpoint() {
        return "account";
    }

    @GetMapping("/api/admin")
    String adminEndpoint() {
        return "admin";
    }
}
```

Ở đây `httpBasic()` bật xác thực HTTP Basic; `formLogin(...disable)` ngăn redirect form login che khuất status API. `hasRole("ADMIN")` đòi granted authority **`ROLE_ADMIN`**; `User.roles("ADMIN")` tự tạo authority đó. Reader chỉ có `ROLE_USER`, admin có `ROLE_ADMIN`. `BCryptPasswordEncoder` mã hóa mật khẩu khi tạo user; tài khoản cố định này **chỉ dùng để học**, không hard-code vào ứng dụng thật.

Chạy ứng dụng (từ dự án Boot đã cấu hình các plugin và phiên bản):

```bash
./gradlew bootRun
```

Trên Windows dùng `gradlew.bat bootRun`. Sau khi ứng dụng chạy ở `localhost:8080`, mở terminal Bash có `curl`, lần lượt gọi:

```bash
# (1) Không có credentials
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8080/api/account

# (2) Có credentials nhưng sai mật khẩu
curl -s -o /dev/null -w '%{http_code}\n' -u reader:wrong http://localhost:8080/api/account

# (3) Xác thực reader thành công, nhưng thiếu ROLE_ADMIN
curl -s -o /dev/null -w '%{http_code}\n' -u reader:reader123 http://localhost:8080/api/admin

# (4) Admin có đúng ROLE_ADMIN
curl -s -o /dev/null -w '%{http_code}\n' -u admin:admin123 http://localhost:8080/api/admin

# (5) Endpoint công khai
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8080/api/public
```

Kết quả dự kiến, mỗi lệnh in một dòng mã trạng thái:

```text
401
401
403
200
200
```

**Giải thích:** (1) chưa thử xác thực; (2) thử rồi nhưng sai; cả hai không có danh tính hợp lệ nên 401. (3) đã xác thực được reader nhưng thiếu role nên 403. (4) đã có role đúng nên vào endpoint; (5) `permitAll()` nên không cần đăng nhập.

Xem đầy đủ header bằng `curl -i http://localhost:8080/api/account`; trên HTTP Basic, phản hồi 401 thường có `WWW-Authenticate: Basic ...`. Header thực tế tùy cấu hình/client. Các request trong ví dụ đều dùng `GET`, nên không phải vô hiệu hóa CSRF; khi thêm request thay đổi trạng thái qua cookie/session phải xử lý CSRF đúng cách.

## 4. Vì sao cơ chế xác thực thay đổi kết quả?

### 4.1. HTTP Basic và API

- Không gửi credentials vào tài nguyên yêu cầu login → thường **401**.
- Gửi username/password sai → thường **401**, do authentication thất bại trước khi có principal hợp lệ.
- Username/password đúng nhưng chỉ có `ROLE_USER`, endpoint yêu cầu `ROLE_ADMIN` → thường **403**.
- HTTP Basic gửi lại credentials theo request; **bắt buộc dùng HTTPS** trong hệ thống thật.

### 4.2. Form login trên website

1. Browser truy cập trang riêng khi chưa đăng nhập. `LoginUrlAuthenticationEntryPoint` thường chuyển browser đến `/login` (HTTP redirect).
2. Người dùng nộp form sai. `UsernamePasswordAuthenticationFilter` gọi `AuthenticationFailureHandler`; cấu hình mặc định thường chuyển đến `/login?error`.
3. Đăng nhập thành công nhưng thiếu role: `AccessDeniedHandler` thường trả 403 hoặc hiển thị trang từ chối truy cập.

Vì thế **không áp dụng máy móc “chưa đăng nhập = 401” cho form login**. Một redirect có thể là hành vi mong đợi. Trong DevTools, xem cả status của request gốc, URL `Location` và response cuối sau redirect.

### 4.3. OAuth2 Resource Server với Bearer token

| Đầu vào | Kết quả xác thực | Phản hồi thường gặp |
| --- | --- | --- |
| Không có Bearer token đến endpoint bảo vệ | Chưa xác thực | **401**; có thể có `WWW-Authenticate: Bearer`. |
| Token hết hạn, chữ ký sai hoặc bị từ chối | Xác thực thất bại | **401**, thường có Bearer error `invalid_token`. |
| Token hợp lệ nhưng thiếu scope/authority cần thiết | Xác thực xong nhưng thiếu quyền | **403**, có thể kèm `insufficient_scope` trong Bearer challenge. |
| Token hợp lệ, đủ scope/authority | Được phép tiếp tục | Endpoint trả trạng thái theo kết quả xử lý. |

Header `WWW-Authenticate` chi tiết tùy `BearerTokenAuthenticationEntryPoint`, `BearerTokenAccessDeniedHandler` và cấu hình Resource Server. **JWT hợp lệ không có nghĩa được phép gọi mọi API**: authentication chỉ chứng minh danh tính; authorization còn phải kiểm tra scope/authority.

## 5. Các lỗi chẩn đoán thường gặp và cách xử lý

**Lỗi 1 — kiểm tra sai trạng thái anonymous.** `AnonymousAuthenticationToken` có thể tồn tại trong `SecurityContext`, thậm chí `isAuthenticated()` trả true. Kiểm tra mỗi `authentication != null` hoặc mỗi `isAuthenticated()` có thể phân loại nhầm anonymous thành người dùng đã đăng nhập. Khi tùy biến, dùng cơ chế đáng tin cậy như `AuthenticationTrustResolver`/các authorization rule của Spring Security.

**Lỗi 2 — nhầm `hasRole` với `hasAuthority`.** `hasRole("ADMIN")` theo mặc định khớp `ROLE_ADMIN`; `hasAuthority("ADMIN")` khớp đúng `ADMIN`. Nếu provider cấp authority khác kỳ vọng, đã đăng nhập vẫn trả 403. Bearer JWT thường ánh xạ scope thành authorities như `SCOPE_reports.read`; đừng nhầm với role.

**Lỗi 3 — mọi 403 đều bị quy cho role.** Nếu `GET` hoạt động nhưng `POST` cùng tài nguyên trả 403, kiểm tra CSRF token, HTTP method matcher và method security. Không tắt CSRF vô điều kiện để “sửa lỗi”; cần hiểu ứng dụng dùng cookie/session hay token ở header và mô hình tấn công CSRF.

**Lỗi 4 — luôn đổi 401 thành 403 hoặc ngược lại.** Client nhận 401 của API thường có thể yêu cầu đăng nhập/gửi credentials hợp lệ; nhận 403 do role thì đăng nhập lại bằng cùng quyền không giúp gì. Việc quy đổi làm giao diện lặp login/refresh token và che lỗi cấu hình.

**Lỗi 5 — chỉ xem status của trang cuối sau redirect.** Form login tạo các request nối tiếp; một màn hình login trả 200 không chứng minh yêu cầu trang bảo vệ thành công. Hãy xem từng request và header `Location`.

**Lỗi 6 — làm lộ nguyên nhân nhạy cảm.** Đối với login thất bại, phản hồi chung “Thông tin đăng nhập không hợp lệ” thay vì “Username tồn tại, mật khẩu sai”; không log mật khẩu, Bearer token nguyên văn hay session secret. Log an toàn request ID, endpoint, loại exception và quyết định authorization phục vụ chẩn đoán.

### Checklist theo thứ tự

1. Xác định **cơ chế xác thực** (Basic, form/session, Bearer) và request thực tế có credentials hay không.
2. Xem **authentication thành công hay thất bại**: provider, encoder, account status, expiry/signature/issuer/audience token theo hệ thống.
3. Nếu xác thực thành công, kiểm tra **principal và granted authorities** thực tế, thay vì chỉ đọc bảng roles trong DB.
4. Xem **rule truy cập**: thứ tự `requestMatchers`, method, URL, `authenticated()`, `hasRole`, `hasAuthority`, `@PreAuthorize` nếu có method security.
5. Với 403 bất thường, kiểm tra thêm **CSRF** và policy khác.
6. Kiểm tra handler đang tạo response: `AuthenticationEntryPoint`, `AuthenticationFailureHandler`, `AccessDeniedHandler`; với form login phải xem redirect.

## 6. Bài tập tình huống

**A.** Request không có Authorization header vào endpoint HTTP Basic yêu cầu `ROLE_ADMIN`. → **Chưa xác thực**, thường 401. `AuthorizationFilter` có thể từ chối; `ExceptionTranslationFilter` nhận diện anonymous và khởi động xác thực.

**B.** Request gửi mật khẩu sai để gọi API cho phép mọi người dùng đã xác thực. → **Xác thực thất bại**, thường 401. Có gửi credentials không đồng nghĩa credentials hợp lệ.

**C.** User có `ROLE_USER` đã đăng nhập hợp lệ, gọi endpoint yêu cầu `ROLE_ADMIN`. → **Không đủ quyền**, thường 403; thay đổi mật khẩu không sửa được thiếu authority.

**D.** User đã login, `GET /profile` trả 200 nhưng `POST /profile` trả 403. → **Chưa đủ thông tin kết luận thiếu role**. Kiểm tra CSRF token, rule theo HTTP method và method security.

**E.** JWT có chữ ký hợp lệ nhưng thiếu scope `reports.write` để ghi báo cáo. → **Đã xác thực, thiếu quyền**, thường 403. Nếu chữ ký không hợp lệ/hết hạn, đó là **authentication failure**, thường 401.

## 7. Ghi nhớ

Quy trình quyết định: **Có danh tính đã xác thực hợp lệ chưa?** Nếu chưa, phân biệt **không gửi credentials** và **credentials không hợp lệ** để xử lý/nghiệp vụ/log phù hợp; với API thường phản hồi 401. Nếu đã có danh tính hợp lệ, kiểm tra role/scope/policy; thiếu quyền thường 403. Khi gặp 403 không giải thích được, kiểm tra cả CSRF và rule khác. **Mã trạng thái là biểu hiện của cơ chế xử lý, không thay thế được phân tích nguyên nhân.**

### Tài liệu chính thức

- [SecurityFilterChain và ExceptionTranslationFilter](https://docs.spring.io/spring-security/reference/6.5/servlet/architecture.html)
- [HTTP Basic Authentication](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/basic.html)
- [Form Login](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/form.html)
- [Authorize HttpServletRequests, hasRole và hasAuthority](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html)
- [OAuth2 Resource Server với Bearer token](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/)
- [FAQ Spring Security (lỗi 403 với POST/CSRF)](https://docs.spring.io/spring-security/reference/6.5/servlet/appendix/faq.html)
