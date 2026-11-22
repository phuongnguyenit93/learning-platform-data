# Truy cập người dùng bằng @AuthenticationPrincipal, Principal và ServerWebExchange

> **Bối cảnh:** Spring Boot 3.3, Spring Security 6, Spring WebFlux và Java 17+. Bài này giải thích cách lấy danh tính đã được Spring Security xác thực trong controller reactive, cách chọn `@AuthenticationPrincipal`, `java.security.Principal` hay `ServerWebExchange`, và cách chuyển thông tin đó qua chuỗi `Mono`/`Flux` mà không phụ thuộc vào thread hiện tại.

## 1. Câu hỏi thực tế: ai đang gọi API?

Giả sử người dùng gọi `GET /api/me` cùng HTTP Basic, cookie phiên hoặc bearer token. Controller cần biết **người gọi mà Spring Security đã xác thực**, sau đó trả lại một ít thông tin công khai, hoặc dùng danh tính đó để kiểm tra quyền đọc dữ liệu.

Có ba cách phổ biến trong một controller WebFlux:

```java
// Lấy đối tượng principal bên trong Authentication:
@AuthenticationPrincipal UserDetails user

// Lấy thông tin danh tính tổng quát do WebFlux cung cấp:
Principal principal

// Lấy ngữ cảnh trao đổi HTTP, rồi truy cập principal theo kiểu reactive:
ServerWebExchange exchange
// exchange.getPrincipal() -> Mono<Principal>
```

**Điều kiện tiên quyết:** request phải đi qua chuỗi bảo mật (`SecurityWebFilterChain`) và cơ chế xác thực đã được cấu hình. Việc truyền tên tham số `principal` vào method không tự xác minh token, không tự đăng nhập và không cấp quyền.

### Sơ đồ luồng

```text
HTTP request (Authorization/cookie)
       |
       v
Spring WebFlux: ServerWebExchange
       |
       v
Spring Security WebFilter / SecurityWebFilterChain
       | xác minh credential, tạo Authentication
       | cung cấp SecurityContext trong Reactor Context
       v
@Controller / @RestController
       |-- @AuthenticationPrincipal -> Authentication.getPrincipal()
       |-- Principal                -> tên/danh tính tổng quát
       |-- Mono<Principal>          -> danh tính theo kiểu reactive
       |-- ServerWebExchange        -> exchange.getPrincipal()
       |
       v
Service -> kiểm quyền dữ liệu -> Mono/Flux -> HTTP response
```

Khi request được chấp nhận, các cách truy cập trên có thể cùng đại diện một người dùng, nhưng **kiểu Java và lượng thông tin chúng cung cấp không giống nhau**.

## 2. So sánh ba cách truy cập

| API/Tham số | Giá trị nhận được | Khi nào chọn | Điểm cần nhớ |
|---|---|---|---|
| `@AuthenticationPrincipal UserDetails user` | Giá trị `Authentication.getPrincipal()`, nếu có kiểu phù hợp | Cần đối tượng user đã xác thực trong controller | Kiểu principal phụ thuộc phương thức xác thực, không luôn là `UserDetails` |
| `@AuthenticationPrincipal Jwt jwt` | Đối tượng `Jwt` trong cấu hình JWT resource server phù hợp | Cần claim đã được xác minh từ JWT | Cần cấu hình resource server/JWT thật; không thể dùng ví dụ Basic rồi ép sang `Jwt` |
| `Principal principal` | `java.security.Principal` với `getName()` | Chỉ cần tên/ID thể hiện trong principal | Không đồng nghĩa toàn bộ `Authentication.getPrincipal()`; ít phụ thuộc vào Spring Security |
| `Mono<Principal> principal` | Publisher phát ra principal khi có, hoặc rỗng | Muốn giữ hình thức reactive trong handler | Không `block()`; xử lý bằng `map`/`flatMap` |
| `ServerWebExchange exchange` | Đối tượng trao đổi HTTP; `getPrincipal()` trả `Mono<Principal>` | Ngoài identity còn cần request metadata/response | Không đọc identity từ header tự khai thay cho principal |
| `ReactiveSecurityContextHolder.getContext()` | `Mono<SecurityContext>` trong Reactor Context | Service/operator cần `Authentication` mà không có tham số HTTP | Phụ thuộc Context của subscription; không thay thế kiểm quyền |

**Khác biệt chính:** `@AuthenticationPrincipal` truy cập **principal nằm bên trong đối tượng Authentication**; `Principal` là **đối tượng danh tính ở giao diện Spring WebFlux**, thường chính là một `Authentication` triển khai `Principal`. Nếu muốn chỉ lấy tên, gọi `getName()`. Nếu cần authority, bạn có thể làm việc với `Authentication` một cách có kiểm tra kiểu hoặc truy cập `SecurityContext`.

## 3. Cơ chế bên dưới trong ứng dụng reactive

Spring Security tạo/khôi phục `Authentication` sau khi xác thực. Một `Authentication` có các thành phần thường gặp:

- `getPrincipal()`: đối tượng danh tính (ví dụ `UserDetails` khi đăng nhập username/password, hoặc `Jwt` với JWT resource server cấu hình tương ứng).
- `getName()`: tên thể hiện cho đối tượng xác thực. Ý nghĩa cụ thể có thể là username, subject hoặc tên đã được ánh xạ; **không mặc định là ID số trong database**.
- `getAuthorities()`: tập quyền/authority đã được thiết lập.
- `isAuthenticated()`: trạng thái của Authentication; cần đọc trong bối cảnh chính sách bảo mật và loại token đang dùng, không được tự lấy boolean này làm thay toàn bộ ủy quyền.

Trong WebFlux, Spring Security tích hợp với **Reactor Context**. Các operator reactive có thể đổi thread; vì vậy một đoạn code lấy người dùng bằng `SecurityContextHolder.getContext()` dựa trên ThreadLocal như ứng dụng Servlet không phải cách mặc định đáng tin cho logic WebFlux. Truy cập bằng tham số controller hoặc `ReactiveSecurityContextHolder` phù hợp hơn.

```text
Authentication
  ├─ principal: UserDetails / Jwt / OidcUser / custom user / ...
  ├─ name: "alice" (tùy cơ chế xác thực)
  ├─ authorities: [ROLE_USER, ...]
  └─ credentials, details, trạng thái xác thực

SecurityContext
  └─ Authentication

Reactor Context của request/subscription
  └─ SecurityContext, sẵn để Spring Security reactive truy cập
```

**Không nhầm lẫn hai trường hợp:** API `exchange.getPrincipal()` lấy principal của request theo cơ chế WebFlux, còn `@AuthenticationPrincipal` tách `Authentication.getPrincipal()`. Với username/password mặc định, cả hai thường cho cùng tên nhưng **không phải cùng kiểu đối tượng**.

## 4. Ví dụ đầy đủ: năm cách đọc cùng một danh tính

Mục tiêu: dựng một ứng dụng WebFlux có các endpoint trả về username và tên cách lấy thông tin. Spring Security yêu cầu xác thực cho các endpoint `/api/me/**`, còn `/api/public` đọc được khi chưa đăng nhập. Dùng HTTP Basic chỉ để thử trên localhost, không dùng credential demo cho production.

Cấu trúc:

```text
reactive-principal-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/demo/identity/
    │   ├── IdentityApplication.java
    │   └── SecurityConfiguration.java
    └── test/java/demo/identity/
        └── IdentityApplicationTest.java
```

**settings.gradle**

```groovy
rootProject.name = 'reactive-principal-demo'
```

**build.gradle**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo.identity'
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
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

**src/main/java/demo/identity/SecurityConfiguration.java**

```java
package demo.identity;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration(proxyBeanMethods = false)
public class SecurityConfiguration {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/api/public").permitAll()
                .anyExchange().authenticated())
            .httpBasic(Customizer.withDefaults())
            .formLogin(form -> form.disable())
            .build();
    }
}
```

Giải thích cấu hình:

- `/api/public` là ngoại lệ GET được công khai để minh họa rule.
- Các request còn lại phải xác thực trước khi vào controller.
- `httpBasic(...)` bật xác thực Basic; `formLogin(...disable())` giúp curl không bị chuyển sang trang login HTML khi thử. Với ứng dụng browser có session/form, bạn phải có cấu hình phù hợp riêng.
- Không tắt CSRF chỉ để làm ví dụ GET. Cấu hình chỉ dùng GET nên không cần chỉnh CSRF.
- Không khai báo nguồn người dùng riêng: Spring Boot WebFlux vẫn có thể tạo user phát triển tên `user` và password ngẫu nhiên khi khởi động. Nhận password từ startup log, chỉ thử trên localhost.

**src/main/java/demo/identity/IdentityApplication.java**

```java
package demo.identity;

import java.security.Principal;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;

@SpringBootApplication
@RestController
public class IdentityApplication {

    public static void main(String[] args) {
        SpringApplication.run(IdentityApplication.class, args);
    }

    public record UserView(String username, String source) {}

    @GetMapping("/api/public")
    public Mono<String> publicMessage() {
        return Mono.just("public");
    }

    // 1. Đối tượng nằm trong Authentication.getPrincipal()
    @GetMapping("/api/me/annotation")
    public Mono<UserView> fromAnnotation(
            @AuthenticationPrincipal UserDetails user) {
        return Mono.just(
            new UserView(user.getUsername(), "@AuthenticationPrincipal"));
    }

    // 2. API thuần Java: java.security.Principal
    @GetMapping("/api/me/principal")
    public Mono<UserView> fromPrincipal(Principal principal) {
        return Mono.just(new UserView(principal.getName(), "Principal"));
    }

    // 3. Cùng Principal nhưng truyền vào dưới dạng Mono
    @GetMapping("/api/me/mono")
    public Mono<UserView> fromMono(Mono<Principal> principal) {
        return principal.map(p -> new UserView(p.getName(), "Mono<Principal>"));
    }

    // 4. Lấy Principal từ ServerWebExchange theo kiểu reactive
    @GetMapping("/api/me/exchange")
    public Mono<UserView> fromExchange(ServerWebExchange exchange) {
        return exchange.getPrincipal()
            .map(p -> new UserView(p.getName(), "ServerWebExchange"));
    }

    // 5. Khi cần Authentication trong chuỗi Reactor
    @GetMapping("/api/me/context")
    public Mono<UserView> fromReactorContext() {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(auth -> new UserView(auth.getName(), "Reactor Context"));
    }
}
```

**Tại sao code đúng vai trò của từng API?**

- `fromAnnotation` nhận đối tượng `UserDetails` là principal khi xác thực Basic bằng kho người dùng của Boot. Chúng ta chỉ đọc `getUsername()` và tạo DTO; **không serialize cả UserDetails**, vì nó có các trường nhạy cảm như hashed password.
- `fromPrincipal` dùng `getName()`. Controller không cần biết implementation của cơ chế đăng nhập.
- `fromMono` thể hiện WebFlux hỗ trợ kiểu reactive cho đối số `Principal`; `map` chỉ chạy khi principal xuất hiện.
- `fromExchange` cho thấy `ServerWebExchange.getPrincipal()` trả `Mono<Principal>`. Không có `block()` hoặc `subscribe()` thủ công.
- `fromReactorContext` thể hiện cách đọc `Authentication` từ Reactor Context khi xử lý reactive. Trong controller đơn giản, ba cách đầu dễ đọc hơn; không cần gọi context holder ở mọi endpoint.

Vì route `/api/me/**` đều được yêu cầu xác thực, ví dụ có thể dùng trực tiếp `user.getUsername()` mà không xử lý `null` trong đoạn demo. Nếu chuyển endpoint sang `permitAll()`, phải thiết kế hành vi cho người chưa đăng nhập và principal không tương thích; không được giữ giả định đó.

### Chạy và gọi thử

Cần JDK 17+ và Gradle tương thích với Spring Boot 3.3. Trong thư mục dự án:

```bash
gradle bootRun
```

Nếu có wrapper, có thể dùng `./gradlew bootRun` (Windows: `gradlew.bat bootRun`). Tìm dòng `Using generated security password: ...` ở startup log. Tài khoản mặc định là `user` khi Boot tạo nguồn người dùng in-memory.

Với curl CLI, `-u user` sẽ yêu cầu nhập password trong terminal, tránh chép mật khẩu vào lệnh:

```bash
# Public
curl -i http://localhost:8080/api/public

# Chưa xác thực
curl -i http://localhost:8080/api/me/principal

# Nhập password sinh ở startup log khi được hỏi
curl -i -u user http://localhost:8080/api/me/annotation
curl -i -u user http://localhost:8080/api/me/principal
curl -i -u user http://localhost:8080/api/me/mono
curl -i -u user http://localhost:8080/api/me/exchange
curl -i -u user http://localhost:8080/api/me/context
```

Trên PowerShell, có thể dùng `curl.exe` nếu `curl` đang là alias của lệnh khác.

| Request | Kết quả chính kỳ vọng |
|---|---|
| `GET /api/public` không credential | HTTP 200; body `public` |
| `GET /api/me/principal` không credential | HTTP 401 (do cấu hình Basic, không bật form login) |
| `GET /api/me/annotation` với Basic hợp lệ | HTTP 200; JSON có `username: "user"`, `source: "@AuthenticationPrincipal"` |
| `GET /api/me/principal` với Basic hợp lệ | HTTP 200; `username: "user"`, `source: "Principal"` |
| `GET /api/me/mono` với Basic hợp lệ | HTTP 200; `username: "user"`, `source: "Mono<Principal>"` |
| `GET /api/me/exchange` với Basic hợp lệ | HTTP 200; `username: "user"`, `source: "ServerWebExchange"` |
| `GET /api/me/context` với Basic hợp lệ | HTTP 200; `username: "user"`, `source: "Reactor Context"` |

Ví dụ phản hồi của `GET /api/me/annotation` sau xác thực thành công:

```json
{
  "username": "user",
  "source": "@AuthenticationPrincipal"
}
```

Tên người dùng ở đây là `user` do nguồn user mặc định của Boot; trong hệ thống thật, `principal.getName()` có thể biểu diễn subject hoặc identifier khác.

## 5. `@AuthenticationPrincipal`: lấy đúng kiểu principal

Annotation được import từ:

```java
import org.springframework.security.core.annotation.AuthenticationPrincipal;
```

Ý nghĩa là resolve đối số handler từ `Authentication.getPrincipal()`. Nó không phải một cơ chế xác thực độc lập.

### 5.1 Khi dùng username/password

Với user được tải bằng `ReactiveUserDetailsService`, principal thường là đối tượng triển khai `UserDetails`:

```java
@GetMapping("/api/me/name")
Mono<String> name(@AuthenticationPrincipal UserDetails user) {
    return Mono.just(user.getUsername());
}
```

Đoạn code này **chỉ là method minh họa**, cần đặt vào controller có import tương ứng; không được thêm vào cùng một route đã khai báo trong ví dụ mà không kiểm soát trùng mapping.

Nếu chỉ cần một thuộc tính của principal, có thể dùng SpEL:

```java
@GetMapping("/api/me/username")
Mono<String> username(
        @AuthenticationPrincipal(expression = "username") String username) {
    return Mono.just(username);
}
```

`expression = "username"` hoạt động khi principal thực sự có thuộc tính `username`, như `UserDetails`. Nếu cơ chế xác thực đổi sang JWT hoặc một loại principal khác, biểu thức này không tự ánh xạ thành claim `sub`.

### 5.2 Khi dùng JWT resource server

Một resource server có thể khai báo:

```java
@GetMapping("/api/me/subject")
Mono<String> subject(@AuthenticationPrincipal Jwt jwt) {
    return Mono.just(jwt.getSubject());
}
```

Đây **không phải code độc lập chạy trong demo Basic**. Nó cần `org.springframework.security.oauth2.jwt.Jwt`, dependency `spring-boot-starter-oauth2-resource-server`, cấu hình xác thực JWT hợp lệ (issuer/JWK, validation thích hợp) và một request mang token được chấp nhận. Trong cơ chế JWT resource server mặc định, principal thường là `Jwt`; trong OAuth2 Login, principal có thể là `OAuth2User`/`OidcUser`; trong Basic, thường là `UserDetails`. Không được ép mọi luồng xác thực về cùng một kiểu.

### 5.3 Khi kiểu principal không khớp

Nếu Spring Security không có đối tượng principal thích hợp hoặc không tương thích với kiểu tham số, annotation có thể cho giá trị `null` (mặc định `errorOnInvalidType = false`). Muốn nhận lỗi sai kiểu sớm trong môi trường phát triển, có thể khai báo:

```java
@AuthenticationPrincipal(errorOnInvalidType = true) UserDetails user
```

Tùy chọn này khiến lỗi sai kiểu biểu hiện bằng `ClassCastException`; nó **không tự cấp thêm quyền**, không biến endpoint public thành protected và không thay thế kiểm tra dữ liệu. Với ứng dụng hỗ trợ nhiều kiểu xác thực, cân nhắc kiểu principal phù hợp và viết tầng ánh xạ danh tính rõ ràng.

### 5.4 UserDetails không phải response DTO

Không trả nguyên đối tượng `UserDetails`, `Jwt` hoặc `Authentication` vào JSON phản hồi. Chúng có thể chứa credential, token metadata, claim nhạy cảm hoặc thông tin nội bộ. Dùng DTO chỉ gồm những thuộc tính an toàn và cần cho chức năng hiện tại, như `username` và tên hiển thị.

## 6. `Principal`: lựa chọn nhỏ gọn khi chỉ cần tên

`java.security.Principal` có method chính `getName()`. Đây là giao diện thuộc JDK, không phải một class của Spring Security.

```java
@GetMapping("/api/me/welcome")
Mono<String> welcome(Principal principal) {
    return Mono.just("Xin chào " + principal.getName());
}
```

Đây là **method minh họa**. Spring WebFlux có thể resolve tham số `Principal` trong handler. Nếu handler là public, trường hợp chưa xác thực có thể dẫn đến không có principal; không dựa vào `principal.getName()` khi chưa bảo đảm có danh tính.

### Principal và Authentication

`Authentication` của Spring Security **extends `Principal`**, vì vậy một đối tượng `Authentication` có `getName()` nhưng cũng có `getPrincipal()`, `getAuthorities()` và thông tin khác. Dù trong thực tế Spring Security thường cung cấp `Authentication`, hãy chọn tham số theo nhu cầu:

- Chỉ cần tên để hiển thị: `Principal`.
- Cần thuộc tính cụ thể từ `Authentication.getPrincipal()`: `@AuthenticationPrincipal` với đúng type.
- Cần roles/authorities hoặc xử lý trong pipeline: nhận `Authentication` qua ngữ cảnh bảo mật reactive, hoặc kiểm tra instance nếu đang có `Principal`.

Đoạn minh họa kiểm tra kiểu, **không phải một controller hoàn chỉnh**:

```java
if (principal instanceof Authentication authentication) {
    boolean canRead = authentication.getAuthorities().stream()
        .anyMatch(a -> a.getAuthority().equals("SCOPE_profile.read"));
    // Chỉ là một điều kiện quyền; còn cần kiểm quyền tài nguyên.
}
```

Cần import `org.springframework.security.core.Authentication` và chọn authority phù hợp với cách hệ thống cấp quyền. Một username không tự chứng minh người dùng sở hữu `orderId` hay có quyền trên tenant khác.

### Reactive argument

WebFlux cũng hỗ trợ đối số `Mono<Principal>` trong controller:

```java
@GetMapping("/api/me/async")
Mono<String> async(Mono<Principal> principal) {
    return principal.map(Principal::getName);
}
```

Nếu publisher rỗng, `map` không sinh giá trị; điều này **không có nghĩa tự động trả HTTP 401**. Security chain phải là nơi thực thi chính sách xác thực; trên route cho phép anonymous, handler phải tự định nghĩa phản hồi phù hợp nếu cần.

## 7. `ServerWebExchange`: truy cập thông tin request và principal reactive

`ServerWebExchange` biểu diễn toàn bộ trao đổi HTTP phía WebFlux, gồm request, response, attributes, thông tin session và principal.

```java
@GetMapping("/api/me/from-exchange")
Mono<String> fromExchange(ServerWebExchange exchange) {
    return exchange.getPrincipal()
        .map(Principal::getName);
}
```

**Đặc điểm:**

1. `getPrincipal()` trả `Mono<Principal>` (chính xác hơn là generic `Mono<T extends Principal>` theo API).
2. Dùng `map`/`flatMap`, không gọi `block()` trên event loop.
3. Nếu không có principal, publisher có thể rỗng. Nếu bạn muốn giá trị dự phòng ở một endpoint công khai, có thể dùng `defaultIfEmpty("guest")`, nhưng cần xác định ứng dụng có anonymous authentication hay không và chính sách response tương ứng.
4. `exchange.getRequest().getHeaders()` có thể đọc header HTTP; header tự gửi như `X-User-Id` hoặc `X-Role` **không đáng tin là danh tính đã xác thực**.

Ví dụ **mã sai về bảo mật** (không sử dụng để cấp quyền):

```java
String userId = exchange.getRequest().getHeaders().getFirst("X-User-Id");
// Client có thể tự sửa header này; không dùng làm current authenticated user.
```

Cách đúng là lấy principal từ cơ chế bảo mật, rút ra ID đã được xác minh theo quy ước hệ thống, sau đó kiểm quyền dữ liệu. Chọn `ServerWebExchange` khi controller thật sự cần thêm thông tin HTTP; nếu chỉ cần tên thì `Principal` thường gọn hơn.

## 8. Khi đi vào Service và operator Reactor

### 8.1 Reactor Context và SecurityContext

Trong WebFlux, một chuỗi có thể chạy trên nhiều thread. Spring Security reactive sử dụng Reactor Context để mang `SecurityContext` qua các operator trong cùng chuỗi subscription.

```java
Mono<String> currentUsername() {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName);
}
```

Đây là **method minh họa**, cần imports cho `Mono`, `ReactiveSecurityContextHolder`, `SecurityContext` và `Authentication`. Khi được gọi trong pipeline có context do Spring Security thiết lập, nó đọc tên người dùng đã xác thực. Nếu không có context, publisher có thể rỗng.

Một cách dùng trong service cần chuỗi bất đồng bộ:

```java
Mono<String> loadGreeting() {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .flatMap(auth -> messageRepository.findGreetingByUser(auth.getName()));
}
```

`messageRepository` ở đây là dependency minh họa, cần được định nghĩa riêng; **đoạn code không phải chương trình độc lập**. Trường hợp service đã nhận được user ID xác minh từ controller, truyền ID đó như tham số rõ ràng cũng là một thiết kế tốt, dễ test.

### 8.2 Những điều làm mất/sai ngữ cảnh

- Không dùng `ThreadLocal` tự tạo để nhận biết user trong WebFlux; request có thể đổi thread.
- Không tự `subscribe()` ở giữa service hoặc handler rồi coi tác vụ tách rời vẫn mang đúng SecurityContext và vòng đời request. Hãy **trả Publisher** để framework quản lý subscription.
- `publishOn` và `subscribeOn` **không mặc nhiên xóa Reactor Context**; rủi ro là tách subscription, callback chạy ngoài chuỗi, chuyển sang API khác mà không chủ động truyền dữ liệu ngữ cảnh.
- Không gọi `block()` để lấy principal trong controller/reactive service; chặn event loop có thể làm cạn tài nguyên, gây lỗi khi chặn ở thread non-blocking.
- Nếu phát event sang queue/job nền, không giả định context HTTP của request tồn tại khi consumer chạy sau đó. Truyền dữ liệu danh tính cần thiết ở mức tối thiểu, gắn nguồn đáng tin và kiểm quyền lại ở phía nhận.

### 8.3 Các đường đi phải nhận cùng một danh tính

`@AuthenticationPrincipal` ở controller, `ServerWebExchange.getPrincipal()` và `ReactiveSecurityContextHolder` đều có thể phản ánh cùng phiên xác thực, nhưng nên kiểm thử sự phù hợp theo cơ chế Basic, form login và JWT của hệ thống. Khi authentication bị thay hoặc claim ánh xạ khác, kiểu `principal` hay giá trị `getName()` có thể khác. Không lấy ba kết quả giống nhau trong demo làm cam kết cho mọi cơ chế.

## 9. Danh tính và phân quyền dữ liệu là hai việc khác nhau

Giả sử người dùng A đã đăng nhập và gọi:

```http
GET /api/orders/892
Authorization: Bearer <access-token-of-A>
```

Biết `principal.getName()` là A **không chứng minh** đơn hàng 892 thuộc A. Hãy kiểm quyền đối tượng ở service hoặc repository bằng danh tính/tenant đã xác minh:

```text
currentUser = authenticated principal or verified subject
requestedOrderId = path variable supplied by client

authorization:
  verify currentUser has access to requestedOrderId
  verify tenant boundary and required action

if allowed:
  query/return an approved response DTO
else:
  return 403 or 404 according to the API policy
```

Đây là **pseudocode**, không phải Java runnable. Trong ứng dụng đa tenant, tránh dùng `tenantId` lấy thẳng từ query, JSON body hoặc header client làm bằng chứng quyền; nguồn danh tính và phạm vi quyền phải do hệ thống xác thực và nghiệp vụ kiểm tra.

Không dùng `Principal.getName()` như ID database nếu hệ thống không bảo đảm mapping bền vững. Username có thể đổi; `sub` của JWT có thể không toàn cục giữa nhiều issuer. Nếu cần ID ổn định, xây một lớp ánh xạ từ danh tính đã xác thực (ví dụ issuer + subject) sang ID nội bộ và kiểm soát tenant/authorization.

## 10. Kiểm thử tự động: ba API trả cùng người dùng

Để kiểm thử demo ở mục 4 mà không phụ thuộc vào mật khẩu sinh ngẫu nhiên, test thiết lập account của Boot **chỉ trong test context**. Không triển khai password mẫu vào môi trường thật.

**src/test/java/demo/identity/IdentityApplicationTest.java**

```java
package demo.identity;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
    properties = {
        "spring.security.user.name=alice",
        "spring.security.user.password=test-only-password"
    }
)
@AutoConfigureWebTestClient
class IdentityApplicationTest {

    @Autowired
    WebTestClient client;

    @Test
    void publicEndpointDoesNotRequireLogin() {
        client.get().uri("/api/public")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("public");
    }

    @Test
    void protectedEndpointRejectsAnonymousRequest() {
        client.get().uri("/api/me/principal")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void principalSourcesAgreeOnUsername() {
        for (String path : List.of(
                "/api/me/annotation",
                "/api/me/principal",
                "/api/me/mono",
                "/api/me/exchange",
                "/api/me/context")) {
            client.get().uri(path)
                .headers(headers ->
                    headers.setBasicAuth("alice", "test-only-password"))
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.username").isEqualTo("alice");
        }
    }

    @Test
    void invalidPasswordIsRejected() {
        client.get().uri("/api/me/annotation")
            .headers(headers ->
                headers.setBasicAuth("alice", "invalid-password"))
            .exchange()
            .expectStatus().isUnauthorized();
    }
}
```

Chạy:

```bash
gradle test
```

Kỳ vọng **4 test method PASS** nếu phiên bản Gradle/JDK tương thích và dependency đã được tải. Test thứ ba gửi request qua cả năm cách và kiểm tra giá trị JSON. Test thứ hai xác nhận controller không được dùng làm điểm xác thực: request bị chặn trước khi vào endpoint bảo vệ.

Đây là kiểm thử mức ứng dụng bằng `WebTestClient`, có thể chạy theo cùng cấu trúc `settings.gradle`, `build.gradle` và Java classes ở mục 4. Với dự án dùng JWT/OIDC hay nguồn user riêng, thay test fixture xác thực theo cơ chế tương ứng; không giữ giả định account `alice` do Boot tự tạo.

## 11. Lỗi thường gặp

| Lỗi | Vì sao sai | Cách sửa |
|---|---|---|
| Inject `@AuthenticationPrincipal UserDetails` nhưng ứng dụng dùng JWT | Principal JWT có thể là `Jwt`, không phải `UserDetails` | Dùng kiểu tương ứng với authentication thực tế |
| Tưởng `@AuthenticationPrincipal` làm request được xác thực | Annotation chỉ đọc từ context | Cấu hình `SecurityWebFilterChain` và authentication thật |
| Dùng `Principal.getName()` làm quyền truy cập mọi object | Xác thực chỉ cung cấp danh tính | Kiểm quyền trên object/tenant ở server |
| Lấy `X-User-Id` làm người dùng hiện tại | Client có thể sửa header | Lấy từ principal/context đã xác thực |
| Ép `Principal` sang `UserDetails` không kiểm tra | `Principal` thường là `Authentication`, principal bên trong mới có thể là `UserDetails` | Dùng `@AuthenticationPrincipal` hoặc kiểm tra kiểu rõ ràng |
| Dùng `SecurityContextHolder` ThreadLocal như trong MVC | Reactive execution không gắn cố định một thread | Dùng tham số controller hoặc `ReactiveSecurityContextHolder` |
| Gọi `exchange.getPrincipal().block()` | Chặn pipeline, có thể lỗi trên event loop | Dùng `map`/`flatMap` và trả `Mono` |
| Gọi `subscribe()` thủ công giữa handler | Tạo subscription có vòng đời/ngữ cảnh khó kiểm soát | Trả publisher để framework subscribe |
| Trả thẳng `UserDetails`/`Authentication` thành JSON | Có thể lộ thông tin nhạy cảm | Chỉ trả DTO gồm trường cần thiết |
| Dùng `@AuthenticationPrincipal` trên route public và mặc định non-null | Không chắc có principal/type khớp | Xử lý anonymous/absent principal đúng policy |
| Đồng nhất tên user với ID ổn định | Username/claim có thể đổi hoặc trùng issuer | Định nghĩa ánh xạ danh tính nội bộ |
| Chỉ test request hợp lệ | Không biết policy có bảo vệ URL hay không | Test anonymous, sai credential, sai quyền, sai object |

## 12. Bài tập thực hành

1. Chạy ví dụ `gradle bootRun`, đăng nhập bằng tài khoản phát triển do Boot tạo; so sánh trường `username` từ năm endpoint `/api/me/**`.
2. Đổi `fromAnnotation` sang `@AuthenticationPrincipal(expression = "username") String username` và giải thích vì sao hoạt động khi principal là `UserDetails`.
3. Thử request đến `/api/me/principal` không có credential, ghi nhận `401`. Sau đó xem policy `anyExchange().authenticated()` và lý giải vì sao controller chưa được chạy.
4. Tạo một endpoint public dùng `ServerWebExchange.getPrincipal()` và xử lý trường hợp không có principal bằng một response có chủ đích; đừng mặc định người dùng anonymous có cùng username trên mọi cấu hình.
5. Tạo một route `/api/orders/{id}` chỉ cho phép người dùng sở hữu tài nguyên đọc. Giải thích vì sao xác thực bằng `Principal` chưa đủ; viết test truy cập ID của người khác.
6. Giả sử dự án chuyển từ Basic sang JWT. Liệt kê các chỗ đang giả định `UserDetails` và cần đổi thành `Jwt`/mô hình identity riêng, đồng thời xác minh issuer, audience, signature và scope của token.
7. Thử đưa thao tác đọc context vào một operator `flatMap` rồi thêm `publishOn`; quan sát context không tự biến mất chỉ vì chuyển scheduler. So sánh với việc tự tạo subscription bên ngoài request.

## Ghi nhớ

- `@AuthenticationPrincipal` lấy **đối tượng bên trong** `Authentication.getPrincipal()` và phải dùng đúng type; phù hợp khi cần `UserDetails`, `Jwt` hoặc custom principal.
- `Principal` và `Mono<Principal>` là lựa chọn gọn khi chỉ cần `getName()`; chúng không tương đương ép kiểu tùy tiện sang `UserDetails`.
- `ServerWebExchange` cung cấp principal theo dạng `Mono` cùng thông tin request/response khác; chỉ dùng khi cần ngữ cảnh HTTP.
- Trong service reactive, ưu tiên truyền ID đã xác minh như tham số rõ ràng hoặc đọc `ReactiveSecurityContextHolder` trong đúng Reactor pipeline.
- Danh tính đã xác thực **không thay thế** authorization theo quyền thao tác, đối tượng, tenant hoặc dữ liệu nghiệp vụ.

## Tài liệu chính thức

- Spring Framework — WebFlux annotated controller method arguments (hỗ trợ `Principal`, `Mono<Principal>` và `ServerWebExchange`): https://docs.spring.io/spring-framework/reference/6.1/web/webflux/controller/ann-methods/arguments.html
- Spring Framework — `ServerWebExchange.getPrincipal()`: https://docs.spring.io/spring-framework/docs/6.1.22/javadoc-api/org/springframework/web/server/ServerWebExchange.html
- Spring Security — `@AuthenticationPrincipal`: https://docs.spring.io/spring-security/site/docs/6.3.10/api/org/springframework/security/core/annotation/AuthenticationPrincipal.html
- Spring Security — WebFlux Security Configuration: https://docs.spring.io/spring-security/reference/6.3/reactive/configuration/webflux.html
- Spring Security — Reactive Method Security / Reactor Context: https://docs.spring.io/spring-security/reference/6.3/reactive/authorization/method.html
- Spring Boot — Spring Security for WebFlux: https://docs.spring.io/spring-boot/3.3/reference/web/spring-security.html
