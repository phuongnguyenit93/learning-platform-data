# Phân biệt quy ước tên /topic, /queue với ngữ nghĩa thực của broker

Trong STOMP, giá trị của header destination là một chuỗi do client gửi đến server. Tên như **/topic/prices** hay **/queue/orders** rất phổ biến, nhưng bản thân giao thức STOMP không quy định rằng mọi server phải hiểu hai prefix này theo cùng một cách. STOMP 1.2 xem destination là chuỗi opaque và để cú pháp cũng như delivery semantics cho từng server/broker quyết định.

Điều đó có nghĩa là cùng một frame STOMP có thể dẫn đến hành vi khác nhau khi chạy với Spring simple broker, RabbitMQ STOMP plugin hoặc ActiveMQ Classic. Một tên destination chỉ có ý nghĩa khi biết adapter/broker nào đang xử lý nó, cấu hình broker ra sao và client dùng SEND hay SUBSCRIBE.

Bài này phân biệt ba lớp: quy ước đặt tên trong ứng dụng, cách Spring định tuyến destination và semantics thực tế do broker cung cấp. Đây là điểm cần nắm trước khi thiết kế queue, topic, durable subscription, competing consumers hoặc hệ thống cần bảo đảm message.

## 1. STOMP không định nghĩa ý nghĩa cố định cho /topic và /queue

STOMP là giao thức messaging ở lớp ứng dụng. Một frame SEND có header destination để chỉ nơi gửi message; frame SUBSCRIBE dùng destination để đăng ký nhận message.

Ví dụ:

~~~text
SEND
destination:/queue/orders
content-type:application/json

{"orderId":"ORD-42","event":"created"}^@
~~~

Hoặc:

~~~text
SUBSCRIBE
id:prices-sub
destination:/topic/prices
ack:auto

^@
~~~

Trong STOMP 1.2, destination là một chuỗi opaque. Giao thức không yêu cầu server phải có queue hoặc topic, cũng không bắt buộc một delivery model cho tên có prefix /queue hay /topic. Cú pháp destination và semantics của message exchange phụ thuộc server.

STOMP chuẩn hóa command và một số header, chẳng hạn SEND, SUBSCRIBE, ACK, NACK, RECEIPT, content-type và content-length. Nó không chuẩn hóa các thuộc tính vận hành của một destination cụ thể như:

- Destination là queue, topic, exchange, address hay một tên logic.
- Một message được giao cho một consumer hay được sao chép tới nhiều subscriber.
- Message có được giữ lại khi không có subscriber hay bị loại bỏ.
- Subscription có durable hay chỉ tồn tại khi client đang kết nối.
- Queue/topic có được tạo tự động khi SEND hoặc SUBSCRIBE hay phải tồn tại trước.
- Message có persistent, có TTL, priority, dead-letter hoặc replay hay không.
- ACK, redelivery và transaction được triển khai ở mức nào.

Do đó, đừng suy ra semantics chỉ từ chuỗi destination. Cần đọc tài liệu STOMP adapter của broker thực tế và kiểm tra cấu hình triển khai.

## 2. /topic và /queue là quy ước đặt tên phổ biến

Trong nhiều hệ thống messaging:

- **Topic** biểu diễn publish-subscribe: một publisher gửi một message, broker có thể tạo bản sao cho nhiều subscription.
- **Queue** biểu diễn point-to-point hoặc competing consumers: nhiều consumer cùng đọc một queue, nhưng mỗi message thường được giao cho một consumer tại một thời điểm.

Quy ước phổ biến là:

- /topic/prices: message giá được phát tới nhiều subscriber.
- /queue/orders: message đơn hàng được phân phối cho một consumer trong nhóm worker.

Đây là cách đặt tên dễ đọc cho người phát triển. Nhưng chỉ broker có semantics tương ứng mới biến quy ước đó thành hành vi queue/topic thực sự.

Cần phân biệt ba ý:

1. **Tên destination:** chuỗi nằm trong header STOMP.
2. **Quy tắc định tuyến:** server chọn handler, broker hoặc resource nào dựa trên chuỗi đó.
3. **Delivery semantics:** broker phân phối, lưu giữ, xác nhận và giao lại message như thế nào.

Một ứng dụng có thể dùng prefix /queue trong tên destination nhưng vẫn nhận broadcast nếu broker chỉ broadcast đến mọi subscription có destination khớp. Ngược lại, một broker có thể dùng một cú pháp khác để truy cập queue hoặc exchange.

## 3. Spring simple broker: prefix chỉ là quy ước định tuyến

Khi bật built-in simple broker:

~~~java
@Configuration
@EnableWebSocketMessageBroker
public class WebSocketConfiguration
        implements WebSocketMessageBrokerConfigurer {

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.enableSimpleBroker("/topic", "/queue");
    }
}
~~~

Spring dùng prefix để phân luồng message:

- Destination bắt đầu bằng /app được chuyển tới các method @MessageMapping.
- Destination bắt đầu bằng /topic hoặc /queue được chuyển trực tiếp đến simple broker.

Với simple broker, /topic và /queue **không có ý nghĩa đặc biệt về delivery**. Đây chỉ là quy ước để đội phát triển phân biệt destination thường dùng cho pub-sub và destination thường dùng cho point-to-point.

Simple broker lưu subscription trong bộ nhớ ứng dụng. Khi một message được gửi đến destination, broker tìm các subscription có destination khớp và broadcast message tới các subscriber đó.

Ví dụ, hai client cùng SUBSCRIBE /queue/orders trên simple broker. Khi ứng dụng gửi một message đến /queue/orders, cả hai subscription đều khớp và cả hai client đều nhận một bản sao. Simple broker không biến /queue/orders thành một queue có competing consumers chỉ nhờ prefix.

Tương tự, /topic/prices cũng được broadcast đến mọi subscription khớp. Với simple broker, sự khác nhau giữa /topic và /queue chủ yếu nằm ở ý nghĩa quy ước trong code và cấu hình prefix.

### 3.1. Simple broker phù hợp khi nào?

Simple broker phù hợp với ứng dụng nhỏ, demo, môi trường phát triển hoặc tính năng realtime có yêu cầu vừa phải:

- Subscription được lưu trong bộ nhớ của một Spring application instance.
- Message được broadcast đến client đang kết nối và có destination khớp.
- Không có persistence của broker để giữ backlog khi ứng dụng dừng.
- Không có cơ chế queue competing consumers như một message broker chuyên dụng.
- Không phù hợp để clustering subscription giữa nhiều application instance.
- Chỉ hỗ trợ một phần STOMP; ví dụ không hỗ trợ ACK và RECEIPT.

Nếu cần một destination có semantics queue thực sự, có lưu message khi consumer offline, phân phối giữa nhiều worker hoặc redelivery sau lỗi, hãy dùng broker chuyên dụng thông qua broker relay.

### 3.2. Không đặt tên gây hiểu nhầm

Nếu dùng simple broker, destination /queue/orders có thể khiến người đọc nghĩ rằng message được load balance giữa các consumer. Điều đó không xảy ra chỉ vì prefix là /queue.

Nên thống nhất convention trong nhóm:

- Dùng /topic cho destination được broadcast đến các subscriber.
- Dùng /queue cho destination logic mà ứng dụng dự định xử lý point-to-point.
- Ghi rõ rằng với simple broker, cả hai vẫn broadcast theo subscription matching.
- Nếu cần semantics queue thật, chuyển sang broker có hỗ trợ queue và xác minh delivery behavior.

Có thể dùng tên như /events/orders hoặc /realtime/prices nếu muốn tránh hàm ý queue/topic do broker không cung cấp.

## 4. Spring broker relay: destination được chuyển tới broker ngoài

Khi cần broker chuyên dụng, Spring có thể relay STOMP frame đến một broker hỗ trợ STOMP:

~~~java
@Override
public void configureMessageBroker(MessageBrokerRegistry registry) {
    registry.setApplicationDestinationPrefixes("/app");
    registry.enableStompBrokerRelay("/topic", "/queue")
            .setRelayHost("broker.example.com")
            .setRelayPort(61613)
            .setClientLogin("spring-client")
            .setClientPasscode("configured-secret");
}
~~~

Trong cấu hình này:

- /app vẫn là prefix để Spring chuyển message đến @MessageMapping.
- /topic và /queue là các prefix Spring chuyển tiếp tới broker relay.
- Broker ngoài quyết định destination được ánh xạ thành resource gì và message được giao theo semantics nào.

Spring broker relay không tự biến /queue thành một queue theo cùng một cách trên mọi broker. Nó chuyển frame đến broker và broker xử lý destination theo adapter, cấu hình và sản phẩm cụ thể.

Ví dụ, RabbitMQ STOMP plugin và ActiveMQ Classic STOMP connector đều hỗ trợ /queue và /topic, nhưng cách ánh xạ destination và một số mặc định khác nhau.

## 5. RabbitMQ STOMP plugin: /queue và /topic có semantics cụ thể

RabbitMQ cung cấp STOMP adapter qua plugin rabbitmq_stomp. Plugin định nghĩa một số dạng destination riêng. Hai dạng phổ biến là /queue và /topic.

### 5.1. /queue/name trong RabbitMQ

Với destination dạng /queue/orders:

- SUBSCRIBE tạo hoặc dùng một shared queue tên orders do STOMP gateway quản lý.
- SEND gửi message vào queue đó.
- Nhiều subscriber cùng đăng ký queue sẽ cạnh tranh nhận message.
- Mỗi message được giao cho tối đa một subscriber tại một thời điểm.
- Khi không có subscriber, message có thể được giữ trong queue chờ consumer kết nối.
- Nếu không chỉ định queue arguments, queue mặc định được mô tả là durable, non-exclusive và non-auto-delete.

Đây là semantics queue/competing consumers mà nhiều người thường mong đợi khi thấy prefix /queue. Tuy nhiên, đây là hành vi của RabbitMQ STOMP plugin, không phải yêu cầu chung của STOMP.

RabbitMQ còn có /amq/queue/name để truy cập queue đã được tạo bên ngoài STOMP gateway. Với SUBSCRIBE, queue phải tồn tại; adapter không tạo queue mới cho dạng destination này.

### 5.2. /topic/name trong RabbitMQ

Với destination dạng /topic/prices:

- SEND publish message vào exchange mặc định amq.topic với routing key tương ứng.
- SUBSCRIBE tạo một queue riêng cho subscription hiện tại và bind queue đó vào exchange.
- Mỗi subscriber có queue riêng nên mỗi subscriber đang hoạt động có thể nhận một bản sao.
- Queue subscription mặc định là auto-delete và non-durable.
- Nếu không có subscriber đang hoạt động, message gửi tới topic có thể bị loại bỏ.

Điều này khác queue: topic thường fan-out đến các subscriber, trong khi queue chia message giữa các consumer cạnh tranh.

RabbitMQ còn hỗ trợ dạng /exchange/exchange-name/routing-key để gửi trực tiếp đến exchange và đăng ký binding pattern. Nếu cần dùng queue có sẵn, hãy phân biệt /queue và /amq/queue theo tài liệu plugin.

### 5.3. Queue bền vững và message bền vững là hai khái niệm khác nhau

Một queue được khai báo durable không tự động có nghĩa mọi message gửi vào đó đều persistent. Durability của queue liên quan đến việc định nghĩa queue còn tồn tại sau broker restart; persistence của message liên quan đến việc broker lưu message theo delivery mode và cấu hình.

Cần kiểm tra cả hai:

- Queue/exchange có durable không?
- Message có persistent không?
- Broker có xác nhận publish đã được chấp nhận không?
- Consumer dùng ack mode nào?
- Message chưa ACK có được redeliver khi consumer disconnect không?
- Có TTL, dead-letter exchange hoặc giới hạn queue không?

Đừng coi tên /queue là bằng chứng message đã được lưu bền vững.

## 6. ActiveMQ Classic STOMP: prefix được bỏ trước khi ánh xạ JMS destination

ActiveMQ Classic có STOMP connector và ánh xạ STOMP destination sang JMS destination.

Theo quy tắc mặc định:

- /queue/FOO.BAR được ánh xạ thành JMS Queue có tên FOO.BAR.
- /topic/FOO.BAR được ánh xạ thành JMS Topic có tên FOO.BAR.
- Prefix /queue/ hoặc /topic/ được bỏ trước khi chuyển tên destination cho ActiveMQ.

Ví dụ, client gửi:

~~~text
SEND
destination:/queue/ORDERS.CREATED

OrderCreated^@
~~~

ActiveMQ Classic nhận đây là JMS Queue ORDERS.CREATED. Nếu gửi tới /topic/ORDERS.CREATED, nó được ánh xạ thành JMS Topic ORDERS.CREATED.

ActiveMQ Classic có một khác biệt quan trọng về persistence: STOMP message mặc định là non-persistent. Muốn gửi persistent message, client cần thêm header:

~~~text
SEND
destination:/queue/ORDERS.CREATED
persistent:true

OrderCreated^@
~~~

Vì vậy, ngay cả khi destination là /queue, message vẫn có thể non-persistent theo mặc định của STOMP connector. Đây là ví dụ rõ ràng cho thấy queue semantics và message persistence phải được kiểm tra riêng.

ActiveMQ Classic cũng hỗ trợ một số header mở rộng để ánh xạ thuộc tính JMS, như correlation-id, expires, priority, reply-to, JMSXGroupID và selector. Các extension này thuộc implementation của ActiveMQ, không phải mọi STOMP broker đều hỗ trợ giống nhau.

## 7. So sánh cùng destination trên các broker

Bảng dưới đây cho thấy cùng một chuỗi destination có thể dẫn đến hành vi khác nhau:

| Destination | Spring simple broker | RabbitMQ STOMP plugin | ActiveMQ Classic STOMP |
|---|---|---|---|
| /queue/orders | Subscription khớp được broadcast; không có competing-consumer queue chỉ nhờ prefix | Shared queue; message được giao cho tối đa một subscriber | JMS Queue tên orders |
| /topic/prices | Subscription khớp được broadcast | Exchange amq.topic; mỗi subscription có queue riêng và nhận bản sao | JMS Topic tên prices |
| Message khi không có subscriber | Simple broker chỉ giữ subscription trong memory; không phải persistent queue | Queue giữ message theo queue config; topic không có active subscriber có thể drop message | Queue/topic và durable subscription tuân theo JMS/ActiveMQ config |
| Message persistence | Không có broker persistence tích hợp | Phụ thuộc queue/message flags và broker config | STOMP non-persistent mặc định; dùng persistent:true để yêu cầu persistent |
| Clustering | Simple broker không chia sẻ subscription giữa instance | Phụ thuộc RabbitMQ cluster và cấu hình | Phụ thuộc ActiveMQ deployment/topology |

Bảng này là hướng dẫn đối chiếu các cấu hình mặc định thường gặp. Broker có thể được tùy chỉnh bằng policy, queue arguments, plugin settings hoặc destination resolver. Luôn xác nhận phiên bản và cấu hình thực tế trước khi dựa vào một semantics cụ thể.

## 8. SEND và SUBSCRIBE có thể có quy tắc tạo destination khác nhau

Một destination không nhất thiết được tạo theo cùng cách khi client gửi SEND và khi client đăng ký SUBSCRIBE.

Ví dụ RabbitMQ:

- SEND đến /queue/orders có thể tạo shared queue lần đầu trong session theo quy tắc của STOMP gateway.
- SUBSCRIBE đến /queue/orders đăng ký consumer vào shared queue đó.
- SUBSCRIBE đến /topic/prices tạo queue riêng cho subscription và bind queue vào exchange.
- SEND đến /topic/prices publish vào exchange; nếu không có binding/subscriber phù hợp, message có thể không được giữ lại.

Với /exchange/orders/created, RabbitMQ có thể publish đến exchange orders với routing key created. Khi SUBSCRIBE cùng destination, adapter có thể tạo queue riêng và bind theo pattern. Đó là lý do cần đọc cả quy tắc SEND lẫn SUBSCRIBE trong tài liệu broker.

Với ActiveMQ Classic, prefix được bỏ để tạo JMS Queue hoặc Topic; destination có thể được tạo theo chính sách broker và quyền của user. Không nên giả định mọi adapter đều có cùng hành vi auto-create.

## 9. Durable subscription không đồng nghĩa với /topic thông thường

Một topic subscription thông thường có thể chỉ tồn tại khi client kết nối. Nếu client disconnect, message được publish trong thời gian đó có thể không được giữ lại cho client.

Durable subscription cung cấp một định danh subscription lâu dài để broker giữ message cho subscriber ngay cả khi client offline, tùy cấu hình và semantics broker. Khi client reconnect và đăng ký lại đúng durable subscription, nó có thể nhận message đang chờ.

Cần xác định:

- Durable subscription được đặt tên bằng header hoặc cấu hình nào?
- Subscription gắn với client ID, user hay session?
- Có thể có nhiều consumer cùng đọc một durable subscription không?
- Khi unsubscribe, subscription bị detach hay bị xóa hoàn toàn?
- Message được giữ trong bao lâu và bị xóa theo TTL/policy nào?
- Có giới hạn backlog và dead-letter không?

Không có quy tắc chung rằng thêm prefix /topic là tạo durable subscription. Ví dụ, RabbitMQ có cách cấu hình durable topic khác với ActiveMQ Classic và các broker STOMP khác.

## 10. /user và destination logic của Spring

Spring còn có user destination prefix, mặc định là /user. Đây là một lớp định tuyến logic để gửi message tới một user đã xác thực hoặc một session cụ thể.

Ví dụ:

~~~java
messagingTemplate.convertAndSendToUser(
        username,
        "/queue/notifications",
        notification
);
~~~

Spring phân giải user destination thành destination riêng cho session của user đó. Chuỗi /user/queue/notifications mà client subscribe không nhất thiết là queue vật lý tên user/queue/notifications trong broker.

Nếu dùng broker relay, Spring có thể chuyển destination đã được phân giải tới broker. Khi đó, semantics cuối cùng vẫn phụ thuộc broker. Cần phân biệt:

- /user là prefix logic của Spring.
- /queue là convention hoặc broker-specific destination prefix.
- Tên queue vật lý được tạo hoặc chọn theo quy tắc broker và Spring user destination resolver.

Không dùng /user như một biện pháp authorization. Server vẫn phải xác thực Principal và kiểm tra user có quyền gửi/nhận destination tương ứng.

## 11. Thiết kế destination để giảm nhầm lẫn

Một quy ước tốt nên thể hiện cả domain và loại delivery mong muốn:

| Mục đích | Tên ví dụ | Điều cần xác minh |
|---|---|---|
| Broadcast giá realtime | /topic/prices | Fan-out, subscriber mới có nhận message cũ không? |
| Phân phối job cho worker | /queue/orders | Competing consumers, persistence, ACK và redelivery |
| Sự kiện theo domain | /topic/orders.created | Một hay nhiều subscriber cần nhận bản sao? |
| Request/reply | /temp-queue/replies | Temporary destination và reply-to được broker hỗ trợ ra sao? |
| Thông báo cho user | /user/queue/notifications | Spring phân giải user/session và broker xử lý destination cuối cùng thế nào? |
| Routing theo key | /exchange/events/order.created | Exchange, routing key và binding pattern của broker |

Nên ghi rõ destination convention trong tài liệu tích hợp:

- Prefix nào là application destination của Spring?
- Prefix nào được chuyển trực tiếp tới broker?
- Tên destination có được auto-create không?
- SEND và SUBSCRIBE dùng cùng resource hay khác nhau?
- Queue/topic có durable không?
- Message có persistent không?
- ACK mode, redelivery và dead-letter policy là gì?
- Destination có giới hạn quyền publish/subscribe theo user không?

Khi đổi broker, không nên chỉ thay connection URL rồi giữ nguyên giả định delivery. Cần rà soát destination mapping, queue declaration, subscription, persistence, ACK và redelivery.

## 12. Bảo mật và quyền truy cập destination

Destination là dữ liệu do client gửi trong STOMP frame. Không nên tin rằng client được phép SEND hoặc SUBSCRIBE chỉ vì nó dùng prefix hợp lệ.

Cần phân quyền riêng:

- **SEND:** user nào được publish vào /app hoặc destination broker nào?
- **SUBSCRIBE:** user nào được đọc /topic, /queue hoặc user destination nào?
- **Destination ownership:** user có được truy cập resource thuộc tenant khác không?
- **Broker credentials:** Spring relay dùng credential riêng; client không nên nhận quyền broker rộng hơn nhu cầu.
- **Destination creation:** client có được tạo queue/topic tùy ý không?
- **Resource limits:** giới hạn số queue, subscription, consumer và message size.

Với Spring Security, có thể kiểm tra message type và destination qua message authorization rules. Với broker ngoài, cần thêm ACL ở broker để giới hạn quyền SEND/SUBSCRIBE và tạo destination. Bảo vệ ở cả Spring và broker giúp tránh việc một đường truy cập khác bỏ qua policy của ứng dụng.

## 13. Ví dụ Java 17: cùng destination, ba cách diễn giải

Ví dụ sau mô phỏng cách ba implementation diễn giải cùng destination. Nó dùng JDK thuần, không kết nối broker và không tạo queue/topic thật. Mục đích là cho thấy prefix không tự mang semantics chung cho mọi server.

Tạo file **StompDestinationSemanticsDemo.java**:

~~~java
public class StompDestinationSemanticsDemo {

    record Interpretation(
            String implementation,
            String destination,
            String resource,
            String delivery,
            String persistence) {}

    static Interpretation springSimpleBroker(
            String destination,
            int matchingSubscribers) {

        requireSupported(destination);

        return new Interpretation(
                "Spring simple broker",
                destination,
                "in-memory subscription destination",
                "broadcast to " + matchingSubscribers
                        + " matching subscriber(s)",
                "no broker persistence"
        );
    }

    static Interpretation rabbitMq(String destination) {
        if (destination.startsWith("/queue/")) {
            String name = destination.substring("/queue/".length());

            return new Interpretation(
                    "RabbitMQ STOMP",
                    destination,
                    "shared queue " + name,
                    "competing consumers; at most one subscriber per message",
                    "queue defaults durable; message persistence is separate"
            );
        }

        if (destination.startsWith("/topic/")) {
            String name = destination.substring("/topic/".length());

            return new Interpretation(
                    "RabbitMQ STOMP",
                    destination,
                    "amq.topic exchange with routing key " + name,
                    "one subscription queue per subscriber; fan-out copies",
                    "subscription queue defaults non-durable and auto-delete"
            );
        }

        throw new IllegalArgumentException(
                "Demo supports only /queue/ and /topic/: " + destination);
    }

    static Interpretation activeMqClassic(String destination) {
        if (destination.startsWith("/queue/")) {
            String jmsName = destination.substring("/queue/".length());

            return new Interpretation(
                    "ActiveMQ Classic STOMP",
                    destination,
                    "JMS Queue " + jmsName,
                    "queue delivery to competing consumers",
                    "STOMP message non-persistent by default"
            );
        }

        if (destination.startsWith("/topic/")) {
            String jmsName = destination.substring("/topic/".length());

            return new Interpretation(
                    "ActiveMQ Classic STOMP",
                    destination,
                    "JMS Topic " + jmsName,
                    "topic fan-out to subscriptions",
                    "STOMP message non-persistent by default"
            );
        }

        throw new IllegalArgumentException(
                "Demo supports only /queue/ and /topic/: " + destination);
    }

    private static void requireSupported(String destination) {
        if (!destination.startsWith("/queue/")
                && !destination.startsWith("/topic/")) {
            throw new IllegalArgumentException(
                    "Unsupported destination: " + destination);
        }
    }

    private static void print(Interpretation result) {
        System.out.println(result.implementation()
                + " | " + result.destination()
                + " | " + result.resource()
                + " | " + result.delivery()
                + " | " + result.persistence());
    }

    public static void main(String[] args) {
        String queueDestination = "/queue/orders";
        String topicDestination = "/topic/prices";

        print(springSimpleBroker(queueDestination, 2));
        print(springSimpleBroker(topicDestination, 2));

        print(rabbitMq(queueDestination));
        print(rabbitMq(topicDestination));

        print(activeMqClassic(queueDestination));
        print(activeMqClassic(topicDestination));
    }
}
~~~

Biên dịch và chạy bằng Java 17 trở lên:

~~~bash
javac StompDestinationSemanticsDemo.java
java StompDestinationSemanticsDemo
~~~

Kết quả:

~~~text
Spring simple broker | /queue/orders | in-memory subscription destination | broadcast to 2 matching subscriber(s) | no broker persistence
Spring simple broker | /topic/prices | in-memory subscription destination | broadcast to 2 matching subscriber(s) | no broker persistence
RabbitMQ STOMP | /queue/orders | shared queue orders | competing consumers; at most one subscriber per message | queue defaults durable; message persistence is separate
RabbitMQ STOMP | /topic/prices | amq.topic exchange with routing key prices | one subscription queue per subscriber; fan-out copies | subscription queue defaults non-durable and auto-delete
ActiveMQ Classic STOMP | /queue/orders | JMS Queue orders | queue delivery to competing consumers | STOMP message non-persistent by default
ActiveMQ Classic STOMP | /topic/prices | JMS Topic prices | topic fan-out to subscriptions | STOMP message non-persistent by default
~~~

Kết quả minh họa các quy tắc được mô tả trong tài liệu của từng implementation. Nó không chứng minh broker đang chạy có cùng cấu hình; queue durability, message persistence, auto-delete, acknowledgement và redelivery phải được kiểm tra ở môi trường thực tế.

## 14. Quy trình xác minh semantics trước khi tích hợp

Khi tích hợp một STOMP broker hoặc đổi broker, hãy thực hiện các bước:

1. Ghi lại phiên bản broker, STOMP plugin/adapter và phiên bản Spring.
2. Đọc destination syntax chính thức của adapter.
3. Kiểm tra riêng hành vi SEND và SUBSCRIBE.
4. Xác định destination được tạo tự động hay phải khai báo trước.
5. Tạo hai subscriber cùng đăng ký một /queue và gửi nhiều message; xác nhận message được chia giữa consumer hay broadcast cho cả hai.
6. Tạo hai subscriber cùng đăng ký một /topic; xác nhận mỗi subscriber có nhận một bản sao không.
7. Ngắt toàn bộ subscriber rồi gửi message; kiểm tra message được giữ, hết hạn hay bị loại bỏ.
8. Restart broker; kiểm tra queue, subscription và message có được khôi phục không.
9. Ngắt consumer trước ACK; xác nhận redelivery và delivery count.
10. Kiểm tra persistent message, receipt/publisher confirm, TTL và dead-letter.
11. Kiểm tra ACL cho SEND, SUBSCRIBE và destination creation.
12. Ghi kết quả thành contract để client và producer dùng cùng semantics.

Một test tích hợp nên chạy với broker thật hoặc container broker tương ứng. Unit test chỉ kiểm tra chuỗi destination không thể chứng minh delivery semantics của broker.

## 15. Ghi nhớ

STOMP chỉ chuẩn hóa destination thành một chuỗi và để server quyết định cú pháp cùng delivery semantics. /topic và /queue là convention phổ biến, nhưng không phải quy tắc bắt buộc của STOMP.

Spring simple broker dùng prefix để chọn đường định tuyến và broadcast đến các subscription khớp; /queue không tự trở thành competing-consumer queue. RabbitMQ STOMP plugin ánh xạ /queue và /topic sang queue/exchange với semantics cụ thể của RabbitMQ. ActiveMQ Classic bỏ prefix rồi ánh xạ sang JMS Queue hoặc Topic, đồng thời STOMP message mặc định non-persistent.

Khi thiết kế hệ thống, hãy xác minh destination mapping, queue/topic behavior, persistence, ACK, redelivery, durable subscription và ACL trên đúng broker. Tên destination nên thể hiện ý định của ứng dụng, còn bảo đảm thực tế phải đến từ cấu hình và contract của implementation.

## Tài liệu tham khảo

- [STOMP 1.2 Specification – Protocol Overview and Destinations](https://stomp.github.io/stomp-specification-1.2.html)
- [Spring Framework – STOMP](https://docs.spring.io/spring-framework/reference/web/websocket/stomp.html)
- [Spring Framework – Simple Broker](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-simple-broker.html)
- [Spring Framework – Flow of Messages](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/message-flow.html)
- [Spring Framework – External Broker Relay](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-broker-relay.html)
- [RabbitMQ – STOMP Plugin and Destinations](https://www.rabbitmq.com/docs/stomp)
- [ActiveMQ Classic – STOMP Destinations and Persistence](https://activemq.apache.org/components/classic/documentation/stomp)