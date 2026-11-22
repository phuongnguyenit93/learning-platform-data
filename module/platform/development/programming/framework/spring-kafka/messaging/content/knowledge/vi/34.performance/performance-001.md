# Đo throughput và latency

Hiệu năng của một ứng dụng Spring Kafka không thể đánh giá chỉ bằng số record producer gửi thành công hoặc thời gian một listener xử lý xong một message. Một luồng messaging có nhiều chặng: producer serialize và gửi record, broker ghi nhận, consumer fetch, listener xử lý, side effect hoàn tất và offset được commit. Mỗi chặng có throughput và latency riêng.

Đo đúng cần xác định ranh giới của phép đo, dùng bộ đếm và bộ đo thời gian phù hợp, quan sát percentile thay vì chỉ nhìn trung bình, đồng thời theo dõi consumer lag. Khi benchmark, phải kiểm soát payload, partition, replication, key distribution, concurrency và tốc độ tạo tải. Nếu không, con số throughput cao có thể chỉ phản ánh một test dễ hơn production.

Bài học thuộc chương **Hiệu năng** của module **SPRING_KAFKA_MESSAGING**, tập trung vào cách đo throughput và latency ở producer, consumer và toàn bộ pipeline, đọc các metric Kafka/Spring Kafka và thiết kế benchmark có thể lặp lại.

## Kết quả cần đạt

Sau bài học, bạn có thể:

- Phân biệt throughput, latency, processing time và consumer lag.
- Xác định ranh giới đo ở producer acknowledgement, listener processing và end-to-end.
- Tính throughput theo records/second và bytes/second.
- Đo latency bằng Micrometer Timer và thời gian monotonic.
- Theo dõi p50, p95, p99 thay vì chỉ dựa vào average.
- Phân biệt số lần xử lý thành công với số event nghiệp vụ duy nhất.
- Đọc các nhóm metric producer, consumer, broker và listener container.
- Hiểu lag theo partition và mối quan hệ giữa tốc độ sản xuất với tốc độ tiêu thụ.
- Thiết kế load test theo open-loop hoặc closed-loop.
- Phân tích ảnh hưởng của partition, key distribution, batching, compression và concurrency.
- Xây dựng dashboard và benchmark có warm-up, steady state, timeout và kết quả lặp lại.

## 1. Throughput và latency là hai đại lượng khác nhau

**Throughput** cho biết hệ thống hoàn thành được bao nhiêu công việc trong một đơn vị thời gian. Với Kafka, thường đo số record/giây hoặc byte/giây.

**Latency** cho biết một record mất bao lâu từ mốc bắt đầu tới mốc kết thúc đã chọn. Ví dụ, producer send latency có thể là thời gian từ lúc gọi send đến khi future hoàn tất; consumer processing latency là thời gian listener xử lý; end-to-end latency là thời gian từ lúc event được phát sinh hoặc publish đến lúc nghiệp vụ downstream hoàn tất.

| Chỉ số | Câu hỏi trả lời | Đơn vị thường dùng |
|---|---|---|
| Producer throughput | Producer gửi được bao nhiêu record? | records/s, bytes/s |
| Producer send latency | Mất bao lâu để broker acknowledge send? | ms |
| Consumer throughput | Listener xử lý thành công bao nhiêu record? | records/s |
| Listener processing latency | Listener mất bao lâu để xử lý một record? | ms |
| End-to-end latency | Event mất bao lâu từ nguồn tới kết quả cuối? | ms, s |
| Consumer lag | Consumer đang chậm bao nhiêu record so với log end? | records, offsets |
| Error/retry rate | Bao nhiêu lần xử lý thất bại hoặc retry? | errors/s, retries/s, % |

Throughput cao không bảo đảm latency thấp. Một hệ thống có thể xử lý 100.000 record/giây nhưng p99 latency vài giây do batch lớn hoặc queueing. Ngược lại, latency thấp với tải nhỏ không chứng minh hệ thống có khả năng chịu tải production.

## 2. Xác định chính xác ranh giới của phép đo

Trước khi viết metric hoặc benchmark, hãy mô tả mốc bắt đầu và mốc kết thúc.

~~~mermaid
flowchart LR
    A[Event created] --> B[Producer send]
    B --> C[Broker acknowledgement]
    C --> D[Consumer fetch]
    D --> E[Listener processing]
    E --> F[Business side effect]
    F --> G[Offset commit]
~~~

Có thể đo nhiều khoảng thời gian:

1. **Send latency**: từ lúc gọi KafkaTemplate.send đến lúc CompletableFuture hoàn tất.
2. **Broker residence/fetch delay**: từ timestamp record tại broker tới lúc consumer nhận, cần lưu ý loại timestamp và đồng bộ clock.
3. **Listener processing time**: từ lúc listener bắt đầu tới lúc xử lý xong.
4. **Business completion latency**: từ lúc nhận record tới lúc database hoặc side effect nghiệp vụ hoàn tất.
5. **End-to-end latency**: từ timestamp phát sinh/publish ở nguồn tới khi kết quả cuối được xác nhận.
6. **Commit latency**: thời gian xác nhận offset, tùy AckMode và transaction.

Không cộng hoặc so sánh các metric nếu chúng dùng ranh giới khác nhau. Ví dụ producer acknowledgement latency không phải end-to-end latency vì consumer chưa chắc đã xử lý record.

## 3. Đo throughput theo records/second và bytes/second

Trong một cửa sổ đo có độ dài T giây:

\[
Throughput_{records} = \frac{N_{successful\ records}}{T}
\]

\[
Throughput_{bytes} = \frac{B_{successful\ bytes}}{T}
\]

Ví dụ trong 60 giây, producer nhận acknowledgement cho 600.000 record:

\[
600.000 / 60 = 10.000\ records/s
\]

Nếu tổng payload là 900 MB trong cùng cửa sổ, byte throughput xấp xỉ 15 MB/s. Cần ghi rõ đang đo payload bytes, Kafka record bytes hay network bytes vì header, protocol overhead, compression và replication làm các giá trị khác nhau.

Khi đo consumer throughput, nên đếm record listener xử lý thành công. Nếu đếm mỗi lần listener được gọi, retry có thể làm số liệu tăng dù số event nghiệp vụ hoàn tất không tăng.

Nên theo dõi riêng:

- Records received.
- Processing attempts.
- Successful processing attempts.
- Failed attempts.
- Unique event IDs completed, nếu nghiệp vụ có deduplication.
- Records published to DLT.

Các bộ đếm này trả lời những câu hỏi khác nhau.

## 4. Đo latency bằng percentile

Latency thường có phân phối lệch: phần lớn record nhanh nhưng một số record chậm do GC, network, retry, database hoặc partition nóng. Average có thể che giấu tail latency.

| Percentile | Ý nghĩa |
|---|---|
| p50 | Một nửa record có latency không vượt quá giá trị này. |
| p90 | 90% record có latency không vượt quá giá trị này. |
| p95 | 95% record có latency không vượt quá giá trị này. |
| p99 | 99% record có latency không vượt quá giá trị này. |
| p99.9 | Nhìn sâu hơn vào tail, cần lượng mẫu đủ lớn. |

Ví dụ p50 = 12 ms, p95 = 80 ms, p99 = 700 ms cho thấy phần lớn record xử lý nhanh nhưng vẫn có một nhóm nhỏ chậm đáng kể.

Khi báo cáo benchmark, ghi rõ percentile, số lượng mẫu, thời gian đo và cách tạo tải. p99 tính từ vài trăm record không đáng tin như p99 tính từ hàng triệu record.

## 5. Dùng monotonic clock để đo khoảng thời gian trong một process

Khi đo duration trong cùng JVM, dùng clock monotonic như System.nanoTime thay vì trừ hai Instant hoặc currentTimeMillis. Đồng hồ wall-clock có thể bị điều chỉnh bởi NTP hoặc thao tác hệ thống.

Ví dụ:

~~~java
long startedAt = System.nanoTime();

orderService.handle(event);

long elapsedNanos = System.nanoTime() - startedAt;
long elapsedMillis = TimeUnit.NANOSECONDS.toMillis(elapsedNanos);
~~~

Nếu đo giữa hai máy hoặc hai service khác nhau, cần dùng timestamp wall-clock trong event và đồng bộ thời gian giữa host. Chênh lệch clock có thể làm end-to-end latency âm hoặc sai lệch.

Cũng cần phân biệt thời điểm event được tạo với thời điểm producer gửi. Một event có thể nằm trong application queue trước khi publish; nếu mục tiêu đo toàn bộ trải nghiệm nghiệp vụ, hãy chọn timestamp bắt đầu phù hợp.

## 6. Đo producer send latency bằng KafkaTemplate

Trong Spring Kafka hiện đại, KafkaTemplate.send trả về CompletableFuture. Có thể đo thời gian từ lúc gọi send tới khi future hoàn tất. Kết quả này phản ánh thời gian producer chờ kết quả gửi theo cấu hình acknowledgement.

Ví dụ dùng Micrometer:

~~~java
@Component
public class MeasuredOrderProducer {

    private final KafkaTemplate<String, OrderCreatedEvent> kafkaTemplate;
    private final MeterRegistry registry;
    private final Counter acknowledged;
    private final Counter failed;
    private final Timer sendTimer;

    public MeasuredOrderProducer(
            KafkaTemplate<String, OrderCreatedEvent> kafkaTemplate,
            MeterRegistry registry) {
        this.kafkaTemplate = kafkaTemplate;
        this.registry = registry;

        this.acknowledged = Counter.builder("app.kafka.producer.acknowledged")
                .tag("topic", "orders.created")
                .register(registry);

        this.failed = Counter.builder("app.kafka.producer.failed")
                .tag("topic", "orders.created")
                .register(registry);

        this.sendTimer = Timer.builder("app.kafka.producer.send")
                .tag("topic", "orders.created")
                .publishPercentileHistogram()
                .register(registry);
    }

    public void publish(OrderCreatedEvent event) {
        Timer.Sample sample = Timer.start(registry);

        try {
            kafkaTemplate.send(
                    "orders.created",
                    event.orderId(),
                    event
            ).whenComplete((result, error) -> {
                sample.stop(sendTimer);

                if (error == null) {
                    acknowledged.increment();
                } else {
                    failed.increment();
                }
            });
        } catch (RuntimeException exception) {
            sample.stop(sendTimer);
            failed.increment();
            throw exception;
        }
    }
}
~~~

Timer đo tới khi future hoàn tất; counter acknowledged chỉ tăng khi send thành công và failed tăng khi future hoặc lời gọi send thất bại. Trong ứng dụng thực tế, cần xử lý exception và log có correlation ID mà không ghi payload nhạy cảm.

Đây là send acknowledgement latency, không phải thời gian record nằm trong broker hoặc thời gian consumer xử lý. Nếu producer dùng acks=0, future completion không mang cùng ý nghĩa xác nhận broker như acks=1 hoặc acks=all.

## 7. Đo listener processing latency

Để đo thời gian nghiệp vụ trong listener, đặt Timer quanh lời gọi service:

~~~java
@Component
public class MeasuredOrderListener {

    private final OrderService orderService;
    private final MeterRegistry registry;
    private final Timer processingTimer;
    private final Counter processed;
    private final Counter processingFailed;

    public MeasuredOrderListener(
            OrderService orderService,
            MeterRegistry registry) {
        this.orderService = orderService;
        this.registry = registry;

        this.processingTimer = Timer.builder("app.kafka.listener.processing")
                .tag("listener", "orders-created")
                .publishPercentileHistogram()
                .register(registry);

        this.processed = Counter.builder("app.kafka.listener.processed")
                .tag("listener", "orders-created")
                .register(registry);

        this.processingFailed = Counter.builder("app.kafka.listener.failed")
                .tag("listener", "orders-created")
                .register(registry);
    }

    @KafkaListener(
            topics = "orders.created",
            groupId = "orders-fulfillment"
    )
    public void consume(OrderCreatedEvent event) {
        Timer.Sample sample = Timer.start(registry);

        try {
            orderService.handle(event);
            processed.increment();
        } catch (RuntimeException exception) {
            processingFailed.increment();
            throw exception;
        } finally {
            sample.stop(processingTimer);
        }
    }
}
~~~

Timer bao gồm thời gian xử lý service và được ghi cả khi service ném exception. Exception vẫn được ném lại để container error handler có thể retry hoặc recover theo cấu hình.

Counter processed trong ví dụ đếm lần xử lý thành công, không nhất thiết đếm event duy nhất. Nếu listener xử lý xong nhưng offset chưa commit và record được redeliver, processed có thể tăng thêm lần nữa. Muốn đo số event nghiệp vụ duy nhất, hãy đếm sau khi idempotency/deduplication xác nhận event ID đã hoàn tất.

## 8. Đo end-to-end latency

Để đo từ lúc event được tạo đến lúc consumer hoàn tất, event có thể mang timestamp phát sinh:

~~~java
public record OrderCreatedEvent(
        String eventId,
        String orderId,
        Instant occurredAt
) {}
~~~

Khi listener hoàn tất:

~~~java
Duration endToEnd = Duration.between(
        event.occurredAt(),
        Instant.now()
);

endToEndTimer.record(endToEnd);
~~~

Cách này cần đồng bộ clock giữa producer và consumer. Nếu hai máy lệch thời gian, kết quả có thể sai. Ngoài ra, occurredAt có thể là thời điểm nghiệp vụ phát sinh chứ không phải thời điểm publish; cần chọn đúng định nghĩa cho SLA.

Có thể đo thêm timestamp publish riêng nếu muốn tách thời gian event nằm trong ứng dụng trước khi gửi khỏi thời gian Kafka và consumer xử lý.

Không dùng System.nanoTime ở producer rồi so sánh với System.nanoTime ở consumer khác process/máy. Monotonic clock chỉ có ý nghĩa trong phạm vi cùng clock source.

## 9. Đo broker acknowledgement, network và client metrics

Kafka client cung cấp các metric về producer và consumer. Tên metric cụ thể có thể khác theo Kafka client version và cách exporter đặt tên, nhưng các nhóm đáng theo dõi gồm:

| Nhóm | Metric/ý nghĩa | Điều có thể phát hiện |
|---|---|---|
| Producer send | Record send rate, send total, error rate | Tốc độ gửi và lỗi produce. |
| Producer request | Request latency average/max | Broker/network response chậm. |
| Producer batching | Batch size, records per request, compression rate | Hiệu quả batching và compression. |
| Producer buffer | Buffer pool wait time, available buffer bytes | Producer bị nghẽn do buffer hoặc broker chậm. |
| Consumer fetch | Records consumed rate, fetch latency | Tốc độ fetch và thời gian chờ broker. |
| Consumer lag | Records lag max hoặc lag theo partition | Consumer tụt lại so với log end. |
| Consumer commit | Commit latency và commit rate | Chi phí xác nhận offset. |
| Consumer assignment | Số partition được assign | Phát hiện consumer không có partition hoặc phân phối lệch. |

Có thể lấy Kafka client metrics qua JMX hoặc tích hợp Micrometer/exporter tương thích. Không nên phụ thuộc một tên metric duy nhất mà chưa kiểm tra phiên bản client thực tế.

## 10. Consumer lag không phải latency

Consumer lag thường biểu diễn khoảng cách giữa log end offset và committed offset của consumer group trên từng partition. Lag cao cho biết consumer chưa theo kịp dữ liệu đã ghi, nhưng không trực tiếp cho biết mỗi record đã chờ bao nhiêu mili giây.

Ví dụ:

| Partition | Log end offset | Committed offset | Lag gần đúng |
|---|---:|---:|---:|
| 0 | 12.000 | 11.900 | 100 |
| 1 | 8.500 | 8.100 | 400 |
| 2 | 9.200 | 9.150 | 50 |

Tổng lag gần đúng là 550 record. Partition 1 đang tụt nhiều hơn các partition khác; có thể do key skew, dữ liệu xử lý chậm hoặc assignment/concurrency không cân bằng.

Lag có thể tăng dù consumer vẫn xử lý được record, nếu producer tạo record nhanh hơn consumer. Lag giảm khi tốc độ xử lý vượt tốc độ sản xuất trong một khoảng thời gian.

Không quy đổi lag thành thời gian bằng một hệ số cố định nếu tốc độ record thay đổi theo thời gian. Muốn đo record age hoặc time lag, cần dùng timestamp có định nghĩa rõ và clock đồng bộ.

## 11. Throughput, latency và lag cần xem cùng nhau

Một dashboard chỉ có throughput có thể che giấu việc backlog tăng. Một dashboard chỉ có latency có thể bỏ qua việc hệ thống đang không đủ năng lực xử lý tải.

| Quan sát | Diễn giải có thể |
|---|---|
| Throughput tăng, p99 ổn định, lag ổn định | Hệ thống đang theo kịp tải trong cửa sổ đo. |
| Throughput chững, p99 tăng, lag tăng | Consumer hoặc broker có thể đã chạm giới hạn. |
| Producer throughput cao, consumer throughput thấp | Backlog đang tích tụ. |
| Consumer throughput thấp, CPU thấp, lag cao | Có thể bị chờ I/O, dependency hoặc partition assignment không đủ. |
| p50 thấp nhưng p99 cao | Tail latency do hot partition, GC, retry hoặc downstream chậm. |
| Retry/DLT tăng cùng lag | Lỗi nghiệp vụ hoặc dependency đang cản tiến độ. |
| Producer buffer wait tăng | Broker/network hoặc producer batching/throughput có vấn đề. |

Hãy so sánh các metric theo cùng time window và cùng topic/group. Nếu dashboard lấy throughput theo 1 phút nhưng latency percentile theo 15 phút, việc đối chiếu có thể gây kết luận sai.

## 12. Thiết kế benchmark có warm-up và steady state

Một benchmark có thể chia thành ba giai đoạn:

1. **Warm-up**: khởi động JVM, tạo connection, khởi tạo metadata, nạp class và ổn định consumer group.
2. **Steady state**: phát tải đều trong khoảng đủ dài để lấy throughput và latency có ý nghĩa.
3. **Cool-down/drain**: dừng tạo tải và quan sát consumer xử lý hết backlog nếu mục tiêu là đo thời gian bắt kịp.

Không lấy vài giây đầu sau khi application start làm kết quả chính. Warm-up có thể chứa JIT compilation, broker connection setup, group join và cache initialization.

Mỗi lần benchmark nên ghi:

- Phiên bản Kafka broker và client/Spring Kafka.
- Số broker, partition, replication factor.
- Producer count và consumer instance/concurrency.
- Payload size và key distribution.
- acks, compression, batch size và linger.
- Consumer fetch settings, AckMode và processing logic.
- Thời gian warm-up và steady-state window.
- Số record/byte gửi, thành công, lỗi và DLT.
- p50/p95/p99 và lag đầu/cuối.
- CPU, memory, GC, network và disk utilization.

Chạy nhiều lần với cùng điều kiện và báo cáo median hoặc range giữa các lần chạy. Một lần benchmark đơn lẻ dễ bị ảnh hưởng bởi cache, GC hoặc hoạt động nền.

## 13. Open-loop và closed-loop load test

Hai cách tạo tải có thể cho kết quả rất khác nhau.

**Closed-loop**: load generator gửi request tiếp theo sau khi request trước hoàn tất. Khi hệ thống chậm, tốc độ tạo request tự giảm. Cách này phù hợp để đo hành vi với số client đồng thời cố định, nhưng có thể che giấu quá tải.

**Open-loop**: load generator phát record theo tốc độ mục tiêu độc lập với thời gian phản hồi. Cách này giúp kiểm tra hệ thống có chịu được arrival rate dự kiến hay không và backlog tăng như thế nào.

| Tiêu chí | Closed-loop | Open-loop |
|---|---|---|
| Tốc độ tạo tải | Phụ thuộc phản hồi | Theo lịch/tốc độ mục tiêu |
| Khi hệ thống chậm | Tải tự giảm | Tải tiếp tục tới |
| Phát hiện queue growth | Có thể khó hơn | Rõ hơn |
| Nguy cơ đo thiếu tail latency | Có thể gặp coordinated omission | Ít hơn nếu lịch phát tải được giữ ổn định |
| Phù hợp | Số client đồng thời cố định | SLA theo arrival rate, capacity planning |

Khi dùng open-loop, load generator phải đủ năng lực phát tải và ghi timestamp dự kiến. Nếu chính load generator bị nghẽn, kết quả không phản ánh Kafka.

## 14. Tránh coordinated omission

Coordinated omission xảy ra khi load generator chỉ gửi request mới sau khi request trước hoàn tất. Khi hệ thống chậm, load generator cũng gửi ít hơn, nên các khoảng thời gian hệ thống quá tải không được đại diện đầy đủ trong latency histogram.

Để giảm hiện tượng này:

- Dùng open-loop generator cho benchmark theo arrival rate.
- Ghi thời điểm dự kiến phát record và thời điểm thực sự phát.
- Tính latency từ thời điểm dự kiến nếu mục tiêu là đo trải nghiệm theo lịch gửi.
- Báo cáo cả offered load và achieved throughput.
- Kiểm tra load generator không bị CPU hoặc network giới hạn.

Nếu offered load là 20.000 record/s nhưng achieved throughput chỉ 12.000 record/s, hệ thống đang tích lũy backlog hoặc generator chưa đạt cấu hình. Không chỉ báo cáo achieved throughput mà bỏ qua tải yêu cầu.

## 15. Partition count và key distribution ảnh hưởng throughput

Kafka song song hóa chủ yếu qua partition. Consumer group có thể phân chia partition cho nhiều consumer member; một partition tại một thời điểm chỉ được gán cho một consumer trong group theo mô hình group thông thường.

Nếu topic có 4 partition nhưng consumer group có 12 consumer, tối đa 4 consumer có partition từ topic đó tại một thời điểm. Tăng concurrency vượt partition count không tự tăng throughput.

Key distribution cũng quan trọng. Nếu mọi record có cùng key, chúng thường đi vào cùng partition và tạo hot partition. Khi đó một consumer xử lý partition nóng trở thành bottleneck dù các consumer khác rảnh.

Benchmark cần thử:
- Key phân bố đều.
- Một số key có lưu lượng cao.
- Một key duy nhất.
- Không key hoặc partition assignment tùy chỉnh.

Không tăng partition chỉ để tăng số consumer nếu thứ tự theo key là yêu cầu nghiệp vụ. Tăng partition có thể thay đổi mapping key-to-partition và ảnh hưởng ordering khi dữ liệu cũ/mới cùng tồn tại.

## 16. Batching, compression và payload size

Producer có thể gom nhiều record thành batch trước khi gửi. Các cấu hình như batch size và linger time ảnh hưởng trade-off giữa throughput và latency.

- Batch lớn có thể tăng hiệu quả network và giảm request overhead.
- Linger cao cho producer thêm thời gian gom batch, thường cải thiện throughput nhưng tăng send latency.
- Compression giảm byte truyền và lưu trữ, nhưng tiêu tốn CPU.
- Payload lớn làm tăng network, serialization, broker I/O và consumer deserialization cost.

Consumer cũng có fetch settings ảnh hưởng lượng dữ liệu lấy mỗi request. Không tối ưu producer riêng lẻ rồi bỏ qua consumer hoặc broker.

Benchmark nên thử nhiều payload size đại diện production, ví dụ nhỏ, trung bình và lớn; đồng thời ghi rõ payload đã nén hay chưa và dùng serializer nào. Dữ liệu giả quá nhỏ có thể làm throughput cao hơn thực tế nhiều lần.

## 17. Concurrency và thời gian xử lý listener

Consumer concurrency tăng có thể tăng khả năng xử lý nếu có đủ partition và dependency chịu được tải. Tuy nhiên, tăng concurrency cũng tăng thread, connection, context switching và tải lên database/downstream.

Hãy đo:
- Records/s theo từng partition.
- Processing time p50/p95/p99.
- Consumer lag từng partition.
- Số consumer được assign partition.
- CPU, heap, GC và thread utilization.
- Connection pool wait time của database.
- Retry và error rate.

Nếu listener bị giới hạn bởi database connection pool, tăng concurrency có thể chỉ làm tăng số thread chờ connection. Nếu listener thực hiện HTTP call chậm, throughput phụ thuộc connection pool và timeout downstream.

Không đưa công việc bất đồng bộ ra executor rồi commit offset trước khi công việc hoàn tất nếu chưa có thiết kế offset/ordering phù hợp. Điều đó có thể làm metric listener trông nhanh nhưng nghiệp vụ thực tế chưa hoàn tất.

## 18. Micrometer và Spring Kafka observation

Spring Kafka có thể tích hợp Micrometer để quan sát KafkaTemplate và listener container ở các phiên bản hỗ trợ. Observation/timer tích hợp giúp thu thập các khoảng thời gian framework quản lý; custom Timer vẫn hữu ích để đo riêng nghiệp vụ.

Khi bật instrumentation:
- Kiểm tra version Spring Kafka và Boot hỗ trợ thuộc tính/observation API nào.
- Không ghi đè metric framework bằng custom metric có cùng tên.
- Dùng tag có cardinality thấp như listener, topic thuộc danh sách cố định, outcome.
- Không dùng eventId, orderId, customerId hoặc key làm metric tag.
- Giữ trace ID trong log/trace context thay vì metric label.

Custom metric cần trả lời câu hỏi vận hành cụ thể. Quá nhiều timer/counter trùng lặp làm dashboard khó đọc và tăng chi phí telemetry.

## 19. Ví dụ Prometheus cho throughput và latency

Nếu Micrometer export các counter/timer theo naming convention của Prometheus, có thể truy vấn rate và histogram. Tên thực tế phụ thuộc registry và cấu hình metric.

Ví dụ dạng truy vấn:

~~~promql
rate(app_kafka_producer_acknowledged_total[1m])
~~~

Tốc độ record producer được broker acknowledge trong cửa sổ 1 phút.

~~~promql
rate(app_kafka_listener_processed_total[1m])
~~~

Tốc độ listener xử lý thành công theo counter ứng dụng. Nhớ rằng counter này đếm lần xử lý thành công, có thể tăng lại khi record được redeliver.

Với histogram:

~~~promql
histogram_quantile(
  0.99,
  sum by (le) (rate(app_kafka_listener_processing_seconds_bucket[5m]))
)
~~~

Truy vấn minh họa p99 listener processing latency. Cần xác minh tên metric/bucket thực tế trong Prometheus trước khi đưa vào dashboard.

Nên có dashboard theo topic/listener cố định, hiển thị:
- Producer acknowledged rate và failed rate.
- Consumer processed rate và processing error rate.
- Listener p50/p95/p99.
- Producer send p50/p95/p99.
- Consumer lag theo partition.
- Retry, DLT và transaction abort rate.
- CPU, heap, GC, network và broker disk.

## 20. Phân tích bottleneck theo dấu hiệu

| Dấu hiệu đo được | Khả năng cần kiểm tra |
|---|---|
| Producer send latency tăng, buffer wait tăng | Broker/network chậm, buffer đầy, batch hoặc compression chưa phù hợp. |
| Producer throughput thấp, CPU cao | Serialization/compression hoặc ứng dụng producer bị giới hạn CPU. |
| Consumer fetch rate thấp, lag tăng | Assignment, fetch settings, broker/network hoặc ít partition. |
| Listener processing p99 cao | Database/HTTP, lock contention, GC hoặc xử lý payload nặng. |
| Một partition lag cao hơn hẳn | Hot key, key skew hoặc dữ liệu partition đó xử lý chậm. |
| Consumer lag tăng dù listener timer thấp | Có thể thời gian chờ trước listener, commit, rebalance hoặc metric processing chưa bao gồm queue wait. |
| DLT/retry tăng | Dependency hoặc dữ liệu lỗi làm giảm throughput hiệu dụng. |
| CPU thấp nhưng latency cao | Chờ I/O, pool cạn, lock hoặc broker/network. |
| CPU và GC cao, p99 tăng | Heap pressure, allocation hoặc batch/payload lớn. |

Không kết luận bottleneck chỉ từ một metric. Hãy đối chiếu client, broker, application, downstream và lag trên cùng cửa sổ thời gian.

## 21. Bài tập tổng hợp: benchmark OrderCreated pipeline

Xây dựng pipeline producer → topic orders.created → consumer Fulfillment. Mục tiêu là xác định throughput tối đa mà p99 listener latency vẫn nằm trong SLA.

Yêu cầu:

1. Tạo counter cho producer acknowledged/failed.
2. Đo producer send latency bằng Timer quanh KafkaTemplate future.
3. Tạo counter consumer success/failure và Timer cho listener processing.
4. Thêm event timestamp để đo end-to-end latency với clock đồng bộ.
5. Thu thập producer/consumer client metrics và consumer lag theo partition.
6. Tạo topic với nhiều partition và replication factor được ghi rõ.
7. Chạy payload nhỏ, vừa và lớn.
8. Chạy key phân bố đều và key skew để phát hiện hot partition.
9. So sánh các mức producer concurrency, consumer concurrency và partition count.
10. Thử batch/linger/compression theo từng lần, chỉ thay một nhóm biến mỗi lần.
11. Chạy warm-up rồi steady state tối thiểu đủ dài để có percentile có ý nghĩa.
12. Thử open-loop ở nhiều offered rate và ghi achieved throughput.
13. Theo dõi lag đầu/cuối, retry, DLT, CPU, heap, GC, network và disk.
14. Báo cáo records/s, bytes/s, p50/p95/p99, error rate và lag.
15. Lặp benchmark nhiều lần và ghi đầy đủ cấu hình để tái hiện.
16. Xác định mức tải đạt SLA cùng headroom trước khi hệ thống bão hòa.

Bài tập hoàn thành khi bạn chỉ ra được bottleneck chính, giải thích vì sao throughput hoặc p99 thay đổi và đề xuất thay đổi có số liệu chứng minh.

## 22. Thứ tự học và tiêu chí hoàn thành

| Chặng | Nội dung trọng tâm | Tiêu chí tự kiểm tra |
|---|---|---|
| 1. Metric model | Throughput, latency, lag | Phân biệt được từng chỉ số và đơn vị. |
| 2. Boundaries | Producer, broker, listener, end-to-end | Nêu rõ mốc bắt đầu/kết thúc mỗi phép đo. |
| 3. Throughput | Records/s và bytes/s | Tính được rate từ counter delta và time window. |
| 4. Latency | Timer, p50/p95/p99 | Đọc được tail latency và sample count. |
| 5. Instrumentation | Micrometer và Kafka client metrics | Thu thập metric có tag cardinality thấp. |
| 6. Consumer lag | Offset theo partition | Phát hiện partition nóng và backlog tăng. |
| 7. Load model | Open-loop/closed-loop | Hiểu offered load, achieved throughput và coordinated omission. |
| 8. Tuning variables | Partition, key, batch, compression, concurrency | Thiết kế benchmark thay đổi biến có kiểm soát. |
| 9. Diagnosis | App, broker, network, downstream | Dùng nhiều metric để xác định bottleneck. |
| 10. Capacity | SLA, headroom và repeatability | Báo cáo mức tải đạt SLA có thể tái hiện. |

Bài học hoàn thành khi bạn đo được throughput và latency ở đúng ranh giới, theo dõi percentile và consumer lag, đồng thời thiết kế benchmark có warm-up, steady state và offered load rõ ràng. Bạn cũng cần giải thích được ảnh hưởng của partition, key distribution, batching, compression, concurrency và downstream dependency.

Throughput cho biết hệ thống xử lý được bao nhiêu; latency cho biết một record phải chờ bao lâu; lag cho biết consumer đang tụt lại bao nhiêu. Chỉ khi nhìn ba nhóm chỉ số cùng với error/retry rate và tài nguyên broker/application, bạn mới có thể đánh giá năng lực thực tế của một pipeline Spring Kafka.

