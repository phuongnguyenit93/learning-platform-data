# Lưu ngữ cảnh bảo mật theo phiên và kiểm soát thời điểm tạo phiên

## 1. Mục tiêu và bối cảnh

Trong Spring Security Reactive, một request WebFlux có thể xác thực thành công rồi kết thúc. Khi trình duyệt gửi request kế tiếp, làm thế nào server biết đó vẫn là người đã đăng nhập? Khi nào một request công khai cần tạo phiên? Liệu gọi `exchange.getSession()` đã khiến server gửi cookie hay chưa? Và cấu hình `NoOpServerSecurityContextRepository` có bảo đảm toàn bộ ứng dụng không bao giờ dùng session không?

Bài này giải quyết trực tiếp các câu hỏi đó trong nhóm **Phiên và đăng xuất** của module **Spring Security – reactive**.

Sau bài học, bạn có thể:

1. Phân biệt **ngữ cảnh bảo mật trong một Reactor subscription**, **ngữ cảnh bảo mật được lưu giữa các request** và **WebSession**.
2. Hiểu hợp đồng `ServerSecurityContextRepository.load(exchange)` và `save(exchange, context)`; lựa chọn `WebSessionServerSecurityContextRepository` hoặc `NoOpServerSecurityContextRepository` có chủ đích.
3. Giải thích vì sao `exchange.getSession()` có thể trả một `WebSession` **chưa bắt đầu**, khi nào `session.start()`/ghi attribute làm phiên bắt đầu và lúc nào trình duyệt thấy session cookie.
4. Biết cách cấu hình **cả đường đọc lẫn đường ghi** security context cho form login WebFlux; tránh lưu thành công nhưng request kế tiếp không khôi phục được identity.
5. Nhận ra những tác nhân khác có thể khởi tạo phiên: CSRF token repository, request cache, app code và login; không nhầm “không lưu security context” với “không có session”.
6. Thiết kế stateful browser login, phân biệt với API nhận credential/token trên từng request; biết các giới hạn của “stateless” trong WebFlux.
7. Chạy ứng dụng Java 17+ với Spring Boot 3.x/Spring Security 6.x, kiểm tra GET chỉ đọc phiên, POST bắt đầu phiên, login tạo security context và request sau với cookie vẫn xác thực.
8. Kiểm tra logout, expiry, session fixation, cookie attributes, hệ thống nhiều instance và các lỗi thường gặp.

**Phạm vi:** ứng dụng inbound là **Spring WebFlux**. Không sao chép nguyên API `HttpSession`, `HttpSecurity`, `HttpSessionSecurityContextRepository` hay `SessionCreationPolicy` của Servlet vào security chain reactive.

## 2. Ba lớp trạng thái không được đánh đồng

### 2.1. Reactor Context: ngữ cảnh *trong request hiện tại*

Spring Security Reactive đưa `SecurityContext` vào **Reactor Context** của subscription đang xử lý request, và ứng dụng đọc bằng `ReactiveSecurityContextHolder`:

```java
// Phần method trong một reactive service/controller.
public Mono<String> username() {
    return ReactiveSecurityContextHolder.getContext()
        .map(ctx -> ctx.getAuthentication().getName());
}
```

Đây là **snippet**, cần import `reactor.core.publisher.Mono` và `org.springframework.security.core.context.ReactiveSecurityContextHolder`; không phải một class Java độc lập. Nó trả username nếu security context tồn tại trong subscriber. Ngữ cảnh này **không tự tồn tại trong request HTTP khác**. Chuyển scheduler bằng `publishOn`/`subscribeOn` không đồng nghĩa mất context ở cùng subscription, nhưng cũng không tạo cơ chế lưu login vĩnh viễn.

### 2.2. ServerSecurityContextRepository: cách *lưu và nạp* giữa request

`ServerSecurityContextRepository` là strategy để nạp và lưu `SecurityContext` theo `ServerWebExchange`:

```java
// Khai báo API đã rút gọn để học; đừng định nghĩa lại interface.
public interface ServerSecurityContextRepository {
    Mono<Void> save(ServerWebExchange exchange, SecurityContext context);
    Mono<SecurityContext> load(ServerWebExchange exchange);
}
```

`load` trả context hoặc hoàn tất rỗng khi chưa tìm thấy; `save` trả publisher bất đồng bộ hoàn tất khi việc lưu đã diễn ra. **Cần compose/return publisher này** nếu viết custom authentication flow; gọi `save(...)` rồi bỏ qua `Mono` chưa phải đã lưu.

Với form login browser, implementation quen thuộc là `WebSessionServerSecurityContextRepository`: đặt security context vào attribute của `WebSession`; ở request kế tiếp, nhận diện cùng session rồi đọc ra. Với API stateless, `NoOpServerSecurityContextRepository` bỏ qua việc lưu/nạp persistent security context.

### 2.3. WebSession: phiên HTTP của WebFlux

`org.springframework.web.server.WebSession` lưu **server-side attributes** giữa các HTTP request nhờ session manager/store và một session ID được client gửi lại, thường qua cookie. `WebSession` không đồng nhất với `SecurityContext`:

- Có WebSession nhưng **không** đăng nhập: app có thể lưu giỏ hàng, CSRF token hoặc saved request.
- Có authentication cho **một request** nhưng **không** lưu WebSession: ví dụ mỗi request có Bearer token hoặc HTTP Basic được xác thực lại.
- Có WebSession chứa security context: browser login duy trì identity giữa các request nhờ repository.

Sơ đồ:

```text
Request 1: POST /login
  Credential -> ReactiveAuthenticationManager
                |
                v
          Authentication hợp lệ
                |
                v
       ServerSecurityContextRepository.save(...)
                |
                v
         WebSession (server-side)
           attribute SecurityContext
                |
                v
       HTTP Set-Cookie: SESSION=<opaque-id>

Request 2: GET /private
        Cookie: SESSION=<opaque-id>
                |
                v
        WebSessionManager / store
                |
                v
       ServerSecurityContextRepository.load(...)
                |
                v
       ReactiveSecurityContextHolder trong Reactor Context
                |
                v
       AuthorizationWebFilter cho qua -> controller
```

Đây là **luồng khái niệm** khi browser giữ cookie, phiên chưa hết hạn và server có repository nhất quán. Cookie **chứa ID phiên**, không chứa plaintext password. Giá trị/thuộc tính cookie và lúc nó được phát có thể khác khi dùng custom session resolver hoặc session middleware.

## 3. WebSession được lấy ra khác với phiên thực sự bắt đầu

Spring Framework định nghĩa `ServerWebExchange.getSession()` trả `Mono<WebSession>`. `DefaultWebSessionManager` có thể trả một đối tượng WebSession hiện có hoặc một đối tượng mới khi client chưa có session ID hợp lệ.

**Quan trọng:** việc tạo đối tượng `WebSession` **không tự động bắt đầu một session có trạng thái được duy trì** và không buộc phải gửi session ID cho client. Theo hợp đồng `WebSession`, phiên bắt đầu khi **có attribute được thêm** hoặc khi code gọi `start()` một cách tường minh.

Mô hình trạng thái:

```text
GET request mới
  -> exchange.getSession()             : nhận một WebSession object
  -> session.isStarted() == false      : có thể đúng
  -> chỉ đọc session.getAttribute(...) : không bắt buộc start

  Khi session.getAttributes().put("cart", ...) hoặc session.start():
    -> session trở thành started
    -> lúc framework commit/save, state được lưu
    -> session resolver có thể phát session cookie

Request sau với cookie hợp lệ:
  -> WebSessionManager lấy session từ store
  -> session.isStarted() == true (nếu còn hiệu lực)
```

### 3.1. Đọc không đồng nghĩa start

Ví dụ phần handler:

```java
@GetMapping("/session/state")
public Mono<String> state(ServerWebExchange exchange) {
    return exchange.getSession()
        .map(session -> "started=" + session.isStarted());
}
```

Một request mới sạch, không có thành phần khác làm khởi tạo session, thường nhận `started=false`. **Không** suy ra chỉ gọi `exchange.getSession()` là đã có cookie `SESSION`. Tránh gọi `session.getId()` rồi dùng “có ID” làm dấu hiệu session đã được lưu: WebSession object mới vẫn có thể mang ID nội bộ trước khi gửi bất kỳ cookie nào.

### 3.2. Start tường minh

```java
@PostMapping("/session/start")
public Mono<String> start(ServerWebExchange exchange) {
    return exchange.getSession()
        .map(session -> {
            session.start();
            return "started=" + session.isStarted();
        });
}
```

Với WebFlux session manager mặc định, khi request hoàn tất, phiên đã start sẽ được lưu và ID được gửi tới client thông qua resolver/cookie thích hợp. Không cần tự `subscribe()` để “ép lưu”. Tại đây dùng **POST** vì chủ động tạo state, tránh biến một GET thành thao tác thay đổi trạng thái. Trong ứng dụng dùng form login, POST còn cần **CSRF token hợp lệ**; ví dụ này sẽ có test `csrf()` ở mục 8.

### 3.3. Start ngầm khi ghi attribute

```java
return exchange.getSession()
    .map(session -> {
        session.getAttributes().put("theme", "dark");
        return "saved";
    });
```

Đây là mảnh code method, không phải chương trình độc lập. Khi attribute được thêm, WebSession được coi là started theo hợp đồng. Đừng tạo session chỉ để lưu một giá trị có thể nằm ở browser hoặc request-scope nếu không cần: state server-side có cost về RAM, storage, expiry và xử lý scale.

### 3.4. Những điểm khiến suy luận bằng status/cookie sai

- **GET /login** có thể kích hoạt tạo/lưu CSRF token và start WebSession trước khi user xác thực.
- **GET /private** chưa xác thực có thể ghi saved request vào session để quay lại sau login.
- App/controller có thể ghi attribute khác ngoài security context.
- `CookieWebSessionIdResolver` hoặc custom resolver có thể thay tên/thuộc tính cookie; không hardcode trong code sản phẩm.
- Một request có session cookie **không** nhất thiết đã login; chỉ là đang giữ một session ID.
- `WebSession.isStarted()` cho biết tình trạng phiên, **không** thay thế kiểm tra `Authentication.isAuthenticated()` và authorization.

Vì vậy, chỉ dựa vào “có `Set-Cookie`” để kết luận Spring Security đang lưu login sai hoặc “không có `Set-Cookie`” để kết luận endpoint không có session là thiếu cơ sở. Hãy truy vết điều gì đã thêm session attribute và repository nào lưu security context.

## 4. WebSessionServerSecurityContextRepository hoạt động như thế nào?

Class `org.springframework.security.web.server.context.WebSessionServerSecurityContextRepository` triển khai `ServerSecurityContextRepository`:

- `load(exchange)` tìm security context từ WebSession tương ứng; khi không có, publisher rỗng.
- `save(exchange, context)` lưu context vào attribute của WebSession.
- Khi lưu context, repository **thay đổi session ID** để giảm nguy cơ **session fixation**. Đây là hành vi được tài liệu API mô tả, không phải tự viết `session.changeSessionId()` trước mọi login.
- `setSpringSecurityContextAttrName(...)` cho phép đổi tên attribute dùng để lưu context trong trường hợp có lý do cụ thể và phải đồng bộ toàn bộ hệ thống.
- `setCacheSecurityContext(true)` có thể cache kết quả `load` ở mức publisher cho một luồng request để tránh nhiều lần lookup; không đồng nghĩa cache credential toàn cục.

Lưu ý **lưu context** và **lưu cookie/session ID** là những thao tác ở các tầng khác nhau: repository viết attribute còn WebFlux WebSessionManager/session store/resolver xử lý vòng đời và nhận diện phiên.

### 4.1. Cơ chế nạp vào Reactor Context

`ReactorContextWebFilter` sử dụng một `ServerSecurityContextRepository` để nạp `SecurityContext` cho `ReactiveSecurityContextHolder` của **request đang chạy**. Vì thế:

```text
WebSession attribute SecurityContext (giữa requests)
           |
           v
ServerSecurityContextRepository.load(exchange)
           |
           v
ReactorContextWebFilter
           |
           v
ReactiveSecurityContextHolder.getContext()
           |
           v
service/controller trong cùng Reactor subscription
```

Nếu bạn cấu hình repository của **form-login filter để save** nhưng `ReactorContextWebFilter` dùng một repository khác để **load**, POST login có thể trả thành công nhưng GET request sau lại xem user là anonymous. Đây là lỗi cấu hình rất khó phát hiện nếu chỉ kiểm tra redirect sau POST login.

### 4.2. Cấu hình read và write phải đồng bộ

`ServerHttpSecurity.securityContextRepository(repository)` chọn strategy sử dụng bởi `ReactorContextWebFilter` để **load** vào Reactor Context. Theo tài liệu API, nó **không tự điều khiển cách từng `AuthenticationWebFilter` lưu context**, vì đường save cấu hình theo từng cơ chế xác thực.

Đối với form login:

```java
// Các dòng bên trong phương thức @Bean SecurityWebFilterChain:
ServerSecurityContextRepository repository =
    new WebSessionServerSecurityContextRepository();

return http
    .securityContextRepository(repository) // load giữa requests
    .formLogin(form -> form
        .securityContextRepository(repository)) // save khi login
    .authorizeExchange(exchanges -> exchanges
        .anyExchange().authenticated())
    .build();
```

Đây là **mảnh cấu hình** để nhấn mạnh read/write dùng **cùng instance/semantics**; chưa có đầy đủ route public, user store và CSRF form. Bài demo chạy được ở mục 7 sẽ bổ sung đầy đủ.

Không nên tự thêm `.contextWrite(ReactiveSecurityContextHolder.withAuthentication(...))` ở controller sau khi xác thực và coi đó là lưu phiên. `contextWrite` chỉ ảnh hưởng scope của **subscription đó**, không lưu vào WebSession cho HTTP request tiếp theo.

### 4.3. Không gọi save rồi bỏ publisher

Sai trong custom flow:

```java
repository.save(exchange, context);
return Mono.just("ok");
```

Đây là **ví dụ sai**: `save(...)` trả `Mono<Void>`; nếu bỏ publisher, thao tác lưu có thể không được thực thi.

Đúng về cách compose:

```java
return repository.save(exchange, context)
    .thenReturn("ok");
```

Đây là **mảnh code minh họa** khi đã có `repository`, `exchange` và `context` đáng tin cậy. Đừng tự làm custom login bằng cách chấp nhận username tùy ý từ request rồi lưu vào session. Việc tạo `Authentication` phải đến từ `ReactiveAuthenticationManager` hoặc một cơ chế xác thực đáng tin; handler của Spring Security đã đảm nhiệm việc đó khi dùng form login.

## 5. Kiểm soát *thời điểm tạo* phiên phải nhìn toàn bộ pipeline

Một chỉ số quan trọng là tỷ lệ request **không cần state** so với request làm **start/persist session**. Để tránh dùng quá nhiều RAM/session store, cần biết tất cả vị trí phát sinh state:

| Hoạt động | Có thể start WebSession? | Giải thích |
|---|---|---|
| `exchange.getSession()` rồi chỉ đọc | Thường **không** | Tạo/tra đối tượng phiên, chưa cần ghi |
| `session.start()` | **Có** | Yêu cầu start tường minh |
| `session.getAttributes().put(...)` | **Có** | Attribute được thêm làm session bắt đầu |
| Form login thành công với `WebSessionServerSecurityContextRepository` | **Có** | Lưu authenticated SecurityContext vào session |
| GET login page có CSRF token trong WebSession | **Có thể** | Cần trạng thái CSRF token để POST sau đó |
| Gặp protected URL khi anonymous, request cache dùng WebSession | **Có thể** | Saved request để redirect sau login |
| Login thất bại | Tùy cấu hình | CSRF/request cache/session trước đó có thể tồn tại; không đồng nghĩa đã xác thực |
| Login API xác minh credential theo từng request với no-op repo | Không do **security-context repository** | Nhưng CSRF/request cache/app vẫn có thể tạo session |
| Logout | Có thể thao tác lên session hiện có | Phải làm mất khả năng khôi phục authentication cũ |

Một GET công khai có thể không start session, nhưng nếu response sử dụng template để truy cập CSRF token hoặc một filter ghi request state, kết quả sẽ khác. Không dùng giả định “GET không bao giờ tạo session”. Muốn chứng minh một endpoint cụ thể **không** start session, test trạng thái và cookie trên request sạch **trong đúng cấu hình thực tế**.

### 5.1. Request cache là một nguồn tạo session độc lập

`WebSessionServerRequestCache` lưu request protected bị gián đoạn để redirect về đó sau login. Khi user mở `/private` rồi bị chuyển `/login`, session có thể đã start **trước khi đăng nhập** vì cache cần lưu URI gốc.

`NoOpServerRequestCache` là lựa chọn khi không muốn cache request, thường trong API stateless. Thay đổi request cache sẽ ảnh hưởng UX browser form login: sau login có thể không quay lại URL ban đầu.

### 5.2. CSRF token cũng cần state trong nhiều cấu hình

`WebSessionServerCsrfTokenRepository` có thể cất CSRF token trong session. Khi login page render form token, session có thể được bắt đầu để giữ token giữa GET form và POST. Không tắt CSRF chỉ vì thấy session được tạo sớm: CSRF bảo vệ luồng browser cookie-based, bao gồm POST login/logout.

Nếu dùng SPA hoặc cơ chế token khác, có thể chọn `CookieServerCsrfTokenRepository` và chính sách an toàn phù hợp, nhưng đó là **cách lưu CSRF token**, không mặc nhiên làm `Authentication` stateless hay bảo vệ khỏi mọi dạng CSRF.

### 5.3. Phân biệt “không cần security session” với “không tạo session bao giờ”

`NoOpServerSecurityContextRepository` chỉ nói về **đường lưu/nạp SecurityContext**. Nó không ngăn code khác gọi `WebSession.start()`, không tắt WebSession manager, không tự thay request cache/CSRF repository, và không xóa các session cookie đã có. Một API cần thật sự tránh session state phải xem **toàn bộ chain, filter, middleware, controller, request cache và login mechanism**.

## 6. Stateful form login và stateless API: hai cách tổ chức

### 6.1. Stateful browser form login

Khi browser đăng nhập bằng HTML form, các thành phần thường phối hợp:

```text
GET /private chưa login
  -> authorization yêu cầu identity
  -> request cache có thể lưu URI, WebSession có thể start
  -> redirect /login

GET /login
  -> form và CSRF token
  -> WebSession có thể có dữ liệu trước login

POST /login + credential + CSRF + cookie
  -> ReactiveAuthenticationManager xác minh
  -> Authentication hợp lệ
  -> WebSessionServerSecurityContextRepository.save(...)
  -> security context lưu qua WebSession, ID có thể đổi
  -> redirect saved URL hoặc trang mặc định

GET /private + cookie phiên hiện tại
  -> WebSessionServerSecurityContextRepository.load(...)
  -> ReactorContextWebFilter đưa context vào subscriber
  -> authorization cho request tiếp tục
```

Điều cần test không chỉ là `POST /login` trả 302; phải có **GET kế tiếp với cookie** và nhận dữ liệu của đúng user.

### 6.2. Stateless API không dùng session để lưu authentication

Ví dụ **mảnh cấu hình minh họa** cho một API xác thực theo từng request bằng HTTP Basic, không phải toàn bộ cấu hình chạy độc lập:

```java
ServerSecurityContextRepository noOp =
    NoOpServerSecurityContextRepository.getInstance();

return http
    .securityContextRepository(noOp)   // load: không khôi phục login từ session
    .httpBasic(basic -> basic
        .securityContextRepository(noOp)) // save: không lưu auth vào session
    .formLogin(form -> form.disable())
    .requestCache(cache -> cache
        .requestCache(NoOpServerRequestCache.getInstance()))
    .authorizeExchange(exchanges -> exchanges
        .anyExchange().authenticated())
    .build();
```

Import các class WebFlux Security trong `org.springframework.security.web.server...`; code cần có `ReactiveAuthenticationManager`/user store phù hợp. Đây là **ví dụ về quyết định persistence**, không chứng minh toàn bộ ứng dụng tuyệt đối không tạo WebSession. HTTP Basic xác minh credential trên từng request, không phải giải pháp thay thế Bearer token trong mọi hệ thống. Nếu browser tự gửi Basic credential, cần **đánh giá CSRF theo threat model**; không tự động tắt CSRF chỉ vì gọi API là stateless.

Với REST API bảo vệ bằng JWT Bearer Resource Server, mô hình thông thường cũng là **xác thực token của từng request**, không cần lưu `Authentication` giữa request trong WebSession. Tuy nhiên phải kiểm tra JWT signature, issuer, audience, expiry, scope/authority và chính sách revocation phù hợp. Các endpoint nhận cookie hoặc hoạt động qua browser vẫn cần đánh giá CSRF riêng.

### 6.3. Không sao chép SessionCreationPolicy của Servlet

Một đoạn cấu hình hay thấy ở tutorial Servlet:

```java
// Servlet only, không áp dụng nguyên văn cho ServerHttpSecurity:
http.sessionManagement(session ->
    session.sessionCreationPolicy(SessionCreationPolicy.STATELESS));
```

Đây là **code minh họa sai stack trong bối cảnh WebFlux**. `SessionCreationPolicy` liên quan tới HTTP Servlet `HttpSecurity`/`HttpSession`. Với reactive, phải xem `ServerSecurityContextRepository`, `ServerRequestCache`, `WebSession` và những thành phần khác. `ServerHttpSecurity.sessionManagement(...)` ở phiên bản có API quản lý session/concurrency không đồng nghĩa có cùng method `sessionCreationPolicy(...)` như Servlet.

Không tuyên bố chỉ một dòng `NoOpServerSecurityContextRepository` tương đương 100% với `STATELESS` của mọi thành phần framework.

## 7. Project chạy được: nhìn thấy session trước và sau login

Ứng dụng demo có ba endpoint quan trọng:

- `GET /session/state`: chỉ tra `WebSession` rồi cho biết `isStarted`.
- `POST /session/start`: chủ động gọi `start()`; vẫn **chưa** xác thực ai.
- `GET /private`: chỉ cho user đã login qua form, đọc `ReactiveSecurityContextHolder` để trả username.

Từ đó ta tách được **session tồn tại** với **SecurityContext đã xác thực**.

### 7.1. Dependency và cấu trúc file

Tạo project Spring Initializr với Java 17+, Spring Boot 3.x, Gradle, Spring Reactive Web, Spring Security, Spring Boot Starter Test và Spring Security Test. Trong `build.gradle` do Initializr tạo, giữ plugin, repositories, dependency management và Java toolchain; block dependencies:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}
```

Đây là **block dependencies**, không phải toàn bộ `build.gradle` chạy độc lập. Không thêm `spring-boot-starter-web` vì inbound WebFlux có thể bị thay bằng Servlet/MVC khi cả hai starters hiện diện.

Cấu trúc file:

```text
src/main/java/demo/sessionsecurity/
  SessionSecurityApplication.java
  SecurityConfig.java
  SessionController.java
src/test/java/demo/sessionsecurity/
  SessionSecurityTests.java
```

### 7.2. `SessionSecurityApplication.java`

```java
package demo.sessionsecurity;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SessionSecurityApplication {

    public static void main(String[] args) {
        SpringApplication.run(SessionSecurityApplication.class, args);
    }
}
```

### 7.3. `SecurityConfig.java`: một repository cho load/save

```java
package demo.sessionsecurity;

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
import org.springframework.security.web.server.context.ServerSecurityContextRepository;
import org.springframework.security.web.server.context.WebSessionServerSecurityContextRepository;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    public ServerSecurityContextRepository securityContextRepository() {
        return new WebSessionServerSecurityContextRepository();
    }

    @Bean
    public SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http,
            ServerSecurityContextRepository repository) {
        return http
            .securityContextRepository(repository)
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET,
                    "/", "/session/state").permitAll()
                .pathMatchers(HttpMethod.POST,
                    "/session/start").permitAll()
                .pathMatchers("/login").permitAll()
                .pathMatchers(HttpMethod.GET,
                    "/private").authenticated()
                .anyExchange().denyAll()
            )
            .formLogin(form -> form
                .securityContextRepository(repository))
            .httpBasic(basic -> basic.disable())
            .build();
    }

    @Bean
    public MapReactiveUserDetailsService users() {
        PasswordEncoder encoder =
            PasswordEncoderFactories.createDelegatingPasswordEncoder();

        UserDetails student = User.withUsername("student")
            .password(encoder.encode("student-pass"))
            .roles("USER")
            .build();

        return new MapReactiveUserDetailsService(student);
    }
}
```

Trong demo:

1. `securityContextRepository()` trả một instance của `WebSessionServerSecurityContextRepository`.
2. `http.securityContextRepository(repository)` cung cấp nguồn đọc cho `ReactorContextWebFilter`.
3. `formLogin(form -> form.securityContextRepository(repository))` chỉ rõ nơi login filter **save** `Authentication`.
4. `GET /session/state` công khai và chỉ đọc trạng thái. `POST /session/start` công khai nhưng thay đổi session nên cần CSRF; endpoint này **chỉ phục vụ thí nghiệm** và không nên mở cho anonymous trong production.
5. `/login` công khai; Spring Security tạo form login page và xử lý POST login. `/private` yêu cầu authentication.
6. CSRF mặc định **được giữ nguyên**; ta không tắt để POST login/POST start vượt qua một cách không an toàn.
7. HTTP Basic bị tắt để browser đi theo flow form login nhất quán.
8. User/password là dữ liệu demo, không lưu plaintext vào account store: password được băm bằng `DelegatingPasswordEncoder`; không tái sử dụng credential mẫu trong sản phẩm.

**Vì sao không tự gọi `new WebSessionServerSecurityContextRepository()` ở hai vị trí?** Hai instance có cùng config mặc định thường có thể cùng đọc một attribute; tuy nhiên dùng một bean làm rõ contract và tránh sai khác tên attribute/caching khi tùy biến. Quan trọng hơn, **đúng loại và cùng semantics** ở load/save để request kế tiếp đọc được context.

### 7.4. `SessionController.java`

```java
package demo.sessionsecurity;

import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@RestController
public class SessionController {

    @GetMapping("/")
    public Mono<String> home() {
        return Mono.just("home");
    }

    @GetMapping("/session/state")
    public Mono<String> state(ServerWebExchange exchange) {
        return exchange.getSession()
            .map(session -> "started=" + session.isStarted());
    }

    @PostMapping("/session/start")
    public Mono<String> start(ServerWebExchange exchange) {
        return exchange.getSession()
            .map(session -> {
                session.start();
                return "started=" + session.isStarted();
            });
    }

    @GetMapping("/private")
    public Mono<String> privatePage() {
        return ReactiveSecurityContextHolder.getContext()
            .map(ctx -> ctx.getAuthentication().getName())
            .map(name -> "hello " + name);
    }
}
```

Các method trả `Mono`, không gọi `block()` hay `subscribe()` trong request handler. Trong Spring WebFlux, session manager xử lý save vào cuối vòng đời trao đổi HTTP; ví dụ chỉ cần `session.start()` khi muốn start rõ ràng.

`/private` không trực tiếp gọi `getSession()`: nó đọc `SecurityContext` từ Reactor Context đã được Spring Security nạp/đặt cho request. Điều này tách responsibility của **security filter** khỏi business controller.

### 7.5. Kết quả dự kiến với browser và curl

Chạy Gradle wrapper:

```bash
./gradlew bootRun
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Ở terminal khác:

```bash
curl -i http://localhost:8080/session/state
curl -i http://localhost:8080/private
```

Với client chưa có session và không có thành phần nào khác thêm attribute ở request công khai, `GET /session/state` dự kiến body:

```text
started=false
```

Nó thường **không** cần `Set-Cookie: SESSION=...`. Lưu ý nếu app được gắn thêm custom filters/session middleware hoặc CSRF token được yêu cầu/render trong request, kết quả có thể thay đổi; đây là bài demo với cấu hình cụ thể.

`GET /private` chưa login thường trả `302 Location: /login` vì form login được bật. Request cache hoặc CSRF có thể khởi tạo session trong luồng này; điều đó **không đồng nghĩa user đã xác thực**.

Trong browser:

1. Mở `http://localhost:8080/private` ở profile chưa login.
2. Browser chuyển tới generated `/login`, mang theo cookie/session nếu framework đã tạo.
3. Đăng nhập `student` / `student-pass`. Generated form bao gồm CSRF token hợp lệ cho session.
4. Login thành công; browser được redirect về saved request hoặc trang mặc định.
5. Mở `/private`: dự kiến `hello student`.
6. Mở `/session/state` trong cùng profile: dự kiến `started=true` vì phiên đã lưu security context.

Không dùng GET trực tiếp để thử `/session/start`: endpoint demo chỉ nhận POST và mặc định yêu cầu CSRF. Một HTTP POST thiếu token nhận `403`; đây là cơ chế bảo vệ bình thường, không phải bug.

### 7.6. Thay đổi cấu hình cookie và timeout

Ví dụ các property Spring Boot 3.x cho **môi trường HTTPS**:

```properties
# application.properties - cấu hình ví dụ, phải kiểm tra với môi trường
server.reactive.session.timeout=20m
server.reactive.session.cookie.name=SESSION
server.reactive.session.cookie.http-only=true
server.reactive.session.cookie.secure=true
server.reactive.session.cookie.same-site=lax
```

`secure=true` chỉ nên được bật khi site phục vụ qua HTTPS (hoặc reverse proxy TLS cấu hình forwarded headers đúng); cookie Secure không được browser gửi trên HTTP thông thường. Vì demo chạy bằng `http://localhost:8080`, **đừng copy nguyên block này vào local demo rồi kết luận login bị mất** khi browser không gửi Secure cookie.

`timeout=20m` là **thời gian hết hạn không hoạt động** theo session manager/store, không phải đảm bảo browser bị logout tức khắc ở đúng mili-giây khi tab còn mở. Với Spring Session bên ngoài, kiểm tra cấu hình timeout riêng của session repository và lifecycle của distributed store. Cookie flags cần thiết nhưng không thay thế CSRF, session fixation protection, logout và authorization.

## 8. Kiểm thử với WebTestClient: session chưa start, bắt đầu, rồi lưu authentication

Để test WebFlux security filter mà không phải tự parse HTML CSRF token, ta dùng `WebTestClient.bindToApplicationContext(...)` với `SecurityMockServerConfigurers.springSecurity()`. Các test dùng mock WebFlux application context và session repository do framework cung cấp; chúng kiểm tra nhiều request/cookie bằng phương thức của `WebTestClient`.

Tạo `src/test/java/demo/sessionsecurity/SessionSecurityTests.java`:

```java
package demo.sessionsecurity;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseCookie;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.reactive.function.BodyInserters;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
class SessionSecurityTests {

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
    void sessionObjectCanBeReadWithoutStartingIt() {
        client.get().uri("/session/state")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class)
            .isEqualTo("started=false");
    }

    @Test
    void startDoesNotMeanAuthentication() {
        var startResult = client.mutateWith(csrf())
            .post().uri("/session/start")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("started=true")
            .returnResult();

        ResponseCookie sessionCookie =
            startResult.getResponseCookies().getFirst("SESSION");
        assertNotNull(sessionCookie);

        client.get().uri("/session/state")
            .cookie("SESSION", sessionCookie.getValue())
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("started=true");

        client.get().uri("/private")
            .cookie("SESSION", sessionCookie.getValue())
            .exchange()
            .expectStatus().is3xxRedirection();
    }

    @Test
    void loginSavesAuthenticationForANewHttpRequest() {
        var loginResult = client.mutateWith(csrf())
            .post().uri("/login")
            .contentType(MediaType.APPLICATION_FORM_URLENCODED)
            .body(BodyInserters.fromFormData(
                "username", "student").with("password", "student-pass"))
            .exchange()
            .expectStatus().is3xxRedirection()
            .expectBody().isEmpty()
            .returnResult();

        ResponseCookie sessionCookie =
            loginResult.getResponseCookies().getFirst("SESSION");
        assertNotNull(sessionCookie);

        client.get().uri("/private")
            .cookie("SESSION", sessionCookie.getValue())
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("hello student");
    }

    @Test
    void missingCsrfRejectsStateChangingPost() {
        client.post().uri("/session/start")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void sessionCookieIsNotRequiredForPublicHome() {
        client.get().uri("/")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("home");
    }
}
```

### 8.1. Vì sao các test có giá trị?

- `sessionObjectCanBeReadWithoutStartingIt` tách việc tạo `WebSession` object khỏi `isStarted`. Trong **đúng cấu hình demo**, request công khai chỉ đọc session và không có thành phần chủ ý ghi attribute.
- `startDoesNotMeanAuthentication` chứng minh session đã start vẫn có thể **anonymous**. Cookie chỉ đại diện state, không cấp role.
- `loginSavesAuthenticationForANewHttpRequest` chứng minh POST login thành công và GET `/private` **là hai HTTP exchanges khác nhau**: request thứ hai chỉ có cookie, không gửi lại mật khẩu; user vẫn được nhận diện nhờ repository.
- `missingCsrfRejectsStateChangingPost` chứng minh endpoint tạo state không bỏ qua CSRF.
- `sessionCookieIsNotRequiredForPublicHome` chứng minh rule `permitAll()` cho phép truy cập public resource.

Trong `loginSavesAuthenticationForANewHttpRequest`, `mutateWith(csrf())` là **test helper** tạo/đính token hợp lệ trong mock WebFlux security environment; nó không phải một cách hợp lệ để client ngoài đời “tự bịa” CSRF token. Browser thật phải lấy token từ trang login/cùng phiên.

Test dùng cookie mặc định `SESSION`. Nếu bạn đã đổi `server.reactive.session.cookie.name` hoặc thay resolver, cần đọc và dùng **tên cookie thật** trong test thay vì hardcode `SESSION`. Không assert ID cố định: Spring Security có thể đổi session ID sau khi save authentication để chống session fixation.

### 8.2. Chạy và diễn giải kết quả

Từ project root:

```bash
./gradlew test
```

Windows:

```powershell
.\gradlew.bat test
```

Kỳ vọng **5 test pass** với Spring Boot 3.x/Spring Security 6.x trong cấu hình đã trình bày. Đây là **kỳ vọng từ code**, không phải tuyên bố đã chạy Gradle trong môi trường học viên. Nếu một test lỗi ở version/test adapter cụ thể, xem response cookie, status, session repo và security filter setup thực thay vì bỏ bớt assertion.

Kiểm thử toàn hệ thống nên bổ sung một test trình duyệt thật hoặc test HTTP chạy server để xác nhận cookie attributes, session rotation, TLS, load balancing và timeout. Mock WebTestClient không thay thế các kiểm chứng network/reverse-proxy.

### 8.3. Một kiểm thử nên có để ngăn user bị lẫn phiên

Sau login thành công bằng `student`, tạo HTTP client khác không gửi cookie và gọi `/private`. Client đó vẫn phải bị redirect/challenge như anonymous. Cookie của user A không thể biến thành authentication toàn cục cho user B. Tuyệt đối không giữ `Authentication` vào static field hoặc singleton mutable để “nhớ” login.

## 9. Khi nào nên tránh khởi tạo session trong hệ thống lớn?

Mỗi session đã start có thể tiêu tốn RAM hoặc dung lượng distributed store, đồng thời tạo traffic đọc/ghi, TTL và công việc dọn dẹp. Nếu server trả cookie session trên mọi request crawler/public asset, số lượng session có thể tăng không cần thiết.

Một phương pháp kiểm soát:

1. Xác định endpoint nào **phải** có session (browser login, cart, wizard, CSRF state tùy chọn).
2. Đối với endpoint thuần public GET, tránh gọi `session.start()` hoặc `put` attribute nếu không có lý do.
3. Kiểm tra cấu hình request cache: đừng cache mọi request vô ích, đặc biệt các API machine-to-machine.
4. Với một API xác thực token mỗi request, ưu tiên `NoOpServerSecurityContextRepository` hoặc strategy tương đương khi không có yêu cầu session persistence, và xem xét request cache/CSRF/cookie toàn pipeline.
5. Đừng disable CSRF chỉ nhằm “bớt session”: nếu browser tự gửi cookie/credential, phải đánh giá CSRF threat model.
6. Đo **started sessions**, session creation rate, storage RAM/Redis, invalidation/expiration, session count theo tenant và tần suất bất thường.
7. Khi thay stateful thành stateless, test đường authentication/authorization cho từng request, không chỉ test login redirect.

### 9.1. Số lượng session và session store

Ở WebFlux cơ bản, `DefaultWebSessionManager` thường dùng `InMemoryWebSessionStore`; dữ liệu này thuộc một instance ứng dụng và không tự chia sẻ giữa các node. Khi chạy nhiều instance, nếu request 1 login ở pod A nhưng request 2 vào pod B, pod B có thể không tìm thấy WebSession; user lại bị redirect login.

Cách xử lý production có thể là Spring Session Reactive với Redis hay storage phù hợp, hoặc kiến trúc token-based không phụ thuộc server session, tùy yêu cầu. **Sticky session** có thể giảm một số triệu chứng nhưng không giải quyết tốt failover/pod restart, và cũng không tự tạo cơ chế đồng bộ revoke/logout giữa instance.

### 9.2. Timeout, idle expiration và logout

WebSession có idle timeout; session store có thể xóa state khi quá hạn. Khi cookie cũ được gửi lại nhưng session đã hết hạn, server có thể tạo một WebSession object mới chưa xác thực. Vì vậy GET protected sau expiry phải yêu cầu login lại.

Ở browser flow, logout phải làm mất khả năng khôi phục authentication: sử dụng handler/logout DSL chính thức. Khi có yêu cầu invalidation toàn phiên, `WebSession.invalidate()` là API thích hợp để loại state; không đủ để bảo đảm browser không còn **các credential độc lập** như remember-me, JWT hoặc HTTP Basic credential đã cache. Logout chính xác tùy cơ chế xác thực.

Ví dụ đoạn mã cho **custom session revocation** đã được ủy quyền:

```java
return exchange.getSession()
    .flatMap(session -> session.invalidate());
```

Đây chỉ là **mảnh code** trong flow có authn/authz phù hợp; không thay thế toàn bộ Spring Security logout handler. `invalidate()` trả `Mono<Void>`, phải return/compose, không tự `subscribe()` và bỏ qua completion.

### 9.3. Session fixation và ID rotation

Một attacker có thể cố dụ user sử dụng trước một session ID mà attacker biết. Nếu server không đổi session ID khi user login, attacker có nguy cơ dùng cùng ID truy cập phiên đã xác thực.

`WebSessionServerSecurityContextRepository` có cơ chế **thay ID khi save SecurityContext** theo tài liệu API. Hãy test rằng client sử dụng cookie ID **sau login**; không cố tái sử dụng ID cũ. Khi tự viết custom context repository/login handler, phải bảo vệ session fixation theo thiết kế tương đương, không coi session là “an toàn do cookie có ngẫu nhiên” mà bỏ qua vòng đời ID.

### 9.4. Session theft, revocation và cookie flags

- `Secure`: browser gửi cookie qua HTTPS phù hợp.
- `HttpOnly`: giảm khả năng JavaScript truy cập session cookie.
- `SameSite`: hạn chế một số luồng cross-site; không thay CSRF token đầy đủ.
- `Path`/`Domain`: giới hạn phạm vi gửi cookie.
- Expiration/idle timeout, logout, device/session management và cảnh báo phiên bất thường làm giảm thời gian khai thác cookie bị đánh cắp.
- Session ID là dữ liệu nhạy cảm: không ghi nguyên giá trị vào log, URL, analytics, exception, support ticket hay tracing baggage.
- Với reverse proxy, chỉ tin forwarded headers từ proxy đáng tin; cấu hình HTTPS/TLS termination đúng để redirect và Secure cookie hoạt động.

## 10. Bảng so sánh những cách lưu security context

| Cấu hình | Nạp SecurityContext ở request sau | Lưu sau authentication | Session có thể được tạo bởi thành phần khác? |
|---|---|---|---|
| `WebSessionServerSecurityContextRepository` cho cả load và save | Có, nếu cookie/session hợp lệ | Có, lưu vào WebSession | Có |
| `NoOpServerSecurityContextRepository` cho cả load và save | Không từ repository này | Không từ repository này | **Có** (CSRF, request cache, app code) |
| Load từ WebSession nhưng form login save vào no-op | Không có context mới để nạp sau login | Không lưu login mới | Có |
| Form login save vào WebSession nhưng load dùng no-op | Request sau không khôi phục context từ WebSession | Có lưu nhưng không được load đúng | Có |
| Chỉ `contextWrite(ReactiveSecurityContextHolder.withAuthentication(...))` | Không tự lưu giữa request | Không | Phụ thuộc components khác |
| Xác thực Bearer JWT từng request | Token mới được kiểm tra mỗi request | Không nhất thiết dùng session | Phụ thuộc components khác |

Bảng mô tả **ý nghĩa của persistence strategy**, không suy ra request có/không có `Set-Cookie` bằng một mình tên class. Các thành phần Spring Security khác có thể dùng session độc lập với authentication repository.

## 11. Những sai lầm phổ biến

1. **Nghĩ `exchange.getSession()` luôn cấp cookie.** Nó trả WebSession object, không bắt buộc started; quan sát `isStarted()` và state thực.
2. **Dựa vào `session.getId()` để xác nhận đã lưu.** Đối tượng session mới cũng có ID; phải xem session started/persisted và cookie thật.
3. **Nhầm WebSession với Authentication.** Session anonymous vẫn có thể tồn tại do CSRF/request cache.
4. **Chỉ cấu hình repo để load, quên form login save.** POST login thành công nhưng request sau không có security context phù hợp.
5. **Chỉ cấu hình form login save, quên nơi load.** Authentication được cất nhưng WebFlux không khôi phục qua đúng repository.
6. **Gọi `repository.save(...)` rồi bỏ publisher.** Reactor lazy; phải compose và return Mono.
7. **Dùng `contextWrite` để “lưu đăng nhập”.** ContextWrite là subscription-scope, không phải server-side session persistence.
8. **Bật NoOp rồi tự tuyên bố toàn hệ thống stateless.** CSRF, saved request, OAuth2 state và controller vẫn có thể tạo phiên.
9. **Tắt CSRF vì POST login bị 403.** Cần gửi token cùng đúng session, không gỡ bảo vệ browser.
10. **Nhầm `SessionCreationPolicy` của Servlet với ServerHttpSecurity.** Không bê nguyên DSL khác stack vào WebFlux.
11. **Dùng GET để start session mà không có lý do.** GET nên an toàn/idempotent; demo chủ động dùng POST.
12. **Mở endpoint start session cho anonymous ngoài production.** Có thể bị lạm dụng tạo nhiều session; demo là ngoại lệ để học.
13. **Tưởng Set-Cookie=đã login.** Cookie chỉ nhận diện session; không nói về role hay credential.
14. **Tưởng không thấy Set-Cookie ở một response nghĩa là không có session.** Cookie có thể đã được đặt trước đó và gửi lại bằng Cookie header.
15. **Không giữ cookie sau redirect hoặc session ID rotation.** Client dùng cookie cũ làm mất login.
16. **Không có distributed session store khi chạy nhiều node.** Mất trạng thái khi load balancer đổi node hoặc pod restart.
17. **Dựa vào ThreadLocal `SecurityContextHolder` trong reactive controller.** Dùng `ReactiveSecurityContextHolder` từ Reactor subscription.
18. **Lưu raw password/token/session ID vào WebSession và log.** Giảm tối đa secret/data nhạy cảm, chỉ lưu state cần thiết có TTL.
19. **Không có timeout/revocation/logout test.** Session có thể còn hiệu lực lâu hơn chính sách dự kiến.
20. **Kiểm thử mock context mà không test HTTP cookie continuity.** Test phải làm request mới và gửi lại cookie đã nhận sau login.

## 12. Bài tập có đáp án

**Bài 1 — Đối tượng session đã tồn tại nghĩa là session được lưu chưa?**

`exchange.getSession()` trả WebSession, `isStarted() == false`, không có attribute được thêm. Khi request kết thúc, có chắc client nhận cookie không?

**Đáp án:** Không. Việc tạo/tra WebSession không tự start session. Cookie/session persistence chỉ cần thiết khi session bắt đầu theo chính sách manager/resolver. Đừng lấy `getId()` làm bằng chứng.

**Bài 2 — Session có cookie nhưng user chưa login**

Một browser mở `/login` và được cấp cookie `SESSION` do CSRF token. Browser tiếp tục gọi `/private` mà không gửi credential. Có được vào trang không?

**Đáp án:** Không. Session đã start không đồng nghĩa có `Authentication` đã xác thực. Authorization vẫn yêu cầu login.

**Bài 3 — Save và load dùng hai chiến lược trái nhau**

Bạn cấu hình form login dùng `WebSessionServerSecurityContextRepository` để save nhưng `ServerHttpSecurity.securityContextRepository(NoOpServerSecurityContextRepository.getInstance())` để load. POST login trả 302 nhưng GET /private kế tiếp lại chuyển /login. Vì sao?

**Đáp án:** Login đã lưu context nhưng `ReactorContextWebFilter` không đọc nó ở request sau. Dùng strategy load/save tương thích và test HTTP cookie continuity.

**Bài 4 — NoOp có đủ bảo đảm không tạo session?**

Thay cả load/save security repo bằng no-op. Tuy nhiên controller `GET /cart` ghi attribute cart vào WebSession. Có thể xuất hiện session cookie không?

**Đáp án:** Có. NoOp chỉ điều khiển persistence của `SecurityContext`. Controller vẫn có thể start WebSession; muốn tránh session cần xem toàn bộ pipeline.

**Bài 5 — Form login cần redirect về URL cũ**

Một user chưa login mở `/private`, request cache lưu URI vào WebSession, rồi chuyển `/login`. Nếu tắt request cache vì muốn “không tạo session trước login” thì gì thay đổi?

**Đáp án:** Browser có thể không quay về `/private` sau login mà về landing page do success handler chọn. Cần đánh đổi UX và state, không tắt request cache tùy tiện.

**Bài 6 — Cách kiểm thử lưu identity giữa hai HTTP request**

Một test gọi `POST /login` với credential hợp lệ, thấy 302, rồi kết thúc. Đã đủ chứng minh lưu session context chưa?

**Đáp án:** Chưa. Phải lấy session cookie **sau login**, gửi GET `/private` mới chỉ với cookie đó, xác minh 200 và username đúng. Kiểm tra thêm client không có cookie vẫn bị yêu cầu login.

**Bài 7 — Điều gì xảy ra khi session hết hạn?**

Client vẫn giữ `SESSION` cookie nhưng server-side session đã bị xóa do idle timeout. Request mới đến protected URL sẽ thế nào?

**Đáp án:** Không còn context để khôi phục; client thường trở thành anonymous và bị entry point yêu cầu xác thực lại (form login có thể redirect). Giữ cookie cũ không phục hồi session đã hết hạn.

**Bài 8 — Tại sao cần đổi session ID khi login?**

**Đáp án:** Để giảm rủi ro session fixation: attacker biết một session ID trước khi user đăng nhập và cố tái sử dụng nó sau login. Repository WebSession của Spring Security có cơ chế đổi ID khi save context; test/client phải tiếp tục với cookie sau login.

**Bài 9 — Chọn thiết kế cho API máy gọi máy**

API nhận Bearer JWT mỗi request, không có browser form login. Có cần lưu security context vào WebSession giữa request không?

**Đáp án:** Thường không. Xác minh JWT đúng ở từng request, dùng no-op security context persistence khi phù hợp; đồng thời kiểm tra request cache, CSRF, app state và các filter khác. Stateless không có nghĩa bỏ authorization, expiry, signature validation hay audit.

## 13. Checklist vận hành

- [ ] Stack inbound thực là WebFlux; dùng `ServerHttpSecurity` và `ServerSecurityContextRepository`, không nhầm Servlet.
- [ ] Security context được lưu theo cơ chế xác thực phù hợp: form login cần read/save nhất quán.
- [ ] Không coi `WebSession` object hay session cookie là bằng chứng user đã xác thực.
- [ ] Chỉ start session khi có state đáng lưu; cân nhắc tác động của CSRF/request cache/login.
- [ ] Public endpoints không vô tình tạo session hàng loạt do filter hoặc app attribute.
- [ ] Với API stateless, kiểm tra **toàn bộ** pipeline thay vì chỉ thêm `NoOpServerSecurityContextRepository`.
- [ ] Browser POST login/logout/state-changing có CSRF protection đúng.
- [ ] HTTPS/TLS, cookie Secure/HttpOnly/SameSite/Path/Domain/timeout phù hợp môi trường.
- [ ] Session fixation protection, ID rotation và logout invalidation đã được kiểm thử.
- [ ] Không lưu/password/secret/session ID vào logs, traces, URL hay response không cần thiết.
- [ ] Hệ thống nhiều instance có shared session store/failover strategy phù hợp, hoặc kiến trúc stateless thực sự.
- [ ] Test cả request trước login, sau login với cookie, không cookie, logout, timeout và thiếu role.
- [ ] Đo session creation rate, active sessions, storage footprint và bất thường theo IP/tenant.
- [ ] Mọi thao tác reactive repository (`save`, `invalidate`) được return/compose, không tự `subscribe()`.

## 14. Tóm tắt nhớ nhanh

```text
GET public mới
  exchange.getSession() -> WebSession object (có thể isStarted=false)
  chỉ đọc -> không bắt buộc có session cookie

CẦN STATE:
  session.start() HOẶC thêm session attribute
  -> WebSession started -> session manager lưu state/cookie

FORM LOGIN:
  Authentication success
  -> WebSessionServerSecurityContextRepository.save(...)
  -> SecurityContext vào WebSession, session ID được đổi để chống fixation

REQUEST SAU:
  Cookie/session hợp lệ -> repository.load(...)
  -> ReactorContextWebFilter -> ReactiveSecurityContextHolder
  -> AuthorizationWebFilter -> handler

STATELESS:
  NoOpServerSecurityContextRepository không lưu/nạp SecurityContext
  NHƯNG không tự ngăn CSRF/request cache/app tạo WebSession

LOGOUT / EXPIRE:
  session context không còn -> request protected cần auth lại
```

**Hai ranh giới cần nhớ:** (1) `Reactor Context` thuộc **request subscription**, còn `WebSession` và `ServerSecurityContextRepository` giữ trạng thái **giữa các HTTP request**; (2) “có WebSession object” khác “session đã started”, và “có session” khác “user đã authenticated”.

## 15. Tài liệu chính thức

- [Spring Framework — WebSession API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/server/WebSession.html)
- [Spring Framework — DefaultWebSessionManager API](https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/web/server/session/DefaultWebSessionManager.html)
- [Spring Security — WebSessionServerSecurityContextRepository API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/context/WebSessionServerSecurityContextRepository.html)
- [Spring Security — ServerSecurityContextRepository API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/context/ServerSecurityContextRepository.html)
- [Spring Security — NoOpServerSecurityContextRepository API](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/web/server/context/NoOpServerSecurityContextRepository.html)
- [Spring Security — ServerHttpSecurity API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.html)
- [Spring Security — FormLoginSpec API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.FormLoginSpec.html)
- [Spring Security — WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html)
- [Spring Security — WebFlux CSRF](https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html)
- [Spring Security — WebFlux Test](https://docs.spring.io/spring-security/reference/reactive/test/web/)
- [Spring Boot 3.4 — Reactive session/cookie application properties](https://docs.spring.io/spring-boot/3.4/appendix/application-properties/)
- [Spring Boot — Spring Session Reactive](https://docs.spring.io/spring-boot/3.4/reference/web/spring-session.html)
