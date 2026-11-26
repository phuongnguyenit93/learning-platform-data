# Retry phía publisher và khả năng tạo thông điệp trùng

## Mục tiêu bài học

Trong **Spring AMQP**, ứng dụng có thể publish sự kiện bằng **RabbitTemplate** đến **RabbitMQ exchange**, sau đó broker định tuyến đến queue qua **binding**; consumer nhận bằng **@RabbitListener**. Khi mạng chập chờn, broker quá tải hoặc connection bị đóng, publisher cần thử gửi lại (**retry**) để giảm nguy cơ mất sự kiện.

Tuy nhiên, việc gửi lại làm nảy sinh một vấn đề quan trọng: **publisher có thể không biết message trước đó đã được broker nhận hay chưa**. Nếu nó gửi lại, broker có thể nhận **hai message đại diện cho cùng một sự kiện nghiệp vụ**.

Sau bài thuộc chương **Gửi thông điệp**, bạn có thể:

1. Phân biệt **lỗi gửi đồng bộ**, **publisher confirm**, **publisher return** và **consumer acknowledgement**.
2. Giải thích tình huống mất confirm, vì sao retry có thể tạo message trùng dù ứng dụng xử lý lỗi hợp lý.
3. Biết phạm vi của **Spring Retry/RetryTemplate** trên RabbitTemplate và những gì nó **không** tự giải quyết.
4. Cấu hình **publisher-confirm-type: correlated**, **publisher-returns** và **mandatory**; theo dõi kết quả publish bằng **CorrelationData**.
5. Thiết kế **retry có giới hạn, exponential backoff, jitter, outbox** và **consumer idempotency**.
6. Phân biệt **at-least-once delivery** với **exactly-once business effect** và biết kiểm tra hệ thống qua fault injection, metric và log.

## 1. Vì sao publisher cần retry?

Ví dụ **Order Service** ghi đơn hàng thành công rồi publish event **OrderCreated** để **Notification Service**, **Analytics Service** và **Audit Service** xử lý bất đồng bộ.

~~~mermaid
flowchart LR
    O["Order Service<br/>Producer / RabbitTemplate"] -->|"publish OrderCreated"| X{"orders.events<br/>topic exchange"}
    X -->|"binding order.created"| Q[("notification.orders<br/>durable queue")]
    Q --> L["Notification Service<br/>@RabbitListener"]
    L --> E["Gửi email xác nhận"]
~~~

Publisher có thể thất bại vì:

- Broker chưa sẵn sàng, connection bị từ chối hoặc mất mạng.
- Channel bị đóng trong quá trình publish.
- RabbitMQ gửi **publisher nack** vì không thể tiếp nhận message.
- Message publish đến exchange nhưng **không có queue phù hợp** để định tuyến.
- Ứng dụng không nhận được publisher confirm trong khoảng thời gian chờ đã đặt.

**Không phải mọi lỗi trên đều nên retry giống nhau.** Lỗi kết nối tạm thời có thể phục hồi; sai tên exchange, thiếu quyền, sai vhost hoặc routing key không khớp thường cần **sửa cấu hình/topology**, nếu thử lại liên tục sẽ chỉ tạo thêm tải.

**Retry phía publisher** là việc **gửi lại một lần publish**. Nó **khác** retry của consumer khi **@RabbitListener** nhận message nhưng xử lý DB/API thất bại. Hai vòng retry có thể cùng tồn tại trong một hệ thống, dẫn đến khả năng một sự kiện được xử lý nhiều lần.

## 2. Ba mốc thành công trong đường truyền

Một lần gọi **RabbitTemplate.convertAndSend(...)** kết thúc **không có nghĩa** consumer đã xử lý event và cũng không nhất thiết chứng minh broker lưu bền message.

| Mốc | Thành phần thông báo | Ý nghĩa | Điều chưa chứng minh |
| --- | --- | --- | --- |
| **Lệnh send kết thúc** | RabbitTemplate/client | Phần thao tác gửi ở phía client hoàn thành mà không ném lỗi đồng bộ | Message chắc chắn được broker chấp nhận hoặc route |
| **Publisher confirm ACK** | RabbitMQ broker → publisher | Broker đã chấp nhận publish theo cơ chế publisher confirms | Message chắc chắn có queue nhận nếu không kiểm tra return; consumer đã xử lý xong |
| **Publisher return** | RabbitMQ broker → publisher | Message có mandatory nhưng không được route đến queue phù hợp | Đây là lỗi của consumer |
| **Consumer ACK** | Consumer → broker | Consumer/container xác nhận lần delivery trên queue | Giao dịch bên ngoài chắc chắn chưa từng thực hiện trùng |
| **Kết quả nghiệp vụ** | Database/API bên ngoài | Hóa đơn/email/bút toán đã được xử lý theo điều kiện nghiệp vụ | Bản thân ACK và confirm không thay thế biện pháp chống trùng |

Đây là hai cơ chế xác nhận độc lập:

~~~text
Producer --basic.publish--> Broker --message delivery--> Consumer
Producer <--publisher ACK--- Broker <--consumer ACK-------- Consumer
            (publish)                           (delivery)
~~~

**Publisher confirm sequence number** thuộc phạm vi channel publish và dùng để tương quan confirm. **Consumer delivery tag** thuộc channel consume và dùng ACK/NACK cho một delivery. Không dùng hai số đó làm định danh sự kiện nghiệp vụ bền vững.

### Bảng các tình trạng dễ nhầm

| Quan sát của publisher | Diễn giải hợp lý | Hành động |
| --- | --- | --- |
| Confirm **ACK**, không có return | Broker xác nhận publish và không thấy trường hợp unroutable được trả về khi mandatory/returns hoạt động | Ghi nhận **published**, chưa coi nghiệp vụ đã hoàn tất |
| Confirm **ACK** nhưng có **return** | Broker đã xử lý publish nhưng **không route** tới queue | Sửa topology/routing, không đánh dấu giao thành công |
| Confirm **NACK** | Broker/framework báo lần publish không được xác nhận thành công | Ghi nhận thất bại/không chắc chắn theo ngữ cảnh; retry có kiểm soát |
| **Timeout chờ confirm** | Chưa nhận được kết quả trước deadline của ứng dụng | **UNKNOWN**: có thể broker đã nhận và chỉ mất confirm |
| **Connection/channel đóng** lúc gửi | Có lỗi kết nối/truyền giao thức | Không mặc nhiên biết broker đã hay chưa nhận message |
| **Return NO_ROUTE** | Không có destination queue khớp binding khi mandatory bật | Kiểm tra exchange, binding, routing key, provisioning |
| Publish vào **exchange không tồn tại** | Broker có thể đóng channel với lỗi giao thức; không phải NO_ROUTE return thông thường | Sửa topology, kiểm tra shutdown/confirm error |

**Quan trọng:** broker có thể ACK **message không route được** sau khi xác định không có queue đích. Vì thế chỉ kiểm tra **confirm.isAck()** mà bỏ qua **publisher return** là chưa đủ.

## 3. Lỗi không chắc chắn: nguyên nhân gốc tạo message trùng

Giả sử ứng dụng publish **OrderCreated(eventId=e-101)**. Broker đã nhận và lưu message nhưng mạng đứt ngay trước khi confirm quay về producer:

~~~mermaid
sequenceDiagram
    participant P as Order Service
    participant B as RabbitMQ
    participant Q as notification.orders
    P->>B: publish eventId=e-101 (attempt 1)
    B->>Q: Enqueue e-101
    B--xP: Publisher confirm ACK bị mất
    Note over P: Timeout, kết quả UNKNOWN
    P->>B: publish eventId=e-101 (attempt 2)
    B->>Q: Enqueue e-101 lần nữa
    B-->>P: Publisher confirm ACK
    Note over Q: Có thể chứa hai message<br/>cùng eventId=e-101
~~~

**Từ góc nhìn producer**, chỉ thấy lần 1 không có confirm và lần 2 được ACK; từ góc nhìn broker, **cả hai lần publish có thể đều thành công**. RabbitMQ với queue AMQP 0.9.1 thông thường không tự hiểu rằng hai message cùng eventId phải bị loại trùng.

Trường hợp này khác **consumer redelivery**:

| Nguồn lặp | Điều xảy ra | Cờ **redelivered** có đáng tin để phát hiện trùng không? |
| --- | --- | --- |
| **Publisher retry** | Hai lần **basic.publish** tạo hai bản message cho cùng event | **Không**: bản thứ hai có thể là delivery đầu tiên, redelivered=false |
| **Consumer crash trước ACK** | Một message trong queue được giao lại | Có thể thấy redelivered=true, nhưng không đủ cho mọi trường hợp |
| **Outbox dispatcher restart** | Bản ghi outbox đã publish nhưng chưa kịp đánh dấu hoàn thành được gửi lại | **Không**: đây là publish mới ở phía broker |
| **Nhiều queue cùng bind exchange** | Mỗi queue cố ý nhận bản sao event | Đây là fan-out có chủ đích, không mặc nhiên là duplicate trong một nhóm nghiệp vụ |

**Kết luận vận hành:** để đạt at-least-once, producer thường phải gửi lại các message **chưa có xác nhận rõ ràng**. Điều này tất yếu tạo **khả năng lặp**; consumer phải xử lý theo hướng **idempotent**.

## 4. RetryTemplate trên RabbitTemplate giải quyết phần nào?

Spring AMQP hỗ trợ **RetryTemplate** từ Spring Retry để thử lại các **thao tác đồng bộ** của RabbitTemplate khi phát sinh exception, đặc biệt là vấn đề kết nối đến broker.

Ví dụ luồng:

~~~text
RabbitTemplate.convertAndSend(...)
    ├── Lỗi kết nối/AmqpException đồng bộ
    │     └── RetryTemplate chờ backoff rồi gọi gửi lại
    └── Lệnh gửi không ném exception đồng bộ
          └── Kết thúc lời gọi gửi
                └── Publisher confirm/return đến BẤT ĐỒNG BỘ sau đó
~~~

**RetryTemplate gắn vào RabbitTemplate không tự biến publisher confirms thành một lời gọi đồng bộ.** NACK hoặc timeout **sau khi convertAndSend trả về** không tự kích hoạt lại cùng RetryTemplate. Nếu muốn retry theo kết quả publisher confirm, ứng dụng phải xây **quy trình theo dõi kết quả bất đồng bộ** riêng.

Ngoài ra, khi lỗi xảy ra trong thao tác gửi đồng bộ, trạng thái broker **vẫn có thể không chắc chắn**; retry sau exception cũng có thể tạo message trùng.

### 4.1. Cấu hình Spring Boot cho retry đơn giản

Ví dụ với **Spring Boot 3.x**, **spring-boot-starter-amqp** và template do Boot auto-configure:

~~~yaml
spring:
  rabbitmq:
    host: localhost
    port: 5672
    template:
      retry:
        enabled: true
        max-attempts: 3
        initial-interval: 500ms
        multiplier: 2.0
        max-interval: 3s
~~~

Cấu hình này minh họa tối đa **3 lần thử tổng cộng** (lần đầu và các lần thử lại), với khoảng chờ tăng dần. Đây là **template retry cho lỗi đồng bộ**, không phải chính sách cho **confirm timeout**, **NO_ROUTE** hoặc **consumer exception**.

**Không bật đồng thời nhiều tầng retry thiếu kiểm soát.** Nếu Spring Boot đã bật template retry và bên ngoài lại có một scheduler retry ba lần, tổng số publish có thể tăng đáng kể. Khi thiết kế reliable outbox publisher, nên chọn rõ tầng nào retry và ai sở hữu số lượt thử.

### 4.2. Java config nếu cần RetryTemplate tùy chỉnh

~~~java
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.retry.backoff.ExponentialBackOffPolicy;
import org.springframework.retry.policy.SimpleRetryPolicy;
import org.springframework.retry.support.RetryTemplate;

RetryTemplate retryTemplate = new RetryTemplate();
SimpleRetryPolicy retryPolicy = new SimpleRetryPolicy(3);
ExponentialBackOffPolicy backOff = new ExponentialBackOffPolicy();
backOff.setInitialInterval(500);
backOff.setMultiplier(2.0);
backOff.setMaxInterval(3000);
retryTemplate.setRetryPolicy(retryPolicy);
retryTemplate.setBackOffPolicy(backOff);

rabbitTemplate.setRetryTemplate(retryTemplate);
~~~

Đây là đoạn minh họa **cấu hình cho bean RabbitTemplate đang có**, không phải một ứng dụng Java độc lập. **SimpleRetryPolicy mặc định có thể retry nhiều loại exception**; trong hệ thống thực tế, hãy hạn chế chính sách vào **lỗi tạm thời có thể phục hồi** và tránh retry lỗi schema, serialization, authorization hoặc topology sai. Dùng **RecoveryCallback** hoặc cơ chế ghi trạng thái bên ngoài để biết việc thử đồng bộ đã hết lượt.

**RetryTemplate không phải transactional outbox**: nếu tiến trình chết, những lần retry chờ trong bộ nhớ không tự được khôi phục. Một sự kiện cần phát chắc chắn phải được lưu vào storage bền vững trước khi giao cho quy trình publish.

## 5. Publisher confirms và returns trong Spring AMQP

Khi cần biết publish có thành công, bật **correlated publisher confirms**. Khi cần biết message có queue đích, bật **publisher returns** và **mandatory**. Hai tín hiệu bổ sung cho nhau.

### 5.1. Cấu hình Spring Boot

~~~yaml
spring:
  rabbitmq:
    host: localhost
    port: 5672
    username: guest
    password: guest
    publisher-confirm-type: correlated
    publisher-returns: true
    template:
      mandatory: true
      retry:
        enabled: false   # Ví dụ này sẽ quản lý retry bằng outbox + confirm.
~~~

Ví dụ chỉ dùng **guest/guest** trên broker local; production phải dùng tài khoản riêng, cấu hình secret và TLS nếu cần. Các thuộc tính Boot có thể khác khi dùng nhánh Spring Boot khác; cần đọc đúng tài liệu phiên bản.

**publisher-confirm-type: correlated** cho phép gắn một **CorrelationData** vào lần publish. **publisher-returns** và **mandatory** giúp trả về message không được route tới queue phù hợp. Nếu quên mandatory, một message unroutable có thể bị broker bỏ mà producer chỉ thấy **ACK**.

### 5.2. Khai báo exchange, queue và binding minh họa

~~~java
import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.amqp.core.TopicExchange;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrdersPublishingTopology {

    @Bean
    TopicExchange ordersExchange() {
        return new TopicExchange("orders.events", true, false);
    }

    @Bean
    Queue notificationOrdersQueue() {
        return QueueBuilder.durable("notification.orders").build();
    }

    @Bean
    Binding notificationOrdersBinding(Queue notificationOrdersQueue,
                                      TopicExchange ordersExchange) {
        return BindingBuilder.bind(notificationOrdersQueue)
                .to(ordersExchange)
                .with("order.created");
    }
}
~~~

RabbitAdmin có thể tự khai báo các bean khi connection được mở và user có quyền. Lưu ý **publisher confirm không tự tạo queue**; lỗi binding vẫn có thể dẫn đến return. Muốn một sự kiện fan-out tới nhiều nghiệp vụ, khai báo thêm các queue/binding độc lập.

### 5.3. Per-attempt CorrelationData và eventId ổn định

Giả sử ta đã tạo event một lần, có ID **evt-101**, và cần thử publish tối đa nhiều lần. Phải phân biệt:

| Định danh | Phạm vi | Có giữ qua retry? |
| --- | --- | --- |
| **eventId** | Một **sự kiện nghiệp vụ** | **Có, luôn giữ nguyên** |
| **MessageProperties.messageId** | Metadata message AMQP | Nên đặt bằng **eventId** (hoặc ID ổn định khác) |
| **CorrelationData.id** | Một **lần publish** cụ thể | Nên **khác nhau giữa các attempt** để theo dõi confirm |
| **attemptNo** | Số lần thử publish | Tăng khi lập attempt mới; không phải identity của event |
| **consumer deliveryTag** | Một lần giao message trên channel consume | Thay đổi; không dùng làm eventId |

**Chọn hai ID với mục đích riêng:** eventId dùng deduplication trên consumer; CorrelationData.id giúp publisher tương quan ACK/NACK cho từng lần gửi. Hai message khác lần publish nhưng cùng eventId **vẫn là một sự kiện nghiệp vụ**.

## 6. Ví dụ Java: publish có confirm và kiểm tra return

Ví dụ sử dụng **Spring AMQP 3.x** với **Spring Boot 3.x**, phù hợp cấu hình ở mục 5. Code minh họa logic phân loại kết quả; các thao tác cập nhật trạng thái retry/outbox sẽ được triển khai trong phần sau.

### 6.1. Dữ liệu event và hàm publish

~~~java
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.nio.charset.StandardCharsets;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.core.MessageDeliveryMode;
import org.springframework.amqp.core.MessageProperties;
import org.springframework.amqp.rabbit.connection.CorrelationData;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.stereotype.Service;

record OrderCreated(String eventId, String orderId, long totalAmount) {}

@Service
public class ConfirmedOrderPublisher {
    private static final Logger log =
            LoggerFactory.getLogger(ConfirmedOrderPublisher.class);

    private final RabbitTemplate template;
    private final ObjectMapper objectMapper;

    public ConfirmedOrderPublisher(RabbitTemplate template,
                                   ObjectMapper objectMapper) {
        this.template = template;
        this.objectMapper = objectMapper;
    }

    public void publish(OrderCreated event, int attemptNo)
            throws JsonProcessingException {

        // eventId đã được tạo và lưu trước lần publish đầu tiên.
        // Nếu retry, nhận lại chính event này, không sinh eventId mới.
        String json = objectMapper.writeValueAsString(event);
        MessageProperties properties = new MessageProperties();
        properties.setContentType(MessageProperties.CONTENT_TYPE_JSON);
        properties.setContentEncoding(StandardCharsets.UTF_8.name());
        properties.setDeliveryMode(MessageDeliveryMode.PERSISTENT);
        properties.setMessageId(event.eventId());
        properties.setHeader("eventType", "order.created");
        properties.setHeader("schemaVersion", 1);

        Message message = new Message(
                json.getBytes(StandardCharsets.UTF_8), properties);

        // Một correlation id KHÁC nhau cho mỗi lần gửi.
        String attemptId = event.eventId() + ":" + attemptNo;
        CorrelationData correlation = new CorrelationData(attemptId);

        try {
            template.send("orders.events", "order.created",
                          message, correlation);
        } catch (RuntimeException sendError) {
            log.warn("Publish failed synchronously eventId={} attempt={}",
                    event.eventId(), attemptNo, sendError);
            // Ghi lại kết quả bất định và đưa vào lịch retry bền vững.
            // Không mặc nhiên cho rằng broker chưa nhận message.
            throw sendError;
        }

        correlation.getFuture().whenComplete((confirm, error) -> {
            if (error != null) {
                log.warn("Confirm future failed eventId={} attempt={}",
                        event.eventId(), attemptNo, error);
                // UNKNOWN -> cập nhật outbox và lập lịch retry có kiểm soát.
                return;
            }

            if (confirm == null || !confirm.isAck()) {
                log.warn("Publish not confirmed eventId={} attempt={} reason={}",
                        event.eventId(), attemptNo,
                        confirm == null ? "no confirm" : confirm.getReason());
                // NACK/UNKNOWN -> áp dụng chính sách xử lý thích hợp.
                return;
            }

            if (correlation.getReturned() != null) {
                log.error("Unroutable eventId={} attempt={} reply={}",
                        event.eventId(), attemptNo,
                        correlation.getReturned().getReplyText());
                // ROUTING_ERROR -> kiểm tra binding/topology; không mark sent.
                return;
            }

            log.info("Broker confirmed eventId={} attempt={}",
                    event.eventId(), attemptNo);
            // CONFIRMED_ROUTED -> đánh dấu outbox theo eventId + attempt.
        });
    }
}
~~~

**Giải thích đoạn mã:**

1. **MessageProperties.messageId** giữ cùng eventId qua mọi attempt; body JSON cũng giữ eventId.
2. Mỗi attempt có một **CorrelationData** riêng; **getFuture()** là **CompletableFuture** chứa kết quả confirm.
3. **confirm.isAck()** chỉ là xác nhận broker tiếp nhận publish, không phải xác nhận consumer xử lý thành công.
4. **correlation.getReturned()** cho biết message bị return khi **mandatory** và **publisher-returns** đã bật. Spring AMQP bảo đảm dữ liệu return tương quan được điền trước khi future hoàn tất với ACK trong tình huống hỗ trợ thông thường.
5. Nếu có lỗi đồng bộ, lỗi future hoặc hết thời hạn chờ, không thể tự động suy ra message đã mất; cần lưu **UNKNOWN** và xử lý retry.
6. Nhánh callback ở đây chỉ **log + mô tả hành động**, chưa triển khai storage hay lịch retry; không nên xem ví dụ riêng lẻ này là một outbox publisher production hoàn chỉnh.

**Đừng gọi Thread.sleep hoặc retry ngay trong callback confirm.** Hãy cập nhật trạng thái và giao lịch gửi lại cho worker/scheduler có backoff, deadline và giới hạn số attempt. Nếu callback bị xử lý lâu hoặc app sập, chỉ dựa vào callback trong bộ nhớ không đủ để giữ trách nhiệm publish.

### 6.2. Timeout của tương lai kết quả không phải bằng chứng mất message

Khi buộc phải chờ confirm đồng bộ (thường phù hợp ở demo hoặc luồng lưu lượng thấp):

~~~java
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

try {
    var confirm = correlation.getFuture().get(5, TimeUnit.SECONDS);
    if (confirm.isAck() && correlation.getReturned() == null) {
        // Đã có confirm và không thấy return theo cấu hình.
    }
} catch (TimeoutException ex) {
    // UNKNOWN: không suy ra broker chưa nhận message.
    // Ghi trạng thái và để retry scheduler xử lý.
}
~~~

Ví dụ chỉ minh họa thao tác trên **correlation** đã được tạo ở mục 6.1. **Timeout 5 giây là deadline của ứng dụng**, không phải cam kết RabbitMQ chắc chắn trả confirm trong 5 giây. Persistent message có thể được xác nhận sau khoảng trễ do đĩa, replication hoặc tải broker. Với throughput cao, không nên block một thread cho mỗi message; ưu tiên xử lý callback/future bất đồng bộ và giới hạn số message đang in-flight.

### 6.3. Callback dùng chung thay cho future của từng message

Spring cũng cho phép cấu hình **RabbitTemplate.ConfirmCallback** và **ReturnsCallback**:

~~~java
template.setConfirmCallback((correlation, ack, cause) -> {
    String id = correlation == null ? "unknown" : correlation.getId();
    log.info("Publish confirm attemptId={} ack={} cause={}", id, ack, cause);
});

template.setReturnsCallback(returned ->
        log.warn("Returned message exchange={} key={} reason={}",
                returned.getExchange(),
                returned.getRoutingKey(),
                returned.getReplyText()));
~~~

Chỉ **một** callback của mỗi loại được đăng ký trên mỗi RabbitTemplate, nên không để từng request tự gọi các setter này. Ví dụ ở mục 6.1 sử dụng **CorrelationData.getFuture()** thay thế cho callback xác nhận per-message; có thể dùng callback chung cho telemetry nhưng phải tránh cập nhật trạng thái nghiệp vụ hai lần.

## 7. Thiết kế retry đúng: phân loại lỗi trước khi gửi lại

Retry nên có ba quyết định: **có đáng retry hay không**, **thử lại khi nào** và **dừng ở đâu**.

| Nhóm lỗi | Ví dụ | Quyết định đề xuất |
| --- | --- | --- |
| **Transient** | Broker restart, mất mạng, connection refused, resource alarm tạm thời | Retry có backoff + jitter, giới hạn attempt |
| **UNKNOWN** | Mất confirm/timeout, channel chết sau khi ghi publish | Retry vì có nguy cơ mất sự kiện, **chấp nhận khả năng trùng** |
| **Routing/configuration** | NO_ROUTE, exchange sai, binding chưa có | Cảnh báo/sửa topology, chỉ retry sau khi điều kiện khắc phục |
| **Permanent application error** | JSON serialization lỗi, payload không hợp lệ, credentials bị từ chối | Không retry vô hạn; sửa dữ liệu/code/quyền |
| **Quá hạn nghiệp vụ** | Event không còn giá trị sau deadline | Đánh dấu cần xử lý thủ công hoặc hủy theo policy nghiệp vụ rõ ràng |
| **Quá số lần thử** | Retry vẫn không có kết quả rõ | Giữ trạng thái lỗi bền vững, cảnh báo và hỗ trợ replay/operator |

### 7.1. Exponential backoff + jitter

Một chính sách minh họa:

~~~text
Attempt 1: gửi ngay
Attempt 2: sau ~0,5 giây
Attempt 3: sau ~1 giây
Attempt 4: sau ~2 giây
Attempt 5: sau ~4 giây
... giới hạn mức chờ ở 30 giây, thêm jitter ±20%
Sau N lượt: đánh dấu cần xử lý vận hành
~~~

**Backoff** giảm tải lên broker khi đang phục hồi. **Jitter** làm nhiều instance không đồng loạt publish lại cùng lúc sau một sự cố chung. Các mốc trên chỉ là ví dụ, không phải thông số mặc định của Spring AMQP hoặc RabbitMQ.

Không nên retry mọi exception theo cùng chính sách: nếu exchange chưa tồn tại, thêm ba lần publish ngay lập tức không giúp việc khai báo trở nên đúng. Cũng không nên đặt deadline quá ngắn khiến consumer nhận nhiều bản trùng khi broker chỉ xác nhận chậm.

### 7.2. Một event, nhiều attempt

~~~text
eventId = evt-101  (KHÔNG ĐỔI)
  ├── attemptNo=1, attemptId=evt-101:1, result=UNKNOWN
  ├── attemptNo=2, attemptId=evt-101:2, result=NACK/UNKNOWN
  └── attemptNo=3, attemptId=evt-101:3, result=ACK_NO_RETURN
~~~

**Số lượt retry là metadata của dispatcher**, không phải một phần xác định danh tính sự kiện. Trong một số bài toán, body event nên **giữ nguyên byte-for-byte** qua mọi attempt để debug và kiểm tra chữ ký/hợp đồng dễ dàng. Nếu cần ghi attemptNo, ưu tiên metadata của publisher thay vì liên tục sửa nội dung nghiệp vụ.

### 7.3. Tránh retry chồng lên nhau

Không nên để ba tầng cùng sở hữu quyền gửi lại một event:

~~~text
HTTP request retry
  └── Service method @Retryable
        └── RabbitTemplate RetryTemplate
              └── Outbox scheduler retry
~~~

Nếu mỗi tầng thử ba lần, một yêu cầu có thể gây nhiều lần publish hơn dự kiến. Hãy xác định **một tầng chịu trách nhiệm trạng thái event**, còn các tầng còn lại có giới hạn rõ ràng hoặc bị tắt.

Với sự kiện cần bảo đảm, **DB outbox + dispatcher** thường là nơi phù hợp để sở hữu retry qua restart. HTTP request có thể trả về orderId/trạng thái **ACCEPTED/PENDING** khi giao dịch tạo đơn/outbox đã commit; không cần chờ các consumer xử lý xong.

## 8. Transactional outbox: không mất trách nhiệm publish khi process sập

Không dùng outbox, có hai lời gọi tách biệt:

~~~text
1. INSERT order → COMMIT DB
2. RabbitTemplate.convertAndSend(OrderCreated)
~~~

Nếu ứng dụng chết **giữa bước 1 và bước 2**, đơn hàng đã tồn tại nhưng không có event. Nếu đảo thứ tự, publish thành công rồi DB rollback, consumer lại có thể nhận một event cho đơn hàng chưa tồn tại.

**Transactional outbox** lưu cả thay đổi nghiệp vụ và bản ghi event chờ publish trong **cùng một database transaction**:

~~~mermaid
flowchart LR
    API["POST /orders"] --> TX["DB transaction<br/>INSERT orders + INSERT outbox"]
    TX --> DB[("Database")]
    DB --> W["Outbox dispatcher<br/>claim + publish + wait confirm"]
    W --> B{"RabbitMQ"}
    B --> Q[("notification.orders")]
    Q --> C["Idempotent consumer"]
    B -.->|"ACK/RETURN/NACK"| W
    W -.->|"status + retryAt"| DB
~~~

### 8.1. Bảng outbox đề xuất

Ví dụ PostgreSQL:

~~~sql
CREATE TABLE outbox_events (
    event_id           UUID PRIMARY KEY,
    event_type         VARCHAR(120) NOT NULL,
    routing_key        VARCHAR(150) NOT NULL,
    payload_json       JSONB NOT NULL,
    status             VARCHAR(30) NOT NULL DEFAULT 'PENDING',
    attempt_count      INTEGER NOT NULL DEFAULT 0,
    next_attempt_at    TIMESTAMPTZ,
    locked_until       TIMESTAMPTZ,
    last_error         TEXT,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    published_at       TIMESTAMPTZ
);
~~~

**event_id** phải được sinh **một lần** trong transaction tạo nghiệp vụ. **payload_json** là snapshot sự kiện cần publish; nếu producer đọc lại dữ liệu hiện tại và dựng payload khác sau mỗi retry, các lần publish của cùng eventId có thể không còn cùng ý nghĩa.

### 8.2. Một giao dịch cho order và outbox

~~~java
@Transactional
public UUID createOrder(CreateOrderRequest request) {
    Order order = orderRepository.save(Order.create(request));
    UUID eventId = UUID.randomUUID();

    OrderCreated payload = new OrderCreated(
            eventId.toString(), order.getId().toString(), order.getTotal());

    outboxRepository.save(OutboxEvent.pending(
            eventId, "order.created", "order.created", payload));

    return order.getId();
}
~~~

Đoạn mã là **pseudocode định hướng nghiệp vụ**: **Order**, **CreateOrderRequest**, **outboxRepository** và **OutboxEvent.pending** cần do ứng dụng triển khai. Điều cần kiểm chứng là **hai thao tác lưu dùng cùng DB transaction**. Nếu outbox ở database khác, transaction trên không còn bảo đảm nguyên tử nếu không có thiết kế bổ sung.

### 8.3. Dispatcher cần ghi trạng thái và xử lý cạnh tranh

Một worker định kỳ thực hiện:

1. Chọn những dòng **PENDING/RETRY_DUE** đã đến hạn, khóa/claim để tránh nhiều instance cùng xử lý một dòng (ví dụ **FOR UPDATE SKIP LOCKED** hoặc lease có timeout).
2. Tạo attempt mới, giữ nguyên **eventId** và payload đã lưu; ghi **attemptNo/attemptId**.
3. Publish bằng RabbitTemplate kèm **CorrelationData**; đợi kết quả bất đồng bộ, không chiếm DB transaction trong lúc chờ broker.
4. Nếu **ACK và không có return**, cập nhật **PUBLISHED** cho đúng eventId/attempt, kèm thời điểm.
5. Nếu **NACK, lỗi tạm hoặc UNKNOWN**, ghi lý do và **next_attempt_at**. Nếu **NO_ROUTE**, chuyển trạng thái **ROUTING_ERROR**/cảnh báo phù hợp.
6. Nếu hết giới hạn, chuyển sang **NEEDS_ATTENTION** thay vì xóa event; cho phép operator kiểm tra và phát lại có kiểm soát.

**Không giữ transaction khóa hàng DB mở suốt lúc chờ confirm**: việc chờ broker có thể dài, gây lock contention. Dùng cơ chế claim/lease ngắn để chiếm việc, rồi cập nhật kết quả bằng điều kiện **eventId + attemptId + trạng thái hiện tại**.

Ví dụ trường hợp dispatcher crash:

~~~text
T0  Outbox evt-101: PENDING
T1  Worker A claim evt-101, gửi attempt 1
T2  Broker đã lưu event
T3  Worker A crash trước khi cập nhật PUBLISHED
T4  Lease hết hạn; Worker B claim và gửi attempt 2 (cùng eventId)
T5  Broker có thể chứa 2 bản sao evt-101
~~~

**Outbox bảo vệ khỏi mất sự kiện giữa DB và broker, nhưng bản thân nó không tạo exactly-once publishing.** Cần consumer idempotency để xử lý event trùng.

### 8.4. Race giữa confirm muộn và retry

Một confirm ACK của attempt 1 có thể đến **sau khi** dispatcher đã cho attempt 2 đi. Nếu callback 1 ghi đè trạng thái mà không kiểm tra attempt đang quản lý, outbox sẽ có lịch sử khó hiểu hoặc retry bị thao tác sai.

Thiết kế nên có **attemptId**, **version** hoặc **fencing token**; state update sử dụng điều kiện so khớp attempt, và trạng thái **PUBLISHED** đã xác nhận cần được xem là kết quả cuối cho event (trừ khi có chính sách phát lại được operator chủ động chọn).

**Nếu một attempt đã được ACK và route thành công**, các retry đang chờ chưa chạy nên được hủy. Nhưng việc hủy retry tương lai **không xóa được bản sao đã publish** trong một attempt đang chạy khác.

## 9. Consumer idempotency: giới hạn tác động nghiệp vụ về một lần

Giả sử Notification Service nhận hai bản **OrderCreated(eventId=evt-101)**. Nếu consumer gửi hai email, khách hàng sẽ nhận thông báo trùng. Để giới hạn tác động, consumer dùng **eventId cố định** và ghi trạng thái đã xử lý.

### 9.1. Ví dụ transaction trong PostgreSQL

~~~sql
CREATE TABLE processed_events (
    consumer_name VARCHAR(100) NOT NULL,
    event_id      UUID NOT NULL,
    processed_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Trong cùng transaction với việc thay đổi dữ liệu nghiệp vụ:

~~~java
@Transactional
public void handle(OrderCreated event) {
    int inserted = jdbcTemplate.update(
        """
        INSERT INTO processed_events (consumer_name, event_id)
        VALUES (?, ?)
        ON CONFLICT DO NOTHING
        """,
        "notification-service",
        UUID.fromString(event.eventId()));

    if (inserted == 0) {
        return; // Event này đã được consumer này xử lý trước đó.
    }

    notificationRepository.createPendingNotification(
            event.eventId(), event.orderId());
}
~~~

Đây là **đoạn code minh họa**: **notificationRepository** do ứng dụng định nghĩa. Chèn processed_events và tạo bản ghi thông báo **phải cùng transaction**, nếu không một sự cố ở giữa có thể khiến event bị đánh dấu đã xử lý nhưng công việc lại chưa hoàn tất.

**Với tác động ngoài DB**, ví dụ gọi nhà cung cấp email hoặc thanh toán, transaction DB không tự bảo đảm API bên ngoài chỉ chạy một lần. Cách an toàn hơn là tạo **notification_outbox**/job có khóa unique theo eventId, rồi dùng idempotency key do nhà cung cấp hỗ trợ hoặc cơ chế trạng thái/reconciliation riêng.

### 9.2. Vì sao redelivered không giải quyết duplicate do publisher?

Một bản sao xuất hiện do **publisher retry** là **một publish mới**. Khi RabbitMQ giao bản đó lần đầu, **redelivered=false** vẫn hoàn toàn có thể xảy ra. Vì thế consumer không thể dùng **MessageProperties.isRedelivered()** để quyết định bỏ qua duplicate.

Tương tự, **CorrelationData.id** ở producer và **deliveryTag** ở consumer không phải khóa nghiệp vụ. Chỉ ID ổn định như **eventId** kết hợp với **unique constraint** hoặc biện pháp idempotency tương đương mới giúp hạn chế tác động trùng.

### 9.3. Idempotency theo từng consumer group

Nếu Analytics, Audit và Notification mỗi bên có queue riêng, chúng **đều phải xử lý event e-101**. Vì vậy bảng **processed_events** nên có khóa kết hợp **consumer_name + event_id**, hoặc mỗi service có bảng idempotency riêng.

Không đặt ràng buộc unique **event_id toàn hệ thống** dùng chung giữa các service nếu điều đó khiến Analytics xử lý trước rồi vô tình ngăn Notification xử lý sự kiện tương tự.

## 10. “Exactly once” có thể hiểu sai như thế nào?

**RabbitMQ AMQP queue + publisher confirms + consumer ACK** giúp xây đường truyền đáng tin cậy, nhưng không tự tạo giao dịch nguyên tử xuyên **database → RabbitMQ → email/payment API**.

| Mục tiêu | Điều hệ thống có thể làm | Giới hạn |
| --- | --- | --- |
| **At-most-once** | Chỉ thử gửi một lần, không retry khi không chắc chắn | Có thể mất event |
| **At-least-once** | Lưu event và retry khi chưa có xác nhận, consumer có ACK/retry | Message có thể được publish/giao/ xử lý lại |
| **Exactly-once business effect** | Thiết kế nghiệp vụ idempotent, unique constraint, provider idempotency key, reconciliation | Đây là **thuộc tính của toàn workflow nghiệp vụ**, không phải chỉ một flag của RabbitMQ |

**Publisher confirms** trả lời “broker có chấp nhận publish theo nghĩa nào?”. **Consumer ACK** trả lời “consumer/container đã xác nhận lần giao này chưa?”. **Idempotency** trả lời “nếu cùng sự kiện xảy ra hai lần, tác động nghiệp vụ có bị nhân đôi không?”.

Với các tác vụ như gửi email, thanh toán, cấp quyền hoặc trừ kho, định nghĩa **exactly-once effect** phải rất cụ thể: có phải đúng một record, một lệnh thanh toán được provider áp dụng, hay chỉ một email người dùng nhìn thấy? Không thể kết luận tất cả những điều đó chỉ vì một message đã ACK.

## 11. Quan sát và cảnh báo phía publisher

Một service publish đáng tin cậy cần metric cho **cả event** và **attempt**:

| Metric/log | Theo dõi | Ý nghĩa |
| --- | --- | --- |
| **publish_attempt_total** | Số lần gọi gửi thực tế | Tăng do retry hay lưu lượng tăng |
| **publisher_confirm_ack_total** | Broker ACK cho từng attempt | Không phải số event nghiệp vụ duy nhất |
| **publisher_confirm_nack_total** | Broker/framework báo NACK | Cần điều tra broker, channel, kết nối |
| **publisher_return_total** | Message không route được với mandatory | Kiểm tra topology/binding/routing |
| **publish_unknown_total** | Timeout, connection mất khi chưa có kết quả chắc chắn | Nhóm có rủi ro duplicate cao |
| **outbox_pending_count** | Event cần publish hoặc chờ retry | Nhu cầu xử lý chưa hoàn tất |
| **outbox_oldest_age_seconds** | Tuổi event cũ nhất chưa publish xong | Đo độ trễ nghiệp vụ thực |
| **duplicate_event_total** | Consumer bỏ qua eventId đã xử lý | Phản ánh retry/redelivery/outbox replay |
| **consumer_business_failure_total** | Tác động nghiệp vụ thất bại | Không suy ra từ publisher confirm |

Log tối thiểu nên có **eventId**, **attemptId**, **routingKey**, **exchange**, **confirm status**, **return reason**, **attemptNo**, **nextRetryAt** và **correlationId** của workflow. Không log toàn bộ payload chứa thông tin nhạy cảm.

### Không biến publisher ACK thành tín hiệu email gửi thành công

Ví dụ Order Service đã nhận confirm ACK, nhưng Notification Service đang offline. Message có thể đang nằm trong **notification.orders**, chưa có email nào được gửi. Khi API trả về trạng thái, nên phân biệt **ORDER_CREATED**, **EVENT_PUBLISHED** và **NOTIFICATION_SENT** nếu nghiệp vụ cần theo dõi từng bước.

**Queue backlog, unacked messages, retry/DLQ, thời gian xử lý consumer** phải được quan sát bên cạnh publisher metric. Nếu chỉ nhìn confirm ACK, không thể biết consumer đang nghẽn hay tác động nghiệp vụ bị lỗi.

## 12. Kiểm thử tình huống lỗi và duplicate

Hãy chuẩn bị môi trường local/test với topology mục 5 và một consumer test ghi eventId vào bảng processed_events. Các bài kiểm thử nên kiểm tra cả **số message** và **số tác động nghiệp vụ duy nhất**.

### Tình huống A — Publish bình thường

1. Publish **evt-101** khi broker và queue đều hoạt động.
2. Quan sát **confirm ACK**, không có return.
3. Kiểm tra listener nhận và transaction nghiệp vụ hoàn tất.
4. Kết quả mong đợi: một eventId được xử lý một lần trong nhóm consumer.

### Tình huống B — Sai routing key

1. Publish vào **orders.events** với key **order.unknown**, khi chỉ có binding **order.created**.
2. Bật mandatory + publisher returns như ở mục 5.
3. Quan sát **return NO_ROUTE**; publisher confirm ACK vẫn có thể xuất hiện.
4. Không đánh dấu outbox là published thành công; sửa binding hoặc phân loại lỗi routing.

### Tình huống C — Broker tạm dừng

1. Dừng RabbitMQ trước khi publish.
2. Gọi send, quan sát exception kết nối và chính sách retry.
3. Khởi động broker rồi để dispatcher gửi lại từ outbox.
4. Kiểm tra eventId giữ nguyên; publisher không tạo một sự kiện nghiệp vụ mới sau mỗi retry.

### Tình huống D — Mất confirm sau broker nhận message

1. Dùng công cụ fault injection/proxy mạng hoặc test tích hợp có khả năng ngắt đường trả confirm đúng thời điểm. Việc tắt broker ngẫu nhiên **không bảo đảm** tái hiện chính xác race này.
2. Cho broker nhận eventId **evt-201**, rồi khiến producer **không nhận confirm**.
3. Quan sát publisher ghi **UNKNOWN** và lập lịch retry.
4. Publish lần 2 với **cùng eventId**; kiểm tra queue có thể có hai message.
5. Consumer dùng unique constraint đảm bảo chỉ **một tác động DB** được thực hiện.

### Tình huống E — Consumer crash trước ACK

1. Consumer commit DB xong nhưng dừng trước khi ACK tới broker.
2. Sau khi listener kết nối lại, message có thể được redeliver.
3. Kiểm tra processed_events để bỏ qua tác động trùng và ACK đúng cách sau khi xác định duplicate an toàn.
4. Phân biệt lần lặp này với bản message mới do publisher retry.

### Tình huống F — Dispatcher outbox crash sau publish

1. Worker claim outbox, publish rồi broker ACK.
2. Làm worker crash **trước khi cập nhật PUBLISHED**.
3. Lease hết hạn, worker khác đọc lại cùng event và gửi tiếp.
4. Kiểm tra **eventId ổn định, attemptId mới, consumer idempotent** và số duplicate được ghi nhận.

## 13. Những lỗi triển khai phổ biến

| Sai lầm | Tác động | Cách sửa |
| --- | --- | --- |
| Coi **convertAndSend không ném exception** là đã giao thành công | Mất event không route/broker lỗi bất đồng bộ | Bật confirms + returns + mandatory và xử lý kết quả |
| Coi **confirm ACK** là consumer đã xử lý xong | Trạng thái nghiệp vụ sai | Theo dõi kết quả consumer riêng |
| Coi **confirm timeout** là “broker chưa nhận” | Publish lại tạo message trùng | Ghi UNKNOWN và retry với eventId ổn định |
| **Sinh UUID mới mỗi lần retry** | Consumer không nhận diện cùng event | Sinh eventId trước lần gửi đầu, lưu trong outbox |
| Dùng **correlationId của confirm** làm eventId mặc định | CorrelationData có thể thay đổi giữa attempt | Tách eventId và attemptId |
| Retry ngay mọi lỗi **NO_ROUTE** | Tăng tải mà topology vẫn sai | Dừng/cảnh báo/sửa binding trước khi phát lại |
| Bật **RetryTemplate + @Retryable + scheduler** cùng lúc | Số lần publish không kiểm soát | Một nơi sở hữu retry và ghi attempt |
| Không giới hạn retry và thiếu jitter | Retry storm khi broker phục hồi | Backoff, jitter, giới hạn attempt và retry budget |
| Outbox cập nhật **PUBLISHED** trước confirm | Có thể mất event khi broker chưa nhận | Chỉ mark sau điều kiện xác nhận phù hợp |
| Đánh dấu outbox hoàn tất chỉ bằng ACK dù có return | Bỏ mất message không route | Kiểm tra ACK **và** return |
| Chỉ dựa vào **redelivered** | Không phát hiện bản publish trùng | Idempotency theo eventId |
| Ghi eventId đã xử lý **ngoài transaction nghiệp vụ** | Có thể mark done nhưng chưa làm việc | Gộp dedupe và tác động DB cùng transaction |
| Gửi email trực tiếp trong transaction DB rồi cho là atomic | Email có thể gửi rồi nhưng DB rollback/crash | Dùng notification outbox, provider idempotency hoặc reconciliation |
| Giữ row lock DB trong lúc chờ RabbitMQ confirm | Lock contention, giảm throughput | Lease/claim ngắn, update condition theo attempt |

## 14. Bài tập thực hành

### Bài 1 — Vẽ lại cuộc đua mất confirm

Viết timeline **publish → broker enqueue → confirm mất → retry → broker enqueue lần 2**. Giải thích vì sao cả hai message có thể có **redelivered=false**, và xác định ID nào cần giữ nguyên.

### Bài 2 — CorrelationData và NO_ROUTE

Dùng config mục 5, publish 10 event hợp lệ, rồi thử một routing key không có binding. Trong future của **CorrelationData**, quan sát **confirm.isAck()** và **getReturned()**. Ghi lại khi nào publisher có thể đánh dấu trạng thái đã route.

### Bài 3 — Retry đồng bộ và retry sau confirm

Bật **spring.rabbitmq.template.retry.enabled** trong môi trường test. Dừng broker trước khi gửi và xem các lần thử khi có lỗi kết nối. Sau đó thử trường hợp broker nhận publish nhưng confirm bị timeout; giải thích vì sao RetryTemplate gắn vào RabbitTemplate **không tự tạo lần retry sau confirm timeout**.

### Bài 4 — Xây bảng outbox và dispatcher

Tạo bảng outbox theo mục 8, ghi Order và event trong một DB transaction. Xây dispatcher có **claim/lease**, **next_attempt_at**, **maxAttempts**, **attemptId** và trạng thái **PENDING/IN_FLIGHT/PUBLISHED/ROUTING_ERROR/NEEDS_ATTENTION**. Kiểm tra restart worker không làm mất event.

### Bài 5 — Chống trùng ở consumer

Tạo bảng **processed_events(consumer_name, event_id)** với unique constraint. Publish cùng eventId hai lần bằng hai CorrelationData khác nhau. Xác minh listener nhận hai message nhưng DB chỉ có một bản ghi nghiệp vụ có hiệu lực.

### Bài 6 — Rà soát retry storm

Giả lập 20 instance producer cùng mất kết nối trong 30 giây. Thiết kế backoff + jitter và giới hạn số in-flight. Nêu cách dùng **outbox_oldest_age_seconds**, **publish_unknown_total** và **publisher_return_total** để phát hiện nguy cơ mất dữ liệu hoặc routing sai.

### Câu hỏi tự đánh giá

1. Publisher confirm ACK có chứng minh message đã được consumer xử lý không?
2. Tại sao ACK của một message **unroutable** vẫn có thể là true?
3. Lỗi gì khiến publisher không thể biết broker đã nhận message trước lúc timeout?
4. RabbitTemplate RetryTemplate có tự retry sau khi confirm future hoàn tất bằng NACK không?
5. Vì sao **eventId phải giữ nguyên** qua các attempt, còn CorrelationData.id nên đại diện cho từng attempt?
6. Transactional outbox ngăn khe hở nào giữa database và broker, và vì sao outbox vẫn có thể gửi trùng?
7. **redelivered=false** có chứng minh consumer chưa từng xử lý cùng eventId không?
8. Vì sao eventId trong bảng processed_events thường phải gắn với **consumer_name**?
9. Nên retry thế nào với lỗi **NO_ROUTE** hoặc thiếu quyền publish?
10. Làm gì khi producer nhận confirm ACK muộn sau lúc scheduler đã khởi chạy retry?

## 15. Tài liệu tham khảo chính thức

- [Spring AMQP 3.2 — AmqpTemplate: Retry, Publisher Confirms and Returns](https://docs.spring.io/spring-amqp/reference/3.2/amqp/template.html): RetryTemplate, xác nhận bất đồng bộ, CorrelationData future và returned message.
- [Spring AMQP 3.2 — Sending Messages](https://docs.spring.io/spring-amqp/reference/3.2/amqp/sending-messages.html): RabbitTemplate.send/convertAndSend, CorrelationData và publish callbacks.
- [Spring AMQP — Resilience: Recovering from Errors and Broker Failures](https://docs.spring.io/spring-amqp/reference/amqp/resilience-recovering-from-errors-and-broker-failures.html): AmqpException và các lựa chọn retry.
- [Spring Boot 3.5 — Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/): spring.rabbitmq.template.retry và publisher confirm/return properties.
- [RabbitMQ — Consumer Acknowledgements and Publisher Confirms](https://www.rabbitmq.com/docs/confirms): publish confirmations, basic.return/ACK, tình huống mạng lỗi, persistence.
- [RabbitMQ — Reliability Guide](https://www.rabbitmq.com/docs/reliability): retransmit message chưa được xác nhận, khả năng trùng và consumer idempotency.
- [RabbitMQ — Publishers](https://www.rabbitmq.com/docs/publishers): kết nối producer, xử lý confirm và thiết kế an toàn dữ liệu.

---

**Ghi nhớ:** **Publisher retry cải thiện khả năng không mất event nhưng có thể tạo message trùng**, đặc biệt khi broker đã nhận publish nhưng confirm bị mất. **RabbitTemplate RetryTemplate** giúp retry lỗi đồng bộ; **publisher confirms + mandatory returns** giúp biết broker tiếp nhận và route message đến đâu nhưng kết quả có thể **UNKNOWN** khi mạng lỗi. Muốn xử lý bất đồng bộ đáng tin cậy, hãy **giữ nguyên eventId qua mọi attempt, quản lý retry có giới hạn bằng outbox, ghi nhận từng attempt và triển khai consumer idempotency**. Không thể suy ra exactly-once business effect chỉ từ publisher confirm và consumer ACK.
