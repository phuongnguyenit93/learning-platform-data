# Header `Authorization` và luồng xác thực HTTP Basic

## 1. HTTP Basic giải quyết vấn đề gì?

HTTP Basic là cơ chế xác thực HTTP tiêu chuẩn (RFC 7617): client gửi tên đăng nhập và mật khẩu trong header `Authorization` để server xác định người đang thực hiện request. Nó thường phù hợp với công cụ dòng lệnh, API nội bộ được bảo vệ bằng HTTPS, hoặc môi trường thử nghiệm. Đây là **cơ chế xác thực (authentication)**; việc người đã xác thực có được truy cập tài nguyên hay không thuộc bước **phân quyền (authorization)**.

Điểm cốt lõi: với HTTP Basic, client tạo chuỗi `username:password`, mã hóa các byte của chuỗi ấy bằng Base64 rồi gửi kèm request. Base64 chỉ là **biểu diễn dữ liệu, không phải mã hóa bảo mật**; bất kỳ ai đọc được header đều có thể giải mã về thông tin đăng nhập. Vì thế Basic phải đi cùng HTTPS/TLS và các biện pháp bảo vệ mật khẩu.

Hai header có vai trò khác nhau:

| Header | Hướng | Ý nghĩa |
| --- | --- | --- |
| `Authorization: Basic …` | Client → server | Client trình thông tin đăng nhập cho request hiện tại. |
| `WWW-Authenticate: Basic realm="…"` | Server → client, thường kèm HTTP 401 | Server thông báo cơ chế xác thực được hỗ trợ và yêu cầu client cung cấp credential. |

`Authorization` **không** đồng nghĩa với việc request đã được cho phép. Server còn phải kiểm tra credential và quyền của người dùng.

## 2. Cấu trúc header `Authorization: Basic`

Cú pháp:

~~~http
Authorization: Basic <base64(username:password)>
~~~

Ví dụ với username `user` và password `pass`:

1. Nối thành chuỗi `user:pass` (dấu `:` đầu tiên là dấu phân tách username/password).
2. Chuyển chuỗi thành các byte theo bộ mã ký tự mà hai phía thống nhất.
3. Base64-encode thành `dXNlcjpwYXNz`.
4. Gửi header:

~~~http
GET /private HTTP/1.1
Host: example.test
Authorization: Basic dXNlcjpwYXNz
~~~

Giải mã phần sau từ khóa `Basic` sẽ thu lại `user:pass`; server **không** so sánh nguyên chuỗi Base64 với mật khẩu trong database. Nó tách username/password rồi chuyển sang cơ chế kiểm tra credential của ứng dụng.

**Những chi tiết dễ nhầm:**

- `Basic` là tên authentication scheme; chuỗi Base64 đứng sau dấu cách. Trường header HTTP không phân biệt chữ hoa/chữ thường theo tên trường.
- Dấu hai chấm đầu tiên phân tách username và password; username không được chứa dấu `:`, password có thể chứa dấu `:`.
- RFC 7617 để ngỏ encoding mặc định của credential nhằm tương thích hệ thống cũ. Server có thể nêu `charset="UTF-8"` trong *challenge* `WWW-Authenticate` (đây là tham số phía server, không phải tham số gắn vào chuỗi credential); khi dùng ký tự ngoài ASCII, hai bên phải thống nhất encoding.
- Base64 không giấu được mật khẩu, cũng không tạo token đăng nhập có thời hạn hay chữ ký.

## 3. Chu trình HTTP khi chưa có credential

Giả sử `GET /private` đòi hỏi đăng nhập.

~~~http
GET /private HTTP/1.1
Host: localhost:8080
~~~

Nếu request không có thông tin xác thực hợp lệ, server có thể đáp:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="Realm"
~~~

`401 Unauthorized` ở đây có nghĩa là **chưa xác thực thành công** (tên status dễ gây nhầm với phân quyền). `WWW-Authenticate` là lời yêu cầu xác thực (*challenge*). `realm` là tên không gian bảo vệ mà server quảng bá; `Realm` chỉ là giá trị minh họa, có thể được cấu hình khác.

Client có thể yêu cầu người dùng nhập tài khoản/mật khẩu rồi gửi lại request:

~~~http
GET /private HTTP/1.1
Host: localhost:8080
Authorization: Basic dXNlcjpwYXNz
~~~

Không phải client nào cũng bắt buộc đợi `401`: công cụ như cURL có thể gửi Basic credential ngay request đầu tiên (*preemptive authentication*). Browser có thể hiển thị hộp thoại đăng nhập khi nhận challenge và có thể giữ lại credential trong một khoảng thời gian; không nên xem hành vi cache đó là phiên đăng nhập có kiểm soát của ứng dụng.

## 4. Luồng bên trong Spring Security (Servlet)

Với ứng dụng Spring MVC sử dụng `SecurityFilterChain` và bật `httpBasic`, luồng điển hình là:

1. **Request vào security filter chain.** Các filter làm việc trước controller. Nếu request có `Authorization: Basic …`, `BasicAuthenticationFilter` xử lý phần credential đó.
2. **Tạo đối tượng xác thực chưa được chứng thực.** `BasicAuthenticationFilter` giải mã credential và tạo `UsernamePasswordAuthenticationToken` chứa username/password, rồi gửi đối tượng này tới `AuthenticationManager`.
3. **Kiểm tra credential.** `AuthenticationManager` (thường là `ProviderManager`) giao cho `AuthenticationProvider` thích hợp. Với tài khoản username/password thông dụng, `DaoAuthenticationProvider` có thể dùng `UserDetailsService` tải user và `PasswordEncoder.matches(...)` so sánh mật khẩu đầu vào với mật khẩu đã băm.
4. **Nếu đúng**, provider trả về `Authentication` đã xác thực cùng danh sách quyền (`GrantedAuthority`). Spring Security đặt kết quả vào `SecurityContextHolder` cho request, sau đó tiếp tục chuỗi filter. `AuthorizationFilter` đánh giá quy tắc truy cập; nếu hợp lệ thì controller mới được gọi.
5. **Nếu sai**, ngữ cảnh bảo mật liên quan được làm sạch và `AuthenticationEntryPoint` xử lý thất bại, thông thường trả `401` cùng Basic challenge. Nếu không có credential và tài nguyên yêu cầu đăng nhập, `AuthorizationFilter` từ chối, `ExceptionTranslationFilter` kích hoạt entry point để bắt đầu xác thực.

Sơ đồ tóm tắt (các nhánh có thể phụ thuộc cấu hình):

~~~text
Client → HTTP request
           │
           ├─ Authorization: Basic ... có mặt
           │    → BasicAuthenticationFilter
           │    → UsernamePasswordAuthenticationToken
           │    → AuthenticationManager / AuthenticationProvider
           │         ├─ Sai credential → AuthenticationEntryPoint → 401
           │         └─ Đúng → SecurityContextHolder có Authentication
           │
           └─ Không có Basic credential → chưa được xác thực bằng Basic
                                          (có thể còn cơ chế khác)
                         │
                         ▼
                  AuthorizationFilter
                     ├─ Cho phép → Controller → 2xx
                     ├─ Chưa xác thực, cần đăng nhập → 401/challenge
                     └─ Đã xác thực, thiếu quyền → 403
~~~

Cần phân biệt hai câu hỏi: **“Bạn là ai?”** do authentication xử lý và **“Bạn được làm gì?”** do authorization xử lý. Xác thực thành công không bảo đảm có quyền truy cập mọi endpoint.

Lưu ý với Spring Security Servlet: theo tài liệu tham chiếu, cấu hình HTTP Basic mặc định có thể không đưa header `WWW-Authenticate` và body vào phản hồi 401 cho request mang `X-Requested-With: XMLHttpRequest`, nhằm tránh bật hộp thoại đăng nhập của trình duyệt. Vì vậy khi debug, đừng suy luận “không có `WWW-Authenticate`” nghĩa là server không dùng Basic.

## 5. Ví dụ Spring Boot 3.x / Spring Security 6.x chạy được

Ví dụ sau dùng Java 17+, Spring Web và Spring Security. Mục tiêu là quan sát *trực tiếp* các trạng thái 200, 401, 403 trong một ứng dụng nhỏ. Để tránh một tài khoản thực bị đưa vào mã nguồn, hai credential dưới đây **chỉ là dữ liệu demo**, tạo trong bộ nhớ và dùng BCrypt.

Nếu dự án Gradle đã sử dụng Spring Boot plugin và dependency management, cần hai dependency sau trong `build.gradle` (đây là **đoạn cấu hình**, không phải toàn bộ file build):

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
}
~~~

Tạo file `src/main/java/com/example/basic/BasicDemoApplication.java`:

~~~java
package com.example.basic;

import java.security.Principal;
import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class BasicDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(BasicDemoApplication.class, args);
    }

    @RestController
    static class DemoController {
        @GetMapping("/public")
        Map<String, String> publicPage() {
            return Map.of("message", "public");
        }

        @GetMapping("/private")
        Map<String, String> privatePage(Principal principal) {
            return Map.of("user", principal.getName());
        }

        @GetMapping("/admin")
        Map<String, String> adminPage(Principal principal) {
            return Map.of("admin", principal.getName());
        }
    }
}
~~~

Tạo file `src/main/java/com/example/basic/SecurityConfig.java`:

~~~java
package com.example.basic;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .requestMatchers("/admin").hasRole("ADMIN")
                .anyRequest().authenticated()
            )
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
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
        return new InMemoryUserDetailsManager(
            User.withUsername("reader")
                .password(encoder.encode("demo-pass"))
                .roles("READER")
                .build(),
            User.withUsername("admin")
                .password(encoder.encode("admin-pass"))
                .roles("ADMIN")
                .build()
        );
    }
}
~~~

Ở đây:

- `httpBasic(Customizer.withDefaults())` đăng ký xử lý HTTP Basic. Khi tự cung cấp `SecurityFilterChain`, nên khai báo cơ chế xác thực muốn dùng một cách tường minh.
- `requestMatchers("/public").permitAll()` mở tài nguyên công khai; các đường dẫn còn lại yêu cầu đã đăng nhập. `/admin` còn đòi `ROLE_ADMIN` (Spring Security ánh xạ `hasRole("ADMIN")` tới authority tương ứng).
- `SessionCreationPolicy.STATELESS` biểu thị ứng dụng không tạo/dùng HTTP session để lưu `SecurityContext` cho luồng này. Header Basic vẫn có thể gửi trong **mỗi request**; trạng thái “stateless” không làm Base64 an toàn hơn.
- `BCryptPasswordEncoder` băm và kiểm tra mật khẩu. Đây là demo in-memory; hệ thống thật cần nguồn tài khoản, cơ chế quản lý secret, giới hạn đăng nhập và chính sách vận hành phù hợp.
- Ví dụ chỉ dùng request `GET`, không thay đổi trạng thái trên server. Cấu hình không tắt CSRF mặc định; khi bổ sung POST/PUT/DELETE, phải đánh giá CSRF theo loại client thay vì tự động tắt nó.

Chạy ứng dụng từ dự án Spring Boot đã cấu hình Gradle:

~~~bash
./gradlew bootRun
~~~

Trên Windows có thể dùng `gradlew.bat bootRun`. Đây là ứng dụng Spring Boot dùng thư viện ngoài, vì vậy lệnh `javac` đơn lẻ không đủ classpath; dùng Gradle để biên dịch và chạy.

### Thử với cURL

~~~bash
# Công khai: không cần username/password.
curl -i http://localhost:8080/public

# Không có credential: tài nguyên riêng tư yêu cầu xác thực.
curl -i http://localhost:8080/private

# Đúng credential (demo).
curl -i -u reader:demo-pass http://localhost:8080/private

# Sai mật khẩu.
curl -i -u reader:wrong-pass http://localhost:8080/private

# Đã xác thực nhưng thiếu quyền ADMIN.
curl -i -u reader:demo-pass http://localhost:8080/admin

# Có quyền ADMIN.
curl -i -u admin:admin-pass http://localhost:8080/admin
~~~

Các kết quả chính cần quan sát:

| Request | HTTP status kỳ vọng | Ý nghĩa |
| --- | --- | --- |
| `GET /public` không credential | `200 OK` | Endpoint công khai. |
| `GET /private` không credential | `401 Unauthorized` | Phải xác thực; thường có Basic challenge. |
| `GET /private` với `reader:demo-pass` | `200 OK` | Auth thành công; body JSON có `"user":"reader"`. |
| `GET /private` với mật khẩu sai | `401 Unauthorized` | Credential bị từ chối. |
| `GET /admin` với `reader:demo-pass` | `403 Forbidden` | Đã xác thực nhưng không có `ROLE_ADMIN`. |
| `GET /admin` với `admin:admin-pass` | `200 OK` | Có quyền truy cập; body chứa `"admin":"admin"`. |

Các status trên áp dụng cho **cấu hình ví dụ này**. Một ứng dụng khác có thể thay đổi entry point, handler lỗi, chính sách quyền hoặc chuỗi filter, khiến chi tiết phản hồi khác đi. Các dòng `curl` không yêu cầu viết Base64 thủ công; tùy client, `-u` có thể gửi Basic ngay request đầu tiên. Nếu PowerShell ánh xạ lệnh `curl` sang công cụ khác, gọi `curl.exe`.

**Không dùng tài khoản thật trong câu lệnh mẫu, log, screenshot hoặc lịch sử shell.** Với credential thật, phương án cung cấp secret an toàn phụ thuộc môi trường vận hành; tham số `-u username:password` hữu ích cho demo nhưng có thể lộ trong command history/process list.

## 6. Vì sao 401 khác 403?

| Tình huống | Diễn giải thường gặp | Kết quả |
| --- | --- | --- |
| Chưa gửi credential, endpoint yêu cầu đăng nhập | Chưa có danh tính được chứng thực | `401` cùng challenge Basic (có ngoại lệ cấu hình). |
| Gửi Basic nhưng username/password sai | Authentication thất bại | `401`. |
| Đã đăng nhập nhưng chỉ có `ROLE_READER`, endpoint yêu cầu `ROLE_ADMIN` | Authorization thất bại | `403`. |
| Credential đúng và đủ quyền | Được phép đi tiếp đến controller | Response nghiệp vụ, thường `2xx`. |

Mã `403` có thể xuất hiện vì nguyên nhân khác (ví dụ chặn bởi CSRF filter), nên cần đọc log đúng filter và ngữ cảnh request; không mặc định mọi 403 đều do thiếu role.

## 7. Điểm bảo mật và giới hạn cần hiểu

1. **Luôn sử dụng HTTPS.** Base64 giải mã được ngay. HTTP Basic không tự bảo vệ đường truyền, chống nghe lén, chống replay hay giới hạn vòng đời credential. Bảo vệ cả kết nối client → reverse proxy và những chặng phù hợp trong hạ tầng.
2. **Gửi lại credential theo request.** Basic không phải session token, OAuth access token hay JWT. Client/browser có thể nhớ credential, nhưng việc đó không mang theo quyền thu hồi hoặc hạn dùng token riêng. Thay đổi/thu hồi mật khẩu là một cách ngăn credential Basic cũ được chấp nhận.
3. **Không để lộ `Authorization`.** Tránh ghi nguyên header vào access log, tracing, analytics, exception message, màn hình chia sẻ hoặc công cụ debug. Kiểm tra proxy/gateway có chuyển tiếp header đúng và có che dữ liệu nhạy cảm khi log hay không.
4. **Băm mật khẩu phía server.** Không lưu mật khẩu rõ hoặc Base64 như cách “mã hóa dữ liệu”. Dùng password hash phù hợp (`BCrypt`, `Argon2` theo hệ thống) và xác minh bằng `PasswordEncoder`. Phân quyền luôn thực hiện phía server.
5. **Không vô hiệu CSRF một cách máy móc.** Basic không dùng cookie đăng nhập của ứng dụng, nhưng browser có thể tự gửi lại HTTP Basic credential đã cache. Vì vậy API được truy cập bởi browser vẫn phải đánh giá CSRF nếu có thao tác thay đổi dữ liệu; một API chỉ dùng client không tự gửi credential có mô hình rủi ro khác.
6. **Bảo vệ chống dò mật khẩu.** Basic không tự cung cấp MFA, rate limiting, khóa/giãn thử sai, phát hiện bất thường hay quản lý credential. Thêm các cơ chế này theo yêu cầu hệ thống. Chỉ cấp quyền tối thiểu cho từng user/endpoint.
7. **Chú ý CORS và cache.** CORS quản lý việc JavaScript trình duyệt đọc response khác origin; nó không thay thế authentication/authorization. Không cache nhầm response riêng tư ở cache dùng chung; áp dụng `Cache-Control` phù hợp với dữ liệu nhạy cảm.

Khi hệ thống cần đăng nhập người dùng cuối, logout rõ ràng, MFA, token có thời hạn, quyền ủy nhiệm hoặc đăng nhập qua nhà cung cấp danh tính, hãy đánh giá cơ chế phiên/cookie hoặc OAuth2/OIDC thích hợp. HTTP Basic có ưu điểm là đơn giản, nhưng đánh đổi bằng việc truyền credential gốc lặp lại.

## 8. Cách tự kiểm tra và gỡ lỗi

- **Đọc request đầu vào:** có đúng tên header `Authorization` và scheme `Basic` không? Base64 có giải mã thành `username:password` đúng như client dự định không? Chỉ kiểm tra với credential demo hoặc trên hệ thống kiểm soát; không đưa thông tin thật vào log.
- **Phân biệt 401 và 403:** 401 hướng tới cơ chế xác thực/credential/entry point; 403 hướng tới quyền truy cập hoặc filter khác như CSRF. Đừng sửa rule quyền trước khi biết request thực sự đã được xác thực.
- **Kiểm tra filter chain:** ứng dụng có `httpBasic(...)` trong đúng `SecurityFilterChain` phục vụ URL không? Các `securityMatcher`, `requestMatchers` và thứ tự chain có khớp endpoint không?
- **Kiểm tra backend xác thực:** `UserDetailsService` tải đúng user? User có trạng thái enabled/locked/expired? Mật khẩu đã mã hóa đúng `PasswordEncoder`? Authority có tiền tố `ROLE_` phù hợp khi dùng `hasRole`?
- **Kiểm tra client và gateway:** client có gửi header qua HTTPS đến đúng host/port không? Reverse proxy có bỏ `Authorization` không? Trình duyệt có cache credential cũ hoặc có request `X-Requested-With: XMLHttpRequest` ảnh hưởng đến challenge hiển thị không?
- **Đối với ký tự Unicode:** xem lại encoding và `charset="UTF-8"` của challenge. Bộ mã không đồng nhất có thể khiến mật khẩu đúng trên giao diện nhưng byte gửi đến server khác.

Một phép thử đáng tin phải chứng minh đủ ba tình huống: **không có credential → 401**, **credential đúng nhưng thiếu quyền → 403**, **credential đúng và đủ quyền → truy cập thành công**. Thử thêm mật khẩu sai và trường hợp qua reverse proxy khi triển khai thực tế.

## 9. Ghi nhớ

- `Authorization: Basic …` là **request header mang credential**; `WWW-Authenticate: Basic realm="…"` là **response challenge** của server.
- Base64 giúp vận chuyển `username:password` trong header, **không bảo mật** credential; phải có HTTPS.
- Trong Spring Security Servlet, `BasicAuthenticationFilter` xử lý Basic credential, `AuthenticationManager` cùng provider xác thực, `SecurityContextHolder` giữ kết quả cho request, và `AuthorizationFilter` quyết định quyền.
- `401` nói về việc chưa xác thực thành công; `403` thường là đã xác thực nhưng không được phép (hoặc bị chặn bởi filter như CSRF).
- HTTP Basic không tự có phiên hay token hết hạn. Cần cân nhắc kỹ khả năng gửi lại credential, bảo vệ log, hạn chế quyền và rủi ro CSRF với trình duyệt.

### Tài liệu tham khảo

- RFC 7617 — The 'Basic' HTTP Authentication Scheme: https://www.rfc-editor.org/rfc/rfc7617
- Spring Security Reference — HTTP Basic Authentication (Servlet): https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/basic.html
- Spring Security Reference — CSRF (Servlet): https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html
