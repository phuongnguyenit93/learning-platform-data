# Quan sát trang đăng nhập, HTTP Basic và phản hồi khi chưa đăng nhập

Khi vừa thêm `spring-boot-starter-security` vào một ứng dụng Spring Boot, bạn có thể gặp hai phản hồi tưởng như khác nhau: **trình duyệt tự chuyển tới trang đăng nhập** trong khi `curl` hoặc một API client nhận **HTTP 401** kèm lời mời gửi thông tin xác thực. Đây là những cách khởi tạo **authentication** phù hợp với các loại client khác nhau. Muốn hiểu chúng, cần quan sát cả **status code**, **HTTP headers**, **đường dẫn chuyển hướng**, **cookie/session** và **cơ chế bảo mật thực sự đang được bật**.

Bài này hướng dẫn quan sát có hệ thống ba tình huống: **form login trong trình duyệt**, **HTTP Basic authentication**, và **phản hồi khi request chưa đăng nhập hoặc không đủ quyền**. Ví dụ dùng **Spring Boot 3, Spring Security 6, Spring MVC/Servlet và Java 17+**. Các lựa chọn cấu hình được viết tường minh để kết quả dễ lặp lại giữa trình duyệt, `curl` và MockMvc. Những giá trị session ID, CSRF token, thời gian, thứ tự header và redirect URL cụ thể có thể thay đổi theo môi trường.

## 1. Trước tiên: phân biệt “chưa đăng nhập”, “sai mật khẩu” và “thiếu quyền”

| Trường hợp | Tình trạng bảo mật | Phản hồi thường thấy | Ý nghĩa |
| --- | --- | --- | --- |
| Trình duyệt chưa đăng nhập, truy cập trang riêng tư có `formLogin` | Chưa có principal đã đăng nhập | **302 Found** tới `/login`, sau đó GET `/login` thường **200 OK** | Chuyển người dùng sang giao diện nhập credentials |
| API dùng HTTP Basic, không gửi credentials | Chưa xác thực | **401 Unauthorized** + `WWW-Authenticate: Basic ...` | Client phải cung cấp username/password hợp lệ |
| API dùng HTTP Basic, username/password sai | Xác thực thất bại | Thường **401**; có thể kèm Basic challenge | Credentials được đưa vào nhưng không được chấp nhận |
| Đã xác thực nhưng gọi chức năng cần role/authority khác | Danh tính hợp lệ nhưng không được phép | Thường **403 Forbidden** | Đây là vấn đề authorization |
| User hợp lệ gọi endpoint đúng quyền | Authentication + authorization thành công | Thường **200 OK** cho GET đơn giản | Request đã qua các kiểm tra đang áp dụng |
| POST dùng session cookie nhưng thiếu CSRF token đúng quy tắc | Có thể đã login, request thay đổi trạng thái không hợp lệ | Thường **403 Forbidden** | Bị lớp CSRF chặn, không đồng nghĩa thiếu role |
| Endpoint được `permitAll()` | Request được phép công khai theo policy | Thường **200 OK** | Không bắt buộc login cho endpoint đó |

Mã trạng thái phụ thuộc **AuthenticationEntryPoint**, **AccessDeniedHandler**, filter chain, cơ chế dùng form/session hay Basic/token và cấu hình ứng dụng. Không thể kết luận mọi 302 đều là login hoặc mọi 403 đều do thiếu role. Cần kiểm tra đúng URL, method, response và cấu hình.

### 1.1. Vì sao HTTP gọi 401 là “Unauthorized” dù bản chất là chưa xác thực?

Trong ngữ cảnh HTTP authentication, **401 Unauthorized** cho biết request thiếu credentials hợp lệ cho tài nguyên yêu cầu xác thực; server có thể trả `WWW-Authenticate` để mô tả scheme mà client phải sử dụng. **403 Forbidden** thường chỉ request đã được xử lý về danh tính nhưng không có quyền, hoặc bị cơ chế khác từ chối như CSRF. Thuật ngữ tên trạng thái HTTP không thay thế việc phân biệt **authentication** và **authorization**.

### 1.2. Thấy trang đăng nhập không đồng nghĩa API đã thành công

Một trình duyệt truy cập `/home` có thể nhận:

```text
GET /home
  -> 302 Location: /login
GET /login
  -> 200 Content-Type: text/html
```

Tab trình duyệt cuối cùng hiển thị trang HTML với **200**, nhưng **request đầu tiên tới /home chưa được phép**. Khi quan sát bằng Developer Tools, phải bật **Preserve log** và xem cả chuỗi request, tránh chỉ nhìn status của trang `/login`.

Tương tự, `curl -L` hoặc HTTP client tự động follow redirects có thể che status ban đầu nếu không xem lịch sử chuyển hướng. Để học hành vi thật, trước tiên hãy **không tự động follow redirect**.

## 2. Hành vi khởi tạo mặc định của Spring Boot và Spring Security

Với Spring Boot 3 ứng dụng Servlet, khi thêm `spring-boot-starter-security` và chưa tự định nghĩa `SecurityFilterChain`, Spring Boot thường cấu hình bảo vệ tất cả request và cung cấp **form-based login** lẫn **HTTP Basic**. Spring Security có cấu hình mặc định về mặt khái niệm tương đương:

```java
http.authorizeHttpRequests(auth -> auth
        .anyRequest().authenticated()
    )
    .formLogin(Customizer.withDefaults())
    .httpBasic(Customizer.withDefaults());
```

Đoạn trên chỉ mô tả **cấu hình khái niệm**, không phải tệp Java độc lập. Trong dự án thực tế, Spring Boot bổ sung các bean, security filter và cơ chế user store phù hợp với auto-configuration. Khi bạn **tự khai báo** một bean `SecurityFilterChain`, cần bật rõ các cơ chế mong muốn, ví dụ `formLogin(...)` và/hoặc `httpBasic(...)`; không giả định chúng tự xuất hiện trong cấu hình tự viết.

### 2.1. Người dùng mặc định và mật khẩu khởi tạo

Nếu chưa có `UserDetailsService`, `AuthenticationProvider` hoặc cơ chế xác thực custom khác, Boot có thể tạo user mặc định, thường mang username `user` và **mật khẩu ngẫu nhiên dùng cho development** được ghi ra log lúc khởi động. Log có thể chứa thông điệp về generated security password.

Điều này phục vụ **khởi tạo và học tập**, không phải cơ chế quản lý tài khoản cho production. Không dựa vào password này trong triển khai thực tế; không chia sẻ log chứa password, secret hoặc token. Tùy những bean bạn tự khai báo, user mặc định có thể không được tạo; vì vậy hãy xem cấu hình cụ thể của dự án trước khi dựa vào tài khoản `user`.

### 2.2. Cùng hệ thống nhưng nhiều cách khởi tạo xác thực

Nếu **cùng một security chain** bật cả form login và HTTP Basic, Spring Security có thể chọn entry point phù hợp dựa trên request, chẳng hạn loại nội dung mà client chấp nhận. Kết quả còn phụ thuộc custom exception handling và cách ứng dụng xử lý API. Vì vậy, chỉ nhìn header `Accept` hoặc chỉ nói “browser luôn 302, curl luôn 401” là quy tắc quá rộng.

Để quan sát hai luồng với kết quả dự đoán được, bài này dùng **hai SecurityFilterChain**:

- `/api/**`: dùng HTTP Basic và không dùng phiên để khôi phục authentication; request chưa xác thực nhận **401**.
- Các URL còn lại: dùng form login; request chưa xác thực tới trang riêng tư nhận **302** dẫn về `/login`.

Đây là **cấu hình mẫu để học**. Ứng dụng production có thể sử dụng session, JWT, OAuth2/OIDC hoặc gateway với chính sách khác, nên phải dựa trên cấu hình thực tế để giải thích response.

## 3. Quan sát form login: từ trang riêng tư tới /login

Với form login, khi một request chưa được xác thực bị rule truy cập chặn, `ExceptionTranslationFilter` phối hợp với `LoginUrlAuthenticationEntryPoint` để khởi tạo luồng đăng nhập bằng cách trả redirect.

### 3.1. Trước khi đăng nhập

```http
GET /home HTTP/1.1
Host: localhost:8080
Accept: text/html
```

Phản hồi điển hình:

```http
HTTP/1.1 302 Found
Location: http://localhost:8080/login
```

`Location` có thể là đường dẫn tương đối hoặc URL đầy đủ, tùy môi trường và redirect strategy. **Điều cần xác minh là redirect trỏ tới trang đăng nhập dự kiến**, không cố gắng so từng ký tự URL trong mọi hệ thống.

Khi trình duyệt follow redirect:

```http
GET /login HTTP/1.1
Host: localhost:8080
Accept: text/html
```

Phản hồi điển hình:

```http
HTTP/1.1 200 OK
Content-Type: text/html;charset=UTF-8
```

Body chứa HTML form đăng nhập. Nếu ứng dụng bật `formLogin(Customizer.withDefaults())` và chưa cung cấp trang login custom, Spring Security có thể sinh trang mặc định qua `DefaultLoginPageGeneratingFilter`.

### 3.2. Trang login mặc định được tạo bởi ai?

Spring Security có thể sinh trang HTML mặc định với các trường `username`, `password` và CSRF token khi cần. Đây là chức năng giúp kiểm tra nhanh cấu hình, **không phải template UI mà ứng dụng đã chủ động xây dựng**.

Để xác minh, mở `http://localhost:8080/login` trong trình duyệt và kiểm tra:

1. URL thanh địa chỉ sau khi vào trang riêng tư đã đổi sang `/login`.
2. HTML chứa form đăng nhập và các ô nhập username/password.
3. DevTools → Network có GET `/home` trả redirect và GET `/login` trả HTML.
4. Nếu đang dùng CSRF protection, form gửi token CSRF theo cơ chế mà Spring Security đã thiết lập.
5. Nếu đăng nhập sai, form login mặc định thường chuyển tới `/login?error`, chứ không bắt buộc trả 401 JSON như một API.

Không coi trang login mặc định là giao diện sản phẩm hoàn chỉnh. Khi dùng trang custom, ứng dụng cần tự cung cấp endpoint/template và phải phối hợp chính xác URL xử lý login, CSRF, lỗi, accessibility và bảo vệ session.

### 3.3. Sau khi đăng nhập bằng form

Luồng khái niệm:

```text
GET /home             -> redirect tới /login
GET /login            -> trang nhập user/password + CSRF
POST /login           -> UsernamePasswordAuthenticationFilter
                       -> AuthenticationManager / Provider
                       -> thành công: security context, session khi phù hợp
                       -> redirect tới request đã lưu hoặc URL thành công
GET /home với session -> 200, nội dung riêng tư
```

Với session-based login, trình duyệt thường lưu cookie phiên như `JSESSIONID` khi server cần phiên. Các giá trị cookie, session fixation protection, CSRF token và request cache tùy ứng dụng, nên không đưa ID cụ thể vào tài liệu hay lấy một chuỗi mẫu cố định làm tiêu chuẩn kiểm thử.

**POST /login không chỉ là gửi username/password.** Nếu CSRF protection đang bật, việc tự gửi POST bằng curl mà không cung cấp CSRF token hợp lệ có thể nhận **403** trước khi kiểm tra password. Trình duyệt dùng form mà framework tạo ra thường có token cần thiết. Không tắt CSRF chỉ vì thử POST thủ công chưa thành công.

### 3.4. Phân biệt 302 từ login với 302 từ ứng dụng

Một ứng dụng có thể trả redirect vì nhiều lý do: sau logout, chuyển trang thành công, thay URL, callback OAuth2 hoặc yêu cầu đăng nhập. Hãy xem `Location`, request ban đầu, trạng thái session và security chain. Khi testing form login, kiểm tra mục tiêu chuyển hướng và user đã được xác thực; chỉ assert “status 302” chưa đủ.

## 4. Quan sát HTTP Basic: 401 và WWW-Authenticate

HTTP Basic là cơ chế authentication do HTTP định nghĩa. Client gửi username/password trong header `Authorization`; khi chưa có credentials hợp lệ, server thường trả **401** và header **`WWW-Authenticate: Basic ...`** để thông báo scheme được hỗ trợ.

### 4.1. Request chưa có Authorization header

```http
GET /api/me HTTP/1.1
Host: localhost:8080
Accept: application/json
```

Phản hồi theo cấu hình API chain của bài:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="Realm"
```

Tên realm là chi tiết cấu hình; **không hardcode giá trị `Realm` trong test ứng dụng tổng quát**. Một số request client đặc biệt hoặc custom entry point có thể nhận header khác; ví dụ Spring Security hỗ trợ hành vi tránh bật hộp thoại Basic của trình duyệt trong một số tình huống XHR. Muốn chứng minh HTTP Basic đang được dùng, hãy kiểm tra cả security chain và challenge phù hợp với request cụ thể.

Header `WWW-Authenticate` là **challenge từ server**, còn header `Authorization` là **credentials do client gửi**; hai tên rất dễ bị đảo nhầm.

### 4.2. Request có Basic credentials

```http
GET /api/me HTTP/1.1
Host: localhost:8080
Authorization: Basic <base64-of-username-colon-password>
```

Giá trị thực được tạo từ chuỗi `username:password` dưới dạng Base64. **Base64 không phải encryption**; bất kỳ ai có header đều có thể giải mã để thấy username/password. HTTP Basic chỉ phù hợp trên **HTTPS** khi sử dụng thực tế, và phải tránh log header `Authorization` hoặc để lộ password trên command line, history, ảnh chụp màn hình.

Trong ví dụ cục bộ, có thể dùng `curl -u alice:demo-alice-pass` để curl tạo header thay vì tự Base64. Sau khi credentials được provider xác minh, request tới `/api/me` trả 200 và dữ liệu user mẫu.

### 4.3. Sai mật khẩu và khác biệt với thiếu quyền

- Username/password sai → **authentication thất bại**, thường trả `401`.
- Username/password đúng, user thiếu `ROLE_ADMIN` → **authorization từ chối**, thường `403`.
- Chưa gửi username/password tới endpoint công khai `permitAll()` → có thể `200`.
- POST thiếu CSRF trong chain bật CSRF → có thể `403`, **dù** username/password đúng.

Một số trình duyệt có thể bật hộp thoại native để hỏi username/password khi nhận Basic challenge; API client như curl/Postman thường hiển thị header/status. Không nhầm hộp thoại Basic của trình duyệt với trang HTML `/login` do Spring Security render: đây là **hai giao diện/cơ chế khác nhau**.

### 4.4. Basic thường không cần session đăng nhập

Với Basic, client thường gửi credentials trên **mỗi request**. Ví dụ sẽ cấu hình API chain `SessionCreationPolicy.STATELESS` để Spring Security không dùng HTTP session làm nguồn khôi phục `SecurityContext` cho API. Điều này cho phép quan sát tính độc lập giữa API Basic và cookie đăng nhập giao diện web.

`STATELESS` **không có nghĩa mọi cơ chế bảo vệ như CSRF đều bị tắt**. Nếu API còn nhận credentials tự động từ trình duyệt hoặc có endpoints thay đổi trạng thái, cần đánh giá threat model và chính sách CSRF cụ thể. Bài này chỉ dùng các API GET để quan sát authentication.

## 5. Bài thực hành Spring Boot 3: hai luồng rõ ràng

Mục tiêu:

| URL | Ai được gọi? | Cơ chế quan sát |
| --- | --- | --- |
| `GET /public` | Công khai | 200 dù chưa đăng nhập |
| `GET /home` | Phải đăng nhập | Anonymous → 302 `/login` |
| `GET /admin` | Phải có `ROLE_ADMIN` | Anonymous → login; user thiếu role → 403 |
| `GET /login` | Form login | Trang HTML do Spring Security tạo |
| `GET /api/public` | Công khai | 200 dù không có Basic credentials |
| `GET /api/me` | Phải xác thực | Anonymous → 401 Basic challenge; Basic đúng → 200 |
| `GET /api/admin` | Phải có `ROLE_ADMIN` | Basic đúng nhưng thiếu quyền → 403 |
| `POST /notes` | Phải login, cần CSRF | POST thiếu token → 403 khi CSRF bật |

### 5.1. Tạo dự án và dependency

Tạo dự án **Spring Boot 3, Java 17+**, loại **Spring Web (MVC)** và **Spring Security**. Với Gradle Groovy DSL, trong `build.gradle` của dự án Boot đã cấu hình plugin và repository, dùng:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Với Maven, dự án Boot có `spring-boot-starter-parent`/BOM sẽ dùng các dependency tương đương. **Không tự ghép phiên bản Spring Security không tương thích với Boot**; để dependency management của dự án chọn bản nhất quán. Tên file Gradle ở đây là một *đoạn của dự án Spring Boot*, không phải file build hoàn chỉnh.

### 5.2. Lớp main

Tạo `src/main/java/example/loginobservation/LoginObservationApplication.java`:

```java
package example.loginobservation;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class LoginObservationApplication {
    public static void main(String[] args) {
        SpringApplication.run(LoginObservationApplication.class, args);
    }
}
```

### 5.3. SecurityConfig: API Basic và web form login

Tạo `src/main/java/example/loginobservation/SecurityConfig.java`:

```java
package example.loginobservation;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("demo-alice-pass"))
            .roles("USER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("demo-admin-pass"))
            .roles("USER", "ADMIN")
            .build();

        return new InMemoryUserDetailsManager(alice, admin);
    }

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public").permitAll()
                .requestMatchers("/api/admin").hasRole("ADMIN")
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults())
            .sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain webChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/public").permitAll()
                .requestMatchers("/admin").hasRole("ADMIN")
                .anyRequest().authenticated()
            )
            .formLogin(Customizer.withDefaults())
            .build();
    }
}
```

Giải thích kỹ các dòng:

1. Hai bean `SecurityFilterChain` được sắp bằng `@Order`. `FilterChainProxy` chọn **chain đầu tiên có matcher khớp**.
2. Chain thứ nhất chỉ xử lý `/api/**`, dùng `httpBasic`. `/api/public` công khai, `/api/admin` cần role ADMIN, các API còn lại cần xác thực.
3. `STATELESS` làm API chain không lấy authentication từ session web; các request API mẫu phải cung cấp Basic credentials nếu endpoint riêng tư.
4. Chain thứ hai **không đặt `securityMatcher`**, làm fallback cho các URL còn lại như `/home`, `/admin`, `/login`. Nó bật `formLogin` và dùng session mặc định khi cần.
5. `formLogin(Customizer.withDefaults())` cho phép Spring Security tạo trang login mặc định tại `/login` và xử lý submit login; với cấu hình trên, trang này thuộc web chain.
6. Các password demo được băm bằng `BCryptPasswordEncoder`. `roles("ADMIN")` tạo `ROLE_ADMIN`, khớp với `hasRole("ADMIN")`. Password trong ví dụ chỉ dùng cục bộ.
7. CSRF protection trong Spring Security Servlet **không bị vô hiệu hóa**. Vì thế POST vào web chain cần token CSRF hợp lệ khi có yêu cầu tương ứng.
8. Cấu hình `apiChain` không bật form login; cấu hình `webChain` không bật HTTP Basic. Do đó cách trả 401 và 302 được xác định bởi chain, giúp thực hành dễ quan sát.

**Điểm quan trọng:** `securityMatcher("/api/**")` chọn phạm vi **cả chain**. Nó khác `requestMatchers(...)`, vốn chỉ tạo rule authorization **bên trong chain đã được chọn**. Nếu một ứng dụng nhiều chain thiếu fallback, một URL không khớp chain nào có thể đi ngoài các security filters của Spring Security. Trong ví dụ này, webChain không có `securityMatcher` nên phủ phần còn lại.

### 5.4. Controller

Tạo `src/main/java/example/loginobservation/ObservationController.java`:

```java
package example.loginobservation;

import java.security.Principal;
import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ObservationController {

    @GetMapping("/")
    public String index() {
        return "Welcome";
    }

    @GetMapping("/public")
    public String publicPage() {
        return "public";
    }

    @GetMapping("/home")
    public String home(Principal principal) {
        return "hello " + principal.getName();
    }

    @GetMapping("/admin")
    public String admin() {
        return "admin page";
    }

    @GetMapping("/api/public")
    public Map<String, String> apiPublic() {
        return Map.of("message", "public api");
    }

    @GetMapping("/api/me")
    public Map<String, String> apiMe(Principal principal) {
        return Map.of("user", principal.getName());
    }

    @GetMapping("/api/admin")
    public Map<String, String> apiAdmin() {
        return Map.of("message", "admin api");
    }

    @PostMapping("/notes")
    public String addNote(Principal principal) {
        return "note from " + principal.getName();
    }
}
```

`Principal` là abstraction của Java/Spring servlet để đọc danh tính đã được hệ thống gắn vào request sau xác thực. Controller **không tự kiểm tra password**; security filters và authentication provider xử lý việc này. Nếu service cần kiểm tra ownership/tenant với tài nguyên cụ thể, đó là một lớp authorization nghiệp vụ bổ sung.

Ở ví dụ này, `/notes` chỉ trả chuỗi, không ghi database; nó tồn tại để minh họa thêm sự khác nhau giữa login, authorization và CSRF.

### 5.5. Chạy ứng dụng

Trong root dự án Spring Boot có Gradle Wrapper:

```bash
./gradlew bootRun
```

Trên Windows PowerShell hoặc CMD:

```powershell
.\gradlew.bat bootRun
```

Khi chạy, ứng dụng mặc định nghe tại `http://localhost:8080` nếu chưa chỉnh `server.port`. Nếu cổng khác, thay URL bên dưới. Hai tài khoản demo:

| Username | Password demo | Role |
| --- | --- | --- |
| `alice` | `demo-alice-pass` | `ROLE_USER` |
| `admin` | `demo-admin-pass` | `ROLE_USER`, `ROLE_ADMIN` |

Không dùng các password trên trong production. Khi triển khai thật, dùng HTTPS, kho danh tính phù hợp, chính sách password/session và quản lý secret an toàn.

## 6. Bài quan sát bằng trình duyệt và Developer Tools

### 6.1. Dùng cửa sổ ẩn danh để bắt đầu từ trạng thái sạch

Một phiên trình duyệt đang giữ cookie `JSESSIONID` có thể đã đăng nhập; khi đó `GET /home` trả 200 và bạn không nhìn thấy redirect. Để học, mở cửa sổ ẩn danh hoặc xóa cookie của riêng ứng dụng demo trên localhost.

Thực hiện:

1. Mở `http://localhost:8080/home` khi chưa login.
2. Quan sát thanh địa chỉ đổi tới `http://localhost:8080/login`.
3. Mở Developer Tools → Network, bật **Preserve log** rồi truy cập lại `/home`.
4. Lọc theo `Doc` hoặc `All`; tìm request `/home` và `/login`.
5. Chọn `/home`, xem status 302 và response header `Location`; chọn `/login`, xem status 200 và HTML form.
6. Nhập `alice` / `demo-alice-pass`. Sau xác thực, trình duyệt được chuyển tới request đã lưu (nếu có) hoặc URL thành công; mở `/home` để thấy `hello alice`.
7. Khi đang login bằng Alice, truy cập `/admin`: expect **403** vì Alice thiếu `ROLE_ADMIN`, không phải redirect tới login.
8. Đăng xuất hoặc mở phiên ẩn danh khác rồi thử Admin để phân biệt quyền.

Một chuỗi quan sát dễ ghi chép:

```text
GET /home         302 -> Location có /login
GET /login        200 -> HTML login
POST /login       302 -> login thành công, redirect
GET /home         200 -> hello alice
GET /admin        403 -> tài khoản đã login thiếu ROLE_ADMIN
```

Giá trị và status của POST login có thể thay đổi nếu có cấu hình custom như login success handler hoặc MFA. Các status trên là **kỳ vọng cho ví dụ tường minh**.

### 6.2. Kiểm tra session cookie có kiểm soát

Trong DevTools → Application/Storage → Cookies (tên mục có thể khác theo trình duyệt), kiểm tra ứng dụng có cookie phiên hay không. **Không sao chép nguyên giá trị session ID ra log, issue tracker hoặc bài hướng dẫn chia sẻ công khai**. Với ứng dụng thật, cookie cần cấu hình `HttpOnly`, `Secure` khi chạy HTTPS và `SameSite` phù hợp theo threat model.

Đừng coi có `JSESSIONID` là chứng minh user đã đăng nhập: một HTTP session có thể tồn tại cho mục đích khác, như lưu request chưa xác thực hoặc CSRF. Hãy kiểm tra hành vi `GET /home` với session đó và Authentication/authorization trên server.

### 6.3. Khi browser cache làm khó quan sát

DevTools có tùy chọn **Disable cache** khi đang mở, giúp quan sát các request khi cần. Tuy nhiên, nếu user đã login thì xóa cache không tự xóa cookie/session. Không nhầm cache của resource với security context.

## 7. Bài quan sát bằng curl: xem rõ status và header

Với mỗi lệnh dưới đây, `-i` cho phép xem HTTP response headers và body. **Không dùng `-L` ở lượt đầu** vì nó tự follow redirects và có thể che phản hồi ban đầu.

### 7.1. Gọi endpoint web private khi chưa login

```bash
curl -i http://localhost:8080/home
```

Kết quả quan trọng:

```text
HTTP/1.1 302
Location: .../login
```

Tên status reason phrase hoặc cách trình bày trên dòng đầu có thể phụ thuộc server/HTTP version, nhưng mã phản hồi 302 và header Location dẫn về login là tín hiệu cần ghi lại.

Trang login:

```bash
curl -i http://localhost:8080/login
```

Kỳ vọng **200** và HTML login form. Không hardcode HTML cụ thể vì trang mặc định có thể thay đổi theo phiên bản và CSRF token.

### 7.2. Gọi API private không có Basic credentials

```bash
curl -i http://localhost:8080/api/me
```

Kỳ vọng:

```text
HTTP/1.1 401
WWW-Authenticate: Basic ...
```

Nếu bạn gửi `X-Requested-By: XMLHttpRequest` hoặc cấu hình custom `AuthenticationEntryPoint`, chi tiết challenge có thể khác. Với các lệnh curl bình thường của bài này, việc thấy Basic challenge là điều cần kiểm tra.

### 7.3. Gọi API với Basic đúng

```bash
curl -i -u alice:demo-alice-pass http://localhost:8080/api/me
```

Kỳ vọng **200 OK** với body JSON:

```json
{"user":"alice"}
```

`curl -u` giúp tự tạo header Authorization Basic. Cú pháp hiển thị password ngay trên dòng lệnh chỉ dùng cho demo cục bộ. Với credentials thật, dùng cơ chế nhập và quản lý secret phù hợp để tránh lộ trong shell history/process list.

### 7.4. Gọi API với Basic sai

```bash
curl -i -u alice:wrong-password http://localhost:8080/api/me
```

Kỳ vọng **401**, không có dữ liệu user từ endpoint. 401 ở đây đến từ **credentials không được chấp nhận**.

### 7.5. Đã login nhưng thiếu quyền admin

```bash
curl -i -u alice:demo-alice-pass http://localhost:8080/api/admin
```

Kỳ vọng **403 Forbidden**, vì Alice có `ROLE_USER` nhưng thiếu `ROLE_ADMIN`. Với tài khoản Admin:

```bash
curl -i -u admin:demo-admin-pass http://localhost:8080/api/admin
```

Kỳ vọng **200** và body:

```json
{"message":"admin api"}
```

Đây là cặp test quan trọng để chứng minh **authentication thành công không đồng nghĩa authorization thành công**.

### 7.6. So sánh public endpoint

```bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/api/public
```

Cả hai kỳ vọng **200**. Request công khai vẫn đi qua filter chain tương ứng; `permitAll()` không có nghĩa tắt toàn bộ Spring Security.

### 7.7. Dùng Accept để kiểm tra vai trò của chain

```bash
curl -i -H "Accept: text/html" http://localhost:8080/api/me
curl -i -H "Accept: application/json" http://localhost:8080/home
```

Với **hai chain đã cấu hình** trong ví dụ, API `/api/me` vẫn trả Basic challenge 401; `/home` vẫn redirect login 302. Đây là một cách chứng minh **cơ chế đang được chọn theo `securityMatcher`**, không đơn thuần do giá trị Accept.

Trong cấu hình **một chain** bật cả form login và Basic, content negotiation và entry point có thể cho hành vi khác. Hãy phân biệt hai tình huống trước khi debug hoặc viết test.

### 7.8. HTTP Basic và hộp thoại trình duyệt

Nếu truy cập `/api/me` trực tiếp bằng browser, trình duyệt có thể hiển thị hộp thoại nhập Basic credentials do header `WWW-Authenticate`. Hộp thoại đó do **browser** quản lý. Nó không phải trang HTML `/login` và không có cùng cách quản lý form/CSRF/session.

Tránh bật Basic challenge vô ý cho giao diện web nếu bạn muốn mọi người dùng đăng nhập qua một form nhất quán.

## 8. Java 17 độc lập: tự in 302, 401, 200 và header

Để quan sát mà không cần IDE, bạn có thể dùng `java.net.http.HttpClient` thuộc JDK 17. Chương trình dưới đây **chạy độc lập bằng javac/java**, nhưng yêu cầu ứng dụng Spring Boot ở mục 5 đang chạy tại `localhost:8080`.

Tạo tệp **`HttpResponseObserver.java`**:

```java
import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

public class HttpResponseObserver {
    private static final String BASE = "http://localhost:8080";

    static void observe(HttpClient client, String path)
            throws IOException, InterruptedException {

        HttpRequest request = HttpRequest.newBuilder()
            .uri(URI.create(BASE + path))
            .GET()
            .build();

        HttpResponse<Void> response = client.send(
            request,
            HttpResponse.BodyHandlers.discarding()
        );

        boolean loginRedirect = response.statusCode() == 302
            && response.headers()
                .firstValue("Location")
                .map(s -> s.contains("/login"))
                .orElse(false);

        boolean basicChallenge = response.statusCode() == 401
            && response.headers()
                .firstValue("WWW-Authenticate")
                .map(s -> s.startsWith("Basic"))
                .orElse(false);

        System.out.println(path + " status=" + response.statusCode()
            + " loginRedirect=" + loginRedirect
            + " basicChallenge=" + basicChallenge);
    }

    public static void main(String[] args)
            throws IOException, InterruptedException {

        HttpClient client = HttpClient.newBuilder()
            .followRedirects(HttpClient.Redirect.NEVER)
            .build();

        observe(client, "/home");
        observe(client, "/api/me");
        observe(client, "/public");
    }
}
```

Biên dịch/chạy từ thư mục chứa file:

```bash
javac HttpResponseObserver.java
java HttpResponseObserver
```

Với ứng dụng ví dụ đang chạy và không có cookie hoặc thông tin đăng nhập gửi kèm, **stdout dự kiến chính xác**:

```text
/home status=302 loginRedirect=true basicChallenge=false
/api/me status=401 loginRedirect=false basicChallenge=true
/public status=200 loginRedirect=false basicChallenge=false
```

Lý do kết quả ổn định trong ví dụ:

- `Redirect.NEVER` giữ lại 302, không tự truy cập `/login`.
- Chương trình không thêm cookie, Authorization header hoặc cấu hình thông tin xác thực.
- `/home` thuộc web chain và yêu cầu login.
- `/api/me` thuộc Basic chain và gửi `WWW-Authenticate` khi chưa xác thực.
- `/public` được `permitAll()`.
- So sánh boolean thay vì in nguyên realm/Location/session ID giúp tránh phụ thuộc vào chi tiết URL có thể thay đổi.

Nếu chạy trước khi server khởi động hoặc port không đúng, chương trình sẽ báo lỗi kết nối, không in đủ ba dòng. Nếu cấu hình của bạn khác ví dụ, hãy dựa vào response thực thay vì mặc định kết quả phải giống.

## 9. Kiểm thử tự động bằng Spring Security Test và MockMvc

Kiểm tra thủ công giúp hiểu request. Để bảo vệ hành vi lâu dài, viết **integration tests** với Spring Security filter chain thật. Trong dự án ở mục 5 đã có `spring-boot-starter-test` và `spring-security-test`.

Tạo `src/test/java/example/loginobservation/ObservationSecurityTest.java`:

```java
package example.loginobservation;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestBuilders.formLogin;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers.authenticated;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ObservationSecurityTest {

    @Autowired
    MockMvc mvc;

    @Test
    void anonymousWebPageRedirectsToLogin() throws Exception {
        mvc.perform(get("/home").accept(MediaType.TEXT_HTML))
            .andExpect(status().isFound())
            .andExpect(header().string(
                HttpHeaders.LOCATION, containsString("/login")));
    }

    @Test
    void generatedLoginPageIsHtml() throws Exception {
        mvc.perform(get("/login"))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                MediaType.TEXT_HTML));
    }

    @Test
    void anonymousApiGetsBasicChallenge() throws Exception {
        mvc.perform(get("/api/me"))
            .andExpect(status().isUnauthorized())
            .andExpect(header().string(
                HttpHeaders.WWW_AUTHENTICATE,
                containsString("Basic")));
    }

    @Test
    void validBasicCredentialsIdentifyUser() throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic("alice", "demo-alice-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.user").value("alice"));
    }

    @Test
    void invalidBasicCredentialsFail() throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic("alice", "wrong-password")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void roleControlsAdminApi() throws Exception {
        mvc.perform(get("/api/admin")
                .with(httpBasic("alice", "demo-alice-pass")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/api/admin")
                .with(httpBasic("admin", "demo-admin-pass")))
            .andExpect(status().isOk());
    }

    @Test
    void formLoginAuthenticatesAlice() throws Exception {
        mvc.perform(formLogin()
                .user("alice")
                .password("demo-alice-pass"))
            .andExpect(status().is3xxRedirection())
            .andExpect(authenticated().withUsername("alice"));
    }

    @Test
    void csrfStillProtectsPost() throws Exception {
        mvc.perform(post("/notes")
                .with(user("alice").roles("USER")))
            .andExpect(status().isForbidden());
    }

    @Test
    void anonymousPublicPagesStayAvailable() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk());
        mvc.perform(get("/api/public"))
            .andExpect(status().isOk());
    }
}
```

Chạy test:

```bash
./gradlew test --tests example.loginobservation.ObservationSecurityTest
```

Trong Windows PowerShell:

```powershell
.\gradlew.bat test --tests example.loginobservation.ObservationSecurityTest
```

**Kỳ vọng:** chín phương thức test đều pass khi dự án Boot 3, hai chain, user store và controller đúng như trên. Không đưa ra một đoạn stdout Gradle cố định vì plugin, version, daemon và log có thể làm output khác nhau.

### 9.1. MockMvc đang chứng minh điều gì?

- `get("/home")` kiểm tra redirect của **web chain** khi chưa login.
- `get("/login")` kiểm tra default login page.
- `get("/api/me")` kiểm tra challenge của **Basic chain**.
- `httpBasic(...)` gửi header Basic để đi qua cơ chế xác thực và provider của ứng dụng.
- `formLogin()` mô phỏng submit form login, gồm dữ liệu cần thiết cho luồng kiểm thử tương ứng.
- `user(...)` **giả lập** người đã xác thực cho request; hữu ích để tách riêng kiểm thử CSRF/authorization, **không chứng minh password provider hoạt động**.
- `status().isForbidden()` khi thiếu quyền admin chứng minh rule phân quyền đang được thực thi với tài khoản đã xác thực.
- CSRF test chứng minh POST thiếu token bị từ chối khi lớp CSRF bật.

Muốn kiểm tra POST **có token hợp lệ**, có thể thêm `.with(csrf())` vào request MockMvc và assert response/side effect phù hợp. Trong ví dụ này, việc thiếu token đã đủ chứng minh lớp bảo vệ hoạt động; đừng sửa test bằng cách tắt CSRF.

### 9.2. Tránh test chỉ assert status 200

Một 200 có thể đến từ `/login` hoặc endpoint public, trong khi request riêng tư ban đầu vẫn bị từ chối. Với test, assert đúng **URL, user, role, status, Location, WWW-Authenticate và body**. Với thao tác làm thay đổi dữ liệu, xác minh cả **không có side effect trái phép** khi security chặn request.

## 10. Những trường hợp khiến kết quả khác kỳ vọng

### 10.1. Một SecurityFilterChain bật cả Basic lẫn form

Nếu bạn viết:

```java
http.authorizeHttpRequests(auth -> auth
        .anyRequest().authenticated())
    .formLogin(Customizer.withDefaults())
    .httpBasic(Customizer.withDefaults());
```

thì cách entry point được chọn có thể chịu ảnh hưởng của **request matcher và content negotiation**, đặc biệt với client chấp nhận HTML so với API client. Đây là tình huống khác với hai chain minh họa; đừng kết luận sai chỉ vì `curl` không thấy redirect hoặc browser nhận Basic challenge.

### 10.2. Đã có session đăng nhập

Nếu browser đang giữ session hợp lệ, `GET /home` trả 200. Cửa sổ ẩn danh hoặc xóa cookie của localhost giúp tạo lại tình huống anonymous. `curl` thường không gửi cookie trừ khi bạn yêu cầu; đó là một lý do curl và browser có thể cho kết quả khác.

### 10.3. Header Accept, XHR và request cache

Header `Accept` mô tả representation mà client mong muốn, không phải bằng chứng identity. Một số cấu hình mặc định dùng media-type matching để chọn entry point. Với HTTP Basic, các tình huống XHR có thể làm response khác ở chi tiết challenge để tránh popup đăng nhập. Ngoài ra, form login có thể lưu request ban đầu và redirect trở lại sau login; HTTP Basic thường không cần request cache theo cùng cách.

### 10.4. Reverse proxy, path prefix và HTTPS

Nếu chạy qua gateway, `Location` có thể chứa URL tuyệt đối, scheme hoặc host khác, nhất là khi forwarded headers chưa được cấu hình đúng. Khi quan sát, kiểm tra cả URL người dùng thực sự gọi, base path, `X-Forwarded-*`/`Forwarded` theo ranh giới tin cậy và chiến lược redirect. Không tự tin các forwarded header do bất kỳ client nào đưa vào; chúng chỉ đáng tin khi được proxy đáng tin cậy thiết lập và ứng dụng cấu hình xử lý phù hợp.

### 10.5. POST thiếu CSRF token

POST tới endpoint dùng cookie/session hoặc chain bật CSRF có thể trả **403** dù credentials hoặc user đang login đã hợp lệ. CSRF xử lý tính hợp lệ của **request thay đổi trạng thái**, khác với authentication. Để quan sát 302 khi chưa đăng nhập, hãy dùng GET tới tài nguyên riêng tư; với POST, kiểm tra cả CSRF trước khi phân tích kết quả.

### 10.6. Custom AuthenticationEntryPoint hoặc AccessDeniedHandler

Nếu dự án đã cấu hình `exceptionHandling` hoặc các handler riêng cho API, có thể nhận JSON 401/403 thay vì challenge hoặc redirect. Nên đọc `SecurityFilterChain` và custom handler của đúng request trước khi quy kết behavior mặc định.

### 10.7. Không khớp đúng chain

Với nhiều chain, thứ tự `@Order` và `securityMatcher` rất quan trọng:

- Chain khớp đầu tiên được chọn.
- Rule `anyRequest()` chỉ áp dụng **trong chain đã chọn**.
- Nếu không có chain fallback phù hợp, có thể có URL không được Spring Security bảo vệ.
- Nếu form login `/login` vô tình rơi vào API chain chỉ có Basic, trang login có thể không hoạt động như dự định.
- Hãy thử cả `/api/me`, `/home`, `/login`, `/admin` và đường dẫn không khai báo để kiểm chứng.

### 10.8. 401 và 403 do các lớp bảo mật khác

Đừng đọc response code rồi đoán một nguyên nhân duy nhất. API có thể trả 401 vì token sai hạn/issuer/audience, 403 do authority thiếu, CSRF sai hoặc policy trên object từ chối. Web có thể redirect tới OAuth2 IdP thay vì `/login` nếu dùng OAuth2 login. Hãy kết hợp Network log, server log được làm sạch và integration test.

## 11. Quan sát an toàn: không để lộ credentials và session

Khi debug authentication, điều cần biết là **đường nào, status gì, handler nào và policy nào**, không phải bí mật cụ thể của người dùng. Không ghi vào log hoặc tài liệu công khai:

- `Authorization` header chứa Basic credentials/Bearer token;
- Password, password hash, access/refresh token hoặc cookie session ID;
- CSRF token thực của phiên người dùng;
- Stack trace hoặc lỗi trả về chứa secret;
- Tài khoản production với password có thật.

Có thể ghi **mã request**, endpoint đã được chuẩn hóa, status, loại authentication/authorization exception, tên security filter hoặc principal ID được xử lý theo chính sách riêng tư. Dùng quyền đọc log phù hợp.

Đừng bật debug log security rộng rãi trong production chỉ để kiểm tra một 401; một số log có thể chứa thông tin nhạy cảm tùy hệ thống. Ưu tiên kiểm thử cục bộ và logging có kiểm soát, giới hạn thời gian.

### 11.1. Form login và HTTP Basic phù hợp khi nào?

| Tiêu chí | Form login | HTTP Basic |
| --- | --- | --- |
| Phù hợp thường gặp | Ứng dụng web có người dùng tương tác với giao diện | API client nội bộ, công cụ thử nghiệm, tích hợp đơn giản |
| Cách gửi credentials | Form submit, thường tạo session sau login | `Authorization: Basic ...` trên request |
| Khi anonymous | Thường 302 đến trang login | Thường 401 và Basic challenge |
| Trải nghiệm trong browser | HTML login form tùy biến | Native browser credential dialog có thể xuất hiện |
| Rủi ro quan trọng | Session/cookie, CSRF, quản lý logout | Credentials lặp trên mỗi request, cần TLS và bảo vệ secret |
| Điều không tự giải quyết | Quyền object/tenant, XSS, business logic | Quyền object/tenant, token lifecycle, business logic |

Trong ứng dụng production có người dùng, lựa chọn form login, OAuth2/OIDC, JWT resource server, session hay các cơ chế khác nên dựa vào kiến trúc và threat model. HTTP Basic là công cụ học tập dễ quan sát, không nên tự suy ra nó thích hợp cho mọi ứng dụng API hiện đại.

## 12. Quy trình debug nhanh khi không thấy kết quả mong muốn

Khi browser không redirect hoặc curl không ra 401, kiểm tra theo thứ tự:

1. **Đúng URL, port, method?** Server có chạy không? Endpoint thực tế ở `/home` hay nằm dưới context path?
2. **Đúng chain?** `securityMatcher` và `@Order` có khiến request đi qua chain mong muốn không?
3. **Đã bật cơ chế cần quan sát?** `formLogin(...)` cho web, `httpBasic(...)` cho API? Có custom entry point?
4. **Request đã có credentials/session?** Có cookie cũ hoặc Authorization header vô tình được trình duyệt/công cụ tự thêm không?
5. **Status và Location?** Với anonymous web GET mong đợi 302 tới `/login`; curl nên bỏ `-L`.
6. **401 và WWW-Authenticate?** Với Basic anonymous mong đợi challenge; kiểm tra các header đặc biệt và handler custom.
7. **403 do gì?** Thiếu role, sai CSRF token, object policy, CORS/browser constraints hay cơ chế khác?
8. **UserDetailsService/PasswordEncoder?** User có tồn tại, password có được hash/compare đúng, account có bị khóa hay vô hiệu không?
9. **Trường hợp public?** Một rule `permitAll()` khớp trước matcher riêng tư có thể làm endpoint trả 200 khi bạn nghĩ nó cần login.
10. **Test thực tế?** Dùng MockMvc/HTTP client tạo request anonymous, Basic sai, Basic đúng, form login, user thiếu role và CSRF thiếu.

Sơ đồ chẩn đoán:

```text
Request chưa có identity
  |
  +-- Có rule permitAll()? ---- Có ---> Endpoint có thể trả 200
  |
  +-- Chain bảo vệ chọn gì?
       |
       +-- Form login -------> 302 tới /login (với cấu hình web mẫu)
       |
       +-- HTTP Basic -------> 401 + WWW-Authenticate
       |
       +-- Custom handler ---> Xem response theo cấu hình riêng
       
Identity đã xác thực
  |
  +-- Thiếu role/permission --> 403 hoặc policy từ chối phù hợp
  |
  +-- Đủ quyền -------------> Tiếp tục controller/service
  |
  +-- POST thiếu CSRF -------> Có thể 403 trước business operation
```

## 13. Lỗi hiểu sai thường gặp

1. **“Trình duyệt hiển thị login 200 nghĩa là /home được truy cập.”** Sai: hãy xem request đầu tiên `/home` và redirect 302.
2. **“Mọi request anonymous đều trả 401.”** Với form login, endpoint riêng tư thường redirect; API Basic thường challenge.
3. **“401 và 403 giống nhau.”** Một bên thường là thiếu/không hợp lệ credentials, bên kia là bị từ chối quyền hoặc cơ chế bảo vệ khác.
4. **“Có HTTP Basic là có trang /login.”** Basic challenge của HTTP khác HTML form login.
5. **“Base64 là mã hóa password an toàn.”** Base64 có thể giải mã; HTTPS là bắt buộc cho thông tin đăng nhập thật.
6. **“Bật starter-security thì mọi cấu hình custom vẫn tự có form và Basic.”** Khi tự tạo chain, hãy bật tường minh cơ chế muốn dùng.
7. **“Thêm một chain /api/** không cần chain fallback.”** Request ngoài /api có thể mất bảo vệ của Spring Security nếu không có chain khớp.
8. **“isAuthenticated là đủ để phân quyền.”** Cần xét anonymous, role/authority, object/tenant và ngữ cảnh.
9. **“Đã có role USER thì xem được mọi đơn.”** Đăng nhập và role không thay thế object-level authorization.
10. **“POST bị 403 vì Spring Security hỏng.”** CSRF có thể đang hoạt động đúng; hãy kiểm tra token/method/chính sách.
11. **“curl -L giúp nhìn rõ redirect ban đầu.”** Khi tự follow redirect, kết quả cuối có thể che status 302 đầu tiên.
12. **“Cookie JSESSIONID có nghĩa đã đăng nhập.”** Session có thể tồn tại trước login; cần kiểm tra context và quyền thật.
13. **“Đăng nhập thành công bằng @WithMockUser chứng minh password đúng.”** Mock user giả lập context, chưa chạy password provider.
14. **“Chỉ assert 200 là đủ.”** Cần kiểm tra URL, status của request đầu, Location, challenge, authority và side effect.
15. **“Có thể chụp màn hình Authorization header để báo lỗi.”** Có nguy cơ lộ bí mật và chiếm quyền; luôn xóa/che credentials.

## 14. Bài tập và câu hỏi tự kiểm tra

### Bài tập A: quan sát 302 và 401

Với ứng dụng ví dụ, dùng cửa sổ ẩn danh truy cập `/home` và dùng curl truy cập `/api/me` không có credentials. Ghi lại **status, Location và WWW-Authenticate** mà không sao chép giá trị secret. Giải thích vì sao hai endpoint có cách phản hồi khác nhau.

### Bài tập B: nhận diện 403

Với `alice`, gọi `/api/me` và `/api/admin` bằng HTTP Basic. Tại sao request đầu trả 200 nhưng request sau trả 403? Dùng `admin` gọi lại để kiểm tra rule.

### Bài tập C: CSRF và trạng thái login

Thử `POST /notes` trong test với người dùng giả lập đã xác thực nhưng thiếu CSRF token; kết quả thế nào? Nếu dùng browser form login, trang mặc định quản lý trường CSRF bằng cách nào? Tại sao không nên tắt CSRF để “sửa” 403?

### Bài tập D: thay đổi cấu hình chain

Tạm đổi `webChain` để bật cả `formLogin` lẫn `httpBasic` và thử các header Accept khác nhau. Ghi lại behavior thực tế, sau đó trở lại cấu hình hai chain để thấy sự khác biệt. Đừng áp dụng thay đổi thử nghiệm vào production.

**Câu hỏi nhanh**

1. `WWW-Authenticate` xuất hiện ở request hay response, và làm gì?
2. `Authorization` xuất hiện ở đâu, chứa điều gì khi dùng Basic?
3. Tại sao `GET /login` trả 200 không chứng minh `GET /home` trả 200?
4. AuthenticationEntryPoint được dùng khi nào?
5. Tài khoản đã xác thực nhưng thiếu `ROLE_ADMIN` thường nhận status nào?
6. Vì sao một request POST chưa đăng nhập có thể nhận 403 thay vì 302?
7. Khi có nhiều `SecurityFilterChain`, rule matcher nào quyết định chain được chọn?
8. Vì sao không thể coi HTTP Basic là encryption cho password?
9. `@WithMockUser` và `httpBasic()` trong MockMvc kiểm tra những khía cạnh khác nhau nào?
10. Khi sử dụng một chain chứa cả form login và Basic, vì sao không thể áp dụng cứng quy tắc “browser = 302, curl = 401” cho mọi request?

**Đáp án gợi ý:**

1. Header response challenge từ server, thông báo HTTP authentication scheme.
2. Header request từ client, chứa chuỗi Base64 username:password khi Basic.
3. Vì `/home` có thể chỉ redirect 302 sang `/login`; HTML login riêng có status 200.
4. Khi security cần khởi tạo quá trình xác thực cho request không đủ điều kiện vào tài nguyên.
5. Thường 403, do authorization từ chối.
6. CSRF filter có thể chặn request thay đổi trạng thái trước khi xử lý yêu cầu đăng nhập/authorization như GET.
7. `securityMatcher` của từng chain cùng thứ tự `@Order`; sau đó `requestMatchers` quyết định quyền trong chain.
8. Base64 chỉ là encoding có thể đảo ngược, không bảo vệ bí mật trên mạng.
9. Mock user tạo danh tính giả lập để test policy; Basic gửi credentials để kiểm tra cơ chế xác thực đã cấu hình.
10. Vì entry point có thể dùng content negotiation, request matcher và custom exception handlers.

## 15. Tài liệu chính thức

- [Spring Security 6.5 – Form Login](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/form.html)
- [Spring Security 6.5 – HTTP Basic Authentication](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/basic.html)
- [Spring Security 6.5 – Java Configuration, nhiều SecurityFilterChain](https://docs.spring.io/spring-security/reference/6.5/servlet/configuration/java.html)
- [Spring Security 6.5 – Servlet Architecture và FilterChainProxy](https://docs.spring.io/spring-security/reference/6.5/servlet/architecture.html)
- [Spring Security 6.5 – Testing HTTP Basic with MockMvc](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/http-basic.html)
- [Spring Security 6.5 – Spring MVC Test Integration](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/)
- [Spring Security 6.5 – CSRF Protection](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html)
