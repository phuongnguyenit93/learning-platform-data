# Publisher confirms và returns

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích **publisher confirms** của RabbitMQ là gì, broker phát **ACK/NACK** cho publisher tại ranh giới nào và vì sao xác nhận đó không phải consumer ACK.
- Phân biệt **publisher return (basic.return)** khi message không được route với **publisher confirm** khi broker xác nhận đã xử lý publish.
- Cấu hình **correlated confirms**, **publisher returns** và **mandatory** qua Spring Boot/Spring AMQP, theo dõi từng message bằng **CorrelationData**.
- Giải thích trạng thái **UNKNOWN** khi mất kết nối hoặc hết thời hạn đợi confirm, cũng như rủi ro gửi trùng khi retry.
- Kết hợp **RabbitTemplate**, AMQP outbound channel adapter và **MessageChannel** trong một Spring Integration flow có hợp đồng gửi một chiều.
- Thiết kế **outbox, eventId, idempotent consumer, retry/backoff, dead-letter** và quy trình đối soát phù hợp với yêu cầu độ tin cậy.
- Kiểm thử các trường hợp publish được route, không có binding, exchange không tồn tại, broker lỗi, confirm đến chậm và consumer xử lý lỗi.

## 1. Bài toán: gọi publish thành công chưa đủ

Giả sử **OrderService** ghi một đơn hàng rồi publish **OrderCreated** lên RabbitMQ. Ứng dụng gọi:

~~~java
rabbitTemplate.convertAndSend(
    "orders.events", "orders.created", "evt-1001|O-1001|150000");
~~~

Lệnh có thể trả về mà **chưa có kết quả cuối cùng** về việc broker chấp nhận publish, định tuyến tới queue mong muốn hay consumer đã xử lý xong. Vì thế, nếu sau lời gọi trên ta lập tức đánh dấu sự kiện **DELIVERED_TO_WAREHOUSE**, ứng dụng có nguy cơ báo sai trạng thái.

RabbitMQ và Spring AMQP cung cấp hai nhóm tín hiệu ở phía publisher:

1. **Publisher confirm:** broker xác nhận ACK hoặc NACK cho một thao tác publish theo cơ chế confirms.
2. **Publisher return:** broker trả lại message **không định tuyến được** khi điều kiện mandatory/returns được đáp ứng.

Hai cơ chế trả lời **hai câu hỏi khác nhau**:

- **Confirm:** Broker đã xử lý/chấp nhận lần publish này ở mức nào?
- **Return:** Có message nào không được route tới queue phù hợp không?

~~~mermaid
flowchart LR
    S["OrderService<br/>OrderCreated"] --> C["MessageChannel"]
    C --> A["AMQP outbound adapter"]
    A --> RT["RabbitTemplate"]
    RT --> EX["RabbitMQ exchange"]
    EX -->|"Binding phù hợp"| Q["Queue"]
    EX -. "Unroutable nếu mandatory" .-> RET["Publisher return"]
    EX -. "ACK/NACK publish" .-> CON["Publisher confirm"]
    Q --> HC["Consumer"]
    HC -. "Consumer ACK/NACK" .-> Q
~~~

**Quan trọng:** RabbitMQ exchange, queue, publisher confirm, publisher return và consumer acknowledgment nằm ở những ranh giới khác nhau. Bài học thuộc chương **Adapter AMQP** trong module **SPRING_INTEGRATION_ADAPTERS**, tập trung vào cách xác định hợp đồng gửi và lỗi của AMQP outbound adapter/gateway; cách suy nghĩ về ranh giới hoàn tất cũng hữu ích khi tích hợp File, SFTP, HTTP, JMS, Kafka hoặc database.

## 2. Năm mốc thường bị nhầm với nhau

| Mốc | Thành phần liên quan | Điều có thể quan sát | Không được suy ra |
| --- | --- | --- | --- |
| **MessageChannel.send() hoàn tất** | Spring Integration | Channel đã xử lý lời gọi gửi theo semantics của nó | RabbitMQ đã lưu message hay consumer đã xử lý |
| **RabbitTemplate gửi publish** | Spring AMQP/client | Client đã thực hiện lời gọi publish; có thể phát hiện lỗi đồng bộ | Đã có publisher confirm hoặc đúng route |
| **Publisher confirm ACK** | RabbitMQ → publisher | Broker xác nhận lần publish theo cơ chế confirms và loại queue/chính sách liên quan | Consumer đã đọc hoặc commit nghiệp vụ |
| **Publisher return** | RabbitMQ → publisher | Message không route được trong điều kiện broker trả message | Broker bị từ chối toàn bộ publish hay consumer lỗi |
| **Consumer ACK** | Consumer → RabbitMQ | Consumer xác nhận một delivery theo mode ACK | Publisher nhận được business reply |

Nếu consumer cần phản hồi **OrderAccepted** hoặc **PaymentResult**, hãy dùng **request–reply gateway** hoặc một luồng phản hồi nghiệp vụ riêng; publisher confirms/returns **không biến outbound adapter một chiều thành gateway**.

### 2.1. Một ví dụ đối lập

Producer publish tới exchange **orders.events**. Exchange tồn tại nhưng không có binding nào khớp routing key **orders.created**.

- Broker vẫn có thể gửi **publisher confirm ACK** vì thao tác publish đã được xử lý.
- Nếu publisher dùng **mandatory=true**, trả message được bật và không có alternate route phù hợp, broker có thể gửi **basic.return** báo bản tin **unroutable**.
- Nếu publisher không bật cơ chế phát hiện unroutable phù hợp, message có thể không tới queue nào mà caller vẫn không có một exception đồng bộ.

Do đó, **chỉ nhìn confirm ACK không đủ để khẳng định message đến queue đích**.

### 2.2. Khi message đã vào queue thì sao?

Kể cả khi RabbitMQ đã route và lưu message vào queue, consumer có thể **chưa hoạt động**, đang chờ database hoặc gặp lỗi schema. Consumer ACK là trao đổi tiếp theo giữa consumer và broker, không được tự động chuyển thành kết quả gửi của producer.

~~~mermaid
sequenceDiagram
    participant P as Publisher / RabbitTemplate
    participant X as RabbitMQ exchange
    participant Q as Queue
    participant C as Consumer
    P->>X: basic.publish(exchange, routing key, body)
    alt Có binding phù hợp
        X->>Q: Route message
    else Unroutable và mandatory
        X-->>P: basic.return
    end
    X-->>P: publisher confirm ACK/NACK
    Q-->>C: Delivery nếu message đã vào queue
    C-->>Q: Consumer ACK/NACK theo mode
~~~

Sơ đồ biểu diễn **các loại sự kiện**, không hứa mọi event sẽ xuất hiện cho mọi message. Ví dụ nếu không có queue nhận thì không có delivery tới consumer; nếu confirms/returns chưa được cấu hình, publisher có thể không có callback tương ứng.

## 3. Publisher confirms hoạt động như thế nào?

RabbitMQ publisher confirms là cơ chế xác nhận **từ broker về publisher**. Sau khi bật confirm mode trên channel, publisher có thể liên kết các bản publish với confirm ACK/NACK do broker trả về.

Trong RabbitMQ client mức thấp, confirm gắn với **publish sequence numbers** trên AMQP channel, và broker có thể xác nhận một hoặc nhiều lần publish theo cơ chế giao thức. **Spring AMQP/RabbitTemplate** bọc phần lớn chi tiết đó để ứng dụng theo dõi qua callback hoặc **CorrelationData**.

### 3.1. ACK của publisher không phải ACK của consumer

Giả sử publisher đã nhận ACK cho **evt-1001**. Điều này là tín hiệu về việc broker xử lý publish theo mức đảm bảo được hỗ trợ bởi exchange/queue và trạng thái broker. Nó **không nói** rằng:

- Warehouse đã nhận delivery.
- Warehouse đã ghi transaction database.
- Consumer không bao giờ được giao lại message.
- Một ứng dụng Analytics khác cũng đã hoàn tất.
- Mọi phần còn lại của workflow đã xong.

**Độ bền publisher confirm** còn phải xem loại queue (classic/quorum), delivery mode, broker cluster, policy và phiên bản RabbitMQ. Không dùng một câu “ACK nghĩa là lưu bền vĩnh viễn trong mọi tình huống”.

### 3.2. Publisher confirm NACK

Broker có thể gửi NACK cho publish trong một số trường hợp không thể xử lý thành công theo cơ chế xác nhận. NACK **không phải** phản hồi “payload sai schema” từ consumer. Khi nhận NACK, publisher cần ghi trạng thái lỗi, phát cảnh báo và cân nhắc retry theo chính sách nghiệp vụ.

**Đừng tự động diễn giải mọi NACK là lỗi tạm thời** hoặc retry vô hạn. Cần thu thập lỗi, thời gian, tình trạng broker và kết quả định tuyến để quyết định.

### 3.3. Async confirms so với synchronous waiting

Có hai cách nhìn kết quả:

- **Bất đồng bộ:** gửi nhiều message rồi tiếp nhận confirm qua callback/future. Phù hợp throughput nhưng cần bảng theo dõi các publish đang chờ.
- **Đợi đồng bộ một confirm:** caller chờ tới khi broker xác nhận hoặc timeout. Dễ reasoning cho một yêu cầu đơn lẻ nhưng có thể chặn thread, giới hạn throughput, và timeout vẫn để lại trạng thái **UNKNOWN**.

Trong Spring AMQP, theo dõi bằng **CorrelationData.getFuture()** là lựa chọn thường dùng khi bật correlated confirms ở phiên bản hỗ trợ. Không được nhầm việc một future hoàn tất **ACK** với việc consumer có business reply.

## 4. Publisher returns và vai trò của mandatory

RabbitMQ publish vào **exchange**. Exchange sử dụng routing key và bindings để quyết định route sang queue nào.

~~~mermaid
flowchart TD
    P["Producer"] --> X["Direct exchange<br/>orders.events"]
    X -->|"orders.created"| Q["orders.created.q"]
    X -. "Key không khớp binding" .-> U["Unroutable"]
    U -->|"mandatory=true<br/>và returns được xử lý"| R["Publisher return<br/>ReturnedMessage"]
    U -->|"mandatory=false<br/>không có AE phù hợp"| DROP["Không có queue nhận"]
~~~

### 4.1. basic.return mang thông tin gì?

Khi broker trả lại một bản publish không route được theo cơ chế **mandatory**, return mang **message** và các dữ liệu chẩn đoán như **reply code/text**, exchange và routing key liên quan. Spring AMQP có lớp dữ liệu tương ứng để xử lý returned message.

Một returned message giúp biết bản tin không đến queue đích theo định tuyến tại thời điểm publish. Nó không có nghĩa consumer đã đọc message rồi từ chối; **đó là lỗi trước delivery**.

### 4.2. Mandatory và publisher returns phải phối hợp

Để phát hiện unroutable ở mức RabbitTemplate, thường cần:

- Cơ chế returns được bật trên ConnectionFactory/client.
- **mandatory=true** cho các publish cần nhận lại message không có route.
- Một **ReturnsCallback** hoặc đường nhận returned message được cấu hình và kiểm thử.

Nếu chỉ bật publisher confirms mà không bật mandatory/returns phù hợp, một message không route được vẫn có thể được broker **ACK ở mức publish**.

### 4.3. Exchange không tồn tại khác binding không khớp

| Tình huống | Khác biệt bản chất | Tín hiệu kỳ vọng |
| --- | --- | --- |
| Exchange **tồn tại**, không có binding khớp | Publish đến đúng exchange nhưng không có đích route | basic.return khi mandatory và điều kiện phù hợp; confirm ACK vẫn có thể xuất hiện |
| Exchange **không tồn tại** | Publish đến tài nguyên exchange sai/thiếu | Lỗi protocol/channel hoặc lỗi publish; không mặc nhiên là basic.return |
| Queue tồn tại nhưng **không có consumer** | Route thành công, chỉ chưa ai nhận | Queue ready có thể tăng; không phải returned message |
| Consumer nhận rồi **reject/requeue** | Lỗi phía sau queue | Consumer NACK/requeue/DLX, không phải publisher return |
| Connection mất trước confirm | Publisher chưa biết broker đã nhận hay chưa | Timeout/connection error, trạng thái UNKNOWN |

### 4.4. Alternate exchange ảnh hưởng kết quả returns

RabbitMQ có thể được cấu hình **alternate exchange (AE)** để nhận bản publish mà exchange chính không route được. Nếu message được route thành công qua AE tới queue dự phòng, điều đó có thể thay đổi việc broker coi message là unroutable và có phát return hay không.

**Không coi việc AE lưu vào một queue khác là đã giao tới queue nghiệp vụ dự kiến.** Cần giám sát queue fallback, có quy trình cảnh báo và xử lý các event không được route theo hợp đồng chính.

## 5. Kiến trúc triển khai trong Spring Integration

Trong một Spring Integration flow, **AMQP outbound channel adapter** nhận Spring Message từ MessageChannel rồi sử dụng RabbitTemplate để publish. Đối tượng và header của Spring Message không phải RabbitMQ native message; adapter/converter/header mapper sẽ ánh xạ theo cấu hình.

~~~mermaid
flowchart LR
    OS["OrderService"] --> MC["ordersToAmqp<br/>MessageChannel"]
    MC --> OA["AMQP outbound adapter"]
    OA --> RT["RabbitTemplate"]
    RT --> CF["ConnectionFactory"]
    CF --> EX["orders.events"]
    EX --> Q["orders.created.q"]
    CF -. "confirm/return" .-> TRACK["Publish tracking<br/>eventId + trạng thái"]
~~~

### 5.1. Loại channel ảnh hưởng tới thời điểm caller biết lỗi

| Channel trước outbound adapter | Hành vi | Rủi ro |
| --- | --- | --- |
| **DirectChannel** | Handler publish được gọi đồng bộ trên luồng gửi | Caller có thể thấy exception đồng bộ nhưng vẫn chưa biết callback confirm/return |
| **ExecutorChannel** | Publish chạy trên executor | send có thể thành công khi mới giao việc; lỗi xuất hiện sau ở thread khác |
| **QueueChannel** | Message được đệm cho polling consumer gửi ra | Cần capacity/poller và nguồn lưu bền nếu muốn khôi phục sau crash |

**MessageChannel.send() trả true không thay thế publisher confirm.** Ngay cả với DirectChannel, việc callback tương lai báo ACK/return thường tách khỏi kết quả boolean của send. Với ExecutorChannel, thời điểm này còn tách xa hơn.

### 5.2. Outbound adapter khác outbound gateway

**Outbound adapter** phù hợp với event one-way: publish OrderCreated rồi các dịch vụ tự xử lý. **Outbound gateway** phù hợp khi cần một **reply nghiệp vụ** qua AMQP request–reply, với reply-to, correlation và timeout.

Publisher confirms chỉ trả thông tin **broker xử lý publish**, publisher returns báo **không route được**; chúng **không làm outbound adapter tự có reply message** từ service bên kia.

### 5.3. Giữ eventId và correlation rõ ràng

Trong phần ví dụ, ta dùng:

~~~text
eventId: evt-1001                 (định danh nghiệp vụ ổn định)
routingKey: orders.created       (định tuyến RabbitMQ)
CorrelationData ID: evt-1001     (liên kết publish với kết quả confirms)
AMQP messageId: có thể đặt riêng (phục vụ tracing)
Spring MessageHeaders.ID: ID hạ tầng nội bộ
~~~

Có thể dùng cùng chuỗi eventId để tạo **CorrelationData** cho một lần publish, nhưng phải hiểu CorrelationData ID dùng **tracking producer**, còn eventId dùng **idempotency nghiệp vụ**. Nếu retry nhiều lần, có thể tạo thêm **attemptId** cho từng lần gửi trong bảng tracking; consumer vẫn phải thấy **cùng eventId** để chống trùng.

## 6. Cấu hình Spring Boot cho publisher confirms và returns

Trong ứng dụng dùng **spring-boot-starter-amqp**, RabbitTemplate/ConnectionFactory thường được Spring Boot cấu hình tự động khi điều kiện phù hợp. Ví dụ cấu hình cho một publisher cần cả confirms và returns:

~~~yaml
spring:
  rabbitmq:
    publisher-confirm-type: correlated
    publisher-returns: true
    template:
      mandatory: true
~~~

Ba thuộc tính phục vụ những mục tiêu khác nhau:

| Thuộc tính | Vai trò |
| --- | --- |
| **publisher-confirm-type: correlated** | Bật correlated publisher confirms cho ứng dụng theo cơ chế Spring AMQP được hỗ trợ |
| **publisher-returns: true** | Cho phép nhận thông tin returned messages |
| **template.mandatory: true** | Yêu cầu broker return bản publish không định tuyến được trong những điều kiện tương ứng |

**Lưu ý phiên bản:** cấu hình trên là mẫu phổ biến của Spring Boot/Spring AMQP hiện đại. Khi nâng cấp, cần kiểm tra tên property và API thực tế của phiên bản được dependency management quản lý.

### 6.1. ConnectionFactory phải đúng bean mà publisher sử dụng

Trong Spring Boot, **CachingConnectionFactory** thường là Spring AMQP ConnectionFactory được dùng chung cho RabbitTemplate và listener. Nếu ứng dụng tạo nhiều ConnectionFactory hoặc RabbitTemplate tùy chỉnh, bật confirms ở một factory **không làm template dùng factory khác tự có confirms**.

Khi gặp tình trạng publish thành công nhưng không có callback, hãy kiểm tra:

- RabbitTemplate đang inject **ConnectionFactory nào**.
- Factory đó có bật **correlated publisher confirms và returns** hay không.
- Đường publish có **mandatory** phù hợp hay không.
- Có callback/future hoặc thành phần tracking **đang thật sự lắng nghe** không.
- Kết nối có bị mất trước khi broker gửi kết quả không.

### 6.2. Khi tự tạo RabbitTemplate

Nếu nhiều endpoint dùng chung một RabbitTemplate, không để các service độc lập tự thay **ConfirmCallback** hoặc **ReturnsCallback** lẫn nhau. Cần một publish tracker tập trung, các template có trách nhiệm riêng hoặc cơ chế callback được Spring Integration quản lý đúng cách.

**Tự tạo RabbitTemplate bean có thể ảnh hưởng auto-configuration của Boot**; vì vậy phải xác nhận template thực tế đã được cấu hình MessageConverter, mandatory và connection factory phù hợp.

### 6.3. Quyền và topology

Publisher cần có quyền publish vào exchange ở đúng RabbitMQ virtual host. Exchange, queue và binding phải được provision bằng RabbitAdmin/AmqpAdmin có quyền hoặc qua hạ tầng bên ngoài. **Khai báo Queue bean không có nghĩa broker đã có queue đó.**

Nên tách tài khoản publisher với tài khoản có quyền quản trị topology nếu chính sách bảo mật yêu cầu. Trong production, nạp username/password từ secret manager, dùng TLS phù hợp và tránh in credential/payload nhạy cảm vào log.

## 7. Ví dụ Spring AMQP: topology và RabbitTemplate

Ta xây dựng một publisher phát **OrderCreated** đến một direct exchange:

~~~text
Exchange:      orders.events
Routing key:   orders.created
Queue:         orders.created.q
Payload:       eventId|orderId|totalVnd
Example:       evt-1001|O-1001|150000
~~~

Đây là hợp đồng minh họa để tập trung vào confirms/returns. Với ứng dụng thật, nên dùng **JSON có eventType/schemaVersion**, validation và serializer được quản lý rõ ràng.

### 7.1. Dependency Spring Boot

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

Các phiên bản cần tương thích với Spring Boot BOM. Tùy hệ thống, broker và topology được tạo tự động qua RabbitAdmin/AmqpAdmin hoặc provision bên ngoài ứng dụng.

### 7.2. Khai báo exchange, queue và binding

~~~java
import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrdersAmqpTopology {
    public static final String EXCHANGE = "orders.events";
    public static final String ROUTING_KEY = "orders.created";
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
            .with(ROUTING_KEY);
    }
}
~~~

Exchange và queue **durable** góp phần duy trì topology qua restart, không đồng nghĩa mỗi message đã được lưu bền và consumer đã xử lý đúng một lần. Cần kiểm tra **delivery mode**, loại queue, confirms và idempotency riêng.

### 7.3. RabbitTemplate chuyên trách theo dõi publish

Nếu muốn sử dụng ReturnsCallback tập trung, có thể tạo một RabbitTemplate riêng cho đường publish OrderCreated:

~~~java
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrdersPublisherTemplateConfiguration {

    @Bean("ordersPublisherTemplate")
    public RabbitTemplate ordersPublisherTemplate(
            ConnectionFactory connectionFactory) {
        RabbitTemplate template = new RabbitTemplate(connectionFactory);

        // Requires publisher returns to be enabled at the connection factory.
        template.setMandatory(true);
        template.setReturnsCallback(returned -> {
            System.err.println(
                "Unroutable exchange=" + returned.getExchange()
                    + ", key=" + returned.getRoutingKey()
                    + ", code=" + returned.getReplyCode()
                    + ", text=" + returned.getReplyText());
        });

        return template;
    }
}
~~~

Đây là **template riêng**, tránh việc một service ghi đè ReturnsCallback do service khác gắn trên template dùng chung. Với Spring Boot property **publisher-returns: true**, cần xác minh ConnectionFactory mà bean mới nhận đúng là factory đã bật returns và correlated confirms. Mã callback chỉ in log để minh họa; **không được xem log là kho trạng thái publish bền vững**.

**Cảnh báo:** Nếu ứng dụng chỉ cần một RabbitTemplate và để Spring Boot tự cấu hình sẵn, có thể sử dụng template đó cùng cơ chế cấu hình callbacks thống nhất. Tạo bean thủ công có thể làm thay đổi điều kiện autoconfiguration; không nên thêm nhiều bean RabbitTemplate không có qualifier rồi để injection mơ hồ.

## 8. Theo dõi từng publish bằng CorrelationData

**CorrelationData** giúp Spring AMQP gắn kết quả confirm với thao tác publish cụ thể. Khi cả correlated confirms và returns hoạt động, dữ liệu trả về do unroutable cũng có thể được gắn với lần publish tương ứng.

Ta dùng hai định danh:

- **eventId** (ví dụ evt-1001): danh tính nghiệp vụ, **không đổi** khi retry.
- **attemptId** (UUID): danh tính từng lần publish, **có thể đổi** khi retry để theo dõi từng lần.

### 8.1. Publisher với confirm future

~~~java
import java.util.UUID;

import org.springframework.amqp.rabbit.connection.CorrelationData;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;

@Service
public class ConfirmTrackedOrderPublisher {
    private final RabbitTemplate rabbitTemplate;

    public ConfirmTrackedOrderPublisher(
            @Qualifier("ordersPublisherTemplate")
            RabbitTemplate rabbitTemplate) {
        this.rabbitTemplate = rabbitTemplate;
    }

    public void publish(String eventId, String orderId, long totalVnd) {
        if (eventId == null || !eventId.matches("[A-Za-z0-9_-]{1,80}")
                || orderId == null
                || !orderId.matches("[A-Za-z0-9_-]{1,80}")
                || totalVnd <= 0) {
            throw new IllegalArgumentException("OrderCreated invalid");
        }

        String body = eventId + "|" + orderId + "|" + totalVnd;
        String attemptId = UUID.randomUUID().toString();
        CorrelationData correlation = new CorrelationData(attemptId);

        try {
            rabbitTemplate.convertAndSend(
                OrdersAmqpTopology.EXCHANGE,
                OrdersAmqpTopology.ROUTING_KEY,
                body,
                correlation);
        } catch (RuntimeException ex) {
            // Publisher outcome might be unknown after some network failures.
            System.err.println(
                "Send exception: event=" + eventId
                    + ", attempt=" + attemptId);
            throw ex;
        }

        correlation.getFuture().whenComplete((confirm, error) -> {
            if (error != null || confirm == null) {
                System.err.println(
                    "Confirm unavailable: " + attemptId);
            } else if (!confirm.isAck()) {
                System.err.println(
                    "Broker NACK: " + attemptId);
            } else if (correlation.getReturned() != null) {
                System.err.println(
                    "Broker ACK but unroutable: " + attemptId);
            } else {
                System.out.println(
                    "Broker ACK and no return: " + attemptId);
            }
        });
    }
}
~~~

**Giả định của ví dụ:** Spring AMQP phiên bản có **CorrelationData.getFuture()**, correlated publisher confirms và returned-message correlation; RabbitTemplate được cấu hình mandatory và connection factory hỗ trợ returns. Cần kiểm tra API đúng theo phiên bản đang dùng.

### 8.2. Cách đọc kết quả cho đúng

| Điều kiện | Diễn giải thận trọng | Hướng xử lý |
| --- | --- | --- |
| Future hoàn tất với **ACK**, **không có returned message** | Broker xác nhận publish; không quan sát unroutable trong cơ chế đã cấu hình | Đạt mốc xác nhận của publisher, **chưa phải consumer processed** |
| Future **ACK**, có **returned message** | Broker xử lý publish nhưng không route tới queue theo hợp đồng | Đánh dấu **UNROUTABLE**, sửa routing/topology |
| Future **NACK** | Broker không xác nhận publish thành công | Ghi trạng thái lỗi, điều tra, retry nếu phù hợp |
| Future hoàn tất lỗi | Không nhận được kết quả xác nhận bình thường | Ghi nhận lỗi/UNKNOWN, đối soát |
| Không nhận confirm trước deadline | Chưa biết broker đã nhận hay chưa | **UNKNOWN**, không tự đánh dấu FAILED chắc chắn |
| convertAndSend ném exception | Lỗi đồng bộ, có thể xảy ra trước hoặc sau một phần tác động | Phân loại nguyên nhân; nếu không chắc broker đã nhận thì vẫn cần idempotency |

**Không nên đồng nhất “không có returned message” với tuyệt đối chắc chắn tất cả queue đích đã nhận.** Kết luận phụ thuộc việc mandatory/returns thực sự được bật và hoạt động, trạng thái connection, alternate exchange, topology và các chính sách khác. Với fanout hoặc nhiều queue đích, publisher confirm cũng không chứng nhận mỗi downstream business handler đã hoàn tất.

### 8.3. ReturnedMessage và thứ tự callback

Với Spring AMQP hỗ trợ correlated returns, thông tin **returned message** được gắn vào CorrelationData trước khi future confirm tương ứng được hoàn tất, trong những điều kiện tính năng đó hoạt động. Vì vậy có thể xem **correlation.getReturned()** khi xử lý confirm.

Tuy nhiên không nên tự ghép event bằng cách dựa vào **thứ tự thời gian của log** hoặc giả định callbacks luôn chạy cùng thread. Trong thực tế các publish đồng thời có thể confirm khác thứ tự gửi. Cần **attemptId** và eventId được lưu có cấu trúc.

### 8.4. Vì sao callback demo chưa đủ cho production?

Mã trên mới in log, chưa:

- Lưu trạng thái trước khi publish.
- Áp thời hạn tối đa đợi confirm cho từng attempt.
- Giải phóng tài nguyên tracking đúng lúc.
- Xử lý restart trước callback.
- Ngăn gửi đồng thời cùng eventId không có chủ đích.
- Cập nhật **outbox** và retry sau lỗi.
- Chứng minh kết quả consumer nghiệp vụ.

**Không thực hiện transaction database hoặc gọi HTTP chặn lâu trực tiếp trong thread callback** nếu chưa có thiết kế concurrency/lifecycle phù hợp. Nên chuyển kết quả sang một worker/publish tracking service có kiểm soát.

## 9. Dùng RabbitTemplate trong Spring Integration AMQP outbound flow

Spring Integration giúp business code gửi **Spring Message** tới channel; **AMQP outbound adapter** chịu trách nhiệm chuyển qua RabbitTemplate:

~~~java
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.amqp.dsl.Amqp;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
public class OrdersIntegrationFlow {

    @Bean
    public MessageChannel ordersToAmqp() {
        return new DirectChannel();
    }

    @Bean
    public IntegrationFlow ordersOutbound(
            @Qualifier("ordersPublisherTemplate")
            RabbitTemplate rabbitTemplate) {
        return IntegrationFlow.from("ordersToAmqp")
            .handle(Amqp.outboundAdapter(rabbitTemplate)
                .exchangeName(OrdersAmqpTopology.EXCHANGE)
                .routingKey(OrdersAmqpTopology.ROUTING_KEY))
            .get();
    }
}
~~~

Ví dụ producer gửi Spring Message vào channel:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Service;

@Service
public class OrdersChannelPublisher {

    private final MessageChannel ordersToAmqp;

    public OrdersChannelPublisher(
            @Qualifier("ordersToAmqp") MessageChannel ordersToAmqp) {
        this.ordersToAmqp = ordersToAmqp;
    }

    public void publish(String eventId, String orderId, long totalVnd) {
        String payload = eventId + "|" + orderId + "|" + totalVnd;
        boolean accepted = ordersToAmqp.send(
            MessageBuilder.withPayload(payload)
                .setHeader("businessEventId", eventId)
                .build());

        if (!accepted) {
            throw new IllegalStateException(
                "MessageChannel did not accept message");
        }
    }
}
~~~

**Hãy chọn một lối gửi duy nhất cho mỗi event:** ví dụ **ConfirmTrackedOrderPublisher trực tiếp gọi RabbitTemplate** hoặc **OrdersChannelPublisher đi qua Spring Integration outbound adapter**. Nếu một business operation gọi cả hai, sẽ tạo hai lần publish.

### 9.1. Cần chú ý về correlation trên outbound adapter

Việc RabbitTemplate có correlated confirms **không đồng nghĩa outbound adapter tự động tạo đúng CorrelationData từ businessEventId và cung cấp đủ tracking cho ứng dụng**.

Nếu cần xử lý ACK/NACK/return ở cấp **Spring Integration message**, hãy dùng các tùy chọn confirm correlation và những channel thông báo confirm/return mà **phiên bản Spring Integration AMQP** hỗ trợ, rồi kiểm thử:

1. Một Spring Message có eventId đi qua adapter.
2. Một kết quả confirm/return được gắn đúng event/attempt.
3. Confirm ACK nhưng unroutable không bị đánh dấu sai là đã giao thành công.
4. Message không có tracking metadata có chính sách xử lý rõ ràng.
5. Lỗi bất đồng bộ không bị bỏ qua chỉ vì MessageChannel.send() đã trả về.

Ví dụ Java DSL ở trên minh họa **đường publish một chiều**. Mẫu **ConfirmTrackedOrderPublisher** ở mục 8 mới minh họa thao tác tạo CorrelationData trực tiếp. Không được coi hai ví dụ tương đương về khả năng tracking khi chưa cấu hình các tùy chọn confirm của outbound adapter.

### 9.2. Kiểu payload và type conversion

Trong ví dụ, payload String được converter của RabbitTemplate chuyển thành AMQP body bytes. Nếu cần JSON DTO, cấu hình MessageConverter/transformer và schemaVersion phù hợp; không giả định header **businessEventId** nội bộ tự xuất hiện nguyên vẹn trong AMQP properties.

Định danh nghiệp vụ quan trọng có thể nằm trong payload theo hợp đồng để consumer vẫn chống trùng được khi header mapper thay đổi. **Content type, charset, eventType, schemaVersion** phải được kiểm tra bằng contract test.

### 9.3. Một reply message có xuất hiện trong outbound adapter không?

**Không phải business reply theo mặc định.** Outbound channel adapter là endpoint một chiều. Confirm ACK và publisher return là tín hiệu về publish, khác message phản hồi nghiệp vụ. Nếu flow cần sử dụng reply từ một dịch vụ khác, cần outbound gateway hoặc một workflow event-based có correlation business rõ ràng.

## 10. Trạng thái UNKNOWN: broker có thể đã nhận nhưng publisher chưa biết

Trường hợp khó nhất không hẳn là NACK hay return, mà là **không nhận được câu trả lời rõ ràng**.

~~~mermaid
sequenceDiagram
    participant A as Order publisher
    participant R as RabbitMQ
    participant D as Tracking store
    A->>D: Lưu event evt-1001 = PENDING
    A->>R: basic.publish(evt-1001)
    R->>R: Có thể đã route và lưu message
    Note over A,R: Mất kết nối / confirm không về
    A->>D: UNKNOWN (chưa đủ bằng chứng)
    A->>D: Lập lịch đối soát hoặc retry an toàn
    A->>R: Gửi lại cùng eventId nếu cần
    Note over R: Có thể có delivery trùng<br/>Consumer cần idempotency
~~~

Ở bước mất kết nối, publisher có thể **không biết chắc** broker đã nhận bản publish hay chưa. Nếu đánh dấu **FAILED_UNSENT** và gửi lại không có chống trùng, consumer có thể áp dụng side effect hai lần. Nếu đánh dấu **SUCCESS** mà broker chưa nhận, sự kiện có thể bị mất.

**UNKNOWN không phải lỗi đặt tên cho đẹp**; đây là một trạng thái kết quả thực sự không quan sát đủ ở hệ phân tán. Cần có nơi lưu trạng thái và một chính sách quyết định tiếp theo.

### 10.1. State machine gợi ý

~~~mermaid
flowchart TD
    N["NEW / PENDING"] --> S["SENDING<br/>attemptId"]
    S -->|"ACK + no return observed"| C["PUBLISH_CONFIRMED"]
    S -->|"Returned unroutable"| U["UNROUTABLE"]
    S -->|"Broker NACK"| F["RETRYABLE_FAILURE<br/>hoặc điều tra"]
    S -->|"Exception / timeout<br/>không đủ chứng cứ"| UN["UNKNOWN"]
    F --> RET["Bounded retry + backoff"]
    UN --> RECON["Đối soát + retry idempotent"]
    RET --> S
    RECON --> S
    U --> FIX["Sửa topology / route"]
~~~

Những trạng thái này là **ví dụ ứng dụng tự thiết kế**, không phải enums mặc định của RabbitTemplate hay Spring Integration. Tên **PUBLISH_CONFIRMED** chỉ là mốc broker, không được diễn giải thành **BUSINESS_COMPLETED**.

### 10.2. Dữ liệu tối thiểu trong publish tracking

| Trường | Vì sao cần |
| --- | --- |
| **eventId** | Định danh nghiệp vụ ổn định qua các lần gửi |
| **attemptId** | Phân biệt các lần publish, ghép với CorrelationData |
| **exchange / routingKey** | Đối soát topology/routing |
| **schemaVersion / contentType** | Biết hợp đồng của payload đã phát |
| **attemptCount / nextRetryAt** | Giới hạn retry và backoff |
| **lastError / returnedInfo** | Điều tra NACK, unroutable, timeout |
| **lastSentAt / confirmedAt** | Quan sát độ trễ và quá hạn |
| **status** | Quyết định phục hồi sau restart |

Nếu payload cần lưu để phát lại, phải lưu **body hoặc tham chiếu bền vững** tới dữ liệu đó, chứ không chỉ lưu eventId. Sự kiện quan trọng cũng cần chính sách retention, PII và quyền truy cập tracking store.

### 10.3. Timeout phải là deadline, không phải kết luận broker từ chối

Một thao tác gửi có thể hết thời gian chờ:

- Kết nối chậm hoặc bị ngắt.
- Broker quá tải hoặc bị chặn publisher.
- Callback đến trễ.
- Application callback worker không kịp xử lý.
- Tiến trình restart trước khi nhận kết quả.

Không có confirm đúng hạn **chưa đủ** để suy ra broker chưa từng nhận message. Thời hạn chờ confirm phải được định nghĩa theo SLA và đi cùng một **timeout sweeper** có khả năng cập nhật những attempt bị treo trạng thái SENDING.

## 11. Retry, eventId và idempotent consumer

Khi publisher retry sau NACK, timeout hoặc mất connection, broker có thể nhận **nhiều bản publish cùng một event nghiệp vụ**. RabbitMQ không tự cung cấp exactly-once business execution xuyên producer, queue, consumer và database.

### 11.1. Một chuỗi có thể tạo trùng

1. Producer publish OrderCreated với **eventId = evt-1001**.
2. Broker route message và có thể gửi confirm, nhưng publisher không nhận được.
3. Producer retry với **cùng eventId**.
4. Consumer nhận hai delivery chứa evt-1001.
5. Consumer phải phát hiện eventId đã được áp dụng, tránh tạo hai đơn hàng hoặc trừ tồn kho hai lần.

~~~mermaid
flowchart LR
    P["Producer retry<br/>evt-1001"] --> Q["RabbitMQ queue"]
    Q --> C["Consumer"]
    C --> D{"Inbox đã có<br/>evt-1001?"}
    D -->|"Chưa"| T["Transaction:<br/>business + mark processed"]
    D -->|"Rồi"| SK["Bỏ qua side effect trùng"]
~~~

**Không dùng CorrelationData ID mới của lần retry thay eventId của dữ liệu nghiệp vụ.** CorrelationData phục vụ tracking từng publish; eventId phục vụ chống trùng ở mọi phía nhận.

### 11.2. Cần bảo vệ điều gì ở consumer?

Với một bảng **processed_event** có unique key theo **consumer_name + event_id** hoặc một business key phù hợp:

- Nếu event chưa xử lý, ghi dấu và thực hiện side effect trong transaction dữ liệu khi có thể.
- Nếu event đã xử lý, trả về/ACK theo chính sách mà **không lặp side effect**.
- Nếu hai delivery được xử lý đồng thời, unique constraint phải ngăn race condition.
- Nếu eventId giống nhưng payload/schema khác, phát hiện conflict, không âm thầm coi là bản sao hợp lệ.

Idempotency là **trách nhiệm của consumer** khi side effect cần được bảo vệ. Một ACK từ broker tới publisher không có khả năng thay thế unique constraint của database.

### 11.3. Retry phải phân biệt loại lỗi

| Lỗi | Tính chất thường gặp | Hành động nên cân nhắc |
| --- | --- | --- |
| Broker tạm thời không sẵn sàng | Có thể hồi phục | Retry có giới hạn, backoff và jitter |
| Connection mất gần confirm | Kết quả không rõ | UNKNOWN + retry idempotent hoặc đối soát |
| Broker confirm NACK | Broker không xác nhận publish | Ghi lỗi, retry/alert theo policy |
| Unroutable vì thiếu binding | Sai topology, thường lỗi cấu hình | Cách ly/alert, sửa binding trước khi phát lại |
| Exchange không tồn tại | Sai cấu hình/topology | Kiểm tra quyền, khai báo exchange, migration |
| Payload không serialize được | Dữ liệu/hợp đồng lỗi cố định | Sửa dữ liệu, không retry nóng |
| Không đủ quyền publish | ACL/credential | Sửa quyền hoặc tài khoản, không retry vô hạn |
| Consumer parse lỗi | Sau khi đã vào queue | Chính sách retry/DLQ ở consumer, không phải publisher return |

**Backoff** giúp tránh bão retry khi broker đang lỗi. **Jitter** giúp nhiều instance không đồng thời gửi lại cùng thời điểm. Cần giới hạn attempts, deadline, queue công việc chờ và tài nguyên tracking; không retry vô hạn trên thread gọi HTTP.

## 12. Transactional outbox phối hợp database và AMQP

Một quy trình điển hình:

~~~text
OrderService ghi order vào database
       |
       v
RabbitTemplate publish OrderCreated
~~~

Nếu ứng dụng chết **sau khi commit order nhưng trước khi publish**, sẽ không có event tương ứng ở broker. Nếu publish thành công nhưng crash **trước khi ghi trạng thái đã publish**, event có thể được gửi lại. Publisher confirms giúp biết broker đã xử lý publish nhưng **không tạo transaction nguyên tử xuyên database và RabbitMQ**.

### 12.1. Mô hình outbox

~~~mermaid
flowchart LR
    S["OrderService"] --> TX["DB transaction"]
    TX --> O[("Orders")]
    TX --> OB[("OutboxEvent")]
    OB --> W["Outbox publisher worker"]
    W --> RT["RabbitTemplate<br/>CorrelationData"]
    RT --> MQ["RabbitMQ"]
    MQ --> C["Idempotent consumer"]
    RT -. "Confirm / Return / UNKNOWN" .-> W
    W --> OB
~~~

Một triển khai có thể:

1. Ghi **Order** và **OutboxEvent** trong **cùng transaction database**.
2. Worker lấy event đang chờ, đánh dấu attempt và gửi qua RabbitTemplate hoặc AMQP outbound adapter.
3. Theo dõi **confirm ACK/NACK**, **returned message** và timeout.
4. Đánh dấu đạt mốc publish theo chính sách đã chọn; nếu UNROUTABLE hoặc UNKNOWN thì không gộp với business completion.
5. Khi worker restart, đọc event chưa ở trạng thái hoàn tất, thử lại với **eventId cũ** và attemptId mới.
6. Consumer dùng inbox/idempotency để tránh side effect trùng.

### 12.2. Tại sao không đánh dấu outbox SENT ngay sau convertAndSend?

Lời gọi **convertAndSend** thông thường không tự đợi kết quả correlated confirm. Nếu cập nhật outbox SENT ngay sau khi method return, publish có thể:

- Không có binding phù hợp và bị return.
- Broker NACK.
- Mất kết nối trước khi kết quả được biết chắc.

**SENT** phải có định nghĩa nghiệp vụ/kiến trúc cụ thể. Một trạng thái an toàn hơn có thể là **PUBLISHED_CONFIRMED** sau khi broker ACK và không quan sát return trong cơ chế configured; còn **BUSINESS_PROCESSED** cần xác nhận riêng từ consumer nếu bắt buộc.

### 12.3. Outbox chưa phải exactly-once

Outbox cung cấp **nguồn phát lại bền vững** và giảm nguy cơ mất sự kiện giữa DB commit và publish. Nó **không** bảo đảm một event chỉ được publish đúng một lần trong mọi trường hợp. Worker có thể retry khi mất confirm hoặc crash giữa publish và cập nhật trạng thái. Consumer idempotency vẫn cần.

### 12.4. Publisher confirms so với RabbitMQ transaction

RabbitMQ có các cơ chế transaction/channel riêng, nhưng bật transaction không đồng nghĩa tự có một giao dịch nguyên tử chung với database của OrderService. Publisher confirms thường được ưu tiên xem xét khi cần theo dõi publish có throughput tốt, kết hợp durable outbox và consumer idempotency theo yêu cầu.

Không nên trộn semantics **RabbitMQ publisher confirms**, **Spring transaction manager**, **JDBC transaction** và **consumer ACK** thành một khái niệm commit duy nhất.

## 13. Publisher returns không phải dead-letter queue

Đây là một nhầm lẫn dễ gây mất dữ liệu:

| Cơ chế | Giai đoạn tác động | Vai trò |
| --- | --- | --- |
| **Publisher return** | Khi exchange không route được publish trong điều kiện mandatory | Báo producer về bản tin không có route |
| **Alternate exchange** | Khi exchange chính không route được và có AE phù hợp | Cho broker thử route qua exchange dự phòng |
| **Dead-letter exchange (DLX)** | Sau khi message đã nằm trong queue và bị dead-letter theo rule | Chuyển delivery lỗi/quá hạn/quá giới hạn sang route khác |
| **Retry queue / delayed retry** | Theo một thiết kế retry cụ thể | Trì hoãn xử lý lại theo thời gian |
| **Outbox/error store** | Bên producer trước/trong/sau publish | Giữ ý định gửi và trạng thái khi publish thất bại |

### 13.1. Ví dụ unroutable

~~~text
Publisher -> orders.events (exchange có thật)
           -> routingKey = orders.unknown
           -> không có binding phù hợp
           -> mandatory=true => basic.return về publisher
~~~

Không cần consumer chạy thì publisher đã có thể phát hiện vấn đề route này. **DLQ của consumer không tự nhận message** vì bản tin chưa từng được route vào queue chính.

### 13.2. Ví dụ consumer dead-letter

~~~text
Publisher -> orders.events
           -> orders.created.q
           -> consumer nhận nhưng parse JSON lỗi
           -> reject/NACK requeue=false
           -> DLX/DLQ nếu queue được cấu hình đúng
~~~

Đây là một tình huống khác. Publisher có thể đã nhận confirm ACK từ trước, còn consumer chưa xử lý thành công và delivery được dead-letter theo policy.

### 13.3. Alternate exchange và cảnh báo

Nếu dùng **alternate exchange** để thu gom unroutable, hãy thiết kế queue dự phòng, retention, DLQ hoặc công cụ điều tra. Đừng bỏ qua các message ở AE vì “publisher không nhận return nên mọi thứ ổn”. Một event được giữ ở queue lỗi routing vẫn **chưa tới consumer nghiệp vụ dự kiến**.

## 14. Throughput, in-flight confirms và khả năng chịu tải

Publisher confirms tạo một luồng tín hiệu ACK/NACK từ broker về producer. Khi publisher gửi nhanh, tại một thời điểm có thể có nhiều publish **chưa nhận confirm**. Nếu không giới hạn số attempt đang theo dõi, ứng dụng có thể tăng bộ nhớ và mất ổn định khi broker chậm.

### 14.1. Các cách tổ chức confirms

| Mô hình | Ưu điểm | Rủi ro / đánh đổi |
| --- | --- | --- |
| **Gửi một message, đợi confirm** | Đơn giản để reasoning theo từng message | Latency cao, throughput thấp nếu round-trip lớn |
| **Gửi một batch, đợi toàn bộ** | Giảm overhead chờ từng message | Khó biết message nào cần retry nếu tracking không chi tiết |
| **Async correlated confirms** | Có thể duy trì nhiều publish in-flight | Phải giới hạn số pending, match từng result, quản lý timeout và restart |

Spring AMQP **CorrelationData** và confirm callbacks giúp xử lý kiểu bất đồng bộ. Nhưng chính ứng dụng vẫn phải thiết kế:

- **Pending count/limit:** bao nhiêu publish chưa confirmed được phép tồn tại cùng lúc?
- **Queue capacity:** publisher worker nhận thêm việc ra sao nếu broker chậm?
- **Timeout:** khi nào một attempt chuyển sang UNKNOWN?
- **Retry scheduling:** có backoff, giới hạn, jitter và tránh hot loop không?
- **Shutdown:** những attempt chưa resolved được giữ bền vững ở đâu?

### 14.2. Không đặt công việc nặng vào callback

Confirm/return callbacks có thể được gọi bởi các thread phục vụ I/O/hạ tầng Spring AMQP. Một callback chạy SQL transaction kéo dài, gọi HTTP đồng bộ hoặc sleep có thể làm chậm việc xử lý những confirms khác.

Phương án thường tốt hơn: callback tạo một **kết quả nhỏ** gồm attemptId, trạng thái, thời điểm; chuyển cho một worker/tracking service chịu trách nhiệm cập nhật database. Nếu việc chuyển kết quả giữa các thread không bền vững, cần có **timeout sweeper** trên bảng outbox để xử lý những publish chưa được cập nhật khi ứng dụng crash.

### 14.3. Đo đúng điểm nghẽn

| Triệu chứng | Nguyên nhân có thể | Kiểm tra |
| --- | --- | --- |
| Publish calls chậm | Network, blocked connection, broker quá tải | Connection, broker alarms, publish latency |
| Confirm latency tăng | Broker/queue persistence, tải, network hoặc callback bị chậm | Confirm p50/p95/p99, pending count |
| NACK tăng | Broker không xử lý publish như kỳ vọng | Broker logs, NACK reason khi có, retry |
| Returns tăng | Binding/routing sai hoặc topology bị đổi | Exchange, routing key, queue/bindings, AE |
| Pending confirms tồn quá lâu | Mất connection, callback không tới hoặc application bị quá tải | Timeout sweeper, connection events, tracking |
| Producer ACK tốt nhưng queue backlog tăng | Consumer chậm hoặc offline | Queue ready/unacked, consumer count, ACK rate |
| Consumer processed thấp dù queue nhỏ | Có thể message bị route sai, bị reject/DLQ, ACK sớm | Route rate, returns, DLQ, business metrics |

**Tăng số thread publish không tự làm RabbitMQ hoặc consumer nhanh hơn.** Tối ưu phải dựa trên năng lực broker, kích thước message, độ bền queue, connection/channel, producer confirms và tốc độ xử lý phía nhận.

### 14.4. Kích thước payload và độ bền broker

Publish message lớn làm tăng network, memory, CPU serialization và thời gian chờ broker xác nhận. Nếu sự kiện chứa file SFTP hàng trăm MB, thường nên gửi **metadata/tham chiếu tới object storage** thay vì nhét toàn bộ file vào một AMQP body, trừ khi đã đánh giá kỹ giới hạn và nhu cầu.

Loại queue (classic/quorum), message persistence, cluster replication, broker disk flow control và network latency có thể tác động tới thời gian confirm. Không copy một ngưỡng confirm timeout từ môi trường local sang production khi điều kiện độ bền và lưu lượng khác nhau.

## 15. Kiểm thử publisher confirms và returns

Kiểm thử chỉ gửi một message rồi thấy consumer in log **chưa đủ** để xác minh độ tin cậy. Cần một bộ test chủ động tạo các trạng thái broker và route khác nhau.

### 15.1. Ma trận kiểm thử bắt buộc

| Trường hợp | Điều kiện | Tín hiệu/kết quả cần kiểm tra |
| --- | --- | --- |
| **Route đúng** | Exchange, queue, binding đúng | Confirm ACK theo cơ chế; không có return; queue/consumer có message |
| **Không có binding** | Exchange có thật, routing key không khớp | Return khi mandatory/returns đúng; confirm có thể vẫn ACK |
| **Exchange không tồn tại** | Publish sai exchange name | Lỗi channel/protocol hoặc publish; không coi là normal return |
| **Broker dừng trước publish** | Không có connection | Exception/attempt failure; outbox không đánh dấu publish confirmed |
| **Broker mất gần confirm** | Publish có thể đã được broker nhận | UNKNOWN/timeout, retry giữ eventId |
| **ReturnsCallback bị thiếu** | Publish unroutable, mandatory và returns cấu hình chưa đủ | Test phải phát hiện bị thiếu quan sát, không coi false positive |
| **Publisher confirms chưa bật** | ConnectionFactory không có correlated confirms | Future/callback không hoạt động như yêu cầu; startup test/config validation |
| **Callback đến khác thứ tự** | Publish nhiều message đồng thời | Correlation theo attemptId, không dựa vào order log |
| **Message lớn** | Payload vượt kích thước cho phép | Truy vết lỗi converter/broker và giới hạn resource |
| **Consumer offline** | Route đúng, không consumer | Queue backlog tăng, không xuất hiện publisher return vì consumer chưa chạy |
| **Consumer reject** | JSON lỗi sau delivery | Consumer DLQ/ACK policy, không phải publisher return |
| **Alternate exchange** | Key không match exchange chính nhưng có AE | Message tới alternate queue theo policy, được cảnh báo khác route chính |
| **Restart publisher** | Outbox có attempt chưa resolved | Event được phục hồi, idempotency tránh side effect trùng |
| **Tải đỉnh** | Nhiều event đồng thời | Pending confirms, heap, latency, retry, callbacks không bị mất |

### 15.2. Test correlated confirm cho route hợp lệ

Trong một integration test chạy với RabbitMQ **riêng cho test**, có thể sử dụng:

~~~java
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.UUID;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.amqp.rabbit.connection.CorrelationData;
import org.springframework.amqp.rabbit.core.RabbitTemplate;

public class PublisherConfirmIntegrationTest {

    private final RabbitTemplate rabbitTemplate;

    public PublisherConfirmIntegrationTest(RabbitTemplate rabbitTemplate) {
        this.rabbitTemplate = rabbitTemplate;
    }

    @Test
    void routedPublishGetsConfirm() throws Exception {
        CorrelationData data =
            new CorrelationData(UUID.randomUUID().toString());

        rabbitTemplate.convertAndSend(
            "orders.events",
            "orders.created",
            "evt-test-1|O-test-1|150000",
            data);

        CorrelationData.Confirm confirm =
            data.getFuture().get(5, TimeUnit.SECONDS);

        assertNotNull(confirm);
        assertTrue(confirm.isAck());
        // Check the return condition separately if mandatory is enabled.
        assertTrue(data.getReturned() == null);
    }
}
~~~

**Điều kiện test:** RabbitTemplate phải dùng ConnectionFactory có correlated confirms và returns, mandatory thích hợp; **orders.events** có binding thật tới **orders.created.q**. Đây là một đoạn test minh họa cách đợi future, không tự động chứng minh consumer đã commit.

Với JUnit/Spring Boot test thực tế, cần tạo test context và tiêm RabbitTemplate phù hợp, chẳng hạn qua Spring test extension và cấu hình tích hợp; không sao chép class này như một unit test standalone thiếu injection rồi cho rằng có thể chạy ngay.

### 15.3. Test returned message khi không có route

Trong **test broker cô lập**, publish vào exchange hợp lệ nhưng chọn routing key không match binding:

~~~java
CorrelationData data =
    new CorrelationData("attempt-unroutable-1");

rabbitTemplate.convertAndSend(
    "orders.events",
    "orders.key.that.does.not.exist",
    "evt-test-2|O-test-2|150000",
    data);

CorrelationData.Confirm confirm =
    data.getFuture().get(5, TimeUnit.SECONDS);

// With publisher confirms and returns correctly configured:
// confirm can be ACK, while data.getReturned() is non-null.
// The returned message provides exchange, routing key and reply info.
~~~

Không viết test mong đợi **NACK bắt buộc** khi unroutable: broker có thể xác nhận **ACK** ở mức publish trong khi gửi **return**. Với một alternate exchange có route phù hợp, kết quả cũng có thể khác; test phải biết topology của broker test.

### 15.4. Vì sao test phải kiểm tra cả broker và trạng thái ứng dụng?

Một test chỉ nhìn CorrelationData future không chứng minh outbox worker đã ghi đúng **PUBLISH_CONFIRMED** hoặc **UNROUTABLE**. Với flow production, cần kiểm tra:

1. Attempt được lưu **trước khi gửi**.
2. ACK/NACK/return/timeout ánh xạ đúng attemptId và eventId.
3. Outbox state được cập nhật idempotently.
4. Nếu process chết trước cập nhật, event chưa hoàn tất được phục hồi.
5. Consumer xử lý trùng an toàn khi broker nhận lại cùng event.

### 15.5. Phân biệt Testcontainers/integration test với unit test

**Unit test** có thể kiểm tra một hàm phân loại kết quả confirm/return và state machine bằng mocks, không cần broker. Nhưng nó **không chứng minh** broker thực sự phát basic.return, channel có bật confirms hoặc queue binding đúng. Những behavior này nên có **integration test với RabbitMQ thật trong môi trường test**, chạy song song với các test hợp đồng converter và xử lý dữ liệu.

## 16. Quan sát và vận hành publisher

Publisher confirms/returns cần đi cùng observability rõ ràng. Một ứng dụng báo endpoint RUNNING nhưng publisher returns tăng nhanh vẫn có thể **không đưa được message tới queue mong muốn**.

### 16.1. Các metric nên có

| Metric gợi ý | Mục đích |
| --- | --- |
| **publish_attempt_total** | Số lần bắt đầu publish theo eventType/destination |
| **publish_confirm_ack_total** | Số publish đã được broker ACK |
| **publish_confirm_nack_total** | Số publish broker NACK |
| **publish_return_total** | Số returned messages (unroutable) |
| **publish_unknown_total** | Số attempt quá hạn hoặc không rõ kết quả |
| **publish_pending_count** | Số attempt đang chờ xác nhận |
| **publish_confirm_latency** | Độ trễ từ publish tới confirm |
| **outbox_pending_age** | Thời gian sự kiện chờ được phát |
| **outbox_retry_total** | Số lần thử lại |
| **queue_ready/unacked** | Tình hình backlog ở RabbitMQ |
| **consumer_business_success_total** | Số nghiệp vụ thực sự xử lý ở consumer |

Đây là **tên metric đề xuất**, không phải cam kết Spring Integration/RabbitTemplate cung cấp đúng từng tên tự động. Có thể dùng Micrometer, Spring observations hoặc instrumentation riêng tùy phiên bản và kiến trúc.

### 16.2. Đọc metric theo ngữ cảnh

- **ACK confirms cao, returns cũng cao:** broker đang xử lý publish nhưng route chưa đúng.
- **ACK confirms cao, queue ready tăng:** producer gửi được, consumer có thể chậm hoặc offline.
- **ACK confirms cao, business success thấp:** cần kiểm tra consumer DLQ, converter, nghiệp vụ hoặc ACK quá sớm.
- **Pending confirms tăng, latency cao:** có thể do broker/network/callback/backpressure.
- **UNKNOWN tăng sau deploy:** kiểm tra ConnectionFactory, callbacks, shutdown và deadline.
- **NACK tăng đồng thời broker disk alarm:** điều tra tình trạng broker/queue policy; không chỉ tăng retry rate.

### 16.3. Logging an toàn

Không log toàn bộ payload chứa dữ liệu cá nhân hoặc credentials. Một dòng log hữu ích:

~~~text
eventId=evt-1001
attemptId=7f31...
exchange=orders.events
routingKey=orders.created
publishStatus=UNROUTABLE
replyCode=312
retryable=false
~~~

**replyCode=312** chỉ là ví dụ mã **NO_ROUTE** thường gặp ở AMQP basic.return, không thay yêu cầu đọc mã thực tế từ returned message. Không tự suy diễn mọi reply code khác nhau là cùng một nguyên nhân.

### 16.4. Vòng đời và graceful shutdown

Khi tắt ứng dụng:

1. Ngừng nhận thêm event từ nguồn hoặc đưa event chưa publish vào outbox bền vững.
2. Dừng tạo thêm attempt mới.
3. Cho những confirms đang pending thêm một khoảng xử lý có giới hạn.
4. Ghi hoặc giữ trạng thái UNKNOWN cho attempt không có kết quả chắc chắn.
5. Đóng endpoint/connection theo lifecycle của Spring, không đóng ConnectionFactory dùng chung tùy tiện.
6. Khi khởi động lại, worker đọc outbox, đối soát và retry an toàn.

**Không nên xem ApplicationContext đóng thành công là bằng chứng mọi publisher confirm đã được nhận và outbox đã đồng bộ**. Cần kiểm thử shutdown giữa burst publish, mất mạng và callback đang in-flight.

### 16.5. Security

Producer cần quyền **write** phù hợp vào exchange đúng virtual host; user quản lý topology cần quyền **configure** tương ứng khi có khai báo exchange/queue/binding. Hãy cấp quyền tối thiểu, dùng TLS, nạp credential từ secret manager và hạn chế logging headers/payload nhạy cảm.

Một returned message có thể chứa cả body ban đầu. **Không dump toàn bộ returned body vào log production** nếu đó là dữ liệu người dùng hoặc giao dịch nhạy cảm.

## 17. Tình huống kiến trúc: đặt hàng và nhiều hệ thống nhận

Hệ thống OrderService cần publish OrderCreated cho **Warehouse** và **Analytics**. Các yêu cầu:

- Sau khi Order được commit, phải có cách phát lại sự kiện nếu RabbitMQ tạm thời không sẵn sàng.
- Một event được phát **một lần ở logic nghiệp vụ**, dù có thể retry nhiều lần ở mức transport.
- Warehouse và Analytics có **queue riêng**, để mỗi hệ thống đều nhận OrderCreated.
- Publisher biết sự kiện đã được broker chấp nhận và không bị return; nếu không rõ phải giữ trạng thái.
- Consumer phải tránh side effect trùng do redelivery/publish lại.

### 17.1. Thiết kế tham khảo

~~~mermaid
flowchart TD
    OS["OrderService"] --> DBTX["DB transaction"]
    DBTX --> O[("Orders")]
    DBTX --> OB[("OutboxEvent<br/>eventId ổn định")]
    OB --> W["Publisher worker"]
    W --> RT["RabbitTemplate<br/>CorrelationData"]
    RT --> EX["orders.events<br/>exchange"]
    EX --> WQ["warehouse.orders.q"]
    EX --> AQ["analytics.orders.q"]
    WQ --> WC["Warehouse consumer<br/>inbox / idempotency"]
    AQ --> AC["Analytics consumer<br/>inbox / idempotency"]
    RT -. "ACK/NACK/return/timeout" .-> TRACK["Publish tracker"]
    TRACK --> OB
~~~

Với direct exchange, cả hai queue có thể bind bằng cùng key **orders.created**; hoặc dùng topic exchange và những binding pattern theo nhu cầu. Producer không cần publish hai lần chỉ vì có hai nhóm nhận, trừ khi contract yêu cầu hai bản publish độc lập.

### 17.2. Những câu hỏi phải chốt trước triển khai

1. **Mốc thành công:** chỉ cần broker xác nhận publish và không return, hay Warehouse phải gửi business acknowledgment?
2. **Định danh:** eventId và attemptId được tạo ở đâu, duy trì qua restart như thế nào?
3. **Hợp đồng:** payload JSON/Avro, schemaVersion, contentType, routing key?
4. **Topology:** Exchange, queue, binding có được provision bởi platform không; ai được quyền sửa?
5. **Failure policy:** Khi UNROUTABLE hoặc NACK, retry hay tạm dừng và cảnh báo?
6. **UNKNOWN:** Khi mất confirm, thời hạn chờ và quy trình đối soát/đẩy lại?
7. **Consumer:** Làm sao tránh ghi trùng, kiểm soát ACK, retry và DLQ?
8. **Quan sát:** So sánh outbox confirmed với số event business processed ở từng consumer ra sao?

### 17.3. Phân biệt “đã phát” với “đã xử lý”

| Trạng thái OrderService biết | Có thể tuyên bố | Chưa nên tuyên bố |
| --- | --- | --- |
| Outbox NEW | Đã ghi ý định phát event trong DB | Broker đã nhận |
| Publisher ACK, no return observed | Đã đạt mốc publisher confirm theo cấu hình | Warehouse/Analytics đã xử lý xong |
| Publisher UNROUTABLE | Route không tới queue theo hợp đồng tại thời điểm publish | Consumer đã nhận hoặc có thể tự khắc phục |
| Publisher UNKNOWN | Chưa biết kết quả cuối của lần publish | Chắc chắn chưa từng gửi |
| Warehouse business ACK riêng | Warehouse xác nhận nghiệp vụ theo contract | Analytics chắc chắn đã xử lý |

Nếu HTTP API của OrderService trả **202 Accepted** sau khi ghi Order + Outbox trong transaction, điều đó có thể mang nghĩa **đã tiếp nhận để xử lý bất đồng bộ**, không nhất thiết nghĩa mọi downstream hoàn tất. Cần định nghĩa status cho caller một cách rõ ràng.

### 17.4. Liên hệ với SFTP/file/HTTP trong module

Một luồng khác nhận file CSV qua SFTP, chuẩn hóa dữ liệu rồi publish sự kiện AMQP:

~~~mermaid
flowchart LR
    S["SFTP CSV"] --> IA["SFTP inbound adapter<br/>poller"]
    IA --> V["Parse + validate"]
    V --> DB["Durable import/outbox"]
    DB --> AM["AMQP outbound adapter<br/>RabbitTemplate"]
    AM --> MQ["RabbitMQ"]
    MQ --> C["Consumer"]
~~~

Trong tình huống này:

- SFTP poller nhận file là **mốc tiếp nhận dữ liệu**.
- DB/outbox ghi nhận các event cần publish là **mốc bền vững nội bộ**.
- Publisher confirms/returns là **mốc giao nhận AMQP**.
- Consumer ACK và business commit là **mốc xử lý phía nhận**.

Không xóa file nguồn hoặc đánh dấu import thành công toàn tuyến chỉ vì MessageChannel.send() trả true, nếu hợp đồng yêu cầu publish bền vững hay downstream completion.

## 18. Các sai lầm phổ biến

**“RabbitTemplate.convertAndSend không ném lỗi nghĩa là broker đã ACK.”** Lời gọi gửi và confirm callback/future có thể khác thời điểm. Cần bật và theo dõi confirms.

**“Publisher ACK nghĩa là chắc chắn đã vào queue đúng.”** Một publish unroutable vẫn có thể được broker ACK. Cần mandatory/returns hoặc cơ chế điều phối topology tương ứng.

**“Unroutable chắc chắn nhận NACK.”** Publisher return và publisher confirm NACK là hai tín hiệu khác nhau; một message không route được có thể ACK ở cấp publish.

**“Không có consumer nghĩa là phải return.”** Message có thể route vào queue và chờ; không có consumer không làm binding vô hiệu.

**“Exchange không tồn tại cũng là returned message.”** Publish tới exchange thiếu thường gây lỗi protocol/channel, khác trường hợp exchange tồn tại nhưng không có route.

**“Chỉ cần publisher-returns=true.”** Cần mandatory được áp dụng và đường callback/tracking hoạt động đúng theo cấu hình.

**“Bật correlated confirms là đã có tracking bền vững.”** CorrelationData future là kết quả bất đồng bộ trong tiến trình; nếu process crash, trạng thái pending cần nguồn khôi phục riêng.

**“Một confirm callback tương ứng thứ tự gửi.”** Nhiều publish đồng thời có thể có confirm đến khác thứ tự; dùng attemptId/correlation.

**“CorrelationData ID là khóa chống trùng duy nhất ở consumer.”** Consumer cần eventId nghiệp vụ ổn định qua retry; attemptId của publisher có thể đổi.

**“Timeout nghĩa là broker chắc chắn không nhận.”** Khi mất kết nối gần confirm, kết quả có thể UNKNOWN; gửi lại phải idempotent.

**“Retry mọi lỗi là an toàn.”** Không retry nóng với binding sai, không đủ quyền hoặc schema không hợp lệ; cần sửa nguyên nhân.

**“Publisher return sẽ đưa bản tin vào DLQ.”** Return báo lỗi từ exchange tới publisher; DLX/DLQ thuộc cơ chế dead-letter phía queue trong tình huống khác.

**“Alternate exchange route được là consumer chính đã nhận.”** Bản tin ở alternate queue có thể chỉ là fallback để điều tra.

**“Outbox + confirms = exactly-once end-to-end.”** Producer có thể gửi lại và consumer có thể nhận trùng; idempotency vẫn bắt buộc.

**“Đánh dấu outbox SENT sau convertAndSend là đủ.”** Nếu mốc yêu cầu là broker-confirmed, cần theo dõi future/callback/return trước khi cập nhật.

**“Đưa toàn bộ body của returned message vào log là vô hại.”** Returned body có thể chứa dữ liệu nhạy cảm; chỉ log metadata an toàn và mã lỗi cần thiết.

**“Dùng ExecutorChannel vẫn biết được lỗi trong method send.”** Publish có thể chạy ở thread khác; lỗi bất đồng bộ cần đường xử lý riêng.

**“Queue durable bảo đảm consumer đã xử lý.”** Queue durability, publisher confirms và consumer business outcome là ba khía cạnh riêng.

**“Đã bật confirms ở một ConnectionFactory thì mọi RabbitTemplate đều có.”** Với nhiều factory/template, phải kiểm tra đúng bean được endpoint dùng.

## 19. Checklist triển khai thực tế

Trước khi đưa luồng AMQP publish vào production, hãy trả lời đủ các câu hỏi sau:

| Nhóm | Điều kiện cần xác minh |
| --- | --- |
| **Routing** | Exchange/routing key/binding ở đúng virtual host; queue đích tồn tại |
| **Confirms** | Correlated confirms thực sự bật trên ConnectionFactory mà RabbitTemplate dùng |
| **Returns** | publisher-returns và mandatory được áp dụng; có listener/tracking cho returned message |
| **Correlation** | EventId ổn định, attemptId phân biệt từng publish; callback ghép đúng trạng thái |
| **Conversion** | Schema, contentType, charset, allowed headers và DTO tương thích |
| **Timeout** | Có deadline cho pending confirms và trạng thái UNKNOWN được lưu bền |
| **Retry** | Retry hữu hạn, backoff/jitter, không tạo hot loop với lỗi cố định |
| **Outbox** | Intent publish được ghi trong transaction nghiệp vụ khi cần bảo đảm không mất event |
| **Idempotency** | Consumer có unique constraint/inbox hoặc biện pháp chống trùng tương đương |
| **Capacity** | Giới hạn số publish đang pending, queue capacity, callback workload |
| **Broker** | Queue type/persistence/cluster policy đáp ứng SLA, có quan sát broker alarms |
| **Consumer** | ACK/retry/DLQ được kiểm thử, business outcome quan sát riêng |
| **Shutdown** | Pending attempts được giải quyết hoặc giữ trạng thái để retry sau restart |
| **Security** | TLS, ACL tối thiểu, credentials không hardcode, logs không lộ payload |
| **Tests** | Unroutable, missing exchange, timeout, NACK, restart và load tests đã có |

### 19.1. Khi nào chọn publisher confirms/returns?

**Nên sử dụng** khi ứng dụng cần xác định kết quả publish ở broker và phân biệt lỗi không route được, đặc biệt với event quan trọng hoặc hệ thống có nhiều consumer/queue. **Không nhất thiết phải ép mọi best-effort notification** vào outbox phức tạp nếu yêu cầu nghiệp vụ chấp nhận mất message, nhưng phải ghi nhận rõ SLA đó.

Nếu yêu cầu là **nhận ngay kết quả xử lý nghiệp vụ**, confirms/returns không đủ: phải có gateway request–reply hoặc kiến trúc callback/event phản hồi. Nếu yêu cầu là **không bỏ sót event sau DB commit**, thêm outbox hoặc cơ chế bền vững tương đương; confirms/returns chỉ là một phần của toàn bộ phương án.

## 20. Câu hỏi tự kiểm tra

1. Publisher confirms trả lời câu hỏi nào về một lần publish? Nó khác consumer ACK ở đâu?
2. Vì sao RabbitTemplate.convertAndSend trả về không có exception chưa chứng minh broker đã confirm?
3. Exchange tồn tại nhưng không có binding khớp: broker có thể vừa gửi return vừa confirm ACK không?
4. Điều kiện nào thường cần để RabbitTemplate nhận publisher returns?
5. Exchange không tồn tại khác trường hợp exchange có thật nhưng không có route như thế nào?
6. Vì sao queue không có consumer không nhất thiết làm message bị return?
7. CorrelationData.getFuture() giúp giải quyết bài toán gì? Nó có thay được durable outbox không?
8. EventId và attemptId nên được thiết kế thế nào khi một event được retry ba lần?
9. Vì sao mất kết nối trước confirm tạo trạng thái UNKNOWN thay vì chắc chắn FAILED?
10. Khi nhận publisher ACK nhưng CorrelationData.getReturned() có dữ liệu, trạng thái publish nên được hiểu thế nào?
11. Khi bật alternate exchange, kết quả return và nơi message được giữ có thể thay đổi ra sao?
12. Publisher return khác dead-letter exchange ở thời điểm xử lý message như thế nào?
13. Tại sao callback publisher không nên thực hiện I/O chặn lâu nếu chưa có thiết kế tách worker?
14. Với DirectChannel và ExecutorChannel, khả năng caller quan sát exception đồng bộ khác nhau thế nào?
15. Vì sao một AMQP outbound adapter không trở thành gateway chỉ vì có confirm ACK?
16. Outbox giúp giải quyết khoảng trống nào giữa database transaction và RabbitMQ publish?
17. Tại sao outbox vẫn cần idempotent consumer khi publisher có correlated confirms?
18. Khi broker ACK nhưng consumer Warehouse offline, thông tin nào cần quan sát tiếp?
19. Những chỉ số nào giúp phân biệt routing lỗi, broker confirm chậm và consumer business processing chậm?
20. Nếu SFTP inbound nhận file thành công nhưng RabbitMQ publish bị UNKNOWN, có nên xóa file và coi toàn pipeline thành công không? Vì sao?

## Tổng kết

**Publisher confirms và returns** là hai công cụ khác nhau để quan sát việc gửi AMQP qua RabbitMQ. **Publisher confirm ACK/NACK** phản ánh kết quả broker xử lý một lần publish theo cơ chế confirms; **publisher return** báo message không được route tới queue phù hợp khi **mandatory/returns** có hiệu lực. Một message có thể **được confirm ACK nhưng vẫn bị returned**. Ngược lại, **consumer ACK và business reply** diễn ra ở ranh giới khác, không được thay bằng một xác nhận publish.

Trong Spring Integration, **AMQP outbound channel adapter** đưa Spring Message từ **MessageChannel** tới RabbitTemplate, nhưng ứng dụng muốn theo dõi độ tin cậy phải cấu hình đúng **ConnectionFactory, correlated confirms, mandatory, returns và CorrelationData**, đồng thời kiểm tra cách adapter chuyển kết quả về flow theo phiên bản hỗ trợ. Với event quan trọng, thiết kế cần **eventId ổn định, attemptId cho mỗi lần thử, trạng thái UNKNOWN, retry hữu hạn, outbox, idempotent consumer, kiểm thử routing và vận hành có metric**. Chỉ khi phân biệt rõ **đã gọi send**, **broker đã ACK**, **message đã route** và **nghiệp vụ đã hoàn tất** thì hệ thống tích hợp AMQP mới có khả năng phục hồi đáng tin cậy.
