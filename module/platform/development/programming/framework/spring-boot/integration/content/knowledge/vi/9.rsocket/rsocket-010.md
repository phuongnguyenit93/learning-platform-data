# Kiểm thử tương tác, ngắt kết nối và xử lý lỗi

## 1. Bài toán tích hợp RSocket cần kiểm thử như thế nào?

Trong hệ thống **Spring Boot Integration**, một RSocket client có thể yêu cầu thông tin tồn kho, nhận luồng cập nhật liên tục, gửi stream giao dịch hoặc phát thông điệp ghi nhật ký. Kết quả được nối sang HTTP client, cơ sở dữ liệu, cache và broker như Kafka/RabbitMQ. Nếu chỉ kiểm tra “request trả về một DTO đúng” thì chưa đủ:

- Kết nối TCP/WebSocket có thể mất giữa lúc client đang nhận stream.
- Backpressure và thao tác hủy subscription phải đi qua ranh giới mạng.
- Responder có thể trả lỗi nghiệp vụ, lỗi codec hoặc lỗi transport; cách retry phải khác nhau.
- Timeout sau khi gửi lệnh ghi không chứng minh phía server **chưa thực hiện**.
- Với **fire-and-forget**, hoàn thành `send()` không phải là acknowledgment xử lý nghiệp vụ.
- Retry có thể tạo lại request, kéo theo duplicate trong database hoặc downstream API.

Bài học xây dựng bộ kiểm thử từ unit-level Reactor tới integration test với RSocket server thật, rồi đi sâu vào test ngắt kết nối, phục hồi và lỗi. Mục tiêu là biết **thao tác nào đã hoàn tất, thao tác nào thất bại và thao tác nào có kết quả chưa chắc chắn**, thay vì chỉ quan sát số lượng exception.

### RSocket trong bức tranh Spring Boot Integration

~~~mermaid
flowchart LR
    A[HTTP / scheduler / broker consumer] --> B[Business Service]
    B --> C[RSocketRequester]
    C <-->|TCP hoặc WebSocket| D[RSocket @MessageMapping]
    D --> E[(DB / cache)]
    D --> F[HTTP đối tác]
    D --> G[(outbox / broker)]
    C -. metrics, trace, retry .-> H[Observability]
    D -. error/close/cancel .-> H
~~~

Không có transaction tự động bao trùm RSocket, database và broker. Phải kiểm tra idempotency tại điểm ghi tác dụng phụ dù đã dùng Reactive Streams.

## 2. Bốn interaction model và kỳ vọng kiểm thử

RSocket là giao thức ứng dụng song công (bidirectional) với **Reactive Streams semantics** cho các tương tác có stream. Chọn đúng mô hình giúp viết test đúng kết quả.

| Mô hình | Requester gửi | Responder trả | API Spring thường dùng | Cần kiểm thử |
| --- | --- | --- | --- | --- |
| **Request-Response** | Một request | Tối đa một response | `.retrieveMono(Result.class)` | Giá trị/empty/error, timeout, retry an toàn |
| **Request-Stream** | Một request | Dòng nhiều response | `.retrieveFlux(Result.class)` | Thứ tự, demand, cancellation, kết thúc khi lỗi |
| **Request-Channel** | Dòng nhiều request | Dòng nhiều response | `.data(flux, Type.class).retrieveFlux(...)` | Hai chiều, backpressure, hủy khi một đầu đóng |
| **Fire-and-Forget** | Một message | Không có application response | `.send()` | Có thể gửi, nhưng không tự chứng minh server đã xử lý |

RSocket còn hỗ trợ **metadata-push** và nhiều tính năng giao thức như keepalive, leasing, resume và fragmentation. Không nên nhầm chúng với bốn mô hình xử lý message chính.

### Bảng trạng thái kết nối khác với trạng thái nghiệp vụ

~~~text
Client       TCP/RSocket             Server               DB/HTTP downstream
  | CONNECT     |                       |                         |
  |-----------> | SETUP                 |                         |
  |             |---------------------->|                         |
  | REQUEST     |                       |                         |
  |-----------> |---------------------->| call downstream         |
  |             |                       |------------------------>|
  |             |<-- MẤT KẾT NỐI ------>|       commit?           |
  | TIMEOUT     |                       |                         |
  |             |      KHÔNG BIẾT SERVER ĐÃ COMMIT HAY CHƯA         |
~~~

Một client timeout/connection error có thể ở trước khi request được gửi, trong khi server đang xử lý hoặc sau khi server đã commit nhưng trước khi response đến. Không dùng chung một nhánh xử lý “retry chắc chắn an toàn” cho tất cả.

## 3. Cấu hình dự án mẫu

Ví dụ định hướng **Spring Boot 3.5.x, Spring Framework 6.2.x, Java 17+**. Với Boot 4.x, cần đối chiếu artifact, package và API theo BOM/version hiện hành; không trộn API giữa các major version.

### 3.1. Dependencies

~~~xml
<dependencies>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-rsocket</artifactId>
  </dependency>

  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
  </dependency>

  <dependency>
    <groupId>io.projectreactor</groupId>
    <artifactId>reactor-test</artifactId>
    <scope>test</scope>
  </dependency>
</dependencies>
~~~

`reactor-test` cung cấp `StepVerifier` và `TestPublisher`. Spring Boot starter RSocket cung cấp lớp hỗ trợ server/client tương ứng khi đủ dependency; không cần thêm `spring-boot-starter-webflux` chỉ để chạy server TCP độc lập. Khi muốn RSocket-over-WebSocket tích hợp trong WebFlux server, cấu hình web server/reactor-netty phù hợp.

### 3.2. RSocket TCP server

~~~yaml
# application.yml — server riêng trên TCP port 7000
spring:
  rsocket:
    server:
      port: 7000
      transport: tcp
~~~

Server TCP độc lập không phải cổng HTTP `server.port`. Một ứng dụng vừa phục vụ REST trên 8080 vừa phục vụ RSocket TCP trên 7000 có **hai transport endpoint** với health/ingress/TLS policy cần xem riêng.

Nếu dùng RSocket-over-WebSocket cùng WebFlux web server:

~~~yaml
# Phương án thay thế, không dùng cùng cấu hình TCP phía trên
spring:
  rsocket:
    server:
      transport: websocket
      mapping-path: /rsocket
~~~

Lựa chọn WebSocket phụ thuộc server reactive và cách triển khai; test client phải dùng `builder.websocket(URI)` thay vì `tcp(host,port)`. Không đưa request HTTP JSON bình thường tới `/rsocket` và chờ nhận kết quả của RSocket.

## 4. Xây responder có thể kiểm thử

Ví dụ một service tồn kho hỗ trợ ba kiểu tương tác; fire-and-forget dùng để tiếp nhận nhật ký không quan trọng và có mã sự kiện riêng. Để code có thể tách thành các file Java thực, mỗi record/class `public` sau đây đặt trong file cùng tên.

~~~java
// InventoryQuery.java
public record InventoryQuery(String sku) {}

// Availability.java
public record Availability(String sku, int available) {}

// InventoryTick.java
public record InventoryTick(String sku, long sequence, int available) {}

// AuditEvent.java
public record AuditEvent(String eventId, String message) {}
~~~

### 4.1. Responder

~~~java
import java.time.Duration;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Controller
public class InventoryRSocketController {

    private final AuditRegistry auditRegistry;

    public InventoryRSocketController(AuditRegistry auditRegistry) {
        this.auditRegistry = auditRegistry;
    }

    @MessageMapping("inventory.check")
    public Mono<Availability> check(InventoryQuery query) {
        return Mono.defer(() -> {
            validate(query);
            return Mono.just(new Availability(query.sku(), 12));
        });
    }

    @MessageMapping("inventory.watch")
    public Flux<InventoryTick> watch(InventoryQuery query) {
        return Flux.defer(() -> {
            validate(query);
            return Flux.range(1, 1_000)
                    .map(sequence ->
                            new InventoryTick(query.sku(), sequence, 12));
        });
    }

    @MessageMapping("inventory.bulk")
    public Flux<Availability> bulk(Flux<InventoryQuery> incoming) {
        return incoming.concatMap(this::check);
    }

    @MessageMapping("inventory.slow")
    public Mono<Availability> slow(InventoryQuery query) {
        return Mono.delay(Duration.ofSeconds(2))
                .map(ignored -> new Availability(query.sku(), 12));
    }

    @MessageMapping("inventory.fail")
    public Mono<Availability> fail(InventoryQuery query) {
        return Mono.error(new IllegalStateException("Dependency unavailable"));
    }

    @MessageMapping("audit.accept")
    public Mono<Void> accept(AuditEvent event) {
        return Mono.fromRunnable(() -> auditRegistry.record(event));
    }

    private static void validate(InventoryQuery query) {
        if (query == null || query.sku() == null
                || query.sku().isBlank()) {
            throw new IllegalArgumentException("sku is required");
        }
    }
}
~~~

~~~java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import org.springframework.stereotype.Component;

@Component
public class AuditRegistry {
    private final ConcurrentMap<String, AuditEvent> events =
            new ConcurrentHashMap<>();

    public void record(AuditEvent event) {
        if (event == null || event.eventId() == null
                || event.eventId().isBlank()) {
            throw new IllegalArgumentException("eventId is required");
        }
        events.putIfAbsent(event.eventId(), event);
    }

    public boolean contains(String eventId) {
        return events.containsKey(eventId);
    }
}
~~~

`AuditRegistry` minh họa kiểm tra duplicate theo `eventId` ở **bộ nhớ một process**, không đủ tin cậy khi nhiều pod hoặc restart. Với tác vụ có giá trị nghiệp vụ, thay nó bằng unique index/inbox trong DB hoặc cơ chế idempotency bền vững và transaction phù hợp. `Flux.range` dùng để minh họa stream hữu hạn và backpressure rõ ràng; khi lấy data từ MongoDB, Redis hoặc HTTP client, upstream đó cũng cần hỗ trợ cancellation và giới hạn tài nguyên.

### 4.2. Requester được Spring Boot cấu hình

~~~java
import org.springframework.messaging.rsocket.RSocketRequester;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Service
public class InventoryRSocketClient {
    private final RSocketRequester requester;

    public InventoryRSocketClient(RSocketRequester.Builder builder) {
        // Được Boot cấu hình codecs và connector customizers.
        // Việc kết nối thực tế được khởi tạo khi có request.
        this.requester = builder.tcp("inventory.example.internal", 7000);
    }

    public Mono<Availability> check(String sku) {
        return requester.route("inventory.check")
                .data(new InventoryQuery(sku))
                .retrieveMono(Availability.class);
    }

    public Flux<InventoryTick> watch(String sku) {
        return requester.route("inventory.watch")
                .data(new InventoryQuery(sku))
                .retrieveFlux(InventoryTick.class);
    }

    public Flux<Availability> bulk(Flux<InventoryQuery> queries) {
        return requester.route("inventory.bulk")
                .data(queries, InventoryQuery.class)
                .retrieveFlux(Availability.class);
    }

    public Mono<Void> sendAudit(AuditEvent event) {
        return requester.route("audit.accept")
                .data(event)
                .send();
    }
}
~~~

**Phân biệt API theo thế hệ:** trong Spring Framework 6.x, `RSocketRequester.Builder.tcp(host, port)` trả về **`RSocketRequester`**, với kết nối dùng chung được thiết lập lazy khi thực hiện request; **không** xử lý nó như `Mono<RSocketRequester>` từ các API cũ `connectTcp(...)`. Builder do Spring Boot cung cấp thường ở prototype scope và có trạng thái, nên tránh tái sử dụng cùng builder đã chỉnh sửa cho nhiều endpoint với setup metadata khác nhau.

Không gọi `block()` bên trong Netty event-loop/WebFlux handler. Test integration dùng `StepVerifier` để subscribe, nêu rõ completion/error và kiểm soát thời gian.

## 5. Kim tự tháp kiểm thử cho RSocket

| Tầng | Đối tượng | Công cụ | Điều nó chứng minh | Điều chưa chứng minh |
| --- | --- | --- | --- | --- |
| **Unit reactive** | Mapping, validation, retry operator, cancellation | JUnit 5, StepVerifier, TestPublisher, virtual time | Semantics của `Mono/Flux` | SETUP, route metadata, wire codec, TLS, thực tế socket |
| **Spring context** | `@Controller`, `@MessageMapping`, bean, codec | `@SpringBootTest` | Bean wiring/validation/serialization trong context | Không đầy đủ nếu không mở transport thật |
| **RSocket integration** | Client kết nối TCP/WebSocket server | `@SpringBootTest`, random port, `RSocketRequester` | Routing, 4 interaction models, remote error, backpressure thực tế | Mất mạng, server restart, broker/DB bên ngoài |
| **Fault integration** | Cắt TCP, delay, packet loss, restart | Toxiproxy, container/netem, fault test network | Timeout, disconnect, reconnect, resource cleanup | Business side effect đúng nếu không kiểm tra DB/outbox |
| **System/contract** | RSocket + DB + HTTP + broker | Testcontainers, mock API, contract fixtures | At-least-once/idempotency, replay và xử lý duplicate | Bảo đảm sản xuất dưới mọi điều kiện |

Không thay toàn bộ bộ kiểm thử bằng một test chỉ mock `RSocketRequester`: test đó có thể bỏ qua lỗi SETUP metadata, sai route hoặc codec không tương thích.

## 6. Integration test TCP trên random port

Spring Boot 3.5 cung cấp `@LocalRSocketServerPort` trong package `org.springframework.boot.test.rsocket.server` để inject cổng đã được hệ điều hành cấp khi `spring.rsocket.server.port=0`. Không dùng `@LocalServerPort`: annotation đó dành cho cổng web HTTP và có thể khác cổng TCP RSocket.

### 6.1. Test Request-Response và remote error

~~~java
import java.time.Duration;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.rsocket.server.LocalRSocketServerPort;
import org.springframework.messaging.rsocket.RSocketRequester;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(properties = {
        "spring.rsocket.server.port=0",
        "spring.rsocket.server.transport=tcp"
})
class InventoryRSocketIT {

    @LocalRSocketServerPort
    int port;

    @Autowired
    RSocketRequester.Builder requesterBuilder;

    @Autowired
    AuditRegistry auditRegistry;

    private RSocketRequester requester;

    @BeforeEach
    void connect() {
        requester = requesterBuilder.tcp("127.0.0.1", port);
    }

    @AfterEach
    void close() {
        if (requester != null) {
            requester.dispose();
        }
    }

    @Test
    void requestResponseReturnsExpectedDto() {
        StepVerifier.create(requester
                .route("inventory.check")
                .data(new InventoryQuery("SKU-101"))
                .retrieveMono(Availability.class))
            .assertNext(value -> {
                assertEquals("SKU-101", value.sku());
                assertEquals(12, value.available());
            })
            .expectComplete()
            .verify(Duration.ofSeconds(5));
    }

    @Test
    void invalidBusinessInputIsNotSuccess() {
        StepVerifier.create(requester
                .route("inventory.check")
                .data(new InventoryQuery(""))
                .retrieveMono(Availability.class))
            .expectErrorMatches(error -> error != null)
            .verify(Duration.ofSeconds(5));
    }
}
~~~

`@SpringBootTest` phải quét được `InventoryRSocketController` và `AuditRegistry` trong ứng dụng mẫu. Nếu bài tập của dự án có package khác, chỉ định đúng test configuration thay vì dựa vào component scan không kiểm soát. Các test RSocket chạy trên socket thật; không cần mở port 7000 cố định nên tránh xung đột khi CI chạy song song.

Test `invalidBusinessInputIsNotSuccess` chỉ xác nhận server không trả success. Với một ứng dụng thực, cần định nghĩa **hợp đồng lỗi có cấu trúc** (mã `INVALID_SKU`, tương quan và thông báo an toàn) rồi assert loại thông điệp phù hợp; không dựa vào raw exception message của Spring RSocket giữa các phiên bản.

### 6.2. Stream: kiểm thử thứ tự, demand và cancellation

Thêm test sau vào **cùng lớp** `InventoryRSocketIT`:

~~~java
@Test
void requestStreamRespectsDownstreamDemand() {
    var updates = requester
            .route("inventory.watch")
            .data(new InventoryQuery("SKU-101"))
            .retrieveFlux(InventoryTick.class);

    StepVerifier.create(updates, 0)
            .thenRequest(2)
            .assertNext(tick -> {
                assertEquals("SKU-101", tick.sku());
                assertEquals(1L, tick.sequence());
            })
            .assertNext(tick ->
                    assertEquals(2L, tick.sequence()))
            .thenRequest(1)
            .assertNext(tick ->
                    assertEquals(3L, tick.sequence()))
            .thenCancel()
            .verify(Duration.ofSeconds(5));
}
~~~

`StepVerifier.create(flux, 0)` bắt đầu với **zero demand**, sau đó thử yêu cầu đúng ba item. `thenCancel()` phát cancellation từ subscriber; responder phải không giữ vô hạn tài nguyên tạo stream sau khi client không còn cần dữ liệu. Tuy nhiên, test này **chưa đo chính xác số frame `REQUEST_N` trên dây**, vì framework/transport có thể dùng prefetch hoặc buffer. Nếu hợp đồng cần xác minh request-N/cancellation frame, instrument transport hoặc dùng test RSocket protocol cấp thấp.

Để test không có dữ liệu ngoài nhu cầu, dùng nguồn kiểm soát được và ngưỡng thời gian phù hợp thay vì chỉ assert giá trị ba item đầu. `Flux.range` phát theo Reactive Streams demand nên là nguồn đơn giản để kiểm tra. Khi dữ liệu đi từ HTTP polling hoặc một hot source không tôn trọng backpressure, cần thêm giới hạn buffer/drop/fail theo contract và test quá tải riêng.

### 6.3. Request-Channel: nhiều request, nhiều response

Thêm test:

~~~java
@Test
void requestChannelReturnsResponsesInOrder() {
    var queries = reactor.core.publisher.Flux.just(
            new InventoryQuery("SKU-A"),
            new InventoryQuery("SKU-B"));

    StepVerifier.create(requester
            .route("inventory.bulk")
            .data(queries, InventoryQuery.class)
            .retrieveFlux(Availability.class))
        .assertNext(value -> assertEquals("SKU-A", value.sku()))
        .assertNext(value -> assertEquals("SKU-B", value.sku()))
        .expectComplete()
        .verify(Duration.ofSeconds(5));
}
~~~

Trong responder `bulk(...)` dùng `concatMap(this::check)` để giữ thứ tự kiểm tra cho ví dụ. Nếu thay bằng `flatMap` với concurrency, response có thể đảo thứ tự theo thời gian hoàn thành; khi đó test cần sử dụng correlation ID thay vì mặc định reply thứ N ứng với request thứ N. Với request-channel thực tế, cũng phải test **input Flux lỗi/hủy giữa chừng** và **server ngừng phát response** khi downstream cancellation được truyền.

### 6.4. Fire-and-Forget: test side effect, không ngộ nhận ACK

~~~java
@Test
void fireAndForgetMustCheckServerSideEffectSeparately() {
    String eventId = "audit-" + java.util.UUID.randomUUID();

    StepVerifier.create(requester
            .route("audit.accept")
            .data(new AuditEvent(eventId, "stock checked"))
            .send())
        .expectComplete()
        .verify(Duration.ofSeconds(5));

    // Assertion riêng trên trạng thái server, không suy ra từ send().
    org.awaitility.Awaitility.await()
            .atMost(Duration.ofSeconds(3))
            .until(() -> auditRegistry.contains(eventId));
}
~~~

`.send()` phát **fire-and-forget**, và `Mono<Void>` hoàn thành chỉ là kết quả gửi trên giao thức, **không đảm bảo handler đã commit DB hoặc hoàn tất công việc**. Trong test cùng ứng dụng, kiểm tra `AuditRegistry` cho phép quan sát handler đã chạy; khi qua nhiều service cần kiểm tra storage/ack nghiệp vụ được thiết kế riêng.

Nếu cần phản hồi “đã lưu bền” trước khi trả kết quả cho caller, **không dùng fire-and-forget** mà hãy dùng request-response với response `ACCEPTED`/`COMMITTED` được định nghĩa rõ; khi cần phát sự kiện sang broker, cân nhắc outbox để bền vững và có thể retry.

### 6.5. Timeout từ client khi responder xử lý chậm

~~~java
@Test
void requestResponseTimesOutWhenServerIsTooSlow() {
    StepVerifier.create(requester
            .route("inventory.slow")
            .data(new InventoryQuery("SKU-101"))
            .retrieveMono(Availability.class)
            .timeout(Duration.ofMillis(300)))
        .expectError(java.util.concurrent.TimeoutException.class)
        .verify(Duration.ofSeconds(5));
}
~~~

Ở đây server cố ý trả sau khoảng **hai giây**, client áp giới hạn **300 ms**. `timeout` là operator Reactor ở phía client, không chứng minh server đã ngừng mọi side effect; nó có thể hủy subscription trong tuyến reactive nhưng không thể rollback một transaction hay HTTP request đã gửi. Nếu CI quá chậm khiến handshake không ổn định, có thể warm up connection bằng request `inventory.check` trước test này và chọn ngân sách lớn hơn đủ phân biệt 2 giây từ server.

### 6.6. Lỗi route, MIME type và serialization

Bên cạnh DTO hợp lệ, cần kiểm tra:

| Dữ liệu / setup | Kết quả mong đợi |
| --- | --- |
| Route `inventory.check` có request đúng | Một `Availability` |
| Route không tồn tại | Không nhận được response thành công; lỗi có thể được RSocket framework mã hóa dưới dạng application error |
| Content type không khớp codecs đã đăng ký | Lỗi decode/encode được phân loại, không biến thành kết quả rỗng |
| Payload sai kiểu/thiếu field | Lỗi contract hoặc response nghiệp vụ theo chính sách |
| Response quá lớn vượt giới hạn frame/reassembly | Bị giới hạn và có metric/cảnh báo; không cấp phát bộ nhớ vô hạn |
| Setup metadata/authentication sai | Kết nối hoặc request bị từ chối theo security contract |
| Server trả `Mono.empty()` trên route request-response | Client thấy completion rỗng, khác cả giá trị trả về lẫn lỗi |

Với những đường chịu schema evolution, test cả DTO version N và N+1: client mới đọc được dữ liệu cũ, và client cũ có xử lý an toàn field/enum mới hay không. RSocket metadata route là một phần hợp đồng; đổi route hoặc encoding không khác gì đổi endpoint HTTP mà không duy trì backward compatibility.

## 7. Ngắt kết nối: những failure mode phải mô phỏng

RSocket dùng một kết nối transport dài sống để multiplex nhiều request. Vì vậy một sự cố socket có thể ảnh hưởng **nhiều request đang chạy**, khác với quan sát một HTTP request độc lập.

| Failure mode | Vị trí xảy ra | Kết quả client có thể thấy | Điều cần xác minh |
| --- | --- | --- | --- |
| Host/port không tồn tại | Trước TCP connect | Connect refused/timeout | Không treo vĩnh viễn; retry có deadline |
| Lỗi `SETUP` (codec, auth, metadata) | Khi bắt đầu phiên | Setup rejected/application error | Không retry mù lỗi cấu hình hoặc credential |
| Mạng bị reset giữa Request-Response | Sau khi gửi request | Connection error / cancel / timeout | Server đã xử lý hay chưa có thể không biết |
| Mất mạng khi Request-Stream | Sau vài phần tử | Flux kết thúc lỗi/hủy, hoặc timeout | Đã nhận bao nhiêu item; có cursor resume/replay không |
| Mất mạng trong Request-Channel | Hai chiều đang phát dữ liệu | Có thể mất một phần dữ liệu cả hai hướng | Correlation, ack ứng dụng, offset/cursor và duplicate |
| Client cancel stream | Sau khi nhận đủ dữ liệu | Tín hiệu `CANCEL` và giải phóng subscription | Không tiếp tục giữ DB cursor/HTTP stream không cần thiết |
| Server restart/rolling update | Kết nối cũ bị đóng | Nhiều request lỗi cùng lúc | Client thiết lập lại kết nối, xử lý tác vụ đang dở |
| Half-open/blackhole network | TCP trông còn mở nhưng không có frame | Chờ vô hạn nếu thiếu timeout/keepalive | Deadline, heartbeat, phát hiện peer không còn sống |
| TLS certificate sai/hết hạn | Handshake | SSL error trước application handler | Không tắt TLS validation để “qua test” |
| Rate/concurrency limit | Server/lease/rejection | Rejected request hoặc timeout | Giảm concurrency, backoff và load shedding |

**Đừng đồng nhất trạng thái socket với trạng thái nghiệp vụ.** Khi response bị mất, server vẫn có thể đã ghi đơn hàng, gửi email hoặc publish Kafka event. Phải có cách truy vấn kết quả bằng business key trước khi thực hiện lại một thao tác có side effect.

### 7.1. Test bằng client `dispose()`

`RSocketRequester` triển khai `Disposable`, có `dispose()` và `isDisposed()`. Trong test, có thể gọi `dispose()` để đóng phía client, rồi xác minh các subscription đang hoạt động kết thúc theo chính sách và tài nguyên được giải phóng.

~~~java
// Phác thảo cho test đóng client có chủ đích:
RSocketRequester requester = builder.tcp("127.0.0.1", port);

// Thực hiện ít nhất một request để kết nối lazy đã hình thành.
StepVerifier.create(requester.route("inventory.check")
        .data(new InventoryQuery("SKU-101"))
        .retrieveMono(Availability.class))
    .expectNextCount(1)
    .expectComplete()
    .verify(Duration.ofSeconds(5));

requester.dispose();
org.junit.jupiter.api.Assertions.assertTrue(requester.isDisposed());
~~~

Đây là test **lifecycle local**: nó xác nhận chính ứng dụng đã đóng requester, **không tương đương** với cắt mạng từ xa hay kill server. Trạng thái terminal của một Flux đang chạy khi dispose có thể phụ thuộc transport/timing; test phải nói rõ mình mong đợi lỗi, completion hay cancellation theo cách ứng dụng chuyển đổi chúng, không cố gán mọi tình huống thành cùng một exception.

### 7.2. Fault injection với Toxiproxy hoặc network proxy

Để mô phỏng lỗi mạng lặp lại được, đặt proxy giữa client và server trong môi trường test:

~~~text
RSocketRequester:127.0.0.1:8666
          |
       [Proxy]
       | latency / timeout / reset / cut connection
          |
Inventory RSocket server:127.0.0.1:<test-port>
~~~

Quy trình kiểm thử:

1. Khởi chạy server RSocket trên cổng ngẫu nhiên, khởi chạy proxy trỏ tới cổng đó.
2. Tạo requester kết nối qua proxy và thực hiện một request khỏe, kiểm tra response/stream.
3. Bắt đầu một request-stream dài hoặc một request-response có thời gian xử lý đáng kể.
4. Cắt kết nối/đặt blackhole sau khi đã quan sát được một phần dữ liệu.
5. Xác nhận subscriber **không chờ vô hạn**: timeout và cơ chế phát hiện mất kết nối phát tín hiệu như thiết kế.
6. Mở lại proxy/server. Với chính sách phục hồi của ứng dụng, tạo kết nối mới hoặc session resume đã được cấu hình, rồi thử lại tác vụ theo đúng business key.
7. Đối chiếu DB, HTTP side effect và broker output để phát hiện duplicate hoặc dữ liệu bị bỏ sót.

Tùy Toxiproxy/netem, thao tác “disable proxy” có thể đóng kết nối ngay, còn “timeout/toxic” có thể làm kết nối im lặng. Hai dạng gây failure path khác nhau, cần test cả hai. Không thao tác network fault trên cụm production chỉ để xác minh bài học này.

### 7.3. Test restart/rolling update

Mô phỏng server chết giữa lần gọi và khởi động instance mới:

~~~text
T0  client tạo requester, gửi eventId=E100
T1  server bắt đầu cập nhật DB
T2  process/server bị kill, connection đóng
T3  client thấy error hoặc timeout
T4  server mới nhận cùng eventId=E100
T5  kiểm tra DB/outbox: side effect logic chỉ xảy ra một lần
~~~

Nếu DB commit trước T2, retry có thể gặp record đã tồn tại; đó là tình huống bình thường của **at-least-once delivery**. Thiết kế idempotency cần phát hiện cùng `eventId`/request ID và trả kết quả phù hợp, không tạo đơn hàng thứ hai. Nếu DB chưa commit, retry có thể thực hiện lại an toàn khi có điều kiện nguyên tử.

Test cần phân biệt **rolling dừng có kiểm soát** (graceful shutdown/drain) và **kill đột ngột**. Graceful shutdown giảm số request bị ngắt nhưng không thay thế chiến lược phục hồi khi crash/network partition.

### 7.4. Keepalive và resume không giải quyết mọi thứ

RSocket hỗ trợ keepalive frame để phát hiện kết nối không còn phản hồi. Một số transport/library có hỗ trợ **session resumption** nếu hai phía cấu hình đầy đủ và giữ được state tương ứng. Cần lưu ý:

- Keepalive giúp phát hiện tình trạng peer không phản hồi, **không** cam kết server hoàn tất nghiệp vụ.
- Resume là cơ chế giao thức có điều kiện về thời gian/state và buffer; không tự bảo đảm hoạt động sau khi toàn bộ process/pod server bị thay bằng instance không có session state.
- Resumption không phải transaction DB hoặc exactly-once của HTTP/Kafka. Sau khi kết nối phục hồi, vẫn phải kiểm tra event ID/cursor và tác dụng phụ nghiệp vụ.
- Nếu connector có cơ chế tự reconnect, cần biết khi nào tạo phiên mới, khi nào resume, và trạng thái của những request đã thất bại trước đó.
- Một requester bị dispose có chủ đích không nên được dùng như thể vẫn giữ kết nối sống; quản lý factory và lifecycle connection rõ ràng.

Việc thử `resume()`/keepalive phải dựa vào API của phiên bản RSocket Java hiện dùng và hỗ trợ ở cả server, client, ingress/proxy; không đưa cấu hình resume mang tính phỏng đoán vào production.

## 8. Phân loại lỗi theo ranh giới RSocket

RSocket dùng frame và error code của giao thức, không dùng HTTP status `404/409/503` trên đường TCP. Spring handler có thể trả lỗi qua `ERROR` frame; Java client thường nhận exception thuộc hệ RSocket hoặc được bao bởi Reactor/transport.

| Nhóm lỗi | Ví dụ | Có retry? | Hành động |
| --- | --- | --- | --- |
| **Dữ liệu/hợp đồng** | SKU không hợp lệ, type/codec sai, route không tồn tại | Thường không | Trả business validation error hoặc quarantine, sửa schema/route |
| **RSocket SETUP/security** | Authentication metadata sai, MIME mismatch, `SETUP` rejected | Không retry với cấu hình y nguyên | Sửa credential, trust, codec và metadata setup |
| **Remote application error** | Responder ném exception khi truy cập DB/HTTP | Tùy mã nguyên nhân, không mặc định | Phân loại business reject với dependency transient |
| **Transport unavailable** | Connection refused/reset, peer restart | Có giới hạn với operation an toàn | Backoff, reconnect/new requester, circuit breaker |
| **Timeout/unknown outcome** | Response không đến sau khi gửi lệnh | Tùy idempotency | Tra cứu bằng business key, retry an toàn hoặc reconciliation |
| **Overload/backpressure** | Producer quá nhanh, queue/pool quá đầy | Giảm tải trước | Giới hạn concurrency, flow control, buffer policy rõ |
| **Cancellation** | Subscriber chủ động hủy | Không phải lỗi server theo mặc định | Dọn tài nguyên upstream; không tự retry stream đã hủy |
| **Serialization failure** | Dữ liệu decoder không đọc được | Không retry mù | Version schema, codec config, DLQ nếu từ broker |

Ví dụ `io.rsocket.exceptions.ApplicationErrorException` có thể xuất hiện khi responder phát application error. Nhưng **đừng phụ thuộc cứng vào một class** để suy ra mã lỗi nghiệp vụ, vì lỗi có thể bị bọc hoặc thông tin chi tiết thay đổi theo phiên bản. Với operation quan trọng, xây **error contract có cấu trúc** ở payload/metadata được công bố hoặc một quy tắc mapping lỗi thống nhất.

### 8.1. Không coi remote error là `Mono.empty()`

Đoạn sau là **sai** nếu dùng cho xác nhận đặt hàng:

~~~java
return requester.route("orders.reserve")
        .data(command)
        .retrieveMono(ReservationResult.class)
        .onErrorResume(error -> Mono.empty());
~~~

Nó làm lỗi kết nối/DB trông giống “không có kết quả”; caller có thể tiếp tục workflow mà không biết reservation có thành công hay không. Cách an toàn hơn là ánh xạ lỗi transport thành lỗi domain có trạng thái **không chắc chắn**, để orchestration quyết định retry/reconciliation:

~~~java
public class RemoteInventoryUnavailable extends RuntimeException {
    public RemoteInventoryUnavailable(Throwable cause) {
        super("Inventory RSocket is temporarily unavailable", cause);
    }
}
~~~

Tầng gọi có thể trả HTTP `503` hoặc tạm hoãn message broker (theo retry/dead-letter policy) nhưng không phải lúc nào cũng kết luận “đơn hàng chưa được xử lý”.

### 8.2. Error contract ở request-response

Một cách tránh phụ thuộc message của `ApplicationErrorException` là trả một envelope dữ liệu cho **kết quả nghiệp vụ có thể dự đoán được**:

~~~java
public record StockCheckResult(
        boolean accepted,
        String code,
        String sku,
        Integer available) {
}
~~~

Ví dụ `code=OUT_OF_STOCK` là một business rejection có kiểm soát, không cần ném transport exception. Ngược lại, khi database bị ngắt hoặc kết nối RSocket mất, vẫn cần **error signal** phù hợp để tầng gọi phân loại là dependency unavailable, không tự tạo `accepted=false` như thể một kết quả nghiệp vụ hợp lệ.

Để tương thích N/N+1 trong triển khai nhiều phiên bản, trường `code` cần có danh mục ổn định và cách xử lý unknown value. Nâng cấp schema có thể đòi thêm field optional/default, nhưng không được thay đổi ý nghĩa `accepted`/`available` mà không có contract migration.

## 9. Retry, reconnect và idempotency

Một số thư viện RSocket có khả năng quản lý kết nối, nhưng không nên suy ra “RSocket tự kết nối lại và phát lại mọi request an toàn”. Cần quyết định ở **ba tầng**:

1. **Transport reconnect:** tái lập kết nối khi server xuất hiện lại, cần phân biệt với resume của một session cũ.
2. **Application retry:** thực thi lại operation khi biết lỗi có thể phục hồi và còn retry budget.
3. **Business deduplication:** bảo đảm replay không tạo tác dụng phụ trùng khi kết quả lần trước chưa chắc chắn.

### 9.1. Chính sách theo loại tương tác

| Operation | Có thể retry khi disconnect? | Điều kiện bắt buộc |
| --- | --- | --- |
| `inventory.check` chỉ đọc | Thường có | Retry giới hạn, timeout và circuit breaker; không gây tác dụng phụ |
| `inventory.watch` theo stream | Có thể subscribe lại | Có sequence/cursor hoặc chấp nhận mất/trùng item; không tiếp tục mù từ điểm ngắt |
| `inventory.bulk` request-channel | Khó hơn | Correlation theo từng item, ack ứng dụng, checkpoint/idempotency từng item |
| `audit.accept` fire-and-forget | Không thể biết đã xử lý từ `send()` | Nếu quan trọng, phải có eventId/inbox bền vững hoặc đổi sang request-response |
| `orders.reserve` làm thay đổi trạng thái | Chỉ khi idempotent | Stable requestId, unique constraint, kiểm tra trạng thái sau timeout |
| Operation thanh toán/giao hàng | Cần hợp đồng đặc biệt | Idempotency của downstream, outbox/inbox và reconciliation |

**Nguyên tắc:** retry chỉ là **resubscribe một Publisher**, không có cơ chế tự undo side effect. Nếu Publisher là cold nguồn đọc, nó thường tạo lại request; nếu là hot stream, nó có thể hoạt động khác. Với RSocketRequester sử dụng connection cũ đã hỏng, chỉ thêm `retryWhen(...)` chưa chắc đã khiến transport tạo phiên mới theo cách bạn mong muốn. Cần test lifecycle connection và cơ chế reconnect của phiên bản client đang dùng.

### 9.2. Ví dụ retry cho phép đọc (idempotent)

Tách retry policy khỏi transport giúp unit test dễ hơn. `Supplier<Mono<Availability>>` được gọi lại cho mỗi attempt, nên caller có thể cung cấp request mới hoặc logic dùng requester mới sau disconnect.

~~~java
import java.time.Duration;
import java.util.concurrent.TimeoutException;
import java.util.function.Supplier;
import io.rsocket.exceptions.ConnectionErrorException;
import reactor.core.publisher.Mono;
import reactor.util.retry.Retry;

public final class InventoryReadRetryPolicy {

    public Mono<Availability> run(
            Supplier<Mono<Availability>> requestFactory) {

        return Mono.defer(requestFactory)
                .timeout(Duration.ofSeconds(2))
                .retryWhen(Retry.backoff(
                        2, Duration.ofMillis(200))
                        .maxBackoff(Duration.ofSeconds(1))
                        .jitter(0.3)
                        .filter(InventoryReadRetryPolicy::isTransient)
                        .onRetryExhaustedThrow(
                                (config, signal) -> signal.failure()));
    }

    private static boolean isTransient(Throwable error) {
        for (Throwable current = error;
                current != null; current = current.getCause()) {

            if (current instanceof TimeoutException
                    || current instanceof ConnectionErrorException
                    || current instanceof java.io.IOException) {
                return true;
            }
        }
        return false;
    }
}
~~~

`Retry.backoff(2, ...)` cho phép **tối đa 2 lần retry sau lần gốc**, không phải tổng 2 lần xử lý. Bộ phân loại trên chỉ là ví dụ khởi đầu; một số lỗi network có thể có subtype khác hoặc bị framework bọc. Cần bổ sung classifier dựa trên exception thực tế, không mặc định retry mọi `RuntimeException`. Đặc biệt, `RejectedSetupException`, lỗi authentication, sai route hoặc bad payload không nên retry liên tục với cùng cấu hình.

Client sử dụng:

~~~java
// Trong service dùng RestClient/RSocketRequester tại ranh giới tích hợp:
InventoryReadRetryPolicy policy = new InventoryReadRetryPolicy();
Mono<Availability> result = policy.run(
        () -> requester.route("inventory.check")
                .data(new InventoryQuery("SKU-101"))
                .retrieveMono(Availability.class));
~~~

Đoạn trên minh họa retry tại application layer; nó dùng requester đã có sẵn. Nếu requester đó đã bị dispose hoặc implementation không reconnect được, caller phải cấp **requester factory/reconnect strategy** phù hợp, không để retry quay vòng trên connection chết. Trong production, nên tránh tạo một TCP connection mới cho **mỗi** request khỏe chỉ vì retry; quản lý reuse và tái kết nối có kiểm soát, đóng requester không dùng nữa.

### 9.3. Test retry bằng virtual time, không cần socket thật

Test trực tiếp pipeline Reactor giúp đo số attempts và backoff mà không chờ giây thực:

~~~java
import java.time.Duration;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import reactor.util.retry.Retry;

import static org.junit.jupiter.api.Assertions.assertEquals;

class RetryPolicyTest {

    @Test
    void retriesTwiceThenSucceeds() {
        AtomicInteger attempts = new AtomicInteger();

        StepVerifier.withVirtualTime(() ->
                Mono.defer(() -> {
                    int n = attempts.incrementAndGet();
                    if (n < 3) {
                        return Mono.<String>error(
                                new TimeoutException("transient"));
                    }
                    return Mono.just("ok");
                }).retryWhen(Retry.backoff(
                        2, Duration.ofSeconds(1)).jitter(0)))
            .expectSubscription()
            .thenAwait(Duration.ofSeconds(4))
            .expectNext("ok")
            .expectComplete()
            .verify(Duration.ofSeconds(5));

        assertEquals(3, attempts.get());
    }
}
~~~

`StepVerifier.withVirtualTime` chỉ điều khiển **scheduler của Reactor** trong pipeline (ví dụ `delay`, `timeout`, `Retry.backoff`). Nó **không làm trôi thời gian của TCP, TLS, hệ điều hành hoặc broker thật**. Để xác minh network disconnect, vẫn phải dùng integration/fault test riêng.

### 9.4. Từ retry tới duplicate suppression

Ví dụ một lệnh `ReserveInventory` có:

~~~json
{
  "requestId": "checkout:req-0031",
  "orderId": "ord-901",
  "sku": "SKU-101",
  "quantity": 2
}
~~~

Ranh giới server:

~~~text
requestId == khóa idempotency của một lệnh logic
  |
  +-- INSERT inbox/processed_requests (UNIQUE requestId) trong transaction
  |     nếu đã có thì tra cứu kết quả cũ
  |
  +-- Kiểm tra số lượng tồn, cập nhật có điều kiện
  |
  +-- Ghi trạng thái và outbox trong cùng transaction
  |
  +-- Commit -> trả response theo contract
~~~

Nếu socket mất sau commit, client retry bằng **cùng requestId**; server nhận diện và trả kết quả cũ hoặc trạng thái `PROCESSING/COMPLETED` theo hợp đồng, không giảm tồn kho lần hai. Nếu phát Kafka event sau DB commit, dùng outbox hoặc cơ chế publish có thể khôi phục; không tuyên bố transaction DB bao trùm RSocket và Kafka.

**Fire-and-forget không thích hợp làm bước xác nhận một giao dịch quan trọng** nếu không có kênh acknowledgment nghiệp vụ khác. `Mono<Void>.then()` của client không chứng minh inbox/DB đã commit bên kia.

## 10. Test stream bị hủy và backpressure vượt mức

### 10.1. Hủy phải làm sạch tài nguyên upstream

Trong unit test, có thể dùng `TestPublisher` để xác minh cách pipeline xử lý lỗi và cancellation:

~~~java
import org.junit.jupiter.api.Test;
import reactor.test.StepVerifier;
import reactor.test.publisher.TestPublisher;

class StreamLifecycleTest {

    @Test
    void propagatesErrorFromUpstream() {
        TestPublisher<String> source = TestPublisher.create();

        StepVerifier.create(source.flux().map(String::toUpperCase))
                .then(() -> source.next("one"))
                .expectNext("ONE")
                .then(() -> source.error(
                        new IllegalStateException("upstream closed")))
                .expectError(IllegalStateException.class)
                .verify();
    }

    @Test
    void cancelStopsSubscription() {
        TestPublisher<String> source = TestPublisher.create();

        StepVerifier.create(source.flux(), 0)
                .thenRequest(1)
                .then(() -> source.next("one"))
                .expectNext("one")
                .thenCancel()
                .verify();

        source.assertCancelled();
    }
}
~~~

Đây là unit test của **Reactor Publisher**, không phải bằng chứng transport RSocket đã phát `CANCEL` frame. Integration test cần thêm một handler `doFinally(signal -> ...)` và xác minh server thực sự nhận cancellation khi client đóng subscription hoặc requester. Có thể dùng Awaitility để chờ counter/metric tăng, tránh assert tức thời gây flaky khi tín hiệu đi qua mạng.

Khi upstream là DB cursor, Kafka consumer hoặc HTTP stream, giải phóng subscription phải kéo theo close/cancel tài nguyên đúng phiên bản driver. Kiểm tra số connection, thread, socket, buffer sau nhiều vòng subscribe/cancel để phát hiện leak.

### 10.2. Backpressure xuyên mạng không đồng nghĩa chống mọi OOM

RSocket dùng Reactive Streams `REQUEST_N` để biểu diễn demand đối với Request-Stream/Channel; nhưng ứng dụng vẫn có thể gây quá tải khi:

- Dữ liệu đến từ hot publisher không có backpressure phù hợp.
- Code dùng `buffer()` không giới hạn hoặc `onBackpressureBuffer()` không đặt capacity.
- Producer lấy một lượng dữ liệu lớn rồi giữ sẵn trong memory trước khi chia thành `Flux`.
- Codec/fragmentation và network buffers lớn hơn ngưỡng giám sát.
- Handler gọi code blocking trong Netty event-loop, khiến các stream khác bị nghẽn.

Chọn một chính sách rõ ràng: **buffer hữu hạn**, drop có metric, fail-fast với lỗi `OVERLOADED`, hoặc chuyển dữ liệu sang queue bền vững để xử lý sau. Với sự kiện tài chính/giao dịch, không được âm thầm drop chỉ để giữ latency thấp.

Ví dụ giới hạn số item trước khi xử lý:

~~~java
Flux<InventoryQuery> incoming = Flux.just(
        new InventoryQuery("A"),
        new InventoryQuery("B"));

Flux<Availability> bounded = incoming
        .limitRate(16)
        .concatMap(query -> Mono.just(
                new Availability(query.sku(), 12)));
~~~

`limitRate(16)` ảnh hưởng cách Reactor yêu cầu dữ liệu upstream, không phải “chặn tối đa 16 request HTTP song song” hay “buffer tối đa 16 item”; nếu cần giới hạn concurrency, đặt ở operator như `flatMap(mapper, concurrency)`, semaphore/bulkhead hoặc adapter phù hợp. Khi dùng `flatMap`, response có thể đến lệch thứ tự; nên dựa vào correlation key thay vì giả định vị trí đầu ra tương ứng đầu vào.

## 11. Security, TLS và hợp đồng metadata cũng phải được test

RSocket có thể chạy trực tiếp trên TCP hoặc qua WebSocket; **TCP `builder.tcp(...)` thông thường không tự có TLS**, và cấu hình HTTPS trên web server cũng không mặc định bảo vệ TCP RSocket độc lập. Với RSocket-over-WebSocket, dùng `wss://` khi có TLS. Với TCP/TLS, cần cấu hình Reactor Netty/client transport và trust/key material phù hợp trong cả server và client.

### 11.1. Những trường hợp bảo mật cần xác minh

| Trường hợp | Kỳ vọng |
| --- | --- |
| Client có CA hợp lệ | Handshake TLS thành công và hostname được xác minh |
| Server certificate hết hạn hoặc không đúng host | Kết nối bị từ chối; không bật trust-all để vượt lỗi |
| mTLS client không có certificate/key | Handshake thất bại theo policy |
| Token RSocket setup sai/hết hạn | `SETUP` hoặc request bị từ chối theo cơ chế authentication |
| Request thiếu quyền truy cập route | Bị từ chối có kiểm soát, không trả dữ liệu nhạy cảm |
| Metadata không đúng MIME/codec | Lỗi setup/codec được phân loại, không coi là server unavailable thông thường |
| Payload chứa thông tin cá nhân | Không log body hoặc metadata chứa token khi debug frames |
| Client đổi chứng chỉ trong quá trình rotation | Có cơ chế refresh/reconnect/rolling update phù hợp |

Để xác thực và phân quyền trên RSocket, dùng Spring Security RSocket hoặc interceptor/metadata authentication đã được cấu hình và kiểm thử; không nhét token vào payload nghiệp vụ rồi chỉ kiểm tra ở một handler. Một kết nối RSocket sống lâu có thể mang context xác thực từ `SETUP`, vì vậy cần xem xét token expiry/rotation và chính sách kiểm tra quyền theo từng request khi phù hợp.

### 11.2. Khi bật WebSocket và gateway

RSocket-over-WebSocket qua HTTP reverse proxy cần hỗ trợ **Upgrade**, idle timeout phù hợp với stream dài, request size/frames và TLS forwarding. Một gateway chỉ test REST 200 OK có thể vẫn chặn WebSocket handshake hoặc đóng idle connection sau một phút. Kiểm thử `wss://` xuyên ingress thực tế là việc khác với test TCP loopback.

Không xem HTTP `101 Switching Protocols` là acknowledgment của một RSocket request. Nó chỉ xác nhận giai đoạn WebSocket upgrade; sau đó còn `SETUP`, route metadata, payload codecs, keepalive và flow-control.

## 12. Observability: nhìn rõ kết nối, request và business effect

RSocket không dùng mô hình HTTP request/response một-một. Một TCP connection có thể chứa nhiều streams và từ cả hai hướng, nên chỉ nhìn TCP connection count không đủ giải thích vấn đề. Nên gắn **business correlation ID**, route và kết quả xử lý ở tầng application.

### 12.1. Nhóm metric đề xuất

| Metric ứng dụng | Ý nghĩa | Điều cần cảnh báo |
| --- | --- | --- |
| `rsocket_connections_active` | Kết nối đang hoạt động theo endpoint | Tăng/giảm bất thường, connection leak |
| `rsocket_connect_failures_total{reason}` | Lỗi thiết lập transport/SETUP | Lỗi DNS/TLS/auth hoặc backend unavailable |
| `rsocket_requests_total{route,result}` | Số request theo route và kết quả | Tỷ lệ lỗi route, remote application error |
| `rsocket_request_duration_seconds{route,result}` | Latency request-response và các thao tác có deadline | P95/P99 vượt SLO |
| `rsocket_streams_active{route}` | Số stream/channel đang còn subscription | Stream leak hoặc đứt đột ngột |
| `rsocket_cancellations_total{route}` | Số lần subscriber chủ động hủy | Cancel cao do client timeout hoặc người dùng đổi trang |
| `rsocket_retry_attempts_total{reason}` | Số lần retry với nhóm nguyên nhân | Retry storm, lỗi hạ tầng dai dẳng |
| `rsocket_timeouts_total{route}` | Timeout ứng dụng | Timeout vượt budget hoặc partner chậm |
| `rsocket_decode_failures_total{schema}` | Lỗi codec/hợp đồng | Producer/consumer không tương thích |
| `business_duplicates_suppressed_total` | Idempotency ngăn xử lý trùng | Retry/disconnect đang tạo duplicate |
| `outbox_oldest_unpublished_seconds` | Sự kiện business chưa publish | Phát hiện tác động tích hợp sau connection loss |

Đây là **tên metric minh họa cần triển khai qua Micrometer** hoặc instrumentation được chọn, không phải tất cả tự động có chỉ nhờ thêm `spring-boot-starter-actuator`. Tránh đặt `sku`, `eventId`, user ID, raw route parameter, token hoặc exception message vào low-cardinality labels. Sử dụng route template, mã lỗi hữu hạn và service/instance version.

### 12.2. Tracing qua RSocket, HTTP và broker

Một trace mong muốn:

~~~text
HTTP POST /inventory/reserve (trace T, business requestId R)
  |
  +-- OrderService
        |
        +-- RSocket request inventory.reserve (route, correlation R)
              |
              +-- InventoryService DB transaction
              +-- Write outbox eventId E
                    |
                    +-- Kafka publisher / downstream consumer
~~~

RSocket route/metadata không phải HTTP header; **không mặc định rằng `traceparent` tự đi qua mọi RSocket client, mọi broker adapter và mọi custom scheduler**. Cần kiểm tra Micrometer Tracing/Observation, metadata propagation, Reactor Context và instrumentation của transport/framework theo đúng phiên bản. Trong test, đo quan hệ parent–child spans và cùng business `requestId`, chứ không suy ra từ một log cùng thread.

Không dùng `traceId` làm idempotency key: khi retry hoặc replay, một business operation có thể có nhiều trace/span; `requestId` vẫn phải ổn định. Không ghi bearer token, credential hay dữ liệu cá nhân vào metadata debug hoặc trace attributes.

### 12.3. Log có cấu trúc ở đúng tầng

Khi gặp lỗi, log tối thiểu:

~~~json
{
  "component": "inventory-rsocket-client",
  "route": "inventory.check",
  "result": "CONNECTION_LOST",
  "retryAttempt": 2,
  "elapsedMs": 1840,
  "correlationId": "corr-58b",
  "requestId": "checkout:req-0031"
}
~~~

Chỉ ghi `requestId` nếu chính sách dữ liệu cho phép và không đặt nó làm metric label. Log cần phân biệt error signal của **subscriber**, số lần reconnect và kết quả nghiệp vụ trong DB/outbox. Một exception stack trace giống nhau cho mọi message không đủ để quyết định replay.

## 13. Ma trận kiểm thử bắt buộc trước khi phát hành

| Ca thử | Tầng | Hành động kiểm thử | Điều kiện đạt |
| --- | --- | --- | --- |
| Request-response thành công | RSocket integration | Gọi route `inventory.check` | DTO đúng và completion |
| Validation error | RSocket integration | SKU rỗng | Có lỗi contract, không trả dữ liệu thành công |
| Route không tồn tại | Integration | Gọi route lạ | Nhận lỗi có kiểm soát |
| Request-stream | Integration | Yêu cầu 3 item rồi cancel | Đúng thứ tự, không gửi thêm cho subscriber sau cancel |
| Request-channel | Integration | Gửi 2 SKU, đọc 2 response | Mapping đúng theo correlation/thứ tự contract |
| Fire-and-forget | Integration | `send()` rồi kiểm tra storage | Không suy diễn thành công nghiệp vụ từ send completion |
| Slow responder | Integration | Server delay 2 s, client timeout ngắn | Timeout hữu hạn và loại lỗi rõ ràng |
| Remote application error | Integration | Handler cố ý `Mono.error` | Không bị coi thành `Mono.empty()`/not-found |
| Codec mismatch | Integration | Setup/payload sai định dạng | Decode failure, không retry vô hạn |
| Connection refused | Fault integration | Server chưa chạy hoặc sai port | Error trong deadline, retry budget hữu hạn |
| Cut in-flight request | Fault integration | Reset socket sau request | Kết quả business được đối soát, không double effect |
| TCP half-open | Fault integration | Proxy blackhole | Timeout/keepalive phát hiện trong ngân sách |
| Disconnect stream | Fault integration | Cắt sau 5 item | Nhận error/termination; lưu cursor hoặc báo mất dữ liệu |
| Recovery/reconnect | Fault integration | Khôi phục server sau restart | Client có thể tạo phiên mới theo policy |
| Unsupported resume | Fault integration | Resume state bị mất/hết hạn | Fallback rõ ràng, không im lặng bỏ qua item |
| Backpressure overload | Load/integration | Subscriber chậm, producer nhanh | Giới hạn buffer, không OOM/khóa event loop |
| Subscriber cancellation | Unit + integration | Cancel khi stream còn hoạt động | Upstream release resources, active stream count giảm |
| TLS handshake failure | Security integration | CA/hostname/mTLS sai | Từ chối kết nối; không tắt verification |
| Auth setup rejected | Security integration | Token sai | Không lặp vô hạn; không lộ payload/secret |
| Retry read-only | Unit virtual time | Fail 2 lần rồi thành công | Tổng 3 attempts, backoff đúng |
| Retry side-effect | System test | DB commit rồi mất response | Same requestId, chỉ một tác dụng phụ logic |
| Rolling deployment | System test | Dừng một pod khi có stream | Client recovery và cancellation/cleanup phù hợp |
| Replay event lịch sử | Contract/system test | Payload N-1, schema cũ | Decoder và business logic tương thích |

### 13.1. Đừng kiểm thử kết nối bằng chỉ một assert

Để chứng minh failover an toàn cho `ReserveInventory`, phải thu thập được bằng chứng:

1. Client thấy lỗi/timeout ở đúng thời điểm fault.
2. Server/DB cho thấy đã commit hay chưa.
3. Retry dùng lại cùng business `requestId`.
4. Inbox/unique constraint ngăn double reservation.
5. Outbox/broker downstream không có hai effect logic.
6. Incident/metric cho thấy sự cố và trạng thái phục hồi.

Nếu chỉ assert `StepVerifier.expectError()`, test mới biết client gặp lỗi; **chưa kiểm thử được tính đúng đắn của cả luồng tích hợp**.

### 13.2. Cách giảm test flaky

- Dùng cổng ngẫu nhiên; chỉ kết nối sau khi application context/RSocket server sẵn sàng.
- Đặt deadline cho mọi `StepVerifier.verify(Duration)`, Awaitility và fault test; không chờ vô hạn.
- Với test timeout, chọn khoảng cách đủ lớn giữa delay server và timeout client để chịu biến động CI.
- Tách unit virtual time và network real time; không trộn clock ảo với socket thật.
- Không dựa vào `Thread.sleep(...)` để đo cancellation; dùng tín hiệu/counter và chờ điều kiện có timeout.
- Đặt request/event ID duy nhất cho mỗi test, dọn DB/topic/queue và requester/connection sau test.
- Kiểm tra số attempts bằng counter và kết quả nghiệp vụ, không dựa vào số dòng stack trace.
- Chạy các fault test làm hỏng network trong container hoặc test process biệt lập; không can thiệp port dịch vụ đang dùng của người khác.

## 14. Runbook xử lý sự cố khi triển khai

### Triệu chứng và hướng khoanh vùng

| Triệu chứng | Câu hỏi đầu tiên | Hướng xử lý |
| --- | --- | --- |
| Không kết nối được ngay từ đầu | DNS/port/transport, TCP hay WebSocket, `SETUP` MIME/auth? | Kiểm tra routing/TLS/config và lỗi setup |
| Request chậm nhưng TCP còn mở | Upstream DB/HTTP chậm hay subscriber không request demand? | Quan sát latency, thread, stream active, deadline |
| Stream ngừng sau đúng 60 giây | Idle timeout gateway/proxy, keepalive có đúng? | Test qua ingress thật, chỉnh timeout có cơ sở |
| Sau deploy mất hàng loạt stream | Pod stop/rolling, drain và reconnect có được thiết kế? | Kiểm tra graceful shutdown, retry/cursor |
| Spike request retries | Connection flap, circuit breaker, duplicate callbacks? | Giới hạn retry, backoff/jitter, tránh hot loop |
| Lệnh reserve bị trừ tồn kho hai lần | Idempotency của server thiếu hay dùng requestId mới? | Tra cứu inbox/transaction/outbox, sửa duplicate |
| Client mất token hoặc TLS certificate hết hạn | Trust store, key/cert, auth setup, rotation policy | Sửa secret/certificate; không tắt xác thực |
| Memory tăng khi request-stream nhiều | Buffer không giới hạn, cancel không cleanup, stream leak? | Kiểm tra demand, heap, connection/buffer metrics |
| Test pass local, fail CI | Race port, timing, server chưa sẵn, timer quá ngắn? | Random port, readiness, Testcontainers/Awaitility |
| DTO đọc được nhưng dữ liệu sai | Schema version/semantic mismatch? | Contract test và decoder tương thích, không retry dữ liệu sai |

### Quy trình ứng cứu

1. **Cô lập nhóm lỗi:** transport, setup/security, application logic, codec, backpressure hay dependency.
2. **Giới hạn thiệt hại:** nếu reconnect/retry quá nhiều, giảm concurrency/mở circuit breaker và giữ message trong broker/outbox bền vững.
3. **Xác định kết quả nghiệp vụ:** tra cứu bằng requestId/eventId, không suy đoán từ timeout.
4. **Sửa nguyên nhân:** DNS/ingress/TLS, policy resource, code validation, codec/schema hoặc downstream.
5. **Khôi phục có kiểm soát:** mở lại traffic, thiết lập lại RSocket session khi phù hợp và redrive backlog theo idempotency key.
6. **Đối soát và quan sát:** kiểm tra DB, HTTP side effects, outbox/broker, stream cursor và tỷ lệ duplicate.
7. **Hậu kiểm:** thêm fixture test tình huống vừa gặp, điều chỉnh timeout/keepalive/retry budget theo SLO thực.

## 15. Ghi nhớ

- RSocket có **bốn mô hình** tương tác chính; mỗi mô hình có contract về completion/error/demand khác nhau.
- `StepVerifier` chứng minh hành vi Reactive Streams; chỉ integration test qua transport mới kiểm được `SETUP`, route, codec, backpressure/cancellation xuyên mạng.
- **Timeout hoặc mất kết nối không chứng minh request chưa xử lý**; với side effect phải dùng idempotency, inbox/outbox và reconciliation.
- `send()` của fire-and-forget **không** phải acknowledgment nghiệp vụ.
- Retry phải hữu hạn, phân loại lỗi rõ và có kế hoạch **reconnect/restore stream state**; một lần resubscribe không tự bảo đảm có phiên mới hoặc exactly-once.
- Test failure phải đối chiếu **kết quả cuối** ở DB, HTTP/broker và backlog, chứ không chỉ kiểm tra exception client.

### Câu hỏi tự kiểm tra

1. Vì sao `Mono<Void>` của `send()` không chứng minh server đã commit tác vụ?
2. Sự khác nhau giữa `StepVerifier.thenCancel()` và một TCP reset qua fault proxy là gì?
3. Nếu client nhận 5 item rồi stream đứt, muốn khôi phục không mất/trùng cần metadata gì?
4. Vì sao một `retryWhen` có thể thử lại trên requester đã đóng thay vì thực sự phục hồi?
5. Khi một lệnh reserve timeout sau commit DB, vì sao retry phải giữ requestId?
6. Có thể dùng virtual time để kiểm thử network keepalive và TLS handshake không?
7. Bốn tình huống nào cần được phân loại khác nhau: invalid SKU, rejected SETUP, connection lost và HTTP downstream 503?
8. Vì sao `limitRate(16)` không có nghĩa mọi buffer hoặc concurrency đều bị giới hạn ở 16?

## Tài liệu tham khảo

- [Spring Framework — RSocket Overview, RSocketRequester, Annotated Responders](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [Spring Boot 3.5 — RSocket Messaging](https://docs.spring.io/spring-boot/3.5/reference/messaging/rsocket.html)
- [Spring Boot 3.5 API — LocalRSocketServerPort](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/rsocket/server/LocalRSocketServerPort.html)
- [RSocket Protocol Specification](https://rsocket.io/about/protocol/)
- [RSocket Java — Reactor Netty Transport](https://github.com/rsocket/rsocket-java)
- [Project Reactor — Testing with StepVerifier](https://projectreactor.io/docs/core/release/reference/testing.html)
- [Project Reactor — RetryBackoffSpec](https://projectreactor.io/docs/core/release/api/reactor/util/retry/RetryBackoffSpec.html)
- [RSocket Java API — Protocol Error Exceptions](https://javadoc.io/static/io.rsocket/rsocket-core/1.1.5/io/rsocket/exceptions/package-summary.html)
- [Spring Integration — RSocket Support](https://docs.spring.io/spring-integration/reference/rsocket.html)
- [Spring Security — RSocket](https://docs.spring.io/spring-security/reference/reactive/integrations/rsocket.html)





