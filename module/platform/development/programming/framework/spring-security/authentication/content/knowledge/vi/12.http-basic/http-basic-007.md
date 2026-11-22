# Giới hạn đăng xuất, xử lý lỗi và tách Basic khỏi chuỗi đăng nhập biểu mẫu

## 1. Ba vấn đề cần phân biệt

Trong ứng dụng Spring Security Servlet, HTTP Basic và form login đều có thể xác thực bằng username/password, nhưng chúng **khác nhau ở cách client gửi credential, cách duy trì trạng thái và trải nghiệm khi thất bại**.

- **HTTP Basic:** mỗi request có thể mang header `Authorization: Basic <base64(username:password)>`. Client hoặc trình duyệt có thể giữ và gửi lại credential. Server xác thực request dựa trên credential đang nhận.
- **Form login:** người dùng nhập tài khoản vào form; sau khi xác thực thành công, ứng dụng web thường lưu `SecurityContext` qua HTTP session và trình duyệt gửi cookie phiên, ví dụ `JSESSIONID`, ở các request tiếp theo.
- **Logout:** với phiên đăng nhập biểu mẫu, server có thể hủy session để chặn việc tái sử dụng phiên cũ. Với Basic, việc hủy session hoặc xóa `SecurityContext` **không làm cho trình duyệt/client ngừng sở hữu hoặc ngừng gửi credential**.

Vì vậy một hệ thống hỗn hợp nên xác định rõ endpoint nào dùng Basic, endpoint nào dùng form login, phản hồi xác thực thất bại của từng nhóm là gì và logout tác động đến trạng thái nào.

Bài này tập trung vào **Spring Security Servlet (Spring Boot 3.x, Spring Security 6.x, Java 17+)**. Với Spring WebFlux, cấu hình filter chain và API khác; không chép nguyên ví dụ Servlet sang Reactive.

## 2. Vì sao HTTP Basic không có “logout” tương đương form login?

### 2.1. Form login có phiên đăng nhập phía server

Luồng form login thường gặp:

~~~text
Browser
  ├─ GET /web/me (chưa có phiên)
  │      → 302 redirect /login
  ├─ GET /login → trang đăng nhập
  ├─ POST /login + username/password + CSRF token
  │      → xác thực thành công, lưu SecurityContext qua session
  │      → browser nhận/giữ session cookie
  ├─ GET /web/me + session cookie → nội dung riêng tư
  └─ POST /logout + CSRF token
         → LogoutFilter chạy các LogoutHandler
         → xóa SecurityContext, vô hiệu session
         → chuyển về /login?logout (theo cấu hình)
~~~

Khi session bị vô hiệu, **cookie phiên cũ không còn đại diện cho một phiên đăng nhập hợp lệ**. Đây là ý nghĩa cốt lõi của logout theo session. Xóa cookie ở trình duyệt là bước dọn dữ liệu bổ sung; server vẫn cần chặn việc tái sử dụng session bị hủy.

Spring Security thường cung cấp `LogoutFilter` và `SecurityContextLogoutHandler`. Tùy cấu hình, các thao tác bao gồm xóa `SecurityContext`, vô hiệu hóa `HttpSession` và dọn trạng thái Remember Me. Khi bật CSRF mặc định, thao tác logout thực sự thường là **POST /logout có CSRF token hợp lệ**; `GET /logout` có thể chỉ hiện trang xác nhận. Không xem request GET đến URL logout là cách đăng xuất mặc định.

### 2.2. HTTP Basic không tạo một credential “đã đăng nhập” để hủy

Luồng Basic có thể như sau:

~~~text
Client
  ├─ GET /api/me + Authorization: Basic ...
  │      → server kiểm tra username/password → 200
  ├─ GET /api/me + cùng Authorization: Basic ...
  │      → server kiểm tra lại credential → 200
  └─ Server xóa SecurityContext hoặc hủy HTTP session
         → client vẫn có username/password
         → GET /api/me + Authorization: Basic ... → vẫn có thể 200
~~~

Ngay cả khi gọi `/logout` và server trả thông báo “đã đăng xuất”, client có thể gửi lại Basic credential hợp lệ ở request tiếp theo. `SecurityContextHolder.clearContext()` chỉ xóa ngữ cảnh của luồng xử lý; `HttpSession.invalidate()` chỉ làm mất session tương ứng. **Không thao tác nào tự thu hồi username/password của HTTP Basic hoặc buộc browser quên credential đã cache.**

Với Basic dùng theo kiểu stateless, không có server session dành riêng cho mỗi lần đăng nhập để thu hồi. Hành vi cache credential thuộc client; không có một API HTTP Basic chuẩn bảo đảm mọi trình duyệt xóa credential. Cố gửi `401`, thay `realm` hoặc chuyển hướng đến URL khác để “ép logout” không phải giải pháp đáng tin cậy, bởi hành vi phụ thuộc browser và có thể kích hoạt hộp thoại yêu cầu đăng nhập lại.

### 2.3. Logout Basic thực tế cần làm gì?

| Bối cảnh | Biện pháp đúng với mục tiêu | Giới hạn |
| --- | --- | --- |
| Script, cURL hoặc ứng dụng desktop | Ngừng đính kèm `Authorization`; bỏ credential lưu ở client và dừng tác vụ gửi request | Nếu script vẫn giữ username/password, request tiếp theo vẫn có thể xác thực. |
| Trình duyệt dùng hộp thoại HTTP Basic | Đóng/đổi phiên trình duyệt hoặc xóa credential đã lưu theo hướng dẫn của browser; xác minh bằng request mới | Không có cam kết “logout một nút” nhất quán giữa mọi browser. |
| Web app cần nút Logout rõ ràng | Ưu tiên form login + session, hoặc cơ chế token có vòng đời và thu hồi được | Phải thiết kế state, CSRF và quản lý token đúng. |
| Credential bị lộ / cần chặn tức thì | Khóa tài khoản, đổi/reset password, thu hồi quyền truy cập ở backend và loại bỏ thông tin đã lộ | Hủy riêng một request/session không vô hiệu hóa password còn hiệu lực. |
| API-to-API đơn giản | Có thể tiếp tục dùng Basic **trên HTTPS** với secret được quản lý, xoay vòng và giới hạn quyền | Cần giới hạn thử sai, tránh log credential, quản lý vòng đời secret. |

**Kết luận thực hành:** API Basic không nên hứa “logout xong credential không thể dùng lại” nếu backend vẫn chấp nhận chính username/password đó. Một nút “quên credential” ở client chỉ bảo đảm ứng dụng client ngừng tự gửi nó trong phạm vi client kiểm soát; không vô hiệu credential tại server.

## 3. Xử lý lỗi Basic: trả 401, 403 và challenge đúng ngữ cảnh

### 3.1. HTTP 401: chưa xác thực thành công

Đối với Basic, khi thiếu credential hoặc credential sai, phản hồi thường là:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="api"
Content-Type: application/json;charset=UTF-8

{"error":"unauthorized"}
~~~

Header `WWW-Authenticate` báo client rằng tài nguyên chấp nhận HTTP Basic và chỉ rõ `realm`. Thông điệp JSON là lựa chọn của ứng dụng, **không phải nội dung bắt buộc của RFC**. Khi tùy chỉnh `AuthenticationEntryPoint`, cần quyết định có giữ Basic challenge hay không; client HTTP chuẩn có thể cần nó để biết cách xác thực.

Trong Spring Security, `BasicAuthenticationFilter` xử lý `Authorization: Basic …` và thông báo lỗi xác thực qua `AuthenticationEntryPoint`. Nếu request không mang credential, quy tắc truy cập yêu cầu đăng nhập sẽ khiến `ExceptionTranslationFilter` gọi entry point tương ứng. Request sai password không được tự động “thử tiếp” form login ở filter chain khác.

### 3.2. HTTP 403: đã xác thực nhưng bị từ chối truy cập

Giả sử `reader` xác thực thành công nhưng chỉ có `ROLE_USER`, trong khi `/api/admin` đòi `ROLE_ADMIN`:

~~~http
HTTP/1.1 403 Forbidden
Content-Type: application/json;charset=UTF-8

{"error":"forbidden"}
~~~

Đây là lỗi **phân quyền**. `AccessDeniedHandler` thích hợp để kiểm soát phản hồi 403. Không nên chuyển mọi 403 thành 401: client sẽ tưởng phải nhập mật khẩu lại, trong khi nguyên nhân là thiếu quyền.

Cần nhớ 403 cũng có thể do CSRF hoặc filter bảo mật khác chặn request; không suy luận thiếu role chỉ từ status code mà chưa kiểm tra request, chain và log an toàn.

### 3.3. Lỗi của form login khác Basic

Form login hướng tới trang web và trạng thái phiên. Một ứng dụng cấu hình mặc định có thể đưa người chưa đăng nhập đến trang `/login` qua redirect; khi nhập sai mật khẩu ở form, thường chuyển đến `/login?error`; khi logout thành công có thể chuyển đến `/login?logout`.

| Tình huống | API Basic mong đợi | Trang web form login mong đợi |
| --- | --- | --- |
| Chưa có xác thực | `401`, kèm `WWW-Authenticate` | Redirect đến trang đăng nhập (thường 302). |
| Sai username/password | `401`; không tạo session đăng nhập | Quay lại trang login với trạng thái lỗi. |
| Đã xác thực nhưng thiếu role | `403` | `403` hoặc trang lỗi truy cập tùy cấu hình. |
| Đăng xuất | Client thôi gửi credential; backend vẫn có thể chấp nhận credential cũ | Hủy session, dọn SecurityContext và điều hướng đến trang sau logout. |

Các phản hồi trên là **hợp đồng mong muốn của ví dụ**, không phải cam kết của mọi cấu hình Spring Security. Một chain có cả `formLogin` và `httpBasic` có thể chọn entry point theo request matcher/content negotiation; khi tùy biến, nên kiểm thử thật bằng browser và HTTP client.

### 3.4. Cẩn trọng khi làm JSON error response

- Không trả thông điệp phân biệt “username không tồn tại” với “password sai” cho người dùng bên ngoài; thông điệp quá chi tiết giúp liệt kê tài khoản.
- Không đưa password, giá trị `Authorization`, Base64 credential, session ID hoặc toàn bộ request header vào JSON lỗi, log hay trace.
- Hạn chế thông tin trả cho client, nhưng ghi nhận sự kiện bảo mật đã **che dữ liệu nhạy cảm** đủ để vận hành điều tra.
- Nếu dùng retry/rate limit, áp dụng theo chính sách thực tế; 401 nhiều lần không tự động chặn dò mật khẩu.
- Với browser, nhiều lần nhận Basic challenge có thể làm xuất hiện hộp thoại đăng nhập không mong muốn; đó là lý do cần tách luồng web.

## 4. Một ứng dụng có hai SecurityFilterChain hoạt động như thế nào?

`FilterChainProxy` chọn **SecurityFilterChain đầu tiên có matcher khớp request**. Chain khớp đầu tiên xử lý request; Spring Security không rơi xuống chain sau chỉ vì credential sai hoặc vì rule chặn truy cập.

Ví dụ phân vùng:

~~~text
Request đi vào FilterChainProxy
           │
           ├─ Path bắt đầu /api/**
           │    → @Order(1), API security chain
           │    → HTTP Basic + chính sách API
           │    → 401 challenge / 403 / API controller
           │
           └─ Các path còn lại
                → Web security chain (fallback)
                → Form login + session + logout + CSRF
                → /login /logout /web/** / ...
~~~

Hai khái niệm rất dễ lẫn:

- `http.securityMatcher("/api/**")` quyết định **request có đi vào chain đó hay không**.
- `authorizeHttpRequests(...requestMatchers("/api/admin").hasRole("ADMIN"))` quyết định **quyền trong chain đã được chọn**; nó không chọn chain.

`@Order(1)` làm API chain được xét trước. Web chain không khai báo `securityMatcher` nên làm fallback cho các đường dẫn còn lại. Nếu hai chain đều chỉ match các path hẹp và request không khớp chain nào, nó có thể **không được Spring Security bảo vệ**. Đó là lỗi cấu hình nghiêm trọng.

Cũng cần nhớ endpoint do filter sinh ra phải nằm trong path của chính chain. Nếu form chain chỉ match `/web/**` nhưng vẫn dùng URL mặc định `/login` và `/logout`, các URL này có thể không đến đúng chain; kết quả là login/logout không hoạt động hoặc 404. Ví dụ dưới đây giữ web chain làm fallback để các URL mặc định hoạt động.

## 5. Ví dụ hoàn chỉnh: API dùng Basic, website dùng form login

Ta xây dựng một ứng dụng Spring Boot 3.x / Java 17+ có:

- `GET /api/me` — Basic hợp lệ mới truy cập được.
- `GET /api/admin` — Basic hợp lệ **và** có `ROLE_ADMIN`.
- `GET /web/me` — đăng nhập qua form và session.
- `GET /` — trang dữ liệu công khai để làm đích mặc định.
- `GET /login`, `POST /login`, `POST /logout` — sử dụng endpoint do Spring Security tạo trong web chain.

Ví dụ dùng các endpoint GET chỉ đọc cho API để minh họa flow xác thực. CSRF **được giữ bật**; nếu sau này thêm API POST/PUT/DELETE, cần xác định API có được browser gọi và có tự gửi credential hay không trước khi quyết định cấu hình CSRF.

### 5.1. Dependency

Trong dự án đã cấu hình Spring Boot Gradle plugin và dependency management, cần:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
}
~~~

Đây là phần `dependencies`, không phải toàn bộ `build.gradle`. Các lớp bên dưới dùng Jakarta Servlet API do Spring Boot 3 cung cấp. Nếu chưa có dự án, tạo dự án Java 17+ với Spring Web và Spring Security từ Spring Initializr rồi thêm các file vào đúng package.

### 5.2. Application và controller

Tạo file `src/main/java/com/example/authsplit/AuthSplitApplication.java`:

~~~java
package com.example.authsplit;

import java.security.Principal;
import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class AuthSplitApplication {
    public static void main(String[] args) {
        SpringApplication.run(AuthSplitApplication.class, args);
    }

    @RestController
    static class Routes {
        @GetMapping("/")
        Map<String, String> home() {
            return Map.of("message", "public");
        }

        @GetMapping("/api/me")
        Map<String, String> apiMe(Principal principal) {
            return Map.of("apiUser", principal.getName());
        }

        @GetMapping("/api/admin")
        Map<String, String> apiAdmin(Principal principal) {
            return Map.of("apiAdmin", principal.getName());
        }

        @GetMapping("/web/me")
        Map<String, String> webMe(Principal principal) {
            return Map.of("webUser", principal.getName());
        }
    }
}
~~~

`Principal` chỉ được dùng ở endpoint yêu cầu xác thực. Spring MVC lấy danh tính đã được xác thực từ security context cho request; controller không cần tự giải Base64.

### 5.3. Hai chain và xử lý 401/403 riêng cho API

Tạo file `src/main/java/com/example/authsplit/SecurityConfig.java`:

~~~java
package com.example.authsplit;

import java.io.IOException;
import java.nio.charset.StandardCharsets;

import jakarta.servlet.http.HttpServletResponse;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.AuthenticationEntryPoint;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        AuthenticationEntryPoint apiEntryPoint = (request, response, ex) -> {
            response.setHeader(
                HttpHeaders.WWW_AUTHENTICATE,
                "Basic realm=\"api\""
            );
            response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
            writeJson(response, "{\"error\":\"unauthorized\"}");
        };

        http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/admin").hasRole("ADMIN")
                .anyRequest().authenticated()
            )
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            )
            .httpBasic(basic -> basic
                .authenticationEntryPoint(apiEntryPoint)
            )
            .exceptionHandling(errors -> errors
                .authenticationEntryPoint(apiEntryPoint)
                .accessDeniedHandler((request, response, ex) -> {
                    response.setStatus(HttpServletResponse.SC_FORBIDDEN);
                    writeJson(response, "{\"error\":\"forbidden\"}");
                })
            );

        return http.build();
    }

    @Bean
    SecurityFilterChain webChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated()
            )
            .formLogin(Customizer.withDefaults())
            .logout(logout -> logout
                .logoutSuccessUrl("/login?logout")
                .permitAll()
            );

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
                .password(encoder.encode("reader-pass"))
                .roles("USER")
                .build(),
            User.withUsername("admin")
                .password(encoder.encode("admin-pass"))
                .roles("ADMIN")
                .build()
        );
    }

    private static void writeJson(
        HttpServletResponse response,
        String json
    ) throws IOException {
        response.setCharacterEncoding(StandardCharsets.UTF_8.name());
        response.setContentType(MediaType.APPLICATION_JSON_VALUE);
        response.getWriter().write(json);
    }
}
~~~

Các quyết định trong cấu hình:

1. **`@Order(1)` + `securityMatcher("/api/**")`:** mọi request bắt đầu `/api/` đi vào chain API. Vì API chain không bật `formLogin`, không có điều hướng sang trang login cho request API không xác thực.
2. **`httpBasic`:** chain API dùng Basic và entry point trả 401 JSON; `WWW-Authenticate` được giữ để client biết scheme.
3. **`exceptionHandling`:** cũng dùng entry point đó khi request API thiếu xác thực nhưng bị rule từ chối; `AccessDeniedHandler` riêng trả 403 JSON khi có danh tính nhưng không đủ quyền.
4. **`STATELESS`:** chain API không tạo hoặc dùng HTTP session để lưu `SecurityContext` cho authentication. Mỗi Basic request dựa trên credential riêng; đây không phải “lệnh logout”.
5. **Web chain làm fallback:** các URL `/login`, `/logout` và `/web/me` đều được chain web phục vụ; chain này bật `formLogin` và logout, **không bật HTTP Basic**.
6. **CSRF giữ mặc định:** web form và `POST /logout` vẫn chịu CSRF protection. API GET trong ví dụ không cần CSRF token. Nếu API có request thay đổi dữ liệu từ browser dùng Basic, vẫn cần đánh giá CSRF.
7. **Cùng kho tài khoản demo:** hai chain có thể dùng chung `UserDetailsService`/`PasswordEncoder`, nhưng cách truyền credential và lưu trạng thái là hai cơ chế khác nhau. Chia chain không mặc định tách danh sách user hoặc quyền.
8. **Password demo:** mật khẩu tồn tại trong source chỉ để thử trên máy phát triển. Production cần kho user/secret phù hợp, HTTPS, bảo vệ log và kiểm soát thử sai. BCrypt là password hash, không phải mã hóa reversible.

Chú ý: ví dụ cấu hình một `SecurityFilterChain` mặc định không có `securityMatcher` để bao phủ các URL còn lại. Không được viết “fallback” bằng một `securityMatcher("/web/**")` rồi bỏ quên `/login`, `/logout`, `/error` hay endpoint mới nằm ngoài vùng bảo vệ.

### 5.4. Chạy ứng dụng

Trong thư mục dự án Spring Boot có Gradle Wrapper:

~~~bash
./gradlew bootRun
~~~

Trên Windows dùng `gradlew.bat bootRun`. Vì mã phụ thuộc Spring Boot và Spring Security, `javac` đơn lẻ không có classpath cần thiết; Gradle compile và chạy ứng dụng.

Thử trực tiếp bằng cURL; server demo đang chạy ở `http://localhost:8080`. **Địa chỉ HTTP này chỉ dành cho localhost thử nghiệm; khi triển khai phải dùng HTTPS.** Trên PowerShell có thể gọi `curl.exe` nếu tên `curl` bị alias.

~~~bash
# API chưa xác thực: phải nhận 401 + Basic challenge.
curl -i http://localhost:8080/api/me

# API có Basic credential đúng: 200.
curl -i -u reader:reader-pass http://localhost:8080/api/me

# Đăng nhập đúng nhưng không có quyền admin: 403.
curl -i -u reader:reader-pass http://localhost:8080/api/admin

# Đăng nhập admin: 200.
curl -i -u admin:admin-pass http://localhost:8080/api/admin

# Trang web chưa có session: redirect tới /login.
curl -i http://localhost:8080/web/me

# Trang login do Spring Security tạo, phục vụ qua web chain.
curl -i http://localhost:8080/login

# Trang công khai.
curl -i http://localhost:8080/
~~~

Kết quả cần kiểm tra:

| Lệnh thử | HTTP status | Nội dung/điểm cần quan sát |
| --- | --- | --- |
| `GET /api/me` không credential | `401` | `WWW-Authenticate: Basic realm="api"` và `{"error":"unauthorized"}`. |
| `GET /api/me` với `reader:reader-pass` | `200` | `{"apiUser":"reader"}`. |
| `GET /api/admin` với reader | `403` | `{"error":"forbidden"}`; không phải sai password. |
| `GET /api/admin` với admin | `200` | `{"apiAdmin":"admin"}`. |
| `GET /web/me` chưa có session | `302` | `Location` trỏ về trang `/login`; không gửi Basic challenge. |
| `GET /login` | `200` | HTML form login do Spring Security tạo. |
| `GET /` | `200` | `{"message":"public"}`. |

Không khẳng định chính xác mọi header phụ, thứ tự header, session cookie hoặc HTML của form: những chi tiết này phụ thuộc servlet container và version. Điều cần QA là **status, authentication scheme, đường đi của chain và phạm vi quyền**.

Lưu ý bảo mật đối với lệnh demo: tham số `-u username:password` có thể xuất hiện trong lịch sử lệnh hoặc danh sách tiến trình. Chỉ dùng tài khoản giả. Khi thao tác với credential thật, dùng phương thức cấp secret phù hợp môi trường và tuyệt đối không chụp/ghi log header Basic.

## 6. Thử logout của form và chứng minh Basic vẫn độc lập

Trong trình duyệt, truy cập `http://localhost:8080/web/me`. Chưa đăng nhập sẽ được đưa đến trang `/login`.

1. Đăng nhập qua form bằng tài khoản demo `reader` / `reader-pass`. Browser gửi form kèm CSRF token mà trang đăng nhập do Spring Security tạo cung cấp; ứng dụng thiết lập session.
2. Mở `/web/me`. Khi xác thực bằng phiên thành công, endpoint trả JSON có khóa `webUser`.
3. Truy cập `/logout`. Nếu CSRF đang bật, Spring Security có thể hiện trang xác nhận. Nhấn nút Logout để gửi **POST** với CSRF token.
4. Sau logout, browser thường chuyển đến `/login?logout`. Truy cập lại `/web/me` sẽ yêu cầu form login, vì session cũ không còn hiệu lực.
5. Dùng cURL gửi lại Basic credential tới API:

~~~bash
curl -i -u reader:reader-pass http://localhost:8080/api/me
~~~

Kết quả vẫn là `200` với `{"apiUser":"reader"}`, bởi username/password vẫn đúng. Đó là minh chứng trực tiếp rằng **logout form không thu hồi credential Basic**. Hai luồng được route bằng chain khác nhau, mặc dù dùng chung user database demo.

Thử thêm request đến `/api/me` **không có** Basic credential nhưng gửi cookie của web session: với cấu hình `STATELESS` của API chain, cookie đó không được dùng để lấy `SecurityContext` cho request API; kết quả mong đợi là 401. Đây là một phép thử quan trọng để phát hiện vô tình chia sẻ session vào API.

Ngược lại, chỉ đưa `Authorization: Basic …` vào request `GET /web/me` không biến API Basic filter thành login web, bởi request này vào web chain vốn không cấu hình `httpBasic`. Khi chưa có session form, web chain vẫn yêu cầu đăng nhập qua form.

## 7. Các lỗi cấu hình thường gặp khi trộn Basic và form login

### Lỗi 1: Bật cả hai cơ chế trong một chain bao trùm

~~~java
// Minh họa cấu hình dễ gây nhầm lẫn, không dùng trong ví dụ.
http
    .authorizeHttpRequests(auth -> auth
        .anyRequest().authenticated()
    )
    .httpBasic(Customizer.withDefaults())
    .formLogin(Customizer.withDefaults());
~~~

Cấu hình này không tự thân sai, nhưng khi cả browser và API dùng chung chain, response chưa xác thực có thể phụ thuộc cách Spring Security chọn entry point. API chờ `401` JSON lại nhận `302` HTML, hoặc browser chờ trang login lại nhận Basic challenge/hộp thoại đăng nhập. Nếu hợp đồng của hai nhóm client khác nhau, hãy dùng các chain có matcher rõ ràng.

### Lỗi 2: Nhầm `securityMatcher` với `requestMatchers`

Chỉ đặt `requestMatchers("/api/**")` bên trong `authorizeHttpRequests` không tạo chain riêng cho API. Phải chỉ định `http.securityMatcher("/api/**")` cho chain API, cùng thứ tự ưu tiên chính xác. Với request khớp cả hai, Spring Security chọn chain đầu tiên, **không thử tiếp chain sau khi chain đầu trả 401/403**.

### Lỗi 3: Để “lỗ hổng” giữa các chain

Hai chain `/api/**` và `/web/**` không tự bảo vệ `/admin`, `/actuator/**` hoặc endpoint mới nằm ngoài hai prefix. Dùng fallback chain phù hợp (không có `securityMatcher`) hoặc một chính sách từ chối mặc định đã tính toán. Đừng mặc định “không khớp chain” tương đương “bị deny”.

### Lỗi 4: Đặt login/logout URL ngoài matcher của web chain

Nếu web chain chỉ match `/web/**` nhưng dùng mặc định `POST /login` và `POST /logout`, hai request đó không vào chain có filter xử lý chúng. Cách sửa là để web chain làm fallback như ví dụ, hoặc đổi cả `loginPage`, `loginProcessingUrl`, `logoutUrl` sang đúng phạm vi matcher và cung cấp trang login phù hợp.

### Lỗi 5: Tắt CSRF vì nghĩ Basic stateless thì an toàn

`SessionCreationPolicy.STATELESS` không loại bỏ rủi ro CSRF khi browser tự gắn Basic credential đã cache vào request. Nếu API có thể được browser truy cập và có thao tác đổi dữ liệu, phải đánh giá CSRF nghiêm túc. Chỉ cân nhắc bỏ CSRF cho API chỉ phục vụ client không tự động đính kèm credential và có mô hình đe dọa đã xác minh. CORS **không** thay thế CSRF protection.

### Lỗi 6: Xem `POST /logout` là lệnh xóa Basic credential

Logout filter xóa ngữ cảnh và session nó quản lý; request API mới vẫn có thể xác thực bằng credential chưa bị thu hồi. Nếu mục tiêu là cấm credential cũ, cần cập nhật trạng thái tài khoản/password hoặc thiết kế cơ chế credential khác có thể thu hồi.

### Lỗi 7: Biến mọi authentication error thành 403

Sai password/chưa có credential thường phải là 401; user đã xác thực nhưng thiếu quyền thường là 403. API đã custom JSON lỗi thì vẫn cần nhất quán ở cả nhánh invalid Basic credential và nhánh không có credential. Khi cấu hình endpoint công khai và filter tùy biến, kiểm tra cả hai tình huống.

### Lỗi 8: Debug bằng cách ghi toàn bộ header

Log nguyên `Authorization` làm lộ username/password qua Base64. Nên log loại lỗi, path đã chuẩn hóa, request ID, thời gian, kết quả (401/403), không log token/credential. Nếu cần phân tích thêm, thực hiện trong môi trường kiểm soát và loại bỏ thông tin nhạy cảm ngay khi hoàn tất.

## 8. Kế hoạch kiểm thử và tiêu chí đạt

Sau khi triển khai hai chain, nên chạy tối thiểu các phép thử sau:

| Test | Request | Kết quả mong đợi |
| --- | --- | --- |
| API-01 | `GET /api/me`, không Authorization | 401, Basic challenge; không redirect login HTML. |
| API-02 | `GET /api/me`, password sai | 401, không tiết lộ user có tồn tại hay không. |
| API-03 | `GET /api/me`, Basic credential đúng | 200; trả danh tính API. |
| API-04 | `GET /api/admin`, reader đúng | 403; không phải 401. |
| API-05 | `GET /api/admin`, admin đúng | 200. |
| WEB-01 | `GET /web/me`, không có session | Redirect đến login, không bật Basic challenge. |
| WEB-02 | `POST /login` với credential + CSRF token hợp lệ | Đăng nhập web thành công và duy trì session. |
| WEB-03 | `POST /logout` với CSRF token hợp lệ | Session bị vô hiệu, không tái dùng được. |
| ISOLATION-01 | `GET /api/me` chỉ có cookie web session, không Basic | 401, chứng minh API không dựa vào web session. |
| ISOLATION-02 | `GET /web/me` chỉ có Basic header, không session | Yêu cầu form login, chứng minh web chain không bật Basic. |
| ISOLATION-03 | Logout web rồi gọi API với Basic credential vẫn hợp lệ | API vẫn có thể 200; thể hiện giới hạn logout Basic. |
| ROUTING-01 | URL mới ngoài `/api/**`, ví dụ `/unexpected` | Fallback chain vẫn bảo vệ hoặc trả status theo chính sách đã khai báo. |

Khi một test bất ngờ thất bại, gỡ lỗi theo thứ tự:

1. **Chain nào nhận request?** Kiểm tra URL sau reverse proxy, context path, `@Order` và `securityMatcher`. Đừng chỉ nhìn rule `requestMatchers`.
2. **Có credential/phiên gì?** Với API xem có Basic header (chỉ kiểm tra sự hiện diện và scheme, không log giá trị); với web kiểm tra session/cookie và trạng thái xác thực đã được lưu.
3. **Lỗi nằm ở authentication hay authorization?** Kiểm tra `AuthenticationEntryPoint`, `AccessDeniedHandler`, role/authority, `UserDetailsService` và `PasswordEncoder`.
4. **Nếu xảy ra ở POST/PUT/DELETE:** kiểm tra CSRF trước khi kết luận thiếu role.
5. **Nếu browser hiện hộp thoại Basic:** xác minh request có lỡ vào API chain hoặc nhận `WWW-Authenticate` ngoài dự kiến.
6. **Nếu logout xong vẫn thấy xác thực:** xác định request đó dùng **session web** hay lại mang **Basic credential**; đây là hai nguyên nhân khác nhau.

## 9. Ghi nhớ

- HTTP Basic **không có logout chuẩn bảo đảm client xóa username/password**. Xóa `SecurityContext` hoặc session chỉ xử lý trạng thái server đang giữ.
- Form login có thể logout bằng hủy session; khi bật CSRF mặc định, `POST /logout` cần CSRF token hợp lệ.
- `401 Unauthorized` dành cho tình huống chưa xác thực thành công; Basic thường kèm `WWW-Authenticate`. `403 Forbidden` dành cho yêu cầu đã bị từ chối, thường do thiếu quyền hoặc CSRF.
- `securityMatcher` chọn **filter chain**; `requestMatchers` trong `authorizeHttpRequests` áp dụng **rule quyền trong chain đó**. Chỉ chain đầu tiên khớp request được dùng.
- Dùng một Basic API chain ưu tiên cho `/api/**` và một form-login fallback chain cho trang web giúp kiểm soát riêng 401 JSON, 302 login, 403 và logout session.
- Cấu hình stateless và tách chain **không thay thế HTTPS, CSRF assessment, bảo vệ credential, rate limiting hoặc quản lý vòng đời password**.

### Tài liệu tham khảo

- RFC 7617 — The 'Basic' HTTP Authentication Scheme: https://www.rfc-editor.org/rfc/rfc7617
- Spring Security Reference — Basic Authentication (Servlet): https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/basic.html
- Spring Security Reference — Java Configuration, Multiple HttpSecurity Instances: https://docs.spring.io/spring-security/reference/servlet/configuration/java.html
- Spring Security Reference — Handling Logouts: https://docs.spring.io/spring-security/reference/servlet/authentication/logout.html
- Spring Security Reference — CSRF: https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html
