# Danh tính, hủy đăng ký và token hết hạn trong SSE hoặc Flux dài hạn

## 1. Bài toán

Một API **Spring WebFlux** trả dữ liệu qua **Server-Sent Events (SSE)** hoặc `Flux<T>` kéo dài hàng phút/hàng giờ. Client mở kết nối bằng Bearer access token; Spring Security xác minh token và cho phép subscription. Đến phút thứ 10, token hết hạn; đến phút thứ 12, tài khoản bị khóa; phút thứ 15, browser đóng tab. Điều gì xảy ra với dữ liệu đang phát, danh tính đang được giữ trong publisher và tài nguyên upstream?

Ba câu hỏi khác nhau cần được giải quyết tách biệt:

1. **Danh tính:** user nào tạo subscription, ai được quyền nhận từng event, tenant nào được phép, `SecurityContext` tồn tại ở đâu khi một `Flux` chuyển scheduler?
2. **Hủy đăng ký / cancellation:** client `EventSource.close()`, `AbortController.abort()`, RSocket `CANCEL`, proxy disconnect hoặc subscriber gọi `cancel()` có thực sự giải phóng listener, broker consumer, connection, timer và cache không?
3. **Token hết hạn/thu hồi:** JWT hợp lệ ở lúc mở stream có tự bị Spring Security kiểm lại trong suốt thời gian stream không? Khi cần re-authentication, dừng luồng, phát tín hiệu nào và reconnect an toàn ra sao?

Mục tiêu của bài là hiểu chính xác **HTTP SSE**, **Reactor subscription** và **RSocket request-stream**, thay vì giả định chúng dùng cùng một cơ chế vòng đời. Bài cung cấp:

- Luồng từ Bearer authentication đến `ReactiveSecurityContextHolder`.
- So sánh authorization lúc bắt đầu stream với kiểm quyền định kỳ/theo mỗi event.
- Cách tự chặn event sau thời hạn `exp` và cách kiểm tra thu hồi quyền nhanh.
- Cơ chế cancellation, `doFinally(SignalType.CANCEL)`, `Flux.usingWhen`, heartbeat và quản lý backpressure.
- Ví dụ **Java 17+** chạy thuần JDK để kiểm tra lifecycle policy, và ứng dụng **Spring Boot 4.1.2 WebFlux SSE** với JWT Resource Server.
- RSocket security **SETUP vs per-request metadata**, lưu ý stream dài và multiplexed connections.
- Test 200/401/403, token expiry, cancellation, reconnect, tenant isolation và logging.

**Chốt nguyên tắc:** “Đã authenticated khi bắt đầu HTTP request” **không** tương đương “token còn active và quyền không đổi trong mọi thời điểm của luồng vô hạn”. Nếu cần đảm bảo này, bạn phải **thiết kế continuous authorization hoặc lifecycle limit**, không thể dựa riêng vào `.authenticated()`.

## 2. Phân biệt request, connection, subscription và event

| Khái niệm | Điểm bắt đầu | Điểm kết thúc | Authentication thường diễn ra khi nào? |
| --- | --- | --- | --- |
| HTTP request SSE | Client gửi `GET` với `Accept: text/event-stream` | Connection đóng hoặc response complete/error | WebFlux Security filters xác thực request **trước** controller |
| Reactor `Flux` subscription | Một subscriber thực sự subscribe | `onComplete`, `onError` hoặc `cancel()` | Theo cách ứng dụng đưa Authentication vào Reactor Context; không tự verify JWT mỗi `onNext` |
| SSE event | `event:... data:...` trên HTTP response | Một bản tin đã flush | Không tạo request authentication mới cho mỗi event |
| RSocket `SETUP` | Mở RSocket connection | Connection đóng | Có thể xác thực tại setup |
| RSocket `REQUEST_STREAM` | Một stream logic trên connection | Stream complete/error/CANCEL | Có thể xác thực tại request hoặc kế thừa setup identity, tùy cấu hình |
| RSocket `REQUEST_CHANNEL` | Bidirectional stream | Hai chiều complete/cancel theo protocol | Tùy metadata/authorization rules và từng request |

### 2.1. Vì sao phải phân biệt?

Ở SSE, **một HTTP GET** có thể có hàng nghìn lần `onNext` nhưng chỉ một lần HTTP Bearer authentication mặc định. Header `Authorization` không được gửi lại trước từng event.

Ở RSocket, một **TCP/WebSocket connection** có thể chứa nhiều logical requests, thậm chí nhiều user nếu gateway multiplex. Authentication chỉ tại `SETUP` có thể hợp lý với connection của một user, nhưng nguy hiểm nếu connection được dùng chung cho người dùng khác.

Ở Reactor, cùng một `Flux` có thể được tạo một lần và subscribe nhiều lần. Nếu lưu user vào **static field/global mutable variable**, subscription của người này có thể rò dữ liệu sang người kia. Danh tính đúng phải gắn với **subscriber/request context hoặc một subscription-local immutable snapshot**.

## 3. SSE từ HTTP Bearer tới Reactor Context

~~~text
Client                               Spring WebFlux API
   |                                        |
   | GET /api/stream                        |
   | Authorization: Bearer <access-token>    |
   |--------------------------------------->|
   |                            AuthenticationWebFilter
   |                            ReactiveJwtDecoder:
   |                              verify signature, iss, aud,
   |                              exp / nbf, allowed algorithm
   |                            JwtAuthenticationToken
   |                            SecurityWebFilterChain:
   |                              require SCOPE_stream.read
   |                            ReactiveSecurityContextHolder
   |                            controller returns Flux<SSE>
   |<---------------------------------------| event seq=0
   |<---------------------------------------| event seq=1
   |<---------------------------------------| event seq=2
   |             ...                        |
   |                                        |
   |      client closes / aborts            |
   |----------------X---------------------->|
   |                            cancel subscription upstream
   |                            release resources (doFinally)
~~~

Spring Security reactive lưu security context qua **Reactor Context** theo subscriber, không nên xem nó là một `ThreadLocal` toàn cục bất biến trong Netty event loop. `ReactiveSecurityContextHolder.getContext()` trả `Mono<SecurityContext>` khi được subscribe trong một reactive pipeline có context thích hợp.

### 3.1. Ví dụ đọc principal từ Reactor Context

~~~java
Mono<String> currentUserName =
        ReactiveSecurityContextHolder.getContext()
                .map(SecurityContext::getAuthentication)
                .map(Authentication::getName);
~~~

Đây là **snippet** bên trong Spring reactive pipeline, không phải chương trình độc lập. Nó đọc user của **subscription hiện tại**. Nếu chạy một publisher bằng `subscribe()` tự phát ngoài pipeline hoặc đưa vào scheduler/task queue mà không truyền context thích hợp, bạn có thể thấy context thiếu.

**Không dùng:**

~~~java
// ANTI-PATTERN trong reactive code:
Authentication a =
        SecurityContextHolder.getContext().getAuthentication();
~~~

`SecurityContextHolder` ThreadLocal của Servlet không phải cách chính để lấy Authentication cho WebFlux Reactor Context. Đừng giả định mọi `publishOn` làm mất Reactor Context; Reactor Context đi theo subscriber trong pipeline Reactor đúng cách. Rủi ro xuất hiện khi **tách khỏi subscription**, dùng callback ngoại lai, tự subscribe hoặc trộn thread/context-propagation khác mà không có contract.

### 3.2. @AuthenticationPrincipal là snapshot tại thời điểm handler chạy

Trong HTTP resource server JWT, một controller có thể nhận:

~~~java
@GetMapping(value = "/api/stream",
        produces = MediaType.TEXT_EVENT_STREAM_VALUE)
Flux<ServerSentEvent<String>> stream(
        @AuthenticationPrincipal Jwt jwt) {
    // jwt đã được resource server decoder xác minh cho HTTP request này.
    return /* một Flux do controller tạo */;
}
~~~

Đây là snippet để giải thích injection. `Jwt` chứa các claims/token timestamps **của lần authentication hiện tại**. Nếu user bị thu hồi role giữa stream, object `Jwt` **không tự biến đổi**. Authentication là snapshot của request, trừ khi ứng dụng chủ động tham chiếu một policy store mới.

### 3.3. Scope, tenant và ownership

Luồng có nhiều event nhạy cảm thường cần cả ba tầng:

1. HTTP route yêu cầu `SCOPE_stream.read`.
2. Verified JWT claim `tenant_id` phải khớp tenant/resource user yêu cầu.
3. Mỗi item nhận từ broker/database cần được lọc theo tenant và object-level authorization.

Một `Flux` chung phát tất cả sự kiện của nhiều tenants rồi lọc **sau khi serialize** là thiết kế nguy hiểm. Bộ lọc tenant phải nằm trước khi dữ liệu nhạy cảm đi vào channel/subscriber không được phép; tốt hơn là query/broker subscription được scoping từ nguồn.

## 4. Token có hết hạn giữa một SSE không?

**Có thể, và rất dễ bỏ sót.** Trong cấu hình JWT Resource Server thông thường:

- Khi HTTP request bắt đầu, `ReactiveJwtDecoder` xác minh chữ ký, `iss`, `exp`, `nbf` và các validator đã cấu hình.
- `SecurityWebFilterChain` kiểm rule authorization cho request.
- Controller trả `Flux<ServerSentEvent<?>>` và response bắt đầu streaming.
- Với từng `onNext` sau đó, **không có cơ chế mặc định** gọi lại JWT decoder chỉ vì đồng hồ đã đi qua `exp`.

Vì vậy một stream bắt đầu ở 09:59:59 với token hết hạn 10:00 có thể **tiếp tục gửi event sau 10:00**, nếu bạn không giới hạn stream hoặc kiểm authorization liên tục. Token expiry **không tự phát tín hiệu Reactor `cancel()`** cho subscription.

### 4.1. Ba chiến lược khả thi

| Chiến lược | Hành vi | Khi nên dùng |
| --- | --- | --- |
| **A. Chỉ xác minh khi mở stream** | Stream có thể tiếp tục qua token expiry | Stream ngắn, dữ liệu ít nhạy cảm, policy chấp nhận lease |
| **B. Cắt stream tại `exp` hoặc lease deadline** | Không phát event quá giới hạn do server chọn; client phải re-auth/reconnect | Khuyến nghị baseline cho bearer streams dài |
| **C. Kiểm cả `exp` và quyền hiện thời** | Mỗi event hoặc mỗi vài giây query permission/account/revocation, dừng khi deny | Dữ liệu nhạy cảm, khóa tài khoản/thu hồi quyền cần hiệu lực nhanh |

Không có một thời lượng áp dụng cho mọi hệ thống. Nếu SLO thu hồi quyền là 5 giây, kiểm mỗi 60 giây là chưa đáp ứng; còn kiểm database trên **mọi event** ở luồng hàng chục nghìn event/s có thể làm tăng tải đột biến. Thiết kế nên tính propagation delay, cache TTL, interval, retry budget và fail-closed behavior.

### 4.2. Token `exp` khác quyền truy cập dữ liệu hiện thời

`exp` là hạn hiệu lực cryptographic token. Nếu user bị khóa tại IdP hoặc bị gỡ quyền ở tenant, một JWT đã phát vẫn có thể pass signature/exp cho đến khi hết hạn; resource server local-only **không tự thấy** revocation. Tái kiểm `exp` mỗi event **chỉ giải quyết expiry**, không giải quyết role/account revocation. Cần policy backend riêng: membership store, token version, denylist, introspection hoặc event-driven invalidation.

### 4.3. Hạn của stream và hạn của token

Có thể đặt:

~~~text
streamDeadline = min(
    jwt.expiresAt,
    subscriptionStart + maximumStreamLease,
    policyRevocationDeadline (nếu đã biết)
)
~~~

Đây là công thức policy. Một service có thể giới hạn mọi stream tối đa 5 phút dù JWT còn 1 giờ để tránh connections vô hạn và cho phép kiểm lại credentials. Nếu token không có `exp`, quyết định phải do **server policy/validator**; đừng mặc định “không hết hạn” rồi mở stream vĩnh viễn.

## 5. Cancellation: dừng nhận sự kiện khác với logout

Client có thể dừng SSE bằng:

~~~javascript
const source = new EventSource("/api/stream");
source.addEventListener("tick", (e) => console.log(e.data));

// Khi component/page không còn cần stream:
source.close();
~~~

Ở client dùng `fetch()` streaming, có thể hủy bằng `AbortController.abort()`. Với Reactor client, gọi `Disposable.dispose()` / subscription `cancel()`. Trong RSocket `REQUEST_STREAM`, receiver phát `CANCEL` frame.

**Cancellation không phải logout và không phải token revocation.** Nó dừng **một subscription/stream**, không xóa OAuth2AuthorizedClient toàn server, không tự thu hồi JWT ở IdP và không đóng mọi stream khác của cùng user.

### 5.1. doFinally phân biệt COMPLETE / ERROR / CANCEL

~~~java
Flux<Long> ticks =
        Flux.interval(Duration.ofSeconds(1))
                .doFinally(signal -> {
                    if (signal == SignalType.CANCEL) {
                        metrics.incrementCancelled();
                    }
                });
~~~

Đây là snippet có `metrics` là dependency của app. `doFinally` được gọi khi publisher complete, error hoặc cancel; signal gồm `ON_COMPLETE`, `ON_ERROR` hoặc `CANCEL`. Khi stream bị client đóng và transport phát hiện, Spring WebFlux thường cancel publisher upstream. **Không cam kết phát hiện ngay** nếu chẳng có dữ liệu/heartbeat nào được ghi và proxy chưa báo disconnect.

### 5.2. Heartbeat giúp phát hiện connection chết

Spring Framework WebFlux khuyến nghị **gửi dữ liệu định kỳ** khi streaming, có thể là SSE comment-only heartbeat:

~~~text
: ping

event: tick
data: 42

: ping

~~~

SSE event cần dòng trống để kết thúc. Heartbeat không cần chứa user token, subject, tenant hoặc dữ liệu nhạy cảm. Nhịp heartbeat nên phù hợp reverse proxy/ingress read timeout, NAT và connection count. Đừng gửi heartbeat tần suất cao nếu có hàng trăm nghìn connections.

### 5.3. Cancellation phải giải phóng upstream resources

Nếu stream sử dụng broker subscription hoặc database tailing cursor, cần cleanup thật:

~~~java
// Pattern khái niệm. resourceFactory / consume / closeAsync
// phải được định nghĩa theo message broker đang dùng.
Flux.usingWhen(
        resourceFactory.openSubscriber(tenant),
        subscriber -> consume.events(subscriber),
        subscriber -> subscriber.closeAsync(),
        (subscriber, error) -> subscriber.closeAsync(),
        subscriber -> subscriber.closeAsync());
~~~

Đây là **snippet kiến trúc**, không phải file standalone; `resourceFactory`, `consume` và `closeAsync` thuộc adapter của ứng dụng. `Flux.usingWhen` có nhánh cleanup khi complete, error và **cancel**. Hãy lựa chọn API phù hợp nếu cleanup blocking (đưa qua bounded elastic và có timeout), không tự `block()` trên Netty event loop.

Một listener `Flux.create`/`Flux.push` gắn callback vào SDK cũng phải dùng `sink.onCancel(...)`/`onDispose(...)` để remove listener, stop consumer và giải phóng handles. `doFinally` ghi metric **không tự** close một connection nếu bạn chưa implement close.

### 5.4. Không tự subscribe trong controller

~~~java
// ANTI-PATTERN: tách upstream khỏi cancellation của HTTP response.
Flux<Event> source = broker.events();
source.subscribe(event -> sendSomewhere(event));
return Flux.never();
~~~

Nếu client đóng browser, subscription được `source.subscribe(...)` tạo riêng có thể tiếp tục chạy vì không được liên kết tới HTTP stream. Thay vào đó **return publisher đã compose**, để WebFlux quản lý subscribe/cancel; nếu có tài nguyên ngoài Reactor, đăng ký cleanup tương ứng.

## 6. Java 17 độc lập: tính policy ở các thời điểm

Trước khi có IdP hoặc Spring, chạy một chương trình Java 17 mô phỏng **verified identity** và 4 quyết định quan trọng: tenant đúng, scope đúng, token chưa expired, quyền hiện thời chưa bị revoke.

Chương trình dưới đây giả định authentication upstream **đã xác minh JWT**. Nó **không phải JWT decoder** và không có khóa ký; không được dùng raw claim/header của client làm `VerifiedIdentity`.

Tạo file `StreamAccessPolicyDemo.java`:

~~~java
import java.time.Instant;
import java.util.Set;

public final class StreamAccessPolicyDemo {

    enum Decision {
        ALLOW, UNKNOWN_TENANT, WRONG_TENANT,
        MISSING_SCOPE, TOKEN_EXPIRED, ACCESS_REVOKED
    }

    record VerifiedIdentity(String tenant,
                            String subject,
                            Set<String> authorities,
                            Instant expiresAt) {
    }

    private StreamAccessPolicyDemo() {
    }

    static Decision evaluate(
            String routeTenant, VerifiedIdentity identity,
            Instant now, boolean currentPermission) {

        if (!Set.of("tenant-a", "tenant-b").contains(routeTenant)) {
            return Decision.UNKNOWN_TENANT;
        }
        if (!routeTenant.equals(identity.tenant())) {
            return Decision.WRONG_TENANT;
        }
        if (!identity.authorities().contains("SCOPE_stream.read")) {
            return Decision.MISSING_SCOPE;
        }
        if (identity.expiresAt() == null
                || !now.isBefore(identity.expiresAt())) {
            return Decision.TOKEN_EXPIRED;
        }
        if (!currentPermission) {
            return Decision.ACCESS_REVOKED;
        }
        return Decision.ALLOW;
    }

    public static void main(String[] args) {
        Instant start = Instant.parse("2026-11-07T00:00:00Z");
        VerifiedIdentity reader = new VerifiedIdentity(
                "tenant-a", "user-42",
                Set.of("SCOPE_stream.read"), start.plusSeconds(10));

        VerifiedIdentity noScope = new VerifiedIdentity(
                reader.tenant(), reader.subject(), Set.of(),
                reader.expiresAt());

        System.out.println("at_open="
                + evaluate("tenant-a", reader, start, true));
        System.out.println("at_second_9="
                + evaluate("tenant-a", reader,
                        start.plusSeconds(9), true));
        System.out.println("at_second_10="
                + evaluate("tenant-a", reader,
                        start.plusSeconds(10), true));
        System.out.println("revoked_early="
                + evaluate("tenant-a", reader,
                        start.plusSeconds(2), false));
        System.out.println("tenant_b="
                + evaluate("tenant-b", reader, start, true));
        System.out.println("scope_missing="
                + evaluate("tenant-a", noScope, start, true));
        System.out.println("unknown_route="
                + evaluate("tenant-x", reader, start, true));
    }
}
~~~

Chạy **không cần Spring/Maven/IdP**:

~~~bash
javac StreamAccessPolicyDemo.java
java StreamAccessPolicyDemo
~~~

**Stdout xác định bởi code:**

~~~text
at_open=ALLOW
at_second_9=ALLOW
at_second_10=TOKEN_EXPIRED
revoked_early=ACCESS_REVOKED
tenant_b=WRONG_TENANT
scope_missing=MISSING_SCOPE
unknown_route=UNKNOWN_TENANT
~~~

Điểm học tập:

- Phút/thời điểm chính xác của `expiresAt` bị coi expired vì điều kiện là `now.isBefore(exp)`, **không** `now <= exp`.
- Thu hồi quyền được mô phỏng bằng biến `currentPermission=false`, không phải tự phát sinh từ `exp`.
- Kết quả UNKNOWN_TENANT/WRONG_TENANT chặn cross-tenant access; runtime thực còn phải kiểm issuer/audience, object ownership.
- `Instant` cố định giúp test deterministic, không đợi đồng hồ thực.
- Không hề có HTTP/WebSocket/RSocket trong chương trình thuần này; nó chỉ kiểm policy, không giả vờ kiểm protocol.

## 7. Ứng dụng Spring Boot 4.1.2 WebFlux SSE

Mẫu hoàn chỉnh dưới đây dùng **JWT Resource Server thật**. Không nhúng secret vào source, không tạo token giả để được “authenticated”, không tắt security. API có:

- `GET /healthz`: health công khai.
- `GET /api/stream`: đòi `SCOPE_stream.read` và JWT hợp lệ do IdP ký.
- `Flux<ServerSentEvent<String>>` gửi tick mỗi giây.
- **Tự kết thúc stream** khi đồng hồ tới token `exp` (không đợi request mới).
- `doFinally` đếm các kết thúc `CANCEL`, `ON_ERROR` và `ON_COMPLETE` bằng log tối giản không token.
- Mỗi subscriber có Flux riêng; không dùng mutable global user principal.

**Giới hạn chủ ý:** mẫu kiểm expiry, **không tự kiểm revocation/role changes ở IdP trong lúc stream đang mở**. Phần sau hướng dẫn bổ sung dynamic checks cho hệ thống yêu cầu thu hồi nhanh.

### 7.1. pom.xml

Tạo project Maven `reactive-sse-lifecycle`, group `com.example`, Java 17+, file `pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>reactive-sse-lifecycle</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security-oauth2-resource-server</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Spring Boot 4 dùng tên starter Resource Server `spring-boot-starter-security-oauth2-resource-server`. Để Spring Boot BOM quản lý phiên bản Framework, Security, Reactor; không trộn `spring-boot-starter-webmvc` hay Servlet `HttpSecurity` vào WebFlux.

### 7.2. application.properties

Tạo file `src/main/resources/application.properties`:

~~~properties
server.port=8080

spring.security.oauth2.resourceserver.jwt.issuer-uri=${DEMO_JWT_ISSUER}
spring.security.oauth2.resourceserver.jwt.audiences=${DEMO_JWT_AUDIENCE}
~~~

Khi lưu bài, ký hiệu `${...}` được thay bằng **Spring property placeholders** bắt đầu bằng `$`. Hai biến môi trường phải được IdP operator cung cấp; không có issuer/credential giả nào tự có giá trị bảo mật.

- `DEMO_JWT_ISSUER`: HTTPS issuer của access tokens.
- `DEMO_JWT_AUDIENCE`: resource identifier dành cho SSE API, ví dụ `events-api` do IdP cấp.
- Token thử nghiệm phải có scope `stream.read` để mapper mặc định tạo `SCOPE_stream.read`.
- Token phải có `exp`; mẫu chủ động từ chối trường hợp thiếu `exp`.
- Nếu ứng dụng nhiều tenants, bổ sung tenant validator và per-event ownership như phần 9, không chỉ dùng scope.

### 7.3. Java application hoàn chỉnh

Tạo file `src/main/java/com/example/stream/SseLifecycleApplication.java`:

~~~java
package com.example.stream;

import java.time.Duration;
import java.time.Instant;
import java.util.Map;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.publisher.SignalType;

@SpringBootApplication
@EnableWebFluxSecurity
public class SseLifecycleApplication {

    public static void main(String[] args) {
        SpringApplication.run(SseLifecycleApplication.class, args);
    }

    @Bean
    SecurityWebFilterChain security(ServerHttpSecurity http) {
        return http
                .authorizeExchange(ex -> ex
                        .pathMatchers("/healthz").permitAll()
                        .pathMatchers("/api/stream")
                                .hasAuthority("SCOPE_stream.read")
                        .anyExchange().denyAll())
                .httpBasic(basic -> basic.disable())
                .formLogin(form -> form.disable())
                .oauth2ResourceServer(oauth2 ->
                        oauth2.jwt(Customizer.withDefaults()))
                .build();
    }

    @RestController
    static class Endpoints {
        private static final Logger LOG =
                LoggerFactory.getLogger(Endpoints.class);

        @GetMapping("/healthz")
        Mono<Map<String, String>> healthz() {
            return Mono.just(Map.of("status", "UP"));
        }

        @GetMapping(value = "/api/stream",
                produces = MediaType.TEXT_EVENT_STREAM_VALUE)
        Flux<ServerSentEvent<String>> stream(
                @AuthenticationPrincipal Jwt jwt) {

            Instant expiresAt = jwt.getExpiresAt();
            if (expiresAt == null
                    || !Instant.now().isBefore(expiresAt)) {
                // Before streaming starts: HTTP status still mutable.
                throw new ResponseStatusException(
                        HttpStatus.UNAUTHORIZED,
                        "Token expiry is required");
            }

            // Captured only for this request; never static/shared.
            // Do not print the token or sensitive claims.
            return Flux.interval(
                            Duration.ZERO, Duration.ofSeconds(1))
                    .takeWhile(seq ->
                            Instant.now().isBefore(expiresAt))
                    .map(seq -> ServerSentEvent.<String>builder()
                            .id(Long.toString(seq))
                            .event("tick")
                            .data("counter=" + seq)
                            .build())
                    .doFinally(signal -> {
                        // Production: use bounded metrics, not raw tokens.
                        if (signal == SignalType.CANCEL) {
                            LOG.debug("sse_closed=cancel");
                        } else if (signal == SignalType.ON_COMPLETE) {
                            LOG.debug("sse_closed=complete");
                        } else if (signal == SignalType.ON_ERROR) {
                            LOG.warn("sse_closed=error");
                        }
                    });
        }
    }
}
~~~

**Vì sao mã này có ý nghĩa:**

1. `ServerHttpSecurity` yêu cầu `SCOPE_stream.read` ngay khi nhận request; JWT được Spring Security Resource Server verify trước controller.
2. `@AuthenticationPrincipal Jwt` là principal đã được xác minh cho request này; không tự parse `Authorization` trong controller.
3. `getExpiresAt()` là `Instant` của verified JWT. Thiếu/đã hết hạn trước khi tạo stream: trả authentication error trước response commit.
4. `Flux.interval(Duration.ZERO, Duration.ofSeconds(1))` gửi một tick mỗi giây. Nó dùng scheduler Reactor, không block Netty event loop.
5. `takeWhile(seq -> Instant.now().isBefore(expiresAt))` kiểm thời gian **trước khi emit mỗi tick**; khi predicate false, stream complete và subscription tới timer bị cancel. Cửa sổ cắt xấp xỉ interval tick cộng scheduling delay; không bảo đảm đóng chính xác tới nanosecond của `exp`.
6. `.id(Long.toString(seq))` tạo SSE ID minh họa, **không phải authorization token**, không dùng ID như quyền.
7. `doFinally` phân biệt lý do kết thúc. Khi completion do expiry, signal bên ngoài thường là `ON_COMPLETE`, **không phải `CANCEL`**; bên trong `takeWhile` có thể cancel upstream.
8. Khi browser đóng stream, Netty/WebFlux thường cancel publisher; không bảo đảm phát hiện tức thì nếu network/proxy không báo. Ticks định kỳ cũng là heartbeat giúp nhận biết disconnect.
9. Sample **không** phát event “token đã hết hạn” kèm secrets và không cố thay HTTP 200 bằng HTTP 401 sau khi đã gửi events (headers đã commit).
10. Đây là mỗi-request Flux riêng, không có global principal và không có `source.subscribe()` tự phát.
11. Chính sách này **không thay thế dynamic revocation** khi tài khoản bị khóa trước `exp`.

### 7.4. Chạy WebFlux với IdP thật

Sau khi IdP có trusted signing keys/JWKS và token thật:

~~~bash
export DEMO_JWT_ISSUER='https://idp.example.com/issuer'
export DEMO_JWT_AUDIENCE='events-api'

./mvnw clean package
./mvnw spring-boot:run
~~~

Các giá trị là minh họa, phải thay bằng issuer/audience thực. Với PowerShell, dùng `$env:DEMO_JWT_ISSUER="..."` và `.\mvnw.cmd spring-boot:run`. Với Windows Maven đã cài, dùng `mvn spring-boot:run` khi không có wrapper.

Test:

~~~bash
# Public health:
curl -i http://localhost:8080/healthz

# No token: expect HTTP 401.
curl -i http://localhost:8080/api/stream

# Valid JWT with scope stream.read and aud=events-api.
# -N disables curl output buffering for SSE.
curl -N -i \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Accept: text/event-stream" \
  http://localhost:8080/api/stream

# Stop the last curl client with Ctrl+C.
~~~

**Không có token thật thì không thể tự hoàn tất E2E JWT test.** Chương trình Java thuần ở phần 6 có thể chạy ngay bằng JDK 17. Sample WebFlux không tự tạo JWT/IdP, không tuyên bố đã xác minh token thật hoặc chạy Maven nếu chưa có môi trường.

### 7.5. Expected observable behavior

| Trường hợp | Kỳ vọng |
| --- | --- |
| `GET /healthz` không Bearer | HTTP 200, `status=UP` |
| `GET /api/stream` không token | HTTP 401 trước streaming |
| JWT sai chữ ký, sai issuer/audience, hết hạn lúc request | HTTP 401 trước streaming |
| JWT hợp lệ nhưng thiếu `SCOPE_stream.read` | HTTP 403 trước streaming |
| JWT hợp lệ, scope đúng | HTTP 200 `text/event-stream`, nhiều event `tick` |
| JWT đến `exp` khi stream đang chạy | Stream được **complete/close** ở tick kế tiếp; không tự sinh 401 sau khi commit |
| Client đóng/cancel trước `exp` | Publisher nhận cancel khi transport phát hiện; cleanup/metrics chạy |
| User bị revoke trước `exp` | Sample **vẫn có thể tiếp tục** cho tới `exp` vì chưa có online policy check |

## 8. RSocket dài hạn: SETUP và từng REQUEST có khác nhau

RSocket không phải SSE. Nó dùng connection dài, có framing/metadata và reactive backpressure, nhiều streams có thể chung một connection. Spring Security RSocket có entry point `PayloadSocketAcceptorInterceptor`, dùng `RSocketSecurity` và `@EnableRSocketSecurity`.

Theo tài liệu chính thức của Spring Security:

- **SETUP authentication:** phù hợp khi một connection thuộc một end user; credential có thể được gửi trong setup metadata.
- **Per-request authentication:** phù hợp khi một connection chung phục vụ nhiều users; credential được gửi theo từng request metadata.
- **Cả hai:** xác thực service/workload ở SETUP và xác thực end user ở từng request.

Nếu chỉ kiểm `SETUP` bằng JWT hết hạn sau 10 phút, không được giả định RSocket tự đóng mọi `REQUEST_STREAM` đang chạy đúng phút thứ 10. Cần policy expiry/revocation riêng và **không reuse authentication setup của user A cho request của user B**.

### 8.1. Cấu hình RSocket security có JWT

Dưới đây là **bean snippet** từ mô hình chính thức, cần một ứng dụng RSocket đã cấu hình `ReactiveJwtDecoder` và Spring RSocket dependencies:

~~~java
@Bean
PayloadSocketAcceptorInterceptor rsocketInterceptor(
        RSocketSecurity rsocket) {

    rsocket
        .authorizePayload(authorize -> authorize
            .anyRequest().authenticated()
            .anyExchange().permitAll())
        .jwt(Customizer.withDefaults());

    return rsocket.build();
}
~~~

Bật `@EnableRSocketSecurity` tại configuration. Spring Boot RSocket Security auto-configuration nối interceptor khi có dependencies thích hợp; cấu hình thủ công cần hiểu `RSocketServerCustomizer`.

**Đoạn này không thay thế HTTP `SecurityWebFilterChain`**. Nó thiết lập interceptor ở RSocket protocol layer. `RSocketSecurity.jwt()` yêu cầu `ReactiveJwtDecoder` bean để verify JWT được gửi bằng Bearer Token Authentication Metadata Extension.

### 8.2. JWT metadata ở SETUP và từng request

~~~text
Option 1: per connection
Client -> SETUP(metadata: Bearer JWT A) -> RSocket server
Client -> REQUEST_STREAM(route=alerts) -> identity A from setup
Client -> REQUEST_RESPONSE(route=profile) -> identity A from setup

Option 2: per request on shared connection
Service -> SETUP(metadata: service credential) -> RSocket server
Service -> REQUEST_STREAM(metadata: user JWT A) -> identity A
Service -> REQUEST_STREAM(metadata: user JWT B) -> identity B
~~~

Một snippet sender cho setup auth theo tài liệu Spring Security:

~~~java
MimeType authMimeType =
        MimeTypeUtils.parseMimeType(
                WellKnownMimeType.MESSAGE_RSOCKET_AUTHENTICATION
                        .getString());

BearerTokenMetadata tokenMetadata =
        new BearerTokenMetadata(userAccessToken);

Mono<RSocketRequester> requester =
        RSocketRequester.builder()
                .setupMetadata(tokenMetadata, authMimeType)
                .connectTcp(host, port);
~~~

Đây là **snippet**, không phải file độc lập; `userAccessToken`, `host`, `port` được cung cấp bởi phần client thực. Với per-request metadata, dùng `req.route(...).metadata(tokenMetadata, authMimeType).retrieveFlux(...)`. Chỉ gửi access token đến RSocket server đáng tin; TLS/route/audience phải phù hợp.

### 8.3. Token hết hạn khi REQUEST_STREAM còn chạy

Ngay cả nếu mỗi request RSocket được xác thực, một `REQUEST_STREAM` đơn lẻ có thể sống qua thời hạn token đã kiểm ở request-start. Phải chọn:

1. **Stream lease:** đóng request-stream khi token exp hoặc sau max duration.
2. **Dynamic checks:** thực thi permission/tenant check theo định kỳ hoặc từng event với async/reactive policy service.
3. **Renew and re-request:** client xin token mới, gửi credential theo request mới; không tự thay credential của một stream đang chạy theo cách không được protocol đảm bảo.
4. **Connection policy:** nếu setup credential hết hạn, xem xét đóng connection/re-setup. Với connection dùng chung, phân biệt service setup credential và user per-request credential.
5. **CANCEL cleanup:** xử lý RSocket CANCEL đúng publisher, không để broker listeners còn sống.
6. **Backpressure:** RSocket hỗ trợ `REQUEST_N`; producer không nên phát vô hạn vào queue khi client demand yếu.

Một RSocket `CANCEL` thường **chỉ hủy logical stream liên quan**, không có nghĩa đóng cả multiplexed connection và các streams khác. Không gọi logout hay revoke token cho toàn bộ user chỉ vì một request-stream bị cancel.

## 9. Continuous authorization khi tài khoản bị khóa trước exp

### 9.1. Chọn nguồn kiểm quyền

Một số lựa chọn thực tế:

| Nguồn | Thông tin có thể xác minh | Độ trễ thu hồi |
| --- | --- | --- |
| JWT snapshot | `exp`, scope/tenant claims đã ký | Đến expiry nếu không có online check |
| Account/permission DB | User active, tenant membership, document access | Độ trễ transaction/replication/cache |
| Introspection IdP | Token `active` theo RFC 7662 | Tùy propagation và cache TTL |
| Token version/denylist | Token đã revoke theo ID/version | Tùy store/event propagation |
| Authorization service | Dynamic policy theo resource và subject | Network latency/availability trade-off |
| Pub/sub revocation event | Push thông tin quyền đổi đến stream manager | Tùy delivery/retry và subscriber state |

**Không phải mọi sự kiện “user đổi role” khiến introspection `active=false`.** Nó phụ thuộc hợp đồng IdP. Nếu yêu cầu revoke trong 5 giây, đo worst-case từ lúc admin thay quyền tới lúc stream cuối cùng dừng nhận dữ liệu, không chỉ đo thời gian truy vấn database.

### 9.2. Pseudocode reactive kiểm mỗi event

~~~java
// Snippet trong service adapter; entitlementService là API riêng
// trả Mono<Boolean> từ nguồn dữ liệu đáng tin.
return sourceEvents
        .concatMap(event ->
                entitlementService.canRead(
                        verifiedIssuer,
                        verifiedSubject,
                        verifiedTenant,
                        event.resourceId())
                    .flatMap(allowed -> allowed
                            ? Mono.just(event)
                            : Mono.error(new AccessDeniedException(
                                    "Access revoked"))));
~~~

**Đây không phải file biên dịch độc lập**; `sourceEvents`, `event.resourceId()`, `entitlementService` và verified identity cần được định nghĩa theo ứng dụng.

Lưu ý:

- `concatMap` giữ thứ tự event và chỉ phát khi policy check pass; throughput thấp hơn nếu mỗi event gọi network.
- Nếu policy service mất kết nối, **không** mặc định `onErrorResume(err -> Mono.just(event))`. Chặn stream/fail closed theo policy.
- Không chỉ lọc event rồi phát các event khác nếu một user bị khóa hoàn toàn; có thể kết thúc subscription.
- Nếu cần kiểm định kỳ, khoảng check + cache TTL + propagation phải nằm trong revocation SLA. Chú ý event vẫn có thể phát giữa hai lần check.
- Nếu stream có nhiều tenants/resources, kiểm quyền từng item hoặc phân partition ở nguồn; một global `allowed=true` cho mọi item có thể dẫn tới rò dữ liệu.
- Tránh gọi policy service mỗi event khi traffic quá lớn nếu không có rate budget, batch, bounded concurrency hoặc cache ngắn được phê duyệt.

### 9.3. Lỗi sau khi HTTP headers đã gửi không thể biến thành 401

Khi SSE đã trả HTTP 200 và gửi vài event, status/headers thường đã commit. Nếu quyền bị thu hồi giữa stream, `Flux.error(new AccessDeniedException(...))` **không bảo đảm client nhận HTTP 403**. Framework có thể đóng kết nối sau khi logging error, chứ không thể sửa response status đã commit.

Hai cách thiết kế:

- **Complete/close stream** ngay khi không đủ quyền; client re-authenticated trên HTTP request mới.
- Nếu business protocol cần chỉ thị, gửi một SSE event an toàn, ví dụ `event: auth_expired`, **không chứa token/PII**, rồi đóng; client phải biết đó là terminal reason và không reconnect vô hạn bằng credential cũ.

SSE terminal event là **protocol-level thông báo**, không phải một OAuth2 token response, cũng không thay server-side stop. Nếu policy check báo deny, không phát thêm event dữ liệu sau sự kiện đó.

### 9.4. Recheck mỗi event không giải quyết mọi race

Nếu event được lấy lúc user vẫn có quyền, rồi quyền bị thu hồi **ngay trước khi write** bytes, vẫn có race. Với giao dịch yêu cầu chặn tức thời tuyệt đối, cần stronger transactional policy/queue isolation, bounded lease và chấp nhận rằng network delivery có buffering. Hãy định nghĩa độ trễ thu hồi và proof bằng E2E test, không chỉ bằng lý thuyết.

## 10. Reconnect: token mới phải được xác minh ở HTTP request mới

### 10.1. Browser EventSource có giới hạn header

Native browser `EventSource` thường dùng:

~~~javascript
const es = new EventSource("/api/stream", {
  withCredentials: true
});

es.addEventListener("tick", (message) => {
  console.log(message.data);
});

// Dọn tài nguyên khi unmount/page unload:
es.close();
~~~

**Quan trọng:** Constructor native `EventSource(url, {withCredentials})` **không có option tùy ý để đặt `Authorization: Bearer ...`**. Vì vậy:

- Với **BFF/cookie-backed session**, EventSource có thể dùng cookie theo same-origin/CORS credentials policy, gateway/BFF chịu trách nhiệm session/security và relay access token an toàn.
- Với **Bearer token trực tiếp từ browser**, cần fetch-based SSE client hỗ trợ custom headers, hoặc một cơ chế được thiết kế bảo mật khác.
- **Không đưa Bearer token vào URL query** để tránh lộ qua browser history, access logs, Referer, proxies và tracing.
- Cẩn thận với `withCredentials:true` ở cross-origin: cần CORS allowlist, không dùng wildcard + credentials; cookie SameSite/CSRF cần review.

### 10.2. fetch + AbortController với Authorization header

~~~javascript
const controller = new AbortController();

async function connectStream(accessToken) {
  const response = await fetch("/api/stream", {
    method: "GET",
    headers: {
      "Accept": "text/event-stream",
      "Authorization": "Bearer " + accessToken
    },
    signal: controller.signal
  });

  if (!response.ok) {
    // 401/403 on the new connection: refresh/login/permission UI.
    // Do not retry indefinitely using the same credential.
    throw new Error("SSE connection refused: " + response.status);
  }

  // Real SSE clients must parse event-stream frames incrementally,
  // including multiline data, id and retry fields.
  return response.body;
}

// When stream is no longer needed:
// controller.abort();
~~~

Đây là **snippet client connection/cancellation**, chưa phải SSE parser hoàn chỉnh; nó trả `ReadableStream` để thư viện/parser chuẩn xử lý. Không tự chia event bằng một `split("\n\n")` đơn giản khi data có multiline/stream chunk rời; dùng SSE parser library được kiểm thử. Token phải được lưu/refresh theo security model của client, không ghi vào local log.

### 10.3. EventSource tự reconnect có thể tạo vòng lặp

Browser native EventSource có cơ chế **reconnect** nếu connection bị mất/đóng theo điều kiện của spec và browser. Khi server đóng do token exp:

- Nếu client tự reconnect mà vẫn dùng credential cũ, request mới có thể nhận **401** liên tục.
- Nếu server đóng sau khi đã gửi event `auth_expired`, client nên `es.close()` và yêu cầu re-login/refresh, thay vì retry cùng cookie/token vô hạn.
- Đặt backoff, jitter, retry budget và giới hạn số connection đồng thời.
- Một khi credential mới được cấp, mở **request SSE mới** để Spring Security kiểm token mới.
- Sự kiện `id`/header `Last-Event-ID` phục vụ resume dữ liệu, **không phải chứng cứ xác thực** hoặc quyền.
- Replay phải filter tenant, authorization và object ownership lại; không cho user đọc lịch sử của tenant khác chỉ vì biết event ID.

### 10.4. Last-Event-ID và quyền

Ví dụ:

~~~http
GET /api/stream HTTP/1.1
Authorization: Bearer <fresh-access-token>
Last-Event-ID: 1024
Accept: text/event-stream
~~~

`Last-Event-ID` là vị trí replay nếu server hỗ trợ. Nó **do client cung cấp**, có thể bị giả mạo; server phải áp scope/tenant/ownership cho **mọi replayed event**, giới hạn history range, áp expiry/retention policy và không dùng event ID làm authorization capability. Nếu không hỗ trợ replay, đừng giả vờ xử lý ID để tránh gaps hoặc duplicate processing ở client.

## 11. Backpressure và memory isolation

### 11.1. Flux không đồng nghĩa server có bộ nhớ vô hạn

Một `Flux` gửi nhanh hơn tốc độ browser/network nhận sẽ gây áp lực:

- `Flux.interval` có thể phát lỗi overflow khi không có demand phù hợp; không mặc định giữ vô hạn.
- `Flux.create` hoặc push từ broker có thể buffer nếu strategy không giới hạn.
- Proxy/nginx có thể buffer SSE, làm client nhận chậm và khiến cancellation/expiry observability lệch.
- Publisher dùng chung nhiều subscribers có thể có backpressure policy khác với `Flux.defer`/cold publisher.

Cần xác định chính sách: **drop, latest, bounded buffer hoặc backpressure upstream**. Với event bảo mật quan trọng, không được “drop rồi coi đã nhận” nếu business yêu cầu exactly-once; có thể chuyển sang message broker + cursor/replay được bảo vệ.

### 11.2. Hạn chế `onBackpressureBuffer()` không giới hạn

~~~java
// Anti-pattern nếu nguồn đẩy vô hạn và client nhận chậm:
source.onBackpressureBuffer();
~~~

Nếu buffer không giới hạn, hàng nghìn clients chậm có thể làm heap tăng. Với luồng cập nhật giao diện thời gian thực, `onBackpressureLatest()` đôi khi hợp lý nhưng **mất event trung gian**; với giao dịch/audit, cần queue có retention/replay/deduplication thay vì bỏ dữ liệu. Quyết định phải dựa vào semantics từng loại event.

### 11.3. Không phát event của tenant A vào subscription B

Nếu dùng hot `Sinks.Many<Event>` chung:

~~~text
allTenantsSink
   -> auth for user tenant B
   -> filter after logging/serialization?
   -> browser B
~~~

Không an toàn nếu đã để raw secret/event đi qua các hệ thống quan sát/buffer không thuộc tenant B. Phân partition tại broker/topic/key, query theo verified tenant và thực hiện final authorization trước khi serialize. Một `filter(event -> tenant.equals(event.tenant()))` chỉ là một lớp phòng thủ; production cần data isolation end-to-end.

### 11.4. Fan-out và cancellation

Nếu một publisher dùng `publish().refCount()` hoặc `share()`, hủy một subscriber **không nhất thiết** hủy upstream nếu những subscriber khác vẫn còn. Điều này đúng với fan-out có chủ đích; nhưng phải đảm bảo user A unsubscribe không gây ảnh hưởng user B, đồng thời tránh giữ upstream forever khi số subscriber về 0. Test `refCount`, cleanup broker consumer và tenant partition.

## 12. Kiểm thử với Reactor StepVerifier và WebTestClient

### 12.1. Unit test policy thuần

`StreamAccessPolicyDemo` ở phần 6 đã có thời gian cố định. Mở rộng JUnit 5 với:

| Test | Input | Expected |
| --- | --- | --- |
| Token tại T0 | `exp=T0+10s`, quyền active | ALLOW |
| T+9s | Chưa hết hạn | ALLOW |
| T+10s | Đúng timestamp exp | TOKEN_EXPIRED |
| Thu hồi tại T+2s | `currentPermission=false` | ACCESS_REVOKED |
| Route tenant B, token A | Tenant mismatch | WRONG_TENANT |
| Scope thiếu | Không có `SCOPE_stream.read` | MISSING_SCOPE |
| Route không được đăng ký | tenant-x | UNKNOWN_TENANT |

Dùng `Clock.fixed(...)` hoặc truyền `Instant` để test mà không chờ thời gian thực. Không test security expiry bằng một đồng hồ hệ thống không điều khiển rồi khẳng định test luôn ổn định trên CI load cao.

### 12.2. Test cancellation trực tiếp với Flux

~~~java
// JUnit/Reactor-Test snippet; test dependency reactor-test cần có.
AtomicInteger cancelled = new AtomicInteger();

Flux<Long> source = Flux.interval(Duration.ofMillis(10))
        .doFinally(signal -> {
            if (signal == SignalType.CANCEL) {
                cancelled.incrementAndGet();
            }
        });

StepVerifier.create(source.take(2))
        .expectNextCount(2)
        .verifyComplete();

// take(2) cancels upstream after 2 elements; doFinally upstream
// can observe CANCEL. Wait for deterministic synchronization if needed.
~~~

Đây là **test method snippet**, không phải class hoàn chỉnh; cần `reactor-test` và imports. Lưu ý vị trí `doFinally`: nếu đặt **sau `take(2)`**, sẽ quan sát `ON_COMPLETE` ở outer subscriber. Nếu đặt **trước `take(2)`**, upstream có thể quan sát `CANCEL`. Đừng assert metric callback async bằng sleep ngẫu nhiên; dùng đồng bộ hóa thích hợp hoặc test hook chuyên dụng.

### 12.3. Test WebFlux authorization

Spring Security Test reactive có `mockJwt()`. Một ví dụ:

~~~java
// Snippet trong WebTestClient integration test đã có Security filters.
webTestClient.mutateWith(mockJwt()
        .jwt(jwt -> jwt
                .subject("test-user")
                .expiresAt(Instant.now().plusSeconds(30)))
        .authorities(new SimpleGrantedAuthority(
                "SCOPE_stream.read")))
        .get().uri("/api/stream")
        .exchange()
        .expectStatus().isOk();
~~~

**Cảnh báo:** `mockJwt()` thường gắn Authentication giả, **không gọi JWT signature decoder**. Test này chứng minh authorization với authorities đã được cấp, không chứng minh issuer/JWKS/audience/exp của JWT thật. Với stream vô hạn, **không dùng `expectBody()` để chờ hết luồng**; lấy response body dạng Flux, `take(n)`/`StepVerifier` rồi **cancel**.

### 12.4. E2E test cần xác minh gì?

| Scenario | Kỳ vọng |
| --- | --- |
| Không Bearer mở SSE protected | HTTP 401 trước event |
| JWT signature/audience/expiry sai lúc mở | 401 trước event |
| JWT hợp lệ nhưng thiếu scope | 403 trước event |
| JWT hợp lệ, còn hạn, đúng tenant | 200 + events đúng tenant |
| Token hết hạn trong lúc stream | Stream complete/close trong lease policy; không thêm events sau expiry window |
| Browser `EventSource.close()` | Upstream cancel khi disconnect được phát hiện; không rò listener |
| `fetch AbortController.abort()` | Client ngừng đọc, server dọn subscription |
| Policy revoke giữa stream | Service có continuous authorization dừng/fail closed trong SLA |
| Token mới sau reconnect | New HTTP request xác thực lại |
| Reconnect với token cũ hết hạn | 401; không retry storm |
| RSocket setup JWT hết hạn | Phụ thuộc policy; phải test không tiếp tục stream vô hạn ngoài lease |
| RSocket `CANCEL` một stream | Đúng stream dừng; những stream khác không bị hủy nhầm |
| Nhiều user chung RSocket connection | Per-request auth không lẫn context giữa users |
| Proxy idle timeout và buffering | Heartbeat hoạt động, event flush kịp, cancellation quan sát được |
| Subscriber chậm / no demand | Bounded memory/drop policy được kiểm thử |
| `Last-Event-ID` từ tenant khác | Không replay cross-tenant dữ liệu |
| IdP outage/permission DB timeout | Fail closed đúng policy, không tiếp tục phát dữ liệu mới |

### 12.5. VirtualTimeScheduler không làm Instant.now tự nhảy

`StepVerifier.withVirtualTime(...)` điều khiển thời gian scheduler Reactor, **không tự làm `Instant.now()` của JVM thay đổi**. Nếu code production dùng `Instant.now()` để cắt stream, một test chỉ advance virtual time có thể không thấy token hết hạn. Hãy inject `Clock` cho policy thời gian và virtual scheduler cho `Flux.interval` khi muốn test nhanh, hoặc mock riêng policy/tick source.

### 12.6. Đừng test infinite stream bằng blocking collection

~~~java
// ANTI-PATTERN trên Flux vô hạn:
List<Event> all = events.collectList().block();
~~~

Nó không hoàn thành, có thể treo test hoặc chờ vô hạn. Thay bằng `take(3)` + `StepVerifier` và cancel. Với WebTestClient SSE, response body có thể không bao giờ hoàn tất theo thiết kế; test harness phải đặt timeout và số event mong đợi.

## 13. Observability và security operations

Theo dõi các chỉ số **gợi ý** (không khẳng định Spring Boot tự sinh tên này):

| Metric | Dùng để biết |
| --- | --- |
| `sse.active_subscriptions` | Tổng stream đang mở theo bounded route/tenant tags |
| `sse.cancel_total` | Client disconnect/cancel |
| `sse.complete_total` | Lease/expirations |
| `sse.error_total` | Upstream failure, transport failure |
| `sse.duration_seconds` | Thời lượng distribution P50/P95/P99 |
| `sse.auth_cutoff_total` | Stream bị cắt vì token exp/permission revoke |
| `rsocket.request_stream_active` | Logical streams còn hoạt động |
| `rsocket.cancel_total` | Logical CANCEL nhận được |
| `stream.authz_recheck_duration` | Chi phí DB/IdP policy check |
| `stream.reconnect_attempts` | Retry storm và client reconnect churn |
| `stream.buffered_events` | Memory pressure cho subscribers chậm |

Đây là tên đề xuất. Tránh metric tags có raw token, `sub`/email, event ID unique hoặc URL bất kỳ gây PII/cardinality explosion. Log correlation ID, trusted route/tenant label, termination reason và policy decision category; **không** log `Authorization` header, ID Token, access/refresh token, raw claims hay payload chứa dữ liệu bí mật.

### 13.1. Phát hiện leaked subscriptions

Một subscription bị leak có dấu hiệu:

- Browser/tab đóng nhưng broker listeners vẫn tăng.
- `sse.active_subscriptions` không giảm sau khi client cancel.
- CPU vẫn chạy timer/task cho kết nối đã đóng.
- Heap/backpressure buffers tăng cùng lượng clients đã disconnect.
- RSocket `CANCEL` không dẫn tới cleanup của một subscription logic.
- Nhiều connections “zombie” sống quá max lease.

Cần test real network disconnect, không chỉ cancel trong unit test, vì reverse proxy/gateway/TCP half-open có thể trì hoãn phát hiện.

### 13.2. Chính sách server cap

Giới hạn:

- Max stream lifetime (ví dụ vài phút theo nghiệp vụ, không phải ngầm theo token TTL).
- Max subscriptions đồng thời per principal/tenant/instance.
- Max buffered events/bytes, heartbeat intervals và idle timeout.
- Max reconnect attempts trong một cửa sổ/thời gian; rate limits.
- Max concurrent policy checks, timeouts và circuit breaker.
- Data retention/replay range cho `Last-Event-ID`.
- Token refresh cadence, grace period có giới hạn và fail-closed cutoff.

Không chỉ tăng server/proxy timeout lên “vô hạn” để che lỗi cancellation hoặc thiếu chính sách token expiry.

## 14. Lỗi thường gặp

### 14.1. Tưởng SecurityWebFilterChain xác minh JWT trước từng SSE event

Sai. Mặc định nó chạy theo HTTP request; `Flux` được emit sau đó không tự gọi JWT decoder mỗi `onNext`. Giải pháp: stream lease, expiry cutoff hoặc continuous policy.

### 14.2. Dùng SecurityContextHolder ThreadLocal trong Flux

Không phù hợp mô hình Reactor Context, dễ thiếu/lẫn identity khi trộn callbacks. Dùng `ReactiveSecurityContextHolder` hoặc nhận `@AuthenticationPrincipal` và giữ immutable subscription-local identity.

### 14.3. Lấy tenant từ query mà không kiểm token

Một request `?tenant=tenant-b` không là bằng chứng. Filter broker/data theo verified tenant claim/membership và resource authorization.

### 14.4. Dùng `Flux.never()` nhưng tạo subscription side-effect riêng

Client đóng stream nhưng subscription bị tạo bằng `source.subscribe()` vẫn chạy. Return composed publisher, cleanup bằng `doFinally`/`usingWhen`/listener hooks.

### 14.5. Nghĩ `doFinally(CANCEL)` luôn chạy ngay khi user mất Wi-Fi

Network disconnection có thể không được phát hiện tức thì. Heartbeat/writes định kỳ và proxy timeouts giúp phát hiện. Test TCP half-open.

### 14.6. Đánh đồng `takeWhile` completion và CANCEL

Khi `takeWhile` quyết định false, outer subscriber thấy `ON_COMPLETE`; `takeWhile` hủy upstream. Vị trí đặt `doFinally` quyết định signal quan sát.

### 14.7. Gửi Access Token bằng SSE event hoặc URL query

Không. Token là credential, không phải event data, log hoặc `Last-Event-ID`. SSE ID chỉ làm cursor; không làm authorization.

### 14.8. Dùng native EventSource rồi cố set Authorization header

Constructor native chỉ cho `url` và option `withCredentials`; không cho tùy chỉnh Bearer header. Dùng secure BFF cookie flow hoặc fetch-based SSE client có header.

### 14.9. Dùng SSE event “expired” như thể HTTP 401

Khi headers đã commit, SSE terminal event là application protocol, không thể đổi status cũ. Client phải hiểu event và ngừng reconnect bằng credential cũ.

### 14.10. Client auto reconnect vô hạn với token hết hạn

Có thể tạo 401 storm. Xử lý auth_expired terminal reason, refresh/re-login và retry budget/backoff.

### 14.11. RSocket auth tại SETUP cho connection dùng chung nhiều users

Setup credential thường là identity của connection/workload, không là identity của mọi user được multiplex. Dùng per-request bearer metadata khi cần user-level auth, enforce route-level authorization.

### 14.12. Nghĩ RSocket CANCEL đóng toàn connection

CANCEL thuộc logical stream; connection multiplex có thể tiếp tục phục vụ streams khác. Cleanup đúng per-stream, không logout toàn bộ user.

### 14.13. Chỉ kiểm `exp` nhưng bỏ revocation

Hạn JWT không thay đổi khi admin khóa user. Cần DB/introspection/denylist/event-driven policy phù hợp SLA nếu muốn dừng trước expiry.

### 14.14. Recheck permission sau khi serialize dữ liệu nhạy cảm

Đã quá muộn nếu event được lưu vào buffer/log/serialization không thuộc tenant. Filter và authorize **trước khi phát** và tại nguồn khi có thể.

### 14.15. Dùng cache permission vĩnh viễn

Cache indefinite có thể khiến user bị revoke vẫn đọc dữ liệu. TTL/invalidations phải nằm trong revocation SLA và được test.

### 14.16. Bỏ qua backpressure và buffer vô hạn

Subscriber chậm có thể làm heap đầy. Dùng bounded buffers/drop-latest khi semantics cho phép, broker replay khi không được mất event.

### 14.17. Test chỉ bằng mockJwt rồi kết luận validation hoạt động

`mockJwt()` bypass signature decoder; nó chỉ test authorization. E2E cần JWT ký thật/test issuer, wrong aud, expired và JWKS rotation.

### 14.18. Coi SSE, WebSocket và RSocket là một giao thức

SSE một chiều HTTP; RSocket có request/response, request-stream, request-channel, frame metadata/CANCEL/demand. Authorization và reconnect phải được triển khai theo protocol thực.

## 15. Checklist production

1. Xác định SSE HTTP, WebSocket hay RSocket và authentication checkpoint thực sự.
2. Spring Security reactive dùng `ServerHttpSecurity` và `ReactiveSecurityContextHolder` đúng subscriber context.
3. JWT issuer/signature/exp/nbf/audience và scope được validate tại initial request.
4. Không coi token snapshot lúc mở stream là authorization vĩnh viễn.
5. Chọn explicit **stream lease/exp cutoff**, phương án continuous revocation nếu cần.
6. Token expiry cutoff được thực thi trước khi phát event mới, có cancellation cleanup.
7. Đặt max stream lifetime kể cả token vẫn còn hạn.
8. Scope/tenant/object ownership được kiểm trên event mới và trên replay.
9. Không biến query/Last-Event-ID/X-User header thành credentials.
10. EventSource native dùng cookie/BFF hoặc fetch-based client khi cần Bearer header.
11. Client renew/reconnect bằng credentials mới, backoff và chặn infinite retry.
12. Hiểu HTTP status sau response commit không thể đổi thành 401/403.
13. Dùng heartbeat/periodic writes để phát hiện disconnected clients sớm hơn.
14. Cleanup broker listeners/DB cursors/timers khi COMPLETE/ERROR/CANCEL.
15. Không tự `subscribe()` rồi bỏ dependency vào HTTP cancellation.
16. Giới hạn active subscriptions, event buffers và memory per tenant.
17. RSocket phân biệt JWT SETUP vs per-request metadata, đặc biệt connection multiplex.
18. RSocket CANCEL chỉ dọn đúng logical stream.
19. Test Reactor Context qua scheduler/async boundary, cancellation và virtual clock.
20. Test expired/revoked token trong khi stream còn mở; đo revocation lag end-to-end.
21. Không log tokens/claims nhạy cảm; có metrics active/cancel/error/reconnect.
22. Có phương án IdP/permission store outage theo fail-closed policy.
23. CSRF/CORS/SameSite đúng với cookie-backed SSE và browser BFF.
24. Đánh giá reverse proxy buffering, idle timeout, TLS termination, connection count.
25. Viết runbook khi revoke user, rotate signing keys hoặc triển khai thay đổi token TTL.

## 16. Câu hỏi tự kiểm tra

**Câu 1.** HTTP JWT được verify một lần khi mở SSE có tự verify lại mỗi `onNext` không?

**Đáp án:** Không theo mặc định. Muốn chặn sau expiry phải giới hạn stream hoặc tự kiểm thời gian/quyền trong pipeline.

**Câu 2.** Vì sao reactive `SecurityContext` không nên xem là global ThreadLocal?

**Đáp án:** Spring Security reactive dùng Reactor Context theo subscriber; global/ThreadLocal dễ thiếu hoặc lẫn identity trong async callbacks.

**Câu 3.** Token hết hạn lúc 10:00 nhưng SSE vẫn phát event lúc 10:05 có nhất thiết là bug của JWT decoder không?

**Đáp án:** Không. Decoder đã xác minh request ban đầu; continuous expiration enforcement là lifecycle policy của stream, không tự có.

**Câu 4.** Khi client gọi `EventSource.close()`, server có luôn biết ngay không?

**Đáp án:** Không chắc. Transport/proxy cần phát hiện disconnect, heartbeat/writes định kỳ giúp sớm nhận cancellation.

**Câu 5.** `doFinally` nhận tín hiệu nào khi subscriber hủy trực tiếp?

**Đáp án:** `SignalType.CANCEL`; với `takeWhile` complete do hết hạn, outer thường thấy `ON_COMPLETE`.

**Câu 6.** Có được dùng `Last-Event-ID` làm chứng minh user có quyền replay không?

**Đáp án:** Không. Đó là cursor do client cung cấp; replay phải xác thực và authorize theo tenant/object.

**Câu 7.** Native EventSource có đặt `Authorization: Bearer` qua constructor không?

**Đáp án:** Không. Dùng cookie-backed BFF hoặc fetch-based SSE client có custom header.

**Câu 8.** Tại sao `Flux.usingWhen` hữu ích?

**Đáp án:** Nó quản lý tài nguyên bất đồng bộ và có cleanup branch cho complete/error/cancel, phù hợp broker subscriptions và DB cursors.

**Câu 9.** RSocket shared connection có nên dùng JWT setup của user A cho các requests user B không?

**Đáp án:** Không. Dùng setup service identity và per-request user authentication khi cần phân quyền theo user.

**Câu 10.** Nếu JWT chưa hết hạn nhưng admin khóa user, chỉ `takeWhile(now < exp)` đã đủ chưa?

**Đáp án:** Chưa. Cần current entitlement/account/revocation check theo SLA.

**Câu 11.** Vì sao sau khi SSE đã gửi dữ liệu, server không thể đổi response thành HTTP 401?

**Đáp án:** Headers/status đã commit, chỉ có thể đóng/error stream hoặc phát protocol-level terminal event theo thiết kế.

**Câu 12.** Vì sao test `StepVerifier.withVirtualTime` có thể không thấy expiry trong code dùng `Instant.now()`?

**Đáp án:** VirtualTimeScheduler điều khiển thời gian Reactor scheduler, không thay đổi đồng hồ JVM; cần inject `Clock` cho thời gian security policy.

## 17. Tài liệu chính thức và đọc thêm

- [Spring Security — Reactive Security Method Support and Reactor Context](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html)
- [Spring Security — Reactive OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html)
- [Spring Security — RSocket Security: setup/request authentication and authorization](https://docs.spring.io/spring-security/reference/reactive/integrations/rsocket.html)
- [Spring Framework — WebFlux Reactive Core, Streaming/Heartbeat](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html)
- [Spring Framework — WebFlux annotated controller return types](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/return-types.html)
- [Spring Framework — WebFlux ResponseEntity and asynchronous response](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/responseentity.html)
- [Project Reactor — Error handling, doFinally, using/usingWhen](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html)
- [Project Reactor — Testing with StepVerifier and VirtualTimeScheduler](https://projectreactor.io/docs/core/release/reference/testing.html)
- [Project Reactor — Backpressure operators](https://projectreactor.io/docs/core/release/reference/coreFeatures/backpressure.html)
- [MDN — EventSource API](https://developer.mozilla.org/en-US/docs/Web/API/EventSource)
- [MDN — EventSource constructor options](https://developer.mozilla.org/en-US/docs/Web/API/EventSource/EventSource)
- [MDN — Server-sent events event stream format](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 7662 — OAuth2 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [RFC 8725 — JWT Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725)
