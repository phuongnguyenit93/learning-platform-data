
# Điều kiện lựa chọn RSocket so với WebClient, SSE hoặc WebSocket trong Spring Reactive

## 1. Mục tiêu của bài học

Không phải ứng dụng reactive nào cũng cần RSocket. Một API CRUD thông thường có thể hoạt động tốt với HTTP và `WebClient`. Một bảng thông báo cập nhật từ server tới browser thường chỉ cần Server-Sent Events (SSE). Chat hoặc trò chơi thời gian thực có thể dùng WebSocket. RSocket nổi bật khi hệ thống cần **nhiều kiểu tương tác hai chiều, các luồng thông điệp kéo dài và cơ chế backpressure ở cấp giao thức giữa các tiến trình**, đồng thời kiểm soát được client, server và hạ tầng truyền dẫn.

Bài học trả lời các câu hỏi:
- Bốn interaction model của RSocket khác request-response HTTP, SSE và WebSocket như thế nào?
- RSocket cung cấp backpressure, multiplexing, keepalive, leasing và resumption ra sao?
- Chọn WebClient, SSE, WebSocket hay RSocket theo chiều dữ liệu, client, hạ tầng, độ tin cậy, vận hành và chi phí?
- Những trường hợp nào RSocket tạo thêm phức tạp mà lợi ích không đáng kể?
- Cấu hình Spring Boot và Java 17+ để thử một RSocket requester/responder với request-response, request-stream, request-channel và fire-and-forget như thế nào?
- Làm sao kiểm thử, đo lường và triển khai một quyết định có thể bảo vệ được?

**Phạm vi:** Spring Framework 6.2+/7.x, Spring Boot 3.5.x và Reactor. Bài tập runnable dùng Spring Boot 3.5.x và Java 17+, phân biệt phần mã độc lập với các snippet minh họa.

## 2. Định vị đúng bốn khái niệm

Trước khi so sánh, cần tránh một lỗi phân loại:

- **WebClient** là HTTP client API của Spring WebFlux. Nó gửi HTTP/1.1 hoặc HTTP/2 tùy connector; có thể lấy một response JSON, download tệp, hoặc đọc một HTTP response streaming như SSE.
- **SSE** là cách server phát luồng sự kiện một chiều về client qua HTTP với media type `text/event-stream`; browser thường dùng `EventSource`.
- **WebSocket** là giao thức duy trì kết nối hai chiều với các message/frame; browser có native WebSocket API.
- **RSocket** là application protocol với bốn interaction model, định tuyến metadata, multiplexing và Reactive Streams demand qua mạng; nó chạy **trên TCP hoặc WebSocket** chứ không đơn giản là một loại HTTP request.

Do vậy “RSocket hay WebClient” không phải so sánh hai API cùng tầng. Thực chất ta lựa chọn **giao thức/kiểu tương tác** cho một use case; sau đó dùng client tương ứng: WebClient cho HTTP, RSocketRequester cho RSocket, EventSource/WebClient cho SSE hoặc WebSocketHandler/WebSocketClient cho WebSocket.

### 2.1. Bảng định vị ban đầu

| Tiêu chí | HTTP với WebClient | SSE | WebSocket | RSocket |
| --- | --- | --- | --- | --- |
| Vai trò | Client HTTP với semantics request-response | Luồng server → client trên HTTP | Transport message hai chiều | Protocol messaging với bốn interaction model |
| Gửi hai chiều trên cùng connection theo application message | Không theo mô hình API truyền thống; mỗi HTTP request có chiều request và response | Không; client gửi yêu cầu khác qua HTTP | Có | Có; cả hai peer có thể làm requester và responder |
| Một request → nhiều kết quả liên tục | Có thể stream HTTP body/SSE | Thiết kế riêng cho việc này | Có nhưng tự thiết kế message protocol | Request-Stream |
| Nhiều message vào ↔ nhiều message ra | Không có abstraction request-channel chuẩn như RSocket | Không | Có nếu tự xây protocol | Request-Channel |
| Backpressure xuyên network ở cấp application message | Không có REQUEST_N như RSocket; HTTP/TCP có cơ chế flow control | Không có demand protocol từ EventSource | Không có Reactive Streams demand trong WebSocket protocol | Có REQUEST_N cho streaming interactions |
| Khả năng browser | HTTP API native, fetch | EventSource native | WebSocket native | Cần RSocket client/library, thường qua WebSocket |
| Gateway/CDN/cache HTTP | Tích hợp rất tốt | Có thể dùng HTTP edge nhưng stream cần proxy tuning | Cần hỗ trợ nâng cấp/duy trì WebSocket | TCP cần hỗ trợ riêng; RSocket-over-WebSocket cần tương thích |
| Chi phí tích hợp | Thấp nếu stack HTTP sẵn có | Thấp cho thông báo một chiều | Trung bình: message contract, reconnect | Cao hơn: protocol, codecs, connection lifecycle, operation support |
| Điển hình | CRUD, REST, public API, service calls | Notifications/dashboard/live feed | Chat, collaboration, browser interaction | Streaming RPC, telemetry, bidirectional service-to-service |

Bảng là hướng dẫn kiến trúc, không phải khẳng định giao thức nào “nhanh nhất” trong mọi hoàn cảnh.

## 3. Bốn kiểu tương tác RSocket và cách suy ra use case

RSocket có bốn interaction model chuẩn. Mỗi interaction được mở trên một kết nối đã thiết lập; kết nối có thể chứa nhiều stream logic cùng lúc.

| RSocket interaction | Payload gửi đi | Payload trả về | Spring requester |
| --- | --- | --- | --- |
| Request-Response | Một request | Không hoặc một response | `retrieveMono(T.class)` |
| Request-Stream | Một request | Nhiều response theo stream | `retrieveFlux(T.class)` |
| Fire-and-Forget | Một message | Không đợi response nghiệp vụ | `send()` |
| Request-Channel | Stream message gửi đi | Stream message nhận về | `data(Flux<T>, T.class).retrieveFlux(R.class)` |

### 3.1. Request-Response

Một bên gửi thông điệp và nhận đúng một kết quả (hoặc lỗi).

```text
Requester ------ request ------> Responder
Requester <----- response ------ Responder
```

Gần với HTTP GET/POST về cách người lập trình suy nghĩ, nhưng không có sẵn HTTP status, cache validators, URL routing, CDN semantics, OpenAPI tooling hay hệ sinh thái proxy HTTP. Nếu ứng dụng chỉ có một vài CRUD call, **HTTP/WebClient thường là lựa chọn đơn giản hơn**.

### 3.2. Request-Stream

Một request duy nhất yêu cầu nhiều phần tử phản hồi qua thời gian:

```text
Requester --- subscribe sensor.temp ---> Responder
Requester <-------- temperature 1 ----- Responder
Requester <-------- temperature 2 ----- Responder
Requester <-------- temperature 3 ----- Responder
```

RSocket có signal demand: requester yêu cầu một số lượng phần tử, responder phải tôn trọng demand. Demand được mang theo initial request và các frame `REQUEST_N` sau đó.

SSE cũng rất phù hợp nếu người nhận là browser và luồng chỉ cần server → browser. RSocket có giá trị hơn khi muốn cùng một hệ thống sử dụng thêm request-channel, multiplex nhiều RPC stream hoặc kiểm soát backpressure xuyên mạng.

### 3.3. Fire-and-Forget

Một message được gửi mà không cần một application response:

```text
Requester ------ event ------> Responder
           (không có response nghiệp vụ)
```

Trong Spring, `send()` trả `Mono<Void>`. Mono này biểu thị thao tác gửi hoàn tất, **không chứng minh handler phía nhận đã xử lý thành công**, càng không bảo đảm dữ liệu đã được ghi xuống storage. Với payment, audit quan trọng hoặc sự kiện cần durable delivery, nên thiết kế xác nhận nghiệp vụ riêng hoặc dùng message broker bền vững.

### 3.4. Request-Channel

Hai chiều đều là luồng; cả hai có thể gửi nhiều message trong cùng interaction:

```text
Requester ---- reading A ------------> Responder
Requester <--- normalized A ---------- Responder
Requester ---- reading B ------------> Responder
Requester ---- reading C ------------> Responder
Requester <--- normalized B ---------- Responder
Requester <--- normalized C ---------- Responder
```

Đây là lý do mạnh để cân nhắc RSocket trong hệ thống service-to-service hoặc telemetry: giao thức đã có mẫu many-to-many và cơ chế demand đi kèm, không phải tự đặt action IDs, ack, request correlation và flow-control control messages bên trên WebSocket.

Tuy nhiên, WebSocket cũng có thể thực hiện bài toán đó khi ứng dụng định nghĩa protocol riêng; không phải không thể làm bằng WebSocket.

### 3.5. Hai peer đối xứng

Sau khi kết nối được thiết lập, cả hai phía có thể đóng vai requester hoặc responder cho những interaction khác nhau. Đây là duplex messaging, không chỉ là client mở kết nối rồi server thụ động trả response.

Ứng dụng vẫn phải thực hiện authentication/authorization cho cả các route phía client và server. Đừng suy luận rằng connection đã mở thì mọi route đều được phép gọi.

## 4. RSocket backpressure khác streaming thông thường thế nào?

RSocket tích hợp Reactive Streams semantics qua network. Với request-stream và request-channel, một phía có thể thông báo số message nó sẵn sàng nhận.

Ví dụ minh họa:

```text
Client                        Server
  | ---- REQUEST_STREAM ------> |
  |       demand = 2            |
  | <------ PAYLOAD #1 -------- |
  | <------ PAYLOAD #2 -------- |
  | ---- REQUEST_N(3) --------> |
  | <------ PAYLOAD #3 -------- |
  | <------ PAYLOAD #4 -------- |
  | <------ PAYLOAD #5 -------- |
```

Điểm khác biệt là demand có ý nghĩa ở **cấp message của giao thức**, không chỉ TCP receive window hoặc buffering trong thư viện client.

Cần phân biệt:

1. **Reactor backpressure** điều tiết publisher/subscriber trong ứng dụng.
2. **TCP hoặc HTTP/2 flow control** điều tiết byte trên network.
3. **RSocket REQUEST_N** truyền demand cho số lượng application payload messages giữa peer.

RSocket giảm nguy cơ producer nhanh hơn consumer trong streaming RPC, nhưng không bảo đảm memory vô hạn, không thay thế giới hạn concurrency/connection pool, và không tự biến blocking database code thành non-blocking.

Spring WebFlux WebSocketHandler sử dụng Reactor publishers và một số connector có điều tiết theo backpressure nội bộ. Tuy nhiên, **WebSocket protocol không định nghĩa REQUEST_N tương đương RSocket**. Nếu cần credit-based flow control ở cấp message, application chạy trên WebSocket thường phải tự xây.

SSE dùng HTTP response streaming. Browser EventSource không cung cấp API gửi demand của từng message tới server. Nếu server phát quá nhanh, cần giới hạn tốc độ, buffer/drop policy, network flow control hoặc backpressure từ publisher/transport tương ứng.

## 5. RSocket có gì ngoài bốn interaction model?

### 5.1. Multiplexing

Một TCP hoặc WebSocket connection có thể chứa nhiều RSocket interaction đồng thời. Điều này giúp tránh mở một socket cho mỗi RPC stream và tránh tự phân biệt message của nhiều yêu cầu trên cùng connection.

Multiplexing không có nghĩa luôn ít latency nhất. Overhead mã hóa, batching, kích thước frame, network hops, CPU, scheduler và upstream service mới là yếu tố đo được.

### 5.2. Routing metadata và codec

Một request mang route, data và metadata. Route như `sensor.stream` được Spring `@MessageMapping` xử lý; payload có thể được encode bằng JSON, CBOR hoặc codec khác theo `RSocketStrategies`.

RSocket không mang sẵn HTTP method/status/header semantics. Khi chuyển API từ HTTP sang RSocket, cần thiết kế lại cách biểu diễn lỗi, versioning, authentication metadata, tracing và timeout.

### 5.3. Keepalive

RSocket có keepalive frames để theo dõi trạng thái connection. Điều đó giúp phát hiện kết nối chết, nhưng không có nghĩa message tự động được replay hoặc business transaction được hoàn tất sau khi mạng đứt.

### 5.4. Leasing (tùy chọn)

RSocket hỗ trợ LEASE frames: peer có thể giới hạn số request được phép mở trong một khoảng thời gian. Đây là **request throttling ở cấp connection**, không giống REQUEST_N điều tiết số phần tử của stream.

Leasing không phải cấu hình bắt buộc hoặc được bật mặc định ở mọi triển khai. Chỉ phụ thuộc vào lease khi đã cấu hình và kiểm tra cả hai peer.

### 5.5. Session resumption (tùy chọn)

RSocket có cơ chế resumption để tiếp tục session khi mất kết nối tạm thời nếu implementation, cả hai peer và hạ tầng hỗ trợ, và có đủ state cần duy trì.

Không được suy ra rằng RSocket:
- Tự retry mọi request an toàn.
- Có durable storage cho message.
- Có exactly-once business processing.
- Bảo đảm không mất event khi server restart.
- Tự replay stream lịch sử nếu app không có nguồn lưu trữ.

Những bảo đảm đó yêu cầu thiết kế **idempotency, offset/cursor, persistence, replay policy, reconnect logic và test failover** riêng.

### 5.6. Transport lựa chọn: TCP hoặc WebSocket

RSocket **không phải WebSocket** nhưng có thể chạy trên WebSocket. Với client browser, thường phải dùng thư viện RSocket JavaScript qua WebSocket; browser native WebSocket API không hiểu RSocket frame, route hoặc REQUEST_N.

RSocket TCP cho service-to-service trực tiếp có thể thuận lợi trong mạng nội bộ, nhưng HTTP ingress, CDN, API gateway và firewall không nhất thiết hỗ trợ route TCP tùy chỉnh. RSocket-over-WebSocket hữu ích khi hạ tầng chỉ cho phép WebSocket, song vẫn cần kiểm tra proxy timeout, max frame, TLS và hỗ trợ subprotocol.

## 6. Khi nào nên giữ HTTP và WebClient?

**Chọn WebClient/HTTP trước** nếu giao tiếp có các đặc điểm:

- Một request nhận một response là chủ đạo.
- API công khai cho browser, mobile, đối tác hoặc bên thứ ba.
- Dùng REST semantics, status code, HTTP auth, caching, ETag, Range Requests, content negotiation.
- Tổ chức có sẵn ingress, WAF, API gateway, service mesh, CDN, OpenAPI và HTTP observability.
- Dễ chạy curl/Postman, dễ debug và onboarding đội ngũ.
- Không cần native request-channel hoặc cross-process demand signals.
- Có HTTP/2 nếu muốn multiplex, hoặc SSE nếu muốn stream response.

Ví dụ Spring WebClient:

```java
WebClient client = WebClient.builder()
        .baseUrl("https://orders.example.test")
        .build();

Mono<OrderDto> order = client.get()
        .uri("/orders/{id}", 42)
        .retrieve()
        .bodyToMono(OrderDto.class);
```

Đây là **snippet minh họa**: OrderDto là DTO của ứng dụng và endpoint giả định. Http request có thể dùng HTTP/1.1 hoặc HTTP/2 tùy connector; đó là vấn đề khác với dùng RSocket.

Khi cần response streaming trên HTTP, WebClient cũng có thể đọc `Flux<ServerSentEvent<T>>`, `application/x-ndjson` hoặc payload streaming thích hợp. Không nhất thiết nâng cả hệ thống sang RSocket chỉ vì return type là Flux.

### 6.1. HTTP/2 không biến WebClient thành RSocket

HTTP/2 cho phép nhiều HTTP streams trên cùng connection và có connection/stream flow control ở cấp byte. Nhưng HTTP vẫn có request-response semantics. Nó không tự định nghĩa request-channel many-to-many với REQUEST_N application message như RSocket.

### 6.2. REST API có thể tồn tại song song với RSocket

Một kiến trúc cân bằng thường là:

```text
Browser / Partner / Public clients
         |
      HTTPS REST
         |
     API Gateway
         |
     WebFlux API
         |
   +-----+-----------------+
   |                       |
HTTP/WebClient       Internal RSocket
   |                       |
CRUD services           live telemetry
```

Chỉ chuyển luồng thực sự cần khả năng RSocket; giữ phần còn lại trên HTTP để tránh migration toàn diện và duy trì khả năng tương thích.

## 7. Khi nào chọn SSE thay vì RSocket?

SSE phù hợp khi **server liên tục gửi thông báo đến browser, còn browser không cần gửi message trên cùng stream**.

Tình huống:

- Dashboard cập nhật số liệu định kỳ.
- Thông báo trạng thái xử lý job.
- Live feed đơn giản hoặc cập nhật tiến độ.
- Tỷ giá, giá cổ phiếu, log ngắn hoặc phát sự kiện hiển thị.
- UI nhận event, còn lệnh từ user được gửi bằng POST/PUT HTTP riêng.

SSE sử dụng `text/event-stream`. Browser `EventSource` hỗ trợ reconnect tự động. Nếu server gửi event ID, client có thể gửi `Last-Event-ID` khi kết nối lại, nhưng replay thực sự đòi hỏi server có event history và logic đọc từ ID đó.

### 7.1. Ví dụ SSE WebFlux

```java
@RestController
public class LiveController {

    @GetMapping(
            value = "/events",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<ServerSentEvent<String>> events() {
        return Flux.interval(Duration.ofSeconds(1))
                .map(n -> ServerSentEvent.<String>builder()
                        .id(Long.toString(n))
                        .event("update")
                        .data("tick-" + n)
                        .build());
    }
}
```

Browser:

```javascript
const stream = new EventSource("/events");

stream.addEventListener("update", event => {
    console.log(event.lastEventId, event.data);
});

stream.onerror = error => {
    console.error("Stream connection problem", error);
};
```

Ví dụ này tạo ID từ đầu trên mỗi subscription, **không có event store và không thực hiện replay**. Dùng để minh họa API, không phải một giải pháp reliable delivery.

### 7.2. Ưu thế thực tế của SSE

- Browser API trực tiếp, không cần thư viện protocol riêng.
- Chạy trên HTTP, dễ tích hợp authentication theo mô hình web và reverse proxy có hỗ trợ streaming.
- Format text dễ kiểm tra bằng curl với `-N`.
- EventSource có cơ chế reconnect và event ID.
- Không cần xây hệ thống message types hai chiều nếu UI chỉ nhận cập nhật.

Giới hạn:
- Chỉ server → client trên một stream SSE; hành động client gửi bằng request HTTP khác.
- EventSource không cung cấp protocol backpressure request-N.
- Cần heartbeat/comment để tránh idle timeout của proxy.
- Proxy buffering, timeout, giới hạn kết nối browser khi HTTP/1.1 và memory per client phải được đánh giá.
- Dữ liệu nhạy cảm cần auth, CORS và bảo vệ token; không đặt credential trong URL tùy tiện.

**Quy tắc:** Nếu đây là “server push cho browser” đơn thuần, hãy thử SSE trước RSocket.

## 8. Khi nào chọn WebSocket thay vì RSocket?

WebSocket có kênh gửi/nhận message hai chiều, native trong browser. Nó phù hợp khi cần tương tác thời gian thực từ cả hai phía nhưng không cần chuẩn RPC/backpressure riêng của RSocket.

Ví dụ:
- Chat một phòng hoặc nhiều phòng.
- Whiteboard/collaboration.
- Multiplayer game.
- Browser gửi thao tác liên tục, server trả thông điệp theo thời gian thực.
- Hệ sinh thái hiện có dùng STOMP/WebSocket, Socket.IO hoặc protocol tùy chỉnh.

Một WebSocket connection có thể chứa message JSON/binary theo contract ứng dụng:

```json
{"type":"chat.send","requestId":"abc-42","room":"dev","text":"hello"}
```

Nhưng WebSocket protocol không quy định route RPC, correlation response, stream cardinality, per-stream request-N hoặc durable event delivery. Ứng dụng có thể tự triển khai các tính năng này; điều đó làm tăng công sức và độ phức tạp giao thức.

### 8.1. Ví dụ WebFlux WebSocketHandler

```java
public final class EchoWebSocketHandler implements WebSocketHandler {

    @Override
    public Mono<Void> handle(WebSocketSession session) {
        Flux<WebSocketMessage> output = session.receive()
                .map(WebSocketMessage::getPayloadAsText)
                .map(text -> session.textMessage("echo:" + text));

        return session.send(output);
    }
}
```

Đây là **mã minh họa cho handler**, cần khai báo bean và URL mapping phù hợp trong WebFlux config. Kết nối WebSocket mở hai chiều; việc gọi session.send nhận Publisher và gắn vòng đời send với inbound stream. Khi triển khai thực tế phải giới hạn kích thước message, xử lý phiên đóng, session auth, origin và pressure ở application/connector.

### 8.2. Khi nào RSocket tốt hơn WebSocket?

RSocket có lợi khi muốn:
- Cùng một kết nối có nhiều request-response, request-stream và request-channel độc lập.
- REQUEST_N across-network backpressure theo từng interaction.
- Route và metadata có semantics nhất quán.
- Giảm số custom message types và logic correlation/ack/flow control tự xây trên WebSocket.
- Peers là service/JVM/backend đã dùng Reactor và có quyền kiểm soát cả hai đầu kết nối.

WebSocket thường tốt hơn nếu:
- Client chủ yếu là browser và đã có WebSocket SDK/hạ tầng.
- Message protocol đơn giản (chat, cursor, presence).
- Không cần native Reactive Streams demand xuyên mạng.
- Muốn ít dependency/client protocol hơn.
- Hệ sinh thái đã có STOMP hoặc một giải pháp realtime WebSocket vận hành ổn định.

**Lưu ý:** RSocket-over-WebSocket vẫn dùng WebSocket làm transport, nhưng thêm lớp protocol RSocket bên trên. Một browser native WebSocket client không thể nói chuyện trực tiếp với RSocket endpoint nếu không triển khai RSocket protocol.

## 9. Bảng lựa chọn theo điều kiện thực tế

| Câu hỏi ra quyết định | Nếu câu trả lời là… | Ưu tiên |
| --- | --- | --- |
| Một HTTP request → một response? | Phần lớn thao tác CRUD/REST | WebClient/HTTP |
| Client bên ngoài cần hợp đồng API dễ công bố? | Public/mobile/partner, OpenAPI, CDN, WAF | WebClient/HTTP |
| Browser chỉ nhận event một chiều? | Notifications, progress, dashboard | SSE |
| Browser gửi và nhận message liên tục? | Chat, whiteboard, game | WebSocket |
| Có nhiều interaction RPC trên một connection? | Request-response + stream + channel | Cân nhắc RSocket |
| Có producer nhanh, consumer chậm và cần remote demand? | Streaming telemetry với pressure rõ ràng | Cân nhắc RSocket |
| Peers có thể chủ động request lẫn nhau? | Full duplex service-to-service | RSocket hoặc WebSocket theo contract |
| Hạ tầng chỉ hỗ trợ HTTP ingress? | Không có TCP route, WebSocket bị chặn | WebClient/SSE |
| Cần browser native, không muốn SDK riêng? | Ưu tiên compatibility và onboarding | SSE/WebSocket |
| Cần durable queue, replay qua ngày, offline consumer? | Delivery/replay là yêu cầu cốt lõi | Broker (Kafka/RabbitMQ/Pulsar), không chỉ RSocket |
| Dữ liệu broadcast tới hàng triệu clients? | Fanout lớn, consumer có tốc độ khác nhau | Thiết kế pub/sub/broker + edge, không chỉ một RSocket connection |
| Đội ngũ không vận hành được connection state? | Mới dùng Spring, hạ tầng HTTP ổn định | Tránh RSocket ban đầu |
| Tương tác thật sự many-to-many và cần REQUEST_N? | Service owned hai đầu, streaming dài hạn | RSocket |

Đây là **heuristic**, không phải phép đo latency. Cần benchmark bằng dữ liệu thực tế trước khi quyết định migration.

## 10. Cây quyết định ngắn

```text
Có yêu cầu trao đổi dữ liệu thời gian thực/stream không?
  |
  +-- Không --> HTTP + WebClient
  |
  +-- Có
       |
       +-- Browser chỉ nhận cập nhật?
       |       |
       |       +-- Có --> SSE
       |       |
       |       +-- Không
       |
       +-- Browser cần gửi và nhận realtime?
       |       |
       |       +-- Có --> WebSocket (hoặc RSocket-over-WS khi
       |       |          thực sự cần RSocket semantics và có SDK)
       |       |
       |       +-- Không
       |
       +-- Service-to-service cần nhiều request/streams và
       |   backpressure xuyên process?
       |       |
       |       +-- Có --> Đánh giá RSocket bằng POC
       |       |
       |       +-- Không --> HTTP/WebClient hoặc SSE
       |
       +-- Cần lưu bền vững và replay offline?
               |
               +-- Có --> Message broker/event log kèm API phù hợp
```

Đừng chọn RSocket chỉ vì dự án dùng Flux/Mono: Spring WebFlux và WebClient đã reactive ngay cả khi giao tiếp qua HTTP.

## 11. Các điều kiện bắt buộc trước khi duyệt RSocket

### 11.1. Kiểm soát được hai phía

RSocket có nhiều thư viện cho Java, JavaScript và các ngôn ngữ khác, nhưng không phổ biến như HTTP. Hãy kiểm tra phiên bản client tương thích, codecs, transport và security trên **mọi nền tảng thực tế**. Nếu nhiều bên thứ ba không thể đổi protocol, giữ HTTP interface ở edge.

### 11.2. Chứng minh nhu cầu interaction model

Viết rõ use case nào cần request-stream hoặc request-channel. Đo số streams đồng thời, kích thước payload, request rate, consumer lag và hành vi khi một consumer chậm.

Nếu toàn bộ use case chỉ là một request-response ngắn, HTTP có thể đơn giản và dễ quan sát hơn.

### 11.3. Hạ tầng hỗ trợ transport

- RSocket TCP cần cổng TCP, firewall, ingress/load balancer L4 và kế hoạch TLS.
- RSocket-over-WebSocket cần endpoint WS/WSS, proxy hỗ trợ Upgrade/long-lived connection và timeout phù hợp.
- HTTP service mesh/gateway không nhất thiết tự hiểu route RSocket.
- TLS, certificates và network policy phải được kiểm tra riêng cho từng transport.
- Cần test reconnect qua proxy, idle timeout, rolling deploy và draining.

### 11.4. Phương án xác thực và phân quyền

HTTP OAuth2/session/cookie không tự động áp dụng cho RSocket TCP. Với Spring Security RSocket, có thể dùng authentication metadata hoặc cơ chế token phù hợp và authorization theo route.

Đặc biệt phải xác định:
- Ai là peer đang kết nối?
- Ai được phép gọi route nào?
- Token hết hạn/thu hồi xử lý ra sao trên connection dài?
- Metadata chứa tenant ID có được xác minh từ principal hay không?
- Có tránh log bearer token hoặc payload nhạy cảm không?

Với SSE/WebSocket cũng cần auth, CORS/origin controls, rate limits và phân quyền từng channel; giao thức nào cũng phải giải quyết security.

### 11.5. Reliability contract rõ ràng

Xác định cho từng interaction:
- At-most-once có đủ không?
- Có cần application ACK hoặc idempotency key?
- Event nào phải được ghi vào store?
- Reconnect làm gì với in-flight request?
- Thông điệp trễ, thiếu, trùng hoặc sai thứ tự có được chấp nhận không?
- Có cần replay từ offset/cursor?

RSocket không tự thay thế Kafka, RabbitMQ hoặc một transactional outbox.

### 11.6. Vận hành và observability

Yêu cầu metrics/tracing cho:
- Connections active, close reason, setup failures.
- Số request theo route/interaction model.
- Latency p50/p95/p99, duration của stream.
- REQUEST_N/demand, consumer lag, buffer/drop.
- Errors, cancellation, resume/reconnect failures.
- Authentication failures, timeouts.
- Memory/CPU và throughput của encoder/decoder.

HTTP tooling thường sẵn có nhiều hơn; với RSocket nên lập kế hoạch instrumentation và runbook trước khi production.

## 12. Ví dụ Java 17+ với Spring Boot: bốn interaction model

Ví dụ sau dùng **một project Spring Boot 3.5.x, chạy hai process bằng profile khác nhau**: một process RSocket server TCP và một process client. Cấu trúc đơn giản để người học kiểm tra hành vi trực tiếp, không cần browser hay cơ sở dữ liệu.

### 12.1. Cấu trúc

```text
rsocket-choice-demo/
  build.gradle
  settings.gradle
  src/main/resources/application.yml
  src/main/java/demo/rsocket/
    ProtocolDemoApplication.java
    TelemetryResponder.java
    DemoClientRunner.java
  src/test/java/demo/rsocket/
    TelemetryResponderTest.java
```

### 12.2. build.gradle

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '1.0.0'

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

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Tệp `settings.gradle`:

```groovy
rootProject.name = 'rsocket-choice-demo'
```

Spring Boot starter RSocket có RSocket Java, Spring Messaging và codec support. Boot auto-configures RSocketStrategies, RSocketMessageHandler và RSocketRequester.Builder. Không cần thêm spring-boot-starter-webflux khi chỉ chạy RSocket TCP độc lập.

### 12.3. application.yml: chỉ mở TCP server với profile server

```yaml
spring:
  application:
    name: rsocket-choice-demo

---
spring:
  config:
    activate:
      on-profile: server
  rsocket:
    server:
      port: 7000
      transport: tcp
```

Profile client không có thuộc tính spring.rsocket.server.port nên ứng dụng client không mở RSocket server phụ. Khi chạy profile server, Boot tạo RSocket TCP server trên cổng 7000.

### 12.4. Application class

```java
package demo.rsocket;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ProtocolDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ProtocolDemoApplication.class, args);
    }
}
```

### 12.5. Responder: @MessageMapping

```java
package demo.rsocket;

import java.time.Duration;

import org.springframework.context.annotation.Profile;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.stereotype.Controller;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Controller
@Profile("server")
public class TelemetryResponder {

    @MessageMapping("greet")
    public Mono<String> greet(@Payload String name) {
        return Mono.just("Xin chào " + name);
    }

    @MessageMapping("sensor.stream")
    public Flux<String> readings(@Payload String sensorId) {
        return Flux.interval(Duration.ofMillis(120))
                .map(n -> sensorId + "#" + n)
                .take(4);
    }

    @MessageMapping("sensor.channel")
    public Flux<String> normalize(@Payload Flux<String> readings) {
        return readings.map(String::trim)
                .filter(value -> !value.isBlank())
                .map(String::toUpperCase);
    }

    @MessageMapping("audit")
    public Mono<Void> audit(@Payload String event) {
        return Mono.fromRunnable(() ->
                System.out.println("audit:" + event));
    }
}
```

Giải thích:
- greet nhận một String và trả Mono<String> → Request-Response.
- sensor.stream nhận một String và trả Flux<String> → Request-Stream.
- sensor.channel nhận Flux<String> và trả Flux<String> → Request-Channel.
- audit nhận một String và trả Mono<Void> → Fire-and-Forget khi requester dùng send().

Trong ví dụ, stream dừng sau bốn giá trị để tránh tạo vô hạn. Không nên phát dữ liệu vô hạn cho người học mà không có cancellation hoặc timeout.

### 12.6. Client runner: RSocketRequester

```java
package demo.rsocket;

import java.time.Duration;
import java.util.List;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Profile;
import org.springframework.messaging.rsocket.RSocketRequester;
import org.springframework.stereotype.Component;

import reactor.core.publisher.Flux;

@Component
@Profile("client")
public class DemoClientRunner implements ApplicationRunner {

    private final RSocketRequester.Builder requesterBuilder;

    public DemoClientRunner(RSocketRequester.Builder requesterBuilder) {
        this.requesterBuilder = requesterBuilder;
    }

    @Override
    public void run(ApplicationArguments arguments) {
        RSocketRequester requester =
                requesterBuilder.tcp("127.0.0.1", 7000);

        String greeting = requester.route("greet")
                .data("An")
                .retrieveMono(String.class)
                .block(Duration.ofSeconds(5));

        List<String> stream = requester.route("sensor.stream")
                .data("temp-1")
                .retrieveFlux(String.class)
                .collectList()
                .block(Duration.ofSeconds(5));

        List<String> channel = requester.route("sensor.channel")
                .data(Flux.just(" a ", "b"), String.class)
                .retrieveFlux(String.class)
                .collectList()
                .block(Duration.ofSeconds(5));

        requester.route("audit")
                .data("client-start")
                .send()
                .block(Duration.ofSeconds(5));

        System.out.println("greet=" + greeting);
        System.out.println("stream=" + stream);
        System.out.println("channel=" + channel);
        System.out.println("fnf sent");
    }
}
```

Việc dùng block(Duration) chỉ để tạo output xác định trong ApplicationRunner của **bài demo CLI**, không phải hướng lập trình trong controller WebFlux hay Netty event-loop. Trong production, trả Mono/Flux cho caller, compose các operator và dùng timeout/retry có điều kiện.

### 12.7. Chạy demo

Mở hai terminal:

Terminal 1 (server):

```bash
./gradlew bootRun --args='--spring.profiles.active=server'
```

Terminal 2 (client):

```bash
./gradlew bootRun --args='--spring.profiles.active=client'
```

Với dữ liệu trong mã, output quan trọng của client:

```text
greet=Xin chào An
stream=[temp-1#0, temp-1#1, temp-1#2, temp-1#3]
channel=[A, B]
fnf sent
```

Server có thể in dòng audit:client-start nhưng thời điểm xuất hiện không được đảm bảo tương đối với dòng fnf sent. send() không phải application-level ACK rằng sự kiện đã được xử lý bền vững.

Nếu client không kết nối, kiểm tra profile server, cổng 7000, firewall, thời gian startup và việc dùng cùng transport TCP. Dùng cùng một cấu hình codec/dataMimeType ở hai phía; starter mặc định hỗ trợ codec tương thích.

### 12.8. Kiểm thử logic publisher bằng StepVerifier

Tệp `src/test/java/demo/rsocket/TelemetryResponderTest.java`:

```java
package demo.rsocket;

import java.time.Duration;

import org.junit.jupiter.api.Test;

import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

class TelemetryResponderTest {

    private final TelemetryResponder responder =
            new TelemetryResponder();

    @Test
    void requestResponseReturnsOneValue() {
        StepVerifier.create(responder.greet("An"))
                .expectNext("Xin chào An")
                .verifyComplete();
    }

    @Test
    void requestChannelTransformsInputStream() {
        StepVerifier.create(responder.normalize(
                        Flux.just(" a ", "   ", "b")))
                .expectNext("A", "B")
                .verifyComplete();
    }

    @Test
    void requestStreamProducesFourReadings() {
        StepVerifier.withVirtualTime(
                        () -> responder.readings("temp-1"))
                .thenAwait(Duration.ofMillis(600))
                .expectNext(
                        "temp-1#0",
                        "temp-1#1",
                        "temp-1#2",
                        "temp-1#3")
                .verifyComplete();
    }
}
```

Chạy:

```bash
./gradlew test
```

Các test này xác nhận logic reactive của responder. Chúng **không thay thế** integration test qua RSocket TCP/WebSocket thật, bởi StepVerifier trực tiếp không chứng minh encoding, routing metadata hoặc REQUEST_N đã hoạt động qua network.

## 13. RSocket over WebSocket: khi nào cần?

Nếu client là browser nhưng use case thực sự cần RSocket semantics, có thể dùng RSocket over WebSocket và client JavaScript tương thích.

Với Spring Boot WebFlux + Reactor Netty, cấu hình RSocket dưới URL mapping:

```properties
spring.rsocket.server.transport=websocket
spring.rsocket.server.mapping-path=/rsocket
```

Thêm starter WebFlux để có HTTP web server. Cấu hình trên gắn RSocket WebSocket endpoint vào WebFlux server tương ứng. Chế độ này được Spring Boot hỗ trợ khi web server sử dụng Reactor Netty; không nên mặc định thay sang Tomcat/Jetty và kỳ vọng cùng auto-configuration hoạt động.

Lựa chọn khác: mở RSocket server TCP độc lập qua spring.rsocket.server.port trên một cổng riêng. Bản demo ở phần 12 sử dụng lựa chọn này.

SSE/WebSocket thuần vẫn có lợi thế về API browser native. Chỉ chấp nhận thêm RSocket JavaScript dependency, protocol framing và vận hành nếu dự án thật sự tận dụng nhiều interaction model/backpressure.

## 14. So sánh độ tin cậy khi mất kết nối

| Sự cố | HTTP/WebClient | SSE/EventSource | WebSocket | RSocket |
| --- | --- | --- | --- | --- |
| Socket bị ngắt | Request lỗi/timeout; cần retry policy | EventSource thường reconnect | App cần reconnect logic | App/connector cần reconnect logic; có thể có resumption nếu bật và hỗ trợ |
| Replay dữ liệu đã mất | API/app tự thiết kế | Last-Event-ID giúp nếu server lưu lịch sử | App tự thiết kế | Resumption tùy chọn và state; không đồng nghĩa durable replay |
| Bảo đảm exactly-once side effect | Không tự có | Không tự có | Không tự có | Không tự có |
| Lưu event cho consumer offline | Cần storage/broker | Cần event store/broker | Cần event store/broker | Cần event store/broker |
| Client gửi tín hiệu demand từng event | Không có request-N message | EventSource không có | Phải tự thêm protocol | REQUEST_N trong streaming |

**Kết luận:** Đừng chọn RSocket chỉ vì muốn “không mất message”. Nếu cần reliable event processing, hãy thiết kế application-level ACK, persistence/idempotency và có thể kết hợp message broker.

## 15. Benchmark POC trước khi quyết định

Một kiến trúc RSocket nên được chứng minh bằng số liệu thay vì cảm nhận “reactive chắc nhanh”.

### 15.1. Đặt cùng workload

So sánh RSocket request-stream với SSE/WebClient streaming trên cùng:
- Tốc độ producer messages/s.
- Số clients/streams đồng thời.
- Kích thước message nhỏ/vừa/lớn.
- Độ trễ RTT và packet loss.
- CPU/memory, số socket, thời gian kết nối.
- Tình huống consumer chậm hoặc tạm dừng đọc.

### 15.2. Metric đo

- Throughput, p50/p95/p99 latency, end-to-end event lag.
- Memory peak/GC, bytes buffered, messages dropped.
- Connection establishment/reconnect time.
- Cancellation propagation.
- Backpressure response khi downstream chỉ nhận N phần tử.
- Tỷ lệ timeout, lỗi mã hóa, reset, leak.
- Deployment complexity: số cổng, TLS, proxy rules, dashboard/tracing.
- Chi phí phát triển và support client.

### 15.3. Các kịch bản lỗi phải thử

1. Consumer đọc chậm.
2. Server phát nhanh hơn capacity.
3. Proxy đóng idle connection.
4. Client chuyển mạng hoặc sleep/wake.
5. Server rolling restart.
6. Token hết hạn giữa session.
7. Một interaction lỗi trong khi các stream khác vẫn chạy.
8. Message lớn cần fragmentation.
9. Retry tạo duplicate side effect.
10. Client không tương thích codec/protocol version.

Nếu POC không tạo ra lợi ích đo được hoặc đội ngũ không có năng lực vận hành, ưu tiên giải pháp đơn giản đã có.

## 16. Tình huống minh họa và khuyến nghị

### Tình huống A: CRUD sản phẩm và thanh toán

Yêu cầu: GET/POST, HTTP status, idempotency, validation, audit và đối tác bên ngoài.

**Lựa chọn:** REST/HTTP với WebClient phía client, WebFlux hoặc Spring MVC phía server. RSocket không cải thiện semantics REST và làm integration khó hơn.

### Tình huống B: Dashboard hiển thị trạng thái đơn hàng

Browser chỉ cần theo dõi trạng thái theo thời gian, thao tác bấm nút gửi POST HTTP riêng.

**Lựa chọn:** SSE. Có thể gửi ID để khôi phục sự kiện nếu có event store. Không cần RSocket chỉ để push notification.

### Tình huống C: Chat và collaborative editor trong browser

Browser liên tục gửi và nhận message. Có room, user presence và các tương tác nhỏ.

**Lựa chọn:** WebSocket với message protocol rõ ràng. Nếu hệ thống đã dùng STOMP hoặc giải pháp realtime vận hành tốt, lợi ích chuyển sang RSocket phải có căn cứ.

### Tình huống D: Thiết bị IoT gửi telemetry và nhận lệnh liên tục

Hai chiều đều có stream; cần giới hạn tốc độ dựa trên khả năng xử lý của peer; mỗi connection chứa nhiều logical streams; cả client/server do cùng tổ chức kiểm soát.

**Lựa chọn:** RSocket là ứng viên mạnh. Cần kiểm tra SDK cho thiết bị, transport TLS, auth, reconnect và bộ nhớ khi mạng không ổn định.

### Tình huống E: Dữ liệu tài chính bắt buộc replay và audit bất kể client offline

Yêu cầu: durable history, replay theo offset, lỗi không làm mất event và nhiều consumer group.

**Lựa chọn:** event log/broker như Kafka/Pulsar hoặc queue phù hợp; WebClient/SSE/WebSocket/RSocket chỉ là một phần của đường giao nhận dữ liệu. RSocket tự nó không tạo ra durable queue.

### Tình huống F: Chỉ một backend service đọc 1 bản ghi từ service khác

Yêu cầu: request-response ngắn, thông qua API gateway và HTTP tracing sẵn.

**Lựa chọn:** WebClient, không cần mở rộng stack RSocket.

## 17. Lỗi kiến trúc thường gặp

| Sai lầm | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Thấy Flux/Mono rồi chọn RSocket | Thêm protocol không cần thiết | Bắt đầu từ use case, không từ return type |
| Nghĩ WebClient không stream được | Migration tốn kém | WebClient có thể tiêu thụ Flux/SSE/NDJSON trên HTTP |
| Nghĩ WebSocket không xử lý hai chiều được | Chọn giao thức dư tính năng | WebSocket native duplex; RSocket thêm semantics |
| Nghĩ SSE hai chiều | Không gửi được message client trên cùng stream | Dùng HTTP POST hoặc WebSocket |
| Nghĩ RSocket là giao thức browser native | Client không kết nối được | Dùng RSocket JS qua WebSocket hoặc chọn native WS/SSE |
| Nghĩ REQUEST_N bằng TCP window | Thiết kế pressure sai | Phân biệt demand application message và byte flow control |
| Dùng fire-and-forget cho sự kiện tài chính quan trọng | Không có business ACK/durable guarantee | Dùng idempotency, ACK, outbox hoặc broker |
| Nghĩ resumption tự bật và luôn không mất data | Sai kỳ vọng reconnect | Xác minh cấu hình hai đầu, replay và failover |
| Không kiểm tra proxy/LB | Kết nối timeout hoặc bị chặn | Test từng hop/transport và idle timeout |
| Mở một connection không giới hạn streams | Quá tải memory/CPU | Đo queue, giới hạn concurrency, buffering policy |
| Không có route authorization | Lộ dữ liệu giữa tenant | Spring Security RSocket + principal/route policy |
| Tự subscribe trong handler | Lỗi/cancel không về caller | Compose Mono/Flux và return publisher |
| Block trong Netty event loop | Tắc nghẽn, mất scalability | Giữ non-blocking, isolate blocking workload |
| Test unit rồi khẳng định network backpressure | Bỏ sót frame/codec/proxy lỗi | Thêm integration + failure-injection tests |
| Dùng RSocket thay Kafka | Không có replay/durable queue | Kết hợp broker khi cần |
| Cho rằng RSocket luôn nhanh hơn HTTP/2 | Benchmark không ủng hộ | POC cùng workload, so p95/p99 và chi phí |

## 18. Checklist quyết định cuối cùng

Trước khi phê duyệt RSocket, trả lời và ghi thành tài liệu:

1. Những route nào cần request-stream hoặc request-channel? Đưa ví dụ payload.
2. Có cần remote REQUEST_N thay vì chỉ HTTP/SSE/WebSocket streaming?
3. Những peer nào dùng Java, JavaScript, mobile, thiết bị? Có SDK tương thích?
4. Có yêu cầu browser native/đối tác external/public OpenAPI?
5. Hạ tầng hỗ trợ TCP/WSS và TLS end-to-end không?
6. Có quyền thay đổi tất cả client và server không?
7. Kế hoạch authentication, authorization theo route, token expiry và tenant isolation là gì?
8. Demand, buffer, cancellation, timeout và rate limiting được đặt ở đâu?
9. Replay, duplicates, ordering, offline consumer và durable processing có cần không?
10. Reconnect/resumption có được cấu hình và kiểm thử failover thật không?
11. Tracing/metrics/logging và công cụ debug có đủ chưa?
12. Benchmark so với WebClient/SSE/WebSocket đã chứng minh lợi ích chưa?
13. Đội ngũ có năng lực vận hành connection lifecycle và protocol errors không?
14. Nếu không đáp ứng các điều kiện trên, giải pháp HTTP/SSE/WebSocket đơn giản hơn có đạt mục tiêu không?

## 19. Tài liệu tham khảo

- [Spring Framework – RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html): bốn interaction model, REQUEST_N, leasing, resumption, requester và @MessageMapping.
- [Spring Boot 3.5 – RSocket](https://docs.spring.io/spring-boot/3.5/reference/messaging/rsocket.html): starter, auto-configuration, TCP server, RSocket-over-WebSocket, RSocketRequester.Builder.
- [Spring Framework – WebClient](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html): HTTP client reactive, response handling và streaming.
- [Spring Framework – WebSockets](https://docs.spring.io/spring-framework/reference/web/webflux-websocket.html): WebSocketHandler, WebSocketSession, receive/send và transport.
- [Spring Framework – Reactive Core Streaming](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html): HTTP SSE/NDJSON streaming và heartbeat.
- [MDN – Using server-sent events](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events): EventSource, server→client, event/id/retry và reconnect.
- [RSocket Protocol](https://rsocket.io/about/protocol/): wire-level interaction, frames, resumability và protocol contract.

## 20. Ghi nhớ

**Đừng chọn RSocket chỉ vì hệ thống đang viết bằng Spring WebFlux.** Chọn WebClient/HTTP cho CRUD, public API và tích hợp HTTP thông thường; chọn SSE khi browser chỉ nhận update; chọn WebSocket khi browser cần gửi/nhận realtime với message protocol đơn giản; cân nhắc RSocket khi các service/peers có nhiều interaction hai chiều, request-stream/request-channel và thực sự cần backpressure thông qua REQUEST_N ở cấp application message.

RSocket có thể chạy trên TCP hoặc WebSocket, có multiplexing, keepalive và tùy chọn leasing/resumption. Nó **không thay thế** HTTP gateway, browser native APIs, security policy, durable broker hoặc business-level ACK. Quyết định đúng dựa trên yêu cầu giao tiếp, khả năng client/hạ tầng, vận hành, bằng chứng benchmark và nhu cầu độ tin cậy — không dựa trên xu hướng công nghệ.
