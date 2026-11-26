# Phân loại lỗi tạm thời với lỗi không thể phục hồi bằng retry

## 1. Vì sao không nên retry mọi lỗi?

Khi dùng **Spring AMQP** để kết nối RabbitMQ, producer gửi sự kiện qua `RabbitTemplate` tới exchange, message được định tuyến bằng routing key và binding vào queue, rồi `@RabbitListener` nhận và xử lý. Nếu consumer thất bại, một câu hỏi quan trọng hơn “retry bao nhiêu lần?” là:

> **Lần chạy tiếp theo có khả năng thành công nếu không thay đổi message, code hoặc cấu hình không?**

Nếu database tạm thời quá tải, retry sau một khoảng chờ có thể thành công. Nếu JSON sai schema hoặc mã đơn hàng không tồn tại vì dữ liệu đầu vào vô nghĩa, việc thử cùng thao tác một nghìn lần chỉ tạo thêm tải và log. Nếu consumer gọi hệ thống thanh toán, phía thanh toán có thể **đã thực hiện giao dịch** trước khi response bị timeout; retry mù còn có thể khiến khách hàng bị tính tiền hai lần.

Ví dụ ba loại lỗi:

~~~text
Message: order.created eventId=evt-1001

A. DB trả "connection unavailable"
   -> Có thể phục hồi sau khi DB trở lại.
   -> Retry hữu hạn, có backoff.

B. amount=-100 hoặc JSON không parse được
   -> Cùng message và cùng contract sẽ tiếp tục sai.
   -> Không retry; reject/DLQ và sửa producer/schema.

C. Gọi payment API timeout sau khi request đã gửi
   -> Không biết thanh toán đã được ghi hay chưa.
   -> Đối soát theo idempotency key trước khi gửi lại.
~~~

Trong chương **Thử lại thông điệp**, bài này trình bày cách phân loại **transient**, **permanent/non-retryable** và **unknown outcome**; cách Spring AMQP xử lý exception từ `@RabbitListener`; cách dùng Spring Retry, ACK/NACK, reject/requeue và dead-letter; cách đặt giới hạn số lần thử, backoff, idempotency, transaction và quan sát hệ thống.

Trọng tâm là **xử lý thông điệp ở consumer**. Việc producer retry publish qua `RabbitTemplate` cũng được phân biệt, vì hai hướng retry tạo các dạng trùng lặp khác nhau. Các ví dụ Spring Java dùng **Spring Boot 3.x / Spring AMQP 3.x / RabbitMQ AMQP 0-9-1**; khi dùng Spring AMQP 4.x hoặc RabbitMQ 4.3+, cần đối chiếu phần lưu ý phiên bản.

## 2. Phân loại ba nhóm kết quả xử lý

### 2.1. Lỗi tạm thời (transient/retryable)

Lỗi có nguyên nhân **ngoài payload**, nhiều khả năng tự cải thiện sau một khoảng thời gian hoặc sau khi hạ tầng phục hồi:

- Database connection bị gián đoạn; transaction gặp deadlock có thể retry theo chính sách.
- API phụ thuộc trả `503 Service Unavailable` hoặc `429 Too Many Requests` có `Retry-After` hợp lệ.
- Connection tới một downstream bị reset và hệ thống xác định thao tác **chưa tạo side effect**.
- Một lock tài nguyên tạm thời đang bị service khác giữ.
- Quota hoặc rate limit được thiết kế cho phép thử lại sau một khoảng chờ.

Điều kiện quan trọng: **retry chỉ hợp lý nếu thao tác là idempotent hoặc có cơ chế an toàn trước việc chạy lại**. Một lỗi tạm thời không tự đồng nghĩa retry ngay luôn đúng.

Ví dụ giao dịch DB do deadlock có thể retry từ đầu **nếu toàn bộ transaction đã rollback** và code không phát sinh side effect không rollback được bên ngoài transaction.

### 2.2. Lỗi không thể phục hồi chỉ bằng retry (permanent/non-retryable)

Lỗi mang tính xác định với **cùng message và contract hiện tại**:

- Body không phải JSON hợp lệ, `contentType` hoặc encoding không đúng.
- Không thể deserialize do thiếu type mapping hoặc schema không tương thích.
- DTO vi phạm `@NotBlank`, `@Positive`, format hoặc required field.
- `eventType`/`schemaVersion` không được consumer hỗ trợ.
- Business rule kết luận **không thể thực hiện**: đơn hàng đã bị hủy, request yêu cầu thao tác không hợp lệ, tài nguyên đã bị xóa vĩnh viễn.
- Sai permission hoặc credentials cố định, exchange/queue không tồn tại do cấu hình sai: retry liên tục trước khi sửa hạ tầng không giúp ích.

Không nên nói “cứ `RuntimeException` là lỗi vĩnh viễn” hoặc “mọi exception database là tạm thời”. Cần xét **ngữ nghĩa của nguyên nhân sâu nhất và bối cảnh nghiệp vụ**. Một lỗi duplicate key có thể là dấu hiệu **đã xử lý thành công trước đó** (idempotent duplicate), hoặc thực sự là lỗi dữ liệu không hợp lệ.

### 2.3. Kết quả chưa xác định (ambiguous/unknown outcome)

Đây là nhóm dễ gây lỗi nghiêm trọng nhất:

~~~text
Consumer -> PaymentService: charge(orderId=ORD-1001)
PaymentService: ghi giao dịch thành công
Network: response bị mất
Consumer: nhận SocketTimeoutException
~~~

Từ phía consumer, thao tác có thể **đã thành công**. Nếu gọi lại `charge(...)` với một ID mới, khách hàng có thể bị tính tiền hai lần. Hướng xử lý đúng là:

1. Gắn **idempotency key** hoặc transaction/reference ID ổn định.
2. Truy vấn/đối soát trạng thái bên nhận theo key.
3. Chỉ retry cùng logical operation khi hợp đồng API cho phép.
4. Đánh dấu trạng thái `UNKNOWN` nếu chưa thể xác định, không gộp nhầm vào `RETRYABLE` một cách vô điều kiện.

### 2.4. Bảng quyết định

| Tình huống | Phân loại ban đầu | Hành động phù hợp |
| --- | --- | --- |
| Database timeout trước khi bắt đầu transaction | Tạm thời | Retry hữu hạn với backoff nếu hạ tầng cho phép. |
| Deadlock DB, transaction đã rollback | Tạm thời | Retry từ transaction boundary an toàn. |
| JSON malformed trước method | Không retry | Container error handler reject không requeue; DLQ nếu có DLX. |
| `@Valid` không đạt | Không retry | DLQ/quarantine, sửa dữ liệu nguồn. |
| Event type mới chưa được triển khai | Không retry ngay | Quarantine, triển khai consumer tương thích rồi replay có kiểm soát. |
| API downstream 503 | Có thể tạm thời | Backoff/circuit breaker; kiểm tra tính idempotent. |
| Payment API timeout sau request đã gửi | Outcome chưa rõ | Reconcile theo idempotency key, không gửi trùng mù. |
| Event đã có trong bảng `processed_events` | Duplicate đã xử lý | Xem là xử lý idempotent thành công và ACK. |
| Business rule từ chối vĩnh viễn | Không retry | Lưu lý do, phản hồi/bù trừ nghiệp vụ thích hợp, ACK hoặc DLQ theo contract. |
| Exchange không tồn tại khi producer publish | Cấu hình sai | Sửa topology/permission; không requeue consumer để chữa publisher. |

Không phải mọi `non-retryable` đều cần DLQ. Ví dụ một lệnh “hủy đơn đã hủy” có thể được domain quy định là **no-op thành công**; khi đó ACK là đúng. DLQ dành cho **thông điệp không xử lý được theo contract**, còn kết quả nghiệp vụ dự kiến có thể được ghi nhận như một outcome bình thường.

## 3. Một lỗi đi qua những lớp nào trong Spring AMQP?

~~~mermaid
flowchart TD
    P["RabbitTemplate producer"]
    X["Exchange → binding → queue"]
    L["Listener container nhận delivery"]
    C{"Message conversion<br/>+ argument validation"}
    M["@RabbitListener gọi service"]
    CL{"Phân loại nguyên nhân"}
    RET["Retry hữu hạn<br/>backoff"]
    R["Reject không requeue<br/>DLX / DLQ"]
    O["Reconcile UNKNOWN<br/>idempotency"]
    A["ACK thành công<br/>hoặc idempotent no-op"]
    P --> X --> L --> C
    C -- "Không hợp lệ/fatal" --> R
    C -- "Hợp lệ" --> M --> CL
    CL -- "Tạm thời" --> RET
    RET -- "Thử lại thành công" --> A
    RET -- "Hết lần thử" --> R
    CL -- "Không retry" --> R
    CL -- "Outcome chưa rõ" --> O
    O -- "Đã xử lý" --> A
    O -- "Có thể thử an toàn" --> RET
    CL -- "Thành công" --> A
~~~

Spring AMQP có các tầng khác nhau:

| Tầng | Ví dụ cơ chế | Ý nghĩa |
| --- | --- | --- |
| AMQP message conversion | `MessageConverter`, Jackson JSON | Nếu JSON/type không hợp lệ, listener method có thể chưa chạy. |
| Handler/validation | `@Payload`, `@Valid`, `@Header` | Lỗi phân giải tham số/validation có thể xảy ra trước invocation. |
| Listener method | `@RabbitListener` và domain service | Ném exception transient/permanent/ambiguous theo contract của ứng dụng. |
| Retry advice | `RetryOperationsInterceptor`, `RetryTemplate` | Thử lại lời gọi listener với policy giới hạn, trước khi lỗi thoát tới container. |
| Container `ErrorHandler` | `ConditionalRejectingErrorHandler` | Phân loại một số exception fatal, quyết định reject không requeue. |
| RabbitMQ broker | `basic.ack`, `basic.reject`, `basic.nack`, DLX | Kết thúc/requeue/dead-letter delivery theo tín hiệu từ consumer. |

Vì lỗi JSON có thể ném **trước khi method được gọi**, khối `try/catch` trong thân `@RabbitListener` không bắt được mọi lỗi. Đồng thời, một số retry advice chỉ bao quanh method invocation và không nhất thiết giải quyết lỗi conversion sớm. Do đó phải có **policy cả ở container**, không chỉ trong code nghiệp vụ.

## 4. Spring AMQP không mặc định biết lỗi nào có thể retry

Với listener container, một exception thoát khỏi method thường được bọc trong `ListenerExecutionFailedException`. Container có thể phản hồi broker tùy:

- `acknowledge-mode`: `AUTO`, `MANUAL` hoặc `NONE`;
- `defaultRequeueRejected`;
- Spring Retry advice/recoverer nếu đã gắn;
- loại exception như `AmqpRejectAndDontRequeueException` hoặc `ImmediateRequeueAmqpException`;
- `ConditionalRejectingErrorHandler` và `FatalExceptionStrategy`;
- policy DLX/DLQ và queue type của RabbitMQ.

**Đừng coi “mặc định retry” là có backoff và có số lần thử tối đa.** Việc requeue một delivery ở broker có thể dẫn đến giao lại liên tục nếu không có cơ chế delay/limit phù hợp. `Spring Retry` cũng có hành vi mặc định retry rộng, cần thêm exception classifier để không retry lỗi vĩnh viễn.

### 4.1. Hai exception điều khiển hành vi requeue

Trong Spring AMQP:

~~~java
import org.springframework.amqp.AmqpRejectAndDontRequeueException;
import org.springframework.amqp.ImmediateRequeueAmqpException;
~~~

- `AmqpRejectAndDontRequeueException`: yêu cầu reject **không requeue** khi lỗi đi tới container, bất kể `defaultRequeueRejected` ở tầng container.
- `ImmediateRequeueAmqpException`: yêu cầu **requeue** delivery, thường dùng khi chính sách container mặc định không requeue.

**Cảnh báo về retry advice:** khi một interceptor đứng ngoài method, chính interceptor cũng phải được cấu hình nhận biết exception không retry. Chỉ ném `AmqpRejectAndDontRequeueException` **bên trong method** không bảo đảm loại exception ấy không bị advice thử lại trước khi nó tới container.

### 4.2. Fatal exception trước method

`ConditionalRejectingErrorHandler` mặc định của Spring AMQP nhận diện một số loại exception **không thể phục hồi bằng retry**, điển hình:

- `org.springframework.amqp.support.converter.MessageConversionException`;
- `org.springframework.messaging.converter.MessageConversionException`;
- `org.springframework.messaging.handler.annotation.support.MethodArgumentNotValidException`;
- lỗi kiểu tham số listener, `ClassCastException` hoặc method không phù hợp trong các trường hợp được framework liệt kê.

Khi xác định fatal, handler có thể ném `AmqpRejectAndDontRequeueException` để broker không requeue. Spring AMQP cũng có những lưu ý đặc biệt về fatal message đã mang header `x-death` nhằm ngăn dead-letter loop; hành vi có thể phụ thuộc phiên bản/cấu hình.

**Không tự mở rộng danh sách fatal thành “mọi RuntimeException”.** Ngoại lệ do DB timeout thường phải được đánh giá riêng. Nếu định nghĩa thêm `FatalExceptionStrategy`, cần bảo đảm nó xử lý đúng nguyên nhân sâu xa của `ListenerExecutionFailedException`.

## 5. So sánh ba tầng retry: local, broker và delayed

| Kiểu retry | Thực hiện ở đâu? | Ưu điểm | Rủi ro/giới hạn |
| --- | --- | --- | --- |
| **Local stateless retry** | Spring Retry chạy lại listener trước khi method invocation kết thúc. | Đơn giản, ít overhead network, phù hợp lỗi thoáng qua rất ngắn. | Giữ delivery unacked và consumer thread, có thể làm chậm queue. |
| **Local stateful retry** | Spring Retry lưu retry state theo message ID, thường phối hợp rollback/redelivery. | Hữu ích khi transaction phía trên phải rollback rồi mới thử lại. | Cần message identity ổn định, quy tắc transaction/requeue rõ. |
| **Broker immediate requeue** | Consumer NACK/reject với `requeue=true`; broker giao lại. | Không giữ riêng retry trong method; consumer khác có thể nhận. | Dễ tạo **redelivery loop** tốc độ cao, tăng tải, không có backoff mặc định. |
| **Delayed retry** | Retry queue có TTL + DLX, scheduler/DB job, hoặc feature theo queue type/version. | Đợi có kiểm soát, tránh hot loop, hợp với outage dài hơn. | Topology, durability, retry accounting và khả năng mất/trùng message phức tạp hơn. |
| **Manual replay từ DLQ** | Operator/replay tool sau khi sửa lỗi. | Phù hợp schema/contract lỗi vĩnh viễn lúc tiếp nhận. | Phải chống trùng, tránh phát lại trước khi bug được sửa. |

Chọn cơ chế theo **thời gian lỗi dự kiến kéo dài**. Một DB deadlock thoáng qua có thể phù hợp local retry vài lần; outage 30 phút của dịch vụ phụ thuộc không nên được giải quyết bằng `Thread.sleep(30 phút)` trong listener.

### 5.1. Stateless và stateful không tương đương

**Stateless retry** gọi lại listener trong cùng một chuỗi xử lý, thích hợp khi service có thể chạy lại và transaction được mở riêng trong mỗi lần retry (hoặc không có transaction ngoài). Nó không phù hợp nếu **transaction bên ngoài advice** đã bị đánh dấu rollback-only sau lần thử đầu tiên.

**Stateful retry** thích hợp khi transaction bao quanh xử lý phải rollback giữa các lần redelivery. Retry context được liên kết với message identity (thường `messageId`); thiếu ID có thể ảnh hưởng hành vi recovery. Cần kiểm tra semantics với transaction manager, container factory và bản Spring AMQP đang dùng.

Không bật stateful chỉ vì nghe có vẻ “bền vững hơn”: retry state không thay thế inbox/outbox database và cũng không tạo exactly-once delivery.

## 6. Ví dụ tự chứa: event, queue, exchange và listener

Ví dụ sau dành cho **Spring Boot 3.x, Spring AMQP 3.x, Java 17+** và RabbitMQ AMQP 0-9-1. Một ứng dụng đơn giản nhận sự kiện tạo đơn hàng, kiểm tra dữ liệu rồi gọi application service.

### 6.1. Dependencies

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-amqp'
    implementation 'org.springframework.boot:spring-boot-starter-json'
    implementation 'org.springframework.retry:spring-retry'
}
~~~

`spring-retry` phải có trên classpath nếu dùng interceptor của Spring Retry. Ở Spring Boot 3.x, Jackson JSON converter đi cùng Jackson 2; nếu chuyển sang Spring AMQP 4.x/Jackson 3, thay converter và starter/dependencies theo bộ phiên bản tương thích.

`application.yml` cho lab:

~~~yaml
spring:
  rabbitmq:
    host: localhost
    port: 5672
    username: guest
    password: guest
    listener:
      simple:
        acknowledge-mode: auto
        prefetch: 5
~~~

`guest/guest` chỉ phù hợp demo localhost; production cần tài khoản/vhost/permission riêng và cơ chế bảo vệ secrets/TLS.

### 6.2. Khai báo topology có DLX/DLQ

~~~java
import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrderRetryTopology {
    public static final String EXCHANGE = "orders.events";
    public static final String ROUTING_KEY = "order.created";
    public static final String QUEUE = "orders.process.q";
    public static final String DLX = "orders.dead";
    public static final String DLQ = "orders.failed.q";

    @Bean
    DirectExchange ordersExchange() {
        return new DirectExchange(EXCHANGE, true, false);
    }

    @Bean
    DirectExchange deadExchange() {
        return new DirectExchange(DLX, true, false);
    }

    @Bean
    Queue ordersQueue() {
        return QueueBuilder.durable(QUEUE)
                .deadLetterExchange(DLX)
                .deadLetterRoutingKey("orders.failed")
                .build();
    }

    @Bean
    Queue deadQueue() {
        return QueueBuilder.durable(DLQ).build();
    }

    @Bean
    Binding ordersBinding(Queue ordersQueue, DirectExchange ordersExchange) {
        return BindingBuilder.bind(ordersQueue)
                .to(ordersExchange)
                .with(ROUTING_KEY);
    }

    @Bean
    Binding deadBinding(Queue deadQueue, DirectExchange deadExchange) {
        return BindingBuilder.bind(deadQueue)
                .to(deadExchange)
                .with("orders.failed");
    }
}
~~~

Spring `RabbitAdmin` có thể khai báo topology qua các bean nếu cấu hình connection phù hợp. Trong production, RabbitMQ khuyến nghị cân nhắc cấu hình DLX bằng **policy** để điều chỉnh mà không redeclare queue; ở lab, queue arguments giúp ví dụ tự chứa.

**Quan trọng:** reject không requeue chỉ vào DLQ nếu **DLX và binding đích tồn tại, hợp lệ**. Nếu không cấu hình DLX, RabbitMQ có thể discard message. DLX không tự biến mọi loại lỗi thành retry có backoff.

### 6.3. DTO và exception nghiệp vụ

~~~java
public record OrderCreatedEvent(
        String eventId,
        String orderId,
        long amount,
        String schemaVersion
) {}
~~~

Hai exception mô tả **ý nghĩa lỗi**, không bắt caller phải suy từ một số mã lỗi chung:

~~~java
public class TransientDependencyException extends RuntimeException {
    public TransientDependencyException(String message, Throwable cause) {
        super(message, cause);
    }
}

public class InvalidOrderEventException extends RuntimeException {
    public InvalidOrderEventException(String message) {
        super(message);
    }
}
~~~

Hai class public đặt trong **hai file Java tương ứng** khi triển khai dự án. Đây là ví dụ các mảnh code của bài học, không yêu cầu ghép mọi block thành một file duy nhất.

### 6.4. Listener kiểm tra contract trước khi thực hiện side effect

~~~java
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class OrderCreatedListener {
    private final OrderProcessingService orderService;

    public OrderCreatedListener(OrderProcessingService orderService) {
        this.orderService = orderService;
    }

    @RabbitListener(
            queues = OrderRetryTopology.QUEUE,
            containerFactory = "ordersRetryFactory")
    public void handle(OrderCreatedEvent event) {
        if (event.eventId() == null || event.eventId().isBlank()) {
            throw new InvalidOrderEventException("Missing eventId");
        }
        if (!"1".equals(event.schemaVersion())) {
            throw new InvalidOrderEventException("Unsupported schemaVersion");
        }
        if (event.amount() <= 0) {
            throw new InvalidOrderEventException("amount must be positive");
        }

        // Service phải ghi idempotency marker cùng transaction nghiệp vụ.
        // Nếu dependency lỗi tạm thời, service có thể ném
        // TransientDependencyException kèm root cause.
        orderService.applyIdempotently(event);
    }
}
~~~

`OrderProcessingService` là domain/application service do dự án triển khai. Contract:

~~~java
public interface OrderProcessingService {
    // Thành công/no-op đã xử lý -> return.
    // Dependency tạm thời -> TransientDependencyException.
    // Outcome không rõ -> cần reconciliation theo eventId.
    void applyIdempotently(OrderCreatedEvent event);
}
~~~

**Không được quăng `TransientDependencyException` cho mọi lỗi chưa hiểu.** Nếu DB báo unique constraint do eventId đã được xử lý, service nên phát hiện duplicate có chủ đích và trả về thành công/no-op, để listener ACK thay vì retry hoặc DLQ.

## 7. Cấu hình retry phân loại theo exception

### 7.1. Vì sao cần xét cause chain?

Spring listener thường bọc exception trong `ListenerExecutionFailedException`. Nếu retry classifier chỉ xét class ngoài cùng, cả `InvalidOrderEventException` và `TransientDependencyException` có thể trông giống nhau.

Spring Retry hỗ trợ `SimpleRetryPolicy` với `traverseCauses=true`, cho phép phân loại theo nguyên nhân nằm sâu bên trong:

~~~java
import java.util.HashMap;
import java.util.Map;
import org.springframework.retry.policy.SimpleRetryPolicy;

Map<Class<? extends Throwable>, Boolean> retryable = new HashMap<>();
retryable.put(TransientDependencyException.class, true);
retryable.put(InvalidOrderEventException.class, false);

// 4 lần thực thi TỔNG CỘNG: lần đầu + tối đa 3 retry.
// traverseCauses=true: xét nguyên nhân bên trong wrapper.
// defaultValue=false: lỗi không được khai báo thì không retry.
SimpleRetryPolicy policy =
        new SimpleRetryPolicy(4, retryable, true, false);
~~~

Giá trị `maxAttempts=4` nghĩa là **tổng số lần gọi**, không phải bốn retry sau lần đầu. Dùng `defaultValue=false` là cách thận trọng: khi xuất hiện loại exception mới, hãy phân loại nó trước khi quyết định retry. Trong production, xác định rõ các loại timeout, lỗi DB và mã HTTP nào có thể retry, tránh dựa hoàn toàn vào tên exception bao ngoài.

### 7.2. Retry interceptor với exponential backoff và recoverer

~~~java
import java.util.Map;
import org.springframework.amqp.rabbit.config.RetryInterceptorBuilder;
import org.springframework.amqp.rabbit.config.SimpleRabbitListenerContainerFactory;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.amqp.rabbit.retry.RejectAndDontRequeueRecoverer;
import org.springframework.amqp.support.converter.Jackson2JsonMessageConverter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.retry.interceptor.RetryOperationsInterceptor;
import org.springframework.retry.policy.SimpleRetryPolicy;

@Configuration
public class OrderRetryConfiguration {

    @Bean
    Jackson2JsonMessageConverter ordersJsonConverter() {
        return new Jackson2JsonMessageConverter();
    }

    @Bean
    RetryOperationsInterceptor orderRetryInterceptor() {
        SimpleRetryPolicy policy = new SimpleRetryPolicy(
                4,
                Map.of(
                        TransientDependencyException.class, true,
                        InvalidOrderEventException.class, false
                ),
                true,
                false
        );

        return RetryInterceptorBuilder.stateless()
                .retryPolicy(policy)
                .backOffOptions(500L, 2.0, 5_000L)
                .recoverer(new RejectAndDontRequeueRecoverer())
                .build();
    }

    @Bean
    SimpleRabbitListenerContainerFactory ordersRetryFactory(
            ConnectionFactory connectionFactory,
            Jackson2JsonMessageConverter ordersJsonConverter,
            RetryOperationsInterceptor orderRetryInterceptor) {
        SimpleRabbitListenerContainerFactory factory =
                new SimpleRabbitListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setMessageConverter(ordersJsonConverter);
        factory.setPrefetchCount(5);
        factory.setConcurrentConsumers(2);
        factory.setDefaultRequeueRejected(false);
        factory.setAdviceChain(orderRetryInterceptor);
        return factory;
    }
}
~~~

**Ý nghĩa của cấu hình:**

1. `retryPolicy` cho phép retry **chỉ** với `TransientDependencyException` được nhận diện trong cause chain.
2. `backOffOptions(500, 2.0, 5000)` tạo thời gian đợi tăng dần giữa các lần thử, có trần 5 giây trong ví dụ. Không nên dựa vào backoff này để xử lý outage hàng giờ.
3. `RejectAndDontRequeueRecoverer` được gọi khi retry không thể tiếp tục/hết số lần thử; nó yêu cầu reject không requeue, cho phép message vào DLQ khi có DLX.
4. `setAdviceChain(...)` gắn retry vào listener container factory, không tự áp dụng cho mọi listener khác trong ứng dụng.
5. `setDefaultRequeueRejected(false)` làm lỗi thoát ra còn lại không tự bị requeue nóng; đây là **policy ví dụ có chủ ý**. Production có thể dùng policy riêng cho từng nhóm lỗi và route.
6. Với Spring Boot auto-config, nếu tự tạo factory riêng, phải cấu hình converter, retry và error handling phù hợp; không giả định mọi thiết lập của factory mặc định được tự sao chép.

**Lưu ý phiên bản:** ví dụ Java dùng `Jackson2JsonMessageConverter` cho Spring AMQP 3.x. Spring AMQP 4.x chuyển sang API `JacksonJsonMessageConverter` dựa trên Jackson 3; cần chọn dependency và converter theo bộ Spring/Boot thực tế. Các API Spring Retry cũng phải khớp version.

### 7.3. Không nhầm recoverer với “thành công nghiệp vụ”

Spring Retry `MessageRecoverer` có thể **xử lý hết lỗi rồi trả về bình thường**. Nếu recoverer mặc định chỉ log/cầm lỗi mà không ném exception, container có thể **ACK message** và RabbitMQ **không dead-letter**, dù nghiệp vụ chưa được xử lý.

Đó là lý do ví dụ dùng `RejectAndDontRequeueRecoverer` khi mục tiêu là reject/DLQ sau retry. Một lựa chọn khác là `RepublishMessageRecoverer` để **phát lại message lỗi sang error exchange**, thêm metadata exception. Khi recoverer republish thành công rồi trả về, delivery gốc có thể được ACK; cần thiết kế publisher confirms/returns và rủi ro crash giữa republish/ACK nếu yêu cầu độ tin cậy cao.

**Không dùng cả hai recovery chiến lược cho cùng một lỗi mà không hiểu kết quả cuối:** 

- `RejectAndDontRequeueRecoverer` → broker reject delivery cũ; DLX thực hiện dead-letter nếu được cấu hình.
- `RepublishMessageRecoverer` → ứng dụng chủ động publish một message mới tới error exchange; delivery cũ có thể được ACK.

Không phải hai cơ chế này tự giống nhau về durability, headers, routing hoặc khả năng mất/trùng message.

## 8. Producer gửi event có ID ổn định

Nếu listener nhận `OrderCreatedEvent` theo JSON, producer cần converter phù hợp. Ví dụ một `RabbitTemplate` tường minh:

~~~java
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.amqp.support.converter.Jackson2JsonMessageConverter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrderPublisherConfiguration {

    @Bean
    RabbitTemplate rabbitTemplate(
            ConnectionFactory connectionFactory,
            Jackson2JsonMessageConverter ordersJsonConverter) {
        RabbitTemplate template = new RabbitTemplate(connectionFactory);
        template.setMessageConverter(ordersJsonConverter);
        return template;
    }
}
~~~

Producer:

~~~java
import java.util.UUID;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderEventPublisher {
    private final RabbitTemplate template;

    public OrderEventPublisher(RabbitTemplate template) {
        this.template = template;
    }

    public void publish(OrderCreatedEvent event) {
        template.convertAndSend(
                OrderRetryTopology.EXCHANGE,
                OrderRetryTopology.ROUTING_KEY,
                event,
                message -> {
                    message.getMessageProperties().setMessageId(event.eventId());
                    return message;
                }
        );
    }

    public void publishOne() {
        String id = UUID.randomUUID().toString();
        publish(new OrderCreatedEvent(id, "ORD-1001", 250_000L, "1"));
    }
}
~~~

**Lưu ý:** khi retry **cùng một logical event** vì producer không biết publisher confirm đã tới chưa, phải giữ nguyên `eventId/messageId`, không gọi lại `publishOne()` để tạo UUID mới cho event cũ. Consumer không thể dựa vào delivery tag để phát hiện bản sao do producer gửi lại.

Một lần `RabbitTemplate.convertAndSend(...)` không ném exception **không có nghĩa** consumer đã xử lý. Publisher confirms/mandatory returns thuộc giai đoạn gửi, còn retry và ACK/NACK của listener thuộc giai đoạn nhận.

## 9. Khi lỗi xuất hiện trước method @RabbitListener

Một message sai JSON có thể thất bại ở **message conversion** trước khi Spring gọi `OrderCreatedListener.handle(...)`. Khi đó:

- Method không thể `catch` lỗi vì nó chưa được invoke.
- `RetryOperationsInterceptor` gắn với method invocation không phải cơ chế duy nhất để xử lý.
- `ConditionalRejectingErrorHandler` của container có thể xác định lỗi conversion hoặc argument validation là **fatal** và reject không requeue.
- DLQ chỉ nhận message nếu topology dead-letter hợp lệ; nếu chưa có DLX, thông điệp có thể bị discard theo broker.

Ví dụ body lỗi:

~~~text
Body: {"eventId": "evt-1001", "amount": }
contentType: application/json

=> Jackson JSON converter không parse được.
=> Không nên requeue vô hạn message này.
=> Ghi root cause và giữ message lỗi ở DLQ/quarantine nếu cần.
~~~

Đừng cố giải quyết bằng cách **bắt mọi lỗi rồi ném `ImmediateRequeueAmqpException`**. Điều đó có thể vô hiệu hóa việc loại poison message và tạo requeue loop.

## 10. Retry nội bộ giữ delivery unacked

Trong local stateless retry, listener có thể chạy lại nhiều lần **trước khi container xác nhận delivery**. Giả sử retry bốn lần với backoff:

~~~text
T0:       Broker giao evt-1001 -> UNACKNOWLEDGED
T0:       Attempt #1 -> DB timeout
T0+0.5s:  Attempt #2 -> DB timeout
T0+1.5s:  Attempt #3 -> DB timeout
T0+3.5s:  Attempt #4 -> thành công
T0+...:   Container ACK
~~~

Trong khoảng đó, delivery vẫn có thể giữ **một slot prefetch**; với rất nhiều consumer và retry chậm, throughput giảm và `messages_unacknowledged` tăng. Nếu retry/blocking kéo dài quá broker **consumer acknowledgement timeout**, channel có thể bị đóng trước khi ACK.

Điều chỉnh đồng thời:

- `maxAttempts`: số lần thử tổng, kể cả lần đầu.
- Backoff: thời gian đợi tăng dần; thêm jitter nếu retry ở nhiều replicas cùng lúc.
- Prefetch: số delivery chưa ACK mà một consumer có thể giữ.
- Concurrency: số consumer xử lý song song, cần phù hợp CPU/DB/downstream.
- Timeout của service và broker consumer ACK; không cho retry giữ delivery vô hạn.

Với outage kéo dài nhiều phút, cân nhắc **delayed retry** hoặc job/outbox bền vững thay vì giữ một listener thread ngủ.

## 11. Broker requeue không tự có backoff

### 11.1. Vì sao requeue=true có thể gây vòng lặp nóng?

Nếu listener luôn ném lỗi và container liên tục reject/NACK với `requeue=true`, broker có thể lập tức giao lại message:

~~~mermaid
flowchart LR
    Q["orders.process.q"]
    C["@RabbitListener"]
    E["Transient failure?"]
    Q -->|"Deliver"| C -->|"NACK/requeue=true"| Q
    C -->|"Không có delay, lặp lại"| E
~~~

Khi tất cả consumers đều từ chối cùng message ngay lập tức, requeue/redelivery loop tiêu thụ CPU, network và log mà không làm downstream phục hồi nhanh hơn. Không có cơ chế exponential backoff chỉ vì đặt `requeue=true`.

### 11.2. BasicReject và BasicNack: khác nhau ở RabbitMQ mới

Trong RabbitMQ AMQP 0-9-1, `basic.reject` từ chối **một delivery**, còn `basic.nack` có thể từ chối nhiều delivery với `multiple=true`. Tuy nhiên, trong **RabbitMQ 4.3+**, quorum queue còn phân biệt hai tín hiệu này khi đếm poison-message failures:

| Tín hiệu requeue | RabbitMQ 4.3+ với quorum queue | Hàm ý |
| --- | --- | --- |
| `basic.reject(requeue=true)` | Tính như một delivery xử lý thất bại, tăng `delivery-count`. | Có thể tiến tới `delivery-limit` rồi dead-letter/drop. |
| `basic.nack(requeue=true)` | Là tín hiệu không xử lý delivery; tăng `acquired-count`, **không tăng `delivery-count`**. | Chỉ dựa vào delivery-limit có thể **không** ngăn vòng lặp NACK. |

Đây là **hành vi phụ thuộc phiên bản và loại queue**. Trong RabbitMQ **4.2 trở về trước**, cách đếm requeue khác. Không dựa vào một mô tả cố định cho mọi broker. Khi thiết kế poison-message policy với quorum queue, kiểm tra **RabbitMQ version, queue arguments/policy, `x-delivery-count` và `x-acquired-count`**, đồng thời kiểm tra Spring container đang phát loại ACK/NACK/Reject nào.

RabbitMQ 4.0 trở đi có quorum queue `delivery-limit` mặc định là **20** trong nhiều cấu hình, nhưng giới hạn này không thay thế retry policy nghiệp vụ. Khi vượt limit, message có thể được dead-letter hoặc drop tùy DLX. Nếu dùng classic queue, không tự giả định có cùng cơ chế delivery limit.

### 11.3. Manual ACK/NACK phải cẩn thận

~~~java
// Trong method @RabbitListener với AcknowledgeMode.MANUAL:
channel.basicAck(deliveryTag, false);           // Hoàn tất delivery.
channel.basicReject(deliveryTag, false);        // Reject, không requeue.
channel.basicNack(deliveryTag, false, true);    // Requeue; có thể tạo hot loop.
~~~

Đây là **ba lựa chọn thay thế**, **không được gọi cả ba cho cùng một delivery**. `deliveryTag` có phạm vi channel, không phải event ID. Double ACK/NACK có thể đóng channel vì delivery tag không hợp lệ. Không tự thử Manual ACK khi listener factory vẫn để `AUTO` rồi gửi ACK chồng lấn.

## 12. Retry có độ trễ và DLQ: thiết kế đường đi

Một topology retry có backoff có thể trông như sau:

~~~mermaid
flowchart LR
    MAIN["Main queue<br/>orders.process.q"]
    C["Consumer"]
    R["Retry queue<br/>TTL/backoff"]
    DL["Dead-letter exchange"]
    FINAL["Final DLQ<br/>orders.failed.q"]
    MAIN --> C
    C -- "Transient, còn lượt thử" --> R
    R -- "Hết delay, quay về main" --> MAIN
    C -- "Permanent hoặc hết lượt thử" --> DL --> FINAL
~~~

**Lưu ý về semantics:** với TTL + DLX, thông điệp có thể đi theo vòng *main → retry queue → main*. Cần thiết kế rõ:

- Bao nhiêu lần thử là tối đa? Lưu count phù hợp, không reset vô hạn.
- Retry được tính theo **attempt nghiệp vụ** hay **số lần delivery broker**?
- Có duy trì `eventId` ổn định không? Có.
- Sau khi đủ attempts, message sẽ vào **final DLQ** hay bị discard?
- DLX/binding có đúng không, có loop vô hạn hay không?
- Delivery/requeue và việc publish qua các queue có bảo đảm gì khi broker/node lỗi?

RabbitMQ có các lựa chọn mới **quorum queue delayed retry** trên những phiên bản hỗ trợ; khi dùng, nên so sánh với topology TTL/DLX và chọn cơ chế phù hợp queue type, phiên bản và bảo đảm dữ liệu. Đừng mặc định mọi classic/quorum queue hoặc mọi RabbitMQ release đều có cùng feature.

### 12.1. DLQ không phải “nơi retry ngay”

**DLQ cuối** dùng để cách ly message không xử lý được trong điều kiện hiện tại, giữ bằng chứng cho việc điều tra, sửa contract rồi replay. **Retry queue** là nơi chờ có chủ đích cho lỗi có thể phục hồi.

Nếu mọi message lỗi đều đi tới một DLQ có TTL rồi tự quay về main mà không có giới hạn, lỗi JSON vĩnh viễn sẽ chạy vòng mãi. Cần **đường thoát cuối**, số attempts hữu hạn và cảnh báo.

### 12.2. Không tự nghĩ rằng x-death là attempt count chính xác

`x-death` là metadata do broker thêm/cập nhật khi message đi qua dead-lettering, có thông tin như reason, queue, exchange, count theo cách RabbitMQ tổng hợp. Nó **không tự đồng nghĩa** số lần method Java thực sự đã chạy, đặc biệt khi:

- Local retry diễn ra nhiều lần trên **một delivery**.
- Producer tự republish một message mới.
- Message đi qua nhiều retry queues.
- Broker thay đổi/ghi đè/cô đọng một số headers qua dead-letter.

Nếu cần giới hạn retry nghiệp vụ chính xác, giữ `attemptId` hoặc retry state do hệ thống kiểm soát, dùng cùng `eventId` cho logical event, và so sánh với broker headers như tín hiệu bổ trợ.

## 13. Không thể retry an toàn khi outcome chưa rõ

Đối với tác vụ có **external side effect**, đặc biệt thanh toán, gửi email, phát thông báo hoặc gọi API ghi dữ liệu:

~~~text
Step 1: Consumer gọi downstream đặt hàng/charge.
Step 2: Downstream COMMIT thành công.
Step 3: Mất kết nối trước khi response tới consumer.
Step 4: Listener ném timeout.
Step 5: Local retry chạy lại cùng hành động.
~~~

Lần retry có thể gây **double charge**, hai email hoặc hai đơn hàng nếu không có cơ chế an toàn.

Giải pháp:

1. Tạo `operationId`/`idempotencyKey` ổn định cho **một logical operation**, độc lập attempt ID.
2. Gửi key tới downstream trong mỗi retry, nếu downstream hỗ trợ idempotency.
3. Nếu downstream hỗ trợ truy vấn trạng thái theo key, đối soát trước khi tạo thao tác khác.
4. Nếu chưa biết kết quả, đánh dấu `UNKNOWN` để tiếp tục reconciliation, không tự “coi là thất bại” rồi tạo request mới.
5. Khi phát event tiếp theo dựa trên side effect, dùng **transactional outbox** hoặc cơ chế đáng tin cậy tương đương.

**Idempotency của consumer và producer giải quyết các lớp khác nhau:**

- Producer có thể gửi lại event sau khi mất publisher confirm.
- Broker có thể redeliver khi consumer commit DB nhưng mất ACK.
- Consumer có thể retry lời gọi downstream.

Cả ba đều có nguy cơ trùng. Một `eventId` ổn định và transaction/idempotency contract là nền tảng để chịu được những vòng retry đó.

## 14. Transactional outbox, inbox và ranh giới ACK

### 14.1. Inbox/idempotent consumer

Mẫu table:

~~~sql
CREATE TABLE processed_events (
    consumer_name VARCHAR(100) NOT NULL,
    event_id      VARCHAR(100) NOT NULL,
    processed_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Khi consumer nhận `evt-1001`, trong **một transaction database**:

1. Thử đăng ký khóa `(consumer_name, event_id)`.
2. Nếu đã có và trạng thái đã hoàn tất, coi là duplicate, **không chạy lại side effect**.
3. Nếu chưa có, thực hiện nghiệp vụ và đánh dấu đã xử lý **trong cùng transaction**.
4. Sau khi commit thành công, listener kết thúc để container `AUTO` gửi ACK.

Không chỉ ghi dấu `processed` trước rồi mới thực hiện nghiệp vụ ở transaction khác: nếu crash giữa hai bước, retry có thể thấy “đã xử lý” và bỏ qua việc chưa từng hoàn tất. Với side effect ngoài DB, cần idempotency ở downstream hoặc saga/compensation rõ ràng.

### 14.2. Outbox ở producer

Producer ghi dữ liệu nghiệp vụ và record sự kiện vào outbox trong cùng transaction DB. Publisher worker gửi event từ outbox, đợi publisher confirm/return rồi cập nhật trạng thái. Nếu không nhận confirm, event có thể **đã vào broker hoặc chưa**; worker retry với **cùng event ID**.

Outbox giảm nguy cơ **bỏ sót publish**, inbox/idempotency giảm nguy cơ **xử lý trùng**. Cả hai không biến RabbitMQ thành exactly-once delivery; chúng cho phép triển khai **at-least-once với side effect có kiểm soát**.

### 14.3. Chọn ACK mode

| ACK mode của Spring | Ý nghĩa | Khi retry cần chú ý |
| --- | --- | --- |
| `AUTO` | Container ACK sau method thành công, phản hồi lỗi theo container. | Local retry giữ delivery unacked; lỗi cuối cùng do recoverer/error handler quyết định. |
| `MANUAL` | Code gửi `basicAck/basicNack/basicReject`. | Phải xác nhận đúng một lần; lỗi trước method cần container error handler; không nhầm deliveryTag với eventId. |
| `NONE` | Broker không chờ ACK sau processing. | Nếu consumer lỗi, broker có thể coi delivery đã xong; không phù hợp khi cần retry tin cậy. |

Đừng nhầm `AcknowledgeMode.AUTO` của Spring với RabbitMQ `autoAck=true`. Trong AUTO, container ACK sau xử lý; trong NONE broker không đợi ACK thủ công.

## 15. Kiểm soát tổng số lần thử và ngân sách thời gian

Một retry policy không nên chỉ có `maxAttempts`. Cần kiểm soát:

| Thành phần | Ý nghĩa |
| --- | --- |
| Max attempts | Tổng số lần xử lý cho một logical event, tính cả lần đầu theo quy ước. |
| Per-attempt timeout | Mỗi lời gọi downstream/DB chờ tối đa bao lâu. |
| Backoff + jitter | Giảm retry đồng thời từ nhiều service replicas. |
| Total retry budget | Thời gian tối đa từ lần nhận đầu đến khi đưa vào retry delay/DLQ. |
| Circuit breaker | Giảm gọi downstream khi hệ thống phụ thuộc đang lỗi hàng loạt. |
| Consumer prefetch | Không nhận trước quá nhiều delivery đang đợi ACK. |
| Consumer acknowledgement timeout | Broker có thể đóng channel nếu delivery giữ quá lâu. |
| DLQ/quarantine policy | Đường xử lý cuối khi lỗi không thể khôi phục hoặc hết số lần thử. |

### 15.1. Ví dụ tính tổng thời gian local retry

Giả sử bốn attempts, mỗi attempt có timeout 3 giây, backoff giữa các attempts là 0,5 giây, 1 giây và 2 giây:

\[
\text{Worst-case local duration} \approx 4\times3 + 0.5+1+2 = 15.5\text{ giây}
\]

Chưa tính overhead của application, DB và ACK. Nếu broker consumer timeout ở mức giới hạn gần đó, phải giảm tổng retry budget hoặc chuyển delayed retry để không giữ delivery quá lâu. Trong thực tế, không tự cấu hình consumer timeout quá thấp; kiểm tra ngưỡng RabbitMQ đang áp dụng.

### 15.2. Retry storm

Khi 20 replicas cùng gọi một dịch vụ đang lỗi và mỗi instance retry nhiều lần ngay lập tức, tải lên downstream có thể tăng gấp bội đúng lúc nó yếu nhất. Dùng **exponential backoff, jitter, circuit breaker, bounded concurrency** và khả năng trả event về hàng chờ bền vững khi sự cố kéo dài.

Không để `Thread.sleep(...)` dài trong mỗi listener như giải pháp production cho outage hàng chục phút.

## 16. Quan sát: đếm lỗi theo nguyên nhân, không chỉ đếm exception

### 16.1. Chỉ số hữu ích

| Metric đề xuất | Ý nghĩa |
| --- | --- |
| `message_processing_success_total` | Số lần xử lý nghiệp vụ thành công/no-op idempotent. |
| `message_failure_total{classification}` | Lỗi theo transient/permanent/unknown. |
| `message_retry_attempt_total{reason}` | Tổng attempts thực tế do Spring/app thực hiện. |
| `message_retry_exhausted_total` | Event vượt retry budget. |
| `message_dlq_total{reason}` | Message được đưa vào DLQ theo nhóm nguyên nhân. |
| `message_reconciliation_pending` | Event có external side effect outcome chưa rõ. |
| `message_duplicate_suppressed_total` | Những event đã xử lý trước đó, được bỏ qua an toàn. |
| `queue_messages_ready` / `queue_messages_unacknowledged` | Backlog và delivery chưa ACK. |
| `queue_redeliver_rate` | Tần suất broker giao lại message. |
| `listener_processing_duration` p95/p99 | Thời gian xử lý và tác động của retry đồng bộ. |
| `downstream_failure_rate` / `downstream_circuit_open` | Phân biệt outage phụ thuộc với poison message. |

Các tên trên là **đề xuất instrumentation ứng dụng**, không mặc định là metric built-in của Spring/RabbitMQ. Log nên có `eventId`, `attemptId`, `correlationId`, exchange, routing key, queue, vhost, exception root cause, retry classification và outcome.

### 16.2. Bảng chẩn đoán

| Triệu chứng | Nghi vấn | Cách kiểm tra |
| --- | --- | --- |
| Message lỗi JSON được xử lý lặp vô hạn | Fatal conversion chưa được reject, hoặc DLX loop. | Container ErrorHandler, content type, DLX, `x-death`. |
| DB timeout tăng, unacked tăng | Local retry quá dài hoặc DB pool cạn. | Retry policy, prefetch, DB timeout, concurrency. |
| DLQ trống dù lỗi liên tục | Recoverer “log rồi nuốt lỗi”, không có DLX, hoặc còn requeue. | `MessageRecoverer`, `defaultRequeueRejected`, queue arguments. |
| Một payment được ghi hai lần | Retry sau timeout không đối soát/idempotent. | Stable operation ID, downstream idempotency logs. |
| Quorum queue không đạt delivery limit dù requeue liên tục | RabbitMQ 4.3+ và `basic.nack(requeue=true)` không tăng delivery-count. | Broker version, `x-acquired-count`, `x-delivery-count`, actual reject/nack. |
| Consumer bị đóng channel khi retry lâu | Consumer ACK timeout. | Broker logs, processing duration, prefetch, retry budget. |
| Số retry ở log lớn hơn broker redelivery count | Local Spring Retry diễn ra trong cùng delivery. | Interceptor metrics vs RabbitMQ headers. |
| Message cùng eventId đến lại sau publisher confirm thất lạc | Producer retry publish. | Outbox attempts, eventId, deduplication. |

Một dashboard tốt cần phân biệt **số lần thử ứng dụng** với **số lần broker giao lại**; đó không phải một bộ đếm chung.

## 17. Bài thực hành theo từng loại lỗi

Thực hành với RabbitMQ cục bộ có Management UI và Spring Boot 3.x. Không gây lỗi giả lập trên queue production.

| Bước | Thao tác | Điều cần xác minh |
| --- | --- | --- |
| 1 | Khởi động topology ở mục 6 và listener với factory retry ở mục 7. | Exchange, queue chính, DLX/DLQ và converter hoạt động. |
| 2 | Gửi `OrderCreatedEvent` hợp lệ. | Service xử lý thành công, consumer ACK, không vào DLQ. |
| 3 | Cho service ném `TransientDependencyException` hai lần rồi thành công ở lần thứ ba. | Retry advice thực hiện ba attempts với backoff; chỉ một delivery broker. |
| 4 | Cho service luôn ném `TransientDependencyException`. | Hết tổng bốn attempts; recoverer reject không requeue, DLQ có message nếu DLX đúng. |
| 5 | Gửi event có `amount=-100`. | `InvalidOrderEventException` không được retry nhiều lần; lỗi được xử lý theo policy. |
| 6 | Gửi raw message JSON lỗi cú pháp với content type JSON. | Converter/handler báo fatal trước method; kiểm tra DLQ và root cause. |
| 7 | Tắt DB ngắn hạn rồi bật lại. | Local retry có thể thành công nếu outage ngắn; nếu outage dài, thử delayed retry để không giữ consumer thread. |
| 8 | Cho payment mock ghi thành công rồi ném timeout. | Consumer không tạo charge trùng nếu retry cùng idempotency key/reconcile. |
| 9 | Gửi lại cùng `eventId` như một message mới. | Inbox/unique eventId chặn side effect trùng, listener ACK no-op. |
| 10 | Bật `requeue=true` liên tục chỉ trong lab cô lập. | Thấy redelivery loop; so sánh với backoff giới hạn và DLQ. |
| 11 | Nếu dùng quorum queue 4.3+, kiểm chứng sự khác nhau giữa `basic.reject` và `basic.nack` qua headers/broker metrics. | Không dựa nhầm vào delivery-limit để chặn NACK loop. |
| 12 | Cố ý gửi message hết số lần thử vào DLQ, sửa code/schema rồi replay có kiểm soát. | EventId giữ nguyên, không lặp side effect, có audit replay. |

### Mẫu ghi kết quả

~~~text
Spring AMQP / RabbitMQ version:
Queue type: classic / quorum
Message ID / Event ID:
Publish attempt ID:
Listener delivery number (nếu đo được):
Spring Retry attempt number:
Root cause:
Classification: TRANSIENT / PERMANENT / UNKNOWN / DUPLICATE
Configured maxAttempts:
Backoff / jitter:
Duration of attempts and total:
ACK / NACK / reject / requeue:
RabbitMQ redelivered / x-death / x-delivery-count:
DLQ outcome:
Idempotency result:
DB transaction / downstream reconciliation:
~~~

Để thực hiện test JSON lỗi, có thể dùng `RabbitTemplate.send(...)` với raw `org.springframework.amqp.core.Message` và `contentType=application/json`; đừng chỉ gửi một String mà converter tự đánh dấu `text/plain` rồi suy ra listener đang kiểm tra JSON. Các test phải tách rõ **conversion failure trước method** và **business exception trong method**.

## 18. Các sai lầm thường gặp

**“Lỗi là exception thì cứ retry năm lần.”** Không. Lỗi JSON sai hoặc validation vi phạm sẽ vẫn sai; retry chỉ thêm tải.

**“Mọi timeout đều retry được.”** Không. Timeout sau khi downstream có thể đã commit phải được đối soát theo idempotency key.

**“Đã bật Spring Retry thì không cần DLQ.”** Không. Khi hết số lần thử hoặc lỗi không retryable, vẫn cần outcome/quarantine có thể điều tra.

**“Đã dùng DLQ là message không thể mất.”** Không. Phải cấu hình DLX/binding, queue durability, queue type và dead-letter safety; DLX có thể có giới hạn khi broker/node không sẵn sàng.

**“defaultRequeueRejected=false là phân loại lỗi thông minh.”** Không. Đây là policy chung, có thể reject cả lỗi tạm thời nếu thiếu retry advice/handler riêng.

**“Ném AmqpRejectAndDontRequeueException thì Spring Retry luôn bỏ qua nó.”** Không tự động. Retry advice cần phân loại exception; nếu không, advice vẫn có thể retry trước khi lỗi tới container.

**“x-death cho biết chính xác số lần code xử lý.”** Không. Spring Retry, republish và dead-letter tạo nhiều tầng attempt khác nhau.

**“Quorum delivery-limit luôn chặn requeue=true.”** Không. RabbitMQ 4.3+ phân biệt `basic.reject` với `basic.nack` trong cách tăng delivery-count.

**“Prefetch=1 đảm bảo xử lý một lần duy nhất.”** Không. ACK thất lạc sau DB commit vẫn có thể redeliver; cần idempotency.

**“Recoverer trả về bình thường nghĩa là đã xử lý nghiệp vụ.”** Không. Recoverer có thể chỉ log rồi khiến container ACK; phải chọn recovery semantics có chủ đích.

**“Một loop DLQ có TTL là retry policy hoàn chỉnh.”** Không. Cần giới hạn số attempts, đường thoát cuối, bảo toàn ID, quan sát và xử lý poison message.

## 19. Câu hỏi tự kiểm tra

**Câu 1.** JSON sai cú pháp, retry sau 5 giây có giúp message parse được không?

**Trả lời:** Không, nếu body/contract không thay đổi. Reject không requeue, lưu DLQ/quarantine để sửa.

**Câu 2.** `maxAttempts=4` trong `SimpleRetryPolicy` cho phép bao nhiêu lần retry sau lần đầu?

**Trả lời:** Tối đa **3 lần retry**, tổng cộng 4 lần gọi nếu các lần trước thất bại và policy cho phép.

**Câu 3.** Tại sao cần `traverseCauses=true`?

**Trả lời:** Vì Spring listener có thể bọc lỗi nghiệp vụ trong `ListenerExecutionFailedException`; classifier cần nhìn nguyên nhân sâu hơn để phân loại đúng.

**Câu 4.** Payment API timeout nhưng có thể đã tính tiền, có nên tạo request mới với idempotency key mới không?

**Trả lời:** Không. Đối soát và nếu retry thì dùng cùng key theo contract để tránh double charge.

**Câu 5.** `AmqpRejectAndDontRequeueException` và `ImmediateRequeueAmqpException` khác nhau thế nào?

**Trả lời:** Một loại yêu cầu reject không requeue; loại còn lại yêu cầu requeue. Retry interceptor vẫn cần classifier riêng trước khi lỗi đi đến container.

**Câu 6.** Vì sao `RepublishMessageRecoverer` và `RejectAndDontRequeueRecoverer` không thể xem như nhau?

**Trả lời:** Một cơ chế **publish message lỗi mới** sang error exchange; một cơ chế yêu cầu broker **reject delivery gốc** để dùng DLX. Side effect, confirm và đường đi message khác nhau.

**Câu 7.** RabbitMQ 4.3+ dùng quorum queue, `basic.nack(requeue=true)` lặp liên tục có chắc kích hoạt delivery-limit không?

**Trả lời:** Không. Theo semantics 4.3+, NACK requeue không tăng `delivery-count`; cần giới hạn retry của ứng dụng hoặc dùng hành vi reject thích hợp theo version.

**Câu 8.** Vì sao consumer cần idempotency dù đã có publisher confirms và retry hữu hạn?

**Trả lời:** Vì producer có thể phát lại sau mất confirm và broker có thể redeliver sau ACK thất lạc; retry advice cũng có thể gọi lại service. Không có cơ chế nào trong ba thứ tự tạo exactly-once side effect.

## 20. Tài liệu tham khảo

- [Spring AMQP 3.2 — Resilience: Recovering from Errors and Broker Failures](https://docs.spring.io/spring-amqp/reference/3.2/amqp/resilience-recovering-from-errors-and-broker-failures.html): stateless/stateful retry, `RetryInterceptorBuilder`, `MessageRecoverer`, `RepublishMessageRecoverer` và cause-chain classification.
- [Spring AMQP — Exception Handling](https://docs.spring.io/spring-amqp/reference/amqp/exception-handling.html): `ConditionalRejectingErrorHandler`, fatal conversion/validation và reject/requeue.
- [Spring Retry — SimpleRetryPolicy](https://docs.spring.io/spring-retry/docs/current/apidocs/spring.retry/org/springframework/retry/policy/SimpleRetryPolicy.html): `maxAttempts`, retryable exception map, `traverseCauses`.
- [RabbitMQ — Consumer Acknowledgements and Publisher Confirms](https://www.rabbitmq.com/docs/confirms): ACK/NACK và requeue/redelivery loops.
- [RabbitMQ — Negative Acknowledgements](https://www.rabbitmq.com/docs/nack): `basic.reject`/`basic.nack`, gồm các khác biệt về poison-message accounting theo phiên bản.
- [RabbitMQ — Quorum Queues](https://www.rabbitmq.com/docs/quorum-queues): delivery limit, poison messages, `x-delivery-count` và cơ chế delayed retry theo phiên bản.
- [RabbitMQ — Dead Letter Exchanges](https://www.rabbitmq.com/docs/dlx): lý do dead-letter, DLX policy, an toàn dead-lettering và các giới hạn.
- [Spring AMQP — Listener Containers](https://docs.spring.io/spring-amqp/reference/amqp/receiving-messages/async-consumer.html): prefetch, ACK mode và listener container behavior.

**Ghi nhớ:** Trong **Spring AMQP**, trước khi retry phải phân loại **lỗi tạm thời**, **lỗi không thể phục hồi bằng việc thử lại cùng message**, và **kết quả side effect chưa rõ**. Dùng **Spring Retry với exception classifier, giới hạn attempts và backoff** cho lỗi transient ngắn; dùng **reject không requeue + DLX/DLQ** cho poison messages; dùng **reconciliation/idempotency key** cho outcome không chắc chắn. Khi lỗi kéo dài, cân nhắc delayed retry hoặc job bền vững thay vì requeue nóng. Cuối cùng, kết hợp **RabbitTemplate publisher confirms**, routing đúng exchange/queue/binding, `@RabbitListener` ACK, transaction, outbox/inbox và quan sát để xây hệ thống xử lý bất đồng bộ đáng tin cậy.
