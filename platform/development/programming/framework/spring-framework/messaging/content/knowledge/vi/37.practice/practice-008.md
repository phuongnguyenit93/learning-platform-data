# So sánh simple broker và broker relay bằng tình huống lỗi

## Mục tiêu

Sau bài này, bạn có thể chọn đúng broker cho Spring WebSocket/STOMP, giải thích dữ liệu và subscription tồn tại ở đâu, dự đoán hành vi khi ứng dụng hoặc broker gặp sự cố, và viết integration test để kiểm tra reconnect, heartbeat, message delivery và khôi phục subscription.

Trọng tâm là hai cấu hình của Spring Messaging:

- **Simple broker:** broker STOMP tích hợp trong tiến trình Spring, lưu subscription trong bộ nhớ và phát message tới các client đang kết nối.
- **Broker relay:** Spring chuyển tiếp STOMP frame qua TCP tới một message broker bên ngoài như RabbitMQ hoặc ActiveMQ; broker bên ngoài quản lý routing và subscription.

Hai lựa chọn dùng chung mô hình WebSocket/STOMP ở phía client và vẫn có thể dùng `@MessageMapping`, `SimpMessagingTemplate`, destination prefix và Spring Security. Khác biệt quan trọng nằm ở nơi quản lý subscription, độ tin cậy, khả năng mở rộng và cách phục hồi khi lỗi.

## 1. Luồng message trong Spring WebSocket/STOMP

STOMP là giao thức message dạng frame. Một client thường mở WebSocket tới endpoint Spring, sau đó gửi các frame như `CONNECT`, `SUBSCRIBE`, `SEND`, `ACK` và `DISCONNECT`.

Spring phân luồng message dựa trên destination:

- `/app/**`: chuyển tới các method `@MessageMapping` trong ứng dụng.
- `/topic/**` và `/queue/**`: thường chuyển tới broker để xử lý subscription và broadcast.
- `/user/**`: Spring chuyển destination thành địa chỉ riêng theo user/session.

Một luồng điển hình:

1. Browser mở WebSocket tới `/ws`.
2. Client gửi STOMP `CONNECT`.
3. Client gửi `SUBSCRIBE` tới `/topic/orders`.
4. Client hoặc controller gửi message tới `/app/orders`.
5. Method `@MessageMapping` xử lý và có thể gửi message tới broker bằng `SimpMessagingTemplate`.
6. Broker phát message tới các subscription phù hợp; Spring gửi frame xuống WebSocket client.

Với simple broker, Spring tự quản lý subscription và broadcast. Với broker relay, Spring chuyển frame qua TCP tới broker bên ngoài và chuyển các message broker trả về xuống WebSocket client.

## 2. Simple broker lưu và xử lý những gì?

Simple broker là broker tích hợp sẵn trong Spring. Nó nhận yêu cầu subscribe, lưu thông tin subscription trong bộ nhớ và broadcast message tới client đang kết nối có destination phù hợp.

Đặc điểm:

- Không cần cài đặt broker bên ngoài.
- Phù hợp học tập, demo, ứng dụng nhỏ hoặc luồng broadcast đơn giản.
- Hỗ trợ destination dạng path và pattern kiểu Ant.
- Có thể hỗ trợ STOMP heartbeat nếu cấu hình `TaskScheduler`.
- Chỉ hỗ trợ một tập con STOMP command; không hỗ trợ ACK, RECEIPT và một số tính năng broker nâng cao.
- Subscription ở trong bộ nhớ tiến trình; không có durable queue/message store để replay sau khi ứng dụng khởi động lại.
- Không phù hợp triển khai cluster nhiều instance vì trạng thái subscription cục bộ trên từng instance.

Simple broker không phải một hàng đợi message bền vững. Destination có tên `/queue` trong cấu hình simple broker không tự mang đầy đủ semantics của một durable queue như RabbitMQ hay ActiveMQ.

### Cấu hình simple broker

Ví dụ Spring Framework:

~~~java
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Lazy;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.scheduling.TaskScheduler;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@Configuration
@EnableWebSocketMessageBroker
class SimpleBrokerConfig implements WebSocketMessageBrokerConfigurer {

    private TaskScheduler messageBrokerTaskScheduler;

    @Autowired
    public void setMessageBrokerTaskScheduler(
            @Lazy TaskScheduler taskScheduler) {
        this.messageBrokerTaskScheduler = taskScheduler;
    }

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");

        registry.enableSimpleBroker("/topic", "/queue")
            .setHeartbeatValue(new long[] {10_000, 20_000})
            .setTaskScheduler(this.messageBrokerTaskScheduler);
    }
}
~~~

Đoạn cấu hình trên dùng broker trong bộ nhớ và bật heartbeat. `TaskScheduler` được lấy từ cấu hình WebSocket của Spring qua lazy injection để tránh vòng phụ thuộc khi khởi tạo. Có thể dùng simple broker mà không cấu hình heartbeat, nhưng khi đó không nên giả định cơ chế heartbeat của broker đã được bật.

## 3. Broker relay hoạt động như thế nào?

Broker relay là một `MessageHandler` trong Spring. Nó nhận STOMP message từ các channel nội bộ, chuyển thành frame và gửi qua TCP tới một STOMP broker bên ngoài. Các frame từ broker được chuyển ngược lại thành Spring message rồi gửi tới các WebSocket session phù hợp.

Relay duy trì hai nhóm kết nối:

1. **System connection:** một kết nối TCP dùng cho message phát sinh từ code phía server, ví dụ `SimpMessagingTemplate` được gọi từ REST controller, scheduled task hoặc service.
2. **Client connections:** một kết nối TCP riêng cho mỗi WebSocket client đang kết nối qua Spring.

System connection không dùng để nhận tất cả message của client. Mỗi client có connection riêng để gửi/nhận STOMP frame của chính session đó. Điều này giúp broker quản lý subscription và delivery theo STOMP, nhưng cũng có nghĩa số connection phía broker tăng theo số client đang kết nối.

### Cấu hình broker relay

Ví dụ với RabbitMQ đã bật STOMP plugin hoặc một broker STOMP tương thích:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.messaging.simp.config.StompBrokerRelayRegistration;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@Configuration
@EnableWebSocketMessageBroker
class StompRelayConfig implements WebSocketMessageBrokerConfigurer {

    private final Environment environment;

    StompRelayConfig(Environment environment) {
        this.environment = environment;
    }

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");

        StompBrokerRelayRegistration relay =
            registry.enableStompBrokerRelay("/topic", "/queue");

        relay.setRelayHost(environment.getRequiredProperty("stomp.relay.host"));
        relay.setRelayPort(environment.getRequiredProperty(
            "stomp.relay.port", Integer.class));

        relay.setClientLogin(environment.getRequiredProperty(
            "stomp.relay.client-login"));
        relay.setClientPasscode(environment.getRequiredProperty(
            "stomp.relay.client-passcode"));

        relay.setSystemLogin(environment.getRequiredProperty(
            "stomp.relay.system-login"));
        relay.setSystemPasscode(environment.getRequiredProperty(
            "stomp.relay.system-passcode"));

        relay.setSystemHeartbeatSendInterval(10_000);
        relay.setSystemHeartbeatReceiveInterval(10_000);
    }
}
~~~

Các property đăng nhập cần được inject từ secret manager hoặc secret store của môi trường. Không ghi password thật vào source code hoặc commit file cấu hình chứa secret.

Với relay, cần cài đặt và bật STOMP support trên broker. Nếu dùng RabbitMQ, plugin STOMP phải được bật; listener TCP mặc định của plugin là port `61613`. Port AMQP mặc định `5672` không phải STOMP listener port. Ví dụ bật plugin:

~~~bash
rabbitmq-plugins enable rabbitmq_stomp
~~~

## 4. So sánh kiến trúc và failure boundary

| Khía cạnh | Simple broker | Broker relay |
|---|---|---|
| Nơi giữ subscription | Bộ nhớ của Spring application | Broker bên ngoài |
| Nơi route/broadcast | Simple broker trong JVM | Broker STOMP qua TCP |
| Message persistence | Không có message store bền vững tích hợp | Phụ thuộc broker, destination, delivery mode và policy |
| STOMP ACK/RECEIPT | Không hỗ trợ đầy đủ | Relay chuyển tiếp tính năng broker hỗ trợ |
| Heartbeat | Có nếu cấu hình scheduler | Có trên system connection; client session cũng cần heartbeat phù hợp |
| Reconnect broker | Không có broker bên ngoài để reconnect | Relay tự reconnect system connection |
| Reconnect client | Client phải mở lại WebSocket/STOMP sau khi session mất | Client vẫn phải tự reconnect; relay không tự khôi phục client session |
| Cluster | Không chia sẻ subscription giữa các JVM | Nhiều Spring instance có thể relay tới cùng broker |
| Vận hành | Ít thành phần, đơn giản | Cần vận hành broker, STOMP listener, credentials, storage và monitoring |
| Phù hợp | Demo, broadcast đơn giản, ít instance | Production cần broker độc lập, nhiều instance, broker features và quản lý backlog |

Broker relay không tự biến mọi message thành durable. Muốn message tồn tại qua broker restart, phải cấu hình durable destination/subscription, persistent delivery và storage theo đúng semantics của broker. Đặc biệt với topic, subscription tạm thời có thể mất khi client disconnect; nếu cần backlog cho client offline, phải chọn durable subscription/queue hoặc cơ chế lưu event riêng theo broker.

## 5. Tình huống lỗi 1: broker bên ngoài bị dừng hoặc restart

Tình huống này chỉ áp dụng khi dùng broker relay vì simple broker không phụ thuộc một broker process bên ngoài.

### Với simple broker

Nếu Spring application vẫn chạy, simple broker vẫn được xem là available. Không có external broker để phát hiện restart hoặc reconnect. Message vẫn được broadcast trong phạm vi các WebSocket session đang kết nối tới instance đó.

Nếu chính Spring application dừng, simple broker cũng dừng theo. Toàn bộ subscription trong bộ nhớ bị mất; khi application khởi động lại, client phải kết nối lại và subscribe lại.

### Với broker relay

Khi broker bên ngoài mất kết nối:

1. System TCP connection của relay bị ngắt.
2. Spring phát `BrokerAvailabilityEvent` để thông báo broker không available.
3. Relay tiếp tục thử kết nối lại system connection; mặc định thử lại mỗi 5 giây.
4. Khi kết nối được thiết lập lại, Spring phát event available.
5. Message gửi từ server trong khoảng thời gian broker unavailable có thể thất bại; code cần kiểm tra trạng thái và xử lý `MessageDeliveryException`.

Điểm quan trọng: relay tự reconnect **system connection**, nhưng các connection riêng của WebSocket client không tự động được khôi phục. Khi broker restart, client thường phát hiện lỗi qua heartbeat (tài liệu Spring nêu khoảng 10 giây trong cấu hình heartbeat mặc định) và phải tự reconnect rồi subscribe lại.

Không được kết luận rằng broker đã phục hồi thì mọi browser subscription cũng đã phục hồi. Hai việc này có vòng đời khác nhau.

## 6. Tình huống lỗi 2: Spring application restart hoặc crash

| Hiện tượng | Simple broker | Broker relay |
|---|---|---|
| WebSocket session | Mất khi app process dừng | Mất khi app process dừng |
| Subscription | Mất hoàn toàn vì nằm trong JVM | Connection của client bị đóng; broker xử lý subscription theo connection và durable policy |
| Message đã gửi trước khi crash | Không có store để replay | Chỉ có thể được giữ nếu broker đã nhận và destination/persistence policy cho phép |
| Client sau restart | Mở WebSocket mới và subscribe lại | Mở WebSocket/STOMP mới và subscribe lại |
| Server-side publisher | Chỉ hoạt động khi app chạy | System connection mới được relay tạo khi app khởi động |

Broker relay giữ message broker-owned tốt hơn khi Spring application restart, nhưng WebSocket session vẫn thuộc về Spring application. Client không được tự động nối lại session cũ chỉ vì broker còn sống.

Nếu cần khôi phục message bị bỏ lỡ trong thời gian client offline:
- Dùng durable queue/subscription được broker hỗ trợ.
- Hoặc lưu event trong database/event store với sequence/cursor.
- Client gửi last-seen offset sau reconnect để server replay phần còn thiếu.
- Dùng event ID để client loại trùng khi replay.

## 7. Tình huống lỗi 3: network partition giữa Spring và broker

Một network partition có thể khiến application không kết nối được broker dù broker process vẫn đang chạy. Về phía relay, hành vi gần giống broker restart:

- Heartbeat trên system connection phát hiện kết nối không còn hoạt động.
- Relay phát trạng thái unavailable và thử reconnect.
- Khi network phục hồi, relay nối lại system connection.
- Các client connection cần được quan sát riêng; không giả định trạng thái system connection đại diện cho mọi client connection.

Có thể xảy ra trạng thái không đối xứng: system connection đã reconnect nhưng một WebSocket client vẫn đang giữ session cũ hoặc chưa nhận được heartbeat. Do đó, client phải quản lý reconnect và resubscribe độc lập.

Không nên dùng một biến `brokerAvailable=true` để khẳng định mọi client đều đã connected. Trạng thái broker và trạng thái từng WebSocket session là hai dimension khác nhau.

## 8. BrokerAvailabilityEvent và xử lý gửi message khi broker unavailable

Spring phát `BrokerAvailabilityEvent` khi trạng thái broker thay đổi. Với simple broker, broker được xem là available ngay khi ứng dụng khởi động và tiếp tục available khi ứng dụng còn chạy. Với broker relay, event phản ánh trạng thái system connection tới broker bên ngoài.

Ví dụ theo dõi trạng thái:

~~~java
import java.util.concurrent.atomic.AtomicBoolean;

import org.springframework.context.event.EventListener;
import org.springframework.messaging.simp.broker.BrokerAvailabilityEvent;
import org.springframework.stereotype.Component;

@Component
class BrokerAvailabilityMonitor {

    private final AtomicBoolean available = new AtomicBoolean();

    @EventListener
    public void onBrokerAvailability(BrokerAvailabilityEvent event) {
        available.set(event.isBrokerAvailable());
    }

    public boolean isAvailable() {
        return available.get();
    }
}
~~~

Service có thể kiểm tra trước khi broadcast:

~~~java
import org.springframework.messaging.MessageDeliveryException;
import org.springframework.messaging.simp.SimpMessagingTemplate;
import org.springframework.stereotype.Service;

@Service
class OrderBroadcastService {

    private final SimpMessagingTemplate messagingTemplate;
    private final BrokerAvailabilityMonitor brokerMonitor;

    OrderBroadcastService(
            SimpMessagingTemplate messagingTemplate,
            BrokerAvailabilityMonitor brokerMonitor) {
        this.messagingTemplate = messagingTemplate;
        this.brokerMonitor = brokerMonitor;
    }

    public void broadcast(OrderUpdate update) {
        if (!brokerMonitor.isAvailable()) {
            throw new IllegalStateException("STOMP broker is unavailable");
        }

        try {
            messagingTemplate.convertAndSend("/topic/orders", update);
        }
        catch (MessageDeliveryException ex) {
            // Ghi nhận lỗi và chuyển sang cơ chế lưu/gửi lại phù hợp.
            throw ex;
        }
    }
}
~~~

Đây là ví dụ minh họa; monitor cần được khởi tạo theo lifecycle của ứng dụng và caller phải xử lý exception phù hợp. Kiểm tra trạng thái chỉ là một guard, không loại bỏ race condition: broker có thể mất kết nối ngay sau khi kiểm tra. Vì vậy vẫn phải bắt `MessageDeliveryException`.

Không nên tự động retry message nghiệp vụ vô hạn ngay trong request thread. Nếu message phải được gửi lại sau outage, lưu event vào transactional outbox hoặc durable queue rồi publisher riêng gửi lại. Gắn event ID ổn định để tránh duplicate nếu broker đã nhận message nhưng client chưa nhận được xác nhận.

## 9. Client recovery: reconnect và resubscribe

Client STOMP cần thực hiện một state machine rõ ràng:

1. **CONNECTED:** WebSocket đã mở và STOMP `CONNECTED` đã nhận.
2. **DISCONNECTED:** WebSocket đóng hoặc heartbeat timeout.
3. **RECONNECTING:** chờ backoff rồi mở WebSocket/STOMP session mới.
4. **RESUBSCRIBING:** sau khi nhận `CONNECTED`, đăng ký lại toàn bộ destination cần thiết.
5. **SYNCHRONIZING:** gửi last-seen event ID/offset để lấy phần dữ liệu bị bỏ lỡ nếu hệ thống hỗ trợ replay.
6. **CONNECTED:** tiếp tục xử lý realtime.

Khuyến nghị:
- Dùng exponential backoff có jitter để nhiều client không reconnect đồng loạt khi broker vừa phục hồi.
- Giới hạn số lần thử hoặc có trạng thái offline rõ ràng khi outage kéo dài.
- Làm mới access token trước khi reconnect nếu phiên đăng nhập đã hết hạn.
- Subscribe lại sau STOMP `CONNECTED`, không subscribe ngay khi WebSocket TCP vừa mở.
- Dùng subscription ID mới cho session mới và quản lý callback theo lifecycle.
- Không giả định message trong lúc offline sẽ tự được gửi bù.
- Dùng sequence number/cursor hoặc event ID nếu cần phát hiện gap và duplicate.

Với relay, heartbeat giữa relay và broker không thay thế heartbeat giữa browser và Spring WebSocket endpoint. Hai đường kết nối cần được theo dõi riêng.

## 10. Tình huống lỗi 4: message được gửi đúng lúc broker mất kết nối

Đây là tình huống có kết quả không chắc chắn nhất.

Ví dụ:
1. Service gọi `SimpMessagingTemplate.convertAndSend(...)`.
2. Relay bắt đầu ghi STOMP frame lên TCP.
3. Network bị ngắt trước khi ứng dụng nhận được phản hồi.
4. Caller không biết broker đã nhận message hay chưa.

Nếu gửi lại một event có side effect, có thể tạo duplicate. Nếu không gửi lại, message có thể bị mất.

Cách xử lý:
- Với notification realtime có thể mất, ghi log/metric và chấp nhận client đồng bộ lại trạng thái khi reconnect.
- Với event nghiệp vụ quan trọng, ghi outbox trong cùng transaction với dữ liệu nghiệp vụ.
- Publisher đọc outbox và gửi lại tới broker cho tới khi nhận xác nhận phù hợp.
- Consumer dùng inbox/unique constraint để xử lý idempotent.
- Nếu broker hỗ trợ STOMP RECEIPT/ACK, dùng chúng theo semantics của broker; receipt không mặc nhiên có nghĩa consumer đã xử lý xong.

Simple broker không hỗ trợ STOMP ACK/RECEIPT như broker đầy đủ. Broker relay chuyển tiếp các tính năng mà broker bên ngoài hỗ trợ, nhưng mức bảo đảm cuối cùng vẫn phụ thuộc broker, destination và cấu hình persistence.

## 11. Tình huống lỗi 5: chạy nhiều Spring application instance

Với simple broker, mỗi JVM có bộ subscription riêng. Client A kết nối instance 1, client B kết nối instance 2; nếu message được broadcast trong simple broker của instance 1, client B không tự nhận được chỉ vì nó subscribe cùng destination ở instance 2.

Với broker relay, các Spring instance có thể cùng kết nối tới một external broker. Broker quản lý routing/subscription tập trung nên message từ instance 1 có thể được phân phối tới client đang kết nối qua instance 2, miễn là broker topology và STOMP destination được cấu hình phù hợp.

Tuy nhiên, broker relay không giải quyết mọi vấn đề cluster:
- Mỗi instance vẫn giữ các WebSocket session của riêng nó.
- User destination registry là cục bộ; nếu dùng `/user/**` xuyên nhiều instance, cần cấu hình broadcast/registry phù hợp.
- Load balancer vẫn cần cấu hình WebSocket upgrade, timeout và chiến lược phân phối phù hợp.
- Mỗi WebSocket client tạo một TCP connection tới broker qua relay; phải tính giới hạn connection và tài nguyên broker.
- Broker trở thành thành phần hạ tầng quan trọng, cần HA, monitoring, capacity planning và backup phù hợp.

## 12. Heartbeat, timeout và phát hiện lỗi

Heartbeat là frame/traffic định kỳ giúp hai phía phát hiện kết nối im lặng bất thường. Nó không phải cơ chế đảm bảo message được lưu hoặc được xử lý.

Với broker relay:
- System connection mặc định gửi và nhận heartbeat mỗi 10 giây.
- Nếu không còn kết nối tới broker, relay mặc định thử reconnect mỗi 5 giây.
- Heartbeat của client STOMP phải được cấu hình và thương lượng riêng.
- Client thường nhận ra broker không phản hồi trong khoảng 10 giây khi heartbeat được bật, nhưng thời gian thực tế phụ thuộc heartbeat negotiation, network timeout và client library.

Với simple broker:
- Cần cấu hình `TaskScheduler` để gửi/nhận STOMP heartbeat.
- Heartbeat giúp phát hiện WebSocket/STOMP session không còn hoạt động.
- Nó không biến simple broker thành broker durable hoặc clustered.

Không đặt heartbeat quá ngắn nếu mạng có jitter hoặc client chạy trên thiết bị di động. Timeout quá nhạy có thể tạo reconnect storm; timeout quá dài làm phát hiện lỗi chậm. Hãy đo RTT và network behavior trong môi trường thật để chọn giá trị.

## 13. ACK, RECEIPT và durability phụ thuộc broker

Simple broker chỉ hỗ trợ một subset STOMP command và không hỗ trợ ACK/RECEIPT. Broker relay chuyển tiếp frame tới external broker, nên khả năng ACK, NACK, RECEIPT, persistence và durable subscription phụ thuộc STOMP implementation của broker.

Ví dụ RabbitMQ:
- Cần bật plugin `rabbitmq_stomp`.
- Plugin hỗ trợ STOMP 1.0, 1.1 và 1.2 cùng một số extension.
- Subscription có thể dùng các acknowledgement mode `auto`, `client`, `client-individual`.
- Persistent message có thể được yêu cầu bằng header `persistent:true`.
- Semantics của `NACK`, requeue và dead-letter phụ thuộc cấu hình broker.

Đừng suy rộng behavior của RabbitMQ sang ActiveMQ hoặc broker khác. Khi đổi broker, cần chạy lại contract/integration test cho ACK, RECEIPT, durable subscription, queue naming và dead-letter policy.

## 14. Kiểm thử failure injection

Unit test có thể kiểm tra logic xử lý event và listener của `BrokerAvailabilityEvent`, nhưng không đủ để chứng minh reconnect TCP, heartbeat, STOMP session hoặc persistence của broker. Các hành vi này cần integration test với broker thật.

### Test matrix

| Kịch bản | Cấu hình simple broker | Cấu hình broker relay | Assertion chính |
|---|---|---|---|
| Spring app restart | Subscription trong JVM bị mất | WebSocket session mất; broker ngoài vẫn chạy | Client reconnect và subscribe lại |
| Broker restart | Không áp dụng external broker | System connection unavailable rồi reconnect | Có event unavailable/available; relay phục hồi |
| Network partition | Kiểm tra WebSocket/instance riêng | System connection mất; relay retry | Client tự reconnect và resubscribe |
| Gửi khi broker unavailable | Simple broker vẫn chạy nếu app còn sống | Có thể ném MessageDeliveryException | Caller không giả định message đã được lưu |
| Client disconnect | Subscription/session của client kết thúc | Client TCP connection kết thúc | Session cleanup idempotent |
| Hai app instance | Subscription không chia sẻ | Cùng broker nhận message liên instance | Client ở cả hai instance nhận đúng event |
| ACK/RECEIPT | Không hỗ trợ đầy đủ | Theo broker STOMP implementation | Kiểm tra đúng semantics provider |
| Broker giữ message | Không có durable store | Theo persistent delivery/durable destination | Message offline được nhận lại nếu cấu hình cho phép |

### Dùng RabbitMQ làm broker test

Một integration test với RabbitMQ cần:
1. Khởi động RabbitMQ container hoặc test broker riêng.
2. Bật STOMP plugin bằng `rabbitmq-plugins enable rabbitmq_stomp`.
3. Expose STOMP TCP port (mặc định 61613).
4. Khởi động Spring application với `enableStompBrokerRelay`.
5. Kết nối hai STOMP client và subscribe destination chung.
6. Gửi message từ client hoặc `SimpMessagingTemplate`, xác nhận client nhận được.
7. Dừng broker, chờ `BrokerAvailabilityEvent(false)`.
8. Khởi động broker lại, chờ relay reconnect và `BrokerAvailabilityEvent(true)`.
9. Xác minh browser/client tự reconnect và subscribe lại; không chỉ kiểm tra system connection.
10. Nếu cần kiểm tra message offline, tạo durable destination/subscription theo đúng RabbitMQ STOMP semantics và xác minh backlog.

Có thể dùng Testcontainers cho lifecycle broker và Toxiproxy hoặc network rule để tạo partition. Dùng latch, Awaitility hoặc polling có timeout thay vì `Thread.sleep` cố định.

### Các assertion quan trọng

- Simple broker không mất subscription khi chỉ có external broker bị dừng vì không có external broker trong kiến trúc này.
- Khi Spring process bị dừng, simple broker mất trạng thái subscription.
- Relay phát `BrokerAvailabilityEvent` khi system connection đổi trạng thái.
- Relay system connection được reconnect; client session vẫn cần reconnect độc lập.
- Client sau reconnect phải gửi `SUBSCRIBE` lại.
- Message được gửi trong outage phải có kết quả được xử lý rõ ràng: retry/outbox, bỏ qua có chủ đích hoặc đồng bộ lại qua cursor.
- Disconnect event có thể xuất hiện nhiều lần; logic cleanup phải idempotent.
- Durable message/subscription chỉ được xác nhận khi broker thực sự lưu và replay theo cấu hình đã chọn.

## 15. Quan sát và vận hành production

Theo dõi các tín hiệu riêng biệt:

**Ở Spring application**
- Trạng thái `BrokerAvailabilityEvent`.
- Số WebSocket session connected/disconnected.
- Số STOMP CONNECT/SUBSCRIBE/DISCONNECT.
- Số `MessageDeliveryException`.
- Số lần client reconnect và resubscribe.
- Latency của message channel và số message bị từ chối.

**Ở external broker**
- TCP/STOMP connection count.
- Số subscription/consumer.
- Queue depth, message ready/unacknowledged nếu broker hỗ trợ.
- Publish/consume rate.
- Redelivery, ACK/NACK và DLQ.
- Disk/memory watermark và cluster health.

Log nên có WebSocket session ID, user ID đã được xác thực, destination, correlation/event ID và trạng thái kết nối. Tránh ghi token, passcode hoặc toàn bộ payload nhạy cảm.

Với broker relay, mỗi client có một TCP connection riêng tới broker; hãy capacity plan theo số client đồng thời, heartbeat, connection limit, file descriptor và network bandwidth. Với simple broker, capacity nằm trong JVM của Spring application và phụ thuộc số subscription, số WebSocket session, message size và outbound throughput.

## 16. Bảo mật khi dùng broker relay

Spring broker relay cấu hình STOMP `login` và `passcode` cho các connection mà nó tạo tới broker. Relay luôn đặt các header này trong CONNECT frame gửi thay client; thông tin login/passcode mà browser gửi trong STOMP CONNECT bị bỏ qua.

Vì vậy:
- Bảo vệ WebSocket endpoint bằng HTTP authentication và TLS.
- Dùng Spring Security để xác thực user và authorize destination/message.
- Dùng tài khoản broker riêng cho system connection và client connection; chỉ cấp quyền cần thiết.
- Lưu credentials bằng secret manager.
- Không cho browser biết system credentials.
- Kiểm soát subscription vào destination riêng tư và `/user/**`.
- Kiểm thử việc user không được subscribe/send tới destination của user khác.

Broker authentication không thay thế authorization ở tầng ứng dụng. Nếu mọi browser connection đều được relay dùng cùng một broker credential, broker có thể chỉ thấy một service identity; Spring vẫn cần bảo vệ quyền truy cập theo user đã xác thực.

## 17. Chọn simple broker hay broker relay?

| Yêu cầu | Lựa chọn phù hợp |
|---|---|
| Demo, học STOMP, broadcast đơn giản | Simple broker |
| Chỉ một Spring instance, không cần ACK/RECEIPT | Có thể dùng simple broker |
| Nhiều Spring instance cùng phát/nhận realtime | Broker relay |
| Cần broker queue, durable subscription, ACK/NACK | Broker relay với broker hỗ trợ các tính năng đó |
| Cần message tồn tại khi client offline | Broker relay + durable destination/subscription hoặc event store |
| Cần quản lý backlog, DLQ và broker monitoring | Broker relay |
| Muốn ít thành phần vận hành và chấp nhận state in-memory | Simple broker |
| Cần khả năng scale độc lập giữa WebSocket app và messaging | Broker relay |

Broker relay tăng khả năng mở rộng và cung cấp broker features, nhưng thêm một hạ tầng cần triển khai, bảo mật, backup và monitoring. Chọn relay khi yêu cầu reliability, clustering hoặc backlog thực sự cần đến; không dùng nó chỉ vì tên gọi “production”.

## 18. Lỗi thường gặp

- **Cho rằng relay tự reconnect mọi browser:** relay tự reconnect system connection; client session phải được client phục hồi.
- **Chỉ chờ BrokerAvailabilityEvent rồi coi mọi client đã online:** event phản ánh system connection, không phải trạng thái từng WebSocket client.
- **Cho rằng simple broker có durable queue:** subscription và broadcast state nằm trong bộ nhớ JVM.
- **Cho rằng broker relay tự đảm bảo message không mất:** phải cấu hình persistence, destination, ACK/RECEIPT và broker storage.
- **Gửi message khi broker unavailable mà không bắt exception:** server có thể gặp MessageDeliveryException.
- **Tự retry mọi message không có event ID:** có thể tạo duplicate nếu broker đã nhận message trước khi connection mất.
- **Chỉ reconnect WebSocket nhưng không subscribe lại:** session STOMP mới không tự khôi phục subscription cũ.
- **Dùng ACK/RECEIPT với simple broker:** simple broker không hỗ trợ đầy đủ các command này.
- **Dùng broker relay nhưng không bật STOMP plugin:** TCP connection tới STOMP port sẽ thất bại dù AMQP port vẫn hoạt động.
- **Dùng cùng credentials mặc định guest/guest ở production:** tạo rủi ro truy cập và thường bị giới hạn theo host/provider.
- **Dùng simple broker ở nhiều instance rồi kỳ vọng broadcast liên node:** mỗi JVM giữ subscription riêng.
- **Không xử lý duplicate SessionDisconnectEvent:** cleanup có thể chạy nhiều lần và gây lỗi trạng thái.

## 19. Checklist trước khi phát hành

- [ ] Đã chọn simple broker hay broker relay theo yêu cầu reliability và scale.
- [ ] Nếu dùng relay, broker đã bật STOMP listener và đúng host/port.
- [ ] Đã cấu hình system/client credentials bằng secret store.
- [ ] Đã bật heartbeat phù hợp ở relay và STOMP client.
- [ ] Có xử lý `BrokerAvailabilityEvent` và `MessageDeliveryException`.
- [ ] Client tự reconnect, xác thực lại và resubscribe sau STOMP CONNECTED.
- [ ] Có event ID/cursor nếu cần phát hiện gap và duplicate.
- [ ] Đã kiểm tra durable subscription/persistent message theo broker thực tế.
- [ ] Đã test broker restart và network partition.
- [ ] Đã test Spring app restart và client reconnect.
- [ ] Đã test nhiều Spring instance nếu triển khai cluster.
- [ ] Đã xác minh ACK/RECEIPT theo broker STOMP implementation.
- [ ] Có metrics cho broker availability, session count, reconnect, queue depth và DLQ.
- [ ] Đã bảo vệ WebSocket endpoint và authorization theo destination.
- [ ] Đã capacity plan TCP connection, heartbeat và broker resources.

## Tài liệu tham khảo

- [Spring Framework — Simple Broker](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-simple-broker.html): subscription trong bộ nhớ, destination pattern và heartbeat.
- [Spring Framework — External Broker](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-broker-relay.html): simple broker limitations và cấu hình broker relay.
- [Spring Framework — Connecting to a Broker](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-broker-relay-configure.html): system/client TCP connections, credentials, heartbeat và reconnect interval.
- [Spring Framework — ApplicationContext Events](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/application-context-events.html): BrokerAvailabilityEvent, session lifecycle events và client reconnect behavior.
- [Spring Framework — Flow of Messages](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/message-flow.html): message channel và flow khi dùng simple broker hoặc broker relay.
- [Spring Framework — BrokerAvailabilityEvent Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/simp/broker/BrokerAvailabilityEvent.html): `isBrokerAvailable()` và ý nghĩa event.
- [RabbitMQ — STOMP Plugin](https://www.rabbitmq.com/docs/stomp): bật STOMP plugin, listener port, ACK/NACK và persistent message.
