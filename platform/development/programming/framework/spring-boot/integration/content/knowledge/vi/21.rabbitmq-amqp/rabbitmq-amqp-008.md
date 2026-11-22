# Thử lại, requeue và tránh vòng lặp thông điệp lỗi trong RabbitMQ/AMQP

Một consumer của `order-service` đọc sự kiện `OrderPaid` từ RabbitMQ để tạo vận đơn. Nếu dịch vụ vận chuyển tạm thời trả HTTP 503, **thử lại** có thể giúp xử lý thành công. Nhưng nếu thông điệp thiếu mã đơn hàng, gửi lại nó 10.000 lần vẫn không sửa được dữ liệu. Tình huống thứ ba nguy hiểm hơn: nghiệp vụ đã lưu vận đơn vào cơ sở dữ liệu nhưng consumer mất kết nối trước khi xác nhận với RabbitMQ. Thông điệp có thể đến lần nữa và phải được **chống xử lý trùng lặp**.

Trong chương **RabbitMQ và AMQP** của module **SPRING_BOOT_INTEGRATION**, nhiệm vụ không chỉ là gọi `@RabbitListener`. Ta cần thống nhất cơ chế phát/nhận, hợp đồng dữ liệu, giới hạn retry, acknowledgement, requeue, dead-letter exchange, giao dịch, idempotency và theo dõi vận hành. Ba từ dễ nhầm phải được tách rõ:

- **Retry**: thử chạy lại một thao tác đã thất bại. Có thể xảy ra trong *cùng một lần RabbitMQ giao message cho listener*, hoặc bằng cách gửi một lần delivery khác sau một khoảng trì hoãn.
- **Requeue**: yêu cầu broker đưa delivery chưa được xử lý thành công trở lại queue, thường để giao lại. `requeue=true` tự nó **không cung cấp backoff** hay giới hạn số lần thử.
- **Dead-letter**: đưa message ra khỏi queue ban đầu khi xảy ra một trong các điều kiện broker hỗ trợ, chẳng hạn reject/nack với `requeue=false`; với DLX được cấu hình, message được định tuyến tới nơi xử lý riêng (thường là DLQ).

Một hệ thống đáng tin cậy phải có đường đi xác định cho message **thành công**, **lỗi tạm thời**, **lỗi không thể khắc phục bằng retry** và **đã hết ngân sách retry**.

> Phạm vi ví dụ: Spring Boot 3.x, Spring AMQP/Spring Rabbit với `spring-boot-starter-amqp` và RabbitMQ hỗ trợ AMQP 0-9-1. Các property `listener.simple` áp dụng cho container kiểu Simple; nếu dự án dùng Direct container, factory riêng hoặc phiên bản khác, phải đặt chính sách tương ứng. Hành vi quorum queue, DLX và một số policy thay đổi theo phiên bản/configuration broker.

## 1. Từ publish đến ack: message đi đâu khi consumer lỗi?

Một sơ đồ thường gặp:

~~~mermaid
flowchart LR
    P["order-service publisher"] --> E["Exchange: orders.events"]
    E --> Q[("Queue: shipping.jobs")]
    Q --> C["shipping-service @RabbitListener"]
    C -->|Thành công + ACK| OK["Hoàn tất delivery"]
    C -->|Reject/Nack requeue=false| DLX["Exchange: orders.dlx"]
    DLX --> DLQ[("Queue: shipping.dead")]
    C -->|Nack requeue=true| Q
~~~

**Producer** publish tới một *exchange* với routing key; exchange phân phối đến các queue đã được binding phù hợp. Consumer nhận delivery từ một queue và xác nhận theo **delivery tag trên channel**. Broker quản lý trạng thái message của queue dựa trên ack/nack/reject và các chính sách liên quan.

Các thao tác AMQP căn bản:

| Thao tác | Ý nghĩa với một delivery | Điều cần nhớ |
| --- | --- | --- |
| `basicAck(tag, false)` | Đã xử lý xong, broker có thể loại delivery khỏi queue | Chỉ gửi sau khi side effect cần bảo vệ đã hoàn tất |
| `basicReject(tag, true)` | Từ chối và yêu cầu requeue | Có thể giao lại ngay, dẫn đến vòng lặp nhanh |
| `basicReject(tag, false)` | Từ chối và không requeue | Dead-letter nếu queue có DLX; nếu không có đường xử lý hợp lệ có thể mất message |
| `basicNack(tag, false, true)` | Negative acknowledgement, requeue một delivery | Không tự tăng thời gian chờ giữa các lần giao |
| `basicNack(tag, false, false)` | Negative acknowledgement, không requeue | Thường kết thúc ở DLX/DLQ đã cấu hình |
| `basicNack(tag, true, ...)` | Có thể tác động **nhiều** delivery còn unacked đến tag trên cùng channel | Phải hiểu `multiple=true` trước khi dùng để tránh tác động các message khác |
| Channel/connection đứt khi delivery chưa ack | Broker có thể đưa message trở lại trạng thái chờ để giao lại | Consumer có thể đã commit side effect trước khi mất kết nối |

Phân biệt **ack trong AMQP** với **publisher confirm**: producer nhận confirm từ broker không có nghĩa consumer đã xử lý thành công; consumer gửi ack cũng không xác nhận rằng một publish tiếp theo của ứng dụng đã được broker lưu. Hai loại tín hiệu phục vụ hai đoạn khác nhau của luồng.

### Spring `AUTO` acknowledgment không phải RabbitMQ `autoAck`

Khi cấu hình Spring AMQP listener `acknowledge-mode: auto`, **Spring container** tự gửi ack sau khi phương thức listener xử lý thành công; khi có exception, container quyết định reject/nack theo loại lỗi và cấu hình. Đây không phải là chế độ RabbitMQ `autoAck=true`, nơi delivery được coi là đã nhận ngay khi giao mà không chờ xử lý.

Nếu chọn `acknowledge-mode: manual`, ứng dụng phải tự xác nhận đúng delivery tag và chịu trách nhiệm xử lý lỗi, shutdown, double-ack. Chỉ dùng manual khi cần kiểm soát cụ thể; đa số trường hợp có thể kết hợp Spring AUTO, retry và dead-letter an toàn.

## 2. Requeue=true nguy hiểm thế nào?

Giả sử `shipping.jobs` có một message không hợp lệ `{"orderId":null}`. Listener luôn ném exception. Nếu container luôn reject/nack với `requeue=true`:

1. Broker giao message lỗi cho consumer A.
2. A ném exception và requeue.
3. Broker đặt message trở lại queue, có thể giao ngay cho A hoặc consumer B.
4. Consumer lại lỗi. Chu trình có thể lặp nhanh, chiếm CPU, log, network, kết nối và ngăn message tốt được xử lý.

~~~mermaid
flowchart TD
    Q[("shipping.jobs")] --> C["Listener"]
    C --> V{"Dữ liệu hợp lệ?"}
    V -->|Không| N["NACK requeue=true"]
    N --> Q
    V -->|Có| W["Xử lý nghiệp vụ"]
    W --> A["ACK"]
~~~

Không có đoạn delay nào xuất hiện trong sơ đồ trên. Các điều kiện như prefetch, thứ tự queue và số consumer khiến vị trí/giao lại message thay đổi; **requeue không bảo đảm phân phối công bằng hoặc lùi message xuống cuối queue**. Việc tăng số worker thường chỉ làm vòng lặp lỗi nhanh hơn.

Cờ `redelivered` trong delivery metadata cho biết broker đã từng cố giao message trước đó, **không phải số lần thử đáng tin cậy**. Nó không phản ánh số lần Spring Retry chạy lại handler *bên trong cùng delivery* và không thay cho bộ đếm retry có giới hạn.

Một lựa chọn thường an toàn hơn là: thử lại tạm thời với ngân sách hữu hạn, sau đó **reject không requeue** để message tới DLQ, đồng thời có quy trình khắc phục và phát lại có kiểm soát.

## 3. Phân loại lỗi trước khi chọn chính sách

Cùng là exception Java nhưng ý nghĩa nghiệp vụ rất khác nhau:

| Nhóm lỗi | Ví dụ | Chính sách gợi ý |
| --- | --- | --- |
| **Tạm thời, có thể phục hồi** | HTTP 503, timeout mạng, DB lock/deadlock, rate limit | Retry hữu hạn + backoff; có thể chuyển sang retry queue chậm |
| **Dữ liệu không hợp lệ** | JSON hỏng, thiếu field bắt buộc, enum/schema không hỗ trợ | Reject không requeue; DLQ để sửa producer/hợp đồng |
| **Vi phạm nghiệp vụ lâu dài** | Đơn hàng đã bị hủy, đối tượng không tồn tại vĩnh viễn | Không retry mù; có thể gửi tới queue điều tra hoặc ghi kết quả từ chối |
| **Phụ thuộc chưa sẵn sàng nhưng có thể sẵn sàng sau lâu** | Partner outage 30 phút, maintenance, quota có lịch reset | Trì hoãn qua broker, circuit breaker và cảnh báo |
| **Trạng thái kết quả không rõ** | DB đã commit rồi mất connection trước ack, timeout sau khi side effect hoàn tất | Redelivery có thể xảy ra; bắt buộc idempotency và tra cứu kết quả |
| **Bug ứng dụng** | NullPointerException từ code, memory leak, mapping sai | Cô lập, cảnh báo, sửa và replay; retry nhanh không giúp |

Không phân loại chỉ theo HTTP status. Ví dụ HTTP 409 có thể là duplicate hợp lệ hoặc lỗi nghiệp vụ; HTTP 404 có thể tạm thời trong hệ thống eventually consistent hoặc vĩnh viễn. Tầng domain phải định nghĩa rõ retryability, trạng thái cuối và khả năng bồi hoàn.

Một quy tắc thực dụng: chỉ retry khi **có lý do lỗi có thể biến mất**, thao tác **an toàn khi phát lại**, và **tổng thời gian/số lần thử nằm trong giới hạn**. Nếu không đáp ứng, đẩy message vào luồng kiểm soát khác.

## 4. Retry có ba vị trí và ba ngữ nghĩa khác nhau

| Cơ chế | Ở đâu? | Ưu điểm | Giới hạn |
| --- | --- | --- | --- |
| **Local/in-process retry** | Trong listener container bằng Spring Retry | Dễ cấu hình, phù hợp lỗi chớp nhoáng | Giữ consumer/thread; backoff dài làm giảm thông lượng, không bền qua restart |
| **Broker requeue** | BasicReject/Nack với `requeue=true` hoặc connection mất khi chưa ack | Đơn giản, broker giao lại | Thường không delay, không tự giới hạn số attempt; dễ lặp vô hạn |
| **Delayed redelivery** | TTL/DLX retry queue, delayed exchange plugin hoặc scheduler | Cho phép backoff dài, giảm tải downstream | Cần quản lý topology, attempt count, routing, publisher confirm và idempotency |

**Local retry** có thể chạy handler ba lần nhưng RabbitMQ vẫn thấy **một delivery đang unacked**; broker-level redelivery thường chỉ xảy ra sau nack/requeue hoặc mất channel. Vì vậy không thể chỉ dựa vào header RabbitMQ để đo đầy đủ tất cả attempt trong ứng dụng.

**Broker requeue** không đồng nghĩa với **retry có trì hoãn**. Việc đặt `Thread.sleep(5_000)` trong listener trước khi requeue có thể giữ thread/consumer và throughput, không phải chiến lược tốt khi số lỗi tăng.

**Delayed redelivery** thường định tuyến message sang queue giữ chờ, sau đó quay về queue nghiệp vụ. Chỉ nên quay lại khi còn attempt budget, còn lại đưa vào DLQ. Nếu tạo vòng queue TTL → DLX → queue chính không có bộ đếm/điểm dừng, kiến trúc vẫn có thể lặp vô hạn hoặc gặp cơ chế phát hiện dead-letter cycle của broker. Không lấy cơ chế phát hiện cycle làm chính sách retry nghiệp vụ.

## 5. Cấu hình Spring Boot: retry hữu hạn, sau đó chuyển DLQ

Ví dụ nền dùng `spring-boot-starter-amqp` với Spring Boot 3.x:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-amqp</artifactId>
</dependency>
~~~

Một cấu hình `application.yml` cho **SimpleRabbitListenerContainerFactory** mặc định của Boot:

~~~yaml
spring:
  rabbitmq:
    host: localhost
    port: 5672
    username: ${RABBITMQ_USER}
    password: ${RABBITMQ_PASSWORD}
    listener:
      simple:
        acknowledge-mode: auto
        default-requeue-rejected: false
        prefetch: 20
        retry:
          enabled: true
          max-attempts: 3
          initial-interval: 300ms
          multiplier: 2.0
          max-interval: 2s
~~~

Ý nghĩa:

- `acknowledge-mode: auto`: Spring ack sau khi listener xử lý xong; exception đi qua xử lý lỗi của container.
- `retry.enabled: true`: bật retry advice trên listener container do auto-configuration tạo.
- `max-attempts: 3`: gồm **lần gọi ban đầu** và tối đa hai lần retry trong cùng delivery. Không có nghĩa broker tự giao lại ba lần.
- `initial-interval`, `multiplier`, `max-interval`: giới hạn backoff của các lần retry local. Nếu listener bị block giữa các lần retry, throughput có thể giảm.
- `default-requeue-rejected: false`: nếu xử lý cuối cùng không thành công, mặc định reject/nack **không requeue**; với DLX phù hợp, message đi vào dead-letter flow.
- `prefetch: 20`: một consumer có thể nhận trước nhiều message chưa ack; khi downstream chậm/retry, prefetch lớn có thể giữ message quá lâu. Cần đo thực tế trước khi chỉnh concurrency/prefetch.

**Bẫy cấu hình:** Các property `spring.rabbitmq.listener.simple.*` chỉ tác động tới Simple container của Boot. Nếu project dùng `listener.direct.*` hoặc tự tạo `SimpleRabbitListenerContainerFactory` rồi không áp dụng Boot configurer, kết quả có thể không giống ví dụ.

Một cách tùy biến factory, trong trường hợp muốn quản lý retry rõ ràng bằng Java:

~~~java
import org.springframework.amqp.rabbit.config.RetryInterceptorBuilder;
import org.springframework.amqp.rabbit.config.SimpleRabbitListenerContainerFactory;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.amqp.rabbit.retry.RejectAndDontRequeueRecoverer;
import org.springframework.boot.autoconfigure.amqp.SimpleRabbitListenerContainerFactoryConfigurer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class ShippingListenerConfig {

    @Bean
    SimpleRabbitListenerContainerFactory boundedRetryFactory(
            ConnectionFactory connectionFactory,
            SimpleRabbitListenerContainerFactoryConfigurer configurer) {

        var factory = new SimpleRabbitListenerContainerFactory();
        configurer.configure(factory, connectionFactory);

        factory.setDefaultRequeueRejected(false);
        factory.setAdviceChain(
            RetryInterceptorBuilder.stateless()
                .maxAttempts(3)
                .backOffOptions(300L, 2.0, 2_000L)
                .recoverer(new RejectAndDontRequeueRecoverer())
                .build()
        );
        return factory;
    }
}
~~~

Sau đó chỉ định tại listener: `@RabbitListener(queues = "shipping.jobs", containerFactory = "boundedRetryFactory")`. Đây là **phương án thay thế** cấu hình retry tự động: nếu Boot configurer đã gắn một retry advice theo properties, hãy tránh bật thêm một retry advice thứ hai rồi vô tình nhân số lần gọi. Có thể tắt `spring.rabbitmq.listener.simple.retry.enabled` khi chủ động cung cấp advice tùy chỉnh.

`RejectAndDontRequeueRecoverer` kết thúc chuỗi retry bằng `AmqpRejectAndDontRequeueException`, khiến container reject delivery thay vì requeue. Nó **không tự tạo DLQ**; cần khai báo DLX/queue/binding phía RabbitMQ hoặc message sẽ không đi đến nơi bạn mong muốn.

### Khi nào dùng stateless và stateful retry?

- **Stateless retry**: các lần thử lại chạy trong cùng một lần listener invocation/delivery theo interceptor. Đơn giản cho các lỗi ngắn như timeout HTTP vài trăm mili giây.
- **Stateful retry**: giữ retry context theo message identity qua nhiều lần delivery/invocation, có những tác động riêng đến transaction và requeue. Cần message ID/khóa ổn định, chính sách recoverer rõ ràng và kiểm thử số lần delivery thực tế.

Đừng bật `stateful` chỉ vì muốn “message sống qua restart”. Retry context trong memory của consumer không tự trở thành hệ thống lưu trữ bền vững qua process restart. Khi yêu cầu retry lâu và không mất lịch sử, broker queues/headers hoặc kho trạng thái nghiệp vụ mới là nền tảng phù hợp.

## 6. Khai báo topology chính và Dead Letter Queue

Một DLQ hữu dụng phải có **đường route thật**, không phải chỉ có queue tên `*.dead`. Ví dụ tạo exchange/queue/binding bằng Spring AMQP:

~~~java
import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class ShippingRabbitTopology {
    public static final String MAIN_EXCHANGE = "orders.events";
    public static final String MAIN_ROUTING_KEY = "order.paid";
    public static final String MAIN_QUEUE = "shipping.jobs";
    public static final String DEAD_EXCHANGE = "orders.dlx";
    public static final String DEAD_ROUTING_KEY = "shipping.dead";
    public static final String DEAD_QUEUE = "shipping.dead";

    @Bean
    DirectExchange ordersExchange() {
        return new DirectExchange(MAIN_EXCHANGE, true, false);
    }

    @Bean
    Queue shippingQueue() {
        return QueueBuilder.durable(MAIN_QUEUE)
                .deadLetterExchange(DEAD_EXCHANGE)
                .deadLetterRoutingKey(DEAD_ROUTING_KEY)
                .build();
    }

    @Bean
    Binding shippingBinding(@Qualifier("shippingQueue") Queue shippingQueue,
                            @Qualifier("ordersExchange") DirectExchange ordersExchange) {
        return BindingBuilder.bind(shippingQueue)
                .to(ordersExchange)
                .with(MAIN_ROUTING_KEY);
    }

    @Bean
    DirectExchange ordersDeadExchange() {
        return new DirectExchange(DEAD_EXCHANGE, true, false);
    }

    @Bean
    Queue shippingDeadQueue() {
        return QueueBuilder.durable(DEAD_QUEUE).build();
    }

    @Bean
    Binding deadBinding(@Qualifier("shippingDeadQueue") Queue shippingDeadQueue,
                        @Qualifier("ordersDeadExchange") DirectExchange ordersDeadExchange) {
        return BindingBuilder.bind(shippingDeadQueue)
                .to(ordersDeadExchange)
                .with(DEAD_ROUTING_KEY);
    }
}
~~~

Khi consumer reject `shipping.jobs` với `requeue=false`, broker dead-letter thông điệp vào `orders.dlx` với routing key `shipping.dead` rồi binding đưa nó tới `shipping.dead`.

Các chi tiết vận hành:

1. **DLX phải tồn tại** và có binding phù hợp. Dead-letter routing sai, exchange bị xóa, policy bị thay đổi, queue đích quá tải hoặc không sẵn sàng đều có thể làm đường xử lý thất bại.
2. `durable queue` không tự biến mọi publish thành bền vững; producer cần persistent delivery phù hợp và broker phải có cơ chế lưu trữ được vận hành đúng. DLX cũng có điều kiện độ bền và tính an toàn riêng.
3. Đối với quorum queue, RabbitMQ có các tính năng và chính sách dead-lettering/delivery limit phụ thuộc version; kiểm thử chế độ dead-lettering được chọn nếu SLA yêu cầu không mất message trong chuyển tiếp.
4. Thay đổi `x-dead-letter-exchange`, `x-dead-letter-routing-key` bằng cách khai báo lại một queue đang tồn tại với argument khác có thể gây `PRECONDITION_FAILED`. Trên production, cân nhắc dùng RabbitMQ policy và kế hoạch migrate topology theo khả năng broker.
5. DLQ cũng cần giới hạn dung lượng/retention, quyền truy cập, cảnh báo và quy trình replay. Một DLQ không được theo dõi chỉ là nơi lỗi bị cất giấu.

### Vì sao error handler của Spring cũng quan trọng?

Không phải message hỏng nào cũng tới được method `@RabbitListener`. Ví dụ sai content type, lỗi conversion, không tìm được method handler hoặc payload không tương thích có thể xảy ra **trước khi listener chạy**. Spring AMQP có cơ chế phân loại lỗi fatal trong container/error handler (chẳng hạn `ConditionalRejectingErrorHandler`) để tránh một số trường hợp conversion lỗi bị requeue mãi.

Khi tùy biến error handler hoặc listener container, kiểm tra chính sách của các lỗi trước listener, cách exception được wrap và hành vi với message đã từng dead-letter. Không mặc định một `catch` trong method listener sẽ xử lý được tất cả lỗi serialization.

## 7. Viết listener: lỗi vĩnh viễn đi DLQ, lỗi tạm thời được retry

Tình huống xử lý `OrderPaid` trong shipping-service. Ta đọc trực tiếp body JSON của Spring AMQP `Message` và chuyển sang DTO, tránh phụ thuộc vào automatic conversion khi đang minh họa chính sách lỗi.

~~~java
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.amqp.AmqpRejectAndDontRequeueException;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class ShippingConsumer {

    private final ObjectMapper objectMapper;
    private final ShipmentService shipmentService;

    public ShippingConsumer(ObjectMapper objectMapper,
                            ShipmentService shipmentService) {
        this.objectMapper = objectMapper;
        this.shipmentService = shipmentService;
    }

    @RabbitListener(
        queues = ShippingRabbitTopology.MAIN_QUEUE,
        containerFactory = "boundedRetryFactory"
    )
    public void onOrderPaid(Message message) {
        OrderPaid event;

        try {
            event = objectMapper.readValue(
                    message.getBody(), OrderPaid.class);
        } catch (JsonProcessingException ex) {
            throw new AmqpRejectAndDontRequeueException(
                    "Không đọc được OrderPaid JSON", ex);
        }

        if (event.eventId() == null
                || event.eventId().isBlank()
                || event.orderId() == null
                || event.orderId().isBlank()) {
            throw new AmqpRejectAndDontRequeueException(
                    "Thiếu eventId hoặc orderId");
        }

        // Nên dùng @Transactional tại ShipmentService cùng inbox idempotency.
        // Nếu lỗi tạm thời, ném exception để retry interceptor xử lý.
        shipmentService.createShipmentOnce(event);
    }
}

record OrderPaid(String eventId, String orderId) {}
~~~

`ShipmentService` là thành phần nghiệp vụ do dự án tự định nghĩa. Trong triển khai thực, `createShipmentOnce` cần kiểm soát transaction SQL, unique key và side effect ngoài cơ sở dữ liệu.

**Chú ý về thứ tự interceptor:** `AmqpRejectAndDontRequeueException` báo cho container rằng message không nên requeue khi exception cuối cùng được xử lý. Nó không có nghĩa **mọi cấu hình retry advice đều bỏ qua các lần retry local** đối với exception này. Với `RetryInterceptorBuilder.stateless()` cơ bản ở mục 5, nếu muốn lỗi payload sai **được kết thúc ngay** mà không lặp local ba lần, cần cấu hình retry classifier/phân nhóm exception tương ứng hoặc tách luồng kiểm tra/consumer sao cho lỗi vĩnh viễn không đi qua advice retry chung.

### Nên xử lý retryable exception ra sao?

Tầng service có thể ném `TransientPartnerException` khi API vận chuyển trả 503/timeout. Listener để exception đi lên, Spring Retry xử lý theo ngân sách. Sau khi tất cả attempts thất bại, recoverer reject không requeue và broker dead-letter.

Ngược lại, nếu code:

~~~java
try {
    shipmentService.createShipmentOnce(event);
} catch (Exception ex) {
    log.error("Lỗi tạo vận đơn", ex);
    // Trả về bình thường.
}
~~~

thì Spring AUTO ack có thể coi delivery đã được xử lý thành công. Message có thể biến mất khỏi queue dù nghiệp vụ thất bại. Cần **ném lỗi, ghi trạng thái lỗi bền vững có chủ đích hoặc chuyển sang luồng khác an toàn**; không chỉ log và bỏ qua.

### `ImmediateRequeueAmqpException` sử dụng rất hạn chế

Spring AMQP có `ImmediateRequeueAmqpException` để yêu cầu requeue ngay dù default reject policy đang là false. Đây là công cụ kiểm soát cho tình huống rất cụ thể, không nên dùng như một giải pháp “retry lúc nào cũng được”: nó có thể đưa bạn quay lại vòng lặp vô hạn. Mỗi đường requeue chủ động phải có cơ chế giới hạn/throttle hoặc điều kiện khiến message chắc chắn không quay lại cùng trạng thái lỗi mãi.

## 8. Manual ack: chính xác ai chịu trách nhiệm xử lý delivery?

Một số hệ thống cần tự xác nhận để phối hợp chặt với kết quả ghi database hoặc một quy trình chuyển tiếp. Khi đó có thể cấu hình `ackMode = MANUAL` trên listener:

~~~java
import com.rabbitmq.client.Channel;
import java.io.IOException;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class ManualShippingConsumer {

    private final ShipmentService shipmentService;

    public ManualShippingConsumer(ShipmentService shipmentService) {
        this.shipmentService = shipmentService;
    }

    @RabbitListener(
        queues = "shipping.manual.jobs",
        ackMode = "MANUAL"
    )
    public void handle(Message message, Channel channel) throws IOException {
        long tag = message.getMessageProperties().getDeliveryTag();

        try {
            shipmentService.processRawOnce(message.getBody());
            channel.basicAck(tag, false);
        } catch (PermanentMessageException ex) {
            channel.basicReject(tag, false);  // DLX nếu đã khai báo.
        } catch (TransientProcessingException ex) {
            channel.basicNack(tag, false, false); // Đưa DLQ, chờ xử lý sau.
        }
    }
}
~~~

Ví dụ cố ý dùng queue khác `shipping.manual.jobs` để không đồng thời chạy hai listener trên cùng main queue. `PermanentMessageException`, `TransientProcessingException` và phương thức `ShipmentService.processRawOnce` là thành phần do ứng dụng định nghĩa. Queue manual cũng cần có topology DLX riêng để `requeue=false` không làm mất message.

Điểm cần hiểu:

- Ack sau khi transaction nghiệp vụ đã commit. Nếu ack trước rồi DB commit lỗi, message sẽ không được broker giao lại.
- Nếu DB đã commit nhưng connection chết trước ack, message có thể được giao lại; inbox idempotency là bắt buộc.
- `basicReject` và `basicNack` dùng delivery tag của **chính channel** đang xử lý message. Không tái sử dụng tag từ channel khác và không ack hai lần.
- Nếu catch chỉ các exception cụ thể, các lỗi bất ngờ khác phải có chính sách rõ ràng (ví dụ container đóng channel và message unacked được redeliver), tránh che giấu lỗi.
- Manual ack có thể hữu ích cho publish chuyển tiếp, nhưng **ack nguồn + publish đích không tạo thành một transaction nguyên tử** chỉ bằng việc đặt trong một phương thức Java.

Với các bài toán thông thường, AUTO ack kết hợp retry bounded và DLQ dễ vận hành hơn; manual ack chỉ nên chọn khi biết chính xác yêu cầu xác nhận.

## 9. Delayed retry qua broker: tránh giữ consumer trong backoff dài

Nếu partner có thể offline 15 phút, local retry 3 lần cách nhau 300 ms chưa đủ. Giữ listener ngủ 15 phút làm chiếm consumer/prefetch và khó scale. Có thể thiết kế queue chờ có TTL rồi dead-letter ngược về main exchange.

Một topology khả thi theo ý tưởng:

~~~mermaid
flowchart LR
    EX["orders.events<br/>routing: order.paid"] --> MAIN[("shipping.jobs")]
    MAIN --> WORKER["shipping-service"]
    WORKER -->|Lỗi tạm thời, còn budget| RETRYEX["orders.retry"]
    RETRYEX --> R5[("shipping.retry.5s<br/>TTL 5s")]
    RETRYEX --> R30[("shipping.retry.30s<br/>TTL 30s")]
    R5 -->|Hết TTL, DLX| EX
    R30 -->|Hết TTL, DLX| EX
    WORKER -->|Lỗi vĩnh viễn / hết budget| DLX["orders.dlx"]
    DLX --> DLQ[("shipping.dead")]
~~~

**Khác với auto-requeue:** listener phải kiểm tra **attempt budget** và định tuyến lỗi tạm thời sang retry queue phù hợp; khi hết lần cho phép, reject/nack không requeue để vào DLQ. Nếu chỉ cấu hình main queue dead-letter sang retry rồi retry queue dead-letter quay lại main **mà không có điều kiện dừng**, bạn vẫn tạo vòng lặp.

### Khai báo hai queue giữ chờ bằng TTL

Đây là phần bổ sung topology theo kiểu queue-level TTL:

~~~java
import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class ShippingRetryTopology {

    @Bean
    DirectExchange retryExchange() {
        return new DirectExchange("orders.retry", true, false);
    }

    @Bean
    Queue retryFiveSecondsQueue() {
        return QueueBuilder.durable("shipping.retry.5s")
                .ttl(5_000)
                .deadLetterExchange("orders.events")
                .deadLetterRoutingKey("order.paid")
                .build();
    }

    @Bean
    Queue retryThirtySecondsQueue() {
        return QueueBuilder.durable("shipping.retry.30s")
                .ttl(30_000)
                .deadLetterExchange("orders.events")
                .deadLetterRoutingKey("order.paid")
                .build();
    }

    @Bean
    Binding bindRetryFiveSeconds(
            @Qualifier("retryFiveSecondsQueue") Queue retryFiveSecondsQueue,
            @Qualifier("retryExchange") DirectExchange retryExchange) {
        return BindingBuilder.bind(retryFiveSecondsQueue)
                .to(retryExchange)
                .with("delay.5s");
    }

    @Bean
    Binding bindRetryThirtySeconds(
            @Qualifier("retryThirtySecondsQueue") Queue retryThirtySecondsQueue,
            @Qualifier("retryExchange") DirectExchange retryExchange) {
        return BindingBuilder.bind(retryThirtySecondsQueue)
                .to(retryExchange)
                .with("delay.30s");
    }
}
~~~

Các queue retry không được có consumer trực tiếp trong mô hình này: chúng giữ message chờ TTL rồi dead-letter về `orders.events`. Main queue và DLQ đã được khai báo ở mục 6. Khi retry queue hết TTL, broker tạo một lần delivery mới về main; producer mới không cần gửi lại tại thời điểm đó.

Để kích hoạt, ứng dụng phải **republish** message sang exchange `orders.retry` với routing key `delay.5s` hoặc `delay.30s` khi biết lỗi còn retry được. Một hướng thiết kế là:

~~~text
on transient error:
    nextAttempt = readValidatedAttempt(message) + 1

    if nextAttempt <= MAX_RETRIES:
        publish original business event with nextAttempt to retry.exchange
        wait for broker publish confirm and handle unroutable return
        acknowledge original delivery
    else:
        reject original delivery with requeue=false   # final DLQ

on permanent error:
    reject original delivery with requeue=false       # final DLQ
~~~

Đây là **pseudo-code mô tả luồng**, không phải một atomic transaction. Việc publish retry rồi ack message gốc có cửa sổ lỗi: publish thành công nhưng ack chưa xong có thể tạo **hai bản sao**; ack gốc trước khi publish được broker chấp nhận có thể **mất việc**. Dùng publisher confirms, mandatory returns/routing checks và một cơ chế lưu trạng thái/outbox hoặc idempotency khi cần guarantee mạnh. Publisher confirm chỉ xác nhận broker nhận publish theo cơ chế đang dùng, không tự chứng minh message đã tới queue đích và được consumer xử lý.

Một chiến lược đơn giản là **local retry ngắn + final DLQ**, dùng vận hành/worker riêng để phân loại DLQ và lên lịch replay có kiểm soát. Chỉ xây delayed retry topology khi có SLA thật sự yêu cầu tự động thử lại theo phút/giờ.

### Vì sao chọn nhiều queue TTL cố định?

Queue-level TTL (ví dụ mọi message trong `shipping.retry.5s` đều 5 giây) dễ dự báo hơn việc gom các message có TTL khác nhau vào cùng queue, vì expiration/dead-letter có thể bị ảnh hưởng bởi vị trí message trong queue. Nếu cần delay động, xem xét plugin delayed-message exchange, scheduler hoặc nền tảng broker hỗ trợ scheduling phù hợp; việc dùng plugin phụ thuộc phiên bản và chính sách triển khai RabbitMQ.

**Quan trọng:** queue TTL cũng có chi phí bộ nhớ/disk. Khi đối tác offline, backlog retry có thể tăng hàng triệu message; cần quota, retention, disk alarms và chiến lược stop-the-world/circuit breaker.

## 10. Đếm số lần thử mà không tạo vòng lặp

Một hệ thống retry phải lưu được hai con số khác nhau:

- **Local attempts**: số lần interceptor gọi handler trong một delivery. `max-attempts=3` là ví dụ.
- **Broker redeliveries/round trips**: số lần message được giao lại do nack/requeue/TTL DLX hoặc được ứng dụng republish thành message mới.

Đừng gom hai con số thành một chỉ bằng `redelivered=true`. RabbitMQ có thể gắn các header death/trace cho message dead-lettered, nhưng chúng không phải bộ đếm tổng số lần handler chạy.

### Header `x-death` của RabbitMQ

Khi broker thực hiện dead-lettering, RabbitMQ thường ghi thông tin như queue đã chết, lý do và số lần dead-letter trong `x-death` (được tổng hợp theo các thuộc tính của chu kỳ chết). Có thể phân biệt lý do như `rejected` và `expired`.

Tuy nhiên:

- `x-death` phản ánh **lần dead-letter tại broker**, không ghi từng lần retry local của Spring.
- Một message được republish thành **message mới** có thể không mang lịch sử `x-death` trước đó nếu ứng dụng không chủ đích giữ/ánh xạ metadata.
- RabbitMQ quản lý `x-death` theo chính sách nội bộ; không nên để client tùy ý quyết định ngân sách retry chỉ bằng việc tự gửi một header tên giống broker.
- Với một pipeline có nhiều queue và reason, cách cộng tất cả `count` không nhất thiết trùng “số lần chạy nghiệp vụ”.

Nếu cần retry budget ổn định xuyên nhiều vòng delay, ứng dụng có thể tự định nghĩa `retryAttempt` trong envelope hoặc header do nội bộ kiểm soát, và tăng **mỗi lần quyết định schedule lại**. Phải có MAX_RETRIES hữu hạn, kiểm tra giá trị khi nhận, giữ nguyên `eventId` và quản lý quyền publish. Có thể lưu retry state trong database để tránh việc copy/forge header hoặc mất state khi republish.

Quorum queue còn có cơ chế delivery count/limit dành cho poison message (tính năng, default và semantics phụ thuộc phiên bản RabbitMQ). Khi sử dụng, xác minh tính chất này với `nack`, `reject`, DLX, quorum queue policy và consumer behavior thực tế; nó **không thay thế** chiến lược retry theo lỗi nghiệp vụ và không đo số lần Spring Retry chạy trong cùng delivery.

### Bảng ngân sách minh họa

| Lần gọi nghiệp vụ | Chỗ thực hiện | Retry counter dự kiến | Hành động nếu tiếp tục lỗi |
| --- | --- | --- | --- |
| Delivery đầu tiên, local call #1 | Main listener | attempt=0 (broker cycle) | Local retry #2 |
| Local call #2 | Cùng delivery | attempt=0 | Local retry #3 |
| Local call #3 | Cùng delivery | attempt=0 | Republish tới delay 5s nếu lỗi tạm thời |
| Nhận lại sau delay 5s | Main listener | attempt=1 | Retry local tối đa 3 lần |
| Nhận lại sau delay 30s | Main listener | attempt=2 | Nếu vẫn lỗi, final DLQ |

Bảng mô tả **một chính sách giả định do ứng dụng tự xây**. Nếu sử dụng recoverer mặc định `RejectAndDontRequeueRecoverer` ở mục 5, message đi DLQ sau khi local retry hết; để schedule delayed retry, recoverer/handler phải được **thay thế bằng chiến lược publish + confirm + ack** riêng. Không bật cả hai rồi kỳ vọng chúng tự phối hợp theo bảng.

## 11. Idempotency: xử lý trùng lặp sau retry, requeue hoặc mất kết nối

Ngay cả khi chỉ xử lý message một lần trong trạng thái bình thường, AMQP consumer theo cách triển khai phổ biến nên được thiết kế theo **at-least-once delivery**: cùng event có thể được nhận lại.

Tình huống:

1. Consumer nhận event `eventId=EVT-1042`.
2. `shipmentService` ghi vận đơn vào SQL và commit.
3. Trước khi Spring container gửi ACK, channel bị ngắt.
4. Broker giao lại event khi kết nối/consumer phục hồi.
5. Nếu service tạo vận đơn mới mà không kiểm tra event ID, một đơn hàng có hai vận đơn.

Sử dụng **inbox/idempotency table** với khóa duy nhất:

~~~sql
CREATE TABLE processed_shipping_events (
    subscriber_id VARCHAR(100) NOT NULL,
    event_id      VARCHAR(120) NOT NULL,
    processed_at  TIMESTAMP NOT NULL,
    PRIMARY KEY (subscriber_id, event_id)
);
~~~

Trong **cùng transaction SQL**, consumer:

1. Xác nhận schema, signature/nguồn tin cậy nếu cần và event ID.
2. Thử ghi `(shipping-service, eventId)` vào inbox (có unique constraint).
3. Nếu khóa đã tồn tại, trả về thành công an toàn, không thực hiện side effect lần nữa.
4. Nếu là lần đầu, tạo/cập nhật vận đơn cùng transaction; commit.
5. Để listener kết thúc bình thường cho Spring ACK.

Nếu commit SQL thành công mà ACK lỗi, lần redelivery sẽ rơi vào nhánh inbox đã tồn tại. Cần xử lý đồng thời nhiều consumer đọc cùng `eventId` bằng unique constraint thật, không chỉ thao tác “kiểm tra trước khi ghi” không có ràng buộc DB.

### Side effect bên ngoài SQL

Nếu nghiệp vụ gọi HTTP API vận chuyển để tạo vận đơn, chỉ có inbox SQL **chưa chắc** bảo vệ việc gọi hai lần trong mọi tình huống, ví dụ HTTP thành công rồi consumer chết trước SQL commit. Hãy gửi **idempotency key** mà đối tác hỗ trợ (chẳng hạn `orderId` hoặc event-derived key), ghi trạng thái giao dịch và có cơ chế kiểm tra lại kết quả/đối soát trước khi retry. Với việc commit SQL rồi phát thêm event, cân nhắc **transactional outbox** để tránh khoảng hở giữa database và RabbitMQ.

**Rabbit transaction, publisher confirm, consumer ack và database transaction là các phạm vi khác nhau.** Không suy ra exactly-once business effect chỉ từ cờ `deliveryMode=PERSISTENT` hoặc `acknowledge-mode=auto`.

## 12. Dead-letter đúng lúc và quy trình vận hành DLQ

Một DLQ hữu ích cần thông tin để hỗ trợ điều tra và replay:

| Thuộc tính cần lưu/quan sát | Mục đích |
| --- | --- |
| `eventId`, `orderId`, `schemaVersion`, event type | Nhận diện và loại trùng; tìm nguồn dữ liệu |
| Timestamp gốc, thời điểm reject, khoảng tuổi message | Xác định độ trễ, ảnh hưởng SLA |
| Original exchange/routing key/queue | Đưa về đúng đường sau khi sửa lỗi |
| `x-death` reason, queue, count | Phân biệt reject, TTL và các lần dead-letter |
| Tên exception, error classification (đã làm sạch) | Phân loại lỗi dữ liệu, bug, downstream |
| Service version, trace/correlation ID | Ghép log/trace và xác định bản triển khai |
| Retry budget và retry history do ứng dụng quản lý | Quyết định còn được phép replay hay không |

**Broker không tự đính kèm toàn bộ stacktrace Java của consumer vào DLQ.** Muốn có thông tin lỗi trong message, cần lựa chọn message recoverer/republisher hoặc hệ thống log/error store riêng; không cố nhét dữ liệu nhạy cảm vào header không được kiểm soát. Một số `RepublishMessageRecoverer` của Spring AMQP có thể thêm thông tin exception khi republish, nhưng phải thiết kế kích thước header, bảo mật, exchange/routing riêng, publisher confirms và hạn chế dữ liệu nội bộ.

Quy trình replay an toàn:

1. Đánh giá nguyên nhân: payload lỗi, bug đã được sửa, dependency outage hay thay đổi schema.
2. Xác định số lượng ảnh hưởng, event IDs, dữ liệu nhạy cảm và khả năng thao tác lặp.
3. Chọn từng message hoặc một batch có giới hạn, giữ nguyên ID nghiệp vụ, có log audit và người chịu trách nhiệm.
4. Kiểm tra broker exchange/routing key, trạng thái DB và idempotency trước khi republish.
5. Điều tiết tốc độ replay, dùng batch nhỏ trước; theo dõi tác động lên partner/DB.
6. Chỉ ack/delete message khỏi DLQ sau khi chiến lược chuyển tiếp đủ tin cậy; không xóa hàng loạt để “làm sạch dashboard”.

Không cấu hình DLQ tự động trả lại main queue vô thời hạn nếu chưa có giới hạn và cách lưu kết quả cuối. Sau khi sửa bug, replay từ DLQ thường phải kiểm soát cả schema version và thứ tự phụ thuộc giữa các sự kiện.

## 13. Các chỉ số và cảnh báo để phát hiện retry storm

Một hệ thống RabbitMQ có thể đang “còn kết nối, còn consumer” nhưng thực tế không tạo tiến bộ nghiệp vụ vì message bị requeue liên tục.

| Chỉ số | Cách đọc |
| --- | --- |
| `messages_ready` tại main queue | Số message chờ chưa giao |
| `messages_unacknowledged` | Số delivery đã giao nhưng chưa ack; cao kéo dài có thể do xử lý chậm, prefetch hoặc local retry |
| Publish/deliver/ack/requeue/redelivery rates | Redelivery cao mà ACK/throughput thấp gợi ý vòng lặp lỗi |
| DLQ depth, ingress rate, age of oldest | Lỗi có tích tụ và vi phạm SLA hay không |
| Retry queue ready/oldest age | Retry có bị dồn do partner outage hay TTL/routing hỏng |
| Consumer count, connection/channel errors | Thiếu consumer hay churn kết nối |
| Local retry attempts theo exception/route | Lỗi transient thật hay payload/bug bị retry sai |
| Idempotency duplicate hits | Cho biết redelivery/republish có tạo bản sao nghiệp vụ |
| Publisher confirm failure, returns | Phát hiện publish retry/replay không tới broker hoặc không route được |
| RabbitMQ memory/disk alarms, queue policy violations | Backlog có vượt capacity, ảnh hưởng toàn broker |

Nếu một message fail và requeue quá nhanh, điều chỉnh concurrency chỉ là biện pháp giảm triệu chứng. Cần xem loại lỗi, thiết kế điểm dừng retry và đường DLQ. Nếu DLQ tăng, phải xác định lỗi producer schema hay consumer version; **xóa DLQ không phải là sửa hệ thống**.

### Hệ quả của concurrency và prefetch

- Nhiều consumer có thể nhận lại message lỗi ở các consumer khác nhau; log từ một pod riêng lẻ có thể không cho thấy vòng lặp.
- Prefetch lớn khiến nhiều message đang unacked ở consumer chậm, ảnh hưởng độ công bằng và thời gian phục hồi khi một node chết.
- Local retry dài giữ thread xử lý, có thể làm toàn bộ consumer mất throughput.
- Retry đồng loạt khi downstream hồi phục có thể gây tải dồn (*thundering herd*). Dùng jitter/backoff, quota và circuit breaker khi phù hợp.

## 14. Ma trận kiểm thử tích hợp nên có

Các bài test quan trọng cần broker thật hoặc RabbitMQ chạy trong môi trường integration test. Mock listener không kiểm tra được semantics ACK/NACK/DLX hoặc header RabbitMQ.

| Ca kiểm thử | Cách thực hiện | Điều phải quan sát |
| --- | --- | --- |
| Message hợp lệ | Publish event với `eventId` mới | Service xử lý một lần, queue empty/ack tăng |
| HTTP 503 hai lần rồi thành công | Stub partner thất bại 2 lần, thành công lần 3 | Listener chạy tối đa 3 lần local, ACK; không vào DLQ |
| HTTP 503 mãi mãi | Stub luôn lỗi; local retry hữu hạn | Final reject không requeue, DLQ nhận đúng message |
| JSON không parse được | Publish payload sai schema | Không xoay vòng main queue; có nơi điều tra lỗi |
| Không có DLX/binding hợp lệ | Cố tình cấu hình sai trong môi trường test | Nhìn thấy thông điệp không đi DLQ và sửa topology |
| Requeue=true liên tục | Dùng consumer test dễ kiểm soát | Xác nhận có redelivery nhanh, sau đó tắt/reconfigure ngay |
| DB commit rồi mất ACK | Giả lập channel chết trước ack | Redelivery được idempotency chặn, không tạo thêm vận đơn |
| Partner downtime 15 phút | Điều hướng sang delay queues (nếu triển khai) | Consumer chính không bị block, retry đúng lịch và budget |
| Delay queue hết TTL | Publish tới `shipping.retry.5s` | Message quay lại main exchange/queue khi hết TTL |
| Vượt MAX_RETRIES | Publish event với retry state gần giới hạn | Kết thúc tại final DLQ, không quay lại main |
| Publisher confirm fail khi republish | Đứt connection đúng thời điểm | Không ack mất message gốc; duplicate được chặn |
| Quorum delivery limit (nếu dùng) | Nack/requeue đủ lần theo policy | Message bị xử lý theo delivery-limit/DLX đã cấu hình |
| Replay DLQ | Sửa nguyên nhân, republish cùng eventId | Không tạo side effect trùng, audit replay có đủ dữ liệu |

Với test publisher confirm/ack, có thể có failure window không thể tạo tất định bằng unit test; dùng fault injection, test ngắt kết nối và kiểm chứng idempotency là hướng đáng tin cậy hơn chỉ test happy path.

## 15. Những hiểu nhầm thường gặp

**“Ném exception từ `@RabbitListener` thì RabbitMQ tự retry sau 5 giây?”**

Không. Hành vi phụ thuộc cấu hình container, retry interceptor và policy của broker. `requeue=true` không kèm 5 giây delay; Spring Retry có backoff local nhưng giữ tài nguyên consumer trong thời gian đó.

**“`max-attempts: 3` nghĩa broker gửi lại message ba lần?”**

Không trong cấu hình Spring Retry stateless thông thường. Nó là tối đa ba lần interceptor gọi handler cho *một delivery*. Số broker redelivery khác với số local retry.

**“`default-requeue-rejected=false` làm mất message lỗi?”**

Nó chỉ chọn không requeue. Nếu đã cấu hình DLX/binding đúng, message có thể được dead-letter; nếu không, broker có thể loại bỏ message. Vì vậy đổi property phải đi kèm kiểm tra topology.

**“Bật DLX cho queue chính rồi nối một retry queue TTL về queue chính là đủ?”**

Chưa. Cần chặn vòng lặp bằng ngân sách retry và điểm kết thúc rõ ràng. Nếu mọi lỗi đều đi lại cùng một chu trình, message độc vẫn có thể quay mãi.

**“Một message có `redelivered=true` thì đã thử lại bao nhiêu lần?”**

Không xác định được từ boolean đó. Local retry, basicNack, dead-letter cycle và ứng dụng republish là những cơ chế khác nhau, cần đo/tổng hợp theo đúng cấp.

**“Thêm idempotency khiến ACK và SQL trở thành một transaction?”**

Không. Nó cho phép xử lý an toàn hơn khi message được giao lại sau khoảng hở DB commit–ACK. Nếu có side effect bên ngoài SQL hoặc publish event tiếp theo, vẫn cần thiết kế idempotency/outbox tương ứng.

**“DLQ chỉ cần dựng queue rồi để đó?”**

DLQ cần cảnh báo, retention, thông tin chẩn đoán và quy trình replay. Nếu không có giám sát, lỗi chỉ bị chuyển từ consumer sang backlog vô hình.

### Checklist triển khai

1. Phân loại lỗi transient/permanent/unknown outcome ở tầng nghiệp vụ.
2. Quy định retry budget hữu hạn, backoff và nơi kết thúc khi lỗi kéo dài.
3. Với Spring listener AUTO, hiểu rõ `default-requeue-rejected`, `retry.max-attempts` và sự khác biệt Simple/Direct container.
4. Đảm bảo main queue có DLX/route/DLQ đã kiểm thử; không để `requeue=true` thành mặc định cho poison message.
5. Nếu dùng delayed retry, thiết kế TTL queues, attempt counter và đường xử lý publish confirm–ack an toàn; chặn vòng main–retry vô hạn.
6. Dùng `eventId` bất biến, unique inbox và transaction nghiệp vụ để chống double side effect.
7. Quan sát ready/unacked/redelivery, số local retry, DLQ, tuổi message, publisher confirms và business duplicate.
8. Kiểm thử cả schema lỗi, downstream outage, broker reconnect, DB commit trước ACK và replay DLQ.
9. Đưa quy trình sửa/replay vào runbook, hạn chế quyền và loại dữ liệu nhạy cảm khỏi log/headers.

### Tài liệu đối chiếu phiên bản

- [RabbitMQ – Consumer Acknowledgements and Publisher Confirms](https://www.rabbitmq.com/docs/confirms): ngữ nghĩa `basicAck`, `basicReject`, `basicNack`, requeue và publisher confirm.
- [RabbitMQ – Dead Letter Exchanges](https://www.rabbitmq.com/docs/dlx): điều kiện dead-letter, routing, cấu hình và rủi ro khi dead-letter.
- [RabbitMQ – Time-To-Live and Expiration](https://www.rabbitmq.com/docs/ttl): message TTL và hành vi hết hạn.
- [Spring AMQP Reference – Exception Handling / Listener Retry](https://docs.spring.io/spring-amqp/reference/amqp/exception-handling.html): phân loại exception, reject và error handler.
- [Spring AMQP Reference – Resilience and Recovering from Errors](https://docs.spring.io/spring-amqp/reference/amqp/resilience-recovering-from-errors-and-broker-failures.html): cấu hình retry/recoverer và các điểm giới hạn.

**Ghi nhớ:** **retry** là quyết định thử thao tác lại, **requeue** chỉ là đưa delivery trở lại queue, còn **dead-letter** là cơ chế chuyển message ra khỏi luồng chính. Để RabbitMQ tích hợp Spring Boot đáng tin cậy, mọi retry phải có giới hạn và backoff phù hợp; mọi đường lỗi phải có điểm kết thúc có thể quan sát; và mọi side effect quan trọng phải chịu được redelivery/trùng lặp.

