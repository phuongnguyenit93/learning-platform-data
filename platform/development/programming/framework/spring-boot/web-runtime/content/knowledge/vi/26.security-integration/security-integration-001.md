# Ảnh hưởng của spring-boot-starter-security tới ứng dụng web

## 1. Điều gì thay đổi khi thêm starter bảo mật?

Một dự án Spring Boot có thể có controller chạy tốt trước khi cài bảo mật:

```java
@RestController
class HelloController {
    @GetMapping("/hello")
    String hello() {
        return "hello";
    }
}
```

Khi chỉ có `spring-boot-starter-web`, request `GET /hello` thường trả HTTP 200 với body `hello` nếu không có thành phần security riêng. Nhưng sau khi thêm:

```groovy
implementation 'org.springframework.boot:spring-boot-starter-security'
```

Spring Boot nhận thấy Spring Security trên classpath và **tự cấu hình bảo mật cho ứng dụng web**. Nếu ứng dụng chưa cung cấp một cấu hình thay thế, nhiều endpoint trước đây truy cập được mà không cần đăng nhập nay sẽ **yêu cầu authentication**; browser có thể được chuyển sang trang login, còn API client có thể nhận HTTP 401. Các request thay đổi dữ liệu bằng POST/PUT/PATCH/DELETE có thể bị **HTTP 403 do thiếu CSRF token**, kể cả khi người gọi đã được xác thực.

**Điểm chính:** starter không chỉ bổ sung thư viện Java. Nó làm xuất hiện **security filter chain/web filter chain** và các bean authentication mặc định tác động lên HTTP request, response, cookie/session, error handling, test và cách tích hợp frontend.

Bài này tập trung **Spring Boot 3.3.x, Spring Security 6.3.x, Java 17+** để minh họa ổn định. Với sản phẩm thực tế, cần theo dõi nhánh Spring Boot còn được hỗ trợ và cập nhật security fixes. Cấu hình ở các major versions mới có thể thay đổi package/API.

## 2. So sánh trước và sau khi có Spring Security

| Tình huống | Chưa có Spring Security (mặc định web thuần) | Có starter-security, chưa tự cấu hình |
|---|---|---|
| `GET /hello` không cung cấp credentials | Thường HTTP 200 | Thường HTTP 401 (API) hoặc 302 đến login (browser) |
| `GET /public` dù tên là “public” | Không có rule bảo vệ từ Spring Security | Vẫn có thể bị yêu cầu login vì **tên path không tự tạo ngoại lệ** |
| Login | Không có flow login của Spring Security | Có support form login và HTTP Basic |
| Tài khoản mặc định | Không có `user` tự tạo bởi Spring Security | In-memory user `user` và password được tạo ngẫu nhiên cho development |
| `POST /orders` từ browser/client | Gọi controller nếu route hợp lệ | Có thể bị chặn bởi authentication hoặc **CSRF** trước controller |
| Authentication/authorization | Ứng dụng tự làm hoặc chưa có | Filter chain kiểm tra identity, authorities và access rules |
| Response headers | Do framework/proxy/app cấu hình | Spring Security có các security headers mặc định |
| Static files và `/error` | Thường truy cập nếu đường dẫn tồn tại | Theo mặc định thường nằm trong phạm vi bảo vệ, trừ endpoint/route được cho phép |
| Actuator | Phụ thuộc có starter actuator hay chưa | Có chính sách auto-security riêng cho Actuator, đặc biệt endpoint health |
| Test MockMvc | Có thể gọi thẳng endpoint | Test phải xét authentication, roles, CSRF và security filter chain |

Cần phân biệt **mặc định của starter** với điều xảy ra sau khi bạn tạo bean `SecurityFilterChain`. Khi đã định nghĩa custom chain, **Boot không tiếp tục dùng toàn bộ default web chain**; lúc đó các access rules do bạn chịu trách nhiệm. Điều này có thể gây lỗ hổng nếu developer chỉ cho phép một nhóm URL rồi vô tình để endpoint khác không có chain bảo vệ.

**Ngoại lệ quan trọng:** cơ chế login (ví dụ `/login`) cần được truy cập trước khi đăng nhập; nói “mọi URL tuyệt đối bị chặn” là cách diễn đạt quá mức. Spring Boot 3.3 mô tả mặc định bảo vệ các **application endpoints** kể cả `/error`; khi có Actuator, auto-configuration thường cho phép health và bảo vệ những endpoint Actuator khác đã được expose.

## 3. Spring Boot tự cấu hình bean nào?

Ở stack Servlet/MVC, tài liệu Spring Boot 3.3 mô tả vai trò của:

- `SecurityAutoConfiguration` và cấu hình web đi kèm: tự tích hợp Spring Security với servlet stack.
- `UserDetailsServiceAutoConfiguration`: cung cấp `UserDetailsService` in-memory một người dùng nếu chưa có authentication infrastructure thay thế tương ứng.
- `DefaultAuthenticationEventPublisher`: công bố sự kiện authentication cho hệ thống có listener/monitoring phù hợp.
- `SecurityFilterChain` mặc định: yêu cầu xác thực và kích hoạt các cơ chế login phù hợp với web client.

Ở WebFlux tương ứng là `ReactiveSecurityAutoConfiguration`, `ReactiveUserDetailsServiceAutoConfiguration`, `SecurityWebFilterChain` và `ReactiveUserDetailsService`.

Trong cấu hình dev mặc định:
- Tên người dùng: **`user`**.
- Password: sinh ngẫu nhiên lúc khởi động, thường log WARN dạng `Using generated security password: ...`.
- Password này **không phải mật khẩu production**, và có thể đổi khi restart.
- Nếu chỉnh logging khiến category `org.springframework.boot.autoconfigure.security` không in WARN, bạn có thể không thấy password ở console dù user được tạo.

Có thể đặt cho môi trường thử nghiệm:

```properties
spring.security.user.name=demo
spring.security.user.password=local-demo-only
spring.security.user.roles=USER
```

Nhưng cấu hình mật khẩu rõ trong source **không được dùng production**. Production phải dùng secret manager/identity provider, password hashing, rotation, và security policy theo ứng dụng. Các property `spring.security.user.*` áp dụng cho **default user setup**; khi bạn tự định nghĩa `UserDetailsService` hoặc cơ chế authentication khác, Boot sẽ điều chỉnh auto-configuration và chúng có thể không còn là nguồn account thực tế.

### 3.1. Ghi đè default web chain khác ghi đè default user

Hai quyết định tách biệt:

| Bạn thêm bean nào? | Tác động chính |
|---|---|
| `SecurityFilterChain` (MVC) | Boot lùi khỏi **default web security rules**, nhưng **không tự động loại default UserDetailsService** |
| `UserDetailsService`, `AuthenticationProvider` hoặc `AuthenticationManager` | Boot lùi khỏi cơ chế tạo default in-memory user tương ứng |
| `SecurityWebFilterChain` (WebFlux) | Thay/định nghĩa access rules reactive riêng |
| `ReactiveUserDetailsService` / `ReactiveAuthenticationManager` | Thay cơ chế user/authentication reactive mặc định |
| Một số OAuth2 client/resource server/SAML dependencies | Có thể làm auto-config default user lùi, tùy loại module và stack |

**Không suy đoán:** “Tôi có một `SecurityFilterChain` nên generated user/password chắc chắn biến mất.” Sai: security rules và user repository được auto-config theo điều kiện riêng.

Cũng **không suy đoán** rằng thêm starter-security nghĩa là tự có JWT/OAuth2/OpenID Connect/SAML provider hoặc database user table. Những tính năng đó cần module/cấu hình khác và nguồn identity thật.

## 4. HTTP request đi qua filter chain như thế nào?

Trong Spring MVC/Servlet, security thường chạy **trước controller**:

```text
Browser/API client
     │
     ▼
Servlet container (Tomcat/Jetty)
     │
     ▼
DelegatingFilterProxy
     │
     ▼
FilterChainProxy
     │
     └── Chọn SecurityFilterChain khớp request
             │
             ├── Load/manage SecurityContext
             ├── Security headers
             ├── CSRF checks theo method/config
             ├── Authentication: session / HTTP Basic / form login / ...
             ├── Authorization: role/authority/URL rule
             └── Exception translation → 401/403/login redirect
                     │
                     ▼
              DispatcherServlet
                     │
                     ▼
                @Controller
                     │
                     ▼
                HTTP response
```

**Thứ tự/chính xác tên filter phụ thuộc cấu hình**, nên hình trên là mô hình logic, không khẳng định tất cả filter luôn có mặt theo một thứ tự cố định. Những class thường gặp ở Servlet là `FilterChainProxy`, `SecurityContextHolderFilter`, `CsrfFilter`, `BasicAuthenticationFilter`, `UsernamePasswordAuthenticationFilter`, `ExceptionTranslationFilter` và `AuthorizationFilter`.

Quy trình tổng quát:
1. Security tìm chain khớp URL/method; nếu có nhiều chain, thường chain đầu tiên khớp được chọn.
2. Cơ chế authentication đọc credentials (session, Authorization Basic/Bearer, form fields... theo config) và thiết lập `Authentication` trong `SecurityContext`.
3. Authorization kiểm tra user có được phép đi tiếp không; khi rule yêu cầu `authenticated()`, anonymous thường không qua.
4. Với request cần chống CSRF, token cũng được kiểm tra. **Authentication hợp lệ không miễn CSRF**.
5. Chỉ khi tất cả rule liên quan cho phép, controller mới xử lý.

`Authentication` đại diện principal, credentials (đã được xử lý theo chính sách), authorities và trạng thái authenticated. `Authorization` quyết định quyền truy cập. **Authenticated không đồng nghĩa Authorized**: một user đã đăng nhập vẫn có thể nhận 403 nếu thiếu role `ADMIN` hoặc `EDITOR`.

Một authentication failure thường dẫn tới `401 Unauthorized` cho API dùng HTTP Basic; người dùng HTML có thể được redirect đến login. Một user đã xác thực nhưng không đủ quyền thường nhận `403 Forbidden`. Tuy nhiên status có thể khác do entry point, Accept header, exception handler và custom config; hãy test response của chính ứng dụng.

## 5. Vì sao browser thấy trang login nhưng curl nhận 401?

Spring Boot dùng content negotiation/authentication entry points để quyết định hành vi mặc định của web app:
- Browser gửi `Accept: text/html` thường được hướng tới `/login` bằng redirect `302` nếu chưa authenticated.
- API client thường gửi `Accept: application/json` và có thể nhận `401` với header `WWW-Authenticate: Basic ...` khi chưa có credentials.
- Nếu gửi `Authorization: Basic ...` đúng, request đọc dữ liệu có thể được phép.
- Nếu sai user/password, response thường `401`; đừng biến “wrong password” thành `500` trong custom authentication.

**Không xem redirect 302 là lỗi controller.** Request thường bị filter chặn trước khi vào handler. Một browser tự động theo redirect sẽ hiển thị trang login thay vì body endpoint, khiến người mới học tưởng route biến mất.

Ví dụ test có chủ đích:

```bash
curl -i -H 'Accept: application/json' http://localhost:8080/private
curl -i -H 'Accept: text/html' http://localhost:8080/private
```

Kết quả tương ứng trong cấu hình mặc định thường là 401 và 302 đến login; không hardcode chính xác header hoặc URL redirect khi framework/custom config có thể thay đổi chúng.

## 6. Ví dụ hoàn chỉnh A: ứng dụng MVC trước khi custom security

Ví dụ dùng **Spring Boot 3.3.13 + Java 17 + Gradle** và không cần database. Ban đầu **không tạo `SecurityConfig`** để quan sát hành vi tự cấu hình thật. Sau đó thêm custom chain ở mục 8 và test ở mục 9.

Cấu trúc khởi đầu:

```text
security-starter-demo/
├── build.gradle
└── src/
    ├── main/
    │   ├── java/com/example/securitydemo/SecurityStarterApplication.java
    │   └── resources/application.properties
    └── test/
        └── java/com/example/securitydemo/SecurityRulesTest.java  # Tạo ở mục 9
```

**`build.gradle`:**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

**`src/main/resources/application.properties`** ở giai đoạn đầu:

```properties
server.port=8080
# Chưa đặt spring.security.user.* để quan sát generated password.
```

**`src/main/java/com/example/securitydemo/SecurityStarterApplication.java`:**

```java
package com.example.securitydemo;

import java.security.Principal;
import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class SecurityStarterApplication {

    public static void main(String[] args) {
        SpringApplication.run(SecurityStarterApplication.class, args);
    }
}

@RestController
class DemoController {

    @GetMapping("/public")
    String publicPage() {
        return "public content";
    }

    @GetMapping("/account")
    Map<String, String> account(Principal principal) {
        return Map.of("name", principal.getName());
    }

    @PostMapping(
            path = "/notes",
            consumes = MediaType.APPLICATION_JSON_VALUE)
    ResponseEntity<SavedNote> save(
            @RequestBody NoteInput input,
            Principal principal) {
        // Demo không ghi database, chỉ minh họa điều kiện authorization/CSRF.
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(new SavedNote(principal.getName(), input.text()));
    }
}

record NoteInput(String text) {}
record SavedNote(String owner, String text) {}
```

Đây là **một file Java hợp lệ**, chỉ có `SecurityStarterApplication` là top-level `public class`; controller và records còn lại ở cùng package được Boot component scan. Vì chưa có bean custom `SecurityFilterChain`, mặc định starter-security vẫn bảo vệ **`/public`, `/account` và `/notes`**.

**Chạy:**

```bash
gradle bootRun
```

Nếu project có Gradle Wrapper: `./gradlew bootRun` (Linux/macOS) hoặc `.\gradlew.bat bootRun` (Windows PowerShell). JDK 17+ và Gradle tương thích Boot 3.3.13 là điều kiện chạy. Console sẽ có generated password dùng trong lượt khởi động này nếu logger ở WARN phù hợp.

### 6.1. Kiểm chứng khác biệt chỉ bằng thêm dependency

**Không có credentials:**

```bash
curl -i -H 'Accept: application/json' http://localhost:8080/public
curl -i -H 'Accept: application/json' http://localhost:8080/account
```

Dù tên `/public`, hai request thường bị security yêu cầu authentication và trả **HTTP 401** trong ngữ cảnh client API. Controller chưa được gọi.

**Có credentials mặc định:** thay `<GENERATED_PASSWORD>` bằng đúng password trong log của lượt chạy:

```bash
curl -i -u 'user:<GENERATED_PASSWORD>' \
  http://localhost:8080/account
```

Kết quả mong đợi nếu password đúng: HTTP 200 và JSON dạng:

```json
{"name":"user"}
```

Dùng `-u` trên command line có thể lộ credential trong shell history/process list; chỉ chấp nhận trong lab local với password sinh cho development. Không log/copy password production ra tài liệu.

**POST đã authenticated nhưng thiếu CSRF token:**

```bash
curl -i -u 'user:<GENERATED_PASSWORD>' \
  -H 'Content-Type: application/json' \
  -d '{"text":"my note"}' \
  http://localhost:8080/notes
```

Với CSRF mặc định của web app, request POST thiếu token thường nhận **403 Forbidden**. Điều đó không phải lỗi JSON mapping: `CsrfFilter` có thể từ chối trước khi controller đọc `NoteInput`.

**Để POST thành công từ browser có session**, cần dùng cơ chế CSRF token đúng theo giao diện/frontend (form hidden field hoặc header/token repository tương ứng). Bài test mục 9 dùng `spring-security-test` để cung cấp token hợp lệ thay vì tự hardcode token.

### 6.2. Điều gì chưa thay đổi?

Thêm starter-security **không tự**:
- Tạo bảng người dùng trong database.
- Định nghĩa role `EDITOR` cho app.
- Tự kết nối OAuth2/OIDC provider hay phát hành JWT.
- Bảo mật kết nối HTTPS nếu bạn chưa cấu hình TLS/ingress.
- Thiết kế permission cho từng dữ liệu/tenant hoặc thay thế validation.
- Tự giới hạn mọi hình thức brute-force, khóa tài khoản, kiểm soát bot/rate limit.
- Tự cấp phép CORS origins tùy ý.
- Biến application state thành transaction hay mã hóa toàn bộ dữ liệu phiên.

Starter cung cấp các thành phần bảo mật và defaults có giá trị, nhưng **security policy production vẫn phải do người phát triển thiết kế, kiểm thử và vận hành**.

## 7. “Public URL” không tự sinh quyền truy cập

Một trong những sai lầm thường gặp là đặt tên controller `/public`, `/health` hay `/login-info` rồi nghĩ Spring Security tự biết endpoint nào nên mở.

Trong default security configuration, **all application endpoints require authentication**, ngoại trừ những điểm phục vụ authentication flow hoặc auto-config đặc thù. Muốn cho phép guest truy cập, ứng dụng phải khai báo rule ví dụ `requestMatchers("/public").permitAll()`. Đặt `permitAll` **không gỡ security filters**; những biện pháp áp dụng khác như security headers và CSRF vẫn có thể hoạt động khi phù hợp.

Phân biệt:

```java
// Chỉ là cú pháp minh họa trong authorizeHttpRequests:
.requestMatchers("/public").permitAll()
.requestMatchers("/admin/**").hasRole("ADMIN")
.anyRequest().authenticated()
```

Mỗi matcher là một **authorization rule**, không phải endpoint registration. Spring MVC controller vẫn phải có `@GetMapping` tương ứng. Các rule được xét theo thứ tự khai báo thích hợp; broad match đặt trước specific match có thể che mất quy tắc quan trọng. Không dán đoạn trên thành Java file độc lập.

**Static resources:** file dưới `src/main/resources/static` được Boot phục vụ bởi web infrastructure nhưng mặc định Spring Security có thể bảo vệ. Nếu CSS/JS/logo của trang login cần công khai, permit đúng đường static bằng `PathRequest.toStaticResources().atCommonLocations()` hoặc matchers cụ thể. Không `web.ignoring()` một cách đại trà chỉ để CSS chạy nếu `permitAll` là đủ.

## 8. Thay chính sách mặc định bằng SecurityFilterChain của ứng dụng

Giả sử mục tiêu:
- `GET /public` cho guest.
- `GET /account` cần authenticated user.
- `POST /notes` yêu cầu role `EDITOR` **và** CSRF token hợp lệ.
- Các request không khai báo rõ bị deny.
- Đăng nhập hỗ trợ form login và HTTP Basic cho demo.
- Mật khẩu demo được hash bằng BCrypt thay vì lưu plaintext trong `UserDetailsService`.

Tạo **file mới** `src/main/java/com/example/securitydemo/SecurityConfig.java`:

```java
package com.example.securitydemo;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
class SecurityConfig {

    @Bean
    SecurityFilterChain applicationSecurity(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers(HttpMethod.GET, "/public").permitAll()
                .requestMatchers(HttpMethod.GET, "/account").authenticated()
                .requestMatchers(HttpMethod.POST, "/notes").hasRole("EDITOR")
                .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults())
            .formLogin(Customizer.withDefaults());

        // CSRF để mặc định BẬT. Không gọi csrf.disable().
        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(
            PasswordEncoder encoder,
            @Value("${demo.security.editor-password}") String rawPassword) {

        UserDetails editor = User.withUsername("editor")
                .password(encoder.encode(rawPassword))
                .roles("EDITOR")
                .build();

        return new InMemoryUserDetailsManager(editor);
    }
}
```

Và thêm vào **`application.properties`**:

```properties
# Chỉ là mật khẩu local để học; không được giữ fallback này ở prod.
demo.security.editor-password=${DEMO_EDITOR_PASSWORD:local-only-change-me}
```

**Giải thích:**

1. Có bean `SecurityFilterChain` → Boot không tiếp tục áp default web chain. **Các rule này là trách nhiệm của ứng dụng.**
2. Có bean `UserDetailsService` → Boot không tạo user mặc định `user` nữa; trong ví dụ dùng `editor`.
3. `BCryptPasswordEncoder` hash password trước khi đặt vào `UserDetails`. Mã demo nhận raw password từ config để tiện thử local, không phải kiến trúc identity storage production.
4. `hasRole("EDITOR")` kiểm tra authority theo convention `ROLE_EDITOR`. `roles("EDITOR")` ở `UserDetails` tạo authority tương ứng.
5. `anyRequest().denyAll()` là **fail-closed**: URL không được liệt kê sẽ bị từ chối. Trong thực tế nếu dùng form login và route static/login/logout cần thêm rule và kiểm thử theo requirement. Mẫu này ưu tiên minh họa API security.
6. `httpBasic(...)` cho phép thử với curl; `formLogin(...)` hỗ trợ browser login. Authentication entry point quyết định 401/redirect theo request.
7. CSRF không bị tắt. Một POST có role đúng mà thiếu CSRF vẫn thất bại.

**Lưu ý quan trọng về default login:** Spring Security có cơ chế tạo trang `/login` và filter xử lý POST login khi bật `formLogin`; `anyRequest().denyAll()` không nên được hiểu là tự chặn các endpoint đặc biệt do security filter quản lý. Nếu tùy chỉnh login page, paths hoặc multiple filter chains, cần khai báo `permitAll` cho các route/login assets cần thiết và viết browser integration tests. Các endpoint tùy biến của ứng dụng không tự được permit.

**Lệnh chạy sau khi thêm config:**

```bash
gradle bootRun
```

Có thể đặt `DEMO_EDITOR_PASSWORD` trên máy local thay vì dùng fallback (ví dụ export trong shell của bạn). Trên production bắt buộc loại fallback và dùng secrets/identity provider.

### 8.1. So sánh response sau khi custom

**Endpoint public giờ mở:**

```bash
curl -i http://localhost:8080/public
```

Dự kiến HTTP 200 và body:

```text
public content
```

**Endpoint account cần login:**

```bash
curl -i -H 'Accept: application/json' http://localhost:8080/account
```

Dự kiến HTTP 401 trong tình huống API không có credentials.

**Authenticated bằng user editor:**

```bash
curl -i -u editor:local-only-change-me \
  -H 'Accept: application/json' http://localhost:8080/account
```

Dự kiến HTTP 200:

```json
{"name":"editor"}
```

**POST có quyền nhưng thiếu CSRF:**

```bash
curl -i -u editor:local-only-change-me \
  -H 'Content-Type: application/json' \
  -d '{"text":"hello"}' http://localhost:8080/notes
```

Dự kiến HTTP 403 vì CSRF protection. Khi dùng test helper `csrf()`, request cùng body có thể trả HTTP 201 và JSON:

```json
{"owner":"editor","text":"hello"}
```

Các output trên dựa vào đúng config demo và chưa có global exception handler riêng; header/whitespace có thể khác. Không viết JavaScript frontend giả vờ có CSRF token: với browser thật, cần tích hợp CSRF token repository/form/header theo tài liệu Spring Security.

## 9. Kiểm thử security bằng MockMvc và spring-security-test

Một lỗi kiểm thử phổ biến: unit test gọi trực tiếp method controller rồi thấy 200, trong khi production request bị filter chain trả 401/403. Để kiểm thử **hành vi HTTP thực**, dùng `@SpringBootTest`, `@AutoConfigureMockMvc`, `spring-security-test` và assertions status/response.

**Tạo file `src/test/java/com/example/securitydemo/SecurityRulesTest.java`** sau khi đã thêm `SecurityConfig.java`:

```java
package com.example.securitydemo;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(properties = {
        "demo.security.editor-password=only-for-test"
})
@AutoConfigureMockMvc
class SecurityRulesTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicEndpointIsOpen() throws Exception {
        mvc.perform(get("/public"))
                .andExpect(status().isOk());
    }

    @Test
    void accountRequiresAuthentication() throws Exception {
        mvc.perform(get("/account")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void correctBasicCredentialsCanReadAccount() throws Exception {
        mvc.perform(get("/account")
                        .with(httpBasic("editor", "only-for-test")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.name").value("editor"));
    }

    @Test
    void editorPostWithoutCsrfIsForbidden() throws Exception {
        mvc.perform(post("/notes")
                        .with(httpBasic("editor", "only-for-test"))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"text\":\"hello\"}"))
                .andExpect(status().isForbidden());
    }

    @Test
    void editorPostWithCsrfIsCreated() throws Exception {
        mvc.perform(post("/notes")
                        .with(httpBasic("editor", "only-for-test"))
                        .with(csrf())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"text\":\"hello\"}"))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.owner").value("editor"));
    }

    @Test
    void authenticatedUserWithoutEditorRoleIsForbidden() throws Exception {
        mvc.perform(post("/notes")
                        .with(user("viewer").roles("VIEWER"))
                        .with(csrf())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"text\":\"hello\"}"))
                .andExpect(status().isForbidden());
    }
}
```

Chạy:

```bash
gradle test
```

**Kỳ vọng:** cả 6 test pass nếu code/cấu hình khớp. Đây là kết quả **mong đợi, không phải output đã được chạy xác minh**. Các test có giá trị vì chúng kiểm tra riêng:
- Guest có thể vào `/public`.
- Guest bị từ chối ở `/account`.
- User có credentials đúng được xác thực.
- CSRF chặn unsafe request dù role đã đúng.
- CSRF token hợp lệ cho phép tiếp tục tới controller.
- User authenticated nhưng thiếu role vẫn bị 403.

`with(user("viewer").roles("VIEWER"))` của spring-security-test **giả lập principal trong MockMvc**, không chứng minh có account viewer trong database. Muốn kiểm tra user repository/authentication thật, test riêng bằng credentials/mocks integration có kiểm soát.

**Đừng dùng `@WithMockUser`/`user()` để thay thế toàn bộ end-to-end authentication tests**, vì chúng bỏ qua việc kiểm tra password encoder, OAuth2 flow, bearer token validation hoặc session store. Chúng rất hữu ích để tách rule authorization khỏi authentication.

## 10. Spring WebFlux cũng bị ảnh hưởng nhưng cơ chế filter khác

Nếu ứng dụng chỉ có `spring-boot-starter-webflux` và thêm `spring-boot-starter-security`, mặc định reactive stack cũng được bảo vệ. Tuy nhiên không dùng Servlet `SecurityFilterChain`/`HttpSecurity` để bảo vệ WebFlux server; loại tương ứng là:

| Spring MVC / Servlet | Spring WebFlux / Reactive |
|---|---|
| `HttpServletRequest` | `ServerWebExchange` / `ServerHttpRequest` |
| `FilterChainProxy` và servlet filters | `WebFilterChainProxy` và `WebFilter` |
| `SecurityFilterChain` | `SecurityWebFilterChain` |
| `HttpSecurity` | `ServerHttpSecurity` |
| `UserDetailsService` | `ReactiveUserDetailsService` |
| `InMemoryUserDetailsManager` | `MapReactiveUserDetailsService` |
| `authorizeHttpRequests` | `authorizeExchange` |
| `requestMatchers` | `pathMatchers` / `matchers` |
| `@EnableMethodSecurity` | `@EnableReactiveMethodSecurity` |

### 10.1. Ví dụ WebFlux độc lập (Java 17+)

Tạo **project riêng** `webflux-security-demo` để không vô tình chạy MVC do cùng classpath có starter-web.

**`build.gradle`:**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

**`src/main/resources/application.properties`:**

```properties
server.port=8081
demo.security.reactive-password=${DEMO_READER_PASSWORD:local-reader-only}
```

**`src/main/java/com/example/reactivesecurity/ReactiveSecurityApplication.java`:**

```java
package com.example.reactivesecurity;

import java.util.Map;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.ReactiveUserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@SpringBootApplication
public class ReactiveSecurityApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveSecurityApplication.class, args);
    }
}

@RestController
class ReactiveController {

    @GetMapping("/public")
    Mono<Map<String, String>> publicEndpoint() {
        return Mono.just(Map.of("message", "public webflux"));
    }

    @GetMapping("/private")
    Mono<Map<String, String>> privateEndpoint() {
        return Mono.just(Map.of("message", "private webflux"));
    }
}

@Configuration(proxyBeanMethods = false)
class ReactiveSecurityConfig {

    @Bean
    SecurityWebFilterChain springSecurityFilterChain(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchange -> exchange
                        .pathMatchers("/public").permitAll()
                        .pathMatchers("/private").authenticated()
                        .anyExchange().denyAll())
                .httpBasic(Customizer.withDefaults())
                .formLogin(Customizer.withDefaults())
                .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    ReactiveUserDetailsService users(
            PasswordEncoder encoder,
            @Value("${demo.security.reactive-password}") String password) {

        UserDetails reader = User.withUsername("reader")
                .password(encoder.encode(password))
                .roles("READER")
                .build();

        return new MapReactiveUserDetailsService(reader);
    }
}
```

Cấu trúc tối thiểu project là `build.gradle`, file Java nêu trên, file `application.properties`. Trong code chỉ `ReactiveSecurityApplication` là top-level public class, class khác cùng package đều có thể được component scan.

Chạy `gradle bootRun` ở project WebFlux. Kiểm tra:

```bash
curl -i http://localhost:8081/public

curl -i -H 'Accept: application/json' \
  http://localhost:8081/private

curl -i -u reader:local-reader-only \
  http://localhost:8081/private
```

Kỳ vọng tương ứng:
- HTTP 200, JSON `{"message":"public webflux"}`.
- HTTP 401 khi không cung cấp credentials trong ngữ cảnh API.
- HTTP 200, JSON `{"message":"private webflux"}` khi reader authenticated.

**Không dùng `block()` trong WebFlux handler để lấy authentication context.** Với pipeline reactive, Spring Security dùng reactive context; nếu cần principal trong handler, dùng argument `Principal`/`Mono<Principal>` được framework hỗ trợ hoặc `ReactiveSecurityContextHolder` theo contract.

Trong WebFlux, method security cũng phải được cấu hình reactive theo yêu cầu. Không sao chép nguyên `SecurityFilterChain(HttpSecurity)` của MVC rồi nghĩ đó là bảo mật server reactive.

## 11. CSRF: vì sao POST thất bại dù đã đăng nhập?

**Cross-Site Request Forgery (CSRF)** là tình huống trình duyệt của nạn nhân tự động gửi credentials như session cookie tới một website khác theo hành động bị kẻ tấn công kích hoạt. Nếu server chỉ kiểm tra cookie mà không xác minh ý định của user, request thay đổi dữ liệu có thể bị lợi dụng.

Spring Security **bật CSRF protection theo mặc định** cho nhiều ứng dụng web (Servlet và WebFlux) với các HTTP methods không được coi là safe. Thường GET/HEAD/OPTIONS/TRACE được coi safe; POST/PUT/PATCH/DELETE phải có CSRF token hợp lệ khi cơ chế này áp dụng.

```text
Browser có session cookie
    │
    ├── GET /account                  → Đọc dữ liệu (thường không cần CSRF)
    │
    └── POST /notes + cookie
            ├── có token hợp lệ       → tiếp tục tới authorization/controller
            └── thiếu/sai token       → thường HTTP 403
```

**Điểm dễ hiểu sai:**
- `401 Unauthorized` thường nghĩa là cần/chưa có authentication hoặc credentials không hợp lệ.
- `403 Forbidden` có thể do **role thiếu** hoặc **CSRF token thiếu/sai**. Không thể chỉ nhìn status 403 để biết nguyên nhân.
- HTTP Basic với browser **không mặc nhiên miễn CSRF** vì browser có thể tự động gửi cached credentials theo cơ chế phù hợp; quyết định phải dựa trên threat model.
- **Stateless** không tự đồng nghĩa CSRF-safe nếu browser vẫn tự đính kèm credentials.
- Chỉ dùng JWT trong `Authorization: Bearer` do script/app tự gắn và không có ambient credentials tự gửi có thể có rủi ro CSRF khác với cookie sessions, nhưng cần phân tích thật chứ không tắt CSRF theo nhãn "REST API".
- CORS và CSRF là hai cơ chế khác nhau. Allow origins không thay thế CSRF defense.
- GET không nên thay đổi trạng thái có ảnh hưởng nghiệp vụ; nếu GET thực hiện transfer tiền/xóa dữ liệu, CSRF mặc định của safe methods không cứu được thiết kế sai.

Đối với form Thymeleaf/MVC, cần render token CSRF theo integration của Spring Security/template engine; đối với SPA, phải có contract truyền token phù hợp khi dùng cookie-based authentication. Không hardcode token vào HTML tĩnh hay repo.

### 11.1. Có nên gọi `csrf.disable()`?

Không nên coi đây là cách sửa nhanh mọi HTTP 403:

```java
// CHỈ là ví dụ về API, không phải lời khuyên production:
http.csrf(csrf -> csrf.disable());
```

Mảnh code chỉ thuộc Servlet `HttpSecurity`; với WebFlux là `ServerHttpSecurity` và API khác. Chỉ xem xét tắt/ignore CSRF trên **phạm vi đã chứng minh không bị tấn công qua browser's ambient credentials**, ví dụ một số machine-to-machine bearer token API thực sự stateless. Nếu cùng app vừa có browser session vừa có API token, nên phân tách chain/matchers và giữ CSRF cho phần browser.

Một số endpoint webhook dùng chữ ký HMAC riêng và không dùng session cookie có thể cần policy khác; chứng thực chữ ký request quan trọng hơn việc “tắt CSRF cho hoạt động”. Mọi exception phải được kiểm thử.

## 12. Session, cookies, authentication và logout

Khi bật form login, Spring Security có thể lưu `SecurityContext` trong HTTP session để nhận diện người dùng ở request tiếp theo; browser giữ cookie session ID như `JSESSIONID` (theo Servlet container/config). Flow đại thể:

```text
GET /account (anonymous)
     │
     └── Redirect tới login
             │
          POST credentials + CSRF token
             │
             ▼
       Authentication success
             │
          SecurityContext
             │
       HttpSession / cookie session id
             │
GET /account + cookie → Được xác thực bằng session
```

Phải phân biệt:
- **Authentication mechanism**: form login, HTTP Basic, JWT/Bearer/OAuth2.
- **Session policy**: dùng/tạo HTTP session khi cần, hạn chế session hoặc stateless.
- **Cookie flags**: `Secure`, `HttpOnly`, `SameSite` theo yêu cầu/deployment.
- **CSRF**: bảo vệ request thay đổi state khi credentials có thể được browser tự gửi.
- **Session fixation protection**: thay/rotate session ID theo policy lúc authentication.
- **Logout**: invalidate session, clear context và/hoặc revoke tokens theo cơ chế, không chỉ ẩn nút logout.

Không giả định HTTP Basic luôn dùng session hoặc luôn không dùng session trong mọi cấu hình; những thành phần Spring Security khác như request cache và security context persistence cũng ảnh hưởng. Nếu API thực sự stateless, hãy thiết kế `SessionCreationPolicy.STATELESS` và token authentication đúng cách (Servlet), test không tạo session ngoài ý muốn, nhưng đừng tắt CSRF tùy tiện nếu dùng cookie tự gửi.

**Cảnh báo:** endpoint public không đồng nghĩa bảo mật dữ liệu đã xong. `permitAll()` cho phép truy cập không cần authentication, vì vậy không trả data nhạy cảm tại URL đó; authorization theo object/tenant vẫn là trách nhiệm nghiệp vụ.

## 13. Security headers: cải thiện mặc định nhưng chưa phải mọi biện pháp

Spring Security có thể thêm nhiều HTTP response headers mặc định, ví dụ:
- `X-Content-Type-Options: nosniff` chống MIME sniffing trong nhiều browser.
- Các policy chống clickjacking (`X-Frame-Options` theo default thích hợp).
- Các cache-control headers ngăn cache nội dung nhạy cảm trong những trường hợp mặc định.
- `Strict-Transport-Security` (HSTS) thường chỉ được phát khi request được nhận diện là secure.
- Một số header khác tùy version/config.

**Đừng suy đoán mọi security header đều bật.** `Content-Security-Policy` (CSP), `Permissions-Policy`, chính sách frame từ third parties, TLS cipher suites, certificate rotation, rate limiting hay WAF thường cần cấu hình riêng.

Nếu TLS terminate tại proxy, ứng dụng cần nhận diện scheme công khai đúng qua **forwarded headers từ proxy đáng tin**, hoặc đặt security headers tại edge theo chính sách. Nếu bạn cho phép client tự giả `X-Forwarded-Proto`, logic xác định request secure có thể sai. Không dùng `Forwarded` chưa xác minh để quyết định tạo security-sensitive redirect hoặc cookie flags.

Có thể kiểm tra headers bằng `curl -i`, nhưng xác nhận HTTPS, HSTS và browser behavior cần test **qua hạ tầng thật** thay vì chỉ MockMvc.

## 14. CORS: starter-security không tự mở quyền cross-origin

Khi frontend ở `https://app.example.test` gọi backend `https://api.example.test`, browser áp dụng **CORS**. Thêm starter-security không tự “allow origin”, và các security filters có thể tác động tới **preflight OPTIONS**.

**CORS preflight** có thể không mang session cookies; nếu nó bị security yêu cầu authentication trước khi CORS được xử lý, browser báo CORS failure dù API có thể hoạt động khi gọi bằng curl. Cần đăng ký CORS tại lớp phù hợp và tích hợp Spring Security, ví dụ Servlet:

```java
// Mảnh cấu hình minh họa trong SecurityFilterChain:
http.cors(Customizer.withDefaults());
```

Để định nghĩa allowed origins/methods/headers theo business policy, có thể cung cấp bean `CorsConfigurationSource`:

```java
// Mảnh code trong một class @Configuration (cần imports tương ứng).
@Bean
CorsConfigurationSource corsConfigurationSource() {
    CorsConfiguration config = new CorsConfiguration();
    config.setAllowedOrigins(List.of("https://app.example.test"));
    config.setAllowedMethods(List.of("GET", "POST"));
    config.setAllowedHeaders(List.of("Content-Type", "X-CSRF-TOKEN"));
    config.setAllowCredentials(true);

    UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
    source.registerCorsConfiguration("/**", config);
    return source;
}
```

Đoạn này **không phải file Java standalone**; cần import `List`, `CorsConfiguration`, `CorsConfigurationSource` và `UrlBasedCorsConfigurationSource` của Spring Web. Nó là ví dụ ý tưởng; với production cần xét chính xác phương thức, headers, credentials, cache max-age và CSRF token delivery. Không dùng `allowedOrigins("*")` kết hợp credentials một cách bừa bãi. Không tự reflect `Origin` vào `Access-Control-Allow-Origin` mà không whitelist.

**CORS không thay thế authentication/authorization.** Bất kỳ client không phải browser nào cũng có thể gửi request HTTP dù không thuộc allowlist CORS; server vẫn phải xác thực/kiểm quyền bằng Spring Security.

## 15. Static resources, trang lỗi và Actuator

### 15.1. Static assets

Khi Boot phục vụ `/css/site.css`, `/js/app.js` từ `src/main/resources/static`, các URL vẫn có thể đi qua security chain. Nếu bạn cần phục vụ login page trước authentication, CSS/JS/logo tương ứng nên được **permitAll** có chủ đích.

Với Spring Boot MVC, ví dụ matcher phù hợp khi dependency Boot được bật:

```java
// Mảnh nằm trong authorizeHttpRequests(...):
.requestMatchers(
    PathRequest.toStaticResources().atCommonLocations()
).permitAll()
```

`PathRequest` này thuộc `org.springframework.boot.autoconfigure.security.servlet.PathRequest` ở Boot 3.3. Đừng “ignore toàn bộ security” với `web.ignoring()` chỉ để ảnh hiển thị nếu có thể `permitAll`: việc ignore có thể khiến những security filters/headers không áp dụng cho các response đó.

### 15.2. Trang lỗi và `/error`

Nếu một handler ném exception, error dispatch có thể đi qua security mechanisms. Boot 3.3 mô tả ứng dụng được bảo vệ theo mặc định, **bao gồm `/error`**. Khi tạo custom chain `anyRequest().denyAll()` hoặc nhiều chain, cần test:
- Endpoint không tồn tại (404) có hiển thị 404 đúng không?
- Endpoint lỗi (500) có vô tình trả 401/403 thay cho original error không?
- Error page có lộ stack trace/PII không?
- User chưa đăng nhập có bị redirect loop giữa lỗi và `/login` không?

Không cần công khai mọi lỗi chi tiết. Có thể cấu hình error dispatch policy với matcher phù hợp để giữ đúng status, nhưng không làm lộ nội dung debug cho user.

### 15.3. Actuator: vấn đề đặc biệt khi tạo custom chain

Nếu thêm `spring-boot-starter-actuator`, Boot có các endpoint quản trị như `/actuator/health`, `/actuator/metrics`, `/actuator/env`... Nhưng:
- Không phải endpoint nào cũng được **expose** qua HTTP. Theo Boot 3.3, mặc định thường chỉ health được expose.
- Khi Spring Security tồn tại và **không có custom SecurityFilterChain**, Boot auto-security thường cho phép health và bảo vệ các Actuator endpoints khác được expose.
- Khi bạn **tạo custom SecurityFilterChain**, Boot lùi khỏi auto-security; **bạn phải kiểm soát quyền Actuator** trong chain của mình (hoặc chain riêng).
- Exposure và authorization là **hai lớp khác nhau**: `management.endpoints.web.exposure.include=*` không tự làm những endpoints đó public an toàn.

Một hướng xây rule trong ứng dụng có Actuator là dùng `EndpointRequest` thay vì hardcode `/actuator/**`:

```java
// Minh họa trong authorizeHttpRequests(...) với actuator trên classpath:
.requestMatchers(EndpointRequest.to("health")).permitAll()
.requestMatchers(EndpointRequest.toAnyEndpoint()).hasRole("OPS")
.anyRequest().authenticated()
```

Ở MVC Boot 3.3, `EndpointRequest` từ `org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest`. Code trên là fragment, không đưa thẳng vào project ví dụ chưa có actuator và role OPS. Nếu management server tách port/context, thiết kế cần kiểm thử thêm các security chains tương ứng.

## 16. Method-level security không tự bật chỉ bằng starter

Authorization theo URL không phải lúc nào cũng đủ. Một service method có thể được gọi bởi nhiều controller, scheduler hoặc message consumer. Spring Security cung cấp method-level authorization, nhưng **phải bật đúng cấu hình**.

Với Spring MVC/Servlet:

```java
@Configuration
@EnableMethodSecurity
class MethodSecurityConfig {}
```

Sau đó:

```java
@Service
class ReportService {
    @PreAuthorize("hasRole('ADMIN')")
    String exportSensitiveReport() {
        return "report content";
    }
}
```

Các đoạn code trên là **mảnh class**, cần imports `@Configuration`, `@EnableMethodSecurity`, `@Service`, `@PreAuthorize` và package phù hợp. Khi cấu hình đúng và method được gọi qua Spring bean/proxy, authorization có thể kiểm tra trước khi thực thi. **Self-invocation** gọi method protected từ một method trong cùng object có thể bypass proxy-based interception; test kiến trúc invocation thực.

Với reactive method security, sử dụng `@EnableReactiveMethodSecurity` và contract reactive tương ứng; không copy vô điều kiện một service blocking vào Netty event loop. Cần lưu ý ReactiveSecurityContextHolder và sự truyền context qua reactive operators.

Chỉ có starter-security **không có nghĩa mọi method tự được bảo vệ** hoặc annotation `@PreAuthorize` tự hoạt động nếu thiếu enable/config phù hợp.

## 17. Nhiều SecurityFilterChain: tránh đường đi không có bảo vệ

Một ứng dụng hỗn hợp có thể cần:
- `/api/**` dùng Bearer token, stateless.
- `/web/**` dùng form login/session/CSRF.
- `/actuator/**` dành cho OPS role hoặc network nội bộ.

Trong MVC, có thể tạo nhiều bean `SecurityFilterChain` với `@Order` và `http.securityMatcher(...)`. **FilterChainProxy chỉ chọn chain đầu tiên khớp request**. `authorizeHttpRequests().requestMatchers(...)` **không chọn chain**, nó chọn access rule **bên trong chain đã được chọn**.

```text
GET /api/orders
    │
    ▼
SecurityFilterChain matching:
    1. /api/** ? YES → chain API
    2. /web/** ? không cần xét
    3. catch-all ? không cần xét
    │
    ▼
Authentication + authorization của chain API
```

**Rủi ro lớn:** nếu bạn chỉ tạo một chain với `securityMatcher("/api/**")` và không có catch-all, các URL ngoài `/api/**` có thể **không đi qua security chain**. Vì Spring Boot đã thấy bean SecurityFilterChain do bạn khai báo nên default chain của Boot không còn tự bảo vệ phần còn lại. Cần thiết kế chain fallback cho mọi URL nằm trong phạm vi app, và kiểm thử negative cases.

Tương tự ở WebFlux: `SecurityWebFilterChain` có `securityMatcher` và thứ tự chọn. Không đặt rule broad `permitAll` trước một rule restricted rồi nghĩ restricted rule sẽ được xem xét sau.

## 18. Authentication schemes và việc thêm starter khác

`spring-boot-starter-security` giải quyết nền tảng security, nhưng production có thể cần:

| Trường hợp | Thành phần thường dùng | Điều cần thiết kế |
|---|---|---|
| Website đăng nhập username/password truyền thống | Form login, user store/identity provider, session/CSRF | Password hashing, session fixation, logout, rate limiting |
| API machine-to-machine với JWT | OAuth2 Resource Server + JWT decoder/issuer validation | Signature, issuer, audience, expiry, authorities mapping |
| Social/enterprise login | OAuth2 Client / OpenID Connect | Authorization code flow, redirect URI, scopes, session/security context |
| SAML login | SAML2 service provider support | Metadata/cert rotation, assertions, recipient/audience |
| Backend-to-backend Basic | HTTP Basic với TLS và credential management | Secret rotation, credential caching, brute-force prevention |
| Reverse proxy auth | Trusted identity headers hoặc token forwarding | Proxy trust boundary, signed identity, không tin header client tự gửi |

Không bật `csrf.disable()` chỉ vì có OAuth2. Flow browser dùng cookies/session có threat model khác bearer-only API. Không xem `@PreAuthorize("hasRole('ADMIN')")` là thay thế object-level authorization (ví dụ một ADMIN của tenant A có được xem dữ liệu tenant B hay không).

Một `UserDetailsService` chỉ mô tả cách tìm user/authorities theo username trong một số authentication providers. Nó không tự thực hiện MFA, account lockout, identity proofing, email confirmation hay token issuance. Những requirement đó cần cơ chế riêng.

## 19. Troubleshooting sau khi thêm spring-boot-starter-security

| Triệu chứng | Nguyên nhân thường gặp | Hướng kiểm tra |
|---|---|---|
| Trước đây `/hello` trả 200, giờ nhận 401 | Starter kích hoạt default authentication requirement | Tạo SecurityFilterChain cho URL policy mong muốn; không xóa starter |
| Browser luôn redirect `/login` | Form login entry point chọn cho HTML client chưa xác thực | Kiểm tra `Accept`, session/authentication và đường login |
| curl chạy Basic nhưng POST bị 403 | CSRF token thiếu/sai hoặc role không đủ | Xem security logs; test `with(csrf())` và authority |
| Sau custom `SecurityFilterChain` vẫn có generated user | Default user config chưa bị thay bởi authentication bean | Khai báo UserDetailsService/provider hoặc auth manager thực |
| CSS/JS của login page không load | Static assets vẫn bị security chain yêu cầu login | Permit đúng static resource paths |
| `@PreAuthorize` không hoạt động | Chưa bật method security, hoặc self-invocation | `@EnableMethodSecurity`, kiểm tra bean/proxy |
| Spring Boot WebFlux app không nhận `SecurityFilterChain(HttpSecurity)` | Nhầm Servlet security với reactive security | Dùng `SecurityWebFilterChain(ServerHttpSecurity)` |
| CORS preflight OPTIONS lỗi | CORS xử lý không đúng trước authorization hoặc chưa whitelist origin | Bật CORS integration và policy origins/headers |
| Redirect sang login thay vì JSON 401 | Content negotiation/entry point thích hợp cho HTML | Test Accept header, custom AuthenticationEntryPoint nếu API-only |
| Login thành công rồi mất phiên | Cookie flags/path, session store hoặc proxy/TLS config | Theo dõi session ID, security context persistence và cookie policy |
| 404/500 bị biến thành 401/403 | Error dispatch cũng đi qua security | Test `/error`/dispatcher handling; cấu hình error policy có chủ đích |
| Actuator metrics bị public sau thêm custom chain | Boot auto-security back off, rule app quá rộng | Dùng EndpointRequest và test management access |
| Password từ log không hoạt động | App dùng custom UserDetailsService hoặc password đã đổi sau restart | Kiểm tra bean/auto-config và active profile |
| 403 dù đã có ROLE_EDITOR trong database | Authority mapping/hasRole vs hasAuthority không khớp | Xem `ROLE_` prefix, loaded authorities và chain được chọn |
| User “authenticated” nhưng vẫn đọc sai dữ liệu tenant | Chỉ có URL/role check, thiếu object-level authorization | Kiểm tra ownership/tenant ở service/repository |

**Debug có kiểm soát:** trong môi trường phát triển, có thể tăng logging của `org.springframework.security` để biết chain/matcher/denial, ví dụ `logging.level.org.springframework.security=DEBUG`. Không bật DEBUG/TRACE tràn lan ở production: thông tin URL/authentication events có thể nhạy cảm và log volume lớn. Tuyệt đối không log password, token, session ID thô hoặc security context có PII.

## 20. Checklist để đưa security starter vào một ứng dụng có sẵn

1. **Xác định stack:** MVC/Servlet hay WebFlux/Reactive; phân biệt `SecurityFilterChain` với `SecurityWebFilterChain`.
2. **Liệt kê endpoints:** public, authenticated, role restricted, admin, actuator, static, login, logout, error và management port.
3. **Thiết kế authentication:** real user store/identity provider, password encoder, MFA/credential rotation khi cần; bỏ generated password dev trước production.
4. **Định nghĩa authorization:** tối thiểu cần `anyRequest().authenticated()` hoặc deny-all strategy phù hợp; không quên default/catch-all khi nhiều chains.
5. **Giữ CSRF đúng threat model:** browser cookie/session cần protection; không tắt chỉ để POST trả 200.
6. **Xem lại CORS:** allowed origins/methods/credentials, preflight integration; CORS không thay auth.
7. **Xem lại session/cookies:** session fixation, secure/httpOnly/sameSite, logout/invalidate và proxy/TLS.
8. **Test 401, 403, 302, 200, 201:** guest, user, wrong role, CSRF thiếu/đúng, login/logout và static resources.
9. **Test Actuator và error:** tránh lộ endpoints quản trị hoặc biến mọi 404 thành login redirect ngoài ý muốn.
10. **Bật method security nếu cần:** kiểm tra `@PreAuthorize` thực sự được áp dụng và không có self-invocation bypass.
11. **Security headers/TLS:** kiểm tra HSTS/HTTPS ở thực tế, bổ sung CSP và cấu hình proxy trusted nếu cần.
12. **Quan sát và kiểm thử rollout:** đặt metrics audit, test sau deploy với gateway, kiểm tra không có đường bypass chain.
13. **Không lạm dụng permitAll/ignoring:** chỉ mở đúng tài nguyên công khai; không dùng `web.ignoring()` thay mọi rule.
14. **Cập nhật dependency:** theo dõi security advisories của Spring Boot/Spring Security, nâng bản vá định kỳ.

## 21. Câu hỏi tự kiểm tra

**Câu 1:** Thêm starter-security có tự làm `/public` public không?  
**Trả lời:** Không. Khi chưa custom config, các application endpoints thường yêu cầu authentication. Muốn mở phải permit chính xác.

**Câu 2:** Vì sao curl GET đã login được mà POST vẫn 403?  
**Trả lời:** CSRF protection kiểm tra unsafe HTTP methods; còn có thể do quyền. Phải phân biệt role denial với missing/invalid CSRF token.

**Câu 3:** Có `SecurityFilterChain` custom thì default user có còn không?  
**Trả lời:** Có thể còn. Default web chain và auto-config authentication user có điều kiện lùi riêng. Nếu muốn thay user, khai báo authentication bean phù hợp.

**Câu 4:** WebFlux dùng `SecurityFilterChain(HttpSecurity)` có đúng không?  
**Trả lời:** Không cho reactive server. WebFlux dùng `SecurityWebFilterChain(ServerHttpSecurity)` và `ReactiveUserDetailsService` nếu cần.

**Câu 5:** Không dùng cookie, chỉ Bearer token do client tự gắn, có thể tắt CSRF không?  
**Trả lời:** Có thể cân nhắc trong API thuần token không có ambient browser credentials, nhưng phải kiểm tra threat model, client types và mọi auth scheme đang bật; không tự động tắt theo tên API.

**Câu 6:** Nếu có hai chains và `securityMatcher("/api/**")` là chain duy nhất, `/admin/**` được bảo vệ không?  
**Trả lời:** Không thể giả định. Đường không match có thể không được Spring Security xử lý vì default Boot chain đã back off; cần catch-all chain.

**Câu 7:** Khi tạo custom chain, ai kiểm soát Actuator?  
**Trả lời:** Ứng dụng phải khai báo rõ chính sách Actuator/management endpoints vì Boot auto-security lùi khi có custom chain, và phải kiểm tra cả exposure.

## 22. Tài liệu tham khảo chính thức

1. Spring Boot 3.3.13 — **Spring Security**: default user/password, default web protection, MVC/WebFlux và cách override: https://docs.spring.io/spring-boot/3.3/reference/web/spring-security.html
2. Spring Boot 3.3.13 — **Actuator Endpoints**: exposure và security khi tạo custom SecurityFilterChain: https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html
3. Spring Security — **Architecture**: DelegatingFilterProxy, FilterChainProxy và SecurityFilterChain: https://docs.spring.io/spring-security/reference/servlet/architecture.html
4. Spring Security — **Authorize HttpServletRequests**: authorizeHttpRequests và requestMatchers: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
5. Spring Security — **CSRF**: khi nào cần token, cookie/browser threat model: https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html
6. Spring Security — **MockMvc with CSRF**: sử dụng `csrf()` trong test: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html
7. Spring Security — **WebFlux Security**: ServerHttpSecurity, WebFilter và SecurityWebFilterChain: https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html

**Tổng kết:** `spring-boot-starter-security` làm xuất hiện authentication/authorization và web security defaults **ngay khi được thêm vào classpath**. Hệ quả được nhìn thấy ở 401/302, role-based 403, CSRF 403, login/logout, session, headers, Actuator và tests. Để chuyển sang production, hãy **định nghĩa đúng các SecurityFilterChain/SecurityWebFilterChain**, cấp user/identity từ nguồn thích hợp, giữ CSRF theo threat model, không để URL nào nằm ngoài security policy, và kiểm thử đầy đủ trước/sau khi thêm starter.