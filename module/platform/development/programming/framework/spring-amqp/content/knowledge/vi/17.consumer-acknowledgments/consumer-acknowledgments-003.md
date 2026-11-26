# Thời điểm ack khi listener trả về thành công

## Mục tiêu bài học

Trong **Spring AMQP**, **RabbitTemplate** gửi message đến RabbitMQ qua **exchange**, **routing key** và **binding**; **@RabbitListener** nhận message từ queue để xử lý công việc nền. Để quyết định khi nào RabbitMQ được phép bỏ message khỏi hàng đợi, consumer phải có cơ chế **acknowledgement** (ACK).

Một câu dễ nhớ nhưng **chưa hoàn toàn đủ chính xác** là:

> Với **AcknowledgeMode.AUTO**, Spring AMQP tự ACK khi listener xử lý thành công; nếu listener ném exception, container áp dụng chính sách lỗi thay vì ACK như bình thường.

Điểm then chốt của chủ đề **“Thời điểm ack khi listener trả về thành công”** là xác định **“thành công” nghĩa là gì**, đâu là **điểm ACK có thể được gửi**, và vì sao **method đã return** không đồng nghĩa **broker chắc chắn đã nhận ACK**, càng không đồng nghĩa **nghiệp vụ được thực hiện đúng một lần**.

Sau bài học thuộc chương **Xác nhận tiêu thụ**, bạn có thể:

1. Vẽ timeline **delivery → converter → handler → return → container ACK → broker**.
2. Phân biệt **Spring AUTO**, **MANUAL** và **NONE**, không nhầm AUTO với RabbitMQ auto-ack.
3. Giải thích ảnh hưởng của **exception**, **catch rồi return**, **retry interceptor**, **message conversion** và **error handler** lên quyết định ACK/NACK.
4. Hiểu các trường hợp ACK không phát ngay sau mỗi lời gọi: **SMLC batchSize**, **DMLC messagesPerAck/ackTimeout**, **channel transaction** và **async listener**.
5. Nhận diện “cửa sổ trùng”: database đã commit nhưng consumer mất kết nối trước khi ACK tới broker.
6. Áp dụng **idempotency**, **retry/DLQ**, **prefetch**, **publisher confirms** và metric để xây consumer tin cậy.

## 1. ACK là tín hiệu gì?

Với RabbitMQ AMQP 0.9.1, mỗi delivery chưa được ACK là một công việc broker vẫn coi là **chưa được xác nhận**. Trong chế độ yêu cầu xác nhận, broker gửi message tới consumer cùng **delivery tag** trên channel nhận. Consumer gửi **basic.ack** khi chấp nhận hoàn tất lần delivery.

~~~mermaid
sequenceDiagram
    participant P as Producer / RabbitTemplate
    participant B as RabbitMQ
    participant C as Spring Listener Container
    participant L as @RabbitListener
    P->>B: basic.publish OrderCreated
    B->>C: basic.deliver (deliveryTag=17)
    Note over B: Delivery đang unacked
    C->>L: Convert body và gọi handler
    L-->>C: Return thành công
    C-->>B: basic.ack(deliveryTag=17)
    Note over B: Broker ghi nhận ACK và loại delivery khỏi backlog queue
~~~

**ACK không phải message mới** và không đi qua exchange/binding. Nó là **frame giao thức** gửi trên **chính AMQP channel** đã nhận delivery.

| Khái niệm | Chiều truyền | Xác nhận điều gì? |
| --- | --- | --- |
| **Publisher confirm** | Broker → publisher | Broker chấp nhận một lần publish theo semantics confirm |
| **Consumer ACK** | Consumer/container → broker | Consumer chấp nhận một lần giao message |
| **Commit database** | Ứng dụng → database | Dữ liệu nghiệp vụ đã commit theo transaction DB |
| **HTTP/email/payment outcome** | Hệ thống ngoài → ứng dụng | Một tác động ngoài đã hoặc chưa hoàn tất |
| **CorrelationId / messageId / eventId** | Metadata nghiệp vụ/AMQP | Định danh và truy vết; không tự xác nhận xử lý |

**Publisher confirm và consumer ACK độc lập nhau.** RabbitMQ có thể xác nhận publish từ lâu trong khi consumer vẫn chưa nhận message, hoặc đã nhận nhưng chưa xử lý xong.

### Delivery tag không phải eventId

**deliveryTag** là số định danh **một delivery trên một channel**. Nếu connection đứt và broker giao lại message trên channel mới, deliveryTag sẽ thuộc phạm vi channel mới, không phải khóa cố định của event. Khi ACK/NACK thủ công, phải dùng **đúng channel nhận** và tag của delivery tương ứng.

**eventId** do producer cung cấp nên giữ ổn định qua publisher retry và consumer redelivery. Đây mới là cơ sở phù hợp để chống tác động nghiệp vụ trùng.

## 2. Với Spring AUTO, chính xác khi nào ACK xảy ra?

Chế độ mặc định thông dụng của Spring listener container là **AcknowledgeMode.AUTO**. Trong đường xử lý **đồng bộ thông thường**, container nhận delivery, converter chuyển kiểu message, listener xử lý; nếu quá trình ấy kết thúc **không có lỗi thoát ra ngoài**, container gửi ACK theo cấu hình.

~~~text
T0  RabbitMQ giao OrderCreated cho consumer (deliveryTag=17).
T1  Spring nhận AMQP Message và chuyển body sang OrderCreated DTO.
T2  Spring gọi method @RabbitListener.
T3  Method ghi database, commit thành công, return bình thường.
T4  Container ghi nhận xử lý thành công.
T5  Container phát basic.ack (hoặc gom ACK theo cấu hình batch).
T6  RabbitMQ nhận ACK, message không còn là delivery chưa xác nhận.

  T3 != T5 != T6
~~~

**T3, T5 và T6 là ba thời điểm khác nhau.** Kết quả của listener giúp container **quyết định** ACK; khung ACK vẫn cần được phát qua channel và broker nhận. Không có hợp đồng rằng “dòng return” chính là thời điểm broker đã loại message.

Trong trường hợp mặc định của **SMLC với batchSize=1**, không dùng transaction đặc biệt và listener đồng bộ, ACK thường được gửi cho từng message sau khi handler chạy thành công. Nhưng đó không phải bất biến cho mọi loại container và cấu hình; các trường hợp batch/async được phân tích ở các phần sau.

### 2.1. “Method trả về thành công” được hiểu thế nào?

Spring quan sát **kết quả thực thi của listener adapter/container**, không biết trực tiếp ý nghĩa nghiệp vụ của code:

- Method hoàn thành bình thường, không có exception thoát ra: **thành công** theo cơ chế container.
- Method có kiểu trả về **void** và hoàn thành bình thường: vẫn được xem là thành công.
- Method trả về **null** bình thường: bản thân null không phải tín hiệu NACK.
- Method trả về **một DTO** để tạo reply: việc xử lý reply theo adapter có thể ảnh hưởng thành công tổng thể, tùy cấu hình request/reply.
- Method ném exception ra ngoài: container đi vào luồng xử lý lỗi, retry/reject/requeue theo chính sách.
- Method bắt lỗi rồi **return bình thường**: đối với container, thường là **đã xử lý thành công**, dù nghiệp vụ có thể thất bại.
- Method trả **CompletableFuture/Mono**: nếu dùng cơ chế async được hỗ trợ, ACK liên quan đến **future hoàn tất** chứ không chỉ thời điểm method trả về future.

Vì vậy “thành công” ở đây có nghĩa **không còn exception chưa xử lý báo thất bại tới container**, chứ không phải Spring tự kiểm tra email đã gửi hay database đã đúng.

### 2.2. Ví dụ thành công đồng bộ

~~~java
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class OrderCreatedListener {
    private final OrderProjectionService projectionService;

    public OrderCreatedListener(OrderProjectionService projectionService) {
        this.projectionService = projectionService;
    }

    @RabbitListener(
            id = "orders-projection-listener",
            queues = "orders.created.work",
            containerFactory = "ordersListenerFactory",
            ackMode = "AUTO")
    public void onOrderCreated(OrderCreated event) {
        // Phải trả về sau khi transaction xử lý thành công.
        projectionService.applyIdempotently(event);
    }
}
~~~

**OrderCreated** là DTO đã được JSON converter giải mã; **OrderProjectionService** là dịch vụ nghiệp vụ do ứng dụng triển khai. Nếu **applyIdempotently** ném exception thoát khỏi method, container **không gửi ACK thành công theo đường bình thường**.

Nếu **applyIdempotently** nuốt exception nội bộ và trả bình thường, listener cũng sẽ trả bình thường. Spring không thể suy luận rằng DB thực tế chưa ghi.

### 2.3. Đừng nhầm ACK với lời gọi return

~~~mermaid
flowchart TD
    B["Broker giao message"] --> C["Spring converter và listener adapter"]
    C --> V{"Có exception chưa được xử lý?"}
    V -->|"Không"| S["Container đánh giá xử lý thành công"]
    S --> A["Gửi ACK theo batch/transaction/async policy"]
    V -->|"Có"| R["Retry/error handler/reject hoặc requeue"]
    R --> D{"Recovery có làm lỗi được coi là handled?"}
    D -->|"Có"| H["Theo semantics recoverer/container:<br/>có thể ACK hoặc reject"]
    D -->|"Không"| N["NACK/reject, requeue hoặc DLX"]
~~~

Một **retry interceptor** hoặc **recoverer** có thể làm thay đổi kết quả cuối mà container quan sát. Chỉ nhìn vào exception bên trong code chưa đủ: phải nhìn cả những tầng advice/error handler bao ngoài.

## 3. AUTO không phải broker auto-ack

Đây là khác biệt quan trọng của Spring AMQP:

| Spring **AcknowledgeMode** | Điều broker thấy | Ai chịu trách nhiệm? | Khi handler lỗi |
| --- | --- | --- | --- |
| **AUTO** | Consumer đăng ký ở chế độ yêu cầu ACK; container gửi ACK/NACK theo kết quả | **Spring container** | Retry/reject/requeue theo cấu hình; không ACK bình thường khi exception thoát |
| **MANUAL** | Consumer đăng ký ở chế độ yêu cầu ACK | **Code ứng dụng** phải gọi basicAck/basicNack | Nếu không ACK/NACK, delivery có thể ở trạng thái unacked cho đến khi channel đóng |
| **NONE** | Broker **auto-ack** delivery khi gửi tới consumer | **Broker** coi như giao xong | Message có thể mất dù handler chưa xử lý thành công |

Tên **AUTO** của Spring nói rằng **Spring tự quản lý việc gửi ACK**. Còn “auto-ack” trong thuật ngữ RabbitMQ tương ứng với **AcknowledgeMode.NONE**.

### AUTO phù hợp khi nào?

Thường là lựa chọn đầu tiên cho **handler đồng bộ**: xử lý trong method, propagate exception nếu thất bại, cấu hình retry/DLQ và đảm bảo idempotency. Container thay ứng dụng quản lý deliveryTag/ACK, giảm lỗi protocol.

### MANUAL phù hợp khi nào?

Khi cần điều khiển ACK rõ ràng theo kết quả một luồng đặc biệt, hoặc dùng callback xử lý bất đồng bộ mà container không thể kết luận chỉ từ return đồng bộ. Phải đảm bảo tất cả nhánh success/failure đều có quyết định ACK/NACK an toàn.

### NONE phù hợp khi nào?

Chỉ khi workload thực sự **best effort**, chấp nhận mất event sau delivery, chẳng hạn telemetry không quan trọng. Không nên dùng NONE cho thanh toán, cập nhật tồn kho, email bắt buộc hoặc công việc có yêu cầu giao nhận đáng tin cậy.

## 4. Bẫy phổ biến: catch exception rồi return

Xem listener sau:

~~~java
@RabbitListener(
        queues = "orders.created.work",
        ackMode = "AUTO")
public void unsafeHandler(OrderCreated event) {
    try {
        orderRepository.saveProjection(event);
        externalNotifier.send(event);
    } catch (Exception ex) {
        log.error("Unable to process order {}", event.orderId(), ex);
        // Không rethrow, không đánh dấu công việc cần phục hồi.
    }
    // Method return bình thường -> container có thể ACK.
}
~~~

Nếu **externalNotifier.send** hoặc **orderRepository.saveProjection** thất bại, code chỉ log rồi kết thúc. **Spring AUTO vẫn coi là thành công**, vì exception không thoát ra.

Một cách sửa khi yêu cầu broker retry là **ném exception trở lại**:

~~~java
@RabbitListener(
        queues = "orders.created.work",
        ackMode = "AUTO",
        containerFactory = "ordersListenerFactory")
public void safeHandler(OrderCreated event) {
    try {
        projectionService.applyIdempotently(event);
    } catch (TransientDataAccessException ex) {
        log.warn("Temporary DB issue, eventId={}", event.eventId(), ex);
        throw ex; // Để container/retry advice xử lý thất bại.
    }
}
~~~

Ở ví dụ này, **TransientDataAccessException** thuộc Spring DAO, và **projectionService** là dependency nghiệp vụ. Đây là minh họa: cần cấu hình retry hữu hạn và DLQ thực tế, không để một lỗi tạm thời khiến broker requeue liên tục không có backoff.

### Khi nào catch và return là đúng?

Có những trường hợp handler đã xử lý hợp lệ khi thấy event trùng:

~~~java
@RabbitListener(queues = "orders.created.work", ackMode = "AUTO")
public void handle(OrderCreated event) {
    if (projectionService.alreadyProcessed(event.eventId())) {
        // Dữ liệu nghiệp vụ đã được commit ở lần trước.
        return; // ACK message trùng là hợp lý.
    }
    projectionService.applyIdempotently(event);
}
~~~

Tuy nhiên, mô hình **check trước rồi insert sau** có race khi nhiều consumer song song. Một triển khai production nên dùng **unique constraint + transaction** thay vì chỉ gọi alreadyProcessed rồi mới xử lý. Phần 10 có ví dụ an toàn hơn.

**Quy tắc:** return bình thường chỉ nên xảy ra khi công việc **đã hoàn tất**, hoặc sự kiện **được xác định là duplicate/không cần xử lý một cách an toàn**. Không coi “đã log exception” là hoàn tất.

## 5. Code Spring Boot: chứng minh thời điểm AUTO ACK

Ví dụ dùng **Java 17**, **Spring Boot 3.x**, **Spring AMQP 3.x** và RabbitMQ AMQP 0.9.1. Với Spring AMQP 4.x dùng đúng API converter tương ứng (Jackson 3). Đây là ví dụ học tập; cần thiết lập connection/credentials theo môi trường.

### 5.1. Maven dependency

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-amqp</artifactId>
</dependency>
~~~

Nếu ứng dụng nhận JSON DTO, cần dependency Jackson tương ứng. Spring Boot có BOM quản lý phiên bản; không trộn thủ công các nhánh Spring AMQP/Jackson.

### 5.2. Event DTO

~~~java
package com.example.contract;

public record OrderCreated(
        String eventId,
        String orderId,
        long totalAmount) {
}
~~~

### 5.3. Khai báo exchange, queue và DLQ

~~~java
package com.example.amqp;

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
                .deadLetterRoutingKey("orders.created.failed")
                .build();
    }

    @Bean
    Queue ordersDlq() {
        return QueueBuilder.durable("orders.created.dlq").build();
    }

    @Bean
    Binding ordersWorkBinding(
            @Qualifier("ordersWorkQueue") Queue queue,
            TopicExchange ordersExchange) {
        return BindingBuilder.bind(queue)
                .to(ordersExchange)
                .with("order.created");
    }

    @Bean
    Binding ordersDeadLetterBinding(
            @Qualifier("ordersDlq") Queue queue,
            DirectExchange ordersDlx) {
        return BindingBuilder.bind(queue)
                .to(ordersDlx)
                .with("orders.created.failed");
    }
}
~~~

**RabbitAdmin** hoặc provisioning tool cần khai báo topology; những bean @Configuration không giúp message tự định tuyến nếu ứng dụng không khởi tạo AMQP connection/không có quyền declare. Trong production, có thể dùng **RabbitMQ policy** để quản lý DLX thay vì hardcode x-dead-letter arguments.

### 5.4. Factory: AUTO, prefetch, converter

~~~java
package com.example.amqp;

import com.example.contract.OrderCreated;
import org.springframework.amqp.core.AcknowledgeMode;
import org.springframework.amqp.rabbit.annotation.EnableRabbit;
import org.springframework.amqp.rabbit.config.SimpleRabbitListenerContainerFactory;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.amqp.support.converter.Jackson2JsonMessageConverter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableRabbit
public class OrderConsumerConfiguration {
    @Bean
    Jackson2JsonMessageConverter orderJsonConverter() {
        return new Jackson2JsonMessageConverter();
    }

    @Bean
    SimpleRabbitListenerContainerFactory ordersListenerFactory(
            ConnectionFactory connectionFactory,
            Jackson2JsonMessageConverter orderJsonConverter) {

        SimpleRabbitListenerContainerFactory factory =
                new SimpleRabbitListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setMessageConverter(orderJsonConverter);
        factory.setAcknowledgeMode(AcknowledgeMode.AUTO);
        factory.setConcurrentConsumers(2);
        factory.setMaxConcurrentConsumers(4);
        factory.setPrefetchCount(10);
        factory.setBatchSize(1); // Dễ quan sát ACK theo mỗi message.
        factory.setDefaultRequeueRejected(false);
        return factory;
    }
}
~~~

**AcknowledgeMode.AUTO** làm container quản lý ACK sau kết quả handler. **batchSize=1** giúp demo không gom nhiều message vào một ACK của SMLC. **defaultRequeueRejected(false)** khiến message lỗi không được requeue vô hạn theo chính sách mặc định; nếu queue có DLX và message được reject không requeue, broker có thể chuyển nó tới DLQ.

**Chú ý:** đây là bean factory được cấu hình thủ công. Các properties của Spring Boot auto-configured listener factory không nhất thiết tự áp vào custom factory này. Chọn một nguồn cấu hình hoặc dùng Boot factory configurer nếu cần kế thừa properties.

### 5.5. Publisher JSON và listener AUTO

~~~java
package com.example.amqp;

import com.example.contract.OrderCreated;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.amqp.support.converter.Jackson2JsonMessageConverter;
import org.springframework.stereotype.Service;

@Service
public class OrderPublisher {
    private final RabbitTemplate template;

    public OrderPublisher(
            org.springframework.amqp.rabbit.connection.ConnectionFactory cf,
            Jackson2JsonMessageConverter converter) {
        this.template = new RabbitTemplate(cf);
        this.template.setMessageConverter(converter);
    }

    public void publish(OrderCreated event) {
        template.convertAndSend(
                "orders.events",
                "order.created",
                event,
                message -> {
                    message.getMessageProperties()
                            .setMessageId(event.eventId());
                    return message;
                });
    }
}
~~~

~~~java
package com.example.amqp;

import com.example.contract.OrderCreated;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class OrderListener {
    private final OrderProjectionService projectionService;

    public OrderListener(OrderProjectionService projectionService) {
        this.projectionService = projectionService;
    }

    @RabbitListener(
            id = "order-projection",
            queues = "orders.created.work",
            containerFactory = "ordersListenerFactory",
            ackMode = "AUTO")
    public void handle(OrderCreated event) {
        projectionService.applyIdempotently(event);
        // Khi lời gọi trả bình thường:
        // Container có thể ACK message theo cấu hình.
    }
}
~~~

**OrderProjectionService** được giả định có trách nhiệm validate DTO, ghi database và idempotency. **OrderListener** không tự gọi basicAck trong AUTO. Nếu body không convert được, lỗi có thể xảy ra **trước method** và đi qua error handling của container.

Cần bật **publisher confirms/returns** nếu muốn biết producer gửi đến broker/queue đáng tin cậy; **AUTO ACK ở consumer không bổ sung bảo đảm cho bước publish**.

### 5.6. Cấu hình qua application.yml thay cho custom factory

Nếu dựa vào **Spring Boot auto-configured factory**, có thể dùng:

~~~yaml
spring:
  rabbitmq:
    host: localhost
    port: 5672
    username: guest
    password: guest
    listener:
      type: simple
      simple:
        acknowledge-mode: auto
        concurrency: 2
        max-concurrency: 4
        prefetch: 10
        default-requeue-rejected: false
~~~

**guest/guest** chỉ phù hợp môi trường RabbitMQ local mặc định. Khi dùng custom factory của mục 5.4, không mặc định những property Boot này được áp lên factory riêng. Để giữ Boot auto-configuration, dùng đúng factory do Boot cung cấp hoặc **SimpleRabbitListenerContainerFactoryConfigurer**.

## 6. Nếu listener ném exception thì chuyện gì xảy ra?

Trong **AUTO**, khi exception thoát khỏi listener, container không coi việc xử lý là thành công. Nó có thể thử lại bằng **listener retry interceptor**, hoặc sau đó **reject/nack** theo error handler và cấu hình.

~~~mermaid
flowchart TD
    A["Delivery"] --> C["Convert + invoke @RabbitListener"]
    C --> D{"Listener/adapter hoàn tất?"}
    D -->|"Thành công"| ACK["ACK theo container policy"]
    D -->|"Exception"| RET["Retry advice / error handler"]
    RET --> E{"Lỗi được xử lý thành công?"}
    E -->|"Có, theo recoverer"| RES["Theo kết quả recovery:<br/>ACK hoặc reject"]
    E -->|"Không"| NACK["Reject/NACK"]
    NACK --> K{"requeue?"}
    K -->|"true"| Q["Quay lại queue và có thể redeliver"]
    K -->|"false"| DLX["Dead-letter nếu DLX có cấu hình<br/>hoặc loại bỏ"]
~~~

### 6.1. defaultRequeueRejected

| Tùy chọn | Ý nghĩa khi reject không có chỉ thị override khác |
| --- | --- |
| **true** (mặc định thường gặp) | Message thất bại có thể được requeue để broker giao lại |
| **false** | Message thất bại bị reject không requeue; đi DLX nếu cấu hình hỗ trợ, nếu không có thể bị loại |

**Requeue ngay không phải retry với backoff.** Message poison bị requeue liên tục có thể tạo vòng lặp nóng làm tăng CPU, network và số lần delivery.

### 6.2. Exception chỉ định hành vi

Spring AMQP có các exception để biểu thị chính sách rõ ràng:

- **AmqpRejectAndDontRequeueException**: yêu cầu reject không requeue.
- **ImmediateRequeueAmqpException**: yêu cầu requeue ngay trong đường xử lý phù hợp.
- **ImmediateAcknowledgeAmqpException**: yêu cầu acknowledgement ngay trong những bối cảnh container hỗ trợ; không dùng để “giấu lỗi” nghiệp vụ chưa xử lý.

Không tùy tiện ném một trong các exception này để “sửa” mọi lỗi: quyết định cần gắn với loại lỗi và tác động nghiệp vụ đã thực hiện.

### 6.3. Lỗi conversion trước method

~~~text
RabbitMQ delivery
    ↓
AMQP MessageConverter
    ↓
[JSON lỗi / class không tin cậy]
    ↓
Listener method CHƯA ĐƯỢC GỌI
    ↓
Container ErrorHandler / ConditionalRejectingErrorHandler
    ↓
Reject/requeue/dead-letter theo chính sách
~~~

**Try/catch đặt trong @RabbitListener không thể bắt lỗi xảy ra trước khi listener được gọi.** Spring AMQP có **ConditionalRejectingErrorHandler** thường coi một số lỗi conversion/argument resolution là fatal và có chính sách reject tương ứng; hiệu lực cụ thể còn phụ thuộc phiên bản, nguyên nhân exception và cấu hình container.

Vì thế không thể khẳng định rằng **mọi exception trong AUTO đều requeue**. Cần phân biệt lỗi logic trong method với lỗi decoder/fatal của container và retry advice/recoverer.

### 6.4. Retry interceptor có thể đổi kết quả ACK

Giả sử handler lỗi hai lần nhưng lần thứ ba thành công. Nếu **RetryOperationsInterceptor** bao quanh invocation và hoàn tất thành công, container nhận được kết quả cuối **thành công**, nên đường ACK bình thường có thể tiếp diễn.

Nếu một **MessageRecoverer** sau khi hết retry đã xử lý message bằng cách **ghi bền vững thông tin lỗi** rồi return bình thường, cần hiểu nghĩa recovery đó: container có thể coi xử lý đã được giải quyết và ACK. Nếu muốn broker **dead-letter qua DLX**, cần recoverer/chính sách reject thích hợp; không cho rằng mọi recoverer return đều tự tạo DLQ.

## 7. ACK có luôn phát ngay sau một message không?

**Không.** Trong mặc định đơn giản, AUTO thường ACK từng message khi xử lý thành công. Nhưng container có thể **gom ACK**, hoặc cần **transaction commit** trước khi broker coi là hoàn tất.

### 7.1. SimpleMessageListenerContainer: batchSize

Với **SimpleMessageListenerContainer (SMLC)**, cấu hình **batchSize** lớn hơn 1 làm container cố xử lý nhiều message trước khi ACK; nó có thể chờ đến receive timeout để kết thúc một nhóm nhỏ hơn batchSize. Khi dùng channel transacted, đây cũng là lúc thực hiện commit của channel.

~~~java
SimpleRabbitListenerContainerFactory factory =
        new SimpleRabbitListenerContainerFactory();
factory.setConnectionFactory(connectionFactory);
factory.setAcknowledgeMode(AcknowledgeMode.AUTO);
factory.setBatchSize(5);
factory.setPrefetchCount(10);
~~~

Timeline minh họa:

~~~text
Listener xử lý M1 thành công → có thể chưa gửi ACK
Listener xử lý M2 thành công → có thể chưa gửi ACK
Listener xử lý M3 thành công → có thể chưa gửi ACK
Listener xử lý M4 thành công → có thể chưa gửi ACK
Listener xử lý M5 thành công → container gửi ACK nhóm theo policy
~~~

Đây là **nhóm ACK**, không bắt buộc là một invocation nhận **List<Message>**. Đừng nhầm **batchSize** dùng để quyết định ACK của SMLC với **consumerBatchEnabled** dùng để gửi danh sách message cho một method batch listener.

Nếu **prefetchCount < batchSize**, Spring AMQP điều chỉnh prefetch tối thiểu để đủ điều kiện cho batch. Nếu handler M5 thất bại, việc xử lý ACK/reject của các message đã hoàn tất trước đó phải tuân theo semantics container, không được suy ra rằng cả năm cùng thất bại y hệt nhau trong mọi cấu hình.

### 7.2. DirectMessageListenerContainer: messagesPerAck và ackTimeout

DMLC có **messagesPerAck** để giảm số lần phát ACK trên workload lớn; cấu hình **ackTimeout** ảnh hưởng thời điểm container quyết định gửi ACK khi chưa đủ số lượng.

~~~java
DirectRabbitListenerContainerFactory factory =
        new DirectRabbitListenerContainerFactory();
factory.setConnectionFactory(connectionFactory);
factory.setAcknowledgeMode(AcknowledgeMode.AUTO);
factory.setConsumersPerQueue(2);
factory.setPrefetchCount(20);
factory.setMessagesPerAck(10);
factory.setAckTimeout(2_000);
~~~

**Đây là code cấu hình trong method @Bean**, không phải ứng dụng độc lập. Các setter thuộc **DirectRabbitListenerContainerFactory** của nhánh Spring AMQP phù hợp; kiểm tra phiên bản cụ thể trước khi áp dụng.

**messagesPerAck=10** có nghĩa các listener hoàn tất có thể chưa được ACK riêng lẻ ngay. Khi có đủ số message hoặc đạt điều kiện timeout, ACK được gửi theo cơ chế container. Nếu không có message mới, việc kiểm tra timeout có thể **xấp xỉ**, phụ thuộc **monitorInterval**.

**Không dùng messagesPerAck trên channelTransacted=true**; tài liệu Spring AMQP quy định cấu hình này không tương thích với transactional channel. Nếu **prefetch < messagesPerAck**, container có thể tăng prefetch cho tương thích.

### 7.3. So sánh hai cách gom ACK

| Khả năng | SMLC | DMLC |
| --- | --- | --- |
| **batchSize** tác động ACK | **Có** | Không phải cơ chế tương đương |
| **messagesPerAck** | Không phải thuộc tính dành cho SMLC | **Có** |
| **ackTimeout/monitorInterval** cho messagesPerAck | Không | **Có** |
| **channelTransacted** | Có, commit theo policy transaction/batch | Có, nhưng không kết hợp messagesPerAck |
| **Lợi ích gom ACK** | Giảm frame ACK/transaction overhead | Giảm frame ACK ở lưu lượng lớn |
| **Đổi lại** | Nhiều message có thể redeliver nếu mất connection trước ACK | Tăng phạm vi delivery chưa ACK tương tự |

**Thông điệp chính:** “listener đã return” có thể chỉ có nghĩa **đang đủ điều kiện được ACK**, chứ không có nghĩa broker đã nhận ACK tại thời điểm ấy. Đừng suy ra vị trí ACK chỉ từ log trong method.

## 8. ACK và transaction: không phải một commit chung

Nếu bật **channelTransacted=true**, RabbitMQ yêu cầu **transaction commit ở channel** để kết thúc các thao tác AMQP thuộc transaction. **AcknowledgeMode.AUTO** và **channelTransacted** là hai cấu hình bổ sung, không phải hai từ đồng nghĩa.

~~~java
SimpleRabbitListenerContainerFactory factory =
        new SimpleRabbitListenerContainerFactory();
factory.setConnectionFactory(connectionFactory);
factory.setAcknowledgeMode(AcknowledgeMode.AUTO);
factory.setChannelTransacted(true);
factory.setBatchSize(1);
~~~

Trong trường hợp này, listener return thành công nhưng broker còn cần xử lý commit của AMQP channel. Nếu transaction/commit có lỗi, không thể chỉ nhìn log **handler returned** rồi khẳng định message đã được ACK thành công.

### 8.1. Database transaction khác AMQP transaction

Giả sử handler xử lý database:

~~~java
@RabbitListener(queues = "orders.created.work", ackMode = "AUTO")
public void onEvent(OrderCreated event) {
    orderProjectionService.applyInDatabaseTransaction(event);
}
~~~

Với service được Spring proxy quản lý và annotation **@Transactional** hiệu lực, phương thức **applyInDatabaseTransaction** có thể chỉ return sau khi DB transaction commit. Sau đó listener mới return và container mới xem xét ACK. Đây là thứ tự mong muốn cho thao tác DB:

~~~text
Nhận delivery → DB transaction bắt đầu
    → UPDATE + COMMIT thành công
    → method listener return
    → container phát ACK theo policy
    → broker nhận ACK
~~~

Nhưng vẫn có **khoảng trống**: DB commit xong, tiến trình hoặc connection hỏng **trước khi ACK tới broker**. Khi đó broker có thể giao lại message. Không có một transaction nguyên tử tự động bao phủ **DB và RabbitMQ** chỉ vì cả hai đều có transaction.

Nếu một phương thức **@Transactional** tự gọi qua self-invocation không đi qua proxy, transaction kỳ vọng có thể không được áp dụng. Cần kiểm tra transaction boundary thực tế.

### 8.2. Nếu ACK đến broker trước khi external API hoàn tất?

Chuyện này có thể xảy ra nếu handler **tạo background thread/fire-and-forget rồi return**:

~~~java
@RabbitListener(queues = "orders.created.work", ackMode = "AUTO")
public void unsafeAsync(OrderCreated event) {
    executor.execute(() -> paymentGateway.charge(event));
    // Listener return NGAY; task async chưa xong.
    // Container có thể ACK dù charge thất bại sau đó.
}
~~~

Dù hình thức này nhìn giống asynchronous processing, Spring không nhận được một **future kết quả** để điều phối ACK. Đây là ví dụ **không an toàn** cho nghiệp vụ bắt buộc hoàn tất.

## 9. Listener trả CompletableFuture/Mono: ACK khi nào?

Spring AMQP hỗ trợ một số **kiểu trả về bất đồng bộ** như **CompletableFuture** và **Mono**. Trong cấu hình được framework hỗ trợ, container cần **MANUAL acknowledgement** để không ACK sớm khi method vừa trả về future. ACK/NACK được điều phối theo **kết quả completion**.

Tài liệu Spring AMQP ghi nhận việc tự phát hiện kiểu async và đổi sang MANUAL từ các bản vá **2.2.21 / 2.3.13 / 2.4.1**, và hỗ trợ Kotlin suspend ở các phiên bản sau. Hành vi cụ thể phụ thuộc phiên bản; cần xác nhận setup listener factory và error policy của ứng dụng.

~~~mermaid
sequenceDiagram
    participant B as RabbitMQ
    participant C as Spring async listener adapter
    participant L as @RabbitListener method
    participant F as CompletableFuture
    B->>C: deliver OrderCreated
    C->>L: invoke async method
    L-->>C: return CompletableFuture ngay
    Note over C: Chưa ACK chỉ vì method return
    F-->>C: complete successfully
    C-->>B: ACK khi completion thành công
~~~

Ví dụ:

~~~java
import java.util.concurrent.CompletableFuture;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class AsyncOrderListener {
    private final OrderAsyncService orderAsyncService;

    public AsyncOrderListener(OrderAsyncService service) {
        this.orderAsyncService = service;
    }

    @RabbitListener(
            queues = "orders.created.async",
            containerFactory = "asyncOrdersFactory")
    public CompletableFuture<Void> handle(OrderCreated event) {
        return orderAsyncService.applyIdempotentlyAsync(event);
    }
}
~~~

**OrderAsyncService** là abstraction do ứng dụng định nghĩa; future trả về **phải chỉ hoàn thành thành công khi công việc cần xác nhận đã kết thúc**. Nếu future hoàn thành sớm hơn DB commit hoặc API operation thì vẫn ACK quá sớm.

Trong ví dụ, **orders.created.async** là queue riêng và **asyncOrdersFactory** phải được cấu hình thích hợp; đừng chạy chung queue với listener khác khi muốn so sánh độc lập. Không tạo future đã complete rồi đẩy công việc thật sang thread khác mà không nối kết kết quả.

### Khi future hoàn tất lỗi

Một **exceptional completion** có thể khiến container NACK/requeue/reject tùy exception, **defaultRequeueRejected** và error handler. Đừng mặc định mọi lỗi async sẽ được requeue hay DLQ. Nếu exception xảy ra **trước khi method trả về future**, cần xử lý/đưa exception về dạng async result phù hợp với contract version đang dùng; tài liệu Spring có lưu ý riêng về tình huống này.

**Điểm phân biệt:**

- Đồng bộ AUTO: return thành công là điểm container quyết định ACK.
- Async được hỗ trợ: return **future** chưa phải hoàn tất; ACK theo **future completion**.
- Fire-and-forget: return sớm có thể khiến ACK sớm; không có cơ chế theo dõi kết quả.

## 10. Crash sau DB commit nhưng trước broker ACK

Đây là tình huống quan trọng nhất để hiểu tại sao **AUTO ACK không đồng nghĩa exactly-once business effect**.

~~~mermaid
sequenceDiagram
    participant B as RabbitMQ
    participant C as Order Consumer
    participant DB as Database
    B->>C: deliver eventId=e-101
    C->>DB: Begin + insert projection + eventId
    DB-->>C: COMMIT OK
    Note over C: Listener return thành công
    C--xB: ACK bị mất vì connection chết
    Note over B: Delivery chưa ACK được requeue
    B->>C: redeliver eventId=e-101
    C->>DB: Kiểm tra eventId đã xử lý
    DB-->>C: Duplicate an toàn
    C-->>B: ACK
~~~

Tại thời điểm database commit, tác động nghiệp vụ đã diễn ra. Nhưng nếu ACK không đến broker, RabbitMQ không thể suy luận DB đã xử lý xong. Khi channel/connection đóng, những delivery chưa được ACK có thể trở lại queue và được giao cho một consumer khác.

**Redelivered=true** có thể hỗ trợ chẩn đoán, nhưng không đủ để loại trùng:
- Producer có thể retry cùng eventId và tạo message **mới**, lúc delivery đầu cờ redelivered có thể false.
- Consumer không nên phụ thuộc deliveryTag vì nó thuộc channel, thay đổi theo lần giao.
- Tác động ngoài (email, thanh toán) có thể đã hoàn tất dù ACK thất lạc.

**Giải pháp:** xử lý theo **at-least-once delivery + idempotent business operation**.

### 10.1. Bảng processed_events

~~~sql
CREATE TABLE processed_events (
    consumer_name VARCHAR(100) NOT NULL,
    event_id VARCHAR(100) NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (consumer_name, event_id)
);
~~~

### 10.2. Một DB transaction cho deduplication và tác động

~~~java
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderProjectionService {
    private final JdbcTemplate jdbcTemplate;
    private final OrderProjectionRepository projectionRepository;

    public OrderProjectionService(
            JdbcTemplate jdbcTemplate,
            OrderProjectionRepository repository) {
        this.jdbcTemplate = jdbcTemplate;
        this.projectionRepository = repository;
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
            return; // Event đã xử lý trong consumer group này.
        }

        projectionRepository.apply(event);
        // Transaction commit thành công trước khi lời gọi trả bình thường.
    }
}
~~~

**OrderProjectionRepository** là repository nghiệp vụ do ứng dụng cung cấp; **@Transactional** phải có transaction manager tương ứng với cùng database chứa **processed_events** và projection. Nếu projection insert lỗi, transaction **rollback cả bản ghi processed_events**, cho phép retry an toàn.

Trường hợp duplicate, method return bình thường vì đã xác định sự kiện không cần làm lại. Container có thể ACK message trùng mà không thực hiện lại tác động.

### 10.3. External side effect còn phức tạp hơn

Nếu listener gọi API gửi email, thanh toán hoặc cấp quyền:
- DB transaction cục bộ không thể tự rollback email đã gửi.
- Có thể ghi **notification_outbox** hoặc **payment_request** với khóa idempotency ổn định, commit cùng transaction.
- Worker tác vụ ngoài dùng idempotency key của provider khi hỗ trợ; cần reconciliation nếu kết quả bên ngoài không chắc chắn.
- Chỉ ACK khi trách nhiệm tiếp theo đã được **lưu bền vững** trong hệ thống quản lý công việc của mình, theo thiết kế nghiệp vụ rõ ràng.

Đừng đánh đồng **message được ACK** với “người dùng chắc chắn chỉ nhận một email”.

## 11. MANUAL ACK: so sánh trực tiếp thời điểm với AUTO

Trong MANUAL, việc method return **không tự động gửi ACK**. Ứng dụng phải gọi basicAck/basicNack trên **đúng Channel**.

~~~java
import com.rabbitmq.client.Channel;
import java.io.IOException;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.rabbit.annotation.RabbitListener;

@RabbitListener(
        queues = "orders.created.manual",
        containerFactory = "manualOrdersFactory",
        ackMode = "MANUAL")
public void handleManually(Message message, Channel channel)
        throws IOException {
    long tag = message.getMessageProperties().getDeliveryTag();

    try {
        orderService.processAndCommit(message);
        channel.basicAck(tag, false); // Chỉ ACK sau khi xử lý thành công.
    } catch (RuntimeException failure) {
        channel.basicNack(tag, false, false);
        // requeue=false: DLQ khi queue có DLX, ngược lại bị loại.
    }
}
~~~

**Đây là ví dụ minh họa:** **manualOrdersFactory**, **orders.created.manual** và **orderService** phải được cấu hình/triển khai. Cần phân loại lỗi temporary/permanent thay vì luôn NACK không requeue.

| Chi tiết | AUTO | MANUAL |
| --- | --- | --- |
| Method return bình thường | Container có thể ACK theo policy | Không tự ACK; code phải đã ACK hoặc còn delivery unacked |
| Handler throw | Container error handling quyết định | Ứng dụng/container có hành vi riêng tùy exception và config; không được quên xử lý tag |
| Ai gọi basicAck | Container | Ứng dụng |
| Nguy cơ double ACK | Không tự ACK thủ công nếu container quản lý | Có nếu code ACK cùng tag nhiều lần |
| Nên dùng khi | Handler đồng bộ thông thường | Lifecycle đặc biệt/ACK điều phối bởi ứng dụng |
| Idempotency | **Vẫn cần** | **Vẫn cần** |

**basicAck(tag, false)** xác nhận đúng một delivery; **multiple=true** có thể ACK nhiều delivery chưa xác nhận trên cùng channel, cần rất thận trọng khi xử lý song song. Nếu ACK cùng tag hai lần hoặc ACK trên channel khác, RabbitMQ có thể đóng channel với **PRECONDITION_FAILED - unknown delivery tag**.

Không viết code MANUAL rồi đồng thời để container AUTO tự ACK theo cùng delivery: điều đó có thể dẫn tới double ACK hoặc lệch lifecycle.

## 12. Prefetch và ACK quyết định áp lực lên consumer

**Prefetch** là giới hạn số message **unacked** RabbitMQ có thể giao cho một consumer trong mô hình QoS thông dụng. ACK đến broker giải phóng “slot” cho delivery tiếp theo.

Ví dụ một listener có **prefetch=10**, đang xử lý message 1 trong khi các message 2–10 được giao trước và đang chờ phía client. Nếu message 1 xử lý chậm, unacked có thể giữ ở mức cao dù queue ready giảm.

| Cấu hình ví dụ | Consumer | Prefetch/consumer | Delivery chưa ACK tiềm năng |
| --- | ---: | ---: | ---: |
| SMLC: concurrency=2 | 2 | 10 | Khoảng 20 |
| SMLC đang chạy 5 consumer | 5 | 20 | Khoảng 100 |
| DMLC: 3 consumers/queue, nghe 2 queue | 6 | 20 | Khoảng 120 |

Đây là **ước lượng tối đa theo QoS** trong tình huống đơn giản; metrics thực tế còn phụ thuộc cấu hình global QoS/batching, backlog, tốc độ consumer và broker.

**Batch ACK có thể giữ message unacked lâu hơn** dù listener đã return, và tăng số delivery phải xử lý lại nếu connection mất. Vì vậy việc tăng batchSize/messagesPerAck để tăng throughput cần đánh đổi với nguy cơ **redelivery hàng loạt**.

Nếu **ackMode=NONE**, broker auto-ack, cơ chế prefetch trên các unacked delivery không có ý nghĩa như ở AUTO/MANUAL.

### Vấn đề thứ tự

Có nhiều consumer, requeue hoặc retry thì thứ tự **hoàn tất nghiệp vụ** có thể khác thứ tự publish. Nếu một đơn hàng có event **OrderCreated → OrderPaid → OrderCancelled**, cần dùng aggregateId, version/sequence và cơ chế xử lý event đến muộn; không đặt niềm tin vào việc ACK sau return để bảo đảm thứ tự nghiệp vụ toàn cục.

## 13. Theo dõi thời điểm ACK bằng metric và log

Mục tiêu quan sát không chỉ là biết method được gọi, mà là biết **delivery có được ACK**, **bị reject**, **được redeliver** hay **bị dead-letter**.

| Dấu hiệu | Ý nghĩa | Gợi ý |
| --- | --- | --- |
| **queue messages_ready** | Message chưa giao cho consumer | Tăng kéo dài có thể thiếu năng lực xử lý |
| **queue messages_unacknowledged** | Delivery đã giao mà broker chưa thấy ACK | Tăng khi handler chậm, prefetch cao, MANUAL quên ACK hoặc gom ACK |
| **deliver/ack rate** | Tốc độ broker giao/nhận ACK | So sánh throughput và timing |
| **redeliver rate** | Delivery được giao lại | Tìm lỗi connection, handler exception, retry loop |
| **DLQ depth** | Message lỗi không xử lý thành công | Cần cảnh báo, phân loại lỗi và replay |
| **handler latency P95/P99** | Thời gian xử lý nghiệp vụ | Tuning concurrency/prefetch |
| **DB commit failures** | Transaction nghiệp vụ lỗi | Phân biệt với ACK error |
| **duplicate_event_total** | EventId đã xử lý được nhìn thấy lại | Kiểm chứng idempotency |
| **connection/channel churn** | Connection reset hoặc channel lỗi | Nguyên nhân ACK thất lạc/redelivery |
| **batch/ack settings** | batchSize/messagesPerAck/ackTimeout | Giải thích ACK rate thấp hơn số handler return |

Một log **“listener success”** được ghi trước khi return **không phải bằng chứng RabbitMQ đã nhận ACK**. Muốn biết ACK frame thật sự được broker xử lý, cần đối chiếu số liệu **broker acknowledgements**, channel health và event lifecycle; không luôn có một callback per-message báo “broker đã nhận consumer ACK” cho application như cơ chế publisher confirm.

### Trace an toàn

Log **eventId**, **queueName**, **consumerName**, **correlationId**, thời gian DB commit và kết quả handler ở mức phù hợp. Không log toàn bộ body chứa dữ liệu cá nhân. RabbitMQ Management UI cung cấp consumer count, ready, unacked, delivery/ack rate; Spring AMQP và Micrometer Observation hỗ trợ quan sát từng listener nếu cấu hình đúng phiên bản.

## 14. Kiểm thử timing ACK với lỗi thực tế

**Không dùng queue production** để thử lỗi nhận message. Dựng topology test, tách queue cho các thử nghiệm và kiểm tra số bản ghi DB cùng số delivery broker nhận.

### Kịch bản A — AUTO thành công

1. Cấu hình **SMLC, AUTO, batchSize=1**, consumer xử lý sự kiện trong 500 ms.
2. Publish một OrderCreated.
3. Trong lúc handler chạy, quan sát queue **unacked**.
4. Sau khi handler return, theo dõi ACK rate và số unacked giảm.
5. Ghi nhận timeline; đừng khẳng định broker ACK đúng cùng mili-giây với log return.

### Kịch bản B — Catch rồi return

1. Handler cố tình ném exception từ DB nhưng catch và chỉ log.
2. Handler return bình thường.
3. Quan sát container ACK theo policy dù projection không được ghi.
4. Sửa code để propagate exception hoặc lưu một job phục hồi bền vững trước khi return.
5. Giải thích vì sao **cách viết code**, không chỉ ackMode, quyết định mất message.

### Kịch bản C — Exception thoát ra và DLQ

1. Dùng **AUTO** và queue có DLX.
2. Cấu hình **defaultRequeueRejected=false**, retry hữu hạn khi cần.
3. Handler ném exception chưa được phục hồi.
4. Kiểm tra message có thể bị reject không requeue rồi được chuyển sang DLQ.
5. Đối chiếu trường hợp **defaultRequeueRejected=true**, tránh requeue loop trong test lâu dài.

### Kịch bản D — DB commit rồi ACK mất

1. Tạo bảng **processed_events** với unique constraint trong cùng transaction projection.
2. Cho handler commit thành công.
3. Dùng fault injection để làm connection chết trước khi broker nhận ACK; việc tắt broker ngẫu nhiên không chắc tạo đúng race.
4. Cho container kết nối lại và broker redeliver.
5. Kiểm tra projection chỉ thay đổi một lần, còn message duplicate được ACK an toàn.

### Kịch bản E — Batch ACK

1. Thử **SMLC batchSize=1**, publish 20 message.
2. Thử **SMLC batchSize=5**, giữ workload tương tự.
3. So sánh số ACK frame, thời gian unacked và nguy cơ redelivery khi connection mất.
4. Lặp lại bằng **DMLC messagesPerAck=10** và ackTimeout có giới hạn.
5. Không áp messagesPerAck vào transactional channel.

### Kịch bản F — Fire-and-forget và async future

1. Viết listener AUTO tạo thread gửi email rồi return ngay.
2. Cố ý làm email task lỗi sau khi method đã return.
3. Quan sát ACK có thể đã được gửi sớm.
4. Viết lại bằng **CompletableFuture** theo khả năng async @RabbitListener của phiên bản và xác minh ACK chỉ xảy ra theo kết quả completion.
5. Kiểm tra cả exceptional completion và lỗi trước khi tạo future.

### Kịch bản G — Quên ACK ở MANUAL

1. Cấu hình MANUAL, prefetch=3.
2. Nhận ba message nhưng không ACK/NACK.
3. Quan sát **messages_unacknowledged** tăng và broker ngừng giao thêm khi đạt prefetch.
4. Đóng channel/connection, quan sát broker có thể requeue những delivery chưa ACK.
5. Sửa code bao phủ mọi nhánh success/failure, tránh ACK trùng tag.

## 15. Checklist vận hành

- **Chọn đúng mode:** AUTO cho handler đồng bộ thông thường, MANUAL khi thật sự cần kiểm soát trực tiếp; NONE chỉ khi chấp nhận mất message.
- **Không nuốt lỗi:** nếu nghiệp vụ chưa xong, propagate exception hoặc ghi bền vững trách nhiệm xử lý tiếp rồi mới return.
- **Kiểm tra phạm vi transaction:** DB commit trước khi listener return; biết vẫn có khoảng trống trước broker ACK.
- **Đừng fire-and-forget:** async work cần future/completion gắn với kết quả ACK, hoặc một outbox/job đã commit.
- **Chọn batch/prefetch phù hợp:** batchSize (SMLC), messagesPerAck/ackTimeout (DMLC), channelTransacted và concurrency có ảnh hưởng timing.
- **Phân loại retry:** transient có bounded retry/backoff, permanent có DLQ/kênh lỗi; tránh vòng lặp requeue nóng.
- **Chống trùng:** eventId ổn định, unique constraint, transaction cùng tác động nghiệp vụ; external API cần idempotency riêng.
- **Quan sát cả hai phía:** log handler success + broker ready/unacked/ACK rate + DLQ + DB commit + duplicates.
- **Không nhầm publisher:** xác nhận publish của RabbitTemplate khác xác nhận consume của @RabbitListener.

## 16. Câu hỏi ôn tập và bài tập thiết kế

1. Spring **AUTO** có phải RabbitMQ **auto-ack** không? Mode nào tương ứng auto-ack của broker?
2. Với AUTO và handler ném RuntimeException ra ngoài, container có gửi ACK thành công theo đường thông thường không?
3. Nếu handler catch exception rồi return, vì sao container vẫn có thể ACK dù DB chưa ghi?
4. Tại sao log **“method returned”** không chứng minh broker đã nhận basicAck?
5. **SMLC batchSize=5** ảnh hưởng thời điểm ACK như thế nào?
6. **DMLC messagesPerAck=10** kết hợp ackTimeout có ý nghĩa gì? Có dùng chung với channelTransacted=true không?
7. Với **CompletableFuture**, ACK nên gắn với return method hay completion của future?
8. Nếu email được gửi trong thread nền còn method listener đã return, rủi ro nào xuất hiện?
9. Vì sao DB commit rồi connection chết trước ACK có thể khiến message được xử lý lại?
10. Vì sao **deliveryTag** không thích hợp để chống trùng? **eventId** có gì khác?
11. MANUAL không ACK/NACK có thể khiến queue **unacked** và prefetch bị ảnh hưởng thế nào?
12. DefaultRequeueRejected=false có tự tạo retry backoff không?
13. Vì sao lỗi JSON trước khi method chạy cần xử lý ở container error handler?
14. Publisher confirm, consumer ACK và transaction nghiệp vụ giải quyết những câu hỏi khác nhau như thế nào?
15. Thiết kế workflow gửi email: lựa chọn AUTO/MANUAL, transaction/outbox, DLQ, idempotency và metric nào để đảm bảo không mất trách nhiệm xử lý?

### Bài tập mở rộng: xác định ranh giới thành công

Cho pipeline **Order Service → orders.events exchange → orders.created.work → OrderProjectionListener → PostgreSQL**. Hãy lập bảng với từng thời điểm: *message tới queue*, *broker giao*, *converter hoàn tất*, *DB commit*, *listener return*, *container gửi ACK*, *broker nhận ACK*. Với mỗi thời điểm, hãy nêu hệ thống biết điều gì, còn điều gì chưa chắc chắn và nếu tiến trình crash thì cần phục hồi theo cách nào.

## 17. Tài liệu tham khảo chính thức

- [Spring AMQP — Message Listener Container Configuration](https://docs.spring.io/spring-amqp/reference/amqp/containerAttributes.html): acknowledgeMode, batchSize (SMLC), messagesPerAck/ackTimeout (DMLC), prefetch và channelTransacted.
- [Spring AMQP — Asynchronous @RabbitListener Return Types](https://docs.spring.io/spring-amqp/reference/amqp/receiving-messages/async-returns.html): CompletableFuture/Mono, MANUAL acknowledgement và async completion.
- [Spring AMQP — Handling Exceptions](https://docs.spring.io/spring-amqp/reference/amqp/receiving-messages/async-annotation-driven/error-handling.html): error handler và exception listener.
- [Spring AMQP — Exception Handling](https://docs.spring.io/spring-amqp/reference/amqp/exception-handling.html): ConditionalRejectingErrorHandler, các lỗi fatal trong conversion.
- [Spring AMQP — Choosing a Container](https://docs.spring.io/spring-amqp/reference/amqp/receiving-messages/choose-container.html): SMLC và DMLC.
- [Spring AMQP — Listener Concurrency](https://docs.spring.io/spring-amqp/reference/amqp/listener-concurrency.html): concurrent consumers, ảnh hưởng throughput.
- [RabbitMQ — Consumer Acknowledgements and Publisher Confirms](https://www.rabbitmq.com/docs/confirms): deliveryTag, basicAck/basicNack, prefetch, redelivery, khác biệt với publisher confirm.
- [RabbitMQ — Consumers](https://www.rabbitmq.com/docs/consumers): consumer lifecycle, delivery timeout, QoS và dispatch.

---

**Ghi nhớ:** Với **Spring AMQP AcknowledgeMode.AUTO**, một **@RabbitListener đồng bộ trả về thành công** khiến container **đủ điều kiện ACK** message; **không** có nghĩa broker nhận ACK ngay tại dòng return. ACK có thể bị gom bởi **SMLC batchSize** hoặc **DMLC messagesPerAck**, bị chi phối bởi transaction, hoặc phụ thuộc **async completion**. **Catch lỗi rồi return** có thể khiến message được ACK dù nghiệp vụ thất bại. Ngay cả khi database đã commit, **mất ACK** có thể gây redelivery. Vì vậy cần **idempotent consumer, retry/DLQ, prefetch hợp lý và quan sát broker unacked/ACK rate**, không chỉ dựa vào log listener thành công.
