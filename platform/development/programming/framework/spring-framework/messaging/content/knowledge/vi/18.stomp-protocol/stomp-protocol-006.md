# Heart-beat và phát hiện kết nối không hoạt động trong STOMP

## 1. Vì sao kết nối lâu dài cần heartbeat?

WebSocket giữ một kết nối TCP mở trong thời gian dài để client và server có thể gửi dữ liệu hai chiều. Kết nối có thể vẫn tồn tại trong bảng trạng thái của ứng dụng dù đường mạng ở giữa đã hỏng. Ví dụ:

- Laptop chuyển từ Wi-Fi sang mạng di động.
- Browser chuyển sang sleep hoặc tab nền bị hệ điều hành giới hạn timer.
- Router hoặc firewall bỏ trạng thái NAT của kết nối idle.
- Reverse proxy đóng socket do idle timeout.
- Broker khởi động lại hoặc mất kết nối tới ứng dụng.
- Một phía bị treo và không còn đọc hoặc ghi dữ liệu.

TCP không phải lúc nào cũng thông báo ngay khi một đường truyền bị đứt âm thầm. Nếu không có dữ liệu đi qua, ứng dụng có thể giữ session cũ rất lâu. Điều này làm sai số lượng client online, giữ subscription không còn người nhận, giữ tài nguyên và khiến thao tác gửi message tới session cũ liên tục thất bại.

Heartbeat là dữ liệu nhỏ được gửi định kỳ khi kết nối không có traffic nghiệp vụ. Khi một phía ngừng nhận heartbeat trong khoảng thời gian cho phép, phía còn lại có thể đánh dấu kết nối là không hoạt động và đóng hoặc loại bỏ session.

Heartbeat giúp kiểm tra liveness của kết nối. Nó không xác nhận người dùng còn nhìn màn hình, không xác nhận nghiệp vụ đã xử lý message và không thay thế ACK/RECEIPT của STOMP.

## 2. Heartbeat nằm ở tầng nào?

Cần phân biệt ba cơ chế thường gặp:

| Cơ chế | Tầng | Dữ liệu gửi | Mục đích |
|---|---|---|---|
| TCP keepalive | TCP/OS | TCP probe | Phát hiện peer hoặc đường TCP không phản hồi |
| WebSocket Ping/Pong | WebSocket | Control frame Ping và Pong | Kiểm tra kết nối WebSocket |
| STOMP heart-beat | STOMP | Một ký tự EOL, thường là LF | Kiểm tra hoạt động của STOMP peer và broker |

STOMP heartbeat là dữ liệu ở tầng ứng dụng. Nếu không có STOMP frame nghiệp vụ nào cần gửi, sender gửi một dòng trống (EOL, thường là byte LF). Nếu đã có dữ liệu STOMP khác đi qua, dữ liệu đó cũng được tính là hoạt động và không cần gửi thêm heartbeat trong khoảng đó.

WebSocket Ping/Pong là control frame của giao thức WebSocket. Browser WebSocket API không cung cấp phương thức JavaScript để ứng dụng tự gửi Ping control frame; runtime và WebSocket implementation xử lý các control frame này. Vì vậy, ứng dụng browser dùng STOMP thường dựa vào STOMP heartbeat để theo dõi hoạt động ở tầng messaging.

TCP keepalive có thể hữu ích ở tầng mạng nhưng thời gian mặc định phụ thuộc hệ điều hành và cấu hình máy chủ. Không nên coi TCP keepalive là timeout nghiệp vụ của STOMP.

## 3. STOMP 1.1/1.2 thương lượng heartbeat

STOMP hỗ trợ heartbeat từ phiên bản 1.1. Hai phía trao đổi khả năng gửi và nhu cầu nhận ngay lúc bắt đầu session:

- Client gửi header heart-beat trong frame CONNECT.
- Server trả header heart-beat trong frame CONNECTED.

Mỗi header có hai số nguyên không âm, đơn vị milliseconds:

**heart-beat: can-send, want-receive**

Số thứ nhất mô tả khoảng thời gian nhỏ nhất mà bên gửi có thể bảo đảm giữa hai heartbeat gửi ra. Giá trị 0 nghĩa là bên đó không thể gửi heartbeat.

Số thứ hai mô tả khoảng thời gian bên gửi mong muốn nhận heartbeat từ peer. Giá trị 0 nghĩa là không yêu cầu nhận heartbeat.

Ví dụ client gửi:

~~~text
CONNECT
accept-version:1.2
host:api.example.com
heart-beat:10000,15000

^@
~~~

Server trả:

~~~text
CONNECTED
version:1.2
heart-beat:5000,20000

^@
~~~

Ở đây:

- Client có thể gửi heartbeat ít nhất mỗi 10.000 ms và muốn server gửi trong khoảng 15.000 ms.
- Server có thể gửi heartbeat ít nhất mỗi 5.000 ms và muốn client gửi trong khoảng 20.000 ms.

Nếu header heart-beat không xuất hiện, STOMP coi như heart-beat:0,0. Khi một giá trị bằng 0 khiến một hướng không thể thương lượng, hướng đó không có heartbeat.

### 3.1. Công thức thương lượng

Ký hiệu:

- **cx**: client có thể gửi heartbeat.
- **cy**: client muốn nhận heartbeat.
- **sx**: server có thể gửi heartbeat.
- **sy**: server muốn nhận heartbeat.

Khoảng heartbeat từ client tới server:

**client → server = max(cx, sy)**

Chỉ có heartbeat nếu cx lớn hơn 0 và sy lớn hơn 0. Nếu một trong hai bằng 0, hướng client tới server bị tắt.

Khoảng heartbeat từ server tới client:

**server → client = max(sx, cy)**

Chỉ có heartbeat nếu sx lớn hơn 0 và cy lớn hơn 0. Nếu một trong hai bằng 0, hướng server tới client bị tắt.

Với ví dụ trên:

| Hướng | Tính toán | Khoảng heartbeat |
|---|---|---:|
| Client → Server | max(10.000, 20.000) | 20.000 ms |
| Server → Client | max(5.000, 15.000) | 15.000 ms |

Giá trị max được dùng vì sender chỉ cam kết gửi theo khả năng của mình, còn receiver chỉ yêu cầu tần suất tối đa mà nó muốn nhận. Hai phía phải chọn khoảng thời gian đáp ứng cả hai điều kiện.

### 3.2. Heartbeat là EOL, không phải một STOMP frame nghiệp vụ

Khi không có frame nghiệp vụ cần gửi trong khoảng đã thương lượng, sender gửi một EOL (end-of-line). Trong STOMP 1.2, EOL là LF hoặc CRLF; heartbeat thông thường là một LF đơn.

Một heartbeat không có command, header, body hay NULL terminator của frame nghiệp vụ. Nó chỉ giữ luồng STOMP có dữ liệu mới để peer biết kết nối còn hoạt động.

STOMP quy định mọi dữ liệu mới nhận được trên kết nối đều có thể chứng minh peer đang hoạt động. Do đó, nếu client liên tục gửi SEND, SUBSCRIBE hoặc frame STOMP khác, những frame đó cũng làm mới trạng thái nhận dữ liệu.

## 4. Khi nào kết nối được coi là không hoạt động?

Giả sử hai phía đã thương lượng khoảng heartbeat n milliseconds cho một hướng. Sender phải gửi dữ liệu mới ít nhất mỗi n milliseconds. Nếu không có frame STOMP nào cần gửi, sender phải gửi EOL.

Receiver có thể xem kết nối là đã chết nếu không nhận dữ liệu mới trong một khoảng thời gian ít nhất bằng n. STOMP specification yêu cầu receiver chừa sai số thời gian (error margin) vì timer, scheduling, network và tải hệ thống có thể làm heartbeat đến muộn.

Không có một hệ số timeout duy nhất bắt buộc cho mọi broker và mọi client. Mỗi implementation có thể chọn grace period riêng:

- Spring simple broker dùng hệ số 3 cho timeout đọc heartbeat của client.
- STOMP.js có heartbeatToleranceMultiplier; tài liệu hiện tại mặc định là 2.
- External broker có thể có timeout hoặc grace period riêng.

Đừng dùng đúng một khoảng heartbeat làm timeout cứng nếu môi trường có jitter hoặc browser background timer. Timeout quá ngắn tạo false disconnect; timeout quá dài khiến session chết được dọn dẹp chậm.

## 5. Bật heartbeat cho Spring simple broker

Spring simple broker có thể gửi heartbeat và phát hiện client không còn gửi dữ liệu. Cần cung cấp TaskScheduler để chạy heartbeat task.

Ví dụ Spring Framework 6.2:

~~~java
@Configuration
@EnableWebSocketMessageBroker
public class StompHeartbeatConfiguration
        implements WebSocketMessageBrokerConfigurer {

    @Bean
    ThreadPoolTaskScheduler stompHeartbeatScheduler() {
        ThreadPoolTaskScheduler scheduler =
            new ThreadPoolTaskScheduler();

        scheduler.setPoolSize(1);
        scheduler.setThreadNamePrefix("stomp-heartbeat-");
        scheduler.setRemoveOnCancelPolicy(true);
        return scheduler;
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.enableSimpleBroker("/topic", "/queue")
            .setHeartbeatValue(new long[] {10_000, 10_000})
            .setTaskScheduler(stompHeartbeatScheduler());

        registry.setApplicationDestinationPrefixes("/app");
    }
}
~~~

Trong setHeartbeatValue:

- Phần tử thứ nhất là khoảng thời gian server gửi heartbeat khi không có dữ liệu outbound.
- Phần tử thứ hai là khoảng thời gian server mong muốn client gửi heartbeat.
- Đơn vị là milliseconds.
- Giá trị 0 tắt heartbeat theo hướng tương ứng.

Khi gọi setTaskScheduler mà chưa đặt heartbeat value, Spring simple broker mặc định dùng [10000, 10000]. Ví dụ trên đặt cả hai giá trị tường minh để cấu hình dễ đọc và dễ vận hành.

Nếu cấu hình heartbeat khác [0,0] mà không cung cấp TaskScheduler, simple broker không thể chạy heartbeat task và sẽ báo lỗi khi khởi động. Khi không cần heartbeat, có thể giữ giá trị [0,0] và không cấu hình scheduler cho broker.

ThreadPoolTaskScheduler là Spring bean nên Spring quản lý vòng đời khởi động và dừng. Dùng scheduler chuyên cho heartbeat để dễ quan sát thread và tránh gắn công việc blocking của ứng dụng vào scheduler này.

## 6. Spring simple broker phát hiện client chết như thế nào?

Khi nhận CONNECT, simple broker đọc heartbeat mà client đã khai báo và heartbeat value phía server. Broker lưu:

- Session ID và Principal.
- Kênh gửi dữ liệu tới WebSocket session.
- Khoảng thời gian cần chờ dữ liệu từ client.
- Khoảng thời gian cần gửi dữ liệu tới client.
- Thời điểm nhận và gửi dữ liệu gần nhất.

Mọi message inbound có session ID đều cập nhật thời điểm đọc gần nhất. Vì vậy, một message nghiệp vụ hợp lệ cũng làm mới liveness; broker không bắt buộc phải nhận riêng một ký tự LF nếu client đã gửi dữ liệu STOMP khác.

Nếu đã thương lượng client → server interval, Spring simple broker dùng:

**read timeout = 3 × max(client can-send, server wants-receive)**

Hệ số 3 là grace period trong implementation của Spring simple broker, phù hợp với yêu cầu chừa sai số của STOMP specification. Đây là hành vi của Spring simple broker, không phải hệ số bắt buộc của mọi STOMP broker.

Khi heartbeat task phát hiện thời gian không có inbound data vượt read timeout, broker:

1. Xóa session khỏi danh sách session đang hoạt động của simple broker.
2. Hủy tất cả subscription thuộc session đó.
3. Gửi thông báo DISCONNECT_ACK về phía WebSocket messaging infrastructure để kết thúc session.

Ở hướng outbound, broker gửi heartbeat khi không có dữ liệu gửi cho client trong khoảng đã thương lượng. Nếu có message outbound, message đó cũng làm mới thời điểm ghi gần nhất.

Việc phát hiện này chỉ hoạt động nếu hai phía đã thương lượng heartbeat cho hướng cần theo dõi. Nếu client gửi heart-beat:0,0, hoặc server đặt giá trị nhận tương ứng bằng 0, simple broker không có read timeout cho hướng đó.

## 7. Dùng STOMP.js trong browser

Với browser client dùng @stomp/stompjs, hai thuộc tính quan trọng là:

- heartbeatOutgoing: khoảng client muốn gửi heartbeat tới server.
- heartbeatIncoming: khoảng client muốn nhận heartbeat từ server.

Ví dụ:

~~~javascript
import { Client, TickerStrategy } from "@stomp/stompjs";

const client = new Client({
    brokerURL: "wss://api.example.com/ws",
    heartbeatOutgoing: 10_000,
    heartbeatIncoming: 10_000,
    reconnectDelay: 5_000,

    onConnect: () => {
        console.log("STOMP connected");

        // onConnect chạy lại sau mỗi lần reconnect.
        client.subscribe("/topic/presence", (frame) => {
            console.log("presence:", frame.body);
        });
    },

    onWebSocketClose: (event) => {
        console.warn("WebSocket closed:", event.code, event.reason);
    },

    onStompError: (frame) => {
        console.error("STOMP error:", frame.headers["message"]);
    }
});

// Worker strategy giúp timer heartbeat ít bị throttling hơn
// khi browser tab chạy nền, nếu môi trường hỗ trợ Web Worker.
client.heartbeatStrategy = TickerStrategy.Worker;

// Có trong STOMP.js phiên bản mới (7.5+).
client.onHeartbeatLost = () => {
    console.warn("No heartbeat received from STOMP server");
};

client.activate();
~~~

heartbeatOutgoing và heartbeatIncoming là giá trị client công bố trong CONNECT. Khoảng thực tế vẫn được thương lượng với server theo công thức STOMP 1.2.

Nếu heartbeatIncoming hoặc heartbeatOutgoing bằng 0, client tắt hướng tương ứng. Không đặt giá trị quá nhỏ khi không có yêu cầu cụ thể: heartbeat tạo traffic, timer và công việc xử lý trên cả client lẫn server.

STOMP.js hỗ trợ tự reconnect qua reconnectDelay. Khi kết nối lại thành công, callback onConnect chạy lại; hãy đăng ký subscription lại ở đó. Reconnect chỉ khôi phục transport và STOMP session mới, không tự khôi phục state nghiệp vụ hoặc những message đã bỏ lỡ.

### 7.1. Browser tab nền và timer bị giới hạn

Browser có thể giảm tần suất timer khi tab ở nền hoặc thiết bị chuyển sang chế độ tiết kiệm năng lượng. Một client dùng timer thường có thể gửi heartbeat muộn hơn dự kiến và bị server xem là mất kết nối.

Với STOMP.js phiên bản hỗ trợ, có thể dùng TickerStrategy.Worker để gửi heartbeat qua Web Worker. Cách này giảm tác động của throttling timer trong tab nền, nhưng không bảo đảm kết nối luôn sống khi máy sleep hoặc mạng bị ngắt.

Nếu client bị đóng hoặc thiết bị sleep, heartbeat không thể thay thế quy trình reconnect và khôi phục trạng thái sau khi hoạt động trở lại.

## 8. Java client với WebSocketStompClient

Spring cung cấp WebSocketStompClient cho ứng dụng Java cần kết nối tới STOMP endpoint qua WebSocket.

Client cần TaskScheduler cho heartbeat scheduling và receipt tracking:

~~~java
@Bean
ThreadPoolTaskScheduler stompClientTaskScheduler() {
    ThreadPoolTaskScheduler scheduler =
        new ThreadPoolTaskScheduler();

    scheduler.setPoolSize(2);
    scheduler.setThreadNamePrefix("stomp-client-");
    return scheduler;
}

@Bean
WebSocketStompClient webSocketStompClient(
        ThreadPoolTaskScheduler stompClientTaskScheduler) {

    WebSocketStompClient client =
        new WebSocketStompClient(new StandardWebSocketClient());

    client.setTaskScheduler(stompClientTaskScheduler);
    client.setDefaultHeartbeat(new long[] {10_000, 10_000});

    return client;
}
~~~

Giá trị đầu tiên của setDefaultHeartbeat là khoảng client gửi heartbeat; giá trị thứ hai là khoảng client muốn server gửi. Khi có scheduler, Spring STOMP client mặc định ưu tiên [10000,10000]; ví dụ vẫn đặt tường minh để tránh phụ thuộc default.

WebSocketStompClient chỉ gửi heartbeat khi không có message khác được gửi. Nếu đang gửi message liên tục, dữ liệu đó được tính là hoạt động. Scheduler cũng hỗ trợ theo dõi thời hạn của RECEIPT nếu ứng dụng dùng receipt tracking.

Với code dùng Spring STOMP client và external broker relay, lưu ý rằng message gửi tới destination xử lý nội bộ như /app/... có thể không được relay tới broker. Broker vì thế có thể không thấy dữ liệu client gửi và cho rằng kết nối đã idle. Cấu hình TaskScheduler trên broker relay giúp Spring theo dõi hoạt động client và gửi heartbeat tới broker khi cần.

## 9. Heartbeat với external STOMP broker relay

Khi dùng enableStompBrokerRelay, Spring duy trì hai loại kết nối tới external broker:

- Một system TCP connection dùng cho message do server application gửi.
- Một TCP connection riêng cho mỗi WebSocket client đã kết nối.

System connection có heartbeat riêng. Spring Framework mặc định gửi và chờ heartbeat từ broker mỗi 10 giây. Nếu system connection mất, broker relay tự thử kết nối lại, mặc định mỗi 5 giây.

Ví dụ cấu hình:

~~~java
@Override
public void configureMessageBroker(MessageBrokerRegistry registry) {
    registry.enableStompBrokerRelay("/topic", "/queue")
        .setRelayHost("broker.example.com")
        .setRelayPort(61613)
        .setSystemHeartbeatSendInterval(10_000)
        .setSystemHeartbeatReceiveInterval(10_000);

    registry.setApplicationDestinationPrefixes("/app");
}
~~~

setSystemHeartbeatSendInterval và setSystemHeartbeatReceiveInterval áp dụng cho system connection giữa Spring relay và broker. Chúng không thay thế heartbeat được thương lượng cho từng client connection.

Broker relay tự phục hồi system connection, nhưng client connection không tự được khôi phục khi broker bị ngắt. Client cần nhận biết mất kết nối và tự reconnect; sau khi reconnect phải tạo lại STOMP session và subscription.

### 9.1. Theo dõi trạng thái broker relay

Spring phát BrokerAvailabilityEvent khi system connection của broker relay chuyển từ available sang unavailable hoặc ngược lại.

Service gửi message qua SimpMessagingTemplate có thể theo dõi event này để tạm dừng gửi khi broker không sẵn sàng. Dù vậy, vẫn phải xử lý MessageDeliveryException vì trạng thái có thể thay đổi ngay giữa lúc kiểm tra và gửi.

~~~java
@Component
public class BrokerAvailabilityMonitor {

    private volatile boolean brokerAvailable = false;

    @EventListener
    public void onBrokerAvailability(BrokerAvailabilityEvent event) {
        brokerAvailable = event.isBrokerAvailable();
        System.out.println("brokerAvailable=" + brokerAvailable);
    }

    public boolean isBrokerAvailable() {
        return brokerAvailable;
    }
}
~~~

Event này theo dõi system connection giữa Spring và broker. Nó không đại diện cho trạng thái của từng browser client.

### 9.2. TaskScheduler trên broker relay

Một số STOMP client, ví dụ STOMP.js, gửi heartbeat theo chu kỳ cố định. Một số client khác, như Spring WebSocketStompClient, chỉ gửi heartbeat khi không có message khác.

Message gửi tới destination nội bộ của Spring có thể được xử lý trong application và không được chuyển tiếp tới broker. Nếu broker không nhận dữ liệu nào trong khoảng heartbeat, nó có thể đánh dấu TCP connection của client là inactive dù browser vẫn đang gửi message tới Spring.

Có thể cung cấp scheduler cho broker relay:

~~~java
registry.enableStompBrokerRelay("/topic", "/queue")
    .setRelayHost("broker.example.com")
    .setRelayPort(61613)
    .setSystemHeartbeatSendInterval(10_000)
    .setSystemHeartbeatReceiveInterval(10_000)
    .setTaskScheduler(stompHeartbeatScheduler());
~~~

Scheduler này cho phép relay theo dõi số message client gửi tới broker trong từng chu kỳ heartbeat và gửi heartbeat khi cần. Hãy bật khi kiến trúc có message nội bộ không được relay và client chỉ phát heartbeat lúc idle.

## 10. Spring phát hiện session kết thúc qua event

Spring công bố các event theo vòng đời STOMP session:

| Event | Ý nghĩa |
|---|---|
| SessionConnectEvent | Nhận CONNECT từ client |
| SessionConnectedEvent | Broker đã phản hồi CONNECTED |
| SessionSubscribeEvent | Client đăng ký subscription |
| SessionUnsubscribeEvent | Client hủy subscription |
| SessionDisconnectEvent | STOMP session kết thúc |
| BrokerAvailabilityEvent | System connection của broker relay đổi trạng thái |

SessionDisconnectEvent có thể xuất hiện khi client gửi DISCONNECT hoặc khi WebSocket session đóng do transport error, heartbeat timeout hay lý do khác. Spring lưu ý event này có thể được phát hơn một lần cho một session. Code cleanup phải idempotent.

Ví dụ xóa state theo session ID:

~~~java
@Component
public class StompSessionCleanup {

    private final ConcurrentMap<String, Object> activeSessions =
        new ConcurrentHashMap<>();

    @EventListener
    public void onDisconnect(SessionDisconnectEvent event) {
        activeSessions.remove(event.getSessionId());
    }
}
~~~

remove(sessionId) an toàn khi event lặp lại. Nếu cleanup còn gọi service ngoài hoặc ghi database, hãy dùng khóa idempotency/session status để tránh xử lý cùng một disconnect nhiều lần.

Không dùng SessionDisconnectEvent để nhận thông báo cho từng message. Event này dành cho lifecycle. Nếu cần theo dõi mọi message, dùng ChannelInterceptor ở inbound/outbound channel.

## 11. Heartbeat, timeout và reverse proxy

Kết nối có thể bị proxy hoặc load balancer đóng trước khi STOMP heartbeat timeout xảy ra. Cần đối chiếu các khoảng thời gian ở nhiều tầng:

- Heartbeat client → server.
- Heartbeat server → client.
- Grace period của STOMP client.
- Timeout đọc của simple broker hoặc external broker.
- Idle timeout của reverse proxy/load balancer.
- TCP keepalive và timeout của môi trường vận hành.

Ví dụ, nếu server gửi heartbeat khoảng 10 giây một lần và proxy đóng kết nối idle sau 60 giây, proxy có đủ traffic để giữ kết nối hoạt động. Nếu heartbeat bị tắt hoặc scheduler bị treo, proxy có thể đóng socket trước khi ứng dụng phát hiện.

Một số nguyên tắc:

1. Heartbeat interval phải nhỏ hơn idle timeout của proxy với khoảng dự phòng phù hợp.
2. Timeout nhận heartbeat phải lớn hơn interval đã thương lượng và có grace period cho jitter.
3. Scheduler phải có thread hoạt động và không bị chiếm bởi công việc blocking.
4. Client reconnect cần backoff; tránh reconnect liên tục với chu kỳ quá ngắn.
5. Khi client reconnect, xác thực lại và tạo lại subscription/state cần thiết.
6. Đo số session đang mở, số disconnect, heartbeat lost, reconnect và broker availability để phát hiện lỗi theo xu hướng.

Không đặt mọi timeout bằng cùng một con số. Timeout của broker, browser và proxy phục vụ các mục đích khác nhau.

## 12. Heartbeat không phải ACK hay RECEIPT

Heartbeat chỉ cho biết có dữ liệu đang đi qua kết nối và peer có khả năng phản hồi. Nó không bảo đảm:

- Message nghiệp vụ đã được xử lý.
- Consumer đã commit database.
- Broker đã lưu message bền vững.
- Subscriber đã nhận hoặc xử lý event.
- Người dùng đang hoạt động trên giao diện.

Nếu cần xác nhận một thao tác SEND hoặc SUBSCRIBE đã được broker xử lý, dùng STOMP receipt header và nhận RECEIPT frame. Nếu cần xác nhận nghiệp vụ đã hoàn tất, định nghĩa ACK/response nghiệp vụ riêng và xử lý idempotency.

Một heartbeat thành công không thay thế retry, ACK, NACK, receipt hoặc transaction.

## 13. Kiểm thử heartbeat và phát hiện kết nối chết

Một bộ kiểm thử nên bao gồm các trường hợp:

### 13.1. Kết nối idle nhưng vẫn hoạt động

1. Kết nối client và server bằng STOMP 1.2.
2. Bật heartbeat hai chiều.
3. Không gửi message nghiệp vụ trong vài chu kỳ.
4. Xác nhận client vẫn connected và server vẫn giữ subscription.

### 13.2. Mất kết nối âm thầm

1. Kết nối client với broker.
2. Chặn hoặc ngắt traffic theo cách không gửi FIN/RST ngay lập tức (ví dụ network blackhole).
3. Chờ qua negotiated interval cộng grace period.
4. Xác nhận broker hoặc client phát hiện timeout và session được dọn dẹp.

Đóng tab hoặc gọi close() thường tạo close handshake/transport close rõ ràng; tình huống đó không kiểm tra đầy đủ khả năng phát hiện một kết nối bị đứt âm thầm.

### 13.3. Broker restart

Với broker relay, restart external broker và xác nhận:

- BrokerAvailabilityEvent chuyển sang unavailable.
- System connection được relay thử kết nối lại.
- Client connection bị mất cần client reconnect.
- Subscription được tạo lại trong callback kết nối thành công.

### 13.4. Timer và môi trường chậm

Thử browser tab nền, CPU cao, scheduler bị chậm và proxy idle timeout. Xác nhận grace period đủ lớn để tránh false disconnect nhưng vẫn dọn session chết trong thời gian chấp nhận được.

## 14. Ví dụ Java 17+ tính negotiated interval và timeout

Ví dụ standalone này minh họa công thức STOMP và grace period 3 lần của Spring simple broker. Nó không mở WebSocket hoặc kết nối broker; nó kiểm tra phép tính để người học có thể xác nhận interval trước khi cấu hình hệ thống.

**HeartbeatNegotiationDemo.java**

~~~java
public class HeartbeatNegotiationDemo {

    record Heartbeat(long canSendMs, long wantsReceiveMs) {
        Heartbeat {
            if (canSendMs < 0 || wantsReceiveMs < 0) {
                throw new IllegalArgumentException(
                    "Heartbeat values cannot be negative"
                );
            }
        }
    }

    record NegotiatedIntervals(
            long clientToServerMs,
            long serverToClientMs) {
    }

    static long negotiate(long senderCanSendMs, long receiverWantsMs) {
        if (senderCanSendMs == 0 || receiverWantsMs == 0) {
            return 0;
        }
        return Math.max(senderCanSendMs, receiverWantsMs);
    }

    static NegotiatedIntervals negotiate(
            Heartbeat client,
            Heartbeat server) {

        long clientToServer = negotiate(
            client.canSendMs(), server.wantsReceiveMs()
        );
        long serverToClient = negotiate(
            server.canSendMs(), client.wantsReceiveMs()
        );

        return new NegotiatedIntervals(
            clientToServer,
            serverToClient
        );
    }

    static long simpleBrokerReadTimeoutMs(long clientToServerMs) {
        return clientToServerMs == 0
            ? 0
            : Math.multiplyExact(clientToServerMs, 3);
    }

    static boolean isTimedOut(long elapsedMs, long timeoutMs) {
        return timeoutMs > 0 && elapsedMs > timeoutMs;
    }

    public static void main(String[] args) {
        Heartbeat client = new Heartbeat(10_000, 15_000);
        Heartbeat server = new Heartbeat(5_000, 20_000);

        NegotiatedIntervals intervals = negotiate(client, server);
        long serverReadTimeout =
            simpleBrokerReadTimeoutMs(intervals.clientToServerMs());

        System.out.println(
            "clientToServerIntervalMs=" + intervals.clientToServerMs()
        );
        System.out.println(
            "serverToClientIntervalMs=" + intervals.serverToClientMs()
        );
        System.out.println(
            "simpleBrokerClientTimeoutMs=" + serverReadTimeout
        );
        System.out.println(
            "clientTimedOutAt60000ms=" +
                isTimedOut(60_000, serverReadTimeout)
        );
        System.out.println(
            "clientTimedOutAt60001ms=" +
                isTimedOut(60_001, serverReadTimeout)
        );
    }
}
~~~

Chạy bằng Java 17:

~~~bash
javac HeartbeatNegotiationDemo.java
java HeartbeatNegotiationDemo
~~~

**Output**

~~~text
clientToServerIntervalMs=20000
serverToClientIntervalMs=15000
simpleBrokerClientTimeoutMs=60000
clientTimedOutAt60000ms=false
clientTimedOutAt60001ms=true
~~~

Giải thích:

- Client gửi được mỗi 10 giây và server muốn nhận mỗi 20 giây, nên interval client → server là 20 giây.
- Server gửi được mỗi 5 giây và client muốn nhận mỗi 15 giây, nên interval server → client là 15 giây.
- Spring simple broker dùng ba lần read interval làm timeout đọc client, nên ngưỡng trong ví dụ là 60 giây.
- Ở đúng 60.000 ms, điều kiện elapsed > timeout chưa đúng; khi vượt 60.000 ms, client được xem là timeout.

Hệ số 3 trong ví dụ mô phỏng implementation của Spring simple broker. STOMP specification chỉ yêu cầu có error margin, còn client và broker khác có thể dùng grace period khác.

## 15. Lỗi thường gặp

1. **Chỉ bật heartbeat phía client:** server và client phải thương lượng cả hai chiều; một hướng có thể bị tắt nếu giá trị phía còn lại bằng 0.
2. **Quên TaskScheduler với simple broker:** cấu hình heartbeat khác [0,0] nhưng không có scheduler sẽ khiến broker không thể chạy heartbeat task.
3. **Nhầm giá trị server heartbeat:** phần tử đầu của setHeartbeatValue là server gửi; phần tử thứ hai là server mong client gửi.
4. **Coi interval là timeout chính xác:** cần grace period; Spring simple broker dùng hệ số 3 cho read timeout.
5. **Cho rằng chỉ heartbeat mới làm mới liveness:** dữ liệu STOMP khác cũng được tính là hoạt động.
6. **Nhầm WebSocket Ping/Pong với STOMP heartbeat:** chúng ở hai tầng giao thức khác nhau.
7. **Tắt heartbeat bằng 0,0 nhưng vẫn kỳ vọng phát hiện idle:** khi hướng bị tắt, không có STOMP heartbeat timeout cho hướng đó.
8. **Proxy timeout ngắn hơn heartbeat:** proxy có thể đóng socket trước khi heartbeat tới.
9. **Dùng heartbeat quá ngắn:** tạo nhiều traffic và scheduler task, tăng tải broker cùng client.
10. **Không xử lý browser tab nền:** timer có thể bị throttle; cân nhắc Worker strategy của STOMP.js.
11. **Cho rằng broker relay tự reconnect mọi client:** relay tự reconnect system connection; client session cần reconnect ở phía client.
12. **Không theo dõi BrokerAvailabilityEvent:** ứng dụng có thể gửi vào broker trong lúc system connection unavailable.
13. **Xử lý SessionDisconnectEvent không idempotent:** event có thể lặp cho cùng session; cleanup phải an toàn khi gọi nhiều lần.
14. **Dùng heartbeat làm ACK nghiệp vụ:** heartbeat không xác nhận message đã được xử lý hoặc lưu bền vững.
15. **Không kiểm thử network blackhole:** đóng socket bình thường không mô phỏng đầy đủ kết nối bị đứt âm thầm.

## 16. Checklist triển khai

Trước khi đưa STOMP heartbeat vào production, hãy kiểm tra:

1. Client và server có dùng STOMP 1.1+ và trao đổi heart-beat trong CONNECT/CONNECTED không?
2. Hai hướng heartbeat có được thương lượng đúng theo công thức max không?
3. Spring simple broker có TaskScheduler và heartbeat value phù hợp không?
4. External broker có heartbeat timeout/grace period riêng cần cấu hình không?
5. Broker relay system heartbeat và client heartbeat có được phân biệt rõ không?
6. Client có phát hiện heartbeat lost và reconnect với backoff không?
7. Subscription được khôi phục sau reconnect chưa?
8. SessionDisconnectEvent cleanup có idempotent không?
9. BrokerAvailabilityEvent được theo dõi khi dùng external broker relay chưa?
10. Proxy/load balancer idle timeout có lớn hơn heartbeat và grace period không?
11. Scheduler, CPU, browser background timer và network jitter đã được kiểm thử chưa?
12. Metric có số session active, disconnect, heartbeat lost, reconnect và broker availability không?
13. Nghiệp vụ cần ACK/RECEIPT riêng đã được triển khai chưa?

## 17. Kết luận

STOMP heartbeat cho client và server biết kết nối còn trao đổi dữ liệu hay đã ngừng phản hồi. Hai phía khai báo khả năng gửi và nhu cầu nhận trong CONNECT/CONNECTED, sau đó thương lượng interval độc lập cho từng hướng bằng công thức max.

Trong Spring simple broker, TaskScheduler chạy heartbeat task, gửi heartbeat khi outbound idle và loại bỏ session khi client không gửi dữ liệu vượt read timeout. Với external broker relay, system connection và từng client connection có vòng đời heartbeat riêng; relay tự phục hồi system connection, còn client phải tự reconnect.

Cấu hình tốt cần thống nhất interval, grace period, proxy timeout, scheduler và reconnect. Heartbeat theo dõi liveness; ACK, RECEIPT và xác nhận nghiệp vụ vẫn cần cơ chế riêng.

## 18. Tài liệu tham khảo

- [STOMP Protocol Specification 1.2 — Heart-beating](https://stomp.github.io/stomp-specification-1.2.html#Heart-beating)
- [Spring Framework 6.2 — Simple Broker](https://docs.spring.io/spring-framework/reference/6.2/web/websocket/stomp/handle-simple-broker.html)
- [SimpleBrokerRegistration — Spring Framework 6.2.18 Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/messaging/simp/config/SimpleBrokerRegistration.html)
- [Spring Framework 6.2 — Connecting to a Broker](https://docs.spring.io/spring-framework/reference/6.2/web/websocket/stomp/handle-broker-relay-configure.html)
- [StompBrokerRelayRegistration — Spring Framework 6.2.18 Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/messaging/simp/config/StompBrokerRelayRegistration.html)
- [Spring Framework 6.2 — STOMP Application Context Events](https://docs.spring.io/spring-framework/reference/6.2/web/websocket/stomp/application-context-events.html)
- [WebSocketStompClient — Spring Framework 6.2 Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/web/socket/messaging/WebSocketStompClient.html)
- [STOMP.js Client API — Heartbeats and Reconnection](https://stomp-js.github.io/api-docs/latest/classes/Client.html)