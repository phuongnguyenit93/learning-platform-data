# Thay đổi API của @KafkaListener

## Mục tiêu của bài học

Trong chương **Nâng cấp và tương thích**, bài này tổng hợp những thay đổi quan trọng của API `@KafkaListener` qua các thế hệ Spring Kafka. Trọng tâm là cách annotation điều khiển listener container, thay đổi cách xác định consumer group, subscription, batch mode, acknowledgment, xử lý bất đồng bộ và tùy biến container.

**SPRING_KAFKA_MESSAGING** tập trung xây dựng ứng dụng gửi và nhận sự kiện Kafka bằng Spring Kafka, KafkaTemplate và @KafkaListener; đồng thời giúp người học hiểu topic, partition, offset, consumer group, serialization, retry, dead-letter, transaction, exactly-once, xử lý đồng thời và kiểm thử. Khi nâng cấp Spring Kafka, thay đổi trong annotation có thể làm thay đổi group ID, cách listener nhận record, thời điểm commit offset hoặc cách container được tạo. Cần kiểm tra phiên bản dependency trước khi áp dụng cú pháp mới.

Sau bài học, người học có thể:

- Hiểu vai trò của @KafkaListener trong việc đăng ký listener endpoint và tạo container.
- Nhận diện các thuộc tính annotation quan trọng và mốc phiên bản được bổ sung.
- Phân biệt id, groupId và idIsGroup.
- Chọn subscription bằng topics, topicPattern hoặc topicPartitions.
- Sử dụng placeholder và SpEL đúng chỗ.
- Chọn record listener, batch listener hoặc asynchronous listener.
- Dùng filter, info, containerPostProcessor và ackMode khi phiên bản hỗ trợ.
- Cập nhật method signature và header API khi nâng cấp.
- Lập kế hoạch migration từ Spring Kafka 2.x lên 3.x hoặc 4.x.
- Kiểm thử tương thích trước khi phát hành.

## 1. @KafkaListener làm gì?

`@KafkaListener` đánh dấu một method hoặc class là điểm nhận message Kafka. Spring phát hiện annotation trong quá trình khởi tạo application context, tạo listener endpoint và đăng ký container để quản lý Kafka consumer.

Ở method-level, mỗi listener method thường có một listener container riêng. Ở class-level, một container có thể phục vụ nhiều method `@KafkaHandler`; Spring chọn method phù hợp theo kiểu payload.

~~~mermaid
flowchart TD
    A["@EnableKafka / Spring configuration"] --> B["KafkaListenerAnnotationBeanPostProcessor"]
    B --> C["Phát hiện @KafkaListener"]
    C --> D["Tạo listener endpoint"]
    D --> E["Chọn KafkaListenerContainerFactory"]
    E --> F["Tạo listener container"]
    F --> G["Kafka consumer poll"]
    G --> H["MessagingMessageListenerAdapter"]
    H --> I["Gọi listener method"]
~~~

Annotation không phải nơi cấu hình mọi chi tiết của Kafka consumer. Factory vẫn là nơi định nghĩa cấu hình chung như `ConsumerFactory`, error handler, converter, concurrency mặc định, acknowledgment mode mặc định và các container properties khác. Annotation cho phép override một số giá trị riêng cho từng listener.

Để dùng annotation-based listener trong cấu hình Java thuần, cần bật `@EnableKafka`; Spring Boot thường tự cấu hình hạ tầng listener khi có dependency và cấu hình phù hợp.

## 2. Các thuộc tính cốt lõi

| Thuộc tính | Vai trò |
|---|---|
| `id` | Định danh listener container; có thể được dùng làm group ID tùy `idIsGroup` |
| `groupId` | Ghi đè `group.id` cho listener |
| `idIsGroup` | Quyết định có dùng `id` làm `group.id` khi không khai báo `groupId` |
| `topics` | Subscribe một hoặc nhiều topic |
| `topicPattern` | Subscribe các topic khớp regex |
| `topicPartitions` | Gán topic/partition thủ công, có thể kèm initial offset |
| `containerFactory` | Chọn bean `KafkaListenerContainerFactory` |
| `clientIdPrefix` | Prefix cho Kafka client ID |
| `concurrency` | Override concurrency của container factory |
| `autoStartup` | Override việc container tự khởi động |
| `properties` | Override một số consumer properties cho listener |
| `batch` | Chọn record hay batch listener trên method |
| `filter` | Chọn `RecordFilterStrategy` riêng |
| `info` | Đưa thông tin tĩnh vào header `KafkaHeaders.LISTENER_INFO` |
| `containerPostProcessor` | Tùy biến container sau khi tạo |
| `ackMode` | Override acknowledgment mode của factory ở phiên bản hỗ trợ |

Không phải mọi thuộc tính đều có trong mọi phiên bản. Các mốc bên dưới giúp xác định lúc nào một cấu hình có thể được dùng.

## 3. Timeline các thay đổi đáng chú ý

| Phiên bản | Thay đổi liên quan đến listener |
|---|---|
| 2.0 | `id` được dùng làm `group.id` mặc định nếu không khai báo `groupId`; `idIsGroup=false` khôi phục cách lấy group ID từ consumer factory; bổ sung `errorHandler` ở cấp listener |
| 2.1.1 | Bổ sung `clientIdPrefix` |
| 2.1.2 | SpEL hỗ trợ pseudo bean `__listener` và thuộc tính `beanRef` để đổi tên token |
| 2.2 | Annotation có thể override `concurrency` và `autoStartup`; hỗ trợ `@KafkaListener` làm meta-annotation |
| 2.2.4 | Bổ sung `properties` để override consumer properties theo listener |
| 2.3.5 | Bổ sung `splitIterables` để điều khiển cách trả về Iterable trong request-reply |
| 2.5 | Có thể nhận `ConsumerRecordMetadata` thay vì nhiều header rời; header received key không còn được thêm khi key null |
| 2.5.5 | `@PartitionOffset` hỗ trợ wildcard `*` cho tất cả partition được khai báo |
| 2.6.4 | `@TopicPartition` hỗ trợ khai báo partition theo danh sách/range |
| 2.7.1 | Bổ sung `contentTypeConverter` |
| 2.8 | Bổ sung `batch` để chọn batch listener ngay trên method |
| 2.8.4 | Bổ sung `filter` và `info` |
| 3.1 | Bổ sung `containerPostProcessor` |
| 3.2 | `@PartitionOffset` hỗ trợ `seekPosition`; listener hỗ trợ kiểu trả về bất đồng bộ như `CompletableFuture`, `Mono` và Kotlin suspend |
| 4.1 | Bổ sung `ackMode` để override acknowledgment mode trực tiếp trên annotation |

Các mốc này là những thay đổi tiêu biểu có ảnh hưởng tới code ứng dụng. Khi nâng cấp, luôn đối chiếu Javadoc và change history đúng version đang dùng; không suy luận rằng một thuộc tính mới trong tài liệu 4.x đã tồn tại trong 2.x hoặc 3.x.

## 4. Thay đổi quan trọng của id và groupId từ 2.0

Trước Spring Kafka 2.0, `id` chủ yếu định danh endpoint/container. Từ 2.0, nếu khai báo `id` và không khai báo `groupId`, giá trị `id` cũng được dùng làm Kafka consumer `group.id`, ghi đè group ID cấu hình trong consumer factory.

Ví dụ:

~~~java
@KafkaListener(
    id = "billingOrders",
    topics = "commerce.order.created"
)
public void listen(OrderCreated event) {
    billingService.process(event);
}
~~~

Với hành vi từ 2.0, consumer group sẽ là `billingOrders` nếu không có `groupId` riêng.

Nếu muốn giữ group ID từ consumer factory, có thể dùng `idIsGroup = false`:

~~~java
@KafkaListener(
    id = "billingOrders",
    idIsGroup = false,
    topics = "commerce.order.created"
)
public void listen(OrderCreated event) {
    billingService.process(event);
}
~~~

Cách rõ ràng hơn khi ứng dụng cần group ID cố định là khai báo cả hai:

~~~java
@KafkaListener(
    id = "billingOrdersListener",
    groupId = "billing-service",
    topics = "commerce.order.created"
)
public void listen(OrderCreated event) {
    billingService.process(event);
}
~~~

Phân biệt:

- `id` là định danh listener container trong Spring.
- `groupId` là danh tính consumer group ở Kafka.
- `idIsGroup` quyết định quan hệ mặc định giữa hai giá trị.

Khi nâng cấp từ phiên bản cũ lên 2.x, hãy kiểm tra những listener chỉ khai báo `id` nhưng dựa vào `spring.kafka.consumer.group-id` hoặc `ConsumerFactory` để lấy group ID. Nếu không rà soát, consumer có thể chuyển sang group mới và bắt đầu dùng offset riêng.

## 5. clientIdPrefix và concurrency

Từ 2.1.1, có thể đặt client ID prefix ngay trên annotation:

~~~java
@KafkaListener(
    id = "ordersListener",
    groupId = "billing-service",
    clientIdPrefix = "billing-orders",
    topics = "commerce.order.created",
    concurrency = "3"
)
public void listen(OrderCreated event) {
    billingService.process(event);
}
~~~

Khi concurrency lớn hơn một, Spring thêm hậu tố để tạo client ID riêng cho từng consumer container, ví dụ `billing-orders-0`, `billing-orders-1`.

`concurrency` có từ 2.2 và override giá trị trên factory. Giá trị có thể là literal, property placeholder hoặc SpEL:

~~~java
@KafkaListener(
    id = "ordersListener",
    topics = "commerce.order.created",
    concurrency = "${app.kafka.orders.concurrency:3}"
)
public void listen(OrderCreated event) {
    billingService.process(event);
}
~~~

Số consumer hữu ích vẫn bị giới hạn bởi số partition được gán. Tăng concurrency không tự làm một partition được nhiều consumer trong cùng group xử lý song song.

## 6. autoStartup và thời điểm khởi động

`autoStartup` được bổ sung để override cấu hình factory từ phiên bản 2.2:

~~~java
@KafkaListener(
    id = "ordersListener",
    topics = "commerce.order.created",
    autoStartup = "${app.kafka.orders.auto-startup:true}"
)
public void listen(OrderCreated event) {
    billingService.process(event);
}
~~~

Giá trị này được xét trong quá trình khởi tạo application context. Nó không phải công tắc runtime để bật/tắt listener sau khi ứng dụng đã chạy. Với thao tác runtime, dùng `KafkaListenerEndpointRegistry` để lấy container rồi gọi `start()` hoặc `stop()`.

Một chi tiết cần chú ý: endpoint đăng ký sau khi application context đã refresh có thể được start ngay bất kể `autoStartup`, trừ khi thay đổi hành vi `alwaysStartAfterRefresh` của registry. Đừng dùng `autoStartup=false` như một bảo đảm rằng mọi endpoint được đăng ký muộn sẽ luôn dừng.

## 7. Placeholder, SpEL và pseudo bean __listener

Phần lớn thuộc tính annotation hỗ trợ property placeholder hoặc SpEL:

~~~java
@KafkaListener(
    id = "ordersListener",
    topics = "${app.kafka.orders.topic}",
    groupId = "${app.kafka.orders.group}",
    concurrency = "${app.kafka.orders.concurrency:2}"
)
public void listen(OrderCreated event) {
    billingService.process(event);
}
~~~

Từ 2.1.2, SpEL hỗ trợ pseudo bean `__listener`, trỏ tới chính bean đang khai báo listener:

~~~java
@Component
public class TenantOrderListener {

    private final String topic;

    public TenantOrderListener(
            @Value("${app.kafka.tenant-topic}") String topic) {
        this.topic = topic;
    }

    @KafkaListener(
        topics = "#{__listener.topic}",
        groupId = "#{__listener.topic}.billing"
    )
    public void listen(OrderCreated event) {
        billingService.process(event);
    }

    public String getTopic() {
        return topic;
    }
}
~~~

Nếu ứng dụng có bean thực sự tên `__listener`, có thể đổi pseudo bean token bằng thuộc tính `beanRef`:

~~~java
@KafkaListener(
    beanRef = "__current",
    topics = "#{__current.topic}"
)
~~~

Dùng placeholder cho cấu hình đơn giản, SpEL khi cần biểu thức động. Không đưa logic nghiệp vụ phức tạp vào annotation; việc đó làm cấu hình khó kiểm thử và khó quan sát.

## 8. properties chỉ override consumer properties phù hợp

Từ 2.2.4, `properties` cho phép override một số Kafka consumer properties ở cấp listener:

~~~java
@KafkaListener(
    id = "slowOrdersListener",
    groupId = "billing-service",
    topics = "commerce.order.created",
    properties = {
        "max.poll.interval.ms=60000",
        "max.poll.records=100"
    }
)
public void listen(OrderCreated event) {
    billingService.process(event);
}
~~~

Các property trong annotation override property cùng tên từ consumer factory nếu factory hỗ trợ property override. Tuy nhiên, không đặt `group.id` hoặc `client.id` trong `properties`; các giá trị này bị bỏ qua. Dùng `groupId` và `clientIdPrefix` tương ứng.

Không nên lặp lại toàn bộ consumer configuration trên từng listener. Giữ cấu hình chung ở factory và chỉ override những giá trị thực sự khác biệt.

## 9. topics, topicPattern và topicPartitions

Ba cách subscription là loại trừ lẫn nhau. Một listener phải chọn đúng một cách.

### 9.1. Subscribe theo topic

~~~java
@KafkaListener(
    id = "ordersListener",
    topics = {
        "commerce.order.created",
        "commerce.order.cancelled"
    }
)
public void listen(OrderEvent event) {
    orderService.process(event);
}
~~~

Kafka group coordinator phân phối partition cho consumer group.

### 9.2. Subscribe theo regex

~~~java
@KafkaListener(
    id = "tenantEventsListener",
    topicPattern = "^tenant\\..*\\.events$"
)
public void listen(TenantEvent event) {
    tenantService.process(event);
}
~~~

Pattern hữu ích khi topic được tạo động theo quy tắc tên. Kafka client định kỳ cập nhật metadata và subscription sẽ nhận các topic khớp pattern.

### 9.3. Gán partition thủ công

~~~java
@KafkaListener(
    id = "ordersPartitionListener",
    topicPartitions = @TopicPartition(
        topic = "commerce.order.created",
        partitions = { "0", "1" }
    )
)
public void listen(ConsumerRecord<String, OrderCreated> record) {
    orderService.process(record.value());
}
~~~

Với manual assignment, ứng dụng tự quyết định partition mà listener nhận. Không dùng đồng thời `topics` hoặc `topicPattern` với `topicPartitions`.

Từ 2.5.5, wildcard `*` trong `@PartitionOffset` có thể áp dụng initial offset cho tất cả partition được khai báo. Từ 2.6.4, có thể khai báo danh sách hoặc range như `0-5,7,10-12`. Từ 3.2, `@PartitionOffset` hỗ trợ `seekPosition` với các giá trị như `BEGINNING`, `END` và `TIMESTAMP`.

Ví dụ seek theo timestamp:

~~~java
@KafkaListener(
    id = "ordersFromTimestamp",
    topicPartitions = @TopicPartition(
        topic = "commerce.order.created",
        partitionOffsets = {
            @PartitionOffset(
                partition = "0",
                initialOffset = "1735689600000",
                seekPosition = "TIMESTAMP"
            )
        }
    )
)
public void listen(ConsumerRecord<String, OrderCreated> record) {
    orderService.process(record.value());
}
~~~

`initialOffset` mang ý nghĩa timestamp khi `seekPosition=TIMESTAMP`. Khi dùng `BEGINNING` hoặc `END`, offset số không còn được diễn giải như offset tuyệt đối. Cần kiểm thử rõ hành vi seek trước khi triển khai.

## 10. Method signature và metadata của record

Listener method có thể nhận payload đơn giản, `ConsumerRecord`, `Message<?>`, `Acknowledgment`, `Consumer<?, ?>` và các header được hỗ trợ.

Từ 2.5, có thể nhận `ConsumerRecordMetadata` thay cho nhiều header rời:

~~~java
@KafkaListener(
    topics = "commerce.order.created",
    groupId = "billing-service"
)
public void listen(
        OrderCreated event,
        ConsumerRecordMetadata metadata) {

    log.info(
        "topic={}, partition={}, offset={}",
        metadata.topic(),
        metadata.partition(),
        metadata.offset()
    );

    billingService.process(event);
}
~~~

`ConsumerRecordMetadata` chứa metadata của record nhưng không chứa key và value. Nếu cần raw record, dùng `ConsumerRecord<K,V>`.

Một thay đổi nhỏ từ 2.5: `KafkaHeaders.RECEIVED_KEY` không còn được thêm khi record có key null. Nếu method parameter nhận header này, nên để `required=false` hoặc dùng kiểu nullable phù hợp.

## 11. Meta-annotation và tái sử dụng cấu hình

Từ 2.2, có thể dùng `@KafkaListener` làm meta-annotation để tạo annotation riêng cho domain:

~~~java
@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
@KafkaListener(
    topics = "commerce.order.created",
    groupId = "billing-service"
)
public @interface BillingOrderListener {
}
~~~

Có thể dùng `@AliasFor` để cho phép caller tùy biến một số thuộc tính của annotation gốc:

~~~java
@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
@KafkaListener
public @interface DomainKafkaListener {

    @AliasFor(annotation = KafkaListener.class, attribute = "topics")
    String[] topics();

    @AliasFor(annotation = KafkaListener.class, attribute = "groupId")
    String groupId() default "";
}
~~~

Cách này hữu ích khi nhiều listener dùng chung convention về group, topic hoặc container. Hãy giữ meta-annotation đơn giản; tránh tạo một lớp annotation lồng nhau khiến người đọc không biết giá trị cuối cùng đến từ đâu.

## 12. Batch listener: thuộc tính batch từ 2.8

Trước 2.8, việc chọn record listener hay batch listener thường được cấu hình trên container factory. Từ 2.8, `batch` có thể override `batchListener` ngay trên method:

~~~java
@KafkaListener(
    id = "ordersBatchListener",
    topics = "commerce.order.created",
    containerFactory = "ordersListenerContainerFactory",
    batch = "true"
)
public void listen(List<OrderCreated> events) {
    billingService.processBatch(events);
}
~~~

Có thể dùng cùng một factory cho record listener và batch listener. Nếu `batch` không được khai báo, container factory quyết định.

Giá trị `batch` phải là literal `true` hoặc `false`; không hỗ trợ property placeholder hoặc SpEL vì loại listener phải xác định khi tạo endpoint. Method batch thường nhận `List<?>`, không nhận payload đơn như record listener.

Từ 2.9.6, factory có setter riêng cho `recordMessageConverter` và `batchMessageConverter`; trước đó một `messageConverter` dùng chung cho cả hai loại. Khi nâng cấp converter configuration, kiểm tra xem ứng dụng có đang dựa vào converter dùng chung hay không.

## 13. filter và info từ 2.8.4

`filter` cho phép listener chọn `RecordFilterStrategy` riêng, override filter trên factory:

~~~java
@KafkaListener(
    id = "priorityOrdersListener",
    topics = "commerce.order.created",
    filter = "priorityOrderFilter"
)
public void listen(OrderCreated event) {
    billingService.process(event);
}
~~~

`info` gắn thông tin tĩnh vào header `KafkaHeaders.LISTENER_INFO`:

~~~java
@KafkaListener(
    id = "ordersListener",
    topics = "commerce.order.created",
    info = "billing-order-consumer"
)
public void listen(
        OrderCreated event,
        @Header(KafkaHeaders.LISTENER_INFO) String listenerInfo) {
    log.debug("listenerInfo={}", listenerInfo);
    billingService.process(event);
}
~~~

Thông tin này có thể được dùng bởi `RecordInterceptor`, `RecordFilterStrategy` hoặc listener method. Header listener info sẽ bị loại bỏ khi tạo outbound record từ headers của input record, tránh vô tình truyền metadata nội bộ sang message khác.

## 14. contentTypeConverter và splitIterables

`contentTypeConverter` được bổ sung từ 2.7.1. Nó chỉ định bean `SmartMessageConverter` để phối hợp với header `MessageHeaders.CONTENT_TYPE` khi chuyển đổi payload sang kiểu method yêu cầu.

Ví dụ chọn converter:

~~~java
@KafkaListener(
    topics = "commerce.order.created",
    contentTypeConverter = "orderContentTypeConverter"
)
public void listen(OrderCreated event) {
    billingService.process(event);
}
~~~

`splitIterables` có từ 2.3.5 và liên quan tới listener có return value dùng để reply. Mặc định `true`, một `Iterable` được tách thành nhiều reply record. Đặt `false` để gửi toàn bộ Iterable như value của một reply record:

~~~java
@KafkaListener(
    topics = "commerce.order.lookup",
    splitIterables = "false"
)
@SendTo("commerce.order.lookup.replies")
public List<OrderSummary> lookup(OrderLookup request) {
    return orderService.findSummaries(request);
}
~~~

Chỉ thay đổi `splitIterables` khi contract reply yêu cầu một record chứa collection. Kiểm tra serializer/deserializer và consumer reply trước khi thay đổi hành vi.

## 15. errorHandler của annotation khác container error handler

Thuộc tính `errorHandler` trên `@KafkaListener` nhận tên bean `KafkaListenerErrorHandler`. Nó xử lý exception ở tầng message listener adapter.

~~~java
@Bean
public KafkaListenerErrorHandler orderListenerErrorHandler() {
    return (message, exception) -> {
        log.error("Listener failed for message {}", message, exception);
        throw exception;
    };
}

@KafkaListener(
    topics = "commerce.order.created",
    errorHandler = "orderListenerErrorHandler"
)
public void listen(OrderCreated event) {
    billingService.process(event);
}
~~~

Cần phân biệt:

- `KafkaListenerErrorHandler`: gắn trên annotation, ở tầng listener method/message adapter.
- `CommonErrorHandler`: cấu hình trên listener container factory, điều khiển retry, seek, recovery và xử lý lỗi ở tầng container.

Giá trị trả về của `KafkaListenerErrorHandler` thường bị bỏ qua; nó chỉ được dùng làm reply khi listener method có `@SendTo`. Handler có thể ném lại exception để container tiếp tục áp dụng error handling policy.

Không dùng `errorHandler` như tên thuộc tính để cấu hình `DefaultErrorHandler`. Nếu muốn retry/DLT ở container, cấu hình `CommonErrorHandler` trên factory theo đúng phiên bản Spring Kafka.

## 16. containerPostProcessor từ 3.1

`containerPostProcessor` cho phép chỉ định bean `ContainerPostProcessor` để tùy biến container sau khi container đã được tạo và cấu hình:

~~~java
@KafkaListener(
    id = "ordersListener",
    topics = "commerce.order.created",
    containerPostProcessor = "ordersContainerPostProcessor"
)
public void listen(OrderCreated event) {
    billingService.process(event);
}
~~~

Ví dụ bean:

~~~java
@Bean
public ContainerPostProcessor<String, OrderCreated,
        ConcurrentMessageListenerContainer<String, OrderCreated>>
        ordersContainerPostProcessor() {

    return container -> {
        container.getContainerProperties()
            .setShutdownTimeout(15_000L);
    };
}
~~~

`ContainerPostProcessor` áp dụng cho listener container hiện tại. Nó chạy sau `ContainerCustomizer` được cấu hình trên factory. Dùng nó khi chỉ một listener cần điều chỉnh riêng; dùng `ContainerCustomizer` khi muốn áp dụng chung cho tất cả container từ factory.

## 17. Kiểu trả về bất đồng bộ từ 3.2

Từ 3.2, `@KafkaListener` và `@KafkaHandler` hỗ trợ kiểu trả về bất đồng bộ như `CompletableFuture<?>`, `Mono<?>` và Kotlin suspend function.

~~~java
@KafkaListener(
    id = "asyncOrdersListener",
    topics = "commerce.order.created",
    groupId = "billing-service"
)
public CompletableFuture<Void> listen(OrderCreated event) {
    return billingService.processAsync(event);
}
~~~

Khi framework phát hiện asynchronous return type, acknowledgment mode được tự động đặt thành `MANUAL` và bật out-of-order commits; việc ack diễn ra khi async operation hoàn tất. Nếu future hoàn tất bằng lỗi, việc retry/recovery phụ thuộc container error handler.

Có ba điều cần chú ý:

1. Exception xảy ra trước khi tạo được future phải được xử lý và trả về một async result phù hợp; nếu không, container không thể theo dõi completion theo cơ chế async.
2. Các invocation có thể chạy đồng thời; side effect của record offset sau có thể hoàn tất trước record offset trước trên cùng partition.
3. Nếu cần thứ tự xử lý nghiêm ngặt, dùng listener đồng bộ hoặc thiết kế tuần tự hóa theo key. Nếu cần xử lý async, side effect phải idempotent và có cơ chế kiểm soát thứ tự phù hợp.

Ví dụ chuyển lỗi đồng bộ thành một future thất bại để container xử lý theo error handler:

~~~java
@KafkaListener(topics = "commerce.order.created")
public CompletableFuture<Void> listen(OrderCreated event) {
    try {
        return billingService.processAsync(event);
    } catch (RuntimeException exception) {
        return CompletableFuture.failedFuture(exception);
    }
}
~~~

Không chỉ đổi kiểu trả về method từ `void` sang `CompletableFuture` rồi giả định hành vi commit vẫn như listener đồng bộ.

## 18. ackMode trực tiếp trên annotation từ 4.1

Trước 4.1, muốn listener dùng acknowledgment mode khác factory thường phải tạo một container factory riêng. Từ 4.1, `ackMode` cho phép override trực tiếp:

~~~java
@KafkaListener(
    id = "manualOrdersListener",
    topics = "commerce.order.created",
    groupId = "billing-service",
    ackMode = "MANUAL"
)
public void listen(
        OrderCreated event,
        Acknowledgment acknowledgment) {

    billingService.process(event);
    acknowledgment.acknowledge();
}
~~~

`ackMode` là String tương ứng với tên enum `ContainerProperties.AckMode`, không phân biệt chữ hoa/thường. Có thể dùng property placeholder hoặc SpEL:

~~~java
@KafkaListener(
    id = "ordersListener",
    topics = "commerce.order.created",
    ackMode = "${app.kafka.orders.ack-mode:RECORD}"
)
public void listen(OrderCreated event) {
    billingService.process(event);
}
~~~

Thuộc tính này chỉ có từ Spring Kafka 4.1. Không dùng trong ứng dụng 3.x hoặc cũ hơn vì sẽ không compile. Khi dùng `MANUAL` hoặc `MANUAL_IMMEDIATE`, method signature có thể nhận `Acknowledgment`; với các mode khác, không nên kỳ vọng tham số này được cung cấp.

`ackMode` chỉ thay đổi acknowledgment behavior. Nó không tự tạo transaction, không làm side effect trong database và offset Kafka trở thành một transaction nguyên tử nếu chưa cấu hình transaction manager tương ứng.

## 19. containerGroup và thay đổi tương thích cũ

Thuộc tính `containerGroup` từng tạo bean collection chứa các listener container để điều khiển theo nhóm. Từ 2.7.3, các bean kiểu Collection cũ bị deprecated và được thay bằng bean `ContainerGroup` có tên `containerGroup + ".group"`; Collection bean cũ bị loại bỏ trong 2.8.

Nếu ứng dụng cũ inject trực tiếp `Collection<MessageListenerContainer>` bằng tên group, cần đổi sang `ContainerGroup` hoặc dùng `KafkaListenerEndpointRegistry` để quản lý container theo ID.

Không nhầm `containerGroup` với `groupId`: một bên là nhóm container trong Spring context, bên kia là Kafka consumer group.

## 20. Những thay đổi lân cận khi nâng cấp lên 3.x

Một số thay đổi không phải thuộc tính của `@KafkaListener` nhưng ảnh hưởng trực tiếp đến listener code.

### 20.1. KafkaHeaders constants

Trong 3.0, các constant đã deprecated từ 2.9 bị loại bỏ:

| Constant cũ | Constant thay thế |
|---|---|
| `KafkaHeaders.MESSAGE_KEY` | `KafkaHeaders.KEY` |
| `KafkaHeaders.PARTITION_ID` | `KafkaHeaders.PARTITION` |
| `KafkaHeaders.RECEIVED_MESSAGE_KEY` | `KafkaHeaders.RECEIVED_KEY` |
| `KafkaHeaders.RECEIVED_PARTITION_ID` | `KafkaHeaders.RECEIVED_PARTITION` |

Nếu method signature dùng `@Header` với các constant cũ, cập nhật import và tên constant trước khi nâng cấp.

### 20.2. KafkaTemplate future

Từ 3.0, future của `KafkaTemplate` và `ReplyingKafkaTemplate` chuyển từ `ListenableFuture` sang `CompletableFuture`. Listener thường gọi producer hoặc reply template có thể cần cập nhật callback và kiểu trả về.

### 20.3. Spring Kafka 4.0

4.0 nâng Kafka client lên 4.0 và loại bỏ hạ tầng ZooKeeper-based trong Kafka test framework; đây là thay đổi hệ sinh thái/test nhiều hơn là một lần viết lại `@KafkaListener`. Kiểm tra broker, embedded Kafka, dependency và test setup riêng khi nâng cấp major version.

## 21. Bảng chọn API theo phiên bản

| Nhu cầu | Phiên bản tối thiểu đáng chú ý |
|---|---|
| `id` làm group ID mặc định | 2.0 |
| `clientIdPrefix` | 2.1.1 |
| `__listener` trong SpEL | 2.1.2 |
| Override concurrency/autoStartup | 2.2 |
| Meta-annotation | 2.2 |
| Consumer `properties` per listener | 2.2.4 |
| `splitIterables` | 2.3.5 |
| `ConsumerRecordMetadata` | 2.5 |
| Wildcard initial offset | 2.5.5 |
| Partition range | 2.6.4 |
| `contentTypeConverter` | 2.7.1 |
| Method-level batch | 2.8 |
| `filter` và `info` | 2.8.4 |
| `containerPostProcessor` | 3.1 |
| Async return type | 3.2 |
| `seekPosition` trên `@PartitionOffset` | 3.2 |
| `ackMode` trên annotation | 4.1 |

Bảng này là mốc tối thiểu cho API được đề cập, không phải ma trận tương thích toàn bộ Spring Boot, Spring Framework và Kafka client.

## 22. Quy trình migration khi nâng cấp

Thực hiện nâng cấp theo thứ tự:

1. Ghi lại Spring Kafka, Spring Boot, Spring Framework và Kafka client version hiện tại.
2. Tìm tất cả `@KafkaListener`, `@KafkaHandler`, meta-annotation và custom annotation liên quan.
3. Kiểm tra listener chỉ có `id` để xác định group ID thực tế sau 2.0.
4. Kiểm tra `containerFactory`, `concurrency`, `autoStartup`, `properties` và `batch`.
5. Tìm constant `KafkaHeaders` đã deprecated/removed.
6. Kiểm tra method signature dùng header key/partition và nullable key.
7. Kiểm tra listener có return `CompletableFuture`, `Mono` hoặc dùng acknowledgment thủ công không.
8. Chỉ dùng `containerPostProcessor` từ 3.1 và `ackMode` từ 4.1.
9. Cập nhật test broker và test framework theo Kafka client version mới.
10. Chạy integration test với record cũ, record mới, batch, retry, DLT và transaction.
11. Theo dõi consumer group, committed offsets, lag và lỗi deserialization sau rollout.

Không nâng riêng Spring Kafka mà bỏ qua dependency alignment. Dùng Spring Boot dependency management/BOM phù hợp hoặc kiểm tra bảng tương thích chính thức trước khi override version.

## 23. Kiểm thử nâng cấp @KafkaListener

Nên có test cho từng nhóm thay đổi:

| Nhóm | Điều cần xác nhận |
|---|---|
| `id`/`groupId` | Listener tham gia đúng consumer group và giữ offset mong muốn |
| `topics`/`topicPattern` | Subscribe đúng topic và phát hiện topic mới theo pattern |
| `topicPartitions` | Assignment và initial offset đúng |
| `concurrency` | Số consumer và partition assignment đúng |
| `autoStartup` | Container có chạy đúng thời điểm |
| `batch` | Method nhận đúng kiểu payload list |
| `filter` | Record bị loại bỏ theo đúng strategy |
| `info` | Header listener info có mặt và không rò ra outbound |
| `ackMode` | Offset commit đúng theo mode |
| Async return | Ack chỉ sau completion; lỗi đi qua error handler |
| `containerPostProcessor` | Container riêng được customize sau factory customizer |
| Header migration | Method nhận đúng key, partition, topic và offset |
| Retry/DLT | Exception được phân loại, retry và recovery đúng policy |

Dùng EmbeddedKafka hoặc Testcontainers để kiểm tra với broker thực tế. Với async listener, dùng future/latch để chờ completion; không dùng `Thread.sleep()` cố định. Với group ID, kiểm tra committed offsets thay vì chỉ xác nhận method được gọi.

## 24. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Sau upgrade listener đọc offset khác | `id` trở thành `group.id` theo semantics 2.0 | Khai báo `groupId` rõ hoặc đặt `idIsGroup=false` |
| Annotation không compile | Dùng thuộc tính mới trên version cũ | Đối chiếu mốc version của thuộc tính |
| `Acknowledgment` null | Factory/listener không ở manual ack mode | Dùng manual mode phù hợp; 4.1 có thể override `ackMode` |
| `batch=true` nhưng method nhận payload đơn | Method signature không phù hợp batch listener | Nhận `List<?>` hoặc bỏ batch |
| `properties` không đổi group/client ID | Hai property này bị bỏ qua trong annotation `properties` | Dùng `groupId` và `clientIdPrefix` |
| Listener khởi động dù autoStartup false | Endpoint đăng ký sau context refresh | Kiểm tra registry lifecycle và thời điểm đăng ký |
| Async listener commit sớm hoặc sai thứ tự side effect | Chưa hiểu async acknowledgment/parallel completion | Dùng async contract đúng, idempotency và xử lý thứ tự |
| Không tìm thấy KafkaHeaders constant | Constant đã bị xóa trong 3.0 | Dùng constant thay thế |
| Filter không chạy với ConsumerRecords listener | Record filter không hỗ trợ dạng listener đó | Dùng `List<?>` nếu cần batch filtering |
| `containerPostProcessor` không tồn tại | Đang dùng trước 3.1 | Customize qua factory/ContainerCustomizer |
| `ackMode` không tồn tại | Đang dùng trước 4.1 | Tạo factory riêng và đặt ContainerProperties AckMode |

## 25. Checklist trước khi phát hành

- [ ] Đã xác định chính xác Spring Kafka version đích?
- [ ] Đã rà `id`, `groupId` và `idIsGroup`?
- [ ] Đã kiểm tra subscription chỉ chọn một trong `topics`, `topicPattern`, `topicPartitions`?
- [ ] Placeholder và SpEL có resolve đúng?
- [ ] `properties` không chứa `group.id` hoặc `client.id`?
- [ ] Batch method nhận đúng signature?
- [ ] `Acknowledgment` chỉ dùng khi ack mode hỗ trợ?
- [ ] Async listener đã xử lý completion, error và ordering?
- [ ] `filter`, `info`, `containerPostProcessor`, `ackMode` có sẵn ở version đang chạy?
- [ ] Đã thay KafkaHeaders constant bị xóa?
- [ ] Đã kiểm tra group ID và committed offsets sau nâng cấp?
- [ ] Đã kiểm thử retry, DLT, transaction và shutdown?
- [ ] Đã căn chỉnh Spring Boot, Spring Framework và Kafka client?
- [ ] Có kế hoạch rollback nếu consumer không đọc được record sau rollout?

## Kết luận

API `@KafkaListener` được mở rộng dần qua các phiên bản Spring Kafka. Những thay đổi có ảnh hưởng lớn nhất là quan hệ giữa `id` và `groupId` từ 2.0, override concurrency/autoStartup từ 2.2, per-listener properties từ 2.2.4, batch/filter/info trong 2.8, container post processor từ 3.1, asynchronous return và seek position từ 3.2, cùng `ackMode` trực tiếp trên annotation từ 4.1.

Khi nâng cấp, hãy xác định version đích rồi rà từng thuộc tính và method signature. Đặc biệt chú ý group ID vì nó quyết định offset namespace, async listener vì nó ảnh hưởng acknowledgment và thứ tự side effect, và `ackMode` vì nó chỉ có ở 4.1 trở lên. Giữ cấu hình chung trong container factory, chỉ override tại annotation khi listener thật sự có nhu cầu riêng, sau đó xác minh bằng integration test với Kafka broker và theo dõi committed offsets/consumer lag trong rollout.

## Tài liệu tham khảo

- Spring Kafka Reference — @KafkaListener Annotation: https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/listener-annotation.html
- Spring Kafka Reference — Change History: https://docs.spring.io/spring-kafka/reference/appendix/change-history.html
- Spring Kafka API — KafkaListener Javadoc: https://docs.spring.io/spring-kafka/docs/4.1.2/api/org/springframework/kafka/annotation/KafkaListener.html
- Spring Kafka Reference — Asynchronous @KafkaListener Return Types: https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/async-returns.html
