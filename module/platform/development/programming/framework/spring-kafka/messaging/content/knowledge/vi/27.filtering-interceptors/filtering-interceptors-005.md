# Consumer interceptor

Consumer interceptor là thành phần chạy trên đường đi của record từ Kafka đến listener, cho phép quan sát, bổ sung metadata hoặc áp dụng logic chung trước/sau khi listener xử lý. Trong Spring Kafka, API thường dùng cho record listener là `RecordInterceptor`; với batch listener có `BatchInterceptor`. Kafka client cũng có interface riêng tên `ConsumerInterceptor`, được cấu hình ở cấp Kafka consumer. Ba API này có vị trí và lifecycle khác nhau, vì vậy cần chọn đúng loại theo mục đích.

Trong module `SPRING_KAFKA_MESSAGING`, consumer nhận event bằng `@KafkaListener`. Interceptor có thể hỗ trợ logging, tracing, kiểm tra metadata hoặc đo thời gian xử lý xuyên suốt nhiều listener. Nếu mục tiêu là loại bỏ record theo điều kiện, Spring Kafka có `RecordFilterStrategy` chuyên biệt; không nên biến interceptor thành nơi chứa toàn bộ business logic.

## 1. Interceptor nằm ở đâu trong luồng consumer?

Với Spring Kafka record listener, luồng khái quát:

```mermaid
flowchart LR
    A[Kafka broker] --> B[KafkaConsumer.poll]
    B --> C[Spring RecordInterceptor]
    C -->|record được giữ| D[@KafkaListener]
    C -->|trả null| E[Listener bị bỏ qua]
    D --> F[Success / failure callback]
    F --> G[Container commit theo AckMode]
```

`RecordInterceptor` được gọi sau khi consumer poll record và trước khi listener method xử lý. Nó có thể trả lại record để listener tiếp tục, hoặc trả `null` để bỏ qua lần gọi listener đó. Các callback lifecycle giúp quan sát kết quả xử lý.

Ở cấp Kafka client, `ConsumerInterceptor` được Kafka consumer gọi trong quá trình `poll()` và khi commit offset. Spring `RecordInterceptor` nằm ở lớp listener container nên phù hợp hơn khi cần tích hợp với Spring application và listener lifecycle.

## 2. Phân biệt ba API thường bị nhầm

| API | Package | Đơn vị xử lý | Mục đích chính |
|---|---|---|---|
| `RecordInterceptor<K,V>` | `org.springframework.kafka.listener` | Một `ConsumerRecord` | Intercept trước/sau từng lần gọi record listener |
| `BatchInterceptor<K,V>` | `org.springframework.kafka.listener` | Một `ConsumerRecords` từ poll | Intercept batch trước/sau batch listener |
| `ConsumerInterceptor<K,V>` | `org.apache.kafka.clients.consumer` | `ConsumerRecords` và offset commit | Hook ở Kafka client, độc lập với Spring listener container |

Nếu ứng dụng dùng `@KafkaListener` và muốn dùng Spring bean, dependency injection hoặc callback success/failure của listener, ưu tiên `RecordInterceptor`/`BatchInterceptor`. Chọn Kafka native `ConsumerInterceptor` khi cần hook ở cấp Kafka client, ví dụ quan sát records vừa poll hoặc offset commit cho mọi consumer được cấu hình interceptor đó.

## 3. Tạo `RecordInterceptor`

Ví dụ event dùng trong bài:

```java
import java.math.BigDecimal;

public record OrderCreatedEvent(
        String eventId,
        String orderId,
        BigDecimal total,
        boolean active
) {}

public interface OrderApplicationService {
    void handle(OrderCreatedEvent event);
}
```

Một interceptor có thể ghi metadata trước listener và ghi kết quả ở callback:

```java
import org.apache.kafka.clients.consumer.Consumer;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.kafka.listener.RecordInterceptor;

public class OrderRecordInterceptor
        implements RecordInterceptor<String, OrderCreatedEvent> {

    private static final Logger log =
            LoggerFactory.getLogger(OrderRecordInterceptor.class);

    @Override
    public ConsumerRecord<String, OrderCreatedEvent> intercept(
            ConsumerRecord<String, OrderCreatedEvent> record,
            Consumer<String, OrderCreatedEvent> consumer) {

        log.debug("Before listener: topic={} partition={} offset={}",
                record.topic(), record.partition(), record.offset());
        return record;
    }

    @Override
    public void success(
            ConsumerRecord<String, OrderCreatedEvent> record,
            Consumer<String, OrderCreatedEvent> consumer) {
        String eventId = record.value() == null
                ? "tombstone"
                : record.value().eventId();
        log.debug("Listener succeeded for eventId={}", eventId);
    }

    @Override
    public void failure(
            ConsumerRecord<String, OrderCreatedEvent> record,
            Exception exception,
            Consumer<String, OrderCreatedEvent> consumer) {
        log.warn("Listener failed for topic={} partition={} offset={}",
                record.topic(), record.partition(), record.offset(), exception);
    }

    @Override
    public void clearThreadState() {
        // Xóa ThreadLocal/context tạm nếu interceptor có sử dụng.
    }

    @Override
    public void afterRecord(
            ConsumerRecord<String, OrderCreatedEvent> record,
            Consumer<String, OrderCreatedEvent> consumer) {
        log.trace("Listener invocation finished for offset={}", record.offset());
    }
}
```

`intercept()` là điểm quyết định record nào được chuyển tiếp đến listener. `success()` và `failure()` cho phép quan sát kết quả listener; `afterRecord()` là callback dọn dẹp/hậu xử lý sau lần gọi listener. Các callback không thay thế error handler và không tự quyết định retry hoặc commit offset.

Nếu `record.value()` có thể null, ví dụ tombstone trong compacted topic, cần kiểm tra null trước khi đọc field. Không giả định mọi record đều chứa POJO khác null.

## 4. Gắn interceptor vào listener container factory

Spring Kafka cho phép cấu hình interceptor trên `ConcurrentKafkaListenerContainerFactory`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.listener.RecordInterceptor;

@Configuration
public class KafkaListenerConfiguration {

    @Bean
    public RecordInterceptor<String, OrderCreatedEvent> orderRecordInterceptor() {
        return new OrderRecordInterceptor();
    }

    @Bean
    public ConcurrentKafkaListenerContainerFactory<String, OrderCreatedEvent>
            orderKafkaListenerContainerFactory(
                    ConsumerFactory<String, OrderCreatedEvent> consumerFactory,
                    RecordInterceptor<String, OrderCreatedEvent> orderRecordInterceptor) {

        var factory = new ConcurrentKafkaListenerContainerFactory<
                String, OrderCreatedEvent>();
        factory.setConsumerFactory(consumerFactory);
        factory.setRecordInterceptor(orderRecordInterceptor);
        return factory;
    }
}
```

Listener chọn factory này:

```java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderCreatedListener {

    private final OrderApplicationService orderService;

    public OrderCreatedListener(OrderApplicationService orderService) {
        this.orderService = orderService;
    }

    @KafkaListener(
            topics = "orders.created",
            groupId = "orders-projection",
            containerFactory = "orderKafkaListenerContainerFactory"
    )
    public void listen(OrderCreatedEvent event) {
        orderService.handle(event);
    }
}
```

Factory có thể được dùng bởi nhiều listener tương thích cùng key/value type. Nếu mỗi listener cần policy khác nhau, tạo factory riêng hoặc dùng interceptor có cấu hình rõ ràng. Khi ứng dụng có nhiều `RecordInterceptor` bean cùng type, dùng `@Qualifier` để inject đúng interceptor.

## 5. Các callback trong lifecycle

| Callback | Khi nào được gọi? | Cách sử dụng phù hợp |
|---|---|---|
| `intercept(record, consumer)` | Trước khi listener xử lý record | Kiểm tra metadata, gắn context hoặc trả record đã điều chỉnh |
| `success(record, consumer)` | Listener xử lý thành công | Ghi metric hoặc log kết quả thành công |
| `failure(record, exception, consumer)` | Listener ném exception | Ghi metric/log lỗi, bổ sung diagnostic context |
| `afterRecord(record, consumer)` | Sau lần gọi listener | Dọn context tạm, kết thúc timer hoặc trace scope |
| `clearThreadState()` | Container yêu cầu interceptor xóa state gắn với thread | Dọn `ThreadLocal` hoặc state giữ theo consumer thread |

Callback success/failure phản ánh kết quả gọi listener, không khẳng định offset đã được commit thành công lên broker. Việc commit còn phụ thuộc `AckMode`, transaction và error handling của container.

Nếu interceptor mở tracing span hoặc lưu context trong `ThreadLocal`, phải đóng/xóa context cả ở nhánh thành công lẫn thất bại. Không giữ dữ liệu của record trước để record sau trên cùng consumer thread dùng nhầm.

## 6. Trả `null` và quyết định bỏ qua record

`RecordInterceptor.intercept()` có thể trả `null`. Khi đó listener không được gọi cho record đó. Đây là hành vi có tác động đến dữ liệu: container có thể tiếp tục tiến độ theo acknowledgment mode, vì vậy record có thể không được xử lý lại như một lỗi thông thường.

Chỉ trả `null` khi việc bỏ qua là quyết định có chủ đích và có thể giải thích/audit được. Ví dụ, record đã được xử lý ở upstream và có marker rõ ràng cho biết consumer này không cần nhận nó. Nếu record không hợp lệ hoặc cần retry, hãy ném exception phù hợp để error handler xử lý thay vì trả null và làm mất cơ hội recovery.

Không dùng interceptor để lọc nghiệp vụ thông thường nếu Spring Kafka `RecordFilterStrategy` đáp ứng tốt hơn. Filter strategy thể hiện rõ ý định loại bỏ record và có cấu hình `ackDiscarded` riêng để quyết định có xác nhận record bị loại bỏ hay không.

## 7. Phân biệt interceptor và filter strategy

`RecordInterceptor` và `RecordFilterStrategy` có mục tiêu khác nhau:

| Tiêu chí | `RecordInterceptor` | `RecordFilterStrategy` |
|---|---|---|
| Mục đích | Quan sát/điều chỉnh record trước listener và callback sau xử lý | Quyết định record có bị loại khỏi listener hay không |
| API chính | `intercept()` trả record hoặc null | `filter()` trả boolean |
| Lifecycle callback | Có success/failure/afterRecord | Không phải hook success/failure của listener |
| Dùng cho | Logging, tracing, metadata, kiểm tra chung | Bỏ qua record theo điều kiện rõ ràng |
| Cấu hình discard acknowledgment | Không phải trách nhiệm chính | Có `ackDiscarded` để kiểm soát acknowledgment của record bị loại |

Ví dụ filter bỏ qua event không active:

```java
factory.setRecordFilterStrategy(record ->
        record.value() == null || !record.value().active());
factory.setAckDiscarded(true);
```

Đoạn ví dụ giả định payload có phương thức `active()` và factory dùng phiên bản Spring Kafka hỗ trợ `setAckDiscarded`. Hãy chọn `ackDiscarded` theo acknowledgment mode và chính sách dữ liệu: nếu record bị loại là quyết định cuối cùng, cần bảo đảm offset được xử lý theo cách mong muốn; nếu không, record có thể được giao lại.

## 8. Dùng `BatchInterceptor` cho batch listener

Nếu listener nhận nhiều record trong một lần poll, có thể dùng `BatchInterceptor`:

```java
import org.apache.kafka.clients.consumer.Consumer;
import org.apache.kafka.clients.consumer.ConsumerRecords;
import org.springframework.kafka.listener.BatchInterceptor;

public class OrderBatchInterceptor
        implements BatchInterceptor<String, OrderCreatedEvent> {

    @Override
    public ConsumerRecords<String, OrderCreatedEvent> intercept(
            ConsumerRecords<String, OrderCreatedEvent> records,
            Consumer<String, OrderCreatedEvent> consumer) {

        return records;
    }

    @Override
    public void success(
            ConsumerRecords<String, OrderCreatedEvent> records,
            Consumer<String, OrderCreatedEvent> consumer) {
        // Ghi metric batch thành công.
    }

    @Override
    public void failure(
            ConsumerRecords<String, OrderCreatedEvent> records,
            Exception exception,
            Consumer<String, OrderCreatedEvent> consumer) {
        // Ghi metric batch thất bại.
    }

    @Override
    public void afterBatch(
            ConsumerRecords<String, OrderCreatedEvent> records,
            Consumer<String, OrderCreatedEvent> consumer) {
        // Dọn context sau khi batch listener hoàn tất.
    }
}
```

Gắn interceptor vào factory batch:

```java
factory.setBatchListener(true);
factory.setBatchInterceptor(orderBatchInterceptor);
```

Batch interceptor nhận `ConsumerRecords` của lần poll thay vì từng `ConsumerRecord`. Không cấu hình record và batch interceptor như thể chúng có cùng signature. Nếu cần bỏ từng record trong batch, cân nhắc filter strategy dành cho batch hoặc xử lý danh sách một cách tường minh.

## 9. Kafka native `ConsumerInterceptor`

Kafka client có interface `org.apache.kafka.clients.consumer.ConsumerInterceptor<K,V>`. Nó được cấu hình bằng thuộc tính `interceptor.classes` của consumer:

```java
import java.util.Map;

import org.apache.kafka.clients.consumer.ConsumerInterceptor;
import org.apache.kafka.clients.consumer.ConsumerRecords;
import org.apache.kafka.clients.consumer.OffsetAndMetadata;
import org.apache.kafka.common.TopicPartition;

public class ConsumerMetricsInterceptor
        implements ConsumerInterceptor<String, OrderCreatedEvent> {

    @Override
    public ConsumerRecords<String, OrderCreatedEvent> onConsume(
            ConsumerRecords<String, OrderCreatedEvent> records) {
        // Quan sát records vừa được poll; trả lại records cho consumer.
        return records;
    }

    @Override
    public void onCommit(
            Map<TopicPartition, OffsetAndMetadata> offsets) {
        // Quan sát các offset được consumer commit.
    }

    @Override
    public void configure(Map<String, ?> configs) {
    }

    @Override
    public void close() {
    }
}
```

Cấu hình class trong `application.yml`:

```yaml
spring:
  kafka:
    consumer:
      properties:
        interceptor.classes: com.acme.kafka.ConsumerMetricsInterceptor
```

Kafka client tạo interceptor theo cơ chế cấu hình của nó; không giả định class này tự động được Spring quản lý như một bean có constructor injection. Nếu cần dependency injection của Spring, thường nên dùng `RecordInterceptor` hoặc một thành phần Spring khác ở tầng listener.

`onConsume()` nhận `ConsumerRecords` sau poll và có thể trả tập record được điều chỉnh; `onCommit()` quan sát commit callback. Native interceptor không thay thế `CommonErrorHandler`, không mở transaction nghiệp vụ và không đảm bảo offset đã commit theo exactly-once.

## 10. Interceptor với concurrency và thread safety

Listener container có thể chạy nhiều consumer thread khi cấu hình concurrency lớn hơn một. Interceptor cần được viết với giả định callback có thể chạy đồng thời trên các thread khác nhau, đặc biệt nếu cùng một bean được gắn vào nhiều container.

- Ưu tiên interceptor stateless.
- Nếu cần state tạm theo thread, dùng `ThreadLocal` và dọn trong `clearThreadState()`.
- Không dùng một mutable `HashMap` dùng chung để ghi trạng thái record mà không đồng bộ.
- Không giữ reference tới `ConsumerRecord` hoặc payload lâu hơn vòng đời xử lý nếu không cần thiết.
- Tránh gọi network, database hoặc xử lý nặng trong interceptor vì nó nằm trên đường consumer xử lý record.
- Không tự gọi `poll()` hoặc commit offset từ interceptor; để container và consumer quản lý lifecycle.

Interceptor chạy lâu làm giảm tốc độ poll và có thể khiến consumer vượt `max.poll.interval.ms`, dẫn đến rời group/rebalance. Dùng interceptor cho công việc ngắn, có giới hạn thời gian và quan sát được.

## 11. Transaction, retry và error handling

Interceptor không thay thế transaction manager hoặc error handler. Nếu listener ném exception, `failure()` có thể ghi nhận lỗi nhưng quyết định retry/recovery thuộc container:

- Với listener thông thường, `CommonErrorHandler` như `DefaultErrorHandler` xử lý retry/backoff/recovery.
- Với transactional listener rollback, `AfterRollbackProcessor` điều phối seek/retry/recovery sau rollback.
- Với non-blocking retry, retry topic topology do `@RetryableTopic` quản lý.
- Với record bị filter, `ackDiscarded` và AckMode quyết định tiến độ offset của record bị loại.

Không gọi `acknowledge()` hoặc commit offset tùy tiện từ interceptor. Làm vậy có thể phá vỡ semantics của container, nhất là với batch hoặc transactional listener.

## 12. Kiểm thử consumer interceptor

Nên kiểm thử interceptor ở mức unit và tích hợp với listener container:

- **Pass-through test:** `intercept()` trả đúng record và listener nhận payload.
- **Null-return test:** interceptor trả null; xác minh listener không được gọi và offset/discard behavior đúng với AckMode.
- **Success callback test:** listener thành công; xác minh callback `success()` được gọi.
- **Failure callback test:** listener ném exception; xác minh `failure()` được gọi và error handler vẫn thực hiện retry/recovery.
- **After-record cleanup test:** xác minh context/thread-local được dọn sau mỗi record.
- **Batch test:** interceptor nhận đúng `ConsumerRecords` và batch listener xử lý tập record mong muốn.
- **Native consumer test:** cấu hình `interceptor.classes`, xác minh `onConsume()` và `onCommit()` được gọi.
- **Concurrency test:** chạy nhiều consumer thread và kiểm tra không có race condition trong state của interceptor.

Dùng Embedded Kafka hoặc Testcontainers cho integration test. Với test filter/return null, kiểm tra committed offset và redelivery thay vì chỉ xác minh listener không được gọi.

## 13. Những lỗi thường gặp

- **Nhầm `ConsumerInterceptor` của Kafka với `RecordInterceptor` của Spring:** package, cấu hình và lifecycle khác nhau.
- **Dùng interceptor để thực hiện business processing:** làm listener khó kiểm thử và trộn cross-cutting concern với nghiệp vụ.
- **Trả null khi gặp lỗi nghiệp vụ:** listener bị bỏ qua và record có thể không đi qua retry/recovery như mong muốn.
- **Dùng interceptor thay cho `RecordFilterStrategy`:** ý định filtering và acknowledgment khó đọc hơn.
- **Cho rằng `success()` nghĩa là offset đã commit:** callback listener và broker commit là hai sự kiện khác nhau.
- **Ghi state mutable dùng chung:** concurrency có thể gây race condition hoặc lẫn metadata giữa record.
- **Không dọn `ThreadLocal`:** context của record trước rò sang record tiếp theo.
- **Gọi network/database trong interceptor:** làm chậm consumer thread và tăng nguy cơ rebalance.
- **Cấu hình native interceptor rồi mong Spring inject bean:** Kafka client tự khởi tạo class theo cấu hình, không tự dùng Spring bean instance.
- **Commit/seek từ interceptor:** có thể xung đột với listener container và AckMode.

## 14. Checklist triển khai

- [ ] Đã chọn đúng `RecordInterceptor`, `BatchInterceptor` hay Kafka native `ConsumerInterceptor`.
- [ ] Interceptor chỉ xử lý concern chung như logging, tracing hoặc metadata.
- [ ] `intercept()` trả record hợp lệ; chỉ trả null khi chủ đích bỏ qua đã được xác định.
- [ ] Filtering nghiệp vụ dùng `RecordFilterStrategy` và cấu hình `ackDiscarded` phù hợp.
- [ ] Success/failure callback không bị nhầm với offset commit.
- [ ] `ThreadLocal`/state tạm được dọn đúng lifecycle.
- [ ] Interceptor thread-safe khi listener chạy concurrency.
- [ ] Không chặn consumer thread bằng I/O hoặc công việc nặng.
- [ ] Retry, DLT và transaction vẫn do container/error handling quản lý.
- [ ] Integration test bao gồm pass-through, null/filter, failure, batch và concurrency.

Consumer interceptor là điểm mở rộng hữu ích để áp dụng logging, tracing và metadata nhất quán trên luồng nhận event. Chọn `RecordInterceptor` cho record listener Spring, `BatchInterceptor` cho batch listener hoặc Kafka native `ConsumerInterceptor` cho hook ở cấp client; giữ interceptor ngắn, thread-safe và để filter/error handler/container quản lý đúng trách nhiệm của chúng.
