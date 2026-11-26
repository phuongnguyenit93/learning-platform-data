# containerFactory, concurrency, ackMode và messageConverter

## Mục tiêu bài học

Trong **Spring AMQP**, annotation **@RabbitListener** giúp ứng dụng nhận message từ một RabbitMQ queue mà không phải tự thao tác với consumer API mức thấp. Nhưng một method được gắn annotation chỉ là phần nổi: Spring cần **listener container** để quản lý connection/channel, luồng xử lý, chuyển kiểu dữ liệu, ACK/NACK, lỗi và recovery.

Bốn thuộc tính quan trọng của bài học thuộc chương **Listener khai báo**:

- **containerFactory**: chọn bean nhà máy tạo listener container.
- **concurrency**: chọn mức độ nhận và xử lý song song.
- **ackMode**: quyết định ai chịu trách nhiệm xác nhận message với broker.
- **messageConverter**: xác định cách chuyển AMQP Message (byte[]) thành Java DTO/payload.

Trong module **SPRING_AMQP**, những thiết lập này phối hợp với **RabbitTemplate**, **exchange**, **queue**, **binding**, publisher confirms, retry, dead-letter, transaction và giám sát để tạo hệ thống bất đồng bộ đáng tin cậy.

Sau bài, bạn có thể:

1. Giải thích chuỗi **broker → listener container → converter → method → ACK/NACK**.
2. Cấu hình **SimpleRabbitListenerContainerFactory** và **DirectRabbitListenerContainerFactory**, hiểu khác biệt của chúng.
3. Dùng đúng **concurrency="2-6"** với Simple container và **concurrency="3"** với Direct container.
4. Phân biệt **AcknowledgeMode.AUTO, MANUAL, NONE**; biết khi nào message có thể mất hoặc được redeliver.
5. Cấu hình JSON converter ở factory hoặc override theo annotation và hiểu type inference.
6. Tuning prefetch, xử lý lỗi conversion, retry/DLQ, idempotency và quan sát consumer.

## 1. Listener có những thành phần nào?

Một method đơn giản:

~~~java
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class SimpleOrderListener {
    @RabbitListener(queues = "orders.created")
    public void handle(String payload) {
        System.out.println(payload);
    }
}
~~~

Nhưng thực tế Spring cần:

1. **@EnableRabbit** hoặc hạ tầng annotation-driven được Spring Boot cấu hình.
2. **RabbitListenerContainerFactory** tạo container của endpoint.
3. **ConnectionFactory** (thường là CachingConnectionFactory) cấp AMQP connection/channel.
4. Container đăng ký consumer và nhận delivery từ queue.
5. **MessageConverter** giải mã body/metadata thành object để method dùng.
6. Container áp dụng **ackMode**, error handler, retry/recovery.

~~~mermaid
flowchart LR
    P["Order Service<br/>RabbitTemplate"] --> X{"Exchange<br/>orders.events"}
    X -->|"routing key + binding"| Q[("orders.created.work")]
    Q --> C["Listener container<br/>concurrency / prefetch"]
    C --> V["MessageConverter<br/>byte[] → DTO"]
    V --> M["@RabbitListener"]
    M --> D{"Kết quả"}
    D -->|"Thành công"| A["ACK theo ackMode"]
    D -->|"Lỗi"| E["Retry / reject / DLQ"]
~~~

**RabbitMQ không biết class Java hoặc phương thức @RabbitListener.** Broker chỉ giao message theo giao thức AMQP 0.9.1; Spring adapter và container ánh xạ delivery thành lời gọi Java.

| Thành phần | Vai trò | Dễ nhầm với |
| --- | --- | --- |
| **ConnectionFactory** | Tạo/tái sử dụng kết nối AMQP | Container factory |
| **RabbitListenerContainerFactory** | Cấu hình và tạo consumer container | ConnectionFactory |
| **Listener container** | Nhận message, quản lý consumer/thread/ACK | Method nghiệp vụ |
| **MessageConverter** | Chuyển body/metadata thành object | Exchange và routing key |
| **RabbitTemplate** | Gửi hoặc chủ động poll message | Listener chạy liên tục |

## 2. containerFactory: Simple hay Direct?

Giá trị **containerFactory** trong @RabbitListener là **tên bean Spring**. Nếu không chỉ định, infrastructure thường tìm factory mặc định tên **rabbitListenerContainerFactory**; Spring Boot có thể auto-configure bean mặc định nếu ứng dụng chưa khai báo factory tương ứng.

~~~java
@RabbitListener(
        queues = "orders.created.work",
        containerFactory = "ordersListenerFactory")
public void process(String payload) {
    // ...
}
~~~

### 2.1. SimpleRabbitListenerContainerFactory

Factory này tạo **SimpleMessageListenerContainer (SMLC)**. SMLC sử dụng consumer thread do container quản lý và cơ chế chuyển giao delivery từ RabbitMQ client sang thread xử lý. Nó hỗ trợ số consumer cố định hoặc một dải min/max có thể scale theo mức hoạt động.

~~~java
import org.springframework.amqp.core.AcknowledgeMode;
import org.springframework.amqp.rabbit.config.SimpleRabbitListenerContainerFactory;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class ListenerConfig {
    @Bean
    SimpleRabbitListenerContainerFactory ordersListenerFactory(
            ConnectionFactory connectionFactory) {
        SimpleRabbitListenerContainerFactory factory =
                new SimpleRabbitListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setConcurrentConsumers(2);
        factory.setMaxConcurrentConsumers(6);
        factory.setPrefetchCount(20);
        factory.setAcknowledgeMode(AcknowledgeMode.AUTO);
        factory.setDefaultRequeueRejected(false);
        return factory;
    }
}
~~~

**Chú ý:** factory có tên **ordersListenerFactory**; endpoint muốn dùng nó phải chỉ rõ tên này trên annotation, trừ khi bạn cấu hình nó là factory mặc định theo cách thích hợp.

### 2.2. DirectRabbitListenerContainerFactory

Factory này tạo **DirectMessageListenerContainer (DMLC)**. DMLC gọi listener trực tiếp từ thread phân phát delivery của RabbitMQ Java Client, có những khác biệt về threading và các tính năng container.

~~~java
import org.springframework.amqp.core.AcknowledgeMode;
import org.springframework.amqp.rabbit.config.DirectRabbitListenerContainerFactory;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.context.annotation.Bean;

@Bean
DirectRabbitListenerContainerFactory directOrdersFactory(
        ConnectionFactory cf) {
    DirectRabbitListenerContainerFactory factory =
            new DirectRabbitListenerContainerFactory();
    factory.setConnectionFactory(cf);
    factory.setConsumersPerQueue(3);
    factory.setPrefetchCount(20);
    factory.setAcknowledgeMode(AcknowledgeMode.AUTO);
    return factory;
}
~~~

Đoạn trên là phương thức bean đặt trong một lớp **@Configuration**, không phải chương trình standalone. Direct không mặc nhiên nhanh hơn Simple: handler bị chặn lâu bởi database hoặc API ngoài có thể gây ảnh hưởng tới thread xử lý delivery; cần sizing và kiểm thử tải.

### 2.3. Bảng chọn container

| Tiêu chí | Simple (SMLC) | Direct (DMLC) |
| --- | --- | --- |
| Factory | **SimpleRabbitListenerContainerFactory** | **DirectRabbitListenerContainerFactory** |
| Threading | Qua cơ chế chuyển giao của container | Listener chạy trên delivery thread của RabbitMQ client |
| Concurrency | **concurrentConsumers**, **maxConcurrentConsumers** | **consumersPerQueue** |
| @RabbitListener.concurrency | **"3"** hoặc **"3-6"** | Chỉ một số nguyên như **"3"** |
| Nghe nhiều queue | Consumer SMLC có thể xử lý các queue đã cấu hình | Consumer được tính **mỗi queue** |
| Autoscale trong khoảng min/max | Có khi đủ điều kiện | Không dùng chuỗi min-max này |
| Điểm khởi đầu | Thích hợp cho đa số worker nghiệp vụ | Dùng khi hiểu rõ yêu cầu threading/lifecycle |

**StreamListenerContainer** dùng native RabbitMQ Streams là một lớp khác; không tự áp toàn bộ ý nghĩa ACK, prefetch và concurrency của listener AMQP 0.9.1 cho stream container.

## 3. concurrency: tăng worker không phải nhân bản message

Khi nhiều consumer cùng nghe **một queue**, RabbitMQ phân phối các delivery để các consumer **cạnh tranh nhận việc**. Nó không phát một bản sao tới từng consumer. Khi nhiều service cần mọi event, phải tạo **queue riêng cho từng consumer group**, rồi bind vào exchange thích hợp.

~~~mermaid
flowchart LR
    P["Publisher"] --> X{"orders.events"}
    X --> Q[("orders.created.work")]
    Q --> C1["Consumer 1"]
    Q --> C2["Consumer 2"]
    Q --> C3["Consumer 3"]
    C1 --> DB[("Order projection DB")]
    C2 --> DB
    C3 --> DB
~~~

### 3.1. Simple container: một số hoặc khoảng

~~~java
@RabbitListener(
        id = "orders-created-consumer",
        queues = "orders.created.work",
        containerFactory = "ordersListenerFactory",
        concurrency = "3-6")
public void onOrder(String raw) {
    // ...
}
~~~

Với **SMLC**, **"3-6"** có nghĩa:

- **concurrentConsumers=3**: số consumer nền.
- **maxConcurrentConsumers=6**: giới hạn tối đa container có thể tăng tới.
- Container tăng/giảm consumer theo nhịp và mức hoạt động, **không luôn duy trì 6 consumer**.
- Giá trị **concurrency trên annotation** ghi đè những giá trị concurrency tương ứng từ factory **cho endpoint này**.

Nếu đặt **"4"**, SMLC dùng mức consumer cố định 4 theo cú pháp một số. Nếu muốn scale động phải chọn dải phù hợp và kiểm tra điều kiện tự tăng/giảm của phiên bản container.

### 3.2. Direct container: một số nguyên trên mỗi queue

~~~java
@RabbitListener(
        queues = "orders.created.work",
        containerFactory = "directOrdersFactory",
        concurrency = "3")
public void directHandle(String raw) {
    // ...
}
~~~

Trong DMLC, **"3"** đặt **consumersPerQueue=3**. Không dùng **"3-6"**, vì Direct container không hiểu chuỗi này theo min/max. Nếu một endpoint Direct nghe **2 queue** với **consumersPerQueue=3**, sẽ có **6 consumer logic** và các channel tương ứng, nếu tất cả được đăng ký thành công.

### 3.3. Concurrency ảnh hưởng gì?

| Thành phần | Khi concurrency tăng |
| --- | --- |
| Broker | Tăng consumer/channel và công việc phân phối |
| Spring | Nhiều luồng xử lý/ngữ cảnh consumer hơn |
| Database | Có thể tăng tranh chấp connection/lock |
| API ngoài | Có thể đụng rate limit nhanh hơn |
| Prefetch | Tổng message unacked đang nằm phía client có thể tăng |
| Thứ tự | Handler hoàn tất có thể khác thứ tự giao message |
| Idempotency | Cần an toàn khi nhiều consumer xử lý cùng khóa nghiệp vụ |

Nếu DB pool chỉ có 5 connection, tăng từ 5 lên 30 consumer có thể làm nhiều thread chờ DB, timeout và queue unacked tăng. **Không chọn concurrency chỉ theo message/giây**; phải đo thời gian xử lý, sức chịu tải của dependencies và độ trễ mục tiêu.

Spring AMQP hỗ trợ placeholder/SpEL cho thuộc tính concurrency, nhưng thay đổi một file cấu hình không có nghĩa container đang chạy tự cập nhật tức thì. Quản lý thay đổi runtime bằng cơ chế cập nhật container/registry có kiểm soát nếu cần.

## 4. ackMode: AUTO, MANUAL và NONE

**AcknowledgeMode** quyết định thời điểm RabbitMQ biết một delivery đã được xử lý.

| Chế độ | Ai xác nhận? | Khi dùng | Rủi ro chính |
| --- | --- | --- | --- |
| **AUTO** | Spring container ACK sau khi handler xử lý thành công | Lựa chọn mặc định thông dụng cho handler đồng bộ | Exception có thể gây requeue; cần chính sách retry/DLQ |
| **MANUAL** | Ứng dụng gọi **basicAck/basicNack/basicReject** trên Channel | Cần điều khiển rõ lifecycle, một số xử lý async | Quên ACK dẫn đến message unacked, chạm prefetch |
| **NONE** | RabbitMQ coi delivery đã được ACK ngay lúc giao (**auto-ack của broker**) | Best-effort khi chấp nhận mất message | Consumer crash sau delivery có thể mất dữ liệu |

**AUTO của Spring không phải auto-ack của RabbitMQ.** Trong **AUTO**, container gửi basicAck sau khi code trả về thành công; **NONE** mới tương ứng với broker auto-ack/no-ack.

~~~mermaid
sequenceDiagram
    participant B as RabbitMQ
    participant C as Listener Container
    participant L as @RabbitListener
    B->>C: deliver message
    C->>L: convert + invoke method
    alt Xử lý thành công
        L-->>C: return normally
        C-->>B: basicAck (AUTO)
    else Handler lỗi
        L--xC: exception
        C-->>B: reject/nack theo policy
    end
~~~

### 4.1. AUTO: đơn giản nhưng không phải exactly-once

~~~java
@RabbitListener(
        queues = "orders.created.work",
        containerFactory = "ordersListenerFactory",
        ackMode = "AUTO")
public void handle(OrderCreated event) {
    projectionService.applyIdempotently(event);
    // Thành công và return: container ACK.
    // Lỗi RuntimeException: container xử lý reject/requeue.
}
~~~

**projectionService** là dịch vụ nghiệp vụ do ứng dụng định nghĩa. Nếu code đã gửi email hoặc commit DB rồi connection mất trước ACK, broker có thể redeliver message. Consumer phải thiết kế **idempotency** theo eventId.

Khi handler ném exception, một số cấu hình mặc định có **defaultRequeueRejected=true**. Nếu lỗi luôn xảy ra (poison message), việc requeue lập tức có thể tạo vòng lặp nóng. **factory.setDefaultRequeueRejected(false)** khiến message lỗi không được requeue; nếu queue có DLX phù hợp thì broker có thể dead-letter nó.

Không nên dùng **false** một cách thiếu suy nghĩ để bỏ mọi lỗi tạm thời. Với database/API có khả năng phục hồi, hãy dùng **retry có giới hạn và backoff**, sau đó mới chuyển sang DLQ/kênh lỗi.

### 4.2. MANUAL: ứng dụng quyết định ACK/NACK

~~~java
import com.rabbitmq.client.Channel;
import java.io.IOException;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class ManualOrderListener {
    private final OrderProjectionService projectionService;

    public ManualOrderListener(OrderProjectionService projectionService) {
        this.projectionService = projectionService;
    }

    @RabbitListener(
            queues = "orders.created.manual",
            containerFactory = "ordersListenerFactory",
            ackMode = "MANUAL")
    public void handle(Message message, Channel channel)
            throws IOException {

        long tag = message.getMessageProperties().getDeliveryTag();
        try {
            projectionService.applyRawIdempotently(message);
        } catch (RuntimeException failure) {
            // Message lỗi đi DLQ nếu queue có DLX được cấu hình.
            channel.basicNack(tag, false, false);
            return;
        }
        channel.basicAck(tag, false);
    }
}
~~~

Đây là ví dụ minh họa; **orders.created.manual** phải được khai báo riêng và có DLX nếu muốn lỗi đi DLQ. **OrderProjectionService** là dependency nghiệp vụ chưa được triển khai trong đoạn trích.

- **basicAck(tag, false)** ACK đúng một delivery. **multiple=false** tránh ACK nhầm delivery khác.
- **basicNack(tag, false, false)** NACK đúng delivery và không requeue; message đi DLX nếu topology hỗ trợ, ngược lại có thể bị loại.
- **basicReject(tag, false)** reject đúng một message.
- **deliveryTag** gắn với **channel nhận**, không có ý nghĩa như eventId hay trên channel khác sau reconnect.
- Nếu basicAck thất bại sau DB commit, message vẫn có khả năng redeliver: **MANUAL không tự tạo exactly-once**.
- Không ACK/NACK hai lần cùng delivery. Double ACK có thể gây lỗi giao thức và đóng channel.

Đoạn code trên đưa mọi RuntimeException vào luồng lỗi; trong production cần phân loại lỗi temporary/permanent và bounded retry trước khi quyết định dead-letter. **Không requeue=true vô hạn** cho dữ liệu lỗi cố định.

### 4.3. NONE: broker auto-ack

~~~java
@RabbitListener(
        queues = "telemetry.best-effort",
        ackMode = "NONE")
public void onTelemetry(String data) {
    // Chấp nhận mất message nếu consumer lỗi sau khi nhận.
}
~~~

Với NONE, broker coi message hoàn tất ngay khi giao, trước khi handler chắc chắn xử lý xong. Không chọn cho đơn hàng, thanh toán, hóa đơn, cập nhật tồn kho hoặc các tác vụ phải hoàn thành.

### 4.4. ACK khi xử lý bất đồng bộ và transaction

Với **@RabbitListener** trả **CompletableFuture/Mono** hoặc Kotlin suspend, ACK phải theo kết quả bất đồng bộ, không đơn giản theo thời điểm method tạo future. Các nhánh Spring AMQP hiện đại có hỗ trợ tự chuyển sang **MANUAL** cho một số async return types, nhưng cần kiểm tra API/exception completion tương ứng và tránh tự ACK mâu thuẫn.

**channelTransacted=true** là cơ chế transaction ở AMQP channel; nó không phải transaction phân tán nguyên tử với database hay HTTP service. Nếu DB và broker phải nhất quán khi phát event, cân nhắc **transactional outbox**; nếu consume có thể redeliver, dùng idempotency.

## 5. messageConverter: đưa byte[] thành DTO

Một AMQP Message có **byte[] body** và **MessageProperties**. Để method nhận **OrderCreated event**, Spring cần chuyển payload đúng định dạng.

~~~text
RabbitMQ delivery
    ↓
org.springframework.amqp.core.Message (byte[] + MessageProperties)
    ↓ [1] AMQP MessageConverter
Spring Messaging Message<?> / payload
    ↓ [2] Method argument converter, nếu cần
@RabbitListener(OrderCreated event)
~~~

Spring AMQP sử dụng **hai bước conversion** với annotated listener:

1. **AMQP MessageConverter** đổi message AMQP thành payload Java/Spring Messaging message. Đây là converter thường cấu hình qua listener factory hoặc annotation.
2. **Method argument conversion** bổ sung cho việc khớp kiểu tham số method, sử dụng hạ tầng Spring Messaging.

Cấu hình một AMQP MessageConverter không đồng nghĩa với thay đổi converter ở bước thứ hai.

### 5.1. Những converter hay gặp

| Converter | Phạm vi | Điểm cần nhớ |
| --- | --- | --- |
| **SimpleMessageConverter** | String, byte[], Java Serializable theo chính sách | Không tự parse JSON thành DTO |
| **Jackson2JsonMessageConverter** | JSON DTO trong Spring AMQP 3.x / Jackson 2 | Phải thống nhất type mapping, content type |
| **JacksonJsonMessageConverter** | JSON DTO trong Spring AMQP 4.x / Jackson 3 | API khác nhánh Jackson 2, không trộn dependency |
| **ContentTypeDelegatingMessageConverter** | Chọn converter theo contentType | Cần mapping MIME và fallback rõ ràng |
| **Custom converter** | Protobuf/Avro/binary | Phải quản lý format, schema và lỗi |

Nếu producer gửi JSON body với **contentType=application/json** nhưng listener dùng SimpleMessageConverter, kết quả có thể là **byte[]**, không phải DTO.

### 5.2. Converter trên factory

~~~java
import org.springframework.amqp.rabbit.config.SimpleRabbitListenerContainerFactory;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.amqp.support.converter.Jackson2JsonMessageConverter;

SimpleRabbitListenerContainerFactory factory =
        new SimpleRabbitListenerContainerFactory();
factory.setConnectionFactory(connectionFactory);
factory.setMessageConverter(new Jackson2JsonMessageConverter());
~~~

Đây là code cấu hình trong một @Configuration method; converter áp dụng mặc định cho những endpoint dùng factory này.

### 5.3. Converter trên từng annotation

Từ Spring AMQP 2.3, **@RabbitListener** có thuộc tính **messageConverter** để chọn **bean name** thay thế converter của factory cho endpoint đó.

~~~java
@RabbitListener(
        queues = "orders.created.work",
        containerFactory = "ordersListenerFactory",
        messageConverter = "ordersJsonConverter")
public void handle(OrderCreated event) {
    // ...
}
~~~

Nếu nhiều endpoint cần nhiều format khác nhau, cách này tránh tạo một factory riêng chỉ để thay converter. **messageConverter ở đây là tên bean**, không phải chuỗi MIME type.

### 5.4. Type headers và kiểu suy ra

Producer Spring JSON converter có thể thêm **__TypeId__** để mô tả type Java/alias. Với listener method có một payload argument concrete, Spring AMQP thường suy ra kiểu đích **từ chính tham số method**, thậm chí ưu tiên kiểu ấy hơn type header. Với interface, abstract class, generic phức tạp hoặc class-level @RabbitListener, cách chọn type có thể khác.

Nên chọn **alias ổn định**, **schemaVersion**, **trusted packages rõ ràng**, validate DTO và không tự mở toàn bộ package bằng wildcard chỉ để chữa lỗi mapping. **Lỗi JSON có thể xảy ra trước khi method được gọi**, nên try/catch trong method không bắt được mọi conversion exception.

## 6. Ví dụ Java: kết hợp cả bốn thuộc tính

Ví dụ này nhắm tới **Java 17 + Spring Boot 3.x + Spring AMQP 3.x/Jackson 2**. Với Spring AMQP 4.x cần thay bằng API JSON converter Jackson 3 phù hợp. Giả định project có **spring-boot-starter-amqp**, Jackson, RabbitMQ AMQP 0.9.1 và quyền declare tài nguyên.

### 6.1. Event DTO

~~~java
package com.example.contracts;

public record OrderCreated(
        String eventId,
        String orderId,
        long totalAmount) {
}
~~~

Ví dụ JSON:

~~~json
{
  "eventId": "evt-101",
  "orderId": "ORD-1001",
  "totalAmount": 150000
}
~~~

**eventId** phải ổn định giữa các lần retry của cùng sự kiện để consumer xử lý trùng an toàn.

### 6.2. Topology: exchange, work queue và DLQ

~~~java
package com.example.amqp;

import org.springframework.amqp.core.*;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrdersTopology {
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
    Binding workBinding(
            @Qualifier("ordersWorkQueue") Queue queue,
            TopicExchange ordersExchange) {
        return BindingBuilder.bind(queue)
                .to(ordersExchange).with("order.created");
    }

    @Bean
    Binding deadLetterBinding(
            @Qualifier("ordersDlq") Queue queue,
            DirectExchange ordersDlx) {
        return BindingBuilder.bind(queue)
                .to(ordersDlx).with("orders.created.failed");
    }
}
~~~

Một message ở work queue bị reject với **requeue=false** có thể được broker chuyển tới **orders.created.dlq**. Trên production, nên cân nhắc dùng **RabbitMQ policy** cho DLX thay vì hardcode mọi argument nhằm thuận tiện cập nhật vận hành.

### 6.3. Converter và factory

~~~java
package com.example.amqp;

import com.example.contracts.OrderCreated;
import java.util.Map;
import org.springframework.amqp.core.AcknowledgeMode;
import org.springframework.amqp.rabbit.annotation.EnableRabbit;
import org.springframework.amqp.rabbit.config.SimpleRabbitListenerContainerFactory;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.amqp.support.converter.DefaultClassMapper;
import org.springframework.amqp.support.converter.Jackson2JsonMessageConverter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableRabbit
public class OrdersListenerConfig {
    @Bean
    DefaultClassMapper ordersClassMapper() {
        DefaultClassMapper mapper = new DefaultClassMapper();
        mapper.setIdClassMapping(
                Map.of("order.created.v1", OrderCreated.class));
        mapper.setTrustedPackages("com.example.contracts");
        return mapper; // Spring thực hiện lifecycle initialization.
    }

    @Bean
    Jackson2JsonMessageConverter ordersJsonConverter(
            DefaultClassMapper ordersClassMapper) {
        Jackson2JsonMessageConverter converter =
                new Jackson2JsonMessageConverter();
        converter.setClassMapper(ordersClassMapper);
        return converter;
    }

    @Bean
    SimpleRabbitListenerContainerFactory ordersListenerFactory(
            ConnectionFactory cf,
            Jackson2JsonMessageConverter ordersJsonConverter) {
        SimpleRabbitListenerContainerFactory factory =
                new SimpleRabbitListenerContainerFactory();
        factory.setConnectionFactory(cf);
        factory.setConcurrentConsumers(2);
        factory.setMaxConcurrentConsumers(6);
        factory.setPrefetchCount(20);
        factory.setAcknowledgeMode(AcknowledgeMode.AUTO);
        factory.setDefaultRequeueRejected(false);
        factory.setMessageConverter(ordersJsonConverter);
        return factory;
    }
}
~~~

ClassMapper dùng **order.created.v1** thay vì ràng buộc message vào tên package Java. **Trusted packages** phải giới hạn các DTO hợp đồng mà ứng dụng mong đợi.

### 6.4. Publisher cùng contract

~~~java
package com.example.amqp;

import com.example.contracts.OrderCreated;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.amqp.support.converter.Jackson2JsonMessageConverter;
import org.springframework.stereotype.Service;

@Service
public class OrdersPublisher {
    private final RabbitTemplate template;

    public OrdersPublisher(ConnectionFactory cf,
                           Jackson2JsonMessageConverter converter) {
        template = new RabbitTemplate(cf);
        template.setMessageConverter(converter);
    }

    public void publish(OrderCreated event) {
        template.convertAndSend(
                "orders.events",
                "order.created",
                event,
                message -> {
                    message.getMessageProperties().setMessageId(event.eventId());
                    message.getMessageProperties().setHeader("schemaVersion", 1);
                    return message;
                });
    }
}
~~~

Ví dụ tự tạo RabbitTemplate để minh họa converter; production thường đặt cấu hình template tập trung thành bean. **Publisher confirms/returns** cần cấu hình riêng nếu muốn theo dõi kết quả publish, và **transactional outbox** giúp giảm khe hở giữa database và publish.

### 6.5. Listener sử dụng cả bốn tham số

~~~java
package com.example.amqp;

import com.example.contracts.OrderCreated;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class OrderCreatedListener {
    private final OrderProjectionService service;

    public OrderCreatedListener(OrderProjectionService service) {
        this.service = service;
    }

    @RabbitListener(
            id = "orders-created-consumer",
            queues = "orders.created.work",
            containerFactory = "ordersListenerFactory",
            concurrency = "3-6",
            ackMode = "AUTO",
            messageConverter = "ordersJsonConverter")
    public void handle(OrderCreated event) {
        service.applyIdempotently(event);
    }
}
~~~

**OrderProjectionService** là dependency nghiệp vụ do ứng dụng cung cấp. Method **applyIdempotently** phải validate event, commit tác động nghiệp vụ và chống trùng theo eventId trước khi trả về.

| Thuộc tính | Giá trị | Tác động |
| --- | --- | --- |
| **queues** | orders.created.work | Queue đã được khai báo |
| **containerFactory** | ordersListenerFactory | Chọn Simple factory |
| **concurrency** | "3-6" | Ghi đè dải 2–6 trên factory thành 3–6 |
| **ackMode** | "AUTO" | Ghi đè acknowledgeMode trên factory nếu khác |
| **messageConverter** | ordersJsonConverter | Chọn converter bean cho listener này |
| **id** | orders-created-consumer | Dùng theo dõi và quản lý endpoint |

Trong ví dụ, **ackMode** và **messageConverter** lặp giá trị factory có chủ đích để cho thấy cách dùng thuộc tính annotation; ứng dụng không bắt buộc khai báo chúng ở cả hai nơi.

## 7. Spring Boot application.yml: cấu hình chung

Nếu sử dụng Spring Boot auto-configured factory, một cấu hình gọn cho Simple listener:

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
        concurrency: 2
        max-concurrency: 6
        prefetch: 20
        acknowledge-mode: auto
        default-requeue-rejected: false
        retry:
          enabled: true
          max-attempts: 3
          initial-interval: 500ms
          multiplier: 2.0
          max-interval: 3s
~~~

**guest/guest** chỉ dành cho RabbitMQ local trong môi trường học; production cần user riêng, secrets và TLS theo yêu cầu bảo mật.

- **listener.type=simple** chọn loại container mà Boot tự cấu hình.
- **simple.concurrency/max-concurrency** đặt số consumer nền/tối đa.
- **prefetch** giới hạn số delivery chưa ACK có thể chờ phía consumer.
- **acknowledge-mode=auto** cho container tự ACK khi xử lý thành công.
- **default-requeue-rejected=false** tránh mặc định requeue lỗi liên tục khi không được phục hồi.
- **retry** là listener retry, **khác** retry của RabbitTemplate ở phía publisher.

**Cảnh báo:** khi bạn tự tạo một bean SimpleRabbitListenerContainerFactory như mục 6, các Spring Boot properties có thể **không tự động được áp vào bean đó**. Hoặc cấu hình thủ công nhất quán, hoặc dùng **SimpleRabbitListenerContainerFactoryConfigurer** của Spring Boot:

~~~java
import org.springframework.amqp.rabbit.config.SimpleRabbitListenerContainerFactory;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.boot.autoconfigure.amqp.SimpleRabbitListenerContainerFactoryConfigurer;
import org.springframework.context.annotation.Bean;

@Bean
SimpleRabbitListenerContainerFactory ordersListenerFactory(
        SimpleRabbitListenerContainerFactoryConfigurer configurer,
        ConnectionFactory connectionFactory,
        Jackson2JsonMessageConverter ordersJsonConverter) {
    SimpleRabbitListenerContainerFactory factory =
            new SimpleRabbitListenerContainerFactory();
    configurer.configure(factory, connectionFactory);
    factory.setMessageConverter(ordersJsonConverter);
    return factory;
}
~~~

Đây là **cách thay thế** cho bean factory của mục 6, không khai báo cả hai cùng tên. Ví dụ dùng API của Spring Boot 3.x; nhánh Boot khác phải kiểm tra tài liệu API tương ứng.

Đối với Direct container do Boot tự cấu hình:

~~~yaml
spring:
  rabbitmq:
    listener:
      type: direct
      direct:
        consumers-per-queue: 3
        prefetch: 20
        acknowledge-mode: auto
~~~

Trên Direct container, **@RabbitListener(concurrency="3")** là cú pháp phù hợp; không áp min-max "3-6" như Simple.

## 8. Thứ tự ưu tiên và phạm vi ghi đè

~~~text
Boot application.yml (nếu dùng auto-configuration)
                   |
                   v
RabbitListenerContainerFactory bean
    |-- ConnectionFactory
    |-- concurrency / prefetch
    |-- acknowledgeMode
    +-- MessageConverter
                   |
                   v
@RabbitListener endpoint
    |-- containerFactory chọn factory cụ thể
    |-- concurrency override cho endpoint
    |-- ackMode override cho endpoint
    +-- messageConverter override cho endpoint
                   |
                   v
Listener container đã được đăng ký
~~~

| Hai nơi có cùng thiết lập | Giá trị hiệu lực thường dùng |
| --- | --- |
| Factory SMLC 2–6, annotation **concurrency="3-6"** | Dải 3–6 cho endpoint |
| Factory AUTO, annotation **ackMode="MANUAL"** | Manual ACK cho endpoint |
| Factory Simple converter, annotation **messageConverter="ordersJsonConverter"** | JSON converter của endpoint |
| Factory prefetch=20, annotation không có prefetch | Prefetch=20 |
| Không khai báo containerFactory | Factory mặc định được đăng ký, thường bean tên rabbitListenerContainerFactory |

**Không phải mọi thuộc tính của container đều có override trên annotation.** Khi cần prefetch hoặc error handler khác nhau giữa các nhóm listener, cấu hình factory riêng hoặc container customizer phù hợp.

## 9. Lỗi conversion, retry, dead-letter và idempotency

Một message có thể thất bại **trước khi method listener được gọi**, ví dụ JSON sai cú pháp hoặc type header trỏ tới class không được tin cậy.

~~~mermaid
flowchart TD
    Q[("orders.created.work")] --> C["MessageConverter"]
    C --> V{"Deserialize hợp lệ?"}
    V -->|"Không"| E["Conversion failure<br/>trước @RabbitListener"]
    V -->|"Có"| H["@RabbitListener handler"]
    H --> R{"Nghiệp vụ thành công?"}
    R -->|"Có"| A["ACK (AUTO)"]
    R -->|"Không"| X["Retry giới hạn / reject"]
    E --> X
    X --> DLQ[("DLQ / error queue")]
~~~

**Try/catch trong @RabbitListener không bắt được lỗi converter xảy ra trước khi method chạy.** Phải xử lý ở tầng **listener container/error handler**, có thể kết hợp retry interceptor, recoverer và dead-letter topology.

### 9.1. Phân biệt lỗi tạm thời và lỗi vĩnh viễn

| Lỗi | Phân loại | Cách xử lý |
| --- | --- | --- |
| JSON sai cú pháp | Permanent | Reject/DLQ, sửa producer/schema |
| Header type không tin cậy | Permanent | Reject, cảnh báo security/contract |
| schemaVersion chưa hỗ trợ | Permanent cho code hiện tại | Cách ly và xử lý khi nâng cấp |
| Database tạm mất kết nối | Transient | Retry có backoff và giới hạn, sau đó kênh lỗi |
| Timeout API ngoài | Thường transient nhưng kết quả có thể bất định | Retry có idempotency key; reconciliation khi cần |
| Broker mất connection | Hạ tầng | Container recovery, xử lý khả năng redelivery |
| Publish trùng từ producer | Không phải lỗi converter | Idempotent consumer theo eventId |

**defaultRequeueRejected=true** có thể tạo vòng lặp nóng cho poison message. **defaultRequeueRejected=false** chấm dứt việc requeue mặc định, nhưng không tự tạo delayed retries. Phải thiết kế retry policy theo loại lỗi.

### 9.2. Consumer ACK không bảo đảm exactly-once

~~~text
T0  Consumer nhận OrderCreated(eventId=e-101)
T1  DB transaction commit thành công
T2  Connection mất trước khi ACK tới RabbitMQ
T3  RabbitMQ redeliver e-101
T4  Consumer phải nhận diện e-101 đã được xử lý
~~~

Dùng **processed_events(consumer_name, event_id)** có unique constraint, ghi trong cùng DB transaction với tác động nghiệp vụ. Nếu external API như gửi email hoặc thanh toán không hỗ trợ transaction DB, cân nhắc notification outbox, idempotency key hoặc cơ chế reconciliation.

**Publisher confirm** kiểm tra phía gửi; **consumer ACK** kiểm tra lần giao; **idempotency** bảo vệ tác động nghiệp vụ. Ba khái niệm không thể thay thế nhau.

## 10. Prefetch, concurrency và thông lượng

Kết hợp **prefetch** và số consumer ảnh hưởng số message **unacked** đang nằm phía ứng dụng.

| Cấu hình | Consumer thực tế | Prefetch/consumer | Unacked tiềm năng, minh họa |
| --- | ---: | ---: | ---: |
| SMLC cố định 2 | 2 | 10 | Khoảng 20 |
| SMLC dải 2–6, hiện chạy 4 | 4 | 20 | Khoảng 80 |
| DMLC nghe 2 queue, 3 consumer/queue | 6 | 20 | Khoảng 120 |

Đây là ước lượng theo số consumer và QoS trong tình huống đơn giản, không phải số liệu broker bắt buộc đúng ở mọi thời điểm. Các tùy chọn batch/transactions/global QoS ảnh hưởng chi tiết thực tế.

**Giảm prefetch** khi message lớn, handler chậm hoặc cần giảm độ lệch phân phối. **Tăng concurrency** chỉ khi DB pool, CPU, API ngoài và broker có đủ capacity. Nếu cần giữ thứ tự nghiệp vụ, nhiều consumer và prefetch cao có thể khiến event cùng aggregate hoàn tất lệch thứ tự; dùng orderId/version/partition hoặc thiết kế serial theo khóa khi cần.

### Tính toán sơ bộ

Giả sử một handler mất khoảng **200 ms** cho một event. Một consumer đồng bộ lý tưởng có thể xử lý khoảng **5 event/giây** trước overhead. Muốn gần **40 event/giây**, có thể cần khoảng **8 consumer**, **nếu** DB/API chịu được mức song song đó. Đây chỉ là mô hình ước lượng ban đầu; cần đo P95 latency, queue lag và failure rate để điều chỉnh.

## 11. Quan sát và điều khiển listener

Đặt **id** cho endpoint để có thể tra cứu bằng **RabbitListenerEndpointRegistry**:

~~~java
import org.springframework.amqp.rabbit.listener.RabbitListenerEndpointRegistry;
import org.springframework.stereotype.Service;

@Service
public class ListenerOperator {
    private final RabbitListenerEndpointRegistry registry;

    public ListenerOperator(RabbitListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public void pauseOrderListener() {
        var container =
                registry.getListenerContainer("orders-created-consumer");
        if (container != null) {
            container.stop();
        }
    }
}
~~~

Chỉ expose thao tác pause/start cho operator được phân quyền, không cho public API tùy ý điều khiển consumer.

| Metric / dấu hiệu | Cần quan sát |
| --- | --- |
| **Consumers per queue** | Giá trị thực tế so với concurrency; SMLC max không phải lúc nào cũng chạy |
| **Queue ready** | Backlog chưa được giao |
| **Queue unacked** | Delivery đã gửi nhưng chưa ACK, có thể do prefetch/handler chậm |
| **Deliver/ACK rate** | Tốc độ tiêu thụ và xác nhận |
| **Redelivery rate** | Reconnect, exception hoặc retry loop |
| **DLQ depth** | Số message lỗi chưa được xử lý |
| **Conversion errors** | Sai JSON/content type/type mapper |
| **Handler latency P95/P99** | Nút nghẽn DB/API/CPU |
| **Channel/connection count** | Tài nguyên client/broker |
| **Duplicate event count** | Cần theo dõi khi publisher retry và consumer redelivery |

Nên ghi eventId, correlationId, routing key và tên queue trong log/tracing khi phù hợp. Không log toàn bộ message chứa dữ liệu nhạy cảm.

## 12. Lỗi cấu hình phổ biến

| Triệu chứng | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| Listener không chạy | Chưa bật hạ tầng @RabbitListener, queue thiếu hoặc cấu hình sai factory | Kiểm tra @EnableRabbit/Boot, bean, topology, lỗi startup |
| Factory tùy biến không được dùng | Sai tên bean **containerFactory** | Kiểm tra bean name trên annotation |
| Dùng "3-6" với DMLC | DMLC chỉ nhận một số nguyên consumersPerQueue | Dùng "3" hoặc chuyển Simple |
| SMLC không tăng ngay đến max | Scale động phụ thuộc ngưỡng active/idle | Quan sát consumer count theo thời gian |
| Message chỉ đến một trong hai listener | Hai listener cùng consume một queue | Tạo queue/binding riêng nếu muốn fanout |
| MANUAL không ACK | Code bỏ qua nhánh ACK/NACK | Rà soát tất cả nhánh xử lý, unacked count |
| AUTO return thành công dù DB lỗi | Code nuốt exception | Propagate exception hoặc xử lý retry tường minh |
| NONE mất dữ liệu sau crash | Broker auto-ack ngay khi giao | Chuyển AUTO/MANUAL cho nghiệp vụ quan trọng |
| JSON thành byte[] | Factory dùng SimpleMessageConverter | Chọn JSON converter ở factory/annotation |
| DTO không resolve | Sai type headers, alias, trusted packages | Cấu hình hợp đồng và allowlist |
| Lỗi conversion không vào method | Lỗi xảy ra trước method | Container error handler, retry/recoverer/DLQ |
| Message lỗi chạy lặp vô hạn | Requeue mặc định, không có backoff | Retry giới hạn, reject/DLQ |
| Boot properties bị bỏ qua | Custom factory không dùng Boot configurer | Cấu hình trực tiếp hoặc dùng configurer |
| Tăng concurrency mà throughput giảm | DB pool/API ngoài đã nghẽn | Đo dependency bottleneck, giới hạn consumer |
| Event bị xử lý trùng | ACK thất lạc hoặc producer gửi lại | Idempotency theo eventId |

### Quy trình chẩn đoán

1. Xác minh listener đang dùng **Simple hay Direct container**, factory bean nào và queue nào.
2. Kiểm tra **concurrency** ở annotation/factory/Boot config và số consumer thực tế trên broker.
3. Kiểm tra **ackMode**: ai ACK/NACK và có nhánh quên xác nhận không?
4. Kiểm tra converter thực tế, contentType, charset, type headers và DTO.
5. Đối chiếu **Ready, Unacked, Consumer count, Deliver/ACK rate** với exception, DB latency và DLQ.
6. Thử lại trong môi trường test với một thay đổi mỗi lần thay vì tăng mọi giới hạn cùng lúc.

## 13. Bài tập thực hành

### Bài 1 — Factory mặc định và factory riêng

Khai báo @RabbitListener không chỉ rõ containerFactory, quan sát factory mặc định. Tạo bean **ordersListenerFactory** đặt prefetch khác, cấu hình annotation sử dụng nó và giải thích vì sao tên bean quyết định factory được chọn.

### Bài 2 — Simple concurrency

Dùng **concurrency="2-6"**, publish 2.000 message với handler có độ trễ giả lập. Đo số consumer hiện tại, queue ready, unacked, tốc độ ACK theo thời gian. Vì sao max không xuất hiện ngay?

### Bài 3 — Direct concurrency

Chuyển sang DMLC, đặt **consumersPerQueue=3** và annotation **concurrency="3"**. Giải thích vì sao dạng **"3-6"** không hợp lệ. Nếu cùng endpoint nghe hai queue, có bao nhiêu consumer logic?

### Bài 4 — So sánh AUTO/MANUAL/NONE

Dùng ba queue thử nghiệm riêng, xử lý thành công và cố tình ném exception. Với MANUAL, quan sát deliveryTag, basicAck và basicNack. Với AUTO, quan sát ACK khi method return và cách xử lý exception. Với NONE, mô phỏng consumer crash sau khi broker giao.

### Bài 5 — Converter override

Gửi JSON OrderCreated có contentType application/json. Tạo một listener dùng SimpleMessageConverter và một listener khác dùng **ordersJsonConverter** trên hai queue riêng. Quan sát kiểu payload; sau đó thử annotation **messageConverter="ordersJsonConverter"**.

### Bài 6 — Poison message và DLQ

Gửi JSON lỗi hoặc schemaVersion chưa được hỗ trợ. Xác minh error handler nhận lỗi trước khi listener method chạy, tránh requeue nóng và đưa message tới DLQ theo cấu hình. Tách lỗi vĩnh viễn với lỗi DB tạm thời cần retry.

### Bài 7 — Concurrency, prefetch và DB pool

Đặt DB pool tối đa 5 connection, handler giả lập 200 ms, queue có 10.000 message. So sánh cấu hình 2/5/15 consumer và prefetch 5/20/100. Ghi throughput, P95 latency, unacked và DB pool wait; chọn cấu hình dựa trên đo thực tế.

### Bài 8 — ACK thất lạc và chống trùng

Producer gửi cùng eventId hai lần vì confirm timeout; thêm tình huống listener commit DB rồi mất connection trước ACK. Ghi processed_events cùng transaction nghiệp vụ để chứng minh một eventId chỉ tạo một tác động hợp lệ trong consumer group.

### Câu hỏi tự đánh giá

1. containerFactory là bean gì, có giống ConnectionFactory không?
2. SMLC hiểu "2-5" ra sao? DMLC có hỗ trợ dạng chuỗi ấy không?
3. DMLC nghe ba queue với consumersPerQueue=2 cần bao nhiêu consumer?
4. Vì sao Spring AUTO khác RabbitMQ auto-ack?
5. MANUAL quên ACK/NACK sẽ gây triệu chứng gì?
6. basicNack(tag,false,false) có đưa message vào DLQ nếu queue không có DLX không?
7. Converter ở annotation hay factory được ưu tiên nếu cấu hình cả hai?
8. Lỗi deserialize trước method phải xử lý ở tầng nào?
9. Vì sao DB commit rồi ACK mất có thể gây message trùng?
10. Vì sao tăng concurrency không chắc tăng throughput khi DB pool nhỏ?
11. Publisher confirm, consumer ACK và idempotency có những mục đích gì?
12. Cần giám sát cả queue ready lẫn unacked và DLQ depth vì sao?

## 14. Tài liệu tham khảo

- [Spring AMQP — Enable Listener Endpoint Annotations](https://docs.spring.io/spring-amqp/reference/amqp/receiving-messages/async-annotation-driven/enable.html): @EnableRabbit, factory mặc định, annotation concurrency/ackMode.
- [Spring AMQP — Choosing a Container](https://docs.spring.io/spring-amqp/reference/amqp/receiving-messages/choose-container.html): Simple vs Direct container.
- [Spring AMQP — Listener Concurrency](https://docs.spring.io/spring-amqp/reference/amqp/listener-concurrency.html): scale min/max, consumersPerQueue.
- [Spring AMQP — Message Listener Container Configuration](https://docs.spring.io/spring-amqp/reference/amqp/containerAttributes.html): ackMode, prefetch, requeue, transactions.
- [Spring AMQP — Message Conversion for Annotated Methods](https://docs.spring.io/spring-amqp/reference/amqp/receiving-messages/async-annotation-driven/conversion.html): hai tầng conversion, messageConverter annotation override.
- [Spring AMQP — Message Converters](https://docs.spring.io/spring-amqp/reference/amqp/message-converters.html): SimpleMessageConverter và JSON.
- [Spring AMQP — Asynchronous @RabbitListener Return Types](https://docs.spring.io/spring-amqp/reference/amqp/receiving-messages/async-returns.html): async ACK và exception.
- [Spring Boot — AMQP](https://docs.spring.io/spring-boot/reference/messaging/amqp.html): auto-configured factory và listener properties.
- [RabbitMQ — Consumer Acknowledgements and Publisher Confirms](https://www.rabbitmq.com/docs/confirms): ACK/NACK, redelivery và confirms.

---

**Ghi nhớ:** **containerFactory** chọn cách Spring tạo và vận hành consumer; **concurrency** quyết định mức song song theo Simple hoặc Direct container; **ackMode** xác định trách nhiệm ACK/NACK; **messageConverter** biến byte[] thành Java DTO. Annotation có thể ghi đè concurrency, ackMode và converter **cho từng endpoint**, nhưng phải chọn đúng bean và hiểu loại container. Với nghiệp vụ cần tin cậy, luôn thiết kế **prefetch, retry/DLQ, idempotency, publisher confirms và quan sát ready/unacked** cùng bốn thuộc tính này.
