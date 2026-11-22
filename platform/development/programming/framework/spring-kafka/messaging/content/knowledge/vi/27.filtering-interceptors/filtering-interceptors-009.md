# Đo lường record bị loại

## 1. Vì sao cần đo record bị loại?

Trong consumer Spring Kafka, không phải record nào đọc được cũng cần chuyển đến listener. Ứng dụng có thể bỏ qua sự kiện trùng, sự kiện đã hết hạn, loại sự kiện không thuộc phạm vi xử lý hoặc phiên bản payload mà consumer không hỗ trợ. `RecordFilterStrategy` cho phép quyết định record nào bị loại trước khi gọi listener.

Nếu chỉ cấu hình filter mà không đo số liệu, nhóm vận hành không biết:

- Có bao nhiêu record đã được kiểm tra và bao nhiêu record bị loại?
- Record bị loại do duplicate, hết hạn hay không đúng loại sự kiện?
- Tỷ lệ record bị loại tăng đột biến ở topic hoặc listener nào?
- Filter có đang loại nhầm sự kiện hợp lệ sau khi producer thay đổi schema?
- Consumer lag giảm vì xử lý nhanh hơn hay vì filter đang loại phần lớn dữ liệu?
- Các record bị loại đã được acknowledge/commit offset theo chính sách mong muốn chưa?

Spring Kafka cung cấp hook `RecordFilterStrategy` để quyết định loại record, nhưng không tự định nghĩa một counter nghiệp vụ cho số record bị loại. Ứng dụng nên đo ngay tại filter boundary bằng Micrometer, sau đó kết hợp với consumer lag, listener throughput, error rate và log để hiểu đúng hành vi.

## 2. RecordFilterStrategy trả về gì?

`RecordFilterStrategy<K,V>` được listener adapter gọi trước khi chuyển record đến phương thức listener. Phương thức `filter()` trả về boolean:

- `true`: loại record, listener không nhận record đó.
- `false`: giữ record và chuyển tiếp đến listener.

Ví dụ một filter loại sự kiện đã hết hạn:

```java
@Component
public class ExpiredOrderFilter
        implements RecordFilterStrategy<String, OrderEvent> {

    @Override
    public boolean filter(ConsumerRecord<String, OrderEvent> record) {
        OrderEvent event = record.value();
        return event != null && event.expired();
    }
}
```

Filter chỉ quyết định record có được gọi vào listener hay không. Nó không xóa record khỏi Kafka log, không sửa payload và không tự gửi record sang DLT. Record vẫn nằm trong partition cho đến khi hết retention hoặc được xóa theo chính sách log compaction.

Với record listener, filter được áp dụng từng record. Với batch listener nhận `List<?>`, Spring Kafka có adapter batch và mặc định lọc từng record. Từ Spring Kafka 2.8, có thể override `filterBatch()` để đánh giá cả batch trong một lần gọi.

## 3. Đo số record được kiểm tra và bị loại

Một bộ số liệu cơ bản nên có ít nhất hai counter:

| Metric | Ý nghĩa |
|---|---|
| `app.kafka.records.examined` | Số record đi qua filter |
| `app.kafka.records.filtered` | Số record filter quyết định loại |

Từ hai counter có thể tính tỷ lệ bị loại:

\[
\text{Filter ratio} = \frac{\text{filtered}}{\text{examined}} \times 100\%
\]

Ví dụ trong một khoảng thời gian có 100.000 record đi qua filter và 8.000 record bị loại, filter ratio là 8%. Tỷ lệ này cần được tính trên cùng cửa sổ thời gian và cùng tập label.

Counter nên tăng đơn điệu. Hệ thống metrics như Prometheus có thể tính tốc độ tăng bằng `rate()` và tỷ lệ bằng phép chia hai rate. Không tạo một gauge bằng cách cộng dồn thủ công qua từng invocation nếu có thể dùng counter.

Hai counter này đo **số quyết định filter**, không nhất thiết là số record Kafka duy nhất. Nếu record bị đọc lại sau restart, rebalance hoặc do offset chưa commit, cùng một `topic-partition-offset` có thể đi qua filter nhiều lần và được đếm nhiều lần. Đây là hành vi đúng nếu mục tiêu là đo lượng công việc filter đã thực hiện. Nếu cần thống kê số record duy nhất, phải deduplicate theo record identity hoặc event ID ở một hệ thống lưu trữ riêng; không nên biến metric counter thành kho trạng thái dedupe.

## 4. Đếm record bị loại bằng Micrometer

Ví dụ sau đo record được kiểm tra và record bị loại theo một số lý do hữu hạn. Các tag `topic` và `reason` có tập giá trị được kiểm soát:

```java
@Component
public class OrderRecordFilter
        implements RecordFilterStrategy<String, OrderEvent> {

    private final Counter examined;
    private final MeterRegistry meterRegistry;

    public OrderRecordFilter(MeterRegistry meterRegistry) {
        this.meterRegistry = meterRegistry;
        this.examined = Counter.builder("app.kafka.records.examined")
                .tag("topic", "orders")
                .register(meterRegistry);
    }

    @Override
    public boolean filter(ConsumerRecord<String, OrderEvent> record) {
        examined.increment();

        String reason = discardReason(record);
        if (reason == null) {
            return false;
        }

        meterRegistry.counter(
                "app.kafka.records.filtered",
                "topic", record.topic(),
                "reason", reason).increment();

        return true;
    }

    private String discardReason(ConsumerRecord<String, OrderEvent> record) {
        OrderEvent event = record.value();
        if (event == null) {
            return "tombstone";
        }
        if (event.expired()) {
            return "expired";
        }
        if (!event.supportedVersion()) {
            return "unsupported_version";
        }
        return null;
    }
}
```

Trong ví dụ:

- `examined` tăng một lần cho mỗi record filter nhận.
- `filtered` tăng theo từng lý do loại.
- Record được giữ lại không làm tăng counter `filtered`.
- Listener không cần tự tăng counter vì filter đã đo tại đúng điểm quyết định.

Không dùng `eventId`, order ID, Kafka offset, correlation ID hoặc exception message làm tag. Mỗi giá trị riêng biệt sẽ tạo một time series mới và làm cardinality tăng nhanh. Các định danh đó phù hợp với log hoặc trace.

### Cấu hình filter trên listener container factory

```java
@Configuration
public class OrderKafkaConfiguration {

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
    ordersListenerFactory(
            ConsumerFactory<String, OrderEvent> consumerFactory,
            OrderRecordFilter orderRecordFilter) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();
        factory.setConsumerFactory(consumerFactory);
        factory.setRecordFilterStrategy(orderRecordFilter);
        return factory;
    }
}
```

Listener chỉ nhận record không bị loại:

```java
@KafkaListener(
        topics = "orders",
        groupId = "order-service",
        containerFactory = "ordersListenerFactory")
public void onOrder(OrderEvent event) {
    orderService.process(event);
}
```

`setAckDiscarded(true)` thể hiện rõ chính sách acknowledge cho record bị loại trong các listener/acknowledgment adapter có hỗ trợ. Cần chọn giá trị theo AckMode và yêu cầu redelivery; phần offset được giải thích ở mục riêng bên dưới.

Từ Spring Kafka 2.8.4, một endpoint có thể thay strategy mặc định của factory bằng thuộc tính `filter` trên `@KafkaListener`:

```java
@KafkaListener(
        id = "orders-expired-filter",
        topics = "orders",
        groupId = "order-service",
        filter = "expiredOrderFilter")
public void onOrder(OrderEvent event) {
    orderService.process(event);
}
```

Giá trị `expiredOrderFilter` là tên bean `RecordFilterStrategy`. Cách này hữu ích khi nhiều listener dùng chung factory nhưng có chính sách filter khác nhau.

## 5. Đếm lý do bị loại mà không tạo cardinality cao

Metric theo lý do giúp phát hiện thay đổi hành vi. Ví dụ:

| Reason | Ý nghĩa |
|---|---|
| `duplicate` | Event ID đã được xử lý trước đó |
| `expired` | Sự kiện đã quá thời hạn nghiệp vụ |
| `unsupported_version` | Consumer không hỗ trợ phiên bản event |
| `irrelevant_type` | Loại event không thuộc listener này |
| `tombstone` | Record có value null và được filter theo chính sách |

Các reason phải là enum hoặc danh sách cố định. Không dùng nội dung payload làm reason, ví dụ `invalid_customer_123`, vì mỗi record có thể tạo một tag khác nhau.

Nếu muốn đo nhiều lý do, có thể dùng enum:

```java
enum FilterReason {
    DUPLICATE,
    EXPIRED,
    UNSUPPORTED_VERSION,
    IRRELEVANT_TYPE,
    TOMBSTONE
}
```

Sau đó chuyển enum sang chuỗi ổn định, ví dụ `duplicate`, `expired`. Khi thêm lý do mới, cần cập nhật dashboard và alert tương ứng.

Tombstone trong compacted topic thường mang nghĩa xóa key khỏi state store. Không filter tombstone một cách tổng quát nếu consumer đang dựng bản sao trạng thái; bỏ qua tombstone có thể khiến dữ liệu cũ tiếp tục tồn tại ở hệ thống downstream.

## 6. Phân biệt record bị loại, record lỗi và record được recover

Không gộp mọi record không đến listener thành một chỉ số “dropped”. Chúng có nguyên nhân và cách xử lý khác nhau:

| Trạng thái | Thành phần thường đo | Ý nghĩa |
|---|---|---|
| Filtered/discarded | Counter trong `RecordFilterStrategy` | Filter chủ động loại trước khi listener xử lý |
| Listener failed | Error handler/RetryListener | Listener đã được gọi nhưng xử lý thất bại |
| Recovered/DLT | Recoverer hoặc DLT publish metric | Record lỗi đã được chuyển sang quy trình phục hồi |
| Deserialization failed | `ErrorHandlingDeserializer`/error handler | Byte không chuyển được thành key/value nên filter thông thường chưa nhận payload hợp lệ |
| Duplicate ignored in service | Metric trong service/inbox | Listener đã nhận record nhưng service quyết định không lặp side effect |
| Tombstone | Filter hoặc logic listener | Kafka record có value null, thường dùng trong compacted topic để biểu diễn xóa |

Filter chạy sau khi consumer đã deserialize key/value. Nếu JSON deserialize thất bại, `RecordFilterStrategy` không phải nơi đo lỗi đó; hãy đo riêng ở error handling/deserialization path.

Nếu listener nhận record rồi mới kiểm tra duplicate trong database, đó là logic idempotency ở tầng nghiệp vụ, không phải filter count. Cần có metric riêng để phân biệt hai trường hợp.

## 7. Đo batch filtering

Với batch listener nhận `List<ConsumerRecord<K,V>>`, `RecordFilterStrategy.filterBatch()` có thể lọc cả batch. Mặc định implementation gọi `filter()` cho từng record. Nếu override `filterBatch()`, hãy đo số record đầu vào và số record bị loại ngay trong phương thức đó.

Ví dụ:

```java
@Component
public class BatchOrderFilter
        implements RecordFilterStrategy<String, OrderEvent> {

    private final Counter examined;
    private final Counter filtered;

    public BatchOrderFilter(MeterRegistry registry) {
        this.examined = Counter.builder("app.kafka.records.examined")
                .tag("topic", "orders")
                .register(registry);
        this.filtered = Counter.builder("app.kafka.records.filtered")
                .tag("topic", "orders")
                .tag("reason", "expired_or_invalid")
                .register(registry);
    }

    @Override
    public boolean filter(ConsumerRecord<String, OrderEvent> record) {
        // Dùng cho record listener hoặc default filterBatch.
        boolean discard = shouldDiscard(record);
        examined.increment();
        if (discard) {
            filtered.increment();
        }
        return discard;
    }

    @Override
    public List<ConsumerRecord<String, OrderEvent>> filterBatch(
            List<ConsumerRecord<String, OrderEvent>> records) {

        List<ConsumerRecord<String, OrderEvent>> kept = new ArrayList<>();
        int discarded = 0;

        for (ConsumerRecord<String, OrderEvent> record : records) {
            examined.increment();
            if (shouldDiscard(record)) {
                discarded++;
            } else {
                kept.add(record);
            }
        }

        if (discarded > 0) {
            filtered.increment(discarded);
        }

        return kept;
    }

    private boolean shouldDiscard(ConsumerRecord<String, OrderEvent> record) {
        OrderEvent event = record.value();
        return event == null || event.expired() || !event.supportedVersion();
    }
}
```

Trong implementation này, `filterBatch()` tự đo từng record và không gọi `filter()` để tránh đếm hai lần. Nếu bỏ override `filterBatch()`, implementation mặc định sẽ gọi `filter()` từng record và counter trong `filter()` vẫn hoạt động.

Khi batch có nhiều loại lý do, hãy phân loại từng record và tăng counter theo reason thay vì gộp nếu dashboard cần phân tích chi tiết. Giữ tập reason hữu hạn.

### Batch rỗng sau khi lọc

Từ Spring Kafka 3.3, `RecordFilterStrategy` có `ignoreEmptyBatch()`. Mặc định trả về `false`, nghĩa là listener batch vẫn được gọi với danh sách rỗng nếu mọi record đã bị lọc.

Nếu không muốn gọi listener khi batch rỗng:

```java
@Override
public boolean ignoreEmptyBatch() {
    return true;
}
```

Khi `ignoreEmptyBatch()` trả về `true`, listener không được gọi nếu tất cả record trong batch bị loại; Spring Kafka vẫn thực hiện commit theo cơ chế container. Nếu trả về `false`, listener nhận danh sách rỗng và phải xử lý trường hợp đó an toàn.

Không tăng `batch.listener.invocations` như thể listener đã xử lý một batch có dữ liệu khi adapter bỏ qua empty batch. Có thể đo riêng `filtered_batches` nếu cần, nhưng metric record count vẫn phải dựa trên số record bị loại.

## 8. ConsumerRecords không hỗ trợ RecordFilterStrategy

`FilteringBatchMessageListenerAdapter` không thể lọc listener có tham số `ConsumerRecords<?, ?>` vì `ConsumerRecords` là immutable. Nếu `@KafkaListener` nhận `ConsumerRecords`, strategy trên factory bị bỏ qua và Spring Kafka ghi log cảnh báo.

Muốn dùng filter cho batch, hãy khai báo listener nhận `List<ConsumerRecord<K,V>>` hoặc payload list tương ứng. Nếu cần giữ `ConsumerRecords` để truy cập `partitions()` và `records(topicPartition)`, có thể tự lọc trong code listener, nhưng lúc đó ứng dụng phải tự quản lý metric và semantics xử lý; không phải filtering adapter của Spring Kafka.

## 9. Acknowledge record bị loại và ảnh hưởng offset

Filter loại record khỏi listener path, nhưng Kafka offset vẫn cần được tiến triển theo chính sách commit của consumer. `ackDiscarded` điều khiển việc adapter acknowledge record bị loại trong các listener hỗ trợ acknowledgment.

Ở Spring Kafka hiện hành (4.1.x), `ackDiscarded` mặc định là `false`. Có thể đặt rõ trên factory:

```java
factory.setAckDiscarded(true);
```

Ví dụ nếu listener dùng manual acknowledgment:

```java
factory.getContainerProperties().setAckMode(ContainerProperties.AckMode.MANUAL);
factory.setAckDiscarded(true);

@KafkaListener(
        topics = "orders",
        groupId = "order-service",
        containerFactory = "ordersListenerFactory")
public void onOrder(OrderEvent event, Acknowledgment acknowledgment) {
    orderService.process(event);
    acknowledgment.acknowledge();
}
```

Với record bị filter, listener không được gọi; adapter acknowledge record đó theo `ackDiscarded=true`. Với record được giữ, listener acknowledge sau khi xử lý nghiệp vụ thành công. Nếu listener ném exception trước khi acknowledge, error handler/container xử lý theo cấu hình.

Ý nghĩa khi chọn:

- Với record listener dùng acknowledging adapter và manual acknowledgment, `true` cho phép adapter acknowledge record bị loại; `false` để việc acknowledge theo luồng listener/container thông thường.
- Với batch listener, khi toàn bộ batch bị lọc, `true` làm adapter acknowledge batch và không gọi delegate; `false` chuyển danh sách rỗng cho delegate để listener tự quyết định acknowledge.
- `ackDiscarded` không phải counter và cũng không có nghĩa mọi offset của partition được commit ngay lập tức. Commit thực tế vẫn theo AckMode, transaction và thứ tự offset.

Với các AckMode tự động do container quản lý như `RECORD` hoặc `BATCH`, commit thực tế vẫn phụ thuộc `AckMode`, transaction và tiến độ các record trong partition. Không suy luận rằng counter `filtered` tăng đồng nghĩa offset đã commit.

Với batch listener, nếu toàn bộ batch bị loại, hành vi còn liên quan đến `ackDiscarded` và `ignoreEmptyBatch()`. `ignoreEmptyBatch()` điều khiển việc gọi listener với batch rỗng từ Spring Kafka 3.3; `ackDiscarded` điều khiển acknowledgment của batch bị loại trong adapter. Kiểm thử chính xác theo AckMode đang dùng, nhất là `MANUAL`/`MANUAL_IMMEDIATE`. Không acknowledge trước khi chắc chắn filter đã thực hiện đúng quyết định nghiệp vụ.

### Khi nào nên acknowledge record bị loại?

Hãy acknowledge khi:

- Filter đã xác định record chắc chắn không cần xử lý.
- Quy tắc loại record có tính ổn định và có thể giải thích.
- Không cần retry lại record sau restart hoặc rebalance.
- Nếu cần audit, metadata tối thiểu đã được ghi nhận ở nơi bền vững trước khi offset được commit.

Không nên acknowledge nếu:

- Quyết định filter phụ thuộc dịch vụ ngoài đang tạm thời lỗi.
- Không chắc record là duplicate hay chỉ chưa đồng bộ trạng thái dedupe.
- Hệ thống chưa lưu được thông tin cần thiết để điều tra record bị loại.
- Việc loại nhầm có thể làm mất dữ liệu nghiệp vụ quan trọng.

## 10. Filter và idempotent receiver

Một use case phổ biến của filter là loại event trùng. Spring Kafka không tự biết một event đã được xử lý ở database hay chưa; đây là trách nhiệm ứng dụng. `RecordFilterStrategy` có thể dùng để triển khai một phần của Idempotent Receiver pattern.

Ví dụ đơn giản:

```java
@Component
public class DuplicateOrderFilter
        implements RecordFilterStrategy<String, OrderEvent> {

    private final ProcessedEventRepository processedEvents;

    public DuplicateOrderFilter(ProcessedEventRepository processedEvents) {
        this.processedEvents = processedEvents;
    }

    @Override
    public boolean filter(ConsumerRecord<String, OrderEvent> record) {
        OrderEvent event = record.value();
        return event != null && processedEvents.existsByEventId(event.eventId());
    }
}
```

Ví dụ này minh họa cách kiểm tra; truy vấn database cho mọi record có thể ảnh hưởng throughput. Có thể dùng cache hoặc kho dedupe phù hợp, nhưng cache chỉ là tối ưu và không thay thế unique constraint bền vững.

Đặc biệt, không thực hiện quy trình “đánh dấu event đã xử lý” trong filter rồi mới để listener cập nhật nghiệp vụ bằng một transaction độc lập. Nếu ứng dụng crash giữa hai bước, event có thể bị đánh dấu đã xử lý nhưng side effect chưa xảy ra; lần đọc lại tiếp theo bị filter loại và dữ liệu bị mất.

Thiết kế an toàn hơn thường là thực hiện insert inbox/processed-event và side effect database trong cùng một DB transaction ở service listener. Filter chỉ nên bỏ qua event đã được xác nhận hoàn tất trước đó, hoặc dùng khi quy trình dedupe có trạng thái bền vững và atomic.

## 11. Phân biệt RecordFilterStrategy và RecordInterceptor

Hai extension point đều chạy quanh listener nhưng mục đích khác nhau:

| Thành phần | Mục đích | Cách biểu diễn bỏ qua |
|---|---|---|
| `RecordFilterStrategy` | Quyết định record có bị loại hay không | `filter(record)` trả `true` |
| `RecordInterceptor` | Quan sát/thay đổi record trước listener và nhận callback sau xử lý | `intercept()` có thể trả `null` để không chuyển record đến listener |

Nếu mục tiêu chính là đo record bị loại và điều khiển acknowledgment cho record đó, `RecordFilterStrategy` thường rõ ràng hơn. Nếu mục tiêu là thêm context, validate nhẹ, logging hoặc quan sát vòng đời record, `RecordInterceptor` phù hợp hơn.

Không đếm cả một record là filtered trong interceptor và filter nếu cùng một record đi qua cả hai hook; điều đó tạo double count. Chọn một điểm chịu trách nhiệm cho metric `filtered` và ghi rõ định nghĩa.

Interceptor cũng không thay thế error handler. Nếu interceptor ném exception, lỗi cần được xử lý theo error handling của container; nó không phải một filter decision bình thường.

## 12. Filter chạy ở đâu trong luồng consumer?

Với record listener, luồng tổng quát:

```text
KafkaConsumer.poll()
        |
        v
Deserialize key/value
        |
        v
RecordFilterStrategy
       / \
      /   \
   false   true
    |       |
    v       v
Listener  Discard/ack policy
    |       |
    v       v
AckMode / offset commit theo container
```

Điều này có một số hệ quả:

- Record bị loại vẫn đã được fetch từ broker, nên filter không tiết kiệm toàn bộ network/fetch cost.
- Deserialization đã xảy ra trước filter; filter không thể sửa JSON hỏng.
- Listener timer thường không phản ánh thời gian filter nếu listener không được gọi; hãy đo filter riêng.
- Filter logic chạy trên consumer thread; thao tác chậm như gọi HTTP hoặc truy vấn DB có thể làm tăng thời gian xử lý và consumer lag.
- Record bị loại không tự động được chuyển sang DLT. Nếu cần quarantine, filter phải ghi/publish có chủ đích và chỉ acknowledge sau khi hành động đó hoàn tất theo semantics đã chọn.

## 13. Theo dõi tỷ lệ filter và cảnh báo bất thường

Một số biểu đồ hữu ích:

| Biểu đồ | Mục tiêu |
|---|---|
| Filtered records per second | Quan sát lưu lượng record bị loại |
| Examined vs filtered | So sánh tổng record qua filter và số bị loại |
| Filter ratio by reason | Phát hiện một lý do loại tăng bất thường |
| Filter ratio by topic/listener | Tìm listener hoặc topic có chính sách khác thường |
| Consumer lag cùng filter rate | Phân biệt giảm lag do throughput hay do bỏ qua nhiều record |
| Filter execution duration | Phát hiện filter logic chậm |

Có thể tính filter ratio trong Prometheus từ counter đã export. Ví dụ nếu metric Micrometer được export dưới tên tương ứng:

```promql
sum(rate(app_kafka_records_filtered_total[5m]))
/
clamp_min(sum(rate(app_kafka_records_examined_total[5m])), 1)
```

Để so sánh theo topic hoặc reason, giữ cùng label set ở tử và mẫu hoặc bỏ label không cần thiết bằng phép aggregation. Tên metric Prometheus thực tế có thể được chuẩn hóa từ tên Micrometer; hãy kiểm tra `/actuator/prometheus` trước khi viết dashboard.

Không đặt alert chỉ vì filter ratio khác 0. Một số topic có thể chủ động chứa event mà consumer không quan tâm. Alert nên dựa trên baseline, tỷ lệ bất thường, reason cụ thể và tác động nghiệp vụ.

## 14. Đo thời gian thực thi filter

Nếu filter thực hiện logic phức tạp, nên đo duration để phát hiện việc filter trở thành bottleneck:

```java
@Component
public class TimedOrderFilter
        implements RecordFilterStrategy<String, OrderEvent> {

    private final Timer filterTimer;

    public TimedOrderFilter(MeterRegistry registry) {
        this.filterTimer = Timer.builder("app.kafka.filter.duration")
                .tag("listener", "orders")
                .register(registry);
    }

    @Override
    public boolean filter(ConsumerRecord<String, OrderEvent> record) {
        return filterTimer.record(() -> shouldDiscard(record));
    }

    private boolean shouldDiscard(ConsumerRecord<String, OrderEvent> record) {
        OrderEvent event = record.value();
        return event == null || event.expired();
    }
}
```

Timer ghi nhận số lần gọi và thời gian thực thi. Có thể theo dõi p95/p99 để biết filter có chậm hơn kỳ vọng hay không. Tránh ghi tag theo event ID hoặc key.

Nếu filter gọi database, đo riêng thời gian lookup và tỷ lệ lỗi dependency. Không nên bắt exception từ database rồi trả `true` để loại record; lỗi dependency tạm thời có thể khiến record hợp lệ bị bỏ qua vĩnh viễn. Hãy ném exception để error handler xử lý retry hoặc thiết kế fallback an toàn.

## 15. Kiểm thử số liệu record bị loại

Kiểm thử cần xác nhận cả quyết định filter, counter và offset:

1. **Record được giữ:** filter trả `false`, `examined` tăng 1, `filtered` không tăng và listener được gọi.
2. **Record bị loại:** filter trả `true`, `examined` và `filtered` tăng đúng 1, listener không được gọi.
3. **Lý do khác nhau:** duplicate, expired và unsupported version tăng đúng counter reason.
4. **Batch có record hợp lệ và bị loại:** số examined bằng kích thước batch đầu vào; filtered bằng số record bị bỏ; listener nhận đúng danh sách còn lại.
5. **Batch bị lọc hết:** xác nhận `ignoreEmptyBatch()` quyết định listener có nhận list rỗng hay không theo phiên bản.
6. **ConsumerRecords listener:** xác nhận filter strategy không áp dụng và có cảnh báo; không kỳ vọng counter filter tăng.
7. **Manual acknowledgment:** kiểm tra `ackDiscarded` true/false và offset commit theo AckMode thực tế.
8. **Filter exception:** xác nhận exception đi qua error handler thay vì bị tính là một quyết định filtered bình thường.
9. **Deserialization failure:** xác nhận lỗi được đo ở error handling, không bị cộng vào filtered counter.
10. **Duplicate event:** xác nhận dedupe không đánh dấu event hoàn tất trước khi side effect nghiệp vụ commit.
11. **Metric cardinality:** xác nhận event ID, offset và key không xuất hiện trong metric tags.
12. **Filter latency:** kiểm tra Timer ghi đúng số lần và thời gian xử lý.

Nên dùng `spring-kafka-test` hoặc Testcontainers Kafka để xác minh listener, offset và filter adapter end-to-end. Unit test cho `RecordFilterStrategy` chỉ kiểm tra logic quyết định, không chứng minh container đã commit offset đúng cách.

## 16. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Listener vẫn nhận record tưởng đã filter | `filter()` trả `false`, factory chưa gắn strategy hoặc endpoint dùng factory khác | Kiểm tra return value, bean và `containerFactory` |
| Filter count lớn hơn số record dự kiến | Đếm cả lần `filter()` và `filterBatch()` hoặc listener retry/đọc lại | Chỉ đo một lần tại một boundary và xác định record có thể redeliver |
| Không thấy filter count cho batch | Override `filterBatch()` nhưng không tăng counter, hoặc listener dùng `ConsumerRecords` | Đếm trong `filterBatch()` và dùng `List<ConsumerRecord>` nếu muốn adapter filter |
| Listener nhận batch rỗng | `ignoreEmptyBatch()` mặc định false từ 3.3 | Trả true nếu muốn bỏ qua invocation khi batch bị lọc hết |
| Offset không tiến triển như mong đợi | `ackDiscarded`, AckMode hoặc manual acknowledgment chưa phù hợp | Kiểm tra cấu hình commit và test với broker |
| Filter ratio tăng đột biến | Producer đổi event version, duplicate tăng hoặc filter rule quá rộng | Phân tích theo reason và topic, đối chiếu release producer |
| Consumer lag giảm mạnh bất thường | Filter đang loại nhiều record | So sánh examined/filtered và xác minh nghiệp vụ |
| Filter làm consumer lag tăng | Logic filter gọi DB/HTTP chậm | Tối ưu lookup, cache có kiểm soát hoặc chuyển logic vào service phù hợp |
| Record hợp lệ bị loại khi database lỗi | Filter coi lỗi lookup là duplicate/invalid | Ném exception hoặc dùng fallback an toàn; không loại khi chưa có quyết định chắc chắn |
| Record bị mất sau khi filter duplicate | Đánh dấu processed trước khi side effect commit | Dùng inbox/unique constraint trong cùng DB transaction |

## 17. Quy trình triển khai đo lường

1. Xác định lý do record cần bị loại và bảo đảm đó là quyết định nghiệp vụ có thể giải thích.
2. Gắn `RecordFilterStrategy` vào đúng listener container factory hoặc chọn filter riêng bằng thuộc tính `filter` của `@KafkaListener`.
3. Tạo counter cho số record examined và filtered; thêm reason có cardinality thấp.
4. Với batch listener, xác định filter dùng `filter()` mặc định hay `filterBatch()` tùy chỉnh và tránh đếm hai lần.
5. Chọn `ackDiscarded` theo AckMode, transaction và chính sách redelivery; cấu hình tường minh.
6. Với batch, quyết định `ignoreEmptyBatch()` nếu dùng Spring Kafka 3.3 trở lên.
7. Không dùng `ConsumerRecords<?, ?>` nếu muốn filtering adapter tự lọc.
8. Đo filter duration nếu logic có truy cập dependency hoặc xử lý phức tạp.
9. Xây dashboard examined, filtered, ratio, reason, duration và consumer lag.
10. Kiểm thử filter, offset, batch rỗng, deserialization failure, duplicate và cardinality trước khi triển khai.

## 18. Tổng kết

- `RecordFilterStrategy.filter(record)` trả `true` để loại record và `false` để chuyển record đến listener.
- Filter không xóa record khỏi Kafka; nó chỉ ngăn listener nhận record và offset vẫn được quản lý theo AckMode/acknowledgment.
- Spring Kafka không cung cấp counter nghiệp vụ riêng cho record bị loại; dùng Micrometer counter tại filter boundary.
- Đo cả `examined` và `filtered`, sau đó tính filter ratio theo cùng topic/listener/reason.
- `filterBatch()` có từ Spring Kafka 2.8; mặc định gọi `filter()` từng record. Nếu override, tự đo số lượng và tránh đếm hai lần.
- `ignoreEmptyBatch()` có từ 3.3 và mặc định false; có thể bỏ qua listener invocation khi batch bị lọc hết.
- Filtering adapter không áp dụng cho listener nhận `ConsumerRecords<?, ?>` vì đối tượng này immutable.
- `ackDiscarded` mặc định false trong phiên bản hiện hành; chọn rõ theo AckMode và yêu cầu redelivery.
- Phân biệt filtered, listener failure, DLT recovery, deserialization failure và duplicate bị bỏ qua trong service.
- Dùng tag có cardinality thấp; đưa event ID, offset và correlation ID vào log/trace.
- Không đánh dấu event đã xử lý trước khi side effect nghiệp vụ commit; dùng inbox/idempotency bền vững cho duplicate.

Khi đo record bị loại ngay tại `RecordFilterStrategy`, nhóm vận hành có thể nhìn thấy filter ratio, lý do loại và thời gian thực thi. Kết hợp các số liệu đó với offset, consumer lag và trạng thái nghiệp vụ giúp phát hiện filter hoạt động sai trước khi việc bỏ qua record trở thành mất dữ liệu.

## Tài liệu tham khảo

- [Spring Kafka Reference — Filtering Messages](https://docs.spring.io/spring-kafka/reference/4.1/kafka/receiving-messages/filtering.html)
- [Spring Kafka API — RecordFilterStrategy](https://docs.spring.io/spring-kafka/api/org/springframework/kafka/listener/adapter/RecordFilterStrategy.html)
- [Spring Kafka API — AbstractKafkaListenerContainerFactory](https://docs.spring.io/spring-kafka/api/org/springframework/kafka/config/AbstractKafkaListenerContainerFactory.html)
- [Spring Boot Reference — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
