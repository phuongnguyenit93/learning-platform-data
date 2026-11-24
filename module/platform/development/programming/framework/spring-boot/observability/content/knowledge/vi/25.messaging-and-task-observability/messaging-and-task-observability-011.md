# Đo thời gian chờ và thời gian xử lý

Một đơn hàng được publish thành message để Inventory Worker xử lý bất đồng bộ. Dashboard cho thấy thời gian xử lý trung bình chỉ 80 ms, nhưng người dùng vẫn phải chờ vài giây mới thấy kết quả. Nguyên nhân có thể là message nằm trong queue lâu trước khi consumer nhận nó. Nếu chỉ đo thời gian xử lý bên trong handler, hệ thống bỏ sót độ trễ do backlog, thiếu consumer capacity hoặc lịch retry.

Bài **Đo thời gian chờ và thời gian xử lý** thuộc chương **Messaging và task observability** của module **SPRING_BOOT_OBSERVABILITY**. Module học cách thiết lập observability cho Spring Boot bằng Micrometer Observation, metrics, logs và distributed tracing; hiểu context propagation, tag/cardinality, exporter, sampling và liên kết các tín hiệu để điều tra lỗi, độ trễ và hành vi ứng dụng trong môi trường thực.

> **Nguyên tắc:** Đo riêng thời gian chờ trước khi xử lý (queue wait), thời gian thực thi (processing duration) và tuổi end-to-end (publish đến hoàn tất). Ba số đo trả lời ba câu hỏi khác nhau. Đừng suy ra queue đang khỏe chỉ vì handler chạy nhanh; cũng đừng cộng retry attempts như thể chúng là các message độc lập nếu muốn đo trải nghiệm của một logical job.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt queue wait time, processing duration và end-to-end message age.
2. Xác định timestamp phù hợp ở publish, enqueue, receive/start, retry và completion.
3. Hiểu tác động của broker semantics, consumer concurrency, prefetch và acknowledgment.
4. Đo thời gian chờ và xử lý bằng Micrometer Timer/Observation.
5. Thiết kế metrics cho backlog, consumer lag, retries, failures và throughput.
6. Xử lý clock skew, timestamp thiếu và message được replay.
7. Phân biệt attempt duration với logical task duration.
8. Liên kết message context với distributed traces qua propagation.
9. Chọn histogram buckets và SLO phù hợp cho queue wait/processing.
10. Kiểm thử và điều tra queue backlog hoặc worker xử lý chậm.

## 2. Ba loại thời gian cần đo

Một message thường đi qua các mốc:
- **Published:** producer bắt đầu hoặc hoàn tất gửi message.
- **Enqueued/accepted:** broker xác nhận message được nhận vào hệ thống.
- **Received/started:** consumer nhận message và bắt đầu xử lý.
- **Completed:** handler kết thúc thành công hoặc thất bại.
- **Acknowledged:** consumer xác nhận với broker rằng message đã được xử lý theo delivery semantics.

~~~mermaid
flowchart LR
    A["Publish"] --> B["Broker accepts"]
    B --> C["Queue wait"]
    C --> D["Consumer starts"]
    D --> E["Processing"]
    E --> F["Complete"]
    F --> G["Ack"]
~~~

Từ các mốc này, định nghĩa:

| Đại lượng | Công thức khái niệm | Ý nghĩa |
|---|---|---|
| Publish-to-accept | accepted_at - publish_started_at | Thời gian gửi/được broker chấp nhận |
| Queue wait | processing_started_at - enqueued_at | Thời gian message chờ trước khi worker bắt đầu |
| Processing duration | processing_finished_at - processing_started_at | Thời gian worker xử lý một attempt |
| Ack latency | acknowledged_at - processing_finished_at | Thời gian từ hoàn tất handler tới broker ack |
| End-to-end age | completed_at - published_at | Tuổi logical message từ publish tới kết quả |
| Consumer lag | Vị trí/offset chưa xử lý hoặc chênh timestamp theo broker | Mức chậm của consumer so với luồng dữ liệu |

Không phải broker nào cũng expose cả mốc enqueue, receive và ack. Cần xác định timestamp có sẵn từ broker/client hay phải ghi trong message metadata. Không trộn các định nghĩa khác nhau vào cùng một metric name.

## 3. Queue wait time

Queue wait time là khoảng từ lúc broker nhận message đến khi consumer bắt đầu xử lý. Nó phản ánh backlog và khả năng tiêu thụ.

Ví dụ:
- Producer publish lúc 10:00:00.000.
- Broker accept lúc 10:00:00.010.
- Consumer bắt đầu lúc 10:00:02.010.
- Handler hoàn tất lúc 10:00:02.090.

Queue wait khoảng 2 giây; processing duration khoảng 80 ms. Handler nhanh nhưng hệ thống vẫn chậm vì message phải chờ.

Queue wait tăng có thể do:
- Message arrival rate lớn hơn processing capacity.
- Consumer instances/threads không đủ.
- Consumer bị pause, rebalance hoặc crash.
- Prefetch/visibility timeout/partition assignment làm message chưa tới worker.
- Một nhóm message poison hoặc retry liên tục chiếm capacity.
- Downstream dependency chậm khiến consumer không nhận message mới.

Queue wait cần được xem cùng queue depth, oldest message age, consumer count, throughput và retry rate.

## 4. Processing duration

Processing duration đo thời gian một attempt bắt đầu chạy handler đến khi handler hoàn tất hoặc phát sinh terminal error/cancel. Nó trả lời worker mất bao lâu để xử lý message sau khi nhận.

Ví dụ:

~~~text
message.type = inventory.reservation
consumer = inventory-worker
processing.duration = 80 ms
outcome = success
~~~

Processing duration tăng có thể do:
- Handler code hoặc serialization tốn CPU.
- Database query/transaction chậm.
- HTTP dependency chậm.
- Lock contention hoặc thread starvation.
- Payload lớn.
- Garbage collection hoặc resource saturation.

Đo processing duration quanh đúng phần xử lý cần quan sát. Nếu timer bao gồm chờ executor queue, nó không còn là pure handler duration; hãy đặt tên/định nghĩa metric phù hợp.

## 5. End-to-end message age

End-to-end age đo từ thời điểm publish của logical message tới lúc business operation hoàn tất. Nó bao gồm publish, queue wait, processing, retries/backoff và các bước trung gian nếu định nghĩa xuyên nhiều services.

~~~mermaid
flowchart TD
    A["Published"] --> B["Broker / queue wait"]
    B --> C["Attempt 1"]
    C --> D{"Success?"}
    D -->|No| E["Retry delay / redelivery"]
    E --> F["Attempt 2"]
    F --> G["Completed"]
    D -->|Yes| G
~~~

Một message có thể có processing duration 80 ms nhưng end-to-end age 5 phút vì nó chờ queue hoặc retry nhiều lần. Đo end-to-end age hữu ích cho user-facing workflows, SLA xử lý bất đồng bộ và deadline của job.

Cần xác định completion có nghĩa gì: handler return, database commit, publish event tiếp theo, hay business workflow hoàn tất. Nếu message tạo workflow nhiều bước, một consumer span không đại diện toàn bộ thời gian business process.

## 6. Định nghĩa timestamp chính xác

Timestamp cần được gắn với sự kiện cụ thể:

| Timestamp | Ai ghi? | Lưu ý |
|---|---|---|
| publishedAt | Producer | Thời điểm logical event được tạo hoặc gửi |
| acceptedAt/enqueuedAt | Broker hoặc producer nhận broker confirmation | Broker thường đáng tin hơn cho queue residence |
| receivedAt | Consumer/client | Có thể khác thời điểm handler bắt đầu |
| processingStartedAt | Consumer instrumentation | Mốc bắt đầu timer handler |
| processingFinishedAt | Consumer instrumentation | Thành công/thất bại/cancel |
| acknowledgedAt | Client/broker protocol | Ack có thể xảy ra sau handler completion |

Không dùng một field tên timestamp cho nhiều ý nghĩa. Nếu broker cung cấp enqueue timestamp, ưu tiên nó để tính queue residence. Nếu chỉ có producer timestamp, phép trừ giữa clocks của producer và consumer có thể sai do clock skew.

### 6.1 Clock skew

Giả sử producer clock nhanh hơn consumer 700 ms. Tính consumerStart - publishedAt có thể nhỏ hơn thực tế 700 ms hoặc thậm chí âm. Queue wait dựa trên broker enqueue timestamp có thể giảm sai số nếu timestamp do broker quản lý, nhưng consumer và broker vẫn cần đồng bộ thời gian.

Khuyến nghị:
- Đồng bộ host clocks bằng NTP/chrony hoặc dịch vụ time sync của platform.
- Ưu tiên monotonic clock cho duration đo trong cùng process.
- Dùng wall-clock timestamps chỉ khi cần đo qua process boundary.
- Ghi nhận và theo dõi negative/implausible durations thay vì clamp âm thành 0 mà không báo.
- Đặt tên metric theo đúng nguồn timestamp để không so sánh nhầm.

### 6.2 Message được replay hoặc migrate

Khi replay message từ dead-letter queue hoặc backfill, publishedAt có thể rất cũ. End-to-end age sẽ phản ánh tuổi từ event gốc, không phải thời gian chờ của lần replay. Cần đo thêm enqueue/receive timestamp của lần delivery hiện tại và phân biệt replay bằng bounded outcome/source dimension nếu cần.

Không ghi message ID duy nhất thành metric tag. Dùng message ID trong trace/log có kiểm soát để điều tra một record cụ thể.

## 7. Acknowledgment, retries và redelivery

Message processing có thể theo at-most-once, at-least-once hoặc broker-specific semantics. Với at-least-once, handler có thể nhận lại message nếu ack không thành công, consumer crash hoặc visibility timeout hết hạn.

Phân biệt:
- **Attempt:** một lần handler thực thi.
- **Delivery:** một lần broker giao message cho consumer; có thể delivery nhưng handler chưa bắt đầu.
- **Logical message/job:** công việc nghiệp vụ ban đầu, có thể gồm nhiều deliveries/attempts.
- **Retry delay:** khoảng chờ trước lần thử tiếp theo.
- **End-to-end age:** tổng tuổi logical job đến terminal completion.

Một attempt thất bại 100 ms, retry delay 30 giây, attempt tiếp theo thành công 100 ms: processing time tổng của hai attempts là 200 ms, nhưng end-to-end age tối thiểu hơn 30 giây cộng queue waits. Hai metrics không được thay thế cho nhau.

### 7.1 Ack latency

Nếu handler return nhưng ack bị chậm hoặc thất bại, broker có thể redeliver message. Đo ack latency giúp phân biệt handler chậm với ack/network issue. Tùy client API, ack có thể được gửi tự động sau callback hoặc do ứng dụng chủ động. Đừng đo ack duration nếu framework không expose mốc chính xác; hãy dùng broker/client metrics sẵn có.

### 7.2 Retry và poison messages

Retry liên tục có thể khiến cùng một logical message chiếm worker nhiều lần. Metrics hữu ích:
- Attempts per logical message (phân phối tổng hợp, không tag ID).
- Retry count/rate theo message type và outcome.
- Dead-letter count.
- Oldest message age.
- Processing duration theo attempt.
- End-to-end age đến success/dead-letter.

Giới hạn retry, dùng backoff/jitter, phân loại lỗi transient/permanent và có dead-letter policy. Không retry lỗi validation/schema vĩnh viễn vô hạn.

## 8. Micrometer metrics cho messaging và task

Một bộ metrics thường có:

| Metric | Type | Định nghĩa |
|---|---|---|
| messaging.consumer.queue.wait | Timer/Histogram | Enqueued đến processing start |
| messaging.consumer.processing | Timer/Histogram | Processing start đến terminal handler outcome |
| messaging.message.age | Timer/Histogram | Published đến business completion |
| messaging.consumer.completed | Counter | Số attempts/logical jobs hoàn tất theo định nghĩa |
| messaging.consumer.errors | Counter | Số attempts thất bại |
| messaging.consumer.retries | Counter | Số retry/redelivery được quan sát |
| messaging.consumer.dead_lettered | Counter | Số message chuyển DLQ |
| messaging.consumer.in_flight | Gauge | Message đang được xử lý |
| messaging.queue.depth | Gauge | Backlog hiện tại nếu broker expose |
| messaging.queue.oldest_age | Gauge | Tuổi message cũ nhất nếu broker expose |

Tên metric cụ thể phụ thuộc Micrometer binder, Spring Integration, Spring Kafka, Spring AMQP hoặc custom instrumentation. Trước khi tạo custom metric, kiểm tra integration hiện có để tránh duplicate measurements.

### 8.1 Timer cho queue wait và processing

Ví dụ custom instrumentation cho task:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import java.time.Duration;
import java.time.Instant;

class TaskMetrics {

    private final MeterRegistry registry;

    TaskMetrics(MeterRegistry registry) {
        this.registry = registry;
    }

    void recordQueueWait(Duration wait, String taskType) {
        Timer.builder("messaging.consumer.queue.wait")
                .tag("task.type", taskType)
                .publishPercentileHistogram()
                .register(registry)
                .record(wait);
    }

    void recordProcessing(Duration duration, String taskType) {
        Timer.builder("messaging.consumer.processing")
                .tag("task.type", taskType)
                .publishPercentileHistogram()
                .register(registry)
                .record(duration);
    }
}
~~~

Đây là ví dụ ghi duration đã tính sẵn. Trong listener thực tế, lấy timestamp đúng mốc và bảo đảm mỗi attempt được record đúng một lần trong success/error/cancel paths.

### 8.2 Đo processing bằng Timer.Sample

Timer.Sample đo duration bằng monotonic clock của Micrometer:

~~~java
Timer.Sample sample = Timer.start(registry);
try {
    process(message);
    sample.stop(successTimer);
} catch (RuntimeException ex) {
    sample.stop(errorTimer);
    throw ex;
}
~~~

Timer.Sample phù hợp cho duration trong cùng process. Nó không đo queue wait xuyên process; queue wait cần timestamp enqueue/receive hoặc broker-provided residence metrics.

## 9. Observation cho consumer processing

Micrometer Observation có thể bao bọc consumer operation để tạo metrics và tracing span qua handlers.

~~~java
Observation.createNotStarted("messaging.process", observationRegistry)
        .lowCardinalityKeyValue("messaging.system", "kafka")
        .lowCardinalityKeyValue("messaging.operation", "process")
        .lowCardinalityKeyValue("messaging.destination.name", "orders")
        .observe(() -> handle(message));
~~~

Ví dụ minh họa custom Observation. Instrumentation tích hợp của Spring Kafka/AMQP hoặc framework khác có thể đã tạo Observation; không bọc thêm một observation trùng cùng operation nếu không có mục đích khác biệt.

Observation context nên chứa:
- Messaging system (kafka, rabbitmq, jms...).
- Destination/queue/topic đã chuẩn hóa.
- Operation (receive/process/settle tùy semantics).
- Outcome (success/error/rejected).
- Error type hữu hạn nếu cần.

Không thêm message key, payload, customer ID hoặc message ID vào low-cardinality tags.

### 9.1 Consumer Observation và span lifecycle

Span consumer có thể bắt đầu khi message được nhận hoặc khi handler bắt đầu, tùy instrumentation. Nếu mục tiêu là queue wait, cần biết mốc broker enqueue; consumer span duration thường chỉ thể hiện phần từ instrumentation start đến stop và không tự động đại diện toàn bộ thời gian nằm trong queue.

Distributed tracing messaging conventions phân biệt producer/consumer spans và links; một message được consume theo batch hoặc từ nhiều producer contexts có thể cần span links thay vì một parent duy nhất. Tuân theo semantics của integration đang dùng.

## 10. Kafka, RabbitMQ và các broker khác

Không phải broker nào cũng định nghĩa queue wait giống nhau.

| Hệ thống | Tín hiệu có thể dùng | Lưu ý |
|---|---|---|
| Kafka | Record timestamp, consumer lag/offset, poll/processing time | Lag thường là offset distance; không trực tiếp bằng thời gian |
| RabbitMQ | Ready/unacked messages, queue stats, delivery/ack | Queue enqueue timestamp cần có nguồn đáng tin |
| JMS | Provider/client delivery metadata, listener duration | Timestamp availability phụ thuộc provider |
| SQS-like queue | Sent/ApproximateFirstReceive/visibility/redrive metrics | Broker age metrics thường approximate |
| Spring TaskExecutor | Task submission/start/finish | Queue wait là executor queue time, không phải broker wait |

### 10.1 Kafka consumer lag không phải queue wait time

Kafka lag thường được tính từ consumer group committed/current offset so với log end offset. Nó đo số records chưa được consume, không phải thời gian một record đã chờ. Lag có thể tăng khi throughput thấp, nhưng để biết tuổi record cần timestamp và cách diễn giải timestamp semantics.

Ví dụ:
- Lag 10.000 records ở topic throughput 20.000/s có thể chỉ là khoảng nửa giây dữ liệu.
- Lag 100 records ở topic throughput 1/s có thể tương đương gần 100 giây.

Do đó theo dõi cả offset lag, records/sec và record age/queue wait nếu cần.

### 10.2 Prefetch và concurrency

RabbitMQ prefetch hoặc Kafka poll batch có thể khiến message đã được broker giao nhưng chưa bắt đầu handler. Nếu queue wait được đo từ enqueue đến handler start, khoảng chờ này bao gồm broker backlog và client-side buffering. Đây thường là góc nhìn hữu ích cho latency thực tế nhưng cần ghi rõ metric definition.

## 11. Cardinality và histogram buckets

Metric tags cần hữu hạn:
- messaging.system.
- destination.name đã allowlist.
- consumer.group đã chuẩn hóa.
- operation.
- task.type với tập giá trị nhỏ.
- outcome/error.type.

Tránh message ID, partition/offset nếu số lượng lớn, message key, user ID, payload fields và exception message. Partition có thể là dimension bounded nếu số partition nhỏ và nhu cầu vận hành rõ ràng; không mặc định mọi broker metadata đều an toàn làm tag.

Histogram buckets nên phản ánh mục tiêu latency:
- Queue wait: có thể cần bucket từ vài ms tới hàng chục giây/phút.
- Processing: thường tập trung ms tới vài giây tùy workload.
- End-to-end age: có thể cần bucket dài hơn và phân phối riêng.

Không dùng cùng bucket cho cả ba metrics nếu scale khác nhau. Client-side percentiles khó tổng hợp giữa instances; histogram buckets phù hợp hơn cho aggregation/SLO ở backend.

## 12. SLO và alerting

Ví dụ SLO:
- 99% message bắt đầu xử lý trong vòng 2 giây sau broker enqueue.
- 99% task hoàn tất handler trong 500 ms.
- 95% logical jobs hoàn tất trong 30 giây từ publish.
- Không để oldest message age vượt 5 phút trong queue critical.

Đây là ví dụ; chọn mục tiêu theo business contract và traffic patterns.

Alert nên kết hợp:
- Queue wait p95/p99 vượt budget.
- Oldest message age tăng liên tục.
- Queue depth/consumer lag tăng và throughput không theo kịp.
- Processing duration tăng.
- Error/retry/dead-letter rate tăng.
- In-flight gần concurrency limit.
- End-to-end age vi phạm SLA.

Không alert chỉ vì queue depth cao nếu queue đang được drain nhanh và age thấp. Queue depth là gauge tức thời; age và throughput giúp hiểu backlog có ảnh hưởng người dùng hay không.

## 13. Kiểm thử đo thời gian chờ và xử lý

Tạo test có các mốc thời gian xác định:
1. Publish message.
2. Giữ message trong queue hoặc trì hoãn listener start.
3. Bắt đầu handler.
4. Cho handler chạy trong một khoảng delay.
5. Hoàn tất/throw/cancel và ack.
6. Assert queue wait và processing duration được ghi đúng theo định nghĩa.

### 13.1 Test phân biệt hai duration

Ví dụ giả lập:
- Enqueued tại t=0.
- Handler bắt đầu tại t=2s.
- Handler hoàn tất tại t=2.1s.

Kỳ vọng:
- Queue wait gần 2s.
- Processing duration gần 100ms.
- End-to-end age gần 2.1s nếu publish và enqueue gần nhau.

Không dùng sleep sát ngưỡng trong test chính nếu có thể dùng latch/barrier và tolerance phù hợp. Test duration nên chấp nhận scheduler jitter.

### 13.2 Test retry và redelivery

Test thêm:
- Attempt đầu thất bại.
- Retry delay 1s.
- Attempt tiếp theo thành công.
- Xác nhận attempt processing timers có hai observations.
- Logical end-to-end age bao gồm retry delay.
- Retry counter tăng đúng một lần theo semantics đã chọn.
- Không gắn message ID làm metric tag.

### 13.3 Test clock skew và missing timestamp

Dùng timestamps giả lập để kiểm tra:
- Producer timestamp muộn/sớm hơn consumer.
- Timestamp thiếu.
- Enqueue timestamp broker không có.
- Replay message có publishedAt cũ.
- Duration âm hoặc vượt giới hạn hợp lý.

Không âm thầm biến mọi duration âm thành 0; ghi nhận invalid timestamp hoặc bỏ sample theo policy có metric riêng.

## 14. Troubleshooting

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Processing duration thấp nhưng user workflow chậm | Queue wait/backlog lớn | Đo queue wait, oldest age và consumer lag |
| Queue wait thấp nhưng processing chậm | Handler/dependency/CPU/DB chậm | Xem consumer span và dependency spans |
| Kafka lag cao nhưng record age thấp | Throughput topic rất cao | Xem offset lag cùng records/sec và timestamp age |
| Queue depth cao nhưng age thấp | Consumer drain nhanh hoặc burst mới đến | Theo dõi age/throughput, không alert depth đơn lẻ |
| Duration âm | Clock skew hoặc timestamp semantics sai | Đồng bộ clock, dùng broker timestamp và validate |
| Replay có age rất lớn | Dùng publish timestamp gốc | Đo thêm enqueue age của lần replay |
| Retry count cao nhưng errors thấp | Retry cuối cùng thành công | Theo dõi attempts và logical outcomes riêng |
| Ack timeout/redelivery tăng | Ack không hoàn tất hoặc consumer crash | Kiểm tra ack mode, visibility timeout và handler lifecycle |
| Consumer span không bao gồm queue wait | Span bắt đầu khi handler nhận message | Dùng broker age/queue wait metric riêng |
| Metric series tăng mạnh | Message ID/key/partition động thành tags | Bỏ ID động, chỉ dùng dimensions bounded |
| Timer ghi hai lần | Success và finally/catch cùng stop timer | Đảm bảo một terminal path record đúng một lần |
| Batch listener duration bất thường | Một span/timer đại diện nhiều messages | Định nghĩa metric theo batch và per-message rõ ràng |

## 15. Playbook: backlog tăng nhưng worker vẫn nhanh

**Tình huống:** Processing p95 vẫn 80 ms, nhưng message completion SLA bị vi phạm.

1. Kiểm tra queue depth/consumer lag và oldest message age.
2. Đo queue wait từ broker enqueue tới handler start.
3. So sánh arrival rate với completion throughput.
4. Kiểm tra consumer count, concurrency, partition assignment và prefetch.
5. Xem retry/dead-letter traffic có chiếm capacity không.
6. Kiểm tra worker pause/rebalance, thread pool và connection pool downstream.
7. Nếu queue wait cao nhưng processing ổn định, scale consumer hoặc điều chỉnh partition/concurrency theo capacity của dependencies.
8. Nếu retry/backoff chiếm thời gian, phân loại transient/permanent failures và giới hạn retry.
9. Theo dõi end-to-end age sau thay đổi để xác nhận SLA hồi phục.

Không tăng consumer concurrency vô hạn: nhiều worker hơn có thể làm database/API downstream quá tải, khiến processing duration tăng và tạo backlog mới.

## 16. Bài tập tự kiểm tra

**Bài 1 — Tách duration.** Message được enqueue lúc 10:00:00, handler bắt đầu 10:00:03 và hoàn tất 10:00:03.2. Queue wait, processing duration và end-to-end age (nếu publish cùng lúc enqueue) là bao nhiêu?

**Bài 2 — Kafka lag.** Vì sao consumer lag 5.000 records không thể tự chuyển thành queue wait 5 giây nếu chưa biết throughput/timestamp?

**Bài 3 — Retry.** Một logical message có hai attempts, mỗi attempt 100 ms và retry delay 20 giây. Processing duration tổng và end-to-end age khác nhau thế nào?

**Bài 4 — Clock skew.** Producer clock nhanh 1 giây so với consumer. Điều gì xảy ra khi tính consumerStart - publishedAt? Nên dùng timestamp nào và đồng bộ ra sao?

**Bài 5 — Ack.** Handler kết thúc nhanh nhưng message redelivery liên tục. Những mốc/metrics nào cần kiểm tra ngoài processing duration?

**Bài 6 — Histogram.** Vì sao queue wait và processing duration cần histogram buckets khác nhau?

**Bài 7 — Cardinality.** Vì sao message ID và offset không nên là metric tags mặc định? Dùng chúng ở đâu để điều tra một message cụ thể?

**Bài 8 — SLO.** Worker xử lý 50 ms nhưng queue wait p99 là 45 giây. SLO nào bị vi phạm và nên xem metric nào để xác định capacity?

### Gợi ý trả lời

1. Queue wait 3 giây; processing 200 ms; end-to-end khoảng 3.2 giây.
2. Lag là số offset records; thời gian phụ thuộc arrival/consume rate và record timestamps.
3. Processing attempts cộng 200 ms; end-to-end tối thiểu khoảng 20.2 giây cộng queue waits và các khoảng khác.
4. Duration có thể âm hoặc nhỏ hơn thực tế 1 giây. Dùng broker enqueue timestamp khi có, đồng bộ clocks và validate timestamp.
5. Ack latency, ack failures, visibility timeout, consumer crash/rebalance và delivery count.
6. Queue wait có thể từ ms đến phút; processing thường ms đến giây. Bucket riêng giúp percentile/SLO có ý nghĩa.
7. Mỗi message/offset tạo series riêng. Dùng trace/log có kiểm soát để tìm message cụ thể.
8. SLO queue-start latency/end-to-end bị vi phạm; xem backlog, arrival/consume throughput, concurrency, partition/prefetch và oldest age.

## 17. Tài liệu tham khảo chính thức

- [Micrometer Observation](https://docs.micrometer.io/micrometer/reference/observation/introduction.html): Observation lifecycle, handlers, conventions và context.
- [Micrometer Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html): Timer, histogram, percentiles và duration recording.
- [Spring for Apache Kafka — Micrometer Observation](https://docs.spring.io/spring-kafka/reference/kafka/micrometer.html): producer/consumer observations và tracing.
- [Spring AMQP — Micrometer Observation](https://docs.spring.io/spring-amqp/reference/amqp/receiving-messages/async-annotation-driven/enable-micrometer.html): listener observation và metrics.
- [Apache Kafka — Monitoring](https://kafka.apache.org/documentation/#monitoring): consumer lag, throughput và broker metrics.
- [RabbitMQ — Monitoring](https://www.rabbitmq.com/docs/monitoring): queue depth, ready/unacked messages và consumer metrics.
- [OpenTelemetry Semantic Conventions — Messaging](https://opentelemetry.io/docs/specs/semconv/messaging/): producer/consumer spans, message attributes và propagation.
- [OpenTelemetry — Context Propagation](https://opentelemetry.io/docs/concepts/context-propagation/): trace context qua process boundaries.
- [Spring Boot — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): Micrometer registry, timers và custom metrics.

**Ghi nhớ:** Queue wait đo thời gian trước khi worker bắt đầu; processing duration đo thời gian một attempt chạy; end-to-end age đo tuổi logical job từ publish tới kết quả. Theo dõi cả ba cùng backlog, throughput, retries, ack và consumer capacity. Dùng broker timestamp khi có, đồng bộ clocks, giữ metric tags bounded và dùng traces/logs để điều tra message cụ thể. Worker chạy nhanh không có nghĩa hệ thống bất đồng bộ phản hồi nhanh nếu queue đang tích tụ.

