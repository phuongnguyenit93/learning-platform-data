# RSocket và nhu cầu giao tiếp phản ứng hai chiều

## 1. Vì sao cần giao tiếp reactive hai chiều?

Trong nhiều ứng dụng phân tán, mô hình HTTP request-response cổ điển vẫn rất hiệu quả: client gửi một request, server trả một response và interaction kết thúc. Nhưng một số bài toán cần trao đổi dữ liệu liên tục hoặc luân phiên theo cả hai hướng trên cùng một kết nối:

- Dashboard nhận giá, telemetry hoặc trạng thái thiết bị mới liên tục.
- Ứng dụng chat/điều phối cần vừa gửi tin nhắn vừa nhận thông báo.
- Gateway trao đổi sự kiện với nhiều dịch vụ backend.
- Thiết bị IoT gửi sensor data và nhận lệnh điều khiển.
- Một dịch vụ cần stream kết quả trong lúc client vẫn tiếp tục cung cấp input.
- Hệ thống cần bảo vệ producer khi consumer chậm (backpressure).

Có thể giải quyết một phần bằng HTTP polling, Server-Sent Events (SSE), WebSocket hoặc message broker. Tuy nhiên, với reactive services cần cả streaming, multiplexing và flow control ở cấp protocol, `RSocket` là một lựa chọn đáng tìm hiểu.

`RSocket` là giao thức binary application-level, hoạt động trên TCP, WebSocket hoặc transport dạng byte stream khác. Nó cung cấp các interaction model đối xứng, giao tiếp full-duplex, hỗ trợ backpressure cho các luồng streaming, đồng thời multiplex nhiều logical stream trên một kết nối vật lý.

**Hai chiều không đồng nghĩa hai bên gửi cùng một lúc ở mọi request.** RSocket hỗ trợ nhiều pattern: có pattern một request một response, có pattern một chiều, có pattern stream kết quả, và có request-channel cho phép hai luồng dữ liệu diễn ra đồng thời.

Mục tiêu bài học: hiểu vấn đề thực tế mà RSocket giải quyết, nắm bốn interaction model, kiến trúc requester/responder, demand/cancellation, khác biệt với HTTP/SSE/WebSocket, và triển khai ví dụ Java 17 + Spring Boot với `@MessageMapping` và `RSocketRequester`.

## 2. RSocket là gì và hoạt động ra sao?

### 2.1. Requester và responder thay cho client/server cố định

Khi mở TCP/WebSocket connection, một phía khởi tạo kết nối và phía còn lại lắng nghe. Sau khi kết nối RSocket được thiết lập, **hai phía có thể đóng vai requester hoặc responder** cho các interaction độc lập.

- **Requester** khởi tạo một interaction.
- **Responder** xử lý interaction và gửi tín hiệu thích hợp.
- Mỗi logical interaction có stream identifier riêng để các thông điệp không nhầm lẫn.
- Một kết nối vật lý có thể đồng thời mang nhiều interaction.

~~~text
                      One TCP / WebSocket connection
+------------------------+  <==================>  +------------------------+
| Service A              |                        | Service B              |
| requester + responder  | -- request  stream 1 ->| responder              |
|                        |<- response stream 1 ---|                        |
| responder              |<- request  stream 3 ---| requester              |
|                        |-- response stream 3 -->|                        |
| requester              |<== channel stream 5 ==>| responder              |
+------------------------+                        +------------------------+
~~~

Nếu Service A khởi tạo connection, điều đó **không** có nghĩa Service B chỉ được trả lời. Khi Service B đã có `RSocketRequester` của kết nối và Service A đã đăng ký responder, Service B cũng có thể chủ động gọi route ở A.

### 2.2. Một interaction khác một TCP connection

RSocket multiplex nhiều logical stream trên một connection. Ví dụ, client có thể gửi request tra cứu danh mục, nhận stream giá và thực hiện request-channel chat mà không tạo một kết nối TCP mới cho từng tác vụ.

Multiplexing giảm overhead kết nối và tạo ra một mô hình thống nhất, nhưng không loại bỏ mọi giới hạn vật lý: nhiều stream vẫn chia sẻ network bandwidth, CPU, buffer và connection congestion.

### 2.3. Khởi tạo connection

Client gửi frame `SETUP` với các thiết lập như data MIME type và metadata MIME type. Server có thể chấp nhận hoặc từ chối SETUP. Sau khi connection được thiết lập, các phía bắt đầu gửi request frames.

~~~text
Initiator                            Acceptor
    | --- TCP/WebSocket connect -----> |
    | -------- RSocket SETUP --------> |
    | <------ setup accepted ----------|
    | -- REQUEST_RESPONSE (stream 1)-> |
    | <--------- PAYLOAD --------------|
    | -- REQUEST_STREAM (stream 3) --> |
    | <---- PAYLOAD, PAYLOAD,... ------|
    | --------- CANCEL --------------> |
~~~

Chi tiết về thời điểm server được phép gửi request ở lúc SETUP cần tuân thủ lifecycle. Trong Spring, `@ConnectMapping` xử lý SETUP; không được chờ một server-initiated request hoàn tất ngay trong callback xử lý SETUP, vì connection cần được chấp nhận trước.

### 2.4. Data, metadata và route

RSocket payload gồm **data** (nội dung nghiệp vụ) và **metadata** (thông tin điều khiển, định tuyến, bảo mật, tracing...). MIME type cho data và metadata được thương lượng trong SETUP.

Spring thường dùng composite metadata để có nhiều entry metadata độc lập, trong đó routing metadata giúp chọn `@MessageMapping` như `orders.created` hoặc `telemetry.readings`. Route là logical destination, **không phải URL HTTP**.

Ví dụ:

~~~java
Flux<String> updates = requester
    .route("telemetry.readings")
    .data("sensor-A")
    .retrieveFlux(String.class);
~~~

Không có HTTP method, status 200 hoặc header Authorization như một REST endpoint thông thường. Với RSocket, metadata/route và error signal có semantic riêng.

## 3. Bốn interaction model của RSocket

RSocket có bốn pattern cốt lõi. Đây là khác biệt quan trọng nhất với một giao thức chỉ cung cấp byte stream hoặc message không có application-level cardinality.

| Model | Input requester gửi | Output responder trả | API Spring thường dùng | Tình huống |
| --- | --- | --- | --- | --- |
| **Request-Response** | 0–1 item | 1 item | `retrieveMono(T.class)` | Tra cứu thông tin |
| **Fire-and-Forget** | 0–1 item | Không có payload phản hồi | `send()` | Gửi event best-effort |
| **Request-Stream** | 0–1 item | Nhiều item | `retrieveFlux(T.class)` | Theo dõi telemetry/giá |
| **Request-Channel** | Stream nhiều item | Stream nhiều item | `data(Flux, type).retrieveFlux(T.class)` | Chat, điều khiển, xử lý realtime |

Trong Spring Messaging, interaction type phần lớn được suy ra từ số lượng input và output. Nếu input là Publisher nhiều phần tử thì đó là Request-Channel; output có thể không có, một hoặc nhiều item tùy handler. Với input 0–1 và output nhiều item, đó là Request-Stream. Tránh giả định “nhiều input, một output” luôn là tương đương request-response: đó vẫn là channel.

### 3.1. Request-Response

Gửi một yêu cầu và nhận một phản hồi. Nó giống về shape với HTTP request-response nhưng sử dụng RSocket frames và metadata thay vì HTTP.

~~~text
Requester                      Responder
   | ----- REQUEST_RESPONSE ----->|
   |<----------- PAYLOAD ----------|
   |        COMPLETE/error         |
~~~

Spring client:

~~~java
Mono<String> greeting = requester
    .route("demo.hello")
    .data("Linh")
    .retrieveMono(String.class);
~~~

Server:

~~~java
@MessageMapping("demo.hello")
public Mono<String> hello(@Payload String name) {
    return Mono.just("Xin chào, " + name);
}
~~~

Phù hợp với một lần tra cứu kết quả. Chỉ nên dùng `retrieveMono` nếu hợp đồng thực sự trả tối đa một giá trị.

### 3.2. Fire-and-Forget

Requester gửi một thông điệp **không chờ business response**:

~~~java
Mono<Void> sent = requester
    .route("demo.notify")
    .data("Order created")
    .send();
~~~

`send()` trả `Mono<Void>` thể hiện việc message đã được gửi theo hợp đồng RSocket; **không bảo đảm ứng dụng bên nhận đã xử lý, lưu database hoặc commit transaction**.

~~~text
Requester                     Responder
   | ------ REQUEST_FNF --------->|
   |  no application response     |
~~~

Không dùng Fire-and-Forget cho payment hoặc lệnh cần acknowledgment nghiệp vụ, trừ khi đã có protocol acknowledgment/idempotency và cơ chế bảo đảm giao hàng riêng. Muốn biết server xử lý thành công, dùng Request-Response hoặc phát acknowledgment qua interaction khác.

### 3.3. Request-Stream

Gửi một request để nhận nhiều kết quả từ server. Ví dụ nhận 3 tick:

~~~java
Flux<String> ticks = requester
    .route("demo.ticks")
    .data("3")
    .retrieveFlux(String.class);
~~~

~~~text
Requester                        Responder
   | ------ REQUEST_STREAM -------->|
   |<--------- PAYLOAD 1 -----------|
   |<--------- PAYLOAD 2 -----------|
   |<--------- PAYLOAD 3 -----------|
   |<---------- COMPLETE -----------|
~~~

Consumer có thể điều chỉnh demand, và khi không cần nữa có thể cancel stream. Mô hình phù hợp với feed giá, telemetry, live progress và query trả nhiều kết quả dần.

### 3.4. Request-Channel: hai luồng dữ liệu độc lập

Đây là pattern thể hiện rõ giao tiếp hai chiều: requester gửi một stream và responder trả một stream. Hai chiều có thể có tốc độ và lifecycle khác nhau; responder không nhất thiết phải chờ requester gửi xong tất cả item mới phản hồi.

~~~java
Flux<String> outbound = Flux.just("a", "b", "c")
    .delayElements(Duration.ofMillis(100));

Flux<String> inbound = requester
    .route("demo.uppercase")
    .data(outbound, String.class)
    .retrieveFlux(String.class);
~~~

~~~text
Requester                       Responder
   | ------- REQUEST_CHANNEL ----->|
   | -------- DATA "a" ----------->|
   |<------- DATA "ECHO:A" --------|
   | -------- DATA "b" ----------->|
   |<------- DATA "ECHO:B" --------|
   | -------- DATA "c" ----------->|
   |<------- DATA "ECHO:C" --------|
   | ------- COMPLETE -----------> |
   |<-------- COMPLETE ----------- |
~~~

Đây là mô hình phù hợp với interactive processing, conversation streams, thiết bị vừa gửi cảm biến vừa nhận phản hồi, và các session có trao đổi trạng thái liên tục.

Cần phân biệt: Request-Channel giúp hai phía trao đổi dữ liệu trong một interaction. **Server khởi tạo một request mới tới client** là khả năng duplex bổ sung, cần client đăng ký responder và server có `RSocketRequester` cho kết nối.

### 3.5. Metadata-Push không phải pattern request nghiệp vụ thứ năm

RSocket có `METADATA_PUSH` frame để gửi metadata ở mức connection mà không gắn vào một request cụ thể. Trong Spring requester, `sendMetadata()` dùng cho cơ chế này. Đây là capability của protocol, không thay thế bốn interaction model cốt lõi ở trên.

## 4. Backpressure, multiplexing và vòng đời stream

### 4.1. Backpressure đi qua network

Trong reactive streams, downstream biểu đạt nhu cầu tiêu thụ bằng tín hiệu demand. RSocket mở rộng cơ chế đó qua network boundary ở Request-Stream và Request-Channel.

Protocol dùng `REQUEST_N` để truyền số lượng item mà phía nhận sẵn sàng xử lý. Khi consumer yêu cầu ít item, responder không nên gửi vượt demand đã được cấp cho chiều stream tương ứng.

~~~text
Consumer                                    Producer
   | -------- request(2) / REQUEST_N --------> |
   | <---------------- item 1 ---------------- |
   | <---------------- item 2 ---------------- |
   | -------- request(1) / REQUEST_N --------> |
   | <---------------- item 3 ---------------- |
   | ---------------- CANCEL ----------------> |
~~~

Spring + Reactor cho phép `request(n)` hoặc các operator như `take(n)` và `limitRate(n)` tham gia flow control. Backpressure của RSocket là lợi thế trước raw WebSocket, nơi ứng dụng thường phải tự thiết kế cơ chế credits hoặc queue.

Tuy nhiên, backpressure **không tự bảo đảm không bao giờ tràn bộ nhớ**. Một source nóng (hot source), một queue không giới hạn, quá nhiều logical streams hoặc một handler giữ state quá lớn vẫn có thể gây áp lực bộ nhớ. Luôn giới hạn buffer, concurrency, số subscriber và tốc độ publish.

### 4.2. Cancellation, complete và error

Một interaction có các tín hiệu lifecycle:

- `PAYLOAD` chứa data/metadata.
- `COMPLETE` báo phía gửi không còn item.
- `ERROR` báo lỗi tương ứng với stream/interaction.
- `CANCEL` báo phía nhận không cần dữ liệu nữa.
- `REQUEST_N` bổ sung demand.

Ví dụ client chỉ cần ba item từ một stream có thể dùng:

~~~java
Flux<String> firstThree = requester
    .route("prices.stream")
    .data("ABC")
    .retrieveFlux(String.class)
    .take(3);
~~~

Sau ba item, `take(3)` hoàn thành và cancel upstream khi cần. Bên phát phải tôn trọng cancellation, giải phóng connection-specific resources, timer và subscription. Không xem cancellation là lỗi nghiệp vụ.

### 4.3. Multiplex không có nghĩa vô hạn concurrency

RSocket phân biệt logical stream bằng stream identifier trên một connection. Nó giúp nhiều interaction hoạt động đồng thời mà không cần một TCP connection mỗi request.

Nhưng tất cả vẫn chia sẻ network link. Khi thiết kế cần giới hạn:

- Số lượng channel và long-lived stream hoạt động.
- Số request chờ và thời gian chờ.
- Kích thước payload, fragmentation và buffer.
- Tần suất reconnect và retry.
- Kích thước message per route và số client đồng thời.

### 4.4. Keepalive, lease, resume và fragmentation

RSocket protocol hỗ trợ các tính năng nâng cao:

- **Keepalive:** kiểm tra tính sống của connection.
- **Leasing:** cấp quyền gửi số request nhất định trong khoảng thời gian bằng `LEASE`.
- **Resumption:** tiếp tục session sau mất kết nối nếu phía triển khai đã bật và giữ đủ state.
- **Fragmentation/reassembly:** chia message lớn thành nhiều frame khi cần.

Các capability này **không mặc định biến RSocket thành durable messaging**. Session resumption cần được cấu hình và có giới hạn state; không bảo đảm giữ message qua mọi lần restart/mất điện. Giao dịch quan trọng vẫn cần persistence, acknowledgment, retry có điều kiện và idempotency ở tầng ứng dụng.

## 5. So sánh RSocket, REST, SSE và WebSocket

| Tiêu chí | HTTP REST | SSE | WebSocket thuần | RSocket |
| --- | --- | --- | --- | --- |
| Kiểu giao tiếp | Request–response | Server → client stream | Full duplex message | 4 reactive interaction models |
| Client gửi dữ liệu liên tục trong 1 interaction | Không phải pattern thông thường | Không | Có | Có, Request-Channel |
| Server push | Polling/long response/HTTP streaming | Có | Có | Có, Request-Stream/channel và server-initiated requests |
| Backpressure application-level qua protocol | Phụ thuộc stack/cơ chế bổ sung | Không có REQUEST_N tương đương | Tự thiết kế | Có cho stream qua REQUEST_N |
| Multiplex logical request/stream trên một connection | HTTP/2 có multiplex ở transport | Tùy HTTP transport | Tự thiết kế ID/protocol | Có sẵn stream identifier |
| Metadata routing | URL/method/header | HTTP header | Tự thiết kế | Composite metadata, route |
| Trình duyệt gọi trực tiếp | Có | Có | Có | Cần RSocket JavaScript client qua WebSocket |
| Thích hợp cho | CRUD, public API | Notification một chiều | Realtime custom protocol | Reactive service-to-service, full duplex stream |

**RSocket không thay thế mọi HTTP API.** HTTP có ecosystem rất rộng về browser, CDN, cache, gateway, HTTP semantics, observability và public clients. RSocket có lợi khi các interaction pattern, streaming hai chiều và backpressure qua network thực sự mang lại giá trị.

**WebSocket cũng full-duplex**, nhưng chỉ cung cấp transport message; ứng dụng phải tự định nghĩa route, request ID, completion, demand, error và retry semantics. RSocket có sẵn các mô hình request/stream và flow control.

**SSE đơn giản hơn** cho notification server → browser, đặc biệt khi client không cần gửi stream ngược. Chọn SSE nếu chỉ cần server push một chiều trên HTTP thay vì triển khai cả RSocket stack.

### 5.1. Khi nào nên chọn RSocket?

Những tình huống đáng cân nhắc:

- Nhiều microservice dùng Reactor và phải trao đổi stream hai chiều.
- Client và server đều có thể chủ động tạo request.
- Tốc độ source/consumer chênh lệch và cần backpressure application-level.
- Có nhiều logical interaction trên một kết nối dài hạn.
- Cần typed routing, metadata và thống nhất lỗi/completion theo RSocket protocol.

Khi nào **không nên**:

- API công khai chủ yếu là CRUD request-response.
- Trình duyệt đơn giản chỉ cần SSE.
- Hệ thống cần lưu hàng đợi bền vững và replay sau nhiều ngày: message broker thường phù hợp hơn.
- Team không có khả năng vận hành và giám sát connection dài hạn.
- Middleware/gateway hiện có không hỗ trợ RSocket.

## 6. Spring Framework hỗ trợ RSocket thế nào?

### 6.1. RSocketRequester

`RSocketRequester` là fluent API của `spring-messaging` để gửi request với data và metadata ở mức object Java. Nó che giấu phần lớn buffer/frame-level logic.

~~~java
Mono<String> result = requester
    .route("catalog.lookup")
    .data("SKU-001")
    .retrieveMono(String.class);
~~~

Những API cần nhớ:

- `route("...")` đưa logical destination vào routing metadata.
- `data(value)` gửi một payload, hoặc `data(Flux, Class)` gửi stream payload.
- `retrieveMono(Target.class)` nhận tối đa một kết quả.
- `retrieveFlux(Target.class)` nhận stream kết quả.
- `send()` dùng cho Fire-and-Forget, trả `Mono<Void>`.
- `metadata(value, mimeType)` bổ sung metadata trên request khi dùng composite metadata.
- `sendMetadata()` gửi metadata-push ở mức connection.

Thông thường requester được tạo từ `RSocketRequester.Builder`:

~~~java
RSocketRequester requester =
    RSocketRequester.builder().tcp("localhost", 7000);
~~~

Việc tạo requester không đồng nghĩa network đã kết nối ngay. Connection được thiết lập khi thực sự phát sinh request; requester tái sử dụng connection theo lifecycle của nó.

### 6.2. @MessageMapping và @Payload

Spring hỗ trợ annotated responder với `@Controller` và `@MessageMapping`:

~~~java
@Controller
public class CatalogRSocketController {

    @MessageMapping("catalog.lookup")
    public Mono<String> lookup(@Payload String sku) {
        return Mono.just("Product:" + sku);
    }
}
~~~

`@Payload` chỉ rõ tham số nhận request data. Có thể dùng `@DestinationVariable` cho route parameter, `@Header` cho metadata đã được đăng ký extraction, hoặc `RSocketRequester` để gọi phía đối diện.

Route `catalog.lookup` không phải URL HTTP; không dùng `@GetMapping` để xử lý RSocket frame.

### 6.3. @ConnectMapping và SETUP

`@ConnectMapping` xử lý SETUP (và metadata push liên quan theo route). Handler có thể trả `void` hoặc `Mono<Void>`; không trả payload business.

~~~java
@ConnectMapping
public void onConnect() {
    log.info("RSocket connection setup received");
}
~~~

Nếu cần xác thực tại SETUP, thiết kế rõ metadata format và security policy. Không block trong `@ConnectMapping` và không chờ server-initiated request hoàn tất ngay tại SETUP.

### 6.4. RSocketStrategies và codec

`RSocketStrategies` giữ encoder/decoder, route matcher và các cấu hình serialization. Spring Boot có `spring-boot-starter-rsocket` sẽ tự cấu hình `RSocketStrategies`. Mặc định Boot ưu tiên CBOR qua Jackson khi phù hợp, sau đó là JSON theo dependency.

Khi tự tạo requester ngoài Boot, cần bảo đảm data MIME type và decoder/encoder khớp server. Không trông chờ các DTO phức tạp được serialize đúng nếu thiếu Jackson codec hoặc strategies thích hợp.

### 6.5. Route và composite metadata

Mặc định Spring dùng routing metadata để khớp `@MessageMapping`. Có thể bổ sung metadata như trace id, authentication hoặc protocol version.

~~~java
MimeType authType =
    MimeType.valueOf("message/x.rsocket.authentication.bearer.v0");

Flux<String> data = requester
    .route("telemetry.watch")
    .metadata(accessToken, authType)
    .data("sensor-A")
    .retrieveFlux(String.class);
~~~

Đây chỉ là minh họa vị trí metadata. Trong production, dùng Spring Security RSocket và codec cho định dạng authentication metadata đúng tiêu chuẩn, không tự gửi token thô sai encoding hoặc tin rằng metadata tự động được bảo vệ. Khi cần bí mật, cấu hình TLS, giới hạn route và kiểm soát quyền cả phía requester/responder.

### 6.6. @RSocketExchange

Spring Framework cũng có RSocket service interface qua `@RSocketExchange` và `RSocketServiceProxyFactory`. Đây là lựa chọn để khai báo contract typed cho requester. `@MessageMapping` thuận tiện cho responder với nhiều route pattern.

Có thể giữ cùng một service contract ở client và server nếu các method được thiết kế phù hợp với khả năng của interface proxy.

## 7. Spring Boot RSocket auto-configuration và transport

### 7.1. Starter và server TCP riêng

Spring Boot 3.5 có starter `spring-boot-starter-rsocket` cho RSocket server/client, Jackson CBOR/JSON strategies và messaging infrastructure.

Cấu hình TCP server độc lập:

~~~properties
spring.rsocket.server.port=7000
spring.rsocket.server.transport=tcp
spring.rsocket.server.address=127.0.0.1
~~~

Port 7000 của RSocket **không phải HTTP port**. Lệnh `curl http://localhost:7000/...` không gọi được RSocket protocol.

Boot sẽ auto-configure `RSocketMessageHandler` để tìm `@Controller` có `@MessageMapping`, và `RSocketRequester.Builder` cho client. Builder trong Boot là bean prototype vì nó có state cấu hình; không dùng chung một instance builder mutable để tạo nhiều requester có SETUP khác nhau.

### 7.2. RSocket over WebSocket

Nếu ứng dụng WebFlux dùng Reactor Netty, có thể tích hợp RSocket WebSocket với web server:

~~~properties
spring.rsocket.server.transport=websocket
spring.rsocket.server.mapping-path=/rsocket
server.port=8080
~~~

Khi đó client RSocket có thể dùng WebSocket transport tại URI phù hợp, ví dụ:

~~~java
RSocketRequester requester = builder
    .webSocket(URI.create("ws://localhost:8080/rsocket"));
~~~

Lưu ý:

- `spring.rsocket.server.mapping-path` chỉ áp dụng cho WebSocket transport.
- Không đồng thời nhầm TCP port riêng với HTTP server port.
- RSocket qua WebSocket vẫn là RSocket binary frames, không phải JSON message đơn thuần.
- Browser cần RSocket client implementation hỗ trợ WebSocket; không chỉ gọi `new WebSocket(...)` rồi gửi JSON tự do.
- Nếu dùng HTTPS, cần WebSocket TLS `wss://` và chính sách xác thực phù hợp.

### 7.3. Tùy chỉnh RSocketStrategies

Boot cho phép khai báo `RSocketStrategiesCustomizer` để thêm codec hoặc thay route matching. `@Order` của các customizer ảnh hưởng thứ tự đăng ký codec.

Tránh đổi chiến lược serialization của một phía mà không đổi phía còn lại; SETUP MIME type và payload codecs phải tương thích.

### 7.4. RSocketConnectorConfigurer

Boot có `RSocketConnectorConfigurer` để điều chỉnh connector, chẳng hạn keepalive, interceptors hoặc session resumption thông qua API cấp thấp của RSocket Java.

Đây là extension point nâng cao. Chỉ bật lease/resume khi thực sự có yêu cầu và đã kiểm thử các failure mode như reconnect, duplicate processing và message ordering.

## 8. Project Java 17 + Spring Boot 3.5.7: bốn pattern thật

Project dưới đây chạy RSocket server TCP và một integration test client dùng RSocketRequester. Nó minh họa cả bốn pattern, trong đó request-channel truyền các item client → server và nhận phản hồi server → client theo luồng.

### 8.1. Cấu trúc thư mục

~~~text
rsocket-duplex-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/example/rsocket/
    │   │   ├── RSocketDemoApplication.java
    │   │   └── DemoRSocketController.java
    │   └── resources/
    │       └── application.properties
    └── test/
        └── java/example/rsocket/
            └── RSocketPatternsTest.java
~~~

### 8.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>rsocket-duplex-demo</artifactId>
    <version>1.0.0</version>

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
~~~

Dùng starter RSocket thay vì chỉ thêm `spring-boot-starter-webflux`. RSocket server riêng không cần có HTTP controller.

### 8.3. application.properties

~~~properties
spring.main.web-application-type=none
spring.rsocket.server.port=7000
spring.rsocket.server.transport=tcp
spring.rsocket.server.address=127.0.0.1
logging.level.example.rsocket=INFO
~~~

Server lắng nghe RSocket trên loopback TCP 7000. Khi chạy môi trường container, điều chỉnh address/network policy tùy kiến trúc. Test bên dưới override port thành 0 để hệ điều hành chọn port trống.

### 8.4. RSocketDemoApplication.java

~~~java
package example.rsocket;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RSocketDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(RSocketDemoApplication.class, args);
    }
}
~~~

### 8.5. DemoRSocketController.java

~~~java
package example.rsocket;

import java.time.Duration;
import java.util.Locale;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.stereotype.Controller;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Controller
public class DemoRSocketController {

    private static final Logger log =
        LoggerFactory.getLogger(DemoRSocketController.class);

    // Request-Response: one input, one output.
    @MessageMapping("demo.hello")
    public Mono<String> hello(@Payload String name) {
        return Mono.just("Xin chào, " + name);
    }

    // Fire-and-Forget: no business response.
    @MessageMapping("demo.notify")
    public void notifyEvent(@Payload String event) {
        log.info("Received notification: {}", event);
    }

    // Request-Stream: one input, multiple outputs.
    @MessageMapping("demo.ticks")
    public Flux<String> ticks(@Payload String rawCount) {
        int count = Integer.parseInt(rawCount);
        if (count < 0 || count > 100) {
            return Flux.error(
                new IllegalArgumentException("count must be 0..100")
            );
        }

        return Flux.range(1, count)
            .delayElements(Duration.ofMillis(20))
            .map(index -> "tick-" + index);
    }

    // Request-Channel: streaming input and streaming output.
    @MessageMapping("demo.uppercase")
    public Flux<String> uppercase(@Payload Flux<String> incoming) {
        return incoming.map(value ->
            "echo:" + value.toUpperCase(Locale.ROOT));
    }
}
~~~

Giải thích:

- Method `hello` trả `Mono<String>` nên phù hợp Request-Response.
- `notifyEvent` trả `void`; client gửi bằng `send()`. Log minh họa xử lý, nhưng send completion không phải acknowledgment nghiệp vụ.
- `ticks` nhận một payload và trả `Flux<String>`, phù hợp Request-Stream; giới hạn count để tránh client yêu cầu stream quá lớn.
- `uppercase` nhận `Flux<String>` và trả `Flux<String>`, phù hợp Request-Channel. Mỗi input item có thể tạo response khi tới, không phải chờ toàn bộ input hoàn tất.

### 8.6. RSocketPatternsTest.java

~~~java
package example.rsocket;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.time.Duration;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.messaging.rsocket.RSocketRequester;

import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

@SpringBootTest(properties = "spring.rsocket.server.port=0")
class RSocketPatternsTest {

    @Autowired
    RSocketRequester.Builder builder;

    @Value("${local.rsocket.server.port}")
    int port;

    private RSocketRequester requester;

    @BeforeEach
    void connectRequester() {
        requester = builder.tcp("127.0.0.1", port);
    }

    @AfterEach
    void disposeRequester() {
        if (requester != null) {
            requester.dispose();
        }
    }

    @Test
    void requestResponse() {
        StepVerifier.create(
                requester.route("demo.hello")
                    .data("Linh")
                    .retrieveMono(String.class))
            .expectNext("Xin chào, Linh")
            .verifyComplete();
    }

    @Test
    void fireAndForget() {
        // Completion of send() does not prove business handling.
        StepVerifier.create(
                requester.route("demo.notify")
                    .data("created:42")
                    .send())
            .verifyComplete();
    }

    @Test
    void requestStream() {
        StepVerifier.create(
                requester.route("demo.ticks")
                    .data("3")
                    .retrieveFlux(String.class))
            .expectNext("tick-1", "tick-2", "tick-3")
            .verifyComplete();
    }

    @Test
    void requestChannelDuplex() {
        Flux<String> input = Flux.just("a", "b", "c")
            .delayElements(Duration.ofMillis(15));

        StepVerifier.create(
                requester.route("demo.uppercase")
                    .data(input, String.class)
                    .retrieveFlux(String.class))
            .expectNext("echo:A", "echo:B", "echo:C")
            .verifyComplete();
    }

    @Test
    void requestStreamRespectsBoundedDemand() {
        Flux<String> stream = requester.route("demo.ticks")
            .data("3")
            .retrieveFlux(String.class);

        StepVerifier.create(stream, 0)
            .thenRequest(1)
            .expectNext("tick-1")
            .thenRequest(2)
            .expectNext("tick-2", "tick-3")
            .verifyComplete();
    }
}
~~~

Trong test, `spring.rsocket.server.port=0` để Boot khởi động server ở một cổng ngẫu nhiên. `local.rsocket.server.port` chứa cổng thực tế. Boot cung cấp `RSocketRequester.Builder` với strategies tương thích server.

`StepVerifier` kiểm tra tín hiệu Publisher theo thứ tự mà không chặn event-loop production. Đây là test chạy ở test thread, việc `verifyComplete()` chờ kết quả là bình thường.

### 8.7. Chạy project

Yêu cầu: Java 17+, Maven, và cổng TCP 7000 chưa bị chiếm nếu chạy server ở chế độ thông thường.

~~~bash
mvn test
~~~

Khi test thành công, Maven báo các test RSocket request-response, fire-and-forget, stream, channel và demand đều pass. Các test mở kết nối thật tới RSocket TCP server do Spring Boot khởi động với port ngẫu nhiên.

Chạy server độc lập:

~~~bash
mvn spring-boot:run
~~~

Server lúc này lắng nghe RSocket TCP port 7000, **không có HTTP route** để thử bằng curl. Muốn gọi server ngoài JUnit test, dùng Java `RSocketRequester`, RSocket CLI (`rsc`) có hỗ trợ routing/MIME phù hợp, hoặc một RSocket client của ngôn ngữ khác.

Không đặt `subscribe()` hoặc `block()` vào handler chỉ để làm các phép thử này. Trong application code, trả `Mono/Flux` để framework quản lý subscription.

## 9. Server chủ động gọi client: duplex thực sự

Request-Channel đã truyền dữ liệu hai chiều trong cùng một logical interaction. Nhưng RSocket còn cho phép server mở một **request mới** tới client trên connection đang có.

### 9.1. Đăng ký client responder

Client phải có handler cho route mà server muốn gọi:

~~~java
public class ClientCallbackHandler {

    @MessageMapping("client.ping")
    public Mono<String> ping(@Payload String message) {
        return Mono.just("client-ack:" + message);
    }
}
~~~

Đoạn trên là class bổ sung, không thuộc project demo ở mục 8. Khi tự đăng ký responder, cấu hình RSocket strategies, route matcher và SocketAcceptor:

~~~java
RSocketStrategies strategies = RSocketStrategies.builder()
    .routeMatcher(new PathPatternRouteMatcher())
    .build();

SocketAcceptor responder =
    RSocketMessageHandler.responder(
        strategies, new ClientCallbackHandler());

RSocketRequester requester = RSocketRequester.builder()
    .rsocketStrategies(strategies)
    .rsocketConnector(connector -> connector.acceptor(responder))
    .tcp("127.0.0.1", 7000);
~~~

Ví dụ nâng cao này giả định đã import các API và thêm module `spring-web` để có `PathPatternRouteMatcher`. Với data type phức tạp, cần đăng ký thêm codec tương thích với server.

### 9.2. Server nhận requester của client

Một `@MessageMapping` hoặc `@ConnectMapping` ở server có thể nhận `RSocketRequester` cho connection hiện tại:

~~~java
@MessageMapping("server.ask-client")
public Mono<String> askClient(
    @Payload String question,
    RSocketRequester clientRequester
) {
    return clientRequester.route("client.ping")
        .data(question)
        .retrieveMono(String.class);
}
~~~

Server lúc này trở thành requester đối với route `client.ping` do client cung cấp.

**Không nhầm:** Server không thể tự gọi route client nếu client không đăng ký responder phù hợp. Việc kết nối TCP/WebSocket không tự cung cấp một danh sách callback của client.

### 9.3. Cẩn trọng với SETUP lifecycle

`@ConnectMapping` xử lý SETUP trước khi connection sẵn sàng phục vụ các request tiếp theo. Nếu muốn server yêu cầu client báo trạng thái ngay sau connect, phải decouple lời gọi đó khỏi Mono/void đang xử lý SETUP; không tạo vòng chờ lẫn nhau.

Trong production, giữ bản đồ connection/requester theo session identity có kiểm soát; xóa khi connection đóng; giới hạn số session; tránh giữ requester đã dispose; và định nghĩa authentication/authorization cho cả chiều client→server lẫn server→client.

## 10. Lỗi, timeout, reconnect và an toàn dữ liệu

### 10.1. Error signal và timeout

RSocket không trả status HTTP 404 hoặc 500 theo cách REST. Handler có thể phát lỗi trong Publisher:

~~~java
@MessageMapping("demo.invalid")
public Mono<String> invalid(@Payload String data) {
    return Mono.error(
        new IllegalArgumentException("Invalid payload"));
}
~~~

Phía requester nhận error signal tương ứng. Không giả định mọi exception phía server được giữ nguyên type hoặc message Java sau khi đi qua network; mapping lỗi phụ thuộc RSocket/Spring và serialization.

Timeout nên được áp dụng ở tầng use case:

~~~java
Mono<String> result = requester.route("demo.hello")
    .data("Linh")
    .retrieveMono(String.class)
    .timeout(Duration.ofSeconds(3));
~~~

Timeout làm consumer hủy subscription khi quá thời hạn. Cần xử lý việc server có thể đã thực hiện side effect trước khi requester timeout. Nếu thao tác ghi có thể lặp, dùng idempotency key hoặc deduplication.

### 10.2. Retry, reconnect và resumption

Không retry mọi request khi connection bị reset. Với Request-Response tra cứu thuần đọc, retry có điều kiện thường an toàn hơn. Với payment, order creation và Fire-and-Forget, retry có thể tạo side effect trùng.

Một retry policy an toàn cần:

- Chỉ retry exception được phân loại transient.
- Giới hạn số lần thử và tổng deadline.
- Dùng exponential backoff có jitter.
- Xem xét idempotency và khả năng replay của Publisher input.
- Ngăn reconnect storm khi dịch vụ downstream gặp sự cố.
- Có circuit breaker/rate limit phù hợp với hệ thống.

Resumption của RSocket không thay thế database, log bền vững hoặc durable queue. Phải kiểm thử restart, mất mạng lâu và duplicate delivery.

### 10.3. Security

RSocket traffic không tự động được mã hóa và xác thực. Cần thiết kế:

1. TLS trên TCP hoặc WebSocket bảo mật.
2. Identity và authentication trên SETUP hoặc request metadata theo cơ chế chuẩn.
3. Authorization theo route và theo chiều giao tiếp.
4. Bảo vệ token/credential khỏi log và error message.
5. Giới hạn payload size, concurrent streams và số request mỗi connection.
6. Không tin route/metadata do client gửi mà không validate.
7. Xác thực và phân quyền cả server-initiated callback.

Spring Security có hỗ trợ RSocket Security để xử lý authentication/authorization. Đừng tự thiết kế token format không tương thích hoặc bỏ qua TLS chỉ vì kết nối giữ lâu.

### 10.4. Observability

Ghi nhận:

- Connection count, reconnect và setup failures.
- Active streams theo route.
- Stream duration, throughput, REQUEST_N/demand và cancellation.
- Lỗi theo route và loại lỗi.
- Payload size, buffer memory, queue depth.
- Latency của request-response và end-to-end channel processing.

Không log raw payload hoặc metadata token mặc định. Chọn route name làm low-cardinality tag; tránh đặt user ID hoặc random session ID vào metric label.

## 11. Các lỗi phổ biến khi bắt đầu với RSocket

**Lỗi 1 — Gọi RSocket bằng HTTP curl.** TCP port RSocket dùng binary frames, không phải HTTP endpoint. Dùng RSocketRequester hoặc client RSocket khác.

**Lỗi 2 — Coi WebSocket và RSocket là cùng một protocol.** WebSocket là transport message, còn RSocket có requester/responder, interaction model, metadata, demand và error semantics.

**Lỗi 3 — Nghĩ RSocket request-channel là request-response.** Channel nhận stream ở hai chiều. Dùng `Flux` input và `retrieveFlux` khi cần many-to-many.

**Lỗi 4 — Gửi Flux nhưng dùng retrieveMono và kỳ vọng trả nhiều item.** Kiểm tra cardinality của input/output và handler; Spring suy ra model từ đó.

**Lỗi 5 — Fire-and-Forget được xem như đã xử lý nghiệp vụ.** `send()` chỉ báo gửi message thành công; không chứng minh DB đã commit.

**Lỗi 6 — Không quản lý subscription của stream dài.** Nguồn có thể tiếp tục chạy khi caller không cần. Dùng cancel, dispose và cleanup.

**Lỗi 7 — Bỏ qua backpressure với hot source.** REQUEST_N chỉ điều khiển những producer tôn trọng demand. Queue không giới hạn vẫn có thể tràn.

**Lỗi 8 — Truyền DTO nhưng thiếu Jackson codec.** Kiểm tra `RSocketStrategies` và data MIME type của hai phía.

**Lỗi 9 — Nhầm route metadata với URL.** `@MessageMapping` match logical route; không dùng HTTP `@GetMapping` cho RSocket.

**Lỗi 10 — Bật WebSocket mapping-path rồi kết nối sai TCP port.** WebSocket transport dùng URI và server WebFlux Reactor Netty, khác TCP server độc lập.

**Lỗi 11 — Tái sử dụng mutable RSocketRequester.Builder cho nhiều setup không đồng nhất.** Builder Boot là prototype; tạo requester theo mục đích, không mutate builder chung.

**Lỗi 12 — Dùng block() trong controller reactive.** Có thể block event loop. Giữ Mono/Flux và xử lý bất đồng bộ.

**Lỗi 13 — Retry mọi request không idempotent.** Dễ tạo side effect trùng và retry storm. Định nghĩa idempotency, backoff và deadline.

**Lỗi 14 — Tin rằng resume bảo đảm giao hàng bền vững.** Resume cần state và cấu hình; không thay durable message broker.

**Lỗi 15 — Cho server gọi client khi client chưa đăng ký responder.** Phải gắn SocketAcceptor và route handler thích hợp.

**Lỗi 16 — Chờ request server→client ngay trong @ConnectMapping.** Setup chưa hoàn tất có thể gây vòng chờ. Decouple callback khỏi setup lifecycle.

**Lỗi 17 — Không bảo mật TCP và metadata.** RSocket không mặc định cung cấp TLS, auth hoặc authorization policy.

**Lỗi 18 — Dùng RSocket cho mọi CRUD endpoint.** Chi phí triển khai/observability/gateway không đáng nếu chỉ cần HTTP request-response.

## 12. Checklist thiết kế trước production

1. Workload cần request-response, Fire-and-Forget, request-stream hay request-channel?
2. Có thật sự cần duplex hoặc server-initiated requests không?
3. Consumer có cần kiểm soát producer bằng backpressure qua network không?
4. Source có thể phát dữ liệu vượt demand hay tạo queue không giới hạn không?
5. Có giới hạn kích thước payload và số active stream per connection không?
6. Transport chọn TCP hay WebSocket? Browser có RSocket JS client chưa?
7. MIME type, codec và routing metadata ở hai phía có tương thích không?
8. SETUP lifecycle và @ConnectMapping có không block không?
9. Client responder có đăng ký nếu server cần request ngược không?
10. TLS, authentication, authorization và metadata handling đã đúng chưa?
11. Timeout, cancellation và cleanup khi client disconnect đã được kiểm thử chưa?
12. Retry có tính idempotency và replayable Publisher không?
13. Có cần leasing/resumption hay durable message broker mới đúng yêu cầu?
14. Có metric cho connection, demand, error và stream lifecycle không?
15. Có integration test đủ cả bốn interaction model không?

## 13. Bài tập tự kiểm tra

1. RSocket là gì? **Binary application protocol cung cấp multiplexed duplex reactive interactions trên byte-stream transport.**
2. “Requester” khác “responder” thế nào? **Requester khởi tạo interaction; responder xử lý và trả signal.**
3. Sau SETUP, bên mở TCP connection có luôn là requester không? **Không; cả hai phía có thể khởi tạo interaction.**
4. Bốn pattern cốt lõi là gì? **Request-Response, Fire-and-Forget, Request-Stream, Request-Channel.**
5. Pattern nào có streams hai chiều trong cùng một interaction? **Request-Channel.**
6. Pattern nào gửi một request, nhận nhiều item? **Request-Stream.**
7. `send()` có chứng minh server xử lý business thành công không? **Không, chỉ báo message được gửi theo protocol.**
8. `REQUEST_N` có nhiệm vụ gì? **Chuyển demand của consumer tới producer trong stream.**
9. `CANCEL` có vai trò gì? **Báo không còn cần stream, giúp phía phát dừng và giải phóng tài nguyên.**
10. Một TCP connection có thể có nhiều logical interaction không? **Có, nhờ stream identifier và multiplexing.**
11. Route RSocket có phải URL HTTP không? **Không; nó là logical destination trong metadata.**
12. Annotation nào tạo responder trong Spring? **`@MessageMapping` trên `@Controller`.**
13. Spring Boot starter nào hỗ trợ server/client RSocket? **`spring-boot-starter-rsocket`.**
14. Spring Boot config mở TCP port dùng property nào? **`spring.rsocket.server.port`.**
15. RSocket over WebSocket trong Boot có dùng property mapping-path không? **Có; kết hợp với transport=websocket.**
16. DTO serialization phụ thuộc thành phần nào? **`RSocketStrategies` cùng encoder/decoder và MIME type.**
17. Vì sao request-channel không tự động cho server gọi callback client? **Server-initiated request mới cần client có responder và server có requester của connection.**
18. Có thể dùng `@ConnectMapping` làm nơi chờ server→client callback trả lời không? **Không; phải hoàn tất SETUP trước.**
19. Vì sao resumption không thay message broker? **Nó cần state/giới hạn và không bảo đảm lưu trữ bền vững qua mọi failure.**
20. Khi nào HTTP/SSE hợp lý hơn RSocket? **Khi ứng dụng chủ yếu CRUD hoặc chỉ cần server push một chiều cho browser.**

## 14. Ghi nhớ và tài liệu tham khảo

- RSocket là binary application protocol, không phải HTTP hay WebSocket thuần.
- Giao tiếp hai chiều có hai mức: `Request-Channel` truyền stream ở hai hướng và **server-initiated request** khi phía client cũng có responder.
- Requester/responder là vai trò theo interaction, không phải vai trò server/client bất biến.
- Bốn model: Request-Response, Fire-and-Forget, Request-Stream và Request-Channel.
- `REQUEST_N` truyền demand qua network; `CANCEL` và `COMPLETE` quản lý lifecycle stream.
- Multiplex giúp nhiều logical stream dùng chung connection, nhưng vẫn phải giới hạn concurrency/buffer.
- Spring dùng `RSocketRequester` để gọi, `@MessageMapping` để xử lý, `@ConnectMapping` cho setup và `RSocketStrategies` cho codec.
- Spring Boot 3.5 có `spring-boot-starter-rsocket`, TCP server properties và WebSocket mapping path.
- `send()` không phải business acknowledgment; TLS/security, timeout, reconnect, idempotency và observability do ứng dụng thiết kế.
- RSocket bổ sung cho HTTP/SSE/WebSocket; chọn theo interaction shape và yêu cầu vận hành.

**Tài liệu chính thức**

1. [Spring Framework — RSocket reference](https://docs.spring.io/spring-framework/reference/rsocket.html): overview, protocol, request patterns, RSocketRequester, annotated responders và metadata.
2. [Spring Boot 3.5 — RSocket](https://docs.spring.io/spring-boot/3.5/reference/messaging/rsocket.html): starter, RSocketStrategies, server TCP/WebSocket, requester builder auto-configuration.
3. [RSocket Protocol Specification](https://rsocket.io/about/protocol/): SETUP, REQUEST_N, CANCEL, REQUEST_CHANNEL, REQUEST_FNF, leasing, resumption.
4. [Spring Framework — RSocketRequester Javadoc](https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/messaging/rsocket/RSocketRequester.html): fluent API, send, retrieveMono, retrieveFlux.
5. [Spring Boot 3.5 — RSocket properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html): TCP port, transport, mapping path, SSL, fragmentation.
6. [Project Reactor Reference](https://projectreactor.io/docs/core/release/reference/): Mono, Flux, subscribeOn, backpressure, retry, cancellation và StepVerifier.
