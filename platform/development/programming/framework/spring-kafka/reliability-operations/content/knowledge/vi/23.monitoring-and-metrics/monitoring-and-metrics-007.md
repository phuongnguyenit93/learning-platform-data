# Retry count và recovery count

Trong một hệ thống Spring Kafka, **retry count** và **recovery count** là hai nhóm metrics cốt lõi để đánh giá khả năng tự phục hồi của consumer. Nhưng không có một ý nghĩa duy nhất cho “một retry” hoặc “một recovery” trong mọi topology. Một record có thể được gọi listener nhiều lần, được chuyển qua nhiều retry topics, rồi gửi DLT; thậm chí DLT publish thành công nhưng offset nguồn chưa commit, khiến cùng record được giao lại và recovery thêm lần nữa.

Điều quan trọng nhất không chỉ là **đếm bao nhiêu**, mà là **đếm đúng sự kiện, đúng ranh giới và đúng kết quả**. Nếu nhầm lần lỗi ban đầu với retry, coi recoverer được gọi là recovery thành công, hoặc cộng cả event handler và producer metrics vào một counter, dashboard có thể hiển thị những con số rất lớn nhưng không trả lời được hệ thống đang khỏe hay không.

Bài học thuộc chương **Monitoring và metrics** của module **Spring Kafka Reliability Operations**. Nội dung xây dựng cách định nghĩa counters, instrument Spring Kafka, phân biệt blocking/non-blocking retry, theo dõi recovery và DLT, thiết kế Micrometer/Prometheus, alert, runbook và kiểm thử kịch bản lỗi.

## 1. Phân biệt “record”, “attempt”, “retry” và “recovery”

Trước khi đặt tên metrics, cần xác định đối tượng đang được đếm.

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| Source record | Một record trong Kafka topic gốc | orders.events partition 2 offset 40 |
| Business event | Một sự kiện nghiệp vụ có ID ổn định | OrderCreated eventId=E-10 |
| Initial processing attempt | Lần đầu logic xử lý được thực thi trong phạm vi đang đo | Listener nhận E-10 lần đầu |
| Processing attempt | Một lần thực thi logic listener | Listener được gọi bốn lần |
| Failed delivery | Một lần xử lý ném exception đến error handler | HTTP timeout |
| Retry scheduled | Hệ thống quyết định sẽ thử lại | Hẹn chờ backoff 1 giây |
| Retry started | Một attempt bổ sung thực sự bắt đầu | Listener chạy lần thứ hai |
| Blocking retry | Retry trong listener container, theo error handler/backoff | Gọi lại record sau 500 ms |
| Non-blocking retry | Record được publish tới retry topic, consumer khác xử lý sau delay | orders-retry-5000 |
| Recovery attempt | Một lần cố chuyển record lỗi sang đường khắc phục | Recoverer cố gửi DLT |
| Recovery succeeded | Recovery hoàn tất theo hợp đồng đã chọn | DLT publish được xác nhận |
| Recovery failed | Recovery operation không đạt điều kiện thành công | DLT send bị authorization error |
| Business success | Nghiệp vụ gốc hoàn thành | Đơn hàng cập nhật thành công |

**Recovery succeeded không đồng nghĩa business succeeded.** Một poison record được gửi vào DLT thành công là kết quả tốt của cơ chế bảo toàn dữ liệu, nhưng nghiệp vụ của record đó vẫn đang chờ sửa và xử lý lại.

## 2. “Retry count” có nhiều cách hiểu

Một số hệ thống gọi số lần retry là **số lần lỗi**. Một số khác gọi đó là **số lần listener được gọi lại**. Cách thứ ba đếm **số lần record được gửi tới retry topic**.

Ba đại lượng này không tương đương.

~~~text
Attempt #1 -> FAILED
     |
     v
Backoff 500 ms
     |
     v
Attempt #2 -> SUCCESS
~~~

Trong luồng này:

- Processing attempts: 2.
- Failed processing attempts: 1.
- Retry attempts đã thực thi: 1.
- Retry scheduled: 1.
- Recovery attempts: 0.

Nếu code tăng retry_count khi lần đầu thất bại nhưng process bị kill trước attempt thứ hai, **retry đã được dự kiến nhưng chưa thực thi**. Muốn theo dõi chính xác thì cần hai counters: một cho retry scheduled và một cho retry actually started.

Một quy ước dễ hiểu:

~~~text
Attempt 1 = initial attempt, không tính là retry
Attempt 2 = retry lần 1
Attempt 3 = retry lần 2
Attempt 4 = retry lần 3
~~~

Theo đó:

~~~text
retry_attempts = max(processing_attempts - initial_attempts, 0)
~~~

Công thức chỉ đúng khi mọi attempts thuộc một chuỗi xử lý được quan sát đầy đủ. Restart, rebalance và retry topic có thể mở chuỗi mới, khiến hệ thống phải định nghĩa lại phạm vi.

## 3. “Recovery count” có nhiều mức kết quả

Một record lỗi có thể đi qua:

~~~text
Listener xử lý thất bại
            |
            v
Hết retry hoặc được phân loại non-retryable
            |
            v
Gọi DeadLetterPublishingRecoverer
            |
            v
KafkaTemplate.send tới DLT
            |
          /   \
   ACK success  Send failed/unknown
        |                |
        v                v
Recovery success    Recovery failure hoặc
theo policy         trạng thái chưa rõ
        |
        v
DLT consumer nhận record sau đó
        |
        v
Manual review/replay/business correction
~~~

Nên có ít nhất ba metrics độc lập:

- **recovery_attempts_total:** một recoverer invocation thực sự bắt đầu.
- **recovery_succeeded_total:** recoverer đã hoàn tất theo durability/ack policy được định nghĩa.
- **recovery_failed_total:** recovery invocation kết thúc thất bại.

Có thể thêm:

- **dlt_publish_attempts_total:** lần gửi Kafka producer tới DLT.
- **dlt_publish_confirmed_total:** số lần producer nhận kết quả gửi thành công.
- **dlt_consume_success_total:** số record DLT workflow xử lý thành công.

Một lần recoverer trả về bình thường chưa chắc tương đương producer đã xác nhận gửi nếu code sử dụng send bất đồng bộ và không kiểm tra future.

## 4. Tại sao không nên chỉ có một counter?

Nếu dùng một metric **kafka_retries_total** cho mọi hành động, dashboard không phân biệt:

- 100 records, mỗi record được retry một lần và thành công.
- Một poison record bị retry 100 lần, liên tục thất bại.
- 100 lần publish vào retry topic nhưng retry consumers chưa xử lý.
- 100 DLT recoveries nhưng không có business success.

Hai hệ thống có cùng tổng retry count có thể có mức rủi ro rất khác nhau.

Nên phân tách theo **attempts**, **outcomes** và **backlog**:

| Nhóm | Chỉ số | Mục đích |
|---|---|---|
| Attempts | Listener attempt rate | Đánh giá lượng xử lý thực tế |
| Errors | Failed delivery rate | Đánh giá độ ổn định đầu vào/dependency |
| Retries | Retry started/scheduled rate | Đánh giá khối lượng retry |
| Recoveries | Recovery attempted/succeeded/failed | Đánh giá terminal recovery |
| Backlog | Retry topic lag, DLT lag | Biết record đang chờ ở đâu |
| Latency | Time to success/recovery | Đo ảnh hưởng đến SLO |
| Business | Processing success rate | Đo nghiệp vụ có thật sự hoàn tất |

## 5. Minh họa một record thành công sau retry

~~~text
Source record R
    |
    v
Listener #1 -> lỗi timeout
    |
    +-- Error handler lên lịch retry
    |
    v
Listener #2 -> thành công
~~~

Kết quả:

| Metric | Giá trị |
|---|---:|
| listener_attempts | 2 |
| listener_failed_deliveries | 1 |
| blocking_retry_attempts_started | 1 |
| recovery_attempts | 0 |
| recovery_succeeded | 0 |
| processing_succeeded_first_attempt | 0 |
| processing_succeeded_after_retry | 1 |

Một metric recovery count bằng 0 ở đây hoàn toàn bình thường: record đã được xử lý thành công mà không cần đi vào recovery.

## 6. Minh họa một record được gửi DLT

Giả sử **FixedBackOff** có hai retries sau lần đầu:

~~~text
Listener #1 -> lỗi
    |
    v
Listener #2 -> lỗi
    |
    v
Listener #3 -> lỗi
    |
    v
DeadLetterPublishingRecoverer -> DLT ACK success
~~~

Kỳ vọng trong một chuỗi không bị restart/rebalance:

| Metric | Giá trị |
|---|---:|
| Listener processing attempts | 3 |
| Listener failures | 3 |
| Blocking retry attempts | 2 |
| Recovery attempts | 1 |
| Recovery succeeded | 1 |
| Recovery failed | 0 |
| DLT publication confirmed | 1 |
| Business success | 0 |

Nếu dashboard cộng recovery_succeeded vào business_success, số liệu tỷ lệ thành công nghiệp vụ sẽ bị sai.

## 7. Minh họa recovery thất bại

~~~text
Listener lỗi và hết retry
         |
         v
Recoverer attempt #1
         |
         +-- DLT publish FAIL
         |
         v
Record được xử lý lại theo policy của error handler
         |
         v
Recoverer attempt #2
         |
         +-- DLT publish SUCCESS
~~~

Nếu chỉ xét hai recovery invocations:

~~~text
recovery_attempts  = 2
recovery_failed    = 1
recovery_succeeded = 1
~~~

Khi recovery thất bại, DefaultErrorHandler có thể áp dụng lại backoff/redelivery tùy phiên bản và cấu hình như **resetStateOnRecoveryFailure**. Vì vậy tổng listener attempts cũng có thể tăng thêm; không mặc định recovery retry chỉ gọi recoverer mà không gọi lại listener.

## 8. DefaultErrorHandler và RetryListener

Đối với record listener non-transactional, **DefaultErrorHandler** thường điều phối blocking retry và recovery. Spring Kafka hỗ trợ **RetryListener** trong các phiên bản phù hợp để nhận thông báo khi một delivery thất bại hoặc một recovery hoàn tất/thất bại.

Luồng khái quát:

~~~text
@KafkaListener throws exception
            |
            v
DefaultErrorHandler
            |
            +-- RetryListener.failedDelivery(...)
            |
            +-- Backoff/redelivery nếu retryable
            |
            +-- Gọi recoverer khi kết thúc retry
                    |
                    +-- RetryListener.recovered(...)
                    |
                    +-- RetryListener.recoveryFailed(...)
~~~

**failedDelivery callback không có nghĩa một retry attempt vừa bắt đầu.** Nó ghi nhận một delivery thất bại, bao gồm khả năng thất bại ở lần đầu. Muốn đếm retry started thực sự, cần quan sát đầu mỗi processing attempt kèm attempt metadata.

### 8.1. Ví dụ gắn RetryListener

~~~java
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.context.annotation.Bean;
import org.springframework.kafka.listener.DeadLetterPublishingRecoverer;
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.kafka.listener.RetryListener;
import org.springframework.util.backoff.FixedBackOff;

@Bean
DefaultErrorHandler ordersErrorHandler(
        DeadLetterPublishingRecoverer recoverer,
        RetryMetricRecorder recorder) {

    DefaultErrorHandler handler =
        new DefaultErrorHandler(
            recoverer,
            new FixedBackOff(500L, 2L)
        );

    handler.setRetryListeners(new RetryListener() {

        @Override
        public void failedDelivery(
                ConsumerRecord<?, ?> record,
                Exception exception,
                int deliveryAttempt) {

            recorder.failedDelivery(
                record,
                exception,
                deliveryAttempt
            );
        }

        @Override
        public void recovered(
                ConsumerRecord<?, ?> record,
                Exception exception) {

            recorder.recovered(record, exception);
        }

        @Override
        public void recoveryFailed(
                ConsumerRecord<?, ?> record,
                Exception original,
                Exception failure) {

            recorder.recoveryFailed(
                record, original, failure
            );
        }
    });

    return handler;
}
~~~

Đây là cấu trúc minh họa. Method signatures và callback semantics cần được đối chiếu với Spring Kafka version đang chạy; lớp **RetryMetricRecorder** do ứng dụng tự xây dựng. Trong một số cấu hình, recoverer có thể xử lý recovery theo đường khác hoặc một listener container factory khác không dùng error handler này.

## 9. Micrometer Counter cho failed delivery

Ví dụ recorder:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.stereotype.Component;

@Component
public class RetryMetricRecorder {

    private final MeterRegistry registry;

    public RetryMetricRecorder(MeterRegistry registry) {
        this.registry = registry;
    }

    public void failedDelivery(
            ConsumerRecord<?, ?> record,
            Exception exception,
            int deliveryAttempt) {

        registry.counter(
            "app.kafka.listener.failed.deliveries",
            "topic", record.topic(),
            "exception_group", classify(exception)
        ).increment();

        if (deliveryAttempt > 1) {
            registry.counter(
                "app.kafka.retry.failed.deliveries",
                "topic", record.topic(),
                "mode", "blocking",
                "exception_group", classify(exception)
            ).increment();
        }
    }

    public void recovered(
            ConsumerRecord<?, ?> record,
            Exception original) {

        registry.counter(
            "app.kafka.recovery.succeeded",
            "topic", record.topic(),
            "mode", "blocking"
        ).increment();
    }

    public void recoveryFailed(
            ConsumerRecord<?, ?> record,
            Exception original,
            Exception failure) {

        registry.counter(
            "app.kafka.recovery.failed",
            "topic", record.topic(),
            "mode", "blocking",
            "exception_group", classify(failure)
        ).increment();
    }

    private String classify(Exception error) {
        return error instanceof IllegalArgumentException
            ? "validation" : "other";
    }
}
~~~

Ví dụ đặt tên **retry.failed.deliveries**, không phải **retry.attempts.started**, vì hook này chỉ được gọi với lần xử lý thất bại. Một retry attempt thành công không sinh ra failedDelivery mới, nên đếm retries chỉ qua callback thất bại sẽ **bị thiếu**.

Muốn có **recovery_attempts_total**, có thể instrument ở recoverer wrapper được gọi trước delegate; cần tránh đếm thêm lần nữa nếu đồng thời có hook ở lớp khác theo cùng định nghĩa.

## 10. Đếm recovery attempts ở đúng boundary

Giả sử ứng dụng muốn biết mỗi lần recoverer được gọi, kể cả khi nó ném exception. Có thể định nghĩa một decorator:

~~~java
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.listener.ConsumerRecordRecoverer;

public final class CountingRecoverer
        implements ConsumerRecordRecoverer {

    private final ConsumerRecordRecoverer delegate;
    private final MeterRegistry registry;

    public CountingRecoverer(
            ConsumerRecordRecoverer delegate,
            MeterRegistry registry) {
        this.delegate = delegate;
        this.registry = registry;
    }

    @Override
    public void accept(
            ConsumerRecord<?, ?> record,
            Exception exception) {

        registry.counter(
            "app.kafka.recovery.attempts",
            "topic", record.topic()
        ).increment();

        delegate.accept(record, exception);
    }
}
~~~

Đây là một ví dụ về ranh giới đo **invocation**, không phải mẫu hoàn chỉnh cho tất cả recoverer paths. Nếu ứng dụng dùng DeadLetterPublishingRecoverer với nhiều destinations, cần xác định cơ chế routing và callback kiểm tra send result đúng với bean thực sự được gọi.

Các outcome metrics recovery_succeeded/recovery_failed nên có **một owner duy nhất**: có thể từ RetryListener hoặc wrapper có try/catch/finally phù hợp, không được để cả hai tăng cùng một metric.

Nếu recoverer gửi Kafka bất đồng bộ rồi trả về trước khi send hoàn tất, callback của wrapper không tự chứng minh broker đã xác nhận record. Cần quan sát kết quả producer send độc lập.

## 11. FixedBackOff: số retries và số attempts

Với:

~~~java
new FixedBackOff(1_000L, 2L)
~~~

Tham số thứ hai thường là **số lần retry bổ sung**. Nếu mỗi lần đều ném exception:

~~~text
Initial delivery = 1
Retries          = 2
Listener calls   = 3
~~~

Không lấy configured retries làm metric thực tế vì:

- Record có thể thành công ngay lần đầu.
- Exception có thể non-retryable.
- Container có thể shutdown giữa các attempts.
- Recovery có thể thất bại và record lại redeliver.
- Consumer rebalance có thể làm một record được xử lý lại trên instance khác.

Nên phân biệt **retry_limit_configured** (cấu hình) và **retry_attempts_started_total** (quan sát thực tế).

## 12. Attempt index và KafkaHeaders.DELIVERY_ATTEMPT

Trong các phiên bản Spring Kafka có hỗ trợ, listener/container có thể bổ sung **delivery attempt metadata**, ví dụ qua **KafkaHeaders.DELIVERY_ATTEMPT**. Việc có header và cách chuyển đổi kiểu phụ thuộc container/error handler và phiên bản.

Ví dụ ý tưởng:

~~~java
@KafkaListener(topics = "orders.events")
public void consume(
        OrderEvent event,
        @Header(
            name = KafkaHeaders.DELIVERY_ATTEMPT,
            required = false
        ) Integer deliveryAttempt) {

    attemptsMetric.increment();

    if (deliveryAttempt != null && deliveryAttempt > 1) {
        retryStartedMetric.increment();
    }

    orderService.process(event);
}
~~~

Không mặc định header luôn có ở mọi listener. Với một số configuration, container cần bật delivery-attempt header và error handler phải cung cấp thông tin. Header cũng có thể có phạm vi **một processing stage**, không phải lifetime attempt index của business event xuyên nhiều retry topics và restart.

Nếu header vắng mặt, cần ghi nhận là **unknown attempt scope** thay vì lặng lẽ coi attempt = 1 trong một báo cáo đòi hỏi chính xác end-to-end.

## 13. Retry thành công thường không tạo failedDelivery callback

Một lỗi instrumentation phổ biến:

~~~text
Attempt 1 -> failure -> failedDelivery callback
Attempt 2 -> success -> KHÔNG có failedDelivery callback mới
~~~

Nếu retry_count chỉ tăng trong failedDelivery callback khi deliveryAttempt > 1:

~~~text
Actual retry attempts = 1
Observed failed retries = 0
~~~

Đây không phải bug của Spring Kafka; **event callback đo một failed delivery**, không đo mọi lần retry bắt đầu.

Giải pháp là đặt metric **retry_attempts_started** ở đầu processing attempt, hoặc dùng một interceptor/observation có attempt context đáng tin cậy. Duy trì riêng metric **failed_retry_deliveries** nếu cần phân tích lần retry vẫn thất bại.

## 14. Non-retryable exception và recovery ngay lập tức

Giả sử một InvalidOrderEventException là lỗi dữ liệu cố định:

~~~text
Listener attempt 1
      |
      +-- InvalidOrderEventException
              |
              v
        No blocking retry
              |
              v
        Recovery / DLT
~~~

Kết quả:

- Listener failures: 1.
- Retry started: 0.
- Recovery attempts: 1.
- Recovery succeeded: 1 nếu gửi DLT theo policy thành công.

Nếu hệ thống báo retry_count = 1 chỉ vì failedDelivery callback được gọi lần đầu, instrumentation đã đánh đồng **failure** với **retry**.

DefaultErrorHandler có cơ chế phân loại fatal/non-retryable exceptions trong những phiên bản phù hợp. Cần kiểm tra classifier và danh sách exception theo version, vì điều này quyết định record nào thực sự đi qua retry.

## 15. Blocking retry và non-blocking retry có đơn vị khác nhau

Với **@RetryableTopic**, một record được chuyển sang retry topic, rồi consumer khác xử lý sau delay. Cần phân biệt:

~~~text
Main topic
    |
    +-- Listener failed
    |
    +-- Publish retry-2000 -> ACK
               |
               v
         Retry consumer starts
               |
               +-- failed, publish retry-10000
                              |
                              v
                        Retry consumer starts
                              |
                              +-- succeeded
~~~

Các số đếm có thể là:

- Retry topic publications attempted: 2.
- Retry topic publications confirmed: 2.
- Retry-topic listener deliveries started: 2.
- Non-blocking retry processing attempts: 2.
- DLT recovery attempts: 0.

Nhưng nếu consumer ở retry-2000 có thêm hai **blocking retries**, số listener executions sẽ tăng mà số retry-topic publications không tăng tương ứng.

Không dùng số retry topics hoặc số messages đã publish sang retry topics như **tổng processing retry attempts**.

## 16. Đếm retry theo từng stage

Một mô hình stage-level:

| Stage | Metric chính | Diễn giải |
|---|---|---|
| Main topic | listener_attempts_total | Processing executions ở topic nguồn |
| Main error handler | blocking_retry_started_total | Thử lại tại topic nguồn |
| Retry publisher | retry_topic_publish_attempts_total | Lần producer cố ghi retry topic |
| Retry producer ack | retry_topic_publish_confirmed_total | Publication đã được xác nhận |
| Retry consumer | retry_topic_deliveries_total | Consumer retry thực sự bắt đầu xử lý |
| Retry error handler | retry_stage_blocking_attempts_total | Blocking retries bên trong retry topic |
| DLT recoverer | recovery_attempts_total | Lần recovery bắt đầu |
| DLT publication | dlt_publish_confirmed_total | DLT producer báo thành công |
| DLT handler | dlt_processing_success_total | Workflow DLT hoàn tất |

Sử dụng tag có kiểm soát, chẳng hạn **stage=main/retry/dlt**, **retry_mode=blocking/non_blocking**.

Nếu một Kafka record đi qua nhiều topics, nó có **topic-partition-offset mới** trên mỗi topic. Muốn liên kết toàn đường đi, cần original metadata hoặc business event ID ổn định, không chỉ current offset.

## 17. Hybrid retry: tổng số lần gọi listener

Giả sử:

- Non-blocking retry policy có 4 deliveries tính cả lần ban đầu.
- Trong mỗi delivery có tối đa 2 blocking retries bổ sung.
- Tất cả attempts đều thất bại.

Theo mô hình đơn giản:

~~~text
Listener calls per delivery = 1 + 2 = 3
Total listener calls        = 4 × 3 = 12
Blocking retry attempts     = 4 × 2 = 8
Non-blocking retry deliveries after first = 3
~~~

Điều này minh họa vì sao **@RetryableTopic attempts** không tự động bằng tổng số lần listener được gọi khi kết hợp với blocking retries.

Con số thực tế còn phụ thuộc exception classification, phiên bản Spring Kafka, việc blocking retry có áp dụng trên tất cả retry consumers không, restart/rebalance và recovery failure.

Nên đo:

- Blocking retry started.
- Non-blocking retry deliveries.
- Total listener attempts.
- Distinct source event IDs entered retry (nếu có persistent correlation).

Không tự nhân cấu hình attempts rồi sử dụng kết quả như số liệu production.

## 18. Recovery ở non-blocking retry topology

Với retry-topic integration, record có thể chuyển qua các retry topics trước khi đến DLT. Recovery trong hệ này có ít nhất hai cách hiểu:

1. **Intermediate transfer:** xử lý thất bại ở stage A, publish sang stage B.
2. **Terminal recovery:** hết policy, publish sang DLT hoặc đích recovery.

Nếu mọi lần publish retry topic đều được gọi là recovery, recovery_count sẽ lớn ngay cả khi record sau đó được xử lý thành công ở retry topic. Điều này gây nhầm lẫn khi dashboard dùng recovery count để đánh giá số record “bị đẩy vào DLT”.

Đặt tên:

~~~text
retry_topic_transfer_total
terminal_recovery_attempts_total
terminal_recovery_succeeded_total
dlt_publish_confirmed_total
~~~

Các nhóm metrics nên có mô tả rõ ràng trong runbook. Nếu dùng Kafka error handler callback có tên recovered nhưng thực chất chỉ **chuyển record sang retry topic**, cần đặt tên metric theo **đích được publish**, không gộp với terminal DLT recovery.

## 19. Transactional listener: AfterRollbackProcessor

Khi listener container dùng Kafka transaction, lỗi có thể gây transaction rollback rồi đi qua **DefaultAfterRollbackProcessor**. Không phải mọi transactional listener đều sử dụng cùng một DefaultErrorHandler như listener non-transactional.

~~~text
Kafka transaction begin
       |
       v
Listener throws exception
       |
       v
Kafka transaction abort
       |
       v
AfterRollbackProcessor
       |
       +-- Redelivery
       |
       +-- Recovery nếu hết policy
~~~

Metric liên quan:

- Kafka transaction abort count.
- After-rollback redelivery count.
- Retry attempts started after rollback.
- Recovery attempts/success/failures trong transactional recovery path.
- Producer fencing/transaction timeout.

**Transaction abort count không bằng retry count.** Một transaction có thể chứa nhiều Kafka output records hoặc xử lý một batch; một lần abort không nhất thiết tương ứng một record retry.

Instrument đúng processor đang được container thực sự sử dụng.

## 20. Batch listener: tránh nhầm batch count với record count

Một batch listener có thể nhận 100 records rồi ném exception vì chỉ một record không hợp lệ.

~~~text
Poll batch: [R1, R2, ... R100]
               |
               v
         Batch listener fails
~~~

Trong trường hợp này:

- Batch listener attempts: 1.
- Batch failures: 1.
- Records trong batch: 100.
- Số records hỏng thật sự: có thể chỉ 1.

Không nhân **batch_failures_total × batch_size** rồi tuyên bố có 100 poison records, trừ khi hệ thống thực sự có evidence/semantics như vậy.

Spring Kafka có cơ chế xử lý batch error và các trường hợp sử dụng BatchListenerFailedException để chỉ ra record gây lỗi. Cách retry/recovery theo batch hay record phụ thuộc version và error handler.

Nên có metric riêng:

| Metric | Đơn vị |
|---|---|
| batch_listener_attempts_total | Lần gọi batch listener |
| batch_listener_failures_total | Batch thất bại |
| batch_records_received_total | Số records được giao trong batch |
| batch_retry_attempts_total | Lần retry của batch |
| record_recovery_attempts_total | Số record recovery invocations |

Không trộn hai loại đơn vị vào một denominator.

## 21. Deserialization failure trước listener

Lỗi deserialization thường xảy ra trong **Consumer.poll()**, trước khi @KafkaListener nhận object. Một bộ đếm đặt ở đầu listener method không quan sát được các lỗi này.

~~~text
Kafka bytes
    |
    v
Deserializer throws exception
    |
    v
Listener chưa được gọi
    |
    v
Error handling / container-level failure
~~~

Với **ErrorHandlingDeserializer**, Spring Kafka có thể đưa thông tin lỗi vào headers để container/error handler xử lý và phục hồi raw bytes khi cần.

Nên theo dõi:

- consumer_deserialization_failures_total.
- error_handler_failed_deliveries_total.
- recovery_attempts_total.
- dlt_publish_confirmed_total.

Nếu chỉ nhìn listener_attempts, service có thể trông như đang **idle** dù một poison record liên tục làm poll lỗi và consumer lag tăng.

## 22. Recovery thành công chỉ khi hoàn tất đúng policy

DeadLetterPublishingRecoverer thường dùng KafkaTemplate gửi record sang DLT. Producer send có thể bất đồng bộ.

~~~text
Recoverer gọi KafkaTemplate.send()
          |
          v
Future chưa hoàn tất
          |
          v
Nếu recoverer trả về sớm, caller có thể
coi recovery success khi broker chưa ACK
          |
          v
Producer future báo lỗi sau đó
~~~

Trong các phiên bản Spring Kafka có hỗ trợ, **DeadLetterPublishingRecoverer.setFailIfSendResultIsError(true)** giúp recoverer phản ánh lỗi producer send vào recovery failure path. Cần đặt timeout chờ send result tương thích producer delivery timeout và SLO.

Tuy vậy, khi producer timeout, kết quả có thể **chưa rõ**: broker có thể đã ghi record nhưng ACK không trở lại. Nếu retry recovery, DLT có thể có duplicate.

Metrics nên phân biệt:

- Recovery attempted.
- Recovery succeeded theo contract.
- DLT publication ACK confirmed.
- DLT publication failed hoặc unknown.
- DLT records observed/consumed.

Không lấy một lần gọi send() làm bằng chứng record đã được lưu an toàn.

## 23. Khi DLT publish thành công nhưng offset chưa commit

~~~text
Source listener failed
       |
       v
DLT publish ACK success
       |
       v
Process crash trước source offset commit
       |
       v
Consumer khác redeliver source record
       |
       v
DLT publish có thể thực hiện lần nữa
~~~

Theo metrics, cùng business event có thể làm recovery_succeeded tăng hai lần trên hai process. Đây không nhất thiết là lỗi instrumentation: đó là **hai lần recovery executions thật**.

Để biết số **unique records** đã được recovery, cần dedup theo original topic/partition/offset hoặc event ID bền vững, với logic phù hợp cho replay và re-publication.

Đối với nghiệp vụ, dùng idempotency key để tránh side effect lặp khi record được replay từ nguồn hoặc DLT.

## 24. “Success after retry” khác “retry attempts succeeded”

Có ít nhất hai tỷ lệ cần phân biệt.

**Theo attempts:**

~~~text
retry_attempt_success_ratio =
  retry_attempts_ending_success
  / retry_attempts_started
~~~

Một record có thể đóng góp nhiều attempts.

**Theo records:**

~~~text
record_retry_success_ratio =
  distinct_records_succeeded_after_retry
  / distinct_records_entered_retry
~~~

Mỗi record chỉ nên được tính một lần trong cùng phạm vi nhận diện.

**Theo recovery attempts:**

~~~text
recovery_success_ratio =
  successful_completed_recovery_attempts
  / all_completed_recovery_attempts
~~~

Tỷ lệ recovery thành công không phải tỷ lệ nghiệp vụ thành công; một DLT publication thành công vẫn có thể là business failure chưa giải quyết.

Không đặt dashboard panel **Retry Success %** nếu không ghi rõ đơn vị và denominator.

## 25. Micrometer: thiết kế tên metrics

Một bộ tên gợi ý:

| Metric Micrometer | Loại | Định nghĩa |
|---|---|---|
| app.kafka.listener.attempts | Counter | Một lần bắt đầu listener |
| app.kafka.listener.failures | Counter | Một listener attempt thất bại |
| app.kafka.retry.scheduled | Counter | Retry được quyết định/lên lịch |
| app.kafka.retry.attempts | Counter | Retry execution thực sự bắt đầu |
| app.kafka.retry.failed.deliveries | Counter | Retry delivery tiếp tục thất bại |
| app.kafka.retry.topic.publish.attempts | Counter | Lần cố publish retry topic |
| app.kafka.retry.topic.publish.confirmed | Counter | Retry topic publish được ACK |
| app.kafka.recovery.attempts | Counter | Recoverer invocation |
| app.kafka.recovery.succeeded | Counter | Recovery đạt success contract |
| app.kafka.recovery.failed | Counter | Recovery hoàn tất với lỗi |
| app.kafka.dlt.publish.confirmed | Counter | DLT producer ACK success |
| app.kafka.dlt.processing.succeeded | Counter | DLT workflow xử lý thành công |
| app.kafka.retry.backoff.duration | Timer | Thời gian chờ retry |
| app.kafka.recovery.duration | Timer | Thời gian thực hiện recovery |
| app.kafka.retry.inflight | Gauge | Operations đang chờ trong app nếu được theo dõi |

Đây là **metric custom** gợi ý, không phải cam kết về metrics built-in của Spring Kafka.

Với Prometheus, Micrometer Counter thường được xuất thành tên có hậu tố **_total** theo naming convention. Cần xác nhận tên và labels trong endpoint metrics thực tế trước khi viết PromQL.

## 26. Đặt tags có kiểm soát

Một bộ labels:

~~~text
service         = order-service
listener_id     = orders-listener
consumer_group  = orders-worker
topic           = orders.events
stage           = main | retry | dlt
mode            = blocking | non_blocking
exception_group = timeout | throttling | schema | validation | other
outcome         = attempted | succeeded | failed
~~~

Không nên dùng:

- eventId, orderId, customerId.
- Kafka key tùy ý.
- Raw payload.
- Exception message tự do.
- Stack trace.
- URL có query parameters động.
- Attempt index không giới hạn.

Các giá trị này gây **high cardinality** nếu đặt làm Prometheus labels. Event ID, topic-partition-offset và correlation ID nên xuất trong structured logs/traces.

### 26.1. Exception classification

Lỗi listener thường được bọc trong exception framework. Nếu chỉ tag wrapper class như ListenerExecutionFailedException, mọi lỗi có thể trở thành cùng một nhóm.

Có thể phân loại nguyên nhân gốc thành:

~~~text
timeout
throttling
dependency_unavailable
deserialization
schema_incompatible
validation
authorization
transaction
other
~~~

Lưu ý phân loại root cause có giới hạn và tránh ghi dữ liệu nhạy cảm. Một timeout có thể do dependency tạm lỗi hoặc cấu hình sai; không phải cứ thấy TimeoutException là nên retry vô hạn.

## 27. Dashboard cần cả counters lẫn độ trễ

Retry count không tự nói được retry có hiệu quả hay không. Ví dụ:

~~~text
Policy A: 3 retries, mỗi lần 100 ms
Policy B: 3 retries, mỗi lần 60 giây
~~~

Cả hai có retry_attempts = 3, nhưng ảnh hưởng tới consumer lag và processing SLO rất khác nhau.

Nên thêm:

- Retry backoff duration p50/p95/p99.
- Time to business success.
- Time to DLT recovery.
- Retry topic wait duration.
- Oldest retry record age.
- Consumer lag theo partition.
- Retry queue/topic depth.
- DLT oldest unreviewed record age.

Một dashboard đầy đủ gồm:

**Input/processing:** listener attempts, first-attempt successes, processing failures, business success rate.

**Retry:** blocking retry rate, retry-topic publish/consume rate, retry duration và success-after-retry.

**Recovery:** recovery attempts/success/failures, DLT publication, recovery latency.

**Backlog:** retry topic lag, DLT backlog, oldest record age.

**Stability:** rebalance, offset commit errors, producer send errors, transaction abort/fencing.

## 28. Prometheus Counter sau restart

Counters của Micrometer thường là **cumulative per-process**. Khi pod restart, counter bắt đầu lại từ 0. Vì thế:

- Không lấy giá trị counter hiện tại làm số attempts từ đầu tháng trên toàn hệ thống.
- Dùng **rate()** để tính attempts mỗi giây.
- Dùng **increase()** để ước lượng số lần tăng trong cửa sổ.
- Tổng hợp qua các instances theo cùng semantic scope.

Ví dụ retry rate:

~~~promql
sum by (listener_id) (
  rate(app_kafka_retry_attempts_total[5m])
)
~~~

Retry attempts trong một giờ:

~~~promql
sum by (listener_id) (
  increase(app_kafka_retry_attempts_total[1h])
)
~~~

Những query này giả định ứng dụng export metric tương ứng. Tên labels thực tế phải được kiểm tra trên exporter.

### 28.1. Tỷ lệ retry attempts trên tổng attempts

~~~promql
sum(rate(app_kafka_retry_attempts_total[5m]))
/
clamp_min(
  sum(rate(app_kafka_listener_attempts_total[5m])),
  0.000001
)
~~~

Đây là **ratio số attempts**, không phải xác suất một source record phải retry. Numerator và denominator phải đo cùng scope; nếu một metric bao gồm retry topic còn metric kia chỉ main topic thì tỷ lệ không còn có ý nghĩa.

## 29. PromQL cho recovery outcomes

Recovery attempts mỗi giây:

~~~promql
sum by (listener_id) (
  rate(app_kafka_recovery_attempts_total[5m])
)
~~~

Recovery failures trong 15 phút:

~~~promql
sum by (listener_id, exception_group) (
  increase(app_kafka_recovery_failed_total[15m])
)
~~~

Tỷ lệ recovery failed trong các attempts đã có outcome:

~~~promql
sum(rate(app_kafka_recovery_failed_total[10m]))
/
clamp_min(
  sum(rate(app_kafka_recovery_succeeded_total[10m]))
  +
  sum(rate(app_kafka_recovery_failed_total[10m])),
  0.000001
)
~~~

Lưu ý thời gian metric scrape, counter reset và các recovery operations còn in-flight. Tỷ lệ này không chứng minh data loss hoặc số unique records bị ảnh hưởng.

## 30. Retry storm: dấu hiệu và cảnh báo

Retry storm là tình trạng nhiều records hoặc một số ít records được thử lại liên tục, làm quá tải consumer thread, Kafka producer và dependency.

Dấu hiệu:

- Retry attempts/sec tăng mạnh.
- Listener success rate giảm.
- Failed delivery rate cao.
- Consumer lag và oldest record age tăng.
- HTTP/database error rate và connection pool pressure tăng.
- Retry-topic backlog tăng.

Một alert nên xét nhiều điều kiện:

~~~text
retry rate cao
AND failure rate cao
AND (consumer lag tăng OR processing success giảm)
~~~

Nếu input traffic tăng gấp mười thì retry count tuyệt đối cũng có thể tăng dù tỷ lệ retry không đổi. Do đó, ngoài retry count nên đo tỷ lệ trên attempts/records với denominator rõ ràng.

Hướng xử lý:

1. Nhóm exceptions theo root cause.
2. Xác định lỗi transient hay permanent.
3. Kiểm tra backoff và retry budget.
4. Giảm concurrency/circuit breaker/pause khi downstream không chịu nổi tải.
5. Không tăng retries vô hạn để làm count recovery thấp đi.

## 31. Recovery count tăng có phải tín hiệu tốt?

Không nhất thiết. **Recovery succeeded tăng** có thể chứng minh hệ thống đã ghi DLT an toàn, nhưng đồng thời báo hiệu nhiều business events không thể xử lý bình thường.

Khi recovery tăng:

- Xem DLT publish thực sự được ACK chưa.
- So sánh recovery rate với initial record rate.
- Xác định exception groups gây nhiều recoveries.
- Kiểm tra producer/schema/dependency changes gần đây.
- Xem DLT backlog và owner xử lý.
- Đo thời gian từ DLT đến khi nghiệp vụ được sửa/replay.

Một dashboard có thể đồng thời hiển thị:

~~~text
Recovery succeeded: high
Business success:   low
DLT backlog:        growing
~~~

Đây là tín hiệu **cơ chế bảo vệ dữ liệu còn hoạt động nhưng luồng nghiệp vụ đang suy giảm**, không phải pipeline đã khỏe mạnh.

## 32. Recovery failure cần được cảnh báo riêng

Recovery failed có thể xảy ra do:

- DLT topic không tồn tại.
- Thiếu Write ACL.
- Serializer không hỗ trợ raw byte[] của lỗi deserialization.
- Partition đích không hợp lệ.
- Broker unavailable hoặc ISR không đủ.
- Producer delivery timeout.
- Record quá lớn.
- Recovery transaction không commit.

Nếu DLT publish chưa được xác nhận, **không nên coi source record đã recover** và commit offset chỉ để lag giảm. Tùy policy, error handler cần giữ khả năng redelivery, retry recovery, pause hoặc chuyển sang đường lưu bền vững khác.

Một metric **recovery_failed_total > 0 kéo dài** thường đáng ưu tiên cao, vì tuyến bảo vệ record lỗi cũng đang bị ảnh hưởng.

## 33. Cửa sổ timeout không chắc DLT chưa ghi

Trường hợp:

~~~text
DLT producer gửi record
      |
      v
Broker append thành công
      |
      v
ACK bị mất do network
      |
      v
Producer báo timeout
      |
      v
Recovery được thử lại
~~~

Khi đó một source record có thể tạo hai DLT records. DLT publication attempt count và số actual records có thể không khớp:

~~~text
publish_attempts = 2
confirmed_success = 1
unknown_timeout = 1
DLT actual copies = có thể 1 hoặc 2
~~~

Không dùng **publish_attempts - failures** làm bằng chứng duy nhất về số record thực tế broker đã lưu, vì timeout có kết quả bất định.

DLT consumer cần dedup theo event ID hoặc original topic-partition-offset nếu workflow yêu cầu.

## 34. Không đếm trùng qua nhiều instrumentation layers

Một listener failure có thể được quan sát ở ba chỗ:

~~~text
Listener catch -> increment failure
       |
       v
DefaultErrorHandler.failedDelivery -> increment failure
       |
       v
Micrometer observation.exception -> increment failure
~~~

Nếu một dashboard cộng cả ba mà không phân biệt, một lỗi được tính ba lần.

Quy tắc:

1. Định nghĩa một **semantic event** cho mỗi metric.
2. Chọn **một instrumentation owner**.
3. Nếu nhiều lớp đều cần đo, đặt tên metrics phản ánh từng boundary.
4. Không cộng metrics từ các lớp có đơn vị khác nhau.
5. Dùng trace/log correlation để đối chiếu từng record, không gắn event ID làm Prometheus label.

Ví dụ mapping:

| Semantic event | Owner đề xuất |
|---|---|
| Listener bắt đầu attempt | Listener/interceptor/observation |
| Listener attempt thất bại | Listener/interceptor/observation |
| Error handler thấy failed delivery | RetryListener |
| Recoverer invocation | Recoverer decorator |
| Recovery outcome | RetryListener hoặc decorator, chọn một |
| Producer DLT ACK success | Producer send-result instrumentation |
| DLT workflow completed | DLT consumer |

## 35. Khi consumer restart hoặc rebalance

Một record có thể được xử lý trên nhiều pods:

~~~text
Pod A:
  Attempt 1 fail
  Attempt 2 fail
  Crash trước commit

Pod B:
  Attempt 1 trong process mới fail
  Attempt 2 thành công
~~~

Local metrics:

~~~text
Pod A listener attempts = 2
Pod B listener attempts = 2
~~~

Business-level reality: cùng một event đã được xử lý ít nhất bốn lần.

Không thể sử dụng một attempt header cục bộ hoặc counter của pod mới để biết lifetime attempts xuyên restart. Nếu cần audit cấp event, sử dụng event ID ổn định và durable event history/tracing.

Với non-blocking retry, Kafka topic-partition-offset cũng thay đổi qua các retry topics. Original metadata và event ID giúp liên kết đường đi.

## 36. Idempotency và duplicate metrics

Một source record có thể replay sau khi database update thành công nhưng Kafka offset chưa commit. Kafka transaction cũng không tự bao gồm HTTP/database side effects bên ngoài Kafka.

Nên có:

- processed_events/inbox table với unique constraint.
- Event ID ổn định qua mọi retry và DLT replay.
- Idempotency key cho HTTP API nếu có side effect.
- Metric **idempotency_dedup_hits_total** khi gặp một event đã xử lý.

Một retry count cao không nhất thiết đồng nghĩa nhiều business side effects nếu idempotency hoạt động. Ngược lại, retry count thấp không loại trừ business duplicate do client gửi lại command với event ID khác.

Tách **transport retries** khỏi **business idempotency outcomes**.

## 37. Retry count thấp không luôn có nghĩa consumer khỏe

Retry metrics có thể bằng 0 vì:

- Topic không có message.
- Consumer đã stopped.
- Container đang paused.
- Không được assign partition.
- Deserializer lỗi trước listener nhưng instrumentation thiếu.
- Consumer poll thread non-responsive.
- DLT recovery đã xong và record rời luồng chính.

Khi đánh giá thấp/cao, phải ghép:

- Listener running state.
- Assigned partitions.
- Last-delivered/last-success age.
- Consumer lag.
- Retry topic lag.
- Producer input rate.
- Poll responsiveness và NonResponsiveConsumerEvent.

Chỉ số retry bằng 0 không tự chứng minh pipeline xử lý thành công.

## 38. Recovery count bằng 0 khi retry vô hạn

Một poison record có thể được retry vô hạn:

~~~text
Retry #1 -> fail
Retry #2 -> fail
Retry #3 -> fail
...
Retry #100000 -> fail

recovery_succeeded = 0
~~~

Không kết luận hệ thống khỏe chỉ vì không có DLT/recovery events. Nên alert khi:

- Retry attempt rate cao kéo dài.
- Same source offset xuất hiện lặp nhiều lần trong logs.
- Oldest retry age vượt SLO.
- Listener success rate thấp.
- Lag tăng.

Với permanent errors, bounded retry rồi DLT/recovery thường là chính sách dễ vận hành hơn retry không giới hạn.

## 39. Runbook: retry count tăng, recovery count thấp

**Bước 1:** Xác nhận metric retry đếm retry started hay failed delivery; nếu instrumentation chưa đúng, số liệu cần được diễn giải lại.

**Bước 2:** Kiểm tra exception groups và dependency health. HTTP timeout, 503 hoặc throttling có thể là transient; invalid payload và schema mismatch thường không tự phục hồi chỉ vì backoff.

**Bước 3:** Kiểm tra retry budget, backoff và chính sách unlimited retries. Nếu record còn ở retry topics, recovery cuối chưa xảy ra.

**Bước 4:** Xem success-after-retry, consumer lag, oldest record age và throughput. Retry tăng nhưng successes vẫn tăng có thể là degradation tạm thời; retry tăng trong khi throughput gần 0 có thể là retry storm.

**Bước 5:** Điều chỉnh concurrency/backoff/circuit breaker hoặc đưa lỗi permanent sang recovery. Tránh restart consumer vô điều kiện làm rebalance và duplicate tăng.

## 40. Runbook: recovery count tăng bất thường

1. Xác định topic/listener/exception_group tạo recovery.
2. So sánh với thời điểm deploy producer/schema/consumer.
3. Kiểm tra số initial deliveries và tỷ lệ recovery trên records.
4. Xác nhận recoverer có thực sự publish DLT hoặc durable destination.
5. Xem DLT incoming count, DLT backlog và oldest unreviewed age.
6. Giao owner xử lý DLT và quy trình replay.
7. Sửa root cause như validation, schema evolution, dependency hoặc ACL.
8. Theo dõi recovery rate giảm và business success rate phục hồi.

Đừng chỉ xem recovery success như thông báo tốt: record vẫn chưa hoàn tất nghiệp vụ nếu đã được đưa vào DLT.

## 41. Runbook: recovery_failed_total tăng

1. Kiểm tra producer send result của recoverer và timeout thực tế.
2. Xem Kafka broker/topic/partition/ISR.
3. Kiểm tra ACL và credential cho DLT KafkaTemplate.
4. Kiểm tra serializer, đặc biệt original raw byte[] do ErrorHandlingDeserializer.
5. Kiểm tra record size và header size.
6. Xác minh recoverer không swallow exception rồi return bình thường.
7. Xác minh offset nguồn chưa được đánh dấu recovered nếu publication chưa an toàn.
8. Nếu recovery bị lặp liên tục, giảm retry storm hoặc pause có kiểm soát.
9. Sau khôi phục, xem DLT publication confirmed tăng, recovery failures giảm và source consumer tiến triển.
10. Đối soát duplicate DLT nếu đã có các producer timeouts với kết quả chưa rõ.

## 42. Kiểm thử định nghĩa counters

Trong một môi trường Kafka test có kiểm soát, kiểm thử các scenario với một record và một processing chain, không có restart/rebalance:

| Trường hợp | Listener attempts | Retry attempts | Recovery attempts | Recovery success | Recovery failure |
|---|---:|---:|---:|---:|---:|
| Thành công lần đầu | 1 | 0 | 0 | 0 | 0 |
| Fail lần đầu, thành công lần hai | 2 | 1 | 0 | 0 | 0 |
| Permanent exception, DLT thành công | 1 | 0 | 1 | 1 | 0 |
| Hai retries đều fail, DLT thành công | 3 | 2 | 1 | 1 | 0 |
| Hai retries fail, DLT publish thất bại | 3 | 2 | 1 | 0 | 1 |

Giá trị chỉ là **mô hình logic theo định nghĩa**. Actual callback counts có thể khác nếu metric instrument failed deliveries, stage transfers hoặc recovery failure redelivery. Test phải phù hợp với semantic owner đã được viết trong tài liệu instrumentation.

Các ca kiểm thử bổ sung:

- Lần retry thành công không tạo failedDelivery callback.
- Blocking + non-blocking retry cùng lúc.
- Retry topic publish thành công nhưng chưa được consume.
- DLT producer timeout ambiguous.
- Crash sau DLT ACK trước source offset commit.
- Consumer rebalance giữa retry attempts.
- Batch listener chỉ một poison record.
- Deserialization error xảy ra trước @KafkaListener.
- Transaction rollback và AfterRollbackProcessor.
- Counter reset sau pod restart.

## 43. Test phát hiện double count

Một luồng:

~~~text
Listener #1 -> fail
Error handler callback
Listener #2 -> success
~~~

Theo mục tiêu instrumentation:

~~~text
listener_attempts_total    +2
listener_failures_total    +1
retry_attempts_total       +1
recovery_attempts_total    +0
~~~

Nếu retry_attempts_total tăng 2, có thể lần đầu đã bị tính là retry. Nếu listener_failures_total tăng 2 dù chỉ một failed attempt, có thể listener catch và error handler cùng cập nhật metric này.

Tách metric error-handler failed deliveries riêng nếu cả hai có ích; đừng cộng chúng như các failed records khác nhau.

## 44. Cumulative count không đo thời gian chờ

Hai policy đều retry ba lần nhưng tác động rất khác:

~~~text
Policy A:
  3 retries với backoff 200 ms
  Tổng backoff khoảng 600 ms

Policy B:
  3 retries với backoff 60 giây
  Tổng backoff khoảng 180 giây
~~~

Nếu chỉ nhìn retry_count=3, không thể đánh giá consumer có kịp SLO hay không.

Nên bổ sung:

- Retry backoff duration histogram.
- Recovery duration histogram.
- Retry topic delay/age.
- End-to-end processing latency.
- Time since last business success.
- Consumer lag/oldest unprocessed record age.

Với retry topic, delay được cấu hình không phải chính xác thời điểm record được xử lý: poll cadence và backlog có thể làm nó trễ hơn.

## 45. Tổng hợp theo một dashboard vận hành

Một dashboard hiệu quả có thể sắp theo các khối:

**Listener throughput**

- Initial deliveries/sec.
- Listener attempts/sec.
- Listener failures/sec.
- Business successes/sec.

**Retry**

- Retry started/sec.
- Retry scheduled/sec.
- Retry success-after-attempt rate.
- Blocking vs non-blocking breakdown.
- Retry-topic lag và oldest age.

**Recovery**

- Recoverer attempts/sec.
- Recovery succeeded/failed.
- DLT producer ACK success/failure.
- Recovery latency.
- DLT backlog và manual-review age.

**System health**

- Consumer lag và assigned partitions.
- Listener paused/stopped/non-responsive.
- Rebalance và offset commit errors.
- Producer errors, transaction abort/fencing.
- Downstream dependency error rate.
- Idempotency duplicate hits.

Trong sự cố, dashboard giúp trả lời ba câu hỏi: **record còn tiến triển không, lỗi đang được retry có ích không, và đường recovery có còn ghi dữ liệu an toàn không?**

## 46. Các lỗi thiết kế thường gặp

| Sai lầm | Hậu quả | Cách điều chỉnh |
|---|---|---|
| Gọi mọi failed delivery là retry | Tính cả lỗi lần đầu | Phân biệt failure và retry started |
| Lấy configured retry limit làm actual count | Sai khi retry thành công sớm/restart | Instrument actual attempts |
| Chỉ đếm failed retries | Bỏ sót lần retry thành công | Đếm lúc retry bắt đầu |
| Coi recoverer invocation là recovery success | DLT send có thể thất bại | Tách attempts/succeeded/failed |
| Coi DLT publication là business success | Nghiệp vụ chưa hoàn tất | Business metric riêng |
| Cộng counters ở listener và error handler | Double count | Một owner cho mỗi semantic event |
| Coi số retry topic records bằng retries executed | Publish chưa chắc đã được consume | Tách publish và delivery |
| Gộp batch failure thành record failure | Sai đơn vị | Metrics batch-level và record-level riêng |
| Không instrument poll-time errors | Thiếu poison records | ErrorHandlingDeserializer/error handler telemetry |
| Bỏ qua transactional rollback path | Thiếu retries/recovery trong transaction | Instrument AfterRollbackProcessor |
| Dùng event ID/exception message làm labels | Cardinality bùng nổ | Bounded taxonomy, IDs ở logs |
| Chỉ nhìn cumulative counters | Bị ảnh hưởng pod restart, traffic volume | Dùng rate/increase |
| Recovery count thấp được xem là khỏe | Unlimited retries có thể kẹt | Xem retry age, lag và successes |
| Không đo DLT backlog | Recovery xong nhưng lỗi bị bỏ quên | DLT oldest age và owner |
| Chỉ tăng retry limit khi lỗi nhiều | Có thể tạo retry storm | Phân loại exception và backpressure |
| Không phân biệt timeout unknown outcome | Tưởng DLT chưa ghi, tạo duplicate | Idempotency và recovery reconciliation |

## 47. Checklist production

Trước khi dùng retry count và recovery count để cảnh báo và ra quyết định:

1. Đã định nghĩa metric theo **attempt**, **record**, **batch** hay **business event** chưa?
2. Retry attempts có loại lần xử lý đầu tiên không?
3. Có phân biệt retry scheduled và retry actually started không?
4. Listener failure và error-handler failed delivery có được đặt tên khác nếu cùng tồn tại không?
5. DefaultErrorHandler/RetryListener có đang gắn vào listener container thực sự không?
6. Có observer tương ứng cho transactional AfterRollbackProcessor không?
7. @RetryableTopic có metrics cho publish và consumer delivery riêng không?
8. Hybrid retry có tách blocking và non-blocking attempts không?
9. Recovery attempts, succeeded và failed có counters riêng không?
10. DLT publish success có dựa trên producer acknowledgement phù hợp không?
11. DLT handler business success có được tách khỏi DLT publication không?
12. Có chống double count qua nhiều layers không?
13. Exception labels có được giới hạn và phân nhóm root cause không?
14. Có tránh event ID, Kafka key và raw payload trong Prometheus labels không?
15. Dashboard có sử dụng rate/increase cho cumulative counters không?
16. Có kết hợp retry metrics với consumer lag, processing success và oldest age không?
17. Có alert retry storm và recovery failed phù hợp mức độ ảnh hưởng không?
18. Có metric đo retry duration và recovery duration không?
19. Có test transient success, permanent DLT, DLT failure, retry topic và transactional rollback không?
20. Có runbook xử lý DLT và replay idempotent không?

## 48. Kết luận

**Retry count** cần trả lời hệ thống đã **thực sự thử lại bao nhiêu lần**, còn **recovery count** cần trả lời đã **cố phục hồi bao nhiêu lần** và có **bao nhiêu recovery thành công/thất bại theo hợp đồng**. Một failed delivery đầu tiên chưa phải retry; một lần gọi recoverer chưa chắc là recovery success; DLT publication thành công cũng chưa phải xử lý nghiệp vụ thành công.

Trong Spring Kafka, hãy theo dõi đúng các ranh giới: listener execution, DefaultErrorHandler/RetryListener, retry-topic publication và consumption, DeadLetterPublishingRecoverer, Kafka producer acknowledgement, DLT consumer workflow và transactional rollback. Trên Micrometer/Prometheus, dùng counters có định nghĩa chính xác, labels hữu hạn, rate/increase theo thời gian, và ghép với retry latency, consumer lag, oldest record age cùng business success.

Khi số liệu không bị đếm trùng và được kiểm chứng qua các kịch bản lỗi, hệ thống sẽ phân biệt được **transient retries đang giúp phục hồi**, **retry storm không còn tiến triển**, **poison records đang đi vào recovery** và **đường DLT/recovery đã bị hỏng**. Đó mới là mục tiêu của monitoring: bảo vệ dữ liệu, giảm tác động sự cố và giúp consumer trở lại trạng thái xử lý ổn định.
