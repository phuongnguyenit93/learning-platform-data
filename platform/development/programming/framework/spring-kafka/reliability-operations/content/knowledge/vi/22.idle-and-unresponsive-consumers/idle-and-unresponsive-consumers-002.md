# idlePartitionEventInterval

Trong một Kafka consumer group, một consumer có thể được giao nhiều partition. Có lúc `orders-0` nhận record đều đặn trong khi `orders-1` không có record mới suốt nhiều phút. Nếu chỉ giám sát consumer ở mức container, ứng dụng có thể trông vẫn hoạt động bình thường vì luồng `orders-0` liên tục có dữ liệu. Tuy nhiên, đội vận hành có thể cần biết **partition nào đã lâu không giao record cho listener**, ngay cả khi những partition khác vẫn hoạt động.

Spring Kafka cung cấp thuộc tính **`idlePartitionEventInterval`** trên listener container để phát **`ListenerContainerPartitionIdleEvent`** khi một partition được gán không có record được nhận trong khoảng thời gian chỉ định. Khi partition từng idle có record trở lại, Spring Kafka có thể phát **`ListenerContainerPartitionNoLongerIdleEvent`**. Đây là các tín hiệu *quan sát trạng thái*, không phải lệnh tự động retry, seek, commit offset, tạm dừng hay khởi động lại consumer.

Điểm quan trọng nhất: **partition idle không đồng nghĩa consumer lỗi hoặc Kafka mất dữ liệu**. Topic có thể tạm hết traffic, producer có thể dừng hợp lệ, partition có thể đã bị pause, hoặc consumer có thể chỉ đang chờ record đủ điều kiện đọc theo transaction isolation. Bài học này trình bày cách cấu hình, xử lý sự kiện, phân biệt trạng thái và thiết kế cảnh báo vận hành đáng tin cậy.

## 1. Idle theo partition khác idle theo container

Giả sử một listener container được gán ba partition:

```text
Kafka topic: orders

orders-0  -->  10 records/s  --> Consumer A --> @KafkaListener
orders-1  -->   0 records/s  --> Consumer A --> @KafkaListener
orders-2  -->   2 records/s  --> Consumer A --> @KafkaListener
```

Container vẫn nhận record từ `orders-0` và `orders-2`, vì vậy cảnh báo **toàn container idle** thường không xuất hiện. Nhưng `orders-1` có thể không nhận record trong một khoảng dài. Chính trường hợp này là lý do tồn tại `idlePartitionEventInterval`.

| Cấu hình | Phạm vi theo dõi | Câu hỏi được trả lời |
|---|---|---|
| `idleEventInterval` | Toàn listener container | Consumer/container đã lâu không nhận record nào? |
| `idlePartitionEventInterval` | Từng partition được gán cho consumer | Partition cụ thể nào đã lâu không nhận record? |
| `noPollThreshold` với `monitorInterval` | Mức độ consumer phản hồi/poll | Consumer có bị kẹt quá lâu, không quay lại `poll()`? |
| Kafka consumer lag | Offset đã commit so với vị trí cuối tương ứng | Có backlog chưa được consumer group xử lý không? |

Với ví dụ trên, đặt `idlePartitionEventInterval=60_000` có thể tạo event cho `orders-1` dù tổng throughput của container vẫn cao. `idleEventInterval=60_000` chỉ có cơ hội phát khi **không partition nào** của container giao record trong ngưỡng quan sát tương ứng.

Không dùng sự vắng mặt của `ListenerContainerIdleEvent` để kết luận mọi partition đều có dữ liệu; cũng không dùng sự xuất hiện của `ListenerContainerPartitionIdleEvent` để kết luận toàn consumer bị treo.

## 2. `idlePartitionEventInterval` điều khiển điều gì?

`idlePartitionEventInterval` là khoảng thời gian tính bằng **mili giây**. Khi được đặt, Spring Kafka listener container theo dõi trạng thái idle cho từng partition và phát event khi khoảng thời gian không nhận record đáp ứng điều kiện của container.

Ví dụ:

```java
factory.getContainerProperties()
       .setIdlePartitionEventInterval(60_000L);
```

Giá trị `60_000L` tương ứng 60 giây. Đây là **ngưỡng phát sự kiện**, không phải ngưỡng khiến Kafka chủ động poll lại, không phải thời gian chờ retry, và không phải cấu hình `max.poll.interval.ms` của Kafka client.

Các đặc điểm cần hiểu:

- Event phản ánh trạng thái nhận record được quan sát bởi **listener container tại một thời điểm**, không phải hợp đồng producer phải gửi tối thiểu một record/phút.
- Với một partition tiếp tục idle, sự kiện idle có thể được phát **lặp lại theo khoảng cấu hình**, không chỉ một lần duy nhất cho cả đời partition.
- Khi partition đã idle nhận lại record, event *no longer idle* giúp quan sát thời điểm phục hồi hoạt động.
- Độ chính xác thời điểm phát phụ thuộc vòng `poll()`, thời gian xử lý, scheduling và lifecycle của container; không phải một bộ hẹn giờ thời gian thực có độ chính xác tuyệt đối.
- Chỉ những partition mà consumer/container đang **được gán và theo dõi** mới có ý nghĩa trong hệ thống sự kiện này. Partition không thuộc assignment của instance không phải partition idle của instance đó.

Đối với các phiên bản Spring Kafka khác nhau, thời điểm ra mắt và mức hỗ trợ của các event theo partition, cách tính idle và xử lý listener batch có thể khác. Khi nâng cấp thư viện, xác nhận `ContainerProperties.setIdlePartitionEventInterval(...)` và các event class thực tế trong dependency đang dùng.

## 3. Cấu hình trong `ConcurrentKafkaListenerContainerFactory`

Đây là cách rõ ràng để bật quan sát idle theo partition cho một nhóm listener cụ thể:

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
        properties.setIdlePartitionEventInterval(60_000L);
        properties.setIdleEventInterval(120_000L);
        properties.setPollTimeout(1_000L);
        properties.setAckMode(ContainerProperties.AckMode.RECORD);

        return factory;
    }
}
```

`OrderEvent` là class nghiệp vụ minh họa; `ConsumerFactory` cần được cấu hình deserializer, bootstrap, security và group settings phù hợp. `concurrency=3` có thể tạo nhiều child container/consumer threads; số consumer thực sự hoạt động và assignment phụ thuộc số partition và các thành viên khác trong group.

Ở ví dụ:

- Sau khoảng 60 giây không nhận record từ một partition, container có thể phát event idle tương ứng với partition đó.
- Nếu toàn bộ container không nhận record, `idleEventInterval=120_000` cho phép một sự kiện idle ở cấp container.
- `pollTimeout=1_000` chỉ là thời gian chờ của mỗi Kafka `poll()` do container quản lý; nó **không** đặt ngưỡng idle 1 giây và cũng **không** thay thế `max.poll.interval.ms`.

Đừng đặt ngưỡng quá nhỏ so với chu kỳ traffic và poll cadence, vì sự kiện có thể xuất hiện dồn dập mà không mang ý nghĩa sự cố. Với topic có traffic theo giờ, ngưỡng idle 60 giây hoàn toàn có thể là hành vi bình thường.

## 4. Bật theo một listener cụ thể

Để listener sử dụng cấu hình trên, chỉ định factory ở `@KafkaListener`:

```java
@Component
public class OrderListener {

    private final OrderService orderService;

    public OrderListener(OrderService orderService) {
        this.orderService = orderService;
    }

    @KafkaListener(
            id = "ordersPartitionMonitor",
            topics = "orders",
            groupId = "order-service",
            containerFactory = "ordersKafkaListenerContainerFactory")
    public void consume(OrderEvent event) {
        orderService.processIdempotently(event);
    }
}
```

Việc gắn factory rất quan trọng nếu ứng dụng có nhiều `@KafkaListener`. Chỉ khai báo một bean factory có bật idle events không chứng minh rằng listener đang chạy dùng nó. Khi có hai consumer groups khác nhau cùng subscribe topic, mỗi group/assignment có thể phát idle events riêng.

Thuộc tính này có thể được cấu hình qua API container hoặc qua cấu hình Spring Boot khi phiên bản Boot có hỗ trợ binding tương ứng. Để tránh phụ thuộc cách đặt tên property giữa các bản phát hành, ví dụ trên dùng `ContainerProperties` trực tiếp.

## 5. Bắt `ListenerContainerPartitionIdleEvent`

Spring có thể chuyển lifecycle events tới bean dùng `@EventListener`. Một observer nên xử lý nhanh, tập trung vào log, metric hoặc cập nhật trạng thái theo dõi:

```java
import org.apache.kafka.common.TopicPartition;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.event.EventListener;
import org.springframework.kafka.event.ListenerContainerPartitionIdleEvent;
import org.springframework.stereotype.Component;

@Component
public class PartitionIdleObserver {

    private static final Logger log = LoggerFactory.getLogger(
            PartitionIdleObserver.class);

    @EventListener
    public void onPartitionIdle(ListenerContainerPartitionIdleEvent event) {
        TopicPartition partition = event.getTopicPartition();

        log.info(
                "Kafka partition idle: topic={}, partition={}, idleMs={}",
                partition.topic(),
                partition.partition(),
                event.getIdleTime());
    }
}
```

`getTopicPartition()` xác định đúng partition đang idle; `getIdleTime()` diễn đạt khoảng thời gian idle được event ghi nhận. Các thuộc tính khác như listener/container identifier, consumer reference hoặc trạng thái pause phụ thuộc loại event và phiên bản Spring Kafka. Khi gắn nhãn log/metric theo container, dùng đúng API được phiên bản thực tế cung cấp.

**Không biến `@EventListener` thành nơi gọi database nặng, HTTP không có timeout hoặc xử lý batch dữ liệu.** Theo mặc định Spring application events được gửi đồng bộ trên thread phát event, và xử lý quá lâu có thể ảnh hưởng vòng xử lý của container.

## 6. Bắt event khi partition có dữ liệu trở lại

Để đo một khoảng idle đã kết thúc, theo dõi thêm `ListenerContainerPartitionNoLongerIdleEvent`:

```java
import org.springframework.context.event.EventListener;
import org.springframework.kafka.event.ListenerContainerPartitionNoLongerIdleEvent;
import org.springframework.stereotype.Component;

@Component
public class PartitionActiveObserver {

    @EventListener
    public void onActive(ListenerContainerPartitionNoLongerIdleEvent event) {
        TopicPartition partition = event.getTopicPartition();

        // Ghi nhận partition hoạt động trở lại trong monitoring.
        metrics.partitionNoLongerIdle(
                partition.topic(),
                partition.partition());
    }
}
```

`metrics` ở ví dụ là một adapter do ứng dụng định nghĩa; không phải biến có sẵn của Spring Kafka. Khi triển khai thực tế, inject một bean metric recorder phù hợp vào class thay vì dùng biến chưa khai báo. Một hình thức hoàn chỉnh có thể sử dụng constructor injection:

```java
@Component
public class PartitionActivityMetrics {

    private final PartitionStatusRecorder metrics;

    public PartitionActivityMetrics(PartitionStatusRecorder metrics) {
        this.metrics = metrics;
    }

    @EventListener
    public void onActive(ListenerContainerPartitionNoLongerIdleEvent event) {
        TopicPartition partition = event.getTopicPartition();
        metrics.markActive(partition.topic(), partition.partition());
    }
}
```

Trong đó `PartitionStatusRecorder` là interface do ứng dụng xây dựng để lưu trạng thái monitoring. `ListenerContainerPartitionNoLongerIdleEvent` cho biết **partition vừa nhận lại record sau giai đoạn idle được quan sát**, không chứng minh mọi record đã xử lý nghiệp vụ thành công. Nếu listener ném exception sau đó, vẫn cần theo dõi retry, DLT và offset.

## 7. Diễn tiến sự kiện theo từng partition

Giả sử một consumer quản lý `payments-0` và `payments-1`, ngưỡng idle theo partition là 30 giây:

```text
Thời gian         payments-0                 payments-1
-----------------------------------------------------------------
t = 0s            nhận record                nhận record
t = 10s           nhận record                không có record
t = 20s           nhận record                không có record
t ~ 30s           nhận record                PartitionIdleEvent
t = 40s           nhận record                vẫn không có record
t ~ 60s           nhận record                có thể phát idle lần tiếp
t = 65s           nhận record                nhận record mới
                                             NoLongerIdleEvent
```

Đây là timeline minh họa, không cam kết event được phát đúng tại dấu mốc đồng hồ 30.000 ms. Spring Kafka quan sát idle theo vòng vận hành của listener container, nên thời điểm thực tế còn phụ thuộc `pollTimeout`, tốc độ xử lý record và scheduling.

Tại `t=30s`, `payments-0` vẫn active, vì vậy **container không idle** theo nghĩa không nhận bất kỳ record nào. Chỉ `payments-1` phát event riêng. Tại `t=65s`, no-longer-idle cho partition 1 giúp hệ thống cập nhật trạng thái monitoring, nhưng chưa phải bằng chứng end-to-end nghiệp vụ đã hoàn tất.

## 8. Idle event không phải `NonResponsiveConsumerEvent`

Tên chương “Idle và non-responsive” dễ dẫn tới nhầm lẫn: một partition không có dữ liệu và một consumer ngừng poll là **hai tình huống khác nhau**.

```text
Tình huống A: Kafka không có record cho partition
  Consumer vẫn poll định kỳ
  Group membership ổn định
  Có thể xuất hiện PartitionIdleEvent

Tình huống B: Listener bị giữ 8 phút trong HTTP/SQL call
  Consumer thread chưa quay lại poll()
  Có nguy cơ vượt max.poll.interval.ms
  Có thể xuất hiện NonResponsiveConsumerEvent từ cơ chế monitor
  Có nguy cơ rebalance và xử lý lại offset chưa commit
```

`NonResponsiveConsumerEvent` liên quan tới cơ chế giám sát thời gian kể từ lần poll của container, thường qua `monitorInterval`, `noPollThreshold` và `pollTimeout` ở các phiên bản Spring Kafka hỗ trợ. Cơ chế này phù hợp để phát hiện consumer bị kẹt, còn `idlePartitionEventInterval` chỉ đo **thiếu record từ một partition đang được theo dõi**.

Không dùng `idlePartitionEventInterval` để thay thế timeout của HTTP client hay phát hiện deadlock. Một consumer thread đã bị chặn lâu có thể **không có cơ hội phát idle event đúng kỳ vọng**; sự vắng mặt của event không chứng minh consumer khỏe.

## 9. Idle event khác consumer lag như thế nào?

**Idle** mô tả không có record được container nhận trong một khoảng thời gian. **Lag** mô tả khoảng cách giữa committed offset của consumer group và một vị trí cuối phù hợp của Kafka log. Hai thông tin có thể cùng hoặc khác nhau.

| Tình huống | Idle event | Lag | Cách diễn giải |
|---|---|---|---|
| Topic tạm không có event mới, group đã xử lý hết | Có thể có | Gần 0 | Bình thường đối với topic ít traffic |
| Partition bị pause vì downstream quá tải | Có thể có tùy lifecycle/cấu hình | Có thể tăng | Intentional backpressure, không nhất thiết producer lỗi |
| Listener xử lý rất chậm, nhiều record đã poll | Không nhất thiết phát đúng hạn | Có thể tăng | Đo processing latency và poll responsiveness |
| Producer gửi event đều, nhưng consumer không nhận | Có thể có | Có thể tăng | Kiểm tra assignment, pause, fetch, auth, group và transaction LSO |
| Producer chỉ gửi vào một partition do key skew | Partition khác có thể idle | Phân bố lag lệch | Kiểm tra partitioning/traffic distribution |

Consumer với `isolation.level=read_committed` có thể chưa đọc được record phía sau một transaction mở sớm trên partition vì Last Stable Offset (LSO) chưa tiến. Đây là một lý do khiến log đã có record nhưng listener chưa nhận record tương ứng; cần phân biệt với topic hoàn toàn không có traffic.

Một cảnh báo đáng tin cậy thường kết hợp `PartitionIdleEvent` với **expected traffic**, **lag**, **producer acknowledgments**, **assignment** và **pause state**. Không báo mất dữ liệu chỉ từ một idle notification.

## 10. Idle sau pause/resume có ý nghĩa gì?

Spring Kafka có `pause()`/`resume()` ở mức container và hỗ trợ pause theo partition trong các phiên bản tương ứng. Khi partition bị pause, consumer thường không nhận record mới từ partition đó, nhưng container vẫn có thể tiếp tục poll để duy trì group membership.

```text
Downstream quá tải
      |
      v
Container.pausePartition(orders-2)
      |
      v
orders-2 không được fetch thêm trong thời gian pause
      |
      v
Nếu có idle event, phải xét trạng thái PAUSED trước khi alert
      |
      v
Downstream hồi phục -> resumePartition(orders-2)
```

Đừng tự động `resumePartition()` chỉ vì nhận `ListenerContainerPartitionIdleEvent`. Một partition có thể được pause **có chủ đích** vì dependency đang outage hoặc rate limit. Resume sai thời điểm có thể tạo retry storm và làm downstream quá tải trở lại.

Nếu muốn đưa pause state vào dashboard, lấy từ API được container hỗ trợ và thiết kế rõ nhiều lý do pause (manual intervention, circuit breaker, backoff). Theo dõi idle, pause và consumer lag như **những trục trạng thái riêng**.

## 11. Concurrency, group assignment và ownership

Với `ConcurrentKafkaListenerContainerFactory`, mỗi child container có Kafka consumer riêng. Kafka phân phối partition của topic cho các consumer trong cùng group; một partition tại một thời điểm thuộc về **một thành viên được gán** theo group protocol thông thường.

```text
orders topic: 6 partitions

Application instance A, group order-service
   child consumer A0 -> orders-0, orders-3
   child consumer A1 -> orders-1

Application instance B, cùng group
   child consumer B0 -> orders-2, orders-4
   child consumer B1 -> orders-5
```

Trong cấu hình đó, instance A có thể quan sát idle cho `orders-0`, `orders-1`, `orders-3`, nhưng **không** quan sát idle cho `orders-2`, `orders-4`, `orders-5` qua những consumer mà nó không sở hữu. Để có góc nhìn toàn group cần tổng hợp event từ mọi replica hoặc kết hợp Kafka metadata/metrics bên ngoài ứng dụng.

Sau rebalance, ownership có thể đổi. Một event idle trước rebalance không nên được lưu như trạng thái “orders-3 mãi mãi idle tại instance A”. Khi partition bị revoke, nên xóa hoặc đánh dấu hết hiệu lực state gắn với assignment cũ. Với các hệ thống lưu trạng thái lâu dài, thêm timestamp và owner/container identity để tránh báo nhầm.

## 12. Rebalance không phải partition idle

Trong consumer lifecycle, các callback revoke/assign có thể xảy ra khi một instance được thêm/xóa, container restart hoặc group cần cân bằng lại partition. Một partition vừa bị revoke có thể **không phát event idle** ở instance cũ vì nó không còn thuộc assignment.

Nếu cần dọn state của partition khi assignment đổi, có thể dùng `ConsumerAwareRebalanceListener`:

```java
factory.getContainerProperties().setConsumerRebalanceListener(
        new ConsumerAwareRebalanceListener() {

    @Override
    public void onPartitionsRevokedBeforeCommit(
            Consumer<?, ?> consumer,
            Collection<TopicPartition> partitions) {
        partitionStatusRecorder.removeOwnership(partitions);
    }

    @Override
    public void onPartitionsAssigned(
            Consumer<?, ?> consumer,
            Collection<TopicPartition> partitions) {
        partitionStatusRecorder.registerOwnership(partitions);
    }
});
```

`partitionStatusRecorder` là bean/adapter của ứng dụng dùng để lưu quan sát state. Trong mã triển khai thực tế, nó cần được inject hoặc giữ trong scope hợp lệ. Callback rebalance không nên thực hiện truy vấn database hoặc HTTP chậm, vì nó nằm trên đường điều phối Kafka consumer group.

Giám sát partition idle là quan sát **không có dữ liệu được nhận**; giám sát rebalance là quan sát **quyền sở hữu partition**. Hai hệ thống nên bổ sung cho nhau nhưng không dùng thay thế nhau.

## 13. Event listener phải ngắn và chú ý thread affinity

Theo mặc định, Spring `ApplicationEventMulticaster` thường gọi event listeners **đồng bộ trên thread phát event**. Kafka listener container phát các event idle từ ngữ cảnh consumer của nó, nên một event listener chậm có thể làm giảm tốc độ polling và tăng thời gian xử lý.

Không nên:

```java
@EventListener
public void onIdle(ListenerContainerPartitionIdleEvent event) {
    // Không gọi HTTP kiểm tra health không có timeout ở đây.
    // Không chạy query toàn bảng hoặc sleep chờ producer ở đây.
    // Không tự seek/commit offset để "chữa" trạng thái idle.
}
```

Nên:

```java
@EventListener
public void onIdle(ListenerContainerPartitionIdleEvent event) {
    TopicPartition partition = event.getTopicPartition();
    metricsRecorder.recordIdle(
            partition.topic(), partition.partition(), event.getIdleTime());
}
```

Đây là đoạn minh họa cần `metricsRecorder` được inject; thao tác nên nhanh và không chặn. Nếu application event multicaster được cấu hình bất đồng bộ, các callback có thể chạy trên executor thread khác. Khi đó, **không** truyền `KafkaConsumer` lấy từ event sang thread khác rồi gọi `pause()`, `seek()` hoặc `commitSync()`: Kafka consumer không thread-safe.

Nếu cần thực hiện một hành động quản trị như pause/resume, sử dụng container API qua `KafkaListenerEndpointRegistry` hoặc một coordinator được thiết kế riêng. Đừng thay đổi consumer assignment, offset hoặc lifecycle ngay trong một event observer chỉ vì vừa thấy partition idle.

## 14. Thiết kế state machine cho cảnh báo idle

Vì idle event có thể xuất hiện nhiều lần, đội vận hành nên quản lý trạng thái thay vì tạo một incident mới mỗi lần nhận event:

```text
             record đã nhận
                  |
                  v
                ACTIVE
                  |
       quá ngưỡng, PartitionIdleEvent
                  |
                  v
                 IDLE
                  |
           idle lặp lại
            (giữ IDLE)
                  |
           record xuất hiện
         NoLongerIdleEvent
                  |
                  v
                ACTIVE
```

Một state entry có thể bao gồm `(groupId, topic, partition, ownerInstance, timestamp, idleSince, observedIdleMs, paused, expectedTraffic)`. Không phải tất cả trường đều có sẵn trong event; `groupId`, owner và expected traffic có thể đến từ cấu hình/metrics ngoài event.

Để tránh false alarms, nên đặt điều kiện như:

1. Partition đã được assign ổn định trong một khoảng tối thiểu.
2. Partition **không bị pause có chủ đích**.
3. Topic/partition này **được kỳ vọng phải có traffic** tại thời điểm theo dõi.
4. Consumer group không đang rebalance hoặc shutdown.
5. Idle kéo dài vượt một ngưỡng SLO thực sự, không chỉ một lần event.

Nếu một partition vẫn idle nhưng đã có record trong Kafka log, so sánh producer lag, consumer lag, isolation level, partition assignment và client fetch metrics để phân biệt **producer không gửi** với **consumer không nhận**.

## 15. Chọn ngưỡng idle phù hợp với loại topic

Không có một `idlePartitionEventInterval` phù hợp cho mọi topic. Một số ví dụ:

| Loại luồng | Đặc điểm | Cách chọn ngưỡng |
|---|---|---|
| Payment/transaction realtime | Dự kiến lưu lượng liên tục trong giờ hoạt động | Ngưỡng vài chục giây đến vài phút, kết hợp expected traffic và SLO |
| Batch events mỗi 15 phút | Khoảng rỗng dài là bình thường | Chỉ alert sau lịch batch cộng biên độ trễ |
| Low-volume tenant/partition | Có thể nhiều giờ không có event | Idle chỉ để telemetry; không tự xem là sự cố |
| Heartbeat events | Producer cam kết nhịp gửi cụ thể | Có thể đối chiếu nhịp gửi với idle event và producer metrics |
| Retry topic | Record chỉ xuất hiện khi có lỗi cần retry | Không có dữ liệu thường là trạng thái **tốt** |
| DLT | Bình thường nên ít hoặc không có record | Không alert vì idle; nên alert khi DLT rate/b backlog tăng |

Đối với retry và DLT, đặt alert “partition idle 60 giây” là phản tác dụng: khi hệ thống không gặp lỗi, các topic đó có thể không nhận record suốt nhiều ngày. Cảnh báo phải phản ánh **nghĩa nghiệp vụ của topic**, không chỉ tính năng kỹ thuật của framework.

Nếu traffic theo múi giờ hoặc ngày làm việc, đưa lịch sản xuất dữ liệu vào alert evaluation. Không tạo sự cố giả mỗi đêm vì một partition hết đơn hàng sau giờ hoạt động.

## 16. Quan sát và metric nên đi kèm

Các event nên được bổ sung bằng metric và log nền tảng:

| Tín hiệu | Ý nghĩa |
|---|---|
| `ListenerContainerPartitionIdleEvent` count | Bao nhiêu lần partition vượt ngưỡng idle |
| `ListenerContainerPartitionNoLongerIdleEvent` count | Số lần nhận lại record sau idle |
| Idle duration per partition | Thời gian quan sát thiếu record ở partition |
| Consumer assignment/owner | Consumer nào đang chịu trách nhiệm partition |
| Consumer lag và last committed offset | Group còn backlog thực sự không |
| Poll count / time between polls | Consumer có còn gọi poll đều không |
| `NonResponsiveConsumerEvent` | Có dấu hiệu consumer bị kẹt trong xử lý/poll lifecycle không |
| Rebalance/partition revoke rate | Partition có đổi owner thường xuyên không |
| Pause requested / paused state | Không nhận record do chủ đích backpressure hay không |
| Producer publish count và errors | Producer có thực sự gửi đến partition không |

Không dùng message ID/offset làm label metrics vì cardinality quá lớn. `topic`, `partition`, listener ID và group ID thường có cardinality hữu hạn nhưng vẫn cần kiểm soát trong cluster có rất nhiều topic/partition. Dùng structured logs cho phần định danh chi tiết khi điều tra.

Khi container có `concurrency > 1`, các event có thể đến từ nhiều child threads. Một dashboard toàn service nên tổng hợp theo đúng `group + topic + partition` và chỉ giữ state của **owner hiện tại**, tránh đếm một partition ở cả owner cũ và owner mới sau rebalance.

## 17. Những lỗi triển khai thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Một partition im lặng nhưng không thấy event | Chưa set `idlePartitionEventInterval`, listener dùng factory khác hoặc partition không thuộc assignment | Kiểm tra factory thực tế, group assignment và phiên bản Spring Kafka |
| Chỉ thấy `ListenerContainerIdleEvent` | Mới bật `idleEventInterval`, chưa bật partition-level interval | Cấu hình `setIdlePartitionEventInterval(...)` |
| Event idle đến liên tục mỗi khoảng | Partition tiếp tục không nhận record nên event được phát lại | Dùng state machine/dedup alert, không mở incident mới cho mỗi event |
| Consumer khỏe nhưng bị cảnh báo chết | Nhầm idle partition với non-responsive poll | Kiểm tra `NonResponsiveConsumerEvent`, poll timing, lag và assignment |
| Partition bị pause mà lại báo producer lỗi | Pause làm container không nhận record | Gắn pause reason/state vào alert conditions |
| Không thấy no-longer-idle dù producer đã gửi | Record chưa tới consumer do pause, assignment, transaction LSO hoặc lỗi fetch | Kiểm tra broker/consumer lag và visibility của record |
| Alarm biến mất sau rebalance | State gắn với instance cũ, không cập nhật owner | Dùng rebalance callbacks hoặc tổng hợp theo group và owner mới |
| Event listener làm consumer chậm | Handler ghi DB/gọi HTTP blocking | Chỉ ghi metric/log nhanh, đưa xử lý chậm ra workflow riêng |
| Topic retry/DLT bị alert idle liên tục | Topic này vốn không cần traffic thường xuyên | Tắt cảnh báo idle hoặc dùng policy theo nghiệp vụ |
| `pollTimeout` thay đổi nhưng ngưỡng idle không như mong muốn | Nhầm poll timeout với idle interval | Đo đúng hai thuộc tính và quan sát thời điểm event thực tế |

Khi điều tra, luôn xác định điều nào đúng: **partition không có record trên broker**, **record có nhưng chưa visible**, **consumer không được assigned**, **consumer bị pause**, hay **consumer bị kẹt**. Cùng một biểu hiện không thấy record ở listener có thể đến từ năm nguyên nhân này và cần năm hướng xử lý khác nhau.

## 18. Kiểm thử tích hợp `idlePartitionEventInterval`

Một kiểm thử tốt nên dùng Kafka test broker hoặc Testcontainers, một topic nhiều partition và một listener container có `idlePartitionEventInterval` ngắn. Test nên quan sát event bằng đồng bộ hóa rõ ràng, không chỉ `Thread.sleep()` và suy luận từ log.

Kịch bản đề xuất:

1. Tạo topic `orders` có ít nhất hai partition và consumer group riêng cho test.
2. Cấu hình listener container với `setIdlePartitionEventInterval(1_000L)`; giữ `pollTimeout` tương đối ngắn để test dễ quan sát.
3. Gửi record liên tục vào partition 0, không gửi vào partition 1.
4. Xác nhận `ListenerContainerPartitionIdleEvent` xuất hiện cho partition 1 dù partition 0 đang active.
5. Gửi một record hợp lệ vào partition 1, xác nhận `ListenerContainerPartitionNoLongerIdleEvent` xuất hiện và listener nhận record.
6. Tiếp tục để partition 1 rỗng, xác nhận event idle có thể xuất hiện lại sau ngưỡng.
7. Pause partition 1, ghi nhận idle và pause state; test không được diễn giải pause là producer outage.
8. Rebalance bằng cách thêm/bớt một consumer cùng group; xác nhận owner mới được theo dõi đúng.
9. Dùng listener cố ý chặn để kích hoạt cơ chế non-responsive trong một test khác, chứng minh hai loại event không thay thế nhau.
10. Kiểm tra cả record processing, committed offset và group assignment; event idle riêng lẻ không phải xác nhận xử lý thành công.

Ví dụ một probe kiểm thử:

```java
@Component
public class PartitionIdleTestProbe {

    private final BlockingQueue<TopicPartition> idlePartitions =
            new LinkedBlockingQueue<>();

    private final BlockingQueue<TopicPartition> activePartitions =
            new LinkedBlockingQueue<>();

    @EventListener
    public void idle(ListenerContainerPartitionIdleEvent event) {
        idlePartitions.offer(event.getTopicPartition());
    }

    @EventListener
    public void active(ListenerContainerPartitionNoLongerIdleEvent event) {
        activePartitions.offer(event.getTopicPartition());
    }

    public TopicPartition awaitIdle(Duration timeout)
            throws InterruptedException {
        return idlePartitions.poll(timeout.toMillis(), TimeUnit.MILLISECONDS);
    }

    public TopicPartition awaitActive(Duration timeout)
            throws InterruptedException {
        return activePartitions.poll(timeout.toMillis(), TimeUnit.MILLISECONDS);
    }
}
```

Trong test, kiểm tra rõ `topic()` và `partition()` trả về từ queue. Nếu cả hai partition đều phát idle event, test cần lọc đúng partition đang kiểm chứng, không khẳng định event đầu tiên luôn thuộc partition 1. Đảm bảo consumer group đã được assigned partition trước khi bắt đầu tính khoảng thời gian quan sát.

Đây là ví dụ về probe; khi test nhiều lần trong cùng Spring context, phải làm sạch queue/state giữa các case để tránh nhận event còn sót. Các điều kiện về version, thread dispatch, poll cadence và số child consumers cần được kiểm tra phù hợp với môi trường thực tế.

## 19. Runbook khi một partition bất ngờ idle

Khi nhận cảnh báo rằng một partition production bất ngờ không có record, nên xử lý theo thứ tự:

1. **Xác minh tính kỳ vọng:** topic/partition có được kỳ vọng có record ở thời điểm này không? Có lịch batch hoặc traffic theo giờ không?
2. **Kiểm tra ownership:** consumer group và instance nào đang được assigned partition? Có rebalance hoặc deployment vừa xảy ra không?
3. **Kiểm tra pause:** container hoặc partition có bị pause do backpressure, retry/backoff hay thao tác vận hành không?
4. **So sánh broker và consumer:** producer có ghi record vào partition không? Lag và LSO/high watermark biểu thị điều gì?
5. **Kiểm tra poll responsiveness:** consumer còn poll và heartbeat đều không? Có `NonResponsiveConsumerEvent` hoặc `max.poll.interval.ms` warning không?
6. **Đọc log listener/error handler:** có lỗi deserialization, conversion, retries hoặc DLT trước khi partition trở nên idle không?
7. **Khắc phục nguyên nhân:** sửa producer routing, resume đúng quy trình, khôi phục dependency hoặc xử lý consumer bị kẹt; không seek/reset offset một cách tùy tiện.
8. **Quan sát phục hồi:** chờ partition nhận record mới, kiểm tra no-longer-idle, tiến độ offset và side effect nghiệp vụ.
9. **Ghi nhận sự cố:** lưu thời gian idle, owner, nhóm nguyên nhân, dữ liệu bị ảnh hưởng và thay đổi alert thresholds nếu cần.

Không reset consumer offset để cố khiến partition “có dữ liệu lại”. Reset lùi có thể phát lại record và tạo duplicate, reset tiến có thể bỏ qua record chưa được xử lý. Với một partition thực sự không có event mới, reset offset không khiến producer tự gửi dữ liệu.

## 20. Nguyên tắc production

1. `idlePartitionEventInterval` là ngưỡng **quan sát idle theo từng partition** ở mức Spring Kafka listener container.
2. `ListenerContainerPartitionIdleEvent` không có nghĩa consumer bị treo, Kafka mất record hoặc nghiệp vụ thất bại.
3. Phân biệt với `idleEventInterval` ở cấp container và `NonResponsiveConsumerEvent` liên quan tới vòng poll.
4. Cấu hình trên **đúng listener container factory**; kiểm tra group assignment thực tế, nhất là với concurrency và nhiều replica.
5. Xử lý event nhanh, không chặn consumer thread bằng HTTP/DB hoặc gọi Kafka consumer API từ thread khác.
6. Theo dõi `ListenerContainerPartitionNoLongerIdleEvent` để biết partition có record trở lại, nhưng không xem đó là bằng chứng business processing thành công.
7. Kết hợp expected traffic, pause state, rebalance, LSO, lag và producer metrics trước khi alert.
8. Không áp dụng cùng ngưỡng cảnh báo cho topic realtime, batch, retry và DLT.
9. Làm sạch state theo partition khi assignment thay đổi; dùng owner/timestamp để tránh nhầm lẫn sau rebalance.
10. Kiểm thử cả partition idle trong khi partition khác active, no-longer-idle, pause, rebalance và consumer non-responsive.

**Kết luận:** `idlePartitionEventInterval` giải quyết một khoảng trống quan sát quan trọng: **một partition có thể không nhận record dù consumer và các partition khác vẫn hoạt động**. Khi cấu hình đúng và kết hợp với trạng thái assignment, pause, consumer lag, nhịp producer và cảnh báo theo SLO, sự kiện này giúp phát hiện điểm bất thường ở cấp partition mà không đánh đồng im lặng bình thường với lỗi hệ thống.
