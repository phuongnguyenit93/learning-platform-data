# Theo dõi retry latency trong Spring Kafka

Trong một consumer Spring Kafka, retry latency là khoảng thời gian bổ sung mà một record phải chịu khi xử lý thất bại và được thử lại. Theo dõi chỉ số này giúp phân biệt một dịch vụ đang chậm vì **nghiệp vụ xử lý lâu**, vì **chờ backoff**, vì **record nằm trong retry topic**, hay vì **Kafka consumer bị backlog**. Đây là khác biệt quan trọng khi xây dựng SLO, cảnh báo, dashboard và quy trình xử lý sự cố.

Không có một metric duy nhất tên “retry latency” đủ mô tả mọi tình huống. Với hệ thống đáng tin cậy, cần xác định rõ mốc bắt đầu, mốc kết thúc, trường hợp thành công và trường hợp phải chuyển DLT. Đồng thời phải nhận ra hai mô hình retry phổ biến trong Spring Kafka: retry tại listener container với `DefaultErrorHandler`, và retry thông qua các topic riêng với `@RetryableTopic`.

Bài học này tập trung vào cách thiết kế và diễn giải việc đo latency, cách thu thập metrics và traces, cách quan sát retry theo từng attempt, cùng những tình huống có thể gây hiểu sai khi vận hành.

## 1. Trước tiên phải định nghĩa đúng latency

Một record có thể trải qua nhiều mốc thời gian:

```text
Producer gửi event             10:00:00.000
    |
Kafka lưu event                10:00:00.040
    |
Consumer bắt đầu lần 1         10:00:00.140
    |  Xử lý 120 ms -> lỗi
Bắt đầu chờ retry              10:00:00.260
    |  Chờ 1.000 ms
Consumer bắt đầu lần 2         10:00:01.260
    |  Xử lý 180 ms -> lỗi
Bắt đầu chờ retry              10:00:01.440
    |  Chờ 2.000 ms
Consumer bắt đầu lần 3         10:00:03.440
    |  Xử lý 160 ms -> thành công
Nghiệp vụ hoàn tất             10:00:03.600
    |
Offset được commit             sau đó
```

Từ cùng một hành trình, có thể tính các metric khác nhau:

| Metric | Mốc bắt đầu → kết thúc | Giá trị trong ví dụ | Diễn giải |
|---|---|---:|---|
| Attempt processing latency | Bắt đầu → kết thúc một lần gọi listener | 120, 180, 160 ms | Thời gian xử lý từng attempt |
| Retry wait / backoff | Một lần thất bại → lần thử tiếp theo | 1.000 và 2.000 ms | Thời gian record chờ giữa các lần |
| Total retry wait | Tổng các khoảng chờ retry | 3.000 ms | Phần chờ theo kế hoạch |
| Time from first attempt to success | Lần gọi đầu → nghiệp vụ thành công | 3.460 ms | Tổng thời gian xử lý và chờ retry |
| Event end-to-end latency | Event được gửi → nghiệp vụ thành công | 3.600 ms | Gồm thời gian trước khi consumer xử lý |
| Commit latency | Bắt đầu commit → Kafka xác nhận commit | Phụ thuộc thực tế | Thời gian xác nhận offset |

Các mốc trên không thể thay thế lẫn nhau. Một dashboard chỉ hiển thị thời gian listener xử lý 160 ms ở lần cuối có thể trông rất tốt, dù sự kiện thực tế đã chờ hơn ba giây.

### 1.1. Attempt processing latency

Đây là thời gian chạy một lần xử lý nghiệp vụ, thường đo từ lúc listener bắt đầu đến lúc listener trả về hoặc ném exception. Nó phù hợp để theo dõi hiệu năng database, HTTP dependency, serialize/deserialize trong phần xử lý hoặc CPU.

Nếu record retry ba lần, cần có ba phép đo attempt tương ứng. Tách được các phép đo này giúp nhận biết retry do xử lý chậm hay do lỗi xảy ra nhanh rồi phải chờ lâu.

### 1.2. Retry delay dự kiến và retry delay thực tế

`BackOff` quy định thời gian chờ dự kiến giữa các attempt. Đó mới là **lịch retry**, chưa chắc là độ trễ thực tế.

Cần phân biệt:

- **Configured delay:** thời gian dự kiến theo `FixedBackOff`, exponential backoff hoặc retry topic schedule.
- **Actual delay:** khoảng thời gian từ lần thất bại đến khi listener thực sự bắt đầu attempt tiếp theo.
- **Scheduling drift:** phần chênh lệch giữa actual delay và configured delay.

Actual delay có thể dài hơn vì consumer bị pause, poll bị chậm, broker không sẵn sàng, topic retry có backlog, rebalance hoặc tài nguyên hệ thống bị bão hòa.

### 1.3. Retry completion latency

Metric này đo từ lần xử lý đầu tiên đến khi nghiệp vụ thành công hoặc đến khi record được chuyển sang recovery. Nó phù hợp để trả lời câu hỏi: “Sau khi bắt đầu xử lý, một event cần bao lâu để đạt trạng thái cuối cùng?”

Nên tách trạng thái kết thúc:

- `success`: nghiệp vụ hoàn tất thành công.
- `recovered`: record được xử lý bởi recoverer, ví dụ gửi DLT thành công.
- `failed`: recovery cũng thất bại hoặc vẫn còn trong trạng thái cần xử lý.

Một record đã đến DLT không nên được thống kê như một lần xử lý nghiệp vụ thành công. Chuyển DLT chỉ là kết quả của luồng xử lý lỗi.

### 1.4. End-to-end latency

Đây là thời gian từ lúc event được tạo/gửi đến lúc nghiệp vụ đích hoàn tất. Chỉ số này bao gồm thời gian lưu trong Kafka trước khi consumer đọc, thời gian xử lý, retry và các quãng chờ khác.

Khi mục tiêu là “95% order event được áp dụng trong 30 giây”, end-to-end latency mới là thước đo trực tiếp của SLO. Retry latency chỉ giải thích một phần nguyên nhân làm SLO bị vi phạm.

## 2. Retry blocking và retry topic tạo ra latency khác nhau

Spring Kafka có hai mô hình retry phổ biến.

### 2.1. Blocking retry tại listener container

Với `DefaultErrorHandler`, record lỗi được retry trong quá trình vận hành của listener container. Tùy cấu hình và phiên bản, container có thể seek để đọc lại record hoặc giữ record trong bộ nhớ và giao lại. Backoff được áp dụng trước các lần thử tiếp theo.

Ví dụ:

```java
@Bean
DefaultErrorHandler orderErrorHandler() {
    FixedBackOff backOff = new FixedBackOff(
            1_000L,  // 1 giây giữa các retry
            3L       // tối đa 3 lần retry sau lần xử lý đầu
    );

    return new DefaultErrorHandler(backOff);
}
```

Cấu hình trên cho phép tối đa bốn lần listener được gọi nếu lỗi liên tục: một lần đầu và ba lần retry. Với ba lần chờ một giây, tổng backoff dự kiến tối đa là ba giây, chưa cộng thời gian xử lý các attempt và các overhead khác.

Blocking retry có thể làm chậm tiến độ của partition đang xử lý. Khi record đứng đầu luồng xử lý bị lỗi liên tục, những record khác có thể phải chờ, làm tăng consumer lag hoặc end-to-end latency của các record không có lỗi.

Cần quan sát:

- Số lần listener thất bại và số attempt.
- Thời gian xử lý từng attempt.
- Khoảng chờ giữa các attempt.
- Tổng thời gian cho một record trước success/recovery.
- Consumer lag và thời gian consumer không poll.
- Commit offset sau thành công hoặc recovery.

### 2.2. Non-blocking retry qua retry topic

Với `@RetryableTopic`, record lỗi được chuyển qua các topic retry theo lịch chờ. Một ví dụ:

```java
@RetryableTopic(
    attempts = "4",
    backoff = @Backoff(delay = 1_000, multiplier = 2.0)
)
@KafkaListener(
    topics = "orders.created",
    groupId = "billing-service"
)
public void handle(OrderCreated event) {
    billingService.process(event);
}
```

`attempts` ở đây bao gồm lần xử lý ban đầu. Retry có thể đi qua các topic trung gian trước khi đến DLT nếu không xử lý thành công. Cách đặt tên topic, hành vi DLT và các thành phần được tạo phụ thuộc cấu hình Spring Kafka.

Với retry topic, latency còn có thêm:

- Thời gian publish record sang retry topic.
- Thời gian chờ đến timestamp được phép xử lý lại.
- Thời gian record nằm trong backlog của retry topic.
- Thời gian consumer retry được phân bổ partition và nhận record.
- Chi phí nhiều lần chuyển tiếp giữa topic.
- Thời gian đi vào DLT nếu hết attempts.

Retry topic giúp record phía sau trong topic chính tiếp tục xử lý, nhưng thay đổi đặc tính thứ tự và tăng số thành phần cần giám sát.

### 2.3. Bảng so sánh điều cần đo

| Khía cạnh | DefaultErrorHandler | @RetryableTopic |
|---|---|---|
| Retry diễn ra ở đâu | Listener container xử lý lại | Qua một hoặc nhiều retry topic |
| Backoff | Do `BackOff` và handler/container thực hiện | Theo lịch giao nhận của retry topic |
| Đối tượng giám sát thêm | Retry attempts, pause/seek, poll, lag | Retry topic lag, publish, due timestamp, các consumer retry |
| Khả năng giữ thứ tự partition gốc | Dễ duy trì hơn trong blocking retry | Có thể thay đổi thứ tự quan sát ở tầng nghiệp vụ |
| Lỗi cần chú ý | Partition bị kẹt, thời gian giữa poll dài | Topic retry backlog, lịch retry bị trễ, nhiều tầng chuyển tiếp |
| Metric end-to-end | Cần lưu mốc lần xử lý đầu | Cần mốc bền vững qua nhiều topic/consumer |

## 3. Những metric cần có trên dashboard

Một dashboard hữu ích nên hiển thị cùng lúc latency, số lượng retry và backlog. Chỉ nhìn một nhóm metric dễ dẫn đến chẩn đoán sai.

| Metric đề xuất | Loại | Mục đích |
|---|---|---|
| `app.kafka.listener.attempt` | Timer | Thời gian xử lý mỗi attempt |
| `app.kafka.retry.failures` | Counter | Số lần xử lý thất bại và bắt đầu đường retry/recovery |
| `app.kafka.retry.actual_delay` | Timer hoặc DistributionSummary | Thời gian thực tế giữa hai lần xử lý |
| `app.kafka.retry.schedule_drift` | Timer hoặc DistributionSummary | Chênh lệch so với lịch backoff |
| `app.kafka.retry.completion` | Timer | Thời gian từ lần xử lý đầu đến outcome cuối |
| `app.kafka.event.end_to_end` | Timer | Thời gian từ mốc event đến nghiệp vụ thành công |
| `app.kafka.retry.recovered` | Counter | Số record đi qua recoverer thành công |
| `app.kafka.retry.recovery_failed` | Counter | Số lần recovery không hoàn tất |
| Consumer group lag | Gauge/metrics Kafka | Số record chưa hoàn tất theo offset đã commit |
| Retry topic lag | Gauge/metrics Kafka | Backlog riêng trong các retry topic |
| DLT message rate | Counter | Lưu lượng bản ghi không xử lý được |

Tên `app.kafka.*` là ví dụ metric tùy chỉnh của ứng dụng, **không phải** lời khẳng định Spring Kafka tự xuất ra tất cả metric này. Những metric nào phải instrument thủ công sẽ phụ thuộc phiên bản Spring Kafka, Micrometer và cơ chế retry sử dụng.

Một thiết kế dashboard nên chia thành ba lớp:

1. **Nghiệp vụ:** end-to-end latency, success rate, SLO violations.
2. **Retry:** attempt count, backoff, completion latency, recovery/DLT.
3. **Hạ tầng:** Kafka consumer lag, rebalance, broker/network latency và tài nguyên của service.

Kết hợp ba lớp giúp tìm được nguyên nhân tăng latency thay vì chỉ biết hệ thống đang chậm.

## 4. Đặt tag thế nào để metric hữu ích?

Nên giữ số lượng giá trị tag hữu hạn và có ý nghĩa vận hành.

| Tag | Ví dụ | Ghi chú |
|---|---|---|
| `service` | `billing-service` | Service sở hữu consumer |
| `topic` | `orders.created` | Topic nguồn, hoặc nhóm topic đã chuẩn hóa |
| `consumer_group` | `billing-service` | Dùng để phân tích lag/ownership |
| `retry_mode` | `blocking`, `topic` | Phân biệt hai mô hình |
| `outcome` | `success`, `recovered` | Tách thành công nghiệp vụ và recovery |
| `exception` | `TimeoutException` | Nên gom nhóm theo loại lỗi |
| `attempt_bucket` | `1`, `2`, `3_plus` | Tránh số lượng tag tăng vô hạn |
| `retry_stage` | `initial`, `retry`, `dlt` | Dễ phân tích đường đi |

Không sử dụng message key, order ID, correlation ID, payload, exception message hoặc Kafka offset làm metric tag. Các giá trị này có cardinality rất cao, dễ làm tăng chi phí lưu trữ metrics và ảnh hưởng hiệu năng. Đưa chúng vào log/traces có kiểm soát, rồi liên kết thông qua trace ID hoặc event ID.

Nếu mỗi retry topic chứa số ngẫu nhiên hoặc định danh động trong tên, cân nhắc chuẩn hóa label theo logical topic hoặc retry stage trước khi ghi metrics.

## 5. Đo thời gian một attempt trong listener

Đo bằng đồng hồ đơn điệu (`System.nanoTime()`) là cách phù hợp cho duration ở cùng một tiến trình. `System.currentTimeMillis()` hoặc `Clock.instant()` dùng để ghi wall-clock timestamp, nhưng có thể bị ảnh hưởng bởi đồng bộ thời gian hệ thống.

Ví dụ record listener dùng Micrometer:

```java
@Component
public class BillingListener {

    private final BillingService billingService;
    private final MeterRegistry meterRegistry;

    public BillingListener(
            BillingService billingService,
            MeterRegistry meterRegistry) {
        this.billingService = billingService;
        this.meterRegistry = meterRegistry;
    }

    @KafkaListener(
        topics = "orders.created",
        groupId = "billing-service"
    )
    public void onMessage(
            ConsumerRecord<String, OrderCreated> record) {

        long startedAtNanos = System.nanoTime();
        String outcome = "success";

        try {
            billingService.process(record.value());
        }
        catch (RuntimeException ex) {
            outcome = "error";
            throw ex;  // Để DefaultErrorHandler xử lý retry/recovery.
        }
        finally {
            long elapsedNanos = System.nanoTime() - startedAtNanos;

            Timer.builder("app.kafka.listener.attempt")
                    .description("Business processing duration per delivery")
                    .tags(
                        "topic", record.topic(),
                        "outcome", outcome
                    )
                    .publishPercentileHistogram()
                    .register(meterRegistry)
                    .record(elapsedNanos, TimeUnit.NANOSECONDS);
        }
    }
}
```

Đoạn code ghi một duration cho mỗi lần listener thực sự được gọi. Nếu cùng record được giao lại ba lần, sẽ có ba phép đo. `finally` bảo đảm cả attempt thành công và thất bại đều được ghi nhận, trong khi exception vẫn được ném lại để Spring Kafka xử lý đúng.

Cần hiểu giới hạn của metric này: nó **không bao gồm thời gian chờ backoff giữa các lần gọi**, thời gian record còn nằm trên retry topic, thời gian trước khi consumer đọc record hay thời gian commit offset sau listener.

Trong nhiều ứng dụng, Spring Kafka có Micrometer timers hoặc Micrometer Observation tích hợp cho listener. Hãy tận dụng instrumentation đó khi nó thể hiện đúng ranh giới mong muốn, tránh tạo metric trùng lặp không cần thiết.

## 6. Dùng DefaultErrorHandler để quan sát số lần thất bại

`DefaultErrorHandler` hỗ trợ `RetryListener` để nhận callback khi một lần delivery bị lỗi hoặc sau recovery. Đây là điểm tích hợp tiện lợi để ghi counter và structured log, ngoài logic trong listener.

Ví dụ cấu hình bean error handler:

```java
@Configuration
public class KafkaErrorConfiguration {

    @Bean
    public DefaultErrorHandler defaultErrorHandler(
            MeterRegistry meterRegistry) {

        DefaultErrorHandler handler =
                new DefaultErrorHandler(
                        new FixedBackOff(1_000L, 3L)
                );

        handler.setRetryListeners(
                (record, exception, deliveryAttempt) -> {
                    meterRegistry.counter(
                            "app.kafka.retry.failures",
                            "topic", record.topic(),
                            "exception",
                            exception.getClass().getSimpleName()
                    ).increment();
                }
        );

        return handler;
    }
}
```

Ở đây `deliveryAttempt` biểu thị số lần giao theo cách Spring Kafka theo dõi, nhưng không được tự động coi nó là số lần “retry đã hoàn tất” hoặc số lần retry còn lại. Nên hiểu chính xác callback được kích hoạt lúc nào trong phiên bản đang dùng và sử dụng tên metric rõ ràng như `failures`.

Có thể mở rộng `RetryListener` để quan sát `recovered` và `recoveryFailed` theo các callback tương ứng trong API của Spring Kafka. Đây là những metric khác với số lần listener thành công.

**Lưu ý:** callback retry không cung cấp sẵn một duration bao gồm toàn bộ thời gian chờ. Muốn đo actual delay phải ghép các mốc thời gian giữa các attempt, chứ không thể suy ra chỉ từ counter.

## 7. Đo thời gian giữa các retry

Để tính actual delay, cần biết khi nào attempt trước thất bại và khi nào attempt kế tiếp bắt đầu.

Ý tưởng:

```text
t0: listener attempt 1 thất bại
t1: error handler bắt đầu xử lý lỗi
t2: scheduled backoff kết thúc
t3: listener attempt 2 thật sự bắt đầu

configured delay = lịch backoff đã định
actual delay     = t3 - t0
scheduling drift = actual delay - configured delay
```

Không phải lúc nào actual delay cũng bằng thời gian `BackOff`. Nó còn chứa overhead xử lý exception, seek hoặc retain, poll, queue và scheduler.

### 7.1. Với blocking retry

Có thể quan sát thời điểm callback lỗi và thời điểm listener được gọi tiếp theo, rồi liên kết bằng bộ nhận diện record gồm topic, partition và offset trong phạm vi consumer hiện tại.

Một bộ theo dõi in-memory có thể hoạt động khi retry chỉ diễn ra trong cùng một tiến trình, nhưng cần quản lý:

- Nhiều consumer thread xử lý đồng thời.
- Rebalance khiến record chuyển sang consumer khác.
- Record hết retry hoặc được chuyển DLT.
- Cleanup sau success, recovery, timeout và shutdown.
- Memory limit nếu lỗi liên tục trên nhiều record.

Không dùng map không giới hạn lưu mọi offset lỗi trong production. Nếu cần đo thời gian qua restart hoặc rebalance, phải lưu timestamp ở nơi bền vững hoặc mang theo metadata trên message.

### 7.2. Với retry topic

Có thể lưu hoặc truy xuất hai mốc:

- **Scheduled due time:** thời điểm record được phép xử lý lại theo lịch retry.
- **Actual retry start time:** thời điểm listener retry thực sự bắt đầu.

Sau đó:

```text
retry scheduling lateness = actual retry start - scheduled due time
```

Khi lateness tăng, hãy kiểm tra retry topic lag, partition assignment, consumer pause, rebalance, throttling và tốc độ xử lý.

Đừng nhầm `scheduled due time` với thời điểm Kafka lưu record trong topic retry. Record có thể được publish ngay nhưng chỉ được xử lý ở thời điểm đến hạn; đây là delay có chủ đích.

Spring Kafka có các metadata header nội bộ cho retry topic. Tên và cách bảo tồn chúng có thể thay đổi theo phiên bản; khi xây metric tùy chỉnh, nên dùng API của phiên bản đang chạy hoặc metadata do ứng dụng quản lý, tránh hard-code tên header nội bộ chưa được xác nhận.

## 8. Đo end-to-end latency qua nhiều topic

Một timestamp gắn với record ngay từ producer có thể dùng để đo thời gian từ lúc xuất bản event đến lúc nghiệp vụ hoàn tất. Timestamp này đi cùng message qua các lần chuyển tiếp nếu pipeline bảo toàn header.

Ví dụ producer ghi một header ứng dụng:

```java
ProducerRecord<String, OrderCreated> record =
        new ProducerRecord<>(
                "orders.created",
                event.orderId(),
                event
        );

byte[] publishedAt = ByteBuffer
        .allocate(Long.BYTES)
        .putLong(clock.millis())
        .array();

record.headers().add("x-event-published-at-ms", publishedAt);
kafkaTemplate.send(record);
```

Consumer đọc timestamp và ghi metric sau khi nghiệp vụ thành công:

```java
@KafkaListener(
    topics = "orders.created",
    groupId = "billing-service"
)
public void onOrderCreated(
        ConsumerRecord<String, OrderCreated> record) {

    billingService.process(record.value());

    Header header =
            record.headers().lastHeader("x-event-published-at-ms");

    if (header == null || header.value().length != Long.BYTES) {
        return;
    }

    long publishedAtMillis =
            ByteBuffer.wrap(header.value()).getLong();

    long elapsedMillis = clock.millis() - publishedAtMillis;

    if (elapsedMillis >= 0) {
        Timer.builder("app.kafka.event.end_to_end")
                .tags(
                    "topic", record.topic(),
                    "outcome", "success"
                )
                .publishPercentileHistogram()
                .register(meterRegistry)
                .record(elapsedMillis, TimeUnit.MILLISECONDS);
    }
}
```

`clock` và `meterRegistry` ở đây là dependency đã được inject vào bean. Ví dụ đo duration **đến thời điểm nghiệp vụ hoàn tất trong listener**; nó không bao gồm thời gian Kafka commit offset sau đó.

Cách đo này áp dụng tốt cho event có cùng nguồn timestamp, nhưng có các giới hạn:

1. Đồng hồ producer và consumer có thể lệch; cần NTP hoặc cơ chế đồng bộ giờ tương ứng.
2. Timestamp do client phát có thể khác thời điểm broker append record.
3. Với retry topic, phải bảo đảm header được bảo tồn khi Spring Kafka publish sang retry topic và khi replay thủ công.
4. Header thiếu hoặc sai định dạng cần được xử lý theo chính sách metric riêng; không tự ghi duration âm.
5. Nếu event bị replay sau nhiều ngày, end-to-end latency rất lớn. Nên phân biệt replay với traffic đang chạy bình thường.

Nếu cần đo **retry completion latency** từ lần xử lý đầu, hãy lưu thêm mốc `first-attempt-at` khi record lần đầu được giao. Với retry topic và restart, mốc này phải đi cùng record hoặc được lưu ở nơi có thể truy xuất. Chỉ dùng timestamp của Kafka record hiện tại không đủ, vì mỗi lần publish vào retry topic có thể tạo timestamp mới.

## 9. Quan sát bằng Micrometer và Spring Kafka

Spring Kafka có tích hợp Micrometer để ghi metrics và observation cho producer/consumer trong các phiên bản hỗ trợ. Có thể bật observation trên listener container khi dùng hệ sinh thái Micrometer Observation.

Ví dụ cấu hình trên factory:

```java
factory.getContainerProperties().setObservationEnabled(true);
```

Với Spring Boot, có thể có các thuộc tính `spring.kafka.listener.observation-enabled` và cấu hình observation tương ứng, tùy phiên bản Boot/Spring Kafka. Cần đối chiếu configuration metadata thực tế của dependency đang chạy.

Spring Kafka listener observation thường theo dõi thời gian gọi listener. Nó không tự chứng minh toàn bộ retry lifecycle từ first attempt đến success/DLT đã được đo. Nếu retry xảy ra sau khi listener ném exception, span hoặc timer của lần listener đó có thể đã kết thúc.

Điều nên làm:

- Tận dụng observation có sẵn để đo listener duration, status và exception.
- Ghi metric riêng cho retry delay và retry completion nếu SLO cần các chỉ số đó.
- Dùng trace context để liên kết producer, listener gốc, các retry topic và DLT.
- Kiểm tra sampling và khả năng truyền context qua headers, đặc biệt khi record được republish.
- Không giả định một trace luôn tồn tại xuyên restart hoặc retry topic nếu hệ thống chưa cấu hình propagation.

### 9.1. Trace giúp trả lời câu hỏi nào?

Với một event cụ thể, trace có thể cho thấy:

```text
Produce orders.created
  └─ Consume orders.created (attempt 1, failed)
       └─ Publish orders.created-retry
            └─ Consume orders.created-retry (attempt 2, failed)
                 └─ Consume retry stage tiếp theo
                      └─ Business operation success
```

Sơ đồ chỉ là mô hình quan sát mong muốn. Việc các spans được nối thành một trace hoặc các trace liên quan phụ thuộc tracing instrumentation, header propagation và hệ thống quan sát được cấu hình.

Metrics cho biết xu hướng số đông; traces và structured logs giúp điều tra một event hoặc một nhóm lỗi cụ thể.

## 10. Phân biệt retry latency với consumer lag

Consumer lag thường là chênh lệch giữa log end offset và committed offset của một consumer group. Nó phản ánh tiến độ đọc/commit theo partition, không trực tiếp đo thời gian retry của một event.

Hai tình huống khác nhau có thể xảy ra:

### 10.1. Retry blocking làm lag tăng

Record đầu tiên thất bại và container chờ/backoff, nên các record tiếp theo trong partition chưa được xử lý. Lag có thể tăng dù throughput producer không thay đổi.

Khi đó, cần xem:

- Retry failure rate và thời gian chờ.
- Tốc độ event đầu vào.
- Thời gian xử lý attempt.
- `max.poll.interval.ms` và tần suất rebalance.
- Partition nào đang bị dồn backlog.

### 10.2. Retry topic làm lag topic gốc thấp nhưng SLA vẫn kém

Record lỗi có thể được chuyển sang retry topic; consumer của topic gốc tiếp tục xử lý các record tiếp theo. Lag topic gốc có thể thấp, nhưng event lỗi vẫn đang nằm trong chuỗi retry.

Vì vậy, nếu dashboard chỉ đo lag của topic gốc, tình trạng retry có thể bị che khuất. Cần xem thêm lag của retry topic, số event đang chờ retry, scheduled delay và tổng event age.

Một consumer có lag bằng 0 cũng không bảo đảm mọi event đã hoàn tất nghiệp vụ: một số record có thể đã được chuyển DLT hoặc đang chờ xử lý trong topic khác.

## 11. Thiết kế dashboard theo latency và outcome

Có thể tổ chức dashboard thành bốn khu vực.

### 11.1. Tổng quan trải nghiệm nghiệp vụ

Hiển thị p50/p95/p99 của `event.end_to_end` đối với event thành công, success rate theo cửa sổ thời gian và tỷ lệ event vượt ngưỡng SLO. Nên biểu diễn số lượng mẫu đi kèm percentile để tránh hiểu sai khi traffic thấp.

### 11.2. Retry effectiveness

Hiển thị:

- Tỷ lệ event cần ít nhất một lần retry.
- Phân bố số attempt cho mỗi event.
- Tỷ lệ thành công sau retry.
- Tỷ lệ chuyển DLT.
- P95/p99 thời gian từ first attempt đến success.
- Thời gian recovery riêng cho record chuyển DLT.

Nếu retry rate tăng nhưng completion latency còn thấp, nhiều khả năng lỗi tạm thời được khắc phục nhanh. Nếu retry rate tương đương nhưng p99 latency tăng, có thể backlog hoặc scheduling drift đang lớn lên.

### 11.3. Chi phí chờ retry

Hiển thị configured backoff, actual delay và lateness. Với retry topic, chia theo retry stage; với blocking retry, chia theo listener hoặc nhóm exception.

Nếu actual delay tăng trong khi configured backoff không đổi, vấn đề có thể ở scheduling, consumer capacity hoặc broker/cluster, chứ không phải ở chính cấu hình BackOff.

### 11.4. Hạ tầng

Hiển thị consumer lag, pause duration, rebalance, listener processing duration, Kafka publish failures và broker/network latency.

Các metrics này giúp xác định nguyên nhân của retry latency tăng.

## 12. Tạo histogram và tính p95/p99

Một `Timer` của Micrometer thường cho phép ghi count, total time và có thể cấu hình histogram để truy vấn percentile theo tập mẫu. Nếu cần tính p95/p99 bằng Prometheus trên nhiều instance, cần bật histogram hoặc cơ chế percentile phù hợp.

Ví dụ:

```java
Timer.builder("app.kafka.retry.completion")
        .description("Duration from first attempt to terminal outcome")
        .tags(
            "topic", topicName,
            "outcome", "success"
        )
        .publishPercentileHistogram()
        .register(meterRegistry)
        .record(elapsed, TimeUnit.MILLISECONDS);
```

Ví dụ PromQL khi Timer được xuất thành histogram với đơn vị giây:

```promql
histogram_quantile(
  0.95,
  sum by (le, topic, outcome) (
    rate(app_kafka_retry_completion_seconds_bucket[5m])
  )
)
```

Query trên tính p95 ước lượng theo histogram trong cửa sổ năm phút. Nó chỉ hoạt động khi hệ thống thực sự xuất các bucket tương ứng và metric có label `topic`, `outcome`.

Có thể tính tốc độ event hoàn tất theo outcome:

```promql
sum by (topic, outcome) (
  rate(app_kafka_retry_completion_seconds_count[5m])
)
```

Khi không đủ mẫu trong một cửa sổ ngắn, percentile có thể dao động mạnh. Cần so sánh với count/rate, dùng cửa sổ thời gian phù hợp và kiểm tra bucket boundaries có đủ chi tiết quanh SLO hay không.

### 12.1. Vì sao không dùng average làm metric duy nhất?

Giả sử 99% record retry hoàn tất trong một giây nhưng 1% mất một phút. Average có thể vẫn thấp, trong khi nhóm khách hàng rơi vào đuôi dài trải nghiệm rất tệ.

P95 và p99 giúp nhìn thấy tail latency. Tuy nhiên, chúng cần đủ số mẫu và histogram đúng; cũng phải biết đang đo success hay DLT, retry blocking hay retry topic.

## 13. Đặt SLO và cảnh báo

SLO nên xuất phát từ yêu cầu nghiệp vụ, không từ số giây backoff đang cấu hình. Ví dụ dịch vụ cần xử lý phần lớn event thanh toán trong 30 giây kể từ khi event được tạo.

Có thể dùng các tín hiệu:

| Tín hiệu | Ví dụ điều kiện cảnh báo | Hành động điều tra |
|---|---|---|
| End-to-end p95 | Vượt SLO trong nhiều cửa sổ liên tiếp | Kiểm tra retry, lag và dependency |
| Retry success rate | Giảm đáng kể so với baseline | Xem exception mix và dependency |
| Retry scheduling drift | P95 tăng trong khi backoff cấu hình không đổi | Kiểm tra topic lag, pause, rebalance |
| Retry backlog | Số record chờ tăng bền vững | Kiểm tra capacity của retry consumer |
| DLT ingress | Tăng đột ngột | Phân tích lỗi không recover được |
| Recovery failure | Bất kỳ spike đáng kể | Kiểm tra publish DLT/serializer/ACL |
| Consumer lag | Tăng cùng retry rate | Xem blocking retry hoặc tải đầu vào |

Một ví dụ tính mục tiêu:

```text
SLO: 99% order events hoàn tất nghiệp vụ trong 30 giây
Theo dõi: event_end_to_end{outcome="success"}
Cảnh báo sớm: p95 > 20 giây và retry backlog đang tăng
Cảnh báo vi phạm: tỷ lệ event quá 30 giây vượt error budget
```

Các ngưỡng 20/30 giây ở đây chỉ là ví dụ. Khi triển khai, cần xác định event nào được tính vào mẫu, thời điểm bắt đầu, outcome nào được xem là đáp ứng SLO và cách tính record còn chờ chưa có terminal outcome.

Chỉ nhìn latency của các record **đã thành công** có thể tạo thiên lệch: record đang kẹt lâu trong retry không xuất hiện trong histogram completion. Vì vậy, cần bổ sung metric “oldest pending retry age” hoặc backlog age để phát hiện record đang chờ quá lâu.

## 14. DLT là một outcome riêng

Khi retry hết, một recoverer có thể publish record vào DLT. Cần ghi riêng:

- Số record vào DLT.
- Thời gian từ first attempt đến khi recovery hoàn tất.
- Số lần publish DLT thất bại.
- Tuổi record lớn nhất đang nằm trong DLT.
- Thời gian từ DLT đến khi được xử lý thủ công hoặc replay thành công.

Không nên ghi `outcome=success` cho record chỉ mới publish vào DLT. Nếu business process chưa hoàn tất, SLO nghiệp vụ vẫn chưa đạt.

Nếu có quy trình replay, event có thể bắt đầu một vòng xử lý mới. Hãy quyết định đo latency theo vòng replay riêng hay từ event gốc. Với nhu cầu audit, nên giữ cả hai: `original_event_age` và `replay_processing_latency`.

### 14.1. Recovery cũng có thể lỗi

Publish DLT có thể thất bại do serializer, quyền truy cập, topic/partition không tồn tại hoặc broker không sẵn sàng. Khi đó recoverer có thể ném exception và record vẫn chưa được recovery.

Metric completion cần được ghi tại điểm biết recovery đã thành công theo chính sách, không chỉ khi lời gọi recoverer bắt đầu. Nếu cần độ bền cao, kiểm tra hành vi xác nhận publish, transaction và offset commit trong cấu hình cụ thể.

## 15. Latency bị ảnh hưởng bởi những yếu tố nào?

### 15.1. Backoff quá ngắn

Retry quá nhanh khi dependency đang lỗi có thể tạo retry storm. Hệ thống nhận nhiều request thất bại, sử dụng thêm CPU và network, làm tăng tail latency cho cả record bình thường.

Giải pháp là chọn backoff có giới hạn, cân nhắc exponential backoff và jitter ở nơi phù hợp, đồng thời đo retry success rate.

### 15.2. Backoff quá dài

Backoff dài giảm áp lực dependency nhưng tăng thời gian hoàn tất record. Khi có SLO ngắn, lịch retry có thể tự nó tiêu hết error budget.

Hãy ước lượng tổng thời gian retry theo lịch:

```text
total_expected_time
  ≈ sum(processing_time_per_attempt)
  + sum(configured_backoff)
  + scheduling_overhead
  + queue_wait
```

Đây là cách ước lượng để lập kế hoạch; latency thực tế cần được đo bằng timestamps.

### 15.3. Consumer capacity không đủ

Retry topic có thể tích tụ backlog khi lượng event lỗi tăng đột ngột. Dù mỗi record có lịch retry một giây, nó có thể phải chờ lâu hơn vì consumer retry không đủ năng lực.

Quan sát lag, partition count, concurrency, CPU, GC, database connection pool và thời gian xử lý attempt.

### 15.4. Rebalance và restart

Rebalance có thể làm gián đoạn tiến độ, tạo thêm thời gian chờ và redelivery. Khi đo latency qua nhiều lần xử lý, phải bảo toàn mốc first attempt qua lần restart hoặc dùng một hệ thống theo dõi bền vững.

### 15.5. Exception có nguyên nhân cố định

Nếu lỗi xảy ra vì payload không hợp lệ, retry nhiều lần chỉ làm tăng latency rồi cuối cùng vẫn đi DLT. Cần phân loại exception, chuyển sớm sang recovery phù hợp và giám sát tỷ lệ non-retryable errors.

## 16. Logging để hỗ trợ điều tra

Một log retry hữu ích nên có thông tin bối cảnh đủ để ghép các attempt mà không ghi payload nhạy cảm.

Ví dụ dữ liệu log có cấu trúc:

```json
{
  "event": "kafka_retry_failure",
  "service": "billing-service",
  "topic": "orders.created",
  "partition": 2,
  "offset": 18420,
  "consumerGroup": "billing-service",
  "deliveryAttempt": 2,
  "exceptionType": "RemoteServiceTimeoutException",
  "retryMode": "blocking",
  "timestamp": "2026-11-15T10:00:01Z",
  "traceId": "example-trace-id"
}
```

Đây là cấu trúc log minh họa; các trường cần được ứng dụng hoặc instrumentation chủ động ghi. Với retry topic, topic/partition/offset có thể thay đổi theo từng lần publish, nên cần một event ID ổn định hoặc correlation ID để theo dõi xuyên các topic.

Không biến event ID, trace ID hoặc offset thành tag cho mọi metric; lưu trong log hoặc trace và chỉ dùng để điều tra từng trường hợp.

## 17. Kịch bản kiểm thử đo retry latency

Một integration test có Kafka thực có thể giúp xác nhận cách đo chứ không chỉ xác nhận listener được gọi lại.

### 17.1. Blocking retry

1. Dùng consumer group và topic test riêng.
2. Đặt `FixedBackOff(500L, 2L)`.
3. Cho listener thất bại hai lần đầu và thành công ở lần thứ ba.
4. Thu timestamp bắt đầu và kết thúc của từng attempt.
5. Xác nhận counter thất bại tăng hai lần, attempt timer có ba mẫu.
6. Kiểm tra khoảng cách giữa hai lần gọi có phản ánh backoff, trong sai số điều phối hợp lý.
7. Kiểm tra completion latency gồm cả xử lý và chờ.
8. Kiểm tra committed offset và không có DLT nếu nghiệp vụ thành công.

Không assert thời gian chính xác đến từng mili giây; môi trường CI có scheduling jitter. Dùng khoảng dung sai phù hợp với hệ điều hành, JVM và broker test.

### 17.2. Retry topic

1. Cấu hình topic chính, retry topic và DLT với backoff ngắn.
2. Gửi event có timestamp gốc do ứng dụng tạo.
3. Cho listener đầu thất bại và listener retry thành công.
4. Xác nhận timestamp gốc còn truy xuất được sau chuyển tiếp.
5. Đo thời điểm record được phép xử lý lại và thời điểm listener thực sự bắt đầu.
6. Xác nhận end-to-end latency gồm cả thời gian chờ trên retry topic.
7. Tạo tình huống retry consumer bị chậm để quan sát scheduling lateness tăng.
8. Kiểm tra DLT và outcome khi tất cả attempt thất bại.

Đối với retry topic, dùng timestamp hoặc metadata được phiên bản Spring Kafka hỗ trợ; tránh ràng buộc test vào cấu trúc header nội bộ không ổn định.

### 17.3. Kiểm thử khởi động lại và duplicate

Gây lỗi sau khi nghiệp vụ đã ghi database nhưng trước khi offset được commit. Khi record được giao lại, metric attempt có thể tăng và event được xử lý trùng. Handler phải idempotent, còn dashboard nên có chỉ số duplicate/replay để giải thích vì sao số attempts lớn hơn số event duy nhất.

## 18. Những lỗi quan sát thường gặp

**Chỉ đo `@KafkaListener` duration.** Metric này đo mỗi lần gọi listener nhưng có thể bỏ qua backoff và thời gian nằm trên retry topic. Bổ sung completion latency và actual retry delay khi cần.

**Lấy configured backoff làm actual latency.** Lịch retry không phản ánh scheduling drift, poll delay và backlog. Cần đo thời gian bắt đầu attempt kế tiếp.

**Chỉ nhìn lag của topic chính.** Non-blocking retry đưa record sang topic riêng. Bổ sung retry topic lag và oldest pending event age.

**Tính DLT là success.** DLT là outcome của recovery, không chứng minh nghiệp vụ hoàn tất. Tách metric outcome.

**Dùng timestamp của retry topic như timestamp event gốc.** Mỗi lần republish có thể thay đổi record timestamp, làm end-to-end latency bị đánh giá thấp. Dùng một timestamp nguồn có thể bảo toàn.

**Dùng System.currentTimeMillis cho duration trong cùng JVM mà không cân nhắc clock change.** Với duration nội bộ, ưu tiên `System.nanoTime()`. Dùng wall-clock khi so sánh mốc qua các hệ thống và kiểm soát clock skew.

**Đưa record key hoặc exception message làm metric tag.** Cardinality tăng cao, dẫn tới chi phí và ảnh hưởng khả năng truy vấn. Dùng labels ít giá trị; để ID chi tiết trong logs/traces.

**Chỉ đo các record đã hoàn tất.** Record kẹt lâu chưa được tính vào completion histogram. Bổ sung pending age, backlog và time-since-first-attempt cho record đang chờ.

**Không phân biệt retry attempt với record duy nhất.** Một event thất bại ba lần có thể tạo ba sample lỗi. Khi tính retry rate, phải xác định mẫu số là số deliveries hay số unique events.

**Không quan sát commit và recovery failure.** Nghiệp vụ có thể hoàn tất trước commit; DLT publish có thể thất bại. Kết hợp metrics outcome với commit failure, redelivery và idempotency.

## 19. Hướng triển khai theo mức ưu tiên

Với một service Spring Kafka đang vận hành, có thể bổ sung observability theo thứ tự:

1. Định nghĩa SLO nghiệp vụ và mốc timestamp bắt đầu/kết thúc.
2. Bật listener metrics hoặc observation phù hợp với phiên bản Spring Kafka.
3. Đếm retry failures, retries exhausted và recovery outcomes bằng `RetryListener` hoặc hooks tương đương.
4. Bảo toàn event timestamp hoặc event ID qua retry topic/DLT.
5. Ghi completion latency và end-to-end latency, tách outcome.
6. Bổ sung actual retry delay và scheduling drift khi cần chẩn đoán backoff.
7. Ghép với consumer lag, retry topic lag, rebalance và resource metrics.
8. Tạo dashboard p50/p95/p99, retry rate, DLT và pending age.
9. Đặt alert theo SLO, quan sát trend và kiểm thử bằng lỗi có chủ đích.
10. Kiểm tra lại instrumentation khi nâng cấp Spring Kafka hoặc thay đổi mô hình retry.

### 19.1. Bộ câu hỏi khi có cảnh báo latency

Khi p95 hoặc p99 tăng, cần kiểm tra lần lượt: retry failures có tăng không? Configured backoff có thay đổi không? Actual delay có lệch lịch không? Retry topic có backlog không? Một loại exception mới có xuất hiện không? Consumer có rebalance hoặc mất partition assignment không? Dependency có timeout không? Có record bị kẹt chưa hoàn tất nên chưa xuất hiện trong completion histogram không?

Các câu hỏi này giúp phân biệt sự cố ở chính sách retry, năng lực consumer, Kafka hoặc dịch vụ nghiệp vụ.

## 20. Tài liệu tham chiếu và phạm vi phiên bản

Khi triển khai trên một phiên bản cụ thể, đối chiếu các phần tài liệu chính thức sau:

- Spring for Apache Kafka Reference: error handling, `DefaultErrorHandler`, `RetryListener`, `BackOff`, `ContainerPausingBackOffHandler`.
- Spring for Apache Kafka Reference: non-blocking retries, `@RetryableTopic`, retry topic headers, backoff timing và DLT.
- Spring Kafka Javadoc: `DefaultErrorHandler`, `RetryListener`, `ConcurrentKafkaListenerContainerFactory`, `ContainerProperties`.
- Spring Kafka Reference: Micrometer timers, Micrometer Observation và listener instrumentation.
- Micrometer Documentation: `Timer`, percentile histograms, tags/cardinality và Prometheus naming.
- Apache Kafka Documentation: consumer lag, offset commits, client metrics và record timestamps.

Các API quan sát, thuộc tính Spring Boot và chi tiết retry topic có thể thay đổi giữa các bản Spring Kafka. Khi nâng cấp dependency, cần kiểm tra các metric được xuất thực tế, tên label, số attempts, header propagation và cách lưu offset. Đặc biệt, listener latency và end-to-end retry latency là hai phép đo khác nhau và nên được thể hiện thành hai đồ thị riêng.

Theo dõi retry latency hiệu quả nghĩa là biết **mỗi lần xử lý tốn bao lâu**, **record đã chờ retry bao lâu**, **vì sao lịch retry bị trễ**, và **sau cùng event hoàn tất hay đi DLT**. Khi những mốc này được ghi nhận cùng với lag và outcome, nhóm vận hành có thể thấy chính xác retry đang bảo vệ hệ thống hay đang kéo dài thời gian xử lý vượt quá SLO.
