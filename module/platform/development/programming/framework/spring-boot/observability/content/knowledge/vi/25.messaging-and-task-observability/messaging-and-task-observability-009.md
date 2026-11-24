# Queue depth và lag trong messaging và task observability

> **Chương:** Messaging và task observability  
> **Bài:** Queue depth và lag  
> **Module:** SPRING_BOOT_OBSERVABILITY — Thiết lập observability cho Spring Boot bằng Micrometer Observation, metrics, logs và distributed tracing. Học propagation ngữ cảnh, tag/cardinality, exporter, sampling và liên kết tín hiệu để điều tra lỗi, độ trễ và hành vi ứng dụng trên môi trường thực.

## 1. Vì sao cần theo dõi queue depth và lag?

Trong hệ thống xử lý bất đồng bộ, producer gửi message hoặc task vào một queue để consumer xử lý sau. Queue giúp tách tốc độ nhận việc khỏi tốc độ xử lý, nhưng nếu producer liên tục nhanh hơn consumer, backlog sẽ tăng. Request HTTP ban đầu vẫn có thể trả 202 Accepted trong khi công việc thực tế bị trì hoãn nhiều phút.

Hai khái niệm cần theo dõi:

- **Queue depth**: số lượng message/task hiện đang chờ xử lý trong queue hoặc subscription theo định nghĩa của broker.
- **Consumer lag**: khoảng cách giữa vị trí message mới nhất mà consumer cần xử lý và vị trí consumer đã hoàn tất/đọc tới. Với Kafka, lag thường được tính theo số offsets giữa log end offset và consumer group committed offset; với queue khác, semantics có thể là số message chưa acknowledge hoặc chưa được giao.

Queue depth và consumer lag liên quan nhưng không thể dùng thay thế cho nhau. Queue depth thường mô tả backlog của queue; Kafka consumer lag mô tả tiến độ của một consumer group so với log. Cần biết metric cụ thể đến từ broker, client hay exporter trước khi diễn giải.

~~~mermaid
flowchart LR
  P["Producer"] --> Q["Broker / queue"]
  Q -->|Backlog| D["Queue depth"]
  Q --> C["Consumer group"]
  C -->|Progress position| L["Consumer lag"]
  C --> W["Worker processing"]
  W --> A["Ack / commit offset"]
  A --> Q
~~~

Nếu chỉ theo dõi số message đang có, nhóm vận hành có thể bỏ lỡ tình huống consumer bị kẹt ở partition cụ thể. Nếu chỉ theo dõi lag, hệ thống queue không có offset semantics có thể cần queue depth, oldest message age hoặc unacked count thay thế.

## 2. Queue depth là gì?

Queue depth là số message/task đang tồn tại trong một trạng thái được broker hoặc hệ thống queue xác định. Tùy công nghệ, depth có thể tính:
- Message sẵn sàng để giao (ready/available).
- Message đã giao nhưng chưa acknowledge (unacked/in-flight).
- Tổng ready + unacked.
- Message đang chờ retry hoặc delay.
- Message trong một subscription cụ thể.

Do đó, metric tên queue_depth ở hai broker khác nhau có thể không cùng semantics.

Ví dụ một queue có:
~~~text
ready messages       = 800
unacked messages     = 120
delayed messages     = 50
total outstanding    = 970 (nếu metric định nghĩa tổng gồm cả ba nhóm)
~~~

Khi xem dashboard, phải đọc định nghĩa metric. Nếu queue depth chỉ tính ready messages, 120 unacked vẫn có thể đang giữ tài nguyên và ảnh hưởng throughput.

Queue depth tăng liên tục thường báo hiệu producer đang gửi nhanh hơn consumer xử lý, consumer bị lỗi, số consumer không đủ hoặc downstream dependency chậm. Tuy nhiên một queue có depth cao nhưng consumer throughput cũng cao và message age thấp có thể là burst được xử lý bình thường.

## 3. Consumer lag là gì?

Consumer lag đo khoảng cách tiến độ giữa dữ liệu đã được broker ghi nhận và vị trí consumer group đã xử lý/commit. Khái niệm phổ biến nhất là Kafka consumer lag.

Với một partition:

~~~text
log end offset       = 12,500
committed offset     = 12,100
consumer lag         = 400 records
~~~

Với nhiều partitions, lag của group thường được tổng hợp bằng tổng hoặc hiển thị riêng từng partition. Cần xác minh exporter/broker metric đang dùng cách nào.

Lag có thể tăng khi:
- Producer tăng tốc độ publish.
- Consumer xử lý chậm.
- Consumer instances giảm hoặc không rebalance thành công.
- Một partition bị hot key và xử lý lệch tải.
- Consumer liên tục retry một record.
- Commit offset bị chậm hoặc không diễn ra.
- Downstream database/API chậm làm handler kéo dài.

Lag là số lượng records chưa được commit/đọc theo metric semantics, không trực tiếp là thời gian chờ. Một lag 10.000 records có thể được xử lý trong vài giây nếu throughput cao, hoặc nhiều giờ nếu consumer gần như dừng.

## 4. Phân biệt queue depth, consumer lag và message age

Ba metric trả lời các câu hỏi khác nhau:

| Metric | Câu hỏi | Đơn vị thường gặp |
| --- | --- | --- |
| Queue depth | Có bao nhiêu message đang chờ? | messages/tasks |
| Consumer lag | Consumer đang chậm bao nhiêu vị trí so với producer/log? | records/offsets |
| Oldest message age | Message cũ nhất đã chờ bao lâu? | seconds |
| Processing duration | Một message mất bao lâu để xử lý? | milliseconds/seconds |
| Consumer throughput | Consumer hoàn tất bao nhiêu message mỗi giây? | messages/second |
| Unacked/in-flight | Có bao nhiêu message đang được xử lý nhưng chưa ack? | messages |

Oldest message age thường hữu ích để hiểu tác động người dùng. Queue depth lớn không luôn đồng nghĩa message bị trễ lâu; queue depth nhỏ cũng có thể chứa một message bị kẹt rất lâu.

Ví dụ:
- Depth=20.000, throughput=5.000/s, age=3s: backlog lớn nhưng đang thoát nhanh.
- Depth=30, throughput=0/s, age=900s: queue nhỏ nhưng consumer có thể đã dừng.
- Kafka lag=50.000 nhưng message age thấp: producer vừa có burst lớn và consumer đang bắt kịp.

Không dùng một ngưỡng depth chung cho mọi queue. Kết hợp depth/lag với age, throughput và SLA xử lý.

## 5. Kafka: lag theo consumer group và partition

Kafka lưu records trong partition và consumer group giữ vị trí offset đã commit. Consumer lag thường được tính:

\[
lag_{partition} = log\_end\_offset - committed\_offset
\]

Tổng lag group có thể là tổng lag trên các partitions:

\[
lag_{group} = \sum_{p \in partitions} lag_p
\]

Đây là mô hình phổ biến; exporter có thể dùng current offset, committed offset hoặc log end offset với cách lấy mẫu khác nhau. Một số dashboard hiển thị lag theo partition để thấy skew.

Ví dụ:

| Partition | Log end | Committed | Lag |
| --- | ---: | ---: | ---: |
| 0 | 10.000 | 9.800 | 200 |
| 1 | 12.000 | 11.950 | 50 |
| 2 | 9.000 | 8.000 | 1.000 |
| **Total** | | | **1.250** |

Partition 2 chiếm phần lớn lag. Nếu chỉ nhìn tổng 1.250, nhóm vận hành không biết consumer đang bị lệch tải ở partition nào.

### 5.1. Consumer group và offset commit

Kafka consumer có thể auto-commit hoặc commit thủ công. Offset commit không nhất thiết đồng nghĩa business operation đã hoàn tất nếu ứng dụng commit sai thời điểm.

Với at-least-once processing, ứng dụng thường cần xử lý thành công rồi mới commit để tránh mất message; đổi lại có thể xử lý lặp nếu crash sau khi xử lý nhưng trước commit. Idempotency và deduplication cần được thiết kế ở tầng nghiệp vụ.

Lag tăng không tự chứng minh consumer không xử lý. Có thể consumer đang xử lý nhưng commit offset chậm. Cần so sánh:
- Records consumed.
- Records processed successfully.
- Commit rate/commit failures.
- Consumer lag.
- Processing duration.
- Rebalance events.

## 6. Queue metrics trong các broker khác

Không phải mọi messaging system đều có offset semantics như Kafka.

| Hệ thống | Metric thường quan tâm | Cần chú ý |
| --- | --- | --- |
| RabbitMQ | Ready, unacked, total messages, consumer count | Ready và unacked là trạng thái khác nhau |
| Kafka | Consumer lag theo group/partition, records in/out | Lag dựa trên offsets/commit |
| Amazon SQS | Approximate number of messages visible, not visible, oldest message age | Một số số liệu là approximate và có độ trễ cập nhật |
| ActiveMQ/Artemis | Queue message count, delivering, consumer count | Xác minh semantics của broker/version |
| In-memory task queue | Pending, running, completed, failed | Cần tự định nghĩa lifecycle và durability |

Ví dụ RabbitMQ:
- Ready: message có thể được giao cho consumer.
- Unacked: đã giao nhưng consumer chưa ack.
- Total: thường được hiển thị theo tổng trạng thái tùy dashboard/broker.

Ví dụ SQS:
- Visible: message đang chờ nhận.
- Not visible: message đang trong visibility timeout sau khi nhận.
- Delayed: message chưa sẵn sàng giao.

Không cộng các metric này nếu broker đã cung cấp một metric total bao gồm chúng; tránh double-count.

## 7. Backlog tăng: producer nhanh hơn consumer

Một queue ổn định khi tốc độ xử lý dài hạn ít nhất cân bằng tốc độ message mới đến. Gọi:
- \(\lambda\): arrival rate, message/second.
- \(\mu\): processing rate tổng, message/second.

Nếu \(\lambda > \mu\), backlog tăng xấp xỉ:

\[
\Delta backlog \approx (\lambda - \mu) \times \Delta t
\]

Ví dụ producer gửi 1.200 msg/s, consumer group xử lý 900 msg/s. Backlog tăng khoảng 300 msg/s. Sau 10 phút:

\[
300 \times 600 = 180{,}000\ messages
\]

Nếu \(\mu > \lambda\), backlog có thể giảm; thời gian drain lý tưởng xấp xỉ backlog chia cho phần throughput dư:

\[
drain\_time \approx \frac{backlog}{\mu-\lambda}
\]

Ví dụ backlog 60.000, arrival 500/s, processing 1.000/s: thời gian drain lý tưởng khoảng 120 giây. Đây là ước lượng ổn định, chưa tính burst, retries, partition imbalance, processing variance và downstream limits.

## 8. Ước lượng thời gian drain và tác động SLA

Queue depth/lag chỉ là số lượng. Để dự đoán khi nào hệ thống bắt kịp, cần throughput và arrival rate.

~~~text
Backlog                  = 120,000 messages
Producer arrival rate    = 400 messages/second
Consumer processing rate = 1,000 messages/second
Net drain rate           = 600 messages/second
Estimated drain time     = 200 seconds
~~~

Nếu consumer throughput chỉ bằng arrival rate, backlog không giảm. Nếu throughput thấp hơn, backlog tiếp tục tăng.

Để hiểu SLA, đo oldest message age hoặc enqueue-to-completion latency. Một queue có thể drain nhanh nhưng đã vi phạm deadline của các message cũ; ngược lại, backlog mới có thể lớn nhưng age vẫn thấp.

Không coi drain-time estimate là cam kết. Đưa vào forecast một safety factor và kiểm tra downstream capacity trước khi tăng consumer concurrency.

## 9. Consumer throughput và processing duration

Consumer throughput đo số records hoàn tất mỗi đơn vị thời gian, không chỉ số records poll/receive.

Phân biệt:
- Received/polled: consumer đã lấy message.
- Started: handler bắt đầu.
- Succeeded: xử lý hoàn tất thành công.
- Failed: xử lý thất bại.
- Acked/committed: broker được báo tiến độ theo protocol.

Nếu consumer poll nhanh nhưng handler xử lý chậm, received rate cao không có nghĩa backlog được giải quyết. Đo success completion rate và processing duration riêng.

Một message có thể được retry nhiều lần. Tính throughput theo unique business completion hay processing attempts cần được xác định rõ; nếu không, dashboard có thể báo consumer nhanh trong khi nhiều attempts bị lặp.

## 10. Partition imbalance và hot partitions

Kafka phân phối records vào partitions. Consumer group song song xử lý partitions, nhưng một partition thường chỉ được gán cho một consumer trong group tại một thời điểm theo mô hình phổ biến.

Nếu key phân phối lệch, một partition có thể nhận nhiều traffic hơn các partition khác. Tổng consumer capacity có thể còn dư nhưng partition nóng vẫn tăng lag.

~~~mermaid
flowchart TD
  P["Producer records"] --> A["Partition 0"]
  P --> B["Partition 1"]
  P --> C["Partition 2"]
  A --> X["Consumer A"]
  B --> Y["Consumer B"]
  C --> Z["Consumer C"]
  C --> L["Lag tăng tại partition 2"]
~~~

Dấu hiệu:
- Một partition lag cao hơn rõ rệt.
- Consumer assigned partition đó có processing duration cao.
- Một key chiếm tỷ trọng lớn.
- Tổng throughput group có vẻ tốt nhưng oldest message age ở một nhóm tăng.

Tăng consumer replicas không nhất thiết giải quyết hot partition nếu số partitions không tăng hoặc một key vẫn luôn map vào cùng partition. Thay đổi partitioning/key strategy cần xem xét ordering, stateful processing và compatibility.

## 11. Retry, poison messages và dead-letter queue

Một message lỗi có thể được retry nhiều lần. Retry làm giảm throughput hữu ích và có thể giữ backlog tăng. Một poison message luôn thất bại có thể bị xử lý lặp, chặn partition/queue tùy semantics.

Cần quan sát:
- Retry attempts và retry delay.
- Failure category.
- Processing duration.
- Dead-letter queue depth/age.
- Number of redeliveries.
- Message processing success/failure rate.

DLQ không phải nơi backlog biến mất. Nếu DLQ tăng, cần cảnh báo và quy trình xử lý. Không xóa message lỗi chỉ để giảm dashboard depth.

Idempotency rất quan trọng với at-least-once delivery. Consumer có thể nhận lại message sau timeout/crash hoặc redelivery; xử lý trùng cần an toàn.

## 12. Spring Boot: instrument message processing

Spring Boot/Micrometer có các integration cho một số messaging technologies. Observation có thể bao quanh producer send và consumer process tùy binder/framework/instrumentation. Không giả định mọi broker client tự động phát đủ metrics hoặc spans chỉ vì có Actuator.

Một observation thủ công cho task nghiệp vụ có thể minh họa:

~~~java
public void process(OrderCreated event) {
    Observation.createNotStarted("orders.process", observationRegistry)
            .lowCardinalityKeyValue("event.type", "order-created")
            .observe(() -> orderHandler.handle(event));
}
~~~

Trong production, cần đặt observation quanh đúng lifecycle của handler, bao gồm error/retry semantics. Nếu listener framework đã instrument consumer operation, tránh tạo span thứ hai cùng boundary; observation nghiệp vụ có thể mô tả bước xử lý riêng.

Low-cardinality tags nên là event type, destination group, outcome hoặc consumer name hữu hạn. Không đưa message ID, customer ID, order ID hay payload vào metric labels.

## 13. Propagate trace context qua message

Distributed trace có thể tiếp tục qua asynchronous boundary nếu producer inject trace context vào message headers và consumer extract context trước khi xử lý.

~~~mermaid
sequenceDiagram
  participant API as order-service
  participant Broker
  participant Worker as fulfillment-worker
  API->>Broker: Publish OrderCreated + trace context
  Broker-->>Worker: Deliver message + headers
  Worker->>Worker: Extract context / start consumer span
  Worker->>Worker: Process order
  Worker-->>Broker: Ack / commit
~~~

Với OpenTelemetry, propagation thường sử dụng W3C Trace Context hoặc format tương thích. Framework integration có thể tự inject/extract. Nếu tự xử lý headers, dùng propagator API; không tự parse traceparent bằng string logic rời rạc.

Một message được xử lý sau vài phút vẫn có thể thuộc trace ban đầu, nhưng trace retention/sampling và span lifecycle cần được cân nhắc. Với workflow rất dài, span link có thể phù hợp hơn parent-child liên tục tùy mô hình messaging và tracing convention.

Trace sampling không thay thế queue metrics. Một message không có trace được lưu vẫn phải được tính trong queue depth, lag và throughput metrics.

## 14. Queue depth và lag trong metrics

Các metrics nên phản ánh rõ semantics:

~~~text
messaging.queue.messages.ready
messaging.queue.messages.unacked
messaging.consumer.lag
messaging.consumer.records.processed
messaging.consumer.processing.duration
messaging.consumer.errors
messaging.consumer.retries
messaging.dlq.messages
messaging.oldest_message.age
~~~

Các tên trên là ví dụ metric design, không phải tên mặc định của mọi Spring Boot integration. Dùng metric broker/exporter có sẵn nếu đã có và ghi rõ đơn vị/semantics.

Dimensions phù hợp:
- destination/queue/topic đã chuẩn hóa.
- consumer group.
- partition nếu số partition hữu hạn và cần thiết.
- outcome/category hữu hạn.
- application/service name.

Tránh labels:
- message ID, key tùy ý.
- order/customer/user ID.
- raw payload hoặc exception message.
- dynamic tenant values không giới hạn.

Partition labels làm tăng series theo số partitions nhưng thường hữu hạn; cần cân nhắc chi phí khi số topics/partitions rất lớn.

## 15. Alerting theo backlog, lag và age

Một alert chỉ dựa vào queue depth có thể báo động trong burst bình thường. Alert tốt thường kết hợp nhiều tín hiệu và thời gian kéo dài.

Ví dụ điều kiện cần xem xét:
- Consumer lag tăng liên tục qua nhiều cửa sổ.
- Oldest message age vượt SLA.
- Consumer success throughput thấp hơn arrival rate.
- Pending/ready tăng cùng processing errors/retries.
- Consumer group không có active members.
- DLQ depth hoặc DLQ age tăng.

Một số quy tắc khái niệm:

~~~text
Alert khi:
  oldest_message_age_seconds > 300
  trong 5 phút

Hoặc:
  consumer_lag tăng liên tục
  AND processed_rate < arrival_rate
  trong 10 phút

Hoặc:
  active_consumers == 0
  AND queue_depth > 0
~~~

Đây là logic minh họa; chọn ngưỡng theo SLA và broker. Với Kafka, consumer lag có thể dao động theo commit interval; cần tránh alert nhạy với dao động ngắn. Với queue có visibility timeout, visible/unacked metrics có thể có độ trễ cập nhật.

## 16. Dashboard để vận hành queue

Một dashboard hữu ích có thể chia thành bốn nhóm:

| Nhóm | Panel | Mục đích |
| --- | --- | --- |
| Backlog | Queue depth / lag theo topic/group/partition | Có bao nhiêu việc chưa xử lý? |
| Freshness | Oldest message age / enqueue-to-completion | Message chờ bao lâu? |
| Capacity | Arrival rate, success throughput, active consumers | Consumer có theo kịp producer không? |
| Reliability | Errors, retries, redeliveries, DLQ | Vì sao backlog không giảm? |

Khi lag tăng, dashboard cần drill down từ group tổng tới partition/queue, rồi tới consumer instance và dependency mà handler gọi. Một consumer xử lý message chậm vì database pool wait có thể làm lag tăng dù broker khỏe.

Không chỉ hiển thị tổng queue depth. Một topic có 20 partitions có thể có một partition lag rất cao và 19 partition gần như rỗng.

## 17. Troubleshooting queue depth và lag

| Triệu chứng | Nguyên nhân có thể | Hướng điều tra |
| --- | --- | --- |
| Depth/lag tăng đều | Arrival rate lớn hơn processing rate | So sánh publish và completion throughput |
| Lag tăng nhưng queue depth thấp | Metric semantics khác nhau hoặc commit lag | Kiểm tra offsets, group và exporter |
| Một partition lag cao | Hot key, partition imbalance, consumer stuck | Partition assignment, key distribution |
| Pending cao, throughput bằng 0 | Consumer down hoặc không poll | Health, active members, logs |
| Ready thấp nhưng unacked cao | Consumer giữ nhiều message/in-flight | Handler duration, ack timeout |
| Age tăng dù depth thấp | Một message bị kẹt hoặc retry lâu | Oldest message, poison message, DLQ |
| Retry tăng nhanh | Dependency lỗi hoặc poison payload | Error category, retry policy, downstream |
| DLQ tăng | Message không thể xử lý sau retry | DLQ age, failure reason, replay process |
| Consumer active nhưng lag không giảm | Poll/receive nhưng handler không complete/commit | Processed vs received vs committed |
| Scaling consumer không cải thiện | Partition limit, DB bottleneck hoặc hot key | Partition count, DB pool, per-partition lag |
| Queue depth đột ngột giảm | Purge, expiration, retention hoặc metric reset | Broker events và retention configuration |
| Metrics bị thiếu | Exporter/binder không thu thập hoặc label filter | Broker metrics và application registry |

### Quy trình điều tra

1. Xác định metric đến từ broker, consumer client hay custom instrumentation.
2. Đọc định nghĩa ready, unacked, lag và committed offset.
3. So sánh arrival rate với successful completion rate.
4. Xem oldest message age và processing duration.
5. Drill down theo topic/queue, group và partition.
6. Kiểm tra active consumers, rebalance và commit failures.
7. Kiểm tra retry, poison messages và DLQ.
8. Xem downstream dependencies như database/HTTP client.
9. Thay đổi concurrency/partition/retry có kiểm soát và đo lại.

## 18. Tình huống thực tế: Kafka consumer lag tăng

**Bối cảnh:** order-service publish 2.000 events/s. fulfillment-worker group xử lý 1.500 events/s. Lag tăng đều khoảng 500 records/s. p95 handler duration cũng tăng.

### Bước 1 — xác định phạm vi lag

Dashboard group cho thấy tổng lag lớn. Drill down phát hiện partition 7 chiếm 60% tổng lag. Consumer assigned partition 7 xử lý chậm hơn các consumer khác.

### Bước 2 — kiểm tra throughput và processing time

Consumer received rate cao nhưng successful completion thấp. Trace của một số message cho thấy handler chờ database operation lâu. Hikari pending connections tăng ở worker.

### Bước 3 — phân biệt broker với downstream bottleneck

Broker vẫn nhận và phục vụ records bình thường. Consumer lag xuất phát từ handler bị giới hạn bởi database connection pool; tăng số consumer có thể làm DB chịu thêm concurrency mà không tăng throughput.

### Bước 4 — khắc phục theo bottleneck

Rút ngắn transaction, giảm thời gian giữ connection, tối ưu query và kiểm soát concurrency. Nếu partition skew do key distribution, xem lại key strategy nhưng phải bảo đảm ordering nghiệp vụ.

### Bước 5 — dự báo drain

Sau tối ưu, completion rate đạt 2.600/s trong khi arrival vẫn 2.000/s. Backlog 180.000 records có net drain rate 600/s, thời gian drain lý tưởng khoảng 300 giây.

### Bước 6 — xác minh

Theo dõi group lag, per-partition lag, oldest message age, successful processing rate, handler p95, DB pool pending và DLQ. Xác nhận backlog giảm ổn định, không chỉ giảm tạm thời do purge hoặc retention.

**Bài học:** queue lag là triệu chứng end-to-end. Muốn giải quyết cần nối broker metrics với consumer processing spans và downstream metrics.

## 19. Bài thực hành và câu hỏi tự kiểm tra

### Bài tập A — định nghĩa semantics

Chọn một broker đang dùng. Viết rõ queue depth metric gồm ready, unacked, delayed hay tổng; consumer lag dựa trên offset/ack nào; oldest message age được tính ở đâu.

### Bài tập B — mô phỏng backlog

Tạo producer phát 1.200 tasks/s và consumer xử lý 900 tasks/s. Dự đoán backlog tăng sau 10 phút. Sau đó tăng consumer throughput lên 1.500/s và ước lượng thời gian drain.

### Bài tập C — Kafka partition lag

Tạo topic nhiều partitions và consumer group. Tạo key skew để một partition nhận nhiều records. Quan sát total lag và per-partition lag; giải thích vì sao thêm consumer có thể không giải quyết partition nóng.

### Bài tập D — retry và DLQ

Tạo poison message. Thiết lập retry giới hạn, backoff và DLQ. Quan sát retry count, processing throughput, queue lag và DLQ age. Xác minh message không bị mất âm thầm.

### Bài tập E — context propagation

Publish message từ một HTTP request có trace. Consumer extract context và tạo processing span. Kiểm tra trace/links, log correlation và behavior khi message được xử lý trễ.

### Bài tập F — dashboard/alert

Xây dashboard queue depth, consumer lag, oldest age, arrival/success throughput, active consumers và DLQ. Tạo alert theo SLA và kiểm thử burst ngắn để tránh false positive.

### Câu hỏi tự kiểm tra

1. Queue depth khác consumer lag như thế nào?
2. Vì sao queue depth cao không nhất thiết có nghĩa message đang chờ lâu?
3. Kafka consumer lag thường được tính từ những offsets nào?
4. Ready và unacked messages khác nhau ra sao?
5. Vì sao oldest message age quan trọng với SLA?
6. Arrival rate và processing rate quyết định backlog thế nào?
7. Cách ước lượng thời gian drain khi throughput lớn hơn arrival?
8. Vì sao per-partition lag cần được theo dõi?
9. Hot key ảnh hưởng consumer parallelism ra sao?
10. Received rate khác successful completion rate thế nào?
11. Retry và poison messages làm lag tăng như thế nào?
12. DLQ depth tăng cần được xử lý ra sao?
13. Trace context được propagate qua message headers thế nào?
14. Vì sao sampling traces không thay thế queue metrics?
15. Khi scaling consumers không hiệu quả, cần kiểm tra broker, partition hay downstream nào?

**Tiêu chí hoàn thành:** giải thích đúng queue depth/lag/age; hiểu semantics theo broker; tính backlog/drain; đọc per-partition lag và consumer throughput; phát hiện retry/DLQ/hot partition; instrument processing observations; propagate trace context; xây dashboard/alert theo SLA.

## 20. Ghi nhớ

- Queue depth đếm message theo trạng thái broker; consumer lag đo tiến độ consumer so với log/queue theo semantics cụ thể.
- Kafka lag thường dựa trên log end offset và committed offset, có thể cần drill down theo partition.
- Oldest message age và processing latency cho biết tác động thời gian mà depth/lag đơn thuần không thể hiện.
- So sánh arrival rate với successful completion rate để biết backlog tăng hay giảm.
- Queue depth lớn có thể là burst bình thường nếu throughput cao và age thấp; queue nhỏ vẫn có thể có message bị kẹt.
- Ready, unacked, delayed, received, processed và committed là các trạng thái khác nhau; không cộng hoặc so sánh nếu semantics không khớp.
- Partition imbalance/hot key có thể làm một partition lag dù tổng consumer capacity còn dư.
- Retry, poison messages và DLQ ảnh hưởng throughput hữu ích; theo dõi attempts, failures và DLQ age.
- Spring Boot/Micrometer Observation có thể đo producer/consumer processing nếu integration hỗ trợ; tránh tạo spans trùng.
- Dùng low-cardinality labels; không đưa message ID, key tùy ý hoặc payload vào metric tags.
- Propagate trace context qua message headers để liên kết request và worker; trace sampling không thay thế broker metrics.
- Alert theo lag trend, oldest age, throughput và active consumers gắn với SLA thay vì một ngưỡng depth chung.

## Tài liệu tham khảo

- [Spring Boot Reference — Messaging](https://docs.spring.io/spring-boot/reference/messaging.html)
- [Spring for Apache Kafka — Monitoring](https://docs.spring.io/spring-kafka/reference/kafka/micrometer.html)
- [Apache Kafka Documentation — Consumer Design](https://kafka.apache.org/documentation/#design_consumerposition)
- [RabbitMQ Documentation — Queues](https://www.rabbitmq.com/docs/queues)
- [Amazon SQS — CloudWatch metrics](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-available-cloudwatch-metrics.html)
- [Micrometer Observation Reference](https://docs.micrometer.io/micrometer/reference/observation.html)
- [OpenTelemetry — Context Propagation](https://opentelemetry.io/docs/concepts/context-propagation/)
- [OpenTelemetry Semantic Conventions — Messaging](https://opentelemetry.io/docs/specs/semconv/messaging/)

