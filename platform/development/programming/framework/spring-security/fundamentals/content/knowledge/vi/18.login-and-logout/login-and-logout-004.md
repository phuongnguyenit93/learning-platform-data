# Đăng nhập JSON là cách tiếp nhận thông tin, không tự xác định mô hình phiên hay token

## 1. Mục tiêu: tách định dạng HTTP khỏi chiến lược duy trì đăng nhập

Một API thường nhận thông tin đăng nhập theo dạng JSON:

~~~http
POST /api/login HTTP/1.1
Content-Type: application/json

{"username":"alice","password":"demo123"}
~~~

Nhìn vào body JSON trên, **chưa thể kết luận ứng dụng dùng session hay JWT**. JSON chỉ là **cách mã hóa dữ liệu gửi tới endpoint**; nó không định nghĩa cách server kiểm tra mật khẩu, lưu Authentication, xác nhận danh tính cho request tiếp theo hay đăng xuất.

Cùng một request POST JSON có thể dẫn tới nhiều thiết kế hợp lệ:

- **Đăng nhập có trạng thái (stateful/session)**: server xác thực rồi lưu trạng thái SecurityContext trong HttpSession. Client nhận và gửi lại cookie phiên ở những request sau.
- **Đăng nhập bằng token (thường stateless)**: server xác thực rồi cấp một access token; client gửi token bằng Authorization: Bearer trong các request tiếp theo; server xác thực token cho từng request.
- **Mô hình lai**: JSON login cấp token nhưng token được lưu trong cookie, hoặc hệ thống dùng session cho web và Bearer token cho API/mobile. Cần đọc cấu hình thực tế để xác định những phần nào còn stateful.

Mục tiêu bài học:
1. Phân biệt **JSON request body**, **authentication**, **authorization**, **SecurityContext**, **HttpSession**, **session cookie**, **access token**.
2. Hiểu vì sao POST JSON thành công không tự khiến GET kế tiếp có Authentication.
3. Viết được ví dụ Spring Boot 3.x + Spring Security 6.x, Java 17+, dùng JSON login **và session**, có lưu SecurityContext rõ ràng.
4. Phác họa đúng luồng dùng Bearer token mà không coi việc trả chuỗi token trong JSON là bảo mật hoàn chỉnh.
5. Thiết kế đúng CSRF, session fixation, cookie, HTTPS, logout, thời hạn sống và xử lý đăng nhập thất bại.
6. Chẩn đoán lỗi “POST /api/login trả 200 nhưng request sau lại 401”.

**Nguyên tắc trung tâm:** *Định dạng truyền credential* và *cơ chế lưu/xác minh danh tính giữa các request* là hai quyết định **độc lập**, dù thường được triển khai cùng một luồng login.

## 2. Phân biệt các lớp trong một luồng đăng nhập

| Thành phần | Nó trả lời câu hỏi gì? | Không có nghĩa là |
| --- | --- | --- |
| **Content-Type: application/json** | Client gửi dữ liệu có định dạng gì? | App bắt buộc phải dùng JWT hoặc stateless |
| **@RequestBody LoginRequest** | Server đọc trường username/password từ body như thế nào? | Password đã được kiểm tra |
| **AuthenticationManager.authenticate(...)** | Credentials có hợp lệ theo các AuthenticationProvider được cấu hình không? | Danh tính đã được lưu sang request tiếp theo |
| **Authentication** | Principal, authorities và trạng thái xác thực của lần xử lý này là gì? | Một session cookie hoặc JWT |
| **SecurityContext** | Authentication hiện hành được đặt ở đâu để authorization đọc? | Một kho lưu thông tin có vòng đời không giới hạn |
| **SecurityContextRepository** | Context có được nạp/lưu qua request không, và lưu ở đâu? | Bắt buộc dùng HttpSession trong mọi ứng dụng |
| **HttpSession + JSESSIONID** | Server liên kết nhiều request qua một phiên như thế nào? | Cookie chứa toàn bộ Authentication |
| **Access token** | Credential cho request sau được phát hành và xác minh ra sao? | Chỉ cần một chuỗi bất kỳ để tự động an toàn |
| **Authorization** | User đã xác thực có quyền gọi endpoint không? | Tương đương với thành công của POST /api/login |

Trên Spring Security Servlet, **SecurityContextHolder** cung cấp ngữ cảnh bảo mật đang hoạt động cho luồng xử lý hiện tại. Sau request, filter chain quản lý việc dọn context. Nếu dùng session, lần GET tiếp theo có thể nạp SecurityContext đã được lưu trong session; nếu dùng Bearer token, lần GET tiếp theo có thể dựng Authentication từ token mà client gửi trong request đó.

### 2.1. Ba câu hỏi cần hỏi khi review một API login

**Câu 1 – Nhận đầu vào:** Endpoint có nhận JSON, application/x-www-form-urlencoded, HTTP Basic, OAuth2 redirect hay cơ chế khác? Đây là cách credential đi vào hệ thống.

**Câu 2 – Xác thực:** Server dùng UserDetailsService + PasswordEncoder, identity provider, LDAP, OIDC hay dịch vụ xác thực ngoài để xác minh danh tính? Kết quả là Authentication hoặc lỗi; cú pháp JSON không quyết định nguồn kiểm tra.

**Câu 3 – Duy trì danh tính:** Sau khi xác thực thành công, server lưu SecurityContext trong HttpSession, trả access token, hay yêu cầu credential mới ở request sau? Đây là quyết định kiến trúc ảnh hưởng đến client, CSRF, logout, scale và vận hành.

Đừng gộp ba câu hỏi thành giả định “đăng nhập JSON = token”.

## 3. Hai luồng có cùng JSON đầu vào nhưng khác nhau ở bước tiếp theo

### 3.1. Trường hợp A: JSON login + server-side session

~~~text
Client                             Spring Boot / Spring Security
  | POST /api/login
  | Content-Type: application/json
  | {"username":"alice","password":"..."}
  |------------------------------------>
  |                                      Parse JSON
  |                                      AuthenticationManager.authenticate()
  |                                      Authentication thành công
  |                                      Tạo SecurityContext
  |                                      SecurityContextRepository.saveContext(...)
  |                                      Lưu SecurityContext gắn HttpSession
  |<------------------------------------
  | HTTP 200 + Set-Cookie: JSESSIONID=...
  |
  | GET /api/me
  | Cookie: JSESSIONID=...
  |------------------------------------>
  |                                      Nạp SecurityContext từ phiên
  |                                      Lấy Authentication và kiểm tra quyền
  |<------------------------------------
  | HTTP 200 {"username":"alice"}
~~~

**Cookie ở đây mang mã phiên**, không phải JWT và không phải nguyên JSON của Authentication. Server thường quản lý session attributes; khi dùng nhiều instance server có thể cần Spring Session hoặc chiến lược session storage phù hợp.

Nếu client quên gửi cookie, gửi cookie sai scope/domain/path hoặc session đã hết hạn, request sau có thể bị coi là chưa xác thực dù POST JSON trước đó trả 200.

### 3.2. Trường hợp B: JSON login + Bearer access token

~~~text
Client                             Authentication/Token Service
  | POST /api/login
  | Content-Type: application/json
  | {"username":"alice","password":"..."}
  |------------------------------------>
  |                                      Parse JSON + authenticate()
  |                                      Phát hành access token có kiểm soát
  |<------------------------------------
  | HTTP 200 {"access_token":"<token>","token_type":"Bearer"}
  |
  | GET /api/me
  | Authorization: Bearer <token>
  |------------------------------------>
  |                                      Xác minh chữ ký hoặc introspection
  |                                      Kiểm tra hạn, issuer, audience, quyền
  |                                      Tạo Authentication cho request
  |<------------------------------------
  | HTTP 200 {"username":"alice"}
~~~

Ở đây server có thể không lưu HttpSession để phục hồi danh tính cho request sau. Nhưng một hệ thống cấp token vẫn có thể duy trì **refresh tokens, danh sách thu hồi, phiên đăng nhập tại authorization server hoặc trạng thái thiết bị** ở một nơi nào đó. Do đó, “Bearer token” không đồng nghĩa “toàn hệ thống không có state”.

**Không phải token nào cũng là JWT.** Access token có thể là chuỗi opaque cần introspection, hoặc JWT được ký và xác minh. Chỉ thêm ba phần ngăn bởi dấu chấm vào response JSON không tự biến hệ thống thành JWT authentication an toàn.

### 3.3. Bảng so sánh thực dụng

| Tiêu chí | JSON login + HttpSession | JSON login + Bearer token |
| --- | --- | --- |
| Body đăng nhập | Có thể là JSON | Có thể là JSON |
| Server làm gì sau khi xác thực? | Lưu SecurityContext vào session/repository | Cấp token theo chính sách; resource server kiểm tra token ở các request |
| Client gửi gì trong lần GET sau? | Session cookie hợp lệ | Authorization: Bearer token (hoặc cơ chế truyền token đã chọn) |
| Khôi phục Authentication | Từ session/repository | Từ kết quả xác minh credential/token cho request |
| Thu hồi quyền truy cập | Có thể hủy/invalidate session | Tùy token: token ngắn hạn, introspection, revocation list, rotation… |
| CSRF | Đặc biệt quan trọng khi browser tự gửi session cookie | Phụ thuộc cách credential được browser gửi; bearer trong Authorization header không được browser tự thêm như cookie |
| XSS | Cần bảo vệ ứng dụng; HttpOnly giúp hạn chế JS đọc cookie | Token lưu trong JS-accessible storage có rủi ro bị XSS lấy; lựa chọn lưu token phải xét threat model |
| Scale nhiều server | Cần session sharing/affinity phù hợp | JWT tự xác minh giảm tra session; vẫn cần giải pháp key rotation/revocation khi phù hợp |
| Logout | Thường hủy session + dọn SecurityContext | Client xóa token; có thể cần thu hồi refresh token/access token nếu chính sách yêu cầu |
| Chứng minh có quyền | Authorities từ Authentication lưu trong context | Authorities thường từ token claims/introspection và converter |

**Đây là hai mô hình kiến trúc, không phải đặc tính riêng của Content-Type.**

## 4. Spring Security 6: đăng nhập thành công chưa chắc được duy trì

Một custom JSON login endpoint có thể thực hiện:

~~~java
Authentication auth = authenticationManager.authenticate(
    UsernamePasswordAuthenticationToken.unauthenticated(
        username, password));
~~~

Mã trên yêu cầu một AuthenticationManager đã cấu hình Provider có thể xác thực username/password. Khi thành công, nó trả một Authentication phù hợp, nhưng **không tự đảm bảo SecurityContext được ghi vào HttpSession**.

Trong Spring Security 6.x, cơ chế lưu context yêu cầu chú ý đến **SecurityContextRepository**. Nếu custom controller tự đặt Authentication nhưng không lưu, request hiện tại có thể đọc Authentication từ SecurityContextHolder, còn request kế tiếp lại không nhận được trạng thái đó.

Cách biểu diễn cốt lõi của session persistence:

~~~java
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(auth);
SecurityContextHolder.setContext(context);
securityContextRepository.saveContext(context, request, response);
~~~

Đây chỉ là **fragment**, không phải toàn bộ luồng đăng nhập an toàn. Trong ứng dụng Servlet, một bộ lọc/form login chuẩn thường xử lý thêm session authentication strategy (ví dụ chống session fixation), sự kiện xác thực, lưu context và các chính sách khác. Nếu tự xây controller login, bạn phải thiết kế những việc đó thay vì nghĩ chỉ cần bốn dòng trên.

Mặt khác, nếu bạn chọn Bearer token, bạn cần **phát hành token hợp lệ** và cấu hình **token validation** cho request sau. Chỉ thêm:

~~~java
return Map.of("token", "some-string");
~~~

không tạo ra một hệ thống xác thực Bearer hoạt động; nếu server không xác minh token và xây dựng Authentication cho request mới, GET /api/me vẫn bị từ chối.

## 5. Demo chạy được: POST JSON nhưng duy trì đăng nhập bằng HttpSession

Mục đích demo: chứng minh một endpoint **POST /api/login nhận JSON**, sau đó **GET /api/me ở request khác** vẫn được xác thực nhờ cookie/session. Ví dụ giữ **CSRF enabled** (kể cả login), tạo cookie jar khi chạy curl, dùng **SecurityContextRepository** explicit save và áp dụng **ChangeSessionIdAuthenticationStrategy** để hạn chế session fixation trong phạm vi bài.

### 5.1. Chuẩn bị dự án

Tạo project từ Spring Initializr:

- **Spring Boot 3.x**, **Java 17+**, **Gradle**.
- Group **com.example**, artifact **demo**, package **com.example.demo**.
- Dependencies **Spring Web** (spring-boot-starter-web) và **Spring Security** (spring-boot-starter-security).

Tạo đúng một file nguồn:

~~~text
src/main/java/com/example/demo/JsonLoginSessionApplication.java
~~~

Chương trình có một public class trùng tên file; các class cấu hình/controller ở cùng package là package-private để Spring Boot component scan.

### 5.2. Toàn bộ mã Java

~~~java
package com.example.demo;

import java.util.Map;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.authentication.session.ChangeSessionIdAuthenticationStrategy;
import org.springframework.security.authentication.session.SessionAuthenticationStrategy;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.HttpStatusEntryPoint;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.security.web.context.SecurityContextRepository;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@SpringBootApplication
public class JsonLoginSessionApplication {

    public static void main(String[] args) {
        SpringApplication.run(JsonLoginSessionApplication.class, args);
    }
}

@Configuration
@EnableWebSecurity
class SecurityConfig {

    @Bean
    SecurityContextRepository securityContextRepository() {
        return new HttpSessionSecurityContextRepository();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoder.encode("demo123"))
                .roles("USER")
                .build(),
            User.withUsername("admin")
                .password(encoder.encode("demo123"))
                .roles("ADMIN")
                .build()
        );
    }

    @Bean
    AuthenticationManager authenticationManager(
            UserDetailsService users, PasswordEncoder encoder) {
        DaoAuthenticationProvider provider =
            new DaoAuthenticationProvider(users);
        provider.setPasswordEncoder(encoder);
        return new ProviderManager(provider);
    }

    @Bean
    SessionAuthenticationStrategy sessionAuthenticationStrategy() {
        return new ChangeSessionIdAuthenticationStrategy();
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            SecurityContextRepository repository) throws Exception {
        return http
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.IF_REQUIRED))
            .securityContext(context -> context
                .securityContextRepository(repository))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/csrf")
                    .permitAll()
                .requestMatchers(HttpMethod.POST, "/api/login")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/api/me")
                    .authenticated()
                .requestMatchers(HttpMethod.GET, "/api/admin")
                    .hasRole("ADMIN")
                .anyRequest().denyAll())
            .formLogin(AbstractHttpConfigurer::disable)
            .httpBasic(AbstractHttpConfigurer::disable)
            .exceptionHandling(errors -> errors
                .authenticationEntryPoint(
                    new HttpStatusEntryPoint(HttpStatus.UNAUTHORIZED)))
            .logout(logout -> logout
                .logoutUrl("/api/logout")
                .logoutSuccessHandler((request, response, auth) -> {
                    response.setStatus(HttpServletResponse.SC_OK);
                    response.setContentType(
                        MediaType.APPLICATION_JSON_VALUE);
                    response.getWriter().write(
                        "{\"status\":\"logged_out\"}");
                })
                .permitAll())
            .build();
    }
}

@RestController
class AuthApi {

    private final AuthenticationManager manager;
    private final SecurityContextRepository repository;
    private final SessionAuthenticationStrategy sessionStrategy;

    AuthApi(AuthenticationManager manager,
            SecurityContextRepository repository,
            SessionAuthenticationStrategy sessionStrategy) {
        this.manager = manager;
        this.repository = repository;
        this.sessionStrategy = sessionStrategy;
    }

    // GET cấp token chống CSRF cho client; mặc định lưu trong session.
    @GetMapping("/api/csrf")
    Map<String, String> csrf(CsrfToken token) {
        return Map.of(
            "headerName", token.getHeaderName(),
            "token", token.getToken());
    }

    public record LoginRequest(String username, String password) {
    }

    public record LoginResult(String username, String mode) {
    }

    @PostMapping(path = "/api/login",
                 consumes = MediaType.APPLICATION_JSON_VALUE)
    LoginResult login(@RequestBody LoginRequest body,
            HttpServletRequest request,
            HttpServletResponse response) {
        try {
            Authentication authentication = manager.authenticate(
                UsernamePasswordAuthenticationToken.unauthenticated(
                    body.username(), body.password()));

            // Controller tùy biến phải chủ động áp dụng
            // các bước cần thiết của session authentication.
            sessionStrategy.onAuthentication(
                authentication, request, response);

            SecurityContext context =
                SecurityContextHolder.createEmptyContext();
            context.setAuthentication(authentication);
            SecurityContextHolder.setContext(context);

            // Chọn mô hình session và lưu explicit.
            repository.saveContext(context, request, response);

            return new LoginResult(authentication.getName(), "session");
        } catch (AuthenticationException ex) {
            throw new ResponseStatusException(
                HttpStatus.UNAUTHORIZED,
                "Invalid username or password");
        }
    }

    @GetMapping("/api/me")
    Map<String, String> me(Authentication authentication) {
        return Map.of("username", authentication.getName());
    }

    @GetMapping("/api/admin")
    Map<String, String> admin(Authentication authentication) {
        return Map.of("message", "admin-only",
                      "username", authentication.getName());
    }
}
~~~

**Giải thích mã:**

- Spring MVC dùng Jackson (qua Spring Web) để chuyển JSON body thành **LoginRequest**; **consumes = application/json** kiểm tra media type của endpoint.
- **AuthenticationManager** được cấu hình với **DaoAuthenticationProvider**, **UserDetailsService** và **PasswordEncoder**. UserDetailsService chỉ giữ hai user demo để dễ kiểm tra.
- **AuthenticationException** được phản hồi 401 chung, không tiết lộ user nào tồn tại; không log password.
- **SessionAuthenticationStrategy** được gọi sau khi xác thực nhằm đổi session ID khi có session phù hợp; đây là cách thể hiện bảo vệ session fixation cho custom flow. Cơ chế chuẩn còn có thể bổ sung xử lý concurrency và CSRF token rotation tùy chính sách.
- **SecurityContextRepository** trong ví dụ là HttpSessionSecurityContextRepository. Nó cùng được cung cấp cho HttpSecurity và controller login; tránh việc login lưu vào repository A nhưng security filter lại đọc repository B.
- **SecurityContextHolder.setContext** giúp code trong request hiện tại thấy Authentication; **saveContext** là bước duy trì đăng nhập sang request tiếp theo.
- **CSRF bật mặc định**: JavaScript/browser/curl phải lấy token từ GET /api/csrf và gửi trong header khi POST login hoặc logout. Chỉ cần JSON không có nghĩa được miễn kiểm tra CSRF.
- **Form login và HTTP Basic bị tắt** trong demo để thể hiện rõ endpoint JSON tự quản lý xác thực. HTTP Basic không được dùng làm cơ chế đăng nhập thay thế ở đây.
- **LogoutFilter chuẩn** xử lý **POST /api/logout**, hủy phiên theo các logout handlers mặc định và trả JSON; endpoint này không phải method của AuthApi.
- **PasswordEncoderFactories.createDelegatingPasswordEncoder()** tạo password hash theo mặc định phù hợp; password demo123 trong source chỉ phục vụ học tập. Môi trường thật phải dùng user store và chính sách mật khẩu phù hợp.
- **GET /api/admin** yêu cầu role ADMIN (authority ROLE_ADMIN); xác thực thành công không tự cấp quyền admin.

**Giới hạn demo:** Không có rate limiting, MFA, audit logging, account lockout, security event handling đầy đủ, distributed session store hoặc kiểm thử hardening chuyên sâu. Ứng dụng production nên ưu tiên cơ chế đăng nhập chuẩn đã được bảo trì, hoặc triển khai custom authentication filter và các session/concurrency/CSRF strategies đầy đủ hơn. Mã này giúp minh họa cách duy trì context bằng session, không phải gói xác thực production sẵn dùng.

### 5.3. Chạy chương trình

Ở thư mục gốc dự án Gradle đã tạo:

~~~bash
./gradlew bootRun
~~~

Trên Windows dùng **gradlew.bat bootRun**. Mặc định, ứng dụng lắng nghe ở **http://localhost:8080** nếu chưa thay đổi server.port.

### 5.4. Thử login có session bằng curl

Ví dụ dưới đây dùng **Bash + Python 3** cho phần tách token từ JSON. Tạo một cookie jar tạm ở thư mục làm việc để bảo đảm request sau gửi **đúng cookie phiên**.

~~~bash
# 1. Xin CSRF token và lưu session cookie.
curl -s -c cookies.txt \
  http://localhost:8080/api/csrf > csrf.json

# 2. Đọc token từ JSON (không cần cài jq).
CSRF=$(python3 -c \
  "import json; print(json.load(open('csrf.json'))['token'])")

# 3. POST JSON, gửi cùng cookie + CSRF token.
curl -i -b cookies.txt -c cookies.txt \
  -H 'Content-Type: application/json' \
  -H "X-CSRF-TOKEN: $CSRF" \
  -d '{"username":"alice","password":"demo123"}' \
  http://localhost:8080/api/login

# 4. Request mới: không gửi password, chỉ có cookie.
curl -i -b cookies.txt http://localhost:8080/api/me

# 5. Alice không có ROLE_ADMIN.
curl -i -b cookies.txt http://localhost:8080/api/admin

# 6. Không mang cookie: không được coi là đã login.
curl -i http://localhost:8080/api/me
~~~

**Các kết quả HTTP mong đợi từ cấu hình**:

| Lượt | Kết quả mong đợi | Lý do |
| --- | --- | --- |
| GET /api/csrf chưa login | **200** JSON token, cookie phục vụ CSRF/session khi cần | Endpoint công khai và token được khởi tạo theo nhu cầu |
| POST /api/login hợp lệ, cookie + CSRF đúng | **200**, JSON chứa username=alice, mode=session | AuthenticationManager xác thực và context được lưu vào session |
| GET /api/me với cookie sau login | **200**, JSON có username=alice | SecurityContextRepository nạp context từ session |
| GET /api/admin với cookie alice | **403** | Alice thiếu ROLE_ADMIN |
| GET /api/me không cookie | **401** | Không có Authentication được khôi phục |
| POST /api/login sai password nhưng CSRF hợp lệ | **401** | AuthenticationManager từ chối credentials |
| POST /api/login thiếu/sai CSRF token | **403** | CSRF filter chặn trước controller |

**Đây là dự đoán lý thuyết, không phải bản ghi thực thi thật.** Cookie flags, header và phần thân lỗi có thể thay đổi theo cấu hình Spring Boot/Spring Security, proxy và môi trường. Trong response 200 login có thể có Set-Cookie với session ID mới do session fixation protection; curl dùng **-c cookies.txt** để lưu thay đổi cookie.

**Cần lưu ý khi chạy lại demo:** Lệnh GET /api/csrf lấy token trước login. Trong hệ thống thật có thể chủ động làm mới CSRF token sau xác thực; nếu vậy client phải lấy token mới trước POST kế tiếp. Với ứng dụng SPA, Spring Security có các yêu cầu riêng về deferred CSRF tokens và BREACH protection.

### 5.5. Logout

Vì CSRF bật và logout dùng POST, cần gửi token hợp lệ cùng cookie phiên. Trong phạm vi demo, sau login có thể GET /api/csrf thêm một lần để lấy token hiện hành rồi POST /api/logout:

~~~bash
curl -s -b cookies.txt -c cookies.txt \
  http://localhost:8080/api/csrf > csrf.json

CSRF=$(python3 -c \
  "import json; print(json.load(open('csrf.json'))['token'])")

curl -i -X POST -b cookies.txt -c cookies.txt \
  -H "X-CSRF-TOKEN: $CSRF" \
  http://localhost:8080/api/logout

# Lần GET sau không còn Authentication theo phiên đã logout.
curl -i -b cookies.txt http://localhost:8080/api/me
~~~

Kết quả mong đợi: logout thành công trả **200** và JSON **{"status":"logged_out"}**; GET /api/me sau đó trả **401** do session bảo mật không còn hợp lệ.

**Logout không chỉ là trả 200 trong JSON.** Server phải vô hiệu hóa session/security context, xóa hoặc làm mất hiệu lực credential theo mô hình đã chọn. Với access token độc lập, xóa cookie JSESSIONID không tự làm token hết hiệu lực.

## 6. Mô hình token: phải có cả phần phát hành lẫn phần xác minh

Một endpoint có thể trả JSON giống:

~~~json
{
  "access_token": "token-value",
  "token_type": "Bearer",
  "expires_in": 900
}
~~~

Đây là **ví dụ cấu trúc**, không phải JWT thật và không phải token có thể dùng ngay. Nếu ứng dụng chọn Bearer token, cần quyết định tối thiểu:

1. **Token type:** JWT hay opaque reference token?
2. **Ai phát hành?** Authorization Server hoặc token service tin cậy nào?
3. **Ai xác minh?** Resource server kiểm chữ ký/JWK hoặc introspection, issuer, audience, expiration và các ràng buộc khác?
4. **Quyền nằm ở đâu?** Claims hoặc introspection response được chuyển thành GrantedAuthority như thế nào?
5. **Client cất token ở đâu?** Browser memory, cookie, cơ chế của native app; đánh giá XSS/CSRF theo lựa chọn.
6. **Access token sống bao lâu?** TTL, refresh token rotation, thu hồi token, logout đa thiết bị.
7. **Có HTTPS, rate limiting và chống dò mật khẩu không?** Token không bù được cho transport hoặc login endpoint yếu.

Spring Security OAuth2 Resource Server có thể kiểm tra token được phát hành bởi hệ thống phù hợp. Ví dụ **chỉ là fragment cấu hình**, cần starter OAuth2 Resource Server và issuer/JWK hợp lệ:

~~~java
http
    .sessionManagement(session -> session
        .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
    .authorizeHttpRequests(auth -> auth
        .requestMatchers("/api/me").authenticated()
        .anyRequest().denyAll())
    .oauth2ResourceServer(oauth -> oauth.jwt());
~~~

Đoạn này **không phát hành JWT**. Resource server dùng cấu hình JWT decoder/issuer tương ứng để xác minh token ở request; không được coi endpoint login JSON của ví dụ session tự tạo access token chỉ vì thêm oauth2ResourceServer.

Một client gửi:

~~~http
GET /api/me HTTP/1.1
Host: localhost:8080
Authorization: Bearer eyJ...example...
~~~

Resource server chỉ coi request đã xác thực nếu token **thực sự hợp lệ và được cấu hình cho đúng hệ thống phát hành**. Một chuỗi ngẫu nhiên hoặc JWT tự khai quyền admin mà server không tin cậy phải bị từ chối.

### 6.1. Token trong cookie có đồng nghĩa session không?

Không. Cookie là **phương tiện truyền/lưu một giá trị ở phía client**; có thể chứa session ID, JWT, opaque token hoặc một giá trị khác tùy thiết kế. Nếu browser tự đính kèm cookie vào request, vẫn phải xem xét **CSRF** cho các hành động thay đổi trạng thái. Một token được đóng trong cookie HttpOnly không tự làm hệ thống miễn nhiễm CSRF.

Ngược lại, access token được JavaScript đặt vào header **Authorization** theo chủ ý không tự được browser đính kèm như cookie, nhưng cách lưu token trong web app lại cần cân nhắc XSS, token theft và hạn chế API origin. Tách rõ **credential format**, **transport**, **storage**, **server validation** và **session persistence** để tránh các khẳng định tuyệt đối.

### 6.2. JWT không phải session mặc định của Spring Security

Một request có JWT hợp lệ có thể được xác thực độc lập với HttpSession. Trong mỗi request, Spring Security vẫn tạo/duy trì Authentication trong SecurityContext **trong lúc xử lý request**; việc không dùng HttpSession chỉ có nghĩa context đó không được duy trì bằng server-side session cho lần GET sau. Hết request, holder được dọn theo filter lifecycle.

**Stateless không có nghĩa không có SecurityContext**, và **có SecurityContext không có nghĩa đã dùng HttpSession**.

## 7. Bảo mật đặc thù khi dùng JSON login

### 7.1. CSRF không phụ thuộc Content-Type theo cách đơn giản

Một browser sử dụng cookie phiên có thể tự gửi cookie theo điều kiện cookie policy, tạo rủi ro CSRF đối với request thay đổi trạng thái. Việc gửi **application/json** thường liên quan CORS/preflight đối với request cross-origin, nhưng đó **không phải thay thế tổng quát cho CSRF protection**.

Nên quyết định CSRF dựa trên cách credential được browser tự đính kèm và threat model:
- Session cookie/browser web app: thông thường giữ CSRF protection và cung cấp token cho POST/PUT/PATCH/DELETE.
- API Bearer token chỉ nằm trong Authorization header do client thêm có chủ đích: thường có mô hình CSRF khác; vẫn cần bảo vệ token khỏi XSS và đánh giá mọi cookie/credential tự gửi.
- JWT trong cookie: vẫn phải đánh giá CSRF; nhãn “JWT” không miễn trừ cơ chế.
- Không tắt CSRF toàn hệ thống chỉ để gửi thử JSON bằng curl cho tiện.

### 7.2. HTTPS, cookie và session fixation

Trong production, login phải chạy qua **HTTPS**. Với phiên:
- Bật cookie **Secure** trong môi trường HTTPS phù hợp; dùng **HttpOnly** cho session cookie.
- Thiết lập **SameSite**, Path và Domain đúng theo kiến trúc cross-origin/cross-site.
- Dùng session fixation protection (đổi session ID tại login khi phù hợp).
- Cấu hình session timeout, invalidate session khi logout và xử lý session tồn tại trên nhiều replica.
- Không gửi session ID qua URL hoặc JSON response, không log Cookie/Set-Cookie hay mật khẩu.

CORS chỉ kiểm soát hành vi của browser đối với cross-origin requests, **không xác thực danh tính** và không cấp quyền nghiệp vụ. Với frontend khác origin, phải cấu hình CORS, credentials và cookie policy đúng nhưng vẫn giữ xác thực/phân quyền phía server.

### 7.3. Chống brute force và enumeration

Trả về cùng một thông báo lỗi cho username không tồn tại và password sai, ví dụ **401 Invalid username or password**. Ngoài ra cần rate limiting/throttling, giám sát sự kiện bất thường, MFA khi phù hợp, chính sách khóa/tạm hoãn hợp lý và không tiết lộ sự tồn tại của tài khoản qua khác biệt response dễ quan sát.

Không lưu password plaintext trong session hay log. Khi dùng UserDetailsService, cần PasswordEncoder phù hợp (ví dụ BCrypt hoặc thuật toán mạnh được cấu hình), quản lý reset password và thay đổi credential.

### 7.4. Kiểm tra quyền sau khi đăng nhập

**Đăng nhập thành công không tự cấp quyền quản trị.** Authentication có authorities và authorization policy vẫn có thể yêu cầu ROLE_ADMIN, report:write hoặc điều kiện ownership/tenant.

Nếu app lưu Authentication vào session, các quyền trong context có thể tồn tại từ thời điểm login; khi vai trò bị thu hồi giữa phiên, cần chiến lược làm mới/thực thi thu hồi phù hợp. Với JWT chứa claims, thông tin quyền cũng có thể tồn tại đến khi token hết hạn trừ khi hệ thống có quy trình thu hồi/kiểm tra bổ sung.

### 7.5. Không trả credential không cần thiết trong JSON

Sau POST login, response của mô hình session có thể chỉ là:

~~~json
{"username":"alice","mode":"session"}
~~~

Không cần trả password, credential hash, session ID hoặc toàn bộ Authentication để client biết đã login. Ngược lại, mô hình token cần trả access token theo tiêu chuẩn được chọn và truyền qua kênh an toàn; hạn chế đưa token ra nơi dễ bị log hoặc analytics thu thập.

## 8. Kiểm thử tích hợp cho JSON login dùng session

Một kiểm thử tốt phải có **hai request khác nhau**, không chỉ assert POST /api/login là 200. Nếu request sau thiếu cookie, hoặc login không lưu SecurityContext, tình huống sẽ bộc lộ.

Trong project Gradle của demo, thêm test dependencies nếu chưa có:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Đây là **fragment của build.gradle**; Spring Initializr thường đã thêm starter-test, tránh khai báo trùng.

Tạo **src/test/java/com/example/demo/JsonLoginSessionApplicationTest.java**:

~~~java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class JsonLoginSessionApplicationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void jsonLoginPersistsAuthenticationInSession()
            throws Exception {

        MvcResult login = mvc.perform(post("/api/login")
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    "{\"username\":\"alice\",\"password\":\"demo123\"}"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.mode").value("session"))
            .andReturn();

        MockHttpSession session = (MockHttpSession)
                login.getRequest().getSession(false);

        mvc.perform(get("/api/me").session(session))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.username").value("alice"));

        mvc.perform(get("/api/admin").session(session))
            .andExpect(status().isForbidden());

        mvc.perform(get("/api/me"))
            .andExpect(status().isUnauthorized());
    }
}
~~~

Chạy:

~~~bash
./gradlew test
~~~

Với Windows dùng **gradlew.bat test**. Test sử dụng **MockMvc và CSRF test helper** để tập trung chứng minh rằng sau POST JSON có lưu Authentication vào cùng HttpSession, còn GET không mang session phải bị coi là chưa đăng nhập. Mã test thể hiện kỳ vọng theo cấu hình bài học; chưa chạy Gradle trong nội dung này.

Đối với hệ thống production, nên bổ sung:
1. Login sai mật khẩu trả 401, không tạo authenticated session.
2. POST login thiếu CSRF token bị từ chối.
3. Logout vô hiệu hóa phiên; GET /api/me sau logout trả 401.
4. Session fixation protection hoạt động đúng với phiên có trước login.
5. Session timeout, cookie flags, cross-origin frontend, quyền bị thu hồi và concurrent sessions.
6. Endpoint admin chỉ mở cho user có ROLE_ADMIN.
7. Không log/echo password, token hay session identifier.

## 9. Những lỗi hiểu sai thường gặp

| Nhận định hoặc hiện tượng | Vấn đề | Cách phân tích đúng |
| --- | --- | --- |
| “POST login nhận JSON nên chắc chắn dùng JWT.” | Nhầm body encoding với auth persistence | Kiểm tra response, cookie, token service và security config. |
| “Login trả 200 thì GET /me chắc chắn đã xác thực.” | Chưa chắc context đã lưu hoặc client gửi credential | Kiểm tra saveContext, repository, Set-Cookie/Cookie hoặc Authorization header. |
| “Có JSESSIONID nghĩa là đã đăng nhập.” | Session có thể tồn tại vì CSRF, request cache hoặc dữ liệu khác | Kiểm tra Authentication thực tế trong SecurityContext. |
| “Không có JSESSIONID thì không có SecurityContext.” | Token authentication vẫn dùng context trong request | Xem resource-server/Bearer configuration. |
| “JWT và cookie là hai phương án đối lập tuyệt đối.” | JWT cũng có thể được vận chuyển bằng cookie | Tách token format khỏi transport/storage. |
| “Đặt token trong cookie HttpOnly là miễn CSRF.” | Browser có thể tự gửi cookie | Đánh giá CSRF theo loại request và cookie policy. |
| “Tắt CSRF là bước bắt buộc để nhận application/json.” | Nhầm CSRF với JSON parsing | Dùng header CSRF và cơ chế client phù hợp nếu bảo vệ session. |
| “SecurityContextHolder.setContext là đủ để giữ login.” | Spring Security 6 custom flow cần explicit save | Dùng SecurityContextRepository.saveContext khi chọn persistence. |
| “Token trả từ login tự được Spring kiểm tra ở GET sau.” | Chưa cấu hình validation/decoder/introspection | Cấu hình Resource Server hoặc authentication filter phù hợp. |
| “Logout JSON trả 200 là đã thu hồi tất cả token.” | Logout stateful và token revocation khác nhau | Thiết kế invalidation/revocation theo credential đang sử dụng. |
| “Mọi lần GET trả 403 đều do password sai.” | 401, 403, CSRF, role và matcher khác nhau | Đọc status, Authentication, GrantedAuthority và thứ tự policy. |
| “Cookie chứa UserDetails dưới dạng JSON.” | Với session chuẩn cookie thường chỉ chứa session ID | Tìm dữ liệu ở server-side session store. |
| “Stateless loại bỏ nhu cầu bảo vệ token.” | Token trở thành credential quan trọng | Bảo vệ HTTPS, token storage, TTL, rotation/revocation, audience/issuer. |
| “Session phải dùng cùng server instance.” | Có thể dùng shared session store | Thiết kế topology/Redis/Spring Session/affinity theo yêu cầu. |

## 10. Checklist ra quyết định kiến trúc

Trước khi đưa một JSON login endpoint vào hệ thống, hãy trả lời:

1. **Client là ai?** Server-rendered browser, SPA, mobile app hay service-to-service?
2. **Credential đầu vào** là username/password, passkey, OTP, OIDC authorization code hay loại khác? Chỉ JSON body không đủ mô tả.
3. **Ai xác thực?** AuthenticationManager nội bộ, identity provider hay authorization server?
4. **Request tiếp theo xác thực ra sao?** Session cookie, Bearer token, mTLS hay phương án khác?
5. **Ai lưu/thu hồi trạng thái?** HttpSession store, token service, revocation list, refresh token store?
6. **CSRF có cần không?** Browser có tự gửi cookie/credential đối với request cross-site không?
7. **Thời gian sống?** Session idle timeout, access-token TTL, refresh token expiration và rotation.
8. **Logout có hiệu lực ở đâu?** Server session invalidation, refresh token revocation, client deletion, tất cả thiết bị?
9. **Quyền được tính khi nào?** Login time, mỗi request hay khi thay đổi role?
10. **Có kiểm thử hai request độc lập chưa?** Một POST login thành công và một GET protected với/không có credential phù hợp?
11. **Đã cấu hình HTTPS, cookie flags, CORS và bảo vệ đăng nhập khỏi brute force chưa?**
12. **Có dùng cơ chế Spring Security chuẩn khi có thể không?** Custom login/controller cần đảm bảo các bước mà standard filters đã xử lý sẵn.

**Kết luận:** **JSON login chỉ quyết định cách tiếp nhận credential.** Nếu muốn **session**, hãy lưu/khôi phục SecurityContext qua SecurityContextRepository và HttpSession/cookie đúng cách. Nếu muốn **token**, hãy phát hành token với một cơ chế tin cậy và cấu hình xác minh token ở request sau. Việc chọn session hay token là quyết định về **quản lý trạng thái, credential và bảo mật**, không phải hệ quả tự động của Content-Type: application/json.

## Tài liệu chính thức để nghiên cứu tiếp

- Spring Security 6.5 — Authentication Persistence and Session Management: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html
- Spring Security 6.5 — Persisting Authentication: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/persistence.html
- Spring Security 6.5 — DaoAuthenticationProvider: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html
- Spring Security 6.5 — CSRF protection for JavaScript applications: https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html
- Spring Security 6.5 — OAuth2 Resource Server JWT: https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/jwt.html
- Spring Security 6.5 — OAuth2 Resource Server Opaque Tokens: https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/opaque-token.html
- Spring Security 6.5 — Logout: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/logout.html
