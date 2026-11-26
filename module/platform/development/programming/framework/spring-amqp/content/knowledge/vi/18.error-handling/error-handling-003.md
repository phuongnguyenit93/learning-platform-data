# ListenerExecutionFailedException và thông điệp gây lỗi

Trong chương **Xử lý lỗi** của **SPRING_AMQP**, khi phương thức **@RabbitListener** thất bại, Spring AMQP thường bao nguyên nhân bên dưới trong **ListenerExecutionFailedException**. Ngoại lệ này giúp hệ thống xác định **tại sao listener lỗi** và **delivery nào gây ra lỗi**, ngay cả khi message hỏng đến mức không thể chuyển thành đối tượng Java.

Hiểu đúng exception này rất quan trọng trong một luồng RabbitMQ hoàn chỉnh: producer gửi bằng **RabbitTemplate** qua exchange, routing key và binding; queue giữ message; listener container nhận delivery, gọi converter và method nghiệp vụ; sau đó quyết định ACK, requeue hoặc reject. Nếu một message sai định dạng bị requeue ngay không giới hạn, nó có thể trở thành **poison message** gây lặp vô tận, ngốn CPU và trì hoãn các message tốt.

Bài học giải thích **getCause()**, **getFailedMessage()**, **getFailedMessages()**, cách đọc raw body và MessageProperties an toàn, phân loại lỗi conversion/validation/business, hai lớp error handler, retry, dead-letter, cũng như ví dụ Spring Boot có thể thử nghiệm.

> **Nguyên tắc:** **ListenerExecutionFailedException** là thông tin về lỗi thực thi listener, **không phải** quyết định retry hay DLQ. Quyết định cuối cùng còn phụ thuộc **RabbitListenerErrorHandler**, **ConditionalRejectingErrorHandler**, **defaultRequeueRejected**, acknowledgment mode, retry interceptor và topology dead-letter.

## 1. Ngoại lệ xuất hiện ở đâu trong đường đi message?

~~~mermaid
flowchart LR
    P["Producer<br/>RabbitTemplate"] --> E["Exchange"]
    E --> Q[("Queue")]
    Q --> C["Listener container"]
    C --> V["Message converter<br/>argument validation"]
    V --> L["@RabbitListener"]
    V -->|"Conversion failed"| X["ListenerExecutionFailedException"]
    L -->|"Throw exception"| X
    X --> H{"Error handling"}
    H -->|"Requeue"| Q
    H -->|"Reject, requeue=false"| DLX["Dead-letter exchange"]
    DLX --> DLQ[("DLQ")]
~~~

Các lỗi có thể phát sinh ở những lớp khác nhau:

| Giai đoạn | Ví dụ | Listener method được gọi chưa? |
|---|---|---|
| Broker giao message | Consumer nhận delivery | Chưa |
| AMQP MessageConverter | JSON sai cấu trúc hoặc contentType không phù hợp | **Có thể chưa** |
| Spring method argument resolution | Type mismatch, validation @Valid thất bại | **Có thể chưa** |
| Business listener | orderId không hợp lệ, vi phạm quy tắc nghiệp vụ | **Đã gọi** |
| Downstream | Database timeout, API trả HTTP 503 | **Đã gọi** |
| Hạ tầng channel/connection | Broker disconnect, channel closed | Không nhất thiết liên quan lỗi method |

Điểm quan trọng: **try/catch đặt trong phương thức listener không thể bắt tất cả lỗi conversion xảy ra trước khi phương thức được gọi**. Trong tình huống đó, cần error handler ở mức adapter/container.

Một stack trace thường có dạng:

~~~text
org.springframework.amqp.rabbit.support.ListenerExecutionFailedException:
  Listener method could not be invoked
Caused by: org.springframework.amqp.support.converter.MessageConversionException:
  Cannot convert incoming message
Caused by: com.fasterxml.jackson.core.JsonParseException:
  Unexpected JSON token
~~~

Nội dung từng dòng phụ thuộc phiên bản Spring và converter; **không parse chuỗi stack trace để quyết định retry**. Hãy dựa vào loại exception và nguyên nhân gốc.

## 2. ListenerExecutionFailedException cung cấp thông tin nào?

Tên lớp:

~~~java
org.springframework.amqp.rabbit.support.ListenerExecutionFailedException
~~~

Các API cần ghi nhớ:

| API | Trả về | Mục đích |
|---|---|---|
| **getCause()** | Throwable nằm bên dưới | Xác định lỗi thật sự |
| **getMessage()** | Mô tả của exception wrapper | Log tóm tắt, không dùng làm enum lỗi |
| **getFailedMessage()** | org.springframework.amqp.core.Message | Message AMQP liên quan đến lần thất bại |
| **getFailedMessages()** | Collection các AMQP Message | Kiểm tra nhiều message khi batch thất bại |
| **getStackTrace()** | Call stack | Debug có kiểm soát |

**getFailedMessage() trả về raw AMQP Message**, không phải DTO của phương thức @RabbitListener. Nó có **body dạng byte[]** và **MessageProperties**. Nhờ đó, bạn vẫn có thể xem contentType, routing key hay messageId khi lỗi xảy ra trước khi deserialization hoàn thành.

Đừng giả định mọi nhánh lỗi luôn mang đúng một failed message. Với batch hoặc adapter đặc thù, có thể có nhiều message. Trong code chẩn đoán nên xử lý an toàn trường hợp không có đối tượng đơn lẻ hoặc dùng **getFailedMessages()** khi cần.

### 2.1. Raw body và MessageProperties

~~~text
org.springframework.amqp.core.Message
  body: byte[]
  messageProperties:
    messageId
    correlationId
    contentType / contentEncoding
    receivedExchange / receivedRoutingKey
    consumerQueue / deliveryTag
    redelivered
    headers (schema-version, x-death, ...)
~~~

| Metadata | Dùng để tìm hiểu |
|---|---|
| messageId | Sự kiện/job nào bị lỗi |
| correlationId | Thuộc workflow hoặc request nào |
| consumerQueue | Listener nhận delivery từ queue nào |
| receivedExchange | Exchange thực tế ở lần gửi |
| receivedRoutingKey | Routing key khi broker giao |
| contentType | Body có được công bố là JSON/text/binary không |
| contentEncoding | Charset hoặc quy ước encoding có phù hợp không |
| body.length | Kích thước message, không cần lộ nội dung |
| redelivered | Broker đánh dấu delivery được giao lại |
| deliveryTag | Số thứ tự delivery trong phạm vi channel hiện tại |
| headers | Schema version, dead-letter history hoặc metadata ứng dụng |

**deliveryTag không phải event ID**, còn **redelivered không phải số lần retry chính xác**. Producer có thể gửi hai bản sao có cùng eventId nhưng mỗi bản sao đều là delivery mới và chưa chắc có redelivered=true.

### 2.2. Wrapper và root cause là hai tầng khác nhau

~~~mermaid
flowchart TD
    E["ListenerExecutionFailedException"] --> C["getCause() / cause chain"]
    C --> P["MessageConversionException"]
    C --> V["Validation exception"]
    C --> B["Business rule exception"]
    C --> T["Transient downstream exception"]
    P --> N["Thường không retry nguyên message"]
    V --> N
    B --> D["Xem contract để quyết định"]
    T --> R["Retry hữu hạn + backoff"]
~~~

Không được viết logic theo kiểu “cứ là ListenerExecutionFailedException thì reject”. Cùng một wrapper có thể xuất hiện với lỗi JSON không hồi phục và lỗi database tạm thời.

Nên tạo các exception domain có ý nghĩa rõ, chẳng hạn **InvalidOrderEventException** cho payload/contract vĩnh viễn sai và **TemporaryBillingException** cho lỗi dependency. Không mặc định mọi IllegalArgumentException là permanent hoặc mọi IllegalStateException là transient.

## 3. Hai tầng xử lý lỗi của Spring AMQP

| Thành phần | Cấu hình ở đâu | Đối tượng nhận vào | Vai trò |
|---|---|---|---|
| **RabbitListenerErrorHandler** | **@RabbitListener(errorHandler="...")** | Raw AMQP Message, converted message nếu có, exception wrapper | Chẩn đoán hoặc tạo reply lỗi; có thể ném lại để container xử lý |
| **org.springframework.util.ErrorHandler** | Listener container/factory | Throwable | Điểm xử lý ngoại lệ ở container |
| **ConditionalRejectingErrorHandler** | ErrorHandler mặc định phổ biến | Throwable và FatalExceptionStrategy | Với lỗi fatal, yêu cầu reject không requeue |
| **Retry interceptor/recoverer** | Advice chain nếu được cấu hình | Exception/attempts | Thử lại hữu hạn rồi lựa chọn recover/reject |

**RabbitListenerErrorHandler không giống container ErrorHandler**. Handler ở tầng annotation có thể trả về một đối tượng reply; nếu trả về bình thường, listener có thể được xem là đã xử lý lỗi và container sẽ ACK theo cơ chế AUTO. Khi mục tiêu chỉ là **ghi log rồi để retry/DLQ quyết định**, cần **ném lại exception**, không chỉ return null.

Trong Spring AMQP 3.2.x, **RabbitListenerErrorHandler** có chữ ký bốn tham số bao gồm **Channel**; ở một số phiên bản cũ hơn signature có ba tham số hoặc overload khác. Ví dụ Java dưới đây dành cho **Spring AMQP 3.2.x / Spring Boot 3.x**, cần đối chiếu API nếu dùng Spring AMQP 4.x.

## 4. Ví dụ Spring Boot: tạo queue và DLQ để quan sát lỗi

### 4.1. Dependency và kết nối

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-amqp</artifactId>
</dependency>
<dependency>
    <groupId>com.fasterxml.jackson.core</groupId>
    <artifactId>jackson-databind</artifactId>
</dependency>
~~~

~~~yaml
spring:
  rabbitmq:
    host: localhost
    port: 5672
    virtual-host: app_dev
    username: learn_amqp
    password: local-demo-only
~~~

Ví dụ dùng tài khoản local. Môi trường thật phải dùng biến môi trường/secret manager, không commit password. Queue/exchange bên dưới cần thuộc đúng vhost và user có quyền khai báo/đọc/ghi phù hợp.

### 4.2. Topology: queue chính và dead-letter

~~~java
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.Declarables;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class ErrorHandlingTopology {
    public static final String EXCHANGE = "orders.events";
    public static final String ROUTING_KEY = "order.placed";
    public static final String QUEUE = "billing.order-placed.q";
    public static final String DLX = "billing.errors.dlx";
    public static final String DLQ = "billing.order-placed.dlq";
    public static final String DEAD_KEY = "billing.order-placed.failed";

    @Bean
    public Declarables errorResources() {
        DirectExchange exchange =
                new DirectExchange(EXCHANGE, true, false);
        DirectExchange dlx =
                new DirectExchange(DLX, true, false);

        Queue work = QueueBuilder.durable(QUEUE)
                .deadLetterExchange(DLX)
                .deadLetterRoutingKey(DEAD_KEY)
                .build();
        Queue failed = QueueBuilder.durable(DLQ).build();

        return new Declarables(
                exchange,
                dlx,
                work,
                failed,
                BindingBuilder.bind(work).to(exchange).with(ROUTING_KEY),
                BindingBuilder.bind(failed).to(dlx).with(DEAD_KEY)
        );
    }
}
~~~

Khi listener reject với **requeue=false**, broker có thể dead-letter message sang **billing.order-placed.dlq** nếu DLX và binding đúng. Nếu không có DLX, message bị reject có thể bị loại bỏ.

**Khai báo DLX không tự bật retry**. Một queue được dead-letter là đường lưu message lỗi, không phải vòng tự động thử lại nếu chưa thiết kế thêm cơ chế.

### 4.3. DTO và listener có hai loại lỗi

~~~java
public record OrderPlacedEvent(
        String eventId,
        String orderId,
        long totalCents
) {}
~~~

~~~java
import org.springframework.amqp.AmqpRejectAndDontRequeueException;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class BillingOrderListener {

    @RabbitListener(
            queues = ErrorHandlingTopology.QUEUE,
            containerFactory = "ordersListenerFactory",
            errorHandler = "diagnosticRabbitErrorHandler"
    )
    public void handle(OrderPlacedEvent event) {
        if (event.orderId() == null || event.orderId().isBlank()
                || event.totalCents() < 0) {
            throw new AmqpRejectAndDontRequeueException(
                    "Invalid OrderPlaced contract"
            );
        }

        if ("temporary".equals(event.orderId())) {
            throw new IllegalStateException(
                    "Billing service temporarily unavailable"
            );
        }

        System.out.println("Accepted order " + event.orderId());
    }
}
~~~

**AmqpRejectAndDontRequeueException** yêu cầu không requeue message sai hợp đồng. **IllegalStateException** ở đây chỉ mô phỏng sự cố tạm thời; trong ứng dụng thật cần exception domain riêng và retry có giới hạn. Lỗi malformed JSON có thể xảy ra trước khi method chạy, vì Spring phải convert bytes thành **OrderPlacedEvent**.

### 4.4. JSON converter và container error handler

~~~java
import org.springframework.amqp.rabbit.config.SimpleRabbitListenerContainerFactory;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.amqp.rabbit.listener.ConditionalRejectingErrorHandler;
import org.springframework.amqp.support.converter.Jackson2JsonMessageConverter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class ErrorListenerConfiguration {

    @Bean("ordersListenerFactory")
    public SimpleRabbitListenerContainerFactory ordersListenerFactory(
            ConnectionFactory connectionFactory) {
        SimpleRabbitListenerContainerFactory factory =
                new SimpleRabbitListenerContainerFactory();

        factory.setConnectionFactory(connectionFactory);
        factory.setMessageConverter(new Jackson2JsonMessageConverter());
        factory.setConcurrentConsumers(1);
        factory.setPrefetchCount(1);

        // Demo không retry ngay mọi lỗi vì chưa có bounded retry.
        factory.setDefaultRequeueRejected(false);
        factory.setErrorHandler(new ConditionalRejectingErrorHandler());
        return factory;
    }
}
~~~

**defaultRequeueRejected=false** ở đây phục vụ **thí nghiệm an toàn**, tránh message lỗi quay vòng vô hạn. Nó cũng có nghĩa **lỗi tạm thời chưa được retry** mà sẽ bị reject, có thể đi DLQ ngay. Trong production, nên dùng chính sách phân loại permanent/transient và retry/backoff hữu hạn thay vì đối xử giống nhau với mọi exception.

Nếu RabbitAdmin của Spring Boot tự khai báo topology, các queue/exchange/binding có thể được tạo khi connection sẵn sàng. Nếu queue cùng tên đã tồn tại nhưng khác DLX arguments/durable/queue type, active declaration có thể báo **406 PRECONDITION_FAILED**; không xóa queue có message chỉ để vượt lỗi.

## 5. Chẩn đoán failedMessage an toàn bằng RabbitListenerErrorHandler

Ví dụ này dùng API **RabbitListenerErrorHandler** bốn tham số của Spring AMQP 3.2.x. Ta đọc raw failed Message, ghi metadata có kiểm soát rồi **ném lại exception** để container tiếp tục xử lý theo chính sách.

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.core.MessageProperties;
import org.springframework.amqp.rabbit.listener.api.RabbitListenerErrorHandler;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class DiagnosticErrorHandlerConfig {
    private static final Logger log =
            LoggerFactory.getLogger(DiagnosticErrorHandlerConfig.class);

    @Bean("diagnosticRabbitErrorHandler")
    public RabbitListenerErrorHandler diagnosticRabbitErrorHandler() {
        return (amqpMessage, channel, convertedMessage, exception) -> {
            Message failed = exception.getFailedMessage();
            if (failed == null) {
                failed = amqpMessage;
            }

            Throwable cause = exception.getCause() == null
                    ? exception : exception.getCause();

            if (failed == null) {
                log.error(
                        "Listener failed without raw message: errorType={}",
                        cause.getClass().getSimpleName()
                );
            } else {
                MessageProperties props = failed.getMessageProperties();

                log.error(
                        "Listener failed: id={}, queue={}, exchange={}, " +
                        "routingKey={}, contentType={}, bodyBytes={}, " +
                        "redelivered={}, errorType={}",
                        props.getMessageId(),
                        props.getConsumerQueue(),
                        props.getReceivedExchange(),
                        props.getReceivedRoutingKey(),
                        props.getContentType(),
                        failed.getBody() == null ? 0 : failed.getBody().length,
                        props.isRedelivered(),
                        cause.getClass().getSimpleName()
                );
            }

            // Không nuốt lỗi, để container reject/requeue theo policy.
            throw exception;
        };
    }
}
~~~

**Vì sao không log failed.getBody() trực tiếp?** Payload có thể chứa tên khách hàng, địa chỉ, payment token hoặc secret. Log raw bytes, Message.toString() và đôi khi full exception message có thể làm lộ dữ liệu.

**convertedMessage** có thể bằng null khi conversion xảy ra lỗi trước khi Spring Messaging Message được tạo. Trong trường hợp đó, raw **amqpMessage** vẫn có thể giúp xác định kiểu dữ liệu và thông tin định tuyến.

Nếu listener error handler **return bình thường** thay vì ném exception, Spring có thể coi method đã được xử lý và tạo reply nếu request có **replyTo/@SendTo**. Với chế độ AUTO, message có thể được ACK. Vì vậy, handler chỉ dùng để log phải **ném lại exception**.

### 5.1. Không suy số lần retry từ redelivered

Thuộc tính **redelivered** cho biết broker đánh dấu delivery đã từng giao rồi được đưa lại. Nó không cho biết chính xác lần thứ mấy. Một producer có thể tự publish cùng một eventId hai lần và cả hai delivery đều không có redelivered=true.

Khi cần giới hạn retry, dùng **attempt count được quản lý đáng tin cậy** trong retry mechanism hoặc trong message metadata được kiểm soát, và kết hợp **idempotency key** để bảo vệ side effect.

## 6. Gửi message hợp lệ và message gây lỗi

Sử dụng **RabbitTemplate.send** để truyền raw JSON bytes với contentType rõ:

~~~java
import java.nio.charset.StandardCharsets;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.core.MessageBuilder;
import org.springframework.amqp.core.MessageProperties;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderTestPublisher {
    private final RabbitTemplate template;

    public OrderTestPublisher(RabbitTemplate template) {
        this.template = template;
    }

    public void publish(String eventId, String json) {
        Message message = MessageBuilder.withBody(
                json.getBytes(StandardCharsets.UTF_8))
                .setContentType(MessageProperties.CONTENT_TYPE_JSON)
                .setContentEncoding("UTF-8")
                .setMessageId(eventId)
                .build();

        template.send(
                ErrorHandlingTopology.EXCHANGE,
                ErrorHandlingTopology.ROUTING_KEY,
                message
        );
    }
}
~~~

Trong một test hoặc runner có bean **OrderTestPublisher**, gọi:

~~~java
publisher.publish(
        "evt-good-1",
        "{\"eventId\":\"evt-good-1\",\"orderId\":\"ord-1\",\"totalCents\":1200}"
);

publisher.publish(
        "evt-bad-1",
        "{\"eventId\":\"evt-bad-1\",\"orderId\":\"\",\"totalCents\":1200}"
);

publisher.publish(
        "evt-json-1",
        "{\"eventId\":\"evt-json-1\",\"orderId\":"
);

publisher.publish(
        "evt-temp-1",
        "{\"eventId\":\"evt-temp-1\",\"orderId\":\"temporary\",\"totalCents\":1200}"
);
~~~

Bảng kết quả kỳ vọng khi cấu hình đúng:

| Event | Nguyên nhân | Method listener có chạy? | Chính sách demo |
|---|---|---|---|
| **evt-good-1** | Không lỗi | Có | Xử lý và ACK |
| **evt-bad-1** | Invalid domain event | Có | Reject không requeue → DLQ |
| **evt-json-1** | JSON malformed | Có thể chưa | Fatal conversion → reject → DLQ |
| **evt-temp-1** | Downstream exception mô phỏng | Có | Với defaultRequeueRejected=false: reject → DLQ |

Hai ví dụ lỗi JSON và lỗi nghiệp vụ có thể đều được biểu diễn bằng **ListenerExecutionFailedException**, nhưng **getCause()** và thời điểm xảy ra lỗi khác nhau.

**Lưu ý:** Một DTO dùng kiểu primitive long có thể nhận giá trị 0 nếu thiếu trường, tùy cấu hình Jackson. Trong ứng dụng thật cần validate sự hiện diện, kiểu và giá trị của các trường bắt buộc theo schema; code trên chỉ minh họa listener failure path.

## 7. ConditionalRejectingErrorHandler và fatal errors

Spring AMQP dùng **ConditionalRejectingErrorHandler** theo mặc định ở nhiều listener container. Handler này xét **FatalExceptionStrategy** để nhận ra những lỗi không nên requeue.

Trong Spring AMQP 3.x, các nhóm lỗi thường được phân loại fatal gồm:

- **org.springframework.amqp.support.converter.MessageConversionException**.
- **org.springframework.messaging.converter.MessageConversionException**.
- **MethodArgumentNotValidException** do validation.
- **MethodArgumentTypeMismatchException** trong resolution.
- **NoSuchMethodException**.
- **ClassCastException**.

Khi fatal strategy trả true, handler thường tạo **AmqpRejectAndDontRequeueException**. Broker có thể chuyển message tới DLQ nếu queue đã khai báo DLX.

### 7.1. defaultRequeueRejected và exception đặc biệt

| Trường hợp | defaultRequeueRejected=true | defaultRequeueRejected=false |
|---|---|---|
| Lỗi listener thông thường, không fatal | Có thể requeue | Thường reject không requeue |
| **AmqpRejectAndDontRequeueException** | Reject không requeue | Reject không requeue |
| **ImmediateRequeueAmqpException** | Yêu cầu requeue | Có thể yêu cầu requeue dù default false |
| Fatal conversion/validation được nhận diện | Thường reject không requeue | Reject không requeue |
| Handler thành công | ACK theo acknowledgment mode | ACK theo acknowledgment mode |

**Requeue ngay** không có backoff và có thể tạo vòng lặp lỗi rất nhanh. Cần retry interceptor có số lần thử hữu hạn, delay/backoff và recoverer hoặc retry queue được giới hạn số vòng để xử lý transient error.

### 7.2. Bổ sung lỗi nghiệp vụ vào FatalExceptionStrategy

Trong Spring AMQP 3.x, có thể mở rộng **ConditionalRejectingErrorHandler.DefaultExceptionStrategy**:

~~~java
import org.springframework.amqp.rabbit.listener.ConditionalRejectingErrorHandler;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class FatalDomainPolicy {

    @Bean
    public ConditionalRejectingErrorHandler domainFatalHandler() {
        return new ConditionalRejectingErrorHandler(
                new ConditionalRejectingErrorHandler.DefaultExceptionStrategy() {
                    @Override
                    protected boolean isUserCauseFatal(Throwable cause) {
                        return cause instanceof InvalidOrderEventException
                                || super.isUserCauseFatal(cause);
                    }
                }
        );
    }
}
~~~

**InvalidOrderEventException** là exception nghiệp vụ do ứng dụng tự định nghĩa; nó chỉ nên đại diện lỗi **permanent**. Để cấu hình này có hiệu lực, cần gán bean hoặc một instance tương đương vào listener container factory. **Chỉ khai báo bean không bảo đảm thay thế mọi error handler mặc định**.

Không đánh dấu HTTP timeout, database connection refused hoặc lỗi transient tương tự là fatal nếu chúng có thể phục hồi.

### 7.3. Lưu ý x-death và vòng DLQ

RabbitMQ thêm header **x-death** cho một số message đã đi qua dead-letter. Trong Spring AMQP hiện đại, ConditionalRejectingErrorHandler có cơ chế **discardFatalsWithXDeath** để ngăn message fatal cứ được trả về queue chính rồi dead-letter liên tục.

Điều đó giúp dừng vòng lặp, nhưng cũng có nghĩa message fatal được redrive nhiều lần có thể **bị discard**, không còn nằm ở queue mong muốn để điều tra. Vì vậy:

1. Tránh cấu hình main queue ↔ DLQ thành vòng retry vô tận.
2. Theo dõi số message fatal và các lần discard.
3. Xây **parking/quarantine queue** khi bắt buộc bảo toàn thông tin lỗi.
4. Thiết kế giới hạn retry có ý nghĩa thay vì chỉ suy số lần từ redelivered.
5. Kiểm tra chính sách theo phiên bản Spring AMQP/RabbitMQ thực tế.

## 8. Batch listener: getFailedMessages() khác getFailedMessage()

Khi xử lý batch, một lần gọi có thể liên quan nhiều AMQP message. **getFailedMessages()** cung cấp collection tương ứng:

~~~java
import java.util.Collection;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.rabbit.support.ListenerExecutionFailedException;

public void inspectBatch(ListenerExecutionFailedException exception) {
    Collection<Message> messages = exception.getFailedMessages();

    for (Message message : messages) {
        if (message == null) {
            continue;
        }
        System.out.println(
                "messageId=" + message.getMessageProperties().getMessageId()
                + ", bytes=" + message.getBody().length
        );
    }
}
~~~

Đoạn code dùng cho việc kiểm tra kỹ thuật trong môi trường thử nghiệm. Trong production nên dùng logger và tránh in trực tiếp body.

**Không kết luận mọi message của batch đều hỏng chỉ vì một lần batch execution thất bại.** Có thể một message ở một index cụ thể là nguyên nhân. Với **BatchListenerFailedException**, một số loại container có thể xử lý theo index/message lỗi để quản lý ACK/NACK phù hợp; phải kiểm tra behavior và phiên bản đang dùng.

## 9. Chọn retry, reject hoặc DLQ theo nguyên nhân

| Loại lỗi | Ví dụ | Chiến lược |
|---|---|---|
| **Sai schema / malformed JSON** | Thiếu required field, contentType sai | Thường reject không requeue → DLQ |
| **Permanent business rule** | Đơn hàng không được phép xử lý | Business response hoặc DLQ theo hợp đồng |
| **Transient downstream** | DB timeout, HTTP 503 | Retry hữu hạn có backoff |
| **Code bug** | NullPointerException không dự kiến | Alert, tránh retry vô hạn |
| **Broker/channel issue** | Mất connection | Để container reconnect/recover |
| **Duplicate** | eventId đã được xử lý | Không lặp side effect, ACK an toàn |

### 9.1. Retry trong container và retry thông qua queue

**Retry interceptor** ở tầng Spring có thể thử lại một số lần trước khi recoverer chọn hành động cuối. Nó có thể giữ thread consumer đang chờ giữa các attempt.

**Retry queue** có thể giữ message trong khoảng delay trước khi đưa trở lại queue chính. Thiết kế này cần chính sách TTL/dead-letter, giới hạn số vòng, theo dõi history và tránh message loop.

Không có chiến lược nào bảo đảm exactly-once. Nếu nghiệp vụ đã commit nhưng ACK mất, cùng event có thể được redeliver. Dùng **eventId, unique constraint và transaction** để ngăn tác dụng phụ lặp lại.

### 9.2. DLQ chỉ nhận message nếu topology đúng

Nếu listener ném **AmqpRejectAndDontRequeueException** và container reject với requeue=false, message **có thể** được đưa vào DLQ. Nhưng để điều này xảy ra, cần:

- Queue chính có cấu hình **dead-letter-exchange**.
- DLX tồn tại và queue đích được **bind** đúng routing key.
- User/broker có quyền và các điều kiện publish dead-letter đáp ứng.
- Không có policy khác làm đổi hành vi.

Nếu thiếu một mắt xích, message có thể bị loại bỏ hoặc không xuất hiện ở DLQ dự kiến. Luôn đối chiếu log với **RabbitMQ Management UI** và metrics queue thực tế.

## 10. Logging failed message mà không lộ dữ liệu

Một lỗi conversion có thể chứa payload khách hàng hoặc dữ liệu bí mật. Không ghi toàn bộ **Message.toString()** hoặc body JSON vào log ở production nếu chưa có quyền và cơ chế bảo vệ phù hợp.

| Nên log | Không nên mặc định log |
|---|---|
| messageId/eventId | Toàn bộ body |
| correlationId | Token, password, API key |
| consumerQueue, receivedRoutingKey | Dữ liệu cá nhân/địa chỉ |
| contentType, contentEncoding | Thông tin thanh toán |
| body byte length | Headers chứa secret |
| Cause class / error code chuẩn hóa | Exception message có chép một phần payload |
| redelivered, attempt theo cơ chế đã quản lý | Tự đoán số lần retry từ redelivered |

Một dòng log hợp lý:

~~~text
listenerId=billingOrderListener
messageId=evt-json-1
queue=billing.order-placed.q
exchange=orders.events
routingKey=order.placed
contentType=application/json
bodyBytes=45
redelivered=false
errorType=MessageConversionException
decision=REJECT_NO_REQUEUE
~~~

**Đừng giả định một log có decision=REJECT_NO_REQUEUE đồng nghĩa message đã nằm ở DLQ.** Cần quan sát broker để xác nhận dead-letter đã route thành công.

### 10.1. Giám sát các chỉ số nào?

| Metric | Mục đích |
|---|---|
| Listener errors theo loại cause | Xác định lỗi schema hay downstream |
| Fatal rejects | Theo dõi poison messages |
| Retry attempts, backoff time | Nhận ra retry quá nhanh |
| DLQ depth / oldest age | Message không được xử lý kéo dài |
| Ready / Unacked | Backlog và delivery đang chờ ACK |
| Redelivery rate | Tín hiệu vòng lặp requeue |
| Consumer count | Listener còn hoạt động không |
| Processing latency | Downstream đang chậm hay không |

Nếu lỗi conversion bùng phát sau một lần triển khai producer mới, cần kiểm tra **schema version và MessageConverter của cả producer/consumer**, không chỉ tăng concurrency.

## 11. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Giải pháp |
|---|---|---|
| Chỉ try/catch trong @RabbitListener | Không bắt được lỗi trước method | Dùng error handler tầng listener/container |
| Chỉ kiểm tra wrapper class | Không phân loại được nguyên nhân thật | Đọc getCause và cause chain |
| Log raw failedMessage body | Có thể lộ thông tin nhạy cảm | Log metadata whitelist |
| Handler log rồi return bình thường | Có thể vô tình ACK | Ném lại exception khi chưa xử lý xong |
| Requeue mọi exception không giới hạn | Poison loop, tăng CPU | Retry giới hạn, fatal classification |
| Reject mọi lỗi lập tức | Không hồi phục được lỗi DB tạm thời | Retry cho transient theo chính sách |
| defaultRequeueRejected=false nhưng không có DLX | Message có thể bị discard | Khai báo DLX/DLQ và giám sát |
| Nhầm redelivered với retry count | Sai kết quả phân tích | Dùng attempt metadata đáng tin |
| MANUAL ACK không ACK/NACK | Unacked tăng | Quản lý deliveryTag và channel đúng |
| Không kiểm tra batch messages | Bỏ sót dữ liệu lỗi trong batch | Dùng getFailedMessages và batch-specific handling |
| Requeue message sau khi DB commit không dedup | Side effect bị lặp | eventId + idempotent consumer |

## 12. Bài tập thực hành

### Bài A — Exception nghiệp vụ

1. Khởi động RabbitMQ với topology mục 4 trên vhost test.
2. Gửi **evt-bad-1** có orderId rỗng.
3. Xem log từ diagnostic error handler và cause type.
4. Kiểm tra message được reject và xuất hiện trong DLQ nếu cấu hình đúng.
5. Giải thích vì sao retry nguyên JSON này không giúp sửa lỗi.

### Bài B — Conversion thất bại trước listener

1. Gửi **evt-json-1** chứa JSON malformed.
2. Đảm bảo listener method không xử lý message đó như một OrderPlacedEvent.
3. Đọc messageId, routing key, contentType và body size từ failed Message.
4. So sánh với bài A về cause type và giai đoạn lỗi xảy ra.
5. Xác minh error handler và DLQ hoạt động như dự kiến.

### Bài C — Lỗi tạm thời

1. Gửi **evt-temp-1**.
2. Quan sát với **defaultRequeueRejected=false**, message không được retry ngay.
3. Thiết kế retry hữu hạn ba lần và backoff khi gặp lỗi downstream.
4. Đề xuất hành động sau khi hết ngân sách retry.
5. Nêu cơ chế idempotency khi listener đã commit dữ liệu nhưng ACK bị mất.

### Bài D — Handler nuốt exception

1. Trong môi trường test, tạm đổi handler sang **return null** thay vì throw.
2. Gửi một message sai, quan sát ACK/queue/DLQ.
3. Giải thích tại sao chỉ log exception không đủ.
4. Khôi phục handler ném lại exception.

### Bài E — Batch và x-death

1. Viết một batch listener trên queue thử nghiệm; tạo ba message, phần tử thứ hai malformed.
2. Xem **getFailedMessages()** và thảo luận cách xác định phần tử lỗi.
3. Tìm hiểu **BatchListenerFailedException** để điều khiển xử lý batch theo phiên bản.
4. Thử replay một message fatal có x-death duy nhất trong môi trường test.
5. Thiết kế parking queue/giới hạn retry để tránh vòng dead-letter vô hạn.

## 13. Câu hỏi tự đánh giá

1. Vì sao ListenerExecutionFailedException không có nghĩa mọi lỗi đều permanent?
2. getFailedMessage khác tham số DTO của @RabbitListener ở đâu?
3. Khi JSON malformed, vì sao try/catch bên trong listener có thể không được chạy?
4. RabbitListenerErrorHandler trả về bình thường có thể tác động đến ACK thế nào?
5. ConditionalRejectingErrorHandler thường phân loại những loại lỗi nào là fatal?
6. defaultRequeueRejected=false có tự tạo dead-letter queue không?
7. Tại sao redelivered không đại diện chính xác số lần event được gửi?
8. Trong batch, khi nào nên đọc getFailedMessages?
9. Vì sao không nên log raw body trong hệ thống xử lý thông tin thanh toán?
10. Khi message có x-death bị trả về queue chính nhiều lần, điều gì có thể xảy ra với fatal handler?

## 14. Tổng kết

- **ListenerExecutionFailedException** gắn lỗi thực thi listener với **message gây lỗi**, truy cập qua **getCause()**, **getFailedMessage()** hoặc **getFailedMessages()**.
- Lỗi **conversion/validation** có thể xảy ra trước khi phương thức @RabbitListener thực sự chạy.
- **RabbitListenerErrorHandler** hỗ trợ quan sát lỗi ở tầng annotated endpoint; **ConditionalRejectingErrorHandler** xử lý chiến lược fatal ở tầng container.
- **Không nuốt exception chỉ để ghi log** nếu muốn container tiếp tục reject/retry.
- **Poison message** thường cần reject và DLQ; lỗi tạm thời cần retry hữu hạn, backoff và cảnh báo.
- **defaultRequeueRejected** không tự tạo DLX/DLQ; cần topology RabbitMQ đúng.
- Metadata của failedMessage hữu ích, nhưng phải tránh ghi dữ liệu nhạy cảm trong body và headers.
- Độ tin cậy của Spring AMQP vẫn phụ thuộc vào **RabbitTemplate, exchange/queue/binding, @RabbitListener, publisher confirms, ACK, retry, dead-letter và idempotency**.

### Tài liệu tham khảo chính thức

- [Spring AMQP — ListenerExecutionFailedException API](https://docs.spring.io/spring-amqp/docs/3.1.x/api/org/springframework/amqp/rabbit/support/ListenerExecutionFailedException.html): getFailedMessage và getFailedMessages.
- [Spring AMQP — Exception Handling](https://docs.spring.io/spring-amqp/reference/amqp/exception-handling.html): ConditionalRejectingErrorHandler và FatalExceptionStrategy.
- [Spring AMQP — @RabbitListener Error Handling](https://docs.spring.io/spring-amqp/reference/amqp/receiving-messages/async-annotation-driven/error-handling.html): RabbitListenerErrorHandler và converted message.
- [Spring AMQP — RabbitListenerErrorHandler Javadoc (3.2)](https://docs.spring.io/spring-amqp/docs/3.2.5/api/org/springframework/amqp/rabbit/listener/api/RabbitListenerErrorHandler.html): chữ ký có Channel.
- [RabbitMQ — Consumer Acknowledgements](https://www.rabbitmq.com/docs/confirms): ACK và NACK.
- [RabbitMQ — Dead Letter Exchanges](https://www.rabbitmq.com/docs/dlx): cơ chế dead-letter khi reject không requeue.
