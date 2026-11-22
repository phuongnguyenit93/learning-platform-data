# Giới hạn kết nối, tài nguyên và hành vi khi phiên bị thu hồi trong RSocket Security

## 1. Mục tiêu và bối cảnh

Bài thuộc mục **RSocket và luồng dài** của module **Spring Security - reactive**. Một kết nối RSocket TCP hoặc RSocket-over-WebSocket có thể tồn tại lâu và multiplex nhiều logical requests/streams. Điều này giúp giảm chi phí mở kết nối nhưng cũng làm xuất hiện ba câu hỏi vận hành khác với HTTP request ngắn:

1. Làm thế nào giới hạn **số kết nối vật lý**, số requests/streams đang hoạt động, dữ liệu đang chờ, memory, CPU, băng thông và thời gian sống của stream?
2. Khi user/tenant/token/phiên xác thực bị **thu hồi**, một stream đã được cho phép lúc đầu sẽ ra sao? Làm thế nào chấm dứt stream và ngăn mở stream mới?
3. Làm thế nào triển khai/kiểm thử các cơ chế trên trong **Spring Security reactive** mà không nhầm RSocket với WebFlux HTTP, không block event loop, không rò rỉ credential hoặc dữ liệu tenant khác?

Sau bài, bạn có thể:

- Tách **physical connection**, **RSocket request/stream**, **authentication session**, **JWT lifetime** và **HTTP WebSession** thành các khái niệm khác nhau.
- Giải thích vì sao `RSocketSecurity` kiểm SETUP/request/route nhưng **không tự động re-authorize mọi PAYLOAD** trong một request-stream kéo dài.
- Thiết kế nhiều lớp quota: edge/transport admission, SETUP identity, per-principal/tenant in-flight streams, per-route concurrency, per-subscription TTL, payload/buffer limits.
- Dùng `Flux.using`, `Sinks.One`, `takeUntilOther` và Reactor cancellation để giải phóng tài nguyên theo **onComplete/onError/cancel**.
- Xử lý revocation ở trạng thái **deny new work + notify/cancel active subscriptions**, không coi logout HTTP là đóng mọi socket.
- Thiết kế kết nối đa node với **durable revocation source**, pub/sub thông báo và xử lý race/reconnect.
- Xây một ví dụ Java 17+ / Spring Boot 3.3.13 / Spring Security RSocket, gồm **registry quota stream**, **chủ động ngắt stream khi bị revoke**, endpoint quản trị lab và kiểm thử `RSocketRequester` + `StepVerifier`.
- Biết điều gì ví dụ thực sự giới hạn và **điều gì chưa giới hạn**, đặc biệt quota logical streams **khác** quota physical TCP connections.

> Trong bài, “phiên” có thể nghĩa là HTTP session, connection-level authentication, access token hoặc một server-side grant/entitlement. Không có khái niệm “thu hồi phiên” duy nhất áp dụng tự động cho tất cả chúng. Phải nêu rõ **đối tượng nào bị revoke, nguồn sự thật nào quyết định, ai nhận notification, và hành vi của các kết nối/streams đang sống**.

## 2. Đơn vị tài nguyên: kết nối, request, stream, message

### 2.1. Một connection có thể chứa nhiều streams

```text
RSocket TCP / WebSocket connection #17
  |
  +-- SETUP (authentication metadata: principal A)
  |
  +-- stream ID 1: REQUEST_RESPONSE route=profile.me
  |      -> 1 response
  |
  +-- stream ID 3: REQUEST_STREAM route=quotes.watch
  |      -> payload 1, 2, ..., N
  |
  +-- stream ID 5: REQUEST_CHANNEL route=chat.room
  |      <-> payloads hai chiều
  |
  +-- stream ID 7: REQUEST_STREAM route=alerts.watch
         -> payloads trong nhiều phút/giờ
```

Chỉ đếm **1 socket** ở sơ đồ trên nhưng có **4 logical interactions** và ít nhất 3 streams có khả năng giữ tài nguyên đáng kể.

RSocket có bốn interaction models:
- **Request-Response**: một request, một response.
- **Fire-and-Forget**: gửi một chiều, không chờ response payload.
- **Request-Stream**: một request, nhiều payloads nhận về; có demand và cancellation.
- **Request-Channel**: cả hai phía có thể truyền streams.

Đừng dùng `maxConnections` của HTTP client pool rồi coi đó là giới hạn requests RSocket server. RSocket server có physical listener riêng và một connection có thể multiplex hàng trăm logical streams.

### 2.2. Tài nguyên cần quản lý ở từng lớp

| Lớp | Đơn vị | Nguy cơ khi không giới hạn |
| --- | --- | --- |
| Edge/ingress/TCP | Sockets, handshakes/giây, IP, FD, TLS | SYN flood, socket exhaustion, handshake CPU |
| RSocket SETUP | Concurrent connects, metadata bytes, auth attempts | Password/JWT verification storm |
| Identity/quota | Connections per principal/tenant/service | Một client chiếm mọi connections |
| Request admission | In-flight requests/streams per principal/route | Quá tải DB/broker/event source |
| Stream lifecycle | Max duration, idle time, max items, reconnect | Subscription tồn tại vĩnh viễn |
| Payload/codecs | Frame bytes, composite metadata, decoder memory | Memory pressure, oversized payload, decompression |
| Outbound event source | Message rate, per-client demand, queues | Buffer vô hạn, slow consumers, data loss |
| Identity/session | Token expiry/revocation, tenant grant state | Stream tiếp tục sau khi thu hồi quyền |
| Cluster | Connections/streams per node, shared limits | Một limit per-node bị nhân theo số node |
| Observability | Metrics, labels, logs | Không nhìn thấy pressure hoặc lộ secrets |

**Connection limit != stream limit != message rate limit.** Hãy đặt cả ba theo topology và threat model.

### 2.3. Ngân sách minh họa

Một node thử nghiệm có thể đặt:

| Mục tiêu | Giới hạn minh họa | Nơi thực thi |
| --- | ---: | --- |
| TCP/WebSocket active connections/node | 500 | Ingress, Netty acceptor/connection admission |
| Handshakes/IP/phút | 60 | Edge/gateway, transport admission |
| Connections/principal | 3 | Connection registry sau khi SETUP AuthN |
| Active request-streams/node | 250 | Application stream registry |
| Active streams/principal | 2 | Application stream registry |
| Stream duration | 15–30 phút | Reactor `take(Duration)`/deadline |
| Items/stream | Theo API contract | `take(count)` + application budget |
| Payload bytes | Theo DTO/transport/decoder | Transport/codecs, không dựa vào một `if` ở controller |
| Unacknowledged/buffered events | Bounded hoặc reject | Event source/broker/buffer strategy |
| Authentication verification timeout | Theo IdP SLO | ReactiveAuthManager/decoder, timeout |
| Revocation propagation | Ví dụ p99 dưới 5 giây | Event bus + process local registries |

Đây là **giá trị giả định để tính toán**, không phải mặc định Spring Boot hay khuyến nghị áp dụng nguyên xi. Giá trị phù hợp phải được xác nhận bằng load tests, tài nguyên host, SLA và nguồn message.

## 3. Điều gì được Spring Security RSocket bảo vệ?

Spring Security RSocket tích hợp qua `PayloadSocketAcceptorInterceptor` và `RSocketSecurity`:

```java
@Bean
PayloadSocketAcceptorInterceptor rsocketInterceptor(
        RSocketSecurity rsocket) {
    return rsocket
            .authorizePayload(auth -> auth
                    .setup().authenticated()
                    .route("events.stream").hasRole("STREAM")
                    .anyRequest().denyAll()
                    .anyExchange().permitAll())
            .simpleAuthentication(Customizer.withDefaults())
            .build();
}
```

Đây là **mảnh cấu hình**, ví dụ đầy đủ xuất hiện ở mục 8.

- `setup().authenticated()`: ở đây bắt buộc authentication metadata khi mở RSocket connection.
- `route("events.stream").hasRole("STREAM")`: kiểm caller có ROLE_STREAM lúc bắt đầu request với route.
- `anyRequest().denyAll()`: từ chối các routes không được liệt kê.
- `anyExchange().permitAll()`: fallback cho các payload exchanges không mang routing metadata của request đầu; không có nghĩa mở permission cho mọi stream.

**Giới hạn quan trọng:** Một `request-stream` đã pass route authorization có thể tiếp tục phát payloads khi token/session đã bị revoke **nếu ứng dụng không có cơ chế hủy/recheck riêng**. `AuthorizationPayloadInterceptor` không tự tái chạy policy trên từng event business của một `Flux` chỉ vì role thay đổi ở database.

### 3.1. Authentication ở SETUP hay theo request?

**SETUP auth:** một connection thường đại diện cho một client/user; metadata được xác minh khi kết nối. Hợp cho mobile app kết nối cá nhân hay service account riêng. Nhưng nếu token `exp` ở tương lai và stream dài hơn token TTL, việc xác minh ban đầu không tự động ngắt stream tại đúng thời điểm exp.

**Per-request auth:** một connection shared phục vụ nhiều end users; mỗi request gửi metadata token riêng. Tốt hơn cho identity isolation trên shared connection, nhưng vẫn không bảo đảm từng event trong một request-stream được kiểm lại.

**Cả hai:** SETUP xác minh identity ứng dụng/gateway, mỗi request xác minh end user. Cần test các authorities khác nhau; không để caller B thừa hưởng authentication của A từ pool/builder.

### 3.2. HTTP WebSession không phải RSocket connection

`WebSession.invalidate()` của HTTP Spring Security có thể thu hồi cookie-based login state, **không tự đóng** một RSocket TCP socket đang sống hoặc hủy một `Flux` đang emit.

Nếu RSocket đi qua WebSocket, HTTP handshake chỉ diễn ra lúc upgrade. Cookie logout sau đó cũng không buộc RSocket payloads được kiểm lại, trừ khi có bridge/connection registry/revoke signaling đã được triển khai. Đừng coi `SecurityWebFilterChain` bảo vệ HTTP là bảo vệ mọi RSocket route.

### 3.3. JWT expiry không phải instant disconnect

Khi dùng `RSocketSecurity.jwt(...)`, `ReactiveJwtDecoder` kiểm JWT trong những authentication attempts được thực hiện. Một connection/authentication đã được xác minh không mặc nhiên nhận thông báo khi token:
- `exp` đã qua;
- Bị revoke trên Authorization Server;
- User bị khóa;
- Tenant bị vô hiệu hóa;
- Role/scope thay đổi.

Với JWT stateless, backend có thể không có một global “session row” để xóa. Để revoke nhanh cần denylist/jti, identity version, token TTL ngắn, introspection/authorization store, broadcast revoke hoặc thiết kế connection TTL phù hợp. **Một lần signature verification không có chức năng push revocation**.

## 4. Bốn tình huống “phiên bị thu hồi” và kết quả mong muốn

| Tình huống | Có tự chấm dứt stream RSocket đang mở? | Phương án |
| --- | --- | --- |
| User logout HTTP WebSession | **Không tự động** | Ứng dụng gửi revoke event sang RSocket connection registry |
| JWT access token hết hạn | **Không được bảo đảm** sau SETUP | Giới hạn stream/connection TTL, reauthenticate/recheck |
| Client API key bị revoke | **Không tự động** với manager đã xác minh tại SETUP | Deny future attempts; force close/cancel active streams |
| Quyền tenant/order bị thay đổi | **Không tự động** cho items đã buffered | Kiểm owner/tenant ở dữ liệu, cancel + drop queued items theo SLA |

Hành vi cần thiết kế **chủ đích**:

1. **Deny new admission:** request/stream mới của principal bị revoke bị từ chối.
2. **Terminate active streams:** phát một tín hiệu (error/complete/cancel) để dừng producer và giải phóng resources.
3. **Optionally close physical connection:** khi revocation áp dụng cho cả connection hoặc security policy yêu cầu.
4. **Reject reconnect:** tại SETUP/per-request authentication manager hoặc central policy mới nhất.
5. **Observe and audit:** ghi who/when/why theo policy (đã redact), số streams đóng, revocation latency và race behavior.
6. **Prevent stale revival:** multi-node state phải duy trì trạng thái revoked qua restart/reconnect, không chỉ lưu volatile flag trong một instance.
7. **Control buffered data:** kiểm nguy cơ data đã vào queue/in-flight khi revoke.

**Không** tạo fallback “IDP down thì dùng token expired để stream tiếp”. Nếu policy yêu cầu quyết định hiện hành, lỗi xác minh phải fail-closed hoặc tuân theo một grace period được định nghĩa/phê duyệt rõ ràng.

## 5. Connection admission thực sự ở đâu?

### 5.1. Bốn tầng defense

```text
Internet / internal clients
        |
        | IP rate limit, SYN/handshake, TLS, origin
        v
Ingress / LB / service mesh
        |
        | physical sockets/handshakes/idle connection caps
        v
Reactor Netty TCP / WebSocket transport
        |
        | max frame/metadata size, traffic budget
        v
RSocket SETUP
        |
        | authenticate principal, per-principal connection cap
        v
RSocket request / stream
        |
        | per-route/per-user active stream cap
        v
Reactive handler / DB / broker
```

Có ít nhất hai nhóm admission:

- **Trước AuthN:** chỉ có IP/connection metadata, chưa biết user đáng tin. Rate-limit theo IP/network/gateway, số socket toàn node và TLS handshake.
- **Sau AuthN:** mới áp giới hạn per-principal/tenant đáng tin, vì tên user từ một header/SETUP data chưa verify là input không tin cậy.

Không dùng `principalId` từ request body làm key global quota trước khi xác minh; attacker có thể tạo vô số key để vượt quota.

### 5.2. Giới hạn server physical connection khác client pool

Một số cấu hình Reactor Netty như `ConnectionProvider.maxConnections(...)` là **connection pool của phía client**, đặc biệt HTTP/TCP client. Không tự áp lên số **inbound RSocket connections của server** chỉ vì cùng nằm trong Reactor Netty.

Với RSocket server:
- Dùng ingress proxy/L4 LB có giới hạn connections/handshakes trước app;
- Hoặc cấu hình Netty transport/server acceptor/connection observer phù hợp đúng phiên bản;
- Hoặc `RSocketServerCustomizer` + `SocketAcceptorInterceptor` để thực thi admission lúc SETUP và theo dõi `onClose`, nếu đây là nơi có đủ metadata;
- Hạn chế file descriptors, per-IP quotas, TLS handshake CPU và connection idle/keepalive;
- Không giữ permit mãi nếu connection fail trong quá trình SETUP.

**Pseudo-code triển khai admission ở tầng connection, KHÔNG phải Java runnable:**

```text
onPhysicalAccept(connection):
    if not globalConnectionPermit.tryAcquire():
        rejectOrClose(connection)
        return
    attach exactly-once release on connection.onClose()
    start SETUP parsing with timeout and max metadata bytes

onAuthenticatedSetup(connection, verifiedIdentity):
    if not principalConnectionPermit(verifiedIdentity).tryAcquire():
        rejectSetupAndClose(connection)
        return
    attach exactly-once release for principal permit on close
    register connectionID -> identity, RSocket dispose handle
    continue RSocket routing

onConnectionClosed(connection):
    release global permit exactly once
    release principal permit if it was acquired
    unregister connectionID
```

Đây là mô hình để gắn vào `RSocketServerCustomizer`/Netty handler tương thích, **không** giả vờ rằng một property `spring.rsocket.server.max-connections` luôn tồn tại. API connection acceptor có thể thay đổi theo Spring Boot/RSocket Java/transport. Kiểm integration với transport thật, gồm failed SETUP, client disconnect, half-open sockets và restart.

### 5.3. Tránh gộp connection limit với stream limit

Giả sử mỗi socket có thể multiplex 100 streams:
- Cap 100 sockets nhưng **không** cap streams ⇒ có thể tới 10.000 streams;
- Cap 100 streams nhưng **không** cap sockets ⇒ attacker có thể mở hàng nghìn idle sockets;
- Chỉ cap messages/sec ⇒ không ngăn một stream chiếm bộ nhớ lớn hoặc một connection giữ FD vô hạn.

Vì vậy ví dụ runnable ở mục 8 cố ý chỉ giải quyết **logical stream quota + revoke signal**, còn physical socket quota đặt ở ingress/acceptor theo mục này. Trong báo cáo vận hành, không được mô tả `activeStreams` như `activeConnections`.

## 6. Resource budgets của request-stream/channel

### 6.1. Giới hạn đồng thời

Đặt:
- `maxActiveStreamsPerPrincipal` để một account không chiếm hết producer slots;
- `maxActiveStreamsGlobalPerNode` để bảo vệ process;
- `maxActiveStreamsPerTenant` khi nhiều users trong một tenant;
- `maxInFlightOperationsPerRoute` nếu route đụng DB/CPU nặng.

Quy trình phải **atomic**: hai requests đồng thời không cùng nhìn thấy “còn một slot” rồi cả hai được admit. Dùng CAS/atomic counter, semaphore có bounded permits hoặc lock theo principal; nếu đa node phải xem global quota có phải nhất quán cluster hay chỉ per-node.

### 6.2. Quota theo số message và thời gian

```java
// Mảnh code minh họa, không phải handler độc lập:
Flux<Event> limited = upstream
        .take(500)                       // max items
        .take(Duration.ofMinutes(5))     // max subscription lifetime
        .doFinally(signal -> releasePermitExactlyOnce());
```

`take(500)`/`take(Duration)` giới hạn items/thời gian, **không giới hạn kích thước mỗi item** và **không bảo vệ memory của upstream** nếu upstream đã buffer vô hạn. Đặt `maxInMemorySize` ở codecs/transport phù hợp, kiểm schema/length và giới hạn broker queues.

### 6.3. Backpressure và slow consumers

RSocket Request-Stream hỗ trợ `REQUEST_N` demand. Điều đó giúp flow control ở giao thức, nhưng producer hay bridge có thể tự tạo buffer lớn trước khi downstream gửi demand:
- `onBackpressureBuffer()` không giới hạn ⇒ dễ OutOfMemory;
- `publishOn` có prefetch/buffer, phải đo;
- Multicast `Sinks` có chính sách overflow/drop khác nhau;
- Fan-out subscription per user có thể nhân tải broker;
- Heavy blocking transform trên event loop gây latency cho mọi connections.

Cân nhắc:
- bounded queues, drop policy chỉ với data cho phép loss;
- reject slow consumers hoặc disconnect nếu backlog vượt quota;
- bounded concurrency trong `flatMap(..., concurrency)`;
- event coalescing/throttling/sampling khi nghiệp vụ cho phép;
- không dùng `onBackpressureDrop` để im lặng mất dữ liệu tài chính cần exactly-once;
- metrics buffer, requested demand, dropped events.

### 6.4. Cancellation và cleanup

Một RSocket client có thể gửi `CANCEL`; upstream Reactor thường nhận cancellation và chạy `doFinally(CANCEL)`. Dù vậy tài nguyên từ DB subscription, file handle, broker consumer hoặc registry lease phải được **đăng ký và giải phóng chính xác một lần**, kể cả lỗi parse, timeout hay disconnect. Với resources gắn vòng đời publisher, `Flux.using`/`Flux.usingWhen` là lựa chọn tốt; không tự gọi `subscribe()` trong handler rồi mất ownership của subscription.

## 7. Kiến trúc revocation có thể kiểm thử

### 7.1. Định nghĩa invariant

Ví dụ bài lab dùng identity `alice`:
- Tối đa **2 active streams/subject**.
- Tối đa **4 active streams toàn node**.
- Một subscription tối đa 20 giây, tối đa 100 items được yêu cầu.
- Admin có quyền gửi `POST /ops/revoke/alice`.
- Sau revoke, **không admit stream mới** cho alice.
- Các streams đã admit nhận **error signal** `STREAM_REVOKED` rồi cleanup permit.
- Đã revoke không tự phục hồi sau một reconnect RSocket trên cùng node trong thời gian app còn chạy.
- **RSocket TCP socket vật lý có thể vẫn mở**, vì demo chỉ hủy logical subscriptions chứ chưa giữ handle connection.
- **Credential Simple Authentication vẫn có thể pass SETUP** vì in-memory user store chưa bị disable. Request stream sẽ bị application registry từ chối. Production cần bổ sung kiểm revocation ngay ở AuthN/SETUP nếu muốn chặn kết nối.

Đây là một contract thực thi **resource entitlement revocation**, không phải bản triển khai đầy đủ của một identity provider hay JWT revocation service.

### 7.2. Vòng đời lease và race conditions

```text
Subscriber opens stream
        |
        v
Flux.using resourceSupplier:
    lock bucket(subject)
    if revoked -> fail
    if per-subject quota exceeded -> reject
    atomic global permit -> reserve
    record lease + revocation signal
        |
        v
Flux interval / upstream event source
    take(count)
    take(maxDuration)
    takeUntilOther(lease.revocationSignal)
        |
        +-- normal complete ------+
        +-- error ----------------+--> Flux.using disposer -> release once
        +-- CANCEL ----------------+
        +-- revoke error ----------+
```

Admin revoke:
- Đặt `bucket.revoked=true` **trong lock**;
- Snapshot các leases đang active;
- Phát tín hiệu revoke ra ngoài lock;
- Mỗi stream nhận error và đi qua disposer;
- Request mới khi đã revoke sẽ fail ngay.

Đặt state revoked **trước** khi phát signal giúp ngăn race: nếu một request mới tới giữa hai bước, nó đã nhìn thấy revoked và bị từ chối. `Sinks.One` nhớ terminal signal nên revocation đã phát trước khi subscriber lắng nghe vẫn được nhận.

**Không hứa zero extra in-flight event** sau đúng nanosecond revoke. Một payload có thể đã đi qua network buffer hoặc đang được encode khi admin xác nhận. Nếu cần cấm leak ngay lập tức tuyệt đối, phải kiểm entitlement ở data boundary/egress với version epoch và thiết kế thứ tự/quiescence rõ ràng; bất kỳ distributed revoke nào cũng có propagation window cần đo.

## 8. Ví dụ chạy được: Boot 3.3.13 + RSocket Security + quota/revoke

### 8.1. Project layout

```text
rsocket-resource-revoke/
  settings.gradle
  build.gradle
  src/
    main/
      resources/application.yml
      java/example/rsquota/
        RsQuotaApplication.java
        UsersConfig.java
        HttpSecurityConfig.java
        RSocketSecurityConfig.java
        ActiveStreamRegistry.java
        TickStreamService.java
        TickRoutes.java
        OpsController.java
    test/
      java/example/rsquota/
        ActiveStreamRegistryTests.java
        RSocketRevocationIntegrationTests.java
```

**Demo user:**

| User | Password lab | Role | Quyền |
| --- | --- | --- | --- |
| `alice` | `lab-only` | `STREAM` | Mở `ticks.watch` |
| `bob` | `lab-only` | `VIEW` | Có thể SETUP nhưng không được mở `ticks.watch` |
| `ops` | `lab-only` | `OPS` | HTTP admin revoke, không có quyền stream |

HTTP WebFlux listener: `127.0.0.1:8080`; RSocket TCP: `127.0.0.1:7000`. Chỉ chạy loopback, vì Simple Authentication metadata/password demo được gửi **cleartext** trên TCP.

### 8.2. settings.gradle

```groovy
rootProject.name = 'rsocket-resource-revoke'
```

### 8.3. build.gradle

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
    implementation 'org.springframework.boot:spring-boot-starter-rsocket'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.security:spring-security-rsocket'
    implementation 'org.springframework.security:spring-security-messaging'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Boot BOM quản lý tương thích Spring Framework, Security và RSocket Java. Không thêm `spring-boot-starter-web` (Servlet), không dùng `HttpSecurity` cho RSocket. Ví dụ cố định version để học/reproduce; dự án mới nên chọn Boot release còn được hỗ trợ và chạy lại integration tests khi nâng.

### 8.4. application.yml

```yaml
server:
  address: 127.0.0.1
  port: 8080

spring:
  rsocket:
    server:
      transport: tcp
      address: 127.0.0.1
      port: 7000
```

Đây là **RSocket TCP riêng** chứ không phải RSocket-over-WebSocket. Không gửi HTTP `curl` tới cổng 7000. HTTP admin endpoint chạy tại 8080, cần HTTP Basic role OPS trong lab.

### 8.5. RsQuotaApplication.java

```java
package example.rsquota;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RsQuotaApplication {
    public static void main(String[] args) {
        SpringApplication.run(RsQuotaApplication.class, args);
    }
}
```

### 8.6. UsersConfig.java

```java
package example.rsquota;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;

@Configuration
public class UsersConfig {

    @Bean
    MapReactiveUserDetailsService users() {
        UserDetails alice = User.withUsername("alice")
                .password("{noop}lab-only")
                .roles("STREAM")
                .build();

        UserDetails bob = User.withUsername("bob")
                .password("{noop}lab-only")
                .roles("VIEW")
                .build();

        UserDetails ops = User.withUsername("ops")
                .password("{noop}lab-only")
                .roles("OPS")
                .build();

        return new MapReactiveUserDetailsService(alice, bob, ops);
    }
}
```

`{noop}lab-only` **chỉ dành localhost lab**, không có password hashing. Ở production dùng IdP/password encoder/Token issuer đáng tin, HTTPS, rate limiting và secret manager. User store được dùng cho cả HTTP Basic và RSocket Simple Authentication, nhưng policies hai protocols là riêng.

### 8.7. HttpSecurityConfig.java

```java
package example.rsquota;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.context.NoOpServerSecurityContextRepository;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
@EnableWebFluxSecurity
public class HttpSecurityConfig {

    @Bean
    SecurityWebFilterChain adminHttpSecurity(ServerHttpSecurity http) {
        return http
                .securityContextRepository(
                        NoOpServerSecurityContextRepository.getInstance())
                .authorizeExchange(ex -> ex
                        .pathMatchers(
                                HttpMethod.GET, "/ops/active")
                        .hasRole("OPS")
                        .pathMatchers(
                                HttpMethod.POST, "/ops/revoke/*")
                        .hasRole("OPS")
                        .anyExchange().denyAll())
                .httpBasic(withDefaults())
                .formLogin(form -> form.disable())
                // Lab admin qua HTTP Basic, không dùng cookie.
                .csrf(csrf -> csrf.disable())
                .build();
    }
}
```

Điểm chính:
- `GET /ops/active` và `POST /ops/revoke/{subject}` chỉ cho ROLE_OPS;
- Không có session authentication được lưu cho admin; gửi Basic mỗi request;
- `csrf.disable()` **chỉ cho API header-only lab**. Nếu browser session/cookie được dùng, cần đánh giá/bật CSRF thay vì copy cấu hình;
- Không expose endpoint revoke này ra public Internet;
- Quyền HTTP không thay thế RSocket role `STREAM`.

### 8.8. RSocketSecurityConfig.java

```java
package example.rsquota;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.rsocket.EnableRSocketSecurity;
import org.springframework.security.config.annotation.rsocket.RSocketSecurity;
import org.springframework.security.rsocket.core.PayloadSocketAcceptorInterceptor;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
@EnableRSocketSecurity
public class RSocketSecurityConfig {

    @Bean
    PayloadSocketAcceptorInterceptor rsocketInterceptor(
            RSocketSecurity rsocket) {
        return rsocket
                .authorizePayload(auth -> auth
                        .setup().authenticated()
                        .route("ticks.watch").hasRole("STREAM")
                        .anyRequest().denyAll()
                        .anyExchange().permitAll())
                .simpleAuthentication(withDefaults())
                .build();
    }
}
```

Spring Boot gắn `PayloadSocketAcceptorInterceptor`/`SecuritySocketAcceptorInterceptor` vào RSocket acceptor khi auto-config phù hợp. Không tự đăng ký interceptor lần hai nếu Boot đã làm việc đó.

**Cần phân biệt:** ROLE_STREAM cho phép tạo một request tới `ticks.watch`. `ActiveStreamRegistry` dưới đây còn kiểm quota và revoked flag. Một user bị revoke ở registry có thể **vẫn qua SETUP Simple Authentication** vì user store chưa bị disable; nhưng không thể admit một subscription mới. Đây là **giới hạn có chủ ý và được nêu rõ của demo**.

### 8.9. ActiveStreamRegistry.java — atomic quota + revoke

```java
package example.rsquota;

import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.security.access.AccessDeniedException;
import org.springframework.stereotype.Component;

import reactor.core.publisher.Mono;
import reactor.core.publisher.Sinks;

@Component
public class ActiveStreamRegistry {

    public static final int PER_SUBJECT_LIMIT = 2;
    public static final int GLOBAL_LIMIT = 4;

    private final ConcurrentHashMap<String, Bucket> subjects =
            new ConcurrentHashMap<>();

    private final AtomicInteger activeGlobal = new AtomicInteger();

    private static final class Bucket {
        boolean revoked;
        final Set<Lease> active = new HashSet<>();
    }

    public final class Lease implements AutoCloseable {
        private final Bucket bucket;
        private final Sinks.One<Void> revokeSignal = Sinks.one();
        private final AtomicBoolean closed = new AtomicBoolean();

        private Lease(Bucket bucket) {
            this.bucket = bucket;
        }

        public Mono<Void> revoked() {
            return revokeSignal.asMono();
        }

        private void signalRevoke() {
            revokeSignal.tryEmitError(
                    new AccessDeniedException("STREAM_REVOKED"));
        }

        @Override
        public void close() {
            if (closed.compareAndSet(false, true)) {
                synchronized (bucket) {
                    bucket.active.remove(this);
                    activeGlobal.decrementAndGet();
                }
            }
        }
    }

    public Lease admit(String subject) {
        if (subject == null || subject.isBlank()) {
            throw new AccessDeniedException("Missing subject");
        }

        Bucket bucket = subjects.computeIfAbsent(
                subject, ignored -> new Bucket());

        synchronized (bucket) {
            if (bucket.revoked) {
                throw new AccessDeniedException(
                        "STREAM_REVOKED");
            }
            if (bucket.active.size() >= PER_SUBJECT_LIMIT) {
                throw new IllegalStateException(
                        "PER_SUBJECT_STREAM_LIMIT");
            }

            int newGlobal = activeGlobal.incrementAndGet();
            if (newGlobal > GLOBAL_LIMIT) {
                activeGlobal.decrementAndGet();
                throw new IllegalStateException(
                        "GLOBAL_STREAM_LIMIT");
            }

            Lease lease = new Lease(bucket);
            bucket.active.add(lease);
            return lease;
        }
    }

    public int activeCount() {
        return activeGlobal.get();
    }

    public boolean isRevoked(String subject) {
        Bucket bucket = subjects.get(subject);
        if (bucket == null) {
            return false;
        }
        synchronized (bucket) {
            return bucket.revoked;
        }
    }

    public void revoke(String subject) {
        if (subject == null || subject.isBlank()) {
            throw new IllegalArgumentException(
                    "Subject is required");
        }

        Bucket bucket = subjects.computeIfAbsent(
                subject, ignored -> new Bucket());

        List<Lease> snapshot;
        synchronized (bucket) {
            bucket.revoked = true;
            snapshot = List.copyOf(bucket.active);
        }

        // Phát tín hiệu NGOÀI synchronized block.
        snapshot.forEach(Lease::signalRevoke);
    }
}
```

**Tại sao cách này tránh oversubscribe?**

- `synchronized(bucket)` bảo vệ revoked flag, per-subject active set và việc reserve global count cùng một critical section theo subject.
- `activeGlobal.incrementAndGet()` là atomic giữa nhiều buckets. Nếu vượt GLOBAL_LIMIT thì giảm ngay và từ chối.
- Sau khi revoke flag được đặt trong lock, mọi `admit(subject)` sau đó bị chặn.
- `snapshot` chụp các leases đang active để không giữ lock trong lúc `Sinks` signal có thể kích hoạt callbacks.
- `Sinks.One<Void>` giữ terminal error, nên race “revoke tới trước khi stream gắn listener” vẫn không bỏ lỡ signal.
- `close()` dùng `AtomicBoolean` để giảm global count **đúng một lần** dù cancellation/error/dispose bị kích hoạt nhiều lần.
- `activeCount()` chỉ đo **active logical streams** của registry, không đo số socket RSocket.
- Bộ nhớ `subjects` không tự dọn các buckets bị revoke. Với demo có vài user là chấp nhận được; production cần TTL/eviction và durable revocation state để ngăn memory growth, đặc biệt khi subject ID có cardinality lớn.
- `revoke()` không xóa record/user/password hay đóng TCP socket. Nó chỉ từ chối **stream mới** và phát error cho leases đã admit. Không mô tả nó là IdP logout hoàn chỉnh.

**Bất biến test:** Sau khi đóng tất cả 4 leases, `activeCount() == 0`, bất kể streams complete/error/cancel. Khi revoke alice, không có `admit("alice")` mới được chấp nhận, kể cả khi đã có slot trống.

### 8.10. TickStreamService.java — giới hạn item, duration và cleanup

```java
package example.rsquota;

import java.time.Duration;

import org.springframework.stereotype.Service;

import reactor.core.publisher.Flux;

@Service
public class TickStreamService {

    private final ActiveStreamRegistry registry;

    public TickStreamService(ActiveStreamRegistry registry) {
        this.registry = registry;
    }

    public Flux<String> ticks(
            String verifiedSubject, Integer requestedCount) {

        if (requestedCount == null
                || requestedCount < 1
                || requestedCount > 100) {
            return Flux.error(new IllegalArgumentException(
                    "requestedCount must be between 1 and 100"));
        }

        return Flux.using(
                () -> registry.admit(verifiedSubject),
                lease -> Flux.interval(Duration.ofMillis(250))
                        .map(i -> "tick-" + i)
                        .take(requestedCount.longValue())
                        .take(Duration.ofSeconds(20))
                        .takeUntilOther(lease.revoked()),
                ActiveStreamRegistry.Lease::close);
    }
}
```

**Ba tính chất:**

1. `Flux.using` cấp lease **khi có subscription**, không phải lúc chỉ tạo publisher; điều này tránh chiếm slots cho một Mono/Flux chưa ai subscribe.
2. `take(100)`/`take(Duration.ofSeconds(20))` giới hạn số items và max duration của lab. Trong production giá trị phải theo SLO; item count không thay payload byte limit.
3. `takeUntilOther(lease.revoked())` dừng dòng khi registry phát error `STREAM_REVOKED`; error tới downstream, và `Flux.using` gọi disposer. Normal complete/cancel/error cũng đều release.

Một `Sinks.One` lỗi được Reactor phát tới `takeUntilOther` và gây terminal error; tùy phiên bản/stack, RSocket client nhận exception đã được wrap thành protocol application error. **Không assert một class/error string wire-level duy nhất giữa các phiên bản**. Nếu client cần mã lỗi định danh, định nghĩa application error contract ở tầng protocol/metadata tương thích, không dựa vào raw stack trace.

**Giới hạn:** `Flux.interval` là nguồn event mô phỏng, không chứa dữ liệu khách hàng. Với database/broker thật, upstream cần thật sự hỗ trợ cancel/cleanup và không còn tiếp tục phát item nhạy cảm sau khi lease bị revoke. Đừng wrap một blocking infinite loop bằng `Mono.just(...)` và nghĩ `takeUntilOther` có thể ngắt I/O không hợp tác.

### 8.11. TickRoutes.java — lấy verified subject trong RSocket reactive context

```java
package example.rsquota;

import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.stereotype.Controller;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Controller
public class TickRoutes {

    private final TickStreamService service;

    public TickRoutes(TickStreamService service) {
        this.service = service;
    }

    @MessageMapping("ticks.watch")
    public Flux<String> watch(@Payload Integer count) {
        return ReactiveSecurityContextHolder.getContext()
                .map(SecurityContext::getAuthentication)
                .switchIfEmpty(Mono.error(
                        new AccessDeniedException(
                                "Authentication required")))
                .flatMapMany(authentication -> {
                    if (authentication == null
                            || !authentication.isAuthenticated()) {
                        return Flux.error(
                                new AccessDeniedException(
                                        "Authentication required"));
                    }
                    return service.ticks(
                            authentication.getName(), count);
                });
    }
}
```

`authentication.getName()` đến từ **validated Spring Security Authentication** khi RSocket SETUP auth thành công, không lấy từ RSocket data do caller tự đưa. Trong production multi-tenant, key quota phải có issuer+subject/tenant/client identity đã kiểm chứng, tránh trùng `alice` giữa các realms.

**Reactive context:** Không dùng Servlet `SecurityContextHolder.getContext()` ThreadLocal trong WebFlux/RSocket. `ReactiveSecurityContextHolder` lấy SecurityContext theo Reactor subscriber context. Với custom reactive operators, không tự gọi `subscribe()` hoặc `block()` trong message handler; điều đó có thể làm mất context/cancellation propagation.

### 8.12. OpsController.java — trigger revoke trong lab

```java
package example.rsquota;

import java.util.Map;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class OpsController {

    private final ActiveStreamRegistry registry;

    public OpsController(ActiveStreamRegistry registry) {
        this.registry = registry;
    }

    @GetMapping("/ops/active")
    public Map<String, Integer> active() {
        return Map.of("activeStreams",
                registry.activeCount());
    }

    @PostMapping("/ops/revoke/{subject}")
    public ResponseEntity<Void> revoke(
            @PathVariable String subject) {
        registry.revoke(subject);
        return ResponseEntity.noContent().build();
    }
}
```

HTTP admin endpoint này được bảo vệ bằng role OPS. Nó trả 204 khi đã set revoked flag và phát signals **trên node đang xử lý request**, không hứa rằng mọi cluster node đã nhận revocation. Trong production phải phát event có version/sequence qua trung tâm và quan sát acknowledgment/propagation; admin call không phải bằng chứng đồng bộ tức thì toàn cluster.

**Không lộ admin endpoint cho người dùng hoặc tự tin mọi request tới /ops/** đã an toàn**: cần mTLS/gateway allowlist, RBAC, audit, rate limiting, CSRF đúng topology và confirmation workflows. Bài dùng HTTP Basic localhost và `{noop}` để dễ thực hành, không triển khai nguyên xi.

### 8.13. Khởi chạy và quan sát

Linux/macOS, với JDK 17+ và Gradle:

```bash
gradle bootRun
```

Nếu dự án có Gradle Wrapper:
```bash
./gradlew bootRun
```

Windows sử dụng `gradlew.bat bootRun`. HTTP admin listener 8080; RSocket TCP listener 7000. Dùng `RSocketRequester` trong test để gửi RSocket requests. `curl` chỉ có thể gọi **HTTP admin**:

```bash
curl -i -u ops:lab-only \
  http://127.0.0.1:8080/ops/active

curl -i -u ops:lab-only \
  -X POST \
  http://127.0.0.1:8080/ops/revoke/alice

curl -i -u ops:lab-only \
  http://127.0.0.1:8080/ops/active
```

Response GET ban đầu dự kiến:

```json
{"activeStreams":0}
```

Nếu chưa có RSocket subscription đang chạy thì activeStreams bằng 0, trước và sau revoke. **Revoke làm thay đổi quyền admit, không bắt buộc số streams ban đầu >0**. Để thấy cancellation đang chạy, cần mở `ticks.watch` bằng test/client trong lúc gọi revoke.

**Windows PowerShell:** dùng `curl.exe` nếu cần đúng syntax `curl -u`; một số shell định nghĩa `curl` là alias của lệnh khác. Credential/password lab có thể xuất hiện trong command history/process list; không dùng lệnh này với mật khẩu production.

## 9. Kiểm thử quota thuần với StepVerifier/JUnit

Tạo `src/test/java/example/rsquota/ActiveStreamRegistryTests.java`:

```java
package example.rsquota;

import org.junit.jupiter.api.Test;
import org.springframework.security.access.AccessDeniedException;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ActiveStreamRegistryTests {

    @Test
    void perSubjectQuotaAndCleanup() {
        ActiveStreamRegistry registry = new ActiveStreamRegistry();

        var first = registry.admit("alice");
        var second = registry.admit("alice");

        assertEquals(2, registry.activeCount());

        assertThrows(IllegalStateException.class,
                () -> registry.admit("alice"));

        first.close();
        first.close(); // idempotent cleanup

        assertEquals(1, registry.activeCount());

        var third = registry.admit("alice");
        assertEquals(2, registry.activeCount());

        second.close();
        third.close();

        assertEquals(0, registry.activeCount());
    }

    @Test
    void globalQuotaCountsAcrossSubjects() {
        ActiveStreamRegistry registry = new ActiveStreamRegistry();

        var a = registry.admit("alice");
        var b = registry.admit("alice");
        var c = registry.admit("bob");
        var d = registry.admit("bob");

        assertEquals(4, registry.activeCount());

        assertThrows(IllegalStateException.class,
                () -> registry.admit("carol"));

        a.close();
        var e = registry.admit("carol");

        b.close();
        c.close();
        d.close();
        e.close();

        assertEquals(0, registry.activeCount());
    }

    @Test
    void revokeBlocksNewAdmissionsAndSignalsExistingLease() {
        ActiveStreamRegistry registry = new ActiveStreamRegistry();

        var lease = registry.admit("alice");

        StepVerifier.create(lease.revoked())
                .then(() -> registry.revoke("alice"))
                .expectError(AccessDeniedException.class)
                .verify();

        assertTrue(registry.isRevoked("alice"));

        assertThrows(AccessDeniedException.class,
                () -> registry.admit("alice"));

        lease.close();
        assertEquals(0, registry.activeCount());
    }

    @Test
    void unrelatedSubjectIsNotRevoked() {
        ActiveStreamRegistry registry = new ActiveStreamRegistry();

        registry.revoke("alice");

        var bob = registry.admit("bob");
        assertEquals(1, registry.activeCount());
        bob.close();
        assertEquals(0, registry.activeCount());
    }
}
```

Các tests này kiểm:
- Giới hạn hai streams cho một subject;
- Giới hạn bốn streams toàn node;
- `close()` đúng một lần;
- Revoke phát error cho lease đang active và chặn admission mới;
- Subject khác vẫn hoạt động;
- **Không** kiểm physical TCP connections, vì registry này chỉ nhận logical stream leases.

**Đặc biệt về test concurrency:** Tests trên là deterministic functional tests. Trước production phải thêm stress test với nhiều threads/virtual clients đồng thời, randomized cancellation, reconnect, shutdown và negative permit counter; đừng chỉ tin một sequential unit test là không có race.

## 10. Integration tests: WebTestClient + RSocketRequester

Tạo `src/test/java/example/rsquota/RSocketRevocationIntegrationTests.java`:

```java
package example.rsquota;

import java.time.Duration;

import io.rsocket.metadata.WellKnownMimeType;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.rsocket.server.LocalRSocketServerPort;
import org.springframework.http.HttpHeaders;
import org.springframework.messaging.rsocket.RSocketRequester;
import org.springframework.security.rsocket.metadata.SimpleAuthenticationEncoder;
import org.springframework.security.rsocket.metadata.UsernamePasswordMetadata;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.util.MimeType;
import org.springframework.util.MimeTypeUtils;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        properties = {
                "spring.rsocket.server.port=0",
                "spring.rsocket.server.address=127.0.0.1"
        })
@AutoConfigureWebTestClient
class RSocketRevocationIntegrationTests {

    private static final MimeType AUTH_MIME =
            MimeTypeUtils.parseMimeType(
                    WellKnownMimeType.MESSAGE_RSOCKET_AUTHENTICATION
                            .getString());

    @Autowired
    WebTestClient http;

    @Autowired
    ObjectProvider<RSocketRequester.Builder> builders;

    @LocalRSocketServerPort
    int port;

    private Mono<RSocketRequester> connect(String user, String pass) {
        return builders.getObject()
                .rsocketStrategies(strategies ->
                        strategies.encoder(
                                new SimpleAuthenticationEncoder()))
                .setupMetadata(
                        new UsernamePasswordMetadata(user, pass),
                        AUTH_MIME)
                .connectTcp("127.0.0.1", port);
    }

    private Flux<String> watch(
            String user, String pass, int count) {
        return connect(user, pass)
                .flatMapMany(requester -> requester
                        .route("ticks.watch")
                        .data(count)
                        .retrieveFlux(String.class)
                        .doFinally(signal ->
                                requester.rsocket().dispose()));
    }

    @Test
    void adminRequiresAuthentication() {
        http.get().uri("/ops/active")
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void opsCanReadActiveStreamCount() {
        http.get().uri("/ops/active")
                .headers(h -> h.setBasicAuth("ops", "lab-only"))
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.activeStreams").isNumber();
    }

    @Test
    void aliceCanReceiveFiniteRequestStream() {
        StepVerifier.create(watch("alice", "lab-only", 3))
                .expectNext("tick-0", "tick-1", "tick-2")
                .expectComplete()
                .verify(Duration.ofSeconds(8));
    }

    @Test
    void bobCanAuthenticateSetupButCannotReadStream() {
        StepVerifier.create(watch("bob", "lab-only", 2))
                .expectError()
                .verify(Duration.ofSeconds(8));
    }

    @Test
    void wrongSetupPasswordIsRejected() {
        StepVerifier.create(watch("alice", "wrong-pass", 2))
                .expectError()
                .verify(Duration.ofSeconds(8));
    }

    @Test
    @DirtiesContext(methodMode = DirtiesContext.MethodMode.AFTER_METHOD)
    void revocationTerminatesActiveStreamAndDeniesNextOne() {
        StepVerifier.create(watch("alice", "lab-only", 80))
                .expectNext("tick-0")
                .then(() -> http.post()
                        .uri("/ops/revoke/alice")
                        .headers(h ->
                                h.setBasicAuth("ops", "lab-only"))
                        .exchange()
                        .expectStatus().isNoContent())
                .expectError()
                .verify(Duration.ofSeconds(8));

        // SETUP có thể vẫn xác thực Simple credentials.
        // Nhưng stream mới không được admitted bởi registry.
        StepVerifier.create(watch("alice", "lab-only", 2))
                .expectError()
                .verify(Duration.ofSeconds(8));
    }
}
```

**Giải thích test:**
- `@LocalRSocketServerPort` (Spring Boot 3.3) lấy RSocket port động thực của test server.
- `ObjectProvider<RSocketRequester.Builder>` tạo builder riêng mỗi connection, tránh giữ setup metadata của user trước.
- `WebTestClient` kiểm HTTP Basic admin policy; `RSocketRequester` mới thật sự gửi RSocket frames.
- `StepVerifier.expectNext` xác minh stream có dữ liệu, `then(...)` gọi HTTP revoke giữa dòng, `expectError` kiểm stream bị chấm dứt.
- `@DirtiesContext` sau test revoke tránh để in-memory registry revoked ảnh hưởng tests khác trong Spring test context.
- `requester.rsocket().dispose()` giải phóng client connection khi Flux kết thúc/bị hủy, **không** được dùng như bằng chứng server tự đóng mọi connection trong production.
- Integration test không assert một exact RSocket wire exception class; class/error message có thể được wrapper theo versions.
- Test không chứng minh TLS, global per-connection cap, multi-node revoke, revocation qua external IdP, login cookie logout hoặc exact time-to-revoke SLO.
- Lệnh `gradle test` chỉ chạy tests nếu dependencies/runtime đã sẵn sàng; số liệu trong README là **hành vi dự kiến**, không phải kết quả execution của một build đã chạy ở đây.

Chạy:

```bash
gradle test
```

Với wrapper:

```bash
./gradlew test
./gradlew test --tests example.rsquota.RSocketRevocationIntegrationTests
```

Kiểm đồng thời bằng load test thêm:
- Mở 3 request-streams cùng username alice: stream thứ ba phải error quota, hai streams đầu phải tiếp tục.
- Mở tổng 5 streams across users: stream thứ năm phải error.
- Revoke khi 2 streams đang active: cả hai nhận signal và permits về 0.
- Cancel client trước revoke: không được double release và counter âm.
- Fail SETUP: không được leak connection permit.
- Disconnect TCP/kill client: subscription cleanup chạy hoặc có watchdog phát hiện connection dead.
- Burst 1000 reconnects: handshakes/IP quotas của edge vẫn phải bảo vệ.
- Gửi oversized frame/metadata: transport decoder phải từ chối theo cấu hình limits.

## 11. Những thứ demo chưa giải quyết và cách mở rộng

### 11.1. Connection cap vật lý

`ActiveStreamRegistry` đếm logical stream leases. Một client có thể mở nhiều TCP connections nhưng chưa subscribe route, khiến `activeStreams=0` trong khi file descriptor/memory đã tăng.

Production cần thêm **transport admission** như mục 5, theo dõi thật `activeConnections`, SETUP attempts/second, connection duration, maximum idle/handshake time và per-IP/per-principal quotas.

### 11.2. Thu hồi Authentication ở SETUP

User `alice` vẫn tồn tại trong `MapReactiveUserDetailsService` sau `registry.revoke("alice")`, vì endpoint chỉ chặn application stream entitlements. Muốn chặn **reconnect** ngay tại SETUP:
- ReactiveAuthenticationManager/validator phải hỏi revocation store (theo key ID/subject/session version) khi authenticate.
- Hoặc khi SETUP authenticated, connection admission policy kiểm user/tenant active từ trusted store.
- Với JWT, verify exp/issuer/audience + denylist/jti/token version/central entitlement theo threat model.
- Revoke event cần làm invalidate caches của auth/authorization, không chỉ handler registry.

Không để revoked flag của một in-memory bean đóng vai **nguồn sự thật duy nhất** khi deploy nhiều nodes hoặc khi process restart.

### 11.3. Chủ động đóng physical connection

Nếu policy yêu cầu xóa **toàn bộ connection của user**, ngoài hủy logical streams cần:
- Ghi connection ID, verified principal và handle của underlying `RSocket` trong connection registry khi SETUP thành công;
- Đăng ký `onClose`/dispose callbacks để xóa registry và trả permit đúng một lần;
- Khi nhận revoke, snapshot connections của subject và gọi `dispose()`/close appropriate transport handle;
- Phát error/control message có contract rõ nếu muốn client phân biệt revoke với network outage;
- Kiểm reconnect bị chặn bởi updated AuthN policy, không lập tức mở socket mới vô hạn.

Việc gọi `RSocketRequester.rsocket().dispose()` trên **client test** không tự động thực thi server-side force disconnect registry. Đừng ghi trong thiết kế “revoke đóng TCP session” nếu chưa có connection handle server và test trên wire.

### 11.4. Đổi từ Simple Authentication sang JWT

Với RSocket JWT:
- Thêm dependency/cấu hình `ReactiveJwtDecoder`;
- Dùng `RSocketSecurity.jwt(...)`, Bearer Authentication metadata;
- Kiểm signature, issuer, audience, exp/nbf và scopes;
- Dùng identity key `issuer + subject + tenant`, không chỉ username;
- Nếu token ở SETUP, xem max connection lifetime không vượt token lifetime theo policy;
- Nếu token per-request, đánh giá token ở mỗi request; stream đã mở vẫn cần recheck/cancel riêng;
- Nếu JWT không có server-side session, “logout” không đồng nghĩa token lập tức bị revoke cho tới exp, trừ khi denylist/introspection/version check.

Đây là **biến thể kiến trúc**, không phải một đoạn YAML có thể chuyển Simple Authentication thành JWT an toàn mà không cấu hình issuer/keys/validators.

## 12. Multi-node revocation: pub/sub nhanh nhưng không đủ làm source of truth

### 12.1. Một node và ba nodes khác nhau thế nào?

```text
                  Admin: revoke alice
                          |
                          v
                  Durable store
                 revoked(alice)=true
                          |
                          v
                 Revocation event bus
                    /     |     \
                   v      v      v
               Node A   Node B  Node C
                |         |       |
             streams    streams  streams
              alice      alice    alice
                |         |       |
              cancel    cancel   cancel
```

Nếu admin request được load balancer đưa vào Node A, một `ConcurrentHashMap` trên Node A không tự thay đổi registry trên B/C. Mỗi node đang giữ active streams cần event hoặc polling để cancel.

### 12.2. Durable record + notify + periodic reconcile

Thiết kế thực tế:
1. Ghi revoked state/version tại **durable trusted store** (DB/Redis phù hợp, có TTL/policy).
2. Commit thành công rồi publish event `subject,tenant,revocationEpoch,eventId`.
3. Mỗi node subscribe event, cập nhật local revoked state, snapshot leases/connections và ngắt.
4. Các new admissions luôn kiểm durable state hoặc cache có TTL/invalidation mạnh, không chỉ phụ thuộc event nhận được.
5. Sau node restart/reconnect, nạp revoked state thay vì bắt đầu từ `false`.
6. Nếu event bus bị mất thông báo, periodic reconciliation/outbox/durable stream xử lý lại.
7. Dùng event IDs/version để tránh out-of-order revoke/restore làm mở lại quyền sai.
8. Đo delay từ commit revoke tới last active stream termination, đặt SLA thực.

**Lưu ý Redis Pub/Sub thường không bền vững như một durable message queue**; subscriber disconnect có thể bỏ lỡ event. Không dùng nó là cơ chế duy nhất ngăn reconnect; kết hợp durable revocation store hoặc Redis Streams/outbox phù hợp.

### 12.3. Quota global toàn cluster

Ví dụ registry local cap 4 streams/node. Chạy 5 nodes có thể cho tới 20 streams nếu clients phân bổ. Nếu contract muốn **4 streams toàn cluster**:
- Central atomic semaphore/counter/lease store (Redis Lua/DB) với TTL/fencing hoặc coordinator;
- Per-node local limit vẫn cần để bảo vệ process;
- Lease expiration cho node crash;
- Heartbeat/renew/cleanup đúng; không tin counter vĩnh viễn nếu node die;
- Chọn trade-off giữa strict global consistency và availability.

Đừng gọi một `AtomicInteger` trong JVM là “global quota” khi ứng dụng có nhiều nodes.

### 12.4. Race revoke và dữ liệu đang in-flight

Tình huống:
1. Node B đã encode event nhạy cảm cho Alice.
2. Node A commit revoke.
3. Event tới Node B sau 100 ms.
4. Một payload B đã gửi trước khi nhận revoke có thể tới client sau mốc revoke.

Không có phương thức đơn giản “xóa khỏi network” những bytes đã gửi. Nếu yêu cầu tuyệt đối không tiết lộ sau mốc policy:
- cần gating theo version/epoch ngay tại data send boundary;
- ngừng nguồn/quiesce subscriptions và kiểm acknowledgment;
- chấp nhận định nghĩa chính xác về revocation effective time, propagating window và in-flight items;
- dùng short-lived streams hay server-driven reconnect nếu cần bảo đảm mạnh.

**Không tuyên bố “revoke ngay lập tức 0ms” chỉ vì `Sinks.One.tryEmitError` chạy nhanh trên một JVM**.

## 13. Token/session expiry, idle timeout và reconnect

### 13.1. Các deadline khác nhau

| Deadline | Bảo vệ | Cách vận dụng |
| --- | --- | --- |
| TLS handshake deadline | CPU/socket resources | Netty/ingress timeout |
| SETUP authentication deadline | Identity store/JWT decoder | Timeout reactive manager |
| Connection idle timeout | Idle FD/memory | Keepalive + transport/ingress policy |
| Request response deadline | In-flight request | Reactor `timeout` + cancellation |
| Subscription max lifetime | Long-running streams | `take(Duration)`, forced reconnect |
| JWT exp | Token validity | Decoder at authentication + stream policy |
| Server-side session expiry | Stored login/entitlement grant | Central store TTL/revocation event |
| Revocation propagation SLA | Active connection/stream termination | Durable state + broadcast + reconciliation |

**Timeout != revocation.** Một stream hết hạn tự nhiên do `take(Duration)` có thể complete bình thường; revocation trong demo phát error `STREAM_REVOKED`; network disconnect lại là loại lỗi khác. Client cần phân loại để chọn reconnect policy.

### 13.2. Hành vi client khi stream bị revoke

Hợp lý:
- Dừng tự động retry cùng credential;
- Xóa/đổi local auth state theo product policy;
- Chỉ xin token mới/reauthentication sau khi user hoặc service được cấp lại quyền;
- Không spam token endpoint hay TCP reconnect theo vòng lặp;
- Log sanitized event category, không log raw credential;
- UI hiển thị “phiên hoặc quyền truy cập đã hết hiệu lực” theo UX mà không lộ secrets.

Không hợp lý:

```java
// SAI: retry vô hạn mọi lỗi, kể cả revoked/invalid credentials.
requester.route("ticks.watch")
        .data(100)
        .retrieveFlux(String.class)
        .retry();
```

Retry chỉ nên dành cho **network/transient failures** đã phân loại, có exponential backoff/jitter, retry cap, total deadline và token refresh behavior đúng contract. Invalid credentials/revoked/permission denied không phải transient availability lỗi.

### 13.3. Connection keepalive không thay JWT revalidation

RSocket có KEEPALIVE và request demand frames để kiểm connectivity/flow control. KEEPALIVE không có nghĩa IdP vừa xác nhận user còn quyền. Một TCP socket còn “healthy” có thể chứa identity đã stale về policy. Vì vậy heartbeat/keepalive và authentication TTL/revocation phải được quản lý độc lập.

### 13.4. HTTP logout và RSocket revoke bridge

Nếu app có WebFlux browser login và RSocket-over-WebSocket:
- HTTP logout invalidate WebSession/cookie;
- Phát một application revocation event theo verified user/session key;
- Map event tới đúng RSocket connections/subscriptions mở dưới identity đó;
- Cancel/dispose theo policy;
- Chặn reconnect/reauth dùng session cũ ở cả handshake và RSocket SETUP;
- Test browser có hai tabs, nhiều devices, nhiều nodes, token/cookie rotation.

**Không** dựa vào `SecurityWebFilterChain` của HTTP để re-auth từng RSocket payload. Hai pipelines độc lập về lifecycle sau upgrade.

## 14. Bảo vệ dữ liệu trong shared streams và request-channel

### 14.1. Đừng dùng principal từ request data

Sai:

```java
// SAI: tenantId do caller tự gửi, không đối chiếu quyền.
@MessageMapping("prices.tenant")
Flux<Price> prices(String tenantId) {
    return repository.watchTenant(tenantId);
}
```

Đoạn trên là mã chống ví dụ, không phải project runnable. Client có thể đoán tenant B rồi subscribe nhầm dữ liệu.

Đúng về nguyên tắc:

```java
// Mảnh minh họa: verifiedIdentity phải đến từ RSocket AuthN.
return currentIdentity()
        .flatMapMany(identity -> repository
                .watchTenant(identity.tenantId())
                .filter(price ->
                        price.allowedFor(identity.subject())));
```

Quota theo subject/tenant phải dùng identity **đã xác minh**. Nếu request có trường tenant, cần kiểm nó thuộc tập allowed tenants của principal và query policy.

### 14.2. Mỗi message của channel có thể chứa quyền khác nhau

RSocket request-channel có một stream of inbound/outbound payloads. Route auth ở request đầu chưa đảm bảo từng item hợp lệ:
- Giới hạn số items và kích thước mỗi payload;
- Kiểm schema và tenant/resource ID;
- Rate limit user/tenant;
- Không để frames sau bỏ qua application-level policy;
- Khi revoke, cancel entire channel hoặc drop/refuse events theo contract;
- Chạy cleanup cho database/broker producers và inbound subscribers.

Đừng dùng `anyExchange().permitAll()` trong RSocketSecurity làm lý do bỏ tất cả per-item checks. Nó giải quyết matcher cho protocol payloads không mang route metadata, không cấp quyền nghiệp vụ vĩnh viễn.

### 14.3. Slow consumer security

Một subscriber chậm có thể giữ các sự kiện nhạy cảm trong buffer rất lâu **sau khi quyền bị thu hồi**. Khi revoke:
- Cắt source và giải phóng buffer;
- Nếu buffer có dữ liệu của user/tenant, đảm bảo không tái phát cho subscriber khác;
- Không dùng global multicast Sink không isolate tenants;
- Chỉ replay event history theo entitlement và retention policy;
- Cân nhắc non-replay control signal cho revoke, durable record cho policy.

Nếu dùng `Sinks.many().multicast().directBestEffort()`, những subscriber chậm có thể bị mất events, không phù hợp cho mọi nghiệp vụ. Nếu dùng `Sinks.many().replay().all()`, bộ đệm có thể tăng vô hạn và replay thông tin nhạy cảm cho người đăng ký sau. Chọn chiến lược theo data sensitivity và correctness.

## 15. Observability và runbook vận hành

### 15.1. Metrics quan trọng

| Metric | Ý nghĩa |
| --- | --- |
| `rsocket_active_connections` | Sockets hiện hoạt theo node/transport, đo tại acceptor |
| `rsocket_setup_attempts_total{result}` | SETUP success/rejected/auth error |
| `rsocket_active_streams` | Concurrent streams thực sự đang giữ lease |
| `rsocket_stream_reject_total{reason}` | Per-user/global quota, revoked, policy |
| `rsocket_stream_duration_seconds` | p50/p95/p99 của subscriptions |
| `rsocket_stream_cancel_total` | Client/network/service cancellation |
| `rsocket_revocation_events_total` | Event revoke đã nhận/processed |
| `rsocket_revocation_to_close_seconds` | Delay revoke tới ngừng stream cuối |
| `rsocket_message_bytes` | Payload bytes/frame size distribution |
| `rsocket_buffer_pending_items` | Queue/slow subscriber pressure |
| `rsocket_reconnect_total` | Reconnect attempts, auth vs network reason |
| `jvm_threads, fd_used, heap_used` | Resource pressure toàn node |

Không đưa raw JWT, password, session cookie, email, full subject IDs có cardinality cao hoặc payload data vào metric labels. Dùng tenant/service alias có allowlist hoặc hashed/aggregated dimension được phê duyệt.

**Sự khác biệt:** `rsocket_active_streams` ở demo đo được; `rsocket_active_connections` cần measurement ở transport/acceptor, **không được dùng một biến số thay cho cả hai**.

### 15.2. Runbook: khi active streams liên tục tăng

1. Kiểm `activeConnections` và `activeStreams` tách biệt.
2. Xem top routes, tenants, subscription durations, buffer pressure.
3. Kiểm `doFinally`/`Flux.using` release khi normal/error/CANCEL.
4. Kiểm client có tự reconnect/retry vô hạn không.
5. Kiểm broker watch/subscription khi RSocket client disconnect.
6. Kiểm proxy idle timeout và keepalive mismatch.
7. Thử revoke test identity ở staging; active stream count phải giảm.
8. Kiểm counter âm hoặc leak sau node restart/abrupt disconnect.
9. Nếu connection flood, giảm ở ingress/Netty, không chỉ hạ stream quota.
10. Nếu CPU cao vì JWT verify tại mỗi request, xem cache và rate limiting nhưng không nới trust/expiry.
11. Không log payloads/headers chứa raw credentials để debug.
12. Thiết kế drain/rolling restart: stop new admission, notify clients, cancel/close streams, wait bounded drain period.

### 15.3. Runbook: user đã revoke vẫn nhận dữ liệu

1. Xác định revocation applied ở Auth Server, WebSession, database entitlement hay registry local.
2. Kiểm ID đúng: issuer+sub, tenant, session ID/jti; tránh nhầm human display name.
3. Xác nhận update durable state thành công.
4. Kiểm event bus/outbox, offset, subscriber lag/Redis PubSub drops.
5. Kiểm node/connection mà user đang thực sự gắn.
6. Kiểm stream đang phát buffered events hay mới đọc DB.
7. Kiểm handler có source cancellation và cleanup đúng.
8. Kiểm reconnect có đi qua AuthN/SETUP validator mới.
9. Kiểm user có token/credential thứ hai vẫn hợp lệ không.
10. Xác định SLA/consistency window đã được thỏa thuận, tránh tuyên bố “0 delay” không có chứng cứ.

## 16. Lỗi thường gặp

| Triệu chứng | Nguyên nhân chính | Khắc phục |
| --- | --- | --- |
| Stream quota không ngăn 10.000 TCP sockets | Logical quota != physical cap | Edge/acceptor connection admission |
| `activeStreams` âm | Double release | `AtomicBoolean`/`Flux.using` lifecycle |
| Stream không bao giờ hết | Thiếu duration/item cap | `take(Duration)` + max item count |
| Subscriber rời đi nhưng broker vẫn phát | Upstream không tôn trọng CANCEL | Dispose/cleanup source và test disconnect |
| Revoked user reconnect thành công | SETUP manager không kiểm durable revoked state | Thêm validation/rejection ở AuthN |
| Revoke node A không dừng stream node B | Registry local | Broadcast + durable shared state |
| Dùng Redis Pub/Sub duy nhất và mất revoke | Lost event khi subscriber offline | Durable store/stream/outbox + reconciliation |
| JWT exp đã qua nhưng stream vẫn sống | Không tự kiểm lại exp midstream | Max lifetime/recheck/cancel policy |
| HTTP logout xong RSocket vẫn nhận data | WebSession != RSocket connection | Explicit revoke bridge/connection registry |
| `anyExchange().permitAll()` bị hiểu là mở mọi dữ liệu | Nhầm RSocket matchers | Route auth + per-item tenant check |
| Buffer tăng vô hạn | Unbounded queue/replay/prefetch | Bounded buffers, slow consumer policy |
| Một user chiếm mọi streams | Thiếu per-subject concurrency | Atomic per-user quota |
| Per-node 4 streams nhưng 5 nodes cho 20 | Local != cluster-global | Distributed lease/quota |
| Revoke đã phát nhưng một event vẫn tới | Network/in-flight race | Xác định effective time và egress gate |
| Client retry liên tục khi revoked | Retry mọi exception | Phân loại auth vs transient network |
| Chỉ có Keepalive, nghĩ identity còn hợp lệ | Heartbeat != AuthN | Token/session expiry/revoke checks |
| Tests HTTP đều pass nhưng RSocket leak | WebTestClient không gửi TCP RSocket | RSocketRequester/StepVerifier |
| Revoke “thành công” HTTP 204 nhưng các nodes chưa nhận | Local method vs distributed commit | Acks/metrics/consistent state |
| Client cache cùng RSocketRequester với mọi users | Credential leakage across tenants | Scoped requester/per-request metadata |
| Tắt certificate verification cho demo | TLS trust error bị bỏ qua | Truststore/hostname SAN đúng |
| Revoke xong không giải phóng slot | Cleanup không chạy khi error | `Flux.using`/`doFinally` test |
| Kiểm subject từ payload | Attacker chọn identity/quota key | Lấy verified principal từ SecurityContext |

## 17. Câu hỏi tự kiểm tra

**1. RSocket physical connection có thể chứa nhiều request-stream không?**  
Có. Multiplexing cho phép nhiều streams cùng một connection; connection count không đo hết tải.

**2. Hạn chế 100 connections có bảo đảm chỉ 100 streams không?**  
Không. Một connection có thể có nhiều streams đồng thời.

**3. `SecurityWebFilterChain` HTTP có tự giới hạn RSocket TCP không?**  
Không. RSocket có acceptor/security pipeline riêng.

**4. RSocketSecurity kiểm quyền từng item của Flux tự động không?**  
Không mặc định. Route/SETUP auth là một tầng; per-item data policy và revocation cần logic riêng.

**5. SETUP auth khác per-request auth ở đâu?**  
SETUP ràng identity của connection; per-request có thể thay identity theo từng request trong shared connection.

**6. HTTP WebSession bị invalidate có tự close TCP RSocket socket không?**  
Không. Cần bridge/connection registry/notification.

**7. JWT `exp` qua lúc stream đang chạy, RSocket tự gửi error ngay không?**  
Không được bảo đảm. Cần stream deadline/revalidation/revoke policy.

**8. Điều kiện đầu tiên khi nhận revoke là gì?**  
Đặt revoked state sao cho không admit new work, sau đó signal/cancel active streams.

**9. Vì sao dùng `Sinks.One` thay vì multicast stream vô hạn cho mỗi lease?**  
Một terminal signal duy nhất lưu lại kết quả, tránh mất revoke signal nếu subscriber attach sau event.

**10. Vì sao dùng `Flux.using` cho active stream lease?**  
Để acquire khi subscribe và release khi complete/error/cancel, tránh leak hoặc double-release.

**11. `take(Duration)` có tự giới hạn buffer memory không?**  
Không. Upstream/broker/codec phải có bounded buffers/payload policies.

**12. Gửi `CANCEL` có nghĩa remove session credential khỏi IdP không?**  
Không. Nó hủy một logical subscription, không revoke identity credential.

**13. `maxConnections` trong Reactor Netty client pool có áp lên inbound RSocket server không?**  
Không mặc định. Cần kiểm đúng lớp transport/server.

**14. Một `AtomicInteger` trong JVM có global quota cho nhiều Kubernetes pods không?**  
Không. Nó chỉ có phạm vi process.

**15. Event Pub/Sub bị mất khi node offline thì sao?**  
Node có thể bỏ lỡ revoke. Cần durable state/outbox/reconciliation và kiểm ở admission.

**16. Sau revoke mà Simple Authentication SETUP vẫn pass trong demo có phải bug?**  
Không phải lỗi thực thi của code; demo chỉ revoke quyền **stream admission**. Production muốn chặn SETUP phải kiểm revoked state ở ReactiveAuthenticationManager/connection policy.

**17. Để đóng physical RSocket connection khi revoke cần gì?**  
Registry mapping verified identity → connection handle, close/dispose on revoke, cleanup onClose, chặn reconnect.

**18. RSocket client nhận lỗi gì khi bị revoke?**  
Demo phát application-level `STREAM_REVOKED` error; wire exception có thể được RSocket stack wrap. Không coi đó là HTTP 401/403.

**19. Stream quota 2/user nhưng Alice mở 2 connections với 1 stream mỗi cái?**  
Cả 2 streams chiếm đủ quota; stream thứ ba của Alice bị từ chối bất kể socket nào.

**20. Vì sao quota phải dùng verified subject chứ không dùng tenant ID trong request payload?**  
Vì request payload có thể bị attacker giả, cho phép né quota hoặc đọc data khác.

**21. Khi nào cần max connection lifetime?**  
Khi SETUP auth/token có TTL hoặc policy muốn buộc re-auth/reconnect theo chu kỳ, tránh connection tồn tại quá lâu.

**22. Keepalive có thay việc kiểm token expiry không?**  
Không. Keepalive chỉ kiểm connectivity/liveness ở transport/protocol.

**23. Vì sao revocation sau khi đã buffer event nhạy cảm khó?**  
Payload có thể đã encode/in-flight; cần định nghĩa effective time và egress gating, không thể xóa bytes đã gửi.

**24. Stream count giảm bằng 0 nhưng CPU vẫn cao có thể do đâu?**  
Idle sockets, handshake flood, decoder/broker work không được cancel, TLS/Netty pressure; cần metrics từng lớp.

**25. Nếu stream là tài liệu tài chính không được mất item, có thể dùng `onBackpressureDrop` tùy tiện không?**  
Không. Phải có durable delivery/ack/replay policy phù hợp và bounded backpressure.

**26. Tại sao không retry vô hạn sau `STREAM_REVOKED`?**  
Đây là policy denial, không phải transient outage; cần reauth/grant mới.

**27. `@DirtiesContext` trong integration test revoke giúp gì?**  
Ngăn in-memory revoked flag còn sống làm thay đổi test cases chạy sau.

**28. Đếm physical connections nên đo ở đâu?**  
Ingress/Netty acceptor/transport connection registry, không lấy `activeStreams` thay thế.

**29. Vì sao cần test cancel và error cùng với normal complete?**  
Permits phải được giải phóng trên mọi terminal signal; chỉ happy-path có thể che memory/slot leak.

**30. Nguyên tắc quan trọng nhất của revoke trên RSocket long-lived streams?**  
Deny new admissions từ nguồn tin đáng tin, gửi cancel/error tới active subscriptions, release resources, xử lý reconnect và distributed consistency, kiểm tenant/owner trước mọi dữ liệu nhạy cảm.

**Ghi nhớ:** Với RSocket, bảo mật không dừng ở AuthN tại SETUP và một rule `route(...).hasRole(...)`. Cần **quota nhiều lớp** (socket, SETUP, request-stream, payload/buffer, duration), **resource cleanup chính xác**, và **revocation lifecycle** (durable deny state → notify nodes → cancel active streams/connections → block reconnect → audit). Đặc biệt, **ngắt một Flux không phải đóng socket** và **logout HTTP không phải revoke RSocket tự động**.

## Tài liệu tham khảo

- [Spring Security — RSocket Security](https://docs.spring.io/spring-security/reference/reactive/integrations/rsocket.html): SETUP/request authentication, authorizePayload, Simple/JWT metadata.
- [Spring Security — RSocketSecurity API](https://docs.spring.io/spring-security/reference/6.3/api/java/org/springframework/security/config/annotation/rsocket/RSocketSecurity.html): RSocketSecurity DSL, payload interceptors.
- [Spring Framework — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html): request-stream/channel, message routing, SETUP, transport, backpressure.
- [Spring Boot — RSocket](https://docs.spring.io/spring-boot/reference/messaging/rsocket.html): RSocket server TCP/WebSocket, requester, auto-configuration.
- [Spring Boot 3.3 — RSocketServerCustomizer](https://docs.spring.io/spring-boot/docs/3.3.0/api/org/springframework/boot/rsocket/server/RSocketServerCustomizer.html): custom server acceptor/transport integration.
- [Spring Boot 3.3 — LocalRSocketServerPort](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/rsocket/server/LocalRSocketServerPort.html): dynamic test port.
- [Project Reactor — Flux.using / usingWhen](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html): resource lifecycle, cancellation, takeUntilOther.
- [Project Reactor — Sinks](https://projectreactor.io/docs/core/release/reference/coreFeatures/sinks.html): one-shot terminal signals, multicast/replay, backpressure behavior.
- [Project Reactor — Backpressure and Context](https://projectreactor.io/docs/core/release/reference/): demand, cancellation, Reactor Context.
- [RSocket Protocol](https://rsocket.io/about/protocol/): SETUP, REQUEST_STREAM, REQUEST_N, CANCEL, KEEPALIVE, ERROR.
- [RSocket — Authentication Metadata Extension](https://github.com/rsocket/rsocket/blob/master/Extensions/Security/Authentication.md): Simple/Bearer metadata formats.
- [OWASP — Denial of Service Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Denial_of_Service_Cheat_Sheet.html): resource quotas and overload policies.
- [OWASP — Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html): credential lifecycle, error handling and brute-force protection.
