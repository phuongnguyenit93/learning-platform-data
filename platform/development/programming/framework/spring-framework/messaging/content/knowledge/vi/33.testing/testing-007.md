# Kiểm thử đầu cuối bằng WebSocketStompClient

## 1. Mục tiêu và phạm vi

Khi ứng dụng Spring dùng STOMP trên WebSocket, một bài kiểm thử chỉ gọi trực tiếp method của controller không xác nhận được toàn bộ đường đi của message. Request thực tế còn đi qua WebSocket handshake, STOMP CONNECT, bộ chuyển đổi payload, các destination, message channel, broker và STOMP MESSAGE trả về client.

**WebSocketStompClient** là STOMP client do Spring cung cấp trên nền WebSocketClient. Dùng nó trong kiểm thử đầu cuối (end-to-end, E2E) để kết nối tới server thật đang chạy, gửi STOMP frame và xác nhận frame phản hồi đã tới client.

Bài này hướng dẫn:

- Khởi động server WebSocket trong test và lấy port động.
- Cấu hình WebSocketStompClient, MessageConverter và TaskScheduler.
- Kết nối ở cả tầng WebSocket và STOMP.
- Subscribe, chờ subscription sẵn sàng, gửi message và nhận kết quả.
- Viết StompFrameHandler để chuyển payload thành DTO.
- Thu thập lỗi từ STOMP session và transport.
- Dọn subscription, session, client và scheduler.
- Phân biệt kiểm thử E2E với kiểm thử controller phía server và biết khi nào cần broker thật.

## 2. E2E test kiểm tra những gì?

Một luồng STOMP điển hình trong Spring:

~~~text
Test client
    |
    | WebSocket handshake: GET /ws + Upgrade
    v
WebSocket endpoint
    |
    | STOMP CONNECT
    v
STOMP session / CONNECTED
    |
    | SUBSCRIBE /topic/replies
    v
Message broker lưu subscription
    |
    | SEND /app/echo
    v
clientInboundChannel
    |
    v
@MessageMapping("/echo")
    |
    | @SendTo("/topic/replies")
    v
brokerChannel / broker
    |
    | STOMP MESSAGE
    v
clientOutboundChannel
    |
    v
WebSocketStompClient
    |
    v
StompFrameHandler.handleFrame(...)
    |
    v
Test assertion
~~~

Một bài E2E có thể kiểm tra nhiều thành phần cùng lúc:

| Thành phần | Điều cần xác nhận |
| --- | --- |
| HTTP/WebSocket handshake | Endpoint có thể được mở và server chấp nhận kết nối. |
| STOMP CONNECT/CONNECTED | STOMP version, session và handshake headers được xử lý đúng. |
| MessageConverter | DTO được serialize khi gửi và deserialize khi nhận. |
| Destination routing | Prefix /app tới controller; /topic hoặc /queue tới broker. |
| @MessageMapping | Đúng handler được gọi với payload đã chuyển đổi. |
| Broker subscription | Client đăng ký đúng destination và nhận được MESSAGE. |
| Error handling | STOMP ERROR, lỗi chuyển đổi và lỗi transport được quan sát. |
| Session cleanup | UNSUBSCRIBE và DISCONNECT được gửi khi test kết thúc. |

Spring có hai hướng kiểm thử STOMP-over-WebSocket. Kiểm thử phía server có thể gửi message trực tiếp vào clientInboundChannel để xác minh controller và annotation trong Spring messaging infrastructure. Kiểm thử E2E cần server WebSocket đang chạy và client thật gửi WebSocket message chứa STOMP frame. Hai hướng bổ sung cho nhau; E2E rộng hơn nhưng khởi động và bảo trì tốn công hơn.

MockMvc hoặc một test chỉ gọi method Java không thực hiện WebSocket handshake thật. Nếu cần xác minh handshake, STOMP protocol, broker routing và client nhận frame, hãy chạy server ở chế độ embedded/random port và kết nối bằng WebSocketStompClient.

## 3. Cấu hình STOMP server cần có

Ví dụ cấu hình cho test dùng broker relay hỗ trợ RECEIPT:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@Configuration
@EnableWebSocketMessageBroker
public class WebSocketConfig implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.enableStompBrokerRelay("/topic", "/queue")
            .setRelayHost("localhost")
            .setRelayPort(61613);
    }
}
~~~

Broker STOMP phải đang chạy ở host/port đã cấu hình. Cấu hình đăng nhập, passcode và system connection theo broker thực tế. Nếu chỉ cần broker trong bộ nhớ cho luồng cơ bản, có thể thay relay bằng:

~~~java
registry.enableSimpleBroker("/topic", "/queue");
~~~

Các destination trong ví dụ có ý nghĩa:

- **/ws** là URL endpoint cho WebSocket handshake.
- **/app** là prefix dành cho message được route tới các method @MessageMapping.
- **/topic** và **/queue** là prefix của broker.

Controller xử lý request:

~~~java
import java.util.Locale;

import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.SendTo;
import org.springframework.stereotype.Controller;

@Controller
public class EchoController {

    @MessageMapping("/echo")
    @SendTo("/topic/replies")
    public ChatMessage echo(ChatMessage message) {
        return new ChatMessage(message.text().toUpperCase(Locale.ROOT));
    }
}
~~~

DTO:

~~~java
public record ChatMessage(String text) {
}
~~~

Client sẽ gửi tới /app/echo; Spring loại bỏ application prefix /app để tìm @MessageMapping("/echo"). Kết quả từ method được gửi tới /topic/replies.

Broker đơn giản trong bộ nhớ phù hợp cho luồng cơ bản. Nó chỉ hỗ trợ một tập con của STOMP và không hỗ trợ một số tính năng như ACK/NACK và RECEIPT. Nếu test cần receipt, acknowledgement, broker relay hoặc hành vi riêng của RabbitMQ/ActiveMQ, hãy chạy broker thật trong môi trường kiểm thử và cấu hình enableStompBrokerRelay tương ứng.

## 4. Khởi tạo WebSocketStompClient

### 4.1. Chọn WebSocket transport

Spring cung cấp WebSocketStompClient trên một implementation của WebSocketClient:

~~~java
WebSocketClient webSocketClient = new StandardWebSocketClient();
WebSocketStompClient stompClient =
    new WebSocketStompClient(webSocketClient);
~~~

StandardWebSocketClient dùng chuẩn Java WebSocket. Nếu endpoint hỗ trợ SockJS và test cần kiểm tra SockJS fallback, có thể cấu hình SockJsClient làm WebSocketClient. Hãy dùng đúng URL và transport mà ứng dụng triển khai.

### 4.2. MessageConverter

StompSession.send(destination, payload) dùng MessageConverter để serialize payload thành byte[]. Khi nhận frame, StompFrameHandler khai báo kiểu đích để converter deserialize payload.

Với DTO JSON, cấu hình Jackson converter:

~~~java
stompClient.setMessageConverter(new MappingJackson2MessageConverter());
~~~

Nếu client gửi ChatMessage, converter tạo JSON tương ứng. Ở chiều nhận, handler trả về ChatMessage.class từ getPayloadType, converter sẽ tạo object để handleFrame nhận được.

Nếu không cấu hình converter phù hợp, test có thể gặp lỗi không tìm được converter, payload nhận sai kiểu hoặc lỗi chuyển đổi JSON. Kiểu dữ liệu hai phía và content-type cần tương thích.

### 4.3. TaskScheduler, heartbeat và receipt

Có thể gắn TaskScheduler cho client:

~~~java
ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
scheduler.setPoolSize(1);
scheduler.setThreadNamePrefix("stomp-test-");
scheduler.initialize();

stompClient.setTaskScheduler(scheduler);
~~~

Scheduler được dùng cho heartbeat và theo dõi thời hạn RECEIPT. Khi test broker hỗ trợ receipt, cấu hình scheduler và thời gian hết hạn receipt rõ ràng. Nếu chỉ test một luồng cơ bản với simple broker, không cần bật receipt.

Heartbeat giúp phát hiện kết nối không còn hoạt động. WebSocketStompClient chỉ gửi heartbeat khi không có message khác; traffic ứng dụng có thể được tính là activity. Với test chạy hàng loạt client, cân nhắc tắt heartbeat nếu nó không thuộc hành vi cần kiểm tra vì mỗi session có thể tạo tác vụ heartbeat riêng.

## 5. Kết nối và vòng đời STOMP session

WebSocket handshake thành công chưa đủ để test gửi message. Client còn phải gửi STOMP CONNECT và nhận STOMP CONNECTED.

Với Spring Framework 6 trở lên, có thể dùng connectAsync:

~~~java
StompSession session = stompClient.connectAsync(
    "ws://localhost:8080/ws",
    new StompSessionHandlerAdapter() {
        @Override
        public void afterConnected(
                StompSession session, StompHeaders connectedHeaders) {
            System.out.println("STOMP connected: " + session.getSessionId());
        }
    }
).get(5, TimeUnit.SECONDS);
~~~

connectAsync trả CompletableFuture<StompSession>. Future hoàn tất khi STOMP session sẵn sàng sử dụng, tức là sau khi client nhận frame CONNECTED từ broker/server. Dùng timeout cho get để test không treo vô hạn nếu server không kết nối được.

Các thành phần quan trọng:

- **StompSessionHandler:** nhận sự kiện vòng đời session, ERROR frame và lỗi transport.
- **StompSessionHandlerAdapter:** lớp adapter có sẵn các method mặc định, có thể override các callback cần theo dõi.
- **StompSession:** gửi message, tạo subscription, unsubscribe và disconnect.
- **StompFrameHandler:** nhận một STOMP frame và xác định kiểu payload.

StompSessionHandler cũng là một StompFrameHandler, vì vậy có thể xử lý ERROR frame. Hai callback lỗi cần phân biệt:

- handleException(...): lỗi trong khi xử lý STOMP frame, ví dụ không chuyển đổi được payload hoặc handler ném exception.
- handleTransportError(...): lỗi ở tầng transport, ví dụ I/O hoặc connection bị mất.

Không nên chỉ kiểm tra session.isConnected() rồi coi đó là bằng chứng broker xử lý được mọi message. Kết nối đang mở không đảm bảo destination hợp lệ, subscription đã được cài đặt hoặc broker còn hoạt động bình thường.

## 6. Subscribe và nhận payload với StompFrameHandler

session.subscribe(destination, handler) gửi STOMP SUBSCRIBE và trả về StompSession.Subscription. Subscription là handle để unsubscribe hoặc theo dõi receipt khi broker hỗ trợ.

Một handler cho DTO:

~~~java
StompFrameHandler frameHandler = new StompFrameHandler() {
    @Override
    public Type getPayloadType(StompHeaders headers) {
        return ChatMessage.class;
    }

    @Override
    public void handleFrame(StompHeaders headers, Object payload) {
        ChatMessage message = (ChatMessage) payload;
        // Chuyển kết quả sang queue/latch để test thread kiểm tra.
    }
};
~~~

Hai method có vai trò riêng:

1. getPayloadType(headers) được gọi trước để xác định kiểu Java mà MessageConverter cần tạo.
2. handleFrame(headers, payload) nhận headers và object đã chuyển đổi.

Có thể trả về String.class, byte[].class, một DTO hoặc một kiểu Type phù hợp. Nếu payload là JSON object, DTO cần tương thích với Jackson. Nếu payload có generic type như List<ChatMessage>, cần khai báo kiểu generic đầy đủ thay vì chỉ trả về List.class.

Callback handleFrame chạy trên thread xử lý message của client. Giữ callback ngắn: đưa payload vào BlockingQueue, hoàn tất CompletableFuture hoặc giảm CountDownLatch. Đừng đặt các assertion phức tạp hoặc công việc blocking trong callback; lỗi phát sinh ở callback có thể được chuyển tới handleException thay vì trực tiếp làm test method thất bại.

## 7. Đồng bộ subscription trước khi gửi message

Đây là một trong những nguồn gây test chập chờn.

Lệnh subscribe gửi frame SUBSCRIBE bất đồng bộ. Việc method subscribe trả về không tự chứng minh broker đã xử lý xong frame và lưu subscription. Nếu gửi ngay message có thể tạo race: server phát message trước khi subscription được đăng ký.

### 7.1. Dùng RECEIPT khi broker hỗ trợ

STOMP có frame RECEIPT. Client gửi header receipt trong frame SUBSCRIBE hoặc SEND; server/broker trả RECEIPT sau khi xử lý frame đó. StompSession.Receiptable cho phép đăng ký callback khi nhận receipt hoặc khi receipt hết hạn.

Ví dụ:

~~~java
StompHeaders subscribeHeaders = new StompHeaders();
subscribeHeaders.setDestination("/topic/replies");
subscribeHeaders.setReceipt("subscribe-ready");

StompSession.Subscription subscription =
    session.subscribe(subscribeHeaders, frameHandler);

CountDownLatch subscribed = new CountDownLatch(1);
AtomicReference<Throwable> receiptFailure = new AtomicReference<>();

subscription.addReceiptTask(subscribed::countDown);
subscription.addReceiptLostTask(() ->
    receiptFailure.set(new AssertionError("SUBSCRIBE receipt expired")));

assertTrue(subscribed.await(5, TimeUnit.SECONDS));
assertNull(receiptFailure.get());
~~~

Để theo dõi receipt, WebSocketStompClient phải được cấu hình TaskScheduler. Có thể dùng session.setAutoReceipt(true) để tự thêm receipt header cho các lệnh SEND và SUBSCRIBE tiếp theo; nếu muốn kiểm soát riêng từng lệnh, hãy thêm receipt header thủ công như ví dụ.

**Lưu ý:** broker trong bộ nhớ enableSimpleBroker của Spring không hỗ trợ RECEIPT. Đừng bật auto receipt rồi chờ mãi khi test đang dùng simple broker. Receipt-based synchronization phù hợp khi test chạy với broker relay hoặc broker STOMP có hỗ trợ RECEIPT.

Receipt xác nhận frame đã được xử lý theo ngữ nghĩa của broker/server. Nó không chứng minh một subscriber khác đã xử lý message nghiệp vụ hoặc đã commit dữ liệu.

### 7.2. Nếu dùng simple broker

Với simple broker, không dùng RECEIPT làm barrier. Có thể chọn một trong các cách sau:

- Thiết kế test fixture có tín hiệu readiness ở tầng ứng dụng và xác nhận tín hiệu đó trước khi publish.
- Theo dõi sự kiện subscription ở phía server trong test harness và phối hợp với trạng thái broker phù hợp.
- Nếu mục tiêu chỉ là kiểm tra controller method và annotation, dùng server-side test với clientInboundChannel.
- Dùng broker relay thật trong test cần xác minh receipt, ACK/NACK hoặc hành vi broker cụ thể.

Tránh giải quyết race bằng Thread.sleep(...). Sleep chỉ chờ một khoảng thời gian phỏng đoán; nó không chứng minh điều kiện mong muốn đã xảy ra.

## 8. Gửi message và đợi kết quả bất đồng bộ

Sau khi subscription đã sẵn sàng, gửi message:

~~~java
session.send("/app/echo", new ChatMessage("hello"));
~~~

Để nhận message, dùng BlockingQueue:

~~~java
BlockingQueue<ChatMessage> received = new LinkedBlockingQueue<>();

// Trong handleFrame:
received.offer((ChatMessage) payload);

// Trong test thread:
ChatMessage reply = received.poll(5, TimeUnit.SECONDS);

assertNotNull(reply, "No STOMP MESSAGE received before timeout");
assertEquals("HELLO", reply.text());
~~~

poll(timeout, unit) vừa chờ message vừa có giới hạn thời gian. Nếu không có message, test thất bại có lý do rõ ràng. Đây là cách ổn định hơn Thread.sleep rồi kiểm tra một biến có thể chưa được cập nhật.

Nếu cần xác nhận nhiều message, có thể dùng queue và lấy đủ số phần tử cần thiết. Nếu thứ tự quan trọng, so sánh sequence number hoặc nội dung theo thứ tự nhận. Nếu có thể nhận message cũ từ session trước, tạo destination riêng theo test ID hoặc kiểm tra correlation ID để tránh test khác làm nhiễu.

### 8.1. Correlation ID và message headers

Khi nhiều test cùng chạy, thêm một ID duy nhất vào payload hoặc custom STOMP header. Khi nhận response, chỉ xác nhận message có ID tương ứng.

Ví dụ:

~~~java
StompHeaders headers = new StompHeaders();
headers.setDestination("/app/echo");
headers.add("x-test-id", testId);

session.send(headers, new ChatMessage("hello"));
~~~

Không giả định mọi custom header đều được giữ nguyên qua broker hoặc được map vào DTO. Nếu header là dữ liệu nghiệp vụ, hãy xác định rõ nơi Spring đọc và truyền header.

## 9. Ví dụ E2E test với Spring Boot và JUnit

Ví dụ sau giả định ứng dụng đã cấu hình endpoint /ws, controller /app/echo và broker relay có hỗ trợ RECEIPT. Server chạy trên port ngẫu nhiên; test kết nối bằng WebSocketStompClient thật.

### 9.1. Dependency

Trong ứng dụng Spring Boot, cần có WebSocket starter và test starter. Version được quản lý bởi Spring Boot dependency management:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-websocket</artifactId>
</dependency>

<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Ứng dụng cũng cần dependency Jackson nếu test serialize DTO JSON. Nếu test dùng broker relay, broker STOMP phải được khởi động và cấu hình cho môi trường test.

### 9.2. Test class

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.lang.reflect.Type;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.messaging.converter.MappingJackson2MessageConverter;
import org.springframework.messaging.simp.stomp.StompCommand;
import org.springframework.messaging.simp.stomp.StompFrameHandler;
import org.springframework.messaging.simp.stomp.StompHeaders;
import org.springframework.messaging.simp.stomp.StompSession;
import org.springframework.messaging.simp.stomp.StompSessionHandlerAdapter;
import org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler;
import org.springframework.web.socket.client.standard.StandardWebSocketClient;
import org.springframework.web.socket.messaging.WebSocketStompClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class WebSocketStompClientE2ETest {

    @LocalServerPort
    int port;

    private ThreadPoolTaskScheduler scheduler;
    private WebSocketStompClient stompClient;
    private StompSession session;

    @BeforeEach
    void setUp() {
        scheduler = new ThreadPoolTaskScheduler();
        scheduler.setPoolSize(1);
        scheduler.setThreadNamePrefix("stomp-test-");
        scheduler.initialize();

        stompClient = new WebSocketStompClient(
            new StandardWebSocketClient()
        );
        stompClient.setMessageConverter(
            new MappingJackson2MessageConverter()
        );
        stompClient.setTaskScheduler(scheduler);
        stompClient.setReceiptTimeLimit(5_000);
        stompClient.start();
    }

    @AfterEach
    void tearDown() {
        if (session != null && session.isConnected()) {
            session.disconnect();
        }
        if (stompClient != null) {
            stompClient.stop();
        }
        if (scheduler != null) {
            scheduler.shutdown();
        }
    }

    @Test
    void sendToControllerAndReceiveTopicMessage() throws Exception {
        BlockingQueue<ChatMessage> received =
            new LinkedBlockingQueue<>();
        BlockingQueue<Throwable> clientErrors =
            new LinkedBlockingQueue<>();

        String url = "ws://localhost:" + port + "/ws";

        session = stompClient.connectAsync(
            url,
            new StompSessionHandlerAdapter() {
                @Override
                public void handleException(
                        StompSession session,
                        StompCommand command,
                        StompHeaders headers,
                        byte[] payload,
                        Throwable exception) {
                    clientErrors.offer(exception);
                }

                @Override
                public void handleTransportError(
                        StompSession session, Throwable exception) {
                    clientErrors.offer(exception);
                }
            }
        ).get(5, TimeUnit.SECONDS);

        StompFrameHandler frameHandler = new StompFrameHandler() {
            @Override
            public Type getPayloadType(StompHeaders headers) {
                return ChatMessage.class;
            }

            @Override
            public void handleFrame(
                    StompHeaders headers, Object payload) {
                received.offer((ChatMessage) payload);
            }
        };

        StompHeaders subscribeHeaders = new StompHeaders();
        subscribeHeaders.setDestination("/topic/replies");
        subscribeHeaders.setReceipt("subscribe-ready");

        CountDownLatch subscribed = new CountDownLatch(1);
        AtomicReference<Throwable> receiptFailure =
            new AtomicReference<>();

        StompSession.Subscription subscription =
            session.subscribe(subscribeHeaders, frameHandler);

        subscription.addReceiptTask(subscribed::countDown);
        subscription.addReceiptLostTask(() ->
            receiptFailure.set(
                new AssertionError("SUBSCRIBE receipt was not received")
            )
        );

        assertTrue(
            subscribed.await(5, TimeUnit.SECONDS),
            "Subscription was not acknowledged"
        );
        assertNull(receiptFailure.get());

        session.send(
            "/app/echo",
            new ChatMessage("hello")
        );

        ChatMessage reply = received.poll(5, TimeUnit.SECONDS);

        assertNotNull(reply, "No reply received");
        assertEquals("HELLO", reply.text());
        assertTrue(
            clientErrors.isEmpty(),
            () -> "Unexpected STOMP client error: " + clientErrors.peek()
        );

        subscription.unsubscribe();
    }
}
~~~

Test này thực hiện lần lượt:

1. Khởi động Spring application context với embedded server và port ngẫu nhiên.
2. Tạo WebSocketStompClient, Jackson converter và scheduler.
3. Kết nối tới endpoint và chờ STOMP CONNECTED.
4. Subscribe /topic/replies với StompFrameHandler.
5. Chờ RECEIPT để biết broker relay đã xử lý SUBSCRIBE.
6. Gửi ChatMessage tới /app/echo.
7. Đợi tối đa năm giây để nhận DTO phản hồi.
8. Kiểm tra nội dung và lỗi client.
9. Unsubscribe; @AfterEach disconnect session, stop client và shutdown scheduler.

Nếu dùng enableSimpleBroker thay cho broker relay, bỏ đoạn receipt và dùng cơ chế readiness phù hợp với test fixture. Simple broker không trả RECEIPT nên test ở trên cần broker hỗ trợ receipt.

Trong code test thực tế, hãy loại bỏ import không sử dụng, đặt DTO ở source/test package phù hợp và dùng đúng class package của ứng dụng. @LocalServerPort là port do Spring Boot cấp cho server RANDOM_PORT.

## 10. STOMP receipt, ACK/NACK và broker relay

### 10.1. Receipt xác nhận điều gì?

STOMP RECEIPT là phản hồi cho một frame mà client yêu cầu receipt. StompSession.setAutoReceipt(true) tự thêm receipt header cho các lệnh SEND và SUBSCRIBE tiếp theo. Có thể đăng ký callback qua Receiptable.addReceiptTask(...) và addReceiptLostTask(...).

Receipt hữu ích để:

- Xác nhận broker đã xử lý SUBSCRIBE trước khi test publish.
- Xác nhận broker đã xử lý một SEND frame theo ngữ nghĩa receipt.
- Phát hiện broker không trả receipt trong thời hạn quy định.

Receipt không phải application-level acknowledgement. Ví dụ, receipt của SEND không chứng minh một consumer đã xử lý business logic hoặc ghi dữ liệu vào database. Muốn xác nhận điều đó, cần một response/event hoặc trạng thái nghiệp vụ riêng.

### 10.2. ACK và NACK

STOMP có ACK/NACK để consumer xác nhận message đã được xử lý hoặc từ chối. Khi dùng, subscription phải đặt ack header là client hoặc client-individual; sau đó client dùng session.acknowledge(...) tương ứng.

Simple broker của Spring không hỗ trợ đầy đủ ACK/NACK. Nếu test cần xác nhận semantics của message acknowledgement, redelivery hoặc queue bền vững, hãy dùng broker thật và kiểm thử đúng loại broker đang triển khai.

### 10.3. Broker relay và simple broker

| Tiêu chí | Simple broker | Broker relay |
| --- | --- | --- |
| Mục tiêu | Khởi đầu, test luồng cơ bản, broker trong bộ nhớ | Kết nối broker STOMP chuyên dụng |
| Subscription | Lưu trong memory của ứng dụng | Được chuyển tiếp tới broker |
| Receipt / ACK | Không hỗ trợ đầy đủ; simple broker không hỗ trợ RECEIPT và ACK/NACK | Phụ thuộc tính năng của broker |
| Clustering / durability | Không phù hợp cho broker phân tán hoặc lưu bền | Dùng tính năng của broker chuyên dụng |
| Kiểm thử | Nhanh và ít phụ thuộc | Gần môi trường production hơn nhưng cần broker |

Không nên kết luận hệ thống production dùng RabbitMQ/ActiveMQ hoạt động đúng chỉ vì test với simple broker thành công. E2E test với simple broker kiểm tra tích hợp Spring endpoint/controller/broker trong bộ nhớ; test với broker relay kiểm tra thêm kết nối và semantics của broker ngoài.

## 11. Kiểm tra lỗi và transport

### 11.1. STOMP ERROR

Server có thể gửi frame ERROR khi nhận frame không hợp lệ, destination không được chấp nhận hoặc có lỗi xử lý theo chính sách server/broker. StompSessionHandler là StompFrameHandler, nên StompSessionHandlerAdapter có thể xử lý ERROR frame.

Khi test lỗi, cần kiểm tra:

- Frame ERROR có được gửi về client không.
- Error headers/body có chứa mã hoặc thông tin mong đợi không.
- Session còn sử dụng được hay server đã đóng session.
- Ứng dụng có làm lộ stack trace hoặc dữ liệu nhạy cảm trong payload lỗi không.

### 11.2. Lỗi trong callback và lỗi transport

handleException dành cho exception phát sinh khi xử lý STOMP frame, ví dụ converter không đọc được JSON hoặc handler ném lỗi. handleTransportError dành cho lỗi transport như I/O hoặc connection bị mất.

Đưa lỗi vào một BlockingQueue<Throwable> hoặc AtomicReference để test thread kiểm tra sau. Đừng nuốt lỗi trong callback. Nếu lỗi bị bỏ qua, test có thể timeout ở received.poll và báo sai nguyên nhân là server không gửi message.

### 11.3. Kết nối mất và reconnect

Khi transport mất, session hiện tại không còn đáng tin cậy. Reconnect thường tạo STOMP session mới; cần subscribe lại các destination và khôi phục trạng thái client cần thiết. Broker relay không tự reconnect mọi client session thay mặt ứng dụng.

Nếu kiểm thử reconnect, hãy xác minh rõ:

1. handleTransportError nhận lỗi.
2. Session cũ được xem là mất kết nối.
3. Client tạo kết nối mới và nhận CONNECTED.
4. Client tạo lại subscription.
5. Message sau reconnect được nhận đúng một lần theo yêu cầu nghiệp vụ.

Không tái sử dụng subscription handle từ session cũ.

## 12. Authentication, headers và SockJS

### 12.1. WebSocket handshake headers và STOMP CONNECT headers

connectAsync có overload nhận WebSocketHttpHeaders cho HTTP handshake và StompHeaders cho STOMP CONNECT. Đây là hai giai đoạn khác nhau:

- HTTP handshake headers được gửi khi nâng cấp kết nối WebSocket.
- STOMP CONNECT headers được gửi sau khi WebSocket đã mở.

Khi test xác thực, hãy đặt token/cookie vào đúng tầng mà server security đang kiểm tra. Không mặc định rằng header gửi trong STOMP CONNECT cũng xuất hiện ở HTTP handshake.

### 12.2. Destination và authorization

Kiểm thử cả trường hợp được phép và bị từ chối:

- Client chưa đăng nhập có được mở endpoint không?
- User có được SEND tới /app/... không?
- User có được SUBSCRIBE /topic/... hoặc /user/queue/... không?
- Message gửi tới user khác có bị chặn không?
- Server có kiểm tra quyền theo từng message, không chỉ ở handshake không?

Nên tạo session riêng với principal/credential riêng để tránh một session đã xác thực làm sai kết quả test session khác.

### 12.3. SockJS

Nếu endpoint đăng ký addEndpoint("/ws").withSockJS(), test cần dùng SockJS client phù hợp. Với WebSocket trực tiếp, dùng StandardWebSocketClient và URL ws://...; với SockJS, dùng SockJsClient và URL HTTP endpoint theo cách cấu hình SockJS. Hãy test fallback transport chỉ khi ứng dụng thật sự cần hỗ trợ fallback đó.

## 13. Chiến lược kiểm thử theo tầng

Không phải mọi trường hợp đều cần chạy server và broker thật.

| Loại test | Công cụ / setup | Nên kiểm tra |
| --- | --- | --- |
| Unit test service | JUnit, Mockito | Logic nghiệp vụ độc lập với STOMP. |
| Controller/message handler test | clientInboundChannel và Spring messaging infrastructure | Mapping annotation, argument conversion, validation, return destination. |
| WebSocket E2E với simple broker | Embedded server + WebSocketStompClient | Handshake, STOMP session, converter, routing và message delivery trong Spring. |
| WebSocket E2E với broker relay | Embedded server + broker thật + WebSocketStompClient | Kết nối broker, receipt, ACK/NACK và broker-specific behavior. |
| Browser/client compatibility | Browser hoặc client thật tương ứng | Cookie, CORS/origin, SockJS, browser behavior và reconnect. |
| Load/performance | Nhiều client và broker gần production | Throughput, latency, connection count, scheduler/heartbeat và broker capacity. |

Giữ E2E test tập trung vào các luồng quan trọng. Test controller/business logic bằng các test nhẹ hơn; chỉ dùng broker thật cho các tính năng phụ thuộc broker.

## 14. Lỗi thường gặp và cách xử lý

| Lỗi | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Test timeout ở connectAsync | URL/port sai, server chưa sẵn sàng, endpoint path sai hoặc STOMP CONNECT bị từ chối. | Dùng RANDOM_PORT, đúng endpoint và kiểm tra handleTransportError/ERROR. |
| Kết nối WebSocket được nhưng test không có session | WebSocket handshake đã xong nhưng STOMP CONNECTED chưa về. | Chờ Future connectAsync hoàn tất trước khi dùng session. |
| Payload nhận là String hoặc byte[] | getPayloadType hoặc MessageConverter không đúng. | Khai báo DTO.class và cấu hình converter tương ứng. |
| Không nhận message sau khi send | Destination sai, controller mapping sai, broker prefix sai hoặc subscribe chưa được xử lý. | Kiểm tra /app, /topic, @MessageMapping, @SendTo và đồng bộ subscription. |
| Test chập chờn do Thread.sleep | Sleep không xác nhận được broker đã đăng ký subscription. | Dùng RECEIPT nếu broker hỗ trợ hoặc readiness barrier ở tầng ứng dụng. |
| Receipt không bao giờ về | Simple broker không hỗ trợ RECEIPT hoặc broker không cấu hình tính năng đó. | Dùng broker relay hỗ trợ receipt hoặc bỏ receipt trong test simple broker. |
| Assertion ném lỗi trong handleFrame nhưng test không đỏ đúng cách | Callback chạy trên thread client và lỗi được chuyển qua callback exception. | Đưa payload vào queue/future rồi assert trên test thread. |
| Test treo khi server mất kết nối | Không đặt timeout cho Future, poll hoặc latch. | Dùng get/poll/await có timeout ở mọi điểm chờ bất đồng bộ. |
| Test khác nhận nhầm message | Destination dùng chung và test chạy song song. | Dùng correlation ID, destination riêng hoặc dọn subscription. |
| Client giữ thread sau test | Không stop client hoặc scheduler. | Disconnect, stop WebSocketStompClient và shutdown TaskScheduler trong finally/AfterEach. |
| Dùng simple broker để kiểm thử ACK/RECEIPT | Simple broker chỉ hỗ trợ subset STOMP. | Chạy broker thật khi cần kiểm tra tính năng đó. |
| Chỉ kiểm tra client.send không ném lỗi | Send thành công ở local API không chứng minh server xử lý đúng. | Đợi response/message hoặc application-level acknowledgement. |

## 15. Checklist cho một E2E test ổn định

Trước khi kết thúc test, xác nhận:

1. Server thực sự chạy bằng web environment hỗ trợ WebSocket, thường là RANDOM_PORT.
2. Client dùng đúng endpoint URL và transport.
3. connectAsync hoàn tất trước khi thao tác với session.
4. MessageConverter tương thích với DTO và content type.
5. Subscribe đúng destination và được đồng bộ trước khi gửi.
6. Mọi poll, await, get đều có timeout hữu hạn.
7. Callback chỉ chuyển dữ liệu/lỗi về test thread, không block.
8. Assertions kiểm tra nội dung, headers hoặc correlation ID thực sự cần thiết.
9. Receipt/ACK chỉ được dùng khi broker hỗ trợ.
10. Subscription được unsubscribe, session disconnect, client stop và scheduler shutdown.
11. Test độc lập khi chạy song song, không dùng destination/ID chung có thể nhận nhầm message.
12. Lỗi transport và STOMP ERROR được thu thập để failure message có ích.

## 16. Ghi nhớ

- WebSocketStompClient là STOMP client trên nền WebSocketClient, phù hợp cho E2E test với server thật.
- connectAsync hoàn tất khi STOMP session nhận CONNECTED; chỉ WebSocket handshake thành công là chưa đủ.
- MessageConverter serialize payload khi send và deserialize payload theo kiểu do StompFrameHandler.getPayloadType trả về.
- subscribe là bất đồng bộ; phải đồng bộ trạng thái subscription trước khi publish nếu thứ tự quan trọng.
- Dùng RECEIPT làm barrier chỉ khi broker hỗ trợ; Spring simple broker không hỗ trợ RECEIPT và ACK/NACK.
- Dùng BlockingQueue.poll hoặc CountDownLatch.await có timeout thay cho Thread.sleep.
- Thu thập lỗi qua handleException và handleTransportError.
- Dọn subscription, session, WebSocketStompClient và TaskScheduler để test không rò rỉ kết nối hoặc thread.
- E2E test với simple broker không thay thế test với broker thật khi production phụ thuộc broker-specific behavior.

## 17. Tài liệu tham khảo

- [Spring Framework Reference — Testing STOMP over WebSocket](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/testing.html): server-side tests và end-to-end integration tests.
- [Spring Framework Reference — STOMP Client](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/client.html): WebSocketStompClient, connect, send, subscribe, heartbeat và receipt.
- [Spring Framework Reference — STOMP](https://docs.spring.io/spring-framework/reference/web/websocket/stomp.html): destination routing, annotated controllers, simple broker và broker relay.
- [WebSocketStompClient Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/socket/messaging/WebSocketStompClient.html): API của client STOMP trên WebSocket.
- [StompSession Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/simp/stomp/StompSession.html): send, subscribe, receipts, acknowledgement và disconnect.
- [StompFrameHandler Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/simp/stomp/StompFrameHandler.html): khai báo payload type và xử lý frame.
- [STOMP 1.2 Specification](https://stomp.github.io/stomp-specification-1.2.html): CONNECT, CONNECTED, SEND, SUBSCRIBE, MESSAGE, RECEIPT, ACK, NACK và DISCONNECT.
