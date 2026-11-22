# Xử lý ngoại lệ, sự kiện kết nối, giám sát và kiểm thử WebSocket trong Spring

## 1. Mục tiêu và phạm vi

Một WebSocket endpoint không chỉ cần nhận và gửi message. Để vận hành đáng tin cậy, ứng dụng phải xác định **lỗi xảy ra ở giai đoạn nào**, biết **khi nào kết nối/STOMP session thực sự tồn tại**, **dọn trạng thái khi kết nối đóng**, có chỉ số quan sát được và có bài kiểm thử cả đường truyền.

Trong Spring Framework 6.x với Java 17+, bài học phân biệt hai mô hình:

1. **Raw WebSocket trên Servlet stack**: `WebSocketHandler`, `TextWebSocketHandler`, `WebSocketSession` và các callback như `handleTransportError`, `afterConnectionClosed`.
2. **STOMP over WebSocket**: `@EnableWebSocketMessageBroker`, `@MessageMapping`, `@MessageExceptionHandler`, sự kiện `SessionConnectEvent`, `SessionConnectedEvent`, `SessionDisconnectEvent`, `BrokerAvailabilityEvent`; kèm `WebSocketMessageBrokerStats` và kiểm thử STOMP.

Đến cuối bài, bạn có thể phân biệt lỗi handshake, lỗi transport, lỗi xử lý message và lỗi broker; viết handler/lắng nghe sự kiện theo vòng đời; đo kết nối đang mở, lỗi và lưu lượng; kiểm thử raw WebSocket với WebSocket client thật; và xây chiến lược kiểm thử STOMP có giới hạn thời gian rõ ràng.

Các ví dụ chính dùng **Spring Boot 3.3.x + Java 17**, thuộc **Servlet / Spring MVC stack**. API reactive WebFlux WebSocket nằm ở package khác và có callback khác; không copy ví dụ Servlet `WebSocketHandler` trực tiếp sang WebFlux.

## 2. Bốn nhóm lỗi thường bị nhầm với nhau

Một kết nối có thể lỗi trước hoặc sau khi protocol được nâng cấp. Chọn đúng tầng xử lý quan trọng hơn việc đặt một khối `try/catch` thật rộng.

| Giai đoạn | Ví dụ | Nơi xử lý/quan sát | Tín hiệu tới client |
| --- | --- | --- | --- |
| HTTP handshake, trước upgrade | Sai URL, thiếu xác thực, origin bị chặn | Servlet filter, Spring Security, `HandshakeInterceptor`, `HandshakeHandler` | HTTP 400/401/403/404 hoặc lỗi handshake |
| Transport WebSocket, sau upgrade | Socket đứt, lỗi đọc/ghi, client đóng tab | `handleTransportError`, `afterConnectionClosed` | Close frame nếu còn gửi được, hoặc mất kết nối |
| Raw message / nghiệp vụ | Lệnh không hợp lệ, payload vượt giới hạn, lỗi service | `handleTextMessage`, validation, logic service | Message lỗi do ứng dụng định nghĩa hoặc close code |
| STOMP message / broker | Payload không hợp lệ, destination không được phép, broker mất kết nối | `@MessageExceptionHandler`, `ChannelInterceptor`, broker events/error handler | STOMP message đến user, STOMP `ERROR` frame hoặc disconnect, tùy loại lỗi |

**Điểm mốc:** HTTP status được trả **khi chưa nâng cấp**. Sau HTTP `101 Switching Protocols`, không còn một HTTP response riêng cho từng WebSocket frame. Vì thế, không “trả HTTP 400” từ `handleTextMessage` hay `@MessageMapping`. Nếu lỗi nghiệp vụ có thể phục hồi, nên chuẩn hóa message lỗi ở tầng ứng dụng; nếu lỗi protocol/chính sách nghiêm trọng, đóng session đúng ngữ nghĩa.

### 2.1. Close code WebSocket

| Code | Ý nghĩa thực tế |
| --- | --- |
| 1000 | Đóng bình thường |
| 1001 | Đầu bên kia rời đi/shutdown |
| 1002 | Lỗi protocol |
| 1003 | Không chấp nhận loại dữ liệu |
| 1008 | Vi phạm chính sách |
| 1009 | Message quá lớn |
| 1011 | Server gặp lỗi bất ngờ |

Code **1006 là trạng thái quan sát kết nối đóng bất thường**, không được gửi trong WebSocket close frame. Tương tự, các code dự trữ không được tự ý dùng làm mã ứng dụng. Một transport error có thể không gửi được close frame, nên client chỉ quan sát mất kết nối chứ không nhất thiết nhận 1011.

## 3. Raw WebSocket: callback xử lý lỗi và vòng đời

Spring Servlet định nghĩa `org.springframework.web.socket.WebSocketHandler`:

```java
void afterConnectionEstablished(WebSocketSession session) throws Exception;
void handleMessage(WebSocketSession session, WebSocketMessage<?> message)
        throws Exception;
void handleTransportError(WebSocketSession session, Throwable exception)
        throws Exception;
void afterConnectionClosed(WebSocketSession session, CloseStatus status)
        throws Exception;
boolean supportsPartialMessages();
```

Đây là **chữ ký API để giải thích**, không phải class Java tự chạy. Khi xử lý text, kế thừa `org.springframework.web.socket.handler.TextWebSocketHandler` và override `handleTextMessage(...)`. Lớp cơ sở hỗ trợ callback lifecycle mặc định.

### 3.1. Các callback cần hiểu chính xác

- `afterConnectionEstablished`: Spring gọi khi handshake thành công và session sẵn sàng. Dùng để đăng ký session, tăng gauge số kết nối, gửi lời chào khi cần.
- `handleTextMessage`: xử lý payload text của **một session cụ thể**. Validate dữ liệu, gọi service, rồi gửi response đúng schema. Không nên để một exception dự kiến (như input sai) lan truyền thành lỗi server.
- `handleTransportError`: nhận lỗi từ tầng truyền tải; có thể log loại lỗi, tăng counter, thử đóng session nếu còn mở. Nó **không phải** callback tổng quát chắc chắn bắt mọi exception nghiệp vụ hay mọi thất bại mạng.
- `afterConnectionClosed`: xóa session khỏi registry và hủy tài nguyên liên quan. Không nên gửi message mới tại đây.
- `supportsPartialMessages`: liên quan cách handler hỗ trợ partial WebSocket messages; không đồng nghĩa STOMP message fragmentation.

Một ứng dụng có nhiều client có thể chia sẻ **một handler bean singleton**. Không lưu `private WebSocketSession currentUserSession;` trong singleton để đại diện tất cả client. Một số callback đóng/lỗi có thể đến trong các tình huống chồng chéo; các thao tác dọn dẹp phải **idempotent**, chẳng hạn dùng `Set.remove(sessionId)` rồi chỉ giảm bộ đếm nếu phần tử thực sự tồn tại.

### 3.2. Lỗi dự kiến và lỗi bất ngờ

Ví dụ nguyên tắc trong subclass:

```java
@Override
protected void handleTextMessage(WebSocketSession session,
                                 TextMessage message) throws Exception {
    String text = message.getPayload();

    if (text.length() > 1024) {
        session.close(CloseStatus.TOO_BIG_TO_PROCESS);
        return;
    }

    if (!"PING".equals(text)) {
        session.sendMessage(new TextMessage("ERROR:BAD_COMMAND"));
        return;
    }

    session.sendMessage(new TextMessage("PONG"));
}
```

Ở đây `ERROR:BAD_COMMAND` là **quy ước ứng dụng**, không phải WebSocket ERROR frame chuẩn. Payload quá lớn là chính sách khác, đóng với 1009. Nếu backend đòi hỏi JSON, nên thiết kế response dạng mã lỗi ổn định (ví dụ `{"type":"error","code":"INVALID_COMMAND"}`) và không gửi stack trace ra client.

Nếu một exception không được xử lý thoát khỏi handler, Spring có lớp hạ tầng như `ExceptionWebSocketHandlerDecorator` để hỗ trợ đóng session trong trường hợp lỗi. Không dựa vào hành vi đóng lỗi mặc định để truyền lỗi nghiệp vụ cho client; tự định nghĩa cách trả lỗi có kiểm soát và thu thập log/metrics ở server.

### 3.3. Không gửi đồng thời từ nhiều thread một cách tùy ý

Với Servlet WebSocket dựa trên Jakarta WebSocket, phần gửi qua một session thường cần serialization; nhiều producer cùng `session.sendMessage(...)` có thể xung đột. `ConcurrentWebSocketSessionDecorator` hỗ trợ giới hạn thời gian gửi và buffer:

```java
WebSocketSession safe =
        new ConcurrentWebSocketSessionDecorator(
                session, 10_000, 64 * 1024);
```

Đây là snippet: import `org.springframework.web.socket.handler.ConcurrentWebSocketSessionDecorator`. Trong hệ thống broadcast, tạo và quản lý **một wrapper nhất quán cho mỗi session** rồi gửi qua wrapper đó. Không bọc mới cho từng message, vì như vậy không bảo đảm tất cả producer chia sẻ cùng cơ chế gửi.

## 4. STOMP: lỗi ở @MessageMapping và lỗi giao thức là hai chuyện khác

STOMP là giao thức nhắn tin trên WebSocket. Phân luồng thường là:

```text
Client WebSocket handshake /stomp (HTTP 101)
  -> STOMP CONNECT -> CONNECTED
  -> STOMP SUBSCRIBE /topic/...
  -> STOMP SEND /app/...
  -> clientInboundChannel
  -> @MessageMapping controller
  -> /topic/... hoặc /user/queue/...
  -> brokerChannel -> clientOutboundChannel
  -> STOMP MESSAGE tới subscriber
```

### 4.1. @MessageExceptionHandler

Nếu một method `@MessageMapping` ném exception nghiệp vụ, Spring Messaging hỗ trợ `@MessageExceptionHandler`, cùng ý tưởng với `@ExceptionHandler` trên HTTP controller nhưng vận hành ở **message handling**, không tự tạo HTTP response:

```java
@Controller
class PingController {
    record PingRequest(String text) {}
    record ErrorReply(String code) {}

    @MessageMapping("/ping")
    @SendTo("/topic/pongs")
    String ping(PingRequest body) {
        if (body == null || body.text() == null ||
                body.text().isBlank()) {
            throw new IllegalArgumentException("text required");
        }
        return "PONG:" + body.text();
    }

    @MessageExceptionHandler(IllegalArgumentException.class)
    @SendToUser(value = "/queue/errors", broadcast = false)
    ErrorReply badInput(IllegalArgumentException exception) {
        return new ErrorReply("INVALID_TEXT");
    }
}
```

Đoạn trên minh họa **đặt trong controller và có imports thích hợp**. Client SEND đến `/app/ping`. Người đăng ký `/topic/pongs` có thể nhận message thành công. Khi body sai, client liên quan đăng ký `/user/queue/errors` để nhận mã lỗi. `broadcast=false` tránh phát cùng lỗi đến mọi session khác của một user có nhiều kết nối; với anonymous session, nó cũng hữu ích để định tuyến về session liên quan.

`@MessageExceptionHandler` có thể được khai báo cùng controller hoặc đặt trong class `@ControllerAdvice` để áp dụng rộng hơn. Không gửi raw exception message/stack trace cho browser vì có thể lộ thông tin cấu trúc dịch vụ hay dữ liệu nhạy cảm. Việc exception được xử lý không có nghĩa phải tự đóng WebSocket.

### 4.2. STOMP ERROR frame và StompSubProtocolErrorHandler

Lỗi parse STOMP frame, lỗi protocol, lỗi ở kênh xử lý hoặc lỗi hạ tầng khác có thể đi theo đường **STOMP ERROR** riêng, không đi qua một `@MessageExceptionHandler` của controller. Spring cung cấp `StompSubProtocolErrorHandler` để tùy biến thông báo lỗi ở mức subprotocol. Có thể cấu hình thông qua `StompEndpointRegistry.setErrorHandler(...)` trong cấu hình broker, ví dụ với implementation đã được thiết kế để không lộ chi tiết nội bộ.

STOMP `ERROR` frame có thể dẫn tới đóng kết nối. Client nên phân biệt:

- **Message lỗi nghiệp vụ** ở `/user/queue/errors`: ứng dụng có thể tiếp tục giữ kết nối và xử lý request khác.
- **STOMP ERROR frame**: lỗi subprotocol/broker, có thể kèm disconnect; cần kiểm tra kết nối và chính sách reconnect.
- **WebSocket transport close/error**: có thể không hề có STOMP ERROR frame.

### 4.3. BrokerAvailabilityEvent và gửi chủ động

Nếu dùng broker relay (ví dụ broker ngoài ứng dụng), một `BrokerAvailabilityEvent` cho biết trạng thái broker có sẵn/không có sẵn để gửi thông điệp. Broker đơn giản nội bộ thường available ngay sau khởi động; broker relay có thể mất kết nối và khôi phục.

Thành phần gọi `SimpMessagingTemplate.convertAndSend(...)` nên lưu trạng thái availability khi thích hợp, nhưng vẫn cần xử lý `MessageDeliveryException`/lỗi gửi: một event availability chỉ là trạng thái quan sát tại thời điểm nhất định, không bảo đảm lần gửi sau sẽ luôn thành công.

## 5. Sự kiện kết nối STOMP: mốc nào mới được coi là online?

Các sự kiện sau đến từ Spring ApplicationContext khi dùng STOMP-over-WebSocket:

| Event | Thời điểm | Lưu ý |
| --- | --- | --- |
| `SessionConnectEvent` | Server nhận STOMP `CONNECT` | Đây **chưa** phải xác nhận session STOMP đã hoàn tất |
| `SessionConnectedEvent` | Broker phản hồi STOMP `CONNECTED` | Có thể tính là STOMP session đã kết nối |
| `SessionSubscribeEvent` | Client gửi `SUBSCRIBE` | Không đồng nghĩa hệ thống đã xác nhận mọi bước của subscription |
| `SessionUnsubscribeEvent` | Client gửi `UNSUBSCRIBE` | Dùng cập nhật subscription tracking nếu cần |
| `SessionDisconnectEvent` | STOMP session chấm dứt | Có thể được phát **hơn một lần** với cùng session; phải idempotent |
| `BrokerAvailabilityEvent` | Broker chuyển trạng thái available/unavailable | Hữu ích khi có broker relay hoặc gửi chủ động |

**Hai tầng kết nối:** WebSocket HTTP handshake thành công chỉ nói kết nối WebSocket đã mở. Client còn cần gửi STOMP `CONNECT` và nhận `CONNECTED` trước khi nói một STOMP session đã sẵn sàng. Khi broker gặp vấn đề, có thể có socket sống nhưng STOMP messaging chưa sử dụng được.

### 5.1. Lắng nghe bằng @EventListener

```java
@Component
class StompSessions {
    private final Set<String> online = ConcurrentHashMap.newKeySet();

    @EventListener
    public void connected(SessionConnectedEvent event) {
        String id = SimpMessageHeaderAccessor
                .wrap(event.getMessage())
                .getSessionId();
        if (id != null) {
            online.add(id);
        }
    }

    @EventListener
    public void disconnected(SessionDisconnectEvent event) {
        online.remove(event.getSessionId());
    }
}
```

Đây là **snippet**, cần imports từ `java.util.Set`, `java.util.concurrent.ConcurrentHashMap`, `org.springframework.context.event.EventListener`, `org.springframework.stereotype.Component`, `org.springframework.messaging.simp.SimpMessageHeaderAccessor`, `org.springframework.web.socket.messaging.SessionConnectedEvent` và `SessionDisconnectEvent`.

Tập hợp session ID cho phép xử lý disconnect lặp một cách an toàn. Nếu muốn cập nhật một counter `disconnect_total` đúng “số session đã online rồi đóng”, chỉ tăng sau khi `online.remove(id)` trả về `true`. Với session thất bại trước STOMP CONNECTED, loại này chưa được thêm vào tập; nên đo thất bại handshake/connect riêng.

**Không dùng sự kiện kết nối để tự suy ra quyền truy cập:** việc session tồn tại không có nghĩa user được phép đọc tất cả destinations. Spring Security, interceptor và kiểm tra nghiệp vụ cần áp dụng riêng.

### 5.2. Mức độ đảm bảo và đa instance

Danh sách `online` trong RAM chỉ phản ánh session của **instance đang chạy**. Khi ứng dụng triển khai nhiều node, tổng số kết nối và presence toàn hệ thống cần cơ chế phân tán hoặc tổng hợp metrics qua nhiều instance. SessionDisconnectEvent có thể phát lặp; event listener cũng không phải nguồn chân lý tuyệt đối cho việc user đang online nếu mạng đứt và timeout chưa phát hiện.

Spring simple broker thích hợp bắt đầu phát triển nhưng không có đầy đủ chức năng broker ngoài, không phù hợp để mở rộng cụm server theo cách relay multi-node. Với yêu cầu routing xuyên node, cân nhắc full broker relay và thiết kế reconnect/authorization rõ ràng.

## 6. Giám sát WebSocket: đo gì và ở tầng nào?

Không có một metric duy nhất chứng minh dịch vụ WebSocket đang khỏe. Ít nhất cần theo dõi:

| Tín hiệu | Điều nó trả lời | Cách diễn giải |
| --- | --- | --- |
| Số raw WebSocket sessions đang mở | Có bao nhiêu kết nối transport hiện tại? | Gauge tăng/giảm theo lifecycle |
| Số STOMP sessions connected | Có bao nhiêu session STOMP đã nhận CONNECTED? | Có thể khác số socket đang mở |
| Kết nối/đóng bất thường theo thời gian | Mạng/proxy/broker có mất ổn định? | Counter/rate; phân loại close status |
| Lỗi transport và lỗi ứng dụng | Lỗi hạ tầng hay dữ liệu? | Tách lỗi transport/validation/server |
| Inbound/outbound messages | Lưu lượng theo giây và theo loại | Counter; không gắn payload làm metric label |
| Kích thước message, send buffer và send time | Client chậm hoặc quá tải? | Xem phân phối, giới hạn configured |
| STOMP CONNECT/CONNECTED/DISCONNECT và subscriptions | Client hoạt động ở tầng STOMP ra sao? | DISCONNECT count có thể ít hơn do rớt mạng |
| Broker relay availability và pending tasks | Broker hoặc executor có nghẽn? | Quan sát với queue/executor stats |

### 6.1. WebSocketMessageBrokerStats cho STOMP

Khi dùng `@EnableWebSocketMessageBroker`, Spring tạo bean `org.springframework.web.socket.config.WebSocketMessageBrokerStats`. Theo cấu hình mặc định, bean này tổng hợp và **log thông tin thống kê ở mức INFO khoảng mỗi 30 phút**: client WebSocket/SockJS sessions, STOMP frames, broker relay khi có, inbound/outbound executor và các giới hạn/lỗi kết nối.

Đây là thống kê dành cho **STOMP message broker infrastructure**, không tự động thay thế metrics raw `WebSocketHandler` do ứng dụng tự xây. Có thể xem theo kiểu:

```java
@Component
class BrokerStatsReader {
    private final WebSocketMessageBrokerStats stats;

    BrokerStatsReader(WebSocketMessageBrokerStats stats) {
        this.stats = stats;
    }

    void inspect() {
        String summary = stats.toString();
        // Chuyển summary sang log nội bộ hoặc hệ thống giám sát phù hợp.
    }
}
```

Snippet này giải thích cách lấy bean; không tự gọi `inspect()` nếu không có scheduler/caller. Trong Spring 6.2, nhiều structured getters thay thế các API thống kê chuỗi đã deprecated; nên kiểm tra Javadoc đúng phiên bản nếu tích hợp dashboard tự động. BrokerStats không phải API phân tán: nếu có nhiều application instances, mỗi instance có số liệu riêng.

### 6.2. Spring Boot Actuator và Micrometer

Nếu bổ sung `spring-boot-starter-actuator`, bạn có thể đăng ký counters và gauges cho logic ứng dụng, rồi xem bằng endpoint metrics hoặc hệ thống thu thập được cấu hình. Ví dụ thiết kế metric:

```text
demo.ws.raw.active              gauge  - raw sessions hiện đang mở
demo.ws.raw.messages            counter - text messages đã nhận
demo.ws.raw.transport.errors    counter - lỗi transport quan sát được
demo.ws.stomp.active            gauge  - STOMP CONNECTED chưa disconnect
demo.ws.stomp.connected         counter - số session CONNECTED
demo.ws.stomp.disconnected      counter - số session CONNECTED đã đóng
demo.ws.stomp.subscriptions     counter - SUBSCRIBE frame đã nhận
```

**Quy tắc cardinality:** không đưa `sessionId`, `userId`, room ID tự do, token, message text hoặc path có biến vô hạn vào metric tag. Những giá trị này tạo quá nhiều time series, tốn bộ nhớ và có thể làm rò dữ liệu. Metric nên có tag hữu hạn như `protocol=raw|stomp`, `result=success|error`, `reason=normal|transport|timeout`.

**Phân biệt:** metric counter thường tăng kể cả khi người dùng reconnect; gauge thể hiện trạng thái ở thời điểm đọc. Khi application restart, số counter của instance bắt đầu lại từ 0, nên dashboard cần rate/aggregation đúng.

### 6.3. Structured logging và correlation

Một log hữu ích thường chứa **thời gian, loại event, session correlation ID nội bộ, loại close code, exception class, thời lượng xử lý, broker status**. Không log cookie, STOMP authorization headers, personal data hoặc toàn bộ nội dung private chat.

Các thread khác nhau có thể xử lý message của cùng WebSocket session. Không giả định `ThreadLocal` hay MDC của HTTP handshake tự truyền qua mọi callback/executor. Nếu cần correlation, truyền context rõ ràng qua message headers/attributes hoặc một interceptor có chính sách xóa MDC để tránh lây sang request khác.

## 7. Ví dụ chạy được: raw + STOMP + sự kiện + Micrometer metrics

Demo sau gồm hai endpoint trên cùng ứng dụng Servlet:

- `ws://localhost:8080/ws/raw`: raw text WebSocket, nhận `PING` trả `PONG`, input khác trả `ERROR:BAD_COMMAND`.
- `ws://localhost:8080/stomp`: STOMP endpoint. Client subscribe `/topic/pongs`, gửi JSON `{"text":"hello"}` tới `/app/ping` và nhận JSON reply. Nếu thiếu text, `@MessageExceptionHandler` gửi error về `/user/queue/errors`.

Các phần đều dùng Java 17, Spring Boot 3.3.x. Demo **mở cho local để học**, chưa có authentication/authorization nên không nên public trực tiếp ra Internet.

### 7.1. Cấu trúc

```text
websocket-observation-demo/
├── build.gradle
└── src/
    ├── main/
    │   ├── java/demo/ws/
    │   │   ├── DemoApplication.java
    │   │   ├── RawHandler.java
    │   │   ├── RawConfig.java
    │   │   ├── StompConfig.java
    │   │   ├── PingController.java
    │   │   └── StompMonitor.java
    │   └── resources/
    │       ├── application.properties
    │       └── static/index.html
    └── test/
        └── java/demo/ws/RawWebSocketIntegrationTest.java
```

### 7.2. build.gradle

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.6'
    id 'io.spring.dependency-management' version '1.1.6'
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
    implementation 'org.springframework.boot:spring-boot-starter-websocket'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`spring-boot-starter-websocket` cung cấp Spring MVC WebSocket/STOMP và embedded Servlet container. `spring-boot-starter-actuator` cung cấp Micrometer và điểm truy vấn metrics; `spring-boot-starter-test` cung cấp JUnit 5 / Spring Boot test. Mọi dependency đều được Spring Boot quản lý phiên bản để tránh lẫn Spring 5/6 hoặc `javax.websocket` với `jakarta.websocket`.

### 7.3. DemoApplication.java

```java
package demo.ws;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

Tất cả class còn lại cùng package `demo.ws` để được component scan.

### 7.4. RawHandler.java: phân biệt lỗi nghiệp vụ và transport

```java
package demo.ws;

import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Component;
import org.springframework.web.socket.CloseStatus;
import org.springframework.web.socket.TextMessage;
import org.springframework.web.socket.WebSocketSession;
import org.springframework.web.socket.handler.TextWebSocketHandler;

@Component
public class RawHandler extends TextWebSocketHandler {
    private final Set<String> live = ConcurrentHashMap.newKeySet();
    private final Counter messages;
    private final Counter transportErrors;

    public RawHandler(MeterRegistry metrics) {
        Gauge.builder("demo.ws.raw.active", live, Set::size)
                .register(metrics);
        this.messages = Counter.builder("demo.ws.raw.messages")
                .register(metrics);
        this.transportErrors =
                Counter.builder("demo.ws.raw.transport.errors")
                        .register(metrics);
    }

    @Override
    public void afterConnectionEstablished(WebSocketSession session) {
        live.add(session.getId());
    }

    @Override
    protected void handleTextMessage(WebSocketSession session,
                                     TextMessage message) throws Exception {
        messages.increment();
        String text = message.getPayload();

        if (text.length() > 1024) {
            session.close(CloseStatus.TOO_BIG_TO_PROCESS);
            return;
        }

        if (!"PING".equals(text)) {
            session.sendMessage(new TextMessage("ERROR:BAD_COMMAND"));
            return;
        }

        session.sendMessage(new TextMessage("PONG"));
    }

    @Override
    public void handleTransportError(WebSocketSession session,
                                     Throwable cause) throws Exception {
        transportErrors.increment();
        if (session.isOpen()) {
            session.close(CloseStatus.SERVER_ERROR);
        }
    }

    @Override
    public void afterConnectionClosed(WebSocketSession session,
                                      CloseStatus status) {
        live.remove(session.getId());
    }
}
```

Handler không giữ session của một user trong field chung; `live` là set các ID đang mở. `remove` idempotent khi callback close đến sau lỗi. Đoạn raw demo chỉ có một nguồn gửi ngay trong callback; khi chuyển thành hệ thống broadcast đa luồng, cần thêm bảo vệ concurrent send và buffer.

Giới hạn `text.length() > 1024` dùng số UTF-16 code units để minh họa. Trong hệ thống thật cần cấu hình giới hạn **bytes, frame và buffer** ở container, kiểm tra kích thước payload trước khi xử lý và đặt các giới hạn tài nguyên theo nhu cầu. Server có thể từ chối message trước khi callback này được gọi.

### 7.5. RawConfig.java: đăng ký raw WebSocket

```java
package demo.ws;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.socket.config.annotation.EnableWebSocket;
import org.springframework.web.socket.config.annotation.WebSocketConfigurer;
import org.springframework.web.socket.config.annotation.WebSocketHandlerRegistry;

@Configuration
@EnableWebSocket
public class RawConfig implements WebSocketConfigurer {
    private final RawHandler handler;

    public RawConfig(RawHandler handler) {
        this.handler = handler;
    }

    @Override
    public void registerWebSocketHandlers(WebSocketHandlerRegistry registry) {
        registry.addHandler(handler, "/ws/raw");
    }
}
```

`@EnableWebSocket` + `WebSocketConfigurer` dành cho raw Servlet WebSocket. Đây không phải `@MessageMapping` và cũng không phát các `SessionConnectedEvent` ở tầng STOMP.

### 7.6. StompConfig.java: endpoint STOMP và giới hạn transport

```java
package demo.ws;

import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;
import org.springframework.web.socket.config.annotation.WebSocketTransportRegistration;

@Configuration
@EnableWebSocketMessageBroker
public class StompConfig implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/stomp");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry config) {
        config.setApplicationDestinationPrefixes("/app");
        config.enableSimpleBroker("/topic", "/queue");
    }

    @Override
    public void configureWebSocketTransport(
            WebSocketTransportRegistration registration) {
        registration.setMessageSizeLimit(64 * 1024);
        registration.setSendBufferSizeLimit(512 * 1024);
        registration.setSendTimeLimit(15_000);
    }
}
```

`setMessageSizeLimit` điều chỉnh giới hạn inbound **STOMP subprotocol message** sau reassembly. `setSendBufferSizeLimit`/`setSendTimeLimit` giúp hạn chế client nhận chậm. Những cấu hình này thuộc STOMP transport registration; không tự áp dụng mọi giới hạn cho raw `RawHandler`.

`enableSimpleBroker` đủ cho ví dụ một instance; không hỗ trợ đầy đủ receipt/ack hay mô hình broker cluster. Dùng external broker relay khi cần chức năng và quy mô tương ứng.

### 7.7. PingController.java: gửi thành công và lỗi nghiệp vụ

```java
package demo.ws;

import org.springframework.messaging.handler.annotation.MessageExceptionHandler;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.SendTo;
import org.springframework.messaging.simp.annotation.SendToUser;
import org.springframework.stereotype.Controller;

@Controller
public class PingController {
    public record PingRequest(String text) {}
    public record PingReply(String text) {}
    public record ErrorReply(String code) {}

    @MessageMapping("/ping")
    @SendTo("/topic/pongs")
    public PingReply onPing(PingRequest request) {
        String text = request == null ? null : request.text();
        if (text == null || text.isBlank()) {
            throw new IllegalArgumentException("Text is required");
        }
        return new PingReply("PONG:" + text);
    }

    @MessageExceptionHandler(IllegalArgumentException.class)
    @SendToUser(value = "/queue/errors", broadcast = false)
    public ErrorReply onValidationError(IllegalArgumentException error) {
        return new ErrorReply("INVALID_TEXT");
    }
}
```

Với `@MessageMapping("/ping")` và prefix `/app`, client SEND tới `/app/ping`. Một request hợp lệ tạo `PingReply` tại `/topic/pongs`. Request rỗng ném exception được `@MessageExceptionHandler` chuyển thành response có schema ổn định để gửi đến session liên quan qua user destination `/user/queue/errors`. Đây là **lỗi nghiệp vụ**, không tự động đồng nghĩa đóng WebSocket.

Spring dùng message converter phù hợp (mặc định với Jackson trên classpath) để chuyển JSON payload sang record `PingRequest` và serialize record response. Nếu có lỗi decode trước khi gọi method, loại exception/tầng xử lý có thể khác: phải kiểm thử thực tế với bad JSON.

### 7.8. StompMonitor.java: đếm kết nối đúng mốc và an toàn với disconnect lặp

```java
package demo.ws;

import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.context.event.EventListener;
import org.springframework.messaging.simp.SimpMessageHeaderAccessor;
import org.springframework.stereotype.Component;
import org.springframework.web.socket.messaging.SessionConnectEvent;
import org.springframework.web.socket.messaging.SessionConnectedEvent;
import org.springframework.web.socket.messaging.SessionDisconnectEvent;
import org.springframework.web.socket.messaging.SessionSubscribeEvent;

@Component
public class StompMonitor {
    private final Set<String> connected = ConcurrentHashMap.newKeySet();
    private final Counter connectedTotal;
    private final Counter disconnectedTotal;
    private final Counter subscribeTotal;
    private final Counter connectAttempts;

    public StompMonitor(MeterRegistry metrics) {
        Gauge.builder("demo.ws.stomp.active", connected, Set::size)
                .register(metrics);
        this.connectedTotal = Counter.builder("demo.ws.stomp.connected")
                .register(metrics);
        this.disconnectedTotal =
                Counter.builder("demo.ws.stomp.disconnected")
                        .register(metrics);
        this.subscribeTotal =
                Counter.builder("demo.ws.stomp.subscriptions")
                        .register(metrics);
        this.connectAttempts =
                Counter.builder("demo.ws.stomp.connect.attempts")
                        .register(metrics);
    }

    @EventListener
    public void onConnect(SessionConnectEvent event) {
        connectAttempts.increment();
    }

    @EventListener
    public void onConnected(SessionConnectedEvent event) {
        String sessionId = SimpMessageHeaderAccessor
                .wrap(event.getMessage()).getSessionId();
        if (sessionId != null && connected.add(sessionId)) {
            connectedTotal.increment();
        }
    }

    @EventListener
    public void onSubscribe(SessionSubscribeEvent event) {
        subscribeTotal.increment();
    }

    @EventListener
    public void onDisconnect(SessionDisconnectEvent event) {
        if (connected.remove(event.getSessionId())) {
            disconnectedTotal.increment();
        }
    }
}
```

Chỉ tăng `connectedTotal` khi session ID mới được thêm, và chỉ tăng `disconnectedTotal` khi ID thực sự được xóa. Nhờ đó, hai `SessionDisconnectEvent` cho cùng session không làm bộ đếm âm hoặc tăng số đóng hai lần.

Nếu muốn đo handshake failures hoặc STOMP CONNECT failures, bổ sung metric ở các tầng liên quan; `connectedTotal - disconnectedTotal` không phải bộ đếm chính xác của mọi socket, đặc biệt khi session chưa bao giờ đạt CONNECTED hoặc ứng dụng vừa restart.

### 7.9. application.properties

```properties
server.port=8080
management.endpoints.web.exposure.include=health,info,metrics
management.endpoint.health.show-details=never
```

Bài demo mở `/actuator/metrics` để xem metric; production phải giới hạn mạng, xác thực/phân quyền hoặc đặt actuator lên management port và kiểm soát endpoint. Đừng public toàn bộ actuator chỉ để thuận tiện debug.

### 7.10. static/index.html: thử cả raw và STOMP từ browser

Trang sau dùng WebSocket API của trình duyệt cho **raw** và minh họa **STOMP frames cơ bản** mà không phụ thuộc CDN. Phần STOMP manual chỉ dành cho việc học trên local; client production nên dùng thư viện STOMP có parser, heartbeat và reconnect đầy đủ.

```html
<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <title>WebSocket Observability Demo</title>
</head>
<body>
  <h1>Raw WebSocket + STOMP</h1>
  <button id="rawConnect">Connect raw</button>
  <button id="rawPing">Send raw PING</button>
  <button id="stompConnect">Connect STOMP</button>
  <button id="stompPing">Send STOMP ping</button>
  <button id="stompBad">Send invalid STOMP ping</button>
  <pre id="log"></pre>

  <script>
    const logBox = document.querySelector("#log");
    const protocol = location.protocol === "https:" ? "wss:" : "ws:";
    const base = protocol + "//" + location.host;
    const log = value => { logBox.textContent += value + "\n"; };
    let raw = null;
    let stomp = null;
    let stompReady = false;

    document.querySelector("#rawConnect").onclick = () => {
      raw = new WebSocket(base + "/ws/raw");
      raw.onopen = () => log("RAW OPEN");
      raw.onmessage = event => log("RAW " + event.data);
      raw.onerror = () => log("RAW ERROR");
      raw.onclose = event => log("RAW CLOSE " + event.code);
    };

    document.querySelector("#rawPing").onclick = () => {
      if (raw && raw.readyState === WebSocket.OPEN) {
        raw.send("PING");
      }
    };

    function frame(command, headers, body = "") {
      const lines = [command];
      for (const [key, value] of Object.entries(headers)) {
        lines.push(key + ":" + value);
      }
      return lines.join("\n") + "\n\n" + body + "\0";
    }

    document.querySelector("#stompConnect").onclick = () => {
      stompReady = false;
      stomp = new WebSocket(base + "/stomp", ["v12.stomp", "v11.stomp"]);
      stomp.onopen = () => {
        stomp.send(frame("CONNECT",
          {"accept-version": "1.2,1.1", host: location.hostname}));
      };
      stomp.onmessage = event => {
        const text = String(event.data);
        log("STOMP " + text.replaceAll("\0", "\\0"));
        if (text.startsWith("CONNECTED\n")) {
          stomp.send(frame("SUBSCRIBE",
            {id: "pongs", destination: "/topic/pongs"}));
          stomp.send(frame("SUBSCRIBE",
            {id: "errors", destination: "/user/queue/errors"}));
          stompReady = true;
          log("STOMP SUBSCRIBE sent");
        }
      };
      stomp.onerror = () => log("STOMP ERROR");
      stomp.onclose = event => {
        stompReady = false;
        log("STOMP CLOSE " + event.code);
      };
    };

    function sendPing(text) {
      if (!stompReady || stomp.readyState !== WebSocket.OPEN) {
        log("STOMP chưa CONNECTED");
        return;
      }
      stomp.send(frame("SEND",
        {destination: "/app/ping", "content-type": "application/json"},
        JSON.stringify({text})));
    }

    document.querySelector("#stompPing").onclick =
      () => sendPing("hello");
    document.querySelector("#stompBad").onclick =
      () => sendPing("");
  </script>
</body>
</html>
```

Lưu ý: script manual trên giả định mỗi `onmessage` có thể được đọc như một frame đơn giản để demo. STOMP thực tế cần parser xử lý phân mảnh, nhiều frames và các quy tắc escaping/heartbeat. Simple broker không hỗ trợ receipts đầy đủ, nên `SUBSCRIBE sent` **không phải xác nhận subscriber đã sẵn sàng**; khi kiểm tra thủ công, nhấn gửi sau khi lệnh subscribe đã được hệ thống xử lý. Muốn test chắc chắn, dùng client STOMP chuyên dụng hoặc thiết kế cơ chế ứng dụng xác nhận subscription.

### 7.11. Chạy và quan sát kết quả

Từ thư mục chứa `build.gradle`, với JDK 17+ và Gradle tương thích:

```bash
gradle bootRun
```

Nếu dự án có Gradle Wrapper, dùng `./gradlew bootRun` (Unix/macOS) hoặc `gradlew.bat bootRun` (Windows).

Mở `http://localhost:8080/`:

1. Nhấn **Connect raw**, rồi **Send raw PING**. Phần log có `RAW OPEN` và `RAW PONG`.
2. Nhấn **Connect STOMP**; sau frame `CONNECTED` và subscribe, nhấn **Send STOMP ping**. Trong STOMP MESSAGE tại `/topic/pongs`, body JSON dự kiến `{"text":"PONG:hello"}`.
3. Nhấn **Send invalid STOMP ping**; khi subscription user destination đã sẵn sàng, body lỗi dự kiến `{"code":"INVALID_TEXT"}` gửi tới `/user/queue/errors`.
4. Kiểm tra `/actuator/metrics/demo.ws.raw.active`, `/actuator/metrics/demo.ws.raw.messages`, `/actuator/metrics/demo.ws.stomp.active` và `/actuator/metrics/demo.ws.stomp.subscriptions` bằng browser hoặc curl.

Đây là nội dung message/metric dự kiến sau thao tác, **không phải chuỗi stdout cố định**: event timing, metrics format, live session counts và các log bootstrap của Spring Boot thay đổi theo thứ tự client kết nối/đóng. Không suy đoán mọi run sẽ có cùng số liệu.

## 8. Kiểm thử tự động: unit, integration và end-to-end

WebSocket là giao thức sống lâu nên một test tốt phải kiểm tra **thời điểm mở, gửi/nhận và đóng**, không chỉ gọi Java method trực tiếp.

| Tầng test | Những gì được xác minh | Những gì chưa được chứng minh |
| --- | --- | --- |
| Unit test handler/service | Validation, error mapping, state changes | Không xác minh HTTP Upgrade, WebSocket framing, container |
| Spring context / messaging integration | @MessageMapping, channel, converter, handler, event wiring | Chưa chắc kết nối qua network/proxy |
| End-to-end raw WebSocket | Server thật, handshake, send/receive, close | Không tự chứng minh STOMP destination routing |
| End-to-end STOMP | CONNECTED, SUBSCRIBE, SEND, MESSAGE, ERROR và broker | Chưa chắc load/proxy/TLS/đa node |
| Load/soak/chaos | Số kết nối lớn, reconnect, client chậm, broker outage, timeout | Cần môi trường giống production mới có ý nghĩa |

### 8.1. RawWebSocketIntegrationTest.java: bài test chạy với server thật

Test sau dùng JUnit 5 và `@SpringBootTest(webEnvironment = RANDOM_PORT)` để chạy embedded Servlet server trên cổng ngẫu nhiên. `StandardWebSocketClient` thực hiện HTTP Upgrade thực tế, không phải direct handler invocation.

```java
package demo.ws;

import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.web.socket.TextMessage;
import org.springframework.web.socket.WebSocketSession;
import org.springframework.web.socket.client.standard.StandardWebSocketClient;
import org.springframework.web.socket.handler.TextWebSocketHandler;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class RawWebSocketIntegrationTest {

    @LocalServerPort
    int port;

    @Test
    void shouldEchoPingAndReportBadCommand() throws Exception {
        BlockingQueue<String> replies = new LinkedBlockingQueue<>();

        TextWebSocketHandler clientHandler = new TextWebSocketHandler() {
            @Override
            protected void handleTextMessage(WebSocketSession session,
                                             TextMessage message) {
                replies.offer(message.getPayload());
            }
        };

        WebSocketSession session = new StandardWebSocketClient()
                .execute(clientHandler,
                        "ws://127.0.0.1:" + port + "/ws/raw")
                .get(5, TimeUnit.SECONDS);

        try {
            session.sendMessage(new TextMessage("PING"));
            assertEquals("PONG",
                    replies.poll(5, TimeUnit.SECONDS));

            session.sendMessage(new TextMessage("BAD"));
            assertEquals("ERROR:BAD_COMMAND",
                    replies.poll(5, TimeUnit.SECONDS));
        } finally {
            session.close();
        }
    }
}
```

Cách chạy:

```bash
gradle test
```

Test dùng timeout hữu hạn để tránh treo CI. Nếu không nhận được message trong 5 giây, `poll` trả null và assertion thất bại có ý nghĩa. `finally` đóng session. Không dùng sleep tùy ý để giả vờ đồng bộ. Có thể dùng `Awaitility` nếu cần đợi gauge trở về 0 một cách ổn định, nhưng metric thường cập nhật bất đồng bộ và không nên assert tức thì sau khi gọi `close()`.

### 8.2. Test STOMP bằng WebSocketStompClient

Spring có `WebSocketStompClient` (package `org.springframework.web.socket.messaging`), phối hợp `StandardWebSocketClient` và `StompSessionHandler`/`StompFrameHandler`. Quy trình e2e hợp lý:

1. Khởi chạy Spring Boot trên random port.
2. Tạo `WebSocketStompClient`, cấu hình `MappingJackson2MessageConverter` nếu muốn truyền/nhận DTO JSON.
3. Gọi `connectAsync(...)` và chờ CONNECTED bằng future/handler.
4. Subscribe `/topic/pongs` và `/user/queue/errors` bằng `StompFrameHandler` trả đúng Java payload type.
5. SEND dữ liệu hợp lệ đến `/app/ping`, đợi message và assert DTO trả về.
6. SEND dữ liệu không hợp lệ, assert error DTO chỉ về user/session liên quan.
7. Disconnect và stop client trong `finally`.

Snippet phía client **minh họa, chưa phải một lớp test đầy đủ**:

```java
WebSocketStompClient stompClient =
        new WebSocketStompClient(new StandardWebSocketClient());
stompClient.setMessageConverter(
        new MappingJackson2MessageConverter());

StompSession session = stompClient
        .connectAsync("ws://127.0.0.1:" + port + "/stomp",
                new StompSessionHandlerAdapter() {})
        .get(5, TimeUnit.SECONDS);
```

Các import bổ sung: `org.springframework.web.socket.messaging.WebSocketStompClient`; `org.springframework.web.socket.messaging.WebSocketStompClient` ở phần code đã nêu; `org.springframework.messaging.converter.MappingJackson2MessageConverter`; `org.springframework.messaging.simp.stomp.StompSession`; `org.springframework.messaging.simp.stomp.StompSessionHandlerAdapter`; `org.springframework.web.socket.client.standard.StandardWebSocketClient`; `java.util.concurrent.TimeUnit`.

**Lưu ý quan trọng để chống flaky test:** Với simple broker, gửi ngay sau `SUBSCRIBE` không bảo đảm subscription đã được lưu xong do messaging channels có thể xử lý bất đồng bộ; simple broker cũng không hỗ trợ đầy đủ STOMP receipt. Nếu test cần một mốc xác nhận đáng tin, thiết kế protocol ứng dụng xác nhận subscription qua một bước khác, hoặc dùng broker hỗ trợ STOMP receipts và đợi receipt. Không dùng `Thread.sleep(500)` làm “bằng chứng” subscriber đã sẵn sàng.

### 8.3. Test sự kiện kết nối và đóng lặp

Cần kiểm chứng hai ca:

- Hai lần thông báo disconnect cho cùng `sessionId` chỉ làm giảm active gauge một lần.
- CONNECT event không đồng nghĩa session đã CONNECTED; chỉ khi connected event đến mới được tính là active.

Với event listener, test unit có thể tạo event tương ứng với mock `Message<?>`/session ID và gọi listener trực tiếp. Đây là test logic idempotency; để xác minh Spring thực sự phát event trong phiên làm việc, cần integration test. Nếu session không kết nối hoàn tất, disconnect cleanup cũng không được làm số active âm.

### 8.4. Test handshake lỗi và abnormal close

Các kịch bản bổ sung:

- Đường dẫn sai: kết nối `/ws/not-found` → handshake không thành công, thường HTTP 404.
- Origin khác bị chặn: có cấu hình allowed-origins phù hợp → handshake từ browser không được phép.
- Token hoặc session thiếu: xác nhận security layer trả 401/403 **trước** upgrade.
- Message quá lớn: kiểm tra chính sách raw handler và giới hạn container. Với payload vượt buffer, handler có thể không thấy message.
- Transport lỗi: giả lập client rớt mạng/proxy đóng socket; đo callback/counters/close status thực tế.
- Nhiều client đồng thời: active gauge tăng, đóng từng client gauge giảm về 0 (đợi eventual consistency).
- STOMP broker relay mất kết nối: quan sát `BrokerAvailabilityEvent`, phát hiện delivery failure, client reconnect.

Không assert một HTTP status hay close code khi trường hợp đó phụ thuộc proxy/container mà chưa cố định môi trường; test cần ghi rõ loại thất bại mong đợi và cách quan sát nó.

## 9. Kịch bản giám sát và xử lý sự cố khi triển khai

### 9.1. Kết nối tăng nhưng không có STOMP message

Kiểm tra HTTP Upgrade có thành công chưa, client đã nhận `CONNECTED` chưa, destination `/app/...`/`/topic/...` đúng chưa và broker có available không. Nếu socket count tăng nhưng STOMP connected count không tăng, ưu tiên kiểm tra STOMP CONNECT, auth/interceptor và broker routing; chưa cần tăng pool size ngay.

### 9.2. Abnormal close tăng đột biến

So khớp thời điểm xảy ra với reverse proxy idle timeout, network drop, restart và giới hạn gửi. Kiểm tra STOMP heartbeat được cấu hình/đồng ý bởi client và server hay chưa; heartbeat không thay thế hoàn toàn TCP/WebSocket transport checks. Quan sát số lần reconnect trên client, hạn chế reconnect storm bằng exponential backoff và jitter.

### 9.3. Latency tăng, send buffer vượt ngưỡng

Xem `clientInboundChannel`/`clientOutboundChannel` executor stats, payload sizes, client chậm, số lượng subscribers và tần suất broadcast. Với STOMP, `setSendTimeLimit` và `setSendBufferSizeLimit` hạn chế tích lũy data cho client chậm. Nếu nghiệp vụ blocking trong message handler, tách việc blocking phù hợp thay vì mở rộng vô hạn executor.

### 9.4. Số sessions không giảm sau disconnect

Rà soát cleanup idempotency; timeout/network half-open có thể khiến callback tới trễ. Đảm bảo không giữ references đến `WebSocketSession` trong map không được dọn. Nếu có subscriber/event listener khác, kiểm tra chúng có giữ state vô hạn không. Không tự giảm counter khi gặp mọi loại lỗi mà chưa biết session đã đăng ký trước đó hay chưa.

### 9.5. Lỗi STOMP không đến đúng client

Xác nhận client đã subscribe `/user/queue/errors`, `@SendToUser(broadcast=false)` có được dùng đúng ngữ cảnh, authenticated principal/user destinations có được cấu hình đúng và lỗi có phát sinh từ `@MessageMapping` hay từ protocol layer. `@MessageExceptionHandler` không thay thế `StompSubProtocolErrorHandler` cho lỗi định dạng frame.

## 10. Bảo mật và giới hạn vận hành

Kết nối dài không có nghĩa quyền của client không thay đổi. Với ứng dụng thực tế cần:

- Xác thực ở HTTP handshake hoặc STOMP CONNECT theo kiến trúc xác thực; kiểm tra quyền truy cập từng destination/room/user.
- Kiểm tra origin cho browser để giảm nguy cơ Cross-Site WebSocket Hijacking. Origin **không phải cơ chế xác thực** với non-browser clients.
- Không đẩy access token, cookie, Authorization hay payload nhạy cảm vào log và metric labels.
- Kiểm soát kích thước và tần suất message, số kết nối mỗi user/IP, send buffers, idle timeout và heartbeat.
- Dùng `wss://` khi triển khai qua HTTPS; bảo đảm reverse proxy cho phép Upgrade/Connection và timeout phù hợp.
- Thiết kế policy cho lỗi có thể phục hồi (message nghiệp vụ), lỗi quyền truy cập nghiêm trọng (đóng kết nối/chặn), lỗi hệ thống (log nội bộ + close) rõ ràng.
- Không mặc định một session STOMP đang CONNECTED nghĩa là user vẫn còn quyền sau khi token/session bị thu hồi; cần chính sách revalidation và disconnect chủ động khi có thể.

## 11. Bài tập tự kiểm tra

**Bài tập 1 — Phân loại lỗi:** Browser kết nối `ws://localhost:8080/ws/raw` nhưng bị HTTP 403; một browser khác kết nối thành công rồi nhận close 1009 sau khi gửi message lớn. Hai trường hợp thuộc tầng xử lý nào? Vì sao không có HTTP 403 ở trường hợp thứ hai?

**Bài tập 2 — Lifecycle:** Client gửi STOMP CONNECT nhưng chưa nhận CONNECTED; server đã nên cộng vào metric `demo.ws.stomp.active` chưa? Lý giải dựa vào SessionConnectEvent và SessionConnectedEvent.

**Bài tập 3 — Lặp disconnect:** Tự gọi listener `onDisconnect` hai lần cho cùng ID đã từng connected. Kỳ vọng gauge và counter thay đổi thế nào? Vì sao phải kiểm tra `Set.remove` trả về `true`?

**Bài tập 4 — Định tuyến lỗi:** SEND JSON `{"text":""}` tới `/app/ping`. Theo demo, lỗi đi qua `@MessageExceptionHandler` về destination nào? Có tự trở thành STOMP ERROR frame hay không?

**Bài tập 5 — Monitoring:** Có 50 raw WebSocket sessions nhưng 45 STOMP sessions, 10 lỗi transport trong một phút và outbound send buffer tăng. Nêu ba giả thuyết cần kiểm tra và metrics/log bổ sung để xác định nguyên nhân, tránh tự kết luận chỉ từ một gauge.

**Bài tập 6 — E2E test:** Bổ sung test kết nối hai raw clients cùng lúc, gửi PING trên một client và chứng minh client kia không nhận message vì endpoint chỉ gửi về session gọi. Đóng cả hai và dùng cơ chế chờ có timeout để xác nhận active gauge trở về 0.

**Bài tập 7 — Reliability:** Nếu ứng dụng chuyển từ simple broker sang broker relay, bổ sung hành vi nào khi BrokerAvailabilityEvent báo false và client mất CONNECTED? Vì sao cần reconnect có backoff và xử lý message delivery failure ngay cả khi event vừa báo true?

## 12. Ghi nhớ các quy tắc quan trọng

1. **Handshake error, transport error, raw message error và STOMP error là bốn tình huống khác nhau.** Chọn handler đúng tầng.
2. `handleTransportError` không phải lưới bắt mọi exception; `afterConnectionClosed` là nơi dọn lifecycle raw WebSocket.
3. `@MessageExceptionHandler` xử lý lỗi method `@MessageMapping`; `StompSubProtocolErrorHandler` dành cho lỗi STOMP ở mức subprotocol.
4. `SessionConnectEvent` khác `SessionConnectedEvent`; tính online của STOMP ở mốc CONNECTED.
5. `SessionDisconnectEvent` có thể phát nhiều lần; cleanup phải idempotent.
6. `WebSocketMessageBrokerStats` phản ánh hạ tầng STOMP, còn raw handler nên đo thêm metric riêng.
7. Một test chỉ gọi handler Java trực tiếp **không chứng minh** WebSocket handshake/frames hoạt động; kết hợp unit, integration và end-to-end.
8. Không dùng sleep tùy ý để bảo đảm STOMP SUBSCRIBE đã sẵn sàng trên simple broker; cần xác nhận đúng tầng.
9. Theo dõi active sessions, errors, closes, message rates, send buffer, broker state và client reconnect; tránh metric labels chứa ID không giới hạn.
10. Hệ thống cần chính sách phân quyền, giới hạn payload, timeout, backpressure/reconnect và logging an toàn trước khi triển khai public.

## Tài liệu chính thức để tra cứu

- Spring WebSocket Servlet API: https://docs.spring.io/spring-framework/reference/6.2/web/websocket/server.html
- Spring STOMP application context events: https://docs.spring.io/spring-framework/reference/6.2/web/websocket/stomp/application-context-events.html
- Spring STOMP annotated controllers và MessageExceptionHandler: https://docs.spring.io/spring-framework/reference/6.2/web/websocket/stomp/handle-annotations.html
- Spring STOMP interception: https://docs.spring.io/spring-framework/reference/6.2/web/websocket/stomp/interceptors.html
- Spring STOMP monitoring: https://docs.spring.io/spring-framework/reference/6.2/web/websocket/stomp/stats.html
- Spring STOMP performance: https://docs.spring.io/spring-framework/reference/6.2/web/websocket/stomp/configuration-performance.html
- Spring STOMP testing: https://docs.spring.io/spring-framework/reference/6.2/web/websocket/stomp/testing.html
- Spring WebSocketClient JavaDoc (6.2): https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/web/socket/client/WebSocketClient.html
