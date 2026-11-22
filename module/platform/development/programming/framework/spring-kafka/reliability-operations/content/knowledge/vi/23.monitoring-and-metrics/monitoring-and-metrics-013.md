# Consumer idle time

Trong hệ thống Spring Kafka, **consumer idle time** có thể mô tả khoảng thời gian listener không nhận record mới, tỷ lệ thời gian consumer chờ trong `poll()`, hoặc khoảng thời gian đã trôi qua kể từ lần gọi `poll()` gần nhất. Ba cách hiểu này khác nhau về nguyên nhân và hậu quả vận hành. Một consumer ít nhận record có thể hoàn toàn khỏe mạnh; một consumer liên tục có record nhưng bị chặn khi gọi database có thể đang đứng trước nguy cơ `max.poll.interval.ms` và rebalance.

Chủ đề **Consumer idle time** thuộc nhóm Monitoring và metrics vì mục tiêu là đo đúng trạng thái, quan sát nguyên nhân, rồi quyết định khi nào cần cảnh báo hoặc can thiệp. Spring Kafka hỗ trợ `idleEventInterval` và các application events như `ListenerContainerIdleEvent`, `ListenerContainerNoLongerIdleEvent`. Kafka consumer client đồng thời có những metrics liên quan đến poll và thời gian rảnh. Không nên gom tất cả vào một chỉ số tên “idle” rồi suy ra hệ thống tốt hoặc xấu.

Một thiết kế vận hành tin cậy cần trả lời: consumer có còn poll không; partition có được gán cho consumer không; Kafka có record mới không; record có đang bị pause hoặc chặn bởi transaction không; và listener có xử lý thành công record được nhận hay không.

## 1. Ba cách hiểu khác nhau về consumer idle time

| Khái niệm | Điều được đo | Ý nghĩa thực tế |
|---|---|---|
| **Listener idle duration** | Thời gian từ lần gần nhất container nhận/giao record cho listener | Phát hiện consumer không có record được quan sát trong một khoảng |
| **Poll idle ratio** | Tỷ lệ thời gian consumer chờ trong `poll()` so với thời gian dành cho xử lý bên ngoài `poll()` | Đánh giá consumer đang chờ dữ liệu nhiều hay bận xử lý |
| **Time since last poll** | Khoảng thời gian từ lần `KafkaConsumer.poll()` gần nhất | Phát hiện consumer thread bị chặn, có nguy cơ vi phạm poll interval |

Ví dụ một topic chỉ có một sự kiện mỗi giờ. Consumer liên tục gọi `poll()` và trả về không có record mới. `ListenerContainerIdleEvent` có thể xuất hiện sau ngưỡng, còn `poll-idle-ratio-avg` có thể cao. Hai tín hiệu này **không chứng minh** consumer bị lỗi. Trái lại, một listener đang xử lý một record trong mười phút có thể không phát idle event đúng thời điểm vì consumer thread không quay lại vòng poll, trong khi chỉ số thời gian từ lần poll cuối tăng nguy hiểm.

Vì vậy, dashboard nên có các nhóm tín hiệu riêng: **availability của consumer**, **traffic/idle của listener**, **latency xử lý**, **consumer lag** và **sức khỏe downstream**.

## 2. Idle ở mức listener container xảy ra khi nào?

Một vòng xử lý Kafka listener thường có dạng:

```text
Kafka broker
      |
      v
KafkaConsumer.poll()
      |
      +---- có records ----> @KafkaListener
      |                         |
      |                         v
      |                    xử lý / ack / commit
      |
      +---- chưa có record ---> tiếp tục poll
      |
      v
Container theo dõi khoảng thời gian không nhận record
      |
      +---- vượt idleEventInterval
                    |
                    v
           ListenerContainerIdleEvent
```

`idleEventInterval` là ngưỡng mà Spring Kafka listener container sử dụng để thông báo không nhận record trong khoảng thời gian đủ dài. Nó **không khiến broker gửi thêm dữ liệu**, không tạo retry và không tự dừng listener. Khi dữ liệu lại xuất hiện sau giai đoạn idle, container có thể phát `ListenerContainerNoLongerIdleEvent` để cho biết trạng thái idle đã kết thúc.

Trong một lần `poll()` không có record, consumer không có nghĩa đã dừng; nó vẫn có thể giữ group membership và tiếp tục polling. Mốc idle event là tín hiệu của application layer, không phải một Kafka protocol error.

## 3. Cấu hình `idleEventInterval` trong Spring Kafka

Để nhận idle events ở một listener factory, có thể cấu hình trực tiếp `ContainerProperties`:

```java
@Configuration
public class OrdersKafkaConfiguration {

    @Bean("ordersKafkaListenerContainerFactory")
    ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
    ordersKafkaListenerContainerFactory(
            ConsumerFactory<String, OrderEvent> consumerFactory) {

        ConcurrentKafkaListenerContainerFactory<String, OrderEvent> factory =
                new ConcurrentKafkaListenerContainerFactory<>();

        factory.setConsumerFactory(consumerFactory);
        factory.setConcurrency(3);

        ContainerProperties properties = factory.getContainerProperties();
        properties.setIdleEventInterval(60_000L);
        properties.setPollTimeout(1_000L);
        properties.setAckMode(ContainerProperties.AckMode.RECORD);

        return factory;
    }
}
```

`OrderEvent` chỉ là kiểu dữ liệu minh họa; ứng dụng phải cung cấp deserializer, `ConsumerFactory` và cấu hình Kafka kết nối thực tế. Giá trị `60_000L` nghĩa là ngưỡng idle **60 giây**, còn `pollTimeout=1_000L` là giới hạn chờ của một lần `poll()` khoảng một giây. Hai thuộc tính **không tương đương**.

Listener được gắn vào factory này:

```java
@Component
public class OrdersListener {

    private final OrderService orderService;

    public OrdersListener(OrderService orderService) {
        this.orderService = orderService;
    }

    @KafkaListener(
            id = "ordersListener",
            topics = "orders",
            groupId = "orders-service",
            containerFactory = "ordersKafkaListenerContainerFactory")
    public void handle(OrderEvent event) {
        orderService.processIdempotently(event);
    }
}
```

Đặt `idleEventInterval` trên một factory có nghĩa các container do factory đó tạo ra sử dụng cùng chính sách idle. Nếu một factory được dùng cho nhiều listener có nhịp dữ liệu khác nhau, cần cân nhắc tách factory hoặc chọn ngưỡng đủ phù hợp. Không giả định property đã áp dụng cho listener chỉ vì nó có trong một bean khác không được annotation tham chiếu.

## 4. Bắt `ListenerContainerIdleEvent`

Spring Kafka phát idle event qua Spring application event mechanism; một bean có thể lắng nghe với `@EventListener`:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.event.EventListener;
import org.springframework.kafka.event.ListenerContainerIdleEvent;
import org.springframework.stereotype.Component;

@Component
public class KafkaIdleEventLogger {

    private static final Logger log = LoggerFactory.getLogger(
            KafkaIdleEventLogger.class);

    @EventListener
    public void onIdle(ListenerContainerIdleEvent event) {
        log.info(
                "Kafka listener idle: listener={}, idleMs={}",
                event.getListenerId(),
                event.getIdleTime());
    }
}
```

`getIdleTime()` biểu diễn thời gian idle mà event ghi nhận, theo đơn vị mili giây; `getListenerId()` cho biết định danh listener/container do framework cung cấp. Trong `ConcurrentMessageListenerContainer`, có nhiều consumer child containers, vì vậy định danh do event cung cấp có thể chi tiết hơn ID trong `@KafkaListener` và cần được quan sát trên bản đang chạy.

Không nên coi việc nhận một idle event là sự cố tự động. Nếu topic dự kiến không có event cuối tuần, đây có thể là một telemetry event bình thường. Tương tự, khi listener đang bị pause có chủ đích, một idle event không đủ để kết luận producer đã dừng gửi record.

## 5. Khi dữ liệu trở lại: `ListenerContainerNoLongerIdleEvent`

Nếu cần biết **idle kết thúc lúc nào**, theo dõi thêm event khi listener nhận dữ liệu trở lại:

```java
import org.springframework.context.event.EventListener;
import org.springframework.kafka.event.ListenerContainerNoLongerIdleEvent;
import org.springframework.stereotype.Component;

@Component
public class KafkaActivityObserver {

    private final ListenerStatusRecorder recorder;

    public KafkaActivityObserver(ListenerStatusRecorder recorder) {
        this.recorder = recorder;
    }

    @EventListener
    public void onActive(ListenerContainerNoLongerIdleEvent event) {
        recorder.markActive(event.getListenerId());
    }
}
```

`ListenerStatusRecorder` là một interface/bean do ứng dụng định nghĩa để lưu trạng thái monitoring. Event *no longer idle* không chứng minh listener đã thực hiện side effect nghiệp vụ thành công: một record vừa được giao cho listener có thể ném exception, bị retry hoặc đi vào DLT. Để kết luận xử lý thành công cần metric/ack/transaction outcome riêng.

Với hệ thống quan sát, cặp idle và no-longer-idle events có thể tạo trạng thái `ACTIVE -> IDLE -> ACTIVE`. Không nhất thiết mở một incident cho mỗi idle event lặp lại, vì Spring Kafka có thể phát idle event định kỳ trong khi không có record.

## 6. Timeline: một consumer thực sự không có traffic

Giả sử `idleEventInterval=60_000`, Kafka topic chỉ có record vào thời điểm đầu và sau ba phút:

```text
t=0s       listener nhận record #1
            |
t=30s      consumer tiếp tục poll, chưa có record mới
            |
t≈60s      ListenerContainerIdleEvent
            |
t≈120s     có thể phát idle event tiếp theo
            |
t≈180s     listener nhận record #2
            |
            +--> ListenerContainerNoLongerIdleEvent
            |
            v
          listener quay về trạng thái active
```

Các mốc có ký hiệu `≈` là giá trị minh họa. Event có thể xuất hiện muộn hơn ngưỡng do vòng poll, thời gian xử lý, scheduling hoặc cách container tính idle. Không thiết kế deadline nghiệp vụ chính xác tới mili giây chỉ dựa trên thời điểm một Spring application event được phát.

Nếu ứng dụng đang khởi động và chưa từng nhận record nào, container vẫn có thể được coi idle sau khoảng thời gian cấu hình, tùy lifecycle và các thuộc tính hỗ trợ của phiên bản. Vì vậy, trạng thái **never received**, **idle after last record** và **stopped/unassigned** nên được tách rõ trong monitoring.

## 7. Idle của toàn container khác idle theo partition

Một consumer có thể được gán nhiều partition. Nếu một partition liên tục có record, container có thể không được coi idle dù partition khác im lặng:

```text
Topic orders:

orders-0 --> 20 records/s --> Consumer A
orders-1 -->  0 records/s --> Consumer A
orders-2 -->  2 records/s --> Consumer A

Consumer A vẫn nhận record, nên không nhất thiết idle toàn container.
```

Spring Kafka còn hỗ trợ `idlePartitionEventInterval` để phát event ở phạm vi **từng partition** khi cần quan sát độ im lặng của một partition cụ thể. Trong các phiên bản hỗ trợ, sự kiện tương ứng là `ListenerContainerPartitionIdleEvent` và `ListenerContainerPartitionNoLongerIdleEvent`.

```java
ContainerProperties properties = factory.getContainerProperties();

properties.setIdleEventInterval(120_000L);          // container
properties.setIdlePartitionEventInterval(60_000L); // partition
```

Hai loại event trả lời hai câu hỏi khác nhau. Nếu mục tiêu là “service có đang nhận bất kỳ record nào không?”, theo dõi listener container idle. Nếu mục tiêu là “partition `orders-1` có đang không nhận record trong khi những partition khác vẫn hoạt động?”, cần partition idle event hoặc metric theo partition.

Khi nhiều replicas thuộc cùng group, chỉ instance đang được gán partition mới có thể theo dõi partition đó ở tầng listener container. Để có góc nhìn toàn group, tổng hợp theo `group + topic + partition` cùng với assignment/rebalance state và owner hiện tại.

## 8. Kafka consumer metric `poll-idle-ratio-avg`

Kafka client có metric thường được gọi **`poll-idle-ratio-avg`** trong nhóm metrics của consumer. Nó biểu diễn tỷ lệ thời gian consumer ở trạng thái chờ trong `poll()` so với thời gian làm việc ở phía ứng dụng giữa các lần poll, theo định nghĩa của Kafka client version đang dùng.

Giải thích thực tế:

| Giá trị gần đúng | Diễn giải thường gặp | Điều cần kiểm tra thêm |
|---:|---|---|
| Gần `1.0` | Consumer dành phần lớn thời gian chờ trong poll | Có record mới không? Topic ít traffic hay consumer bị pause? |
| Quanh `0.5` | Thời gian chờ poll và thời gian xử lý ngoài poll tương đối cân bằng | Batch size, throughput và listener latency |
| Gần `0.0` | Consumer rất bận ngoài poll, hoặc bị giữ trong xử lý | Slow listener, downstream latency, time between polls |

Đây là một **ratio**, không phải số mili giây idle. `0.9` không có nghĩa consumer đã không nhận record trong 900 ms hoặc 90 giây. Một consumer bận xử lý nhiều record có thể có poll-idle ratio thấp và thực sự có throughput cao; điều đó chưa chắc là lỗi. Ngược lại, ratio thấp đi cùng `time-between-poll-max` lớn có thể là dấu hiệu consumer thread bị chặn.

Tên metric trong JMX, Micrometer Kafka client binder và Prometheus exporter có thể khác nhau theo version. Trước khi viết dashboard, hãy đọc meter/series thực tế; không mặc định tên exporter là một chuỗi cố định ở mọi cluster.

## 9. `time-between-poll` và `last-poll-seconds-ago`

Kafka consumer client còn có metrics phản ánh nhịp gọi `poll()` như `time-between-poll-avg`, `time-between-poll-max` hoặc `last-poll-seconds-ago` ở những phiên bản hỗ trợ. Những metric này quan trọng khi consumer **không phản hồi**, chứ không chỉ khi không có data.

Ví dụ:

```text
Consumer A:
  poll-idle-ratio-avg      0.95
  time-between-poll-max  1.2 s
  lag                    0

Diễn giải:
  consumer thường xuyên poll và chờ record, không có backlog rõ rệt.

Consumer B:
  poll-idle-ratio-avg      0.01
  time-between-poll-max  280 s
  max.poll.interval.ms   300000
  lag                    tăng

Diễn giải:
  nguy cơ vượt poll interval do listener/downstream xử lý quá lâu.
```

Các con số trên chỉ minh họa. Cần biết cách metric được đo trên cửa sổ thời gian và có được làm mới khi không poll hay không. Trong một số điều kiện, metrics đo theo mẫu có thể không phản ánh ngay trạng thái của một thread đã kẹt hẳn. Vì vậy, nên kết hợp application logs, thread dumps và cơ chế monitor non-responsive của Spring Kafka.

## 10. Phân biệt idle và `NonResponsiveConsumerEvent`

Đây là điểm rất quan trọng trong nhóm **Monitoring và metrics**:

```text
Tình huống A — Không có traffic:
  poll() chạy đều đặn
  không nhận record
  có thể phát ListenerContainerIdleEvent
  group membership vẫn ổn định

Tình huống B — Listener bị treo:
  poll() lần trước nhận record
  listener gọi HTTP/SQL quá lâu
  consumer thread không quay lại poll()
  có thể phát NonResponsiveConsumerEvent từ container monitor
  nguy cơ max.poll.interval.ms và rebalance
```

Spring Kafka có cơ chế theo dõi consumer không phản hồi qua các thuộc tính như `monitorInterval`, `noPollThreshold` và `pollTimeout` trên container tùy phiên bản. Một event non-responsive là cảnh báo về **khả năng tiến triển của consumer thread/poll**, trong khi idle event chỉ báo **không nhận record**.

Một listener bận xử lý record nhiều phút có thể chưa đến được code phát idle event theo chu kỳ; sự vắng mặt của idle event **không chứng minh** consumer thread khỏe mạnh. Để điều tra, đối chiếu `max.poll.interval.ms`, thời gian listener, heartbeat, rebalance, consumer metrics và các sự kiện non-responsive.

## 11. `max.poll.interval.ms` không phải idle interval

Ba tham số dễ bị nhầm:

| Cấu hình | Đơn vị/ngữ cảnh | Chức năng |
|---|---|---|
| `ContainerProperties.idleEventInterval` | ms, Spring Kafka | Khi nào phát listener idle event |
| `ContainerProperties.pollTimeout` | ms, Spring Kafka/Kafka poll | Một lời gọi `poll()` chờ tối đa bao lâu trong vòng poll thông thường |
| `ConsumerConfig.MAX_POLL_INTERVAL_MS_CONFIG` | ms, Kafka consumer | Giới hạn thời gian giữa các lời gọi `poll()` trước khi Kafka coi consumer thiếu tiến triển |

Ví dụ `idleEventInterval=30_000` không có nghĩa Kafka sẽ rebalance consumer sau 30 giây không có record. Nếu container vẫn poll, group membership có thể tiếp tục bình thường nhiều giờ dù topic trống.

Ngược lại, `max.poll.interval.ms=300000` không phải ngưỡng chờ 5 phút để phát idle event. Nó là ràng buộc liveness/progress của consumer. Nếu listener gọi downstream chậm hơn giới hạn này, có thể dẫn đến mất assignment, `CommitFailedException` hoặc redelivery sau rebalance.

Một hệ thống khỏe mạnh có thể phát hàng nghìn idle events mà không có một rebalance nào; hoặc rebalance liên tục do listener chậm mà hầu như không phát idle events theo kỳ vọng.

## 12. Vì sao consumer idle không đồng nghĩa consumer lag bằng không?

**Consumer lag** là khoảng cách giữa committed offset của group và vị trí cuối phù hợp của Kafka log. **Idle time** là khoảng thời gian container không nhận record. Hai chỉ số có thể khác nhau đáng kể:

| Tình huống | Idle | Lag | Ý nghĩa có thể |
|---|---|---|---|
| Topic hết record và group đã xử lý xong | Cao | Gần 0 | Thường bình thường |
| Producer ghi nhiều nhưng consumer bị pause | Cao | Tăng | Có intentional backpressure hoặc lỗi resume |
| Listener xử lý record rất chậm | Có thể không phát đúng hạn | Tăng | Nút thắt ở listener/downstream |
| Producer chỉ ghi vào một partition | Một số partition idle | Lag phân bố lệch | Key skew hoặc partitioning không đều |
| Transaction đang mở giữ LSO | Có thể tăng | Tùy cách dashboard tính lag | Record chưa được `read_committed` consumer nhìn thấy |
| Consumer không có assignment | Không nên coi là idle bình thường của partition đó | Cần xem group | Member chưa được gán partition hoặc đang rebalance |

Đặc biệt với `isolation.level=read_committed`, Last Stable Offset (LSO) có thể chưa tiến do một transaction đang mở. Broker có record phía sau nhưng consumer chưa được phép đọc. Một idle event trong trường hợp đó không nói rằng producer không gửi; cần xem transaction visibility và các giới hạn của log.

Nếu downstream outage khiến container pause, lag tăng là một kết quả được dự đoán. Có thể cần cảnh báo về thời gian pause và tuổi record lớn nhất, nhưng không nên tự reset offset để “xóa lag”; reset tiến có thể mất dữ liệu, reset lùi có thể tạo duplicate.

## 13. Idle khi container hoặc partition bị pause

Trong Spring Kafka, `pause()`/`resume()` tạm điều chỉnh việc nhận record mà không nhất thiết làm consumer rời group. Nếu một listener container bị pause vì API downstream quá tải, consumer vẫn có thể tiếp tục poll theo lifecycle để duy trì membership.

```text
Downstream trả 429/503 liên tục
          |
          v
Controller yêu cầu container.pause()
          |
          v
Container không nhận thêm record mới
          |
          v
Idle time tăng / có thể xuất hiện idle event
          |
          v
Đây có thể là trạng thái vận hành chủ động
```

Nếu có idle event trong lúc pause, đừng kết luận producer dừng hoặc broker mất dữ liệu. Nên giữ trạng thái `PAUSED`, nguyên nhân pause và thời điểm pause trong dashboard. Một số event phiên bản Spring Kafka cung cấp thông tin liên quan đến pause, nhưng cách tin cậy là kết hợp với API/metric của listener container đang quản lý.

Không tự động gọi `resume()` chỉ vì nhận idle event: pause có thể được kích hoạt vì circuit breaker hoặc quota và chỉ được gỡ khi downstream khỏe lại. Nhiều cơ chế pause khác nhau cần một bộ điều phối ownership rõ để tránh một observer vô tình giải phóng pause của error handler.

## 14. Metric custom: thời gian từ record gần nhất

Nếu đội vận hành cần một **gauge liên tục** thể hiện giây từ record gần nhất thay vì chỉ các idle events rời rạc, có thể ghi dấu hoạt động tại listener và đăng ký gauge Micrometer của ứng dụng.

Ví dụ dưới đây dùng `System.nanoTime()` để đo khoảng thời gian đã trôi qua tương đối ổn định trước thay đổi wall clock. Khi chưa nhận record nào, gauge trả `NaN` để không giả định consumer đã nhận record:

```java
import java.util.concurrent.atomic.AtomicLong;
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Component;

@Component
public class OrderListenerActivity {

    private final AtomicLong lastRecordNanos = new AtomicLong(-1L);

    public OrderListenerActivity(MeterRegistry registry) {
        Gauge.builder("app.kafka.listener.since_last_record.seconds", this,
                        OrderListenerActivity::secondsSinceLastRecord)
                .description("Seconds since a record entered the orders listener")
                .tag("pipeline", "orders")
                .register(registry);
    }

    public void recordReceived() {
        lastRecordNanos.set(System.nanoTime());
    }

    public double secondsSinceLastRecord() {
        long previous = lastRecordNanos.get();
        if (previous < 0L) {
            return Double.NaN;
        }

        long elapsed = System.nanoTime() - previous;
        return Math.max(0L, elapsed) / 1_000_000_000.0;
    }
}
```

Gắn tracker tại đầu listener:

```java
@Component
public class OrdersTrackedListener {

    private final OrderListenerActivity activity;
    private final OrderService orderService;

    public OrdersTrackedListener(
            OrderListenerActivity activity,
            OrderService orderService) {
        this.activity = activity;
        this.orderService = orderService;
    }

    @KafkaListener(
            id = "ordersTrackedListener",
            topics = "orders",
            groupId = "orders-service")
    public void onOrder(OrderEvent event) {
        activity.recordReceived();
        orderService.processIdempotently(event);
    }
}
```

**Giới hạn của ví dụ:** gauge đo thời gian kể từ record **đã vào method listener**, không phải thời gian kể từ record trên broker được commit, không đo cho từng partition, và không phân biệt consumer stopped/unassigned. Nếu deserialization thất bại trước khi listener được gọi, gauge không được reset dù Kafka consumer đã fetch record. Nếu listener chưa bao giờ nhận record, `NaN` cần được dashboard xử lý rõ thay vì mặc định về 0.

Với nhiều child consumers dùng chung một bean, gauge trên là **độ rảnh chung của listener logic**, không phải từng child. Nếu muốn theo dõi từng child hoặc partition, cần thiết kế state per assignment và cleanup sau rebalance, cùng kiểm soát cardinality.

## 15. Idle duration, processing latency và business success là ba metric riêng

Một record có thể được listener nhận ở thời điểm `t0`, xử lý database mất 40 giây và cuối cùng thất bại. Nếu gauge đo từ lúc listener bắt đầu, nó reset tại `t0`. Nếu timer đo thời gian xử lý, nó ghi khoảng 40 giây. Nếu business success counter chỉ tăng khi giao dịch hoàn tất, counter không tăng.

```text
t0:    @KafkaListener được gọi
       |   -> since_last_record được reset
       |
t0+40s: listener ném exception
       |   -> processing timer phản ánh 40 giây
       |   -> business_success không tăng
       v
Error handler retry hoặc gửi DLT
```

Không lấy thời gian từ record cuối làm “độ trễ xử lý” hoặc “thời gian chờ nghiệp vụ”. Một consumer nhận record đều có idle duration thấp nhưng có thể luôn thất bại, đẩy mọi record vào DLT. Ngược lại, một consumer idle lâu có thể đã hoàn tất tất cả công việc và không có lỗi nào.

Một dashboard nên thể hiện ít nhất **records received**, **listener processing duration**, **processing outcome**, **consumer lag**, và **idle/no-longer-idle state**. Với DLT/retry, bổ sung retry attempts, DLT publish success/failure và backlog của các topic liên quan.

## 16. Tiếp cận metrics từ Kafka consumer client

`KafkaConsumer` có API `metrics()` cho client metrics, song Kafka consumer object **không thread-safe** và thuộc quyền quản lý của listener container. Không nên lấy reference từ event rồi lưu vào một singleton để một scheduler gọi `metrics()` và các method consumer tùy ý trong thread khác.

Thay vào đó có thể dùng Micrometer Kafka client metrics binder, JMX exporter hoặc các cơ chế instrumentation do Spring Boot/Kafka client version cung cấp. Khi sử dụng binder, xác định chính xác metric group/name trong runtime trước khi viết query.

Ví dụ những nhóm metric cần quan tâm:

```text
Consumer poll/progress:
  poll-idle-ratio-avg
  time-between-poll-avg / time-between-poll-max
  last-poll-seconds-ago

Consumer fetch / lag:
  records-consumed-rate
  records-lag-max
  fetch-rate / fetch-latency

Consumer group lifecycle:
  rebalance count/rate
  assigned partitions
  commit rate/failure logs
```

Không phải mọi metric có mặt trong mọi client version và binder. Nếu không tìm thấy tên metric mong muốn, kiểm tra Kafka client metrics được đăng ký ở broker/client runtime nào và exporter có lọc/đổi tên metric hay không. Không cố suy ra tình trạng poll chỉ từ một Spring listener timer `spring.kafka.listener`: timer đó chủ yếu đo xử lý listener, không đo toàn bộ khoảng chờ không có record.

## 17. Ngưỡng cảnh báo phải phụ thuộc expected traffic

Một idle interval hợp lý cho topic giao dịch realtime có thể là một cảnh báo vô nghĩa đối với topic chỉ xuất bản dữ liệu mỗi đêm.

| Luồng | Traffic kỳ vọng | Cách dùng idle time |
|---|---|---|
| Payment events realtime | Có record đều trong giờ xử lý | Alert sau ngưỡng SLO và xác nhận producer/consumer health |
| Batch events hàng giờ | Rỗng phần lớn thời gian | Chỉ alert sau lịch batch cộng biên độ trễ |
| Audit/topic ít traffic | Không có tần suất tối thiểu | Theo dõi telemetry, không tự mở incident vì idle |
| Retry topic | Chỉ có record khi có retry | Idle thường là trạng thái tốt |
| DLT | Nên hiếm khi có record | Nên alert khi **DLT tăng**, không phải khi idle |
| Heartbeat topic có hợp đồng gửi đều | Producer gửi nhịp định kỳ | Idle time có thể hỗ trợ kiểm chứng hợp đồng |

Nếu doanh nghiệp không cam kết traffic tối thiểu, không thể suy ra outage từ “10 phút không có record”. Có thể alert dựa trên producer heartbeat hợp lệ, số event đến thấp bất thường so với baseline, hoặc consumer lag tăng kết hợp fetch rate thấp.

Với topic theo giờ làm việc, đưa lịch hoạt động, ngày nghỉ và timezone vào alert evaluation. Một cảnh báo xuất hiện lúc 3 giờ sáng khi hệ thống bình thường không phát record chỉ gây alert fatigue.

## 18. Kết hợp Micrometer/Prometheus và thiết kế dashboard

Đối với metric custom gauge ở ví dụ, exporter Prometheus có thể hiển thị tên metric được chuẩn hóa từ `app.kafka.listener.since_last_record.seconds`, ví dụ dạng `app_kafka_listener_since_last_record_seconds` tùy Micrometer/exporter version. Để tránh query sai, luôn kiểm tra tên và tags thật được xuất.

Một biểu thức PromQL minh họa khi đã xác nhận tên gauge:

```promql
# Theo dõi thời gian từ record cuối của pipeline orders
app_kafka_listener_since_last_record_seconds{pipeline="orders"}
```

Nếu nhiều replica cùng chạy, mỗi instance có gauge riêng và cần xác định câu hỏi muốn trả lời: **instance nào không có record** hay **toàn pipeline không có record**. Không lấy `max` trên mọi replica rồi báo toàn hệ thống idle khi một instance không được gán partition hoặc vừa khởi động lại.

Không tạo tag `event_id`, `order_id`, `offset` hoặc Kafka key vào gauge hoặc listener timer. Những trường này có cardinality rất lớn; lưu chúng trong structured logs hoặc tracing. Tags phù hợp hơn gồm `service`, `pipeline`, `listener`, `group` và, khi thật sự cần, `topic`/`partition` có giới hạn số lượng rõ ràng.

Một dashboard nên đặt cạnh nhau:

```text
Order Kafka pipeline

  Consumer group lag       0 / tăng / giảm
  Records consumed rate   0 / n records/s
  Listener idle time      giây từ record cuối
  Poll idle ratio         tỷ lệ chờ trong poll
  Time since last poll    dấu hiệu thread bị chặn
  Listener p95/p99        thời gian xử lý
  Rebalance / pause       trạng thái lifecycle
  DLT / retry             tình trạng recovery
```

Nhờ đặt cạnh nhau, đội vận hành có thể phân biệt **rảnh do hết việc**, **rảnh do pause**, **chậm do xử lý**, và **không nhận dữ liệu dù broker có record**.

## 19. Alert lifecycle: không báo thiếu traffic khi consumer chưa có assignment

Một container có thể chưa start, đang shutdown, bị pause hoặc đang rebalance. Trong những trạng thái đó, timer ghi thời gian từ record cuối hoặc trạng thái idle cần được đọc với bối cảnh phù hợp.

Ví dụ một lược đồ trạng thái giám sát:

```text
STARTING
   |
   v
ASSIGNED + ACTIVE
   |
   +---- không nhận record quá ngưỡng ----> ASSIGNED + IDLE
   |                                           |
   |                                      có record mới
   |                                           |
   <-------------------------------------------+
   |
   +---- pause có chủ đích ----------------> PAUSED
   |
   +---- partition revoked ----------------> REBALANCING / UNASSIGNED
   |
   +---- stop -----------------------------> STOPPED
```

Không nên giữ vô hạn trạng thái idle của một partition trên instance A sau khi partition đã được gán sang instance B. Nếu lưu trạng thái theo partition, dùng callback revoke/assigned hoặc event lifecycle để xóa state cũ và xác định owner hiện tại. Với group nhiều replicas, một dashboard tập trung phải gom theo assignment hiện tại thay vì chỉ đếm mọi idle event mà từng replica đã phát.

`ListenerContainerIdleEvent` không phải event consumer **liveness** cuối cùng. Nếu JVM bị kill hoặc process chết, Spring application event có thể không được phát; readiness/liveness, instance heartbeat và consumer group monitoring phải được thiết kế độc lập.

## 20. Những lỗi vận hành thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng điều tra |
|---|---|---|
| Idle event xuất hiện dù topic khỏe | Topic có traffic thưa hoặc container chỉ được gán partition ít traffic | Kiểm tra expected traffic, assignment và producer rate |
| Không thấy idle event sau ngưỡng | Listener dùng factory khác, chưa bật `idleEventInterval`, consumer đang chặn hoặc event listener không được đăng ký | Kiểm tra bean wiring, poll lifecycle và event multicaster |
| Idle event xuất hiện lặp lại khiến nhiều incident | Trạng thái idle vẫn tiếp diễn và events được phát định kỳ | Dùng state machine/dedup alert theo listener hoặc partition |
| Consumer lag tăng nhưng có idle event | Consumer bị pause, thiếu assignment, fetch bị chặn hoặc transaction LSO | So sánh pause, group, lag, broker/producer và isolation |
| Consumer không nhận record nhưng `poll-idle-ratio-avg` cao | Consumer đang chờ trong poll vì ít data | Đánh giá xem có thực sự kỳ vọng dữ liệu mới không |
| Consumer rebalance vì poll timeout | Listener xử lý lâu, `time-between-poll-max` sát giới hạn | Kiểm tra downstream timeout, batch size và `max.poll.interval.ms` |
| Gauges không giảm sau khi listener stop | Gauge custom không theo lifecycle/assignment | Xóa hoặc đánh dấu inactive khi container dừng, không coi metric cũ là live |
| Có `NoLongerIdleEvent` nhưng nghiệp vụ vẫn lỗi | Record được giao lại nhưng listener thất bại | Theo dõi error handler, retry/DLT và business success |
| Chỉ một partition im lặng nhưng container không idle | Partition khác vẫn có data | Dùng `idlePartitionEventInterval` hoặc partition metrics |
| Prometheus không có metric dù listener chạy | Registry/exporter chưa được gắn, sai tên metric hoặc custom gauge chưa đăng ký | Kiểm tra `MeterRegistry`, scrape, labels và series thật |

Khi xử lý sự cố, câu hỏi đầu tiên là “**có kỳ vọng record mới phải xuất hiện vào lúc này không?**”. Nếu câu trả lời là không, idle có thể hoàn toàn bình thường. Nếu có, mới tiếp tục so sánh producer, broker, assignment, pause, consumer polling và listener errors.

## 21. Kiểm thử tích hợp cần có

Có thể dùng Kafka test broker hoặc Testcontainers cùng một listener có `idleEventInterval` ngắn trong môi trường kiểm thử. Dùng latch/queue để ghi nhận events thay vì chỉ ngủ một khoảng cố định và kiểm tra log.

```java
@Component
public class IdleEventTestProbe {

    private final BlockingQueue<String> idle = new LinkedBlockingQueue<>();
    private final BlockingQueue<String> active = new LinkedBlockingQueue<>();

    @EventListener
    public void onIdle(ListenerContainerIdleEvent event) {
        idle.offer(event.getListenerId());
    }

    @EventListener
    public void onActive(ListenerContainerNoLongerIdleEvent event) {
        active.offer(event.getListenerId());
    }

    public String awaitIdle(Duration timeout) throws InterruptedException {
        return idle.poll(timeout.toMillis(), TimeUnit.MILLISECONDS);
    }

    public String awaitActive(Duration timeout) throws InterruptedException {
        return active.poll(timeout.toMillis(), TimeUnit.MILLISECONDS);
    }
}
```

Test nên bảo đảm container đã được gán partition trước khi tính thời gian idle, và nếu có nhiều child containers thì lọc đúng listener/container ID cần quan sát. Sau mỗi test case, xóa state/queue cũ để không nhầm event còn sót.

Những kịch bản đáng có:

1. **Không có record:** listener container đang poll bình thường, phát idle event sau ngưỡng.
2. **Có record trở lại:** listener nhận record sau giai đoạn idle và phát no-longer-idle event.
3. **Có record liên tục:** không phát idle sai khi khoảng cách record nhỏ hơn ngưỡng.
4. **Hai partition khác nhịp:** container có thể active trong khi một partition idle; dùng partition idle event để phân biệt.
5. **Pause/resume:** không quy mọi idle event khi pause thành producer outage.
6. **Listener blocking:** cơ chế non-responsive/poll interval phát hiện đúng tình huống khác idle bình thường.
7. **Rebalance:** state giám sát được cập nhật khi assignment đổi và owner cũ không tiếp tục báo sai.
8. **Deserialization/retry failure:** idle gauge tại method listener có thể không thấy record lỗi trước listener; DLT/retry metrics vẫn phản ánh sự cố.
9. **Custom gauge:** giá trị ban đầu chưa có record được biểu diễn rõ, sau record mới reset đúng và tiếp tục tăng theo thời gian.
10. **Multi-instance:** dashboard aggregation không báo cả pipeline idle chỉ vì một replica không được gán partition.

Các test cần xác minh **event đã được phát**, **listener nhận record**, **group/partition assignment** và **offset/processing outcome** phù hợp. Chỉ nhìn thấy một event idle không đủ để chứng minh consumer group đang hoạt động đúng end-to-end.

## 22. Runbook khi consumer idle bất thường

Khi alert cho thấy consumer idle lâu hơn dự kiến, quy trình điều tra có thể là:

1. **Kiểm tra hợp đồng traffic:** producer được kỳ vọng gửi bao nhiêu record, theo khung giờ nào, có lịch batch/ngày nghỉ không?
2. **Xác định scope:** listener ID, consumer group, topic, partition, instance và assignment hiện tại.
3. **Phân biệt trạng thái:** container đang running, idle, paused, unassigned, rebalance hay stopped?
4. **Xem dữ liệu ở broker:** topic có record mới không, end offset/LSO thay đổi không và producer có lỗi publish không?
5. **Xem poll responsiveness:** consumer còn gọi poll thường xuyên không, có `NonResponsiveConsumerEvent`, warning `max.poll.interval.ms` hoặc heartbeat issue không?
6. **Xem lag:** group có backlog nhưng không fetch hay thực sự đã bắt kịp log?
7. **Xem listener/downstream:** HTTP/DB chậm, retry, DLT hoặc deserialization khiến record không vào listener method không?
8. **Khắc phục đúng điểm:** sửa producer, resume container theo chính sách, khôi phục downstream hoặc sửa lỗi consumer; không reset offset theo phản xạ.
9. **Đối soát phục hồi:** quan sát no-longer-idle, throughput, committed offset, consumer lag và business success.
10. **Cải thiện cảnh báo:** bổ sung trạng thái pause/assignment và expected traffic để giảm false positives.

Một cảnh báo hợp lý cần mô tả *vì sao idle bất thường*. Ví dụ “payment listener không nhận record 8 phút trong giờ cao điểm, producer publish rate vẫn 100 records/s, group lag tăng, container không pause” có tín hiệu sự cố mạnh hơn “consumer idle 8 phút”.

Không chạy `seekToEnd`, reset group offset hoặc mở group mới để làm mất cảnh báo nếu chưa xác định đúng nguyên nhân. Các thao tác đó có thể bỏ qua record chưa xử lý hoặc tạo duplicate, trong khi không khắc phục được producer outage hoặc consumer đang bị chặn.

## 23. Những nguyên tắc cốt lõi

1. **Consumer idle time không có một định nghĩa duy nhất:** phân biệt listener idle duration, poll idle ratio và thời gian từ lần poll cuối.
2. `idleEventInterval` phát `ListenerContainerIdleEvent` khi container không nhận record đủ lâu; event không tự thay đổi retry, offset hay consumer lifecycle.
3. Theo dõi `ListenerContainerNoLongerIdleEvent` để biết dữ liệu trở lại, nhưng không xem nó là bằng chứng xử lý nghiệp vụ thành công.
4. Khi nhiều partition thuộc một consumer, container có thể vẫn active dù một partition idle; dùng partition idle events khi cần.
5. `poll-idle-ratio-avg` là tỷ lệ chờ trong poll, **không phải số giây từ record cuối**.
6. `time-between-poll` và `NonResponsiveConsumerEvent` giúp phát hiện consumer thread bị kẹt; không dùng idle event để thay thế.
7. Cảnh báo chỉ hữu ích khi có expected traffic và bối cảnh: assignment, pause, lag, producer health, LSO và môi trường.
8. Không thực hiện HTTP/DB blocking trong event observer mặc định đồng bộ; không sử dụng Kafka consumer object từ thread khác.
9. Gauge custom cần xác định rõ điểm đo, xử lý trạng thái chưa có record, stop/rebalance và giới hạn metric tag cardinality.
10. Kết hợp listener idle, Kafka client metrics, processing latency, retry/DLT, consumer lag và business outcome để chẩn đoán reliability.

**Kết luận:** đo consumer idle time giúp xác định lúc một listener đang rảnh hoặc không nhận dữ liệu như kỳ vọng, nhưng chỉ có ý nghĩa khi đặt cạnh polling health, partition ownership và luồng dữ liệu thực tế. Trong Spring Kafka, `idleEventInterval` và các idle events cung cấp tín hiệu quan sát ở tầng container; Kafka client metrics giúp đánh giá mức chờ trong `poll()` và khả năng tiến triển của consumer. Phân biệt đúng các tín hiệu này giúp đội vận hành giảm cảnh báo giả, phát hiện consumer bị kẹt sớm và tránh các hành động reset offset hoặc restart không cần thiết.
