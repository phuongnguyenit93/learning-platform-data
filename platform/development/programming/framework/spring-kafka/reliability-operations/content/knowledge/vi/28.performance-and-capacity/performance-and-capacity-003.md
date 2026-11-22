# Listener processing time

## 1. Listener processing time là gì?

Trong Spring Kafka, **listener processing time** là thời gian ứng dụng dành để xử lý dữ liệu sau khi Kafka consumer nhận record và gọi listener method. Đây là một chỉ số hiệu năng quan trọng vì nó ảnh hưởng tới throughput, consumer lag, khả năng giữ partition assignment và capacity của service.

Ví dụ Order Fulfillment tiêu thụ topic orders.created. Mỗi record cần kiểm tra dữ liệu, đọc trạng thái đơn hàng, gọi Inventory và ghi kết quả vào database. Nếu listener xử lý trung bình 40 ms nhưng p99 lên tới 3 giây, một số partition có thể bị chậm dù average vẫn trông tốt.

~~~text
Kafka broker
    |
    | ConsumerRecord
    v
KafkaConsumer.poll()
    |
    v
Spring Kafka listener container
    |
    v
@KafkaListener method
    |
    +--> validate event
    +--> load business state
    +--> call downstream services
    +--> update database
    |
    v
Listener returns / throws
    |
    v
Acknowledgment, error handling, next poll
~~~

Cần phân biệt listener processing time với:

- **Poll duration:** thời gian một lời gọi KafkaConsumer.poll() mất để trả về.
- **End-to-end event latency:** thời gian từ lúc producer tạo/publish event đến lúc business outcome hoàn tất.
- **Consumer lag:** khoảng cách giữa offset consumer đã xử lý/commit và log end offset.
- **Commit latency:** thời gian cần để commit offset hoặc hoàn tất transaction.
- **Downstream latency:** thời gian DB, HTTP, cache hoặc service phụ thuộc phản hồi.

Một listener có thể xử lý nhanh nhưng consumer vẫn lag do ít partition/concurrency, broker fetch chậm hoặc downstream commit. Ngược lại, poll có thể trả nhanh nhưng listener mất nhiều thời gian trước khi poll tiếp theo.

## 2. Vì sao processing time quan trọng?

Thời gian xử lý quyết định mỗi consumer có thể hoàn tất bao nhiêu record trong một đơn vị thời gian. Khi tốc độ message đến cao hơn tốc độ xử lý, backlog tăng.

Ví dụ:

~~~text
Producer rate       = 1,000 records/second
Consumer capacity   =   700 records/second

Backlog growth      =   300 records/second
~~~

Ngay cả khi listener không có lỗi, hệ thống vẫn không theo kịp traffic. Nếu tình trạng kéo dài, consumer lag và event age tăng, có thể vi phạm SLA nghiệp vụ.

Processing time còn tác động tới:

- Thời gian giữa các lần poll.
- max.poll.interval.ms và group membership.
- Số lượng consumer instances cần thiết.
- Kích thước batch và memory pressure.
- Database connection pool và HTTP connection pool.
- Retry frequency và duplicate processing.
- Chi phí CPU, memory, tracing và metrics.
- Khả năng phục hồi sau một đợt traffic spike.

Không nên tối ưu mỗi average processing time. Percentiles, throughput, lag và downstream saturation cần được xem cùng nhau.

## 3. Các mốc thời gian trong một lần xử lý record

Một record có nhiều khoảng thời gian khác nhau:

~~~text
t0: producer tạo event
 |
 v
t1: record được broker append
 |
 v
t2: consumer poll nhận record
 |
 v
t3: listener bắt đầu
 |
 v
t4: listener hoàn tất hoặc ném exception
 |
 v
t5: acknowledgment / offset commit hoàn tất
 |
 v
t6: business outcome được xác nhận ở downstream
~~~

Các metric tương ứng:

| Khoảng | Ý nghĩa |
|---|---|
| t0 đến t1 | Producer-side creation/publish delay, tùy timestamp |
| t1 đến t2 | Broker retention/fetch/consumer scheduling delay |
| t2 đến t3 | Container dispatch delay |
| t3 đến t4 | Listener processing time |
| t4 đến t5 | Ack/commit/transaction completion |
| t0 đến t6 | End-to-end business latency |

Không nên dùng timestamp của Kafka record như một clock tuyệt đối nếu producer và consumer clock không đồng bộ. Với end-to-end latency, cần xác định timestamp source và clock synchronization.

### 3.1. Đo đúng ranh giới

Nếu bắt đầu timer ngay đầu listener và dừng ngay trước return, timer đo thời gian method body. Nếu timer bao gồm validation, DB và HTTP calls thì đó là listener processing duration theo góc nhìn ứng dụng.

Nếu muốn đo thời gian tới khi Kafka offset commit, cần instrumentation ở container/ack/transaction lifecycle phù hợp. Không cộng commit time vào listener timer bằng cách suy đoán.

## 4. Record listener và batch listener

Spring Kafka hỗ trợ hai kiểu listener phổ biến.

**Record listener** nhận từng ConsumerRecord:

~~~java
@KafkaListener(topics = "orders.created")
public void consume(OrderCreated event) {
    orderService.process(event);
}
~~~

Mỗi invocation xử lý một record. Processing timer có thể đo một lần gọi method.

**Batch listener** nhận một danh sách record:

~~~java
@KafkaListener(
    topics = "orders.created",
    containerFactory = "ordersBatchFactory"
)
public void consume(List<ConsumerRecord<String, OrderCreated>> records) {
    for (var record : records) {
        orderService.process(record.value());
    }
}
~~~

Một invocation xử lý nhiều record. Nếu timer đo quanh toàn bộ method, kết quả là **batch processing time**, không phải latency riêng của từng record.

Ví dụ batch có 100 records và method mất 500 ms:

- Batch duration = 500 ms.
- Average service time theo phép chia đơn giản = 5 ms/record.
- Nhưng không thể kết luận mỗi record đều mất 5 ms.
- Một record có thể mất 300 ms, các record còn lại nhanh hơn.

### 4.1. Cần chọn đúng đơn vị

| Listener type | Timer method-level đo gì? | Cần thêm gì nếu muốn per-record latency? |
|---|---|---|
| Record | Một record invocation | Thường đã gần với per-record duration |
| Batch | Cả batch | Timer/metric riêng trong vòng lặp hoặc per-record observation phù hợp version |
| Async handoff | Thời gian submit task | Timer trong worker để đo business completion |
| Transactional listener | Thời gian listener method | Thêm transaction/commit outcome nếu cần |

Với batch, nên theo dõi đồng thời batch size, batch duration và throughput records/second.

## 5. Các yếu tố tạo nên processing time

Một listener thường thực hiện nhiều bước:

~~~text
Listener invocation
       |
       +--> Deserialize / conversion (thường trước method)
       |
       +--> Validation
       |
       +--> Business rules
       |
       +--> Database reads/writes
       |
       +--> HTTP / RPC calls
       |
       +--> Cache / lock / filesystem
       |
       +--> Result mapping
       |
       v
Method returns
~~~

Lưu ý rằng deserialization, interceptor và container dispatch có thể nằm ngoài ranh giới method-level timer tùy instrumentation. Nếu cần đo toàn bộ pipeline từ fetch tới business completion, phải đo ở các điểm tương ứng.

Các yếu tố thường chiếm nhiều thời gian:

- Database query, transaction lock hoặc connection pool wait.
- HTTP call tới service khác.
- Retry/backoff đồng bộ.
- CPU-heavy JSON transformation hoặc cryptography.
- Batch quá lớn.
- Lock contention trong shared state.
- Garbage collection và memory allocation.
- Thread scheduling/CPU throttling.
- Logging hoặc tracing quá nặng.
- Schema registry hoặc external lookup trong hot path.

Không giả định listener chậm là do Kafka broker. Đa số business processing time nằm trong ứng dụng hoặc dependencies.

## 6. Đo thủ công bằng System.nanoTime()

Một cách đơn giản là dùng System.nanoTime() để đo duration trong listener:

~~~java
@KafkaListener(topics = "orders.created")
public void consume(OrderCreated event) {
    long started = System.nanoTime();

    try {
        orderService.process(event);
    }
    finally {
        long elapsedNanos = System.nanoTime() - started;

        log.debug(
            "Order listener processing completed in {} ms",
            elapsedNanos / 1_000_000.0
        );
    }
}
~~~

**System.nanoTime()** phù hợp đo khoảng thời gian trong cùng JVM vì nó là monotonic clock. Không dùng System.currentTimeMillis() để đo duration ngắn vì wall clock có thể thay đổi do đồng bộ thời gian.

Đoạn code trên vẫn log duration trong finally nếu business service ném exception. Nếu muốn phân biệt success và failure, cần ghi outcome rõ ràng:

~~~java
long started = System.nanoTime();
String result = "success";

try {
    orderService.process(event);
}
catch (RuntimeException ex) {
    result = "failure";
    throw ex;
}
finally {
    long elapsed = System.nanoTime() - started;
    processingMetrics.record(elapsed, result);
}
~~~

Ở production, nên dùng Timer/Observation để có histogram và percentiles thay vì chỉ ghi từng duration vào log.

## 7. Dùng Micrometer Timer

Micrometer Timer đo số lần thực hiện và thời gian hoàn tất. Timer có thể cung cấp:

- Count.
- Total time.
- Max.
- Histogram/percentiles nếu được cấu hình.
- Distribution statistics tùy registry.

Ví dụ custom Timer:

~~~java
@Component
public class OrderProcessingMetrics {

    private final Timer timer;

    public OrderProcessingMetrics(MeterRegistry registry) {
        this.timer = Timer.builder("app.kafka.order.processing")
            .description("Time spent processing an order event")
            .tag("listener", "orders-created")
            .register(registry);
    }

    public void record(Runnable action) {
        timer.record(action);
    }
}
~~~

Listener:

~~~java
@KafkaListener(topics = "orders.created")
public void consume(OrderCreated event) {
    processingMetrics.record(() -> orderService.process(event));
}
~~~

Đây là một metric tùy biến. Nếu Spring Kafka đã tạo timer cho listener, hãy kiểm tra metric có sẵn trước khi tạo thêm một timer trùng semantics.

### 7.1. Đo cả success và failure

Timer thường đo duration cho cả các invocation thành công và thất bại nếu wrapper ghi trong finally. Nếu cần phân loại outcome, có thể thêm tag result với tập giá trị hữu hạn:

~~~text
result=success
result=failure
~~~

Không đưa exception message, stack trace hoặc error ID vào metric tag. Nếu cần loại exception, map về một tập category hữu hạn như timeout, validation, dependency hoặc other.

### 7.2. Không tạo Timer cho từng record

Không tạo MeterRegistry.timer() mới với record key hoặc correlation ID. Việc tạo meter theo ID mỗi message gây tăng số time series không kiểm soát.

Đăng ký timer theo một tập tag cố định hoặc low-cardinality đã allowlist.

## 8. Spring Kafka Micrometer listener timers

Spring Kafka hỗ trợ Micrometer metrics cho listener containers. Trong cấu hình legacy Micrometer timers, listener processing được đo và xuất dưới metric có tên theo convention của Spring Kafka, thường là **spring.kafka.listener** ở các version hiện đại.

Container có thể bật/tắt instrumentation qua property:

~~~java
factory.getContainerProperties()
    .setMicrometerEnabled(true);
~~~

Có thể bổ sung static tags:

~~~java
factory.getContainerProperties()
    .setMicrometerTags(Map.of(
        "application", "fulfillment-service",
        "environment", "production"
    ));
~~~

Một số phiên bản hỗ trợ micrometerTagsProvider để thêm dynamic tags theo ConsumerRecord cho record listener. Provider này không áp dụng cho batch listener và không được dùng khi observationEnabled=true.

Tên meter, tags mặc định và behavior có thể khác theo version. Hãy kiểm tra metric thực tế trong registry hoặc actuator endpoint thay vì giả định tên tag từ một phiên bản khác.

### 8.1. Metric tags nên có cardinality thấp

Ví dụ phù hợp nếu topic/family có tập giá trị được quản lý:

~~~text
listener=orders-created
topic=orders.created
environment=prod
event.family=order
~~~

Không dùng:

~~~text
order.id=order-913828
correlation.id=order-flow-9281
offset=9812371
~~~

Những giá trị thay đổi theo từng message phù hợp hơn với logs/traces có kiểm soát, không phải metrics labels.

## 9. Micrometer Observation và tracing

Từ Spring Kafka 3.0, listener container có thể sử dụng Micrometer Observation. Khi bật observationEnabled và cấu hình ObservationRegistry, framework có thể tạo observation cho listener; các handlers đã đăng ký có thể xuất metrics và tracing spans.

~~~java
var properties = factory.getContainerProperties();

properties.setObservationEnabled(true);
properties.setObservationRegistry(observationRegistry);
~~~

Observation cho phép một nguồn instrumentation chung cho metrics và traces:

~~~text
Kafka listener invocation
          |
          v
       Observation
          |
     +----+----------------+
     |                     |
     v                     v
Meter handler        Tracing handler
     |                     |
     v                     v
Timer metrics          Span
~~~

Bật observation không tự bảo đảm có backend spans. Cần Micrometer Tracing bridge, exporter, sampler và tracing backend.

### 9.1. Observation khác custom Timer

- Observation tích hợp metrics/tracing theo một lifecycle chung.
- Timer thủ công phù hợp đo một đoạn business logic riêng.
- Có thể dùng cả hai nếu chúng đo các ranh giới khác nhau.
- Không tạo hai metrics cùng tên/semantics cho một invocation rồi cộng dồn như thể là hai loại công việc khác nhau.

Nếu đã có listener observation, custom Timer nên đo một bước cụ thể như database stage hoặc downstream call.

## 10. Percentiles quan trọng hơn average

Average processing time có thể che giấu tail latency.

Ví dụ 100 record:

- 95 record xử lý trong 10 ms.
- 5 record xử lý trong 2 giây.

Average:

~~~text
(95 x 10 ms + 5 x 2000 ms) / 100
= 109.5 ms
~~~

Average 109.5 ms có vẻ không quá cao, nhưng 5% record mất 2 giây. Với event quan trọng, tail latency có thể vi phạm SLA.

Nên quan sát:

| Statistic | Câu hỏi |
|---|---|
| p50 | Trường hợp điển hình mất bao lâu? |
| p90 | 10% chậm nhất bắt đầu ở đâu? |
| p95 | Tail latency phổ biến |
| p99 | Các trường hợp rất chậm |
| max | Có spike hoặc outlier nào? |
| count | Đã đo bao nhiêu invocation? |
| total time | Tổng thời gian processing |
| throughput | Bao nhiêu record hoàn tất mỗi giây? |

Percentiles được tính theo cách backend hỗ trợ. Client-side percentiles và histogram buckets có semantics/chi phí khác nhau. Đối với Prometheus, histogram thường phù hợp để tổng hợp qua nhiều instances.

## 11. Cấu hình histogram và percentiles

Ví dụ custom Timer có histogram:

~~~java
Timer.builder("app.kafka.order.processing")
    .publishPercentileHistogram()
    .serviceLevelObjectives(
        Duration.ofMillis(50),
        Duration.ofMillis(100),
        Duration.ofMillis(250),
        Duration.ofSeconds(1)
    )
    .register(registry);
~~~

SLO buckets nên phản ánh yêu cầu nghiệp vụ. Nếu order event phải xử lý trong 200 ms, bucket 50/100/250 ms có thể hữu ích. Nếu listener gọi service ngoài với latency cao, cần bucket phù hợp thực tế.

Không bật percentile histogram cho mọi metric một cách vô điều kiện. Histogram buckets tạo thêm series và chi phí ingest. Đặt budget và chỉ bật ở listener quan trọng.

## 12. Batch size ảnh hưởng processing time thế nào?

Với batch listener, tổng duration thường tăng theo số record và độ phức tạp từng record.

Ví dụ:

~~~text
batch size = 100
average per-record work = 8 ms
sequential processing estimate = 800 ms
~~~

Đây là ước lượng đơn giản. Batch có thể có shared setup cost, database bulk operations hoặc parallelism, nên duration thực tế không nhất thiết bằng phép nhân.

Cần đo:

- Batch size.
- Batch processing duration.
- Records processed per batch.
- Average/p95 time per record nếu có instrumentation.
- Failure count và retry count.
- Time spent in shared DB/bulk operation.

### 12.1. max.poll.records

Kafka consumer property **max.poll.records** giới hạn số record trả về trong một lần poll. Giá trị cao có thể tăng throughput nếu xử lý batch hiệu quả, nhưng cũng có thể kéo dài thời gian xử lý batch và tăng memory pressure.

Giảm max.poll.records có thể giúp:

- Giảm thời gian xử lý mỗi batch.
- Giảm số record in-flight.
- Hạn chế thời gian giữa các poll.
- Giảm lượng công việc phải retry khi batch thất bại.

Nhưng giảm quá thấp có thể tăng overhead poll và giảm throughput. Cần benchmark với payload và dependency thực tế.

### 12.2. Batch database writes

Nếu listener có thể dùng bulk insert/update, batch processing đôi khi nhanh hơn xử lý từng record riêng. Tuy nhiên, batch lớn có thể giữ transaction/connection lâu và làm p99 xấu hơn.

Chọn batch size theo DB capacity, lock contention, memory và SLA.

## 13. max.poll.interval.ms và processing time

**max.poll.interval.ms** là giới hạn thời gian giữa các lần poll hợp lệ trong consumer group. Nếu listener xử lý quá lâu trước khi poll tiếp, consumer có thể bị xem là không còn tiến độ và partition assignment có thể thay đổi.

Ví dụ:

~~~text
max.poll.interval.ms = 300000 ms (5 phút)

poll() trả 200 records
listener xử lý batch mất 360 giây
poll tiếp theo đến quá muộn
~~~

Consumer có nguy cơ rời group/rebalance vì vượt max.poll.interval.ms.

Không giải quyết mọi vấn đề bằng cách tăng max.poll.interval.ms. Nếu listener bị treo do HTTP call không timeout, tăng interval chỉ làm sự cố kéo dài hơn và consumer lag tăng lâu hơn.

### 13.1. Cần tính tổng thời gian giữa polls

Thời gian giữa poll có thể bao gồm:

- Xử lý records trong batch.
- Error handling và blocking backoff.
- Rebalance callbacks.
- Transaction completion.
- GC pause hoặc CPU starvation.
- Các tác vụ đồng bộ khác trên consumer thread.

Một listener method mất 30 giây không phải lúc nào cũng có nghĩa khoảng poll là 30 giây nếu có nhiều lần poll/dispatch khác trong flow; cần xem container mode và thread thực tế.

## 14. pollTimeout khác processing time

**pollTimeout** là thời gian consumer poll chờ record. **Listener processing time** là thời gian xử lý record sau khi poll đã trả dữ liệu.

~~~text
pollTimeout = 5 seconds

poll():
  returned 20 records in 40 ms

listener:
  processes records in 2.5 seconds

next poll()
~~~

Trong ví dụ, poll latency là 40 ms; batch/listener processing time là 2.5 giây. Đổi pollTimeout không làm business logic nhanh hơn.

Nếu poll trả rỗng, thời gian chờ poll có thể dài tới pollTimeout nhưng listener processing time vẫn không có invocation tương ứng.

## 15. Downstream latency và connection pools

Listener thường gọi database hoặc HTTP service. Khi downstream chậm, listener processing time tăng.

Ví dụ:

~~~text
Listener processing = 900 ms
  validation         =  10 ms
  database pool wait = 300 ms
  SQL execution      = 100 ms
  payment HTTP       = 450 ms
  mapping/logging    =  40 ms
~~~

Tối ưu cần đo từng stage:

- Connection pool wait time.
- Query execution time.
- HTTP connection acquisition.
- DNS/TLS handshake.
- Remote response time.
- Retry/backoff duration.
- Serialization/deserialization.

Một DB query có thể nhanh nhưng chờ lấy connection 300 ms vì pool hết connection. Chỉ đo query duration sẽ không phát hiện bottleneck.

### 15.1. Timeout cho dependency

Đặt connect timeout, response/read timeout và overall deadline cho HTTP/RPC. Với database, đặt query timeout và transaction timeout phù hợp.

Không để một downstream call block consumer thread vô hạn. Retry phải có giới hạn và backoff; nếu không, một dependency outage có thể giữ toàn bộ listener capacity.

## 16. Retry làm processing time tăng

Khi listener ném exception, Spring Kafka error handler có thể retry record. Một lần business event có thể có nhiều processing attempts.

~~~text
Attempt 1 -> DB timeout -> backoff 1s
Attempt 2 -> DB timeout -> backoff 2s
Attempt 3 -> success
~~~

Cần phân biệt:

- **Attempt duration:** thời gian một lần gọi listener.
- **Retry backoff:** thời gian chờ giữa attempts.
- **Total recovery time:** tổng thời gian từ lần đầu tới outcome cuối.
- **End-to-end latency:** có thể bao gồm cả queue wait trước lần xử lý đầu.

Nếu timer nằm trong method listener, nó thường đo từng invocation chứ không tự cộng thời gian backoff nằm ngoài method. Nếu muốn đo total recovery time, cần state/timing ở tầng retry workflow hoặc tracing span bao trùm.

### 16.1. Retry không phải capacity

Retry có thể làm throughput giảm vì cùng một record tiêu tốn nhiều attempts. Nếu dependency lỗi, tăng concurrency hoặc giảm backoff một cách mù quáng có thể tạo thêm load lên dependency đang yếu.

Theo dõi attempt count, failure rate, backoff duration và DLT rate cùng processing timer.

## 17. Error handler và DLT ảnh hưởng latency

DefaultErrorHandler có thể retry và sau đó recover record. Nếu backoff dài, tổng thời gian từ lần nhận đầu tới recovery có thể rất lớn dù từng listener invocation ngắn.

~~~text
Listener attempt
     |
     v
Exception
     |
     v
Error handler
     |
     +--> Backoff
     |
     +--> Retry listener
     |
     +--> Recoverer / DLT
~~~

Đo riêng:

- Listener invocation duration.
- Error handler retry count.
- Backoff time.
- Recovery/DLT publish duration.
- Total time to final outcome.

Đừng gộp mọi thứ vào một timer rồi không còn phân biệt được business code chậm hay policy retry dài.

## 18. Transactions và acknowledgment

Với AckMode RECORD, BATCH, MANUAL hoặc MANUAL_IMMEDIATE, vị trí commit/ack khác nhau. Processing time của listener không nhất thiết bao gồm thời gian commit offset.

Với transactional listener, transaction có thể bao gồm listener processing và Kafka send/offset operations. Transaction completion có thể thêm latency sau khi method body kết thúc.

Nếu cần end-to-end commit latency, đo transaction lifecycle hoặc commit outcome ở đúng điểm. Không suy ra commit đã xong chỉ vì listener method return.

### 18.1. Database side effect và Kafka offset

Nếu listener ghi database rồi consumer crash trước khi Kafka offset commit, record có thể được giao lại. Listener processing timer sẽ ghi nhận thêm một invocation, dù business event chỉ có một outcome mong muốn.

Dùng idempotency/inbox pattern để bảo vệ side effects và hiểu đúng semantics của success metrics.

## 19. Concurrency và throughput

Spring Kafka concurrency tạo nhiều child consumers trong một listener container. Tăng concurrency có thể tăng khả năng xử lý song song, nhưng còn phụ thuộc số partition.

~~~text
Topic: orders.created (6 partitions)

concurrency = 3
  child 0 -> P0, P1
  child 1 -> P2, P3
  child 2 -> P4, P5
~~~

Nếu concurrency lớn hơn số partition, một số child có thể không được assign partition. Tăng concurrency vượt partition count không tự tăng throughput.

Cần cân nhắc:

- Số partition.
- CPU cores và CPU throttling.
- DB connection pool capacity.
- HTTP downstream rate limits.
- Listener thread blocking.
- Ordering requirement.
- Consumer group rebalance overhead.

### 19.1. Throughput ước lượng

Nếu một record mất trung bình 20 ms và được xử lý tuần tự trên một consumer thread:

~~~text
1 / 0.020 seconds = 50 records/second
~~~

Với 6 consumers độc lập, throughput lý thuyết có thể gần 300 records/second nếu partition và downstream cho phép. Thực tế sẽ thấp hơn do poll, serialization, network, commit, lock và shared dependencies.

Không lấy công thức đơn giản này làm capacity commitment. Dùng benchmark với workload đại diện.

## 20. Blocking và asynchronous processing

Một listener đồng bộ giữ consumer thread trong lúc xử lý:

~~~java
@KafkaListener(topics = "orders.created")
public void consume(OrderCreated event) {
    inventoryClient.reserve(event);
    paymentClient.authorize(event);
    orderRepository.save(event);
}
~~~

Nếu HTTP call mất 2 giây, consumer thread bị giữ trong khoảng đó. Điều này làm giảm số lần poll và có thể tác động max.poll.interval.ms.

Có thể chuyển một số công việc sang async processing, nhưng phải thiết kế offset acknowledgment cẩn thận. Nếu listener submit task rồi return, container có thể xem invocation hoàn tất và commit offset trước khi async task thành công.

Các lựa chọn:

- Giữ xử lý đồng bộ nhưng đặt timeout và tối ưu dependency.
- Dùng batch/bulk operation.
- Tạo một application-level work queue có durable handoff.
- Dùng async listener return types/acknowledgment pattern được Spring Kafka version hỗ trợ.
- Chỉ commit khi business completion semantics đã đạt.

**Async không tự làm throughput tăng** nếu downstream vẫn là bottleneck hoặc queue không có giới hạn.

## 21. Thread pools và backpressure

Nếu listener submit task vào executor, cần đặt giới hạn:

- Core/max pool size.
- Queue capacity.
- Rejection policy.
- Task timeout/cancellation.
- Shutdown behavior.
- Context propagation.
- Acknowledgment semantics.

Một queue không giới hạn có thể làm listener processing timer rất thấp (chỉ đo thời gian submit) trong khi thời gian chờ thực tế và memory tăng liên tục.

~~~text
Kafka listener
     |
     v
Executor queue
     |
     v
Worker threads
     |
     v
Database / HTTP
~~~

Cần đo riêng:

- Listener handoff duration.
- Queue wait time.
- Worker execution time.
- Queue depth.
- Rejected task count.
- Total time to business completion.

Backpressure phải làm producer rate hoặc consumer intake thích nghi với capacity thật, không chỉ đẩy backlog từ Kafka vào RAM.

## 22. Batch size, concurrency và memory

Tăng batch size có thể giảm overhead trên mỗi record nhưng tăng:

- Object allocations.
- Heap usage.
- GC pressure.
- Transaction duration.
- Retry cost khi batch thất bại.
- Khoảng cách giữa các poll.

Tăng concurrency có thể tăng parallelism nhưng cũng tăng connection usage và contention ở DB.

Nên thay đổi từng tham số và đo cùng một workload:

| Tham số | Tác động tích cực có thể có | Rủi ro |
|---|---|---|
| max.poll.records | Batch lớn hơn, amortize overhead | Processing dài, memory cao |
| concurrency | Nhiều consumer threads | DB/HTTP saturation, rebalance |
| fetch.min.bytes | Fetch efficiency trong workload phù hợp | Tăng latency chờ dữ liệu |
| fetch.max.wait.ms | Có thể cải thiện batching | Chờ fetch lâu hơn |
| max.poll.interval.ms | Chịu được processing dài hơn | Phát hiện consumer lỗi chậm hơn |
| DB pool size | Giảm pool wait nếu DB còn capacity | Quá tải DB, connection contention |

Không tăng tất cả cùng lúc vì sẽ khó xác định thay đổi nào tạo tác động.

## 23. Đo từng stage trong business logic

Một listener có thể dùng các Timer riêng cho các bước:

~~~java
@KafkaListener(topics = "orders.created")
public void consume(OrderCreated event) {
    validationTimer.record(() -> validator.validate(event));

    Order order = databaseTimer.recordCallable(
        () -> orderRepository.load(event.orderId())
    );

    paymentTimer.record(() -> paymentClient.authorize(order));

    persistenceTimer.record(() -> orderRepository.markPaid(order.id()));
}
~~~

Ví dụ chỉ minh họa ý tưởng; cần xử lý checked exceptions và kết quả trả về phù hợp với API Timer của Micrometer.

Stage timers giúp biết bottleneck ở validation, DB, payment hay persistence. Đặt tên metric ổn định, tag thấp cardinality và không tạo meter theo order ID.

Nếu listener có nhiều nhánh business, nên thống nhất semantics để tổng stage durations có thể giải thích được. Không phải mọi stage timer luôn cộng đúng bằng listener timer vì có overhead, parallel work hoặc nested calls.

## 24. Structured logging và slow listener diagnostics

Có thể ghi cảnh báo khi listener vượt một ngưỡng:

~~~java
long started = System.nanoTime();

try {
    orderService.process(event);
}
finally {
    long elapsedMs =
        TimeUnit.NANOSECONDS.toMillis(System.nanoTime() - started);

    if (elapsedMs > 500) {
        log.warn(
            "Slow Kafka listener: listener={}, durationMs={}, eventType={}",
            "orders-created",
            elapsedMs,
            event.getClass().getSimpleName()
        );
    }
}
~~~

Ngưỡng 500 ms chỉ là ví dụ. Chọn theo SLA và phân phối thực tế.

Không log payload, token, customer data hoặc raw key chỉ để chẩn đoán. Dùng correlation ID/trace ID đã được phê duyệt để liên kết logs và traces.

### 24.1. Log từng record có thể tự tạo bottleneck

Ở throughput cao, INFO log cho mọi record có thể làm I/O logging trở thành một phần đáng kể của listener processing time. Nên dùng metrics cho aggregate và log có chọn lọc cho slow/error cases.

Sampling log phải giữ đủ thông tin điều tra và không làm mất toàn bộ bằng chứng ở incident hiếm.

## 25. Đặt SLO cho listener processing

Một SLO nên định nghĩa rõ:

- Đo record invocation hay end-to-end event latency?
- Bắt đầu và kết thúc tại đâu?
- Bao gồm retry/backoff không?
- Bao gồm commit/transaction không?
- Đo success only hay cả failure?
- Percentile nào được dùng?
- Cửa sổ thời gian nào?
- Listener nào là critical?

Ví dụ:

~~~text
SLO:
  99% successful orders.created listener invocations
  complete within 250 ms over a rolling 30-minute window
~~~

SLO này không có nghĩa 99% event được publish tới business completion trong 250 ms nếu producer-to-consumer queue delay không được đo.

### 25.1. Alert theo nhiều tín hiệu

Một alert hữu ích có thể kết hợp:

- p95/p99 processing time tăng.
- Consumer lag tăng.
- Throughput giảm.
- Error/retry rate tăng.
- Downstream latency tăng.

Chỉ alert average latency cao có thể bỏ sót tail latency. Chỉ alert lag cao có thể không phân biệt consumer chậm với producer spike.

## 26. Benchmark và capacity planning

Benchmark listener processing cần workload đại diện:

1. Payload size gần production.
2. Phân phối event types thực tế.
3. Tỷ lệ success/failure/retry tương tự.
4. Database và downstream latency gần production.
5. Số partition và concurrency dự kiến.
6. Logging/tracing settings giống production.
7. Warm-up JVM và JIT.
8. Đo throughput, p50/p95/p99, lag, CPU, heap và connection pool.
9. Chạy đủ lâu để quan sát GC và sustained load.
10. Thử burst traffic và recovery sau dependency outage.

Không chỉ chạy benchmark với mock service phản hồi trong 1 ms rồi lấy kết quả làm capacity production.

### 26.1. Little's Law như một ước lượng

Little's Law:

~~~text
L = lambda x W
~~~

Trong đó:

- L là số công việc trung bình đang ở trong hệ thống.
- lambda là throughput trung bình.
- W là thời gian trung bình trong hệ thống.

Nếu consumer nhận 500 records/second và trung bình một record nằm trong pipeline 0.2 giây, số record trung bình đang in-flight/queued theo mô hình đơn giản là:

~~~text
L = 500 x 0.2 = 100 records
~~~

Đây là ước lượng hệ thống ổn định. Nó không thay thế đo lag hoặc tính toán partition capacity; cần xác định chính xác boundary của W.

## 27. Runbook khi listener processing time tăng

1. Xác định listener ID, topic, group và deployment version.
2. So sánh p50, p95, p99 và max với baseline.
3. Xem throughput và consumer lag theo partition.
4. Xác định record listener hay batch listener.
5. Kiểm tra batch size, max.poll.records và concurrency.
6. Đo DB connection pool wait và query latency.
7. Đo HTTP/RPC latency, timeout và retry count.
8. Kiểm tra CPU, heap, GC pause và thread contention.
9. Kiểm tra max.poll.interval.ms và rebalance events.
10. Tách listener invocation time khỏi retry backoff và commit latency.
11. Xem traces/logs của một số slow samples đã được phép.
12. Tối ưu bottleneck cụ thể, không tăng concurrency mù quáng.
13. Thay đổi một tham số mỗi lần và benchmark.
14. Xác nhận p95/p99, throughput và lag cải thiện cùng nhau.
15. Kiểm tra duplicate/replay và offset commit semantics sau thay đổi.

Khi listener processing time thấp nhưng lag vẫn tăng, hãy xem producer rate, partition count, fetch/poll, assignment và broker capacity. Không quy mọi backlog cho business method.

## 28. Những nhầm lẫn thường gặp

**Listener processing time bằng poll duration.** Sai; poll có thể trả nhanh rồi listener xử lý lâu.

**Average thấp nghĩa listener khỏe.** Sai; p95/p99 có thể rất cao.

**Batch timer là per-record timer.** Sai; thường đo toàn bộ invocation/batch.

**Tăng concurrency luôn tăng throughput.** Sai; partition count và downstream capacity giới hạn.

**Tăng max.poll.interval.ms sửa listener chậm.** Nó chỉ thay đổi ngưỡng liveness, không làm code nhanh hơn.

**Giảm pollTimeout làm business logic nhanh hơn.** Không đúng; pollTimeout là thời gian chờ poll.

**Timer listener bao gồm offset commit.** Không mặc định; commit/transaction có lifecycle riêng.

**Retry backoff nằm trong listener timer.** Không nhất thiết; tùy điểm instrumentation.

**Submit task async nghĩa business đã hoàn tất.** Sai; chỉ có thể đã handoff vào queue.

**Metric label có thể là order ID để debug.** Sai; dùng logs/traces theo policy.

**Tăng batch size luôn tốt.** Có thể tăng memory, tail latency và retry cost.

**Log mọi record giúp điều tra dễ hơn.** Logging volume có thể trở thành bottleneck.

## 29. Checklist triển khai

- [ ] Định nghĩa ranh giới listener processing time.
- [ ] Phân biệt poll, listener, commit và end-to-end latency.
- [ ] Xác định record hay batch listener.
- [ ] Bật Micrometer timers hoặc Observation phù hợp version.
- [ ] Theo dõi p50/p95/p99 và throughput.
- [ ] Có stage timers cho DB/HTTP nếu cần.
- [ ] Dùng low-cardinality metric tags.
- [ ] Không gắn record key, offset, correlation ID làm metric labels.
- [ ] Theo dõi batch size và max.poll.records.
- [ ] Đối chiếu max.poll.interval.ms với worst-case processing.
- [ ] Đặt timeout và bounded retry cho dependencies.
- [ ] Có backpressure và giới hạn executor queue.
- [ ] Không commit offset trước async business completion.
- [ ] Bảo vệ side effects bằng idempotency.
- [ ] Benchmark với payload/dependencies thực tế.
- [ ] Alert kết hợp latency, lag, throughput và failures.
- [ ] Có runbook điều tra slow listener.

## 30. Tài liệu tham khảo

- Spring Kafka Reference — Monitoring: https://docs.spring.io/spring-kafka/reference/kafka/micrometer.html
- Spring Kafka Reference — Micrometer Observation: https://docs.spring.io/spring-kafka/reference/appendix/micrometer.html
- Spring Kafka Reference — Listener Container Properties: https://docs.spring.io/spring-kafka/reference/kafka/container-props.html
- Micrometer Documentation — Timers: https://docs.micrometer.io/micrometer/reference/concepts/timers.html
- Apache Kafka Consumer Configuration — max.poll.interval.ms and max.poll.records: https://kafka.apache.org/documentation/#consumerconfigs

Đối chiếu đúng Spring Kafka, Micrometer và Kafka client version của ứng dụng vì meter names, default tags, batch observation và auto-configuration có thể thay đổi giữa các phiên bản.

## 31. Ghi nhớ

**Listener processing time** đo thời gian ứng dụng xử lý record hoặc batch trong listener. Nó khác poll duration, consumer lag, commit latency và end-to-end event latency. Muốn tìm bottleneck, phải xác định ranh giới đo rồi quan sát p50/p95/p99 cùng throughput và lag.

Spring Kafka có thể cung cấp Micrometer listener timers hoặc Observation; custom Timer hữu ích để đo các business stages như database và downstream calls. Với batch listener, timer quanh method thường đo cả batch, không phải từng record. Retry/backoff và transaction completion cũng có thể nằm ngoài listener method timer.

Tối ưu cần đo downstream latency, batch size, concurrency, max.poll.records, max.poll.interval.ms, CPU/GC và connection pools. Không tăng concurrency hoặc batch size một cách mù quáng; dùng benchmark đại diện, timeout, backpressure và idempotency. Chỉ xem listener khỏe khi latency, throughput, lag và offset progress đều đáp ứng mục tiêu vận hành.

