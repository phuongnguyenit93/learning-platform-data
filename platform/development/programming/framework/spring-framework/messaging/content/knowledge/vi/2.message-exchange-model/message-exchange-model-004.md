# Phát hành và đăng ký nhận thông điệp trong Spring Framework

## 1. Mục tiêu và mô hình publish-subscribe

Publish-subscribe (phát hành và đăng ký nhận) là mô hình trao đổi trong đó một bên phát thông điệp lên một kênh hoặc một đích nhận, còn các bên quan tâm đăng ký trước để nhận thông điệp đó. Bên phát không cần biết có bao nhiêu subscriber, subscriber nào đang chạy hay chúng được triển khai ở đâu.

Ví dụ, khi đơn hàng được tạo, hệ thống phát sự kiện \`order.created\`. Các subscriber có thể ghi nhật ký kiểm toán, cập nhật số liệu, gửi thông báo và đồng bộ dữ liệu. Mỗi subscriber xử lý cùng một sự kiện theo trách nhiệm riêng.

Mô hình này phù hợp khi:
- Một sự kiện cần kích hoạt nhiều tác vụ độc lập.
- Muốn giảm phụ thuộc trực tiếp giữa thành phần phát và thành phần nhận.
- Có thể bổ sung hoặc gỡ subscriber mà không phải sửa logic của publisher.
- Thông điệp mang ý nghĩa thông báo rằng một việc đã xảy ra, thay vì yêu cầu một consumer duy nhất thực hiện công việc.

Cần phân biệt hai kiểu trao đổi:

| Đặc điểm | Publish-subscribe | Point-to-point |
| --- | --- | --- |
| Phân phối | Một thông điệp được chuyển đến mọi subscriber phù hợp | Một thông điệp được giao cho một consumer trong nhóm |
| Mục tiêu | Thông báo cho nhiều thành phần | Chia việc cho các consumer cùng xử lý |
| Ví dụ | Đơn hàng mới được gửi đến audit, analytics và notification | Một tác vụ gửi email được lấy bởi một worker |
| Rủi ro thường gặp | Một subscriber lỗi hoặc chậm ảnh hưởng đến luồng phát tùy cách dispatch | Consumer cạnh tranh, phân phối tải và xử lý lại |

Publish-subscribe không tự động đồng nghĩa với lưu trữ bền vững. Một kênh trong bộ nhớ có thể phát thông điệp đến nhiều subscriber đang đăng ký, nhưng không giữ thông điệp để subscriber ngoại tuyến nhận lại sau này.

## 2. Các khối nền tảng của Spring Messaging

Spring Framework cung cấp module \`spring-messaging\` với các abstraction để tách bên phát khỏi bên nhận:

- **\`Message<T>\`**: một thông điệp gồm payload có kiểu và tập metadata.
- **\`MessageHeaders\`**: chứa metadata như ID, timestamp, content type, correlation ID, destination hoặc header tùy chỉnh. Header của một message đã tạo là bất biến; hãy dùng builder hoặc accessor để tạo message mới thay vì sửa trực tiếp.
- **\`MessageChannel\`**: hợp đồng gửi message. Publisher gọi \`send(message)\` mà không cần gọi thẳng handler.
- **\`SubscribableChannel\`**: mở rộng \`MessageChannel\`, cho phép đăng ký và hủy đăng ký \`MessageHandler\`.
- **\`MessageHandler\`**: hợp đồng xử lý message thông qua \`handleMessage(message)\`.
- **\`ExecutorSubscribableChannel\`**: triển khai \`SubscribableChannel\` và gửi message đến từng subscriber. Constructor không tham số chạy handler trên thread gọi \`send\`; constructor nhận \`Executor\` chuyển việc dispatch sang executor đó.
- **\`MessageBuilder\`**: tạo message và đặt header theo cách an toàn.

Ví dụ tạo message:

~~~java
Message<String> message = MessageBuilder
    .withPayload("order-42")
    .setHeader("eventType", "order.created")
    .setHeader("correlationId", "request-91")
    .build();
~~~

Payload mô tả dữ liệu nghiệp vụ; header mô tả ngữ cảnh vận chuyển và định tuyến. Nên dùng payload bất biến hoặc coi payload là chỉ đọc, vì nhiều subscriber có thể cùng nhận một message.

Lưu ý về tên lớp: \`ExecutorSubscribableChannel\` thuộc Spring Framework, package \`org.springframework.messaging.support\`. \`PublishSubscribeChannel\` và \`DirectChannel\` thường được nhắc đến trong tài liệu Spring Integration: \`PublishSubscribeChannel\` phát đến các handler đăng ký, còn \`DirectChannel\` dùng cơ chế phân phối point-to-point. Muốn dùng các lớp của Spring Integration, dự án phải có module \`spring-integration-core\`; không nhầm chúng với lớp trong \`spring-messaging\`.

## 3. Luồng phát và nhận trong một ứng dụng

Luồng xử lý trong một kênh publish-subscribe có thể hình dung như sau:

~~~mermaid
flowchart LR
    P[Publisher] --> M[Message: payload + headers]
    M --> C[SubscribableChannel]
    C --> A[Subscriber: audit]
    C --> B[Subscriber: analytics]
    C --> N[Subscriber: notification]
~~~

1. Publisher tạo message với payload và các header cần thiết.
2. Publisher gọi \`channel.send(message)\`.
3. Channel tìm các handler đã đăng ký và dispatch message theo chính sách của implementation.
4. Mỗi subscriber xử lý message trong handler của mình.
5. Subscriber có thể ghi dữ liệu, gọi dịch vụ khác hoặc phát một message mới; không nên giả định subscriber khác đã hoàn thành trước khi handler hiện tại chạy.

\`subscribe(handler)\` trả về \`true\` khi handler được đăng ký và \`false\` nếu handler đó đã đăng ký. \`unsubscribe(handler)\` hủy đăng ký handler. Giữ lại đúng instance handler nếu cần hủy đăng ký sau này.

## 4. Ví dụ chạy được với ExecutorSubscribableChannel

Ví dụ dưới đây dùng Java 17+ và Spring Framework 7.0.10. Kênh được tạo bằng constructor không tham số nên hai handler chạy đồng bộ trên thread gọi \`send\`. Đây là ví dụ độc lập, không cần khởi tạo Spring ApplicationContext.

Cấu trúc thư mục:

~~~text
spring-messaging-pubsub/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── PublishSubscribeDemo.java
~~~

**pom.xml**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>spring-messaging-pubsub</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-messaging</artifactId>
            <version>7.0.10</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>PublishSubscribeDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**src/main/java/PublishSubscribeDemo.java**

~~~java
import java.util.Map;
import java.util.TreeMap;

import org.springframework.messaging.Message;
import org.springframework.messaging.support.ExecutorSubscribableChannel;
import org.springframework.messaging.support.MessageBuilder;

public class PublishSubscribeDemo {

    public static void main(String[] args) {
        ExecutorSubscribableChannel channel = new ExecutorSubscribableChannel();
        Map<String, String> received = new TreeMap<>();

        channel.subscribe(message ->
            received.put("audit", String.valueOf(message.getPayload()))
        );

        channel.subscribe(message ->
            received.put("metrics",
                String.valueOf(message.getHeaders().get("eventType")))
        );

        Message<String> event = MessageBuilder
            .withPayload("order-42")
            .setHeader("eventType", "order.created")
            .build();

        boolean sent = channel.send(event);

        received.forEach((subscriber, value) ->
            System.out.println(subscriber + ": " + value)
        );
        System.out.println("sent=" + sent);
    }
}
~~~

Chạy từ thư mục có \`pom.xml\`:

~~~bash
mvn -q clean compile exec:java
~~~

Kết quả:

~~~text
audit: order-42
metrics: order.created
sent=true
~~~

Hai subscriber đều nhận được cùng payload và có thể đọc header \`eventType\`. \`TreeMap\` chỉ được dùng để in kết quả theo thứ tự ổn định; nó không quyết định thứ tự dispatch của channel. Giá trị \`sent=true\` cho biết lần gửi được channel chấp nhận theo cơ chế dispatch hiện tại, không phải bằng chứng rằng message đã được lưu bền vững ở một broker bên ngoài.

## 5. Chạy subscriber bằng executor

Khi handler thực hiện công việc tốn thời gian, có thể truyền một \`Executor\` cho \`ExecutorSubscribableChannel\`. Trong ứng dụng Spring, có thể quản lý thread pool bằng \`ThreadPoolTaskExecutor\`:

~~~java
@Configuration
public class MessagingConfig {

    @Bean
    public ThreadPoolTaskExecutor messagingExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(200);
        executor.setThreadNamePrefix("messaging-");
        return executor;
    }

    @Bean
    public MessageChannel orderEvents(ThreadPoolTaskExecutor messagingExecutor) {
        return new ExecutorSubscribableChannel(messagingExecutor);
    }
}
~~~

Khi đó, các handler được dispatch qua executor. Cần lưu ý:

- \`send\` có thể trả về sau khi công việc đã được đưa vào executor, trước khi tất cả handler hoàn tất.
- Ngoại lệ phát sinh trong xử lý bất đồng bộ có thể không được ném về thread gọi \`send\`; cần cấu hình cơ chế báo lỗi, log và giám sát phù hợp.
- Transaction, security context, MDC và các \`ThreadLocal\` của thread gửi không tự động được chuyển sang thread xử lý.
- Cấu hình giới hạn queue, số thread, chính sách từ chối và thời gian shutdown. Queue không giới hạn có thể làm bộ nhớ tăng liên tục khi subscriber xử lý chậm.
- Không dựa vào thứ tự hoàn tất giữa các subscriber khi chạy song song. Nếu nghiệp vụ cần thứ tự, phải thiết kế partition, khóa hoặc cơ chế tuần tự hóa phù hợp.

## 6. Publish-subscribe bằng Spring Application Events

Nếu publisher và subscriber đều là bean trong cùng một \`ApplicationContext\`, Spring Application Events là lựa chọn gọn hơn khi chỉ cần thông báo sự kiện nội bộ. Cơ chế này dùng \`ApplicationEventPublisher\` và \`@EventListener\`, không yêu cầu tạo \`MessageChannel\`.

~~~java
public record StockChanged(long productId, int quantity) {
}

@Component
public class StockService {

    private final ApplicationEventPublisher events;

    public StockService(ApplicationEventPublisher events) {
        this.events = events;
    }

    public void publishStockChange(long productId, int quantity) {
        events.publishEvent(new StockChanged(productId, quantity));
    }
}

@Component
public class StockAuditListener {

    @EventListener
    public void onStockChanged(StockChanged event) {
        System.out.println(
            "Stock changed: product=" + event.productId()
                + ", quantity=" + event.quantity()
        );
    }
}
~~~

Spring tự tìm các listener phù hợp với kiểu event. Mặc định, listener được gọi đồng bộ trên thread phát event; \`publishEvent\` chờ các listener hoàn tất. Có thể dùng \`@Async\` cùng \`@EnableAsync\` hoặc cấu hình \`ApplicationEventMulticaster\` với executor để xử lý bất đồng bộ. Khi chuyển sang thread khác, lỗi và thread context không còn được truyền về publisher theo cách đồng bộ.

Nếu listener cần đọc dữ liệu đã commit trong database, có thể dùng \`@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)\` để xử lý sau khi transaction commit. Application Events chỉ phục vụ giao tiếp trong application context; chúng không tự gửi sự kiện sang tiến trình hoặc máy chủ khác và không thay thế message broker có lưu trữ.

## 7. Publish-subscribe cho client bằng STOMP và WebSocket

Khi cần gửi thông báo từ server đến nhiều trình duyệt hoặc thiết bị đang kết nối, Spring WebSocket hỗ trợ STOMP. STOMP định nghĩa các frame như \`CONNECT\`, \`SUBSCRIBE\`, \`SEND\` và \`MESSAGE\`; destination cho biết message được gửi đến đâu.

### 7.1. Cấu hình endpoint và broker

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
    }
}
~~~

- Client kết nối WebSocket tại endpoint \`/ws\`.
- Destination bắt đầu bằng \`/app\` được định tuyến đến các phương thức \`@MessageMapping\`.
- Destination bắt đầu bằng \`/topic\` hoặc \`/queue\` được chuyển đến broker đã cấu hình.
- \`/topic\` thường được dùng theo quy ước cho publish-subscribe; \`/queue\` thường được dùng cho point-to-point. Trong STOMP, ý nghĩa destination do broker quyết định; hai tiền tố này không tự có ý nghĩa đặc biệt trong simple broker ngoài quy tắc định tuyến đã cấu hình.

### 7.2. Nhận yêu cầu và phát kết quả đến topic

~~~java
public record NoticeCommand(String text) {
}

public record Notice(String text) {
}

@Controller
public class NoticeController {

    @MessageMapping("/notices")
    @SendTo("/topic/notices")
    public Notice publish(NoticeCommand command) {
        return new Notice(command.text());
    }
}
~~~

Client gửi STOMP frame đến \`/app/notices\`. Spring định tuyến frame đến \`NoticeController.publish\`; kết quả trả về được gửi đến \`/topic/notices\`. Broker phân phối message cho các client đang đăng ký destination đó. Cần cấu hình message converter phù hợp nếu payload được trao đổi dưới dạng JSON.

Ví dụ frame phía client (ký hiệu \`^@\` biểu thị byte kết thúc frame STOMP):

~~~text
SUBSCRIBE
id:notice-sub-1
destination:/topic/notices

^@

SEND
destination:/app/notices
content-type:application/json

{"text":"Bảo trì lúc 22:00"}
^@
~~~

### 7.3. Phát từ service hoặc thành phần bất kỳ

Không cần một client gửi message trước. Một service, scheduled task hoặc HTTP controller cũng có thể phát đến broker bằng \`SimpMessagingTemplate\`:

~~~java
@Component
public class NoticePublisher {

    private final SimpMessagingTemplate messagingTemplate;

    public NoticePublisher(SimpMessagingTemplate messagingTemplate) {
        this.messagingTemplate = messagingTemplate;
    }

    public void publish(Notice notice) {
        messagingTemplate.convertAndSend("/topic/notices", notice);
    }
}
~~~

\`convertAndSend\` chuyển payload thành message rồi gửi đến destination. Dùng \`convertAndSendToUser(user, destination, payload)\` hoặc \`@SendToUser\` khi cần gửi riêng cho người dùng đã xác thực; không lấy danh tính người nhận từ một user ID không đáng tin trong payload.

### 7.4. Simple broker và broker relay

\`enableSimpleBroker\` bật broker tích hợp trong Spring. Broker này lưu subscription trong bộ nhớ và broadcast đến client đang kết nối có destination phù hợp. Nó hữu ích để học, phát triển và triển khai trường hợp đơn giản, nhưng chỉ hỗ trợ một phần lệnh STOMP, không hỗ trợ ACK/receipt theo đầy đủ giao thức và không phù hợp cho clustering.

Khi cần broker chuyên dụng hoặc nhiều instance ứng dụng, cấu hình STOMP broker relay, ví dụ:

~~~java
registry.enableStompBrokerRelay("/topic", "/queue");
~~~

Relay mở kết nối TCP đến broker bên ngoài (chẳng hạn RabbitMQ hoặc ActiveMQ), chuyển message lên broker và chuyển message nhận về đến các WebSocket client. Cần cấu hình host, port, tài khoản, quyền truy cập và chính sách vận hành của broker. Relay giúp mở rộng khả năng broadcast, nhưng độ bền, xác nhận, retry và lưu trữ vẫn phụ thuộc cấu hình thực tế của broker.

Luồng STOMP phổ biến:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant I as clientInboundChannel
    participant H as @MessageMapping
    participant B as Broker
    participant O as clientOutboundChannel
    C->>I: SUBSCRIBE /topic/notices
    I->>B: Đăng ký subscription
    C->>I: SEND /app/notices
    I->>H: Định tuyến đến controller
    H->>B: Gửi kết quả qua brokerChannel
    B->>O: Broadcast đến subscriber phù hợp
    O->>C: STOMP MESSAGE
~~~

## 8. Chọn cơ chế phù hợp

| Cơ chế | Phạm vi | Khi nên dùng | Giới hạn chính |
| --- | --- | --- | --- |
| \`ExecutorSubscribableChannel\` | Trong một ứng dụng | Nhiều handler cần nhận message qua abstraction của Spring Messaging | Không có broker hoặc lưu trữ bền vững mặc định |
| \`ApplicationEventPublisher\` + \`@EventListener\` | Trong một ApplicationContext | Thông báo thay đổi nghiệp vụ giữa các bean | Không truyền message qua mạng; mặc định đồng bộ |
| STOMP + simple broker | Server đến các WebSocket client đang kết nối | Dashboard, chat hoặc thông báo thời gian thực ở quy mô đơn giản | Subscription ở bộ nhớ; không clustering và không đủ tính năng của broker đầy đủ |
| STOMP broker relay | Server, broker bên ngoài và WebSocket client | Cần broker chuyên dụng, nhiều instance hoặc tính năng broker nâng cao | Cần vận hành broker và cấu hình kết nối, bảo mật |
| Spring Integration \`PublishSubscribeChannel\` | Luồng tích hợp trong ứng dụng | Xây dựng integration flow với các channel, router, transformer và handler | Cần thêm Spring Integration |

Không cần dựng broker cho mọi trường hợp. Nếu các bean trong cùng ứng dụng chỉ cần thông báo cho nhau, Application Events thường đủ. Nếu cần abstraction message channel và handler, dùng Spring Messaging. Nếu cần client qua mạng hoặc phân phối giữa nhiều tiến trình, dùng STOMP cùng broker phù hợp.

## 9. Độ tin cậy, transaction và bảo mật

### 9.1. Độ tin cậy và xử lý lỗi

- Xác định rõ điều gì được coi là thành công: channel nhận message, handler hoàn tất hay broker đã xác nhận lưu message là các mức khác nhau.
- Thiết kế subscriber có tính idempotent. Nếu broker có thể gửi lại một message, cùng một event không được làm lặp tác động nghiệp vụ.
- Đặt event ID và correlation ID để truy vết, đối chiếu và phát hiện trùng lặp.
- Với broker bên ngoài, cấu hình acknowledgement, retry, dead-letter queue và thời gian lưu trữ theo yêu cầu nghiệp vụ và khả năng của broker.
- Nếu phải cập nhật database và phát event như một thao tác nhất quán, cân nhắc Transactional Outbox. Ghi thay đổi nghiệp vụ và bản ghi outbox trong cùng transaction; một tiến trình riêng chuyển outbox sang broker.
- Không coi simple broker hoặc channel trong bộ nhớ là hàng đợi bền vững. Khi ứng dụng dừng, subscription hoặc message chưa xử lý có thể mất.

### 9.2. Transaction và thứ tự xử lý

Listener đồng bộ của Application Events mặc định chạy trong thread phát event và có thể tham gia transaction context hiện tại. Nếu listener phải đọc dữ liệu sau commit, dùng \`@TransactionalEventListener\` với phase \`AFTER_COMMIT\`. Nếu xử lý bất đồng bộ, transaction của publisher không tự kéo dài sang thread mới.

Với nhiều subscriber chạy song song, thứ tự hoàn tất không được đảm bảo. Nếu một nghiệp vụ cần tuần tự theo đơn hàng hoặc tài khoản, hãy xác định khóa phân vùng và cơ chế tuần tự hóa; không dựa vào thứ tự thread được scheduler chọn.

### 9.3. Bảo mật

- Xác thực kết nối WebSocket và phân quyền riêng cho các thao tác STOMP \`SEND\` và \`SUBSCRIBE\`.
- Chỉ cho phép client đăng ký destination mà họ được quyền đọc; không dựa vào việc destination có tên khó đoán.
- Kiểm tra và validate payload ở server, kể cả khi client đã kiểm tra trước.
- Dùng \`Principal\` của phiên đã xác thực để định tuyến message riêng cho user.
- Không đưa access token, mật khẩu, dữ liệu cá nhân hoặc payload nhạy cảm vào log message.
- Với broker relay, giới hạn quyền của tài khoản broker theo destination và môi trường.

## 10. Lỗi thường gặp

| Biểu hiện | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Không có subscriber nhận message | Sai destination, handler chưa subscribe hoặc broker chưa hoạt động | Kiểm tra nơi đăng ký, destination và trạng thái broker |
| Client kết nối được nhưng không thấy broadcast | Client chưa gửi \`SUBSCRIBE\`, sai prefix hoặc không có quyền đọc | Kiểm tra frame SUBSCRIBE, cấu hình broker và security rules |
| Controller không được gọi | Client gửi đến \`/topic\` thay vì prefix ứng dụng như \`/app\` | Gửi đến destination khớp \`@MessageMapping\` |
| Một listener làm chậm publisher | Handler đồng bộ chạy trên thread gửi | Dùng executor có giới hạn hoặc tách công việc dài |
| Gửi thành công nhưng subscriber xử lý lỗi | Dispatch bất đồng bộ chỉ xác nhận việc đưa task vào executor | Theo dõi lỗi ở thread xử lý và cấu hình error handler |
| Message biến mất sau khi restart | Dùng channel hoặc simple broker lưu trạng thái trong bộ nhớ | Dùng broker có persistence và cấu hình durability phù hợp |
| Một sự kiện gây tác động hai lần | Retry hoặc redelivery nhưng consumer không idempotent | Dùng event ID và lưu dấu xử lý đã hoàn tất |
| Không broadcast giữa các instance | Mỗi instance đang dùng simple broker riêng | Dùng broker bên ngoài qua broker relay |

## 11. Checklist triển khai

- [ ] Xác định rõ message là thông báo fan-out hay công việc point-to-point.
- [ ] Chọn Application Events, Spring Messaging hay STOMP theo phạm vi trao đổi.
- [ ] Định nghĩa payload có kiểu, header cần thiết, event ID và correlation ID.
- [ ] Chọn đồng bộ hay bất đồng bộ; cấu hình executor có giới hạn nếu cần.
- [ ] Quy định cách xử lý lỗi, retry, trùng lặp và thứ tự.
- [ ] Nếu có database và broker, xem xét Transactional Outbox hoặc phát event sau commit.
- [ ] Bảo vệ destination và xác thực quyền gửi/đăng ký.
- [ ] Kiểm tra trường hợp không có subscriber, subscriber chậm, broker mất kết nối và ứng dụng khởi động lại.
- [ ] Theo dõi số lượng message, độ trễ, lỗi handler và trạng thái broker.

## 12. Tài liệu tham khảo

- [Spring Framework — Flow of Messages](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/message-flow.html)
- [Spring Framework — Sending Messages](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-send.html)
- [Spring Framework — Simple Broker](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-simple-broker.html)
- [Spring Framework — External Broker](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-broker-relay.html)
- [Spring Framework API — ExecutorSubscribableChannel](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/support/ExecutorSubscribableChannel.html)
- [Spring Framework — Application Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Spring Integration — Channel Configuration](https://docs.spring.io/spring-integration/reference/channel/configuration.html)
