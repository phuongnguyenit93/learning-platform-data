# RabbitTemplate và connection factory

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt **RabbitTemplate**, **Spring AMQP ConnectionFactory**, **CachingConnectionFactory**, AMQP channel và RabbitMQ broker.
- Sử dụng đúng các thao tác **send**, **convertAndSend**, **receive**, **receiveAndConvert** và **convertSendAndReceive**.
- Giải thích cách AMQP channel adapter/gateway trong Spring Integration sử dụng RabbitTemplate và ConnectionFactory.
- Cấu hình connection, exchange, queue, binding, MessageConverter, publisher confirms và publisher returns.
- Viết Spring Integration Java DSL publish message từ MessageChannel sang RabbitMQ.
- Phân tích timeout, retry, delivery/ACK, idempotency, outbox và vòng đời kết nối trong ứng dụng thực tế.

## 1. Tại sao cần RabbitTemplate và ConnectionFactory?

Giả sử OrderService đã lưu một đơn hàng và muốn phát sự kiện **OrderCreated** tới dịch vụ kho. Mã nghiệp vụ không nên trực tiếp mở TCP socket, cấp AMQP channel, serialize dữ liệu, gửi publish và đóng tài nguyên mỗi lần có đơn hàng. Spring AMQP cung cấp những abstraction để tách phần kết nối này khỏi nghiệp vụ:

- **RabbitTemplate** là client cấp ứng dụng dùng để gửi, lấy một message hoặc thực hiện request–reply qua RabbitMQ.
- **ConnectionFactory** cấp kết nối AMQP cho RabbitTemplate, listener container và các endpoint khác.
- **CachingConnectionFactory** tái sử dụng connection/channel, giảm chi phí tạo tài nguyên liên tục.
- **Spring Integration AMQP adapter/gateway** kết nối những thao tác RabbitMQ với luồng **MessageChannel** và **Spring Message**.

~~~mermaid
flowchart LR
    S["OrderService"] --> MC["Spring MessageChannel"]
    MC --> A["AMQP outbound adapter"]
    A --> T["RabbitTemplate"]
    T --> CF["Spring AMQP<br/>ConnectionFactory"]
    CF --> B["RabbitMQ exchange"]
    B --> Q["Queue"]
    Q --> L["Listener container"]
    L --> IA["AMQP inbound adapter"]
    IA --> R["MessageChannel bên nhận"]
~~~

**RabbitTemplate không phải MessageChannel**, ConnectionFactory không phải queue, và RabbitMQ exchange không phải service activator. Mỗi thành phần có phạm vi trách nhiệm và ý nghĩa thành công khác nhau. Tổ chức đúng các lớp này giúp hệ thống Spring Integration có thể tích hợp AMQP với file, SFTP, HTTP, JMS, Kafka hoặc database mà không trộn connection management vào logic nghiệp vụ.

## 2. Mô hình các thành phần Spring AMQP

| Thành phần | Vai trò | Không phải |
| --- | --- | --- |
| **RabbitTemplate** | API gửi/nhận/RPC qua RabbitMQ | Broker, MessageChannel, listener container |
| **Spring AMQP ConnectionFactory** | Cấp và quản lý connection/channel | JDBC ConnectionFactory hoặc JMS factory |
| **CachingConnectionFactory** | Cache connection/channel theo cấu hình | Queue lưu message |
| **MessageConverter** | Ánh xạ Java object ↔ AMQP body/properties | Transformer nghiệp vụ |
| **RabbitAdmin / AmqpAdmin** | Khai báo exchange, queue, binding | Publisher xác nhận consumer đã xử lý |
| **Listener container** | Nhận delivery, ACK/NACK, concurrency, reconnect | RabbitTemplate gửi message |
| **AMQP outbound channel adapter** | MessageChannel → RabbitTemplate → broker | Gateway hai chiều |
| **AMQP inbound channel adapter** | Broker delivery → MessageChannel | AMQP outbound adapter |
| **AMQP gateway** | Request–reply giữa RabbitMQ và messaging flow | Publisher confirm |

### 2.1. Hai ConnectionFactory cùng tên nhưng khác API

Phải phân biệt:

- **org.springframework.amqp.rabbit.connection.ConnectionFactory**: interface Spring AMQP được RabbitTemplate, inbound gateway và listener container sử dụng.
- **com.rabbitmq.client.ConnectionFactory**: lớp của RabbitMQ Java client mức thấp, có kiểu connection và API khác.

Spring Boot thường cấu hình **CachingConnectionFactory** triển khai interface Spring AMQP. Không đưa thẳng factory của RabbitMQ Java client vào nơi yêu cầu Spring AMQP ConnectionFactory mà thiếu bước tích hợp tương ứng.

### 2.2. Đường đi của một lần publish

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant T as RabbitTemplate
    participant F as ConnectionFactory
    participant B as RabbitMQ
    participant C as Consumer
    P->>T: convertAndSend(exchange, key, payload)
    T->>T: MessageConverter tạo body/properties
    T->>F: Lấy AMQP channel
    F-->>T: Channel sẵn có hoặc mới
    T->>B: basic.publish
    B-->>T: Publisher confirm/return nếu cấu hình
    B-->>C: Delivery từ queue nếu route được
    C-->>B: Consumer ACK/NACK theo listener
~~~

Các mốc **send vào MessageChannel**, **gửi publish**, **publisher confirm**, **message route tới queue** và **consumer ACK** khác nhau. Không được xem một lần gửi thành công ở tầng client là bằng chứng nghiệp vụ của consumer đã hoàn tất.

## 3. RabbitTemplate API và khi nào nên dùng

| API | Đầu vào/đầu ra chính | Mục đích |
| --- | --- | --- |
| **send(...)** | AMQP Message → publish | Caller đã tự chuẩn bị body và MessageProperties |
| **convertAndSend(...)** | Java object → publish | Dùng MessageConverter tạo AMQP Message |
| **receive(...)** | Lấy một AMQP Message từ queue | Thao tác pull/kiểm tra đặc biệt |
| **receiveAndConvert(...)** | Lấy message và convert payload | Pull theo hợp đồng converter |
| **sendAndReceive(...)** | AMQP Message → AMQP reply | Request–reply ở cấp AMQP Message |
| **convertSendAndReceive(...)** | Java object → Java reply | RPC với chuyển đổi request/reply |
| **execute(...)** | Callback sử dụng RabbitMQ channel | Tác vụ cấp thấp cần API client đặc biệt |

### 3.1. send so với convertAndSend

~~~java
import java.nio.charset.StandardCharsets;

import org.springframework.amqp.core.Message;
import org.springframework.amqp.core.MessageProperties;
import org.springframework.amqp.rabbit.core.RabbitTemplate;

public class PublishVariants {
    private final RabbitTemplate rabbitTemplate;

    public PublishVariants(RabbitTemplate rabbitTemplate) {
        this.rabbitTemplate = rabbitTemplate;
    }

    public void sendAsBytes() {
        MessageProperties props = new MessageProperties();
        props.setContentType(MessageProperties.CONTENT_TYPE_TEXT_PLAIN);
        props.setContentEncoding(StandardCharsets.UTF_8.name());
        Message message = new Message(
            "evt-1001|O-1001".getBytes(StandardCharsets.UTF_8), props);
        rabbitTemplate.send("orders.events", "orders.created", message);
    }

    public void sendAsString() {
        rabbitTemplate.convertAndSend(
            "orders.events", "orders.created", "evt-1001|O-1001");
    }
}
~~~

**sendAsBytes** tự tạo AMQP Message và metadata. **sendAsString** để MessageConverter của RabbitTemplate tạo body/properties. Cả hai đều là publish **một chiều**, không trả business reply của consumer.

### 3.2. receive và receiveAndConvert

RabbitTemplate cũng có thể chủ động lấy một message từ queue. Việc trả null có thể đơn giản là **chưa có message** hoặc đã hết thời gian chờ theo cấu hình. Không dùng vòng lặp receive không giới hạn để thay thế listener container trong một luồng tiêu thụ liên tục nếu không có lý do rõ ràng.

Trong Spring Integration, **AMQP inbound channel adapter dạng message-driven** thường dùng Spring AMQP listener container để nhận delivery và đưa vào MessageChannel; nó không cần một Spring Integration Poller giống File/SFTP inbound adapter. Listener container quản lý consumer, prefetch, ACK/requeue và vòng đời.

### 3.3. convertSendAndReceive dành cho RPC

~~~java
Object reply = rabbitTemplate.convertSendAndReceive(
    "quotes.requests", "quote.calculate", "req-1001|SKU-42|2");

if (!(reply instanceof String result)) {
    throw new IllegalStateException("Khong co reply hop le / timeout");
}
~~~

Đây là tương tác **request–reply**. RabbitTemplate có thể thiết lập reply-to và cơ chế correlation phù hợp theo cấu hình/broker. Một outbound Integration gateway cung cấp hợp đồng tương tự cho luồng Spring Integration. **Timeout ở caller không chứng minh server chưa xử lý**; nếu request tạo side effect, phải có idempotency key nghiệp vụ.

## 4. ConnectionFactory và CachingConnectionFactory

RabbitMQ sử dụng **TCP/TLS connection** và nhiều **AMQP channel**. Connection thường đắt hơn channel, nhưng mỗi channel vẫn có tài nguyên và giới hạn. Spring AMQP ConnectionFactory cung cấp abstraction để RabbitTemplate hoặc listener container lấy những tài nguyên đó.

~~~mermaid
flowchart TB
    RT["RabbitTemplate"] --> CF["CachingConnectionFactory"]
    L["Listener container"] --> CF
    CF --> TCP["Connection TCP/TLS"]
    TCP --> A["AMQP channel A"]
    TCP --> B["AMQP channel B"]
    TCP --> C["AMQP channel C"]
    A --> MQ["RabbitMQ"]
    B --> MQ
    C --> MQ
~~~

**CachingConnectionFactory** giảm việc mở/đóng connection/channel liên tục. Tuy nhiên **channel cache size không phải số message có thể buffer**, và không nên tự hiểu là giới hạn cứng số channel có thể mở nếu các thiết lập checkout timeout/cache mode khác chưa được xem xét.

| Cấu hình | Mục đích |
| --- | --- |
| **host/port/addresses** | Địa chỉ broker và khả năng kết nối |
| **virtual-host** | Namespace RabbitMQ mà ứng dụng truy cập |
| **username/password** | Xác thực; nên nạp từ secret manager |
| **connection-timeout** | Giới hạn thời gian kết nối |
| **requested-heartbeat** | Phát hiện connection không còn khả dụng theo thương lượng broker/client |
| **cache.channel.size** | Số channel được giữ lại trong cache theo chế độ |
| **publisher-confirm-type** | Cơ chế nhận xác nhận publish |
| **publisher-returns** | Cơ chế quan sát thông điệp không route được |
| **template.mandatory** | Yêu cầu broker return message không route được khi thích hợp |

### 4.1. Vòng đời và chia sẻ connection

Trong một Spring Boot application thông thường, hãy để **Spring quản lý ConnectionFactory/RabbitTemplate như bean dùng chung**. Không tạo factory/connection mới trong mỗi lời gọi nghiệp vụ, không đóng factory dùng chung khi một publish bị lỗi, và không giữ AMQP channel thủ công ngoài vòng đời do client/container quản lý.

**isRunning() của endpoint không phải phép health check RabbitMQ.** Broker có thể mất kết nối sau khi listener bắt đầu, hoặc publisher có thể lỗi do quyền exchange, mất route, TLS/certificate. Cần log và metrics riêng cho connection, publish, confirms, returns và consumer backlog.

### 4.2. Khi nào cần nhiều ConnectionFactory?

Nếu các luồng dùng nhiều broker/virtual host khác nhau hoặc chính sách xác thực riêng, có thể cần nhiều factory/template, được phân biệt bằng qualifier/routing configuration. Nhưng không tạo nhiều factory chỉ vì hai flow publish **routing key khác nhau** trên cùng broker; RabbitTemplate và outbound endpoint có thể cấu hình exchange/routing key theo từng thao tác.

## 5. Cấu hình Spring Boot và dependency

Với Spring Boot, có thể sử dụng:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-amqp</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-integration</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.integration</groupId>
        <artifactId>spring-integration-amqp</artifactId>
    </dependency>
</dependencies>
~~~

Spring Boot thường tự cấu hình **CachingConnectionFactory** và **RabbitTemplate** khi các điều kiện autoconfiguration phù hợp.

~~~yaml
spring:
  rabbitmq:
    host: localhost
    port: 5672
    virtual-host: /
    username: ${RABBITMQ_USERNAME}
    password: ${RABBITMQ_PASSWORD}
    connection-timeout: 5s
    requested-heartbeat: 30s
    cache:
      channel:
        size: 25
    publisher-confirm-type: correlated
    publisher-returns: true
    template:
      mandatory: true
      reply-timeout: 5s
~~~

**Các con số là giá trị ví dụ**, không phải ngưỡng khuyến nghị cho production. Kiểm tra phiên bản Boot/Spring AMQP đang dùng trước khi đưa cấu hình vào hệ thống thực. Không hardcode credentials thật hoặc cung cấp quyền khai báo topology không cần thiết cho ứng dụng producer.

### 5.1. RabbitTemplate tự cấu hình và tùy chỉnh

Khi tạo **RabbitTemplate bean tùy chỉnh**, cần xem ảnh hưởng tới auto-configuration của Boot, MessageConverter và các callback confirms/returns. Nếu nhiều endpoint dùng chung template, một cấu hình callback không nên ghi đè cơ chế theo dõi publisher của endpoint khác. Có thể tách template có trách nhiệm rõ ràng hoặc quản lý callback tập trung.

**RabbitAdmin/AmqpAdmin** chịu trách nhiệm khai báo topology nếu ứng dụng được cho phép. Một bean Queue hay DirectExchange không tự bảo đảm broker đã có tài nguyên đó; hệ thống có thể được provision từ bên ngoài bằng IaC hoặc công cụ vận hành.

## 6. Ví dụ Java: RabbitTemplate và RabbitMQ topology

Ví dụ sử dụng **direct exchange orders.events**, routing key **orders.created**, queue **orders.created.q** và nội dung String đơn giản **eventId|orderId|totalVnd**.

### 6.1. Exchange, queue, binding

~~~java
import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrdersRabbitTopology {
    public static final String EXCHANGE = "orders.events";
    public static final String KEY = "orders.created";
    public static final String QUEUE = "orders.created.q";

    @Bean
    public DirectExchange ordersExchange() {
        return new DirectExchange(EXCHANGE, true, false);
    }

    @Bean
    public Queue ordersQueue() {
        return new Queue(QUEUE, true);
    }

    @Bean
    public Binding ordersBinding(
            Queue ordersQueue, DirectExchange ordersExchange) {
        return BindingBuilder.bind(ordersQueue)
            .to(ordersExchange)
            .with(KEY);
    }
}
~~~

Exchange và queue durable chỉ góp phần xác định **độ bền topology**. Message persistence, publisher confirms, routing chính xác, consumer ACK và nghiệp vụ vẫn phải được xem xét riêng.

### 6.2. Producer dùng RabbitTemplate trực tiếp

~~~java
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.stereotype.Service;

@Service
public class RabbitOrderPublisher {

    private final RabbitTemplate rabbitTemplate;

    public RabbitOrderPublisher(RabbitTemplate rabbitTemplate) {
        this.rabbitTemplate = rabbitTemplate;
    }

    public void publish(String eventId, String orderId, long totalVnd) {
        if (eventId == null || !eventId.matches("[A-Za-z0-9_-]{1,80}")
                || orderId == null || !orderId.matches("[A-Za-z0-9_-]{1,80}")
                || totalVnd <= 0) {
            throw new IllegalArgumentException("OrderCreated khong hop le");
        }

        String body = eventId + "|" + orderId + "|" + totalVnd;
        rabbitTemplate.convertAndSend(
            OrdersRabbitTopology.EXCHANGE, OrdersRabbitTopology.KEY, body);
    }
}
~~~

Khi gọi publish với **evt-1001**, **O-1001** và **150000**, body minh họa là:

~~~text
evt-1001|O-1001|150000
~~~

Ví dụ này **chưa** sử dụng Spring Integration. Nó cho thấy client trực tiếp RabbitTemplate thực hiện chuyển đổi và publish. Với production, nên dùng JSON/Avro/Protobuf với schemaVersion, eventId ổn định, xác thực dữ liệu và phiên bản hợp đồng.

## 7. RabbitTemplate bên dưới Spring Integration AMQP outbound adapter

Một IntegrationFlow có thể che chi tiết RabbitTemplate khỏi business service bằng cách đưa message vào MessageChannel rồi cấu hình outbound adapter:

~~~mermaid
flowchart LR
    P["ChannelOrderPublisher"] --> M["Spring Message"]
    M --> C["ordersToAmqp<br/>DirectChannel"]
    C --> A["AMQP outbound adapter"]
    A --> RT["RabbitTemplate bean"]
    RT --> CF["ConnectionFactory"]
    CF --> EX["orders.events"]
~~~

### 7.1. Java DSL

~~~java
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.amqp.dsl.Amqp;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
public class OrdersAmqpIntegrationConfiguration {

    @Bean
    public MessageChannel ordersToAmqp() {
        return new DirectChannel();
    }

    @Bean
    public IntegrationFlow ordersOutboundFlow(RabbitTemplate rabbitTemplate) {
        return IntegrationFlow.from("ordersToAmqp")
            .handle(Amqp.outboundAdapter(rabbitTemplate)
                .exchangeName(OrdersRabbitTopology.EXCHANGE)
                .routingKey(OrdersRabbitTopology.KEY))
            .get();
    }
}
~~~

### 7.2. Producer gửi Spring Message vào channel

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Service;

@Service
public class ChannelOrderPublisher {

    private final MessageChannel ordersToAmqp;

    public ChannelOrderPublisher(
            @Qualifier("ordersToAmqp") MessageChannel ordersToAmqp) {
        this.ordersToAmqp = ordersToAmqp;
    }

    public void publish(String eventId, String orderId, long totalVnd) {
        if (eventId == null || !eventId.matches("[A-Za-z0-9_-]{1,80}")
                || orderId == null || !orderId.matches("[A-Za-z0-9_-]{1,80}")
                || totalVnd <= 0) {
            throw new IllegalArgumentException("Event khong hop le");
        }
        String payload = eventId + "|" + orderId + "|" + totalVnd;
        boolean accepted = ordersToAmqp.send(
            MessageBuilder.withPayload(payload)
                .setHeader("eventId", eventId)
                .build());
        if (!accepted) {
            throw new IllegalStateException(
                "Message khong duoc channel chap nhan");
        }
    }
}
~~~

**Chọn một đường publish cho một nghiệp vụ**: RabbitOrderPublisher trực tiếp **hoặc** ChannelOrderPublisher qua IntegrationFlow. Không gọi đồng thời hai service cho một event, vì sẽ gửi hai bản tin.

Với DirectChannel, outbound handler thường được gọi đồng bộ. Nhưng **send() trả về thành công không chứng minh có publisher confirm, không chứng minh message đã được route đúng queue và không chứng minh consumer đã xử lý nghiệp vụ**.

### 7.3. Hợp đồng message qua các lớp

| Lớp | Dữ liệu minh họa | Người chịu trách nhiệm |
| --- | --- | --- |
| Spring Message payload | evt-1001|O-1001|150000 | Producer của flow |
| Spring header eventId | evt-1001 | Ứng dụng để tracing nếu cần |
| AMQP body | Bytes từ String qua MessageConverter | RabbitTemplate |
| Exchange/routing key | orders.events / orders.created | Outbound adapter hoặc RabbitTemplate |
| Queue thực nhận | orders.created.q | Broker topology/binding |

**Không mặc định header eventId tự có trên wire format.** Header mapper có quy tắc riêng; eventId nằm trong payload minh họa để bên nhận đọc được ngay cả khi header không được truyền. Tránh serialize nguyên Spring replyChannel/errorChannel ra broker.

## 8. Publisher confirms, returns và mandatory

Khi thiết kế độ tin cậy của RabbitTemplate, cần phân biệt ít nhất **ba mốc**:

| Cơ chế | Bên phát tín hiệu | Điều nó cho biết | Điều nó không cho biết |
| --- | --- | --- | --- |
| **Publisher confirm** | RabbitMQ → producer | Broker xác nhận ACK/NACK cho publish theo cơ chế confirms | Consumer đã xử lý nghiệp vụ |
| **Publisher return** | RabbitMQ → producer | Message không route được, khi mandatory và returns được cấu hình đúng | Lỗi nghiệp vụ của consumer |
| **Consumer ACK/NACK** | Consumer → RabbitMQ | Consumer xác nhận một delivery theo chế độ ACK | Producer đã nhận business reply |

~~~mermaid
sequenceDiagram
    participant P as RabbitTemplate
    participant E as RabbitMQ exchange
    participant Q as Queue
    participant C as Consumer
    P->>E: basic.publish
    alt Có route phù hợp
        E->>Q: Chuyển message tới queue
    else Không route, mandatory
        E-->>P: basic.return
    end
    E-->>P: Publisher confirm ACK/NACK
    Q-->>C: Delivery từ queue
    C-->>Q: Consumer ACK/NACK riêng
~~~

### 8.1. Correlated publisher confirms

Khi bật **spring.rabbitmq.publisher-confirm-type: correlated**, ứng dụng có thể tạo **CorrelationData** cho một lần publish và theo dõi future/callback nhận kết quả tương ứng.

~~~java
import org.springframework.amqp.rabbit.connection.CorrelationData;
import org.springframework.amqp.rabbit.core.RabbitTemplate;

public class ConfirmAwarePublisher {
    private final RabbitTemplate rabbitTemplate;

    public ConfirmAwarePublisher(RabbitTemplate rabbitTemplate) {
        this.rabbitTemplate = rabbitTemplate;
    }

    public void publish(String eventId, String body) {
        CorrelationData data = new CorrelationData(eventId);

        rabbitTemplate.convertAndSend(
            "orders.events", "orders.created", body, data);

        data.getFuture().whenComplete((confirm, failure) -> {
            if (failure != null) {
                System.err.println("Confirm error: " + eventId);
            } else if (confirm != null && confirm.isAck()) {
                System.out.println("Broker confirmed: " + eventId);
            } else {
                System.err.println("Broker did not confirm ACK: " + eventId);
            }
        });
    }
}
~~~

Đây là **minh họa theo dõi confirms bất đồng bộ**, không phải hệ thống publish tracking hoàn chỉnh. Trong production:

- Cần xác nhận đã bật correlated confirms trên ConnectionFactory/ứng dụng đang dùng.
- Future có thể không hoàn tất đúng lúc nếu có sự cố; phải có timeout, trạng thái **UNKNOWN** và nơi lưu tiến độ.
- Callback có thể chạy trên thread của hạ tầng client; không nên xử lý nghiệp vụ nặng hoặc chặn lâu trong callback.
- Confirm ACK không phải business ACK và không chứng minh message được định tuyến đến queue mong muốn nếu chỉ dựa vào confirm.
- Nếu cần cập nhật outbox, hãy phối hợp confirm, returned message, exception và trạng thái trong database theo một chính sách có kiểm thử.

API CorrelationData/Confirm và cách đăng ký callback cần được đối chiếu với phiên bản Spring AMQP cụ thể; ví dụ giả định phiên bản có API **getFuture()**.

### 8.2. Publisher returns: trường hợp exchange tồn tại nhưng không có route

Giả sử publisher publish tới **orders.events**, nhưng binding **orders.created** đã bị xóa. Exchange vẫn có thể tiếp nhận publish; không có queue nào phù hợp để nhận message. Publisher confirm ACK có thể vẫn xuất hiện, mặc dù message **unroutable**.

Muốn phát hiện, cấu hình:

~~~yaml
spring:
  rabbitmq:
    publisher-returns: true
    template:
      mandatory: true
~~~

RabbitTemplate có cơ chế **ReturnsCallback** để nhận thông tin trả lại. Nếu dùng template được chia sẻ, cần đăng ký callback có điều phối; nhiều thành phần tự thay callback của nhau có thể làm mất tín hiệu cần thiết.

**Mandatory** và **returns** chỉ giúp phát hiện một loại thất bại định tuyến. Nếu publish tới exchange không tồn tại, có thể phát sinh lỗi channel/protocol thay vì returned-message callback; cần kiểm thử từng trường hợp riêng.

### 8.3. Producer confirm không phải consumer ACK

Ngay cả khi broker xác nhận đã nhận sự kiện và nó đã vào queue, consumer phía nhận có thể:

- Chưa kết nối nên message còn chờ.
- Đang xử lý nhưng chưa ACK.
- NACK/requeue do database lỗi.
- ACK quá sớm so với công việc bất đồng bộ downstream.

Vì vậy, nếu nghiệp vụ cần “warehouse đã cập nhật tồn kho”, phải có **phản hồi nghiệp vụ hoặc đối soát** riêng, không dùng kết quả publisher confirm làm bằng chứng.

## 9. MessageConverter và header mapping

RabbitTemplate sử dụng **MessageConverter** khi gọi convertAndSend hoặc convertSendAndReceive. Converter liên quan đến cả **body bytes** lẫn **content type** và các message properties. Không chỉ kiểm tra Java type của payload mà bỏ qua wire format.

| Payload Java | Cách chuyển đổi cần xác định | Rủi ro |
| --- | --- | --- |
| **String** | Charset và content type text | Consumer decode sai charset |
| **byte[]** | Body nhị phân và schema | Không rõ cách diễn giải bytes |
| **DTO Java** | JSON/Avro/Protobuf converter được cấu hình rõ | Không tương thích với ngôn ngữ/phiên bản consumer |
| **Serializable Java object** | Có thể có serialization đặc thù Java nếu converter cho phép | Không phù hợp hệ thống đa ngôn ngữ, nhiều nguy cơ tương thích/bảo mật |

Ví dụ hợp đồng JSON cho OrderCreated:

~~~json
{
  "eventId": "evt-1001",
  "eventType": "ORDER_CREATED",
  "schemaVersion": 1,
  "orderId": "O-1001",
  "totalVnd": 150000
}
~~~

Trong một flow thực tế, có thể **transform** domain OrderCreated thành JSON trước adapter, rồi dùng String converter để tạo AMQP body. Hoặc cấu hình JSON MessageConverter để RabbitTemplate chuyển DTO trực tiếp. **Không serialize hai lần** nếu hai lớp cùng chịu trách nhiệm chuyển sang JSON.

### 9.1. Phân biệt Spring MessageHeaders với AMQP properties

- Spring Integration MessageHeaders có thể chứa **replyChannel**, **errorChannel**, ID, timestamp và header nghiệp vụ.
- AMQP MessageProperties có **contentType**, **contentEncoding**, **messageId**, **correlationId**, deliveryMode và application headers.
- Header mapper quyết định metadata nào được phép chuyển qua ranh giới.

**MessageHeaders.ID mới sinh không phải eventId ổn định.** Không chuyển nguyên Spring MessageChannel hay object hạ tầng vào AMQP headers. Với thông tin nhạy cảm, chỉ cho phép header thực sự cần thiết và tránh ghi toàn bộ properties vào log.

### 9.2. Đặt converter ở đâu?

Một converter có thể được cấu hình trên RabbitTemplate hoặc do endpoint/client khác dùng tùy cách xây dựng ứng dụng. Nếu tạo **RabbitTemplate tùy chỉnh**, cần nhớ auto-config và các endpoint đang inject template nào.

Không nên sửa MessageConverter của một RabbitTemplate dùng chung ở runtime chỉ để phục vụ một message. Hãy cố định hợp đồng serialize theo destination/event type hoặc dùng các template được tách trách nhiệm rõ ràng khi thực sự cần khác nhau.

## 10. RabbitTemplate cho request–reply và listener cho inbound

Đôi khi ứng dụng cần trao đổi hai chiều chứ không chỉ phát event. Ví dụ tính phí giao hàng qua AMQP:

~~~mermaid
flowchart LR
    C["QuoteClient"] --> T["RabbitTemplate<br/>convertSendAndReceive"]
    T --> Q["quotes.request.q"]
    Q --> G["AMQP inbound gateway"]
    G --> H["QuoteService"]
    H --> G
    G --> R["Reply destination"]
    R --> T
    T --> C
~~~

**Request–reply** phải có cơ chế reply-to và correlation; timeout tại client và gateway cần được quản lý. RabbitMQ direct reply-to phù hợp với nhiều RPC ngắn nhưng không phải durable queue lưu kết quả cho client offline. Nếu xử lý có thể kéo dài hàng phút, cân nhắc **job ID + tra cứu trạng thái/callback** thay vì giữ một RPC chờ quá lâu.

### 10.1. RabbitTemplate không thay vai trò listener container

RabbitTemplate có API receive/receiveAndConvert, nhưng ứng dụng tiếp nhận message thường xuyên nên xem xét:

- Spring AMQP **listener container** để nhận message-driven.
- Spring Integration **AMQP inbound channel adapter** để đưa delivery vào MessageChannel.
- Spring Integration **AMQP inbound gateway** nếu request phía ngoài cần reply nghiệp vụ.

Listener container quản lý concurrency, prefetch và acknowledgment theo chế độ AUTO/MANUAL/NONE; những cơ chế đó thuộc phía **consumer**, không phải publisher confirm của RabbitTemplate.

### 10.2. Khi có nhiều request đồng thời

Correlation ID dùng để ghép reply với đúng request; nếu custom reply queue hoặc header mapper làm mất correlation, caller có thể timeout hoặc không nhận đúng reply. Khi retry một RPC có side effect, cần **idempotency key nghiệp vụ** ổn định ngoài correlation.

## 11. Hiệu năng, channel cache và thread model

Khi tải tăng, thường xuất hiện ba nơi nghẽn:

1. **Producer/MessageChannel:** business service phát nhanh hơn khả năng xử lý của outbound endpoint.
2. **RabbitTemplate/ConnectionFactory:** channel pool, connection hoặc network bị giới hạn.
3. **Broker/consumer:** queue backlog tăng vì đích không xử lý đủ nhanh.

| Quan sát | Khả năng nguyên nhân | Việc nên kiểm tra |
| --- | --- | --- |
| Publish latency tăng | Network, broker chậm, channel contention | RTT, connections, channel usage, confirm latency |
| Nhiều connection | Tạo factory/template lặp hoặc cache config sai | Bean scope, factory count và connection lifecycle |
| Channel churn cao | Cache quá nhỏ hoặc workload mở nhiều channel | Cache mode, channel cache metrics, checkout |
| Queue depth tăng | Producer nhanh hơn consumer | Deliver/ack rates, consumer latency và concurrency |
| Nhiều returned messages | Routing/binding sai | Exchange, routing key, mandatory/returns |
| Confirm timeout | Broker/network gặp sự cố hoặc callback không nhận | Confirm/NACK/UNKNOWN, connection errors |
| Executor queue tăng | Worker không theo kịp | Capacity, rejection policy, publish throughput |

### 11.1. DirectChannel, ExecutorChannel và QueueChannel

| Channel trước outbound adapter | Điều xảy ra | Điều cần tránh |
| --- | --- | --- |
| **DirectChannel** | RabbitTemplate được gọi trên chuỗi xử lý đồng bộ | Giữ request thread quá lâu khi broker chậm |
| **ExecutorChannel** | Publish chạy trên executor | Caller tưởng đã publish xong dù mới chuyển việc |
| **QueueChannel** | Polling consumer lấy message rồi publish | Mất message khi crash nếu queue chỉ nằm trong bộ nhớ |

**QueueChannel mặc định không phải kho bền vững**. Với dữ liệu quan trọng, dùng MessageStore thích hợp hoặc transactional outbox để phục hồi message đang chờ. Một channel async có thể cải thiện độ trễ của producer nhưng **không tăng năng lực thực tế của RabbitMQ hoặc consumer** nếu downstream đã quá tải.

### 11.2. Thread safety và tài nguyên dùng chung

RabbitTemplate được thiết kế để dùng như một Spring bean tái sử dụng trong cấu hình thông thường; connection/channel được factory quản lý. Không nên tự giữ cùng một native AMQP channel để nhiều thread thao tác tùy ý. Nếu dùng callback cấp thấp, hãy tôn trọng vòng đời/channel ownership của Spring AMQP.

## 12. Retry, idempotency và transactional outbox

Khi RabbitTemplate publish, lỗi có thể xuất hiện **trước gửi**, **trong lúc kết nối**, **khi broker xử lý** hoặc **sau khi broker đã nhận nhưng trước confirm**. Bảng sau giúp phân loại:

| Lỗi | Ví dụ | Cách xử lý |
| --- | --- | --- |
| **Sai dữ liệu/converter** | DTO không serialize được, schema sai | Sửa dữ liệu/hợp đồng; không retry vô hạn |
| **Connection failure** | Broker down, TLS handshake lỗi | Retry có giới hạn và backoff nếu có thể hồi phục |
| **Permission/topology** | Không có quyền publish, exchange không tồn tại | Sửa cấu hình/ACL, alert |
| **Unroutable** | Exchange có nhưng không có binding đúng | Publisher return, đối soát route và topology |
| **Confirm NACK** | Broker không xác nhận publish thành công | Lưu sự kiện cần thử lại, ghi lỗi |
| **Confirm timeout/UNKNOWN** | Có thể broker đã nhận rồi nhưng callback không tới | Giữ eventId, đối soát hoặc retry idempotent |
| **Consumer business failure** | Consumer DB lỗi sau khi queue nhận | Xử lý ở listener phía nhận, không nhầm với producer lỗi |

### 12.1. Idempotency giữa các lần thử

Giả sử RabbitTemplate đã publish event **evt-1001**, broker nhận nhưng kết nối đứt trước confirm. Nếu producer retry, consumer có thể nhận cùng sự kiện hai lần. Vì vậy:

- Giữ nguyên **eventId = evt-1001** giữa các lần retry.
- Consumer lưu eventId đã xử lý bằng unique constraint/inbox table.
- Nếu request có side effect, xử lý nghiệp vụ và dấu chống trùng trong transaction phù hợp.
- Không dùng MessageHeaders.ID hoặc correlation ID tự phát sinh thay khóa nghiệp vụ ổn định.

**Retry không đồng nghĩa exactly-once.** Dù broker và client có tính năng hỗ trợ độ tin cậy, việc tránh side effect trùng vẫn phải được thiết kế ở tầng nghiệp vụ.

### 12.2. Transactional outbox phối hợp database và RabbitMQ

Nếu OrderService commit đơn hàng rồi gọi RabbitTemplate trực tiếp, ứng dụng có thể chết giữa lúc commit database và publish; sự kiện bị bỏ sót. **Transactional outbox** giúp:

1. Ghi Order và bản ghi OutboxEvent cùng transaction database.
2. Worker đọc outbox và publish bằng RabbitTemplate hoặc Integration AMQP outbound adapter.
3. Theo dõi confirm/return/timeout theo hợp đồng, cập nhật trạng thái đã gửi.
4. Retry khi cần với eventId không đổi; consumer vẫn phải idempotent.

~~~mermaid
flowchart LR
    OS["OrderService"] --> DB["DB transaction"]
    DB --> ORDER["Orders"]
    DB --> OB["OutboxEvent"]
    OB --> W["Outbox publisher"]
    W --> RT["RabbitTemplate / outbound adapter"]
    RT --> MQ["RabbitMQ"]
    MQ --> IC["Idempotent consumer"]
~~~

Outbox **không tự tạo transaction nguyên tử giữa database và RabbitMQ**; nó giúp ghi nhận ý định publish một cách bền vững để phục hồi. Lựa chọn này đặc biệt có ích khi yêu cầu không bỏ sót sự kiện sau khi nghiệp vụ đã commit.

## 13. Bảo mật và lifecycle

### 13.1. Bảo mật kết nối

- Sử dụng TLS và xác minh chứng chỉ/hostname khi môi trường yêu cầu.
- Tài khoản RabbitMQ có quyền tối thiểu theo virtual host/exchange/queue; producer không cần quyền quản trị topology nếu broker do hệ thống khác quản lý.
- Nạp credential từ môi trường/secret manager, có chính sách rotation.
- Giới hạn kích thước message và tránh đặt thông tin nhạy cảm trong headers/log.
- Không vô hiệu hóa kiểm tra host/certificate chỉ để xử lý lỗi kết nối.

### 13.2. Bắt đầu và dừng

RabbitTemplate/ConnectionFactory thường là tài nguyên dùng chung; inbound listener và Integration endpoint có vòng đời **Lifecycle/SmartLifecycle** theo cấu hình. Khi shutdown:

1. Ngừng tạo thêm công việc mới hoặc dừng inbound nguồn trước.
2. Cho những publish đang in-flight được xử lý trong giới hạn vận hành, hoặc lưu trạng thái bền vững để retry.
3. Theo dõi confirm/return pending; đừng đánh dấu event hoàn tất chỉ vì producer thread đã trả về.
4. Dừng endpoint/worker rồi để Spring đóng connection factory và tài nguyên chia sẻ theo lifecycle.
5. Khi restart, đọc trạng thái outbox/queue bền vững và phục hồi theo chính sách idempotency.

Không nên hiểu **stop() luôn đợi mọi confirm** hay **isRunning() đồng nghĩa broker khỏe**. Cần kiểm tra khả năng shutdown và những callback chưa hoàn tất trong hệ thống thực tế.

## 14. Quan sát và chẩn đoán sự cố

| Lớp | Thông tin nên theo dõi |
| --- | --- |
| **Ứng dụng** | Event ID, MessageChannel send, số bản tin chờ trong outbox |
| **RabbitTemplate** | Publish attempts, exception, confirms ACK/NACK, returns, timeout |
| **ConnectionFactory** | Connection/channel count, reconnect, channel cache, TLS/auth errors |
| **RabbitMQ** | Exchange publish rate, route rate, queue ready/unacked, số consumer |
| **Consumer** | Delivery/ack/nack, retry/requeue/DLQ, xử lý nghiệp vụ thành công |
| **Độ trễ** | Publish latency, confirm latency, age của backlog, end-to-end latency |
| **Bảo mật** | Access denied, credential rotation, các lần kết nối bất thường |

**Queue trống không chứng minh publish thất bại** vì consumer có thể đã xử lý rất nhanh. **Queue có message không chứng minh consumer đang khỏe**; phải xem consumer count, ready/unacked, lag và kết quả nghiệp vụ. Ngược lại, endpoint báo running trong Spring cũng chưa chứng minh nó đã có kết nối RabbitMQ ổn định.

### 14.1. Ma trận kiểm thử tích hợp

| Tình huống | Kết quả cần xác minh |
| --- | --- |
| Topology đúng | orders.events + orders.created route đến orders.created.q |
| Thiếu binding | Mandatory/returns phát hiện unroutable theo cấu hình |
| Exchange không tồn tại | Exception/channel error được quan sát, không âm thầm coi thành công |
| Broker bị ngắt | Connection handling và retry/backoff đúng chính sách |
| Confirm ACK | Được liên kết đúng event, không nhầm consumer ACK |
| Confirm timeout | Giữ trạng thái UNKNOWN; retry bảo toàn eventId |
| JSON/charset sai | Converter/consumer phát hiện và xử lý có cấu trúc |
| Hai lần publish cùng eventId | Consumer không tạo side effect trùng |
| Chạy lại ứng dụng | Event outbox chưa confirmed được khôi phục |
| Nhiều consumer một queue | Competing consumers, không mặc nhiên broadcast |
| Nhiều queue cùng exchange | Mỗi hệ thống nhận một bản theo binding |
| Tải đỉnh | Đo connections/channels, confirm latency, queue backlog |
| Shutdown giữa publish | Không mất sự kiện chỉ vì dữ liệu nằm trong channel bộ nhớ |

### 14.2. Các bước thử bài thực hành

1. Khởi động RabbitMQ test và kiểm tra ConnectionFactory của ứng dụng kết nối được.
2. Xác minh exchange **orders.events**, queue **orders.created.q** và binding **orders.created** có thật trên broker.
3. Chọn **một** producer (RabbitTemplate trực tiếp hoặc IntegrationFlow) để publish sự kiện evt-1001.
4. Quan sát payload và properties bằng consumer test hoặc công cụ quản trị RabbitMQ.
5. Bật correlated publisher confirms, mandatory và returns nếu bài kiểm thử cần kiểm tra routing/confirm.
6. Trong test riêng, bỏ binding rồi publish; xác minh returned message được nhận.
7. Mô phỏng broker restart hoặc mất kết nối gần thời điểm confirm, xem event có trạng thái UNKNOWN hay bị đánh dấu sai là hoàn tất.
8. Publish lại cùng eventId, xác minh consumer idempotent.

**Giới hạn demo:** Các ví dụ chỉ mô tả hợp đồng publish và kết nối, không chạy broker hay kiểm thử tự động trong bài. Chưa triển khai đầy đủ publish tracker, outbox hoặc consumer nghiệp vụ; các phần này phải được bổ sung trước production.

## 15. Tình huống thiết kế: một event cho nhiều dịch vụ

Nếu kho và phân tích đều cần mọi OrderCreated, không nên cho hai dịch vụ cùng đọc một queue rồi hy vọng mỗi bên đều nhận message. **Nhiều consumer trên cùng queue thường cạnh tranh nhận delivery.** Hãy dùng những queue độc lập cùng bind vào exchange theo routing phù hợp:

~~~mermaid
flowchart TD
    T["RabbitTemplate"] --> X["orders.events"]
    X -->|"orders.created"| WQ["warehouse.orders.q"]
    X -->|"orders.created"| AQ["analytics.orders.q"]
    WQ --> W["Warehouse consumer"]
    AQ --> A["Analytics consumer"]
~~~

RabbitTemplate chỉ cần publish một lần theo exchange/routing key; broker chịu trách nhiệm định tuyến tới các queue đã khai báo. Mỗi consumer group có backlog, retry, ACK và chính sách lỗi độc lập. Nếu thay direct exchange bằng topic/fanout exchange, cần đánh giá lại binding, routing và quyền, không chỉ đổi tên một bean.

Trong hệ thống đa broker hoặc đa tenant, có thể cần connection factory/routing template riêng. Hãy chọn theo **ranh giới kết nối và bảo mật thực tế**, không tạo connection factory cho từng event hoặc từng queue trên cùng broker mà không có nhu cầu.

## 16. Các sai lầm thường gặp

**“RabbitTemplate là một integration channel.”** RabbitTemplate thao tác với RabbitMQ; MessageChannel chuyển Spring Message nội bộ. Adapter/gateway kết nối hai phía.

**“ConnectionFactory là nơi lưu message.”** Factory cấp connection/channel; queue ở RabbitMQ mới là nơi broker lưu delivery theo chính sách.

**“Mỗi message cần một ConnectionFactory.”** Cách này tạo overhead và khó quản lý tài nguyên. Thường dùng bean singleton với caching theo workload.

**“cache.channel.size là số message tối đa.”** Đây là cấu hình cache channel, không phải queue capacity hay giới hạn payload.

**“convertAndSend trả về nghĩa là consumer đã hoàn tất.”** Producer confirm, routing và consumer ACK là các mốc khác nhau.

**“Confirm ACK chắc chắn message đã vào đúng queue.”** Có thể ACK khi message unroutable; phải kiểm tra mandatory/returns và topology.

**“Durable queue bảo đảm exactly-once.”** Cần message persistence, broker policy, ACK, retries và consumer idempotency; không suy ra exactly-once end-to-end.

**“Có RabbitTemplate thì luôn cần viết loop receive.”** Inbound adapter và listener container phù hợp hơn cho nhiều tác vụ tiêu thụ liên tục.

**“Gửi JSON trong transformer rồi JSON converter lần nữa là vô hại.”** Có thể tạo double encoding; xác định một nơi chịu trách nhiệm wire format.

**“RabbitTemplate.convertSendAndReceive chỉ là publish có confirm.”** Đó là RPC request–reply với reply-to/correlation, khác publisher confirm.

**“Retry lỗi nào cũng an toàn.”** Lỗi schema/permission thường cần sửa cấu hình, còn timeout có thể xuất hiện sau khi broker đã nhận; dùng eventId ổn định.

**“Tạo bean queue đồng nghĩa broker đã có queue.”** Phải có RabbitAdmin/AmqpAdmin đủ quyền hoặc provision topology từ hệ thống hạ tầng.

**“QueueChannel mặc định lưu bền khi restart.”** Mặc định thường lưu trong bộ nhớ; yêu cầu không mất sự kiện cần storage bền vững/outbox.

## 17. Câu hỏi tự kiểm tra

1. RabbitTemplate, ConnectionFactory, CachingConnectionFactory và MessageChannel khác nhau về trách nhiệm ở đâu?
2. Vì sao Spring AMQP ConnectionFactory không thể thay thế tùy tiện bằng com.rabbitmq.client.ConnectionFactory?
3. send và convertAndSend khác nhau về kiểu đầu vào và vai trò MessageConverter thế nào?
4. Khi nào dùng receiveAndConvert, khi nào nên dùng AMQP inbound adapter có listener container?
5. convertSendAndReceive khác gì với một publisher confirm?
6. Một lần DirectChannel.send thành công chứng minh điều gì? Chưa chứng minh điều gì về RabbitMQ và consumer?
7. Vì sao publisher confirm ACK không đủ để xác định message đã tới queue đích? Mandatory và returns được dùng ra sao?
8. Khi broker đã nhận nhưng producer mất confirm, vì sao phải giữ eventId ổn định?
9. CachingConnectionFactory giảm overhead thế nào? Channel cache size có phải queue capacity không?
10. Nếu một ứng dụng cần publish với hai routing key trên cùng broker, có nhất thiết tạo hai ConnectionFactory không?
11. Transactional outbox xử lý rủi ro gì giữa database commit và RabbitTemplate publish?
12. Vì sao hai service muốn nhận mỗi event riêng nên có hai queue thay vì hai consumer trên cùng một queue?
13. Những chỉ số nào giúp phân biệt broker không kết nối được, publish bị unroutable và consumer xử lý chậm?
14. Khi shutdown ứng dụng, vì sao phải xét các publish đang chờ confirms?
15. Khi thêm JSON MessageConverter, cần kiểm tra những gì để tránh converter/transformer chồng chéo?

## Tổng kết

**RabbitTemplate** là API client Spring AMQP để gửi, lấy message và request–reply với RabbitMQ; **ConnectionFactory** cấp kết nối AMQP, còn **CachingConnectionFactory** giúp tái sử dụng connection/channel hiệu quả. Trong Spring Integration, các **AMQP adapter/gateway** dùng những thành phần đó để nối **MessageChannel** với broker mà không làm mã nghiệp vụ phụ thuộc trực tiếp vào RabbitMQ client.

Một thiết kế đáng tin cậy phải xác định exchange/routing key/binding, MessageConverter, content type và các metadata cần truyền; đồng thời **không đánh đồng send, publisher confirm, publisher return, consumer ACK và business reply**. Với các sự kiện quan trọng, cần xử lý timeout/UNKNOWN, eventId ổn định, retry có giới hạn, idempotent consumer và transactional outbox khi phối hợp database. Bên cạnh đó, việc dùng connection cache, TLS, quyền tối thiểu, lifecycle và metrics rõ ràng giúp duy trì luồng AMQP an toàn trong môi trường tích hợp nhiều hệ thống.
