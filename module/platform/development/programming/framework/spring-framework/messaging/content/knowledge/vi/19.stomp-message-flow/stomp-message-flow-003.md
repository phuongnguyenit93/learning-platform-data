# configureMessageBroker và các tiền tố đích

Trong Spring STOMP over WebSocket, client gửi frame có header destination. Spring cần xác định frame đó dành cho method xử lý của ứng dụng, dành cho message broker hay dành cho một user cụ thể. Phương thức configureMessageBroker trong WebSocketMessageBrokerConfigurer cấu hình quy tắc định tuyến này thông qua MessageBrokerRegistry.

Điểm quan trọng là mỗi loại tiền tố có một vai trò riêng:

- Application destination prefix định tuyến message từ client đến các method @MessageMapping hoặc @SubscribeMapping.
- Broker destination prefix định tuyến message và subscription đến simple broker tích hợp hoặc STOMP broker relay.
- User destination prefix biểu diễn destination riêng cho user/session; Spring phân giải nó thành destination thực tế phù hợp với các session của user.

Destination prefix là quy ước định tuyến ở tầng STOMP. Nó không phải URL dùng để mở WebSocket và cũng không tự cấp quyền truy cập cho client.

## 1. configureMessageBroker nằm ở đâu trong cấu hình STOMP?

Một cấu hình STOMP thường triển khai WebSocketMessageBrokerConfigurer và bật hạ tầng bằng @EnableWebSocketMessageBroker.

Có hai phần cấu hình cần phân biệt:

- registerStompEndpoints đăng ký URL handshake mà browser hoặc client dùng để mở WebSocket.
- configureMessageBroker cấu hình cách xử lý destination trong STOMP SEND, SUBSCRIBE và message gửi từ ứng dụng.

Ví dụ:

~~~java
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
        registry.setUserDestinationPrefix("/user/");
    }
}
~~~

Trong ví dụ:

- /ws là URL endpoint cho HTTP Upgrade/WebSocket handshake.
- /app là tiền tố cho message gửi vào các method xử lý của ứng dụng.
- /topic và /queue là tiền tố destination do simple broker xử lý.
- /user/ là tiền tố logic cho destination hướng tới user cụ thể.

Client kết nối tới /ws. Sau khi STOMP session được thiết lập, client mới gửi SEND hoặc SUBSCRIBE frame với destination tương ứng.

Không thêm /ws vào destination STOMP. Endpoint URL và destination là hai không gian tên khác nhau.

## 2. Application destination prefix

### 2.1. setApplicationDestinationPrefixes dùng để làm gì?

setApplicationDestinationPrefixes khai báo một hoặc nhiều tiền tố dành cho message cần được xử lý bởi các method có @MessageMapping hoặc @SubscribeMapping.

Ví dụ:

~~~java
registry.setApplicationDestinationPrefixes("/app");
~~~

Client gửi STOMP SEND tới:

~~~text
SEND
destination:/app/chat.send

{"text":"Hello"}
~~~

Spring nhận ra destination bắt đầu bằng /app, bỏ phần tiền tố này rồi dùng phần còn lại để tìm method mapping. Vì vậy, controller khai báo:

~~~java
@Controller
public class ChatController {

    @MessageMapping("/chat.send")
    @SendTo("/topic/chat")
    public ChatMessage send(ChatMessage message) {
        return message;
    }
}
~~~

Method dùng /chat.send, không dùng /app/chat.send. Phần /app đã được loại bỏ trước khi tra cứu mapping.

### 2.2. Có thể khai báo nhiều application prefix

MessageBrokerRegistry cho phép truyền nhiều tiền tố:

~~~java
registry.setApplicationDestinationPrefixes(
        "/app",
        "/api"
);
~~~

Khi đó các destination /app/... và /api/... đều có thể được định tuyến tới annotated controller.

Spring tự thêm dấu / ở cuối tiền tố nếu chuỗi được cấu hình chưa có dấu này. Điều đó giúp so khớp theo ranh giới segment: tiền tố /app không nên được hiểu là khớp với /application.

Chỉ khai báo nhiều prefix khi ứng dụng có lý do rõ ràng, chẳng hạn hai nhóm client hoặc hai quy ước API cần duy trì. Dùng một prefix chung thường giúp client dễ hiểu hơn.

### 2.3. Nếu không cấu hình application prefix

Theo mặc định, không có application destination prefix thì mọi destination đều có thể đủ điều kiện để được xét bởi annotated method handler. Khi ứng dụng đồng thời bật broker, việc phân chia rõ /app với /topic hoặc /queue giúp tránh các destination bị xử lý không đúng tầng.

Với ứng dụng STOMP thông thường, nên đặt application prefix tường minh và không dùng trùng prefix với broker destination.

## 3. Broker destination prefix

### 3.1. enableSimpleBroker

enableSimpleBroker bật simple message broker tích hợp trong Spring và khai báo các destination prefix mà broker này xử lý.

~~~java
registry.enableSimpleBroker("/topic", "/queue");
~~~

Simple broker lưu subscription trong bộ nhớ và gửi message tới các client đang kết nối có subscription khớp destination.

Ví dụ client đăng ký:

~~~text
SUBSCRIBE
destination:/topic/prices
id:prices-sub
~~~

Một thành phần gửi message đến /topic/prices. Simple broker tìm các subscription khớp destination rồi phát message tới những client đó.

Các tiền tố /topic và /queue là quy ước phổ biến. Với simple broker, cả hai đều được xử lý theo cơ chế subscription và broadcast của broker tích hợp. Chỉ đặt tên destination là /queue không tạo ra semantics queue cạnh tranh consumer như một JMS queue hoặc queue thực của broker ngoài.

### 3.2. Chọn prefix phù hợp

Một quy ước thường dùng:

| Prefix | Ý định thường gặp | Ví dụ |
|---|---|---|
| /app | Client gửi command/event vào ứng dụng | /app/orders.create |
| /topic | Phát dữ liệu cho các subscriber phù hợp | /topic/prices |
| /queue | Destination dạng hàng đợi theo quy ước broker | /queue/orders |
| /user/ | Destination logic riêng cho user/session | /user/queue/notifications |

Các tên trên là convention, không phải từ khóa bắt buộc của STOMP. Broker ngoài có thể định nghĩa semantics khác cho /queue và /topic; hãy kiểm tra cấu hình và tài liệu broker đang sử dụng.

### 3.3. Prefix broker không phải mapping controller

Nếu client gửi SEND tới /topic/prices, message được định tuyến tới broker theo prefix đã khai báo. Nó không được gọi method @MessageMapping("/prices") chỉ vì tên phần cuối giống nhau.

Nếu muốn ứng dụng xử lý message trước, client phải gửi tới application prefix, ví dụ /app/prices.update. Nếu muốn broker phân phối trực tiếp, client dùng broker prefix như /topic/prices.

Sự tách biệt này giúp xác định rõ message nào là command đi vào logic nghiệp vụ và message nào là subscription/broadcast.

## 4. Phân biệt SEND và SUBSCRIBE khi định tuyến

STOMP dùng các frame khác nhau cho việc gửi message và đăng ký nhận message.

- SEND đưa payload từ client vào một destination.
- SUBSCRIBE đăng ký nhận các message được gửi đến destination.
- MESSAGE là frame broker gửi lại cho subscriber.
- UNSUBSCRIBE hủy đăng ký.

Với application prefix, SEND thường được xử lý bởi @MessageMapping. SUBSCRIBE tới application destination có thể được xử lý bằng @SubscribeMapping.

Với broker prefix, SUBSCRIBE đăng ký với broker. SEND tới broker prefix có thể được broker chuyển đến các subscriber phù hợp, tùy semantics của broker.

Ví dụ:

~~~text
Client A                         Spring
   |                               |
   | SEND /app/chat.send           |
   |------------------------------>|
   |                               | bỏ /app
   |                               | gọi @MessageMapping("/chat.send")
   |                               |
   |<------ MESSAGE /topic/chat ---|
   |                               |
Client B                           |
   |                               |
   | SUBSCRIBE /topic/chat -------->|
   |                               | broker lưu subscription
   |<------ MESSAGE /topic/chat ---|
~~~

Đây là luồng khái quát khi controller gửi kết quả tới /topic/chat và broker phát cho các subscriber.

## 5. Mapping destination với @MessageMapping

@MessageMapping ánh xạ STOMP message tới method controller theo destination sau khi application prefix đã được bỏ.

Ví dụ:

~~~java
@Controller
public class OrderController {

    @MessageMapping("/orders.create")
    @SendTo("/topic/orders")
    public OrderCreated create(CreateOrderCommand command) {
        return orderService.create(command);
    }
}
~~~

Client gửi tới /app/orders.create. Spring bỏ /app rồi tìm mapping /orders.create.

Có thể đặt prefix chung ở cấp class:

~~~java
@Controller
@MessageMapping("/orders")
public class OrderController {

    @MessageMapping("/create")
    @SendTo("/topic/orders")
    public OrderCreated create(CreateOrderCommand command) {
        return orderService.create(command);
    }

    @MessageMapping("/{orderId}/cancel")
    @SendTo("/topic/orders")
    public OrderCancelled cancel(
            @DestinationVariable String orderId) {

        return orderService.cancel(orderId);
    }
}
~~~

Trong ví dụ, các mapping kết hợp thành /orders/create và /orders/{orderId}/cancel. Client tương ứng gửi /app/orders/create hoặc /app/orders/123/cancel.

Mặc định, Spring sử dụng Ant-style path matching, hỗ trợ pattern và biến đường dẫn. @DestinationVariable lấy giá trị từ phần biến trong destination.

### 5.1. Destination của response

Nếu method @MessageMapping trả về payload, Spring chuyển payload thành message gửi tới broker. Có thể dùng @SendTo để khai báo destination rõ ràng:

~~~java
@MessageMapping("/chat.send")
@SendTo("/topic/chat")
public ChatMessage send(ChatMessage message) {
    return message;
}
~~~

Nếu không chỉ định @SendTo hoặc @SendToUser, Spring có quy tắc destination mặc định cho response dựa trên destination đầu vào, thường thay application prefix bằng /topic. Dùng @SendTo khi contract của ứng dụng cần destination ổn định và dễ đọc.

Có thể gửi tới nhiều destination bằng cách khai báo nhiều giá trị trong @SendTo nếu use case cần broadcast tới nhiều nhóm subscriber.

## 6. @SubscribeMapping và application prefix

@SubscribeMapping xử lý STOMP SUBSCRIBE frame có destination thuộc application prefix.

Ví dụ:

~~~java
@Controller
public class DashboardController {

    @SubscribeMapping("/dashboard.initial")
    public DashboardSnapshot initialSnapshot() {
        return dashboardService.currentSnapshot();
    }
}
~~~

Client đăng ký:

~~~text
SUBSCRIBE
destination:/app/dashboard.initial
id:dashboard-init
~~~

Spring bỏ /app, gọi method /dashboard.initial rồi gửi kết quả trực tiếp về client đã gửi SUBSCRIBE. Theo mặc định, response này không đi qua broker và không được broadcast cho mọi subscriber.

Nếu muốn kết quả của @SubscribeMapping đi qua broker, có thể kết hợp @SendTo:

~~~java
@SubscribeMapping("/dashboard.initial")
@SendTo("/topic/dashboard")
public DashboardSnapshot initialSnapshot() {
    return dashboardService.currentSnapshot();
}
~~~

Cách dùng này phù hợp khi client cần lấy snapshot ban đầu lúc đăng ký. Các cập nhật tiếp theo có thể được phát tới /topic/dashboard.

Không dùng @SubscribeMapping như một thay thế cho subscription broker lâu dài. Nó thường trả lời một lần cho thao tác đăng ký; việc nhận update liên tục vẫn cần subscription tới broker destination.

## 7. User destination prefix

### 7.1. User destination là destination logic

Spring hỗ trợ destination hướng tới một user cụ thể thông qua UserDestinationMessageHandler. Prefix mặc định là /user/.

Client có thể đăng ký:

~~~text
SUBSCRIBE
destination:/user/queue/notifications
id:notifications-sub
~~~

Spring phân giải destination logic này thành destination thực tế duy nhất theo user/session. Nhờ vậy, nhiều user có thể cùng đăng ký tên logic /user/queue/notifications mà không nhận message của nhau.

User destination đặc biệt hữu ích cho thông báo cá nhân, trạng thái tác vụ hoặc kết quả chỉ dành cho người dùng đã đăng nhập.

### 7.2. Cấu hình user prefix

Có thể dùng mặc định hoặc đặt tường minh:

~~~java
registry.setUserDestinationPrefix("/user/");
~~~

Nếu thay prefix, client và server phải dùng cùng convention mới. Không cấu hình broker xử lý trực tiếp prefix /user/ trước khi Spring có cơ hội phân giải user destination.

Cấu hình đầy đủ:

~~~java
@Override
public void configureMessageBroker(MessageBrokerRegistry registry) {
    registry.setApplicationDestinationPrefixes("/app");
    registry.enableSimpleBroker("/topic", "/queue");
    registry.setUserDestinationPrefix("/user/");
}
~~~

### 7.3. Gửi message tới một user

Server có thể gửi qua SimpMessagingTemplate:

~~~java
@Service
public class NotificationService {

    private final SimpMessagingTemplate messagingTemplate;

    public NotificationService(SimpMessagingTemplate messagingTemplate) {
        this.messagingTemplate = messagingTemplate;
    }

    public void notifyUser(
            String username,
            Notification notification) {

        messagingTemplate.convertAndSendToUser(
                username,
                "/queue/notifications",
                notification
        );
    }
}
~~~

username cần khớp với Principal.getName() của user đã xác thực. Destination truyền cho convertAndSendToUser là phần đích phía sau user prefix, thường bắt đầu bằng /queue; không thêm /user/{username} vào tham số destination này.

Spring tìm các session đang gắn với user và phân giải destination thành các destination cụ thể cho những session đó.

### 7.4. Gửi tới user từ controller

Có thể dùng @SendToUser:

~~~java
@MessageMapping("/profile.refresh")
@SendToUser("/queue/profile")
public ProfileView refreshProfile(Principal principal) {
    return profileService.load(principal.getName());
}
~~~

@SendToUser định tuyến response tới user gửi message. Với nhiều session của cùng user, thuộc tính broadcast quyết định việc gửi tới tất cả session hay chỉ session phát sinh request; kiểm tra mặc định và đặt broadcast=false nếu chỉ muốn trả về session hiện tại.

Không tin username do client tự truyền trong payload để quyết định người nhận. Dùng Principal đã được xác thực ở server và kiểm tra quyền truy cập.

## 8. Simple broker và STOMP broker relay

### 8.1. Simple broker

Simple broker được bật bằng:

~~~java
registry.enableSimpleBroker("/topic", "/queue");
~~~

Đặc điểm:

- Tích hợp trong Spring application.
- Lưu subscription trong memory.
- Phát message tới các client đang kết nối có destination khớp.
- Dễ cấu hình và phù hợp cho demo, phát triển hoặc ứng dụng đơn giản.
- Chỉ hỗ trợ một tập con của STOMP; không cung cấp đầy đủ các tính năng như acknowledgement và receipt.
- Không phù hợp cho clustering hoặc nhu cầu message persistence ở broker.

Nếu ứng dụng cần durable queue/topic, acknowledgement, receipt, broker clustering hoặc quản trị backlog, simple broker không đáp ứng đầy đủ.

### 8.2. STOMP broker relay

Broker relay chuyển tiếp STOMP frame từ Spring tới một message broker ngoài có hỗ trợ STOMP, chẳng hạn broker được triển khai với STOMP plugin/protocol adapter.

Ví dụ:

~~~java
@Override
public void configureMessageBroker(MessageBrokerRegistry registry) {
    registry.setApplicationDestinationPrefixes("/app");

    registry.enableStompBrokerRelay("/topic", "/queue")
            .setRelayHost("broker.internal")
            .setRelayPort(61613);
}
~~~

Trong cấu hình này:

- /app vẫn định tuyến message tới controller của Spring.
- /topic và /queue được chuyển tiếp tới broker ngoài.
- Broker ngoài xử lý subscription, queue/topic và các semantics theo sản phẩm/cấu hình của nó.

Broker relay tạo TCP connection tới broker và chuyển tiếp message giữa Spring với broker. Relay có system connection và các client connection được quản lý theo cấu hình.

Thông tin đăng nhập, virtual host, heartbeat và địa chỉ broker cần được cấu hình theo môi trường. Không hard-code credential trong source control; bind từ secret manager hoặc cấu hình bảo mật của deployment.

### 8.3. Chọn loại broker

| Nhu cầu | Simple broker | Broker relay |
|---|---|---|
| Cấu hình ban đầu đơn giản | Phù hợp | Cần broker ngoài |
| Subscription trong memory | Có | Broker quản lý |
| STOMP ACK/receipt đầy đủ | Không | Tùy broker |
| Durable queue/topic | Không cung cấp đầy đủ | Tùy broker |
| Clustering và quản trị backlog | Không phù hợp | Broker có thể hỗ trợ |
| Vận hành độc lập với Spring process | Không | Có |

Khi dùng relay, prefix truyền vào enableStompBrokerRelay phải phù hợp với destination mà broker ngoài hỗ trợ. /queue và /topic không phải cú pháp bắt buộc cho mọi broker; một số broker có cách đặt destination riêng.

## 9. Phân biệt endpoint, application prefix, broker prefix và user prefix

Bốn loại tên thường bị nhầm:

| Thành phần | Ví dụ | Vai trò |
|---|---|---|
| WebSocket endpoint | /ws | URL mở kết nối HTTP Upgrade |
| Application prefix | /app | Định tuyến SEND/SUBSCRIBE tới annotated controller |
| Broker prefix | /topic, /queue | Định tuyến destination tới message broker |
| User prefix | /user/ | Định tuyến logic tới user/session cụ thể |

Một client có thể:

1. Kết nối tới /ws.
2. Gửi SEND tới /app/orders.create.
3. Đăng ký SUBSCRIBE tới /topic/orders.
4. Đăng ký thêm /user/queue/notifications để nhận thông báo riêng.

Việc dùng chung một chuỗi cho endpoint và destination không làm chúng trở thành cùng một route. Hãy đặt tên rõ ràng và giữ contract client/server nhất quán.

## 10. Prefix matching và PathMatcher

### 10.1. Application prefix được so khớp theo segment

Spring xử lý application prefix theo ranh giới đường dẫn. Ví dụ /app được cấu hình thành tiền tố ứng dụng thì /app/orders.create phù hợp; /application/orders.create không nên được coi là destination cùng prefix.

Khi tiền tố không có dấu / cuối, Spring tự thêm dấu này trong cấu hình application destination prefixes.

Không nên tạo nhiều prefix chồng lấn hoặc gần giống nhau nếu không có lý do, vì chúng làm route khó đọc và khó kiểm tra.

### 10.2. PathMatcher mặc định

Các mapping @MessageMapping mặc định dùng AntPathMatcher với dấu / làm separator.

Ví dụ:

~~~java
@MessageMapping("/stocks/{symbol}")
public void updateStock(
        @DestinationVariable String symbol,
        StockUpdate update) {
    stockService.update(symbol, update);
}
~~~

Destination /app/stocks/ACME sau khi bỏ /app sẽ khớp /stocks/{symbol}, và symbol nhận giá trị ACME.

Có thể dùng wildcard như /stocks/** hoặc template variable như /stocks/{symbol}. Cần kiểm thử các pattern có khả năng chồng lấn để bảo đảm chỉ method mong muốn được chọn.

### 10.3. Dùng dấu chấm làm separator

Một số hệ thống messaging thích convention dạng dot-separated, ví dụ stock.price.ACME. Có thể cấu hình PathMatcher:

~~~java
registry.setPathMatcher(new AntPathMatcher("."));
~~~

Khi thay separator, cập nhật nhất quán mapping ở controller và quy ước destination của client. Đặc biệt, kiểm tra cách simple broker match subscription pattern và cách broker ngoài diễn giải destination. Không đổi separator chỉ ở một phía.

## 11. Một cấu hình hoàn chỉnh với simple broker

Ví dụ sau gồm endpoint, application prefix, broker prefix và user destination prefix:

~~~java
@Configuration
@EnableWebSocketMessageBroker
public class StompWebSocketConfiguration
        implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");

        registry.enableSimpleBroker("/topic", "/queue");

        registry.setUserDestinationPrefix("/user/");
    }
}
~~~

Controller nhận command và phát kết quả:

~~~java
@Controller
public class ChatController {

    @MessageMapping("/chat.send")
    @SendTo("/topic/chat")
    public ChatMessage send(ChatMessage message) {
        return message;
    }
}
~~~

Client STOMP:

~~~javascript
const socket = new WebSocket("ws://localhost:8080/ws");
const client = Stomp.over(socket);

client.connect({}, () => {
    client.subscribe("/topic/chat", frame => {
        console.log("Received:", frame.body);
    });

    client.send(
        "/app/chat.send",
        {"content-type": "application/json"},
        JSON.stringify({text: "Hello Spring"})
    );
});
~~~

Đây là đoạn minh họa dùng STOMP.js. API cụ thể của client library có thể khác giữa các phiên bản. Phía Spring vẫn nhận SEND /app/chat.send, gọi method /chat.send và gửi response tới /topic/chat.

## 12. Tùy chọn cấu hình MessageBrokerRegistry

Ngoài ba nhóm prefix, MessageBrokerRegistry còn có một số tùy chọn hữu ích.

### 12.1. Giữ thứ tự publish

~~~java
registry.setPreservePublishOrder(true);
~~~

Tùy chọn này yêu cầu message gửi tới client trong cùng session được publish theo thứ tự. Nó có overhead xử lý, vì vậy chỉ bật khi nghiệp vụ cần thứ tự ổn định.

Thứ tự xử lý message inbound và thứ tự publish outbound là hai vấn đề riêng. Nếu cần giữ thứ tự message client gửi vào, hãy kiểm tra cấu hình preserveReceiveOrder tại STOMP endpoint registry của phiên bản Spring đang dùng.

### 12.2. Giới hạn cache mapping

~~~java
registry.setCacheLimit(1024);
~~~

Cache limit điều chỉnh giới hạn cache cho việc đăng ký/mapping destination. Giá trị cần dựa trên số lượng pattern và destination thực tế; không tăng tùy tiện nếu chưa quan sát bộ nhớ và hit rate.

### 12.3. Tùy chỉnh broker channel

configureBrokerChannel cho phép cấu hình channel gửi message từ ứng dụng tới broker. Mặc định, việc gửi qua broker channel là synchronous để code gửi có thể nhận exception nếu không gửi được. Có thể cấu hình task executor nếu cần xử lý bất đồng bộ, nhưng phải đánh giá ảnh hưởng đến thứ tự, backpressure và cách exception được quan sát.

Các tùy chọn nâng cao nên được bật theo số liệu vận hành và yêu cầu rõ ràng, không cần thêm vào mọi ứng dụng.

## 13. Quyền truy cập destination

Prefix chỉ quyết định đường đi của message. Nó không phải cơ chế authorization.

Ví dụ, việc client gửi tới /app/admin.delete không có nghĩa client được phép xóa dữ liệu. Method controller phải kiểm tra Principal, quyền và dữ liệu đầu vào; cấu hình Spring Security messaging phải kiểm soát ai được SEND hoặc SUBSCRIBE vào destination nào.

Cần xác định riêng:

- Client nào được SEND tới /app/**.
- Client nào được SUBSCRIBE tới /topic/**.
- Destination nào chỉ dành cho user đã xác thực.
- User nào được phép gửi tới destination của user khác.
- Broker relay dùng credential nào để kết nối broker.
- Broker ACL nào giới hạn quyền publish/subscribe khi dùng broker ngoài.

Đặc biệt với user destination, không lấy username tùy ý từ payload để gửi message. Dùng Principal đã xác thực và kiểm tra quyền trước khi gửi.

## 14. Lỗi thường gặp khi cấu hình prefix

### 14.1. Đưa /app vào @MessageMapping

Nếu cấu hình application prefix là /app, Spring bỏ prefix trước khi lookup. Mapping đúng là /chat.send; khai báo /app/chat.send có thể khiến method không khớp.

### 14.2. Client gửi tới sai prefix

SEND tới /topic/chat được xử lý bởi broker; nó không gọi controller @MessageMapping. Nếu muốn gọi controller, gửi tới /app/chat.send.

### 14.3. Nhầm endpoint URL với destination

Client phải kết nối tới endpoint như /ws rồi mới gửi STOMP destination như /app/orders.create. Gửi HTTP request tới /app/orders.create không tạo STOMP message.

### 14.4. Nghĩ /queue của simple broker có semantics queue thực

Simple broker broadcast tới mọi subscriber khớp destination. Prefix /queue chỉ là tên route trong cấu hình simple broker. Dùng broker ngoài nếu cần queue semantics thực, persistence hoặc competing consumers.

### 14.5. Quên cấu hình broker prefix

Nếu client SUBSCRIBE /topic/prices nhưng simple broker chỉ nhận /queue, subscription không được xử lý theo broker route mong muốn.

### 14.6. Cấu hình user prefix trùng với broker prefix

Nếu broker nhận trực tiếp /user/**, message có thể đi sai tầng trước khi UserDestinationMessageHandler phân giải destination. Đảm bảo user prefix được xử lý như logical destination và đích sau khi resolve nằm trong broker prefix hợp lệ.

### 14.7. Broker ngoài không hỗ trợ prefix đã khai báo

Broker relay chỉ chuyển frame. Destination phải tuân theo cú pháp và cấu hình của broker. Kiểm tra plugin STOMP, virtual host, queue/topic và ACL.

### 14.8. Dùng simple broker cho yêu cầu ACK hoặc durable subscription

Simple broker không có đầy đủ tính năng của broker ngoài. Chuyển sang broker relay nếu cần ACK/receipt, persistence, durable subscription hoặc clustering.

### 14.9. Không kiểm tra route của @SubscribeMapping

@SubscribeMapping xử lý SUBSCRIBE tới application prefix và thường trả response trực tiếp cho client. Nếu mong response được broadcast qua broker, cần @SendTo hoặc thiết kế route rõ ràng.

### 14.10. Coi prefix là ranh giới bảo mật

Tên /admin hoặc /private không tự bảo vệ destination. Cấu hình authorization ở tầng Spring Security và broker ACL.

## 15. Kiểm thử cấu hình định tuyến

Nên kiểm thử cả cấu hình Spring và hành vi frame thực tế.

Các trường hợp chính:

1. Kết nối được tới đúng WebSocket endpoint.
2. SEND /app/... gọi đúng @MessageMapping.
3. Prefix /app được bỏ trước khi tra cứu method.
4. SUBSCRIBE /topic/... được simple broker hoặc relay nhận.
5. Message gửi tới broker destination đến đúng subscriber.
6. SEND trực tiếp tới /topic/... không vô tình gọi controller.
7. @SubscribeMapping xử lý SUBSCRIBE tới application destination.
8. Response @SubscribeMapping được gửi trực tiếp hoặc qua broker đúng theo @SendTo.
9. /user/queue/... được resolve theo Principal/session.
10. convertAndSendToUser gửi đúng user và các session tương ứng.
11. Prefix tùy chỉnh hoạt động nhất quán giữa client và server.
12. Pattern với PathMatcher khớp đúng destination.
13. Broker relay kết nối được và broker chấp nhận destination.
14. Client không có quyền bị từ chối khi SEND hoặc SUBSCRIBE.
15. Tùy chọn preserve publish order được kiểm thử nếu nghiệp vụ yêu cầu.

Có thể dùng Spring WebSocket/STOMP test support hoặc kết nối broker test để xác nhận các frame. Unit test chỉ gọi trực tiếp method controller không kiểm tra được toàn bộ bước phân loại destination và broker routing.

## 16. Checklist trước khi phát hành

- WebSocket endpoint URL đã được phân biệt với STOMP destination chưa?
- Application prefix có tường minh và thống nhất không?
- @MessageMapping có bỏ application prefix khỏi annotation không?
- Broker prefix có khớp destination mà client subscribe/publish không?
- Simple broker hay broker relay phù hợp với yêu cầu lưu trữ và ACK?
- Có hiểu đúng semantics của /queue và /topic theo broker đang dùng không?
- User destination prefix có được UserDestinationMessageHandler xử lý không?
- Principal được dùng để xác định user có đáng tin cậy không?
- Prefix và PathMatcher có thống nhất giữa client, controller và broker không?
- Có cấu hình authorization cho SEND/SUBSCRIBE?
- Broker relay có host, port, credential, virtual host và ACL phù hợp không?
- Có integration test cho các route quan trọng và trường hợp bị từ chối không?

## 17. Tài liệu tham khảo

- [MessageBrokerRegistry — Spring Framework 6.1 Javadoc](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/messaging/simp/config/MessageBrokerRegistry.html)
- [Enable STOMP — Spring Framework Reference](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/enable.html)
- [Simple Broker — Spring Framework Reference](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-simple-broker.html)
- [External Broker and STOMP Relay — Spring Framework Reference](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-broker-relay.html)
- [User Destinations — Spring Framework Reference](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/user-destination.html)
- [Message Flow — Spring Framework Reference](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/message-flow.html)
- [@MessageMapping — Spring Framework Javadoc](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/messaging/handler/annotation/MessageMapping.html)
- [@SubscribeMapping — Spring Framework 6.1 Javadoc](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/messaging/simp/annotation/SubscribeMapping.html)
- [SimpMessagingTemplate — Spring Framework Javadoc](https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/messaging/simp/SimpMessagingTemplate.html)

configureMessageBroker định nghĩa cách Spring phân loại destination STOMP. Application prefix đưa message vào controller, broker prefix chuyển message tới simple broker hoặc relay, còn user prefix cho phép gửi tới session của user đã xác thực. Khi phân biệt đúng endpoint, destination và các lớp prefix, luồng SEND, SUBSCRIBE và response trở nên dễ theo dõi, kiểm thử và bảo trì.