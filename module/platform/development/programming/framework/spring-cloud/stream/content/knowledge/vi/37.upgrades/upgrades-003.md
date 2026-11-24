# Chuyển mô hình annotation cũ sang Supplier, Function và Consumer

## 1. Vì sao Spring Cloud Stream chuyển sang mô hình hàm?

Các phiên bản Spring Cloud Stream trước đây thường khai báo interface channel rồi gắn annotation `@EnableBinding`, `@Input`, `@Output`, `@StreamListener` và `@SendTo` lên lớp hoặc phương thức. Mô hình đó khiến code nghiệp vụ biết nhiều về channel và cấu trúc message transport.

Mô hình hiện đại dùng các functional bean của Java:

- `Supplier<T>`: tạo sự kiện để phát ra một output binding.
- `Function<I, O>`: nhận một input message, biến đổi và phát output.
- `Consumer<T>`: nhận sự kiện rồi thực hiện xử lý, không có output binding mặc định.

Spring Cloud Function khám phá các bean này; Spring Cloud Stream tạo binding kết nối chúng với Kafka, RabbitMQ hoặc Pulsar. Nhờ đó, logic nghiệp vụ trở thành hàm thuần hoặc hàm xử lý dễ kiểm thử, trong khi topic, group, serialization và retry được cấu hình ngoài code.

~~~mermaid
flowchart LR
    L[Legacy annotations] --> M[Migration]
    M --> S[Supplier output only]
    M --> F[Function input and output]
    M --> C[Consumer input only]
    S --> B[Spring Cloud Stream bindings]
    F --> B
    C --> B
    B --> K[(Kafka / RabbitMQ / Pulsar)]
~~~

Đây không đơn thuần là đổi annotation. Một lần nâng cấp đúng phải giữ được hợp đồng event, group/subscription, thứ tự, xử lý lỗi và delivery semantics của hệ thống đang chạy.

## 2. Đối chiếu annotation cũ với cấu trúc mới

| Trong ứng dụng cũ | Mục đích | Cách tương ứng trong mô hình hàm |
|---|---|---|
| `@EnableBinding(Sink.class)` | Đăng ký input channel | Bean `Consumer<T>` hoặc `Function<T,R>` và input binding |
| `@EnableBinding(Source.class)` | Đăng ký output channel | Bean `Supplier<T>` hoặc `StreamBridge` |
| `@EnableBinding(Processor.class)` | Có cả input và output | Bean `Function<I,O>` |
| `@StreamListener(Sink.INPUT)` | Xử lý message đầu vào | Bean `Consumer<T>` |
| `@StreamListener` kèm `@SendTo` | Nhận và trả về message đầu ra | Bean `Function<I,O>` |
| `@Input` / `@Output` interface methods | Khai báo channel có tên | Binding được suy ra từ tên functional bean hoặc alias |
| Inject `MessageChannel` rồi `send` | Phát message chủ động | `StreamBridge.send` qua output binding |
| `@InboundChannelAdapter` + poller | Phát sự kiện theo lịch polling | `Supplier<T>` và poller được cấu hình |
| Điều kiện trên `@StreamListener` | Định tuyến có điều kiện | Router function, filter hoặc nhiều function thiết kế rõ ràng |

Không phải mọi annotation của Spring Integration đều bị loại bỏ. Bài này bàn về **mô hình binding và listener kiểu cũ của Spring Cloud Stream**, không khuyến nghị xóa các integration adapter còn cần thiết ở thành phần khác.

## 3. Xác định phạm vi và lập danh mục trước khi sửa code

Trước khi chuyển đổi, liệt kê trong ứng dụng đang chạy:

1. Các channel interface gắn `@Input`, `@Output` và `@EnableBinding`.
2. Các method `@StreamListener`: input, output, payload type và header.
3. Nơi trực tiếp gọi `MessageChannel.send`.
4. Cấu hình `destination`, `group`, `contentType`, partition và concurrency.
5. Các binder Kafka/Rabbit/Pulsar, topic/queue, retry/DLQ, error channel và acknowledgement.
6. Supplier/poller, lịch phát event và điều kiện kích hoạt.
7. Dạng message có `Message<T>`, header tùy biến hoặc native serialization.
8. Điểm xử lý bất đồng bộ, giao dịch, idempotency và các side effect.

Tạo bảng đối chiếu mỗi luồng trước/sau; không đổi tên topic hoặc group vô tình khi thay tên Java bean.

Ví dụ:

| Thuộc tính | Legacy | Sau nâng cấp cần giữ |
|---|---|---|
| Input channel | `input` | `acceptOrder-in-0` |
| Input destination | `orders.events` | `orders.events` |
| Consumer group | `order-processor` | `order-processor` |
| Output channel | `output` | `acceptOrder-out-0` |
| Output destination | `orders.accepted` | `orders.accepted` |
| Input payload format | JSON schema v2 | Tương thích JSON schema v2 |
| Failure semantics | Retry, DLT, ack theo broker | Chứng minh tương đương bằng test |

## 4. Ví dụ trước chuyển đổi: Processor và StreamListener

Mô hình cũ có thể trông như sau:

~~~java
import org.springframework.cloud.stream.annotation.EnableBinding;
import org.springframework.cloud.stream.annotation.StreamListener;
import org.springframework.cloud.stream.messaging.Processor;
import org.springframework.messaging.handler.annotation.SendTo;

record OrderCreated(String orderId, long totalCents) {}
record OrderAccepted(String orderId, String status) {}

@EnableBinding(Processor.class)
class LegacyOrderProcessor {

    @StreamListener(Processor.INPUT)
    @SendTo(Processor.OUTPUT)
    public OrderAccepted acceptOrder(OrderCreated event) {
        return new OrderAccepted(event.orderId(), "ACCEPTED");
    }
}
~~~

Các tên channel `input` và `output` xuất phát từ interface `Processor`. Cấu hình cũ:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        input:
          destination: orders.events
          group: order-processor
          contentType: application/json
        output:
          destination: orders.accepted
          contentType: application/json
~~~

Đoạn này là **mẫu legacy để nhận diện trong source cũ**, không phải lựa chọn cho ứng dụng Spring Cloud Stream mới. Khi nâng cấp phiên bản framework, loại bỏ import/API legacy theo migration guide của release train thực tế.

## 5. Sau chuyển đổi: Function nhận và trả kết quả

Tách logic nghiệp vụ thành một bean `Function<OrderCreated, OrderAccepted>`:

~~~java
import java.util.function.Function;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OrderFunctions {

    @Bean
    Function<OrderCreated, OrderAccepted> acceptOrder() {
        return event -> new OrderAccepted(event.orderId(), "ACCEPTED");
    }
}
~~~

Spring Cloud Stream suy ra:

- Input binding: `acceptOrder-in-0`.
- Output binding: `acceptOrder-out-0`.

Khai báo rõ các đích cũ và group cũ:

~~~yaml
spring:
  cloud:
    function:
      definition: acceptOrder
    stream:
      bindings:
        acceptOrder-in-0:
          destination: orders.events
          group: order-processor
          content-type: application/json
        acceptOrder-out-0:
          destination: orders.accepted
          content-type: application/json
~~~

Giữ nguyên `orders.events` và `order-processor` để consumer mới tham gia cùng logical workload thay vì vô tình tạo một subscription/group mới. **Không chạy phiên bản cũ và mới đồng thời trong cùng group nếu chưa tính đến việc chúng chia nhau message và thay đổi xử lý.**

## 6. Từ StreamListener không trả giá trị sang Consumer

Một phương thức legacy chỉ xử lý side effect:

~~~java
import org.springframework.cloud.stream.annotation.EnableBinding;
import org.springframework.cloud.stream.annotation.StreamListener;
import org.springframework.cloud.stream.messaging.Sink;

@EnableBinding(Sink.class)
class LegacyPaymentListener {

    @StreamListener(Sink.INPUT)
    public void applyPayment(PaymentReceived payment) {
        paymentService.apply(payment);
    }
}
~~~

Phiên bản functional:

~~~java
import java.util.function.Consumer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class PaymentFunctions {

    @Bean
    Consumer<PaymentReceived> applyPayment(PaymentService paymentService) {
        return payment -> paymentService.apply(payment);
    }
}
~~~

~~~yaml
spring:
  cloud:
    function:
      definition: applyPayment
    stream:
      bindings:
        applyPayment-in-0:
          destination: payments.received
          group: payment-ledger
~~~

`Consumer<T>` không tạo output binding tự động. Nếu code cũ vừa ghi database vừa gửi event, cần cân nhắc thay thành `Function` trả output, hoặc dùng `StreamBridge` có kiểm soát; không bỏ mất bước publish khi chuyển sang Consumer.

## 7. Từ Source/InboundChannelAdapter sang Supplier

Một source cũ phát sự kiện theo poller:

~~~java
import org.springframework.cloud.stream.annotation.EnableBinding;
import org.springframework.cloud.stream.messaging.Source;
import org.springframework.integration.annotation.InboundChannelAdapter;
import org.springframework.integration.annotation.Poller;

@EnableBinding(Source.class)
class LegacyHeartbeatSource {

    @InboundChannelAdapter(
        value = Source.OUTPUT,
        poller = @Poller(fixedDelay = "5000")
    )
    public Heartbeat nextHeartbeat() {
        return new Heartbeat("service-a", System.currentTimeMillis());
    }
}
~~~

Chuyển sang bean Supplier:

~~~java
import java.util.function.Supplier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

record Heartbeat(String source, long timestampMs) {}

@Configuration
class HeartbeatFunctions {

    @Bean
    Supplier<Heartbeat> heartbeat() {
        return () -> new Heartbeat("service-a", System.currentTimeMillis());
    }
}
~~~

Supplier không tự tiêu thụ message từ broker; framework gọi Supplier qua cơ chế polling phù hợp. Cấu hình output destination:

~~~yaml
spring:
  cloud:
    function:
      definition: heartbeat
    stream:
      bindings:
        heartbeat-out-0:
          destination: service.heartbeat
  integration:
    poller:
      fixed-delay: 5000
~~~

Thuộc tính poller và cách gọi Supplier cần đối chiếu phiên bản Spring Cloud Stream/Spring Integration. Tránh dùng Supplier để tự phát lại một business event mỗi lần poll: nếu event chỉ được lấy bằng cách đọc bản ghi “chưa gửi”, cần có trạng thái phát, transaction/outbox hoặc cơ chế xác nhận để chống duplicate.

## 8. Từ inject Output MessageChannel sang StreamBridge

Code cũ có thể inject channel output rồi gọi `send` trong một REST endpoint hoặc job:

~~~java
@EnableBinding(Source.class)
class LegacyOrderPublisher {
    private final MessageChannel output;

    LegacyOrderPublisher(@Qualifier(Source.OUTPUT) MessageChannel output) {
        this.output = output;
    }

    void publish(OrderCreated event) {
        output.send(MessageBuilder.withPayload(event).build());
    }
}
~~~

Với mô hình mới, dùng `StreamBridge` khi phát message **không xuất phát từ một input binding**:

~~~java
import org.springframework.cloud.stream.function.StreamBridge;
import org.springframework.stereotype.Service;

@Service
class OrderPublisher {

    private final StreamBridge streamBridge;

    OrderPublisher(StreamBridge streamBridge) {
        this.streamBridge = streamBridge;
    }

    void publish(OrderCreated event) {
        boolean accepted = streamBridge.send("orderEvents", event);
        if (!accepted) {
            throw new IllegalStateException("Output binding rejected event");
        }
    }
}
~~~

~~~yaml
spring:
  cloud:
    stream:
      output-bindings: orderEvents
      bindings:
        orderEvents:
          destination: orders.events
          content-type: application/json
~~~

`StreamBridge.send` xác nhận việc gửi qua API/binding theo semantics binder, **không chứng minh consumer đích đã xử lý nghiệp vụ**. Nếu yêu cầu publish chắc chắn sau database commit, thiết kế outbox hoặc cơ chế transaction rõ ràng. Không thay mọi Function bằng StreamBridge vì cách đó có thể làm mất lợi ích composition, output binding và quản lý lỗi chuẩn.

## 9. Quy tắc tên binding trong functional model

Với bean tên `processOrder`, tên binding mặc định được tạo theo mẫu:

~~~text
<functionName>-in-<inputIndex>
<functionName>-out-<outputIndex>
~~~

| Functional bean | Input binding | Output binding |
|---|---|---|
| `Consumer<Order> processOrder` | `processOrder-in-0` | Không có mặc định |
| `Function<Order,Result> acceptOrder` | `acceptOrder-in-0` | `acceptOrder-out-0` |
| `Supplier<Heartbeat> heartbeat` | Không có mặc định | `heartbeat-out-0` |

Tên binding dùng trong `spring.cloud.stream.bindings`; còn `destination` là tên topic/exchange/topic logic thực tế. Thay tên bean từ `processOrder` sang `handleOrders` mà không đổi YAML sẽ khiến cấu hình cũ không còn áp dụng lên binding mới.

Đối với function composition và nhiều input/output, tên binding có thể phức tạp hơn. Xác minh tên được runtime tạo hoặc dùng alias rõ ràng thay vì đoán.

## 10. Dùng binding alias khi muốn giữ tên cấu hình

Ứng dụng lớn có thể đã chứa nhiều property gắn với tên `input` và `output`. Spring Cloud Stream hỗ trợ alias binding:

~~~yaml
spring:
  cloud:
    function:
      definition: acceptOrder
    stream:
      function:
        bindings:
          acceptOrder-in-0: input
          acceptOrder-out-0: output
      bindings:
        input:
          destination: orders.events
          group: order-processor
        output:
          destination: orders.accepted
~~~

Alias giúp việc đổi sang Function không bắt buộc đổi toàn bộ key cấu hình trong một bước. Tuy nhiên, đây là một lớp ánh xạ bổ sung cần tài liệu hóa. Với dự án mới hoặc khi có thể chỉnh cấu hình đồng bộ, sử dụng tên binding theo functional bean thường dễ hiểu hơn.

Một alias không thay đổi destination thật, không đồng bộ dữ liệu giữa hai broker và không thay thế group/subscription.

## 11. Kích hoạt nhiều function độc lập

Ứng dụng có thể khai báo nhiều bean:

~~~java
@Configuration
class MultipleFunctions {

    @Bean
    Function<String, String> normalize() {
        return String::trim;
    }

    @Bean
    Consumer<String> audit(AuditService auditService) {
        return auditService::record;
    }
}
~~~

Nếu muốn tạo hai đường xử lý độc lập, sử dụng dấu chấm phẩy:

~~~yaml
spring:
  cloud:
    function:
      definition: normalize;audit
    stream:
      bindings:
        normalize-in-0:
          destination: names.raw
          group: normalizer
        normalize-out-0:
          destination: names.normalized
        audit-in-0:
          destination: events.audit
          group: audit-service
~~~

Dấu `;` khai báo nhiều function độc lập; dấu `|` dùng để compose các function nối tiếp. Không nhầm hai cách: `normalize;audit` không có nghĩa output normalize tự chảy vào audit.

Khi có nhiều bean Function/Supplier/Consumer và chưa chọn rõ, cấu hình `spring.cloud.function.definition` để tránh ambiguity.

## 12. Composition không giống các channel nối bằng tay

Legacy có thể dùng hai ứng dụng hoặc hai channel:

~~~text
orders.raw -> normalize -> orders.normalized -> validate -> orders.validated
~~~

Nếu hai bước chỉ là xử lý dữ liệu trong cùng ứng dụng và không cần ranh giới broker ở giữa, có thể dùng function composition:

~~~java
@Bean
Function<String, String> normalize() {
    return String::trim;
}

@Bean
Function<String, String> validate() {
    return text -> {
        if (text.isBlank()) {
            throw new IllegalArgumentException("Blank value");
        }
        return text;
    };
}
~~~

~~~yaml
spring:
  cloud:
    function:
      definition: normalize|validate
~~~

Composition kết hợp logic trong một pipeline, **không tạo một destination trung gian** như broker flow cũ. Vì vậy có thể thay đổi retry boundary, khả năng replay riêng và quan sát của từng bước. Nếu topic trung gian là hợp đồng của các ứng dụng khác hoặc là ranh giới lưu trữ bền vững, giữ nó thành một output/input thật thay vì gộp hai function.

## 13. Bảo toàn content type và chuyển đổi payload

Trong mô hình annotation cũ, `@StreamListener` có thể nhận POJO vì framework chuyển bytes thành Java object dựa trên content type. Functional bean cũng sử dụng cơ chế message conversion, nhưng phiên bản framework, codec và cấu hình có thể thay đổi.

Ví dụ payload:

~~~json
{
  "orderId": "ord-42",
  "totalCents": 150000
}
~~~

Bean:

~~~java
record OrderCreated(String orderId, long totalCents) {}

@Bean
Function<OrderCreated, OrderAccepted> acceptOrder() {
    return order -> new OrderAccepted(order.orderId(), "ACCEPTED");
}
~~~

Binding:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        acceptOrder-in-0:
          destination: orders.events
          group: order-processor
          content-type: application/json
        acceptOrder-out-0:
          destination: orders.accepted
          content-type: application/json
~~~

Kiểm thử cả schema version cũ và mới, missing fields, enum không nhận diện, timestamp, số lớn và payload lỗi. Nếu sử dụng `useNativeDecoding`/`useNativeEncoding` của binder, serializer/deserializer do broker client đảm nhiệm, không thể suy ra rằng JSON conversion mặc định vẫn áp dụng.

## 14. Bảo toàn headers và Message wrapper

Legacy có thể đọc `Message<T>` để lấy correlation ID, tenant ID hoặc trace headers. Có thể giữ kiểu đó trong function mới:

~~~java
import java.util.function.Function;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

@Bean
Function<Message<OrderCreated>, Message<OrderAccepted>> acceptOrder() {
    return incoming -> {
        OrderCreated order = incoming.getPayload();
        OrderAccepted accepted = new OrderAccepted(
            order.orderId(), "ACCEPTED"
        );
        Object correlationId = incoming.getHeaders().get("correlationId");
        return MessageBuilder.withPayload(accepted)
            .setHeader("correlationId", correlationId)
            .build();
    };
}
~~~

Không copy mù quáng mọi broker-specific header từ input sang output: một số header gắn với consumer offset, partition nhận, acknowledgement hoặc internal transport, không thích hợp để gửi tiếp. Chọn các business/trace headers cần giữ và xác minh chúng được map qua binder đích.

Nếu ứng dụng nối Kafka sang RabbitMQ hoặc Pulsar, kiểm tra sự tương thích của header mapping và kiểu dữ liệu header, đặc biệt với binary values và giới hạn kích thước.

## 15. Giữ nguyên consumer group khi nâng cấp

Trước chuyển đổi:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        input:
          destination: orders.events
          group: order-processor
~~~

Sau chuyển đổi:

~~~yaml
spring:
  cloud:
    function:
      definition: acceptOrder
    stream:
      bindings:
        acceptOrder-in-0:
          destination: orders.events
          group: order-processor
~~~

Việc đổi tên binding không buộc phải đổi topic hoặc consumer group. Nếu đổi group thành `order-processor-v2`, Kafka sẽ dùng nhóm offset khác, Rabbit binder có thể tạo queue khác và Pulsar có thể dùng subscription khác; ứng dụng dễ đọc lại nhiều dữ liệu hoặc bỏ qua backlog tùy chính sách start offset và provisioning.

Với rollout hai version cùng group, message được chia giữa cả hai phiên bản trong thời gian trùng lặp. Đây là chiến lược rolling upgrade có rủi ro nếu hai version có semantics khác nhau. Cần kiểm tra backward compatibility và idempotency trước khi cho chạy song song.

## 16. Partition, routing và thứ tự phải được kiểm tra lại

Nếu source cũ dùng `partitionKeyExpression`, producer key headers hoặc cấu hình partition count, cần xác nhận functional binding mới phát Kafka record key/partition tương ứng.

Những sai lệch thường gặp:

- Trường `customerId` có trong JSON nhưng không phải message key.
- Đổi cách serialize key khiến hash partition thay đổi.
- Thay partition count khiến key được đưa tới partition khác trong tương lai.
- Tăng concurrency làm thứ tự **hoàn tất xử lý** khác thứ tự nhận.
- Chuyển Rabbit consumer hoặc Pulsar subscription mode làm thay đổi cách chia tải.

Với Kafka Streams KStream/KTable, migration logic cần dùng chữ ký hàm Kafka Streams chuyên biệt, không thay các topology stateful bằng `Function<POJO, POJO>` rồi kỳ vọng tự có state store và changelog.

## 17. Retry và error handling không nên được chuyển một cách máy móc

Một phương thức `@StreamListener` có thể có retry annotation, binder retry, error channel hoặc DLQ. Khi chuyển sang Function/Consumer, cần xác minh **lỗi được ném ở đâu** và binder nào nhận được lỗi đó.

Ví dụ Consumer:

~~~java
@Bean
Consumer<OrderCreated> processOrder(OrderService service) {
    return event -> {
        service.handle(event); // throw on a real failure
    };
}
~~~

Nếu handler bắt exception rồi chỉ log mà không ném lại, binder thường nhìn thấy xử lý đã hoàn tất; message có thể bị ack/commit tùy mode dù nghiệp vụ thất bại. Nếu muốn retry, đừng nuốt lỗi mà không chủ đích.

Một cấu hình retry chung:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.events
          group: order-processor
          consumer:
            maxAttempts: 3
            backOffInitialInterval: 1000
            backOffMultiplier: 2.0
~~~

Phải kiểm tra error handling theo binder và mode: Kafka, RabbitMQ, Pulsar, transactional processing, native decoding và reactive function không nhất thiết dùng đúng cùng cơ chế retry. Chỉ chấp nhận migration khi đã thử lỗi transient, lỗi không retry và hành vi DLQ.

## 18. Kafka binder: DLQ và offset không được đổi ngoài ý muốn

Khi giữ Kafka binder, có thể cần cấu hình DLQ riêng cho input binding mới:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.events
          group: order-processor
          consumer:
            maxAttempts: 3
      kafka:
        bindings:
          processOrder-in-0:
            consumer:
              enableDlq: true
              dlqName: orders.events.dlt
~~~

Vì tên binding đã đổi từ `input` sang `processOrder-in-0`, tất cả property dưới `spring.cloud.stream.kafka.bindings.input` của ứng dụng cũ cũng cần được remap. Nếu bỏ sót `enableDlq`, `startOffset`, `ackMode` hoặc consumer properties khác, chức năng có thể chạy nhưng recovery và lỗi khác trước.

Không gộp trạng thái Kafka offset với side effect ngoài Kafka thành “exactly-once” nếu không có cơ chế transaction hoặc idempotency phù hợp. Một crash sau DB commit nhưng trước offset commit vẫn có thể gây redelivery.

## 19. RabbitMQ binder: queue, DLQ và acknowledgement

Với RabbitMQ, `destination` thường ánh xạ thành exchange; `group` góp phần xác định queue của consumer. Khi nâng cấp, giữ đúng destination/group và rà lại cấu hình Rabbit binder riêng cho tên binding mới.

Ví dụ:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.events
          group: order-processor
      rabbit:
        bindings:
          processOrder-in-0:
            consumer:
              autoBindDlq: true
              prefetch: 20
~~~

Giữ queue/consumer naming, durability, routing keys, prefetch và dead-letter semantics. Nếu ứng dụng production đã pre-provision tài nguyên bằng tài khoản quản trị, kiểm tra lại runtime permission và các tùy chọn auto-declare thay vì cấp admin credential cho binder.

Một message bị consumer nhận rồi process chết trước acknowledgement có thể được RabbitMQ redeliver. Bản migration vẫn cần xử lý lặp an toàn.

## 20. Pulsar binder: subscription và ack semantics

Đối với Pulsar, giữ subscription/group logic và loại subscription tương ứng. Các kiểu `Exclusive`, `Failover`, `Shared`, `Key_Shared` có hành vi chia tải, failover và thứ tự khác nhau.

Các điểm cần kiểm tra khi chuyển:

- Binding mới có thực sự nối tới topic cũ trong đúng tenant/namespace không?
- Subscription name có còn bền vững qua restart không?
- Subscription type có bị đổi bởi cấu hình mới không?
- Consumer ack timeout, negative ack, redelivery và DLQ có khác không?
- Producer key/batching có còn đáp ứng key affinity khi dùng Key_Shared không?

Không chuyển sang Shared chỉ để tăng throughput nếu luồng cần thứ tự theo key. Việc chuyển mô hình annotation sang functional bean không yêu cầu thay subscription type; hãy xem chúng như hai quyết định khác nhau.

## 21. Sự khác nhau giữa Function đồng bộ và reactive

Function đồng bộ dùng:

~~~java
@Bean
Function<OrderCreated, OrderAccepted> acceptOrder() {
    return order -> transform(order);
}
~~~

Một ứng dụng reactive có thể khai báo:

~~~java
import reactor.core.publisher.Flux;
import java.util.function.Function;

@Bean
Function<Flux<OrderCreated>, Flux<OrderAccepted>> acceptOrders() {
    return orders -> orders.map(order ->
        new OrderAccepted(order.orderId(), "ACCEPTED")
    );
}
~~~

Không đổi từ function đồng bộ sang Flux chỉ vì API mới cho phép. Reactive function chạy theo lifecycle của publisher và cơ chế subscription của framework; backpressure, lỗi phát sinh trong stream và tính nhất quán xử lý có thể khác xử lý record từng cái.

Với `Consumer<Flux<T>>`, cần rất thận trọng về việc ai subscribe và ai chịu trách nhiệm xử lý lỗi; không mặc định điều đó tương đương `Consumer<T>`. Đối với workflow có stateful join/window theo Kafka, dùng Kafka Streams functional binding chuyên dụng.

## 22. Conditional StreamListener cần thiết kế lại

Một số code cũ dùng `@StreamListener` với `condition` để nhiều handler nhận record theo header/type. Khi bỏ annotation, không tự động có nhiều Consumer cùng nhận rồi lọc message theo đúng luật cũ.

Các lựa chọn thay thế:

1. Một Consumer nhận mọi message và dispatch tới service theo event type, có nhánh unknown rõ ràng.
2. Một Function router của Spring Cloud Function với routing expression/header được cấu hình và kiểm thử tương ứng.
3. Tách input destination/topic theo loại sự kiện nếu ranh giới broker cần độc lập.

Ví dụ dispatch đơn giản, tránh suy đoán router configuration:

~~~java
@Bean
Consumer<Message<String>> dispatch(
        OrderEventHandler orderHandler,
        AuditEventHandler auditHandler) {
    return message -> {
        String type = (String) message.getHeaders().get("eventType");
        if ("ORDER".equals(type)) {
            orderHandler.handle(message.getPayload());
        } else if ("AUDIT".equals(type)) {
            auditHandler.handle(message.getPayload());
        } else {
            throw new IllegalArgumentException("Unsupported eventType: " + type);
        }
    };
}
~~~

Định nghĩa hành vi khi header bị thiếu hoặc type không hỗ trợ: reject, DLQ hay ignore. Không để một message lỗi bị xử lý không giới hạn trong vòng retry.

## 23. Nhiều input/output: không suy diễn một-một

Code annotation cũ có thể nhận hai input channel trong cùng handler hoặc gửi nhiều output. Mô hình functional hỗ trợ một số chữ ký nhiều input/output, nhưng không phải mọi dạng method cũ đều map trực tiếp thành một `BiFunction<POJO,POJO,R>`.

Với hai luồng reactive, có thể dùng một `BiFunction<Flux<A>, Flux<B>, Flux<C>>` được hỗ trợ bởi functional model:

~~~java
import java.util.function.BiFunction;
import reactor.core.publisher.Flux;

record CustomerProfile(String customerId, String tier) {}
record EnrichedOrder(String orderId, String tier) {}

@Bean
BiFunction<Flux<OrderCreated>, Flux<CustomerProfile>, Flux<EnrichedOrder>>
enrich() {
    return (orders, customers) -> orders.zipWith(
        customers,
        (order, customer) -> new EnrichedOrder(
            order.orderId(), customer.tier()
        )
    );
}
~~~

`zipWith` ghép phần tử theo **thứ tự xuất hiện**, không phải join theo customerId hay event time. Nếu dữ liệu là hai topic đến độc lập, cần cơ chế state/correlation hoặc Kafka Streams join phù hợp. Với nhiều output, nghiên cứu tuple output hoặc StreamBridge theo semantics mong muốn; viết integration test bảo đảm mỗi output được publish đúng destination.

## 24. Kafka Streams binder phải giữ topology và state store

Nếu ứng dụng cũ dùng Kafka Streams binder với KStream/KTable thay vì message channel annotation, không được áp dụng máy móc công thức “StreamListener → Function POJO”. Kafka Streams có topology, partitions, state stores và changelog riêng.

Functional Kafka Streams bean thường có chữ ký:

~~~java
import java.util.function.Function;
import org.apache.kafka.streams.kstream.KStream;
import org.springframework.context.annotation.Bean;

@Bean
Function<KStream<String, OrderCreated>, KStream<String, OrderAccepted>>
acceptOrders() {
    return stream -> stream.mapValues(order ->
        new OrderAccepted(order.orderId(), "ACCEPTED")
    );
}
~~~

Hệ thống stateful cần so sánh chính xác application ID, input/output topics, Serdes, partitioning, state store names và topic changelog. Đổi application ID có thể dẫn đến việc Kafka Streams đọc lại dữ liệu và tạo state mới. Nếu muốn đổi application ID hoặc topology, cần chiến lược chuyển state/offset riêng.

## 25. Giữ cấu hình binder và nhiều cluster nhất quán

Một ứng dụng có nhiều Kafka cluster hoặc RabbitMQ virtual host thường gán từng binding vào binder có tên. Khi đổi binding name, cũng phải chuyển thuộc tính `binder`:

~~~yaml
spring:
  cloud:
    function:
      definition: relayOrder
    stream:
      bindings:
        relayOrder-in-0:
          destination: orders.events
          group: order-relay
          binder: kafka-primary
        relayOrder-out-0:
          destination: audit.orders
          binder: kafka-audit
~~~

Giữ nguyên binder selection, endpoint, credentials, TLS, ACL và serialization của từng destination. Không có transaction phân tán mặc định giữa hai Kafka cluster hoặc Kafka và RabbitMQ; pipeline cần idempotency/compensation hoặc outbox tùy nghiệp vụ.

## 26. Kiểm thử logic function trước khi kiểm thử broker

Việc đưa logic về Java Function làm unit test đơn giản:

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import org.junit.jupiter.api.Test;

class OrderFunctionsTest {

    @Test
    void transformsOrderWithoutBroker() {
        OrderFunctions configuration = new OrderFunctions();
        OrderAccepted result = configuration.acceptOrder()
            .apply(new OrderCreated("ORD-101", 49_000));

        assertThat(result.orderId()).isEqualTo("ORD-101");
        assertThat(result.status()).isEqualTo("ACCEPTED");
    }
}
~~~

Unit test chứng minh business transformation nhưng không xác nhận content-type conversion, routing hoặc acknowledgement. Vì vậy cần một lớp test thứ hai bằng Spring Cloud Stream Test Binder và lớp integration test với broker thật.

## 27. Test Binder: kiểm tra destination trước/sau migration

Với test binder, gửi input và nhận output bằng tên **destination hiệu lực** đã cấu hình:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.stream.binder.test.InputDestination;
import org.springframework.cloud.stream.binder.test.OutputDestination;
import org.springframework.cloud.stream.binder.test.TestChannelBinderConfiguration;
import org.springframework.context.annotation.Import;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.util.MimeTypeUtils;

@SpringBootTest(properties = {
    "spring.cloud.function.definition=acceptOrder",
    "spring.cloud.stream.bindings.acceptOrder-in-0.destination=orders.events",
    "spring.cloud.stream.bindings.acceptOrder-out-0.destination=orders.accepted"
})
@Import(TestChannelBinderConfiguration.class)
class OrderBindingTest {

    @Autowired InputDestination input;
    @Autowired OutputDestination output;

    @Test
    void keepsTheDestinationContract() {
        byte[] json = "{\"orderId\":\"ORD-101\",\"totalCents\":49000}"
            .getBytes(StandardCharsets.UTF_8);

        input.send(MessageBuilder.withPayload(json)
            .setHeader(MessageHeaders.CONTENT_TYPE, MimeTypeUtils.APPLICATION_JSON)
            .build(), "orders.events");

        Message<byte[]> result = output.receive(2_000, "orders.accepted");
        assertThat(result).isNotNull();
        assertThat(new String(result.getPayload(), StandardCharsets.UTF_8))
            .contains("ORD-101", "ACCEPTED");
    }
}
~~~

Test này kiểm tra function binding và conversion trong application context. Nó không thay thế test Kafka partition/offset, Rabbit queue/ack hoặc Pulsar subscription thật. Nếu nhiều function cùng chạy, luôn chỉ định destination khi gửi/nhận để không đọc nhầm channel.

## 28. Integration test và đối soát hành vi quan trọng

Test migration với broker thật hoặc môi trường container tương thích cần bao gồm:

| Hạng mục | Kịch bản | Điều cần xác nhận |
|---|---|---|
| Happy path | Event hợp lệ đi qua input/output | Payload, headers và destination giống hợp đồng cũ |
| Consumer group | Restart nhiều instance | Vẫn dùng group/subscription mong muốn |
| Retained backlog | Dừng consumer rồi phát message | Không mất event vì đổi group/tên queue |
| Payload cũ | Gửi schema version được hỗ trợ | Conversion tương thích |
| Poison message | Gửi JSON không hợp lệ | Retry/DLQ hoặc reject đúng chính sách |
| Transient error | Downstream trả timeout/503 | Bounded retry, backoff và recovery |
| Crash window | Kill sau side effect, trước ack | Duplicate không làm hỏng nghiệp vụ |
| Header routing | Gửi correlationId/eventType | Truyền và xử lý header chính xác |
| Partition | Cùng key, nhiều message | Thứ tự theo key/partition đúng yêu cầu |
| Multi-binder | Input/output ở broker khác nhau | Đúng binder, ACL, topic/exchange |

Đo consumer lag, retry count, DLQ size, duplicate outcome, throughput và p95/p99 trước và sau migration. Một bài test chỉ assert output của một message không đủ để chứng minh nâng cấp an toàn.

## 29. Lộ trình chuyển đổi từng bước

Quy trình đề xuất:

1. **Kiểm kê** tất cả annotation legacy, channel interface, bean name, binding và binder-specific properties.
2. **Đóng băng hợp đồng** topic/queue, group, schema, key, headers, retry/DLQ và delivery semantics.
3. **Tách logic** ra service hoặc hàm Java không phụ thuộc Spring Cloud Stream annotation.
4. **Chọn kiểu hàm**: Supplier cho nguồn phát, Function cho transform, Consumer cho sink, StreamBridge cho phát chủ động.
5. **Đặt tên bean** ổn định và cấu hình `spring.cloud.function.definition` rõ ràng.
6. **Remap binding** từ `input`/`output` sang tên functional, hoặc dùng alias có kiểm soát.
7. **Chuyển binder properties** cho Kafka/Rabbit/Pulsar sang tên binding mới.
8. **Chạy unit và Test Binder tests** để chứng minh logic và đường đi message.
9. **Chạy integration tests** với broker, queue, partition, retry, DLQ và replay.
10. **Triển khai canary/rolling phù hợp** sau khi kiểm soát vấn đề offset và hai phiên bản cùng group.
11. **Quan sát** lag, throughput, duplicate, lỗi conversion và backlog ở đích.
12. **Gỡ bỏ legacy API/dependency** chỉ sau khi không còn điểm gọi cần chúng và có rollback plan.

Nên commit phần remapping cấu hình cùng thay đổi code tương ứng; tránh deploy code mới nhưng YAML cũ khiến ứng dụng tạo binding tới destination ngoài dự kiến.

## 30. Canary, rollback và tránh duplicate khi hai phiên bản cùng chạy

Với Kafka, hai consumer cùng group chia partition; chúng không đều nhận cùng message trong hoạt động bình thường. Nếu chạy legacy và functional cùng group, các partition sẽ được phân phối giữa hai phiên bản. Khi semantics khác nhau, kết quả có thể không nhất quán giữa partition.

Nếu dùng group mới cho canary, canary có thể đọc luồng dữ liệu độc lập và tạo **side effect trùng** nếu cùng ghi vào hệ thống production. Một hướng an toàn là shadow mode: canary đọc message nhưng chỉ ghi metrics hoặc output cô lập, không thực hiện side effect quan trọng.

Kế hoạch rollback cần làm rõ:

- Có giữ nguyên group/offset khi quay lại không?
- Có schema mới nào version cũ không đọc được không?
- Có message đã được xử lý theo logic mới không thể xử lý lại theo logic cũ không?
- Có cần dừng producer hoặc chuyển traffic trong rollback không?
- Có DLT/retry message nào chưa được xử lý cần đối soát không?

Rollback không đơn giản là đưa lại image cũ nếu hợp đồng message, state store hoặc schema đã thay đổi.

## 31. Các lỗi migration thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách sửa |
|---|---|---|
| Function bean tồn tại nhưng không bind | `spring.cloud.function.definition` chưa chọn hàm | Khai báo definition và kiểm tra log khởi động |
| Không nhận message | Dùng `input` cũ nhưng binding mới là `acceptOrder-in-0` | Remap hoặc dùng binding alias |
| Nhận lại lịch sử event | Vô tình đổi group hoặc subscription | Giữ group cũ; đánh giá offset policy |
| Output đi topic khác | Destination output chưa remap | Cấu hình `acceptOrder-out-0.destination` |
| Retry/DLQ không hoạt động như trước | Binder property còn gắn với tên binding cũ | Chuyển toàn bộ Kafka/Rabbit/Pulsar binding config |
| Consumer không phát output | Đổi nhầm Function thành Consumer | Dùng Function hoặc StreamBridge đúng semantics |
| Supplier gửi trùng không kiểm soát | Poller gọi lại mỗi chu kỳ và không có trạng thái | Thiết kế event generation/outbox, kiểm soát lịch phát |
| Message parse lỗi | Content type, Serde hoặc native decoding thay đổi | So sánh payload/headers/codec |
| Header biến mất | Chỉ return POJO trong khi logic cần correlationId | Dùng `Message<T>`, giữ header cần thiết |
| Nhiều listener không còn routing đúng | Conditional StreamListener không map tự động | Router/dispatch rõ ràng và test |
| State Kafka Streams đọc lại toàn bộ | Đổi application ID hoặc state store semantics | Migration topology/state có kế hoạch |
| Lỗi bị nuốt, message vẫn ack | Handler bắt exception nhưng không ném lại | Phân loại lỗi và khớp error handling |

## 32. Checklist hoàn tất nâng cấp

- [ ] Không còn sử dụng legacy `@EnableBinding`, `@Input`, `@Output`, `@StreamListener` ở luồng đã chuyển.
- [ ] Các bean Supplier/Function/Consumer có tên ổn định và được chọn trong definition.
- [ ] Tất cả input/output binding, alias và destination được ghi rõ.
- [ ] Consumer group/subscription và tính bền vững qua restart được giữ hoặc thay đổi có chủ đích.
- [ ] Key, partitioning, headers, content-type và schema tương thích.
- [ ] Supplier poller có nhịp phát chính xác và không sinh duplicate ngoài ý muốn.
- [ ] StreamBridge được dùng đúng nơi cần phát message chủ động.
- [ ] Kafka/Rabbit/Pulsar binder-specific properties đã chuyển sang binding name mới.
- [ ] Retry, acknowledgement, DLT/DLQ và poison message đã được test.
- [ ] Có idempotency cho crash/rebalance/redelivery.
- [ ] Kafka Streams topology/state/application ID được bảo toàn nếu áp dụng.
- [ ] Test Binder và broker integration tests đều đạt.
- [ ] Đã định nghĩa canary, rollback và cách theo dõi outcome/lag/duplicate.
- [ ] Không xóa hay thay đổi dữ liệu broker/offset chỉ để khắc phục cấu hình nhầm.

## 33. Tổng kết

Chuyển từ annotation-based model sang functional model giúp code nghiệp vụ trong Spring Cloud Stream dễ hiểu và kiểm thử: **Supplier** tạo message, **Function** xử lý và phát kết quả, **Consumer** nhận message để thực hiện hành động, còn **StreamBridge** hỗ trợ phát output từ code bên ngoài một input binding.

Phần dễ mắc lỗi nhất không nằm ở câu lệnh Java mà ở **hợp đồng vận hành**: tên binding đổi từ input/output sang function-in-0/function-out-0; destination, group, serializer, partition, retry/DLQ và acknowledgement phải được map đúng. Với Kafka Streams stateful, multiple binders, header routing hoặc các listener có điều kiện, hãy lập kế hoạch chuyển đổi riêng thay vì thay thế annotation một cách cơ học.

Một migration chỉ được xem là an toàn khi cả logic nghiệp vụ, luồng message, khả năng xử lý lỗi và hành vi trong lúc restart/rebalance đều được kiểm chứng bằng test tương ứng.

## Tài liệu tham khảo

- [Spring Cloud Stream — Programming Model](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producing-and-consuming-messages.html)
- [Spring Cloud Stream — Functional Binding Names](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/functional-binding-names.html)
- [Spring Cloud Stream — StreamBridge](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producing-and-consuming-messages.html#streambridge-and-dynamic-destinations)
- [Spring Cloud Stream — Testing](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/spring_integration_test_binder.html)
- [Spring Cloud Stream — Kafka Binder](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/overview.html)
- [Spring Cloud Stream — Rabbit Binder](https://docs.spring.io/spring-cloud-stream/reference/rabbit/rabbit_overview.html)
- [Spring Cloud Function — Programming Model](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html)

