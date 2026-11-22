# ServerSecurityContextRepository và vòng đời lưu, nạp ngữ cảnh trong Spring Security WebFlux

## Mục tiêu bài học

Trong ứng dụng **Spring Security - reactive**, người dùng đăng nhập thành công tại một request nhưng vẫn cần được nhận diện ở các request tiếp theo. `ServerSecurityContextRepository` giải quyết **lưu và nạp SecurityContext qua các yêu cầu HTTP**. Bài học thuộc nhóm **Ngữ cảnh bảo mật** và tập trung vào WebFlux, Reactor cùng vòng đời xác thực.

Sau bài này, bạn có thể:

1. Giải thích chính xác `ServerSecurityContextRepository.load(exchange)` và `save(exchange, context)`.
2. Phân biệt **Reactor Context trong một subscription** với **SecurityContext được lưu giữa nhiều request**.
3. Theo dõi flow chưa đăng nhập → form login → lưu WebSession → gửi cookie → load → authorization → logout.
4. Đánh giá `WebSessionServerSecurityContextRepository` và `NoOpServerSecurityContextRepository` theo loại ứng dụng.
5. Cấu hình nhất quán repository cho **đường nạp** và **đường lưu** của authentication filter.
6. Xây dựng ví dụ Java 17+ với Spring Boot 3.3.13, kiểm tra request có/không có session và phát hiện lỗi persistence.

> Tài liệu sử dụng các API thuộc `org.springframework.security.web.server.*` (WebFlux). Không nhầm với `SecurityContextRepository`, `HttpSessionSecurityContextRepository` hoặc `SecurityContextPersistenceFilter` của Servlet.

## 1. SecurityContext giữ dữ liệu gì?

`SecurityContext` là đối tượng chứa một `Authentication`. `Authentication` mô tả principal, authorities, trạng thái xác thực cùng một số thông tin liên quan.

```text
SecurityContext
  |
  +-- Authentication
        |
        +-- Principal (user, token subject, UserDetails...)
        +-- Authorities (ROLE_USER, SCOPE_read...)
        +-- authenticated (trạng thái xác thực)
        +-- details / credentials tùy implementation
```

Các khái niệm nên tách bạch:

| Thành phần | Trách nhiệm |
| --- | --- |
| `SecurityContext` | Trạng thái bảo mật, trong đó chứa `Authentication` |
| `ReactiveSecurityContextHolder` | API để đọc/đặt context trong **Reactor Context của pipeline** |
| `ServerSecurityContextRepository` | Chiến lược **lưu và tìm lại** SecurityContext gắn với `ServerWebExchange` |
| `WebSession` | Session của WebFlux, có thể giữ SecurityContext và những thuộc tính khác |
| Session cookie | Mang **định danh session**, giúp server tìm lại session; không tự chứa toàn bộ Authentication |
| `ReactiveAuthenticationManager` | Xác thực credentials/token và phát một `Authentication` đã xác thực khi thành công |
| `ReactiveAuthorizationManager` | Ra quyết định quyền đối với tài nguyên; không thay thế lưu/nạp context |

**Hai cấp vòng đời khác nhau:** Reactor Context đi theo chuỗi publisher/subscriber của **một request**; repository có thể cho phép request **sau** dựng lại context từ dữ liệu đã lưu. Dùng `ReactiveSecurityContextHolder.withAuthentication(auth)` không tự ghi `auth` vào WebSession.

Khác với Servlet thường dựa vào `ThreadLocal` của `SecurityContextHolder`, WebFlux có thể chuyển execution sang nhiều thread. Khi đọc security context trong xử lý reactive, ưu tiên `ReactiveSecurityContextHolder.getContext()` hoặc API principal do framework truyền qua pipeline, thay vì giả định ThreadLocal luôn giữ danh tính.

## 2. Hợp đồng của ServerSecurityContextRepository

API định nghĩa:

```java
// Chữ ký biểu diễn hợp đồng chính; annotation nullable
// có thể khác tùy phiên bản Spring Security.
public interface ServerSecurityContextRepository {

    Mono<Void> save(
            ServerWebExchange exchange,
            SecurityContext context);

    Mono<SecurityContext> load(ServerWebExchange exchange);
}
```

`ServerWebExchange` chứa request, response, attributes và đường tới `WebSession`, giúp repository liên hệ context với một HTTP exchange.

### 2.1. Ý nghĩa của load

| Kết quả `load(exchange)` | Diễn giải đúng |
| --- | --- |
| `Mono.just(securityContext)` | Repository tìm thấy context cho exchange |
| `Mono.empty()` | Không có context đã lưu để phục hồi; không phát giá trị `null` |
| `Mono.error(error)` | Lỗi truy xuất/lấy lại context; có thể là sự cố của backend session |

`Mono.empty()` **không** phải quyết định `deny` và càng không phải `allow`. Sau đó authentication filter có thể xác thực credentials trong request; nếu không có authentication thì authorization hoặc entry point mới quyết định có redirect, challenge, từ chối hay không.

Một context được load cũng **không tự cấp quyền**: authorization vẫn kiểm tra trạng thái authentication và authorities theo policy.

### 2.2. Ý nghĩa của save

`save(exchange, context)` trả `Mono<Void>`: luồng hoàn tất bình thường là tín hiệu thao tác lưu đã hoàn tất theo hợp đồng repository, lỗi dùng `onError`. `Mono<Void>` không cần phát `onNext`.

Vì Reactor thường lazy, đoạn dưới đây **chưa bảo đảm thực hiện lưu**:

```java
repository.save(exchange, context); // Không subscribe/compose.
```

Phải ghép thao tác vào pipeline:

```java
// Mảnh minh họa bên trong authentication flow tùy biến;
// repository, exchange và authenticated là biến có sẵn.
SecurityContext context = new SecurityContextImpl(authenticated);

return repository.save(exchange, context)
        .thenReturn(authenticated);
```

`thenReturn` phát kết quả sau khi `save` hoàn tất. Nếu save lỗi, lỗi không bị che giấu. Không nên tạo một `subscribe()` độc lập trong WebFilter hoặc gọi `block()` trên event-loop chỉ để lưu context. Với Spring Security chuẩn, hãy dùng `AuthenticationWebFilter` và cơ chế cấu hình đã có.

## 3. Load diễn ra như thế nào trong một request?

```text
Browser gửi GET /me + session cookie
        |
        v
Spring WebFlux WebFilter pipeline
        |
        v
WebFilterChainProxy -> SecurityWebFilterChain được chọn
        |
        v
ReactorContextWebFilter
        |
        +-- ServerSecurityContextRepository.load(exchange)
        |        |
        |        +-- có context -> truyền vào Reactor Context
        |        +-- empty       -> không khôi phục authentication từ repo
        |        +-- error       -> lỗi truy xuất phải được xử lý
        |
        v
Authentication/Authorization WebFilter
        |
        v
Handler đọc ReactiveSecurityContextHolder khi được phép
        |
        v
Response
```

`ReactorContextWebFilter` sử dụng repository để khởi tạo `ReactiveSecurityContextHolder` cho downstream. Đây là flow **reactive**: thao tác load được đánh giá theo subscription và cách downstream sử dụng context; đừng mặc định nó là một truy vấn đồng bộ xảy ra tuyệt đối ngay đầu request.

`SecurityContextServerWebExchangeWebFilter` là filter liên quan: nó điều chỉnh cách `ServerWebExchange.getPrincipal()` tìm principal qua ReactiveSecurityContextHolder. Nhờ đó handler WebFlux có thể nhận `Principal` hoặc lấy authentication từ API reactive khi chain đã thiết lập context.

Nếu load empty, người dùng có thể vẫn được xác thực bằng HTTP Basic hoặc Bearer token có trong chính request. **Load không phải toàn bộ authentication process.**

## 4. Save diễn ra như thế nào khi đăng nhập?

```text
POST /login + username/password + CSRF token hợp lệ
       |
       v
AuthenticationWebFilter (form login)
       |
       +-- chuyển request thành Authentication chưa xác thực
       +-- ReactiveAuthenticationManager xác thực
       |
       +-- nếu thành công:
       |       SecurityContextImpl(Authentication đã xác thực)
       |                 |
       |                 v
       |       repository.save(exchange, securityContext)
       |                 |
       |                 +-- WebSession: lưu vào session
       |                 +-- NoOp: không giữ giữa các request
       |                 |
       |                 v
       |       authentication success handler/redirect
       |
       +-- nếu thất bại:
               failure handler, không tạo đăng nhập thành công
```

Sau khi form login lưu vào `WebSession`, response có thể cập nhật cookie với session ID hiện hành. Browser cần gửi lại cookie đó ở request kế tiếp. Ở request sau, load theo WebSession tìm lại context, rồi handler nhận được principal.

**Một điểm API rất dễ bỏ sót:** `ServerHttpSecurity.securityContextRepository(repository)` chủ yếu chọn repository mà `ReactorContextWebFilter` dùng **để load**. Javadoc nói rõ việc **save được cấu hình theo từng AuthenticationWebFilter**. Với form login, dùng `FormLoginSpec.securityContextRepository(...)` hoặc xác nhận default của phiên bản; với HTTP Basic và filter tùy biến, cũng kiểm tra cơ chế save riêng.

```java
// Mảnh cấu hình trong SecurityWebFilterChain, dùng cùng một repo:
return http
        .securityContextRepository(repository)           // LOAD
        .formLogin(login ->
            login.securityContextRepository(repository)) // SAVE
        .build();
```

Nếu form login lưu vào WebSession còn load dùng NoOp, request POST có thể thành công nhưng request GET sau lại chưa đăng nhập. Ngược lại, nếu load dùng WebSession nhưng form filter save bằng NoOp thì cũng không có context mới để phục hồi.

## 5. Các repository có sẵn

| Repository | Khi load | Khi save | Sử dụng điển hình |
| --- | --- | --- | --- |
| `WebSessionServerSecurityContextRepository` | Lấy SecurityContext từ WebSession; không thấy thì empty | Lưu context thành thuộc tính WebSession | Web UI/form login cần duy trì đăng nhập |
| `NoOpServerSecurityContextRepository` | Không load context đã lưu | Không lưu context | API xác thực mỗi request bằng token/credentials |
| Repository tự viết | Phụ thuộc implementation, có thể dùng distributed store | Phải bảo đảm atomicity/lifecycle/error semantics | Hợp đồng persistence đặc thù; chỉ làm khi thật cần |

### 5.1. WebSessionServerSecurityContextRepository

Class `org.springframework.security.web.server.context.WebSessionServerSecurityContextRepository` dùng một thuộc tính trong `WebSession`. Nó cung cấp `DEFAULT_SPRING_SECURITY_CONTEXT_ATTR_NAME` và `setSpringSecurityContextAttrName(...)`; `setCacheSecurityContext(boolean)` có thể cache kết quả load trong trường hợp cần tránh lookup lặp.

Theo API chính thức, **mỗi lần lưu SecurityContext, session ID được thay đổi để chống session fixation**. Vì vậy ID dùng trước xác thực và ID sau xác thực có thể khác nhau. Khi viết integration test cần nhận và gửi **cookie mới** của response đăng nhập.

WebSession không phải lưu trữ vĩnh viễn: timeout, invalidation, backend storage, restart hay load balancing đều có thể tác động. Nếu hệ thống nhiều node, hãy thiết kế session store chia sẻ đúng yêu cầu (chẳng hạn Spring Session và Redis) và kiểm thử logout/expiration. Cookie phải được bảo vệ bằng HTTPS, Secure, HttpOnly, SameSite đúng mô hình và không đưa session ID vào log.

### 5.2. NoOpServerSecurityContextRepository

`NoOpServerSecurityContextRepository.getInstance()` luôn biểu diễn chiến lược **không lưu/nạp SecurityContext**. Một request mang Bearer token hợp lệ vẫn có thể được xác thực và ủy quyền **trong chính request ấy**, do token được xử lý tại authentication filter. Nhưng request tiếp theo không gửi credentials thì không thể “kế thừa” context từ NoOp.

```text
Request #1: Authorization: Bearer <token-hợp-lệ>
   -> verify token -> Authentication cho request #1
   -> NoOp.save: không lưu giữa requests

Request #2: không gửi token
   -> NoOp.load: empty
   -> không có Authentication từ request #1
   -> endpoint bảo vệ đòi authentication mới
```

NoOp **không tự tắt mọi WebSession**: một thành phần khác, ví dụ CSRF token repository hoặc request cache, vẫn có thể dùng session. Nó chỉ điều khiển persistence của **SecurityContext**, không giải quyết cấu hình JWT, refresh token, CSRF hay cookie.

### 5.3. Không đánh đồng các interface tương tự

- `SecurityContextRepository` của Servlet làm việc với request/response Servlet và có contract khác.
- `ServerCsrfTokenRepository` lưu **CSRF token**, không phải SecurityContext.
- `ServerSecurityContextRepository` không thay thế `ReactiveAuthenticationManager` và cũng không tự quyết định 401/403.
- `WebSession` là hạ tầng session, có thể chứa nhiều dữ liệu hơn context.
- `ReactiveSecurityContextHolder` truyền context qua Reactor Context của subscription, không phải một kho dữ liệu lâu dài.

## 6. Ví dụ hoàn chỉnh: Spring Boot 3.3.13, Java 17+ và form login

Ví dụ này dùng **một SecurityWebFilterChain** để tập trung vào lifecycle. Người dùng `alice` truy cập `/me` sau khi đăng nhập bằng form. Browser gửi lại session cookie ở request mới, repository load lại Authentication.

### 6.1. Tạo dự án Gradle

Cấu trúc:

```text
security-context-demo/
  settings.gradle
  build.gradle
  src/main/java/example/SecurityContextDemoApplication.java
  src/test/java/example/SecurityContextDemoApplicationTests.java
```

`settings.gradle`:

```groovy
rootProject.name = 'security-context-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'example'
version = '0.0.1-SNAPSHOT'

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
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Boot BOM quản lý phiên bản tương thích của Spring Security, Spring Framework và Reactor. Không trộn cấu hình Servlet `HttpSecurity` với WebFlux `ServerHttpSecurity`.

### 6.2. SecurityContextDemoApplication.java

```java
package example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.MediaType;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.context.WebSessionServerSecurityContextRepository;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@SpringBootApplication
@EnableWebFluxSecurity
@RestController
public class SecurityContextDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(SecurityContextDemoApplication.class, args);
    }

    @GetMapping("/")
    public String index() {
        return "Visit /login, then /me";
    }

    @GetMapping("/public/ping")
    public String ping() {
        return "PONG";
    }

    @GetMapping(value = "/me", produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> me() {
        return ReactiveSecurityContextHolder.getContext()
                .map(SecurityContext::getAuthentication)
                .map(Authentication::getName)
                .map(name -> "AUTHENTICATED:" + name);
    }

    @Bean
    WebSessionServerSecurityContextRepository contextRepository() {
        return new WebSessionServerSecurityContextRepository();
    }

    @Bean
    SecurityWebFilterChain securityChain(
            ServerHttpSecurity http,
            WebSessionServerSecurityContextRepository contextRepository) {

        return http
                // Nạp context cho request hiện tại:
                .securityContextRepository(contextRepository)
                .authorizeExchange(ex -> ex
                        .pathMatchers("/", "/login", "/public/**")
                        .permitAll()
                        .anyExchange().authenticated())
                // Lưu context sau khi xác thực bằng form thành công:
                .formLogin(form -> form
                        .securityContextRepository(contextRepository))
                .httpBasic(basic -> basic.disable())
                // CSRF mặc định vẫn bật.
                .build();
    }

    @Bean
    MapReactiveUserDetailsService users() {
        UserDetails alice = User.withUsername("alice")
                .password("{noop}learn")
                .roles("USER")
                .build();
        return new MapReactiveUserDetailsService(alice);
    }
}
```

**Giải thích:**

1. `contextRepository()` tạo instance repository lưu SecurityContext trong WebSession. Cả load lẫn save trong form login dùng **cùng instance**.
2. `.securityContextRepository(contextRepository)` định cấu hình nạp; `formLogin(...securityContextRepository(...))` định cấu hình lưu của login filter.
3. `/me` chỉ được truy cập khi đã xác thực và lấy username từ **ReactiveSecurityContextHolder** tại request đang chạy.
4. `GET /login` dùng trang form mặc định do Spring Security cung cấp, có luồng CSRF phù hợp. `POST /login` do security filter xử lý; không cần tự viết controller.
5. `{noop}learn` chỉ phù hợp **demo cục bộ**; production phải mã hóa mật khẩu, bảo mật cookie/session và dùng HTTPS.
6. HTTP Basic bị tắt để request không có context dùng giao diện đăng nhập thay vì HTTP Basic challenge.

### 6.3. Chạy và kiểm chứng

Yêu cầu JDK 17+ và Gradle tương thích với plugin:

```bash
gradle bootRun
```

Nếu có Gradle Wrapper: `./gradlew bootRun` trên Linux/macOS hoặc `gradlew.bat bootRun` trên Windows.

Quan sát trong browser:

1. Mở `http://localhost:8080/public/ping` → HTTP 200, body chính xác **`PONG`**.
2. Mở `http://localhost:8080/me` khi chưa đăng nhập → được chuyển sang form login (`/login`).
3. Đăng nhập với username **`alice`**, password **`learn`**. Trình duyệt gửi cookie phiên và CSRF token tương ứng.
4. Mở lại `http://localhost:8080/me` → HTTP 200, body:

```text
AUTHENTICATED:alice
```

5. Refresh `/me` → vẫn thấy `AUTHENTICATED:alice` khi session còn hợp lệ.
6. Mở cửa sổ private/incognito không dùng cùng cookie, truy cập `/me` → lại phải đăng nhập. Đó là request không tìm được context đã lưu cho session tương ứng.

Thao tác Refresh quan trọng: nó tạo **một request HTTP mới**; việc handler thấy `alice` cho thấy client mang cookie hiện hành và load đã phục hồi context. Việc chỉ kiểm tra POST login thành công **chưa chứng minh** có persistence liên request.

### 6.4. Lưu ý CSRF khi kiểm thử bằng curl

Với mặc định CSRF bật, lệnh sau có thể nhận **403**:

```bash
curl -i -X POST -d "username=alice&password=learn" \
  http://localhost:8080/login
```

Nguyên nhân là request thiếu CSRF token/session tương ứng, không nhất thiết do username sai hay repository không save. Muốn đăng nhập bằng script HTTP, cần GET trang login để lấy CSRF token, giữ cookie và gửi **cả token lẫn cookie** trong POST. Browser xử lý việc này trong flow form mặc định. Đừng tắt CSRF chỉ để làm ví dụ POST ngắn hơn.

## 7. Timeline request: nơi dữ liệu được tạo, lưu và nạp

| Thời điểm | Request | Diễn biến |
| --- | --- | --- |
| T0 | `GET /me` không cookie | Repo không khôi phục được context; entry point chuyển tới login |
| T1 | `GET /login` | Trang form và CSRF token được chuẩn bị theo cấu hình |
| T2 | `POST /login` đúng credentials + CSRF | Authentication thành công, tạo context, save vào WebSession; có thể đổi session ID |
| T3 | Redirect hoặc `GET /me` với cookie mới | load khôi phục context, authorization cho phép, handler thấy principal `alice` |
| T4 | `GET /me` với cookie hết hạn/không có cookie | Không tìm được context từ session; cần login lại |
| T5 | Logout được xử lý với CSRF thích hợp | Framework xóa/invalidate context theo logout handler và repository |
| T6 | `GET /me` sau logout | Context cũ không còn được khôi phục, endpoint yêu cầu xác thực |

Các phần như request cache, redirect URL, cách tạo session và cookie có thể thay đổi theo cấu hình. **Không phải request public nào cũng tạo WebSession**, dù một thành phần CSRF hoặc request cache có thể làm xuất hiện session.

### Khi save lỗi

Repository có thể phát `Mono.error(...)` vì sự cố storage. Trên flow tự viết, không được báo thành công rồi bỏ qua lỗi; phải compose save và xử lý lỗi trước khi xác nhận persistence. Trong framework, kết quả HTTP cụ thể phụ thuộc authentication/error handlers.

### Khi load lỗi

`load` thất bại do storage không đồng nghĩa người dùng bị từ chối nghiệp vụ. Không dùng `onErrorReturn(true)` hoặc biến lỗi tùy tiện thành context đã xác thực. Phân biệt rõ **lỗi hạ tầng**, **context absent** và **authorization DENY** trong observability và test.

## 8. Reactor Context không phải session storage

Hãy nhìn hai cơ chế song song:

```text
Trong cùng một subscription:
  Authentication
    -> SecurityContext
    -> ReactiveSecurityContextHolder
    -> downstream operators/handler
    -> request kết thúc

Giữa các requests:
  POST /login
    -> repository.save(exchange, context)
    -> WebSession storage / session cookie
    -> GET /me request mới
    -> repository.load(exchange)
    -> ReactiveSecurityContextHolder
    -> authorization/handler
```

Bạn có thể cung cấp context cho **một publisher**:

```java
// Mảnh code minh họa; authentication là giá trị có sẵn.
Mono<String> currentName =
        ReactiveSecurityContextHolder.getContext()
                .map(SecurityContext::getAuthentication)
                .map(Authentication::getName);

Mono<String> scopedPublisher = currentName.contextWrite(
        ReactiveSecurityContextHolder.withAuthentication(authentication));
```

Khi subscribe `scopedPublisher`, nó có context ở phạm vi subscriber phù hợp. Nhưng **không có thao tác save** nào xảy ra chỉ vì dùng `contextWrite`. Request kế tiếp không kế thừa tự động.

Ngược lại, chỉ gọi `repository.save(...)` không nhất thiết làm context xuất hiện trong Reactor Context hiện tại nếu bạn tự viết custom filter sai cách. Đường **persistence** và đường **truyền context nội bộ** là hai phần trách nhiệm riêng; authentication filter chuẩn của Spring Security nối chúng trong flow hợp lệ.

## 9. Chọn chiến lược cho API và UI

Giả sử một hệ thống vừa có UI đăng nhập form, vừa có REST API gọi bằng Bearer token:

| Nhóm | Repository thường phù hợp | Giải thích |
| --- | --- | --- |
| UI form login và session cookie | `WebSessionServerSecurityContextRepository` | Đăng nhập một lần, load lại context ở request tiếp theo |
| REST Bearer token ở header mỗi request | `NoOpServerSecurityContextRepository` | Token được gửi và xác thực lại từng request; không cần lưu context từ request trước |
| REST API dùng session cookie của browser | Có thể cần WebSession và CSRF | JSON/REST không tự biến cookie-based auth thành stateless |
| Nhiều instance cần session chia sẻ | WebSession + backing store phù hợp | Bảo đảm persistence qua node theo chính sách vận hành |

Mảnh cấu hình NoOp cho đường load:

```java
import org.springframework.security.web.server.context.NoOpServerSecurityContextRepository;

ServerSecurityContextRepository noOp =
        NoOpServerSecurityContextRepository.getInstance();

http.securityContextRepository(noOp);
```

**Đây chỉ là mảnh cấu hình**, chưa phải ứng dụng chạy được: cần khai báo loại `ServerSecurityContextRepository` và chuẩn bị `http`. Đối với custom `AuthenticationWebFilter`, repository dùng khi save được chọn bằng:

```java
AuthenticationWebFilter authenticationFilter =
        new AuthenticationWebFilter(authenticationManager);

authenticationFilter.setSecurityContextRepository(
        NoOpServerSecurityContextRepository.getInstance());
```

Các đoạn này cần một `ReactiveAuthenticationManager`, converter và matcher thích hợp. Nếu dùng `oauth2ResourceServer(...)`, Spring Security tự cấu hình các filter tương ứng; cần kiểm tra save behavior của chính cơ chế Resource Server. **Đừng hiểu chỉ `http.securityContextRepository(noOp)` bảo đảm mọi authentication filter tự sử dụng NoOp khi save.**

Với nhiều `SecurityWebFilterChain`, mỗi chain có thể có matcher, mechanism và repository khác nhau. Ví dụ `/api/**` dùng Bearer/NoOp, còn chain UI mặc định dùng WebSession/form login. Nếu không cấu hình cẩn thận, API có thể nhận authentication từ cookie session của UI ngoài dự kiến, hoặc UI mất đăng nhập sau redirect. Cần test ranh giới chain, session và credentials.

## 10. Logout, session invalidation và token revocation

Đăng xuất cần xử lý **context đã lưu**, không chỉ trả redirect hoặc xóa trạng thái ở giao diện. Spring Security WebFlux cung cấp logout filter và `SecurityContextServerLogoutHandler` để xóa security context bằng repository đã cấu hình. Cách xóa có thể gọi `save(exchange, null)` ở API hỗ trợ null và xử lý xóa thuộc tính session; đừng tự gọi với null khi chưa xác minh phiên bản/implementation.

Kết quả mong muốn:

```text
POST /logout + CSRF + cookie hợp lệ
       |
       v
LogoutWebFilter + logout handlers
       |
       v
xóa SecurityContext khỏi repository
       |
       v
Request mới không thể load Authentication cũ
```

Xóa SecurityContext có thể khác với hủy mọi thuộc tính của WebSession. Nếu viết repository tùy biến, phải hỗ trợ **clear/invalidate** nhất quán với logout và ngăn session tiếp tục chứa authentication sau khi đăng xuất. Test bằng request mới sau logout.

Cũng không nên nhầm logout session với **thu hồi Bearer JWT**. Một token tự chứa vẫn có thể hợp lệ cho đến khi hết hạn, trừ khi có cơ chế thu hồi/denylist/rotation phù hợp. NoOp repository không tự thu hồi token.

## 11. Kiểm thử nào thật sự chứng minh save/load?

Cần kiểm thử hành vi xuyên **hai request HTTP thật**:

| Test | Điều kiện | Kết quả cần quan sát |
| --- | --- | --- |
| Chưa login | `GET /me` không cookie | Redirect/challenge; không thấy `AUTHENTICATED:alice` |
| Login thành công | `POST /login` có CSRF + credentials hợp lệ | Authentication success, response/session cookie thích hợp |
| Request mới cùng session | `GET /me` gửi cookie sau login | 200, `AUTHENTICATED:alice` |
| Request mới không cookie | `GET /me` ở session khác | Bị yêu cầu xác thực |
| Login sai mật khẩu | `POST /login` sai credentials | Không tạo context đã xác thực thành công |
| Session hết hạn hoặc bị invalid | `GET /me` với cookie cũ | Không khôi phục context |
| Logout | Logout theo policy, sau đó `GET /me` | Context cũ không còn |
| NoOp | Request 1 có token, request 2 thiếu token | Request 2 không kế thừa authentication |
| Backend lỗi | `load` hoặc `save` phát error | Có xử lý lỗi, không giả làm ALLOW |
| Nhiều chain | UI cookie gửi tới API Bearer-only | API không tự nhận đăng nhập UI ngoài ý định |

### Test JUnit tối thiểu

Tạo `src/test/java/example/SecurityContextDemoApplicationTests.java`:

```java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.boot.test.context.SpringBootTest.WebEnvironment.RANDOM_PORT;

@SpringBootTest(webEnvironment = RANDOM_PORT)
@AutoConfigureWebTestClient
class SecurityContextDemoApplicationTests {

    @Autowired
    WebTestClient client;

    @Test
    void publicRouteIsAccessible() {
        client.get().uri("/public/ping")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("PONG");
    }

    @Test
    void protectedRouteRequiresLogin() {
        client.get().uri("/me")
                .exchange()
                .expectStatus().is3xxRedirection();
    }

    @Test
    void loginPageIsAvailable() {
        client.get().uri("/login")
                .exchange()
                .expectStatus().isOk();
    }
}
```

Chạy:

```bash
gradle test
```

Ba test này xác minh **khởi đầu của flow**, không tự chứng minh persistence. Khi mở rộng integration test với `WebTestClient`, hãy GET login → giữ cookie/CSRF → POST login → giữ cookie **mới** từ response → GET `/me` với cookie mới; không dùng `mockUser` làm bằng chứng lưu/nạp vì mock chỉ gắn principal cho test hiện tại và có thể bypass repository.

### StepVerifier khi xây repository tùy biến

```java
// Mảnh test: repository, exchange và securityContext do test chuẩn bị.
StepVerifier.create(repository.save(exchange, securityContext))
        .verifyComplete();

StepVerifier.create(repository.load(exchange))
        .assertNext(saved -> {
            // So sánh Authentication và authorities theo hợp đồng.
        })
        .verifyComplete();
```

`StepVerifier` thuộc dependency `io.projectreactor:reactor-test` (được Spring Boot starter test quản lý nếu đã có trên classpath; có thể khai báo `testImplementation 'io.projectreactor:reactor-test'` khi cần). Đừng chỉ tạo publisher `save` rồi bỏ qua mà kết luận đã kiểm thử lưu thành công.

## 12. Quan sát lỗi trong thực tế

Triệu chứng **“login thành công nhưng vào trang khác lại bị yêu cầu login”** có thể đến từ nhiều tầng:

1. Login filter có thật sự nhận credentials và xác thực thành công?
2. Filter dùng repository nào cho `save`? Nó có hoàn tất hay lỗi?
3. Client có nhận và gửi lại cookie session ID mới sau khi repository rotate ID?
4. `ReactorContextWebFilter` dùng repository nào để `load`?
5. Backend session có còn dữ liệu, có đúng session ID, timeout, cookie path/domain, node/instance?
6. Handler đọc `ReactiveSecurityContextHolder` đúng subscription hay bị mất context do tự subscribe một luồng khác?
7. Authorization có từ chối vì thiếu authority, dù context vẫn được load thành công?

Bật DEBUG tạm ở môi trường phát triển:

```yaml
logging:
  level:
    org.springframework.security: DEBUG
```

Khi cần kiểm tra sâu, TRACE có thể có nhiều thông tin. **Không ghi log nguyên password, access token, cookie SESSION hoặc toàn bộ SecurityContext**; dùng correlation ID và thông tin tối thiểu (request path, trạng thái load present/empty/error, loại lỗi, kết quả authorization).

**Phân biệt HTTP:** UI dùng form login thường redirect 302 khi cần đăng nhập; API Basic/Bearer thường challenge 401; đã xác thực mà thiếu quyền có thể là 403; lỗi storage có thể dẫn tới phản hồi 5xx. Những con số này phụ thuộc entry point và handler của security chain, không suy trực tiếp từ `Mono.empty()` của repository.

## 13. Những lỗi thường gặp

- **Nhầm load với save:** `http.securityContextRepository(...)` ảnh hưởng đường nạp; save còn được cấu hình theo từng authentication filter.
- **NoOp dùng cho UI cần giữ login:** request POST login thành công nhưng GET request tiếp theo không khôi phục user.
- **Tưởng `contextWrite` là save:** Reactor Context không tự lưu vào WebSession.
- **Tưởng `save` đồng nghĩa đã có context trong publisher hiện hành:** đường persistence và đường context propagation phải được thiết kế đúng.
- **Không subscribe/compose `Mono<Void>`:** lời gọi save chưa chắc được thực thi; không có `onNext` không có nghĩa lỗi.
- **Dùng `block()` trong WebFlux:** làm nghẽn thread xử lý; dùng toán tử Reactor và filter framework.
- **`Mono.empty()` từ load bị hiểu là DENY hoặc ALLOW:** nó chỉ nói không có context được nạp.
- **NoOp bị hiểu là không có WebSession nào:** CSRF, request cache hoặc code khác vẫn có thể tạo session.
- **ThreadLocal `SecurityContextHolder` bị dùng như Servlet:** không phù hợp với flow đổi thread của reactive.
- **Chỉ test mockUser:** bỏ qua persistence/cookie/CSRF thật.
- **Logout chỉ redirect mà không clear repository:** request sau có thể vẫn nhìn thấy principal cũ.
- **Session ID bị cố định:** WebSession repo có cơ chế đổi ID khi lưu nhằm chống session fixation; không giả định cookie không đổi sau login.
- **Nhầm repository của Servlet và WebFlux:** dùng đúng package `org.springframework.security.web.server.context`.
- **Coi 403 CSRF là lỗi repository:** phải kiểm tra CSRF token, session và HTTP method trước.

## 14. Câu hỏi tự kiểm tra

**1. `load(exchange)` trả `Mono.empty()` có nghĩa tài khoản bị khóa?**  
Không. Repo chỉ không tìm thấy context. Policy xác thực/ủy quyền phía sau quyết định tiếp.

**2. Vì sao UI form login cần cả save và load cùng chiến lược?**  
Login lưu context ở request POST; request GET sau dùng repository để nạp lại. Hai đầu không thống nhất thì không phục hồi được authentication.

**3. `ReactiveSecurityContextHolder.withAuthentication(auth)` có làm request sau tự có auth không?**  
Không. Nó gắn context trong Reactor pipeline hiện tại, không lưu vào repository.

**4. NoOp có ngăn một request mang JWT hợp lệ được cấp quyền không?**  
Không. Token được xác thực trong request hiện tại; NoOp chỉ không nhớ context cho request sau.

**5. `save` trả `Mono<Void>` hoàn tất mà không có giá trị; có phải lỗi không?**  
Không. `onComplete` là hoàn tất bình thường. Lỗi dùng `onError`. Phải compose/subscribe publisher đúng.

**6. Sau login, vì sao cookie session có thể thay đổi?**  
`WebSessionServerSecurityContextRepository` thay session ID khi lưu context nhằm hạn chế session fixation. Client cần dùng cookie hiện hành.

**7. Xóa SecurityContext server-side có làm JWT tự hết hiệu lực không?**  
Không. Revocation của token là một vấn đề khác.

**8. Làm sao chứng minh repository thực sự giữ phiên đăng nhập?**  
Thực hiện login có CSRF/cookie hợp lệ, sau đó gửi **request mới** với cookie được server cấp và kiểm tra principal, rồi thử lại không cookie hoặc sau logout.

**Ghi nhớ:** `ServerSecurityContextRepository` quản lý **vòng đời lưu/nạp giữa các HTTP request**; `ReactiveSecurityContextHolder` quản lý **ngữ cảnh trong pipeline**. Tài khoản, session cookie, repo load/save, authentication filter và authorization là những bước khác nhau phải vận hành thống nhất.

## Tài liệu tham khảo

- [Spring Security API — ServerSecurityContextRepository](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/context/ServerSecurityContextRepository.html) — hai phương thức `save` và `load`, kết quả empty.
- [Spring Security API — WebSessionServerSecurityContextRepository](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/context/WebSessionServerSecurityContextRepository.html) — lưu context trong WebSession và đổi session ID.
- [Spring Security API — NoOpServerSecurityContextRepository](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/context/NoOpServerSecurityContextRepository.html) — không lưu và không khôi phục context.
- [Spring Security API — ReactorContextWebFilter](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/context/ReactorContextWebFilter.html) — đưa SecurityContext từ repository vào ReactiveSecurityContextHolder.
- [Spring Security API — ServerHttpSecurity](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.html) — phân biệt repository cho load với save cấu hình theo authentication filter.
- [Spring Security — WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html) — cấu hình form login và SecurityWebFilterChain.
- [Project Reactor — Context](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html) — propagation của Reactor Context.
