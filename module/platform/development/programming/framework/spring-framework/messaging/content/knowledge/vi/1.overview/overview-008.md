# Phạm vi của spring-messaging, spring-jms và spring-websocket

Ba module này cùng phục vụ bài toán trao đổi thông điệp trong ứng dụng Spring, nhưng mỗi module giải quyết một lớp khác nhau:

- **spring-messaging** cung cấp mô hình thông điệp và các hợp đồng xử lý chung để producer, channel và consumer ít phụ thuộc vào nhau.
- **spring-jms** kết nối ứng dụng Spring với hệ thống triển khai Jakarta Messaging (JMS), chẳng hạn một message broker hỗ trợ JMS.
- **spring-websocket** cung cấp giao tiếp WebSocket trên Servlet stack; khi dùng STOMP, module này phối hợp với spring-messaging để định tuyến thông điệp giữa trình duyệt và ứng dụng.

Hiểu ranh giới này giúp chọn đúng API, dependency và cơ chế đảm bảo giao nhận. Cả ba đều là thành phần tích hợp ở phía ứng dụng; chúng không tự biến ứng dụng thành một message broker có lưu trữ bền vững.

## 1. Messaging giải quyết vấn đề gì?

Trong mô hình HTTP request-response, client gửi request đến một endpoint và thường chờ response trong cùng lượt tương tác. Mô hình này phù hợp với thao tác cần kết quả ngay, ví dụ đọc thông tin hoặc cập nhật một tài nguyên.

Messaging tách bên gửi khỏi bên nhận bằng một thông điệp. Bên gửi tạo thông điệp và chuyển nó đến một đích; bên nhận xử lý khi có thể. Tùy công nghệ, thông điệp có thể được lưu trong broker, phân phối đến nhiều subscriber hoặc truyền qua một kết nối đang mở.

Một message thường cần ít nhất hai phần:

- **Payload:** dữ liệu nghiệp vụ, ví dụ mã đơn hàng hoặc nội dung sự kiện.
- **Headers:** metadata như loại sự kiện, correlation ID, content type, thời điểm hoặc thông tin định tuyến.

Messaging hữu ích khi các thành phần cần giảm phụ thuộc thời gian, xử lý bất đồng bộ, phát sự kiện cho nhiều bên hoặc cập nhật giao diện liên tục. Tuy nhiên, messaging cũng đưa vào các vấn đề cần thiết kế rõ: thứ tự xử lý, retry, duplicate, timeout, xác nhận đã nhận, bảo mật và khả năng quan sát.

## 2. So sánh nhanh ba module

| Module | Trách nhiệm chính | API tiêu biểu | Thành phần bên ngoài |
|---|---|---|---|
| spring-messaging | Mô hình message, channel, handler, converter và messaging template | Message, MessageChannel, MessageHandler, MessageBuilder, MessageConverter | Không bắt buộc có broker nếu chỉ dùng abstraction trong ứng dụng |
| spring-jms | Tích hợp ứng dụng với Jakarta Messaging | JmsTemplate, JmsMessagingTemplate, @JmsListener, JmsTransactionManager | JMS ConnectionFactory và một JMS provider/broker |
| spring-websocket | Kết nối WebSocket, SockJS và messaging qua STOMP | WebSocketHandler, WebSocketConfigurer, @EnableWebSocketMessageBroker, @MessageMapping, SimpMessagingTemplate | WebSocket client; broker STOMP ngoài là tùy chọn khi dùng broker relay |

Có thể ghi nhớ theo ba câu hỏi:

1. Ứng dụng biểu diễn và chuyển một message như thế nào? Đây là trọng tâm của **spring-messaging**.
2. Ứng dụng gửi hoặc nhận message qua một JMS provider như thế nào? Đây là trọng tâm của **spring-jms**.
3. Trình duyệt duy trì kết nối hai chiều và gửi/nhận message theo thời gian thực như thế nào? Đây là trọng tâm của **spring-websocket**.

## 3. spring-messaging: mô hình thông điệp dùng chung

### 3.1. Các abstraction cốt lõi

Package chính là org.springframework.messaging. Những abstraction quan trọng gồm:

- **Message<T>:** đại diện một message có payload kiểu T và tập headers.
- **MessageHeaders:** tập metadata gắn với message.
- **MessageChannel:** hợp đồng gửi message, giúp bên gửi không cần biết handler cụ thể nào sẽ xử lý.
- **MessageHandler:** hợp đồng nhận và xử lý một message.
- **SubscribableChannel:** channel quản lý các handler đăng ký nhận message.
- **PollableChannel:** channel cho phép consumer chủ động lấy message bằng thao tác polling.
- **MessageBuilder:** tạo message và thiết lập headers.
- **MessageConverter:** chuyển đổi payload giữa dạng truyền tải và kiểu Java mà handler mong muốn.
- **GenericMessagingTemplate** (trong `org.springframework.messaging.core`): implementation của các messaging operations, phân giải tên destination thành `MessageChannel` để gửi, nhận và thực hiện request-reply.

Một luồng xử lý khái quát:

~~~text
Producer
   |
   | tạo Message(payload, headers)
   v
MessageChannel
   |
   v
MessageHandler
   |
   v
Business logic
~~~

Channel tạo ranh giới giữa producer và consumer. Producer chỉ cần biết nơi gửi; handler tập trung vào việc xử lý. Nhờ vậy có thể thay đổi cách phân phối message hoặc cách đăng ký handler mà ít phải sửa business logic.

### 3.2. Tạo message bằng Java

Ví dụ sau minh họa payload và header. Đây là chương trình nhỏ cần có dependency spring-messaging trên classpath; nó không cần kết nối broker.

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

public class MessageModelDemo {

    public static void main(String[] args) {
        Message<String> message = MessageBuilder
                .withPayload("order-42")
                .setHeader("eventType", "OrderCreated")
                .build();

        System.out.println(message.getPayload());
        System.out.println(message.getHeaders().get("eventType"));
    }
}
~~~

Kết quả:

~~~text
order-42
OrderCreated
~~~

Ví dụ cho thấy message không chỉ chứa dữ liệu nghiệp vụ. Header cho phép bổ sung metadata mà không phải nhồi các trường định tuyến hoặc correlation vào payload. Khi thiết kế contract, payload vẫn nên mô tả dữ liệu nghiệp vụ; header nên dành cho metadata phục vụ truyền tải và xử lý.

### 3.3. Conversion, handler và annotation

Message có thể đến từ nhiều nguồn với định dạng khác nhau. MessageConverter chịu trách nhiệm chuyển đổi payload, ví dụ từ JSON hoặc text sang một kiểu Java. Việc chọn converter cần nhất quán với content type và contract giữa producer với consumer.

Các API xử lý method còn cung cấp annotation như:

- **@MessageMapping:** ánh xạ message đến method dựa trên destination hoặc điều kiện định tuyến.
- **@Payload:** chỉ rõ tham số lấy từ payload.
- **@Header** và **@Headers:** lấy một header hoặc toàn bộ headers.
- **@SendTo:** chỉ định destination nhận giá trị trả về của handler trong các mô hình messaging hỗ trợ annotation này.

Những annotation này không tự tạo ra một broker. Chúng là cơ chế ánh xạ và gọi method khi một hạ tầng messaging tương ứng đã được cấu hình.

### 3.4. Ranh giới của spring-messaging

spring-messaging cung cấp abstraction và một số thành phần hỗ trợ giao tiếp, nhưng bản thân module không bảo đảm:

- message được lưu bền vững sau khi ứng dụng dừng;
- message được giao đúng một lần;
- consumer luôn nhận được message khi mất kết nối;
- thứ tự toàn cục giữa nhiều producer hoặc consumer;
- retry, dead-letter queue hay retention theo chính sách nghiệp vụ.

Các bảo đảm này phụ thuộc vào transport, broker, cấu hình và logic ứng dụng. Nếu chỉ tạo Message và gọi một channel nội bộ, không có nghĩa message đã được đưa vào một hệ thống hàng đợi phân tán.

## 4. spring-jms: tích hợp với Jakarta Messaging

### 4.1. JMS nằm ở đâu trong kiến trúc?

JMS là API chuẩn Java cho messaging giữa các ứng dụng hoặc thành phần. Spring cung cấp lớp hỗ trợ để code nghiệp vụ không phải lặp lại việc tạo connection, session, producer, consumer và xử lý các ngoại lệ JMS.

Một ứng dụng Spring sử dụng JMS cần một **ConnectionFactory** kết nối đến một JMS provider. Provider thực hiện việc quản lý destination, truyền message và các chính sách giao nhận tương ứng. Spring Framework không đóng vai trò thay thế provider đó.

Hai kiểu destination thường gặp:

- **Queue:** mô hình point-to-point; message được xử lý bởi một consumer trong nhóm cạnh tranh theo cơ chế của provider.
- **Topic:** mô hình publish-subscribe; message được phân phối đến các subscription theo cấu hình của provider.

Đặc tính lưu trữ, durable subscription, redelivery, selector và giới hạn tài nguyên phụ thuộc vào JMS provider cùng cấu hình triển khai.

### 4.2. Gửi và nhận đồng bộ bằng JmsTemplate

JmsTemplate là API trung tâm cho thao tác gửi và nhận đồng bộ. Template quản lý vòng đời các tài nguyên JMS cần thiết, chuyển đổi message và cung cấp các phương thức tiện dụng.

Ví dụ gọi từ một Spring bean đã được inject JmsTemplate:

~~~java
jmsTemplate.convertAndSend("orders", "order-42");
~~~

Lệnh trên gửi payload đến destination có tên orders. Để dùng được, ứng dụng phải cấu hình ConnectionFactory và destination phù hợp; tên destination không tự bảo đảm broker đã tạo queue hoặc topic vật lý.

JmsTemplate cũng hỗ trợ nhận đồng bộ. Cần cấu hình receive timeout rõ ràng vì thao tác nhận có thể làm thread gọi chờ message. Không nên để một request xử lý HTTP thông thường bị chặn vô thời hạn chỉ vì đang chờ một message.

### 4.3. Nhận bất đồng bộ bằng @JmsListener

Với xử lý bất đồng bộ, Spring có thể đăng ký method làm listener endpoint:

~~~java
@Component
public class OrderListener {

    @JmsListener(destination = "orders")
    public void handle(String payload) {
        System.out.println("Received order: " + payload);
    }
}
~~~

Để annotation hoạt động trong cấu hình Spring Framework thuần, bật hỗ trợ bằng @EnableJms và cung cấp listener container factory cùng ConnectionFactory:

~~~java
@Configuration
@EnableJms
public class JmsConfiguration {

    @Bean
    public DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
            ConnectionFactory connectionFactory) {

        DefaultJmsListenerContainerFactory factory =
                new DefaultJmsListenerContainerFactory();

        factory.setConnectionFactory(connectionFactory);
        factory.setSessionTransacted(true);
        return factory;
    }
}
~~~

Đây là các mảnh cấu hình minh họa, không phải ứng dụng độc lập. ConnectionFactory phải được cung cấp bởi JMS provider hoặc cấu hình nền tảng tương ứng. Trong Spring Boot, starter và auto-configuration có thể tạo một phần hạ tầng này khi dependency và thuộc tính kết nối đã được khai báo.

Một listener container chịu trách nhiệm nhận message, quản lý thread, gọi listener, phối hợp session và xử lý vòng đời kết nối. Hai triển khai tiêu biểu là SimpleMessageListenerContainer và DefaultMessageListenerContainer; chúng có khả năng điều chỉnh tải và tham gia transaction khác nhau. Cần chọn dựa trên môi trường, transaction manager và yêu cầu vận hành.

### 4.4. Conversion và kết nối với Spring Messaging

JMS có kiểu message riêng của Jakarta Messaging. Spring cung cấp MessageConverter để chuyển giữa JMS message và đối tượng Java. Khi listener nhận một kiểu payload cụ thể, converter phải biết cách tạo kiểu đó từ message đến.

JmsMessagingTemplate là cầu nối giữa JmsTemplate và abstraction org.springframework.messaging.Message. Nhờ đó code có thể sử dụng mô hình message chung của Spring khi gửi qua JMS. Đây là điểm giao giữa hai module, không có nghĩa mọi MessageChannel nội bộ đều tự động trở thành JMS destination.

### 4.5. Transaction, acknowledgement và độ tin cậy

JMS có các chế độ acknowledgement và transaction. Spring hỗ trợ transaction cục bộ qua JmsTransactionManager cho một ConnectionFactory. Khi cần transaction phân tán qua nhiều resource, phải cấu hình JTA và các resource XA tương thích; không thể chỉ thêm @Transactional rồi mặc định có atomicity xuyên broker và database.

Một số nguyên tắc vận hành quan trọng:

1. **Không mặc định AUTO_ACKNOWLEDGE là đủ tin cậy.** Cấu hình acknowledgement mặc định có thể khiến message bị xác nhận dù xử lý nghiệp vụ thất bại, tùy listener container và provider.
2. **Thiết kế listener có thể nhận message trùng.** Broker có thể redeliver khi lỗi hoặc khi tiến trình dừng ở thời điểm không thuận lợi. Dùng message ID hoặc business key để kiểm tra tính idempotent.
3. **Chọn transaction đúng phạm vi.** Transaction JMS cục bộ không tự bao gồm transaction database. Nếu cần phối hợp nhiều resource, phải xác định rõ transaction manager và khả năng XA.
4. **Đặt chính sách retry và lỗi có chủ đích.** Xác định số lần thử, backoff, dead-letter destination và cách xử lý message không hợp lệ theo năng lực provider.
5. **Theo dõi consumer lag và trạng thái broker.** Một listener chạy nhưng không xử lý kịp vẫn có thể làm queue tăng liên tục.

Không nên tuyên bố hệ thống có exactly-once chỉ vì đã bật transaction. Thực tế thường cần kết hợp transaction phù hợp, idempotency và quy trình phục hồi.

## 5. spring-websocket: giao tiếp hai chiều với client

### 5.1. WebSocket khác HTTP như thế nào?

WebSocket bắt đầu bằng một HTTP handshake. Client gửi yêu cầu nâng cấp giao thức; nếu server chấp nhận, kết nối TCP được giữ mở để client và server có thể gửi dữ liệu hai chiều trên cùng kết nối.

HTTP thường định tuyến theo URL, method và headers cho từng request. WebSocket thường chỉ dùng URL ở bước kết nối; sau đó nhiều message đi qua cùng một kết nối. WebSocket là giao thức truyền tải mức thấp và không tự định nghĩa ý nghĩa nghiệp vụ của payload. Client và server phải thống nhất định dạng hoặc sử dụng một sub-protocol như STOMP.

WebSocket phù hợp khi cần cập nhật thường xuyên với độ trễ thấp, ví dụ chat, bảng điều khiển trực tiếp, cộng tác hoặc trạng thái giao dịch. Với dữ liệu chỉ cần làm mới vài phút một lần, polling hoặc Server-Sent Events có thể đơn giản hơn.

### 5.2. Raw WebSocket API

Nếu ứng dụng cần giao thức riêng, Spring cho phép đăng ký WebSocketHandler và xử lý frame trực tiếp. Các API thường gặp gồm WebSocketHandler, TextWebSocketHandler, WebSocketConfigurer và @EnableWebSocket.

Ở mức này, ứng dụng tự quyết định:

- cấu trúc payload và cách phân loại message;
- quy tắc xác thực, gắn người dùng với session và phân quyền;
- cách broadcast hoặc định tuyến đến session;
- heartbeat, timeout, reconnect và xử lý session đóng;
- giới hạn kích thước frame và kiểm soát tải.

Raw WebSocket phù hợp khi cần kiểm soát giao thức hoặc chỉ trao đổi một số loại message đơn giản. Đổi lại, ứng dụng phải tự thiết kế nhiều quy ước mà một messaging sub-protocol có thể cung cấp sẵn.

### 5.3. SockJS và khả năng fallback

SockJS cung cấp mô hình client-server tương tự WebSocket và có thể dùng các transport thay thế khi môi trường không hỗ trợ WebSocket. Có thể bật fallback cho endpoint bằng:

~~~java
registry.addEndpoint("/ws").withSockJS();
~~~

Fallback không làm mọi transport có cùng đặc tính hiệu năng hoặc vận hành. Khi triển khai sau reverse proxy, load balancer hoặc nền tảng cloud, cần xác minh đường truyền WebSocket Upgrade, timeout của kết nối dài và cấu hình sticky session nếu kiến trúc yêu cầu.

### 5.4. STOMP trên WebSocket

STOMP là một messaging sub-protocol. Nó định nghĩa các frame như CONNECT, SEND, SUBSCRIBE, MESSAGE và DISCONNECT, cùng destination để client và server thống nhất cách gửi, đăng ký nhận và phân phối message.

Khi dùng STOMP, spring-websocket cung cấp transport và hạ tầng broker messaging; spring-messaging cung cấp các abstraction Message, channel, handler, annotation và template được sử dụng trong luồng xử lý.

Cấu hình tối thiểu:

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

Controller nhận message từ client:

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

Một client STOMP có thể thực hiện luồng sau:

1. Kết nối WebSocket đến endpoint /ws.
2. Gửi frame SEND đến destination /app/chat.send.
3. Spring định tuyến message vào method được ánh xạ bởi @MessageMapping.
4. Giá trị trả về được gửi đến /topic/chat.
5. Các client đã SUBSCRIBE /topic/chat nhận message do broker phân phối.

Các prefix /app, /topic và /queue là quy ước định tuyến trong cấu hình ví dụ. Chúng không phải destination JMS và không tự tạo queue/topic trong một JMS broker.

### 5.5. Simple broker và external broker relay

Spring có thể dùng simple broker chạy trong bộ nhớ của ứng dụng. Cách này tiện cho học tập, thử nghiệm và trường hợp nhỏ, nhưng không cung cấp đầy đủ năng lực của một broker độc lập có lưu trữ bền vững và quản lý cụm.

Khi cần broker chuyên dụng, cấu hình STOMP broker relay để chuyển các frame phù hợp đến một broker STOMP bên ngoài. Khi đó cần quản lý địa chỉ kết nối, thông tin xác thực, heartbeat, giới hạn kết nối và khả năng phục hồi của broker.

Không nên chọn simple broker chỉ vì ứng dụng đã dùng WebSocket rồi kỳ vọng nó có các tính năng như durable subscription, replay hoặc dead-letter queue. Hãy kiểm tra rõ năng lực broker và yêu cầu giao nhận thực tế.

### 5.6. Gửi message đến client từ server

SimpMessagingTemplate cho phép một service gửi message đến destination STOMP, kể cả khi message được phát sinh từ một luồng xử lý khác thay vì method @MessageMapping:

~~~java
simpMessagingTemplate.convertAndSend("/topic/orders", orderEvent);
~~~

Cách này hữu ích cho cập nhật trạng thái hoặc thông báo đến nhiều client. Với destination riêng cho người dùng, cần dùng cơ chế user destination và cấu hình bảo mật tương ứng; không tự ghép tên người dùng vào chuỗi destination mà bỏ qua kiểm soát truy cập.

### 5.7. Bảo mật và vận hành WebSocket

WebSocket giữ kết nối lâu dài nên cần thiết kế vòng đời và quyền truy cập rõ ràng:

- Xác thực ở handshake hoặc theo cơ chế xác thực STOMP được ứng dụng hỗ trợ.
- Kiểm tra Origin và cấu hình CORS phù hợp với client được phép kết nối.
- Phân quyền theo destination và thao tác SEND/SUBSCRIBE; việc kết nối thành công không có nghĩa người dùng được đọc mọi topic.
- Giới hạn payload, tốc độ gửi, số kết nối và thời gian không hoạt động.
- Xử lý reconnect, heartbeat, session đóng và việc gửi lại dữ liệu sau khi client kết nối lại.
- Không xem WebSocket như kho lưu trữ. Client mất kết nối có thể bỏ lỡ các cập nhật; nếu cần khôi phục, hãy lưu trạng thái/sự kiện ở nơi bền vững và cung cấp API đọc lại.

## 6. Ba module phối hợp với nhau ra sao?

Có thể hình dung mối quan hệ như sau:

~~~text
                         spring-messaging
                 Message / Channel / Handler
                    /                  \
                   /                    \
          spring-jms                 spring-websocket
       Jakarta JMS API              WebSocket + STOMP
              |                           |
       JMS ConnectionFactory          WebSocket session
              |                           |
       JMS provider/broker            Browser/client
~~~

spring-messaging là lớp abstraction dùng chung. spring-jms ánh xạ thao tác gửi/nhận qua JMS; spring-websocket dùng abstraction messaging khi chạy STOMP. Hai integration module có thể cùng xuất hiện trong một ứng dụng, nhưng không tự động nối mọi queue JMS với mọi topic WebSocket.

Ví dụ một ứng dụng nhận sự kiện từ JMS rồi phát thông báo đến các trình duyệt:

~~~java
@Component
public class OrderEventBroadcaster {

    private final SimpMessagingTemplate messagingTemplate;

    public OrderEventBroadcaster(SimpMessagingTemplate messagingTemplate) {
        this.messagingTemplate = messagingTemplate;
    }

    @JmsListener(destination = "orders.events")
    public void onOrderEvent(OrderEvent event) {
        messagingTemplate.convertAndSend("/topic/orders", event);
    }
}
~~~

Trong ví dụ này:

- JMS provider chuyển message đến listener của ứng dụng.
- Listener chuyển payload nghiệp vụ sang destination STOMP.
- WebSocket broker phân phối message đến các client đã đăng ký nhận destination đó.

Đây là một bridge do ứng dụng viết. Nó không tạo transaction nguyên tử giữa JMS acknowledgement và việc client nhận frame WebSocket. Nếu listener xử lý thành công nhưng client đang offline, client có thể không nhận được thông báo. Với dữ liệu quan trọng, hãy lưu trạng thái nghiệp vụ trước, phát thông báo như tín hiệu cập nhật và cho client đọc lại trạng thái qua API hoặc cơ chế replay.

## 7. Chọn module theo nhu cầu

| Nhu cầu | Lựa chọn phù hợp | Lý do |
|---|---|---|
| Chuẩn hóa payload, header, channel và handler trong code Spring | spring-messaging | Cung cấp mô hình message dùng chung |
| Gửi lệnh hoặc sự kiện bất đồng bộ qua queue/topic có JMS provider | spring-jms | Có template, listener container, converter và transaction support cho JMS |
| Cập nhật trình duyệt hai chiều, liên tục | spring-websocket | Duy trì WebSocket session; có thể dùng STOMP để định tuyến |
| Client cần publish-subscribe qua WebSocket | spring-websocket + spring-messaging | STOMP dùng messaging abstraction và broker routing |
| Tích hợp nhiều hệ thống, routing, transform, split, aggregate và adapter phong phú | Spring Integration | Đây là project mở rộng cho Enterprise Integration Patterns |
| Tích hợp Kafka hoặc AMQP/RabbitMQ | Spring for Apache Kafka hoặc Spring AMQP | Dùng integration module chuyên biệt cho broker/protocol đó |

Không phải ứng dụng nào cũng cần cả ba module. Chỉ thêm dependency cho capability thực sự sử dụng; dependency không thay thế cấu hình provider, broker, security hay chính sách vận hành.

## 8. Dependency và cấu hình ở mức dự án

Các tọa độ module của Spring Framework:

~~~groovy
dependencies {
    implementation("org.springframework:spring-messaging")
    implementation("org.springframework:spring-jms")
    implementation("org.springframework:spring-websocket")
}
~~~

Ví dụ trên giả định dự án có dependency management hoặc BOM quản lý phiên bản Spring Framework đồng bộ. Nếu không dùng BOM, phải khai báo phiên bản tương thích cho các module Spring. Không trộn tùy ý các phiên bản khác nhau.

Ngoài các dependency trên:

- spring-jms cần Jakarta JMS API và thư viện client của provider tương ứng; cần khai báo ConnectionFactory và cấu hình kết nối đến broker.
- spring-websocket trên Servlet stack cần web runtime phù hợp và cấu hình endpoint; STOMP external broker relay cần một broker hỗ trợ STOMP.
- spring-messaging có thể được dùng độc lập cho abstraction và xử lý message nội bộ; dùng abstraction không đồng nghĩa đã có transport phân tán.

Trong Spring Boot, các starter có thể gom dependency và auto-configure một phần hạ tầng. Cần phân biệt starter của Spring Boot với module thư viện gốc của Spring Framework.

## 9. Các nhầm lẫn thường gặp

**Nhầm abstraction với transport.** Message và MessageChannel mô tả cách ứng dụng biểu diễn/chuyển message. Chúng không tự mở kết nối đến JMS broker hoặc trình duyệt.

**Nhầm WebSocket với STOMP.** WebSocket là transport hai chiều; STOMP là protocol messaging có thể chạy trên WebSocket. Dùng raw WebSocket thì ứng dụng phải tự thống nhất cấu trúc và cách định tuyến payload.

**Nghĩ spring-jms chứa sẵn broker.** spring-jms là integration layer. Ứng dụng vẫn cần JMS provider, ConnectionFactory và destination hợp lệ.

**Cho rằng queue và topic của STOMP giống destination JMS.** Chúng thuộc hai hệ thống định tuyến khác nhau. Prefix /topic hoặc /queue trong STOMP không tự ánh xạ đến queue/topic của JMS.

**Cho rằng gửi message đồng nghĩa consumer đã xử lý thành công.** Việc gửi, broker nhận, listener xử lý, database commit và client hiển thị là các giai đoạn khác nhau. Cần correlation ID, log, metric và cơ chế xử lý lỗi để quan sát toàn bộ luồng.

**Bỏ qua duplicate và thứ tự.** Retry hoặc reconnect có thể tạo lần xử lý lặp; nhiều consumer có thể hoàn tất không theo thứ tự gửi. Thiết kế idempotency và version/sequence nếu nghiệp vụ cần.

**Dùng WebSocket cho dữ liệu cần lưu trữ.** WebSocket phù hợp để đẩy cập nhật đến client đang kết nối. Lịch sử, trạng thái cuối cùng và khả năng đọc lại cần một nguồn dữ liệu bền vững.

## 10. Checklist khi thiết kế một luồng messaging

1. Xác định ai gửi, ai nhận và message đại diện cho command hay event.
2. Định nghĩa payload, headers, schema version và correlation ID.
3. Chọn transport: JMS cho tích hợp qua JMS provider; WebSocket/STOMP cho client thời gian thực; abstraction nội bộ khi cần tách producer khỏi handler.
4. Xác định delivery semantics: acknowledgement, retry, timeout, duplicate, ordering và dead-letter handling.
5. Xác định transaction boundary giữa broker và database; không giả định chúng tự động atomic.
6. Thiết kế xác thực, phân quyền theo destination, kiểm soát payload và giới hạn tải.
7. Kiểm thử cả trường hợp bình thường, broker mất kết nối, listener lỗi, message không hợp lệ, client reconnect và message trùng.
8. Bổ sung log có correlation ID, metric về backlog/consumer/session và cảnh báo cho lỗi kéo dài.

## 11. Tài liệu tham khảo

- [Spring Framework Reference — Messaging](https://docs.spring.io/spring-framework/reference/integration.html)
- [Spring Framework Reference — JMS](https://docs.spring.io/spring-framework/reference/integration/jms.html)
- [Spring Framework Reference — WebSocket](https://docs.spring.io/spring-framework/reference/web/websocket.html)
- [Spring Framework Reference — STOMP](https://docs.spring.io/spring-framework/reference/web/websocket/stomp.html)
- [Spring Framework 6.1 Javadoc — org.springframework.messaging](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/messaging/package-summary.html)
- [Spring Framework 6.1 Javadoc — org.springframework.jms](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/jms/package-summary.html)

Khi đọc tài liệu, hãy chọn đúng phiên bản Spring Framework mà dự án đang sử dụng. Một số API và lựa chọn cấu hình có thể thay đổi giữa các nhánh phát hành.