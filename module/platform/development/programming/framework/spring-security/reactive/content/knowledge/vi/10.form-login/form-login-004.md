# Đọc dữ liệu biểu mẫu và xác thực người dùng trong WebFlux

## 1. Bài toán và mục tiêu

Khi người dùng mở trang đăng nhập, nhập **username/password** và nhấn “Đăng nhập”, trình duyệt thường gửi một HTTP POST có nội dung `application/x-www-form-urlencoded`. Trong Spring WebFlux, việc đọc dữ liệu form diễn ra **bất đồng bộ**; Spring Security reactive có sẵn một chuỗi xử lý đăng nhập để chuyển form thành yêu cầu xác thực, kiểm tra mật khẩu, đưa danh tính đã được xác thực vào `SecurityContext` và duy trì phiên đăng nhập khi cần.

Điểm cốt lõi là phân biệt hai công việc:

1. **Đọc dữ liệu biểu mẫu (form decoding):** chuyển body HTTP thành các cặp tên–giá trị, ví dụ `username=reader&password=...`.
2. **Xác thực (authentication):** dùng nguồn người dùng đáng tin cậy và bộ mã hóa mật khẩu để xác minh username/password, không tin rằng client tự gửi danh tính đúng.

**Không nên viết một controller `POST /login` tự đọc mật khẩu và tự tạo session nếu Spring Security `formLogin` đã đáp ứng nhu cầu.** Cơ chế có sẵn thực hiện nhiều bước dễ bỏ sót như xử lý lỗi, CSRF, context và cookie/session.

Sau bài học, bạn sẽ:
- Hiểu `ServerWebExchange.getFormData()`, `Mono<MultiValueMap<String,String>>` và sự khác biệt với JSON/multipart.
- Diễn giải pipeline đăng nhập reactive: `formLogin` → `AuthenticationWebFilter` → converter → `ReactiveAuthenticationManager` → `SecurityContext`.
- Cấu hình `ReactiveUserDetailsService`, `PasswordEncoder` và `SecurityWebFilterChain` cho login biểu mẫu.
- Phân biệt request chưa đăng nhập, password sai, thiếu CSRF token và user đã xác thực nhưng thiếu quyền.
- Chạy ví dụ Java 17+ với Spring Boot WebFlux, kiểm tra hành vi trình duyệt và `WebTestClient`.
- Biết khi nào cần form đăng nhập riêng và cách tránh lộ mật khẩu/session.

## 2. Luồng đăng nhập biểu mẫu hoạt động thế nào?

Giả sử ứng dụng có `/account` cần đăng nhập:

~~~text
Trình duyệt                 Spring Security WebFlux                  Nguồn user
     │                                │                                  │
     ├── GET /account ───────────────►│                                  │
     │              chưa xác thực     │                                  │
     ◄───────── 302 /login ───────────┤                                  │
     │                                │                                  │
     ├── GET /login ─────────────────►│                                  │
     ◄──── HTML form + CSRF token ────┤                                  │
     │                                │                                  │
     ├── POST /login ────────────────►│                                  │
     │   Content-Type: application/   │                                  │
     │     x-www-form-urlencoded      │                                  │
     │   username, password, _csrf    │                                  │
     │                                ├── kiểm tra CSRF                   │
     │                                ├── đọc formData theo reactive     │
     │                                ├── tạo Authentication chưa xác thực
     │                                ├── manager.authenticate(...) ────►│
     │                                │                 tra user/hash     │
     │                                ◄──── Authentication đã xác thực ──┤
     │                                ├── lưu context vào session phù hợp
     │                                └── success handler / redirect     │
     ◄──────── 302 + session cookie ──┤                                  │
     │                                │                                  │
     ├── GET /account + cookie ──────►│                                  │
     │                                ├── tải context đã lưu              │
     │                                └── kiểm tra authenticated()       │
     ◄──────── 200 Hello reader ──────┤                                  │
~~~

Một số chi tiết quan trọng:

- **`GET /login` không phải yêu cầu xác thực.** Nó trả trang HTML để người dùng điền form; Spring Security có thể tạo trang mặc định.
- **`POST /login` là lần thử xác thực mặc định**, khi `formLogin` được bật. Các trường mặc định là `username` và `password`.
- **CSRF được kiểm tra trước khi xử lý đăng nhập** với phương thức POST: thiếu/sai token có thể trả HTTP 403 dù username/password đúng.
- Manager dùng password encoder để so sánh **raw password** do client gửi với **password hash** đã lưu; không đem raw password so sánh trực tiếp với chuỗi hash.
- Xác thực thành công chưa chắc đồng nghĩa truy cập mọi URL; `authorizeExchange` còn kiểm tra role/authority.
- Với form login thông thường, context có thể được lưu vào **WebSession** để request tiếp theo giữ danh tính. Reactor Context chỉ là ngữ cảnh cho một subscription/request, không tự thay thế session.
- Kết quả redirect có thể đưa về trang trước đó hoặc URL mặc định tùy saved request/success handler; không hard-code mọi lần đăng nhập đều về `/`.

## 3. Đọc form trong WebFlux bằng `getFormData()`

### 3.1. Cú pháp và kiểu dữ liệu

`org.springframework.web.server.ServerWebExchange` cung cấp:

~~~java
Mono<MultiValueMap<String, String>> getFormData();
~~~

`MultiValueMap` khác `Map<String,String>` ở chỗ **mỗi key có thể có nhiều giá trị**. Ví dụ body:

~~~text
username=reader&password=reader-pass&remember=on&remember=yes
~~~

Sau khi parse:
- `getFirst("username")` trả `"reader"`.
- `getFirst("password")` trả `"reader-pass"`.
- `get("remember")` có thể trả danh sách `["on","yes"]`.

Dùng API:

~~~java
Mono<String> username = exchange.getFormData()
    .map(form -> form.getFirst("username"));
~~~

**Đây chỉ là đoạn minh họa**, giả định `exchange` là `ServerWebExchange` hợp lệ và import `reactor.core.publisher.Mono`. Đoạn này chưa hề xác minh mật khẩu; dữ liệu form vẫn là **không đáng tin**.

`getFormData()`:
- Xử lý body có `Content-Type: application/x-www-form-urlencoded`; với content type khác, thường trả map rỗng.
- Dùng `HttpMessageReader` của WebFlux để đọc và parse body.
- Trả `Mono`, nên bạn tiếp tục bằng `map` / `flatMap`; không `block()` trong event loop.
- Parse và cache form data theo contract của `ServerWebExchange`, nên việc gọi `getFormData()` nhiều lần trên cùng exchange được hỗ trợ. **Không vì thế mà chủ động đọc lại password ở nhiều lớp**: cần giới hạn nơi xử lý bí mật.
- Body form thường được đọc/parse toàn bộ; kích thước body và bộ nhớ cần được giới hạn bằng cấu hình codec/web server phù hợp.

### 3.2. Ví dụ endpoint đọc form không nhạy cảm

Để học cách đọc form mà không đụng tới đăng nhập, đây là **một đoạn handler minh họa**, không có mặt trong dự án runnable ở mục 8:

~~~java
@PostMapping(
    path = "/feedback",
    consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE
)
Mono<String> feedback(ServerWebExchange exchange) {
    return exchange.getFormData().map(form -> {
        String title = form.getFirst("title");
        if (title == null || title.isBlank()) {
            return "Missing title";
        }
        return "Received feedback title";
    });
}
~~~

Các import tương ứng gồm `org.springframework.http.MediaType`, `org.springframework.web.bind.annotation.PostMapping` và `org.springframework.web.server.ServerWebExchange`. Ví dụ chỉ nhận form title và không chứa password.

**Không** thay thế `title` bằng `password` rồi log, trả lại hoặc lưu raw password. Ở endpoint nghiệp vụ thông thường, phải kiểm tra input, CSRF, size limit và authorization riêng.

### 3.3. `@RequestParam`, `@RequestBody` và `multipart/form-data`

- `@RequestParam` trong WebFlux annotated controllers chủ yếu đọc query parameters; **không nên giả định nó tự xử lý form body giống Spring MVC Servlet**. Để lấy form URL encoded trong WebFlux, dùng `ServerWebExchange.getFormData()` hoặc `ServerRequest.formData()` (functional endpoint).
- `@RequestBody Mono<MyDto>` phù hợp cho JSON và media type được decoder hỗ trợ. Nó không phải cách tương đương trực tiếp với việc lấy field từ HTML form của `formLogin`.
- `multipart/form-data` dùng `getMultipartData()` hoặc APIs xử lý `Part`, **không** phải `getFormData()`. Không mặc định dùng multipart để nhận mật khẩu thông thường.
- Query string `?password=...` không an toàn: dễ đi vào URL log/history/referrer. Form login chuẩn dùng POST body, và tất cả traffic thật phải dùng HTTPS.

## 4. Cơ chế `formLogin` có sẵn: không cần tự viết controller POST /login

Với Spring Security WebFlux:

~~~java
@Bean
SecurityWebFilterChain security(ServerHttpSecurity http) {
    return http
        .authorizeExchange(exchanges -> exchanges
            .pathMatchers("/", "/about").permitAll()
            .anyExchange().authenticated()
        )
        .formLogin(Customizer.withDefaults())
        .build();
}
~~~

Đây là **đoạn cấu hình trích**, cần thêm imports/beans trong ứng dụng WebFlux. Lời gọi `formLogin(...)` bật chuỗi xử lý đăng nhập biểu mẫu. Khi dùng page mặc định:
- `GET /login`: Spring Security tạo trang login.
- `POST /login`: `AuthenticationWebFilter` của form login nhận thông tin đăng nhập.
- Các field cơ bản là `username` và `password`.
- Login thất bại vì credentials thường được redirect về `/login?error`.
- Login thành công thường redirect tới URL đã lưu hoặc mục tiêu mặc định.
- CSRF mặc định được bật; form generated page xử lý token.
- Form login thường sử dụng `WebSessionServerSecurityContextRepository` để lưu authentication giữa các request và cơ chế context-loading tương ứng.

Tách trách nhiệm rõ ràng:

| Thành phần | Chức năng |
| --- | --- |
| `ServerHttpSecurity.formLogin(...)` | Tạo/configure cơ chế đăng nhập biểu mẫu |
| `AuthenticationWebFilter` | Điều phối một lần thử xác thực khi request khớp matcher |
| `ServerFormLoginAuthenticationConverter` | Đọc username/password từ form và chuyển thành authentication **chưa xác thực** |
| `ReactiveAuthenticationManager` | Kiểm tra credentials và tạo authentication đã tin cậy |
| `ReactiveUserDetailsService` | Tìm account/UserDetails bằng username trong nguồn đáng tin cậy |
| `PasswordEncoder` | So sánh mật khẩu client với password hash đã lưu |
| `SecurityContext` | Chứa `Authentication` đã xác thực |
| `WebSessionServerSecurityContextRepository` | Lưu/tải context qua WebSession khi cấu hình form login session-based |
| `authorizeExchange(...)` | Kiểm tra quyền truy cập URI theo trạng thái và authorities |

**Chú ý phiên bản:** Tài liệu API Spring Security 6.x mô tả `ServerFormLoginAuthenticationConverter`. Đừng chép nhầm `UsernamePasswordAuthenticationFilter` (Servlet) hay `HttpSecurity` vào dự án WebFlux. WebFlux dùng `ServerHttpSecurity`, `SecurityWebFilterChain` và `WebFilter`.

### 4.1. Authentication chưa xác thực → đã xác thực

Khi form có `username` và `password`:
1. Converter phát `UsernamePasswordAuthenticationToken` **chưa xác thực**.
2. Manager tìm user, kiểm tra trạng thái account, gọi `PasswordEncoder.matches(raw, hash)` theo cơ chế tương ứng.
3. Đúng mật khẩu → tạo `Authentication` đã xác thực với authorities từ backend.
4. Sai mật khẩu/không có user → phát `AuthenticationException`; failure handler xử lý.
5. Sau thành công, `Authentication` vào `SecurityContext`, rồi Spring Security áp dụng authorization ở request hiện tại và sau này khi tải session phù hợp.

**Không tự gọi** `UsernamePasswordAuthenticationToken.authenticated(username, password, clientRoles)` từ dữ liệu form. Factory này dành cho kết quả **sau khi xác minh**; dùng trước khi kiểm tra là lỗi vượt qua xác thực.

### 4.2. Matcher đăng nhập khác rule phân quyền

- Matcher của form login xác định request **nào kích hoạt quá trình login**: mặc định POST `/login`.
- `authorizeExchange(...).pathMatchers("/account").authenticated()` xác định **URL nào yêu cầu user đã đăng nhập**.
- `permitAll` cho `GET /login` không xác minh user; nó chỉ cho phép truy cập trang login.

Một request tới `/account` cần authentication **không phải** request mà converter sẽ đọc username/password từ form. Spring Security xử lý hai request khác nhau: request ban đầu dẫn đến redirect, sau đó browser POST form login.

## 5. CSRF là một phần của form login, không phải lỗi phụ

Đăng nhập dựa trên cookie/session có nguy cơ **login CSRF** và các request thay đổi trạng thái ngoài ý muốn. Spring Security WebFlux bật CSRF protection mặc định và yêu cầu token hợp lệ cho các request POST (bao gồm POST login), PUT, PATCH, DELETE... trừ khi được cấu hình ngoại lệ có chủ đích.

Form HTML gửi POST phải chứa CSRF token phù hợp, thường là hidden input với tên `_csrf`. Trang login mặc định do Spring Security tạo thường đã chuẩn bị token. Với template tùy biến, phải render token từ cơ chế CSRF reactive tương ứng.

Tại WebFlux:
- `CsrfWebFilter` có vai trò kiểm tra token.
- `ServerCsrfTokenRepository` quản lý token theo cấu hình; mặc định thường dùng `WebSessionServerCsrfTokenRepository`.
- Spring Security 6.x có cơ chế request handler để tăng bảo vệ BREACH đối với token trong HTML; **không tự đoán giá trị token từ cookie rồi coi là hợp lệ với mọi cấu hình**.
- `Mono<CsrfToken>` có thể được framework đưa vào exchange attributes để template renderer truy cập theo hợp đồng. Sử dụng integration chính thức khi dùng template engine.
- `POST /login` mà thiếu hoặc sai token có thể trả 403 **trước cả bước so sánh password**.

### 5.1. Ba trạng thái cần phân biệt

| Request | Kết quả dự kiến trong demo |
| --- | --- |
| `GET /login` | 200, trang HTML form |
| `POST /login` có đúng username/password nhưng thiếu token CSRF | 403 Forbidden |
| `POST /login` có token CSRF hợp lệ, password sai | Redirect tới `/login?error` (thường 302) |
| `POST /login` có token CSRF hợp lệ, password đúng | Redirect thành công (thường 302) và thiết lập session |
| `GET /account` chưa có session authenticated | Redirect tới login |
| `GET /account` có session authenticated hợp lệ | 200 |

Nếu gặp HTTP 403 lúc login, **đừng vội kết luận password sai**. Xem Content-Type, CSRF token, cookie phiên, đường dẫn POST và thứ tự các security filters.

### 5.2. Form login và API JSON không có cùng hợp đồng

Một API JSON `POST /api/login` với body `{"username":"...", "password":"..."}` **không tự được** converter của form login mặc định hiểu. Tương tự, gửi JSON tới POST `/login` không tương đương gửi HTML form.

Nếu thiết kế sản phẩm thật sự cần JSON authentication:
- Xác định API spec rõ ràng, CSRF/session/token policy.
- Dùng một `ServerAuthenticationConverter` phù hợp và `ReactiveAuthenticationManager`, hoặc phương án xác thực chuẩn có sẵn.
- Kiểm tra validation, origin, brute-force mitigation, success/failure responses và không tự subscribe/block trong filter.
- Không disable CSRF “cho dễ test” nếu trình duyệt vẫn dùng cookie/session.

## 6. Session, Reactor Context và vòng đời đăng nhập

Có ít nhất ba đối tượng không được đánh đồng:

| Đối tượng | Phạm vi | Vai trò |
| --- | --- | --- |
| `SecurityContext` | Trong cơ chế Spring Security | Giữ `Authentication` hiện tại |
| **Reactor Context** | Theo subscription reactive | Truyền dữ liệu bảo mật trong pipeline không phụ thuộc một ThreadLocal cố định |
| **WebSession** | Có thể tồn tại giữa nhiều HTTP requests | Lưu trạng thái như security context với cookie/session id tùy repository |

Với form login mặc định, Spring Security thường cấu hình `WebSessionServerSecurityContextRepository` để **lưu security context sau đăng nhập** và tải lại trong request sau. Trình duyệt mang session cookie đến những request tiếp theo. Nếu client bỏ cookie, hoặc session hết hạn/bị xóa, request có thể được coi là chưa đăng nhập dù login trước đó từng trả 302.

Trong handler reactive:

~~~java
Mono<String> currentName() {
    return ReactiveSecurityContextHolder.getContext()
        .flatMap(context ->
            Mono.justOrEmpty(context.getAuthentication()))
        .map(Authentication::getName);
}
~~~

Đây là **đoạn method minh họa**: cần chạy bên trong class Java có imports tương ứng. `getContext()` trả publisher, không trả một `SecurityContext` đồng bộ.

**Không dùng** `SecurityContextHolder.getContext()` với giả định ThreadLocal của Servlet để đọc danh tính request trong tất cả nhánh WebFlux. Cũng không gọi `block()` hay `subscribe()` thủ công trong controller để lấy username; trả về `Mono` để Reactor/Spring quản lý subscription và context.

Session-based form login khác API stateless Bearer JWT: trong mô hình stateless, client thường gửi token ở từng request và server xác minh lại; với form login, browser có thể dùng cookie/session. Hai mô hình cần chính sách CSRF và logout khác nhau.

## 7. Xây ứng dụng chạy được bằng Java 17+ và Spring Boot WebFlux

Demo dùng **Spring Boot 3.3.13**, Java 17+, Gradle 8.x và Spring Security reactive. Phiên bản được cố định để minh họa API đồng nhất, không phải lời khuyên dùng phiên bản đã hết hỗ trợ cho ứng dụng production. Trong dự án mới, lựa chọn dòng Spring Boot đang được hỗ trợ và kiểm thử tương thích.

Chúng ta sẽ dùng **trang login mặc định** để tập trung vào việc đọc form/xác thực, thay vì tự viết giao diện và quên CSRF. Mọi endpoint do ứng dụng định nghĩa đều là GET.

### 7.1. Cấu trúc thư mục

~~~text
webflux-form-login-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/demo/
    │   ├── FormLoginApplication.java
    │   ├── SecurityConfig.java
    │   └── DemoController.java
    └── test/java/demo/
        └── FormLoginTests.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'webflux-form-login-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
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
~~~

Lưu ý dependencies:
- `spring-boot-starter-webflux`: server reactive, Reactor và WebFlux.
- `spring-boot-starter-security`: Spring Security, cấu hình WebFlux, form login.
- `spring-security-test`: hỗ trợ `WebTestClient` với mock CSRF/spring security trong integration tests; chỉ dùng trong test scope.
- Không thêm `spring-boot-starter-web` (Servlet/MVC) vì Boot có thể chọn stack Servlet khi cả hai starter cùng hiện diện.
- Không thêm Thymeleaf ở demo vì dùng login page generated bởi Spring Security.

### 7.2. Lớp khởi động

`src/main/java/demo/FormLoginApplication.java`:

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FormLoginApplication {

    public static void main(String[] args) {
        SpringApplication.run(FormLoginApplication.class, args);
    }
}
~~~

### 7.3. Bean người dùng, password encoder và security chain

`src/main/java/demo/SecurityConfig.java`:

~~~java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService userDetailsService(
            PasswordEncoder encoder) {

        UserDetails reader = User.withUsername("reader")
            .password(encoder.encode("reader-pass"))
            .roles("USER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("admin-pass"))
            .roles("ADMIN")
            .build();

        return new MapReactiveUserDetailsService(reader, admin);
    }

    @Bean
    SecurityWebFilterChain springSecurityFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchange -> exchange
                .pathMatchers("/", "/about").permitAll()
                .pathMatchers("/admin").hasRole("ADMIN")
                .anyExchange().authenticated()
            )
            .formLogin(Customizer.withDefaults())
            // Tắt HTTP Basic để tập trung quan sát hành vi form login.
            .httpBasic(spec -> spec.disable())
            .build();
    }
}
~~~

**Giải thích từng phần:**
1. `@EnableWebFluxSecurity` bật cấu hình bảo mật WebFlux. Trong ứng dụng Spring Boot có starter Security phù hợp, auto-configuration cũng thường đảm nhiệm việc này, nên annotation không phải điều kiện bắt buộc trong mọi dự án Boot.
2. `MapReactiveUserDetailsService` cung cấp `Mono<UserDetails>` qua triển khai reactive; ứng dụng thực tế có thể thay bằng user store reactive dựa trên R2DBC/identity provider.
3. `BCryptPasswordEncoder` hash password trong user store; khi đăng nhập, manager kiểm tra raw input với hash. Không dùng plaintext password cho production.
4. `.formLogin(Customizer.withDefaults())` bật login page generated và cơ chế xử lý `POST /login` với username/password.
5. `.httpBasic(...disable())` tắt HTTP Basic trong demo để các request browser tập trung vào cơ chế form login và redirect. Đây là lựa chọn của demo, không phải yêu cầu của `formLogin`.
6. `/` và `/about` public; `/admin` đòi authority `ROLE_ADMIN` thông qua `hasRole("ADMIN")`; các URL còn lại yêu cầu `authenticated()`.
7. Không tắt CSRF. POST `/login` vẫn yêu cầu token hợp lệ; trang login generated hỗ trợ điều này.
8. Không cần viết `@PostMapping("/login")` vì login filter của Spring Security xử lý request trước controller. Nếu controller tự xử lý song song, dễ gặp nhầm luồng authentication và tạo lỗ hổng.

Không hard-code user/password, lưu BCrypt hash trong memory hoặc database không có bảo vệ cho ứng dụng thật. Mục tiêu của bộ user trên là **demo kiểm thử local**.

### 7.4. Controller minh họa ngữ cảnh đã xác thực

`src/main/java/demo/DemoController.java`:

~~~java
package demo;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
class DemoController {

    @GetMapping("/")
    Mono<String> home() {
        return Mono.just("home");
    }

    @GetMapping("/about")
    Mono<String> about() {
        return Mono.just("about");
    }

    @GetMapping("/account")
    Mono<String> account() {
        return ReactiveSecurityContextHolder.getContext()
            .flatMap(context ->
                Mono.justOrEmpty(context.getAuthentication()))
            .map(Authentication::getName)
            .map(name -> "Hello " + name);
    }

    @GetMapping("/admin")
    Mono<String> adminOnly() {
        return Mono.just("admin-only");
    }
}
~~~

Handler `/account` không đọc password, không lấy username từ query parameter và không gọi `block()`. `ReactiveSecurityContextHolder` đọc authentication đã được Spring Security đưa vào Reactor Context; nếu chưa xác thực, rule `anyExchange().authenticated()` phải chặn request **trước khi handler trả kết quả**.

## 8. Chạy thật với trình duyệt

Từ thư mục `webflux-form-login-demo`, máy cần JDK 17+, Gradle tương thích và quyền tải dependencies lần đầu:

~~~bash
gradle bootRun
~~~

Nếu có Gradle Wrapper, dùng `./gradlew bootRun` (Unix/macOS) hoặc `gradlew.bat bootRun` (Windows). Server mặc định chạy tại `http://localhost:8080` nếu chưa cấu hình cổng khác.

Các bước quan sát:

1. Mở `http://localhost:8080/`: nhận body `home`, không cần login.
2. Mở `http://localhost:8080/account` khi trình duyệt chưa có session: thường được redirect tới `/login`.
3. Trang `/login` do Spring Security tạo: nhập username `reader` và password `reader-pass`. Không cần tự nhập CSRF token; trang generated sẽ chuẩn bị field phù hợp.
4. Trình duyệt gửi `POST /login` có `Content-Type: application/x-www-form-urlencoded`, username/password/CSRF. Security filter kiểm chứng rồi redirect.
5. Quay lại `/account` với session cookie: body `Hello reader`.
6. Mở `/admin` khi đang là reader: nhận **403 Forbidden** do không có `ROLE_ADMIN`.
7. Đăng xuất bằng cơ chế logout mặc định rồi đăng nhập user `admin` / `admin-pass`. `/admin` lúc này trả `admin-only`.

**Chú ý redirect sau login:** nếu người dùng đã xin truy cập `/account` trước khi login, success handler có thể điều hướng tới trang đó. Nếu vào thẳng `/login`, trang đích có thể khác. Đừng coi mỗi HTTP status 302 là bằng chứng user đã authenticated; cần kiểm tra session và truy cập endpoint protected ở request tiếp theo.

### 8.1. Tại sao test đơn giản bằng curl dễ bị 403?

Ví dụ:

~~~bash
curl -i -X POST http://localhost:8080/login \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data 'username=reader&password=reader-pass'
~~~

Ngay cả với mật khẩu đúng, request mẫu **không có token CSRF**, vì vậy có thể bị từ chối **403**. Đây là behavior bảo vệ có chủ đích, không phải lỗi `PasswordEncoder`.

Muốn dùng curl mô phỏng browser hoàn chỉnh cần:
- Lấy trang `GET /login` và session cookie ban đầu.
- Trích token CSRF **được render bởi trang** (không tự dự đoán), giữ cookie jar.
- Gửi form có `username`, `password`, `_csrf` phù hợp và cookie của cùng phiên.
- Theo redirect, dùng cookie sau login cho request protected.

Token có thể được mã hóa/đổi representation để chống BREACH; regex lấy token từ HTML dễ vỡ theo phiên bản/template. Vì vậy, **đối với bài học**, dùng browser hoặc `WebTestClient.mutateWith(csrf())` là cách đáng tin cậy hơn thay vì đưa một shell script phụ thuộc HTML cụ thể.

## 9. Kiểm thử tích hợp bằng `WebTestClient` và CSRF hỗ trợ bởi Spring Security Test

Spring Security có công cụ test reactive để tạo CSRF token giả **hợp lệ trong môi trường test**; không cần tắt CSRF để POST form login.

`src/test/java/demo/FormLoginTests.java`:

~~~java
package demo;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.reactive.function.BodyInserters;

import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
class FormLoginTests {

    @Autowired
    ApplicationContext applicationContext;

    private WebTestClient client;

    @BeforeEach
    void setup() {
        client = WebTestClient.bindToApplicationContext(applicationContext)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    @Test
    void publicHomeCanBeVisitedWithoutAuthentication() {
        client.get().uri("/")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("home");
    }

    @Test
    void defaultLoginPageExists() {
        client.get().uri("/login")
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
            .contentTypeCompatibleWith(MediaType.TEXT_HTML);
    }

    @Test
    void protectedBrowserPageRedirectsToLogin() {
        client.get().uri("/account")
            .header(HttpHeaders.ACCEPT, MediaType.TEXT_HTML_VALUE)
            .exchange()
            .expectStatus().is3xxRedirection()
            .expectHeader().valueMatches("Location", ".*/login.*");
    }

    @Test
    void postLoginWithoutCsrfIsRejected() {
        client.post().uri("/login")
            .contentType(MediaType.APPLICATION_FORM_URLENCODED)
            .body(BodyInserters.fromFormData("username", "reader")
                .with("password", "reader-pass"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void invalidPasswordWithCsrfRedirectsToErrorPage() {
        client.mutateWith(csrf())
            .post().uri("/login")
            .contentType(MediaType.APPLICATION_FORM_URLENCODED)
            .body(BodyInserters.fromFormData("username", "reader")
                .with("password", "wrong"))
            .exchange()
            .expectStatus().is3xxRedirection()
            .expectHeader().valueMatches(
                "Location", ".*login\\?error.*");
    }

    @Test
    void correctPasswordWithCsrfStartsAuthenticatedSession() {
        client.mutateWith(csrf())
            .post().uri("/login")
            .contentType(MediaType.APPLICATION_FORM_URLENCODED)
            .body(BodyInserters.fromFormData("username", "reader")
                .with("password", "reader-pass"))
            .exchange()
            .expectStatus().is3xxRedirection()
            .expectHeader().exists(HttpHeaders.LOCATION);
    }
}
~~~

Giải thích:
- `WebTestClient.bindToApplicationContext(...)` tạo client cho ứng dụng WebFlux trong test; `apply(springSecurity())` gắn các Spring Security WebFilters vào môi trường test.
- `mutateWith(csrf())` cung cấp CSRF token hợp lệ trong môi trường mock; **không** là lệnh tắt bảo vệ CSRF.
- `BodyInserters.fromFormData(...).with(...)` gửi dữ liệu dưới dạng form URL encoded đúng với login converter.
- Test no-CSRF kỳ vọng 403.
- Test sai password nhưng có CSRF kỳ vọng redirect error.
- Test đúng password với CSRF kỳ vọng redirect success; muốn chứng minh persistence xuyên request cần test tiếp theo với cookie session thực tế (bên dưới).
- Test không dùng mock user để xác thực chính thao tác login; nó đi qua password manager thật của demo.

**Lưu ý mức độ kiểm thử:** Các test trên khẳng định status và redirect, không chứng minh nguyên văn mọi response header ngoài `Location` hoặc cookie theo mọi server/session implementation. Tên và thuộc tính session cookie có thể bị cấu hình thay đổi trong hệ thống thật.

### 9.1. Kiểm tra session của login thực tế sau redirect

Để kiểm chứng danh tính còn tồn tại ở request sau, bạn có thể dùng **kiểm thử tích hợp HTTP thật** với `@SpringBootTest(webEnvironment = RANDOM_PORT)`, một client giữ cookie jar, và cách nhận/gửi CSRF token từ trang login. Khi login thành công, request sau tới `/account` mang cookie của cùng phiên phải trả `Hello reader`.

Hoặc với test dùng mock `WebTestClient` trên ApplicationContext, có thể thu thập response cookies sau POST login rồi đưa vào request `GET /account`, nếu cấu hình WebSession tương ứng. Trong demo WebFlux mặc định, cookie session thường tên `SESSION`; **không lấy cookie đó làm chân lý chung** nếu ứng dụng đã tùy biến resolver, path, domain hoặc SameSite. Một test persistence đầy đủ nên kiểm tra hai trường hợp: có cookie hợp lệ được 200; bỏ cookie quay lại 302 login.

### 9.2. Bảng test thêm cần có với hệ thống thật

| Tình huống | Kỳ vọng |
| --- | --- |
| GET `/login` | 200 HTML chứa form có trường username/password và token |
| POST login đúng password, có CSRF | Redirect success + security context được lưu phù hợp |
| POST login sai password, có CSRF | Redirect error, không có session authenticated |
| POST login thiếu/sai CSRF | 403, không xác thực |
| GET `/account` chưa login | Redirect login |
| GET `/account` sau login, cùng cookie | 200 và danh tính đúng |
| GET `/admin` với ROLE_USER | 403 |
| GET `/admin` với ROLE_ADMIN | 200 |
| Logout POST có CSRF hợp lệ | Session/logout state được xử lý |
| Logout GET khi chưa chủ đích cấu hình lại | Không tự coi là yêu cầu logout thành công |
| Request từ origin khác, redirect URL lạ | Không tạo open redirect, tuân thủ cookie/security headers |

## 10. Nếu muốn tự thiết kế trang login

Cấu hình minh họa:

~~~java
.formLogin(form -> form.loginPage("/signin"))
~~~

**Đây là đoạn cấu hình bổ sung, không phải chương trình Java độc lập.** Trong Spring Security WebFlux, khi chỉ định `loginPage("/signin")`:
- Framework không tự render trang login mặc định theo cách cũ.
- Ứng dụng phải cung cấp trang **GET `/signin`**.
- Form HTML cần gửi **POST `/signin`** khi dùng login page này, theo hợp đồng mặc định liên quan đến `loginPage`.
- Form phải có tên trường đúng `username`, `password` và CSRF token đã render.
- Ứng dụng nên tự render trang lỗi đăng nhập, ví dụ `/signin?error`.
- Cần chắc chắn `GET /signin` được phép truy cập **khi anonymous**, tránh vòng lặp redirect.
- Không dựng HTML bằng nối chuỗi từ input người dùng; dùng view/template engine được hỗ trợ và output escaping.

Trong ứng dụng dùng Thymeleaf reactive, tích hợp CSRF qua Spring Security và template engine có thể tự thêm input token vào form POST, nếu cấu hình model/request attributes và processor đúng cách. Với form HTML viết tay, phải cung cấp token từ `Mono<CsrfToken>` do Spring Security expose theo hợp đồng phiên bản đã dùng; không hard-code token vào source hoặc dùng một token chung cho mọi người.

### 10.1. Tự đọc form rồi gọi manager: minh họa API, không thay thế flow mặc định

Nếu thực sự xây authentication flow tùy biến, logic converter có thể trông như sau:

~~~java
ServerAuthenticationConverter converter = exchange ->
    exchange.getFormData()
        .map(form -> {
            String username = form.getFirst("username");
            String password = form.getFirst("password");
            return UsernamePasswordAuthenticationToken.unauthenticated(
                username == null ? "" : username,
                password == null ? "" : password
            );
        });
~~~

Đoạn trên **không phải ứng dụng độc lập**, cần import:
- `org.springframework.security.web.server.authentication.ServerAuthenticationConverter`
- `org.springframework.security.authentication.UsernamePasswordAuthenticationToken`
- `org.springframework.web.server.ServerWebExchange` (kiểu của tham số lambda được suy luận)
- `reactor.core.publisher.Mono` qua API.

Converter chỉ tạo token **chưa xác thực**. Manager, matcher, success/failure handler và SecurityContext persistence vẫn cần cấu hình. Đoạn code không kiểm soát toàn bộ validation, Content-Type, giới hạn body, CSRF, session fixation, rate-limit; đó là lý do **ưu tiên `formLogin` có sẵn** khi không có yêu cầu đặc biệt.

Nếu muốn đổi tên field, URL login hoặc failure handling, hãy xem API `ServerHttpSecurity.FormLoginSpec` và converter thay vì đặt một `@PostMapping("/login")` mới trong controller. Khi thay đổi cơ chế, kiểm thử lại POST form hợp lệ, malformed và an toàn CSRF.

## 11. Lỗi phổ biến và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra / sửa |
| --- | --- | --- |
| GET `/account` trả 302 dù endpoint đã viết controller | Chưa có authentication hợp lệ, đang áp dụng `authenticated()` | Dùng browser login, giữ session cookie; không bỏ rule |
| POST `/login` đúng password nhưng 403 | Thiếu/sai CSRF token, không cùng session, token mất hiệu lực | Xem CSRF và cookie, không tắt CSRF để né lỗi |
| POST `/login` trả `/login?error` | Credentials sai, user bị khóa/hết hạn hoặc encoder không khớp | Kiểm tra user store, `PasswordEncoder`, log đã lọc |
| Login 302 thành công nhưng `/account` vẫn bị redirect | Không mang cookie session/khác domain/khác path hoặc repository chưa tương thích | Kiểm tra response `Set-Cookie`, request Cookie, TTL, context repository |
| Form gửi JSON thay vì URL encoded | Converter mặc định không đọc JSON làm username/password | Gửi `application/x-www-form-urlencoded` hoặc thiết kế API khác |
| Form dùng `user`/`pass` thay vì `username`/`password` | Tên field không đúng cấu hình converter | Đồng bộ tên field hoặc customize converter có test |
| Đọc form bằng `@RequestParam` như MVC và thấy null | Khác biệt resolver/stack WebFlux | Dùng `exchange.getFormData()` cho body |
| Dùng `getFormData()` cho multipart upload | Media type và decoder khác | Dùng `getMultipartData()` / `Part` |
| So sánh password plaintext với BCrypt hash bằng `equals` | Luôn sai hoặc tạo giải pháp insecure | Dùng `PasswordEncoder.matches` |
| Dùng controller POST `/login` cùng với `formLogin` | Filter có thể xử lý trước, controller không chạy như tưởng | Để Spring Security quản lý login POST |
| Gọi `block()` trong converter/manager WebFlux | Chặn event loop, gây lỗi hoặc giảm throughput | Dùng các publisher/reactive repository đúng contract |
| Dùng `HttpSecurity` và `UsernamePasswordAuthenticationFilter` của Servlet | Sai web stack | Dùng `ServerHttpSecurity`, `SecurityWebFilterChain`, `AuthenticationWebFilter` |
| Trang custom login bị redirect vòng tròn | GET login cũng bị chặn bởi authorization | Permit trang login + tài nguyên CSS/JS cần thiết |
| User đã login nhưng /admin 403 | Không có `ROLE_ADMIN` | Kiểm tra authorities, không cấp quyền từ form input |
| Đổi form login thành stateless không lưu session | Login POST có thể thành công nhưng request sau không có context | Thiết kế lại persistence/token flow; không giả định session tự lưu |
| Log cả form body, Authorization hoặc password | Rò rỉ bí mật | Không log credentials; log trace ID và loại kết quả ở mức tối thiểu |

### 11.1. Phân biệt HTTP 302, 401, 403

- **302 Redirect**: thường gặp với form login: chưa đăng nhập được đưa về login, hoặc login success/failure đưa đến trang đích.
- **401 Unauthorized**: thường xuất hiện với cơ chế API (HTTP Basic/Bearer) hoặc entry point tùy biến; form login browser mặc định có thể trả 302 thay vì 401.
- **403 Forbidden**: authentication hợp lệ nhưng thiếu quyền, **hoặc** bị CSRF filter từ chối request thay đổi trạng thái.

Không kiểm tra HTTP status một mình rồi đoán ra nguyên nhân; kiểm tra location, cookies, loại client (browser/API), form body, CSRF và authorization rules.

### 11.2. Dữ liệu form là không đáng tin và cần kiểm soát

- Áp đặt giới hạn kích thước request body/form, số trường và thời gian xử lý.
- Không log raw password hoặc body của POST login, kể cả khi debug.
- Dùng TLS/HTTPS và cookie flags thích hợp (`Secure`, `HttpOnly`, `SameSite` phù hợp với flow).
- Giới hạn brute-force/credential-stuffing bằng rate limit, giám sát, lockout/challenge phù hợp; không tiết lộ “username không tồn tại” hay “password sai” cho attacker.
- Không gửi password ở query string, URL path hay analytics event.
- Không lưu plaintext password; hash bằng thuật toán thích hợp (BCrypt/Argon2 hoặc encoder đã được đánh giá), có chính sách nâng cấp hash.
- Kiểm soát session fixation, session expiry, logout, concurrency và revocation theo mức rủi ro.
- Bảo vệ trang login custom trước XSS, open redirect, CSP và dữ liệu chèn từ client.
- Có kiểm thử phân quyền sau login, bao gồm ranh giới tenant/ownership; login thành công không cấp tất cả quyền.

## 12. Tự kiểm tra kiến thức

1. **`ServerWebExchange.getFormData()` trả kiểu gì?** `Mono<MultiValueMap<String,String>>`; form body được đọc/parse không chặn theo API reactive.
2. **Form login default gửi tới đường dẫn nào, method nào?** `POST /login`, với `username` và `password` theo mặc định.
3. **Tại sao không xử lý password trong `@PostMapping("/login")` nếu đã dùng `formLogin`?** Spring Security đã đặt filter vào pipeline để kiểm tra CSRF, chuyển dữ liệu, xác thực và quản lý context.
4. **Converter có quyền tạo authentication đã authenticated trước khi kiểm password không?** Không. Nó tạo yêu cầu chưa xác thực; manager mới xác minh.
5. **Manager lấy user/hash ở đâu?** Từ nguồn người dùng tin cậy qua `ReactiveUserDetailsService` hoặc cơ chế authentication tương ứng; kiểm bằng `PasswordEncoder`.
6. **Đúng password nhưng thiếu CSRF token, có được login không?** Thông thường không; POST bị CSRF filter từ chối 403.
7. **Sai password với CSRF hợp lệ sẽ như thế nào?** Thường redirect về `/login?error` theo form login mặc định.
8. **Tại sao GET /account vẫn cần cookie sau lần POST login thành công?** Session/context được liên kết qua cookie/session id; Reactor Context không thay session qua nhiều request.
9. **`@RequestParam` trong WebFlux có luôn lấy trường từ form body như Spring MVC không?** Không nên giả định; để đọc body dùng `getFormData()`/`ServerRequest.formData()`.
10. **Dùng `getMultipartData()` khi nào?** Khi request là `multipart/form-data` (ví dụ file upload), không phải `application/x-www-form-urlencoded` thông thường.
11. **`hasRole("ADMIN")` mặc định so với authority nào?** `ROLE_ADMIN`.
12. **`WebTestClient.mutateWith(csrf())` có tắt CSRF ở production không?** Không. Nó là hỗ trợ test giả lập token hợp lệ trong mock environment.
13. **Khi cấu hình `form.loginPage("/signin")` cần chuẩn bị gì?** Tự render GET /signin và trang lỗi, POST /signin với fields + CSRF, cho anonymous truy cập page.
14. **Tại sao login form không hợp với API JSON thuần túy?** Converter mặc định của form login mong dữ liệu biểu mẫu, không đọc JSON theo hợp đồng form.
15. **Có cần thay `SecurityWebFilterChain` để lấy username trong handler reactive không?** Không. Sau authorization dùng `ReactiveSecurityContextHolder.getContext()` để lấy authentication trong pipeline.
16. **HTTP 403 ở /admin có luôn do CSRF không?** Không; GET không cần CSRF theo chính sách mặc định, 403 có thể do user thiếu role ADMIN.

## 13. Checklist triển khai

- [ ] Web stack thực sự là WebFlux, không vô tình chạy Servlet MVC.
- [ ] Form `POST /login` dùng tên field phù hợp và đúng media type.
- [ ] `ReactiveUserDetailsService` trả user và password hash từ nguồn tin cậy.
- [ ] `PasswordEncoder` được cấu hình nhất quán với hash lưu trữ.
- [ ] CSRF được giữ cho session-based form login và token được render đúng.
- [ ] Success/failure redirect được kiểm thử; login page/asset được phép anonymous.
- [ ] Context persistence, session cookie và logout hoạt động đúng.
- [ ] Không lưu/log password, không chuyển raw credentials vào response.
- [ ] Handler WebFlux đọc Reactor security context không blocking.
- [ ] Authorization sau login dùng role/permission và object ownership phù hợp.
- [ ] Có test success, wrong password, missing CSRF, session reuse, 403 thiếu quyền.
- [ ] Dùng HTTPS, cookie flags, rate limit và giảm rủi ro credential stuffing.

## 14. Tài liệu chính thức

- Spring Security — WebFlux Security Configuration: https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html
- Spring Security API — `ServerHttpSecurity.FormLoginSpec` (loginPage, matcher, repository, failure): https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.FormLoginSpec.html
- Spring Security API — `ServerFormLoginAuthenticationConverter`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/authentication/ServerFormLoginAuthenticationConverter.html
- Spring Framework — `ServerWebExchange.getFormData()`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/server/ServerWebExchange.html
- Spring Framework — WebFlux form-data parsing: https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html
- Spring Security — CSRF for WebFlux: https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html
- Spring Security — Testing with CSRF/WebTestClient: https://docs.spring.io/spring-security/reference/reactive/test/web/csrf.html

**Ghi nhớ:** `getFormData()` đọc dữ liệu từ HTTP body; nó **không xác thực người dùng**. `formLogin` tích hợp converter, reactive authentication manager, password encoder, xử lý CSRF và session/context để xây một phiên đăng nhập có kiểm soát. Trong WebFlux, hãy giữ các bước này trên pipeline `Mono`/`Flux` và kiểm thử cả trường hợp thành công, sai mật khẩu, thiếu CSRF và request sau login.
