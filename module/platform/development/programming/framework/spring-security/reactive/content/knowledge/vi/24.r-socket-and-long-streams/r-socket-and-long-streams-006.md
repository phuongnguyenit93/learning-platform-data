# Kiểm thử RSocket với thiếu thông tin xác thực và thiếu quyền

## 1. Bối cảnh: bảo vệ RSocket khác bảo vệ HTTP ở điểm nào?

**RSocket** là giao thức nhắn tin bất đồng bộ, hai chiều, chạy trên những transport như TCP hoặc WebSocket. Nó hỗ trợ bốn mô hình tương tác chính: **request-response**, **fire-and-forget**, **request-stream** và **request-channel**. Một connection có thể tồn tại lâu, mang nhiều request và nhiều luồng dữ liệu. Vì vậy, bảo mật không chỉ là “trước khi vào controller có token hay không”, mà còn liên quan tới **SETUP frame**, **metadata theo request**, quyền của từng **route**, và việc xử lý **stream đã bắt đầu**.

Trong Spring Security Reactive, các thành phần quan trọng gồm:

- `@EnableRSocketSecurity` bật RSocket Security trong application context.
- `RSocketSecurity` cung cấp DSL `authorizePayload(...)`, `simpleAuthentication(...)` và `jwt(...)`.
- `PayloadSocketAcceptorInterceptor` tích hợp các authentication/authorization interceptors vào RSocket socket acceptor.
- `AuthenticationPayloadInterceptor` phối hợp với `ReactiveAuthenticationManager` để xác minh credentials.
- `AuthorizationPayloadInterceptor` kiểm tra principal/authorities theo `PayloadExchange` và rule của route.
- `RSocketRequester` ở client gửi metadata để authenticate khi kết nối (`SETUP`) hoặc cho từng request.
- `StepVerifier` và **RSocket client/server thật trong test** giúp xác nhận các tín hiệu success/error/cancel.

Đề bài của chúng ta là **kiểm thử khi thiếu thông tin xác thực và khi thiếu quyền**. Hai lỗi này phải được tách rõ:

1. **Chưa được xác thực**: client không gửi credentials/token cho một route protected hoặc gửi credentials sai. Không thể xây dựng trusted `Authentication`.
2. **Đã xác thực, nhưng không được phép**: user/token hợp lệ và đã có `Authentication`, song thiếu `ROLE_ADMIN`, authority hoặc scope mà route yêu cầu.

> **Khác biệt cốt lõi với HTTP:** RSocket trên TCP không có HTTP status **401/403** cho từng message. Security failure có thể dẫn đến connection bị từ chối trong `SETUP`, hoặc reactive Publisher của một request kết thúc bằng **`onError`** tương ứng RSocket error frame. Đừng viết integration test RSocket bằng `WebTestClient.expectStatus().isUnauthorized()`: đó là kiểm thử HTTP, không phải RSocket metadata/authentication.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **SETUP authentication** và **per-request authentication**, chọn đúng mô hình test.
2. Xác minh route public không cần credentials; route protected từ chối request anonymous.
3. Xác minh credentials sai bị từ chối, không bị coi như user có quyền thấp.
4. Xác minh user `ROLE_READER` được đọc route hợp lệ nhưng không được gọi route `ROLE_ADMIN`.
5. Kiểm tra user `ROLE_ADMIN` thực sự gọi được route để chứng minh test denied không phải do routing lỗi.
6. Viết test RSocket **TCP thật trên random port** bằng `@SpringBootTest`, `@LocalRSocketServerPort`, `RSocketRequester` và `StepVerifier`.
7. Dùng `SimpleAuthenticationEncoder` / `UsernamePasswordMetadata` đúng MIME type.
8. Kiểm thử request-stream, giới hạn số phần tử và cancellation để tránh test treo.
9. Hiểu giới hạn của authentication tại SETUP khi connection/stream sống lâu: token hết hạn, logout, thay đổi quyền và revocation **không tự được kiểm tra lại trên mỗi sự kiện**.
10. Tránh rò credentials, kiểm tra TLS và phân biệt test unit/mock với test end-to-end.

## 2. Bốn loại RSocket interaction và tác động tới authorization

| Mô hình | RSocket frame khởi tạo | Kiểu reactive thường gặp | Điều cần test |
| --- | --- | --- | --- |
| Request-response | `REQUEST_RESPONSE` | `Mono<T>` | Anonymous/role thấp có bị chặn trước khi handler trả dữ liệu không? |
| Fire-and-forget | `REQUEST_FNF` | `Mono<Void>` | Request không đủ quyền có bị chặn trước side effect không? Client có thể không nhìn thấy application response |
| Request-stream | `REQUEST_STREAM` | `Flux<T>` | Có chặn trước phần tử đầu tiên? Sau subscribe, cancellation/backpressure đúng không? |
| Request-channel | `REQUEST_CHANNEL` | `Flux<In>` → `Flux<Out>` | Quyền được kiểm tra cho request ban đầu và các message/payload tiếp theo theo policy nào? |

Ở HTTP, một request thường có response status và body. Ở RSocket, một connection duy trì nhiều tương tác độc lập, mỗi tương tác có stream ID hoặc trạng thái giao thức. **Từ chối một request không nhất thiết đóng cả connection**, còn từ chối `SETUP` có thể ngăn connection được thành lập.

Với `request-stream`, nếu authentication/authorization chỉ được kiểm tra ở lúc bắt đầu stream, một stream đã chạy **không tự động hỏi backend quyền cho từng phần tử**. Khi security policy yêu cầu thu hồi quyền tức thời, phải thiết kế cơ chế kiểm tra lại/đóng stream/disconnect và kiểm thử riêng.

## 3. Authentication và authorization trong RSocket

### Authentication

Authentication biến **credentials** từ RSocket metadata thành một `Authentication` được tin cậy:

```text
RSocket SETUP / REQUEST frame
    → metadata chứa credentials/token
    → AuthenticationPayloadInterceptor
    → ReactiveAuthenticationManager
    → Authentication hoặc onError
```

Một kết nối có thể mang `UsernamePasswordMetadata` khi `SETUP` (mô hình một user/connection) hoặc mỗi request (mô hình nhiều users dùng chung connection). Spring Security hỗ trợ cả hai. Với JWT, metadata Bearer có thể gửi ở SETUP hoặc request, nếu `RSocketSecurity.jwt(...)` và `ReactiveJwtDecoder` được cấu hình.

**Thiếu credentials** khác **credentials sai** về chẩn đoán, nhưng cả hai không được dẫn đến một principal đã xác thực.

### Authorization

Authorization quyết định quyền trên một **payload exchange**:

```java
rsocket.authorizePayload(authorize -> authorize
    .setup().permitAll()
    .route("public.ping").permitAll()
    .route("profile.current").authenticated()
    .route("admin.metrics").hasRole("ADMIN")
    .anyRequest().denyAll()
    .anyExchange().permitAll()
);
```

Đây là một cấu hình **minh họa** (được triển khai hoàn chỉnh ở phần dưới). `hasRole("ADMIN")` tương ứng quyền `ROLE_ADMIN` theo Spring Security; `authenticated()` chỉ đòi principal hợp lệ, không mặc nhiên có quyền admin.

**Thứ tự rules quan trọng**: Spring Security xét theo thứ tự, rule đầu tiên match được chọn. Nếu đặt `.anyRequest().authenticated()` trước `.route("admin.metrics").hasRole("ADMIN")`, route admin có thể chỉ cần login mà không cần role! Đó là một lỗ hổng do cấu hình, không phải test framework.

### `anyRequest()` khác `anyExchange()`

Theo tài liệu Spring Security RSocket:

- `anyRequest()` bao phủ request có route/metadata để kiểm tra authorization.
- `anyExchange()` bao phủ những exchange chưa được match, có thể gồm **các payload tiếp nối không có metadata** trong một tương tác/stream.

Một mẫu thường dùng là **kiểm tra request đầu theo route** rồi `.anyExchange().permitAll()` để không vô tình chặn các khung dữ liệu tiếp nối không có route metadata. Điều này **không có nghĩa stream data an toàn tuyệt đối**: nghiệp vụ vẫn phải tự kiểm tra quyền với từng đối tượng/message khi cần.

Nếu ứng dụng có bảo mật rất chặt cho request-channel, kiểm thử đúng frame sequence và interaction types. Đừng suy ra rule `.route(...)` chắc chắn được áp cho từng phần tử của một stream.

## 4. SETUP authentication so với request-time authentication

| Đặc tính | Authentication tại `SETUP` | Authentication theo request |
| --- | --- | --- |
| Credentials được gửi lúc nào? | Khi tạo connection | Khi gửi message/route |
| Phù hợp | Một user/client identity gắn với một connection | Connection được chia sẻ cho nhiều users/tác vụ |
| Kiểm tra route | Dựa vào principal đã establish lúc setup | Dựa vào credentials của request hoặc policy tổng hợp |
| Thay đổi identity | Thường cần kết nối lại hoặc cơ chế có chủ đích | Có thể gửi credentials khác theo request |
| Token hết hạn/thu hồi khi stream đã chạy | Có nguy cơ snapshot identity cũ | Token mới trên request mới; stream đang chạy vẫn cần policy riêng |
| Test bắt buộc | Có/không metadata setup, sai secret, roles, setup rejection | Missing/wrong metadata trên từng route, không kế thừa user khác |
| Rủi ro khi pool connection | Gắn danh tính user A rồi tái sử dụng cho B | Cần cô lập và gắn auth đúng mỗi request |

### Thử theo SETUP: khi server cho phép guest kết nối

Nếu rule là:

```java
.setup().permitAll()
.route("private.feed").authenticated()
```

Một client **không có metadata setup** vẫn có thể mở RSocket connection, nhưng khi gọi `private.feed` phải nhận **onError**. Đây là thiết kế hữu ích để thử hai lỗi tách biệt: **kết nối được** không có nghĩa **route protected gọi được**.

### Thử SETUP bị từ chối ngay

Nếu policy là:

```java
.setup().hasRole("CONNECT")
```

client thiếu role `ROLE_CONNECT` có thể bị từ chối trong quá trình thiết lập socket. Với test, **ghi nhận lỗi từ `connectTcp`/`tcp` hoặc tín hiệu đầu tiên** tùy API/runtime; không ép tất cả lỗi setup thành exception giống lỗi route-level. Phần dự án chính chọn `.setup().permitAll()` để có thể test route-level denial mà không nhầm với lỗi kết nối.

### Đừng nhầm RSocket Simple Authentication với HTTP Basic

Spring Security RSocket hiện hỗ trợ **Simple Authentication Metadata Extension**. `RSocketSecurity.basicAuthentication(...)` tồn tại cho compatibility nhưng đã được đánh dấu deprecated trong các bản Security 6.x; cấu hình mới ưu tiên:

```java
.simpleAuthentication(Customizer.withDefaults())
```

Client dùng **`SimpleAuthenticationEncoder`** cùng **`UsernamePasswordMetadata`** được gắn vào metadata có MIME type thích hợp. Nó không phải HTTP `Authorization: Basic` header. **Simple Authentication không mã hóa credentials**; trong môi trường thật phải dùng transport bảo vệ (TLS/mTLS, WSS) và xử lý secrets an toàn.

## 5. Lập ma trận kiểm thử trước khi viết mã

Giả sử server khai báo:

- `public.ping` — public.
- `private.feed` — cần authenticated user.
- `admin.metrics` — cần `ROLE_ADMIN`.
- `events.private` — một request-stream cần authenticated user.

Ta đăng ký hai user thử nghiệm:

- `reader` với `ROLE_READER`.
- `admin` với `ROLE_READER` và `ROLE_ADMIN`.

| Test case | Setup metadata | Request metadata | Route | Kỳ vọng |
| --- | --- | --- | --- | --- |
| A | Không | Không | `public.ping` | Nhận `"PONG"` |
| B | Không | Không | `private.feed` | `onError`, không có dữ liệu private |
| C | `reader` đúng | Không | `private.feed` | Nhận `"PRIVATE"` |
| D | `reader` đúng | Không | `admin.metrics` | `onError`, không thấy metrics |
| E | `admin` đúng | Không | `admin.metrics` | Nhận `"ADMIN_METRICS"` |
| F | `reader`/password sai | Không | `private.feed` | Kết nối hoặc request lỗi, không được trả data |
| G | Không | `reader` đúng | `private.feed` | Nhận `"PRIVATE"` nếu per-request auth bật |
| H | Không | Không | `events.private` | `onError`, không có event |
| I | `reader` đúng | Không | `events.private` | Có event, consumer có thể cancel sớm |
| J | Không | `admin` đúng | `admin.metrics` | Nhận `"ADMIN_METRICS"` nếu per-request auth bật |
| K | `reader` đúng | Không | route chưa allowlist | Bị từ chối, không âm thầm permit |
| L | `admin` đúng | Không | route public | Vẫn nhận public data, không leak auth metadata |

**Không kiểm tra chỉ một negative test.** Một route có thể trả `onError` vì **không tồn tại controller**, codec không khớp, server chưa chạy hoặc transport lỗi. Vì vậy mỗi denied test cần **positive control** cho **chính route đó** với user đúng quyền. Tốt nhất kiểm tra thêm server-side invocation counters hoặc audit để chứng minh controller không bị thực thi khi bị từ chối.

## 6. Ví dụ Java 17+: RSocket TCP và Spring Security Reactive

Bộ ví dụ dưới đây là dự án Spring Boot 3.x / Spring Security 6.x dùng **RSocket TCP riêng trên port 9898**. Không tạo HTTP REST endpoint và không dùng `WebTestClient`; kiểm thử bằng `RSocketRequester` kết nối tới RSocket server thật.

Cấu hình minh họa:

- `SETUP` cho phép connection không mang credentials; từng route có policy riêng.
- `Simple Authentication` xác minh username/password bằng `MapReactiveUserDetailsService`.
- Password được lưu dạng **BCrypt-based encoded hash** qua `PasswordEncoder` phù hợp (không lưu plaintext trong user repository).
- Bốn routes làm dữ liệu giả lập, không có secret thật.
- Tests dùng random TCP port (`spring.rsocket.server.port=0`) để không phụ thuộc port 9898 hoặc xung đột CI.

**Giới hạn:** Test TCP localhost không có TLS để thuận tiện. **Không triển khai cấu hình truyền plaintext credentials trên TCP công cộng**; production phải có TLS/mTLS hoặc WebSocket Secure, hợp đồng auth và key/secret management phù hợp.

### 6.1. Cấu trúc thư mục

```text
rsocket-security-tests/
  settings.gradle
  build.gradle
  src/main/resources/application.yml
  src/main/java/demo/rsocketauth/
    RSocketAuthApplication.java
    RSocketAuthSecurityConfig.java
    SecureMessageController.java
  src/test/java/demo/rsocketauth/
    RSocketSecurityIntegrationTest.java
```

### 6.2. `settings.gradle`

```groovy
rootProject.name = 'rsocket-security-tests'
```

### 6.3. `build.gradle`

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.0'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
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

    // RSocket security DSL, interceptors, metadata extensions.
    implementation 'org.springframework.security:spring-security-rsocket'
    implementation 'org.springframework.security:spring-security-messaging'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`spring-boot-starter-rsocket` cung cấp RSocket server/client, Reactor Netty và Spring Messaging; `spring-security-rsocket` cung cấp `RSocketSecurity`/authentication interceptors, còn `spring-boot-starter-security` cung cấp authentication support. Sử dụng Spring Boot BOM để chọn phiên bản tương thích; không trộn Spring Security 6.x với Framework/RSocket jars thuộc các major khác. `reactor-test` cung cấp `StepVerifier`.

**Không cần `spring-boot-starter-web`** chỉ để chạy RSocket TCP độc lập. Spring Boot cũng hỗ trợ RSocket over WebSocket trên WebFlux khi cấu hình transport/mapping-path phù hợp; bài này chọn TCP để test ít lớp hơn.

### 6.4. `src/main/resources/application.yml`

```yaml
spring:
  rsocket:
    server:
      port: 9898
      transport: tcp
```

Lệnh `bootRun` sẽ mở RSocket TCP server trên cổng 9898. Trong test, `@SpringBootTest(properties = "spring.rsocket.server.port=0")` ghi đè thành **random free port** và `@LocalRSocketServerPort` lấy port được bind thật.

**Không nhầm RSocket port với HTTP port**: `@LocalServerPort` dành cho HTTP server; RSocket port dùng `@LocalRSocketServerPort`.

### 6.5. `src/main/java/demo/rsocketauth/RSocketAuthApplication.java`

```java
package demo.rsocketauth;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RSocketAuthApplication {
    public static void main(String[] args) {
        SpringApplication.run(RSocketAuthApplication.class, args);
    }
}
```

### 6.6. `src/main/java/demo/rsocketauth/RSocketAuthSecurityConfig.java`

```java
package demo.rsocketauth;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.rsocket.EnableRSocketSecurity;
import org.springframework.security.config.annotation.rsocket.RSocketSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.rsocket.core.PayloadSocketAcceptorInterceptor;

@Configuration
@EnableRSocketSecurity
public class RSocketAuthSecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        // Sinh hash có prefix {bcrypt} theo DelegatingPasswordEncoder.
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService userDetailsService(
            PasswordEncoder encoder) {

        UserDetails reader = User.withUsername("reader")
            .password(encoder.encode("reader-pass"))
            .roles("READER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("admin-pass"))
            .roles("READER", "ADMIN")
            .build();

        return new MapReactiveUserDetailsService(reader, admin);
    }

    @Bean
    PayloadSocketAcceptorInterceptor rsocketInterceptor(
            RSocketSecurity rsocket) {

        rsocket
            .authorizePayload(authorize -> authorize
                // Cho phép kết nối để test denial theo từng route.
                .setup().permitAll()

                .route("public.ping").permitAll()
                .route("private.feed").authenticated()
                .route("admin.metrics").hasRole("ADMIN")
                .route("events.private").authenticated()

                // Không vô tình mở route không được chỉ định.
                .anyRequest().denyAll()

                // Những payload tiếp nối không có route metadata.
                .anyExchange().permitAll())
            .simpleAuthentication(Customizer.withDefaults());

        return rsocket.build();
    }
}
```

**Điểm QA quan trọng:**

1. `@EnableRSocketSecurity` và `RSocketSecurity` là **RSocket API**, không phải `@EnableWebFluxSecurity`/`ServerHttpSecurity` cho HTTP.
2. Với đúng dependencies, Spring Boot tự kết nối RSocket Security socket acceptor interceptor vào RSocket server; không tự gắn interceptor lần thứ hai nếu auto-configuration đã thực hiện.
3. `.setup().permitAll()` là một **chủ đích của bài test**. Không có credentials tại `SETUP` vẫn được tạo connection, nhưng route protected vẫn bị từ chối.
4. `.route("admin.metrics").hasRole("ADMIN")` nằm **trước** catch-all. User reader đã authenticate vẫn không có `ROLE_ADMIN`.
5. `.anyRequest().denyAll()` để route mới không âm thầm public; `.anyExchange().permitAll()` cho payloads không có routing metadata thuộc request đã được kiểm tra. Với ứng dụng channel nhiều message, cần bổ sung policy/check nội dung ở tầng domain.
6. `.simpleAuthentication(Customizer.withDefaults())` cấu hình decoder xác thực RSocket Simple metadata. Không phải HTTP Basic; client cần metadata MIME type và encoder.
7. `MapReactiveUserDetailsService` là một kho user **in-memory dành cho demo**. Password demo có thể đọc ngay trong tài liệu nhưng không được copy sang production. Production dùng identity provider/secret management phù hợp.
8. `PasswordEncoderFactories.createDelegatingPasswordEncoder()` tạo hash có prefix thuật toán như `{bcrypt}`, tương thích với các bộ giải mã mật khẩu mặc định theo Spring Security. Password raw không được lưu trong users bean.

### 6.7. `src/main/java/demo/rsocketauth/SecureMessageController.java`

```java
package demo.rsocketauth;

import java.time.Duration;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Controller
public class SecureMessageController {

    private final AtomicInteger privateInvocations = new AtomicInteger();
    private final AtomicInteger adminInvocations = new AtomicInteger();

    @MessageMapping("public.ping")
    public Mono<String> ping() {
        return Mono.just("PONG");
    }

    @MessageMapping("private.feed")
    public Mono<String> privateFeed() {
        privateInvocations.incrementAndGet();
        return Mono.just("PRIVATE");
    }

    @MessageMapping("admin.metrics")
    public Mono<String> adminMetrics() {
        adminInvocations.incrementAndGet();
        return Mono.just("ADMIN_METRICS");
    }

    @MessageMapping("events.private")
    public Flux<String> privateEvents() {
        return Flux.interval(Duration.ofMillis(100))
            .map(index -> "event-" + index);
    }

    // Counter chỉ phục vụ kiểm thử invocation, không phải API public.
    public int privateCallCount() {
        return privateInvocations.get();
    }

    public int adminCallCount() {
        return adminInvocations.get();
    }
}
```

**Tại sao có counters?** Negative tests có thể xác minh **khi bị chặn thì controller không thực thi**. Nếu chỉ kiểm tra `onError`, một route không tồn tại/codec sai cũng có thể gây lỗi và làm ta tưởng Security hoạt động.

`Flux.interval` là một stream **không kết thúc tự nhiên**, giúp kiểm thử cancellation. Production streams cần backpressure, timeouts/quotas, data ownership, cleanup và revocation policy. Test phải **cancel** sau một vài phần tử thay vì chờ `verifyComplete()` vô hạn.

Các counters demo dùng `AtomicInteger` cho thread safety cơ bản trong bài test, nhưng không phải audit metric. Không dùng chúng để lưu số lần user login/failed password ở hệ thống thật.

## 7. RSocket client test: metadata và encoder đúng chuẩn

### 7.1. MIME type của Simple Authentication

Spring Security RSocket dùng well-known RSocket authentication MIME type:

```java
MimeType SIMPLE_AUTH_MIME =
    MimeTypeUtils.parseMimeType(
        WellKnownMimeType.MESSAGE_RSOCKET_AUTHENTICATION.getString());
```

Imports:

```java
import io.rsocket.metadata.WellKnownMimeType;
import org.springframework.util.MimeType;
import org.springframework.util.MimeTypeUtils;
```

Dùng **`UsernamePasswordMetadata`**, không đưa Basic HTTP header vào request metadata:

```java
UsernamePasswordMetadata credentials =
    new UsernamePasswordMetadata("reader", "reader-pass");
```

Imports:

```java
import org.springframework.security.rsocket.metadata.UsernamePasswordMetadata;
import org.springframework.security.rsocket.metadata.SimpleAuthenticationEncoder;
```

Requester cần `SimpleAuthenticationEncoder` để chuyển `UsernamePasswordMetadata` thành metadata bytes có MIME tương ứng. Spring Boot cung cấp `RSocketRequester.Builder` prototype; tạo **builder mới** cho mỗi kết nối vì builder là stateful.

### 7.2. SETUP metadata

Ví dụ kết nối trực tiếp:

```java
RSocketRequester requester = builder
    .rsocketStrategies(strategies ->
        strategies.encoder(new SimpleAuthenticationEncoder()))
    .setupMetadata(
        new UsernamePasswordMetadata("reader", "reader-pass"),
        SIMPLE_AUTH_MIME)
    .tcp("localhost", 9898);
```

Đoạn này minh họa cách dựng client, không phải class Java độc lập. Nếu muốn test một user khác, tạo **một builder mới** thay vì tái sử dụng builder đã `.setupMetadata` của user cũ.

### 7.3. Metadata theo từng request

Khi connection không có credentials, request cụ thể có thể cung cấp:

```java
Mono<String> response = requester
    .route("private.feed")
    .metadata(
        new UsernamePasswordMetadata("reader", "reader-pass"),
        SIMPLE_AUTH_MIME)
    .retrieveMono(String.class);
```

Đây là **per-request authentication** được Spring Security hỗ trợ. Dữ liệu credentials không xuất hiện trong payload nghiệp vụ; metadata phải được encode đúng và transport phải được bảo vệ bằng TLS trong production.

**Không tự đặt `UsernamePasswordMetadata` trên mọi request của một requester dùng chung nhiều người dùng**, nếu giá trị này là credentials của một user khác. Mỗi request phải gắn đúng identity và scopes của actor đang được phục vụ, không để user B thừa hưởng user A.

## 8. Integration test đầy đủ qua RSocket TCP thật

File dưới đây có thể đặt tại `src/test/java/demo/rsocketauth/RSocketSecurityIntegrationTest.java`. Test dùng RSocket server tự khởi động từ Spring Boot và port ngẫu nhiên. Không cần mock Security interceptor hoặc fake response chỉ trả exception.

### 8.1. Test code

```java
package demo.rsocketauth;

import java.time.Duration;

import io.rsocket.metadata.WellKnownMimeType;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.rsocket.server.LocalRSocketServerPort;
import org.springframework.messaging.rsocket.RSocketRequester;
import org.springframework.security.rsocket.metadata.SimpleAuthenticationEncoder;
import org.springframework.security.rsocket.metadata.UsernamePasswordMetadata;
import org.springframework.util.MimeType;
import org.springframework.util.MimeTypeUtils;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(properties = "spring.rsocket.server.port=0")
class RSocketSecurityIntegrationTest {

    private static final MimeType AUTH_MIME =
        MimeTypeUtils.parseMimeType(
            WellKnownMimeType.MESSAGE_RSOCKET_AUTHENTICATION.getString());

    @LocalRSocketServerPort
    int port;

    @Autowired
    ObjectProvider<RSocketRequester.Builder> requesterBuilders;

    @Autowired
    SecureMessageController controller;

    // Builder là prototype và stateful: mỗi lần mở lấy builder mới.
    private RSocketRequester openAnonymousConnection() {
        return requesterBuilders.getObject()
            .rsocketStrategies(s ->
                s.encoder(new SimpleAuthenticationEncoder()))
            .tcp("localhost", port);
    }

    private RSocketRequester openConnection(
            String username, String password) {
        return requesterBuilders.getObject()
            .rsocketStrategies(s ->
                s.encoder(new SimpleAuthenticationEncoder()))
            .setupMetadata(
                new UsernamePasswordMetadata(username, password),
                AUTH_MIME)
            .tcp("localhost", port);
    }

    @Test
    void publicRouteWorksWithoutAuthentication() {
        RSocketRequester client = openAnonymousConnection();
        try {
            StepVerifier.create(
                    client.route("public.ping")
                        .retrieveMono(String.class))
                .expectNext("PONG")
                .verifyComplete();
        } finally {
            client.dispose();
        }
    }

    @Test
    void missingAuthenticationCannotReadPrivateRoute() {
        RSocketRequester client = openAnonymousConnection();
        try {
            int before = controller.privateCallCount();

            StepVerifier.create(
                    client.route("private.feed")
                        .retrieveMono(String.class))
                .expectError()
                .verify(Duration.ofSeconds(5));

            // Denied request không được gọi private controller.
            assertEquals(before, controller.privateCallCount());
        } finally {
            client.dispose();
        }
    }

    @Test
    void validReaderCanReadPrivateRoute() {
        RSocketRequester client =
            openConnection("reader", "reader-pass");
        try {
            StepVerifier.create(
                    client.route("private.feed")
                        .retrieveMono(String.class))
                .expectNext("PRIVATE")
                .verifyComplete();
        } finally {
            client.dispose();
        }
    }

    @Test
    void authenticatedReaderCannotReadAdminRoute() {
        RSocketRequester client =
            openConnection("reader", "reader-pass");
        try {
            int before = controller.adminCallCount();

            StepVerifier.create(
                    client.route("admin.metrics")
                        .retrieveMono(String.class))
                .expectError()
                .verify(Duration.ofSeconds(5));

            // Login thành công không đồng nghĩa có ROLE_ADMIN.
            assertEquals(before, controller.adminCallCount());
        } finally {
            client.dispose();
        }
    }

    @Test
    void validAdminCanReadSameAdminRoute() {
        RSocketRequester client =
            openConnection("admin", "admin-pass");
        try {
            StepVerifier.create(
                    client.route("admin.metrics")
                        .retrieveMono(String.class))
                .expectNext("ADMIN_METRICS")
                .verifyComplete();
        } finally {
            client.dispose();
        }
    }

    @Test
    void invalidPasswordNeverReadsPrivateData() {
        // Tùy timing/setup implementation, lỗi có thể xuất hiện
        // khi connect hoặc trên request tiếp theo.
        StepVerifier.create(
                reactor.core.publisher.Mono.fromCallable(() ->
                        openConnection("reader", "wrong-password"))
                    .flatMap(client ->
                        client.route("private.feed")
                            .retrieveMono(String.class)
                            .doFinally(signal -> client.dispose())))
            .expectError()
            .verify(Duration.ofSeconds(5));
    }

    @Test
    void perRequestCredentialsCanAuthenticateGuestConnection() {
        RSocketRequester client = openAnonymousConnection();
        try {
            StepVerifier.create(
                    client.route("private.feed")
                        .metadata(
                            new UsernamePasswordMetadata(
                                "reader", "reader-pass"),
                            AUTH_MIME)
                        .retrieveMono(String.class))
                .expectNext("PRIVATE")
                .verifyComplete();
        } finally {
            client.dispose();
        }
    }

    @Test
    void missingAuthenticationCannotStartProtectedStream() {
        RSocketRequester client = openAnonymousConnection();
        try {
            StepVerifier.create(
                    client.route("events.private")
                        .retrieveFlux(String.class))
                .expectError()
                .verify(Duration.ofSeconds(5));
        } finally {
            client.dispose();
        }
    }

    @Test
    void authorizedStreamCanEmitAndBeCancelled() {
        RSocketRequester client =
            openConnection("reader", "reader-pass");
        try {
            StepVerifier.create(
                    client.route("events.private")
                        .retrieveFlux(String.class))
                .expectNext("event-0", "event-1")
                .thenCancel()
                .verify(Duration.ofSeconds(5));
        } finally {
            client.dispose();
        }
    }

    @Test
    void unknownRouteIsNotAccidentallyPublic() {
        RSocketRequester client =
            openConnection("reader", "reader-pass");
        try {
            StepVerifier.create(
                    client.route("admin.unknown")
                        .retrieveMono(String.class))
                .expectError()
                .verify(Duration.ofSeconds(5));
        } finally {
            client.dispose();
        }
    }
}
```

### 8.2. Mức độ tin cậy của bộ test

**Đây là integration test thật** của RSocket transport + Spring Messaging routes + RSocket Security interceptors + Simple Authentication, không phải mock MVC. Nó kiểm tra:

- Anonymous **kết nối được** do `.setup().permitAll()` nhưng không đọc được `private.feed`.
- Cùng route `private.feed` hoạt động với user reader, chứng minh denied test không phải lỗi “route không tồn tại”.
- Reader đã authenticated vẫn không truy cập được `admin.metrics`.
- Admin truy cập **chính route đó** thành công.
- Credentials sai không trả nội dung private.
- Per-request metadata có thể authenticate trên connection ban đầu anonymous.
- Request-stream không có auth không phát event; user hợp lệ nhận được dữ liệu và có thể cancel.
- Controller counters không tăng khi request bị denied, tăng khi positive case đi qua handler.

**Không assert nguyên văn exception message** như `"Access Denied"` hay `"Unauthorized"`; cách Spring Security/RSocket Java chuyển exception thành RSocket frame/message có thể thay đổi giữa versions. Bộ test chủ ý kiểm tra `onError` cùng positive controls và invocation counters, tránh test xanh giả chỉ vì một chuỗi text có sẵn.

**Cần lưu ý khi chạy parallel tests:** các `AtomicInteger` counters trong singleton controller được chia sẻ giữa methods; JUnit chạy tuần tự theo mặc định trong nhiều dự án, nhưng khi bật `junit.jupiter.execution.parallel.enabled=true`, counter assertion `before/after` có thể bị ảnh hưởng bởi test khác đồng thời. Khi chạy parallel, cô lập context/counter theo request ID, dùng spy với interaction isolation hoặc không dựa vào global counters.

### 8.3. Chạy test

```bash
# Linux/macOS:
./gradlew test --tests 'demo.rsocketauth.RSocketSecurityIntegrationTest'

# Windows:
gradlew.bat test --tests "demo.rsocketauth.RSocketSecurityIntegrationTest"

# Tất cả test trong project:
./gradlew test
```

Ví dụ **expected results** theo logic test:

```text
publicRouteWorksWithoutAuthentication          PASS
missingAuthenticationCannotReadPrivateRoute    PASS
validReaderCanReadPrivateRoute                 PASS
authenticatedReaderCannotReadAdminRoute        PASS
validAdminCanReadSameAdminRoute                PASS
invalidPasswordNeverReadsPrivateData           PASS
perRequestCredentialsCanAuthenticateGuestConnection PASS
missingAuthenticationCannotStartProtectedStream PASS
authorizedStreamCanEmitAndBeCancelled          PASS
unknownRouteIsNotAccidentallyPublic            PASS
```

Danh sách trên mô tả **kết quả kiểm thử mong đợi**, không phải log Gradle đã chạy thực tế. Với môi trường khác, hãy xác minh cấu hình Boot/RSocket và kết quả test thật. Nếu test báo lỗi codec/connection/port thay vì authorization, cần sửa nguyên nhân đó, **không tính là Security denial hợp lệ**.

## 9. Vì sao test “thiếu quyền” phải chứng minh user đã authenticate?

Một sai lầm thường gặp:

```java
StepVerifier.create(
    anonymousRequester.route("admin.metrics")
        .retrieveMono(String.class))
    .expectError()
    .verify();
```

Test này **không chứng minh route đang kiểm tra `ROLE_ADMIN`**. Nó chỉ chứng minh một anonymous request thất bại; kể cả cấu hình chỉ `.authenticated()` cũng có thể làm nó thất bại.

Để chứng minh **authorization**:

1. Chuẩn bị user hợp lệ `reader` với `ROLE_READER`, không có `ROLE_ADMIN`.
2. Gọi `private.feed` bằng chính user đó và **nhận response thành công**.
3. Gọi `admin.metrics` cũng bằng user đó và nhận **onError**.
4. Gọi **cùng route admin** bằng user `admin` có `ROLE_ADMIN`, nhận success.
5. Kiểm tra protected handler không chạy ở đường denied.
6. Nếu cần chắc chắn rule không bị lách, kiểm tra thứ tự `.route("admin.metrics").hasRole("ADMIN")` trước `.anyRequest().authenticated()`.

Bộ test ba tầng này giúp tách lỗi **“user chưa authenticate”** với lỗi **“user authenticated nhưng không có authority”**. Không lấy message `"Denied"` từ client làm bằng chứng duy nhất.

### Khi app dùng scopes thay roles

Với JWT, authority có thể mang prefix `SCOPE_`, ví dụ `SCOPE_reports.read`. Trong RSocket Security rule có thể dùng:

```java
.route("reports.read").hasAuthority("SCOPE_reports.read")
```

Không viết `.hasRole("reports.read")` nếu token mapping tạo `SCOPE_reports.read`. `hasRole("ADMIN")` thường kiểm tra `ROLE_ADMIN`, không tự lấy từ JWT `scope`.

Nếu có domain-level ownership/tenant check, token có đủ `SCOPE_reports.read` **không tự động có quyền mọi report**; cần custom reactive authorization manager hoặc kiểm tra trong service logic theo principal và resource ID.

## 10. Kiểm thử ở cấp SETUP: một mô hình chính sách khác

Dự án trên cố ý cho phép setup anonymous. Với một **service-to-service RSocket connection** cần client identity ngay khi kết nối, một policy khác có thể là:

```java
// Phương án thay thế, không cài cùng cấu hình chính:
rsocket.authorizePayload(authorize -> authorize
    .setup().hasRole("CONNECT")
    .route("public.ping").permitAll()
    .route("admin.metrics").hasRole("ADMIN")
    .anyRequest().authenticated()
    .anyExchange().permitAll()
);
```

Một user có `ROLE_CONNECT` được tạo connection, nhưng **không tự có `ROLE_ADMIN`**. Cần test:

- Không có setup credentials → setup/connection bị từ chối.
- Setup credentials sai → từ chối.
- Credentials hợp lệ nhưng thiếu `ROLE_CONNECT` → từ chối ngay ở SETUP.
- User có `ROLE_CONNECT` (không `ROLE_ADMIN`) → connect được, admin route bị deny.
- User có cả `ROLE_CONNECT`, `ROLE_ADMIN` → connect và gọi admin route thành công.

Đây là **phương án test riêng**, không phải extension được bật trong ví dụ chính. Nếu chỉ sửa `.setup().hasRole("CONNECT")` mà không thêm `ROLE_CONNECT` cho bất kỳ user nào, tất cả connections sẽ bị từ chối, test route-level không chạy được. Điều đó là cấu hình sai mục đích test, không phải bằng chứng route authorization đúng.

### Cách bắt lỗi SETUP khi kết nối được thực hiện bất đồng bộ

RSocketRequester API có biến thể trả `Mono<RSocketRequester>` cho connection hoặc phương thức tạo requester đồng bộ tùy Framework version. Với kết nối có thể lỗi trước request, một cách bao bọc trong test:

```java
Mono<String> attempt = Mono.fromCallable(() ->
        requesterBuilderWithSetupMetadata.tcp("localhost", port))
    .flatMap(requester ->
        requester.route("private.feed")
            .retrieveMono(String.class)
            .doFinally(signal -> requester.dispose()));
```

`requesterBuilderWithSetupMetadata` trong đoạn này là **biến minh họa**, đã cấu hình bằng `RSocketRequester.Builder` chứa setup credentials. Mục tiêu là không để exception của quá trình connect xảy ra **trước** khi `StepVerifier` nhận publisher. Đừng gọi `Mono.fromCallable(() -> connect()).block()` trong Netty event loop; trong test JUnit việc tạo client trên test thread là một trường hợp khác.

**Lưu ý protocol:** RSocket SETUP rejection không phải một HTTP `401`; thường có RSocket error code như `REJECTED_SETUP` ở tầng connection. Exact exception/error text là chi tiết của transport/runtime; assert theo event semantics và loại lỗi phù hợp với thư viện đang dùng.

## 11. Long-lived request-stream: bài test không được dừng ở phần tử đầu

RSocket hay được dùng cho telemetry, giá/đơn hàng theo thời gian thực, subscription feed và thiết bị IoT. Những luồng này tồn tại lâu hơn một HTTP request-response.

Một stream protected nên có ít nhất các test:

1. **Anonymous subscription** tới route protected → không nhận event, publisher có `onError`.
2. **Authenticated, đủ quyền** → nhận một vài events theo thứ tự, có thể cancel.
3. **Authenticated nhưng thiếu quyền** trên stream admin → không nhận event nào.
4. **Cancellation** từ client → upstream được giải phóng theo policy, không tiếp tục xử lý vô hạn.
5. **Backpressure** khi subscriber yêu cầu ít hơn tốc độ phát → không chiếm bộ nhớ vô hạn; cần kiểm tra `request(n)`, buffering/drop policy nếu domain yêu cầu.
6. **Connection drop/reconnect** → không dùng lại context của một principal khác một cách vô tình.
7. **Token hết hạn giữa stream** (nếu JWT/SETUP auth) → hành vi revocation/reauth phải được thiết kế và test; không mặc định framework tự ngắt stream.
8. **Role hoặc tenant membership bị thu hồi sau subscribe** → xác định phải cắt stream tức thì hay chấp nhận kiểm tra tại lần subscription kế tiếp; implement chủ động nếu cần.

Test trong phần 8 sử dụng:

```java
StepVerifier.create(
    client.route("events.private").retrieveFlux(String.class))
    .expectNext("event-0", "event-1")
    .thenCancel()
    .verify(Duration.ofSeconds(5));
```

Nó chứng minh stream bắt đầu khi authenticated và client có thể cancel sau hai phần tử. Nó **không** chứng minh backend đã xử lý revocation giữa stream, cũng không đo backpressure/cancellation cleanup. Những điều đó cần thêm instrumentation, test clocks/virtual time hoặc integration test có fake IdP/revocation events.

### Cẩn trọng với `StepVerifier.withVirtualTime`

`withVirtualTime` có thể kiểm thử `Flux.interval` nội bộ với `VirtualTimeScheduler` nếu publisher được tạo lazy và mọi timer đều điều khiển được. Nhưng trên **RSocket transport/network thật**, clock của Netty socket, TLS, scheduling và remote server không tự được chuyển sang virtual time. Vì vậy bài dùng `Duration.ofMillis(100)` và timeout tổng 5 giây cho test qua TCP thật; không đặt `withVirtualTime` rồi giả sử đã tua thời gian ở cả server.

## 12. Khi dùng JWT/Bearer thay Simple Authentication

RSocket Security hỗ trợ **Bearer Authentication Metadata Extension**, thường dùng khi application nhận JWT access token thay username/password.

Server:

```java
@Bean
PayloadSocketAcceptorInterceptor rsocketInterceptor(
        RSocketSecurity rsocket) {
    rsocket
        .authorizePayload(authorize -> authorize
            .setup().permitAll()
            .route("public.ping").permitAll()
            .route("reports.read")
                .hasAuthority("SCOPE_reports.read")
            .anyRequest().authenticated()
            .anyExchange().permitAll())
        .jwt(Customizer.withDefaults());
    return rsocket.build();
}
```

Đây là **cấu hình thay thế**, không bật đồng thời với `.simpleAuthentication` trong ví dụ chính nếu chưa thiết kế rõ cách phân giải nhiều cơ chế. Để cấu hình `.jwt(...)`, Spring Security cần `ReactiveJwtDecoder` bean phù hợp; issuer/JWK trust, signature, `exp`, `nbf`, `aud`/scope mapping phải được xác minh theo policy.

Client gửi một `BearerTokenMetadata` tại SETUP hoặc request:

```java
MimeType authMime = MimeTypeUtils.parseMimeType(
    WellKnownMimeType.MESSAGE_RSOCKET_AUTHENTICATION.getString());

BearerTokenMetadata bearer =
    new BearerTokenMetadata(accessToken);

// SETUP:
RSocketRequester requester = builder
    .setupMetadata(bearer, authMime)
    .tcp("localhost", port);

// Hoặc trong request:
Mono<String> result = requester.route("reports.read")
    .metadata(bearer, authMime)
    .retrieveMono(String.class);
```

**Đây là snippet tích hợp, không phải class độc lập**: `accessToken`, `port`, `builder` phải được cấu hình trong chương trình thật. Import `org.springframework.security.rsocket.metadata.BearerTokenMetadata`. JWT phải được phát bởi issuer đáng tin; không dùng chuỗi tự dựng hoặc ID token thay access token của Resource Server.

### Matrix cho JWT RSocket

| JWT/token | Nội dung | Kỳ vọng |
| --- | --- | --- |
| Không có Bearer metadata | Route protected | `onError` |
| Bearer sai định dạng | Không decode được | `onError` authentication |
| JWT sai chữ ký | Signature invalid | `onError` authentication |
| JWT hết hạn | `exp` quá hạn | `onError` authentication |
| JWT đúng, thiếu `SCOPE_reports.read` | Authenticated nhưng thiếu quyền | `onError` authorization |
| JWT đúng, có `SCOPE_reports.read` | Đủ scope | Data success |
| JWT đúng issuer nhưng sai audience | API policy không chấp nhận | `onError` authentication |
| JWT hợp lệ lúc SETUP, hết hạn sau 1 giờ | Connection/stream vẫn mở | Phụ thuộc reauth/revocation design, **không tự bảo đảm bị cắt** |

**Kiểm thử thật sự JWT validation:** phát JWT ký bằng **test private key**, cung cấp trusted test JWKS/public key và cấu hình `ReactiveJwtDecoder` test. Không dùng authentication mock rồi tuyên bố đã kiểm tra signature, expiry hoặc issuer. Nếu chỉ muốn test route scope policy, mock đã xác thực hữu ích, nhưng phải ghi rõ nó bỏ qua tầng cryptographic verification.

## 13. Các lỗi và status: RSocket không dùng HTTP 401/403 cho mỗi route

Một vài khác biệt thường gây test sai:

| Lỗi | HTTP REST thường thấy | RSocket trên TCP |
| --- | --- | --- |
| Thiếu credentials | 401 | Setup rejection hoặc request publisher `onError` |
| Credentials sai | 401 | Authentication failure, RSocket error |
| User hợp lệ thiếu role/scope | 403 | Authorization denial, RSocket error |
| Route không tồn tại | 404 | Routing/handler RSocket error |
| Codec sai, payload sai định dạng | 400 | Decode/serialization error qua RSocket |
| Socket bị mất kết nối | Network error | Error/connection termination, chưa chứng minh Security denial |
| Setup không được chấp nhận | Không có HTTP tương đương trực tiếp | RSocket `REJECTED_SETUP` hoặc loại protocol error tương ứng |
| Request response lỗi | Có HTTP status | RSocket `ERROR` frame / `onError` |

**Không dựa vào một chuỗi `"Access Denied"` duy nhất** để phân loại. Cần xem route đã tồn tại, credentials của test user được verify thành công ở route khác, role đúng, và đôi khi cần kiểm tra `RSocketErrorException.errorCode` hoặc server audit/metrics theo version.

Các thư viện/client có thể map lỗi thành exception wrapper khác nhau. Với ứng dụng production, nên định nghĩa **một error contract an toàn** cho client nhưng không trả raw credentials, JWT, security context hay backend stack trace trong RSocket error message. Nếu cần error code domain-level, phải phân biệt authentication failure, authorization denied và validation lỗi payload.

## 14. Không quên `request-channel` và fire-and-forget

### Fire-and-forget

Với `REQUEST_FNF`, client **không có response payload nghiệp vụ** để xác nhận server nhận hay từ chối thao tác. Một publisher completion trên client có thể chỉ nghĩa frame đã được gửi, không chứng minh side effect server đã xảy ra. Khi kiểm thử authorization cho fire-and-forget có side effect:

1. Gửi request từ guest/reader/admin theo ma trận.
2. Kiểm tra server-side audited invocation/side effect **không xảy ra** nếu thiếu quyền.
3. Chờ xác nhận trạng thái theo một cơ chế test riêng (repository/fake service/metrics), không chỉ assert `Mono<Void>` complete.
4. Tránh timeout/race làm test xanh giả.
5. Với yêu cầu nghiệp vụ đảm bảo kết quả, cân nhắc request-response/ack protocol thay vì chỉ FNF.

### Request-channel

`REQUEST_CHANNEL` là một stream dữ liệu hai chiều; các payload frame có thể không mang route metadata sau frame đầu. Nếu kiểm tra route chỉ ở request đầu, một client đã được cấp quyền có thể gửi các item mới trong suốt cuộc gọi. Cần:

- Quy định authorization per-channel hay per-item.
- Đối chiếu tenant/resource ID của mỗi item tại service layer.
- Bound data sizes và áp backpressure.
- Kiểm tra cancellation và client reconnect.
- Nếu principal/token đổi giữa các item, thiết kế explicit reauthentication hoặc channel closure policy.
- Test thiếu quyền ở **frame đầu** và hành vi khi quyền bị thu hồi **giữa channel** nếu yêu cầu nghiệp vụ đòi.

Không dùng `.anyExchange().permitAll()` làm lý do bỏ mọi kiểm tra trong service khi messages mang dữ liệu nhạy cảm.

## 15. Kịch bản kiểm thử revocation, logout và connection dài

Khi authenticating tại SETUP, authorization có thể dựa trên principal đã được tạo ở thời điểm thiết lập connection. Một user bị xóa role trong DB sau đó **không mặc nhiên thay đổi `Authentication` object đã tồn tại trên socket**.

Ví dụ:

```text
T0: user reader kết nối, mang ROLE_READER.
T1: server cho phép subscription events.private.
T2: hệ thống IAM vô hiệu hóa reader.
T3: stream vẫn phát dữ liệu nếu không có reauth/revocation logic riêng.
```

Nếu sản phẩm bắt buộc **cắt stream tại T2**, cần thiết kế một trong các biện pháp:

- Đóng socket/stream khi nhận sự kiện revoke của identity provider hoặc policy service.
- Dùng short-lived tokens và yêu cầu reauthentication hoặc reconnect theo chu kỳ.
- Đối với mỗi event nhạy cảm, kiểm tra permission/tenant tại data source hoặc stream pipeline, với cache TTL ngắn có mục đích.
- Giới hạn connection/stream lifetime theo chính sách.
- Có idempotent cleanup và không tạo race dẫn tới gửi thêm dữ liệu sau revoke beyond documented tolerance.

**Không chỉ set `JWT exp=60s` rồi mặc nhiên khẳng định stream bị cắt sau 60 giây.** JWT validation thường diễn ra khi authentication được thực hiện; một stream đã được cấp quyền trước đó có thể tiếp tục nếu không thêm policy kiểm tra lại.

Test revocation cần kiểm soát thời điểm (latch/test sink/virtual clock phù hợp), phát một số events trước revoke, rồi revoke và kiểm tra không nhận thêm event nhạy cảm hoặc nhận termination signal trong SLA đã định.

## 16. Vấn đề bảo mật của transport và metadata

RSocket Simple Authentication gửi **username/password dưới dạng metadata có cấu trúc**, không mã hóa những giá trị này. Metadata không phải một kênh truyền bảo mật riêng; nếu kết nối TCP không có TLS, kẻ nghe lén có thể nhìn thấy credentials hoặc payload.

Do đó:

1. Test localhost TCP không TLS chỉ để luyện API/test.
2. Production dùng TLS/mTLS khi dùng TCP, hoặc WebSocket Secure (`wss://`) khi triển khai trên WebSocket.
3. Ràng buộc server identity, certificate trust và key rotation phù hợp với tổ chức.
4. Không log raw RSocket frames, setup metadata, Simple credentials, Bearer tokens hoặc payload PII khi bật debug.
5. Không đặt password/token vào `.route("...")` hoặc `setupData` dưới dạng string dễ bị log.
6. Giới hạn kích thước metadata/payload, số connections, số streams, backpressure request count và tốc độ kết nối.
7. Rate-limit failed authentication attempts và audit loại lỗi bằng correlation ID an toàn.
8. Với pooled/shared connections, đừng gắn user credentials ở SETUP rồi cho request của user khác dùng chung vô ý.
9. Bảo đảm `@MessageMapping` thực sự được Security interceptor bảo vệ; custom bootstrap/server có thể cần tự gắn `SecuritySocketAcceptorInterceptor`.
10. Test network reconnect, session resumption và revoke trong deployment thực, không suy ra từ một localhost test.

## 17. Kiểm thử method-level/domain authorization

Các rule `RSocketSecurity.authorizePayload(...)` là một lớp **chặn trước handler** dựa trên route/principal. Với nghiệp vụ có nhiều report, order hoặc tenant, phải kiểm tra **quyền đối với đối tượng cụ thể**:

```text
admin.metrics        → ROLE_ADMIN
report.read.{id}     → SCOPE_reports.read VÀ principal được phép đọc id
project.events.{id}  → principal phải thuộc project/tenant này
```

`ROLE_ADMIN`/`SCOPE_reports.read` không tự giải quyết **object-level authorization**. Có thể dùng custom `ReactiveAuthorizationManager<PayloadExchange>` hoặc kiểm tra ở service với principal đã xác thực và resource ID trusted. Tách:

- Route-level guard chặn user không có quyền cơ bản.
- Domain guard kiểm tra ownership, tenant, project membership và trạng thái resource.
- Stream policy quyết định quyền có cần được đánh giá lại trong quá trình phát events hay không.

Test negative cases phải có cả:

- Alice được đọc project A, không đọc project B.
- Bob cùng role nhưng tenant khác không được đọc dữ liệu Alice.
- Thay route parameter/resource ID không làm lộ data.
- Missing/invalid metadata không trả tài liệu nhạy cảm.
- Error message không tiết lộ resource tồn tại hay không nếu domain policy yêu cầu.

Nếu dùng annotations của Method Security Reactive, cần kiểm tra việc mở `@EnableReactiveMethodSecurity`, proxy boundaries và Reactor Context đúng trong RSocket handlers. Đừng cho rằng HTTP method-security annotation tự được áp vào mọi RSocket route nếu chưa bật và test.

## 18. Chẩn đoán khi test RSocket thất bại

| Triệu chứng | Nguyên nhân phổ biến | Hướng kiểm tra |
| --- | --- | --- |
| Tất cả request đều báo connection refused | RSocket server chưa bind, port sai | `spring.rsocket.server.port`, `@LocalRSocketServerPort` |
| Test anonymous private route trả dữ liệu | Security interceptor chưa được gắn, rule public quá rộng | `@EnableRSocketSecurity`, dependencies, Boot RSocket auto config |
| Reader gọi admin được | Catch-all `.authenticated()` đặt trước `.hasRole("ADMIN")` | Thứ tự `authorizePayload` |
| Reader không gọi private được | Simple metadata sai MIME/encoder, password sai, auth config thiếu | `SimpleAuthenticationEncoder`, `UsernamePasswordMetadata` |
| Reader không connect được | `.setup().hasRole(...)` quá chặt hoặc setup metadata bị mất | SETUP policy và user roles |
| Anonymous không connect dù `.setup().permitAll()` | Authentication metadata hỏng được gửi/codec lỗi hoặc setup handler khác | Requester builder và SETUP metadata |
| Test `.expectError()` pass do route không tồn tại | Không có positive control | Test cùng route với admin/reader hợp lệ |
| Test đúng ở máy A, fail ở CI | Port cố định, race, scheduler/cold start | Random port và timeout bounded |
| Request-stream test treo mãi | Flux vô hạn, test đợi `verifyComplete()` | Dùng `.thenCancel().verify(Duration)` |
| Fire-and-forget `Mono<Void>` complete nhưng side effect xảy ra | Test nhầm send-complete với authorization | Kiểm tra server-side side effect/audit |
| Token hết hạn nhưng stream vẫn phát | Không có mid-stream reauth | Revocation/stream lifecycle policy |
| Guest gọi public route bị lỗi | `.anyRequest().authenticated()` đặt trước public rule | Thứ tự policy |
| Auth request sau khi logout vẫn được xử lý | Connection-level principal còn tồn tại | Đóng connection/re-auth rules |
| Error là serialization/codec exception | Data MIME hoặc DTO không khớp | Test codec/serialization, không gộp với auth deny |
| Client A request dùng identity B | Dùng chung builder/requester với setup metadata B | Tách connection hoặc per-request auth rõ |
| Logs có password/token | Raw RSocket frame logging | Redact/auth audit |
| Unit test security pass nhưng production mở route | Mock không gắn thật socket interceptor | TCP integration test + deployment validation |

### Quy trình debug tám bước

1. **Phân loại transport trước**: kết nối có được tạo không? Port/transport TCP hay WebSocket đúng chứ?
2. **Kiểm tra security interceptor**: Spring Boot đã gắn `PayloadSocketAcceptorInterceptor`/`SecuritySocketAcceptorInterceptor` thật chưa?
3. **Kiểm tra metadata**: `MESSAGE_RSOCKET_AUTHENTICATION`, encoder, `UsernamePasswordMetadata`/Bearer token đúng nơi (SETUP hay REQUEST) không?
4. **Kiểm tra rule và thứ tự**: `.setup`, `.route`, `.anyRequest`, `.anyExchange` có rule lỏng đặt trước rule chặt không?
5. **Phân biệt authentication/authorization**: user reader gọi route thường có được không trước khi kết luận admin thiếu quyền?
6. **Kiểm tra positive/negative controls**: cùng route admin được khi role phù hợp; handler invocation không xảy ra ở denied path.
7. **Với stream**, xác nhận số phần tử trước/ sau revoke, cancellation, connection lifetime và backpressure.
8. **Kiểm tra secret hygiene**: không log credentials, stack trace nhạy cảm hoặc raw frames; có TLS cho môi trường thật.

## 19. Sai lầm phổ biến cần tránh

**Sai lầm 1 — Dùng `WebTestClient` để assert 401/403 cho RSocket TCP.**  
RSocket không dùng HTTP response status trên từng route. Dùng `RSocketRequester` và `StepVerifier` hoặc RSocket Java low-level test tools.

**Sai lầm 2 — Test thiếu quyền chỉ bằng anonymous user.**  
Anonymous bị từ chối không chứng minh route đòi `ROLE_ADMIN`; phải có authenticated reader và positive admin control.

**Sai lầm 3 — Tạo requester `builder.tcp(...)` trước khi gắn `SimpleAuthenticationEncoder`.**  
Metadata `UsernamePasswordMetadata` cần đúng encoder; đặt vào Spring `RSocketStrategies` trước khi kết nối/gửi.

**Sai lầm 4 — Quên MIME type của authentication metadata.**  
Dùng `MESSAGE_RSOCKET_AUTHENTICATION` khi gửi Simple/Bearer metadata, không dùng một string ngẫu nhiên.

**Sai lầm 5 — Gửi credentials ở SETUP rồi mong request sau đó của user khác tự đổi identity.**  
Setup identity thường gắn với connection. Shared connection cần per-request authentication thiết kế có chủ đích.

**Sai lầm 6 — `.anyRequest().authenticated()` đặt trước `.route("admin.metrics").hasRole("ADMIN")`.**  
Rule đầu match trước làm route admin chỉ cần login.

**Sai lầm 7 — Dùng `.anyExchange().permitAll()` làm lý do không có object-level authorization.**  
Route guard và domain guard là hai tầng khác nhau; request-channel/stream cần policy riêng.

**Sai lầm 8 — Dùng `Mono.empty()` của RSocket FNF làm bằng chứng server đã thực hiện side effect.**  
Không có response payload ứng dụng để xác nhận; cần kiểm tra server-side state/audit.

**Sai lầm 9 — `verifyComplete()` trên stream vô hạn.**  
Test treo; dùng `expectNextCount(n)`, `thenCancel`, `verify(Duration...)`.

**Sai lầm 10 — Bỏ TLS vì Simple Authentication “có encoder”.**  
Encoder là serialize metadata, **không mã hóa transport**. Credentials có thể bị lộ.

**Sai lầm 11 — Coi JWT hết hạn ở phút thứ 10 là auto-disconnect stream đã có từ phút 0.**  
Không có bảo đảm reauth giữa stream nếu chưa thiết kế và kiểm thử.

**Sai lầm 12 — Dùng một exception message để nhận diện mọi security failure.**  
Transport, routing, codec và authorization đều có thể tạo `onError`; cần phân loại và positive controls.

**Sai lầm 13 — Test với port cố định ở CI.**  
Port 9898 có thể bận; dùng `spring.rsocket.server.port=0` và `@LocalRSocketServerPort`.

**Sai lầm 14 — Không `dispose()` requester sau test.**  
RSocket connection/threads có thể còn sống giữa tests, gây flakiness và rò tài nguyên.

**Sai lầm 15 — Log raw RSocket setup frames.**  
Simple metadata/Bearer token có thể bị ghi ra logs/traces; phải redaction.

## 20. Checklist production/test

| Hạng mục | Tiêu chí |
| --- | --- |
| RSocket Security | `@EnableRSocketSecurity`, interceptor thật được gắn |
| SETUP policy | Guest connection vs required setup role rõ ràng |
| Route policy | Public, authenticated và `ROLE_ADMIN` tách biệt |
| Rule order | Rule chặt đứng trước catch-all |
| Metadata | MIME `MESSAGE_RSOCKET_AUTHENTICATION` đúng |
| Client codec | Có `SimpleAuthenticationEncoder` khi dùng Simple auth |
| Requester isolation | Không chia sẻ setup user identity sai actor |
| Missing credentials | Protected route trả `onError`, không lộ data |
| Wrong credentials | Không establish trusted authentication |
| Insufficient authority | Reader valid không gọi được admin route |
| Positive controls | Reader private thành công; admin admin thành công |
| No handler execution | Denied path không invoke private handler |
| Random test port | `@LocalRSocketServerPort` thay port cứng |
| Bounded tests | `StepVerifier.verify(Duration...)`, stream cancel |
| FNF/channel | Kiểm tra server side effects và per-item policy |
| Long-lived streams | Revocation/role change/expiry behavior có hợp đồng |
| JWT nếu dùng | Trusted JWK/issuer/audience/expiry/scope |
| TLS | Simple credentials/tokens chỉ truyền trên kênh bảo mật |
| Observability | Phân loại transport/authN/authZ, không log credentials |
| Cleanup | `requester.dispose()` sau mỗi test |
| CI | Không phụ thuộc thread/order/port cố định, isolate tests |

## 21. Câu hỏi tự kiểm tra

**1. Vì sao không kiểm tra RSocket anonymous bằng `WebTestClient.expectStatus().isUnauthorized()`?**  
Vì RSocket route trên TCP không có HTTP response 401 theo từng frame; kiểm tra RSocket error signals/connection failure bằng `RSocketRequester` và `StepVerifier`.

**2. Một client kết nối được dù không có auth có nghĩa mọi route đều public?**  
Không. `.setup().permitAll()` chỉ cho phép SETUP; route vẫn có thể đòi `authenticated()` hoặc role.

**3. Làm sao chứng minh lỗi “thiếu quyền” thay vì “thiếu xác thực”?**  
Dùng reader credentials hợp lệ, cho họ gọi private route thành công rồi assert admin route bị deny; admin có role gọi chính route đó thành công.

**4. `hasRole("ADMIN")` cần authority nào?**  
`ROLE_ADMIN` theo prefix mặc định của Spring Security.

**5. Tại sao cần `SimpleAuthenticationEncoder`?**  
Để serialize `UsernamePasswordMetadata` thành RSocket Simple Authentication metadata đúng MIME; encoder không phải mã hóa bảo mật.

**6. Setup credentials có luôn được làm mới trong request-stream đã mở không?**  
Không mặc nhiên. Snapshot authentication/authorization có thể sống cùng connection/stream; cần reauth/revoke policy riêng nếu yêu cầu.

**7. `anyRequest()` và `anyExchange()` có giống nhau không?**  
Không. Một cái bao request có metadata/route, cái kia bao các exchange chưa match, gồm payloads tiếp theo không có metadata trong một số mô hình.

**8. Tại sao `expectError()` cần positive control?**  
Vì codec lỗi, route không tồn tại hay transport lỗi cũng có thể kết thúc bằng `onError` mà không liên quan security.

**9. Khi thử request-stream vô hạn, dừng test bằng gì?**  
Nhận một số phần tử rồi `.thenCancel()` và dùng `.verify(Duration...)`.

**10. Một anonymous FNF request complete trên client chứng minh handler được gọi không?**  
Không. FNF không có response payload để xác nhận xử lý; kiểm tra server-side side effect/audit.

**11. Khi dùng JWT với RSocket, có thể chỉ đọc `scope` trong payload chưa verify không?**  
Không. Resource side phải xác minh signature, issuer, audience, expiry và mapping authorities trước khi authorize.

**12. Vì sao cần TLS với Simple Authentication?**  
Vì username/password được serialize trong metadata chứ không được bảo mật bằng encoding; transport cần bảo mật confidentiality và authenticity.

## Ghi nhớ

- **RSocket Security kiểm tra `SETUP` và route/request payloads**, không trả HTTP 401/403 cho mỗi message trên TCP.
- **Thiếu xác thực** khác **đã xác thực nhưng thiếu quyền**; cần test cả anonymous, invalid credentials, reader, admin.
- Dùng `RSocketRequester` + `StepVerifier`, kiểm tra `onError` và positive controls cùng route, không dựa vào message text duy nhất.
- `RSocketSecurity.authorizePayload(...)` xét rules theo thứ tự; `hasRole("ADMIN")` cần `ROLE_ADMIN`.
- `SimpleAuthenticationEncoder` + `UsernamePasswordMetadata` + `MESSAGE_RSOCKET_AUTHENTICATION` là bộ ba quan trọng khi gửi Simple metadata.
- **Request-stream cần bounded tests** với cancellation, và **long-lived sessions** cần thiết kế revocation/reauth riêng.
- **Không để credentials lộ qua transport/logs**; Simple Auth metadata không thay TLS.
- Với JWT, test cryptographic validation riêng; `SCOPE_` authority không tự tương đương `ROLE_`.

### Tài liệu tham khảo chính thức

- [Spring Security 6.5 — RSocket Security](https://docs.spring.io/spring-security/reference/6.5/reactive/integrations/rsocket.html)
- [Spring Security 6.5 — RSocketSecurity API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/annotation/rsocket/RSocketSecurity.html)
- [Spring Security 6.5 — PayloadSocketAcceptorInterceptor API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/rsocket/core/PayloadSocketAcceptorInterceptor.html)
- [Spring Security 6.5 — SimpleAuthenticationEncoder API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/rsocket/metadata/SimpleAuthenticationEncoder.html)
- [Spring Boot 3.5 — RSocket](https://docs.spring.io/spring-boot/3.5/reference/messaging/rsocket.html)
- [Spring Framework 6.2 — RSocket](https://docs.spring.io/spring-framework/reference/6.2/rsocket.html)
- [Spring Boot — LocalRSocketServerPort API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/rsocket/server/LocalRSocketServerPort.html)
- [Project Reactor — Testing Reactive Sequences](https://projectreactor.io/docs/core/release/reference/testing.html)
- [Spring Blog — Getting Started with RSocket: Spring Security](https://spring.io/blog/2020/06/17/getting-started-with-rsocket-spring-security/)
