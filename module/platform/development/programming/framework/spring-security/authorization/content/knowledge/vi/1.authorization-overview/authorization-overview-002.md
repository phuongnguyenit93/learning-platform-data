# Phân biệt xác thực danh tính với quyết định cấp quyền trong Spring Security

> **Phạm vi:** Spring Security cho ứng dụng web Servlet/Spring MVC. Trọng tâm là nhận biết hai bước bảo mật khác nhau: **authentication (xác thực danh tính)** và **authorization (quyết định cấp quyền)**, đồng thời thấy chúng phối hợp như thế nào trong một request.

## 1. Hai câu hỏi khác nhau

- **Authentication — “Bạn là ai?”**: Hệ thống kiểm tra bằng chứng danh tính (ví dụ tên đăng nhập/mật khẩu, phiên đăng nhập, access token được xác minh). Khi thành công, nó có thông tin về chủ thể (principal) và trạng thái xác thực đáng tin cậy.
- **Authorization — “Chủ thể đó có được thực hiện hành động này trên tài nguyên này không?”**: Hệ thống áp dụng chính sách quyền lên người dùng đã biết hoặc người dùng ẩn danh, cùng với **hành động**, **tài nguyên** và có thể cả **ngữ cảnh**. Kết quả là cho phép hoặc từ chối.

Ví dụ: Alice đăng nhập thành công nhưng chỉ có vai trò `USER`. Yêu cầu `GET /admin/panel` của Alice bị từ chối theo quy tắc `hasRole("ADMIN")`. **Đăng nhập đúng không đồng nghĩa với có mọi quyền.** Ngược lại, `GET /public/ping` có thể được truy cập không cần đăng nhập vì chính sách `permitAll()`.

| Góc nhìn | Authentication (xác thực) | Authorization (phân quyền) |
| --- | --- | --- |
| Câu hỏi | Ai đang gửi yêu cầu, bằng chứng danh tính có hợp lệ không? | Người đó được làm việc này với tài nguyên này không? |
| Dữ liệu chính | Credential/token/session và cơ chế xác minh tương ứng | `Authentication`, `GrantedAuthority`, đường dẫn/phương thức HTTP, phương thức Java, chủ sở hữu tài nguyên, quy tắc nghiệp vụ |
| Kết quả | Danh tính được xác thực và đặt trong ngữ cảnh bảo mật, hoặc thất bại/chưa đăng nhập | Quyết định cho phép/từ chối; có thể cần xác thực trước |
| Tình huống thất bại | Mật khẩu sai, token hết hạn, không có thông tin đăng nhập cho tài nguyên được bảo vệ | Danh tính hợp lệ nhưng thiếu vai trò/quyền, hoặc không sở hữu tài nguyên |
| Thành phần Spring Security thường gặp | `AuthenticationManager`, `AuthenticationProvider`, các authentication filter, `SecurityContextHolder` | `AuthorizationManager`, `AuthorizationFilter`, `authorizeHttpRequests`, `@PreAuthorize` |
| Ý nghĩa thực tế | “Tôi biết bạn là Alice.” | “Alice có được xem báo cáo quản trị không?” |

**Phân biệt bổ sung:** “Đã được xác thực?” khác với “Đã được cấp quyền?”. `authenticated()` trong cấu hình HTTP chỉ yêu cầu trạng thái xác thực phù hợp; `hasRole(...)` / `hasAuthority(...)` / quy tắc sở hữu còn kiểm tra điều kiện truy cập.

## 2. Spring Security lưu danh tính và ra quyết định như thế nào?

Ở phía **xác thực**:

1. Một cơ chế như HTTP Basic, form login hoặc Bearer token xử lý dữ liệu đăng nhập. Cơ chế cụ thể quyết định cách kiểm tra credential/token; không phải mọi request đều nhập mật khẩu.
2. Với một luồng đăng nhập dựa trên `AuthenticationManager`, manager chuyển yêu cầu đến `AuthenticationProvider` phù hợp. Khi xác minh thành công, hệ thống có một `Authentication` đại diện cho chủ thể đã xác thực.
3. `SecurityContext` chứa `Authentication` của request hiện tại; mã Servlet thường truy cập qua `SecurityContextHolder`. `Authentication#getName()` trả về tên chủ thể, còn `getAuthorities()` trả về danh sách `GrantedAuthority` đã được gán.

Ở phía **phân quyền**:

1. Quy tắc HTTP trong `authorizeHttpRequests` khớp request và chọn chính sách theo **thứ tự khai báo**; thường chỉ quy tắc khớp đầu tiên được dùng.
2. `AuthorizationFilter` sử dụng `AuthorizationManager` để đánh giá yêu cầu, khi cần sẽ lấy `Authentication` từ ngữ cảnh bảo mật. Quy tắc `permitAll()` có thể cho phép mà không cần đọc danh tính.
3. Sau khi vượt qua kiểm tra tại HTTP, phương thức nghiệp vụ vẫn có thể có kiểm tra quyền độc lập bằng `@PreAuthorize` nếu ứng dụng bật method security.

~~~text
Client gửi GET /admin/panel
  -> SecurityFilterChain (Servlet)
     -> Cơ chế authentication (nếu cần; ví dụ Basic)
        -> SecurityContext / Authentication {principal, authorities}
     -> AuthorizationFilter + chính sách HTTP
        -> THỎA QUY TẮC: đi tiếp đến controller/service
        -> KHÔNG THỎA: từ chối
     -> Method security (nếu có @PreAuthorize trên bean được Spring quản lý)
        -> THỎA: thực thi logic nghiệp vụ
        -> KHÔNG THỎA: từ chối
~~~

Hình trên là **luồng khái niệm**, không phải danh sách đầy đủ mọi filter. Những thành phần xử lý ngoại lệ cũng tham gia chuỗi. Trong ứng dụng dùng Bearer JWT, **việc xác minh chữ ký, hạn dùng và các điều kiện tin cậy của token** thuộc về phía xác thực; **việc kiểm tra scope, role, quyền hoặc chủ sở hữu** của endpoint thuộc về phía phân quyền.

### Principal, role và authority

- **Principal**: chủ thể đã được xác định, ví dụ `alice`. Nó trả lời *ai*.
- **Authority**: quyền/nhãn quyền mà hệ thống gán cho `Authentication`, ví dụ `ROLE_ADMIN`, `invoice:read`. Nó là dữ liệu đầu vào cho chính sách, **không tự động cấp quyền ở mọi nơi**.
- **Role**: cách tổ chức authority. Với cấu hình mặc định, `hasRole("ADMIN")` kiểm tra authority `ROLE_ADMIN`; `hasAuthority("ROLE_ADMIN")` so khớp chuỗi đó trực tiếp. `hasAuthority("invoice:read")` kiểm tra đúng authority `invoice:read`.
- **Quy tắc theo tài nguyên**: ngay cả hai người cùng role `USER` cũng không mặc nhiên được đọc hóa đơn của nhau; có thể phải kiểm tra `invoice.ownerId == authentication.name` tại tầng service hoặc bằng một `AuthorizationManager` riêng.

Lưu ý: Spring Security có thể đặt một `AnonymousAuthenticationToken` trong `SecurityContext` khi người dùng chưa đăng nhập. Vì thế **chỉ kiểm tra `authentication != null` hoặc tự dựa vào `Authentication#isAuthenticated()` là chưa đủ để kết luận đây là người dùng đăng nhập thật**. Hãy dùng quy tắc `authenticated()` của framework hoặc `AuthenticationTrustResolver` khi cần phân biệt anonymous.

## 3. Ví dụ Java 17+: một ứng dụng, hai tầng kiểm tra

Ví dụ dưới đây chạy được trong **dự án Spring Boot dùng Java 17+** với các dependency **Spring Web** và **Spring Security** (chẳng hạn tạo dự án Maven bằng Spring Initializr). Đây là mã ứng dụng hoàn chỉnh cho một tệp Java; Spring Boot và các starter cung cấp thư viện cần thiết, nên **không dùng riêng `javac` để biên dịch tệp này nếu chưa thiết lập classpath**.

Tạo hoặc thay thế tệp `src/main/java/com/example/demo/SecurityDemoApplication.java`; bảo đảm package tương ứng với dự án.

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@EnableMethodSecurity
public class SecurityDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(SecurityDemoApplication.class, args);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/ping").permitAll()
                .requestMatchers("/profile/me", "/reports/summary").authenticated()
                .requestMatchers("/admin/panel").hasRole("ADMIN")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults());
        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("demo123"))
            .roles("USER")
            .build();

        UserDetails bob = User.withUsername("bob")
            .password(encoder.encode("demo456"))
            .roles("ADMIN")
            .build();

        return new InMemoryUserDetailsManager(alice, bob);
    }

    @RestController
    static class ApiController {
        private final ReportService reportService;

        ApiController(ReportService reportService) {
            this.reportService = reportService;
        }

        @GetMapping("/public/ping")
        String ping() {
            return "pong";
        }

        @GetMapping("/profile/me")
        String me(Authentication authentication) {
            return authentication.getName();
        }

        @GetMapping("/admin/panel")
        String panel() {
            return "admin data";
        }

        @GetMapping("/reports/summary")
        String report() {
            return reportService.summary();
        }
    }

    @Service
    static class ReportService {
        @PreAuthorize("hasRole('ADMIN')")
        public String summary() {
            return "quarterly report";
        }
    }
}
~~~

Chạy với Maven Wrapper ở thư mục dự án:

~~~bash
# macOS/Linux
./mvnw spring-boot:run

# Windows PowerShell / Command Prompt
mvnw.cmd spring-boot:run
~~~

Sau khi ứng dụng chạy trên cổng mặc định 8080, thử các yêu cầu GET sau (mật khẩu này **chỉ là dữ liệu demo**, không áp dụng nguyên xi trong môi trường thật):

~~~bash
curl -i http://localhost:8080/public/ping
curl -i http://localhost:8080/profile/me
curl -i -u alice:demo123 http://localhost:8080/profile/me
curl -i -u alice:demo123 http://localhost:8080/admin/panel
curl -i -u bob:demo456 http://localhost:8080/admin/panel
curl -i -u alice:demo123 http://localhost:8080/reports/summary
curl -i -u bob:demo456 http://localhost:8080/reports/summary
~~~

| Lời gọi | Kết quả kỳ vọng | Lý do |
| --- | --- | --- |
| `/public/ping`, không credential | `200`, body `pong` | Chính sách `permitAll()` |
| `/profile/me`, không credential | `401 Unauthorized` | Endpoint yêu cầu xác thực, HTTP Basic yêu cầu credential |
| `/profile/me`, Alice | `200`, body `alice` | Alice đã xác thực; không yêu cầu role cụ thể |
| `/admin/panel`, Alice | `403 Forbidden` | Alice xác thực thành công nhưng không có `ROLE_ADMIN` |
| `/admin/panel`, Bob | `200`, body `admin data` | Bob có `ROLE_ADMIN` |
| `/reports/summary`, Alice | `403 Forbidden` | Qua quy tắc HTTP `authenticated()`, nhưng bị `@PreAuthorize` ở service từ chối |
| `/reports/summary`, Bob | `200`, body `quarterly report` | Qua cả hai tầng HTTP và method security |

**Giải thích điều cần quan sát:** `/reports/summary` chỉ đòi hỏi đăng nhập ở HTTP, nhưng service vẫn buộc có role admin. Điều này thể hiện rõ “xác thực thành công” chưa đủ để được thực hiện phương thức nghiệp vụ. `@EnableMethodSecurity` kích hoạt các kiểm tra như `@PreAuthorize`; Spring Boot Security starter không tự động kích hoạt method security chỉ vì có dependency. Lời gọi controller → bean `ReportService` đi qua proxy của Spring; nếu một phương thức trong cùng bean tự gọi phương thức được gắn `@PreAuthorize` qua `this` thì có thể bỏ qua kiểm tra AOP theo cơ chế proxy thông thường.

### HTTP 401, 403 và chuyển hướng đăng nhập

Trong ví dụ dùng HTTP Basic, khi không có credential cho tài nguyên cần xác thực, entry point trả `401 Unauthorized`; người đã đăng nhập nhưng thiếu quyền thường nhận `403 Forbidden`.

Spring Security sử dụng `ExceptionTranslationFilter` để chuyển các ngoại lệ bảo mật thành luồng HTTP thích hợp:

- `AuthenticationException` hoặc yêu cầu bị từ chối trong ngữ cảnh anonymous thường kích hoạt `AuthenticationEntryPoint` (HTTP Basic thường là 401; form login có thể là **302 redirect** đến trang đăng nhập).
- `AccessDeniedException` của người dùng đã xác thực thường đi đến `AccessDeniedHandler` (mặc định thường là 403).

Vì thế **đừng suy luận “mọi lỗi authentication luôn 401” hay “mọi lần từ chối authorization luôn 403”** mà bỏ qua cơ chế login, anonymous và cấu hình entry point. Trong ứng dụng API, hãy xác định rõ contract trả lỗi.

## 4. Áp dụng vào tình huống thực tế

**API hóa đơn:**

- Authentication: xác minh access token và nhận diện `alice`; ánh xạ các authority hợp lệ đã được cấp.
- Authorization cấp endpoint: chỉ người có `invoice:read` mới được gọi `GET /invoices/{id}`.
- Authorization cấp đối tượng: nạp invoice cần đọc và kiểm tra `invoice.ownerId == alice.id`, hoặc một quyền quản trị được thiết kế rõ ràng.
- Kết luận: Alice có quyền đọc hóa đơn nói chung **vẫn không nhất thiết được đọc hóa đơn của Bob**. Kiểm tra role/scope ở URL là chưa đủ cho tài nguyên cụ thể.

**Cách đặt chính sách hợp lý:** sử dụng `authorizeHttpRequests` để bảo vệ tuyến HTTP, dùng `@PreAuthorize` hoặc `AuthorizationManager`/policy service cho quyết định gần nghiệp vụ, và áp dụng **deny by default** cho endpoint chưa có quy tắc. Không lấy việc frontend ẩn nút hoặc đường dẫn khó đoán làm biện pháp phân quyền.

## 5. Những nhầm lẫn thường gặp

1. **“Token đúng thì được truy cập mọi API.”** Sai: token hợp lệ xác lập danh tính/ngữ cảnh tin cậy; API vẫn kiểm tra scope, role, action và tài nguyên. Authority từ token chỉ đáng tin sau khi token đã được xác minh đúng.
2. **“`authenticated()` là kiểm tra admin.”** Sai: đó là yêu cầu xác thực; admin cần `hasRole("ADMIN")` hoặc chính sách tương đương.
3. **“`hasRole("ADMIN")` giống `hasAuthority("ADMIN")`.”** Không đúng với tiền tố role mặc định: `hasRole("ADMIN")` kiểm tra `ROLE_ADMIN`, còn `hasAuthority("ADMIN")` kiểm tra chuỗi `ADMIN`. Tiền tố có thể tùy chỉnh.
4. **“Có `Authentication` tức là đã đăng nhập.”** Sai với anonymous token; sử dụng cơ chế nhận biết anonymous của Spring Security.
5. **“Đã chặn URL là đủ.”** Chưa chắc: service được gọi từ chỗ khác (job, REST endpoint khác, message consumer) có thể cần chính sách method/domain. Khi dùng `@PreAuthorize` theo AOP, tránh tự gọi trong cùng bean nếu mong muốn proxy chặn.
6. **“`permitAll()` có nghĩa bỏ qua Spring Security.”** Không: request vẫn nằm trong security filter chain; `permitAll()` chỉ là quyết định cấp phép của tuyến đó, khác với bỏ qua toàn bộ các filter.
7. **“Quy tắc nào khớp cũng được.”** `authorizeHttpRequests` xét theo thứ tự; đặt `anyRequest()` ở cuối và sắp quy tắc cụ thể trước quy tắc rộng.
8. **“Basic Authentication tự mã hóa mật khẩu trên đường truyền.”** Không: Basic mã hóa Base64, không phải mã hóa bảo mật; với hệ thống thực tế phải dùng HTTPS. Tài khoản/mật khẩu cứng trong ví dụ chỉ phục vụ học tập.

## 6. Tự kiểm tra kiến thức

1. Alice đã đăng nhập, có `ROLE_USER` nhưng không có `ROLE_ADMIN`. `hasRole("ADMIN")` nên cho phép hay từ chối? **Từ chối**; authentication đã thành công nhưng authorization không đạt.
2. Endpoint `/health` có `permitAll()`; người chưa đăng nhập có thể được phép không? **Có**, nếu không có chính sách khác chặn request.
3. Bob có `invoice:read` nhưng yêu cầu đọc hóa đơn của Alice. Cần thêm gì? **Kiểm tra quyền trên chính đối tượng**, chẳng hạn chủ sở hữu hoặc quan hệ truy cập.
4. Vì sao `/reports/summary` trong ví dụ có thể trả 403 dù HTTP khai báo `authenticated()`? Vì **`@PreAuthorize` của service tiếp tục đánh giá `ROLE_ADMIN`**.
5. Nhìn `Authentication#getAuthorities()` có thể biết ngay “được vào tất cả API nào” không? **Không**; quyết định còn phụ thuộc chính sách endpoint, phương thức và dữ liệu tài nguyên.

**Ghi nhớ:** *Authentication xác định “ai”, còn authorization quyết định “được làm gì với cái gì, trong hoàn cảnh nào”.* Spring Security dùng danh tính và authorities như **đầu vào** cho chính sách; một kết quả xác thực thành công không tự thay thế quyết định phân quyền.

## Tài liệu chính thức

- Spring Security — Authentication Architecture: https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html
- Spring Security — Authorization Architecture: https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html
- Spring Security — Authorize HTTP Requests: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security — Method Security: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Security — Anonymous Authentication: https://docs.spring.io/spring-security/reference/servlet/authentication/anonymous.html
- Spring Security — Servlet Architecture: https://docs.spring.io/spring-security/reference/servlet/architecture.html
