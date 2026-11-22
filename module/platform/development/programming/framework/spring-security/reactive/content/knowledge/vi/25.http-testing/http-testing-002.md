# Phân biệt kiểm thử bằng ApplicationContext với kiểm thử qua máy chủ thật — Spring Security WebFlux

## Mục tiêu học tập

Bài học thuộc **Spring Security – reactive**, nhóm **Kiểm thử HTTP**. Sau khi học, bạn có thể:

1. Phân biệt `WebTestClient.bindToApplicationContext(...)` và `WebTestClient.bindToServer()` theo cơ chế đưa request đến server, phạm vi Spring beans, WebFilter và HTTP transport.
2. Biết `@SpringBootTest` mặc định dùng `WebEnvironment.MOCK`, **không mở HTTP server**, trong khi `@SpringBootTest(webEnvironment = RANDOM_PORT)` khởi động embedded server thực.
3. Phân biệt full ApplicationContext với `@WebFluxTest` web slice, `bindToController(...)` và `bindToRouterFunction(...)`; không nhầm từ "mock web" với "tất cả services đã mock".
4. Kiểm tra Spring Security reactive bằng `SecurityWebFilterChain`, `SecurityMockServerConfigurers.springSecurity()`, `mockUser()` và Basic Authorization headers.
5. Phân biệt kiểm thử **authorization với Authentication giả lập** và kiểm thử **HTTP Basic password/JWT signature/opaque introspection** thật.
6. Tạo project Java 17+ / Spring Boot 3.5.16 có ba nhóm test: ApplicationContext in-memory, WebFlux slice, và HTTP thật qua Reactor Netty, dùng `WebTestClient` cùng một controller.
7. Chọn kiểu test cho authn/authz, JSON, status code, error handling, streaming/SSE, port, network, proxy/TLS, external IdP và DB.
8. Tránh false confidence do security chain bị bỏ qua, nhầm `@AutoConfigureWebTestClient` với real-server, dùng `@MockitoBean` thay service cần kiểm, hoặc dùng `mockJwt()` rồi kết luận JWT signature đã verify.

> **Baseline:** Java 17+, Spring Boot **3.5.16**, Spring Security **6.5.x**, Spring Framework 6.2.x, WebFlux và Reactor Netty. Spring Boot 3.5.16 là bản cuối nhánh 3.5 có hỗ trợ OSS; production mới nên chuyển sang dòng được hỗ trợ và cập nhật bản vá. Bài dùng user/password `{noop}` chỉ cho demo test local, **không dùng trong sản phẩm**.

---

## 1. Cùng một WebTestClient DSL nhưng hai đường đi của request

`WebTestClient` là một client API của Spring Test. Phần lớn các kiểm thử nhìn giống nhau:

```java
client.get().uri("/api/reports")
        .exchange()
        .expectStatus().isOk()
        .expectBody(String.class)
        .isEqualTo("report-for-reader");
```

Tuy nhiên, **đường đi của request không thể suy ra chỉ từ DSL**. Nó phụ thuộc cách tạo `client`.

### 1.1. Bind vào ApplicationContext — mock HTTP exchange

```text
JUnit Test
   |
   | WebTestClient.bindToApplicationContext(context)
   v
Mock ServerHttpRequest / Mock ServerHttpResponse
   |
   v
Spring WebHttpHandlerBuilder
   |
   v
WebFilter chain (gồm Security nếu context đã cấu hình)
   |
   v
HandlerMapping / HandlerAdapter / Controller
   |
   v
Mono / Flux -> Mock response -> expectBody / expectStatus

Không có HTTP listener, không có TCP socket tới server.
```

Spring Test tạo request/response giả lập và đưa trực tiếp vào **WebFlux WebHandler chain** trong cùng JVM. Nếu ApplicationContext chứa security filters, conversion, handlers và exception handlers thật, chúng vẫn chạy; **không phải** request HTTP thật đi qua Reactor Netty.

Điều này rất hữu ích cho hầu hết kiểm thử HTTP application behavior vì tránh chi phí bind port và network transport.

### 1.2. Bind vào server đang chạy — HTTP network

```text
JUnit test
   |
   | WebTestClient.bindToServer()
   | baseUrl=http://127.0.0.1:<random-port>
   v
HTTP client -> TCP loopback -> Reactor Netty server
   |
   v
Spring WebFlux WebFilters / SecurityWebFilterChain
   |
   v
HandlerMapping -> Controller -> Service
   |
   v
Netty HTTP response -> WebTestClient assertions
```

Đây là HTTP request/response qua socket thực. Với `@SpringBootTest(RANDOM_PORT)`, Spring Boot khởi động embedded server và hệ điều hành chọn một cổng tạm. Mục đích là kiểm tra **network entrypoint**, bên cạnh behavior của filter/controller.

### 1.3. So sánh theo từng trục

| Đặc điểm | bindToApplicationContext | bindToServer |
| --- | --- | --- |
| Có cần HTTP server thật? | Không | Có |
| Có TCP/socket? | Không | Có |
| Có sử dụng WebFlux controller thật? | Có nếu được nạp | Có |
| Có chạy WebFilter và security chain? | Có nếu nạp/áp đúng | Có theo app đang chạy |
| Có kiểm tra port bind và HTTP parser? | Không | Có |
| Có kiểm HTTP Basic filter qua header? | Có thể, nếu security/user store thật | Có |
| Có kiểm JWT signature khi dùng `mockJwt()`? | Không | Không có `mockJwt()` qua network; phải gửi JWT thật |
| Có kiểm TLS/ingress production? | Không | Chỉ khi **thực sự** dựng TLS/ingress |
| Có tự mock mọi service/DB? | Không | Không |
| Thường nhanh hơn? | Có | Chậm hơn do mở server/I/O |
| Điểm mạnh | Controller, WebFilter, authz, status, response mapping | Real HTTP transport, server lifecycle, authn on the wire |

**Hai trục độc lập:** "full context vs web slice" mô tả Spring beans được nạp; "mock HTTP vs real HTTP" mô tả transport. Không dùng "full integration" như một nhãn mơ hồ khi báo coverage.

## 2. Spring Boot test annotations: khác nhau ở điều gì?

### 2.1. @SpringBootTest mặc định

```java
@SpringBootTest
@AutoConfigureWebTestClient
class FullContextWithoutSocketTests {
    // webEnvironment mặc định = MOCK.
}
```

Spring Boot tải **ApplicationContext đầy đủ**, nhưng **không mở HTTP listener**. Với WebFlux app, `@AutoConfigureWebTestClient` cấu hình client dùng mock HTTP exchange. Bạn cũng có thể tự viết `WebTestClient.bindToApplicationContext(context)` để kiểm soát thiết lập.

Các beans như Service, Repository và `SecurityWebFilterChain` có thể vẫn là bean thật. Nếu service kết nối DB/remote API, nó vẫn có thể tạo I/O **ra ngoài**; chỉ *inbound HTTP transport* được mô phỏng.

### 2.2. @SpringBootTest(RANDOM_PORT)

```java
@SpringBootTest(webEnvironment =
        SpringBootTest.WebEnvironment.RANDOM_PORT)
class EmbeddedHttpTests {
    @LocalServerPort int port;
}
```

Spring Boot tải context và **chạy embedded HTTP server**. Với dependency chỉ có WebFlux, nó thường là Reactor Netty. `@LocalServerPort` lấy số cổng thực tế; không đặt cứng 8080.

`DEFINED_PORT` cũng khởi động server thực nhưng trên port đã cấu hình, dễ xung đột khi CI chạy song song. `NONE` không có web environment; `MOCK` là default.

### 2.3. @WebFluxTest — slice test

```java
@WebFluxTest(ReportController.class)
class ReportControllerSliceTests {
    // Controller + WebFlux infrastructure; không mở server.
}
```

Spring Boot chỉ nạp web-related components theo chính sách test slice. Service thông thường không được scan tự động; dùng `@MockitoBean` hoặc `@Import` theo mục tiêu test.

**Lưu ý với Security:** `@WebFluxTest` **không tự nhận ra custom SecurityWebFilterChain bean của ứng dụng**. Để kiểm đúng security policy, hãy `@Import(HttpSecurityConfiguration.class)` hoặc dùng full-context test. Một slice test trả 200 không chứng minh security chain production chạy, trừ khi xác nhận cấu hình chain tương ứng.

### 2.4. bindToController và bindToRouterFunction

```java
// Standalone controller fragment — không có WebFlux app SecurityWebFilterChain.
WebTestClient standalone = WebTestClient
        .bindToController(new PublicController())
        .build();
```

`bindToController(...)` tạo handler infrastructure cho controller được chỉ định. `bindToRouterFunction(router)` kiểm functional routing qua mock request. Không mặc định có đầy đủ bean/security configuration từ ứng dụng.

Hãy dùng chúng để kiểm URL binding, conversion hoặc payload của controller cô lập, **không** kết luận protected endpoint đã được security production bảo vệ nếu SecurityWebFilterChain không được đưa vào.

### 2.5. Ma trận chọn nhanh

| Kiểu test | Spring context | Incoming HTTP | Công dụng |
| --- | --- | --- | --- |
| bindToController | Không yêu cầu full context | Mock | Handler đơn lẻ |
| @WebFluxTest + WebTestClient | Slice | Mock | Controller/serialization + imported security |
| @SpringBootTest(MOCK) | Full app | Mock | Full-context in-process integration |
| @SpringBootTest(RANDOM_PORT) | Full app | Thật qua socket | Real HTTP integration |
| bindToServer tới staging | App chạy bên ngoài | Thật qua network | Contract/smoke/E2E theo môi trường |

**Không cần** thêm `@ExtendWith(SpringExtension.class)` khi class đã dùng Spring Boot test annotation trong JUnit 5.

---

## 3. Security WebFilters và mock Authentication

### 3.1. Spring Security WebFlux sử dụng Reactor Context

Trong ứng dụng reactive, Spring Security xây dựng `SecurityWebFilterChain` qua `ServerHttpSecurity`, xác thực rồi đưa Authentication vào reactive `SecurityContext`. Handler/service truy cập identity trong reactive pipeline.

Nếu WebTestClient bind vào context, filter chain chạy nếu đã được đăng ký và test support được cấu hình:

```java
WebTestClient client = WebTestClient
        .bindToApplicationContext(context)
        .apply(SecurityMockServerConfigurers.springSecurity())
        .configureClient()
        .build();
```

`.apply(springSecurity())` đặc biệt quan trọng khi dùng `SecurityMockServerConfigurers.mockUser()`, `mockJwt()` hoặc `mockOpaqueToken()`.

### 3.2. mockUser() dùng cho authorization

```java
client.mutateWith(mockUser("reader").authorities(
        new SimpleGrantedAuthority("SCOPE_reports.read")))
    .get().uri("/api/reports")
    .exchange()
    .expectStatus().isOk();
```

Đây là cách kiểm "nếu Authentication có SCOPE_reports.read thì route có cho truy cập không?". Nó **không** kiểm tra password, IdP, JWT signature, JWKS hoặc opaque token introspection.

**Ngược lại**, nếu bindToApplicationContext với security/user store thật rồi gửi:

```java
client.get().uri("/api/reports")
        .headers(h -> h.setBasicAuth("reader", "reader-pass"))
        .exchange()
        .expectStatus().isOk();
```

thì **HTTP Basic WebFilter và password check vẫn có thể hoạt động thực trong mock exchange**, vì chúng là một phần của application chain. Chỉ phần HTTP transport/socket bị mô phỏng.

Do đó không nên nói "ApplicationContext mock test hoàn toàn không kiểm authentication"; cần phân biệt **mock Authentication** với **mock HTTP transport**.

### 3.3. mockJwt() và mockOpaqueToken()

Trong WebFlux Resource Server JWT:

```java
// FRAGMENT: dùng trong test app có oauth2ResourceServer().jwt().
client.mutateWith(mockJwt().authorities(
        new SimpleGrantedAuthority("SCOPE_reports.read")))
    .get().uri("/api/reports")
    .exchange()
    .expectStatus().isOk();
```

Trong WebFlux Resource Server Opaque:

```java
// FRAGMENT: dùng trong test app có oauth2ResourceServer().opaqueToken().
client.mutateWith(mockOpaqueToken().authorities(
        new SimpleGrantedAuthority("SCOPE_reports.read")))
    .get().uri("/api/reports")
    .exchange()
    .expectStatus().isOk();
```

Hai fragment này minh họa **authorization tests** và **không** thuộc project HTTP Basic ở mục 6. `mockJwt()` không phát RSA-signed token để `ReactiveJwtDecoder` thật verify. `mockOpaqueToken()` không POST tới introspection endpoint.

Muốn kiểm JWT signature/issuer/audience/time, hãy sinh token có chữ ký thật từ private key test, cấu hình JWKS fixture public key và gửi Bearer qua real HTTP; negative tests với chữ ký sai/iss/aud/exp/nbf. Muốn kiểm opaque token, dùng `ReactiveOpaqueTokenIntrospector` thật kết nối MockWebServer/WireMock trả `active=true/false`, kiểm cả Basic introspection client credentials.

### 3.4. Authorization status cần test cả trường hợp thất bại

| Tình huống | HTTP status thường thấy |
| --- | --- |
| Public GET | 200 |
| Protected GET, không credential | 401 |
| Basic sai password / Bearer invalid | 401 |
| Authenticated, thiếu authority | 403 |
| Authenticated, có authority cần thiết | 200 |
| Request bị `denyAll()` nhưng không authenticated | Có thể 401 hoặc 403 tùy exception entrypoint |
| Controller trả lỗi validation | 4xx theo `@ControllerAdvice` |
| Bất thường network/upstream | Tùy error handling, không được suy luôn 401 |

Một security regression có thể không lộ khi test chỉ happy path 200. Nên có ít nhất 401 và 403 để phân biệt authentication vs authorization.

---

## 4. Khi nào ApplicationContext test là đủ?

Nếu mục tiêu chỉ là chứng minh route `GET /api/reports` yêu cầu authority, controller trả đúng JSON/text, request validation và exception mapping, in-memory `WebTestClient` thường đủ. Khi context nạp đủ filters/beans, nó chạy WebFlux handler chain thật và không cần port.

Nó phù hợp cho:

- URL/method mapping, path/query binding, validation.
- Authentication / authorization policy ở WebFilter theo cấu hình nạp vào.
- Serializing/deserializing body, status, headers, content negotiation.
- Controller Advice và exception handlers.
- Reactive `Mono`/`Flux` composition ở tầng handler.
- Nhiều input boundary cases và negative authz tests.
- Test context với mocked/in-memory service giúp chạy nhanh hơn.

**Không phù hợp để kết luận** rằng Netty đã mở cổng thành công, response đi qua TCP parser, HTTPS handshake thành công, reverse proxy đã sanitize headers, HTTP/2 negotiation chạy đúng, hoặc client disconnect/backpressure hoạt động trong network thực.

**Bẫy:** `@WebFluxTest` có thể không nạp custom security chain hoặc service. `@SpringBootTest(MOCK)` nạp nhiều beans hơn và có thể còn thực sự gọi DB/HTTP upstream nếu không stub.

## 5. Khi nào cần máy chủ thật?

Dùng `@SpringBootTest(RANDOM_PORT)` + `WebTestClient.bindToServer()` để kiểm:

1. Embedded Reactor Netty/Tomcat phù hợp app type thực sự khởi động, bind được port.
2. HTTP request/response đi qua socket TCP, network client và server request parser.
3. Header Basic/Bearer được truyền qua wire và xử lý bởi actual SecurityWebFilterChain.
4. Mapping/exception handling hoạt động với một request HTTP thật.
5. Streaming, chunking, SSE, compressed payload, timeout và cancellation khi viết test riêng.
6. Code phụ thuộc remote address, base URL, forwarded headers hoặc server-specific options trong phạm vi cấu hình test.
7. Cấu hình server response size, path encoding, Host header, status và Content-Type theo test.

**Nhưng** một localhost HTTP test **không tự kiểm** production TLS, mTLS, proxy/load balancer, DNS, firewall, IdP thật, OAuth2 auth-code grants hay cluster. Chỉ những thành phần bạn đưa vào test mới được xác minh.

### Transaction / data isolation

Khi test gọi server thật, request được server xử lý ở một execution/reactive context riêng; transaction trên test method không đảm bảo rollback các database writes bên server. Dùng cleanup/ephemeral DB, unique test IDs hoặc R2DBC transactional fixtures có kiểm chứng. Không dựa vào `@Transactional` trên JUnit class để "chắc chắn" khôi phục mọi thay đổi phía HTTP server.

---

## 6. Demo Java 17+ Spring Boot 3.5.16

Dự án cố tình đơn giản để thấy khác biệt do **transport** chứ không do DB/IdP:

- HTTP Basic users trong bộ nhớ.
- `reader` có `SCOPE_reports.read` và password `reader-pass`.
- `viewer` chỉ có `SCOPE_profile.read` và password `viewer-pass`.
- `GET /public/ping` public.
- `GET /api/reports` yêu cầu `SCOPE_reports.read` và trả body từ `ReportService`.
- Nhóm A dùng full ApplicationContext mock; nhóm B web slice với mock service; nhóm C real HTTP.
- Tất cả test file cùng package `example.httpmodes` để Spring Boot tìm main configuration.

**Các mật khẩu và `{noop}` chỉ dành cho lab. Không dùng trong production.**

### 6.1. Cấu trúc thư mục

```text
webflux-http-test-modes/
  settings.gradle
  build.gradle
  src/main/java/example/httpmodes/
    HttpModesApplication.java
    HttpSecurityConfiguration.java
    ReportService.java
    ReportController.java
  src/test/java/example/httpmodes/
    MockApplicationContextTests.java
    WebFluxSliceTests.java
    RealHttpServerTests.java
```

### 6.2. Gradle Groovy

**`settings.gradle`:**

```groovy
rootProject.name = 'webflux-http-test-modes'
```

**`build.gradle`:**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
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
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

- Spring WebFlux starter mang WebClient, WebTestClient-related classpath và Reactor Netty.
- Security starter cung cấp WebFlux HTTP Basic filters và reactive user service.
- Test starter mang JUnit5/Spring Test/Mockito, `spring-security-test` mang `SecurityMockServerConfigurers`.
- Không thêm `spring-boot-starter-web`: Spring Boot có thể ưu tiên MVC/Servlet nếu có cả hai stacks.

### 6.3. Main class

**`src/main/java/example/httpmodes/HttpModesApplication.java`:**

```java
package example.httpmodes;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class HttpModesApplication {
    public static void main(String[] args) {
        SpringApplication.run(HttpModesApplication.class, args);
    }
}
```

### 6.4. SecurityWebFilterChain + MapReactiveUserDetailsService

**`src/main/java/example/httpmodes/HttpSecurityConfiguration.java`:**

```java
package example.httpmodes;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
public class HttpSecurityConfiguration {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers(HttpMethod.GET, "/public/ping")
                            .permitAll()
                        .pathMatchers(HttpMethod.GET, "/api/reports")
                            .hasAuthority("SCOPE_reports.read")
                        .anyExchange().denyAll()
                )
                .httpBasic(Customizer.withDefaults())
                .formLogin(form -> form.disable())
                .build();
    }

    @Bean
    MapReactiveUserDetailsService reactiveUsers() {
        UserDetails reader = User.withUsername("reader")
                .password("{noop}reader-pass")
                .authorities("SCOPE_reports.read")
                .build();

        UserDetails viewer = User.withUsername("viewer")
                .password("{noop}viewer-pass")
                .authorities("SCOPE_profile.read")
                .build();

        return new MapReactiveUserDetailsService(reader, viewer);
    }
}
```

Code này dùng API reactive `ServerHttpSecurity`, không dùng Servlet `HttpSecurity`.

- `/api/reports` chỉ cho Authentication có `SCOPE_reports.read`.
- `httpBasic(Customizer.withDefaults())` bật Basic authentication cho demo.
- `formLogin(form -> form.disable())` tắt form login, giúp route API yêu cầu Basic.
- User store dùng `{noop}` chỉ cho test; production cần BCrypt/Argon2 hoặc chiến lược được duyệt.
- Demo chỉ có GET nên CSRF không cản các request minh họa. Với POST/PUT/DELETE và cookie-based auth, phải phân tích CSRF riêng.
- `anyExchange().denyAll()` chặn các route khác.

### 6.5. Service

**`src/main/java/example/httpmodes/ReportService.java`:**

```java
package example.httpmodes;

import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class ReportService {

    public Mono<String> readFor(String username) {
        return Mono.just("report-for-" + username);
    }
}
```

Không có DB/remote service, nên việc khác biệt giữa mock/full/real HTTP không bị che bởi các dependencies khác. Trong app thật, repository và authorization theo bản ghi cần test riêng.

### 6.6. Controller

**`src/main/java/example/httpmodes/ReportController.java`:**

```java
package example.httpmodes;

import java.security.Principal;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class ReportController {

    private final ReportService reportService;

    public ReportController(ReportService reportService) {
        this.reportService = reportService;
    }

    @GetMapping("/public/ping")
    public Mono<String> ping() {
        return Mono.just("pong");
    }

    @GetMapping("/api/reports")
    public Mono<String> reports(Principal principal) {
        return reportService.readFor(principal.getName());
    }
}
```

WebFlux resolve `Principal` từ authenticated security context. Nếu reader đã qua Basic authentication, response dự kiến:

```text
report-for-reader
```

Nếu viewer được authenticated nhưng thiếu `SCOPE_reports.read`, Spring Security trả 403 **trước khi service được gọi**.

---

## 7. Nhóm A — Full ApplicationContext, mock HTTP

**`src/test/java/example/httpmodes/MockApplicationContextTests.java`:**

```java
package example.httpmodes;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
class MockApplicationContextTests {

    @Autowired ApplicationContext context;

    private WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient.bindToApplicationContext(context)
                .apply(springSecurity())
                .configureClient()
                .baseUrl("http://localhost")
                .build();
    }

    @Test
    void publicPingDoesNotRequireCredentials() {
        client.get().uri("/public/ping").exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("pong");
    }

    @Test
    void protectedRouteWithoutCredentialsIs401() {
        client.get().uri("/api/reports").exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void mockUserWithReadAuthorityCanGetReport() {
        client.mutateWith(mockUser("reader").authorities(
                    new SimpleGrantedAuthority("SCOPE_reports.read")))
                .get().uri("/api/reports").exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("report-for-reader");
    }

    @Test
    void mockUserWithoutAuthorityIs403() {
        client.mutateWith(mockUser("viewer").authorities(
                    new SimpleGrantedAuthority("SCOPE_profile.read")))
                .get().uri("/api/reports").exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void realBasicCredentialsAlsoWorkThroughMockWebFilterChain() {
        client.get().uri("/api/reports")
                .headers(h -> h.setBasicAuth("reader", "reader-pass"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("report-for-reader");
    }

    @Test
    void wrongBasicPasswordIsRejectedWithoutARealHttpServer() {
        client.get().uri("/api/reports")
                .headers(h -> h.setBasicAuth("reader", "wrong-password"))
                .exchange()
                .expectStatus().isUnauthorized();
    }
}
```

**Giải thích:**

- Full Spring ApplicationContext thực sự được nạp, gồm controller, service và SecurityWebFilterChain.
- `WebTestClient.bindToApplicationContext` tạo mock request/response trong cùng JVM, không có port.
- `.apply(springSecurity())` cho phép `mockUser` test support.
- Hai test `mockUser(...)` kiểm **authorization** theo authority giả lập; không kiểm password.
- Hai test Basic header đi qua **HTTP Basic WebFilter/password check thật**, dù transport in-process.
- `.baseUrl("http://localhost")` chỉ là base URI cho mock test, **không** làm nó gọi HTTP network.
- Nếu bỏ `.apply(springSecurity())`, các test dựa vào mock authentication có thể không còn hoạt động như dự kiến. Đây là cấu hình test, không phải logic production.

## 8. Nhóm B — @WebFluxTest với @MockitoBean

**`src/test/java/example/httpmodes/WebFluxSliceTests.java`:**

```java
package example.httpmodes;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Import;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.core.publisher.Mono;

import static org.mockito.BDDMockito.given;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@WebFluxTest(ReportController.class)
@Import(HttpSecurityConfiguration.class)
class WebFluxSliceTests {

    @Autowired ApplicationContext context;

    @MockitoBean ReportService reportService;

    private WebTestClient client;

    @BeforeEach
    void setUp() {
        given(reportService.readFor("reader"))
                .willReturn(Mono.just("slice-report-for-reader"));

        client = WebTestClient.bindToApplicationContext(context)
                .apply(springSecurity())
                .configureClient()
                .build();
    }

    @Test
    void authorizedReaderUsesMockedService() {
        client.mutateWith(mockUser("reader").authorities(
                    new SimpleGrantedAuthority("SCOPE_reports.read")))
                .get().uri("/api/reports").exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("slice-report-for-reader");
    }

    @Test
    void viewerWithoutScopeIs403BeforeService() {
        client.mutateWith(mockUser("viewer").authorities(
                    new SimpleGrantedAuthority("SCOPE_profile.read")))
                .get().uri("/api/reports").exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void publicRouteWorksInWebSlice() {
        client.get().uri("/public/ping").exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("pong");
    }
}
```

**Giải thích:**

1. `@WebFluxTest(ReportController.class)` chỉ nạp web slice, không tự scan service thông thường.
2. `@MockitoBean ReportService` đưa collaborator giả vào context và stub trả `slice-report-for-reader`. Kết quả này khác body từ service thật có chủ đích.
3. `@Import(HttpSecurityConfiguration.class)` bổ sung SecurityWebFilterChain/user store thật của project. Không import có thể tạo test giả tạo về authz.
4. `mockUser(...)` kiểm scope rule, không password.
5. Spring Boot 3.5 dùng `@MockitoBean` từ Spring Test 6.2; `@MockBean` kiểu cũ đã deprecated.
6. Toàn bộ request trong slice vẫn đi qua **mock WebFlux handler chain**, không có HTTP socket.

Slice phù hợp khi business service/DB quá nặng và bạn chỉ cần kiểm HTTP/controller behavior. Nó không chứng minh service/repository implementation hoạt động.

## 9. Nhóm C — HTTP thật qua embedded Reactor Netty

**`src/test/java/example/httpmodes/RealHttpServerTests.java`:**

```java
package example.httpmodes;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class RealHttpServerTests {

    @LocalServerPort int port;

    private WebTestClient client;

    @BeforeEach
    void setUp() {
        assertTrue(port > 0, "Embedded server must bind a port");
        client = WebTestClient.bindToServer()
                .baseUrl("http://127.0.0.1:" + port)
                .build();
    }

    @Test
    void realHttpPublicPing() {
        client.get().uri("/public/ping").exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("pong");
    }

    @Test
    void realHttpAnonymousIs401() {
        client.get().uri("/api/reports").exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void realHttpBasicReaderGetsReport() {
        client.get().uri("/api/reports")
                .headers(h -> h.setBasicAuth("reader", "reader-pass"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("report-for-reader");
    }

    @Test
    void realHttpBasicViewerHas403() {
        client.get().uri("/api/reports")
                .headers(h -> h.setBasicAuth("viewer", "viewer-pass"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void realHttpWrongPasswordIs401() {
        client.get().uri("/api/reports")
                .headers(h -> h.setBasicAuth("reader", "wrong-password"))
                .exchange()
                .expectStatus().isUnauthorized();
    }
}
```

### Vì sao đây là HTTP thật?

- `@SpringBootTest(RANDOM_PORT)` tạo embedded server thực khi dự án dùng WebFlux.
- `@LocalServerPort` lấy port do OS cấp, không có hardcoded 8080.
- `bindToServer()` dùng HTTP client gửi request TCP tới `127.0.0.1:port`.
- Basic header đi qua HTTP parser, WebFlux Security filter và MapReactiveUserDetailsService.
- Không dùng `mockUser` để tạo Authentication trong server. Mọi authorization quyết định dựa vào identity đã được kiểm credential thật của lab.
- Server không kết nối IDP hay database production vì sample không có dependency như vậy.

### Vì sao real HTTP không tự đồng nghĩa E2E?

HTTP socket là thật nhưng TLS, reverse proxy, DNS, OAuth2, JWKS, session cookie, R2DBC hay service mesh vẫn **không** có trong demo. Để test những ranh giới đó cần dựng chúng cụ thể ở staging/test container phù hợp.

---

## 10. Chạy tests

Nếu project có Gradle Wrapper:

```bash
./gradlew test
```

Chạy riêng nhóm ApplicationContext:

```bash
./gradlew test --tests example.httpmodes.MockApplicationContextTests
```

Chạy slice:

```bash
./gradlew test --tests example.httpmodes.WebFluxSliceTests
```

Chạy real HTTP:

```bash
./gradlew test --tests example.httpmodes.RealHttpServerTests
```

Windows PowerShell:

```powershell
.\gradlew.bat test --tests example.httpmodes.RealHttpServerTests
```

Nếu chưa có wrapper nhưng đã cài Gradle tương thích:

```bash
gradle test
```

**Kết quả kỳ vọng:** **14 test methods** PASS (6 mock full-context + 3 slice + 5 real HTTP) trên JDK 17+ và dependency/runtime tương thích. Đây **không phải kết quả từ một lần chạy Gradle thực tế**. Sau khi chạy, xem:

```text
build/reports/tests/test/index.html
```

Để kiểm riêng publisher đơn giản mà không có HTTP, có thể dùng `StepVerifier` (dependency `reactor-test` đã thêm trong Gradle):

```java
// FRAGMENT unit test service, không kiểm HTTP transport:
StepVerifier.create(new ReportService().readFor("reader"))
        .expectNext("report-for-reader")
        .verifyComplete();
```

`StepVerifier` hữu ích cho `Mono`/`Flux`, virtual time và reactive signals; nó không thay `WebTestClient` để kiểm Security WebFilter hay real HTTP status.

---

## 11. Cần thêm những loại test nào cho Resource Server JWT/Opaque?

Demo HTTP Basic là để cô lập khác biệt ApplicationContext/real-server, không phải toàn bộ mô hình OAuth2. Khi ứng dụng chuyển sang JWT/opaque, giữ **ba lớp kiểm thử**:

| Câu hỏi | Test nhanh | Kiểm thử tích hợp |
| --- | --- | --- |
| Route nào public/protected? | Mock context + mockJwt / mockOpaqueToken | RANDOM_PORT + Bearer token |
| Scope/role policy đúng? | mockJwt/mockOpaqueToken authorities | Token thật được verify |
| JWT signature/issuer/audience/time? | Unit test validators/decoder | Signed RS256 JWT + JWKS fixture + real HTTP |
| Opaque token `active=false`? | Mock introspector unit test | WebTestClient real HTTP + MockWebServer introspection |
| HTTP Basic wrong password? | Mock web chain + header Basic | Real HTTP + Basic credential |
| JSON/status/validation? | WebFlux slice/full context | Real HTTP smoke/contract |
| External IdP timeout? | Mock error responses | HTTP + network stub/IdP staging |
| TLS/mTLS/proxy forwarded headers? | Config review/unit tests | Staging test có TLS/proxy thực |
| Đọc chéo tenant? | Policy/service tests | HTTP + tenant-aware DB integration |
| Streaming response/SSE? | Flux StepVerifier/WebTestClient | Real HTTP streaming/backpressure test |

### MockWebServer có làm test mất "HTTP thật" không?

Nếu bạn chạy `@SpringBootTest(RANDOM_PORT)` và gửi request tới app qua `bindToServer()`, **incoming HTTP** là thật. Bạn vẫn có thể để app gọi một **mock downstream** qua HTTP, ví dụ MockWebServer/WireMock mô phỏng IdP. Khi báo cáo test, ghi rõ: transport inbound thật, upstream giả lập.

Dùng `@DynamicPropertySource` để inject endpoint port ngẫu nhiên của MockWebServer **trước** khi Spring tạo context. Không đặt địa chỉ cố định `localhost:8080` hoặc để test phụ thuộc dịch vụ Internet.

**Fragment** cho một Resource Server có introspection, không dùng trong project Basic demo:

```java
// Chỉ minh họa; test cần tự định nghĩa/start/close IDP.
@DynamicPropertySource
static void configureIntrospection(DynamicPropertyRegistry registry) {
    registry.add(
            "spring.security.oauth2.resourceserver.opaquetoken.introspection-uri",
            () -> IDP.url("/introspect").toString());
}
```

Test end-to-end với IdP thật hoặc OAuth2 token endpoint thật cần credentials hợp lệ, policy reset data, test tenant riêng, rotation handling và không chạy destructive operations trên production.

## 12. Các lỗi gây false confidence

### 12.1. Dùng @WebFluxTest nhưng quên SecurityWebFilterChain

Custom `SecurityWebFilterChain` có thể không được scan. Một endpoint trả 200 trong slice không có nghĩa production bảo vệ đúng. Import config thật hoặc dùng full context; thêm negative tests 401/403.

### 12.2. Dùng mockUser rồi kết luận Basic password hợp lệ

`mockUser` tạo Authentication đã xác thực giả lập. Dùng Basic header với user store thật để kiểm password, và real HTTP test để kiểm network entrypoint.

### 12.3. Dùng mockJwt rồi kết luận chữ ký/issuer đã được verify

Mock JWT bỏ qua phần mật mã. Signed token + decoder thật + JWKS fixture mới kiểm signature/issuer/audience/time. Negative tests wrong key, wrong issuer, expired giúp phát hiện missing validators.

### 12.4. @SpringBootTest mặc định nhưng nghĩ server đã chạy

`@SpringBootTest` mặc định dùng MOCK. Nếu test gọi `http://localhost:8080`, có thể đang gọi **một tiến trình khác** hoặc bị connection refused. Muốn server thật dùng `RANDOM_PORT` và `@LocalServerPort`.

### 12.5. bindToApplicationContext có baseUrl HTTP

`baseUrl("http://localhost")` chỉ giải quyết relative URIs khi bindToApplicationContext; không chuyển sang network mode. Phải gọi `bindToServer()` mới dùng transport thật.

### 12.6. Hardcode port cho CI

Port 8080 dễ va chạm với ứng dụng khác. Dùng RANDOM_PORT và inject port thực. Không bắt test phụ thuộc thứ tự khởi động một server ngoài mà không có lifecycle management.

### 12.7. Test chỉ kiểm 200

Bổ sung no-credential 401, invalid-credential 401, insufficient-scope 403, forbidden method/path và relevant exception cases. Nếu quên security config, những test âm tính sẽ giúp phát hiện.

### 12.8. @MockitoBean che mất business bug

Một slice test có `@MockitoBean ReportService` chỉ kiểm controller gọi đúng service API; không kiểm service thật. Cần service unit tests, DB/R2DBC integration và row-level permission tests.

### 12.9. @Transactional test rollback giả định quá mức

Real HTTP server xử lý request trong execution context khác test method, nên server-side changes có thể không bị rollback bởi transaction của test. Dùng ephemeral DB và cleanup rõ.

### 12.10. Real localhost HTTP ≠ production TLS

Dù `bindToServer()` test thành công, bạn chưa xác minh TLS, proxy headers, DNS, auth federation hoặc zero-trust boundary nếu không thực sự đưa chúng vào test.

### 12.11. Context cache và tests chạy song song

Spring Boot test context có thể cache giữa classes. Mutable state, static mocks, singleton services và DB fixtures có thể rò dữ liệu. Ưu tiên state isolation/reset mocks và tránh lạm dụng `@DirtiesContext`.

### 12.12. Không chờ Publisher hoàn tất

Trong WebFlux, tránh tự `subscribe()` trong controller rồi trả response trước khi xử lý xong. Trả `Mono`/`Flux` từ handler; WebTestClient sẽ assert response trong lifecycle request được quản lý.

---

## 13. Checklist và bài tập

### Checklist cho một bộ test có ý nghĩa

1. Tên test/mô tả chỉ rõ Spring scope (slice hay full context) và HTTP transport (mock hay socket).
2. ApplicationContext tests đã nạp đúng SecurityWebFilterChain.
3. Nếu dùng mock auth, không mô tả nó là xác minh mật khẩu/JWT/opaque thật.
4. Sử dụng `springSecurity()` khi cần SecurityMockServerConfigurers trên WebTestClient in-memory.
5. Có tests negative 401/403.
6. Không trộn MVC và WebFlux classpath một cách vô ý.
7. Đường đi HTTP thật dùng RANDOM_PORT, không hardcode port.
8. DB/IdP/downstream dependencies đã được mô tả là thật, in-memory hay mock.
9. Test timeout/streaming/network/TLS khi đó là rủi ro cần kiểm, không suy từ kết quả controller test.
10. Chỉ dùng secrets lab giả, không đưa production credentials vào tests.
11. Report/logs phân biệt "expected" với "observed".
12. Khi cần method security, test cả request qua HTTP và reactive service invocation có SecurityContext.
13. Chú ý data cleanup ở server-side transactions.
14. Dùng @MockitoBean có chủ đích và không overmock.
15. Khi có multi-tenant, test wrong tenant/owner để phát hiện dữ liệu chéo tenant.

### Bài tập mở rộng

1. Chạy 14 test và xác định class nào mở HTTP listener.
2. Thử bỏ `springSecurity()` khỏi mock client, quan sát mockUser thay đổi thế nào.
3. Giữ `mockUser("reader")` nhưng đặt quyền khác; vì sao quyền, không phải username, quyết định 403?
4. Gửi sai mật khẩu Basic ở mock context và real HTTP; phân biệt phần pipeline được kiểm.
5. Bỏ `@Import(HttpSecurityConfiguration.class)` khỏi slice, xem context/security policy thay đổi thế nào.
6. Thử bỏ `@MockitoBean` khỏi slice; giải thích vì sao ReportService không được nạp từ component scan.
7. Đổi RANDOM_PORT thành MOCK nhưng vẫn `bindToServer()`; quan sát connection refused.
8. Dùng `@AutoConfigureWebTestClient` và inject client vào full-context MOCK, so với bind thủ công.
9. Thêm JSON DTO và test serialization/validation ở hai modes.
10. Thêm POST endpoint với authn cookie, phân tích CSRF chứ không tắt để test pass.
11. Thay Basic bằng JWT Resource Server; tạo RSA token, JWKS fixture, kiểm wrong iss/aud.
12. Thay bằng opaque token introspection, test active=false và wrong scope qua MockWebServer.
13. Thêm R2DBC tenant-aware access và cleanup riêng cho real HTTP tests.
14. Test SSE/Flux cả in-process và real HTTP, quan sát timeout/streaming.
15. Đặt gateway sau reverse proxy và xác minh trusted forwarding headers trong staging.
16. Thiết kế test pyramid theo độ rủi ro của app; không ép một tỷ lệ cố định.

## Kết luận

**`bindToApplicationContext`** gửi mock request qua WebFlux handler chain trong cùng JVM: chạy nhanh, có thể test security filters/authorization thật nhưng **không** chứng minh TCP server hoặc HTTP transport. **`bindToServer`** gọi một server đang chạy bằng HTTP request thực, kiểm thêm networking/container behavior.

**`@SpringBootTest` mặc định = full context + MOCK**, **`@SpringBootTest(RANDOM_PORT)` = full context + real HTTP server**, còn **`@WebFluxTest` = web slice + mock exchange**. `mockUser()`/`mockJwt()`/`mockOpaqueToken()` giúp kiểm authorization nhưng **không tự kiểm** credential/signature/introspection.

Một bộ test tốt cần cả **in-process tests cho nhiều rule** và **real HTTP integration tests cho các ranh giới quan trọng**, cộng thêm proxy/TLS/IdP/DB integration khi có mục tiêu kiểm chứng tương ứng.

## Tài liệu tham khảo

- [Spring Framework 6.2 — WebTestClient](https://docs.spring.io/spring-framework/reference/6.2/testing/webtestclient.html)
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)
- [Spring Security 6.5 — WebTestClient Security Setup](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/setup.html)
- [Spring Security 6.5 — Testing Authentication](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/authentication.html)
- [Spring Security 6.5 — Testing OAuth2](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/oauth2.html)
- [Spring Security 6.5 — Reactive WebFlux Security](https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html)
- [Spring Test — @MockitoBean](https://docs.spring.io/spring-framework/reference/6.2/testing/annotations/integration-spring/annotation-mockitobean.html)
- [Spring Boot 3.5.16 Release](https://spring.io/blog/2026/06/25/spring-boot-3-5-16-available-now/)
