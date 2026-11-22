# Giới hạn của kết nối lâu dài khi client hoặc server ngắt

WebSocket tạo một kết nối hai chiều tồn tại lâu giữa client và server. Kết nối này giúp trao đổi dữ liệu liên tục mà không phải mở một HTTP request mới cho mỗi message, nhưng bản thân kết nối không lưu lịch sử message và không tự khôi phục trạng thái ứng dụng sau khi mạng bị ngắt.

Khi client, server, proxy hoặc broker mất kết nối, ứng dụng phải giải quyết ba việc riêng:

1. **Phát hiện:** nhận biết kết nối đã chết hoặc không còn phản hồi.
2. **Kết nối lại:** thiết lập một WebSocket/STOMP session mới và đăng ký lại những gì cần thiết.
3. **Khôi phục dữ liệu:** xác định message nào đã đến, message nào bị bỏ lỡ và cách tiếp tục mà không xử lý trùng.

Spring Framework cung cấp callback, event, heartbeat và giới hạn transport để hỗ trợ các việc này. Việc kết nối lại và khôi phục dữ liệu nghiệp vụ vẫn cần được thiết kế theo yêu cầu của ứng dụng.

## 1. Kết nối WebSocket lâu dài hoạt động thế nào?

WebSocket bắt đầu bằng HTTP opening handshake. Khi handshake thành công, hai bên chuyển sang trao đổi frame WebSocket trên kết nối TCP đã mở.

~~~text
Client                         Server
  |                               |
  |------ HTTP Upgrade ---------->|
  |<----- 101 Switching ----------|
  |                               |
  |<==== WebSocket frames ========>|
  |                               |
  |------ Close frame ------------>|
  |<----- Close frame -------------|
  |                               |
  |------ TCP connection closed --|
~~~

Kết nối có trạng thái ở tầng transport. Hai bên có thể gửi text frame, binary frame, ping, pong và close frame. Khi kết nối còn hoạt động, TCP cung cấp luồng byte có thứ tự và cơ chế truyền lại ở tầng mạng.

Tuy nhiên, WebSocket không tự cung cấp:

- Kho lưu trữ message khi client offline.
- Replay message sau khi reconnect.
- Acknowledgement nghiệp vụ rằng client đã xử lý xong.
- Khôi phục subscription hoặc state trong bộ nhớ sau server restart.
- Bảo đảm client luôn online hoặc server luôn giữ socket mở.

Nếu cần những hành vi đó, ứng dụng phải dùng broker có khả năng lưu trữ phù hợp hoặc xây dựng cơ chế lưu event, cursor, acknowledgement và resume ở tầng nghiệp vụ.

## 2. Các kiểu ngắt kết nối

### 2.1. Đóng kết nối có chủ đích

Một bên gửi WebSocket Close frame để bắt đầu closing handshake. Hai bên trao đổi Close frame rồi đóng TCP connection.

Các tình huống thường gặp:

- Người dùng đóng tab hoặc rời trang.
- Client gọi close() khi logout.
- Server đóng session trong lúc deploy hoặc bảo trì.
- Ứng dụng chủ động từ chối một session không còn hợp lệ.

Close frame có thể chứa status code và reason. Code 1000 biểu thị đóng bình thường; 1001 thường dùng khi endpoint đang rời đi, chẳng hạn server shutdown.

### 2.2. Mất mạng đột ngột

Client có thể mất Wi-Fi, chuyển mạng, sleep hoặc mất sóng di động. Server có thể bị kill, process crash, máy chủ restart hoặc network route bị thay đổi.

Trong trường hợp này, hai bên có thể không trao đổi được Close frame. TCP connection có thể ở trạng thái half-open một thời gian vì một phía chưa biết đường truyền đã mất.

Client thường quan sát việc đóng bất thường bằng close code 1006. Đây là mã dành cho trạng thái bất thường do local endpoint quan sát; không được gửi trực tiếp trong Close frame trên wire.

### 2.3. Proxy hoặc load balancer đóng kết nối idle

Một kết nối không có dữ liệu trong thời gian dài có thể bị reverse proxy, firewall, NAT hoặc load balancer đóng theo idle timeout.

Ứng dụng có thể thấy socket bị đóng dù client và server vẫn hoạt động bình thường. Nếu heartbeat không được cấu hình hoặc không đi qua toàn bộ network path, các thiết bị trung gian có thể xem kết nối là idle.

### 2.4. Server restart hoặc deploy

Khi một node Spring khởi động lại, mọi WebSocket session đang nằm trong process đó đều mất. Spring không tự di chuyển socket sang node khác.

Client phải tạo connection mới. Server mới phải xác thực lại client, tạo session mới và khôi phục subscription/state cần thiết theo contract ứng dụng.

### 2.5. Client vẫn kết nối nhưng không còn đọc dữ liệu

Một client chậm, tab bị treo hoặc thiết bị có băng thông thấp có thể vẫn giữ socket mở nhưng không tiêu thụ message đủ nhanh. Server tiếp tục ghi dữ liệu vào buffer cho tới khi giới hạn được chạm tới.

Đây là vấn đề slow consumer/backpressure. Nó có thể làm tăng bộ nhớ, độ trễ và ảnh hưởng đến các client khác nếu không giới hạn buffer.

## 3. Điều gì được bảo đảm khi kết nối còn hoạt động?

TCP/WebSocket giữ thứ tự các byte/frame trên một connection đang hoạt động. Nếu connection bị đóng, không có bảo đảm rằng ứng dụng biết chính xác message cuối cùng đã được phía kia xử lý đến đâu.

Ví dụ:

1. Server gửi event E42.
2. TCP stack chấp nhận dữ liệu để gửi.
3. Client có thể đã nhận frame nhưng chưa xử lý.
4. Mạng đứt trước khi client gửi acknowledgement ở tầng ứng dụng.
5. Server không thể biết chắc client đã hoàn thành nghiệp vụ hay chưa.

Một lần gọi send thành công hoặc không ném exception không chứng minh client đã đọc, lưu hoặc xử lý message. Nó chỉ phản ánh kết quả gửi ở tầng transport/API tại thời điểm đó.

Nếu cần xác nhận xử lý, hãy định nghĩa acknowledgement ở tầng ứng dụng. Ví dụ client gửi ACK chứa event ID hoặc sequence number sau khi lưu dữ liệu thành công. Server chỉ đánh dấu event đã được xử lý khi nhận ACK phù hợp.

## 4. Phát hiện kết nối chết bằng Ping/Pong

RFC 6455 định nghĩa Ping và Pong control frame:

- Endpoint có thể gửi Ping khi connection đang mở.
- Khi nhận Ping, endpoint phải phản hồi Pong, trừ trường hợp connection đã bắt đầu đóng.
- Ping có thể dùng làm keepalive hoặc kiểm tra endpoint phía bên kia còn phản hồi không.
- Pong phản hồi phải mang cùng application data của Ping tương ứng.

Heartbeat giúp phát hiện kết nối không còn phản hồi. Nếu gửi Ping nhưng không nhận Pong trong thời hạn đã đặt, endpoint có thể xem connection là mất và đóng nó.

Một lưu ý với browser: WebSocket JavaScript API không cung cấp method để ứng dụng JavaScript tự gửi hoặc nhận Ping/Pong control frame. Trình duyệt xử lý các control frame ở tầng protocol. Với browser client, có thể dùng heartbeat của STOMP hoặc application-level heartbeat nếu cần điều khiển từ JavaScript.

Heartbeat không bảo đảm phát hiện tức thì. Thời điểm phát hiện phụ thuộc chu kỳ heartbeat, timeout, scheduler, network delay và việc thread xử lý có bị nghẽn hay không.

## 5. Heartbeat ở tầng STOMP và SockJS

### 5.1. STOMP heartbeat

Khi dùng STOMP trên WebSocket, client và server có thể thương lượng heartbeat qua header heart-beat của STOMP CONNECT/CONNECTED.

Hai giá trị biểu thị khoảng thời gian tối thiểu mà mỗi phía dự kiến gửi dữ liệu/heartbeat. Giá trị 0 có nghĩa phía đó không gửi heartbeat theo hướng tương ứng. Heartbeat chỉ được gửi khi không có message khác trong khoảng thời gian cần thiết.

Với Spring WebSocketStompClient, có thể cấu hình TaskScheduler và heartbeat mặc định:

~~~java
WebSocketStompClient stompClient =
        new WebSocketStompClient(new StandardWebSocketClient());

stompClient.setTaskScheduler(heartbeatScheduler);
stompClient.setDefaultHeartbeat(
        new long[] {10_000, 10_000}
);
~~~

TaskScheduler được dùng để lập lịch heartbeat và theo dõi STOMP receipt. Khi không cấu hình scheduler, heartbeat mặc định của WebSocketStompClient có thể bị tắt; việc thiết lập scheduler sẽ kích hoạt giá trị mặc định phù hợp nếu chưa được cấu hình khác.

Ở server, simple broker cũng cần TaskScheduler để gửi và kiểm tra heartbeat:

~~~java
registry.enableSimpleBroker("/topic", "/queue")
        .setHeartbeatValue(new long[] {10_000, 10_000})
        .setTaskScheduler(messageBrokerTaskScheduler);
~~~

Các khoảng 10 giây ở ví dụ là giá trị minh họa. Hãy chọn interval và timeout dựa trên idle timeout của proxy, độ trễ mạng, tải hệ thống và số lượng connection. Không đặt heartbeat quá dày khi có hàng chục nghìn client nếu scheduler chưa được sizing phù hợp.

### 5.2. SockJS heartbeat

Khi dùng SockJS fallback, Spring mặc định gửi heartbeat sau khoảng 25 giây nếu connection không có message khác. Heartbeat giúp proxy không xem HTTP streaming/long polling connection là bị treo.

Nếu STOMP client và server đã thương lượng heartbeat, SockJS heartbeat sẽ được tắt để tránh gửi hai cơ chế heartbeat chồng nhau.

Với HTTP streaming hoặc long polling, Servlet API không cung cấp notification trực tiếp cho mọi trường hợp client đã biến mất. Server thường chỉ nhận ra disconnect khi lần ghi tiếp theo thất bại; heartbeat giúp tạo lần ghi định kỳ để phát hiện sớm hơn.

## 6. Callback và event phát hiện disconnect trong Spring

### 6.1. Raw WebSocketHandler

Khi triển khai WebSocketHandler hoặc TextWebSocketHandler, các callback quan trọng gồm:

- afterConnectionEstablished: handshake thành công và session sẵn sàng.
- handleTransportError: transport báo lỗi khi đọc/ghi hoặc xử lý message.
- afterConnectionClosed: connection đã đóng hoặc transport error đã xảy ra.

Ví dụ:

~~~java
@Component
public class PresenceWebSocketHandler extends TextWebSocketHandler {

    private final PresenceService presenceService;

    public PresenceWebSocketHandler(PresenceService presenceService) {
        this.presenceService = presenceService;
    }

    @Override
    public void afterConnectionEstablished(WebSocketSession session) {
        presenceService.connected(
                session.getId(),
                session.getPrincipal()
        );
    }

    @Override
    public void handleTransportError(
            WebSocketSession session,
            Throwable exception) {

        presenceService.markTransportError(session.getId(), exception);
    }

    @Override
    public void afterConnectionClosed(
            WebSocketSession session,
            CloseStatus status) {

        presenceService.disconnected(
                session.getId(),
                status.getCode()
        );
    }
}
~~~

Ví dụ minh họa lifecycle hook. PresenceService cần xử lý việc cập nhật trạng thái an toàn khi callback lỗi và callback đóng cùng xuất hiện. Không giả định một callback duy nhất sẽ luôn mô tả đầy đủ nguyên nhân mất kết nối.

Sau khi afterConnectionClosed được gọi, việc tiếp tục gửi message qua session đó không được khuyến nghị và thường sẽ thất bại.

### 6.2. STOMP SessionDisconnectEvent

Khi dùng STOMP, Spring phát các event như:

- SessionConnectEvent: nhận được STOMP CONNECT.
- SessionConnectedEvent: broker đã phản hồi CONNECTED, STOMP session được thiết lập.
- SessionSubscribeEvent và SessionUnsubscribeEvent: client đăng ký hoặc hủy subscription.
- SessionDisconnectEvent: STOMP session kết thúc.

SessionDisconnectEvent có thể được phát nhiều hơn một lần cho cùng session. Listener xử lý event này phải idempotent.

~~~java
@Component
public class StompSessionLifecycleListener {

    private final PresenceService presenceService;

    public StompSessionLifecycleListener(
            PresenceService presenceService) {
        this.presenceService = presenceService;
    }

    @EventListener
    public void onDisconnect(SessionDisconnectEvent event) {
        presenceService.removeIfPresent(event.getSessionId());
    }
}
~~~

Hãy dùng session ID để dọn trạng thái của connection tương ứng. Nếu nghiệp vụ quản lý online/offline theo user, cần tính đến việc cùng user có thể mở nhiều tab hoặc thiết bị; đóng một session không đồng nghĩa user đã offline hoàn toàn.

## 7. Client phải tự kết nối lại

Spring STOMP broker relay có thể tự kết nối lại system connection giữa ứng dụng Spring và broker khi broker phục hồi. Các client WebSocket đã bị ngắt không tự động được kết nối lại theo cơ chế đó. Client cần tự thực hiện reconnect.

Một chiến lược phổ biến là exponential backoff có jitter:

1. Thử kết nối lại sau một khoảng ngắn.
2. Nếu tiếp tục thất bại, tăng dần khoảng chờ.
3. Đặt giới hạn tối đa để không chờ quá lâu.
4. Thêm jitter ngẫu nhiên để nhiều client không reconnect đồng thời.
5. Reset số lần retry sau khi connection đã ổn định một khoảng thời gian.

Ví dụ logic client JavaScript:

~~~javascript
let retryAttempt = 0;
let manuallyStopped = false;

function scheduleReconnect() {
    if (manuallyStopped) {
        return;
    }

    const ceiling = Math.min(30_000, 500 * (2 ** retryAttempt));
    retryAttempt = Math.min(retryAttempt + 1, 10);

    const delay = Math.random() * ceiling;
    window.setTimeout(connect, delay);
}

function connect() {
    const socket = new WebSocket("wss://example.com/ws");

    socket.addEventListener("open", () => {
        restoreSubscriptionsAndResumeState(socket);

        window.setTimeout(() => {
            if (socket.readyState === WebSocket.OPEN) {
                retryAttempt = 0;
            }
        }, 30_000);
    });

    socket.addEventListener("close", () => {
        scheduleReconnect();
    });

    socket.addEventListener("error", () => {
        socket.close();
    });
}
~~~

Đây là đoạn minh họa cho browser client; ứng dụng cần bổ sung quản lý timer, hủy reconnect khi người dùng logout, ngăn tạo nhiều socket đồng thời và xử lý lỗi xác thực. Trong ứng dụng STOMP, sau khi kết nối WebSocket thành công còn phải gửi STOMP CONNECT, chờ CONNECTED rồi đăng ký lại các destination cần thiết.

Không reset retry counter ngay khi socket vừa mở. Nếu connection liên tục mở rồi đóng sau vài giây, reset ngay lập tức sẽ khiến client lặp lại retry nhanh vô hạn.

## 8. Reconnect không tự khôi phục subscription và state

Một WebSocket session mới có session ID mới. Các subscription, request đang chờ, session attribute và dữ liệu chỉ lưu trong bộ nhớ của connection cũ có thể không còn.

Sau reconnect, client nên thực hiện theo thứ tự:

1. Mở WebSocket connection.
2. Xác thực lại và thiết lập STOMP session nếu dùng STOMP.
3. Đăng ký lại các destination.
4. Gửi cursor/sequence number cuối cùng mà client đã xử lý thành công.
5. Nhận phần event còn thiếu hoặc tải snapshot mới.
6. Gửi acknowledgement cho event đã xử lý theo contract.

Không dùng WebSocket session ID làm định danh user lâu dài. Dùng user ID đã được xác thực, device ID hoặc một business client identity phù hợp; session ID chỉ đại diện cho một lần kết nối.

Nếu server restart, mọi state chỉ nằm trong memory của node đó có thể mất. State cần tồn tại qua restart phải được lưu ở database, distributed cache hoặc broker phù hợp.

## 9. Message bị mất hoặc xử lý trùng khi connection đứt

Giả sử server gửi event E100, E101, E102 trong lúc mạng chập chờn. Client nhận E100 và E101, nhưng connection mất trước khi E102 đến.

Nếu server không có event log hoặc cơ chế replay, client không có cách yêu cầu lấy lại E102. Ngược lại, nếu client nhận E101 nhưng ACK bị mất, server có thể gửi E101 lần nữa khi reconnect.

Đây là hai tình huống phổ biến:

- **Message gap:** client bỏ lỡ một hoặc nhiều message trong thời gian offline.
- **Duplicate delivery:** client nhận lại message đã xử lý vì acknowledgement trước đó không đến server.

Một giao thức resume nên có:

- eventId duy nhất để deduplicate.
- sequence number tăng theo stream hoặc partition.
- cursor cuối cùng client xác nhận đã xử lý.
- nơi lưu event để replay.
- acknowledgement sau khi client lưu/xử lý thành công.
- chính sách retention để xác định thời gian có thể replay.

Ví dụ payload:

~~~json
{
  "eventId": "evt-1002",
  "sequence": 1002,
  "type": "OrderUpdated",
  "data": {
    "orderId": "ORD-42",
    "status": "PAID"
  }
}
~~~

Khi reconnect, client gửi lastProcessedSequence=1001. Server có thể phát lại từ sequence 1002 nếu event còn trong retention. Client lưu eventId hoặc sequence đã xử lý để bỏ qua bản sao.

WebSocket chỉ vận chuyển message. Việc lưu event, replay và deduplication thuộc tầng ứng dụng hoặc broker.

## 10. STOMP receipt, acknowledgement và xử lý nghiệp vụ

STOMP có receipt để client yêu cầu server gửi RECEIPT frame sau khi một frame gửi/subscribe được xử lý ở phía server. Receipt giúp biết server đã xử lý frame theo semantics của STOMP.

Receipt không tự chứng minh database transaction hoặc side effect nghiệp vụ ở client/server đã hoàn tất. Nếu cần xác nhận nghiệp vụ, hãy định nghĩa application ACK riêng chứa event ID, kết quả và sequence.

STOMP subscription có các acknowledgement mode như auto, client và client-individual. Chọn mode theo semantics broker và cách client xử lý message. Nếu dùng external broker, kiểm tra cách broker lưu subscription và xử lý unacknowledged message khi connection đóng.

Spring simple broker lưu subscription trong memory và gửi message tới client đang kết nối. Nó không phải message store bền vững cho client offline. Nếu cần durable subscription hoặc replay khi offline, dùng broker ngoài có hỗ trợ tính năng đó và cấu hình theo tài liệu của broker.

## 11. Broker và WebSocket connection là hai kết nối khác nhau

Trong kiến trúc Spring STOMP broker relay có ít nhất hai nhóm kết nối:

- WebSocket connection từ browser/client đến ứng dụng Spring.
- TCP/STOMP connection từ Spring broker relay đến message broker.

Broker relay có thể reconnect system connection khi broker khởi động lại. Spring phát BrokerAvailabilityEvent khi trạng thái system connection thay đổi. Thành phần gửi qua SimpMessagingTemplate nên theo dõi trạng thái này và sẵn sàng xử lý MessageDeliveryException nếu broker chưa sẵn sàng.

Việc system connection đã phục hồi không làm các WebSocket client đã rớt tự động kết nối lại. Client cần mở session mới và đăng ký subscription lại.

Nếu broker hỗ trợ durable subscription, hãy cấu hình durable subscription theo contract của broker/STOMP client. Spring simple broker không cung cấp persistence cho subscription hoặc message offline.

## 12. Giới hạn của proxy, load balancer và server

Kết nối lâu dài chịu ảnh hưởng của mọi thành phần trên đường truyền:

- Reverse proxy và load balancer có idle timeout.
- Firewall và NAT có thể xóa mapping khi không có traffic.
- Servlet container hoặc WebSocket engine có idle timeout và giới hạn buffer.
- Operating system có giới hạn file descriptor, socket và memory.
- Spring application có giới hạn connection, scheduler, thread pool và send buffer.
- Broker có giới hạn connection, subscription và dung lượng lưu message.

Heartbeat nên được gửi thường xuyên hơn idle timeout ngắn nhất trên toàn bộ network path, có khoảng an toàn cho scheduler delay và network jitter.

Nếu proxy đóng connection sau 60 giây idle, heartbeat mỗi 90 giây sẽ không bảo vệ được socket. Ngược lại, heartbeat quá dày làm tăng traffic và công việc scheduler khi số lượng client lớn.

Cấu hình idle timeout phải đồng bộ giữa client, server, proxy và broker. Đừng giả định tăng timeout trên Spring server sẽ thay đổi timeout do load balancer hoặc firewall áp dụng.

## 13. Slow consumer, send buffer và giới hạn message size

Một client có băng thông thấp có thể tiêu thụ dữ liệu chậm hơn tốc độ server phát. Spring phải buffer các message đang chờ gửi. Nếu không giới hạn, buffer có thể tăng và gây áp lực bộ nhớ.

Với STOMP over WebSocket, có thể cấu hình giới hạn transport:

~~~java
@Override
public void configureWebSocketTransport(
        WebSocketTransportRegistration registration) {

    registration
            .setMessageSizeLimit(64 * 1024)
            .setSendTimeLimit(15_000)
            .setSendBufferSizeLimit(512 * 1024);
}
~~~

Ý nghĩa:

- messageSizeLimit giới hạn kích thước sub-protocol message như STOMP frame sau khi được ghép từ các WebSocket message.
- sendTimeLimit giới hạn thời gian gửi tới một session.
- sendBufferSizeLimit giới hạn lượng dữ liệu đang chờ gửi tới một session.

Các con số là ví dụ khởi đầu, cần điều chỉnh theo payload, số client và băng thông thực tế. Khi giới hạn bị vượt, Spring có thể dọn trạng thái gửi và đóng session để bảo vệ tài nguyên.

Với raw WebSocketHandler, có thể dùng ConcurrentWebSocketSessionDecorator để tuần tự hóa việc gửi và giới hạn buffer:

~~~java
WebSocketSession safeSession =
        new ConcurrentWebSocketSessionDecorator(
                session,
                10_000,
                512 * 1024
        );

safeSession.sendMessage(new TextMessage("update"));
~~~

Nên tạo wrapper một lần cho session và dùng lại. WebSocket session chuẩn không cho phép nhiều thread gửi đồng thời; decorator đảm bảo một thread gửi tại một thời điểm và buffer các lần gửi cạnh tranh.

Với Jakarta WebSocket server, có thể cấu hình giới hạn text/binary buffer ở server container:

~~~java
@Bean
public ServletServerContainerFactoryBean webSocketContainer() {
    ServletServerContainerFactoryBean container =
            new ServletServerContainerFactoryBean();

    container.setMaxTextMessageBufferSize(64 * 1024);
    container.setMaxBinaryMessageBufferSize(64 * 1024);

    return container;
}
~~~

Giới hạn của server container và giới hạn STOMP frame là hai tầng khác nhau. Cần kiểm tra cả hai nếu ứng dụng dùng STOMP.

## 14. Scale nhiều client và nhiều server node

Một WebSocket connection được giữ bởi một process/node cụ thể trong suốt vòng đời socket. Khi client reconnect, load balancer có thể đưa nó sang node khác.

Sticky session có thể giúp một connection hiện tại tiếp tục đi đến cùng node, nhưng không làm state của node được sao chép sang node khác. Nếu node cũ chết, client vẫn phải reconnect và ứng dụng phải khôi phục state từ nguồn dùng chung.

Với nhiều node Spring, cần cân nhắc:

- Dùng external broker để phân phối message giữa các node.
- Lưu presence, subscription metadata hoặc session mapping cần thiết ở shared store nếu nghiệp vụ yêu cầu.
- Dùng user registry và cơ chế broadcast phù hợp khi cần định tuyến tới user đang kết nối trên node khác.
- Tránh dùng static Map trong một node làm nguồn sự thật duy nhất cho trạng thái online.
- Thiết kế graceful shutdown để ngừng nhận kết nối mới, thông báo client reconnect và đóng session có kiểm soát.

Nếu server deploy đồng loạt, hàng nghìn client có thể reconnect cùng lúc. Jitter, backoff và giới hạn tốc độ handshake giúp tránh reconnect storm.

## 15. Authentication và session hết hạn

WebSocket handshake ban đầu thường đi qua HTTP, nên xác thực có thể dựa trên cookie/session hoặc cơ chế authentication của HTTP. Sau khi upgrade, connection tồn tại lâu hơn một HTTP request thông thường.

Nếu access token hết hạn trong lúc socket còn mở, không nên mặc định connection tự bị đóng hoặc quyền truy cập tự được cập nhật. Ứng dụng phải quyết định cách xử lý:

- Đóng connection khi credential hết hạn.
- Yêu cầu client refresh credential rồi reconnect.
- Gửi thông báo application-level yêu cầu xác thực lại.
- Kiểm tra quyền tại các message nhạy cảm nếu chính sách yêu cầu.

Khi reconnect, thực hiện handshake và xác thực lại theo cơ chế bảo mật hiện hành. Không tin user ID hoặc role do client tự gửi trong STOMP header. Kiểm tra Origin, quyền subscribe/send và dữ liệu đầu vào theo chính sách bảo mật của endpoint.

Cũng cần tránh đưa access token vào query string nếu URL có thể bị ghi vào access log, proxy log hoặc browser history.

## 16. Ví dụ cấu hình STOMP heartbeat và transport trong Spring

Ví dụ cấu hình dưới đây minh họa simple broker với heartbeat và giới hạn gửi:

~~~java
@Configuration
@EnableWebSocketMessageBroker
public class WebSocketConfiguration
        implements WebSocketMessageBrokerConfigurer {

    private final TaskScheduler heartbeatScheduler;

    public WebSocketConfiguration(TaskScheduler heartbeatScheduler) {
        this.heartbeatScheduler = heartbeatScheduler;
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.enableSimpleBroker("/topic", "/queue")
                .setHeartbeatValue(new long[] {10_000, 10_000})
                .setTaskScheduler(heartbeatScheduler);

        registry.setApplicationDestinationPrefixes("/app");
    }

    @Override
    public void configureWebSocketTransport(
            WebSocketTransportRegistration registration) {

        registration
                .setMessageSizeLimit(64 * 1024)
                .setSendTimeLimit(15_000)
                .setSendBufferSizeLimit(512 * 1024);
    }
}
~~~

Có thể khai báo scheduler riêng:

~~~java
@Bean
public ThreadPoolTaskScheduler heartbeatScheduler() {
    ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
    scheduler.setPoolSize(4);
    scheduler.setThreadNamePrefix("ws-heartbeat-");
    return scheduler;
}
~~~

Cấu hình này áp dụng cho STOMP message broker tích hợp trong Spring. Nếu dùng broker relay, cần cấu hình heartbeat và reconnect ở tầng broker relay theo yêu cầu của broker; nếu dùng raw WebSocketHandler, hãy cấu hình giới hạn server/container và quản lý send concurrency tương ứng.

## 17. Giám sát kết nối và nguyên nhân disconnect

Không nên chỉ đếm số lần connect/disconnect. Cần quan sát cả chất lượng kết nối và tải gửi.

Các chỉ số hữu ích:

- Số WebSocket session đang mở theo node.
- Số session được tạo/đóng trong một khoảng thời gian.
- Số disconnect theo close status và transport error.
- Heartbeat timeout và thời gian phát hiện disconnect.
- Số lần reconnect của client, thời gian reconnect và tỷ lệ reconnect thành công.
- Số STOMP CONNECT, CONNECTED, DISCONNECT và SUBSCRIBE frame.
- Send time limit exceeded và send buffer limit exceeded.
- Kích thước buffer, message size và độ trễ outbound.
- Số client chậm, số message bị bỏ qua hoặc replay.
- Trạng thái broker relay và số lần system connection reconnect.

Spring cung cấp SessionConnectEvent, SessionConnectedEvent, SessionDisconnectEvent và BrokerAvailabilityEvent để theo dõi lifecycle. SessionDisconnectEvent có thể xuất hiện nhiều lần cho một session, vì vậy cleanup và metric nghiệp vụ phải chống xử lý trùng.

Không log toàn bộ payload hoặc token để chẩn đoán disconnect. Ưu tiên session ID, user identity đã được xác thực, close code, loại lỗi và correlation ID phù hợp.

## 18. Kiểm thử các tình huống mất kết nối

Một bài test chỉ mở WebSocket rồi gửi một message không đủ kiểm tra độ tin cậy của connection lâu dài.

Nên có các tình huống:

1. Client đóng bình thường bằng Close frame.
2. Client mất mạng mà không gửi Close frame.
3. Server restart trong khi có nhiều session.
4. Proxy idle timeout ngắn hơn heartbeat để xác nhận lỗi cấu hình.
5. Heartbeat timeout khi peer không phản hồi.
6. Client reconnect với exponential backoff và jitter.
7. Client đăng ký lại STOMP subscription sau reconnect.
8. Client gửi cursor và server replay các event còn thiếu.
9. ACK bị mất khiến một event được gửi lại; client deduplicate theo event ID.
10. Slow consumer làm send buffer chạm giới hạn.
11. Message vượt giới hạn size của container hoặc STOMP transport.
12. Broker relay mất kết nối rồi phục hồi system connection.
13. Client reconnect sang node Spring khác.
14. Token hết hạn giữa lúc connection đang mở.
15. Nhiều client reconnect đồng thời sau một lần deploy.

Test reconnect nên dùng latch, polling có timeout hoặc điều kiện quan sát được thay vì sleep cố định. Khi kiểm tra mất message, phải xác định rõ message được lưu ở đâu và acknowledgement nào được xem là hoàn tất.

## 19. Lỗi thường gặp

### 19.1. Nghĩ WebSocket tự reconnect

WebSocket protocol không tự thiết lập connection mới sau khi connection cũ đóng. Client phải gọi connect lại và xử lý lỗi.

### 19.2. Nghĩ heartbeat bảo đảm không mất message

Heartbeat chỉ kiểm tra hoạt động của connection. Nó không lưu message, không xác nhận nghiệp vụ và không replay dữ liệu.

### 19.3. Chỉ xử lý close event ở client

Mạng có thể mất đột ngột nên server không nhận Close frame. Server cần heartbeat, transport error và cơ chế timeout để dọn session stale.

### 19.4. Dùng session ID làm định danh lâu dài

Session ID gắn với một connection. Sau reconnect, ID có thể thay đổi. Dùng business identity đã xác thực để khôi phục trạng thái.

### 19.5. Không đăng ký lại subscription

STOMP session mới không tự giữ các subscription của session cũ. Client phải SUBSCRIBE lại sau CONNECTED.

### 19.6. Tin rằng send thành công nghĩa là client đã xử lý

Transport write không phải business acknowledgement. Dùng ACK ở tầng ứng dụng khi cần xác nhận xử lý.

### 19.7. Không giới hạn buffer cho client chậm

Message gửi nhanh hơn tốc độ tiêu thụ làm buffer tăng. Cấu hình send time limit, send buffer size và chính sách drop/coalesce message phù hợp.

### 19.8. Đặt heartbeat dài hơn proxy idle timeout

Proxy có thể đóng connection trước khi heartbeat tiếp theo được gửi. Chọn heartbeat thấp hơn timeout ngắn nhất trên đường truyền.

### 19.9. Cho rằng broker relay reconnect là client reconnect

Broker relay chỉ phục hồi kết nối của Spring tới broker. WebSocket client vẫn cần tự mở session mới.

### 19.10. Cleanup disconnect không idempotent

Spring có thể phát SessionDisconnectEvent nhiều lần. Nếu cleanup chạy trùng có thể làm sai presence count hoặc ghi nhận logout lặp. Dùng thao tác remove-if-present hoặc trạng thái có version.

## 20. Checklist thiết kế kết nối lâu dài

- Client có phát hiện socket close, error và heartbeat timeout không?
- Heartbeat được cấu hình ở đúng tầng WebSocket, STOMP hoặc SockJS?
- Interval có thấp hơn idle timeout của proxy/load balancer không?
- Reconnect có exponential backoff, jitter và giới hạn retry không?
- Client có ngăn nhiều reconnect loop chạy đồng thời không?
- Sau reconnect có xác thực lại và đăng ký lại subscription không?
- Có cursor/sequence để phát hiện message gap không?
- Có event ID và idempotency để xử lý duplicate không?
- Có application ACK nếu cần xác nhận nghiệp vụ không?
- State quan trọng có nằm trong shared store hoặc broker phù hợp không?
- Slow client có send buffer và send time limit không?
- Message size limit được cấu hình ở server container và sub-protocol?
- Server có xử lý duplicate disconnect event an toàn không?
- Broker relay availability có được theo dõi không?
- Nhiều node có thể tiếp nhận client reconnect mà không mất state không?
- Có test server restart, network partition, proxy timeout và reconnect storm không?

## 21. Tài liệu tham khảo

- [RFC 6455 — The WebSocket Protocol](https://www.rfc-editor.org/rfc/rfc6455.html)
- [Spring Framework 6.1 — WebSocket API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/socket/WebSocketSession.html)
- [Spring Framework 6.1 — WebSocketHandler](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/socket/WebSocketHandler.html)
- [Spring Framework 6.1 — ConcurrentWebSocketSessionDecorator](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/socket/handler/ConcurrentWebSocketSessionDecorator.html)
- [Spring Framework 6.1 — WebSocketStompClient](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/socket/messaging/WebSocketStompClient.html)
- [Spring Framework 6.1 — SessionDisconnectEvent](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/socket/messaging/SessionDisconnectEvent.html)
- [Spring Framework Reference — STOMP Client and Heartbeats](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/client.html)
- [Spring Framework Reference — STOMP Application Context Events](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/application-context-events.html)
- [Spring Framework Reference — WebSocket Performance and Send Limits](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/configuration-performance.html)
- [Spring Framework Reference — SockJS Heartbeats and Client Disconnects](https://docs.spring.io/spring-framework/reference/web/websocket/fallback.html)

Kết nối WebSocket giúp trao đổi dữ liệu liên tục trong thời gian session còn sống. Khi client hoặc server ngắt kết nối, ứng dụng phải phát hiện lỗi, tạo session mới và khôi phục dữ liệu theo contract riêng. Heartbeat giúp phát hiện peer không phản hồi; reconnect giúp mở lại transport; event log, cursor, acknowledgement và idempotency mới giải quyết việc tiếp tục luồng dữ liệu an toàn.