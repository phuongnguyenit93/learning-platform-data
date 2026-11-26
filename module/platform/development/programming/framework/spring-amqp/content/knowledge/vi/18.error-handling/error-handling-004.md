# ErrorHandler của container và RabbitListenerErrorHandler

## Mục tiêu bài học

Trong **Spring AMQP**, producer dùng **RabbitTemplate** phát message tới RabbitMQ; **exchange** định tuyến qua **binding** đến queue, còn **@RabbitListener** thực hiện xử lý nghiệp vụ. Khi consumer gặp lỗi, một câu hỏi quan trọng là: **ai thấy lỗi đầu tiên, ai quyết định thử lại, khi nào message được ACK/NACK, và khi nào nó vào dead-letter queue (DLQ)?**

Spring AMQP có **hai tầng error handler dễ bị nhầm lẫn**:

1. **ErrorHandler của listener container**, thường là **ConditionalRejectingErrorHandler**. Nó xử lý lỗi đi ra đến tầng container, phân loại lỗi fatal và ảnh hưởng quyết định reject/requeue.
2. **RabbitListenerErrorHandler**, gắn trực tiếp với một endpoint **@RabbitListener(errorHandler="...")**. Nó được gọi trong tầng annotation listener adapter, có thể quan sát raw AMQP Message, converted Spring Messaging Message và exception; có thể **trả kết quả** hoặc **ném exception tiếp**.

Bài thuộc chương **Xử lý lỗi**, tập trung vào điểm khác nhau, thứ tự xử lý, ví dụ cấu hình thực tế và các tình huống message không hợp lệ, DB tạm mất kết nối, retry, dead-letter, transaction và idempotency.

Sau bài này, bạn có thể:

1. Phân biệt **container ErrorHandler** với **RabbitListenerErrorHandler** theo phạm vi, thời điểm, chữ ký và trách nhiệm.
2. Mô tả luồng lỗi từ **MessageConverter → @RabbitListener → RabbitListenerErrorHandler → container ErrorHandler → broker**.
3. Hiểu **ConditionalRejectingErrorHandler**, **FatalExceptionStrategy**, các lỗi conversion/argument fatal và các tùy chọn **rejectManual**, **discardFatalsWithXDeath**.
4. Cấu hình handler bằng **SimpleRabbitListenerContainerFactory.setErrorHandler(...)** và **@RabbitListener(errorHandler=...)**.
5. Biết khi nào **return** trong RabbitListenerErrorHandler làm lỗi được xem là đã xử lý, khi nào **throw** khiến container tiếp tục xử lý.
6. Thiết kế retry hữu hạn, DLQ, ACK và idempotent consumer, tránh poison-message loop hoặc mất message do nuốt lỗi.

## 1. Bối cảnh: một lỗi có thể xảy ra trước hoặc trong listener

Một message không nhất thiết chỉ thất bại trong code nghiệp vụ. Xem các tình huống:

- Message có body JSON sai cú pháp, converter không thể tạo DTO.
- JSON hợp lệ nhưng thiếu trường bắt buộc, gây **MethodArgumentNotValidException** khi validate.
- DTO hợp lệ nhưng gọi database bị timeout.
- Một API thanh toán nhận lệnh nhưng connection đứt trước khi trả kết quả.
- Listener xử lý xong DB nhưng ACK bị mất, message được broker giao lại.
- Retry hết lượt, cần chuyển message tới DLQ để kiểm tra.

~~~mermaid
flowchart TD
    P["RabbitTemplate publish"] --> X{"orders.events exchange"}
    X --> Q[("orders.created.work queue")]
    Q --> C["Listener container nhận delivery"]
    C --> V["AMQP converter + listener adapter"]
    V --> D{"Chuyển đổi thành công?"}
    D -->|"Không"| H["@RabbitListener errorHandler<br/>khi adapter hỗ trợ"]
    D -->|"Có"| L["@RabbitListener method"]
    L --> B{"Handler thành công?"}
    B -->|"Có"| A["ACK theo ackMode"]
    B -->|"Không"| H
    H --> T{"Return hay throw?"}
    T -->|"Return kết quả, xử lý hợp lệ"| R["Adapter tiếp tục reply/complete"]
    T -->|"Throw"| E["Container ErrorHandler"]
    E --> F{"Fatal hoặc policy?"}
    F -->|"Reject không requeue"| DLQ["DLX / DLQ nếu cấu hình"]
    F -->|"Requeue"| Q
~~~

Đây là **sơ đồ khái niệm**, không có nghĩa mọi lỗi đều phải đi qua RabbitListenerErrorHandler. Nếu endpoint không cấu hình handler ấy, hoặc lỗi xảy ra trước khi listener adapter kiểm soát được message, exception có thể đi thẳng tới container.

**ErrorHandler không phải message recoverer, không phải DLX và không phải RabbitAdmin.** Một exception được đánh dấu reject không requeue chỉ dẫn đến DLQ khi **broker có dead-letter topology phù hợp**.

## 2. So sánh hai ErrorHandler

| Tiêu chí | ErrorHandler của container | RabbitListenerErrorHandler |
| --- | --- | --- |
| Interface | **org.springframework.util.ErrorHandler** | **org.springframework.amqp.rabbit.listener.api.RabbitListenerErrorHandler** |
| Đặt ở đâu? | Listener container/factory | **@RabbitListener(errorHandler="beanName")** |
| Phạm vi | Các endpoint/consumer dùng container hoặc factory đã cấu hình | Endpoint được gắn tên handler |
| Input chính | **Throwable** | Raw AMQP Message, AMQP Channel (API mới), converted Spring Messaging Message (có thể null), **ListenerExecutionFailedException** |
| Tầng xử lý | Container, phía ngoài listener adapter | Annotated listener adapter, gần method nghiệp vụ hơn |
| Có thể trả reply không? | **Không**; handleError trả void | **Có**; return value có thể được xử lý theo request/reply |
| Điều khiển reject/requeue | Thông qua exception/fatal classification, phối hợp chính sách container | Có thể ném **AmqpRejectAndDontRequeueException**, **ImmediateRequeueAmqpException** để chuyển quyền xử lý xuống container |
| Lỗi JSON trước khi method chạy | Có thể xử lý exception nhận được từ adapter/container | Một số phiên bản gọi handler với converted message **null** khi lỗi conversion trong adapter |
| Use case chính | Quy tắc fatal của toàn nhóm listener, log/metric, tránh redelivery vô hạn | Chính sách lỗi từng method, response chuẩn hóa cho request/reply, bổ sung ngữ cảnh endpoint |

**Không thay thế lẫn nhau:** cấu hình một **@RabbitListener(errorHandler="...")** không vô hiệu hóa error handler ở container. Nếu endpoint handler ném lỗi tiếp, container vẫn có cơ hội phân loại và quyết định xử lý theo cấu hình.

### 2.1. Thứ tự khi listener ném lỗi

~~~mermaid
sequenceDiagram
    participant B as RabbitMQ
    participant C as Listener container
    participant A as Annotated listener adapter
    participant L as @RabbitListener method
    participant H as RabbitListenerErrorHandler
    participant E as Container ErrorHandler
    B->>C: Delivery OrderCreated
    C->>A: Invoke adapter
    A->>L: invoke method
    L--xA: throw business exception
    A->>H: handleError(raw, channel, converted, wrapped error)
    alt Handler trả kết quả
        H-->>A: return result
        A-->>C: xử lý reply/complete theo endpoint
        C-->>B: ACK theo mode nếu thành công
    else Handler ném exception
        H--xA: throw
        A--xC: propagate
        C->>E: handleError(Throwable)
        E--xC: reject marker hoặc rethrow
        C-->>B: reject/requeue hoặc DLX theo policy
    end
~~~

Nếu một handler **trả bình thường** và adapter hoàn thành việc xử lý thành công, với **AcknowledgeMode.AUTO** container có thể gửi ACK; vì vậy **trả kết quả để che giấu lỗi nghiệp vụ chưa xử lý** có thể làm mất cơ hội retry.

## 3. ErrorHandler ở container: ConditionalRejectingErrorHandler

Spring AMQP thường dùng **ConditionalRejectingErrorHandler** mặc định cho message listener container. Đây là một triển khai của **org.springframework.util.ErrorHandler**, có phương thức:

~~~java
void handleError(Throwable t);
~~~

Nó kiểm tra exception/cause chain. Với các lỗi được đánh giá **fatal**, handler ném **AmqpRejectAndDontRequeueException**, nhằm không đưa một message rõ ràng không xử lý được quay vòng qua queue vô hạn.

### 3.1. Các lỗi fatal mặc định đáng chú ý

Trong các nhánh Spring AMQP 3.x, **DefaultExceptionStrategy** có thể coi những lỗi sau là fatal khi chúng là nguyên nhân liên quan tới listener execution:

| Ngoại lệ | Nguồn lỗi thường gặp | Vì sao retry y nguyên ít hữu ích? |
| --- | --- | --- |
| **org.springframework.amqp.support.converter.MessageConversionException** | AMQP MessageConverter không đọc được body/content type | Body/metadata không đổi qua retry |
| **org.springframework.messaging.converter.MessageConversionException** | Conversion bổ sung ở Spring Messaging | Không khớp kiểu đích method |
| **MethodArgumentNotValidException** | @Valid hoặc Bean Validation ở argument | Dữ liệu không đáp ứng ràng buộc |
| **MethodArgumentTypeMismatchException** | Argument sai type của method | Không thể invoke endpoint tương ứng |
| **NoSuchMethodException** | Dispatch không tìm được handler phù hợp | Sai contract/method mapping |
| **ClassCastException** | Type mismatch theo đường adapter | Payload không phù hợp với type xử lý |

**Đây không phải bảng khẳng định mọi RuntimeException đều fatal.** Lỗi database, timeout HTTP hay một business exception thông thường cần chính sách riêng. Ngoài ra, danh sách fatal mặc định là chính sách của **Spring AMQP**, không phải phân loại tự động của RabbitMQ broker.

### 3.2. Tại sao defaultRequeueRejected=true chưa đủ để đoán kết quả?

Một container có thể cấu hình:

~~~java
factory.setDefaultRequeueRejected(true);
~~~

Giá trị này thường cho phép requeue khi listener thất bại **mà không có chỉ thị khác**. Tuy nhiên, **ConditionalRejectingErrorHandler** có thể xác định lỗi conversion là fatal và ném **AmqpRejectAndDontRequeueException**, **ghi đè** hành vi requeue mặc định.

Vì thế:

- **Lỗi DB tạm thời:** có thể được requeue nếu không có retry/recoverer chỉ định khác.
- **Lỗi JSON fatal:** thường bị reject **không requeue** theo chiến lược mặc định.
- **Lỗi do application chủ động ném AmqpRejectAndDontRequeueException:** yêu cầu reject không requeue.
- **Lỗi do application ném ImmediateRequeueAmqpException:** yêu cầu requeue theo cơ chế hỗ trợ.

**Requeue=true không phải delayed retry**: message có thể được giao lại rất nhanh và tạo poison-message loop nếu thất bại liên tục.

### 3.3. Tự mở rộng FatalExceptionStrategy

Bạn có thể muốn coi **InvalidOrderEventException** là lỗi vĩnh viễn, trong khi lỗi kết nối database có thể thử lại. Một hướng an toàn là **mở rộng DefaultExceptionStrategy**, giữ nguyên các lỗi fatal mặc định:

~~~java
import org.springframework.amqp.rabbit.listener.ConditionalRejectingErrorHandler;

public class OrderFatalExceptionStrategy
        extends ConditionalRejectingErrorHandler.DefaultExceptionStrategy {

    @Override
    protected boolean isUserCauseFatal(Throwable cause) {
        return cause instanceof InvalidOrderEventException
                || super.isUserCauseFatal(cause);
    }
}
~~~

**InvalidOrderEventException** là exception nghiệp vụ do ứng dụng định nghĩa:

~~~java
public class InvalidOrderEventException extends RuntimeException {
    public InvalidOrderEventException(String message) {
        super(message);
    }
}
~~~

Khi khởi tạo container factory, cung cấp strategy cho container error handler:

~~~java
factory.setErrorHandler(
        new ConditionalRejectingErrorHandler(
                new OrderFatalExceptionStrategy()));
~~~

**Không viết FatalExceptionStrategy để đánh dấu mọi exception là fatal** nếu hệ thống có lỗi mạng/DB tạm thời: bạn có thể reject rồi làm mất cơ hội retry một công việc hợp lệ.

### 3.4. x-death và discardFatalsWithXDeath

RabbitMQ có thể thêm **x-death** khi message đã đi qua dead-letter flow. Một topology dùng TTL + DLX đưa message từ retry queue về work queue có thể khiến **message lỗi vĩnh viễn chạy vòng lặp**.

**ConditionalRejectingErrorHandler** có tùy chọn **discardFatalsWithXDeath**. Trong các phiên bản có tính năng này, mặc định một message **đã có x-death và lại bị coi là fatal** có thể được **log rồi discard**, để chặn chu kỳ DLQ/retry vô tận.

~~~java
ConditionalRejectingErrorHandler errorHandler =
        new ConditionalRejectingErrorHandler();
errorHandler.setDiscardFatalsWithXDeath(true);
factory.setErrorHandler(errorHandler);
~~~

**Cảnh báo:** discard không tương đương “chắc chắn được giữ lại trong DLQ”. Nếu việc giữ forensic record là bắt buộc, hãy thiết kế **parking queue, audit storage hoặc quy trình cách ly riêng**, theo dõi metric discard và kiểm thử thực tế với đúng RabbitMQ/Spring AMQP version. Chỉ tắt cơ chế này khi đã có cách chặn vòng lặp khác.

### 3.5. Fatal error khi ackMode=MANUAL

Một số lỗi conversion xảy ra **trước khi listener được gọi**, nên với **MANUAL** ứng dụng không có cơ hội basicAck/basicNack. Để tránh message treo unacked, các phiên bản Spring AMQP hiện đại mặc định **reject fatal message ngay cả trong MANUAL** (tùy chọn **rejectManual=true**).

~~~java
ConditionalRejectingErrorHandler errorHandler =
        new ConditionalRejectingErrorHandler();
errorHandler.setRejectManual(true);
factory.setErrorHandler(errorHandler);
~~~

**Không hiểu điều này là Spring tự quản lý mọi ACK của MANUAL.** Với những message đã vào listener thành công, ứng dụng vẫn chịu trách nhiệm xác nhận theo chế độ MANUAL. **setRejectManual(false)** có thể để lại những delivery fatal trong trạng thái unacked; cần hiểu kỹ trước khi chỉnh.

## 4. RabbitListenerErrorHandler: xử lý lỗi gần method

Interface **RabbitListenerErrorHandler** cho phép endpoint **@RabbitListener** gắn handler lỗi theo tên bean.

~~~java
@RabbitListener(
        queues = "orders.created.work",
        containerFactory = "ordersListenerFactory",
        errorHandler = "orderEndpointErrorHandler")
public void onOrder(OrderCreated event) {
    // ...
}
~~~

Đây **không phải** tên bean container factory hay một thuộc tính trong MessageConverter. Handler chỉ áp dụng cho endpoint được chỉ định.

### 4.1. Chữ ký API khác nhau theo phiên bản

Trong các nhánh cũ, chữ ký interface gồm ba tham số:

~~~java
Object handleError(
        org.springframework.amqp.core.Message rawMessage,
        org.springframework.messaging.Message<?> convertedMessage,
        ListenerExecutionFailedException exception)
        throws Exception;
~~~

Từ **Spring AMQP 3.1.3**, API còn cung cấp **Channel**. Trong **Spring AMQP 3.2.x**, chữ ký abstract được dùng với **bốn tham số**:

~~~java
Object handleError(
        org.springframework.amqp.core.Message rawMessage,
        com.rabbitmq.client.Channel channel,
        org.springframework.messaging.Message<?> convertedMessage,
        ListenerExecutionFailedException exception)
        throws Exception;
~~~

Vì vậy **lambda ba tham số từ ví dụ cũ có thể không compile với 3.2.x**. Bài này chọn **Spring AMQP 3.2.x** cho ví dụ đầy đủ dưới đây; nếu codebase là 3.0/3.1 hoặc 4.x, đối chiếu **RabbitListenerErrorHandler** của phiên bản đang dùng.

### 4.2. Ý nghĩa từng tham số

| Tham số | Kiểu | Cần lưu ý |
| --- | --- | --- |
| **rawMessage** | org.springframework.amqp.core.Message | Body byte[], AMQP properties và metadata nhận; có thể chưa giải mã được |
| **channel** | com.rabbitmq.client.Channel | Dùng khi cần thao tác manual ack/nack rất có kiểm soát |
| **convertedMessage** | org.springframework.messaging.Message&lt;?&gt; | Có thể **null** nếu conversion thất bại trước khi tạo Spring Messaging Message |
| **exception** | ListenerExecutionFailedException | Wrapper chứa nguyên nhân; có thể lấy **getCause()** và thông tin message thất bại |

Kể từ các bản vá **Spring AMQP 2.2.18**, trường hợp converter lỗi trong annotated listener adapter có thể vẫn gọi **RabbitListenerErrorHandler** với **convertedMessage=null**. Vì vậy code trong handler **phải kiểm tra null** trước khi gọi getPayload()/getHeaders().

**Không mặc định mọi lỗi trước method đều đi qua handler endpoint**: lỗi ở tầng container, connection, khai báo queue, hoặc điểm xử lý trước adapter có thể được xử lý khác.

### 4.3. Return khác throw như thế nào?

| Hành động của RabbitListenerErrorHandler | Tác động |
| --- | --- |
| **return một object** | Adapter xem là kết quả xử lý; nếu có **replyTo/@SendTo**, có thể gửi như reply |
| **return null** | Thường không có reply; nếu adapter hoàn tất bình thường, container có thể ACK trong AUTO |
| **throw exception gốc** | Lỗi tiếp tục ra container; container ErrorHandler/retry policy có thể quyết định reject/requeue |
| **throw AmqpRejectAndDontRequeueException** | Báo hiệu không requeue để đi DLQ nếu cấu hình |
| **throw ImmediateRequeueAmqpException** | Yêu cầu requeue theo semantics hỗ trợ |
| **Log rồi return khi nghiệp vụ chưa xong** | Rủi ro **ACK nhầm** và mất cơ hội retry |

**Trả về ErrorResponse không phải thao tác dead-letter.** Trong request/reply, response sẽ được gửi qua reply route phù hợp. Với listener một chiều không có reply destination, một object trả về có thể gây lỗi không xác định được reply destination; nếu muốn xác nhận một event đã được xử lý theo hướng khác, cần ghi bền vững kết quả trước khi return.

## 5. Ví dụ Spring Boot hoàn chỉnh: hai tầng handler

Giả sử Order Service phát sự kiện **OrderCreated**, Audit Service ghi projection từ queue **orders.created.work**. Nếu payload sai contract, message cần cách ly; nếu database tạm lỗi, ứng dụng cần retry có giới hạn.

Các ví dụ dùng **Java 17**, **Spring Boot 3.x** (nhánh phù hợp với **Spring AMQP 3.2.x**) và RabbitMQ AMQP 0.9.1. Cần **spring-boot-starter-amqp** cùng Jackson JSON trên classpath và vhost/user có quyền tương ứng.

### 5.1. DTO và exception nghiệp vụ

~~~java
package com.example.orders;

public record OrderCreated(
        String eventId,
        String orderId,
        long totalAmount) {
}
~~~

Exception **InvalidOrderEventException** được định nghĩa ở mục 3.3, dùng khi DTO parse được nhưng vi phạm contract.

### 5.2. Exchange, queue, binding và DLQ

~~~java
package com.example.orders;

import org.springframework.amqp.core.*;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrderTopology {
    @Bean
    TopicExchange ordersExchange() {
        return new TopicExchange("orders.events", true, false);
    }

    @Bean
    DirectExchange ordersDlx() {
        return new DirectExchange("orders.dlx", true, false);
    }

    @Bean
    Queue ordersWorkQueue() {
        return QueueBuilder.durable("orders.created.work")
                .deadLetterExchange("orders.dlx")
                .deadLetterRoutingKey("order.created.failed")
                .build();
    }

    @Bean
    Queue ordersDlq() {
        return QueueBuilder.durable("orders.created.dlq").build();
    }

    @Bean
    Binding workBinding(
            @Qualifier("ordersWorkQueue") Queue queue,
            TopicExchange ordersExchange) {
        return BindingBuilder.bind(queue)
                .to(ordersExchange)
                .with("order.created");
    }

    @Bean
    Binding dlqBinding(
            @Qualifier("ordersDlq") Queue queue,
            DirectExchange ordersDlx) {
        return BindingBuilder.bind(queue)
                .to(ordersDlx)
                .with("order.created.failed");
    }
}
~~~

**RabbitAdmin** hoặc công cụ provisioning cần khai báo resources. **Queue durable** và exchange durable là nền tảng, nhưng độ tin cậy publish còn đòi **publisher confirms/mandatory returns**, message persistent và chiến lược retry/outbox thích hợp.

RabbitMQ **dead-letter** khi message bị reject không requeue và queue có DLX/binding tương ứng. Nếu thiếu DLX hoặc không route tới queue đích, message có thể bị loại; hãy kiểm tra topology và giám sát DLQ.

### 5.3. JSON converter và container ErrorHandler

~~~java
package com.example.orders;

import java.util.Map;
import org.springframework.amqp.core.AcknowledgeMode;
import org.springframework.amqp.rabbit.annotation.EnableRabbit;
import org.springframework.amqp.rabbit.config.SimpleRabbitListenerContainerFactory;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.amqp.rabbit.listener.ConditionalRejectingErrorHandler;
import org.springframework.amqp.support.converter.DefaultClassMapper;
import org.springframework.amqp.support.converter.Jackson2JsonMessageConverter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableRabbit
public class OrderListenerConfiguration {

    @Bean
    DefaultClassMapper orderClassMapper() {
        DefaultClassMapper mapper = new DefaultClassMapper();
        mapper.setIdClassMapping(
                Map.of("order.created.v1", OrderCreated.class));
        mapper.setTrustedPackages("com.example.orders");
        return mapper;
    }

    @Bean
    Jackson2JsonMessageConverter orderJsonConverter(
            DefaultClassMapper orderClassMapper) {
        Jackson2JsonMessageConverter converter =
                new Jackson2JsonMessageConverter();
        converter.setClassMapper(orderClassMapper);
        return converter;
    }

    @Bean
    SimpleRabbitListenerContainerFactory ordersListenerFactory(
            ConnectionFactory connectionFactory,
            Jackson2JsonMessageConverter orderJsonConverter) {
        SimpleRabbitListenerContainerFactory factory =
                new SimpleRabbitListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setMessageConverter(orderJsonConverter);
        factory.setConcurrentConsumers(2);
        factory.setPrefetchCount(10);
        factory.setAcknowledgeMode(AcknowledgeMode.AUTO);
        factory.setDefaultRequeueRejected(false);
        factory.setErrorHandler(
                new ConditionalRejectingErrorHandler(
                        new OrderFatalExceptionStrategy()));
        return factory;
    }
}
~~~

**Giải thích:**

- **setErrorHandler(...)** đặt handler ở **container** cho những listener dùng factory này.
- **ConditionalRejectingErrorHandler** phân loại lỗi fatal và chuyển thành reject không requeue khi thích hợp.
- **setDefaultRequeueRejected(false)** là lựa chọn demo để những lỗi không được phục hồi không chạy requeue loop; với transient DB error phải bổ sung retry có giới hạn trước khi rơi vào DLQ.
- **AcknowledgeMode.AUTO** cho phép container gửi ACK sau khi xử lý thành công; nếu endpoint error handler ném lỗi tiếp, container xử lý thất bại theo policy.
- **DefaultClassMapper** dùng alias ổn định, hạn chế trusted packages. Đây là bảo vệ type resolution, **không thay thế validation payload**.
- Các cấu hình Spring Boot auto-configured factory có thể không được áp dụng tự động nếu bạn tạo factory riêng như ở đây.

### 5.4. RabbitListenerErrorHandler gắn vào endpoint

~~~java
package com.example.orders;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.amqp.AmqpRejectAndDontRequeueException;
import org.springframework.amqp.rabbit.listener.api.RabbitListenerErrorHandler;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrderEndpointErrorConfiguration {
    private static final Logger log =
            LoggerFactory.getLogger(OrderEndpointErrorConfiguration.class);

    @Bean
    RabbitListenerErrorHandler orderEndpointErrorHandler() {
        // Spring AMQP 3.2.x: lambda có bốn tham số.
        return (rawMessage, channel, convertedMessage, exception) -> {
            String eventId = rawMessage.getMessageProperties().getMessageId();
            Throwable cause = exception.getCause();

            log.warn("Order listener failed eventId={} cause={}",
                    eventId,
                    cause == null ? "unknown" : cause.getClass().getSimpleName());

            if (convertedMessage == null) {
                log.warn("Converted Spring message unavailable: "
                        + "possibly a conversion failure");
            }

            if (cause instanceof InvalidOrderEventException) {
                throw new AmqpRejectAndDontRequeueException(
                        "Invalid OrderCreated event: " + eventId, exception);
            }

            // Transient/unknown error: container + retry policy xử lý.
            throw exception;
        };
    }
}
~~~

**Không ghi toàn bộ rawMessage.getBody() vào log** nếu message có thông tin nhạy cảm. Trong các lỗi đặc biệt, rawMessage/metadata cũng cần được kiểm tra an toàn trước khi dùng; không để logic log gây ra exception mới che khuất lỗi gốc.

Với **exception** được gói qua nhiều lớp, kiểm tra **getCause()** có thể chưa đủ để xác định root cause. Production nên có utility phân tích cause chain và chiến lược phân loại ổn định, nhưng không dựa vào nội dung **exception.getMessage()** không có cấu trúc để quyết định tài chính/giao dịch.

### 5.5. Listener và producer

~~~java
package com.example.orders;

import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class OrderConsumer {
    private final OrderProjectionService projectionService;

    public OrderConsumer(OrderProjectionService projectionService) {
        this.projectionService = projectionService;
    }

    @RabbitListener(
            id = "orders-created-listener",
            queues = "orders.created.work",
            containerFactory = "ordersListenerFactory",
            errorHandler = "orderEndpointErrorHandler")
    public void handle(OrderCreated event) {
        if (event.eventId() == null || event.eventId().isBlank()
                || event.orderId() == null || event.totalAmount() < 0) {
            throw new InvalidOrderEventException(
                    "Missing event fields or invalid amount");
        }
        projectionService.applyIdempotently(event);
    }
}
~~~

~~~java
package com.example.orders;

import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.amqp.support.converter.Jackson2JsonMessageConverter;
import org.springframework.stereotype.Service;

@Service
public class OrderPublisher {
    private final RabbitTemplate rabbitTemplate;

    public OrderPublisher(ConnectionFactory connectionFactory,
                          Jackson2JsonMessageConverter converter) {
        this.rabbitTemplate = new RabbitTemplate(connectionFactory);
        this.rabbitTemplate.setMessageConverter(converter);
    }

    public void publish(OrderCreated event) {
        rabbitTemplate.convertAndSend(
                "orders.events", "order.created", event,
                message -> {
                    message.getMessageProperties().setMessageId(event.eventId());
                    return message;
                });
    }
}
~~~

Ví dụ cố tình dùng một converter chung để producer gắn **__TypeId__=order.created.v1** và consumer hiểu DTO cùng alias. Với các service độc lập, từng service có thể ánh xạ cùng alias sang class Java nội bộ tương ứng.

**OrderProjectionService** là dependency nghiệp vụ phải do ứng dụng cài đặt, chịu trách nhiệm transaction/idempotency. Không coi snippet là hệ thống production đầy đủ nếu chưa thêm publisher confirms, outbox, retry hữu hạn, TLS/secret và giám sát.

### 5.6. Kiểm chứng đường đi của ba tình huống

| Tình huống | Điểm lỗi | RabbitListenerErrorHandler | Container ErrorHandler / ACK |
| --- | --- | --- | --- |
| Event hợp lệ, DB ghi xong | Không có | Không chạy | Container AUTO ACK |
| DTO hợp lệ nhưng totalAmount âm | Listener throw InvalidOrderEventException | Ghi log, ném reject không requeue | Container xử lý reject; broker DLX nếu có |
| JSON không giải mã được | Converter/adapter trước method | **Có thể** gọi với convertedMessage null | Nếu lỗi vẫn propagate: default fatal classification, reject không requeue |
| DB timeout | Listener/service throw | Ghi log, ném tiếp | Theo retry policy; trong config demo defaultRequeueRejected=false nên reject sau khi không được phục hồi |
| Mất connection trước broker nhận ACK | Sau khi handler thành công | Không nhất thiết chạy | RabbitMQ có thể redeliver; idempotency bảo vệ DB |

**Container ErrorHandler không phải lớp “luôn ghi log cuối cùng”** nếu lỗi đã được endpoint handler xử lý hoàn toàn bằng return, hoặc bị retry advice/recoverer hấp thụ theo một chính sách khác.

## 6. Khi RabbitListenerErrorHandler trả ErrorResponse

Một tình huống riêng là **request/reply qua RabbitMQ**. Consumer nhận request, validate và trả reply; nếu validation thất bại, thay vì để sender timeout, endpoint có thể trả **ErrorResponse** đã chuẩn hóa.

~~~java
package com.example.orders;

public record ValidationErrorResponse(
        String code,
        String message,
        String correlationId) {
}
~~~

~~~java
@Bean
RabbitListenerErrorHandler validationReplyErrorHandler() {
    return (raw, channel, converted, ex) ->
            new ValidationErrorResponse(
                    "INVALID_ORDER",
                    "Request could not be processed",
                    raw.getMessageProperties().getCorrelationId());
}
~~~

~~~java
@RabbitListener(
        queues = "orders.validation.requests",
        errorHandler = "validationReplyErrorHandler")
public OrderValidationResponse validate(OrderValidationRequest request) {
    return orderValidationService.validate(request);
}
~~~

Ví dụ này **giả định** queue request, DTO **OrderValidationRequest/OrderValidationResponse**, reply-to và converter phù hợp đã được cấu hình. Để reply JSON đúng, cần bảo đảm listener reply converter có thể serialize **ValidationErrorResponse** và sender nhận được response theo hợp đồng request/reply.

Nếu **RabbitListenerErrorHandler trả một ErrorResponse**, exception **có thể được xem là đã xử lý** và container ACK trong AUTO. Đó là hành vi có chủ đích khi consumer thực sự đã trả lời yêu cầu **“invalid request”**; không nên dùng cùng cách cho một event one-way bị lỗi DB mà vẫn cần retry.

### 6.1. returnExceptions=true không phải lựa chọn mặc định nên bật

**@RabbitListener(returnExceptions="true")** hỗ trợ gửi exception về sender trong request/reply theo cơ chế **RemoteInvocationResult** và adapter. Cơ chế này truyền exception qua serialization, thường phù hợp hơn với **SimpleMessageConverter** trong một hệ thống Java được tin cậy; **không phù hợp để gửi exception tùy ý qua JSON**.

Trong hệ thống nhiều ngôn ngữ/service, thường nên trả về **error DTO** có code/message không nhạy cảm, phân biệt lỗi nghiệp vụ và lỗi hạ tầng, thay vì serialize exception/stack trace nội bộ qua broker.

**Không nhầm với DLQ:** returnExceptions trả thông tin cho caller; **không tự chuyển request lỗi sang dead-letter queue**.

## 7. Khi nào cần retry interceptor thay vì ErrorHandler?

**ErrorHandler là nơi phân loại/phản ứng khi lỗi xảy ra**, không phải một scheduler retry có backoff tự động.

Một bài toán thực tế có hai nhóm:

- **Permanent:** JSON sai, schemaVersion không hỗ trợ, tenant/account không hợp lệ, tham số thiếu. Retry cùng message nhiều lần không giúp.
- **Transient:** database tạm không sẵn sàng, timeout API ngoài, connection pool cạn, service phụ thuộc chập chờn. Cần retry **hữu hạn**, delay/backoff và quan sát.

Với listener container, Spring Retry có **RetryOperationsInterceptor** và các recoverer. Ví dụ cấu hình có thể thêm advice chain:

~~~java
import org.springframework.amqp.rabbit.config.RetryInterceptorBuilder;
import org.springframework.amqp.rabbit.retry.RejectAndDontRequeueRecoverer;

factory.setAdviceChain(
        RetryInterceptorBuilder.stateless()
                .maxAttempts(3)
                .backOffOptions(500L, 2.0, 3_000L)
                .recoverer(new RejectAndDontRequeueRecoverer())
                .build());
~~~

Đây là **đoạn cấu hình bổ sung** cho factory ở mục 5.3, cần **Spring Retry** trên classpath và dùng API tương thích. **maxAttempts(3)** bao gồm lần đầu; khi thất bại sau các lượt retry, recoverer ném reject không requeue để có thể tới DLQ.

**Thứ tự advice/recoverer/error handler và việc error handler endpoint ném loại exception nào** ảnh hưởng retry thực tế. Nếu nghiệp vụ đánh dấu một event là permanent trước khi đến retry advice, không nên tiếp tục retry nó chỉ vì interceptor đặt chung một chính sách rộng. Để phân loại chính xác, dùng RetryPolicy chọn exception hoặc tách flow permanent/transient theo contract.

### 7.1. Retry đồng bộ khác retry qua broker

| Phương án | Diễn ra ở đâu? | Ưu điểm | Giới hạn |
| --- | --- | --- | --- |
| **Stateless retry interceptor** | Trong lần xử lý listener | Dễ triển khai, retry lỗi tạm thời nhanh | Giữ thread/consumer, không thay message body |
| **Broker requeue ngay** | RabbitMQ giao lại sau reject | Không phải tự lên lịch | Dễ tạo hot loop, không có backoff mặc định |
| **TTL + DLX retry queue** | Queue riêng với TTL rồi quay lại main queue | Có khoảng chờ broker-side | Cần chống vòng lặp, quản lý x-death/retention |
| **Ứng dụng ghi job lỗi rồi ACK** | Database/job scheduler bền vững | Kiểm soát chính sách và delay | Chỉ ACK sau khi **job đã được lưu bền** |
| **Quarantine/DLQ** | Queue riêng giữ poison messages | Hỗ trợ điều tra và replay | Không tự sửa payload, cần vận hành |

**Không dùng ErrorHandler chỉ để log rồi return** nếu mục tiêu thực sự là retry. Muốn container biết message thất bại, phải ném lỗi phù hợp hoặc đưa trách nhiệm xử lý vào một storage bền vững trước khi xác nhận.

### 7.2. ErrorHandler không tự động xóa toàn bộ nguy cơ duplicate

Trong **AcknowledgeMode.AUTO**, nếu DB commit xong nhưng ACK chưa đến RabbitMQ, message có thể redeliver. Nếu publisher đã retry vì mất confirm, có thể còn có **hai lần publish của cùng event**. Hai hiện tượng khác nhau nhưng đều khiến consumer nhìn thấy cùng eventId nhiều lần.

Thiết kế consumer nên idempotent bất kể đã cấu hình handler và DLQ tốt đến đâu.

## 8. ACK/NACK khi có ErrorHandler: AUTO, MANUAL, NONE

| Chế độ | Khi endpoint handler return bình thường | Khi exception tiếp tục ra container |
| --- | --- | --- |
| **AUTO** | Container có thể ACK theo policy; không có nghĩa DB đã commit nếu code xử lý sai | ErrorHandler/retry/recoverer chi phối reject/requeue |
| **MANUAL** | **Ứng dụng vẫn phải ACK/NACK** nếu chưa có cơ chế phù hợp xác nhận | Các lỗi fatal trước method có thể được container reject theo **rejectManual**; lỗi nghiệp vụ cần quản lý tag cẩn thận |
| **NONE** | Broker auto-ack khi giao delivery, không chờ handler | Không dựa vào broker để redeliver message đã auto-ack |

### 8.1. Ví dụ MANUAL với Channel

Trong Spring AMQP 3.2.x, RabbitListenerErrorHandler nhận **Channel** ở tham số thứ hai. Nếu dùng MANUAL, có thể quyết định NACK ở handler, nhưng phải tránh double ack/nack.

~~~java
@Bean
RabbitListenerErrorHandler manualRejectingErrorHandler() {
    return (raw, channel, converted, exception) -> {
        long tag = raw.getMessageProperties().getDeliveryTag();

        // Chỉ minh họa một nhánh reject có chủ đích.
        // Cần đảm bảo tag chưa ACK/NACK trước đó.
        channel.basicReject(tag, false);
        return null;
    };
}
~~~

**Không nên copy nguyên ví dụ này lên production mà không kiểm tra trạng thái ACK.** Khi convertedMessage null hoặc lỗi xảy ra trước method, broker/container có thể có policy riêng. Manual reject phải dùng **đúng channel và deliveryTag**, xử lý IOException, đồng thời bảo đảm không có tầng khác ACK/NACK cùng delivery.

Nếu mục tiêu chỉ là **không requeue lỗi vĩnh viễn** ở chế độ AUTO, **throw AmqpRejectAndDontRequeueException** thường rõ ràng và ít rủi ro hơn tự gọi Channel trong endpoint handler.

### 8.2. Các loại exception điều khiển flow

| Exception | Ý nghĩa chính |
| --- | --- |
| **AmqpRejectAndDontRequeueException** | Yêu cầu message bị reject không requeue |
| **ImmediateRequeueAmqpException** | Yêu cầu requeue theo container semantics |
| **ImmediateAcknowledgeAmqpException** | Chỉ thị xử lý acknowledgement đặc biệt; không dùng để giấu lỗi chưa xử lý |
| **ListenerExecutionFailedException** | Wrapper ghi nhận lỗi xử lý listener, có thông tin failed message |
| **MessageConversionException** | Lỗi giải mã message theo converter |
| **MethodArgumentNotValidException** | Lỗi validation argument trước khi method thực thi |

Lớp exception **không tự sinh DLQ**: RabbitMQ chỉ dead-letter theo trigger và topology được cấu hình; nếu missing DLX/binding, message có thể bị loại.

## 9. Fatal errors và x-death: tránh vòng lặp DLQ

Giả sử một worker nhận message sai JSON và bị dead-letter vào **orders.created.dlq**. Operator hoặc một retry policy tự động đẩy message đó lại work queue. Lỗi giống hệt xảy ra lần thứ hai.

~~~text
orders.created.work
    │ [fatal conversion]
    ▼
orders.dlx → orders.created.dlq
    │ [replay/TTL retry]
    ▼
orders.created.work
    │ [same fatal conversion]
    ▼
... vòng lặp nếu không có giới hạn ...
~~~

Nếu message đã có **x-death** và lỗi lại được phân loại fatal, **ConditionalRejectingErrorHandler** có thể áp chính sách **discardFatalsWithXDeath**. Điều này là **chống vòng lặp**, nhưng không thay cho quy trình cách ly an toàn.

Một thiết kế vận hành chặt chẽ cần:

1. **Lưu raw message/metadata có kiểm soát**, không rò dữ liệu nhạy cảm.
2. **Theo dõi lý do DLX**, queue gốc và lần retry; lưu eventId/correlationId khi có.
3. **Đặt giới hạn số lượt retry** và xác định điểm chuyển parking queue.
4. **Không đẩy lại vô hạn tự động** khi schema chưa được consumer hỗ trợ.
5. **Không để việc discard xảy ra âm thầm** đối với các sự kiện nghiệp vụ quan trọng; có metric/cảnh báo và audit theo chính sách bảo mật.

### x-death không phải số lần xử lý nghiệp vụ chính xác

Header x-death mô tả lịch sử **dead-lettering** của message theo RabbitMQ. Nó **không đếm mọi lần retry nội bộ** của Spring Retry interceptor và **không đếm mọi duplicate do publisher publish lại**.

Nếu muốn biết một event đã xử lý bao nhiêu lần, cần định nghĩa và lưu **attemptId/attemptCount** ở nơi quản lý retry phù hợp thay vì suy ra chỉ từ x-death.

## 10. Idempotency: ErrorHandler không tạo exactly-once

Tưởng tượng hai sự cố:

~~~text
A. Publisher gửi OrderCreated(eventId=e-101), mất confirm rồi gửi lại.
   Broker có thể chứa hai message cùng eventId.

B. Consumer ghi database thành công, nhưng connection mất trước ACK.
   RabbitMQ có thể giao lại delivery cũ.
~~~

Một handler lỗi dù tốt cũng **không ngăn tự động** hai khả năng trên. Consumer cần xác định một event đã có tác động nghiệp vụ trước đó hay chưa.

### 10.1. Transactional deduplication

Ví dụ PostgreSQL:

~~~sql
CREATE TABLE processed_events (
    consumer_name VARCHAR(100) NOT NULL,
    event_id VARCHAR(100) NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (consumer_name, event_id)
);
~~~

~~~java
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderProjectionService {
    private final JdbcTemplate jdbcTemplate;
    private final OrderProjectionRepository repository;

    public OrderProjectionService(
            JdbcTemplate jdbcTemplate,
            OrderProjectionRepository repository) {
        this.jdbcTemplate = jdbcTemplate;
        this.repository = repository;
    }

    @Transactional
    public void applyIdempotently(OrderCreated event) {
        int inserted = jdbcTemplate.update(
            """
            INSERT INTO processed_events (consumer_name, event_id)
            VALUES (?, ?)
            ON CONFLICT DO NOTHING
            """,
            "order-projection", event.eventId());

        if (inserted == 0) {
            return; // Duplicate, không thực hiện tác động lần hai.
        }

        repository.apply(event);
        // Cùng DB transaction với processed_events.
    }
}
~~~

**OrderProjectionRepository** là repository do ứng dụng triển khai. Cần đảm bảo cùng transaction manager/database và transaction thực sự commit trước khi listener trả bình thường. Nếu ghi projection lỗi, transaction phải rollback cả processed_events.

Với tác động ngoài DB như gửi email/thanh toán, nên dùng **notification outbox**, provider idempotency key và reconciliation; một DB transaction cục bộ không thể rollback email đã được gửi.

### 10.2. Retry phải giữ eventId cố định

Nếu producer gặp timeout confirm và thử lại, **không sinh eventId mới** cho cùng event. Dùng eventId ổn định từ bản ghi outbox gốc, CorrelationData/attemptId riêng cho mỗi lần publish và metric duplicate ở consumer.

**redelivered=false không chứng minh chưa xử lý**: bản sao do publisher retry là một publish mới và có thể được giao lần đầu với flag false.

## 11. Xử lý lỗi có transaction và async listener

### 11.1. Transaction database và container ACK

Trong mô hình thông thường:

~~~text
Delivery
  → @RabbitListener gọi service
  → service mở DB transaction
  → ghi projection + processed_events
  → COMMIT
  → service return, listener return
  → container ACK theo policy
~~~

Nếu DB rollback, exception cần đi ra để container biết xử lý thất bại. Nếu code catch exception rồi return **không có kế hoạch phục hồi bền vững**, container AUTO có thể ACK nhầm.

Nếu **channelTransacted=true**, broker còn cần commit AMQP channel; đó **không phải** distributed transaction nguyên tử giữa RabbitMQ và database.

### 11.2. Async return types

Với **@RabbitListener** trả **CompletableFuture** hoặc **Mono**, Spring AMQP hiện đại hỗ trợ điều phối ACK theo **async completion**, thường yêu cầu MANUAL mode được container xử lý phù hợp. Từ Spring AMQP 3.0.5, **RabbitListenerErrorHandler** còn được tích hợp cho một số luồng async failure; hành vi cụ thể phải đối chiếu version.

**Không return một CompletableFuture đã complete trong khi việc thật tiếp tục ở background** rồi cho rằng ACK sẽ đợi công việc. Future phải đại diện cho **toàn bộ kết quả cần xác nhận**.

Khi async error handler được gọi, cần đặc biệt chú ý reply, exception completion và cách ACK/NACK. Không viết error handler sync/async giả định giống hệt nhau ở mọi phiên bản.

## 12. Observability: theo dõi cả lỗi và kết quả thực tế

Chỉ log stack trace trong ErrorHandler là không đủ. Nên quan sát ít nhất:

| Metric/log | Ý nghĩa |
| --- | --- |
| **listener_error_total** theo exception class | Lỗi phát sinh từ handler/adapter |
| **conversion_error_total** | Poison JSON, type headers/schema không khớp |
| **fatal_reject_total** | Lỗi bị reject không requeue |
| **requeue_total / redeliver rate** | Dấu hiệu retry nóng hoặc connection gián đoạn |
| **retry_attempt_total** | Số lần retry nội bộ ứng dụng, khác x-death |
| **dlq_messages_ready** | Backlog lỗi cần điều tra |
| **fatal_discard_with_xdeath_total** | Message bị discard bởi chiến lược chống vòng lặp |
| **queue_unacked** | Delivery đã giao nhưng chưa ACK; quan trọng với MANUAL |
| **handler_duration_p95/p99** | Độ trễ xử lý nghiệp vụ |
| **duplicate_event_total** | EventId đã có trong processed_events |
| **publisher_confirm_nack / returns** | Lỗi phía phát, độc lập với consumer error handler |

Log hữu ích nên có **eventId**, **correlationId**, **queue**, **routing key**, **consumer id**, **exception category**, **attemptNo**, **decision=ACK/REQUEUE/DLX/DISCARD**. Không log raw payload hoặc credentials có dữ liệu nhạy cảm.

**ErrorHandler chỉ biết exception trong quá trình xử lý; nó không chứng minh publisher đã route message hoặc external API đã hoàn tất.** Kết hợp RabbitMQ Management/Micrometer Observation với DB và trạng thái nghiệp vụ.

## 13. Những lỗi cấu hình phổ biến

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Đã cấu hình errorHandler trên @RabbitListener nhưng factory không thay đổi | Nhầm **RabbitListenerErrorHandler** với **container ErrorHandler** | Chọn đúng API: annotation hoặc factory.setErrorHandler |
| Handler endpoint không được gọi | Sai bean name, chưa bật annotation infrastructure, lỗi xảy ra ngoài adapter | Kiểm tra id, bean, converter, log container |
| Handler lambda không compile | Dùng signature 3 tham số trên API có 4 tham số | Kiểm tra Spring AMQP version và interface |
| NullPointerException trong error handler | **convertedMessage=null** khi lỗi conversion | Kiểm tra null; đọc rawMessage an toàn |
| Error DTO return nhưng không có reply | Listener một chiều, thiếu replyTo/@SendTo | Chỉ trả DTO trong request/reply đã cấu hình |
| Lỗi nghiệp vụ nhưng broker ACK | Handler catch + return, recoverer coi lỗi handled | Propagate exception hoặc ghi bền trách nhiệm trước return |
| JSON lỗi bị requeue liên tục | Không có fatal policy phù hợp hoặc custom handler thay mặc định | Dùng ConditionalRejectingErrorHandler và DLQ |
| DB timeout bị đưa DLQ ngay | defaultRequeueRejected=false nhưng không có bounded retry | Thêm retry interceptor/policy cho lỗi tạm thời |
| Message vào DLQ rồi biến mất ở lần phát lại | discardFatalsWithXDeath của handler | Quan sát discard và thiết kế parking queue |
| Message treo unacked ở MANUAL | Quên ACK/NACK hoặc rejectManual bị thay đổi | Kiểm tra channel/tag, fatal before method, mode |
| Duplicate sau reconnect | ACK thất lạc hoặc publisher retry | Idempotency theo eventId, unique constraint |
| DLQ không nhận message bị reject | Thiếu DLX, binding hoặc quyền | Kiểm tra RabbitMQ topology và queue type |
| Retry count không khớp x-death | Retry nội bộ không dead-letter | Theo dõi attempt riêng |
| Log quá nhiều payload nhạy cảm | ErrorHandler log toàn body/headers | Redact, sampling, RBAC, retention phù hợp |
| Bật returnExceptions khi dùng JSON | Java exception không JSON-friendly | Error DTO ổn định hoặc propagate tới container |

### Quy trình chẩn đoán theo tầng

1. **Xác định nguồn lỗi:** connection/container, message conversion, method argument, nghiệp vụ hay reply generation?
2. **Kiểm tra handler được gọi:** RabbitListenerErrorHandler của endpoint hay container ErrorHandler?
3. **Xem exception thật và cause chain:** ListenerExecutionFailedException có bọc nguyên nhân gì?
4. **Kiểm tra mode ACK:** AUTO/MANUAL/NONE, defaultRequeueRejected, rejectManual và action đã gọi.
5. **Kiểm tra policy retry:** advice chain/recoverer có return bình thường hay throw tiếp không?
6. **Kiểm tra broker:** queue ready/unacked, DLX/DLQ, x-death, redelivery, consumer count.
7. **Kiểm tra nghiệp vụ:** DB đã commit chưa? eventId đã được xử lý? External API có kết quả bất định không?
8. **Thử trên queue test:** thay một yếu tố mỗi lần, quan sát metric và kết quả ACK/DLQ.

## 14. Bài tập thực hành

### Bài 1 — So sánh hai ErrorHandler

Tạo **orders.created.work** với SimpleRabbitListenerContainerFactory và một **@RabbitListener(errorHandler="orderEndpointErrorHandler")**. Cố ý ném InvalidOrderEventException. Log thứ tự endpoint handler và container handler; giải thích khi nào một trong hai không được gọi.

### Bài 2 — JSON sai trước method

Dùng Jackson2JsonMessageConverter, publish một message có **contentType=application/json** nhưng body sai cú pháp. Xác minh listener method chưa chạy. Quan sát **convertedMessage=null** nếu adapter gọi RabbitListenerErrorHandler; đối chiếu container fatal classification và DLQ. Không dùng queue production để thử.

### Bài 3 — Return hay throw?

Tạo hai biến thể endpoint handler: (a) trả null sau khi ghi bền job lỗi; (b) ném AmqpRejectAndDontRequeueException. Với **AUTO**, so sánh kết quả ACK/DLQ. Giải thích vì sao return bình thường nhưng chưa ghi trách nhiệm phục hồi có thể mất công việc.

### Bài 4 — Thay FatalExceptionStrategy

Mở rộng **DefaultExceptionStrategy.isUserCauseFatal** để đánh dấu InvalidOrderEventException, nhưng giữ DB timeout là transient. Kiểm thử payload tổng tiền âm so với database offline và ghi lại đường xử lý từng trường hợp.

### Bài 5 — Retry có giới hạn

Thêm stateless retry interceptor với **maxAttempts=3** và exponential backoff. Mô phỏng DB lỗi hai lần rồi thành công lần ba; quan sát message không vào DLQ. Sau đó để DB lỗi mãi và kiểm tra recoverer dẫn tới reject không requeue.

### Bài 6 — MANUAL và fatal conversion

Đặt **ackMode=MANUAL**, prefetch=3 và truyền poison JSON. Quan sát **rejectManual=true** xử lý lỗi không tới method. Sau đó nhận message hợp lệ nhưng quên ACK, xem RabbitMQ unacked tăng. Giải thích sự khác biệt.

### Bài 7 — x-death và replay

Gửi message lỗi vào DLQ, dùng công cụ test phát lại message còn x-death vào work queue. Quan sát cơ chế chống vòng lặp của ConditionalRejectingErrorHandler. Thiết kế parking queue/audit để không đánh mất dữ liệu cần điều tra.

### Bài 8 — Request/reply ErrorResponse

Dùng @RabbitListener trả reply và RabbitListenerErrorHandler trả **ValidationErrorResponse** khi request sai. Cấu hình reply-to/@SendTo và JSON converter; chứng minh sender nhận error DTO, không nhầm với DLQ hoặc thrown exception serialization.

### Bài 9 — Duplicate do ACK thất lạc

Ghi một eventId vào processed_events cùng transaction nghiệp vụ, sau đó mô phỏng mất connection trước consumer ACK. Khi broker giao lại, xác minh listener bỏ qua tác động trùng rồi ACK bình thường. Giải thích vì sao ErrorHandler tự nó không tạo exactly-once.

### Câu hỏi tự đánh giá

1. **org.springframework.util.ErrorHandler** và **RabbitListenerErrorHandler** khác nhau ở lớp nào?
2. Tại sao lỗi JSON có thể xảy ra trước khi method @RabbitListener chạy?
3. Container mặc định làm gì với một số lỗi fatal conversion?
4. **defaultRequeueRejected=true** có bảo đảm mọi lỗi được requeue không?
5. **convertedMessage=null** trong RabbitListenerErrorHandler có thể xảy ra khi nào?
6. Trong Spring AMQP 3.2.x, RabbitListenerErrorHandler có bao nhiêu tham số?
7. Khi endpoint handler **return ErrorResponse**, broker có tự dead-letter message lỗi không?
8. Vì sao return null từ endpoint handler có thể khiến container AUTO ACK?
9. Ý nghĩa và rủi ro của **discardFatalsWithXDeath** là gì?
10. **rejectManual=true** có làm Spring quản lý mọi ACK của mode MANUAL không?
11. **x-death** có đếm mọi lần RetryOperationsInterceptor retry không?
12. Tại sao cần cùng một DB transaction cho processed_events và tác động nghiệp vụ?
13. Khi nào nên dùng **AmqpRejectAndDontRequeueException** thay vì **ImmediateRequeueAmqpException**?
14. Bật **returnExceptions=true** có phù hợp làm JSON contract giữa microservices không?
15. Cần những metric nào để phân biệt retry loop, conversion error và DB outage?

## 15. Tài liệu tham khảo chính thức

- [Spring AMQP 3.2 — Handling Exceptions for Annotated Listeners](https://docs.spring.io/spring-amqp/reference/3.2/amqp/receiving-messages/async-annotation-driven/error-handling.html): RabbitListenerErrorHandler, returnExceptions, converted message null và reply semantics.
- [Spring AMQP 3.2 — Exception Handling](https://docs.spring.io/spring-amqp/reference/3.2/amqp/exception-handling.html): ConditionalRejectingErrorHandler, fatal exceptions, x-death và rejectManual.
- [Spring AMQP 3.2 API — RabbitListenerErrorHandler](https://docs.spring.io/spring-amqp/docs/3.2.x/api/org/springframework/amqp/rabbit/listener/api/RabbitListenerErrorHandler.html): chữ ký mới nhận Channel trong nhánh 3.2.
- [Spring AMQP 3.2 API — AbstractRabbitListenerContainerFactory](https://docs.spring.io/spring-amqp/docs/3.2.x/api/org/springframework/amqp/rabbit/config/AbstractRabbitListenerContainerFactory.html): setErrorHandler và các thuộc tính container factory.
- [Spring AMQP 3.2 API — ConditionalRejectingErrorHandler](https://docs.spring.io/spring-amqp/docs/3.2.x/api/org/springframework/amqp/rabbit/listener/ConditionalRejectingErrorHandler.html): DefaultExceptionStrategy, rejectManual, discardFatalsWithXDeath.
- [Spring AMQP — Listener Retry](https://docs.spring.io/spring-amqp/reference/amqp/resilience-recovering-from-errors-and-broker-failures.html): retry/recovery và lỗi broker.
- [Spring AMQP — Asynchronous @RabbitListener Return Types](https://docs.spring.io/spring-amqp/reference/amqp/receiving-messages/async-returns.html): async completion và acknowledgement.
- [RabbitMQ — Consumer Acknowledgements and Publisher Confirms](https://www.rabbitmq.com/docs/confirms): ACK/NACK, requeue, publisher confirm.
- [RabbitMQ — Dead Letter Exchanges](https://www.rabbitmq.com/docs/dlx): dead-letter trigger, x-death, định tuyến và chính sách DLX.

---

**Ghi nhớ:** **RabbitListenerErrorHandler** là lớp xử lý lỗi ở **từng @RabbitListener endpoint**: có thể trả reply/đánh dấu lỗi đã xử lý hoặc ném tiếp. **Container ErrorHandler**, thường là **ConditionalRejectingErrorHandler**, xử lý lỗi ở tầng container và phân loại **fatal** để tránh requeue vô hạn. **Return bình thường có thể dẫn tới ACK**, còn **reject không requeue chỉ đi DLQ khi topology hỗ trợ**. Hai handler không thay thế retry policy, DLQ, publisher confirms, transaction hay idempotency. Hãy quản lý lỗi theo tầng, không nuốt lỗi nghiệp vụ chưa hoàn tất và theo dõi cả **redelivery, unacked, DLQ, conversion errors, DB commit và duplicate eventId**.
