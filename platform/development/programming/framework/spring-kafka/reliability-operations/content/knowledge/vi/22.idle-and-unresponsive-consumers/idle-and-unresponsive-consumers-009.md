# NonResponsiveConsumerEvent

Trong một ứng dụng Spring Kafka, consumer có thể không nhận thêm record vì **topic đang không có dữ liệu mới** hoặc vì **consumer thread không còn thực hiện vòng `poll()` đúng tiến độ**. Hai hiện tượng có biểu hiện bề ngoài giống nhau — listener im lặng, số record xử lý không tăng — nhưng cách điều tra và khôi phục khác hẳn.

`NonResponsiveConsumerEvent` là application event của Spring Kafka dùng để cảnh báo trường hợp thứ hai: listener container phát hiện thời gian kể từ hoạt động `poll()` quá dài so với ngưỡng giám sát. Event giúp nhận biết consumer có nguy cơ mắc kẹt trong thao tác Kafka client, listener business code, transaction, callback hoặc do JVM không được cấp CPU đủ để tiến triển.

Trong chương **Idle và non-responsive** của Spring Kafka Reliability Operations, điều quan trọng không phải chỉ biết cách nhận event mà còn phải phân biệt nó với **idle event** khi consumer vẫn poll bình thường, hiểu ngưỡng phát hiện, biết thu thập bằng chứng và tránh những phản ứng tự động khiến consumer group rebalance liên tục hoặc xử lý trùng dữ liệu.

## 1. Consumer idle khác consumer non-responsive như thế nào?

Một Spring Kafka listener container quản lý Kafka consumer theo chu kỳ:

```text
           +--------------------+
           | consumer.poll(...) |
           +----------+---------+
                      |
               +------+------+
               |             |
           Không record    Có record
               |             |
               |             v
               |       @KafkaListener
               |        xử lý record
               |             |
               +------+------+
                      |
                      v
                Poll tiếp tục
```

Nếu topic chưa có record mới, `poll()` có thể trả tập record rỗng rồi container tiếp tục poll. Đây là **idle về dữ liệu**, thường hoàn toàn bình thường. Trong tình huống non-responsive, container không thấy consumer tiến triển hoạt động poll trong thời gian được xem là bất thường.

| Trạng thái | Consumer có tiếp tục poll? | Listener nhận record? | Đánh giá ban đầu |
|---|---|---|---|
| Topic không có record mới | Thường có. | Không. | Có thể là idle bình thường. |
| Partition bị pause có chủ đích | Container thường vẫn poll để giữ group. | Không nhận record mới từ partition đã pause. | Là trạng thái điều khiển consumption. |
| Listener xử lý một record rất lâu | Có thể chưa quay lại poll tiếp theo. | Đang bận xử lý record đã nhận. | Có thể thành non-responsive nếu vượt ngưỡng. |
| Consumer kẹt trong Kafka client hoặc callback | Không có tiến triển poll như kỳ vọng. | Có thể không nhận record mới. | Cần điều tra non-responsive. |
| Container đã stop | Không còn consumer loop đang chạy. | Không. | Là lifecycle stopped, không đơn thuần là idle. |

**Không có message** không đồng nghĩa **consumer bị kẹt**. Ngược lại, một thread đang xử lý record dở có thể khiến metric throughput tạm không tăng dù Kafka vẫn khỏe.

## 2. Phân biệt các Spring Kafka application event

Các event quan trọng trong nhóm idle và non-responsive:

| Event | Điều kiện phản ánh | Hướng sử dụng |
|---|---|---|
| `ListenerContainerIdleEvent` | Container không nhận/giao record mới trong khoảng `idleEventInterval` được cấu hình. | Giám sát topic yên lặng, kích hoạt thao tác phù hợp với idle. |
| `ListenerContainerNoLongerIdleEvent` | Container nhận dữ liệu trở lại sau trạng thái idle. | Xác nhận luồng dữ liệu đã hoạt động lại. |
| `NonResponsiveConsumerEvent` | Monitor nhận thấy khoảng cách hoạt động poll vượt ngưỡng. | Cảnh báo nguy cơ consumer bị block hoặc không tiến triển. |
| `ConsumerPausedEvent` / `ConsumerResumedEvent` | Consumer/container đã pause hoặc resume. | Theo dõi điều khiển backpressure. |
| `ConsumerStoppedEvent` | Consumer/container dừng với lý do theo API tương ứng. | Chẩn đoán lifecycle/recovery. |

Ví dụ một topic chỉ có event đặt hàng mỗi vài phút:

```text
12:00:00 — poll() trả record và listener xử lý
12:00:05 — poll() trả rỗng
12:00:10 — poll() trả rỗng
12:00:15 — poll() trả rỗng
...
12:01:00 — idle interval đạt ngưỡng
             -> có thể phát ListenerContainerIdleEvent
```

Đây không phải `NonResponsiveConsumerEvent`, vì consumer vẫn poll đều đặn.

Ngược lại:

```text
12:00:00 — poll() trả record
12:00:01 — listener gọi HTTP dependency
12:00:35 — lời gọi HTTP vẫn block, consumer chưa poll tiếp
             -> monitor có thể phát NonResponsiveConsumerEvent
```

**Cùng là listener im lặng, nhưng nguyên nhân và mức độ rủi ro khác nhau.**

## 3. NonResponsiveConsumerEvent cho biết điều gì?

Event thuộc package:

```java
import org.springframework.kafka.event.NonResponsiveConsumerEvent;
```

Spring Kafka listener container có bộ giám sát chuyên kiểm tra khoảng thời gian consumer không thực hiện poll theo tiến độ kỳ vọng. Khi khoảng thời gian vượt `pollTimeout × noPollThreshold` trong một lần kiểm tra, container có thể publish `NonResponsiveConsumerEvent` qua Spring application event infrastructure.

Thông tin event có thể dùng cho:

- Xác định listener/container ID đang có vấn đề.
- Ghi thời gian kể từ poll theo thông tin container theo dõi.
- Xác định tập topic-partition liên quan theo metadata có sẵn.
- Gắn sự kiện với pod, thread, consumer group và mốc thời gian incident.
- Tăng counter, gửi alert có deduplication hoặc lưu bằng chứng điều tra.

Event **không tự chứng minh**:

- Kafka broker đã mất kết nối hoặc cluster unavailable.
- Consumer chắc chắn đã bị group coordinator loại khỏi group.
- Record đang xử lý đã thất bại hoặc đã được chuyển DLT.
- Committed offset đã mất, bị reset hay đã tiến.
- Có deadlock Java, vì cũng có thể do long-running listener.

Event cũng không tự gọi `stop()`, `restart()`, `seek()`, `commitSync()` hay `wakeup()` để khôi phục. **Phát hiện** và **hành động phục hồi** là hai lớp cần tách biệt.

## 4. Ba tham số quan trọng: pollTimeout, noPollThreshold, monitorInterval

`ContainerProperties` cho phép cấu hình ngưỡng non-responsive:

| Cấu hình | Ý nghĩa | Đơn vị |
|---|---|---|
| `pollTimeout` | Thời gian consumer có thể chờ trong mỗi lời gọi `poll()` bình thường. | Millisecond |
| `noPollThreshold` | Hệ số nhân với `pollTimeout` để tạo ngưỡng non-responsive. | Không có đơn vị |
| `monitorInterval` | Khoảng thời gian giữa các lượt kiểm tra của monitor. | Giây |

Để hiểu trực quan:

```text
Ngưỡng non-responsive gần đúng:

T_threshold = pollTimeout × noPollThreshold

Ví dụ:
pollTimeout     = 5.000 ms
noPollThreshold = 3,0

T_threshold = 15.000 ms = 15 giây
```

Ở các phiên bản Spring Kafka thường gặp, các giá trị mặc định là `pollTimeout=5.000 ms`, `noPollThreshold=3.0` và `monitorInterval=30 giây`. Đây là các mặc định để tham khảo; khi vận hành phải xem **giá trị container thực tế**, vì Boot/custom factory có thể ghi đè và các phiên bản framework có thể thay đổi mặc định.

`monitorInterval` không phải ngưỡng phát hiện; nó là chu kỳ **quét**. Nếu ngưỡng là 15 giây nhưng monitor chỉ quét mỗi 30 giây, event có thể được phát sau khi ngưỡng đã vượt một khoảng đáng kể.

Ví dụ:

| `pollTimeout` | `noPollThreshold` | Ngưỡng tính toán | `monitorInterval` |
|---:|---:|---:|---:|
| 5.000 ms | 3,0 | 15 giây | 30 giây |
| 5.000 ms | 6,0 | 30 giây | 10 giây |
| 2.000 ms | 4,0 | 8 giây | 5 giây |
| 10.000 ms | 3,0 | 30 giây | 15 giây |

Các số trên chỉ minh họa phép tính, không phải bộ cấu hình tối ưu chung. Ngưỡng quá thấp tạo false-positive với listener có thời gian xử lý hợp lệ dài; ngưỡng quá cao khiến phát hiện consumer bị kẹt chậm.

## 5. Cấu hình listener container có monitor

Ví dụ sử dụng `ConcurrentKafkaListenerContainerFactory`:

```java
@Configuration
public class KafkaListenerMonitorConfig {

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, String>
            monitoredListenerFactory(
                    ConsumerFactory<String, String> consumerFactory) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, String>();

        factory.setConsumerFactory(consumerFactory);
        factory.getContainerProperties().setPollTimeout(5_000L);
        factory.getContainerProperties().setNoPollThreshold(4.0f);
        factory.getContainerProperties().setMonitorInterval(10);

        return factory;
    }
}
```

Các import:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
```

Đoạn cấu hình đặt ngưỡng non-responsive xấp xỉ 20 giây, với monitor quét mỗi 10 giây. Listener sử dụng factory:

```java
@Component
public class OrderEventListener {

    @KafkaListener(
        id = "orders-consumer",
        topics = "orders",
        groupId = "orders-service",
        containerFactory = "monitoredListenerFactory"
    )
    public void consume(ConsumerRecord<String, String> record) {
        orderService.process(record.key(), record.value());
    }
}
```

Trong ứng dụng có nhiều listener factory, việc cấu hình `monitoredListenerFactory` không tự thay đổi các listener vẫn dùng default factory. Hãy xác nhận `containerFactory` tại từng endpoint hoặc cấu hình chung mà ứng dụng thực sự dùng.

Ngoài ra, `pollTimeout` là tham số trên **container**, trong khi `max.poll.interval.ms` là cấu hình trên **Kafka consumer client**. Hai giá trị không thay thế lẫn nhau.

## 6. Nhận event bằng @EventListener

Sử dụng Spring event listener để log và đo số lần cảnh báo:

```java
@Component
public class ConsumerResponsivenessMonitor {

    private static final Logger log =
            LoggerFactory.getLogger(ConsumerResponsivenessMonitor.class);

    private final MeterRegistry metrics;

    public ConsumerResponsivenessMonitor(MeterRegistry metrics) {
        this.metrics = metrics;
    }

    @EventListener
    public void onNonResponsive(NonResponsiveConsumerEvent event) {
        log.warn(
            "Kafka consumer non-responsive: listenerId={}, " +
            "elapsedMs={}, partitions={}",
            event.getListenerId(),
            event.getTimeSinceLastPoll(),
            event.getTopicPartitions());

        metrics.counter(
                "app.kafka.nonresponsive.events",
                "listener", event.getListenerId())
                .increment();
    }
}
```

Import minh họa:

```java
import io.micrometer.core.instrument.MeterRegistry;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.event.EventListener;
import org.springframework.kafka.event.NonResponsiveConsumerEvent;
import org.springframework.stereotype.Component;
```

`getTimeSinceLastPoll()` thể hiện thời gian theo millisecond được event báo từ trạng thái poll mà container theo dõi. `getTopicPartitions()` là context topic-partition liên quan. `getListenerId()` xác định listener/container; nên gắn thêm pod/instance và consumer group trong log ở hệ thống nhiều replica.

`app.kafka.nonresponsive.events` là tên metric **tự định nghĩa**, không phải tên metric mặc định của Spring Kafka. Để tránh cardinality cao, không đưa event ID, offset hoặc toàn bộ topic-partition động vào nhãn Prometheus tùy tiện.

**Lưu ý:** nếu không cấu hình bean `MeterRegistry`, ví dụ trên cần bỏ phần metric hoặc bổ sung Micrometer phù hợp. Chỉ nên thực hiện công việc nhanh trong callback event; không gọi HTTP/database chậm hoặc block thread phát event.

## 7. Theo dõi idle và non-responsive cạnh nhau

Để tránh nhầm “không có record mới” với “consumer bị kẹt”, có thể quan sát cả `ListenerContainerIdleEvent`:

```java
@Configuration
class KafkaIdleConfiguration {

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, String>
            idleAwareListenerFactory(
                    ConsumerFactory<String, String> consumerFactory) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, String>();
        factory.setConsumerFactory(consumerFactory);

        // Phát idle event khi không nhận message trong 60 giây.
        factory.getContainerProperties().setIdleEventInterval(60_000L);

        // Vẫn theo dõi non-responsive qua poll monitor.
        factory.getContainerProperties().setPollTimeout(5_000L);
        factory.getContainerProperties().setNoPollThreshold(4.0f);
        factory.getContainerProperties().setMonitorInterval(10);

        return factory;
    }
}
```

Ví dụ listener event:

```java
@Component
public class IdleAndStuckConsumerEvents {

    private static final Logger log =
            LoggerFactory.getLogger(IdleAndStuckConsumerEvents.class);

    @EventListener
    public void onIdle(ListenerContainerIdleEvent event) {
        log.info("Kafka listener idle: {}", event.getListenerId());
    }

    @EventListener
    public void onNonResponsive(NonResponsiveConsumerEvent event) {
        log.error(
                "Kafka consumer may be stuck: listenerId={}, elapsedMs={}",
                event.getListenerId(),
                event.getTimeSinceLastPoll());
    }
}
```

Ở đây `ListenerContainerIdleEvent` và `NonResponsiveConsumerEvent` đo **hai hiện tượng khác nhau**. Nếu listener không nhận message nhưng poll vẫn đều, idle event có thể hợp lệ mà không có non-responsive event. Nếu listener block trong xử lý, monitor có thể báo non-responsive dù topic vẫn liên tục có dữ liệu mới.

Đừng dùng idle event làm trigger restart pod theo mặc định: với topic ít traffic, một consumer khỏe mạnh có thể idle hàng giờ.

## 8. Phân biệt noPollThreshold với max.poll.interval.ms

`max.poll.interval.ms` là quy tắc của Kafka consumer group: nếu khoảng cách giữa các lần `poll()` vượt giới hạn, consumer có thể bị xem là không tiến triển và mất quyền tham gia group theo hành vi client/coordinator. `NonResponsiveConsumerEvent` lại dựa vào ngưỡng monitor của Spring Kafka.

Ví dụ cấu hình:

```yaml
spring:
  kafka:
    consumer:
      group-id: orders-service
      properties:
        "[max.poll.interval.ms]": 300000
        "[max.poll.records]": 300
```

Giả sử container có:

```text
pollTimeout             = 5 giây
noPollThreshold         = 4,0
monitorInterval         = 10 giây
max.poll.interval.ms    = 300 giây

Ngưỡng monitor ≈ 20 giây
Giới hạn poll interval Kafka = 300 giây
```

Ở mốc 25–30 giây, `NonResponsiveConsumerEvent` có thể đã được phát, nhưng group chưa nhất thiết rebalance. Event là **cảnh báo sớm**, không phải xác nhận Kafka đã vượt `max.poll.interval.ms`.

Ngược lại, nếu mã listener mất nhiều phút để xử lý record, consumer có thể bị group thu hồi assignment sau khi vượt ngưỡng Kafka; khi đó việc phát hiện từ monitor sớm giúp đội vận hành điều tra trước khi rủi ro tăng.

Không tăng `max.poll.interval.ms` lên quá lớn chỉ để tránh rebalance khi code business bị treo. Cần đánh giá `max.poll.records`, thời gian xử lý batch, timeout bên ngoài và chính sách retry để giữ vòng poll trong giới hạn hợp lý.

## 9. Các nguyên nhân phổ biến của non-responsive

### 9.1. Listener gọi dependency quá lâu

Ví dụ:

```java
@KafkaListener(topics = "orders")
public void processOrder(String payload) {
    // Nếu HTTP client thiếu timeout, consumer thread có thể bị giữ lâu.
    inventoryClient.reserve(payload);
}
```

Nếu `inventoryClient.reserve` chờ vô thời hạn, container không quay lại poll. Monitor có thể báo non-responsive mặc dù Kafka broker và partition assignment hoàn toàn bình thường.

**Hướng xử lý:** đặt connect/read/response timeout, circuit breaker, bulkhead và retry có giới hạn; tránh chặn consumer thread khi không cần thiết.

### 9.2. Database lock hoặc connection pool cạn

Consumer thread đang chờ lấy connection hoặc chờ lock trong transaction:

```text
Kafka consumer thread
  -> OrderService.save(...)
     -> HikariCP getConnection()
        hoặc PostgreSQL lock wait
           (block rất lâu)
```

Kiểm tra active/idle/pending connection, query latency, deadlock, lock contention và transaction timeout.

### 9.3. Blocking Kafka client, commit hoặc transaction

Consumer có thể đang chờ network, coordinator, `commitSync()`, callback hoặc Kafka transactional producer. Thread dump và Kafka client logs giúp phân biệt lỗi này với listener xử lý lâu.

### 9.4. GC pause, CPU starvation hoặc deadlock

Nếu JVM stop-the-world GC kéo dài hoặc container bị CPU throttling, nhiều thread không tiến triển cùng lúc. Khi đó sự cố không riêng Kafka; restart listener container có thể không giải quyết căn nguyên.

### 9.5. Backoff hoặc tác vụ người dùng chặn thread

Một vòng `Thread.sleep(...)` dài, chờ `Future.get()` không timeout hoặc dùng retry đồng bộ với tổng thời gian quá lớn có thể giữ consumer không poll. Nên dùng chính sách backoff có giới hạn, quan sát tổng thời gian và cân nhắc retry topic nếu yêu cầu thứ tự/transaction cho phép.

## 10. Có thể dùng event để tự động wakeup consumer không?

`NonResponsiveConsumerEvent` cung cấp context về consumer. Kafka `Consumer.wakeup()` được thiết kế để gọi từ thread khác nhằm đánh thức consumer khỏi các thao tác blocking hỗ trợ wakeup. Tuy nhiên, **không gọi wakeup ngay trên mọi event**:

- `wakeup()` có thể dẫn đến `WakeupException` trên consumer thread.
- Nếu thread đang block trong HTTP/database hoặc deadlock ngoài Kafka, wakeup không chắc giúp gì.
- Container có lifecycle và error handling của riêng nó; can thiệp cần hiểu cách container xử lý `WakeupException`.
- Gọi lặp trên nhiều event có thể làm container bất ổn, tăng rebalance và phát thêm lỗi.

Ví dụ minh họa ý tưởng, **mặc định chỉ log, không tự wakeup**:

```java
@EventListener
public void onNonResponsive(NonResponsiveConsumerEvent event) {
    log.error("Consumer seems stuck: {}", event.getListenerId());

    // Chỉ khi một runbook/cơ chế kiểm soát đã cho phép:
    // if (recoveryPolicy.shouldWakeup(event)) {
    //     event.getConsumer().wakeup();
    // }
}
```

Kafka `Consumer` không an toàn để sử dụng tùy ý từ thread khác; `wakeup()` là ngoại lệ được thiết kế cho tình huống đặc biệt. **Không dùng `event.getConsumer().poll()`, `commitSync()` hoặc `seek()` từ callback giám sát**.

Ưu tiên thu thập thread dump, consumer group state và metric trước khi thay đổi lifecycle. Nếu thật sự phải stop/restart, điều phối qua API container và executor phù hợp, với cooldown và giới hạn số lần.

## 11. Tại sao restart ngay khi nhận event thường nguy hiểm?

Một cách xử lý tưởng tiện lợi nhưng không an toàn:

```java
@EventListener
public void onNonResponsive(NonResponsiveConsumerEvent event) {
    container.stop();
    container.start();
}
```

Đoạn code trên **không nên áp dụng** trong production. Monitor có thể phát nhiều event liên tiếp khi cùng một consumer vẫn kẹt. Mỗi event đều stop/start container có thể dẫn đến:

- Rebalance storm trong consumer group.
- Record được giao lại vì transaction hoặc offset trước đó chưa commit.
- Side effect ngoài Kafka bị thực hiện trùng.
- Pod tiêu tốn tài nguyên tạo consumer mới nhưng không giải quyết lỗi DB/HTTP.
- Mất thread dump và dấu vết gốc trước khi đội vận hành lấy được.

Một chính sách khôi phục tự động cần có **deduplication, cooldown, rate limit, incident state** và điều kiện để xác nhận đã khôi phục. Khi không thể xác định nguyên nhân hoặc lỗi tái diễn, nên escalade cho operator thay vì loop restart vô hạn.

## 12. Thread dump là bằng chứng quan trọng

Khi event xuất hiện, hãy xác định consumer thread đang làm gì. Nếu có quyền truy cập JVM, `jcmd` có thể giúp lấy thread dump:

```bash
# PID ở đây là Java process ID trong pod/VM đang điều tra.
jcmd 1 Thread.print > /tmp/consumer-thread-dump.txt
```

Ví dụ này giả định Java process có PID 1; trong hệ thống thực tế phải xác định PID đúng và công cụ `jcmd` có sẵn. Nếu không có JDK tools trong runtime container, dùng cách thu thập thread dump theo quy trình vận hành được phê duyệt.

Các stack cần phân biệt:

```text
Case A — blocked in application HTTP:
KafkaMessageListenerContainer...
  -> OrderService.process
     -> HttpClient.execute
        -> socket read

Case B — blocked in database:
KafkaMessageListenerContainer...
  -> OrderRepository.save
     -> JDBC execute
        -> database lock/connection wait

Case C — Kafka client/coordinator:
KafkaMessageListenerContainer...
  -> KafkaConsumer.poll / commit
     -> NetworkClient / coordinator...

Case D — JVM-wide stall:
Nhiều thread cùng không tiến triển,
CPU throttling / long GC / deadlock
```

Thread dump là snapshot, không phải kết luận tuyệt đối; so sánh nhiều mẫu cách nhau một khoảng khi có thể, cùng với dependency timeout, heap/GC metrics và Kafka logs để tránh chẩn đoán nhầm.

## 13. Ghép event với consumer lag và assignment

Một consumer non-responsive có thể khiến committed offset đứng yên trong lúc producer tiếp tục ghi. Ví dụ:

```text
Topic: orders; partition: 2

T0:
  committed offset = 1.200
  log-end offset   = 1.300
  lag              = 100

T1 (sau 5 phút):
  committed offset = 1.200
  log-end offset   = 2.100
  lag              = 900
```

Nếu cùng thời gian nhận `NonResponsiveConsumerEvent` từ listener sở hữu partition 2, cần điều tra gấp. Tuy nhiên lag tăng cũng có thể xảy ra nếu throughput thấp hơn producer rate, record lỗi đang retry hoặc partition đang pause chủ đích.

Xem consumer group bằng Kafka CLI:

```bash
kafka-consumer-groups.sh \
  --bootstrap-server kafka:9092 \
  --describe \
  --group orders-service

kafka-consumer-groups.sh \
  --bootstrap-server kafka:9092 \
  --describe \
  --group orders-service \
  --members --verbose
```

CLI giúp kiểm tra member, assignment, offset và lag. Nó **không biết Spring Kafka vừa phát `NonResponsiveConsumerEvent`**; thông tin này phải đến từ ứng dụng. Hãy ghép log event với pod, consumer group, partition ownership, listener/container ID và mốc thời gian.

## 14. Non-responsive trong lúc pause chủ đích

Spring Kafka `pause()` và `pausePartition(...)` yêu cầu container ngừng nhận thêm record từ phạm vi được pause, nhưng consumer vẫn thường poll để duy trì group membership. Vì vậy:

- Không nhận message từ partition đang pause là **hành vi đúng**.
- Không có `ListenerContainerIdleEvent` hoặc có event idle tùy cấu hình không tự chứng minh consumer bị kẹt.
- `NonResponsiveConsumerEvent` khi container đang pause vẫn cần điều tra xem consumer thread có thật sự không tiến triển poll, hay một tác vụ khác đang block.
- Pause không tự dừng transaction đang xử lý hoặc hủy các record đã fetch trước khi pause.

Nếu team dùng pause để chống quá tải dependency, hãy ghi **intentional pause state** vào monitoring để tránh alert nhầm về throughput/lag. Đồng thời đừng tắt hẳn cảnh báo non-responsive chỉ vì container được pause: consumer vẫn cần duy trì poll/lifecycle phù hợp.

## 15. Multi-instance và container ID

Một `@KafkaListener` có thể chạy với `concurrency > 1`, tạo nhiều child container/consumer thread. Trong Kubernetes, nhiều pod của cùng service có thể sử dụng cùng listener ID ở cấp ứng dụng.

Ví dụ:

```text
orders-service
  Pod A
    orders-consumer-0 -> orders-0, orders-3
    orders-consumer-1 -> orders-1

  Pod B
    orders-consumer-0 -> orders-2, orders-5
    orders-consumer-1 -> orders-4
```

Assignment chỉ để minh họa; Kafka assignor quyết định mapping thực tế. Nếu alert chỉ có `listenerId=orders-consumer-0` mà không có pod/instance, operator có thể không biết consumer nào thực sự kẹt.

Structured log nên có:

```text
event=kafka_consumer_nonresponsive
service=orders-service
instance=orders-service-pod-a
listener_id=orders-consumer-0
consumer_group=orders-service
elapsed_ms=48000
assigned_partitions=orders-0,orders-3
action=ALERT_ONLY
```

Đây là format ví dụ do ứng dụng tạo, không phải format mặc định của Spring Kafka.

Khi partition chuyển sang pod mới do rebalance, sự kiện cũ chỉ phản ánh trạng thái của owner tại thời điểm phát. Nếu cần tự động khôi phục, điều phối phải kiểm tra **owner hiện tại** thay vì gửi lệnh stop/pause đến pod đã mất assignment.

## 16. Monitoring và alert có chống trùng

Một `NonResponsiveConsumerEvent` có thể được phát lặp lại ở nhiều chu kỳ `monitorInterval` nếu trạng thái không tiến triển vẫn tồn tại. Không nên tạo một ticket hoặc gửi thông báo khẩn mới cho mỗi event.

Các tín hiệu nên kết hợp:

| Tín hiệu | Ý nghĩa |
|---|---|
| Số `NonResponsiveConsumerEvent` theo listener/instance | Phát hiện symptom bị kẹt hoặc xử lý kéo dài. |
| Thời gian kể từ poll theo event | Đánh giá mức độ kéo dài, so với ngưỡng monitor. |
| Listener invocation duration | Phân biệt công việc thực tế dài với poll Kafka bị block. |
| Consumer committed offset và lag | Xác định tiến độ xử lý có bị dừng không. |
| Consumer group rebalance rate | Phát hiện tác động mất membership hoặc restart storm. |
| Dependency p95/p99 latency, timeout rate | Chẩn đoán HTTP/DB giữ consumer thread. |
| JVM GC pause, CPU throttling, thread pool | Tìm sự cố tài nguyên hoặc thread starvation. |
| Retry/DLT ingress và transaction abort | Biết record lỗi có được đưa sang luồng phục hồi không. |

Nên có cooldown cho alert lặp, và tiêu chí đóng incident khi poll/processing phục hồi **và** committed offset hoặc business throughput tiến trở lại. Chỉ vì không nhận event mới không có nghĩa consumer đã khỏe; container có thể đã stop hoặc pod đã bị restart.

Với hệ thống có nhiều consumer, thêm tầng tổng hợp để không phát một cảnh báo critical riêng cho từng partition nếu nguyên nhân là cùng một database outage.

## 17. Runbook điều tra sự cố

Khi nhận `NonResponsiveConsumerEvent` ở production:

**Bước 1 — Ghi context.** Thu thập timestamp, service/pod, listener/container ID, group ID, `getTimeSinceLastPoll()` và topic-partition liên quan.

**Bước 2 — Kiểm tra cấu hình.** Đọc `pollTimeout`, `noPollThreshold`, `monitorInterval`, `max.poll.interval.ms` và `max.poll.records` thực tế. Có thay đổi sau deployment không?

**Bước 3 — Kiểm tra lifecycle.** Container đang running, paused hay stopped? Có rebalance? Partition còn assigned cho member vừa phát event không?

**Bước 4 — Lấy thread dump.** Xác định consumer thread bị block trong `poll()`, listener nghiệp vụ, JDBC, HTTP, transaction hoặc callback.

**Bước 5 — Đối chiếu dependency và JVM.** Xem broker/coordinator, network, TLS/auth, database lock, HTTP timeout, GC, CPU throttling và thread pool.

**Bước 6 — Kiểm tra tiến độ Kafka.** Committed offset có đứng yên không? Lag tăng thế nào? Có retry/DLT hoặc aborted transaction trong cùng giai đoạn?

**Bước 7 — Chọn hành động đúng nguyên nhân.** Sửa dependency hoặc timeout; cân nhắc pause có kiểm soát; chỉ wakeup/restart khi cơ chế hỗ trợ và runbook cho phép.

**Bước 8 — Xác nhận khôi phục.** Consumer quay lại poll, group assignment ổn định, committed offset tiến, lag giảm và business side effects không bị lặp.

**Bước 9 — Ghi postmortem.** Lưu thread dump/metric và bổ sung timeout, backpressure, idempotency hoặc cảnh báo phù hợp cho lần sau.

Không reset consumer offset chỉ để làm lag giảm nếu chưa xác định record nào đã được xử lý và record nào cần replay.

## 18. Runbook khi sự kiện xuất hiện ngay sau deployment

Sau khi deploy code mới, event xuất hiện đồng thời với việc consumer group rebalance:

1. Kiểm tra listener concurrency và các thay đổi `max.poll.records`; một batch lớn hơn có thể khiến một vòng xử lý kéo dài.
2. Kiểm tra HTTP client, JDBC pool và `@Transactional` vừa thay đổi có gây lock hoặc blocking wait.
3. So sánh thời gian xử lý từng record trước/sau deployment.
4. Kiểm tra CPU/memory limits, pod restart, GC và thread dump ở instance lỗi.
5. Kiểm tra consumer assignment và timeout group; một rebalance không đồng nghĩa Kafka broker lỗi.
6. Nếu cần rollback, chuẩn bị idempotency cho record đã xử lý nhưng chưa commit.
7. Xác nhận sau rollback/fix rằng event không còn kéo dài, offset tiếp tục tiến và DLT không tăng bất thường.

Nếu chỉ tăng `noPollThreshold` để che alert, sự cố processing stall vẫn có thể tồn tại và cuối cùng dẫn đến `max.poll.interval.ms` violation. Chỉ điều chỉnh monitor khi có bằng chứng workload hợp lệ cần ngưỡng cao hơn.

## 19. Kiểm thử NonResponsiveConsumerEvent

Có thể kiểm thử bằng Kafka Testcontainers hoặc embedded broker và listener container thật:

1. Tạo topic, consumer group và listener test riêng.
2. Cấu hình `pollTimeout`, `noPollThreshold` và `monitorInterval` nhỏ đủ để test chạy nhanh, nhưng không quá sát ngưỡng gây flaky test.
3. Đăng ký `@EventListener` để thu thập `NonResponsiveConsumerEvent`.
4. Gửi một record khiến listener chờ trên `CountDownLatch` trong thời gian lâu hơn ngưỡng monitor.
5. Dùng await condition có timeout để đợi event, thay vì kỳ vọng event phát đúng thời điểm tính toán.
6. Xác nhận event chứa context listener và elapsed time có ý nghĩa.
7. Giải phóng latch; kiểm tra listener hoàn tất, consumer poll trở lại và committed offset tiến theo ack mode.
8. Tạo kịch bản topic không có record để kiểm tra idle behavior riêng, tránh nhầm với non-responsive.
9. Nếu cần, mô phỏng restart hoặc rebalance để xem recovery có tạo duplicate hay không.

Không cố ý block consumer production để xác nhận event. Khi kiểm thử, cần cleanup latch/executor nếu test fail để không giữ test JVM vô thời hạn.

## 20. Lỗi hiểu nhầm phổ biến

| Triệu chứng | Hiểu nhầm | Cách tiếp cận đúng |
|---|---|---|
| Listener không có log record mới | Consumer bị kẹt. | Kiểm tra topic có data không, poll/idle event, group assignment và pause state. |
| `ListenerContainerIdleEvent` xuất hiện | Broker không phản hồi. | Đây thường là không có record; consumer có thể vẫn poll bình thường. |
| `NonResponsiveConsumerEvent` xuất hiện | Broker chắc chắn down. | Kiểm tra consumer thread, HTTP/DB, transaction, JVM và Kafka network. |
| Event phát trước `max.poll.interval.ms` | Kafka đã loại consumer khỏi group. | Spring monitor có ngưỡng khác; phải kiểm tra group membership. |
| Nhiều event lặp lại | Nhiều incident mới. | Có thể cùng consumer bị kẹt qua nhiều lần monitor; deduplicate/cooldown. |
| Gọi `wakeup()` không có tác dụng | Kafka client không hỗ trợ wakeup. | Có thể thread bị block ngoài Kafka, cần sửa dependency/deadlock. |
| Sau restart lag giảm nhưng DLT tăng | Đã phục hồi hoàn toàn. | Cần điều tra record được chuyển DLT và business outcome. |
| Pod Ready nhưng non-responsive | Health check không thể sai. | HTTP readiness có thể khỏe dù Kafka consumer thread bị block. |
| Consumer đang pause không nhận record | Consumer non-responsive. | Intentional pause khác poll stall; xem requested/applied state. |

## 21. Checklist vận hành

- [ ] Phân biệt rõ **idle về dữ liệu** và **consumer không tiến triển poll**.
- [ ] Cấu hình `pollTimeout`, `noPollThreshold` và `monitorInterval` với đúng đơn vị.
- [ ] Biết `max.poll.interval.ms` của Kafka client và thời gian xử lý p99 thực tế.
- [ ] Nhận `NonResponsiveConsumerEvent` qua `@EventListener`, ghi listener ID và instance/pod.
- [ ] Ghép event với committed offset, lag, assignment, pause state và retry/DLT.
- [ ] Có timeout/circuit breaker cho dependency có thể block consumer thread.
- [ ] Có khả năng thu thập thread dump và JVM metrics khi sự cố xảy ra.
- [ ] Không gọi `KafkaConsumer` từ thread ngoài ngoại trừ API được cho phép như `wakeup()` khi có quy trình rõ ràng.
- [ ] Không stop/start pod hoặc container cho mỗi event mà thiếu cooldown và idempotency.
- [ ] Không reset offset để bỏ qua backlog khi chưa có quyết định nghiệp vụ.
- [ ] Có tiêu chí đóng incident dựa trên consumer poll, offset và business progress.
- [ ] Kiểm thử kịch bản idle lành mạnh và non-responsive thật trong môi trường cô lập.

## 22. Kết luận

`NonResponsiveConsumerEvent` là một tín hiệu quan sát quan trọng để phát hiện consumer Spring Kafka có dấu hiệu **không quay lại hoạt động `poll()` đúng tiến độ**. Nó khác về bản chất với `ListenerContainerIdleEvent`: một bên cảnh báo sự trì trệ của consumer, bên kia phản ánh việc không có record được nhận trong một khoảng thời gian.

Khi vận hành, cần xem event như **điểm khởi đầu của điều tra**, không phải kết luận broker đã hỏng hay chỉ thị restart tức thì. Kết hợp cấu hình monitor hợp lý, thread dump, dependency metrics, consumer lag và group assignment giúp tìm đúng nguyên nhân; các quy trình khôi phục có giới hạn, idempotency và xác nhận business progress giúp sự cố được giải quyết mà không tạo thêm duplicate hoặc rebalance storm.
