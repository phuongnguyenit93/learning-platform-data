# Phân biệt JMS API với giao thức của từng broker

JMS và giao thức mạng của broker là hai lớp khác nhau. JMS (hiện thuộc Jakarta Messaging) là một API chuẩn cho ứng dụng Java gửi và nhận message. Nó định nghĩa các abstraction như ConnectionFactory, Connection, Session, Destination, MessageProducer, MessageConsumer, Queue, Topic và các kiểu message. JMS không quy định cách byte được mã hóa, đóng gói và truyền trên mạng.

Giao thức của broker là định dạng trao đổi ở tầng wire giữa client và server, ví dụ AMQP 1.0, AMQP 0-9-1, OpenWire, Artemis Core, MQTT, STOMP hoặc Kafka protocol. Một JMS provider cung cấp implementation của API JMS và chuyển các lời gọi Java thành thao tác theo giao thức mà provider sử dụng. Cùng một broker có thể hỗ trợ nhiều giao thức; mỗi loại client phải dùng thư viện và cấu hình tương ứng.

Spring JMS làm việc ở lớp API JMS thông qua một jakarta.jms.ConnectionFactory. Spring AMQP, Spring Kafka, MQTT/STOMP adapters và RSocket có abstraction và client protocol riêng. Đổi URL kết nối hoặc thay tên broker không tự động biến một client JMS thành client AMQP, Kafka hay MQTT.

## 1. Ba lớp cần phân biệt

Một hệ thống messaging thường có ba lớp:

1. **Programming API:** kiểu và phương thức mà code ứng dụng gọi. Ví dụ Jakarta Messaging API, Spring Messaging, Spring AMQP hoặc Kafka client API.
2. **Wire protocol:** định dạng frame, command, header, handshake và acknowledgment trao đổi giữa client và broker. Ví dụ AMQP 1.0, OpenWire, MQTT hoặc Kafka protocol.
3. **Transport:** đường truyền đưa frame qua mạng hoặc trong tiến trình. Ví dụ TCP, TLS trên TCP, WebSocket hoặc In-VM transport.

Các lớp này có thể kết hợp theo nhiều cách:

~~~text
Ứng dụng Java
    |
    v
Spring JmsTemplate
    |
    v
Jakarta Messaging API
    |
    v
JMS provider client (ConnectionFactory implementation)
    |
    v
Wire protocol do provider chọn
    |
    v
TCP/TLS hoặc transport tương ứng
    |
    v
Broker acceptor/protocol handler
~~~

Spring không tự chọn một wire protocol chung cho mọi JMS provider. Provider client quyết định cách chuyển API calls thành giao thức cụ thể; broker phải có acceptor hoặc protocol handler tương thích.

Ví dụ, một URI bắt đầu bằng tcp:// chỉ mô tả transport endpoint. Nó không đủ để kết luận client đang nói OpenWire, AMQP hay Artemis Core. Cần xem class ConnectionFactory, thư viện client, các tham số URI và cấu hình acceptor phía broker.

## 2. JMS/Jakarta Messaging chuẩn hóa điều gì?

Jakarta Messaging định nghĩa hợp đồng lập trình để các ứng dụng Java có thể dùng chung một mô hình gửi nhận message. Các thành phần cốt lõi gồm:

- **ConnectionFactory:** tạo kết nối tới messaging provider.
- **Connection:** kết nối logic của client tới provider.
- **Session:** ngữ cảnh tạo message, producer, consumer và quản lý acknowledgment/transaction theo chế độ được chọn.
- **Destination:** địa chỉ logic, thường là Queue hoặc Topic.
- **MessageProducer:** gửi message tới destination.
- **MessageConsumer:** nhận message từ destination.
- **MessageListener:** callback nhận message bất đồng bộ.
- **Message:** envelope có header, properties và body.

JMS có các kiểu message body phổ biến:

| Kiểu | Nội dung |
|---|---|
| TextMessage | Chuỗi văn bản, thường dùng JSON/XML hoặc text format |
| BytesMessage | Dữ liệu byte |
| MapMessage | Các trường key/value có kiểu dữ liệu JMS hỗ trợ |
| ObjectMessage | Đối tượng Java Serializable |
| StreamMessage | Chuỗi giá trị được đọc tuần tự |

Message properties là các trường metadata do ứng dụng đặt, có thể dùng trong selector nếu provider hỗ trợ semantics tương ứng. JMS headers chứa các trường chuẩn như JMSMessageID, JMSCorrelationID, JMSType, JMSReplyTo, JMSDestination, JMSPriority và JMSExpiration.

### 2.1. Những gì JMS không chuẩn hóa

Jakarta Messaging không định nghĩa wire protocol. Specification cũng không chuẩn hóa đầy đủ các phần như quản trị broker, cơ chế bảo mật/trao đổi khóa, load balancing và fault tolerance giữa nhiều client, hay các notification/advisory riêng của từng sản phẩm.

Vì vậy, hai broker cùng cung cấp JMS API vẫn có thể khác nhau về:

- Cách cấu hình địa chỉ và destination vật lý.
- Connection URI, discovery, failover và reconnect.
- Cách xác thực, phân quyền và mã hóa kết nối.
- Chính sách retry/redelivery và dead-letter.
- Cách tạo queue/topic động và quyền quản trị destination.
- Cách cấu hình durable/shared subscription.
- Hành vi của selector, message grouping, priority và expiration.
- Cách cấu hình transaction, XA và giới hạn của transaction.
- Extension properties, advisory message và công cụ quản trị.
- Giới hạn payload, frame, throughput và flow control.

JMS chuẩn hóa một phần API và semantics, không đảm bảo mọi tính năng nâng cao của broker có thể chuyển nguyên trạng sang sản phẩm khác.

## 3. Wire protocol là hợp đồng trao đổi giữa client và broker

Wire protocol mô tả những gì thực sự được gửi qua mạng. Nó quyết định cấu trúc frame, handshake, cách truyền message body, metadata, acknowledgment, flow control và một số thao tác giao thức.

| Giao thức | Đặc điểm | Ghi chú |
|---|---|---|
| AMQP 1.0 | Giao thức messaging chuẩn hóa ở wire level, hỗ trợ nhiều ngôn ngữ và nền tảng | Qpid JMS là một implementation Jakarta Messaging chạy trên AMQP 1.0 |
| AMQP 0-9-1 | Wire protocol được RabbitMQ sử dụng phổ biến | Spring AMQP/RabbitTemplate thường dùng RabbitMQ Java client với AMQP 0-9-1 |
| OpenWire | Giao thức nhị phân do ActiveMQ định nghĩa | ActiveMQ Classic JMS client thường dùng OpenWire; Artemis cũng có protocol adapter tương thích OpenWire |
| Artemis Core | Giao thức riêng của Apache ActiveMQ Artemis | Artemis JMS client dùng facade JMS ở phía client và giao tiếp qua Core protocol |
| MQTT | Giao thức publish/subscribe gọn nhẹ, phù hợp thiết bị và mạng hạn chế | Không phải JMS; dùng MQTT client/API riêng |
| STOMP | Giao thức text-oriented, đơn giản cho messaging interoperability | Không phải JMS; Spring có hỗ trợ STOMP qua WebSocket/message broker |
| Kafka protocol | Giao thức native của Apache Kafka | Spring Kafka dùng Kafka client; KafkaTemplate không phải JmsTemplate |

### 3.1. Không nhầm AMQP 1.0 với AMQP 0-9-1

Tên AMQP được dùng cho nhiều phiên bản giao thức khác nhau. AMQP 1.0 và AMQP 0-9-1 không phải hai tên gọi thay thế cho cùng một wire protocol. Một client được xây dựng cho AMQP 1.0 không mặc nhiên kết nối được với endpoint chỉ hỗ trợ AMQP 0-9-1.

Spring AMQP hiện tập trung vào RabbitMQ và client library tương ứng. Qpid JMS là một ví dụ khác: nó cung cấp API Jakarta Messaging nhưng truyền dữ liệu bằng AMQP 1.0. Vì vậy, cùng một ứng dụng có thể gọi JMS API nhưng protocol trên dây là AMQP 1.0.

### 3.2. Broker có thể hỗ trợ nhiều protocol

Một broker có thể mở nhiều listener/acceptor hoặc một endpoint nhận diện nhiều protocol. Ví dụ Apache ActiveMQ Artemis hỗ trợ các protocol module như Core, AMQP, MQTT, STOMP và OpenWire.

Điều đó không có nghĩa mọi client tự động dùng chung protocol. Một Artemis JMS client, Qpid JMS client và MQTT client có thể kết nối tới cùng một cụm broker nhưng sử dụng protocol khác nhau và nhìn thấy mô hình destination khác nhau.

Broker thường ánh xạ từng protocol vào mô hình địa chỉ nội bộ của nó. Ví dụ, JMS dùng Queue/Topic, MQTT dùng topic, STOMP dùng destination tổng quát, còn AMQP dùng node. Việc ánh xạ này do broker định nghĩa.

## 4. Một số ví dụ provider và protocol thực tế

### 4.1. Apache ActiveMQ Artemis

Artemis cung cấp Jakarta Messaging/JMS client API. JMS facade phía client chuyển các thao tác JMS thành các thao tác Core client và giao tiếp qua Artemis Core protocol.

Artemis cũng có thể nhận các client khác thông qua protocol adapter như AMQP 1.0, MQTT, STOMP và OpenWire. Ví dụ:

- Ứng dụng Java dùng Artemis JMS client: gọi jakarta.jms API, kết nối bằng Artemis client, dùng Core protocol.
- Ứng dụng dùng Qpid JMS: gọi Jakarta Messaging API, nhưng kết nối bằng AMQP 1.0.
- Thiết bị dùng MQTT client: gửi/nhận bằng MQTT, không gọi JMS API.

Các protocol có thể cùng truy cập broker, nhưng cách ánh xạ queue, topic, address, subscription và header cần được kiểm tra theo tài liệu Artemis.

### 4.2. Apache ActiveMQ Classic

ActiveMQ Classic hỗ trợ nhiều wire protocol, trong đó có OpenWire, AMQP, MQTT và STOMP. JMS client của ActiveMQ Classic thường sử dụng OpenWire theo cấu hình mặc định. Broker có thể mở connector hoặc protocol detection cho các client dùng protocol khác.

Một ứng dụng dùng ActiveMQConnectionFactory và JMS API không thể chỉ thay URI sang một broker khác rồi kỳ vọng protocol và các extension OpenWire vẫn hoạt động. Cần thay provider client nếu broker mới yêu cầu protocol khác.

### 4.3. Apache Qpid JMS

Qpid JMS là một client triển khai Jakarta Messaging trên AMQP 1.0. Ứng dụng vẫn có thể gọi ConnectionFactory, Session, MessageProducer, MessageConsumer hoặc dùng Spring JmsTemplate; Qpid JMS chịu trách nhiệm mã hóa và truyền các thao tác bằng AMQP 1.0.

Đây là ví dụ rõ ràng cho việc API và wire protocol độc lập: code ứng dụng nhìn thấy JMS, còn broker nhìn thấy AMQP 1.0.

### 4.4. RabbitMQ và Spring AMQP

RabbitMQ có client Java native sử dụng AMQP 0-9-1. Spring AMQP cung cấp RabbitTemplate, AmqpTemplate, @RabbitListener và các listener container trên client library đó.

Spring AMQP không phải Spring JMS. Dù cả hai đều có template và listener, API, connection factory, message abstraction, exchange/queue/binding và protocol là khác nhau.

Nếu muốn sử dụng Jakarta Messaging với một broker cụ thể, phải chọn một JMS provider/client tương thích với broker và protocol mà broker hỗ trợ. Không nên suy ra broker có JMS chỉ vì broker có AMQP.

### 4.5. Apache Kafka

Kafka có protocol native riêng và mô hình topic-partition, offset, consumer group. Spring Kafka cung cấp KafkaTemplate và @KafkaListener dựa trên Kafka client.

Kafka không trở thành JMS chỉ vì ứng dụng dùng Spring Messaging Message<?> hoặc Spring Integration để nối channel. Những abstraction này nằm ở phía ứng dụng; wire protocol vẫn là Kafka protocol.

## 5. Spring JMS nằm ở lớp API JMS

Spring Framework cung cấp hỗ trợ JMS qua module spring-jms. Các thành phần chính:

- **JmsTemplate:** gửi, nhận và chuyển đổi JMS message; quản lý việc tạo và giải phóng resource.
- **@JmsListener:** khai báo endpoint nhận message.
- **DefaultMessageListenerContainer:** quản lý consumer, session, transaction, thread và vòng đời listener.
- **SimpleMessageListenerContainer:** listener container đơn giản hơn, dựa nhiều vào callback của provider.
- **MessageConverter:** chuyển đổi payload của ứng dụng thành JMS Message và ngược lại.
- **DestinationResolver:** phân giải tên destination thành đối tượng JMS Destination.
- **JmsTransactionManager:** quản lý local transaction cho một JMS ConnectionFactory.

Các thành phần này sử dụng jakarta.jms.ConnectionFactory. ConnectionFactory thực tế phải đến từ provider client tương ứng với broker.

### 5.1. Ví dụ gửi message bằng JmsTemplate

~~~java
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Service;

@Service
class OrderPublisher {

    private final JmsTemplate jmsTemplate;

    OrderPublisher(JmsTemplate jmsTemplate) {
        this.jmsTemplate = jmsTemplate;
    }

    void publish(OrderCreated event) {
        this.jmsTemplate.convertAndSend("orders", event);
    }
}

record OrderCreated(String orderId, String customerId) {
}
~~~

Đây là fragment của ứng dụng Spring dùng Java 17+. JmsTemplate lấy ConnectionFactory đã cấu hình, dùng MessageConverter để chuyển object thành JMS message, sau đó gọi provider client. Provider client mới là thành phần chọn wire protocol và truyền message tới broker.

### 5.2. Ví dụ nhận message bằng @JmsListener

~~~java
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
class OrderConsumer {

    @JmsListener(destination = "orders")
    public void handle(OrderCreated event) {
        System.out.println("Received order: " + event.orderId());
    }
}
~~~

Listener container quản lý việc đăng ký consumer với provider, nhận JMS message và gọi phương thức listener. Ứng dụng không cần tự mở connection/session cho từng message.

Trong Spring Boot, JMS infrastructure có thể được auto-configure nếu có provider dependency và ConnectionFactory phù hợp. Ứng dụng Spring không dùng Boot thường cần bật @EnableJms và khai báo listener container factory.

### 5.3. Cấu hình listener container

~~~java
import jakarta.jms.ConnectionFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;
import org.springframework.jms.annotation.EnableJms;

@Configuration
@EnableJms
class JmsConfiguration {

    @Bean
    DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
            ConnectionFactory connectionFactory) {

        var factory = new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setSessionTransacted(true);
        factory.setConcurrency("2-8");
        return factory;
    }
}
~~~

Đây là cấu hình Spring JMS; ConnectionFactory được inject là implementation do provider cung cấp. setSessionTransacted(true) yêu cầu listener session dùng local JMS transaction. Nếu listener ném exception, transaction có thể rollback và message có thể được redeliver tùy provider và cấu hình broker.

Local JMS transaction không tự động bao gồm transaction database hoặc HTTP service. Muốn phối hợp nhiều resource cần thiết kế transaction phù hợp, XA nếu thực sự cần, hoặc outbox/inbox và idempotency.

## 6. Spring JMS, Spring AMQP và Spring Kafka không thay thế trực tiếp cho nhau

Các API có hình dạng tương tự nhưng semantics khác nhau:

| Nhu cầu | Spring API | Client/provider | Wire protocol |
|---|---|---|---|
| Gửi/nhận theo JMS Queue/Topic | JmsTemplate, @JmsListener | Jakarta Messaging provider | Provider-specific |
| RabbitMQ exchange/queue/routing key | RabbitTemplate, @RabbitListener | RabbitMQ Java client | AMQP 0-9-1 |
| Kafka topic/partition/offset | KafkaTemplate, @KafkaListener | Apache Kafka client | Kafka protocol |
| RSocket request-response/stream | RSocketRequester, @MessageMapping | RSocket implementation | RSocket protocol |
| MQTT publish/subscribe | MQTT client hoặc Spring Integration MQTT adapter | MQTT client provider | MQTT |
| STOMP qua WebSocket | Spring Messaging/STOMP | STOMP client/broker relay | STOMP trên WebSocket hoặc TCP |

Spring Messaging Message<?> là abstraction message trong ứng dụng. Nó không quyết định protocol mạng. Spring Integration có thể nối một JMS inbound adapter vào MessageChannel hoặc một AMQP adapter vào channel; khi đó adapter là ranh giới giữa abstraction nội bộ và protocol/client bên ngoài.

Ví dụ:
- Jms.message-driven-channel-adapter nhận message qua JMS provider rồi chuyển thành Spring Integration Message.
- Spring AMQP inbound adapter nhận message từ RabbitMQ qua AMQP client.
- Kafka message-driven adapter nhận record từ Kafka client.
- STOMP/WebSocket handler nhận frame STOMP và ánh xạ thành Spring Messaging message.

Không nên chọn một adapter chỉ vì payload có cùng JSON schema. Cần xem semantics của acknowledgment, transaction, ordering, routing, retention và retry.

## 7. Message conversion không phải wire protocol conversion

MessageConverter của Spring JMS chuyển đổi giữa object ứng dụng và các kiểu JMS Message. Ví dụ:
- OrderCreated object thành TextMessage chứa JSON.
- byte[] thành BytesMessage.
- String thành TextMessage.

Sau đó JMS provider mới mã hóa JMS message thành frame/command của protocol cụ thể.

Tương tự, Spring AMQP MessageConverter chuyển đổi payload/header của Spring AMQP Message sang dạng mà RabbitMQ client gửi được. Kafka Serializer/Deserializer chuyển đổi key/value thành byte array cho Kafka protocol. Các bước này là conversion/serialization của payload; chúng không biến một wire protocol thành wire protocol khác.

Ví dụ cùng một payload JSON có thể được gửi qua JMS, AMQP hoặc Kafka. JSON chỉ là định dạng body; nó không cho biết message được truyền bằng giao thức nào, được ACK thế nào hoặc được định tuyến ra sao.

### 7.1. Cẩn trọng với ObjectMessage

ObjectMessage có thể dựa trên Java serialization và phụ thuộc class compatibility giữa producer và consumer. Điều này làm tăng coupling và có rủi ro bảo mật khi deserialize dữ liệu không tin cậy. Với hệ thống liên ngôn ngữ hoặc cần schema evolution, thường nên dùng TextMessage/BytesMessage với JSON, Avro hoặc Protobuf và schema/version rõ ràng.

## 8. Những khác biệt broker-specific cần kiểm tra

Khi dùng cùng JMS API với hai broker khác nhau, hãy xác minh các điểm sau:

| Chủ đề | Điều cần xác minh |
|---|---|
| Destination | Queue/topic có được tạo tự động không? Tên JMS ánh xạ sang physical destination nào? |
| Durable subscription | Cách đặt client ID, subscription name và shared subscription có tương thích không? |
| Acknowledgment | AUTO_ACKNOWLEDGE, CLIENT_ACKNOWLEDGE và transacted session có semantics nào khác biệt? |
| Redelivery | Số lần redelivery, delay, backoff, poison message và DLQ được cấu hình ở đâu? |
| Ordering | Broker có message grouping, exclusive consumer hay thứ tự theo queue không? Concurrency có làm đổi thứ tự không? |
| Priority/TTL | Broker hỗ trợ priority, expiration và xử lý message hết hạn như thế nào? |
| Selectors | Selector expression nào được hỗ trợ và hiệu năng lọc ra sao? |
| Transactions | Local transaction, XA, producer/consumer transaction và rollback được hỗ trợ tới đâu? |
| Security | TLS, SASL, username/password, certificate, ACL và authorization được cấu hình theo cơ chế nào? |
| Failover | Client reconnect, topology discovery, failover URL và retry có phải extension của provider không? |
| Message size | Giới hạn payload/frame, large-message handling và paging có khác nhau không? |
| Management | Tạo destination, browse queue, purge, metrics và advisory dùng công cụ/API nào? |

Đặc biệt, không mặc định rằng một tính năng broker-specific có thể chuyển sang broker khác chỉ vì cả hai cung cấp JMS API. Nếu ứng dụng phụ thuộc vào vendor extension, hãy cô lập extension đó trong adapter/configuration riêng và ghi rõ trong kiến trúc.

## 9. Namespace javax.jms và jakarta.jms

Đây là điểm tương thích quan trọng khi nâng cấp Spring:

- Spring Framework 5.x sử dụng Java EE JMS namespace javax.jms.
- Spring Framework 6.x và 7.x sử dụng Jakarta Messaging namespace jakarta.jms.
- JMS provider client phải implement đúng namespace mà ứng dụng đang dùng.

javax.jms.ConnectionFactory và jakarta.jms.ConnectionFactory là hai kiểu Java khác package, không thể thay thế trực tiếp cho nhau. Chỉ thay import mà giữ dependency provider cũ thường không đủ.

Khi nâng cấp từ Spring 5 lên Spring 6/7, cần:
1. Chọn provider client có Jakarta Messaging API tương thích.
2. Kiểm tra dependency tree để tránh đồng thời hai API namespace.
3. Cập nhật import và configuration classes.
4. Kiểm tra message converter, listener container và transaction manager.
5. Chạy integration test với đúng broker/version đang triển khai.

Không nhầm việc chuyển javax sang jakarta với việc đổi wire protocol. Đây là thay đổi namespace API ở phía Java; protocol mạng có thể vẫn giữ nguyên nếu provider client hỗ trợ cả hai namespace.

## 10. Chọn API và protocol theo yêu cầu hệ thống

### 10.1. Khi chọn JMS

JMS phù hợp khi:
- Ứng dụng Java cần abstraction chuẩn queue/topic và producer/consumer.
- Cần tích hợp với broker có JMS provider/client phù hợp.
- Muốn dùng JmsTemplate, @JmsListener và Spring transaction support.
- Có nhu cầu tương thích với hệ thống Java EE/Jakarta EE hoặc hệ thống messaging doanh nghiệp hiện có.

Cần chấp nhận rằng failover, security, administration và nhiều tính năng vận hành vẫn phụ thuộc provider.

### 10.2. Khi chọn AMQP

AMQP phù hợp khi cần wire protocol interoperability giữa các ngôn ngữ hoặc nền tảng, nhưng phải chọn rõ phiên bản AMQP và client tương ứng.

- AMQP 1.0: wire protocol chuẩn hóa; Qpid JMS cho phép dùng Jakarta Messaging API trên AMQP 1.0.
- AMQP 0-9-1: thường dùng với RabbitMQ và Spring AMQP/RabbitTemplate.
- Không giả định AMQP 1.0 client có thể kết nối AMQP 0-9-1 endpoint.

### 10.3. Khi chọn Kafka

Kafka phù hợp với event streaming, partitioned log, replay theo offset, consumer group và throughput lớn. Spring Kafka cung cấp KafkaTemplate và @KafkaListener. Đây là API/protocol riêng, không phải JMS queue/topic.

### 10.4. Khi chọn MQTT hoặc STOMP

MQTT phù hợp với thiết bị và môi trường constrained; STOMP phù hợp cho giao tiếp message đơn giản, đặc biệt qua WebSocket trong ứng dụng web. Cả hai có protocol/client riêng và không được chuẩn hóa bởi JMS.

## 11. Quy trình thay broker hoặc đổi protocol

Khi chuyển từ broker A sang broker B, không bắt đầu bằng việc sửa connection URL. Hãy kiểm tra theo thứ tự:

1. **Xác định API đang dùng:** code gọi JmsTemplate, RabbitTemplate, KafkaTemplate hay một client native?
2. **Xác định provider/client:** class thực tế của ConnectionFactory hoặc client factory là gì? Artifact Maven nào cung cấp nó?
3. **Xác định wire protocol:** provider client dùng OpenWire, Artemis Core, AMQP 1.0 hay giao thức khác?
4. **Kiểm tra broker endpoint:** broker đã bật acceptor/protocol phù hợp chưa? TLS/auth có tương thích không?
5. **So sánh semantics:** queue/topic, subscription, selector, acknowledgment, redelivery, transaction, ordering và TTL có mapping tương đương không?
6. **So sánh message conversion:** body, header, property, correlation ID, timestamp và schema có được bảo toàn không?
7. **Kiểm tra provider extension:** failover, discovery, message grouping, advisory và management API có được dùng trong code không?
8. **Kiểm thử tích hợp:** send/receive, rollback, duplicate, reconnect, DLQ, ordering và restart broker.
9. **Triển khai có kiểm soát:** đo throughput/latency, quan sát backlog và giữ khả năng rollback.

Nếu chỉ thay JMS provider nhưng giữ JMS API, phần lớn code application có thể giữ nguyên; configuration và behavior vẫn cần xác minh. Nếu đổi từ JMS sang Spring AMQP hoặc Kafka, đó là migration API và semantics, không chỉ là thay client dependency.

## 12. Lỗi thường gặp

### 12.1. JMS client không kết nối được broker dù host/port đúng

Có thể transport TCP thông suốt nhưng wire protocol không tương thích. Kiểm tra provider client, URI scheme/parameters, broker acceptor và protocol được bật ở endpoint.

### 12.2. ClassCastException hoặc NoClassDefFoundError với ConnectionFactory

Kiểm tra javax.jms và jakarta.jms có bị trộn không. Đảm bảo Spring Framework và provider client cùng dùng một namespace/API version.

### 12.3. Chuyển broker nhưng selector hoặc durable subscription hoạt động khác

Đây có thể là khác biệt provider-specific hoặc cách ánh xạ destination. So sánh cấu hình queue/topic, subscription name, client ID và selector implementation.

### 12.4. Message bị redeliver nhiều lần sau exception

Kiểm tra sessionTransacted, acknowledgment mode, listener container, provider redelivery policy và DLQ. JMS API không tự định nghĩa toàn bộ chính sách redelivery của từng broker.

### 12.5. AMQP client không kết nối được broker RabbitMQ

Kiểm tra chính xác AMQP 0-9-1 hay AMQP 1.0 đang được sử dụng. Qpid JMS dùng AMQP 1.0; RabbitMQ client phổ biến của Spring AMQP dùng AMQP 0-9-1. Cần broker/plugin và client tương thích cùng phiên bản protocol.

### 12.6. Nghĩ rằng Spring MessageConverter thay đổi protocol

MessageConverter chỉ đổi payload/message representation ở lớp ứng dụng. Wire protocol do provider/client và broker endpoint quyết định.

## 13. Kiểm thử để chứng minh đúng API và protocol

Một unit test với mock ConnectionFactory chỉ kiểm tra code gọi API JMS đúng. Nó không chứng minh broker chấp nhận protocol hoặc semantics giống production.

Nên có các integration test với đúng provider/broker:
- Tạo connection và session bằng đúng Jakarta JMS client.
- Gửi và nhận message qua JmsTemplate và @JmsListener.
- Kiểm tra message body, properties, correlation ID và reply-to.
- Kiểm tra transacted session và rollback/redelivery.
- Kiểm tra queue/topic và durable subscription.
- Kiểm tra selector, TTL, priority và DLQ nếu ứng dụng sử dụng.
- Kiểm tra broker restart, client reconnect và failover.
- Kiểm tra TLS/auth và ACL.
- Kiểm tra tương thích khi nâng cấp broker hoặc provider client.
- Kiểm tra interoperability nếu producer/consumer dùng hai protocol client khác nhau.

Dùng Testcontainers hoặc broker test instance tương ứng khi cần xác nhận wire protocol thực. Một test chỉ chạy Embedded broker hoặc mock không thể chứng minh protocol adapter production đang được cấu hình đúng.

## 14. Checklist trước khi triển khai

- [ ] Đã phân biệt programming API, wire protocol và transport.
- [ ] Biết chính xác class và artifact của JMS provider client.
- [ ] Đã xác định broker acceptor và wire protocol mà client thực sự sử dụng.
- [ ] Không nhầm AMQP 1.0 với AMQP 0-9-1.
- [ ] Không nhầm Spring JMS với Spring AMQP hoặc Spring Kafka.
- [ ] Jakarta/Javax JMS namespace tương thích với phiên bản Spring và provider.
- [ ] Destination, acknowledgment, transaction, redelivery và DLQ đã được kiểm tra trên broker thật.
- [ ] MessageConverter/schema không phụ thuộc serialization không an toàn.
- [ ] TLS, authentication, authorization và failover đã được kiểm tra.
- [ ] Có integration test cho provider/broker/protocol thực tế.
- [ ] Đã ghi rõ các provider extension mà ứng dụng đang phụ thuộc.

## Tài liệu tham khảo

- Jakarta Messaging Specification — API scope and explicit statement that the specification does not define a wire protocol: https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html
- Spring Framework Reference — Using Spring JMS, JmsTemplate and listener containers: https://docs.spring.io/spring-framework/reference/integration/jms/using.html
- Spring Framework Reference — Receiving JMS messages and listener containers: https://docs.spring.io/spring-framework/reference/integration/jms/receiving.html
- Spring AMQP Reference — distinction between JMS interface API and AMQP wire protocol: https://docs.spring.io/spring-amqp/reference/amqp/template.html
- Spring AMQP Reference — Spring AMQP abstractions and RabbitTemplate: https://docs.spring.io/spring-amqp/reference/amqp.html
- Apache ActiveMQ Artemis — Protocols and Interoperability: https://artemis.apache.org/components/artemis/documentation/latest/protocols-interoperability.html
- Apache ActiveMQ Artemis — Core architecture and JMS facade: https://artemis.apache.org/components/artemis/documentation/latest/architecture.html
- Apache Qpid JMS — Jakarta Messaging client over AMQP 1.0: https://qpid.apache.org/components/jms/index.html
- Apache ActiveMQ Classic — Supported wire protocols: https://activemq.apache.org/components/classic/documentation/protocols
