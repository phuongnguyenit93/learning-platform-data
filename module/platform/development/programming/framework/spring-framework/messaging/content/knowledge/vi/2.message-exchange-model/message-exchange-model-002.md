# Trao đổi trong bộ nhớ và trao đổi qua mạng trong Spring Framework

## 1. Bức tranh tổng thể

Messaging là cách một thành phần gửi thông tin cho một hoặc nhiều thành phần khác thông qua một thông điệp. Bên gửi không nhất thiết phải biết chi tiết bên nhận được triển khai ở đâu hoặc chạy trên luồng nào. Trong Spring, cần phân biệt ba lớp:

- **Mô hình thông điệp:** **Message<T>** chứa payload và headers.
- **Điểm gửi/nhận trong ứng dụng:** **MessageChannel**, **SubscribableChannel**, **PollableChannel** và **MessageHandler**.
- **Cơ chế vận chuyển:** lời gọi trong cùng JVM, WebSocket/STOMP, JMS hoặc một broker/protocol khác.

Một đối tượng **Message<T>** thường gồm:

- **Payload:** dữ liệu nghiệp vụ, ví dụ **OrderCreated**, chuỗi hoặc DTO.
- **Headers:** metadata như **id**, **timestamp**, **contentType**, **correlationId**, thông tin nguồn hoặc khóa định tuyến.

**MessageHeaders** là cấu trúc header bất biến sau khi thông điệp được tạo; điều đó không làm payload tự động bất biến. Nếu payload là một object có thể thay đổi và nhiều luồng cùng truy cập, ứng dụng vẫn cần bảo vệ dữ liệu hoặc tạo bản sao phù hợp.

**MessageChannel** định nghĩa nơi gửi thông điệp qua phương thức **send**. **SubscribableChannel** cho phép đăng ký một hay nhiều **MessageHandler**; **PollableChannel** cho phép bên nhận chủ động gọi **receive**. Các interface này mô tả cách trao đổi trong ứng dụng, tự chúng không khẳng định dữ liệu sẽ đi qua mạng.

Có thể tạo thông điệp có metadata bằng **MessageBuilder**:

~~~java
Message<String> message = MessageBuilder
    .withPayload("order-42")
    .setHeader("correlationId", "corr-001")
    .build();
~~~

## 2. Trao đổi trong bộ nhớ (in-memory)

Trao đổi trong bộ nhớ diễn ra bên trong cùng một tiến trình Java. Producer gọi một API Spring hoặc gửi vào channel; listener/handler được gọi trong chính JVM đó. Không cần socket, broker từ xa hay serialize payload để truyền qua mạng.

### 2.1. Application events

Spring cung cấp **ApplicationEventPublisher** để một bean phát sự kiện và **@EventListener** để bean khác lắng nghe:

~~~java
public record OrderCreated(String orderId) {}

@Component
class OrderAuditListener {
    @EventListener
    public void onOrderCreated(OrderCreated event) {
        System.out.println("Created: " + event.orderId());
    }
}

@Service
class OrderService {
    private final ApplicationEventPublisher events;

    OrderService(ApplicationEventPublisher events) {
        this.events = events;
    }

    public void create(String orderId) {
        // Lưu đơn hàng tại đây.
        events.publishEvent(new OrderCreated(orderId));
    }
}
~~~

Mặc định, **SimpleApplicationEventMulticaster** gọi listener đồng bộ trên luồng phát sự kiện. Vì vậy, listener chạy lâu có thể làm chậm **create**; lỗi từ listener đồng bộ cũng có thể ảnh hưởng đến luồng phát sự kiện. Có thể cấu hình executor cho event multicaster hoặc dùng **@Async** khi thực sự cần xử lý bất đồng bộ. Khi dùng bất đồng bộ, cần cấu hình executor, giới hạn hàng đợi, cách xử lý exception và vòng đời tác vụ.

Event nội bộ không phải hàng đợi bền vững. Nếu tiến trình dừng, sự kiện chưa xử lý sẽ mất; Spring không tự lưu sự kiện để phát lại sau khi ứng dụng khởi động. Nếu sự kiện phụ thuộc vào transaction, cân nhắc **@TransactionalEventListener** với phase phù hợp, chẳng hạn **AFTER_COMMIT**, để listener chỉ chạy sau khi transaction commit. Cách này điều chỉnh thời điểm gọi listener, nhưng không tự tạo bảo đảm giao nhận nguyên tử giữa database và một broker bên ngoài.

### 2.2. Message channel trong cùng JVM

Spring Messaging cung cấp abstraction channel và các triển khai hỗ trợ dispatch trong tiến trình. Ví dụ **ExecutorSubscribableChannel** chuyển thông điệp tới các handler đã đăng ký. Với constructor mặc định, không có executor riêng nên việc dispatch diễn ra đồng bộ; khi truyền một **Executor**, handler có thể được chạy trên executor đó.

Ví dụ dưới đây là chương trình Java 17+ có thể chạy độc lập với Maven:

**Cấu trúc dự án**

~~~text
in-memory-demo/
  pom.xml
  src/
    main/
      java/
        demo/
          InMemoryMessagingDemo.java
~~~

**pom.xml**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>in-memory-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-messaging</artifactId>
            <version>6.2.0</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**src/main/java/demo/InMemoryMessagingDemo.java**

~~~java
package demo;

import org.springframework.messaging.Message;
import org.springframework.messaging.support.ExecutorSubscribableChannel;
import org.springframework.messaging.support.MessageBuilder;

public class InMemoryMessagingDemo {
    public static void main(String[] args) {
        ExecutorSubscribableChannel channel = new ExecutorSubscribableChannel();

        channel.subscribe(message -> {
            System.out.println("payload=" + message.getPayload());
            System.out.println(
                "correlationId=" + message.getHeaders().get("correlationId")
            );
        });

        Message<String> message = MessageBuilder
            .withPayload("order-42")
            .setHeader("correlationId", "demo-001")
            .build();

        if (!channel.send(message)) {
            throw new IllegalStateException("Message was not accepted");
        }
    }
}
~~~

Chạy từ thư mục **in-memory-demo**:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.InMemoryMessagingDemo
~~~

**stdout**

~~~text
payload=order-42
correlationId=demo-001
~~~

Ví dụ chỉ có một subscriber và dùng channel mặc định nên kết quả được in ngay trong luồng gọi **send**. Khi cấu hình executor, không nên giả định handler đã hoàn tất tại thời điểm **send** trả về. Giá trị boolean từ **send** thể hiện kết quả gửi/tiếp nhận ở channel, không phải xác nhận rằng nghiệp vụ phía consumer đã commit thành công.

### 2.3. Điểm mạnh và giới hạn

**Ưu điểm**

- Độ trễ thấp, ít chi phí hơn giao tiếp qua mạng.
- Dễ debug và kiểm thử vì producer, channel và handler cùng tiến trình.
- Không cần triển khai broker hay quản lý kết nối mạng.
- Có thể dùng event hoặc channel để giảm phụ thuộc trực tiếp giữa các bean.

**Giới hạn**

- Chỉ các thành phần trong cùng tiến trình mới trực tiếp tham gia; instance khác không tự nhận được event/channel message.
- Không có persistence mặc định, không có replay sau restart và không tự có dead-letter queue.
- Listener đồng bộ có thể chặn luồng gửi; executor có thể quá tải nếu tốc độ gửi lớn hơn tốc độ xử lý.
- Không có ranh giới mạng nên lỗi, timeout và bảo mật khác với giao tiếp giữa các dịch vụ.
- Payload dùng chung trong heap có thể bị thay đổi ngoài dự kiến nếu nhiều thành phần giữ cùng một tham chiếu.

Nếu cần các channel như **DirectChannel**, **QueueChannel** hoặc **PublishSubscribeChannel**, thường đó là các triển khai thuộc **Spring Integration** (package **org.springframework.integration.channel**). Spring Framework Messaging cung cấp các abstraction nền tảng; không nên nhầm các class của Spring Integration với API lõi của Spring Framework.

## 3. Trao đổi qua mạng

Trao đổi qua mạng xảy ra khi producer và consumer nằm ở các tiến trình hoặc máy khác nhau, hoặc khi client bên ngoài kết nối tới ứng dụng. Thông điệp phải đi qua một transport/protocol như WebSocket, STOMP hoặc JMS. Dữ liệu thường cần được chuyển đổi sang định dạng có thể truyền, ví dụ JSON hoặc định dạng mà broker hỗ trợ.

Mạng tạo ra ranh giới lỗi mới: kết nối có thể đứt, broker có thể ngừng hoạt động, request có thể timeout và consumer có thể xử lý lặp. Vì vậy, cần xác định rõ timeout, retry, xác nhận, định danh thông điệp, bảo mật và cách xử lý thông điệp lỗi.

### 3.1. WebSocket và STOMP

WebSocket tạo kết nối hai chiều tồn tại lâu giữa client và server. WebSocket cung cấp transport; nó không tự định nghĩa đầy đủ mô hình destination, subscription hay routing cho ứng dụng. STOMP bổ sung các frame và quy ước như **SEND**, **SUBSCRIBE** và destination. Spring WebSocket kết hợp Spring Messaging để định tuyến thông điệp tới controller và broker.

Ví dụ cấu hình tối thiểu:

~~~java
@Configuration
@EnableWebSocketMessageBroker
class WebSocketConfig implements WebSocketMessageBrokerConfigurer {

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

Controller nhận thông điệp từ client:

~~~java
@Controller
class ChatController {

    @MessageMapping("/chat.send")
    @SendTo("/topic/chat")
    public ChatMessage send(ChatMessage message) {
        return message;
    }
}

public record ChatMessage(String sender, String text) {}
~~~

Client kết nối tới endpoint **/ws**, gửi STOMP **SEND** tới **/app/chat.send** và đăng ký **SUBSCRIBE** tới **/topic/chat**. Spring loại bỏ application prefix **/app** khi tìm **@MessageMapping**; kết quả từ method được gửi tới destination trong **@SendTo**.

Ứng dụng cũng có thể chủ động đẩy dữ liệu bằng **SimpMessagingTemplate**:

~~~java
messagingTemplate.convertAndSend("/topic/orders", orderUpdate);
~~~

Trong cấu hình trên, **enableSimpleBroker** bật simple broker tích hợp trong ứng dụng. Client vẫn giao tiếp với server qua mạng, nhưng broker xử lý subscription nằm trong bộ nhớ của tiến trình Spring. Đây là lựa chọn gọn cho ứng dụng đơn giản hoặc môi trường phát triển; nó không cung cấp broker bền vững dùng chung cho nhiều instance và chỉ hỗ trợ một phần tính năng STOMP.

Khi cần broker bên ngoài, có thể cấu hình relay:

~~~java
registry.enableStompBrokerRelay("/topic", "/queue")
        .setRelayHost("localhost")
        .setRelayPort(61613);
~~~

Relay chuyển thông điệp giữa Spring và một STOMP broker tương thích, chẳng hạn broker được cấu hình STOMP endpoint. Broker bên ngoài có thể cung cấp khả năng mở rộng, lưu trữ, xác nhận và phân phối theo cấu hình của chính nó. Cần cấu hình thông tin đăng nhập, TLS, quyền truy cập destination, heartbeat và giới hạn kết nối cho môi trường thật.

Spring Boot thường dùng dependency **spring-boot-starter-websocket**; ứng dụng Spring Framework thuần cần các module tương ứng như **spring-websocket** và **spring-messaging**. Ví dụ cấu hình trên giả định ứng dụng đã có Spring application context và các bean MVC/WebSocket cần thiết.

### 3.2. JMS và broker

JMS là API nhắn tin hướng message broker. Spring Framework cung cấp tích hợp JMS trong module **spring-jms**, gồm **JmsTemplate** để gửi và **@JmsListener** để nhận:

~~~java
jmsTemplate.convertAndSend("orders.created", orderCreated);

@JmsListener(destination = "orders.created")
public void handle(OrderCreated event) {
    // Xử lý thông điệp.
}
~~~

Ứng dụng cần một JMS **ConnectionFactory**, cấu hình listener container và một JMS provider/broker phù hợp. Việc chuyển đổi object sang message phụ thuộc **MessageConverter**; khi giao tiếp giữa dịch vụ độc lập, nên chọn schema/định dạng rõ ràng như JSON thay vì phụ thuộc vào Java object serialization.

JMS định nghĩa API và một số mô hình giao nhận; persistence, redelivery, acknowledgment, transaction và dead-letter queue còn phụ thuộc provider cùng cấu hình. Không nên kết luận rằng mọi lệnh **convertAndSend** đều bảo đảm message đã được consumer xử lý thành công.

AMQP/RabbitMQ và Apache Kafka thường được tích hợp qua các dự án Spring riêng như **Spring AMQP** và **Spring for Apache Kafka**. Chúng có mô hình routing, partition, offset, acknowledgment và vận hành riêng; không phải mọi class của các dự án đó đều thuộc Spring Framework core.

## 4. So sánh hai mô hình

| Tiêu chí | Trong bộ nhớ | Qua mạng |
|---|---|---|
| Phạm vi | Cùng JVM/tiến trình | Nhiều tiến trình, máy hoặc client |
| Độ trễ | Thường thấp | Có thêm chi phí serialization, network và broker |
| Phụ thuộc | Bean, channel hoặc event trong ứng dụng | Transport, protocol, broker hoặc dịch vụ từ xa |
| Khả năng sống sót khi restart | Không có mặc định | Có thể có nếu broker được cấu hình persistence |
| Mở rộng ngang | Không tự chia sẻ event giữa instance | Có thể phân phối qua broker/cluster |
| Lỗi thường gặp | Listener chậm, executor đầy, exception trong tiến trình | Timeout, mất kết nối, broker lỗi, message lặp |
| Bảo mật | Chủ yếu theo ranh giới ứng dụng/JVM | Cần xác thực, phân quyền, TLS và kiểm soát mạng |
| Kiểm thử | Có thể kiểm thử trực tiếp bằng unit test | Thường cần kiểm thử integration với transport/broker |

Đừng đánh đồng **bất đồng bộ** với **qua mạng**. Một channel trong JVM có thể dùng executor để chạy handler bất đồng bộ. Ngược lại, một lời gọi HTTP qua mạng có thể vẫn là request-response đồng bộ từ góc nhìn caller. Hai trục cần đánh giá riêng là vị trí của các thành phần và cách điều phối luồng xử lý.

Cũng cần phân biệt **transport qua mạng** với **broker có persistence**. WebSocket tới simple broker của Spring là giao tiếp qua mạng giữa client và server, nhưng trạng thái broker vẫn nằm trong bộ nhớ server. Ngược lại, một broker có thể được cài đặt trên cùng máy để phát triển nhưng vẫn có mô hình giao tiếp và lưu trữ khác với event nội bộ.

## 5. Chọn mô hình nào?

- **Dùng ApplicationEventPublisher** khi một bean muốn thông báo sự kiện nghiệp vụ cho các listener trong cùng ứng dụng, ví dụ cập nhật cache hoặc ghi audit. Chọn listener đồng bộ nếu caller cần biết kết quả ngay; chọn async khi chấp nhận xử lý sau và đã cấu hình executor phù hợp.
- **Dùng Spring Messaging channel** khi cần abstraction message/handler bên trong một pipeline hoặc tích hợp với thành phần Spring sử dụng **Message<?>**.
- **Dùng WebSocket/STOMP** khi trình duyệt hoặc client cần kết nối hai chiều và nhận cập nhật trực tiếp, chẳng hạn chat, dashboard hoặc thông báo thời gian thực.
- **Dùng JMS hoặc broker chuyên dụng** khi các dịch vụ cần trao đổi mà không phải cùng chạy một tiến trình, cần tách thời gian hoạt động của producer/consumer hoặc cần khả năng lưu trữ và phân phối do broker cung cấp.
- **Dùng Spring AMQP/Kafka** khi bài toán cần các đặc tính routing, queue, exchange, partition, consumer group hoặc lưu event log của hệ sinh thái tương ứng.

Một quy tắc thực tế: bắt đầu với cơ chế nội bộ khi tất cả thành phần thuộc cùng ứng dụng và không cần giao nhận bền vững. Chuyển sang broker/transport khi cần vượt qua ranh giới tiến trình, triển khai độc lập, chia sẻ giữa nhiều instance hoặc có yêu cầu lưu trữ và xử lý lại.

## 6. Độ tin cậy và vận hành

Dù chọn mô hình nào, hãy làm rõ các câu hỏi sau trước khi đưa vào production:

1. **Ai sở hữu message?** Xác định producer, consumer, schema, version và ý nghĩa của từng header.
2. **Gửi thành công có nghĩa là gì?** **MessageChannel.send** trả về không đồng nghĩa với nghiệp vụ consumer đã commit. Với broker, phân biệt broker nhận message, consumer nhận message và consumer hoàn tất transaction.
3. **Có thể xử lý lặp không?** Retry hoặc redelivery có thể khiến cùng một message tới nhiều lần. Thiết kế consumer idempotent bằng message ID hoặc business key.
4. **Khi nào retry và khi nào chuyển lỗi?** Phân biệt lỗi tạm thời với lỗi dữ liệu; giới hạn số lần retry và định nghĩa dead-letter/quarantine flow khi broker hỗ trợ.
5. **Có cần thứ tự không?** Thứ tự chỉ được bảo đảm trong phạm vi và điều kiện cụ thể của channel/broker/partition; không giả định toàn hệ thống có thứ tự toàn cục.
6. **Có cần quan sát luồng xử lý không?** Dùng correlation ID/trace ID, log có cấu trúc, metric về throughput, latency, queue depth, retry và lỗi.
7. **Payload có an toàn và tương thích không?** Kiểm tra kích thước, schema, version, dữ liệu nhạy cảm và quyền truy cập. Không gửi object tùy ý qua ranh giới tin cậy.
8. **Có cần tính nguyên tử với database không?** Nếu cần lưu thay đổi nghiệp vụ và phát message như một thao tác bền vững, cân nhắc transactional outbox hoặc cơ chế tích hợp transaction phù hợp; chỉ phát event sau commit không giải quyết mọi trường hợp tiến trình dừng giữa hai thao tác.

Với in-memory async, cấu hình executor có giới hạn và chính sách từ chối tác vụ rõ ràng. Nếu hàng đợi không giới hạn, tải tăng đột biến có thể làm bộ nhớ tăng liên tục. Với broker, theo dõi queue/partition lag, kết nối, disk, redelivery và dead-letter. Bảo đảm xác thực, phân quyền theo destination/topic và mã hóa đường truyền khi thông điệp rời khỏi tiến trình.

## 7. Lỗi thiết kế thường gặp

- **Cho rằng MessageChannel luôn là network channel:** interface chỉ mô tả điểm gửi; phải xem implementation và adapter thực tế.
- **Cho rằng @EventListener mặc định chạy nền:** listener mặc định thường chạy đồng bộ trên luồng phát event.
- **Cho rằng simple broker là broker cluster:** simple broker tích hợp của Spring giữ trạng thái trong bộ nhớ ứng dụng; nhiều instance không tự chia sẻ subscription.
- **Coi send() là xác nhận xử lý:** kết quả gửi không thay thế acknowledgment hoặc kết quả transaction của consumer.
- **Dùng payload mutable giữa nhiều handler:** một handler thay đổi object có thể làm handler khác thấy dữ liệu đã bị sửa.
- **Không đặt correlation ID hoặc không có idempotency:** khó truy vết một luồng message và khó xử lý an toàn khi retry.
- **Dùng event nội bộ cho tác vụ phải tồn tại qua restart:** event in-memory không phải durable queue; chọn broker/outbox nếu yêu cầu nghiệp vụ cần điều đó.
- **Nhầm Spring Framework với Spring Integration/Spring AMQP/Spring Kafka:** kiểm tra dependency và package để biết abstraction hoặc implementation đến từ dự án nào.

## 8. Kết luận

Trao đổi trong bộ nhớ phù hợp cho phối hợp nội bộ trong một tiến trình: đơn giản, nhanh và ít thành phần vận hành, nhưng không có persistence hay khả năng phân phối giữa instance theo mặc định. Trao đổi qua mạng phù hợp khi client hoặc dịch vụ độc lập cần giao tiếp; nó mở rộng phạm vi kết nối nhưng đưa thêm serialization, lỗi mạng, bảo mật và yêu cầu vận hành.

Spring cung cấp abstraction message để giảm phụ thuộc giữa producer và consumer. Lựa chọn đúng phụ thuộc vào ranh giới triển khai, độ tin cậy, độ trễ, khả năng mở rộng và mức độ độc lập mà hệ thống cần.