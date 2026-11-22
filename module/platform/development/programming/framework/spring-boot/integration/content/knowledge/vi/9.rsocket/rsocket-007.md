# Cấu hình responder bằng @MessageMapping khi cần nhận thông điệp

## Mục tiêu và bối cảnh

Trong module **SPRING_BOOT_INTEGRATION**, Spring Boot tổ chức tích hợp qua HTTP client, cơ sở dữ liệu, cache, broker thông điệp và các adapter Spring Integration. Những luồng này không chỉ cần kết nối thành công: chúng còn phải quản lý **cấu hình, hợp đồng dữ liệu, giao dịch, lỗi, xử lý trùng lặp, kiểm thử và quan sát**.

**RSocket** là giao thức hướng message, hỗ trợ nhiều request/stream được multiplex trên một kết nối TCP hoặc WebSocket. Spring Framework cung cấp **RSocket responder** theo mô hình Spring Messaging: một Spring bean gắn `@Controller`, các method gắn `@MessageMapping`, và các `Mono`/`Flux` thể hiện kết quả. Phía gọi thường dùng `RSocketRequester`.

Ví dụ, Inventory Service có thể nhận:

- `inventory.stock.get`: truy vấn tồn kho theo SKU, trả một kết quả.
- `inventory.stock.watch`: đăng ký luồng thay đổi tồn kho.
- `inventory.audit.accept`: tiếp nhận thông báo không cần phản hồi nghiệp vụ trực tiếp.
- `inventory.batch.reserve`: nhận nhiều commands trong request-channel và trả kết quả theo từng lệnh.
- `inventory.reserve`: thực hiện command có tác động PostgreSQL và trả receipt.

Giả sử request `inventory.reserve` đã được Inventory COMMIT nhưng mạng đứt trước khi Order Service nhận response. Caller thấy timeout, song reservation đã tồn tại. Do đó, **một responder đúng về route chưa đủ để an toàn**: phải có operation ID ổn định, SQL uniqueness, giới hạn concurrency và reconciliation.

Bài thuộc chương **RSocket**, đề mục **Cấu hình responder bằng `@MessageMapping` khi cần nhận thông điệp**.

### Kết quả học tập

1. Giải thích vai trò requester, responder, route, payload và routing metadata.
2. Phân biệt request-response, fire-and-forget, request-stream và request-channel.
3. Cấu hình RSocket TCP responder trên Spring Boot, tự kiểm tra server port.
4. Viết `@Controller`/`@MessageMapping`, dùng DTO, `Mono`, `Flux`, `@DestinationVariable`.
5. Gọi responder qua `RSocketRequester` và hiểu lifecycle của connection/request.
6. Cấu hình và chẩn đoán MIME/codecs/`RSocketStrategies`.
7. Xử lý validation, security, RSocket errors và unknown business outcomes.
8. Tránh blocking event loop khi gọi JDBC, Redis hay HTTP partner.
9. Thiết kế backpressure, bounded concurrency, cancellation và retry.
10. Tích hợp transaction, outbox/inbox, idempotency và kiểm thử fault windows.

> **Nguyên tắc:** `@MessageMapping` khai báo **route nhận message**, không tạo HTTP endpoint, durable queue hay exactly-once business transaction.

## 1. RSocket trong kiến trúc Spring Boot Integration

~~~mermaid
flowchart LR
    A["Order Service / RSocketRequester"] --> B["RSocket TCP/WebSocket"]
    B --> C["RSocketMessageHandler"]
    C --> D["@MessageMapping responder"]
    D --> E["Application service"]
    E --> F["PostgreSQL / Redis"]
    E --> G["Transactional outbox"]
    G --> H["Kafka / RabbitMQ / HTTP"]
    D -. "Mono / Flux" .-> A
~~~

| Thành phần | Trách nhiệm | Không tự cung cấp |
| --- | --- | --- |
| RSocket transport | Multiplex frames qua TCP/WebSocket | Durable retention |
| `RSocketRequester` | Gửi request, FNF, stream, channel | Transaction cho hệ thống đích |
| Routing metadata | Chỉ định tên route | Authentication/authorization |
| `RSocketMessageHandler` | Dispatch message vào annotated methods | Domain logic |
| `@Controller` | Spring bean chứa responder methods | TCP port nếu chưa cấu hình |
| `@MessageMapping` | Map logical route | HTTP method/path |
| `RSocketStrategies` | Encoder, decoder, metadata extraction | Business schema semantics |
| `Mono`/`Flux` | Publisher, demand, cancellation | Idempotency/durability |
| Application service | Validation, transaction, receipts | Tự động phân tán ACID |

**Phân biệt transport với broker:**

| Nhu cầu | RSocket | HTTP REST | Kafka/RabbitMQ |
| --- | --- | --- | --- |
| Request-response | Native | Native | RPC thiết kế thêm |
| Một request → nhiều phản hồi | Native request-stream | SSE/streaming tùy API | Consumer đọc messages riêng |
| Hai chiều cùng một tương tác | Native request-channel | WebSocket/HTTP streaming khác | Nhiều queues/topics |
| Backpressure | Reactive Streams demand | Phụ thuộc API/protocol | Broker-specific flow control |
| Chạy khi consumer offline | Không tự giữ | Không tự giữ | Có theo queue/topic policy |
| Replay sau crash | Cần business store/cursor | Cần business store | Có theo broker/retention |
| Exactly-once business effect | Không tự có | Không tự có | Không tự có |

Chọn RSocket khi cần streaming hai chiều hoặc multiplexed requests giữa peers có thể duy trì kết nối. Với yêu cầu **đợi đích offline hàng giờ rồi giao lại**, cần outbox, queue, broker hoặc work table bền vững.

## 2. Bốn interaction models

~~~mermaid
flowchart TD
    A["Requester"] --> R["REQUEST_RESPONSE: 1 request → 0..1 reply"]
    A --> F["FIRE_AND_FORGET: 1 → không có application reply"]
    A --> S["REQUEST_STREAM: 1 request → nhiều replies"]
    A --> C["REQUEST_CHANNEL: nhiều requests ↔ nhiều replies"]
~~~

| Kiểu | Client thường dùng | Responder thường nhận/trả | Use case |
| --- | --- | --- | --- |
| Request-response | `retrieveMono(Reply.class)` | DTO → `Mono<Reply>` | Truy vấn hoặc command cần receipt |
| Fire-and-forget | `send()` | DTO → `Mono<Void>` | Notification chấp nhận không có reply |
| Request-stream | `retrieveFlux(Update.class)` | DTO → `Flux<Update>` | Theo dõi tồn kho |
| Request-channel | `data(Flux, Type).retrieveFlux(...)` | `Flux<Command>` → `Flux<Result>` | Batch commands hai chiều |

Loại frame/interaction được **requester chọn**. Return type Java phải tương thích với RSocket interaction và route, không tự biến request-response thành request-stream chỉ vì method trả `Flux`.

### 2.1. Demand không đồng nghĩa dữ liệu bền

RSocket request-stream/channel dùng Reactive Streams demand để điều tiết số item phía nhận đã yêu cầu. Điều này giúp tránh phát vô hạn vào một slow subscriber **nếu nguồn publisher thực sự tuân thủ demand**.

Backpressure không:

- Ghi item vào database khi peer offline.
- Bảo đảm thứ tự commit từ nhiều concurrent streams.
- Tăng HikariCP connections hoặc capacity của HTTP partner.
- Undo side effect khi client cancel.
- Thay inbox/outbox hoặc idempotency.

## 3. Dependencies và auto-configuration

Ví dụ Spring Boot 3.x, Java 17+, Gradle Groovy DSL:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-rsocket'

    // Khi đồng thời dùng HTTP WebFlux/WebClient:
    implementation 'org.springframework.boot:spring-boot-starter-webflux'

    // Nếu responder gọi JDBC:
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'org.postgresql:postgresql'

    implementation 'org.springframework.boot:spring-boot-starter-validation'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:postgresql'
}
~~~

`spring-boot-starter-rsocket` cung cấp RSocket/Spring Messaging integration; **không bắt buộc** thêm WebFlux chỉ để mở RSocket over TCP. WebSocket transport có thể yêu cầu web runtime thích hợp. Dùng BOM tương thích với Spring Boot/Spring Framework/Reactor/RSocket Java versions của dự án; Boot 4 có thể đổi starter/package/codecs.

### 3.1. Server TCP

~~~yaml
spring:
  rsocket:
    server:
      port: 7000
      transport: tcp

app:
  inventory:
    max-watch-subscribers: 100
~~~

`spring.rsocket.server.port` là **RSocket server port**, khác `server.port` của HTTP server. Spring Boot tự cấu hình responder khi đủ dependency, port và bean conditions. Đọc startup log để biết listener đã bind thành công; chỉ thêm `@MessageMapping` không đồng nghĩa server chắc chắn đang chạy.

### 3.2. TCP và WebSocket

| Transport | Dùng khi | Lưu ý |
| --- | --- | --- |
| RSocket over TCP | Kết nối trực tiếp giữa services | LB, firewall, TLS, idle timeout |
| RSocket over WebSocket | Hạ tầng hỗ trợ HTTP upgrade | Web runtime, mapping path, reverse proxy |
| Local/in-process transport | Test logic giao thức | Không thay fault tests trên network thật |

Một số phiên bản Boot có `spring.rsocket.server.mapping-path` cho WebSocket; đây là path **HTTP upgrade**, không phải route `inventory.stock.get` của RSocket TCP. Cấu hình TLS phải phù hợp transport/version; không giả định `server.ssl.*` HTTP sẽ tự áp lên RSocket TCP.

## 4. Responder đầu tiên: request-response

DTO cho hợp đồng tồn kho:

~~~java
// StockQuery.java
public record StockQuery(String sku) {
}

// StockAvailability.java
public record StockAvailability(
        String sku,
        long availableQuantity,
        long aggregateVersion) {
}
~~~

Port dịch vụ:

~~~java
import reactor.core.publisher.Mono;

public interface InventoryReadService {
    Mono<StockAvailability> getAvailability(String sku);
}
~~~

Responder:

~~~java
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Mono;

@Controller
public class InventoryRSocketResponder {

    private final InventoryReadService inventory;

    public InventoryRSocketResponder(InventoryReadService inventory) {
        this.inventory = inventory;
    }

    @MessageMapping("inventory.stock.get")
    public Mono<StockAvailability> getStock(
            @Payload StockQuery request) {

        if (request == null || request.sku() == null
                || request.sku().isBlank()) {
            return Mono.error(
                    new IllegalArgumentException("sku required"));
        }

        return inventory.getAvailability(request.sku());
    }
}
~~~

- `@Controller` đánh dấu component chứa message endpoints.
- `@MessageMapping` đăng ký **logical RSocket route**.
- `@Payload` nhận dữ liệu từ RSocket frame đã được decode.
- `Mono<StockAvailability>` có tối đa một giá trị.
- `Mono.error(...)` là reactive error; nó không tự biến thành HTTP 400.
- `RSocketMessageHandler` chịu trách nhiệm tìm route, argument resolution và encode response.

~~~mermaid
sequenceDiagram
    participant C as RSocketRequester
    participant T as TCP transport
    participant H as RSocketMessageHandler
    participant M as @MessageMapping
    participant S as InventoryReadService
    C->>T: REQUEST_RESPONSE route=inventory.stock.get
    T->>H: Routing metadata + JSON
    H->>M: getStock(StockQuery)
    M->>S: getAvailability(sku)
    S-->>M: Mono result
    M-->>H: Publisher
    H-->>C: RESPONSE payload
~~~

Nếu route không tồn tại, client nhận lỗi RSocket/mapping theo implementation, **không phải HTTP 404**.

## 5. Gọi responder bằng RSocketRequester

Spring Boot thường tạo `RSocketRequester.Builder` khi RSocket infrastructure được cấu hình.

~~~java
import java.time.Duration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.rsocket.RSocketRequester;

@Configuration(proxyBeanMethods = false)
public class InventoryRequesterConfiguration {

    @Bean
    RSocketRequester inventoryRequester(
            RSocketRequester.Builder builder) {

        // Minh họa khởi tạo kết nối trong bài học.
        return builder
                .connectTcp("localhost", 7000)
                .block(Duration.ofSeconds(5));
    }
}
~~~

Đây là cấu hình **đơn giản cho test/học tập**. Nếu peer down lúc startup, `block()` có thể khiến bean tạo thất bại. Production cần quản lý connection/reconnect, load balancing, authentication, readiness, shutdown; tránh tạo connection mới cho mỗi request. Không gọi `block()` trên Reactor Netty event loop.

Client:

~~~java
import org.springframework.messaging.rsocket.RSocketRequester;
import reactor.core.publisher.Mono;

public class InventoryRSocketClient {

    private final RSocketRequester requester;

    public InventoryRSocketClient(RSocketRequester requester) {
        this.requester = requester;
    }

    public Mono<StockAvailability> getStock(String sku) {
        return requester
                .route("inventory.stock.get")
                .data(new StockQuery(sku))
                .retrieveMono(StockAvailability.class);
    }
}
~~~

Publisher là lazy; request thực sự được gửi khi subscribe. Trong reactive HTTP handler, nên **trả publisher** để outer framework quản lý subscription.

### 5.1. Anti-pattern: subscribe vô chủ

~~~java
public void handle(String sku) {
    client.getStock(sku).subscribe();
    // Không còn ownership để xử lý error/cancel/completion.
}
~~~

Tốt hơn:

~~~java
public Mono<StockAvailability> handle(String sku) {
    return client.getStock(sku)
            .timeout(java.time.Duration.ofSeconds(2));
}
~~~

Timeout của một query đọc có thể retry theo policy; timeout của command cập nhật dữ liệu có thể là **UNKNOWN** do phía đích đã commit.

### 5.2. Requester lifecycle

Một requester gắn với RSocket connection/session. Khi mạng hỏng, requester có thể cần được tạo lại; không giả định `.retrieveMono()` tự reconnect an toàn. Đặt reconnect backoff/jitter, giới hạn concurrent connection attempts và giữ operationId ổn định cho commands được retry.

## 6. Fire-and-forget bằng @MessageMapping

DTO thông báo:

~~~java
public record AuditEvent(
        String eventId,
        String sku,
        String action) {
}
~~~

Responder:

~~~java
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Mono;

@Controller
public class AuditResponder {

    private final AuditService audit;

    public AuditResponder(AuditService audit) {
        this.audit = audit;
    }

    @MessageMapping("inventory.audit.accept")
    public Mono<Void> accept(AuditEvent event) {
        return audit.record(event);
    }
}
~~~

`AuditService.record` là port ứng dụng trả `Mono<Void>`. Requester:

~~~java
public Mono<Void> sendAudit(
        RSocketRequester requester, AuditEvent event) {

    return requester
            .route("inventory.audit.accept")
            .data(event)
            .send();
}
~~~

**Quan trọng:** `send()` không cung cấp **business acknowledgement** rằng responder đã ghi audit vào DB. Fire-and-forget không có response mang receipt.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant R as Responder
    participant D as PostgreSQL
    C->>R: FIRE_AND_FORGET E-100
    C->>C: send() completes
    R->>D: Write audit
    D--xR: SQL unavailable
    Note over C,D: Caller không có business receipt
~~~

Nếu audit, payment hoặc inventory event **không được phép mất**, dùng durable outbox/broker hoặc request-response với persisted receipt. Không lấy FNF làm thay thế RabbitMQ publisher confirm.

## 7. Request-stream: một yêu cầu, nhiều phản hồi

DTO:

~~~java
public record StockWatchRequest(String sku) {
}

public record StockUpdate(
        String sku,
        long quantity,
        long aggregateVersion) {
}
~~~

Nguồn cập nhật:

~~~java
import reactor.core.publisher.Flux;

public interface InventoryUpdateSource {
    Flux<StockUpdate> watch(String sku);
}
~~~

Responder:

~~~java
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Flux;

@Controller
public class StockWatchResponder {

    private final InventoryUpdateSource source;

    public StockWatchResponder(InventoryUpdateSource source) {
        this.source = source;
    }

    @MessageMapping("inventory.stock.watch")
    public Flux<StockUpdate> watch(StockWatchRequest request) {
        return source.watch(request.sku());
    }
}
~~~

Client:

~~~java
public Flux<StockUpdate> watchSku(
        RSocketRequester requester, String sku) {

    return requester
            .route("inventory.stock.watch")
            .data(new StockWatchRequest(sku))
            .retrieveFlux(StockUpdate.class);
}
~~~

### 7.1. Định nghĩa stream contract

Phải xác định:

1. Stream có gửi snapshot đầu tiên không, hay chỉ changes?
2. Ordering có được bảo đảm per SKU không?
3. Có replay theo cursor/aggregateVersion khi reconnect không?
4. Slow consumer được buffer, drop hoặc coalesce updates?
5. Mỗi client có thể mở bao nhiêu subscriptions?
6. Stream kết thúc khi nào?
7. Cancellation có giải phóng DB cursor/listener/buffer không?

Một `Flux` từ in-memory source không tự lưu events qua disconnect. Khi cần không bỏ sự kiện, dùng durable log + cursor hoặc message broker.

### 7.2. Backpressure REQUEST_N

~~~mermaid
sequenceDiagram
    participant C as Client
    participant R as Server
    C->>R: REQUEST_STREAM
    C->>R: REQUEST_N(3)
    R-->>C: Update #1
    R-->>C: Update #2
    R-->>C: Update #3
    C->>R: REQUEST_N(2)
    R-->>C: Update #4
    R-->>C: Update #5
~~~

Reactive source cần tôn trọng demand. `onBackpressureLatest()` chỉ phù hợp với trạng thái có thể bỏ giá trị trung gian; **không dùng để bỏ audit hoặc financial events**.

### 7.3. Cancellation

~~~java
return source.watch(request.sku())
        .doFinally(signalType ->
                metrics.recordStreamClosed(signalType.name()));
~~~

`metrics` là component minh họa. `doFinally` xử lý complete/error/cancel, nhưng không tự rollback transaction đã commit. Quản lý cleanup nguồn stream độc lập.

## 8. Request-channel: nhận Flux và trả Flux

Request-channel cho phép requester truyền nhiều commands và nhận nhiều results trong cùng interaction.

~~~java
public record ReservationCommand(
        String operationId,
        String orderId,
        String sku,
        int quantity) {
}

public record ReservationResult(
        String operationId,
        String outcome,
        String reservationId) {
}
~~~

Port:

~~~java
import reactor.core.publisher.Mono;

public interface ReservationService {
    Mono<ReservationResult> reserveIdempotently(
            ReservationCommand command);
}
~~~

Responder:

~~~java
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Flux;

@Controller
public class ReservationChannelResponder {

    private final ReservationService reservations;

    public ReservationChannelResponder(
            ReservationService reservations) {
        this.reservations = reservations;
    }

    @MessageMapping("inventory.batch.reserve")
    public Flux<ReservationResult> reserveMany(
            Flux<ReservationCommand> commands) {

        return commands
                .concatMap(reservations::reserveIdempotently);
    }
}
~~~

Requester:

~~~java
public Flux<ReservationResult> reserveMany(
        RSocketRequester requester,
        Flux<ReservationCommand> commands) {

    return requester
            .route("inventory.batch.reserve")
            .data(commands, ReservationCommand.class)
            .retrieveFlux(ReservationResult.class);
}
~~~

`concatMap` tuần tự hóa **trong một subscription**. Nhiều streams/connections có thể xử lý đồng thời, nên phải có per-resource/per-tenant limits.

### 8.1. FlatMap, ordering và concurrency

- `concatMap`: xử lý từng command theo thứ tự.
- `flatMap(fn, 8)`: cho phép nhiều commands đang thực thi; output có thể đảo thứ tự.
- `flatMapSequential`: giữ thứ tự output, nhưng các side effects có thể commit khác thứ tự.
- Nếu state machine cần order/version, dùng `aggregateVersion`, conditional update hoặc partitioning phù hợp, không chỉ dựa `Flux` ordering.

### 8.2. Channel không phải transaction vô hạn

Không bao một request-channel kéo dài trong một SQL transaction. Mỗi command có **transaction ngắn và operationId độc lập**; kết quả được phát sau commit. Một stream có thể xử lý thành công vài chục items rồi network disconnect, nên cần partial completion/recovery policy.

### 8.3. Partial failure

~~~text
Client gửi K1, K2, K3.
Server COMMIT K1 và K2.
Response cho K2 bị mất; connection ngắt.
Client chỉ chắc chắn đã nhận receipt của K1.
~~~

Client **không thể** kết luận K2 chưa được xử lý và tạo operation ID mới để gửi lại. Cần query status hoặc retry cùng key. K3 có thể chưa đến hoặc đã đến tùy thời điểm.

## 9. Route variables và route ownership

Route name là một phần **wire contract**, không phải tên method Java hoặc URL.

~~~java
public final class InventoryRoutes {

    private InventoryRoutes() {
    }

    public static final String STOCK_GET =
            "inventory.stock.get";

    public static final String RESERVE =
            "inventory.reserve";
}
~~~

Dùng constant trong annotation:

~~~java
@MessageMapping(InventoryRoutes.STOCK_GET)
public Mono<StockAvailability> get(StockQuery request) {
    return inventory.getAvailability(request.sku());
}
~~~

Route variable:

~~~java
import org.springframework.messaging.handler.annotation.DestinationVariable;
import org.springframework.messaging.handler.annotation.MessageMapping;

@MessageMapping("inventory.stock.{sku}")
public Mono<StockAvailability> bySku(
        @DestinationVariable String sku) {
    return inventory.getAvailability(sku);
}
~~~

Requester:

~~~java
return requester.route("inventory.stock.{sku}", sku)
        .retrieveMono(StockAvailability.class);
~~~

`@DestinationVariable` thuộc Spring Messaging route handling, **không phải** MVC `@PathVariable`. Validate SKU và authorization; client kiểm soát route không được quyền chọn bất kỳ business action nào.

| Annotation | Transport/boundary |
| --- | --- |
| `@MessageMapping` trong RSocket responder | Routing metadata → message handler |
| `@PostMapping` | HTTP endpoint |
| `@KafkaListener` | Topic/partition |
| `@RabbitListener` | Queue/consumer container |
| `@ServiceActivator` | Spring Integration MessageChannel |

Spring Messaging cũng dùng `@MessageMapping` trong STOMP/WebSocket contexts; ở bài này, phải đảm bảo **RSocket messaging infrastructure** được cấu hình.

## 10. Payload, MIME và RSocketStrategies

Một RSocket payload có **data bytes** và **metadata bytes**. Data có thể là JSON, Protobuf, CBOR hoặc binary. Metadata có thể bao gồm routing, authentication, trace/correlation và custom fields.

Client có thể gửi:

~~~json
{"sku":"SKU-A"}
~~~

Responder decode thành `StockQuery` khi có codec tương thích. `RSocketStrategies` tập hợp message encoders/decoders và metadata extractor support.

### 10.1. Data MIME type

~~~java
import java.time.Duration;
import org.springframework.messaging.rsocket.RSocketRequester;
import org.springframework.util.MimeTypeUtils;

RSocketRequester requester =
        RSocketRequester.builder()
                .dataMimeType(MimeTypeUtils.APPLICATION_JSON)
                .connectTcp("localhost", 7000)
                .block(Duration.ofSeconds(5));
~~~

Trong Spring Boot, ưu tiên injected builder vì đã có thể áp config codec/metadata/observation. Không tự thay toàn bộ `RSocketStrategies` rồi đánh mất default JSON codecs.

### 10.2. Composite metadata

~~~text
RSocket composite metadata
  - routing: inventory.reserve
  - authentication: credentials / bearer information
  - trace/correlation metadata
  - application-defined metadata
Data MIME: application/json
Data: {"operationId":"K-100","sku":"SKU-A",...}
~~~

Custom metadata không tự trở thành Spring message headers nếu chưa cấu hình extractor phù hợp. `@Header("tenantId")` không có nghĩa đã đọc một HTTP header; RSocket TCP không có HTTP request header trong mỗi message theo cùng semantics.

### 10.3. Security implication

Không tin metadata client tự gắn như `tenantId`, `role`, Java class name hoặc user identity. Cần xác thực kết nối/request rồi kiểm tra domain authorization. Đặc biệt không deserialize arbitrary Java class names từ untrusted type metadata.

### 10.4. Hợp đồng data MIME và schema

Cần công bố:

- MIME/codec.
- Required/optional/null fields.
- Timestamp/timezone, decimal units, enum unknown policy.
- Schema version và payload compatibility.
- Maximum payload size/nesting/collection cardinality.
- Error response representation.
- Idempotency/business identity.

RSocket protocol không biết một field `amountMinor` đang được hiểu là VND hay USD. Schema structural compatibility không tự đảm bảo business semantics.

## 11. Validation và RSocket error handling

DTO command:

~~~java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Positive;

public record ReserveCommand(
        @NotBlank String operationId,
        @NotBlank String orderId,
        @NotBlank String sku,
        @Positive int quantity) {
}
~~~

Method:

~~~java
import jakarta.validation.Valid;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import reactor.core.publisher.Mono;

@MessageMapping("inventory.reserve")
public Mono<ReservationResult> reserve(
        @Valid @Payload ReserveCommand command) {

    return reservations.reserveIdempotently(command);
}
~~~

`@Valid` chỉ có tác dụng nếu Bean Validation/messaging infrastructure version được cấu hình phù hợp. Phải test invalid/missing payload qua **RSocket connection thật**, không chỉ gọi Java method trực tiếp.

### 11.1. Missing, null và primitive defaults

Nếu JSON thiếu `quantity`, primitive `int` có thể nhận 0 tùy mapper; `@Positive` reject 0 khi validation chạy. Nếu nghiệp vụ cần phân biệt **absent** với explicit 0, dùng `Integer` + `@NotNull` hoặc kiểm tra JSON presence.

### 11.2. Error signal không phải HTTP status

| Lỗi | Cách xử lý |
| --- | --- |
| Invalid JSON/unsupported schema | Reject, không retry nóng |
| Missing required field | Business validation error |
| Unauthorized route/tenant | Reject + audit security |
| Optimistic lock conflict | Reload/reconcile nếu an toàn |
| SQL connection unavailable | Backoff/bulkhead, bounded retry |
| RSocket connection reset | Operation có thể UNKNOWN |
| Stream cancelled | Release subscriptions/resources |
| Fatal codec/server bug | Alert, không expose stacktrace |

Một exception từ `@MessageMapping` thường lan qua reactive error/RSocket error frame, **không phải HTTP 400/500**. Nếu muốn expected business rejection có cấu trúc, định nghĩa response contract:

~~~java
public record ReservationReply(
        String operationId,
        String outcome,
        String reservationId,
        String errorCode) {
}
~~~

Ví dụ `outcome` có thể là `ACCEPTED`, `CONFIRMED`, `REJECTED`, `UNKNOWN`. Không trả `CONFIRMED` khi mới chỉ ghi background job PENDING.

## 12. Không blocking Reactor event loop

RSocket dùng reactive/network infrastructure. Một handler return `Mono` nhưng gọi blocking JDBC/HTTP **trước khi tạo Mono** vẫn làm tắc execution thread.

### 12.1. Anti-pattern

~~~java
@MessageMapping("inventory.reserve")
public Mono<ReservationResult> reserve(
        ReservationCommand command) {

    ReservationResult result =
            jdbcStore.reserve(command); // Blocking!
    return Mono.just(result);
}
~~~

Đoạn này thực hiện SQL đồng bộ trước khi publisher hình thành; có thể khiến các RSocket streams và connection keepalive tăng latency.

### 12.2. Offload đúng sang boundedElastic

~~~java
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@MessageMapping("inventory.reserve")
public Mono<ReservationResult> reserve(
        ReservationCommand command) {

    return Mono.fromCallable(() ->
                    blockingReservationService
                            .reserveIdempotently(command))
            .subscribeOn(Schedulers.boundedElastic());
}
~~~

`Mono.fromCallable` là lazy, thực thi khi subscribe. `boundedElastic` phù hợp với blocking APIs hơn `Schedulers.parallel()`, nhưng **không tự giới hạn theo Hikari max connections hay HTTP quota**. Cần bulkhead tại từng external resource.

### 12.3. Transaction context không tự xuyên thread

Một Spring JDBC `@Transactional` method được gọi qua proxy sẽ mở transaction ở thread đang chạy method. Khi chuyển sang `boundedElastic`, đó là một **thread boundary**: transaction cũ ở caller không tự được propagate. Đặt transaction tại business service trên worker thread, không cố wrap toàn bộ reactive stream vô hạn bằng một local JDBC transaction.

Với R2DBC, dùng reactive transaction manager/`TransactionalOperator` và Reactor context phù hợp; không trộn JDBC transaction semantics vào reactive DB access.

### 12.4. Virtual threads Java 21

Virtual threads có thể giảm chi phí chờ blocking I/O, nhưng **không tăng năng lực PostgreSQL, Redis hoặc HTTP partner**. Bật virtual threads không thay thế resource budgets, deadlines hay flow control.

## 13. Backpressure và bounded concurrency

Một kết nối RSocket có thể có nhiều in-flight requests và streams. Không thể coi max TCP connections là toàn bộ admission policy.

| Nguồn tải | Giới hạn cần cân nhắc |
| --- | --- |
| Số active streams | Quota per client/tenant |
| Max payload/frame | Codec/memory safety |
| Route QPS | Rate limiter |
| JDBC SQL | HikariCP max + short transactions |
| HTTP downstream | Per-route connection/concurrency pool |
| Redis | Command latency/client capacity |
| Broker | Listener concurrency/prefetch |
| Retries | Attempts + deadline + backoff |
| Streaming sources | Bounded buffer/cancellation cleanup |

### 13.1. Semaphore quanh blocking SQL

~~~java
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

public class BoundedReservationAdapter {

    private final BlockingReservationService service;
    private final Semaphore permits = new Semaphore(8);

    public BoundedReservationAdapter(
            BlockingReservationService service) {
        this.service = service;
    }

    public Mono<ReservationResult> reserve(
            ReservationCommand command) {

        return Mono.fromCallable(() -> {
            boolean acquired =
                    permits.tryAcquire(100, TimeUnit.MILLISECONDS);

            if (!acquired) {
                throw new DownstreamBusyException(
                        "Reservation budget exceeded");
            }

            try {
                return service.reserveIdempotently(command);
            } finally {
                permits.release();
            }
        }).subscribeOn(Schedulers.boundedElastic());
    }
}
~~~

`DownstreamBusyException` là exception do ứng dụng định nghĩa. Tối đa 8 operations **trên một instance**; 8 pods có thể chạy tới 64 cùng lúc. `tryAcquire(timeout)` tránh chờ permit vô hạn, `finally` tránh leak.

Đây là bulkhead theo concurrency, **không phải rate limiter QPS**. Nếu mỗi call chỉ 5 ms, 8 permits có thể tạo throughput vượt quota partner. Khi cần toàn cluster quota, dùng chiến lược rate limit/distributed coordination phù hợp.

### 13.2. Unbounded buffers nguy hiểm

~~~java
// Anti-pattern khi producer nhanh hơn subscriber.
return source.watch(sku)
        .onBackpressureBuffer();
~~~

Không có giới hạn buffer có thể gây OOM. Nếu event chỉ là snapshot cập nhật, có thể coalesce/latest theo contract; audit/payment records không được drop tùy tiện. Nếu không được mất, dùng durable log hoặc bounded queuing + overflow handling rõ.

### 13.3. Giới hạn số subscriptions

`REQUEST_N` giới hạn items **trong stream**, không giới hạn số streams mới. Cần max streams per client/tenant, stream lifetime/idle policy, resource cleanup và chống mở hàng nghìn subscriptions tới cùng SKU.

## 14. Transaction và idempotency cho command responder

Một command `inventory.reserve` có side effect cần **business operationId** ổn định, không dùng RSocket stream ID hoặc connection ID làm idempotency key.

SQL ví dụ PostgreSQL:

~~~sql
CREATE TABLE inventory_reservations (
    reservation_id UUID PRIMARY KEY,
    operation_id UUID NOT NULL UNIQUE,
    order_id VARCHAR(120) NOT NULL,
    sku VARCHAR(100) NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    state VARCHAR(24) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE reservation_receipts (
    operation_id UUID PRIMARY KEY,
    request_hash CHAR(64) NOT NULL,
    receipt_json JSONB NOT NULL,
    completed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

`request_hash` là fingerprint của **canonical business payload**; cùng key nhưng payload khác phải reject mismatch. Business mutation và receipt phải commit **cùng SQL transaction**.

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class BlockingReservationService {

    private final ReservationStore store;

    public BlockingReservationService(ReservationStore store) {
        this.store = store;
    }

    @Transactional
    public ReservationResult reserveIdempotently(
            ReservationCommand command) {

        return store.insertOrReturnPreviousReceipt(command);
    }
}
~~~

`ReservationStore.insertOrReturnPreviousReceipt` là application-specific port, phải hiện thực atomic SQL insert/unique handling và transaction. `SELECT exists` rồi `INSERT` không có unique constraint **không đủ** khi hai clients retry đồng thời.

### 14.1. Retry cùng key nhưng không cùng payload

~~~text
K-100 -> reserve SKU-A quantity=2 -> receipt R-500.
K-100 -> reserve SKU-B quantity=7 -> conflict.
~~~

Không tạo reservation thứ hai cũng không trả receipt R-500 như thể đã áp dụng payload mới. Không coi operation ID là auth: cần tenant/user ownership và quyền reserve.

### 14.2. @Transactional không gồm HTTP/Kafka/Rabbit

SQL transaction không làm remote HTTP API, RSocket peer khác, Kafka publish hay RabbitMQ broker trở thành cùng distributed ACID transaction. Nếu cần phát event sau khi reservation commit, ghi **outbox intent** trong SQL transaction rồi relay sau commit.

### 14.3. Outbox/inbox

~~~mermaid
flowchart LR
    C["Order command"] --> T["Local SQL transaction"]
    T --> O["Save order + outbox K-100"]
    O --> R["Relay after commit"]
    R --> S["RSocket inventory.reserve K-100"]
    S --> D["Target SQL reservation + receipt"]
    D --> A["Response / UNKNOWN"]
    A --> P["Reconciliation/retry same K-100"]
~~~

Outbox bảo đảm không mất ý định khi process crash sau local commit; target idempotency bảo đảm retry an toàn. Outbox **at least once**, không tự exactly once.

**Điểm then chốt:** Responder phải bảo vệ business transaction bằng stable operationId/SQL uniqueness; RSocket connection và Reactive Streams không thể tự xác nhận/hoàn tác remote side effects.

 
## 15. Mất kết nối sau khi đích đã commit: kết quả UNKNOWN

Với RSocket request-response, caller có thể nhận `TimeoutException`, `ConnectionErrorException`, lỗi đóng connection hoặc kết thúc subscription bất thường, **kể cả khi responder đã COMMIT thành công**. Loại exception từ client không tự chứng minh business operation chưa xảy ra.

~~~mermaid
sequenceDiagram
    participant C as Order Service / Requester
    participant R as Inventory / Responder
    participant D as PostgreSQL
    C->>R: REQUEST_RESPONSE reserve(operationId=K-100)
    R->>D: INSERT reservation + receipt
    D-->>R: COMMIT OK
    R--xC: Response lost / connection reset
    C->>C: Timeout -> UNKNOWN
    C->>R: Query K-100 hoặc retry cùng K-100
    R->>D: Find persisted receipt
    D-->>R: RES-500 already committed
    R-->>C: Return same receipt
~~~

### 15.1. Các mốc không được trộn lẫn

| Mốc | Điều đã xảy ra | Chưa chứng minh |
| --- | --- | --- |
| Requester tạo `Mono` | Đã mô tả một operation | Frame đã rời JVM |
| Publisher được subscribe | RSocket operation được bắt đầu | Responder nhận đủ data |
| Responder method được gọi | Metadata/route/payload đủ để dispatch | Business transaction commit |
| Target SQL COMMIT | Local database ghi nhận state | Client đã nhận receipt |
| Responder phát response | Server ứng dụng có result | Bytes đã đến client |
| Client `retrieveMono` complete | Có result theo RSocket contract | Async downstream khác đã hoàn tất |
| Client `send()` complete cho FNF | Thao tác gửi phía requester hoàn thành | Responder đã COMMIT |

Một timeout ở phía caller sau bước 4 thường được gọi là **unknown outcome**, không phải business failure đã xác định. API cần trạng thái như `PENDING`, `CONFIRMED`, `REJECTED`, `UNKNOWN`.

### 15.2. Không retry bằng operationId mới

~~~java
// Sai: một intent có thể tạo hai reservations.
return inventoryReserve(newCommandWithRandomId())
        .retry(3);
~~~

Thay bằng một operationId đã lưu bền:

~~~java
ReservationCommand command =
        outboxRepository.findPendingCommand(operationId);

return rsocketClient.reserve(command)
        .timeout(java.time.Duration.ofSeconds(2))
        .onErrorResume(java.util.concurrent.TimeoutException.class,
                error -> reconciliation.lookup(command.operationId()));
~~~

`outboxRepository`, `rsocketClient` và `reconciliation` là ports minh họa. Logic thực phải phân biệt permanent/transient/unknown, đặt retry budget và persist outcome. Không chuyển mọi RSocket system error thành HTTP 500 rồi tạo một business command mới.

### 15.3. Client cancellation không phải rollback

Khi client hủy subscription hoặc timeout operator cancel upstream, responder có thể nhận cancellation. Nhưng:

- SQL transaction đã commit **không** tự rollback.
- HTTP partner có thể đã xử lý side effect dù socket client đóng.
- Broker có thể đã nhận event trước khi producer confirm đến.
- Một command đang chạy trên blocking thread có thể không hủy ngay khi cancellation.
- Ngay cả khi Java task interrupt, remote side effect chưa chắc bị hủy.

Hãy áp **deadline, idempotency và reconciliation**, không dựa vào `cancel()` để đảm bảo business atomicity.

### 15.4. Chọn request-response hay accepted-async

Nếu reservation thực hiện trong một transaction ngắn, trả synchronous receipt có thể phù hợp. Nếu phải gọi nhiều hệ thống hoặc chờ partner lâu:

1. RSocket responder validate và persist `operationId` + durable intent.
2. Trả `ACCEPTED` cùng ID, không trả `CONFIRMED`.
3. Worker xử lý qua outbox/broker.
4. Requester subscribe result stream hoặc query status.
5. Khi reconnect, requester dùng cùng ID để tiếp tục/đối soát.

RSocket cho phép streaming kết quả, nhưng **nguồn trạng thái** phải bền khi ứng dụng có yêu cầu recovery.

## 16. Lỗi ở các tầng khác nhau

Không phải exception nào cũng phát sinh bên trong method `@MessageMapping`.

~~~mermaid
flowchart TD
    A["RSocket frame"] --> B["Transport / connection"]
    B --> C["Routing metadata"]
    C --> D["Message decoding"]
    D --> E["Argument validation"]
    E --> F["Business service"]
    F --> G["JDBC/HTTP/Redis/broker"]
    G --> H["Response encode/send"]
~~~

Có thể xảy ra:

- **Transport/connection:** TLS handshake, peer disconnect, keepalive timeout.
- **Routing:** route không tồn tại hoặc ambiguous.
- **Payload:** MIME/codec mismatch, JSON malformed, unknown schema version.
- **Argument validation:** missing/invalid fields.
- **Authorization:** principal/tenant không đủ quyền.
- **Business:** conflict, duplicate operationId, state transition invalid.
- **Resource:** Hikari timeout, SQL deadlock, Redis unavailable, HTTP 429/503.
- **Output:** encode response fail, connection lost sau SQL commit.

### 16.1. Phân loại permanent/transient/unknown

| Lỗi | Nhóm | Policy gợi ý |
| --- | --- | --- |
| Wrong route, unsupported schema | Permanent cho phiên bản hiện tại | Chỉnh contract/deployment |
| Missing/invalid business field | Permanent nếu input không đổi | Rejected, không retry nóng |
| Unauthorized/forbidden | Permanent cho credentials hiện tại | Reject, audit |
| SQL uniqueness duplicate key | Tùy contract | Dedupe/return previous receipt |
| Optimistic version conflict | Có thể recover | Reload, business reconcile |
| SQL deadlock/serialization | Thường transient | Retry transaction giới hạn |
| Hikari pool exhausted | Resource overload | Bulkhead/backoff, cải thiện pool/tx |
| Remote HTTP 429/503 | Transient theo policy | Retry-After/backoff/rate limit |
| RSocket connection lost during command | **Unknown** | Lookup receipt/idempotent replay |
| Cancellation after local COMMIT | **Committed** tại local DB | Không undo; phản ánh đúng status |

Error handler không nên lộ stack trace SQL, access token hoặc PII. Có thể dùng `@MessageExceptionHandler`/Spring Messaging exception advice theo phiên bản phù hợp, hoặc chuyển expected business errors thành DTO rõ ràng; RSocket ERROR frames không có semantics HTTP status code.

### 16.2. Không nuốt lỗi rồi return success

~~~java
@MessageMapping("inventory.reserve")
public Mono<ReservationReply> incorrect(ReserveCommand command) {
    return reservationService.reserve(command)
            .onErrorResume(ex -> {
                log.warn("reserve failed", ex);
                return Mono.just(new ReservationReply(
                        command.operationId(),
                        "CONFIRMED", null, null));
            });
}
~~~

Đây là **anti-pattern**: một operation thất bại hoặc UNKNOWN bị báo thành `CONFIRMED`. Với command có side effect, cần phân loại lỗi, ghi trạng thái và trả đúng receipt hoặc error contract.

### 16.3. Bounded retries

~~~java
import java.time.Duration;
import reactor.util.retry.Retry;

return requester.route("inventory.stock.get")
        .data(new StockQuery(sku))
        .retrieveMono(StockAvailability.class)
        .retryWhen(Retry.backoff(2, Duration.ofMillis(100)));
~~~

Đây là minh họa **read-only query**; production cần lọc đúng transient errors và tổng deadline. Không copy chính policy này sang `inventory.reserve` nếu không có idempotency server-side.

Retries tại nhiều tầng có thể nhân attempts: client 3 × adapter 3 × broker 3 = 27. Giới hạn tổng attempts, backoff, jitter, deadlines và kiểm tra quotas.

## 17. Connection lifecycle, keepalive và reconnect

RSocket multiplex streams trên một connection. Khi mạng đứt, các active subscriptions có thể kết thúc lỗi; một requester gắn với connection cũ không đảm bảo có thể tự gửi tiếp trên connection mới.

### 17.1. Cấu hình keepalive

Trong các phiên bản RSocket Java hỗ trợ connector customization, có thể thiết lập keepalive:

~~~java
import java.time.Duration;

builder.rsocketConnector(connector ->
        connector.keepAlive(
                Duration.ofSeconds(20),
                Duration.ofSeconds(90)));
~~~

Đoạn này giả định có `RSocketRequester.Builder builder` tương thích và được cấu hình trước khi connect. Kiểm tra exact API/version và load balancer idle-timeout; không đặt keepalive interval lớn hơn idle timeout mà không chủ đích.

**Keepalive chỉ hỗ trợ connection liveness**, không chứng minh Inventory database khỏe hoặc một reservation đã được commit.

### 17.2. Reconnect và re-subscribe

~~~text
Connection reset
   -> requester marks connection unavailable
   -> backoff + jitter
   -> establish new connection and auth
   -> resubscribe stock.watch
   -> read snapshot / cursor if required
   -> reconcile in-flight reservation operationIds
~~~

Không re-subscribe hàng nghìn streams cùng lúc sau một outage; dùng connection/admission budget, retry jitter, restore priority và observability.

### 17.3. RSocket resume không phải durable queue

RSocket protocol có khả năng resumption nếu client/server cùng hỗ trợ và được cấu hình phù hợp, với giới hạn session/buffer. Không assume Spring Boot mặc định bật resume, hoặc có thể resume qua **process crash/redeploy**.

Nếu cần chắc chắn không mất updates qua downtime, dùng durable event log, monotonic cursor/aggregateVersion hoặc broker. Resume không thay business idempotency/SQL transactions.

### 17.4. Graceful shutdown

Khi rolling deploy:

1. Ngừng chấp nhận subscriptions/requests mới theo lifecycle.
2. Cho in-flight operations hoàn tất trong grace period khi an toàn.
3. Không đánh dấu success cho work chỉ tồn tại trong RAM.
4. Active streams có thể bị cancel; client cần reconnect và replay từ cursor.
5. Các commands UNKNOWN được đối soát theo operationId.
6. Giữ metrics/trace correlation để chẩn đoán sau restart.

Đừng hủy toàn bộ connections rồi giả định SQL operations đã rollback. Với Java virtual threads hoặc Reactor cancellation, local transaction có thể đã commit.

## 18. Bảo mật RSocket responder

Một route `inventory.reserve` có thể làm thay đổi dữ liệu. Cần xác định **ai được mở connection, ai được gọi route và ai được thao tác SKU/tenant cụ thể**.

### 18.1. Các lớp kiểm soát

| Lớp | Mục tiêu |
| --- | --- |
| TLS/trust | Bảo vệ kết nối, xác minh peer |
| mTLS khi cần | Xác thực client certificate |
| RSocket authentication | Xác định caller identity theo setup/per-request policy |
| Route authorization | `inventory.reserve` chỉ cho service role phù hợp |
| Domain authorization | Caller được phép giữ SKU/warehouse/tenant đó |
| Limits | Payload size, streams, QPS, concurrency |
| Schema validation | Reject untrusted/unsupported data |
| Audit/redaction | Log quyết định mà không lộ secrets |

### 18.2. Metadata authentication khác HTTP headers

Spring Security có integration cho RSocket authentication/authorization trong các versions hỗ trợ. Nhưng một `@Header("Authorization")` hay JSON field `tenantId` **không tự kích hoạt Spring Security filter của MVC/HTTP**.

Cần cấu hình RSocket security interceptor/metadata support và test:

- No credentials → reject.
- Invalid/expired credentials → reject.
- Authenticated caller nhưng thiếu route permission → forbidden.
- Tenant A cố reserve SKU của tenant B → reject ở service.
- Raw `tenantId` metadata không được override authenticated identity.
- Valid service identity được route tới đúng business policy.

Một policy minh họa:

~~~text
inventory.stock.get     -> authenticated read scope
inventory.stock.watch   -> read scope + tenant stream quota
inventory.reserve       -> service role INVENTORY_RESERVE
inventory.batch.reserve -> batch role + per-command ownership check
~~~

Đây là yêu cầu business policy, không phải DSL config code hoàn chỉnh. Tùy Spring Security/RSocket version, API bảo mật khác nhau; tham chiếu docs chính thức và test actual runtime.

### 18.3. TLS và secrets hygiene

- Verify CA chain và hostname, không tắt TLS validation trong production.
- Mọi credentials/private keys lấy từ secret manager và có rotation policy.
- Tránh log bearer token/Basic credentials, raw PII payloads.
- Bảo đảm LB/proxy hỗ trợ long-lived TCP/WebSocket connections.
- Không đưa raw Authorization/tenant/email vào metrics tags.
- Giới hạn JSON nesting/size để chống denial of service.

## 19. Versioning route, DTO và metadata

Route là contract. Một thay đổi additive field có thể phá reader cũ strict, và reader mới có thể không đọc được payload lịch sử nếu field mới bắt buộc.

V1:

~~~json
{"sku":"SKU-A"}
~~~

V2:

~~~json
{"sku":"SKU-A","warehouseId":"WH-1"}
~~~

### 19.1. Compatibility matrix

| Reader | Writer | Cần kiểm tra |
| --- | --- | --- |
| V1 | V1 | Baseline |
| V2 | V1 | New reader nhận old payload |
| V1 | V2 | Old reader nhận extra field |
| V2 | V2 | New path |
| V3 | V1 | Historical replay/transitive support |

`@MessageMapping` không tự version schema. Có thể chọn route mới `inventory.stock.get.v2`, schemaVersion trong envelope, data MIME version hoặc adapter; định nghĩa rõ chính sách.

### 19.2. Event/command identity khác schemaVersion

~~~json
{
  "operationId": "K-100",
  "schemaVersion": 2,
  "aggregateVersion": 17,
  "orderId": "ORD-100",
  "sku": "SKU-A",
  "quantity": 2
}
~~~

- `operationId`: logical business command identity, dùng idempotency.
- `schemaVersion`: cách deserialize và validate payload.
- `aggregateVersion`: domain ordering/version conflict.
- RSocket stream ID: identity trong transport/session, **không dùng làm dedupe key**.

Khi upgrade schema, không vô tình tạo operationId mới cho cùng command đang retry trong outbox.

### 19.3. Thay đổi semantics nguy hiểm

Nếu `availableQuantity` V1 nghĩa là “physical stock” còn V2 nghĩa là “available-to-promise”, giữ nguyên field name là semantic breaking change dù JSON vẫn parse. Cần field/route mới, versioning và migration.

### 19.4. Unknown versions

Responder không nên deserialize arbitrary version như DTO hiện tại rồi mặc định áp nghiệp vụ. Với unsupported version, reject/park theo contract, giữ audit/operationId và alerts; không retry nóng cùng payload chưa được hỗ trợ.

## 20. Kiểm thử responder

Unit test gọi Java method trực tiếp **không** kiểm tra route metadata, TCP connection, JSON codec, RSocket frame type, cancellation và error mapping.

### 20.1. Testing pyramid

| Tầng | Cần chứng minh |
| --- | --- |
| Domain unit | Validation, business invariants |
| Responder unit | Handler gọi đúng service/Mono/Flux |
| Contract test | DTO v1/v2, missing/null/unknown fields |
| RSocket integration | Actual route, MIME, request-response/stream/channel |
| SQL Testcontainers | Unique operationId, transaction, rollback, receipt |
| Fault injection | Response lost sau COMMIT, reconnect/cancellation |
| Security integration | Authentication, authorization, tenant isolation |
| Load/soak | Backpressure, stream count, Hikari/HTTP limits |

### 20.2. StepVerifier unit test

~~~java
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class InventoryResponderUnitTest {

    @Test
    void returnsStock() {
        InventoryReadService fake =
                sku -> Mono.just(
                        new StockAvailability(sku, 8, 5));

        InventoryRSocketResponder responder =
                new InventoryRSocketResponder(fake);

        StepVerifier.create(
                responder.getStock(new StockQuery("SKU-A")))
                .expectNext(new StockAvailability("SKU-A", 8, 5))
                .verifyComplete();
    }
}
~~~

Test này chỉ xác minh method logic. Nó không chứng minh `@MessageMapping("inventory.stock.get")` đã được đăng ký hoặc codec JSON đúng.

### 20.3. RSocket TCP integration test

Ví dụ **test skeleton** với port test dành riêng:

~~~java
import java.time.Duration;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.messaging.rsocket.RSocketRequester;
import reactor.test.StepVerifier;

@SpringBootTest(properties = {
        "spring.rsocket.server.port=7001",
        "spring.rsocket.server.transport=tcp"
})
class InventoryRSocketIntegrationTest {

    @Autowired
    RSocketRequester.Builder builder;

    @Test
    void routesAndDecodesRequestResponse() {
        RSocketRequester requester = builder
                .connectTcp("localhost", 7001)
                .block(Duration.ofSeconds(5));

        StepVerifier.create(
                requester.route("inventory.stock.get")
                        .data(new StockQuery("SKU-A"))
                        .retrieveMono(StockAvailability.class))
                .assertNext(result ->
                        org.junit.jupiter.api.Assertions
                                .assertEquals("SKU-A", result.sku()))
                .verifyComplete();
    }
}
~~~

Cần application context chứa responder và fake/real `InventoryReadService`. Port 7001 có thể conflict trong CI song song: triển khai thật nên dùng random/isolation và lấy actual bound port theo Spring Boot version. Cần đóng requester/connection sau test, không leak sockets. Snippet chỉ là skeleton, **chưa chứng minh SQL hoặc durable business behavior**.

### 20.4. Test Request-stream với demand/cancel

~~~java
import reactor.test.StepVerifier;

StepVerifier.create(
        requester.route("inventory.stock.watch")
                .data(new StockWatchRequest("SKU-A"))
                .retrieveFlux(StockUpdate.class),
        0)
    .thenRequest(2)
    .expectNextCount(2)
    .thenCancel()
    .verify();
~~~

Test cần một nguồn giả có ít nhất 2 updates và có instrumentation xác nhận subscription được cleanup khi cancel. Đừng dùng `Thread.sleep(100)` để đo “đã nhận đủ” nếu có thể dùng `StepVerifier`/latches với timeout.

### 20.5. Test Request-channel partial failure

~~~text
Given K1, K2, K3 command stream
And server commits K1 and K2
When network connection drops before K2 receipt
Then requester records K2 UNKNOWN
And target database has exactly one reservation per K1, K2
When requester reconnects and retries K2 using same key
Then server returns stored K2 receipt
And total business side effects remain unchanged
~~~

Để test deterministic, dùng `CountDownLatch`/commit markers hoặc fault proxy thay vì sleep ngẫu nhiên.

### 20.6. Test FNF semantics

Một test `send()` hoàn thành không đủ. Cần chứng minh:

- Responder nhận event được route đúng.
- Nếu audit không bền, consumer behavior khi DB fail được document.
- Nếu audit bắt buộc bền, dùng outbox/broker/receipt; không ngộ nhận send completion.
- Lỗi JSON conversion trước method được xử lý đúng.

### 20.7. Test matrix bốn tương tác

| Interaction | Happy path | Failure/edge path |
| --- | --- | --- |
| Request-response | DTO và result đúng | Unknown route, validation, response lost after commit |
| Fire-and-forget | Routed to handler | Receiver fail after send, no receipt |
| Request-stream | Backpressure/demand | Slow reader, cancel, reconnect, missed updates |
| Request-channel | Input/output mapping | Partial commits, duplicate IDs, reordering |
| Cross-cutting | Security, codecs | Untrusted metadata, MIME mismatch, overload |

### 20.8. JDBC/Redis/HTTP failure tests

Một RSocket endpoint có thể xử lý transport hoàn hảo nhưng integration fail:

- Hikari connection timeout.
- SQL deadlock/optimistic version conflict.
- Redis cache stampede.
- Partner HTTP 429/503.
- Outbox insert fail sau business mutation.
- Connection lost sau SQL COMMIT.
- Kafka/Rabbit publisher confirm lost.

Dùng PostgreSQL Testcontainers và fault proxies/HTTP stubs; kiểm tra business state thực sau lỗi, không chỉ `StepVerifier.expectError()`.

## 21. Observability và vận hành

### 21.1. Tín hiệu cần phân biệt

| Signal | Tầng | Ý nghĩa |
| --- | --- | --- |
| Active RSocket connections | Transport | Peer connectivity |
| Active request-response | Responder | In-flight calls |
| Active request-stream/channel | Responder | Subscriptions, memory |
| Route latency p95/p99 | Messaging | Slow routes |
| Route errors by category | Messaging | Mapping/validation/SQL/network |
| Cancellation rate | Stream | Slow/disconnected clients |
| Reconnect attempts | Client | Network instability |
| Keepalive failures | Transport | Connection liveness |
| Hikari active/pending | Database | JDBC bottleneck |
| HTTP downstream 429/503 | Adapter | Partner overload |
| Outbox pending oldest age | Workflow | Durable intent backlog |
| Duplicate operationId | Business | Replay deduped |
| Business confirmed count | Domain | Actual commit |
| Unsupported schema version | Contract | Writer/reader drift |

Actuator/Micrometer/Reactor Netty có metrics/observation capabilities tùy version và cấu hình, nhưng không assume tất cả bảng trên tự được export. Business confirmation, outbox age và idempotency cần instrumentation rõ.

### 21.2. Metrics cardinality

Tags hợp lý:

~~~text
route=inventory.reserve
transport=tcp
outcome=confirmed|rejected|unknown
error_type=validation|auth|db|network
schema_version=1|2
~~~

Không đưa `operationId`, `sku`, `customerId`, email, raw payload hoặc bearer token vào Prometheus labels. Correlation IDs có thể vào structured logs theo policy redaction/access control.

### 21.3. Trace nhiều tầng

~~~text
RSocket inventory.reserve
  -> metadata auth/authorization
  -> payload decode + validation
  -> concurrency admission
  -> JDBC transaction (reservation + receipt)
  -> COMMIT
  -> RSocket response encode/send
~~~

Nếu có outbox:

~~~text
  -> outbox insert in same SQL transaction
  -> relay after COMMIT
  -> Kafka/Rabbit/HTTP partner
  -> consumer inbox + business commit
~~~

Transport completion và business completion là **hai tín hiệu khác nhau**; dashboard phải hiển thị rõ.

## 22. Runbook khi @MessageMapping không hoạt động

| Triệu chứng | Nguyên nhân thường gặp | Bước kiểm tra |
| --- | --- | --- |
| TCP connection refused | Không mở port/RSocket server chưa start | Starter, `spring.rsocket.server.port`, startup logs |
| Connect được nhưng unknown route | Sai route/bean không scan | `@Controller`, `@MessageMapping`, spelling |
| Không decode được DTO | MIME/codecs/schema mismatch | `RSocketStrategies`, payload fixtures |
| Missing field gây lỗi | Required/null/default không tương thích | Contract/Bean Validation |
| `Mono` không chạy | Không có subscriber | Trả publisher qua outer pipeline |
| Event loop latency tăng | Blocking JDBC/HTTP trực tiếp | Thread profiles, offload |
| Hikari timeout | Too many DB calls/long transactions | Pool active/pending, SQL locks |
| Client timeout nhưng DB đã commit | Response lost | Query receipt, operationId |
| Reservation xử lý hai lần | Retry sinh key mới | SQL UNIQUE/idempotency |
| FNF “success” nhưng audit không ghi | Không có application receipt | Durable handoff |
| Flux memory tăng | Unbounded buffer/streams | Bounded concurrency/overflow |
| Cancel nhưng resources vẫn giữ | Thiếu cleanup | `doFinally`, resource ownership |
| Stream mất updates sau reconnect | Không có replay source | Durable log/cursor |
| Channel replies đảo thứ tự | `flatMap` hoặc parallel writes | `concatMap`/version guard |
| TLS/auth fail | CA, hostname, credentials, route ACL | Transport/security integration |
| Idle disconnect | LB/proxy timeout, keepalive | Keepalive, network config |
| Reconnect storm | Retry không backoff/jitter | Client admission strategy |
| Rollback code không đọc schema mới | Data evolution thiếu plan | Versioned route/adapter |
| Missing metrics | Instrumentation chưa bật | Actuator/Micrometer/custom counters |

### 22.1. Thứ tự điều tra

1. Kiểm tra transport/port/TLS/connection setup.
2. Xem route metadata phía requester.
3. Xác nhận `@Controller` bean và `@MessageMapping` mapping đã đăng ký.
4. Kiểm tra data MIME, codecs, schemaVersion và validation.
5. Xác minh authentication/tenant authorization.
6. Đo event-loop, scheduler, Hikari, HTTP partner capacity.
7. Phân biệt request attempted, responder received, database COMMIT và response received.
8. Nếu timeout, dùng stable operationId tra cứu trước khi retry.
9. Kiểm tra active subscriptions, cancellation và buffer pressure.
10. Tái hiện bằng test có real TCP connection/fault injection.

Không xóa outbox/receipts hoặc tự tạo key mới chỉ để làm queue hết pending.

## 23. Những anti-pattern thường gặp

| Anti-pattern | Vì sao sai? | Hướng sửa |
| --- | --- | --- |
| Coi `@MessageMapping` là HTTP `@PostMapping` | Khác routing/transport/errors | Dùng RSocket route metadata |
| Không bật server port | Responder không có listener | Boot RSocket config |
| Chỉ gọi Java method trong unit test | Không kiểm tra mapping/codecs | Real RSocket integration test |
| Dùng FNF cho business cần receipt | Caller không biết target commit | Request-response + idempotency |
| JDBC call trước `Mono.just` | Block event-loop | `Mono.fromCallable` + boundedElastic |
| Dùng `Schedulers.parallel()` cho blocking SQL | Nghẽn CPU workers | Scheduler/resource boundary phù hợp |
| `onBackpressureBuffer()` vô hạn | OOM | Bounded buffer/durable log |
| Một SQL transaction cho stream vô hạn | Chiếm JDBC connection/locks | Per-item transactions |
| Dùng RSocket stream ID để dedupe | Transport identity không ổn định | Business operationId |
| `timeout -> retry with new UUID` | Nhân đôi side effect | UNKNOWN + stable ID/reconciliation |
| Assume `send()` là business ACK | Không có application reply | Durable result/status |
| Assume reconnect tự hồi phục stream history | Không có durable replay | Cursor/event log |
| Tăng request streams không giới hạn | DB/HTTP downstream quá tải | Quotas/bulkhead |
| `flatMap` rồi mong strict output order | Concurrent results reorder | `concatMap`/version guard |
| Lấy `tenantId` metadata làm trust | Có thể giả mạo | Authenticated principal + ACL |
| Tắt certificate validation | MITM/credential leak | TLS trust/hostname verification |
| Log full payload/token | Security/privacy leak | Redaction |
| Xem Mono complete là downstream all done | Có thể chỉ accepted | Business receipt/status |
| Không handle cancel | Resource leaks | Cleanup/lifecycle ownership |
| Auto retry every error | Retry storm/permanent errors | Error taxonomy + retry budget |

## 24. Checklist production

- [ ] RSocket được chọn vì cần request/stream/channel thực tế, không chỉ vì sự mới lạ.
- [ ] Spring Boot/Reactor/RSocket Java versions tương thích qua BOM.
- [ ] TCP/WebSocket transport, port, TLS, load balancer và readiness phù hợp.
- [ ] `@Controller` được scan; các `@MessageMapping` routes không trùng/xung đột.
- [ ] Route, DTO/MIME/schemaVersion/error semantics được công bố như contract.
- [ ] Responder/requester khớp interaction model: RR, FNF, stream, channel.
- [ ] FNF không dùng cho command cần business receipt nếu không có durable handoff.
- [ ] Requester quản lý connection, keepalive, reconnect/backoff, shutdown.
- [ ] Payload codecs/metadata extraction được cấu hình và test thật.
- [ ] Authentication/authorization theo route và domain resources, không tin tenantId do caller tự gắn.
- [ ] Bean Validation và malformed payload/error mapping được kiểm chứng.
- [ ] Không blocking SQL/HTTP/Redis trực tiếp trên event-loop.
- [ ] Blocking adapters có boundedElastic/worker và admission/bulkhead giới hạn.
- [ ] Hikari, HTTP pool, Redis, broker và số replicas nằm trong capacity budget.
- [ ] Streams có demand, bounded buffers, max subscribers và cancellation cleanup.
- [ ] Channel có per-item transaction, partial failure và replay policy.
- [ ] Business commands có stable operationId và SQL unique constraint.
- [ ] Timeout/response lost sau COMMIT được xử lý thành UNKNOWN/reconciliation.
- [ ] Outbox/inbox hoặc broker bền vững nếu cần recover sau process crash.
- [ ] Retry có deadline, attempts giới hạn, backoff/jitter và phân loại lỗi.
- [ ] Schema evolution test old/new writer-reader, replay và rollback.
- [ ] Real RSocket connection tests cho 4 interaction models và route mapping.
- [ ] PostgreSQL Testcontainers test transaction/idempotency/unique race.
- [ ] Fault injection test mất kết nối sau commit, cancel và reconnect.
- [ ] Metrics tách transport sends, route errors, business COMMIT và outbox lag.
- [ ] Không lộ tokens, PII, password hay high-cardinality IDs trong metrics/logs.

**Ghi nhớ:** Cấu hình responder RSocket trong Spring Boot thường bắt đầu bằng `@Controller` và `@MessageMapping("route")`, kết hợp `Mono`/`Flux` để thể hiện bốn kiểu tương tác. Những annotation này giúp **nhận và phản hồi message**, nhưng không thay được **hợp đồng dữ liệu, giới hạn tài nguyên, transaction, outbox/inbox, idempotency, xử lý kết quả UNKNOWN và cơ chế quan sát**. Một responder production cần được kiểm thử cả happy path và các cửa sổ lỗi trước/sau khi hệ thống đích commit.

## Tài liệu tham khảo

- [Spring Framework — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html): kiến trúc requester/responder.
- [Spring Framework — Annotated RSocket Responders](https://docs.spring.io/spring-framework/reference/rsocket/rsocket-annotated.html): `@MessageMapping`, signatures, routing.
- [Spring Framework — RSocketRequester](https://docs.spring.io/spring-framework/reference/rsocket/rsocket-requester.html): RR, FNF, stream, channel.
- [Spring Framework — RSocketStrategies](https://docs.spring.io/spring-framework/reference/rsocket/rsocket-strategies.html): codecs, metadata, MIME.
- [Spring Boot — RSocket](https://docs.spring.io/spring-boot/reference/messaging/rsocket.html): server auto-config, TCP/WebSocket.
- [RSocket Protocol Specification](https://rsocket.io/about/protocol/): RSocket interaction models, frames, demand.
- [RSocket Java](https://github.com/rsocket/rsocket-java): transport/connector implementation.
- [Project Reactor — Reference](https://projectreactor.io/docs/core/release/reference/): `Mono`, `Flux`, schedulers, backpressure.
- [Project Reactor — Testing](https://projectreactor.io/docs/test/release/reference/): `StepVerifier`, cancellation tests.
- [Spring Security — RSocket](https://docs.spring.io/spring-security/reference/reactive/integrations/rsocket.html): authentication/authorization.
- [Spring Framework — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html): JDBC/reactive transaction boundaries.
- [Spring Integration — Reference](https://docs.spring.io/spring-integration/reference/): message channels/adapters.
- [Spring Boot — SQL Databases](https://docs.spring.io/spring-boot/reference/data/sql.html): JDBC, HikariCP, pool sizing.
- [Testcontainers — PostgreSQL](https://java.testcontainers.org/modules/databases/postgres/): SQL transaction tests.
- [Testcontainers — Toxiproxy](https://java.testcontainers.org/modules/toxiproxy/): network fault injection.
- [Enterprise Integration Patterns — Idempotent Receiver](https://www.enterpriseintegrationpatterns.com/patterns/messaging/IdempotentReceiver.html): duplicate-safe processing.
- [Transactional Outbox Pattern](https://microservices.io/patterns/data/transactional-outbox.html): durable intent + retry after commit.
