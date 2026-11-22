# Cấu hình @EnableRSocketSecurity, RSocketSecurity và SocketAcceptorInterceptor

*Module: Spring Security - reactive · Nhóm: RSocket và luồng dài · Java 17+ / Spring Security 6.5 / Spring Boot 3.5.x.*

## 1. Mục tiêu và bối cảnh bảo mật

RSocket cung cấp truyền thông hai chiều qua TCP hoặc WebSocket với các mô hình request-response, fire-and-forget, request-stream và request-channel. Một kết nối có thể sống lâu và tải nhiều request hoặc nhiều payloads; khác với HTTP, khi danh tính được xác thực tại thời điểm **SETUP**, các request tiếp theo trên kết nối có thể sử dụng context này.

Spring Security cho WebFlux HTTP dùng `ServerHttpSecurity`, `SecurityWebFilterChain` và `WebFilter`. **RSocket không tự được bảo vệ bằng các rule HTTP đó**. Để bảo vệ RSocket routes, Spring Security cung cấp:

- **`@EnableRSocketSecurity`**: bật hỗ trợ cấu hình RSocket Security.
- **`RSocketSecurity`**: DSL để khai báo authentication, authorization rules cho SETUP/route/request exchanges.
- **`PayloadSocketAcceptorInterceptor`**: kết quả `RSocketSecurity.build()`, áp dụng chuỗi payload interceptors.
- **`SecuritySocketAcceptorInterceptor`**: bridge để đưa payload security vào RSocket server qua `SocketAcceptorInterceptor`.
- **`RSocketSecurityAutoConfiguration`**: Spring Boot tự gắn bridge vào RSocket server khi có đúng dependencies/beans.
- **`AuthenticationPayloadInterceptor`**: phối hợp converter và `ReactiveAuthenticationManager` xác thực thông tin đăng nhập.
- **`AuthorizationPayloadInterceptor`**: dùng `ReactiveAuthorizationManager`/DSL đánh giá quyền route và setup.
- **`RSocketRequester`**: client API tạo kết nối, gửi route, data và authentication metadata.

**Kết quả học tập:** bạn sẽ biết cài đúng các beans và dependencies, phân biệt SETUP-auth với request-auth, viết policy fail-closed cho route, mã hóa Simple Authentication metadata theo RSocket extension, thiết kế luồng dài không rò quyền/tài nguyên, và chạy một project Java 17+ cùng tests `StepVerifier` thực sự gọi RSocket TCP server.

**Phạm vi:** hướng dẫn lập trình một RSocket TCP server trên localhost. Không giả định có Authorization Server/OIDC thực; phần JWT là ví dụ mở rộng và yêu cầu `ReactiveJwtDecoder` từ issuer tin cậy. Không trộn HTTP status 401/403 vào giao thức RSocket TCP.

## 2. RSocket interaction models và điểm kiểm tra quyền

```text
Client                                       RSocket Server
  |                                               |
  |--- SETUP(auth metadata, connection prefs) --->|
  |<-- connection accepted / ERROR ---------------|
  |                                               |
  |--- REQUEST_RESPONSE(route, data) ------------>|
  |<-- PAYLOAD(result) / ERROR --------------------|
  |                                               |
  |--- REQUEST_STREAM(route) --------------------->|
  |<-- PAYLOAD #1 ---------------------------------|
  |<-- PAYLOAD #2 ---------------------------------|
  |--- REQUEST_N (demand) ------------------------>|
  |--- CANCEL (when caller stops) ---------------->|
  |                                               |
  |--- FIRE_AND_FORGET(route, data) -------------->|
  |                                               |
  |<============= long-lived connection =========>|
```

| Loại frame / interaction | Tính chất | Câu hỏi bảo mật |
| --- | --- | --- |
| `SETUP` | Khởi tạo một kết nối | Principal nào được quyền mở kết nối? |
| Request-response | 1 request, tối đa 1 response | Có được gọi route này không? |
| Fire-and-forget | Gửi dữ liệu, không đợi response nghiệp vụ | Chặn side effect trước khi xử lý ra sao? |
| Request-stream | Một request kích hoạt nhiều PAYLOAD | Người dùng có tiếp tục được quyền nhận dữ liệu trong suốt stream? |
| Request-channel | Client và server trao đổi nhiều phần tử | Per-request authentication và per-element validation cần gì? |
| `METADATA_PUSH` | Metadata mới trên connection đã có | Không được coi metadata chưa xác minh là principal |
| `REQUEST_N`, `CANCEL` | Backpressure, hủy | Có trả tài nguyên và dừng publisher khi không còn subscriber? |

### 2.1. Route RSocket không phải đường dẫn HTTP

Một responder có:

```java
@MessageMapping("profile.me")
public Mono<String> whoAmI() {
    return Mono.just("response");
}
```

được định tuyến qua **RSocket routing metadata**, không phải `GET /profile.me`. Đây là một method minh họa, không phải file biên dịch độc lập.

Cấu hình HTTP:

```java
http.authorizeExchange(ex ->
        ex.pathMatchers("/profile.me").authenticated());
```

**không thay** `rsocket.authorizePayload(...)` cho RSocket TCP route. Một ứng dụng có cả WebFlux REST và RSocket phải cấu hình hai ranh giới bảo mật riêng.

### 2.2. Metadata không phải là authentication đã hoàn thành

RSocket composite metadata chứa các mục có MIME type như route, authentication, tracing. Một `UsernamePasswordMetadata` là credential được cung cấp để server xác minh, **không phải một authenticated principal**. Một chuỗi JSON trong data như `{"user":"admin","role":"ADMIN"}` cũng không mang quyền ADMIN.

Spring Security's RSocket layer có decoder/converter và `ReactiveAuthenticationManager` để xác minh credential, sau đó đưa `Authentication` vào Reactor Context. Handler/authorization chỉ nên tin Authentication đến từ security layer, không gán nó trực tiếp từ data, route variables hoặc metadata chưa xác thực.

## 3. Phân biệt ba thành phần được yêu cầu

### 3.1. `@EnableRSocketSecurity`

```java
@Configuration
@EnableRSocketSecurity
public class SecurityConfig {
    // RSocket Security beans.
}
```

Annotation có package `org.springframework.security.config.annotation.rsocket.EnableRSocketSecurity`. Nó bật cấu hình/security support chứ không tự cấp TLS, JWT issuer trust, quyền route hay network ACL. Nếu bạn chỉ thêm annotation rồi thấy server kết nối được, điều đó chưa chứng minh những route riêng tư đã được bảo vệ.

### 3.2. `RSocketSecurity`

Builder thuộc `org.springframework.security.config.annotation.rsocket.RSocketSecurity`. Bạn dùng:

```java
rsocket
    .authorizePayload(authz -> authz
        .setup().permitAll()
        .route("public.ping").permitAll()
        .route("admin.ping").hasRole("ADMIN")
        .route("private.greet").authenticated()
        .route("ticks.stream").authenticated()
        .anyRequest().denyAll()
        .anyExchange().permitAll())
    .simpleAuthentication(Customizer.withDefaults());

PayloadSocketAcceptorInterceptor interceptor = rsocket.build();
```

Đây là snippet trong một method `@Bean`; project đầy đủ ở mục 7. Ý nghĩa:

1. `setup().permitAll()` cho phép thiết lập connection chưa có principal. **Không** đồng nghĩa mọi route đều public.
2. Route `public.ping` cho anonymous request.
3. Route `admin.ping` cần `ROLE_ADMIN`, lấy từ server-side authorities, không từ JSON gửi lên.
4. Route `private.greet` và `ticks.stream` cần một `Authentication` đã xác minh.
5. `anyRequest().denyAll()` chặn request không khớp route allow-list, kể cả handler mới vô tình được thêm.
6. `anyExchange().permitAll()` là fallback cho các exchange **không phải request có routing metadata** như những phần tiếp của stream; không có ý nghĩa mở public các route đã match.
7. `simpleAuthentication(...)` bật xác thực username/password dùng **RSocket Simple Authentication metadata**.
8. Rules được áp dụng **theo thứ tự**; chỉ rule match đầu tiên có hiệu lực.

**Lỗi nguy hiểm:** đặt `anyRequest().permitAll()` hoặc `anyExchange().permitAll()` trước rule ADMIN có thể che các rule sau. Đặt các route cụ thể trước fallback.

### 3.3. `SocketAcceptorInterceptor` và bridge

Ở RSocket Java plugin layer, `SocketAcceptorInterceptor` can thiệp việc chấp nhận một kết nối RSocket. Spring Security có **`SecuritySocketAcceptorInterceptor`** nối lớp plugin này với security payload interceptors. Chính `RSocketSecurity.build()` trả về **`PayloadSocketAcceptorInterceptor`**, không phải một Spring HTTP `WebFilter`.

```text
RSocketServer
     |
     v
SocketAcceptorInterceptor
     |
     v
SecuritySocketAcceptorInterceptor
     |
     v
PayloadSocketAcceptorInterceptor (từ RSocketSecurity.build)
     |
     +--> AuthenticationPayloadInterceptor
     |        +--> ReactiveAuthenticationManager
     |
     +--> AuthorizationPayloadInterceptor
              +--> authorizePayload rules
     |
     v
RSocketMessageHandler -> @MessageMapping -> Mono/Flux
```

Sơ đồ là trách nhiệm logic; call stack nội bộ có thể thay đổi theo phiên bản. Điều quan trọng là *plugin acceptor* và *payload authentication/authorization* là hai lớp kết nối với nhau.

**Với Spring Boot:** khi `spring-security-rsocket` và RSocket infrastructure được tự cấu hình, Boot sẽ đăng ký `SecuritySocketAcceptorInterceptor` bằng `RSocketSecurityAutoConfiguration`. Không thêm **cùng interceptor** bằng customizer thủ công lần nữa.

**Không có Boot auto-config hoặc tự tạo RSocket server:** có thể gắn thủ công:

```java
@Bean
RSocketServerCustomizer rsocketSecurityHook(
        SecuritySocketAcceptorInterceptor security) {
    return server -> server.interceptors(
            registry -> registry.forSocketAcceptor(security));
}
```

Snippet này dành cho hệ thống **chưa có** auto-registered bridge, không là phần của demo Boot bên dưới. Imports tương ứng là `org.springframework.boot.rsocket.server.RSocketServerCustomizer` và `org.springframework.security.rsocket.core.SecuritySocketAcceptorInterceptor`.

Việc đăng ký hai lần dễ gây audit lặp, authentication trùng, lỗi thứ tự và gia tăng latency. Chỉ một bean `PayloadSocketAcceptorInterceptor` tồn tại cũng chưa đủ: phải thực sự được gắn vào RSocket acceptor path và xác minh hành vi qua integration test.

## 4. Xác thực tại SETUP và theo từng request

### 4.1. Xác thực tại SETUP

Một ứng dụng mobile có connection riêng cho Alice. Client gửi credential trong `SETUP`:

```text
SETUP(username=alice, password=...)
      |
      v
Server verifies Alice
      |
      v
private.greet -> "hello alice"
```

Khi credential được xác minh, context connection có thể hỗ trợ các request tiếp theo. Cách này hợp lý khi **một connection tương ứng một principal/service identity**.

**Cảnh báo:** SETUP authentication không tự revalidate password/JWT token trên mọi PAYLOAD kéo dài. Khi user logout, quyền bị revoke, password đổi hoặc JWT hết hạn, cần xác định khi nào **đóng connection, reauthenticate, giới hạn stream lifetime hoặc hủy stream** theo threat model.

### 4.2. Xác thực theo request

Backend web thường chia sẻ một connection để gọi dịch vụ RSocket thay mặt nhiều người:

```text
Shared RSocket connection
    +-- Request for Alice -> Alice credential metadata
    +-- Request for Bob   -> Bob credential metadata
    +-- Request for Carol -> Carol credential metadata
```

Khi đó không dùng một SETUP token của Alice cho mọi user, tránh cross-user access. Client gắn metadata riêng vào request, và Spring Security xác minh trong `AuthenticationPayloadInterceptor`.

Một biến thể mạnh hơn: dùng credential SETUP cho **service có ROLE_SETUP** để kiểm soát ai được kết nối, còn per-request credential là end-user identity. Phải test semantics khi đồng thời có SETUP và request metadata; không giả định token request được phép ghi đè mọi quyền của SETUP.

### 4.3. Kiểm tra chính SETUP

Nếu chỉ có trusted services mới được phép kết nối, có thể cấu hình:

```java
rsocket.authorizePayload(authz -> authz
        .setup().hasRole("SETUP")
        .route("private.greet").authenticated()
        .anyRequest().denyAll()
        .anyExchange().permitAll());
```

**Đây là policy thay thế**, không ghép vào demo `setup().permitAll()`. Với `hasRole("SETUP")`, client phải gửi thông tin được xác minh ở SETUP; không thể kết nối anonymous rồi dùng per-request auth để tránh kiểm tra setup. ROLE_SETUP phải do server-side manager cấp, không phải client tự khai.

### 4.4. Simple Authentication metadata

Simple Authentication extension dùng MIME type:

```java
MimeType authMime = MimeTypeUtils.parseMimeType(
        WellKnownMimeType.MESSAGE_RSOCKET_AUTHENTICATION.getString());
```

Client thêm `UsernamePasswordMetadata` bằng `SimpleAuthenticationEncoder`. Nó **không** dùng HTTP header `Authorization: Basic` của HTTP Basic và **không mã hóa password trên transport**. Với network thật phải dùng TLS/mTLS, certificate verification và quản lý secrets.

Có thể gửi ở connection:

```java
RSocketRequester.builder()
        .rsocketStrategies(b -> b.encoder(new SimpleAuthenticationEncoder()))
        .setupMetadata(
                new UsernamePasswordMetadata("alice", "alice-pass"),
                authMime)
        .tcp("127.0.0.1", 7000);
```

Hoặc tại từng request của một requester dùng chung:

```java
requester.route("private.greet")
        .metadata(
                new UsernamePasswordMetadata("alice", "alice-pass"),
                authMime)
        .retrieveMono(String.class);
```

Các snippet trên cần imports, requester và server thật; mã hoàn chỉnh xuất hiện ở mục 7/8.

## 5. Phân quyền RSocket: setup, route, request, stream

| RSocket exchange | Rule | Expected |
| --- | --- | --- |
| SETUP anonymous | `.setup().permitAll()` | Connection được chấp nhận |
| `public.ping` anonymous | `.route(...).permitAll()` | Trả pong |
| `private.greet` anonymous | `.authenticated()` | RSocket error |
| `private.greet` authenticated Alice | `.authenticated()` | Trả hello alice |
| `admin.ping` authenticated Alice | `.hasRole("ADMIN")` | RSocket error |
| `admin.ping` authenticated admin | `.hasRole("ADMIN")` | Trả admin-ok |
| `ticks.stream` authenticated | `.authenticated()` | Bắt đầu Flux |
| `internal.debug` (route chưa listed) | `.anyRequest().denyAll()` | RSocket error |
| Những exchanges khác không có request route metadata | `.anyExchange().permitAll()` | Không dùng để mở public request routes |

**Không có HTTP 401/403 mặc định** trên RSocket TCP. Authentication failure và authorization denial được truyền qua Reactor `onError`/RSocket Error frame, có thể là những exception khác nhau. Nếu chạy RSocket-over-WebSocket, HTTP handshake và RSocket errors sau khi kết nối là hai lớp riêng.

### 5.1. `hasRole` và `hasAuthority`

`hasRole("ADMIN")` thông thường đòi `ROLE_ADMIN`; role này phải đến từ `ReactiveAuthenticationManager`, user store hoặc verified JWT-to-authorities converter, không lấy từ raw metadata. Với JWT, scope thường được chuyển thành authorities kiểu `SCOPE_stream.read`; nếu dùng hasAuthority thì phải bảo đảm mapping đó thực sự tồn tại và đã được xác minh.

### 5.2. Không bỏ quên fallback

Nếu có handler mới `@MessageMapping("internal.debug")` nhưng bạn không muốn cho client gọi, `.anyRequest().denyAll()` giúp fail-closed. Không chứng minh fallback bằng cách gọi route không tồn tại: route không có handler vốn cũng báo lỗi. Bài test sẽ tạo một **handler tồn tại** rồi chứng minh nó bị rule denyAll ngăn chặn.

## 6. Bài toán luồng dài

Nếu một request-stream đã bắt đầu với một user có quyền, các PAYLOAD tiếp theo không mặc nhiên chạy lại toàn bộ authentication/authorization DSL cho từng item. Giả sử user bị khóa sau 15 phút nhưng stream còn mở vài giờ, dữ liệu có thể tiếp tục được phát nếu ứng dụng không kiểm tra revoke/expiry riêng.

Đánh giá:

1. Giới hạn stream lifetime/lease theo loại dữ liệu.
2. Tôn trọng `REQUEST_N` và `CANCEL`; không dùng buffer không giới hạn.
3. Đóng hoặc chủ động cancel khi user logout/revoke nếu nghiệp vụ yêu cầu thu hồi tức thời.
4. Cân nhắc per-message tenant/owner checks trong request-channel và domain service.
5. Giới hạn connection count, concurrent streams, frame size, payload size, token size, rate.
6. Đánh giá reconnect/resumption: không mặc nhiên tin credential cũ sau reconnect.
7. Ghi metrics timeout/error/cancel nhưng không log raw auth metadata, JWT, password.
8. Không `block()` hoặc `subscribe()` rời pipeline trong `@MessageMapping`.
9. Dùng `Flux` với cancellation cleanup (doFinally, usingWhen, resource lifecycle).
10. Đảm bảo một user không dùng principal của user khác trên shared connection.

## 7. Project Java 17+ Spring Boot RSocket TCP hoàn chỉnh

Bài demo chạy RSocket TCP trên localhost:7000, có năm handlers:

- `public.ping` trả **pong** không cần credential.
- `private.greet` trả **hello alice** hoặc hello admin dựa trên verified principal.
- `admin.ping` chỉ ADMIN, trả **admin-ok**.
- `ticks.stream` trả năm phần tử **tick-1 đến tick-5**.
- `internal.debug` có handler thật nhưng **bị denyAll** vì không được allow-list.

Người dùng demo local:
- `alice / alice-pass` có ROLE_USER.
- `admin / admin-pass` có ROLE_USER và ROLE_ADMIN.

**Không có Identity Provider thật và không dùng HTTP Basic.** Password demo chỉ dùng localhost. Production phải dùng TLS và user store/IdP phù hợp.

### 7.1. Cấu trúc thư mục

```text
rsocket-security-lab/
├── settings.gradle
├── build.gradle
├── src/main/resources/application.yml
├── src/main/java/example/rsocket/RSocketSecurityApplication.java
├── src/main/java/example/rsocket/RSocketSecurityConfig.java
├── src/main/java/example/rsocket/DemoRSocketController.java
├── src/main/java/example/rsocket/RSocketClientDemo.java
└── src/test/java/example/rsocket/RSocketSecurityIntegrationTest.java
```

### 7.2. settings.gradle

```groovy
rootProject.name = 'rsocket-security-lab'
```

### 7.3. build.gradle

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
    implementation 'org.springframework.boot:spring-boot-starter-rsocket'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.security:spring-security-rsocket'
    implementation 'org.springframework.security:spring-security-messaging'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}

tasks.register('runDemoClient', JavaExec) {
    classpath = sourceSets.main.runtimeClasspath
    mainClass = 'example.rsocket.RSocketClientDemo'
}
```

Dependency `spring-boot-starter-rsocket` cung cấp server/transport/RSocketRequester. `spring-security-rsocket` cung cấp DSL/interceptors/security metadata; `spring-boot-starter-security` hỗ trợ user/password managers. `spring-security-messaging` phục vụ tính năng mở rộng security messaging. Không cần `spring-boot-starter-web` (Servlet MVC) cho server TCP độc lập. Boot BOM chọn các Spring Security/Reactor phiên bản tương thích.

### 7.4. application.yml

```yaml
spring:
  application:
    name: rsocket-security-lab
  rsocket:
    server:
      transport: tcp
      address: 127.0.0.1
      port: 7000
```

Bind loopback tránh công bố Simple Authentication qua TCP không mã hóa. Port này **không phải HTTP**: lệnh curl HTTP vào 7000 không mô phỏng RSocket client.

### 7.5. RSocketSecurityApplication.java

```java
package example.rsocket;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RSocketSecurityApplication {
    public static void main(String[] args) {
        SpringApplication.run(
                RSocketSecurityApplication.class, args);
    }
}
```

### 7.6. RSocketSecurityConfig.java

```java
package example.rsocket;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.rsocket.EnableRSocketSecurity;
import org.springframework.security.config.annotation.rsocket.RSocketSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.rsocket.core.PayloadSocketAcceptorInterceptor;

@Configuration
@EnableRSocketSecurity
public class RSocketSecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService userDetailsService(
            PasswordEncoder encoder) {

        UserDetails alice = User.withUsername("alice")
                .password(encoder.encode("alice-pass"))
                .roles("USER")
                .build();

        UserDetails admin = User.withUsername("admin")
                .password(encoder.encode("admin-pass"))
                .roles("USER", "ADMIN")
                .build();

        return new MapReactiveUserDetailsService(alice, admin);
    }

    @Bean
    PayloadSocketAcceptorInterceptor rsocketInterceptor(
            RSocketSecurity rsocket) {

        return rsocket
                .authorizePayload(authz -> authz
                        .setup().permitAll()
                        .route("public.ping").permitAll()
                        .route("admin.ping").hasRole("ADMIN")
                        .route("private.greet").authenticated()
                        .route("ticks.stream").authenticated()
                        .anyRequest().denyAll()
                        .anyExchange().permitAll())
                .simpleAuthentication(Customizer.withDefaults())
                .build();
    }
}
```

**Giải thích về source:**

1. `@EnableRSocketSecurity` bật RSocket Security, không phải HTTP Security.
2. `RSocketSecurity` bean được Spring inject vào method.
3. `build()` trả **PayloadSocketAcceptorInterceptor**, tương thích với Spring Boot auto-registration bridge.
4. `setup().permitAll()` là policy có chủ đích cho bài demo; các private routes vẫn yêu cầu Authentication.
5. Admin rule dùng `hasRole("ADMIN")`, tương ứng ROLE_ADMIN do UserDetailsService cung cấp.
6. `anyRequest().denyAll()` chặn route chưa có rule, kể cả internal.debug.
7. `anyExchange().permitAll()` áp dụng cho exchanges không bị các rule trước match, không phá admin rule nếu đặt cuối.
8. `simpleAuthentication` xác thực UsernamePasswordMetadata, không phải HTTP Basic Header.
9. Không có bean `RSocketServerCustomizer` manual trong project Boot này; tránh double-registration.
10. Password được BCrypt-hash trong user store in-memory; không dùng demo credentials trong production.
11. Không có quyền nào lấy trực tiếp từ input user chưa xác minh.

### 7.7. DemoRSocketController.java

```java
package example.rsocket;

import java.time.Duration;

import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.stereotype.Controller;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Controller
public class DemoRSocketController {

    @MessageMapping("public.ping")
    public Mono<String> ping() {
        return Mono.just("pong");
    }

    @MessageMapping("private.greet")
    public Mono<String> greet() {
        return ReactiveSecurityContextHolder.getContext()
                .map(SecurityContext::getAuthentication)
                .map(Authentication::getName)
                .map(name -> "hello " + name);
    }

    @MessageMapping("admin.ping")
    public Mono<String> admin() {
        return Mono.just("admin-ok");
    }

    @MessageMapping("ticks.stream")
    public Flux<String> ticks() {
        return Flux.range(1, 5)
                .delayElements(Duration.ofMillis(40))
                .map(i -> "tick-" + i);
    }

    // Handler có thật nhưng bị anyRequest().denyAll().
    @MessageMapping("internal.debug")
    public Mono<String> debug() {
        return Mono.just("must-not-be-reachable");
    }
}
```

`@MessageMapping` là route RSocket, không phải `@GetMapping` của HTTP. Handler `greet` đọc **ReactiveSecurityContextHolder** đã được security pipeline cung cấp; không parse metadata và không tự gắn Authentication. Trong demo, Flux finite 5 items để người học dễ kiểm tra; luồng thật có thể kéo dài nhiều giờ và cần expiry/cancel/revoke policy.

### 7.8. RSocketClientDemo.java

```java
package example.rsocket;

import java.time.Duration;
import java.util.List;

import io.rsocket.metadata.WellKnownMimeType;
import org.springframework.messaging.rsocket.RSocketRequester;
import org.springframework.security.rsocket.metadata.SimpleAuthenticationEncoder;
import org.springframework.security.rsocket.metadata.UsernamePasswordMetadata;
import org.springframework.util.MimeType;
import org.springframework.util.MimeTypeUtils;

public final class RSocketClientDemo {

    private static final MimeType AUTH_MIME =
            MimeTypeUtils.parseMimeType(
                    WellKnownMimeType
                            .MESSAGE_RSOCKET_AUTHENTICATION.getString());

    public static void main(String[] args) {
        RSocketRequester requester = RSocketRequester.builder()
                .rsocketStrategies(b ->
                        b.encoder(new SimpleAuthenticationEncoder()))
                .setupMetadata(
                        new UsernamePasswordMetadata(
                                "alice", "alice-pass"),
                        AUTH_MIME)
                .tcp("127.0.0.1", 7000);

        try {
            String pong = requester.route("public.ping")
                    .retrieveMono(String.class)
                    .block(Duration.ofSeconds(5));

            String greeting = requester.route("private.greet")
                    .retrieveMono(String.class)
                    .block(Duration.ofSeconds(5));

            List<String> ticks = requester.route("ticks.stream")
                    .retrieveFlux(String.class)
                    .collectList()
                    .block(Duration.ofSeconds(5));

            System.out.println(pong);
            System.out.println(greeting);
            System.out.println(ticks);
        }
        finally {
            requester.dispose();
        }
    }
}
```

`SimpleAuthenticationEncoder` và `UsernamePasswordMetadata` mã hóa metadata theo extension MIME RSocket. Password được gửi ở SETUP, không qua HTTP Basic Authorization header.

**Lưu ý Reactor:** CLI `main()` chạy đồng bộ, dùng `.block(Duration)` để in kết quả ở boundary này có thể chấp nhận. **Không** copy `.block()` vào RSocket handler hay Netty event loop.

### 7.9. Chạy sample

Ở terminal 1:

```bash
gradle bootRun
```

Ở terminal 2:

```bash
gradle runDemoClient
```

Kết quả **dự kiến**:

```text
pong
hello alice
[tick-1, tick-2, tick-3, tick-4, tick-5]
```

Khi server chưa chạy/sai port, bạn sẽ nhận transport error. Khi password sai hoặc thiếu quyền, bạn sẽ nhận RSocket error. Đây là kết quả dự kiến từ code, **không phải tuyên bố đã chạy Gradle trong phiên soạn bài**.

## 8. Integration tests thật bằng RSocketRequester và StepVerifier

Thay vì mock toàn bộ security layer, bộ test tạo RSocketRequester kết nối đến **RSocket server thực do Spring Boot test mở**, dùng user/password fixture, quyền route và payloads. Với `spring.rsocket.server.port=0`, server nhận port ngẫu nhiên và `@LocalRSocketServerPort` inject port thực vào test.

Tất cả tests tạo Builder/requester mới theo identity; `RSocketRequester.Builder` có state, không nên tái sử dụng một builder mutable để đổi SETUP credentials giữa Alice và Bob.

### 8.1. RSocketSecurityIntegrationTest.java

```java
package example.rsocket;

import java.time.Duration;

import io.rsocket.metadata.WellKnownMimeType;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.rsocket.server.LocalRSocketServerPort;
import org.springframework.messaging.rsocket.RSocketRequester;
import org.springframework.security.rsocket.metadata.SimpleAuthenticationEncoder;
import org.springframework.security.rsocket.metadata.UsernamePasswordMetadata;
import org.springframework.util.MimeType;
import org.springframework.util.MimeTypeUtils;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

@SpringBootTest(properties = "spring.rsocket.server.port=0")
class RSocketSecurityIntegrationTest {

    private static final MimeType AUTH_MIME =
            MimeTypeUtils.parseMimeType(
                    WellKnownMimeType
                            .MESSAGE_RSOCKET_AUTHENTICATION.getString());

    @LocalRSocketServerPort
    int port;

    private RSocketRequester client(String username, String password) {
        RSocketRequester.Builder builder =
                RSocketRequester.builder()
                        .rsocketStrategies(s ->
                                s.encoder(new SimpleAuthenticationEncoder()));

        if (username != null) {
            builder.setupMetadata(
                    new UsernamePasswordMetadata(username, password),
                    AUTH_MIME);
        }

        return builder.tcp("127.0.0.1", port);
    }

    private Mono<String> request(
            String username, String password, String route) {
        RSocketRequester requester = client(username, password);
        return requester.route(route).retrieveMono(String.class)
                .doFinally(signal -> requester.dispose());
    }

    private Flux<String> stream(String username, String password) {
        RSocketRequester requester = client(username, password);
        return requester.route("ticks.stream")
                .retrieveFlux(String.class)
                .doFinally(signal -> requester.dispose());
    }

    @Test
    void anonymousSetupCanCallPublicPing() {
        StepVerifier.create(
                request(null, null, "public.ping"))
                .expectNext("pong")
                .expectComplete()
                .verify(Duration.ofSeconds(10));
    }

    @Test
    void privateGreetRejectsAnonymous() {
        StepVerifier.create(
                request(null, null, "private.greet"))
                .expectError()
                .verify(Duration.ofSeconds(10));
    }

    @Test
    void aliceSetupCredentialsAreVerified() {
        StepVerifier.create(
                request("alice", "alice-pass", "private.greet"))
                .expectNext("hello alice")
                .expectComplete()
                .verify(Duration.ofSeconds(10));
    }

    @Test
    void adminRoleCanCallAdmin() {
        StepVerifier.create(
                request("admin", "admin-pass", "admin.ping"))
                .expectNext("admin-ok")
                .expectComplete()
                .verify(Duration.ofSeconds(10));
    }

    @Test
    void aliceCannotCallAdmin() {
        StepVerifier.create(
                request("alice", "alice-pass", "admin.ping"))
                .expectError()
                .verify(Duration.ofSeconds(10));
    }

    @Test
    void wrongSetupPasswordFails() {
        StepVerifier.create(
                request("alice", "wrong", "private.greet"))
                .expectError()
                .verify(Duration.ofSeconds(10));
    }

    @Test
    void perRequestCredentialsWorkAfterAnonymousSetup() {
        RSocketRequester requester = client(null, null);
        try {
            Mono<String> response =
                    requester.route("private.greet")
                            .metadata(
                                    new UsernamePasswordMetadata(
                                            "alice", "alice-pass"),
                                    AUTH_MIME)
                            .retrieveMono(String.class);

            StepVerifier.create(response)
                    .expectNext("hello alice")
                    .expectComplete()
                    .verify(Duration.ofSeconds(10));
        }
        finally {
            requester.dispose();
        }
    }

    @Test
    void wrongPerRequestPasswordFails() {
        RSocketRequester requester = client(null, null);
        try {
            Mono<String> response =
                    requester.route("private.greet")
                            .metadata(
                                    new UsernamePasswordMetadata(
                                            "alice", "wrong"),
                                    AUTH_MIME)
                            .retrieveMono(String.class);

            StepVerifier.create(response)
                    .expectError()
                    .verify(Duration.ofSeconds(10));
        }
        finally {
            requester.dispose();
        }
    }

    @Test
    void anonymousCannotCallAdmin() {
        StepVerifier.create(
                request(null, null, "admin.ping"))
                .expectError()
                .verify(Duration.ofSeconds(10));
    }

    @Test
    void authenticatedUserCanOpenStream() {
        StepVerifier.create(
                stream("alice", "alice-pass"))
                .expectNext(
                        "tick-1", "tick-2", "tick-3",
                        "tick-4", "tick-5")
                .expectComplete()
                .verify(Duration.ofSeconds(10));
    }

    @Test
    void anonymousCannotOpenStream() {
        StepVerifier.create(
                stream(null, null))
                .expectError()
                .verify(Duration.ofSeconds(10));
    }

    @Test
    void takeTwoCancelsTheStream() {
        StepVerifier.create(
                stream("alice", "alice-pass").take(2))
                .expectNext("tick-1", "tick-2")
                .expectComplete()
                .verify(Duration.ofSeconds(10));
    }

    @Test
    void unknownButExistingHandlerIsDenied() {
        StepVerifier.create(
                request("admin", "admin-pass", "internal.debug"))
                .expectError()
                .verify(Duration.ofSeconds(10));
    }

    @Test
    void separateConnectionsDoNotSharePrincipals() {
        StepVerifier.create(
                request("alice", "alice-pass", "private.greet"))
                .expectNext("hello alice")
                .expectComplete()
                .verify(Duration.ofSeconds(10));

        StepVerifier.create(
                request("admin", "admin-pass", "private.greet"))
                .expectNext("hello admin")
                .expectComplete()
                .verify(Duration.ofSeconds(10));
    }
}
```

### 8.2. Chạy tests

```bash
gradle test
```

**Kỳ vọng:** 14 tests PASS khi JDK, Gradle và dependencies tương thích. Đây là kỳ vọng thiết kế, **chưa phải kết quả chạy thực tế trong phiên viết bài**.

| Test | Kết quả mong đợi | Kiểm chứng |
| --- | --- | --- |
| Anonymous setup gọi public | pong | SETUP permitAll + public rule |
| Anonymous vào private | Error | Authenticated rule |
| Alice setup đúng password | hello alice | Simple Auth thực sự kiểm tra credentials |
| Admin setup đúng | admin-ok | ROLE_ADMIN từ server |
| Alice vào admin | Error | Authorization chặn user không đủ role |
| Wrong password SETUP | Error | Không chỉ đọc username |
| Request metadata của Alice | hello alice | Per-request authentication |
| Request metadata password sai | Error | Bad credentials không cấp quyền |
| Anonymous vào admin | Error | Setup permitAll không bypass route |
| Alice mở stream | tick-1..tick-5 | Stream request có authorization |
| Anonymous mở stream | Error | Luồng riêng tư không công khai |
| take(2) | Hai phần tử rồi complete | Subscriber cancellation |
| internal.debug | Error | denyAll chặn handler có thật |
| Two connections | Alice/Admin đúng | Identity isolation |

### 8.3. Vì sao không dùng HTTP 401/403 cho assert?

RSocket TCP trả dữ liệu theo protocol, khi authn/authz thất bại gửi **RSocket Error frame** và Reactor `onError`. HTTP status chỉ liên quan tới HTTP handshake (khi dùng RSocket-over-WebSocket), không đại diện trực tiếp lỗi request RSocket bên trong connection.

`expectError()` cho biết request không thành công; để phân biệt security errors với network timeout trong production, hãy assert chi tiết **RSocket error type/code** theo dependency version, cùng server-side logs an toàn. Không dựa duy nhất trên thông báo exception dạng chuỗi có thể thay đổi.

### 8.4. Vì sao không tự block trong handler?

Đúng trong @MessageMapping:

```java
return ReactiveSecurityContextHolder.getContext()
        .map(ctx -> ctx.getAuthentication().getName())
        .map(name -> "hello " + name);
```

Sai ở Netty event loop:

```java
String name = ReactiveSecurityContextHolder.getContext()
        .block()
        .getAuthentication().getName();
```

Đoạn thứ hai là antipattern chỉ để giải thích; không dùng trong source project. Reactive Context có thể di chuyển giữa threads, nên cũng không dùng SecurityContextHolder thread-local như cách mặc định ở Servlet. Trả Mono/Flux để framework quản lý subscription, errors, cancellation.

## 9. Thay Simple Authentication bằng JWT Bearer

Nếu tổ chức dùng OAuth2/OIDC, Spring Security RSocket hỗ trợ `.jwt(Customizer.withDefaults())`, dùng `ReactiveJwtDecoder` đáng tin cậy.

Phương án cấu hình thay thế:

```java
@Bean
PayloadSocketAcceptorInterceptor rsocketJwtSecurity(
        RSocketSecurity rsocket) {
    return rsocket
            .authorizePayload(authz -> authz
                    .setup().permitAll()
                    .route("public.ping").permitAll()
                    .route("private.greet").authenticated()
                    .anyRequest().denyAll()
                    .anyExchange().permitAll())
            .jwt(Customizer.withDefaults())
            .build();
}
```

Đây là **phương án thay** bean dùng Simple Authentication, không bổ sung vô thức hai beans và hai interceptor cùng nhiệm vụ vào ứng dụng. Cần có **ReactiveJwtDecoder bean** xác minh issuer, JWS signature, expiry, not-before và **audience** của dịch vụ. Khi cần scopes, map sang verified authorities như SCOPE_xxx theo policy và kiểm tra tenant/owner trong business layer.

Client dùng `BearerTokenMetadata` ở SETUP hoặc trên từng request:

```java
// Chỉ snippet: bearerValue phải do IdP đáng tin phát hành.
BearerTokenMetadata bearer = new BearerTokenMetadata(bearerValue);

RSocketRequester requester = RSocketRequester.builder()
        .setupMetadata(bearer, AUTH_MIME)
        .tcp("127.0.0.1", 7000);
```

Phần này cần imports/decoder/real token và TLS phù hợp, **không phải file Java chạy độc lập**. Không tự Base64URL decode JWT và tin sub/role trước khi verify. Đừng dùng ID token OIDC làm access token chỉ vì token có signature hợp lệ.

**Stream expiry:** JWT có thể hết hạn/revoke trong khi một request-stream còn đang phát dữ liệu; việc kiểm tra khi mở stream không tự đồng nghĩa tái xác thực ở mỗi item. Nếu rủi ro yêu cầu thu hồi quyền ngay, bạn phải chủ động cancel/revalidate/giới hạn stream lifetime.

## 10. Tùy biến SocketAcceptorInterceptor/PayloadInterceptor

Khi Boot auto-config đang hoạt động, không tự gắn lại **SecuritySocketAcceptorInterceptor**. Nếu ứng dụng dùng RSocket server self-hosted hoặc có interceptor giao thức khác, cần lập kế hoạch thứ tự và trách nhiệm rõ ràng.

`RSocketSecurity.addPayloadInterceptor(custom)` hỗ trợ thêm payload interceptor khi DSL tiêu chuẩn không đáp ứng. Theo Javadoc, custom PayloadInterceptor cần Ordered/@Order phù hợp để tránh tương tác sai thứ tự với AuthenticationPayloadInterceptor và AuthorizationPayloadInterceptor.

Không dùng một custom interceptor để giả lập authenticated principal bằng cách đọc metadata rồi gán authorities. Nếu phải xác thực API key/HMAC scheme mới, hãy triển khai credential converter và ReactiveAuthenticationManager thực sự kiểm chứng, giới hạn route và thêm anti-replay, rate limiting, key rotation.

**Cẩn trọng với double-registration:**

- Duplicate authentication/authorization có thể chạy hai lần.
- Metric/audit event có thể lặp.
- SecurityContext và error handling khó xác định.
- Kết nối bị từ chối dù policy có vẻ permit.
- Chi phí per-payload tăng ở stream dài.
- Test chỉ kiểm tra có bean không phát hiện việc bridge bị gắn trùng: phải test behavior thực.

## 11. Lỗi thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Bật `@EnableRSocketSecurity` nhưng không cấu hình policy routes | Sai bảo vệ | `RSocketSecurity.authorizePayload` |
| Thiếu `spring-security-rsocket` | Thiếu API/auto-configuration | Thêm dependency |
| Tưởng `build()` trả trực tiếp RSocket HTTP WebFilter | Nhầm tầng | PayloadSocketAcceptorInterceptor |
| Manual register khi Boot auto-register | Double security layer | Một lần gắn bridge |
| Dùng `ServerHttpSecurity` cho RSocket TCP | Routes không được bảo vệ | RSocketSecurity, không HTTP matcher |
| SETUP permitAll rồi bỏ rule riêng | Mở route trái ý | Route authorization độc lập |
| Đặt anyRequest permitAll trước admin | Che admin rule | Specific trước fallback |
| Không có denyAll cuối | Handler mới có nguy cơ mở | `anyRequest().denyAll()` |
| Dùng HTTP Basic Header trong TCP | Auth không chạy | Simple RSocket metadata |
| Gửi username/password qua TCP công khai | Rò credential | TLS/mTLS |
| Reuse SETUP identity Alice cho Bob | Cross-user access | Per-request auth/connection isolation |
| Dùng raw metadata làm authenticated user | Authentication bypass | Verified Authentication |
| Bật JWT nhưng không có decoder | Thiếu xác minh | ReactiveJwtDecoder với issuer/aud |
| Dùng JWT ID token thay access token | Token confusion | Kiểm tra token profile |
| Đợi HTTP 403 trên RSocket TCP | Test sai | RSocket Error/onError |
| Reuse mutable Builder đổi user | Lẫn credential metadata | Builder riêng |
| Không dispose requester | Connection leak | Lifecycle cleanup |
| `.block()` trong handler | Block event loop | Nonblocking Mono/Flux |
| `.subscribe()` rời request | Detached/ignore errors | Return publisher |
| Stream quá dài không timeout | Stale rights/resource leak | TTL/revalidation/cancel |
| Buffer vô hạn hoặc bỏ REQUEST_N | Memory/DoS | Backpressure, quotas |
| Không kiểm tra quyền tenant/record | IDOR | Domain-level authorization |
| Log raw SETUP metadata | Password/token leak | Redact, giới hạn log |

## 12. Checklist triển khai production

1. Dùng TLS/mTLS khi RSocket TCP vượt khỏi localhost; WSS nếu transport qua browser.
2. Có `@EnableRSocketSecurity` và một bean `PayloadSocketAcceptorInterceptor`.
3. Xác minh bridge `SecuritySocketAcceptorInterceptor` được gắn **một lần** vào RSocket server.
4. Rules SETUP rõ ràng, không coi permitAll SETUP cho phép mọi requests.
5. Mọi private/admin route có allow rules trước fallback denyAll.
6. Credential được ReactiveAuthenticationManager hoặc ReactiveJwtDecoder xác minh.
7. Không đặt role do client tự khai trong data/route/metadata thành authority.
8. Với kết nối shared, gửi per-request credential và tách principal identity.
9. JWT phải được kiểm tra issuer, audience, expiry, signature, token use và scopes.
10. Giới hạn max connections, frame/payload sizes, concurrent streams và request rates.
11. Theo dõi stream cancellation, backpressure, timeout và cleanup sau disconnect.
12. Có chính sách token expiry/revoke trong luồng dài, không giả định SETUP auth là vĩnh viễn.
13. Ghi audit theo principal đã xác minh, tránh logs raw token/password.
14. Test SETUP public, private denied, admin denied/allowed, wrong credentials.
15. Test per-request metadata, stream mở và stream cancel, unknown existing route.
16. Phân biệt RSocket authentication failure, authorization denial và transport failure.
17. Test nhiều users và multi-tenants; không để dùng nhầm SETUP credential.
18. Không block Netty event loop, không subscribe thủ công trong @MessageMapping.
19. Kiểm tra reconnect/resumption và TLS certificate validation tại edge.
20. Sau khi nâng Spring Boot/Security, kiểm tra lại RSocket auto-config và Javadoc.

## 13. Bài tập tự đánh giá

1. `@EnableRSocketSecurity` tự tạo TLS không? — Không.
2. `RSocketSecurity.build()` trả về gì? — PayloadSocketAcceptorInterceptor.
3. SocketAcceptorInterceptor và PayloadSocketAcceptorInterceptor khác nhau thế nào? — Plugin acceptor vs chuỗi payload security.
4. Boot có tự gắn bridge khi đủ dependencies không? — Có.
5. Có nên thêm manual customizer lần hai không? — Không.
6. SETUP permitAll có nghĩa public mọi route? — Không.
7. Tại sao route rules được khai theo thứ tự? — Rule match đầu tiên được dùng.
8. `anyRequest().denyAll()` nhằm làm gì? — Chặn unknown requests fail-closed.
9. `anyExchange().permitAll()` có mở public admin không? — Không nếu đặt đúng cuối sau rule match.
10. Simple Authentication dùng MIME type nào? — MESSAGE_RSOCKET_AUTHENTICATION.
11. Vì sao Simple không dùng HTTP Basic header? — RSocket dùng metadata có MIME riêng, không có HTTP request headers theo TCP.
12. Vì sao cần TLS với Simple metadata? — Password không được giao thức Simple tự mã hóa.
13. Setup credentials phù hợp trong trường hợp nào? — Single-principal connection.
14. Per-request auth phù hợp trường hợp nào? — Shared connection nhiều end-users.
15. ROLE_ADMIN trong ví dụ đến từ đâu? — UserDetailsService/verified Authentication.
16. Có thể lấy raw role từ data làm quyền? — Không.
17. RSocket TCP auth failure trả HTTP 401? — Không, Error frame/onError.
18. Vì sao test dùng @LocalRSocketServerPort? — Inject random RSocket TCP port thật.
19. Vì sao không reuse mutable RSocketRequester.Builder giữa users? — SETUP credentials có thể bị lẫn.
20. Vì sao test handler internal.debug quan trọng? — Handler có thật nhưng phải bị fallback denyAll chặn.
21. Request-stream có mặc định tái xác thực mỗi PAYLOAD? — Không.
22. Khi user bị revoke giữa stream phải làm gì? — Giới hạn/revalidate/cancel theo policy.
23. Vì sao REQUEST_N và CANCEL quan trọng? — Backpressure và cleanup.
24. Khi dùng JWT cần loại bean nào? — ReactiveJwtDecoder trusted.
25. Test positive public.ping đã chứng minh admin an toàn chưa? — Chưa, phải có negative test admin.

## 14. Tài liệu tham khảo

- Spring Security — RSocket Security: https://docs.spring.io/spring-security/reference/reactive/integrations/rsocket.html
- Spring Security 6.5 — RSocketSecurity Javadoc: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/annotation/rsocket/RSocketSecurity.html
- Spring Security 6.5 — EnableRSocketSecurity: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/annotation/rsocket/EnableRSocketSecurity.html
- Spring Security — PayloadSocketAcceptorInterceptor: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/rsocket/core/PayloadSocketAcceptorInterceptor.html
- Spring Security — UsernamePasswordMetadata: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/rsocket/metadata/UsernamePasswordMetadata.html
- Spring Boot 3.5 — RSocket: https://docs.spring.io/spring-boot/3.5/reference/messaging/rsocket.html
- Spring Boot 3.5 — Application Properties: https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html
- Spring Framework — RSocket requester/annotated responders: https://docs.spring.io/spring-framework/reference/rsocket.html
- Project Reactor — Reference: https://projectreactor.io/docs/core/release/reference/
- RSocket Protocol: https://rsocket.io/about/protocol/

**Kết luận:** Với Spring Security Reactive RSocket, cấu hình đúng là `@EnableRSocketSecurity` và `RSocketSecurity` (build một `PayloadSocketAcceptorInterceptor`), được Spring Boot nối vào RSocket server thông qua `SecuritySocketAcceptorInterceptor`/`SocketAcceptorInterceptor`. Định nghĩa SETUP và route permission độc lập, rule order và denyAll fallback, xác minh Simple hoặc Bearer metadata, rồi áp dụng policies thích hợp cho long-lived streams. Test qua RSocketRequester/StepVerifier, không qua HTTP curl/status; production phải có TLS, reconnect/revalidation, cancellation và resource limits.