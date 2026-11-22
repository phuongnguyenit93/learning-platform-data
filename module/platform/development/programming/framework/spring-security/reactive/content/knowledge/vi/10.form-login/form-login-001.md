# Luồng truy cập tài nguyên được bảo vệ, chuyển hướng và đăng nhập

## Mục tiêu của bài học

Trong ứng dụng **Spring Security Reactive (Spring WebFlux)** dùng **form login**, một người dùng chưa đăng nhập thường không nhận nội dung của trang được bảo vệ ngay. Thay vào đó, Spring Security khởi động một **quy trình đăng nhập qua trình duyệt**: chuyển hướng đến trang login, xác thực dữ liệu biểu mẫu, lưu trạng thái xác thực phù hợp với WebFlux, rồi đưa người dùng trở lại tài nguyên đã yêu cầu nếu request được ghi nhớ.

Sau bài này, bạn có thể:

1. Mô tả chính xác chuỗi request/response từ `GET /private` chưa xác thực tới `GET /login`, `POST /login`, rồi trở về `/private`.
2. Phân biệt **authentication** (người dùng là ai) với **authorization** (người đó được phép truy cập gì).
3. Phân biệt **redirect 302**, **401 cần xác thực**, **403 không đủ quyền** và **CSRF 403**.
4. Hiểu vai trò của `SecurityWebFilterChain`, `AuthenticationWebFilter`, `ReactiveAuthenticationManager`, `ReactiveUserDetailsService`, `ExceptionTranslationWebFilter`, authentication entry point, success/failure handlers và request cache.
5. Giải thích vì sao **session cookie, CSRF token và saved request** cần được giữ nhất quán giữa các request trình duyệt.
6. Viết một ứng dụng WebFlux Java 17+ với form login mặc định, hai user có role khác nhau, endpoint công khai và endpoint được bảo vệ.
7. Kiểm tra đường đi bằng trình duyệt và `WebTestClient`; tránh những lỗi như redirect loop, mất session, POST login thiếu CSRF hoặc mở sai endpoint.

Bài học thuộc phần **Đăng nhập biểu mẫu**. Các ví dụ hướng tới Spring Boot 3.x, Spring Security 6.x, Reactor và Java 17 trở lên. API/hành vi tùy phiên bản cần được đối chiếu với Spring Security đang sử dụng. Ví dụ dùng username/password lưu trong bộ nhớ **chỉ để học**, không dùng credential mẫu hoặc cơ chế lưu đó cho production.

## 1. Bài toán: người chưa đăng nhập mở trang được bảo vệ

Giả sử website có bốn đường dẫn:

| Endpoint | Chính sách | Kết quả mong muốn |
|---|---|---|
| `GET /` | Công khai | Trang chủ `home` |
| `GET /public` | Công khai | Nội dung `public` |
| `GET /private` | Phải xác thực | Chỉ người đã đăng nhập xem được nội dung cá nhân |
| `GET /admin` | Phải có role `ADMIN` | Chỉ admin xem được |
| `GET /login` | Công khai, do Spring Security tạo trong demo | Trang HTML có form username/password |
| `POST /login` | Endpoint xử lý xác thực biểu mẫu, không phải controller nghiệp vụ | Xác minh credential, tạo trạng thái login, redirect |
| Các URL khác | Từ chối theo policy demo | Không tự động public |

Với khách chưa đăng nhập, request `GET /private` **không được cho qua controller**. Tùy cấu hình cơ chế xác thực, Spring Security có thể trả `401`, `302` hoặc xử lý khác. Riêng trong **form login qua browser** của demo này, kết quả thông thường là **302 Found**, header `Location: /login`.

Trình duyệt hiểu `302` là chỉ dẫn gửi **request mới** tới URL trong `Location`. Đó không phải Server “thay request ban đầu thành login” trong cùng một HTTP request. Hai request có URL khác nhau và một chuỗi cookie/session tiếp nối.

## 2. Toàn bộ hành trình: request được bảo vệ → login → trở lại tài nguyên

### 2.1. Sơ đồ theo thời gian

```text
Browser               Spring Security WebFlux             Controller / App
  |                             |                                  |
  |--- GET /private ----------->|                                  |
  |                             | chưa xác thực                    |
  |                             | ghi nhớ request (nếu cache bật)  |
  |<-- 302 Location: /login ----|                                  |
  |     (có thể Set-Cookie)     |                                  |
  |                             |                                  |
  |--- GET /login ------------->|                                  |
  |     Cookie: SESSION=...     |                                  |
  |<-- 200 HTML login form -----|                                  |
  |     (form có CSRF token)    |                                  |
  |                             |                                  |
  |--- POST /login ------------>|                                  |
  |     username/password       |                                  |
  |     CSRF token              |                                  |
  |     Cookie: SESSION=...     |                                  |
  |                             | kiểm tra CSRF                    |
  |                             | xác thực credential             |
  |                             | lưu Authentication phù hợp      |
  |                             | tìm saved request               |
  |<-- 302 Location: /private --|                                  |
  |     (session có thể đổi ID) |                                  |
  |                             |                                  |
  |--- GET /private ----------->|                                  |
  |     Cookie phiên hiện tại   |                                  |
  |                             | tìm SecurityContext             |
  |                             | cho qua authorization           |
  |                             |--------------------------------->|
  |                             |                          xử lý /private
  |<----------------------------+-------- 200 hello viewer --------|
```

Đây là **happy path** khi request được lưu trong session, user nhập đúng mật khẩu, CSRF token hợp lệ, session/cookie được trình duyệt gửi lại và success handler sử dụng request cache mặc định. Không cam kết tất cả header hay giá trị cookie tuyệt đối giống nhau ở mọi phiên bản. Nếu không có saved request, success handler mặc định thường chuyển về `/` thay vì `/private`.

### 2.2. Bước 1: GET tài nguyên nhưng chưa đăng nhập

`GET /private` đi vào các `WebFilter` của WebFlux rồi qua Spring Security `WebFilterChainProxy` và `SecurityWebFilterChain`. Rule:

```java
.pathMatchers(HttpMethod.GET, "/private").authenticated()
```

yêu cầu `Authentication` đã được xác thực. Nếu chưa có, authorization không thể cho request tiếp tục tới controller.

Trong cấu hình form login, cơ chế **authentication entry point** sẽ khởi động tương tác đăng nhập. Một implementation quen thuộc của WebFlux là `RedirectServerAuthenticationEntryPoint`: thay vì viết HTML ngay tại `/private`, nó trả redirect tới `/login`.

Trong một số luồng, `ServerRequestCache` lưu URI/request ban đầu để success handler có thể quay lại sau khi login. Spring Security WebFlux cung cấp `WebSessionServerRequestCache`, `NoOpServerRequestCache` và các lựa chọn khác. Với form login/session mặc định, request cache kiểu WebSession thường được sử dụng. **Saved request không phải một bản sao tùy ý của toàn bộ body**; không giả định upload POST có thể replay an toàn sau login. Đặc biệt cần cẩn trọng với hành động thay đổi dữ liệu, request lớn và tham số nhạy cảm.

### 2.3. Bước 2: browser nhận redirect

Kết quả HTTP tiêu biểu:

```http
HTTP/1.1 302 Found
Location: /login
Set-Cookie: SESSION=...; Path=/; HttpOnly; ...
```

Đây là **ví dụ hình dạng response**, không phải header nguyên văn mà mọi server đều gửi. Cookie có thể đã tồn tại từ trước, được đặt ở request khác, hoặc thuộc cấu hình session khác; đừng hardcode session ID và đừng coi tên/cờ cookie luôn cố định mà không kiểm tra môi trường.

Khi nhận `Location: /login`, browser mở request GET khác. Nếu có cookie phù hợp domain/path/SameSite/Secure, browser gửi cookie tương ứng. Dùng client không giữ cookie (ví dụ gọi từng lệnh `curl` riêng mà không có cookie jar) rất dễ khiến request cache và trạng thái đăng nhập bị mất.

### 2.4. Bước 3: GET login page

Với `formLogin(Customizer.withDefaults())`, Spring Security WebFlux có thể cung cấp **trang đăng nhập mặc định**: form HTML có trường `username`, `password` và CSRF token cho POST.

Ví dụ cấu trúc biểu mẫu mô tả:

```html
<form method="post" action="/login">
  <input type="text" name="username" autocomplete="username">
  <input type="password" name="password" autocomplete="current-password">
  <!-- Spring Security / view engine bổ sung CSRF token hợp lệ -->
  <button type="submit">Sign in</button>
</form>
```

Đây là đoạn **minh họa cấu trúc**, chưa bao gồm CSRF field thực; **không copy nguyên form rút gọn này để triển khai production**. Khi dùng generated login page của Spring Security, trang cung cấp token theo tích hợp framework. Nếu tự viết login page, cần render token thật của đúng session; không lấy token giả/giá trị tĩnh từ ví dụ.

### 2.5. Bước 4: browser gửi POST /login

Biểu mẫu thường gửi content type `application/x-www-form-urlencoded` với các trường:

```text
username=viewer
password=viewer-pass
_csrf=<giá trị token CSRF do server phát cho phiên>
```

Chuỗi `<giá trị token CSRF do server phát cho phiên>` trong minh họa **không phải giá trị dùng được**. Browser tự tạo request từ form; mật khẩu phải truyền qua **HTTPS** trong ứng dụng thật.

Trong Spring Security WebFlux, login filter (thường thuộc cơ chế `AuthenticationWebFilter` cho form login) lấy credential từ request và gọi `ReactiveAuthenticationManager`. Manager kiểm tra user qua `ReactiveUserDetailsService` hay một identity provider khác, đồng thời xác minh password với `PasswordEncoder` đúng định dạng hash.

**Điểm quan trọng:** `POST /login` được security filter xử lý. Bạn **không cần** viết controller `@PostMapping("/login")` cho cơ chế mặc định; viết nhầm controller ở đây có thể làm sai hoặc gây xung đột với login processing.

### 2.6. Bước 5: đăng nhập thành công

Sau khi credential hợp lệ, security tạo `Authentication` đã xác thực với authorities và đặt vào ngữ cảnh reactive. Tùy cấu hình, một `ServerSecurityContextRepository` như `WebSessionServerSecurityContextRepository` lưu trạng thái qua `WebSession` để request kế tiếp với session cookie có thể được xác định là đã login.

Đừng suy luận rằng chỉ vì tên “reactive” thì login form mặc định **stateless**. Browser form login truyền thống cần trạng thái đủ để xử lý session, request cache và logout. Reactor Context phục vụ ngữ cảnh **trong subscription của một request**, còn WebSession/security context repository giúp **request kế tiếp** khôi phục authentication phù hợp.

Một success handler như `RedirectServerAuthenticationSuccessHandler` xem xét request đã lưu. Nếu có request `/private` phù hợp và session liên tục, nó thường đưa browser về `/private`; nếu không có request trước đó, mặc định thường về `/`.

### 2.7. Bước 6: browser yêu cầu lại tài nguyên

Browser gửi **request thứ hai tới `/private`** cùng cookie phiên hiện tại. Spring Security khôi phục `Authentication`, authorization kiểm tra `authenticated()` và request mới được đi tiếp tới controller.

Controller trả nội dung cá nhân, ví dụ `hello viewer`. Thành công của đăng nhập **không tự cấp mọi quyền**: nếu viewer sau đó mở `/admin` nhưng chỉ có `ROLE_USER`, rule `hasRole("ADMIN")` có thể từ chối bằng `403 Forbidden`.

## 3. Phân biệt những HTTP status dễ nhầm

| Tình huống | Hành vi điển hình trong demo form login | Ý nghĩa |
|---|---|---|
| Khách mở `GET /private` | `302 Location: /login` | Khởi động xác thực tương tác |
| Khách mở `GET /login` | `200` với HTML form | Trang login công khai |
| `POST /login` đúng credential và CSRF | `302` đến saved request hoặc `/` | Đăng nhập thành công; browser làm GET tiếp |
| `POST /login` sai username/password, CSRF hợp lệ | `302 Location: /login?error` | Authentication thất bại |
| `POST /login` thiếu/sai CSRF | `403` theo CSRF protection mặc định | Request bị từ chối trước khi login hợp lệ |
| Viewer đã login mở `GET /admin` | `403` | Có identity nhưng không có role ADMIN |
| Admin đã login mở `GET /admin` | `200` | Authentication + authorization hợp lệ |
| Client API chọn HTTP Basic thay form | Thường `401` kèm challenge | Cơ chế trả lời khác do entry point |

Mã HTTP chính xác phụ thuộc authentication entry point, success/failure handlers, request cache, content negotiation và các tùy chỉnh. Không đánh đồng “chưa login” với “đã login nhưng thiếu quyền”, và cũng không đánh đồng `403 CSRF` với `403 thiếu role`.

### 3.1. Vì sao không phải lúc nào cũng trả 401?

`401` phù hợp với nhiều API/token/HTTP Basic: client nhận challenge và gửi credential. Với **browser form login**, trải nghiệm dự kiến là chuyển browser tới một trang HTML cho người dùng nhập dữ liệu. Vì vậy `302 /login` thường xuất hiện.

Nếu bạn bật **cả** form login và HTTP Basic, entry point được chọn có thể phụ thuộc cấu hình và dạng request. Để bài demo có một luồng dễ kiểm chứng, ta **tắt HTTP Basic** và bật form login tường minh.

## 4. Những thành phần Spring Security Reactive tham gia

| Thành phần | Trách nhiệm trong hành trình |
|---|---|
| `WebFilterChainProxy` | Chọn security chain áp dụng cho request WebFlux |
| `SecurityWebFilterChain` | Bao gồm các filter xác thực, phân quyền, CSRF, context, redirect, logout… theo cấu hình |
| `ServerHttpSecurity` | Builder tạo chain; ở đây dùng `authorizeExchange` và `formLogin` |
| `AuthorizationWebFilter` | Áp chính sách `authenticated()`, `hasRole(...)`, v.v. |
| `ExceptionTranslationWebFilter` | Chuyển những lỗi authn/authz phù hợp nằm trong phạm vi nó xử lý thành phản ứng HTTP thông qua entry point/denied handler |
| `RedirectServerAuthenticationEntryPoint` | Thực hiện redirect tới trang đăng nhập khi cần xác thực tương tác |
| `ServerRequestCache` | Ghi nhớ request/URI thích hợp để trở về sau khi login |
| `AuthenticationWebFilter` | Đọc credential form, yêu cầu xác thực, xử lý success/failure qua handler tương ứng |
| `ReactiveAuthenticationManager` | Xác minh credential; có thể dựa vào user store hoặc hệ thống khác |
| `ReactiveUserDetailsService` | Tra user trong mô hình reactive |
| `PasswordEncoder` | So sánh raw password vừa nhập với hash đã lưu bằng `matches` |
| `ServerSecurityContextRepository` | Lưu/khôi phục security context giữa request, thường liên quan WebSession ở luồng form login |
| `ReactiveSecurityContextHolder` | Đọc security context trong subscription của reactive request |
| `CsrfWebFilter` | Bảo vệ các phương thức không an toàn như POST login và POST logout |
| `RedirectServerAuthenticationSuccessHandler` | Chuyển hướng sau login thành công, xét saved request |
| `ServerAuthenticationFailureHandler` | Quyết định phản ứng khi credential không hợp lệ |

Đây là **sơ đồ trách nhiệm**, không phải lời khẳng định rằng các filter luôn xuất hiện theo thứ tự của bảng. Thứ tự thực tế được Spring Security quản lý; muốn thêm security filter tùy biến phải hiểu `SecurityWebFiltersOrder`. Đừng dùng `HttpSecurity`, `SecurityFilterChain`, `ExceptionTranslationFilter` hoặc `HttpSessionRequestCache` của **Servlet** để cấu hình inbound WebFlux: chúng thuộc stack khác.

## 5. Tạo ứng dụng WebFlux Java 17+ với form login mặc định

### 5.1. Khởi tạo project

Tạo project bằng [Spring Initializr](https://start.spring.io/) với:

- Spring Boot 3.x tương thích Java 17+.
- Gradle hoặc Gradle Kotlin DSL (ví dụ dưới đây dùng Gradle Groovy DSL).
- Dependency **Spring Reactive Web** (`spring-boot-starter-webflux`).
- Dependency **Spring Security** (`spring-boot-starter-security`).
- Dependency **Spring Boot Starter Test** và **Spring Security Test** để kiểm thử.

Trong `build.gradle` do Initializr tạo, phần dependencies tương ứng:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}
```

**Đây chỉ là block dependencies**, không phải toàn bộ `build.gradle` độc lập: giữ plugins, repositories, dependency management, Java toolchain và Gradle wrapper do Initializr sinh. Không thêm `spring-boot-starter-web` vào ví dụ, vì khi cả MVC và WebFlux cùng hiện diện, Spring Boot 3.x thường ưu tiên inbound Servlet/MVC theo mặc định.

Cấu trúc mã:

```text
src/
  main/
    java/demo/formflow/
      FormFlowApplication.java
      WebSecurityConfig.java
      PagesController.java
  test/
    java/demo/formflow/
      FormFlowSecurityTests.java
```

### 5.2. `FormFlowApplication.java`

```java
package demo.formflow;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FormFlowApplication {

    public static void main(String[] args) {
        SpringApplication.run(FormFlowApplication.class, args);
    }
}
```

Class này khởi động ứng dụng và quét các component trong package `demo.formflow`.

### 5.3. `WebSecurityConfig.java`

```java
package demo.formflow;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class WebSecurityConfig {

    @Bean
    public SecurityWebFilterChain springSecurityFilterChain(
            ServerHttpSecurity http) {

        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/", "/public").permitAll()
                .pathMatchers("/login").permitAll()
                .pathMatchers(HttpMethod.GET, "/private").authenticated()
                .pathMatchers(HttpMethod.GET, "/admin").hasRole("ADMIN")
                .anyExchange().denyAll())
            .formLogin(Customizer.withDefaults())
            .httpBasic(basic -> basic.disable())
            .build();
    }

    @Bean
    public MapReactiveUserDetailsService userDetailsService() {
        PasswordEncoder encoder =
            PasswordEncoderFactories.createDelegatingPasswordEncoder();

        UserDetails viewer = User.withUsername("viewer")
            .password(encoder.encode("viewer-pass"))
            .roles("USER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("admin-pass"))
            .roles("ADMIN")
            .build();

        return new MapReactiveUserDetailsService(viewer, admin);
    }
}
```

**Giải thích các quyết định quan trọng:**

1. `@EnableWebFluxSecurity` bật integration của Spring Security với WebFlux; Spring Boot có auto-configuration, nhưng annotation tường minh giúp nhìn rõ stack đang học.
2. `SecurityWebFilterChain` từ `ServerHttpSecurity` là loại chain của WebFlux, khác `SecurityFilterChain` từ `HttpSecurity` ở Servlet.
3. `GET /` và `GET /public` là công khai để có trang xuất phát và trang về mặc định.
4. `/login` được cho phép công khai; nếu chặn chính trang login, browser có thể redirect lặp không tới được form.
5. `GET /private` yêu cầu `authenticated()`, còn `GET /admin` yêu cầu `ROLE_ADMIN`.
6. `anyExchange().denyAll()` chặn mọi request không khớp chính sách demo, tránh mở vô tình endpoint mới. Trong production cần thiết kế riêng static assets, healthcheck, CORS và các HTTP method sử dụng thực tế.
7. `formLogin(Customizer.withDefaults())` yêu cầu Spring Security sử dụng cấu hình form login mặc định; ví dụ không tự tạo HTML và không tự viết POST handler.
8. `httpBasic(basic -> basic.disable())` tránh việc HTTP Basic entry point can thiệp vào luồng redirect dành riêng cho trình duyệt.
9. `PasswordEncoderFactories.createDelegatingPasswordEncoder()` tạo hash có prefix thuật toán, thường dùng BCrypt làm lựa chọn encode mặc định theo cấu hình Spring Security. Hai mật khẩu cố định trong source là **dữ liệu bài tập**, không phải secret sản phẩm.
10. `MapReactiveUserDetailsService` cho phép Spring Security tra user theo mô hình reactive. Với production cần tích hợp account store thực, quản lý password reset, password hashing cost, MFA và audit.

**Chú ý về role:** `.roles("ADMIN")` gán authority `ROLE_ADMIN`. `.hasRole("ADMIN")` kiểm tra authority đó; không viết `hasRole("ROLE_ADMIN")` theo convention mặc định. Admin trong ví dụ chỉ có role ADMIN, không tự có USER nếu không khai báo hoặc không có role hierarchy.

**CSRF chưa bị tắt**. Đây là một phần quan trọng của form login và các POST trong browser. Không đưa `csrf(csrf -> csrf.disable())` vào cấu hình chỉ để đăng nhập “chạy được”.

### 5.4. `PagesController.java`

```java
package demo.formflow;

import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class PagesController {

    @GetMapping("/")
    public Mono<String> home() {
        return Mono.just("home");
    }

    @GetMapping("/public")
    public Mono<String> publicPage() {
        return Mono.just("public");
    }

    @GetMapping("/private")
    public Mono<String> privatePage() {
        return ReactiveSecurityContextHolder.getContext()
            .map(context -> context.getAuthentication().getName())
            .map(name -> "hello " + name);
    }

    @GetMapping("/admin")
    public Mono<String> adminPage() {
        return Mono.just("admin");
    }
}
```

`@RestController` trả các body text đơn giản để dễ quan sát trong browser. Ở ứng dụng web thực, các trang thường render template HTML; **luồng security không phụ thuộc việc controller trả HTML hay chuỗi text**. `ReactiveSecurityContextHolder` đọc authentication từ **Reactor Context** của subscription, không dựa vào ThreadLocal của Servlet.

Khi một người mở `/private` chưa đăng nhập, controller **không được gọi thành công trước bước login**. Khi đã login, controller trả `hello viewer` hoặc `hello admin` tùy principal. Việc controller có thể lấy username không có nghĩa toàn bộ dữ liệu của user đã được kiểm soát truy cập: với dữ liệu thật phải kiểm tra quyền tài nguyên trong service/repository.

## 6. Chạy thử hành trình trên trình duyệt

Từ thư mục project có Gradle wrapper:

```bash
./gradlew bootRun
```

Trên Windows:

```powershell
.\gradlew.bat bootRun
```

Dùng trình duyệt thông thường, phiên mới/chưa login, và thực hiện:

1. Mở `http://localhost:8080/public`. Kỳ vọng body `public` mà không cần login.
2. Mở `http://localhost:8080/private`. Trình duyệt nhận 302 tới `/login` và hiển thị form.
3. Nhập username `viewer`, password `viewer-pass` rồi submit. Trình duyệt gửi POST có cookie của phiên và CSRF token sinh bởi trang login.
4. Login thành công. Nếu request `/private` được saved request cache giữ lại, browser được redirect trở về `/private` và thấy `hello viewer`.
5. Mở `http://localhost:8080/admin` trong cùng browser session. Kỳ vọng từ chối `403` vì viewer không có role ADMIN.
6. Mở một cửa sổ private/incognito mới, đăng nhập `admin` / `admin-pass`. Sau khi login, `/admin` cho phép và trả `admin`.

**Vì sao cần dùng hai session/cửa sổ riêng?** Browser đã login viewer thường gửi cookie phiên đó cho mọi tab cùng origin. Mở tab mới không nhất thiết cho bạn một danh tính khác; muốn kiểm thử admin, hãy logout hoặc dùng profile/browser session khác.

### 6.1. Đăng nhập trực tiếp khác truy cập protected page trước

Nếu bạn mở `/login` trực tiếp và đăng nhập mà **chưa** có saved request, success handler mặc định thường đưa bạn tới `/`. Đó là kết quả phù hợp với cấu hình mặc định, không chứng minh mất request cache. Muốn test quay lại `/private`, **phải bắt đầu từ `/private` khi chưa đăng nhập**.

### 6.2. Kiểm chứng redirect với curl

Có thể xem header mà không cần browser:

```bash
curl -i http://localhost:8080/private
```

Nếu chưa có cookie xác thực và không bị HTTP Basic/entry point tùy biến can thiệp, hãy tìm HTTP `302` và header `Location` hướng tới `/login`. Để theo dõi cookie giữa nhiều request curl, dùng cookie jar:

```bash
curl -i -c cookies.txt -b cookies.txt http://localhost:8080/private
curl -i -c cookies.txt -b cookies.txt http://localhost:8080/login
```

Cú pháp này là minh họa cơ chế cookie jar. Muốn POST form bằng curl còn cần trích **CSRF token hợp lệ của chính phiên đó**, gửi đúng trường form URL encoded và dùng lại cookie jar; không gửi password thật trên terminal/lịch sử shell. Để học luồng end-to-end, browser thường trực quan và ít lỗi hơn việc copy token bằng tay.

Đừng dùng `curl -L` ngay khi đang muốn nhìn thấy các bước 302; nó tự theo redirect khiến bạn dễ bỏ qua status và `Location` của từng chặng.

## 7. Kiểm thử tự động Spring Security WebFlux

Test nên xác minh **trạng thái của từng bước**, không chỉ thử xem controller trả chuỗi nào. Ở đây dùng `WebTestClient` trong **mock WebFlux application context**, áp dụng Spring Security test support. Cách này cho phép gửi CSRF token trong test mà không phải tự parse HTML và vẫn đi qua security filters.

Tạo `src/test/java/demo/formflow/FormFlowSecurityTests.java`:

```java
package demo.formflow;

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
    .SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
class FormFlowSecurityTests {

    @Autowired
    ApplicationContext context;

    private WebTestClient client;

    @BeforeEach
    void setup() {
        client = WebTestClient.bindToApplicationContext(context)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    @Test
    void publicResourceDoesNotRequireLogin() {
        client.get().uri("/public")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("public");
    }

    @Test
    void unauthenticatedPrivateRequestRedirectsToLogin() {
        client.get().uri("/private")
            .exchange()
            .expectStatus().is3xxRedirection()
            .expectHeader().valueEquals(HttpHeaders.LOCATION, "/login");
    }

    @Test
    void defaultLoginPageIsAccessible() {
        client.get().uri("/login")
            .exchange()
            .expectStatus().isOk();
    }

    @Test
    void loginWithoutCsrfIsRejected() {
        client.post().uri("/login")
            .contentType(MediaType.APPLICATION_FORM_URLENCODED)
            .body(BodyInserters.fromFormData(
                "username", "viewer").with("password", "viewer-pass"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void validLoginWithCsrfRedirects() {
        client.mutateWith(csrf())
            .post().uri("/login")
            .contentType(MediaType.APPLICATION_FORM_URLENCODED)
            .body(BodyInserters.fromFormData(
                "username", "viewer").with("password", "viewer-pass"))
            .exchange()
            .expectStatus().is3xxRedirection()
            .expectHeader().valueEquals(HttpHeaders.LOCATION, "/");
    }

    @Test
    void invalidPasswordRedirectsBackWithError() {
        client.mutateWith(csrf())
            .post().uri("/login")
            .contentType(MediaType.APPLICATION_FORM_URLENCODED)
            .body(BodyInserters.fromFormData(
                "username", "viewer").with("password", "wrong"))
            .exchange()
            .expectStatus().is3xxRedirection()
            .expectHeader().valueEquals(
                HttpHeaders.LOCATION, "/login?error");
    }

    @Test
    void userRoleIsNotAdminRole() {
        client.mutateWith(mockUser("viewer").roles("USER"))
            .get().uri("/admin")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void adminRoleCanAccessAdminEndpoint() {
        client.mutateWith(mockUser("admin").roles("ADMIN"))
            .get().uri("/admin")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("admin");
    }
}
```

**Lưu ý về import static trong Java:** Cú pháp `import static org.springframework.security.test.web.reactive.server` xuống dòng `.SecurityMockServerConfigurers...;` trong snippet trên là một import declaration Java trải qua xuống dòng tại dấu chấm; whitespace vẫn hợp lệ về từ vựng. Bạn có thể nhập một dòng duy nhất trong IDE. Các symbol cần là `SecurityMockServerConfigurers.csrf`, `mockUser`, `springSecurity` từ `spring-security-test`.

**Vì sao dùng `bindToApplicationContext(...).apply(springSecurity())`?** Khi dùng WebTestClient mock server trực tiếp từ application context, cần tích hợp Spring Security WebFilters vào client setup; nếu chỉ bind controller, authorization có thể bị bypass trong test. `mutateWith(csrf())` dùng security test infrastructure gửi token hợp lệ cho login POST. Hai test `mockUser` kiểm tra **authorization** bằng principal giả lập; chúng **không** kiểm tra việc hash password. Hai test POST login mới đi qua form credential verification.

**Ý nghĩa của test redirect `/`:** `validLoginWithCsrfRedirects` không bắt đầu bằng `GET /private`, nên mặc định không có saved request trong session của request đó. Kỳ vọng về `/` là hợp lý. Muốn xác minh saved-request end-to-end, test cần giữ cookie/session xuyên các chặng hoặc chạy browser automation có kiểm soát; không gửi hai request độc lập rồi đoán vì sao không quay về `/private`.

Chạy:

```bash
./gradlew test
```

Windows:

```powershell
.\gradlew.bat test
```

Kỳ vọng **8 test pass** trong project Spring Boot 3.x có dependencies và cấu hình đúng như trên. Đây là kết quả mong đợi chứ **không phải tuyên bố đã thực thi Gradle thực tế**. Nếu version library hoặc test adapter có khác biệt về redirect URL, hãy đọc header thực tế và điều chỉnh assertion dựa trên **chính sách được xác nhận**, không thay expected status chỉ để test xanh.

### 7.1. Kiểm thử request cache riêng

Để xác minh redirect quay về `/private` thật sự, viết hoặc chạy luồng tích hợp giữ cùng session:

```text
1. GET /private (không xác thực)
   assert 302 + Location /login
   lấy cookie phiên, nếu server trả Set-Cookie

2. GET /login với cookie đó
   assert 200 và lấy CSRF token từ HTML
   ghi nhớ cookie phiên mới nếu có

3. POST /login với:
   Cookie hiện tại
   username=viewer
   password=viewer-pass
   _csrf=<token thực lấy được từ form>
   assert 302 + Location /private

4. GET /private với cookie phiên sau login
   assert 200, body "hello viewer"
```

Đây là **kịch bản test**, không phải code giả lập token. Thay đổi session ID sau login hoặc phân bổ session trên nhiều server có thể khiến test phải cập nhật cookie jar. Điều quan trọng là mọi request trong flow sử dụng đúng dữ liệu session/token theo cơ chế của ứng dụng.

### 7.2. Bộ test nên mở rộng trong sản phẩm

Với chính sách thật, thêm những case:

- Credential không hợp lệ, user vô hiệu/khóa, session hết hạn.
- Viewer đã login không được xem dữ liệu admin, kể cả gọi URL trực tiếp.
- Login thành công không có saved request -> landing page hợp lệ.
- Login thành công có saved request -> URL đúng, query string có chính sách an toàn.
- URL login công khai và resource tĩnh được phép tải; không có redirect loop.
- CSRF thiếu/sai -> POST bị từ chối; POST đúng token/session -> đi tới authentication.
- Logout POST đúng CSRF và cookie, sau đó tài nguyên protected cần login lại.
- Session renewal/session fixation protection, cookie `Secure`, `HttpOnly`, `SameSite` phù hợp production.
- Có chính sách không cho redirect ra domain do attacker cung cấp (open redirect).
- Client nhận lỗi phù hợp khi login service hoặc user store gặp sự cố, không rò rỉ thông tin credential.

## 8. Saved request, RequestCache và redirect sau login

### 8.1. Saved request là gì?

Khi một user chưa xác thực mở `/private`, Spring Security có thể lưu thông tin request cần trở lại sau login trong `ServerRequestCache`. Form login success handler tra cache để chọn đích chuyển hướng. Với WebFlux, class liên quan là `org.springframework.security.web.server.savedrequest.WebSessionServerRequestCache`.

Không nhầm với Servlet `HttpSessionRequestCache` hoặc `SavedRequestAwareAuthenticationSuccessHandler`: tên class/contract khác nhau theo stack. Không phải mọi request đều nên được lưu (ví dụ upload hoặc POST state-changing); cách cache phù hợp cần được đánh giá theo version và chính sách application.

### 8.2. Tại sao sometimes redirect về /?

Có một số lý do hợp lệ:

1. Người dùng tự mở `/login`, không có request protected trước đó.
2. Browser không gửi lại session cookie đã dùng khi saved request được ghi.
3. Saved request hết hạn, đã bị xóa hoặc bị thay thế do user mở nhiều protected pages.
4. Request cache bị vô hiệu hóa hoặc ứng dụng cấu hình success handler luôn về một trang cố định.
5. App chạy nhiều instance mà session state không được chia sẻ/định tuyến đúng.
6. URL ban đầu bị chặn bởi chính sách redirect/matcher, nên handler không chọn nó.

Nếu muốn luôn về trang cố định (ví dụ dashboard), có thể cấu hình `ServerAuthenticationSuccessHandler` phù hợp, nhưng cần cân nhắc rằng nó sẽ bỏ qua hoặc thay đổi trải nghiệm trở về saved request. Đây là **quyết định UX và bảo mật**, không phải sửa mọi trường hợp bằng một chuỗi URL hardcode.

### 8.3. Tránh open redirect

Không bao giờ tin một tham số `next`/`returnUrl` do client gửi mà không xác minh. Ví dụ `/login?next=https://attacker.invalid/collect` không được dùng thẳng làm `Location` sau login. Nếu hỗ trợ redirect theo tham số, chỉ chấp nhận đường dẫn nội bộ/allowlist origin, chuẩn hóa path, tránh protocol-relative URL (`//host`), kiểm tra encoding và canonicalization. Saved request cache do framework quản lý thường tốt hơn việc tự truyền next URL không kiểm soát.

### 8.4. Session không bằng Reactor Context

`WebSession` lưu trạng thái giữa **các HTTP request** thông qua cơ chế session repository/cookie. `ReactiveSecurityContextHolder` lấy security context trong **reactive subscriber** đang xử lý request. Khi request mới đến, security filter cần khôi phục authentication từ nguồn đáng tin và gắn lại cho subscription hiện tại. Vì thế việc “copy Reactor Context vào ThreadLocal” không thay thế được session handling.

## 9. Form login, CSRF và cookie: ba yếu tố gắn liền

### 9.1. Vì sao POST /login bắt buộc có CSRF?

CSRF không chỉ bảo vệ thao tác thay đổi dữ liệu trong ứng dụng: **login CSRF** cũng có thể ép một trình duyệt đăng nhập vào tài khoản do attacker kiểm soát, dẫn đến các hệ quả về lưu dữ liệu, sự nhầm lẫn identity và privacy. Spring Security WebFlux bật CSRF protection mặc định cho các request unsafe, trong đó có POST login.

Khi render form, security framework/view engine phải cung cấp token cho đúng phiên. User submit POST với cookie và token, `CsrfWebFilter` xác minh. Khi token sai/thiếu, request bị chặn. **Không** tắt CSRF chỉ để không cần cung cấp token cho form.

Nếu tự viết view Thymeleaf, biểu mẫu nên sử dụng integration với Spring Security để tự điền token:

```html
<form th:action="@{/login}" method="post">
  <label>
    Username
    <input type="text" name="username" autocomplete="username">
  </label>
  <label>
    Password
    <input type="password" name="password" autocomplete="current-password">
  </label>
  <button type="submit">Log in</button>
</form>
```

Đây là **mảnh template Thymeleaf** trong một ứng dụng đã bổ sung dependency/view resolver Thymeleaf và cấu hình CSRF tích hợp đúng. Không phải file HTML thuần độc lập đã đủ bảo vệ. Thymeleaf có thể tự chèn CSRF hidden field khi `th:action` và Spring Security integration hoạt động; luôn kiểm tra HTML rendered và POST thật của version đang chạy.

### 9.2. Vai trò cookie phiên

Browser nhận cookie định danh một session do server quản lý, và có thể gửi nó lại trong các request cùng origin/phạm vi. Cookie này **không nên chứa mật khẩu plaintext**. Các flag `Secure` (HTTPS), `HttpOnly`, `SameSite`, scope domain/path và thời hạn cần được cấu hình phù hợp threat model. `SameSite` giảm một số rủi ro CSRF nhưng **không thay thế CSRF token** trong các form có thể bị tấn công.

Khi test qua proxy/reverse proxy, chú ý TLS termination và forwarded headers để tránh cookie không được đánh dấu Secure hoặc URL redirect bị tạo theo scheme/host sai. Chỉ tin forwarded headers từ proxy đáng tin.

### 9.3. Session fixation và login thành công

Hệ thống cần bảo vệ trước **session fixation**: attacker cố định một session ID rồi dụ user đăng nhập để chiếm phiên. Cơ chế renew/invalidate/migrate session ID khi xác thực, logout handlers và security context repository phải được đánh giá theo chính sách/version. Không tự giả định session ID luôn giữ nguyên trước và sau login; browser và WebTestClient cần theo cookie do server trả sau từng bước.

### 9.4. Logout POST cần CSRF

Trong Spring Security WebFlux, default logout flow thường xử lý **POST /logout**; vì đây là request state-changing, CSRF protection áp dụng. Người dùng có thể vào trang xác nhận logout bằng GET, rồi gửi POST từ form có token. Không biến `GET /logout` thành hành động logout chỉ để thuận tiện, trừ khi đã đánh giá rõ nguy cơ forced logout. Khi logout thành công, phải kiểm tra rằng request mới tới `/private` không còn mang authentication cũ.

## 10. Tùy biến form login: ranh giới của các endpoint

Ở ứng dụng thật, bạn có thể muốn một form HTML branded thay vì generated login page. Khái niệm:

```java
// Mảnh cấu hình bên trong ServerHttpSecurity DSL.
// Không thêm đồng thời với formLogin mặc định ở ví dụ chính.
.formLogin(form -> form.loginPage("/signin"))
```

Khi tự đổi login page URL, bạn có trách nhiệm **phục vụ GET /signin** (controller và template/static page), cho phép URL đó công khai và giữ login processing URL/CSRF nhất quán. URL của login page và URL nhận POST login **có thể là hai endpoint khác nhau**. Đừng suy luận đổi `loginPage("/signin")` sẽ luôn tự tạo controller hoặc template.

Một số customization cần biết:

- **Login page**: URL GET cho người dùng xem form.
- **Authentication converter**: đọc username/password từ form hoặc format bạn lựa chọn theo cơ chế Spring Security.
- **ReactiveAuthenticationManager**: quyết định credential có hợp lệ không.
- **Success handler**: quyết định redirect sau login, có xét saved request hay route cố định.
- **Failure handler**: thường chuyển lại login page có thông báo lỗi.
- **Authentication entry point**: quyết định phản ứng khi khách mở protected page mà chưa xác thực.
- **Security context repository**: lưu/khôi phục ngữ cảnh giữa các request.
- **Request cache**: lưu request ban đầu nếu cần quay lại.
- **Access-denied handler**: phản hồi khi người đã xác thực nhưng thiếu quyền.

**Không cấu hình theo tên API Servlet chỉ vì bài hướng tới browser.** Ở WebFlux, dùng những thành phần trong package `org.springframework.security.web.server...` và `ServerHttpSecurity`. Xác minh tên từng method của phiên bản đang dùng trước khi copy một đoạn tùy biến từ tutorial Servlet.

### 10.1. Chống redirect loop khi viết custom page

Nếu có rule:

```java
.authorizeExchange(exchanges -> exchanges
    .anyExchange().authenticated())
.formLogin(form -> form.loginPage("/signin"))
```

nhưng không cho phép `GET /signin` công khai, user có thể bị redirect tới trang mà họ vẫn cần đăng nhập để truy cập. Trong ví dụ chính, `pathMatchers("/login").permitAll()` giải quyết đúng vấn đề tương ứng. Khi thêm CSS, JS, logo hoặc locale route cho custom form, phải cho phép **chính xác những static assets** mà trang login cần, tránh dùng `permitAll()` quá rộng làm lộ API.

### 10.2. Không lấy username/password từ query string

Form login nên gửi bằng **POST** trong body URL encoded và qua HTTPS. Đừng tạo link `/login?username=...&password=...`: URL có thể xuất hiện trong browser history, reverse proxy logs, analytics và referrer. Mật khẩu cũng không nên được lưu vào localStorage, ghi vào log hoặc phản hồi trở lại client sau login.

### 10.3. Sau login vẫn cần authorization

Một user có thể vượt qua bước authentication nhưng không có quyền vào tài nguyên ban đầu. Chẳng hạn user USER truy cập `/admin` khi chưa login: ban đầu có thể được chuyển tới login page, login thành công bằng viewer, nhưng request quay lại `/admin` vẫn phải bị từ chối `403`. Đây là kết quả đúng, không phải lỗi redirect. **Success handler không thay thế authorization.**

## 11. Phân biệt form login WebFlux với các cơ chế khác

| Cơ chế | Credential ở đâu? | Response chưa xác thực thường gặp | Giữ trạng thái |
|---|---|---|---|
| Form login WebFlux | POST HTML form + CSRF | Redirect `302` tới login page | Thường dựa trên WebSession/security context repository |
| HTTP Basic | `Authorization: Basic ...` mỗi request | `401` kèm Basic challenge | Không suy ra stateless chỉ từ việc bật Basic |
| OAuth2/OIDC login | Browser redirect giữa app và identity provider | Redirect tới authorization endpoint | Có state/nonce và session/correlation theo giao thức |
| JWT Bearer Resource Server | `Authorization: Bearer token` | `401` kèm challenge theo cấu hình | Thường token-based, nhưng phải đánh giá từng ứng dụng |

Không đồng nhất “login page” với OAuth2 authorization flow hay JWT login REST API. Bài học này chỉ thực hiện **form login username/password** qua Spring Security Reactive.

Ứng dụng Spring MVC có thể sử dụng `WebClient` để gọi service khác nhưng inbound security vẫn là **Servlet**. Phân biệt dựa trên loại web application xử lý request và cấu hình security, không dựa trên việc có thư viện Reactor.

## 12. Cách debug khi browser không trở lại trang mong muốn

### 12.1. Lập bảng quan sát từng request

Khi bug, bật Developer Tools → Network trong trình duyệt và quan sát:

| Chặng | Kiểm tra | Dấu hiệu bất thường |
|---|---|---|
| GET protected | `302`, `Location` đến login URL, cookie/session | 401 bất ngờ hoặc redirect URL sai host |
| GET login | `200`, form có action/method đúng, token CSRF | 302 lặp lại, thiếu form, static CSS 403 |
| POST login | Body form có username/password, CSRF token; cookie session | 403 CSRF, 302 ?error hoặc 4xx/5xx |
| Redirect sau login | `Location` saved request hoặc landing page | Về / vì mất cookie/saved request, open redirect |
| GET protected sau login | Cookie hiện tại; status 200 hoặc 403 theo role | 302 trở lại /login dù vừa login |
| POST logout | Cookie/token; logout thành công | 403 do thiếu CSRF, request mới còn xác thực |

Không bật log full request body/header chứa credential. Khi cần debug, dùng request ID, URL path đã loại query nhạy cảm, status, exception type và session correlation ID đã xử lý an toàn; không in session ID/token nguyên văn.

### 12.2. Một số nguyên nhân và hướng sửa cụ thể

**A. 302 /login lặp vô hạn**

- Login page của bạn cũng bị rule `authenticated()` chặn.
- Proxy rewrite path/context path khiến redirect tới URL không có controller.
- Session cookie không được gửi qua HTTPS/domain/path đúng.
- Custom entry point cho redirect sai URL; cần cho phép login page và kiểm tra proxy headers.

**B. GET /login trả 404**

- Đã cấu hình `formLogin(form -> form.loginPage(...))` nhưng không tạo controller/template cho custom URL.
- Đang dùng MVC/Servlet stack thay vì WebFlux mặc dù tưởng là reactive.
- Đã tắt form login hoặc tạo custom security chain không match URL.
- URL có context path/routing khác với client.

**C. POST /login trả 403**

- Thiếu CSRF token hoặc token không khớp session hiện tại.
- Cookie phiên không được gửi lại; token được tạo từ phiên khác.
- Form action/HTTP method/content-type không như security filter mong đợi.
- Security rule hoặc custom filter từ chối trước authentication. Kiểm tra response và log an toàn trước khi kết luận sai password.

**D. POST /login chuyển về ?error**

- Username/password sai, user bị disabled/locked/expired theo chính sách hoặc authentication manager không đọc đúng account store.
- Password hash lưu sai định dạng/encoder hoặc user store không cung cấp đúng username.
- CSRF đã hợp lệ nhưng credential verification thất bại; đừng đổi mã thành 403 nếu lý do thật là authentication failure.

**E. Login thành công nhưng về / thay vì /private**

- User tự mở trang login không qua protected request.
- Không giữ cookie/session giữa GET protected, GET login, POST login.
- Request cache bị tắt, bị ghi đè hoặc success handler dùng redirect cố định.
- Browser nhiều tab/cửa sổ dẫn tới thay đổi saved request cuối cùng.
- Session expired hoặc app nhiều instance không chia sẻ session đúng cách.

**F. Login thành công nhưng vẫn 403 ở /admin**

- Authentication hợp lệ nhưng role/authority không đủ: viewer chỉ có `ROLE_USER`.
- Mapper role sai hoặc dùng `hasRole("ROLE_ADMIN")` thay vì `hasRole("ADMIN")` theo convention.
- Không sửa bằng cách cho `permitAll` vùng admin; phải cấp authority hợp lệ hoặc từ chối theo policy.

**G. Sau login lại 302 đến /login**

- Security context không được lưu/khôi phục giữa hai request.
- Browser không gửi session cookie hoặc cookie bị browser chặn vì Secure/SameSite/domain.
- Ứng dụng có nhiều session repositories/proxies cấu hình không nhất quán.
- Custom auth success handler ghi response mà không để framework hoàn thành lưu context.
- Session ID đã đổi nhưng HTTP client tiếp tục dùng cookie cũ.

**H. Client JavaScript gọi API nhận HTML login thay vì JSON**

- Client của bạn đang gọi một endpoint với security policy của website browser.
- Nếu là API machine-to-machine, cân nhắc chain/entry point riêng để trả 401/403 phù hợp, token-based auth và CSRF threat model; không mặc định redirect HTML là đúng cho mọi client.
- Cần thiết kế `securityMatcher` và thứ tự nhiều `SecurityWebFilterChain` khi có cả browser UI và API, không thêm hai catch-all chain tùy tiện.

## 13. Câu hỏi và bài tập có đáp án

### Bài 1 — Dự đoán các request

Một browser mới mở `GET /private` và nhận `302 /login`. Sau đó mở `GET /login` rồi POST thành công. Vì sao browser lại thực hiện thêm GET tới `/private`?

**Đáp án:** Success handler dùng request cache để xác định URI đã yêu cầu trước khi xác thực, trả redirect mới. Trình duyệt thực hiện request GET mới tới URL đó và gửi session cookie hiện tại. Không phải request `GET /private` ban đầu tiếp tục chạy âm thầm từ nơi bị chặn.

### Bài 2 — Đăng nhập đúng nhưng bị 403

Viewer đăng nhập thành công với `ROLE_USER`. Khi browser được redirect về `/admin`, server trả 403. Có lỗi xác thực không?

**Đáp án:** Không nhất thiết. Authentication thành công nghĩa là danh tính đã xác minh; `hasRole("ADMIN")` đòi `ROLE_ADMIN`. Viewer không đủ quyền nên 403 là phản ứng đúng.

### Bài 3 — Login thiếu CSRF

Form POST gửi username/password đúng nhưng không có CSRF token, server trả 403. Có nên thêm `csrf(csrf -> csrf.disable())` để login hoạt động?

**Đáp án:** Không. Bảo vệ login khỏi CSRF là yêu cầu an toàn của browser form. Cần bảo đảm trang login cung cấp token từ đúng session, form gửi nó với POST và browser giữ cookie. Chỉ thay đổi CSRF policy khi threat model đã được đánh giá kỹ và có biện pháp thích hợp.

### Bài 4 — Truy cập /login trực tiếp

Nếu user mở thẳng `GET /login` rồi đăng nhập thành công, tại sao thường về `/` mà không về `/private`?

**Đáp án:** Vì trước đó không có saved request từ tài nguyên protected. Success handler dùng landing page mặc định, trong ví dụ là `/`.

### Bài 5 — Curl có thể xác minh redirect mà không login không?

**Đáp án:** Có. `curl -i` xem status 302 và Location. Nhưng để test login thành công và quay về trang cũ, client phải quản lý session cookie và CSRF token qua nhiều request; một POST độc lập không đủ.

### Bài 6 — Vì sao không tạo @PostMapping("/login")?

**Đáp án:** Spring Security form login có security filter xử lý POST login theo cấu hình. Controller riêng chỉ cần khi bạn đang thiết kế flow khác một cách có chủ đích; viết trùng endpoint rất dễ nhầm tuyến xử lý và bỏ qua bảo vệ.

### Bài 7 — Có thể lưu Authentication vào ThreadLocal sau login không?

**Đáp án:** Với WebFlux, cách chuẩn để truy cập identity trong reactive request là `ReactiveSecurityContextHolder`/Reactor Context. Authentication giữa các request liên quan `ServerSecurityContextRepository`/session; ThreadLocal không thay thế chúng khi Reactor đổi thread.

### Bài 8 — Browser redirect tới một domain do client truyền vào

Custom success handler đọc `returnUrl` từ query mà không kiểm tra, sau login trả `Location` tới domain đó. Rủi ro gì?

**Đáp án:** Open redirect: attacker lợi dụng website tin cậy để chuyển user tới site giả mạo, có thể phục vụ phishing hoặc chuỗi tấn công khác. Chỉ cho phép đích nội bộ/allowlist được chuẩn hóa và kiểm chứng; tránh tin input client nguyên văn.

### Bài 9 — Sau logout vẫn truy cập /private được

Một browser logout rồi mở lại `/private` và thấy nội dung mà không login. Cần kiểm tra gì?

**Đáp án:** Logout thực sự có xóa/không còn khôi phục security context không, cookie/session đúng chưa, client có browser cache/service worker hiển thị nội dung cũ không, và server có đang cho phép endpoint theo policy nhầm hay không. Với trang nhạy cảm nên kiểm soát cache headers phù hợp, không kết luận chỉ dựa trên trang hiển thị.

## 14. Checklist thiết kế trước khi đưa vào sản xuất

- [ ] Inbound stack thật là Spring WebFlux; dùng `ServerHttpSecurity`/`SecurityWebFilterChain`, không nhầm Servlet.
- [ ] Public endpoints (`/login`, assets cần thiết) rõ ràng; protected routes có policy dựa trên authn/authz.
- [ ] Form POST đúng URL, username/password field, method và encoding.
- [ ] Bật CSRF protection cho POST login/logout và những thao tác state-changing từ browser.
- [ ] Cookie session có `Secure`, `HttpOnly`, `SameSite`, domain/path/expiry phù hợp HTTPS/reverse proxy.
- [ ] Có bảo vệ session fixation và kế hoạch timeout/logout/revocation phù hợp.
- [ ] Password được băm qua `PasswordEncoder`, không lưu hoặc log plaintext.
- [ ] Login có rate limiting, chống credential stuffing, MFA khi phù hợp, error message tránh tiết lộ account existence.
- [ ] Success handler và request cache có behavior đã kiểm thử: saved request đúng, URL redirect an toàn, không open redirect.
- [ ] Failures trả thông báo phù hợp; người dùng không đủ role nhận 403, không bị tự cấp quyền.
- [ ] Không ghi session ID, CSRF token, raw password, Authorization header vào logs.
- [ ] Test browser cả đường happy path, sai password, CSRF invalid, session timeout, logout.
- [ ] Test API clients riêng với entry point phù hợp nếu ứng dụng cũng hỗ trợ REST/SPA.
- [ ] Có quan sát request/response status và redirect chain đủ để chẩn đoán nhưng không rò rỉ dữ liệu nhạy cảm.
- [ ] Không sử dụng account in-memory và mật khẩu ví dụ trong production.

## 15. Tóm tắt luồng cần ghi nhớ

```text
GET /private (chưa login)
  -> AuthorizationWebFilter yêu cầu authenticated()
  -> authentication entry point cho browser
  -> RequestCache có thể lưu URI /private trong WebSession
  <- 302 Location: /login

GET /login + cookie
  <- 200 HTML form có CSRF token hợp lệ

POST /login + username/password + CSRF + cookie
  -> CSRF validation
  -> AuthenticationWebFilter
  -> ReactiveAuthenticationManager + ReactiveUserDetailsService
  -> PasswordEncoder.matches(rawPassword, storedHash)

Nếu sai:
  <- 302 /login?error (form login failure handler mặc định)

Nếu đúng:
  -> Authentication + authorities được xác thực
  -> ServerSecurityContextRepository lưu context/session phù hợp
  -> RedirectServerAuthenticationSuccessHandler tra saved request
  <- 302 /private (nếu có saved request) hoặc / (nếu không)

GET /private + session cookie hiện tại
  -> SecurityContext được khôi phục cho reactive request
  -> authorization authenticated() cho phép
  -> controller trả "hello viewer"

GET /admin + session viewer
  -> role thiếu ROLE_ADMIN
  <- 403 Forbidden
```

**Ba ý cốt lõi:** (1) redirect tới login và redirect sau login là những HTTP response khác nhau; (2) saved request/session/cookie cho phép hành trình đi qua nhiều request nhưng không thay thế CSRF; (3) đăng nhập thành công chỉ xác minh danh tính, còn quyền truy cập từng resource vẫn do authorization quyết định.

## Tài liệu chính thức

- [Spring Security — WebFlux Security Configuration](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html)
- [Spring Security — Getting Started with WebFlux](https://docs.spring.io/spring-security/reference/reactive/getting-started.html)
- [Spring Security — CSRF for WebFlux](https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html)
- [Spring Security — Testing WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/test/web/)
- [Spring Security — Testing CSRF with WebTestClient](https://docs.spring.io/spring-security/reference/reactive/test/web/csrf.html)
- [Spring Security — Authorize ServerHttpRequests](https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html)
- [Spring Security — RedirectServerAuthenticationSuccessHandler API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/authentication/RedirectServerAuthenticationSuccessHandler.html)
- [Spring Security — WebSessionServerRequestCache API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/savedrequest/WebSessionServerRequestCache.html)
- [Spring Security — WebFlux WebSessionServerSecurityContextRepository API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/context/WebSessionServerSecurityContextRepository.html)
