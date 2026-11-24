# Khi nào nên viết binder và khi nào nên dùng thư viện broker trực tiếp

Trong Spring Cloud Stream, mô hình hàm Supplier, Function và Consumer cho phép xử lý sự kiện mà không buộc phần nghiệp vụ phải biết chi tiết của Kafka, RabbitMQ hoặc Pulsar. Binder kết nối các input/output binding với broker, chuyển đổi cấu hình, quản lý endpoint và phối hợp một phần vòng đời consumer/producer. Nhưng có những lúc ứng dụng cần một API hoặc tính năng broker nằm ngoài abstraction hiện có. Khi ấy, đội phát triển phải lựa chọn: tiếp tục dùng binder chuẩn, mở rộng/cấu hình binder chuẩn, dùng thư viện broker trực tiếp, hay xây dựng một custom binder.

Quyết định tốt không bắt đầu từ câu hỏi “có viết được binder không?”, mà từ yêu cầu về chức năng, tính đúng đắn, khả năng tái sử dụng, quyền kiểm soát protocol và chi phí bảo trì. Viết custom binder là phát triển một thành phần hạ tầng có hợp đồng với Spring Cloud Stream; nó khác với viết thêm một class gọi KafkaTemplate hoặc RabbitTemplate.

## 1. Bốn lựa chọn thường gặp

| Lựa chọn | Cơ chế | Khi phù hợp nhất | Trách nhiệm chính |
|---|---|---|---|
| Binder có sẵn | Kafka Binder, RabbitMQ Binder, Pulsar Binder hoặc Kafka Streams Binder phù hợp | Luồng event tiêu chuẩn theo mô hình hàm, binding và group | Cấu hình, kiểm thử, vận hành business flow |
| Tùy biến binder có sẵn | Extended binding properties, client config, customizer, native encoding/decoding | Cần tham số broker riêng nhưng vẫn nằm trong khả năng binder | Hiểu đúng extension point và phiên bản |
| API broker trực tiếp | Spring Kafka, Spring AMQP, Spring Pulsar hoặc client SDK | Cần API/semantics đặc thù cho một ứng dụng hay một tuyến xử lý | Tự quản lý nhiều chi tiết producer, listener và delivery |
| Custom Binder SPI | Module Binder mới triển khai adapter tới middleware khác | Nhiều ứng dụng cần cùng một binding abstraction trên broker/protocol chưa có binder thích hợp | Cung cấp SPI, provisioning, consumer/producer lifecycle, cấu hình, test và nâng cấp |

Một ứng dụng có thể kết hợp các lựa chọn. Ví dụ consumer nghiệp vụ nhận event qua Kafka Binder, còn một job vận hành dùng AdminClient của Kafka để tra cứu metadata. Điều đó không đồng nghĩa phải tự viết Kafka Binder mới hoặc thay thế tất cả binding bằng client trực tiếp.

~~~mermaid
flowchart TD
    A["Có yêu cầu messaging mới"] --> B{"Binder chuẩn hỗ trợ yêu cầu?"}
    B -->|Có| C["Dùng binder chuẩn"]
    B -->|Một vài thiếu sót| D{"Extension point đáp ứng?"}
    D -->|Có| E["Tùy biến binder chuẩn"]
    D -->|Không| F{"Cần dùng lại trong nhiều ứng dụng?"}
    B -->|Không| F
    F -->|Không| G["Dùng API/SDK broker trực tiếp"]
    F -->|Có| H{"Có thể định nghĩa contract ổn định?"}
    H -->|Không| G
    H -->|Có| I["Đánh giá đầu tư custom Binder SPI"]
~~~

Sơ đồ là quy tắc quyết định ban đầu. Trước khi đầu tư custom binder, vẫn phải kiểm tra thư viện/adapter được cộng đồng hỗ trợ, khả năng mở rộng Spring Integration và chi phí vận hành thực tế.

## 2. Binder chuẩn cung cấp những gì?

Các ứng dụng Spring Cloud Stream thường dùng function bean và binding names thay vì viết code tạo consumer thủ công:

~~~java
@Configuration
class OrderFunctions {

    @Bean
    Function<OrderCreated, OrderValidated> validateOrder() {
        return event -> new OrderValidated(
                event.orderId(), event.customerId(), event.total());
    }
}
~~~

~~~yaml
spring:
  cloud:
    function:
      definition: validateOrder
    stream:
      bindings:
        validateOrder-in-0:
          destination: orders.created
          group: order-validation
          content-type: application/json
        validateOrder-out-0:
          destination: orders.validated
          content-type: application/json
~~~

Với binder phù hợp trên classpath, framework tạo kết nối từ input/output binding tới destination. Những lợi ích thường gặp:

- Tách phần xử lý nghiệp vụ khỏi code mở connection và polling listener.
- Có convention nhất quán cho function, binding names, destination và consumer group.
- Cấu hình theo môi trường bằng Spring Boot properties.
- Có cơ chế mở rộng thuộc tính producer/consumer theo từng binder.
- Tận dụng khả năng retry, error handling, partitioning và provisioning mà binder cụ thể hỗ trợ.
- Dễ viết test theo abstraction Spring Cloud Stream bằng Test Binder.
- Có thể dùng nhiều binder trong một ứng dụng qua named binder configuration.

Các chức năng này **không có semantics giống hệt nhau ở mọi broker**. Kafka offset và partition khác RabbitMQ acknowledgement/queue, cũng khác Pulsar subscription. Không coi abstraction chung là cam kết tự động về giao nhận exactly-once, thứ tự toàn cục hoặc transaction xuyên broker.

## 3. Bắt đầu bằng khả năng của binder đã có

Trước khi bỏ binder, kiểm tra bốn tầng mở rộng:

1. **Common binding properties:** destination, group, content type, consumer concurrency, error handling và partitioning.
2. **Extended binder properties:** các option đặc thù cho Kafka, RabbitMQ, Pulsar ở cấp producer hoặc consumer binding.
3. **Client/native configuration:** serializer, deserializer, SSL/SASL, acknowledgement, listener/container, batching, timeout và client factory khi binder hỗ trợ.
4. **Customization extension points:** BinderCustomizer, ProducerMessageHandlerCustomizer, cấu hình producer/consumer và các hook khác được phiên bản binder cung cấp.

Nếu yêu cầu có thể đáp ứng ở các tầng này, duy trì binder chuẩn thường giảm rủi ro hơn việc phải viết lại lifecycle, retry, rebalance và error infrastructure.

### 3.1. Ví dụ chỉ cần native Kafka config

Giả sử một consumer yêu cầu cấu hình fetch và timeout riêng. Trước tiên tìm thuộc tính mà Kafka Binder chuyển tới Kafka consumer hoặc listener container, ví dụ cấu hình chung:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.created
          group: order-workers
          consumer:
            concurrency: 3
      kafka:
        binder:
          brokers: kafka.internal:9092
          consumer-properties:
            fetch.min.bytes: 1024
~~~

Tên và vị trí các option cần được kiểm tra với tài liệu release đang chạy. Một số setting thuộc binder-level, một số thuộc extended binding-level hoặc Kafka client configuration. Thêm một option Kafka không có nghĩa cần viết custom binder.

### 3.2. Ví dụ dùng BinderCustomizer

Trong ứng dụng có nhiều binder, Spring Cloud Stream hỗ trợ BinderCustomizer để tùy biến instance binder đã được tạo. Đây là extension point cho binder hiện có, **không phải** custom Binder SPI mới.

~~~java
@Bean
BinderCustomizer binderCustomizer() {
    return (binder, binderName) -> {
        if (binder instanceof KafkaMessageChannelBinder kafkaBinder) {
            // Chỉ áp dụng thay đổi được API của phiên bản cho phép.
            // Ví dụ: cấu hình một rebalance listener phù hợp.
        }
    };
}
~~~

Đoạn mã là khung để minh họa vị trí customizer, chưa phải một thay đổi vận hành hoàn chỉnh. Khi có nhiều instance cùng loại binder, dùng binderName để phân biệt. Không ép cast mọi binder thành KafkaMessageChannelBinder, vì có thể còn RabbitMQ Binder hoặc Kafka Streams Binder với loại riêng.

### 3.3. Native encoding và conversion

Khi cần serializer hoặc schema đặc thù, kiểm tra khả năng use-native-encoding/use-native-decoding trước. Nếu binder cho phép chuyển trách nhiệm serialize/deserialize tới client native, có thể giữ function binding nhưng sử dụng Serde/serializer tương thích Avro, Protobuf hoặc schema registry. Kiểm thử end-to-end với broker thật; Test Binder không chứng minh wire format hoặc registry hoạt động đúng.

## 4. StreamBridge là lựa chọn trung gian cho producer

Một yêu cầu thường gặp là gửi message từ REST controller, scheduled job hoặc domain service, tức việc gửi không xuất phát trực tiếp từ một Function đã có output. Spring Cloud Stream cung cấp StreamBridge để publish tới output binding mà không cần dựng producer client thủ công.

~~~java
@Service
class AuditPublisher {
    private final StreamBridge streamBridge;

    AuditPublisher(StreamBridge streamBridge) {
        this.streamBridge = streamBridge;
    }

    boolean publish(OrderAuditEvent event) {
        return streamBridge.send("audit-out-0", event);
    }
}
~~~

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        audit-out-0:
          destination: orders.audit
          content-type: application/json
~~~

Trong ví dụ này, StreamBridge gửi event thông qua binder của output binding. Khi có nhiều binder, có overload để chỉ định binder name. Giá trị boolean phản ánh kết quả gửi vào messaging channel theo contract của StreamBridge; **không tự động là chứng nhận broker đã lưu bền vững**. Nếu nghiệp vụ cần publisher acknowledgement hoặc transaction cụ thể, phải kiểm tra semantics của binder hoặc dùng API native thích hợp.

Không viết custom binder chỉ vì cần publish từ REST endpoint. StreamBridge hoặc một Supplier/Function phù hợp thường đủ.

## 5. Khi nào dùng thư viện broker trực tiếp?

Dùng thư viện trực tiếp khi ứng dụng cần quyền điều khiển cụ thể mà binder không expose hợp lý, nhất là yêu cầu chỉ xuất hiện tại một vài nơi. Có thể dùng:

- **Kafka:** Spring Kafka KafkaTemplate, @KafkaListener, listener container, Producer/Consumer/AdminClient hoặc Kafka Streams API.
- **RabbitMQ:** Spring AMQP RabbitTemplate, @RabbitListener, RabbitAdmin và listener container; khi cần tính năng đặc biệt có thể dùng RabbitMQ Java client.
- **Pulsar:** Spring Pulsar PulsarTemplate, @PulsarListener, @ReactivePulsarListener hoặc Pulsar Java client.
- **Các giao thức khác:** SDK do vendor cung cấp nếu chưa có integration framework phù hợp.

Các nhu cầu có thể dẫn tới native API:

- Điều khiển offset, seek, pause/resume, listener container hoặc assignment theo một workflow đặc biệt.
- Dùng Kafka transactions, AdminClient hoặc consumer API có yêu cầu chính xác mà binding abstraction không bao phủ.
- RabbitMQ RPC/request-reply, publisher confirms/returns hoặc topology/quorum/stream behavior rất đặc thù.
- Pulsar Reader API, subscription-specific operation, schema API hoặc tính năng mới chưa được binder hỗ trợ.
- Truy cập broker admin API trong một công cụ vận hành thay vì một luồng Function/Consumer.
- Cần hook mức thấp cho performance tracing, custom protocol header hoặc client extension.

Trước khi dùng native API, xác minh xem **Spring Kafka / Spring AMQP / Spring Pulsar** đã cung cấp abstraction phù hợp hay chưa. Gọi thẳng KafkaConsumer hoặc RabbitMQ Channel chỉ khi cần hơn những gì thư viện Spring hỗ trợ.

## 6. Ví dụ API trực tiếp cho Kafka

Với một chức năng gửi event đặc thù cần quan sát callback từ producer, dùng KafkaTemplate:

~~~java
@Service
class InventoryAuditPublisher {
    private final KafkaTemplate<String, InventoryAuditEvent> template;

    InventoryAuditPublisher(
            KafkaTemplate<String, InventoryAuditEvent> template) {
        this.template = template;
    }

    CompletableFuture<SendResult<String, InventoryAuditEvent>> publish(
            InventoryAuditEvent event) {
        return template.send("inventory.audit", event.sku(), event);
    }
}
~~~

Ví dụ áp dụng cho các phiên bản Spring Kafka có API send trả CompletableFuture. Producer factory, serializer, authentication và broker endpoint vẫn phải được cấu hình đúng. Caller cần xử lý completion/exception và chính sách retry; chỉ gọi send rồi bỏ qua kết quả có thể không đáp ứng yêu cầu giao nhận.

~~~java
publisher.publish(event).whenComplete((result, error) -> {
    if (error != null) {
        log.warn("Audit publish failed for sku={}", event.sku(), error);
        // Báo lỗi hoặc dùng chiến lược retry/outbox có kiểm soát.
    }
});
~~~

Nếu nguồn event xuất phát từ database transaction và không thể chấp nhận mất event khi process crash, chỉ dựa vào CompletableFuture không đủ. Cân nhắc transactional outbox và idempotent consumer. Kafka producer idempotence không tạo transaction nguyên tử với cơ sở dữ liệu độc lập.

## 7. Ví dụ API trực tiếp cho RabbitMQ và Pulsar

Spring AMQP cung cấp RabbitTemplate:

~~~java
@Service
class RabbitAuditPublisher {
    private final RabbitTemplate template;

    RabbitAuditPublisher(RabbitTemplate template) {
        this.template = template;
    }

    void publish(InventoryAuditEvent event) {
        template.convertAndSend("audit.exchange", "inventory.audit", event);
    }
}
~~~

Lệnh convertAndSend không có nghĩa broker chắc chắn đã lưu message; nếu cần xác nhận, cấu hình publisher confirms/returns phù hợp và xử lý trường hợp unroutable. Exchange, queue, binding, durability và permission vẫn phải được provision đúng.

Với Pulsar, Spring Pulsar cung cấp PulsarTemplate:

~~~java
@Service
class PulsarAuditPublisher {
    private final PulsarTemplate<InventoryAuditEvent> template;

    PulsarAuditPublisher(PulsarTemplate<InventoryAuditEvent> template) {
        this.template = template;
    }

    void publish(InventoryAuditEvent event) {
        template.send(
                "persistent://inventory/events/inventory.audit",
                event);
    }
}
~~~

Schema inference, producer config, acknowledgement và transaction phụ thuộc Spring Pulsar và Pulsar client version. Không sao chép cấu hình Kafka sang Pulsar vì delivery và subscription semantics khác nhau.

### 7.1. Direct listener và yêu cầu vận hành

Khi dùng @KafkaListener, @RabbitListener hoặc @PulsarListener thay cho Consumer binding, nhóm phát triển cần trực tiếp kiểm soát container configuration, retry, concurrency, lỗi conversion, acknowledgement, DLQ, tracing và observability theo thư viện. Các thư viện Spring giúp xử lý nhiều phần nhưng không tự cung cấp quy ước binding/function chung của Spring Cloud Stream.

Không tạo consumer native song song với binder consumer trên cùng topic/group chỉ để “nghe thêm” nếu chưa hiểu assignment: chúng có thể tranh partition hoặc phân phối message khác kỳ vọng. Nếu cần hai xử lý độc lập, dùng group/subscription độc lập theo semantics broker.

## 8. Khi nào custom Binder SPI thực sự hợp lý?

Một custom binder hợp lý khi có một transport hoặc hệ thống messaging mà nhiều ứng dụng Spring Cloud Stream phải dùng với **cùng hợp đồng** về binding, provisioning, consumer group, producer acknowledgement và error handling.

Ví dụ một tổ chức có event bus nội bộ dùng protocol riêng. Hàng chục dịch vụ cần khai báo:

- Input/output theo Function và Consumer.
- Destination từ application.yml.
- Group hoặc subscription độc lập.
- Partition routing hoặc sharding.
- Retry, acknowledgement và error channels có quy tắc thống nhất.
- Authentication, observability và resource provisioning.
- Test Binder-compatible contract để team ứng dụng chỉ viết nghiệp vụ.

Nếu mỗi ứng dụng tự dùng SDK, chúng sẽ lặp lại code subscription, conversion, lifecycle, retries và tracing. Lúc này một custom binder có thể chuyển phần tích hợp ấy vào một module tái sử dụng.

Điều kiện nên thỏa:
1. Không có binder chuẩn hoặc extension tương thích với transport.
2. Protocol/SDK ổn định đủ để duy trì một interface.
3. Có ít nhất nhiều consumer/team cần dùng chung, không chỉ một endpoint.
4. Có một nhóm chịu trách nhiệm version, security, bug fix và nâng cấp Spring.
5. Delivery semantics có thể ánh xạ trung thực vào contract Spring Cloud Stream.
6. Có cluster/test infrastructure cho integration và failure tests.
7. Có tài liệu sử dụng, migration và compatibility policy cho binder.

Nếu protocol không có consumer group hoặc acknowledgement tương đương, custom binder vẫn có thể triển khai nhưng phải **công bố giới hạn**, không giả lập cam kết không tồn tại.

## 9. Custom binder là gì ở mức SPI?

Spring Cloud Stream định nghĩa Binder SPI dùng để gắn producer và consumer target vào middleware. Hợp đồng lõi có hình dạng:

~~~java
public interface Binder<T, C extends ConsumerProperties, P extends ProducerProperties> {
    Binding<T> bindConsumer(
            String bindingName,
            String group,
            T inboundBindTarget,
            C consumerProperties);

    Binding<T> bindProducer(
            String bindingName,
            T outboundBindTarget,
            P producerProperties);
}
~~~

Các generic type mô tả target và consumer/producer properties. Trong một Binder triển khai theo MessageChannel, adapter phải biết tạo endpoint nhận và handler gửi. Một custom binder cần ít nhất:

- **ProvisioningProvider:** ánh xạ logical destination/group thành physical destination, kiểm tra/tạo tài nguyên theo policy.
- **Consumer endpoint hoặc MessageProducer:** đọc event từ transport, chuyển thành Spring Message và phát vào input target.
- **Producer MessageHandler:** nhận Spring Message, serialize và gửi tới transport.
- **Binder implementation:** triển khai SPI hoặc kế thừa AbstractMessageChannelBinder khi phù hợp.
- **Binder configuration:** Spring @Configuration đăng ký bean Binder và dependency tương ứng.
- **Discovery metadata:** META-INF/spring.binders để Spring Cloud Stream tìm type.
- **Extended properties, health/metrics và test** theo nhu cầu production.

Một cấu trúc module điển hình:

~~~text
acme-stream-binder/
  src/main/java/com/example/acme/
    AcmeBinderConfiguration.java
    AcmeMessageChannelBinder.java
    AcmeProvisioningProvider.java
    AcmeMessageProducer.java
    AcmeMessageHandler.java
    AcmeConsumerProperties.java
    AcmeProducerProperties.java
  src/main/resources/META-INF/
    spring.binders
~~~

Tên lớp chỉ là minh họa; tên thật và cách chia class phụ thuộc SPI của Spring Cloud Stream release tương ứng.

### 9.1. Đăng ký binder type

File META-INF/spring.binders là file properties mô tả binder type và configuration class:

~~~properties
acmeBus: com.example.acme.AcmeBinderConfiguration
~~~

Trong configuration có bean Binder và các service adapter. Khi module có trên classpath, ứng dụng có thể chọn named binder:

~~~yaml
spring:
  cloud:
    stream:
      default-binder: acmeBus
      bindings:
        ingestEvent-in-0:
          destination: orders.in
          group: audit-workers
          binder: acmeBus
~~~

Ví dụ chỉ minh họa cách discovery/binder selection; chưa có implementation nên không tự chạy được. Các binder implementation khác có thể xuất hiện cùng classpath, khi đó cần cấu hình default-binder hoặc binder riêng cho từng binding.

### 9.2. Dùng AbstractMessageChannelBinder khi phù hợp

Với transport có mô hình MessageChannel và MessageHandler, Spring Cloud Stream cung cấp AbstractMessageChannelBinder để giảm phần boilerplate. Binder mới có thể triển khai các hook tạo producer handler và consumer endpoint, đồng thời dùng ProvisioningProvider.

~~~java
// Khung kiến trúc — chưa phải class hoàn chỉnh để biên dịch.
class AcmeBinder extends AbstractMessageChannelBinder<
        ConsumerProperties,
        ProducerProperties,
        AcmeProvisioningProvider> {

    // Constructor tạo binder với provisioning provider và cấu hình nền.

    // createProducerMessageHandler(...):
    //   chuyển Spring Message thành payload của Acme transport.

    // createConsumerEndpoint(...):
    //   kết nối Acme subscription với inbound MessageChannel.
}
~~~

Không chỉ tạo một class có tên Binder là Spring Cloud Stream sẽ tự hỗ trợ partition/group/error handling. Mỗi behavior phải được triển khai hoặc ủy quyền đúng vào SDK; phải test shutdown, reconnection, backpressure và resource cleanup.

## 10. Trách nhiệm khó nhất khi tự viết binder

| Mảng | Binder cần bảo đảm hoặc công bố | Rủi ro nếu thiếu |
|---|---|---|
| Destination provisioning | Ánh xạ tên logical sang resource thật, không tạo sai môi trường | Topic/queue thiếu, ACL vượt quyền |
| Consumer group | Phân phối message và progress theo group/subscription | Duplicate hoặc message bị bỏ sót |
| Acknowledgement | Điều kiện ack/nack và xử lý crash window | At-most-once ngoài ý muốn hoặc vô hạn redelivery |
| Partition/key | Routing key và ordering scope | Event cùng aggregate sai thứ tự |
| Retry/DLQ | Retry hữu hạn, phân loại poison message, redelivery | Retry storm hoặc mất message |
| Payload/headers | Serializer, content type, schema, header mapping | Dữ liệu sai/không tương thích |
| Backpressure | Giới hạn in-flight, batching, pause/resume | Hết RAM, trễ không kiểm soát |
| Lifecycle | Start/stop, reconnect, rebalance, dispose resources | Connection leak hoặc consumer zombie |
| Security | Auth, TLS, secret rotation | Lộ quyền, kết nối không an toàn |
| Observability | Error count, latency, lag/backlog, tracing | Khó điều tra, thiếu alert |
| Compatibility | SPI version, broker SDK version | Hỏng khi nâng Spring Cloud |
| Testing | Contract, integration, restart, chaos | Lỗi delivery chỉ xuất hiện trên production |

Phần tốn công nhất thường không phải gọi send() hay poll(), mà là đảm bảo delivery semantics khi có sự cố, timeout, restart, đồng thời quản lý resource và chứng minh khả năng vận hành trên nhiều phiên bản.

## 11. Khi nào không nên viết custom binder?

Các tình huống sau thường có hướng đơn giản hơn:

- Chỉ cần thêm một producer để phát event từ REST controller → StreamBridge.
- Chỉ cần thay content type, group, concurrency, retry hoặc partition key → binding properties.
- Chỉ cần Kafka consumer seek một lần trong một job riêng → Spring Kafka listener/Consumer API.
- Chỉ cần gọi RabbitMQ management API hoặc Pulsar admin API → admin client/tool, không cần binder.
- Chỉ cần gửi request-reply qua RabbitMQ trong một service → Spring AMQP.
- Chỉ cần Kafka Streams DSL, KStream hoặc KTable → Kafka Streams Binder hoặc Kafka Streams API; không cần tạo binder mới cho Kafka.
- Chỉ muốn “ẩn” vài method SDK để code nghiệp vụ gọn hơn → viết application service/adapter mỏng, không triển khai Binder SPI.
- Transport chỉ có một consumer trong một ứng dụng và không có kế hoạch tái sử dụng → thường dùng SDK trực tiếp.

Một abstraction nhỏ do nhóm ứng dụng sở hữu, ví dụ EventPublisher interface và một adapter dùng KafkaTemplate, có thể đủ để cô lập business code khỏi client API. Đây là **adapter của ứng dụng**, khác với một reusable Spring Cloud Stream Binder.

## 12. Ma trận lựa chọn theo yêu cầu

| Yêu cầu | Binder chuẩn | Tùy biến binder | API trực tiếp | Custom binder |
|---|---|---|---|---|
| Consumer Function đơn giản Kafka/Rabbit/Pulsar | Phù hợp nhất | Khi cần option riêng | Có thể nhưng tăng code | Không cần |
| Publish từ REST endpoint | StreamBridge | Khi cần producer setting | Nếu cần broker callback đặc thù | Không cần |
| Kafka seek/assignment control rất chi tiết | Kiểm tra khả năng trước | Có thể đủ | Thường phù hợp | Không nên |
| Rabbit publisher confirms phức tạp | Tùy binder/version | Có thể phù hợp | Spring AMQP phù hợp | Không nên |
| Pulsar Reader hoặc API subscription đặc thù | Kiểm tra binder | Có thể đủ | Spring Pulsar/SDK phù hợp | Không nên |
| Broker nội bộ không có binder, dùng cho 1 dịch vụ | Không có | Không áp dụng | Thường phù hợp | Chưa đáng đầu tư |
| Broker nội bộ ổn định dùng cho hàng chục dịch vụ | Không có | Không áp dụng | Lặp lại adapter | Có thể hợp lý |
| Thay đổi protocol thường xuyên | Không có | Không áp dụng | Linh hoạt hơn | Rủi ro lớn |
| Muốn nhất quán config/test/metrics ở nhiều team | Có sẵn khi được hỗ trợ | Có thể bổ sung | Cần convention riêng | Có giá trị nếu đủ quy mô |

Không lựa chọn chỉ vì “API trực tiếp nhanh hơn” hoặc “binder dễ bảo trì hơn” theo cảm giác. Chi phí thực tế phải được đo theo throughput, latency, resource, số sự cố, số nhóm sử dụng và công sức nâng cấp.

## 13. So sánh chi phí vòng đời

Một custom binder là một sản phẩm thư viện nội bộ. Nhóm phát triển chịu thêm:

1. Thiết kế SPI và mapping protocol.
2. Duy trì compatibility với Spring Boot/Cloud/Integration releases.
3. Quản lý SDK, CVE, authentication, TLS và cấu hình nâng cấp.
4. Chạy test matrix cho broker version, retry, disconnect và restart.
5. Viết migration guide khi schema/configuration thay đổi.
6. Gỡ lỗi production khi các service dùng chung binder.
7. Cung cấp observability, troubleshooting và runbook.
8. Hỗ trợ developer adoption và version pinning/BOM.

Đổi lại, nhiều service tránh viết cùng adapter và có một cách tiêu chuẩn để cấu hình, triển khai và kiểm thử. Lợi ích chỉ lớn khi mức tái sử dụng cao và interface đủ ổn định.

Một thư viện wrapper quanh SDK trực tiếp có thể là lựa chọn ở giữa: cung cấp EventPublisher/EventSubscriber chung, phần mapping thuộc ứng dụng vẫn gọn, nhưng không cần hứa hỗ trợ toàn bộ Spring Cloud Stream Binder contract.

## 14. Rủi ro khi kết hợp binder và client trực tiếp

Kết hợp là hợp lệ nhưng cần ranh giới rõ ràng:

- Hai đường consumer trên **cùng group** có thể chia partition hoặc cạnh tranh message; đó không phải hai bản sao độc lập của event.
- Hai đường producer có thể dùng serializer/header convention khác nhau, khiến downstream khó đọc.
- Retry/DLQ của binder khác error handler của native listener, dẫn tới chính sách không nhất quán.
- Kafka transactions chỉ bao phủ các producer/consumer được cấu hình phù hợp; không mặc nhiên kết hợp với database, RabbitMQ hoặc Pulsar transaction.
- Một binding và một native listener có thể cùng provision hoặc kiểm soát queue/topic, tạo thay đổi ngoài dự kiến.
- Traces và metrics có thể bị đếm hai lần nếu instrument không rõ ràng.

Nên xác định ownership: đường nào consume input chính, đường nào publish audit hoặc làm admin, nhóm nào sở hữu retry và acknowledgement. Ghi rõ naming convention, content contract và consumer group/subscription.

## 15. Checklist thiết kế trước khi viết binder mới

Trả lời các câu hỏi dưới đây bằng một tài liệu thiết kế ngắn:

1. Broker/protocol nào chưa có binder phù hợp?
2. Vì sao binder có sẵn, customizer hoặc StreamBridge không đủ?
3. Có bao nhiêu service/team sẽ dùng trong 6–12 tháng?
4. Destination, group/subscription và partition được ánh xạ thế nào?
5. Khi consumer xử lý thành công/thất bại, ack/nack ra sao?
6. Khi process crash sau side effect nhưng trước ack, điều gì xảy ra?
7. Có retry limit, DLQ, poison-message policy và idempotency contract không?
8. Payload/schema/header chuyển đổi và versioning thế nào?
9. Có backpressure, flow control, prefetch và memory bound không?
10. Cấu hình secrets, TLS, resource provisioning và quyền tối thiểu ra sao?
11. Metric, health, tracing và alert nào phải có?
12. Có thể dựng broker test và mô phỏng failover/restart không?
13. Tương thích Spring Cloud Stream/Boot version nào?
14. Ai sở hữu bug fix, phát hành, security patch và migration?
15. Nếu binder bị bỏ, có kế hoạch chuyển sang SDK/native adapter không?

Nếu chưa trả lời được delivery semantics hoặc không có owner lâu dài, không nên công bố custom binder để các team khác phụ thuộc.

## 16. Kế hoạch thử nghiệm bằng một spike nhỏ

Trước khi phát triển binder đầy đủ, dùng proof of concept cho một topic/subscription. Đánh giá hai hướng: dùng Spring broker client trực tiếp và một custom binder tối thiểu.

Với API trực tiếp, đo:
- Số dòng cấu hình/code cần duy trì cho một consumer và producer.
- Throughput, p95/p99 latency và CPU.
- Mức độ truy cập được native API.
- Retry, reconnect, checkpoint/ack và shutdown.
- Khả năng test bằng embedded broker/Testcontainers hoặc môi trường thật.

Với custom binder, đo:
- Khối lượng SPI/provisioning/endpoint implementation.
- Binding discovery và naming.
- Tương thích function, conversion, group, error handling.
- Observability và lifecycle.
- Chi phí integration/contract test.
- Công sức upgrade framework.

Nếu chỉ một ứng dụng dùng và custom binder đòi nhiều logic vận hành, API trực tiếp thường có chi phí sở hữu thấp hơn. Nếu nhiều ứng dụng tái sử dụng và framework contract đem lại lợi ích đo được, binder là khoản đầu tư có thể biện minh.

## 17. Kiểm thử theo lựa chọn

### 17.1. Khi dùng binder chuẩn

- Unit test Function/Consumer logic.
- Test Binder với InputDestination và OutputDestination.
- Integration test với broker cho partition, group, ack, retry, DLQ, schema.
- Test config profile và security thực tế.
- Monitoring lag, backlog, latency, DLQ trong staging.

### 17.2. Khi dùng API broker trực tiếp

- Test KafkaTemplate/RabbitTemplate/PulsarTemplate bằng test double chỉ cho logic mỏng.
- Integration test producer acknowledgement và listener processing thật.
- Kiểm tra callback/exception, timeout, retry và serialization.
- Test restart giữa database commit và broker ack.
- Test concurrency, partition/order, backlog và network fault.

### 17.3. Khi tự viết binder

Ngoài các test trên, cần **contract test** cho SPI:
- Binder type được discovery đúng qua META-INF/spring.binders.
- bindProducer/bindConsumer tạo Binding có lifecycle start/stop/unbind đúng.
- Destination và group được provision đúng theo quyền và environment.
- Producer handler forward payload/headers đúng schema.
- Consumer endpoint chuyển nhận dữ liệu thành Spring Message đúng.
- Retry/DLQ không làm mất message hoặc retry vô hạn.
- Partition/key routing bảo toàn ordering đã hứa.
- Reconnect, rebalance, broker restart và redelivery được xử lý.
- Không leak thread, connection, subscription sau unbind.
- Nhiều instance và nhiều binder cùng classpath hoạt động đúng.
- Nâng Spring Boot/Cloud/broker SDK không làm contract thay đổi bất ngờ.

Test Binder chỉ kiểm tra abstraction trong JVM; nó không thay thế broker integration test hay phép thử crash/recovery.

## 18. Chuyển đổi từng bước giữa các hướng

Nếu đang dùng SDK trực tiếp mà sau này muốn tạo custom binder:

1. Thống kê các service và chuẩn hóa event envelope, serializer/header.
2. Viết consumer/producer adapter nhỏ có interface rõ.
3. Tạo binder module mới và triển khai một tuyến thử nghiệm.
4. Chạy song song theo luồng shadow có group/subscription và destination tách biệt; tránh duplicate side effect.
5. So sánh output, ordering, latency, retry và metrics.
6. Chuyển từng service sau khi broker integration test pass.
7. Giữ rollback path, không đổi consumer group/offset hoặc subscription một cách tùy tiện.
8. Sau khi migration hoàn tất mới ngừng đường native cũ.

Nếu muốn rời binder để dùng native client, cũng cần phân tích offset/group, topic mapping, DLQ/retry và serializer. Tránh thay đổi cách consume và thay đổi schema trong cùng một lần triển khai nếu chưa có kế hoạch migration có thể kiểm chứng.

## 19. Tình huống minh họa

### Tình huống A: Xử lý đơn hàng với Kafka

Ứng dụng nhận orders.created, validate rồi phát orders.validated. Các yêu cầu đều dùng Function, group và destination tiêu chuẩn. Chọn Kafka Binder. Nếu REST endpoint cần phát event bổ sung, dùng StreamBridge. Không cần custom binder.

### Tình huống B: Job vận hành cần đọc offset tùy ý

Một job đọc lại record ở offset cụ thể, truy vấn metadata partition và điều khiển seek thủ công. Đây là chức năng broker-specific và ít tái sử dụng theo mô hình Stream. Chọn Spring Kafka hoặc Kafka AdminClient/Consumer API; giữ phần nghiệp vụ khác trên binder nếu phù hợp.

### Tình huống C: RabbitMQ workflow cần request-reply

Một service gọi RPC qua RabbitMQ với correlation ID, reply timeout và xử lý publisher confirms. Spring AMQP RabbitTemplate phù hợp hơn việc thêm một custom binder chỉ cho một yêu cầu RPC. Cần test reply queue và timeout trên broker thật.

### Tình huống D: Nền tảng event bus nội bộ

Nhiều team muốn dùng một broker proprietary, đồng nhất destination, group, retry, DLQ và metrics. Broker có API ổn định và nhóm platform chịu trách nhiệm adapter. Xây custom binder sau spike/contract test là một lựa chọn hợp lý vì lợi ích có tính tổ chức.

### Tình huống E: Kafka Streams stateful processing

Ứng dụng dùng KStream/KTable, join, window và state store. Xem xét Kafka Streams Binder hoặc Kafka Streams API trực tiếp. Không viết lại Kafka Binder để hỗ trợ KTable nếu framework đã có binder chuyên biệt.

## 20. Những hiểu lầm thường gặp

| Hiểu lầm | Điều cần hiểu đúng |
|---|---|
| Chỉ cần một tính năng broker mới là phải viết binder | Có thể dùng extended properties, customizer hoặc API trực tiếp |
| Custom binder chỉ là wrapper cho send/receive | Nó phải tích hợp lifecycle, provisioning, error, group và delivery semantics |
| Binder luôn hỗ trợ mọi tính năng broker native | Binder abstraction có giới hạn và semantics phụ thuộc implementation |
| Dùng API trực tiếp luôn nhanh hơn binder | Cần benchmark; overhead không chỉ ở abstraction |
| Binder bảo đảm exactly-once xuyên database và broker | Không có cam kết transaction phân tán tự động |
| StreamBridge trả true là message đã lưu trên broker | Chỉ là kết quả send theo contract của framework; kiểm tra publisher confirmation riêng |
| Tự viết binder một lần rồi không cần bảo trì | Phải nâng theo Spring, SDK, bảo mật và broker protocol |
| Test Binder pass là broker integration cũng pass | Test Binder không mô phỏng đầy đủ broker retry, offset, ack, partition, network |
| Hai consumer cùng group là hai bản sao độc lập | Trong nhiều broker, chúng chia hoặc cạnh tranh message |
| API trực tiếp khiến business code nhất thiết phụ thuộc SDK | Có thể đặt adapter interface ở application boundary |

## 21. Checklist ra quyết định

- [ ] Đã kiểm tra binder chính thức hoặc được cộng đồng duy trì cho broker.
- [ ] Đã thử binding/extended properties, native serializer và customizer.
- [ ] Đã cân nhắc StreamBridge cho producer ngoài function.
- [ ] Đã xác định chính xác native feature còn thiếu.
- [ ] Đã định nghĩa group, ack, transaction, retry, DLQ và ordering yêu cầu.
- [ ] Đã phân tích liệu feature chỉ thuộc một service hay cần tái sử dụng rộng.
- [ ] Đã so sánh chi phí code, test, metrics, vận hành và nâng version.
- [ ] Nếu dùng API trực tiếp, đã cô lập SDK trong adapter/service phù hợp.
- [ ] Nếu tự viết binder, có owner và compatibility policy lâu dài.
- [ ] Có test broker thật cho failure window, redelivery và serialization.
- [ ] Có chính sách security, secret, TLS và resource provisioning.
- [ ] Có rollback/migration plan khi thay cách kết nối.
- [ ] Không tuyên bố giao nhận hoặc ordering mạnh hơn broker và implementation thực sự hỗ trợ.

Trong Spring Cloud Stream, binder chuẩn nên là điểm xuất phát cho luồng Function/Consumer thông thường. Khi chỉ thiếu một tính năng nhỏ, hãy tìm extension point trước. Khi một chức năng broker đặc thù cần quyền kiểm soát mức thấp trong phạm vi hẹp, Spring Kafka, Spring AMQP, Spring Pulsar hoặc SDK trực tiếp thường rõ ràng hơn. Custom Binder SPI trở nên đáng giá khi có một middleware chưa được hỗ trợ, semantics có thể định nghĩa trung thực và nhiều ứng dụng cần một lớp kết nối nhất quán, được vận hành lâu dài như một thư viện nền tảng.

## Tài liệu tham khảo

- [Spring Cloud Stream — Binder SPI](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/overview-binder-api.html)
- [Spring Cloud Stream — Implementing Custom Binders](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/overview-custom-binder-impl.html)
- [Spring Cloud Stream — Binder Configuration Properties](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binder-configuration-properties.html)
- [Spring Cloud Stream — Customizing Binders](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binder-customizer.html)
- [Spring Cloud Stream — Producing and Consuming Messages](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producing-and-consuming-messages.html)
- [Spring Kafka — Transactions](https://docs.spring.io/spring-kafka/reference/kafka/transactions.html)
- [Spring AMQP — AmqpTemplate](https://docs.spring.io/spring-amqp/reference/amqp/template.html)
- [Spring Pulsar — Quick Tour](https://docs.spring.io/spring-pulsar/reference/reference/pulsar/quick-tour.html)

