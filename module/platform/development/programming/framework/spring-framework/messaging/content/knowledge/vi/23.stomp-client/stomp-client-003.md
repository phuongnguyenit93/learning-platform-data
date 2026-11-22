# StompSessionHandler và vòng đời kết nối STOMP

## 1. Vai trò của StompSessionHandler

Spring Framework cung cấp STOMP client để ứng dụng Java kết nối tới server qua WebSocket hoặc TCP. Với transport WebSocket, lớp trung tâm là \`WebSocketStompClient\`. Khi kết nối, ứng dụng truyền một \`StompSessionHandler\` để nhận thông báo về trạng thái phiên STOMP và các lỗi xảy ra trong quá trình giao tiếp.

\`StompSessionHandler\` là hợp đồng phía client, thuộc package \`org.springframework.messaging.simp.stomp\`. Nó mở rộng \`StompFrameHandler\`, vì vậy ngoài các callback vòng đời, handler còn có thể nhận frame STOMP \`ERROR\` do broker gửi về. Handler không phải là controller phía server và cũng không tự quản lý vòng đời của toàn bộ \`WebSocketStompClient\`.

Trong ứng dụng thực tế, thường kế thừa \`StompSessionHandlerAdapter\` thay vì tự triển khai interface. Adapter cung cấp các phương thức mặc định rỗng, giúp chỉ cần override những callback có ý nghĩa đối với ứng dụng.

## 2. Các callback và hợp đồng API

| Phương thức | Thời điểm được gọi | Trách nhiệm thường gặp |
| --- | --- | --- |
| \`afterConnected(session, connectedHeaders)\` | Sau khi transport đã kết nối và client nhận frame STOMP \`CONNECTED\` | Lưu phiên hiện tại, đăng ký subscription, khởi tạo trạng thái ứng dụng |
| \`getPayloadType(headers)\` | Khi cần xác định kiểu Java cho payload của frame mà handler nhận | Chọn kiểu đích để MessageConverter giải mã payload |
| \`handleFrame(headers, payload)\` | Khi nhận frame được chuyển cho handler; với session handler thường dùng để xử lý STOMP \`ERROR\` | Ghi nhận lỗi do broker gửi và phân tích headers/payload |
| \`handleException(session, command, headers, payload, exception)\` | Khi có lỗi trong quá trình xử lý frame, ví dụ giải mã payload hoặc exception thoát ra từ StompFrameHandler của subscription | Ghi log, phát cảnh báo, đánh dấu lỗi xử lý message |
| \`handleTransportError(session, exception)\` | Khi có lỗi tầng transport, như lỗi I/O, encode/decode hoặc mất kết nối | Đánh dấu phiên mất kết nối và kích hoạt quy trình phục hồi |

Các callback trên có phạm vi khác nhau. Phân biệt chúng giúp tránh xử lý một lỗi broker như lỗi mạng hoặc bỏ sót lỗi giải mã message.

### 2.1. afterConnected

\`afterConnected\` chỉ chạy khi phiên STOMP đã sẵn sàng: WebSocket hoặc TCP transport đã kết nối và broker đã trả frame \`CONNECTED\` cho frame \`CONNECT\` của client. Việc bắt tay WebSocket thành công mới chỉ xác nhận tầng transport; nó chưa chứng minh STOMP session đã được thiết lập.

Tham số:

- \`session\`: đối tượng \`StompSession\` đại diện cho phiên STOMP vừa được thiết lập.
- \`connectedHeaders\`: headers trong frame \`CONNECTED\`, có thể chứa phiên bản STOMP và thông tin heartbeat được thương lượng.

Đây là nơi phù hợp để đăng ký các destination cần thiết. Khi server xác nhận kết nối, client có thể bắt đầu gửi lệnh và nhận message. Nếu ứng dụng cần biết subscription đã được broker xử lý, hãy yêu cầu STOMP receipt và chờ callback receipt; việc gọi \`subscribe\` chỉ gửi frame đăng ký.

### 2.2. getPayloadType và handleFrame

\`StompSessionHandler\` kế thừa \`StompFrameHandler\`, gồm hai phương thức:

\`\`\`java
Type getPayloadType(StompHeaders headers);

void handleFrame(StompHeaders headers, Object payload);
\`\`\`

\`getPayloadType\` cho biết kiểu Java mong muốn của payload để Spring MessageConverter chuyển đổi dữ liệu. Ví dụ, nếu broker gửi JSON đại diện cho \`Notification\`, trả về \`Notification.class\`.

\`handleFrame\` nhận headers và payload đã được chuyển đổi. Với handler gắn ở cấp session, hai phương thức này chủ yếu phục vụ việc xử lý frame \`ERROR\` do broker gửi. Mỗi subscription được tạo bằng \`session.subscribe(...)\` có thể có \`StompFrameHandler\` riêng để xử lý các frame \`MESSAGE\` của destination đó.

\`StompSessionHandlerAdapter\` mặc định khai báo kiểu payload của frame lỗi là \`String\` và để \`handleFrame\` rỗng. Vì thế, nếu muốn nhìn thấy nội dung lỗi từ broker, cần override \`handleFrame\`. Nếu không override, frame lỗi có thể được nhận nhưng ứng dụng không ghi nhận nội dung của nó.

### 2.3. handleException

Callback này xử lý exception phát sinh trong quá trình xử lý frame STOMP, ví dụ:

- MessageConverter không thể chuyển payload thành kiểu Java mà \`getPayloadType\` yêu cầu.
- Một \`StompFrameHandler.handleFrame\` của subscription ném exception không được xử lý bên trong handler.
- Logic xử lý message gặp lỗi khi đọc dữ liệu hoặc chuyển đổi kiểu.

Tham số gồm session, STOMP command liên quan nếu có, headers, payload thô dạng \`byte[]\` và exception. Payload thô hữu ích khi chẩn đoán lỗi chuyển đổi, nhưng có thể chứa dữ liệu cá nhân hoặc bí mật; chỉ ghi log khi đã áp dụng chính sách lọc dữ liệu.

### 2.4. handleTransportError

Callback này dành cho lỗi tầng transport, chẳng hạn I/O, lỗi mã hóa/giải mã STOMP hoặc kết nối bị mất. Khi kết nối bị mất thay vì được đóng bình thường bằng \`StompSession.disconnect()\`, Spring chuyển \`ConnectionLostException\` vào callback này.

Không nên xem mọi lỗi ứng dụng là lỗi transport. Ví dụ, broker gửi frame \`ERROR\` là lỗi ở giao thức/ứng dụng; payload JSON sai kiểu là lỗi xử lý frame; socket bị reset là lỗi transport. Mỗi loại cần chiến lược khắc phục khác nhau.

### 2.5. StompSessionHandlerAdapter

Adapter triển khai sẵn các phương thức của \`StompSessionHandler\` và \`StompFrameHandler\`:

- \`afterConnected\`, \`handleException\`, \`handleTransportError\` và \`handleFrame\` mặc định không làm gì.
- \`getPayloadType\` mặc định trả về \`String.class\`, kiểu payload dự kiến cho STOMP ERROR frame.

Do đó, kế thừa adapter không có nghĩa là lỗi đã được xử lý tự động. Ứng dụng phải override callback phù hợp để ghi nhận hoặc phản ứng với lỗi.

## 3. Vòng đời của một phiên STOMP

Một phiên STOMP có thể được nhìn theo chuỗi trạng thái sau:

\`\`\`mermaid
sequenceDiagram
    participant App as Ứng dụng Java
    participant Client as WebSocketStompClient
    participant Server as WebSocket / STOMP Server
    participant Handler as StompSessionHandler

    App->>Client: connectAsync(url, handler)
    Client->>Server: WebSocket handshake
    Server-->>Client: WebSocket established
    Client->>Server: STOMP CONNECT
    Server-->>Client: STOMP CONNECTED
    Client->>Handler: afterConnected(session, headers)
    Handler->>Server: SUBSCRIBE destinations
    Server-->>Handler: MESSAGE frames
    Handler->>App: cập nhật trạng thái / xử lý payload
    Note over Client,Server: Gửi và nhận message trong phiên
    App->>Client: session.disconnect()
    Client->>Server: STOMP DISCONNECT
    Client->>Server: đóng transport
\`\`\`

Các bước chính:

1. **Tạo client và cấu hình transport.** Chọn \`StandardWebSocketClient\` cho WebSocket tiêu chuẩn hoặc \`SockJsClient\` khi cần cơ chế fallback của SockJS.
2. **Mở kết nối transport.** Client thực hiện HTTP Upgrade/WebSocket handshake hoặc kết nối TCP, tùy loại client.
3. **Gửi STOMP CONNECT.** Sau khi transport sẵn sàng, client gửi frame \`CONNECT\` hoặc \`STOMP\` cùng các headers cần thiết.
4. **Nhận STOMP CONNECTED.** Server/broker xác nhận phiên STOMP và có thể thương lượng phiên bản giao thức, heartbeat.
5. **Gọi afterConnected.** Handler nhận \`StompSession\` có thể sử dụng. Đây là mốc bắt đầu gửi lệnh, đăng ký destination và thiết lập các callback.
6. **Trao đổi message.** Client gửi bằng \`session.send\`, đăng ký bằng \`session.subscribe\`, nhận frame qua các \`StompFrameHandler\`.
7. **Đóng phiên hoặc gặp lỗi.** Ứng dụng có thể gọi \`session.disconnect()\`; nếu transport mất kết nối, handler nhận lỗi transport.
8. **Kết nối lại khi cần.** Client phải thực hiện chiến lược reconnect của ứng dụng. Phiên mới có session ID mới và cần tạo lại các subscription.

Một WebSocket có thể vẫn đang mở trong khi STOMP CONNECT chưa thành công. Vì vậy, không đặt trạng thái ứng dụng là “đã kết nối” chỉ dựa trên callback hoặc log của tầng WebSocket.

## 4. Cấu hình WebSocketStompClient

Ví dụ cấu hình client với Jackson converter và scheduler phục vụ heartbeat/receipt:

\`\`\`java
import org.springframework.messaging.converter.MappingJackson2MessageConverter;
import org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler;
import org.springframework.web.socket.client.standard.StandardWebSocketClient;
import org.springframework.web.socket.messaging.WebSocketStompClient;

public final class StompClientFactory {

    private StompClientFactory() {
    }

    public static WebSocketStompClient createClient(
            ThreadPoolTaskScheduler scheduler) {

        var webSocketClient = new StandardWebSocketClient();
        var stompClient = new WebSocketStompClient(webSocketClient);

        stompClient.setMessageConverter(
                new MappingJackson2MessageConverter());
        stompClient.setTaskScheduler(scheduler);
        stompClient.setReceiptTimeLimit(15_000);

        return stompClient;
    }
}
\`\`\`

Khởi tạo scheduler khi tạo ứng dụng:

\`\`\`java
import org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler;

ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
scheduler.setPoolSize(1);
scheduler.setThreadNamePrefix("stomp-scheduler-");
scheduler.initialize();
\`\`\`

Trong ứng dụng Spring, nên khai báo scheduler và client thành bean để Spring quản lý vòng đời của chúng. Nếu tự tạo bằng Java như ví dụ, ứng dụng phải đóng scheduler khi kết thúc để giải phóng thread. \`WebSocketStompClient\` triển khai \`SmartLifecycle\`; với bean do Spring quản lý, vòng đời start/stop có thể được điều phối cùng ApplicationContext.

Các điểm cấu hình cần hiểu:

- **WebSocketClient:** chọn transport. \`StandardWebSocketClient\` dùng WebSocket tiêu chuẩn; \`SockJsClient\` có thể dùng WebSocket hoặc transport HTTP fallback.
- **MessageConverter:** quyết định cách serialize payload gửi đi và deserialize payload nhận về. JSON DTO cần converter JSON phù hợp; chuỗi thuần có thể dùng \`StringMessageConverter\`.
- **TaskScheduler:** hỗ trợ tác vụ heartbeat và theo dõi thời hạn receipt. Không cấu hình scheduler thì không thể dựa vào cơ chế lập lịch của client cho các tính năng đó.
- **Receipt time limit:** khoảng thời gian client chờ receipt trước khi xem receipt bị mất. Giá trị mặc định là 15 giây; chỉ tùy chỉnh khi có cơ sở từ độ trễ và đặc tính broker.
- **Message size:** inbound message mặc định giới hạn 64 KB. Có thể dùng \`setInboundMessageSizeLimit\` và \`setOutboundMessageSizeLimit\` để đặt giới hạn phù hợp. Message STOMP outbound lớn có thể được chia thành partial WebSocket messages; bên nhận phải ghép lại. Inbound vượt giới hạn sẽ gây \`StompConversionException\`.

Cấu hình converter phải thống nhất với hợp đồng payload của server. Nếu server gửi JSON nhưng client dùng converter chỉ đọc chuỗi, hoặc hai phía khác kiểu dữ liệu, lỗi chuyển đổi có thể được chuyển tới \`handleException\`.

## 5. Kết nối và nhận StompSession

Từ Spring Framework 6.0, có thể dùng \`connectAsync\`, trả về \`CompletableFuture<StompSession>\`. Future hoàn thành khi kết nối STOMP đã sẵn sàng, sau khi nhận frame \`CONNECTED\`.

\`\`\`java
import java.util.concurrent.CompletableFuture;

import org.springframework.messaging.simp.stomp.StompSession;
import org.springframework.web.socket.messaging.WebSocketStompClient;

public final class StompConnector {

    private final WebSocketStompClient client;

    public StompConnector(WebSocketStompClient client) {
        this.client = client;
    }

    public CompletableFuture<StompSession> connect(
            String url,
            NotificationSessionHandler handler) {

        return client.connectAsync(url, handler);
    }
}
\`\`\`

Có thể quan sát kết quả kết nối bằng future:

\`\`\`java
connector.connect(url, handler)
        .whenComplete((session, error) -> {
            if (error != null) {
                System.err.println("STOMP connect failed: " + error);
                return;
            }

            System.out.println(
                    "STOMP session ready: " + session.getSessionId());
        });
\`\`\`

Nên chọn một nơi chịu trách nhiệm đăng ký subscription. Nếu \`afterConnected\` đã đăng ký subscription, callback \`whenComplete\` chỉ nên ghi nhận kết quả hoặc cập nhật trạng thái giao diện. Đăng ký cùng destination ở cả hai nơi sẽ tạo subscription trùng lặp.

Các overload của \`connectAsync\` còn cho phép truyền headers của WebSocket handshake và headers của STOMP CONNECT. Hai loại headers thuộc hai giai đoạn khác nhau:

- \`WebSocketHttpHeaders\` áp dụng cho HTTP handshake, ví dụ cookie hoặc header xác thực HTTP được server cho phép.
- \`StompHeaders\` áp dụng cho frame STOMP CONNECT, ví dụ login/passcode nếu broker sử dụng cơ chế xác thực STOMP.

Không đặt thông tin xác thực vào query string hoặc log. Chỉ gửi credentials qua transport được bảo vệ bằng TLS (\`wss://\`) và theo đúng cơ chế xác thực của server/broker.

## 6. Ví dụ handler quản lý subscription và lỗi

Giả sử broker gửi thông báo JSON có cấu trúc:

\`\`\`java
public record Notification(
        String id,
        String title,
        String message
) {
}
\`\`\`

Handler:

\`\`\`java
import java.lang.reflect.Type;
import java.util.function.Consumer;

import org.springframework.messaging.simp.stomp.StompCommand;
import org.springframework.messaging.simp.stomp.StompFrameHandler;
import org.springframework.messaging.simp.stomp.StompHeaders;
import org.springframework.messaging.simp.stomp.StompSession;
import org.springframework.messaging.simp.stomp.StompSessionHandlerAdapter;

public final class NotificationSessionHandler
        extends StompSessionHandlerAdapter {

    private static final System.Logger LOG =
            System.getLogger(NotificationSessionHandler.class.getName());

    private final Consumer<Notification> notificationConsumer;

    private volatile StompSession.Subscription subscription;

    public NotificationSessionHandler(
            Consumer<Notification> notificationConsumer) {
        this.notificationConsumer = notificationConsumer;
    }

    @Override
    public void afterConnected(
            StompSession session,
            StompHeaders connectedHeaders) {

        LOG.log(System.Logger.Level.INFO,
                "STOMP connected: sessionId={0}",
                session.getSessionId());

        session.setAutoReceipt(true);

        this.subscription = session.subscribe(
                "/topic/notifications",
                new StompFrameHandler() {
                    @Override
                    public Type getPayloadType(StompHeaders headers) {
                        return Notification.class;
                    }

                    @Override
                    public void handleFrame(
                            StompHeaders headers,
                            Object payload) {
                        notificationConsumer.accept(
                                (Notification) payload);
                    }
                });

        this.subscription.addReceiptTask(() ->
                LOG.log(System.Logger.Level.INFO,
                        "Notification subscription confirmed"));

        this.subscription.addReceiptLostTask(() ->
                LOG.log(System.Logger.Level.WARNING,
                        "Notification subscription receipt timed out"));
    }

    @Override
    public void handleFrame(StompHeaders headers, Object payload) {
        // StompSessionHandler also receives broker STOMP ERROR frames.
        LOG.log(System.Logger.Level.ERROR,
                "Broker STOMP ERROR: {0}", payload);
    }

    @Override
    public void handleException(
            StompSession session,
            StompCommand command,
            StompHeaders headers,
            byte[] payload,
            Throwable exception) {

        LOG.log(System.Logger.Level.ERROR,
                "STOMP frame processing failed; command=" + command,
                exception);
    }

    @Override
    public void handleTransportError(
            StompSession session,
            Throwable exception) {

        LOG.log(System.Logger.Level.WARNING,
                "STOMP transport error for session "
                        + (session != null ? session.getSessionId() : "unknown"),
                exception);
    }

    public void unsubscribe() {
        StompSession.Subscription current = this.subscription;
        if (current != null) {
            current.unsubscribe();
            this.subscription = null;
        }
    }
}
\`\`\`

Đây là một ví dụ thành phần client; nó cần Spring Messaging/WebSocket, Jackson nếu dùng JSON, một broker có destination \`/topic/notifications\` và một \`Consumer\` do ứng dụng cung cấp. Có thể đặt mỗi kiểu \`public\` trong tệp riêng.

Trong ví dụ:

1. \`afterConnected\` nhận phiên đã sẵn sàng và đăng ký \`/topic/notifications\`.
2. \`getPayloadType\` yêu cầu converter chuyển payload thành \`Notification\`.
3. \`handleFrame\` của subscription nhận message nghiệp vụ.
4. Receipt callback cho biết broker đã xử lý frame SUBSCRIBE hoặc receipt đã hết thời hạn.
5. \`handleFrame\` của session handler nhận frame \`ERROR\` ở cấp session.
6. \`handleException\` nhận exception từ quá trình xử lý frame.
7. \`handleTransportError\` nhận lỗi tầng transport.
8. \`unsubscribe\` hủy subscription hiện tại khi ứng dụng không còn cần nhận message.

Giữ callback ngắn và tránh chạy truy vấn chậm hoặc xử lý tốn thời gian ngay trên luồng nhận message. Có thể chuyển payload sang executor hoặc hàng đợi ứng dụng, đồng thời đặt giới hạn hàng đợi để tránh tăng bộ nhớ vô hạn khi consumer xử lý chậm.

## 7. StompSession và quản lý subscription

\`StompSession\` là API thao tác với một phiên STOMP đã kết nối:

| API | Mục đích |
| --- | --- |
| \`getSessionId()\` | Lấy ID phiên hiện tại |
| \`isConnected()\` | Kiểm tra trạng thái kết nối của phiên |
| \`send(destination, payload)\` | Gửi message tới destination |
| \`subscribe(destination, handler)\` | Đăng ký destination và nhận \`Subscription\` handle |
| \`setAutoReceipt(true)\` | Tự thêm receipt header cho các thao tác send/subscribe tiếp theo |
| \`disconnect()\` | Gửi STOMP DISCONNECT và đóng phiên theo cách chủ động |

Subscription handle có thể được giữ lại để hủy đăng ký:

\`\`\`java
StompSession.Subscription subscription =
        session.subscribe("/topic/orders", orderFrameHandler);

// Khi không cần nhận message nữa:
subscription.unsubscribe();
\`\`\`

Subscription thuộc về phiên đã tạo nó. Khi phiên bị mất hoặc đóng, không nên tiếp tục dùng handle cũ. Sau khi kết nối lại, phải gọi \`subscribe\` trên \`StompSession\` mới và lưu các handle mới.

Nếu một phiên cần nhiều destination, lưu chúng trong một registry theo session để có thể quản lý và hủy đăng ký rõ ràng. Tránh đăng ký lặp mỗi lần UI refresh hoặc mỗi lần một service callback chạy. Có thể dùng một cờ trạng thái hoặc cấu trúc map theo destination để bảo đảm chỉ tạo một subscription cần thiết trên mỗi phiên.

## 8. Heartbeat và receipt

### 8.1. Heartbeat

Heartbeat là tín hiệu nhỏ cho biết kết nối STOMP vẫn hoạt động ngay cả khi không có message nghiệp vụ. Để bật heartbeat cho \`WebSocketStompClient\`, cấu hình \`TaskScheduler\`; có thể tùy chỉnh hai khoảng thời gian mặc định 10 giây:

- Khoảng không có dữ liệu gửi đi trước khi client phát heartbeat.
- Khoảng không nhận dữ liệu trước khi client xem kết nối đã chết và đóng kết nối.

Các khoảng thời gian thực tế còn phụ thuộc heartbeat được thương lượng giữa client và server theo STOMP. Client chỉ gửi heartbeat khi không có message khác được gửi. Do đó, heartbeat không phải là message nghiệp vụ và không thể dùng để chứng minh server đã xử lý lệnh của ứng dụng.

Nếu dùng external broker, lưu ý rằng message hướng tới destination nội bộ của ứng dụng có thể được xem là hoạt động ở client nhưng không được chuyển tiếp tới broker. Cần cấu hình scheduler phù hợp ở phía broker relay khi kiến trúc yêu cầu heartbeat tới broker trong trường hợp đó.

Mỗi kết nối có thể tạo các tác vụ heartbeat riêng. Khi chạy tải lớn với hàng nghìn client trên một máy, cân nhắc chi phí scheduler và mục tiêu của bài test trước khi bật heartbeat cho toàn bộ kết nối mô phỏng.

### 8.2. Receipt

Receipt xác nhận ở cấp STOMP rằng server/broker đã xử lý frame có yêu cầu receipt. Nó hữu ích khi cần biết một lệnh SEND hoặc SUBSCRIBE đã được broker tiếp nhận. Receipt không xác nhận rằng nghiệp vụ phía server đã hoàn tất hoặc người dùng cuối đã xử lý message.

Có thể bật receipt tự động:

\`\`\`java
session.setAutoReceipt(true);
StompSession.Receiptable receipt =
        session.send("/app/orders", orderCommand);

receipt.addReceiptTask(() ->
        System.out.println("Broker đã xác nhận SEND"));

receipt.addReceiptLostTask(() ->
        System.err.println("Không nhận được receipt đúng hạn"));
\`\`\`

Hoặc yêu cầu receipt thủ công bằng header cho một thao tác cụ thể. Cả \`send\` và \`subscribe\` trả về \`Receiptable\` để đăng ký callback thành công hoặc bị mất. Cần cấu hình \`TaskScheduler\` để theo dõi thời hạn receipt; thời hạn mặc định là 15 giây.

Broker phải hỗ trợ receipt theo yêu cầu của ứng dụng. Nếu broker không hỗ trợ hoặc phản hồi chậm hơn thời hạn, callback receipt-lost có thể được gọi. Không diễn giải receipt timeout là bằng chứng message chắc chắn chưa được xử lý: frame có thể đã tới broker nhưng phản hồi bị mất trên đường truyền. Với lệnh nghiệp vụ cần retry, hãy dùng request ID/idempotency key để tránh thực hiện trùng.

## 9. Reconnect và khôi phục phiên

Spring không tự động reconnect client STOMP khi kết nối bị mất. Broker relay phía server có thể tự kết nối lại system connection tới broker, nhưng các client WebSocket đang kết nối cần có logic reconnect riêng. Heartbeat giúp phát hiện kết nối không còn phản hồi; nó không tự mở phiên mới.

Một quy trình phục hồi nên có các bước:

1. Nhận biết lỗi kết nối qua \`handleTransportError\` hoặc lỗi từ future của lần kết nối ban đầu.
2. Đánh dấu phiên hiện tại là không còn sử dụng được; ngừng gửi message qua session cũ.
3. Chờ một khoảng thời gian trước khi thử lại. Dùng exponential backoff có giới hạn và jitter để nhiều client không đồng loạt kết nối lại.
4. Tạo kết nối mới bằng \`connectAsync\`.
5. Chờ frame \`CONNECTED\`; trong \`afterConnected\`, lưu session mới và tạo lại mọi subscription.
6. Đồng bộ lại dữ liệu ứng dụng bằng snapshot, sequence number hoặc cơ chế replay nếu hệ thống cần bảo đảm không mất sự kiện.
7. Nếu ứng dụng đang shutdown hoặc người dùng chủ động logout, hủy retry và đóng tài nguyên.

Ví dụ tính thời gian chờ retry:

\`\`\`java
static long retryDelayMillis(int attempt) {
    long base = 500L;
    long max = 30_000L;
    int exponent = Math.min(attempt, 10);
    long exponential = Math.min(max, base * (1L << exponent));

    // Jitter ngẫu nhiên trong khoảng 0..25% thời gian chờ.
    long jitter = java.util.concurrent.ThreadLocalRandom.current()
            .nextLong(Math.max(1L, exponential / 4L));

    return exponential + jitter;
}
\`\`\`

Đây chỉ là hàm tính thời gian chờ. Bộ điều phối reconnect cần thêm trạng thái để bảo đảm:

- Chỉ có một lần kết nối lại đang chờ hoặc đang chạy tại một thời điểm.
- Không retry sau khi người dùng chủ động disconnect.
- Hủy tác vụ retry khi ứng dụng shutdown.
- Không giữ session/subscription cũ sau khi đã chuyển sang phiên mới.
- Có giới hạn số lần thử hoặc cơ chế circuit breaker khi server ngừng hoạt động lâu.
- Không retry lỗi xác thực hoặc cấu hình sai một cách vô hạn; cần phân biệt lỗi tạm thời với lỗi cần can thiệp.

Một lần reconnect tạo ra một STOMP session mới. Các subscription cũ không tự xuất hiện trên session mới. Đăng ký lại trong \`afterConnected\` là cách tập trung để mọi lần kết nối thành công đều thiết lập cùng một tập subscription. Cần bảo đảm callback này không vô tình đăng ký hai lần cho cùng một session.

### 9.1. Snapshot và sự kiện sau reconnect

Khi kết nối bị mất, client có thể bỏ lỡ message trong khoảng thời gian offline. Việc đăng ký lại destination chỉ giúp nhận message từ thời điểm subscription mới có hiệu lực.

Nếu ứng dụng cần tính nhất quán, hãy gắn sequence/version vào event và snapshot. Khi reconnect, client có thể:

- Yêu cầu snapshot hiện tại rồi thay thế state cũ.
- Gửi sequence cuối cùng đã xử lý để server phát lại các event còn thiếu.
- Loại bỏ event trùng theo event ID hoặc sequence.
- Phát hiện khoảng trống sequence và yêu cầu đồng bộ lại.

Không giả định STOMP session tự lưu hàng đợi message cho client offline. Khả năng lưu trữ/replay phụ thuộc broker và thiết kế ứng dụng.

## 10. Đóng kết nối và giải phóng tài nguyên

Khi ứng dụng chủ động kết thúc phiên:

\`\`\`java
if (session != null && session.isConnected()) {
    session.disconnect();
}
\`\`\`

Có thể unsubscribe các destination trước khi disconnect nếu ứng dụng cần hủy đăng ký có kiểm soát. Đóng session khác với dừng toàn bộ \`WebSocketStompClient\`: một client có thể quản lý nhiều session, nên chỉ gọi \`stop()\` khi muốn dừng component client và đang chịu trách nhiệm vòng đời của component đó.

Trong ứng dụng Spring, để ApplicationContext quản lý bean \`WebSocketStompClient\` và \`TaskScheduler\`. Khi tự tạo chúng, đóng session, dừng client nếu cần và shutdown scheduler trong bước cleanup. Không gọi \`System.exit\` để xử lý một lỗi kết nối thông thường.

\`StompSessionHandler\` không có callback riêng tên \`afterDisconnected\`. Vì vậy, đừng viết logic cleanup dựa trên một callback như vậy. Có thể đặt cleanup tại nơi ứng dụng gọi \`disconnect\`, xử lý \`ConnectionLostException\` trong \`handleTransportError\`, hoặc dùng trạng thái lifecycle của component do ứng dụng quản lý. Phía server có các Spring application events như \`SessionConnectEvent\`, \`SessionConnectedEvent\` và \`SessionDisconnectEvent\`; đó là event phía server, không phải callback của client handler. \`SessionDisconnectEvent\` có thể được phát nhiều lần cho cùng một phiên, nên listener server phải idempotent.

## 11. Phân biệt các nhóm lỗi

| Hiện tượng | Nơi xử lý | Hướng điều tra |
| --- | --- | --- |
| Không mở được WebSocket hoặc connect future thất bại | Future của \`connectAsync\` và log transport | URL, TLS, HTTP status, proxy, handshake headers, server availability |
| STOMP CONNECT bị broker từ chối | STOMP ERROR hoặc lỗi kết nối tùy thời điểm | CONNECT headers, credentials, phiên bản STOMP, quyền truy cập |
| Broker gửi frame ERROR trong phiên | \`handleFrame\` của \`StompSessionHandler\` | Error message, destination, broker ACL, nội dung lệnh |
| JSON không giải mã được hoặc handler subscription ném exception | \`handleException\` | Content-Type, MessageConverter, payload schema, code trong handler |
| Socket đóng bất thường hoặc mất kết nối | \`handleTransportError\` | Network, idle timeout, proxy, server restart, heartbeat |
| Không nhận message sau reconnect | Logic \`afterConnected\` và subscription registry | Subscription có được tạo lại không, receipt, destination, resync |
| Receipt bị mất | Callback receipt-lost | Broker có hỗ trợ receipt, scheduler, timeout, network delay |
| Inbound payload vượt giới hạn | \`handleException\` với lỗi chuyển đổi | \`inboundMessageSizeLimit\`, kích thước payload, phân mảnh ở transport |

Không nên chỉ log exception rồi bỏ qua. Hãy ghi nhận loại lỗi, session ID, destination hoặc STOMP command khi có, thời điểm và correlation ID. Không ghi passcode, token, cookie hoặc toàn bộ payload nhạy cảm.

## 12. Kiểm thử vòng đời và lỗi

Một bộ kiểm thử có giá trị nên xác nhận các mốc của giao thức, không chỉ gọi trực tiếp callback:

1. **Kết nối thành công:** xác nhận \`afterConnected\` chỉ chạy sau khi client nhận \`CONNECTED\`.
2. **Đăng ký:** xác nhận handler tạo đúng các subscription một lần trên mỗi session.
3. **Nhận message:** xác nhận \`getPayloadType\` chọn đúng DTO và \`handleFrame\` của subscription nhận payload đã giải mã.
4. **Broker ERROR:** gửi frame ERROR giả lập và xác nhận session handler ghi nhận nội dung.
5. **Lỗi giải mã:** gửi payload sai schema/Content-Type và xác nhận lỗi được chuyển tới \`handleException\`.
6. **Lỗi transport:** đóng socket bất thường và xác nhận \`handleTransportError\` được xử lý.
7. **Receipt:** xác nhận callback thành công và callback mất receipt trong các tình huống tương ứng; dùng broker hỗ trợ receipt.
8. **Reconnect:** ngắt kết nối, cho client tạo phiên mới và xác nhận subscription được khôi phục đúng một lần.
9. **Shutdown:** xác nhận retry bị hủy, session được đóng và scheduler được giải phóng.

Có thể kiểm thử handler bằng mock \`StompSession\` để xác nhận hành vi trong \`afterConnected\`, nhưng cần thêm kiểm thử tích hợp với server STOMP thật để kiểm tra handshake, CONNECTED, converter, receipt và transport. Mock không chứng minh broker hỗ trợ một tính năng giao thức.

## 13. Lỗi triển khai thường gặp

- **Đánh dấu connected ngay khi WebSocket handshake xong:** STOMP CONNECT/CONNECTED vẫn có thể thất bại. Chỉ cập nhật trạng thái phiên STOMP sau \`afterConnected\` hoặc khi future kết nối hoàn tất.
- **Cho rằng Adapter tự log lỗi:** các phương thức mặc định rỗng. Override callback và tích hợp logging/metrics phù hợp.
- **Chỉ xử lý handleException:** frame STOMP ERROR được chuyển qua \`handleFrame\`; lỗi transport đi qua \`handleTransportError\`.
- **Không override handleFrame:** adapter mặc định bỏ qua frame ERROR, khiến nguyên nhân từ broker khó quan sát.
- **Dùng cùng handler để nhận mọi MESSAGE:** message của subscription được xử lý bởi \`StompFrameHandler\` truyền vào \`subscribe\`; session handler chủ yếu nhận frame ERROR ở cấp session.
- **Reconnect nhưng không subscribe lại:** session mới không thừa hưởng subscription của phiên cũ.
- **Tạo nhiều subscription trùng lặp:** thường xảy ra khi đăng ký trong cả \`afterConnected\` và callback future hoặc khi retry không được điều phối.
- **Chạy tác vụ nặng trong callback:** làm chậm luồng nhận frame, gây backlog và timeout. Chuyển việc nặng sang executor có giới hạn.
- **Bỏ qua heartbeat/receipt timeout:** kết nối chết hoặc broker chậm có thể không được phát hiện kịp thời.
- **Retry vô hạn mọi lỗi:** lỗi xác thực, sai destination hoặc cấu hình converter không tự hết khi đợi lâu hơn.
- **Dùng receipt như xác nhận nghiệp vụ:** receipt xác nhận xử lý frame ở giao thức; nếu cần xác nhận nghiệp vụ, server phải gửi phản hồi nghiệp vụ riêng.

## 14. Checklist triển khai

- [ ] Chọn đúng transport và endpoint \`ws://\` hoặc \`wss://\`.
- [ ] Cấu hình MessageConverter phù hợp payload.
- [ ] Cấu hình TaskScheduler nếu dùng heartbeat hoặc receipt.
- [ ] Dùng \`afterConnected\` làm mốc phiên STOMP sẵn sàng.
- [ ] Tạo subscription và lưu handle theo session.
- [ ] Override \`handleFrame\` để quan sát STOMP ERROR.
- [ ] Phân biệt \`handleException\` với \`handleTransportError\`.
- [ ] Giới hạn kích thước message và kiểm soát payload.
- [ ] Dùng TLS và quản lý credentials an toàn.
- [ ] Thiết kế reconnect có backoff, jitter, hủy retry khi shutdown.
- [ ] Tạo lại subscription và đồng bộ dữ liệu sau reconnect.
- [ ] Đóng session, client và scheduler theo đúng quyền sở hữu vòng đời.

## Tài liệu tham khảo chính thức

- [Spring Framework — STOMP Client](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/client.html): cấu hình WebSocketStompClient, kết nối, handler, subscription, heartbeat, receipt và giới hạn message.
- [StompSessionHandler Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/simp/stomp/StompSessionHandler.html): hợp đồng callback vòng đời và xử lý lỗi của client.
- [StompSessionHandlerAdapter Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/simp/stomp/StompSessionHandlerAdapter.html): hành vi mặc định của adapter.
- [StompSession Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/simp/stomp/StompSession.html): API gửi, subscribe, unsubscribe, receipt và disconnect.
- [Spring Framework — Application Context Events](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/application-context-events.html): các event STOMP ở phía server và hành vi khi session ngắt kết nối.

**Ghi nhớ:** \`afterConnected\` xác nhận phiên STOMP đã nhận CONNECTED; \`handleFrame\` giúp xử lý frame ERROR; \`handleException\` dành cho lỗi xử lý frame; \`handleTransportError\` dành cho lỗi kết nối. Mỗi lần reconnect là một session mới, vì vậy ứng dụng cần tạo lại subscription và đồng bộ lại trạng thái cần thiết.
