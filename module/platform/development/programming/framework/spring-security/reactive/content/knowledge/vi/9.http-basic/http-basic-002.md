# Bật HTTP Basic trong SecurityWebFilterChain

> **Phạm vi:** Cấu hình HTTP Basic cho **Spring Security reactive / Spring WebFlux**, sử dụng Spring Boot 3.x, Spring Security 6.x và Java 17+. Mục tiêu là khai báo đúng `SecurityWebFilterChain` với `ServerHttpSecurity.httpBasic(...)`, xác thực username/password bằng reactive user service, kiểm tra quyền truy cập và xác minh hành vi HTTP. Các mật khẩu cố định xuất hiện dưới đây chỉ phục vụ bài thực hành trên localhost.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích `Authorization: Basic <credentials>`, phản hồi `401 Unauthorized` và header `WWW-Authenticate`.
2. Bật HTTP Basic bằng `http.httpBasic(Customizer.withDefaults())` trong `SecurityWebFilterChain`, phân biệt API này với `HttpSecurity`/`SecurityFilterChain` của Spring MVC.
3. Cấu hình `MapReactiveUserDetailsService`, `PasswordEncoder` và các quy tắc `authorizeExchange`.
4. Chạy thử các trạng thái **200 (đủ quyền), 401 (chưa xác thực hoặc sai credential), 403 (đã xác thực nhưng thiếu quyền)** bằng curl và `WebTestClient`.
5. Hiểu phạm vi phiên, CSRF, HTTPS, xử lý lỗi, nhiều filter chains, cách vô hiệu hóa HTTP Basic và các tình huống không nên dùng Basic trong production.

## 1. HTTP Basic hoạt động như thế nào?

HTTP Basic là một **authentication scheme** của HTTP. Client gửi username/password trên mỗi request trong header `Authorization`:

```http
GET /api/me HTTP/1.1
Host: localhost:8080
Authorization: Basic cmVhZGVyOnJlYWRlci1wYXNz
```

Ví dụ header ở trên chứa Base64 của `reader:reader-pass`, chỉ để minh họa cú pháp. **Base64 là mã hóa biểu diễn, không phải mã hóa bảo mật:** bất kỳ người nào có được header cũng có thể giải mã lại username/password. Vì vậy khi kết nối qua mạng thực, phải dùng **HTTPS/TLS**, bảo vệ credential khỏi log, proxy và công cụ giám sát không cần thiết.

Client thường nhận challenge trước:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="Realm"
```

Giá trị `realm` là **ví dụ minh họa**, không nên viết test phụ thuộc cứng vào tên realm mặc định. Header `WWW-Authenticate` cho client biết phương thức xác thực server chấp nhận. Sau khi có credential, client thử lại request với `Authorization: Basic ...`. Một số client biết trước credentials nên gửi ngay mà không chờ 401.

### 1.1 Authentication khác Authorization

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Authentication** | Server kiểm chứng người gọi là ai | Username/password đúng → đối tượng `Authentication` |
| **Authorization** | Server quyết định người đó được làm gì | `ROLE_READER` được vào `/api/me`; thiếu `ROLE_ADMIN` không được vào `/api/admin` |
| **HTTP Basic** | Cách vận chuyển credential của HTTP request | `Authorization: Basic ...` |
| **ReactiveAuthenticationManager** | API xác thực credential trong WebFlux | Trả `Mono<Authentication>` hoặc error/empty phù hợp |
| **SecurityWebFilterChain** | Bộ filter bảo mật HTTP của Spring WebFlux | Basic authentication, security context, authorization, CSRF, headers |
| **ReactiveSecurityContextHolder** | Đọc context của request/subscription reactive | Lấy username/authorities sau xác thực |

Bật Basic **không tự động cấp quyền** cho mọi endpoint. `httpBasic(...)` thiết lập **phương thức xác thực**; `authorizeExchange(...)` quyết định **quy tắc truy cập**.

### 1.2 HTTP Basic không phải một trang đăng nhập

- Với HTTP Basic, client gửi credential trong `Authorization`; server không cần phát form HTML để thu password.
- Trình duyệt có thể tự hiển thị hộp thoại khi nhận Basic challenge, tùy trình duyệt và ngữ cảnh request.
- Form login thông thường xử lý form/cookie/session và chuyển hướng khi chưa đăng nhập; đó là **cơ chế khác**.
- Spring Security có thể cấu hình **cả Basic và form login** nếu bài toán cần, nhưng với API chỉ dùng Basic ta thường tắt form login để client nhận **401**, tránh bất ngờ chuyển hướng sang trang đăng nhập.

## 2. SecurityWebFilterChain nằm ở đâu trong WebFlux?

`SecurityWebFilterChain` là một tập `WebFilter` áp dụng cho những request `ServerWebExchange` phù hợp. Spring Security reactive dùng `WebFilterChainProxy` và các WebFilter để xử lý bảo mật trước khi Spring WebFlux gọi annotated controller hoặc functional route handler.

Luồng logic đơn giản hóa:

```text
Client (HTTP Basic request)
    |
    v
WebFlux HttpHandler / WebFilter pipeline
    |
    v
Spring Security WebFilterChainProxy
    |
    +-- chọn SecurityWebFilterChain theo securityMatcher
    |
    +-- HTTP Basic authentication filter
    |     |
    |     +-- đọc Authorization: Basic ...
    |     +-- tạo UsernamePasswordAuthenticationToken chưa xác thực
    |     +-- gọi ReactiveAuthenticationManager
    |     +-- xác thực thành công hoặc báo lỗi
    |
    +-- SecurityContext trong Reactor Context
    |
    +-- authorizeExchange (path/method/role)
    |
    +-- có thể trả 401 hoặc 403 và dừng request
    |
    v
DispatcherHandler
    |
    +-- @RestController / @GetMapping
    +-- RouterFunction / HandlerFunction
    |
    v
HTTP response
```

Sơ đồ chỉ diễn tả các **giai đoạn về ý nghĩa**, không cam kết mọi `WebFilter` vật lý có cùng thứ tự hoặc tên với các dòng. Thành phần cụ thể còn thay đổi theo cấu hình/phiên bản.

**Điểm then chốt:** Basic credential được Spring Security xử lý **trong WebFilter pipeline**, không phải controller tự Base64-decode password. Controller chỉ nhận request sau khi đáp ứng policy bảo mật. Nếu có cả Controller và RouterFunction trên một WebFlux server, `SecurityWebFilterChain` cũng bảo vệ chúng theo URL/method giống nhau.

## 3. Phân biệt Reactive Security với Servlet Security

Đừng nhầm hai bộ cấu hình:

| Spring MVC / Servlet | Spring WebFlux / Reactive |
| --- | --- |
| `HttpSecurity` | `ServerHttpSecurity` |
| `SecurityFilterChain` | `SecurityWebFilterChain` |
| Servlet `Filter` | Reactive `WebFilter` |
| `@EnableWebSecurity` | `@EnableWebFluxSecurity` |
| `authorizeHttpRequests(...)` | `authorizeExchange(...)` |
| `UserDetailsService` | `ReactiveUserDetailsService` |
| `AuthenticationManager` | `ReactiveAuthenticationManager` |
| `SecurityContextHolder` thường gắn ThreadLocal | `ReactiveSecurityContextHolder` sử dụng Reactor Context |

Nếu Spring Boot có **cả** `spring-boot-starter-web` (MVC) và `spring-boot-starter-webflux`, Boot thường **ưu tiên Spring MVC** ở chế độ tự nhận diện mặc định. Có class `WebClient` hoặc publisher `Mono` chưa chứng minh server là WebFlux. Để làm đúng bài này, nên dùng **chỉ `spring-boot-starter-webflux`** cho HTTP server, trừ khi bạn đã chủ động ép `WebApplicationType.REACTIVE` và kiểm thử runtime.

## 4. Khởi tạo dự án thực hành

Dùng Spring Initializr tạo ứng dụng Spring Boot 3.x, **Java 17+**, Gradle Groovy, thêm dependencies:

- Spring Reactive Web (`spring-boot-starter-webflux`)
- Spring Security (`spring-boot-starter-security`)
- Spring Boot Test (`spring-boot-starter-test`)

Tương đương phần dependency trong `build.gradle` của project đã có Boot plugin và cấu hình dependency management:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Project mẫu sẽ gồm bốn file dưới cùng package:

```text
src/
  main/java/com/example/basicwebflux/
    BasicWebfluxApplication.java
    SecurityConfig.java
    ApiController.java
  test/java/com/example/basicwebflux/
    HttpBasicIntegrationTest.java
```

Tên package trong toàn bộ file phải giống nhau; nếu bạn dùng package khác, thay đồng loạt `package` và đường dẫn. Java code sau cần Spring Boot/Spring Security/Reactor dependencies. **Không chạy riêng bằng `javac` không có classpath framework**; dùng Gradle wrapper của project.

### 4.1 Main class — BasicWebfluxApplication.java

`src/main/java/com/example/basicwebflux/BasicWebfluxApplication.java`:

```java
package com.example.basicwebflux;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BasicWebfluxApplication {

    public static void main(String[] args) {
        SpringApplication.run(BasicWebfluxApplication.class, args);
    }
}
```

Vì `@SpringBootApplication` component-scan package hiện tại và package con, hai file `SecurityConfig` và `ApiController` cũng được tạo bean trong cùng application context.

## 5. Bật HTTP Basic trong SecurityWebFilterChain

### 5.1 SecurityConfig.java — mã đầy đủ

`src/main/java/com/example/basicwebflux/SecurityConfig.java`:

```java
package com.example.basicwebflux;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/public/**").permitAll()
                .pathMatchers(HttpMethod.GET, "/api/admin").hasRole("ADMIN")
                .pathMatchers(HttpMethod.GET, "/api/**").authenticated()
                .anyExchange().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService reactiveUsers(PasswordEncoder encoder) {
        UserDetails reader = User.withUsername("reader")
            .password(encoder.encode("reader-demo-password"))
            .roles("READER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("admin-demo-password"))
            .roles("READER", "ADMIN")
            .build();

        return new MapReactiveUserDetailsService(reader, admin);
    }
}
```

Đây là **một cấu hình hoạt động đầy đủ trong Boot project ở trên**, không cần bạn tự tạo `AuthenticationWebFilter` hoặc tự giải mã Base64. Spring Security WebFlux đăng ký phần cần thiết khi `@EnableWebFluxSecurity` và `SecurityWebFilterChain` được khai báo đúng.

### 5.2 Giải thích từng dòng quan trọng

**`@EnableWebFluxSecurity`**

Bật support bảo mật cho WebFlux. Đây không phải annotation `@EnableWebSecurity` dành cho Servlet. Nó cũng **không đổi** loại web stack nếu Spring Boot đã chọn MVC do dependency; cần đảm bảo ứng dụng thực sự chạy WebFlux.

**`SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http)`**

Khai báo bean web security cho reactive server; `ServerHttpSecurity` là DSL WebFlux. `http.build()` tạo chain sau khi bạn định nghĩa rules và authentication. Không trả về `SecurityFilterChain` của Servlet.

**`authorizeExchange(...)`**

Rules áp dụng theo thứ tự:

1. `GET /public/**` — công khai.
2. `GET /api/admin` — cần quyền admin.
3. `GET /api/**` — người dùng đã xác thực có thể gọi.
4. `anyExchange().denyAll()` — request còn lại bị từ chối theo policy authorization.

Đặt `/api/admin` **trước** `/api/**`, vì matcher rộng nếu đặt trước sẽ che yêu cầu admin. Với `hasRole("ADMIN")`, Spring Security yêu cầu authority `ROLE_ADMIN`. `User.roles("ADMIN")` tự thêm tiền tố `ROLE_`; không gọi `roles("ROLE_ADMIN")`.

**`httpBasic(Customizer.withDefaults())`**

Bật HTTP Basic với các thiết lập mặc định của Spring Security WebFlux. `Customizer.withDefaults()` yêu cầu DSL dùng cấu hình mặc định; nó **không tự tạo user**, **không tự cấp role**, và **không thay thế** `authorizeExchange`.

**`formLogin(ServerHttpSecurity.FormLoginSpec::disable)`**

Tắt form login trong chain demo để API tập trung vào HTTP Basic, có phản hồi 401/challenge khi request thiếu credential thay vì hành vi form login. Việc tắt form login không đồng nghĩa tắt CSRF hoặc tắt các security headers.

**`MapReactiveUserDetailsService`**

Tạo kho user reactive in-memory dùng cho bài thực hành. Nó đáp ứng `ReactiveUserDetailsService` và có thể được Spring Security tự dùng để xây dựng password authentication manager cho Basic khi không có custom manager khác làm thay đổi cấu hình. Production nên thay bằng cơ chế user store/IdP được quản trị đúng.

**`PasswordEncoderFactories.createDelegatingPasswordEncoder()`**

Tạo `DelegatingPasswordEncoder`; với cấu hình mặc định, khi gọi `encode` thường tạo chuỗi có prefix `{bcrypt}` và hash salted. Không lưu password raw hoặc dùng `{noop}` trong production. Hash thu được có salt nên không kỳ vọng giống nhau giữa các lần chạy.

### 5.3 CSRF không bị tắt trong ví dụ

Spring Security WebFlux bật CSRF protection theo mặc định. Các endpoint minh họa là **GET** nên không cần gửi CSRF token để gọi chúng. Với POST/PUT/PATCH/DELETE, request có thể bị CSRF filter từ chối **trước** khi handler chạy nếu không có token, dù Basic authentication đúng.

Không chủ động thêm `.csrf(ServerHttpSecurity.CsrfSpec::disable)` vào bài chỉ để mọi request POST chạy được. Với **browser** có khả năng tự gửi HTTP Basic credentials sau khi đã xác thực, CSRF vẫn có thể là vấn đề khi thay đổi dữ liệu. Chỉ cân nhắc thay đổi CSRF policy khi hiểu rõ loại client, cách tự động gửi credential, browser origins và threat model.

## 6. Tạo ba endpoint kiểm tra policy

`src/main/java/com/example/basicwebflux/ApiController.java`:

```java
package com.example.basicwebflux;

import org.springframework.http.MediaType;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class ApiController {

    @GetMapping(
        value = "/public/ping",
        produces = MediaType.TEXT_PLAIN_VALUE
    )
    public Mono<String> ping() {
        return Mono.just("pong");
    }

    @GetMapping(
        value = "/api/me",
        produces = MediaType.TEXT_PLAIN_VALUE
    )
    public Mono<String> me() {
        return currentUsername().map(name -> "Hello " + name);
    }

    @GetMapping(
        value = "/api/admin",
        produces = MediaType.TEXT_PLAIN_VALUE
    )
    public Mono<String> admin() {
        return currentUsername().map(name -> "Admin " + name);
    }

    private Mono<String> currentUsername() {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(Authentication::getName);
    }
}
```

**Phân tích:** Controller không kiểm tra password trực tiếp. Khi Basic credential đúng, authentication filter xử lý xác thực trước; Spring Security đặt thông tin vào Reactor Context của request. `ReactiveSecurityContextHolder` đọc username từ context đó.

Không gọi `SecurityContextHolder.getContext()` theo kiểu ThreadLocal Servlet trong reactive handler. Không dùng `block()` để lấy principal trong WebFlux event-loop; giữ logic trong `Mono` / `Flux`.

### 6.1 Kết quả mong đợi của từng người dùng

| Request | Credential | Dự đoán HTTP | Body khi thành công |
| --- | --- | --- | --- |
| GET `/public/ping` | Không có | **200 OK** | `pong` |
| GET `/api/me` | Không có | **401 Unauthorized** | Không có body ứng dụng |
| GET `/api/me` | `reader` + đúng password | **200 OK** | `Hello reader` |
| GET `/api/me` | `reader` + sai password | **401 Unauthorized** | Không có body ứng dụng |
| GET `/api/admin` | `reader` + đúng password | **403 Forbidden** | Không có body ứng dụng |
| GET `/api/admin` | `admin` + đúng password | **200 OK** | `Admin admin` |
| GET `/api/admin` | Không có | **401 Unauthorized** | Không có body ứng dụng |
| POST `/api/me` | Bất kỳ | Không được handler GET xử lý; có thể bị CSRF/authorization chặn | Không áp dụng |

**Chú ý:** `/api/admin` được đặt trước `/api/**` trong authorization rules. Nếu làm ngược, reader có thể được phép đi qua vì rule authenticated bắt trước, gây lỗi phân quyền dù Basic xác thực đúng.

## 7. Chạy thử bằng curl

Từ thư mục Gradle project:

```bash
./gradlew bootRun
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Mặc định ứng dụng thường chạy tại `http://localhost:8080` nếu port chưa đổi và không có ứng dụng khác chiếm port. Dùng **HTTP ở localhost chỉ cho bài demo**, không gửi credential thật trên HTTP mạng công cộng.

### 7.1 Request công khai và request chưa xác thực

```bash
curl -i http://localhost:8080/public/ping
curl -i http://localhost:8080/api/me
curl -i http://localhost:8080/api/admin
```

Kỳ vọng:

```text
GET /public/ping  -> 200, body pong
GET /api/me       -> 401 khi thiếu Basic header
GET /api/admin    -> 401 khi thiếu Basic header
```

Phản hồi 401 thường có `WWW-Authenticate: Basic ...`. Giá trị cụ thể của realm, các security headers và HTTP protocol version có thể khác giữa môi trường. Đừng kiểm tra bằng cách so khớp toàn bộ chuỗi raw HTTP response.

### 7.2 Basic username/password đúng

Dùng curl với `-u`, để **curl hỏi password tương tác** thay vì đặt nó ngay trong command line:

```bash
curl -i -u reader http://localhost:8080/api/me
curl -i -u reader http://localhost:8080/api/admin
curl -i -u admin http://localhost:8080/api/admin
```

Khi curl hỏi, nhập password demo tương ứng:

- `reader`: `reader-demo-password`;
- `admin`: `admin-demo-password`.

Lần gọi reader vào `/api/me` kỳ vọng 200, body `Hello reader`. Reader vào `/api/admin` kỳ vọng 403 do thiếu role ADMIN. Admin vào `/api/admin` kỳ vọng 200, body `Admin admin`.

**Không viết** `curl -u reader:your-real-password` trong lịch sử shell của môi trường dùng thực. Không copy raw `Authorization` header chứa password thật vào ticket/log. Nếu cần debug, che header hoặc chỉ log request path và HTTP status.

### 7.3 Tự giải thích Base64 để hiểu giao thức

Đối với chuỗi `reader:reader-demo-password`, client tạo Base64 cho toàn bộ `username:password` và gắn:

```http
Authorization: Basic <BASE64_OF_USERNAME_COLON_PASSWORD>
```

Đây là **placeholder giao thức**, không phải header hợp lệ để paste và chạy. Dùng curl hoặc HTTP client để tạo header chuẩn. Base64 có thể có dấu `=` cuối chuỗi (padding) tùy số byte; các ký tự quốc tế trong username/password cần được client/server xử lý theo charset/chuẩn HTTP Basic tương thích.

Cốt lõi không thay đổi: **HTTPS/TLS mới bảo vệ đường truyền**, không phải Base64. Nếu client gửi token/credential qua kết nối không mã hóa, người trung gian có thể lấy được secret.

## 8. Kiểm thử HTTP Basic bằng WebTestClient

Kiểm thử quan trọng nhất là cho request **thực sự chạy qua Spring Security WebFilterChain** và dùng Basic header, thay vì tự đặt principal vào context rồi suy ra HTTP Basic đã hoạt động.

Tạo `src/test/java/com/example/basicwebflux/HttpBasicIntegrationTest.java`:

```java
package com.example.basicwebflux;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class HttpBasicIntegrationTest {

    @Autowired
    WebTestClient client;

    @Test
    void publicEndpointWorksWithoutCredentials() {
        client.get()
            .uri("/public/ping")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class)
            .isEqualTo("pong");
    }

    @Test
    void anonymousRequestIsChallenged() {
        client.get()
            .uri("/api/me")
            .exchange()
            .expectStatus().isUnauthorized()
            .expectHeader().exists("WWW-Authenticate");
    }

    @Test
    void correctBasicCredentialsAreAccepted() {
        client.get()
            .uri("/api/me")
            .headers(headers -> headers.setBasicAuth(
                "reader", "reader-demo-password"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class)
            .isEqualTo("Hello reader");
    }

    @Test
    void incorrectPasswordReturns401() {
        client.get()
            .uri("/api/me")
            .headers(headers -> headers.setBasicAuth(
                "reader", "not-the-password"))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void validReaderIsForbiddenOnAdminRoute() {
        client.get()
            .uri("/api/admin")
            .headers(headers -> headers.setBasicAuth(
                "reader", "reader-demo-password"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void adminCanAccessAdminRoute() {
        client.get()
            .uri("/api/admin")
            .headers(headers -> headers.setBasicAuth(
                "admin", "admin-demo-password"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class)
            .isEqualTo("Admin admin");
    }

    @Test
    void credentialsAreRequiredOnEachIndependentRequest() {
        client.get()
            .uri("/api/me")
            .headers(headers -> headers.setBasicAuth(
                "reader", "reader-demo-password"))
            .exchange()
            .expectStatus().isOk();

        client.get()
            .uri("/api/me")
            .exchange()
            .expectStatus().isUnauthorized();
    }
}
```

Chạy:

```bash
./gradlew test --tests '*HttpBasicIntegrationTest'
```

Hoặc Windows PowerShell:

```powershell
.\gradlew.bat test --tests '*HttpBasicIntegrationTest'
```

Những assertions trên xác minh đầy đủ:

- Endpoint public vẫn truy cập được dù không có credential.
- Không có Basic credentials thì protected request nhận 401/challenge.
- Password đúng được xác thực, SecurityContext có username.
- Password sai không biến thành authenticated request.
- User authenticated nhưng thiếu role ADMIN nhận 403.
- Admin đủ quyền nhận 200.
- Sau một request có Basic header, một **request mới không tự thừa hưởng** authentication của request trước trong cấu hình demo.

**Lưu ý:** Bài test dùng password in-memory demo và HTTP server random port trong process kiểm thử. Kết quả là **kỳ vọng từ cấu hình mẫu**, chưa phải stdout được ghi nhận từ một lần build thực tế ở đây. Nếu project thêm security configuration khác, profile khác, custom repository, proxy hoặc dependency MVC, cần kiểm tra config hoạt động trước khi kết luận về lỗi 401/403.

### 8.1 Tại sao không chỉ dùng mockUser?

`spring-security-test` có `mockUser()` và `@WithMockUser` để giúp test authorization. Chúng rất hữu ích nhưng **không chứng minh Basic header được parser và password đã được kiểm tra**. Một test mockUser có thể qua ngay cả khi HTTP Basic bị tắt.

Để kiểm tra chính xác bài này, dùng `headers.setBasicAuth(...)` trên `WebTestClient` và chạy full-context test như trên. Có thể bổ sung mock-user tests để cô lập authorization; hai cấp kiểm thử phục vụ hai mục tiêu khác nhau.

### 8.2 Kiểm tra thứ tự rule: bài thực hành regression

Thử chuyển:

```java
.pathMatchers(HttpMethod.GET, "/api/**").authenticated()
.pathMatchers(HttpMethod.GET, "/api/admin").hasRole("ADMIN")
```

thay cho hai dòng cùng thứ tự trong `SecurityConfig`. Khi đó rule `/api/**` đứng trước có thể chấp nhận reader vào `/api/admin`, khiến test `validReaderIsForbiddenOnAdminRoute` thất bại.

**Khắc phục:** đặt rule cụ thể hơn `/api/admin` trước `/api/**`, và duy trì test 403 nhằm phòng sai sót khi thêm endpoint mới.

## 9. Điều chỉnh HTTP Basic theo nhu cầu

Cấu hình cơ bản nhất chỉ cần:

```java
@Bean
SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
    return http
        .authorizeExchange(exchanges -> exchanges
            .anyExchange().authenticated())
        .httpBasic(Customizer.withDefaults())
        .build();
}
```

Đây là **một bean thay thế** khi muốn bảo vệ mọi request; cần import và có `ReactiveAuthenticationManager`/`ReactiveUserDetailsService` phù hợp. Dòng `httpBasic` không tự cung cấp password. Nếu đã dùng bean đầy đủ ở mục 5, đừng khai báo thêm bean tối giản này cùng lúc trừ khi bạn chủ động cấu hình nhiều chain với thứ tự/matcher.

### 9.1 Chỉ định ReactiveAuthenticationManager riêng

Khi muốn xác thực password qua cơ chế tùy chỉnh, `HttpBasicSpec` cho phép đặt một `ReactiveAuthenticationManager`:

```java
@Bean
SecurityWebFilterChain securityWebFilterChain(
        ServerHttpSecurity http,
        ReactiveAuthenticationManager manager) {

    return http
        .authorizeExchange(exchanges -> exchanges
            .anyExchange().authenticated())
        .httpBasic(basic -> basic.authenticationManager(manager))
        .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
        .build();
}
```

Đây là **một phương án thay thế** cho bean `securityWebFilterChain` ở mục 5; cần một bean `ReactiveAuthenticationManager` hợp lệ được cấu hình ở nơi khác. Import `ReactiveAuthenticationManager` từ `org.springframework.security.authentication`. Manager phải kiểm chứng credential trước khi trả `Authentication` đã được xác thực, không được trả `Mono.just(...)` với role từ input chưa kiểm chứng.

Bên cạnh manager, `ServerHttpSecurity.HttpBasicSpec` còn cho phép tùy chỉnh `authenticationEntryPoint`, `authenticationFailureHandler` và `securityContextRepository`. Tùy chỉnh các điểm này chỉ khi có yêu cầu chính sách và test tương ứng; mặc định là điểm khởi đầu tốt.

### 9.2 Khi nào nên tắt HTTP Basic?

Nếu ứng dụng đổi hoàn toàn sang OAuth2 Bearer JWT hoặc chỉ form login, không nên để Basic mở ngoài ý muốn.

```java
http
    .authorizeExchange(exchanges -> exchanges
        .anyExchange().authenticated())
    .httpBasic(ServerHttpSecurity.HttpBasicSpec::disable)
    .oauth2ResourceServer(oauth2 -> oauth2.jwt(
        Customizer.withDefaults()
    ));
```

Đây là **snippet cấu hình**, không phải file hoàn chỉnh; phải có dependency Resource Server, `ReactiveJwtDecoder` và cấu hình issuer/audience phù hợp. Không gọi `http.build()` hai lần hoặc ghép mảnh này cạnh `httpBasic(withDefaults())` trong cùng chain nếu mục tiêu là tắt Basic. Một ứng dụng OIDC/browser có thể sử dụng `oauth2Login(...)` hoặc phương án phiên khác thay vì Basic.

**Phân biệt:** `httpBasic(...disable)` tắt cơ chế **HTTP Basic**; không tự tắt tất cả cơ chế xác thực hay làm endpoint trở thành public. `authorizeExchange` vẫn ra quyết định cho route.

### 9.3 Nhiều SecurityWebFilterChain: Basic chỉ cho một khu vực

Một hệ thống có thể muốn:

- `/internal/**`: dùng HTTP Basic với account của automation.
- `/api/**`: dùng JWT Resource Server.
- `/web/**`: dùng OAuth2 Login/session.

Thiết kế này thường cần **nhiều bean `SecurityWebFilterChain`**, mỗi bean có `securityMatcher` và `@Order`; Spring Security chọn **chain đầu tiên phù hợp**, không áp dụng dồn mọi chain cho cùng request.

Sơ đồ khái niệm:

```text
@Order(1) chainInternal  -> securityMatcher("/internal/**") -> httpBasic()
@Order(2) chainApi       -> securityMatcher("/api/**")      -> jwt()
@Order(3) chainWeb       -> catch-all                       -> oauth2Login()
```

Đây là **pseudocode kiến trúc**, không phải Java độc lập. Trong ứng dụng thực, phải chọn matchers, authentication providers và fallback chain đúng; nếu chỉ tạo Basic chain khớp `/internal/**` rồi bỏ hết chain khác, những URL ngoài matcher **không được bảo vệ bởi chain đó**. Không dựa vào `anyExchange().authenticated()` ở một chain có matcher hẹp để bảo vệ mọi URL.

### 9.4 Đặt HTTPS/TLS, không nhầm với Base64

Ở production, bảo vệ kênh HTTP bằng TLS, triển khai proxy/ingress và chứng chỉ đúng, chỉ chấp nhận credential qua HTTPS. Có thể cấu hình HTTPS enforcement ở reverse proxy hoặc Spring Security theo môi trường. Basic thường gửi lại username/password với **mỗi request**, làm tăng độ nhạy cảm của access logs và đường truyền.

Đừng coi `Authorization: Basic ...` như JWT có expiry/scope/audience. Basic mang credential có thể dùng lâu dài nếu account/password chưa thay; cần quản lý vòng đời, bảo vệ xác thực và chính sách chống brute-force ở tầng hệ thống.

## 10. HTTP Basic và session, CSRF, CORS

### 10.1 Basic không tự yêu cầu cookie session

Trong cấu hình HTTP Basic WebFlux, Basic filter xác thực **mỗi request có header phù hợp**; mặc định `HttpBasicSpec` dùng `NoOpServerSecurityContextRepository` cho việc lưu context của Basic. Vì vậy ví dụ không dùng Basic như cơ chế “đăng nhập một lần rồi dựa trên session”.

Tuy nhiên, **không kết luận toàn ứng dụng tuyệt đối stateless** chỉ vì đã bật Basic. Các phần khác như form login, OAuth2, CSRF token repository, WebSession và các thành phần custom có thể dùng session. Kiểm tra toàn bộ cấu hình trước khi tuyên bố stateless hoặc triển khai policy cookie.

### 10.2 Giữ CSRF khi có browser tự gửi credential

Nếu client luôn dùng header `Authorization` được chủ động thêm bởi code và **không được browser tự gửi** qua các request cross-origin, threat model có thể khác với ứng dụng có cookie/session. Nhưng HTTP Basic do trình duyệt ghi nhớ có thể được trình duyệt gửi tự động cho cùng protection space. **Không coi “Basic” là bằng chứng đủ để tắt CSRF**.

Trong Spring Security WebFlux, CSRF thường được bật theo mặc định. Với GET/HEAD đọc dữ liệu, không nên có side effect. Với POST/PUT/PATCH/DELETE, xác định cách client nhận và gửi CSRF token nếu có nguy cơ request giả mạo trên browser. Nếu chỉ là API machine-to-machine được xác định rõ, có thể thiết kế security chain/matcher khác và vô hiệu CSRF **cho phạm vi phù hợp** sau khi đánh giá, không tắt toàn app một cách máy móc.

### 10.3 CORS không thay thế xác thực

CORS giới hạn trang web nào được browser cho phép truy cập response và điều khiển preflight; nó không chứng minh identity. Browser dùng JavaScript với `Authorization` thường kích hoạt CORS preflight khi khác origin. Cần cho phép các headers/methods cần thiết **đúng origin** qua policy CORS, không tùy tiện đặt `Access-Control-Allow-Origin: *` kèm credentials.

CORS preflight có thể bị SecurityWebFilterChain chặn nếu không cấu hình đúng. Kiểm thử tình huống này riêng; không giải quyết bằng cách public toàn bộ `/api/**`.

## 11. Chẩn đoán lỗi 401, 403 và 404

### 11.1 Bảng nguyên nhân thường gặp

| Hiện tượng | Nhận định có khả năng | Hướng kiểm tra |
| --- | --- | --- |
| Không gửi `Authorization` → 401 | Đúng khi gọi protected route | Kiểm tra route/rules và header `WWW-Authenticate` |
| Đã gửi Basic nhưng vẫn 401 | Password sai, username không tồn tại, encoder không khớp, header lỗi | Kiểm tra user store/encoder; không log password thô |
| Có user authenticated nhưng 403 | Thiếu authority/role, hoặc CSRF ở method unsafe | Kiểm tra `hasRole`/`hasAuthority`, CSRF token và HTTP method |
| GET public lại 401 | Rule `permitAll` không match, chain khác được chọn | Kiểm tra path/method matcher, `securityMatcher` và `@Order` |
| Reader truy cập admin thành công | Rule `/api/**` đặt trước rule admin | Sắp xếp matcher từ cụ thể đến tổng quát |
| 302 redirect sang `/login` thay vì 401 | Form login/entry point khác vẫn active | Tắt form login ở API chain hoặc kiểm tra chain được chọn |
| 404 trên route dự kiến | Controller chưa scan, path sai, handler không tồn tại | Kiểm tra mappings; bảo mật không tạo route |
| POST authenticated nhận 403 | CSRF token thiếu/không hợp lệ, hoặc authorization deny | Không mặc nhiên tắt CSRF; kiểm tra đường xử lý |
| User được dùng trong unit test nhưng HTTP thật vẫn 401 | Test bypass filter hoặc header Basic chưa được gửi | Dùng full-context `WebTestClient` và Basic header |
| 401 sau khi gửi đúng password đã đổi | Password hash/user store thay đổi, cache/account policy | Kiểm tra nguồn users và version/config thực |
| 401 khi gửi Bearer token | Basic filter không xác thực Bearer credential | Bật OAuth2 Resource Server nếu API dùng Bearer |
| Basic hoạt động trong MVC nhưng không trong WebFlux | Dùng nhầm Servlet DSL hoặc Boot chọn MVC | Kiểm tra `ApplicationContext` và loại security chain |

HTTP status không có nguồn duy nhất: **401** thường liên quan đến authentication challenge/failure; **403** có thể do thiếu authorization hoặc CSRF; **404** liên quan đến handler mapping sau khi request đi qua các filter. Xem security logs và integration tests để phân biệt, không chỉ nhìn một status.

### 11.2 Vì sao UserDetailsService phải là reactive?

Mẫu bài này dùng `MapReactiveUserDetailsService`. Trong hệ thống thật, bạn có thể triển khai `ReactiveUserDetailsService.findByUsername(String)` trả về `Mono<UserDetails>` từ database/repository reactive. Bộ authentication kiểm tra password bằng `PasswordEncoder.matches(...)` và tạo authenticated principal phù hợp.

Không viết mã blocking database trong event-loop và gói kết quả bằng `Mono.just(blockingCall())`: `blockingCall()` vẫn chạy đồng bộ trước khi Mono được tạo. Nếu bắt buộc tích hợp legacy blocking, đưa sang executor/scheduler phù hợp, áp dụng giới hạn tải và đo latency.

### 11.3 PasswordEncoder và tiền tố hash

`PasswordEncoderFactories.createDelegatingPasswordEncoder()` sử dụng cơ chế encoding có ID như `{bcrypt}...`. Lỗi `There is no PasswordEncoder mapped for the id "null"` thường xuất hiện khi đưa password plain text không có prefix vào `DelegatingPasswordEncoder` theo cách không hợp lệ.

Trong demo, gọi `encoder.encode(...)` trước khi tạo user, nên tránh trường hợp này. Production nên lưu **mật khẩu được băm** bằng password hashing algorithm phù hợp (bcrypt/Argon2/PBKDF2 theo chính sách), thay vì ghi mật khẩu gốc vào database hoặc property file. Không hardcode `{noop}` để tránh lỗi.

## 12. So sánh HTTP Basic với Bearer/JWT và form login

| Tiêu chí | HTTP Basic | Bearer/JWT Resource Server | Form login / session |
| --- | --- | --- | --- |
| Header/credential | Username/password trong Base64 | `Authorization: Bearer <token>` | Form submit, thường tạo cookie session |
| Xác thực | Password authentication manager/user store | JWT decoder/opaque introspection; issuer/audience/scope | Login flow, session/security context |
| Gửi credential | Thường mỗi HTTP request | Access token mỗi request | Cookie/session tự được client gửi |
| Vai trò phù hợp | Admin API nội bộ, demo, client đơn giản có TLS | REST API và service-to-service chuẩn hóa | Ứng dụng web browser truyền thống |
| Hết hạn/thu hồi | Phụ thuộc chính sách tài khoản/password | Token expiry, revocation/introspection và thiết kế IdP | Session expiry, logout/invalidation |
| Nguy cơ nổi bật | Lộ password khi log/HTTP; brute-force | Lộ bearer token; sai issuer/audience/algorithm | CSRF/session fixation/cookie bảo mật |

Không nói HTTP Basic “luôn kém an toàn” trong mọi ngữ cảnh: có TLS, quản lý secret, giới hạn quyền, rate limit và kiểm soát vận hành thì nó có thể phù hợp cho client đơn giản. Tuy nhiên, đối với API quy mô lớn và hệ thống cần giới hạn scope, token expiry, delegated identity, OAuth2/OIDC hoặc workload identity thường phù hợp hơn việc chuyển password chính của user trên mỗi request.

## 13. Những lỗi cấu hình nên tránh

1. **Nhầm `SecurityFilterChain` với `SecurityWebFilterChain`:** loại Servlet không phải thứ WebFlux request pipeline dùng. Chọn đúng `ServerHttpSecurity` và runtime reactive.
2. **Chỉ bật Basic, không cấu hình authorization:** có thể tạo policy mặc định khác dự kiến. Khai báo `authorizeExchange` tường minh và test mọi endpoint nhạy cảm.
3. **Chỉ tạo user nhưng không gọi `httpBasic(...)`:** Spring Security có default cấu hình tùy ngữ cảnh, nhưng một custom chain không nên dựa vào mặc định mơ hồ. Bật Basic tường minh trong bean.
4. **Đặt matcher rộng trước matcher hẹp:** `/api/**` có thể cho reader đi qua `/api/admin`. Kiểm thử rule precedence.
5. **Dùng `{noop}` hoặc plaintext trong production:** bảo vệ mật khẩu bằng encoder thích hợp và credential store.
6. **Gửi Basic qua HTTP thật:** Base64 dễ giải mã. Chỉ thử HTTP trên localhost với dummy data; bắt buộc HTTPS/TLS khi triển khai.
7. **Log `Authorization` header hoặc password:** log scrubbing ở gateway/reverse proxy/application, tránh curl command có real password.
8. **Tắt CSRF máy móc:** đặc biệt nguy hiểm với browser có cơ chế tự gửi credential; cần xem threat model.
9. **Đưa username tự khai vào `Authentication`:** bypass password verification. Để manager/provider xử lý credential.
10. **Dùng `@WithMockUser` làm bằng chứng HTTP Basic hoạt động:** mockUser bypass Basic header parsing; cần integration test với header.
11. **Không kiểm tra nhiều chains:** Basic config có thể nằm trong chain không match URL mong muốn; dùng `securityMatcher` và `@Order` đúng.
12. **Nhầm 401 và 403:** thiếu/sai credential khác với đã xác thực nhưng thiếu quyền. Phân biệt trong test và xử lý client.
13. **Cho phép request thay đổi dữ liệu qua GET:** CSRF có thể giả định GET an toàn; dùng HTTP method đúng và bổ sung CSRF protection.
14. **Giả định Basic luôn hoàn toàn stateless:** các thành phần security khác có thể dùng WebSession; kiểm tra toàn bộ cấu hình.
15. **Không kiểm tra rate limiting và brute-force:** Basic có thể bị thử password hàng loạt; cần bảo vệ ở ingress/IdP/account controls.

## 14. Bài tự kiểm tra

**Câu 1.** Trong WebFlux, đoạn nào bật HTTP Basic đúng khi viết `SecurityWebFilterChain`?

**Đáp:** `.httpBasic(Customizer.withDefaults())` trên `ServerHttpSecurity`, hoặc cấu hình `.httpBasic(basic -> ...)` khi cần custom. Không dùng Servlet `HttpSecurity` cho pipeline reactive.

**Câu 2.** `Authorization: Basic ...` có được mã hóa bảo mật không?

**Đáp:** Không. Phần sau Basic là Base64 của `username:password`, có thể giải mã. HTTPS/TLS bảo vệ credential trên đường truyền.

**Câu 3.** Tại sao request chưa đăng nhập nhận 401 còn reader vào `/api/admin` nhận 403?

**Đáp:** 401 là yêu cầu xác thực, còn reader có principal hợp lệ nhưng không có `ROLE_ADMIN` nên bị từ chối ở authorization.

**Câu 4.** Nếu khai báo `.pathMatchers("/api/**").authenticated()` trước `.pathMatchers("/api/admin").hasRole("ADMIN")` thì sao?

**Đáp:** Rule rộng có thể match trước làm mất ràng buộc admin. Đưa rule cụ thể lên trước.

**Câu 5.** Có cần lưu username/password vào cookie session mới dùng được Basic không?

**Đáp:** Không. Client có thể gửi header Basic trên mỗi request. Nhưng các thành phần khác của ứng dụng vẫn có thể dùng session, nên không đánh đồng bật Basic với mọi thứ stateless.

**Câu 6.** Có phải tắt CSRF mới bật được HTTP Basic?

**Đáp:** Không. GET trong bài hoạt động khi CSRF vẫn bật. Với method thay đổi trạng thái, quyết định CSRF theo browser/client/credential và nguy cơ giả mạo, không tắt toàn cục vô điều kiện.

**Câu 7.** Vì sao `@WithMockUser` test pass nhưng curl Basic vẫn trả 401?

**Đáp:** MockUser chỉ đặt test authentication và có thể bỏ qua luồng parse/verify Basic credentials. Kiểm tra username/password, encoder, `httpBasic(...)`, active chain và dùng `WebTestClient.headers(setBasicAuth)` để test thực.

**Câu 8.** Nếu API dùng Bearer JWT, có nên dùng `httpBasic` để đọc JWT không?

**Đáp:** Không. Bearer JWT dùng cơ chế OAuth2 Resource Server với JWT decoder và validation đúng. Basic dùng username/password. Hai scheme có converter/manager khác nhau.

## 15. Checklist trước khi hoàn thành

- [ ] Boot đang chạy **WebFlux reactive**, không vô tình dùng Servlet do dependency MVC.
- [ ] Có `SecurityWebFilterChain` với `ServerHttpSecurity` và `.httpBasic(Customizer.withDefaults())`.
- [ ] Form login được giữ hoặc tắt có chủ đích cho client của từng chain.
- [ ] Có `ReactiveUserDetailsService` hoặc `ReactiveAuthenticationManager` hợp lệ và password encoder an toàn.
- [ ] `authorizeExchange` được cấu hình rõ, matcher cụ thể đặt trước matcher tổng quát và có rule cuối an toàn.
- [ ] Endpoint public trả 200 không cần credential; protected endpoint trả 401 khi không có hoặc sai Basic credentials.
- [ ] Đúng username/password trả 200; user thiếu role nhận 403; admin đủ role nhận 200.
- [ ] Browser/API CSRF, CORS, HTTP methods, session semantics được đánh giá.
- [ ] Production dùng HTTPS/TLS, bảo vệ password/Authorization logs, rate limit và credential rotation.
- [ ] Đã chạy integration test HTTP Basic thật, không chỉ test với mockUser.
- [ ] Nếu nhiều `SecurityWebFilterChain`, đã kiểm tra `securityMatcher`, `@Order` và chain thực sự được chọn.

**Kết luận:** Để bật HTTP Basic trong Spring Security reactive, khai báo `SecurityWebFilterChain` dùng `ServerHttpSecurity.httpBasic(Customizer.withDefaults())`, cung cấp user service/manager có kiểm chứng password, và đặt `authorizeExchange` cho các endpoint. HTTP Basic xác thực người gọi; authorization mới quyết định quyền. Kiểm thử 200/401/403 với `WebTestClient` để chứng minh hệ thống chạy đúng; luôn dùng TLS khi truyền credential thực.

### Tài liệu tham khảo chính thức

- [Spring Security 6.5 — WebFlux Security và cấu hình httpBasic](https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html)
- [Spring Security 6.5 — ServerHttpSecurity API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.html)
- [Spring Security 6.5 — ServerHttpSecurity.HttpBasicSpec API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.HttpBasicSpec.html)
- [Spring Security 6.5 — WebFlux CSRF](https://docs.spring.io/spring-security/reference/6.5/reactive/exploits/csrf.html)
- [Spring Security — WebFlux testing authentication](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/authentication.html)
- [Spring Framework — WebFlux Reactive Stack](https://docs.spring.io/spring-framework/reference/web/webflux.html)
- [RFC 7617 — The "Basic" HTTP Authentication Scheme](https://www.rfc-editor.org/rfc/rfc7617)
