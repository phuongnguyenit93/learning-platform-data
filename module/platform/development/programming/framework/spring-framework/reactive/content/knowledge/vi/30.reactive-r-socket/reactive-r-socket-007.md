# Thiết lập kết nối, vòng đời và xử lý lỗi RSocket trong Spring Framework reactive

## 1. Mục tiêu bài học

RSocket là giao thức truyền thông hai chiều (duplex), hỗ trợ nhiều request trên cùng một kết nối và truyền tín hiệu backpressure của Reactive Streams qua mạng. Trong Spring, `RSocketRequester` tạo các request từ client hoặc từ server; `@MessageMapping` và `@ConnectMapping` là các điểm xử lý phía responder.

Một lời gọi RSocket không đơn giản là “mở socket rồi gửi JSON”. Ứng dụng phải quản lý:

- Chọn transport TCP hoặc WebSocket và xác định endpoint.
- Thương lượng `SETUP` frame: version, MIME type, metadata, keepalive và khả năng tùy chọn.
- Tái sử dụng kết nối và thiết lập lại khi kết nối bị mất.
- Vòng đời từng request: hoàn tất, hủy, lỗi, timeout.
- Vòng đời requester khi ứng dụng shutdown: ngừng yêu cầu mới và giải phóng transport.
- Phân biệt lỗi TCP/TLS, setup rejection, lỗi protocol và lỗi nghiệp vụ.
- Retry/backoff có kiểm soát, tránh gửi lại thao tác không idempotent.
- Log/metrics/trace an toàn, bảo vệ credential và tài nguyên.

Bài này sử dụng Java 17+, Spring Boot 3.3.x, Spring Framework 6.1/6.2 và RSocket Java 1.1.x làm nền tảng. Ví dụ Spring Boot 3.3.5 được trình bày đầy đủ để có thể chạy bằng Maven.

**Kết quả mong muốn:** hiểu rõ ranh giới **connection** so với **request stream**; cấu hình được `RSocketRequester`; biết khi nào client tự tạo kết nối lại và khi nào ứng dụng phải quyết định retry; có kiểm thử request-response, request-stream, channel và application error.

## 2. RSocket khác HTTP request/response ở đâu?

HTTP truyền thống thường gắn một request vào một response. RSocket hỗ trợ bốn interaction model sau khi một kết nối được thiết lập.

| Mô hình | Hướng dữ liệu | RSocketRequester thường dùng |
|---|---|---|
| Request-Response | 1 request → 0/1 response | `retrieveMono(T.class)` |
| Request-Stream | 1 request → nhiều response | `retrieveFlux(T.class)` |
| Request-Channel | Nhiều request payload ↔ nhiều response | `data(Publisher, Class)` + `retrieveFlux(T.class)` |
| Fire-and-Forget | Gửi một request, không chờ response payload | `send()` |

Tương ứng:

```text
Request-Response
  Requester -- REQUEST_RESPONSE --> Responder
  Requester <-- PAYLOAD ---------- Responder

Request-Stream
  Requester -- REQUEST_STREAM ----> Responder
  Requester <-- PAYLOAD(1..n) ---- Responder

Request-Channel
  Requester -- REQUEST_CHANNEL --> Responder
  Requester <-- PAYLOAD ---------- Responder
  Requester -- PAYLOAD ----------> Responder

Fire-and-Forget
  Requester -- REQUEST_FNF -------> Responder
```

Không có nghĩa RSocket bảo đảm lưu trữ bền vững hay xử lý exactly-once. Fire-and-Forget chỉ nói rằng requester không nhận một response payload theo mô hình giao thức; không có xác nhận nghiệp vụ rằng dữ liệu đã commit vào database.

Sau khi kết nối đã mở, hai phía về mặt protocol gần như đối xứng: cả hai đều có thể chủ động gửi request. Vì thế Spring phân biệt *requester* và *responder* thay vì cố định client/server cho từng request.

### Những lợi ích liên quan đến vòng đời

- Một kết nối có thể đồng thời mang nhiều logical streams.
- Mỗi stream có identity và tín hiệu complete/error/cancel riêng.
- Request-Stream/Channel truyền demand qua `REQUEST_N`.
- Keepalive giúp phát hiện peer không còn phản hồi.
- Một số tính năng nâng cao như leasing/resume cần được hỗ trợ và cấu hình ở cả hai phía.

Không tự đồng nhất backpressure với độ bền dữ liệu hoặc khả năng khôi phục request đã bị mất.

## 3. Các bước thiết lập kết nối RSocket

Sơ đồ thời gian:

```text
Client / Requester                      Server / Responder
        |                                        |
        |---- Resolve DNS, TCP connect -------->|
        |       (hoặc WebSocket upgrade)         |
        |---- RSocket SETUP -------------------->|
        |      protocol version                  |
        |      data + metadata MIME types        |
        |      keepalive / max lifetime          |
        |      optional setup data/metadata      |
        |                                        |
        |<--- Accept hoặc ERROR (setup) ---------|
        |                                        |
        |---- REQUEST_RESPONSE/STREAM/etc. ----->|
        |<--- PAYLOAD hoặc ERROR ----------------|
        |                                        |
        |<---> KEEPALIVE (theo chính sách) ------|
        |                                        |
        |---- dispose/transport close ---------->|
```

### 3.1. Giai đoạn transport

RSocket chạy trên TCP, WebSocket hoặc các byte-stream transports phù hợp. Với TCP, kết nối có thể là:

```text
127.0.0.1:7000
```

Với WebSocket, endpoint có URI, ví dụ:

```text
ws://localhost:8080/rsocket
wss://gateway.example.com/rsocket
```

Transport phải kết nối được trước khi trao đổi frame RSocket. Lỗi DNS, routing, firewall, TLS handshake hoặc WebSocket HTTP upgrade nằm ở giai đoạn này.

RSocket TCP và RSocket over WebSocket đều dùng request/response models như nhau ở tầng protocol, nhưng đường đi mạng, proxy, port, TLS và observability có thể khác nhau.

### 3.2. `SETUP` frame

Sau khi transport sẵn sàng, requester gửi frame `SETUP` với các tham số. Một số trường:

- Phiên bản giao thức.
- `dataMimeType` và `metadataMimeType` dùng trên kết nối.
- Keepalive interval và max lifetime.
- Setup data và setup metadata (nếu có).
- Thông tin tùy chọn cho lease/resume.

Metadata có thể chứa route hoặc thông tin dùng để xác thực connection. Server có thể chấp nhận hoặc từ chối setup. Nếu setup bị từ chối, không có chuyện “mở kết nối thành công nên mọi request chắc chắn hợp lệ”.

### 3.3. Sau SETUP

Các request stream được multiplex trên kết nối. Một lỗi ở một request stream có thể chỉ kết thúc stream đó, trong khi một `ERROR` ở connection level hoặc transport disconnect có thể ảnh hưởng tất cả request đang dùng kết nối.

Vì vậy, khi debug cần xác định lỗi ở **transport**, **connection SETUP**, **individual stream** hay **application handler**.

## 4. Tạo requester bằng `RSocketRequester.Builder`

Spring cung cấp `org.springframework.messaging.rsocket.RSocketRequester`. Spring Boot khi có starter RSocket tự cấu hình `RSocketRequester.Builder` và các codec. Builder là stateful và được cung cấp theo scope prototype để mỗi injection point có cấu hình riêng.

### 4.1. Kết nối TCP

```java
RSocketRequester requester = requesterBuilder
        .tcp("localhost", 7000);
```

Đây là API hiện đại trong Spring Framework 5.3+ và 6.x. `tcp(...)` trả về requester; nó **không bắt buộc mở kết nối ngay lập tức**. Khi một request thực sự được subscribe, một shared connection được tạo theo nhu cầu.

Ví dụ:

```java
Mono<String> greeting = requester.route("hello")
        .data("Mai")
        .retrieveMono(String.class);
```

Publisher chưa được subscribe thì không có bảo đảm request đã được gửi. Trong service reactive hãy `return greeting` hoặc compose vào pipeline khác; không gọi `subscribe()` tùy tiện.

### 4.2. Kết nối WebSocket

```java
URI endpoint = URI.create("ws://localhost:8080/rsocket");

RSocketRequester requester = requesterBuilder
        .websocket(endpoint);
```

Bên server phải bật RSocket over WebSocket và cấu hình mapping path khớp `/rsocket`. Không nhầm WebSocket thuần với RSocket chạy trên WebSocket: cùng dùng WebSocket transport nhưng payload ở đây là RSocket frames, không phải JSON chat thuần.

### 4.3. Tránh các ví dụ API cũ

Một số hướng dẫn Spring 5.2 dùng `connectTcp(...)` hoặc `connectWebSocket(...)` trả `Mono<RSocketRequester>` và gọi `.block()`. Với Spring Framework 6.1/6.2, ưu tiên `tcp(...)` và `websocket(...)` như trên. Không copy máy móc các ví dụ cũ sang Boot 3.x.

### 4.4. Reuse requester

Một requester tạo bằng `.tcp(...)` hoặc `.websocket(...)` được thiết kế để phục vụ nhiều request đồng thời qua shared connection. Thay vì dựng requester trong mỗi lần gọi service, nên giữ một requester theo một endpoint và trust policy.

Ví dụ:

```java
@Service
public final class InventoryRequester {

    private final RSocketRequester requester;

    public InventoryRequester(RSocketRequester.Builder builder) {
        this.requester = builder.tcp("inventory.internal", 7000);
    }

    public Mono<String> status(String sku) {
        return requester.route("inventory.status")
                .data(sku)
                .retrieveMono(String.class);
    }

    @PreDestroy
    public void stop() {
        requester.dispose();
    }
}
```

Đoạn trên minh họa một service khi endpoint đã biết. `@PreDestroy` cần import `jakarta.annotation.PreDestroy`. Production nên đưa host/port vào configuration, không hardcode.

## 5. Cấu hình MIME type, route và setup metadata

RSocket có hai vùng dữ liệu:

1. **Data**: payload nghiệp vụ, ví dụ JSON object.
2. **Metadata**: routing, authentication hoặc context khác.

MIME type được thỏa thuận trong `SETUP` và ảnh hưởng codec ở cả hai phía.

```java
RSocketRequester requester = builder
        .dataMimeType(MimeTypeUtils.APPLICATION_JSON)
        .tcp("localhost", 7000);
```

`MimeTypeUtils.APPLICATION_JSON` nằm trong package `org.springframework.util`. Nếu client dùng JSON, server phải có codec phù hợp. Spring Boot starter cung cấp tích hợp codec của Spring; với cấu hình tự tạo ngoài Boot, phải tự chuẩn bị `RSocketStrategies`.

### 5.1. Route trong từng request

```java
Mono<Order> order = requester
        .route("orders.lookup")
        .data("order-42")
        .retrieveMono(Order.class);
```

Route là metadata được dùng để tìm `@MessageMapping` phía responder. Nó không phải HTTP URL path, không chứa scheme/host và không phải TCP port.

### 5.2. Setup route

Có thể đặt setup route và setup data:

```java
RSocketRequester requester = builder
        .dataMimeType(MimeTypeUtils.APPLICATION_JSON)
        .setupRoute("client.connect")
        .setupData("client-app")
        .tcp("localhost", 7000);
```

Phía server có thể xử lý setup bằng `@ConnectMapping("client.connect")` và đọc setup payload nếu contract cho phép. Nếu server không có route setup tương ứng, cần kiểm thử cách setup được xử lý; đừng thêm setup route tùy ý.

### 5.3. Composite metadata

Khi cần gửi nhiều metadata entry độc lập (route, JWT hoặc trace context), RSocket thường sử dụng composite metadata. Nếu tự cấu hình metadata MIME type, phải bảo đảm hai bên thống nhất format và Spring có encoder/decoder tương ứng.

Không đặt token vào log hoặc in ra setup metadata. Nếu token được gắn ở connection level, cần có chính sách đối với token hết hạn và authorization của từng request.

## 6. Cấu hình server với Spring Boot

Spring Boot auto-configure RSocket server khi có `spring-boot-starter-rsocket` và cấu hình phù hợp.

### 6.1. TCP độc lập

Trong `application.properties`:

```properties
spring.rsocket.server.port=7000
spring.rsocket.server.transport=tcp
```

Server TCP chạy trên cổng RSocket riêng. Không cần WebFlux HTTP server chỉ để chạy TCP RSocket.

### 6.2. WebSocket tích hợp vào WebFlux server

```properties
spring.rsocket.server.transport=websocket
spring.rsocket.server.mapping-path=/rsocket
server.port=8080
```

Khi ứng dụng là WebFlux reactive và dùng Reactor Netty, RSocket over WebSocket có thể gắn vào HTTP server. Trong kiểu triển khai này thường **không** đặt riêng `spring.rsocket.server.port`, vì transport chia sẻ HTTP server.

### 6.3. Hai phương án có gì khác?

| Tiêu chí | TCP | WebSocket |
|---|---|---|
| Cách truy cập | `host:port` | `ws://` hoặc `wss://` URI |
| Cấu hình chính | `spring.rsocket.server.port` | `transport=websocket`, `mapping-path` |
| Tích hợp reverse proxy HTTP | Cần proxy hỗ trợ TCP | Thường thuận lợi qua HTTP gateway có WebSocket upgrade |
| TLS | Theo transport/TLS config | Có thể dùng WSS/TLS ở server hoặc ingress |
| Handler nghiệp vụ | `@MessageMapping` | `@MessageMapping` |

Không chọn WebSocket chỉ vì dự án khác có WebSocket endpoint. RSocket over WebSocket là giao thức RSocket bên trên WebSocket, không tự tương thích với client dùng WebSocket message văn bản tùy ý.

## 7. Responder: `@MessageMapping` và `@ConnectMapping`

`RSocketMessageHandler` ánh xạ route tới annotated methods.

```java
@Controller
public class GreetingResponder {

    @MessageMapping("hello")
    public Mono<String> hello(String name) {
        return Mono.just("Xin chào, " + name);
    }
}
```

RSocket requester:

```java
requester.route("hello")
        .data("An")
        .retrieveMono(String.class);
```

### 7.1. Handler request-stream

```java
@MessageMapping("numbers")
public Flux<Integer> numbers(Integer count) {
    return Flux.range(1, count);
}
```

Client:

```java
Flux<Integer> numbers = requester.route("numbers")
        .data(3)
        .retrieveFlux(Integer.class);
```

Đối với server streaming, demand từ subscriber được thể hiện qua protocol. Tuy nhiên, một handler tự tạo queue không giới hạn, gọi `collectList()` hoặc dùng producer không hỗ trợ backpressure vẫn có thể giữ nhiều dữ liệu trong memory.

### 7.2. Handler request-channel

```java
@MessageMapping("upper")
public Flux<String> upper(Flux<String> words) {
    return words.map(word -> word.toUpperCase(Locale.ROOT));
}
```

Client gửi một stream:

```java
Flux<String> result = requester.route("upper")
        .data(Flux.just("mot", "hai", "ba"), String.class)
        .retrieveFlux(String.class);
```

Cần `java.util.Locale` trong ví dụ. Producer của channel phải tuân theo demand và kết thúc publisher khi không còn dữ liệu.

### 7.3. `@ConnectMapping` chỉ xử lý connection-level event

`@ConnectMapping` có thể xử lý nội dung của `SETUP` frame hoặc `METADATA_PUSH`:

```java
@ConnectMapping("client.connect")
public Mono<Void> onConnect(String applicationName) {
    return validateClientApplication(applicationName);
}
```

`validateClientApplication` là service trả `Mono<Void>` của ứng dụng; code này chỉ minh họa hợp đồng method, không phải một class độc lập.

Các method `@ConnectMapping` chỉ được trả `void` hoặc một async type có cardinality bằng 0 như `Mono<Void>`. Nếu xử lý SETUP trả lỗi, kết nối có thể bị từ chối.

**Cảnh báo:** Không chặn handler `@ConnectMapping` bằng cách chờ chính kết nối đang setup gửi và hoàn thành một request trở lại. Kết nối chưa hoàn tất setup nên có thể tạo vòng phụ thuộc. Việc requester gửi request ngay khi connection setup có thể cần được tách bất đồng bộ theo kiến trúc tương ứng.

## 8. Vòng đời connection khác vòng đời request stream

Hãy phân biệt rõ hai trục thời gian.

### 8.1. Connection lifecycle

```text
NEW
  |
  v
TRANSPORT CONNECT
  |
  v
SETUP
  |
  v
ACTIVE
  |
  +---- multiple request streams
  |
  +---- KEEPALIVE
  |
  v
CLOSED / FAILED / DISPOSED
```

Kết nối có thể được đóng vì:

- Client/server shutdown.
- Network disconnect.
- Keepalive timeout.
- Setup rejection.
- Protocol-level connection error.
- TLS/proxy transport failure.

### 8.2. Stream lifecycle

```text
REQUEST CREATED
     |
     v
SUBSCRIBED / SENT
     |
     +-- PAYLOAD(s) -> onNext
     |
     +-- onComplete
     |
     +-- onError
     |
     +-- CANCEL
```

Một stream request-response trả lỗi validation không nhất thiết đóng toàn bộ connection. Ngược lại, mất connection có thể làm nhiều stream đồng thời phát lỗi/cancel.

**Nguyên tắc vận hành:** retry một stream và tái kết nối transport là hai thao tác khác nhau. Kết nối lại thành công không tự khôi phục mọi request đang chờ trước đó.

## 9. Lazy shared connection và tái kết nối

Với các API builder hiện đại `.tcp(...)` và `.websocket(...)`, Spring xây dựng requester sử dụng `RSocketClient`. Khi request được tạo và subscribe, một shared connection được thiết lập theo nhu cầu.

Spring API mô tả rằng requester có thể dùng connection chung để gửi nhiều request đồng thời, và khi cần thực hiện các request mới, connection có thể được tái thiết lập nếu connection cũ không còn.

```java
RSocketRequester requester = builder.tcp("service", 7000);

Mono<String> call1 = requester.route("hello")
        .data("A")
        .retrieveMono(String.class);

Mono<String> call2 = requester.route("hello")
        .data("B")
        .retrieveMono(String.class);
```

Cả hai publisher có thể sử dụng cùng kết nối. Chúng không tự mở một connection mới cho từng request nếu shared connection còn phù hợp.

### 9.1. Điều gì xảy ra khi server restart?

Ví dụ:

1. Client đã gửi request A trên connection 1.
2. Server bị restart trước khi trả response A.
3. Request A có thể nhận error vì connection đã chết.
4. Khi client gửi request B sau đó, requester có thể mở lại connection để xử lý B.
5. Request A **không tự được replay** chỉ vì B làm connection mới thành công.

Nếu muốn gọi lại A, ứng dụng phải quyết định dựa trên loại request và idempotency.

### 9.2. Không nhầm reconnect với resume

RSocket protocol hỗ trợ session resumption trong những điều kiện và triển khai nhất định, nhưng tính năng này cần được cấu hình phù hợp ở cả hai phía. Đừng suy ra rằng một `RSocketRequester` dùng shared connection đã bật resume, hoặc mọi in-flight stream đều được giữ nguyên sau reconnect.

Nếu use case cần đảm bảo nhận đủ dữ liệu sau ngắt mạng, hãy thiết kế thêm cursor, checkpoint, event offset, message ID hoặc cơ chế replay ở application layer.

## 10. Keepalive và phát hiện kết nối mất

RSocket gửi `KEEPALIVE` frames để phát hiện peer không còn phản hồi. RSocket Java `RSocketConnector.keepAlive(interval, maxLifeTime)` có thể cấu hình từ Spring:

```java
RSocketRequester requester = builder
        .rsocketConnector(connector ->
                connector.keepAlive(
                        Duration.ofSeconds(20),
                        Duration.ofSeconds(90)))
        .tcp("localhost", 7000);
```

`interval` là khoảng thời gian giữa các keepalive frames. `maxLifeTime` là giới hạn thời gian không nhận được tín hiệu hợp lệ từ phía xa trước khi kết luận kết nối đã mất theo cơ chế protocol.

Trong RSocket Java 1.1.5, các giá trị mặc định là 20 giây và 90 giây. Chúng không phải SLA cố định cho mọi hệ thống; hãy lựa chọn theo network topology, load balancer idle timeout, độ trễ và chi phí heartbeat.

### 10.1. Không đặt keepalive quá dày

Keepalive 100 ms với hàng trăm nghìn kết nối tạo rất nhiều frame nhỏ và chi phí scheduling. Ngược lại, timeout quá dài sẽ khiến hệ thống chậm phát hiện peer mất kết nối.

Điều chỉnh cần cân nhắc:

- RTT và jitter mạng.
- Client di động, mạng yếu, NAT.
- Proxy/load balancer idle timeout.
- Chi phí frame và số lượng connection.
- Timeout mà nghiệp vụ có thể chờ.

### 10.2. Keepalive khác request timeout

Kết nối có thể hoàn toàn khỏe nhưng một request cần chờ database 30 giây. Keepalive không thay request timeout. Một request có thể timeout do SLA dù connection vẫn hoạt động bình thường.

Ví dụ:

```java
Mono<String> reply = requester.route("hello")
        .data("An")
        .retrieveMono(String.class)
        .timeout(Duration.ofSeconds(2));
```

Timeout ở đây áp dụng cho publisher request; không cấu hình keepalive của toàn connection.

## 11. Quản lý lifecycle khi ứng dụng shutdown

`RSocketRequester` implement `Disposable`:

```java
requester.dispose();

boolean disposed = requester.isDisposed();
```

`dispose()` yêu cầu đóng connection từ transport bên dưới và thông báo cho subscriber. Khi ứng dụng có một requester lâu dài, nên gắn lifecycle với bean/container.

```java
@Configuration
public class RSocketClientConfig {

    @Bean(destroyMethod = "dispose")
    RSocketRequester pricingRequester(RSocketRequester.Builder builder) {
        return builder.tcp("pricing.internal", 7000);
    }
}
```

Spring sẽ gọi `dispose()` khi bean bị hủy. Đây là ví dụ tích hợp lifecycle bean, không phải yêu cầu tạo một requester mới mỗi lần gọi.

Nếu ứng dụng tự quản lý requester ngoài Spring bean, dùng `@PreDestroy` hoặc đóng qua shutdown hook ở nơi tạo requester.

### 11.1. Sau dispose thì sao?

Sau khi dispose, không tái sử dụng requester cho traffic mới. Nếu cần khởi động lại một client adapter, tạo requester mới theo lifecycle mới; đừng coi `dispose()` là một lần tạm mất network có thể tự retry lại vô hạn.

### 11.2. Hủy stream

Trong Reactor, subscriber có thể cancel một request stream. Cancellation được truyền qua publisher và, khi protocol cho phép, có thể tạo `CANCEL` frame. Tuy nhiên, phía responder có thể đã bắt đầu side effect trước khi nhận cancel; cancel không tương đương rollback giao dịch.

Đối với service xử lý file/database, cần xem cancellation cleanup và transaction semantics riêng.

## 12. Phân loại lỗi RSocket theo tầng

Lỗi cần được phân loại để chọn hành vi đúng.

| Tầng | Ví dụ | Ý nghĩa |
|---|---|---|
| DNS/TCP/TLS/WebSocket | Không resolve, refused, timeout, TLS handshake fail, WebSocket upgrade fail | Transport chưa sẵn sàng |
| SETUP | `InvalidSetupException`, `RejectedSetupException`, `UnsupportedSetupException` | Không chấp nhận phiên RSocket / tham số setup |
| Connection | `ConnectionErrorException`, `ConnectionCloseException` | Kết nối bị kết thúc |
| Request stream | `ApplicationErrorException`, `RejectedException`, `CanceledException`, `InvalidException` | Một tương tác cụ thể gặp lỗi |
| Payload codec | Decode JSON/CBOR thất bại | Body không hợp lệ hoặc codec MIME không khớp |
| Application | Domain rule, database, permission, timeout | Xử lý nghiệp vụ hoặc hạ tầng bên dưới |
| Reactor | `TimeoutException`, cancellation, retry exhausted | Chính sách pipeline/client |

Một số exception RSocket protocol nằm trong `io.rsocket.exceptions`; chúng thể hiện error code tương ứng trên wire. Nhiều lỗi transport có thể được bọc bởi exception khác; hãy kiểm tra cause chain thay vì chỉ so khớp một `getClass().getSimpleName()`.

### 12.1. `ApplicationErrorException`

Responder có thể gửi một RSocket `ERROR` frame ở stream level khi handler phát `onError`. Requester nhận exception tương ứng, thường là `ApplicationErrorException`.

Không giả định exception Java nguyên bản trên server được serialize đầy đủ sang client. RSocket protocol mang error code và error data/message; client nên dùng error contract riêng nếu cần cấu trúc ổn định.

### 12.2. `RejectedException` và `CanceledException`

Theo semantics RSocket:

- `RejectedException`: responder từ chối request hợp lệ và bảo đảm chưa xử lý request đó.
- `CanceledException`: responder hủy request nhưng có thể đã bắt đầu xử lý; không bảo đảm không có side effect.

Phân biệt này cực kỳ quan trọng khi quyết định retry thao tác có side effect.

### 12.3. Setup rejection không phải application 404

RSocket không có HTTP status 404/500 trong một RSocket TCP interaction. Không tìm được route hoặc lỗi handler được biểu diễn theo exception/error protocol của RSocket; nếu transport là WebSocket, HTTP status chỉ có vai trò trong giai đoạn HTTP upgrade, không phải response status cho từng RSocket request.

## 13. Xử lý lỗi ở client: `onErrorMap`, `onErrorResume` và logging

Một reactive service có thể giữ exception transport ở boundary adapter rồi chuyển thành exception của ứng dụng.

```java
public Mono<String> getGreeting(String name) {
    return requester.route("hello")
            .data(name)
            .retrieveMono(String.class)
            .onErrorMap(
                    io.rsocket.exceptions.ApplicationErrorException.class,
                    error -> new RemoteBusinessException(
                            "Responder rejected greeting", error))
            .doOnError(error ->
                    logger.warn(
                            "RSocket greeting failed: type={}",
                            error.getClass().getSimpleName()));
}
```

`RemoteBusinessException` là exception domain cần do ứng dụng khai báo. Với retry/timeout, giữ nguyên cause giúp vận hành phân biệt lỗi nguồn.

### 13.1. Fallback khi thật sự có giá trị nghiệp vụ

```java
public Mono<String> optionalGreeting(String name) {
    return requester.route("hello")
            .data(name)
            .retrieveMono(String.class)
            .onErrorResume(
                    io.rsocket.exceptions.ApplicationErrorException.class,
                    error -> Mono.just("Tạm thời không thể chào"));
}
```

Fallback phù hợp nếu use case cho phép trả giá trị thay thế. Không biến mọi lỗi kết nối thành dữ liệu “thành công” nếu điều đó khiến caller bỏ qua việc đơn hàng đã không được xử lý.

### 13.2. Đừng log raw metadata/payload

RSocket setup/request metadata có thể chứa token hoặc session identifiers. Log an toàn nên có:

- Tên endpoint, route.
- Connection/client ID đã được chuẩn hóa.
- Lớp lỗi và mã lỗi RSocket khi có.
- Correlation/trace ID.
- Thời gian connect và latency request.
- Số lần retry và nguyên nhân.

Không log access token, full payload, private key, thông tin tài khoản hoặc stack trace của upstream vào public response.

## 14. Retry khác với reconnect

`retryWhen(...)` của Reactor hoạt động bằng cách subscribe lại nguồn khi publisher phát `onError`. Với RSocket, điều đó có thể gửi lại *request*, không đơn thuần là “tạo lại socket”.

```java
Mono<String> result = requester.route("hello")
        .data("An")
        .retrieveMono(String.class)
        .retryWhen(
                Retry.backoff(2, Duration.ofMillis(200))
                        .maxBackoff(Duration.ofSeconds(2)));
```

Ví dụ có tối đa 2 lần retry sau lần gọi đầu tiên. Đây chỉ là minh họa cho một operation được phép retry; không áp dụng cho mọi route.

### 14.1. Vì sao retry có thể tạo side effect trùng?

Xét route:

```text
payments.charge
```

Client gửi request thanh toán. Server ghi giao dịch thành công nhưng connection đứt trước khi phản hồi. Client nhận lỗi transport và retry. Server có thể thực hiện thanh toán lần thứ hai.

RSocket không tự bảo đảm exactly-once delivery hoặc business-level deduplication. Với operation không idempotent, cần:

- Idempotency key do client sinh.
- Server lưu kết quả đã xử lý theo key.
- Retry chỉ khi contract cho phép.
- Giới hạn số lần retry, có backoff và jitter.
- Deadline tổng để tránh retry kéo dài vô hạn.

### 14.2. Chỉ retry lỗi transient được chọn

Ví dụ predicate có chủ đích:

```java
Retry retryPolicy = Retry.backoff(3, Duration.ofMillis(200))
        .maxBackoff(Duration.ofSeconds(2))
        .filter(error ->
                error instanceof io.rsocket.exceptions.ConnectionErrorException
                || error instanceof java.net.ConnectException)
        .onRetryExhaustedThrow(
                (spec, signal) -> signal.failure());
```

Đây là ví dụ lọc một số lỗi. Trên thực tế lỗi có thể được wrap; nên viết utility kiểm tra cause chain và kiểm thử với connector/phiên bản đang dùng. Đừng retry `InvalidSetupException`, authentication failure hoặc application validation error chỉ vì chúng cũng là `RuntimeException`.

### 14.3. Retry stream có thể phát dữ liệu lặp

Với Request-Stream:

```java
Flux<Event> events = requester.route("events")
        .data("room-1")
        .retrieveFlux(Event.class)
        .retryWhen(Retry.backoff(2, Duration.ofSeconds(1)));
```

Nếu đã nhận 100 event rồi connection đứt, retry thường bắt đầu lại stream từ đầu (theo contract của route), có thể phát lại 100 event cũ. Không dùng retry stream trần nếu ứng dụng yêu cầu exactly-once ordering. Cần server hỗ trợ cursor/offset/checkpoint và client de-duplicate event ID.

### 14.4. Khi nào không retry?

- Setup bị từ chối do version/MIME không tương thích.
- Credential sai hoặc không đủ quyền.
- Domain validation lỗi.
- Route không tồn tại.
- Request có side effect mà chưa có idempotency.
- Đã quá deadline tổng.
- Downstream đang bị quá tải và retry sẽ làm tình hình tệ hơn.

## 15. Timeout, deadline và backpressure

### 15.1. `Mono.timeout` là request-level deadline

```java
Mono<String> result = requester.route("hello")
        .data("An")
        .retrieveMono(String.class)
        .timeout(Duration.ofSeconds(3));
```

Timeout hủy subscription khi không hoàn tất trong thời gian yêu cầu. Nó không chứng minh server chưa xử lý side effect.

### 15.2. Timeout tổng với retry

```java
Mono<String> result = requester.route("hello")
        .data("An")
        .retrieveMono(String.class)
        .retryWhen(
                Retry.backoff(2, Duration.ofMillis(250)))
        .timeout(Duration.ofSeconds(5));
```

Đặt timeout sau `retryWhen` để giới hạn toàn bộ chuỗi retries. Đặt timeout trước retry có semantics khác: mỗi attempt có thể nhận một timeout riêng rồi lại được retry, kéo dài tổng thời gian.

### 15.3. Backpressure qua mạng

Trong Request-Stream/Channel, RSocket mang tín hiệu demand qua `REQUEST_N`. Tuy nhiên:

- `Flux` chỉ giúp nếu producer tôn trọng demand.
- Queue tự viết không giới hạn vẫn có thể ngốn bộ nhớ.
- `collectList()` của một stream rất dài có thể tích lũy toàn bộ dữ liệu.
- `flatMap` không giới hạn có thể làm tăng số request đang chạy.
- Network-level backpressure không thay thế giới hạn payload và memory.

Ví dụ một consumer xử lý tuần tự:

```java
Mono<Void> processing = requester.route("events")
        .data("room-1")
        .retrieveFlux(Event.class)
        .concatMap(eventService::process)
        .then();
```

Nếu muốn xử lý đồng thời, dùng `flatMap(eventService::process, concurrency)` với giới hạn hữu hạn.

## 16. Xử lý lỗi ở responder

Một handler có thể trả publisher phát lỗi:

```java
@MessageMapping("validate")
public Mono<String> validate(String input) {
    if (input == null || input.isBlank()) {
        return Mono.error(
                new IllegalArgumentException("value must not be blank"));
    }

    return Mono.just(input.toUpperCase(Locale.ROOT));
}
```

Khi handler phát error, RSocket có thể truyền một `ERROR` frame tương ứng với request stream. Các request khác trên cùng connection không nhất thiết bị ảnh hưởng.

### 16.1. Map lỗi có ý nghĩa ứng dụng

Có thể gửi error result có cấu trúc trên đường thành công nếu client/server đã thống nhất contract:

```java
public record OperationResult(
        boolean success,
        String code,
        String message) {
}
```

Không dùng `Mono.just(OperationResult(false,...))` một cách tùy tiện nếu API contract coi đó là lỗi terminal. Cần quy định rõ khi nào trả `ERROR` frame, khi nào trả domain result.

### 16.2. Lỗi connection-level

`@ConnectMapping` có thể từ chối `SETUP` bằng cách trả error khi kiểm tra connection identity hoặc setup data không hợp lệ. Điều đó khác với việc một `@MessageMapping` route trả validation error ở request stream.

Đừng trả stack trace, SQL hoặc private server details trong error payload. Nếu cần error code ổn định, xây dựng application error contract có version.

## 17. Session resumption, leasing và fragmentation

RSocket protocol có các khả năng nâng cao, không nên mặc định đã bật.

### 17.1. Resume

Session resumption hỗ trợ nối lại một phiên sau mất kết nối khi cả hai phía đã thương lượng và lưu state phù hợp. Không phải RSocket requester nào cũng bật resume. Hạ tầng cần có memory/state và quy tắc replay frame.

Nếu ứng dụng cần khôi phục dữ liệu sau mất kết nối, cân nhắc thiết kế checkpoint/replay ở application layer ngay cả khi dùng resume.

### 17.2. Lease

Lease là cơ chế responder cấp số lượng request cho requester theo thời gian; requester phải tôn trọng lease trước khi gửi thêm. Lease khác với Reactive Streams demand của một request stream và khác với rate limit HTTP.

Nếu bật leasing mà server/client không cấu hình tương thích, có thể gặp rejection hoặc request bị trì hoãn. Chỉ bật khi có thiết kế capacity management rõ ràng.

### 17.3. Fragmentation

RSocket có thể fragment payload/frame lớn để truyền qua transport. Fragmentation giúp vận chuyển payload nhưng không có nghĩa ứng dụng có thể nhận dữ liệu vô hạn không cần giới hạn. Cần đặt max inbound payload, memory limit, concurrency và codec limit thích hợp.

`RSocketConnector.fragment(mtu)` là API ở tầng connector để cấu hình phân mảnh; giá trị cụ thể phải phù hợp với server/transport.

## 18. Bảo mật kết nối và metadata

Kết nối RSocket có thể tồn tại lâu; vì vậy authentication và authorization cần được thiết kế cho cả connection-level và request-level.

- Dùng TLS khi kết nối qua mạng không tin cậy.
- Nếu chạy RSocket over WebSocket, dùng `wss://` và kiểm tra reverse proxy hỗ trợ WebSocket upgrade.
- Với TCP transport, cấu hình TLS ở transport hoặc lớp mạng phù hợp.
- Setup metadata có thể mang credential cho connection; không log secret.
- Quyền truy cập từng route vẫn cần được kiểm tra.
- Token có thể hết hạn khi connection đang mở; xác định chính sách re-authenticate hoặc đóng phiên.
- Giới hạn số kết nối, số stream, payload size và request rate.
- Không coi network-level connection có nghĩa mọi message đều được phép.
- Không gửi password trong unencrypted connection.

Spring Security hỗ trợ authorization cho RSocket. Khi triển khai thực tế, kiểm thử cả setup authentication, message authorization và expired credentials.

## 19. Dự án Java 17+ có thể chạy: RSocket over WebSocket

Dự án ví dụ kết hợp Spring Boot 3.3.5, Spring WebFlux, RSocket starter, Jackson và JUnit 5. Dùng WebSocket transport để test mở server trên cổng ngẫu nhiên qua `@SpringBootTest(webEnvironment = RANDOM_PORT)`, tránh phụ thuộc cổng TCP cố định.

**Các route minh họa:**

- `hello`: Request-Response.
- `numbers`: Request-Stream.
- `upper`: Request-Channel.
- `reject`: Application error.
- `audit`: Fire-and-Forget.

### 19.1. Cấu trúc

```text
rsocket-connection-lifecycle/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/edu/demo/rsocket/
    │   │   ├── RSocketApplication.java
    │   │   └── DemoResponder.java
    │   └── resources/
    │       └── application.properties
    └── test/
        └── java/edu/demo/rsocket/
            └── RSocketLifecycleTests.java
```

### 19.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>edu.demo</groupId>
    <artifactId>rsocket-connection-lifecycle</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-rsocket</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
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

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-boot-starter-rsocket` mang RSocket transport và Spring messaging support. `spring-boot-starter-webflux` tạo reactive HTTP server dùng để host RSocket over WebSocket.

### 19.3. `application.properties`

```properties
server.port=8080
spring.rsocket.server.transport=websocket
spring.rsocket.server.mapping-path=/rsocket
logging.level.io.rsocket=INFO
```

Ở production, không bật DEBUG toàn bộ RSocket frames nếu metadata chứa token hoặc dữ liệu nhạy cảm. Ở đây dùng INFO để tránh log payload.

### 19.4. `RSocketApplication.java`

```java
package edu.demo.rsocket;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RSocketApplication {

    public static void main(String[] args) {
        SpringApplication.run(RSocketApplication.class, args);
    }
}
```

### 19.5. `DemoResponder.java`

```java
package edu.demo.rsocket;

import java.util.Locale;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.stereotype.Controller;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Controller
public class DemoResponder {

    private final AtomicInteger auditCount = new AtomicInteger();

    @MessageMapping("hello")
    public Mono<String> hello(String name) {
        return Mono.just("Xin chào, " + name);
    }

    @MessageMapping("numbers")
    public Flux<Integer> numbers(Integer count) {
        int safeCount = Math.max(0, Math.min(count, 10));
        return Flux.range(1, safeCount);
    }

    @MessageMapping("upper")
    public Flux<String> upper(Flux<String> words) {
        return words.map(word -> word.toUpperCase(Locale.ROOT));
    }

    @MessageMapping("reject")
    public Mono<String> reject(String input) {
        return Mono.error(
                new IllegalArgumentException("Rejected: " + input));
    }

    @MessageMapping("audit")
    public Mono<Void> audit(String event) {
        return Mono.fromRunnable(auditCount::incrementAndGet);
    }

    public int auditCount() {
        return auditCount.get();
    }
}
```

`auditCount` dùng cho quan sát nội bộ của sample, không phải persistence. Trong hệ thống thật, Fire-and-Forget cần giải quyết acknowledgment ở tầng nghiệp vụ nếu phải bảo đảm dữ liệu không mất.

### 19.6. `RSocketLifecycleTests.java`

```java
package edu.demo.rsocket;

import java.net.URI;
import java.time.Duration;

import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.TestInstance;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.messaging.rsocket.RSocketRequester;
import org.springframework.util.MimeTypeUtils;

import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
class RSocketLifecycleTests {

    @LocalServerPort
    int port;

    @Autowired
    RSocketRequester.Builder builder;

    private RSocketRequester requester;

    @BeforeAll
    void connect() {
        requester = builder
                .dataMimeType(MimeTypeUtils.APPLICATION_JSON)
                .rsocketConnector(connector ->
                        connector.keepAlive(
                                Duration.ofSeconds(20),
                                Duration.ofSeconds(90)))
                .websocket(URI.create(
                        "ws://localhost:" + port + "/rsocket"));
    }

    @AfterAll
    void close() {
        if (requester != null) {
            requester.dispose();
        }
    }

    @Test
    void requestResponseReturnsOneValue() {
        StepVerifier.create(
                        requester.route("hello")
                                .data("An")
                                .retrieveMono(String.class))
                .expectNext("Xin chào, An")
                .verifyComplete();
    }

    @Test
    void requestStreamRespectsDemandAndCompletes() {
        StepVerifier.create(
                        requester.route("numbers")
                                .data(3)
                                .retrieveFlux(Integer.class),
                        0)
                .thenRequest(1)
                .expectNext(1)
                .thenRequest(2)
                .expectNext(2, 3)
                .verifyComplete();
    }

    @Test
    void requestChannelTransformsSeveralMessages() {
        StepVerifier.create(
                        requester.route("upper")
                                .data(
                                        Flux.just("mot", "hai", "ba"),
                                        String.class)
                                .retrieveFlux(String.class))
                .expectNext("MOT", "HAI", "BA")
                .verifyComplete();
    }

    @Test
    void applicationErrorIsSignaledToRequester() {
        StepVerifier.create(
                        requester.route("reject")
                                .data("bad")
                                .retrieveMono(String.class))
                .expectError()
                .verify();
    }

    @Test
    void timeoutCancelsSlowPublisher() {
        StepVerifier.create(
                        Flux.never()
                                .timeout(Duration.ofMillis(100)))
                .expectError(java.util.concurrent.TimeoutException.class)
                .verify(Duration.ofSeconds(3));
    }
}
```

**Lưu ý về test cuối:** kiểm thử `Flux.never().timeout(...)` nhằm kiểm tra semantics deadline của Reactor tại lớp client, không khẳng định remote RSocket server đã được gọi. Bốn test đầu là integration test với RSocket WebSocket thực.

Test `@BeforeAll` xây dựng requester nhưng không buộc transport kết nối ngay lập tức. Khi `StepVerifier` subscribe request đầu tiên, kết nối được mở. Các test còn lại có thể dùng chung connection; `@AfterAll` dispose để giải phóng tài nguyên.

### 19.7. Chạy Maven

Từ thư mục chứa `pom.xml`:

```bash
mvn test
```

Sau đó có thể chạy server:

```bash
mvn spring-boot:run
```

Endpoint RSocket over WebSocket:

```text
ws://localhost:8080/rsocket
```

Để kết nối từ một Java client khác:

```java
RSocketRequester requester = RSocketRequester.builder()
        .dataMimeType(MimeTypeUtils.APPLICATION_JSON)
        .websocket(URI.create("ws://localhost:8080/rsocket"));

requester.route("hello")
        .data("Mai")
        .retrieveMono(String.class)
        .doFinally(signal -> requester.dispose())
        .block(Duration.ofSeconds(5));
```

`block(Duration)` ở đây chỉ dành cho một chương trình demo đồng bộ hoặc ranh giới CLI/test. Trong service WebFlux production, trả publisher và quản lý requester qua Spring bean; không block Netty event-loop.

### 19.8. Kết quả kỳ vọng

Các assertions kiểm tra:

1. Request-response trả `"Xin chào, An"`.
2. Request-stream phát `1, 2, 3` theo demand được yêu cầu.
3. Request-channel chuyển ba từ thành chữ hoa.
4. `reject` phát terminal error tới requester.
5. Reactor timeout phát `TimeoutException`.

Một lần chạy Maven thành công dự kiến có năm test được thực thi, không fail/error/skip. Đây là kết quả mong đợi, không phải xác nhận Maven đã được chạy trong môi trường biên soạn.

### 19.9. Chuyển sample sang TCP

Thay cấu hình server:

```properties
spring.rsocket.server.port=7000
spring.rsocket.server.transport=tcp
```

Client thay:

```java
RSocketRequester requester = builder
        .dataMimeType(MimeTypeUtils.APPLICATION_JSON)
        .tcp("localhost", 7000);
```

Nếu dùng TCP server độc lập, không dùng URI `/rsocket`. Với WebSocket tích hợp WebFlux, giữ `mapping-path` và URI WebSocket đúng.

## 20. Quan sát connection và request trong production

Một hệ thống RSocket vận hành tốt cần metric và log theo cả connection và stream.

### 20.1. Các số đo hữu ích

| Metric | Ý nghĩa |
|---|---|
| Active connections | Số kết nối đang mở |
| Connection attempts/failures | Lỗi DNS/TCP/TLS/setup |
| Setup rejection count | Server từ chối connection |
| Keepalive timeout | Peer có thể đã mất kết nối |
| Request count theo route/type | Khối lượng công việc |
| Request latency p50/p95/p99 | Độ trễ theo route |
| Application error rate | Lỗi handler |
| Stream cancellation | Request bị hủy |
| Retry attempts/exhaustion | Sức ép retry |
| In-flight streams | Mức đồng thời |
| Payload size/queue depth | Áp lực bộ nhớ |

### 20.2. Log có cấu trúc

Ví dụ log một lỗi client:

```java
requester.route("hello")
        .data("An")
        .retrieveMono(String.class)
        .doOnError(error ->
                logger.warn(
                        "rsocket route=hello failed type={}",
                        error.getClass().getSimpleName()));
```

Trong production nên thêm correlation ID và tracing, nhưng tránh ghi nội dung token/metadata nhạy cảm. Với long-lived streams, gắn một ID cho request stream và ghi event complete/error/cancel theo lifecycle.

### 20.3. Mục tiêu cảnh báo

- Setup failure tăng đột biến.
- Keepalive disconnect nhiều.
- Thời gian reconnect kéo dài.
- Retry exhaustion tăng.
- Request latency và in-flight count tăng.
- Queue size vượt ngưỡng.
- Application errors theo route tăng so với baseline.

Đừng chỉ theo dõi TCP active connections. Một connection khỏe vẫn có thể có hàng nghìn streams chậm hoặc lỗi nghiệp vụ.

## 21. Kịch bản chẩn đoán lỗi

### Kịch bản A: TCP refused

Triệu chứng: client gọi `.tcp("localhost", 7000)` nhưng không kết nối.

Kiểm tra:

1. Server có `spring.rsocket.server.port=7000` không?
2. Transport có phải TCP không?
3. Port có đang listen không?
4. Container/network namespace có đúng host và port không?
5. Firewall/NetworkPolicy có chặn không?

Không thay đổi retry để che lỗi cấu hình host/port cố định.

### Kịch bản B: WebSocket upgrade failed

Triệu chứng: kết nối `ws://.../rsocket` bị từ chối.

Kiểm tra:

- Server đã bật `transport=websocket` và mapping path đúng chưa?
- WebFlux server có chạy bằng Reactor Netty không?
- Proxy có chuyển tiếp WebSocket Upgrade/Connection headers không?
- URI có đúng `ws://` hoặc `wss://` không?
- Có gateway route nào rewrite path sai không?
- Origin/TLS/authentication ở handshake có đúng không?

### Kịch bản C: SETUP rejected

Triệu chứng: transport kết nối được nhưng server từ chối phiên RSocket.

Kiểm tra:

- Protocol version tương thích.
- Data/metadata MIME types.
- Route setup/metadata format.
- Credential/authorization setup.
- Lease/resume options có được server hỗ trợ không?

Retry nguyên cấu hình sai thường không giải quyết được. Sửa setup rồi mới kết nối lại.

### Kịch bản D: Request cũ fail sau restart

Triệu chứng: gọi A trước restart nhận lỗi, gọi B sau restart thành công.

Đây có thể là hành vi bình thường: requester tạo lại shared connection cho request B, nhưng request A đang in-flight không được replay tự động. Nếu cần A hoàn tất, thiết kế application-level retry với idempotency và kiểm soát duplicate.

### Kịch bản E: Stream bị duplicate sau retry

Triệu chứng: 100 events đầu tiên xuất hiện lặp lại.

Retry `retrieveFlux` có thể subscribe lại từ đầu nguồn. Cần event IDs, cursor/offset và de-duplication thay vì chỉ `.retryWhen(...)`.

### Kịch bản F: Keepalive timeout thường xuyên

Kiểm tra:

- Network jitter và RTT.
- Proxy/load balancer idle timeout.
- Event-loop bị blocking.
- JVM GC pause.
- Giá trị interval và maxLifeTime quá chặt.
- Số connection vượt năng lực server.

Không đặt interval cực thấp để cố “chữa” timeout; trước hết đo network và event loop.

## 22. Các sai lầm phổ biến

| Sai lầm | Hậu quả | Cách sửa |
|---|---|---|
| Dùng API Spring 5.2 `connectTcp().block()` trong code Spring 6 | Code lỗi biên dịch hoặc blocking không cần thiết | Dùng `tcp(...)`/`websocket(...)` |
| Tạo requester mới mỗi lần gọi | Mở nhiều connection, khó cleanup | Dùng requester lâu dài theo endpoint |
| Quên subscribe/return publisher | Request không được thực hiện | Return/compose Mono, Flux |
| Gọi `.subscribe()` riêng trong service | Lỗi/cancel thoát khỏi lifecycle | Giữ composition reactive |
| Nhầm SETUP với từng request | Xử lý lỗi sai tầng | Phân biệt connection-level và stream-level |
| Cho rằng reconnect tự replay in-flight request | Mất request/side effect không chắc chắn | App-level idempotency/replay |
| Retry mọi exception | Lặp lỗi cấu hình, auth, validation | Chọn transient errors |
| Retry POST-like business operation không idempotent | Side effect trùng | Idempotency key |
| Retry stream không có offset | Nhận dữ liệu trùng | Cursor/checkpoint/de-dup |
| Không giới hạn request timeout | Dễ giữ stream chờ vô hạn | Deadline rõ ràng |
| Chỉ dùng keepalive để giới hạn SLA | Request chậm không được phát hiện đúng | Timeout từng request |
| Đặt keepalive quá dày | Tăng frame/scheduling overhead | Cấu hình theo topology |
| Quên `dispose()` | Rò rỉ connection khi shutdown | Bean `destroyMethod`/`@PreDestroy` |
| Dùng requester đã dispose | Request mới thất bại | Tạo lifecycle requester mới |
| Nhầm RSocket WebSocket với WebSocket thuần | Client không hiểu frame | Dùng RSocket-aware client |
| Log setup metadata chứa token | Rò rỉ credential | Mask secret, log metadata an toàn |
| Không giới hạn payload/streams | Memory/resource pressure | Size, concurrency, lease/quota |
| Coi cancel là rollback | Side effect đã bắt đầu vẫn có thể commit | Transaction/idempotency |
| Nghĩ resume mặc định bật | Hiểu sai hành vi sau disconnect | Cấu hình đúng hoặc dùng app replay |
| Chỉ monitor active connections | Bỏ sót request failures/latency | Metrics cả connection và route |

## 23. Checklist trước khi đưa RSocket vào production

### Connection setup

- Transport TCP hay WebSocket đã được chọn đúng?
- Host, port hoặc WebSocket URI có khớp deployment?
- TLS, truststore, proxy và ingress có được cấu hình nếu cần?
- `SETUP` MIME types có được client/server thống nhất?
- Có setup metadata/route bắt buộc không?
- Authentication ở connection-level có an toàn không?

### Lifecycle

- Requester được dùng lại cho nhiều calls?
- Có shutdown lifecycle để dispose requester?
- Khi mất connection, có phân biệt request mới và in-flight requests?
- Keepalive phù hợp với network idle timeout và RTT?
- Có theo dõi connection failures và reconnect latency?
- Có tránh tự subscribe ở adapter/service?

### Error handling

- Có phân biệt transport, setup, connection, stream, codec và domain errors?
- Có tránh retry lỗi permanent?
- Retry có số lần tối đa, backoff, jitter và deadline?
- Route có side effect có idempotency key?
- Stream retry có checkpoint/offset/de-dup nếu cần?
- Có log/tracing nhưng không lộ payload/credentials?
- Có fallback đúng nghiệp vụ hoặc propagate failure?

### Capacity và security

- Có giới hạn số connections và in-flight streams?
- Có payload size limit?
- Có quyền truy cập theo route?
- Có token expiry/re-authentication policy cho connection dài?
- Có backpressure và giới hạn queue?
- Có kiểm thử load, disconnect, restart, timeout và slow consumer?

### Kiểm thử

- Test bốn interaction models theo nhu cầu.
- Test setup failure và unsupported MIME.
- Test handler application error.
- Test timeout và cancellation.
- Test connection lost + request mới.
- Test no duplicate side effects khi retry.
- Test shutdown resource cleanup.
- Test WebSocket upgrade qua gateway nếu deploy qua proxy.

## 24. Bài tập tự kiểm tra

**Bài 1.** `RSocketRequester.Builder.tcp(...)` có luôn mở TCP connection ngay lập tức không?

**Đáp án:** Không. API hiện đại xây dựng requester kết nối theo nhu cầu, khi request được subscribe. Các request có thể dùng shared connection.

**Bài 2.** RSocket `SETUP` chứa những thông tin quan trọng nào?

**Đáp án:** Phiên bản protocol, data/metadata MIME types, keepalive settings và optional setup data/metadata, lease/resume options.

**Bài 3.** `@ConnectMapping` khác `@MessageMapping` như thế nào?

**Đáp án:** `@ConnectMapping` xử lý connection-level SETUP/METADATA_PUSH, không trả response data; `@MessageMapping` xử lý từng request route.

**Bài 4.** Server restart, request A lỗi, request B sau đó thành công. Điều này có mâu thuẫn không?

**Đáp án:** Không. Request mới có thể tạo shared connection mới, nhưng request đang chạy bị mất không tự được replay.

**Bài 5.** `RSocketRequester.dispose()` dùng khi nào?

**Đáp án:** Khi client adapter/app shutdown hoặc không còn dùng requester. Không tái sử dụng requester đã dispose.

**Bài 6.** `KEEPALIVE` có thay thế `Mono.timeout` cho request không?

**Đáp án:** Không. Keepalive kiểm tra kết nối, còn request timeout giới hạn thời gian phản hồi của một operation.

**Bài 7.** `RejectedException` và `CanceledException` khác nhau ở điểm nào quan trọng?

**Đáp án:** Rejected bảo đảm responder chưa xử lý request; canceled có thể xảy ra sau khi đã bắt đầu side effect. Retry cần xem semantics này.

**Bài 8.** Vì sao retry một Request-Stream có thể gây duplicate events?

**Đáp án:** Retry subscribe lại publisher và có thể khởi động stream từ đầu theo contract của route. Cần cursor, event ID, checkpoint/de-dup.

**Bài 9.** Có thể dùng `@MessageMapping` để xử lý RSocket trên WebSocket không?

**Đáp án:** Có. Interaction model và handler của RSocket vẫn như nhau; chỉ transport và endpoint configuration thay đổi.

**Bài 10.** Muốn đảm bảo không xử lý thanh toán hai lần khi connection đứt sau commit phải làm gì?

**Đáp án:** Dùng idempotency key được server lưu và enforce, đồng thời áp dụng retry policy dựa trên business contract. Reconnect/keepalive không cung cấp exactly-once.

## 25. Ghi nhớ

- RSocket hỗ trợ Request-Response, Request-Stream, Channel và Fire-and-Forget.
- Connection được thiết lập bằng transport + `SETUP`; các request streams chạy trên shared connection.
- `RSocketRequester.Builder.tcp(...)` và `.websocket(...)` là API phù hợp với Spring Framework 6.x, kết nối theo nhu cầu.
- `SETUP` chứa MIME types, keepalive và optional metadata. `@ConnectMapping` có thể xử lý setup và từ chối kết nối.
- Một stream-level `ERROR` không đồng nghĩa toàn connection đã chết.
- Mất connection có thể khiến in-flight requests lỗi; request mới có thể tạo kết nối mới nhưng request cũ không tự replay.
- `dispose()` quản lý lifecycle requester khi shutdown.
- `KEEPALIVE` kiểm tra peer; `Mono.timeout` kiểm soát deadline từng operation.
- Phân loại transport/setup/connection/stream/codec/application errors trước khi quyết định retry.
- Retry là subscribe lại publisher, có thể gửi lại request và làm trùng side effects hoặc stream events.
- Idempotency, event cursor và de-duplication phải được giải quyết theo contract nghiệp vụ.
- Resume, leasing và fragmentation là tính năng nâng cao cần được cấu hình và kiểm thử, không mặc nhiên bật.
- Long-lived connections cần security, metrics, payload limits, concurrency limits và graceful cleanup.

**Quy tắc nhớ nhanh:** **Connection lại được chưa? Request cũ có thật sự hoàn thành không? Retry có an toàn không?** Đây là ba câu hỏi phải trả lời riêng khi thiết kế ứng dụng RSocket bền vững.

## Tài liệu chính thức và đọc thêm

- Spring Framework — RSocket Overview, `RSocketRequester`, Connection Setup và Annotated Responders: https://docs.spring.io/spring-framework/reference/rsocket.html
- Spring Framework 6.1 — `RSocketRequester.Builder` Javadoc: https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/messaging/rsocket/RSocketRequester.Builder.html
- Spring Framework 6.2 — `RSocketRequester` Javadoc và lifecycle `dispose()`: https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/messaging/rsocket/RSocketRequester.html
- Spring Boot 3.3 — RSocket messaging/auto-configuration: https://docs.spring.io/spring-boot/3.3/reference/messaging/rsocket.html
- RSocket Java 1.1.5 — `RSocketConnector`/keepalive API: https://javadoc.io/static/io.rsocket/rsocket-core/1.1.5/io/rsocket/core/RSocketConnector.html
- RSocket Java 1.1.5 — Protocol exception classes: https://javadoc.io/static/io.rsocket/rsocket-core/1.1.5/io/rsocket/exceptions/package-summary.html
- RSocket Protocol Specification: https://rsocket.io/about/protocol/
- Project Reactor — Error Handling và Retry: https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html