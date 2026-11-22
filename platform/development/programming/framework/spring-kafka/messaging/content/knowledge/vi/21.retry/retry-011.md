# Đo lường số lần retry

## 1. Vì sao cần đo số lần retry?

Trong ứng dụng Spring Kafka, một record có thể được listener xử lý nhiều lần nếu lần trước thất bại. Retry giúp khắc phục lỗi tạm thời, nhưng nếu không đo lường, đội vận hành khó biết consumer đang phục hồi tốt hay đang lặp lại cùng một lỗi.

Đo số lần retry giúp trả lời các câu hỏi:

- Có bao nhiêu lần xử lý thất bại và bao nhiêu lần giao lại do error handler?
- Record nào đang được thử lại nhiều lần?
- Nhóm exception nào tạo ra phần lớn retry?
- Bao nhiêu record đã được phục hồi thành công, bao nhiêu record hết retry và đi DLT?
- Retry đang làm consumer lag tăng hay làm dependency quá tải?
- Retry diễn ra trong listener container hay qua retry topic?

Spring Kafka cung cấp các hook để quan sát retry và delivery attempt. Ứng dụng có thể kết hợp các hook đó với Micrometer, log và tracing để xây dựng số liệu vận hành.

## 2. Phân biệt delivery attempt và retry attempt

Hai khái niệm này thường bị dùng thay thế cho nhau, nhưng cách đếm khác nhau:

- **Delivery attempt** là số thứ tự lần listener nhận và thử xử lý record trong một chuỗi retry được error handler theo dõi.
- **Retry attempt** là số lần thử lại sau lần giao ban đầu.

Lần giao đầu tiên đã là delivery attempt số `1`, nhưng chưa phải retry. Vì vậy:

\[
\text{Retry attempts đã thực hiện} = \max(0,\text{Delivery attempt}-1)
\]

Ví dụ:

| Lần listener nhận record | Delivery attempt | Retry đã diễn ra trước lần này |
|---:|---:|---:|
| Lần đầu | 1 | 0 |
| Lần giao lại thứ nhất | 2 | 1 |
| Lần giao lại thứ hai | 3 | 2 |
| Lần giao lại thứ ba | 4 | 3 |

Nếu cấu hình `FixedBackOff(1_000L, 2L)`, listener có thể được gọi tối đa ba lần: một lần ban đầu và hai lần retry. Delivery attempt cuối cùng là `3`; số retry tối đa là `2`.

Khi đặt tên metric, nên phân biệt `delivery_attempt`, `failed_delivery_total` và `retry_delivery_total`. Đừng đặt một metric tên `retry_count` nhưng lại cộng cả lần giao đầu tiên vào đó.

## 3. Những loại retry cần tách riêng khi đo

Trong một hệ thống Spring Kafka có thể tồn tại nhiều cơ chế thử lại. Chúng có phạm vi và cách đếm khác nhau:

| Cơ chế | Thành phần theo dõi | Ý nghĩa |
|---|---|---|
| Blocking retry | `DefaultErrorHandler` / `RetryListener` | Giao lại record trong luồng xử lý của listener container |
| Retry topic (non-blocking) | Header của Spring Kafka Retry Topic | Record được chuyển qua retry topic và được consumer retry xử lý ở lần giao sau |
| Transaction rollback retry | `DefaultAfterRollbackProcessor` | Record được giao lại sau khi transaction listener rollback |
| Producer send retry | Kafka producer metrics/configuration | Producer thử gửi lại do lỗi broker/network có thể phục hồi; không phải listener retry |
| Redelivery sau restart/rebalance | Offset, log và định danh record | Record có thể được đọc lại vì offset chưa commit; không nhất thiết là retry do error handler |
| Retry bên trong service nghiệp vụ | Metric của service hoặc thư viện retry | Ví dụ service gọi database/API nhiều lần trong một lần listener invocation |

Không cộng tất cả các loại trên thành một chỉ số duy nhất nếu mục tiêu là đo hiệu quả của `DefaultErrorHandler`. Nên có metric riêng cho blocking retry, retry topic, transaction rollback và producer send retry.

## 4. Theo dõi retry bằng RetryListener

`RetryListener` là hook của Spring Kafka để nhận thông báo khi delivery thất bại và khi recovery kết thúc. Có thể đăng ký một hoặc nhiều listener vào `DefaultErrorHandler`.

Các callback chính:

| Callback | Khi nào được gọi? | Thông tin nhận được |
|---|---|---|
| `failedDelivery(record, ex, deliveryAttempt)` | Một lần listener xử lý record thất bại | Record, exception và số thứ tự delivery attempt đã thất bại |
| `recovered(record, ex)` | Recoverer phục hồi record thành công sau khi retry hết | Record và exception ban đầu |
| `recoveryFailed(record, original, failure)` | Recoverer ném exception, recovery chưa hoàn tất | Record, lỗi xử lý ban đầu và lỗi recovery |

`RetryListener` được hỗ trợ từ Spring Kafka 2.7. Các callback nhận `ConsumerRecords` cho batch listener được bổ sung từ Spring Kafka 2.8.10. Kiểm tra phiên bản dependency trước khi triển khai callback batch.

### Đăng ký RetryListener

```java
@Bean
RetryListener orderRetryListener(MeterRegistry meterRegistry) {
    return new RetryListener() {

        @Override
        public void failedDelivery(
                ConsumerRecord<?, ?> record,
                Exception exception,
                int deliveryAttempt) {

            Counter.builder("app.kafka.listener.failed-delivery")
                    .tag("topic", record.topic())
                    .tag("exception", exception.getClass().getSimpleName())
                    .register(meterRegistry)
                    .increment();
        }

        @Override
        public void recovered(ConsumerRecord<?, ?> record, Exception exception) {
            Counter.builder("app.kafka.listener.recovered")
                    .tag("topic", record.topic())
                    .register(meterRegistry)
                    .increment();
        }

        @Override
        public void recoveryFailed(
                ConsumerRecord<?, ?> record,
                Exception original,
                Exception failure) {

            Counter.builder("app.kafka.listener.recovery-failed")
                    .tag("topic", record.topic())
                    .tag("exception", failure.getClass().getSimpleName())
                    .register(meterRegistry)
                    .increment();
        }
    };
}
```

Gắn listener vào error handler:

```java
@Bean
DefaultErrorHandler orderErrorHandler(
        KafkaTemplate<Object, Object> dltTemplate,
        RetryListener orderRetryListener) {

    var recoverer = new DeadLetterPublishingRecoverer(dltTemplate);
    var handler = new DefaultErrorHandler(
            recoverer,
            new FixedBackOff(1_000L, 2L));

    handler.setRetryListeners(orderRetryListener);
    return handler;
}
```

`failedDelivery` được gọi cho lần xử lý thất bại, bao gồm lần giao ban đầu nếu lần đó thất bại. Vì vậy metric trong ví dụ có tên `failed-delivery`, không phải `retry-delivery`. Callback cung cấp `deliveryAttempt` để phân biệt lần đầu và các lần giao lại.

`recovered` đo số record được recover thành công theo error handler; `recoveryFailed` đo trường hợp recoverer thất bại. Nếu chỉ đo số lần retry mà bỏ qua recovery, dashboard có thể không cho biết record đã được chuyển DLT hay vẫn mắc kẹt trong luồng.

## 5. Đếm retry delivery bằng deliveryAttempt

Để đếm lần listener thực sự được gọi lại, có thể dùng delivery attempt header. Header này cho biết số thứ tự delivery hiện tại. Khi `deliveryAttempt > 1`, record đã được giao lại ít nhất một lần trong chuỗi retry được error handler theo dõi.

Ví dụ listener ghi nhận retry delivery:

```java
@Component
public class OrderListener {

    private final OrderService orderService;
    private final MeterRegistry meterRegistry;

    public OrderListener(
            OrderService orderService,
            MeterRegistry meterRegistry) {
        this.orderService = orderService;
        this.meterRegistry = meterRegistry;
    }

    @KafkaListener(
            topics = "orders",
            groupId = "order-service",
            containerFactory = "ordersListenerFactory")
    public void onOrder(
            OrderCreated event,
            @Header(KafkaHeaders.DELIVERY_ATTEMPT) int deliveryAttempt) {

        if (deliveryAttempt > 1) {
            Counter.builder("app.kafka.listener.retry-delivery")
                    .tag("topic", "orders")
                    .register(meterRegistry)
                    .increment();
        }

        orderService.process(event);
    }
}
```

Metric này tăng khi listener bắt đầu một lần giao lại, kể cả lần giao lại đó xử lý thành công. Nó đo retry delivery đã quan sát được, khác với callback `failedDelivery`, vốn chỉ được gọi khi một lần xử lý thất bại.

Không nên cộng `deliveryAttempt` vào counter ở mọi lần listener gọi. Giá trị đó là số thứ tự hiện tại, không phải số retry mới phát sinh trong lần gọi. Nếu cộng 2, 3, 4 vào counter, số liệu sẽ bị phóng đại.

## 6. Bật KafkaHeaders.DELIVERY_ATTEMPT

Từ Spring Kafka 2.5, `DefaultErrorHandler` và `DefaultAfterRollbackProcessor` hỗ trợ delivery attempt header cho record listener. Tính năng này bị tắt mặc định để tránh chi phí nhỏ khi tra cứu trạng thái và thêm header cho từng record.

Bật trên container properties:

```java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
ordersListenerFactory(
        ConsumerFactory<String, OrderCreated> consumerFactory,
        DefaultErrorHandler orderErrorHandler) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();
    factory.setConsumerFactory(consumerFactory);
    factory.setCommonErrorHandler(orderErrorHandler);
    factory.getContainerProperties().setDeliveryAttemptHeader(true);
    return factory;
}
```

Listener có thể đọc header bằng `@Header`:

```java
@KafkaListener(
        topics = "orders",
        groupId = "order-service",
        containerFactory = "ordersListenerFactory")
public void onOrder(
        OrderCreated event,
        @Header(KafkaHeaders.DELIVERY_ATTEMPT) int deliveryAttempt) {
    log.info("orderId={}, deliveryAttempt={}",
            event.orderId(), deliveryAttempt);
    orderService.process(event);
}
```

Khi dùng `DefaultKafkaHeaderMapper` hoặc `SimpleKafkaHeaderMapper`, Spring có thể ánh xạ header thành `int` cho tham số listener. Nếu nhận raw `ConsumerRecord`, value của header là `byte[4]` và cần giải mã:

```java
Header header = record.headers().lastHeader(KafkaHeaders.DELIVERY_ATTEMPT);
if (header != null) {
    int deliveryAttempt = ByteBuffer.wrap(header.value()).getInt();
}
```

Header này áp dụng cho record listener. Không giả định nó có sẵn trong mọi batch listener hoặc mọi lần record được đọc lại sau restart/rebalance.

## 7. Delivery attempt header với batch listener

Trong batch listener, record được đưa vào một batch nên cách theo dõi delivery attempt khác với record listener. Từ Spring Kafka 3.3, có thể dùng `DeliveryAttemptAwareRetryListener` để thêm delivery attempt header vào từng `ConsumerRecord` trong batch:

```java
DefaultErrorHandler errorHandler =
        new DefaultErrorHandler(new FixedBackOff(1_000L, 2L));

errorHandler.setRetryListeners(new DeliveryAttemptAwareRetryListener());

ConcurrentKafkaListenerContainerFactory<String, OrderCreated> factory =
        new ConcurrentKafkaListenerContainerFactory<>();
factory.setConsumerFactory(consumerFactory);
factory.setBatchListener(true);
factory.setCommonErrorHandler(errorHandler);
```

Trong batch listener, đọc header từ từng record:

```java
@KafkaListener(
        topics = "orders",
        groupId = "order-service",
        containerFactory = "batchOrdersFactory")
public void onOrders(
        List<ConsumerRecord<String, OrderCreated>> records) {

    for (ConsumerRecord<String, OrderCreated> record : records) {
        Header header = record.headers()
                .lastHeader(KafkaHeaders.DELIVERY_ATTEMPT);

        int attempt = header == null
                ? 1
                : ByteBuffer.wrap(header.value()).getInt();

        log.info("partition={}, offset={}, deliveryAttempt={}",
                record.partition(), record.offset(), attempt);
        orderService.process(record.value());
    }
}
```

Tính năng này phụ thuộc Spring Kafka 3.3 trở lên. Với phiên bản cũ hơn, dùng callback batch của `RetryListener` nếu phiên bản hỗ trợ, hoặc tự theo dõi số lần xử lý bằng cơ chế ứng dụng có khóa record rõ ràng. Không đọc `KafkaHeaders.DELIVERY_ATTEMPT` từ batch rồi mặc định header luôn tồn tại.

## 8. Đo retry topic (non-blocking retry)

`@RetryableTopic` dùng retry topic để trì hoãn lần thử lại. Đây là cơ chế khác với blocking retry của `DefaultErrorHandler`, vì vậy không nên dùng delivery attempt header của blocking retry làm số liệu duy nhất.

Có thể đọc số lần thử non-blocking bằng header `RetryTopicHeaders.DEFAULT_HEADER_ATTEMPTS`:

```java
@RetryableTopic(
        attempts = "4",
        backoff = @Backoff(delay = 1_000, multiplier = 2.0))
@KafkaListener(topics = "orders", groupId = "order-service")
public void onOrder(
        OrderCreated event,
        @Header(
                name = RetryTopicHeaders.DEFAULT_HEADER_ATTEMPTS,
                required = false) Integer nonBlockingAttempts) {

    log.info("orderId={}, nonBlockingAttempts={}",
            event.orderId(), nonBlockingAttempts);
    orderService.process(event);
}
```

Header retry topic có thể chưa tồn tại ở lần giao ban đầu, vì vậy tham số cần nullable (`Integer`) và `required=false`. Không dùng primitive `int` cho header có thể vắng mặt.

Thuộc tính `attempts` của `@RetryableTopic` là tổng số lần thử trước khi chuyển DLT, bao gồm lần giao ban đầu. Với `attempts = "4"`, thông thường có một lần ban đầu và tối đa ba lần retry. Đây là cách đếm khác với `FixedBackOff`, nơi tham số `maxAttempts` là số lần retry sau lần ban đầu.

Từ Spring Kafka 3.0.10, `KafkaMessageHeaderAccessor` cung cấp cách đọc thuận tiện hơn:

```java
@RetryableTopic(
        attempts = "4",
        backoff = @Backoff(delay = 1_000, multiplier = 2.0))
@KafkaListener(topics = "orders", groupId = "order-service")
public void onOrder(
        OrderCreated event,
        KafkaMessageHeaderAccessor accessor) {

    int blockingAttempts = accessor.getBlockingRetryDeliveryAttempt();
    int nonBlockingAttempts = accessor.getNonBlockingRetryDeliveryAttempt();

    log.info("orderId={}, blockingAttempts={}, nonBlockingAttempts={}",
            event.orderId(), blockingAttempts, nonBlockingAttempts);
    orderService.process(event);
}
```

Accessor trả về `1` cho lần giao đầu tiên của non-blocking retry. `getBlockingRetryDeliveryAttempt()` ném `IllegalStateException` nếu blocking delivery attempt chưa được bật. Chỉ dùng accessor khi phiên bản Spring Kafka từ 3.0.10 trở lên.

Hai ví dụ `@RetryableTopic` ở trên dùng API Spring Kafka 2.7 đến 4.0: thuộc tính `backoff` cùng annotation `@Backoff` của Spring Retry. Từ Spring Kafka 4.1, Spring Retry được loại khỏi dependency và cú pháp đổi thành `backOff = @BackOff(...)` của Spring Kafka. Hãy dùng đúng cú pháp theo phiên bản đang khai báo trong dự án.

Không cộng blocking attempts với non-blocking attempts một cách máy móc. Chúng phản ánh hai cơ chế retry khác nhau; nếu ứng dụng kết hợp cả hai, dashboard nên có metric riêng và định nghĩa rõ tổng số delivery theo từng tầng.

## 9. RetryListener cho batch và recovery

`RetryListener` có overload nhận `ConsumerRecords<?, ?>` để theo dõi lỗi batch. Từ Spring Kafka 2.8.10, các callback batch được bổ sung. Ví dụ:

```java
RetryListener retryListener = new RetryListener() {

    @Override
    public void failedDelivery(
            ConsumerRecords<?, ?> records,
            Exception exception,
            int deliveryAttempt) {

        log.warn("Batch delivery failed: records={}, attempt={}, cause={}",
                records.count(), deliveryAttempt,
                exception.getClass().getSimpleName());
    }

    @Override
    public void recovered(ConsumerRecords<?, ?> records, Exception exception) {
        log.info("Batch recovered: records={}", records.count());
    }

    @Override
    public void recoveryFailed(
            ConsumerRecords<?, ?> records,
            Exception original,
            Exception failure) {

        log.error("Batch recovery failed: records={}", records.count(), failure);
    }
};

errorHandler.setRetryListeners(retryListener);
```

Callback batch cho biết lần xử lý batch thất bại, không phải lúc nào cũng cung cấp số lần retry chính xác riêng cho từng record. Nếu cần metric theo record, cần đọc delivery attempt header từng record (Spring Kafka 3.3 với `DeliveryAttemptAwareRetryListener`) hoặc tự ghi nhận identity và trạng thái theo cách phù hợp.

## 10. Thiết kế metric bằng Micrometer

Một bộ metric tối thiểu nên phân biệt thất bại, retry delivery, recovery thành công và recovery thất bại:

| Metric gợi ý | Loại | Khi tăng |
|---|---|---|
| `app.kafka.listener.failed-delivery` | Counter | Mỗi callback `RetryListener.failedDelivery` |
| `app.kafka.listener.retry-delivery` | Counter | Mỗi lần listener bắt đầu với delivery attempt lớn hơn 1 |
| `app.kafka.listener.recovered` | Counter | Callback `RetryListener.recovered` |
| `app.kafka.listener.recovery-failed` | Counter | Callback `RetryListener.recoveryFailed` |
| `app.kafka.retry-topic.delivery` | Counter | Mỗi lần nhận record từ retry topic, theo header retry topic |
| `app.kafka.listener.processing` | Timer | Thời gian thực thi logic listener, đo bằng observation/interceptor hoặc timer quanh service |

Các dimension phù hợp thường gồm:

- `listener` hoặc `group` với tập giá trị hữu hạn.
- `topic` nếu số topic được kiểm soát.
- `exception` theo tên class đã chuẩn hóa.
- `result` như `failed`, `recovered`, `recovery_failed`.
- `retry_type` như `blocking`, `non_blocking`, `transactional`.

Không dùng `eventId`, `correlationId`, offset, key hoặc exception message làm metric tag. Đây là các giá trị có cardinality rất cao, có thể làm hệ thống metrics tăng bộ nhớ và chi phí lưu trữ. Đưa các giá trị đó vào log hoặc trace để điều tra từng record.

Nếu dùng Spring Boot Actuator và Micrometer, các counter được đăng ký vào `MeterRegistry` có thể xuất qua endpoint metrics hoặc backend như Prometheus tùy cấu hình ứng dụng. Hãy đặt tên metric theo convention thống nhất và kiểm tra metric thực tế được export.

## 11. Định danh record để đối chiếu log và metric

Để điều tra một record retry nhiều lần, cần một định danh ổn định. Có thể dùng:

\[
\text{Record identity}=(\text{topic},\text{partition},\text{offset})
\]

Trong hệ thống nghiệp vụ, nên có thêm `eventId` duy nhất trong payload hoặc header. `topic-partition-offset` định danh record trong log Kafka; `eventId` liên kết cùng sự kiện qua các topic khác nhau, ví dụ topic chính, retry topic và DLT.

Ví dụ log có cấu trúc:

```java
@KafkaListener(
        topics = "orders",
        groupId = "order-service",
        containerFactory = "ordersListenerFactory")
public void onOrder(
        OrderCreated event,
        @Header(KafkaHeaders.RECEIVED_TOPIC) String topic,
        @Header(KafkaHeaders.RECEIVED_PARTITION) int partition,
        @Header(KafkaHeaders.OFFSET) long offset,
        @Header(KafkaHeaders.DELIVERY_ATTEMPT) int deliveryAttempt) {

    log.warn("Kafka delivery: eventId={}, topic={}, partition={}, offset={}, attempt={}",
            event.eventId(), topic, partition, offset, deliveryAttempt);
    orderService.process(event);
}
```

Khi record được chuyển sang retry topic hoặc DLT, topic/partition/offset có thể thay đổi. `eventId` giúp nối các lần xử lý xuyên topic. Nếu payload không deserialize được và chưa đọc được `eventId`, dùng topic, partition, offset và timestamp gốc để truy vết.

## 12. Retry count không giống consumer lag

Consumer lag đo khoảng cách offset giữa tiến độ đã commit và end offset. Nó không phải số lần retry.

Một consumer có thể có lag cao vì producer ghi nhanh hơn consumer, dù không có record nào retry. Ngược lại, một record có thể bị retry nhiều lần nhưng lag tổng thể vẫn thấp nếu lưu lượng topic nhỏ.

| Chỉ số | Trả lời câu hỏi |
|---|---|
| Retry delivery count | Listener đã nhận lại bao nhiêu lần do retry được theo dõi? |
| Failed delivery count | Bao nhiêu lần invocation xử lý thất bại? |
| Recovery count | Bao nhiêu record đã được recover sau khi retry hết? |
| DLT publish count | Bao nhiêu record được chuyển sang DLT? |
| Consumer lag | Group còn cách end offset bao xa? |
| Processing latency | Một lần xử lý record mất bao lâu? |
| Producer `record-retry-total` | Producer đã retry gửi bao nhiêu lần do lỗi gửi có thể retry? |

Để chẩn đoán, hãy quan sát các chỉ số cùng nhau. Lag tăng và retry rate tăng cùng lúc có thể chỉ ra dependency đang lỗi; lag tăng nhưng retry rate ổn định có thể do throughput, partition skew hoặc consumer thiếu tài nguyên.

## 13. Những lần giao lại không được tính như retry của error handler

Delivery attempt header và `RetryListener` theo dõi retry mà error handler quản lý. Chúng không phải bộ đếm toàn cục cho mọi lần Kafka giao lại record.

Ví dụ listener xử lý xong database nhưng process dừng trước khi commit offset. Sau restart, record có thể được giao lại từ committed offset cũ. Tương tự, rebalance có thể khiến record chưa commit được consumer member khác đọc lại. Đây là redelivery do semantics offset/commit, không nhất thiết đi qua chuỗi retry của `DefaultErrorHandler`.

Nếu cần đo duplicate processing toàn hệ thống, phải theo dõi thêm `eventId` đã xử lý hoặc idempotency key ở tầng nghiệp vụ. Không thể chỉ dựa vào `KafkaHeaders.DELIVERY_ATTEMPT` để phát hiện mọi duplicate.

Với transactional listener, `DefaultAfterRollbackProcessor` cũng kế thừa cơ chế retry listener. Có thể đăng ký cùng một `RetryListener` trên processor để quan sát failed delivery và recovery sau rollback; delivery attempt header cũng được hỗ trợ khi container bật thuộc tính tương ứng. Khi tổng hợp dashboard, vẫn nên gắn `retry_type=transactional` để phân biệt với `DefaultErrorHandler` của listener không transaction.

## 14. Những sai lầm khi đo số lần retry

| Sai lầm | Hậu quả | Cách làm đúng |
|---|---|---|
| Tính delivery attempt 1 là một lần retry | Retry count cao hơn thực tế một đơn vị | Retry count bằng delivery attempt trừ 1 |
| Chỉ đếm callback `failedDelivery` | Bỏ sót retry delivery đã thành công | Đếm invocation có delivery attempt lớn hơn 1 |
| Coi consumer lag là retry count | Chẩn đoán sai nguyên nhân chậm | Theo dõi lag và retry metric riêng |
| Gộp blocking và non-blocking retry | Không biết record đang retry ở đâu | Dùng metric riêng và phân biệt header tương ứng |
| Dùng delivery header cho batch ở mọi phiên bản | Header không tồn tại hoặc không được cập nhật như kỳ vọng | Kiểm tra version; từ 3.3 dùng `DeliveryAttemptAwareRetryListener` cho batch |
| Gắn event ID/offset vào metric tag | Cardinality tăng rất lớn | Đưa record identity vào log/trace |
| Coi recovery callback là DLT publish thành công trong mọi custom recoverer | Metric phản ánh sai hành động cuối | Xác định recoverer thực hiện gì và đo kết quả publish/lưu bền vững riêng nếu cần |
| Bỏ qua recovery failure | Record có thể tiếp tục bị giao lại nhưng dashboard báo đã xử lý | Theo dõi `recoveryFailed` và lỗi publish DLT |

## 15. Kiểm thử số liệu retry

Nên kiểm thử các trường hợp để xác nhận định nghĩa metric khớp với hành vi thực tế:

1. **Thành công lần đầu:** listener được gọi với delivery attempt 1; retry delivery counter không tăng.
2. **Thất bại một lần rồi thành công:** listener được gọi với attempt 1 và 2; retry delivery counter tăng 1; failed delivery callback ghi nhận lần thất bại đầu.
3. **Thất bại đến hết BackOff:** xác nhận số invocation, số callback `failedDelivery`, callback `recovered` và DLT/recovery result.
4. **Recovery thất bại:** xác nhận `recoveryFailed` tăng và record chưa bị báo là recovered.
5. **Non-retryable exception:** xác nhận không có retry delivery nhưng recovery vẫn được ghi nhận.
6. **Retry topic:** xác nhận header non-blocking vắng mặt ở lần đầu theo cách đọc raw header và được cập nhật ở lần giao retry; kiểm tra accessor nếu dùng phiên bản hỗ trợ.
7. **Batch listener:** xác nhận callback batch và delivery attempt theo từng record đúng với phiên bản Spring Kafka.
8. **Restart trước commit:** xác nhận record có thể được giao lại mà không nhất thiết tăng blocking retry attempt như một lần retry error handler.
9. **Metric cardinality:** xác nhận event ID và offset không trở thành tag.
10. **DLT:** xác nhận số liệu recovery phản ánh đúng kết quả publish và có thể truy vết record qua event ID.

Với `spring-kafka-test` hoặc Kafka test broker/container, có thể kiểm tra end-to-end cả callback, header, offset và DLT. Dùng `CountDownLatch`, Awaitility hoặc cơ chế chờ có timeout để test bất đồng bộ; tránh `Thread.sleep()` dài và không có điều kiện dừng.

## 16. Quy trình triển khai đo lường

1. Xác định ứng dụng đang dùng blocking retry, retry topic, transactional retry hay kết hợp.
2. Chọn chỉ số riêng: failed delivery, retry delivery, recovered, recovery failed và DLT publish.
3. Với record listener, bật `deliveryAttemptHeader` nếu cần đọc attempt trong listener.
4. Đăng ký `RetryListener` trên `DefaultErrorHandler` để ghi nhận failure và recovery callback.
5. Với retry topic, đọc `RetryTopicHeaders.DEFAULT_HEADER_ATTEMPTS` hoặc dùng `KafkaMessageHeaderAccessor` từ Spring Kafka 3.0.10.
6. Với batch listener, kiểm tra hỗ trợ theo version; dùng batch callbacks từ 2.8.10 và delivery header per-record từ 3.3.
7. Đưa counter/timer vào Micrometer với tag có cardinality thấp.
8. Ghi record identity vào log/trace để điều tra từng sự kiện.
9. Đối chiếu retry metric với consumer lag, processing latency, DLT rate và dependency health.
10. Kiểm thử lần đầu, retry thành công, retry hết, recovery lỗi và restart/rebalance trước khi triển khai.

## 17. Tổng kết

- Delivery attempt bắt đầu từ `1`; retry attempt là số lần giao lại sau lần đầu.
- `RetryListener` ghi nhận failed delivery, recovery thành công và recovery thất bại; batch callbacks có từ Spring Kafka 2.8.10.
- `KafkaHeaders.DELIVERY_ATTEMPT` được hỗ trợ từ 2.5 cho record listener và cần bật `deliveryAttemptHeader` trên container properties.
- Với batch listener, từ Spring Kafka 3.3 có thể dùng `DeliveryAttemptAwareRetryListener` để thêm header vào từng `ConsumerRecord`.
- Retry topic dùng header `RetryTopicHeaders.DEFAULT_HEADER_ATTEMPTS`; lần giao đầu có thể chưa có header raw, còn `KafkaMessageHeaderAccessor` từ 3.0.10 cung cấp giá trị non-blocking attempt chuẩn hóa.
- Đo riêng failed delivery, retry delivery, recovered, recovery failed và DLT publish.
- Consumer lag, producer send retry và redelivery sau restart/rebalance không đồng nghĩa với blocking retry.
- Dùng topic/partition/offset và event ID trong log/trace; tránh đưa định danh từng record vào metric tag.

Khi định nghĩa đúng delivery attempt và tách riêng các cơ chế retry, ứng dụng Spring Kafka có thể đo được số lần thử lại, tỷ lệ phục hồi và các record cần điều tra mà không nhầm retry với consumer lag hoặc redelivery do commit offset.

## Tài liệu tham khảo

- [Spring Kafka Reference — Handling Exceptions](https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html)
- [Spring Kafka Reference — Accessing Delivery Attempts](https://docs.spring.io/spring-kafka/reference/retrytopic/accessing-delivery-attempts.html)
- [Spring Kafka API — RetryListener](https://docs.spring.io/spring-kafka/api/org/springframework/kafka/listener/RetryListener.html)
- [Spring Kafka API — DeliveryAttemptAwareRetryListener](https://docs.spring.io/spring-kafka/api/org/springframework/kafka/listener/DeliveryAttemptAwareRetryListener.html)
- [Spring Kafka API — DefaultAfterRollbackProcessor](https://docs.spring.io/spring-kafka/api/org/springframework/kafka/listener/DefaultAfterRollbackProcessor.html)
- [Spring Kafka Reference — Retry Topic Features](https://docs.spring.io/spring-kafka/reference/retrytopic/features.html)
- [Spring Kafka Change History — Spring Kafka 4.1 retry API changes](https://docs.spring.io/spring-kafka/reference/appendix/change-history.html)
- [Apache Kafka Operations — Producer and Consumer Metrics](https://kafka.apache.org/40/operations/monitoring/)
