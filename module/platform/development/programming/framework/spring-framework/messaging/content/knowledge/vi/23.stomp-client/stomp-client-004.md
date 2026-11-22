# StompSession, StompHeaders và gửi thông điệp

Trong Spring Framework, Java STOMP client dùng WebSocketStompClient để thiết lập kết nối WebSocket và bắt tay STOMP. Sau khi server gửi frame CONNECTED, client làm việc với StompSession. Đối tượng này cung cấp các thao tác ở tầng STOMP như gửi SEND, đăng ký SUBSCRIBE, xác nhận ACK và ngắt kết nối.

StompHeaders mô tả các header của từng STOMP frame. Chúng cho biết destination, content type, receipt, acknowledgement mode và các metadata do ứng dụng định nghĩa. Khi gửi payload Java, message converter của client chuyển đối tượng thành byte/string phù hợp với giao thức.

Cần phân biệt ba kết quả: lời gọi send đã được client thực hiện, broker đã xác nhận frame bằng RECEIPT, và ứng dụng nhận đã xử lý nghiệp vụ. Chúng là các mốc khác nhau.

## 1. Vị trí của Java STOMP client trong luồng giao tiếp

Một client Java thường có các thành phần:

- **WebSocketStompClient** quản lý kết nối WebSocket và lớp STOMP phía client.
- **StompSessionHandler** nhận sự kiện vòng đời session, frame lỗi và lỗi transport.
- **StompSession** đại diện cho một phiên STOMP đã kết nối; client dùng nó để gửi message, subscribe và disconnect.
- **StompHeaders** chứa header của CONNECT, SEND, SUBSCRIBE, ACK hoặc các frame liên quan.
- **MessageConverter** chuyển payload giữa đối tượng Java và nội dung message trên đường truyền.
- **StompFrameHandler** khai báo kiểu payload mong đợi và xử lý từng frame MESSAGE nhận được.

Luồng kết nối và gửi message:

~~~mermaid
sequenceDiagram
    participant App as Java application
    participant Client as WebSocketStompClient
    participant Server as Spring STOMP server
    participant Broker as Message broker

    App->>Client: connectAsync(url, handler)
    Client->>Server: WebSocket handshake
    Client->>Server: STOMP CONNECT
    Server-->>Client: STOMP CONNECTED
    Client-->>App: afterConnected(StompSession)
    App->>Client: session.subscribe(...)
    Client->>Server: SUBSCRIBE
    App->>Client: session.send(...)
    Client->>Server: SEND + headers + payload
    Server->>Broker: Route application/broker message
    Broker-->>Server: MESSAGE khi có subscription phù hợp
    Server-->>Client: STOMP MESSAGE
    Client-->>App: StompFrameHandler.handleFrame(...)
~~~

StompSession chỉ sẵn sàng sau khi STOMP handshake hoàn tất. Có WebSocket connection chưa đồng nghĩa client đã nhận frame CONNECTED hoặc đã có một STOMP session có thể sử dụng.

## 2. Tạo WebSocketStompClient

Spring cung cấp WebSocketStompClient để kết hợp một WebSocket client implementation với STOMP protocol handler. Ví dụ dưới đây dùng StandardWebSocketClient và Jackson converter để gửi, nhận JSON.

~~~java
import org.springframework.messaging.converter.MappingJackson2MessageConverter;
import org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler;
import org.springframework.web.socket.client.standard.StandardWebSocketClient;
import org.springframework.web.socket.messaging.WebSocketStompClient;

public final class StompClientFactory {

    private StompClientFactory() {
    }

    public static WebSocketStompClient create() {
        WebSocketStompClient client =
            new WebSocketStompClient(new StandardWebSocketClient());

        client.setMessageConverter(new MappingJackson2MessageConverter());

        ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
        scheduler.setPoolSize(1);
        scheduler.setThreadNamePrefix("stomp-heartbeat-");
        scheduler.initialize();

        client.setTaskScheduler(scheduler);
        client.setDefaultHeartbeat(new long[] {10_000, 10_000});

        return client;
    }
}
~~~

Scheduler được dùng để chạy tác vụ heartbeat khi heartbeat được cấu hình. Trong ứng dụng Spring, nên quản lý scheduler bằng bean hoặc lifecycle của ứng dụng để nó được shutdown đúng lúc. Ví dụ dùng một scheduler riêng để làm rõ vai trò; không tạo một thread pool mới cho mỗi message.

StandardWebSocketClient cần một WebSocket implementation tương thích với Jakarta WebSocket trên classpath. Trong môi trường khác, có thể dùng WebSocket client implementation tương ứng, miễn là nó đáp ứng API mà Spring yêu cầu.

Message converter quyết định cách payload được serialize và deserialize:

- MappingJackson2MessageConverter: chuyển object Java và JSON.
- StringMessageConverter: chuyển nội dung text.
- ByteArrayMessageConverter: chuyển payload byte[].

Hai đầu giao tiếp cần thống nhất định dạng payload và content type. Nếu server gửi JSON nhưng client khai báo kiểu String hoặc một DTO không tương thích, việc chuyển đổi hoặc ép kiểu có thể thất bại.

## 3. Kết nối và nhận StompSession

connectAsync thực hiện kết nối bất đồng bộ và trả về CompletableFuture<StompSession>. Callback afterConnected được gọi sau khi client nhận STOMP CONNECTED.

~~~java
import java.lang.reflect.Type;
import java.util.UUID;
import java.util.concurrent.CompletableFuture;

import org.springframework.messaging.simp.stomp.StompFrameHandler;
import org.springframework.messaging.simp.stomp.StompHeaders;
import org.springframework.messaging.simp.stomp.StompSession;
import org.springframework.messaging.simp.stomp.StompSessionHandlerAdapter;
import org.springframework.util.MimeTypeUtils;
import org.springframework.web.socket.messaging.WebSocketStompClient;

public class OrderStompClient {

    private final WebSocketStompClient stompClient;

    public OrderStompClient(WebSocketStompClient stompClient) {
        this.stompClient = stompClient;
    }

    public CompletableFuture<StompSession> connect() {
        return stompClient.connectAsync(
            "ws://localhost:8080/ws",
            new StompSessionHandlerAdapter() {

                @Override
                public void afterConnected(
                        StompSession session,
                        StompHeaders connectedHeaders) {

                    System.out.println(
                        "STOMP connected, sessionId=" + session.getSessionId()
                    );

                    subscribeToOrderEvents(session);
                    sendCreateOrder(session);
                }

                @Override
                public void handleTransportError(
                        StompSession session,
                        Throwable exception) {

                    System.err.println(
                        "STOMP transport error: " + exception.getMessage()
                    );
                }
            }
        );
    }

    private void subscribeToOrderEvents(StompSession session) {
        session.subscribe(
            "/topic/order-events",
            new StompFrameHandler() {
                @Override
                public Type getPayloadType(StompHeaders headers) {
                    return OrderEvent.class;
                }

                @Override
                public void handleFrame(
                        StompHeaders headers,
                        Object payload) {

                    OrderEvent event = (OrderEvent) payload;
                    System.out.println("Received event: " + event);
                }
            }
        );
    }

    private void sendCreateOrder(StompSession session) {
        StompHeaders headers = new StompHeaders();
        headers.setDestination("/app/orders");
        headers.setContentType(MimeTypeUtils.APPLICATION_JSON);
        headers.set("x-correlation-id", UUID.randomUUID().toString());

        session.send(headers, new CreateOrder("ORD-100"));
    }

    public record CreateOrder(String orderId) {}

    public record OrderEvent(String eventId, String status) {}
}
~~~

Trong ví dụ:

1. Client mở kết nối đến endpoint /ws.
2. Server hoàn tất STOMP handshake và trả CONNECTED.
3. Spring gọi afterConnected với StompSession.
4. Client subscribe /topic/order-events.
5. Client gửi command đến /app/orders với JSON payload và correlation ID.
6. Các frame MESSAGE phù hợp được chuyển đến StompFrameHandler.

Chỉ gửi command sau khi session đã kết nối. Không gọi session.send trong lúc CompletableFuture chưa hoàn tất hoặc trước callback afterConnected. Nếu handshake thất bại, future có thể hoàn tất exceptionally; hãy xử lý lỗi đó ở nơi gọi connect.

## 4. Các thao tác chính của StompSession

StompSession là API làm việc với STOMP protocol sau khi kết nối. Những phương thức thường dùng:

| Phương thức | Mục đích |
|---|---|
| getSessionId() | Lấy ID của STOMP session |
| isConnected() | Kiểm tra trạng thái kết nối mà client đang theo dõi |
| send(destination, payload) | Gửi frame SEND đến destination |
| send(headers, payload) | Gửi SEND với header tùy chỉnh |
| subscribe(destination, handler) | Đăng ký nhận MESSAGE từ destination |
| subscribe(headers, handler) | Đăng ký với header SUBSCRIBE tùy chỉnh |
| unsubscribe(id) hoặc unsubscribe(headers) | Hủy subscription |
| acknowledge(messageId, consumed) | Gửi ACK/NACK theo acknowledgement mode được hỗ trợ |
| disconnect() | Ngắt STOMP session một cách có chủ đích |

send và subscribe là các thao tác bất đồng bộ theo luồng messaging. Việc phương thức trả về không có nghĩa callback nhận message đã chạy hoặc nghiệp vụ phía server/client đã hoàn tất.

isConnected() phản ánh trạng thái mà client biết tại thời điểm kiểm tra. Một kết nối có thể bị đứt ngay sau lần kiểm tra, vì vậy vẫn cần xử lý transport error và reconnect.

## 5. Gửi message bằng send

Cách đơn giản nhất là cung cấp destination và payload:

~~~java
session.send("/app/orders", new CreateOrder("ORD-100"));
~~~

Spring sử dụng message converter đã cấu hình để chuyển CreateOrder thành payload trên frame STOMP SEND. Server thường định tuyến destination có application prefix /app đến @MessageMapping tương ứng.

Nếu cần kiểm soát header, dùng overload nhận StompHeaders:

~~~java
StompHeaders headers = new StompHeaders();
headers.setDestination("/app/orders");
headers.setContentType(MimeTypeUtils.APPLICATION_JSON);
headers.set("x-correlation-id", "corr-2026-001");
headers.set("x-client-version", "1.4.0");

session.send(headers, new CreateOrder("ORD-101"));
~~~

Các trường có ý nghĩa:

- **destination:** đích của frame SEND; đây là header bắt buộc trong trường hợp gửi message đến destination.
- **content-type:** mô tả định dạng payload, ví dụ application/json.
- **x-correlation-id:** header do ứng dụng định nghĩa để nối log hoặc truy vết một yêu cầu.
- **x-client-version:** metadata phục vụ quan sát hoặc tương thích phiên bản nếu server có nhu cầu.

Header tùy chỉnh phải là dữ liệu dạng chuỗi theo STOMP. Server có thể đọc header bằng @Header hoặc MessageHeaders, nhưng cần xác thực và kiểm tra giá trị đầu vào.

Mỗi frame nên có một StompHeaders riêng. Không chia sẻ một instance mutable giữa nhiều luồng gửi đồng thời; điều đó có thể làm header của message này lẫn sang message khác.

## 6. StompHeaders và phạm vi của header

StompHeaders là collection các header của STOMP frame. Nó có những accessor thuận tiện cho header giao thức như destination, content type, receipt, subscription và acknowledgement, đồng thời cho phép thêm header tùy chỉnh.

Một số header thường gặp:

| Header | Frame thường dùng | Ý nghĩa |
|---|---|---|
| destination | SEND, SUBSCRIBE | Đích gửi hoặc destination đăng ký |
| content-type | SEND, MESSAGE | Kiểu nội dung của payload |
| receipt | SEND, SUBSCRIBE, UNSUBSCRIBE | Yêu cầu broker trả RECEIPT cho frame |
| id | SUBSCRIBE, UNSUBSCRIBE | Định danh subscription |
| ack | SUBSCRIBE | Chế độ acknowledgement |
| message-id | MESSAGE | Định danh message do broker cung cấp trong ngữ cảnh hỗ trợ |
| subscription | MESSAGE | Subscription nhận message |
| x-correlation-id | Do ứng dụng quy định | Theo dõi request/event xuyên các thành phần |

Ví dụ đọc header từ frame nhận:

~~~java
@Override
public void handleFrame(StompHeaders headers, Object payload) {
    String contentType = headers.getContentType() == null
        ? null
        : headers.getContentType().toString();

    String messageId = headers.getFirst("message-id");
    String correlationId = headers.getFirst("x-correlation-id");

    System.out.println("content-type=" + contentType);
    System.out.println("message-id=" + messageId);
    System.out.println("correlation-id=" + correlationId);
}
~~~

Không phải frame nào cũng có tất cả header trong bảng. Ví dụ message-id và subscription thường do broker thêm vào MESSAGE; chúng không phải giá trị mà client tùy ý gán cho một frame SEND để quyết định định tuyến.

Cần phân biệt StompHeaders với HTTP handshake headers. HTTP header được gửi trong quá trình mở kết nối WebSocket; STOMP header nằm trong frame CONNECT, SEND, SUBSCRIBE hoặc MESSAGE sau khi WebSocket đã mở. Nếu cần gửi Authorization trong HTTP handshake, dùng cơ chế WebSocket handshake headers phù hợp. Nếu ứng dụng đặt token trong STOMP CONNECT header, server phải chủ động xác thực token qua channel interceptor; Spring không tự coi mọi custom header là danh tính đã xác thực.

## 7. Subscribe và chuyển payload về đúng kiểu Java

Client đăng ký nhận message bằng destination logic:

~~~java
session.subscribe(
    "/topic/order-events",
    new StompFrameHandler() {
        @Override
        public Type getPayloadType(StompHeaders headers) {
            return OrderEvent.class;
        }

        @Override
        public void handleFrame(StompHeaders headers, Object payload) {
            OrderEvent event = (OrderEvent) payload;
            process(event);
        }
    }
);
~~~

getPayloadType cho message converter biết kiểu đích cần tạo. Nếu payload là JSON biểu diễn OrderEvent, MappingJackson2MessageConverter sẽ cố gắng tạo object OrderEvent. Kiểu này phải khớp schema mà server phát ra.

Nếu muốn nhận nội dung thô để tự xử lý, có thể khai báo byte[]. Cách này hữu ích khi cần kiểm tra encoding hoặc định dạng đặc biệt, nhưng khi dùng DTO sẽ thuận tiện hơn cho ứng dụng thông thường.

SUBSCRIBE là một thao tác độc lập với SEND. Client cần subscribe đúng destination trước khi kỳ vọng nhận message. Với topic không lưu trữ, message được phát trước khi subscription hoạt động có thể bị bỏ lỡ.

## 8. Receipt: broker đã xử lý frame đến đâu?

STOMP hỗ trợ header receipt để client yêu cầu broker gửi frame RECEIPT khi frame tương ứng được xử lý theo hợp đồng của broker.

Có thể yêu cầu receipt cho một frame cụ thể bằng StompHeaders:

~~~java
StompHeaders headers = new StompHeaders();
headers.setDestination("/app/orders");
headers.setReceipt("receipt-order-100");

StompSession.Receiptable receipt =
    session.send(headers, new CreateOrder("ORD-100"));

receipt.addReceiptTask(() ->
    System.out.println("Broker returned RECEIPT")
);

receipt.addReceiptLostTask(() ->
    System.err.println("Receipt was not received in time")
);
~~~

Có thể bật auto receipt trên session để tự yêu cầu receipt cho các thao tác phù hợp:

~~~java
session.setAutoReceipt(true);
~~~

Receiptable cho phép đăng ký callback khi receipt đến hoặc khi hết thời gian chờ. Cấu hình thời hạn chờ receipt ở STOMP client để việc mất receipt có thể được phát hiện và xử lý.

Receipt của SEND cho biết broker đã xử lý frame SEND theo hợp đồng của broker. Nó không chứng minh mọi subscriber đã nhận MESSAGE, cũng không chứng minh client nhận đã lưu dữ liệu hoặc hoàn tất side effect.

Spring Simple Broker không cung cấp đầy đủ các tính năng STOMP nâng cao như receipt và acknowledgement. Khi cần dựa vào RECEIPT, hãy kiểm tra broker relay và broker bên ngoài thực sự hỗ trợ tính năng đó. Nếu broker không hỗ trợ hoặc đường truyền bị gián đoạn, callback receipt-lost có thể được gọi.

## 9. ACK và NACK khi subscription yêu cầu acknowledgement

Một subscription có thể dùng acknowledgement mode do broker hỗ trợ. Trong STOMP, các chế độ phổ biến gồm auto, client và client-individual. Khi dùng chế độ client hoặc client-individual, client có thể ACK sau khi xử lý MESSAGE hoặc NACK khi không thể xử lý.

Ví dụ về ý tưởng ACK:

~~~java
StompHeaders subscribeHeaders = new StompHeaders();
subscribeHeaders.setDestination("/queue/jobs");
subscribeHeaders.setAck("client-individual");

session.subscribe(subscribeHeaders, new StompFrameHandler() {
    @Override
    public Type getPayloadType(StompHeaders headers) {
        return Job.class;
    }

    @Override
    public void handleFrame(StompHeaders headers, Object payload) {
        Job job = (Job) payload;
        process(job);

        String messageId = headers.getFirst("message-id");
        if (messageId != null) {
            session.acknowledge(messageId, true);
        }
    }
});
~~~

Đoạn trên minh họa luồng xử lý; chỉ dùng khi broker và destination thực sự hỗ trợ acknowledgement mode đó. ACK phải được gửi sau khi bước xử lý mà ứng dụng muốn xác nhận đã hoàn thành. Nếu process ném exception, không nên ACK như thể tác vụ đã thành công.

ACK STOMP là xác nhận ở tầng giao thức/broker. Nó không thay thế ACK nghiệp vụ giữa hai ứng dụng và không tự động tạo exactly-once processing. Khi retry có thể giao lại message, consumer vẫn cần idempotency để tránh thực hiện side effect nhiều lần.

## 10. Xử lý lỗi và vòng đời kết nối

Các lỗi có thể xảy ra ở nhiều giai đoạn:

- **WebSocket handshake:** URL sai, server không khả dụng, TLS hoặc HTTP authentication thất bại.
- **STOMP CONNECT:** server từ chối kết nối, phiên bản giao thức hoặc thông tin xác thực không hợp lệ.
- **Message conversion:** payload không thể serialize/deserialize hoặc content type không phù hợp.
- **SEND/SUBSCRIBE:** destination không được phép, header không hợp lệ hoặc broker từ chối.
- **Transport:** socket bị đóng, timeout hoặc mạng mất kết nối.
- **Application callback:** code trong handleFrame ném exception hoặc xử lý nghiệp vụ thất bại.

StompSessionHandlerAdapter cho phép ghi nhận các callback quan trọng như afterConnected, handleTransportError và handleException. Nên log session ID, destination, correlation ID và loại lỗi; tránh ghi token hoặc payload nhạy cảm.

Khi reconnect:

1. Đánh dấu session cũ là không còn sử dụng khi transport bị lỗi.
2. Áp dụng retry có giới hạn và backoff, tránh reconnect liên tục gây tải cho server.
3. Tạo kết nối STOMP mới và chờ CONNECTED.
4. Subscribe lại các destination cần thiết trong afterConnected.
5. Đồng bộ dữ liệu hoặc event đã bỏ lỡ từ nguồn lưu trữ bền vững.
6. Gửi lại command chỉ khi có idempotency key hoặc cơ chế xác định command trước đó đã được xử lý hay chưa.

WebSocketStompClient cung cấp API kết nối, nhưng ứng dụng vẫn phải thiết kế chính sách reconnect và khôi phục subscription theo yêu cầu nghiệp vụ. Một StompSession đã lỗi không nên được dùng như thể nó tự phục hồi.

Khi kết thúc phiên có chủ đích, gọi session.disconnect(). Ứng dụng cũng cần quản lý lifecycle của WebSocketStompClient và TaskScheduler để giải phóng tài nguyên khi shutdown.

## 11. Bảo mật khi gửi header và message

STOMP header là dữ liệu đầu vào. Client có thể tự đặt x-correlation-id, x-client-version hoặc các giá trị tùy chỉnh; server không được mặc định tin cậy chúng.

- Lấy danh tính người dùng từ Principal đã được xác thực, không từ username trong payload.
- Kiểm tra quyền gửi đến từng destination /app và quyền subscribe /topic hoặc /queue.
- Nếu dùng JWT trong STOMP CONNECT header, xác thực token trong ChannelInterceptor trước khi xử lý message và gắn Principal hợp lệ cho session.
- Không gửi mật khẩu broker hoặc secret nội bộ cho browser client.
- Không dùng custom header để bỏ qua kiểm tra authorization.
- Giới hạn kích thước payload và kiểm tra dữ liệu trước khi xử lý.
- Không log access token, cookie, passcode hoặc dữ liệu cá nhân không cần thiết.

Nếu broker relay yêu cầu login/passcode để kết nối broker, đó là thông tin kết nối giữa server và broker. Không nhầm credentials này với thông tin đăng nhập của người dùng cuối.

## 12. Kiểm thử Java STOMP client

Một integration test có giá trị nên kiểm tra cả kết nối, gửi và nhận message:

- Client connect thành công và callback afterConnected được gọi.
- Client subscribe đúng destination và nhận DTO đúng kiểu.
- SEND dùng đúng destination, content type và custom header.
- Server từ chối destination không được cấp quyền.
- Payload sai schema tạo lỗi conversion có thể quan sát.
- Broker có hỗ trợ receipt thì receipt callback chạy; khi không có receipt, timeout được xử lý.
- Nếu dùng ACK mode, kiểm tra ACK sau xử lý và hành vi khi consumer lỗi.
- Ngắt kết nối rồi reconnect; client subscribe lại và đồng bộ trạng thái theo hợp đồng.
- Gửi lại cùng command ID không tạo tác động nghiệp vụ trùng.

Tránh dùng Thread.sleep cố định để đợi message. Dùng CompletableFuture, CountDownLatch hoặc cơ chế chờ có timeout để test kết thúc khi điều kiện mong đợi xảy ra. Một test trên Simple Broker không chứng minh broker relay hoặc receipt/ACK của broker bên ngoài hoạt động.

## 13. Checklist khi gửi không thành công

- CompletableFuture kết nối đã hoàn tất và afterConnected đã được gọi chưa?
- StompSession còn kết nối theo trạng thái client không?
- Destination SEND có đúng application prefix /app hay broker prefix /topic, /queue không?
- Payload converter và content-type có khớp schema ở server không?
- StompHeaders có destination bắt buộc và các custom header hợp lệ không?
- Client đã subscribe đúng destination trước thời điểm server publish chưa?
- Có frame ERROR, transport error hoặc lỗi conversion nào không?
- Broker có hỗ trợ receipt/ACK mà ứng dụng đang trông đợi không?
- Nếu reconnect, client đã subscribe lại và đồng bộ message bị bỏ lỡ chưa?
- Server có xác thực Principal và kiểm tra quyền trên destination không?

StompSession cung cấp API thao tác với một phiên STOMP; StompHeaders mô tả metadata trên từng frame; message converter xử lý payload Java. Khi gửi message, hãy kiểm tra riêng kết nối, destination, serialization, broker receipt và xác nhận nghiệp vụ để biết chính xác hệ thống đã hoàn tất đến mốc nào.