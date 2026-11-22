# Phân quyền theo đường dẫn, HTTP method và biến đường dẫn trong Spring Security WebFlux

> **Phạm vi:** Spring WebFlux + Spring Security 6.x, Spring Boot 3.3.x và Java 17+. Mục tiêu là viết chính sách **phân quyền HTTP reactive** dựa trên đường dẫn, phương thức HTTP và biến URI, hiểu thứ tự đánh giá matcher, kiểm tra chủ sở hữu đơn giản bằng `AuthorizationContext`, rồi chứng minh đúng/sai qua `WebTestClient`. Cú pháp minh họa hướng tới Spring Security 6.x; khi dùng phiên bản mới hơn cần kiểm tra API và cập nhật dependency đã được hỗ trợ, vá bảo mật.

## 1. Phân biệt authentication và authorization

**Authentication (xác thực)** trả lời “ai đang gọi?”. Ví dụ: server kiểm tra HTTP Basic, form login hoặc JWT rồi tạo `Authentication`. **Authorization (phân quyền)** trả lời “request đã xác thực được phép thực hiện việc này không?”. Trong WebFlux, Spring Security dùng `SecurityWebFilterChain` để thực thi chính sách trước khi request vào controller.

```text
HTTP request: GET /api/accounts/alice
                 |
                 v
     SecurityWebFilterChain
                 |
       xác thực HTTP Basic/JWT...
                 |
       Authentication: name=alice
                 |
       authorizeExchange()
          +-- so URL/method
          +-- lấy biến path {username}=alice
          +-- quyết định quyền từ Authentication
                 |
            grant / deny
                 |
           @RestController
```

Điều kiện `authenticated()` chỉ chứng minh caller có một danh tính hợp lệ theo cơ chế đã cấu hình; nó **không tự chứng minh caller sở hữu bản ghi** mang ID trong URL. `hasRole("ADMIN")` kiểm quyền được cấp cho người gọi, chứ không phân tích owner của một đơn hàng. Khi cần cả ba trục, hãy thiết kế rule tương ứng và kiểm tra quyền dữ liệu ở tầng nghiệp vụ.

Trong ứng dụng **reactive**:

- Builder: `org.springframework.security.config.web.server.ServerHttpSecurity`.
- Kết quả builder: `org.springframework.security.web.server.SecurityWebFilterChain`.
- Cấu hình request: `authorizeExchange(exchanges -> ...)`.
- Matcher URL/method: `pathMatchers(...)`.
- Manager cho logic riêng: `ReactiveAuthorizationManager<AuthorizationContext>`.
- Thông tin request và biến URI: `org.springframework.security.web.server.authorization.AuthorizationContext`.

**Đừng trộn với Servlet/MVC:** `HttpSecurity`, `SecurityFilterChain` và `authorizeHttpRequests().requestMatchers(...)` là một nhánh API khác. Không copy một ví dụ `RequestAuthorizationContext` của Servlet sang WebFlux và nghĩ nó cùng kiểu.

## 2. Cấu trúc cơ bản: pathMatchers và anyExchange

Một cấu hình WebFlux điển hình:

```java
@Bean
SecurityWebFilterChain security(ServerHttpSecurity http) {
    return http
        .authorizeExchange(exchanges -> exchanges
            .pathMatchers("/public/**").permitAll()
            .pathMatchers("/api/admin/**").hasRole("ADMIN")
            .pathMatchers("/api/**").authenticated()
            .anyExchange().denyAll())
        .httpBasic(Customizer.withDefaults())
        .build();
}
```

**Đây là method bean minh họa**, phải đặt trong lớp `@Configuration` với imports tương ứng; `Customizer` import từ `org.springframework.security.config.Customizer`. Không cần `.and()` khi dùng lambda DSL.

Ý nghĩa:

1. URL trong `/public/**`: cho phép mọi người, kể cả không đăng nhập.
2. URL trong `/api/admin/**`: cần authority `ROLE_ADMIN`.
3. URL còn lại trong `/api/**`: chỉ cần có danh tính được xác thực.
4. Mọi exchange khác: từ chối (fail closed).
5. HTTP Basic được bật bằng `Customizer.withDefaults()` để client gửi credential; nó **không thay thế** bất kỳ rule authorization nào.

Các rule được xét **theo thứ tự khai báo**, rule đầu tiên match sẽ được dùng. Vì vậy phải đặt điều kiện hẹp/chặt trước điều kiện rộng, và fallback `anyExchange()` ở **cuối**.

### Những quyết định thường dùng

| Action | Ý nghĩa | Khi thích hợp |
|---|---|---|
| `permitAll()` | Không yêu cầu xác thực/role cho request match | Health endpoint công khai có chủ đích, public docs |
| `authenticated()` | Yêu cầu user được xác thực thực sự | API nội bộ của user đã login |
| `hasRole("ADMIN")` | Yêu cầu authority `ROLE_ADMIN` theo prefix mặc định | Route quản trị |
| `hasAuthority("SCOPE_reports.read")` | Yêu cầu authority đúng tên được truyền | JWT scope được map thành authority như ví dụ |
| `hasAnyRole("EDITOR", "ADMIN")` | Một trong các role | Endpoint ghi cho nhiều nhóm |
| `denyAll()` | Chặn request match | URL ngoài phạm vi đã liệt kê |
| `access(reactiveManager)` | Áp dụng logic permission tùy chỉnh | So biến path với người dùng, kiểm owner/tenant async |

`hasRole("ADMIN")` không viết `hasRole("ROLE_ADMIN")` khi dùng prefix mặc định; nếu authority của bạn là `"ROLE_ADMIN"`, truyền `"ADMIN"` vào `hasRole`. Với OAuth2/JWT, ánh xạ claim/scope/role phụ thuộc cấu hình; phải kiểm authorities thực tế, không tự suy luận từ token text hay username.

## 3. Phân quyền theo **đường dẫn**

### 3.1 Pattern thường gặp

| Matcher | Đường dẫn minh họa match | Ý nghĩa |
|---|---|---|
| `/api/ping` | `/api/ping` | Đường dẫn cụ thể |
| `/api/accounts/*` | `/api/accounts/alice` | Một segment trong vị trí `*` |
| `/api/accounts/**` | `/api/accounts/alice`, các đường con | Phạm vi nhiều segment; cần cẩn thận khi cấp public |
| `/api/accounts/{username}` | `/api/accounts/alice` | Match segment có tên biến `username` |
| `/api/projects/{projectId}/members` | `/api/projects/42/members` | Matcher có biến nằm giữa |
| `/api/admin/**` | `/api/admin/audit` | Một nhánh route yêu cầu quyền quản trị |

Spring WebFlux và các matcher của Spring Security dựa trên cơ chế path pattern; `{username}` là **biến URI được trích xuất từ đường dẫn**. Đừng hiểu chuỗi `"{username}"` là một username cố định. Các pattern cụ thể được định nghĩa theo ngữ nghĩa của `PathPattern`, nên khi dùng dấu sao, encoded segments, trailing slash hoặc prefix context path cần kiểm thử chính hệ thống đang chạy.

**Phân biệt path với query string:** URL `/api/accounts/alice?detail=full` có path `/api/accounts/alice`; tham số query `detail=full` không phải tên biến trong `/api/accounts/{username}`. Nếu quyền phụ thuộc query/headers, không giả vờ `pathMatchers` tự kiểm tra chúng; dùng logic được kiểm chứng ở tầng phù hợp hoặc matcher tùy chỉnh.

### 3.2 Lỗi thứ tự rule nghiêm trọng

**Sai:**

```java
.authorizeExchange(exchanges -> exchanges
    .pathMatchers("/api/**").permitAll()
    .pathMatchers("/api/admin/**").hasRole("ADMIN")
    .anyExchange().authenticated())
```

Request `GET /api/admin/users` đã bị rule `/api/**` cho phép ở phía trước, nên rule admin không còn bảo vệ được URL đó.

**Đúng:**

```java
.authorizeExchange(exchanges -> exchanges
    .pathMatchers("/api/admin/**").hasRole("ADMIN")
    .pathMatchers("/api/public/**").permitAll()
    .pathMatchers("/api/**").authenticated()
    .anyExchange().denyAll())
```

Đây là **hai mảnh cấu hình thay thế nhau**, không dán đồng thời vào ví dụ chạy ở phía dưới. Nguyên tắc “hẹp trước, rộng sau” không thay thế việc code review thứ tự, vì một rule chính xác nhưng sai vị trí vẫn có thể tạo lỗ hổng.

### 3.3 URL matcher khác controller mapping

Security kiểm tra request **trước** khi controller xử lý. Không giả định:

- `@GetMapping("/api/orders/{id}")` tự cấp quyền xem order cho ai biết `id`.
- Cùng một URL mà Security và controller đang dùng cùng phương pháp chuẩn hóa, decode, trailing slash, hoặc path prefix nếu bạn tùy chỉnh matcher ở một phía.
- URL không có controller handler sẽ luôn bị chặn một cách an toàn. Nếu policy quá rộng, Security có thể cho phép request trước khi WebFlux trả `404`.

Nên viết test cho cả URL chính thức, URL có segment bổ sung, path tương tự dễ nhầm và method không dự định hỗ trợ.

## 4. Phân quyền theo **HTTP method**

`ServerHttpSecurity.AuthorizeExchangeSpec.pathMatchers` có overload nhận `HttpMethod`:

```java
.authorizeExchange(exchanges -> exchanges
    .pathMatchers(HttpMethod.GET, "/api/articles/**").permitAll()
    .pathMatchers(HttpMethod.POST, "/api/articles/**").hasRole("EDITOR")
    .pathMatchers(HttpMethod.PUT, "/api/articles/**").hasRole("EDITOR")
    .pathMatchers(HttpMethod.PATCH, "/api/articles/**").hasRole("EDITOR")
    .pathMatchers(HttpMethod.DELETE, "/api/articles/**").hasRole("ADMIN")
    .anyExchange().denyAll())
```

Đây là mảnh code cần import `org.springframework.http.HttpMethod`.

**Một URL, nhiều phương thức, nhiều policy:** đọc bài công khai không đồng nghĩa ai cũng được sửa, xóa hoặc thêm bài. Với các nhóm route dạng REST, thường phân tách GET/HEAD, POST, PUT, PATCH, DELETE và phân quyền tương ứng.

### 4.1 Method-specific và method-agnostic

- `pathMatchers(HttpMethod.GET, "/api/articles/**")` chỉ match request **GET** đối với pattern đó.
- `pathMatchers("/api/articles/**")` không ràng buộc method; nếu đặt trước các rule ghi, nó có thể cho phép tất cả method đi vào controller.
- Khi matcher không match method, Spring Security xét rule tiếp theo; nếu có `anyExchange().denyAll()`, method chưa liệt kê bị từ chối.

**HEAD và OPTIONS phải xem riêng.** Spring WebFlux có thể hỗ trợ HEAD cho handler GET; điều đó không làm matcher `HttpMethod.GET` tự match HEAD. CORS preflight dùng OPTIONS với các header tương ứng và cần cấu hình CORS phù hợp, không nên mở `OPTIONS /**` vô điều kiện chỉ để giảm lỗi frontend.

### 4.2 Authorization khác với CSRF

Một `POST` có đủ `ROLE_EDITOR` vẫn có thể bị **403 Forbidden** do thiếu token CSRF khi chain dùng CSRF protection (phổ biến ở ứng dụng web có cookie/session). `permitAll()` cũng **không tự vô hiệu hóa CSRF**.

```text
POST /api/articles
  |
  +-- CSRF protection: token hợp lệ? (nếu áp dụng)
  |
  +-- Authentication: caller là ai?
  |
  +-- Authorization: caller có ROLE_EDITOR không?
  |
  +-- Controller: ghi dữ liệu
```

Đừng mặc định sửa `403` bằng `csrf(csrf -> csrf.disable())`. Hãy xác định request dùng browser cookie tự động gửi credential hay API bearer token, rồi cấu hình CSRF theo threat model. Ví dụ chạy ở mục 7 **giữ CSRF bật** để test được cả phân quyền method lẫn CSRF.

## 5. Biến đường dẫn và AuthorizationContext

Với pattern `/api/accounts/{username}`, bạn có thể muốn rule: **chính user được xem account mang username của họ, hoặc ADMIN được xem mọi account**.

```text
GET /api/accounts/alice
    |-- pathMatchers(..., "/api/accounts/{username}")
    |-- AuthorizationContext.getVariables()["username"] = "alice"
    |-- Authentication.getName() = "alice"
    |-- ownerOrAdmin? -> GRANT
```

Trong Spring Security reactive, khi matcher trích xuất biến URI, `AuthorizationContext` có các API:

```java
context.getExchange();   // ServerWebExchange
context.getVariables();  // Map<String,Object>
```

Tên và kiểu cần đúng: đây là `org.springframework.security.web.server.authorization.AuthorizationContext`, **không** phải `org.springframework.security.web.access.intercept.RequestAuthorizationContext` của Servlet. `getVariables()` cho giá trị kiểu `Object`, không tự là ID đã xác minh hoặc `@PathVariable` của controller.

### 5.1 Matcher biến URI không tự kiểm tra quyền

```java
.pathMatchers(HttpMethod.GET, "/api/accounts/{username}")
    .authenticated()
```

Cấu hình trên chỉ đòi hỏi **người gọi đã đăng nhập**, chứ **không kiểm tra** username trong URL có bằng danh tính đã xác thực hay không. Alice vẫn có thể gọi `/api/accounts/bob` nếu controller/service không kiểm quyền tiếp. Đây là ví dụ điển hình của **broken object-level authorization (BOLA/IDOR)**.

Để có kiểm tra tại HTTP layer, dùng `access(ReactiveAuthorizationManager<AuthorizationContext>)` hoặc lambda có cùng chữ ký. Quyết định cần dựa trên **Authentication đáng tin** và giá trị URI được kiểm tra, không dựa vào header `X-User` hoặc body do caller tự khai.

### 5.2 ReactiveAuthorizationManager đọc biến và danh tính

Manager reactive ở Spring Security 6.x có mẫu chữ ký:

```java
Mono<AuthorizationDecision> check(
    Mono<Authentication> authentication, AuthorizationContext context);
```

Đây là hình thức minh họa của method trong `ReactiveAuthorizationManager<AuthorizationContext>`. Bên trong:

- `authentication`: publisher có thể phát `Authentication` đã được cung cấp bởi Spring Security; nếu không có thì có thể rỗng.
- `context.getVariables()`: các biến do path matcher tạo, ví dụ `username`.
- `AuthorizationDecision(true/false)`: cho phép hoặc từ chối.
- Để giữ tính reactive, dùng `map`/`flatMap` và trả `Mono<AuthorizationDecision>`, **không gọi `block()`/`subscribe()` thủ công.

Một phiên bản an toàn, từ chối mặc định:

```java
private ReactiveAuthorizationManager<AuthorizationContext> ownerOrAdmin() {
    AuthenticationTrustResolver trust =
        new AuthenticationTrustResolverImpl();

    return (authentication, context) -> {
        Object value = context.getVariables().get("username");
        if (!(value instanceof String username)) {
            return Mono.just(new AuthorizationDecision(false));
        }

        return authentication.map(auth -> {
            boolean admin = auth.getAuthorities().stream()
                .anyMatch(a -> "ROLE_ADMIN".equals(a.getAuthority()));
            boolean owner = username.equals(auth.getName());
            return new AuthorizationDecision(
                trust.isAuthenticated(auth) && (owner || admin));
        }).defaultIfEmpty(new AuthorizationDecision(false));
    };
}
```

Đây là **method minh họa**; ở mục 7 nó được đặt vào lớp cấu hình đầy đủ với imports chính xác. `AuthenticationTrustResolverImpl` tránh coi `AnonymousAuthenticationToken` (có thể có raw `isAuthenticated()==true`) là người dùng đã login; `trust.isAuthenticated(auth)` loại anonymous. Với biến thiếu/sai kiểu, hoặc publisher rỗng, trả quyết định từ chối.

**Phạm vi ví dụ:** so sánh username URI và `Authentication.getName()` chỉ là mẫu dễ hiểu. Trong hệ thống thật, username có thể đổi và `Authentication.getName()` có thể là subject do issuer cấp. Nếu URL chứa numeric ID của order/project, kiểm tra quyền sở hữu phải dựa trên mapping ID/tenant đáng tin và dữ liệu server, không so chuỗi username một cách máy móc.

### 5.3 Khi biến ID tham chiếu tài nguyên thật: kiểm quyền phía dữ liệu

Một route khác:

```http
GET /api/orders/892
Authorization: Bearer <token-cua-alice>
```

`892` chỉ là identifier do client chọn. Biết caller là Alice không chứng minh order 892 thuộc Alice. Cần quy tắc phân quyền trên bản ghi:

```text
authenticated user: alice (do Security xác minh)
requested orderId: 892 (đọc từ URL)
   |
   v
repository/service: order 892 thuộc tenant nào?
   |
   +-- Alice có quyền xem order trong tenant này? -> allow
   +-- Không có quyền? -> deny (403/404 theo API policy)
```

Có thể dùng `ReactiveAuthorizationManager` gọi repository R2DBC non-blocking trong `flatMap`; hoặc đặt kiểm tra cùng truy vấn dữ liệu trong service (ví dụ truy vấn theo `id AND owner_id`). Điều quan trọng: **không phân quyền bằng ID được truyền từ client mà bỏ kiểm dữ liệu server**.

**Pseudocode reactive** (chưa đầy đủ class/repository để chạy độc lập):

```java
return authentication.flatMap(auth -> {
    if (!trust.isAuthenticated(auth)) {
        return Mono.just(new AuthorizationDecision(false));
    }
    return orderPermissionService.canRead(
            auth.getName(), orderId, tenantId)
        .map(AuthorizationDecision::new)
        .defaultIfEmpty(new AuthorizationDecision(false));
}).defaultIfEmpty(new AuthorizationDecision(false));
```

Cần xác minh `orderId`/`tenantId` từ nguồn phù hợp, giới hạn truy vấn, xử lý lỗi và fail closed. Nếu implementation truy cập JDBC/JPA đồng bộ, **không gọi nó trực tiếp trên event loop**; sử dụng blocking boundary có scheduler/concurrency/timeout thích hợp hoặc chuyển sang reactive driver. Đừng đưa lỗi backend vào `onErrorReturn(true)`.

## 6. Kế hoạch authorization mẫu

Thiết kế một API với ba tài khoản demo và sáu loại request:

| HTTP method | URL | Đối tượng được phép |
|---|---|---|
| GET | `/api/public` | Tất cả |
| GET | `/api/admin/metrics` | `ROLE_ADMIN` |
| GET | `/api/accounts/{username}` | Chính user có tên trong URL, hoặc `ROLE_ADMIN` |
| GET | `/api/reports` | `ROLE_READER` |
| POST | `/api/reports` | `ROLE_EDITOR` **và** CSRF token khi chain áp dụng |
| Mọi method/path khác | Không thuộc policy | Từ chối qua `anyExchange().denyAll()` |

Thứ tự có chủ đích: public GET, admin GET, owner GET, reports GET, reports POST, fallback. Chỉ liệt kê GET/POST theo đúng chức năng. Ví dụ gồm ba tài khoản: Alice và Bob có `ROLE_READER`; Admin có `ROLE_ADMIN`, `ROLE_READER` và `ROLE_EDITOR`.

Chú ý: gọi cùng một path với một method khác sẽ **không** được thừa hưởng rule của GET. Ví dụ `POST /api/accounts/alice` có thể trùng một controller handler khác trong tương lai; với fallback hiện tại, request này bị từ chối.

## 7. Dự án Spring Boot WebFlux chạy được

Ví dụ này dùng **HTTP Basic** và nguồn người dùng in-memory, mật khẩu BCrypt; chỉ để chạy thử trên máy học/localhost. Spring Boot 3.3.13 là phiên bản minh họa API, **không phải khuyến nghị production năm 2026**. Dự án thật cần phiên bản đã được vá, password/IdP quản lý an toàn, TLS, CSRF/CORS/observability phù hợp.

### 7.1 Cấu trúc dự án

```text
webflux-http-authorization/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/demo/authorization/
    │   ├── AuthorizationApplication.java
    │   ├── SecurityConfiguration.java
    │   └── ApiController.java
    └── test/java/demo/authorization/
        └── AuthorizationPolicyTest.java
```

**settings.gradle**

```groovy
rootProject.name = 'webflux-http-authorization'
```

**build.gradle**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo.authorization'
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

Không thêm `spring-boot-starter-web` vì đây là ví dụ WebFlux; nếu một dự án khác có cả starter MVC, Boot có thể chọn web application type khác. Dependencies test gồm Spring Security Test để kiểm thử CSRF trong `WebTestClient`.

### 7.2 Application

**src/main/java/demo/authorization/AuthorizationApplication.java**

```java
package demo.authorization;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AuthorizationApplication {

    public static void main(String[] args) {
        SpringApplication.run(AuthorizationApplication.class, args);
    }
}
```

### 7.3 Security configuration — path, method và biến URI

**src/main/java/demo/authorization/SecurityConfiguration.java**

```java
package demo.authorization;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.authentication.AuthenticationTrustResolver;
import org.springframework.security.authentication.AuthenticationTrustResolverImpl;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.ReactiveAuthorizationManager;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.authorization.AuthorizationContext;
import reactor.core.publisher.Mono;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
public class SecurityConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService userDetailsService(
            PasswordEncoder passwordEncoder) {

        UserDetails alice = User.withUsername("alice")
            .password(passwordEncoder.encode("dev-alice-password"))
            .roles("READER")
            .build();

        UserDetails bob = User.withUsername("bob")
            .password(passwordEncoder.encode("dev-bob-password"))
            .roles("READER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(passwordEncoder.encode("dev-admin-password"))
            .roles("ADMIN", "READER", "EDITOR")
            .build();

        return new MapReactiveUserDetailsService(alice, bob, admin);
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/api/public").permitAll()
                .pathMatchers(HttpMethod.GET, "/api/admin/metrics")
                    .hasRole("ADMIN")
                .pathMatchers(HttpMethod.GET, "/api/accounts/{username}")
                    .access(ownerOrAdmin())
                .pathMatchers(HttpMethod.GET, "/api/reports")
                    .hasRole("READER")
                .pathMatchers(HttpMethod.POST, "/api/reports")
                    .hasRole("EDITOR")
                .anyExchange().denyAll())
            .httpBasic(Customizer.withDefaults())
            .formLogin(form -> form.disable())
            .csrf(Customizer.withDefaults())
            .build();
    }

    private ReactiveAuthorizationManager<AuthorizationContext>
            ownerOrAdmin() {

        AuthenticationTrustResolver trust =
            new AuthenticationTrustResolverImpl();

        return (authentication, context) -> {
            Object value = context.getVariables().get("username");
            if (!(value instanceof String username)) {
                return Mono.just(new AuthorizationDecision(false));
            }

            return authentication
                .map(auth -> {
                    boolean isAdmin = auth.getAuthorities().stream()
                        .anyMatch(a ->
                            "ROLE_ADMIN".equals(a.getAuthority()));
                    boolean ownsPath =
                        username.equals(auth.getName());

                    return new AuthorizationDecision(
                        trust.isAuthenticated(auth)
                            && (ownsPath || isAdmin));
                })
                .defaultIfEmpty(new AuthorizationDecision(false));
        };
    }
}
```

**Đọc code chính xác:**

1. `@EnableWebFluxSecurity` bật cấu hình Spring Security WebFlux; không dùng `@EnableWebSecurity` của MVC.
2. `MapReactiveUserDetailsService` là user store **phát triển**, không phải giải pháp quản lý danh tính production. Password được hash bằng BCrypt; dữ liệu ví dụ không dùng làm credential thật.
3. `GET /api/public` không cần login. Các phương thức khác trên `/api/public` **không** được mặc định cho phép.
4. `GET /api/admin/metrics` yêu cầu `ROLE_ADMIN`.
5. `GET /api/accounts/{username}` dùng `access(ownerOrAdmin())` để so biến URI với người đã xác thực hoặc role ADMIN. Nếu không có principal hoặc không có biến phù hợp, trả quyết định deny.
6. `GET /api/reports` yêu cầu `ROLE_READER`. `POST /api/reports` yêu cầu `ROLE_EDITOR` **và** CSRF token theo chain.
7. `anyExchange().denyAll()` từ chối request chưa được rule bao phủ. Nó không tự định nghĩa HTTP status cho mọi loại lỗi; response phụ thuộc trạng thái xác thực, CSRF và exception handling.
8. `httpBasic(withDefaults())` bật login qua Basic; `formLogin(disable)` ngăn redirect HTML trong bài demo API.
9. `csrf(withDefaults())` giữ bảo vệ CSRF. Test POST hợp lệ phải có token; đừng hiểu role EDITOR đủ để bỏ qua CSRF.
10. `ownerOrAdmin()` chỉ dùng thông tin trusted từ `Authentication` và biến do matcher giải mã, không tin header `X-User-Id` hoặc giá trị JSON do client tự đưa vào.

Mặc dù ví dụ bảo vệ `/api/accounts/{username}` theo chính username, business rule thực tế thường yêu cầu map từ issuer+subject sang account ID rồi kiểm quyền dữ liệu trong service. **Không coi username URL là đại diện đầy đủ cho ownership của mọi bản ghi.**

### 7.4 Controller minh họa

**src/main/java/demo/authorization/ApiController.java**

```java
package demo.authorization;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class ApiController {

    @GetMapping("/api/public")
    public Mono<String> publicInfo() {
        return Mono.just("public");
    }

    @GetMapping("/api/admin/metrics")
    public Mono<String> metrics() {
        return Mono.just("admin metrics");
    }

    @GetMapping("/api/accounts/{username}")
    public Mono<String> account(@PathVariable String username) {
        return Mono.just("account:" + username);
    }

    @GetMapping("/api/reports")
    public Mono<String> reports() {
        return Mono.just("reports");
    }

    @PostMapping("/api/reports")
    public Mono<String> createReport() {
        return Mono.just("created");
    }
}
```

Controller không tự xử lý authorization, vì `SecurityWebFilterChain` đã quyết định ai được gọi handler. Tuy vậy trong ứng dụng có DB, service vẫn phải kiểm quyền **đối tượng/tenant** và tránh trả dữ liệu nhạy cảm ngoài chính sách. Demo chỉ trả chuỗi cố định, không truy cập kho thật.

### 7.5 Chạy thử với curl

Cần JDK 17+, Gradle phù hợp Boot 3.3 và máy có quyền tải Maven dependencies. Tại thư mục dự án:

```bash
gradle bootRun
```

Nếu có wrapper tương thích, dùng `./gradlew bootRun` (Windows: `gradlew.bat bootRun`). Các credential dưới đây chỉ dùng local.

```bash
# Công khai, không gửi mật khẩu
curl -i http://localhost:8080/api/public

# Chưa đăng nhập: yêu cầu đăng nhập
curl -i -H "Accept: application/json" \
    http://localhost:8080/api/accounts/alice

# Curl sẽ hỏi password tại terminal: nhập dev-alice-password
curl -i -u alice \
    http://localhost:8080/api/accounts/alice

# Với alice, nhập lại dev-alice-password: không được đọc account bob
curl -i -u alice \
    http://localhost:8080/api/accounts/bob

# Với admin, nhập dev-admin-password: được đọc account bob
curl -i -u admin \
    http://localhost:8080/api/accounts/bob

# Alice có ROLE_READER nên được GET reports
curl -i -u alice \
    http://localhost:8080/api/reports

# Không có CSRF token hợp lệ: POST sẽ bị 403
curl -i -u admin -X POST \
    http://localhost:8080/api/reports
```

Khi dùng PowerShell, `curl` có thể là alias; dùng `curl.exe` khi cần. Không đưa mật khẩu vào shell history hoặc tài liệu log.

| Request | Kết quả chính kỳ vọng |
|---|---|
| `GET /api/public` không credential | `200`, body `public` |
| `GET /api/accounts/alice` không credential | `401` với Basic |
| `GET /api/accounts/alice` bằng Alice | `200`, body `account:alice` |
| `GET /api/accounts/bob` bằng Alice | `403` |
| `GET /api/accounts/bob` bằng Admin | `200`, body `account:bob` |
| `GET /api/reports` bằng Alice | `200`, body `reports` |
| `GET /api/admin/metrics` bằng Alice | `403` |
| `GET /api/admin/metrics` bằng Admin | `200`, body `admin metrics` |
| `POST /api/reports` bằng Admin nhưng không CSRF | `403` |
| `GET /api/unknown` bằng Admin | `403` vì fallback `denyAll` |

Các status được nêu cho cấu hình ví dụ; trên một hệ thống có entry point, redirect login, exception handler hoặc CORS tùy chỉnh, HTTP response có thể khác. Lệnh POST trên chỉ để chứng minh CSRF; để POST thành công cần token hợp lệ từ cơ chế cấp CSRF của server hoặc test WebTestClient ở mục tiếp theo.

## 8. Kiểm thử phân quyền tự động với WebTestClient

Test dùng server mock trong ứng dụng Spring Boot và HTTP Basic **thật** theo user store demo, không chỉ mock principal. `spring-security-test` cung cấp `csrf()` cho test request thay đổi trạng thái. Nhờ đó có thể kiểm thử các nhánh 200, 401, 403 và đường dẫn không khớp mà không cần database.

**src/test/java/demo/authorization/AuthorizationPolicyTest.java**

```java
package demo.authorization;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureWebTestClient
class AuthorizationPolicyTest {

    @Autowired
    WebTestClient client;

    @Test
    void publicGetDoesNotNeedLogin() {
        client.get().uri("/api/public")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("public");
    }

    @Test
    void protectedAccountRejectsUnauthenticatedRequest() {
        client.get().uri("/api/accounts/alice")
            .accept(MediaType.APPLICATION_JSON)
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void ownerCanReadOwnAccount() {
        client.get().uri("/api/accounts/alice")
            .headers(h -> h.setBasicAuth("alice", "dev-alice-password"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("account:alice");
    }

    @Test
    void ownerCannotReadSomeoneElsesAccount() {
        client.get().uri("/api/accounts/bob")
            .headers(h -> h.setBasicAuth("alice", "dev-alice-password"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void adminCanReadOtherAccount() {
        client.get().uri("/api/accounts/bob")
            .headers(h -> h.setBasicAuth("admin", "dev-admin-password"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("account:bob");
    }

    @Test
    void getReportsAndAdminMetricsRequireDifferentRoles() {
        client.get().uri("/api/reports")
            .headers(h -> h.setBasicAuth("alice", "dev-alice-password"))
            .exchange()
            .expectStatus().isOk();

        client.get().uri("/api/admin/metrics")
            .headers(h -> h.setBasicAuth("alice", "dev-alice-password"))
            .exchange()
            .expectStatus().isForbidden();

        client.get().uri("/api/admin/metrics")
            .headers(h -> h.setBasicAuth("admin", "dev-admin-password"))
            .exchange()
            .expectStatus().isOk();
    }

    @Test
    void postMethodNeedsEditorAndCsrf() {
        // Editor role nhưng thiếu CSRF vẫn bị chặn.
        client.post().uri("/api/reports")
            .headers(h -> h.setBasicAuth("admin", "dev-admin-password"))
            .exchange()
            .expectStatus().isForbidden();

        // CSRF hợp lệ nhưng Alice không có ROLE_EDITOR.
        client.mutateWith(csrf())
            .post().uri("/api/reports")
            .headers(h -> h.setBasicAuth("alice", "dev-alice-password"))
            .exchange()
            .expectStatus().isForbidden();

        // Có cả ROLE_EDITOR và CSRF hợp lệ.
        client.mutateWith(csrf())
            .post().uri("/api/reports")
            .headers(h -> h.setBasicAuth("admin", "dev-admin-password"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("created");
    }

    @Test
    void unlistedPathAndMethodAreDenied() {
        client.get().uri("/api/unknown")
            .headers(h -> h.setBasicAuth("admin", "dev-admin-password"))
            .exchange()
            .expectStatus().isForbidden();

        client.mutateWith(csrf())
            .post().uri("/api/accounts/alice")
            .headers(h -> h.setBasicAuth("admin", "dev-admin-password"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void wrongCredentialIsRejected() {
        client.get().uri("/api/reports")
            .headers(h -> h.setBasicAuth("alice", "wrong-password"))
            .exchange()
            .expectStatus().isUnauthorized();
    }
}
```

Chạy:

```bash
gradle test
```

Kỳ vọng **9 test methods PASS** khi dự án, dependencies và cấu hình tương thích, với giả định CSRF test mutator được Spring Security Test tích hợp vào WebTestClient mock server. Không tuyên bố đã chạy build/test chỉ vì code được trình bày: nếu thất bại cần xem stack trace và phiên bản Spring Boot/Security/Gradle thực tế.

### Tại sao test âm tính quan trọng?

- Không credential → `401`: bảo vệ yêu cầu authentication.
- Credential đúng nhưng sai owner/role → `403`: có authentication nhưng không được authorization.
- Role đúng nhưng thiếu CSRF → `403`: permission không thay thế CSRF.
- URL hoặc method không nằm trong policy → `403`: fallback deny hoạt động.
- Admin có đúng role hoặc user đúng owner → `200`: tránh chính sách quá chặt làm hỏng chức năng.

Với route có owner/tenant trên database, cần thêm các test cross-tenant và truy cập record không thuộc user; các test so sánh username URL chỉ chứng minh chính sách mẫu, không thay cho kiểm thử BOLA thật.

## 9. Nhiều SecurityWebFilterChain và phạm vi policy

Ứng dụng có thể có một chain cho `/api/**` (HTTP Basic, JWT) và một chain cho trang web (form login). Phải phân biệt:

| Thành phần | Vai trò |
|---|---|
| `ServerHttpSecurity.securityMatcher(...)` | Xác định request **có vào chain này** hay không |
| `authorizeExchange().pathMatchers(...)` | Khi đã vào chain, quyết định rule nào kiểm quyền |
| `@Order` trên các chain | Ưu tiên chain nào được thử trước |
| Fallback chain | Bao phủ những request không khớp chain riêng để không lọt khỏi Spring Security |

Ví dụ **mảnh cấu hình định hướng**:

```java
@Bean
@Order(0)
SecurityWebFilterChain apiChain(ServerHttpSecurity http) {
    return http
        .securityMatcher(
            new PathPatternParserServerWebExchangeMatcher("/api/**"))
        .authorizeExchange(exchanges -> exchanges
            .pathMatchers(HttpMethod.GET, "/api/public").permitAll()
            .anyExchange().authenticated())
        .httpBasic(Customizer.withDefaults())
        .build();
}

@Bean
@Order(1)
SecurityWebFilterChain fallbackChain(ServerHttpSecurity http) {
    return http
        .authorizeExchange(exchanges -> exchanges
            .anyExchange().denyAll())
        .build();
}
```

Đây là code **thay thế** một phần cấu hình ở mục 7, không thêm hai bean này đồng thời với `securityWebFilterChain` demo. Cần imports `Order` và `PathPatternParserServerWebExchangeMatcher`; khi cấu hình nhiều chain, mỗi chain mang chính sách authentication/CSRF/authorization riêng. `securityMatcher` của chain API không cho phép tự động mọi URL `/api/**`, vì vẫn cần `authorizeExchange` bên trong chain đó.

Nếu không có fallback và một URL không khớp **bất kỳ chain nào**, request đó có thể đi qua mà không được các filter Spring Security trong các chain này bảo vệ. Vì vậy cần test route ngoài cả `/api/**` và trang web theo ý đồ.

## 10. Các trường hợp khó cần phân tích

### 10.1 Path variable không phải authentication

`GET /api/accounts/{username}` với caller Alice yêu cầu `/api/accounts/bob`. Cả biến URI và body/header do client điều khiển; chỉ danh tính do Spring Security đã xác minh là đáng tin để so đối chiếu. Không dùng cách sau:

```java
// SAI: header tự khai là chứng minh danh tính
String claimedUser =
    exchange.getRequest().getHeaders().getFirst("X-User");
boolean allow = claimedUser.equals(requestedUsername);
```

Đây là mảnh code **sai về bảo mật**, không dùng trong service thật. Nếu API gateway chèn header identity, phải có mô hình trusted proxy, mTLS/network boundary và chính sách chống spoof, không tin một header do Internet client gửi.

### 10.2 Query parameter không tương đương PathPattern

`GET /api/orders?user=alice` không có biến `{user}` chỉ vì query có tên user. Nếu client dùng `?tenantId=...`, cần xác định tenant được xác minh từ claims hoặc mapping server. Phân quyền theo query chỉ nên làm khi có lý do rõ, matcher custom/test đủ và không quên backend object-level authorization.

### 10.3 Request method có thể bị thay đổi qua proxy/gateway

Tại server phải nhận biết đúng HTTP method cuối cùng. Không đưa các HTTP method override headers tùy ý vào trust boundary; nếu proxy có rewrite, test đối chiếu behavior giữa gateway và app. `@GetMapping` không biến một POST thành GET trong `pathMatchers(HttpMethod.GET,...)`.

### 10.4 Phân quyền URL không tự che dữ liệu trong response

Ngay cả khi `GET /api/accounts/alice` chỉ Alice/Admin truy cập được, controller có thể vô tình trả toàn bộ profile, tokens hoặc bản ghi tenant khác. Cần DTO tối thiểu, filter dữ liệu trong service/repository, và policy ghi/đọc tách biệt.

### 10.5 Authentication failure, deny và lỗi nghiệp vụ

Khi một request không đạt policy có thể thấy:

- **401 Unauthorized:** không có credential/credential không hợp lệ và cơ chế authentication yêu cầu thử lại (Basic).
- **403 Forbidden:** principal đã xác thực nhưng không đủ role, không đạt owner rule, hoặc thiếu CSRF.
- **404 Not Found:** controller không có route/record; một số API có thể trả 404 thay cho 403 để tránh tiết lộ tài nguyên, nhưng phải thiết kế nhất quán.
- **405 Method Not Allowed:** handler tồn tại theo path nhưng không hỗ trợ method; tuy nhiên nếu Security `denyAll` chặn từ trước, người gọi có thể nhận `403` trước khi WebFlux quyết định 405.

Không suy luận chỉ từ status rằng một lớp security nhất định đã chạy; kiểm tra security chain, matcher, CSRF, login flow và log có kiểm soát.

### 10.6 Sắp xếp rule theo mã nguồn, không theo độ dài đường dẫn

Framework xét thứ tự khai báo, không tự sắp xếp rule theo “đường dẫn dài nhất” để đảm bảo route admin được ưu tiên. Nếu đặt `/api/**.permitAll()` trước `/api/admin/**.hasRole(...)`, matcher rộng có thể chiếm trước. Review code phải kiểm được thứ tự và test phải bắt được lỗi quyền quá rộng.

## 11. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách sửa |
|---|---|---|
| Dùng `HttpSecurity`/`requestMatchers` của Servlet | Nhầm API stack | Dùng `ServerHttpSecurity`, `SecurityWebFilterChain` và `pathMatchers` |
| Đặt `/api/**.permitAll()` trước matcher admin | Mở quyền trên route nhạy cảm | Đặt matcher cụ thể trước matcher rộng |
| `authenticated()` cho `/accounts/{username}` | User A có thể đọc URL của user B | Dùng manager/kiểm quyền object-level |
| Bỏ `anyExchange()` fallback | Có thể thiếu bảo vệ khi thêm route mới | Dùng fallback `denyAll`/policy rõ ràng |
| Dùng `pathMatchers("/api/articles/**").permitAll()` cho GET | Vô tình mở cả POST/DELETE | Dùng overload theo `HttpMethod.GET` |
| Nghĩ GET policy tự áp cho HEAD/OPTIONS | HEAD/preflight có thể bị từ chối hoặc xử lý khác | Liệt kê/test method thật và cấu hình CORS đúng |
| Gọi `hasRole("ROLE_ADMIN")` | Prefix role bị xử lý sai | Truyền `"ADMIN"` với role prefix mặc định |
| So `@PathVariable username` và header tự khai | Client giả mạo được danh tính | So với `Authentication` đã xác minh |
| Truyền path variable vào SQL/LDAP bằng nối chuỗi | Injection và truy cập chéo tenant | Parameterized query/filter escaping + kiểm quyền |
| Dùng `authentication.isAuthenticated()` raw để cho guest | Anonymous token có thể mang flag true | Dùng trust resolver/authorization framework |
| Dùng `block()` trong manager reactive | Chặn event-loop hoặc phá throughput | Trả `Mono`; offload backend blocking có giới hạn |
| Bật `csrf.disable()` vì POST 403 | Tăng rủi ro với browser/cookie | Hiểu token CSRF và threat model |
| Chỉ test case `200` | Không phát hiện quyền quá rộng | Test anonymous, wrong credential, wrong role, wrong owner |
| Phân quyền tại URL mà không phân quyền tại DB | Dễ BOLA/IDOR, cross-tenant | Kiểm tra owner/tenant trên bản ghi và hành động |
| Tách nhiều chain nhưng không có fallback | URL có thể không được bảo vệ | Có chain catch-all, test URL ngoài matcher |

## 12. Checklist triển khai production

1. Ghi lại tất cả HTTP methods/path patterns, nhóm người dùng và quyền dữ liệu tương ứng.
2. Xác minh app dùng WebFlux thực sự, chain nào áp dụng và thứ tự `@Order` khi có nhiều chain.
3. Đặt public route thật sự công khai bằng `permitAll()`; không dùng matcher rộng hơn yêu cầu.
4. Dùng `HttpMethod` trong matcher khi cùng URL có rule đọc/ghi khác nhau; test HEAD/OPTIONS/PATCH/DELETE theo API thực tế.
5. Khi có `{username}` hoặc `{id}`, quyết định có cần kiểm owner/tenant/quan hệ sở hữu ở DB hay không.
6. Trong `ReactiveAuthorizationManager`, chỉ dùng authenticated identity đáng tin, fail closed khi thiếu biến hoặc lỗi backend, không gọi blocking I/O trên event-loop.
7. Với OAuth2/JWT, kiểm signature, issuer, audience, thời hạn và mapping authorities đúng cấu hình; không tin claims trước xác minh.
8. Giữ CSRF protection khi browser tự gửi cookie credential, cấu hình CORS đúng origin/method/header; không cho mọi OPTIONS/POST vô điều kiện.
9. Thiết kế fallback `anyExchange().denyAll()` và fallback chain nếu nhiều chain; review sau mỗi lần thêm controller.
10. Log có kiểm soát tên policy/trạng thái (không credential/token), monitor 401/403, security exceptions và biến động traffic.
11. Kiểm thử cả cho phép và từ chối: guest, user, admin, sai role, sai owner, cross-tenant, sai method, ID không tồn tại, CSRF thiếu.
12. Không đưa mật khẩu demo hoặc tài khoản in-memory vào production. Cập nhật phiên bản Spring Security và các dependency theo security advisory.

## 13. Bài tập thực hành

1. Giữ `GET /api/public` là public, thêm `POST /api/public`; giải thích vì sao fallback `denyAll()` sẽ chặn method mới nếu chưa thêm rule.
2. Thay `.pathMatchers(HttpMethod.GET, "/api/accounts/{username}").access(ownerOrAdmin())` bằng `authenticated()`, viết test Alice đọc account Bob và phân tích lỗi.
3. Thêm role `ROLE_SUPPORT` cho một user và thiết kế chính sách chỉ cho xem account thuộc tenant được cấp quyền; không lấy tenant từ query làm chứng cứ duy nhất.
4. Thử hoán đổi rule `/api/**.permitAll()` và `/api/admin/**.hasRole("ADMIN")`; kiểm chứng bằng test an ninh vì sao thứ tự ảnh hưởng.
5. Bật `POST /api/reports` cho role EDITOR và viết test có/không có CSRF. Vì sao role đúng chưa đủ nếu CSRF được bật?
6. Viết matcher cho `DELETE /api/reports/{id}` chỉ ADMIN. Với một record thuộc tenant khác, còn điều kiện nào phải kiểm trong service?
7. Dùng `AuthorizationContext.getVariables()` để rút `projectId` từ `/api/projects/{projectId}/members`; viết manager dùng repository reactive kiểm membership/tenant. Định nghĩa hành vi khi không có record và khi repository lỗi.
8. Tách `/api/**` và `/web/**` thành hai `SecurityWebFilterChain` rồi thêm fallback deny. Test một URL nằm ngoài cả hai.
9. Tạo tập test cho HEAD, OPTIONS preflight, trailing slash, encoded URL và URL gần giống matcher nhạy cảm; so kết quả giữa Spring Security và WebFlux mapping.
10. Giải thích vì sao `hasAuthority("SCOPE_orders.read")` chỉ có tác dụng nếu JWT/identity provider được cấu hình để map scope thành authority đó.

## Tóm tắt

**Phân quyền HTTP reactive** dùng `ServerHttpSecurity.authorizeExchange(...)` để kết hợp ba thông tin: **path pattern**, **HTTP method** và **danh tính/quyền đã xác thực**. Matcher `/accounts/{username}` có thể trích xuất biến vào `AuthorizationContext.getVariables()`; một `ReactiveAuthorizationManager` dùng biến đó để đưa ra `AuthorizationDecision`. Các rule xét theo thứ tự khai báo, vì vậy matcher cụ thể phải nằm trước matcher rộng và luôn cân nhắc `anyExchange().denyAll()`. Kiểm tra theo URL chỉ là một lớp bảo vệ: quyền sở hữu dữ liệu/tenant ở service và CSRF/CORS theo mô hình client vẫn là yêu cầu bắt buộc.

## Tài liệu chính thức

- Spring Security 6.3 — Authorize ServerHttpRequest (reactive), thứ tự rule và access manager: https://docs.spring.io/spring-security/reference/6.3/reactive/authorization/authorize-http-requests.html
- Spring Security 6.3 — WebFlux Security configuration và nhiều `SecurityWebFilterChain`: https://docs.spring.io/spring-security/reference/6.3/reactive/configuration/webflux.html
- Javadoc 6.2.8 — `AuthorizationContext.getVariables()`: https://docs.spring.io/spring-security/site/docs/6.2.8/api/org/springframework/security/web/server/authorization/AuthorizationContext.html
- Javadoc — `AuthenticationTrustResolver.isAuthenticated`: https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/authentication/AuthenticationTrustResolver.html
- Spring Security — Reactive WebTestClient authentication testing: https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/authentication.html
- Spring Security — Reactive CSRF testing: https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/csrf.html
- Spring Framework — WebFlux annotated controller method arguments: https://docs.spring.io/spring-framework/reference/6.1/web/webflux/controller/ann-methods/arguments.html
