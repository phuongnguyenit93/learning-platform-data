# Phân phối STOMP qua broker ngoài khi chạy nhiều server

## Mục tiêu

Khi một ứng dụng Spring chạy trên một server, simple broker tích hợp có thể đủ để quản lý subscription và phát message. Khi ứng dụng được triển khai thành nhiều instance sau load balancer, mỗi instance lại có bộ nhớ và danh sách WebSocket session riêng. Nếu dùng simple broker ở từng instance, một client kết nối vào node A sẽ không tự nhận được message mà node B gửi tới broker cục bộ của nó.

Giải pháp phổ biến là dùng **STOMP broker relay** để mỗi instance Spring chuyển tiếp message tới một message broker bên ngoài dùng chung. Broker đảm nhiệm việc quản lý subscription và phân phối message giữa các kết nối đến từ nhiều instance ứng dụng.

Bài này giải thích kiến trúc, cấu hình và vận hành mô hình đó với Spring Framework 6.1. Ví dụ broker cụ thể dùng RabbitMQ để minh họa; destination và queue semantics phải được kiểm tra theo broker thực tế.

Sau bài này, bạn có thể:

- Phân biệt simple broker và external STOMP broker relay.
- Mô tả luồng message khi có nhiều Spring application server.
- Cấu hình enableStompBrokerRelay với destination prefixes, credentials và heartbeat.
- Dùng userRegistryBroadcast và userDestinationBroadcast cho user destination giữa nhiều node.
- Phân biệt application destination, broker destination và user destination.
- Thiết kế xác thực, phân quyền, queue lifecycle và kết nối an toàn.
- Tính quy mô kết nối, xử lý broker outage và kiểm thử phân phối xuyên node.

## 1. Vấn đề khi chạy nhiều application server

### 1.1. Simple broker giữ subscription trong bộ nhớ từng node

Spring có thể bật broker tích hợp bằng:

~~~java
registry.enableSimpleBroker("/topic", "/queue");
~~~

Simple broker quản lý subscription trong bộ nhớ của application instance. Giả sử có hai node:

~~~text
                    Load Balancer
                    /           \
                   v             v
             Spring Node A   Spring Node B
             Simple Broker   Simple Broker
             Client Alice    Client Bob
~~~

Alice kết nối WebSocket vào Node A. Bob kết nối vào Node B. Khi Node A gửi message tới /topic/orders, simple broker của Node A chỉ biết các subscriber mà Node A đang quản lý. Nó không có subscription của Bob ở Node B. Chiều ngược lại cũng tương tự.

Nếu mọi client luôn kết nối vào cùng một node thì giới hạn này có thể chưa lộ ra. Khi scale ngang, deploy rolling hoặc client reconnect sang node khác, mỗi simple broker vẫn là một bộ nhớ độc lập.

Sticky session ở load balancer không giải quyết việc chia sẻ subscription giữa các node. Nó chỉ giữ một kết nối hoặc nhóm request gắn với một backend trong phạm vi cấu hình của load balancer.

### 1.2. External broker làm điểm phân phối chung

Với broker relay, mỗi Spring node vẫn quản lý WebSocket session của những client đang kết nối trực tiếp vào node đó. Tuy nhiên, subscription và message có prefix broker được chuyển tới một external broker chung:

~~~text
                         WebSocket clients
                       /                   \
                  Alice                     Bob
                    |                        |
                    v                        v
              Spring Node A            Spring Node B
              WebSocket session        WebSocket session
              STOMP relay              STOMP relay
                    |                        |
                    +-----------+------------+
                                |
                                v
                       External STOMP Broker
                       shared destinations
                                |
                    +-----------+------------+
                    |                        |
                    v                        v
              Relay Node A              Relay Node B
                    |                        |
                    v                        v
              Alice session             Bob session
~~~

Khi Alice publish message vào một broker destination, Node A chuyển message tới broker. Broker tìm các subscription phù hợp trên toàn hệ thống và gửi message về các relay connection tương ứng. Node B nhận message từ broker rồi chuyển tới WebSocket session của Bob.

Nhờ đó, các application instance dùng chung một hệ thống phân phối message. Broker có thể là RabbitMQ, ActiveMQ hoặc một STOMP broker khác có hỗ trợ destination và tính năng phù hợp.

### 1.3. Broker relay không thay thế application server

Spring vẫn chịu trách nhiệm:

- Xác thực HTTP/WebSocket và gắn Principal cho session.
- Chuyển message gửi tới application destination vào @MessageMapping.
- Chạy validation, authorization và nghiệp vụ.
- Chuyển đổi payload, headers và response.
- Quản lý WebSocket session trên node đang giữ kết nối.
- Chuyển message tới broker hoặc nhận message từ broker.

External broker chịu trách nhiệm:

- Quản lý các STOMP subscription mà client relay đăng ký.
- Phân phối message tới subscription phù hợp.
- Thực hiện semantics queue/topic theo broker.
- Cung cấp các tính năng broker hỗ trợ như acknowledgement, receipt, persistence hoặc durable subscription.

Broker relay là MessageHandler của Spring, chuyển tiếp message hai chiều qua TCP giữa Spring và broker. Nó không tự chia sẻ database, HTTP session, cache hay trạng thái nghiệp vụ giữa các application node.

## 2. Simple broker và STOMP broker relay

| Tiêu chí | Simple broker | STOMP broker relay |
|---|---|---|
| Nơi giữ subscription | Bộ nhớ của một Spring application instance | External broker |
| Phân phối giữa nhiều Spring node | Không tự chia sẻ | Có thể thông qua broker chung |
| Hỗ trợ STOMP commands | Chỉ một tập con | Theo khả năng của broker |
| ACK, RECEIPT | Không hỗ trợ đầy đủ | Broker có thể hỗ trợ |
| Persistence và durable subscription | Không phải mục tiêu của simple broker | Phụ thuộc broker và cấu hình |
| Vận hành | Ít thành phần | Cần vận hành broker, kết nối và quyền truy cập |
| Mở rộng ngang | Không phù hợp làm broker cluster | Phù hợp hơn khi broker được triển khai có HA |

Simple broker hữu ích khi phát triển, demo hoặc ứng dụng đơn giản. Nó không phải một broker cluster và không tự đồng bộ subscription giữa các instance. Spring khuyến nghị dùng broker relay khi cần một broker đầy đủ tính năng và phân phối message có khả năng mở rộng.

Không phải mọi STOMP broker đều hỗ trợ cùng một tập command. ACK, RECEIPT, durable subscription, queue declaration và các destination cụ thể phụ thuộc broker. Hãy kiểm tra tài liệu của broker trước khi thiết kế giao thức client.

## 3. Các loại destination trong Spring STOMP

Cần phân biệt ba nhóm destination để tránh gửi nhầm message tới broker.

### 3.1. Application destination

Ví dụ:

~~~text
/app/orders.create
/app/chat.send
~~~

Destination có prefix /app được Spring định tuyến tới các phương thức @MessageMapping. Prefix /app được loại bỏ trước khi Spring tìm mapping.

~~~java
@Controller
public class OrderController {

    @MessageMapping("/orders.create")
    public OrderResult create(OrderCommand command) {
        return orderService.create(command);
    }
}
~~~

Client gửi STOMP SEND tới /app/orders.create. Request được xử lý bởi application instance đang giữ WebSocket session của client. Broker không thực thi phương thức controller này.

### 3.2. Broker destination

Ví dụ thường gặp:

~~~text
/topic/orders
/queue/order-processing
~~~

Các destination có prefix /topic hoặc /queue được chuyển tới external broker khi relay được cấu hình tương ứng. Ý nghĩa chính xác của destination do broker quy định; STOMP không bắt buộc mọi broker phải hiểu /topic và /queue theo cùng một cách.

Thông thường:

- Topic biểu diễn publish-subscribe: một message có thể được phát tới nhiều subscription.
- Queue biểu diễn point-to-point hoặc work distribution: một message thường được giao cho một consumer trong nhóm, tùy broker.

Không nên giả định mọi subscriber của một queue đều nhận được bản sao message. Nếu cần broadcast, hãy chọn destination và exchange semantics phù hợp với broker.

### 3.3. User destination

Ví dụ:

~~~text
/user/queue/notifications
~~~

Spring xử lý prefix /user thông qua UserDestinationMessageHandler. Destination chung được chuyển thành destination riêng cho user/session để các user không va chạm vào cùng một queue hoặc subscription nội bộ.

Client có thể subscribe:

~~~text
SUBSCRIBE
id:notifications-1
destination:/user/queue/notifications

^@
~~~

Phía server có thể gửi tới user cụ thể bằng SimpMessagingTemplate hoặc @SendToUser. User destination được Spring phân giải trước khi message đi tới broker; không cấu hình broker trực tiếp xử lý prefix /user như một destination thông thường.

## 4. Cấu hình broker relay

### 4.1. Khai báo endpoint và broker prefixes

Một cấu hình cơ bản:

~~~java
@Configuration
@EnableWebSocketMessageBroker
public class WebSocketConfiguration
        implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(
            StompEndpointRegistry registry) {
        registry.addEndpoint("/ws");
    }

    @Override
    public void configureMessageBroker(
            MessageBrokerRegistry registry) {

        registry.setApplicationDestinationPrefixes("/app");

        registry.enableStompBrokerRelay(
                "/topic",
                "/queue");
    }
}
~~~

Ở đây:

- /ws là HTTP endpoint để client thực hiện WebSocket handshake.
- /app định tuyến message tới @MessageMapping.
- /topic và /queue được relay tới external broker.
- /user là user destination prefix mặc định của Spring; có thể cấu hình tường minh bằng setUserDestinationPrefix nếu muốn.

Không bật enableSimpleBroker cùng các prefix dự định gửi qua external relay trong cùng cấu hình. Hãy xác định rõ prefix nào thuộc application và prefix nào thuộc broker.

### 4.2. Cấu hình host, port và credentials

StompBrokerRelayRegistration trả về từ enableStompBrokerRelay cho phép cấu hình host, port và credentials. Nên lấy thông tin kết nối từ environment, secret manager hoặc cấu hình triển khai, không hard-code passcode vào source code.

Ví dụ dưới đây dùng một record chứa cấu hình đã được nạp từ property source:

~~~java
public record StompRelayProperties(
        String host,
        int port,
        String clientLogin,
        String clientPasscode,
        String systemLogin,
        String systemPasscode,
        String virtualHost) {
}
~~~

Bean StompRelayProperties cần được cung cấp bởi cấu hình ứng dụng. Ví dụ với Spring Environment:

~~~java
@Configuration
class StompRelayPropertiesConfiguration {

    @Bean
    StompRelayProperties stompRelayProperties(
            Environment environment) {

        return new StompRelayProperties(
                environment.getRequiredProperty(
                        "messaging.stomp.relay.host"),
                environment.getRequiredProperty(
                        "messaging.stomp.relay.port", Integer.class),
                environment.getRequiredProperty(
                        "messaging.stomp.relay.client-login"),
                environment.getRequiredProperty(
                        "messaging.stomp.relay.client-passcode"),
                environment.getRequiredProperty(
                        "messaging.stomp.relay.system-login"),
                environment.getRequiredProperty(
                        "messaging.stomp.relay.system-passcode"),
                environment.getProperty(
                        "messaging.stomp.relay.virtual-host"));
    }
}
~~~

Cấu hình relay:

~~~java
@Configuration
@EnableWebSocketMessageBroker
public class WebSocketConfiguration
        implements WebSocketMessageBrokerConfigurer {

    private final StompRelayProperties properties;

    public WebSocketConfiguration(
            StompRelayProperties properties) {
        this.properties = properties;
    }

    @Override
    public void registerStompEndpoints(
            StompEndpointRegistry registry) {
        registry.addEndpoint("/ws");
    }

    @Override
    public void configureMessageBroker(
            MessageBrokerRegistry registry) {

        registry.setApplicationDestinationPrefixes("/app");
        registry.setUserDestinationPrefix("/user/");

        StompBrokerRelayRegistration relay =
                registry.enableStompBrokerRelay(
                        "/topic",
                        "/queue");

        relay.setRelayHost(properties.host());
        relay.setRelayPort(properties.port());

        relay.setClientLogin(properties.clientLogin());
        relay.setClientPasscode(properties.clientPasscode());

        relay.setSystemLogin(properties.systemLogin());
        relay.setSystemPasscode(properties.systemPasscode());

        relay.setSystemHeartbeatSendInterval(10_000);
        relay.setSystemHeartbeatReceiveInterval(10_000);

        if (properties.virtualHost() != null
                && !properties.virtualHost().isBlank()) {
            relay.setVirtualHost(properties.virtualHost());
        }
    }
}
~~~

Ví dụ dùng API của Spring Framework 6.1.21. Trong hệ thống thật, property passcode phải được cấp từ secret manager hoặc cơ chế quản lý secret của nền tảng triển khai. Không đưa secret vào Git, log hoặc thông tin lỗi.

### 4.3. Phân biệt client connection và system connection

Broker relay duy trì hai loại kết nối:

| Kết nối | Số lượng | Dùng cho |
|---|---:|---|
| System TCP connection | Một kết nối cho mỗi relay/application instance | Message do code phía server gửi tới broker, không gắn với một WebSocket client cụ thể |
| Client TCP connection | Một kết nối cho mỗi WebSocket client đang kết nối | Relay message và subscription của client đó với broker |

System connection dùng cho message phát sinh từ application, không phải đường nhận message broker gửi về các WebSocket client. Các client TCP connection nhận message từ broker và relay chúng về đúng WebSocket session.

Điều này có ảnh hưởng trực tiếp đến quy mô. Nếu có 4 application instance và tổng cộng 20.000 WebSocket client đang hoạt động, broker có thể phải phục vụ xấp xỉ 20.000 client TCP connection cùng 4 system connection, chưa kể kết nối quản trị và các client khác.

Không hiểu nhầm relay là một connection pool duy nhất dùng chung cho mọi WebSocket client. Broker phải được sizing theo số client connection, subscription, throughput, heartbeat và queue topology thực tế.

### 4.4. System credentials và client credentials

- clientLogin/clientPasscode được dùng cho các TCP connection được tạo thay mặt WebSocket client.
- systemLogin/systemPasscode được dùng cho system connection gửi message từ application code, ví dụ HTTP controller hoặc scheduled job.

Theo thiết kế broker relay, các CONNECT frame được chuyển tiếp thay mặt client sẽ được relay đặt login/passcode từ clientLogin/clientPasscode. Vì vậy, STOMP login/passcode do browser tự gửi không quyết định danh tính broker của kết nối đó.

Tất cả các client connection thường dùng chung broker identity đã cấu hình cho clientLogin. Do đó, không thể mặc định broker biết chính xác end-user nào đang thao tác chỉ từ broker username. Việc xác thực user và phân quyền destination cần được thực hiện tại Spring/WebSocket layer; broker ACL kiểm soát quyền của relay identities.

## 5. Kiến trúc nhiều node và luồng message

Giả sử có hai node Spring:

- Node A đang giữ WebSocket session của Alice.
- Node B đang giữ WebSocket session của Bob.
- Cả hai relay đều kết nối tới cùng external broker.

### 5.1. Broadcast từ một node tới client ở node khác

Bob subscribe /topic/orders thông qua Node B. Alice gửi lệnh tới /app/orders.create thông qua Node A. Controller trên Node A xử lý nghiệp vụ rồi phát event:

~~~java
messagingTemplate.convertAndSend(
        "/topic/orders",
        new OrderCreatedEvent(orderId, status));
~~~

Message đi theo luồng:

1. Alice gửi /app/orders.create tới Node A.
2. Spring định tuyến message tới @MessageMapping trên Node A.
3. Service tạo đơn hàng và trả về kết quả.
4. Node A gửi event tới /topic/orders qua broker relay.
5. External broker tìm subscription của /topic/orders.
6. Broker chuyển event tới relay của Node B.
7. Node B chuyển event qua clientOutboundChannel tới WebSocket session của Bob.

Cùng một destination broker có thể được subscribe bởi client ở nhiều application instance. Broker xử lý fan-out; các node không cần gọi trực tiếp nhau.

### 5.2. Message từ HTTP request hoặc background job

Không chỉ message đến từ WebSocket client mới được phát qua broker. Bất kỳ component nào có SimpMessagingTemplate đều có thể gửi message:

~~~java
@Service
public class OrderEventPublisher {

    private final SimpMessagingTemplate messagingTemplate;

    public OrderEventPublisher(
            SimpMessagingTemplate messagingTemplate) {
        this.messagingTemplate = messagingTemplate;
    }

    public void publish(OrderCreatedEvent event) {
        messagingTemplate.convertAndSend(
                "/topic/orders",
                event);
    }
}
~~~

Ví dụ có thể được gọi từ REST controller, scheduled job, service hoặc listener. Message không gắn với một WebSocket client cụ thể được gửi qua system connection của broker relay.

Vì thế, nếu một REST request được load balancer chuyển tới Node A, event vẫn có thể tới các subscriber đang kết nối ở Node B, C hoặc D thông qua broker chung.

### 5.3. Application destination vẫn chạy trên node nhận kết nối

Broker relay không tự chuyển mọi message /app sang một controller trên bất kỳ node nào. Khi client gửi /app/orders.create, message được xử lý trong application instance đang giữ WebSocket session của client.

Nếu handler cần chia sẻ công việc giữa nhiều node, hãy thiết kế một broker destination hoặc application event phù hợp. Không dùng /app như thể nó là một queue phân phối task giữa các server.

## 6. User destination khi user kết nối ở node khác

Đây là phần cần cấu hình riêng trong mô hình nhiều application server.

### 6.1. User destination được phân giải dựa trên user registry

Spring giữ một SimpUserRegistry cục bộ trên mỗi application instance. Registry biết những user/session được node đó quản lý.

Ví dụ Alice subscribe:

~~~text
/user/queue/notifications
~~~

Node A ghi nhận session của Alice và chuyển destination chung thành một destination nội bộ duy nhất cho user/session đó.

Nếu Node B gọi:

~~~java
messagingTemplate.convertAndSendToUser(
        "alice",
        "/queue/notifications",
        notification);
~~~

Node B cần biết Alice đang kết nối ở đâu. Nếu chỉ dùng registry cục bộ, Node B có thể không tìm thấy Alice vì session đang nằm trên Node A.

### 6.2. Broadcast user registry giữa các node

StompBrokerRelayRegistration có API:

~~~java
relay.setUserRegistryBroadcast(
        "/topic/internal.simp-user-registry");
~~~

Cấu hình này cho phép node broadcast nội dung local user registry và nhận broadcast từ các server khác. Nhờ vậy, mỗi node có thể nhận biết user đang kết nối trên những node còn lại.

Tất cả application instance phải dùng cùng destination registry broadcast và cùng external broker. Destination này cần có semantics broadcast để mọi node nhận được thông tin registry.

### 6.3. Broadcast user destination chưa phân giải được

Cấu hình thêm:

~~~java
relay.setUserDestinationBroadcast(
        "/topic/internal.unresolved-user-destination");
~~~

Khi một node không thể phân giải user destination vì user có thể đang kết nối trên node khác, message chưa phân giải được được broadcast để các node còn lại có cơ hội xử lý.

Hai cấu hình có vai trò khác nhau:

| Cấu hình | Mục đích |
|---|---|
| userRegistryBroadcast | Chia sẻ thông tin user/session giữa các node |
| userDestinationBroadcast | Chuyển tiếp message user destination chưa phân giải để node khác thử xử lý |

Trong thực tế, khi cần gửi user-specific message xuyên node, hãy cấu hình cả hai trên mọi instance và kiểm thử với client thực sự kết nối ở các node khác nhau. Registry broadcast giúp các node có cái nhìn rộng hơn; unresolved broadcast là cơ chế xử lý trường hợp node hiện tại vẫn chưa tìm thấy đích.

### 6.4. Ví dụ cấu hình user destination đầy đủ

~~~java
@Override
public void configureMessageBroker(
        MessageBrokerRegistry registry) {

    registry.setApplicationDestinationPrefixes("/app");
    registry.setUserDestinationPrefix("/user/");

    registry.enableStompBrokerRelay("/topic", "/queue")
            .setRelayHost(properties.host())
            .setRelayPort(properties.port())
            .setClientLogin(properties.clientLogin())
            .setClientPasscode(properties.clientPasscode())
            .setSystemLogin(properties.systemLogin())
            .setSystemPasscode(properties.systemPasscode())
            .setUserRegistryBroadcast(
                    "/topic/internal.simp-user-registry")
            .setUserDestinationBroadcast(
                    "/topic/internal.unresolved-user-destination");
}
~~~

Tên destination internal phải giống nhau trên mọi node. Không cấu hình node A dùng registry topic khác node B, nếu không các node không thể chia sẻ thông tin.

Các internal topic này chứa dữ liệu điều phối user/session. Hãy giới hạn quyền truy cập và không cho browser client subscribe hoặc publish tùy ý vào chúng.

### 6.5. Gửi message tới user

Client subscribe:

~~~text
SUBSCRIBE
id:user-alerts
destination:/user/queue/alerts

^@
~~~

Server gửi:

~~~java
messagingTemplate.convertAndSendToUser(
        "alice",
        "/queue/alerts",
        new Alert("ORDER_READY", "Your order is ready"));
~~~

Hoặc dùng @SendToUser trong controller:

~~~java
@Controller
public class OrderNotificationController {

    @MessageMapping("/orders.watch")
    @SendToUser("/queue/order-updates")
    public OrderUpdate watch(
            OrderWatchCommand command,
            Principal principal) {

        return orderService.watch(
                principal.getName(),
                command.orderId());
    }
}
~~~

Nếu user có nhiều session, mặc định message gửi tới tất cả session đã subscribe destination đó. Khi chỉ muốn trả về session tạo request, có thể dùng @SendToUser với broadcast=false.

### 6.6. Dọn dẹp destination theo vòng đời user

User destination được chuyển thành destination nội bộ có thể thay đổi theo session. Khi user disconnect, broker cần xóa queue/subscription tạm theo đúng semantics của broker.

Với RabbitMQ, có thể dùng exchange destination tạo queue auto-delete cho subscription. Với ActiveMQ, có cơ chế purge inactive destination riêng. Cần kiểm tra cách broker xử lý inactive queue, durable subscription và reconnect; nếu không, các queue không còn subscriber có thể tồn tại lâu và tích lũy tài nguyên.

## 7. Destination semantics phụ thuộc broker

STOMP định nghĩa frame SEND, SUBSCRIBE, MESSAGE và destination header, nhưng không bắt buộc mọi broker dùng cùng quy tắc đặt tên destination. Spring chỉ chuyển destination prefix tới broker; broker quyết định cách tạo exchange, queue và binding.

### 7.1. Ví dụ RabbitMQ STOMP plugin

RabbitMQ hỗ trợ STOMP thông qua plugin:

~~~bash
rabbitmq-plugins enable rabbitmq_stomp
~~~

STOMP TCP listener mặc định thường dùng port 61613 nếu không cấu hình khác. Broker phải bật plugin và cho phép các tài khoản relay kết nối.

RabbitMQ hỗ trợ một số destination thường dùng:

| Destination | Ý nghĩa trong RabbitMQ STOMP |
|---|---|
| /topic/name | Publish/subscribe qua topic exchange; mỗi subscription có queue riêng |
| /queue/name | Queue dùng chung; một message được giao cho tối đa một subscriber |
| /amq/queue/name | Truy cập queue đã tồn tại, không tự tạo queue mới |
| /exchange/name/routing-key | Gửi tới exchange và routing key cụ thể |
| /temp-queue/name | Temporary queue trong reply-to flow |

Với /topic, queue subscription mặc định thường là non-durable và auto-delete. Nếu không có subscriber, message gửi tới topic có thể bị bỏ. Với /queue, nhiều subscriber có thể cạnh tranh nhận message từ cùng queue; không phải mọi subscriber đều nhận bản sao.

Các semantics trên là của RabbitMQ STOMP adapter, không phải quy tắc chung của STOMP. Nếu dùng ActiveMQ hoặc broker khác, phải kiểm tra destination prefix, durable subscription, acknowledgement, queue cleanup và routing syntax tương ứng.

### 7.2. Broadcast và work queue là hai nhu cầu khác nhau

Nếu cần gửi thông báo cho tất cả người dùng đang mở màn hình, hãy dùng topic/fan-out destination.

Nếu cần phân phối một công việc cho một worker trong nhóm, hãy dùng queue/work-queue destination.

Dùng queue cho broadcast có thể khiến một số client không nhận được message vì broker chỉ giao message cho một consumer. Dùng topic cho công việc cần một consumer duy nhất có thể khiến mọi subscriber đều thực hiện cùng side effect.

### 7.3. Message offline và durable subscription

Topic subscription tạm thời thường chỉ nhận message khi subscription đang hoạt động. Nếu người dùng offline mà vẫn phải nhận thông báo sau khi đăng nhập lại, cần chọn một cơ chế bền vững:

- Durable topic subscription được broker hỗ trợ.
- Queue riêng có persistence và chính sách retention.
- Lưu notification vào database/event store rồi client đọc lại khi reconnect.
- Kết hợp broker notification với API truy vấn trạng thái.

Không giả định broker relay tự lưu mọi message cho user đang offline. Delivery guarantee phụ thuộc destination, durability, acknowledgement và cấu hình broker.

## 8. Bảo mật trong mô hình relay

### 8.1. Xác thực WebSocket bằng HTTP identity

Một STOMP over WebSocket session bắt đầu bằng HTTP handshake. Spring thường gắn Principal từ HTTP request vào WebSocket session và các message sau đó.

Vì broker relay đặt clientLogin/clientPasscode lên CONNECT frame gửi tới broker thay mặt browser, login/passcode do browser gửi không phải danh tính end-user được dùng để xác thực broker connection.

Thiết kế nên gồm:

- Bảo vệ HTTP endpoint /ws bằng cơ chế xác thực của ứng dụng.
- Gắn Principal đáng tin cậy cho WebSocket session.
- Kiểm tra quyền SEND và SUBSCRIBE theo destination.
- Không tin username hoặc userId do payload/header client tự khai báo.
- Chỉ cho phép client SEND vào application prefix như /app.
- Chặn client publish trực tiếp vào destination nội bộ hoặc topic hệ thống nếu không được phép.

### 8.2. Phân quyền tại Spring và broker

Vì nhiều client connection có thể dùng cùng broker client identity, broker không tự biết user Alice hay Bob đang gửi frame nào. Do đó:

- Spring Security hoặc ChannelInterceptor cần kiểm tra quyền theo Principal.
- Broker ACL giới hạn relay identity được truy cập exchange, queue và virtual host nào.
- System identity nên có quyền riêng cho message từ application và internal broadcast.
- Không dùng guest/guest trong production.
- Tạo credential riêng cho client relay và system relay.
- Rotate secrets theo chính sách vận hành.

Tách clientLogin và systemLogin giúp broker có thể áp dụng quyền khác nhau cho traffic từ client session và message từ server. Cần kiểm tra ACL thực tế của broker và đảm bảo internal broadcast destination không bị client bên ngoài truy cập.

### 8.3. Bảo vệ internal broadcast destinations

Các destination như:

~~~text
/topic/internal.simp-user-registry
/topic/internal.unresolved-user-destination
~~~

là kênh điều phối giữa Spring node. Chúng không phải public API cho browser.

Nếu client có thể subscribe hoặc publish tùy ý vào các destination này, có thể lộ thông tin user/session hoặc làm sai lệch quá trình phân giải user destination. Hãy chặn truy cập từ client ở Spring Security và giới hạn ACL ở broker nếu broker hỗ trợ.

### 8.4. TLS và network boundary

Kết nối browser tới application nên dùng HTTPS/WSS. Kết nối application tới broker nên đi qua mạng nội bộ được kiểm soát hoặc TLS khi đi qua mạng không tin cậy.

Với RabbitMQ, STOMP plugin hỗ trợ TLS listener riêng. Cần cấu hình certificate, trust chain và listener TLS ở broker; relay phải dùng TCP client có TLS tương ứng. Không chỉ bật WSS ở phía browser rồi coi đường app-to-broker đã được mã hóa.

Nếu broker chạy trong cloud, virtualHost cấu hình STOMP CONNECT host header có thể khác hostname TCP mà application kết nối tới. Đây là hai thông tin khác nhau.

## 9. High availability và reconnect

### 9.1. Broker relay tự reconnect system connection

Spring STOMP broker relay duy trì system connection và heartbeat với broker. Theo mặc định, heartbeat gửi/nhận là 10 giây. Khi mất kết nối, relay tiếp tục thử kết nối lại, mặc định khoảng mỗi 5 giây.

Có thể tùy chỉnh:

~~~java
relay.setSystemHeartbeatSendInterval(10_000);
relay.setSystemHeartbeatReceiveInterval(10_000);
~~~

Chọn heartbeat phải phù hợp với broker, load balancer, firewall và network idle timeout. Nếu các bên dùng heartbeat interval khác nhau hoặc timeout quá ngắn, kết nối khỏe có thể bị xem là chết.

### 9.2. Theo dõi BrokerAvailabilityEvent

Spring phát BrokerAvailabilityEvent khi system connection với broker bị mất hoặc được thiết lập lại. Application component có thể lắng nghe để tạm dừng các thao tác cần broker khi broker chưa sẵn sàng:

~~~java
@Component
public class BrokerAvailabilityListener
        implements ApplicationListener<BrokerAvailabilityEvent> {

    @Override
    public void onApplicationEvent(
            BrokerAvailabilityEvent event) {

        if (event.isBrokerAvailable()) {
            // Broker system connection đã sẵn sàng.
        }
        else {
            // Tạm dừng hoặc từ chối tác vụ cần broker.
        }
    }
}
~~~

Event này phản ánh trạng thái system connection của relay. Nó không thay thế việc giám sát từng WebSocket session hoặc toàn bộ subscription của client.

### 9.3. Client reconnect và resubscribe

Khi broker hoặc application node bị restart, WebSocket client có thể mất session. Client cần:

1. Phát hiện WebSocket disconnect.
2. Kết nối lại tới endpoint qua load balancer.
3. Xác thực lại nếu session/token đã hết hạn.
4. Tạo lại STOMP session.
5. Subscribe lại các destination cần thiết.
6. Đồng bộ trạng thái hiện tại từ API/database nếu có khoảng thời gian mất message.

Không giả định subscription cũ được tự khôi phục sau khi WebSocket session đã bị đóng. Nếu message trong thời gian offline phải được giữ lại, cần durable queue/subscription hoặc lưu trạng thái nghiệp vụ bền vững.

### 9.4. Broker HA là một bài toán riêng

Có nhiều Spring node không đồng nghĩa external broker đã có HA. Cần thiết kế riêng cho broker:

- Broker cluster hoặc cơ chế replication phù hợp.
- Load balancer hoặc service endpoint cho STOMP TCP/TLS.
- Queue type, replication và persistence phù hợp với mức độ quan trọng của message.
- Quorum, failover, backup và disaster recovery theo broker.
- Monitoring connection limit, queue depth, unacked messages và disk/memory alarm.

Mặc định relay kết nối lại cùng host/port đã cấu hình. Nếu cần chọn nhiều địa chỉ broker theo từng lần connect, Spring cho phép cấu hình TcpOperations<byte[]> tùy chỉnh qua setTcpClient. Khi dùng custom TCP client, host/port được cấu hình trực tiếp trên relay sẽ bị bỏ qua.

Không coi reconnect là bảo đảm không mất message. Reconnect chỉ khôi phục đường truyền; durability, acknowledgement và duplicate handling phải được thiết kế ở broker và application.

## 10. Tính quy mô và giới hạn kết nối

Với N client WebSocket đang kết nối trên một node, relay cần xấp xỉ N client TCP connection tới broker và một system connection. Với nhiều node:

~~~text
Tổng broker connections
    ≈ tổng WebSocket client connections trên mọi node
      + số application node
      + kết nối quản trị/producer/consumer khác
~~~

Ví dụ có 3 node với 4.000, 3.500 và 2.500 WebSocket client:

~~~text
Client connections = 4.000 + 3.500 + 2.500
                   = 10.000

System connections = 3

Relay connections  ≈ 10.003
~~~

Đây là ước tính cho relay, chưa tính kết nối khác và các kết nối phụ thuộc broker implementation. Khi scale, cần tính:

- Giới hạn TCP connection trên broker và OS.
- Memory cho mỗi connection và subscription.
- Số lượng subscription mỗi client.
- Heartbeat traffic.
- Message rate và kích thước payload.
- Queue backlog và consumer acknowledgement.
- Số connection tạo mới trong rolling deployment hoặc reconnect storm.
- Giới hạn thread, event loop và file descriptor ở application/broker.

Tăng số Spring node có thể tăng số system connection và phân tán WebSocket sessions, nhưng không làm tổng số broker client connections biến mất. Broker phải được scale theo tổng số session và throughput toàn cụm.

## 11. Monitoring và vận hành

Nên theo dõi cả application relay và external broker.

**Phía Spring application:**

- Số WebSocket session hiện tại theo node.
- Số lần disconnect/reconnect.
- BrokerAvailabilityEvent chuyển trạng thái.
- Lỗi gửi qua broker channel.
- Số message inbound/outbound, độ trễ và payload size.
- Số subscription/user destination đang hoạt động.
- Số message bị từ chối bởi authorization.

**Phía broker:**

- Tổng STOMP connections và số connection theo identity.
- Số subscription, queue và consumer.
- Queue depth, unacked messages và message age.
- Publish/deliver/ack rate.
- Unroutable hoặc dropped message.
- Connection churn, heartbeat timeout, memory/disk alarm.
- Queue không còn consumer hoặc temporary queue không được dọn.

Dùng tag metric có cardinality thấp như protocol, destination template, outcome và application node. Không đưa userId, sessionId, messageId hoặc traceId vào metric tags. Định danh cụ thể nên được ghi trong log/trace có kiểm soát để tránh tạo quá nhiều time series.

Khi system connection mất, application có thể vẫn phục vụ HTTP và WebSocket handshake nhưng không thể gửi message qua broker như mong đợi. Hãy quyết định rõ endpoint nào phải báo unavailable, tác vụ nào được queue nội bộ và tác vụ nào phải fail-fast.

## 12. Kiểm thử phân phối giữa nhiều server

Unit test cho controller không chứng minh broker đã phân phối message giữa các node. Cần integration test có external broker thật hoặc môi trường test tương đương.

### 12.1. Kiểm thử broadcast xuyên node

Thiết lập:

- Khởi chạy broker có STOMP plugin.
- Khởi chạy hai Spring application instance A và B với cùng broker config.
- Kết nối STOMP client Alice vào node A.
- Kết nối STOMP client Bob vào node B.
- Bob subscribe /topic/orders.
- Alice gửi message qua /app/orders.create.
- Controller node A publish event tới /topic/orders.

Assertion: Bob nhận được event dù session của Bob nằm ở node B.

### 12.2. Kiểm thử user destination xuyên node

- Alice kết nối node A và subscribe /user/queue/alerts.
- Bob hoặc một HTTP request đi vào node B.
- Node B gọi convertAndSendToUser("alice", "/queue/alerts", payload).
- Kiểm tra registry broadcast đã giúp node B nhận biết user Alice.
- Kiểm tra unresolved destination broadcast có thể chuyển message sang node A nếu node B chưa phân giải được.
- Xác nhận chỉ các session của Alice nhận message theo đúng broadcast policy.

Test này cần xác minh cả hai API userRegistryBroadcast và userDestinationBroadcast, không chỉ test user destination khi user và sender cùng một node.

### 12.3. Kiểm thử lỗi và failover

| Tình huống | Điều cần xác minh |
|---|---|
| Broker dừng khi application đang chạy | Availability event chuyển unavailable; send policy rõ ràng |
| Broker khởi động lại | Relay reconnect; client session được xử lý theo policy |
| Node A bị dừng | Client reconnect sang node khác và subscribe lại |
| Node B gửi tới user đang ở node A | User registry và unresolved destination broadcast hoạt động |
| Một node cấu hình sai broker prefix | Test phát hiện node không nhận message |
| Broker từ chối credentials | Relay không sẵn sàng; log không lộ passcode |
| Queue/topic không tồn tại hoặc sai semantics | Broker trả lỗi hoặc message không route; test phát hiện |
| User disconnect | Temporary queue/subscription được cleanup theo broker policy |
| Hai node cùng xử lý event | Idempotency bảo vệ side effect nếu message bị gửi lặp |
| Broker quá tải hoặc hết connection limit | Backpressure/failure behavior và cảnh báo hoạt động |

Nên chạy thêm kiểm thử tải với số client gần mức dự kiến, subscription thực tế và message rate đại diện. Một test chỉ có vài WebSocket client không đủ để xác nhận giới hạn connection hoặc memory của broker.

## 13. Lỗi cấu hình thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Hướng kiểm tra |
|---|---|---|
| Client node A không nhận message do node B phát | Hai node dùng simple broker riêng hoặc relay khác broker | Kiểm tra enableStompBrokerRelay và broker endpoint chung |
| Message /app không tới controller | Application destination prefix hoặc @MessageMapping sai | Kiểm tra /app prefix và mapping sau khi bỏ prefix |
| Message /topic không được broadcast | Prefix không được relay hoặc broker không hỗ trợ destination | Kiểm tra relay prefixes và broker destination semantics |
| User-specific message không tới node khác | Chưa cấu hình user registry/unresolved broadcast | Kiểm tra hai API broadcast và internal topic |
| Client nhận message queue không đều | Dùng queue cho nhu cầu broadcast | Chuyển sang topic/fan-out semantics phù hợp |
| Broker nhận mọi client dưới cùng user | Relay dùng clientLogin chung cho các client connection | Phân quyền end-user ở Spring layer |
| Message bị mất khi user offline | Subscription tạm thời hoặc topic không có subscriber | Dùng durable queue/subscription hoặc lưu notification |
| Broker tạo nhiều queue không được xóa | Queue/session cleanup không phù hợp | Kiểm tra auto-delete, expiry và broker policy |
| Kết nối bị đóng định kỳ | Heartbeat hoặc idle timeout không thống nhất | Kiểm tra heartbeat hai phía và load balancer |
| Broker unavailable nhưng HTTP vẫn trả thành công | Application không kiểm tra trạng thái broker trước khi publish | Xử lý BrokerAvailabilityEvent và định nghĩa failure policy |
| Một node gửi được, node khác không gửi được | Credentials, vhost, ACL hoặc network khác nhau | So sánh cấu hình và broker permission giữa node |
| Restart broker làm client không nhận lại | WebSocket/STOMP session và subscription đã mất | Thiết kế reconnect, re-authentication và resubscribe |

## 14. Checklist triển khai production

Trước khi triển khai nhiều Spring server với external STOMP broker, hãy xác nhận:

1. Broker hỗ trợ các STOMP command cần dùng.
2. STOMP plugin/listener đã bật và network route từ mọi application node tới broker hoạt động.
3. Mọi node dùng cùng broker endpoint, destination prefixes và user broadcast destinations.
4. enableStompBrokerRelay được dùng thay cho simple broker khi cần phân phối xuyên node.
5. /app, /topic, /queue và /user có ranh giới rõ ràng.
6. Client authentication dựa trên HTTP/WebSocket Principal và authorization được kiểm tra ở Spring.
7. Client relay identity và system relay identity có quyền broker phù hợp.
8. Internal user registry/unresolved topics không mở cho browser client.
9. TLS và secret management được cấu hình cho đường kết nối tới broker.
10. Broker connection limit được sizing theo tổng WebSocket sessions của toàn cụm.
11. Heartbeat, reconnect, BrokerAvailabilityEvent và client resubscribe đã được kiểm thử.
12. User-specific queue/subscription có chính sách cleanup.
13. Durable message hoặc offline notification có thiết kế riêng.
14. Integration test xác minh broadcast và user destination giữa ít nhất hai application node.
15. Broker HA, persistence, queue policy và backup được vận hành riêng.
16. Monitoring bao phủ application relay và broker.

## Ghi nhớ

External STOMP broker giải quyết việc phân phối subscription và message giữa nhiều Spring application server. Mỗi node vẫn quản lý WebSocket session cục bộ, còn broker relay chuyển các broker destination tới một broker dùng chung.

Trong Spring Framework, enableStompBrokerRelay cấu hình destination prefixes và trả về StompBrokerRelayRegistration để đặt host, port, credentials, heartbeat và các broadcast destination. Broker relay có một system connection cho message từ application và một client connection cho mỗi WebSocket client.

Với user destination xuyên node, cấu hình userRegistryBroadcast để chia sẻ user registry và userDestinationBroadcast để chuyển tiếp message chưa phân giải. Bảo vệ các internal destination, xác thực user ở WebSocket layer và phân quyền ở cả Spring lẫn broker.

Cuối cùng, broker relay không tự bảo đảm message durability hoặc HA. Những điều đó phụ thuộc broker, destination, acknowledgement, queue policy, persistence và cơ chế reconnect của client. Hãy kiểm thử với nhiều application instance và broker thật trước khi coi hệ thống đã sẵn sàng cho production.

## Tài liệu tham khảo

- [Spring Framework — External Broker](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-broker-relay.html)
- [Spring Framework 6.1.21 — StompBrokerRelayRegistration API](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/messaging/simp/config/StompBrokerRelayRegistration.html)
- [Spring Framework 6.1.21 — MessageBrokerRegistry API](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/messaging/simp/config/MessageBrokerRegistry.html)
- [Spring Framework — Connecting to a Broker](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-broker-relay-configure.html)
- [Spring Framework — User Destinations](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/user-destination.html)
- [Spring Framework — STOMP Authentication](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/authentication.html)
- [Spring Security — WebSocket Security](https://docs.spring.io/spring-security/reference/servlet/integrations/websocket.html)
- [RabbitMQ — STOMP Plugin](https://www.rabbitmq.com/docs/stomp)
