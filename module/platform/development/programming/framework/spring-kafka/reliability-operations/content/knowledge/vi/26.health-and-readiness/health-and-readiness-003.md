# Liveness của consumer thread

Một ứng dụng Spring Kafka có thể vẫn sống ở cấp process nhưng consumer thread đã ngừng tiến triển. HTTP endpoint vẫn trả lời, JVM vẫn dùng CPU, health endpoint tổng thể vẫn xanh, trong khi một `@KafkaListener` không gọi được `poll()` tiếp theo và consumer group bắt đầu tụt hậu. Đây là một dạng lỗi khó phát hiện nếu chỉ kiểm tra process hoặc container có đang chạy hay không.

**Liveness của consumer thread** là khả năng consumer thread tiếp tục thực hiện vòng đời tiêu thụ Kafka, đặc biệt là quay lại gọi `KafkaConsumer.poll()` trong thời gian phù hợp. Spring Kafka cung cấp cơ chế giám sát và application event `NonResponsiveConsumerEvent` để báo rằng consumer không phản hồi việc poll theo ngưỡng cấu hình. Tín hiệu này giúp phát hiện listener bị block, thread starvation, deadlock hoặc một tác vụ phụ thuộc đang chờ quá lâu.

Liveness của consumer thread khác với liveness của JVM/process, khác với readiness của ứng dụng và cũng khác với Kafka consumer group heartbeat. Muốn chẩn đoán đúng, cần kết hợp trạng thái container, tiến độ poll, `max.poll.interval.ms`, heartbeat/session timeout, thread dump, lag và thời gian xử lý nghiệp vụ. Một event non-responsive là **tín hiệu cần điều tra**, không phải bằng chứng rằng Kafka broker hỏng hoặc process chắc chắn phải restart.

## 1. Consumer thread làm gì?

Trong mô hình listener container thông thường, Spring Kafka quản lý một Kafka consumer trên một consumer thread. Thread này lặp lại các công việc:

1. Gọi `KafkaConsumer.poll()` để lấy records và duy trì hoạt động của consumer group.
2. Đưa records tới listener adapter hoặc listener method.
3. Chờ listener xử lý theo semantics record/batch, acknowledgment và transaction đã cấu hình.
4. Hoàn tất commit/recovery tương ứng.
5. Quay lại `poll()` để tiếp tục tiêu thụ.

Sơ đồ đơn giản:

~~~text
Consumer thread
      |
      v
  poll()
      |
      v
  records
      |
      v
@KafkaListener
      |
      +--> business logic
      +--> database / HTTP / cache
      +--> KafkaTemplate
      |
      v
ack / commit / recovery
      |
      v
  poll() tiếp theo
~~~

Nếu listener xử lý quá lâu hoặc bị block, consumer thread có thể không quay lại `poll()` đúng hạn. Kafka client có các cơ chế heartbeat và group membership, còn Spring Kafka có thể quan sát khoảng thời gian không thấy poll để phát hiện tình trạng consumer không tiến triển.

### 1.1. Thread còn sống không có nghĩa consumer còn tiến triển

Một Java thread có thể tồn tại nhưng đang:

- `BLOCKED` vì chờ monitor lock.
- `WAITING` hoặc `TIMED_WAITING` vì chờ future, semaphore, queue hoặc I/O.
- `RUNNABLE` nhưng mắc trong vòng lặp CPU không kết thúc.
- Chờ database connection pool hoặc HTTP response.
- Bị starvation vì executor không cấp được thread.
- Chờ một callback chỉ được thực thi khi chính thread đó tiếp tục tiến triển.

Vì vậy, kiểm tra thread có tồn tại hay process chưa exit là chưa đủ. Điều cần biết là **consumer có quay lại poll và xử lý được dữ liệu hay không**.

### 1.2. Consumer thread liveness không đồng nghĩa message throughput

Consumer có thể poll đều nhưng topic không có record. Khi đó consumer vẫn responsive dù throughput bằng 0. Ngược lại, consumer vừa nhận một batch rồi bị kẹt trong listener; throughput trước đó vẫn có thể cao nhưng poll progress đã dừng.

Hai câu hỏi cần đo riêng:

- **Liveness/progress:** consumer có tiếp tục poll theo giới hạn không?
- **Data progress:** consumer có nhận và hoàn tất records theo kỳ vọng không?

## 2. NonResponsiveConsumerEvent của Spring Kafka

Spring Kafka có application event `NonResponsiveConsumerEvent` để báo tình huống consumer không gọi hoặc không hoàn tất tiến trình poll trong khoảng thời gian mà container theo dõi. Đây là event ở tầng Spring Kafka, không phải một record được gửi từ broker và cũng không phải một exception bắt buộc được ném ra từ listener method.

Event giúp phát hiện những tình huống như:

- Listener method chờ một HTTP request quá lâu.
- Database query hoặc connection acquisition bị treo.
- Một lock trong ứng dụng bị giữ vô thời hạn.
- Consumer thread bị block bởi code đồng bộ.
- Thread pool hoặc JVM bị starvation.
- Một lỗi trong callback hoặc integration làm consumer không quay lại vòng poll.

Khi nhận event, hệ thống có thể ghi log, tăng metric, cập nhật trạng thái readiness hoặc kích hoạt một quy trình điều tra/recovery có kiểm soát.

### 2.1. Event không chứng minh thread đã chết

Tên “non-responsive” mô tả **không có poll progress trong ngưỡng theo dõi**. Thread có thể vẫn đang chạy một method, chờ network hoặc bị lock. Nó chưa chắc ở trạng thái TERMINATED.

Đây là lý do cần lấy thread dump và kiểm tra stack frames thay vì chỉ restart ngay.

### 2.2. Event không phải Kafka broker error

Consumer không poll có thể do code ứng dụng bị block trong khi broker hoàn toàn khỏe. Ngược lại, consumer có thể tiếp tục gọi poll nhưng liên tục gặp network/authorization errors. Hai tình huống có biểu hiện khác nhau và cần xem cả Kafka client logs.

## 3. monitorInterval, noPollThreshold và pollTimeout

Container có các thuộc tính để theo dõi thời gian không poll:

| Thuộc tính | Vai trò |
|---|---|
| `pollTimeout` | Thời gian một lần `poll()` có thể chờ dữ liệu trước khi trả về |
| `monitorInterval` | Chu kỳ monitor kiểm tra tình trạng consumer |
| `noPollThreshold` | Hệ số dùng để xác định khoảng không poll đủ dài để coi consumer không responsive |

Trong các phiên bản Spring Kafka hỗ trợ cơ chế này, ngưỡng phát hiện thường được tính dựa trên **poll timeout nhân với no-poll threshold**; monitor task kiểm tra theo `monitorInterval`. Vì vậy event không nhất thiết xuất hiện chính xác tại thời điểm ngưỡng vừa bị vượt. Hãy xác nhận cách tính và default trong Javadoc của version Spring Kafka đang triển khai.

Ví dụ minh họa:

~~~text
pollTimeout      = 5 giây
noPollThreshold  = 3.0
monitorInterval  = 10 giây

Ngưỡng không poll để đánh giá ≈ 5 × 3 = 15 giây
Monitor kiểm tra mỗi 10 giây

Event có thể được phát ở lần monitor kiểm tra
đầu tiên phát hiện khoảng không poll đã vượt ngưỡng.
~~~

Đây là ví dụ cách suy nghĩ về ba thông số, không phải cam kết event luôn phát đúng giây thứ 15. Poll scheduling, monitor scheduling và version implementation ảnh hưởng thời điểm quan sát.

### 3.1. Cấu hình ContainerProperties

Ví dụ Java:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
ordersListenerFactory(
        ConsumerFactory<String, OrderEvent> consumerFactory) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<
                    String, OrderEvent>();

    factory.setConsumerFactory(consumerFactory);
    factory.setConcurrency(3);

    ContainerProperties properties =
            factory.getContainerProperties();

    properties.setPollTimeout(5_000L);
    properties.setMonitorInterval(10);
    properties.setNoPollThreshold(3.0);

    return factory;
}
~~~

Các setter và kiểu dữ liệu của monitor interval cần khớp với phiên bản Spring Kafka trong dự án. Ví dụ thể hiện nơi cấu hình; không nên copy nguyên giá trị vào production khi chưa đối chiếu thời gian xử lý thực tế và API đang dùng.

### 3.2. Đừng đặt ngưỡng thấp hơn thời gian xử lý bình thường

Giả sử listener thường xử lý một batch trong 20 giây nhưng ngưỡng non-responsive chỉ là 15 giây. Hệ thống có thể phát event trong khi consumer đang thực hiện một công việc hợp lệ.

Hãy tính ngưỡng từ:

- Thời gian xử lý p95/p99.
- Kích thước batch và số record trong poll.
- Thời gian gọi database/HTTP.
- Thời gian chờ queue/lock.
- Poll timeout.
- `max.poll.interval.ms` và group protocol.

Không chọn threshold chỉ để event xuất hiện thật nhanh; false positives sẽ làm đội vận hành mất niềm tin vào cảnh báo.

## 4. Bắt NonResponsiveConsumerEvent

Có thể nhận event bằng Spring `@EventListener`:

~~~java
@Component
public class ConsumerLivenessEvents {

    private static final Logger log =
            LoggerFactory.getLogger(ConsumerLivenessEvents.class);

    @EventListener
    public void onNonResponsive(
            NonResponsiveConsumerEvent event) {

        log.error(
                "Kafka consumer has not polled within the expected " +
                "interval: listener={}, timeSinceLastPollMs={}, partitions={}",
                event.getListenerId(),
                event.getTimeSinceLastPoll(),
                event.getTopicPartitions());
    }
}
~~~

Ví dụ dùng các accessor thường có trên event trong các phiên bản Spring Kafka tương ứng. Hãy kiểm tra package và method signatures trong Javadoc của version dự án. Không giả định mọi version đều có cùng metadata hoặc constructor.

Event có thể cung cấp ngữ cảnh như listener ID, container, consumer, thời gian kể từ lần poll gần nhất và partitions. Chỉ sử dụng những field thực sự có trong API hiện hành.

### 4.1. Event handler nên nhẹ

Một event callback nên:

- Ghi structured log ngắn.
- Tăng counter.
- Lưu timestamp/last-known state vào cấu trúc thread-safe.
- Gửi tín hiệu cho health aggregator hoặc alert pipeline có giới hạn.

Không nên thực hiện một HTTP request kéo dài, truy vấn database nặng, sleep hoặc tự chạy một chuỗi restart trong callback. Event được publish trong lifecycle/container monitoring; callback nặng có thể làm chậm chính đường giám sát.

### 4.2. Không gọi KafkaConsumer trực tiếp từ event thread

Event có thể cung cấp tham chiếu consumer để chẩn đoán. Tuy nhiên, KafkaConsumer không thread-safe cho các thao tác tùy ý từ thread khác. Không gọi `poll()`, `seek()`, `commitSync()` hoặc thao tác consumer trực tiếp từ event listener.

Hãy dùng các API quản lý của Spring listener container và tuân thủ thread ownership. Nếu cần thread dump, lấy từ JVM/process bằng công cụ quản trị thay vì thao tác consumer.

## 5. Phân biệt các loại liveness

Từ “liveness” thường bị dùng cho nhiều lớp khác nhau:

| Lớp | Câu hỏi | Ví dụ tín hiệu |
|---|---|---|
| Process/JVM liveness | JVM còn chạy và có khả năng tiếp tục thực thi không? | Process state, deadlock, JVM fatal error |
| Container lifecycle | Spring listener container có được start và chưa stop không? | `isRunning()` |
| Consumer-thread progress | Consumer có quay lại poll đúng hạn không? | `NonResponsiveConsumerEvent` |
| Kafka group membership | Broker còn xem consumer là thành viên group không? | Heartbeat, session timeout, rebalance |
| Readiness | Instance có đủ khả năng nhận thêm traffic/công việc không? | Readiness probe và dependency policy |
| Business progress | Event có được xử lý thành công theo SLO không? | Success rate, oldest record age, lag |

Không dùng một health boolean duy nhất để đại diện tất cả những khái niệm này.

### 5.1. Container running không có nghĩa consumer responsive

`MessageListenerContainer.isRunning()` cho biết trạng thái lifecycle của container. Container có thể vẫn báo running trong khi consumer thread đang bị block và chưa poll tiếp.

### 5.2. Consumer responsive không có nghĩa topic có data

Consumer có thể poll đều nhưng không nhận record. Nếu topic trống và group không có lag, đây có thể là trạng thái tốt. Đừng đánh dấu unhealthy chỉ vì throughput bằng 0.

### 5.3. Group membership khác listener progress

Kafka có heartbeat và group coordination để phát hiện member mất kết nối hoặc không còn đáp ứng protocol. Một consumer thread có thể bị block trong listener trong khi heartbeat vẫn được duy trì một khoảng thời gian, nhưng `max.poll.interval.ms` vẫn giới hạn thời gian giữa các lần poll.

Vì vậy, group chưa rebalance ngay không chứng minh listener vẫn xử lý được dữ liệu.

## 6. max.poll.interval.ms và session.timeout.ms

Kafka consumer có các timeout khác nhau, mỗi timeout bảo vệ một khía cạnh.

| Cấu hình | Ý nghĩa |
|---|---|
| `max.poll.interval.ms` | Giới hạn thời gian giữa các lần poll trong consumer group protocol |
| `session.timeout.ms` | Ngưỡng broker chờ heartbeat trước khi xem member mất session |
| `heartbeat.interval.ms` | Tần suất heartbeat theo cấu hình client/protocol tương ứng |
| `pollTimeout` | Thời gian một lần poll có thể chờ dữ liệu trong container |
| `monitorInterval` | Tần suất Spring monitor kiểm tra |
| `noPollThreshold` | Hệ số ngưỡng phát hiện poll không tiến triển |

Các thông số này không thay thế nhau.

### 6.1. max.poll.interval.ms bảo vệ tiến độ poll

Nếu consumer không gọi `poll()` trong thời gian vượt `max.poll.interval.ms`, Kafka group coordinator có thể xem consumer không còn tiến triển và thực hiện cơ chế rời group/rebalance theo protocol.

Điều này đặc biệt quan trọng khi listener method chạy đồng bộ trên consumer thread. Một thao tác nghiệp vụ block quá lâu có thể khiến lần poll kế tiếp đến muộn.

### 6.2. session.timeout.ms bảo vệ heartbeat

Session timeout tập trung vào việc broker không nhận heartbeat trong khoảng thời gian quy định. Với classic consumer group protocol, heartbeat được xử lý bởi client background activity, nhưng tiến độ poll vẫn bị giới hạn bởi `max.poll.interval.ms`. Chi tiết có thể khác với group protocol mới và Kafka client version.

Không tăng `session.timeout.ms` để che một listener block. Cũng không tăng `max.poll.interval.ms` vô hạn vì điều đó có thể làm group chậm phát hiện consumer không tiến triển.

### 6.3. Ví dụ một listener block

~~~text
T0: consumer poll() nhận một batch
T1: listener bắt đầu xử lý batch
T2: HTTP downstream bị treo
T3: consumer thread vẫn chờ HTTP, chưa poll tiếp
T4: Spring monitor phát NonResponsiveConsumerEvent
T5: max.poll.interval.ms có thể bị vượt
T6: group coordinator xử lý member không tiến triển
~~~

Thời điểm và thứ tự thực tế phụ thuộc timeout, heartbeat protocol, monitor scheduling và thời gian block. Đừng coi event Spring và rebalance của Kafka là một sự kiện đồng thời.

## 7. Những nguyên nhân phổ biến khiến consumer thread không tiến triển

### 7.1. I/O đồng bộ không có timeout

~~~java
@KafkaListener(topics = "orders.events")
public void consume(OrderEvent event) {
    // HTTP client không có deadline phù hợp.
    paymentClient.charge(event);
}
~~~

Nếu downstream không trả lời, listener giữ consumer thread. Cần connect/read/call timeout, retry có giới hạn và circuit breaker phù hợp.

### 7.2. Database connection pool cạn

Listener có thể chờ lấy connection trong pool. Nếu các transaction khác giữ connection quá lâu, consumer thread không hoàn tất listener và không quay lại poll.

Theo dõi:

- Active/idle/pending connections.
- Connection acquisition timeout.
- Query duration.
- Transaction duration.
- Lock wait/deadlock.

Tăng consumer concurrency khi DB pool đã cạn có thể làm tình trạng nặng hơn.

### 7.3. Lock contention hoặc deadlock

Một thread có thể ở trạng thái `BLOCKED` chờ monitor, hoặc nhiều thread chờ lock theo vòng. Thread dump nhiều lần giúp xác định stack trace không thay đổi và lock owner.

### 7.4. Future.get()/join() không có deadline

~~~java
@KafkaListener(topics = "orders.events")
public void consume(OrderEvent event) throws Exception {
    downstreamClient.callAsync(event).get();
}
~~~

`get()` không timeout có thể chờ vô hạn. Dùng deadline phù hợp và xử lý cancellation/retry theo semantics; timeout phải bao phủ cả thời gian xử lý nghiệp vụ và budget poll.

### 7.5. CPU loop hoặc GC pressure

Một listener có thể thực hiện tính toán quá nặng, tạo object lớn hoặc kích hoạt GC pauses dài. Thread vẫn chạy nhưng poll progress bị chậm.

Theo dõi CPU throttling, allocation rate, heap, GC pause duration và processing latency.

### 7.6. Executor starvation

Nếu consumer tasks dùng chung executor với tác vụ dài hạn, consumer có thể không được chạy hoặc không được tiếp tục theo lịch mong đợi. Cần tách pool cho long-lived consumer tasks khỏi các công việc background/HTTP khác, hoặc cấp capacity theo tổng concurrency thực tế.

## 8. Poll loop và thời gian xử lý record/batch

Đối với record listener đồng bộ, listener method thường được gọi trong quá trình container xử lý records trả về từ poll. Thời gian xử lý các records trong một poll ảnh hưởng khoảng cách tới poll tiếp theo.

Ví dụ một poll nhận 100 records, mỗi record mất 200 ms:

~~~text
100 × 200 ms = 20.000 ms ≈ 20 giây
~~~

Đây là phép nhân đơn giản. Thời gian thực tế có thể khác do parallel work, batch listener, error handler, backoff, database contention và overhead framework.

Nếu `max.poll.interval.ms` chỉ 15 giây, một batch mất 20 giây có nguy cơ vượt giới hạn. Nếu dùng batch listener, thời gian xử lý cả batch cần nằm trong budget phù hợp.

### 8.1. Giảm max.poll.records không phải luôn là lời giải

Giảm `max.poll.records` có thể làm batch nhỏ hơn, giảm thời gian xử lý một poll. Nhưng nó cũng làm tăng số lần poll/commit và có thể giảm throughput do overhead.

Hãy đo:

- Batch size thực tế.
- Processing time per record/batch.
- Poll-to-poll interval.
- Commit latency.
- Consumer lag.

Sau đó điều chỉnh batch size và concurrency dựa trên dữ liệu.

### 8.2. Async listener không tự động giải quyết liveness

Một số kiểu listener trả về future hoặc dùng async processing có semantics riêng theo Spring Kafka version và ack mode. Không giả định mọi asynchronous method đều giải phóng consumer thread ngay mà vẫn bảo đảm offset chưa commit quá sớm.

Khi chuyển sang async, phải xác minh:

- Khi nào listener được xem là hoàn tất?
- Offset được acknowledge/commit ở thời điểm nào?
- Exception từ worker quay lại container ra sao?
- Consumer có thể nhận thêm records vượt khả năng queue không?
- Context/trace có được truyền qua thread boundary không?

## 9. Thread dump là công cụ chẩn đoán chính

Khi nhận `NonResponsiveConsumerEvent`, thread dump giúp xác định consumer thread đang ở đâu.

Trên JVM có thể dùng:

~~~bash
jcmd <pid> Thread.print
~~~

Hoặc:

~~~bash
jstack <pid>
~~~

Trong môi trường container, cần chạy bằng quyền phù hợp và đúng PID trong namespace process. Không đưa PID giả hoặc output thread dump chứa thông tin nhạy cảm lên kênh công khai.

### 9.1. Lấy nhiều thread dumps

Một thread dump duy nhất cho thấy snapshot. Lấy hai hoặc ba snapshot cách nhau vài giây có thể phân biệt:

- Thread đang tiến triển qua các stack frames.
- Thread chờ mãi tại cùng một network read.
- Thread bị lock.
- Thread chạy CPU loop.
- Thread đã kết thúc.

Đừng chỉ đọc trạng thái `WAITING` rồi kết luận deadlock; nhiều thread bình thường cũng chờ queue/condition.

### 9.2. Tìm consumer thread

Thread name phụ thuộc container type, concurrency, Spring Kafka version và naming configuration. Hãy tìm tên có liên quan listener/container hoặc Kafka consumer, sau đó xác nhận stack frames thực tế thay vì dựa vào một prefix cố định.

Stack trace có thể cho thấy:

- `KafkaConsumer.poll`: đang ở vòng poll.
- `SocketInputStream.read` hoặc network client: đang chờ I/O.
- `CompletableFuture.get`: chờ async completion.
- JDBC driver/connection pool: chờ database.
- Application service: đang thực hiện business logic.
- `AbstractQueuedSynchronizer`/monitor: chờ lock/semaphore.

### 9.3. Thread dump có thể chứa dữ liệu nhạy cảm

Stack traces có thể bao gồm URL, SQL, tên tenant, class names nội bộ và các giá trị trong local variables tùy công cụ. Lưu và chia sẻ theo chính sách bảo mật; không gửi toàn bộ dump ra kênh không được bảo vệ.

## 10. Ghi nhận NonResponsiveConsumerEvent và metric

Một listener nhẹ có thể tăng counter và log thời gian kể từ lần poll:

~~~java
@Component
public class ConsumerLivenessMonitor {

    private static final Logger log =
            LoggerFactory.getLogger(ConsumerLivenessMonitor.class);

    private final Counter nonResponsiveEvents;

    public ConsumerLivenessMonitor(MeterRegistry registry) {
        this.nonResponsiveEvents = Counter.builder(
                "app.kafka.consumer.non_responsive.events")
                .description("Non-responsive Kafka consumer events")
                .register(registry);
    }

    @EventListener
    public void onNonResponsive(
            NonResponsiveConsumerEvent event) {

        nonResponsiveEvents.increment();

        log.error(
                "Kafka consumer poll progress stalled: listener={}, " +
                "timeSinceLastPollMs={}, partitions={}",
                event.getListenerId(),
                event.getTimeSinceLastPoll(),
                event.getTopicPartitions());
    }
}
~~~

Ví dụ sử dụng Micrometer và accessor của event theo phiên bản Spring Kafka phù hợp. Metric này do ứng dụng tự định nghĩa; không phải tên metric mặc định của Spring Kafka.

### 10.1. Không tạo metric tag từ offset hoặc exception message

Metric tags nên có cardinality thấp, ví dụ:

- service.
- environment.
- listener ID (tập hữu hạn).
- failure category đã chuẩn hóa.

Không đưa topic-partition list thay đổi, offset, event ID, trace ID hoặc exception message nguyên văn vào metric labels. Dùng structured logs/traces cho chi tiết từng incident.

### 10.2. Deduplicate event

Nếu consumer vẫn bị block, monitor có thể tiếp tục phát event trong các chu kỳ kiểm tra. Đừng tạo một page mới cho mỗi event.

Có thể lưu:

- Listener/container ID.
- Instance/pod.
- Thời điểm non-responsive đầu tiên.
- Thời điểm gần nhất.
- Current incident state.
- Số lần event trong cùng incident.
- Thời điểm poll progress phục hồi.

Chỉ mở incident một lần khi trạng thái chuyển từ healthy sang stalled; cập nhật incident đang mở cho các event lặp; đóng khi poll progress được xác nhận trở lại.

## 11. Readiness và liveness probe nên phản ánh điều gì?

Trong môi trường Kubernetes hoặc nền tảng orchestration tương tự, thường có hai loại probe:

- **Liveness probe:** process cần restart vì không thể tự phục hồi.
- **Readiness probe:** instance có nên nhận thêm traffic/công việc mới hay không.

Một consumer thread bị non-responsive không tự động có nghĩa toàn JVM phải restart ngay. Có thể readiness cần chuyển sang false hoặc degraded trong khi liveness vẫn true để tránh restart loop.

### 11.1. Liveness probe không nên phụ thuộc trực tiếp vào Kafka broker

Nếu liveness endpoint trả fail mỗi khi Kafka broker tạm thời unavailable, orchestrator có thể restart toàn bộ pods cùng lúc, tạo rebalance storm khi broker vừa phục hồi.

Liveness nên phản ánh khả năng tiến triển của chính process/JVM và các failure state không tự hồi phục. Dependency health thường phù hợp hơn với readiness hoặc dependency-specific alert.

### 11.2. Readiness cho consumer worker

Nếu ứng dụng chỉ làm Kafka worker và không phục vụ HTTP traffic, readiness có thể được dùng để báo trạng thái vận hành cho orchestrator/monitoring. Cần định nghĩa:

- Consumer nào là bắt buộc?
- Có chấp nhận một consumer child tạm thời non-responsive không?
- Có thể tiếp tục nhận records ở các partitions khác không?
- Có thể pause một listener mà vẫn coi instance ready không?
- Khi nào cần remove instance khỏi service discovery?

Readiness không tự dừng Kafka listener container. Nếu muốn ngừng tiêu thụ khi not-ready, cần cơ chế pause/stop được thiết kế riêng và hiểu tác động group membership.

### 11.3. Tránh liveness restart loop

Nếu nguyên nhân là database timeout, restart pod có thể không giúp gì. Pod mới lập tức gặp cùng database outage, consumer group lại rebalance và có thể tạo thêm tải.

Chỉ dùng liveness failure để restart khi có bằng chứng process/thread state không thể phục hồi hoặc policy đã được kiểm thử. Với lỗi dependency tạm thời, dùng timeout, circuit breaker, backoff và readiness/degraded state.

## 12. Consumer liveness và group heartbeat

Kafka consumer group protocol có cơ chế duy trì membership. Các cấu hình classic thường được biết đến:

- `heartbeat.interval.ms`: nhịp heartbeat.
- `session.timeout.ms`: thời gian broker chờ heartbeat trước khi loại member.
- `max.poll.interval.ms`: thời gian tối đa giữa các lần poll.

Một consumer thread có thể đang xử lý listener trong khi client vẫn có heartbeat hoạt động. Tuy nhiên, nếu không gọi poll trong khoảng vượt `max.poll.interval.ms`, client/group protocol có thể xem member không còn tiến triển.

### 12.1. Hai timeout có mục tiêu khác nhau

~~~text
Heartbeat:
  "Consumer còn giữ được kết nối/membership không?"

max.poll.interval:
  "Consumer có tiếp tục lấy và xử lý records theo nhịp poll không?"

Spring NonResponsiveConsumerEvent:
  "Container quan sát thấy poll progress bị chậm hơn ngưỡng nội bộ?"
~~~

Đây là cách diễn giải vận hành, không phải mô tả mọi chi tiết protocol của mọi Kafka version. Group protocol mới có thể thay đổi cách heartbeat và membership được quản lý.

### 12.2. Static membership có nuance

Với static membership (`group.instance.id`), hành vi khi consumer vượt max poll interval có thể khác về thời điểm partition được reassigned so với dynamic member. Không giả định partition luôn chuyển ngay khi listener block; hãy kiểm tra Kafka client version, group protocol và logs coordinator.

## 13. Những event khác không nên nhầm với non-responsive

| Event | Thể hiện | Điều cần điều tra |
|---|---|---|
| `ConsumerStartedEvent` | Consumer đã bắt đầu | Assignment và poll progress sau đó |
| `ConsumerFailedToStartEvent` | Consumer không start trong startup timeout | Executor/lifecycle/startup capacity |
| `ConsumerStoppedEvent` | Consumer dừng | Shutdown, fatal error, lifecycle |
| `ListenerContainerIdleEvent` | Không nhận record trong khoảng idle | Input traffic, assignment, pause |
| `ListenerContainerNoLongerIdleEvent` | Consumer nhận lại record sau idle | Data flow đã phục hồi |
| `NonResponsiveConsumerEvent` | Không có poll progress theo ngưỡng monitor | Thread block, poll delay, dependency |
| `ConsumerPausedEvent` | Consumer đã pause | Backpressure/maintenance reason |
| `ConsumerResumedEvent` | Consumer đã resume | Delivery và backlog progress |

Idle event có thể hoàn toàn bình thường khi topic trống. Non-responsive event nói về poll progress; nó cần được điều tra ngay cả khi lag chưa lớn vì consumer có thể vừa bị block trước khi backlog kịp tích tụ.

## 14. Cách thiết kế dependency timeout

Consumer thread thường gọi database, HTTP, cache hoặc các service khác. Mỗi dependency cần timeout nằm trong ngân sách xử lý record.

Ví dụ budget đơn giản:

~~~text
Poll/processing budget mục tiêu: 30 giây

Database acquisition + query: tối đa 5 giây
HTTP downstream: tối đa 8 giây
Business computation: tối đa 5 giây
Retry/backoff trong listener: giới hạn rõ ràng
Cleanup/commit margin: phần thời gian còn lại
~~~

Đây là số minh họa. Cần tính worst-case/batch time và `max.poll.interval.ms` với margin thích hợp, không cộng các timeout riêng lẻ rồi quên retry/queueing.

### 14.1. Timeout ở mọi tầng

Nên xem xét:

- Connection timeout.
- Read/response timeout.
- Overall call deadline.
- Database connection acquisition timeout.
- Query timeout.
- Transaction timeout.
- Future wait timeout.
- Retry count và backoff cap.

Một timeout ở tầng ngoài không nhất thiết hủy được socket/query ở tầng dưới. Cần hiểu cancellation semantics của client và driver.

### 14.2. Không retry đồng bộ quá lâu trong consumer thread

Nếu listener retry một HTTP call 10 lần, mỗi lần 10 giây, tổng thời gian có thể vượt poll interval. Cân nhắc error handler backoff, retry topics, outbox hoặc state machine bất đồng bộ theo yêu cầu nghiệp vụ.

Retry topics có thể chuyển record sang một consumer flow khác, nhưng cần hiểu transaction/offset semantics và idempotency. Chuyển sang async cũng không được commit offset trước khi có durability phù hợp.

## 15. Listener processing duration và max.poll.interval.ms

Đo thời gian xử lý ở cấp record và batch:

| Metric | Ý nghĩa |
|---|---|
| Listener duration p50/p95/p99 | Phân bố thời gian xử lý |
| Max poll-to-poll interval | Khoảng cách thực tế giữa polls |
| Batch size | Số records xử lý trong một poll |
| Error handler/backoff duration | Thời gian retry/backoff |
| Dependency latency | DB/HTTP/cache time |
| Commit latency | Thời gian xác nhận offsets/transaction |

Nếu `max.poll.interval.ms` là 300 giây nhưng listener p99 chỉ 1 giây, liveness issue có thể do deadlock hoặc một số requests treo vô hạn. Nếu batch processing p99 là 280 giây, margin quá thấp và cần xem lại batch size/concurrency.

### 15.1. Đừng chỉ nhìn p99

Một listener có p99 tốt nhưng một record cụ thể bị treo vô hạn vẫn có thể làm consumer không poll. Cần quan sát oldest in-flight age, max duration và NonResponsiveConsumerEvent.

### 15.2. Poll timeout không phải processing timeout

`pollTimeout` chỉ điều khiển thời gian poll chờ records. Nó không giới hạn thời gian listener method chạy. Tăng poll timeout không giải quyết một HTTP call treo trong listener.

## 16. Xử lý non-responsive theo mức độ

Không phải mọi event đều cần restart. Một quy trình theo tầng:

~~~text
NonResponsiveConsumerEvent
          |
          v
Ghi incident + metrics + listener/instance
          |
          v
Lấy thread dump / kiểm tra dependency
          |
          v
Consumer tự quay lại poll?
       /           \
     Có             Không
     |               |
     v               v
Theo dõi lag     Kiểm tra deadlock/
và processing    blocked I/O/thread
                     |
                     v
             Có phương án phục hồi?
                /          \
              Có            Không
              |              |
              v              v
      Recovery có kiểm    Restart/replace
      soát, cooldown      theo policy đã test
~~~

Đây là một decision flow định hướng. Hành động thực tế phụ thuộc listener criticality, transaction semantics, group state và khả năng xử lý record trùng.

### 16.1. Ưu tiên phục hồi nguyên nhân

- HTTP bị treo: sửa timeout/circuit breaker hoặc phục hồi downstream.
- DB pool cạn: giải phóng connection, điều chỉnh transaction hoặc capacity.
- Lock deadlock: sửa thứ tự lock/code và xử lý transaction.
- CPU saturation: xử lý throttling/GC/algorithm.
- Executor starvation: cấp threads hoặc tách pool.
- Kafka network issue: kiểm tra broker/network/credentials.

Restart chỉ hữu ích khi process/thread state không tự phục hồi hoặc container đã vào trạng thái không thể tiếp tục.

### 16.2. Không stop/start lặp trong event callback

Nếu callback gọi stop/start ngay mỗi lần nhận event, có thể:

- Tạo restart loop.
- Tạo group rebalance liên tục.
- Duplicate processing do records chưa commit.
- Làm mất bằng chứng thread dump trước khi điều tra.
- Tăng tải lên broker/downstream.

Nếu cần tự phục hồi, hãy dùng một supervisor riêng có trạng thái, cooldown, giới hạn attempts và audit. Supervisor phải tránh thao tác cùng container đồng thời từ nhiều controllers.

## 17. Quản lý container bằng KafkaListenerEndpointRegistry

Với listener khai báo bằng `@KafkaListener`, có thể tìm container qua `KafkaListenerEndpointRegistry`:

~~~java
@Service
public class OrdersContainerSupervisor {

    private final KafkaListenerEndpointRegistry registry;

    public OrdersContainerSupervisor(
            KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public boolean isContainerRunning(String listenerId) {
        MessageListenerContainer container =
                registry.getListenerContainer(listenerId);

        return container != null && container.isRunning();
    }
}
~~~

Ví dụ này chỉ kiểm tra lifecycle. Nó **không chứng minh consumer thread đang responsive**. Hãy kết hợp event/last poll state và metrics.

### 17.1. Restart cần quy trình

Nếu đã xác định restart container là phương án phù hợp:

1. Kiểm tra container tồn tại và không có restart đang diễn ra.
2. Ghi lại incident context và thread diagnostics trước khi stop nếu có thể.
3. Dùng lifecycle API của container/registry đúng phiên bản.
4. Chờ stop completion theo API được hỗ trợ.
5. Start lại theo desired state.
6. Xác nhận consumer startup event, partition assignment và poll progress.
7. Kiểm tra lag, redelivery và idempotency.

Không giả định một lời gọi stop/start trả về là toàn bộ consumer threads đã được khởi tạo lại. Dùng lifecycle callbacks/events để xác nhận.

### 17.2. Một child consumer bị kẹt trong concurrent container

`ConcurrentMessageListenerContainer` có thể quản lý nhiều child consumers. Một child non-responsive không nhất thiết có nghĩa tất cả child đều lỗi. Cần xác định child/partition cụ thể trước khi restart toàn container, vì thao tác cấp container có thể gây rebalance rộng hơn.

## 18. Observability: metrics cần có

Một dashboard consumer liveness nên kết hợp:

| Metric/tín hiệu | Câu hỏi |
|---|---|
| Time since last poll | Consumer đã không poll bao lâu? |
| NonResponsiveConsumerEvent count | Có bao nhiêu lần vượt ngưỡng? |
| Listener processing duration | Listener có đang xử lý quá lâu? |
| Max poll interval observed | Có nguy cơ vượt max.poll.interval.ms? |
| Consumer lag by partition | Backlog có tăng không? |
| Records consumed rate | Consumer có tiếp tục nhận dữ liệu? |
| Business success rate | Công việc có hoàn tất? |
| Active consumer thread count | Có đủ threads chạy? |
| Executor active/queue/rejection | Có thread starvation? |
| JVM CPU/GC/heap | JVM có bị quá tải? |
| Dependency latency/error | DB/HTTP có đang block? |
| Rebalance count/duration | Group membership có bất ổn? |

Không phải tất cả các metric này có sẵn tự động trong mọi Spring Kafka version. Một số cần Micrometer, Kafka client metrics, JMX exporter và instrumentation của ứng dụng.

### 18.1. Alert theo thời gian và tác động

Một event đơn lẻ có thể là cảnh báo sớm; alert nghiêm trọng nên dựa trên:

- Non-responsive kéo dài qua nhiều lần monitor.
- Listener critical không có poll progress.
- Lag tăng hoặc oldest record age vượt SLO.
- Group bắt đầu rebalance hoặc mất assignments.
- Business success rate giảm.

Không page chỉ vì một consumer ít traffic hoặc topic đang trống. Nhưng nếu poll progress dừng và listener critical có backlog, cần nâng mức cảnh báo.

### 18.2. Không dùng event count thay cho duration

Nếu monitor phát event mỗi chu kỳ trong lúc consumer vẫn kẹt, counter tăng nhanh. Incident duration hoặc gauge last-poll-age giúp đo thời gian thực tế; counter chỉ đo số lần quan sát.

## 19. Readiness policy ví dụ

Một service có thể lưu trạng thái consumer liveness:

~~~java
@Component
public class ConsumerLivenessState {

    private final AtomicLong lastNonResponsiveAt =
            new AtomicLong(0L);

    private final AtomicLong lastResponsiveAt =
            new AtomicLong(System.currentTimeMillis());

    @EventListener
    public void onNonResponsive(
            NonResponsiveConsumerEvent event) {
        lastNonResponsiveAt.set(System.currentTimeMillis());
    }

    public void markPollProgressRecovered() {
        lastResponsiveAt.set(System.currentTimeMillis());
    }

    public boolean hasRecentFailure(long windowMs) {
        long failedAt = lastNonResponsiveAt.get();
        return failedAt > 0
                && System.currentTimeMillis() - failedAt < windowMs
                && lastResponsiveAt.get() < failedAt;
    }
}
~~~

Đây là mô hình minh họa state, **chưa phải implementation hoàn chỉnh**: cần một tín hiệu xác nhận poll progress phục hồi đáng tin cậy, phân biệt listener IDs/instances và xử lý nhiều child consumers. Không gọi `markPollProgressRecovered()` chỉ vì process nhận HTTP request hoặc container báo running.

### 19.1. HealthIndicator

Một custom Spring Boot `HealthIndicator` có thể đọc trạng thái trên để báo `UP`/`DOWN` hoặc status tùy biến. Cần xác định nó được map vào readiness hay liveness group theo Spring Boot version/configuration.

Không trả DOWN cho toàn ứng dụng chỉ vì một consumer optional bị non-responsive nếu service vẫn có thể thực hiện nhiệm vụ quan trọng khác. Có thể dùng degraded status hoặc health component riêng cho từng listener.

### 19.2. Readiness không tự điều khiển consumer

Khi readiness DOWN, Kubernetes thường ngừng gửi traffic Service tới pod; nó không tự dừng Kafka listener. Nếu policy yêu cầu ngừng nhận Kafka records, ứng dụng cần điều khiển pause/stop riêng, đồng thời cân nhắc group membership, rebalance và offset behavior.

## 20. Consumer thread liveness với retry và error handler

Một record thất bại có thể khiến consumer không quay lại poll trong thời gian backoff nếu retry được thực hiện đồng bộ trên consumer thread.

Ví dụ:

~~~text
poll() -> record
       |
       v
listener throws
       |
       v
blocking retry / backoff
       |
       v
retry attempt
       |
       v
listener success hoặc recover
       |
       v
poll() tiếp theo
~~~

Nếu backoff dài hoặc retry nhiều lần, poll-to-poll interval có thể vượt ngưỡng. Cần tính tổng thời gian:

~~~text
Total attempt budget
  = Σ processing time
  + Σ backoff time
  + error handling / recovery time
~~~

So sánh tổng thời gian với `max.poll.interval.ms` và monitor threshold.

### 20.1. Retry topics có thể tách thời gian chờ

Non-blocking retry topics có thể chuyển record sang topic khác và để main consumer tiếp tục, thay vì giữ consumer thread chờ backoff dài. Nhưng topology có thêm consumers, offsets và recovery stages; cần quan sát từng group/topic.

Không kết luận consumer main group khỏe mạnh chỉ vì lag giảm sau khi chuyển record sang retry topic. Event vẫn có thể đang chờ xử lý ở retry pipeline.

### 20.2. DLT publish cũng có thể block

Nếu recoverer gửi DLT đồng bộ hoặc chờ producer future, DLT broker/network lỗi có thể giữ consumer thread. Cần timeout cho publish/recovery và bảo đảm source offset không được commit khi DLT chưa được lưu an toàn theo policy.

## 21. Consumer thread liveness và Kafka transactions

Trong transactional listener container, consumer thread có thể giữ Kafka transaction mở trong khi listener xử lý. Nếu listener block:

- Transaction duration tăng.
- Producer transaction có thể timeout.
- Consumer không quay lại poll.
- Group progress có thể bị ảnh hưởng.
- Consumer downstream `read_committed` có thể chờ LSO nếu transaction chưa kết thúc.

Khi nhận non-responsive event trong transactional flow, kiểm tra cả:

1. Listener processing duration.
2. Kafka transaction start/commit/abort.
3. Transaction timeout.
4. Database transaction nếu có.
5. Producer fencing.
6. Group poll/heartbeat progress.

Không tăng transaction timeout vô hạn để che listener block. Cũng không kill process ngay khi transaction đang mở mà chưa đánh giá side effects và redelivery.

## 22. Multi-thread và async processing

Nếu listener gửi công việc sang executor:

~~~java
@KafkaListener(topics = "orders.events")
public void consume(OrderEvent event) {
    executor.submit(() -> orderService.process(event));
}
~~~

Consumer thread có thể quay lại poll nhanh, nhưng worker có thể bị block. Khi đó:

- Consumer liveness có thể trông khỏe.
- Kafka lag có thể giảm nếu offset đã commit.
- Internal queue có thể tăng.
- Business completion bị chậm hoặc mất nếu process crash.

Đây là **backlog đã dịch chuyển khỏi Kafka**, không phải đã biến mất.

### 22.1. Đo cả worker liveness

Nếu dùng async processing, cần metric:

- Queue depth.
- Oldest queued task age.
- Active worker count.
- Worker rejection count.
- Task success/failure rate.
- Time from Kafka receive to durable completion.

Không chỉ giám sát consumer thread rồi kết luận pipeline end-to-end khỏe.

### 22.2. Bounded queue và backpressure

Queue không giới hạn có thể làm JVM hết heap khi consumer poll nhanh hơn worker. Dùng bounded queue, pause/backpressure, hoặc thiết kế durable work queue. Khi queue đầy, quyết định ack/commit phải được thực hiện sao cho không mất record.

## 23. Thread liveness và JVM deadlock

Một deadlock trong consumer thread có thể làm poll progress dừng. Thread dump thường chỉ ra:

~~~text
Found one Java-level deadlock:

"orders-consumer-1":
  waiting to lock <0x...> held by "inventory-worker-2"

"inventory-worker-2":
  waiting to lock <0x...> held by "orders-consumer-1"
~~~

Đây là output minh họa. Khi phát hiện:

1. Lưu thread dump và JVM diagnostics.
2. Xác định lock owner và code path.
3. Kiểm tra transaction/database lock có tạo vòng chờ liên quan không.
4. Dùng timeout/lock ordering hoặc giảm phạm vi synchronized.
5. Nếu không thể phục hồi, thay instance theo runbook.

Đừng cố dùng `Thread.stop()` hoặc interrupt tùy tiện để giải phóng thread; có thể để lại object/resource ở trạng thái không nhất quán.

## 24. Rebalance và duplicate delivery sau khi thread bị kẹt

Nếu consumer vượt `max.poll.interval.ms` hoặc mất session, Kafka group có thể rebalance partition. Record chưa commit có thể được consumer khác nhận lại.

Hệ quả:

- Listener có thể đã thực hiện side effect nhưng offset chưa commit.
- Consumer mới nhận lại record.
- Database update hoặc HTTP side effect có thể lặp.
- Transaction cũ có thể abort.

Vì vậy, consumer thread liveness liên quan trực tiếp tới idempotency:

- Dùng event ID ổn định.
- Inbox/processed-events table.
- Unique constraint.
- Side effects trong DB transaction phù hợp.
- Không ack trước khi công việc bền vững.

Restart consumer không đảm bảo không có duplicate; nó có thể làm record chưa commit được giao lại đúng theo at-least-once semantics.

## 25. Runbook: NonResponsiveConsumerEvent xuất hiện

1. Ghi nhận listener ID, instance/pod, partitions và time-since-last-poll.
2. Kiểm tra container có đang running, paused hoặc stopping không.
3. Kiểm tra consumer group state và rebalance logs.
4. Lấy ít nhất hai thread dumps cách nhau vài giây.
5. Xác định consumer thread đang block ở HTTP, database, lock, future hay CPU loop.
6. Kiểm tra `max.poll.interval.ms` và các timeout dependency.
7. Đối chiếu listener duration, batch size, error handler/backoff.
8. Kiểm tra consumer lag và oldest record age.
9. Sửa hoặc phục hồi dependency/root cause.
10. Xác nhận consumer quay lại poll, group assignment ổn định và lag bắt đầu giảm.

Không restart ngay trước khi lưu diagnostics nếu incident cần điều tra và có thể thu thập an toàn.

## 26. Runbook: container running nhưng không xử lý records

1. Xác nhận container ID và `isRunning()`.
2. Kiểm tra `NonResponsiveConsumerEvent` hoặc thời gian từ poll gần nhất.
3. Kiểm tra partition assignment và group membership.
4. Xem topic có records mới hoặc lag đang tồn tại không.
5. Kiểm tra pause state và pause reasons.
6. Kiểm tra thread dump consumer.
7. Kiểm tra listener/error handler có đang retry/block không.
8. Kiểm tra deserialization/conversion failures trước listener.
9. Xác nhận consumer thực sự gọi poll trở lại.

Nếu lag bằng 0 và topic không có data, listener im lặng có thể là bình thường. Cần phân biệt không có việc để làm với không thể làm việc.

## 27. Runbook: consumer bị non-responsive sau một downstream timeout

1. Tìm dependency đang được gọi trong stack trace.
2. Kiểm tra connect/read/call timeout có cấu hình hay không.
3. Kiểm tra retry có nhân tổng thời gian vượt poll budget không.
4. Kiểm tra circuit breaker và connection pool.
5. Xác định có transaction/DB lock đang được giữ trong lúc chờ network không.
6. Khôi phục dependency hoặc bật chế độ degraded phù hợp.
7. Chờ listener kết thúc/timeout theo policy.
8. Nếu thread không thể phục hồi, dùng controlled container/process recovery.
9. Theo dõi redelivery và idempotency sau rebalance.

Không tăng `max.poll.interval.ms` một cách máy móc để che HTTP request không timeout.

## 28. Runbook: liveness alert nhưng consumer group chưa rebalance

1. Xác định Spring monitor threshold và poll timeout.
2. Kiểm tra heartbeat/session timeout.
3. Kiểm tra `max.poll.interval.ms`.
4. Xem consumer thread có đang chạy listener nhưng vẫn giữ heartbeat hay không.
5. Kiểm tra group protocol và static membership.
6. Xác định partitions còn thuộc consumer cũ hay đã reassigned.
7. Kiểm tra lag và side effects của record đang in-flight.
8. Chọn recovery dựa trên thread state, không dựa chỉ vào việc group chưa rebalance.

Group membership chưa thay đổi ngay không có nghĩa consumer thread khỏe.

## 29. Runbook: non-responsive lặp lại sau restart

1. So sánh thread dumps trước/sau restart.
2. Xác định root cause có lặp lại ở cùng dependency/code path không.
3. Kiểm tra pool sizing, CPU limits và connection pool.
4. Kiểm tra batch size, concurrency và retry budget.
5. Xem restart có gây rebalance storm hoặc duplicate side effects không.
6. Thêm circuit breaker/timeout hoặc sửa lock/thread pool.
7. Giới hạn tự restart và alert khi vượt attempts.
8. Chỉ đóng incident khi poll progress và business completion ổn định.

Nếu cùng stack trace xuất hiện sau mỗi lần restart, restart không phải biện pháp sửa lỗi.

## 30. Kiểm thử consumer thread liveness

Integration tests nên xác nhận monitor phát hiện poll progress bị dừng, đồng thời tránh false positive khi listener hoạt động bình thường.

### 30.1. Listener nhanh

1. Khởi động Kafka broker test và listener container.
2. Cấu hình poll timeout/monitor threshold có khoảng dư phù hợp.
3. Gửi records.
4. Xác nhận listener xử lý và poll tiếp.
5. Xác nhận không phát non-responsive event trong điều kiện bình thường.

### 30.2. Listener block có kiểm soát

1. Dùng latch để giữ listener method chưa hoàn tất.
2. Cấu hình threshold đủ ngắn cho test.
3. Chờ monitor phát `NonResponsiveConsumerEvent`.
4. Xác nhận metadata listener/container có thể xác định.
5. Release latch.
6. Xác nhận consumer quay lại poll và xử lý records tiếp theo.

Test phải release latch trong `finally` để tránh treo test suite.

### 30.3. Downstream timeout

1. Mock HTTP/DB dependency phản hồi chậm hoặc timeout.
2. Xác nhận listener không chờ vô hạn.
3. Kiểm tra event/metrics theo ngưỡng.
4. Kiểm tra error handler/retry policy.
5. Xác nhận consumer progress được phục hồi sau khi dependency khỏe.

### 30.4. Batch vượt poll budget

1. Tạo batch có processing duration được kiểm soát.
2. Đo tổng thời gian xử lý batch.
3. So với `max.poll.interval.ms`.
4. Xác nhận rebalance hoặc poll monitor theo behavior dự kiến của version.
5. Điều chỉnh batch/concurrency và lặp lại test.

Không dùng test timeout sát ngưỡng thực tế đến mức phụ thuộc scheduling của CI; cần dung sai đủ lớn.

### 30.5. Thread starvation/deadlock

1. Cấp executor quá nhỏ hoặc cố tình giữ lock trong test.
2. Xác nhận consumer poll progress dừng.
3. Thu thread dump hoặc trạng thái worker.
4. Giải phóng resource.
5. Xác nhận consumer tiếp tục hoặc container được recovery theo policy.

Đây là fault injection chỉ dùng trong môi trường test cô lập.

### 30.6. Test readiness và liveness riêng

1. Làm consumer non-responsive nhưng giữ HTTP server/process hoạt động.
2. Xác nhận readiness phản ánh policy của listener quan trọng.
3. Xác nhận liveness không restart loop chỉ vì Kafka/dependency tạm thời unavailable.
4. Mô phỏng deadlock/unrecoverable state và xác nhận liveness policy có thể xử lý theo thiết kế.
5. Phục hồi và xác nhận trạng thái health trở lại.

## 31. Những sai lầm thường gặp

**Chỉ kiểm tra process còn sống.** JVM có thể chạy nhưng consumer thread không quay lại poll.

**Coi NonResponsiveConsumerEvent là bằng chứng broker down.** Listener có thể block ở database hoặc HTTP.

**Nhầm idle với non-responsive.** Topic trống nhưng poll đều là idle hợp lệ.

**Nhầm container running với consumer progress.** Lifecycle state không chứng minh poll đang diễn ra.

**Chỉ tăng session.timeout.ms.** Nó không sửa listener block và không thay thế max.poll.interval.ms.

**Tăng max.poll.interval.ms vô hạn.** Có thể kéo dài thời gian phát hiện consumer không tiến triển và che batch processing quá lâu.

**Đặt monitor threshold quá thấp.** Listener hợp lệ có thể bị đánh dấu non-responsive.

**Đặt threshold quá cao.** Incident bị phát hiện muộn, lag và record age tăng.

**Gọi KafkaConsumer từ event thread.** KafkaConsumer không thread-safe cho thao tác tùy ý từ thread khác.

**Restart ngay trong event callback.** Có thể gây restart/rebalance loop và mất diagnostics.

**Không timeout dependency hoặc Future.get().** Consumer thread có thể chờ vô hạn.

**Chỉ giám sát consumer thread khi xử lý async.** Worker queue vẫn có thể tích tụ dù poll thread khỏe.

**Tăng concurrency khi database đã cạn connection.** Làm downstream overload nặng hơn.

**Bỏ qua duplicate delivery sau rebalance.** Side effects có thể lặp nếu không idempotent.

**Đưa non-responsive event count thành metric duy nhất.** Cần duration, last poll age, lag và recovery signal.

## 32. Checklist triển khai

### Cấu hình poll/liveness

- [ ] Đã hiểu `pollTimeout`, `monitorInterval` và `noPollThreshold` trên đúng Spring Kafka version.
- [ ] Ngưỡng monitor phù hợp processing p95/p99 và batch size.
- [ ] `max.poll.interval.ms` có đủ ngân sách xử lý nhưng vẫn phát hiện consumer không tiến triển.
- [ ] `session.timeout.ms` và heartbeat settings phù hợp group protocol.
- [ ] Dependency I/O và future waits có timeout.

### Application events và diagnostics

- [ ] Có handler cho `NonResponsiveConsumerEvent`.
- [ ] Handler nhẹ, không thực hiện I/O nặng hoặc restart đệ quy.
- [ ] Log listener ID, instance, time-since-last-poll và partitions khi API hỗ trợ.
- [ ] Có quy trình lấy thread dumps an toàn.
- [ ] Không thao tác trực tiếp KafkaConsumer từ event thread.
- [ ] Event lặp được deduplicate thành incident có thời gian bắt đầu/kết thúc.

### Health và recovery

- [ ] Phân biệt process liveness, container state, consumer progress, group membership và business progress.
- [ ] Readiness policy phản ánh listener critical.
- [ ] Liveness không phụ thuộc trực tiếp vào Kafka broker tạm thời unavailable.
- [ ] Có controlled recovery, cooldown và giới hạn restart.
- [ ] Idempotency bảo vệ side effects khi rebalance/redelivery.
- [ ] Async worker queue cũng có health/backpressure metrics.

### Monitoring và kiểm thử

- [ ] Có last poll age, listener duration, lag và business success rate.
- [ ] Có executor, CPU, GC, DB/HTTP latency metrics.
- [ ] Có alert theo duration và tác động SLO.
- [ ] Test listener block, dependency timeout và thread starvation.
- [ ] Test consumer phục hồi và poll tiếp sau khi release block.
- [ ] Test readiness/liveness không tạo restart loop.
- [ ] Có runbook cho non-responsive, rebalance và duplicate delivery.

## Kết luận

**Liveness của consumer thread** là khả năng consumer tiếp tục tiến triển qua vòng `poll()` và xử lý records trong giới hạn thời gian phù hợp. Spring Kafka có thể phát `NonResponsiveConsumerEvent` khi monitor nhận thấy consumer không poll theo ngưỡng dựa trên `pollTimeout` và `noPollThreshold`. Event này giúp phát hiện listener bị block, dependency timeout, lock contention hoặc thread starvation; nó không tự khẳng định broker hỏng, thread đã chết hay process cần restart ngay.

Để vận hành đúng, hãy phân biệt process liveness, container lifecycle, poll progress, Kafka group heartbeat và business completion. Dùng thread dumps cùng listener/dependency metrics để tìm nguyên nhân, thiết kế timeout và retry trong ngân sách `max.poll.interval.ms`, và xây readiness/liveness policy tránh restart loop khi dependency tạm thời lỗi. Khi consumer bị phục hồi hoặc rebalance, vẫn phải bảo vệ side effects bằng idempotency vì record chưa commit có thể được giao lại. **Một consumer khỏe không chỉ là một thread còn tồn tại; đó là một luồng xử lý có thể tiếp tục poll, hoàn tất công việc và tiến offset an toàn.**
