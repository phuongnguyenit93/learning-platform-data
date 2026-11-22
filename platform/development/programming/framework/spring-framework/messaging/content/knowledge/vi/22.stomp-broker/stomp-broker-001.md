# Simple broker trong bộ nhớ và quản lý subscription

## Mục tiêu

Spring Framework cung cấp một simple message broker tích hợp cho ứng dụng WebSocket/STOMP. Broker nhận các yêu cầu SUBSCRIBE, lưu thông tin subscription trong bộ nhớ và phát message đến các client đang kết nối có destination khớp.

Sau bài này, bạn có thể:

- Cấu hình simple broker với các destination prefix như /topic và /queue.
- Giải thích vòng đời SUBSCRIBE, UNSUBSCRIBE và DISCONNECT.
- Hiểu cách broker lưu subscription, tìm subscriber phù hợp và gửi MESSAGE.
- Dùng destination pattern, heartbeat và selector khi phù hợp.
- Theo dõi vòng đời session bằng các ApplicationContext event.
- Nhận biết giới hạn về lưu trữ, ACK, receipt và clustering để chọn broker phù hợp.

## 1. Simple broker là gì?

Simple broker là bộ xử lý message tích hợp trong Spring Messaging. Khi ứng dụng bật STOMP message broker, Spring có thể tạo SimpleBrokerMessageHandler để xử lý message broker mà không cần cài đặt một máy chủ broker bên ngoài.

Simple broker thực hiện ba việc chính:

1. Nhận frame SUBSCRIBE từ client và đăng ký subscription trong bộ nhớ.
2. Nhận message có destination thuộc prefix mà broker quản lý.
3. Tìm những subscription có destination khớp và gửi một frame MESSAGE đến từng client tương ứng.

Ví dụ, một ứng dụng cấu hình broker prefix /topic và /queue. Client A và B cùng subscribe /topic/news. Khi ứng dụng phát message đến /topic/news, cả A và B đều nhận được message nếu các kết nối còn hoạt động.

Simple broker phù hợp để phát triển, thử nghiệm, ứng dụng nội bộ hoặc hệ thống có quy mô vừa phải khi yêu cầu message broker còn đơn giản. Nó không phải một message broker độc lập có lưu trữ bền vững, quản lý hàng đợi phân tán hoặc khả năng clustering.

## 2. Vị trí của simple broker trong luồng STOMP

WebSocket tạo kết nối hai chiều giữa trình duyệt và server. STOMP định nghĩa các frame thông điệp chạy trên kết nối đó, chẳng hạn CONNECT, CONNECTED, SEND, SUBSCRIBE, UNSUBSCRIBE, MESSAGE và DISCONNECT.

Spring tổ chức luồng xử lý bằng các channel chính:

- clientInboundChannel: nhận message từ các WebSocket session.
- brokerChannel: chuyển message từ ứng dụng đến message broker.
- clientOutboundChannel: chuyển message từ server về các WebSocket session.

Với cấu hình thường gặp, destination được chia thành hai nhóm:

| Nhóm | Ví dụ | Thành phần xử lý |
| --- | --- | --- |
| Application destination | /app/orders.create | Phương thức @MessageMapping |
| Broker destination | /topic/orders, /queue/alerts | Simple broker |

Cấu hình application prefix /app dành cho message đi vào logic ứng dụng. Các prefix /topic và /queue được giao cho simple broker xử lý.

Luồng một message broadcast:

1. Client kết nối đến endpoint WebSocket, ví dụ /ws, rồi gửi STOMP CONNECT.
2. Server trả CONNECTED sau khi phiên STOMP được thiết lập.
3. Client gửi SUBSCRIBE với destination /topic/news và một subscription id.
4. Simple broker ghi nhận subscription gắn với session hiện tại.
5. Ứng dụng hoặc một controller gửi message đến /topic/news.
6. Broker tìm các subscription phù hợp với destination.
7. Với mỗi subscription phù hợp, Spring tạo message gửi về session tương ứng qua clientOutboundChannel.
8. Client nhận frame MESSAGE và xử lý payload.

Điểm quan trọng: client có thể subscribe destination broker mà không cần gọi @MessageMapping. Controller chỉ tham gia khi destination được định tuyến vào application prefix hoặc khi ứng dụng chủ động gọi API gửi message.

## 3. Cấu hình simple broker

Một cấu hình cơ bản:

~~~java
package com.example.messaging;

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
        registry.enableSimpleBroker("/topic", "/queue");
    }
}
~~~

Ý nghĩa:

- @EnableWebSocketMessageBroker bật hạ tầng WebSocket/STOMP có message broker.
- addEndpoint("/ws") đăng ký endpoint HTTP handshake để client mở kết nối WebSocket.
- setApplicationDestinationPrefixes("/app") dành destination bắt đầu bằng /app cho controller.
- enableSimpleBroker("/topic", "/queue") đăng ký simple broker để xử lý các destination bắt đầu bằng /topic hoặc /queue.

Một số ví dụ destination:

| Destination | Mục đích thường gặp |
| --- | --- |
| /topic/news | Broadcast tin tức đến mọi subscriber phù hợp |
| /topic/rooms/engineering | Broadcast trong một phòng |
| /queue/notifications | Tên destination thường dùng cho thông báo |
| /app/orders.create | Gửi yêu cầu để ứng dụng xử lý |

Tên prefix là quy ước định tuyến. Đặc biệt, trong simple broker, /queue không tự biến thành hàng đợi point-to-point. Broker vẫn phát message đến mọi subscription khớp destination. Nếu A và B cùng subscribe /queue/notifications, cả hai đều có thể nhận cùng một message.

Không nên dùng cùng một prefix cho application controller và broker nếu không có chủ đích. Khi hai thành phần cùng xử lý một destination, message có thể được xử lý song song và không có bảo đảm thành phần nào xử lý trước.

## 4. Broker quản lý subscription như thế nào?

Một STOMP SUBSCRIBE thường chứa ít nhất destination và id. Subscription id phải phân biệt được trong phạm vi một session. Client có thể đăng ký nhiều subscription trên cùng một kết nối, kể cả nhiều subscription cùng destination, miễn là id khác nhau.

Về mặt khái niệm, registry quản lý các thông tin:

- Session id: định danh kết nối STOMP của client.
- Subscription id: định danh một subscription trong session.
- Destination: nơi client muốn nhận message.
- Thông tin bổ sung: header hoặc selector nếu được cấu hình.

Spring sử dụng abstraction SubscriptionRegistry để lưu và tra cứu subscription. Cấu hình mặc định dùng DefaultSubscriptionRegistry. Registry lưu trạng thái trong bộ nhớ của tiến trình Spring và dùng PathMatcher để so khớp destination.

Ví dụ một session có thể đăng ký:

| Session | Subscription id | Destination |
| --- | --- | --- |
| session-A | sub-1 | /topic/news |
| session-A | sub-2 | /topic/orders |
| session-A | sub-3 | /topic/news |
| session-B | sub-1 | /topic/news |

Khi broker phát message đến /topic/news, cả ba subscription sub-1, sub-3 của session-A và sub-1 của session-B đều khớp. Vì session-A có hai subscription khác nhau cùng destination, client có thể nhận một message cho mỗi subscription đó. Nếu chỉ muốn một handler nhận message, tránh đăng ký lặp destination ngoài ý muốn.

### Vòng đời subscription

| Hành động | Frame STOMP | Kết quả ở server |
| --- | --- | --- |
| Bắt đầu kết nối | CONNECT | Tạo phiên STOMP sau khi handshake và xác thực thành công |
| Đăng ký nhận message | SUBSCRIBE | Lưu subscription id và destination trong registry |
| Hủy một subscription | UNSUBSCRIBE | Xóa subscription theo id trong session |
| Đóng phiên | DISCONNECT hoặc WebSocket close | Xóa toàn bộ subscription thuộc session |

Khi client gọi UNSUBSCRIBE, client phải dùng đúng id của subscription cần hủy. Khi kết nối bị đóng, Spring tự loại bỏ các subscription gắn với session đó. Client reconnect sẽ tạo session mới và cần đăng ký lại các subscription.

Simple broker không lưu subscription bền vững để khôi phục sau khi ứng dụng khởi động lại. Nó cũng không giữ message để giao lại cho client đang offline. Vì vậy, subscription và việc nhận message chỉ có hiệu lực trong vòng đời kết nối hiện tại.

## 5. Destination matching và wildcard

Simple broker dùng PathMatcher để so sánh destination của message với destination trong subscription. Mặc định, Spring dùng AntPathMatcher với dấu gạch chéo / làm dấu phân cách.

Các ký tự pattern thường dùng:

| Pattern | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| * | Khớp phần ký tự trong một path segment | /topic/rooms/* |
| ** | Khớp nhiều path segment | /topic/** |
| ? | Khớp một ký tự trong segment | /topic/room? |
| {name} | Biến đường dẫn trong mapping của controller | /app/rooms/{roomId} |

Ví dụ:

- Subscription /topic/rooms/* có thể khớp /topic/rooms/engineering.
- Subscription /topic/** có thể khớp các destination sâu hơn dưới /topic.
- Pattern wildcard cần được dùng có chủ đích vì một subscription quá rộng có thể nhận nhiều message hơn dự kiến.

Biến {roomId} thường được dùng trong mapping @MessageMapping và lấy bằng @DestinationVariable. Khi dùng pattern cho broker subscription, mục tiêu là khớp destination để phân phối message; không nên nhầm cơ chế này với việc bind tham số controller.

### Dùng dấu chấm làm separator

Một số hệ thống dùng destination dạng event.order.created thay vì /event/order/created. Có thể đổi PathMatcher:

~~~java
import org.springframework.util.AntPathMatcher;

@Override
public void configureMessageBroker(MessageBrokerRegistry registry) {
    registry.setPathMatcher(new AntPathMatcher("."));
    registry.setApplicationDestinationPrefixes("/app");
    registry.enableSimpleBroker("/topic", "/queue");
}
~~~

Khi đổi separator, hãy dùng nhất quán trong controller mapping và broker subscription. Với simple broker, PathMatcher được cấu hình cũng ảnh hưởng đến cách broker so destination của message với pattern trong subscription. Với external broker, quy tắc destination còn phụ thuộc broker bên ngoài.

## 6. Gửi message đến các subscription

Ứng dụng có thể phát message đến broker bằng SimpMessagingTemplate:

~~~java
package com.example.messaging;

import org.springframework.messaging.simp.SimpMessagingTemplate;
import org.springframework.stereotype.Service;

@Service
public class AnnouncementPublisher {

    private final SimpMessagingTemplate messagingTemplate;

    public AnnouncementPublisher(SimpMessagingTemplate messagingTemplate) {
        this.messagingTemplate = messagingTemplate;
    }

    public void publish(Announcement announcement) {
        messagingTemplate.convertAndSend("/topic/announcements", announcement);
    }
}
~~~

Khi convertAndSend được gọi, Spring chuyển payload thành message và gửi qua brokerChannel. Simple broker tìm subscription phù hợp rồi phát message đến các client.

Có thể phát từ controller, service, listener hoặc tác vụ nền. Không cần một controller STOMP nếu message được tạo từ một sự kiện nghiệp vụ khác, ví dụ đơn hàng được xác nhận hoặc trạng thái công việc thay đổi.

Message chỉ được gửi đến subscription phù hợp đang tồn tại tại thời điểm broker xử lý message. Client không kết nối hoặc chưa subscribe sẽ không nhận lại message sau đó.

## 7. Hủy subscription từ client

Ví dụ dùng thư viện JavaScript @stomp/stompjs:

~~~javascript
import { Client } from "@stomp/stompjs";

const client = new Client({
  brokerURL: "ws://localhost:8080/ws",
  reconnectDelay: 5000
});

let newsSubscription;

client.onConnect = () => {
  newsSubscription = client.subscribe("/topic/news", (frame) => {
    const news = JSON.parse(frame.body);
    console.log(news.title);
  });
};

client.activate();

// Khi không cần nhận tin nữa:
newsSubscription?.unsubscribe();

// Khi đóng trang hoặc rời màn hình:
await client.deactivate();
~~~

client.subscribe trả về đối tượng Subscription. Gọi unsubscribe() trên đối tượng đó sẽ gửi UNSUBSCRIBE tương ứng. Gọi deactivate() sẽ đóng client và kết thúc kết nối; server sẽ dọn các subscription còn lại thuộc session khi phiên kết thúc.

Với reconnect, callback onConnect được gọi lại khi kết nối mới được thiết lập. Hãy đăng ký lại các destination cần thiết trong callback này. Không giữ giả định rằng subscription của session cũ vẫn tồn tại trong session mới.

Một lỗi thường gặp là gọi subscribe nhiều lần mỗi khi component UI render mà không hủy subscription cũ. Điều này tạo nhiều subscription trùng lặp, khiến một message được xử lý nhiều lần. Hãy quản lý subscription handle theo vòng đời component hoặc màn hình.

## 8. Theo dõi vòng đời session và subscription

Spring phát các ApplicationContext event hữu ích cho việc theo dõi kết nối và subscription:

| Event | Thời điểm |
| --- | --- |
| SessionConnectEvent | Nhận được STOMP CONNECT mới |
| SessionConnectedEvent | Broker đã gửi CONNECTED; phiên STOMP được xem là thiết lập |
| SessionSubscribeEvent | Nhận được STOMP SUBSCRIBE |
| SessionUnsubscribeEvent | Nhận được STOMP UNSUBSCRIBE |
| SessionDisconnectEvent | Phiên STOMP kết thúc |

Ví dụ listener ghi log:

~~~java
package com.example.messaging;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.event.EventListener;
import org.springframework.messaging.simp.stomp.StompHeaderAccessor;
import org.springframework.stereotype.Component;
import org.springframework.web.socket.messaging.SessionDisconnectEvent;
import org.springframework.web.socket.messaging.SessionSubscribeEvent;
import org.springframework.web.socket.messaging.SessionUnsubscribeEvent;

@Component
public class StompSessionEvents {

    private static final Logger log =
            LoggerFactory.getLogger(StompSessionEvents.class);

    @EventListener
    public void onSubscribe(SessionSubscribeEvent event) {
        StompHeaderAccessor headers =
                StompHeaderAccessor.wrap(event.getMessage());

        log.info("SUBSCRIBE session={}, id={}, destination={}",
                headers.getSessionId(),
                headers.getSubscriptionId(),
                headers.getDestination());
    }

    @EventListener
    public void onUnsubscribe(SessionUnsubscribeEvent event) {
        StompHeaderAccessor headers =
                StompHeaderAccessor.wrap(event.getMessage());

        log.info("UNSUBSCRIBE session={}, id={}",
                headers.getSessionId(),
                headers.getSubscriptionId());
    }

    @EventListener
    public void onDisconnect(SessionDisconnectEvent event) {
        log.info("DISCONNECT session={}, user={}",
                event.getSessionId(),
                event.getUser());
    }
}
~~~

Các event này hữu ích để ghi log, đếm kết nối, cập nhật trạng thái online hoặc giải phóng tài nguyên nghiệp vụ gắn với session. SessionDisconnectEvent đôi khi được phát nhiều lần cho cùng một session, vì vậy logic cleanup phải idempotent: chạy lặp lại vẫn cho cùng kết quả và không gây lỗi.

SessionSubscribeEvent cho biết Spring đã nhận frame SUBSCRIBE. Nó không phải STOMP RECEIPT xác nhận rằng broker đã hoàn tất đăng ký và sẵn sàng phát message. Simple broker không hỗ trợ receipt. Nếu một quy trình cần biết chính xác khi brokerChannel xử lý xong subscription, hãy dùng cơ chế đồng bộ ở server, chẳng hạn ExecutorChannelInterceptor.afterMessageHandled trên brokerChannel.

Không nên tự viết một registry khác để thay thế registry nội bộ của broker chỉ nhằm theo dõi subscription. Nếu cần trạng thái người dùng, có thể xem xét SimpUserRegistry hoặc lưu dữ liệu hiện diện ở tầng nghiệp vụ riêng.

## 9. Heartbeat để phát hiện kết nối mất hoạt động

WebSocket là kết nối dài hạn. Proxy, mạng di động hoặc máy khách có thể mất kết nối mà không đóng phiên một cách rõ ràng. STOMP heartbeat giúp hai phía phát hiện kết nối không còn hoạt động.

Simple broker hỗ trợ heartbeat khi được cấu hình TaskScheduler. Ví dụ dưới đây sử dụng scheduler được khai báo trong cấu hình WebSocket tích hợp của Spring:

~~~java
package com.example.messaging;

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
public class HeartbeatWebSocketConfig
        implements WebSocketMessageBrokerConfigurer {

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

Hai giá trị heartbeat tính bằng mili giây:

- Giá trị thứ nhất là khoảng thời gian server gửi heartbeat khi không có dữ liệu gửi đi.
- Giá trị thứ hai là khoảng thời gian client nên gửi heartbeat.
- Giá trị 0 nghĩa là không yêu cầu heartbeat theo hướng tương ứng.

Ví dụ 10.000 và 20.000 biểu thị các khoảng 10 giây và 20 giây trước khi STOMP thương lượng heartbeat với client. Đây không phải cam kết rằng mọi message đều được gửi đúng vào từng mốc thời gian; heartbeat là tín hiệu kiểm tra hoạt động khi không có dữ liệu khác.

Khi dùng TaskScheduler được khai báo sẵn trong cấu hình WebSocket tích hợp, Spring hướng dẫn inject qua setter với @Lazy để tránh vòng phụ thuộc giữa cấu hình WebSocket và cấu hình ứng dụng. Có thể khai báo TaskScheduler riêng nếu ứng dụng cần kiểm soát pool hoặc lịch chạy.

Client STOMP cũng phải cấu hình heartbeat tương thích. Ví dụ với @stomp/stompjs:

~~~javascript
const client = new Client({
  brokerURL: "ws://localhost:8080/ws",
  heartbeatIncoming: 10000,
  heartbeatOutgoing: 10000,
  reconnectDelay: 5000
});
~~~

Heartbeat không thay thế reconnect logic. Khi kết nối bị đóng, client cần kết nối lại và subscribe lại các destination cần thiết.

## 10. Selector để lọc message theo header

Ngoài việc khớp destination, DefaultSubscriptionRegistry có thể lọc message dựa trên biểu thức Spring Expression Language (SpEL) trong subscription header. Tính năng này gọi là selector.

Từ Spring Framework 6.1, selector bị tắt mặc định. Có thể bật bằng cách cấu hình tên header:

~~~java
@Override
public void configureMessageBroker(MessageBrokerRegistry registry) {
    registry.setApplicationDestinationPrefixes("/app");

    registry.enableSimpleBroker("/topic")
            .setSelectorHeaderName("selector");
}
~~~

Khi selector được bật, client có thể gửi header selector cùng SUBSCRIBE. Ví dụ về mặt ý tưởng:

~~~javascript
const subscription = client.subscribe(
  "/topic/orders",
  (frame) => console.log(frame.body),
  { selector: "headers.region == 'north'" }
);
~~~

Biểu thức được đánh giá trên header của message, không phải trên JSON payload. Message chỉ được gửi đến subscription nếu destination khớp và selector trả về true.

Selector là cơ chế lọc bổ sung, không phải hệ thống phân quyền. Không dùng selector để thay thế xác thực người dùng hoặc kiểm tra quyền truy cập destination. Chỉ bật tính năng này khi có nhu cầu rõ ràng và kiểm soát được biểu thức mà client gửi lên.

## 11. Thứ tự xử lý message

Các channel xử lý message có thể dùng thread pool. Do đó, message inbound hoặc outbound có thể được xử lý trên nhiều thread và thứ tự quan sát ở client có thể khác thứ tự message được gửi vào channel.

Nếu ứng dụng cần giữ thứ tự publish cho từng client session, cấu hình:

~~~java
@Override
public void configureMessageBroker(MessageBrokerRegistry registry) {
    registry.setPreservePublishOrder(true);
    registry.enableSimpleBroker("/topic", "/queue");
    registry.setApplicationDestinationPrefixes("/app");
}
~~~

Nếu cần giữ thứ tự nhận message từ cùng một client session, cấu hình ở StompEndpointRegistry:

~~~java
@Override
public void registerStompEndpoints(StompEndpointRegistry registry) {
    registry.setPreserveReceiveOrder(true);
    registry.addEndpoint("/ws");
}
~~~

Hai tùy chọn này có chi phí hiệu năng. Chỉ bật khi thứ tự là yêu cầu nghiệp vụ thực sự, ví dụ các sự kiện thay đổi trạng thái phải được xử lý theo thứ tự. Nếu message độc lập, xử lý song song thường đem lại thông lượng tốt hơn.

## 12. Giới hạn của simple broker

Simple broker có một số giới hạn quan trọng:

- **Chỉ lưu trong bộ nhớ:** subscription mất khi session kết thúc hoặc ứng dụng khởi động lại.
- **Không lưu message cho client offline:** client phải kết nối và subscribe trước khi message được phát.
- **Không hỗ trợ đầy đủ STOMP:** simple broker không hỗ trợ ACK, RECEIPT và một số tính năng khác của STOMP.
- **Không có clustering:** mỗi instance Spring giữ registry subscription riêng. Một message đến instance này không tự động được phân phối đến subscription trên instance khác.
- **Không phải hàng đợi point-to-point:** prefix /queue chỉ là destination prefix; simple broker vẫn broadcast đến mọi subscription khớp.
- **Không có bảo đảm thứ tự mặc định:** channel có thể xử lý message song song; bật preserve order khi cần.

Simple broker phù hợp khi ứng dụng cần broadcast thời gian thực đơn giản và các client đang kết nối có thể nhận trực tiếp. Nếu cần ACK, receipt, durable queue, competing consumers, lưu trữ message hoặc nhiều instance ứng dụng, nên dùng broker chuyên dụng.

## 13. Khi nào chuyển sang external broker?

Spring hỗ trợ STOMP broker relay để chuyển tiếp message đến một broker bên ngoài như RabbitMQ hoặc ActiveMQ. Cấu hình cơ bản:

~~~java
@Override
public void configureMessageBroker(MessageBrokerRegistry registry) {
    registry.enableStompBrokerRelay("/topic", "/queue");
    registry.setApplicationDestinationPrefixes("/app");
}
~~~

Broker relay là một MessageHandler kết nối TCP đến broker bên ngoài, chuyển message của Spring đến broker và chuyển message nhận được từ broker về các WebSocket session. Broker bên ngoài chịu trách nhiệm lưu trữ, định tuyến và quản lý subscription theo tính năng của chính nó.

| Nhu cầu | Simple broker | External broker qua relay |
| --- | --- | --- |
| Không cần cài broker riêng | Phù hợp | Cần broker bên ngoài |
| Broadcast cho client đang kết nối | Có | Có |
| Lưu subscription trong bộ nhớ | Có | Do broker quản lý |
| STOMP ACK/RECEIPT | Không hỗ trợ đầy đủ | Tùy broker |
| Durable queue và message persistence | Không | Tùy broker |
| Clustering và phân phối nhiều node | Không phù hợp | Hỗ trợ qua cấu hình broker |
| Vận hành đơn giản | Dễ hơn | Cần vận hành thêm hạ tầng |

Chuyển sang broker relay không tự động giải quyết mọi yêu cầu về độ tin cậy. Cần cấu hình queue, exchange, retention, quyền truy cập, heartbeat, reconnect và chính sách retry theo broker cụ thể.

Khi dùng broker relay, Spring phát BrokerAvailabilityEvent khi trạng thái kết nối với broker thay đổi. Ứng dụng dùng SimpMessagingTemplate nên theo dõi trạng thái này và vẫn cần xử lý MessageDeliveryException khi gửi message.

## 14. Bảo mật và vận hành subscription

Simple broker chỉ định tuyến message theo destination và subscription. Nó không tự xác định người dùng có quyền subscribe hoặc publish đến destination nào.

Các điểm cần kiểm soát:

- **Xác thực session:** xác thực người dùng tại WebSocket handshake hoặc tích hợp cơ chế token phù hợp. Gắn Principal đã xác thực với session.
- **Phân quyền SEND:** kiểm tra người dùng có quyền gửi message đến application destination hay không.
- **Phân quyền SUBSCRIBE:** kiểm tra quyền đọc destination. Một người dùng không được subscribe topic riêng tư chỉ vì biết tên topic.
- **Không tin dữ liệu client tự khai báo:** userId, role hoặc tenant trong payload không chứng minh danh tính. Dùng security context và kiểm tra quyền ở server.
- **Giới hạn subscription:** tránh cho một session đăng ký số lượng lớn destination hoặc wildcard quá rộng.
- **Giới hạn kích thước message:** cấu hình giới hạn transport và kiểm tra payload để giảm nguy cơ tiêu thụ bộ nhớ quá mức.
- **Quan sát vòng đời:** ghi nhận số session, subscription, disconnect bất thường và lỗi gửi message; tránh log token, cookie hoặc payload nhạy cảm.

Với ứng dụng nhiều tenant hoặc nhiều phòng, cần kiểm tra quyền ở cả hai thời điểm: khi client gửi message và khi client đăng ký nhận message. Không nên xem tên destination là bí mật hoặc là cơ chế bảo mật.

## 15. Kiểm thử simple broker

Một integration test nên kiểm tra cả vòng đời subscription và luồng message:

1. Khởi động ứng dụng với WebSocket/STOMP endpoint và simple broker.
2. Kết nối hai STOMP client riêng biệt.
3. Client A và B subscribe cùng một destination.
4. Ứng dụng phát message đến destination đó.
5. Xác nhận cả A và B nhận payload.
6. Client A gửi UNSUBSCRIBE.
7. Phát message tiếp theo và xác nhận A không nhận message mới trong khi B vẫn nhận.
8. Đóng session B rồi xác nhận subscription của B không còn được sử dụng.

Cũng nên kiểm thử các tình huống:

- Hai subscription khác id nhưng cùng destination.
- Destination không có subscriber.
- Wildcard khớp nhiều destination.
- Client reconnect và đăng ký lại subscription.
- WebSocket đóng đột ngột.
- Payload có header selector nếu ứng dụng bật selector.
- Người dùng không đủ quyền SUBSCRIBE một destination.

Simple broker không hỗ trợ STOMP RECEIPT, vì vậy không thể dựa vào RECEIPT để xác nhận subscription đã sẵn sàng. Nếu integration test cần đồng bộ chính xác, có thể cài ExecutorChannelInterceptor trên brokerChannel và dùng afterMessageHandled để biết khi message SUBSCRIBE đã được xử lý xong. SessionSubscribeEvent chỉ thông báo Spring đã nhận SUBSCRIBE, không thay thế xác nhận hoàn tất xử lý.

## 16. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Client không nhận message | Subscribe sai destination hoặc prefix chưa được cấu hình | Đối chiếu destination của SUBSCRIBE với broker prefix và destination được publish. |
| Nhiều callback chạy cho một message | Client subscribe trùng destination nhiều lần | Kiểm tra subscription id và đảm bảo unsubscribe khi component bị hủy. |
| Client A và B đều nhận message ở /queue | Simple broker broadcast đến mọi subscription phù hợp | Nhớ rằng /queue trong simple broker không có semantics competing-consumer. |
| Message mất khi client offline | Simple broker không lưu message để phát lại | Dùng external broker có persistence hoặc lưu sự kiện trong database. |
| Subscription biến mất sau reconnect | Kết nối mới tạo session mới | Đăng ký lại trong callback onConnect. |
| Wildcard nhận quá nhiều message | Pattern quá rộng | Thu hẹp pattern và kiểm tra quyền SUBSCRIBE. |
| Heartbeat không hoạt động | Chưa cấu hình TaskScheduler hoặc heartbeat phía client không tương thích | Kiểm tra TaskScheduler, heartbeatValue và client heartbeat settings. |
| Event disconnect xử lý trùng | SessionDisconnectEvent có thể xuất hiện nhiều lần | Làm logic cleanup idempotent. |
| Thứ tự message thay đổi | Channel xử lý message song song | Bật preserve publish/receive order khi nghiệp vụ cần. |
| Nhiều instance không thấy subscription của nhau | Mỗi simple broker chỉ giữ trạng thái trong instance hiện tại | Dùng external broker relay cho phân phối nhiều node. |

## 17. Ghi nhớ

- Simple broker là broker tích hợp, lưu subscription trong bộ nhớ và broadcast đến các client đang kết nối có destination khớp.
- SUBSCRIBE tạo subscription; UNSUBSCRIBE xóa subscription theo id; khi session đóng, Spring xóa subscription của session đó.
- DefaultSubscriptionRegistry quản lý subscription và dùng PathMatcher để khớp destination.
- /topic và /queue là quy ước prefix. Với simple broker, cả hai đều broadcast đến các subscription phù hợp.
- Heartbeat cần TaskScheduler; selector là tính năng lọc theo header và bị tắt mặc định từ Spring Framework 6.1.
- Simple broker không hỗ trợ đầy đủ ACK/RECEIPT, không lưu message offline và không phù hợp cho clustering.
- Khi cần durable queue, message persistence, competing consumers hoặc phân phối nhiều node, hãy cân nhắc external broker relay.

## Tài liệu tham khảo

- [Spring Framework — Simple Broker](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-simple-broker.html)
- [Spring Framework — External Broker](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-broker-relay.html)
- [Spring Framework — Events](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/application-context-events.html)
- [Spring Framework — Dots as Separators](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/destination-separator.html)
- [Spring Framework — Order of Messages](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/ordered-messages.html)
- [DefaultSubscriptionRegistry Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/simp/broker/DefaultSubscriptionRegistry.html)
- [SimpleBrokerMessageHandler Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/simp/broker/SimpleBrokerMessageHandler.html)
- [SimpleBrokerRegistration Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/simp/config/SimpleBrokerRegistration.html)

