# Bean interceptor trong Spring Kafka

Interceptor là một điểm móc để quan sát hoặc điều chỉnh record trong quá trình producer gửi hoặc consumer nhận dữ liệu. Spring Kafka còn cung cấp interceptor ở tầng listener container để ứng dụng có thể thực hiện logic chung trước và sau khi listener xử lý record. Nhờ đó, các thao tác như gắn ngữ cảnh trace, ghi metric hoặc log metadata có thể được đặt ở một nơi thay vì lặp lại trong mọi phương thức `@KafkaListener`.

Tuy nhiên, có nhiều loại interceptor ở các tầng khác nhau. `RecordInterceptor` của Spring Kafka không giống `ProducerInterceptor` hay `ConsumerInterceptor` của Kafka client. Chọn đúng tầng giúp tránh đặt logic sai vòng đời, bỏ sót callback hoặc vô tình làm thay đổi hành vi commit offset.

## 1. Interceptor nằm ở đâu trong luồng Kafka?

Với consumer, record đi qua Kafka client, listener container và sau đó tới listener. Interceptor có thể được cài ở hai tầng chính:

- Kafka client `ConsumerInterceptor` nhận `ConsumerRecords` sau khi client poll và trước khi Spring listener xử lý.
- Spring Kafka `RecordInterceptor` hoặc `BatchInterceptor` được listener container gọi quanh lần gọi listener.

Với producer, `ProducerInterceptor` của Kafka client được gọi trong quá trình `KafkaProducer.send()` và khi broker trả acknowledgment. Interceptor này có thể được dùng cả khi producer được tạo thông qua `KafkaTemplate`, miễn là cấu hình interceptor được truyền tới producer factory.

```mermaid
flowchart TD
    A[Kafka topic] --> B[KafkaConsumer.poll]
    B --> C[ConsumerInterceptor.onConsume]
    C --> D[Spring Kafka listener container]
    D --> E[RecordInterceptor hoặc BatchInterceptor]
    E --> F[@KafkaListener]
    F --> G[success / failure / afterRecord]
    H[KafkaTemplate.send] --> I[KafkaProducer.send]
    I --> J[ProducerInterceptor.onSend]
    J --> K[Kafka broker]
    K --> L[ProducerInterceptor.onAcknowledgement]
```

Interceptor phù hợp với logic kỹ thuật dùng chung. Nó không thay thế listener, deserializer, validator nghiệp vụ hoặc error handler. Những thành phần đó có trách nhiệm riêng và cần được cấu hình ở đúng tầng.

## 2. `RecordInterceptor` của Spring Kafka

`RecordInterceptor<K, V>` cho phép ứng dụng can thiệp vào từng `ConsumerRecord` ngay trước khi listener được gọi. Interceptor nhận record và consumer hiện tại, sau đó trả về record để tiếp tục hoặc trả `null` để bỏ qua lần gọi listener cho record đó.

Ví dụ một interceptor ghi nhận metadata và theo dõi kết quả xử lý:

```java
@Component
public class OrderRecordInterceptor
        implements RecordInterceptor<String, OrderEvent> {

    private static final Logger log =
            LoggerFactory.getLogger(OrderRecordInterceptor.class);

    @Override
    public ConsumerRecord<String, OrderEvent> intercept(
            ConsumerRecord<String, OrderEvent> record,
            Consumer<String, OrderEvent> consumer) {

        log.debug("Receiving order event: topic={}, partition={}, offset={}, key={}",
                record.topic(), record.partition(), record.offset(), record.key());
        return record;
    }

    @Override
    public void success(
            ConsumerRecord<String, OrderEvent> record,
            Consumer<String, OrderEvent> consumer) {
        log.debug("Order event processed: eventId={}", record.value().eventId());
    }

    @Override
    public void failure(
            ConsumerRecord<String, OrderEvent> record,
            Exception exception,
            Consumer<String, OrderEvent> consumer) {

        log.warn("Order event failed: topic={}, partition={}, offset={}",
                record.topic(), record.partition(), record.offset(), exception);
    }
}
```

Gắn interceptor vào listener container factory:

```java
@Configuration
public class OrderKafkaConfiguration {

    @Bean
    public ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
            orderListenerFactory(
                    ConsumerFactory<String, OrderEvent> consumerFactory,
                    OrderRecordInterceptor interceptor) {

        ConcurrentKafkaListenerContainerFactory<String, OrderEvent> factory =
                new ConcurrentKafkaListenerContainerFactory<>();
        factory.setConsumerFactory(consumerFactory);
        factory.setRecordInterceptor(interceptor);
        return factory;
    }
}
```

Listener sử dụng factory này:

```java
@KafkaListener(
        topics = "orders",
        groupId = "order-service",
        containerFactory = "orderListenerFactory")
public void consume(OrderEvent event) {
    orderService.process(event);
}
```

Việc khai báo interceptor bằng `@Component` chỉ tạo Spring bean. Ứng dụng vẫn phải gắn bean vào factory bằng `setRecordInterceptor(...)` hoặc cơ chế cấu hình tương ứng; không nên giả định mọi bean có kiểu interceptor sẽ tự động được áp dụng cho tất cả listener container.

Các callback thường dùng:

| Callback | Thời điểm | Mục đích |
|---|---|---|
| `intercept(record, consumer)` | Trước khi listener xử lý record | Đọc metadata, bổ sung ngữ cảnh kỹ thuật hoặc trả record đã điều chỉnh. |
| `success(record, consumer)` | Sau khi listener xử lý thành công | Ghi metric hoặc log kết quả thành công. |
| `failure(record, exception, consumer)` | Khi listener xử lý phát sinh exception | Ghi nhận lỗi và ngữ cảnh record. |
| `afterRecord(record, consumer)` | Sau lần gọi listener, bất kể thành công hay thất bại | Dọn ngữ cảnh hoặc kết thúc đo thời gian. |

Các hook mặc định và chữ ký callback có thể khác giữa các phiên bản Spring Kafka. Khi dự án dùng phiên bản cũ, hãy đối chiếu interface của đúng phiên bản đang chạy trước khi triển khai.

## 3. Dùng `BatchInterceptor` cho batch listener

Nếu listener nhận cả `ConsumerRecords` hoặc danh sách record trong một lần poll, cần chọn interceptor dành cho batch. `BatchInterceptor<K, V>` nhận cả batch và consumer thay vì từng record riêng lẻ.

Ví dụ minh họa:

```java
@Component
public class OrderBatchInterceptor
        implements BatchInterceptor<String, OrderEvent> {

    @Override
    public ConsumerRecords<String, OrderEvent> intercept(
            ConsumerRecords<String, OrderEvent> records,
            Consumer<String, OrderEvent> consumer) {

        log.debug("Received batch with {} records", records.count());
        return records;
    }

    @Override
    public void success(
            ConsumerRecords<String, OrderEvent> records,
            Consumer<String, OrderEvent> consumer) {
        log.debug("Batch processed: {} records", records.count());
    }

    @Override
    public void failure(
            ConsumerRecords<String, OrderEvent> records,
            Exception exception,
            Consumer<String, OrderEvent> consumer) {
        log.warn("Batch processing failed: count={}", records.count(), exception);
    }
}
```

Gắn vào factory dành cho batch listener:

```java
factory.setBatchListener(true);
factory.setBatchInterceptor(batchInterceptor);
```

Không nên gắn interceptor record và batch tùy tiện vào cùng một listener factory. Hãy chọn loại listener và interceptor khớp nhau: `RecordInterceptor` cho record listener, `BatchInterceptor` cho batch listener. Điều này giúp callback nhận đúng đơn vị xử lý và tránh hiểu nhầm một lần gọi listener tương ứng với một record.

Với batch, một exception có thể làm cả batch hoặc một phần batch được retry tùy error handler và cách listener báo vị trí record lỗi. Interceptor nên ghi nhận batch metadata; không tự suy luận rằng toàn bộ record đã thành công chỉ vì một callback batch được gọi.

## 4. Phân biệt interceptor với filtering

Một mục đích thường gặp là bỏ qua record không cần xử lý. `RecordInterceptor` có thể trả `null` để không gọi listener cho record đó, nhưng nếu mục đích chính là lọc theo điều kiện nghiệp vụ đơn giản, `RecordFilterStrategy` diễn đạt ý định rõ hơn.

Ví dụ chỉ xử lý đơn hàng đang hoạt động:

```java
factory.setRecordFilterStrategy(record ->
        record.value() == null || record.value().isArchived());
```

Với `RecordFilterStrategy`, trả `true` nghĩa là loại record khỏi listener; trả `false` nghĩa là giữ lại để xử lý. Nếu dùng manual acknowledgment và muốn acknowledge record đã bị loại, có thể cấu hình `setAckDiscarded(true)` theo chính sách ack của container.

| Cơ chế | Điều kiện bỏ qua | Ý nghĩa |
|---|---|---|
| `RecordInterceptor` | `intercept(...)` trả `null` | Listener không được gọi cho record đó. Có thể dùng khi quyết định bỏ qua cần ngữ cảnh interceptor. |
| `RecordFilterStrategy` | `filter(record)` trả `true` | Record bị loại theo chính sách lọc được khai báo riêng. |
| `BatchInterceptor` | Can thiệp trên batch | Dùng cho logic trước/sau một lần gọi batch listener. |

Record bị bỏ qua vẫn cần được xử lý offset theo `AckMode` và cấu hình container. Đừng coi việc listener không được gọi là record tự động được xác nhận theo mọi chế độ. Kiểm tra hành vi `RECORD`, `BATCH`, `MANUAL` hoặc `MANUAL_IMMEDIATE`, đặc biệt khi dùng `ackDiscarded`.

Lọc record cũng có nghĩa dữ liệu đó không đi qua logic nghiệp vụ của listener. Chỉ loại record khi quyết định bỏ qua là có chủ đích, có thể giải thích và không làm mất sự kiện cần xử lý. Nếu record không hợp lệ cần được điều tra, hãy dùng error handler và DLT thay vì filter bỏ qua.

## 5. Kafka client `ProducerInterceptor`

`ProducerInterceptor<K, V>` thuộc Kafka client, được gọi khi producer gửi record và khi nhận acknowledgment. Nó có hai callback quan trọng:

- `onSend(record)` chạy trước khi record được gửi; có thể trả lại record đã điều chỉnh, ví dụ thêm header kỹ thuật.
- `onAcknowledgement(metadata, exception)` được gọi khi kết quả gửi được xác định, với metadata nếu thành công hoặc exception nếu thất bại.

Ví dụ:

```java
public class TraceProducerInterceptor
        implements ProducerInterceptor<String, OrderEvent> {

    @Override
    public ProducerRecord<String, OrderEvent> onSend(
            ProducerRecord<String, OrderEvent> record) {

        record.headers().add(new RecordHeader(
                "producer-service",
                "order-service".getBytes(StandardCharsets.UTF_8)));
        return record;
    }

    @Override
    public void onAcknowledgement(
            RecordMetadata metadata,
            Exception exception) {
        if (exception != null) {
            log.warn("Kafka send failed", exception);
        }
        else {
            log.debug("Kafka send acknowledged: topic={}, partition={}, offset={}",
                    metadata.topic(), metadata.partition(), metadata.offset());
        }
    }

    @Override
    public void close() {
    }

    @Override
    public void configure(Map<String, ?> configs) {
    }
}
```

Đăng ký interceptor qua producer properties:

```java
props.put(
        ProducerConfig.INTERCEPTOR_CLASSES_CONFIG,
        TraceProducerInterceptor.class.getName());
```

Nếu dùng Spring Boot, có thể truyền thuộc tính Kafka client trong `spring.kafka.producer.properties`:

```yaml
spring:
  kafka:
    producer:
      properties:
        "[interceptor.classes]": com.example.kafka.TraceProducerInterceptor
```

Kafka client tự khởi tạo interceptor theo cấu hình; đây không phải Spring bean được inject dependency tự động. Nếu interceptor cần cấu hình, dùng `configure(Map<String, ?>)` hoặc cơ chế factory riêng. Tránh giả định có thể inject trực tiếp Spring service vào Kafka client interceptor.

`onSend` và `onAcknowledgement` có thể được gọi từ các thread khác nhau. Interceptor cần thread-safe, không giữ state mutable dùng chung nếu không có đồng bộ phù hợp. Theo Kafka client contract, exception phát sinh từ interceptor được client bắt và ghi log; không dùng interceptor để thay thế xử lý lỗi gửi trong callback của `KafkaTemplate` hoặc producer listener.

## 6. Kafka client `ConsumerInterceptor`

`ConsumerInterceptor<K, V>` thuộc Kafka client và hoạt động quanh kết quả poll của consumer. `onConsume(records)` nhận `ConsumerRecords` trước khi Spring listener container chuyển tiếp dữ liệu; `onCommit(offsets)` được gọi khi consumer commit offset.

Ví dụ ghi nhận số record được poll:

```java
public class PollMetricsInterceptor
        implements ConsumerInterceptor<String, OrderEvent> {

    @Override
    public ConsumerRecords<String, OrderEvent> onConsume(
            ConsumerRecords<String, OrderEvent> records) {

        metrics.counter("kafka.consumer.polled.records").increment(records.count());
        return records;
    }

    @Override
    public void onCommit(
            Map<TopicPartition, OffsetAndMetadata> offsets) {
        log.debug("Consumer committed {} partition offsets", offsets.size());
    }

    @Override
    public void close() {
    }

    @Override
    public void configure(Map<String, ?> configs) {
    }
}
```

Đăng ký qua consumer properties:

```java
consumerProps.put(
        ConsumerConfig.INTERCEPTOR_CLASSES_CONFIG,
        PollMetricsInterceptor.class.getName());
```

Hoặc Spring Boot:

```yaml
spring:
  kafka:
    consumer:
      properties:
        "[interceptor.classes]": com.example.kafka.PollMetricsInterceptor
```

`ConsumerInterceptor` thấy dữ liệu ở tầng Kafka client, trước callback của Spring listener container. Nó phù hợp với metric poll hoặc quan sát commit ở cấp client. Nếu cần hook theo từng lần listener xử lý thành công/thất bại, `RecordInterceptor` phù hợp hơn vì có callback gắn trực tiếp với listener.

Không gọi `poll()`, `commitSync()`, `commitAsync()`, `seek()` hoặc thay đổi assignment từ interceptor. Những thao tác này có thể làm sai vòng đời consumer do container quản lý. Dùng API container, acknowledgment và error handler cho điều khiển offset hoặc retry.

## 7. Thread-safety và side effect

Interceptor thường được cấu hình trên factory dùng chung cho nhiều listener container hoặc producer. Khi concurrency lớn hơn một, nhiều consumer thread có thể gọi cùng một bean interceptor. Vì vậy, interceptor nên stateless hoặc dùng state thread-safe.

Một số nguyên tắc:

1. Không lưu record hiện tại trong field mutable dùng chung giữa các thread.
2. Dùng Micrometer counter/timer hoặc logger thread-safe thay vì tự xây bộ đếm không đồng bộ.
3. Không gọi database, HTTP service hoặc thao tác I/O chậm trong `intercept()`; việc đó kéo dài thời gian xử lý và làm tăng consumer lag.
4. Không thực hiện side effect nghiệp vụ trong callback interceptor. Record có thể được giao lại do retry, rebalance hoặc restart, khiến side effect chạy nhiều lần.
5. Không commit offset hoặc tự điều khiển poll trong interceptor của consumer do container quản lý.
6. Không làm thay đổi key, topic hoặc partition nếu không hiểu tác động đến routing và ordering.
7. Nếu thêm header, tránh ghi đè header correlation hoặc tracing do hệ thống khác quản lý; thống nhất tên header và encoding.

Nếu dùng transaction listener, interceptor được gọi trong luồng xử lý của container, nhưng side effect tới hệ thống ngoài Kafka không tự rollback khi Kafka transaction abort. Do đó, interceptor chỉ nên ghi nhận thông tin kỹ thuật hoặc chuẩn bị metadata không gây tác động nghiệp vụ.

## 8. Chọn interceptor theo nhu cầu

| Nhu cầu | Cơ chế nên xem xét |
|---|---|
| Ghi log/metric trước và sau mỗi listener record | Spring Kafka `RecordInterceptor` |
| Ghi log/metric cho một lần gọi batch listener | Spring Kafka `BatchInterceptor` |
| Loại record theo điều kiện đơn giản | `RecordFilterStrategy` |
| Thêm header hoặc quan sát send acknowledgment ở producer client | Kafka `ProducerInterceptor` |
| Quan sát kết quả poll hoặc commit ở consumer client | Kafka `ConsumerInterceptor` |
| Retry, recover hoặc chuyển DLT khi listener lỗi | Spring Kafka error handler |
| Kiểm tra dữ liệu nghiệp vụ và từ chối command | Validator hoặc logic trong service/listener |

Đừng dùng interceptor để nhồi toàn bộ logic dùng chung vào một nơi. Nếu cần xử lý nghiệp vụ, gọi service nghiệp vụ từ listener để luồng điều khiển và lỗi được thể hiện rõ. Nếu cần lọc, dùng filter strategy. Nếu cần retry, để exception truyền tới error handler.

## 9. Kiểm thử interceptor

Nên kiểm thử cả callback và tác động của interceptor tới listener/container:

- Khi `intercept()` trả record, listener nhận đúng record và xử lý bình thường.
- Khi `intercept()` trả `null`, listener không được gọi và offset được xử lý theo `AckMode` đã cấu hình.
- Khi listener thành công, callback `success` được gọi; khi listener ném exception, callback `failure` nhận exception tương ứng.
- Với batch listener, interceptor nhận đúng batch và callback phản ánh kết quả của lần gọi batch.
- `RecordFilterStrategy` trả `true` loại record; xác minh `ackDiscarded` theo chế độ acknowledgment đang dùng.
- `ProducerInterceptor` thêm header đúng và quan sát được acknowledgment thành công/thất bại.
- `ConsumerInterceptor` nhận đúng số record poll và callback commit không làm thay đổi offset.
- Khi concurrency tăng, interceptor không có race condition hoặc chia sẻ state sai giữa các thread.
- Khi retry/rebalance xảy ra, metric và log không tạo giả định rằng interceptor chỉ chạy một lần cho mỗi event.

Trong kiểm thử tích hợp, có thể dùng Embedded Kafka hoặc broker kiểm thử để gửi record thật qua listener container. Với callback đơn giản, unit test có thể tạo `ConsumerRecord` mẫu và gọi interceptor trực tiếp. Dù dùng cách nào, cần xác minh hành vi offset và retry ở container khi interceptor lọc record; chỉ kiểm tra giá trị trả về của hàm chưa đủ để chứng minh luồng consumer vận hành đúng.

Bean interceptor giúp tập trung logic kỹ thuật quanh luồng gửi/nhận Kafka. Chọn `RecordInterceptor` hoặc `BatchInterceptor` khi cần hook vào listener Spring Kafka, dùng `RecordFilterStrategy` khi cần lọc record, và dùng interceptor Kafka client khi cần quan sát ở tầng producer/consumer. Giữ interceptor nhẹ, thread-safe và không chứa side effect nghiệp vụ để luồng messaging vẫn dễ hiểu, có thể retry và vận hành tin cậy.
