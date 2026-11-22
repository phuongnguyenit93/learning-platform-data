# Ranh giới giữa WebSocket thuần và STOMP trong Spring Framework

## 1. Mục tiêu bài học

Sau bài này, người học cần phân biệt được **WebSocket là transport hai chiều** với **STOMP là giao thức messaging ở tầng ứng dụng** có thể chạy trên transport đó; biết khi nào nên tự thiết kế message protocol trên WebSocket, khi nào nên dùng STOMP, và đặc biệt **không nhầm WebFlux WebSocketHandler với Spring STOMP message-broker configuration**.

Các năng lực cụ thể:

1. Giải thích HTTP Upgrade, WebSocket text/binary frame và ý nghĩa của `Sec-WebSocket-Protocol`.
2. Nhận diện các STOMP frame như `CONNECT`, `CONNECTED`, `SUBSCRIBE`, `SEND`, `MESSAGE`, `ACK`, `NACK`, `DISCONNECT`.
3. Phân biệt WebSocket URL với STOMP destination, transport close code với STOMP `ERROR`/`RECEIPT`.
4. Hiểu routing `/app`, `/topic`, `/queue` trong Spring và sự khác nhau giữa simple broker với external broker relay.
5. Nhận diện ranh giới công nghệ: WebFlux reactive WebSocket API so với Spring WebSocket/STOMP messaging của Servlet stack.
6. Xây một WebFlux raw WebSocket echo server và một ứng dụng Spring MVC + STOMP độc lập, Java 17+.
7. Chọn giải pháp theo latency, routing, subscription, reliability, security, operations và khả năng mở rộng.

## 2. Khái niệm trong một câu

**WebSocket thuần** là một kết nối full-duplex cho phép hai phía trao đổi các message text/binary. RFC 6455 **không định nghĩa** message `subscribe`, `order-created` hay `chat-room-42` có ý nghĩa gì. Nếu ứng dụng muốn các hành động đó, hai phía phải tự thỏa thuận format và semantics.

**STOMP** (Simple Text Oriented Messaging Protocol) là một giao thức message-oriented có command, headers, body và frame terminator. STOMP định nghĩa cách kết nối phiên messaging, gửi tới destination, đăng ký nhận message, acknowledgement và một số control operation. STOMP có thể chạy trên WebSocket hoặc một transport streaming hai chiều khác như TCP.

Nói ngắn gọn:

~~~text
WebSocket thuần:
  HTTP Upgrade -> WebSocket frames -> payload do ứng dụng tự định nghĩa

STOMP over WebSocket:
  HTTP Upgrade -> WebSocket frames -> STOMP protocol frames
                                      |
                                      +-- destinations
                                      +-- subscriptions
                                      +-- SEND / MESSAGE
                                      +-- ACK / NACK
                                      +-- heartbeats
                                      +-- broker routing
~~~

**STOMP không phải một phiên bản WebSocket.** Nó là một giao thức cao hơn, được chuyên chở qua WebSocket. Và một WebSocket được mở thành công **không tự động** hiểu STOMP.

## 3. Bảng so sánh hai mô hình

| Tiêu chí | WebSocket thuần | STOMP trên WebSocket |
| --- | --- | --- |
| Tầng chính | Transport | Messaging protocol chạy trên transport |
| Đơn vị trao đổi | WebSocket text/binary message | STOMP frame nằm trong WebSocket payload |
| Format ứng dụng | Tự chọn JSON, text, binary, Protobuf... | STOMP command/headers/body; body có thể JSON/binary |
| Routing | Ứng dụng tự viết | Destination và subscription của broker |
| Subscribe/unsubscribe | Phải định nghĩa riêng nếu cần | `SUBSCRIBE` / `UNSUBSCRIBE` |
| Publish | Tự định nghĩa và thực thi | `SEND` tới destination |
| ACK/NACK | Tự định nghĩa | Có trong STOMP, broker phải hỗ trợ |
| Heartbeat | WebSocket Ping/Pong hoặc ứng dụng tự định nghĩa | STOMP heartbeat thương lượng, tách biệt Ping/Pong |
| Broadcast/fan-out | Ứng dụng hoặc broker tích hợp tự viết | Simple broker hoặc external broker relay |
| Backpressure | API và thiết kế riêng của ứng dụng | Còn phụ thuộc thư viện/broker; STOMP không tự mang Reactive Streams demand |
| Độ phức tạp protocol | Ít overhead nếu nghiệp vụ đơn giản | Có overhead command/header và state subscription |
| Phù hợp | Game, sensor stream, binary feed, protocol riêng | Chat room, notification topics, ứng dụng pub/sub nhiều client |
| Spring WebFlux | `WebSocketHandler`, `WebSocketSession`, `Flux`, `Mono` | Không tự cung cấp đầy đủ STOMP broker chỉ bằng reactive WebSocketHandler |
| Spring STOMP hỗ trợ sẵn | Không bắt buộc | `@EnableWebSocketMessageBroker`, `@MessageMapping`, `SimpMessagingTemplate` trong hệ hỗ trợ Servlet WebSocket messaging |

Một lựa chọn không mặc nhiên nhanh hơn lựa chọn còn lại trong mọi tình huống. STOMP thêm protocol overhead nhưng giảm code routing/subscription tự viết. Raw WebSocket có thể giảm overhead ở hệ thống message cố định, nhưng trách nhiệm đảm bảo giao thức, phân quyền và vận hành chuyển sang ứng dụng.

## 4. Hai lần bắt tay: WebSocket handshake và STOMP CONNECT

Khi dùng STOMP over WebSocket, có **hai tầng thiết lập phiên**:

~~~text
Browser / STOMP client                         Server
        |                                         |
        | -- HTTP GET Upgrade: websocket ------>  |
        | <-- HTTP 101 Switching Protocols -----  |
        |                                         |
        | ==== WebSocket transport đã mở ======  |
        |                                         |
        | -- WebSocket payload: CONNECT frame --> |
        | <-- WebSocket payload: CONNECTED -----  |
        |                                         |
        | ==== STOMP messaging session sẵn sàng = |
        |                                         |
        | -- SUBSCRIBE destination:/topic/... --> |
        | -- SEND destination:/app/... ---------> |
        | <-- MESSAGE destination:/topic/... ---- |
~~~

HTTP status **101 Switching Protocols** xác nhận đổi giao thức transport sang WebSocket. Nó không phải STOMP `CONNECTED`.

Header `Sec-WebSocket-Protocol` có thể được client và server dùng để thương lượng WebSocket subprotocol, ví dụ `v12.stomp`. Nếu ứng dụng muốn dùng STOMP thì việc thương lượng này phải phù hợp với cấu hình server/client. WebSocket handshake thành công nhưng sau đó gửi raw JSON tới endpoint STOMP thường không đúng protocol; ngược lại, gửi một STOMP `CONNECT` tới raw echo WebSocket sẽ chỉ là payload text nếu handler không implement STOMP parser.

Trong client JavaScript:

~~~javascript
// WebSocket thuần: payload do ứng dụng thiết kế.
const rawSocket = new WebSocket("ws://localhost:8080/ws/raw");
rawSocket.onopen = () => rawSocket.send("ping");

// STOMP cần một STOMP client library và STOMP CONNECT frame.
// new WebSocket(...) một mình không tạo STOMP session.
~~~

## 5. WebSocket frame khác STOMP frame thế nào?

WebSocket định nghĩa các message text/binary, control frame Ping/Pong và Close. Cách phân mảnh frame thuộc transport. Dữ liệu text có thể chứa một JSON document:

~~~json
{
  "type": "subscribe",
  "channel": "orders",
  "orderId": 42
}
~~~

Đây là **JSON protocol tự thiết kế**. Browser gửi và server hiểu được chỉ vì hai phía đã thống nhất field `type`, `channel`, `orderId` và semantics. WebSocket không biết field nào là destination hay subscription.

STOMP frame có cấu trúc:

~~~text
COMMAND
header-1:value-1
header-2:value-2

body<NULL>
~~~

`<NULL>` ở đây đại diện cho **một byte NUL (0x00)** kết thúc frame, không phải chuỗi ký tự “<NULL>” gửi trên dây. Frame có dòng command, các dòng header, dòng trống rồi body. Một STOMP protocol parser phải tách frame theo framing STOMP, không giả định một lần callback WebSocket luôn bằng một STOMP frame hoàn chỉnh.

Ví dụ gửi nội dung JSON qua STOMP:

~~~text
SEND
destination:/app/orders
content-type:application/json

{"orderId":42,"action":"confirm"}<NULL>
~~~

STOMP tạo thêm lớp định tuyến và control; phần body vẫn có thể là JSON. STOMP không thay thế JSON, và JSON cũng không tự biến một raw WebSocket thành STOMP.

**Cảnh báo parser:** STOMP 1.2 hỗ trợ `content-length`, header escaping, frame boundary, nhiều command/headers và heartbeat là byte xuống dòng. Nếu tự implement STOMP parser, phải tuân thủ specification; không chỉ `split("\n")` hay kết luận “mỗi WebSocket message chứa đúng một STOMP frame”.

## 6. Các frame STOMP quan trọng

| Frame | Ai thường gửi? | Vai trò |
| --- | --- | --- |
| `CONNECT` hoặc `STOMP` | Client | Đề nghị mở STOMP session, version và heartbeat |
| `CONNECTED` | Server | Xác nhận version đã chọn |
| `SUBSCRIBE` | Client | Đăng ký một destination, có subscription ID |
| `UNSUBSCRIBE` | Client | Hủy subscription bằng ID |
| `SEND` | Client | Gửi message tới destination |
| `MESSAGE` | Server | Chuyển một message tới subscription |
| `ACK` | Client | Xác nhận message theo ack mode |
| `NACK` | Client | Báo không xử lý message |
| `BEGIN` / `COMMIT` / `ABORT` | Client | Điều khiển transaction khi broker hỗ trợ |
| `RECEIPT` | Server | Xác nhận frame có receipt đã được xử lý |
| `ERROR` | Server | Báo lỗi protocol hoặc processing |
| `DISCONNECT` | Client | Yêu cầu kết thúc STOMP session |

Tối thiểu, STOMP 1.2 client cần cung cấp `accept-version` và `host` trong `CONNECT`:

~~~text
CONNECT
accept-version:1.2
host:localhost
heart-beat:10000,10000

<NULL>
~~~

Nếu server chấp nhận:

~~~text
CONNECTED
version:1.2
heart-beat:10000,10000

<NULL>
~~~

Sau đó có thể subscribe:

~~~text
SUBSCRIBE
id:sub-1
destination:/topic/greetings
ack:auto

<NULL>
~~~

Và gửi một message:

~~~text
SEND
destination:/app/hello
content-type:application/json

{"name":"An"}<NULL>
~~~

Một message server phát tới subscriber có metadata:

~~~text
MESSAGE
subscription:sub-1
message-id:message-7
destination:/topic/greetings
content-type:application/json

{"content":"Xin chào, An!"}<NULL>
~~~

Các ID và body ở trên là ví dụ minh họa, không phải giá trị cố định mà Spring luôn tạo. Tên destination, khả năng ACK/NACK, transaction và delivery semantics do broker/server quyết định; STOMP specification không đảm bảo rằng prefix `/queue` luôn tương đương queue bền vững.

## 7. Destination không phải WebSocket URL

Đây là một trong các nhầm lẫn quan trọng nhất.

- `ws://localhost:8081/ws-stomp` là **URL để tạo kết nối WebSocket**.
- `/app/hello` là **STOMP destination cho lệnh từ client tới application handler** trong cấu hình Spring ví dụ.
- `/topic/greetings` là **STOMP destination để client subscribe và nhận broadcast**.
- `/queue/...` là prefix destination theo quy ước; semantics cụ thể phụ thuộc message broker và cấu hình.

Một WebSocket connection có thể mang **nhiều subscription STOMP**. Client không cần mở một WebSocket riêng cho mỗi destination.

Trong Spring STOMP cấu hình thường gặp:

~~~java
registry.setApplicationDestinationPrefixes("/app");
registry.enableSimpleBroker("/topic", "/queue");
~~~

Điều đó có nghĩa:

1. Message STOMP `SEND` tới `/app/hello` được đưa tới `@MessageMapping("/hello")`.
2. `SUBSCRIBE` tới `/topic/greetings` được broker quản lý.
3. Return value từ `@MessageMapping` có thể gửi tới `/topic/greetings` qua `@SendTo` hoặc `SimpMessagingTemplate`.
4. Prefix không phải một HTTP controller route, không phải WebFlux `@GetMapping` và cũng không phải Spring Security authorization rule.

Trong simple broker của Spring, `/topic` và `/queue` không tự mang khác biệt routing đảm bảo; đó chủ yếu là quy ước được cấu hình. Broker ngoài có thể đặt semantics khác.

## 8. Spring: ranh giới quan trọng giữa WebFlux và STOMP hỗ trợ sẵn

Trong hệ sinh thái Spring có hai nhánh tài liệu và API liên quan:

**A. Reactive WebFlux WebSocket**

- Module chính: `spring-webflux`.
- Server endpoint dùng `org.springframework.web.reactive.socket.WebSocketHandler`.
- `handle(WebSocketSession)` trả `Mono<Void>`.
- `receive()` là `Flux<WebSocketMessage>`, `send(...)` là `Mono<Void>`.
- Phù hợp với Reactor Netty/Reactive Streams và protocol do ứng dụng định nghĩa.
- WebSocket thuần không tự có `@MessageMapping`, destination broker hoặc STOMP subscription manager.

**B. Spring STOMP-over-WebSocket messaging**

- Cấu hình được Spring Framework tài liệu hóa ở nhóm **Servlet-stack WebSocket messaging**.
- Module `spring-messaging` và `spring-websocket`.
- Sử dụng `@EnableWebSocketMessageBroker`, `WebSocketMessageBrokerConfigurer`, `@MessageMapping`, `@SendTo`, `SimpMessagingTemplate`.
- Client gửi/nhận STOMP frames; Spring giải mã và route qua messaging channels/broker.
- Starter `spring-boot-starter-websocket` của Spring Boot 3.5 có dependency tới MVC web support, messaging và websocket.

**Không kết luận rằng thêm `@EnableWebSocketMessageBroker` vào ứng dụng chỉ có `spring-boot-starter-webflux` trên Reactor Netty sẽ tự tạo STOMP broker hoạt động giống mẫu Servlet.** Đây là hai programming models; Spring Boot còn thường ưu tiên MVC khi cả MVC và WebFlux starter cùng có mặt. Muốn dùng STOMP messaging hỗ trợ sẵn thì chọn stack/config phù hợp hoặc một thư viện/server STOMP bên ngoài, không nhầm với reactive WebSocketHandler.

Bảng quyết định nhanh:

| Nhu cầu | Hướng nên xem xét |
| --- | --- |
| Giữ ứng dụng reactive WebFlux/Netty, custom protocol | WebFlux WebSocketHandler |
| WebFlux/Netty nhưng client cần STOMP | Chọn STOMP-capable server/broker gateway phù hợp; đánh giá tích hợp và kiến trúc riêng |
| Spring chuẩn `@MessageMapping`, simple broker | Spring Servlet WebSocket messaging |
| Có hàng nghìn subscription, broker clustering, ACK/receipt | STOMP broker relay tới RabbitMQ/ActiveMQ hoặc broker phù hợp |
| Chỉ đẩy một feed một chiều | SSE/HTTP streaming cũng đáng cân nhắc |
| Client cần publish/subscribe nhiều topic chuẩn hóa | STOMP có thể giảm code routing ứng dụng |

**STOMP không phải mặc định của WebFlux**, và **WebFlux không bắt buộc ứng dụng phải dùng STOMP**. Cùng dùng chữ “WebSocket” không có nghĩa có thể tráo API/configuration giữa hai stack.

## 9. Luồng xử lý của Spring STOMP messaging

Trong Spring Servlet STOMP messaging, flow thường là:

~~~text
Browser STOMP client
        |
        v
WebSocket transport /ws-stomp
        |
        v
STOMP decoder
        |
        v
clientInboundChannel
        |
        +--> destination /app/hello
        |         |
        |         v
        |   @MessageMapping("/hello")
        |         |
        |         v
        |    @SendTo("/topic/greetings")
        |         |
        |         v
        |      brokerChannel
        |         |
        |         v
        +--> simple broker / external broker relay
                  |
                  v
           clientOutboundChannel
                  |
                  v
             MESSAGE frame
                  |
                  v
        Browser subscription callback
~~~

Đối với `SUBSCRIBE /topic/greetings`, broker lưu subscription. Đối với `SEND /app/hello`, application controller xử lý payload và đưa response qua broker. Các messaging channels này khác với HTTP controller invocation trong DispatcherHandler của WebFlux.

Spring có thể thay simple broker bằng broker relay để chuyển tiếp STOMP tới broker ngoài qua TCP. Relay không biến từng WebSocket browser thành kết nối trực tiếp từ browser tới RabbitMQ; Spring vẫn là một lớp gateway.

## 10. Simple broker và external broker relay

Spring cho phép bật simple broker tích hợp:

~~~java
registry.enableSimpleBroker("/topic", "/queue");
~~~

Simple broker lưu subscription trong memory và chuyển message cho các client phù hợp. Nó tiện cho ứng dụng demo hoặc pub/sub đơn giản, nhưng có giới hạn đáng lưu ý:

- Không hỗ trợ đầy đủ STOMP acknowledgement, receipt và nhiều tính năng nâng cao.
- Không được thiết kế cho broker clustering thực sự.
- Subscription state nằm tại tiến trình ứng dụng; không coi đây là persistent queue.
- Sau khi server restart, subscription phải được client khởi tạo lại.
- Không được coi delivery success là business transaction success.

Khi cần queue semantics, ACK/NACK, receipt, durable messaging, scaling nhiều node hoặc retry/redelivery, cân nhắc broker ngoài:

~~~java
registry.enableStompBrokerRelay("/topic", "/queue");
registry.setApplicationDestinationPrefixes("/app");
~~~

Relay cần broker STOMP hoạt động và cấu hình kết nối/credential phù hợp. Tính năng cụ thể phụ thuộc RabbitMQ, ActiveMQ hoặc broker khác; không mặc nhiên mọi broker có behavior giống nhau.

**Một cạm bẫy khi đánh giá:** STOMP có lệnh `ACK` trong specification, nhưng **simple broker của Spring không có nghĩa tự hỗ trợ mọi ACK/receipt**. Không hứa “đã đảm bảo exactly-once” chỉ vì dùng STOMP. Cần kiểm tra implementation, persistence, idempotency và message processing policy.

## 11. Heartbeat: WebSocket Ping/Pong khác STOMP heartbeat

WebSocket có protocol-level Ping/Pong control frames. STOMP 1.1/1.2 có heartbeat riêng, thương lượng qua `heart-beat:cx,cy` và `heart-beat:sx,sy`.

- `cx`: khoảng gửi heartbeat tối thiểu mà client có thể bảo đảm.
- `cy`: khoảng client muốn nhận heartbeat từ server.
- `sx`: khoảng gửi tối thiểu mà server có thể bảo đảm.
- `sy`: khoảng server muốn nhận heartbeat từ client.

Nếu hai giá trị liên quan khác 0, chu kỳ dự kiến theo một hướng là giá trị lớn hơn trong hai mức thỏa thuận. Ví dụ client gửi `heart-beat:10000,10000`, server `heart-beat:5000,5000` thì hai phía thường mong hoạt động tối thiểu khoảng 10 giây mỗi hướng, có tolerance với scheduling/network jitter.

Nếu cả hai không có frame STOMP thực cần gửi, STOMP heartbeat là một byte xuống dòng (EOL). Đó **không phải** WebSocket Ping frame và cũng không phải JSON `{"type":"heartbeat"}`.

Raw WebSocket:

~~~text
WS Ping  --> WS Pong (control frame)
~~~

STOMP over WebSocket:

~~~text
STOMP CONNECT heart-beat:10000,10000
STOMP CONNECTED heart-beat:5000,5000
... các byte EOL trên WebSocket transport khi im lặng
~~~

Không đặt heartbeat quá dày cho hàng chục nghìn kết nối mà không đo cost. Proxy idle timeout, broker heartbeat policy và WebSocket transport timeout đều có thể ảnh hưởng liveness.

## 12. ACK/NACK và mức độ tin cậy

STOMP có ba acknowledgement mode trong SUBSCRIBE:

| Mode | Ý nghĩa |
| --- | --- |
| `auto` | Broker coi message đã giao khi gửi, không yêu cầu ACK riêng |
| `client` | Client ACK theo kiểu cộng dồn (cumulative) cho các message trước đó trong subscription |
| `client-individual` | ACK/NACK riêng từng message |

Ví dụ:

~~~text
SUBSCRIBE
id:orders-1
destination:/queue/orders
ack:client-individual

<NULL>
~~~

Server gửi MESSAGE và có thể kèm header `ack`, client ACK theo ID header đó:

~~~text
ACK
id:ack-token-from-message

<NULL>
~~~

**ACK ở đây không tự động chứng minh ứng dụng đã commit database thành công.** Ứng dụng phải định nghĩa ranh giới “xử lý xong mới ACK”, sử dụng transaction/idempotency, và hiểu redelivery policy của broker.

STOMP `RECEIPT` khác `ACK`:

- `RECEIPT` xác nhận broker/server đã xử lý một client frame có request receipt.
- `ACK` xác nhận việc tiêu thụ một MESSAGE theo subscription mode.
- Cả hai đều **không** tạo exactly-once end-to-end nếu ứng dụng không có thiết kế bổ sung.

WebSocket thuần không có ACK/NACK ở tầng ứng dụng; muốn tương tự phải tự triển khai message ID, pending table, timeout, retry, duplicate handling và persistence.

## 13. Authentication, authorization và security

Cả hai mô hình đều cần security, nhưng điểm kiểm soát khác nhau.

### 13.1. Handshake authentication

WebSocket bắt đầu bằng HTTP handshake. Có thể dùng cookie/session hoặc cơ chế xác thực được hỗ trợ trước khi nâng cấp connection. Trên browser, WebSocket API không cho đặt arbitrary HTTP Authorization header giống fetch; nếu cần token, phải thiết kế handshake/cookie/subprotocol/first-message strategy phù hợp và tránh đưa token vào URL hoặc log.

### 13.2. STOMP authentication và destination authorization

STOMP messaging còn có bước CONNECT và các destination như `/app/*`, `/topic/*` hoặc user destination. Cần:

- Xác thực phiên và gắn Principal.
- Xác thực/kiểm tra CONNECT và message headers có nguồn không tin cậy.
- Phân quyền `SEND`/`SUBSCRIBE` theo user, role và resource ID.
- Không tin client tự khai `userId`, `accountId` hoặc bất kỳ destination tùy ý.
- Giới hạn số subscription, kích thước message và tần suất SEND.
- Kiểm soát allowed origins/cross-origin use với cookie authentication.
- Cân nhắc CSRF và authorization model của Spring Security cho inbound STOMP.

Một raw WebSocket ứng dụng cũng phải kiểm tra quyền tương đương trên các message tự định nghĩa. Có STOMP không làm hệ thống tự an toàn. Subscribing `/topic/private/order-42` chỉ vì biết tên không phải bằng chứng user được phép đọc order 42.

### 13.3. WSS

Trong production, ưu tiên `wss://` qua TLS. STOMP trên `ws://` không được mã hóa chỉ vì framing có command và header. Không log STOMP `passcode`, token hay body có PII.

## 14. Backpressure và trách nhiệm vận hành

Trong WebFlux raw, API `Flux`/`Mono` giúp biểu diễn nhu cầu và cancellation. Tuy nhiên, network buffer và client chậm vẫn cần giới hạn: queue không giới hạn, large message và source vô hạn đều có thể làm tăng memory.

Trong Spring STOMP messaging, các channel/broker có executor và outbound buffer riêng. STOMP subscription **không đồng nghĩa** với `request(n)` của Reactive Streams. Khi xử lý payload lớn, kết nối chậm hoặc nhiều subscriber, cần quan sát:

- Active WebSocket sessions và STOMP subscriptions.
- Message throughput vào/ra.
- Queue depth, send time, send buffer.
- Session disconnect/abnormal close.
- Broker relay availability và reconnect.
- Heartbeat misses.
- Publish-to-delivery latency.
- Consumer lag, ACK/NACK/redelivery với broker có hỗ trợ.
- Memory và tài nguyên của broker.

Nếu STOMP là cách kết nối trình duyệt với một broker ngoài, hãy xác định rõ broker chịu trách nhiệm persistence, retry và fan-out; application gateway chịu trách nhiệm authentication, authorization và validation ở đâu.

## 15. Demo A — WebFlux WebSocket thuần (Java 17+)

Demo đầu tiên chứng minh raw WebSocket **không có STOMP**. Một WebSocket endpoint nhận text message và gửi lại text có tiền tố `raw:`.

### 15.1. Cấu trúc dự án

~~~text
raw-webflux-websocket/
  build.gradle
  src/main/java/demo/raw/
    RawApp.java
    RawEchoHandler.java
    RawWebSocketConfig.java
  src/test/java/demo/raw/
    RawWebSocketTest.java
~~~

### 15.2. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.6'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo.raw'
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
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Không thêm `spring-boot-starter-websocket` vào demo raw này: starter đó thường kéo stack Spring MVC/Servlet messaging, không cần thiết cho WebFlux handler trên Reactor Netty.

### 15.3. RawApp.java

~~~java
package demo.raw;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RawApp {
    public static void main(String[] args) {
        SpringApplication.run(RawApp.class, args);
    }
}
~~~

### 15.4. RawEchoHandler.java

~~~java
package demo.raw;

import org.springframework.stereotype.Component;
import org.springframework.web.reactive.socket.WebSocketHandler;
import org.springframework.web.reactive.socket.WebSocketMessage;
import org.springframework.web.reactive.socket.WebSocketSession;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Component
public class RawEchoHandler implements WebSocketHandler {

    @Override
    public Mono<Void> handle(WebSocketSession session) {
        Flux<WebSocketMessage> outgoing = session.receive()
            .map(WebSocketMessage::getPayloadAsText)
            .map(text -> session.textMessage("raw:" + text));

        return session.send(outgoing);
    }
}
~~~

Ở đây chỉ có WebSocket message. Nếu client gửi `ping`, server trả `raw:ping`. Nếu client gửi JSON, server chỉ thêm prefix vào nguyên text, không đọc destination hoặc subscription.

### 15.5. RawWebSocketConfig.java

~~~java
package demo.raw;

import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.HandlerMapping;
import org.springframework.web.reactive.handler.SimpleUrlHandlerMapping;
import org.springframework.web.reactive.socket.WebSocketHandler;

@Configuration
public class RawWebSocketConfig {

    @Bean
    HandlerMapping webSocketMapping(RawEchoHandler handler) {
        SimpleUrlHandlerMapping mapping =
            new SimpleUrlHandlerMapping();

        mapping.setUrlMap(Map.<String, WebSocketHandler>of(
            "/ws/raw", handler
        ));
        mapping.setOrder(-1);
        return mapping;
    }
}
~~~

Spring Boot WebFlux cung cấp cấu hình xử lý WebSocket tương ứng. Nếu xây ứng dụng WebFlux hoàn toàn bằng manual configuration không dùng WebFlux config, phải đăng ký thêm `WebSocketHandlerAdapter` theo tài liệu Spring.

### 15.6. RawWebSocketTest.java

~~~java
package demo.raw;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.net.URI;
import java.time.Duration;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.web.reactive.socket.CloseStatus;
import org.springframework.web.reactive.socket.client.ReactorNettyWebSocketClient;
import org.springframework.web.reactive.socket.client.WebSocketClient;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class RawWebSocketTest {

    @LocalServerPort
    int port;

    @Test
    void rawWebSocketEchoesPlainText() {
        WebSocketClient client = new ReactorNettyWebSocketClient();
        AtomicReference<String> received = new AtomicReference<>();

        URI uri = URI.create("ws://localhost:" + port + "/ws/raw");

        Mono<Void> result = client.execute(uri, session ->
            Mono.when(
                session.send(
                    Mono.just(session.textMessage("ping"))
                ),
                session.receive()
                    .next()
                    .doOnNext(message ->
                        received.set(message.getPayloadAsText()))
                    .then()
            ).then(session.close(CloseStatus.NORMAL))
        );

        StepVerifier.create(result)
            .expectComplete()
            .verify(Duration.ofSeconds(10));

        assertEquals("raw:ping", received.get());
    }
}
~~~

Test minh họa có client WebSocket thực, gửi đúng một text message, nhận phản hồi và đóng session. Không cần STOMP frame hay client STOMP library.

### 15.7. Chạy và thử bằng browser

Tại thư mục demo:

~~~bash
./gradlew bootRun
~~~

Hoặc nếu đã cài Gradle:

~~~bash
gradle bootRun
~~~

Browser console:

~~~javascript
const socket = new WebSocket("ws://localhost:8080/ws/raw");

socket.onopen = () => {
    socket.send("ping");
    socket.send('{"type":"subscribe","channel":"orders"}');
};

socket.onmessage = event => console.log(event.data);
socket.onclose = event => console.log("closed", event.code);
~~~

Dữ liệu server phát trong ví dụ:

~~~text
raw:ping
raw:{"type":"subscribe","channel":"orders"}
~~~

Dòng JSON không đăng ký subscribe thật; raw server không có router cho field `type`. Đây là minh chứng rõ ràng rằng WebSocket chỉ chuyển payload, mọi semantics phải do ứng dụng tạo.

## 16. Demo B — Spring STOMP messaging (Servlet stack, Java 17+)

Demo thứ hai là **một dự án Spring Boot khác**, chạy riêng trên port 8081. Nó dùng STOMP over WebSocket, simple broker, `@MessageMapping` và `@SendTo`. Không ghép code dự án này vào demo WebFlux/raw rồi cho rằng hai configuration giống nhau.

### 16.1. Cấu trúc dự án

~~~text
stomp-mvc-messaging/
  build.gradle
  src/main/java/demo/stomp/
    StompApp.java
    StompConfig.java
    GreetingController.java
    HelloRequest.java
    Greeting.java
  src/main/resources/
    application.properties
    static/stomp-client.html
  src/test/java/demo/stomp/
    GreetingControllerTest.java
~~~

### 16.2. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.6'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo.stomp'
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
    implementation 'org.springframework.boot:spring-boot-starter-websocket'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

`spring-boot-starter-websocket` mang vào các dependency cần thiết cho Spring MVC WebSocket messaging. Không thêm `spring-boot-starter-webflux` để “bật STOMP”; đó là hai nhánh kỹ thuật khác nhau.

### 16.3. application.properties

~~~properties
spring.application.name=stomp-mvc-messaging
server.port=8081
~~~

### 16.4. StompApp.java

~~~java
package demo.stomp;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class StompApp {
    public static void main(String[] args) {
        SpringApplication.run(StompApp.class, args);
    }
}
~~~

### 16.5. StompConfig.java

~~~java
package demo.stomp;

import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@Configuration
@EnableWebSocketMessageBroker
public class StompConfig implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws-stomp");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.enableSimpleBroker("/topic");
    }
}
~~~

`/ws-stomp` là đường dẫn WebSocket handshake. `/app` route tới application controllers. `/topic` route tới simple broker. Chúng là ba khái niệm khác nhau.

### 16.6. HelloRequest.java

~~~java
package demo.stomp;

public record HelloRequest(String name) {
}
~~~

### 16.7. Greeting.java

~~~java
package demo.stomp;

public record Greeting(String content) {
}
~~~

### 16.8. GreetingController.java

~~~java
package demo.stomp;

import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.SendTo;
import org.springframework.stereotype.Controller;

@Controller
public class GreetingController {

    @MessageMapping("/hello")
    @SendTo("/topic/greetings")
    public Greeting greet(HelloRequest request) {
        String name = request.name() == null
            ? "khách"
            : request.name().strip();

        if (name.isEmpty()) {
            name = "khách";
        }

        return new Greeting("Xin chào, " + name + "!");
    }
}
~~~

Client gửi `SEND destination:/app/hello` với JSON body `{"name":"An"}`. Spring chuyển payload thành HelloRequest, gọi `greet`, chuyển Greeting thành MESSAGE và broker phát tới các subscriber của `/topic/greetings`.

Đây là messaging controller, **không phải HTTP `@PostMapping("/app/hello")`**. HTTP GET/POST tới /app/hello sẽ không gọi method này.

### 16.9. static/stomp-client.html

Trang HTML sau dùng STOMP client JavaScript qua UMD bundle để thử nhanh. Trong production, nên cài package qua npm và tự bundle, không phụ thuộc một CDN không được quản lý.

~~~html
<!doctype html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <title>STOMP demo</title>
</head>
<body>
    <h1>STOMP messaging demo</h1>
    <input id="name" value="An">
    <button id="send" disabled>Gửi greeting</button>
    <ul id="messages"></ul>

    <script src="https://cdn.jsdelivr.net/npm/@stomp/stompjs@7/bundles/stomp.umd.min.js"></script>
    <script>
        const scheme = location.protocol === "https:" ? "wss:" : "ws:";
        const brokerURL = scheme + "//" + location.host + "/ws-stomp";

        const client = new StompJs.Client({
            brokerURL: brokerURL,
            reconnectDelay: 5000,
            heartbeatIncoming: 10000,
            heartbeatOutgoing: 10000
        });

        client.onConnect = () => {
            client.subscribe("/topic/greetings", message => {
                const greeting = JSON.parse(message.body);
                const item = document.createElement("li");
                item.textContent = greeting.content;
                document.getElementById("messages").appendChild(item);
            });

            document.getElementById("send").disabled = false;
        };

        client.onStompError = frame => {
            console.error("STOMP ERROR", frame.headers["message"]);
        };

        client.onWebSocketClose = event => {
            console.log("WebSocket closed:", event.code);
            document.getElementById("send").disabled = true;
        };

        document.getElementById("send").addEventListener("click", () => {
            const name = document.getElementById("name").value;

            client.publish({
                destination: "/app/hello",
                body: JSON.stringify({name: name}),
                headers: {"content-type": "application/json"}
            });
        });

        client.activate();

        window.addEventListener("beforeunload", () => {
            client.deactivate();
        });
    </script>
</body>
</html>
~~~

Truy cập `http://localhost:8081/stomp-client.html`. Sau khi STOMP CONNECTED, nút Gửi greeting được bật. Khi bấm, STOMP client publish tới `/app/hello`, và subscription nhận JSON Greeting từ `/topic/greetings`.

Việc sử dụng `textContent` giúp trình duyệt không diễn giải nội dung greeting thành HTML tùy ý. Trong ứng dụng thực tế, vẫn phải kiểm tra input và phân quyền destination.

### 16.10. GreetingControllerTest.java

~~~java
package demo.stomp;

import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

class GreetingControllerTest {

    private final GreetingController controller =
        new GreetingController();

    @Test
    void createsGreetingForName() {
        Greeting response =
            controller.greet(new HelloRequest("An"));

        assertEquals("Xin chào, An!", response.content());
    }

    @Test
    void usesGuestNameWhenBlank() {
        Greeting response =
            controller.greet(new HelloRequest("  "));

        assertEquals("Xin chào, khách!", response.content());
    }
}
~~~

Các test này chỉ kiểm tra transformation của method `greet`, **không** kiểm tra broker wiring hay WebSocket handshake. Để kiểm thử end-to-end, cần một STOMP client thật kết nối qua `/ws-stomp`, subscribe `/topic/greetings`, gửi `SEND /app/hello` và xác minh callback nhận MESSAGE.

### 16.11. Chạy ứng dụng

~~~bash
./gradlew bootRun
~~~

Hoặc:

~~~bash
gradle bootRun
~~~

Mở trang:

~~~text
http://localhost:8081/stomp-client.html
~~~

Bấm Gửi greeting với tên “An”. Nội dung giao diện nhận được:

~~~text
Xin chào, An!
~~~

Chạy unit test:

~~~bash
./gradlew test
~~~

Kết quả này khác demo raw: client STOMP quản lý CONNECT/SUBSCRIBE/SEND, controller nhận message theo destination, và broker fan-out đến subscriber. STOMP tạo semantics messaging mà WebSocket thuần không có sẵn.

## 17. Chọn giải pháp theo tình huống thực tế

### Trường hợp A: game hoặc bảng giá tốc độ cao, dữ liệu binary

Raw WebSocket thường là lựa chọn đáng cân nhắc nếu:

- Message schema được kiểm soát chặt giữa một nhóm client và server.
- Cần binary format nhỏ như Protobuf hoặc custom bytes.
- Đã có routing/connection manager riêng.
- Cần kiểm soát scheduling, queue và backpressure theo protocol riêng.

Nhưng phải tự thiết kế message type, version, authorization, subscription (nếu có), recovery và monitoring.

### Trường hợp B: chat room và notification subscription

STOMP có lợi nếu:

- Client cần subscribe/unsubscribe nhiều topic trên một WebSocket.
- Có nhiều producer và consumer.
- Muốn mapping từ destination tới `@MessageMapping`.
- Muốn broadcast thông qua broker.
- Có khả năng cần external broker về sau.

Cần chấp nhận overhead của framing, broker state và giám sát message channels.

### Trường hợp C: hệ thống WebFlux lớn đang chạy Reactor Netty

Không chỉ đổi `WebSocketHandler` thành `@MessageMapping`. Hãy lựa chọn rõ ràng:

1. Giữ raw WebSocket và tự thiết kế protocol nhỏ, đồng thời kết nối broker bằng reactive client phù hợp nếu cần.
2. Tách riêng một Servlet STOMP gateway chịu trách nhiệm WebSocket messaging, phía sau kết nối các service reactive qua API/message broker.
3. Sử dụng STOMP-capable gateway hoặc broker và cấu hình client tương ứng.
4. Nếu chỉ push một chiều, đánh giá SSE để giảm complexity.

Đây là lựa chọn kiến trúc, không đơn thuần là đổi một annotation.

### Trường hợp D: yêu cầu đảm bảo giao nhận

Không chọn STOMP chỉ vì nó có ACK command. Hãy hỏi:

- Broker nào hỗ trợ ACK/NACK thực sự?
- Có persistence hay durable subscription không?
- Khi client reconnect, message nào sẽ được phát lại?
- Message ID/idempotency key được quản lý ở đâu?
- Client ACK sau khi xử lý thành công hay ngay khi nhận?
- Nhiều node có chia sẻ subscription/queue state không?

Nếu các câu trả lời này chưa rõ, STOMP không giúp tự động đạt delivery guarantee.

## 18. Migration từ raw WebSocket sang STOMP

Đổi giao thức cần thay đổi ở cả client và server. Không thể giữ nguyên browser raw WebSocket client gửi JSON trực tiếp rồi kỳ vọng Spring STOMP tự hiểu.

### 18.1. Protocol

Trước:

~~~json
{"type":"join","room":"general"}
~~~

Sau: client STOMP gửi `SUBSCRIBE` tới destination có contract rõ ràng:

~~~text
SUBSCRIBE
id:room-general
destination:/topic/chat/general

<NULL>
~~~

Trước:

~~~json
{"type":"chat","room":"general","message":"hello"}
~~~

Sau:

~~~text
SEND
destination:/app/chat/general
content-type:application/json

{"message":"hello"}<NULL>
~~~

### 18.2. Server API

- Thay raw `WebSocketHandler.handle(session)` bằng Spring STOMP message handler ở stack được hỗ trợ.
- Định nghĩa application destination prefixes và broker destinations.
- Sử dụng `@MessageMapping` cho message gửi tới ứng dụng.
- Dùng `@SendTo` hoặc `SimpMessagingTemplate` cho broadcast.
- Phân quyền SUBSCRIBE/SEND theo destination và user.
- Thiết kế reconnect, heartbeat, ACK và error handling phù hợp broker.

### 18.3. Client API

- Chọn STOMP client library.
- Mở WebSocket transport, gửi CONNECT và chờ CONNECTED.
- Subscribe sau khi kết nối STOMP thành công.
- Publish tới application destination.
- Unsubscribe và deactivate/disconnect khi rời trang.
- Khi reconnect, đăng ký lại subscriptions theo lifecycle của library.
- Xử lý STOMP ERROR và WebSocket close riêng biệt.

### 18.4. Kiểm thử chuyển đổi

| Kiểm thử | Điều cần chứng minh |
| --- | --- |
| WebSocket handshake | URL và subprotocol thương lượng đúng |
| STOMP CONNECT | Nhận CONNECTED trước publish |
| Subscribe | Broker đã đăng ký đúng destination |
| Send | @MessageMapping nhận payload đúng |
| Broadcast | Đúng subscriber nhận MESSAGE |
| Unauthorized subscribe | Client không thể đọc topic ngoài quyền |
| Invalid payload | Lỗi được xử lý và không làm lộ thông tin |
| Heartbeat | Timeout/reconnect được xử lý theo cấu hình |
| Reconnect | Subscription khôi phục theo chính sách |
| Multi-node | External broker hoặc sticky session được cấu hình đúng |
| Slow client | Queue/outbound limits và monitoring hoạt động |

## 19. Lỗi thường gặp

| Nhầm lẫn | Vì sao sai | Cách sửa |
| --- | --- | --- |
| WebSocket tự hiểu SEND/SUBSCRIBE | RFC 6455 không định nghĩa STOMP | Dùng STOMP client/server hoặc tự định nghĩa protocol |
| STOMP là WebSocket version mới hơn | STOMP chạy trên WebSocket | Phân biệt transport với messaging protocol |
| Cứ dùng `new WebSocket(url)` là có STOMP | Browser chỉ mở transport | Dùng STOMP library và CONNECT |
| `/topic/x` là HTTP endpoint | Nó là STOMP destination | Dùng SUBSCRIBE với destination |
| `@MessageMapping` chạy tự động trong raw WebFlux | WebFlux WebSocketHandler không phải STOMP broker | Chọn Spring STOMP configuration/stack phù hợp |
| Gắn `spring-boot-starter-websocket` để “bật STOMP” trong Netty WebFlux | Starter 3.5 kéo MVC Servlet web stack | Tách mô hình và kiểm tra effective application type |
| `/queue` luôn durable | Prefix không định nghĩa delivery semantics | Kiểm tra broker, persistence và policy |
| Simple broker hỗ trợ đủ ACK/receipt | Simple broker chỉ hỗ trợ tập con | Dùng broker có hỗ trợ cần thiết |
| ACK nghĩa là exactly-once | ACK chỉ là acknowledgement ở messaging layer | Dùng idempotency, transaction và recovery |
| STOMP heartbeat là WebSocket Ping | Hai cơ chế ở tầng khác nhau | Cấu hình và giám sát độc lập |
| STOMP ERROR giống WS Close code | Khác tầng protocol | Xử lý ERROR frame và close event riêng |
| HTTP 101 nghĩa là CONNECTED | Chỉ xác nhận WS upgrade | Chờ STOMP CONNECTED |
| Thêm subscription không cần authorization | Client có thể đọc dữ liệu ngoài quyền | Phân quyền SUBSCRIBE theo resource/user |
| Kết nối wss tự bảo đảm payload hợp lệ | TLS không validate nghiệp vụ | Validate schema, rate limit và permission |
| Cứ STOMP là mở rộng multi-node | Simple broker giữ state trong memory | External broker/relay và thiết kế HA |
| Dùng raw WebSocket cho mọi việc | Tự phải xây lại pub/sub/retry | So sánh chi phí với STOMP/SSE/broker |

## 20. Checklist thiết kế

Trước khi quyết định giao thức, trả lời:

1. Ứng dụng cần full-duplex hay chỉ server push một chiều?
2. Client có nhiều subscription/destination hay chỉ một stream đơn?
3. Payload chủ yếu là text/JSON hay binary tốc độ cao?
4. Có cần broadcast qua broker hay server tự xử lý một connection?
5. Framework hiện đang dùng WebFlux reactive hay Servlet MVC?
6. Có chọn đúng starter/module của Spring cho stack đó chưa?
7. Có cần ACK, NACK, RECEIPT, persistence, redelivery không?
8. Broker thực tế có hỗ trợ các tính năng được yêu cầu không?
9. Prefix destination và access control đã định nghĩa chưa?
10. Khi reconnect, client có đăng ký lại và phục hồi state đúng không?
11. Heartbeat và transport Ping/Pong có được hiểu tách biệt không?
12. Có giới hạn message size, rate, subscriptions và queue không?
13. Có test cho handshake, CONNECTED, SEND, SUBSCRIBE, authorization và close không?
14. Có metric cho active connections, broker subscriptions, dropped messages và latency không?
15. Có kế hoạch nâng cấp version protocol khi thay đổi schema không?

## 21. Câu hỏi tự kiểm tra có đáp án

**Câu 1.** WebSocket có định nghĩa message tên `SUBSCRIBE` không?

**Đáp án:** Không. WebSocket là transport với text/binary/control frames. SUBSCRIBE là command thuộc STOMP.

**Câu 2.** STOMP có bắt buộc phải dùng WebSocket không?

**Đáp án:** Không. STOMP là messaging protocol có thể chạy trên một reliable two-way streaming transport, ví dụ TCP hoặc WebSocket.

**Câu 3.** HTTP 101 khác STOMP CONNECTED ở điểm nào?

**Đáp án:** HTTP 101 xác nhận nâng cấp transport sang WebSocket; CONNECTED là xác nhận STOMP session sau đó.

**Câu 4.** WebSocket URL khác STOMP destination thế nào?

**Đáp án:** URL chọn endpoint handshake; destination được dùng trong SEND/SUBSCRIBE để route message bên trong STOMP connection.

**Câu 5.** Dùng WebFlux WebSocketHandler có tự hỗ trợ @MessageMapping không?

**Đáp án:** Không. @MessageMapping là phần của Spring STOMP messaging support được cấu hình trong mô hình phù hợp, không phải tính năng tự có của raw WebFlux WebSocketHandler.

**Câu 6.** `/app/hello` và `/topic/greetings` có vai trò gì trong ví dụ Spring?

**Đáp án:** /app/hello đi tới @MessageMapping("/hello"); /topic/greetings là destination được broker broadcast tới subscriber.

**Câu 7.** Simple broker có phải persistent cluster-aware broker không?

**Đáp án:** Không. Nó là broker in-memory đơn giản, không phù hợp cho mọi tính năng ACK/receipt/clustering.

**Câu 8.** ACK và RECEIPT khác nhau gì?

**Đáp án:** ACK xác nhận consumption của MESSAGE trong subscription mode; RECEIPT xác nhận xử lý frame có request receipt. Không cái nào tự tạo exactly-once end-to-end.

**Câu 9.** STOMP heartbeat là WS Ping frame không?

**Đáp án:** Không. STOMP heartbeat là EOL byte ở messaging layer; WebSocket Ping/Pong là control frame của transport.

**Câu 10.** Trong browser, dùng new WebSocket(url) gửi JSON tới raw handler có phải STOMP?

**Đáp án:** Không. Đó là custom application protocol; cần STOMP frame/client và STOMP-capable server để sử dụng STOMP.

**Câu 11.** Vì sao subscribe destination phải phân quyền?

**Đáp án:** Vì topic name không chứng minh user có quyền xem dữ liệu. Mỗi subscription/resource cần authorization.

**Câu 12.** Khi nào dùng SSE thay WebSocket/STOMP?

**Đáp án:** Khi chủ yếu chỉ cần server đẩy cập nhật một chiều và không cần publish từ browser qua cùng kết nối.

## 22. Tóm tắt và tài liệu tham khảo

- **WebSocket = transport full-duplex**; **STOMP = messaging protocol** trên transport.
- **WebSocket message** không tự mang destination; STOMP frame có command, headers, body và NUL terminator.
- **URL WebSocket** khác **STOMP destination**.
- `HTTP 101` khác `STOMP CONNECTED`.
- `CONNECT`, `SUBSCRIBE`, `SEND`, `MESSAGE`, `ACK`, `NACK`, `RECEIPT` và `DISCONNECT` là STOMP commands, không phải WebSocket control frames.
- Spring WebFlux dùng reactive `WebSocketHandler`; Spring STOMP messaging dùng `@EnableWebSocketMessageBroker`/`@MessageMapping` trong hỗ trợ Servlet stack.
- Simple broker phù hợp pub/sub đơn giản; không hứa đầy đủ ACK, receipt, clustering hoặc persistence.
- Heartbeat STOMP khác Ping/Pong của WebSocket.
- Transport, broker và application đều phải có kiểm soát security, quota, lifecycle và observability.
- Chọn raw hoặc STOMP theo yêu cầu thực sự; không tráo hai mô hình chỉ vì đều dùng WebSocket.

Tài liệu chính thức:

1. [Spring Framework — WebFlux WebSockets](https://docs.spring.io/spring-framework/reference/web/webflux-websocket.html): API reactive WebSocketHandler, receive/send, handshake và lifecycle.
2. [Spring Framework — STOMP Overview](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/overview.html): STOMP over WebSocket, destinations, message flow và broker.
3. [Spring Framework — Enable STOMP](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/enable.html): cấu hình @EnableWebSocketMessageBroker và destination prefixes.
4. [Spring Framework — STOMP Message Flow](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/message-flow.html): clientInboundChannel, brokerChannel và clientOutboundChannel.
5. [Spring Framework — Annotated Controllers](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-annotations.html): @MessageMapping, @SendTo, @SubscribeMapping.
6. [Spring Framework — Simple Broker](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-simple-broker.html): in-memory subscriptions, heartbeat và giới hạn.
7. [Spring Framework — External Broker Relay](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-broker-relay.html): TCP relay tới broker STOMP ngoài, giới hạn simple broker.
8. [STOMP Protocol Specification 1.2](https://stomp.github.io/stomp-specification-1.2.html): framing, commands, ACK modes, heartbeats, receipts và transactions.
9. [Spring Boot 3.5 — WebSockets](https://docs.spring.io/spring-boot/3.5/reference/messaging/websockets.html): starter và phân biệt ứng dụng web reactive/Servlet.
10. [Spring Getting Started — Messaging with STOMP over WebSocket](https://spring.io/guides/gs/messaging-stomp-websocket): ví dụ được Spring hướng dẫn xây dựng.
