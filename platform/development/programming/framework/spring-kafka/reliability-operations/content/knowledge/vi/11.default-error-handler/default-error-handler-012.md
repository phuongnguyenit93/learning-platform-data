# RetryListener theo dõi delivery attempt

Trong Spring Kafka, **RetryListener** là callback interface cho phép ứng dụng quan sát các lần giao record thất bại và quá trình recovery do error handler thực hiện. Khi dùng **DefaultErrorHandler**, ứng dụng có thể đăng ký RetryListener để nhận thông tin về record, exception và số lần giao hiện tại. Callback này giúp xây dựng log có cấu trúc, metric retry, cảnh báo poison message và dữ liệu phục vụ điều tra.

Một delivery attempt là một lần consumer nhận và thử xử lý record. Lần giao đầu tiên cũng được tính là một attempt; các lần giao lại sau retry làm số attempt tăng. Vì vậy, **deliveryAttempt** không đơn giản là số lần retry đã thực hiện. Ví dụ, nếu record thất bại ở attempt 3 thì record đã có ba lần giao/thử xử lý, tương ứng hai lần giao lại sau lần đầu.

RetryListener quan sát luồng retry do error handler quản lý. Nó không tự thực hiện retry, không quyết định BackOff, không commit offset và không thay thế recoverer. Các quyết định đó vẫn thuộc **DefaultErrorHandler**, container và cấu hình recovery.

## 1. Delivery attempt trong luồng xử lý Kafka

Một record có thể được giao nhiều lần khi listener ném exception và error handler quyết định retry. Với blocking retry của DefaultErrorHandler, container xử lý record, chờ theo BackOff rồi giao lại record theo cơ chế seek/retry tương ứng.

Ví dụ một record trải qua các bước:

1. Consumer nhận record lần đầu.
2. Listener xử lý và ném exception.
3. DefaultErrorHandler gọi RetryListener để thông báo lần giao thất bại.
4. Error handler chờ theo BackOff đã cấu hình.
5. Record được giao lại.
6. Nếu listener tiếp tục thất bại, callback được gọi với delivery attempt tiếp theo.
7. Khi hết retry, recoverer xử lý record; RetryListener được thông báo nếu recovery thành công hoặc thất bại.

~~~mermaid
sequenceDiagram
    participant C as Kafka consumer/container
    participant L as Listener
    participant E as DefaultErrorHandler
    participant R as RetryListener
    participant X as Recoverer

    C->>L: Giao record (attempt 1)
    L-->>E: Ném exception
    E->>R: failedDelivery(record, ex, 1)
    E->>E: BackOff
    C->>L: Giao lại record (attempt 2)
    L-->>E: Ném exception
    E->>R: failedDelivery(record, ex, 2)
    E->>E: Hết retry
    E->>X: Recover record
    X-->>E: Recovery thành công
    E->>R: recovered(record, ex)
~~~

Sơ đồ minh họa một trường hợp có hai lần giao thất bại rồi recovery. Số lần retry thực tế phụ thuộc BackOff. Nếu listener thành công ở một attempt, luồng xử lý kết thúc mà không cần recovery.

## 2. RetryListener cung cấp những callback nào?

Với record listener và các phiên bản Spring Kafka hiện đại có RetryListener API, ba callback chính thường được sử dụng:

| Callback | Khi nào được gọi | Mục đích |
|---|---|---|
| **failedDelivery(record, ex, deliveryAttempt)** | Sau khi một lần giao xử lý thất bại, trước lần retry tiếp theo hoặc bước recovery | Ghi nhận lần giao thất bại và số attempt |
| **recovered(record, ex)** | Khi recoverer hoàn tất recovery thành công | Ghi nhận record đã được xử lý bởi quy trình recovery |
| **recoveryFailed(record, original, failure)** | Khi recoverer ném lỗi trong quá trình recovery | Ghi nhận recovery thất bại và nguyên nhân |

Các callback có ý nghĩa khác nhau:

- **failedDelivery** ghi nhận listener invocation thất bại. Nó có thể được gọi nhiều lần cho cùng record.
- **recovered** cho biết recoverer đã hoàn tất thao tác recovery. Nếu recoverer publish record sang DLT, callback cho biết thao tác recovery đó đã trả về thành công; nó không có nghĩa nghiệp vụ gốc đã xử lý thành công.
- **recoveryFailed** cho biết chính quy trình recovery cũng gặp lỗi. Record có thể tiếp tục được xử lý lại tùy cấu hình error handler.

Tên và overload chính xác của interface có thể khác theo phiên bản Spring Kafka. Ví dụ dưới đây dùng các method record-level phổ biến trong Spring Kafka 2.8 trở lên. Batch listener và các phiên bản mới hơn có thể cung cấp overload nhận **ConsumerRecords**; hãy đối chiếu API của dependency đang chạy.

### Phân biệt attempt và retry count

Giả sử cấu hình cho phép hai lần retry sau lần giao đầu:

| Lần listener được gọi | deliveryAttempt | Kết quả |
|---:|---:|---|
| Lần đầu | 1 | Thất bại |
| Retry thứ nhất | 2 | Thất bại |
| Retry thứ hai | 3 | Thất bại, chuyển recovery |

Ở ví dụ này, có ba delivery attempt nhưng chỉ có hai retry sau lần đầu. Khi hiển thị metric hoặc log, nên đặt tên trường rõ ràng như **delivery_attempt** và **retry_number** nếu ứng dụng tự tính cả hai. Không gán trực tiếp deliveryAttempt thành số retry.

## 3. Cấu hình RetryListener với DefaultErrorHandler

RetryListener được đăng ký trên error handler. Với Spring Kafka hiện đại, **DefaultErrorHandler** cung cấp phương thức **setRetryListeners(...)**.

Ví dụ dưới đây dùng một recoverer ghi nhận record đã hết retry và một RetryListener để quan sát từng bước:

~~~java
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.listener.ConsumerRecordRecoverer;
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.kafka.listener.RetryListener;
import org.springframework.util.backoff.FixedBackOff;

@Configuration
public class KafkaErrorHandlerConfiguration {

    @Bean
    DefaultErrorHandler orderErrorHandler() {
        ConsumerRecordRecoverer recoverer = (record, exception) -> {
            // Ví dụ: ghi log hoặc chuyển record tới recovery store.
            // Thay bằng DLT recoverer nếu hệ thống có DLT.
            log.error(
                    "Recovering topic={} partition={} offset={}",
                    record.topic(),
                    record.partition(),
                    record.offset(),
                    exception
            );
        };

        var errorHandler = new DefaultErrorHandler(
                recoverer,
                new FixedBackOff(1_000L, 2L)
        );

        errorHandler.setRetryListeners(new RetryListener() {

            @Override
            public void failedDelivery(
                    ConsumerRecord<?, ?> record,
                    Exception exception,
                    int deliveryAttempt) {

                log.warn(
                        "Delivery failed topic={} partition={} offset={} attempt={}",
                        record.topic(),
                        record.partition(),
                        record.offset(),
                        deliveryAttempt,
                        exception
                );
            }

            @Override
            public void recovered(
                    ConsumerRecord<?, ?> record,
                    Exception exception) {

                log.info(
                        "Record recovered topic={} partition={} offset={}",
                        record.topic(),
                        record.partition(),
                        record.offset()
                );
            }

            @Override
            public void recoveryFailed(
                    ConsumerRecord<?, ?> record,
                    Exception original,
                    Exception recoveryFailure) {

                log.error(
                        "Recovery failed topic={} partition={} offset={}",
                        record.topic(),
                        record.partition(),
                        record.offset(),
                        recoveryFailure
                );
            }
        });

        return errorHandler;
    }
}
~~~

Trong ví dụ, **FixedBackOff(1_000L, 2L)** yêu cầu chờ 1 giây giữa các lần thử và cho phép hai lần retry sau lần giao đầu theo semantics của Spring BackOff. Recoverer được gọi khi record đã hết retry. RetryListener quan sát lỗi và kết quả recovery; nó không làm thay đổi số lần retry.

Đoạn code dùng logger **log** theo quy ước của ứng dụng. Trong một class Java thuần, cần khai báo logger, ví dụ qua SLF4J. Nếu muốn gửi DLT, thay recoverer minh họa bằng **DeadLetterPublishingRecoverer** và cấu hình KafkaTemplate, topic đích cùng quyền publish phù hợp.

## 4. Gắn error handler vào listener container factory

Error handler chỉ được sử dụng khi container của listener được cấu hình dùng nó. Có thể gắn bean **DefaultErrorHandler** vào **ConcurrentKafkaListenerContainerFactory**:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.listener.DefaultErrorHandler;

@Configuration
public class OrderListenerConfiguration {

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
    orderListenerFactory(
            ConsumerFactory<String, OrderEvent> consumerFactory,
            DefaultErrorHandler orderErrorHandler) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

        factory.setConsumerFactory(consumerFactory);
        factory.setCommonErrorHandler(orderErrorHandler);

        return factory;
    }
}
~~~

Listener sử dụng factory:

~~~java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderListener {

    @KafkaListener(
        id = "orderListener",
        topics = "orders.created",
        groupId = "billing-service",
        containerFactory = "orderListenerFactory"
    )
    public void handle(OrderEvent event) {
        billingService.process(event);
    }
}
~~~

Khi listener ném exception, container chuyển lỗi tới DefaultErrorHandler đã gắn. RetryListener được gọi theo các callback tương ứng. Nếu ứng dụng có nhiều factory, hãy bảo đảm listener cần quan sát retry thực sự dùng factory có error handler đã đăng ký RetryListener.

### Dùng factory mặc định của Spring Boot

Nếu ứng dụng sử dụng factory mặc định do Spring Boot tạo, có thể cấu hình factory qua cơ chế customizer hoặc tự khai báo bean factory và gắn error handler. Cách cụ thể phụ thuộc phiên bản Spring Boot và Spring Kafka.

Khi tự định nghĩa factory, cần giữ các thiết lập hiện có mà ứng dụng đang cần, chẳng hạn ConsumerFactory, message converter, concurrency, AckMode, transaction manager và các customizer. Chỉ khai báo RetryListener trên một error handler không được listener container sử dụng sẽ không tạo ra callback.

## 5. Theo dõi từng lần giao thất bại

**failedDelivery** là callback chính để ghi nhận attempt. Một event log có thể chứa:

- Tên service và môi trường.
- Consumer group hoặc listener ID.
- Topic, partition và offset.
- Event ID hoặc correlation ID nếu có.
- Số delivery attempt.
- Exception class và SQLState/vendor code nếu lỗi đến từ database.
- Thời điểm callback.
- Retry policy hoặc error handler đang áp dụng.

Ví dụ log có cấu trúc:

~~~text
event=consumer_delivery_failed
service=billing-service
listener=orderListener
group=billing-service
topic=orders.created
partition=2
offset=1048
event_id=evt-7f9a
delivery_attempt=2
exception=TransientDataAccessException
~~~

Đây chỉ là dạng minh họa. Không ghi toàn bộ payload, credential, access token hoặc dữ liệu nhạy cảm vào log. Event ID chỉ nên được log nếu chính sách dữ liệu của hệ thống cho phép.

### Đếm số lần thất bại

RetryListener có thể tăng counter mỗi khi một lần giao thất bại:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.listener.RetryListener;

public class DeliveryMetricsRetryListener implements RetryListener {

    private final MeterRegistry meterRegistry;

    public DeliveryMetricsRetryListener(MeterRegistry meterRegistry) {
        this.meterRegistry = meterRegistry;
    }

    @Override
    public void failedDelivery(
            ConsumerRecord<?, ?> record,
            Exception exception,
            int deliveryAttempt) {

        meterRegistry.counter(
                "spring.kafka.delivery.failures",
                "topic", record.topic(),
                "exception", exception.getClass().getSimpleName()
        ).increment();
    }

    @Override
    public void recovered(
            ConsumerRecord<?, ?> record,
            Exception exception) {

        meterRegistry.counter(
                "spring.kafka.delivery.recovered",
                "topic", record.topic()
        ).increment();
    }

    @Override
    public void recoveryFailed(
            ConsumerRecord<?, ?> record,
            Exception original,
            Exception failure) {

        meterRegistry.counter(
                "spring.kafka.delivery.recovery.failed",
                "topic", record.topic(),
                "exception", failure.getClass().getSimpleName()
        ).increment();
    }
}
~~~

Các tag trong ví dụ là những chiều phân loại có số lượng giá trị tương đối giới hạn. Không dùng offset, event ID, key, customer ID hoặc correlation ID làm metric tag vì chúng tạo cardinality rất lớn và có thể làm hệ thống metrics quá tải. Những giá trị định danh từng record phù hợp hơn với log hoặc trace.

## 6. Phân biệt failedDelivery, recovered và recoveryFailed

Ba callback này mô tả ba giai đoạn khác nhau. Khi đọc dashboard, không cộng chúng thành một chỉ số “retry thành công” duy nhất.

### failedDelivery

Callback này được gọi khi listener invocation thất bại. Một record có thể phát sinh nhiều callback failedDelivery nếu nhiều attempt liên tiếp thất bại.

Ví dụ:

- Attempt 1 thất bại do database deadlock.
- Attempt 2 thất bại do downstream timeout.
- Attempt 3 thành công.

RetryListener có thể ghi nhận hai lần failedDelivery. Không có callback recovered nếu record cuối cùng được listener xử lý thành công mà không cần recoverer.

### recovered

Callback này cho biết error handler đã gọi recoverer và recoverer hoàn tất. Ví dụ recoverer publish record sang dead-letter topic và không ném exception.

**recovered** không có nghĩa nghiệp vụ gốc đã thành công. Record đã được chuyển sang một quy trình recovery. Dashboard nên phân biệt listener processing success, record recovered/sent to DLT và record recovery failed.

### recoveryFailed

Callback này xảy ra khi recoverer thất bại, ví dụ DLT publisher không thể gửi do broker unavailable, authorization failure hoặc lỗi serialization.

Khi recovery thất bại, record chưa được xử lý thành công bởi quy trình recovery. Hành vi tiếp theo phụ thuộc error handler, BackOff, reset state và cấu hình container. Cần alert riêng cho recovery failure vì nó có thể khiến record tiếp tục được giao lại hoặc làm partition bị chặn bởi một record lỗi.

## 7. RetryListener không phải là cơ chế retry

RetryListener chỉ quan sát và báo sự kiện. Nó không quyết định:

- Exception nào được retry.
- Có bao nhiêu lần retry.
- Khoảng nghỉ giữa các lần thử.
- Có dùng fixed, exponential hay custom BackOff.
- Khi nào record được chuyển DLT.
- Offset được commit ở thời điểm nào.
- Consumer có seek lại partition hay không.

Những quyết định đó thuộc DefaultErrorHandler, BackOff, ConsumerRecordRecoverer, container properties và transaction configuration.

Không đặt logic retry trực tiếp trong callback **failedDelivery**. Callback nên nhanh, không blocking và không thực hiện side effect nghiệp vụ. Nếu callback gọi database, HTTP API hoặc gửi message đồng bộ, nó có thể kéo dài luồng xử lý consumer và làm tăng consumer lag.

Nếu cần gửi cảnh báo, ưu tiên ghi log/metric hoặc đẩy một tín hiệu nhẹ sang hệ thống quan sát. Cần bảo đảm lỗi trong chính RetryListener không làm che mất exception gốc hoặc phá luồng xử lý của error handler.

Nếu cần thực hiện hành động recovery, triển khai qua ConsumerRecordRecoverer hoặc DLT publishing. RetryListener chỉ ghi nhận sự kiện và outcome.

## 8. Delivery attempt và offset

Delivery attempt không phải Kafka offset. Hai giá trị có ý nghĩa khác nhau:

| Giá trị | Ý nghĩa |
|---|---|
| Topic/partition/offset | Vị trí record trong Kafka log |
| deliveryAttempt | Số lần record được giao/thử xử lý trong retry flow do error handler quản lý |
| Retry count | Số lần giao lại sau lần đầu; thường thấp hơn deliveryAttempt một đơn vị nếu lần đầu được tính là attempt 1 |
| Consumer group committed offset | Vị trí tiếp theo consumer group đã xác nhận |

Một record ở offset 1048 có thể được giao ở attempt 1, 2 và 3. Offset vẫn là 1048 trong các lần giao lại. Khi listener xử lý thành công và offset được commit theo AckMode, committed position mới tiến qua record đó.

Delivery attempt không phải một bộ đếm toàn cục được lưu bền vững cho toàn bộ vòng đời của event. Khi process restart, rebalance, thay đổi error handler hoặc chuyển record qua một hệ thống retry topic, lịch sử attempt có thể có phạm vi khác. Nếu cần lịch sử end-to-end, ứng dụng phải lưu attempt hoặc trạng thái workflow vào một hệ thống bền vững với event ID.

## 9. Kết hợp RetryListener với DLT recovery

Một quy trình phổ biến là retry record một số lần, sau đó publish sang dead-letter topic. RetryListener giúp quan sát cả lần thất bại và kết quả recovery.

Ví dụ cấu hình:

~~~java
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.listener.DeadLetterPublishingRecoverer;
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.util.backoff.FixedBackOff;

@Bean
DefaultErrorHandler orderErrorHandler(
        KafkaTemplate<Object, Object> kafkaTemplate,
        RetryListener deliveryRetryListener) {

    var recoverer = new DeadLetterPublishingRecoverer(kafkaTemplate);

    var handler = new DefaultErrorHandler(
            recoverer,
            new FixedBackOff(1_000L, 3L)
    );

    handler.setRetryListeners(deliveryRetryListener);

    return handler;
}
~~~

Trong cấu hình này, recoverer mặc định của ví dụ dùng cơ chế định tuyến DLT của DeadLetterPublishingRecoverer. Trong production, hãy cấu hình rõ topic đích, partition routing, serializer, producer permissions và metadata cần giữ. **FixedBackOff(1_000L, 3L)** minh họa ba lần retry sau lần giao đầu; tổng số lần listener có thể được gọi khi mọi lần đều thất bại là bốn.

RetryListener ghi nhận:

- Các attempt thất bại qua **failedDelivery**.
- Recovery thành công qua **recovered**.
- Recovery thất bại qua **recoveryFailed**.

Nếu DLT publish thành công nhưng consumer không thể commit offset do rebalance hoặc lỗi commit, cần hiểu semantics của container để tránh xử lý lại và gửi DLT trùng. DLT consumer và replay workflow vẫn cần idempotency.

## 10. Phân loại exception và retry policy

Không phải mọi exception đều nên retry. RetryListener quan sát attempt, nhưng error handler cần có phân loại lỗi đúng.

| Nhóm lỗi | Hành vi thường cân nhắc |
|---|---|
| Database deadlock | Retry giới hạn với backoff sau khi transaction rollback |
| Database connection reset | Retry có giới hạn; theo dõi tình trạng database |
| HTTP 503 hoặc timeout tạm thời | Retry có backoff nếu thao tác an toàn |
| Validation error | Thường không retry; recovery/DLT để điều tra |
| AuthorizationException | Sửa quyền; retry liên tục không tạo ACL |
| Deserialization error | Recovery/DLT hoặc xử lý dữ liệu lỗi theo policy |
| Unique constraint nghiệp vụ | Xác định duplicate/idempotency; không mặc định retry |

Có thể cấu hình exception classification trên DefaultErrorHandler bằng các phương thức như **addRetryableExceptions** và **addNotRetryableExceptions**, tùy phiên bản Spring Kafka. Hãy kiểm tra cause chain để tránh phân loại sai khi exception database hoặc HTTP được bọc bởi exception khác.

Một chính sách rõ ràng giúp metrics của RetryListener có ý nghĩa. Nếu lỗi không retryable nhưng vẫn bị ghi nhận như retry failure, dashboard có thể làm người vận hành hiểu nhầm rằng hệ thống đang thử lại.

## 11. Batch listener và RetryListener

Với batch listener, một lần gọi listener có thể nhận nhiều record. Khi batch thất bại, error handler có thể xử lý lại cả batch hoặc dùng thông tin về record lỗi để seek/recover phù hợp.

Một số phiên bản Spring Kafka mở rộng RetryListener với callback nhận **ConsumerRecords<?, ?>** cho batch delivery. Không nên triển khai overload batch khi dependency đang dùng chưa cung cấp API đó. Hãy kiểm tra Javadoc của đúng phiên bản.

Khi theo dõi batch, nên ghi thêm:

- Số record trong batch.
- Topic-partition có liên quan.
- Offset đầu và cuối hoặc offset record lỗi.
- Batch listener ID.
- Delivery attempt.
- Exception và recovery outcome.

Nếu batch chứa record từ nhiều partition, một metric theo topic có thể không đủ để khoanh vùng. Có thể ghi chi tiết partition/offset trong log, nhưng không dùng chúng làm tag metric có cardinality cao.

Nếu bật **subBatchPerPartition**, container có thể chia batch theo partition trước khi gọi listener theo cấu hình. Điều này thay đổi phạm vi invocation, nhưng không thay thế error handler hoặc retry listener.

## 12. Phân biệt blocking retry và non-blocking retry topics

RetryListener của DefaultErrorHandler theo dõi các lần giao và xử lý retry do error handler đó quản lý. Spring Kafka cũng có cơ chế non-blocking retry với retry topics, thường được khai báo qua **@RetryableTopic**.

Hai mô hình có đường đi khác nhau:

- **Blocking retry** giữ luồng xử lý trong consumer và retry record theo BackOff/error handler.
- **Non-blocking retry** chuyển record sang retry topic, để một listener/container khác nhận lại sau thời gian trì hoãn.

Với retry topics, mỗi lần chuyển topic là một bước trong pipeline retry. Không nên coi một RetryListener trên consumer ban đầu là bộ đếm tổng thể cho toàn bộ vòng retry topic. Cần theo dõi retry topic, DLT, delivery metadata/header, số record chuyển tiếp và trạng thái consumer của từng topic.

Nếu ứng dụng dùng **@RetryableTopic**, hãy quan sát retry infrastructure mà annotation tạo ra và xác định callback được gắn vào container nào. Dùng event ID để nối log giữa topic gốc, retry topic và DLT.

## 13. Quan sát, dashboard và cảnh báo

RetryListener cung cấp sự kiện gần với thời điểm listener thất bại. Kết hợp chúng với metric consumer và DLT để theo dõi sức khỏe xử lý.

### Các metric nên có

| Metric | Ý nghĩa |
|---|---|
| **spring.kafka.delivery.failures** | Số lần listener delivery thất bại |
| **spring.kafka.delivery.recovered** | Số record được recover thành công |
| **spring.kafka.delivery.recovery.failed** | Số lần recoverer thất bại |
| Retry attempts theo exception class | Nhóm lỗi gây retry |
| DLT publish rate | Tốc độ record được chuyển vào DLT |
| Consumer lag | Mức tồn đọng trong group |
| Listener processing duration | Thời gian xử lý record/batch |
| Recovery latency | Thời gian từ lần thất bại đầu đến recovery |

Tên metric là convention minh họa; ứng dụng có thể chọn tên theo quy tắc observability nội bộ. Khi dùng Micrometer, giữ tag cardinality thấp và nhất quán.

### Cảnh báo hữu ích

- Tỷ lệ failedDelivery tăng đột ngột theo service hoặc topic.
- Một exception class tạo nhiều attempt liên tiếp.
- Recovery failed khác 0.
- DLT publish tăng vượt ngưỡng bình thường.
- Consumer lag tăng đồng thời với retry rate.
- Một listener có nhiều record chạm attempt tối đa.
- Tuổi của record ở DLT hoặc retry topic vượt SLA.

Không cảnh báo chỉ dựa vào một lần failedDelivery. Một lỗi tạm thời được retry thành công có thể là hành vi bình thường. Alert nên dựa vào tỷ lệ, xu hướng, attempt cao, recovery failure hoặc tác động đến lag/SLA.

### Correlation trong log và trace

Dùng event ID, correlation ID, listener ID và consumer group để nối các lần thử của cùng một record. Offset giúp xác định vị trí trong Kafka nhưng không thay thế event ID khi cùng một event có thể được publish lại thành record mới ở offset khác.

## 14. RetryListener phải nhẹ và an toàn

Callback chạy trong đường xử lý error handler. Công việc nặng trong callback có thể làm consumer xử lý chậm và gây thêm lag.

Nên:

- Ghi log có cấu trúc với thông tin đủ để truy vết.
- Tăng counter hoặc timer nhanh.
- Gắn listener ID hoặc service name có số lượng hữu hạn.
- Tránh thao tác network đồng bộ.
- Không lưu payload nhạy cảm.
- Không ném exception mới từ callback.
- Tránh giữ tham chiếu record hoặc exception trong collection không giới hạn.

Không nên dùng callback để gọi lại listener, commit offset hoặc tự publish record. Những thao tác đó có thể phá vỡ semantics do DefaultErrorHandler quản lý.

Nếu cần thực hiện hành động recovery, triển khai qua ConsumerRecordRecoverer hoặc DLT publishing. RetryListener chỉ ghi nhận sự kiện và outcome.

## 15. Kiểm thử RetryListener

Unit test có thể xác minh callback được gọi và các trường được ghi nhận khi handler xử lý lỗi. Integration test với Kafka broker giúp xác nhận hành vi delivery, retry, recovery và offset trong container thực tế.

Một kịch bản kiểm thử:

1. Tạo topic test và consumer group riêng.
2. Cấu hình listener cố ý thất bại ở hai lần đầu, sau đó thành công.
3. Cấu hình DefaultErrorHandler với BackOff ngắn và RetryListener test.
4. Gửi một record có event ID cố định.
5. Xác nhận callback failedDelivery nhận attempt tăng dần.
6. Xác nhận listener thành công ở lần tiếp theo.
7. Xác nhận recoverer không được gọi nếu record được xử lý thành công trước khi hết retry.
8. Tạo một kịch bản khác luôn thất bại và xác nhận recoverer được gọi sau số lần thử đã cấu hình.
9. Xác nhận recovered khi recoverer hoàn tất.
10. Tạo một recoverer ném exception và xác nhận recoveryFailed.
11. Kiểm tra offset và redelivery theo AckMode/container configuration.

Ví dụ listener test có bộ đếm:

~~~java
@Component
public class RetryTestListener {

    private final AtomicInteger invocations = new AtomicInteger();

    @KafkaListener(
        topics = "retry-test",
        groupId = "retry-test-group"
    )
    public void consume(String value) {
        int current = invocations.incrementAndGet();

        if (current <= 2) {
            throw new IllegalStateException("Simulated transient failure");
        }
    }

    public int invocationCount() {
        return invocations.get();
    }
}
~~~

Trong test thật, cần cô lập counter theo event ID nếu có thể nhận nhiều record hoặc chạy test song song. Một counter dùng chung chỉ phù hợp cho ví dụ đơn giản và có thể làm kết quả không xác định khi concurrency lớn hơn một.

### Kiểm thử callback độc lập

Có thể dùng RetryListener giả để thu thập lời gọi:

~~~java
public class RecordingRetryListener implements RetryListener {

    private final List<Integer> failedAttempts = new CopyOnWriteArrayList<>();
    private final AtomicInteger recoveredCount = new AtomicInteger();
    private final AtomicInteger recoveryFailedCount = new AtomicInteger();

    @Override
    public void failedDelivery(
            ConsumerRecord<?, ?> record,
            Exception exception,
            int deliveryAttempt) {
        failedAttempts.add(deliveryAttempt);
    }

    @Override
    public void recovered(
            ConsumerRecord<?, ?> record,
            Exception exception) {
        recoveredCount.incrementAndGet();
    }

    @Override
    public void recoveryFailed(
            ConsumerRecord<?, ?> record,
            Exception original,
            Exception failure) {
        recoveryFailedCount.incrementAndGet();
    }

    public List<Integer> failedAttempts() {
        return List.copyOf(failedAttempts);
    }
}
~~~

Test nên dùng assertion chờ có timeout thay vì sleep cố định. Với listener concurrency cao, collection và counter phải thread-safe. Không dùng chung recording listener giữa nhiều test nếu không reset state hoặc cô lập context.

## 16. Các lỗi triển khai thường gặp

**Nhầm deliveryAttempt với retry count.** Delivery attempt thường tính cả lần giao đầu. Hiển thị tên metric và log chính xác.

**Chỉ ghi log failedDelivery.** Không quan sát recovered và recoveryFailed sẽ khiến đội vận hành không biết record đã được phục hồi hay recovery cũng lỗi.

**Nghĩ RetryListener thực hiện retry.** Callback chỉ quan sát; BackOff và DefaultErrorHandler quyết định retry.

**Đăng ký listener trên error handler không được sử dụng.** Factory hoặc endpoint có thể đang dùng một handler khác. Kiểm tra container factory hiệu lực.

**Thực hiện HTTP/database call trong callback.** Callback làm chậm đường xử lý và có thể tăng consumer lag. Giữ callback ngắn.

**Dùng offset hoặc event ID làm metric tag.** Cardinality tăng rất nhanh. Đưa định danh từng record vào log/trace.

**Coi recovered là nghiệp vụ thành công.** Recovered có nghĩa recoverer hoàn tất, ví dụ publish DLT. Record có thể chưa hoàn tất nghiệp vụ ban đầu.

**Không xử lý recoveryFailed.** DLT publish có thể thất bại do quyền, serialization hoặc broker. Cần alert và runbook riêng.

**Dùng RetryListener của blocking retry để đo toàn bộ retry topic.** Non-blocking retry có nhiều container và topic. Cần quan sát từng hop của pipeline.

**Giả định attempt count tồn tại vĩnh viễn qua restart.** RetryListener phản ánh retry state do handler quản lý. Nếu cần lịch sử end-to-end, lưu vào hệ thống bền vững theo event ID.

## 17. Runbook khi retry attempt tăng bất thường

1. Xác định listener ID, consumer group, topic và partition.
2. Tìm log failedDelivery theo event ID hoặc topic-partition-offset.
3. Xem deliveryAttempt cao nhất và exception class tương ứng.
4. Kiểm tra DefaultErrorHandler, BackOff và exception classification.
5. Xác định lỗi là transient, dữ liệu không hợp lệ hay cấu hình không thể tự phục hồi.
6. Kiểm tra listener processing time, downstream latency và consumer lag.
7. Nếu callback recovered xuất hiện, xác minh recoverer thực sự đã lưu/publish record đúng đích.
8. Nếu recoveryFailed xuất hiện, kiểm tra DLT topic, ACL, serializer và broker connectivity.
9. Kiểm tra record có bị chuyển qua retry topic hay không; đối chiếu từng hop.
10. Sau khi sửa nguyên nhân, replay record theo quy trình có idempotency.
11. Theo dõi failedDelivery rate, recovery success, DLT rate và consumer lag sau phục hồi.
12. Ghi lại exception classification hoặc BackOff đã thay đổi để tránh retry storm tái diễn.

Không tăng số lần retry chỉ vì attempt cao. Nếu lỗi là schema hoặc authorization, tăng retry thường chỉ kéo dài thời gian xử lý và làm backlog lớn hơn.

## 18. Checklist trước khi đưa RetryListener vào production

**Cấu hình**

- [ ] RetryListener được đăng ký trên đúng DefaultErrorHandler.
- [ ] Listener container thực sự dùng error handler đó.
- [ ] BackOff và số lần retry được xác định rõ.
- [ ] Exception retryable và non-retryable được phân loại.
- [ ] API callback tương thích với phiên bản Spring Kafka.

**Theo dõi**

- [ ] failedDelivery ghi nhận attempt và exception.
- [ ] recovered được phân biệt với listener success.
- [ ] recoveryFailed tạo cảnh báo.
- [ ] Log có listener/group/topic/partition/offset và event ID phù hợp.
- [ ] Metric tags có cardinality thấp.

**An toàn và phục hồi**

- [ ] Callback không blocking và không thực hiện nghiệp vụ.
- [ ] Callback không ném exception mới.
- [ ] Recoverer có DLT/recovery store và quyền publish phù hợp.
- [ ] Record có idempotency để chịu redelivery.
- [ ] Retry topic và blocking retry được theo dõi đúng phạm vi.

**Kiểm thử**

- [ ] Test attempt tăng qua các lần delivery failure.
- [ ] Test listener thành công trước khi hết retry.
- [ ] Test recovered sau recovery thành công.
- [ ] Test recoveryFailed khi recoverer ném exception.
- [ ] Test offset/redelivery trong container thật hoặc test broker.

## 19. Nguyên tắc sử dụng

RetryListener giúp quan sát các lần delivery thất bại và kết quả recovery của DefaultErrorHandler. **failedDelivery** cho biết record đã thất bại ở attempt nào; **recovered** cho biết recoverer hoàn tất; **recoveryFailed** cho biết recovery cũng gặp lỗi. Ba tín hiệu này cung cấp dữ liệu để theo dõi retry, tìm nguyên nhân và vận hành DLT.

Hãy giữ callback ngắn, ghi log/metric có cardinality phù hợp và gắn nó vào đúng error handler mà listener container sử dụng. Để DefaultErrorHandler quản lý BackOff, retry và recovery; dùng database hoặc workflow bền vững nếu cần lịch sử attempt xuyên qua restart và retry topics.

## 20. Cấu hình RetryListener thành bean dùng chung

Khi nhiều listener sử dụng cùng một chính sách retry, có thể khai báo RetryListener thành Spring bean để tái sử dụng. Ví dụ:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.listener.RetryListener;

@Configuration
public class RetryObservationConfiguration {

    @Bean
    RetryListener deliveryRetryListener(MeterRegistry registry) {
        return new RetryListener() {

            @Override
            public void failedDelivery(
                    ConsumerRecord<?, ?> record,
                    Exception exception,
                    int deliveryAttempt) {

                registry.counter(
                        "spring.kafka.delivery.failures",
                        "topic", record.topic(),
                        "exception", exception.getClass().getSimpleName()
                ).increment();
            }

            @Override
            public void recovered(
                    ConsumerRecord<?, ?> record,
                    Exception exception) {

                registry.counter(
                        "spring.kafka.delivery.recovered",
                        "topic", record.topic()
                ).increment();
            }

            @Override
            public void recoveryFailed(
                    ConsumerRecord<?, ?> record,
                    Exception original,
                    Exception failure) {

                registry.counter(
                        "spring.kafka.delivery.recovery.failed",
                        "topic", record.topic(),
                        "exception", failure.getClass().getSimpleName()
                ).increment();
            }
        };
    }
}
~~~

Gắn bean này vào error handler:

~~~java
@Bean
DefaultErrorHandler orderErrorHandler(RetryListener deliveryRetryListener) {
    var handler = new DefaultErrorHandler(
            new FixedBackOff(500L, 3L)
    );

    handler.setRetryListeners(deliveryRetryListener);
    return handler;
}
~~~

Một RetryListener bean có thể được chia sẻ giữa nhiều error handler nếu nó stateless hoặc thread-safe. Tránh giữ danh sách record hoặc trạng thái mutable không đồng bộ trong bean singleton. Nếu mỗi listener cần metric hoặc policy khác nhau, có thể tạo listener riêng hoặc truyền nhãn cấu hình có số lượng hữu hạn.

## 21. Phân tích một ví dụ delivery attempt

Giả sử record có topic **orders.created**, partition 2, offset 1048 và event ID **evt-7f9a**. Listener gọi database và gặp deadlock ở hai lần đầu. Lần thứ ba xử lý thành công.

| Thời điểm | Callback / hoạt động | Attempt | Kết quả |
|---|---|---:|---|
| T0 | Listener nhận record | 1 | Database deadlock |
| T0 | failedDelivery | 1 | Ghi failure đầu tiên |
| T0 + BackOff | Listener nhận lại record | 2 | Database deadlock |
| T1 | failedDelivery | 2 | Ghi failure thứ hai |
| T1 + BackOff | Listener nhận lại record | 3 | Database commit thành công |
| T2 | Listener hoàn tất | 3 | Container tiếp tục acknowledgement/commit theo cấu hình |

Trong trường hợp này:

- Có ba lần delivery attempt.
- Có hai lần listener thất bại.
- Có hai lần retry sau lần giao đầu.
- Recoverer không cần chạy.
- recovered và recoveryFailed không được gọi cho record này.

Nếu lần thứ ba vẫn thất bại và error handler chuyển record sang DLT, failedDelivery ghi nhận lần thất bại tương ứng, sau đó recovered được gọi khi DLT recoverer hoàn tất. Nếu DLT publisher ném exception, recoveryFailed ghi nhận lỗi recovery.

Ví dụ giúp phân biệt ba số liệu: delivery attempts, listener failures và recovery outcomes. Khi báo cáo vận hành, hãy đặt định nghĩa metric rõ ràng để không đếm một record nhiều lần như nhiều event nghiệp vụ khác nhau.

## 22. Phạm vi của attempt state và yêu cầu audit

Attempt number từ RetryListener hữu ích để chẩn đoán retry hiện tại, nhưng không phải audit log bền vững của event. Nếu cần trả lời câu hỏi “event này đã được thử bao nhiêu lần trong toàn bộ vòng đời, kể cả sau deploy/restart và qua retry topic?”, cần một mô hình lưu trạng thái riêng.

Có thể lưu một bảng retry history với các trường:

| Trường | Ý nghĩa |
|---|---|
| **event_id** | Định danh ổn định của event |
| **source_topic** | Topic ban đầu |
| **source_partition** | Partition ban đầu |
| **source_offset** | Offset record ban đầu |
| **attempt** | Attempt được ghi nhận |
| **failure_type** | Nhóm exception |
| **failure_time** | Thời điểm thất bại |
| **recovery_status** | Chưa recovery, recovered hoặc recovery failed |
| **last_error** | Thông tin lỗi đã lọc dữ liệu nhạy cảm |

Nếu ghi audit từ callback, thao tác ghi phải không làm ảnh hưởng retry path. Một lựa chọn là đẩy event telemetry vào queue nội bộ có giới hạn hoặc ghi vào observability pipeline. Nếu cần bảo đảm không mất audit record, cần một durable mechanism và xử lý lỗi ghi audit rõ ràng. Không mở transaction database nghiệp vụ từ callback rồi giữ consumer thread chờ ghi telemetry đồng bộ.

Với retry topic, event ID là khóa liên kết các lần chuyển topic. Attempt number có thể được biểu diễn bằng header hoặc metadata của pipeline tùy cấu hình. Cần xác định một nguồn sự thật cho attempt toàn cục để tránh cộng lặp các counter từ nhiều consumer container.

## 23. Các điểm cần lưu ý khi nâng cấp Spring Kafka

RetryListener là API thuộc Spring Kafka, nên cần đối chiếu dependency version khi nâng cấp. Các thay đổi có thể liên quan:

- Tên method và overload hỗ trợ record hay batch.
- API đăng ký callback trên error handler.
- Cách DefaultErrorHandler xử lý retry, seek và recovery.
- Hành vi delivery attempt header.
- Sự khác nhau giữa record listener và batch listener.
- Sự khác nhau giữa blocking retry và non-blocking retry topic infrastructure.

Khi nâng cấp, compile test xác nhận method override vẫn đúng. Integration test nên xác nhận số lần callback, callback recovery và offset behavior. Không dựa vào một ví dụ code từ phiên bản khác nếu ứng dụng đang dùng Spring Kafka cũ.

Nếu listener sử dụng **@RetryableTopic**, kiểm tra retry-topic infrastructure riêng. RetryListener của DefaultErrorHandler chỉ phản ánh các lần xử lý mà handler đó quản lý; nó không tự tổng hợp mọi lần chuyển qua các retry topic.

## 24. Nguyên tắc vận hành

Hãy dùng RetryListener để trả lời ba câu hỏi: record đã thất bại ở attempt nào, recovery có hoàn tất hay không, và nếu recovery thất bại thì lỗi nào xảy ra. Gắn callback với đúng DefaultErrorHandler, phân loại lỗi và cấu hình BackOff ở error handler, đồng thời giữ log và metric có cardinality thấp.

Delivery attempt là số lần giao/thử xử lý trong phạm vi retry flow đang quan sát. Nó không phải Kafka offset, không phải số lần retry sau lần đầu và không phải lịch sử toàn cục của event. Nếu cần audit xuyên restart hoặc retry topics, lưu trạng thái bền vững theo event ID và kết hợp với metadata của từng hop.
